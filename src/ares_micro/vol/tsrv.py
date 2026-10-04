"""Two Scales Realized Volatility (TSRV) — Zhang, Mykland & Aït-Sahalia (2005).

Implements the five estimators from Romero (2016) thesis exposition of ZMA05:
fifth-best (all-sample RV), fourth (sparse), third (optimal sparse), second
(averaged sparse grids), first (TSRV bias-corrected) + small-sample adj, and
the noise variance proxy Ê[ε²] = [Y,Y]_all / (2n).

Notebooks/scripts import this module; do not paste estimators inline.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray


from ares_micro.book.tob import mid_price
from ares_micro.core.arrays import forward_fill
from ares_micro.core.constants import NS_PER_S
from ares_micro.core.rv import log_returns, realized_variance


def fifth_best(returns_all: NDArray[np.float64]) -> float:
    """All-sample RV [Y,Y]_T^(all) — biased for integrated vol; noise-dominated."""
    return realized_variance(returns_all)


def noise_variance_proxy(returns_all: NDArray[np.float64]) -> dict[str, float]:
    """Eq. (9): Ê[ε²] = (1/(2n)) [Y,Y]_T^(all).

    Consistent for microstructure noise variance under ZMA05 i.i.d. noise.
    """
    r = np.asarray(returns_all, dtype=np.float64)
    r = r[np.isfinite(r)]
    n = int(r.size)
    yy = realized_variance(r)
    if n <= 0 or not np.isfinite(yy):
        return {
            "yy_all": float("nan"),
            "n": 0.0,
            "noise_var": float("nan"),
            "noise_std": float("nan"),
        }
    nv = yy / (2.0 * n)
    return {
        "yy_all": float(yy),
        "n": float(n),
        "noise_var": float(nv),
        "noise_std": float(np.sqrt(nv)) if nv >= 0 else float("nan"),
    }


def fourth_best(log_px: NDArray[np.float64], step: int) -> float:
    """Sparse RV at fixed step (e.g. step=300 ≈ 5 min on 1s grid)."""
    x = np.asarray(log_px, dtype=np.float64)
    step = max(int(step), 1)
    if x.size < step + 1:
        return float("nan")
    xs = x[::step]
    return realized_variance(np.diff(xs))


def third_best_optimal_n(
    *,
    T: float,
    noise_var: float,
    iq: float,
) -> float:
    """Eq. (3): n*_sparse = (T / (4 (Eε²)²) · IQ)^(1/3) with IQ = ∫ σ⁴ dt."""
    if noise_var <= 0 or not np.isfinite(noise_var) or not np.isfinite(iq) or iq <= 0:
        return float("nan")
    return float((T / (4.0 * noise_var**2) * iq) ** (1.0 / 3.0))


def third_best(log_px: NDArray[np.float64], n_sparse: int) -> float:
    """Sparse RV at optimal (or chosen) n_sparse intervals over the path."""
    x = np.asarray(log_px, dtype=np.float64)
    n_sparse = max(int(n_sparse), 1)
    if x.size < 2:
        return float("nan")
    # step so that roughly n_sparse returns
    step = max(int(np.floor((x.size - 1) / n_sparse)), 1)
    return fourth_best(x, step)


def second_best(log_px: NDArray[np.float64], K: int, step: int) -> dict[str, float]:
    """Average of K sparse grids (G_k): start at offset k, sample every ``step``.

    Returns avg RV and n_bar = (n - K + 1) / K.
    """
    x = np.asarray(log_px, dtype=np.float64)
    K = max(int(K), 1)
    step = max(int(step), 1)
    n = int(x.size) - 1  # number of 1-step returns available
    if n < step or x.size < step + 1:
        return {"yy_avg": float("nan"), "n_bar": float("nan"), "K": float(K), "n": float(max(n, 0))}
    rvs: list[float] = []
    ns: list[int] = []
    for k in range(K):
        xs = x[k::step]
        if xs.size < 2:
            continue
        rvs.append(realized_variance(np.diff(xs)))
        ns.append(int(xs.size) - 1)
    if not rvs:
        return {"yy_avg": float("nan"), "n_bar": float("nan"), "K": float(K), "n": float(n)}
    n_bar = float(np.mean(ns)) if ns else float((n - K + 1) / K)
    return {
        "yy_avg": float(np.mean(rvs)),
        "n_bar": float(n_bar),
        "K": float(K),
        "n": float(n),
    }


def first_best(
    log_px: NDArray[np.float64],
    *,
    K: int,
    step: int,
) -> dict[str, float]:
    """TSRV: ⟨X,X⟩̂_T = [Y,Y]_avg − (n̄/n) [Y,Y]_all  (eq. 5).

    Plus small-sample adj (eq. 6): (1 − n̄/n)^−1 · ⟨X,X⟩̂_T.
    """
    x = np.asarray(log_px, dtype=np.float64)
    r_all = log_returns(x)
    yy_all = fifth_best(r_all)
    avg = second_best(x, K=K, step=step)
    n = float(avg["n"])
    n_bar = float(avg["n_bar"])
    yy_avg = float(avg["yy_avg"])
    if not np.isfinite(yy_all) or not np.isfinite(yy_avg) or n <= 0 or not np.isfinite(n_bar):
        return {
            "yy_all": float(yy_all),
            "yy_avg": float(yy_avg),
            "tsrv": float("nan"),
            "tsrv_adj": float("nan"),
            "n": n,
            "n_bar": n_bar,
            "K": float(K),
            "step": float(step),
        }
    ratio = n_bar / n
    tsrv = yy_avg - ratio * yy_all
    adj_factor = 1.0 / (1.0 - ratio) if abs(1.0 - ratio) > 1e-12 else float("nan")
    tsrv_adj = adj_factor * tsrv if np.isfinite(adj_factor) else float("nan")
    return {
        "yy_all": float(yy_all),
        "yy_avg": float(yy_avg),
        "tsrv": float(tsrv),
        "tsrv_adj": float(tsrv_adj),
        "n": n,
        "n_bar": n_bar,
        "K": float(K),
        "step": float(step),
        "ratio_nbar_n": float(ratio),
    }


def all_estimators(
    log_px: NDArray[np.float64],
    *,
    K: int = 300,
    step: int = 300,
    n_sparse_opt: int | None = None,
) -> dict[str, float]:
    """Compute fifth→first (+adj) plus noise proxy on a log-price path."""
    x = np.asarray(log_px, dtype=np.float64)
    r = log_returns(x)
    noise = noise_variance_proxy(r)
    fb = first_best(x, K=K, step=step)
    n_sp = int(n_sparse_opt) if n_sparse_opt is not None else max(int(np.floor((x.size - 1) / step)), 1)
    return {
        "fifth": fifth_best(r),
        "fourth": fourth_best(x, step),
        "third": third_best(x, n_sp),
        "second": float(fb["yy_avg"]),
        "first": float(fb["tsrv"]),
        "first_adj": float(fb["tsrv_adj"]),
        **{f"noise_{k}": v for k, v in noise.items()},
        "n": float(fb["n"]),
        "n_bar": float(fb["n_bar"]),
        "K": float(K),
        "step": float(step),
    }


# ---------------------------------------------------------------------------
# Heston + noise Monte Carlo (thesis §V / ZMA05 params)
# ---------------------------------------------------------------------------

HESTON_DEFAULTS: dict[str, float] = {
    "mu": 0.05,
    "kappa": 5.0,
    "alpha": 0.04,
    "gamma": 0.5,
    "rho": -0.5,
    "noise_std": 0.0005,  # 0.05% of price level on log scale ≈ σ_ε
    "T": 1.0 / 252.0,
    "dt": 1.0 / (252.0 * 6.5 * 3600.0),  # 1s of a 6.5h equity day
}


def simulate_heston_day(
    rng: np.random.Generator,
    *,
    mu: float = 0.05,
    kappa: float = 5.0,
    alpha: float = 0.04,
    gamma: float = 0.5,
    rho: float = -0.5,
    noise_std: float = 0.0005,
    T: float = 1.0 / 252.0,
    dt: float | None = None,
    x0: float = 0.0,
    v0: float | None = None,
) -> dict[str, NDArray[np.float64] | float]:
    """One trading-day path under Heston + i.i.d. Gaussian microstructure noise.

    Returns latent log-price X, observed Y = X + ε, and integrated variance.
    Default ``dt`` ≈ 1 second on a 6.5h RTH day (23_400 steps).
    """
    if dt is None:
        dt = 1.0 / (252.0 * 6.5 * 3600.0)
    n = max(int(round(T / dt)), 2)
    v0 = float(alpha if v0 is None else v0)
    X = np.empty(n + 1, dtype=np.float64)
    v = np.empty(n + 1, dtype=np.float64)
    X[0] = float(x0)
    v[0] = max(v0, 1e-12)
    iq = 0.0  # ∫ σ⁴ ≈ sum v² dt
    iv = 0.0  # ∫ σ² dt
    for i in range(n):
        z1, z2 = rng.standard_normal(2)
        dW = z1
        dB = rho * z1 + np.sqrt(max(1.0 - rho * rho, 0.0)) * z2
        vi = max(v[i], 1e-12)
        v[i + 1] = max(vi + kappa * (alpha - vi) * dt + gamma * np.sqrt(vi) * np.sqrt(dt) * dW, 1e-12)
        X[i + 1] = X[i] + (mu - 0.5 * vi) * dt + np.sqrt(vi) * np.sqrt(dt) * dB
        iv += vi * dt
        iq += (vi * vi) * dt
    eps = rng.normal(0.0, noise_std, size=n + 1)
    Y = X + eps
    return {
        "log_X": X,
        "log_Y": Y,
        "v": v,
        "integrated_var": float(iv),
        "integrated_quarticity": float(iq),
        "n_steps": float(n),
        "dt": float(dt),
        "T": float(T),
        "noise_std": float(noise_std),
    }


def monte_carlo_estimators(
    n_sims: int = 500,
    *,
    K: int = 300,
    step: int = 300,
    seed: int = 42,
    heston: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Replicate thesis Table-1 style bias/var/RMSE for the five estimators.

    Default ``n_sims`` is desk-speed (thesis used 25_000); pass larger for final.
    """
    rng = np.random.default_rng(seed)
    params = {**HESTON_DEFAULTS, **(heston or {})}
    names = ("fifth", "fourth", "third", "second", "first", "first_adj")
    errs: dict[str, list[float]] = {k: [] for k in names}
    sim_kw = {
        "mu": params["mu"],
        "kappa": params["kappa"],
        "alpha": params["alpha"],
        "gamma": params["gamma"],
        "rho": params["rho"],
        "noise_std": params["noise_std"],
        "T": params["T"],
        "dt": params.get("dt"),
    }
    for _ in range(int(n_sims)):
        path = simulate_heston_day(rng, **sim_kw)
        true_iv = float(path["integrated_var"])
        est = all_estimators(np.asarray(path["log_Y"], dtype=np.float64), K=K, step=step)
        for k in names:
            val = float(est[k])
            if np.isfinite(val) and np.isfinite(true_iv):
                errs[k].append(val - true_iv)
    out: dict[str, Any] = {
        "n_sims": int(n_sims),
        "K": int(K),
        "step": int(step),
        "heston": params,
        "estimators": {},
    }
    for k in names:
        e = np.asarray(errs[k], dtype=np.float64)
        if e.size == 0:
            out["estimators"][k] = {"bias": float("nan"), "var": float("nan"), "rmse": float("nan"), "n": 0}
            continue
        bias = float(np.mean(e))
        var = float(np.var(e, ddof=1)) if e.size > 1 else 0.0
        rmse = float(np.sqrt(np.mean(e * e)))
        out["estimators"][k] = {"bias": bias, "var": var, "rmse": rmse, "n": int(e.size)}
    return out


