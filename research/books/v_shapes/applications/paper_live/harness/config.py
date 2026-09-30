"""Config loader for V-shapes paper_live SHADOW."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PKG = Path(__file__).resolve().parents[1]


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else PKG / "config.yaml"
    with p.open() as f:
        cfg = yaml.safe_load(f) or {}
    cfg["live_orders"] = False
    cfg["alpha_claim"] = False
    cfg.setdefault("venue", "hyperliquid")
    cfg.setdefault("symbol", "ETH")
    cfg.setdefault("poll_interval_s", 120.0)
    cfg.setdefault("out_dir", "out")
    cfg.setdefault("log_dir", "logs")
    cfg.setdefault("log_file", "shadow.log")
    # Resolve relative coef path against book root (applications/../..)
    cal = dict(cfg.get("calendar_ridge") or {})
    coef = cal.get("coef_path")
    if coef and not Path(coef).is_absolute():
        cal["coef_path"] = str((PKG / coef).resolve())
    cfg["calendar_ridge"] = cal
    return cfg
