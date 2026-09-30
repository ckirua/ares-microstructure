#!/usr/bin/env python3
"""Expanded lab runner — panel extension, robustness, strategies, models, scoreboard.

Writes under applications/expanded_lab/out/ only (sibling event_panel untouched).
ClickHouse MCP banned. Quant bar: time-split, bootstrap CIs, no fake alpha.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

LAB = Path(__file__).resolve().parent
APP = LAB.parent
BOOK = APP.parent
ROOT = BOOK.parents[2]
OUT = LAB / "out"
FIG = OUT / "figs"

for p in (str(LAB), str(APP / "scripts"), str(BOOK / "scripts"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from _common import save_fig, save_json  # noqa: E402
from book_realism import run_book_realism  # noqa: E402
from models_ext import run_models  # noqa: E402
from panel import build_expanded_panel, panel_event_lists  # noqa: E402
from robustness import run_robustness  # noqa: E402
from scoreboard import build_scoreboard  # noqa: E402
from strategy_variants import score_policies  # noqa: E402


def jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, float)):
        x = float(obj)
        return x if np.isfinite(x) else None
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if obj is None:
        return None
    return str(obj)


def _figs_robustness(rob: dict[str, Any]) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    paths = []
    FIG.mkdir(parents=True, exist_ok=True)
    slices = ["core", "core_plus_extend", "sol", "all"]
    deltas, los, his, labels = [], [], [], []
    for s in slices:
        kl = rob["slices"].get(s, {}).get("kill_ladder", {})
        d = kl.get("delta_abs_mo_5s") or {}
        if kl.get("n", 0) <= 0 or not np.isfinite(d.get("delta", np.nan) or np.nan):
            continue
        labels.append(f"{s}\nn={kl.get('n_fire')}")
        deltas.append(d["delta"])
        los.append(d["lo"])
        his.append(d["hi"])
    if labels:
        fig, ax = plt.subplots(figsize=(8, 4.2))
        x = np.arange(len(labels))
        ax.bar(x, deltas, color="#3d5a80", alpha=0.85)
        ax.errorbar(x, deltas, yerr=[np.array(deltas) - np.array(los), np.array(his) - np.array(deltas)], fmt="none", ecolor="black", capsize=4)
        ax.axhline(2.0, color="#c1121f", ls="--", lw=1, label="friction 2bps")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=9)
        ax.set_ylabel("Δ|mo|@5s fire−control (bps)")
        ax.set_title("Kill-ladder robustness across panel slices")
        ax.legend(fontsize=8)
        p = FIG / "fig_kill_ladder_robustness.png"
        save_fig(p)
        paths.append(str(p))

    # nanex precision
    fig, ax = plt.subplots(figsize=(7, 4))
    precs, names = [], []
    for s in slices:
        nx = rob["slices"].get(s, {}).get("nanex", {})
        if nx.get("n_gated", 0) <= 0:
            continue
        names.append(s)
        precs.append(nx.get("precision") or 0)
    if names:
        ax.bar(names, precs, color="#2a9d8f")
        ax.axhline(0.85, color="#c1121f", ls="--", label="0.85 bar")
        ax.set_ylim(0, 1.05)
        ax.set_ylabel("Nanex→SSM precision")
        ax.set_title("Nanex∩SSM precision by slice")
        ax.legend(fontsize=8)
        p = FIG / "fig_nanex_precision_slices.png"
        save_fig(p)
        paths.append(str(p))
    return paths


def _figs_strategies(strat: dict[str, Any]) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    paths = []
    pols = strat.get("policies") or {}
    ranked = strat.get("ranked_by_risk") or []
    if not ranked:
        return paths
    cont = []
    dd = []
    hole = []
    for pol in ranked:
        fr = pols[pol]["friction_sweep"]["2.0"]
        c = fr.get("cont_adverse_mean") or fr["adverse_mean"]
        cont.append(c["point"])
        dd.append(fr["max_dd_mean"]["point"])
        hole.append(fr["hole_inventory_mean"]["point"])
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2))
    y = np.arange(len(ranked))
    for ax, vals, title in zip(
        axes,
        [cont, dd, hole],
        ["Cont adverse (bps)", "Max DD proxy (bps)", "Hole inventory (size)"],
    ):
        ax.barh(y, vals, color="#264653")
        ax.set_yticks(y)
        ax.set_yticklabels(ranked, fontsize=8)
        ax.set_title(title, fontsize=10)
        ax.invert_yaxis()
    fig.suptitle("Strategy risk scoreboard @ 2bps friction (lower=better)", fontsize=11)
    p = FIG / "fig_strategy_risk_scoreboard.png"
    save_fig(p)
    paths.append(str(p))

    # friction sweep for top 3
    top = ranked[:4]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    frs = [0.0, 1.0, 2.0, 4.0]
    for pol in top:
        ys = []
        for fr in frs:
            cell = pols[pol]["friction_sweep"][str(fr)]
            c = cell.get("cont_adverse_mean") or cell["adverse_mean"]
            ys.append(c["point"])
        ax.plot(frs, ys, marker="o", label=pol)
    ax.set_xlabel("Friction haircut (bps)")
    ax.set_ylabel("Continuation adverse cost")
    ax.set_title("Friction sweep — cont adverse")
    ax.legend(fontsize=7)
    p = FIG / "fig_friction_sweep.png"
    save_fig(p)
    paths.append(str(p))
    return paths


def _figs_models(models: dict[str, Any]) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    paths = []
    occ = models.get("occurrence") or {}
    cal = occ.get("calibration") or {}
    if "frac_pos" in cal and "mean_pred" in cal:
        fig, ax = plt.subplots(figsize=(5, 5))
        ax.plot([0, 1], [0, 1], "k--", lw=1)
        ax.plot(cal["mean_pred"], cal["frac_pos"], "o-", color="#e76f51")
        ax.set_xlabel("Mean predicted P(crash)")
        ax.set_ylabel("Fraction positive")
        ax.set_title(f"Occurrence calibration (AUC_te={occ.get('auc_test')})")
        p = FIG / "fig_occurrence_calibration.png"
        save_fig(p)
        paths.append(str(p))
    return paths


def _figs_book(book: dict[str, Any]) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    paths = []
    probes = [p for p in book.get("probes") or [] if "error" not in p]
    if not probes:
        return paths
    # scatter median_dt warehouse vs collector when both exist
    xs, ys, labs = [], [], []
    for p in probes:
        w = p.get("warehouse") or {}
        c = p.get("collector") or {}
        if w.get("missing") or c.get("missing"):
            continue
        if not np.isfinite(w.get("median_dt_s", np.nan)) or not np.isfinite(c.get("median_dt_s", np.nan)):
            continue
        xs.append(w["median_dt_s"])
        ys.append(c["median_dt_s"])
        labs.append(f"{p['day'][-5:]} {p['venue'][:2]}/{p['symbol']}")
    if xs:
        fig, ax = plt.subplots(figsize=(6, 5))
        ax.scatter(xs, ys, c="#457b9d")
        mx = max(max(xs), max(ys)) * 1.1
        ax.plot([0, mx], [0, mx], "k--", lw=1)
        ax.set_xlabel("Warehouse median Δt (s)")
        ax.set_ylabel("Collector median Δt (s)")
        ax.set_title("Book cadence: collector vs warehouse")
        p = FIG / "fig_book_cadence_compare.png"
        save_fig(p)
        paths.append(str(p))

    # outside rates best book
    outs = [
        (f"{p['day'][-5:]} {p['venue'][:2]}", p.get("best", {}).get("outside_rate"))
        for p in probes
        if isinstance(p.get("best"), dict) and np.isfinite(p["best"].get("outside_rate", np.nan) or np.nan)
    ]
    if outs:
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.bar([o[0] for o in outs], [o[1] for o in outs], color="#6d597a")
        ax.set_ylabel("Outside-TOB rate")
        ax.set_title("Outside-TOB (best book) — honesty check")
        ax.tick_params(axis="x", rotation=60, labelsize=7)
        p = FIG / "fig_outside_tob_best.png"
        save_fig(p)
        paths.append(str(p))
    return paths


def write_exp_report(summary: dict[str, Any]) -> Path:
    sb = summary["scoreboard"]
    rob = summary["robustness"]
    strat = summary["strategies"]
    models = summary["models"]
    book = summary["book"]
    meta = summary["panel_meta"]
    lines = [
        "# Expanded lab — EXP_REPORT",
        "",
        f"Generated: {summary['generated_at']}",
        f"Panel days={meta.get('days')} · symbols={meta.get('symbols')} · n_rows={meta.get('n_rows')}",
        f"Events: core={summary['n_events']['core']} · core+extend={summary['n_events']['core_plus_extend']} · "
        f"SOL={summary['n_events']['sol']} · all={summary['n_events']['all']}",
        "",
        "## Honesty",
        "- Own cache `expanded_lab/out/panel/` — sibling `applications/out/event_panel` untouched.",
        "- Risk overlays + MM playbooks first; **no naked tradable alpha**.",
        "- Time-split + bootstrap CIs; friction haircut on adverse costs.",
        "- HL SOL empty on flat-era Phase-4 days → SOL = Deribit+Kraken.",
        "",
        "## Kill-ladder / Nanex robustness",
        f"- Core kill-ladder: `{rob['slices']['core']['kill_ladder'].get('readiness')}` "
        f"Δ|mo|={rob['slices']['core']['kill_ladder'].get('delta_abs_mo_5s')}",
        f"- Core+extend: `{rob['slices']['core_plus_extend']['kill_ladder'].get('readiness')}` "
        f"Δ|mo|={rob['slices']['core_plus_extend']['kill_ladder'].get('delta_abs_mo_5s')}",
        f"- SOL: n={rob['slices']['sol']['kill_ladder'].get('n')} "
        f"readiness=`{rob['slices']['sol']['kill_ladder'].get('readiness')}`",
        f"- Nanex precision core={rob['slices']['core']['nanex'].get('precision')} "
        f"extend={rob['slices']['core_plus_extend']['nanex'].get('precision')} "
        f"SOL={rob['slices']['sol']['nanex'].get('precision')}",
        "",
        "## Strategy risk scoreboard (2bps)",
        f"- Ranked (best→worst cont adverse / DD / hole inv): `{strat.get('ranked_by_risk')}`",
        f"- Best: **{strat.get('best')}**",
        f"- Friction rank stable across grid: `{summary['scoreboard'].get('friction_rank_stable')}`",
        "",
        "## Models",
        f"- Occurrence: verdict=`{models['occurrence'].get('verdict')}` "
        f"AUC_te={models['occurrence'].get('auc_test')} Brier={models['occurrence'].get('brier_test')} "
        f"BayesAUC={models['occurrence'].get('bayes_beta_auc')}",
        f"- Severity: verdict=`{models['severity'].get('verdict')}` "
        f"R²_te={models['severity'].get('ridge_r2_test')} "
        f"BayesR²={models['severity'].get('bayes_ridge_r2_test')}",
        "",
        "## Book realism",
        f"- {book.get('summary')}",
        f"- Rec: {book.get('recommendation')}",
        "",
        "## Promotes / Holds (new)",
    ]
    for p in sb.get("promotes") or []:
        lines.append(f"- **{p['verdict']}** `{p['object']}` — {p['why']}")
    lines.append("")
    lines.append("### Holds")
    for h in sb.get("holds") or []:
        lines.append(f"- **{h['verdict']}** `{h['object']}` — {h['why']}")
    lines += [
        "",
        "## Figures",
        *[f"- `{Path(p).name}`" for p in summary.get("figures") or []],
        "",
        "## Identification",
        "- Gate: SSM z*=6 + |ΔP|≥10bps + i_c≥5",
        "- Ladder: within-gated z percentiles + intensity + Nanex nest",
        "- Strategy costs: size × signed tape mo (crash direction); rank on risk not rebound PnL",
        "",
    ]
    path = LAB / "EXP_REPORT.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def write_notebook(summary: dict[str, Any]) -> Path:
    """Minimal notebook pointing at figs + rollup JSON."""
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "# Expanded lab — cross_miniflash\n",
                    "\n",
                    "Risk overlays + MM playbooks on extended panel. **No naked alpha.**\n",
                    "\n",
                    f"Generated: {summary['generated_at']}\n",
                    "\n",
                    "See `EXP_REPORT.md` · `out/summary.json` · `out/figs/`.\n",
                ],
            },
            {
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": [
                    "import json\n",
                    "from pathlib import Path\n",
                    "from IPython.display import Image, display, Markdown\n",
                    "\n",
                    "OUT = Path('out')\n",
                    "summary = json.loads((OUT / 'summary.json').read_text())\n",
                    "print(summary['scoreboard']['headline'])\n",
                    "print('Promotes:', len(summary['scoreboard']['promotes']))\n",
                    "for p in summary['scoreboard']['promotes']:\n",
                    "    print(' ', p['verdict'], p['object'])\n",
                ],
            },
            {
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": [
                    "fig_dir = OUT / 'figs'\n",
                    "for p in sorted(fig_dir.glob('*.png')):\n",
                    "    display(Markdown(f'### {p.name}'))\n",
                    "    display(Image(filename=str(p)))\n",
                ],
            },
        ],
    }
    path = LAB / "expanded_lab.ipynb"
    path.write_text(json.dumps(nb, indent=1) + "\n")
    return path


def run(
    *,
    force_panel: bool = False,
    workers: int = 4,
    skip_book: bool = False,
    skip_extend: bool = False,
    skip_sol: bool = False,
    skip_dense: bool = False,
) -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)

    print("[1/6] expanded panel", flush=True)
    panel = build_expanded_panel(
        force=force_panel,
        workers=workers,
        include_extend_days=not skip_extend,
        include_sol=not skip_sol,
        include_dense_tob=not skip_dense,
    )
    by_slice = panel_event_lists(panel)
    n_events = {k: len(by_slice[k]) for k in ("core", "core_plus_extend", "sol", "all")}

    print("[2/6] robustness", flush=True)
    rob = run_robustness(panel, by_slice)

    print("[3/6] strategy variants", flush=True)
    # score on core+extend (power) and separately SOL if any
    strat = score_policies(by_slice["core_plus_extend"] or by_slice["core"])
    strat_sol = score_policies(by_slice["sol"]) if by_slice.get("sol") else {"n": 0}

    print("[4/6] models", flush=True)
    models = run_models(by_slice["core_plus_extend"] or by_slice["core"], panel["rows"])

    print("[5/6] book realism", flush=True)
    if skip_book:
        book = {"skipped": True, "summary": {}, "recommendation": "skipped", "probes": []}
    else:
        book = run_book_realism()

    print("[6/6] scoreboard + figs", flush=True)
    sb = build_scoreboard(
        strategy_scores=strat, robustness=rob, models=models, book=book
    )
    figs = []
    figs += _figs_robustness(rob)
    figs += _figs_strategies(strat)
    figs += _figs_models(models)
    figs += _figs_book(book)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "panel_meta": panel["meta"],
        "panel_cached": panel.get("cached"),
        "n_events": n_events,
        "robustness": rob,
        "strategies": strat,
        "strategies_sol": strat_sol,
        "models": models,
        "book": {
            "summary": book.get("summary"),
            "recommendation": book.get("recommendation"),
            "n_probes": book.get("n_probes"),
            "probes": book.get("probes"),  # keep for figs re-run honesty
        },
        "scoreboard": sb,
        "figures": figs,
    }
    save_json(OUT / "summary.json", jsonable(summary))
    save_json(OUT / "scoreboard.json", jsonable(sb))
    save_json(OUT / "robustness.json", jsonable(rob))
    write_exp_report(summary)
    write_notebook(summary)
    print(sb["headline"], flush=True)
    print("Promotes:", [p["object"] for p in sb["promotes"]], flush=True)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force-panel", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--skip-book", action="store_true")
    ap.add_argument("--skip-extend", action="store_true")
    ap.add_argument("--skip-sol", action="store_true")
    ap.add_argument("--include-dense", action="store_true", help="Add Sep29/30 cells despite thin coverage")
    ap.add_argument("--skip-dense", action="store_true", help="Deprecated; dense off by default")
    ap.add_argument("--core-only", action="store_true", help="Reuse core panel only; skip S3 extensions")
    args = ap.parse_args()
    skip_dense = not args.include_dense
    if args.core_only:
        args.skip_extend = args.skip_sol = True
        skip_dense = True
    run(
        force_panel=args.force_panel,
        workers=args.workers,
        skip_book=args.skip_book,
        skip_extend=args.skip_extend,
        skip_sol=args.skip_sol,
        skip_dense=skip_dense,
    )


if __name__ == "__main__":
    main()
