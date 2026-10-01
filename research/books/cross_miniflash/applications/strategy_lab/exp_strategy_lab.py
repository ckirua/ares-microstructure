from __future__ import annotations
#!/usr/bin/env python3
"""Strategy lab runner — tick/OB sims, equity curves, regime plots.

Builds marked PnL backtests for:
  - baseline always-on maker
  - kill-ladder gated maker
  - Nanex∩SSM temporary pull
  - V-restore confirm vs stay-wide
  - optional HL thin size-cap overlay

Uses trade tape + best available book (collector TOB or warehouse l2_rebuild).
Documents cadence limits. ClickHouse MCP banned. No fantasy fills.
"""

import os

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
STARTARB = Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb'))
WAREHOUSE_SRC = Path(os.environ.get('WAREHOUSE_SRC') or ((Path(os.environ.get('WAREHOUSE_ROOT') or (Path.home() / 'lab' / 'lab-n2070' / 'warehouse')) / 'src')))
OUT = LAB / "out"
FIG = OUT / "figs"
SCRIPTS_APP = APP / "scripts"

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
    DEFAULT_DAYS,
    DEFAULT_SYMBOLS,
    FRICTION_BPS,
    assign_ladder_tiers,
    build_event_panel,
    early_late_by_day,
    flatten_events,
    save_fig,
    save_json,
)
from _data import ensure_env, load_day_trades, normalize_side  # noqa: E402
from research.lib.crash import recovery_fraction  # noqa: E402
from sim.book import book_meta, load_best_book  # noqa: E402
from sim.engine import SimConfig, run_tick_sim  # noqa: E402
from sim.metrics import early_late_metrics, equity_stats, max_drawdown  # noqa: E402
from strategies import (  # noqa: E402
    AlwaysStayWidePostCrash,
    BaselineMaker,
    KillLadderOverlay,
    NanexTemporaryPull,
    ThinVenueSizeCap,
    VRestoreVsStayWide,
    build_event_clock,
)

NS = 1_000_000_000
STRAT_NAMES = [
    "baseline_maker",
    "kill_ladder_maker",
    "nanex_temp_pull",
    "v_restore_confirm",
    "always_stay_wide",
    "hl_thin_size_cap",
]


def _assert_fills_on_tape(r: dict[str, Any]) -> None:
    """Every fill must be the tape print at fill_i (or matching ts+px)."""
    fpx = np.asarray(r.get("fill_px", []), dtype=np.float64)
    if fpx.size == 0:
        return
    ts_arr = np.asarray(r["ts"], dtype=np.int64)
    px_arr = np.asarray(r["px"], dtype=np.float64)
    fi = np.asarray(r.get("fill_i", []), dtype=np.int64)
    fts = np.asarray(r["fill_ts"], dtype=np.int64)
    if fi.size == fpx.size:
        for j in range(fpx.size):
            i = int(fi[j])
            if i < 0 or i >= px_arr.size:
                raise AssertionError(f"fill[{j}] fill_i={i} out of range n={px_arr.size}")
            if int(ts_arr[i]) != int(fts[j]) or not np.isclose(px_arr[i], fpx[j], rtol=0.0, atol=1e-6):
                raise AssertionError(
                    f"fill[{j}] px={fpx[j]} ts={fts[j]} != tape[{i}] px={px_arr[i]} ts={ts_arr[i]}"
                )
        return
    for j in range(fpx.size):
        same_t = np.flatnonzero(ts_arr == fts[j])
        if same_t.size == 0 or not np.any(np.isclose(px_arr[same_t], fpx[j], rtol=0.0, atol=1e-6)):
            raise AssertionError(
                f"fill[{j}] px={fpx[j]} ts={fts[j]} not on trade tape — check sim bookkeeping"
            )


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
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if obj is None:
        return None
    return str(obj)


