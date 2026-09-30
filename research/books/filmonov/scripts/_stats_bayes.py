"""Statistical + Bayesian helpers for Filimonov desk research.

Conjugate / Laplace approximations only (scipy+numpy) — no pymc/numpyro.
Used by ``exp_feature_stats.py`` and ``exp_bayes_layer.py``.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

import numpy as np
from numpy.typing import NDArray
from scipy import stats


# ---------------------------------------------------------------------------
# Univariate / dependence (frequentist hygiene)
# ---------------------------------------------------------------------------


def univariate_moments(x: NDArray[np.floating], *, qs: Sequence[float] = (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)) -> dict[str, Any]:
    """Moments + tail quantiles for a 1-D sample (finite only)."""
    a = np.asarray(x, dtype=np.float64)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return {"n": 0, "mean": float("nan"), "std": float("nan"), "skew": float("nan"), "kurt": float("nan"), "quantiles": {}}
    sk = float(stats.skew(a, bias=False)) if a.size >= 3 else float("nan")
    ku = float(stats.kurtosis(a, fisher=True, bias=False)) if a.size >= 4 else float("nan")
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


def tod_seasonality(
    ts_ns: NDArray[np.int64],
    values: NDArray[np.floating] | None = None,
    *,
    bin_hours: float = 1.0,
) -> dict[str, Any]:
    """UTC hour-of-day counts (or mean of values) for event timestamps."""
    t = np.asarray(ts_ns, dtype=np.int64)
    if t.size == 0:
        return {"bin_hours": float(bin_hours), "hours": [], "counts": [], "means": []}
    hour = ((t // 1_000_000_000) % 86_400) / 3600.0
    n_bins = max(1, int(round(24.0 / float(bin_hours))))
    edges = np.linspace(0.0, 24.0, n_bins + 1)
    centers = 0.5 * (edges[:-1] + edges[1:])
    idx = np.clip(np.searchsorted(edges, hour, side="right") - 1, 0, n_bins - 1)
    counts = np.bincount(idx, minlength=n_bins).astype(np.float64)
    means: list[float] = []
    if values is not None:
        v = np.asarray(values, dtype=np.float64)
        for b in range(n_bins):
            m = idx == b
            means.append(float(np.nanmean(v[m])) if m.any() else float("nan"))
    else:
        means = [float("nan")] * n_bins
    return {
        "bin_hours": float(bin_hours),
        "hours": centers.tolist(),
        "counts": counts.tolist(),
        "means": means,
    }


def pearson_spearman(x: NDArray[np.floating], y: NDArray[np.floating]) -> dict[str, float]:
    a = np.asarray(x, dtype=np.float64)
    b = np.asarray(y, dtype=np.float64)
    m = np.isfinite(a) & np.isfinite(b)
    a, b = a[m], b[m]
    if a.size < 3:
        return {"n": float(a.size), "pearson": float("nan"), "spearman": float("nan")}
    pr = float(stats.pearsonr(a, b).statistic)
    sr = float(stats.spearmanr(a, b).statistic)
    return {"n": float(a.size), "pearson": pr, "spearman": sr}


def partial_corr(
    x: NDArray[np.floating],
    y: NDArray[np.floating],
    z: NDArray[np.floating],
) -> dict[str, float]:
    """Partial correlation of x,y controlling for z (OLS residual corr)."""
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


def mutual_info_binned(
    x: NDArray[np.floating],
    y: NDArray[np.floating],
    *,
    n_bins: int = 8,
) -> dict[str, float]:
    """Histogram MI (nats). Stable only for n ≳ n_bins²; else NaN."""
    a = np.asarray(x, dtype=np.float64)
    b = np.asarray(y, dtype=np.float64)
    m = np.isfinite(a) & np.isfinite(b)
    a, b = a[m], b[m]
    min_n = int(n_bins * n_bins)
    if a.size < max(min_n, 20):
        return {"n": float(a.size), "mi_nats": float("nan"), "n_bins": float(n_bins), "stable": 0.0}
    # equal-frequency bins via rank quantiles
    qa = np.unique(np.quantile(a, np.linspace(0, 1, n_bins + 1)))
    qb = np.unique(np.quantile(b, np.linspace(0, 1, n_bins + 1)))
    if qa.size < 3 or qb.size < 3:
        return {"n": float(a.size), "mi_nats": float("nan"), "n_bins": float(n_bins), "stable": 0.0}
    ia = np.clip(np.searchsorted(qa, a, side="right") - 1, 0, qa.size - 2)
    ib = np.clip(np.searchsorted(qb, b, side="right") - 1, 0, qb.size - 2)
    nx, ny = qa.size - 1, qb.size - 1
    joint = np.zeros((nx, ny), dtype=np.float64)
    for i, j in zip(ia, ib):
        joint[i, j] += 1.0
    joint /= joint.sum()
    px = joint.sum(axis=1, keepdims=True)
    py = joint.sum(axis=0, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = joint / (px @ py)
        term = np.where((joint > 0) & np.isfinite(ratio) & (ratio > 0), joint * np.log(ratio), 0.0)
    return {"n": float(a.size), "mi_nats": float(term.sum()), "n_bins": float(n_bins), "stable": 1.0}


def lead_lag_crosscorr(
    ts_a: NDArray[np.int64],
    ts_b: NDArray[np.int64],
    *,
    lags_ms: Sequence[float] = (-2000.0, -1000.0, -500.0, -250.0, 0.0, 250.0, 500.0, 1000.0, 2000.0),
    bar_ms: float = 250.0,
) -> dict[str, Any]:
    """Bar-count cross-correlation of two event streams at lag grid (ms)."""
    a = np.asarray(ts_a, dtype=np.int64)
    b = np.asarray(ts_b, dtype=np.int64)
    lags = [float(x) for x in lags_ms]
    if a.size < 2 or b.size < 2:
        return {"lags_ms": lags, "corr": [float("nan")] * len(lags), "n_bars": 0}
    t0 = int(min(a.min(), b.min()))
    t1 = int(max(a.max(), b.max()))
    bar_ns = int(float(bar_ms) * 1_000_000)
    n_bars = max(1, int((t1 - t0) // bar_ns) + 1)
    if n_bars > 50_000:
        # coarsen to keep O(n) reasonable
        bar_ns = max(bar_ns, int((t1 - t0) // 20_000) + 1)
        n_bars = max(1, int((t1 - t0) // bar_ns) + 1)
    ca = np.zeros(n_bars, dtype=np.float64)
    cb = np.zeros(n_bars, dtype=np.float64)
    for t in a:
        i = int((int(t) - t0) // bar_ns)
        if 0 <= i < n_bars:
            ca[i] += 1.0
    for t in b:
        i = int((int(t) - t0) // bar_ns)
        if 0 <= i < n_bars:
            cb[i] += 1.0
    ca = ca - ca.mean()
    cb = cb - cb.mean()
    den = float(np.sqrt(np.sum(ca * ca) * np.sum(cb * cb)))
    out: list[float] = []
    for lag in lags:
        shift = int(round(lag / float(bar_ms)))
        if shift == 0:
            num = float(np.sum(ca * cb))
        elif shift > 0:
            num = float(np.sum(ca[:-shift] * cb[shift:])) if shift < n_bars else float("nan")
        else:
            s = -shift
            num = float(np.sum(ca[s:] * cb[:-s])) if s < n_bars else float("nan")
        out.append(float(num / den) if den > 0 and np.isfinite(num) else float("nan"))
    return {"lags_ms": lags, "corr": out, "n_bars": int(n_bars), "bar_ms": float(bar_ms)}


def day_block_bootstrap_ci(
    day_values: NDArray[np.floating],
    *,
    stat: Callable[[NDArray[np.float64]], float] = np.mean,
    n_boot: int = 500,
    alpha: float = 0.05,
    seed: int = 0,
) -> dict[str, float]:
    """Bootstrap over day blocks (resample days with replacement)."""
    x = np.asarray(day_values, dtype=np.float64)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return {"n": 0, "point": float("nan"), "lo": float("nan"), "hi": float("nan"), "alpha": float(alpha), "n_boot": int(n_boot)}
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


def bh_fdr(p_values: Sequence[float], *, alpha: float = 0.05) -> dict[str, Any]:
    """Benjamini–Hochberg FDR control. Returns reject mask + adjusted p."""
    p = np.asarray(p_values, dtype=np.float64)
    m = int(p.size)
    if m == 0:
        return {"alpha": float(alpha), "reject": [], "p_adj": [], "n": 0}
    order = np.argsort(p)
    ranked = p[order]
    adj = np.empty(m, dtype=np.float64)
    prev = 1.0
    for i in range(m - 1, -1, -1):
        rank = i + 1
        val = min(prev, ranked[i] * m / rank)
        adj[i] = val
        prev = val
    p_adj = np.empty(m, dtype=np.float64)
    p_adj[order] = adj
    reject = (p_adj <= alpha).tolist()
    return {"alpha": float(alpha), "reject": reject, "p_adj": p_adj.tolist(), "n": m, "p_raw": p.tolist()}


def two_sided_p_from_ci(point: float, lo: float, hi: float) -> float:
    """Crude two-sided p proxy from percentile CI: 0 if 0∉CI else ~1."""
    if not np.isfinite(point) or not np.isfinite(lo) or not np.isfinite(hi):
        return float("nan")
    if lo > 0 or hi < 0:
        # distance outside in CI half-width units → small p
        half = 0.5 * (hi - lo)
        if half <= 0:
            return 0.001
        dist = abs(point) / half
        return float(max(0.001, min(0.2, 2.0 * (1.0 - stats.norm.cdf(dist)))))
    # 0 inside CI
    half = 0.5 * (hi - lo)
    if half <= 0:
        return 1.0
    dist = abs(point) / half
    return float(max(0.2, min(1.0, 2.0 * (1.0 - stats.norm.cdf(dist)))))


# ---------------------------------------------------------------------------
# Conjugate Bayesian layer
# ---------------------------------------------------------------------------


def beta_binomial_posterior(
    successes: int | float,
    trials: int | float,
    *,
    a0: float = 1.0,
    b0: float = 1.0,
) -> dict[str, Any]:
    """Beta-Binomial conjugate posterior for a rate/probability."""
    s = float(successes)
    n = float(trials)
    a = a0 + s
    b = b0 + max(0.0, n - s)
    dist = stats.beta(a, b)
    mean = float(dist.mean())
    lo, hi = [float(x) for x in dist.ppf([0.025, 0.975])]
    return {
        "family": "beta_binomial",
        "a0": float(a0),
        "b0": float(b0),
        "a": float(a),
        "b": float(b),
        "n_success": s,
        "n_trials": n,
        "mean": mean,
        "median": float(dist.median()),
        "mode": float((a - 1) / (a + b - 2)) if a > 1 and b > 1 else float("nan"),
        "cri95": [lo, hi],
        "var": float(dist.var()),
    }


def poisson_gamma_posterior(
    count: int | float,
    exposure: float,
    *,
    a0: float = 1.0,
    b0: float = 1.0,
) -> dict[str, Any]:
    """Poisson-Gamma conjugate for rate λ (events per unit exposure).

    Prior λ ~ Gamma(a0, rate=b0); after count k in exposure E:
    posterior Gamma(a0+k, rate=b0+E). Mean = a/b.
    """
    k = float(count)
    e = max(float(exposure), 1e-12)
    a = a0 + k
    b = b0 + e
    dist = stats.gamma(a=a, scale=1.0 / b)
    mean = float(dist.mean())
    lo, hi = [float(x) for x in dist.ppf([0.025, 0.975])]
    return {
        "family": "poisson_gamma",
        "a0": float(a0),
        "b0": float(b0),
        "a": float(a),
        "b": float(b),
        "count": k,
        "exposure": e,
        "mean": mean,
        "median": float(dist.median()),
        "cri95": [lo, hi],
        "var": float(dist.var()),
    }


def hierarchical_beta_shrinkage(
    successes: Sequence[float],
    trials: Sequence[float],
    labels: Sequence[str] | None = None,
    *,
    a0: float = 1.0,
    b0: float = 1.0,
) -> dict[str, Any]:
    """Empirical-Bayes hierarchical Beta: shared (α,β) via moment matching.

    Group means → method-of-moments hyperparams; then per-group posteriors
    shrink toward the grand mean. Desk: venue/day fade P or adverse rates.
    """
    s = np.asarray(successes, dtype=np.float64)
    n = np.asarray(trials, dtype=np.float64)
    labs = list(labels) if labels is not None else [f"g{i}" for i in range(len(s))]
    m = (n > 0) & np.isfinite(s) & np.isfinite(n)
    s, n = s[m], n[m]
    labs = [labs[i] for i in range(len(m)) if m[i]]
    if s.size == 0:
        return {"groups": [], "hyper": {}, "n_groups": 0}
    phat = s / n
    # moment-matched Beta on phat (clip)
    phat_c = np.clip(phat, 1e-6, 1 - 1e-6)
    mu = float(np.mean(phat_c))
    var = float(np.var(phat_c, ddof=1)) if phat_c.size > 1 else 0.0
    # Beta(α,β): μ=α/(α+β), var=μ(1-μ)/(α+β+1)
    if var > 0 and var < mu * (1 - mu):
        conc = mu * (1 - mu) / var - 1.0
        alpha = max(0.5, mu * conc)
        beta = max(0.5, (1 - mu) * conc)
    else:
        alpha, beta = float(a0), float(b0)
    # blend with weak prior so tiny panels don't over-concentrate
    alpha = 0.5 * alpha + 0.5 * a0
    beta = 0.5 * beta + 0.5 * b0
    groups = []
    for lab, si, ni in zip(labs, s, n):
        post = beta_binomial_posterior(si, ni, a0=alpha, b0=beta)
        raw = beta_binomial_posterior(si, ni, a0=a0, b0=b0)
        groups.append(
            {
                "label": lab,
                "n_success": float(si),
                "n_trials": float(ni),
                "mle": float(si / ni) if ni > 0 else float("nan"),
                "posterior": post,
                "unpooled": raw,
                "shrinkage": float(1.0 - post["var"] / raw["var"]) if raw["var"] > 0 and np.isfinite(raw["var"]) else float("nan"),
            }
        )
    return {
        "n_groups": int(len(groups)),
        "hyper": {"alpha": float(alpha), "beta": float(beta), "grand_mean": mu, "grand_var": var},
        "groups": groups,
    }


def hierarchical_poisson_shrinkage(
    counts: Sequence[float],
    exposures: Sequence[float],
    labels: Sequence[str] | None = None,
    *,
    a0: float = 1.0,
    b0: float = 1.0,
) -> dict[str, Any]:
    """Empirical-Bayes Gamma hyperparams for Poisson rates across groups."""
    k = np.asarray(counts, dtype=np.float64)
    e = np.asarray(exposures, dtype=np.float64)
    labs = list(labels) if labels is not None else [f"g{i}" for i in range(len(k))]
    m = (e > 0) & np.isfinite(k) & np.isfinite(e)
    k, e = k[m], e[m]
    labs = [labs[i] for i in range(len(m)) if m[i]]
    if k.size == 0:
        return {"groups": [], "hyper": {}, "n_groups": 0}
    rates = k / e
    mu = float(np.mean(rates))
    var = float(np.var(rates, ddof=1)) if rates.size > 1 else 0.0
    # Gamma mean=a/b, var=a/b² → a=μ²/var, b=μ/var
    if var > 0 and mu > 0:
        a_h = max(0.5, (mu * mu) / var)
        b_h = max(0.5, mu / var)
    else:
        a_h, b_h = float(a0), float(b0)
    a_h = 0.5 * a_h + 0.5 * a0
    b_h = 0.5 * b_h + 0.5 * b0
    groups = []
    for lab, ki, ei in zip(labs, k, e):
        post = poisson_gamma_posterior(ki, ei, a0=a_h, b0=b_h)
        raw = poisson_gamma_posterior(ki, ei, a0=a0, b0=b0)
        groups.append(
            {
                "label": lab,
                "count": float(ki),
                "exposure": float(ei),
                "mle": float(ki / ei),
                "posterior": post,
                "unpooled": raw,
            }
        )
    return {
        "n_groups": int(len(groups)),
        "hyper": {"a": float(a_h), "b": float(b_h), "grand_mean": mu, "grand_var": var},
        "groups": groups,
    }


def posterior_predictive_beta(
    post: dict[str, Any],
    *,
    n_pred_trials: int = 100,
    n_draws: int = 2000,
    seed: int = 0,
) -> dict[str, Any]:
    """PPC: draw θ~Beta(a,b), then y~Bin(n_pred, θ)."""
    a, b = float(post["a"]), float(post["b"])
    rng = np.random.default_rng(seed)
    theta = rng.beta(a, b, size=n_draws)
    y = rng.binomial(n_pred_trials, theta)
    return {
        "n_pred_trials": int(n_pred_trials),
        "n_draws": int(n_draws),
        "y_mean": float(np.mean(y)),
        "y_cri95": [float(np.quantile(y, 0.025)), float(np.quantile(y, 0.975))],
        "theta_mean": float(np.mean(theta)),
        "theta_cri95": [float(np.quantile(theta, 0.025)), float(np.quantile(theta, 0.975))],
    }


def prior_sensitivity_beta(
    successes: float,
    trials: float,
    priors: Sequence[tuple[float, float, str]] | None = None,
) -> dict[str, Any]:
    """Compare Beta posteriors under several priors (desk honesty note)."""
    if priors is None:
        priors = [
            (1.0, 1.0, "uniform"),
            (0.5, 0.5, "jeffreys"),
            (2.0, 2.0, "weak_shrink_0.5"),
            (1.0, 19.0, "skeptical_p05"),
            (1.0, 99.0, "skeptical_p01"),
        ]
    rows = []
    for a0, b0, name in priors:
        post = beta_binomial_posterior(successes, trials, a0=a0, b0=b0)
        rows.append({"prior": name, "a0": a0, "b0": b0, "mean": post["mean"], "cri95": post["cri95"]})
    return {"n_success": float(successes), "n_trials": float(trials), "rows": rows}


def logistic_laplace_posterior(
    y: NDArray[np.floating],
    X: NDArray[np.floating],
    *,
    prior_var: float = 25.0,
    max_iter: int = 50,
) -> dict[str, Any]:
    """Bayesian logistic regression via Laplace (MAP + Hessian) approx.

    Prior β ~ N(0, prior_var I). Returns posterior mean, se, 95% CrI approx.
    Desk use: P(adverse | storm_flag) / P(widen | fade).
    """
    yy = np.asarray(y, dtype=np.float64).reshape(-1)
    xx = np.asarray(X, dtype=np.float64)
    if xx.ndim == 1:
        xx = xx.reshape(-1, 1)
    m = np.isfinite(yy) & np.isfinite(xx).all(axis=1)
    yy, xx = yy[m], xx[m]
    n, k = xx.shape
    if n < k + 5 or np.unique(yy).size < 2:
        return {
            "n": int(n),
            "k": int(k),
            "beta_mean": [float("nan")] * k,
            "beta_se": [float("nan")] * k,
            "cri95": [[float("nan"), float("nan")]] * k,
            "converged": False,
        }
    # include intercept
    Z = np.column_stack([np.ones(n), xx])
    pdim = Z.shape[1]
    prec = 1.0 / float(prior_var)
    beta = np.zeros(pdim, dtype=np.float64)
    converged = False
    for _ in range(max_iter):
        eta = Z @ beta
        eta = np.clip(eta, -30, 30)
        p = 1.0 / (1.0 + np.exp(-eta))
        w = p * (1.0 - p)
        W = np.diag(w)
        # gradient / Hessian of log-posterior
        grad = Z.T @ (yy - p) - prec * beta
        H = -(Z.T @ W @ Z) - prec * np.eye(pdim)
        try:
            step = np.linalg.solve(-H, grad)
        except np.linalg.LinAlgError:
            break
        beta = beta + step
        if float(np.max(np.abs(step))) < 1e-8:
            converged = True
            break
    eta = Z @ beta
    p = 1.0 / (1.0 + np.exp(-np.clip(eta, -30, 30)))
    w = p * (1.0 - p)
    H = -(Z.T @ (w[:, None] * Z)) - prec * np.eye(pdim)
    try:
        cov = np.linalg.inv(-H)
        se = np.sqrt(np.clip(np.diag(cov), 0, None))
    except np.linalg.LinAlgError:
        se = np.full(pdim, np.nan)
    cri = [[float(beta[i] - 1.96 * se[i]), float(beta[i] + 1.96 * se[i])] for i in range(pdim)]
    return {
        "n": int(n),
        "k": int(pdim),
        "names": ["intercept"] + [f"x{i}" for i in range(k)],
        "beta_mean": beta.tolist(),
        "beta_se": se.tolist(),
        "cri95": cri,
        "prior_var": float(prior_var),
        "converged": bool(converged),
        "auc_proxy": float(np.mean((p >= 0.5) == (yy >= 0.5))),
    }


def density_grid_beta(post: dict[str, Any], *, n: int = 200) -> dict[str, list[float]]:
    a, b = float(post["a"]), float(post["b"])
    xs = np.linspace(0.001, 0.999, n)
    ys = stats.beta.pdf(xs, a, b)
    return {"x": xs.tolist(), "y": ys.tolist()}


def density_grid_gamma(post: dict[str, Any], *, n: int = 200, x_max: float | None = None) -> dict[str, list[float]]:
    a, b = float(post["a"]), float(post["b"])
    dist = stats.gamma(a=a, scale=1.0 / b)
    hi = float(x_max) if x_max is not None else float(dist.ppf(0.995))
    hi = max(hi, float(post.get("mean", 1.0)) * 3.0, 1e-6)
    xs = np.linspace(0.0, hi, n)
    ys = dist.pdf(xs)
    return {"x": xs.tolist(), "y": ys.tolist()}
