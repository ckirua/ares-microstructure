"""Shared loaders for empirical_mm experiments (collector TOB + warehouse trades)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

STARTARB = Path("/home/dev/srv/ares-startarb")
DEFAULT_TOB = STARTARB / "results" / "xarb_md" / "tob"
# Flat parquet (~≤2026-09-10) stores opaque HL instrument ids; catalog FNV(coin) misses.
# See startarb/config/symbols.yaml → hyperliquid_flat_ids.
HL_FLAT_IDS: dict[str, int] = {
    "BTC": 3860219501,
    "ETH": 3337431014,
}
HL_FLAT_CUTOFF = "2026-09-10"
LISTING_CACHE = Path.home() / ".cache" / "warehouse" / "listings"


def ensure_env() -> None:
    from startarb.env import ensure_env as _e

    _e()


def resolve_days(
    days: list[str] | None,
    venue: str = "hyperliquid",
    n: int = 3,
    *,
    prefer_listing_cache: bool = True,
) -> list[str]:
    if days:
        return days
    # Prefer local listing-cache days (avoids hanging S3 list_days).
    if prefer_listing_cache:
        bucket = {
            "hyperliquid": "mercat-hyperliquid-md",
            "deribit": "mercat-deribit-md",
            "kraken": "mercat-kraken-md",
            "lighter": "mercat-lighter-md",
            "extended": "mercat-extended-md",
            "risex": "mercat-risex-md",
        }.get(venue.strip().lower())
        if bucket:
            root = LISTING_CACHE / bucket
            if root.is_dir():
                cached = sorted(p.stem for p in root.glob("*.json"))
                if cached:
                    return cached[-n:] if n > 0 else cached
    from warehouse import list_days

    return list_days(venue)[-n:]


def hl_trade_instrument(symbol: str, day: str) -> str | int:
    """Opaque flat id for ≤FLAT_CUTOFF; catalog name thereafter."""
    sym = symbol.strip().upper()
    if day <= HL_FLAT_CUTOFF and sym in HL_FLAT_IDS:
        return HL_FLAT_IDS[sym]
    return sym


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
    from startarb.data.trades import load_trade_tape

    v = venue.strip().lower()
    if v != "hyperliquid" or not use_flat_ids or len(days) != 1:
        inst: str | int = symbol
        if v == "hyperliquid" and use_flat_ids and days:
            # multi-day: loader is per-call; callers should loop day-by-day for flat ids
            inst = symbol
        return load_trade_tape(
            v, inst, days=days, max_files=max_files, prefer_shards=prefer_shards, quiet=quiet
        )
    day = days[0]
    inst = hl_trade_instrument(symbol, day)
    return load_trade_tape(
        v, inst, days=[day], max_files=max_files, prefer_shards=prefer_shards, quiet=quiet
    )


def clip_tape_to_utc_day(tape: Any, day: str) -> dict[str, np.ndarray]:
    """Keep prints whose source_ts falls in [day, day+1) UTC.

    Flat-era warehouse objects often bleed across calendar days; clipping
    avoids double-counting when adjacent warehouse days are concatenated.
    Falls back to unclipped arrays if the UTC window is empty.
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
    }


