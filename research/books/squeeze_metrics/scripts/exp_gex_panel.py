#!/usr/bin/env python3
"""Pass-1 GEX / VEX / GEX+ panel on certified ETH option+TOB days.

DDOI = trade-flow proxy (warehouse option OI absent). IV = Deribit options.
Underlying S = Deribit ETH-PERPETUAL mark. Real HL+Deribit TOB for RV join.
Never Promote TOB-cross α. ClickHouse MCP banned.
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
WAREHOUSE_SRC = Path(
    os.environ.get("WAREHOUSE_SRC")
    or ((Path(os.environ.get("WAREHOUSE_ROOT") or (Path.home() / "lab" / "lab-n2070" / "warehouse")) / "src"))
)
STARTARB = Path(os.environ.get("ARES_STARTARB") or (Path.home() / "srv" / "ares-startarb"))
for _p in (str(WAREHOUSE_SRC), str(STARTARB / "src"), str(ROOT), str(SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from _data import (  # noqa: E402
    ensure_env,
    load_day_marks,
    load_eth_option_iv_day,
    load_eth_option_trades_day,
    load_venue_tob,
)
from certified_panel import (  # noqa: E402
    DDOI_LABEL,
    annotate_title,
    gex_panel_days,
    primary_days,
)
from research.lib.squeeze import (  # noqa: E402
    LABEL_TRADE_DDOI,
    LABEL_UNIT_OI,
    accumulate_ddoi_by_instrument,
    chain_exposures,
    ddoi_from_trade_flow,
    dealer_sign_from_gex,
    mid_range,
    realized_vol,
    scarcity_flag,
    squeeze_intensity,
    unsigned_unit_ddoi,
)

OUT = BOOK / "out" / "gex_implied_book"


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


def _spot_from_marks(marks: dict[str, Any]) -> float:
    mid = marks.get("mid")
    if mid is None:
        px = marks.get("price") or marks.get("mark")
        mid = px
    arr = np.asarray(mid, dtype=np.float64) if mid is not None else np.asarray([])
    arr = arr[np.isfinite(arr) & (arr > 0)]
    if arr.size == 0:
        return float("nan")
    return float(arr[arr.size // 2])  # median-ish via mid index; use nanmedian
    # unreachable


def _day_pack(symbol: str, day: str) -> dict[str, Any]:
    iv = load_eth_option_iv_day(day, underlying=symbol)
    if not iv.get("ok"):
        return {"day": day, "ok": False, "error": iv.get("error") or "iv_fail", "iv": iv}

    marks = load_day_marks("deribit", symbol, day)
    mid = np.asarray(marks.get("mid") if marks.get("mid") is not None else marks.get("price"), dtype=np.float64)
    mid = mid[np.isfinite(mid) & (mid > 0)]
    spot = float(np.nanmedian(mid)) if mid.size else float("nan")
    if not np.isfinite(spot):
        return {"day": day, "ok": False, "error": "no_spot", "marks_n": int(mid.size)}

    # trade-flow DDOI
    ddoi_mode = LABEL_UNIT_OI
    ddoi = unsigned_unit_ddoi(int(iv["n"]), sign=1.0)
    trade_n = 0
    try:
        tr = load_eth_option_trades_day(day, underlying=symbol)
        trade_n = int(tr.get("n") or 0)
        if tr.get("ok") and trade_n > 0:
            cols = tr["columns"]
            # mercat md_qty_lots is typically 1e8-scaled contract units
            qty = np.asarray(cols["md_qty_lots"], dtype=np.float64)
            med = float(np.nanmedian(np.abs(qty))) if qty.size else 0.0
            scale = 1e8 if med > 1e5 else 1.0
            flow = ddoi_from_trade_flow(qty / scale, cols["aggressor_side"])
            by_id = accumulate_ddoi_by_instrument(cols["instrument_id"], flow)
            mapped = []
            for iid in iv["instrument_ids"]:
                mapped.append(by_id.get(int(iid), 0.0))
            ddoi = np.asarray(mapped, dtype=np.float64)
            # if all zero, fall back to unit
            if np.allclose(ddoi, 0):
                ddoi = unsigned_unit_ddoi(int(iv["n"]), sign=1.0)
                ddoi_mode = LABEL_UNIT_OI
            else:
                ddoi_mode = LABEL_TRADE_DDOI
    except Exception as exc:  # noqa: BLE001
        tr = {"error": f"{type(exc).__name__}: {exc}"}

    pack = chain_exposures(
        flags=iv["flags"],
        strikes=iv["strikes"],
        ttm_years=iv["ttm_years"],
        iv=iv["iv"],
        ddoi=ddoi,
        spot=spot,
        r=0.0,
        contract_multiplier=1.0,
        per_point=1.0,
        d_sigma=0.01,
    )

    # HL mid RV for validation scatter
    hl_rv = float("nan")
    hl_range = float("nan")
    hl_n = 0
    try:
        hl = load_venue_tob("hyperliquid", symbol, day=day)
        hlm = np.asarray(hl.get("mid"), dtype=np.float64)
        hlm = hlm[np.isfinite(hlm) & (hlm > 0)]
        hl_n = int(hlm.size)
        hl_rv = realized_vol(hlm, dt_s=60.0, annualize=False)
        hl_range = mid_range(hlm)
    except Exception as exc:  # noqa: BLE001
        hl = {"error": f"{type(exc).__name__}: {exc}"}

    db_rv = realized_vol(mid, dt_s=1.0, annualize=False) if mid.size > 3 else float("nan")
    db_range = mid_range(mid)

    gex = pack["gex"]
    vex = pack["vex"]
    gp = pack["gex_plus"]
    return {
        "day": day,
        "ok": True,
        "symbol": symbol,
        "spot": spot,
        "n_contracts": pack["n_contracts"],
        "n_finite_gex": pack["n_finite_gex"],
        "gex": gex,
        "vex": vex,
        "gex_plus": gp,
        "squeeze_intensity": squeeze_intensity(gex, vex, gex_scale=max(abs(gex), 1.0), vex_scale=max(abs(vex), 1.0)),
        "scarce": scarcity_flag(gp),
        "dealer_sign": dealer_sign_from_gex(gex),
        "ddoi_mode": ddoi_mode,
        "opt_iv_n": int(iv["n"]),
        "opt_trade_n": trade_n,
        "hl_tob_n": hl_n,
        "hl_rv": hl_rv,
        "hl_range": hl_range,
        "db_rv": db_rv,
        "db_range": db_range,
        "marks_n": int(mid.size),
        "honesty": (
            f"DDOI={ddoi_mode}; IV=warehouse options; OI futures-only unused; "
            "TOB real quotes only; monitor≠α"
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--days", nargs="*", default=None)
    args = ap.parse_args()
    ensure_env()
    OUT.mkdir(parents=True, exist_ok=True)

    days = list(args.days) if args.days else gex_panel_days()
    if not days:
        days = primary_days()
    rows = []
    for day in days:
        print(f"=== {day} ===", flush=True)
        try:
            rec = _day_pack(args.symbol, day)
        except Exception as exc:  # noqa: BLE001
            rec = {"day": day, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
        (OUT / f"day_{day}.json").write_text(json.dumps(_jsonable(rec), indent=2))
        rows.append(rec)
        if rec.get("ok"):
            print(
                f"  S={rec['spot']:.2f} GEX={rec['gex']:.4g} VEX={rec['vex']:.4g} "
                f"GEX+={rec['gex_plus']:.4g} ddoi={rec['ddoi_mode']} iv_n={rec['opt_iv_n']}",
                flush=True,
            )
        else:
            print("  FAIL", rec.get("error"), flush=True)

    ok_rows = [r for r in rows if r.get("ok")]
    gexs = np.array([r["gex"] for r in ok_rows], dtype=np.float64)
    vexs = np.array([r["vex"] for r in ok_rows], dtype=np.float64)
    rvs = np.array([r["hl_rv"] for r in ok_rows], dtype=np.float64)
    ranges = np.array([r["hl_range"] for r in ok_rows], dtype=np.float64)

    def _corr(a, b):
        m = np.isfinite(a) & np.isfinite(b)
        if m.sum() < 3:
            return None
        return float(np.corrcoef(a[m], b[m])[0, 1])

    summary = {
        "symbol": args.symbol,
        "n_days_requested": len(days),
        "n_ok": len(ok_rows),
        "days_ok": [r["day"] for r in ok_rows],
        "gex_mean": float(np.nanmean(gexs)) if ok_rows else None,
        "vex_mean": float(np.nanmean(vexs)) if ok_rows else None,
        "gex_plus_mean": float(np.nanmean(gexs + vexs)) if ok_rows else None,
        "corr_gex_hl_rv": _corr(gexs, rvs),
        "corr_gex_hl_range": _corr(gexs, ranges),
        "corr_gexplus_hl_range": _corr(gexs + vexs, ranges),
        "ddoi_modes": sorted({r.get("ddoi_mode") for r in ok_rows}),
        "title": annotate_title("GEX/VEX panel", [r["day"] for r in ok_rows], panel="panel_gex_options"),
        "decision": "Hold",
        "promote": False,
        "kill_tob_cross_alpha": True,
        "rows": _jsonable(rows),
    }
    (OUT / "summary.json").write_text(json.dumps(_jsonable(summary), indent=2))
    (OUT / "panel_rows.json").write_text(json.dumps(_jsonable(ok_rows), indent=2))
    print(json.dumps({k: summary[k] for k in summary if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
