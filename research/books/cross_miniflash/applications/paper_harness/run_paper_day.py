#!/usr/bin/env python3
"""Paper-trade harness entrypoint — one UTC day or rolling window (shadow only).

Examples:
  python run_paper_day.py --day 2026-09-04
  python run_paper_day.py --day 2026-09-04 --venue hyperliquid --symbol ETH
  python run_paper_day.py --days 2026-09-04,2026-09-05,2026-09-06
  python run_paper_day.py --panel-days --extra-venues deribit,kraken

No live orders. ClickHouse MCP banned. Warehouse + startarb loaders only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

PKG = Path(__file__).resolve().parent
sys.path.insert(0, str(PKG))

from harness.actions import jsonable  # noqa: E402
from harness.config import load_config  # noqa: E402
from harness.pipeline import run_paper_day  # noqa: E402
from harness.report import write_rollup_markdown  # noqa: E402

DEFAULT_PANEL_DAYS = [
    "2026-09-04",
    "2026-09-05",
    "2026-09-06",
    "2026-09-07",
    "2026-09-08",
    "2026-09-09",
    "2026-09-10",
]


def _extra_brief(summary: dict) -> str:
    extras = summary.get("extra_venues") or []
    parts = []
    for e in extras:
        if e.get("error"):
            parts.append(f"{e.get('venue')}:err")
        elif e.get("skip"):
            parts.append(f"{e.get('venue')}:skip")
        else:
            parts.append(f"{e.get('venue')}:g{e.get('ssm_10_n')}")
    return ",".join(parts) if parts else "—"


def main() -> None:
    ap = argparse.ArgumentParser(description="Paper harness: detect → ladder → shadow → risk report")
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
        help="Comma list (e.g. deribit,kraken) — detect/log only",
    )
    ap.add_argument("--out-dir", default="", help="Override output root")
    ap.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Run even if day completeness flags fail",
    )
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.venue:
        cfg["venue"] = args.venue.lower()
    if args.symbol:
        cfg["symbol"] = args.symbol.upper()
    if args.extra_venues:
        cfg["extra_venues"] = [v.strip().lower() for v in args.extra_venues.split(",") if v.strip()]
    if args.allow_incomplete:
        cfg["require_complete_day"] = False
    out_root = Path(args.out_dir) if args.out_dir else PKG / str(cfg.get("out_dir") or "out")

    if args.panel_days:
        days = list(DEFAULT_PANEL_DAYS)
    elif args.days:
        days = [d.strip() for d in args.days.split(",") if d.strip()]
    elif args.day:
        days = [args.day.strip()]
    else:
        ap.error("Provide --day, --days, or --panel-days")

    results = []
    for day in days:
        try:
            r = run_paper_day(
                day,
                cfg=cfg,
                out_root=out_root,
                quiet=args.quiet,
            )
            summary = r.get("summary") or {}
            delta = (summary.get("shadow") or {}).get("delta_vs_baseline") or {}
            if not delta:
                delta = (r.get("shadow_meta") or {}).get("delta_vs_baseline") or {}
            delta_s = (summary.get("shadow") or {}).get("delta_stack_vs_baseline") or {}
            if not delta_s:
                delta_s = (r.get("shadow_meta") or {}).get("delta_stack_vs_baseline") or {}
            sh = summary.get("shadow") or {}
            results.append(
                {
                    "day": day,
                    "ok": not r.get("skipped"),
                    "skipped": r.get("skipped"),
                    "out_dir": r.get("out_dir"),
                    "risk_report_md": r.get("risk_report_md"),
                    "ssm_10_n": summary.get("ssm_10_n"),
                    "n_fire": summary.get("n_fire"),
                    "n_fills": (r.get("shadow_meta") or {}).get("n_fills_ladder"),
                    "n_fills_stack": (r.get("shadow_meta") or {}).get("n_fills_stack"),
                    "fill_model": sh.get("fill_model"),
                    "abs_mo5_fire_mean": summary.get("abs_mo5_fire_mean"),
                    "mo5_fire_mean": summary.get("mo5_fire_mean"),
                    "delta_equity_bps": delta.get("delta_equity_bps"),
                    "delta_fills_in_fire": delta.get("delta_fills_in_fire"),
                    "delta_equity_incr_fire_bps": delta.get("delta_equity_incr_fire_bps"),
                    "overlay_nullified": delta.get("overlay_nullified_in_fire"),
                    "delta_stack_equity_bps": delta_s.get("delta_equity_bps"),
                    "delta_stack_n_fills": delta_s.get("delta_n_fills"),
                    "delta_stack_fills_in_fire": delta_s.get("delta_fills_in_fire"),
                    "delta_stack_equity_incr_fire_bps": delta_s.get("delta_equity_incr_fire_bps"),
                    "avoided_adverse_mo_proxy": sh.get("avoided_adverse_mo_proxy"),
                    "stack_nullified": delta_s.get("overlay_nullified_in_fire"),
                    "n_fire_pause_prints": sh.get("n_fire_pause_prints"),
                    "n_nest_hard_prints": sh.get("n_nest_hard_prints"),
                    "extra_venues_brief": _extra_brief(summary),
                }
            )
        except Exception as exc:  # noqa: BLE001
            results.append({"day": day, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
            if not args.quiet:
                print(f"[paper_harness] FAIL {day}: {exc}", file=sys.stderr)

    ok_rows = [r for r in results if r.get("ok")]
    def _m(key: str) -> float:
        xs = [float(r[key]) for r in ok_rows if r.get(key) is not None and np.isfinite(float(r[key]))]
        return float(np.mean(xs)) if xs else float("nan")

    pool = {
        "n": len(ok_rows),
        "mean_delta_equity_bps": _m("delta_equity_bps"),
        "mean_delta_fills_in_fire": _m("delta_fills_in_fire"),
        "mean_delta_equity_incr_fire_bps": _m("delta_equity_incr_fire_bps"),
        "mean_delta_stack_equity_bps": _m("delta_stack_equity_bps"),
        "mean_delta_stack_n_fills": _m("delta_stack_n_fills"),
        "mean_delta_stack_fills_in_fire": _m("delta_stack_fills_in_fire"),
        "mean_delta_stack_equity_incr_fire_bps": _m("delta_stack_equity_incr_fire_bps"),
        "mean_abs_mo5_fire": _m("abs_mo5_fire_mean"),
        "mean_avoided_adverse_mo_proxy": _m("avoided_adverse_mo_proxy"),
        "frac_nullified": float(
            np.mean([1.0 if r.get("overlay_nullified") else 0.0 for r in ok_rows])
        )
        if ok_rows
        else float("nan"),
        "frac_stack_nullified": float(
            np.mean([1.0 if r.get("stack_nullified") else 0.0 for r in ok_rows])
        )
        if ok_rows
        else float("nan"),
        "sum_gated": int(sum(int(r.get("ssm_10_n") or 0) for r in ok_rows)),
        "sum_fire": int(sum(int(r.get("n_fire") or 0) for r in ok_rows)),
    }

    rollup = {
        "days": days,
        "venue": cfg.get("venue"),
        "symbol": cfg.get("symbol"),
        "extra_venues": cfg.get("extra_venues") or [],
        "results": results,
        "n_ok": sum(1 for r in results if r.get("ok")),
        "pool": pool,
        "compare": "baseline_vs_risk_gate_stack",
        "honesty": {
            "overlay": "risk_policy_not_pnl_alpha",
            "live_orders": False,
            "clickhouse_mcp": False,
            "scoreboard": "delta_fills_and_adverse_mo_proxy_not_tradable_alpha",
        },
    }
    rollup_path = out_root / "rollup.json"
    rollup_path.parent.mkdir(parents=True, exist_ok=True)
    rollup_path.write_text(json.dumps(jsonable(rollup), indent=2) + "\n")
    md_path = write_rollup_markdown(rollup, out_root / "RISK_ROLLUP.md")
    if not args.quiet:
        print(f"[paper_harness] rollup → {rollup_path} · {md_path}")
    print(json.dumps(jsonable(rollup), indent=2))


if __name__ == "__main__":
    main()
