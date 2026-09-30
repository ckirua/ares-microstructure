#!/usr/bin/env python3
"""TI-v-fade paper shadow CLI — causal fade on real tape (not MM, not live).

Examples:
  python3 run_v_fade_paper.py --day 2026-09-04
  python3 run_v_fade_paper.py --day 2026-09-04 --venue hyperliquid --symbol ETH
  python3 run_v_fade_paper.py --days 2026-09-04,2026-09-05
  python3 run_v_fade_paper.py --panel-days
  python3 run_v_fade_paper.py --panel-days --extra-venues deribit,kraken
  python3 run_v_fade_paper.py --panel-days --confirm-s 0 --exit-s 3 --always-fade
  python3 run_v_fade_paper.py --panel-days --from-gap-best   # load out/gap_summary.json

Honesty: research_sim · RT=4bps · mid_mo null → tape mo · live_orders=False.
ALWAYS reports BOTH lab identity (−mo5s−RT) AND path PnL (entry→exit−RT).
path ≠ lab — do not pretend otherwise. ClickHouse MCP banned.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parent
sys.path.insert(0, str(PKG))

from harness.causal import jsonable  # noqa: E402
from harness.config import load_config  # noqa: E402
from harness.pipeline import run_v_fade_day, run_v_fade_panel  # noqa: E402

DEFAULT_PANEL_DAYS = [
    "2026-09-04",
    "2026-09-05",
    "2026-09-06",
    "2026-09-07",
    "2026-09-08",
    "2026-09-09",
    "2026-09-10",
]


def main() -> None:
    ap = argparse.ArgumentParser(
        description="V-fade paper: detect → causal@2s → shadow taker → risk report"
    )
    ap.add_argument("--day", default="", help="Single UTC day YYYY-MM-DD")
    ap.add_argument("--days", default="", help="Comma-separated UTC days")
    ap.add_argument(
        "--panel-days",
        action="store_true",
        help="Run Phase-4 research days 2026-09-04…10",
    )
    ap.add_argument("--config", default=str(PKG / "config.yaml"))
    ap.add_argument("--venue", default="", help="Override config venue (default hyperliquid)")
    ap.add_argument("--symbol", default="", help="Override config symbol (default ETH)")
    ap.add_argument(
        "--extra-venues",
        default="",
        help="Comma list (e. for deribit,kraken) — full fade sim per venue",
    )
    ap.add_argument("--out-dir", default="", help="Override output root")
    ap.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Run even if day completeness flags fail",
    )
    ap.add_argument("--quiet", action="store_true")
    # Executable path knobs (default = lab-locked confirm=2 / exit=5)
    ap.add_argument("--confirm-s", type=float, default=None, help="Entry delay after ts_end")
    ap.add_argument("--exit-s", type=float, default=None, help="Time-stop after ts_end")
    ap.add_argument("--v-threshold-r2", type=float, default=None, help="V recovery threshold")
    ap.add_argument("--soft-confirm-r1", type=float, default=None, help="Soft 1s recovery floor")
    ap.add_argument("--adverse-stop-bps", type=float, default=None, help="Crash-continue stop from entry")
    ap.add_argument(
        "--always-fade",
        action="store_true",
        help="Fade all gated events (no causal V gate); typical with --confirm-s 0",
    )
    ap.add_argument(
        "--no-adverse-stop",
        action="store_true",
        help="Disable adverse stop (set threshold to 1e9)",
    )
    ap.add_argument(
        "--from-gap-best",
        action="store_true",
        help="Apply best executable params from out/gap_summary.json if present",
    )
    args = ap.parse_args()

    cfg = load_config(args.config)
    if cfg.get("live_orders"):
        print("[v_fade_paper] REFUSE: live_orders=True (K8)", file=sys.stderr)
        sys.exit(2)
    if args.venue:
        cfg["venue"] = args.venue.lower()
    if args.symbol:
        cfg["symbol"] = args.symbol.upper()
    if args.extra_venues:
        cfg["extra_venues"] = [v.strip().lower() for v in args.extra_venues.split(",") if v.strip()]
    if args.allow_incomplete:
        cfg["require_complete_day"] = False

    vf = dict(cfg.get("v_fade") or {})
    if args.from_gap_best:
        gap_path = PKG / "out" / "gap_summary.json"
        if not gap_path.is_file():
            print(f"[v_fade_paper] --from-gap-best but missing {gap_path}", file=sys.stderr)
            sys.exit(2)
        gap = json.loads(gap_path.read_text())
        best = gap.get("best_policy") or {}
        if not best:
            print("[v_fade_paper] gap_summary.json has no best_policy", file=sys.stderr)
            sys.exit(2)
        vf["confirm_s"] = float(best.get("confirm_s", vf.get("confirm_s", 2.0)))
        vf["exit_s"] = float(best.get("exit_s", vf.get("exit_s", 5.0)))
        vf["v_threshold_r2"] = float(best.get("v_threshold_r2", vf.get("v_threshold_r2", 0.5)))
        vf["soft_confirm_r1"] = float(best.get("soft_confirm_r1", vf.get("soft_confirm_r1", 0.35)))
        adv = best.get("adverse_stop_bps")
        vf["adverse_stop_bps"] = float(adv) if adv is not None else 1e9
        vf["always_fade"] = bool(best.get("always_fade", False))
        print(
            f"[v_fade_paper] from-gap-best decision={gap.get('decision')} "
            f"confirm={vf['confirm_s']} exit={vf['exit_s']} "
            f"v_thr={vf['v_threshold_r2']} always_fade={vf['always_fade']}",
            file=sys.stderr,
        )
    if args.confirm_s is not None:
        vf["confirm_s"] = float(args.confirm_s)
    if args.exit_s is not None:
        vf["exit_s"] = float(args.exit_s)
    if args.v_threshold_r2 is not None:
        vf["v_threshold_r2"] = float(args.v_threshold_r2)
    if args.soft_confirm_r1 is not None:
        vf["soft_confirm_r1"] = float(args.soft_confirm_r1)
    if args.adverse_stop_bps is not None:
        vf["adverse_stop_bps"] = float(args.adverse_stop_bps)
    if args.no_adverse_stop:
        vf["adverse_stop_bps"] = 1e9
    if args.always_fade:
        vf["always_fade"] = True
    cfg["v_fade"] = vf

    out_root = Path(args.out_dir) if args.out_dir else PKG / str(cfg.get("out_dir") or "out")

    if args.panel_days:
        days = list(DEFAULT_PANEL_DAYS)
    elif args.days:
        days = [d.strip() for d in args.days.split(",") if d.strip()]
    elif args.day:
        days = [args.day.strip()]
    else:
        ap.error("Provide --day, --days, or --panel-days")

    if len(days) == 1 and not args.panel_days:
        r = run_v_fade_day(
            days[0],
            cfg=cfg,
            out_root=out_root,
            quiet=args.quiet,
        )
        print(json.dumps(jsonable(r.get("summary") or r), indent=2))
        return

    rollup = run_v_fade_panel(days, cfg=cfg, out_root=out_root, quiet=args.quiet)
    lab = rollup.get("lab_pnl_net_bps") or {}
    path = rollup.get("path_pnl_net_bps") or {}
    # Compact stdout for desk — BOTH scoreboards always
    brief = {
        "n_ok": rollup.get("n_ok"),
        "n_faded": rollup.get("n_faded"),
        "params": {
            "confirm_s": vf.get("confirm_s"),
            "exit_s": vf.get("exit_s"),
            "v_threshold_r2": vf.get("v_threshold_r2"),
            "soft_confirm_r1": vf.get("soft_confirm_r1"),
            "adverse_stop_bps": vf.get("adverse_stop_bps"),
            "always_fade": bool(vf.get("always_fade", False)),
        },
        "lab_identity": {
            "formula": "-mo_5s - RT4",
            "pnl_net_bps": lab,
            "note": "NOT executable at confirm entry — credits pre-entry rebound",
        },
        "path_executable": {
            "formula": "side*(exit/entry-1)*1e4 - RT4",
            "pnl_net_bps": path,
            "note": "entry@ts_end+confirm_s → exit markout on tape",
        },
        "lab_pnl_net_bps": lab,
        "path_pnl_net_bps": path,
        "gap_lab_minus_path_mean": (
            (lab.get("mean") - path.get("mean"))
            if lab.get("mean") is not None and path.get("mean") is not None
            else None
        ),
        "early_mean_lab": rollup.get("early_mean"),
        "late_mean_lab": rollup.get("late_mean"),
        "hit_rate_lab": rollup.get("hit_rate"),
        "kills": {
            "decision": (rollup.get("kills") or {}).get("decision"),
            "any_kill": (rollup.get("kills") or {}).get("any_kill"),
            "flags": (rollup.get("kills") or {}).get("flags"),
            "note": "Kills currently keyed off lab identity; path CI is the live gate",
        },
        "honesty": {
            "path_equals_lab": False,
            "alpha_claim": False,
            "live_orders": False,
        },
        "out_dir": str(out_root),
        "risk_report": str(out_root / "RISK_REPORT.md"),
        "rollup_json": str(out_root / "rollup.json"),
    }
    print(json.dumps(jsonable(brief), indent=2))


if __name__ == "__main__":
    main()
