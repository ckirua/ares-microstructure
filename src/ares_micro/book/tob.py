"""TOB helpers: mid, tick inference, imbalance, post-trade resilience."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from ares_micro.core.arrays import asof_idx
from ares_micro.core.constants import NS_PER_MS


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


def median_tick(prices: NDArray[np.float64], *, fallback: float = 1e-8) -> float:
    """Median |Δp| tick proxy from a price path (desk fallback, not exchange tick)."""
    p = np.asarray(prices, dtype=np.float64)
    if p.size < 3:
        return float(fallback)
    d = np.diff(p)
    d = d[np.isfinite(d) & (np.abs(d) > 0)]
    if d.size == 0:
        return float(fallback)
    t = float(np.median(np.abs(d)))
    return t if t > 0 else float(fallback)


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

    i0 = asof_idx(ev, t)
    for h_ms in horizons_ms:
        h_ns = int(h_ms) * NS_PER_MS
        i1 = asof_idx(ev + h_ns, t)
        ok = (i0 >= 0) & (i1 > i0) & (i1 < t.size)
        if not np.any(ok):
            out["mean_depth_ratio"].append(float("nan"))
            out["mean_abs_mid_bps"].append(float("nan"))
            out["n_events"].append(0)
            continue
        i0v, i1v = i0[ok], i1[ok]
        d0, d1 = d[i0v], d[i1v]
        m0, m1 = m[i0v], m[i1v]
        ok2 = (
            np.isfinite(d0)
            & (d0 > 0)
            & np.isfinite(d1)
            & np.isfinite(m0)
            & np.isfinite(m1)
            & (m0 > 0)
        )
        if not np.any(ok2):
            out["mean_depth_ratio"].append(float("nan"))
            out["mean_abs_mid_bps"].append(float("nan"))
            out["n_events"].append(0)
            continue
        ratios = d1[ok2] / d0[ok2]
        mid_moves = 1e4 * np.abs(m1[ok2] - m0[ok2]) / m0[ok2]
        out["mean_depth_ratio"].append(float(np.mean(ratios)))
        out["mean_abs_mid_bps"].append(float(np.mean(mid_moves)))
        out["n_events"].append(int(ok2.sum()))
    return out
