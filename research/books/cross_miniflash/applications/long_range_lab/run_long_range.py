#!/usr/bin/env python3
"""Long-range crash-risk strategy sims — tick tape + best-available book.

Extends strategy_lab / paper_harness over the longest clean HL ETH (and BTC)
UTC days from the listing cache + PIN usable set (~28 days).

**Reuses** ``expanded_lab`` panel rows (events/tiers) when present and imports
quote stubs from ``expanded_lab.strategies`` (`ladder_plus_v_restore`,
`confirm_before_restore`, `ladder_plus_confirm_before_restore`). This package
owns multi-day marked-maker equity / inventory / DD paths — not a fork of the
event-study scoreboard.

Strategies (overlays on shadow maker — risk policy, not alpha):
  1. baseline_maker
  2. kill_ladder_maker
  3. nanex_temp_pull
  4. ladder_plus_v_restore / confirm_before_restore (expanded_lab stubs)
  5. ladder_plus_confirm_before_restore (combined best)

Fills at trade print + fill_i (strategy_lab integrity). ClickHouse MCP banned.
"""

from __future__ import annotations

import argparse
import json
import sys
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
STARTARB = Path("/home/dev/srv/ares-startarb")
WAREHOUSE_SRC = Path("/home/dev/lab/lab-n2070/warehouse/src")
OUT = LAB / "out"
FIG = OUT / "figs"
DAYS_DIR = OUT / "days"
SCRIPTS_APP = APP / "scripts"
STRATEGY_LAB = APP / "strategy_lab"
EXPANDED = APP / "expanded_lab"
PAPER = APP / "paper_harness"
EXPANDED_PANEL_DIR = EXPANDED / "out" / "panel"
PIN_SUMMARY = (
    ROOT
    / "research/books/empirical_mm/out/ch15_pin/exp_ch15_eth_summary.json"
)
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
THIN_PUBLIC_MD = {"2026-09-12", "2026-09-13", "2026-09-23", "2026-09-24", "2026-09-28", "2026-09-29"}
PANEL_CORE = [
    "2026-09-04",
    "2026-09-05",
    "2026-09-06",
    "2026-09-07",
    "2026-09-08",
    "2026-09-09",
    "2026-09-10",
]

for p in (
    str(LAB),
    str(PAPER),
    str(APP),
    str(SCRIPTS_APP),
    str(BOOK / "scripts"),
    str(ROOT),
    str(STARTARB / "src"),
    str(WAREHOUSE_SRC),
    str(EXPANDED),  # before strategy_lab so strategy_lab wins `strategies`
    str(STRATEGY_LAB),  # must be last insert(0) → front of path for BaselineMaker etc.
):
    if p not in sys.path:
        sys.path.insert(0, p)

from _common import (  # noqa: E402
    FRICTION_BPS,
    assign_ladder_tiers,
    early_late_by_day,
    save_fig,
    save_json,
)
from _data import LISTING_CACHE, day_completeness, ensure_env, load_day_trades, normalize_side  # noqa: E402
from research.lib.crash import recovery_fraction  # noqa: E402
from harness.detect import detect_day  # noqa: E402
from sim.book import book_meta, load_best_book  # noqa: E402
from sim.engine import SimConfig, run_tick_sim  # noqa: E402
from sim.metrics import early_late_metrics, equity_stats, max_drawdown  # noqa: E402
from strategies import (  # noqa: E402  — strategy_lab baseline / ladder / nanex / clock
    BaselineMaker,
    KillLadderOverlay,
    NanexTemporaryPull,
    build_event_clock,
)
# expanded_lab quote stubs (shared package under applications/)
from expanded_lab.strategies import (  # noqa: E402
    ConfirmBeforeRestore,
    LadderPlusConfirmBeforeRestore,
    LadderPlusVRestore,
)

NS = 1_000_000_000
STRAT_NAMES = [
    "baseline_maker",
    "kill_ladder_maker",
    "nanex_temp_pull",
    "ladder_plus_v_restore",
    "confirm_before_restore",
    "ladder_plus_confirm_before_restore",
]
FIRE_TIERS = {"widen", "size_cap", "halt"}


def load_expanded_panel() -> dict[str, Any]:
    """Load sibling expanded_lab panel cache (events/tiers); empty if missing."""
    meta_p = EXPANDED_PANEL_DIR / "panel_meta.json"
    rows_p = EXPANDED_PANEL_DIR / "panel_rows.json"
    if not meta_p.exists() or not rows_p.exists():
        return {"meta": {}, "rows": [], "by_key": {}, "available": False}
    meta = json.loads(meta_p.read_text())
    rows = json.loads(rows_p.read_text())
    by_key: dict[tuple, dict] = {}
    for r in rows:
        if r.get("skip") or not r.get("events"):
            continue
        by_key[(r.get("day"), r.get("symbol"), r.get("venue"))] = r
    return {"meta": meta, "rows": rows, "by_key": by_key, "available": True}


def jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, float)):
        x = float(obj)
        return x if np.isfinite(x) else None
    # bool is a subclass of int — must check before int
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if obj is None:
        return None
    return str(obj)


def candidate_days(*, prefer_pin: bool = True) -> list[str]:
    """Union of listing-cache HL days + PIN usable + Phase-4 panel."""
    days: set[str] = set(PANEL_CORE) | set(PIN_USABLE)
    root = LISTING_CACHE / "mercat-hyperliquid-md"
    if root.is_dir():
        days |= {p.stem for p in root.glob("*.json")}
    if prefer_pin and PIN_SUMMARY.exists():
        try:
            meta = json.loads(PIN_SUMMARY.read_text())
            keys = (meta.get("mle") or {}).get("day_keys") or meta.get("day_keys")
            if not keys:
                # fall back to day_meta keys with span ≥ 4h / n ≥ 400
                dm = meta.get("day_meta") or {}
                keys = [
                    d
                    for d, v in dm.items()
                    if float(v.get("span_h") or 0) >= 4.0 and int(v.get("n") or 0) >= 400
                ]
            days |= set(keys)
        except Exception:  # noqa: BLE001
            pass
    return sorted(days)


def probe_day(venue: str, symbol: str, day: str) -> dict[str, Any]:
    """Load tape completeness without full detect (coverage table)."""
    ensure_env()
    try:
        rec = load_day_trades(venue, symbol, day, quiet=True)
    except Exception as exc:  # noqa: BLE001
        return {
            "day": day,
            "symbol": symbol,
            "venue": venue,
            "included": False,
            "reason": f"load:{type(exc).__name__}: {exc}",
            "complete": False,
            "n_trades": 0,
        }
    flags = rec.get("completeness") or day_completeness(rec["tape"], day)
    complete = bool(flags.get("complete"))
    thin = day in THIN_PUBLIC_MD
    reason = ""
    if thin and not complete:
        reason = "thin_public_md"
    elif not complete:
        reason = ",".join(flags.get("reasons") or ["incomplete"])
    elif flags.get("n", 0) < 500:
        reason = "n<500"
        complete = False
    return {
        "day": day,
        "symbol": symbol,
        "venue": venue,
        "included": bool(complete and not thin),
        "reason": reason or ("ok" if complete else "incomplete"),
        "complete": bool(complete),
        "n_trades": int(flags.get("n") or 0),
        "span_s": float(flags.get("span_s") or 0),
        "coverage": float(flags.get("coverage") or 0),
        "pin_usable": bool(day in PIN_USABLE),
        "panel_core": bool(day in PANEL_CORE),
        "thin_public_md": bool(thin),
    }


