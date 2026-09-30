"""TOB helpers: mid, tick inference, imbalance, post-trade resilience."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def mid_price(bid: NDArray[np.float64], ask: NDArray[np.float64]) -> NDArray[np.float64]:
    """Mid = (bid + ask) / 2."""
    return 0.5 * (np.asarray(bid, dtype=np.float64) + np.asarray(ask, dtype=np.float64))


def infer_tick(prices: NDArray[np.float64], *, min_diff: float = 1e-12) -> float:
    """Infer minimum positive price increment from observed best prices."""
    p = np.unique(np.round(np.asarray(prices, dtype=np.float64), 10))
    if p.size < 2:
        return float("nan")
    d = np.diff(np.sort(p))
    d = d[d > min_diff]
    if d.size == 0:
        return float("nan")
    return float(np.min(d))


def depth_imbalance(
    bid_sz: NDArray[np.float64],
    ask_sz: NDArray[np.float64],
) -> NDArray[np.float64]:
    """L0 imbalance (b − a) / (b + a) ∈ (−1, 1)."""
    b = np.asarray(bid_sz, dtype=np.float64)
    a = np.asarray(ask_sz, dtype=np.float64)
    den = b + a
    out = np.full_like(den, np.nan)
    ok = den > 0
    out[ok] = (b[ok] - a[ok]) / den[ok]
    return out


def tob_resilience(
    ts_ns: NDArray[np.int64],
    mid: NDArray[np.float64],
    depth: NDArray[np.float64],
    event_ts_ns: NDArray[np.int64],
    *,
    horizons_ms: tuple[int, ...] = (100, 500, 1000, 5000),
) -> dict[str, list[float]]:
    """Depth / mid recovery after event times (trades or large BBO jumps).

    For each event, compare depth and |Δmid| at t+h vs pre-event level.
    Requires TOB stream sorted by ``ts_ns``. Queue position is *not* observed
    on L0-only feeds — this is a resilience / refill proxy only.

    Update frequency: TOB cadence (collector ~ms; warehouse L2 rebuild ~seconds).
    """
    t = np.asarray(ts_ns, dtype=np.int64)
    m = np.asarray(mid, dtype=np.float64)
    d = np.asarray(depth, dtype=np.float64)
    ev = np.asarray(event_ts_ns, dtype=np.int64)
    out: dict[str, list[float]] = {
        "horizon_ms": list(horizons_ms),
        "mean_depth_ratio": [],
        "mean_abs_mid_bps": [],
        "n_events": [],
    }
    if t.size < 2 or ev.size == 0:
        for _ in horizons_ms:
            out["mean_depth_ratio"].append(float("nan"))
            out["mean_abs_mid_bps"].append(float("nan"))
            out["n_events"].append(0)
        return out

    for h_ms in horizons_ms:
        h_ns = int(h_ms) * 1_000_000
        ratios: list[float] = []
        mid_moves: list[float] = []
        for e in ev:
            i0 = int(np.searchsorted(t, e, side="right") - 1)
            if i0 < 0:
                continue
            i1 = int(np.searchsorted(t, e + h_ns, side="right") - 1)
            if i1 <= i0 or i1 >= t.size:
                continue
            d0 = d[i0]
            if not np.isfinite(d0) or d0 <= 0:
                continue
            d1 = d[i1]
            m0, m1 = m[i0], m[i1]
            if not (np.isfinite(d1) and np.isfinite(m0) and np.isfinite(m1) and m0 > 0):
                continue
            ratios.append(float(d1 / d0))
            mid_moves.append(float(1e4 * abs(m1 - m0) / m0))
        out["mean_depth_ratio"].append(float(np.mean(ratios)) if ratios else float("nan"))
        out["mean_abs_mid_bps"].append(float(np.mean(mid_moves)) if mid_moves else float("nan"))
        out["n_events"].append(len(ratios))
    return out
