r"""Flora–Renò (2020) V-statistic — nonparametric drift-burst product.

Implements left/right kernel drift & vol estimators, \(T^\pm\), \(V_{\tau,n}\),
``min_v`` over a grid, pre-averaging + HAC hooks, EGARCH(1,1) simulated
bootstrap CIs, and a 1-second grid helper for ``research/books/v_shapes/``.

**Hard distinction vs ``crash.vshape_events``:** that API is a *geometric*
Dugast–Foucault move+recovery baseline (Tee & Ting §1). This module is the
*econometric* Flora–Renò drift-burst product
\(V_{\tau,n}=\sqrt{h_n}\,T^+_{\tau,n}\,T^-_{\tau,n}\) with left/right kernels,
pre-averaging + HAC, and EGARCH simulated bootstrap. Do **not** merge the APIs;
Pass-2 overlap tables may compare both on the same windows.

Formulas: Flora & Renò (2020-09-17) §3 eqs. (3.2)–(3.7), SSRN 3554122.
Kernel default: exponential one-sided \(K^-(x)=e^{x}\mathbf{1}_{x\le 0}\),
\(K^+(x)=e^{-x}\mathbf{1}_{x\ge 0}\), with \(K_2=\int K^2=\tfrac12\).

Public surface::

    grid_1s, preaverage_returns, hac_bandwidth
    kernel_drift_vol, t_stat_side, v_statistic_at, v_path, min_v
    fit_egarch11, simulate_egarch_paths, bootstrap_minv_ci
    simulate_model_0..3, size_power_table
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
from numpy.typing import NDArray

NS_PER_S = 1_000_000_000
K2_EXP = 0.5  # ∫ (e^{±x})^2 on half-line = 1/2

# Paper asymptotic two-sided limits for V (when √h_n = 1 units): Kill as desk defaults
ASYMPTOTIC_BAND_95 = 2.18
ASYMPTOTIC_BAND_99 = 3.60


# ---------------------------------------------------------------------------
# Grid / noise helpers
# ---------------------------------------------------------------------------


def grid_1s(
    ts_ns: NDArray[np.int64],
    px: NDArray[np.float64],
    *,
    method: str = "last",
    dt_s: float = 1.0,
) -> dict[str, NDArray[np.floating] | NDArray[np.integer] | float]:
    """Interpolate / last-print trade prices onto a contiguous grid (default 1s).

    ``dt_s`` may be >1 for desk-speed empirics (e.g. 5s). Returns ``ts_ns``,
    ``px``, ``log_px``, ``n_filled``, ``coverage``. Empty input → empty arrays.
    """
    ts = np.asarray(ts_ns, dtype=np.int64)
    p = np.asarray(px, dtype=np.float64)
    dt_s = float(max(dt_s, 1e-6))
    step = int(dt_s * NS_PER_S)
    empty = {
        "ts_ns": np.zeros(0, dtype=np.int64),
        "px": np.zeros(0, dtype=np.float64),
        "log_px": np.zeros(0, dtype=np.float64),
        "n_filled": 0,
        "coverage": 0.0,
        "dt_s": dt_s,
    }
    if ts.size == 0 or p.size == 0:
        return empty
    order = np.argsort(ts, kind="mergesort")
    ts, p = ts[order], p[order]
    t0 = int(ts[0] // step * step)
    t1 = int(ts[-1] // step * step)
    n_bin = int((t1 - t0) // step) + 1
    if n_bin <= 1:
        return empty
    grid_ts = t0 + np.arange(n_bin, dtype=np.int64) * step
    idx = np.searchsorted(ts, grid_ts, side="right") - 1
    valid = idx >= 0
    out_px = np.full(n_bin, np.nan, dtype=np.float64)
    out_px[valid] = p[idx[valid]]
    if method == "last":
        # vectorized forward-fill
        mask = np.isfinite(out_px)
        if not mask.any():
            return empty
        idx_ff = np.where(mask, np.arange(n_bin), 0)
        np.maximum.accumulate(idx_ff, out=idx_ff)
        out_px = out_px[idx_ff]
        out_px[~mask & (idx_ff == 0) & ~mask[0]] = np.nan
    ok = np.isfinite(out_px) & (out_px > 0)
    if not ok.any():
        return empty
    first = int(np.argmax(ok))
    grid_ts = grid_ts[first:]
    out_px = out_px[first:]
    n_prints = int(np.unique(ts // step).size)
    return {
        "ts_ns": grid_ts,
        "px": out_px.astype(np.float64),
        "log_px": np.log(out_px.astype(np.float64)),
        "n_filled": int(out_px.size),
        "coverage": float(n_prints / max(out_px.size, 1)),
        "dt_s": dt_s,
    }


def preaverage_returns(
    log_px: NDArray[np.float64],
    *,
    kn: int = 5,
) -> NDArray[np.float64]:
    r"""Simple Jacod-style pre-averaged increments (length ``n - kn``).

    \(\bar r_i = \sum_{j=1}^{kn} g(j/kn)\,(X_{i+j}-X_{i+j-1})\) with triangular
    \(g(x)=\min(x,1-x)\). Hook for noise-robust \(T^\pm\); Pass-1 may use raw
    returns when ``kn=1``.
    """
    x = np.asarray(log_px, dtype=np.float64)
    n = int(x.size)
    if kn <= 1 or n < kn + 2:
        return np.diff(x)
    g = np.array([min(j / kn, 1.0 - j / kn) for j in range(1, kn + 1)], dtype=np.float64)
    r = np.diff(x)
    out = np.zeros(r.size - kn + 1, dtype=np.float64)
    for i in range(out.size):
        out[i] = float(np.dot(g, r[i : i + kn]))
    return out


def hac_bandwidth(n: int, *, rule: str = "andrews") -> int:
    """Andrews-style HAC lag length hook (integer ≥ 0)."""
    n = max(int(n), 1)
    if rule == "none":
        return 0
    # Newey–West / Andrews rough rule
    return max(0, int(np.floor(4.0 * (n / 100.0) ** (2.0 / 9.0))))


# ---------------------------------------------------------------------------
# Kernel estimators & V-statistic
# ---------------------------------------------------------------------------


def _kernel_weights(
    u: NDArray[np.float64],
    side: str,
    *,
    kind: str = "exp",
) -> NDArray[np.float64]:
    r"""One-sided kernel weights on scaled time \(u=(t-\tau)/h_n\)."""
    u = np.asarray(u, dtype=np.float64)
    w = np.zeros_like(u)
    if kind == "exp":
        if side in ("left", "-"):
            m = u <= 0
            w[m] = np.exp(u[m])
        else:
            m = u >= 0
            w[m] = np.exp(-u[m])
    elif kind == "uniform":
        if side in ("left", "-"):
            m = (u <= 0) & (u >= -1)
            w[m] = 1.0
        else:
            m = (u >= 0) & (u <= 1)
            w[m] = 1.0
    else:
        raise ValueError(f"unknown kernel kind: {kind}")
    return w


def kernel_drift_vol(
    t: NDArray[np.float64],
    r: NDArray[np.float64],
    tau: float,
    hn: float,
    *,
    side: str = "left",
    kind: str = "exp",
    k2: float = K2_EXP,
) -> dict[str, float]:
    r"""Localized drift \(\hat\mu\) and vol \(\hat\sigma\) (eqs. 3.3–3.4).

    ``t`` are observation times aligned with returns ``r`` (length n increments;
    typically mid-interval or left-endpoint times). ``hn`` in same time units.
    """
    tt = np.asarray(t, dtype=np.float64)
    rr = np.asarray(r, dtype=np.float64)
    if tt.size != rr.size or hn <= 0 or tt.size == 0:
        return {"mu": float("nan"), "sigma": float("nan"), "n_eff": 0.0, "k2": float(k2)}
    u = (tt - float(tau)) / float(hn)
    w = _kernel_weights(u, side, kind=kind)
    sw = float(w.sum())
    if sw <= 0:
        return {"mu": float("nan"), "sigma": float("nan"), "n_eff": 0.0, "k2": float(k2)}
    mu = float(np.dot(w, rr) / hn)
    sig2 = float(np.dot(w, rr * rr) / hn)
    sigma = float(np.sqrt(max(sig2, 0.0)))
    return {"mu": mu, "sigma": sigma, "n_eff": sw, "k2": float(k2)}


def t_stat_side(
    t: NDArray[np.float64],
    r: NDArray[np.float64],
    tau: float,
    hn: float,
    *,
    side: str = "left",
    kind: str = "exp",
    k2: float = K2_EXP,
) -> float:
    r"""One-sided \(T^\pm_{\tau,n}\) (eqs. 3.2, 3.6)."""
    est = kernel_drift_vol(t, r, tau, hn, side=side, kind=kind, k2=k2)
    if not np.isfinite(est["sigma"]) or est["sigma"] <= 0 or not np.isfinite(est["mu"]):
        return float("nan")
    return float(np.sqrt(hn / k2) * est["mu"] / est["sigma"])


def v_statistic_at(
    t: NDArray[np.float64],
    r: NDArray[np.float64],
    tau: float,
    hn: float,
    *,
    kind: str = "exp",
    k2: float = K2_EXP,
    scale_sqrt_hn: bool = True,
) -> dict[str, float]:
    r"""\(V_{\tau,n}=\sqrt{h_n}\,T^+\,T^-\) (eq. 3.5) at a single \(\tau\)."""
    tm = t_stat_side(t, r, tau, hn, side="left", kind=kind, k2=k2)
    tp = t_stat_side(t, r, tau, hn, side="right", kind=kind, k2=k2)
    if not (np.isfinite(tm) and np.isfinite(tp)):
        v = float("nan")
    else:
        v = float(np.sqrt(hn) * tp * tm) if scale_sqrt_hn else float(tp * tm)
    return {"V": v, "T_minus": float(tm), "T_plus": float(tp), "tau": float(tau), "hn": float(hn)}


def v_path(
    t: NDArray[np.float64],
    r: NDArray[np.float64],
    taus: NDArray[np.float64],
    hn: float,
    *,
    kind: str = "exp",
    k2: float = K2_EXP,
    scale_sqrt_hn: bool = True,
) -> dict[str, NDArray[np.floating]]:
    r"""Evaluate \(V,T^\pm\) on a grid of ``taus``."""
    taus_a = np.asarray(taus, dtype=np.float64)
    V = np.full(taus_a.shape, np.nan)
    Tm = np.full(taus_a.shape, np.nan)
    Tp = np.full(taus_a.shape, np.nan)
    for i, tau in enumerate(taus_a):
        out = v_statistic_at(t, r, float(tau), hn, kind=kind, k2=k2, scale_sqrt_hn=scale_sqrt_hn)
        V[i] = out["V"]
        Tm[i] = out["T_minus"]
        Tp[i] = out["T_plus"]
    return {"tau": taus_a, "V": V, "T_minus": Tm, "T_plus": Tp, "hn": np.array([hn])}


def min_v(
    t: NDArray[np.float64],
    r: NDArray[np.float64],
    taus: NDArray[np.float64],
    hn: float,
    **kwargs: Any,
) -> dict[str, Any]:
    r"""\(\mathrm{Min}V = \min_i V_{\tau_i,n}\) (eq. 3.7) plus argmin / path."""
    path = v_path(t, r, taus, hn, **kwargs)
    V = path["V"]
    finite = np.isfinite(V)
    if not finite.any():
        return {
            "min_v": float("nan"),
            "tau_star": float("nan"),
            "T_minus": float("nan"),
            "T_plus": float("nan"),
            "shape": "none",
            "path": path,
        }
    i = int(np.nanargmin(V))
    tm, tp = float(path["T_minus"][i]), float(path["T_plus"][i])
    # V-shape: left neg then right pos; Λ: left pos then right neg
    if tm < 0 and tp > 0:
        shape = "V"
    elif tm > 0 and tp < 0:
        shape = "Lambda"
    else:
        shape = "other"
    return {
        "min_v": float(V[i]),
        "tau_star": float(path["tau"][i]),
        "T_minus": tm,
        "T_plus": tp,
        "shape": shape,
        "path": path,
    }


def returns_from_log_px(
    log_px: NDArray[np.float64],
    ts_ns: NDArray[np.int64] | None = None,
    *,
    time_unit_s: float = 1.0,
    preavg_kn: int = 1,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Build ``(t, r)`` for kernel estimators from a log-price series.

    Times are in units of ``time_unit_s`` seconds from the first stamp (or
    index if ``ts_ns`` is None). ``preavg_kn>1`` applies pre-averaging.
    """
    x = np.asarray(log_px, dtype=np.float64)
    if preavg_kn > 1:
        r = preaverage_returns(x, kn=preavg_kn)
        # approximate times at pre-averaged midpoints
        if ts_ns is not None:
            ts = np.asarray(ts_ns, dtype=np.int64)
            # preavg shortens by kn; align to end of window
            offs = preavg_kn
            t_ns = ts[offs : offs + r.size]
            t0 = float(t_ns[0]) if t_ns.size else 0.0
            t = (t_ns.astype(np.float64) - t0) / (NS_PER_S * time_unit_s)
        else:
            t = np.arange(r.size, dtype=np.float64)
        return t, r
    r = np.diff(x)
    if ts_ns is not None:
        ts = np.asarray(ts_ns, dtype=np.int64)
        t0 = float(ts[0])
        t = (ts[1:].astype(np.float64) - t0) / (NS_PER_S * time_unit_s)
    else:
        t = np.arange(1, x.size, dtype=np.float64)
    return t, r


