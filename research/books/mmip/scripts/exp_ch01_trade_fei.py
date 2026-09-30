#!/usr/bin/env python3
"""Ch.1 iterate: trade-notional FEI on HL tape (single venue → hourly as spatial proxy note).

True multi-venue trade FEI needs Lit/RX trade tables; here we report:
  - HL notional by hour FEI (temporal)
  - Optional binance public aggTrades REST vs HL same window if requested
Paper only.
"""
from __future__ import annotations
import json, math, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

BOOK_ROOT = Path(__file__).resolve().parents[1]
ROOT = BOOK_ROOT.parents[2]  # repo root (mmip → books → research → repo)
OUT = BOOK_ROOT / "out" / "ch01_fragmentation"
STARTARB = Path("/home/dev/srv/ares-startarb")

def fei(q):
    q = np.asarray(q, float); s = q.sum()
    if s <= 0: return 0.0
    q = q/s; n = int((q>0).sum())
    return 0.0 if n<=1 else float(-np.sum(q[q>0]*np.log(q[q>0]))/math.log(n))

def main():
    sys.path.insert(0, str(STARTARB/"src"))
    from startarb.env import ensure_env
    ensure_env()
    from startarb.data.trades import load_trade_tape
    days = ["2026-09-14","2026-09-15","2026-09-16","2026-09-25","2026-09-26"]
    rows = []
    for day in days:
        tape = load_trade_tape("hyperliquid","ETH",days=[day], max_files=16)
        notional = tape.price * tape.qty_coin
        h = ((tape.ts_ns // 1_000_000_000) % 86400) // 3600
        vol = np.array([float(notional[h==i].sum()) for i in range(24)])
        rows.append({"day": day, "n": len(tape), "fei_hourly_notional": fei(vol),
                     "total_notional": float(vol.sum()), "hourly_share": (vol/vol.sum()).tolist() if vol.sum()>0 else []})
        print(day, "n", len(tape), "fei_h", rows[-1]["fei_hourly_notional"])
    payload = {"created_at": datetime.now(timezone.utc).isoformat(),
               "note": "Single-venue HL: FEI over UTC hours is temporal concentration, not spatial fragmentation. Multi-venue trade FEI still todo.",
               "days": rows,
               "mean_fei_hourly": float(np.mean([r["fei_hourly_notional"] for r in rows]))}
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT/"exp_ch01_trade_fei_eth_summary.json"
    p.write_text(json.dumps(payload, indent=2))
    (OUT/"exp_ch01_trade_fei_eth_REPORT.md").write_text(
        f"# Ch1 iterate — trade notional FEI (HL ETH hourly)\n\n"
        f"- Mean hourly-share FEI: **{payload['mean_fei_hourly']:.3f}**\n"
        f"- Spatial multi-venue trade FEI: **blocked** until Lit/RX/Binance tapes wired.\n"
        f"- Artifact: `{p}`\n")
    print("wrote", p)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
