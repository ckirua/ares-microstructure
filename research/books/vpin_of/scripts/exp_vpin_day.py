#!/usr/bin/env python3
"""Single-day VPIN summary (Pass 1 hook).

Example:
  python3 scripts/exp_vpin_day.py --venue hyperliquid --symbol ETH --day 2026-09-30

Writes: out/vpin_day/{venue}_{symbol}_{day}.json
Updates: chapters/vpin_construction/EXP_REPORT.md (stub summary)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import normalize_venue, resolve_days, vpin_day_features  # noqa: E402

OUT = BOOK / "out" / "vpin_day"
CH = BOOK / "chapters" / "vpin_construction"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--venue", default="hyperliquid")
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--day", default=None)
    ap.add_argument("--max-files", type=int, default=24)
    ap.add_argument("--n-buckets-window", type=int, default=50)
    ap.add_argument("--bucket-scale", type=float, default=50.0)
    args = ap.parse_args()
    v = normalize_venue(args.venue)
    day = args.day
    if not day:
        days = resolve_days(None, v, n=3)
        day = days[-2] if len(days) >= 2 else days[-1]
    feat = vpin_day_features(
        v,
        args.symbol,
        day,
        max_files=args.max_files,
        n_buckets_window=args.n_buckets_window,
        bucket_scale=args.bucket_scale,
    )
    summary = feat["vpin_summary"]
    out_rec = {
        "venue": v,
        "symbol": args.symbol,
        "day": day,
        "instrument": feat.get("instrument"),
        "completeness": feat.get("completeness"),
        "bucket_volume": feat.get("bucket_volume"),
        "vpin_summary": {k: summary[k] for k in summary if k != "vpin_ci95"},
        "vpin_ci95": summary.get("vpin_ci95"),
        "vpin_path_finite": feat.get("vpin_path_finite"),
        "vpin_path_last": feat.get("vpin_path_last"),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    slug = f"{v}_{args.symbol}_{day}.json"
    (OUT / slug).write_text(json.dumps(out_rec, indent=2) + "\n")
    promote = bool(
        feat.get("completeness", {}).get("complete")
        and summary.get("n_buckets", 0) >= 20
        and np.isfinite(summary.get("mean_vpin", float("nan")))
    )
    CH.mkdir(parents=True, exist_ok=True)
    md = [
        f"# VPIN construction — {args.symbol} {v} {day}",
        "",
        f"- complete: **{feat.get('completeness', {}).get('complete')}**",
        f"- n_trades: **{feat.get('completeness', {}).get('n')}**",
        f"- bucket_volume: **{feat.get('bucket_volume')}**",
        f"- mean_vpin: **{summary.get('mean_vpin')}** n_buckets={summary.get('n_buckets')}",
        f"- gate `cont.vpin_constructed`: **{'Promote' if promote else 'Hold'}**",
        "",
        f"Artifact: `out/vpin_day/{slug}`",
    ]
    (CH / "EXP_REPORT.md").write_text("\n".join(md) + "\n")
    print(json.dumps(out_rec, indent=2))


if __name__ == "__main__":
    main()
