"""Load paper-harness YAML config."""

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
    # normalize
    raw["venue"] = str(raw.get("venue") or "hyperliquid").lower()
    raw["symbol"] = str(raw.get("symbol") or "ETH").upper()
    raw["extra_venues"] = [str(v).lower() for v in (raw.get("extra_venues") or [])]
    raw["out_dir"] = str(raw.get("out_dir") or "out")
    raw.setdefault("z_breaks", {"p25": 12.5, "p50": 15.9, "p75": 20.4})
    raw.setdefault("gate", {"min_dp_pct": 0.10, "min_i_c": 5})
    raw.setdefault(
        "size_mult",
        {"none": 1.0, "observe": 1.0, "widen": 0.5, "size_cap": 0.25, "halt": 0.0},
    )
    return raw
