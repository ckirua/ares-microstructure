from __future__ import annotations
#!/usr/bin/env python3
"""Horizon / sampling-clock sweep for mini-flash SSM + kill-ladder risk overlay.

Clarifies clocks and answers: can detection / intensity / kill-ladder work at
trade-count bars N∈{100,300,900,3000,9000}, volume clocks, calendar bars
(1s/5s/1m), vs pure event-time SSM?

**No live orders.** ClickHouse MCP banned. Quant bar: bootstrap CIs + early/late.

Outputs under ``out/``: summary.json, EXP_REPORT.md, HORIZON_RECOMMENDATION.md, figs/.
"""

import os

import argparse
import json
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

LAB = Path(__file__).resolve().parent
APP = LAB.parent
BOOK = APP.parent
ROOT = BOOK.parents[2]
STARTARB = Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb'))
WAREHOUSE_SRC = Path(os.environ.get('WAREHOUSE_SRC') or ((Path(os.environ.get('WAREHOUSE_ROOT') or (Path.home() / 'lab' / 'lab-n2070' / 'warehouse')) / 'src')))
OUT = LAB / "out"
FIG = OUT / "figs"
SCRIPTS_APP = APP / "scripts"

PIN_USABLE = [
    "2026-08-28",
    "2026-08-29",
    "2026-08-30",
    "2026-08-31",
    "2026-09-01",
    "2026-09-02",
    "2026-09-03",
    "2026-09-04",
    "2026-09-05",
    "2026-09-06",
    "2026-09-07",
    "2026-09-08",
    "2026-09-09",
    "2026-09-10",
    "2026-09-11",
    "2026-09-14",
    "2026-09-15",
    "2026-09-16",
    "2026-09-17",
    "2026-09-18",
    "2026-09-19",
    "2026-09-20",
    "2026-09-21",
    "2026-09-22",
    "2026-09-25",
    "2026-09-26",
    "2026-09-27",
    "2026-09-30",
]

for p in (
    str(LAB),
    str(APP),
    str(SCRIPTS_APP),
    str(BOOK / "scripts"),
    str(ROOT),
    str(STARTARB / "src"),
    str(WAREHOUSE_SRC),
):
    if p not in sys.path:
        sys.path.insert(0, p)

from _common import (  # noqa: E402
    FRICTION_BPS,
    GATE_PRIMARY,
    Z_STAR,
    assign_ladder_tiers,
    early_late_by_day,
    effect_delta_ci,
    ladder_tier,
    rolling_gated_intensity,
    save_fig,
    save_json,
)
from _data import ensure_env, load_day_trades  # noqa: E402
from research.lib.continuous import amihud_illiquidity  # noqa: E402
from research.lib.crash import (  # noqa: E402
    classify_recovery,
    detect_ssm_events,
    kalman_ssm_filter,
    mc_garch_bar_vol,
    nanex_detect,
    recovery_fraction,
    severity_gate,
    sigma_process_meas,
)
from research.lib.stats import bootstrap_ci, spearman_r  # noqa: E402

NS = 1_000_000_000
FIRE = frozenset({"widen", "size_cap", "halt"})
VENUE = "hyperliquid"
SYMBOL = "ETH"

TRADE_NS = (100, 300, 900, 3000, 9000)
CAL_S = (1.0, 5.0, 60.0)
# Volume-clock targets ≈ N-trade notionals at ~$30–50/print → round buckets
VOL_USD = (10_000.0, 50_000.0, 200_000.0, 500_000.0)
# Policy intensity windows (wall-clock + trade-count) on event-time detection
INTENSITY_WINDOWS = [
    ("wall_30s", "wall", 30.0),
    ("wall_60s", "wall", 60.0),  # desk default
    ("wall_300s", "wall", 300.0),
    ("trade_100", "trade", 100.0),
    ("trade_300", "trade", 300.0),
    ("trade_900", "trade", 900.0),
    ("trade_3000", "trade", 3000.0),
    ("trade_9000", "trade", 9000.0),
]


# ---------------------------------------------------------------------------
# Resamplers
# ---------------------------------------------------------------------------


def resample_last_n_trades(
    ts: np.ndarray, px: np.ndarray, qty: np.ndarray, n: int
) -> dict[str, np.ndarray]:
    """Keep last print of every N trades (trade-count bar close)."""
    n = int(n)
    if n < 1 or ts.size < n:
        return {"ts": ts[:0], "px": px[:0], "qty": qty[:0], "n_src": np.zeros(0, dtype=np.int64)}
    idx = np.arange(n - 1, ts.size, n, dtype=np.int64)
    return {
        "ts": ts[idx],
        "px": px[idx],
        "qty": qty[idx],
        "n_src": np.full(idx.size, n, dtype=np.int64),
    }


def resample_ohlc_extreme(
    ts: np.ndarray, px: np.ndarray, qty: np.ndarray, n: int
) -> dict[str, np.ndarray]:
    """Per N-trade bar: open → intra-bar extreme → close (preserves excursion)."""
    n = int(n)
    outs_t: list[int] = []
    outs_p: list[float] = []
    outs_q: list[float] = []
    outs_src: list[int] = []
    for i in range(0, int(ts.size) - n + 1, n):
        seg = px[i : i + n]
        tseg = ts[i : i + n]
        qseg = qty[i : i + n]
        if not np.isfinite(seg).any() or float(seg[0]) <= 0:
            continue
        o = float(seg[0])
        c = float(seg[-1])
        hi_i = int(np.nanargmax(seg))
        lo_i = int(np.nanargmin(seg))
        hi = float(seg[hi_i])
        lo = float(seg[lo_i])
        qsum = float(np.nansum(qseg))
        if abs(hi - o) >= abs(o - lo):
            outs_t.extend([int(tseg[0]), int(tseg[hi_i]), int(tseg[-1])])
            outs_p.extend([o, hi, c])
        else:
            outs_t.extend([int(tseg[0]), int(tseg[lo_i]), int(tseg[-1])])
            outs_p.extend([o, lo, c])
        outs_q.extend([qsum / 3.0] * 3)
        outs_src.extend([n] * 3)
    return {
        "ts": np.asarray(outs_t, dtype=np.int64),
        "px": np.asarray(outs_p, dtype=np.float64),
        "qty": np.asarray(outs_q, dtype=np.float64),
        "n_src": np.asarray(outs_src, dtype=np.int64),
    }


