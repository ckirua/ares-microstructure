"""Shared microstructure research helpers (FEI, etc.)."""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray


def entropy(q: NDArray[np.float64] | list[float]) -> float:
    """Shannon entropy H = -sum q log q (nats). Convention: 0*log0 = 0."""
    arr = np.asarray(q, dtype=np.float64)
    arr = arr[arr > 0]
    if arr.size == 0:
        return 0.0
    return float(-np.sum(arr * np.log(arr)))


def fei(q: NDArray[np.float64] | list[float], *, n_pools: int | None = None) -> float:
    """Fragmentation Efficiency Index F = H(q) / log(N) (Lehalle & Laruelle A.1).

    If ``n_pools`` is None, N = count of strictly positive weights after
    renormalization (matches equal-share → 1.0).
    """
    arr = np.asarray(q, dtype=np.float64)
    s = float(arr.sum())
    if s <= 0:
        return 0.0
    arr = arr / s
    n = int(n_pools) if n_pools is not None else int((arr > 0).sum())
    if n <= 1:
        return 0.0
    return entropy(arr) / math.log(n)
