"""ares-micro — quant / market-microstructure research library.

Layout::

    ares_micro/
      core/    # generic array + RV helpers
      stats.py # bootstrap / CIs / splits
      book/    # TOB/LOB / spreads / tick
      flow/    # order-flow / toxicity / impact
      vol/     # noise & volatility / crash

Proprietary loaders and path helpers live in ``research.md`` (repo checkout; not in the wheel).

Usage::

    from ares_micro import fei, quoted_spread_bps, trade_markouts
    from ares_micro.flow.vpin import rolling_vpin
"""

from __future__ import annotations

from ares_micro.book import *  # noqa: F403
from ares_micro.book import __all__ as _BOOK_ALL
from ares_micro.flow import *  # noqa: F403
from ares_micro.flow import __all__ as _FLOW_ALL
from ares_micro.stats import bootstrap_ci, pearson_r_ci, spearman_r, time_split_mask
from ares_micro.vol import *  # noqa: F403
from ares_micro.vol import __all__ as _VOL_ALL

__all__ = [
    *_BOOK_ALL,
    *_FLOW_ALL,
    *_VOL_ALL,
    "bootstrap_ci",
    "pearson_r_ci",
    "spearman_r",
    "time_split_mask",
]
