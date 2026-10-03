#!/usr/bin/env python3
"""Pass-1 squeeze regimes: GEX+ scarcity vs RV/range; stress/calm splits."""

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

import exp_gex_panel as gex  # noqa: E402
from _data import ensure_env  # noqa: E402
from certified_panel import gex_panel_days, primary_days  # noqa: E402
from research.lib.squeeze import regime_split_corr, squeeze_intensity  # noqa: E402

OUT = BOOK / "out" / "squeeze_regimes"


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
        if not rec.get("ok"):
            rows.append({"day": day, "ok": False, "error": rec.get("error")})
            continue
        rows.append(
            {
                "day": day,
                "ok": True,
                "gex": rec["gex"],
                "vex": rec["vex"],
                "gex_plus": rec["gex_plus"],
                "squeeze_intensity": rec["squeeze_intensity"],
                "scarce": rec["scarce"],
                "hl_range": rec["hl_range"],
                "hl_rv": rec["hl_rv"],
                "db_range": rec["db_range"],
                "ddoi_mode": rec["ddoi_mode"],
            }
        )
        (OUT / f"day_{day}.json").write_text(json.dumps(gex._jsonable(rows[-1]), indent=2))
        print(day, "scarce", rec["scarce"], "GEX+", rec["gex_plus"], "range", rec["hl_range"])

    ok = [r for r in rows if r.get("ok")]
    if ok:
        gp = np.array([r["gex_plus"] for r in ok], dtype=np.float64)
        rng = np.array([r["hl_range"] for r in ok], dtype=np.float64)
        scarce = np.array([bool(r["scarce"]) for r in ok])
        # stress = upper half of |squeeze intensity|
        inten = np.array([r["squeeze_intensity"] for r in ok], dtype=np.float64)
        med = float(np.nanmedian(inten)) if inten.size else 0.0
        stress = inten >= med
        split = regime_split_corr(gp, rng, stress)
    else:
        split = {}
        gp = np.zeros(0)
        scarce = np.zeros(0, dtype=bool)

    summary = {
        "n_ok": len(ok),
        "days_ok": [r["day"] for r in ok],
        "n_scarce": int(scarce.sum()) if scarce.size else 0,
        "gex_plus_mean": float(np.nanmean(gp)) if ok else None,
        "regime_split_gexplus_vs_range": split,
        "decision": "Hold",
        "promote": False,
        "rows": gex._jsonable(rows),
    }
    (OUT / "summary.json").write_text(json.dumps(gex._jsonable(summary), indent=2))
    (OUT / "panel_rows.json").write_text(json.dumps(gex._jsonable(ok), indent=2))
    print(json.dumps({k: summary[k] for k in summary if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