def _assert_fills_on_tape(r: dict[str, Any]) -> None:
    fpx = np.asarray(r.get("fill_px", []), dtype=np.float64)
    if fpx.size == 0:
        return
    ts_arr = np.asarray(r["ts"], dtype=np.int64)
    px_arr = np.asarray(r["px"], dtype=np.float64)
    fi = np.asarray(r.get("fill_i", []), dtype=np.int64)
    fts = np.asarray(r["fill_ts"], dtype=np.int64)
    if fi.size != fpx.size:
        raise AssertionError("fill_i missing/mismatched — refuse stale bid/ask fills")
    for j in range(fpx.size):
        i = int(fi[j])
        if i < 0 or i >= px_arr.size:
            raise AssertionError(f"fill_i={i} OOB")
        if int(ts_arr[i]) != int(fts[j]) or not np.isclose(px_arr[i], fpx[j], rtol=0.0, atol=1e-6):
            raise AssertionError(
                f"fill[{j}] not on tape print — px={fpx[j]} vs tape[{i}]={px_arr[i]}"
            )


def _attach_recovery_horizons(events: dict, ts: np.ndarray, px: np.ndarray) -> dict:
    ts_end = np.asarray(events.get("ts_end", []), dtype=np.int64)
    direction = np.asarray(events.get("direction", []), dtype=np.float64)
    ts_start = np.asarray(events.get("ts_start", []), dtype=np.int64)
    n = ts_end.size
    if n == 0:
        events = dict(events)
        events["recovery_1s"] = []
        events["recovery_2s"] = []
        return events
    end_i = np.clip(np.searchsorted(ts, ts_end, side="left"), 0, max(ts.size - 1, 0))
    start_i = np.clip(np.searchsorted(ts, ts_start, side="left"), 0, max(ts.size - 1, 0))
    if direction.size != n:
        dp = np.asarray(events.get("dp_pct", np.zeros(n)), dtype=np.float64)
        direction = np.sign(dp)
        direction[direction == 0] = -1.0
    r1 = recovery_fraction(ts, px, start_i, end_i, direction, horizon_s=1.0)
    r2 = recovery_fraction(ts, px, start_i, end_i, direction, horizon_s=2.0)
    events = dict(events)
    events["recovery_1s"] = r1.tolist()
    events["recovery_2s"] = r2.tolist()
    return events


def _downsample_tape(tape: dict[str, np.ndarray], *, max_trades: int) -> dict[str, np.ndarray]:
    n = int(tape["ts"].size)
    if n <= max_trades:
        return tape
    step = int(np.ceil(n / max_trades))
    idx = np.arange(0, n, step)
    return {k: (v[idx] if isinstance(v, np.ndarray) and v.shape == (n,) else v) for k, v in tape.items()}


def _events_to_dict(events: dict[str, Any]) -> dict[str, Any]:
    """Normalize detect_day event arrays to lists for clock / JSON."""
    out = {}
    for k, v in events.items():
        if isinstance(v, np.ndarray):
            out[k] = v.tolist() if v.dtype != object else [str(x) for x in v.tolist()]
        else:
            out[k] = v
    return out


def _fire_risk_stats(events: dict[str, Any]) -> dict[str, Any]:
    tiers = [str(t) for t in events.get("tier", [])]
    labels = [str(l) for l in events.get("recovery_label", [])]
    mo5 = np.asarray(events.get("mo_5s", []), dtype=np.float64)
    n = len(tiers)
    fire_i = [i for i, t in enumerate(tiers) if t in FIRE_TIERS]
    ctrl_i = [i for i, t in enumerate(tiers) if t == "observe"]
    n_fire = len(fire_i)
    n_v_fire = sum(1 for i in fire_i if i < len(labels) and labels[i] == "v_recovery")
    fp_v_rate = float(n_v_fire / n_fire) if n_fire else float("nan")
    adv_fire = np.abs(mo5[fire_i]) if fire_i and mo5.size == n else np.asarray([], dtype=np.float64)
    adv_ctrl = np.abs(mo5[ctrl_i]) if ctrl_i and mo5.size == n else np.asarray([], dtype=np.float64)
    return {
        "n_events": n,
        "n_fire": n_fire,
        "n_control": len(ctrl_i),
        "tier_counts": {t: tiers.count(t) for t in sorted(set(tiers))},
        "fp_v_recovery_rate": fp_v_rate,
        "n_v_among_fire": n_v_fire,
        "adverse_mo5_fire_mean": float(np.nanmean(adv_fire)) if adv_fire.size else float("nan"),
        "adverse_mo5_control_mean": float(np.nanmean(adv_ctrl)) if adv_ctrl.size else float("nan"),
        "nanex_fire_n": int(
            sum(
                1
                for i in fire_i
                if i < len(events.get("nanex_overlap", []))
                and bool(list(events.get("nanex_overlap", []))[i])
            )
        ),
    }


