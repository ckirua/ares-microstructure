from __future__ import annotations
#!/usr/bin/env python3
"""Class models lab — P(V) for soft fade sizing (not mid prediction).

Feature store: panel_cache ⊕ event_panel.
Models: logistic + optional sklearn GBM; chrono train/test.
Scoreboard: AUC / Brier / calibration + OOS soft-size vs always-fade / hard V-rule
after 4 bps RT. Promote only if soft-size OOS lift clears CI; else Hold.

Honesty: research_sim · tape mo_5s economics · alpha_claim=False · no ClickHouse MCP.
"""


import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
APP = LAB.parent
BOOK = APP.parent
ROOT = BOOK.parents[2]
SCRIPTS = APP / "scripts"
OUT = HERE / "out"
FIG = OUT / "figs"
STORE = OUT / "store"

for p in (str(HERE.parent), str(SCRIPTS), str(APP), str(ROOT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

# package-relative imports when run as script
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from _common import early_late_by_day, save_fig, save_json  # noqa: E402

from feature_store import (  # noqa: E402
    FORBIDDEN_FEATURES,
    NUMERIC_FEATURES,
    build_feature_store,
    chrono_split_indices,
    save_store_jsonl,
)
from models import fit_classifiers  # noqa: E402
from sizing import RT_FRICTION, evaluate_sizing  # noqa: E402

HONESTY = {
    "slice": "research_sim_on_real_tape",
    "job": "class_V_vs_continuation_soft_fade_size",
    "not_mid_prediction": True,
    "live_orders": False,
    "fills": "synthetic_size_x_signed_tape_mo5s",
    "alpha_claim": False,
    "costs_bps_round_trip": RT_FRICTION,
    "clickhouse_mcp": False,
    "leakage_doc": "LEAKAGE.md",
    "mo_5s_role": "outcome_only_never_feature",
}


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
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if obj is None:
        return None
    return str(obj)


def _figs(
    events: list[dict[str, Any]],
    clf: dict[str, Any],
    sizing_packs: dict[str, dict[str, Any]],
) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    te = np.asarray(clf["te_mask"], dtype=bool)
    y = np.asarray(clf["y"], dtype=np.float64)
    usable = np.asarray(clf["usable_mask"], dtype=bool)

    # 1) calibration logistic
    cal = (clf.get("logistic") or {}).get("calibration_test") or {}
    if "mean_pred" in cal and "frac_pos" in cal:
        fig, ax = plt.subplots(figsize=(5.2, 4.2))
        ax.plot([0, 1], [0, 1], "k--", lw=1, label="ideal")
        ax.plot(cal["mean_pred"], cal["frac_pos"], "o-", color="#1f4e79", label="logistic OOS")
        gcal = ((clf.get("gbm") or {}) or {}).get("calibration_test") or {}
        if "mean_pred" in gcal:
            ax.plot(gcal["mean_pred"], gcal["frac_pos"], "s-", color="#c45c26", label="GBM OOS")
        ax.set_xlabel("mean P̂(V)")
        ax.set_ylabel("frac V (oracle)")
        ax.set_title("Calibration — OOS")
        ax.legend(fontsize=8)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        p = FIG / "fig_calibration.png"
        save_fig(p)
        paths.append(str(p.relative_to(HERE)))

    # 2) ROC-ish: score hist by class OOS
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.8), sharey=True)
    for ax, key, title, color in (
        (axes[0], "proba_logistic", "logistic", "#1f4e79"),
        (axes[1], "proba_gbm", "GBM", "#c45c26"),
    ):
        p = np.asarray(clf.get(key), dtype=np.float64)
        m = te & usable & np.isfinite(p)
        if not m.any():
            ax.set_title(f"{title}: empty")
            continue
        ax.hist(p[m & (y == 1)], bins=12, alpha=0.65, color=color, label="V", density=True)
        ax.hist(p[m & (y == 0)], bins=12, alpha=0.45, color="#888", label="not-V", density=True)
        ax.set_title(f"OOS P̂(V) — {title}")
        ax.set_xlabel("P̂(V)")
        ax.legend(fontsize=8)
    axes[0].set_ylabel("density")
    p = FIG / "fig_proba_hist_oos.png"
    save_fig(p)
    paths.append(str(p.relative_to(HERE)))

    # 3) feature coef / importance
    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    coef = (clf.get("logistic") or {}).get("coef") or {}
    if coef:
        items = sorted(coef.items(), key=lambda kv: abs(kv[1]), reverse=True)[:15]
        names = [k for k, _ in items][::-1]
        vals = [v for _, v in items][::-1]
        axes[0].barh(names, vals, color="#1f4e79")
        axes[0].axvline(0, color="k", lw=0.6)
        axes[0].set_title("logistic |coef| top-15")
    imp = ((clf.get("gbm") or {}) or {}).get("feature_importance") or {}
    if imp:
        items = sorted(imp.items(), key=lambda kv: kv[1], reverse=True)[:15]
        names = [k for k, _ in items][::-1]
        vals = [v for _, v in items][::-1]
        axes[1].barh(names, vals, color="#c45c26")
        axes[1].set_title("GBM importance top-15")
    p = FIG / "fig_feature_weights.png"
    save_fig(p)
    paths.append(str(p.relative_to(HERE)))

    # 4) OOS PnL by rule (primary model)
    primary = clf.get("primary_model", "logistic")
    pack = sizing_packs.get(primary) or next(iter(sizing_packs.values()), {})
    if pack and "soft_rules" in pack:
        labels = ["always_fade", "hard_v_rule"] + list(pack["soft_rules"].keys())
        means, los, his = [], [], []
        for lab in labels:
            if lab in ("always_fade", "hard_v_rule"):
                ci = pack["baselines"][lab]["pnl"]
            else:
                ci = pack["soft_rules"][lab]["pnl"]
            means.append(ci.get("mean", np.nan))
            los.append(ci.get("lo", np.nan))
            his.append(ci.get("hi", np.nan))
        fig, ax = plt.subplots(figsize=(10, 4.2))
        x = np.arange(len(labels))
        err_lo = np.asarray(means) - np.asarray(los)
        err_hi = np.asarray(his) - np.asarray(means)
        colors = ["#666" if l in ("always_fade", "hard_v_rule") else "#2a6f4e" for l in labels]
        ax.bar(x, means, color=colors, yerr=[err_lo, err_hi], capsize=3)
        ax.axhline(0, color="k", lw=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
        ax.set_ylabel("OOS mean net bps (RT=4)")
        ax.set_title(f"Soft-size vs baselines — {primary}")
        p = FIG / "fig_oos_pnl_rules.png"
        save_fig(p)
        paths.append(str(p.relative_to(HERE)))

        # 5) lift bars
        fig, ax = plt.subplots(figsize=(9, 4))
        names = list(pack["soft_rules"].keys())
        d_h = [pack["soft_rules"][n]["lift_vs_hard_v_rule"]["delta"] for n in names]
        d_a = [pack["soft_rules"][n]["lift_vs_always_fade"]["delta"] for n in names]
        x = np.arange(len(names))
        w = 0.38
        ax.bar(x - w / 2, d_h, w, label="Δ vs hard V-rule", color="#1f4e79")
        ax.bar(x + w / 2, d_a, w, label="Δ vs always-fade", color="#c45c26")
        ax.axhline(0, color="k", lw=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels(names, rotation=30, ha="right", fontsize=8)
        ax.set_ylabel("OOS paired lift (bps)")
        ax.set_title("Soft-size lift (Promote needs CI>0 vs both)")
        ax.legend(fontsize=8)
        p = FIG / "fig_oos_lifts.png"
        save_fig(p)
        paths.append(str(p.relative_to(HERE)))

    # 6) class counts
    fig, ax = plt.subplots(figsize=(5.5, 3.5))
    labs = ["v_recovery", "continuation", "partial"]
    oracle = [sum(1 for e in events if e.get("label") == lab) for lab in labs]
    causal = [sum(1 for e in events if e.get("causal") == lab) for lab in labs]
    x = np.arange(len(labs))
    ax.bar(x - 0.2, oracle, 0.4, label="oracle@5s", color="#1f4e79")
    ax.bar(x + 0.2, causal, 0.4, label="causal@2s", color="#888")
    ax.set_xticks(x)
    ax.set_xticklabels(labs)
    ax.set_ylabel("n events")
    ax.set_title("V / cont / partial counts")
    ax.legend(fontsize=8)
    p = FIG / "fig_class_counts.png"
    save_fig(p)
    paths.append(str(p.relative_to(HERE)))

    return paths


def write_report(summary: dict[str, Any], fig_paths: list[str]) -> Path:
    clf = summary["classifiers"]
    log = clf.get("logistic") or {}
    gbm = clf.get("gbm") or {}
    primary = clf.get("primary_model", "logistic")
    sz = summary["sizing"][primary]
    verd = sz["verdict"]
    split = summary["split"]

    lines = [
        "# Class models — V vs continuation (soft fade size)",
        "",
        f"Generated: {summary['generated_at']}",
        f"Script: `applications/edge_lab/class_models/run_class_models.py`",
        f"Out: `applications/edge_lab/class_models/out/`",
        "",
        "## Honesty",
        "",
        f"- job=`{HONESTY['job']}` · **not mid prediction** · live_orders=False · alpha_claim=False",
        f"- RT friction = **{RT_FRICTION} bps** · fills = synthetic size × signed tape mo@5s",
        "- **`mo_5s` is outcome only — never a feature** (see [`LEAKAGE.md`](../LEAKAGE.md))",
        "- ClickHouse MCP banned",
        "",
        "## Feature store",
        "",
        f"- panel_cache events: **{summary['store_meta']['n_events']}**",
        f"- join exact/slack/miss: **{summary['store_meta']['n_joined_exact']}** / "
        f"{summary['store_meta']['n_joined_slack']} / {summary['store_meta']['n_join_miss']}",
        f"- oracle counts: `{summary['store_meta']['oracle_counts']}`",
        f"- causal counts: `{summary['store_meta']['causal_counts']}`",
        f"- numeric features ({len(NUMERIC_FEATURES)}): `{NUMERIC_FEATURES}`",
        f"- forbidden (stripped): `{sorted(FORBIDDEN_FEATURES)[:8]}…`",
        "",
        "## Chrono split",
        "",
        f"- train n={split['n_train']} days={split['days_train']}",
        f"- test  n={split['n_test']} days={split['days_test']}",
        f"- cut_index={split['cut_index']} · cut_day_hint={split.get('cut_day_hint')}",
        "",
        "## Classifier OOS metrics",
        "",
        "| model | AUC train | AUC test | Brier test | base Brier | beats base |",
        "|-------|----------:|---------:|-----------:|-----------:|:----------:|",
    ]
    for name, pack in (("logistic", log), ("gbm", gbm)):
        if not pack:
            continue
        lines.append(
            f"| {name}{' ★' if name == primary or (name == 'gbm' and primary == 'gbm') else ''} | "
            f"{pack.get('auc_train', float('nan')):.3f} | {pack.get('auc_test', float('nan')):.3f} | "
            f"{pack.get('brier_test', float('nan')):.4f} | {pack.get('brier_base_test', float('nan')):.4f} | "
            f"{pack.get('beats_base_brier')} |"
        )
    lines += [
        "",
        f"Primary sizing model: **{primary}** (better OOS Brier / AUC among ok models).",
        "",
        "### Top logistic coefficients (by |coef|)",
        "",
    ]
    coef = log.get("coef") or {}
    for k, v in sorted(coef.items(), key=lambda kv: abs(kv[1]), reverse=True)[:12]:
        lines.append(f"- `{k}`: {v:+.3f}")
    if gbm and gbm.get("feature_importance"):
        lines += ["", "### Top GBM importances", ""]
        for k, v in sorted(gbm["feature_importance"].items(), key=lambda kv: kv[1], reverse=True)[:12]:
            lines.append(f"- `{k}`: {v:.3f}")

    lines += [
        "",
        "## OOS fade sizing (net bps after RT=4)",
        "",
        f"n_oos={sz['n_oos']} · P̂(V) mean={sz['p_v_oos']['mean']:.3f}",
        "",
        "### Baselines",
        "",
        "| rule | n_traded | mean net | lo | hi | hit |",
        "|------|----------|---------:|---:|---:|----:|",
    ]
    for name in ("always_fade", "hard_v_rule"):
        b = sz["baselines"][name]
        ci = b["pnl"]
        lines.append(
            f"| `{name}` | {b['n_traded']} | {ci['mean']:.2f} | {ci['lo']:.2f} | {ci['hi']:.2f} | "
            f"{b.get('hit_rate', float('nan')):.2f} |"
        )

    lines += [
        "",
        "### Soft maps P(V)→size",
        "",
        "| rule | n_traded | mean net | Δ vs hard (lo,hi) | Δ vs always (lo,hi) | clears both |",
        "|------|----------|---------:|-------------------:|--------------------:|:-----------:|",
    ]
    for name, r in sz["soft_rules"].items():
        ci = r["pnl"]
        vh = r["lift_vs_hard_v_rule"]
        va = r["lift_vs_always_fade"]
        star = " ★" if name == sz["primary_soft_rule"] else ""
        lines.append(
            f"| `{name}`{star} | {r['n_traded']} | {ci['mean']:.2f} | "
            f"{vh['delta']:.2f} [{vh['lo']:.2f},{vh['hi']:.2f}] | "
            f"{va['delta']:.2f} [{va['lo']:.2f},{va['hi']:.2f}] | "
            f"{r['clears_hard'] and r['clears_always']} |"
        )

    lines += [
        "",
        f"Time-split (primary soft `{sz['primary_soft_rule']}`): "
        f"early={sz['time_split_primary']['early']:.2f} · late={sz['time_split_primary']['late']:.2f} · "
        f"stable={sz['time_split_primary']['sign_stable']}",
        "",
        "## Verdict",
        "",
        f"- **{verd['decision']}** — {verd['why']}",
        f"- promote_requires: `{verd['promote_requires']}`",
        "- Classifier metrics alone do **not** Promote; soft-size lift must clear CI.",
        "- No ML alpha claim on raw mid (`mid_mo_*` null).",
        "",
        "## Figures",
        "",
    ]
    for fp in fig_paths:
        lines.append(f"- `{fp}`")
    lines += [
        "",
        "## How to run",
        "",
        "```bash",
        "cd research/books/cross_miniflash/applications/edge_lab/class_models",
        "python3 run_class_models.py",
        "```",
        "",
        "## Artifacts",
        "",
        "- `out/summary.json`",
        "- `out/EXP_REPORT.md`",
        "- `out/store/feature_store.jsonl`",
        "- `out/store/meta.json`",
        "- `LEAKAGE.md`",
        "- `class_models.ipynb`",
        "",
    ]
    path = OUT / "EXP_REPORT.md"
    path.write_text("\n".join(lines) + "\n")
    # desk stub copy at package root
    (HERE / "EXP_REPORT.md").write_text(path.read_text())
    return path


def write_notebook() -> Path:
    """Minimal executed-style notebook that reloads summary + plots paths."""
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "# Class models — V vs continuation (soft fade size)\n",
                    "\n",
                    "Not mid prediction. `mo_5s` is outcome only. See `LEAKAGE.md`.\n",
                    "Re-run: `python3 run_class_models.py` then refresh this notebook.\n",
                ],
            },
            {
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": [
                    "from pathlib import Path\n",
                    "import json\n",
                    "from IPython.display import display, Markdown, Image\n",
                    "\n",
                    "HERE = Path('.').resolve()\n",
                    "if not (HERE / 'out' / 'summary.json').exists():\n",
                    "    HERE = Path('applications/edge_lab/class_models').resolve()\n",
                    "summary = json.loads((HERE / 'out' / 'summary.json').read_text())\n",
                    "print('decision:', summary['sizing'][summary['classifiers']['primary_model']]['verdict']['decision'])\n",
                    "print('primary model:', summary['classifiers']['primary_model'])\n",
                    "log = summary['classifiers']['logistic']\n",
                    "print(f\"logistic OOS AUC={log['auc_test']:.3f} Brier={log['brier_test']:.4f}\")\n",
                    "gbm = summary['classifiers'].get('gbm') or {}\n",
                    "if gbm:\n",
                    "    print(f\"GBM OOS AUC={gbm['auc_test']:.3f} Brier={gbm['brier_test']:.4f}\")\n",
                    "sz = summary['sizing'][summary['classifiers']['primary_model']]\n",
                    "print('OOS soft primary:', sz['primary_soft_rule'])\n",
                    "print('vs hard:', sz['soft_rules'][sz['primary_soft_rule']]['lift_vs_hard_v_rule'])\n",
                    "print('vs always:', sz['soft_rules'][sz['primary_soft_rule']]['lift_vs_always_fade'])\n",
                ],
            },
            {
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": [
                    "import pandas as pd\n",
                    "rows = []\n",
                    "for name, r in sz['soft_rules'].items():\n",
                    "    rows.append({\n",
                    "        'rule': name,\n",
                    "        'mean_net': r['pnl']['mean'],\n",
                    "        'lo': r['pnl']['lo'],\n",
                    "        'hi': r['pnl']['hi'],\n",
                    "        'd_hard': r['lift_vs_hard_v_rule']['delta'],\n",
                    "        'd_always': r['lift_vs_always_fade']['delta'],\n",
                    "        'clears_both': r['clears_hard'] and r['clears_always'],\n",
                    "    })\n",
                    "for name in ('always_fade', 'hard_v_rule'):\n",
                    "    b = sz['baselines'][name]\n",
                    "    rows.append({'rule': name, 'mean_net': b['pnl']['mean'], 'lo': b['pnl']['lo'], 'hi': b['pnl']['hi'],\n",
                    "                'd_hard': None, 'd_always': None, 'clears_both': None})\n",
                    "display(pd.DataFrame(rows))\n",
                ],
            },
            {
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": [
                    "fig_dir = HERE / 'out' / 'figs'\n",
                    "for p in sorted(fig_dir.glob('*.png')):\n",
                    "    display(Markdown(f'### {p.name}'))\n",
                    "    display(Image(filename=str(p)))\n",
                ],
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## Leakage checklist\n",
                    "- [x] no `mo_5s` as feature\n",
                    "- [x] no `label` / `recovery_5s` as feature\n",
                    "- [x] chrono train/test\n",
                    "- [x] Promote gated on OOS soft-size lift CI, not AUC alone\n",
                    "- [x] no mid ML claim\n",
                ],
            },
        ],
    }
    path = HERE / "class_models.ipynb"
    path.write_text(json.dumps(nb, indent=1) + "\n")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-gbm", action="store_true")
    ap.add_argument("--train-frac", type=float, default=0.6)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    STORE.mkdir(parents=True, exist_ok=True)

    events, store_meta = build_feature_store()
    save_store_jsonl(STORE / "feature_store.jsonl", events, NUMERIC_FEATURES)
    save_json(STORE / "meta.json", store_meta)

    tr, te, split = chrono_split_indices(events, train_frac=args.train_frac)
    early, late = early_late_by_day(store_meta["days"])

    clf = fit_classifiers(events, tr, te, fit_gbm=not args.no_gbm)
    if clf.get("error"):
        summary = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "honesty": HONESTY,
            "store_meta": store_meta,
            "split": split,
            "classifiers": clf,
            "sizing": {},
            "verdict": {"decision": "Hold", "why": f"classifier error: {clf['error']}"},
        }
        save_json(OUT / "summary.json", summary)
        print("ERROR", clf)
        return 1

    # strip heavy arrays from saved classifier meta
    sizing_packs: dict[str, dict[str, Any]] = {}
    for model_key, proba_key in (("logistic", "proba_logistic"), ("gbm", "proba_gbm")):
        if model_key == "gbm" and not clf.get("gbm"):
            continue
        p = np.asarray(clf[proba_key], dtype=np.float64)
        sizing_packs[model_key] = evaluate_sizing(events, p, te, model_name=model_key)

    primary = clf["primary_model"]
    fig_paths = _figs(events, clf, sizing_packs)

    clf_save = {
        "features": clf["features"],
        "primary_model": primary,
        "logistic": clf["logistic"],
        "gbm": clf["gbm"],
        "forbidden_ok": clf["forbidden_ok"],
        "note": clf["note"],
        "n_usable_train": int((np.asarray(clf["tr_mask"]) & np.asarray(clf["usable_mask"])).sum()),
        "n_usable_test": int((np.asarray(clf["te_mask"]) & np.asarray(clf["usable_mask"])).sum()),
    }

    verdict = sizing_packs[primary]["verdict"]
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "honesty": HONESTY,
        "store_meta": store_meta,
        "split": split,
        "early_late_days": {"early": sorted(early), "late": sorted(late)},
        "classifiers": clf_save,
        "sizing": sizing_packs,
        "verdict": verdict,
        "fig_paths": fig_paths,
    }
    save_json(OUT / "summary.json", jsonable(summary))
    write_report(summary, fig_paths)
    write_notebook()

    print("=== class_models ===")
    print(f"n={store_meta['n_events']} train={split['n_train']} test={split['n_test']}")
    print(
        f"logistic AUC_oos={clf['logistic']['auc_test']:.3f} "
        f"Brier={clf['logistic']['brier_test']:.4f}"
    )
    if clf.get("gbm"):
        print(f"gbm AUC_oos={clf['gbm']['auc_test']:.3f} Brier={clf['gbm']['brier_test']:.4f}")
    print(f"primary={primary} soft={sizing_packs[primary]['primary_soft_rule']}")
    print(f"VERDICT: {verdict['decision']} — {verdict['why']}")
    print(f"wrote {OUT / 'EXP_REPORT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
