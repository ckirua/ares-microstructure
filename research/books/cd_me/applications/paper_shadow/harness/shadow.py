"""Warehouse day discovery for cd_me paper_shadow."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

PKG = Path(__file__).resolve().parents[1]
BOOK = PKG.parents[1]
SCRIPTS = BOOK / "scripts"
WAREHOUSE_SRC = Path(
    os.environ.get("WAREHOUSE_SRC")
    or ((Path(os.environ.get("WAREHOUSE_ROOT") or (Path.home() / "lab" / "lab-n2070" / "warehouse")) / "src"))
)
STARTARB = Path(os.environ.get("ARES_STARTARB") or (Path.home() / "srv" / "ares-startarb"))
ROOT = BOOK.parents[2]


def _ensure_paths() -> None:
    for p in (str(WAREHOUSE_SRC), str(STARTARB / "src"), str(ROOT), str(SCRIPTS)):
        if p not in sys.path:
            sys.path.insert(0, p)


def list_warehouse_days(venue: str = "hyperliquid") -> list[str]:
    _ensure_paths()
    from _data import ensure_env, resolve_days

    ensure_env()
    return list(resolve_days(None, venue, n=0))


def find_latest_day(
    venue: str = "hyperliquid",
    symbol: str = "ETH",
    *,
    lookback: int = 21,
    prefer_complete: bool = False,
    quiet: bool = True,
    max_files: int = 48,
) -> dict[str, Any]:
    """Newest listing day; optionally walk until trade-completeness."""
    _ensure_paths()
    from _data import ensure_env, load_day_trades

    ensure_env()
    days = list_warehouse_days(venue)
    if not days:
        raise RuntimeError(f"no warehouse listing days for {venue}")
    probed: list[dict[str, Any]] = []
    window = list(reversed(days[-max(lookback, 1) :]))
    for day in window:
        try:
            rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
            flags = rec.get("completeness") or {}
            row = {
                "day": day,
                "complete": bool(flags.get("complete")),
                "n": flags.get("n"),
                "coverage": flags.get("coverage"),
            }
            probed.append(row)
            if not prefer_complete or row["complete"]:
                if not quiet:
                    print(f"[cdme_shadow] day={day} complete={row['complete']} n={row['n']}")
                return {"day": day, "completeness": flags, "probed": probed, "rec": rec}
        except Exception as exc:  # noqa: BLE001
            probed.append({"day": day, "complete": False, "error": f"{type(exc).__name__}: {exc}"})
    # fall back to newest even if incomplete
    day = window[0]
    return {"day": day, "completeness": {"complete": False}, "probed": probed, "rec": None}
