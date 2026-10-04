"""Collector / warehouse / Kraken TOB loaders."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from research.md.constants import (
    DEFAULT_TOB,
    KRAKEN_FUT_TOB,
    KRAKEN_SPOT_TOB,
)
from research.md.env import ensure_env
from research.md.symbols import normalize_underlying, normalize_venue, venue_instrument
from ares_micro.book.tob import mid_price
from ares_micro.core.arrays import asof_join, day_bounds_ns, normalize_side


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
    mid = mid_price(bid, ask)
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
    inst = KRAKEN_SPOT_TOB.get(u)
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
            "table": getattr(qs, "table", "l2_rebuild"),
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
    never Promote as native quoted TOB.
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


def load_kraken_futures_tob_day(
    symbol: str,
    day: str,
    *,
    tob_root: Path = KRAKEN_FUT_TOB,
) -> dict[str, Any]:
    """Load Kraken **futures** quoted TOB from local ingest cache (if present).

    Cache written by book ``scripts/ingest_kraken_futures_tob.py`` (REST orderbook poll).
    Raises if cache empty for the day — caller falls back to spot L2 or proxies.
    """
    import pandas as pd
    import pyarrow.parquet as pq

    u = normalize_underlying(symbol)
    native = venue_instrument(u, "kraken").upper()
    aliases = {u.upper(), native, f"PF_{u}USD", "PF_XBTUSD" if u == "BTC" else native}
    day_dir = tob_root / day.replace("-", "")
    if not day_dir.is_dir():
        day_dir = tob_root / day
    if not day_dir.is_dir():
        raise FileNotFoundError(f"no Kraken futures TOB cache for {day} under {tob_root}")
    frames = []
    for f in sorted(day_dir.glob("tob_*.parquet")):
        t = pq.read_table(
            f, columns=["ts", "venue", "symbol", "bid", "ask", "bid_sz", "ask_sz"]
        ).to_pandas()
        frames.append(t)
    if not frames:
        raise FileNotFoundError(f"empty Kraken futures TOB cache {day_dir}")
    df = pd.concat(frames, ignore_index=True)
    sym = df["symbol"].astype(str).str.upper()
    df = df[(df["venue"].astype(str).str.lower() == "kraken") & sym.isin(aliases)]
    df = df.sort_values("ts")
    if df.empty:
        raise RuntimeError(f"no futures TOB rows for {aliases} on {day}")
    out = _filter_tob_arrays(
        df["ts"].to_numpy(np.int64),
        df["bid"].to_numpy(np.float64),
        df["ask"].to_numpy(np.float64),
        df["bid_sz"].to_numpy(np.float64),
        df["ask_sz"].to_numpy(np.float64),
        day,
        min_n=10,
    )
    out.update(
        {
            "venue": "kraken",
            "source": "ingest:kraken_futures_tob",
            "market": "futures",
            "instrument": native,
            "quoted_available": True,
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
        "mid": mid_price(bid, ask),
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
    max_files: int = 24,
    quotes_per_minute: int | None = 30,
    min_quotes: int = 30,
    allow_trade_fallback: bool = False,
    refuse_trade_synth: bool = True,
) -> dict[str, Any]:
    """Warehouse L2/BBO TOB for one UTC day via ``load_quote_stream``.

    Hyperliquid prefers ``l2_rebuild``. Kraken redirects to spot L2
    (``load_kraken_spot_tob_day``). Trade-synth refused by default.
    """
    ensure_env()
    from startarb.data.bbo_stream import load_quote_stream

    v = normalize_venue(venue)
    if v == "kraken":
        return load_kraken_spot_tob_day(
            symbol,
            day,
            max_files=max_files,
            quotes_per_minute=int(quotes_per_minute or 30),
            min_quotes=max(min_quotes, 30),
        )
    inst = venue_instrument(symbol, v)
    table = "l2_rebuild" if v == "hyperliquid" else None
    qs = load_quote_stream(
        v,
        inst,
        [day],
        table=table,
        max_files=max_files,
        prefer_shards=True,
        quotes_per_minute=quotes_per_minute,
        quiet=True,
        allow_trade_fallback=allow_trade_fallback,
    )
    n = len(qs)
    if n < min_quotes:
        raise RuntimeError(f"warehouse TOB too thin {v}/{inst}/{day}: n={n} < {min_quotes}")
    src = str(getattr(qs, "source", "") or "")
    if refuse_trade_synth and "trade_synth" in src:
        raise RuntimeError(f"refuse trade-synth TOB for {v}/{day}: {src}")
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
            "venue": v,
            "aliases": [inst],
            "source": f"warehouse:{getattr(qs, 'table', '?')}/{src}",
            "table": getattr(qs, "table", None),
            "n_files": int(getattr(qs, "n_files", 0) or 0),
            "day": day,
            "n": int(out["n"]),
        }
    )
    return out


def load_venue_tob(
    venue: str,
    symbol: str,
    tob_root: Path = DEFAULT_TOB,
    *,
    day: str | None = None,
    max_rows: int = 300_000,
    max_day_dirs: int = 2,
    prefer_warehouse: bool = False,
    warehouse_max_files: int = 8,
    allow_kraken_synth: bool = False,
) -> dict[str, np.ndarray]:
    """Best-effort TOB: optional warehouse L2/BBO, else collector.

    Default ``prefer_warehouse=False`` preserves collector-only call sites
    (empirical_mm / cross_miniflash / filmonov). Pass ``prefer_warehouse=True``
    + ``day`` for squeeze/cd_me warehouse-first behavior.

    Kraken warehouse path: **spot ``l2_rebuild`` only** unless
    ``allow_kraken_synth=True`` (PROXY / NOT TOB).
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
    if prefer_warehouse and day and v != "kraken":
        try:
            return load_warehouse_tob(
                venue, symbol, day, max_files=warehouse_max_files, quotes_per_minute=10
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
    if errors:
        raise RuntimeError(f"no TOB for {venue}/{symbol} day={day}; " + " | ".join(errors))
    raise RuntimeError(f"no TOB for {venue}/{symbol} day={day}")


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


def load_tob_day(
    venue: str,
    symbol: str,
    day: str,
    *,
    max_files: int = 24,
    tob_root: Path = DEFAULT_TOB,
) -> dict[str, Any]:
    """Best-effort TOB: collector → Kraken futures ingest → warehouse L2/spot."""
    v = normalize_venue(venue)
    u = normalize_underlying(symbol)
    lo, hi = day_bounds_ns(day)
    try:
        tob = load_venue_tob(v, u, tob_root=tob_root, max_day_dirs=6, max_rows=500_000)
        m = (tob["ts"] >= lo) & (tob["ts"] < hi)
        if int(m.sum()) >= 30:
            return {
                "ts": tob["ts"][m],
                "bid": tob["bid"][m],
                "ask": tob["ask"][m],
                "mid": tob["mid"][m],
                "bid_sz": tob["bid_sz"][m],
                "ask_sz": tob["ask_sz"][m],
                "venue": v,
                "source": "collector",
                "day": day,
            }
    except Exception:
        pass
    if v == "kraken":
        try:
            return load_kraken_futures_tob_day(u, day)
        except Exception:
            pass
        try:
            return load_kraken_spot_tob_day(u, day, max_files=max_files)
        except Exception:
            pass
        raise RuntimeError(
            f"no Kraken quoted TOB for {u}/{day} "
            "(futures cache empty; spot L2 miss; proxies are separate)"
        )
    return load_warehouse_tob(v, u, day, max_files=max_files)


def load_tob_any(
    venue: str,
    symbol: str,
    day: str,
    *,
    prefer_collector: bool = True,
) -> dict[str, np.ndarray]:
    """Collector TOB if present for the day; else warehouse quote stream."""
    if prefer_collector:
        try:
            tob = load_venue_tob(venue, symbol, max_day_dirs=4)
            lo, hi = day_bounds_ns(day)
            ts = np.asarray(tob["ts"], dtype=np.int64)
            m = (ts >= lo) & (ts < hi)
            if int(m.sum()) >= 50:
                out = {
                    k: (np.asarray(tob[k])[m] if isinstance(tob[k], np.ndarray) else tob[k])
                    for k in ("ts", "bid", "ask", "mid", "bid_sz", "ask_sz")
                }
                out["venue"] = normalize_venue(venue)
                out["day_clipped"] = True
                out["n"] = int(m.sum())
                out["source"] = "collector"
                return out
        except Exception:
            pass
    return load_warehouse_tob(venue, symbol, day)


def kraken_liquidity_proxies(
    tape: dict[str, Any],
    symbol: str,
    day: str,
) -> dict[str, Any]:
    """Kraken futures historical L2 absent in S3 — Roll + mark-asof proxies."""
    from ares_micro.book.spreads import effective_spread_bps, roll_implied_spread

    ts = np.asarray(tape["ts"], dtype=np.int64)
    px = np.asarray(tape["px"], dtype=np.float64)
    side = normalize_side(np.asarray(tape["side"], dtype=np.float64))
    u = normalize_underlying(symbol)
    out: dict[str, Any] = {
        "source": "kraken_proxy",
        "quoted_available": False,
        "reason": "kraken_futures_l2_absent_in_s3_archives_use_spot_or_ingest",
        "underlying": u,
    }
    ok_px = np.isfinite(px) & (px > 0)
    r = np.diff(np.log(px[ok_px]))
    roll = roll_implied_spread(r)
    mid_px = float(np.nanmedian(px[ok_px])) if ok_px.any() else float("nan")
    out["roll_spread_bps"] = (
        float(1e4 * roll / mid_px) if np.isfinite(roll) and mid_px > 0 else float("nan")
    )
    out["roll_raw"] = float(roll) if np.isfinite(roll) else float("nan")
    try:
        from startarb.data.marks import load_mark_ticks

        ensure_env()
        mts, mpx, src = load_mark_ticks(
            "kraken", venue_instrument(u, "kraken"), days=[day], max_files=16, quiet=True
        )
        mid = asof_join(ts, np.asarray(mts, dtype=np.int64), np.asarray(mpx, dtype=np.float64))
        es = effective_spread_bps(px, mid, side)
        out["eff_spread_bps_mean"] = float(np.nanmean(es)) if np.isfinite(es).any() else float("nan")
        out["eff_spread_n"] = int(np.isfinite(es).sum())
        out["mark_n"] = int(np.asarray(mts).size)
        out["mark_source"] = src
    except Exception as exc:  # noqa: BLE001
        out["eff_spread_error"] = f"{type(exc).__name__}: {exc}"
        out["eff_spread_bps_mean"] = float("nan")
    eff = out.get("eff_spread_bps_mean", float("nan"))
    roll_b = out["roll_spread_bps"]
    if np.isfinite(eff) and 0 < eff < 500:
        out["spread_bps_mean"] = float(eff)
        out["spread_kind"] = "effective_vs_mark"
    elif np.isfinite(roll_b):
        out["spread_bps_mean"] = float(roll_b)
        out["spread_kind"] = "roll"
    else:
        out["spread_bps_mean"] = float("nan")
        out["spread_kind"] = "none"
    out["ok"] = bool(np.isfinite(out["spread_bps_mean"]))
    return out


__all__ = [
    "collector_tob_days",
    "kraken_liquidity_proxies",
    "load_collector_tob",
    "load_hl_tob",
    "load_kraken_futures_tob_day",
    "load_kraken_futures_trade_synth_tob_day",
    "load_kraken_spot_tob_day",
    "load_tob_any",
    "load_tob_day",
    "load_venue_tob",
    "load_warehouse_tob",
    "_filter_tob_arrays",
]
