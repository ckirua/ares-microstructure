"""Shared realized-variance / log-return helpers for vol / continuous-path estimators."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def log_returns(log_px: NDArray[np.float64]) -> NDArray[np.float64]:
    """Δ log price; drops non-finite (shorter than input)."""
    x = np.asarray(log_px, dtype=np.float64)
    if x.size < 2:
        return np.asarray([], dtype=np.float64)
    r = np.diff(x)
    return r[np.isfinite(r)]


def realized_variance(returns: NDArray[np.float64]) -> float:
    """Sum of squared finite returns (RV)."""
    r = np.asarray(returns, dtype=np.float64)
    r = r[np.isfinite(r)]
    return float(np.sum(r * r)) if r.size else float("nan")
