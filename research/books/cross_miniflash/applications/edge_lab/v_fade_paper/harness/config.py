"""Load v_fade_paper YAML config."""

from __future__ import annotations

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
    raw["extra_venues"] = [str(v).lower() for v in (raw.get("extra_venues") or [])]
    raw["out_dir"] = str(raw.get("out_dir") or "out")
    raw["live_orders"] = bool(raw.get("live_orders", False))
    raw.setdefault("gate", {"min_dp_pct": 0.10, "min_i_c": 5})
    raw.setdefault(
        "v_fade",
        {
            "confirm_s": 2.0,
            "exit_s": 5.0,
            "soft_confirm_r1": 0.35,
            "v_threshold_r2": 0.5,
            "cont_threshold_r2": 0.2,
            "rt_friction_bps": 4.0,
            "friction_bps_one_way": 2.0,
            "adverse_stop_bps": 12.0,
            "max_concurrent": 1,
            "clip_notional": 1.0,
            "n_boot": 800,
        },
    )
    raw.setdefault(
        "kill",
        {
            "k1_rolling_days": 5,
            "k1_min_n": 20,
            "k2_n_boot": 800,
            "k4_hit_rate_kill": 0.55,
            "k4_hit_rate_warn": 0.65,
            "k4_min_n": 40,
            "k5_adverse_share": 0.40,
            "k5_min_n": 30,
            "k6_median_one_way_bps": 5.0,
        },
    )
    return raw
