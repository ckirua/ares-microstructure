from __future__ import annotations
#!/usr/bin/env python3
"""Paper-live — continuous crash-risk overlay (shadow only).

Long-running poll loop:
  warehouse tape refresh → SSM 10bps/ic5 gate → kill-ladder (+ Nanex escalate,
  optional ladder+confirm) → shadow fills at trade print → rolling RISK_REPORT.

Examples:
  python3 run_paper_live.py --poll
  python3 run_paper_live.py --iterations 3 --interval 5
  python3 run_paper_live.py --day 2026-09-30 --iterations 1

No live orders. ClickHouse MCP banned. Never mercat/gateway OE.
"""


import argparse
import json
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parent
sys.path.insert(0, str(PKG))

from live.config import load_config  # noqa: E402
from live.logging_setup import setup_logging  # noqa: E402
from live.loop import run_loop  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Paper-live continuous shadow sim (crash risk overlay)"
    )
    ap.add_argument("--config", default=str(PKG / "config.yaml"))
    ap.add_argument("--venue", default="", help="Override venue (default hyperliquid)")
    ap.add_argument("--symbol", default="", help="Override symbol (default ETH)")
    ap.add_argument(
        "--day",
        default="",
        help="Pin UTC day YYYY-MM-DD (default: roll with UTC today)",
    )
    ap.add_argument(
        "--interval",
        type=float,
        default=None,
        help="Poll interval seconds (default: config poll_interval_s ≈ 10)",
    )
    ap.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Number of polls (0 = forever). Default 3 for safe smoke.",
    )
    ap.add_argument(
        "--poll",
        action="store_true",
        help="Run forever (iterations=0)",
    )
    ap.add_argument("--out-dir", default="", help="Override output root")
    ap.add_argument(
        "--log-file",
        default="",
        help="Override log path (default logs/paper_live.log)",
    )
    ap.add_argument("--figs", action="store_true", help="Write PNG figs on each report")
    ap.add_argument("--quiet", action="store_true", help="Log file only (no stdout)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.venue:
        cfg["venue"] = args.venue.lower()
    if args.symbol:
        cfg["symbol"] = args.symbol.upper()
    cfg["live_orders"] = False

    out_root = Path(args.out_dir) if args.out_dir else PKG / str(cfg.get("out_dir") or "out")
    out_root.mkdir(parents=True, exist_ok=True)

    log_path = (
        Path(args.log_file)
        if args.log_file
        else PKG / str(cfg.get("log_dir") or "logs") / str(cfg.get("log_file") or "paper_live.log")
    )
    setup_logging(
        log_path,
        rotate=str(cfg.get("log_rotate") or "daily"),
        max_bytes=int(cfg.get("log_max_bytes") or 10 * 1024 * 1024),
        backup_count=int(cfg.get("log_backup_count") or 14),
        quiet=args.quiet,
    )

    iterations = 0 if args.poll else int(args.iterations)
    day = args.day.strip() or None

    result = run_loop(
        cfg=cfg,
        out_root=out_root,
        interval_s=args.interval,
        iterations=iterations,
        day=day,
        write_figs=args.figs,
    )
    # Compact stdout summary for smoke / journal
    brief = {
        "n_polls": result.get("n_polls"),
        "last_ok": (result.get("last") or {}).get("ok"),
        "last_day": (result.get("last") or {}).get("day"),
        "out_dir": (result.get("last") or {}).get("out_dir"),
        "risk_report_md": (result.get("last") or {}).get("risk_report_md"),
        "log_file": str(log_path),
        "live_orders": False,
    }
    print(json.dumps(brief, indent=2))


if __name__ == "__main__":
    main()
