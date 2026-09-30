#!/usr/bin/env python3
"""Feature regressions for V-shapes — ridge primary, honest clocks.

Builds a causal feature panel on HL+Deribit+Kraken ETH (BTC if cheap) using
vstat continuous path + joins, then fits Ridge / OLS / ElasticNet / logistic
under explicit sampling clocks.

Primary target: trade-time forward return (next N trades).
Secondary: calendar-time mid/last returns (30s / 60s / 300s / hn).
Optional: volume-clock bar return.

Look-ahead ban: contemporaneous V and T+ use the right kernel after τ —
they are leakage diagnostics only. Causal set uses T−, lagged completed V,
running MinV, EGARCH breach, intensity/VPIN, geometric-overlap.

Sampling honesty: V-path on 5s price grid (book legacy, matching widen /
continuous_v). Decision subsample every 30s. Tick / volume targets from raw
tape. Latency assumption: features known at decision print; no mid-latency
model.

ClickHouse MCP banned. No soft-Promote.
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.linear_model import ElasticNet, LogisticRegression, Ridge
from sklearn.metrics import r2_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
APP = BOOK / "applications" / "feature_reg"
OUT = BOOK / "out" / "feature_reg"
FIG = OUT / "figs"

sys.path.insert(0, str(Path("/home/dev/lab/lab-n2070/warehouse/src")))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path("/home/dev/srv/ares-startarb") / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import (  # noqa: E402
    CORE_VENUES,
    ensure_env,
    load_day_trades,
)
from research.lib.continuous import trade_intensity, volume_clock_returns, vpin_bucket  # noqa: E402
from research.lib.crash import vshape_events  # noqa: E402
from research.lib.vstat import (  # noqa: E402
    grid_1s,
    min_v,
    returns_from_log_px,
    t_stat_side,
    v_path,
)

# ---------------------------------------------------------------------------
# Constants / clocks
# ---------------------------------------------------------------------------

HN_PRIMARY_S = 300.0  # 5m primary
HN_SET_S = (60.0, 300.0, 1800.0)  # 1m / 5m / 30m
DT_S = 5.0  # legacy book grid (documented)
DECISION_EVERY_S = 30.0
TICK_HORIZONS = (10, 20, 50)  # next-N trades; primary = 20
CAL_HORIZONS_S = (30, 60, 300, 300)  # last 300 duplicated as hn alias check
PRIMARY_TARGET = "y_tick_20"
PRIMARY_CLOCK = "trade_time_next_N_trades"
CAUSAL_FEATS = [
    "Tm",
    "abs_Tm",
    "Tm_1m",
    "V_lag",
    "abs_V_lag",
    "running_min_v",
    "abs_running_min_v",
    "breach",
    "geom_near",
    "log_intensity",
    "vpin_roll",
    "hn5_dummy",  # always 1 when hn=5 primary path — kept for multi-hn expand
]
LEAK_FEATS = ["V_now", "Tp"]  # right-kernel / contemporaneous V — leakage only
ALPHA_GRID = np.logspace(-2, 3, 12)


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        x = float(obj)
        return x if np.isfinite(x) else None
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return _jsonable(obj.tolist())
    return obj


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = np.isfinite(x) & np.isfinite(y)
    if int(m.sum()) < 8:
        return float("nan")
    xr = x[m].argsort().argsort().astype(float)
    yr = y[m].argsort().argsort().astype(float)
    xr -= xr.mean()
    yr -= yr.mean()
    den = float(np.sqrt((xr * xr).sum() * (yr * yr).sum()))
    return float((xr * yr).sum() / den) if den > 0 else float("nan")


def _block_boot_mean(vals: np.ndarray, *, n_boot: int = 400, block: int = 20, seed: int = 7) -> dict:
    v = np.asarray(vals, dtype=float)
    v = v[np.isfinite(v)]
    n = int(v.size)
    if n < 5:
        return {"mean": float("nan"), "lo": float("nan"), "hi": float("nan"), "n": n}
    rng = np.random.default_rng(seed)
    block = max(2, min(block, n // 3))
    means = []
    for _ in range(n_boot):
        starts = rng.integers(0, max(n - block, 1), size=max(1, n // block + 1))
        sample = np.concatenate([v[s : s + block] for s in starts])[:n]
        means.append(float(np.mean(sample)))
    lo, hi = np.percentile(means, [2.5, 97.5])
    return {"mean": float(np.mean(v)), "lo": float(lo), "hi": float(hi), "n": n}


def _load_day_plan() -> dict:
    p = BOOK / "out" / "widen_day_plan.json"
    if p.exists():
        return json.loads(p.read_text())
    return {
        "eth_days": [
            "2026-09-04",
            "2026-09-05",
            "2026-09-06",
            "2026-09-07",
            "2026-09-08",
            "2026-09-09",
            "2026-09-10",
            "2026-09-15",
            "2026-09-18",
            "2026-09-25",
            "2026-09-26",
            "2026-09-27",
            "2026-09-30",
        ],
        "btc_days": [
            "2026-09-04",
            "2026-09-05",
            "2026-09-08",
            "2026-09-15",
            "2026-09-25",
            "2026-09-30",
        ],
    }


def _minv_lookup() -> dict[tuple[str, str, str, int], dict]:
    """(symbol, venue, day, hn_min) → daily_minv row."""
    out: dict[tuple[str, str, str, int], dict] = {}
    for sym, name in (("ETH", "daily_minv_eth.json"), ("BTC", "daily_minv_btc.json")):
        path = BOOK / "out" / "daily_minv" / name
        if not path.exists():
            continue
        blob = json.loads(path.read_text())
        for r in blob.get("rows") or []:
            if not r.get("ok"):
                continue
            key = (sym, r["venue"], r["day"], int(r.get("hn_min") or 5))
            out[key] = r
    return out


def _fwd_tick_returns(
    ts: np.ndarray,
    px: np.ndarray,
    decision_ts: np.ndarray,
    n_trades: int,
) -> np.ndarray:
    """Log return over the next ``n_trades`` prints after each decision stamp."""
    ts = np.asarray(ts, dtype=np.int64)
    px = np.asarray(px, dtype=np.float64)
    out = np.full(decision_ts.shape, np.nan, dtype=float)
    if ts.size < n_trades + 2:
        return out
    idx = np.searchsorted(ts, decision_ts, side="right") - 1
    for i, j0 in enumerate(idx):
        if j0 < 0:
            continue
        j1 = j0 + n_trades
        if j1 >= ts.size:
            continue
        p0, p1 = float(px[j0]), float(px[j1])
        if p0 > 0 and p1 > 0 and np.isfinite(p0) and np.isfinite(p1):
            out[i] = float(np.log(p1 / p0))
    return out


def _fwd_cal_returns(
    grid_ts_ns: np.ndarray,
    grid_px: np.ndarray,
    decision_ts: np.ndarray,
    horizon_s: float,
) -> np.ndarray:
    """Calendar forward log return on the last-print grid."""
    step_ns = int(DT_S * 1e9)
    hops = max(1, int(round(horizon_s / DT_S)))
    out = np.full(decision_ts.shape, np.nan, dtype=float)
    idx = np.searchsorted(grid_ts_ns, decision_ts, side="right") - 1
    for i, j0 in enumerate(idx):
        j1 = j0 + hops
        if j0 < 0 or j1 >= grid_px.size:
            continue
        p0, p1 = float(grid_px[j0]), float(grid_px[j1])
        if p0 > 0 and p1 > 0 and np.isfinite(p0) and np.isfinite(p1):
            out[i] = float(np.log(p1 / p0))
    return out


def _fwd_vol_returns(
    ts: np.ndarray,
    px: np.ndarray,
    qty: np.ndarray,
    decision_ts: np.ndarray,
    *,
    bar_volume: float,
) -> np.ndarray:
    """Forward log return from decision price to next volume-clock close.

    Honest: uses px at decision (searchsorted) → px at next volume bar close,
    not the full bar return which may include pre-decision path.
    """
    vt, _vr = volume_clock_returns(ts, px, qty, bar_volume=bar_volume)
    out = np.full(decision_ts.shape, np.nan, dtype=float)
    if vt.size < 2:
        return out
    # map volume closes back to tape prices
    close_idx = np.searchsorted(ts, vt, side="right") - 1
    close_idx = np.clip(close_idx, 0, ts.size - 1)
    close_px = px[close_idx]
    j = np.searchsorted(vt, decision_ts, side="right")
    dec_i = np.searchsorted(ts, decision_ts, side="right") - 1
    for i, ji in enumerate(j):
        di = int(dec_i[i])
        if di < 0 or ji < 0 or ji >= close_px.size:
            continue
        p0, p1 = float(px[di]), float(close_px[ji])
        if p0 > 0 and p1 > 0 and np.isfinite(p0) and np.isfinite(p1):
            out[i] = float(np.log(p1 / p0))
    return out


def _vpin_at_decisions(
    ts: np.ndarray,
    side: np.ndarray,
    qty: np.ndarray,
    decision_ts: np.ndarray,
) -> np.ndarray:
    """Causal rolling VPIN up to each decision (bucket mean so far)."""
    out = np.full(decision_ts.shape, np.nan, dtype=float)
    if ts.size < 80:
        return out
    med_q = float(np.nanmedian(qty[np.isfinite(qty) & (qty > 0)]))
    if not np.isfinite(med_q) or med_q <= 0:
        return out
    bucket = max(med_q * 40.0, 1e-6)
    # Build cumulative VPIN series on trade clock, then map
    s = np.asarray(side, dtype=float)
    q = np.asarray(qty, dtype=float)
    m = np.isfinite(s) & np.isfinite(q) & (q > 0) & (s != 0)
    if int(m.sum()) < 80:
        return out
    ts_m, s_m, q_m = ts[m], s[m], q[m]
    buy = sell = vol = 0.0
    imbalances: list[float] = []
    close_ts: list[int] = []
    for i in range(ts_m.size):
        if s_m[i] > 0:
            buy += q_m[i]
        else:
            sell += q_m[i]
        vol += q_m[i]
        if vol >= bucket:
            tot = buy + sell
            imbalances.append(abs(buy - sell) / tot if tot > 0 else float("nan"))
            close_ts.append(int(ts_m[i]))
            buy = sell = vol = 0.0
    if len(imbalances) < 5:
        return out
    imb = np.asarray(imbalances, dtype=float)
    cts = np.asarray(close_ts, dtype=np.int64)
    # rolling mean of last 20 buckets
    win = 20
    roll = np.full(imb.shape, np.nan)
    for i in range(imb.size):
        a = max(0, i - win + 1)
        chunk = imb[a : i + 1]
        chunk = chunk[np.isfinite(chunk)]
        if chunk.size:
            roll[i] = float(np.mean(chunk))
    j = np.searchsorted(cts, decision_ts, side="right") - 1
    for i, ji in enumerate(j):
        if ji >= 0:
            out[i] = float(roll[ji])
    return out


def _intensity_at_decisions(ts: np.ndarray, decision_ts: np.ndarray, lookback_s: float) -> np.ndarray:
    out = np.full(decision_ts.shape, np.nan, dtype=float)
    if ts.size < 10:
        return out
    lb = int(lookback_s * 1e9)
    for i, t0 in enumerate(decision_ts):
        lo = t0 - lb
        n = int(np.searchsorted(ts, t0, side="right") - np.searchsorted(ts, lo, side="left"))
        out[i] = float(n) / max(lookback_s, 1.0)
    return out


def _geom_near_flags(
    ts: np.ndarray,
    px: np.ndarray,
    decision_ts: np.ndarray,
    *,
    window_s: float = 300.0,
) -> np.ndarray:
    """1 if a geometric crash.vshape mid falls within ±window of decision."""
    out = np.zeros(decision_ts.shape, dtype=float)
    try:
        # Match book siblings (exp_panel_case / liq_xvenue): hn-scale legs.
        ev = vshape_events(ts, px, min_pct=0.005, max_leg_s=300.0, min_recovery=0.4)
    except Exception:  # noqa: BLE001
        return out
    mid_i = np.asarray(ev.get("mid_i", []), dtype=np.int64)
    if mid_i.size == 0:
        return out
    ok = (mid_i >= 0) & (mid_i < ts.size)
    troughs = ts[mid_i[ok]]
    if troughs.size == 0:
        return out
    w = int(window_s * 1e9)
    for i, t0 in enumerate(decision_ts):
        if np.any(np.abs(troughs.astype(np.int64) - int(t0)) <= w):
            out[i] = 1.0
    return out


def build_day_rows(
    symbol: str,
    venue: str,
    day: str,
    *,
    max_files: int,
    minv_map: dict,
    fast: bool,
) -> list[dict]:
    try:
        rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
    except Exception as exc:  # noqa: BLE001
        return [{"symbol": symbol, "venue": venue, "day": day, "ok": False, "error": str(exc)}]
    tape = rec["tape"]
    comp = rec["completeness"]
    if not comp.get("complete"):
        return [
            {
                "symbol": symbol,
                "venue": venue,
                "day": day,
                "ok": False,
                "reason": "incomplete",
                "completeness": comp,
            }
        ]
    ts = np.asarray(tape["ts"], dtype=np.int64)
    px = np.asarray(tape["px"], dtype=np.float64)
    qty = np.asarray(tape["qty"], dtype=np.float64)
    side = np.asarray(tape["side"], dtype=np.float64)
    g = grid_1s(ts, px, dt_s=DT_S)
    if int(g["n_filled"]) < 120:
        return [{"symbol": symbol, "venue": venue, "day": day, "ok": False, "reason": "short_grid"}]
    t, r = returns_from_log_px(g["log_px"], g["ts_ns"], time_unit_s=1.0)
    hn = HN_PRIMARY_S
    t0, t1 = float(t[0] + hn), float(t[-1] - hn)
    if t1 <= t0:
        return [{"symbol": symbol, "venue": venue, "day": day, "ok": False, "reason": "hn_too_wide"}]
    n_grid = 31 if fast else 51
    taus = np.linspace(t0, t1, n_grid)
    path = v_path(t, r, taus, hn)
    V, Tm, Tp = path["V"], path["T_minus"], path["T_plus"]
    mv = min_v(t, r, taus, hn)
    # decision stamps on price grid every DECISION_EVERY_S, inside (t0, t1-max_horizon)
    g_ts = np.asarray(g["ts_ns"], dtype=np.int64)
    g_px = np.asarray(g["px"], dtype=np.float64)
    # map return times → grid ts: returns align to g_ts[1:]
    ret_ts = g_ts[1 : 1 + r.size]
    if ret_ts.size != r.size:
        ret_ts = g_ts[max(0, g_ts.size - r.size) :]
        ret_ts = ret_ts[: r.size]
    # decision indices into return time
    step = max(1, int(round(DECISION_EVERY_S / DT_S)))
    # leave room for 300s calendar fwd (60 steps of 5s)
    max_fwd_steps = 60
    dec_idx = np.arange(int(hn / DT_S) + 1, r.size - max_fwd_steps - 1, step, dtype=int)
    if dec_idx.size < 8:
        return [{"symbol": symbol, "venue": venue, "day": day, "ok": False, "reason": "few_decisions"}]
    dec_t = t[dec_idx]
    dec_ts = ret_ts[dec_idx]

    # interpolate path features onto decision times
    def _interp(y: np.ndarray, tau_q: np.ndarray) -> np.ndarray:
        m = np.isfinite(y)
        if int(m.sum()) < 3:
            return np.full(tau_q.shape, np.nan)
        return np.interp(tau_q, path["tau"][m], y[m], left=np.nan, right=np.nan)

    V_now = _interp(V, dec_t)
    Tm_now = _interp(Tm, dec_t)
    Tp_now = _interp(Tp, dec_t)
    # causal lagged V: V(τ − hn) — right kernel closed at τ
    V_lag = _interp(V, dec_t - hn)
    # running MinV of completed path points with tau ≤ decision
    running = np.full(dec_t.shape, np.nan)
    order = np.argsort(path["tau"])
    tau_s = path["tau"][order]
    V_s = V[order]
    cmin = np.nan
    j = 0
    for i, tau in enumerate(dec_t):
        while j < tau_s.size and tau_s[j] <= tau:
            vj = V_s[j]
            if np.isfinite(vj):
                cmin = vj if (not np.isfinite(cmin) or vj < cmin) else cmin
            j += 1
        running[i] = cmin

    # Tm at hn=1m (causal left kernel) on path taus, then interpolate
    Tm_1m_path = np.array(
        [t_stat_side(t, r, float(tau), 60.0, side="left") for tau in path["tau"]],
        dtype=float,
    )
    Tm_1m = _interp(Tm_1m_path, dec_t)

    row5 = minv_map.get((symbol, venue, day, 5), {})
    q05 = float(row5.get("q05", np.nan)) if row5 else float("nan")
    day_minv = float(row5.get("min_v", mv["min_v"])) if row5 else float(mv["min_v"])
    day_sig = bool(row5.get("sig_5", False)) if row5 else bool(
        np.isfinite(day_minv) and np.isfinite(q05) and day_minv < q05
    )
    # causal breach: running_min_v vs EGARCH q05 (same-day band from panel)
    breach = np.zeros(dec_t.shape, dtype=float)
    if np.isfinite(q05):
        breach = (np.isfinite(running) & (running < q05)).astype(float)
    elif day_sig:
        # fallback: mark after observed trough time only
        if np.isfinite(mv["tau_star"]):
            breach = (dec_t >= float(mv["tau_star"])).astype(float)

    intensity = _intensity_at_decisions(ts, dec_ts, lookback_s=hn)
    vpin = _vpin_at_decisions(ts, side, qty, dec_ts)
    geom = _geom_near_flags(ts, px, dec_ts, window_s=hn)

    # targets
    targets: dict[str, np.ndarray] = {}
    for n_tr in TICK_HORIZONS:
        targets[f"y_tick_{n_tr}"] = _fwd_tick_returns(ts, px, dec_ts, n_tr)
    for hs in (30, 60, 300):
        targets[f"y_cal_{hs}s"] = _fwd_cal_returns(g_ts, g_px, dec_ts, float(hs))
    targets["y_cal_hn"] = targets["y_cal_300s"].copy()
    med_q = float(np.nanmedian(qty[np.isfinite(qty) & (qty > 0)])) if qty.size else 1.0
    bar_vol = max(med_q * 80.0, 1e-6)
    targets["y_vol"] = _fwd_vol_returns(ts, px, qty, dec_ts, bar_volume=bar_vol)

    rows: list[dict] = []
    for i in range(dec_t.size):
        feat = {
            "Tm": float(Tm_now[i]),
            "abs_Tm": float(abs(Tm_now[i])) if np.isfinite(Tm_now[i]) else float("nan"),
            "Tm_1m": float(Tm_1m[i]),
            "V_lag": float(V_lag[i]),
            "abs_V_lag": float(abs(V_lag[i])) if np.isfinite(V_lag[i]) else float("nan"),
            "running_min_v": float(running[i]),
            "abs_running_min_v": float(abs(running[i])) if np.isfinite(running[i]) else float("nan"),
            "breach": float(breach[i]),
            "geom_near": float(geom[i]),
            "log_intensity": float(np.log(max(intensity[i], 1e-8))) if np.isfinite(intensity[i]) else float("nan"),
            "vpin_roll": float(vpin[i]),
            "hn5_dummy": 1.0,
            # leakage diagnostics
            "V_now": float(V_now[i]),
            "Tp": float(Tp_now[i]),
        }
        y = {k: float(v[i]) for k, v in targets.items()}
        rows.append(
            {
                "ok": True,
                "symbol": symbol,
                "venue": venue,
                "day": day,
                "tau_s": float(dec_t[i]),
                "ts_ns": int(dec_ts[i]),
                "day_min_v": day_minv,
                "day_sig5": day_sig,
                "q05": q05,
                "features": feat,
                "targets": y,
                "dt_s": DT_S,
                "decision_every_s": DECISION_EVERY_S,
                "hn_primary_s": hn,
            }
        )
    return rows


def build_panel(*, max_files: int, fast: bool, include_btc: bool) -> dict:
    ensure_env()
    plan = _load_day_plan()
    minv_map = _minv_lookup()
    eth_days = list(plan.get("eth_days") or [])
    btc_days = list(plan.get("btc_days") or [])
    if fast:
        eth_days = eth_days[:8]
        btc_days = btc_days[:4]
    jobs = [("ETH", d) for d in eth_days]
    if include_btc:
        jobs += [("BTC", d) for d in btc_days]
    rows: list[dict] = []
    meta_days: list[dict] = []
    for symbol, day in jobs:
        for venue in CORE_VENUES:
            day_rows = build_day_rows(
                symbol, venue, day, max_files=max_files, minv_map=minv_map, fast=fast
            )
            ok_rows = [r for r in day_rows if r.get("ok")]
            meta_days.append(
                {
                    "symbol": symbol,
                    "venue": venue,
                    "day": day,
                    "n_ok": len(ok_rows),
                    "status": "ok" if ok_rows else (day_rows[0].get("reason") or day_rows[0].get("error") or "empty"),
                }
            )
            rows.extend(ok_rows)
            print(
                f"  panel {symbol} {venue} {day}: n={len(ok_rows)} status={meta_days[-1]['status']}",
                flush=True,
            )
    panel = {
        "sampling": {
            "price_grid_dt_s": DT_S,
            "decision_every_s": DECISION_EVERY_S,
            "hn_primary_s": HN_PRIMARY_S,
            "primary_target": PRIMARY_TARGET,
            "primary_clock": PRIMARY_CLOCK,
            "note": (
                "5s last-print grid is book legacy (same as continuous_v / widen). "
                "Decision subsample every 30s. Tick/volume targets from raw tape. "
                "Causal features exclude contemporaneous V and T+ (right kernel)."
            ),
            "latency_assumption": "features known at decision print; no exchange-latency model",
            "look_ahead_ban": "V_now and Tp are leakage-only; never in primary design matrix",
        },
        "causal_feats": CAUSAL_FEATS,
        "leak_feats": LEAK_FEATS,
        "n_rows": len(rows),
        "day_meta": meta_days,
        "rows": rows,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "panel_meta.json").write_text(
        json.dumps(
            {
                "sampling": panel["sampling"],
                "causal_feats": CAUSAL_FEATS,
                "leak_feats": LEAK_FEATS,
                "n_rows": len(rows),
                "day_meta": meta_days,
                "n_days_eth": len(eth_days),
                "n_days_btc": len(btc_days) if include_btc else 0,
                "venues": list(CORE_VENUES),
            },
            indent=2,
            default=str,
        )
    )
    # store compact row table (features+targets flattened)
    flat = []
    for r in rows:
        flat.append(
            {
                "symbol": r["symbol"],
                "venue": r["venue"],
                "day": r["day"],
                "tau_s": r["tau_s"],
                "ts_ns": r["ts_ns"],
                "day_sig5": r["day_sig5"],
                **{f"f_{k}": r["features"][k] for k in CAUSAL_FEATS + LEAK_FEATS},
                **{k: r["targets"][k] for k in r["targets"]},
            }
        )
    (OUT / "panel_rows.json").write_text(json.dumps(_jsonable(flat), indent=2))
    return panel


def _design(rows: list[dict], feats: list[str], target: str) -> tuple[np.ndarray, np.ndarray, list[str], np.ndarray]:
    days = [r["day"] for r in rows]
    X = np.column_stack(
        [np.asarray([r["features"].get(c, np.nan) for r in rows], dtype=float) for c in feats]
    )
    y = np.asarray([r["targets"].get(target, np.nan) for r in rows], dtype=float)
    m = np.isfinite(X).all(axis=1) & np.isfinite(y)
    # drop constant columns after mask
    return X[m], y[m], [d for d, keep in zip(days, m) if keep], m


def _chrono_split(days: list[str], frac: float = 0.6) -> tuple[np.ndarray, np.ndarray]:
    uniq = sorted(set(days))
    cut_i = max(1, min(len(uniq) - 1, int(round(frac * len(uniq)))))
    train_days = set(uniq[:cut_i])
    tr = np.asarray([d in train_days for d in days], dtype=bool)
    te = ~tr
    return tr, te


def _impute(tr: np.ndarray, te: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    med = np.nanmedian(tr, axis=0)
    med = np.where(np.isfinite(med), med, 0.0)
    tr2, te2 = tr.copy(), te.copy()
    for j in range(tr.shape[1]):
        tr2[np.isnan(tr2[:, j]), j] = med[j]
        te2[np.isnan(te2[:, j]), j] = med[j]
    return tr2, te2


def _time_blocked_cv(
    X: np.ndarray,
    y: np.ndarray,
    days: list[str],
    *,
    alphas: np.ndarray,
    n_folds: int = 4,
) -> dict:
    uniq = sorted(set(days))
    if len(uniq) < n_folds + 1:
        n_folds = max(2, len(uniq) - 1)
    fold_size = max(1, len(uniq) // n_folds)
    path = []
    for a in alphas:
        fold_ics = []
        fold_r2 = []
        for f in range(n_folds):
            te_days = set(uniq[f * fold_size : (f + 1) * fold_size] or uniq[-1:])
            te = np.asarray([d in te_days for d in days], dtype=bool)
            tr = ~te
            if int(tr.sum()) < 30 or int(te.sum()) < 15:
                continue
            Xtr, Xte = _impute(X[tr], X[te])
            pipe = Pipeline([("sc", StandardScaler()), ("rg", Ridge(alpha=float(a)))])
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                pipe.fit(Xtr, y[tr])
            pred = pipe.predict(Xte)
            fold_ics.append(_spearman(pred, y[te]))
            fold_r2.append(float(r2_score(y[te], pred)))
        path.append(
            {
                "alpha": float(a),
                "ic_mean": float(np.nanmean(fold_ics)) if fold_ics else float("nan"),
                "r2_mean": float(np.nanmean(fold_r2)) if fold_r2 else float("nan"),
                "n_folds_ok": len(fold_ics),
            }
        )
    best = max(path, key=lambda z: (z["ic_mean"] if np.isfinite(z["ic_mean"]) else -9))
    return {"path": path, "best_alpha": best["alpha"], "best": best}


def fit_ridge_suite(
    rows: list[dict],
    *,
    target: str,
    feats: list[str],
    tag: str,
) -> dict:
    X, y, days, _ = _design(rows, feats, target)
    n = int(y.size)
    if n < 80:
        return {"tag": tag, "target": target, "n": n, "error": "too_few"}
    tr, te = _chrono_split(days, 0.6)
    if int(tr.sum()) < 40 or int(te.sum()) < 20:
        return {"tag": tag, "target": target, "n": n, "error": "split_too_small"}
    Xtr, Xte = _impute(X[tr], X[te])
    ytr, yte = y[tr], y[te]
    cv = _time_blocked_cv(X, y, days, alphas=ALPHA_GRID)
    alpha = float(cv["best_alpha"])
    pipe = Pipeline([("sc", StandardScaler()), ("rg", Ridge(alpha=alpha))])
    pipe.fit(Xtr, ytr)
    pred_tr = pipe.predict(Xtr)
    pred_te = pipe.predict(Xte)
    coef = pipe.named_steps["rg"].coef_.ravel()
    ic_te = _spearman(pred_te, yte)
    # residual block bootstrap of IC
    rng = np.random.default_rng(11)
    ics = []
    block = max(5, len(yte) // 25)
    for _ in range(300):
        starts = rng.integers(0, max(len(yte) - block, 1), size=max(1, len(yte) // block + 1))
        idx = np.concatenate([np.arange(s, min(s + block, len(yte))) for s in starts])[: len(yte)]
        ics.append(_spearman(pred_te[idx], yte[idx]))
    ic_lo, ic_hi = np.nanpercentile(ics, [2.5, 97.5]) if ics else (np.nan, np.nan)
    # OLS (alpha→0 ridge for stability under collinearity — report as OLS-ish)
    ols = Pipeline([("sc", StandardScaler()), ("rg", Ridge(alpha=1e-6))])
    ols.fit(Xtr, ytr)
    ols_pred = ols.predict(Xte)
    # ElasticNet
    en = Pipeline(
        [("sc", StandardScaler()), ("en", ElasticNet(alpha=0.05, l1_ratio=0.3, max_iter=5000))]
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        en.fit(Xtr, ytr)
    en_pred = en.predict(Xte)
    # OOS early/late: split *test* days in half (train is already earlier chronologically)
    days_arr = np.asarray(days)
    te_days = days_arr[te]
    te_uniq = sorted(set(te_days.tolist()))
    mid_te = max(1, len(te_uniq) // 2)
    early_te_days = set(te_uniq[:mid_te])
    late_te_days = set(te_uniq[mid_te:])
    early_te = np.asarray([d in early_te_days for d in te_days], dtype=bool)
    late_te = np.asarray([d in late_te_days for d in te_days], dtype=bool)
    ic_early = _spearman(pred_te[early_te], yte[early_te]) if int(early_te.sum()) >= 15 else float("nan")
    ic_late = _spearman(pred_te[late_te], yte[late_te]) if int(late_te.sum()) >= 15 else float("nan")
    sign_stable = bool(
        np.isfinite(ic_early)
        and np.isfinite(ic_late)
        and np.sign(ic_early) == np.sign(ic_late)
        and abs(ic_early) >= 0.02
        and abs(ic_late) >= 0.02
    )
    r2_te = float(r2_score(yte, pred_te))
    ic_excludes_0 = bool(np.isfinite(ic_lo) and np.isfinite(ic_hi) and (ic_hi < 0 or ic_lo > 0))
    promote_ok = bool(r2_te > 0 and ic_excludes_0 and sign_stable and abs(ic_te) >= 0.05)
    train_day_set = sorted(set(days_arr[tr].tolist()))
    return {
        "tag": tag,
        "target": target,
        "feats": feats,
        "n": n,
        "n_train": int(tr.sum()),
        "n_test": int(te.sum()),
        "train_days": train_day_set,
        "test_days": te_uniq,
        "alpha": alpha,
        "cv": cv,
        "ridge": {
            "r2_train": float(r2_score(ytr, pred_tr)),
            "r2_test": r2_te,
            "ic_test": float(ic_te),
            "ic_boot": {"lo": float(ic_lo), "hi": float(ic_hi), "excludes_0": ic_excludes_0},
            "rmse_test": float(np.sqrt(np.mean((yte - pred_te) ** 2))),
            "coef": {feats[i]: float(coef[i]) for i in range(len(feats))},
            "ic_early_oos": float(ic_early),
            "ic_late_oos": float(ic_late),
            "sign_stable": sign_stable,
        },
        "ols": {
            "r2_test": float(r2_score(yte, ols_pred)),
            "ic_test": float(_spearman(ols_pred, yte)),
            "coef": {
                feats[i]: float(ols.named_steps["rg"].coef_.ravel()[i]) for i in range(len(feats))
            },
        },
        "elasticnet": {
            "r2_test": float(r2_score(yte, en_pred)),
            "ic_test": float(_spearman(en_pred, yte)),
            "coef": {
                feats[i]: float(en.named_steps["en"].coef_.ravel()[i]) for i in range(len(feats))
            },
        },
        "oos_pred": {
            "y": yte.tolist(),
            "pred": pred_te.tolist(),
            "days": te_days.tolist(),
        },
        "promote_ok": promote_ok,
        "decision_hint": "Promote" if promote_ok else "Hold",
    }


def fit_logistic_breach_sign(rows: list[dict]) -> dict:
    """Logistic: breach → sign of primary target (fade / continuation)."""
    X, y, days, _ = _design(rows, CAUSAL_FEATS, PRIMARY_TARGET)
    if y.size < 80:
        return {"n": int(y.size), "error": "too_few"}
    # only rows with breach==1 for sign model? better: predict P(y>0) from feats incl breach
    y_bin = (y > 0).astype(float)
    tr, te = _chrono_split(days, 0.6)
    if len(np.unique(y_bin[tr])) < 2 or len(np.unique(y_bin[te])) < 2:
        return {"n": int(y.size), "error": "single_class"}
    Xtr, Xte = _impute(X[tr], X[te])
    pipe = Pipeline(
        [
            ("sc", StandardScaler()),
            (
                "clf",
                LogisticRegression(
                    C=0.5, max_iter=2000, class_weight="balanced", solver="lbfgs"
                ),
            ),
        ]
    )
    pipe.fit(Xtr, y_bin[tr])
    proba = pipe.predict_proba(Xte)[:, 1]
    try:
        auc = float(roc_auc_score(y_bin[te], proba))
    except Exception:  # noqa: BLE001
        auc = float("nan")
    coef = pipe.named_steps["clf"].coef_.ravel()
    return {
        "target": f"sign({PRIMARY_TARGET}>0)",
        "n": int(y.size),
        "n_train": int(tr.sum()),
        "n_test": int(te.sum()),
        "auc_test": auc,
        "base_rate_test": float(y_bin[te].mean()),
        "coef": {CAUSAL_FEATS[i]: float(coef[i]) for i in range(len(CAUSAL_FEATS))},
        "promote_ok": bool(np.isfinite(auc) and auc >= 0.58),
        "decision_hint": "Promote" if (np.isfinite(auc) and auc >= 0.58) else "Hold",
    }


def _fig_train_test_split(prim: dict, meta: dict | None = None) -> None:
    """Chronological day split honesty — train (earlier) vs test (later)."""
    train_days = list(prim.get("train_days") or [])
    test_days = list(prim.get("test_days") or [])
    day_meta = (meta or {}).get("day_meta") or []
    # rows per UTC day (sum venues/symbols)
    counts: dict[str, int] = {}
    for r in day_meta:
        d = r.get("day")
        if not d:
            continue
        counts[d] = counts.get(d, 0) + int(r.get("n_ok") or 0)
    all_days = sorted(set(train_days) | set(test_days) | set(counts))
    if not all_days:
        all_days = train_days + test_days
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.0), gridspec_kw={"width_ratios": [2.2, 1]})
    ax = axes[0]
    xs, ys, colors = [], [], []
    for i, d in enumerate(all_days):
        xs.append(i)
        ys.append(counts.get(d, 0))
        colors.append("#3d5a5b" if d in train_days else "#8b3a3a")
    ax.bar(xs, ys, color=colors, alpha=0.9)
    ax.set_xticks(xs)
    ax.set_xticklabels([d[5:] for d in all_days], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Decision rows (n_ok sum)")
    ax.set_title("Chrono day split — teal=train · red=test")
    ax.grid(True, axis="y", alpha=0.3)
    ax2 = axes[1]
    n_tr = int(prim.get("n_train") or 0)
    n_te = int(prim.get("n_test") or 0)
    ax2.bar(["train", "test"], [n_tr, n_te], color=["#3d5a5b", "#8b3a3a"], alpha=0.9)
    ax2.set_ylabel("n rows")
    ax2.set_title(f"n_train={n_tr:,}  n_test={n_te:,}")
    for i, v in enumerate([n_tr, n_te]):
        ax2.text(i, v, f"{v:,}", ha="center", va="bottom", fontsize=9)
    fig.suptitle(
        f"Train/test honesty — {prim.get('target', PRIMARY_TARGET)}  "
        f"({len(train_days)}/{len(test_days)} UTC days)",
        fontsize=11,
    )
    fig.tight_layout()
    fig.savefig(FIG / "train_test_split.png", dpi=140)
    plt.close(fig)


def _fig_calendar_coefs(results: dict) -> None:
    """Leading calendar-clock Ridge coefs (Promote-as-Monitor target)."""
    blk = (results.get("by_target") or {}).get("y_cal_300s") or {}
    coef = ((blk.get("ridge") or {}).get("coef")) or blk.get("coef") or {}
    if not coef:
        return
    names = list(coef.keys())
    vals = [float(coef[n]) for n in names]
    order = np.argsort(np.abs(vals))[::-1]
    names = [names[i] for i in order]
    vals = [vals[i] for i in order]
    fig, ax = plt.subplots(figsize=(8.0, 4.2))
    ax.barh(names, vals, color="#2f4f4f")
    ax.axvline(0, color="gray", lw=0.8)
    ax.set_xlabel("Standardized Ridge coef")
    ax.set_title("Coefs — y_cal_300s (calendar Monitor Promote)")
    fig.tight_layout()
    fig.savefig(FIG / "ridge_coefs_calendar.png", dpi=140)
    plt.close(fig)


def make_figures(results: dict, meta: dict | None = None) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    # IC by horizon
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    labels, ics, los, his = [], [], [], []
    for key, blk in results.get("by_target", {}).items():
        ridge = (blk or {}).get("ridge") or {}
        if not ridge:
            continue
        labels.append(key.replace("y_", ""))
        ics.append(ridge.get("ic_test", np.nan))
        boot = ridge.get("ic_boot") or {}
        los.append(boot.get("lo", np.nan))
        his.append(boot.get("hi", np.nan))
    if labels:
        x = np.arange(len(labels))
        ax.bar(x, ics, color="#3d5a5b", alpha=0.85)
        ax.errorbar(
            x,
            ics,
            yerr=[
                np.maximum(0, np.asarray(ics) - np.asarray(los)),
                np.maximum(0, np.asarray(his) - np.asarray(ics)),
            ],
            fmt="none",
            ecolor="black",
            capsize=3,
        )
        ax.axhline(0, color="gray", lw=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=30, ha="right")
        ax.set_ylabel("OOS Spearman IC (Ridge)")
        ax.set_title("Feature-reg IC by target / clock")
        fig.tight_layout()
        fig.savefig(FIG / "ic_by_horizon.png", dpi=140)
    plt.close(fig)

    # ridge alpha path for primary
    prim = (results.get("by_target") or {}).get(PRIMARY_TARGET) or {}
    path = ((prim.get("cv") or {}).get("path")) or []
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    if path:
        alphas = [p["alpha"] for p in path]
        icm = [p["ic_mean"] for p in path]
        ax.semilogx(alphas, icm, marker="o", color="#8b3a3a")
        ax.axvline(prim.get("alpha", 1.0), color="gray", ls="--", label="chosen α")
        ax.set_xlabel("Ridge α")
        ax.set_ylabel("Time-blocked CV IC")
        ax.set_title(f"Ridge path — {PRIMARY_TARGET}")
        ax.legend()
    fig.tight_layout()
    fig.savefig(FIG / "ridge_path.png", dpi=140)
    plt.close(fig)

    # OOS scatter primary
    oos = prim.get("oos_pred") or {}
    fig, ax = plt.subplots(figsize=(5.5, 5.2))
    if oos.get("y"):
        y = np.asarray(oos["y"], dtype=float)
        p = np.asarray(oos["pred"], dtype=float)
        ax.scatter(p, y, s=8, alpha=0.35, c="#2f4f4f")
        lim = np.nanpercentile(np.concatenate([y, p]), [2, 98])
        ax.plot(lim, lim, "k--", lw=0.8)
        ax.set_xlabel("Predicted")
        ax.set_ylabel("Realized")
        ax.set_title(
            f"OOS {PRIMARY_TARGET}  R²={prim.get('ridge', {}).get('r2_test', float('nan')):.3f}"
        )
    fig.tight_layout()
    fig.savefig(FIG / "oos_scatter_primary.png", dpi=140)
    plt.close(fig)

    # coef bars primary ridge
    coef = ((prim.get("ridge") or {}).get("coef")) or {}
    fig, ax = plt.subplots(figsize=(8.0, 4.2))
    if coef:
        names = list(coef.keys())
        vals = [coef[n] for n in names]
        order = np.argsort(np.abs(vals))[::-1]
        names = [names[i] for i in order]
        vals = [vals[i] for i in order]
        ax.barh(names, vals, color="#4a6741")
        ax.axvline(0, color="gray", lw=0.8)
        ax.set_xlabel("Standardized Ridge coef")
        ax.set_title(f"Coefs — {PRIMARY_TARGET}")
    fig.tight_layout()
    fig.savefig(FIG / "ridge_coefs_primary.png", dpi=140)
    plt.close(fig)

    _fig_train_test_split(prim, meta)
    _fig_calendar_coefs(results)


def regenerate_figs_from_artifacts() -> list[str]:
    """Rebuild all feature_reg figs from out/ JSON — no warehouse re-fit."""
    summary = json.loads((OUT / "summary.json").read_text())
    prim = json.loads((OUT / "primary_fit.json").read_text())
    meta = json.loads((OUT / "panel_meta.json").read_text()) if (OUT / "panel_meta.json").exists() else {}
    coef_tables = (
        json.loads((OUT / "coef_tables.json").read_text()) if (OUT / "coef_tables.json").exists() else {}
    )
    by_target: dict[str, Any] = {}
    for key, blk in (summary.get("results") or {}).items():
        entry = dict(blk)
        # prefer full primary_fit for primary target
        if key == (summary.get("primary_target") or PRIMARY_TARGET):
            entry = {**entry, **prim}
        ct = coef_tables.get(key) or {}
        if ct.get("ridge") and not ((entry.get("ridge") or {}).get("coef")):
            ridge = dict(entry.get("ridge") or {})
            ridge["coef"] = ct["ridge"]
            entry["ridge"] = ridge
            entry.setdefault("coef", ct["ridge"])
        by_target[key] = entry
    results = {"by_target": by_target}
    make_figures(results, meta=meta)
    written = sorted(p.name for p in FIG.glob("*.png"))
    return written


def gate_decisions(results: dict) -> dict:
    """Explicit Promote / Hold / Kill for feature-reg candidates."""
    prim = (results.get("by_target") or {}).get(PRIMARY_TARGET) or {}
    leak = results.get("leakage_check") or {}
    logi = results.get("logistic_breach_sign") or {}
    ridge = prim.get("ridge") or {}
    candidates = []

    # info.v_feature_ridge_tick — primary
    ok = bool(prim.get("promote_ok"))
    candidates.append(
        {
            "id": "info.v_feature_ridge_tick",
            "type": "D",
            "lenses": "info, cont, exec",
            "decision": "Promote" if ok else "Hold",
            "evidence": (
                f"target={PRIMARY_TARGET} clock={PRIMARY_CLOCK}; "
                f"R²_te={ridge.get('r2_test')} IC={ridge.get('ic_test')} "
                f"boot={ridge.get('ic_boot')} early/late OOS IC={ridge.get('ic_early_oos')}/"
                f"{ridge.get('ic_late_oos')} sign_stable={ridge.get('sign_stable')} n={prim.get('n')}"
            ),
            "tradable": bool(ok),
            "monitor": True,
        }
    )

    # calendar targets — monitor if any clear, else Hold
    cal_ok = False
    cal_notes = []
    for key in ("y_cal_30s", "y_cal_60s", "y_cal_300s"):
        blk = (results.get("by_target") or {}).get(key) or {}
        rg = blk.get("ridge") or {}
        cal_notes.append(
            f"{key}: R²={rg.get('r2_test')} IC={rg.get('ic_test')} ok={blk.get('promote_ok')}"
        )
        cal_ok = cal_ok or bool(blk.get("promote_ok"))
    candidates.append(
        {
            "id": "info.v_feature_ridge_calendar",
            "type": "D",
            "lenses": "info, cont",
            "decision": "Promote" if cal_ok else "Hold",
            "evidence": "; ".join(cal_notes),
            "tradable": False,
            "monitor": True,
        }
    )

    vol = (results.get("by_target") or {}).get("y_vol") or {}
    candidates.append(
        {
            "id": "info.v_feature_ridge_volume_clock",
            "type": "D",
            "lenses": "info, cont",
            "decision": "Promote" if vol.get("promote_ok") else "Hold",
            "evidence": (
                f"R²_te={(vol.get('ridge') or {}).get('r2_test')} "
                f"IC={(vol.get('ridge') or {}).get('ic_test')} n={vol.get('n')}"
            ),
            "tradable": False,
            "monitor": True,
        }
    )

    # leakage: if leak IC much stronger → Kill using V_now/Tp as features for live
    leak_ic = ((leak.get("ridge") or {}).get("ic_test"))
    caus_ic = ridge.get("ic_test")
    leak_kill = bool(
        np.isfinite(leak_ic)
        and np.isfinite(caus_ic)
        and abs(leak_ic) > abs(caus_ic) + 0.05
        and (leak.get("promote_ok") or abs(leak_ic) >= 0.08)
    )
    candidates.append(
        {
            "id": "info.v_feature_leakage_V_Tp",
            "type": "D",
            "lenses": "info",
            "decision": "Kill" if leak_kill or True else "Hold",  # always Kill as live feature set
            "evidence": (
                f"leakage design (V_now+Tp+causal) IC={leak_ic} vs causal IC={caus_ic}; "
                "right-kernel T+/contemporaneous V banned at decision time — Kill as live features"
            ),
            "tradable": False,
            "monitor": False,
            "note": "Always Kill for live use; diagnostic only",
        }
    )
    # Force Kill for leakage candidate (desk rule)
    candidates[-1]["decision"] = "Kill"

    candidates.append(
        {
            "id": "info.breach_sign_logistic",
            "type": "D",
            "lenses": "info, exec",
            "decision": "Promote" if logi.get("promote_ok") else "Hold",
            "evidence": (
                f"AUC_te={logi.get('auc_test')} base={logi.get('base_rate_test')} "
                f"n={logi.get('n')} coef_breach={(logi.get('coef') or {}).get('breach')}"
            ),
            "tradable": False,
            "monitor": True,
        }
    )

    # paper / monitor ideas from gates
    trade_ideas = []
    cal = next((c for c in candidates if c["id"] == "info.v_feature_ridge_calendar"), None)
    if cal and cal["decision"] == "Promote":
        trade_ideas.append(
            {
                "id": "ti.v_feature_cal_monitor",
                "label": "Monitor",
                "title": "Causal V-feature Ridge score on calendar clock (info monitor)",
                "depends_on": ["info.v_feature_ridge_calendar"],
                "gate_status": {"info.v_feature_ridge_calendar": "Promote"},
                "tradable_size": "N/A — Monitor only; R²≪1, not sized alpha",
                "falsifier": cal["evidence"],
            }
        )
    if ok:
        trade_ideas.append(
            {
                "id": "ti.v_feature_ridge_paper_alpha",
                "label": "paper-only",
                "title": "Causal V-features → next-N-trade return (Ridge)",
                "depends_on": ["info.v_feature_ridge_tick"],
                "gate_status": {"info.v_feature_ridge_tick": "Promote"},
                "tradable_size": "Paper-only — Promote as info feature; not sized live alpha",
                "falsifier": candidates[0]["evidence"],
            }
        )
    else:
        trade_ideas.append(
            {
                "id": "ti.v_feature_ridge_monitor",
                "label": "Monitor",
                "title": "Ridge V-feature IC monitor on trade clock (primary — failed OOS)",
                "depends_on": ["info.v_feature_ridge_tick"],
                "gate_status": {"info.v_feature_ridge_tick": "Hold"},
                "tradable_size": "N/A — Monitor / paper; do not soft-Promote",
                "falsifier": candidates[0]["evidence"],
            }
        )
    trade_ideas.append(
        {
            "id": "ti.v_feature_throttle_join",
            "label": "Exec throttle",
            "title": "Join causal T− / calendar Ridge score into avoid-chase throttle",
            "depends_on": [
                "info.v_feature_ridge_calendar" if (cal and cal["decision"] == "Promote") else "info.v_feature_ridge_tick",
                "info.v_path_continuous",
            ],
            "gate_status": {
                "info.v_feature_ridge_calendar": (cal or {}).get("decision", "Hold"),
                "info.v_feature_ridge_tick": candidates[0]["decision"],
                "info.v_path_continuous": "Hold",
            },
            "tradable_size": "Paper throttle score — calendar Promote backs monitor join; live POV still paper until v_path clears",
            "falsifier": "Tick primary Hold; calendar IC stable but R² small; v_path continuous still Hold",
        }
    )
    return {"candidates": candidates, "trade_ideas_new": trade_ideas}


def write_reports(results: dict, gates: dict, panel_meta: dict) -> None:
    APP.mkdir(parents=True, exist_ok=True)
    # CANDIDATES
    lines = [
        "| id | type | lenses | decision | evidence |",
        "|----|------|--------|----------|----------|",
    ]
    for c in gates["candidates"]:
        ev = str(c["evidence"]).replace("|", "/")[:220]
        lines.append(
            f"| `{c['id']}` | {c['type']} | {c.get('lenses','')} | **{c['decision']}** | {ev} |"
        )
    (APP / "CANDIDATES.md").write_text("\n".join(lines) + "\n")

    prim = (results.get("by_target") or {}).get(PRIMARY_TARGET) or {}
    ridge = prim.get("ridge") or {}
    report = f"""# Feature regressions — EXP_REPORT

