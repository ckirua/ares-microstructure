from __future__ import annotations
#!/usr/bin/env python3
"""Phase 3a: crash_stats + cross_section (Pass 1 + Pass 2).

Pass 1 — crash_stats: ΔP, i_c, Δt, recovery on Nanex + severity-gated SSM.
Pass 1 — cross_section: quintiles + NW-OLS of severity on size/vol/liq/price.
Pass 2 — markout / V vs continuation / duration→risk; ex-ante predictive xsec;
         multi-coin panel; VPIN interaction; time-split + placebo falsifiers.

Severity gate (locked primary): |ΔP|≥10 bps, i_c≥5 on SSM z*=6 (Phase 2 raw=3668).
OI proxy: daily notional (true OI loader unavailable — document ceiling).
Dense TOB optional; tape-price markout always.

ClickHouse MCP banned. Data: HL + Deribit + Kraken via scripts/_data.py.
"""

import os

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
STARTARB = Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb'))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(STARTARB / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import (  # noqa: E402
    CORE_VENUES,
    day_bounds_ns,
    ensure_env,
    load_day_trades,
    load_venue_tob,
    normalize_side,
    venue_instrument,
)
from research.lib.continuous import amihud_illiquidity, vpin_bucket  # noqa: E402
from research.lib.crash import (  # noqa: E402
    classify_recovery,
    detect_ssm_events,
    kalman_ssm_filter,
    mc_garch_bar_vol,
    nanex_detect,
    post_event_markout_px,
    recovery_fraction,
    severity_gate,
    sigma_process_meas,
)
from research.lib.stats import bootstrap_ci, nw_ols, spearman_r, time_split_mask  # noqa: E402
from research.lib.tob import tob_resilience  # noqa: E402

OUT = BOOK / "out" / "phase3a_stats_xsec"
FIG = OUT / "figs"

DEFAULT_DAYS = [
    "2026-09-04",
    "2026-09-05",
    "2026-09-06",
    "2026-09-07",
    "2026-09-08",
    "2026-09-09",
    "2026-09-10",
]
DEFAULT_SYMBOLS = ["ETH", "BTC"]
Z_STAR = 6.0
# Primary severity gate (Pass 1); ablations in Pass 2
GATE_PRIMARY = {"min_dp_pct": 0.10, "min_i_c": 5}
GATE_ABLATIONS = [
    {"min_dp_pct": 0.05, "min_i_c": 3, "label": "5bps_ic3"},
    {"min_dp_pct": 0.10, "min_i_c": 5, "label": "10bps_ic5"},
    {"min_dp_pct": 0.30, "min_i_c": 10, "label": "30bps_ic10"},
]
NANEX_PCT = 0.003  # 30 bps crypto Hold from Phase 2
RECOVERY_H_S = 5.0


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        if obj.dtype == object:
            return [_jsonable(x) for x in obj.tolist()]
        return obj.tolist()
    if isinstance(obj, (np.floating, float)):
        x = float(obj)
        return x if np.isfinite(x) else None
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if obj is None:
        return None
    return str(obj)


def _save_fig(path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=140, bbox_inches="tight")
    plt.close()


def _summarize(arr: np.ndarray) -> dict[str, float]:
    a = np.asarray(arr, dtype=np.float64)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return {"n": 0, "mean": float("nan"), "median": float("nan"), "sd": float("nan"),
                "p25": float("nan"), "p75": float("nan")}
    return {
        "n": int(a.size),
        "mean": float(a.mean()),
        "median": float(np.median(a)),
        "sd": float(a.std(ddof=1)) if a.size > 1 else 0.0,
        "p25": float(np.percentile(a, 25)),
        "p75": float(np.percentile(a, 75)),
    }


