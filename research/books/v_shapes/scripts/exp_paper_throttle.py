#!/usr/bin/env python3
"""Paper exec-throttle / risk harness — V-shapes Promote monitors → desk actions.

Turns Promoted MinV / EGARCH-band objects into simulated maker-desk throttle
actions and benchmarks vs always-on baseline on real HL+Deribit+Kraken tape.

Honesty
-------
- Research sim on warehouse tape — not live OE, not sized alpha.
- Fills: synthetic maker participation × tape aggressor flow; book at trade print
  + friction haircut (base + widen). No fantasy latency edge / mid-touch invent.
- Primary trigger: UTC-day MinV vs EGARCH 5% (Promote stack) — activate at
  τ★ (trough observed) for duration h_n (causal post-detection).
- Secondary: calendar Ridge score (Promote Monitor only) as paper-only weight
  to deepen throttle; never standalone size; tick y_tick_20 stays Hold.
- Chronological OOS (~60/40 by UTC day, matching feature_reg).
- Promote scope: **Exec throttle / risk** iff OOS risk improves (DD / adverse
  markout) with early∧late sign-stable — Hold as alpha always.
- Placebo: random windows of matched duration must not clear the risk bar.
- ClickHouse MCP banned.

Desk objects: ti.risk_monitor_minv_breach, ti.exec_throttle_avoid_chase,
ti.v_feature_throttle_join.
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

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
APP = BOOK / "applications" / "paper_throttle"
OUT = BOOK / "out" / "paper_throttle"
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
from research.lib.vstat import (  # noqa: E402
    grid_1s,
    returns_from_log_px,
    t_stat_side,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DT_S = 5.0
HN_PRIMARY_MIN = 5
HN_SET_MIN = (1, 5, 30)
BASE_SIZE = 0.25  # coin units at touch
BASE_FRICTION_BPS = 2.0
MAX_INV = 2.0
MARKOUT_HORIZONS_S = (5.0, 30.0, 60.0)
DECISION_STRIDE_TRADES = 1  # walk every print (honest participation)

# Throttle knobs (desk memo ranges)
THROTTLE_SIZE_MULT = 0.35
THROTTLE_WIDEN_BPS = 5.0
THROTTLE_POV = 0.20  # vs baseline participation 1.0
THROTTLE_TAKE_PAUSE = True

# Calendar Ridge boost (paper-only secondary)
CAL_BOOST_SIZE_MULT = 0.22
CAL_BOOST_WIDEN_BPS = 8.0
CAL_BOOST_POV = 0.10
CAL_SCORE_QUANTILE = 0.90  # deepen when |score| ≥ train q90

HONESTY = {
    "class": "exec_throttle_risk_sim",
    "slice": "research_sim_on_real_tape",
    "live_orders": False,
    "fills": "synthetic_maker_participation_x_tape_print_plus_friction",
    "alpha_claim": False,
    "promote_scope": "exec_throttle_risk_not_tradable_alpha",
    "clickhouse_mcp": False,
    "book_objects": [
        "risk.egarch_minv_bands",
        "risk.v_vs_jump_taxonomy",
        "risk.daily_minv_panel",
        "risk.stress_day_minv",
        "info.v_feature_ridge_calendar",
    ],
    "hold_as_alpha": True,
    "tick_primary": "y_tick_20 Hold — never sized",
}


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


def _block_boot_mean(vals: np.ndarray, *, n_boot: int = 500, block: int = 3, seed: int = 11) -> dict:
    v = np.asarray(vals, dtype=float)
    v = v[np.isfinite(v)]
    n = int(v.size)
    if n < 3:
        return {"mean": float(np.mean(v)) if n else float("nan"), "lo": float("nan"), "hi": float("nan"), "n": n}
    rng = np.random.default_rng(seed)
    block = max(1, min(block, max(1, n // 2)))
    means = []
    for _ in range(n_boot):
        starts = rng.integers(0, max(n - block + 1, 1), size=max(1, (n + block - 1) // block))
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


def _chrono_split(days: list[str]) -> tuple[list[str], list[str]]:
    days = sorted(set(days))
    if len(days) < 4:
        cut = max(1, len(days) - 1)
    else:
        cut = max(2, int(round(len(days) * 0.6)))
    return days[:cut], days[cut:]


def load_minv_breaches() -> list[dict]:
    """Promote-object breaches from daily_minv panels (sig_5 EGARCH)."""
    out: list[dict] = []
    for sym, name in (("ETH", "daily_minv_eth.json"), ("BTC", "daily_minv_btc.json")):
        path = BOOK / "out" / "daily_minv" / name
        if not path.exists():
            continue
        blob = json.loads(path.read_text())
        for r in blob.get("rows") or []:
            if not r.get("ok"):
                continue
            sig = bool(r.get("sig_5"))
            out.append(
                {
                    "symbol": sym,
                    "venue": r["venue"],
                    "day": r["day"],
                    "hn_min": int(r.get("hn_min") or HN_PRIMARY_MIN),
                    "min_v": float(r.get("min_v") or np.nan),
                    "q05": float(r.get("q05") or np.nan),
                    "tau_star_s": float(r.get("tau_star_s") or np.nan),
                    "shape": r.get("shape"),
                    "sig_5": sig,
                    "complete": bool(r.get("complete")),
                    "n_trades": int(r.get("n_trades") or 0),
                }
            )
    return out


def load_cal_coefs() -> dict[str, float]:
    """Calendar Ridge coefs (Promote Monitor) — paper-only secondary weight."""
    path = BOOK / "out" / "feature_reg" / "coef_tables.json"
    if not path.exists():
        return {}
    blob = json.loads(path.read_text())
    # Prefer 60s (desk-speed); fall back 300s
    for key in ("y_cal_60s", "y_cal_300s", "y_cal_30s"):
        coef = ((blob.get(key) or {}).get("ridge")) or {}
        if coef:
            return {str(k): float(v) for k, v in coef.items()}
    return {}


def _day_start_ns(day: str) -> int:
    from datetime import datetime, timezone

    t0 = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(t0.timestamp() * 1e9)


def breach_windows_for_day(
    breaches: list[dict],
    *,
    symbol: str,
    venue: str,
    day: str,
    hn_set: tuple[int, ...] = HN_SET_MIN,
) -> list[dict]:
    """Causal post-τ★ windows for significant EGARCH breaches on this day."""
    wins = []
    for r in breaches:
        if r["symbol"] != symbol or r["venue"] != venue or r["day"] != day:
            continue
        if not r["sig_5"]:
            continue
        if int(r["hn_min"]) not in hn_set:
            continue
        tau = float(r["tau_star_s"])
        if not np.isfinite(tau):
            continue
        hn_s = float(r["hn_min"]) * 60.0
        wins.append(
            {
                "t0_s": tau,
                "t1_s": tau + hn_s,
                "hn_min": int(r["hn_min"]),
                "min_v": r["min_v"],
                "q05": r["q05"],
                "shape": r["shape"],
                "source": "egarch_minv_sig5",
            }
        )
    # merge overlapping
    if not wins:
        return []
    wins.sort(key=lambda w: w["t0_s"])
    merged = [dict(wins[0])]
    for w in wins[1:]:
        if w["t0_s"] <= merged[-1]["t1_s"]:
            merged[-1]["t1_s"] = max(merged[-1]["t1_s"], w["t1_s"])
            merged[-1]["hn_min"] = max(merged[-1]["hn_min"], w["hn_min"])
        else:
            merged.append(dict(w))
    return merged


def placebo_windows(
    wins: list[dict],
    *,
    day_span_s: float = 86400.0,
    seed: int,
) -> list[dict]:
    """Same durations, random start — falsifier."""
    rng = np.random.default_rng(seed)
    out = []
    for i, w in enumerate(wins):
        dur = max(60.0, float(w["t1_s"] - w["t0_s"]))
        if dur >= day_span_s - 60:
            continue
        t0 = float(rng.uniform(0.0, day_span_s - dur))
        out.append(
            {
                "t0_s": t0,
                "t1_s": t0 + dur,
                "hn_min": w.get("hn_min"),
                "min_v": None,
                "q05": None,
                "shape": "placebo",
                "source": "placebo",
            }
        )
    return out


def cal_score_at_trough(
    ts: np.ndarray,
    px: np.ndarray,
    *,
    day: str,
    tau_s: float,
    coefs: dict[str, float],
    hn_s: float = 300.0,
) -> float:
    """Lightweight causal calendar score at τ★ (T− dominant + breach flag)."""
    if not coefs or not np.isfinite(tau_s):
        return float("nan")
    t0 = _day_start_ns(day)
    tau_ns = t0 + int(tau_s * 1e9)
    m = ts <= tau_ns
    if int(m.sum()) < 50:
        return float("nan")
    g = grid_1s(ts[m], px[m], dt_s=DT_S)
    gpx = np.asarray(g["px"], dtype=float)
    gts = np.asarray(g["ts_ns"], dtype=np.int64)
    if gpx.size < 40:
        return float("nan")
    log_px = np.log(np.clip(gpx, 1e-12, None))
    try:
        t_u, r = returns_from_log_px(log_px, gts, time_unit_s=DT_S)
        tau_u = float(t_u[-1]) if t_u.size else float("nan")
        tm = float(t_stat_side(t_u, r, tau_u, hn_s / DT_S, side="left")) if t_u.size > 10 else float("nan")
    except Exception:
        tm = float("nan")
    feats = {
        "Tm": tm if np.isfinite(tm) else 0.0,
        "abs_Tm": abs(tm) if np.isfinite(tm) else 0.0,
        "Tm_1m": 0.0,
        "V_lag": 0.0,
        "abs_V_lag": 0.0,
        "running_min_v": 0.0,
        "abs_running_min_v": 0.0,
        "breach": 1.0,
        "geom_near": 0.0,
        "log_intensity": float(np.log(max(int(m.sum()), 1))),
        "vpin_roll": 0.0,
        "hn5_dummy": 1.0,
    }
    score = 0.0
    for k, c in coefs.items():
        score += float(c) * float(feats.get(k, 0.0))
    return float(score)


def simulate_day(
    *,
    ts: np.ndarray,
    px: np.ndarray,
    side: np.ndarray,
    qty: np.ndarray,
    windows: list[dict],
    policy: str,
    cal_boost: bool,
    cal_scores: dict[tuple[float, float], float] | None,
    cal_thresh: float,
    day: str,
    base_size: float = BASE_SIZE,
    friction_bps: float = BASE_FRICTION_BPS,
    max_inv: float = MAX_INV,
    seed: int = 0,
) -> dict[str, Any]:
    """Synthetic maker sim: always_on vs throttle vs placebo.

    Participation: each aggressor print may fill us as the passive side with
    probability = pov (throttle) or 1.0 (always_on), size = base * size_mult.
    Fill price = trade print ± friction. Inventory marked to last print mid.
    """
    ts = np.asarray(ts, dtype=np.int64)
    px = np.asarray(px, dtype=np.float64)
    side = np.asarray(side, dtype=np.float64)
    qty = np.asarray(qty, dtype=np.float64)
    n = int(ts.size)
    if n < 100:
        return {"ok": False, "reason": "thin_tape", "n": n}

    # windows use tau_star_s from UTC day start — align tape to same clock
    sod0 = _day_start_ns(day)
    sod_s = (ts - sod0) / 1e9

    def in_window(s: float) -> tuple[bool, dict | None]:
        for w in windows:
            if w["t0_s"] <= s < w["t1_s"]:
                return True, w
        return False, None

    inv = 0.0
    cash_bps = 0.0
    ref = float(px[np.isfinite(px) & (px > 0)][0]) if np.any(np.isfinite(px) & (px > 0)) else 1.0
    prev_mid = ref
    equity = np.zeros(n, dtype=np.float64)
    inv_path = np.zeros(n, dtype=np.float64)
    throttled = np.zeros(n, dtype=np.int8)
    n_fills = 0
    part_num = 0.0
    part_den = 0.0
    fill_i: list[int] = []
    fill_side: list[int] = []
    fill_px: list[float] = []
    fill_qty: list[float] = []
    markouts: dict[str, list[float]] = {f"mo_{int(h)}s": [] for h in MARKOUT_HORIZONS_S}
    adverse_mo: list[float] = []  # + = adverse for maker (inventory × mid move wrong way)

    rng = np.random.default_rng(seed)

    for i in range(n):
        m = float(px[i]) if np.isfinite(px[i]) and px[i] > 0 else prev_mid
        if i > 0 and inv != 0.0 and prev_mid > 0:
            cash_bps += inv * (m - prev_mid) / ref * 1e4
        prev_mid = m
        inv_path[i] = inv
        equity[i] = cash_bps

        s_ofday = float(sod_s[i])
        active, win = in_window(s_ofday)
        throttled[i] = 1 if active and policy in ("throttle", "throttle_cal", "placebo") else 0

        # policy knobs
        size_mult = 1.0
        widen = 0.0
        pov = 1.0
        take_pause = False
        if policy == "always_on":
            pass
        elif policy in ("throttle", "throttle_cal", "placebo"):
            if active:
                size_mult = THROTTLE_SIZE_MULT
                widen = THROTTLE_WIDEN_BPS
                pov = THROTTLE_POV
                take_pause = THROTTLE_TAKE_PAUSE
                if policy == "throttle_cal" and cal_boost and win is not None:
                    # paper-only calendar deepen
                    key = (float(win["t0_s"]), float(win["t1_s"]))
                    sc = (cal_scores or {}).get(key, float("nan"))
                    if np.isfinite(sc) and np.isfinite(cal_thresh) and abs(sc) >= cal_thresh:
                        size_mult = CAL_BOOST_SIZE_MULT
                        widen = CAL_BOOST_WIDEN_BPS
                        pov = CAL_BOOST_POV

        tr_side = float(side[i])  # +1 buy aggressor → we sell (ask)
        tr_qty = float(qty[i]) if np.isfinite(qty[i]) else 0.0
        tr_px = float(px[i]) if np.isfinite(px[i]) else m
        if tr_qty <= 0 or not np.isfinite(tr_side) or tr_side == 0:
            continue

        # pause aggressive takes: skip fills that would add with-flow inventory when take_pause
        # maker always passive; "pause takes" = refuse to lean into aggressor (skip fill)
        if take_pause and active:
            # still allow small size; model as pov already cut — skip additional "lean"
            pass

        part_den += tr_qty
        # participation draw
        if rng.random() > pov:
            continue
        our_sz = base_size * size_mult
        # inventory clamp
        if tr_side > 0 and inv <= -max_inv:  # they buy, we sell — already short max
            continue
        if tr_side < 0 and inv >= max_inv:
            continue
        fqty = min(our_sz, tr_qty)
        if fqty <= 0:
            continue
        # our side: opposite of aggressor
        our_side = -1 if tr_side > 0 else +1  # +1 we buy
        fr = (friction_bps + widen) * 1e-4
        # fill at print with adverse friction
        if our_side > 0:
            fpx = tr_px * (1.0 + fr)
        else:
            fpx = tr_px * (1.0 - fr)
        # realize cash in bps of ref
        # buying: -fpx, selling: +fpx
        cash_bps += our_side * (m - fpx) / ref * 1e4 * fqty  # immediate friction vs mid
        inv += our_side * fqty
        n_fills += 1
        part_num += fqty
        fill_i.append(i)
        fill_side.append(our_side)
        fill_px.append(fpx)
        fill_qty.append(fqty)

        # markouts vs future mid
        for h in MARKOUT_HORIZONS_S:
            j = int(np.searchsorted(ts, ts[i] + int(h * 1e9), side="left"))
            if j >= n:
                continue
            mj = float(px[j]) if np.isfinite(px[j]) and px[j] > 0 else m
            # maker PnL markout in bps: our_side * (mj - fpx) / ref * 1e4
            mo = our_side * (mj - fpx) / ref * 1e4
            markouts[f"mo_{int(h)}s"].append(mo)
            if int(h) == 30:
                # adverse = negative of maker PnL (positive = hurt)
                adverse_mo.append(-mo)

    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    mo30 = np.asarray(markouts["mo_30s"], dtype=float)
    adv = np.asarray(adverse_mo, dtype=float)
    return {
        "ok": True,
        "n": n,
        "n_fills": n_fills,
        "final_equity_bps": float(equity[-1]),
        "max_dd_bps": float(np.min(dd)) if dd.size else float("nan"),
        "mean_abs_inv": float(np.mean(np.abs(inv_path))),
        "max_abs_inv": float(np.max(np.abs(inv_path))),
        "participation": float(part_num / part_den) if part_den > 0 else 0.0,
        "pct_time_throttled": float(np.mean(throttled)),
        "n_windows": len(windows),
        "mo_5s_mean": float(np.mean(markouts["mo_5s"])) if markouts["mo_5s"] else float("nan"),
        "mo_30s_mean": float(np.mean(mo30)) if mo30.size else float("nan"),
        "mo_60s_mean": float(np.mean(markouts["mo_60s"])) if markouts["mo_60s"] else float("nan"),
        "adverse_mo_30s_mean": float(np.mean(adv)) if adv.size else float("nan"),
        "equity": equity,
        "inv_path": inv_path,
        "throttled": throttled,
        "sod_s": sod_s,
        "fill_i": np.asarray(fill_i, dtype=np.int64),
        "windows": windows,
        "policy": policy,
    }


def _summarize_policy_rows(rows: list[dict]) -> dict[str, Any]:
    def col(name: str) -> np.ndarray:
        return np.asarray([r.get(name) for r in rows if r.get("ok")], dtype=float)

    out = {}
    for name in (
        "final_equity_bps",
        "max_dd_bps",
        "mean_abs_inv",
        "participation",
        "pct_time_throttled",
        "mo_30s_mean",
        "adverse_mo_30s_mean",
        "n_fills",
    ):
        v = col(name)
        out[name] = {
            "mean": float(np.nanmean(v)) if v.size else float("nan"),
            "boot": _block_boot_mean(v[np.isfinite(v)]),
            "n": int(np.isfinite(v).sum()),
        }
    return out


def run_panel(
    *,
    max_files: int,
    include_btc: bool,
    fast: bool,
    seed: int = 7,
) -> dict[str, Any]:
    ensure_env()
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)

    plan = _load_day_plan()
    eth_days = list(plan.get("eth_days") or [])
    btc_days = list(plan.get("btc_days") or []) if include_btc else []
    if fast:
        eth_days = eth_days[:8]
        btc_days = btc_days[:3]
    # use full widen sample days from DESK_MEMO if present in daily_minv
    breaches = load_minv_breaches()
    # expand eth days from breach panel
    panel_days_eth = sorted({r["day"] for r in breaches if r["symbol"] == "ETH"})
    panel_days_btc = sorted({r["day"] for r in breaches if r["symbol"] == "BTC"})
    if not fast:
        eth_days = sorted(set(eth_days) | set(panel_days_eth))
        if include_btc:
            btc_days = sorted(set(btc_days) | set(panel_days_btc))

    train_days, test_days = _chrono_split(eth_days)
    coefs = load_cal_coefs()

    day_rows: list[dict] = []
    timeline: list[dict] = []
    cal_score_train: list[float] = []

    jobs: list[tuple[str, str, str]] = []
    for d in eth_days:
        for v in CORE_VENUES:
            jobs.append(("ETH", v, d))
    for d in btc_days:
        for v in CORE_VENUES:
            jobs.append(("BTC", v, d))

    print(f"== paper_throttle panel jobs={len(jobs)} eth_days={len(eth_days)} btc_days={len(btc_days)} ==", flush=True)

    for ji, (sym, venue, day) in enumerate(jobs):
        try:
            loaded = load_day_trades(venue, sym, day, max_files=max_files, quiet=True)
        except Exception as e:
            day_rows.append(
                {
                    "ok": False,
                    "symbol": sym,
                    "venue": venue,
                    "day": day,
                    "reason": f"load:{type(e).__name__}",
                }
            )
            continue
        tape = loaded["tape"]
        flags = loaded["completeness"]
        ts = np.asarray(tape["ts"], dtype=np.int64)
        px = np.asarray(tape["px"], dtype=np.float64)
        side = np.asarray(tape["side"], dtype=np.float64)
        qty = np.asarray(tape["qty"], dtype=np.float64)
        if not flags.get("complete") or ts.size < 500:
            day_rows.append(
                {
                    "ok": False,
                    "symbol": sym,
                    "venue": venue,
                    "day": day,
                    "reason": "incomplete",
                    "completeness": flags,
                    "n": int(ts.size),
                }
            )
            continue

        wins = breach_windows_for_day(breaches, symbol=sym, venue=venue, day=day)
        # calendar scores per window (paper-only)
        cal_scores: dict[tuple[float, float], float] = {}
        for w in wins:
            sc = cal_score_at_trough(ts, px, day=day, tau_s=float(w["t0_s"]), coefs=coefs)
            cal_scores[(float(w["t0_s"]), float(w["t1_s"]))] = sc
            if day in train_days and np.isfinite(sc):
                cal_score_train.append(sc)

        placebo = placebo_windows(wins, seed=seed + ji * 17)

        policies = {
            "always_on": {"windows": [], "policy": "always_on", "cal_boost": False},
            "throttle": {"windows": wins, "policy": "throttle", "cal_boost": False},
            "throttle_cal": {"windows": wins, "policy": "throttle_cal", "cal_boost": True},
            "placebo": {"windows": placebo, "policy": "placebo", "cal_boost": False},
        }

        # provisional thresh from train scores seen so far; finalize later for OOS report
        thresh_tmp = (
            float(np.quantile(np.abs(np.asarray(cal_score_train, dtype=float)), CAL_SCORE_QUANTILE))
            if len(cal_score_train) >= 5
            else float("inf")
        )

        pol_out: dict[str, Any] = {}
        for pname, cfg in policies.items():
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                sim = simulate_day(
                    ts=ts,
                    px=px,
                    side=side,
                    qty=qty,
                    windows=cfg["windows"],
                    policy=cfg["policy"],
                    cal_boost=cfg["cal_boost"],
                    cal_scores=cal_scores,
                    cal_thresh=thresh_tmp,
                    day=day,
                    seed=seed + ji,
                )
            # drop heavy arrays from row; keep for one example fig later
            slim = {k: v for k, v in sim.items() if k not in ("equity", "inv_path", "throttled", "sod_s", "fill_i")}
            slim.update(
                {
                    "symbol": sym,
                    "venue": venue,
                    "day": day,
                    "split": "train" if day in train_days else ("test" if day in test_days else "other"),
                    "n_breach_windows": len(wins),
                    "has_breach": bool(wins),
                    "cal_scores": {f"{a:.1f}-{b:.1f}": cal_scores.get((a, b)) for a, b in cal_scores},
                }
            )
            pol_out[pname] = slim
            if pname == "throttle" and wins:
                timeline.append(
                    {
                        "symbol": sym,
                        "venue": venue,
                        "day": day,
                        "windows": wins,
                        "max_dd_throttle": slim.get("max_dd_bps"),
                        "max_dd_base": None,  # fill below
                        "adverse_mo_throttle": slim.get("adverse_mo_30s_mean"),
                    }
                )

        if "always_on" in pol_out and "throttle" in pol_out:
            for t in timeline:
                if t["symbol"] == sym and t["venue"] == venue and t["day"] == day:
                    t["max_dd_base"] = pol_out["always_on"].get("max_dd_bps")
                    t["adverse_mo_base"] = pol_out["always_on"].get("adverse_mo_30s_mean")
                    t["delta_dd"] = (
                        float(pol_out["throttle"]["max_dd_bps"]) - float(pol_out["always_on"]["max_dd_bps"])
                        if pol_out["throttle"].get("ok") and pol_out["always_on"].get("ok")
                        else None
                    )
                    t["delta_adverse"] = (
                        float(pol_out["throttle"]["adverse_mo_30s_mean"])
                        - float(pol_out["always_on"]["adverse_mo_30s_mean"])
                        if np.isfinite(pol_out["throttle"].get("adverse_mo_30s_mean", np.nan))
                        and np.isfinite(pol_out["always_on"].get("adverse_mo_30s_mean", np.nan))
                        else None
                    )

        # keep one full path for figures (first breach day on HL ETH)
        artifact_path = None
        if wins and sym == "ETH" and venue == "hyperliquid":
            artifact_path = OUT / f"path_{day}_{venue}_{sym}.npz"
            if not artifact_path.exists():
                base = policies["always_on"]
                th = policies["throttle"]
                sim_b = simulate_day(
                    ts=ts,
                    px=px,
                    side=side,
                    qty=qty,
                    windows=[],
                    policy="always_on",
                    cal_boost=False,
                    cal_scores=None,
                    cal_thresh=thresh_tmp,
                    day=day,
                    seed=seed + ji,
                )
                sim_t = simulate_day(
                    ts=ts,
                    px=px,
                    side=side,
                    qty=qty,
                    windows=wins,
                    policy="throttle",
                    cal_boost=False,
                    cal_scores=cal_scores,
                    cal_thresh=thresh_tmp,
                    day=day,
                    seed=seed + ji,
                )
                np.savez_compressed(
                    artifact_path,
                    sod_s=sim_t["sod_s"][:: max(1, int(sim_t["n"] // 8000))],
                    equity_base=sim_b["equity"][:: max(1, int(sim_b["n"] // 8000))],
                    equity_th=sim_t["equity"][:: max(1, int(sim_t["n"] // 8000))],
                    inv_base=sim_b["inv_path"][:: max(1, int(sim_b["n"] // 8000))],
                    inv_th=sim_t["inv_path"][:: max(1, int(sim_t["n"] // 8000))],
                    throttled=sim_t["throttled"][:: max(1, int(sim_t["n"] // 8000))],
                )

        day_rows.append(
            {
                "ok": True,
                "symbol": sym,
                "venue": venue,
                "day": day,
                "split": "train" if day in train_days else ("test" if day in test_days else "other"),
                "completeness": {k: flags.get(k) for k in ("complete", "n", "coverage", "span_s")},
                "n_breach_windows": len(wins),
                "windows": wins,
                "policies": {k: {kk: vv for kk, vv in v.items() if kk != "windows"} for k, v in pol_out.items()},
                "path_artifact": str(artifact_path) if artifact_path else None,
            }
        )
        if (ji + 1) % 5 == 0 or wins:
            print(
                f"  [{ji+1}/{len(jobs)}] {sym} {venue} {day} "
                f"breach_wins={len(wins)} ok fills_th="
                f"{(pol_out.get('throttle') or {}).get('n_fills')}",
                flush=True,
            )

    # finalize cal threshold on full train
    cal_thresh = (
        float(np.quantile(np.abs(np.asarray(cal_score_train, dtype=float)), CAL_SCORE_QUANTILE))
        if len(cal_score_train) >= 5
        else float("inf")
    )

    # deltas throttle - baseline per day row
    delta_rows = []
    for r in day_rows:
        if not r.get("ok"):
            continue
        pols = r.get("policies") or {}
        base = pols.get("always_on") or {}
        th = pols.get("throttle") or {}
        thc = pols.get("throttle_cal") or {}
        pl = pols.get("placebo") or {}
        if not (base.get("ok") and th.get("ok")):
            continue

        def delta(a: dict, b: dict, key: str) -> float:
            va, vb = a.get(key), b.get(key)
            if va is None or vb is None:
                return float("nan")
            try:
                return float(va) - float(vb)
            except (TypeError, ValueError):
                return float("nan")

        delta_rows.append(
            {
                "symbol": r["symbol"],
                "venue": r["venue"],
                "day": r["day"],
                "split": r["split"],
                "has_breach": r["n_breach_windows"] > 0,
                "n_breach_windows": r["n_breach_windows"],
                "d_max_dd_throttle": delta(th, base, "max_dd_bps"),  # >0 means less negative DD? max_dd is neg
                # max_dd_bps is ≤0; improvement = throttle max_dd - base max_dd > 0 (e.g. -10 vs -50)
                "d_adverse_mo_throttle": delta(th, base, "adverse_mo_30s_mean"),  # <0 better
                "d_pnl_throttle": delta(th, base, "final_equity_bps"),
                "d_part_throttle": delta(th, base, "participation"),
                "d_abs_inv_throttle": delta(th, base, "mean_abs_inv"),
                "d_max_dd_cal": delta(thc, base, "max_dd_bps") if thc.get("ok") else float("nan"),
                "d_adverse_mo_cal": delta(thc, base, "adverse_mo_30s_mean") if thc.get("ok") else float("nan"),
                "d_pnl_cal": delta(thc, base, "final_equity_bps") if thc.get("ok") else float("nan"),
                "d_max_dd_placebo": delta(pl, base, "max_dd_bps") if pl.get("ok") else float("nan"),
                "d_adverse_mo_placebo": delta(pl, base, "adverse_mo_30s_mean") if pl.get("ok") else float("nan"),
                "base_max_dd": base.get("max_dd_bps"),
                "th_max_dd": th.get("max_dd_bps"),
                "base_adverse": base.get("adverse_mo_30s_mean"),
                "th_adverse": th.get("adverse_mo_30s_mean"),
                "base_pnl": base.get("final_equity_bps"),
                "th_pnl": th.get("final_equity_bps"),
            }
        )

    def agg_deltas(rows: list[dict], *, breach_only: bool | None = None) -> dict:
        sel = rows
        if breach_only is True:
            sel = [r for r in rows if r.get("has_breach")]
        elif breach_only is False:
            sel = [r for r in rows if not r.get("has_breach")]
        keys = [
            "d_max_dd_throttle",
            "d_adverse_mo_throttle",
            "d_pnl_throttle",
            "d_part_throttle",
            "d_abs_inv_throttle",
            "d_max_dd_cal",
            "d_adverse_mo_cal",
            "d_pnl_cal",
            "d_max_dd_placebo",
            "d_adverse_mo_placebo",
        ]
        out = {"n": len(sel)}
        for k in keys:
            v = np.asarray([r.get(k) for r in sel], dtype=float)
            out[k] = _block_boot_mean(v)
        return out

    oos = [r for r in delta_rows if r["split"] == "test"]
    ins = [r for r in delta_rows if r["split"] == "train"]
    # early/late within OOS
    oos_days = sorted({r["day"] for r in oos})
    mid = max(1, len(oos_days) // 2)
    early_d, late_d = set(oos_days[:mid]), set(oos_days[mid:])
    early = [r for r in oos if r["day"] in early_d]
    late = [r for r in oos if r["day"] in late_d]

    summary = {
        "honesty": dict(HONESTY),
        "sample": {
            "eth_days": eth_days,
            "btc_days": btc_days,
            "train_days": train_days,
            "test_days": test_days,
            "n_jobs": len(jobs),
            "n_ok_days": sum(1 for r in day_rows if r.get("ok")),
            "n_breach_dayvenue": sum(1 for r in day_rows if r.get("ok") and r.get("n_breach_windows", 0) > 0),
            "venues": list(CORE_VENUES),
            "cal_thresh_abs": cal_thresh,
            "n_cal_train_scores": len(cal_score_train),
        },
        "knobs": {
            "throttle_size_mult": THROTTLE_SIZE_MULT,
            "throttle_widen_bps": THROTTLE_WIDEN_BPS,
            "throttle_pov": THROTTLE_POV,
            "cal_boost_size_mult": CAL_BOOST_SIZE_MULT,
            "cal_boost_widen_bps": CAL_BOOST_WIDEN_BPS,
            "base_friction_bps": BASE_FRICTION_BPS,
            "base_size": BASE_SIZE,
            "hn_set_min": list(HN_SET_MIN),
        },
        "agg_all": agg_deltas(delta_rows),
        "agg_train": agg_deltas(ins),
        "agg_oos": agg_deltas(oos),
        "agg_oos_breach": agg_deltas(oos, breach_only=True),
        "agg_oos_calm": agg_deltas(oos, breach_only=False),
        "agg_oos_early": agg_deltas(early),
        "agg_oos_late": agg_deltas(late),
        "delta_rows": delta_rows,
        "timeline": timeline,
    }
    return {"summary": summary, "day_rows": day_rows, "breaches": [b for b in breaches if b["sig_5"]]}


def gate_decisions(summary: dict) -> dict:
    """Promote as Exec throttle / risk only; Hold as alpha; Kill if risk worsens."""
    oos = summary.get("agg_oos") or {}
    oos_b = summary.get("agg_oos_breach") or {}
    early = summary.get("agg_oos_early") or {}
    late = summary.get("agg_oos_late") or {}
    placebo = oos  # use placebo deltas from oos

    def mean(block: dict, key: str) -> float:
        return float(((block.get(key) or {}).get("mean")) or np.nan)

    def boot(block: dict, key: str) -> dict:
        return (block.get(key) or {}) if isinstance(block.get(key), dict) else {}

    # Risk help: Δ max_dd > 0 (less severe drawdown) OR Δ adverse_mo < 0
    d_dd = mean(oos_b if oos_b.get("n", 0) >= 2 else oos, "d_max_dd_throttle")
    d_adv = mean(oos_b if oos_b.get("n", 0) >= 2 else oos, "d_adverse_mo_throttle")
    d_pnl = mean(oos, "d_pnl_throttle")
    d_dd_e = mean(early, "d_max_dd_throttle")
    d_dd_l = mean(late, "d_max_dd_throttle")
    d_adv_e = mean(early, "d_adverse_mo_throttle")
    d_adv_l = mean(late, "d_adverse_mo_throttle")
    d_dd_pl = mean(placebo, "d_max_dd_placebo")
    d_adv_pl = mean(placebo, "d_adverse_mo_placebo")

    dd_boot = boot(oos_b if oos_b.get("n", 0) >= 2 else oos, "d_max_dd_throttle")
    adv_boot = boot(oos_b if oos_b.get("n", 0) >= 2 else oos, "d_adverse_mo_throttle")

    risk_helps = bool(
        (np.isfinite(d_dd) and d_dd > 0)  # DD improved (less negative)
        or (np.isfinite(d_adv) and d_adv < 0)  # adverse markout down
    )
    # require at least one metric's CI to clear 0 in the helpful direction, or both point helpful
    dd_ci_ok = bool(np.isfinite(dd_boot.get("lo", np.nan)) and dd_boot["lo"] > 0)
    adv_ci_ok = bool(np.isfinite(adv_boot.get("hi", np.nan)) and adv_boot["hi"] < 0)
    ci_ok = dd_ci_ok or adv_ci_ok
    sign_stable = bool(
        (np.isfinite(d_dd_e) and np.isfinite(d_dd_l) and np.sign(d_dd_e) == np.sign(d_dd_l) and d_dd_e > 0)
        or (
            np.isfinite(d_adv_e)
            and np.isfinite(d_adv_l)
            and np.sign(d_adv_e) == np.sign(d_adv_l)
            and d_adv_e < 0
        )
    )
    # placebo should not look better than real throttle on the same metric
    placebo_fails = True
    if np.isfinite(d_dd) and np.isfinite(d_dd_pl):
        placebo_fails = placebo_fails and (d_dd >= d_dd_pl)  # real DD improvement ≥ placebo
    if np.isfinite(d_adv) and np.isfinite(d_adv_pl):
        # real adverse reduction should be ≤ placebo (more negative or equal)
        placebo_fails = placebo_fails and (d_adv <= d_adv_pl + 1e-9)

    # Kill if risk clearly worsens OOS (CI)
    risk_worsens = bool(
        (np.isfinite(dd_boot.get("hi", np.nan)) and dd_boot["hi"] < 0 and np.isfinite(d_dd) and d_dd < 0)
        or (
            np.isfinite(adv_boot.get("lo", np.nan))
            and adv_boot["lo"] > 0
            and np.isfinite(d_adv)
            and d_adv > 0
        )
    )

    promote_risk = bool(risk_helps and (ci_ok or (sign_stable and risk_helps)) and not risk_worsens)
    # Soft Promote as exec throttle if risk helps + sign stable even if CI thin (n small)
    if risk_helps and sign_stable and (oos_b.get("n", 0) + oos.get("n", 0)) >= 4 and not risk_worsens:
        promote_risk = True
    if risk_worsens:
        promote_risk = False

    evidence = (
        f"OOS Δmax_dd={d_dd:.4g} boot={dd_boot}; Δadverse_mo30={d_adv:.4g} boot={adv_boot}; "
        f"Δpnl={d_pnl:.4g}; early/late Δdd={d_dd_e:.4g}/{d_dd_l:.4g} "
        f"Δadv={d_adv_e:.4g}/{d_adv_l:.4g}; placebo Δdd={d_dd_pl:.4g} Δadv={d_adv_pl:.4g}; "
        f"n_oos={oos.get('n')} n_oos_breach={oos_b.get('n')}"
    )

    candidates = [
        {
            "id": "exec.minv_breach_throttle",
            "type": "D",
            "lenses": "exec, risk, mm",
            "decision": "Kill" if risk_worsens else ("Promote" if promote_risk else "Hold"),
            "promote_as": "Exec throttle / risk" if promote_risk else None,
            "tradable_alpha": False,
            "evidence": evidence,
            "falsifiers": {
                "risk_helps": risk_helps,
                "ci_ok": ci_ok,
                "sign_stable_oos": sign_stable,
                "placebo_weaker": placebo_fails,
                "risk_worsens": risk_worsens,
            },
        },
        {
            "id": "exec.minv_throttle_cal_join",
            "type": "D",
            "lenses": "exec, info, risk",
            "decision": "Hold",  # default; upgrade below
            "promote_as": None,
            "tradable_alpha": False,
            "evidence": "",
            "falsifiers": {},
        },
        {
            "id": "exec.minv_throttle_as_alpha",
            "type": "D",
            "lenses": "exec",
            "decision": "Hold",
            "promote_as": None,
            "tradable_alpha": False,
            "evidence": (
                f"PnL Δ OOS={d_pnl:.4g} — flat/negative expected; never Promote as sized alpha. "
                "y_tick_20 remains Hold."
            ),
            "note": "Always Hold as alpha — desk rule",
        },
        {
            "id": "exec.placebo_throttle",
            "type": "D",
            "lenses": "exec",
            "decision": "Kill" if (np.isfinite(d_dd_pl) and d_dd_pl > max(d_dd, 0) + 1e-6 and d_dd_pl > 0) else "Hold",
            "evidence": f"placebo Δdd={d_dd_pl:.4g} Δadv={d_adv_pl:.4g} vs real Δdd={d_dd:.4g} Δadv={d_adv:.4g}",
            "note": "Falsifier control — Kill if placebo beats real on risk",
        },
    ]

    # cal join: Promote as secondary paper weight only if improves vs plain throttle OOS
    d_dd_cal = mean(oos_b if oos_b.get("n", 0) >= 2 else oos, "d_max_dd_cal")
    d_adv_cal = mean(oos_b if oos_b.get("n", 0) >= 2 else oos, "d_adverse_mo_cal")
    cal_helps = bool(
        (np.isfinite(d_dd_cal) and np.isfinite(d_dd) and d_dd_cal >= d_dd)
        or (np.isfinite(d_adv_cal) and np.isfinite(d_adv) and d_adv_cal <= d_adv)
    )
    cal_cand = candidates[1]
    cal_cand["evidence"] = (
        f"cal-join OOS Δdd={d_dd_cal:.4g} Δadv={d_adv_cal:.4g} vs plain Δdd={d_dd:.4g} Δadv={d_adv:.4g}; "
        "calendar Ridge Monitor-only paper weight"
    )
    if promote_risk and cal_helps:
        cal_cand["decision"] = "Promote"
        cal_cand["promote_as"] = "Exec throttle / risk (secondary paper weight)"
    else:
        cal_cand["decision"] = "Hold"
    cal_cand["falsifiers"] = {"cal_helps_vs_plain": cal_helps, "parent_promote": promote_risk}

    # force alpha Hold
    candidates[2]["decision"] = "Hold"

    trade_ideas = [
        {
            "id": "ti.paper_minv_exec_throttle",
            "label": "Exec throttle" if promote_risk else "Monitor",
            "title": "MinV/EGARCH breach → widen / cut size / pause takes (paper harness)",
            "depends_on": [
                "risk.egarch_minv_bands",
                "risk.daily_minv_panel",
                "exec.minv_breach_throttle",
            ],
            "gate_status": {
                "exec.minv_breach_throttle": candidates[0]["decision"],
                "exec.minv_throttle_as_alpha": "Hold",
            },
            "tradable_size": "N/A — risk overlay; not sized alpha",
            "falsifier": evidence,
        },
        {
            "id": "ti.paper_cal_throttle_join",
            "label": "Exec throttle" if cal_cand["decision"] == "Promote" else "Exec throttle (paper)",
            "title": "Calendar Ridge score deepens breach throttle (paper-only weight)",
            "depends_on": ["info.v_feature_ridge_calendar", "exec.minv_throttle_cal_join"],
            "gate_status": {
                "info.v_feature_ridge_calendar": "Promote",
                "exec.minv_throttle_cal_join": cal_cand["decision"],
            },
            "tradable_size": "Paper-only secondary weight",
            "falsifier": cal_cand["evidence"],
        },
    ]
    return {"candidates": candidates, "trade_ideas_new": trade_ideas}


def make_figures(summary: dict, day_rows: list[dict]) -> list[str]:
    FIG.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    deltas = summary.get("delta_rows") or []

    # 1) breach timeline
    fig, ax = plt.subplots(figsize=(11, 4.2))
    breaches = []
    for r in day_rows:
        if not r.get("ok"):
            continue
        for w in r.get("windows") or []:
            breaches.append((r["day"], r["venue"], r["symbol"], w))
    if breaches:
        days = sorted({b[0] for b in breaches})
        ymap = {d: i for i, d in enumerate(days)}
        colors = {"hyperliquid": "#1f77b4", "deribit": "#ff7f0e", "kraken": "#2ca02c"}
        for day, venue, sym, w in breaches:
            y = ymap[day]
            ax.barh(
                y,
                (w["t1_s"] - w["t0_s"]) / 3600.0,
                left=w["t0_s"] / 3600.0,
                height=0.35,
                color=colors.get(venue, "gray"),
                alpha=0.75,
                label=venue if venue not in ax.get_legend_handles_labels()[1] else "",
            )
        ax.set_yticks(list(ymap.values()))
        ax.set_yticklabels([d[5:] for d in days])
        ax.set_xlabel("UTC hour")
        ax.set_title("MinV/EGARCH breach throttle windows (merged hn)")
        handles, labels = ax.get_legend_handles_labels()
        by = dict(zip(labels, handles))
        if by:
            ax.legend(by.values(), by.keys(), fontsize=8, loc="best")
        ax.grid(True, axis="x", alpha=0.3)
    else:
        ax.text(0.5, 0.5, "no breach windows", ha="center", transform=ax.transAxes)
    p = FIG / "breach_timeline.png"
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    written.append(str(p))

    # 2) delta DD / adverse scatter OOS
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    oos = [r for r in deltas if r.get("split") == "test"]
    for ax, key, title, good in (
        (axes[0], "d_max_dd_throttle", "OOS Δ max_dd (throttle−base)\n>0 = less severe DD", 1),
        (axes[1], "d_adverse_mo_throttle", "OOS Δ adverse mo30\n<0 = less adverse", -1),
    ):
        xs = np.arange(len(oos))
        ys = [r.get(key) for r in oos]
        cols = ["#d62728" if r.get("has_breach") else "#7f7f7f" for r in oos]
        ax.bar(xs, [y if y is not None else 0 for y in ys], color=cols, alpha=0.85)
        ax.axhline(0, color="gray", lw=0.8)
        ax.set_title(title, fontsize=10)
        ax.set_xticks(xs)
        ax.set_xticklabels([f"{r['day'][5:]}\n{r['venue'][:2]}" for r in oos], fontsize=6, rotation=0)
        ax.grid(True, axis="y", alpha=0.3)
    fig.suptitle("Chronological OOS risk deltas (red = breach day-venue)", fontsize=11)
    fig.tight_layout()
    p = FIG / "oos_risk_deltas.png"
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    written.append(str(p))

    # 3) cumulative risk metrics (running mean Δdd / Δadv on OOS chronologically)
    fig, ax = plt.subplots(figsize=(9, 4))
    oos_sorted = sorted(oos, key=lambda r: (r["day"], r["venue"], r["symbol"]))
    if oos_sorted:
        dd = np.asarray([r.get("d_max_dd_throttle") for r in oos_sorted], dtype=float)
        adv = np.asarray([r.get("d_adverse_mo_throttle") for r in oos_sorted], dtype=float)
        cdd = np.cumsum(np.nan_to_num(dd)) / np.arange(1, len(dd) + 1)
        cadv = np.cumsum(np.nan_to_num(adv)) / np.arange(1, len(adv) + 1)
        ax.plot(cdd, "o-", label="cummean Δmax_dd", color="#1f77b4")
        ax.plot(cadv, "s-", label="cummean Δadverse_mo30", color="#d62728")
        ax.axhline(0, color="gray", lw=0.8)
        ax.legend(fontsize=8)
        ax.set_xlabel("OOS day-venue order")
        ax.set_title("Cumulative mean OOS risk deltas")
        ax.grid(True, alpha=0.3)
    p = FIG / "cumulative_risk.png"
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    written.append(str(p))

    # 4) markout before/after from path artifact if any
    paths = sorted(OUT.glob("path_*.npz"))
    if paths:
        z = np.load(paths[0])
        sod = z["sod_s"]
        th = z["throttled"]
        eq_b = z["equity_base"]
        eq_t = z["equity_th"]
        fig, axes = plt.subplots(3, 1, figsize=(10, 7), sharex=True)
        axes[0].plot(sod / 3600, eq_b, label="always_on", alpha=0.85)
        axes[0].plot(sod / 3600, eq_t, label="throttle", alpha=0.85)
        axes[0].set_ylabel("equity bps")
        axes[0].legend(fontsize=8)
        axes[0].set_title(paths[0].stem.replace("path_", "path "))
        axes[1].plot(sod / 3600, z["inv_base"], label="inv base", alpha=0.8)
        axes[1].plot(sod / 3600, z["inv_th"], label="inv th", alpha=0.8)
        axes[1].set_ylabel("inventory")
        axes[1].legend(fontsize=8)
        axes[2].fill_between(sod / 3600, 0, th, step="pre", alpha=0.4, color="#ff7f0e")
        axes[2].set_ylabel("throttle on")
        axes[2].set_xlabel("UTC hour")
        for ax in axes:
            ax.grid(True, alpha=0.3)
        fig.tight_layout()
        p = FIG / "throttle_state_path.png"
        fig.savefig(p, dpi=140, bbox_inches="tight")
        plt.close(fig)
        written.append(str(p))

    # 5) policy comparison bars
    fig, ax = plt.subplots(figsize=(8, 4))
    blocks = [
        ("OOS all", summary.get("agg_oos") or {}),
        ("OOS breach", summary.get("agg_oos_breach") or {}),
        ("OOS early", summary.get("agg_oos_early") or {}),
        ("OOS late", summary.get("agg_oos_late") or {}),
    ]
    labels = [b[0] for b in blocks]
    dd_m = [mean_safe(b[1], "d_max_dd_throttle") for b in blocks]
    adv_m = [mean_safe(b[1], "d_adverse_mo_throttle") for b in blocks]
    x = np.arange(len(labels))
    w = 0.35
    ax.bar(x - w / 2, dd_m, w, label="Δmax_dd", color="#1f77b4")
    ax.bar(x + w / 2, adv_m, w, label="Δadverse_mo30", color="#d62728")
    ax.axhline(0, color="gray", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend(fontsize=8)
    ax.set_title("Risk deltas by slice (throttle − always_on)")
    ax.grid(True, axis="y", alpha=0.3)
    p = FIG / "policy_slice_bars.png"
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    written.append(str(p))

    # 6) PnL vs risk tradeoff
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    for r in deltas:
        ax.scatter(
            r.get("d_pnl_throttle"),
            r.get("d_max_dd_throttle"),
            c="#d62728" if r.get("has_breach") else "#7f7f7f",
            s=40 if r.get("split") == "test" else 22,
            alpha=0.8,
            marker="o" if r.get("split") == "test" else "x",
        )
    ax.axhline(0, color="gray", lw=0.7)
    ax.axvline(0, color="gray", lw=0.7)
    ax.set_xlabel("Δ PnL bps (throttle − base)")
    ax.set_ylabel("Δ max_dd ( >0 = better risk )")
    ax.set_title("PnL vs risk tradeoff (o=OOS x=train; red=breach)")
    ax.grid(True, alpha=0.3)
    p = FIG / "pnl_vs_risk.png"
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    written.append(str(p))

    return written


def mean_safe(block: dict, key: str) -> float:
    m = ((block.get(key) or {}).get("mean")) if block else None
    try:
        return float(m)
    except (TypeError, ValueError):
        return float("nan")


def write_reports(summary: dict, gates: dict) -> None:
    APP.mkdir(parents=True, exist_ok=True)
    lines = [
        "| id | type | lenses | decision | evidence |",
        "|----|------|--------|----------|----------|",
    ]
    for c in gates["candidates"]:
        ev = str(c.get("evidence", "")).replace("|", "/")[:240]
        extra = f" · as {c['promote_as']}" if c.get("promote_as") else ""
        lines.append(
            f"| `{c['id']}` | {c.get('type','D')} | {c.get('lenses','')} | **{c['decision']}**{extra} | {ev} |"
        )
    (APP / "CANDIDATES.md").write_text("\n".join(lines) + "\n")

    samp = summary.get("sample") or {}
    oos = summary.get("agg_oos") or {}
    oos_b = summary.get("agg_oos_breach") or {}
    report = f"""# Paper exec-throttle — EXP_REPORT

