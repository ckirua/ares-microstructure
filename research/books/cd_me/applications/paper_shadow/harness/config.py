"""Config loader for cd_me paper_shadow."""

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
    cfg.setdefault("extra_venues", ["deribit", "kraken"])
    cfg.setdefault(
        "gates",
        {
            "risk.pim_cross_venue": "Hold",
            "risk.dcm_pc1": "Hold",
            "liq.elasticity_regime": "Hold",
            "info.vloop_tcost_commonality": "Hold",
            "alpha.tob_cross_arb": "Kill",
            "risk.bank_cds_var": "Kill",
        },
    )
    return cfg