def _attach_recovery_horizons(events: dict, ts: np.ndarray, px: np.ndarray) -> dict:
    """Add recovery_1s / recovery_2s using event end indices on this tape."""
    ts_end = np.asarray(events.get("ts_end", []), dtype=np.int64)
    direction = np.asarray(events.get("direction", []), dtype=np.float64)
    ts_start = np.asarray(events.get("ts_start", []), dtype=np.int64)
    n = ts_end.size
    if n == 0:
        events["recovery_1s"] = []
        events["recovery_2s"] = []
        return events
    end_i = np.searchsorted(ts, ts_end, side="left")
    end_i = np.clip(end_i, 0, max(ts.size - 1, 0))
    start_i = np.searchsorted(ts, ts_start, side="left")
    start_i = np.clip(start_i, 0, max(ts.size - 1, 0))
    # direction may be missing on older panel — infer from dp
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


def _downsample_tape(
    tape: dict[str, np.ndarray],
    *,
    max_trades: int = 120_000,
) -> dict[str, np.ndarray]:
    n = int(tape["ts"].size)
    if n <= max_trades:
        return tape
    step = int(np.ceil(n / max_trades))
    idx = np.arange(0, n, step)
    return {k: (v[idx] if isinstance(v, np.ndarray) and v.shape == (n,) else v) for k, v in tape.items()}


