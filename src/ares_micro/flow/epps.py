"""Epps effect: correlation vs sampling lag."""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from ares_micro.core.arrays import log_returns_on_grid
from ares_micro.core.constants import NS_PER_S
from ares_micro.stats import pearson_r


def corr_vs_lag(
    ts_a: NDArray[np.int64],
    px_a: NDArray[np.float64],
    ts_b: NDArray[np.int64],
    px_b: NDArray[np.float64],
    *,
    lags_s: tuple[float, ...] = (1.0, 5.0, 15.0, 60.0, 300.0, 600.0),
    window_s: float | None = None,
) -> dict[str, Any]:
    """Pearson corr of log-returns at successive sampling lags (Epps curve).

    Implementation sketch: last-price sync on a regular grid of step = lag;
    corr of contemporaneous log-returns. Latency: assumes comparable clocks.
    """
    ta = np.asarray(ts_a, dtype=np.int64)
    tb = np.asarray(ts_b, dtype=np.int64)
    t0 = int(max(ta.min(), tb.min()))
    t1 = int(min(ta.max(), tb.max()))
    if window_s is not None:
        t1 = min(t1, t0 + int(window_s * NS_PER_S))
    rows = []
    for lag in lags_s:
        step = int(lag * NS_PER_S)
        if step <= 0 or t1 - t0 < 3 * step:
            rows.append({"lag_s": float(lag), "corr": float("nan"), "n": 0})
            continue
        grid = np.arange(t0, t1 + 1, step, dtype=np.int64)
        ra = log_returns_on_grid(ta, px_a, grid)
        rb = log_returns_on_grid(tb, px_b, grid)
        m = np.isfinite(ra) & np.isfinite(rb)
        n = int(m.sum())
        if n < 5:
            rows.append({"lag_s": float(lag), "corr": float("nan"), "n": n})
            continue
        rows.append({"lag_s": float(lag), "corr": pearson_r(ra[m], rb[m]), "n": n})
    return {"curve": rows}
