"""POV (participation-of-volume) child-order simulation sketch."""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray


def simulate_pov_child(
    trade_ts_ns: NDArray[np.int64],
    trade_px: NDArray[np.float64],
    trade_qty: NDArray[np.float64],
    *,
    target_participation: float = 0.05,
    side: int = 1,
    max_child_qty: float | None = None,
) -> dict[str, Any]:
    """Simulate a POV child that takes ``π`` of each tape print (paper).

    Assumptions (latency / microstructure honesty):
    - Instant fill at trade price (no queue; taker).
    - No self-impact feedback into the tape.
    - Participation measured vs contemporaneous print size, not vs ADV.

    Returns filled qty, VWAP, arrival mid proxy (first trade), and impact-ish
    metric 1e4 · side · (vwap − arrival) / arrival.
    """
    ts = np.asarray(trade_ts_ns, dtype=np.int64)
    px = np.asarray(trade_px, dtype=np.float64)
    qty = np.asarray(trade_qty, dtype=np.float64)
    pi = float(target_participation)
    if ts.size == 0 or pi <= 0:
        return {"n_fills": 0, "filled_qty": 0.0, "vwap": float("nan"), "impact_bps": float("nan")}
    child = pi * qty
    if max_child_qty is not None:
        child = np.minimum(child, float(max_child_qty))
    filled = float(child.sum())
    if filled <= 0:
        return {"n_fills": 0, "filled_qty": 0.0, "vwap": float("nan"), "impact_bps": float("nan")}
    vwap = float((child * px).sum() / filled)
    arrival = float(px[0])
    impact = float(1e4 * side * (vwap - arrival) / arrival) if arrival > 0 else float("nan")
    return {
        "n_fills": int((child > 0).sum()),
        "filled_qty": filled,
        "vwap": vwap,
        "arrival_px": arrival,
        "impact_bps": impact,
        "participation": pi,
        "side": int(side),
    }
