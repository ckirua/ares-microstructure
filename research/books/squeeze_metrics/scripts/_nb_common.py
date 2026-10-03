"""Shared notebook bootstrap for squeeze_metrics chapter / desk notebooks.

Prefer loading ``out/`` artifacts; regenerate light plots inline when PNGs
are missing. DDOI is always labeled PROXY_trade_flow_DDOI.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def book_root() -> Path:
    env = os.environ.get("ARES_MICROSTRUCTURE")
    base = Path(env) if env else (Path.home() / "srv" / "ares-microstructure")
    return base / "research" / "books" / "squeeze_metrics"


def ensure_research_path(book: Path | None = None) -> Path:
    book = book or book_root()
    research = book.parents[1]
    if str(research) not in sys.path:
        sys.path.insert(0, str(research))
    return research


def load_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def panel_to_df(rows: list[dict] | None) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def gex_day_table(gex_rows: list[dict], cert: dict | None = None) -> pd.DataFrame:
    """Day-level GEX/VEX table with venue / DDOI honesty columns."""
    spot = set()
    if cert:
        spot = set((cert.get("panels") or {}).get("panel_3venue_spot", {}).get("days") or [])
        if not spot:
            spot = set((cert.get("primary") or {}).get("spot_l2_subpanel") or [])
    rows = []
    for r in gex_rows or []:
        day = r.get("day")
        kraken = "spot_l2" if str(day) in spot else "absent_2venue"
        rows.append(
            {
                "day": day,
                "ok": r.get("ok"),
                "spot": r.get("spot"),
                "gex": r.get("gex"),
                "vex": r.get("vex"),
                "gex_plus": r.get("gex_plus"),
                "squeeze_intensity": r.get("squeeze_intensity"),
                "scarce": r.get("scarce"),
                "dealer_sign": r.get("dealer_sign"),
                "ddoi_mode": r.get("ddoi_mode"),
                "opt_iv_n": r.get("opt_iv_n"),
                "opt_trade_n": r.get("opt_trade_n"),
                "hl_tob_n": r.get("hl_tob_n"),
                "hl_rv": r.get("hl_rv"),
                "hl_range": r.get("hl_range"),
                "db_rv": r.get("db_rv"),
                "db_range": r.get("db_range"),
                "kraken": kraken,
            }
        )
    return pd.DataFrame(rows)


def safe_corr(a, b) -> float | None:
    x = np.asarray(a, dtype=np.float64)
    y = np.asarray(b, dtype=np.float64)
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 3:
        return None
    return float(np.corrcoef(x[m], y[m])[0, 1])


def partial_corr_vs_rv(x, y, rv) -> float | None:
    """Incremental association: corr of residuals after linear RV projection."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    z = np.asarray(rv, dtype=np.float64)
    m = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    if m.sum() < 4:
        return None
    x, y, z = x[m], y[m], z[m]
    # residualize on [1, z]
    A = np.column_stack([np.ones(z.size), z])
    bx, *_ = np.linalg.lstsq(A, x, rcond=None)
    by, *_ = np.linalg.lstsq(A, y, rcond=None)
    rx, ry = x - A @ bx, y - A @ by
    if np.std(rx) < 1e-15 or np.std(ry) < 1e-15:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def lead_lag_day(x: np.ndarray, y: np.ndarray, max_lag: int = 2) -> dict[str, float | None]:
    """Simple day-panel lead-lag: corr(x[t], y[t+k]) for k in [-max_lag..max_lag]."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    out: dict[str, float | None] = {}
    for k in range(-max_lag, max_lag + 1):
        if k < 0:
            a, b = x[-k:], y[: len(y) + k]
        elif k > 0:
            a, b = x[: len(x) - k], y[k:]
        else:
            a, b = x, y
        out[f"lag_{k:+d}"] = safe_corr(a, b)
    return out


SIGNAL_BOARD = [
    (
        "risk.gex_exposure",
        "Hold",
        "Σ PROXY_trade_flow_DDOI · BS-γ · panel_gex_options n=9 — monitor≠α",
    ),
    (
        "risk.vex_exposure",
        "Hold",
        "Σ DDOI · BS-vanna vs HL range/RV — Hold",
    ),
    (
        "risk.squeeze_intensity",
        "Hold",
        "GEX+ scarcity / stress–calm — Hold",
    ),
    (
        "liq.implied_book_scarcity",
        "Hold",
        "Abundance / scarce labels from GEX+ — Hold",
    ),
    (
        "liq.gex_rv_link",
        "Hold",
        "corr(GEX, HL RV)≈−0.22; day-block CI crosses 0 — research tile",
    ),
    (
        "risk.squeeze_falsifier_board",
        "Hold",
        "Pass-2b chrono / day-block / placebo / venue-drop / LOO — 0 Promote",
    ),
    (
        "info.gex_range_incremental",
        "Hold",
        "partial(range,GEX|RV)≈0 · ΔR²≈0 — vol-overlap honesty tile",
    ),
    (
        "info.squeeze_after_gex",
        "Hold",
        "ΔR²(squeeze|GEX) on range ~0 — research",
    ),
    (
        "info.vex_incremental",
        "Hold",
        "ΔR²(VEX|RV+GEX)~0 — research",
    ),
    (
        "info.gex_leadlag_map",
        "Hold",
        "Day lead-lag GEX→RV/range/mid_ret — descriptive not IRF α",
    ),
    (
        "info.gex_markout_regimes",
        "Hold",
        "Intraday cum mid-ret markouts by scarce/stress/calm — research",
    ),
    (
        "info.tod_factor_structure",
        "Hold",
        "ToD RV / mid_ret by regime + day-feature PCA — commonality",
    ),
    (
        "info.stress_vs_calm",
        "Hold",
        "|GEX| / scarce regime splits vs HL RV — policy/monitor",
    ),
    (
        "info.object_use_map",
        "Hold",
        "APPLICATIONS: monitor vs throttle vs never-tradable",
    ),
    (
        "info.ddoi_coverage",
        "Hold",
        "PROXY_trade_flow_DDOI; warehouse OI futures-only unused",
    ),
    (
        "info.kraken_spot_vs_2venue",
        "Hold",
        "spot_l2 appendix n=4 vs absent_2venue; trade_synth QUARANTINED",
    ),
    (
        "alpha.tob_cross_arb",
        "Kill",
        "TOB mid gap ≠ sized arb; never soft-Promote",
    ),
    (
        "data.trade_synth",
        "Kill",
        "PROXY_NOT_TOB_trade_synth — never SoT for DDOI/GEX/VEX",
    ),
]