def simulate_cell(
    day: str,
    symbol: str,
    venue: str,
    *,
    friction_bps: float,
    max_trades: int,
    ladder_breaks: dict[str, float] | None = None,
    keep_full: bool = False,
    panel_events: dict[str, Any] | None = None,
    panel_source: str | None = None,
) -> dict[str, Any]:
    """Detect (paper_harness or expanded panel) → book → strategy_lab tick sims."""
    events_from_panel = panel_events is not None and bool(panel_events.get("ts_end"))
    if events_from_panel:
        # Still need tape + completeness from loader; reuse expanded_lab events/tiers
        ensure_env()
        try:
            rec = load_day_trades(venue, symbol, day, quiet=True)
        except Exception as exc:  # noqa: BLE001
            return {
                "day": day,
                "symbol": symbol,
                "venue": venue,
                "skip": f"tape:{exc}",
                "complete": False,
                "n_trades": 0,
            }
        complete = bool(rec.get("completeness", {}).get("complete"))
        if not complete:
            return {
                "day": day,
                "symbol": symbol,
                "venue": venue,
                "skip": "incomplete",
                "complete": False,
                "n_trades": int(rec.get("completeness", {}).get("n") or 0),
                "completeness": rec.get("completeness"),
            }
        tape = rec["tape"]
        events = _events_to_dict(dict(panel_events))
        cell_meta = {"panel_reuse": panel_source or "expanded_lab"}
    else:
        cell = detect_day(venue, symbol, day, quiet=True)
        if cell.get("skip"):
            return {
                "day": day,
                "symbol": symbol,
                "venue": venue,
                "skip": cell["skip"],
                "complete": cell.get("complete"),
                "n_trades": cell.get("n_trades", 0),
            }
        if not cell.get("complete"):
            return {
                "day": day,
                "symbol": symbol,
                "venue": venue,
                "skip": "incomplete",
                "complete": False,
                "n_trades": cell.get("n_trades", 0),
                "completeness": cell.get("completeness"),
            }
        tape = cell["tape"]
        events = _events_to_dict(cell["events"])
        cell_meta = {"panel_reuse": None}

    ts = np.asarray(tape["ts"], dtype=np.int64)
    px = np.asarray(tape["px"], dtype=np.float64)
    qty = np.asarray(tape["qty"], dtype=np.float64)
    side = normalize_side(tape["side"])
    if ts.size < 500:
        return {"day": day, "symbol": symbol, "venue": venue, "skip": "thin_tape", "n_trades": int(ts.size)}

    # re-tier with pooled breaks when provided (and not already tiered from panel)
    if ladder_breaks and events.get("z_peak"):
        flat = [
            {
                "z_peak": float(events["z_peak"][i]),
                "intensity_60s": int(events["intensity_60s"][i]) if i < len(events.get("intensity_60s", [])) else 1,
                "nanex_overlap": bool(events["nanex_overlap"][i]) if i < len(events.get("nanex_overlap", [])) else False,
                "dp_pct": float(events["dp_pct"][i]) if i < len(events.get("dp_pct", [])) else 0.0,
            }
            for i in range(len(events["z_peak"]))
        ]
        from _common import ladder_tier

        events["tier"] = [
            ladder_tier(
                e["z_peak"],
                intensity=e["intensity_60s"],
                nanex_overlap=e["nanex_overlap"],
                dp_pct=e["dp_pct"],
                z_breaks=ladder_breaks,
                dp_p90=float(ladder_breaks.get("dp_p90", 0.45)),
            )
            for e in flat
        ]

    events = _attach_recovery_horizons(events, ts, px)
    fire_stats = _fire_risk_stats(events)

    book = load_best_book(venue, symbol, day, prefer_collector=True, attach_l2_depth=False)
    if book is not None and book.n >= 10:
        asof = book.asof(ts)
        mid, bid, ask = asof["mid"], asof["bid"], asof["ask"]
        miss = ~np.isfinite(mid) | (mid <= 0)
        mid = mid.copy()
        mid[miss] = px[miss]
        bid = np.where(np.isfinite(bid) & (bid > 0), bid, mid * (1 - 0.5e-4))
        ask = np.where(np.isfinite(ask) & (ask > 0), ask, mid * (1 + 0.5e-4))
        bmeta = book_meta(book)
    else:
        mid = px.copy()
        bid = px * (1 - 0.5e-4)
        ask = px * (1 + 0.5e-4)
        bmeta = {"available": False, "source": "tape_proxy", "n": 0, "median_dt_s": None}

    packed = _downsample_tape(
        {"ts": ts, "px": px, "qty": qty, "side": side, "mid": mid, "bid": bid, "ask": ask},
        max_trades=max_trades,
    )
    clock = build_event_clock(packed["ts"], events)
    cfg = SimConfig(base_size=0.25, friction_bps=friction_bps, max_inventory=2.0)
    strategies = [
        BaselineMaker(base_size=cfg.base_size),
        KillLadderOverlay(clock=clock, base_size=cfg.base_size),
        NanexTemporaryPull(clock=clock, base_size=cfg.base_size),
        LadderPlusVRestore(clock=clock, base_size=cfg.base_size),
        ConfirmBeforeRestore(clock=clock, base_size=cfg.base_size),
        LadderPlusConfirmBeforeRestore(clock=clock, base_size=cfg.base_size),
    ]
    results: dict[str, Any] = {}
    for strat in strategies:
        sim = run_tick_sim(
            ts=packed["ts"],
            px=packed["px"],
            side=packed["side"],
            qty=packed["qty"],
            mid=packed["mid"],
            bid=packed["bid"],
            ask=packed["ask"],
            strategy=strat,
            cfg=cfg,
        )
        st = equity_stats(sim.equity_bps)
        block = {
            "final_equity_bps": st["final_bps"],
            "max_dd_bps": st["max_dd_bps"],
            "n_fills": sim.n_fills,
            "mean_step_bps": st["mean_step_bps"],
            "sharpe_like": st["sharpe_like"],
            "final_inv": sim.meta["final_inv"],
            "equity_bps": sim.equity_bps,
            "inventory": sim.inventory,
            "regime": sim.regime,
            "fill_ts": sim.fill_ts,
            "fill_side": sim.fill_side,
            "fill_px": sim.fill_px,
            "fill_i": sim.fill_i,
            "ts": sim.ts,
            "px": sim.px,
            "mid": sim.mid,
        }
        _assert_fills_on_tape(block)
        results[strat.name] = block

    return {
        "day": day,
        "symbol": symbol,
        "venue": venue,
        "complete": True,
        "n_trades": int(packed["ts"].size),
        "n_events": int(len(events.get("ts_end", []))),
        "book": bmeta,
        "fire_stats": fire_stats,
        "events_slim": {
            "ts_end": events.get("ts_end", []),
            "tier": events.get("tier", []),
            "recovery_label": events.get("recovery_label", []),
            "mo_5s": events.get("mo_5s", []),
            "nanex_overlap": events.get("nanex_overlap", []),
            "dp_pct": events.get("dp_pct", []),
        },
        "results": results,
        "keep_full": keep_full,
        "panel_reuse": cell_meta.get("panel_reuse"),
        "error": None,
    }


