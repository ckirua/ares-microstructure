"""Certified ETH panel definitions — **real quotes only**.

Hard rules (desk):
- Primary TOB = Hyperliquid + Deribit warehouse/collector quotes.
- Kraken ``spot_l2`` (``l2_rebuild`` on ``spot|ETH/USD``) may join a *secondary*
  3-venue subpanel when dense — never trade_synth.
- ``trade_synth`` / TOB-from-trades is **quarantined** (PROXY / NOT TOB). It must
  not appear in primary PIM, DCM joins, elasticity, info dig, or default figs.
- Days without usable Kraken spot_l2 are **2-venue only** (HL↔Deribit), not
  "3-venue with synth".

ClickHouse MCP banned. Never soft-Promote TOB-cross α.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BOOK = Path(__file__).resolve().parents[1]
OUT = BOOK / "out" / "panel_completeness"
CERT_PATH = OUT / "certified_panels.json"

# ---------------------------------------------------------------------------
# Gates (real quotes)
# ---------------------------------------------------------------------------

# HL warehouse TOB is sparse (~1/min snap) — gate on presence + min quotes, not coverage %.
GATE_HL_TOB_N = 80
GATE_DB_TOB_N = 500  # Deribit L2 denser; thin days fail
GATE_KR_SPOT_N = 80  # spot_l2 usable density (refuse collapsed n≈1)
# HL warehouse TOB ≈100–130 quotes/day → 2-venue finite PIM often ~100–200
GATE_PIM_2V_N_FINITE = 80
GATE_DCM_N_VALID = 200  # minute-bar PC1 rows
GATE_DB_COV = 0.25  # fraction of day grid with Deribit mid (when available)

# Quarantine label
SYNTH_LABEL = "PROXY_NOT_TOB_trade_synth"


def load_certified(path: Path | None = None) -> dict[str, Any]:
    p = path or CERT_PATH
    if not p.is_file():
        return {}
    return json.loads(p.read_text())


def primary_days(cert: dict[str, Any] | None = None) -> list[str]:
    """Days for default analysis: ``panel_core_2venue`` primary window."""
    c = cert if cert is not None else load_certified()
    primary = c.get("primary") or {}
    days = list(primary.get("days") or [])
    if days:
        return days
    return list((c.get("panels") or {}).get("panel_core_2venue", {}).get("days") or [])


def spot_l2_days(cert: dict[str, Any] | None = None) -> list[str]:
    c = cert if cert is not None else load_certified()
    return list((c.get("panels") or {}).get("panel_3venue_spot", {}).get("days") or [])


def excluded_days(cert: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    c = cert if cert is not None else load_certified()
    return list(c.get("excluded") or [])


def annotate_title(base: str, days: list[str], *, panel: str = "panel_core_2venue") -> str:
    """Figure title annotation: n + day list (truncated)."""
    n = len(days)
    if n <= 6:
        dstr = ", ".join(days)
    else:
        dstr = f"{days[0]} … {days[-1]} ({n}d)"
    return f"{base}\n[{panel} n={n}: {dstr}]"


def drop_all_null_series(series: dict[str, list | Any]) -> dict[str, Any]:
    """Remove keys whose values are all None/NaN (plot hygiene)."""
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
