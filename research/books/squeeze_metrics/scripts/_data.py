"""Shared loaders for squeeze_metrics (HL + Deribit + Kraken).

Cloned/adapted from ``research/books/cd_me/scripts/_data.py`` — same real-quote
rules: warehouse trades via ``startarb.data.trades.load_trade_tape``, collector
TOB under ares-startarb ``results/xarb_md/tob``, UTC-day clip + completeness.
Mark-bar helpers feed GEX/VEX *crypto-adapted proxies* (basis / home mid RV /
funding / depth skew) when Deribit option-chain DDOI+greeks are unavailable.

Symbol normalize (esp. Kraken): underlying ``ETH`` / aliases ``ETH/USD``,
``ETH-USD`` → venue-native ``PF_ETHUSD`` via ``startarb.data.symbols.venue_symbol``
with a local fallback map if startarb config is unavailable.

Hard rules: real quotes only (HL+Deribit; Kraken dense ``spot_l2`` only);
quarantine ``trade_synth``; never soft-Promote TOB-cross α; ClickHouse MCP banned.

Data inventory: ``research/DATA_PATHS.md``.
Lib: ``research/lib/squeeze.py`` (do **not** merge into continuous.py / cdme.py / tob.py).
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

# Mercat catalog keys for Kraken *spot* L2 (warehouse stream=spot-000).
# Futures ``PF_*`` sealed public-md: trade/mark/index/funding/OI only — no BBO/L2.
_KRAKEN_SPOT_TOB: dict[str, str] = {
    "BTC": "spot|BTC/USD",
    "ETH": "spot|ETH/USD",
    "SOL": "spot|SOL/USD",
}

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


def _filter_tob_arrays(
    ts: np.ndarray,
    bid: np.ndarray,
    ask: np.ndarray,
    bsz: np.ndarray,
    asz: np.ndarray,
    day: str,
    *,
    max_spread_bps: float = 100.0,
    min_n: int = 30,
) -> dict[str, Any]:
    """UTC-day clip + crossed/absurd-spread filter shared by TOB loaders."""
    ts = np.asarray(ts, dtype=np.int64)
    bid = np.asarray(bid, dtype=np.float64)
    ask = np.asarray(ask, dtype=np.float64)
    bsz = np.asarray(bsz, dtype=np.float64)
    asz = np.asarray(asz, dtype=np.float64)
    lo, hi = day_bounds_ns(day)
    m = (ts >= lo) & (ts < hi) & np.isfinite(bid) & np.isfinite(ask) & (ask > bid) & (bid > 0)
    mid = 0.5 * (bid + ask)
    sp = np.full_like(mid, np.nan)
    sp[m] = 1e4 * (ask[m] - bid[m]) / mid[m]
    m = m & np.isfinite(sp) & (sp < max_spread_bps)
    if int(m.sum()) < min_n:
        raise RuntimeError(f"TOB thin for day={day}: n={int(m.sum())}")
    n = int(m.sum())
    return {
        "ts": ts[m],
        "bid": bid[m],
        "ask": ask[m],
        "mid": mid[m],
        "bid_sz": bsz[m] if bsz.size == ts.size else np.ones(n),
        "ask_sz": asz[m] if asz.size == ts.size else np.ones(n),
        "day": day,
        "n": n,
    }


def load_kraken_spot_tob_day(
    symbol: str,
    day: str,
    *,
    max_files: int = 24,
    quotes_per_minute: int = 10,
    min_quotes: int = 80,
) -> dict[str, Any]:
    """Kraken **spot** quoted TOB from warehouse ``l2_rebuild`` (S3 public-md spot shard).

    Instrument must be ``spot|ETH/USD`` — ``PF_ETHUSD`` / default ``venue_instrument``
    resolves to futures and has **no** L2 in mercat-kraken-md listings.
    """
    ensure_env()
    from startarb.data.bbo_stream import load_quote_stream

    u = normalize_underlying(symbol)
    inst = _KRAKEN_SPOT_TOB.get(u)
    if inst is None:
        raise KeyError(f"no Kraken spot TOB mapping for underlying={u}")
    qs = load_quote_stream(
        "kraken",
        inst,
        [day],
        table="l2_rebuild",
        max_files=max_files,
        prefer_shards=True,
        quotes_per_minute=quotes_per_minute,
        quiet=True,
        allow_trade_fallback=False,
    )
    if len(qs) < min_quotes:
        raise RuntimeError(
            f"kraken spot TOB too thin {inst}/{day}: n={len(qs)} < {min_quotes}"
        )
    out = _filter_tob_arrays(
        qs.ts_ns,
        qs.bid,
        qs.ask,
        qs.bid_qty,
        qs.ask_qty,
        day,
        min_n=min(min_quotes, 30),
    )
    out.update(
        {
            "venue": "kraken",
            "aliases": [inst, u],
            "source": "warehouse:kraken_spot_l2_rebuild",
            "instrument": inst,
            "market": "spot",
            "n_files": int(getattr(qs, "n_files", 0) or 0),
            "quoted_available": True,
        }
    )
    return out


def load_kraken_futures_trade_synth_tob_day(
    symbol: str,
    day: str,
    *,
    max_files: int = 64,
    quotes_per_minute: int = 10,
    min_quotes: int = 80,
) -> dict[str, Any]:
    """Kraken **futures** trade-synthesized TOB (``PF_*``) when L2/BBO absent in S3.

    Honest: not exchange quoted BBO — use for cross-venue **monitor** PIM only;
    never Promote as native quoted TOB. See ``out/kraken_s3_inventory.json``.
    """
    ensure_env()
    from startarb.data.bbo_stream import load_quote_stream

    u = normalize_underlying(symbol)
    inst = venue_instrument(u, "kraken")
    qs = load_quote_stream(
        "kraken",
        inst,
        [day],
        table="trade",
        max_files=max_files,
        prefer_shards=True,
        quotes_per_minute=quotes_per_minute,
        quiet=True,
        allow_trade_fallback=False,
    )
    if len(qs) < min_quotes:
        raise RuntimeError(
            f"kraken futures trade_synth too thin {inst}/{day}: n={len(qs)}"
        )
    src = str(getattr(qs, "source", "") or "")
    if "trade_synth" not in src:
        raise RuntimeError(f"expected trade_synth for kraken futures {day}: {src}")
    out = _filter_tob_arrays(
        qs.ts_ns,
        qs.bid,
        qs.ask,
        qs.bid_qty,
        qs.ask_qty,
        day,
        min_n=min(min_quotes, 30),
    )
    out.update(
        {
            "venue": "kraken",
            "aliases": [inst, u],
            "source": f"warehouse:kraken_futures_trade_synth/{src}",
            "instrument": inst,
            "market": "futures",
            "is_synth": True,
            "n_files": int(getattr(qs, "n_files", 0) or 0),
        }
    )
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
    allow_kraken_synth: bool = False,
) -> dict[str, np.ndarray]:
    """Best-effort **real-quote** TOB: warehouse L2/BBO first, else collector.

    Kraken default: **spot ``l2_rebuild`` only** (``spot|ETH/USD``). Futures
    ``trade_synth`` is quarantined — pass ``allow_kraken_synth=True`` only for
    labeled PROXY / NOT TOB sensitivity. Never treat synth as a third venue in
    primary PIM. See ``out/panel_completeness/``.
    """
    errors: list[str] = []
    v = normalize_venue(venue)
    if prefer_warehouse and day and v == "kraken":
        try:
            return load_kraken_spot_tob_day(
                symbol, day, max_files=max(warehouse_max_files, 12)
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"kraken_spot:{type(exc).__name__}:{exc}")
        if allow_kraken_synth:
            try:
                out = load_kraken_futures_trade_synth_tob_day(
                    symbol, day, max_files=max(warehouse_max_files, 32)
                )
                out["is_synth"] = True
                out["proxy_label"] = "PROXY_NOT_TOB_trade_synth"
                return out
            except Exception as exc:  # noqa: BLE001
                errors.append(f"kraken_futures_synth:{type(exc).__name__}:{exc}")
        # no synth fallback — day is 2-venue (HL↔Deribit) without Kraken quotes
    if prefer_warehouse and day and v != "kraken":
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
    mid_arr = np.asarray(mid)
    mid_ts_arr = np.asarray(mid_ts)
    if mid_arr.size == 0 or mid_ts_arr.size == 0:
        return out
    valid = (i0 >= 0) & (i0 < mid_ts_arr.size) & (i0 < mid_arr.size)
    out[valid] = mid_arr[i0[valid]]
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


# ---------------------------------------------------------------------------
# cd_me extras: marks / basis / multi-venue TOB panel / volume buckets
# ---------------------------------------------------------------------------

def load_day_marks(
    venue: str,
    symbol: str,
    day: str,
    *,
    bar_ns: int = 60_000_000_000,
    max_files: int = 24,
    quiet: bool = True,
) -> dict[str, Any]:
    """1m (default) mark/mid bars for DCM / basis construction."""
    ensure_env()
    from startarb.data.marks import load_mark_bars

    v = normalize_venue(venue)
    inst = venue_instrument(symbol, v)
    bars = load_mark_bars(v, inst, days=[day], bar_ns=bar_ns, max_files=max_files, quiet=quiet)
    close = np.asarray(bars["close"], dtype=np.float64)
    # ``time`` may be datetime64 — convert to ns
    time = bars["time"]
    if hasattr(time, "dtype") and np.issubdtype(time.dtype, np.datetime64):
        ts = time.astype("datetime64[ns]").astype(np.int64)
    else:
        ts = np.asarray(time, dtype=np.int64)
    return {
        "venue": v,
        "instrument": inst,
        "day": day,
        "ts": ts,
        "mid": close,
        "n": int(close.size),
        "source": bars.get("source"),
        "dt_s": float(bars.get("dt_s") or bar_ns / 1e9),
    }


def load_cross_venue_marks(
    symbol: str,
    day: str,
    *,
    venues: tuple[str, ...] = CORE_VENUES,
    bar_ns: int = 60_000_000_000,
    max_files: int = 24,
    quiet: bool = True,
) -> dict[str, Any]:
    """Per-venue mark bars for one UTC day (basis = log(perp/home) later)."""
    out: dict[str, Any] = {"underlying": normalize_underlying(symbol), "day": day, "venues": {}}
    for v in venues:
        try:
            out["venues"][normalize_venue(v)] = load_day_marks(
                v, symbol, day, bar_ns=bar_ns, max_files=max_files, quiet=quiet
            )
        except Exception as exc:  # noqa: BLE001
            out["venues"][normalize_venue(v)] = {
                "venue": normalize_venue(v),
                "error": f"{type(exc).__name__}: {exc}",
                "n": 0,
            }
    return out


def load_cross_venue_tob(
    symbol: str,
    day: str,
    *,
    venues: tuple[str, ...] = ("hyperliquid", "deribit"),
    prefer_warehouse: bool = True,
    warehouse_max_files: int = 8,
    allow_kraken_synth: bool = False,
    require_real_quotes: bool = True,
) -> dict[str, Any]:
    """Best-effort TOB per venue for one UTC day (warehouse then collector).

    Default venues are **HL + Deribit** (real quotes). Pass ``kraken`` only when
    spot_l2 is intended; ``allow_kraken_synth`` stays False unless building a
    quarantined PROXY appendix. Synth rows are dropped when
    ``require_real_quotes=True``.
    """
    out: dict[str, Any] = {
        "underlying": normalize_underlying(symbol),
        "day": day,
        "venues": {},
        "errors": {},
        "kraken_mode": None,
    }
    for v in venues:
        vn = normalize_venue(v)
        try:
            tob = load_venue_tob(
                vn,
                symbol,
                day=day,
                prefer_warehouse=prefer_warehouse,
                warehouse_max_files=warehouse_max_files,
                allow_kraken_synth=allow_kraken_synth and vn == "kraken",
            )
            is_synth = bool(tob.get("is_synth")) or ("trade_synth" in str(tob.get("source") or ""))
            if vn == "kraken":
                out["kraken_mode"] = "trade_synth" if is_synth else "spot_l2"
            if require_real_quotes and is_synth:
                out["errors"][vn] = (
                    "refused_trade_synth_PROXY_NOT_TOB "
                    f"(source={tob.get('source')})"
                )
                continue
            out["venues"][vn] = tob
        except Exception as exc:  # noqa: BLE001
            out["errors"][vn] = f"{type(exc).__name__}: {exc}"
            if vn == "kraken":
                out["kraken_mode"] = "missing"
    out["n_venues"] = len(out["venues"])
    return out


def trade_volume_buckets(
    tape: dict[str, np.ndarray],
    *,
    bucket_s: float = 3600.0,
    day: str | None = None,
) -> dict[str, np.ndarray]:
    """Notional + count + signed imbalance per UTC bucket from clipped tape."""
    ts = np.asarray(tape["ts"], dtype=np.int64)
    px = np.asarray(tape.get("px", np.ones(ts.shape)), dtype=np.float64)
    qty = np.asarray(tape.get("qty", np.ones(ts.shape)), dtype=np.float64)
    side = normalize_side(tape.get("side", np.ones(ts.shape)))
    if ts.size == 0:
        empty = np.zeros(0, dtype=np.float64)
        return {
            "ts": np.zeros(0, dtype=np.int64),
            "notional": empty,
            "n_trades": empty,
            "imbalance": empty,
            "bucket_s": float(bucket_s),
        }
    step = int(float(bucket_s) * 1e9)
    if day:
        lo, _ = day_bounds_ns(day)
        t0 = lo
    else:
        t0 = int(ts.min() // step * step)
    bin_id = ((ts - t0) // step).astype(np.int64)
    n_bins = int(bin_id.max()) + 1
    centers = t0 + (np.arange(n_bins, dtype=np.int64) + 1) * step // 2
    notional = px * qty
    signed = side * qty
    notional_b = np.bincount(bin_id, weights=notional, minlength=n_bins).astype(np.float64)
    qty_b = np.bincount(bin_id, weights=qty, minlength=n_bins).astype(np.float64)
    signed_b = np.bincount(bin_id, weights=signed, minlength=n_bins).astype(np.float64)
    n_b = np.bincount(bin_id, minlength=n_bins).astype(np.float64)
    imb = np.full(n_bins, np.nan, dtype=np.float64)
    ok = qty_b > 0
    imb[ok] = signed_b[ok] / qty_b[ok]
    return {
        "ts": centers,
        "notional": notional_b,
        "n_trades": n_b,
        "imbalance": imb,
        "bucket_s": float(bucket_s),
    }


def funding_proxy_from_marks(
    home_mid: np.ndarray,
    home_ts: np.ndarray,
    *,
    window: int = 60,
) -> dict[str, np.ndarray]:
    """Crude public funding-stress proxy when funding table is absent.

    Uses rolling |Δlog mid| mean as a carry/funding intensity stand-in — labeled
    ``funding_proxy`` (not exchange funding rate). Prefer real funding when wired.
    """
    mid = np.asarray(home_mid, dtype=np.float64)
    ts = np.asarray(home_ts, dtype=np.int64)
    r = np.diff(np.log(np.clip(mid, 1e-12, None)), prepend=np.nan)
    abs_r = np.abs(r)
    out = np.full(mid.shape, np.nan, dtype=np.float64)
    w = max(int(window), 2)
    for i in range(mid.size):
        j0 = i - w + 1
        if j0 < 0:
            continue
        chunk = abs_r[j0 : i + 1]
        chunk = chunk[np.isfinite(chunk)]
        if chunk.size >= w // 2:
            out[i] = float(np.mean(chunk))
    return {"ts": ts, "funding_proxy": out}


# ---------------------------------------------------------------------------
# squeeze_metrics extras: funding / OI / IV table probes (honest thin/absent)
# ---------------------------------------------------------------------------

def _column_batch_arrays(batch: Any) -> dict[str, np.ndarray]:
    """Normalize warehouse ColumnBatch / dict to plain ndarray columns."""
    if batch is None:
        return {}
    if isinstance(batch, dict):
        return {str(k): np.asarray(v) for k, v in batch.items()}
    # ColumnBatch: dict-like via .columns / __getitem__
    cols = getattr(batch, "columns", None)
    if cols is None and hasattr(batch, "names"):
        cols = batch.names
    if cols is None:
        try:
            cols = list(batch)  # type: ignore[arg-type]
        except Exception:
            return {}
    out: dict[str, np.ndarray] = {}
    for c in cols:
        try:
            out[str(c)] = np.asarray(batch[c])
        except Exception:
            continue
    return out


def load_deribit_table_day(
    table: str,
    symbol: str,
    day: str,
    *,
    max_files: int = 16,
    quiet: bool = True,
) -> dict[str, Any]:
    """Best-effort Deribit warehouse table load (funding / open_interest / implied_vol).

    Option-chain DDOI + BS greeks are **not** in startarb exports today. These
    tables are mostly perpetual/instrument-level; treat any success as a bonus
    input to crypto-adapted GEX/VEX proxies, not paper-grade GEX.
    """
    ensure_env()
    from warehouse import open_day
    from startarb.data.instruments import instrument_id as _iid

    inst = venue_instrument(symbol, "deribit")
    try:
        iid = int(_iid("deribit", inst))
        ids: list[int] | None = [iid]
    except Exception:
        ids = None
    try:
        batch = open_day("deribit", day).load(
            table, instrument_ids=ids, max_files=max_files
        )
        arr = _column_batch_arrays(batch)
        n = int(next(iter(arr.values())).size) if arr else 0
        return {
            "venue": "deribit",
            "table": table,
            "instrument": inst,
            "day": day,
            "n": n,
            "columns": arr,
            "ok": n > 0,
            "label": f"warehouse:deribit:{table}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "venue": "deribit",
            "table": table,
            "instrument": inst,
            "day": day,
            "n": 0,
            "columns": {},
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }




def _mercat_deribit_path() -> Path:
    return Path(os.environ.get("MERCAT_DERIBIT_SRC") or (Path.home() / "lab" / "lab-n2070" / "deribit" / "src"))


def load_deribit_instrument_map(*, refresh: bool = False) -> list[dict[str, Any]]:
    """Deribit instrument catalog (options + futures) via mercat_deribit."""
    src = str(_mercat_deribit_path())
    if src not in sys.path:
        sys.path.insert(0, src)
    from mercat_deribit._instruments import load_instrument_map

    return list(load_instrument_map(refresh=refresh))


def deribit_option_catalog(
    underlying: str = "ETH",
    *,
    refresh: bool = False,
) -> dict[int, dict[str, Any]]:
    """instrument_id → compact option row for inverse ETH/BTC options."""
    u = normalize_underlying(underlying)
    rows = load_deribit_instrument_map(refresh=refresh)
    out: dict[int, dict[str, Any]] = {}
    for r in rows:
        if r.get("kind") != "option":
            continue
        name = str(r.get("instrument_name") or r.get("name") or "")
        # Prefer classic inverse ``ETH-26SEP25-4000-C`` style (not ETH_USDC linear)
        if not name.startswith(f"{u}-"):
            continue
        if name.count("-") < 3:
            continue
        iid = int(r["instrument_id"])
        out[iid] = r
    return out


def load_eth_option_iv_day(
    day: str,
    *,
    underlying: str = "ETH",
    max_files: int = 64,
    min_rows_per_instrument: int = 1,
) -> dict[str, Any]:
    """Load Deribit ``implied_vol`` for ETH (or BTC) options; join catalog.

    Returns last IV per option instrument + strike/expiry metadata.
    ``iv_ticks`` scale: mercat typically 1e8 → divide by 1e8 for decimal vol;
    values already in percent (e.g. 45) are left for ``squeeze.chain_exposures``
    to normalize.
    """
    ensure_env()
    from warehouse import open_day

    cat = deribit_option_catalog(underlying)
    if not cat:
        return {"ok": False, "error": "empty_option_catalog", "day": day, "n": 0}

    batch = open_day("deribit", day).load("implied_vol", max_files=max_files)
    ids = np.asarray(batch.columns["instrument_id"])
    ts = np.asarray(batch.columns["source_ts_ns"], dtype=np.uint64)
    iv_ticks = np.asarray(batch.columns["iv_ticks"], dtype=np.float64)
    # keep only catalog options
    mask = np.array([int(i) in cat for i in ids], dtype=bool)
    ids, ts, iv_ticks = ids[mask], ts[mask], iv_ticks[mask]
    if ids.size == 0:
        return {
            "ok": False,
            "error": "no_option_iv_rows",
            "day": day,
            "n": 0,
            "n_catalog": len(cat),
        }
    order = np.argsort(ts)
    ids, ts, iv_ticks = ids[order], ts[order], iv_ticks[order]
    last: dict[int, tuple[float, int]] = {}
    for iid, t, iv in zip(ids, ts, iv_ticks):
        last[int(iid)] = (float(iv), int(t))

    # scale: if median huge, treat as 1e8 ticks
    raw_vals = np.array([v for v, _ in last.values()], dtype=np.float64)
    scale = 1e8 if np.nanmedian(np.abs(raw_vals)) > 10 else 1.0

    day_end = np.datetime64(day) + np.timedelta64(1, "D")
    # ns since epoch for day end approx via datetime
    from datetime import datetime, timezone

    day_end_ns = int(
        datetime(int(day[:4]), int(day[5:7]), int(day[8:10]), tzinfo=timezone.utc).timestamp()
        * 1e9
    ) + 86_400_000_000_000

    flags: list[str] = []
    strikes: list[float] = []
    ttm: list[float] = []
    ivs: list[float] = []
    iids: list[int] = []
    names: list[str] = []
    for iid, (iv_raw, _) in last.items():
        meta = cat[iid]
        strike = meta.get("strike")
        opt = meta.get("option_type") or ""
        exp_ms = meta.get("expiration_timestamp")
        name = str(meta.get("instrument_name") or "")
        if strike is None or exp_ms is None:
            # parse name ETH-2OCT26-2000-C
            parts = name.split("-")
            if len(parts) >= 4:
                try:
                    strike = float(parts[2])
                    opt = parts[3][:1]
                except Exception:
                    continue
            else:
                continue
        # option_type may be 'call'/'put'
        o = str(opt).strip().upper()[:1]
        if o not in ("C", "P"):
            if str(opt).lower().startswith("c"):
                o = "C"
            elif str(opt).lower().startswith("p"):
                o = "P"
            else:
                continue
        exp_ns = int(exp_ms) * 1_000_000
        t_years = max((exp_ns - day_end_ns) / (365.25 * 24 * 3600 * 1e9), 1e-6)
        iv = float(iv_raw) / scale
        flags.append(o)
        strikes.append(float(strike))
        ttm.append(float(t_years))
        ivs.append(iv)
        iids.append(iid)
        names.append(name)

    return {
        "ok": len(iids) > 0,
        "day": day,
        "underlying": normalize_underlying(underlying),
        "n": len(iids),
        "n_iv_raw": int(ids.size),
        "iv_scale": scale,
        "instrument_ids": np.asarray(iids, dtype=np.int64),
        "names": names,
        "flags": np.asarray(flags),
        "strikes": np.asarray(strikes, dtype=np.float64),
        "ttm_years": np.asarray(ttm, dtype=np.float64),
        "iv": np.asarray(ivs, dtype=np.float64),
        "label": "warehouse:deribit:implied_vol:options",
    }


def load_eth_option_trades_day(
    day: str,
    *,
    underlying: str = "ETH",
    max_files: int = 64,
    qty_lot_scale: float = 1e8,
) -> dict[str, Any]:
    """Option trades for trade-flow DDOI proxy.

    ``md_qty_lots`` is mercat tick-scaled (typically ×1e8). We expose both raw
    lots and ``qty`` = lots / ``qty_lot_scale`` (contract units).
    """
    ensure_env()
    from warehouse import open_day

    cat = deribit_option_catalog(underlying)
    batch = open_day("deribit", day).load("trade", max_files=max_files)
    ids = np.asarray(batch.columns["instrument_id"])
    mask = np.array([int(i) in cat for i in ids], dtype=bool)
    if not np.any(mask):
        return {"ok": False, "n": 0, "day": day, "error": "no_option_trades"}
    lots = np.asarray(batch.columns["md_qty_lots"], dtype=np.float64)[mask]
    cols = {
        "instrument_id": ids[mask],
        "source_ts_ns": np.asarray(batch.columns["source_ts_ns"])[mask],
        "price_ticks": np.asarray(batch.columns["price_ticks"], dtype=np.float64)[mask],
        "md_qty_lots": lots,
        "qty": lots / float(qty_lot_scale),
        "aggressor_side": np.asarray(batch.columns["aggressor_side"])[mask],
    }
    return {
        "ok": True,
        "day": day,
        "underlying": normalize_underlying(underlying),
        "n": int(mask.sum()),
        "n_instruments": int(len(set(int(i) for i in cols["instrument_id"]))),
        "qty_lot_scale": float(qty_lot_scale),
        "columns": cols,
        "label": "warehouse:deribit:trade:options",
    }


def load_deribit_underlying_mark(
    day: str,
    *,
    underlying: str = "ETH",
    max_files: int = 16,
) -> dict[str, Any]:
    """Deribit perpetual mark path for underlying S."""
    return load_day_marks("deribit", underlying, day, max_files=max_files)



def load_squeeze_feature_inputs(
    symbol: str,
    day: str,
    *,
    venues: tuple[str, ...] = ("hyperliquid", "deribit"),
    warehouse_max_files: int = 8,
    allow_kraken_synth: bool = False,
    include_kraken_spot: bool = True,
) -> dict[str, Any]:
    """One-shot panel inputs for squeeze proxies: real TOB + marks + trades.

    Never returns trade_synth as primary TOB. Optional Kraken spot_l2 only.
    """
    ensure_env()
    vlist = list(venues)
    if include_kraken_spot and "kraken" not in vlist:
        # probe only; may be absent → 2-venue day
        pass
    tob = load_cross_venue_tob(
        symbol,
        day,
        venues=tuple(vlist),
        warehouse_max_files=warehouse_max_files,
        allow_kraken_synth=allow_kraken_synth,
        require_real_quotes=True,
    )
    if include_kraken_spot and "kraken" not in tob["venues"]:
        try:
            kr = load_kraken_spot_tob_day(symbol, day, max_files=max(warehouse_max_files, 12))
            tob["venues"]["kraken"] = kr
            tob["kraken_mode"] = "spot_l2"
            tob["n_venues"] = len(tob["venues"])
        except Exception as exc:  # noqa: BLE001
            tob["errors"]["kraken"] = f"{type(exc).__name__}: {exc}"
            tob["kraken_mode"] = tob.get("kraken_mode") or "missing"

    marks = load_cross_venue_marks(symbol, day, venues=("hyperliquid", "deribit", "kraken"))
    trades: dict[str, Any] = {}
    for v in ("hyperliquid", "deribit"):
        try:
            trades[v] = load_day_trades(v, symbol, day, quiet=True)
        except Exception as exc:  # noqa: BLE001
            trades[v] = {"venue": v, "error": f"{type(exc).__name__}: {exc}"}

    funding = load_deribit_table_day("funding", symbol, day, max_files=8)
    oi = load_deribit_table_day("open_interest", symbol, day, max_files=8)
    try:
        opt_iv = load_eth_option_iv_day(day, underlying=normalize_underlying(symbol), max_files=12)
    except Exception as exc:  # noqa: BLE001
        opt_iv = {"ok": False, "n": 0, "error": f"{type(exc).__name__}: {exc}"}
    try:
        opt_tr = load_eth_option_trades_day(day, underlying=normalize_underlying(symbol), max_files=16)
    except Exception as exc:  # noqa: BLE001
        opt_tr = {"ok": False, "n": 0, "error": f"{type(exc).__name__}: {exc}"}

    return {
        "underlying": normalize_underlying(symbol),
        "day": day,
        "tob": tob,
        "marks": marks,
        "trades": trades,
        "deribit_funding": funding,
        "deribit_oi": oi,
        "option_iv": opt_iv,
        "option_trades": opt_tr,
        "options_chain_available": bool(opt_iv.get("ok")),
        "honesty": (
            "Deribit implied_vol covers OPTIONS; open_interest table is FUTURES-ONLY. "
            "DDOI = trade-flow proxy from option trades (or live API OI). "
            "GEX/VEX from BS γ/vanna on IV chain. Underlying TOB = HL+Deribit real quotes; "
            "Kraken spot_l2 only when dense. Never trade_synth; never TOB-cross α."
        ),
    }