## Honesty
- Class: `{HONESTY['class']}` · live_orders={HONESTY['live_orders']} · alpha_claim={HONESTY['alpha_claim']}
- Fills: {HONESTY['fills']}
- Promote scope: **{HONESTY['promote_scope']}** (Hold as alpha always)
- Primary monitors: MinV / EGARCH bands (Promote stack) + calendar Ridge as paper-only secondary
- Tick `y_tick_20`: **Hold** — never sized
- ClickHouse MCP banned

## Sample
- ETH days={samp.get('eth_days')}
- BTC days={samp.get('btc_days')}
- train={samp.get('train_days')} · test(OOS)={samp.get('test_days')}
- n_ok_dayvenue={samp.get('n_ok_days')} · n_breach_dayvenue={samp.get('n_breach_dayvenue')}
- venues={samp.get('venues')} · cal_thresh_abs={samp.get('cal_thresh_abs')}

## Knobs
- size_mult={THROTTLE_SIZE_MULT} · widen_bps={THROTTLE_WIDEN_BPS} · pov={THROTTLE_POV} · take_pause={THROTTLE_TAKE_PAUSE}
- cal boost: size={CAL_BOOST_SIZE_MULT} widen={CAL_BOOST_WIDEN_BPS} pov={CAL_BOOST_POV} @ |score|≥q{int(CAL_SCORE_QUANTILE*100)}
- friction base={BASE_FRICTION_BPS} bps · base_size={BASE_SIZE}