def _cell_worker(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        out = simulate_cell(
            payload["day"],
            payload["symbol"],
            payload["venue"],
            friction_bps=payload["friction_bps"],
            max_trades=payload["max_trades"],
            ladder_breaks=payload.get("ladder_breaks"),
            keep_full=payload.get("keep_full", False),
            panel_events=payload.get("panel_events"),
            panel_source=payload.get("panel_source"),
        )
        if out.get("skip") or "results" not in out:
            return out
        keep_full = bool(out.get("keep_full"))
        slim_results = {}
        for name, r in out["results"].items():
            slim = {
                "final_equity_bps": r["final_equity_bps"],
                "max_dd_bps": r["max_dd_bps"],
                "n_fills": r["n_fills"],
                "mean_step_bps": r["mean_step_bps"],
                "sharpe_like": r["sharpe_like"],
                "final_inv": r["final_inv"],
            }
            if keep_full:
                slim.update(
                    {
                        "ts": r["ts"],
                        "px": r["px"],
                        "mid": r["mid"],
                        "equity_bps": r["equity_bps"],
                        "inventory": r["inventory"],
                        "regime": r["regime"],
                        "fill_ts": r["fill_ts"],
                        "fill_side": r["fill_side"],
                        "fill_px": r["fill_px"],
                        "fill_i": r["fill_i"],
                    }
                )
            slim_results[name] = slim
        return {
            "day": out["day"],
            "symbol": out["symbol"],
            "venue": out["venue"],
            "complete": True,
            "n_trades": out["n_trades"],
            "n_events": out["n_events"],
            "book": out["book"],
            "fire_stats": out["fire_stats"],
            "events_slim": out["events_slim"],
            "results": slim_results,
            "keep_full": keep_full,
            "panel_reuse": out.get("panel_reuse"),
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "day": payload.get("day"),
            "symbol": payload.get("symbol"),
            "venue": payload.get("venue"),
            "error": f"{type(exc).__name__}: {exc}",
            "trace": traceback.format_exc()[-2000:],
        }


def _pool_equity(cells: list[dict], strat: str) -> dict[str, Any]:
    finals, dds, fills = [], [], []
    by_day: dict[str, list[float]] = {}
    inv_abs = []
    for c in cells:
        r = (c.get("results") or {}).get(strat)
        if not r:
            continue
        fe = r["final_equity_bps"]
        if fe is None or not np.isfinite(fe):
            continue
        finals.append(float(fe))
        dds.append(float(r["max_dd_bps"]) if np.isfinite(r.get("max_dd_bps", np.nan)) else float("nan"))
        fills.append(int(r["n_fills"]))
        by_day.setdefault(c["day"], []).append(float(fe))
        if r.get("final_inv") is not None and np.isfinite(r["final_inv"]):
            inv_abs.append(abs(float(r["final_inv"])))
    day_eq = {d: float(np.mean(v)) for d, v in by_day.items()}
    # cumulative equity across chronological days (mean per day if multi-symbol)
    cum = []
    running = 0.0
    for d in sorted(day_eq):
        running += day_eq[d]
        cum.append({"day": d, "cum_equity_bps": running, "day_equity_bps": day_eq[d]})
    return {
        "n_cells": len(finals),
        "final_equity_bps": {
            "mean": float(np.mean(finals)) if finals else float("nan"),
            "median": float(np.median(finals)) if finals else float("nan"),
            "sum": float(np.sum(finals)) if finals else float("nan"),
        },
        "max_dd_bps": {
            "mean": float(np.nanmean(dds)) if dds else float("nan"),
            "median": float(np.nanmedian(dds)) if dds else float("nan"),
        },
        "abs_final_inv_mean": float(np.mean(inv_abs)) if inv_abs else float("nan"),
        "n_fills_total": int(np.sum(fills)) if fills else 0,
        "by_day_mean_final": day_eq,
        "cumulative_by_day": cum,
    }


def _delta_vs_baseline(cells: list[dict], strat: str) -> dict[str, Any]:
    deltas = []
    for c in cells:
        b = (c.get("results") or {}).get("baseline_maker", {})
        s = (c.get("results") or {}).get(strat, {})
        if not b or not s:
            continue
        bf, sf = b.get("final_equity_bps"), s.get("final_equity_bps")
        if bf is None or sf is None:
            continue
        if np.isfinite(bf) and np.isfinite(sf):
            deltas.append(float(sf) - float(bf))
    a = np.asarray(deltas, dtype=np.float64)
    if a.size == 0:
        return {"n": 0, "delta_mean": float("nan"), "lo": float("nan"), "hi": float("nan"), "frac_positive": float("nan")}
    from research.lib.stats import bootstrap_ci

    boot = bootstrap_ci(a, n_boot=800, seed=42)
    return {
        "n": int(a.size),
        "delta_mean": float(a.mean()),
        "lo": boot["lo"],
        "hi": boot["hi"],
        "frac_positive": float(np.mean(a > 0)),
    }


def _dd_delta_vs_baseline(cells: list[dict], strat: str) -> dict[str, Any]:
    """Positive = overlay has less severe (higher / closer-to-zero) max DD."""
    deltas = []
    for c in cells:
        b = (c.get("results") or {}).get("baseline_maker", {})
        s = (c.get("results") or {}).get(strat, {})
        if not b or not s:
            continue
        bd, sd = b.get("max_dd_bps"), s.get("max_dd_bps")
        if bd is None or sd is None:
            continue
        if np.isfinite(bd) and np.isfinite(sd):
            deltas.append(float(sd) - float(bd))  # less negative is better
    a = np.asarray(deltas, dtype=np.float64)
    if a.size == 0:
        return {"n": 0, "delta_mean": float("nan")}
    return {"n": int(a.size), "delta_mean": float(a.mean()), "median": float(np.median(a))}


def aggregate_fire_scoreboard(cells: list[dict]) -> dict[str, Any]:
    n_fire = n_ctrl = n_v = 0
    adv_f, adv_c = [], []
    for c in cells:
        fs = c.get("fire_stats") or {}
        nf = int(fs.get("n_fire") or 0)
        nc = int(fs.get("n_control") or 0)
        n_fire += nf
        n_ctrl += nc
        n_v += int(fs.get("n_v_among_fire") or 0)
        if nf and np.isfinite(fs.get("adverse_mo5_fire_mean", np.nan)):
            adv_f.extend([float(fs["adverse_mo5_fire_mean"])] * nf)
        if nc and np.isfinite(fs.get("adverse_mo5_control_mean", np.nan)):
            adv_c.extend([float(fs["adverse_mo5_control_mean"])] * nc)
    return {
        "n_fire": n_fire,
        "n_control": n_ctrl,
        "fp_v_recovery_rate": float(n_v / n_fire) if n_fire else float("nan"),
        "n_v_among_fire": n_v,
        "adverse_mo5_fire_mean": float(np.mean(adv_f)) if adv_f else float("nan"),
        "adverse_mo5_control_mean": float(np.mean(adv_c)) if adv_c else float("nan"),
        "delta_adverse_mo5": (
            float(np.mean(adv_f) - np.mean(adv_c)) if adv_f and adv_c else float("nan")
        ),
    }


def pick_winner(strat_summary: dict[str, Any]) -> dict[str, Any]:
    """Rank overlays on risk: better max_dd (less severe), then Δ equity vs baseline."""
    ranked = []
    for name in STRAT_NAMES:
        if name == "baseline_maker":
            continue
        block = strat_summary[name]
        dd = float(block["pool"]["max_dd_bps"]["mean"])
        d_eq = float(block["delta_vs_baseline"]["delta_mean"])
        d_dd = float(block["dd_vs_baseline"]["delta_mean"])
        # score: prefer higher DD delta (less drawdown) then higher equity delta
        ranked.append((name, d_dd, d_eq, dd))
    ranked.sort(key=lambda x: (-x[1], -x[2]))
    best = ranked[0][0] if ranked else None
    return {
        "ranked": [r[0] for r in ranked],
        "best": best,
        "note": "Ranked by mean ΔmaxDD vs baseline (less severe first), then Δequity",
    }


def plot_all(cells: list[dict], summary: dict, coverage: list[dict]) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    # 1) Coverage heatmap-ish table as bar
    fig, ax = plt.subplots(figsize=(12, 3.2))
    days = sorted({c["day"] for c in coverage})
    ins = {c["day"] for c in coverage if c.get("included") and c.get("symbol") == "ETH"}
    outs = [d for d in days if d not in ins]
    ax.bar(range(len(days)), [1 if d in ins else 0 for d in days], color=["#27ae60" if d in ins else "#c0392b" for d in days])
    ax.set_xticks(range(len(days)))
    ax.set_xticklabels([d[5:] for d in days], rotation=90, fontsize=7)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["out", "in"])
    ax.set_title(f"HL ETH day coverage — in={len(ins)} out={len(outs)} (red=thin/incomplete)")
    p = FIG / "coverage_days.png"
    save_fig(p)
    paths.append(str(p))

    # 2) Cumulative equity by strategy
    fig, ax = plt.subplots(figsize=(11, 4.5))
    for name in STRAT_NAMES:
        cum = summary["strategies"][name]["pool"]["cumulative_by_day"]
        if not cum:
            continue
        ax.plot([c["day"][5:] for c in cum], [c["cum_equity_bps"] for c in cum], label=name, lw=1.3, marker="o", ms=3)
    ax.axhline(0, color="k", lw=0.5, alpha=0.4)
    ax.set_title("Cumulative marked equity across long-range days (bps of ref)")
    ax.set_ylabel("cum equity (bps)")
    ax.legend(fontsize=7, ncol=2)
    plt.xticks(rotation=60, ha="right", fontsize=7)
    p = FIG / "equity_cumulative.png"
    save_fig(p)
    paths.append(str(p))

    # 3) Drawdown comparison bars
    fig, ax = plt.subplots(figsize=(9, 4))
    names = STRAT_NAMES
    dds = [summary["strategies"][n]["pool"]["max_dd_bps"]["mean"] for n in names]
    ax.bar(names, dds, color="#e74c3c", alpha=0.8)
    ax.set_ylabel("mean max DD (bps)")
    ax.set_title("Mean max drawdown by strategy (less severe = closer to 0)")
    plt.xticks(rotation=25, ha="right")
    p = FIG / "drawdown_scoreboard.png"
    save_fig(p)
    paths.append(str(p))

    # 4) Δ vs baseline
    fig, ax = plt.subplots(figsize=(9, 4))
    names = [s for s in STRAT_NAMES if s != "baseline_maker"]
    deltas = [summary["strategies"][s]["delta_vs_baseline"]["delta_mean"] for s in names]
    los = [summary["strategies"][s]["delta_vs_baseline"]["lo"] for s in names]
    his = [summary["strategies"][s]["delta_vs_baseline"]["hi"] for s in names]
    yerr = np.vstack([np.asarray(deltas) - np.asarray(los), np.asarray(his) - np.asarray(deltas)])
    ax.bar(names, deltas, yerr=yerr, color="#3498db", alpha=0.85, capsize=4)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_ylabel("Δ final equity vs baseline (bps)")
    ax.set_title("Overlay value vs always-on maker (cell-pooled)")
    plt.xticks(rotation=25, ha="right")
    p = FIG / "delta_vs_baseline.png"
    save_fig(p)
    paths.append(str(p))

    # 5) Risk scoreboard — fire adverse / FP V
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    fs = summary["fire_scoreboard"]
    axes[0].bar(
        ["fire |mo5|", "control |mo5|"],
        [fs.get("adverse_mo5_fire_mean") or 0, fs.get("adverse_mo5_control_mean") or 0],
        color=["#c0392b", "#7f8c8d"],
    )
    axes[0].set_title("Adverse |markout 5s| after gated events")
    axes[0].set_ylabel("bps")
    axes[1].bar(["FP V-recovery rate", "fires", "controls"], [
        fs.get("fp_v_recovery_rate") or 0,
        fs.get("n_fire") or 0,
        fs.get("n_control") or 0,
    ], color=["#8e44ad", "#e67e22", "#95a5a6"])
    axes[1].set_title(f"Fire counts + FP V rate (n_fire={fs.get('n_fire')})")
    for ax in axes:
        plt.sca(ax)
        plt.xticks(rotation=15, ha="right", fontsize=8)
    p = FIG / "risk_scoreboard.png"
    save_fig(p)
    paths.append(str(p))

    # 6) Early / late
    fig, ax = plt.subplots(figsize=(9, 4))
    for strat, color in (
        ("kill_ladder_maker", "#c0392b"),
        ("nanex_temp_pull", "#8e44ad"),
        ("ladder_plus_v_restore", "#16a085"),
        ("confirm_before_restore", "#d35400"),
        ("ladder_plus_confirm_before_restore", "#2980b9"),
    ):
        el = summary["strategies"][strat]["early_late"]
        ax.bar(
            [f"{strat[:12]}\nearly", f"{strat[:12]}\nlate"],
            [el["early_mean_final_bps"], el["late_mean_final_bps"]],
            color=color,
            alpha=0.75,
        )
    ax.axhline(0, color="k", lw=0.5)
    ax.set_ylabel("mean day final equity (bps)")
    ax.set_title("Early vs late half stability")
    p = FIG / "early_late_split.png"
    save_fig(p)
    paths.append(str(p))

    # 7) Example day zoom — richest HL ETH
    hl = [c for c in cells if c.get("keep_full") and c.get("results") and c.get("symbol") == "ETH"]
    if hl:
        focus = max(hl, key=lambda c: int(c.get("n_events") or 0))
        # equity curves
        fig, ax = plt.subplots(figsize=(11, 4.2))
        for name in STRAT_NAMES:
            r = focus["results"].get(name)
            if not r or "equity_bps" not in r:
                continue
            t = (np.asarray(r["ts"], dtype=np.float64) - float(r["ts"][0])) / NS / 3600.0
            ax.plot(t, r["equity_bps"], label=name, lw=1.1)
        ax.axhline(0, color="k", lw=0.4, alpha=0.4)
        ax.set_xlabel("hours from day start")
        ax.set_ylabel("equity (bps)")
        ax.set_title(
            f"Example day equity — {focus['venue']} {focus['symbol']} {focus['day']} "
            f"(events={focus['n_events']}, book={focus['book'].get('source')})"
        )
        ax.legend(fontsize=7, ncol=2)
        p = FIG / "example_day_equity.png"
        save_fig(p)
        paths.append(str(p))

        # price + fills + ladder shades
        r = focus["results"].get("kill_ladder_maker")
        if r and "px" in r:
            fig, ax = plt.subplots(figsize=(11, 4.2))
            t = (np.asarray(r["ts"], dtype=np.float64) - float(r["ts"][0])) / NS / 3600.0
            ax.plot(t, r["px"], color="#2c3e50", lw=0.7, label="trade px")
            reg = np.asarray(r["regime"], dtype=object)
            for label, color, alpha in (
                ("halt", "#e74c3c", 0.25),
                ("size_cap", "#e67e22", 0.18),
                ("widen", "#f1c40f", 0.12),
            ):
                m = reg == label
                if not m.any():
                    continue
                idx = np.where(m)[0]
                breaks = np.where(np.diff(idx) > 1)[0]
                starts = np.r_[idx[0], idx[breaks + 1]]
                ends = np.r_[idx[breaks], idx[-1]]
                for a, b in zip(starts, ends):
                    ax.axvspan(t[a], t[b], color=color, alpha=alpha, lw=0)
            if len(r.get("fill_ts", [])):
                fts = np.asarray(r["fill_ts"], dtype=np.int64)
                fpx = np.asarray(r["fill_px"], dtype=np.float64)
                fside = np.asarray(r["fill_side"], dtype=np.int64)
                ts_arr = np.asarray(r["ts"], dtype=np.int64)
                px_arr = np.asarray(r["px"], dtype=np.float64)
                fi = np.asarray(r.get("fill_i", []), dtype=np.int64)
                t0 = float(ts_arr[0])
                if fi.size == fpx.size and fi.size and int(fi.max()) < px_arr.size:
                    ft = (ts_arr[fi].astype(np.float64) - t0) / NS / 3600.0
                    fy = px_arr[fi]
                else:
                    ft = (fts.astype(np.float64) - t0) / NS / 3600.0
                    fy = fpx
                ax.scatter(ft[fside > 0], fy[fside > 0], s=8, c="#27ae60", label="buy fill", zorder=5)
                ax.scatter(ft[fside < 0], fy[fside < 0], s=8, c="#c0392b", label="sell fill", zorder=5)
            ax.set_title(f"Price + ladder shades + fills — {focus['day']} ETH")
            ax.legend(fontsize=7, loc="best")
            p = FIG / "example_day_price_fills.png"
            save_fig(p)
            paths.append(str(p))

        # inventory
        fig, ax = plt.subplots(figsize=(11, 3.5))
        for name in ("baseline_maker", "kill_ladder_maker", "ladder_plus_confirm_before_restore"):
            r = focus["results"].get(name)
            if not r or "inventory" not in r:
                continue
            t = (np.asarray(r["ts"], dtype=np.float64) - float(r["ts"][0])) / NS / 3600.0
            ax.plot(t, r["inventory"], label=name, lw=1.0)
        ax.set_title(f"Inventory path — {focus['day']} ETH")
        ax.set_ylabel("coins")
        ax.legend(fontsize=8)
        p = FIG / "example_day_inventory.png"
        save_fig(p)
        paths.append(str(p))

        summary["focus_cell"] = {
            "day": focus["day"],
            "symbol": focus["symbol"],
            "venue": focus["venue"],
            "n_events": focus["n_events"],
            "book": focus["book"],
        }

    # 8) Book source honesty
    fig, ax = plt.subplots(figsize=(9, 3.5))
    sources: dict[str, int] = {}
    for c in cells:
        src = str((c.get("book") or {}).get("source") or "none")
        # collapse iid suffixes for readability
        key = src.split(":iid=")[0] if ":iid=" in src else src
        sources[key] = sources.get(key, 0) + 1
    ax.bar(list(sources.keys()), list(sources.values()), color="#7f8c8d")
    ax.set_title("Book source counts (cadence honesty)")
    ax.set_ylabel("# cells")
    plt.xticks(rotation=20, ha="right")
    p = FIG / "book_source_counts.png"
    save_fig(p)
    paths.append(str(p))

    return paths