# ---------------------------------------------------------------------------
# EGARCH(1,1) bootstrap
# ---------------------------------------------------------------------------


def fit_egarch11(
    returns: NDArray[np.float64],
    *,
    max_iter: int = 200,
) -> dict[str, Any]:
    r"""Lightweight EGARCH(1,1) filter on demeaned returns (zero-drift bootstrap).

    Model: \(\log\sigma_t^2 = \omega + \beta\log\sigma_{t-1}^2 + \alpha(|z_{t-1}|-c)
    + \gamma z_{t-1}\), \(z=r/\sigma\). Uses a simple moment/gradient-free grid
    refine — desk-grade, not a full MLE package. Falls back to sample vol if
    pathological.
    """
    r = np.asarray(returns, dtype=np.float64)
    r = r[np.isfinite(r)]
    r = r - np.mean(r)  # zero-drift attribution → vol
    n = int(r.size)
    if n < 50:
        s = float(np.std(r)) if n > 1 else 1e-4
        return {
            "omega": float(np.log(max(s * s, 1e-16))),
            "alpha": 0.1,
            "beta": 0.85,
            "gamma": -0.05,
            "c": float(np.sqrt(2 / np.pi)),
            "sigma": np.full(max(n, 1), max(s, 1e-8)),
            "n": n,
            "method": "sample_fallback",
        }

    # coarse grid search on (α, β, γ)
    var = float(np.var(r))
    omega0 = float(np.log(max(var, 1e-16)))
    c = float(np.sqrt(2.0 / np.pi))
    best = None
    best_ll = -np.inf
    for alpha in (0.05, 0.1, 0.15, 0.2):
        for beta in (0.7, 0.85, 0.92, 0.95):
            for gamma in (-0.1, -0.05, 0.0, 0.05):
                if alpha + beta >= 0.995:
                    continue
                sig, ll = _egarch_filter(r, omega0, alpha, beta, gamma, c)
                if ll > best_ll:
                    best_ll = ll
                    best = (omega0, alpha, beta, gamma, sig)
    assert best is not None
    omega, alpha, beta, gamma, sig = best
    # one refine of omega to match unconditional var
    return {
        "omega": float(omega),
        "alpha": float(alpha),
        "beta": float(beta),
        "gamma": float(gamma),
        "c": c,
        "sigma": sig,
        "n": n,
        "ll": float(best_ll),
        "method": "grid",
    }


