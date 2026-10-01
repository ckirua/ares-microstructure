from __future__ import annotations
#!/usr/bin/env python3
"""TI-v-fade SHADOW PAPER CLI — causal fade on real tape (not MM, not live).

Examples:
  python3 run_v_fade_paper.py --day 2026-09-04
  python3 run_v_fade_paper.py --panel-days --extra-venues deribit,kraken
  python3 run_v_fade_paper.py --shadow
  python3 run_v_fade_paper.py --shadow --confirm-s 1.0 --exit-s 8.0

Honesty: SHADOW PAPER · research_sim · RT=4bps · mid_mo null → tape mo · live_orders=False.
ClickHouse MCP banned. Warehouse + startarb loaders only.
"""


import argparse
import json
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parent
sys.path.insert(0, str(PKG))

from harness.causal import jsonable  # noqa: E402
from harness.config import load_config  # noqa: E402
from harness.pipeline import run_v_fade_day, run_v_fade_panel  # noqa: E402
from harness.shadow import (  # noqa: E402
    apply_vf_overrides,
    find_latest_complete_day,
    load_gap_summary,
    path_candidate_overrides,
    write_shadow_board,
)

DEFAULT_PANEL_DAYS = [
    "2026-09-04",
    "2026-09-05",
    "2026-09-06",
    "2026-09-07",
    "2026-09-08",
    "2026-09-09",
    "2026-09-10",
]


def _add_vf_flags(ap: argparse.ArgumentParser) -> None:
    ap.add_argument(
        "--entry-mode",
        choices=("severity_zend", "confirm_r2"),
        default=None,
        help="severity_zend=|z|≥z_min at ts_end (no r2); confirm_r2=lab V-confirm (path-late)",
    )
    ap.add_argument(
        "--confirm-s",
        type=float,
        default=None,
        help="Entry delay after ts_end (0 or 0.5 for severity_zend; 2 for confirm_r2)",
    )
    ap.add_argument("--exit-s", type=float, default=None, help="Override v_fade.exit_s")
    ap.add_argument("--z-min", type=float, default=None, help="|z_peak| gate for severity_zend")
    ap.add_argument(
        "--adverse-stop-bps",
        type=float,
        default=None,
        help="Override v_fade.adverse_stop_bps",
    )
    ap.add_argument("--v-threshold-r2", type=float, default=None, help="Override v_fade.v_threshold_r2")
    ap.add_argument(
        "--soft-confirm-r1",
        type=float,
        default=None,
        help="Override v_fade.soft_confirm_r1",
    )
    ap.add_argument(
        "--cont-threshold-r2",
        type=float,
        default=None,
        help="Override v_fade.cont_threshold_r2",
    )
    ap.add_argument("--rt-friction-bps", type=float, default=None, help="Override RT haircut bps")
    ap.add_argument(
        "--always-fade",
        action="store_true",
        help="Bypass causal V gate (confirm_r2 path-candidate / confirm=0)",
    )
    ap.add_argument(
        "--no-adverse-stop",
        action="store_true",
        help="Disable adverse stop (sets adverse_stop_bps=1e9)",
    )
    ap.add_argument(
        "--suppress-fire-pause",
        action="store_true",
        default=None,
        help="Skip entries while fire_pause_5m is live (compose rule)",
    )
    ap.add_argument(
        "--allow-fire-pause",
        action="store_true",
        help="Do NOT suppress fades during fire_pause_5m (diagnostic)",
    )
    ap.add_argument(
        "--gap-summary",
        default="",
        help="Path to gap_summary.json (default out/gap_summary.json)",
    )