def resample_calendar(
    ts: np.ndarray, px: np.ndarray, qty: np.ndarray, bar_s: float
) -> dict[str, np.ndarray]:
    """Last print per calendar bar of width ``bar_s`` seconds."""
    if ts.size == 0:
        return {"ts": ts, "px": px, "qty": qty, "n_src": np.zeros(0, dtype=np.int64)}
    w = int(float(bar_s) * NS)
    bins = (ts - int(ts[0])) // max(w, 1)
    # last index per bin
    order = np.argsort(bins, kind="mergesort")
    bins_s = bins[order]
    # find last occurrence of each bin
    change = np.ones(bins_s.size, dtype=bool)
    change[:-1] = bins_s[:-1] != bins_s[1:]
    last_pos = order[change]
    last_pos = np.sort(last_pos)
    # trade count per bar via unique counts
    _, counts = np.unique(bins, return_counts=True)
    # align counts to last_pos order of unique bins sorted by time
    uniq = bins[last_pos]
    # map bin → count
    u_all, c_all = np.unique(bins, return_counts=True)
    cmap = {int(u): int(c) for u, c in zip(u_all, c_all)}
    n_src = np.asarray([cmap.get(int(u), 1) for u in uniq], dtype=np.int64)
    return {
        "ts": ts[last_pos],
        "px": px[last_pos],
        "qty": qty[last_pos],
        "n_src": n_src,
    }


def resample_volume(
    ts: np.ndarray, px: np.ndarray, qty: np.ndarray, usd: float
) -> dict[str, np.ndarray]:
    """Close each time cumulative USD notional crosses ``usd``."""
    notion = np.asarray(px, dtype=np.float64) * np.asarray(qty, dtype=np.float64)
    notion = np.where(np.isfinite(notion) & (notion > 0), notion, 0.0)
    cum = np.cumsum(notion)
    if cum.size == 0 or float(cum[-1]) < float(usd):
        return {"ts": ts[:0], "px": px[:0], "qty": qty[:0], "n_src": np.zeros(0, dtype=np.int64)}
    targets = np.arange(float(usd), float(cum[-1]) + 1e-9, float(usd))
    idx = np.searchsorted(cum, targets, side="left")
    idx = idx[idx < ts.size]
    if idx.size == 0:
        return {"ts": ts[:0], "px": px[:0], "qty": qty[:0], "n_src": np.zeros(0, dtype=np.int64)}
    # unique increasing
    keep = np.ones(idx.size, dtype=bool)
    keep[1:] = idx[1:] > idx[:-1]
    idx = idx[keep]
    n_src = np.diff(np.concatenate([[0], idx + 1]))
    return {
        "ts": ts[idx],
        "px": px[idx],
        "qty": qty[idx],
        "n_src": n_src.astype(np.int64),
    }


# ---------------------------------------------------------------------------
# Detection + outcomes (markout always on full tape)
# ---------------------------------------------------------------------------


def _per_event_markout_on_tape(
    full_ts: np.ndarray,
    full_px: np.ndarray,
    event_ts_end: np.ndarray,
    direction: np.ndarray,
    horizons_s: tuple[float, ...] = (1.0, 5.0),
) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    for h in horizons_s:
        h_ns = int(h * NS)
        arr = np.full(event_ts_end.shape, np.nan, dtype=np.float64)
        for k in range(event_ts_end.size):
            t0 = int(event_ts_end[k])
            d = int(direction[k])
            if d == 0:
                continue
            b = int(np.searchsorted(full_ts, t0, side="right") - 1)
            if b < 0 or b >= full_px.size or full_px[b] <= 0:
                continue
            j = int(np.searchsorted(full_ts, t0 + h_ns, side="right") - 1)
            if j <= b or j >= full_px.size or not np.isfinite(full_px[j]):
                continue
            arr[k] = float(d * (full_px[j] - full_px[b]) / full_px[b] * 1e4)
        out[f"mo_{h:g}s"] = arr
    return out


def run_ssm_on_series(
    ts: np.ndarray,
    px: np.ndarray,
    *,
    min_i_c: int,
    z_star: float = Z_STAR,
) -> dict[str, Any]:
    if ts.size < 30 or not np.isfinite(px).any():
        return {"skip": "thin", "n_bars": int(ts.size), "raw_n": 0, "gated_n": 0}
    t0 = time.perf_counter()
    log_px = np.log(np.where(px > 0, px, np.nan))
    mcg = mc_garch_bar_vol(ts, px)
    sig = sigma_process_meas(ts, mcg, sigma_m_frac=1.0, log_px=log_px)
    filt = kalman_ssm_filter(ts, px, sig["sigma_p2_dt"], sig["sigma_m2"])
    raw = detect_ssm_events(ts, px, filt, z_star=z_star)
    gated = severity_gate(raw, min_dp_pct=GATE_PRIMARY["min_dp_pct"], min_i_c=int(min_i_c))
    elapsed = time.perf_counter() - t0
    return {
        "n_bars": int(ts.size),
        "raw_n": int(raw["n_events"]),
        "gated_n": int(gated["n_events"]),
        "raw": raw,
        "gated": gated,
        "filt_z": filt["z_score"],
        "sec": float(elapsed),
        "min_i_c": int(min_i_c),
    }


def attach_outcomes(
    det: dict[str, Any],
    *,
    full_ts: np.ndarray,
    full_px: np.ndarray,
    intensity_window_s: float = 60.0,
) -> dict[str, Any]:
    if det.get("skip") or int(det.get("gated_n", 0)) == 0:
        return {
            **{k: det.get(k) for k in ("n_bars", "raw_n", "gated_n", "sec", "min_i_c", "skip")},
            "events": [],
            "ladder_breaks": {},
        }
    g = det["gated"]
    intens = rolling_gated_intensity(g["ts_start"], window_s=float(intensity_window_s))
    # map bar-event timestamps → indices on the full trade tape for recovery/markout
    n_full = int(full_ts.size)
    start_i = np.clip(np.searchsorted(full_ts, g["ts_start"], side="left"), 0, max(n_full - 1, 0))
    end_i = np.clip(np.searchsorted(full_ts, g["ts_end"], side="right") - 1, 0, max(n_full - 1, 0))
    end_i = np.maximum(end_i, start_i)
    rec = recovery_fraction(full_ts, full_px, start_i, end_i, g["direction"], horizon_s=5.0)
    cls = classify_recovery(rec)
    mo = _per_event_markout_on_tape(full_ts, full_px, g["ts_end"], g["direction"])
    flat = []
    for i in range(int(g["n_events"])):
        flat.append(
            {
                "ts_start": int(g["ts_start"][i]),
                "ts_end": int(g["ts_end"][i]),
                "dp_pct": float(g["dp_pct"][i]),
                "i_c": int(g["i_c"][i]),
                "z_peak": float(g["z_peak"][i]),
                "direction": int(g["direction"][i]),
                "intensity_60s": int(intens[i]),
                "nanex_overlap": False,
                "recovery": float(rec[i]) if i < rec.size else float("nan"),
                "recovery_label": str(cls["labels"][i]) if i < len(cls["labels"]) else "unknown",
                "mo_1s": float(mo["mo_1s"][i]),
                "mo_5s": float(mo["mo_5s"][i]),
            }
        )
    breaks = assign_ladder_tiers(flat) if flat else {}
    for e in flat:
        e["tier"] = str(e.get("tier", "observe"))
        e["fire"] = e["tier"] in FIRE
    return {
        "n_bars": det["n_bars"],
        "raw_n": det["raw_n"],
        "gated_n": int(len(flat)),
        "sec": det["sec"],
        "min_i_c": det["min_i_c"],
        "events": flat,
        "ladder_breaks": breaks,
    }