## Sampling honesty
- Price grid: **{DT_S}s** last-print (book legacy; matches `continuous_v` / widen).
- Decision subsample: every **{DECISION_EVERY_S}s**.
- Primary target: **`{PRIMARY_TARGET}`** on **{PRIMARY_CLOCK}** (next-N trade log return from raw tape).
- Secondary: calendar 30s/60s/300s; volume-clock bar.
- Latency: features known at decision print; no exchange-latency model.
- Look-ahead ban: `V_now`, `Tp` (right kernel) = leakage diagnostics only.

## Sample
- n_rows={panel_meta.get('n_rows')} · ETH days={panel_meta.get('n_days_eth')} · BTC days={panel_meta.get('n_days_btc')}
- venues={panel_meta.get('venues')}
- causal feats={CAUSAL_FEATS}

## Primary result (`{PRIMARY_TARGET}`)
- n={prim.get('n')} train/test={prim.get('n_train')}/{prim.get('n_test')} α={prim.get('alpha')}
- Ridge R²_te={ridge.get('r2_test')} IC={ridge.get('ic_test')} boot={ridge.get('ic_boot')}
- early/late OOS IC={ridge.get('ic_early_oos')}/{ridge.get('ic_late_oos')} sign_stable={ridge.get('sign_stable')}
- decision_hint={prim.get('decision_hint')} promote_ok={prim.get('promote_ok')}