def build_notebook(summary: dict) -> Path:
    import nbformat as nbf

    nb = nbf.v4.new_notebook()
    best = (summary.get("winner") or {}).get("best")
    span = summary.get("date_span") or {}
    cells = []
    cells.append(
        nbf.v4.new_markdown_cell(
            f"""# Long-range crash-risk strategies — tick + order book

**Primary deliverable** for multi-day marked-maker equity under crash risk overlays.

| | |
|--|--|
| Date span | **{span.get('first')} → {span.get('last')}** |
| Days in | **{summary.get('n_days_in')}** (ETH) · probed {summary.get('n_days_probed')} |
| Venue focus | Hyperliquid (Deribit TOB when joined for book honesty) |
| Friction | **{summary.get('friction_bps')} bps** one-way |
| Best overlay (risk) | **`{best}`** |

Sibling: [`../expanded_lab/`](../expanded_lab/) = event-study risk scoreboard + shared quote stubs.  
This lab = **tick/OB equity paths** over the PIN-usable long panel; reuses expanded panel events when present.

## Strategies

| Stub | Role |
|------|------|
| `baseline_maker` | Always-on small touch maker |
| `kill_ladder_maker` | Ladder size / halt pull |
| `nanex_temp_pull` | Nanex∩SSM temporary escalate/pull |
| `ladder_plus_v_restore` | Ladder × V-confirm restore (expanded_lab stub) |
| `confirm_before_restore` | Dual-horizon V confirm (expanded_lab stub) |
| `ladder_plus_confirm_before_restore` | Ladder × dual-horizon confirm (combined best) |

**Class:** risk-policy / MM playbook — **not** naked tradable alpha.

## Cadence honesty

{summary.get('cadence_honesty', '')}

Fills book at **trade print** + `fill_i` (never stale asof bid/ask as fill px).
"""
        )
    )
    cells.append(
        nbf.v4.new_code_cell(
            """
import json
from pathlib import Path
import pandas as pd
from IPython.display import Image, display, Markdown

OUT = Path('out')
s = json.loads((OUT / 'summary.json').read_text())
cov = pd.DataFrame(json.loads((OUT / 'coverage.json').read_text()))
if 'included' not in cov.columns and 'in' in cov.columns:
    cov = cov.rename(columns={'in': 'included'})
cov['included'] = cov['included'].astype(bool)

print('span', s['date_span'], 'n_days_in', s['n_days_in'], 'n_cells_ok', s['n_cells_ok'])
print('winner', s['winner'])
print('fire_scoreboard', s['fire_scoreboard'])
print()
for name, block in s['strategies'].items():
    d = block['delta_vs_baseline']
    print(f\"{name:36s} eq_mean={block['pool']['final_equity_bps']['mean']:+9.2f}  \"
          f\"dd_mean={block['pool']['max_dd_bps']['mean']:+9.2f}  \"
          f\"Δeq={d['delta_mean']:+8.2f} CI=[{d.get('lo', float('nan')):+.1f},{d.get('hi', float('nan')):+.1f}]\")
"""
        )
    )
    cells.append(nbf.v4.new_markdown_cell("## Date coverage (in / out)"))
    cells.append(
        nbf.v4.new_code_cell(
            """
eth = cov[cov.symbol == 'ETH'].sort_values('day')
display(eth[['day', 'included', 'reason', 'n_trades', 'coverage', 'pin_usable', 'panel_core', 'thin_public_md']])
print('IN days:', eth.loc[eth['included'], 'day'].tolist())
print('OUT days:', eth.loc[~eth['included'], 'day'].tolist())
if (OUT / 'figs' / 'coverage_days.png').exists():
    display(Image(filename=str(OUT / 'figs' / 'coverage_days.png')))
"""
        )
    )
    cells.append(
        nbf.v4.new_markdown_cell(
            "## Aggregate equity / inventory / drawdown\n\nPNGs under `out/figs/`."
        )
    )
    cells.append(
        nbf.v4.new_code_cell(
            """
from IPython.display import Image, display, Markdown
for name in [
    'equity_cumulative.png',
    'drawdown_scoreboard.png',
    'delta_vs_baseline.png',
    'example_day_inventory.png',
]:
    p = OUT / 'figs' / name
    if p.exists():
        display(Markdown(f'### `{name}`'))
        display(Image(filename=str(p)))
"""
        )
    )
    cells.append(
        nbf.v4.new_markdown_cell(
            "## Risk scoreboard\n\nAdverse |mo5| after fires · FP V-recovery rate · fire counts."
        )
    )
    cells.append(
        nbf.v4.new_code_cell(
            """
fs = s['fire_scoreboard']
display(Markdown(
    f\"\"\"- **n_fire**={fs['n_fire']} · **n_control**={fs['n_control']}
- **FP V-recovery rate**={fs['fp_v_recovery_rate']:.3f} (fires labeled `v_recovery`)
- **adverse |mo5| fire**={fs['adverse_mo5_fire_mean']:.2f} · control={fs['adverse_mo5_control_mean']:.2f}
- **Δ adverse**={fs['delta_adverse_mo5']:.2f} (fire − control; higher = fires are worse tails — ladder targets these)
\"\"\"
))
display(Image(filename=str(OUT / 'figs' / 'risk_scoreboard.png')))
"""
        )
    )
    cells.append(
        nbf.v4.new_markdown_cell("## Example day zoom — price + fills + ladder shades")
    )
    cells.append(
        nbf.v4.new_code_cell(
            """
display(Markdown(f\"Focus cell: `{s.get('focus_cell')}`\"))
for name in ['example_day_equity.png', 'example_day_price_fills.png']:
    p = OUT / 'figs' / name
    if p.exists():
        display(Markdown(f'### `{name}`'))
        display(Image(filename=str(p)))
"""
        )
    )
    cells.append(nbf.v4.new_markdown_cell("## Early vs late half stability"))
    cells.append(
        nbf.v4.new_code_cell(
            """
for name, block in s['strategies'].items():
    if name == 'baseline_maker':
        continue
    el = block['early_late']
    print(f\"{name:36s} early={el['early_mean_final_bps']:+.2f} (n={el['early_n_days']})  \"
          f\"late={el['late_mean_final_bps']:+.2f} (n={el['late_n_days']})  \"
          f\"sign_stable={el['sign_stable']}\")
display(Image(filename=str(OUT / 'figs' / 'early_late_split.png')))
display(Image(filename=str(OUT / 'figs' / 'book_source_counts.png')))
"""
        )
    )
    cells.append(
        nbf.v4.new_markdown_cell(
            f"""## Headline

**Best risk overlay on this long panel:** `{best}`

Ranked: `{(summary.get('winner') or {}).get('ranked')}`

Re-run: `python3 run_long_range.py --workers 8` · see [`README.md`](README.md).
Wire: `expanded_lab` panel + quote stubs · `paper_harness.detect_day` (off-panel days) · `strategy_lab.run_tick_sim` (fills at trade print).
"""
        )
    )
    nb.cells = cells
    path = LAB / "long_range_strategies.ipynb"
    nbf.write(nb, path)
    return path