def grid_log_price_from_tape(
    ts_ns: NDArray[np.int64],
    px: NDArray[np.float64],
    *,
    dt_s: float = 1.0,
) -> dict[str, Any]:
    """Last-print calendar grid → log prices (NaN-filled forward)."""
    t = np.asarray(ts_ns, dtype=np.int64)
    p = np.asarray(px, dtype=np.float64)
    m = np.isfinite(p) & (p > 0)
    t, p = t[m], p[m]
    if t.size < 2:
        return {"log_px": np.asarray([], dtype=np.float64), "n_filled": 0, "dt_s": float(dt_s)}
    t0, t1 = int(t.min()), int(t.max())
    step_ns = int(dt_s * NS_PER_S)
    edges = np.arange(t0, t1 + step_ns, step_ns, dtype=np.int64)
    log_px = np.full(edges.size, np.nan, dtype=np.float64)
    idx = np.searchsorted(edges, t, side="right") - 1
    idx = np.clip(idx, 0, edges.size - 1)
    # last print wins within each bin
    for i, j in enumerate(idx):
        log_px[j] = np.log(p[i])
    filled = int(np.isfinite(log_px).sum())
    log_px = forward_fill(log_px)
    return {
        "log_px": log_px,
        "ts_ns": edges,
        "n_filled": filled,
        "n_grid": int(log_px.size),
        "dt_s": float(dt_s),
        "coverage": float(filled) / float(log_px.size) if log_px.size else 0.0,
    }


