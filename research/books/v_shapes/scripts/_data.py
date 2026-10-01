"""Shared loaders for v_shapes (HL + Deribit + Kraken).

Mirrors ``research/books/empirical_mm/scripts/_data.py`` patterns: warehouse
trades via ``startarb.data.trades.load_trade_tape``, collector TOB under
ares-startarb ``results/xarb_md/tob``, UTC-day clip + day-completeness flags.

Symbol normalize (esp. Kraken): underlying ``ETH`` / aliases ``ETH/USD``,
``ETH-USD`` → venue-native ``PF_ETHUSD`` via ``startarb.data.symbols.venue_symbol``
with a local fallback map if startarb config is unavailable.

Data inventory: ``research/DATA_PATHS.md``. ClickHouse MCP banned.
"""


from __future__ import annotations

import os

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

STARTARB = Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb'))
WAREHOUSE_SRC = Path(os.environ.get('WAREHOUSE_SRC') or ((Path(os.environ.get('WAREHOUSE_ROOT') or (Path.home() / 'lab' / 'lab-n2070' / 'warehouse')) / 'src')))
MICRO_ROOT = Path(__file__).resolve().parents[3]
for _p in (str(WAREHOUSE_SRC), str(STARTARB / "src"), str(MICRO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DEFAULT_TOB = STARTARB / "results" / "xarb_md" / "tob"
HL_FLAT_IDS: dict[str, int] = {
    "BTC": 3860219501,
    "ETH": 3337431014,
}
HL_FLAT_CUTOFF = "2026-09-10"
LISTING_CACHE = Path.home() / ".cache" / "warehouse" / "listings"

# Core venues locked by book plan
CORE_VENUES = ("hyperliquid", "deribit", "kraken")

# Fallback when startarb symbols.yaml is not importable
_VENUE_SYMBOL_FALLBACK: dict[str, dict[str, str]] = {
    "BTC": {
        "hyperliquid": "BTC",
        "deribit": "BTC-PERPETUAL",
        "kraken": "PF_XBTUSD",
        "lighter": "BTC",
        "extended": "BTC-USD",
        "risex": "BTC/USDC",
    },
    "ETH": {
        "hyperliquid": "ETH",
        "deribit": "ETH-PERPETUAL",
        "kraken": "PF_ETHUSD",
        "lighter": "ETH",
        "extended": "ETH-USD",
        "risex": "ETH/USDC",
    },
    "SOL": {
        "hyperliquid": "SOL",
        "deribit": "SOL_USDC-PERPETUAL",
        "kraken": "PF_SOLUSD",
        "lighter": "SOL",
        "extended": "SOL-USD",
        "risex": "SOL/USDC",
    },
}

# Common aliases → underlying
_ALIAS_TO_UNDERLYING: dict[str, str] = {
    "BTC": "BTC",
    "XBT": "BTC",
    "BTC/USD": "BTC",
    "BTC-USD": "BTC",
    "BTC/USDC": "BTC",
    "PF_XBTUSD": "BTC",
    "BTC-PERPETUAL": "BTC",
    "ETH": "ETH",
    "ETH/USD": "ETH",
    "ETH-USD": "ETH",
    "ETH/USDC": "ETH",
    "PF_ETHUSD": "ETH",
    "ETH-PERPETUAL": "ETH",
    "SOL": "SOL",
    "SOL/USD": "SOL",
    "SOL-USD": "SOL",
    "SOL/USDC": "SOL",
    "PF_SOLUSD": "SOL",
    "SOL_USDC-PERPETUAL": "SOL",
}


def ensure_env() -> None:
    from startarb.env import ensure_env as _e

    _e()


def normalize_underlying(symbol: str) -> str:
    """Map venue-native or slash aliases to canonical underlying (BTC/ETH/SOL)."""
    s = str(symbol).strip().upper().replace(" ", "")
    if s in _ALIAS_TO_UNDERLYING:
        return _ALIAS_TO_UNDERLYING[s]
    # strip common quote suffixes
    for suf in ("/USD", "-USD", "/USDC", "-USDC", "-PERPETUAL"):
        if s.endswith(suf):
            base = s[: -len(suf)]
            if base in _ALIAS_TO_UNDERLYING:
                return _ALIAS_TO_UNDERLYING[base]
            if base in _VENUE_SYMBOL_FALLBACK:
                return base
    if s in _VENUE_SYMBOL_FALLBACK:
        return s
    return s


def normalize_venue(venue: str) -> str:
    v = str(venue).strip().lower()
    if v in ("hl", "hyperliquid"):
        return "hyperliquid"
    if v in ("db", "deribit"):
        return "deribit"
    if v in ("kr", "kraken"):
        return "kraken"
    return v


def venue_instrument(symbol: str, venue: str) -> str:
    """Underlying or alias → venue-native catalog symbol.

    Kraken examples: ``ETH`` / ``ETH/USD`` → ``PF_ETHUSD``;
    ``BTC`` / ``XBT`` → ``PF_XBTUSD``.
    """
    u = normalize_underlying(symbol)
    v = normalize_venue(venue)
    try:
        from startarb.data.symbols import venue_symbol

        return str(venue_symbol(u, v))
    except Exception:
        table = _VENUE_SYMBOL_FALLBACK.get(u)
        if not table or v not in table:
            # already venue-native?
            return str(symbol).strip()
        return table[v]


def resolve_days(
    days: list[str] | None,
    venue: str = "hyperliquid",
    n: int = 3,
    *,
    prefer_listing_cache: bool = True,
) -> list[str]:
    if days:
        return days
    v = normalize_venue(venue)
    if prefer_listing_cache:
        bucket = {
            "hyperliquid": "mercat-hyperliquid-md",
            "deribit": "mercat-deribit-md",
            "kraken": "mercat-kraken-md",
            "lighter": "mercat-lighter-md",
            "extended": "mercat-extended-md",
            "risex": "mercat-risex-md",
        }.get(v)
        if bucket:
            root = LISTING_CACHE / bucket
            if root.is_dir():
                cached = sorted(p.stem for p in root.glob("*.json"))
                if cached:
                    return cached[-n:] if n > 0 else cached
    # Avoid hanging S3 list_days on research hosts — listing cache is SoT.
    try:
        from warehouse import list_days

        return list_days(v)[-n:]
    except Exception:
        return []


def hl_trade_instrument(symbol: str, day: str) -> str | int:
    """Opaque flat id for ≤FLAT_CUTOFF; catalog name thereafter."""
    sym = normalize_underlying(symbol)
    if day <= HL_FLAT_CUTOFF and sym in HL_FLAT_IDS:
        return HL_FLAT_IDS[sym]
    return venue_instrument(sym, "hyperliquid")


def day_bounds_ns(day: str) -> tuple[int, int]:
    t0 = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    start = int(t0.timestamp() * 1e9)
    return start, start + 86_400_000_000_000


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
    """UTC-day completeness flags (PIN lesson: opaque flat-id + UTC clip).

    ``coverage`` = span of first→last print / 86400. A day is ``complete`` when
    clipped, ``n >= min_trades``, span ≥ ``min_span_s``, and coverage ≥
    ``min_coverage``. Warehouse tails often fail — always report flags in
    EXP_REPORT; do not Promote on incomplete days alone.
    """
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
        except Exception as exc:  # noqa: BLE001 — desk loaders must surface per-venue failure
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


def collector_tob_days(tob_root: Path = DEFAULT_TOB) -> list[str]:
    """UTC days present under the WS collector archive (``YYYYMMDD`` dirs)."""
    if not tob_root.is_dir():
        return []
    out = []
    for p in sorted(tob_root.iterdir()):
        if p.is_dir() and len(p.name) == 8 and p.name.isdigit():
            out.append(f"{p.name[:4]}-{p.name[4:6]}-{p.name[6:8]}")
    return out


def load_collector_tob(
    venue: str,
    symbol: str,
    day: str | None = None,
    tob_root: Path = DEFAULT_TOB,
    *,
    max_rows: int = 300_000,
    max_day_dirs: int = 2,
) -> dict[str, np.ndarray]:
    """Collector TOB for a venue/symbol (symbol matched case-insensitive).

    Kraken collector rows may use ``ETH`` or ``PF_ETHUSD`` — we match either
    the underlying or the venue-native instrument. When ``day`` is set, only
    that ``YYYYMMDD`` archive dir is read.
    """
    import pandas as pd
    import pyarrow.parquet as pq

    v = normalize_venue(venue)
    u = normalize_underlying(symbol)
    native = venue_instrument(u, v).upper()
    aliases = {u.upper(), native, str(symbol).strip().upper()}

    if day:
        dname = day.replace("-", "")
        day_dirs = [tob_root / dname]
        if not day_dirs[0].is_dir():
            raise FileNotFoundError(f"no collector TOB dir for {day}: {day_dirs[0]}")
    else:
        day_dirs = sorted(p for p in tob_root.iterdir() if p.is_dir())
        if not day_dirs:
            raise FileNotFoundError(tob_root)
        day_dirs = day_dirs[-max_day_dirs:]
    frames = []
    for d in day_dirs:
        for f in sorted(d.glob("tob_*.parquet")):
            t = pq.read_table(
                f, columns=["ts", "venue", "symbol", "bid", "ask", "bid_sz", "ask_sz"]
            ).to_pandas()
            frames.append(t)
    if not frames:
        raise RuntimeError(f"no collector parquet under {day_dirs}")
    df = pd.concat(frames, ignore_index=True)
    sym = df["symbol"].astype(str).str.upper()
    df = df[(df["venue"].astype(str).str.lower() == v) & sym.isin(aliases)]
    df = df.sort_values("ts")
    if len(df) > max_rows:
        df = df.iloc[:: max(1, len(df) // max_rows)]
    if df.empty:
        raise RuntimeError(f"no collector TOB for {v}/{symbol} (tried {sorted(aliases)})")
    bid = df["bid"].to_numpy(np.float64)
    ask = df["ask"].to_numpy(np.float64)
    return {
        "ts": df["ts"].to_numpy(np.int64),
        "bid": bid,
        "ask": ask,
        "mid": 0.5 * (bid + ask),
        "bid_sz": df["bid_sz"].to_numpy(np.float64),
        "ask_sz": df["ask_sz"].to_numpy(np.float64),
        "venue": v,
        "aliases": sorted(aliases),
        "source": "collector",
        "day": day,
    }


def load_warehouse_tob(
    venue: str,
    symbol: str,
    day: str,
    *,
    max_files: int = 8,
    quotes_per_minute: int | None = 10,
    min_quotes: int = 80,
) -> dict[str, np.ndarray]:
    """Warehouse L2→TOB / BBO via ``startarb.data.bbo_stream.load_quote_stream``.

    Deribit ``l2_snapshot_level`` is the usable multi-day path. Kraken warehouse
    L2 is typically empty (hard ceiling). HL snap/L2 is sparse (~1/min); reject
    trade-synth fallbacks for liq Promotes (``source`` must not be trade_synth).
    """
    ensure_env()
    from startarb.data.bbo_stream import load_quote_stream

    v = normalize_venue(venue)
    inst = venue_instrument(symbol, v)
    qs = load_quote_stream(
        v,
        inst,
        [day],
        max_files=max_files,
        quiet=True,
        quotes_per_minute=quotes_per_minute,
        allow_trade_fallback=False,
    )
    n = len(qs)
    if n < min_quotes:
        raise RuntimeError(f"warehouse TOB too thin {v}/{inst}/{day}: n={n} < {min_quotes}")
    src = str(getattr(qs, "source", "") or "")
    if "trade_synth" in src:
        raise RuntimeError(f"refuse trade-synth TOB for {v}/{day}: {src}")
    bid = np.asarray(qs.bid, dtype=np.float64)
    ask = np.asarray(qs.ask, dtype=np.float64)
    return {
        "ts": np.asarray(qs.ts_ns, dtype=np.int64),
        "bid": bid,
        "ask": ask,
        "mid": 0.5 * (bid + ask),
        "bid_sz": np.asarray(qs.bid_qty, dtype=np.float64),
        "ask_sz": np.asarray(qs.ask_qty, dtype=np.float64),
        "venue": v,
        "aliases": [inst],
        "source": f"warehouse:{getattr(qs, 'table', '?')}/{src}",
        "day": day,
        "n": n,
    }


def load_venue_tob(
    venue: str,
    symbol: str,
    tob_root: Path = DEFAULT_TOB,
    *,
    day: str | None = None,
    max_rows: int = 300_000,
    max_day_dirs: int = 2,
    prefer_warehouse: bool = True,
    warehouse_max_files: int = 8,
) -> dict[str, np.ndarray]:
    """Best-effort TOB: warehouse L2/BBO first (when ``day`` known), else collector.

    Honest ceiling (2026-09 warehouse): Deribit L2 multi-day OK; Kraken warehouse
    L2 empty; collector archive only 2026-09-29/30. Do not invent TOB.
    """
    errors: list[str] = []
    if prefer_warehouse and day:
        try:
            return load_warehouse_tob(
                venue, symbol, day, max_files=warehouse_max_files
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"warehouse:{type(exc).__name__}:{exc}")
    try:
        return load_collector_tob(
            venue,
            symbol,
            day=day,
            tob_root=tob_root,
            max_rows=max_rows,
            max_day_dirs=max_day_dirs,
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"collector:{type(exc).__name__}:{exc}")
    raise RuntimeError(f"no TOB for {venue}/{symbol} day={day}; " + " | ".join(errors))


def load_hl_tob(
    symbol: str,
    tob_root: Path = DEFAULT_TOB,
    *,
    day: str | None = None,
    max_rows: int = 400_000,
) -> dict[str, np.ndarray]:
    return load_venue_tob(
        "hyperliquid", symbol, tob_root=tob_root, day=day, max_rows=max_rows
    )


def normalize_side(side: np.ndarray) -> np.ndarray:
    s = np.asarray(side, dtype=np.float64)
    uniq = set(np.unique(s[np.isfinite(s)]).tolist())
    if uniq <= {0.0, 1.0} or uniq <= {0, 1}:
        s = np.where(s > 0, 1.0, -1.0)
    return s


def asof_mid(trade_ts: np.ndarray, mid_ts: np.ndarray, mid: np.ndarray) -> np.ndarray:
    i0 = np.searchsorted(mid_ts, trade_ts, side="right") - 1
    out = np.full(trade_ts.shape, np.nan)
    valid = (i0 >= 0) & (i0 < mid_ts.size)
    out[valid] = mid[i0[valid]]
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
        "mid0": asof_mid(ts[in_win], tob["ts"], tob["mid"]),
    }
