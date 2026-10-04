"""Thin re-export of ``research.md`` plus empirical_mm-only helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from research.md import *  # noqa: F403
from research.md import __all__ as _DATA_ALL


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


__all__ = list(_DATA_ALL) + ["align_mids_calendar", "load_hl_l2_levels"]
