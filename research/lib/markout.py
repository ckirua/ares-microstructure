"""Adverse selection / markout by side and size (maker toxicity proxy)."""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from research.lib.stats import bootstrap_ci


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
    px = np.asarray(trade_px, dtype=np.float64)
    s = np.asarray(side, dtype=np.float64)
    s = np.where(s == 0, np.nan, s)
    mt = np.asarray(mid_ts_ns, dtype=np.int64)
    mv = np.asarray(mid, dtype=np.float64)

    # prevailing mid at trade
    i0 = np.searchsorted(mt, tt, side="right") - 1
    valid0 = (i0 >= 0) & (i0 < mt.size)
    mid0 = np.full(tt.size, np.nan)
    mid0[valid0] = mv[i0[valid0]]

    per_h: dict[str, Any] = {"horizons_ms": list(horizons_ms), "by_horizon": {}}
    for h_ms in horizons_ms:
        h_ns = int(h_ms) * 1_000_000
        i1 = np.searchsorted(mt, tt + h_ns, side="right") - 1
        valid = valid0 & (i1 > i0) & (i1 < mt.size) & np.isfinite(s) & (mid0 > 0)
        mid1 = np.full(tt.size, np.nan)
        mid1[valid] = mv[i1[valid]]
        mo = np.full(tt.size, np.nan)
        ok = valid & np.isfinite(mid1)
        mo[ok] = s[ok] * 1e4 * (mid1[ok] - mid0[ok]) / mid0[ok]
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
