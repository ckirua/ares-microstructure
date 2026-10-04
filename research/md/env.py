"""Environment bootstrap for warehouse / startarb loaders."""

from __future__ import annotations

import sys

from research.md.paths import microstructure_root, startarb_root, warehouse_src


def ensure_path() -> None:
    """Put warehouse src, startarb src, and repo root on ``sys.path`` if needed."""
    for _p in (str(warehouse_src()), str(startarb_root() / "src"), str(microstructure_root())):
        if _p not in sys.path:
            sys.path.insert(0, _p)


def ensure_env() -> None:
    """Load ``~/.env`` via startarb and ensure sibling packages are importable."""
    ensure_path()
    from startarb.env import ensure_env as _e

    _e()


__all__ = ["ensure_env", "ensure_path"]
