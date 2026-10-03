#!/usr/bin/env python3
"""Refresh vpin_of data inventory (listing cache + completeness probes).

ClickHouse MCP banned. Writes:
  out/data_inventory/inventory.json
  out/data_inventory/INVENTORY_REPORT.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import CORE_VENUES, load_day_trades, resolve_days  # noqa: E402

OUT = BOOK / "out" / "data_inventory"
SYMBOLS = ("ETH", "BTC", "SOL")
PROBE_DAYS = ("2026-09-30", "2026-09-29", "2026-09-28")


def _first_nonempty_day(venue: str, symbol: str) -> dict:
    listing = resolve_days(None, venue, n=999)
    for day in PROBE_DAYS:
        if listing and day not in listing:
            continue
        try:
            rec = load_day_trades(venue, symbol, day, max_files=16, quiet=True)
            c = rec["completeness"]
            if int(c.get("n", 0)) > 0:
                return {
                    "underlying": symbol,
                    "venue": venue,
                    "day": day,
                    "n_trades": c.get("n"),
                    "complete": c.get("complete"),
                    "coverage": c.get("coverage"),
                    "reasons": c.get("reasons"),
                }
        except Exception as exc:  # noqa: BLE001
            return {"underlying": symbol, "venue": venue, "day": day, "error": f"{type(exc).__name__}: {exc}"}
    return {"underlying": symbol, "venue": venue, "error": "no_nonempty_probe_day", "probe_days": list(PROBE_DAYS)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.parse_args()
    listing_span = {}
    for v in CORE_VENUES:
        days = resolve_days(None, v, n=999)
        listing_span[v] = {"first": days[0] if days else None, "last": days[-1] if days else None, "n_days": len(days)}
    rows = [_first_nonempty_day(v, s) for s in SYMBOLS for v in CORE_VENUES]
    payload = {"listing_span": listing_span, "probe_rows": rows, "symbols": list(SYMBOLS), "venues": list(CORE_VENUES)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "inventory.json").write_text(json.dumps(payload, indent=2) + "\n")
    lines = [
        "# Data inventory report (auto)",
        "",
        "Regenerate: `python3 scripts/exp_data_inventory.py`",
        "",
        "## Listing span",
        "",
        "| Venue | First | Last | n_days |",
        "|-------|-------|------|--------|",
    ]
    for v, meta in listing_span.items():
        lines.append(f"| {v} | {meta['first']} | {meta['last']} | {meta['n_days']} |")
    lines.extend(["", "## Probe rows", ""])
    for r in rows:
        lines.append(f"- **{r.get('underlying')}/{r.get('venue')}** day={r.get('day')} n={r.get('n_trades')} complete={r.get('complete')} coverage={r.get('coverage')} {r.get('reasons') or r.get('error', '')}")
    (OUT / "INVENTORY_REPORT.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
