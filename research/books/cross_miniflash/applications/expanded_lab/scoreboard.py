"""Risk scoreboard — compare strategies on risk metrics, not vanity PnL.

Metrics: adverse markout, max DD proxy, inventory-in-holes, friction-swept cont cost.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def build_scoreboard(
    *,
    strategy_scores: dict[str, Any],
    robustness: dict[str, Any],
    models: dict[str, Any],
    book: dict[str, Any],
) -> dict[str, Any]:
    ranked = strategy_scores.get("ranked_by_risk") or []
    pols = strategy_scores.get("policies") or {}
    rows = []
    for pol in ranked:
        p = pols[pol]
        fr2 = p["friction_sweep"]["2.0"]
        rows.append(
            {
                "strategy": pol,
                "cont_adverse_bps": fr2.get("cont_adverse_mean", {}).get("point")
                if fr2.get("cont_adverse_mean")
                else fr2["adverse_mean"]["point"],
                "cont_adverse_ci": fr2.get("cont_adverse_mean"),
                "adverse_bps": fr2["adverse_mean"]["point"],
                "max_dd_bps": fr2["max_dd_mean"]["point"],
                "hole_inventory": fr2["hole_inventory_mean"]["point"],
                "exposure": fr2["exposure_mean"],
                "path_cost_bps": fr2["path_cost_mean"]["point"],
            }
        )

    # friction sweep stability: best policy same at 1 and 4 bps?
    best_by_fr = {}
    for fr in strategy_scores.get("friction_grid") or []:
        key = str(float(fr))
        order = sorted(
            ranked,
            key=lambda p: (
                pols[p]["friction_sweep"][key].get("cont_adverse_mean") or pols[p]["friction_sweep"][key]["adverse_mean"]
            )["point"],
        )
        best_by_fr[key] = order[0] if order else None

    core_kl = robustness.get("slices", {}).get("core", {}).get("kill_ladder", {})
    ext_kl = robustness.get("slices", {}).get("core_plus_extend", {}).get("kill_ladder", {})
    sol_kl = robustness.get("slices", {}).get("sol", {}).get("kill_ladder", {})
    core_nx = robustness.get("slices", {}).get("core", {}).get("nanex", {})
    ext_nx = robustness.get("slices", {}).get("core_plus_extend", {}).get("nanex", {})

    promotes = []
    holds = []

    def _add(label: str, verdict: str, why: str):
        (promotes if "Promote" in verdict else holds).append(
            {"object": label, "verdict": verdict, "why": why}
        )

    if core_kl.get("readiness") == "promote_as_risk_policy":
        if ext_kl.get("friction_cleared") and ext_kl.get("time_split_sign_stable"):
            _add(
                "kill_ladder (core+extend)",
                "Promote-as-risk-policy",
                f"Δ|mo|={ext_kl.get('delta_abs_mo_5s', {}).get('delta')} friction+time-split OK",
            )
        else:
            _add("kill_ladder (extend)", "Hold", "core Promote; extend weakens CI/sign")
    if core_nx.get("precision", 0) >= 0.85:
        prec_e = ext_nx.get("precision")
        if prec_e is not None and prec_e >= 0.80:
            _add(
                "nanex∩ssm",
                "Promote-as-risk-policy",
                f"precision core={core_nx.get('precision'):.3f} extend={prec_e:.3f}",
            )
        else:
            _add("nanex∩ssm (extend)", "Hold", f"extend precision={prec_e}")

    best = strategy_scores.get("best")
    if best in ("ladder_plus_v_restore", "ladder_plus_confirm_before_restore", "confirm_before_restore", "v_restore_confirm", "always_stay_wide"):
        _add(
            f"MM playbook::{best}",
            "Promote (med)",
            "Ranks best on cont adverse + max DD at 2bps friction — playbook not alpha",
        )
    if sol_kl.get("n", 0) >= 30 and sol_kl.get("readiness") == "promote_as_risk_policy":
        _add("kill_ladder SOL (DB+KR)", "Promote-as-risk-policy (med)", "SOL subsample full Promote bar")
    elif sol_kl.get("n", 0) >= 20 and sol_kl.get("friction_cleared"):
        _add(
            "kill_ladder SOL (DB+KR)",
            "Hold (promising)",
            f"n={sol_kl.get('n')} friction clears but readiness={sol_kl.get('readiness')} — underpowered time-split",
        )
    elif sol_kl.get("n", 0) > 0:
        _add("kill_ladder SOL", "Hold", f"n={sol_kl.get('n')} — underpowered or CI soft")
    else:
        _add("kill_ladder SOL", "Hold", "No SOL gated events / HL SOL empty in warehouse")
    occ = models.get("occurrence") or {}
    if occ.get("soft_promote"):
        _add(
            "occurrence model (expanded feats)",
            "Soft Promote",
            f"AUC_te={occ.get('auc_test'):.3f} Brier={occ.get('brier_test'):.3f}",
        )
    else:
        _add(
            "occurrence model",
            "Hold",
            f"AUC_te={occ.get('auc_test')} — bar not cleared or split issue",
        )
    sev = models.get("severity") or {}
    _add(
        "severity |ΔP| model",
        sev.get("verdict") or "Hold",
        f"ridge R²_te={sev.get('ridge_r2_test')} bayes R²={sev.get('bayes_ridge_r2_test')} ({sev.get('feature_note','')})",
    )
    _add(
        "dense TOB marking",
        "Promote (ops)" if book.get("summary", {}).get("dense_days_collector_hits", 0) > 0 else "Hold",
        book.get("recommendation", ""),
    )

    return {
        "strategy_rows": rows,
        "best_strategy_2bps": best,
        "best_by_friction": best_by_fr,
        "friction_rank_stable": len(set(best_by_fr.values())) == 1,
        "promotes": promotes,
        "holds": holds,
        "risk_not_vanity": True,
        "headline": (
            f"Best risk playbook={best}; "
            f"kill-ladder extend={ext_kl.get('readiness')}; "
            f"nanex prec extend={ext_nx.get('precision')}"
        ),
    }