def trade_clock_log_px(
    ts_ns: NDArray[np.int64],
    px: NDArray[np.float64],
    *,
    max_n: int | None = None,
) -> dict[str, Any]:
    """Event-time log prices: one observation per trade (no calendar fill).

    Classic microstructure bounce shows up more clearly here than on a
    forward-filled 1s last-print grid.
    """
    t = np.asarray(ts_ns, dtype=np.int64)
    p = np.asarray(px, dtype=np.float64)
    m = np.isfinite(p) & (p > 0)
    t, p = t[m], p[m]
    if t.size < 2:
        return {"log_px": np.asarray([], dtype=np.float64), "ts_ns": t, "n": 0}
    order = np.argsort(t)
    t, p = t[order], p[order]
    if max_n is not None and t.size > int(max_n):
        # uniform downsample to keep TSRV K/step tractable
        idx = np.linspace(0, t.size - 1, int(max_n), dtype=np.int64)
        t, p = t[idx], p[idx]
    return {
        "log_px": np.log(p),
        "ts_ns": t,
        "n": int(t.size),
        "clock": "trade",
    }


def estimators_trade_clock(
    ts_ns: NDArray[np.int64],
    px: NDArray[np.float64],
    *,
    K: int = 300,
    step: int = 300,
    max_n: int = 50_000,
) -> dict[str, float]:
    """TSRV ladder + noise proxy on trade clock (step in #trades, not seconds)."""
    g = trade_clock_log_px(ts_ns, px, max_n=max_n)
    out = estimators_on_log_px(g["log_px"], K=K, step=step)
    return out


