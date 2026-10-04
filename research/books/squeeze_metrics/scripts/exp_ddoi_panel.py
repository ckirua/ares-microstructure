#!/usr/bin/env python3
"""Pass-1 DDOI trade-flow proxy panel (option trades → signed dealer inventory).

Warehouse open_interest is futures-only — never used as option DDOI.
"""

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

from _data import ensure_env, load_eth_option_trades_day  # noqa: E402
from certified_panel import DDOI_LABEL, gex_panel_days, primary_days  # noqa: E402
from ares_micro.flow.squeeze import accumulate_ddoi_by_instrument, ddoi_from_trade_flow  # noqa: E402

OUT = BOOK / "out" / "ddoi_positions"


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.floating, float)):
        x = float(obj)
        return x if np.isfinite(x) else None
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, np.ndarray):
        return _jsonable(obj.tolist())
    return obj


def day_ddoi(symbol: str, day: str) -> dict[str, Any]:
    tr = load_eth_option_trades_day(day, underlying=symbol)
    if not tr.get("ok"):
        return {"day": day, "ok": False, "error": tr.get("error"), "label": DDOI_LABEL}
    cols = tr["columns"]
    qty = np.asarray(cols["md_qty_lots"], dtype=np.float64)
    med = float(np.nanmedian(np.abs(qty))) if qty.size else 0.0
    scale = 1e8 if med > 1e5 else 1.0
    flow = ddoi_from_trade_flow(qty / scale, cols["aggressor_side"])
    by_id = accumulate_ddoi_by_instrument(cols["instrument_id"], flow)
    vals = np.array(list(by_id.values()), dtype=np.float64) if by_id else np.zeros(0)
    return {
        "day": day,
        "ok": True,
        "label": DDOI_LABEL,
        "n_trades": int(tr["n"]),
        "n_instruments": int(tr["n_instruments"]),
        "ddoi_sum": float(np.nansum(vals)) if vals.size else 0.0,
        "ddoi_abs_sum": float(np.nansum(np.abs(vals))) if vals.size else 0.0,
        "ddoi_n_nonzero": int(np.count_nonzero(vals)),
        "top_instruments": sorted(
            ((int(k), float(v)) for k, v in by_id.items()),
            key=lambda kv: abs(kv[1]),
            reverse=True,
        )[:15],
        "honesty": "Trade-flow DDOI proxy — not paper transaction+ΔOI verified DDOI",
    }


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
        rec = day_ddoi(args.symbol, day)
        (OUT / f"day_{day}.json").write_text(json.dumps(_jsonable(rec), indent=2))
        rows.append(rec)
        print(day, "ok" if rec.get("ok") else "FAIL", rec.get("n_trades"), rec.get("ddoi_sum"))
    ok = [r for r in rows if r.get("ok")]
    summary = {
        "n_ok": len(ok),
        "days_ok": [r["day"] for r in ok],
        "mean_abs_ddoi": float(np.mean([r["ddoi_abs_sum"] for r in ok])) if ok else None,
        "label": DDOI_LABEL,
        "decision": "Hold",
        "rows": _jsonable(rows),
    }
    (OUT / "summary.json").write_text(json.dumps(_jsonable(summary), indent=2))
    print(json.dumps({k: summary[k] for k in summary if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
