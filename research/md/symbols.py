"""Venue / underlying / instrument normalization."""

from __future__ import annotations

from research.md.constants import (
    ALIAS_TO_UNDERLYING,
    HL_FLAT_CUTOFF,
    HL_FLAT_IDS,
    LISTING_CACHE,
    VENUE_SYMBOL_FALLBACK,
)


def normalize_underlying(symbol: str) -> str:
    """Map venue-native or slash aliases to canonical underlying (BTC/ETH/SOL)."""
    s = str(symbol).strip().upper().replace(" ", "")
    if s in ALIAS_TO_UNDERLYING:
        return ALIAS_TO_UNDERLYING[s]
    for suf in ("/USD", "-USD", "/USDC", "-USDC", "-PERPETUAL"):
        if s.endswith(suf):
            base = s[: -len(suf)]
            if base in ALIAS_TO_UNDERLYING:
                return ALIAS_TO_UNDERLYING[base]
            if base in VENUE_SYMBOL_FALLBACK:
                return base
    if s in VENUE_SYMBOL_FALLBACK:
        return s
    return s


def normalize_venue(venue: str) -> str:
    v = str(venue).strip().lower()
    if v in ("hl", "hyperliquid"):
        return "hyperliquid"
    if v in ("db", "deribit"):
        return "deribit"
    if v in ("kr", "kraken"):
        return "kraken"
    return v


def venue_instrument(symbol: str, venue: str) -> str:
    """Underlying or alias → venue-native catalog symbol.

    Kraken examples: ``ETH`` / ``ETH/USD`` → ``PF_ETHUSD``;
    ``BTC`` / ``XBT`` → ``PF_XBTUSD``.
    """
    u = normalize_underlying(symbol)
    v = normalize_venue(venue)
    try:
        from startarb.data.symbols import venue_symbol

        return str(venue_symbol(u, v))
    except Exception:
        table = VENUE_SYMBOL_FALLBACK.get(u)
        if not table or v not in table:
            return str(symbol).strip()
        return table[v]


def resolve_days(
    days: list[str] | None,
    venue: str = "hyperliquid",
    n: int = 3,
    *,
    prefer_listing_cache: bool = True,
) -> list[str]:
    if days:
        return days
    v = normalize_venue(venue)
    if prefer_listing_cache:
        bucket = {
            "hyperliquid": "mercat-hyperliquid-md",
            "deribit": "mercat-deribit-md",
            "kraken": "mercat-kraken-md",
            "lighter": "mercat-lighter-md",
            "extended": "mercat-extended-md",
            "risex": "mercat-risex-md",
        }.get(v)
        if bucket:
            root = LISTING_CACHE / bucket
            if root.is_dir():
                cached = sorted(p.stem for p in root.glob("*.json"))
                if cached:
                    return cached[-n:] if n > 0 else cached
    try:
        from warehouse import list_days

        return list_days(v)[-n:]
    except Exception:
        return []


def hl_trade_instrument(symbol: str, day: str) -> str | int:
    """Opaque flat id for ≤FLAT_CUTOFF; catalog name thereafter."""
    sym = normalize_underlying(symbol)
    if day <= HL_FLAT_CUTOFF and sym in HL_FLAT_IDS:
        return HL_FLAT_IDS[sym]
    return venue_instrument(sym, "hyperliquid")


__all__ = [
    "hl_trade_instrument",
    "normalize_underlying",
    "normalize_venue",
    "resolve_days",
    "venue_instrument",
]
