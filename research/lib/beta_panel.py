"""β / idiosyncratic variance panel helpers."""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray


def ols_beta(
    y: NDArray[np.float64],
    x: NDArray[np.float64],
) -> dict[str, float]:
    """Simple OLS: y = α + β x. Pairwise complete observations."""
    a = np.asarray(y, dtype=np.float64)
    b = np.asarray(x, dtype=np.float64)
    m = np.isfinite(a) & np.isfinite(b)
    a, b = a[m], b[m]
    n = int(a.size)
    if n < 3:
        return {"n": n, "alpha": float("nan"), "beta": float("nan"), "r2": float("nan")}
    b0 = b - b.mean()
    a0 = a - a.mean()
    den = float((b0 * b0).sum())
    if den <= 0:
        return {"n": n, "alpha": float("nan"), "beta": float("nan"), "r2": float("nan")}
    beta = float((b0 * a0).sum() / den)
    alpha = float(a.mean() - beta * b.mean())
    resid = a - (alpha + beta * b)
    ss_tot = float(((a - a.mean()) ** 2).sum())
    ss_res = float((resid ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return {"n": n, "alpha": alpha, "beta": beta, "r2": float(r2)}


def variance_shares(
    y: NDArray[np.float64],
    x: NDArray[np.float64],
    beta: float | None = None,
) -> dict[str, Any]:
    """Systematic vs idiosyncratic variance shares for y vs factor x.

    If ``beta`` is None, fit OLS β first. sys = β² Var(x) / Var(y), idio = 1 − sys
    (clipped). Desk use: inventory hedging capacity / residual risk budget.
    """
    a = np.asarray(y, dtype=np.float64)
    b = np.asarray(x, dtype=np.float64)
    m = np.isfinite(a) & np.isfinite(b)
    a, b = a[m], b[m]
    if a.size < 3:
        return {"n": int(a.size), "sys_share": float("nan"), "idio_share": float("nan")}
    if beta is None:
        beta = ols_beta(a, b)["beta"]
    vy = float(np.var(a))
    vx = float(np.var(b))
    if not np.isfinite(beta) or vy <= 0:
        return {"n": int(a.size), "sys_share": float("nan"), "idio_share": float("nan"), "beta": beta}
    sys = float((beta ** 2) * vx / vy)
    sys = float(np.clip(sys, 0.0, 1.0))
    return {
        "n": int(a.size),
        "beta": float(beta),
        "sys_share": sys,
        "idio_share": float(1.0 - sys),
        "var_y": vy,
        "var_x": vx,
    }