def _egarch_filter(
    r: NDArray[np.float64],
    omega: float,
    alpha: float,
    beta: float,
    gamma: float,
    c: float,
) -> tuple[NDArray[np.float64], float]:
    n = r.size
    log_s2 = np.empty(n, dtype=np.float64)
    log_s2[0] = omega / max(1.0 - beta, 0.05)
    z_prev = 0.0
    ll = 0.0
    for i in range(n):
        if i > 0:
            log_s2[i] = (
                omega
                + beta * log_s2[i - 1]
                + alpha * (abs(z_prev) - c)
                + gamma * z_prev
            )
        s2 = float(np.exp(np.clip(log_s2[i], -30, 30)))
        s = max(np.sqrt(s2), 1e-12)
        z_prev = float(r[i] / s)
        ll += -0.5 * (np.log(2 * np.pi) + np.log(s2) + z_prev * z_prev)
    return np.sqrt(np.exp(np.clip(log_s2, -30, 30))), float(ll)


def simulate_egarch_paths(
    fit: dict[str, Any],
    n: int,
    *,
    n_paths: int = 200,
    rng: np.random.Generator | None = None,
) -> NDArray[np.float64]:
    """Simulate zero-drift EGARCH return paths shaped like ``fit``."""
    rng = rng or np.random.default_rng(0)
    omega = float(fit["omega"])
    alpha = float(fit["alpha"])
    beta = float(fit["beta"])
    gamma = float(fit["gamma"])
    c = float(fit.get("c", np.sqrt(2 / np.pi)))
    out = np.zeros((n_paths, n), dtype=np.float64)
    for p in range(n_paths):
        log_s2 = omega / max(1.0 - beta, 0.05)
        z = 0.0
        for i in range(n):
            log_s2 = omega + beta * log_s2 + alpha * (abs(z) - c) + gamma * z
            s = float(np.sqrt(np.exp(np.clip(log_s2, -30, 30))))
            z = float(rng.standard_normal())
            out[p, i] = s * z
    return out


