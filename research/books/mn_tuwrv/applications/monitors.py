"""Thin TSRV / noise monitors for mn_tuwrv (Hold board, no orders, no fake PnL).

Mirrors cd_me applications/monitors style: read expand_panel + depth_predict
artifacts, emit JSON alert rows for a desk strip.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

BOOK = Path(__file__).resolve().parents[1]
EXPAND = BOOK / "out" / "expand_panel" / "expand_panel.json"
DEPTH = BOOK / "out" / "depth_predict" / "depth_predict.json"
OUT = BOOK / "applications" / "out"

GATE_LABELS = {
    "cont.sparse_rv_only": "Kill",
    "cont.noise_mid_clock": "Hold",
    "cont.tsrv_first_adj": "Hold",
    "liq.noise_vs_spread": "Hold",
}


def _load_expand() -> dict:
    return json.loads(EXPAND.read_text())


def _load_depth() -> dict | None:
    if not DEPTH.is_file():
        return None
    return json.loads(DEPTH.read_text())


def monitor_day(venue: str, symbol: str, day: str) -> dict[str, Any]:
    """Emit monitor snapshot for one venue-day from frozen panel (no live orders)."""
    expand = _load_expand()
    rows = [r for r in expand["rows"] if r.get("ok")]
    # history for same venue×symbol
    hist = [r for r in rows if r["venue"] == venue and r["symbol"] == symbol]
    hist = sorted(hist, key=lambda r: r["day"])
    cur = next((r for r in hist if r["day"] == day), None)
    if cur is None:
        return {"ok": False, "reason": "day_not_in_panel", "venue": venue, "symbol": symbol, "day": day}

    def _noise(r: dict) -> float:
        return float(r.get("noise_std", (r.get("calendar") or {}).get("noise_std", float("nan"))))

    noises = np.asarray([_noise(r) for r in hist if r["day"] <= day], dtype=np.float64)
    noises = noises[np.isfinite(noises)]
    n_cur = _noise(cur)
    med = float(np.median(noises)) if noises.size else float("nan")
    mad = float(np.median(np.abs(noises - med))) if noises.size else float("nan")
    z = (n_cur - med) / (1.4826 * mad) if (np.isfinite(mad) and mad > 0) else float("nan")

    mid_ff = float(cur.get("fifth_over_fourth_mid", float("nan")))
    gap = float(cur.get("sparse_minus_tsrv", float("nan")))
    gaps = np.asarray(
        [float(r.get("sparse_minus_tsrv", float("nan"))) for r in hist if r["day"] <= day],
        dtype=np.float64,
    )
    gaps = gaps[np.isfinite(gaps)]
    gap_med = float(np.median(gaps)) if gaps.size else float("nan")

    alerts = []
    if np.isfinite(z) and abs(z) > 2:
        alerts.append(
            {
                "id": "mon.noise_std_level",
                "level": "flag",
                "z": z,
                "action": "risk strip only — liq.noise_vs_spread still Hold",
            }
        )
    if np.isfinite(mid_ff) and mid_ff > 3.0:
        alerts.append(
            {
                "id": "mon.mid_fifth_fourth",
                "level": "warn",
                "mid_fifth_fourth": mid_ff,
                "action": "distrust mid RV; prefer TSRV on mid grid",
            }
        )
    if np.isfinite(gap) and np.isfinite(gap_med) and gap > gap_med * 1.5 and gap_med > 0:
        alerts.append(
            {
                "id": "mon.tsrv_sparse_gap",
                "level": "info",
                "gap": gap,
                "gap_med": gap_med,
                "action": "prefer first_adj for σ budgets",
            }
        )

    depth = _load_depth()
    thesis = {}
    if depth:
        thesis = {
            "signature_slope_med": depth.get("tape_depth", {}).get("signature", {}).get("median_fine_log_slope"),
            "acf_lag1_med": depth.get("tape_depth", {}).get("noise_acf", {}).get("median_lag1"),
        }

    return {
        "ok": True,
        "venue": venue,
        "symbol": symbol,
        "day": day,
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "noise_std": n_cur,
            "noise_z_vs_hist": z,
            "fifth_over_fourth_cal": float(cur.get("fifth_over_fourth_cal", float("nan"))),
            "fifth_over_fourth_mid": mid_ff,
            "sparse_minus_tsrv": gap,
            "first_adj": float(cur.get("first_adj", float("nan"))),
            "fourth": float(cur.get("fourth", float("nan"))),
        },
        "alerts": alerts,
        "gate_labels": GATE_LABELS,
        "thesis_panel": thesis,
        "orders": [],  # hard: never place
        "pnl_claim": False,
    }


def run_latest_snapshot() -> dict[str, Any]:
    expand = _load_expand()
    rows = [r for r in expand["rows"] if r.get("ok")]
    if not rows:
        return {"ok": False, "reason": "empty_panel"}
    # latest day per venue×symbol
    latest: dict[tuple[str, str], dict] = {}
    for r in rows:
        key = (r["venue"], r["symbol"])
        if key not in latest or r["day"] > latest[key]["day"]:
            latest[key] = r
    snaps = [monitor_day(r["venue"], r["symbol"], r["day"]) for r in latest.values()]
    out = {
        "ok": True,
        "n": len(snaps),
        "snapshots": snaps,
        "n_alerts": sum(len(s.get("alerts") or []) for s in snaps),
        "ts_utc": datetime.now(timezone.utc).isoformat(),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "monitor_snapshot.json"
    path.write_text(json.dumps(out, indent=2))
    out["path"] = str(path)
    return out


if __name__ == "__main__":
    print(json.dumps(run_latest_snapshot(), indent=2)[:2000])