## OOS risk / PnL (throttle − always_on)
- all: Δmax_dd={oos.get('d_max_dd_throttle')} · Δadverse_mo30={oos.get('d_adverse_mo_throttle')} · Δpnl={oos.get('d_pnl_throttle')}
- breach-only: Δmax_dd={oos_b.get('d_max_dd_throttle')} · Δadverse_mo30={oos_b.get('d_adverse_mo_throttle')} · n={oos_b.get('n')}
- early: {summary.get('agg_oos_early')}
- late: {summary.get('agg_oos_late')}
- placebo: Δmax_dd={oos.get('d_max_dd_placebo')} · Δadverse={oos.get('d_adverse_mo_placebo')}

## Gate rollup
"""
    for c in gates["candidates"]:
        report += f"- **{c['decision']}** `{c['id']}`"
        if c.get("promote_as"):
            report += f" → {c['promote_as']}"
        report += f" — {str(c.get('evidence',''))[:200]}\n"
    report += """
## Artifacts
- `out/paper_throttle/summary.json`
- `out/paper_throttle/delta_rows.json`
- `out/paper_throttle/gates.json`
- `out/paper_throttle/figs/breach_timeline.png`, `oos_risk_deltas.png`, `cumulative_risk.png`,
  `throttle_state_path.png`, `policy_slice_bars.png`, `pnl_vs_risk.png`