def _day_features(ts: np.ndarray, px: np.ndarray, qty: np.ndarray, side: np.ndarray) -> dict[str, float]:
    """Ex-ante / contemporaneous cell features (OI proxy = notional)."""
    notional = px * qty
    day_notional = float(np.nansum(notional[np.isfinite(notional)]))
    mean_px = float(np.nanmean(px[px > 0])) if (px > 0).any() else float("nan")
    # 1-minute RV
    bar_ns = 60 * 1_000_000_000
    if ts.size < 10:
        return {
            "log_notional": float("nan"),
            "notional": day_notional,
            "mean_px": mean_px,
            "log_px": float("nan"),
            "rv": float("nan"),
            "amihud": float("nan"),
            "vpin_mean": float("nan"),
            "n_trades": int(ts.size),
        }
    t0 = int(ts[0] // bar_ns * bar_ns)
    bucket = (ts - t0) // bar_ns
    last_px, last_not = [], []
    for b in np.unique(bucket):
        m = bucket == b
        pp = px[m]
        nn = notional[m]
        if (pp > 0).any():
            last_px.append(float(pp[pp > 0][-1]))
            last_not.append(float(np.nansum(nn)))
    last_px_a = np.asarray(last_px, dtype=np.float64)
    last_not_a = np.asarray(last_not, dtype=np.float64)
    if last_px_a.size >= 3:
        r = np.diff(np.log(last_px_a))
        rv = float(np.sqrt(np.nansum(r ** 2)))
        am = amihud_illiquidity(r, last_not_a[1:])
        amihud = float(am.get("illiq", float("nan")))
    else:
        rv, amihud = float("nan"), float("nan")
    med_q = float(np.median(qty[qty > 0])) if (qty > 0).any() else 1.0
    vpin = vpin_bucket(
        normalize_side(side), qty, bucket_volume=max(50.0 * med_q, 1e-6), n_buckets_window=30
    )
    return {
        "log_notional": float(np.log(max(day_notional, 1.0))),
        "notional": day_notional,
        "mean_px": mean_px,
        "log_px": float(np.log(mean_px)) if mean_px > 0 else float("nan"),
        "rv": rv,
        "amihud": amihud,
        "vpin_mean": float(vpin.get("mean_vpin", float("nan"))),
        "n_trades": int(ts.size),
    }


def _try_tob(venue: str, symbol: str, day: str) -> dict[str, Any] | None:
    try:
        from startarb.data.bbo_stream import load_quote_stream

        inst = venue_instrument(symbol, venue)
        qs = load_quote_stream(
            venue,
            inst,
            [day],
            max_files=6,
            prefer_shards=True,
            quotes_per_minute=30,
            quiet=True,
            allow_trade_fallback=False,
        )
        ts = np.asarray(qs.ts_ns, dtype=np.int64)
        bid = np.asarray(qs.bid, dtype=np.float64)
        ask = np.asarray(qs.ask, dtype=np.float64)
        lo, hi = day_bounds_ns(day)
        m = (ts >= lo) & (ts < hi) & np.isfinite(bid) & np.isfinite(ask) & (ask > bid)
        if int(m.sum()) < 50:
            return None
        bsz = np.asarray(getattr(qs, "bid_sz", np.ones(ts.size)), dtype=np.float64)
        asz = np.asarray(getattr(qs, "ask_sz", np.ones(ts.size)), dtype=np.float64)
        mid = 0.5 * (bid[m] + ask[m])
        depth = (bsz[m] if bsz.size == ts.size else np.ones(int(m.sum()))) + (
            asz[m] if asz.size == ts.size else np.ones(int(m.sum()))
        )
        return {
            "ts": ts[m],
            "mid": mid,
            "depth": depth,
            "n": int(m.sum()),
            "source": "warehouse_quote_stream",
        }
    except Exception:
        try:
            tob = load_venue_tob(venue, symbol, max_day_dirs=4, max_rows=150_000)
            mid = tob["mid"]
            depth = tob["bid_sz"] + tob["ask_sz"]
            return {
                "ts": tob["ts"],
                "mid": mid,
                "depth": depth,
                "n": int(tob["ts"].size),
                "source": "collector",
            }
        except Exception:
            return None


def _process_cell(
    venue: str,
    symbol: str,
    day: str,
    *,
    max_files: int,
) -> dict[str, Any] | None:
    rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
    flags = rec["completeness"]
    if not flags.get("complete"):
        return {
            "venue": venue,
            "symbol": symbol,
            "day": day,
            "complete": False,
            "skip": flags.get("reasons"),
            "n_trades": flags.get("n", 0),
        }
    tape = rec["tape"]
    ts = np.asarray(tape["ts"], dtype=np.int64)
    px = np.asarray(tape["px"], dtype=np.float64)
    qty = np.asarray(tape["qty"], dtype=np.float64)
    side = normalize_side(tape["side"])
    m = np.isfinite(px) & (px > 0) & np.isfinite(ts)
    ts, px, qty, side = ts[m], px[m], qty[m], side[m]
    if ts.size < 500:
        return {
            "venue": venue,
            "symbol": symbol,
            "day": day,
            "complete": False,
            "skip": ["n_after_clean<500"],
            "n_trades": int(ts.size),
        }

    # Detectors
    nanex = nanex_detect(ts, px, min_pct=NANEX_PCT, min_trades=10, max_window_s=1.5)
    comp = mc_garch_bar_vol(ts, px)
    log_px = np.log(px)
    sig = sigma_process_meas(ts, comp, sigma_m_frac=1.0, log_px=log_px)
    filt = kalman_ssm_filter(ts, px, sig["sigma_p2_dt"], sig["sigma_m2"])
    ssm_raw = detect_ssm_events(ts, px, filt, z_star=Z_STAR)

    # Severity gates
    gate_rows = {}
    ssm_primary = None
    for g in GATE_ABLATIONS:
        gated = severity_gate(ssm_raw, min_dp_pct=g["min_dp_pct"], min_i_c=g["min_i_c"])
        gate_rows[g["label"]] = {
            "n_raw": gated["n_raw"],
            "n_kept": gated["n_events"],
            "gate": gated["gate"],
            "median_dp": float(np.nanmedian(gated["dp_pct"])) if gated["n_events"] else None,
            "median_ic": float(np.nanmedian(gated["i_c"])) if gated["n_events"] else None,
            "median_dt": float(np.nanmedian(gated["dt_s"])) if gated["n_events"] else None,
        }
        if g["label"] == "10bps_ic5":
            ssm_primary = gated
    assert ssm_primary is not None

    # Recovery + class for Nanex and gated SSM
    def _pack_events(ev: dict[str, Any], label: str) -> dict[str, Any]:
        n = int(ev.get("n_events", 0))
        if n == 0:
            return {"source": label, "n_events": 0}
        recov = recovery_fraction(
            ts, px, ev["start_i"], ev["end_i"], ev["direction"], horizon_s=RECOVERY_H_S
        )
        cls = classify_recovery(recov)
        mo = post_event_markout_px(ts, px, ev["end_i"], ev["direction"])
        # duration as risk: corr(dt, |markout 5s|)
        mo5 = []
        for k in range(n):
            b = int(ev["end_i"][k])
            h_ns = int(5.0 * 1e9)
            j = int(np.searchsorted(ts, ts[b] + h_ns, side="right") - 1)
            if j > b and px[b] > 0:
                mo5.append(abs(ev["direction"][k] * (px[j] - px[b]) / px[b] * 1e4))
            else:
                mo5.append(np.nan)
        mo5_a = np.asarray(mo5, dtype=np.float64)
        dt_a = np.asarray(ev["dt_s"], dtype=np.float64)
        return {
            "source": label,
            "n_events": n,
            "dp": _summarize(ev["dp_pct"]),
            "i_c": _summarize(ev["i_c"].astype(np.float64)),
            "dt_s": _summarize(ev["dt_s"]),
            "recovery_5s": _summarize(recov),
            "class": {
                "n_v_recovery": cls["n_v_recovery"],
                "n_continuation": cls["n_continuation"],
                "n_partial": cls["n_partial"],
                "share_v": cls["share_v"],
                "share_continuation": cls["share_continuation"],
            },
            "markout_px": mo,
            "spearman_dt_abs_mo5": spearman_r(dt_a, mo5_a),
            "dp_pct": np.asarray(ev["dp_pct"], dtype=np.float64),
            "i_c_arr": np.asarray(ev["i_c"], dtype=np.float64),
            "dt_arr": dt_a,
            "recov_arr": recov,
            "ts_start": np.asarray(ev.get("ts_start", ts[ev["start_i"]]), dtype=np.int64),
            "direction": np.asarray(ev["direction"], dtype=np.int64),
            "end_i": np.asarray(ev["end_i"], dtype=np.int64),
            "start_i": np.asarray(ev["start_i"], dtype=np.int64),
        }

    nanex_pack = _pack_events(
        {
            "n_events": nanex["n_events"],
            "start_i": nanex["start_i"],
            "end_i": nanex["end_i"],
            "direction": nanex["direction"],
            "dp_pct": nanex["dp_pct"],
            "i_c": nanex["n_trades"],
            "dt_s": nanex["dt_s"],
            "ts_start": ts[nanex["start_i"]] if nanex["n_events"] else np.zeros(0, dtype=np.int64),
        },
        "nanex_30bps",
    )
    ssm_pack = _pack_events(ssm_primary, "ssm_gated_10bps_ic5")
    ssm_raw_pack = {
        "n_events": int(ssm_raw["n_events"]),
        "dp": _summarize(ssm_raw["dp_pct"]),
        "i_c": _summarize(ssm_raw["i_c"].astype(np.float64)),
        "dt_s": _summarize(ssm_raw["dt_s"]),
    }

    feats = _day_features(ts, px, qty, side)
    tob = _try_tob(venue, symbol, day)
    resilience = None
    if tob and ssm_pack["n_events"] > 0:
        try:
            resilience = tob_resilience(
                tob["ts"],
                tob["mid"],
                tob["depth"],
                ssm_pack["ts_start"],
                horizons_ms=(500, 1000, 5000),
            )
        except Exception as exc:  # noqa: BLE001
            resilience = {"error": f"{type(exc).__name__}: {exc}"}

    # Placebo: random event times → recovery / markout null
    placebo = None
    if ssm_pack["n_events"] >= 5:
        rng = np.random.default_rng(hash((venue, symbol, day)) % (2**31 - 1))
        n_p = int(ssm_pack["n_events"])
        idx = rng.integers(0, max(ts.size - 20, 1), size=n_p)
        ends = np.clip(idx + 5, 0, ts.size - 1)
        dirs = np.where(rng.random(n_p) > 0.5, 1, -1).astype(np.int64)
        prec = recovery_fraction(ts, px, idx.astype(np.int64), ends, dirs, horizon_s=RECOVERY_H_S)
        pmo = post_event_markout_px(ts, px, ends, dirs)
        placebo = {
            "n": n_p,
            "recovery_median": float(np.nanmedian(prec)),
            "mo5_mean_bps": pmo["by_horizon"].get("5.0", {}).get("mean_bps"),
        }

    return {
        "venue": venue,
        "symbol": symbol,
        "day": day,
        "complete": True,
        "n_trades": int(ts.size),
        "features": feats,
        "gate_ablation": gate_rows,
        "ssm_raw": ssm_raw_pack,
        "nanex": {k: v for k, v in nanex_pack.items() if not isinstance(v, np.ndarray)},
        "ssm_gated": {k: v for k, v in ssm_pack.items() if not isinstance(v, np.ndarray)},
        # keep arrays for pooling
        "_nanex_arr": {k: v for k, v in nanex_pack.items() if isinstance(v, np.ndarray)},
        "_ssm_arr": {k: v for k, v in ssm_pack.items() if isinstance(v, np.ndarray)},
        "tob": {"n": tob["n"] if tob else 0, "source": tob["source"] if tob else None},
        "resilience": resilience,
        "placebo": placebo,
    }


def _quintile_table(x: np.ndarray, y: np.ndarray, *, n_q: int = 5) -> list[dict[str, Any]]:
    """Mean y by x quintile (Tee & Ting Tables V–VIII style)."""
    a = np.asarray(x, dtype=np.float64)
    b = np.asarray(y, dtype=np.float64)
    m = np.isfinite(a) & np.isfinite(b)
    a, b = a[m], b[m]
    if a.size < n_q * 2:
        return []
    edges = np.quantile(a, np.linspace(0, 1, n_q + 1))
    rows = []
    for i in range(n_q):
        lo, hi = edges[i], edges[i + 1]
        mask = (a >= lo) & (a <= hi if i == n_q - 1 else a < hi)
        sub = b[mask]
        rows.append(
            {
                "q": i + 1,
                "x_lo": float(lo),
                "x_hi": float(hi),
                "n": int(sub.size),
                "y_mean": float(np.mean(sub)) if sub.size else None,
                "y_median": float(np.median(sub)) if sub.size else None,
            }
        )
    return rows


def _pool_and_xsec(cells: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [c for c in cells if c.get("complete")]
    # Aggregate stats
    def _pool_stat(key_src: str, field: str) -> dict[str, Any]:
        parts = []
        for c in complete:
            arr = c.get(f"_{key_src}_arr", {}).get(field)
            if arr is not None and np.asarray(arr).size:
                parts.append(np.asarray(arr, dtype=np.float64))
        if not parts:
            return _summarize(np.array([]))
        return _summarize(np.concatenate(parts))

    pooled = {
        "n_cells": len(complete),
        "n_nanex": int(sum(c["nanex"].get("n_events", 0) for c in complete)),
        "n_ssm_raw": int(sum(c["ssm_raw"].get("n_events", 0) for c in complete)),
        "n_ssm_gated": int(sum(c["ssm_gated"].get("n_events", 0) for c in complete)),
        "nanex_dp": _pool_stat("nanex", "dp_pct"),
        "nanex_ic": _pool_stat("nanex", "i_c_arr"),
        "nanex_dt": _pool_stat("nanex", "dt_arr"),
        "nanex_recov": _pool_stat("nanex", "recov_arr"),
        "ssm_dp": _pool_stat("ssm", "dp_pct"),
        "ssm_ic": _pool_stat("ssm", "i_c_arr"),
        "ssm_dt": _pool_stat("ssm", "dt_arr"),
        "ssm_recov": _pool_stat("ssm", "recov_arr"),
    }

    # Class shares (weighted by events)
    n_v = n_c = n_p = 0
    for c in complete:
        cl = c["ssm_gated"].get("class") or {}
        n_v += int(cl.get("n_v_recovery") or 0)
        n_c += int(cl.get("n_continuation") or 0)
        n_p += int(cl.get("n_partial") or 0)
    n_cls = n_v + n_c + n_p
    pooled["ssm_class"] = {
        "n_v_recovery": n_v,
        "n_continuation": n_c,
        "n_partial": n_p,
        "share_v": float(n_v / n_cls) if n_cls else None,
        "share_continuation": float(n_c / n_cls) if n_cls else None,
    }

    # Markout pooled means (skip non-finite cell means)
    mo_acc: dict[str, list[float]] = {}
    dt_mo_pairs: list[tuple[float, float]] = []
    for c in complete:
        mo = (c["ssm_gated"].get("markout_px") or {}).get("by_horizon") or {}
        for h, row in mo.items():
            mb = row.get("mean_bps")
            if mb is not None and np.isfinite(mb):
                mo_acc.setdefault(h, []).append(float(mb))
        # duration risk from cell spearman
        sp = c["ssm_gated"].get("spearman_dt_abs_mo5")
        if sp is not None and np.isfinite(sp):
            dt_mo_pairs.append((float(sp), float(c["ssm_gated"].get("n_events", 0))))
    pooled["ssm_markout_mean_bps"] = {
        h: float(np.mean(v)) if v else None for h, v in mo_acc.items()
    }
    pooled["ssm_markout_n_cells"] = {h: len(v) for h, v in mo_acc.items()}
    pooled["spearman_dt_mo5_cell_mean"] = (
        float(np.average([p[0] for p in dt_mo_pairs], weights=[p[1] for p in dt_mo_pairs]))
        if dt_mo_pairs
        else None
    )

    # Gate ablation totals
    gate_tot: dict[str, dict[str, float]] = {}
    for c in complete:
        for lab, row in (c.get("gate_ablation") or {}).items():
            g = gate_tot.setdefault(lab, {"n_raw": 0, "n_kept": 0})
            g["n_raw"] += int(row.get("n_raw") or 0)
            g["n_kept"] += int(row.get("n_kept") or 0)
    pooled["gate_ablation_totals"] = gate_tot

    # Cross-section panel: one row per event with cell features
    panel_rows = []
    for c in complete:
        feat = c["features"]
        arr = c.get("_ssm_arr") or {}
        dp = np.asarray(arr.get("dp_pct", []), dtype=np.float64)
        ic = np.asarray(arr.get("i_c_arr", []), dtype=np.float64)
        dt = np.asarray(arr.get("dt_arr", []), dtype=np.float64)
        t0 = np.asarray(arr.get("ts_start", []), dtype=np.int64)
        for i in range(dp.size):
            panel_rows.append(
                {
                    "venue": c["venue"],
                    "symbol": c["symbol"],
                    "day": c["day"],
                    "dp_pct": float(dp[i]),
                    "i_c": float(ic[i]) if i < ic.size else float("nan"),
                    "dt_s": float(dt[i]) if i < dt.size else float("nan"),
                    "ts_start": int(t0[i]) if i < t0.size else 0,
                    "log_notional": feat["log_notional"],
                    "rv": feat["rv"],
                    "log_px": feat["log_px"],
                    "amihud": feat["amihud"],
                    "vpin": feat["vpin_mean"],
                    "notional": feat["notional"],
                }
            )
    # Cell-level panel for ex-ante (median severity per cell)
    cell_panel = []
    for c in complete:
        sg = c["ssm_gated"]
        feat = c["features"]
        cell_panel.append(
            {
                "venue": c["venue"],
                "symbol": c["symbol"],
                "day": c["day"],
                "n_events": sg.get("n_events", 0),
                "median_dp": (sg.get("dp") or {}).get("median"),
                "median_ic": (sg.get("i_c") or {}).get("median"),
                "median_dt": (sg.get("dt_s") or {}).get("median"),
                "mean_dp": (sg.get("dp") or {}).get("mean"),
                "log_notional": feat["log_notional"],
                "rv": feat["rv"],
                "log_px": feat["log_px"],
                "amihud": feat["amihud"],
                "vpin": feat["vpin_mean"],
                "notional": feat["notional"],
                "mean_px": feat["mean_px"],
                "n_trades": feat["n_trades"],
            }
        )

    # Quintiles by log_notional (size proxy for MCap/OI)
    if panel_rows:
        logn = np.array([r["log_notional"] for r in panel_rows], dtype=np.float64)
        dps = np.array([r["dp_pct"] for r in panel_rows], dtype=np.float64)
        ics = np.array([r["i_c"] for r in panel_rows], dtype=np.float64)
        dts = np.array([r["dt_s"] for r in panel_rows], dtype=np.float64)
        quintiles = {
            "by_log_notional_dp": _quintile_table(logn, dps),
            "by_log_notional_ic": _quintile_table(logn, ics),
            "by_log_notional_dt": _quintile_table(logn, dts),
            "by_rv_dp": _quintile_table(
                np.array([r["rv"] for r in panel_rows], dtype=np.float64), dps
            ),
            "by_vpin_dp": _quintile_table(
                np.array([r["vpin"] for r in panel_rows], dtype=np.float64), dps
            ),
        }
    else:
        quintiles = {}

    def _fit_y(y_key: str, rows: list[dict[str, Any]], *, interact_vpin: bool = False) -> dict[str, Any]:
        y = np.array([r[y_key] for r in rows], dtype=np.float64)
        cols = ["log_notional", "rv", "log_px", "amihud"]
        X = np.column_stack([np.array([r[c] for r in rows], dtype=np.float64) for c in cols])
        names = ["const"] + cols
        fit = nw_ols(y, X, add_const=True)
        out = {
            "y": y_key,
            "n": fit["n"],
            "r2": fit["r2"],
            "lags": fit["lags"],
            "coef": {
                names[i]: {"beta": float(fit["beta"][i]), "se": float(fit["se"][i]), "t": float(fit["t"][i])}
                for i in range(len(names))
                if i < len(fit["beta"])
            },
        }
        if interact_vpin:
            vpin = np.array([r["vpin"] for r in rows], dtype=np.float64)
            Xb = np.column_stack([X, vpin, X[:, 0] * vpin])  # + VPIN + logN×VPIN
            names2 = names + ["vpin", "logN_x_vpin"]
            fit2 = nw_ols(y, Xb, add_const=True)
            out["with_vpin_interaction"] = {
                "n": fit2["n"],
                "r2": fit2["r2"],
                "coef": {
                    names2[i]: {
                        "beta": float(fit2["beta"][i]),
                        "se": float(fit2["se"][i]),
                        "t": float(fit2["t"][i]),
                    }
                    for i in range(len(names2))
                    if i < len(fit2["beta"])
                },
            }
        return out

    ols_event = {}
    ols_cell = {}
    if len(panel_rows) >= 30:
        ols_event = {
            "dp": _fit_y("dp_pct", panel_rows, interact_vpin=True),
            "i_c": _fit_y("i_c", panel_rows),
            "dt_s": _fit_y("dt_s", panel_rows),
        }
    if len(cell_panel) >= 15:
        # only cells with events
        cp = [r for r in cell_panel if (r.get("n_events") or 0) > 0 and r.get("median_dp") is not None]
        if len(cp) >= 12:
            ols_cell = {
                "median_dp": _fit_y("median_dp", cp, interact_vpin=True),
                "median_ic": _fit_y("median_ic", cp),
                "median_dt": _fit_y("median_dt", cp),
            }

    # Ex-ante predictive: lag cell features by previous calendar day same venue×symbol
    by_key = {(c["venue"], c["symbol"], c["day"]): c for c in complete}
    pred_rows = []
    for c in complete:
        day = c["day"]
        # previous day string
        from datetime import datetime, timedelta

        d0 = datetime.strptime(day, "%Y-%m-%d") - timedelta(days=1)
        prev = d0.strftime("%Y-%m-%d")
        prev_c = by_key.get((c["venue"], c["symbol"], prev))
        if prev_c is None or not c["ssm_gated"].get("n_events"):
            continue
        med = (c["ssm_gated"].get("dp") or {}).get("median")
        if med is None:
            continue
        pf = prev_c["features"]
        pred_rows.append(
            {
                "dp_pct": float(med),
                "i_c": float((c["ssm_gated"].get("i_c") or {}).get("median") or np.nan),
                "dt_s": float((c["ssm_gated"].get("dt_s") or {}).get("median") or np.nan),
                "log_notional": pf["log_notional"],
                "rv": pf["rv"],
                "log_px": pf["log_px"],
                "amihud": pf["amihud"],
                "vpin": pf["vpin_mean"],
                "venue": c["venue"],
                "symbol": c["symbol"],
                "day": day,
            }
        )
    ols_exante = {}
    if len(pred_rows) >= 12:
        ols_exante = {
            "median_dp": _fit_y("dp_pct", pred_rows, interact_vpin=True),
            "n_pred_rows": len(pred_rows),
        }

    # Time-split falsifier on event-level OLS β(log_notional → dp)
    time_split = {}
    if panel_rows:
        ts_all = np.array([r["ts_start"] for r in panel_rows], dtype=np.int64)
        tr, te = time_split_mask(ts_all, train_frac=0.6)
        early = [r for r, m in zip(panel_rows, tr) if m]
        late = [r for r, m in zip(panel_rows, te) if m]
        if len(early) >= 20 and len(late) >= 20:
            fe = _fit_y("dp_pct", early)
            fl = _fit_y("dp_pct", late)
            be = fe["coef"].get("log_notional", {}).get("beta")
            bl = fl["coef"].get("log_notional", {}).get("beta")
            time_split = {
                "early_n": fe["n"],
                "late_n": fl["n"],
                "early_beta_logN": be,
                "late_beta_logN": bl,
                "early_r2": fe["r2"],
                "late_r2": fl["r2"],
                "sign_stable": (
                    be is not None
                    and bl is not None
                    and np.isfinite(be)
                    and np.isfinite(bl)
                    and (be * bl > 0)
                ),
            }

    # Multi-coin: ETH vs BTC mean severity
    by_sym: dict[str, list[float]] = {}
    for c in complete:
        med = (c["ssm_gated"].get("dp") or {}).get("median")
        if med is not None:
            by_sym.setdefault(c["symbol"], []).append(float(med))
    multi_coin = {
        sym: {"n_cells": len(v), "mean_median_dp": float(np.mean(v)), "median_of_medians": float(np.median(v))}
        for sym, v in by_sym.items()
        if v
    }

    # Venue breakdown
    by_venue: dict[str, Any] = {}
    for c in complete:
        v = c["venue"]
        b = by_venue.setdefault(
            v, {"n_cells": 0, "n_ssm_raw": 0, "n_ssm_gated": 0, "n_nanex": 0, "tob_cells": 0}
        )
        b["n_cells"] += 1
        b["n_ssm_raw"] += int(c["ssm_raw"].get("n_events") or 0)
        b["n_ssm_gated"] += int(c["ssm_gated"].get("n_events") or 0)
        b["n_nanex"] += int(c["nanex"].get("n_events") or 0)
        if (c.get("tob") or {}).get("n", 0) > 0:
            b["tob_cells"] += 1

    return {
        "pooled": pooled,
        "quintiles": quintiles,
        "ols_event": ols_event,
        "ols_cell": ols_cell,
        "ols_exante": ols_exante,
        "time_split": time_split,
        "multi_coin": multi_coin,
        "by_venue": by_venue,
        "n_panel_events": len(panel_rows),
        "n_pred_rows": len(pred_rows),
        "oi_proxy": "daily_notional_log (true OI unavailable)",
        "tob_ceiling": "tape markout always; tob_resilience only when quote stream present",
    }


def _make_figures(summary: dict[str, Any], cells: list[dict[str, Any]]) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG.mkdir(parents=True, exist_ok=True)
    figs = []
    pooled = summary["pooled"]

    # Fig 1: gate ablation kept counts
    gat = pooled.get("gate_ablation_totals") or {}
    if gat:
        labels = list(gat.keys())
        kept = [gat[k]["n_kept"] for k in labels]
        raw = [gat[k]["n_raw"] for k in labels]
        fig, ax = plt.subplots(figsize=(7, 4))
        x = np.arange(len(labels))
        ax.bar(x - 0.2, raw, 0.4, label="raw SSM", color="#888")
        ax.bar(x + 0.2, kept, 0.4, label="gated", color="#2a6")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=15)
        ax.set_ylabel("events")
        ax.set_title("SSM severity gate ablation (pooled)")
        ax.legend()
        p = FIG / "fig_severity_gate.png"
        _save_fig(p)
        figs.append(str(p.relative_to(OUT)))

    # Fig 2: ΔP distributions Nanex vs gated SSM
    fig, ax = plt.subplots(figsize=(7, 4))
    for src, color in (("nanex", "#c45"), ("ssm", "#258")):
        parts = []
        for c in cells:
            if not c.get("complete"):
                continue
            arr = c.get(f"_{src}_arr", {}).get("dp_pct")
            if arr is not None and len(arr):
                parts.append(np.asarray(arr, dtype=np.float64))
        if parts:
            a = np.concatenate(parts)
            a = a[np.isfinite(a) & (a < np.percentile(a, 99))]
            ax.hist(a, bins=40, alpha=0.55, label=src, color=color, density=True)
    ax.set_xlabel("ΔP (%)")
    ax.set_ylabel("density")
    ax.set_title("Severity ΔP: Nanex 30bps vs SSM gated")
    ax.legend()
    p = FIG / "fig_dp_hist.png"
    _save_fig(p)
    figs.append(str(p.relative_to(OUT)))

    # Fig 3: recovery class shares
    cl = pooled.get("ssm_class") or {}
    if cl.get("n_v_recovery") is not None:
        fig, ax = plt.subplots(figsize=(5, 4))
        vals = [cl["n_v_recovery"], cl["n_partial"], cl["n_continuation"]]
        ax.bar(["V-recovery", "partial", "continuation"], vals, color=["#2a6", "#ca5", "#c45"])
        ax.set_title("SSM gated recovery classes @5s")
        ax.set_ylabel("events")
        p = FIG / "fig_recovery_class.png"
        _save_fig(p)
        figs.append(str(p.relative_to(OUT)))

    # Fig 4: quintiles ΔP by size
    q = (summary.get("quintiles") or {}).get("by_log_notional_dp") or []
    if q:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.plot([r["q"] for r in q], [r["y_mean"] for r in q], "o-", color="#258")
        ax.set_xlabel("log(notional) quintile")
        ax.set_ylabel("mean |ΔP| (%)")
        ax.set_title("Cross-section: severity vs size proxy")
        p = FIG / "fig_quintile_size_dp.png"
        _save_fig(p)
        figs.append(str(p.relative_to(OUT)))

    # Fig 5: OLS coef forest for dp
    ols = (summary.get("ols_event") or {}).get("dp") or {}
    coef = ols.get("coef") or {}
    keys = [k for k in ("log_notional", "rv", "log_px", "amihud") if k in coef]
    if keys:
        fig, ax = plt.subplots(figsize=(6, 4))
        betas = [coef[k]["beta"] for k in keys]
        ses = [coef[k]["se"] for k in keys]
        y = np.arange(len(keys))
        ax.errorbar(betas, y, xerr=[1.96 * s for s in ses], fmt="o", color="#258")
        ax.axvline(0, color="#888", lw=0.8)
        ax.set_yticks(y)
        ax.set_yticklabels(keys)
        ax.set_xlabel("NW-OLS β (ΔP)")
        ax.set_title(f"Event-level NW-OLS (n={ols.get('n')}, R²={ols.get('r2'):.3f})" if ols.get("r2") else "NW-OLS")
        p = FIG / "fig_nw_ols_dp.png"
        _save_fig(p)
        figs.append(str(p.relative_to(OUT)))

    # Fig 6: multi-coin
    mc = summary.get("multi_coin") or {}
    if mc:
        fig, ax = plt.subplots(figsize=(5, 4))
        syms = list(mc.keys())
        ax.bar(syms, [mc[s]["mean_median_dp"] for s in syms], color="#258")
        ax.set_ylabel("mean cell median ΔP (%)")
        ax.set_title("Multi-coin severity (gated SSM)")
        p = FIG / "fig_multi_coin.png"
        _save_fig(p)
        figs.append(str(p.relative_to(OUT)))

    return figs


def _write_report(summary: dict[str, Any], figs: list[str]) -> None:
    p = summary["pooled"]
    lines = [
        "# Phase 3a — crash_stats + cross_section",
        "",
        f"Generated: {summary['generated_at']}",
        f"Days: {summary['days']}",
        f"Symbols: {summary['symbols']} · Venues: {summary['venues']}",
        f"Complete cells: **{p['n_cells']}**",
        "",
        "## Severity gate",
        "",
        f"Primary: |ΔP|≥10 bps, i_c≥5 on SSM z*={Z_STAR}.",
        f"Raw SSM events: **{p['n_ssm_raw']}** → gated: **{p['n_ssm_gated']}** · Nanex 30bps: **{p['n_nanex']}**",
        f"Gate ablation: `{p.get('gate_ablation_totals')}`",
        "",
        "## Crash stats (gated SSM)",
        "",
        f"- ΔP %: {p['ssm_dp']}",
        f"- i_c: {p['ssm_ic']}",
        f"- Δt s: {p['ssm_dt']}",
        f"- recovery@5s: {p['ssm_recov']}",
        f"- class: {p['ssm_class']}",
        f"- markout (tape) mean bps: {p.get('ssm_markout_mean_bps')}",
        f"- spearman(dt, |mo5|) cell-weighted: {p.get('spearman_dt_mo5_cell_mean')}",
        "",
        "## Cross-section",
        "",
        f"- OI proxy: {summary.get('oi_proxy')}",
        f"- Event OLS ΔP: {summary.get('ols_event', {}).get('dp')}",
        f"- Ex-ante OLS: {summary.get('ols_exante')}",
        f"- Time-split: {summary.get('time_split')}",
        f"- Multi-coin: {summary.get('multi_coin')}",
        f"- By venue: {summary.get('by_venue')}",
        "",
        "## TOB ceiling",
        "",
        summary.get("tob_ceiling", ""),
        "",
        "## Figures",
        "",
    ]
    for f in figs:
        lines.append(f"- `{f}`")
    (OUT / "phase3a_REPORT.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", nargs="*", default=DEFAULT_DAYS)
    ap.add_argument("--symbols", nargs="*", default=DEFAULT_SYMBOLS)
    ap.add_argument("--venues", nargs="*", default=list(CORE_VENUES))
    ap.add_argument("--max-files", type=int, default=24)
    ap.add_argument("--fast", action="store_true", help="2 days × ETH only smoke")
    args = ap.parse_args()
    if args.fast:
        args.days = DEFAULT_DAYS[:2]
        args.symbols = ["ETH"]

    ensure_env()
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    log_path = OUT / "run.log"
    log_f = log_path.open("w")

    cells: list[dict[str, Any]] = []
    for day in args.days:
        for symbol in args.symbols:
            for venue in args.venues:
                msg = f"[run] {venue} {symbol} {day}"
                print(msg, flush=True)
                log_f.write(msg + "\n")
                try:
                    cell = _process_cell(venue, symbol, day, max_files=args.max_files)
                except Exception as exc:  # noqa: BLE001
                    cell = {
                        "venue": venue,
                        "symbol": symbol,
                        "day": day,
                        "complete": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                if cell:
                    cells.append(cell)
                    n_g = (cell.get("ssm_gated") or {}).get("n_events")
                    n_r = (cell.get("ssm_raw") or {}).get("n_events")
                    line = (
                        f"  -> complete={cell.get('complete')} ssm_raw={n_r} "
                        f"ssm_gated={n_g} nanex={(cell.get('nanex') or {}).get('n_events')} "
                        f"tob={(cell.get('tob') or {}).get('n')}"
                    )
                    print(line, flush=True)
                    log_f.write(line + "\n")
    log_f.close()

    # Strip private arrays for JSON rows (keep in memory for pooling)
    rows_public = []
    for c in cells:
        pub = {k: v for k, v in c.items() if not k.startswith("_")}
        rows_public.append(pub)

    summary = _pool_and_xsec(cells)
    summary.update(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "days": list(args.days),
            "symbols": list(args.symbols),
            "venues": list(args.venues),
            "z_star": Z_STAR,
            "gate_primary": GATE_PRIMARY,
            "nanex_pct": NANEX_PCT,
            "recovery_horizon_s": RECOVERY_H_S,
        }
    )
    figs = _make_figures(summary, cells)
    summary["figures"] = figs

    (OUT / "phase3a_rows.json").write_text(json.dumps(_jsonable(rows_public), indent=2))
    (OUT / "phase3a_summary.json").write_text(json.dumps(_jsonable(summary), indent=2))
    _write_report(summary, figs)
    print(
        f"[done] cells={summary['pooled']['n_cells']} "
        f"ssm_raw={summary['pooled']['n_ssm_raw']} "
        f"ssm_gated={summary['pooled']['n_ssm_gated']} "
        f"nanex={summary['pooled']['n_nanex']} → {OUT}",
        flush=True,
    )


if __name__ == "__main__":
    main()