def mid_clock_log_px(
    ts_ns: NDArray[np.int64],
    bid: NDArray[np.float64],
    ask: NDArray[np.float64],
    *,
    dt_s: float = 1.0,
) -> dict[str, Any]:
    """Calendar mid-price clock from TOB bid/ask (forward-filled)."""
    t = np.asarray(ts_ns, dtype=np.int64)
    b = np.asarray(bid, dtype=np.float64)
    a = np.asarray(ask, dtype=np.float64)
    mid = mid_price(b, a)
    m = np.isfinite(mid) & (mid > 0) & np.isfinite(b) & np.isfinite(a) & (a > b)
    g = grid_log_price_from_tape(t[m], mid[m], dt_s=dt_s)
    g["clock"] = "mid"
    return g


def tick_rule_bounce_path(
    ts_ns: NDArray[np.int64],
    px: NDArray[np.float64],
    *,
    max_n: int | None = 50_000,
) -> dict[str, Any]:
    """Tick-rule bounce clock: retain direction-changing trade prices only.

    Lee–Ready / tick rule: sign_t = sign(Δp_t); zero-change inherits prior sign.
    Bounce subsequence = prints where sign flips (classic bid-ask bounce path).
    """
    t = np.asarray(ts_ns, dtype=np.int64)
    p = np.asarray(px, dtype=np.float64)
    m = np.isfinite(p) & (p > 0)
    t, p = t[m], p[m]
    if t.size < 3:
        return {
            "log_px": np.asarray([], dtype=np.float64),
            "ts_ns": t,
            "n": 0,
            "n_flips": 0,
            "flip_rate": float("nan"),
            "clock": "tick_bounce",
        }
    order = np.argsort(t)
    t, p = t[order], p[order]
    dp = np.diff(p)
    sign = np.ones(p.size, dtype=np.float64)
    for i in range(1, p.size):
        if dp[i - 1] > 0:
            sign[i] = 1.0
        elif dp[i - 1] < 0:
            sign[i] = -1.0
        else:
            sign[i] = sign[i - 1]
    flip = np.zeros(p.size, dtype=bool)
    flip[0] = True
    flip[1:] = sign[1:] != sign[:-1]
    tf, pf = t[flip], p[flip]
    if max_n is not None and tf.size > int(max_n):
        idx = np.linspace(0, tf.size - 1, int(max_n), dtype=np.int64)
        tf, pf = tf[idx], pf[idx]
    return {
        "log_px": np.log(pf),
        "ts_ns": tf,
        "n": int(tf.size),
        "n_flips": int(flip.sum()),
        "flip_rate": float(flip.mean()),
        "clock": "tick_bounce",
    }