def load_hl_tob(
    symbol: str,
    tob_root: Path = DEFAULT_TOB,
    *,
    max_rows: int = 400_000,
) -> dict[str, np.ndarray]:
    import pandas as pd
    import pyarrow.parquet as pq

    day_dirs = sorted(p for p in tob_root.iterdir() if p.is_dir())
    if not day_dirs:
        raise FileNotFoundError(tob_root)
    frames = []
    for d in day_dirs[-2:]:
        for f in sorted(d.glob("tob_*.parquet")):
            t = pq.read_table(
                f, columns=["ts", "venue", "symbol", "bid", "ask", "bid_sz", "ask_sz"]
            ).to_pandas()
            frames.append(t)
    df = pd.concat(frames, ignore_index=True)
    df = df[(df["venue"] == "hyperliquid") & (df["symbol"].astype(str).str.upper() == symbol.upper())]
    df = df.sort_values("ts")
    if len(df) > max_rows:
        df = df.iloc[:: max(1, len(df) // max_rows)]
    bid = df["bid"].to_numpy(np.float64)
    ask = df["ask"].to_numpy(np.float64)
    return {
        "ts": df["ts"].to_numpy(np.int64),
        "bid": bid,
        "ask": ask,
        "bid_sz": df["bid_sz"].to_numpy(np.float64),
        "ask_sz": df["ask_sz"].to_numpy(np.float64),
        "mid": 0.5 * (bid + ask),
        "depth": df["bid_sz"].to_numpy(np.float64) + df["ask_sz"].to_numpy(np.float64),
    }


def load_venue_tob(
    venue: str,
    symbol: str,
    tob_root: Path = DEFAULT_TOB,
    *,
    max_rows: int = 300_000,
) -> dict[str, np.ndarray]:
    import pandas as pd
    import pyarrow.parquet as pq

    day_dirs = sorted(p for p in tob_root.iterdir() if p.is_dir())
    frames = []
    for d in day_dirs[-2:]:
        for f in sorted(d.glob("tob_*.parquet")):
            t = pq.read_table(
                f, columns=["ts", "venue", "symbol", "bid", "ask", "bid_sz", "ask_sz"]
            ).to_pandas()
            frames.append(t)
    df = pd.concat(frames, ignore_index=True)
    df = df[(df["venue"] == venue) & (df["symbol"].astype(str).str.upper() == symbol.upper())]
    df = df.sort_values("ts")
    if len(df) > max_rows:
        df = df.iloc[:: max(1, len(df) // max_rows)]
    if df.empty:
        raise RuntimeError(f"no TOB for {venue}/{symbol}")
    bid = df["bid"].to_numpy(np.float64)
    ask = df["ask"].to_numpy(np.float64)
    return {
        "ts": df["ts"].to_numpy(np.int64),
        "bid": bid,
        "ask": ask,
        "mid": 0.5 * (bid + ask),
        "bid_sz": df["bid_sz"].to_numpy(np.float64),
        "ask_sz": df["ask_sz"].to_numpy(np.float64),
    }


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


def align_mids_calendar(
    a: dict[str, np.ndarray],
    b: dict[str, np.ndarray],
    *,
    bar_ns: int = 1_000_000_000,
) -> tuple[np.ndarray, np.ndarray]:
    """Last mid on common calendar grid for two venues."""
    t0 = int(max(a["ts"].min(), b["ts"].min()))
    t1 = int(min(a["ts"].max(), b["ts"].max()))
    grid = np.arange(t0, t1 + 1, bar_ns, dtype=np.int64)
    ia = np.searchsorted(a["ts"], grid, side="right") - 1
    ib = np.searchsorted(b["ts"], grid, side="right") - 1
    ma = np.full(grid.shape, np.nan)
    mb = np.full(grid.shape, np.nan)
    oka = (ia >= 0) & (ia < a["ts"].size)
    okb = (ib >= 0) & (ib < b["ts"].size)
    ma[oka] = a["mid"][ia[oka]]
    mb[okb] = b["mid"][ib[okb]]
    m = np.isfinite(ma) & np.isfinite(mb)
    return ma[m], mb[m]


def load_hl_l2_levels(
    symbol: str = "ETH",
    *,
    max_files: int = 80,
    cache_glob: str | None = None,
) -> dict[str, np.ndarray]:
    """Load multilevel HL ``l2_snapshot_level`` rows (depth > L0).

    Prefer local warehouse object cache (fast). Falls back to empty arrays if
    no matching instrument rows. Ask levels on HL are encoded 20..39
    (offset 20 from bid 0..19) — callers should pass that to Sandas helpers.
    """
    import glob

    import pyarrow as pa
    import pyarrow.parquet as pq

    from startarb.data.instruments import instrument_id

    iid = int(instrument_id("hyperliquid", symbol))
    pattern = cache_glob or str(
        Path.home() / ".cache/warehouse/objects/mercat-hyperliquid-md/**/*l2_snapshot_level*"
    )
    files = sorted(glob.glob(pattern, recursive=True))
    if not files:
        z = np.zeros(0, dtype=np.int64)
        e = np.zeros(0, dtype=np.float64)
        return {
            "ts": z,
            "side": z,
            "level": z,
            "qty": e,
            "price_ticks": z,
            "snapshot_id": z,
            "instrument_id": z,
            "n_files": 0,
            "instrument_id_target": iid,
        }
    # stride across cache for coverage without huge RAM
    step = max(1, len(files) // max_files)
    chosen = files[::step][:max_files]
    tables = []
    cols = [
        "source_ts_ns",
        "instrument_id",
        "snapshot_id",
        "side",
        "level",
        "price_ticks",
        "md_qty_lots",
    ]
    for f in chosen:
        try:
            tables.append(pq.read_table(f, columns=cols))
        except Exception:
            continue
    if not tables:
        z = np.zeros(0, dtype=np.int64)
        e = np.zeros(0, dtype=np.float64)
        return {
            "ts": z,
            "side": z,
            "level": z,
            "qty": e,
            "price_ticks": z,
            "snapshot_id": z,
            "instrument_id": z,
            "n_files": 0,
            "instrument_id_target": iid,
        }
    df = pa.concat_tables(tables).to_pandas()
    sub = df[df["instrument_id"] == iid]
    if sub.empty:
        # opaque / flat-id mismatch: take busiest instrument in sample
        iid2 = int(df["instrument_id"].value_counts().index[0])
        sub = df[df["instrument_id"] == iid2]
        iid = iid2
    return {
        "ts": sub["source_ts_ns"].to_numpy(np.int64),
        "side": sub["side"].to_numpy(np.int64),
        "level": sub["level"].to_numpy(np.int64),
        "qty": sub["md_qty_lots"].to_numpy(np.float64),
        "price_ticks": sub["price_ticks"].to_numpy(np.int64),
        "snapshot_id": sub["snapshot_id"].to_numpy(np.int64),
        "instrument_id": sub["instrument_id"].to_numpy(np.int64),
        "n_files": int(len(chosen)),
        "instrument_id_target": int(iid),
    }


def overlap_trades_with_mids(
    tape: Any,
    tob: dict[str, np.ndarray],
) -> dict[str, np.ndarray]:
    ts = np.asarray(tape.ts_ns, dtype=np.int64)
    px = np.asarray(tape.price, dtype=np.float64)
    qty = np.asarray(tape.qty_coin, dtype=np.float64)
    side = normalize_side(tape.side)
    m0, m1 = int(tob["ts"].min()), int(tob["ts"].max())
    in_win = (ts >= m0) & (ts <= m1)
    if int(in_win.sum()) < 200:
        # keep all trades; mids may still asof outside
        in_win = np.ones(ts.shape, dtype=bool)
    return {
        "ts": ts[in_win],
        "px": px[in_win],
        "qty": qty[in_win],
        "side": side[in_win],
        "notional": px[in_win] * qty[in_win],
        "mid0": asof_mid(ts[in_win], tob["ts"], tob["mid"]),
    }