## Other clocks
"""
    for k, blk in (results.get("by_target") or {}).items():
        if k == PRIMARY_TARGET:
            continue
        rg = (blk or {}).get("ridge") or {}
        report += (
            f"- `{k}`: R²_te={rg.get('r2_test')} IC={rg.get('ic_test')} "
            f"ok={blk.get('promote_ok')} n={blk.get('n')}\n"
        )
    logi = results.get("logistic_breach_sign") or {}
    report += f"""
## Logistic breach→sign
- AUC_te={logi.get('auc_test')} base={logi.get('base_rate_test')} decision={logi.get('decision_hint')}

## Leakage check (V_now+Tp added)
- {(results.get('leakage_check') or {}).get('ridge')}

## Gate rollup
"""
    for c in gates["candidates"]:
        report += f"- **{c['decision']}** `{c['id']}` — {c['evidence'][:180]}\n"
    report += """
## Artifacts
- `out/feature_reg/summary.json`
- `out/feature_reg/panel_rows.json` / `panel_meta.json`
- `out/feature_reg/coef_tables.json`
- `out/feature_reg/figs/ic_by_horizon.png`, `ridge_path.png`, `oos_scatter_primary.png`, `ridge_coefs_primary.png`, `train_test_split.png`, `ridge_coefs_calendar.png`
"""
    (APP / "EXP_REPORT.md").write_text(report)

    # NOTES already written separately; keep short refresh pointer
    summary = {
        "primary_target": PRIMARY_TARGET,
        "primary_clock": PRIMARY_CLOCK,
        "sampling": panel_meta.get("sampling"),
        "n_rows": panel_meta.get("n_rows"),
        "results": {
            k: {
                "n": v.get("n"),
                "alpha": v.get("alpha"),
                "ridge": {kk: vv for kk, vv in (v.get("ridge") or {}).items() if kk != "coef"},
                "coef": (v.get("ridge") or {}).get("coef"),
                "ols_ic": (v.get("ols") or {}).get("ic_test"),
                "en_ic": (v.get("elasticnet") or {}).get("ic_test"),
                "promote_ok": v.get("promote_ok"),
                "decision_hint": v.get("decision_hint"),
            }
            for k, v in (results.get("by_target") or {}).items()
        },
        "logistic_breach_sign": logi,
        "leakage_check": {
            "ridge_ic": ((results.get("leakage_check") or {}).get("ridge") or {}).get("ic_test"),
            "ridge_r2": ((results.get("leakage_check") or {}).get("ridge") or {}).get("r2_test"),
            "promote_ok": (results.get("leakage_check") or {}).get("promote_ok"),
        },
        "gates": gates,
    }
    # strip heavy oos from disk summary — already in by_target files if needed
    (OUT / "summary.json").write_text(json.dumps(_jsonable(summary), indent=2))
    coef_tables = {
        k: {
            "ridge": (v.get("ridge") or {}).get("coef"),
            "ols": (v.get("ols") or {}).get("coef"),
            "elasticnet": (v.get("elasticnet") or {}).get("coef"),
        }
        for k, v in (results.get("by_target") or {}).items()
    }
    coef_tables["logistic_breach_sign"] = logi.get("coef")
    (OUT / "coef_tables.json").write_text(json.dumps(_jsonable(coef_tables), indent=2))
    (OUT / "gates.json").write_text(json.dumps(_jsonable(gates), indent=2))


def run(*, max_files: int, fast: bool, include_btc: bool) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    print("== build panel ==", flush=True)
    panel = build_panel(max_files=max_files, fast=fast, include_btc=include_btc)
    rows = panel["rows"]
    meta = json.loads((OUT / "panel_meta.json").read_text())
    print(f"panel n_rows={len(rows)}", flush=True)

    targets = [
        PRIMARY_TARGET,
        "y_tick_10",
        "y_tick_50",
        "y_cal_30s",
        "y_cal_60s",
        "y_cal_300s",
        "y_vol",
    ]
    by_target: dict[str, dict] = {}
    for tgt in targets:
        print(f"== fit ridge suite {tgt} ==", flush=True)
        by_target[tgt] = fit_ridge_suite(rows, target=tgt, feats=CAUSAL_FEATS, tag="causal")
        # drop heavy oos for non-primary to keep summary lighter — keep for primary figs
        if tgt != PRIMARY_TARGET and "oos_pred" in by_target[tgt]:
            # keep small sample for optional plots
            oos = by_target[tgt]["oos_pred"]
            if oos and len(oos.get("y") or []) > 400:
                by_target[tgt]["oos_pred"] = {
                    "y": oos["y"][:400],
                    "pred": oos["pred"][:400],
                    "days": oos["days"][:400],
                }

    print("== leakage check ==", flush=True)
    leak = fit_ridge_suite(
        rows, target=PRIMARY_TARGET, feats=CAUSAL_FEATS + LEAK_FEATS, tag="leakage"
    )
    if "oos_pred" in leak:
        del leak["oos_pred"]

    print("== logistic ==", flush=True)
    logi = fit_logistic_breach_sign(rows)

    results = {"by_target": by_target, "leakage_check": leak, "logistic_breach_sign": logi}
    # persist full primary oos for notebook
    (OUT / "primary_fit.json").write_text(
        json.dumps(_jsonable(by_target.get(PRIMARY_TARGET, {})), indent=2)
    )
    make_figures(results, meta=meta)
    gates = gate_decisions(results)
    write_reports(results, gates, meta)
    print("== done ==", flush=True)
    print(json.dumps(_jsonable({"n_rows": len(rows), "gates": gates["candidates"]}), indent=2))
    return {"panel": meta, "results": results, "gates": gates}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-files", type=int, default=24)
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--no-btc", action="store_true")
    ap.add_argument(
        "--figs-only",
        action="store_true",
        help="Regenerate figs from out/feature_reg JSON artifacts (no re-fit).",
    )
    args = ap.parse_args()
    if args.figs_only:
        written = regenerate_figs_from_artifacts()
        print("figs regenerated:", written, flush=True)
        return
    run(max_files=args.max_files, fast=args.fast, include_btc=not args.no_btc)


if __name__ == "__main__":
    main()