def estimators_on_log_px(
    log_px: NDArray[np.float64],
    *,
    K: int = 300,
    step: int = 300,
) -> dict[str, float]:
    x = np.asarray(log_px, dtype=np.float64)
    if x.size < step + 2:
        return {"ok": 0.0, "n": float(x.size)}
    est = all_estimators(x, K=K, step=step)
    nv = noise_variance_proxy(log_returns(x))
    fifth = float(est["fifth"])
    fourth = float(est["fourth"])
    return {
        "ok": 1.0,
        "n": float(x.size),
        "fifth": fifth,
        "fourth": fourth,
        "first_adj": float(est["first_adj"]),
        "second": float(est["second"]),
        "noise_var": float(nv["noise_var"]),
        "noise_std": float(nv["noise_std"]),
        "fifth_over_fourth": (
            fifth / fourth if np.isfinite(fifth) and np.isfinite(fourth) and fourth > 0 else float("nan")
        ),
        "K": float(K),
        "step": float(step),
    }


def compare_clocks_bootstrap(
    clocks: dict[str, list[float] | NDArray[np.float64]],
    *,
    n_boot: int = 500,
    seed: int = 11,
) -> dict[str, Any]:
    """Bootstrap medians + paired diffs for fifth/fourth ratios by clock."""
    names = list(clocks.keys())
    series: dict[str, NDArray[np.float64]] = {}
    for n in names:
        a = np.asarray(clocks[n], dtype=np.float64)
        series[n] = a[np.isfinite(a)]
    rng = np.random.default_rng(seed)
    out: dict[str, Any] = {"clocks": {}, "pairs": {}}
    for n, a in series.items():
        if a.size == 0:
            out["clocks"][n] = {"n": 0, "median": float("nan"), "ci95": [float("nan"), float("nan")]}
            continue
        boots = [float(np.median(a[rng.integers(0, a.size, size=a.size)])) for _ in range(n_boot)]
        lo, hi = np.quantile(boots, [0.025, 0.975])
        out["clocks"][n] = {
            "n": int(a.size),
            "median": float(np.median(a)),
            "mean": float(np.mean(a)),
            "std": float(np.std(a, ddof=1)) if a.size > 1 else float("nan"),
            "ci95": [float(lo), float(hi)],
        }
    for i, a_name in enumerate(names):
        for b_name in names[i + 1 :]:
            a, b = series[a_name], series[b_name]
            n = min(a.size, b.size)
            if n < 3:
                out["pairs"][f"{a_name}_minus_{b_name}"] = {"n": int(n), "median_diff": float("nan")}
                continue
            d = a[:n] - b[:n]
            boots = [float(np.median(d[rng.integers(0, n, size=n)])) for _ in range(n_boot)]
            lo, hi = np.quantile(boots, [0.025, 0.975])
            out["pairs"][f"{a_name}_minus_{b_name}"] = {
                "n": int(n),
                "median_diff": float(np.median(d)),
                "mean_diff": float(np.mean(d)),
                "ci95": [float(lo), float(hi)],
                "ci_excludes_0": bool(lo > 0 or hi < 0),
            }
    return out


