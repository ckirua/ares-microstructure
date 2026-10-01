"""Load paper-live YAML config (HL ETH defaults)."""


from __future__ import annotations

import os

from pathlib import Path
from typing import Any

import yaml

PKG = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PKG / "config.yaml"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else DEFAULT_CONFIG
    raw = yaml.safe_load(p.read_text()) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"config must be a mapping: {p}")
    raw["_config_path"] = str(p.resolve())
    raw["venue"] = str(raw.get("venue") or "hyperliquid").lower()
    raw["symbol"] = str(raw.get("symbol") or "ETH").upper()
    raw["out_dir"] = str(raw.get("out_dir") or "out")
    raw["log_dir"] = str(raw.get("log_dir") or "logs")
    raw["log_file"] = str(raw.get("log_file") or "paper_live.log")
    raw["poll_interval_s"] = float(raw.get("poll_interval_s") or 10.0)
    raw["live_orders"] = False  # hard pin — never submit
    # A13 horizon defaults: event-time SSM + wall_60s intensity (not trade_last_N detect)
    raw.setdefault("detection_clock", "event")
    raw.setdefault("intensity_clock", "wall_60s")
    raw.setdefault("intensity_window_s", 60.0)
    det_clock = str(raw.get("detection_clock") or "event").lower()
    if det_clock.startswith("trade_last") or det_clock in {
        "trade_last_300",
        "trade_last_9000",
        "trade_300",
        "trade_9000",
    }:
        raise ValueError(
            f"detection_clock={det_clock!r} is Kill for mini-flash SSM "
            "(A13); use event-time detection, not trade_last_N observation bars"
        )
    raw["detection_clock"] = det_clock
    raw.setdefault("z_breaks", {"p25": 12.5, "p50": 15.9, "p75": 20.4})
    raw.setdefault("gate", {"min_dp_pct": 0.10, "min_i_c": 5})
    raw.setdefault(
        "size_mult",
        {"none": 1.0, "observe": 1.0, "widen": 0.5, "size_cap": 0.25, "halt": 0.0},
    )
    raw.setdefault(
        "data",
        {
            "prefer_warehouse_refresh": True,
            "use_collector_tob": True,
            "collector_tob_root": str(Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb')) / "results/xarb_md/tob"),
        },
    )
    raw.setdefault(
        "v_fade",
        {
            "entry_mode": "severity_zend",
            "confirm_s": 0.5,
            "exit_s": 3.0,
            "z_min": 20.0,
            "suppress_fire_pause": "prior_only",
            "adverse_stop_bps": 1e9,
            "rt_friction_bps": 4.0,
        },
    )
    raw["require_complete_day"] = bool(raw.get("require_complete_day", False))
    if bool(raw.get("live_orders")):
        raise RuntimeError("paper_live refuses live_orders=true")
    return raw