def day_amihud(ts: np.ndarray, px: np.ndarray, qty: np.ndarray, bar_s: float = 60.0) -> float:
    """Amihud on 1m calendar closes (desk proxy)."""
    bar = resample_calendar(ts, px, qty, bar_s)
    p = bar["px"]
    if p.size < 10:
        return float("nan")
    r = np.diff(np.log(np.where(p > 0, p, np.nan)))
    # dollar volume per bar: approximate via mean qty * px of close (coarse)
    # better: sum notionals in each calendar bin
    w = int(bar_s * NS)
    bins = (ts - int(ts[0])) // max(w, 1)
    notion = px * qty
    notion = np.where(np.isfinite(notion) & (notion > 0), notion, 0.0)
    # align to unique sorted bins matching resample_calendar lasts
    u = np.unique(bins)
    dvol = np.zeros(u.size, dtype=np.float64)
    for i, b in enumerate(u):
        dvol[i] = float(np.sum(notion[bins == b]))
    # returns length = n_bars-1; use dvol[1:]
    if dvol.size != p.size:
        # fallback equal length truncate
        m = min(dvol.size, p.size)
        dvol, p = dvol[:m], p[:m]
        r = np.diff(np.log(np.where(p > 0, p, np.nan)))
    am = amihud_illiquidity(r, dvol[1 : 1 + r.size] if dvol.size > 1 else dvol)
    return float(am.get("illiq", float("nan")))


