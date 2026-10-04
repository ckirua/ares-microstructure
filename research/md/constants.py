"""Shared path / venue / symbol constants for research data loaders."""

from __future__ import annotations

import os
from pathlib import Path

from research.md.paths import microstructure_root, startarb_root, warehouse_src

STARTARB = startarb_root()
WAREHOUSE_SRC = warehouse_src()
MICRO_ROOT = microstructure_root()
DEFAULT_TOB = STARTARB / "results" / "xarb_md" / "tob"

# Local Kraken futures TOB ingest cache (vpin_of / mn_tuwrv). Override with KRAKEN_FUT_TOB.
def _default_kraken_fut_tob() -> Path:
    env = os.environ.get("KRAKEN_FUT_TOB")
    if env:
        return Path(env).expanduser()
    return MICRO_ROOT / "research" / "books" / "vpin_of" / "out" / "kraken_futures_tob"


KRAKEN_FUT_TOB = _default_kraken_fut_tob()

HL_FLAT_IDS: dict[str, int] = {
    "BTC": 3860219501,
    "ETH": 3337431014,
}
HL_FLAT_CUTOFF = "2026-09-10"
LISTING_CACHE = Path.home() / ".cache" / "warehouse" / "listings"

# Mercat catalog keys for Kraken *spot* L2 (warehouse stream=spot-000).
# Futures ``PF_*`` sealed public-md: trade/mark/index/funding/OI only — no BBO/L2.
KRAKEN_SPOT_TOB: dict[str, str] = {
    "BTC": "spot|BTC/USD",
    "ETH": "spot|ETH/USD",
    "SOL": "spot|SOL/USD",
}
# Back-compat private alias used by older call sites / docs.
_KRAKEN_SPOT_TOB = KRAKEN_SPOT_TOB

CORE_VENUES = ("hyperliquid", "deribit", "kraken")

# Fallback when startarb symbols.yaml is not importable
VENUE_SYMBOL_FALLBACK: dict[str, dict[str, str]] = {
    "BTC": {
        "hyperliquid": "BTC",
        "deribit": "BTC-PERPETUAL",
        "kraken": "PF_XBTUSD",
        "lighter": "BTC",
        "extended": "BTC-USD",
        "risex": "BTC/USDC",
    },
    "ETH": {
        "hyperliquid": "ETH",
        "deribit": "ETH-PERPETUAL",
        "kraken": "PF_ETHUSD",
        "lighter": "ETH",
        "extended": "ETH-USD",
        "risex": "ETH/USDC",
    },
    "SOL": {
        "hyperliquid": "SOL",
        "deribit": "SOL_USDC-PERPETUAL",
        "kraken": "PF_SOLUSD",
        "lighter": "SOL",
        "extended": "SOL-USD",
        "risex": "SOL/USDC",
    },
}
_VENUE_SYMBOL_FALLBACK = VENUE_SYMBOL_FALLBACK

# Common aliases → underlying
ALIAS_TO_UNDERLYING: dict[str, str] = {
    "BTC": "BTC",
    "XBT": "BTC",
    "BTC/USD": "BTC",
    "BTC-USD": "BTC",
    "BTC/USDC": "BTC",
    "PF_XBTUSD": "BTC",
    "BTC-PERPETUAL": "BTC",
    "ETH": "ETH",
    "ETH/USD": "ETH",
    "ETH-USD": "ETH",
    "ETH/USDC": "ETH",
    "PF_ETHUSD": "ETH",
    "ETH-PERPETUAL": "ETH",
    "SOL": "SOL",
    "SOL/USD": "SOL",
    "SOL-USD": "SOL",
    "SOL/USDC": "SOL",
    "PF_SOLUSD": "SOL",
    "SOL_USDC-PERPETUAL": "SOL",
}
_ALIAS_TO_UNDERLYING = ALIAS_TO_UNDERLYING

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
]