def _cli_vf_overrides(args: argparse.Namespace) -> dict:
    mapping = {
        "confirm_s": args.confirm_s,
        "exit_s": args.exit_s,
        "adverse_stop_bps": args.adverse_stop_bps,
        "v_threshold_r2": args.v_threshold_r2,
        "soft_confirm_r1": args.soft_confirm_r1,
        "cont_threshold_r2": args.cont_threshold_r2,
        "rt_friction_bps": args.rt_friction_bps,
        "z_min": args.z_min,
        "entry_mode": args.entry_mode,
    }
    out = {k: v for k, v in mapping.items() if v is not None}
    if getattr(args, "always_fade", False):
        out["always_fade"] = True
    if getattr(args, "no_adverse_stop", False):
        out["adverse_stop_bps"] = 1e9
    if getattr(args, "allow_fire_pause", False):
        out["suppress_fire_pause"] = False
    elif getattr(args, "suppress_fire_pause", None):
        out["suppress_fire_pause"] = True
    return out


def run_shadow(
    *,
    cfg: dict,
    out_root: Path,
    quiet: bool = False,
    gap_path: str | Path | None = None,
    cli_overrides: dict | None = None,
    panel_days: list[str] | None = None,
) -> dict:
    """Latest complete day w/ gated SSM → SHADOW_BOARD confirm_r2 vs severity best.

    Default severity from gap_summary best_policy (Promote_shadow):
      severity_zend · z≥20 · confirm=0.5 · exit=3 · fire_pause prior_only
    confirm_r2@2→5 remains the Hold / path-late column.
    """
    venue = cfg.get("venue") or "hyperliquid"
    symbol = cfg.get("symbol") or "ETH"
    found = find_latest_complete_day(
        venue, symbol, quiet=quiet, require_gated_ssm=True
    )
    day = found["day"]

    gap = load_gap_summary(gap_path) if gap_path else load_gap_summary()
    if gap is None:
        gap = load_gap_summary(out_root / "gap_summary.json")

    cli_ov = dict(cli_overrides or {})
    best = path_candidate_overrides(gap) or {}
    # Promote_shadow locked defaults (overridden by gap then CLI)
    sev_defaults = {
        "entry_mode": "severity_zend",
        "confirm_s": 0.5,
        "exit_s": 3.0,
        "z_min": 20.0,
        "adverse_stop_bps": 1e9,
        "suppress_fire_pause": "prior_only",
        "always_fade": False,
    }
    sev_defaults.update({k: v for k, v in best.items() if v is not None})
    sev_defaults.update({k: v for k, v in cli_ov.items() if v is not None})
    sev_defaults["entry_mode"] = "severity_zend"
    sev_defaults["always_fade"] = False

    z_min = float(sev_defaults.get("z_min", 20.0))
    sev_confirm = float(sev_defaults.get("confirm_s", 0.5))
    sev_exit = float(sev_defaults.get("exit_s", 3.0))

    # A) confirm_r2 legacy (path Hold)
    confirm_cfg = apply_vf_overrides(
        cfg,
        {
            "entry_mode": "confirm_r2",
            "confirm_s": 2.0,
            "exit_s": 5.0,
            "adverse_stop_bps": 12.0,
            "always_fade": False,
            "suppress_fire_pause": "prior_only",
            "soft_confirm_r1": (cfg.get("v_fade") or {}).get("soft_confirm_r1", 0.35),
            "v_threshold_r2": (cfg.get("v_fade") or {}).get("v_threshold_r2", 0.5),
        },
    )
    confirm_cfg["v_fade"]["entry_mode"] = "confirm_r2"
    confirm_cfg["v_fade"]["confirm_s"] = 2.0
    confirm_cfg["v_fade"]["exit_s"] = 5.0

    # B) severity Promote_shadow best
    severity_cfg = apply_vf_overrides(cfg, sev_defaults)
    severity_cfg["v_fade"]["entry_mode"] = "severity_zend"
    severity_cfg["v_fade"]["confirm_s"] = sev_confirm
    severity_cfg["v_fade"]["exit_s"] = sev_exit
    severity_cfg["v_fade"]["z_min"] = z_min

    if not quiet:
        print(
            f"[SHADOW] day={day} {venue} {symbol} live_orders=false · "
            f"A=confirm_r2@2→5 · B=severity_zend |z|≥{z_min:g} @{sev_confirm}s→{sev_exit}s prior_only"
        )

    confirm_root = out_root / "shadow_confirm_r2"
    severity_root = out_root / "shadow_severity_zend"
    confirm_root.mkdir(parents=True, exist_ok=True)
    severity_root.mkdir(parents=True, exist_ok=True)

    confirm_run = run_v_fade_day(day, cfg=confirm_cfg, out_root=confirm_root, quiet=quiet)
    severity_run = run_v_fade_day(day, cfg=severity_cfg, out_root=severity_root, quiet=quiet)

    board = write_shadow_board(
        out_root=out_root,
        day=day,
        venue=venue,
        symbol=symbol,
        lab_run=confirm_run,
        path_run=severity_run,
        gap=gap,
        panel_days=panel_days or DEFAULT_PANEL_DAYS,
        policy_a_name="confirm_r2@2→5 (Hold / path-late)",
        policy_b_name=(
            f"severity_zend |z|≥{z_min:g} @{sev_confirm:g}s→{sev_exit:g}s prior_only "
            f"(Promote_shadow)"
        ),
    )
    c_sum = confirm_run.get("summary") or {}
    s_sum = severity_run.get("summary") or {}
    gap_best = (gap or {}).get("best_policy") or {}
    gap_base = (gap or {}).get("baseline_confirm_r2") or {}
    brief = {
        "mode": "SHADOW_PAPER",
        "live_orders": False,
        "decision": (gap or {}).get("decision"),
        "day": day,
        "venue": venue,
        "symbol": symbol,
        "shadow_board": str(board),
        "panel_confirm_r2": {
            "n": gap_base.get("n"),
            "path_mean": gap_base.get("path_mean"),
            "path_ci": [gap_base.get("path_lo"), gap_base.get("path_hi")],
            "lab_mean": gap_base.get("lab_mean"),
        },
        "panel_severity_best": {
            "n": gap_best.get("n"),
            "path_mean": gap_best.get("path_mean"),
            "path_ci": [gap_best.get("path_lo"), gap_best.get("path_hi")],
            "lab_mean": gap_best.get("lab_mean"),
            "params": {
                "confirm_s": gap_best.get("confirm_s"),
                "exit_s": gap_best.get("exit_s"),
                "z_min": gap_best.get("z_min"),
                "suppress_fire_pause": gap_best.get("suppress_fire_pause"),
            },
        },
        "living_day_confirm_r2": {
            "n_faded": c_sum.get("n_faded"),
            "lab_pnl_net_bps": c_sum.get("lab_pnl_net_bps"),
            "path_pnl_net_bps": c_sum.get("path_pnl_net_bps"),
            "out_dir": confirm_run.get("out_dir"),
        },
        "living_day_severity_zend": {
            "n_faded": s_sum.get("n_faded"),
            "lab_pnl_net_bps": s_sum.get("lab_pnl_net_bps"),
            "path_pnl_net_bps": s_sum.get("path_pnl_net_bps"),
            "confirm_s": sev_confirm,
            "exit_s": sev_exit,
            "z_min": z_min,
            "out_dir": severity_run.get("out_dir"),
        },
        "gap_summary_present": gap is not None,
        "completeness_probed": found.get("probed"),
    }
    return brief


