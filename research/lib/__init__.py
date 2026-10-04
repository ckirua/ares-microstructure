"""Notebook shim — canonical package is ``ares_micro``.

Prefer::

    from ares_micro import fei, quoted_spread_bps
    from research.md import load_trades, ensure_env
"""
from ares_micro import *  # noqa: F403
from ares_micro import __all__ as __all__  # noqa: F401