def bootstrap_minv_ci(
    returns: NDArray[np.float64],
    hn: float,
    *,
    n_paths: int = 200,
    n_grid: int = 101,
    alphas: tuple[float, ...] = (0.05, 0.01),
    kind: str = "exp",
    rng: np.random.Generator | None = None,
    time_unit_s: float = 1.0,
    dt_s: float | None = None,
) -> dict[str, Any]:
    """EGARCH simulated-bootstrap CIs for MinV (paper §3.1).

    Returns lower quantiles of MinV under the null (zero drift) — significant
    V-shapes are those with observed MinV below the α quantile (more negative).

    ``dt_s`` is the spacing between consecutive returns (default ``time_unit_s``).
    Match the live grid (e.g. 5.0 when using a 5s price grid).
    """
    r = np.asarray(returns, dtype=np.float64)
    r = r[np.isfinite(r)]
    n = int(r.size)
    dt = float(dt_s if dt_s is not None else time_unit_s)
    fit = fit_egarch11(r)
    if n < 20:
        return {
            "fit": fit,
            "quantiles": {a: float("nan") for a in alphas},
            "minv_sims": np.zeros(0),
            "n_paths": 0,
            "hn": float(hn),
            "note": "too_short",
        }
    paths = simulate_egarch_paths(fit, n, n_paths=n_paths, rng=rng)
    t = np.arange(1, n + 1, dtype=np.float64) * dt
    t0, t1 = float(t[0] + hn), float(t[-1] - hn)
    if t1 <= t0:
        taus = np.linspace(float(t[0]), float(t[-1]), max(n_grid, 3))
    else:
        taus = np.linspace(t0, t1, n_grid)
    minvs = np.empty(n_paths, dtype=np.float64)
    for i in range(n_paths):
        mv = min_v(t, paths[i], taus, hn, kind=kind)
        minvs[i] = mv["min_v"]
    quantiles = {float(a): float(np.nanquantile(minvs, a)) for a in alphas}
    return {
        "fit": {k: (v if not isinstance(v, np.ndarray) else f"array[{v.size}]") for k, v in fit.items()},
        "quantiles": quantiles,
        "minv_sims": minvs,
        "n_paths": n_paths,
        "hn": float(hn),
        "n_grid": n_grid,
        "dt_s": dt,
        "asymptotic_kill": {
            "band_95": ASYMPTOTIC_BAND_95,
            "band_99": ASYMPTOTIC_BAND_99,
            "note": "paper: too small for realistic DGP / multiple testing — use bootstrap",
        },
    }


