"""Fragmentation Efficiency Index and Shannon entropy (Lehalle & Laruelle A.1)."""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray


def entropy(q: NDArray[np.float64] | list[float]) -> float:
    """Shannon entropy H = -∑ q log q (nats). Convention: 0·log0 = 0."""
    arr = np.asarray(q, dtype=np.float64)
    arr = arr[arr > 0]
    if arr.size == 0:
        return 0.0
    return float(-np.sum(arr * np.log(arr)))


def fei(q: NDArray[np.float64] | list[float], *, n_pools: int | None = None) -> float:
    """Fragmentation Efficiency Index F = H(q) / log(N).

    Parameters
    ----------
    q:
        Non-negative weights (size, notional, or update counts). Renormalized
        to a probability vector before entropy.
    n_pools:
        If set, use this N even when some weights are zero (book convention for
        fixed venue universe). Else N = count of strictly positive shares.

    Returns
    -------
    float
        In [0, 1] for equal-share → 1 when ``n_pools`` matches support.
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