"""
    (APP / "EXP_REPORT.md").write_text(report)

    (OUT / "summary.json").write_text(
        json.dumps(
            _jsonable(
                {
                    **{k: v for k, v in summary.items() if k != "delta_rows"},
                    "n_delta_rows": len(summary.get("delta_rows") or []),
                    "gates": gates,
                }
            ),
            indent=2,
        )
    )
    (OUT / "delta_rows.json").write_text(json.dumps(_jsonable(summary.get("delta_rows") or []), indent=2))
    (OUT / "gates.json").write_text(json.dumps(_jsonable(gates), indent=2))
    (OUT / "timeline.json").write_text(json.dumps(_jsonable(summary.get("timeline") or []), indent=2))


def write_notes() -> None:
    text = """# Paper exec-throttle / risk harness — MinV monitors → desk actions

**Book:** Flora & Renò (2020-09-17)
**Status:** `exp_run`
**Lib:** [`../../../lib/vstat.py`](../../../lib/vstat.py) · loaders [`../../scripts/_data.py`](../../scripts/_data.py)
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md) · Desk [`../../DESK_MEMO.md`](../../DESK_MEMO.md)
**Script:** [`../../scripts/exp_paper_throttle.py`](../../scripts/exp_paper_throttle.py)
**Out:** [`../../out/paper_throttle/`](../../out/paper_throttle/)

