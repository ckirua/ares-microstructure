"""Day-level VPIN feature helper (uses proprietary trade loaders)."""

from __future__ import annotations

from typing import Any

import numpy as np

from ares_micro.core.arrays import normalize_side
from ares_micro.flow.vpin import (
    resolve_bucket_volume,
    rolling_vpin_series,
    vpin_bucket,
)
from research.md.trades import load_day_trades


def vpin_day_features(
    venue: str,
    symbol: str,
    day: str,
    *,
    max_files: int = 24,
    n_buckets_window: int = 50,
    bucket_scale: float = 50.0,
    target_buckets: float | None = None,
) -> dict[str, Any]:
    """One UTC day → completeness + ``vpin_bucket`` summary + rolling path meta."""
    rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
    tape = rec["tape"]
    side = normalize_side(np.asarray(tape["side"], dtype=np.float64))
    qty = np.asarray(tape["qty"], dtype=np.float64)
    ts = np.asarray(tape["ts"], dtype=np.int64)
    bucket_v, bucket_method = resolve_bucket_volume(
        qty, bucket_scale=bucket_scale, target_buckets=target_buckets
    )
    summary = vpin_bucket(
        side, qty, bucket_volume=bucket_v, n_buckets_window=n_buckets_window
    )
    v_ts, v_roll = rolling_vpin_series(
        side, qty, ts, bucket_volume=bucket_v, n_buckets_window=n_buckets_window
    )
    return {
        **rec,
        "bucket_volume": bucket_v,
        "bucket_method": bucket_method,
        "vpin_summary": summary,
        "vpin_path_n": int(v_roll.size),
        "vpin_path_finite": int(np.isfinite(v_roll).sum()),
        "vpin_path_last": float(v_roll[-1]) if v_roll.size and np.isfinite(v_roll[-1]) else float("nan"),
        "vpin_ts": v_ts,
        "vpin_roll": v_roll,
    }


__all__ = ["vpin_day_features"]
