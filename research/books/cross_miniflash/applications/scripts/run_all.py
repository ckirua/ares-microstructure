from __future__ import annotations
#!/usr/bin/env python3
"""Run all RISK+EXEC application backtests (builds shared event panel once)."""


import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import build_event_panel, jsonable, save_json, OUT  # noqa: E402
import exp_kill_ladder  # noqa: E402
import exp_nanex_burst  # noqa: E402
import exp_hl_thin_sor  # noqa: E402
import exp_hv_fei_sizing  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="rebuild event panel")
    ap.add_argument("--no-pov", action="store_true")
    args = ap.parse_args()

    print("=== building event panel ===", flush=True)
    panel = build_event_panel(force=args.force)
    print(
        f"panel rows={panel['meta']['n_rows']} cached={panel.get('cached')}",
        flush=True,
    )

    print("=== kill_ladder ===", flush=True)
    s1 = exp_kill_ladder.run(force=False)
    print("=== nanex_burst ===", flush=True)
    s2 = exp_nanex_burst.run(force=False)
    print("=== hl_thin_sor ===", flush=True)
    s3 = exp_hl_thin_sor.run(force=False)
    print("=== hv_fei_capacity ===", flush=True)
    s4 = exp_hv_fei_sizing.run(force=False, run_pov=not args.no_pov)

    board = {
        "kill_ladder": {
            "readiness": s1["policy"]["readiness"],
            "promote_as_risk_policy": s1["policy"]["promote_as_risk_policy"],
            "n_gated": s1["n_gated_events"],
            "abs_mo_delta": s1["policy"]["abs_mo_elevation_fire_vs_ctrl"],
            "friction_cleared": s1["policy"]["friction_cleared"],
            "sign_stable": s1["time_split"]["sign_stable"],
        },
        "nanex_burst": {
            "tag_readiness": s2["policy"]["tag_readiness"],
            "auto_pull_readiness": s2["policy"]["auto_pull_readiness"],
            "promote_as_risk_policy": s2["policy"]["promote_as_risk_policy"],
            "n_nested": s2["n_nested"],
            "precision": s2["nanex_precision_pooled"],
            "dp_effect": s2["effects_nested_minus_ssm_only"]["dp"],
        },
        "hl_thin_sor": {
            "readiness": s3["policy"]["readiness"],
            "monitor": s3["policy"]["monitor_readiness"],
            "promote_as_risk_policy": s3["policy"]["promote_as_risk_policy"],
            "crash_share": s3["crash_share_gated"],
            "delta_abs_mo": s3["hl_fire_vs_thick"]["abs_mo"],
            "sign_stable": s3["time_split"]["sign_stable"],
        },
        "hv_fei_capacity": {
            "readiness": s4["policy"]["readiness"],
            "monitor": s4["policy"]["monitor_readiness"],
            "promote_as_risk_policy": s4["policy"]["promote_as_risk_policy"],
            "spearman": s4["spearman"],
            "pov": s4.get("pov"),
            "slippage_improved": s4["policy"]["slippage_improved_vs_flat"],
        },
    }
    save_json(OUT / "applications_board.json", board)
    print(json.dumps(jsonable(board), indent=2))


if __name__ == "__main__":
    main()
