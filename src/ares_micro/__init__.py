"""ares-microstructure package — thin re-export of research.lib for installed use."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from research.lib import (  # noqa: E402
    bootstrap_ci,
    entropy,
    fei,
    infer_tick,
    mid_price,
    quoted_spread_bps,
    spearman_r,
)

__all__ = [
    "bootstrap_ci",
    "entropy",
    "fei",
    "infer_tick",
    "mid_price",
    "quoted_spread_bps",
    "spearman_r",
]
