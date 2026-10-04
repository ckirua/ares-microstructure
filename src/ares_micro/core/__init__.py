"""Generic array / RV helpers shared by book, flow, and vol."""

from __future__ import annotations

from ares_micro.core.arrays import (
    asof_idx,
    asof_join,
    consecutive_log_returns,
    day_bounds_ns,
    forward_fill,
    interval_overlap,
    log_returns_on_grid,
    normalize_side,
)
from ares_micro.core.constants import NS_PER_MS, NS_PER_S
from ares_micro.core.rv import log_returns, realized_variance

__all__ = [
    "NS_PER_MS",
    "NS_PER_S",
    "asof_idx",
    "asof_join",
    "consecutive_log_returns",
    "day_bounds_ns",
    "forward_fill",
    "interval_overlap",
    "log_returns",
    "log_returns_on_grid",
    "normalize_side",
    "realized_variance",
]