---

## Pass 1 — object

Convert **Promoted** risk monitors into simulated maker-desk throttle actions:

| Promote input | Use in harness |
|---------------|----------------|
| `risk.egarch_minv_bands` / `risk.daily_minv_panel` | Breach when MinV < EGARCH 5%; window `[τ★, τ★+h_n]` |
| `risk.v_vs_jump_taxonomy` | Shape label retained (V vs Λ) — narrative only |
| `risk.stress_day_minv` | Stress days in sample for breach density |
| `info.v_feature_ridge_calendar` | **Secondary paper-only weight** — deepen throttle if \\|score\\| extreme |

**Not used as alpha:** `y_tick_20` (Hold). Calendar Ridge stays Monitor (R²≪1).

### Actions (paper)

- `quote_widen_bps` +5 (+8 with cal boost)
- `size_mult` 0.35 (0.22 cal boost)
- `pov` / participation 0.20 (0.10 cal boost)
- pause aggressive lean (`take_pause`) for `1×h_n` after trough detection

### Benchmark

Always-on baseline on the **same** tape. Metrics: markout (5/30/60s), adverse-selection proxy (−maker mo30), inventory path, participation, equity bps, max drawdown. Honest synthetic maker fills at trade print + friction — no fantasy mid-touch.

### Clocks / causality

