"""Certified ETH panel definitions for squeeze_metrics — **real quotes only**.

Hard rules (desk):
- Primary TOB = Hyperliquid + Deribit warehouse/collector quotes.
- Kraken ``spot_l2`` (``l2_rebuild`` on ``spot|ETH/USD``) may join a *secondary*
  3-venue subpanel when dense — never trade_synth.
- ``trade_synth`` / TOB-from-trades is **quarantined** (PROXY / NOT TOB).
- Option DDOI = trade-flow proxy (warehouse OI is futures-only).
- GEX/VEX from BS γ/vanna on Deribit ``implied_vol`` option chain.
- Prefer cd_me-proven days when they still pass TOB + option-IV gates.
- Never soft-Promote TOB-cross α. ClickHouse MCP banned.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BOOK = Path(__file__).resolve().parents[1]
OUT = BOOK / "out" / "panel_completeness"
CERT_PATH = OUT / "certified_panels.json"

# Prefer cd_me primary window when those days pass squeeze gates
CD_ME_PREFERRED_DAYS: list[str] = [
    "2026-09-14",
    "2026-09-15",
    "2026-09-16",
    "2026-09-17",
    "2026-09-18",
    "2026-09-25",
    "2026-09-26",
    "2026-09-27",
    "2026-10-01",
]
SEED_CORE_2VENUE = list(CD_ME_PREFERRED_DAYS)
SEED_SPOT_L2 = [
    "2026-09-25",
    "2026-09-26",
    "2026-09-27",
    "2026-10-01",
]

CANDIDATE_DAYS: list[str] = sorted(
    set(CD_ME_PREFERRED_DAYS)
    | {
        "2026-09-19",
        "2026-09-23",
        "2026-09-24",
        "2026-09-28",
        "2026-09-29",
        "2026-09-30",
    }
)

# TOB gates (aligned with cd_me)
GATE_HL_TOB_N = 80
GATE_DB_TOB_N = 500
GATE_KR_SPOT_N = 80
GATE_MARKS_N = 200
GATE_SQUEEZE_N_FINITE = 80

# Options / GEX gates
GATE_OPT_IV_N = 50  # ETH option instruments with IV
GATE_OPT_TRADE_N = 10  # option trade prints (soft)

SYNTH_LABEL = "PROXY_NOT_TOB_trade_synth"
DDOI_LABEL = "PROXY_trade_flow_DDOI"
GEX_PROXY_LABEL = "BS_GEX_trade_flow_DDOI"  # real IV chain; DDOI is PROXY


def load_certified(path: Path | None = None) -> dict[str, Any]:
    p = path or CERT_PATH
    if not p.is_file():
        return {}
    return json.loads(p.read_text())


def primary_days(cert: dict[str, Any] | None = None) -> list[str]:
    c = cert if cert is not None else load_certified()
    primary = c.get("primary") or {}
    days = list(primary.get("days") or [])
    if days:
        return days
    panels = (c.get("panels") or {}).get("panel_core_2venue") or {}
    days = list(panels.get("days") or [])
    return days or list(SEED_CORE_2VENUE)


def spot_l2_days(cert: dict[str, Any] | None = None) -> list[str]:
    c = cert if cert is not None else load_certified()
    days = list((c.get("panels") or {}).get("panel_3venue_spot", {}).get("days") or [])
    return days or list(SEED_SPOT_L2)


def gex_panel_days(cert: dict[str, Any] | None = None) -> list[str]:
    """Days with TOB + option IV — primary GEX analysis window."""
    c = cert if cert is not None else load_certified()
    days = list((c.get("panels") or {}).get("panel_gex_options", {}).get("days") or [])
    return days or primary_days(c)


def excluded_days(cert: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    c = cert if cert is not None else load_certified()
    return list(c.get("excluded") or [])


def annotate_title(base: str, days: list[str], *, panel: str = "panel_core_2venue") -> str:
    n = len(days)
    if n <= 6:
        dstr = ", ".join(days)
    else:
        dstr = f"{days[0]} … {days[-1]} ({n}d)"
    return f"{base}\n[{panel} n={n}: {dstr}]"


def drop_all_null_series(series: dict[str, list | Any]) -> dict[str, Any]:
    import math

    out: dict[str, Any] = {}
    for k, v in series.items():
        if not isinstance(v, (list, tuple)):
            out[k] = v
            continue
        finite = False
        for x in v:
            if x is None:
                continue
            try:
                fx = float(x)
            except (TypeError, ValueError):
                finite = True
                break
            if math.isfinite(fx):
                finite = True
                break
        if finite:
            out[k] = v
    return out
