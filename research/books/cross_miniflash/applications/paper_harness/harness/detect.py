"""Gated SSM + Nanex detection for one venue×symbol×UTC day."""


from __future__ import annotations

import os

import sys
from pathlib import Path
from typing import Any

import numpy as np

PKG = Path(__file__).resolve().parents[1]
APP = PKG.parent
BOOK = APP.parent
ROOT = BOOK.parents[2]
STARTARB = Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb'))
WAREHOUSE_SRC = Path(os.environ.get('WAREHOUSE_SRC') or ((Path(os.environ.get('WAREHOUSE_ROOT') or (Path.home() / 'lab' / 'lab-n2070' / 'warehouse')) / 'src')))
SCRIPTS_APP = APP / "scripts"

for p in (
    str(ROOT),
    str(STARTARB / "src"),
    str(WAREHOUSE_SRC),
    str(BOOK / "scripts"),
    str(SCRIPTS_APP),
):
    if p not in sys.path:
        sys.path.insert(0, p)

from _common import (  # noqa: E402
    GATE_PRIMARY,
    Z_STAR,
    assign_ladder_tiers,
    detect_venue_day,
    rolling_gated_intensity,
)
from _data import ensure_env, load_day_trades  # noqa: E402
from research.lib.crash import recovery_fraction  # noqa: E402


def load_tape(venue: str, symbol: str, day: str, *, quiet: bool = True) -> dict[str, Any]:
    ensure_env()
    return load_day_trades(venue, symbol, day, quiet=quiet)


def detect_day(
    venue: str,
    symbol: str,
    day: str,
    *,
    cfg: dict[str, Any] | None = None,
    quiet: bool = True,
) -> dict[str, Any]:
    """Load tape → SSM/Nanex detect → intensity → provisional tiers.

    Returns a cell dict compatible with kill_ladder / strategy_lab event clocks.
    """
    cfg = cfg or {}
    rec = load_tape(venue, symbol, day, quiet=quiet)
    complete = bool(rec.get("completeness", {}).get("complete"))
    tape = rec["tape"]
    z_star = float(cfg.get("z_star", Z_STAR))
    sigma_m_frac = float(cfg.get("sigma_m_frac", 1.0))
    det = detect_venue_day(tape, sigma_m_frac=sigma_m_frac, z_star=z_star)
    if det.get("skip"):
        return {
            "day": day,
            "symbol": symbol,
            "venue": venue,
            "complete": complete,
            "skip": det["skip"],
            "n_trades": det.get("n_trades", 0),
            "tape": tape,
            "completeness": rec.get("completeness"),
        }

    s10 = det["ssm_10bps"]
    intens = rolling_gated_intensity(
        s10["ts_start"], window_s=float(cfg.get("intensity_window_s", 60.0))
    )
    nx = det["nanex"]
    # rebuild nanex overlap on SSM (already in det via nested mask on nanex side;
    # ssm-side flags from detect_venue_day path in _common panel builder)
    from _common import _ssm_has_nanex_overlap  # noqa: WPS433

    ssm_has_nanex = _ssm_has_nanex_overlap(
        s10, nx, det["ts"], slack_s=float(cfg.get("nanex_slack_s", 0.5))
    )
    # Causal V-confirm horizons for ladder+confirm playbook (Promote med MM)
    r1 = recovery_fraction(
        det["ts"],
        det["px"],
        s10["start_i"],
        s10["end_i"],
        s10["direction"],
        horizon_s=1.0,
    )
    r2 = recovery_fraction(
        det["ts"],
        det["px"],
        s10["start_i"],
        s10["end_i"],
        s10["direction"],
        horizon_s=2.0,
    )
    events = {
        "ts_start": np.asarray(s10["ts_start"], dtype=np.int64),
        "ts_end": np.asarray(s10["ts_end"], dtype=np.int64),
        "dp_pct": np.asarray(s10["dp_pct"], dtype=np.float64),
        "i_c": np.asarray(s10["i_c"], dtype=np.int64),
        "dt_s": np.asarray(s10["dt_s"], dtype=np.float64),
        "direction": np.asarray(s10["direction"], dtype=np.int64),
        "z_peak": np.asarray(s10["z_peak"], dtype=np.float64),
        "intensity_60s": intens,
        "recovery": np.asarray(det["recovery"], dtype=np.float64),
        "recovery_1s": np.asarray(r1, dtype=np.float64),
        "recovery_2s": np.asarray(r2, dtype=np.float64),
        "recovery_label": np.asarray(det["recovery_class"]["labels"], dtype=object),
        "mo_1s": np.asarray(det["markout_1s"], dtype=np.float64),
        "mo_5s": np.asarray(det["markout_5s"], dtype=np.float64),
        "nanex_overlap": ssm_has_nanex,
    }
    # provisional tiers from config breaks; reassigned by assign_event_tiers
    zb = cfg.get("z_breaks") or {}
    flat = [
        {
            "z_peak": float(events["z_peak"][i]),
            "intensity_60s": int(events["intensity_60s"][i]),
            "nanex_overlap": bool(events["nanex_overlap"][i]),
            "dp_pct": float(events["dp_pct"][i]),
        }
        for i in range(int(s10["n_events"]))
    ]
    breaks = assign_ladder_tiers(flat) if flat else {
        **{k: float(zb.get(k, v)) for k, v in (("p25", 12.5), ("p50", 15.9), ("p75", 20.4))},
        "dp_p90": float(cfg.get("dp_p90", 0.45)),
    }
    if flat:
        events["tier"] = np.asarray([e["tier"] for e in flat], dtype=object)
    else:
        events["tier"] = np.asarray([], dtype=object)

    gate = cfg.get("gate") or GATE_PRIMARY
    return {
        "day": day,
        "symbol": symbol,
        "venue": venue,
        "complete": complete,
        "completeness": rec.get("completeness"),
        "n_trades": int(det["n_trades"]),
        "tape": tape,
        "ts": det["ts"],
        "px": det["px"],
        "sigma_m_median": det.get("sigma_m_median"),
        "sigma_m_floor_hit": det.get("sigma_m_floor_hit"),
        "ssm_raw_n": int(det["ssm_raw"]["n_events"]),
        "ssm_10_n": int(s10["n_events"]),
        "nanex_n": int(nx["n_events"]),
        "nanex_nested_n": int(np.sum(det["nanex_nested_mask"])),
        "nanex_ssm_precision": det["nanex_ssm_nest"].get("precision_a"),
        "events": events,
        "nanex_events": {
            "ts_start": np.asarray(nx["ts_start"], dtype=np.int64),
            "ts_end": np.asarray(nx["ts_end"], dtype=np.int64),
            "dp_pct": np.asarray(nx["dp_pct"], dtype=np.float64),
            "nested": np.asarray(det["nanex_nested_mask"], dtype=bool),
        },
        "ladder_breaks": breaks,
        "gate": dict(gate),
        "z_star": z_star,
    }
