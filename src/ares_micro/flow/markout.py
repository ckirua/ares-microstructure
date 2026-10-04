"""Adverse selection / markout by side and size (maker toxicity proxy)."""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from ares_micro.core.arrays import asof_idx, asof_join
from ares_micro.core.constants import NS_PER_MS
from ares_micro.stats import bootstrap_ci


def trade_markouts(
    trade_ts_ns: NDArray[np.int64],
    trade_px: NDArray[np.float64],
    side: NDArray[np.int8] | NDArray[np.float64],
    mid_ts_ns: NDArray[np.int64],
    mid: NDArray[np.float64],
    *,
    horizons_ms: tuple[int, ...] = (100, 500, 1000, 5000, 30000),
) -> dict[str, Any]:
    """Signed markout in bps: side · 1e4 · (mid_{t+h} − mid_t) / mid_t.

    Positive markout ⇒ price moved *with* the aggressor ⇒ adverse for the
    resting maker on the opposite side.

    ``side``: +1 buy aggressor, −1 sell aggressor (map 0→nan).
    Mid path must be sorted by ``mid_ts_ns``. Latency assumption: mid and trade
    clocks are comparable (same venue exchange time preferred).
    """
    tt = np.asarray(trade_ts_ns, dtype=np.int64)
    s = np.asarray(side, dtype=np.float64)
    s = np.where(s == 0, np.nan, s)
    mt = np.asarray(mid_ts_ns, dtype=np.int64)
    mv = np.asarray(mid, dtype=np.float64)

    i0 = asof_idx(tt, mt)
    mid0 = asof_join(tt, mt, mv)
    valid0 = np.isfinite(mid0)

    per_h: dict[str, Any] = {"horizons_ms": list(horizons_ms), "by_horizon": {}}
    for h_ms in horizons_ms:
        h_ns = int(h_ms) * NS_PER_MS
        i1 = asof_idx(tt + h_ns, mt)
        mid1 = asof_join(tt + h_ns, mt, mv)
        valid = valid0 & (i1 > i0) & np.isfinite(s) & (mid0 > 0) & np.isfinite(mid1)
        mo = np.full(tt.size, np.nan)
        mo[valid] = s[valid] * 1e4 * (mid1[valid] - mid0[valid]) / mid0[valid]
        sample = mo[np.isfinite(mo)]
        ci = bootstrap_ci(sample, n_boot=500, seed=7)
        per_h["by_horizon"][str(h_ms)] = {
            "n": int(sample.size),
            "mean_bps": ci["point"],
            "ci95": [ci["lo"], ci["hi"]],
            "p50_bps": float(np.median(sample)) if sample.size else float("nan"),
        }
    per_h["n_trades"] = int(tt.size)
    per_h["n_with_mid"] = int(np.isfinite(mid0).sum())
    return per_h


def adverse_selection_table(
    markouts_1s: NDArray[np.float64],
    side: NDArray[np.int8] | NDArray[np.float64],
    notional: NDArray[np.float64],
    *,
    size_quantiles: tuple[float, ...] = (0.25, 0.5, 0.75),
) -> dict[str, Any]:
    """Mean 1s markout by aggressor side and notional quartile.

    Desk use: widen / skew when large-buy markouts ≫ small, or kill size tiers
    that are systematically toxic.
    """
    mo = np.asarray(markouts_1s, dtype=np.float64)
    s = np.asarray(side, dtype=np.float64)
    n = np.asarray(notional, dtype=np.float64)
    m = np.isfinite(mo) & np.isfinite(s) & np.isfinite(n) & (n > 0) & (s != 0)
    mo, s, n = mo[m], s[m], n[m]
    out: dict[str, Any] = {"n": int(mo.size), "by_side": {}, "by_size_q": {}}
    for label, mask in (("buy", s > 0), ("sell", s < 0)):
        sub = mo[mask]
        ci = bootstrap_ci(sub, n_boot=500, seed=11)
        out["by_side"][label] = {
            "n": int(sub.size),
            "mean_bps": ci["point"],
            "ci95": [ci["lo"], ci["hi"]],
        }
    if mo.size >= 8:
        edges = np.quantile(n, (0.0,) + size_quantiles + (1.0,))
        for i in range(len(edges) - 1):
            lo, hi = edges[i], edges[i + 1]
            mask = (n >= lo) & (n <= hi if i == len(edges) - 2 else n < hi)
            sub = mo[mask]
            ci = bootstrap_ci(sub, n_boot=400, seed=13 + i)
            out["by_size_q"][f"q{i}"] = {
                "n": int(sub.size),
                "notional_lo": float(lo),
                "notional_hi": float(hi),
                "mean_bps": ci["point"],
                "ci95": [ci["lo"], ci["hi"]],
            }
    return out