def signature_rv_curve(
    log_px: NDArray[np.float64],
    steps: tuple[int, ...] = (1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900),
) -> dict[str, Any]:
    """Classical signature plot: sparse RV vs sampling step (seconds on 1s grid).

    Under microstructure noise, RV explodes as step→1; under pure diffusion it is
    flat in expectation. Slope of log(RV) vs log(step) on the fine end proxies
    noise dominance.
    """
    x = np.asarray(log_px, dtype=np.float64)
    steps_u = sorted({max(int(s), 1) for s in steps})
    rv: list[float] = []
    used: list[int] = []
    for s in steps_u:
        if x.size < s + 1:
            continue
        v = fourth_best(x, s)
        if np.isfinite(v):
            rv.append(float(v))
            used.append(int(s))
    slope = float("nan")
    if len(used) >= 3:
        # fine-end slope: first half of steps (noise-dominated region)
        n_half = max(3, len(used) // 2)
        lx = np.log(np.asarray(used[:n_half], dtype=np.float64))
        ly = np.log(np.maximum(np.asarray(rv[:n_half], dtype=np.float64), 1e-18))
        if np.std(lx) > 0:
            slope = float(np.polyfit(lx, ly, 1)[0])
    return {
        "steps": used,
        "rv": rv,
        "fine_log_slope": slope,
        "rv_1s": float(rv[0]) if used and used[0] == 1 else float("nan"),
        "rv_300s": float(rv[used.index(300)]) if 300 in used else float("nan"),
    }


def noise_return_acf(
    log_px: NDArray[np.float64],
    *,
    max_lag: int = 20,
) -> dict[str, Any]:
    """ACF of 1-step log returns — MA(1)-like noise ⇒ large negative lag-1.

    Under ZMA05 i.i.d. noise, Corr(ΔY_t, ΔY_{t+1}) ≈ −Eε² / (Eε² + …) < 0.
    """
    r = log_returns(log_px)
    max_lag = max(int(max_lag), 1)
    if r.size < max_lag + 5:
        return {
            "acf": [],
            "lag1": float("nan"),
            "ma1_compatible": False,
            "n": float(r.size),
        }
    r = r - float(np.mean(r))
    var = float(np.dot(r, r) / r.size)
    if not np.isfinite(var) or var <= 0:
        return {"acf": [], "lag1": float("nan"), "ma1_compatible": False, "n": float(r.size)}
    acf: list[float] = []
    for lag in range(1, max_lag + 1):
        c = float(np.dot(r[:-lag], r[lag:]) / r.size)
        acf.append(c / var)
    lag1 = float(acf[0]) if acf else float("nan")
    return {
        "acf": acf,
        "lag1": lag1,
        "ma1_compatible": bool(np.isfinite(lag1) and lag1 < -0.05),
        "n": float(r.size),
    }


def optimal_K_scan(
    log_px: NDArray[np.float64],
    *,
    step: int = 300,
    Ks: tuple[int, ...] = (30, 60, 120, 180, 300, 450, 600),
) -> dict[str, Any]:
    """TSRV first_adj vs K at fixed sparse step — bias/variance trade-off scan."""
    x = np.asarray(log_px, dtype=np.float64)
    step = max(int(step), 1)
    rows: list[dict[str, float]] = []
    for K in Ks:
        if x.size < step + 2:
            continue
        est = all_estimators(x, K=int(K), step=step)
        rows.append(
            {
                "K": float(K),
                "first_adj": float(est["first_adj"]),
                "second": float(est["second"]),
                "fourth": float(est["fourth"]),
            }
        )
    firsts = np.asarray([r["first_adj"] for r in rows if np.isfinite(r["first_adj"])], dtype=np.float64)
    # pick K minimizing |first_adj - median(first_adj)| as stability proxy (no true IV)
    best_K = float("nan")
    if firsts.size and rows:
        med = float(np.median(firsts))
        best = min(rows, key=lambda r: abs(r["first_adj"] - med) if np.isfinite(r["first_adj"]) else 1e99)
        best_K = float(best["K"])
    return {"grid": rows, "best_K_stability": best_K, "step": float(step)}


def k_step_ablation(
    log_px: NDArray[np.float64],
    *,
    Ks: tuple[int, ...] = (60, 150, 300),
    steps: tuple[int, ...] = (60, 300, 600),
) -> dict[str, Any]:
    """Scan (K, step) → first_adj and noise_std; flag fragility if CV of first_adj large."""
    x = np.asarray(log_px, dtype=np.float64)
    grid: list[dict[str, float]] = []
    firsts: list[float] = []
    noises: list[float] = []
    for K in Ks:
        for step in steps:
            if x.size < step + 2:
                continue
            est = all_estimators(x, K=int(K), step=int(step))
            nv = noise_variance_proxy(log_returns(x))
            row = {
                "K": float(K),
                "step": float(step),
                "first_adj": float(est["first_adj"]),
                "fourth": float(est["fourth"]),
                "fifth": float(est["fifth"]),
                "noise_std": float(nv["noise_std"]),
            }
            grid.append(row)
            if np.isfinite(row["first_adj"]):
                firsts.append(row["first_adj"])
            if np.isfinite(row["noise_std"]):
                noises.append(row["noise_std"])
    firsts_a = np.asarray(firsts, dtype=np.float64)
    noises_a = np.asarray(noises, dtype=np.float64)
    def _cv(a: NDArray[np.float64]) -> float:
        if a.size < 2 or not np.isfinite(a).all():
            return float("nan")
        mu = float(np.mean(a))
        return float(np.std(a) / abs(mu)) if abs(mu) > 1e-18 else float("nan")
    return {
        "grid": grid,
        "first_adj_cv": _cv(firsts_a),
        "noise_std_cv": _cv(noises_a),
        "first_adj_range": [float(np.min(firsts_a)), float(np.max(firsts_a))] if firsts_a.size else [float("nan"), float("nan")],
        "fragile_first_adj": bool(np.isfinite(_cv(firsts_a)) and _cv(firsts_a) > 0.5),
        "Ks": list(Ks),
        "steps": list(steps),
    }