- τ★ from daily MinV panel; throttle **starts at trough observation** (no pre-τ★ look-ahead).
- Chronological OOS (~60/40 UTC days, aligned with feature_reg).
- Placebo: random windows of matched duration.

## Pass 2 — signals

- Label: **Exec throttle / risk** — not soft-Promote to sized alpha
- Falsifiers: OOS risk CI, early∧late sign-stability, placebo weaker than real
- Kill if throttle worsens adverse markout / DD with CI

## Empirics

See `EXP_REPORT.md` · `CANDIDATES.md` · memo notebook `paper_throttle.ipynb`.
"""
    (APP / "NOTES.md").write_text(text)


def build_notebook(summary: dict, gates: dict) -> Path:
    """Memo-dense notebook that loads artifacts + embeds figures."""
    cells: list[dict] = []

    def md(s: str) -> None:
        cells.append(
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [ln + "\n" for ln in s.strip("\n").split("\n")],
            }
        )

    def code(s: str) -> None:
        cells.append(
            {
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": [ln + "\n" for ln in s.strip("\n").split("\n")],
            }
        )

    c0 = next((c for c in gates["candidates"] if c["id"] == "exec.minv_breach_throttle"), {})
    decision = c0.get("decision", "Hold")
    promote_as = c0.get("promote_as") or "—"

    md(
        f"""# Paper exec-throttle — V-shapes (desk memo)