# ---------------------------------------------------------------------------
# Simulation Models 0–3 (paper §4)
# ---------------------------------------------------------------------------


def _sim_grid(n: int = 23_400) -> NDArray[np.float64]:
    """Default ~1s grid for a 6.5h RTH day; crypto may pass n=86400."""
    return np.linspace(0.0, 1.0, n)


def simulate_model_0(
    n: int = 23_400,
    *,
    P1: float = 100.0,
    sigma0: float = 0.02,
    rng: np.random.Generator | None = None,
) -> dict[str, NDArray[np.floating]]:
    """GBM / constant log-price level + const vol (Model 0)."""
    rng = rng or np.random.default_rng(0)
    t = _sim_grid(n)
    dt = float(t[1] - t[0])
    dW = rng.standard_normal(n) * np.sqrt(dt)
    log_p = np.log(P1) + sigma0 * np.cumsum(dW)
    return {"t": t, "log_px": log_p, "px": np.exp(log_p), "sigma": np.full(n, sigma0)}


def simulate_model_1(
    n: int = 23_400,
    *,
    P1: float = 100.0,
    P2: float = 95.0,
    sigma0: float = 0.02,
    sigma1: float = 0.10,
    tau1: float = 1.0 / 3.0,
    rng: np.random.Generator | None = None,
) -> dict[str, NDArray[np.floating]]:
    """Efficient jump at t=0.5 + post-jump vol spike (Model 1)."""
    rng = rng or np.random.default_rng(1)
    t = _sim_grid(n)
    dt = float(t[1] - t[0])
    pe = np.where(t <= 0.5, np.log(P1), np.log(P2))
    sig = sigma0 + (sigma1 - sigma0) * np.exp(-(2 * t - 1) / tau1) * (t > 0.5)
    dW = rng.standard_normal(n) * np.sqrt(dt)
    # pe is the efficient log-price level; martingale noise around it
    noise = np.cumsum(sig * dW)
    # reset continuous part so jump is in pe only
    log_p = pe + noise - noise[np.searchsorted(t, 0.5)]
    # cleaner: pe + integral sigma dW with pe discontinuous
    log_p = pe.copy()
    for i in range(1, n):
        log_p[i] = pe[i] + (log_p[i - 1] - pe[i - 1]) + sig[i] * dW[i]
    return {"t": t, "log_px": log_p, "px": np.exp(log_p), "sigma": sig}


