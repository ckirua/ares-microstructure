"""Shared microstructure research helpers (desk-grade, importable from notebooks/scripts).

Usage from repo root::

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path('.../ares-microstructure')))
    from research.lib import fei, quoted_spread_bps, trade_markouts
"""

from __future__ import annotations

from research.lib.beta_panel import ols_beta, variance_shares
from research.lib.epps import corr_vs_lag
from research.lib.fei import entropy, fei
from research.lib.markout import adverse_selection_table, trade_markouts
from research.lib.pov import simulate_pov_child
from research.lib.spreads import (
    effective_spread_bps,
    quoted_spread_bps,
    realized_spread_bps,
    roll_implied_spread,
)
from research.lib.stats import (
    bootstrap_ci,
    pearson_r_ci,
    spearman_r,
    time_split_mask,
)
from research.lib.tob import (
    depth_imbalance,
    infer_tick,
    mid_price,
    tob_resilience,
)

__all__ = [
    "adverse_selection_table",
    "bootstrap_ci",
    "corr_vs_lag",
    "depth_imbalance",
    "effective_spread_bps",
    "entropy",
    "fei",
    "infer_tick",
    "mid_price",
    "ols_beta",
    "pearson_r_ci",
    "quoted_spread_bps",
    "realized_spread_bps",
    "roll_implied_spread",
    "simulate_pov_child",
    "spearman_r",
    "time_split_mask",
    "tob_resilience",
    "trade_markouts",
    "variance_shares",
]
