"""Spread definitions: quoted, effective, realized, Roll."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from ares_micro.book.tob import mid_price


def quoted_spread_bps(
    bid: NDArray[np.float64],
    ask: NDArray[np.float64],
    *,
    mid: NDArray[np.float64] | None = None,
) -> NDArray[np.float64]:
    """Quoted spread in bps: 1e4 · (ask − bid) / mid.

    Column def: per-quote row; update frequency = quote stream cadence.
    Latency: assumes bid/ask are simultaneous (same exchange timestamp).
    """
    b = np.asarray(bid, dtype=np.float64)
    a = np.asarray(ask, dtype=np.float64)
    m = mid_price(b, a) if mid is None else np.asarray(mid, dtype=np.float64)
    out = np.full_like(m, np.nan)
    ok = (m > 0) & np.isfinite(m) & np.isfinite(b) & np.isfinite(a)
    out[ok] = 1e4 * (a[ok] - b[ok]) / m[ok]
    return out


def effective_spread_bps(
    trade_px: NDArray[np.float64],
    mid: NDArray[np.float64],
    side: NDArray[np.int8] | NDArray[np.float64],
) -> NDArray[np.float64]:
    """Effective spread (bps): 2 · 1e4 · side · (p − mid) / mid.

    ``side`` is +1 for buyer-initiated (lift ask), −1 for seller-initiated.
    Mid should be the prevailing quote mid at trade time (as-of join).
    """
    p = np.asarray(trade_px, dtype=np.float64)
    m = np.asarray(mid, dtype=np.float64)
    s = np.asarray(side, dtype=np.float64)
    out = np.full_like(p, np.nan)
    ok = (m > 0) & np.isfinite(p) & np.isfinite(m) & np.isfinite(s) & (s != 0)
    out[ok] = 2.0 * 1e4 * s[ok] * (p[ok] - m[ok]) / m[ok]
    return out


def realized_spread_bps(
    trade_px: NDArray[np.float64],
    mid_future: NDArray[np.float64],
    side: NDArray[np.int8] | NDArray[np.float64],
) -> NDArray[np.float64]:
    """Realized spread (bps): 2 · 1e4 · side · (p − mid_{t+Δ}) / mid_{t+Δ}.

    Maker revenue proxy after adverse selection over horizon Δ.
    Falsifier: if mean realized ≈ quoted and markout≈0, toxicity is weak.
    Same arithmetic as ``effective_spread_bps`` with the horizon mid.
    """
    return effective_spread_bps(trade_px, mid_future, side)


def roll_acov(returns: NDArray[np.float64]) -> dict[str, float]:
    """Roll (1984) autocovariance objects: ``g0=Var(Δp)``, ``g1=Cov(Δp_t,Δp_{t-1})``.

    Also reports ``c=√(−g1)`` and ``spread_2c=2c`` when identified (g1 < 0).
    """
    r = np.asarray(returns, dtype=np.float64)
    r = r[np.isfinite(r)]
    out = {
        "n": float(r.size),
        "g0": float("nan"),
        "g1": float("nan"),
        "c": float("nan"),
        "spread_2c": float("nan"),
        "identified": 0.0,
    }
    if r.size < 3:
        return out
    g0 = float(np.var(r))
    g1 = float(np.cov(r[1:], r[:-1])[0, 1])
    out["g0"], out["g1"] = g0, g1
    if g1 >= 0:
        return out
    c = float(np.sqrt(-g1))
    out.update({"c": c, "spread_2c": 2.0 * c, "identified": 1.0})
    return out


def roll_implied_spread(returns: NDArray[np.float64]) -> float:
    """Roll (1984) implied spread 2√(−cov(Δp_t, Δp_{t−1})) in price units.

    Uses first-difference of mid or trade prices. Returns NaN if cov ≥ 0
    (no negative serial covariance → Roll not identified).
    """
    return float(roll_acov(returns)["spread_2c"])