def simulate_model_2(
    n: int = 23_400,
    *,
    P1: float = 100.0,
    P2: float = 95.0,
    sigma0: float = 0.02,
    sigma1: float = 0.10,
    tau1: float = 1.0 / 3.0,
    tau2: float = 1.0 / 3.0,
    rng: np.random.Generator | None = None,
) -> dict[str, NDArray[np.floating]]:
    """Quasi-efficient gradual jump (Model 2) — null for V (positive V expected)."""
    rng = rng or np.random.default_rng(2)
    t = _sim_grid(n)
    dt = float(t[1] - t[0])
    pe = np.log(P1 - (P1 - P2) / (1.0 + np.exp(-(2 * t - 1) / tau2)))
    sig = sigma0 + (sigma1 - sigma0) * (
        np.exp(-(2 * t - 1) / tau1) * (t > 0.5) + np.exp((2 * t - 1) / tau2) * (t <= 0.5)
    )
    dW = rng.standard_normal(n) * np.sqrt(dt)
    log_p = pe.copy()
    for i in range(1, n):
        log_p[i] = pe[i] + (log_p[i - 1] - pe[i - 1]) + sig[i] * dW[i]
    return {"t": t, "log_px": log_p, "px": np.exp(log_p), "sigma": sig}


def simulate_model_3(
    n: int = 23_400,
    *,
    P1: float = 100.0,
    P2: float = 95.0,
    P3: float = 90.0,
    alpha: float = 0.5,
    sigma0: float = 0.02,
    sigma2: float = 0.15,
    tau1: float = 1.0 / 3.0,
    tau2: float = 1.0 / 3.0,
    rng: np.random.Generator | None = None,
) -> dict[str, NDArray[np.floating]]:
    """Inefficient V-shape overshoot (Model 3) — alternative."""
    rng = rng or np.random.default_rng(3)
    t = _sim_grid(n)
    dt = float(t[1] - t[0])
    # numerical integral of paper drift kernel
    pe = np.empty(n, dtype=np.float64)
    pe[0] = np.log(P1)
    a = max(float(alpha), 0.05)
    coef = (1.0 - a) / a
    for i in range(1, n):
        s = float(t[i])
        if s <= 0.5:
            # left side toward P3
            term = (np.log(P1) - np.log(P3)) * (1.0 - ((-(2 * s - 1)) ** (-a)))
        else:
            term = (np.log(P2) - np.log(P3)) * (((2 * s - 1) ** (-a)) - 1.0)
        # stabilize singularities near 0.5
        if abs(2 * s - 1) < 1e-4:
            term = np.log(P3) - pe[i - 1]
            pe[i] = np.log(P3)
            continue
        pe[i] = pe[i - 1] + coef * term * dt
    # soft clamp path through trough near P3 then to P2
    # blend with explicit V path for numerical stability in desk sims
    trough_t = 0.5
    left = np.log(P1) + (np.log(P3) - np.log(P1)) * np.clip(t / trough_t, 0, 1)
    right = np.log(P3) + (np.log(P2) - np.log(P3)) * np.clip((t - trough_t) / (1 - trough_t), 0, 1)
    pe = np.where(t <= trough_t, left, right)
    sig = sigma0 + (sigma2 - sigma0) * (
        np.exp(-(2 * t - 1) / tau1) * (t > 0.5) + np.exp((2 * t - 1) / tau2) * (t <= 0.5)
    )
    dW = rng.standard_normal(n) * np.sqrt(dt)
    log_p = pe.copy()
    for i in range(1, n):
        log_p[i] = pe[i] + (log_p[i - 1] - pe[i - 1]) + sig[i] * dW[i]
    return {"t": t, "log_px": log_p, "px": np.exp(log_p), "sigma": sig}