def _prepare_cell(row: dict[str, Any], *, friction_bps: float, max_trades: int) -> dict[str, Any] | None:
    day, sym, venue = row["day"], row["symbol"], row["venue"]
    if row.get("skip") or not row.get("events"):
        return None
    ensure_env()
    try:
        rec = load_day_trades(venue, sym, day, quiet=True)
    except Exception as exc:  # noqa: BLE001
        return {"day": day, "symbol": sym, "venue": venue, "error": f"tape:{exc}"}
    tape = rec["tape"]
    ts = np.asarray(tape["ts"], dtype=np.int64)
    px = np.asarray(tape["px"], dtype=np.float64)
    qty = np.asarray(tape["qty"], dtype=np.float64)
    side = normalize_side(tape["side"])
    if ts.size < 500:
        return {"day": day, "symbol": sym, "venue": venue, "error": "thin_tape"}

    # L2 multilevel attach is expensive; TOB touch size is enough for event plots.
    book = load_best_book(venue, sym, day, prefer_collector=True, attach_l2_depth=False)
    if book is not None and book.n >= 10:
        asof = book.asof(ts)
        mid, bid, ask = asof["mid"], asof["bid"], asof["ask"]
        # fill gaps with trade px
        miss = ~np.isfinite(mid) | (mid <= 0)
        mid = mid.copy()
        mid[miss] = px[miss]
        bid = np.where(np.isfinite(bid) & (bid > 0), bid, mid * (1 - 0.5e-4))
        ask = np.where(np.isfinite(ask) & (ask > 0), ask, mid * (1 + 0.5e-4))
        bmeta = book_meta(book)
        depth_bid = asof.get("depth_bid")
        depth_ask = asof.get("depth_ask")
    else:
        mid = px.copy()
        bid = px * (1 - 0.5e-4)
        ask = px * (1 + 0.5e-4)
        bmeta = {"available": False, "source": "tape_proxy", "n": 0, "median_dt_s": None}
        depth_bid = depth_ask = None

    events = _attach_recovery_horizons(dict(row["events"]), ts, px)
    # re-tier with pooled breaks from panel flatten later — keep row tiers
    thin_cap = bool(
        venue == "hyperliquid"
        and np.isfinite(row.get("excess", np.nan))
        and float(row.get("excess") or 0) > 0.3
    )
    packed = {
        "ts": ts,
        "px": px,
        "qty": qty,
        "side": side,
        "mid": mid,
        "bid": bid,
        "ask": ask,
    }
    packed = _downsample_tape(packed, max_trades=max_trades)
    # rebuild clock on (possibly downsampled) tape
    clock = build_event_clock(packed["ts"], events, thin_cap=thin_cap)
    cfg = SimConfig(base_size=0.25, friction_bps=friction_bps, max_inventory=2.0)

    strategies = [
        BaselineMaker(base_size=cfg.base_size),
        KillLadderOverlay(clock=clock, base_size=cfg.base_size),
        NanexTemporaryPull(clock=clock, base_size=cfg.base_size),
        VRestoreVsStayWide(clock=clock, base_size=cfg.base_size),
        AlwaysStayWidePostCrash(clock=clock, base_size=cfg.base_size),
        ThinVenueSizeCap(clock=clock, base_size=cfg.base_size),
    ]
    results = {}
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
        results[strat.name] = {
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
        # Spot-check before any IPC downsample: fill px must equal tape print
        _assert_fills_on_tape(results[strat.name])

    # event windows for depth plots (first up to 8 events)
    ev_windows = []
    ts_e = np.asarray(events.get("ts_end", []), dtype=np.int64)[:8]
    for t_end in ts_e:
        lo = t_end - 5 * NS
        hi = t_end + 15 * NS
        m = (packed["ts"] >= lo) & (packed["ts"] <= hi)
        w: dict[str, Any] = {
            "t_end": int(t_end),
            "ts": packed["ts"][m],
            "px": packed["px"][m],
            "mid": packed["mid"][m],
            "bid_sz": None,
            "ask_sz": None,
        }
        if book is not None:
            a = book.asof(packed["ts"][m])
            w["bid_sz"] = a["bid_sz"]
            w["ask_sz"] = a["ask_sz"]
            if depth_bid is not None:
                # depth arrays are on full tape before downsample — re-asof
                w["depth_bid"] = a.get("depth_bid")
                w["depth_ask"] = a.get("depth_ask")
        ev_windows.append(w)

    return {
        "day": day,
        "symbol": sym,
        "venue": venue,
        "n_trades": int(packed["ts"].size),
        "n_events": int(len(events.get("ts_end", []))),
        "book": bmeta,
        "thin_cap": thin_cap,
        "excess": row.get("excess"),
        "results": results,
        "event_windows": ev_windows,
        "error": None,
    }


def _cell_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Process-pool entry: strip heavy arrays from return for aggregation."""
    try:
        out = _prepare_cell(
            payload["row"],
            friction_bps=payload["friction_bps"],
            max_trades=payload["max_trades"],
        )
        if out is None:
            return {"skip": True, **{k: payload["row"].get(k) for k in ("day", "symbol", "venue")}}
        if out.get("error") and "results" not in out:
            return out
        # keep full arrays only for HL cells (plot focus); others summarize
        keep_full = out["venue"] == "hyperliquid" and out["symbol"] in ("ETH", "BTC")
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
                # Keep full-resolution tape for focus plots so fill markers sit on the
                # same (ts, px) series as the trade line (downsampling would drop the
                # prints fills executed against and float markers).
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
                        "fill_i": r.get("fill_i", np.asarray([], dtype=np.int64)),
                    }
                )
            slim_results[name] = slim
        return {
            "day": out["day"],
            "symbol": out["symbol"],
            "venue": out["venue"],
            "n_trades": out["n_trades"],
            "n_events": out["n_events"],
            "book": out["book"],
            "thin_cap": out["thin_cap"],
            "excess": out["excess"],
            "results": slim_results,
            "event_windows": out["event_windows"] if keep_full else [],
            "keep_full": keep_full,
            "error": out.get("error"),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "day": payload["row"].get("day"),
            "symbol": payload["row"].get("symbol"),
            "venue": payload["row"].get("venue"),
            "error": f"{type(exc).__name__}: {exc}",
            "trace": traceback.format_exc()[-2000:],
        }


def _pool_equity(cells: list[dict], strat: str) -> dict[str, Any]:
    finals = []
    dds = []
    fills = []
    by_day: dict[str, list[float]] = {}
    for c in cells:
        r = (c.get("results") or {}).get(strat)
        if not r:
            continue
        fe = r["final_equity_bps"]
        if fe is None or not np.isfinite(fe):
            continue
        finals.append(float(fe))
        dds.append(float(r["max_dd_bps"]) if np.isfinite(r["max_dd_bps"]) else float("nan"))
        fills.append(int(r["n_fills"]))
        by_day.setdefault(c["day"], []).append(float(fe))
    day_eq = {d: float(np.mean(v)) for d, v in by_day.items()}
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
        "n_fills_total": int(np.sum(fills)) if fills else 0,
        "by_day_mean_final": day_eq,
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
        return {"n": 0, "delta_mean": float("nan"), "lo": float("nan"), "hi": float("nan")}
    from research.lib.stats import bootstrap_ci

    boot = bootstrap_ci(a, n_boot=800, seed=42)
    return {
        "n": int(a.size),
        "delta_mean": float(a.mean()),
        "lo": boot["lo"],
        "hi": boot["hi"],
        "frac_positive": float(np.mean(a > 0)),
    }


def plot_all(cells: list[dict], summary: dict) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    # 1) Equity curves — pick richest HL ETH day
    hl = [c for c in cells if c.get("keep_full") and c.get("results")]
    hl_eth = [c for c in hl if c.get("symbol") == "ETH"] or hl
    if not hl_eth:
        return paths
    # choose day with most events
    focus = max(hl_eth, key=lambda c: int(c.get("n_events") or 0))
    fig, ax = plt.subplots(figsize=(11, 4.5))
    for name in STRAT_NAMES:
        r = focus["results"].get(name)
        if not r or "equity_bps" not in r:
            continue
        t = (np.asarray(r["ts"], dtype=np.float64) - float(r["ts"][0])) / NS / 3600.0
        ax.plot(t, r["equity_bps"], label=name, lw=1.2)
    ax.set_xlabel("hours from day start")
    ax.set_ylabel("equity (bps of ref)")
    ax.set_title(
        f"Equity curves — {focus['venue']} {focus['symbol']} {focus['day']} "
        f"(book={focus['book'].get('source')})"
    )
    ax.legend(fontsize=7, ncol=2)
    ax.axhline(0, color="k", lw=0.5, alpha=0.4)
    p = FIG / "equity_curves_focus.png"
    save_fig(p)
    paths.append(str(p))

    # 2) Drawdowns for baseline vs ladder
    fig, ax = plt.subplots(figsize=(11, 3.8))
    for name, color in (("baseline_maker", "#444"), ("kill_ladder_maker", "#c0392b")):
        r = focus["results"].get(name)
        if not r or "equity_bps" not in r:
            continue
        dd = max_drawdown(np.asarray(r["equity_bps"], dtype=np.float64))
        t = (np.asarray(r["ts"], dtype=np.float64) - float(r["ts"][0])) / NS / 3600.0
        ax.plot(t, dd, label=name, color=color, lw=1.2)
    ax.set_title("Drawdown — baseline vs kill-ladder")
    ax.set_ylabel("dd (bps)")
    ax.legend(fontsize=8)
    p = FIG / "drawdown_baseline_vs_ladder.png"
    save_fig(p)
    paths.append(str(p))

    # 3) Trade marks on price + regime shades
    r = focus["results"].get("kill_ladder_maker")
    if r and "px" in r:
        fig, ax = plt.subplots(figsize=(11, 4.2))
        t = (np.asarray(r["ts"], dtype=np.float64) - float(r["ts"][0])) / NS / 3600.0
        ax.plot(t, r["px"], color="#2c3e50", lw=0.7, label="trade px")
        # shade halt/size_cap regimes
        reg = np.asarray(r["regime"], dtype=object)
        for label, color, alpha in (
            ("halt", "#e74c3c", 0.25),
            ("size_cap", "#e67e22", 0.18),
            ("widen", "#f1c40f", 0.12),
        ):
            m = reg == label
            if not m.any():
                continue
            # paint contiguous spans
            idx = np.where(m)[0]
            if idx.size == 0:
                continue
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
            t0 = float(ts_arr[0])
            # Prefer fill_i → tape px so markers sit exactly on the plotted line
            fi = np.asarray(r.get("fill_i", []), dtype=np.int64)
            if fi.size == fpx.size and fi.size and int(fi.max()) < px_arr.size:
                ft = (ts_arr[fi].astype(np.float64) - t0) / NS / 3600.0
                fy = px_arr[fi]
            else:
                ft = (fts.astype(np.float64) - t0) / NS / 3600.0
                fy = fpx
            _assert_fills_on_tape(
                {
                    "ts": ts_arr,
                    "px": px_arr,
                    "fill_ts": fts,
                    "fill_px": fpx,
                    "fill_i": fi if fi.size == fpx.size else np.asarray([], dtype=np.int64),
                }
            )
            ax.scatter(ft[fside > 0], fy[fside > 0], s=8, c="#27ae60", label="buy fill", zorder=5)
            ax.scatter(ft[fside < 0], fy[fside < 0], s=8, c="#c0392b", label="sell fill", zorder=5)
        ax.set_title("Price path + ladder regime shades + fills")
        ax.legend(fontsize=7, loc="best")
        p = FIG / "price_regimes_fills.png"
        save_fig(p)
        paths.append(str(p))

    # 4) Inventory path
    fig, ax = plt.subplots(figsize=(11, 3.5))
    for name in ("baseline_maker", "kill_ladder_maker", "nanex_temp_pull"):
        r = focus["results"].get(name)
        if not r or "inventory" not in r:
            continue
        t = (np.asarray(r["ts"], dtype=np.float64) - float(r["ts"][0])) / NS / 3600.0
        ax.plot(t, r["inventory"], label=name, lw=1.0)
    ax.set_title("Inventory path")
    ax.set_ylabel("coins")
    ax.legend(fontsize=8)
    p = FIG / "inventory_path.png"
    save_fig(p)
    paths.append(str(p))

    # 5) Book depth around events
    wins = focus.get("event_windows") or []
    if wins:
        fig, axes = plt.subplots(min(4, len(wins)), 1, figsize=(11, 2.4 * min(4, len(wins))), sharex=False)
        if min(4, len(wins)) == 1:
            axes = [axes]
        for ax, w in zip(axes, wins[:4]):
            if len(w["ts"]) < 2:
                continue
            tw = (np.asarray(w["ts"], dtype=np.float64) - float(w["t_end"])) / NS
            ax.plot(tw, w["px"], color="#2c3e50", lw=0.9, label="px")
            if w.get("bid_sz") is not None:
                ax2 = ax.twinx()
                ax2.fill_between(tw, 0, np.asarray(w["bid_sz"], dtype=np.float64), alpha=0.25, color="#27ae60", label="bid_sz")
                ax2.fill_between(tw, 0, -np.asarray(w["ask_sz"], dtype=np.float64), alpha=0.25, color="#c0392b", label="ask_sz")
                ax2.set_ylabel("touch size")
            ax.axvline(0, color="k", ls="--", lw=0.7)
            ax.set_ylabel("px")
            ax.set_title(f"event @ {w['t_end']} (±s from end)")
        fig.suptitle(f"Book touch size around events — {focus['day']} {focus['symbol']}", y=1.01)
        p = FIG / "book_depth_events.png"
        save_fig(p)
        paths.append(str(p))

    # 6) Strategy comparison bar — delta vs baseline
    fig, ax = plt.subplots(figsize=(9, 4))
    names = [s for s in STRAT_NAMES if s != "baseline_maker"]
    deltas = [summary["strategies"][s]["delta_vs_baseline"]["delta_mean"] for s in names]
    los = [summary["strategies"][s]["delta_vs_baseline"]["lo"] for s in names]
    his = [summary["strategies"][s]["delta_vs_baseline"]["hi"] for s in names]
    yerr = np.vstack(
        [
            np.asarray(deltas) - np.asarray(los),
            np.asarray(his) - np.asarray(deltas),
        ]
    )
    ax.bar(names, deltas, yerr=yerr, color="#3498db", alpha=0.85, capsize=4)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_ylabel("Δ final equity vs baseline (bps)")
    ax.set_title("Overlay value vs always-on maker (cell-pooled)")
    plt.xticks(rotation=25, ha="right")
    p = FIG / "delta_vs_baseline.png"
    save_fig(p)
    paths.append(str(p))

    # 7) Early / late split for kill ladder
    fig, ax = plt.subplots(figsize=(7, 4))
    for strat, color in (("kill_ladder_maker", "#c0392b"), ("nanex_temp_pull", "#8e44ad"), ("v_restore_confirm", "#16a085")):
        el = summary["strategies"][strat]["early_late"]
        ax.bar(
            [f"{strat}\nearly", f"{strat}\nlate"],
            [el["early_mean_final_bps"], el["late_mean_final_bps"]],
            color=color,
            alpha=0.75,
        )
    ax.axhline(0, color="k", lw=0.5)
    ax.set_ylabel("mean cell final equity (bps)")
    ax.set_title("Early / late day split")
    p = FIG / "early_late_split.png"
    save_fig(p)
    paths.append(str(p))

    # 8) Cadence honesty panel
    fig, ax = plt.subplots(figsize=(8, 3.5))
    sources = {}
    for c in cells:
        b = c.get("book") or {}
        src = b.get("source") or "none"
        sources[src] = sources.get(src, 0) + 1
        if b.get("median_dt_s") is not None and np.isfinite(b["median_dt_s"]):
            pass
    ax.bar(list(sources.keys()), list(sources.values()), color="#7f8c8d")
    ax.set_title("Book source counts across cells (cadence honesty)")
    ax.set_ylabel("# cells")
    plt.xticks(rotation=20, ha="right")
    p = FIG / "book_source_counts.png"
    save_fig(p)
    paths.append(str(p))

    return paths


def build_notebook(summary: dict, fig_paths: list[str]) -> Path:
    import nbformat as nbf

    nb = nbf.v4.new_notebook()
    cells = []
    cells.append(
        nbf.v4.new_markdown_cell(
            f"""# Strategy lab — tick / order-book sims

**Open this first** for equity curves, drawdowns, regime shades, and book-around-event plots.

Slice: `{summary.get('days')}` · symbols `{summary.get('symbols')}` · friction **{summary.get('friction_bps')} bps**.

## Cadence limits (read before trusting curves)

{summary.get('cadence_honesty', '')}

## Strategies

| Name | Role |
|------|------|
| `baseline_maker` | Always-on small touch maker |
| `kill_ladder_maker` | Ladder size schedule / pull on halt |
| `nanex_temp_pull` | Temporary pull on Nanex∩SSM |
| `v_restore_confirm` | Stay wide until causal V confirm |
| `always_stay_wide` | Stay wide through crash window |
| `hl_thin_size_cap` | HL thin-excess size cap |

Class: **risk-policy / MM playbook sims** — not naked tradable alpha.
See [`STRATEGY_LAB.md`](STRATEGY_LAB.md) · desk [`../../DESK_MEMO.md`](../../DESK_MEMO.md) §7.
"""
        )
    )
    cells.append(
        nbf.v4.new_code_cell(
            """
import json
from pathlib import Path
from IPython.display import Image, display, Markdown

OUT = Path('out')
s = json.loads((OUT/'summary.json').read_text())
print('n_cells_ok', s['n_cells_ok'], 'friction_bps', s['friction_bps'])
print('cadence:', s['cadence_honesty'][:400], '...')
for name, block in s['strategies'].items():
    d = block['delta_vs_baseline']
    print(f\"{name:22s} final_mean={block['pool']['final_equity_bps']['mean']:+.3f}  \"
          f\"Δvs_base={d['delta_mean']:+.3f} CI=[{d['lo']:+.3f},{d['hi']:+.3f}] fills={block['pool']['n_fills_total']}\")
"""
        )
    )
    cells.append(
        nbf.v4.new_markdown_cell(
            "## Equity / drawdown / marks / book depth\n\nPNG artifacts under `out/figs/`."
        )
    )
    cells.append(
        nbf.v4.new_code_cell(
            """
from IPython.display import Image, display
from pathlib import Path
for fig in sorted(Path('out/figs').glob('*.png')):
    display(Markdown(f'### `{fig.name}`'))
    display(Image(filename=str(fig)))
"""
        )
    )
    cells.append(
        nbf.v4.new_markdown_cell(
            f"""## Focus cell

`{summary.get('focus_cell')}`

## How to interpret

1. **Equity (bps of ref)** — cumulative marked PnL after friction; compare overlays to `baseline_maker`.
2. **Δ vs baseline CI** — if CI includes 0, overlay does not clear noise on this slice.
3. **Regime shades** — ladder fire windows on the price path; fills mark synthetic maker hits.
4. **Book depth** — touch size around gated events; warehouse BBO may be ~seconds stale.
5. **Early/late** — sign-stable overlays are stronger desk candidates; unstable → Hold.
"""
        )
    )
    nb.cells = cells
    path = LAB / "strategy_lab.ipynb"
    nbf.write(nb, path)
    return path


def run(
    *,
    force_panel: bool = False,
    workers: int = 12,
    max_trades: int = 100_000,
    friction_bps: float = FRICTION_BPS,
    venues: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    panel = build_event_panel(force=force_panel)
    rows = [r for r in panel["rows"] if r.get("events") and int(r.get("ssm_10_n") or 0) > 0]
    # re-assign ladder tiers with pooled breaks
    flat = flatten_events(rows)
    breaks = assign_ladder_tiers(flat)
    # write tiers back to rows by matching (day,symbol,venue,ts_end)
    key_tier = {(e["day"], e["symbol"], e["venue"], int(e["ts_end"])): e["tier"] for e in flat}
    for r in rows:
        ev = r["events"]
        tiers = []
        for t_end in ev["ts_end"]:
            tiers.append(key_tier.get((r["day"], r["symbol"], r["venue"], int(t_end)), "observe"))
        ev["tier"] = tiers

    if venues:
        rows = [r for r in rows if r["venue"] in venues]

    payloads = [
        {"row": r, "friction_bps": friction_bps, "max_trades": max_trades} for r in rows
    ]
    cells: list[dict] = []
    errors: list[dict] = []
    print(f"[strategy_lab] cells={len(payloads)} workers={workers} max_trades={max_trades}", flush=True)

    with ProcessPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = {ex.submit(_cell_worker, p): i for i, p in enumerate(payloads)}
        for fut in as_completed(futs):
            out = fut.result()
            if out.get("skip"):
                continue
            if out.get("error") and "results" not in out:
                errors.append(out)
                print(f"  ERR {out.get('day')} {out.get('symbol')} {out.get('venue')}: {out['error']}", flush=True)
                continue
            cells.append(out)
            print(
                f"  OK {out['day']} {out['symbol']} {out['venue']} "
                f"trades={out['n_trades']} events={out['n_events']} book={out['book'].get('source')}",
                flush=True,
            )

    early, late = early_late_by_day(panel["meta"]["days"])
    strat_summary = {}
    for name in STRAT_NAMES:
        pool = _pool_equity(cells, name)
        delta = _delta_vs_baseline(cells, name) if name != "baseline_maker" else {
            "n": pool["n_cells"],
            "delta_mean": 0.0,
            "lo": 0.0,
            "hi": 0.0,
            "frac_positive": float("nan"),
        }
        el = early_late_metrics(pool["by_day_mean_final"], early, late)
        strat_summary[name] = {
            "pool": pool,
            "delta_vs_baseline": delta,
            "early_late": el,
        }

    # cadence honesty blurb
    src_counts: dict[str, int] = {}
    med_dts = []
    for c in cells:
        b = c.get("book") or {}
        src = str(b.get("source") or "none")
        src_counts[src] = src_counts.get(src, 0) + 1
        if b.get("median_dt_s") is not None and np.isfinite(b.get("median_dt_s", np.nan)):
            med_dts.append(float(b["median_dt_s"]))
    cadence = (
        f"Trade tape is ms-level. Book sources this run: {src_counts}. "
        f"Median book Δt ≈ {float(np.median(med_dts)) if med_dts else float('nan'):.2f}s. "
        "Collector TOB (ms-ish) is preferred when present; Phase-4 days typically fall back to "
        "warehouse HL `l2_rebuild` (~5s) or venue BBO — **not** sub-second L2. "
        "Equity curves are synthetic touch-maker marks with friction haircut, not live quote logs."
    )

    focus = None
    hl = [c for c in cells if c.get("keep_full")]
    if hl:
        focus_cell = max(hl, key=lambda c: int(c.get("n_events") or 0))
        focus = {
            "day": focus_cell["day"],
            "symbol": focus_cell["symbol"],
            "venue": focus_cell["venue"],
            "n_events": focus_cell["n_events"],
            "book": focus_cell["book"],
        }

    # verdict sketch
    kl = strat_summary["kill_ladder_maker"]["delta_vs_baseline"]
    nx = strat_summary["nanex_temp_pull"]["delta_vs_baseline"]
    vr = strat_summary["v_restore_confirm"]["delta_vs_baseline"]
    verdict = {
        "kill_ladder": (
            "Promote-as-risk-policy (sim)"
            if np.isfinite(kl["delta_mean"]) and kl["lo"] > 0
            else "Hold / inspect (Δ vs baseline CI not cleanly >0 on marked maker PnL)"
        ),
        "nanex_pull": (
            "Promote-as-risk-policy (sim)"
            if np.isfinite(nx["delta_mean"]) and nx["lo"] > 0
            else "Hold / nested tag still Promote — sim Δ soft"
        ),
        "v_restore": (
            "Promote (med) MM playbook"
            if np.isfinite(vr["delta_mean"]) and vr["frac_positive"] and vr["frac_positive"] >= 0.5
            else "Hold / compare stay-wide"
        ),
        "note": "Sims validate overlay vs baseline maker; desk still treats Promotes as policy not alpha.",
    }

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days": panel["meta"]["days"],
        "symbols": panel["meta"]["symbols"],
        "friction_bps": friction_bps,
        "ladder_breaks": breaks,
        "n_rows_panel": len(panel["rows"]),
        "n_cells_ok": len(cells),
        "n_errors": len(errors),
        "errors": errors[:20],
        "book_source_counts": src_counts,
        "cadence_honesty": cadence,
        "focus_cell": focus,
        "strategies": strat_summary,
        "verdict": verdict,
        "paths": {
            "summary": str(OUT / "summary.json"),
            "figs": str(FIG),
            "notebook": str(LAB / "strategy_lab.ipynb"),
            "doc": str(LAB / "STRATEGY_LAB.md"),
        },
    }

    fig_paths = plot_all(cells, summary)
    summary["fig_paths"] = fig_paths
    save_json(OUT / "summary.json", summary)
    # light cell rollup without huge arrays
    rollup = []
    for c in cells:
        rollup.append(
            {
                "day": c["day"],
                "symbol": c["symbol"],
                "venue": c["venue"],
                "n_trades": c["n_trades"],
                "n_events": c["n_events"],
                "book": c["book"],
                "thin_cap": c["thin_cap"],
                "results": {
                    k: {
                        "final_equity_bps": v["final_equity_bps"],
                        "max_dd_bps": v["max_dd_bps"],
                        "n_fills": v["n_fills"],
                        "sharpe_like": v.get("sharpe_like"),
                    }
                    for k, v in c["results"].items()
                },
            }
        )
    save_json(OUT / "cells_rollup.json", rollup)
    nb_path = build_notebook(summary, fig_paths)
    print(f"[strategy_lab] wrote {OUT/'summary.json'} figs={len(fig_paths)} nb={nb_path}", flush=True)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force-panel", action="store_true")
    ap.add_argument("--workers", type=int, default=14)
    ap.add_argument("--max-trades", type=int, default=100_000)
    ap.add_argument("--friction-bps", type=float, default=FRICTION_BPS)
    ap.add_argument("--hl-only", action="store_true", help="Run HL cells only (faster book focus)")
    args = ap.parse_args()
    venues = ("hyperliquid",) if args.hl_only else None
    run(
        force_panel=args.force_panel,
        workers=args.workers,
        max_trades=args.max_trades,
        friction_bps=args.friction_bps,
        venues=venues,
    )


if __name__ == "__main__":
    main()
