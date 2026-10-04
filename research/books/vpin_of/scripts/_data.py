"""Thin re-export of ``research.md`` + VPIN helpers for vpin_of."""

from __future__ import annotations

from pathlib import Path

from ares_micro.flow.vpin import (
    default_bucket_volume,
    resolve_bucket_volume,
    rolling_vpin_series,
)
from research.md import *  # noqa: F403
from research.md import __all__ as _DATA_ALL

# Book-local Kraken futures TOB ingest cache (overrides lib default).
KRAKEN_FUT_TOB = Path(__file__).resolve().parents[1] / "out" / "kraken_futures_tob"

__all__ = list(_DATA_ALL) + [
    "KRAKEN_FUT_TOB",
    "default_bucket_volume",
    "resolve_bucket_volume",
    "rolling_vpin_series",
]
