"""Statistical helpers for cd_me Pass-2.5 info / feature dig.

Conjugate / bootstrap only (numpy + optional scipy). Mirrors filmonov
``_stats_bayes`` patterns without importing across books.
ClickHouse MCP banned.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

import numpy as np
from numpy.typing import NDArray

try:
    from scipy import stats as scipy_stats
except ImportError:  # pragma: no cover
    scipy_stats = None  # type: ignore


def univariate_moments(
    x: NDArray[np.floating],
    *,
    qs: Sequence[float] = (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99),
) -> dict[str, Any]:
    a = np.asarray(x, dtype=np.float64)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return {
            "n": 0,
            "mean": float("nan"),
            "std": float("nan"),
            "skew": float("nan"),
            "kurt": float("nan"),
            "quantiles": {},
        }
    if scipy_stats is not None and a.size >= 3:
        sk = float(scipy_stats.skew(a, bias=False))
        ku = float(scipy_stats.kurtosis(a, fisher=True, bias=False)) if a.size >= 4 else float("nan")
    else:
        m = float(np.mean(a))
        s = float(np.std(a, ddof=1)) if a.size > 1 else 0.0
        z = (a - m) / s if s > 0 else a * 0.0
        sk = float(np.mean(z**3)) if a.size >= 3 else float("nan")
        ku = float(np.mean(z**4) - 3.0) if a.size >= 4 else float("nan")
    qv = {f"q{int(q * 100):02d}": float(np.quantile(a, q)) for q in qs}
    return {
        "n": int(a.size),
        "mean": float(np.mean(a)),
        "std": float(np.std(a, ddof=1)) if a.size > 1 else 0.0,
        "skew": sk,
        "kurt": ku,
        "min": float(np.min(a)),
        "max": float(np.max(a)),
        "quantiles": qv,
    }


def tod_profile(
    hour_utc: NDArray[np.floating],
    values: NDArray[np.floating],
) -> dict[str, Any]:
    h = np.asarray(hour_utc, dtype=np.float64)
    v = np.asarray(values, dtype=np.float64)
    m = np.isfinite(h) & np.isfinite(v)
    h, v = h[m], v[m]
    hours = list(range(24))
    means: list[float] = []
    counts: list[int] = []
    for b in hours:
        sel = h.astype(np.int64) == int(b)
        counts.append(int(sel.sum()))
        means.append(float(np.mean(v[sel])) if sel.any() else float("nan"))
    return {"hours": hours, "means": means, "counts": counts}


def pearson_spearman(x: NDArray[np.floating], y: NDArray[np.floating]) -> dict[str, float]:
    a = np.asarray(x, dtype=np.float64)
    b = np.asarray(y, dtype=np.float64)
    m = np.isfinite(a) & np.isfinite(b)
    a, b = a[m], b[m]
    n = int(a.size)
    if n < 3:
        return {"n": float(n), "pearson": float("nan"), "spearman": float("nan")}
    pr = float(np.corrcoef(a, b)[0, 1])
    ra = a.argsort().argsort().astype(np.float64)
    rb = b.argsort().argsort().astype(np.float64)
    ra -= ra.mean()
    rb -= rb.mean()
    den = float(np.sqrt((ra * ra).sum() * (rb * rb).sum()))
    sr = float((ra * rb).sum() / den) if den > 0 else float("nan")
    return {"n": float(n), "pearson": pr, "spearman": sr}


def partial_corr(
    x: NDArray[np.floating],
    y: NDArray[np.floating],
    z: NDArray[np.floating],
) -> dict[str, float]:
    a = np.asarray(x, dtype=np.float64)
    b = np.asarray(y, dtype=np.float64)
    c = np.asarray(z, dtype=np.float64)
    m = np.isfinite(a) & np.isfinite(b) & np.isfinite(c)
    a, b, c = a[m], b[m], c[m]
    if a.size < 5:
        return {"n": float(a.size), "partial_r": float("nan")}
    Z = np.column_stack([np.ones(a.size), c])
    ra = a - Z @ np.linalg.lstsq(Z, a, rcond=None)[0]
    rb = b - Z @ np.linalg.lstsq(Z, b, rcond=None)[0]
    den = float(np.sqrt(np.sum(ra * ra) * np.sum(rb * rb)))
    r = float(np.sum(ra * rb) / den) if den > 0 else float("nan")
    return {"n": float(a.size), "partial_r": r}


def ols_incremental(
    y: NDArray[np.floating],
    X: NDArray[np.floating],
    *,
    names: Sequence[str] | None = None,
) -> dict[str, Any]:
    """OLS y ~ const + X columns; returns R², betas, residual std."""
    yy = np.asarray(y, dtype=np.float64).reshape(-1)
    xx = np.asarray(X, dtype=np.float64)
    if xx.ndim == 1:
        xx = xx.reshape(-1, 1)
    m = np.isfinite(yy) & np.isfinite(xx).all(axis=1)
    yy, xx = yy[m], xx[m]
    n, k = int(yy.size), int(xx.shape[1])
    colnames = list(names) if names is not None else [f"x{i}" for i in range(k)]
    if n < k + 3:
        return {
            "n": n,
            "r2": float("nan"),
            "betas": {c: float("nan") for c in ["const", *colnames]},
            "ok": False,
        }
    Z = np.column_stack([np.ones(n), xx])
    beta, _, _, _ = np.linalg.lstsq(Z, yy, rcond=None)
    resid = yy - Z @ beta
    ss_tot = float(((yy - yy.mean()) ** 2).sum())
    ss_res = float((resid**2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return {
        "n": n,
        "r2": float(r2),
        "betas": {name: float(b) for name, b in zip(["const", *colnames], beta)},
        "resid_std": float(np.std(resid, ddof=k + 1)) if n > k + 1 else float("nan"),
        "ok": True,
    }


def lead_lag_corr(
    x: NDArray[np.floating],
    y: NDArray[np.floating],
    *,
    lags: Sequence[int] = (-3, -2, -1, 0, 1, 2, 3),
) -> dict[str, Any]:
    """Hourly-series lead-lag Pearson corr; positive lag ⇒ y leads x by lag hours."""
    a = np.asarray(x, dtype=np.float64)
    b = np.asarray(y, dtype=np.float64)
    out_lags: list[int] = []
    out_corr: list[float] = []
    out_n: list[int] = []
    for lag in lags:
        if lag == 0:
            aa, bb = a, b
        elif lag > 0:
            aa, bb = a[lag:], b[:-lag]
        else:
            s = -lag
            aa, bb = a[:-s], b[s:]
        m = np.isfinite(aa) & np.isfinite(bb)
        n = int(m.sum())
        c = float(np.corrcoef(aa[m], bb[m])[0, 1]) if n >= 8 else float("nan")
        out_lags.append(int(lag))
        out_corr.append(c)
        out_n.append(n)
    best_i = int(np.nanargmax(np.abs(out_corr))) if any(np.isfinite(out_corr)) else 0
    return {
        "lags": out_lags,
        "corr": out_corr,
        "n": out_n,
        "best_lag": out_lags[best_i] if out_lags else None,
        "best_corr": out_corr[best_i] if out_corr else float("nan"),
    }


def day_block_bootstrap_corr(
    day_tags: NDArray[Any],
    x: NDArray[np.floating],
    y: NDArray[np.floating],
    *,
    n_boot: int = 400,
    alpha: float = 0.05,
    seed: int = 0,
    min_n: int = 10,
) -> dict[str, Any]:
    """Resample whole days; recompute pooled Pearson corr."""
    days = np.asarray(day_tags)
    a = np.asarray(x, dtype=np.float64)
    b = np.asarray(y, dtype=np.float64)
    m = np.isfinite(a) & np.isfinite(b)
    days, a, b = days[m], a[m], b[m]
    uniq = np.unique(days)
    if uniq.size < 2 or a.size < min_n:
        return {
            "ok": False,
            "n": int(a.size),
            "n_days": int(uniq.size),
            "corr": float("nan"),
            "ci_lo": float("nan"),
            "ci_hi": float("nan"),
        }
    point = float(np.corrcoef(a, b)[0, 1])
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot, dtype=np.float64)
    for i in range(n_boot):
        draw = rng.choice(uniq, size=uniq.size, replace=True)
        mask = np.isin(days, draw)
        # with replacement of days, include multiples by concatenating
        xs: list[np.ndarray] = []
        ys: list[np.ndarray] = []
        for d in draw:
            sel = days == d
            xs.append(a[sel])
            ys.append(b[sel])
        xx = np.concatenate(xs) if xs else np.zeros(0)
        yy = np.concatenate(ys) if ys else np.zeros(0)
        if xx.size < min_n:
            boots[i] = np.nan
            continue
        boots[i] = float(np.corrcoef(xx, yy)[0, 1])
    boots = boots[np.isfinite(boots)]
    if boots.size < max(20, n_boot // 5):
        return {
            "ok": True,
            "n": int(a.size),
            "n_days": int(uniq.size),
            "corr": point,
            "ci_lo": float("nan"),
            "ci_hi": float("nan"),
            "n_boot": int(boots.size),
            "label": "day_block_bootstrap",
        }
    lo, hi = np.quantile(boots, [alpha / 2, 1 - alpha / 2])
    return {
        "ok": True,
        "n": int(a.size),
        "n_days": int(uniq.size),
        "corr": point,
        "ci_lo": float(lo),
        "ci_hi": float(hi),
        "n_boot": int(boots.size),
        "label": "day_block_bootstrap",
    }


def day_block_bootstrap_stat(
    day_values: NDArray[np.floating],
    *,
    stat: Callable[[NDArray[np.float64]], float] = np.mean,
    n_boot: int = 400,
    alpha: float = 0.05,
    seed: int = 0,
) -> dict[str, float]:
    x = np.asarray(day_values, dtype=np.float64)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return {
            "n": 0,
            "point": float("nan"),
            "lo": float("nan"),
            "hi": float("nan"),
            "alpha": float(alpha),
            "n_boot": int(n_boot),
        }
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot, dtype=np.float64)
    n = x.size
    for i in range(n_boot):
        boots[i] = float(stat(x[rng.integers(0, n, size=n)]))
    lo, hi = np.quantile(boots, [alpha / 2, 1 - alpha / 2])
    return {
        "n": int(n),
        "point": float(stat(x)),
        "lo": float(lo),
        "hi": float(hi),
        "alpha": float(alpha),
        "n_boot": int(n_boot),
    }


def fisher_z_normal_posterior(
    r: float,
    n: int,
    *,
    prior_mean: float = 0.0,
    prior_prec: float = 0.0,
) -> dict[str, Any]:
    """Light Normal posterior on Fisher-z of a correlation (honest conjugate).

    Likelihood z ~ N(atanh(r), 1/(n-3)); optional Normal prior. Does **not**
    invent α — report posterior mean/CrI of r via tanh.
    """
    if not np.isfinite(r) or n < 5 or abs(r) >= 1.0:
        return {
            "ok": False,
            "r": float(r) if np.isfinite(r) else float("nan"),
            "n": int(n),
            "mean_r": float("nan"),
            "cri95": [float("nan"), float("nan")],
        }
    z_hat = float(np.arctanh(np.clip(r, -0.999999, 0.999999)))
    lik_prec = float(max(n - 3, 1))
    post_prec = prior_prec + lik_prec
    post_mean = (prior_prec * prior_mean + lik_prec * z_hat) / post_prec
    post_sd = float(1.0 / np.sqrt(post_prec))
    lo_z, hi_z = post_mean - 1.96 * post_sd, post_mean + 1.96 * post_sd
    return {
        "ok": True,
        "family": "fisher_z_normal",
        "r": float(r),
        "n": int(n),
        "z_hat": z_hat,
        "mean_z": float(post_mean),
        "sd_z": post_sd,
        "mean_r": float(np.tanh(post_mean)),
        "cri95": [float(np.tanh(lo_z)), float(np.tanh(hi_z))],
        "prior_prec": float(prior_prec),
    }


def pca_commonality(
    matrix: NDArray[np.floating],
    *,
    row_labels: Sequence[str] | None = None,
) -> dict[str, Any]:
    """PCA on rows×cols matrix (nan→col mean); return PC1 loadings + explained."""
    M = np.asarray(matrix, dtype=np.float64)
    if M.ndim != 2 or M.size == 0:
        return {"ok": False, "explained": [], "loadings": {}}
    col_mu = np.nanmean(M, axis=0)
    for j in range(M.shape[1]):
        bad = ~np.isfinite(M[:, j])
        M[bad, j] = col_mu[j] if np.isfinite(col_mu[j]) else 0.0
    X = M - M.mean(axis=0, keepdims=True)
    if X.shape[0] < 2 or X.shape[1] < 2:
        return {"ok": False, "explained": [], "loadings": {}}
    try:
        _, s, vt = np.linalg.svd(X, full_matrices=False)
    except np.linalg.LinAlgError:
        return {"ok": False, "explained": [], "loadings": {}}
    var = s**2
    explained = (var / var.sum()).tolist() if var.sum() > 0 else []
    labels = list(row_labels) if row_labels is not None else [str(i) for i in range(M.shape[0])]
    # loadings on rows via scores of first PC oriented
    scores = X @ vt[0]
    if scores.mean() < 0:
        scores = -scores
        vt = vt.copy()
        vt[0] = -vt[0]
    return {
        "ok": True,
        "explained": [float(e) for e in explained[:5]],
        "pc1_explained": float(explained[0]) if explained else float("nan"),
        "pc1_row_scores": {lab: float(sc) for lab, sc in zip(labels, scores)},
        "n_rows": int(M.shape[0]),
        "n_cols": int(M.shape[1]),
    }
