"""Epps effect: correlation vs sampling lag."""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray


def _logret_on_grid(
    ts_ns: NDArray[np.int64],
    px: NDArray[np.float64],
    grid_ns: NDArray[np.int64],
) -> NDArray[np.float64]:
    """Last-price on grid then log-return; NaN where empty."""
    t = np.asarray(ts_ns, dtype=np.int64)
    p = np.asarray(px, dtype=np.float64)
    idx = np.searchsorted(t, grid_ns, side="right") - 1
    out = np.full(grid_ns.shape, np.nan)
    ok = (idx >= 0) & (idx < t.size)
    out[ok] = p[idx[ok]]
    # forward-fill gaps already via last-price; drop leading NaNs in ret
    lr = np.full_like(out, np.nan)
    valid = np.isfinite(out)
    # pairwise consecutive finite
    for i in range(1, out.size):
        if valid[i] and valid[i - 1] and out[i - 1] > 0 and out[i] > 0:
            lr[i] = np.log(out[i] / out[i - 1])
    return lr


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
        t1 = min(t1, t0 + int(window_s * 1e9))
    rows = []
    for lag in lags_s:
        step = int(lag * 1e9)
        if step <= 0 or t1 - t0 < 3 * step:
            rows.append({"lag_s": float(lag), "corr": float("nan"), "n": 0})
            continue
        grid = np.arange(t0, t1 + 1, step, dtype=np.int64)
        ra = _logret_on_grid(ta, px_a, grid)
        rb = _logret_on_grid(tb, px_b, grid)
        m = np.isfinite(ra) & np.isfinite(rb)
        n = int(m.sum())
        if n < 5:
            rows.append({"lag_s": float(lag), "corr": float("nan"), "n": n})
            continue
        x, y = ra[m], rb[m]
        x = x - x.mean()
        y = y - y.mean()
        den = float(np.sqrt((x * x).sum() * (y * y).sum()))
        c = float((x * y).sum() / den) if den > 0 else float("nan")
        rows.append({"lag_s": float(lag), "corr": c, "n": n})
    return {"curve": rows}