def run(
    *,
    symbols: tuple[str, ...] = ("ETH",),
    venue: str = "hyperliquid",
    workers: int = 8,
    max_trades: int = 80_000,
    friction_bps: float = FRICTION_BPS,
    days: list[str] | None = None,
    smoke: int = 0,
) -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    DAYS_DIR.mkdir(parents=True, exist_ok=True)
    ensure_env()

    cand = days or candidate_days()
    if smoke > 0:
        # prefer panel core for smoke
        prefer = [d for d in PANEL_CORE if d in cand] + [d for d in cand if d not in PANEL_CORE]
        cand = prefer[:smoke]

    print(f"[long_range] probing {len(cand)} days × {symbols} on {venue}", flush=True)
    coverage: list[dict] = []
    for sym in symbols:
        for day in cand:
            row = probe_day(venue, sym, day)
            coverage.append(row)
            flag = "IN " if row["included"] else "OUT"
            print(
                f"  {flag} {day} {sym} n={row['n_trades']} cov={row.get('coverage', 0):.2f} ({row['reason']})",
                flush=True,
            )
    save_json(OUT / "coverage.json", coverage)

    in_days_eth = sorted({c["day"] for c in coverage if c["symbol"] == "ETH" and c["included"]})
    expanded = load_expanded_panel()
    panel_by = expanded.get("by_key") or {}
    n_panel_hit = 0
    jobs = []
    for c in coverage:
        if not c["included"]:
            continue
        key = (c["day"], c["symbol"], venue)
        prow = panel_by.get(key)
        pevents = prow.get("events") if prow else None
        if pevents:
            n_panel_hit += 1
        jobs.append(
            {
                "day": c["day"],
                "symbol": c["symbol"],
                "venue": venue,
                "panel_events": pevents,
                "panel_source": "expanded_lab" if pevents else None,
            }
        )
    print(
        f"[long_range] expanded_lab panel available={expanded.get('available')} "
        f"reuse_hits={n_panel_hit}/{len(jobs)} (days={expanded.get('meta', {}).get('days')})",
        flush=True,
    )

    # Prefer expanded panel events for pooled ladder breaks; else detect sample
    print(f"[long_range] building pooled ladder breaks…", flush=True)
    flat_events: list[dict] = []
    for j in jobs:
        pe = j.get("panel_events")
        if pe and pe.get("z_peak"):
            for i in range(len(pe["z_peak"])):
                flat_events.append(
                    {
                        "z_peak": float(pe["z_peak"][i]),
                        "intensity_60s": int(pe.get("intensity_60s", [1] * len(pe["z_peak"]))[i]),
                        "nanex_overlap": bool(pe.get("nanex_overlap", [False] * len(pe["z_peak"]))[i]),
                        "dp_pct": float(pe.get("dp_pct", [0.0] * len(pe["z_peak"]))[i]),
                    }
                )
    if len(flat_events) < 20:
        for j in jobs[:12]:
            if j.get("panel_events"):
                continue
            try:
                cell = detect_day(j["venue"], j["symbol"], j["day"], quiet=True)
                if cell.get("skip") or not cell.get("events"):
                    continue
                ev = cell["events"]
                n = len(ev.get("z_peak", []))
                for i in range(n):
                    flat_events.append(
                        {
                            "z_peak": float(np.asarray(ev["z_peak"])[i]),
                            "intensity_60s": int(np.asarray(ev["intensity_60s"])[i]),
                            "nanex_overlap": bool(np.asarray(ev["nanex_overlap"])[i]),
                            "dp_pct": float(np.asarray(ev["dp_pct"])[i]),
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                print(f"  break-sample FAIL {j['day']} {j['symbol']}: {exc}", flush=True)
    breaks = assign_ladder_tiers(flat_events) if flat_events else {
        "p25": 12.5, "p50": 15.9, "p75": 20.4, "dp_p90": 0.45
    }
    print(f"[long_range] ladder_breaks={breaks} n_sample_events={len(flat_events)}", flush=True)

    payloads = [
        {
            **j,
            "friction_bps": friction_bps,
            "max_trades": max_trades,
            "ladder_breaks": breaks,
            "keep_full": False,  # slim IPC; re-sim focus day later for plots
        }
        for j in jobs
    ]
    cells: list[dict] = []
    errors: list[dict] = []
    print(f"[long_range] simulating {len(payloads)} cells workers={workers}", flush=True)

    if workers <= 1:
        for p in payloads:
            out = _cell_worker(p)
            if out.get("error") and "results" not in out:
                errors.append(out)
                print(f"  ERR {out.get('day')} {out.get('symbol')}: {out['error']}", flush=True)
                continue
            if out.get("skip"):
                print(f"  SKIP {out.get('day')} {out.get('symbol')}: {out.get('skip')}", flush=True)
                continue
            cells.append(out)
            # per-day summary (metrics only)
            day_sum = {
                "day": out["day"],
                "symbol": out["symbol"],
                "n_trades": out["n_trades"],
                "n_events": out["n_events"],
                "book": out["book"],
                "fire_stats": out["fire_stats"],
                "results": {
                    k: {
                        "final_equity_bps": v["final_equity_bps"],
                        "max_dd_bps": v["max_dd_bps"],
                        "n_fills": v["n_fills"],
                    }
                    for k, v in out["results"].items()
                },
            }
            save_json(DAYS_DIR / f"{out['day']}_{out['symbol']}.json", day_sum)
            print(
                f"  OK {out['day']} {out['symbol']} trades={out['n_trades']} "
                f"events={out['n_events']} book={out['book'].get('source')}",
                flush=True,
            )
    else:
        with ProcessPoolExecutor(max_workers=max(1, workers)) as ex:
            futs = {ex.submit(_cell_worker, p): p for p in payloads}
            for fut in as_completed(futs):
                out = fut.result()
                if out.get("error") and "results" not in out:
                    errors.append(out)
                    print(f"  ERR {out.get('day')} {out.get('symbol')}: {out['error']}", flush=True)
                    continue
                if out.get("skip"):
                    print(f"  SKIP {out.get('day')} {out.get('symbol')}: {out.get('skip')}", flush=True)
                    continue
                cells.append(out)
                day_sum = {
                    "day": out["day"],
                    "symbol": out["symbol"],
                    "n_trades": out["n_trades"],
                    "n_events": out["n_events"],
                    "book": out["book"],
                    "fire_stats": out["fire_stats"],
                    "results": {
                        k: {
                            "final_equity_bps": v["final_equity_bps"],
                            "max_dd_bps": v["max_dd_bps"],
                            "n_fills": v["n_fills"],
                        }
                        for k, v in out["results"].items()
                    },
                }
                save_json(DAYS_DIR / f"{out['day']}_{out['symbol']}.json", day_sum)
                print(
                    f"  OK {out['day']} {out['symbol']} trades={out['n_trades']} "
                    f"events={out['n_events']} book={out['book'].get('source')}",
                    flush=True,
                )

    ok_days = sorted({c["day"] for c in cells})
    early, late = early_late_by_day(ok_days)
    strat_summary: dict[str, Any] = {}
    for name in STRAT_NAMES:
        pool = _pool_equity(cells, name)
        delta = (
            _delta_vs_baseline(cells, name)
            if name != "baseline_maker"
            else {"n": pool["n_cells"], "delta_mean": 0.0, "lo": 0.0, "hi": 0.0, "frac_positive": float("nan")}
        )
        strat_summary[name] = {
            "pool": pool,
            "delta_vs_baseline": delta,
            "dd_vs_baseline": _dd_delta_vs_baseline(cells, name),
            "early_late": early_late_metrics(pool["by_day_mean_final"], early, late),
        }

    fire_sb = aggregate_fire_scoreboard(cells)
    winner = pick_winner(strat_summary)

    src_counts: dict[str, int] = {}
    med_dts = []
    for c in cells:
        b = c.get("book") or {}
        src = str(b.get("source") or "none")
        src_counts[src] = src_counts.get(src, 0) + 1
        if b.get("median_dt_s") is not None and np.isfinite(b.get("median_dt_s", np.nan)):
            med_dts.append(float(b["median_dt_s"]))
    cadence = (
        f"Trade tape is ms-level. Book sources this run: { {k.split(':iid=')[0]: v for k, v in src_counts.items()} }. "
        f"Median book Δt ≈ {float(np.median(med_dts)) if med_dts else float('nan'):.2f}s. "
        "Collector TOB preferred when present; else HL `l2_snapshot_level` / warehouse BBO "
        "(~seconds–minutes median) or Deribit TOB — **not** sub-second L2. "
        "Equity = synthetic touch-maker marks with friction; fills at trade print + fill_i."
    )

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "date_span": {
            "first": ok_days[0] if ok_days else None,
            "last": ok_days[-1] if ok_days else None,
        },
        "days_in": ok_days,
        "n_days_in": len(ok_days),
        "n_days_probed": len({c["day"] for c in coverage if c["symbol"] == "ETH"}),
        "symbols": list(symbols),
        "venue": venue,
        "friction_bps": friction_bps,
        "ladder_breaks": breaks,
        "n_cells_ok": len(cells),
        "n_errors": len(errors),
        "errors": errors[:20],
        "book_source_counts": src_counts,
        "cadence_honesty": cadence,
        "fire_scoreboard": fire_sb,
        "strategies": strat_summary,
        "winner": winner,
        "sibling_expanded_lab": {
            "path": str(APP / "expanded_lab"),
            "panel_available": bool(expanded.get("available")),
            "panel_reuse_hits": n_panel_hit,
            "panel_days": (expanded.get("meta") or {}).get("days"),
            "note": (
                "Reused expanded_lab panel events/tiers when (day,symbol,venue) matches; "
                "quote stubs from expanded_lab.strategies; event-study scoreboard stays in expanded_lab/out"
            ),
        },
        "n_days_eth_in": len(in_days_eth),
        "paths": {
            "summary": str(OUT / "summary.json"),
            "coverage": str(OUT / "coverage.json"),
            "figs": str(FIG),
            "days": str(DAYS_DIR),
            "notebook": str(LAB / "long_range_strategies.ipynb"),
        },
    }

    # Re-sim richest ETH day with keep_full for zoom plots (equity paths on tape)
    eth_cells = [c for c in cells if c.get("symbol") == "ETH" and c.get("results")]
    if eth_cells:
        focus_meta = max(eth_cells, key=lambda c: int(c.get("n_events") or 0))
        print(
            f"[long_range] re-sim focus {focus_meta['day']} ETH keep_full "
            f"(events={focus_meta['n_events']})…",
            flush=True,
        )
        focus_job = next(
            (j for j in jobs if j["day"] == focus_meta["day"] and j["symbol"] == "ETH"),
            {"day": focus_meta["day"], "symbol": "ETH", "venue": venue},
        )
        focus_full = _cell_worker(
            {
                **focus_job,
                "friction_bps": friction_bps,
                "max_trades": max_trades,
                "ladder_breaks": breaks,
                "keep_full": True,
            }
        )
        if focus_full.get("results") and focus_full.get("keep_full"):
            # replace matching slim cell
            cells = [
                focus_full if (c["day"] == focus_full["day"] and c["symbol"] == focus_full["symbol"]) else c
                for c in cells
            ]
            print(f"  focus OK book={focus_full.get('book', {}).get('source')}", flush=True)
        else:
            print(f"  focus FAIL {focus_full.get('error') or focus_full.get('skip')}", flush=True)

    fig_paths = plot_all(cells, summary, coverage)
    summary["fig_paths"] = fig_paths
    # light rollup
    rollup = [
        {
            "day": c["day"],
            "symbol": c["symbol"],
            "n_trades": c["n_trades"],
            "n_events": c["n_events"],
            "book": c["book"],
            "fire_stats": c["fire_stats"],
            "results": {
                k: {
                    "final_equity_bps": v["final_equity_bps"],
                    "max_dd_bps": v["max_dd_bps"],
                    "n_fills": v["n_fills"],
                }
                for k, v in c["results"].items()
            },
        }
        for c in cells
    ]
    save_json(OUT / "cells_rollup.json", rollup)
    save_json(OUT / "summary.json", summary)
    # equity curves CSV-ish json
    save_json(
        OUT / "equity_curves.json",
        {
            name: strat_summary[name]["pool"]["cumulative_by_day"]
            for name in STRAT_NAMES
        },
    )
    nb_path = build_notebook(summary)
    print(
        f"[long_range] DONE days_in={len(ok_days)} span={summary['date_span']} "
        f"winner={winner['best']} figs={len(fig_paths)} nb={nb_path}",
        flush=True,
    )
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Long-range tick/OB crash-risk strategy lab")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--max-trades", type=int, default=80_000)
    ap.add_argument("--friction-bps", type=float, default=FRICTION_BPS)
    ap.add_argument("--symbols", default="ETH", help="Comma list, e.g. ETH or ETH,BTC")
    ap.add_argument("--days", default="", help="Comma YYYY-MM-DD override")
    ap.add_argument("--smoke", type=int, default=0, help="Only first N candidate days (panel-preferring)")
    ap.add_argument("--venue", default="hyperliquid")
    args = ap.parse_args()
    symbols = tuple(s.strip().upper() for s in args.symbols.split(",") if s.strip())
    days = [d.strip() for d in args.days.split(",") if d.strip()] or None
    run(
        symbols=symbols,
        venue=args.venue.lower(),
        workers=args.workers,
        max_trades=args.max_trades,
        friction_bps=args.friction_bps,
        days=days,
        smoke=args.smoke,
    )


if __name__ == "__main__":
    main()