def diurnal_hour_share(events: list[dict[str, Any]]) -> dict[str, float]:
    if not events:
        return {}
    hours = []
    for e in events:
        # UTC hour from ns
        h = int((int(e["ts_end"]) // NS) % 86400) // 3600
        hours.append(h)
    harr = np.asarray(hours, dtype=np.int64)
    # peak bucket from desk memo ~UTC-12 for this cohort
    peak = ((harr >= 10) & (harr <= 14)).mean()
    off = ((harr < 6) | (harr >= 20)).mean()
    return {
        "share_utc_10_14": float(peak),
        "share_utc_off": float(off),
        "n": float(len(hours)),
    }


# ---------------------------------------------------------------------------
# Per-day worker
# ---------------------------------------------------------------------------


def process_day(day: str) -> dict[str, Any]:
    ensure_env()
    rec = load_day_trades(VENUE, SYMBOL, day, quiet=True)
    tape = rec["tape"]
    ts = np.asarray(tape["ts"], dtype=np.int64)
    px = np.asarray(tape["px"], dtype=np.float64)
    qty = np.asarray(tape["qty"], dtype=np.float64)
    complete = bool(rec.get("completeness", {}).get("complete"))
    out: dict[str, Any] = {
        "day": day,
        "complete": complete,
        "n_trades": int(ts.size),
        "ok": False,
    }
    if ts.size < 500 or not complete:
        out["skip"] = "thin_or_incomplete"
        return out

    span_s = float(ts[-1] - ts[0]) / NS if ts.size > 1 else float("nan")
    dt = np.diff(ts) / NS
    pos = dt[dt > 0]
    med_dt = float(np.median(pos)) if pos.size else float("nan")
    out.update(
        {
            "span_s": span_s,
            "trades_per_s": float(ts.size / span_s) if span_s and span_s > 0 else float("nan"),
            "med_dt_pos_s": med_dt,
            "amihud_1m": day_amihud(ts, px, qty, 60.0),
        }
    )

    clocks: list[tuple[str, dict[str, np.ndarray], int]] = []
    # event-time baseline: min_i_c=5 (primary gate)
    clocks.append(
        (
            "event",
            {"ts": ts, "px": px, "qty": qty, "n_src": np.ones(ts.size, dtype=np.int64)},
            5,
        )
    )
    for n in TRADE_NS:
        clocks.append((f"trade_last_{n}", resample_last_n_trades(ts, px, qty, n), 1))
        clocks.append((f"trade_ohlc_{n}", resample_ohlc_extreme(ts, px, qty, n), 1))
    for sec in CAL_S:
        label = f"cal_{int(sec)}s" if sec >= 1 else f"cal_{sec}s"
        clocks.append((label, resample_calendar(ts, px, qty, sec), 1))
    for usd in VOL_USD:
        clocks.append((f"vol_{int(usd)}", resample_volume(ts, px, qty, usd), 1))

    clock_rows: dict[str, Any] = {}
    for name, series, min_ic in clocks:
        if series["ts"].size < 20:
            clock_rows[name] = {
                "n_bars": int(series["ts"].size),
                "raw_n": 0,
                "gated_n": 0,
                "sec": 0.0,
                "events": [],
                "skip": "too_few_bars",
                "med_bar_s": float("nan"),
            }
            continue
        # wall-time per bar
        bts = series["ts"]
        if bts.size > 1:
            med_bar = float(np.median(np.diff(bts.astype(np.float64)) / NS))
        else:
            med_bar = float("nan")
        det = run_ssm_on_series(series["ts"], series["px"], min_i_c=min_ic)
        packed = attach_outcomes(det, full_ts=ts, full_px=px, intensity_window_s=60.0)
        packed["med_bar_s"] = med_bar
        packed["clock"] = name
        clock_rows[name] = packed

    # Policy / intensity sweep on event-time detection
    event_pack = clock_rows.get("event") or {}
    policy_rows: dict[str, Any] = {}
    if int(event_pack.get("gated_n", 0)) > 0:
        # rebuild gated arrays from events list
        evs = event_pack["events"]
        # Need trade indices for trade-count intensity
        # Map event ts_start → trade index on full tape
        ev_start_i = np.asarray(
            [int(np.searchsorted(ts, e["ts_start"], side="left")) for e in evs],
            dtype=np.int64,
        )
        for pname, kind, val in INTENSITY_WINDOWS:
            if kind == "wall":
                intens = rolling_gated_intensity(
                    np.asarray([e["ts_start"] for e in evs], dtype=np.int64),
                    window_s=float(val),
                )
            else:
                # count gated events whose start_i in (i-N, i]
                intens = np.zeros(len(evs), dtype=np.int64)
                N = int(val)
                for i, si in enumerate(ev_start_i):
                    intens[i] = int(np.sum((ev_start_i <= si) & (ev_start_i > si - N)))
            # re-tier with this intensity
            flat = []
            for i, e in enumerate(evs):
                flat.append(
                    {
                        "z_peak": e["z_peak"],
                        "intensity_60s": int(intens[i]),
                        "nanex_overlap": False,
                        "dp_pct": e["dp_pct"],
                        "mo_5s": e["mo_5s"],
                        "recovery_label": e["recovery_label"],
                        "ts_start": e["ts_start"],
                        "day": day,
                    }
                )
            breaks = assign_ladder_tiers(flat)
            for e in flat:
                e["tier"] = str(e.get("tier", "observe"))
                e["fire"] = e["tier"] in FIRE
            policy_rows[pname] = {
                "intensity_kind": kind,
                "intensity_val": float(val),
                "ladder_breaks": breaks,
                "events": flat,
                "n_fire": int(sum(1 for e in flat if e["fire"])),
                "n_obs": int(sum(1 for e in flat if not e["fire"])),
            }

    # Nanex on event tape (reference)
    nx = nanex_detect(ts, px, min_trades=10, max_window_s=1.5, min_pct=0.003, use_trade_count=True)
    out.update(
        {
            "ok": True,
            "clocks": clock_rows,
            "policy": policy_rows,
            "nanex_n": int(nx["n_events"]),
        }
    )
    return out


# ---------------------------------------------------------------------------
# Aggregation / scoreboard
# ---------------------------------------------------------------------------


def _fire_obs_mo(events: list[dict[str, Any]]) -> dict[str, Any]:
    fire = np.asarray(
        [abs(float(e["mo_5s"])) for e in events if e.get("fire") and np.isfinite(e.get("mo_5s", np.nan))],
        dtype=np.float64,
    )
    obs = np.asarray(
        [
            abs(float(e["mo_5s"]))
            for e in events
            if (not e.get("fire")) and np.isfinite(e.get("mo_5s", np.nan))
        ],
        dtype=np.float64,
    )
    delta = effect_delta_ci(fire, obs, n_boot=800, seed=41)
    v_fire = [
        e
        for e in events
        if e.get("fire") and str(e.get("recovery_label", "")).lower().startswith("v")
    ]
    n_fire = sum(1 for e in events if e.get("fire"))
    return {
        "delta_abs_mo5": delta,
        "n_fire": int(n_fire),
        "n_obs": int(len(events) - n_fire),
        "v_share_fire": float(len(v_fire) / n_fire) if n_fire else float("nan"),
        "crash_rate_per_day": float("nan"),  # filled by caller
    }


def pool_clock(day_rows: list[dict[str, Any]], clock: str) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    secs: list[float] = []
    bars: list[int] = []
    raws: list[int] = []
    gateds: list[int] = []
    med_bars: list[float] = []
    days_ok: list[str] = []
    for row in day_rows:
        if not row.get("ok"):
            continue
        c = (row.get("clocks") or {}).get(clock)
        if not c:
            continue
        days_ok.append(row["day"])
        secs.append(float(c.get("sec") or 0.0))
        bars.append(int(c.get("n_bars") or 0))
        raws.append(int(c.get("raw_n") or 0))
        gateds.append(int(c.get("gated_n") or 0))
        if np.isfinite(c.get("med_bar_s", np.nan)):
            med_bars.append(float(c["med_bar_s"]))
        for e in c.get("events") or []:
            events.append({**e, "day": row["day"]})
    early, late = early_late_by_day(days_ok)
    score = _fire_obs_mo(events) if events else {
        "delta_abs_mo5": {
            "n_treat": 0,
            "n_control": 0,
            "delta": float("nan"),
            "lo": float("nan"),
            "hi": float("nan"),
        },
        "n_fire": 0,
        "n_obs": 0,
        "v_share_fire": float("nan"),
    }
    early_ev = [e for e in events if e["day"] in early]
    late_ev = [e for e in events if e["day"] in late]
    d_early = _fire_obs_mo(early_ev)["delta_abs_mo5"] if early_ev else {"delta": float("nan")}
    d_late = _fire_obs_mo(late_ev)["delta_abs_mo5"] if late_ev else {"delta": float("nan")}
    de = d_early.get("delta", float("nan"))
    dl = d_late.get("delta", float("nan"))
    sign_stable = bool(
        np.isfinite(de) and np.isfinite(dl) and ((de > 0 and dl > 0) or (de < 0 and dl < 0))
    )
    delta = score["delta_abs_mo5"]
    ci_clears = bool(
        np.isfinite(delta.get("delta", np.nan))
        and delta["delta"] > FRICTION_BPS
        and delta.get("lo", -1) > 0
    )
    n_days = max(len(days_ok), 1)
    verdict = "Kill"
    if int(score["n_fire"]) < 20 and sum(gateds) < 20:
        verdict = "Kill" if sum(gateds) == 0 else "Hold"
        why = "underpowered or zero gated crashes"
    elif ci_clears and sign_stable:
        verdict = "Promote"
        why = "Δ|mo| fire−obs CI>0, >friction, early/late sign-stable"
    elif np.isfinite(delta.get("delta", np.nan)) and delta["delta"] > 0 and sign_stable:
        verdict = "Hold"
        why = "direction OK but CI/friction bar not cleared"
    elif sum(gateds) > 0:
        verdict = "Hold"
        why = "detection survives; kill-ladder separation weak"
    else:
        why = "no gated events — clock too coarse for mini-flash SSM"

    return {
        "clock": clock,
        "n_days": len(days_ok),
        "n_gated": int(sum(gateds)),
        "n_raw": int(sum(raws)),
        "gated_per_day": float(sum(gateds) / n_days),
        "raw_per_day": float(sum(raws) / n_days),
        "mean_n_bars": float(np.mean(bars)) if bars else float("nan"),
        "med_bar_s": float(np.median(med_bars)) if med_bars else float("nan"),
        "mean_sec_per_day": float(np.mean(secs)) if secs else float("nan"),
        "n_fire": score["n_fire"],
        "n_obs": score["n_obs"],
        "v_share_fire": score["v_share_fire"],
        "delta_abs_mo5": delta,
        "delta_early": float(de) if np.isfinite(de) else None,
        "delta_late": float(dl) if np.isfinite(dl) else None,
        "sign_stable_early_late": sign_stable,
        "ci_clears_friction": ci_clears,
        "verdict": verdict,
        "why": why,
        "diurnal": diurnal_hour_share(events),
    }


def pool_policy(day_rows: list[dict[str, Any]], pname: str) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    days_ok: list[str] = []
    for row in day_rows:
        if not row.get("ok"):
            continue
        p = (row.get("policy") or {}).get(pname)
        if not p:
            continue
        days_ok.append(row["day"])
        for e in p.get("events") or []:
            events.append({**e, "day": row["day"]})
    score = _fire_obs_mo(events)
    early, late = early_late_by_day(days_ok)
    d_early = _fire_obs_mo([e for e in events if e["day"] in early])["delta_abs_mo5"]
    d_late = _fire_obs_mo([e for e in events if e["day"] in late])["delta_abs_mo5"]
    de, dl = d_early.get("delta", float("nan")), d_late.get("delta", float("nan"))
    sign_stable = bool(
        np.isfinite(de) and np.isfinite(dl) and ((de > 0 and dl > 0) or (de < 0 and dl < 0))
    )
    delta = score["delta_abs_mo5"]
    ci_clears = bool(
        np.isfinite(delta.get("delta", np.nan))
        and delta["delta"] > FRICTION_BPS
        and delta.get("lo", -1) > 0
    )
    if ci_clears and sign_stable:
        verdict, why = "Promote", "intensity clock preserves fire−obs separation"
    elif np.isfinite(delta.get("delta", np.nan)) and delta["delta"] > 0:
        verdict, why = "Hold", "positive Δ but CI/split soft"
    else:
        verdict, why = "Kill", "intensity clock destroys ladder usefulness"
    meta = next(
        (
            (row.get("policy") or {}).get(pname)
            for row in day_rows
            if row.get("ok") and (row.get("policy") or {}).get(pname)
        ),
        {},
    )
    return {
        "policy": pname,
        "intensity_kind": meta.get("intensity_kind"),
        "intensity_val": meta.get("intensity_val"),
        "n_days": len(days_ok),
        "n_events": len(events),
        "n_fire": score["n_fire"],
        "n_obs": score["n_obs"],
        "v_share_fire": score["v_share_fire"],
        "delta_abs_mo5": delta,
        "delta_early": float(de) if np.isfinite(de) else None,
        "delta_late": float(dl) if np.isfinite(dl) else None,
        "sign_stable_early_late": sign_stable,
        "ci_clears_friction": ci_clears,
        "verdict": verdict,
        "why": why,
    }


def liquidity_slice(day_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Does optimal detection clock shift with Amihud / diurnal / activity?"""
    ok = [r for r in day_rows if r.get("ok")]
    if len(ok) < 6:
        return {"n": len(ok), "note": "underpowered for terciles"}
    am = np.asarray([r.get("amihud_1m", np.nan) for r in ok], dtype=np.float64)
    tps = np.asarray([r.get("trades_per_s", np.nan) for r in ok], dtype=np.float64)
    # event gated per day
    g_event = np.asarray(
        [(r.get("clocks") or {}).get("event", {}).get("gated_n", 0) for r in ok],
        dtype=np.float64,
    )
    g_cal1 = np.asarray(
        [(r.get("clocks") or {}).get("cal_1s", {}).get("gated_n", 0) for r in ok],
        dtype=np.float64,
    )
    g_cal5 = np.asarray(
        [(r.get("clocks") or {}).get("cal_5s", {}).get("gated_n", 0) for r in ok],
        dtype=np.float64,
    )
    g_t300 = np.asarray(
        [(r.get("clocks") or {}).get("trade_last_300", {}).get("gated_n", 0) for r in ok],
        dtype=np.float64,
    )
    g_t9000 = np.asarray(
        [(r.get("clocks") or {}).get("trade_last_9000", {}).get("gated_n", 0) for r in ok],
        dtype=np.float64,
    )

    def _tercile_means(x: np.ndarray, y: np.ndarray) -> dict[str, Any]:
        m = np.isfinite(x) & np.isfinite(y)
        xx, yy = x[m], y[m]
        if xx.size < 6:
            return {"n": int(xx.size)}
        q1, q2 = np.nanpercentile(xx, [33.333, 66.666])
        lo, mid, hi = yy[xx <= q1], yy[(xx > q1) & (xx <= q2)], yy[xx > q2]
        return {
            "n": int(xx.size),
            "lo_mean": float(np.mean(lo)) if lo.size else float("nan"),
            "mid_mean": float(np.mean(mid)) if mid.size else float("nan"),
            "hi_mean": float(np.mean(hi)) if hi.size else float("nan"),
            "spearman_x_y": float(spearman_r(xx, yy)),
        }

    # retention ratio cal_1s / event by Amihud tercile
    ret = np.where(g_event > 0, g_cal1 / np.maximum(g_event, 1), np.nan)
    return {
        "n_days": len(ok),
        "amihud_vs_event_gated": _tercile_means(am, g_event),
        "amihud_vs_cal1_retention": _tercile_means(am, ret),
        "activity_vs_event_gated": _tercile_means(tps, g_event),
        "amihud_vs_trade300_gated": _tercile_means(am, g_t300),
        "mean_gated": {
            "event": float(np.mean(g_event)),
            "cal_1s": float(np.mean(g_cal1)),
            "cal_5s": float(np.mean(g_cal5)),
            "trade_last_300": float(np.mean(g_t300)),
            "trade_last_9000": float(np.mean(g_t9000)),
        },
        "note": (
            "Retention = gated(cal_1s)/gated(event). "
            "If Amihud-high days keep higher retention at coarse clocks, "
            "optimal horizon would shift — else horizon choice is liquidity-invariant."
        ),
    }


# ---------------------------------------------------------------------------
# Figures + reports
# ---------------------------------------------------------------------------


def make_figs(clock_board: list[dict[str, Any]], policy_board: list[dict[str, Any]]) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    # 1) gated rate by clock
    labels = [c["clock"] for c in clock_board]
    rates = [c["gated_per_day"] for c in clock_board]
    fig, ax = plt.subplots(figsize=(11, 4.5))
    colors = []
    for c in clock_board:
        if c["verdict"] == "Promote":
            colors.append("#2a9d8f")
        elif c["verdict"] == "Hold":
            colors.append("#e9c46a")
        else:
            colors.append("#e76f51")
    ax.bar(range(len(labels)), rates, color=colors)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=55, ha="right", fontsize=8)
    ax.set_ylabel("Gated crashes / day")
    ax.set_title("HL ETH — SSM gated rate by sampling clock")
    ax.axhline(0, color="#333", lw=0.5)
    p = FIG / "fig_gated_rate_by_clock.png"
    save_fig(p)
    paths.append(str(p))

    # 2) Δ|mo| fire−obs
    fig, ax = plt.subplots(figsize=(11, 4.5))
    xs, ys, lo, hi = [], [], [], []
    for i, c in enumerate(clock_board):
        d = c.get("delta_abs_mo5") or {}
        if not np.isfinite(d.get("delta", np.nan)):
            continue
        xs.append(i)
        ys.append(d["delta"])
        lo.append(d["delta"] - d.get("lo", d["delta"]))
        hi.append(d.get("hi", d["delta"]) - d["delta"])
    if xs:
        ax.errorbar(
            xs,
            ys,
            yerr=[lo, hi],
            fmt="o",
            color="#264653",
            ecolor="#6c757d",
            capsize=3,
        )
    ax.axhline(FRICTION_BPS, ls="--", color="#e76f51", label=f"friction {FRICTION_BPS}bps")
    ax.axhline(0, color="#333", lw=0.5)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=55, ha="right", fontsize=8)
    ax.set_ylabel("Δ|mo|@5s fire−obs (bps)")
    ax.set_title("Kill-ladder usefulness by detection clock")
    ax.legend(fontsize=8)
    p = FIG / "fig_delta_mo_by_clock.png"
    save_fig(p)
    paths.append(str(p))

    # 3) compute cost
    fig, ax = plt.subplots(figsize=(11, 4.0))
    secs = [c["mean_sec_per_day"] for c in clock_board]
    ax.bar(range(len(labels)), secs, color="#457b9d")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=55, ha="right", fontsize=8)
    ax.set_ylabel("Mean SSM sec / day")
    ax.set_title("Compute cost by clock (lower is cheaper)")
    p = FIG / "fig_compute_cost.png"
    save_fig(p)
    paths.append(str(p))

    # 4) policy intensity board
    if policy_board:
        fig, ax = plt.subplots(figsize=(9, 4.2))
        plab = [p["policy"] for p in policy_board]
        pd = [
            (p.get("delta_abs_mo5") or {}).get("delta", float("nan")) for p in policy_board
        ]
        plo = [(p.get("delta_abs_mo5") or {}).get("lo", float("nan")) for p in policy_board]
        phi = [(p.get("delta_abs_mo5") or {}).get("hi", float("nan")) for p in policy_board]
        yerr = [
            [pd[i] - plo[i] if np.isfinite(pd[i]) and np.isfinite(plo[i]) else 0 for i in range(len(pd))],
            [phi[i] - pd[i] if np.isfinite(pd[i]) and np.isfinite(phi[i]) else 0 for i in range(len(pd))],
        ]
        ax.errorbar(range(len(plab)), pd, yerr=yerr, fmt="o", color="#2a9d8f", capsize=3)
        ax.axhline(FRICTION_BPS, ls="--", color="#e76f51")
        ax.axhline(0, color="#333", lw=0.5)
        ax.set_xticks(range(len(plab)))
        ax.set_xticklabels(plab, rotation=40, ha="right", fontsize=8)
        ax.set_ylabel("Δ|mo|@5s")
        ax.set_title("Event-time detection · intensity-window policy sweep")
        p = FIG / "fig_policy_intensity.png"
        save_fig(p)
        paths.append(str(p))

    # 5) wall-time map for trade-N
    fig, ax = plt.subplots(figsize=(7, 4))
    trade_clocks = [c for c in clock_board if c["clock"].startswith("trade_last_")]
    if trade_clocks:
        ns = [int(c["clock"].split("_")[-1]) for c in trade_clocks]
        meds = [c["med_bar_s"] for c in trade_clocks]
        ax.plot(ns, meds, "o-", color="#264653")
        for n, m, c in zip(ns, meds, trade_clocks):
            ax.annotate(
                c["verdict"][0],
                (n, m),
                textcoords="offset points",
                xytext=(4, 4),
                fontsize=8,
            )
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("N trades / bar")
        ax.set_ylabel("Median bar wall-time (s)")
        ax.set_title("Trade-count N → wall time (HL ETH)")
    p = FIG / "fig_tradeN_walltime.png"
    save_fig(p)
    paths.append(str(p))

    return paths


def write_reports(
    *,
    summary: dict[str, Any],
    clock_board: list[dict[str, Any]],
    policy_board: list[dict[str, Any]],
    liq: dict[str, Any],
    fig_paths: list[str],
) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ts = summary["generated"]

    # EXP_REPORT
    lines = [
        "# Horizon lab — EXP_REPORT",
        "",
        f"Generated: {ts}",
        f"Panel: HL ETH · {summary['n_days_ok']}/{summary['n_days']} days · "
        f"span {summary['day_min']}…{summary['day_max']}",
        "Honesty: risk-policy / detection object — **not** naked alpha · live_orders=False · "
        f"friction={FRICTION_BPS} bps · bootstrap n=800 seed=41 · early/late time-split",
        "",
        "## Clock taxonomy",
        "",
        "| Clock family | Meaning | What we resample |",
        "|--------------|---------|------------------|",
        "| **event** | Pure trade-by-trade SSM (desk baseline) | nothing — every print |",
        "| **trade_last_N** | Every N-th trade close | last px of N trades |",
        "| **trade_ohlc_N** | N-trade bar with open→extreme→close | preserves intra-bar excursion |",
        "| **cal_Xs** | Calendar last-print bars | 1s / 5s / 60s |",
        "| **vol_USD** | Volume clock | close when cum $ notional hits bucket |",
        "| **policy intensity** | Event detection + N-tick / wall intensity | ladder input only |",
        "",
        "Note: plan language **300 / 9000 ticks** = event counts (trades or TOB updates), "
        "**not** 300 ms / 9 s. On HL ETH tape, N=300 trades ≈ **3–4 min** wall; "
        "N=9000 ≈ **1.5–2 h**. Collector TOB ~0.5 s → 300 TOB ≈ **2–3 min**; "
        "warehouse TOB ~seconds–minutes → same N is much slower.",
        "",
        "## Detection-clock scoreboard",
        "",
        "| clock | gated/day | med bar_s | Δ\\|mo\\| fire−obs | V-share fire | early/late | sec/day | verdict |",
        "|-------|----------:|----------:|-----------------:|-------------:|------------|--------:|---------|",
    ]
    for c in clock_board:
        d = c.get("delta_abs_mo5") or {}
        dlt = d.get("delta", float("nan"))
        lo, hi = d.get("lo", float("nan")), d.get("hi", float("nan"))
        dstr = (
            f"{dlt:.2f} [{lo:.2f},{hi:.2f}]"
            if np.isfinite(dlt)
            else "—"
        )
        lines.append(
            f"| `{c['clock']}` | {c['gated_per_day']:.2f} | "
            f"{c['med_bar_s'] if np.isfinite(c['med_bar_s']) else float('nan'):.2f} | "
            f"{dstr} | "
            f"{c['v_share_fire'] if np.isfinite(c.get('v_share_fire', np.nan)) else float('nan'):.2f} | "
            f"{c.get('delta_early')}/{c.get('delta_late')} "
            f"{'✓' if c.get('sign_stable_early_late') else '✗'} | "
            f"{c['mean_sec_per_day']:.3f} | **{c['verdict']}** |"
        )

    lines += [
        "",
        "## Policy intensity (event-time detection fixed)",
        "",
        "| intensity | n_fire | Δ\\|mo\\| | early/late | verdict | why |",
        "|-----------|-------:|--------|------------|---------|-----|",
    ]
    for p in policy_board:
        d = p.get("delta_abs_mo5") or {}
        dlt = d.get("delta", float("nan"))
        lo, hi = d.get("lo", float("nan")), d.get("hi", float("nan"))
        dstr = f"{dlt:.2f} [{lo:.2f},{hi:.2f}]" if np.isfinite(dlt) else "—"
        lines.append(
            f"| `{p['policy']}` | {p['n_fire']} | {dstr} | "
            f"{p.get('delta_early')}/{p.get('delta_late')} "
            f"{'✓' if p.get('sign_stable_early_late') else '✗'} | "
            f"**{p['verdict']}** | {p['why']} |"
        )

    lines += [
        "",
        "## Liquidity interaction",
        "",
        "```json",
        json.dumps(liq, indent=2, default=str),
        "```",
        "",
        "## Defaults recommended",
        "",
        f"- **Paper-live / risk overlay:** `{summary['rec_paper']}`",
        f"- **Research detection board:** `{summary['rec_research']}`",
        f"- **Do not use for mini-flash SSM:** `{summary['rec_avoid']}`",
        "",
        "## Figures",
        "",
    ]
    for fp in fig_paths:
        lines.append(f"- `{Path(fp).name}`")

    lines += [
        "",
        "## How to run",
        "",
        "```bash",
        "cd research/books/cross_miniflash/applications/horizon_lab",
        "python3 run_horizon_sweep.py --workers 8",
        "python3 run_horizon_sweep.py --smoke 4 --workers 4",
        "```",
        "",
        "## Not tested here",
        "",
        "- Live OE / fill realism",
        "- Cross-ex xarb tick-bar PnL (separate startarb lane; see plan `xarb_tick_horizons`)",
        "- Dense ms multi-venue TOB decision path on Phase-4 core days",
        "- FEI tercile × horizon (3-venue day panel not rebuilt in this lab)",
        "",
    ]
    (OUT / "EXP_REPORT.md").write_text("\n".join(lines) + "\n")

    # Short user-facing recommendation
    rec = [
        "# Horizon recommendation — mini-flash / risk-overlay sampling",
        "",
        f"_Generated {ts}. Evidence: `applications/horizon_lab/out/EXP_REPORT.md`._",
        "",
        "## One-paragraph answer",
        "",
        summary["answer_paragraph"],
        "",
        "## Recommended defaults",
        "",
        f"1. **Paper-live / kill-ladder risk overlay:** **{summary['rec_paper']}**",
        f"2. **Research detection + boards:** **{summary['rec_research']}**",
        f"3. **Avoid for SSM mini-flash detection:** **{summary['rec_avoid']}**",
        "",
        "## Clock cheat-sheet (HL ETH)",
        "",
        "| N trades | ≈ wall time | Detection? |",
        "|---------:|------------:|:-----------|",
    ]
    for c in clock_board:
        if c["clock"].startswith("trade_last_"):
            n = c["clock"].split("_")[-1]
            rec.append(
                f"| {n} | {c['med_bar_s']:.0f}s | **{c['verdict']}** "
                f"({c['gated_per_day']:.2f} gated/day) |"
            )
    rec += [
        "",
        "## Warehouse vs ms tape",
        "",
        summary["cadence_honesty"],
        "",
        "## Liquidity",
        "",
        summary["liquidity_blurb"],
        "",
    ]
    (OUT / "HORIZON_RECOMMENDATION.md").write_text("\n".join(rec) + "\n")
    # also book-root convenience copy
    (LAB / "HORIZON_RECOMMENDATION.md").write_text("\n".join(rec) + "\n")


def build_recommendations(
    clock_board: list[dict[str, Any]],
    policy_board: list[dict[str, Any]],
    liq: dict[str, Any],
) -> dict[str, str]:
    by = {c["clock"]: c for c in clock_board}
    ev = by.get("event", {})
    cal1 = by.get("cal_1s", {})
    cal5 = by.get("cal_5s", {})
    t300 = by.get("trade_last_300", {})
    t9000 = by.get("trade_last_9000", {})

    # Prefer wall_60s policy if Promote else best Promote policy
    pol_promote = [p for p in policy_board if p["verdict"] == "Promote"]
    best_pol = next((p for p in pol_promote if p["policy"] == "wall_60s"), None) or (
        pol_promote[0] if pol_promote else None
    )

    rec_paper = (
        "event-time SSM (trade tape) + kill-ladder intensity "
        f"`{(best_pol or {}).get('policy', 'wall_60s')}` "
        "(decision wake may coalesce ~0.5–1s; do **not** detect on 300/9000 trade bars)"
    )
    # research: event + cal_1s as robustness if Hold/Promote
    if cal1.get("verdict") in ("Promote", "Hold") and cal1.get("gated_per_day", 0) > 0:
        rec_research = (
            f"primary `event`; secondary robustness `cal_1s` "
            f"({cal1.get('gated_per_day', 0):.2f} gated/day, verdict {cal1.get('verdict')})"
        )
    else:
        rec_research = "primary `event` only (calendar bars lose too many gated crashes)"

    rec_avoid = (
        f"trade_last_300 / trade_last_9000 / coarse vol clocks for **detection** "
        f"(300→{t300.get('gated_per_day', 0):.2f}/day, 9000→{t9000.get('gated_per_day', 0):.2f}/day gated)"
    )

    answer = (
        f"**300 and 9000 trade-count bars are doable as decision/cadence knobs, not as SSM detection "
        f"sampling.** On HL ETH ({ev.get('n_days', '?')} days), pure event-time SSM yields "
        f"~{ev.get('gated_per_day', float('nan')):.1f} gated crashes/day with kill-ladder "
        f"Δ|mo|={((ev.get('delta_abs_mo5') or {}).get('delta'))} bps "
        f"(verdict **{ev.get('verdict')}**). Last-print **N=300** (~{t300.get('med_bar_s', float('nan')):.0f}s wall) "
        f"and **N=9000** (~{t9000.get('med_bar_s', float('nan')):.0f}s) collapse gated intensity to "
        f"~{t300.get('gated_per_day', 0):.2f} / ~{t9000.get('gated_per_day', 0):.2f} per day — mini-flashes "
        f"are averaged away inside the bar. Calendar **1s** retains usable detection "
        f"({cal1.get('verdict')}, ~{cal1.get('gated_per_day', 0):.2f}/day); **5s** is marginal "
        f"({cal5.get('verdict')}); **1m** is research-only sparse. "
        f"Keep paper-live on the **ms trade tape** (or ≤1s calendar), and use N∈{{300,9000}} only if you "
        f"mean intensity/hold **windows** on top of event detection — not the KF observation clock."
    )

    mean_g = (liq or {}).get("mean_gated") or {}
    am_ret = (liq or {}).get("amihud_vs_cal1_retention") or {}
    liquidity_blurb = (
        f"Day Amihud vs event gated Spearman={am_ret.get('spearman_x_y', 'n/a')}; "
        f"mean gated event/cal1s/trade300="
        f"{mean_g.get('event')}/{mean_g.get('cal_1s')}/{mean_g.get('trade_last_300')}. "
        "Coarse trade-N clocks stay near-zero across Amihud terciles — optimal **detection** horizon "
        "does **not** shift into 300/9000 when liquidity worsens; thin/Amihud-high days still need "
        "event or ≤1s clocks. Diurnal scheduling (UTC peak) remains a prior (R03 Hold), not a bar-size switch."
    )

    cadence = (
        "Warehouse TOB on Phase-4 core days is **seconds–minutes** (expanded_lab: core median Δt≃177s; "
        "dense collector days ~0.55s). Sub-second queue-position / outside-TOB claims need collector TOB. "
        "Crash SSM here is **trade-tape** event-time — that path is available at ms resolution even when "
        "BBO is sparse. Do not confuse warehouse quote cadence with trade-tick horizons."
    )
    return {
        "rec_paper": rec_paper,
        "rec_research": rec_research,
        "rec_avoid": rec_avoid,
        "answer_paragraph": answer,
        "liquidity_blurb": liquidity_blurb,
        "cadence_honesty": cadence,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--smoke", type=int, default=0, help="Use first N PIN days only")
    ap.add_argument("--days", type=str, default="", help="Comma-separated UTC days")
    args = ap.parse_args()

    ensure_env()
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)

    if args.days.strip():
        days = [d.strip() for d in args.days.split(",") if d.strip()]
    else:
        days = list(PIN_USABLE)
    if args.smoke and args.smoke > 0:
        days = days[: int(args.smoke)]

    print(f"[horizon_lab] days={len(days)} workers={args.workers}", flush=True)
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    if args.workers <= 1:
        for d in days:
            try:
                rows.append(process_day(d))
                print(f"  {d} ok={rows[-1].get('ok')} gated_event="
                      f"{(rows[-1].get('clocks') or {}).get('event', {}).get('gated_n')}", flush=True)
            except Exception as exc:
                errors.append({"day": d, "error": f"{type(exc).__name__}: {exc}"})
                traceback.print_exc()
    else:
        with ProcessPoolExecutor(max_workers=int(args.workers)) as ex:
            futs = {ex.submit(process_day, d): d for d in days}
            for fut in as_completed(futs):
                d = futs[fut]
                try:
                    row = fut.result()
                    rows.append(row)
                    print(
                        f"  {d} ok={row.get('ok')} gated_event="
                        f"{(row.get('clocks') or {}).get('event', {}).get('gated_n')}",
                        flush=True,
                    )
                except Exception as exc:
                    errors.append({"day": d, "error": f"{type(exc).__name__}: {exc}"})
                    traceback.print_exc()

    rows.sort(key=lambda r: r.get("day", ""))
    ok_rows = [r for r in rows if r.get("ok")]

    # union of clock names
    clock_names: list[str] = []
    seen: set[str] = set()
    for r in ok_rows:
        for k in (r.get("clocks") or {}):
            if k not in seen:
                seen.add(k)
                clock_names.append(k)
    # stable priority order
    prefer = (
        ["event"]
        + [f"trade_last_{n}" for n in TRADE_NS]
        + [f"trade_ohlc_{n}" for n in TRADE_NS]
        + [f"cal_{int(s)}s" for s in CAL_S]
        + [f"vol_{int(u)}" for u in VOL_USD]
    )
    clock_names = [c for c in prefer if c in seen] + [c for c in clock_names if c not in prefer]

    clock_board = [pool_clock(ok_rows, c) for c in clock_names]
    policy_names = [p[0] for p in INTENSITY_WINDOWS]
    policy_board = [pool_policy(ok_rows, p) for p in policy_names]
    liq = liquidity_slice(ok_rows)
    recs = build_recommendations(clock_board, policy_board, liq)

    day_list = [r["day"] for r in ok_rows]
    summary = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "venue": VENUE,
        "symbol": SYMBOL,
        "n_days": len(days),
        "n_days_ok": len(ok_rows),
        "day_min": min(day_list) if day_list else None,
        "day_max": max(day_list) if day_list else None,
        "days_ok": day_list,
        "errors": errors,
        "friction_bps": FRICTION_BPS,
        "gate": GATE_PRIMARY,
        "z_star": Z_STAR,
        "clock_board": clock_board,
        "policy_board": policy_board,
        "liquidity": liq,
        **recs,
    }
    save_json(OUT / "summary.json", summary)
    # slim day cache (events only for event + key clocks)
    slim = []
    for r in ok_rows:
        slim.append(
            {
                "day": r["day"],
                "n_trades": r["n_trades"],
                "trades_per_s": r.get("trades_per_s"),
                "amihud_1m": r.get("amihud_1m"),
                "clocks": {
                    k: {
                        "n_bars": v.get("n_bars"),
                        "raw_n": v.get("raw_n"),
                        "gated_n": v.get("gated_n"),
                        "sec": v.get("sec"),
                        "med_bar_s": v.get("med_bar_s"),
                        "n_events": len(v.get("events") or []),
                    }
                    for k, v in (r.get("clocks") or {}).items()
                },
            }
        )
    save_json(OUT / "days_slim.json", slim)

    fig_paths = make_figs(clock_board, policy_board)
    write_reports(
        summary=summary,
        clock_board=clock_board,
        policy_board=policy_board,
        liq=liq,
        fig_paths=fig_paths,
    )

    print(
        f"[horizon_lab] done ok_days={len(ok_rows)} "
        f"event_gated/day={(by := {c['clock']: c for c in clock_board}).get('event', {}).get('gated_per_day')} "
        f"rec_paper={recs['rec_paper'][:60]}...",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