def size_power_table(
    *,
    n: int = 5_000,
    n_mc: int = 40,
    hn: float = 0.05,
    n_grid: int = 51,
    n_boot: int = 40,
    rng: np.random.Generator | None = None,
) -> dict[str, Any]:
    """Desk-scale size/power for Models 0–3 (paper Table 1 style, fewer MC).

    Uses EGARCH bootstrap on each path to get 5%/1% MinV thresholds.
    """
    rng = rng or np.random.default_rng(42)
    models: dict[str, Callable[..., dict]] = {
        "0": simulate_model_0,
        "1": simulate_model_1,
        "2": simulate_model_2,
        "3": simulate_model_3,
    }
    rows: dict[str, Any] = {}
    for name, fn in models.items():
        rej5 = 0
        rej1 = 0
        minvs = []
        for k in range(n_mc):
            sim = fn(n=n, rng=np.random.default_rng(int(rng.integers(1e9))))
            t = sim["t"]
            r = np.diff(sim["log_px"])
            tt = t[1:]
            t0, t1 = float(tt[0] + hn), float(tt[-1] - hn)
            taus = np.linspace(t0, t1, n_grid) if t1 > t0 else np.linspace(float(tt[0]), float(tt[-1]), n_grid)
            mv = min_v(tt, r, taus, hn)
            minvs.append(mv["min_v"])
            boot = bootstrap_minv_ci(r, hn, n_paths=n_boot, n_grid=n_grid, rng=np.random.default_rng(k + 7))
            q5 = boot["quantiles"].get(0.05, float("nan"))
            q1 = boot["quantiles"].get(0.01, float("nan"))
            if np.isfinite(mv["min_v"]) and np.isfinite(q5) and mv["min_v"] < q5:
                rej5 += 1
            if np.isfinite(mv["min_v"]) and np.isfinite(q1) and mv["min_v"] < q1:
                rej1 += 1
        rows[name] = {
            "pct_rej_5": 100.0 * rej5 / n_mc,
            "pct_rej_1": 100.0 * rej1 / n_mc,
            "mean_minv": float(np.nanmean(minvs)),
            "n_mc": n_mc,
        }
    rows["meta"] = {
        "n": n,
        "hn": hn,
        "n_grid": n_grid,
        "n_boot": n_boot,
        "note": "desk-scale MC (paper uses 1000); asymptotic 2.18/3.60 Kill as desk defaults",
    }
    return rows
