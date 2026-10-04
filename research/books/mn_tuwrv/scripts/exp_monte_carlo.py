from __future__ import annotations
#!/usr/bin/env python3
"""Heston + noise Monte Carlo for mn_tuwrv (§V / Table 1 style).

Desk-speed default n_sims=200; pass --n-sims 25000 for thesis-scale.
ClickHouse MCP banned — pure simulation.
"""


import argparse
import json
import sys
from pathlib import Path

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(ROOT))

from ares_micro.vol.tsrv import monte_carlo_estimators  # noqa: E402

OUT = BOOK / "out" / "monte_carlo"
CH_MC = BOOK / "chapters" / "monte_carlo"
CH_EST = BOOK / "chapters" / "estimators"


def _write_report(summary: dict) -> None:
    lines = [
        "# Monte Carlo — EXP_REPORT (Pass 1)",
        "",
        "## Sample",
        f"- n_sims: {summary['n_sims']}",
        f"- K: {summary['K']}  step: {summary['step']}",
        f"- Heston: μ={summary['heston']['mu']}, κ={summary['heston']['kappa']}, "
        f"α={summary['heston']['alpha']}, γ={summary['heston']['gamma']}, "
        f"ρ={summary['heston']['rho']}, σ_ε={summary['heston']['noise_std']}",
        f"- T={summary['heston']['T']}, dt={summary['heston'].get('dt')}",
        "",
        "## Estimator errors (estimate − true IV)",
        "",
        "| Estimator | Bias | Var | RMSE | n |",
        "|-----------|------|-----|------|---|",
    ]
    for name, row in summary["estimators"].items():
        lines.append(
            f"| {name} | {row['bias']:.6g} | {row['var']:.6g} | {row['rmse']:.6g} | {row['n']} |"
        )
    fourth_rmse = summary["estimators"].get("fourth", {}).get("rmse", float("nan"))
    adj_rmse = summary["estimators"].get("first_adj", {}).get("rmse", float("nan"))
    fifth_bias = summary["estimators"].get("fifth", {}).get("bias", float("nan"))
    lines += [
        "",
        "## Pass 1 takeaways",
        f"- Fifth-best bias ≈ {fifth_bias:.6g} (noise-dominated; not an IV estimator).",
        f"- Fourth (sparse) RMSE ≈ {fourth_rmse:.6g}; first_adj RMSE ≈ {adj_rmse:.6g}.",
        "- If first_adj RMSE ≪ fourth: support **Kill** `cont.sparse_rv_only` as desk default.",
        "",
        "## Artifacts",
        f"- JSON: `{OUT.relative_to(BOOK)}/mc_summary.json`",
        "",
    ]
    text = "\n".join(lines)
    (CH_MC / "EXP_REPORT.md").write_text(text)
    # brief pointer on estimators chapter
    est_rep = (
        "# Estimators — EXP_REPORT\n\n"
        "## Sample\n"
        f"- Monte Carlo linked from `monte_carlo` (n_sims={summary['n_sims']}).\n"
        "- Tape panel: see `noise_proxy` / `scripts/exp_tsrv_panel.py`.\n\n"
        "## Status\n"
        "- Lib ladder exercised via MC; real-tape sanity in panel script.\n"
    )
    (CH_EST / "EXP_REPORT.md").write_text(est_rep)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-sims", type=int, default=200)
    ap.add_argument("--K", type=int, default=300)
    ap.add_argument("--step", type=int, default=300)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Running MC n_sims={args.n_sims} K={args.K} step={args.step} …", flush=True)
    summary = monte_carlo_estimators(
        n_sims=args.n_sims, K=args.K, step=args.step, seed=args.seed
    )
    path = OUT / "mc_summary.json"
    path.write_text(json.dumps(summary, indent=2, default=str))
    _write_report(summary)
    print(json.dumps(summary["estimators"], indent=2))
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
