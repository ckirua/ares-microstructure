"""Statistical hygiene: bootstrap CIs, rank corr, time splits."""

from __future__ import annotations

from typing import Callable

import numpy as np
from numpy.typing import NDArray


def bootstrap_ci(
    x: NDArray[np.float64],
    stat: Callable[[NDArray[np.float64]], float] = np.mean,
    *,
    n_boot: int = 1000,
    alpha: float = 0.05,
    seed: int = 0,
) -> dict[str, float]:
    """Percentile bootstrap CI for a scalar statistic of 1-D sample ``x``.

    Multiple-testing honesty: report family size N when scanning many Promotes;
    do not claim discovery from unadjusted α alone.
    """
    arr = np.asarray(x, dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return {"n": 0, "point": float("nan"), "lo": float("nan"), "hi": float("nan")}
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot, dtype=np.float64)
    n = arr.size
    for i in range(n_boot):
        sample = arr[rng.integers(0, n, size=n)]
        boots[i] = float(stat(sample))
    lo, hi = np.quantile(boots, [alpha / 2, 1 - alpha / 2])
    return {
        "n": int(n),
        "point": float(stat(arr)),
        "lo": float(lo),
        "hi": float(hi),
        "alpha": float(alpha),
        "n_boot": int(n_boot),
    }


def spearman_r(x: NDArray[np.float64], y: NDArray[np.float64]) -> float:
    """Spearman rank correlation (no SciPy dependency)."""
    a = np.asarray(x, dtype=np.float64)
    b = np.asarray(y, dtype=np.float64)
    m = np.isfinite(a) & np.isfinite(b)
    a, b = a[m], b[m]
    if a.size < 3:
        return float("nan")
    ra = a.argsort().argsort().astype(np.float64)
    rb = b.argsort().argsort().astype(np.float64)
    ra -= ra.mean()
    rb -= rb.mean()
    den = float(np.sqrt((ra * ra).sum() * (rb * rb).sum()))
    if den <= 0:
        return float("nan")
    return float((ra * rb).sum() / den)


def pearson_r_ci(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    *,
    n_boot: int = 1000,
    alpha: float = 0.05,
    seed: int = 0,
) -> dict[str, float]:
    """Pearson r with bootstrap CI (pairwise complete)."""
    a = np.asarray(x, dtype=np.float64)
    b = np.asarray(y, dtype=np.float64)
    m = np.isfinite(a) & np.isfinite(b)
    a, b = a[m], b[m]
    if a.size < 3:
        return {"n": int(a.size), "r": float("nan"), "lo": float("nan"), "hi": float("nan")}

    def _r(idx: NDArray[np.int64]) -> float:
        xx, yy = a[idx], b[idx]
        xx = xx - xx.mean()
        yy = yy - yy.mean()
        den = float(np.sqrt((xx * xx).sum() * (yy * yy).sum()))
        return float((xx * yy).sum() / den) if den > 0 else float("nan")

    n = a.size
    point = _r(np.arange(n))
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot, dtype=np.float64)
    for i in range(n_boot):
        boots[i] = _r(rng.integers(0, n, size=n))
    lo, hi = np.quantile(boots[np.isfinite(boots)], [alpha / 2, 1 - alpha / 2])
    return {"n": int(n), "r": float(point), "lo": float(lo), "hi": float(hi), "alpha": float(alpha)}


def time_split_mask(
    ts_ns: NDArray[np.int64],
    *,
    train_frac: float = 0.7,
) -> tuple[NDArray[np.bool_], NDArray[np.bool_]]:
    """Chronological train/test split by timestamp quantile (no shuffle).

    Falsifier for non-stationary Promotes: train metric outside test CI → Kill/Hold.
    """
    t = np.asarray(ts_ns, dtype=np.int64)
    if t.size == 0:
        empty = np.zeros(0, dtype=bool)
        return empty, empty
    cut = np.quantile(t.astype(np.float64), train_frac)
    train = t <= int(cut)
    test = ~train
    return train, test