def main() -> None:
    ap = argparse.ArgumentParser(
        description="V-fade SHADOW PAPER: detect → causal confirm → shadow taker → risk report"
    )
    ap.add_argument("--day", default="", help="Single UTC day YYYY-MM-DD")
    ap.add_argument("--days", default="", help="Comma-separated UTC days")
    ap.add_argument(
        "--panel-days",
        action="store_true",
        help="Run Phase-4 research days 2026-09-04…10",
    )
    ap.add_argument(
        "--shadow",
        action="store_true",
        help="Living SHADOW board on latest complete warehouse day (+ path candidate if gap_summary)",
    )
    ap.add_argument("--config", default=str(PKG / "config.yaml"))
    ap.add_argument("--venue", default="", help="Override config venue (default hyperliquid)")
    ap.add_argument("--symbol", default="", help="Override config symbol (default ETH)")
    ap.add_argument(
        "--extra-venues",
        default="",
        help="Comma list (e.g. deribit,kraken) — full fade sim per venue",
    )
    ap.add_argument("--out-dir", default="", help="Override output root")
    ap.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Run even if day completeness flags fail",
    )
    ap.add_argument("--quiet", action="store_true")
    _add_vf_flags(ap)
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

    cli_ov = _cli_vf_overrides(args)
    cfg = apply_vf_overrides(cfg, cli_ov)

    out_root = Path(args.out_dir) if args.out_dir else PKG / str(cfg.get("out_dir") or "out")
    gap_path = Path(args.gap_summary) if args.gap_summary else None

    if args.shadow:
        brief = run_shadow(
            cfg=cfg,
            out_root=out_root,
            quiet=args.quiet,
            gap_path=gap_path,
            cli_overrides=cli_ov,
            panel_days=DEFAULT_PANEL_DAYS,
        )
        print(json.dumps(jsonable(brief), indent=2))
        return

    if args.panel_days:
        days = list(DEFAULT_PANEL_DAYS)
    elif args.days:
        days = [d.strip() for d in args.days.split(",") if d.strip()]
    elif args.day:
        days = [args.day.strip()]
    else:
        ap.error("Provide --day, --days, --panel-days, or --shadow")

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
    vf = cfg.get("v_fade") or {}
    lab = rollup.get("lab_pnl_net_bps") or {}
    path = rollup.get("path_pnl_net_bps") or {}
    path_lo, path_hi = path.get("lo"), path.get("hi")
    path_ci_gt_0 = bool(
        path.get("mean") is not None
        and path_lo is not None
        and path_hi is not None
        and path_lo > 0
    )
    brief = {
        "mode": "SHADOW_PAPER",
        "live_orders": False,
        "n_ok": rollup.get("n_ok"),
        "n_faded": rollup.get("n_faded"),
        "params": {
            "entry_mode": vf.get("entry_mode"),
            "confirm_s": vf.get("confirm_s"),
            "exit_s": vf.get("exit_s"),
            "z_min": vf.get("z_min"),
            "suppress_fire_pause": vf.get("suppress_fire_pause", True),
            "adverse_stop_bps": vf.get("adverse_stop_bps"),
        },
        "lab_identity": {
            "formula": "-mo_5s - RT4",
            "pnl_net_bps": lab,
            "note": "NOT equal to path under confirm_r2 — credits pre-entry rebound",
        },
        "path_executable": {
            "formula": "side*(exit/entry-1)*1e4 - RT4",
            "pnl_net_bps": path,
            "path_ci_gt_0": path_ci_gt_0,
            "promote_shadow": bool(path_ci_gt_0),
        },
        "lab_pnl_net_bps": lab,
        "path_pnl_net_bps": path,
        "early_mean": rollup.get("early_mean"),
        "late_mean": rollup.get("late_mean"),
        "hit_rate": rollup.get("hit_rate"),
        "kills": {
            "decision": (rollup.get("kills") or {}).get("decision"),
            "any_kill": (rollup.get("kills") or {}).get("any_kill"),
            "flags": (rollup.get("kills") or {}).get("flags"),
            "note": "lab-keyed kills; path CI is the live/shadow promote gate",
        },
        "honesty": {
            "path_equals_lab": False,
            "alpha_claim": False,
            "live_orders": False,
        },
        "out_dir": str(out_root),
        "risk_report": str(out_root / "RISK_REPORT.md"),
        "rollup_json": str(out_root / "rollup.json"),
        "days": days,
    }
    print(json.dumps(jsonable(brief), indent=2))


if __name__ == "__main__":
    main()
