"""Portable roots for sibling packages (no hardcoded home directories).

Override with env vars when layouts differ:

- ``ARES_STARTARB`` — ares-startarb checkout (default ``$HOME/srv/ares-startarb``)
- ``WAREHOUSE_ROOT`` — warehouse package root (default ``$HOME/lab/lab-n2070/warehouse``)
- ``WAREHOUSE_SRC`` — warehouse ``src/`` (default ``$WAREHOUSE_ROOT/src``)
- ``ARES_MICROSTRUCTURE`` — this repo (default ``$HOME/srv/ares-microstructure``)
"""

from __future__ import annotations

import os
from pathlib import Path


def _env_or_home(name: str, *parts: str) -> Path:
    raw = os.environ.get(name)
    if raw:
        return Path(raw).expanduser()
    return Path.home().joinpath(*parts)


def startarb_root() -> Path:
    return _env_or_home("ARES_STARTARB", "srv", "ares-startarb")


def warehouse_root() -> Path:
    return _env_or_home("WAREHOUSE_ROOT", "lab", "lab-n2070", "warehouse")


def warehouse_src() -> Path:
    raw = os.environ.get("WAREHOUSE_SRC")
    if raw:
        return Path(raw).expanduser()
    return warehouse_root() / "src"


def microstructure_root() -> Path:
    """Prefer env; else walk up from this file; else ``$HOME/srv/ares-microstructure``."""
    raw = os.environ.get("ARES_MICROSTRUCTURE")
    if raw:
        return Path(raw).expanduser()
    here = Path(__file__).resolve()
    # research/lib/paths.py → repo root is parents[2]
    candidate = here.parents[2]
    if (candidate / "research" / "lib" / "paths.py").is_file():
        return candidate
    return Path.home() / "srv" / "ares-microstructure"
