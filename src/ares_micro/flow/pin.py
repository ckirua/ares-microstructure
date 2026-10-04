"""Easley–Hvidkjaer–O'Hara (EHO) PIN MLE and day-level buy/sell utilities.

Hasbrouck *Empirical Market Microstructure* Ch.15 / EHO (2002).
Each UTC (or labeled) day is one observation of (B, S) counts.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
from numpy.typing import NDArray

from ares_micro.core.constants import NS_PER_S


def daily_buy_sell_counts(
    ts_ns: NDArray[np.int64],
    side: NDArray[np.float64] | NDArray[np.int8],
    *,
    day_labels: Sequence[str] | None = None,
) -> dict[str, dict[str, float]]:
    """Per-UTC-day buy/sell counts (PIN likelihood inputs).

    If ``day_labels`` is provided with the same length as ``ts_ns``, counts are
    grouped by those labels instead of UTC epoch days (useful for warehouse day
    tags when the tape is incomplete within the UTC day).
    """
    ts = np.asarray(ts_ns, dtype=np.int64)
    s = np.asarray(side, dtype=np.float64)
    m = np.isfinite(s) & (s != 0) & np.isfinite(ts)
    ts, s = ts[m], s[m]
    out: dict[str, dict[str, float]] = {}
    if ts.size == 0:
        return out
    if day_labels is not None:
        keys = np.asarray(list(day_labels), dtype=object)[m]
    else:
        keys = (ts // NS_PER_S) // 86_400
    uniq, inv = np.unique(keys, return_inverse=True)
    B = np.bincount(inv, weights=(s > 0).astype(np.float64)).astype(np.int64)
    S = np.bincount(inv, weights=(s < 0).astype(np.float64)).astype(np.int64)
    n = np.bincount(inv)
    ts_min = np.full(uniq.shape, np.iinfo(np.int64).max, dtype=np.int64)
    ts_max = np.full(uniq.shape, np.iinfo(np.int64).min, dtype=np.int64)
    np.minimum.at(ts_min, inv, ts)
    np.maximum.at(ts_max, inv, ts)
    for i, k in enumerate(uniq):
        ni = int(n[i])
        bi, si = int(B[i]), int(S[i])
        t0, t1 = int(ts_min[i]), int(ts_max[i])
        out[str(k)] = {
            "B": bi,
            "S": si,
            "n": ni,
            "imb": float(bi - si) / max(ni, 1),
            "ts_min": t0,
            "ts_max": t1,
            "span_h": float((t1 - t0) / NS_PER_S / 3600.0),
        }
    return out


def pin_proxy_from_days(days_bs: dict[str, dict[str, float]]) -> dict[str, float]:
    """Descriptive stand-in: E[|B−S| / (B+S)] without full MLE."""
    if not days_bs:
        return {
            "n_days": 0,
            "pin_proxy": float("nan"),
            "mean_abs_imb": float("nan"),
            "mean_B": float("nan"),
            "mean_S": float("nan"),
        }
    Bs = np.array([v["B"] for v in days_bs.values()], dtype=np.float64)
    Ss = np.array([v["S"] for v in days_bs.values()], dtype=np.float64)
    imbs = np.array([v["imb"] for v in days_bs.values()], dtype=np.float64)
    pin_hat = float(np.mean(np.abs(Bs - Ss) / np.maximum(Bs + Ss, 1.0)))
    return {
        "n_days": int(len(days_bs)),
        "pin_proxy": pin_hat,
        "mean_abs_imb": float(np.mean(np.abs(imbs))),
        "mean_B": float(np.mean(Bs)),
        "mean_S": float(np.mean(Ss)),
    }


def _poisson_logpmf(n: NDArray[np.float64], lam: float) -> NDArray[np.float64]:
    """log P(N=n | Poisson(λ)) via Stirling — stable for large n, λ."""
    lam = float(max(lam, 1e-12))
    n = np.asarray(n, dtype=np.float64)
    # log(n!) ≈ n log n − n + 0.5 log(2πn) for n≥1; 0 for n=0
    log_fact = np.zeros_like(n)
    pos = n >= 1.0
    nn = n[pos]
    log_fact[pos] = nn * np.log(nn) - nn + 0.5 * np.log(2.0 * np.pi * nn)
    # small-n exact-ish correction via scipy if available
    try:
        from scipy.special import gammaln

        log_fact = gammaln(n + 1.0)
    except Exception:  # noqa: BLE001
        pass
    return -lam + n * np.log(lam) - log_fact


def _day_loglik(
    B: NDArray[np.float64],
    S: NDArray[np.float64],
    alpha: float,
    delta: float,
    eps_b: float,
    eps_s: float,
    mu: float,
) -> float:
    """Sum of log mixture densities (Hasbrouck 15.a.2)."""
    a = float(np.clip(alpha, 1e-8, 1.0 - 1e-8))
    d = float(np.clip(delta, 1e-8, 1.0 - 1e-8))
    eb = float(max(eps_b, 1e-8))
    es = float(max(eps_s, 1e-8))
    m = float(max(mu, 1e-8))

    # three regime log-weights + log joint poisson
    log_w0 = np.log(1.0 - a)
    log_w1 = np.log(a) + np.log(d)
    log_w2 = np.log(a) + np.log(1.0 - d)

    ll0 = log_w0 + _poisson_logpmf(B, eb) + _poisson_logpmf(S, es)
    ll1 = log_w1 + _poisson_logpmf(B, eb + m) + _poisson_logpmf(S, es)
    ll2 = log_w2 + _poisson_logpmf(B, eb) + _poisson_logpmf(S, es + m)

    # log-sum-exp across regimes per day
    stacked = np.vstack([ll0, ll1, ll2])
    mx = np.max(stacked, axis=0)
    ll = mx + np.log(np.exp(stacked - mx).sum(axis=0))
    return float(np.sum(ll))


def pin_from_params(
    alpha: float,
    mu: float,
    eps_b: float,
    eps_s: float,
) -> float:
    """PIN = αμ / (αμ + ε_B + ε_S)."""
    num = float(alpha) * float(mu)
    den = num + float(eps_b) + float(eps_s)
    return float(num / den) if den > 0 else float("nan")


def eho_pin_mle(
    days_bs: dict[str, dict[str, float]],
    *,
    symmetric: bool = False,
    delta_fixed: float | None = 0.5,
    min_trades_per_day: int = 200,
    min_span_h: float = 4.0,
) -> dict[str, Any]:
    """Full EHO-style MLE on day-level (B, S).

    Parameters
    ----------
    symmetric
        If True, constrain ε_B = ε_S.
    delta_fixed
        If not None, fix δ (Hasbrouck often uses 1/2).
    min_trades_per_day / min_span_h
        Filters for "usable" days when tape is incomplete.

    Returns decision-ready dict with PIN, params, n_days, success flag.
    """
    rows = []
    for key, v in days_bs.items():
        if int(v.get("n", 0)) < min_trades_per_day:
            continue
        if float(v.get("span_h", 24.0)) < min_span_h:
            continue
        rows.append((key, float(v["B"]), float(v["S"]), float(v.get("span_h", 24.0))))
    out: dict[str, Any] = {
        "ok": False,
        "n_days": 0,
        "n_days_raw": int(len(days_bs)),
        "PIN": float("nan"),
        "alpha": float("nan"),
        "delta": float("nan"),
        "eps_b": float("nan"),
        "eps_s": float("nan"),
        "mu": float("nan"),
        "loglik": float("nan"),
        "symmetric": symmetric,
        "delta_fixed": delta_fixed,
        "day_keys": [],
        "message": "insufficient days",
    }
    if len(rows) < 3:
        out["message"] = f"only {len(rows)} usable days after filters"
        return out

    keys = [r[0] for r in rows]
    B = np.array([r[1] for r in rows], dtype=np.float64)
    S = np.array([r[2] for r in rows], dtype=np.float64)
    out["n_days"] = int(len(rows))
    out["day_keys"] = keys
    out["mean_B"] = float(np.mean(B))
    out["mean_S"] = float(np.mean(S))
    out["mean_abs_imb"] = float(np.mean(np.abs(B - S) / np.maximum(B + S, 1.0)))

    # MOM-style starts
    eps0 = float(max(np.median(np.minimum(B, S)), 1.0))
    mu0 = float(max(np.median(np.abs(B - S)), 1.0))
    alpha0 = 0.3
    delta0 = 0.5 if delta_fixed is None else float(delta_fixed)

    try:
        from scipy.optimize import minimize
    except ImportError:
        out["message"] = "scipy required for MLE"
        return out

    if symmetric and delta_fixed is not None:
        # θ = (logit α, log ε, log μ)
        def unpack(x: NDArray[np.float64]) -> tuple[float, float, float, float, float]:
            a = 1.0 / (1.0 + np.exp(-x[0]))
            e = float(np.exp(x[1]))
            m = float(np.exp(x[2]))
            return a, float(delta_fixed), e, e, m

        x0 = np.array(
            [np.log(alpha0 / (1 - alpha0)), np.log(eps0), np.log(mu0)],
            dtype=np.float64,
        )
    elif symmetric:
        # θ = (logit α, logit δ, log ε, log μ)
        def unpack(x: NDArray[np.float64]) -> tuple[float, float, float, float, float]:
            a = 1.0 / (1.0 + np.exp(-x[0]))
            d = 1.0 / (1.0 + np.exp(-x[1]))
            e = float(np.exp(x[2]))
            m = float(np.exp(x[3]))
            return a, d, e, e, m

        x0 = np.array(
            [
                np.log(alpha0 / (1 - alpha0)),
                np.log(delta0 / (1 - delta0)),
                np.log(eps0),
                np.log(mu0),
            ],
            dtype=np.float64,
        )
    elif delta_fixed is not None:
        # θ = (logit α, log εb, log εs, log μ)
        def unpack(x: NDArray[np.float64]) -> tuple[float, float, float, float, float]:
            a = 1.0 / (1.0 + np.exp(-x[0]))
            eb = float(np.exp(x[1]))
            es = float(np.exp(x[2]))
            m = float(np.exp(x[3]))
            return a, float(delta_fixed), eb, es, m

        x0 = np.array(
            [
                np.log(alpha0 / (1 - alpha0)),
                np.log(max(np.median(B) * 0.7, 1.0)),
                np.log(max(np.median(S) * 0.7, 1.0)),
                np.log(mu0),
            ],
            dtype=np.float64,
        )
    else:
        def unpack(x: NDArray[np.float64]) -> tuple[float, float, float, float, float]:
            a = 1.0 / (1.0 + np.exp(-x[0]))
            d = 1.0 / (1.0 + np.exp(-x[1]))
            eb = float(np.exp(x[2]))
            es = float(np.exp(x[3]))
            m = float(np.exp(x[4]))
            return a, d, eb, es, m

        x0 = np.array(
            [
                np.log(alpha0 / (1 - alpha0)),
                np.log(delta0 / (1 - delta0)),
                np.log(max(np.median(B) * 0.7, 1.0)),
                np.log(max(np.median(S) * 0.7, 1.0)),
                np.log(mu0),
            ],
            dtype=np.float64,
        )

    def nll(x: NDArray[np.float64]) -> float:
        a, d, eb, es, m = unpack(x)
        ll = _day_loglik(B, S, a, d, eb, es, m)
        if not np.isfinite(ll):
            return 1e30
        return -ll

    best = None
    # multi-start for mixture identification
    rng = np.random.default_rng(17)
    starts = [x0]
    for _ in range(8):
        starts.append(x0 + rng.normal(0.0, 0.35, size=x0.shape))

    for st in starts:
        res = minimize(nll, st, method="L-BFGS-B", options={"maxiter": 400})
        if best is None or (res.success and res.fun < best.fun) or (
            best is not None and np.isfinite(res.fun) and res.fun < best.fun
        ):
            best = res

    if best is None or not np.isfinite(best.fun):
        out["message"] = "optimizer failed"
        return out

    a, d, eb, es, m = unpack(best.x)
    pin = pin_from_params(a, m, eb, es)
    out.update(
        {
            "ok": True,
            "PIN": pin,
            "alpha": float(a),
            "delta": float(d),
            "eps_b": float(eb),
            "eps_s": float(es),
            "mu": float(m),
            "loglik": float(-best.fun),
            "success": bool(best.success),
            "message": "ok" if best.success else f"converged_with_status={best.message}",
            "am_product": float(a * m),
        }
    )
    return out


def compare_pin_vpin(
    pin: dict[str, Any],
    vpin: dict[str, Any],
) -> dict[str, Any]:
    """Honest side-by-side of day-mixture PIN vs volume-clock VPIN."""
    return {
        "pin": pin.get("PIN"),
        "pin_ok": bool(pin.get("ok")),
        "pin_n_days": pin.get("n_days"),
        "vpin_mean": vpin.get("mean_vpin"),
        "vpin_n_buckets": vpin.get("n_buckets"),
        "note": (
            "PIN is day-level mixture of informed vs uninformed Poisson flows; "
            "VPIN is volume-bucket |buy−sell|/V rolling mean — different clocks, "
            "not interchangeable levels."
        ),
    }
