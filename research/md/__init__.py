"""Proprietary market-data I/O (startarb / warehouse).

Not part of the installable ``ares_micro`` wheel. Import with the repo root
on ``PYTHONPATH`` (or run book scripts from a checkout)::

    from research.md import load_trades, ensure_env, load_venue_tob
"""

from __future__ import annotations

from ares_micro.core.arrays import asof_join, day_bounds_ns, normalize_side
from research.md.constants import (
    ALIAS_TO_UNDERLYING,
    CORE_VENUES,
    DEFAULT_TOB,
    HL_FLAT_CUTOFF,
    HL_FLAT_IDS,
    KRAKEN_FUT_TOB,
    KRAKEN_SPOT_TOB,
    LISTING_CACHE,
    MICRO_ROOT,
    STARTARB,
    VENUE_SYMBOL_FALLBACK,
    WAREHOUSE_SRC,
    _ALIAS_TO_UNDERLYING,
    _KRAKEN_SPOT_TOB,
    _VENUE_SYMBOL_FALLBACK,
)
from research.md.env import ensure_env, ensure_path
from research.md.marks import (
    funding_proxy_from_marks,
    load_cross_venue_marks,
    load_cross_venue_tob,
    load_day_marks,
    load_squeeze_feature_inputs,
    trade_volume_buckets,
)
from research.md.options import (
    deribit_option_catalog,
    load_deribit_instrument_map,
    load_deribit_table_day,
    load_deribit_underlying_mark,
    load_eth_option_iv_day,
    load_eth_option_trades_day,
    _column_batch_arrays,
)
from research.md.symbols import (
    hl_trade_instrument,
    normalize_underlying,
    normalize_venue,
    resolve_days,
    venue_instrument,
)
from research.md.tob import (
    collector_tob_days,
    kraken_liquidity_proxies,
    load_collector_tob,
    load_hl_tob,
    load_kraken_futures_tob_day,
    load_kraken_futures_trade_synth_tob_day,
    load_kraken_spot_tob_day,
    load_tob_any,
    load_tob_day,
    load_venue_tob,
    load_warehouse_tob,
    _filter_tob_arrays,
)
from research.md.trades import (
    clip_tape_to_utc_day,
    day_completeness,
    load_core_venues_day,
    load_day_trades,
    load_trades,
    overlap_trades_with_mids,
)
from research.md.vpin import vpin_day_features

__all__ = [
    "ALIAS_TO_UNDERLYING",
    "CORE_VENUES",
    "DEFAULT_TOB",
    "HL_FLAT_CUTOFF",
    "HL_FLAT_IDS",
    "KRAKEN_FUT_TOB",
    "KRAKEN_SPOT_TOB",
    "LISTING_CACHE",
    "MICRO_ROOT",
    "STARTARB",
    "VENUE_SYMBOL_FALLBACK",
    "WAREHOUSE_SRC",
    "_ALIAS_TO_UNDERLYING",
    "_KRAKEN_SPOT_TOB",
    "_VENUE_SYMBOL_FALLBACK",
    "_column_batch_arrays",
    "_filter_tob_arrays",
    "asof_join",
    "clip_tape_to_utc_day",
    "collector_tob_days",
    "day_bounds_ns",
    "day_completeness",
    "deribit_option_catalog",
    "ensure_env",
    "ensure_path",
    "funding_proxy_from_marks",
    "hl_trade_instrument",
    "kraken_liquidity_proxies",
    "load_collector_tob",
    "load_core_venues_day",
    "load_cross_venue_marks",
    "load_cross_venue_tob",
    "load_day_marks",
    "load_day_trades",
    "load_deribit_instrument_map",
    "load_deribit_table_day",
    "load_deribit_underlying_mark",
    "load_eth_option_iv_day",
    "load_eth_option_trades_day",
    "load_hl_tob",
    "load_kraken_futures_tob_day",
    "load_kraken_futures_trade_synth_tob_day",
    "load_kraken_spot_tob_day",
    "load_squeeze_feature_inputs",
    "load_tob_any",
    "load_tob_day",
    "load_trades",
    "load_venue_tob",
    "load_warehouse_tob",
    "normalize_side",
    "normalize_underlying",
    "normalize_venue",
    "overlap_trades_with_mids",
    "resolve_days",
    "trade_volume_buckets",
    "venue_instrument",
    "vpin_day_features",
]
