"""Statistical hygiene: bootstrap CIs, rank corr, time splits."""

from __future__ import annotations

from typing import Any, Callable

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
    n = arr.size
    idx = rng.integers(0, n, size=(n_boot, n))
    samples = arr[idx]
    # Fast path for common ufuncs; generic callables stay row-wise.
    if stat is np.mean or getattr(stat, "__name__", "") == "mean":
        boots = samples.mean(axis=1)
    elif stat is np.median or getattr(stat, "__name__", "") == "median":
        boots = np.median(samples, axis=1)
    else:
        boots = np.empty(n_boot, dtype=np.float64)
        for i in range(n_boot):
            boots[i] = float(stat(samples[i]))
    lo, hi = np.quantile(boots, [alpha / 2, 1 - alpha / 2])
    return {
        "n": int(n),
        "point": float(stat(arr)),
        "lo": float(lo),
        "hi": float(hi),
        "alpha": float(alpha),
        "n_boot": int(n_boot),
    }


def pearson_r(x: NDArray[np.float64], y: NDArray[np.float64]) -> float:
    """Pearson correlation (pairwise complete); NaN if <3 points."""
    a = np.asarray(x, dtype=np.float64)
    b = np.asarray(y, dtype=np.float64)
    m = np.isfinite(a) & np.isfinite(b)
    a, b = a[m], b[m]
    if a.size < 3:
        return float("nan")
    a0, b0 = a - a.mean(), b - b.mean()
    den = float(np.sqrt((a0 * a0).sum() * (b0 * b0).sum()))
    return float((a0 * b0).sum() / den) if den > 0 else float("nan")


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

    n = a.size
    point = pearson_r(a, b)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    xx = a[idx] - a[idx].mean(axis=1, keepdims=True)
    yy = b[idx] - b[idx].mean(axis=1, keepdims=True)
    den = np.sqrt((xx * xx).sum(axis=1) * (yy * yy).sum(axis=1))
    num = (xx * yy).sum(axis=1)
    boots = np.where(den > 0, num / den, np.nan)
    finite = boots[np.isfinite(boots)]
    if finite.size == 0:
        return {"n": int(n), "r": float(point), "lo": float("nan"), "hi": float("nan"), "alpha": float(alpha)}
    lo, hi = np.quantile(finite, [alpha / 2, 1 - alpha / 2])
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


def nw_ols(
    y: NDArray[np.float64],
    X: NDArray[np.float64],
    *,
    add_const: bool = True,
    lags: int | None = None,
) -> dict[str, Any]:
    r"""OLS with Newey–West (HAC) standard errors.

    ``X`` is n×k (no constant unless ``add_const``). Returns β, NW se, t-stats,
    R². Lag default: Andrews-ish \(L=\lfloor 4(n/100)^{2/9}\rfloor\).
    """
    yy = np.asarray(y, dtype=np.float64).reshape(-1)
    xx = np.asarray(X, dtype=np.float64)
    if xx.ndim == 1:
        xx = xx.reshape(-1, 1)
    m = np.isfinite(yy) & np.isfinite(xx).all(axis=1)
    yy, xx = yy[m], xx[m]
    n = int(yy.size)
    if n < xx.shape[1] + 3:
        return {
            "n": n,
            "beta": np.full(xx.shape[1] + int(add_const), np.nan),
            "se": np.full(xx.shape[1] + int(add_const), np.nan),
            "t": np.full(xx.shape[1] + int(add_const), np.nan),
            "r2": float("nan"),
            "lags": 0,
        }
    if add_const:
        xx = np.column_stack([np.ones(n), xx])
    k = xx.shape[1]
    # OLS
    try:
        beta, _, _, _ = np.linalg.lstsq(xx, yy, rcond=None)
    except np.linalg.LinAlgError:
        return {
            "n": n,
            "beta": np.full(k, np.nan),
            "se": np.full(k, np.nan),
            "t": np.full(k, np.nan),
            "r2": float("nan"),
            "lags": 0,
        }
    resid = yy - xx @ beta
    ss_tot = float(((yy - yy.mean()) ** 2).sum())
    ss_res = float((resid ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    if lags is None:
        lags = max(0, int(np.floor(4.0 * (n / 100.0) ** (2.0 / 9.0))))
    # Newey–West S = Γ0 + Σ_ℓ w_ℓ (Γℓ + Γℓ')
    uX = resid[:, None] * xx  # n×k score
    gamma0 = (uX.T @ uX) / n
    S = gamma0.copy()
    for ell in range(1, int(lags) + 1):
        w = 1.0 - ell / (lags + 1.0)
        g = (uX[ell:].T @ uX[:-ell]) / n
        S += w * (g + g.T)
    try:
        xtx_inv = np.linalg.inv(xx.T @ xx / n)
        cov = xtx_inv @ S @ xtx_inv / n
        se = np.sqrt(np.maximum(np.diag(cov), 0.0))
    except np.linalg.LinAlgError:
        se = np.full(k, np.nan)
    tstat = np.where(se > 0, beta / se, np.nan)
    return {
        "n": n,
        "beta": beta.astype(np.float64),
        "se": se.astype(np.float64),
        "t": tstat.astype(np.float64),
        "r2": float(r2),
        "lags": int(lags),
        "add_const": bool(add_const),
    }