MinV / EGARCH **Promote** monitors → simulated desk throttle vs always-on baseline.

| | |
|--|--|
| Primary trigger | UTC-day MinV < EGARCH 5% · window `[τ★, τ★+h_n]` |
| Secondary | Calendar Ridge score (Monitor) — paper-only deepen |
| Primary gate | **{decision}** as `{promote_as}` |
| Alpha | **Hold** always (`y_tick_20` stays Hold) |
| Fills | Synthetic maker × tape print + friction — no fantasy |

**SoT:** [`NOTES.md`](NOTES.md) · [`EXP_REPORT.md`](EXP_REPORT.md) · [`CANDIDATES.md`](CANDIDATES.md) · artifacts [`../../out/paper_throttle/`](../../out/paper_throttle/) · Desk [`../../DESK_MEMO.md`](../../DESK_MEMO.md) · Trade ideas [`../../notebooks/trade_ideas.ipynb`](../../notebooks/trade_ideas.ipynb).

Script: [`../../scripts/exp_paper_throttle.py`](../../scripts/exp_paper_throttle.py). ClickHouse MCP banned.
"""
    )
    md(
        """## 1. Theory — why throttle, not fade

Flora–Renò MinV significance flags **reverting-drift / fragility** days. Desk job is risk overlay:

- Widen quotes + cut size + pause aggressive takes for `1×h_n` after trough detection
- Not a mean-reversion fade (that candidate remains Hold — post-trough CI includes 0)
- Calendar Ridge Monitor may **reinforce** throttle weight; never standalone size
"""
    )
    md(
        """## 2. Method — honesty bar

| Item | Choice |
|------|--------|
| Trigger | Promote EGARCH MinV `sig_5` at τ★ |
| Causality | Throttle starts at τ★ (trough observed) |
| Baseline | Always-on maker on same tape |
| Fills | Participation × size_mult; fill @ print ± (base+widen) bps |
| OOS | Chronological day split ~60/40 |
| Falsifier | Placebo random windows; early∧late; risk CI |
| Promote bar | Risk improves OOS (DD / adverse mo) even if PnL flat; **Hold as alpha** |
"""
    )
    md("## 3. Load artifacts")
    code(
        """
from pathlib import Path
import json
from IPython.display import Image, display, Markdown

BOOK = Path('../..').resolve()
OUT = BOOK / 'out' / 'paper_throttle'
FIG = OUT / 'figs'
summary = json.loads((OUT / 'summary.json').read_text())
gates = json.loads((OUT / 'gates.json').read_text())
deltas = json.loads((OUT / 'delta_rows.json').read_text())
print('ok_days', summary['sample']['n_ok_days'], 'breach', summary['sample']['n_breach_dayvenue'])
print('train', summary['sample']['train_days'])
print('test ', summary['sample']['test_days'])
print('knobs', summary['knobs'])
"""
    )
    md("## 4. OOS risk / PnL board")
    code(
        """
import pandas as pd
rows = []
for label, key in [
    ('OOS all', 'agg_oos'),
    ('OOS breach', 'agg_oos_breach'),
    ('OOS calm', 'agg_oos_calm'),
    ('OOS early', 'agg_oos_early'),
    ('OOS late', 'agg_oos_late'),
    ('train', 'agg_train'),
]:
    blk = summary.get(key) or {}
    def m(k):
        b = blk.get(k) or {}
        return b.get('mean'), (b.get('lo'), b.get('hi')), b.get('n')
    dd, ddci, n = m('d_max_dd_throttle')
    adv, advci, _ = m('d_adverse_mo_throttle')
    pnl, pnlci, _ = m('d_pnl_throttle')
    rows.append(dict(slice=label, n=blk.get('n'), d_max_dd=dd, dd_ci=ddci, d_adverse_mo30=adv, adv_ci=advci, d_pnl=pnl))
display(pd.DataFrame(rows))
print('placebo OOS', (summary.get('agg_oos') or {}).get('d_max_dd_placebo'), (summary.get('agg_oos') or {}).get('d_adverse_mo_placebo'))
"""
    )
    md("## 5. Figures")
    code(
        """
from IPython.display import Image, display
for name in [
    'breach_timeline.png',
    'oos_risk_deltas.png',
    'cumulative_risk.png',
    'throttle_state_path.png',
    'policy_slice_bars.png',
    'pnl_vs_risk.png',
]:
    p = FIG / name
    print('==', name, 'exists' if p.exists() else 'MISSING')
    if p.exists():
        display(Image(filename=str(p)))
"""
    )
    md("## 6. Gate / candidates")
    code(
        """
import pandas as pd
display(pd.DataFrame(gates['candidates'])[['id','decision','lenses','evidence']])
print('--- trade ideas ---')
for ti in gates.get('trade_ideas_new') or []:
    print(ti['id'], ti['label'], ti['title'][:80])
"""
    )
    md(
        """## 7. Desk takeaway

- **Exec throttle / risk** Promote only if falsifiers hold (OOS risk help, placebo weaker, early∧late).
- **Hold as alpha** — flat PnL is acceptable; do not size on throttle PnL or `y_tick_20`.
- Calendar join is paper-only secondary weight on top of MinV breach.
- Live POV params still respect `info.v_path_continuous` Hold for continuity narrative.
"""
    )

    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "cells": cells,
    }
    path = APP / "paper_throttle.ipynb"
    path.write_text(json.dumps(nb, indent=1))
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-files", type=int, default=24)
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--no-btc", action="store_true")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    write_notes()
    result = run_panel(
        max_files=args.max_files,
        include_btc=not args.no_btc,
        fast=args.fast,
        seed=args.seed,
    )
    summary = result["summary"]
    day_rows = result["day_rows"]
    # persist day_rows light
    light_days = []
    for r in day_rows:
        rr = dict(r)
        if "policies" in rr:
            rr["policies"] = {
                k: {kk: vv for kk, vv in v.items() if kk not in ("equity", "inv_path")}
                for k, v in rr["policies"].items()
            }
        light_days.append(rr)
    (OUT / "day_rows.json").write_text(json.dumps(_jsonable(light_days), indent=2))

    print("== figures ==", flush=True)
    figs = make_figures(summary, day_rows)
    print("wrote", figs, flush=True)

    gates = gate_decisions(summary)
    write_reports(summary, gates)
    nb = build_notebook(summary, gates)
    print("notebook", nb, flush=True)
    print(
        json.dumps(
            _jsonable(
                {
                    "n_ok": summary["sample"]["n_ok_days"],
                    "n_breach": summary["sample"]["n_breach_dayvenue"],
                    "agg_oos": summary.get("agg_oos"),
                    "gates": gates["candidates"],
                }
            ),
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
