"""Trade-tape loaders, UTC-day clip, and completeness flags."""

from __future__ import annotations

from typing import Any

import numpy as np

from ares_micro.core.arrays import asof_join, day_bounds_ns, normalize_side
from research.md.constants import CORE_VENUES
from research.md.env import ensure_env
from research.md.symbols import (
    hl_trade_instrument,
    normalize_underlying,
    normalize_venue,
    venue_instrument,
)


def load_trades(
    symbol: str,
    days: list[str],
    max_files: int = 24,
    *,
    prefer_shards: bool = True,
    venue: str = "hyperliquid",
    use_flat_ids: bool = True,
    quiet: bool = False,
):
    """Load warehouse trade tape with venue-native symbol normalize.

    Hyperliquid single-day + ``use_flat_ids`` uses opaque ids on flat-era days.
    Kraken / Deribit always go through ``venue_instrument``.
    """
    from startarb.data.trades import load_trade_tape

    v = normalize_venue(venue)
    if v == "hyperliquid" and use_flat_ids and len(days) == 1:
        inst: str | int = hl_trade_instrument(symbol, days[0])
        return load_trade_tape(
            v, inst, days=days, max_files=max_files, prefer_shards=prefer_shards, quiet=quiet
        )
    inst_s = venue_instrument(symbol, v)
    return load_trade_tape(
        v, inst_s, days=days, max_files=max_files, prefer_shards=prefer_shards, quiet=quiet
    )


def clip_tape_to_utc_day(tape: Any, day: str) -> dict[str, np.ndarray]:
    """Keep prints whose source_ts falls in [day, day+1) UTC.

    Flat-era warehouse objects often bleed across calendar days; clipping
    avoids double-counting. Falls back to unclipped arrays if the UTC window
    is empty (``clipped=False``).
    """
    ts = np.asarray(tape.ts_ns, dtype=np.int64)
    side = np.asarray(tape.side, dtype=np.float64)
    qty = np.asarray(tape.qty_coin, dtype=np.float64)
    px = np.asarray(tape.price, dtype=np.float64) if hasattr(tape, "price") else np.zeros_like(qty)
    lo, hi = day_bounds_ns(day)
    m = (ts >= lo) & (ts < hi)
    clipped = bool(m.any())
    if not clipped:
        m = np.ones(ts.shape, dtype=bool)
    return {
        "ts": ts[m],
        "side": side[m],
        "qty": qty[m],
        "px": px[m],
        "clipped": clipped,
        "n_raw": int(ts.size),
        "n": int(m.sum()) if m.dtype == bool else int(ts.size),
        "day": day,
    }


def day_completeness(
    clipped: dict[str, np.ndarray],
    day: str,
    *,
    min_trades: int = 500,
    min_span_s: float = 6 * 3600,
    min_coverage: float = 0.25,
) -> dict[str, Any]:
    """UTC-day completeness flags (PIN lesson: opaque flat-id + UTC clip)."""
    ts = np.asarray(clipped.get("ts", []), dtype=np.int64)
    n = int(ts.size)
    lo, hi = day_bounds_ns(day)
    out: dict[str, Any] = {
        "day": day,
        "n": n,
        "clipped": bool(clipped.get("clipped", False)),
        "span_s": 0.0,
        "coverage": 0.0,
        "t_first": None,
        "t_last": None,
        "complete": False,
        "reasons": [],
    }
    if n == 0:
        out["reasons"].append("empty")
        return out
    t0, t1 = int(ts.min()), int(ts.max())
    span_s = max(0.0, (t1 - t0) / 1e9)
    coverage = span_s / 86_400.0
    out.update(
        {
            "span_s": span_s,
            "coverage": coverage,
            "t_first": t0,
            "t_last": t1,
            "within_bounds": bool(t0 >= lo and t1 < hi),
        }
    )
    reasons = []
    if not out["clipped"]:
        reasons.append("unclipped_fallback")
    if n < min_trades:
        reasons.append(f"n<{min_trades}")
    if span_s < min_span_s:
        reasons.append(f"span<{min_span_s}s")
    if coverage < min_coverage:
        reasons.append(f"coverage<{min_coverage}")
    out["reasons"] = reasons
    out["complete"] = len(reasons) == 0
    return out


def load_day_trades(
    venue: str,
    symbol: str,
    day: str,
    *,
    max_files: int = 24,
    quiet: bool = False,
) -> dict[str, Any]:
    """One-shot: load → UTC clip → completeness for a venue/symbol/day."""
    ensure_env()
    v = normalize_venue(venue)
    inst = venue_instrument(symbol, v)
    tape = load_trades(symbol, [day], max_files=max_files, venue=v, quiet=quiet)
    clipped = clip_tape_to_utc_day(tape, day)
    flags = day_completeness(clipped, day)
    return {
        "venue": v,
        "symbol_in": symbol,
        "instrument": inst if v != "hyperliquid" else hl_trade_instrument(symbol, day),
        "underlying": normalize_underlying(symbol),
        "day": day,
        "tape": clipped,
        "completeness": flags,
    }


def load_core_venues_day(
    symbol: str,
    day: str,
    *,
    venues: tuple[str, ...] = CORE_VENUES,
    max_files: int = 24,
    quiet: bool = False,
) -> dict[str, Any]:
    """Load the same underlying on HL + Deribit + Kraken for one UTC day."""
    out: dict[str, Any] = {"underlying": normalize_underlying(symbol), "day": day, "venues": {}}
    for v in venues:
        try:
            out["venues"][normalize_venue(v)] = load_day_trades(
                v, symbol, day, max_files=max_files, quiet=quiet
            )
        except Exception as exc:  # noqa: BLE001
            out["venues"][normalize_venue(v)] = {
                "venue": normalize_venue(v),
                "error": f"{type(exc).__name__}: {exc}",
                "completeness": {"complete": False, "reasons": ["load_error"]},
            }
    out["n_complete"] = sum(
        1
        for rec in out["venues"].values()
        if isinstance(rec, dict) and rec.get("completeness", {}).get("complete")
    )
    return out


def overlap_trades_with_mids(
    tape: Any,
    tob: dict[str, np.ndarray],
) -> dict[str, np.ndarray]:
    """Join clipped tape dict or TradeTape with TOB mids."""
    if isinstance(tape, dict):
        ts = np.asarray(tape["ts"], dtype=np.int64)
        px = np.asarray(tape["px"], dtype=np.float64)
        qty = np.asarray(tape["qty"], dtype=np.float64)
        side = normalize_side(tape["side"])
    else:
        ts = np.asarray(tape.ts_ns, dtype=np.int64)
        px = np.asarray(tape.price, dtype=np.float64)
        qty = np.asarray(tape.qty_coin, dtype=np.float64)
        side = normalize_side(tape.side)
    m0, m1 = int(tob["ts"].min()), int(tob["ts"].max())
    in_win = (ts >= m0) & (ts <= m1)
    if int(in_win.sum()) < 200:
        in_win = np.ones(ts.shape, dtype=bool)
    return {
        "ts": ts[in_win],
        "px": px[in_win],
        "qty": qty[in_win],
        "side": side[in_win],
        "notional": px[in_win] * qty[in_win],
        "mid0": asof_join(ts[in_win], tob["ts"], tob["mid"]),
    }


__all__ = [
    "clip_tape_to_utc_day",
    "day_completeness",
    "load_core_venues_day",
    "load_day_trades",
    "load_trades",
    "overlap_trades_with_mids",
]
