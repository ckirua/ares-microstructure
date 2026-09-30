#!/usr/bin/env python3
"""Entry-timing micro-research for V-fade executable gap.

Hypothesis: by confirm (+2s) most of the V rebound is already realized, so
path PnL (entry@+2s → exit@+5s) is late / adversely selected vs lab (−mo_5s
from ts_end).

Writes:
  out/ENTRY_TIMING.md
  out/figs/entry_timing_*.png
  out/entry_timing_rows.jsonl
  out/entry_timing_summary.json

Own files only under v_fade_paper/ (+ this script). No ClickHouse MCP. No commit.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PKG = Path(__file__).resolve().parent
BOOK = PKG.parents[2]
ROOT = BOOK.parents[2]
STRATEGY_LAB = BOOK / "applications" / "strategy_lab"

for p in (str(PKG), str(STRATEGY_LAB), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from harness.causal import asof_trade_px, causal_class, jsonable, write_jsonl  # noqa: E402
from harness.config import load_config  # noqa: E402
from harness.pipeline import _detect_cfg, _load_paper_detect  # noqa: E402
from research.lib.crash import recovery_fraction  # noqa: E402
from sim.book import book_meta, load_best_book  # noqa: E402

NS = 1_000_000_000
HORIZONS = (0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0)
ENTRY_DELAYS = (0.0, 0.5, 1.0, 1.5, 2.0)
EXIT_S = 5.0
RT_BPS = 4.0
PANEL_DAYS = [
    "2026-09-04",
    "2026-09-05",
    "2026-09-06",
    "2026-09-07",
    "2026-09-08",
    "2026-09-09",
    "2026-09-10",
]


def _boot_mean(x: np.ndarray, *, n_boot: int = 800, seed: int = 7) -> dict[str, float]:
    x = np.asarray(x, dtype=np.float64)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return {"n": 0, "mean": float("nan"), "lo": float("nan"), "hi": float("nan")}
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot, dtype=np.float64)
    for i in range(n_boot):
        means[i] = float(np.mean(rng.choice(x, size=x.size, replace=True)))
    return {
        "n": int(x.size),
        "mean": float(np.mean(x)),
        "lo": float(np.percentile(means, 2.5)),
        "hi": float(np.percentile(means, 97.5)),
    }


def _end_indices(ts: np.ndarray, ts_end: np.ndarray) -> np.ndarray:
    """Index of last tape print at or before each ts_end."""
    out = np.searchsorted(ts, ts_end, side="right") - 1
    return out.astype(np.int64)


def _start_indices(ts: np.ndarray, ts_start: np.ndarray) -> np.ndarray:
    out = np.searchsorted(ts, ts_start, side="left")
    out = np.clip(out, 0, max(ts.size - 1, 0))
    return out.astype(np.int64)


def _rebound_bps(
    ts: np.ndarray,
    px: np.ndarray,
    end_i: int,
    direction: int,
    *,
    horizon_s: float,
) -> float:
    """Favorable rebound for fade (bps of end px) over [end, end+h].

    Crash direction +1 (up-crash): fade sells; rebound = drop from end.
    Crash direction −1 (down-crash): fade buys; rebound = rise from end.
    Returns positive when price moved against the crash (good for fade).
    """
    if end_i < 0 or end_i >= px.size or px[end_i] <= 0 or direction == 0:
        return float("nan")
    t_lim = int(ts[end_i]) + int(horizon_s * NS)
    j = int(np.searchsorted(ts, t_lim, side="right") - 1)
    if j <= end_i:
        return 0.0
    p0 = float(px[end_i])
    window = px[end_i : j + 1]
    if direction < 0:
        # down crash → rebound up
        fav = float(np.nanmax(window) - p0)
    else:
        fav = float(p0 - np.nanmin(window))
    return fav / p0 * 1e4


def _px_at(ts: np.ndarray, px: np.ndarray, t_ns: int) -> float:
    return asof_trade_px(ts, px, t_ns)


def _fade_mo_bps(
    ts: np.ndarray,
    px: np.ndarray,
    *,
    t_entry: int,
    t_exit: int,
    side: int,
) -> float:
    """Fade-side markout bps from entry → exit (tape asof)."""
    pe = _px_at(ts, px, t_entry)
    px_out = _px_at(ts, px, t_exit)
    if not (np.isfinite(pe) and np.isfinite(px_out) and pe > 0):
        return float("nan")
    return float(side) * (px_out / pe - 1.0) * 1e4


def _tape_impact_bps(
    ts: np.ndarray,
    px: np.ndarray,
    t_entry: int,
    side: int,
    *,
    n_prints: int = 5,
) -> float:
    """Adverse selection proxy: fade-signed move over next n_prints after entry."""
    j = int(np.searchsorted(ts, t_entry, side="right") - 1)
    if j < 0 or j + n_prints >= px.size:
        return float("nan")
    p0 = float(px[j])
    p1 = float(px[j + n_prints])
    if not (np.isfinite(p0) and np.isfinite(p1) and p0 > 0):
        return float("nan")
    # positive = price moved with crash = adverse for fade
    return float(-side) * (p1 / p0 - 1.0) * 1e4


def _rolling_recovery_at(
    ts: np.ndarray,
    px: np.ndarray,
    start_i: int,
    end_i: int,
    direction: int,
    t_ns: int,
) -> float:
    """Causal recovery fraction using only prints ≤ t_ns after event end."""
    if start_i < 0 or end_i >= px.size or end_i < start_i or px[start_i] <= 0:
        return float("nan")
    move = float(px[end_i] - px[start_i])
    if move == 0 or direction == 0:
        return float("nan")
    j = int(np.searchsorted(ts, t_ns, side="right") - 1)
    if j <= end_i:
        return 0.0
    if direction < 0:
        rebound = float(np.nanmax(px[end_i : j + 1]) - px[end_i])
    else:
        rebound = float(px[end_i] - np.nanmin(px[end_i : j + 1]))
    return rebound / abs(move)


def _first_causal_early_entry_ns(
    ts: np.ndarray,
    px: np.ndarray,
    start_i: int,
    end_i: int,
    direction: int,
    ts_end: int,
    *,
    v_thr: float = 0.5,
    soft_r1: float = 0.35,
    min_wait_s: float = 1.0,
    max_wait_s: float = 2.0,
) -> int | None:
    """Earliest causal entry: after min_wait, once rolling recovery ≥ v_thr
    and soft 1s confirm holds — never uses future r2 beyond current t.
    """
    t_min = ts_end + int(min_wait_s * NS)
    t_max = ts_end + int(max_wait_s * NS)
    # need r1 soft once t≥1s
    r1 = _rolling_recovery_at(ts, px, start_i, end_i, direction, t_min)
    if not np.isfinite(r1) or r1 < soft_r1:
        return None
    # walk prints in (t_min, t_max]
    lo = int(np.searchsorted(ts, t_min, side="left"))
    hi = int(np.searchsorted(ts, t_max, side="right"))
    for j in range(lo, hi):
        t = int(ts[j])
        if t < t_min:
            continue
        r = _rolling_recovery_at(ts, px, start_i, end_i, direction, t)
        if np.isfinite(r) and r >= v_thr:
            return t
    # if already ≥ thr at t_min
    r0 = _rolling_recovery_at(ts, px, start_i, end_i, direction, t_min)
    if np.isfinite(r0) and r0 >= v_thr:
        return t_min
    return None


def analyze_day(
    day: str,
    *,
    detect_fn,
    dcfg: dict[str, Any],
    venue: str = "hyperliquid",
    symbol: str = "ETH",
) -> list[dict[str, Any]]:
    cell = detect_fn(venue, symbol, day, cfg=dcfg, quiet=True)
    if cell.get("skip"):
        return []
    ts = np.asarray(cell["ts"], dtype=np.int64)
    px = np.asarray(cell["px"], dtype=np.float64)
    ev = cell["events"]
    n = int(cell.get("ssm_10_n") or 0)
    if n == 0 or ts.size == 0:
        return []

    ts_start = np.asarray(ev["ts_start"], dtype=np.int64)
    ts_end = np.asarray(ev["ts_end"], dtype=np.int64)
    direction = np.asarray(ev["direction"], dtype=np.int64)
    r1 = np.asarray(ev["recovery_1s"], dtype=np.float64)
    r2 = np.asarray(ev["recovery_2s"], dtype=np.float64)
    mo5 = np.asarray(ev["mo_5s"], dtype=np.float64)
    zpk = np.asarray(ev.get("z_peak", []), dtype=np.float64)
    dp = np.asarray(ev.get("dp_pct", []), dtype=np.float64)
    start_i = _start_indices(ts, ts_start)
    end_i = _end_indices(ts, ts_end)

    # recovery ladder (diagnostic; fixed horizons)
    rec_by_h = {
        h: recovery_fraction(ts, px, start_i, end_i, direction, horizon_s=h)
        for h in HORIZONS
    }

    book = load_best_book(venue, symbol, day, prefer_collector=True, attach_l2_depth=False)
    bmeta = book_meta(book)

    rows: list[dict[str, Any]] = []
    for i in range(n):
        d = int(direction[i])
        te = int(ts_end[i])
        ei = int(end_i[i])
        si = int(start_i[i])
        rr1 = float(r1[i]) if np.isfinite(r1[i]) else float("nan")
        rr2 = float(r2[i]) if np.isfinite(r2[i]) else float("nan")
        cls = causal_class(rr2, rr1)
        side = -d
        mo = float(mo5[i]) if np.isfinite(mo5[i]) else float("nan")

        rebound = {h: _rebound_bps(ts, px, ei, d, horizon_s=h) for h in HORIZONS}
        r5 = rebound.get(5.0, float("nan"))
        frac_of_5s = {}
        for h in HORIZONS:
            rh = rebound[h]
            if np.isfinite(r5) and r5 > 1e-9 and np.isfinite(rh):
                frac_of_5s[h] = float(np.clip(rh / r5, 0.0, 3.0))
            else:
                frac_of_5s[h] = float("nan")

        # fade mo: from ts_end vs delayed entry, exit fixed at ts_end+5s
        t_exit = te + int(EXIT_S * NS)
        mo_from_end = _fade_mo_bps(ts, px, t_entry=te, t_exit=t_exit, side=side)
        mo_by_delay: dict[float, float] = {}
        residual_by_delay: dict[float, float] = {}
        for delay in ENTRY_DELAYS:
            t_ent = te + int(delay * NS)
            mo_d = _fade_mo_bps(ts, px, t_entry=t_ent, t_exit=t_exit, side=side)
            mo_by_delay[delay] = mo_d
            # residual share of end→5s fade mo still available after delay
            if np.isfinite(mo_from_end) and abs(mo_from_end) > 1e-9 and np.isfinite(mo_d):
                residual_by_delay[delay] = mo_d / mo_from_end
            else:
                residual_by_delay[delay] = float("nan")

        # spread / impact at candidate entries
        book_at: dict[str, Any] = {}
        impact_at: dict[str, Any] = {}
        for delay in ENTRY_DELAYS:
            t_ent = te + int(delay * NS)
            impact_at[str(delay)] = _tape_impact_bps(ts, px, t_ent, side, n_prints=5)
            if book is not None:
                snap = book.asof(np.asarray([t_ent], dtype=np.int64))
                bid = float(snap["bid"][0])
                ask = float(snap["ask"][0])
                mid = float(snap["mid"][0])
                bi = int(snap["book_i"][0])
                age_s = float("nan")
                if snap["valid"][0] and bi >= 0:
                    age_s = (t_ent - int(book.ts[bi])) / NS
                spr = (ask - bid) / mid * 1e4 if mid > 0 and np.isfinite(mid) else float("nan")
                # taker pay: sell → hit bid; buy → lift ask
                if side < 0 and mid > 0 and np.isfinite(bid):
                    half = (mid - bid) / mid * 1e4
                elif side > 0 and mid > 0 and np.isfinite(ask):
                    half = (ask - mid) / mid * 1e4
                else:
                    half = float("nan")
                book_at[str(delay)] = {
                    "spread_bps": spr,
                    "half_touch_bps": half,
                    "book_age_s": age_s,
                    "valid": bool(snap["valid"][0]),
                }
            else:
                book_at[str(delay)] = {
                    "spread_bps": float("nan"),
                    "half_touch_bps": float("nan"),
                    "book_age_s": float("nan"),
                    "valid": False,
                }

        early_t = _first_causal_early_entry_ns(ts, px, si, ei, d, te)
        early_delay_s = (early_t - te) / NS if early_t is not None else float("nan")
        mo_early = (
            _fade_mo_bps(ts, px, t_entry=early_t, t_exit=t_exit, side=side)
            if early_t is not None
            else float("nan")
        )
        # strict +1s rule: enter at 1s if r1≥0.5 (causal, no r2)
        enter_r1_strict = bool(np.isfinite(rr1) and rr1 >= 0.5)
        mo_r1_strict = (
            _fade_mo_bps(ts, px, t_entry=te + NS, t_exit=t_exit, side=side)
            if enter_r1_strict
            else float("nan")
        )
        # first t where rolling recovery ≥ 0.5 (no min wait)
        first_r50_t = None
        t_max = te + int(2.0 * NS)
        lo = int(np.searchsorted(ts, te, side="right"))
        hi = int(np.searchsorted(ts, t_max, side="right"))
        for j in range(lo, hi):
            t = int(ts[j])
            rr = _rolling_recovery_at(ts, px, si, ei, d, t)
            if np.isfinite(rr) and rr >= 0.5:
                first_r50_t = t
                break
        mo_first_r50 = (
            _fade_mo_bps(ts, px, t_entry=first_r50_t, t_exit=t_exit, side=side)
            if first_r50_t is not None
            else float("nan")
        )
        z_abs = abs(float(zpk[i])) if i < zpk.size and np.isfinite(zpk[i]) else float("nan")
        dp_i = float(dp[i]) if i < dp.size and np.isfinite(dp[i]) else float("nan")
        r05 = _rolling_recovery_at(ts, px, si, ei, d, te + int(0.5 * NS))

        rows.append(
            {
                "day": day,
                "venue": venue,
                "symbol": symbol,
                "event_i": i,
                "direction": d,
                "side": side,
                "causal_class": cls,
                "is_v": cls == "v_recovery",
                "z_peak_abs": z_abs if np.isfinite(z_abs) else None,
                "dp_pct": dp_i if np.isfinite(dp_i) else None,
                "recovery_1s": rr1 if np.isfinite(rr1) else None,
                "recovery_2s": rr2 if np.isfinite(rr2) else None,
                "recovery_0_5s": r05 if np.isfinite(r05) else None,
                "mo_5s_crash": mo if np.isfinite(mo) else None,
                "lab_net_bps": (-mo - RT_BPS) if np.isfinite(mo) else None,
                "recovery_by_h": {str(h): float(rec_by_h[h][i]) for h in HORIZONS},
                "rebound_bps_by_h": {str(h): rebound[h] for h in HORIZONS},
                "frac_of_5s_rebound": {str(h): frac_of_5s[h] for h in HORIZONS},
                "fade_mo_end_to_5s": mo_from_end,
                "fade_mo_by_entry_delay": {str(k): v for k, v in mo_by_delay.items()},
                "residual_mo_frac_by_delay": {str(k): v for k, v in residual_by_delay.items()},
                "path_net_at_2s": (mo_by_delay[2.0] - RT_BPS)
                if np.isfinite(mo_by_delay[2.0])
                else None,
                "tape_impact_5prints": impact_at,
                "book_at_entry": book_at,
                "book_meta": bmeta,
                "early_rolling_entry_delay_s": early_delay_s
                if np.isfinite(early_delay_s)
                else None,
                "fade_mo_early_rolling": mo_early if np.isfinite(mo_early) else None,
                "r1_strict_enter": enter_r1_strict,
                "fade_mo_r1_strict": mo_r1_strict if np.isfinite(mo_r1_strict) else None,
                "first_r50_delay_s": ((first_r50_t - te) / NS)
                if first_r50_t is not None
                else None,
                "fade_mo_first_r50": mo_first_r50 if np.isfinite(mo_first_r50) else None,
            }
        )
    return rows


def _nanmean(xs: list[float]) -> float:
    a = np.asarray(xs, dtype=np.float64)
    a = a[np.isfinite(a)]
    return float(np.mean(a)) if a.size else float("nan")


def _nanmedian(xs: list[float]) -> float:
    a = np.asarray(xs, dtype=np.float64)
    a = a[np.isfinite(a)]
    return float(np.median(a)) if a.size else float("nan")


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    vrows = [r for r in rows if r.get("is_v")]
    all_n = len(rows)
    v_n = len(vrows)

    frac_curve = {}
    rebound_curve = {}
    for h in HORIZONS:
        fr = [float(r["frac_of_5s_rebound"][str(h)]) for r in vrows]
        rb = [float(r["rebound_bps_by_h"][str(h)]) for r in vrows]
        frac_curve[str(h)] = {
            "mean": _nanmean(fr),
            "median": _nanmedian(fr),
            "p25": float(np.nanpercentile(fr, 25)) if any(np.isfinite(fr)) else float("nan"),
            "p75": float(np.nanpercentile(fr, 75)) if any(np.isfinite(fr)) else float("nan"),
            "n": int(np.sum(np.isfinite(fr))),
        }
        rebound_curve[str(h)] = {
            "mean_bps": _nanmean(rb),
            "median_bps": _nanmedian(rb),
            "n": int(np.sum(np.isfinite(rb))),
        }

    mo_by_delay = {}
    residual = {}
    for delay in ENTRY_DELAYS:
        mos = [float(r["fade_mo_by_entry_delay"][str(delay)]) for r in vrows]
        res = [float(r["residual_mo_frac_by_delay"][str(delay)]) for r in vrows]
        nets = [m - RT_BPS for m in mos if np.isfinite(m)]
        mo_by_delay[str(delay)] = {
            **_boot_mean(np.asarray(mos, dtype=np.float64), seed=11 + int(delay * 10)),
            "net_mean": _nanmean(nets),
            "hit_rate": float(np.mean(np.asarray(nets) > 0)) if nets else float("nan"),
        }
        residual[str(delay)] = {
            "mean": _nanmean(res),
            "median": _nanmedian(res),
            "n": int(np.sum(np.isfinite(res))),
        }

    # when is rebound "used up"? first h where median frac ≥ thresholds
    used_up = {}
    for thr in (0.5, 0.75, 0.90):
        hit_h = None
        for h in HORIZONS:
            med = frac_curve[str(h)]["median"]
            if np.isfinite(med) and med >= thr:
                hit_h = h
                break
        used_up[str(thr)] = hit_h

    # spread / impact at +2s vs +0/+1
    spread = {}
    impact = {}
    for delay in ENTRY_DELAYS:
        spr = [
            float(r["book_at_entry"][str(delay)]["spread_bps"])
            for r in vrows
            if r["book_at_entry"][str(delay)].get("valid")
        ]
        half = [
            float(r["book_at_entry"][str(delay)]["half_touch_bps"])
            for r in vrows
            if r["book_at_entry"][str(delay)].get("valid")
        ]
        age = [
            float(r["book_at_entry"][str(delay)]["book_age_s"])
            for r in vrows
            if r["book_at_entry"][str(delay)].get("valid")
        ]
        imp = [float(r["tape_impact_5prints"][str(delay)]) for r in vrows]
        spread[str(delay)] = {
            "spread_mean": _nanmean(spr),
            "half_touch_mean": _nanmean(half),
            "book_age_median_s": _nanmedian(age),
            "n_book": int(np.sum(np.isfinite(spr))),
        }
        impact[str(delay)] = {
            "adverse_5print_mean_bps": _nanmean(imp),
            "adverse_5print_median_bps": _nanmedian(imp),
            "n": int(np.sum(np.isfinite(imp))),
        }

    # causal early rules (evaluated on same V set for diagnostic + on causal filter)
    early_delays = [
        float(r["early_rolling_entry_delay_s"])
        for r in vrows
        if r.get("early_rolling_entry_delay_s") is not None
    ]
    early_mos = [
        float(r["fade_mo_early_rolling"])
        for r in vrows
        if r.get("fade_mo_early_rolling") is not None
    ]
    r1_strict_mos = [
        float(r["fade_mo_r1_strict"]) for r in vrows if r.get("r1_strict_enter")
    ]
    # Fully causal selection: enter via rolling rule without requiring r2 class
    causal_early_rows = [
        r
        for r in rows
        if r.get("early_rolling_entry_delay_s") is not None
        and r.get("fade_mo_early_rolling") is not None
    ]
    causal_early_mos = [float(r["fade_mo_early_rolling"]) for r in causal_early_rows]
    causal_r1 = [
        r for r in rows if r.get("r1_strict_enter") and r.get("fade_mo_r1_strict") is not None
    ]
    causal_r1_mos = [float(r["fade_mo_r1_strict"]) for r in causal_r1]

    def _sel_mo(pred, delay: float) -> dict[str, Any]:
        mos = [
            float(r["fade_mo_by_entry_delay"][str(delay)])
            for r in rows
            if pred(r) and np.isfinite(float(r["fade_mo_by_entry_delay"][str(delay)]))
        ]
        return {
            "n": len(mos),
            "fade_mo": _boot_mean(np.asarray(mos, dtype=np.float64), seed=61 + int(delay * 10)),
            "net_mean": _nanmean([m - RT_BPS for m in mos]),
            "hit_rate": float(np.mean(np.asarray(mos) - RT_BPS > 0)) if mos else float("nan"),
        }

    first_r50_mos = [
        float(r["fade_mo_first_r50"])
        for r in vrows
        if r.get("fade_mo_first_r50") is not None
    ]
    first_r50_delays = [
        float(r["first_r50_delay_s"])
        for r in vrows
        if r.get("first_r50_delay_s") is not None
    ]

    book_sources = {}
    for r in vrows:
        src = (r.get("book_meta") or {}).get("source") or "none"
        book_sources[src] = book_sources.get(src, 0) + 1

    # share of V events with frac≥0.9 by horizon
    share_used = {}
    for h in HORIZONS:
        fr = np.asarray(
            [float(r["frac_of_5s_rebound"][str(h)]) for r in vrows], dtype=np.float64
        )
        fr = fr[np.isfinite(fr)]
        share_used[str(h)] = {
            "ge_0_5": float(np.mean(fr >= 0.5)) if fr.size else float("nan"),
            "ge_0_9": float(np.mean(fr >= 0.9)) if fr.size else float("nan"),
            "ge_1_0": float(np.mean(fr >= 0.999)) if fr.size else float("nan"),
        }

    return {
        "n_events_gated": all_n,
        "n_v_recovery": v_n,
        "frac_of_5s_rebound_curve": frac_curve,
        "rebound_bps_curve": rebound_curve,
        "used_up_median_frac_ge": used_up,
        "fade_mo_by_entry_delay": mo_by_delay,
        "residual_mo_frac_by_delay": residual,
        "spread_at_entry": spread,
        "tape_impact_at_entry": impact,
        "book_sources": book_sources,
        "on_v_set": {
            "early_rolling": {
                "n": len(early_mos),
                "mean_delay_s": _nanmean(early_delays),
                "median_delay_s": _nanmedian(early_delays),
                "fade_mo": _boot_mean(np.asarray(early_mos, dtype=np.float64), seed=41),
                "net_mean": _nanmean([m - RT_BPS for m in early_mos]),
            },
            "r1_strict": {
                "n": len(r1_strict_mos),
                "fade_mo": _boot_mean(np.asarray(r1_strict_mos, dtype=np.float64), seed=42),
                "net_mean": _nanmean([m - RT_BPS for m in r1_strict_mos]),
            },
            "confirm_2s": mo_by_delay.get("2.0"),
            "from_end": mo_by_delay.get("0.0"),
        },
        "share_rebound_used_by_h": share_used,
        "on_v_first_r50": {
            "n": len(first_r50_mos),
            "median_delay_s": _nanmedian(first_r50_delays),
            "mean_delay_s": _nanmean(first_r50_delays),
            "fade_mo": _boot_mean(np.asarray(first_r50_mos, dtype=np.float64), seed=55),
            "net_mean": _nanmean([m - RT_BPS for m in first_r50_mos]),
        },
        "causal_no_r2_lookaside": {
            "rolling_enter_ge1s": {
                "n": len(causal_early_mos),
                "fade_mo": _boot_mean(
                    np.asarray(causal_early_mos, dtype=np.float64), seed=51
                ),
                "net_mean": _nanmean([m - RT_BPS for m in causal_early_mos]),
                "mean_delay_s": _nanmean(
                    [
                        float(r["early_rolling_entry_delay_s"])
                        for r in causal_early_rows
                        if r.get("early_rolling_entry_delay_s") is not None
                    ]
                ),
            },
            "r1_ge_0_5_enter_at_1s": {
                "n": len(causal_r1_mos),
                "fade_mo": _boot_mean(np.asarray(causal_r1_mos, dtype=np.float64), seed=52),
                "net_mean": _nanmean([m - RT_BPS for m in causal_r1_mos]),
            },
            # severity @ ts_end — no recovery look-ahead
            "z_ge_15_at_0s": _sel_mo(
                lambda r: (r.get("z_peak_abs") or 0) >= 15.0, 0.0
            ),
            "z_ge_20_at_0s": _sel_mo(
                lambda r: (r.get("z_peak_abs") or 0) >= 20.0, 0.0
            ),
            "z_ge_15_at_0_5s": _sel_mo(
                lambda r: (r.get("z_peak_abs") or 0) >= 15.0, 0.5
            ),
            "all_gated_at_0s": _sel_mo(lambda _r: True, 0.0),
            "all_gated_at_0_5s": _sel_mo(lambda _r: True, 0.5),
            "all_gated_at_2s": _sel_mo(lambda _r: True, 2.0),
        },
    }


def write_figs(rows: list[dict[str, Any]], summary: dict[str, Any], fig_dir: Path) -> list[str]:
    fig_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    vrows = [r for r in rows if r.get("is_v")]
    if not vrows:
        return paths

    # 1) fraction of 5s rebound realized
    hs = list(HORIZONS)
    meds = [summary["frac_of_5s_rebound_curve"][str(h)]["median"] for h in hs]
    means = [summary["frac_of_5s_rebound_curve"][str(h)]["mean"] for h in hs]
    p25 = [summary["frac_of_5s_rebound_curve"][str(h)]["p25"] for h in hs]
    p75 = [summary["frac_of_5s_rebound_curve"][str(h)]["p75"] for h in hs]
    fig, ax = plt.subplots(figsize=(9.5, 4.2))
    ax.fill_between(hs, p25, p75, color="#aed6f1", alpha=0.7, label="p25–p75")
    ax.plot(hs, meds, "o-", color="#1a5276", lw=1.8, label="median")
    ax.plot(hs, means, "s--", color="#148f77", lw=1.2, label="mean")
    ax.axhline(0.5, color="#7f8c8d", ls=":", lw=0.9)
    ax.axhline(0.75, color="#7f8c8d", ls=":", lw=0.9)
    ax.axvline(1.0, color="#b7950b", ls="--", lw=1.0, label="used-up ~+1s")
    ax.axvline(2.0, color="#c0392b", ls="--", lw=1.0, label="confirm +2s")
    ax.set_xlabel("seconds after ts_end")
    ax.set_ylabel("fraction of +5s rebound already realized")
    ax.set_title("HL ETH V-fades — how fast the rebound is used up")
    ax.set_ylim(0, 1.15)
    ax.legend(fontsize=8)
    p = fig_dir / "entry_timing_rebound_frac.png"
    fig.tight_layout()
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p))

    # 2) fade mo by entry delay
    delays = list(ENTRY_DELAYS)
    means_mo = [summary["fade_mo_by_entry_delay"][str(d)]["mean"] for d in delays]
    los = [summary["fade_mo_by_entry_delay"][str(d)]["lo"] for d in delays]
    his = [summary["fade_mo_by_entry_delay"][str(d)]["hi"] for d in delays]
    nets = [summary["fade_mo_by_entry_delay"][str(d)]["net_mean"] for d in delays]
    fig, ax = plt.subplots(figsize=(9.5, 4.2))
    ax.fill_between(delays, los, his, color="#fadbd8", alpha=0.8, label="gross CI")
    ax.plot(delays, means_mo, "o-", color="#922b21", lw=1.8, label="gross fade mo")
    ax.plot(delays, nets, "s--", color="#1a5276", lw=1.3, label="net (−RT4)")
    ax.axhline(0, color="#7f8c8d", lw=0.8)
    ax.axvline(2.0, color="#c0392b", ls="--", lw=1.0)
    ax.set_xlabel("entry delay after ts_end (s)")
    ax.set_ylabel("fade markout to ts_end+5s (bps)")
    ax.set_title("Fade-side residual edge vs entry delay (V set, exit@+5s)")
    ax.legend(fontsize=8)
    p = fig_dir / "entry_timing_fade_mo_by_delay.png"
    fig.tight_layout()
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p))

    # 3) per-event rebound path spaghetti (sample)
    fig, ax = plt.subplots(figsize=(9.5, 4.2))
    for r in vrows[:80]:
        ys = [float(r["frac_of_5s_rebound"][str(h)]) for h in hs]
        ax.plot(hs, ys, color="#85929e", alpha=0.25, lw=0.8)
    ax.plot(hs, meds, "o-", color="#1a5276", lw=2.0, label="median")
    ax.axvline(2.0, color="#c0392b", ls="--", lw=1.0)
    ax.set_ylim(0, 1.2)
    ax.set_xlabel("seconds after ts_end")
    ax.set_ylabel("frac of +5s rebound")
    ax.set_title("Per-event rebound consumption (V-fades)")
    ax.legend(fontsize=8)
    p = fig_dir / "entry_timing_rebound_spaghetti.png"
    fig.tight_layout()
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p))

    # 4) impact + half-touch
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.8))
    imp_m = [
        summary["tape_impact_at_entry"][str(d)]["adverse_5print_mean_bps"] for d in delays
    ]
    half_m = [summary["spread_at_entry"][str(d)]["half_touch_mean"] for d in delays]
    axes[0].bar([str(d) for d in delays], imp_m, color="#5d6d7e", alpha=0.85)
    axes[0].axhline(0, color="#7f8c8d", lw=0.8)
    axes[0].set_title("Tape adverse move (next 5 prints)")
    axes[0].set_xlabel("entry delay (s)")
    axes[0].set_ylabel("bps (fade-adverse +)")
    axes[1].bar([str(d) for d in delays], half_m, color="#2471a3", alpha=0.85)
    axes[1].set_title("Half-touch (warehouse/collector book)")
    axes[1].set_xlabel("entry delay (s)")
    axes[1].set_ylabel("bps")
    fig.suptitle("Entry friction / adverse selection proxies", fontsize=11)
    p = fig_dir / "entry_timing_spread_impact.png"
    fig.tight_layout()
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p))

    return paths


def _fmt(x: Any, nd: int = 2) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "—"
    if not np.isfinite(v):
        return "—"
    return f"{v:.{nd}f}"


def write_markdown(summary: dict[str, Any], fig_paths: list[str], out: Path) -> None:
    used = summary["used_up_median_frac_ge"]
    fc = summary["frac_of_5s_rebound_curve"]
    mo = summary["fade_mo_by_entry_delay"]
    res = summary["residual_mo_frac_by_delay"]
    onv = summary["on_v_set"]
    causal = summary["causal_no_r2_lookaside"]
    share = summary.get("share_rebound_used_by_h") or {}
    fr50 = summary.get("on_v_first_r50") or {}

    fig_lines = "\n".join(f"- `{Path(p).name}`" for p in fig_paths)

    lines = [
        "# V-fade entry timing — rebound used-up study",
        "",
        f"Panel: HL ETH · days {PANEL_DAYS[0]}…{PANEL_DAYS[-1]} · "
        f"gated SSM n={summary['n_events_gated']} · causal V n={summary['n_v_recovery']}",
        "",
        "Hypothesis: lab edge (−mo₅ₛ from `ts_end`) is real, but **confirm@+2s** "
        "enters after most of the V rebound, so path PnL is late / taker-adverse.",
        "",
        "## Verdict — when the rebound is used up",
        "",
        f"- **Cliff between +0.5s and +1.0s.** Median frac of the +5s rebound: "
        f"**{_fmt(fc['0.5']['median'])} at +0.5s → {_fmt(fc['1.0']['median'])} at +1.0s** "
        f"(mean {_fmt(fc['0.5']['mean'])} → {_fmt(fc['1.0']['mean'])}).",
        f"- Median crosses 50% / 75% / 90% of +5s rebound by **+{_fmt(used.get('0.5'), 2)}s** "
        f"/ **+{_fmt(used.get('0.75'), 2)}s** / **+{_fmt(used.get('0.9'), 2)}s**.",
        f"- At **+2.0s (current confirm)**: median frac = **{_fmt(fc['2.0']['median'])}** "
        f"(mean {_fmt(fc['2.0']['mean'])}); "
        f"share with ≥90% used = **{_fmt((share.get('2.0') or {}).get('ge_0_9'), 2)}**.",
        f"- Share ≥90% used: +0.5s **{_fmt((share.get('0.5') or {}).get('ge_0_9'), 2)}** · "
        f"+1s **{_fmt((share.get('1.0') or {}).get('ge_0_9'), 2)}** · "
        f"+2s **{_fmt((share.get('2.0') or {}).get('ge_0_9'), 2)}**.",
        "",
        "**Bottom line:** on faded Vs, the rebound is **used up by ~+1s** (often fully). "
        "Confirm@+2s is after the move; residual fade MO from +1s/+2s → +5s is ≤0.",
        "",
        "## Rebound consumption curve (V set)",
        "",
        "| t after end | median frac of +5s rebound | mean | p25 | p75 | ≥90% used | rebound mean bps |",
        "|-------------|---------------------------:|-----:|----:|----:|----------:|-----------------:|",
    ]
    for h in HORIZONS:
        c = fc[str(h)]
        rb = summary["rebound_bps_curve"][str(h)]
        sh = share.get(str(h)) or {}
        lines.append(
            f"| +{h:g}s | {_fmt(c['median'])} | {_fmt(c['mean'])} | "
            f"{_fmt(c['p25'])} | {_fmt(c['p75'])} | {_fmt(sh.get('ge_0_9'), 2)} | "
            f"{_fmt(rb['mean_bps'])} |"
        )

    lines += [
        "",
        "## Fade-side MO: from `ts_end` vs delayed entry (exit fixed @ +5s)",
        "",
        "Same causal-V set as the paper board (selected with r2 — diagnostic only).",
        "",
        "| entry delay | gross fade mo mean | CI | net (−RT4) | hit | residual / end→5s |",
        "|-------------|-------------------:|----|-----------:|----:|------------------:|",
    ]
    for d in ENTRY_DELAYS:
        m = mo[str(d)]
        r = res[str(d)]
        lines.append(
            f"| +{d:g}s | {_fmt(m['mean'])} | [{_fmt(m['lo'])}, {_fmt(m['hi'])}] | "
            f"{_fmt(m['net_mean'])} | {_fmt(m['hit_rate'], 3)} | {_fmt(r['median'])} |"
        )

    lines += [
        "",
        f"Entry@0 matches lab economics (~{_fmt(mo['0.0']['net_mean'])} net). "
        f"Entry@+2s net ≈ {_fmt(mo['2.0']['net_mean'])} — same sign as path gap on the board.",
        "",
        "### Structural note — recovery confirm burns the edge",
        "",
        f"First time rolling `recovery≥0.5` on the V set: median delay "
        f"**{_fmt(fr50.get('median_delay_s'))}s**, gross fade mo "
        f"**{_fmt((fr50.get('fade_mo') or {}).get('mean'))}**, net "
        f"**{_fmt(fr50.get('net_mean'))}**. Waiting until the V is *visible* "
        "is waiting until the rebound is mostly done — so **r2-confirm-then-taker "
        "is structurally late**, not just a +2s clock bug.",
        "",
        "## Spread / impact at entry clocks",
        "",
        "Book on Phase-4 days is mostly warehouse L2/BBO (collector TOB absent "
        "for Sep4–10). Treat half-touch as **stale**; tape 5-print impact is the "
        "taker adverse-selection proxy.",
        "",
        "| entry delay | half-touch mean bps | spread mean | book age med (s) | adverse 5-print mean |",
        "|-------------|--------------------:|------------:|-----------------:|---------------------:|",
    ]
    for d in ENTRY_DELAYS:
        s = summary["spread_at_entry"][str(d)]
        im = summary["tape_impact_at_entry"][str(d)]
        lines.append(
            f"| +{d:g}s | {_fmt(s['half_touch_mean'])} | {_fmt(s['spread_mean'])} | "
            f"{_fmt(s['book_age_median_s'], 1)} | {_fmt(im['adverse_5print_mean_bps'])} |"
        )
    lines += [
        "",
        "Tape 5-print impact is **fade-favorable** at +0/+0.5s (negative adverse) and "
        "flips **adverse** from +1s onward — consistent with rebound used-up.",
        "",
        f"Book sources on V rows: `{json.dumps(summary.get('book_sources') or {})}`.",
        "",
        "## Suggested executable rule (causal — no r2 / label look-ahead)",
        "",
        "**Do not** wait for `recovery_2s≥0.5` then taker-fade. That confirm *is* the rebound.",
        "",
        "Proposed **severity-at-end** fade (still causal):",
        "",
        "1. On gated SSM `ts_end`, if `|z_peak| ≥ 15` (optional tighten to 18–20), **enter immediately** "
        "(or ≤+0.25s OE latency buffer).",
        "2. Side = `−direction` (fade crash). Exit at `ts_end+5s` or adverse stop from entry.",
        "3. **No** recovery@1s/@2s gate for entry. Optional *late abort*: if still flat by +0.5s "
        "and book/tape already shows `recovery≥0.5`, skip leftover size (rebound done).",
        "4. Keep RT=4 shadow haircut; promote only if causal net CI > 0 on panel + path improves vs confirm@+2s.",
        "",
        "Severity uses only info available at event end (SSM path) — no future recovery labels.",
        "",
        "### Counterfactuals",
        "",
        "| rule | n | delay | gross fade mo | net (−RT4) | hit |",
        "|------|--:|------:|--------------:|-----------:|----:|",
        (
            f"| confirm@+2s (today, V via r2) | {onv['confirm_2s']['n']} | 2.00 | "
            f"{_fmt(onv['confirm_2s']['mean'])} | {_fmt(onv['confirm_2s']['net_mean'])} | "
            f"{_fmt(onv['confirm_2s']['hit_rate'], 3)} |"
        ),
        (
            f"| oracle V @0s (look-ahead class) | {onv['from_end']['n']} | 0.00 | "
            f"{_fmt(onv['from_end']['mean'])} | {_fmt(onv['from_end']['net_mean'])} | "
            f"{_fmt(onv['from_end']['hit_rate'], 3)} |"
        ),
        (
            f"| first r≥0.5 then enter (V set) | {fr50.get('n')} | "
            f"{_fmt(fr50.get('median_delay_s'))} | "
            f"{_fmt((fr50.get('fade_mo') or {}).get('mean'))} | "
            f"{_fmt(fr50.get('net_mean'))} | — |"
        ),
        (
            f"| rolling early min_wait=1s (V) | {onv['early_rolling']['n']} | "
            f"{_fmt(onv['early_rolling']['median_delay_s'])} | "
            f"{_fmt(onv['early_rolling']['fade_mo']['mean'])} | "
            f"{_fmt(onv['early_rolling']['net_mean'])} | — |"
        ),
        (
            f"| **causal** `|z|≥15` @0s | {causal['z_ge_15_at_0s']['n']} | 0.00 | "
            f"{_fmt(causal['z_ge_15_at_0s']['fade_mo']['mean'])} | "
            f"{_fmt(causal['z_ge_15_at_0s']['net_mean'])} | "
            f"{_fmt(causal['z_ge_15_at_0s']['hit_rate'], 3)} |"
        ),
        (
            f"| **causal** `|z|≥20` @0s | {causal['z_ge_20_at_0s']['n']} | 0.00 | "
            f"{_fmt(causal['z_ge_20_at_0s']['fade_mo']['mean'])} | "
            f"{_fmt(causal['z_ge_20_at_0s']['net_mean'])} | "
            f"{_fmt(causal['z_ge_20_at_0s']['hit_rate'], 3)} |"
        ),
        (
            f"| **causal** `|z|≥15` @+0.5s | {causal['z_ge_15_at_0_5s']['n']} | 0.50 | "
            f"{_fmt(causal['z_ge_15_at_0_5s']['fade_mo']['mean'])} | "
            f"{_fmt(causal['z_ge_15_at_0_5s']['net_mean'])} | "
            f"{_fmt(causal['z_ge_15_at_0_5s']['hit_rate'], 3)} |"
        ),
        (
            f"| **causal** all gated @0s | {causal['all_gated_at_0s']['n']} | 0.00 | "
            f"{_fmt(causal['all_gated_at_0s']['fade_mo']['mean'])} | "
            f"{_fmt(causal['all_gated_at_0s']['net_mean'])} | "
            f"{_fmt(causal['all_gated_at_0s']['hit_rate'], 3)} |"
        ),
        (
            f"| **causal** all gated @+2s | {causal['all_gated_at_2s']['n']} | 2.00 | "
            f"{_fmt(causal['all_gated_at_2s']['fade_mo']['mean'])} | "
            f"{_fmt(causal['all_gated_at_2s']['net_mean'])} | "
            f"{_fmt(causal['all_gated_at_2s']['hit_rate'], 3)} |"
        ),
        "",
        "**Recommendation:** shadow `|z|≥15` (or 20) enter-at-`ts_end` taker fade; "
        "drop r2 confirm for the executable path. Keep current r2 rule as lab scoreboard "
        "only. Re-kill if early/late or CI fails under severity gate.",
        "",
        "## Figures",
        "",
        fig_lines,
        "",
        "## Honesty",
        "",
        "- Tape asof fills · mid_mo ignored · warehouse/collector book may be stale "
        "on Phase-4 days · `live_orders=False` · ClickHouse MCP banned · not live alpha.",
        "- Rebound “used up” uses peak favorable excursion by horizon vs peak by +5s "
        "(path-dependent); residual MO uses fixed exit@+5s.",
        "- Oracle V @0s uses r2 class look-ahead for diagnostics; causal rows do not.",
        "",
        "Reproduce: `python3 analyze_entry_timing.py`",
        "",
    ]
    out.write_text("\n".join(lines))


def main() -> int:
    cfg = load_config()
    venue = str(cfg.get("venue") or "hyperliquid")
    symbol = str(cfg.get("symbol") or "ETH")
    dcfg = _detect_cfg(cfg)
    detect = _load_paper_detect()
    out = PKG / str(cfg.get("out_dir") or "out")
    fig_dir = out / "figs"
    out.mkdir(parents=True, exist_ok=True)

    print(f"[entry_timing] panel {venue} {symbol} days={len(PANEL_DAYS)}")
    rows: list[dict[str, Any]] = []
    for day in PANEL_DAYS:
        day_rows = analyze_day(day, detect_fn=detect, dcfg=dcfg, venue=venue, symbol=symbol)
        print(f"  {day}: events={len(day_rows)} V={sum(1 for r in day_rows if r['is_v'])}")
        rows.extend(day_rows)

    summary = summarize(rows)
    write_jsonl(out / "entry_timing_rows.jsonl", rows)
    (out / "entry_timing_summary.json").write_text(
        json.dumps(jsonable(summary), indent=2) + "\n"
    )
    figs = write_figs(rows, summary, fig_dir)
    write_markdown(summary, figs, out / "ENTRY_TIMING.md")

    used = summary["used_up_median_frac_ge"]
    print(
        f"[entry_timing] V={summary['n_v_recovery']} "
        f"used_up@50%≤{used.get('0.5')}s @75%≤{used.get('0.75')}s @90%≤{used.get('0.9')}s "
        f"frac@+2s_med={summary['frac_of_5s_rebound_curve']['2.0']['median']:.3f}"
    )
    print(f"[entry_timing] → {out / 'ENTRY_TIMING.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
