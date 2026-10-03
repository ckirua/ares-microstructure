#!/usr/bin/env python3
"""Pass-1 VEX-focused panel + GEX+ (reuses GEX chain builder)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
SCRIPTS = Path(__file__).resolve().parent
for _p in (
    str(Path(os.environ.get("WAREHOUSE_SRC") or (Path.home() / "lab" / "lab-n2070" / "warehouse" / "src"))),
    str((Path(os.environ.get("ARES_STARTARB") or (Path.home() / "srv" / "ares-startarb")) / "src")),
    str(ROOT),
    str(SCRIPTS),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Reuse day pack from gex panel
import exp_gex_panel as gex  # noqa: E402
from _data import ensure_env  # noqa: E402
from certified_panel import gex_panel_days, primary_days  # noqa: E402

OUT = BOOK / "out" / "vex_vanna"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--days", nargs="*", default=None)
    args = ap.parse_args()
    ensure_env()
    OUT.mkdir(parents=True, exist_ok=True)
    days = list(args.days) if args.days else (gex_panel_days() or primary_days())
    rows = []
    for day in days:
        rec = gex._day_pack(args.symbol, day)
        slim = {
            "day": day,
            "ok": rec.get("ok"),
            "error": rec.get("error"),
            "spot": rec.get("spot"),
            "vex": rec.get("vex"),
            "gex": rec.get("gex"),
            "gex_plus": rec.get("gex_plus"),
            "ddoi_mode": rec.get("ddoi_mode"),
            "hl_range": rec.get("hl_range"),
            "hl_rv": rec.get("hl_rv"),
            "dealer_sign": rec.get("dealer_sign"),
            "honesty": rec.get("honesty"),
        }
        (OUT / f"day_{day}.json").write_text(json.dumps(gex._jsonable(slim), indent=2))
        rows.append(slim)
        print(day, slim.get("vex"), slim.get("gex_plus"))
    ok = [r for r in rows if r.get("ok")]
    vex = np.array([r["vex"] for r in ok], dtype=np.float64)
    rng = np.array([r["hl_range"] for r in ok], dtype=np.float64)
    corr = None
    m = np.isfinite(vex) & np.isfinite(rng)
    if m.sum() >= 3:
        corr = float(np.corrcoef(vex[m], rng[m])[0, 1])
    summary = {
        "n_ok": len(ok),
        "days_ok": [r["day"] for r in ok],
        "vex_mean": float(np.nanmean(vex)) if ok else None,
        "corr_vex_hl_range": corr,
        "decision": "Hold",
        "rows": gex._jsonable(rows),
    }
    (OUT / "summary.json").write_text(json.dumps(gex._jsonable(summary), indent=2))
    print(json.dumps({k: summary[k] for k in summary if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
