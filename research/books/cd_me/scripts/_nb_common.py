"""Shared notebook bootstrap for cd_me chapter / desk notebooks.

Import from chapter notebooks after adding research/ to sys.path, or copy the
path resolution block. Prefer loading ``out/`` artifacts; regenerate light
plots inline when PNGs are missing.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def book_root() -> Path:
    env = os.environ.get("ARES_MICROSTRUCTURE")
    base = Path(env) if env else (Path.home() / "srv" / "ares-microstructure")
    return base / "research" / "books" / "cd_me"


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


def ns_to_hour_utc(ts_ns: np.ndarray | list) -> np.ndarray:
    ts = np.asarray(ts_ns, dtype=np.int64)
    # floor to UTC hour-of-day
    return ((ts // 1_000_000_000) % 86400) // 3600


def expand_pim_hourly(panel_rows: list[dict]) -> pd.DataFrame:
    rows: list[dict] = []
    for day in panel_rows:
        if not day.get("ok"):
            continue
        h = day.get("hourly") or {}
        ts = h.get("ts") or []
        for i, t in enumerate(ts):
            rows.append(
                {
                    "day": day["day"],
                    "ts_ns": int(t),
                    "hour_utc": int(((int(t) // 1_000_000_000) % 86400) // 3600),
                    "vloop": _f(h.get("vloop"), i),
                    "tcost": _f(h.get("tcost"), i),
                    "pim": _f(h.get("pim"), i),
                    "notional": _f(h.get("notional"), i),
                    "imbalance": _f(h.get("imbalance"), i),
                    "home_venue": day.get("home_venue"),
                    "cov_hl": (day.get("coverage") or {}).get("hyperliquid"),
                    "cov_db": (day.get("coverage") or {}).get("deribit"),
                    "cov_kr": (day.get("coverage") or {}).get("kraken"),
                    "n_finite_pim": (day.get("summary") or {}).get("n_finite_pim"),
                    "corr_vt": (day.get("summary") or {}).get("corr_vloop_tcost"),
                }
            )
    return pd.DataFrame(rows)


def expand_dcm_hourly(panel_rows: list[dict]) -> pd.DataFrame:
    rows: list[dict] = []
    for day in panel_rows:
        if not day.get("ok"):
            continue
        h = day.get("hourly_pool") or {}
        ts = h.get("ts") or []
        dcm_meta = day.get("dcm") or {}
        for i, t in enumerate(ts):
            rows.append(
                {
                    "day": day["day"],
                    "ts_ns": int(t),
                    "hour_utc": int(((int(t) // 1_000_000_000) % 86400) // 3600),
                    "pim": _f(h.get("pim"), i),
                    "notional": _f(h.get("notional"), i),
                    "dcm": _f(h.get("dcm"), i),
                    "home_venue": day.get("home_venue"),
                    "explained_var": dcm_meta.get("explained_var"),
                    "n_valid": dcm_meta.get("n_valid"),
                    "G_mean": dcm_meta.get("G_mean"),
                }
            )
    return pd.DataFrame(rows)


def _f(arr: list | None, i: int) -> float:
    if not arr or i >= len(arr):
        return float("nan")
    v = arr[i]
    if v is None:
        return float("nan")
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def load_kraken_inventory(book: Path | None = None) -> dict:
    book = book or book_root()
    return load_json(book / "out" / "kraken_s3_inventory.json") or {}


def kraken_mode_for_day(day: str, inventory: dict | None = None) -> str:
    """Label Kraken TOB path for a day — **real quotes only**.

    Returns one of: ``spot_l2``, ``absent_2venue``, ``PROXY_NOT_TOB_trade_synth``
    (legacy miscount only — never treat as primary 3-venue).

    Prefer ``out/panel_completeness/completeness.json`` / certified panels;
    fall back to inventory notes (spot rebuild density).
    """
    # 1) Completeness matrix (authoritative after real-quote fix)
    comp = load_json(book_root() / "out" / "panel_completeness" / "completeness.json") or {}
    for d in comp.get("days") or []:
        if str(d.get("day")) != str(day):
            continue
        if (d.get("kr_spot_l2") or {}).get("ok"):
            return "spot_l2"
        if d.get("legacy_included_synth_as_3venue"):
            return "PROXY_NOT_TOB_trade_synth"
        return "absent_2venue"

    # 2) PIM day artifact
    pim = load_json(book_root() / "out" / "pim_vloop_tcost" / f"day_{day}.json") or {}
    km = pim.get("kraken_mode")
    if km in ("spot_l2", "absent_2venue", "absent", "missing"):
        return "spot_l2" if km == "spot_l2" else "absent_2venue"
    if km == "trade_synth":
        return "PROXY_NOT_TOB_trade_synth"

    # 3) Legacy inventory (spot density only — never promote synth)
    inv = inventory if inventory is not None else load_kraken_inventory()
    note = str((inv.get("streams_by_panel_day") or {}).get(day) or "")
    if not note:
        return "absent_2venue"
    m = re.search(r"rebuild n≈(\d+)", note)
    if m and int(m.group(1)) > 5:
        return "spot_l2"
    if "futures-000 only" in note or (m and int(m.group(1)) <= 5):
        return "PROXY_NOT_TOB_trade_synth"  # quarantined label
    return "absent_2venue"


def day_summary_table(
    pim_panel: list[dict], *, inventory: dict | None = None
) -> pd.DataFrame:
    inv = inventory if inventory is not None else load_kraken_inventory()
    rows = []
    for d in pim_panel:
        s = d.get("summary") or {}
        cov = d.get("coverage") or {}
        venues = list(d.get("venues_tob") or [])
        errs = d.get("tob_errors") or {}
        day = d.get("day")
        km = d.get("kraken_mode")
        if km in ("spot_l2",):
            kraken = "spot_l2"
        elif km in ("absent_2venue", "absent", "missing"):
            kraken = "absent_2venue"
        elif km in ("trade_synth", "PROXY_NOT_TOB_trade_synth"):
            kraken = "PROXY_NOT_TOB_trade_synth"
        elif "kraken" in errs:
            kraken = f"err:{errs.get('kraken')}"
        elif "kraken" in venues:
            kraken = kraken_mode_for_day(str(day), inv)
        else:
            kraken = "absent_2venue"
        rows.append(
            {
                "day": day,
                "ok": d.get("ok"),
                "venues": ",".join(venues),
                "n_venues": len(venues),
                "n_finite": s.get("n_finite_pim"),
                "pim_mean": s.get("pim_mean"),
                "vloop_mean": s.get("vloop_mean"),
                "tcost_mean": s.get("tcost_mean"),
                "corr_vt": s.get("corr_vloop_tcost"),
                "cov_hl": cov.get("hyperliquid"),
                "cov_db": cov.get("deribit"),
                "cov_kr": cov.get("kraken"),
                "kraken": kraken,
            }
        )
    return pd.DataFrame(rows)


SIGNAL_BOARD = [
    (
        "risk.pim_cross_venue",
        "Hold",
        "PIM = VLOOP+|TCOST| · panel_core_2venue (HL↔Deribit real quotes); spot_l2 subpanel only",
    ),
    (
        "info.vloop_tcost_commonality",
        "Hold",
        "pooled hourly corr on certified real-quote panel (see DESK_MEMO)",
    ),
    (
        "info.vloop_tcost_stress_split",
        "Hold",
        "calm vs stress (PIM q25/q75) on certified panel",
    ),
    (
        "risk.dcm_pc1",
        "Hold",
        "PC1 of public funding/basis/RV/imbalance proxies",
    ),
    (
        "info.pim_dcm_incremental",
        "Hold",
        "partial(PIM,DCM|RV) on certified panel — not pure RV alias",
    ),
    (
        "liq.elasticity_regime",
        "Hold",
        "corr(VLM,PIM) by DCM quantile — certified 2-venue; ceiling Hold",
    ),
    (
        "info.elasticity_after_rv",
        "Hold",
        "partial(PIM,VLM|RV) on certified panel",
    ),
    (
        "info.object_leadlag_map",
        "Hold",
        "hourly lead-lag vs mid_ret/RV/notional — descriptive map not α",
    ),
    (
        "info.kraken_spot_vs_2venue",
        "Hold",
        "spot_l2 subpanel vs absent_2venue; trade_synth QUARANTINED (PROXY/NOT TOB)",
    ),
    (
        "info.day_factor_commonality",
        "Hold",
        "day / ToD PCA on certified panel",
    ),
    (
        "info.object_use_map",
        "Hold",
        "APPLICATIONS.md risk/exec/policy routing — 0 Promote",
    ),
    ("disc.lstar_gmm", "Park", "γ/c unidentified on short tape"),
    ("disc.constrained_dealer_dgp", "Park", "qualitative toy only until calibrated"),
    (
        "risk.cdme_falsifier_board",
        "Hold",
        "Pass-2 falsifiers in out/pass2/ — 0 Promote",
    ),
    ("alpha.tob_cross_arb", "Kill", "detection ≠ sized arb; trade_synth PROXY never Promote"),
    ("risk.bank_cds_var", "Kill", "no public crypto CDS/VaR"),
]
