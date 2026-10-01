from __future__ import annotations
#!/usr/bin/env python3
"""V-recovery vs continuation quoting restore — policy sims (desk deliverable).

After gated SSM (10bps / i_c≥5) on real warehouse tape, classify V vs
continuation via recovery@5s (causal policies use recovery@1–2s only).
Simulate quote-size restore vs stay-wide; score with signed tape/mid
markout × size exposure. Emit PnL / markout / inventory-risk charts +
RISK_REPORT.md.

Desk object: info.crash_v_vs_continuation (TRADING_APPLICATIONS §3.2).
Honesty: MM playbook **sim** on real tape — not live orders, not tradable alpha.
"""


import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

APP = Path(__file__).resolve().parents[1]
BOOK = APP.parent
ROOT = BOOK.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(APP))

from common.event_panel import (  # noqa: E402
    DEFAULT_DAYS,
    DEFAULT_SYMBOLS,
    boot_mean,
    build_panel,
    event_arrays,
    jsonable,
    summarize,
)

OUT = APP / "mm_quoting" / "out"
FIG = OUT / "figs"

# Size schedules (relative to baseline quote size = 1.0)
WIDE_SIZE = 0.25
RESTORE_SIZE = 1.0
HOLD_S = 5.0  # post-event hold window for stay-wide

HONESTY = {
    "class": "MM_playbook_sim",
    "slice": "research_sim_on_real_tape",
    "live_orders": False,
    "fills": "synthetic_size_x_signed_markout",
    "alpha_claim": False,
    "promote_scope": "med_quoting_playbook_not_tradable",
    "clickhouse_mcp": False,
    "data": "warehouse_tape_gated_SSM_10bps_ic5",
    "book_objects": [
        "info.crash_v_vs_continuation",
        "risk.ssm_severity_gate_10bps",
    ],
}


def honesty_block() -> dict[str, Any]:
    """Fresh copy — never share/mutate module constant (jsonable bool→int trap)."""
    return {
        "class": "MM_playbook_sim",
        "slice": "research_sim_on_real_tape",
        "live_orders": False,
        "fills": "synthetic_size_x_signed_markout",
        "alpha_claim": False,
        "promote_scope": "med_quoting_playbook_not_tradable",
        "clickhouse_mcp": False,
        "data": "warehouse_tape_gated_SSM_10bps_ic5",
        "book_objects": [
            "info.crash_v_vs_continuation",
            "risk.ssm_severity_gate_10bps",
        ],
    }


def _policy_size_path(
    label: str,
    recovery_1s: float,
    recovery_2s: float,
    *,
    policy: str,
) -> dict[str, float]:
    """Map policy → size at horizons after event end.

    Sizes are relative multipliers on baseline quote size.
    """
    # oracle uses full 5s label (upper bound — not tradable live)
    is_v = label == "v_recovery"
    is_cont = label == "continuation"
    # causal confirms
    confirm_v_1 = np.isfinite(recovery_1s) and recovery_1s >= 0.5
    confirm_v_2 = np.isfinite(recovery_2s) and recovery_2s >= 0.5
    confirm_cont_2 = np.isfinite(recovery_2s) and recovery_2s < 0.2
    both_v = confirm_v_1 and confirm_v_2

    sizes = {"0.5s": WIDE_SIZE, "1.0s": WIDE_SIZE, "2.0s": WIDE_SIZE, "5.0s": WIDE_SIZE}

    if policy == "always_restore":
        sizes = {h: RESTORE_SIZE for h in sizes}
    elif policy == "always_stay_wide":
        sizes = {h: WIDE_SIZE for h in sizes}
    elif policy == "oracle_class":
        # perfect foresight of 5s class
        if is_v:
            sizes = {"0.5s": 0.6, "1.0s": 0.85, "2.0s": RESTORE_SIZE, "5.0s": RESTORE_SIZE}
        elif is_cont:
            sizes = {h: WIDE_SIZE for h in sizes}
        else:  # partial
            sizes = {"0.5s": WIDE_SIZE, "1.0s": 0.5, "2.0s": 0.7, "5.0s": 0.85}
    elif policy == "confirm_v_restore":
        # stay wide until +2s V confirm, else stay wide through 5s
        if confirm_v_1:
            sizes = {"0.5s": WIDE_SIZE, "1.0s": 0.7, "2.0s": RESTORE_SIZE, "5.0s": RESTORE_SIZE}
        elif confirm_v_2:
            sizes = {"0.5s": WIDE_SIZE, "1.0s": WIDE_SIZE, "2.0s": 0.85, "5.0s": RESTORE_SIZE}
        else:
            sizes = {h: WIDE_SIZE for h in sizes}
    elif policy == "confirm_before_restore":
        # expanded_lab / STRATEGY_LAB: require 1s AND 2s V confirm before full restore
        if both_v:
            sizes = {"0.5s": WIDE_SIZE, "1.0s": 0.7, "2.0s": RESTORE_SIZE, "5.0s": RESTORE_SIZE}
        elif confirm_v_2:
            sizes = {"0.5s": WIDE_SIZE, "1.0s": WIDE_SIZE, "2.0s": 0.6, "5.0s": 0.85}
        else:
            sizes = {h: WIDE_SIZE for h in sizes}
    elif policy == "cont_protect":
        # if continuation confirm @2s → stay wide; else gradual restore
        if confirm_cont_2:
            sizes = {h: WIDE_SIZE for h in sizes}
        elif confirm_v_2:
            sizes = {"0.5s": WIDE_SIZE, "1.0s": WIDE_SIZE, "2.0s": 0.85, "5.0s": RESTORE_SIZE}
        else:
            sizes = {"0.5s": WIDE_SIZE, "1.0s": 0.5, "2.0s": 0.7, "5.0s": 0.9}
    else:
        raise ValueError(policy)
    return sizes


def _score_event(ev: dict[str, Any], policy: str) -> dict[str, float]:
    """Inventory risk proxy: size × signed markout (adverse if price continues).

    Positive signed mo = continuation in crash direction = adverse for recovery /
    fade inventory. Cost = size * mo (maker inventory hurt when mo>0).
    Also report |mid path| × size as inventory excursion.
    """

    def _f(v: Any) -> float:
        if v is None:
            return float("nan")
        try:
            x = float(v)
            return x if np.isfinite(x) else float("nan")
        except (TypeError, ValueError):
            return float("nan")

    sizes = _policy_size_path(
        str(ev.get("label", "unknown")),
        _f(ev.get("recovery_1s")),
        _f(ev.get("recovery_2s")),
        policy=policy,
    )
    mo5 = _f(ev.get("mo_5s"))
    mid5 = _f(ev.get("mid_mo_5s"))
    sz5 = float(sizes["5.0s"])
    costs = []
    mid_costs = []
    for h, sk in [("0.5", "0.5s"), ("1", "1.0s"), ("5", "5.0s")]:
        mo = _f(ev.get(f"mo_{h}s"))
        sz = float(sizes[sk])
        if np.isfinite(mo):
            costs.append(sz * mo)
        mm = _f(ev.get(f"mid_mo_{h}s"))
        if np.isfinite(mm):
            mid_costs.append(sz * mm)
    inv_excursion = abs(sz5 * mo5) if np.isfinite(mo5) else float("nan")
    return {
        "size_5s": sz5,
        "cost_5s": sz5 * mo5 if np.isfinite(mo5) else float("nan"),
        "mid_cost_5s": sz5 * mid5 if np.isfinite(mid5) else float("nan"),
        "path_cost_mean": float(np.mean(costs)) if costs else float("nan"),
        "mid_path_cost_mean": float(np.mean(mid_costs)) if mid_costs else float("nan"),
        "abs_mo5": abs(mo5) if np.isfinite(mo5) else float("nan"),
        "abs_mid5": abs(mid5) if np.isfinite(mid5) else float("nan"),
        "exposure_size_mean": float(np.mean(list(sizes.values()))),
        "inv_excursion_5s": inv_excursion,
        # PnL proxy: negative of adverse cost (rebound capture when mo<0)
        "pnl_proxy_5s": -(sz5 * mo5) if np.isfinite(mo5) else float("nan"),
    }


POLICIES = [
    "always_stay_wide",
    "always_restore",
    "oracle_class",
    "confirm_v_restore",
    "confirm_before_restore",
    "cont_protect",
]

# Desk-facing focus set (oracle excluded from "live candidate" charts)
LIVE_CANDIDATES = [
    "always_stay_wide",
    "confirm_v_restore",
    "confirm_before_restore",
    "cont_protect",
    "always_restore",
]


def simulate_policies(events: list[dict[str, Any]]) -> dict[str, Any]:
    by_policy: dict[str, Any] = {}
    for pol in POLICIES:
        rows = [_score_event(ev, pol) for ev in events]
        cost = np.asarray([r["cost_5s"] for r in rows], dtype=np.float64)
        path = np.asarray([r["path_cost_mean"] for r in rows], dtype=np.float64)
        mid_c = np.asarray([r["mid_cost_5s"] for r in rows], dtype=np.float64)
        expo = np.asarray([r["exposure_size_mean"] for r in rows], dtype=np.float64)
        pnl = np.asarray([r["pnl_proxy_5s"] for r in rows], dtype=np.float64)
        inv = np.asarray([r["inv_excursion_5s"] for r in rows], dtype=np.float64)
        adv = cost[np.isfinite(cost) & (cost > 0)]
        labs = [e.get("label") for e in events]
        cont_cost = np.asarray(
            [r["cost_5s"] for r, l in zip(rows, labs) if l == "continuation"], dtype=np.float64
        )
        v_cost = np.asarray(
            [r["cost_5s"] for r, l in zip(rows, labs) if l == "v_recovery"], dtype=np.float64
        )
        by_policy[pol] = {
            "n": len(rows),
            "cost_5s": {**summarize(cost), "boot": boot_mean(cost, seed=11)},
            "path_cost": {**summarize(path), "boot": boot_mean(path, seed=12)},
            "mid_cost_5s": {**summarize(mid_c), "boot": boot_mean(mid_c, seed=13)},
            "pnl_proxy_5s": {**summarize(pnl), "boot": boot_mean(pnl, seed=17)},
            "inv_excursion_5s": {**summarize(inv), "boot": boot_mean(inv, seed=18)},
            "exposure": summarize(expo),
            "adverse_cost_5s": {
                **summarize(adv),
                "boot": boot_mean(adv, seed=14),
                "n_adverse": int(adv.size),
            },
            "cost_on_continuation": {
                **summarize(cont_cost),
                "boot": boot_mean(cont_cost, seed=15),
            },
            "cost_on_v": {**summarize(v_cost), "boot": boot_mean(v_cost, seed=16)},
        }
    by_class: dict[str, Any] = {}
    for lab in ("v_recovery", "continuation", "partial"):
        sub = [e for e in events if e.get("label") == lab]
        if not sub:
            by_class[lab] = {"n": 0}
            continue
        mo5 = event_arrays(sub, "mo_5s")
        mid5 = event_arrays(sub, "mid_mo_5s")
        by_class[lab] = {
            "n": len(sub),
            "mo_5s": {**summarize(mo5), "boot": boot_mean(mo5, seed=21)},
            "mid_mo_5s": {**summarize(mid5), "boot": boot_mean(mid5, seed=22)},
            "share": float(len(sub) / max(len(events), 1)),
        }
    return {"by_policy": by_policy, "by_class": by_class}


def cohort_split(events: list[dict[str, Any]]) -> dict[str, Any]:
    out = {}
    for name in ("early", "late", "all"):
        if name == "all":
            sub = events
        else:
            sub = [e for e in events if e.get("cohort") == name]
        out[name] = simulate_policies(sub) if sub else {"by_policy": {}, "by_class": {}, "n": 0}
        out[name]["n"] = len(sub)
        if sub:
            labels = [e.get("label") for e in sub]
            out[name]["share_v"] = float(sum(1 for x in labels if x == "v_recovery") / len(sub))
            out[name]["share_cont"] = float(sum(1 for x in labels if x == "continuation") / len(sub))
    return out


def policy_ranking(sim: dict[str, Any], *, key: str = "cost_on_continuation") -> list[dict[str, Any]]:
    """Rank by continuation adverse cost (lower = better MM protect)."""
    rows = []
    for pol, d in (sim.get("by_policy") or {}).items():
        metric = (d.get(key) or {}).get("mean", float("nan"))
        rows.append(
            {
                "policy": pol,
                "cont_cost_mean": (d.get("cost_on_continuation") or {}).get("mean"),
                "path_cost_mean": (d.get("path_cost") or {}).get("mean"),
                "pnl_proxy_mean": (d.get("pnl_proxy_5s") or {}).get("mean"),
                "inv_excursion_mean": (d.get("inv_excursion_5s") or {}).get("mean"),
                "adverse_mean": (d.get("adverse_cost_5s") or {}).get("mean"),
                "v_cost_mean": (d.get("cost_on_v") or {}).get("mean"),
                "exposure_mean": (d.get("exposure") or {}).get("mean"),
                "rank_metric": metric,
                "n": d.get("n"),
            }
        )
    rows.sort(key=lambda r: (r["rank_metric"] if np.isfinite(r["rank_metric"] or np.nan) else 1e9))
    return rows


def event_paths(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Time-ordered cumulative PnL / inventory / exposure paths per policy.

    Events sorted by (day, ts_end). PnL proxy = cumsum(−size×mo@5s).
    Inventory risk = cumsum(|size×mo@5s|) and rolling mean exposure.
    """
    ordered = sorted(
        events,
        key=lambda e: (str(e.get("day") or ""), int(e.get("ts_end") or 0)),
    )
    paths: dict[str, Any] = {"n": len(ordered), "order_key": "day,ts_end"}
    for pol in POLICIES:
        rows = [_score_event(ev, pol) for ev in ordered]
        pnl = np.asarray([r["pnl_proxy_5s"] for r in rows], dtype=np.float64)
        cost = np.asarray([r["cost_5s"] for r in rows], dtype=np.float64)
        inv = np.asarray([r["inv_excursion_5s"] for r in rows], dtype=np.float64)
        expo = np.asarray([r["exposure_size_mean"] for r in rows], dtype=np.float64)
        labs = [e.get("label") for e in ordered]
        # replace nan with 0 for cumsum continuity; track coverage
        pnl_f = np.where(np.isfinite(pnl), pnl, 0.0)
        inv_f = np.where(np.isfinite(inv), inv, 0.0)
        cost_f = np.where(np.isfinite(cost), cost, 0.0)
        cum_pnl = np.cumsum(pnl_f)
        cum_inv = np.cumsum(inv_f)
        cum_adv = np.cumsum(np.where(cost_f > 0, cost_f, 0.0))
        # max drawdown on cum PnL
        peak = np.maximum.accumulate(cum_pnl) if cum_pnl.size else cum_pnl
        dd = cum_pnl - peak
        max_dd = float(dd.min()) if dd.size else float("nan")
        paths[pol] = {
            "cum_pnl_proxy": cum_pnl.tolist(),
            "cum_inv_excursion": cum_inv.tolist(),
            "cum_adverse_cost": cum_adv.tolist(),
            "exposure": expo.tolist(),
            "labels": labs,
            "final_pnl_proxy": float(cum_pnl[-1]) if cum_pnl.size else float("nan"),
            "final_inv_excursion": float(cum_inv[-1]) if cum_inv.size else float("nan"),
            "final_adverse_cost": float(cum_adv[-1]) if cum_adv.size else float("nan"),
            "max_dd_pnl_proxy": max_dd,
            "mean_exposure": float(np.nanmean(expo)) if expo.size else float("nan"),
            "n_scored": int(np.isfinite(pnl).sum()),
        }
    return paths


def decide_promote(cohort: dict[str, Any]) -> dict[str, Any]:
    """Honesty gate: protect on continuation; restore on V.

    Promote (med playbook) if class-conditional mo sep is early/late stable AND
    protective policies beat always_restore on continuation cost both cohorts.
    """
    early = cohort.get("early") or {}
    late = cohort.get("late") or {}
    all_ = cohort.get("all") or {}

    def _mo(cl: dict, lab: str) -> float:
        return float((((cl.get("by_class") or {}).get(lab) or {}).get("mo_5s") or {}).get("mean", np.nan))

    def _cont_cost(cl: dict, pol: str) -> float:
        return float(
            (((cl.get("by_policy") or {}).get(pol) or {}).get("cost_on_continuation") or {}).get(
                "mean", np.nan
            )
        )

    mo_v_e, mo_c_e = _mo(early, "v_recovery"), _mo(early, "continuation")
    mo_v_l, mo_c_l = _mo(late, "v_recovery"), _mo(late, "continuation")
    class_sep_early = np.isfinite(mo_v_e) and np.isfinite(mo_c_e) and (mo_v_e < mo_c_e)
    class_sep_late = np.isfinite(mo_v_l) and np.isfinite(mo_c_l) and (mo_v_l < mo_c_l)

    protect_pols = (
        "always_stay_wide",
        "confirm_v_restore",
        "confirm_before_restore",
        "cont_protect",
    )

    def _protects(cl: dict) -> bool:
        rest = _cont_cost(cl, "always_restore")
        if not np.isfinite(rest):
            return False
        cands = [_cont_cost(cl, p) for p in protect_pols]
        cands = [x for x in cands if np.isfinite(x)]
        return bool(cands) and min(cands) < rest

    protect_early = _protects(early)
    protect_late = _protects(late)
    ranking = policy_ranking(all_)
    # best live candidate (exclude oracle)
    live_rank = [r for r in ranking if r["policy"] != "oracle_class"]
    best = live_rank[0]["policy"] if live_rank else (ranking[0]["policy"] if ranking else None)
    promote_ok = bool(class_sep_early and class_sep_late and protect_early and protect_late)
    decision = "Promote" if promote_ok else "Hold"
    why_parts = []
    if class_sep_early and class_sep_late:
        why_parts.append(
            f"class sep stable (V mo early/late={mo_v_e:.1f}/{mo_v_l:.1f}; "
            f"cont={mo_c_e:.1f}/{mo_c_l:.1f})"
        )
    else:
        why_parts.append(
            f"V vs cont mo@5s sep unstable (early V={mo_v_e}/C={mo_c_e}; late V={mo_v_l}/C={mo_c_l})"
        )
    if protect_early and protect_late:
        why_parts.append(
            "stay-wide/confirm/cont_protect beat blind restore on continuation cost both cohorts"
        )
    else:
        why_parts.append(
            "protective policies do not beat always_restore on continuation cost both cohorts"
        )
    return {
        "decision": decision,
        "object": "info.crash_v_vs_continuation / mm quoting restore",
        "best_policy_pooled": best,
        "ranking_pooled": ranking,
        "ranking_live_candidates": live_rank,
        "class_sep_early": class_sep_early,
        "class_sep_late": class_sep_late,
        "protect_early": protect_early,
        "protect_late": protect_late,
        "mo_v_early": mo_v_e,
        "mo_c_early": mo_c_e,
        "mo_v_late": mo_v_l,
        "mo_c_late": mo_c_l,
        "cont_cost": {
            "early": {p: _cont_cost(early, p) for p in (*protect_pols, "always_restore")},
            "late": {p: _cont_cost(late, p) for p in (*protect_pols, "always_restore")},
        },
        "why": "; ".join(why_parts),
        "confidence": "med" if promote_ok else "low–med",
        "note": (
            "Promote = med quoting playbook (restore after V-confirm; stay wide on cont), "
            "not tradable fade. Ranked on continuation adverse cost, not pooled rebound capture. "
            "confirm_before_restore aligns with expanded_lab / strategy_lab best-risk stub."
        ),
    }


def plot_figs(
    cohort: dict[str, Any],
    decision: dict[str, Any],
    paths: dict[str, Any],
) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG.mkdir(parents=True, exist_ok=True)
    paths_out: list[str] = []

    colors = {
        "always_stay_wide": "#2a7a4b",
        "always_restore": "#b33a3a",
        "oracle_class": "#888888",
        "confirm_v_restore": "#2a5f8f",
        "confirm_before_restore": "#5b3a8f",
        "cont_protect": "#c47a1a",
    }

    # Fig 1: policy continuation costs early/late
    fig, ax = plt.subplots(figsize=(9.0, 4.4))
    pols = POLICIES
    x = np.arange(len(pols))
    w = 0.35
    early_c = [
        (((cohort["early"].get("by_policy") or {}).get(p) or {}).get("cost_on_continuation") or {}).get(
            "mean", np.nan
        )
        for p in pols
    ]
    late_c = [
        (((cohort["late"].get("by_policy") or {}).get(p) or {}).get("cost_on_continuation") or {}).get(
            "mean", np.nan
        )
        for p in pols
    ]
    ax.bar(x - w / 2, early_c, w, label="early", color="#3a7")
    ax.bar(x + w / 2, late_c, w, label="late", color="#c65")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels(pols, rotation=28, ha="right")
    ax.set_ylabel("mean cost on continuation (size × mo bps)")
    ax.set_title("Quoting policies — continuation adverse cost (research sim)")
    ax.legend()
    p = FIG / "fig_policy_path_cost.png"
    fig.tight_layout()
    fig.savefig(p, dpi=140)
    plt.close(fig)
    paths_out.append(str(p))

    # Fig 2: class markouts
    fig, ax = plt.subplots(figsize=(7, 4))
    labs = ["v_recovery", "partial", "continuation"]
    for i, name in enumerate(("early", "late")):
        means = [
            (((cohort[name].get("by_class") or {}).get(lab) or {}).get("mo_5s") or {}).get("mean", np.nan)
            for lab in labs
        ]
        ax.plot(labs, means, marker="o", label=name)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_ylabel("signed tape mo@5s (bps)")
    ax.set_title("Markout by recovery class (real tape, gated SSM)")
    ax.legend()
    p = FIG / "fig_class_markout.png"
    fig.tight_layout()
    fig.savefig(p, dpi=140)
    plt.close(fig)
    paths_out.append(str(p))

    # Fig 3: ranking strip (live candidates)
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    rank = decision.get("ranking_live_candidates") or [
        r for r in (decision.get("ranking_pooled") or []) if r["policy"] != "oracle_class"
    ]
    if rank:
        ax.barh(
            [r["policy"] for r in rank][::-1],
            [r.get("cont_cost_mean") for r in rank][::-1],
            color=[colors.get(r["policy"], "#58a") for r in rank][::-1],
        )
        ax.axvline(0, color="k", lw=0.6)
        ax.set_xlabel("continuation cost mean (bps·size)")
        ax.set_title(
            f"Pooled ranking (cont adverse) — {decision.get('decision')} (med playbook)"
        )
    p = FIG / "fig_policy_rank.png"
    fig.tight_layout()
    fig.savefig(p, dpi=140)
    plt.close(fig)
    paths_out.append(str(p))

    # Fig 4: cumulative PnL proxy
    fig, ax = plt.subplots(figsize=(9.0, 4.6))
    for pol in LIVE_CANDIDATES:
        d = paths.get(pol) or {}
        y = d.get("cum_pnl_proxy") or []
        if y:
            ax.plot(y, label=pol, color=colors.get(pol, None), lw=1.6)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlabel("event index (day, ts_end ordered)")
    ax.set_ylabel("cumulative PnL proxy (−size×mo@5s)")
    ax.set_title("Event-study PnL proxy by policy (not live fills)")
    ax.legend(loc="best", fontsize=8)
    p = FIG / "fig_pnl_cumulative.png"
    fig.tight_layout()
    fig.savefig(p, dpi=140)
    plt.close(fig)
    paths_out.append(str(p))

    # Fig 5: inventory risk — cum adverse + mean exposure inset style
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(10.5, 4.2))
    for pol in LIVE_CANDIDATES:
        d = paths.get(pol) or {}
        y = d.get("cum_inv_excursion") or []
        if y:
            ax0.plot(y, label=pol, color=colors.get(pol, None), lw=1.5)
    ax0.set_xlabel("event index")
    ax0.set_ylabel("cumulative |size×mo@5s|")
    ax0.set_title("Inventory risk proxy (excursion)")
    ax0.legend(fontsize=7)

    for pol in LIVE_CANDIDATES:
        d = paths.get(pol) or {}
        y = d.get("cum_adverse_cost") or []
        if y:
            ax1.plot(y, label=pol, color=colors.get(pol, None), lw=1.5)
    ax1.set_xlabel("event index")
    ax1.set_ylabel("cumulative adverse cost (mo>0 only)")
    ax1.set_title("Continuation / adverse inventory hits")
    ax1.legend(fontsize=7)
    p = FIG / "fig_inventory_risk.png"
    fig.tight_layout()
    fig.savefig(p, dpi=140)
    plt.close(fig)
    paths_out.append(str(p))

    # Fig 6: markout histogram by class
    fig, ax = plt.subplots(figsize=(8.0, 4.2))
    all_ev = None
    # rebuild from cohort all by_class means not enough — use summary events later via paths labels
    # Pull from cohort all via stored means only for annotation; hist needs raw — use paths labels + score
    # We pass markout via paths from always_restore cost (= mo when size=1)
    restore = paths.get("always_restore") or {}
    # Use pnl of always_restore negated = mo; split by label
    # Better: re-score from decision context — plot using cohort class means with boot CI bars
    labs_c = ["v_recovery", "continuation", "partial"]
    means = []
    los = []
    his = []
    ns = []
    for lab in labs_c:
        d = ((cohort["all"].get("by_class") or {}).get(lab) or {})
        mo = d.get("mo_5s") or {}
        boot = mo.get("boot") or {}
        means.append(mo.get("mean", np.nan))
        los.append(boot.get("lo", np.nan))
        his.append(boot.get("hi", np.nan))
        ns.append(d.get("n", 0))
    x = np.arange(len(labs_c))
    yerr = [
        [m - lo if np.isfinite(m) and np.isfinite(lo) else 0 for m, lo in zip(means, los)],
        [hi - m if np.isfinite(m) and np.isfinite(hi) else 0 for m, hi in zip(means, his)],
    ]
    ax.bar(x, means, color=["#2a7a4b", "#b33a3a", "#888"], yerr=yerr, capsize=4, alpha=0.85)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{l}\nn={n}" for l, n in zip(labs_c, ns)])
    ax.set_ylabel("signed tape mo@5s (bps)")
    ax.set_title("Class markout @5s with bootstrap CI (research / sim)")
    p = FIG / "fig_markout_ci.png"
    fig.tight_layout()
    fig.savefig(p, dpi=140)
    plt.close(fig)
    paths_out.append(str(p))

    # Fig 7: exposure vs cont-cost scatter (risk/return for playbook)
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    for r in decision.get("ranking_pooled") or []:
        pol = r["policy"]
        if pol == "oracle_class":
            marker = "x"
        else:
            marker = "o"
        ax.scatter(
            r.get("exposure_mean"),
            r.get("cont_cost_mean"),
            s=80,
            c=colors.get(pol, "#58a"),
            marker=marker,
            label=pol,
            zorder=3,
        )
        ax.annotate(pol, (r.get("exposure_mean") or 0, r.get("cont_cost_mean") or 0), fontsize=7, xytext=(4, 4), textcoords="offset points")
    ax.set_xlabel("mean size exposure")
    ax.set_ylabel("continuation adverse cost")
    ax.set_title("Playbook risk map: exposure vs cont protect")
    ax.axhline(0, color="k", lw=0.5)
    p = FIG / "fig_exposure_vs_cont.png"
    fig.tight_layout()
    fig.savefig(p, dpi=140)
    plt.close(fig)
    paths_out.append(str(p))

    return paths_out


def _fmt_boot(d: dict[str, Any] | None) -> str:
    d = d or {}
    boot = d.get("boot") or {}
    return f"mean={d.get('mean')} bootCI=[{boot.get('lo')}, {boot.get('hi')}]"


def write_risk_report(
    summary: dict[str, Any],
    decision: dict[str, Any],
    paths: dict[str, Any],
    figs: list[str],
) -> Path:
    """Desk-facing RISK_REPORT.md (sibling paper_harness style)."""
    cohort = summary["cohort"]
    all_ = cohort["all"]
    honesty = summary.get("honesty") or HONESTY
    lines = [
        "# MM quoting risk report — V vs continuation restore",
        "",
        f"Generated: `{summary['generated']}`",
        "",
        f"**Class:** {honesty.get('class')} — MM playbook on real tape, **not** PnL alpha. "
        f"**Fills:** {honesty.get('fills')}. **Live orders:** `{honesty.get('live_orders')}`.",
        "",
        "## Sample",
        f"- Days: `{summary['days']}` · symbols: `{summary['symbols']}` · venues: `{summary['venues']}`",
        f"- Gated SSM 10bps/ic5 events: **n={summary['n_events']}** "
        f"(cells complete {summary['n_complete']}/{summary['n_cells']})",
        f"- Gate: `{summary.get('gate')}` · z*={summary.get('z_star', 6)}",
        "",
        "## Class / markout",
        f"- share_V={all_.get('share_v'):.3f} · share_cont={all_.get('share_cont'):.3f}",
    ]
    for lab in ("v_recovery", "continuation", "partial"):
        d = (all_.get("by_class") or {}).get(lab) or {}
        mo = d.get("mo_5s") or {}
        boot = mo.get("boot") or {}
        lines.append(
            f"- **{lab}** n={d.get('n')} mo@5s mean={mo.get('mean')} "
            f"CI=[{boot.get('lo')}, {boot.get('hi')}]"
        )
    lines += [
        "",
        "## Policy sims (continuation adverse = size×mo@5s on continuation)",
    ]
    for pol in POLICIES:
        d = (all_.get("by_policy") or {}).get(pol) or {}
        cc = d.get("cost_on_continuation") or {}
        pnl = d.get("pnl_proxy_5s") or {}
        inv = d.get("inv_excursion_5s") or {}
        expo = (d.get("exposure") or {}).get("mean")
        path_d = paths.get(pol) or {}
        lines.append(
            f"- `{pol}`: cont_cost={_fmt_boot(cc)} | pnl_proxy={pnl.get('mean')} | "
            f"inv_exc={inv.get('mean')} | exposure={expo} | "
            f"cum_pnl={path_d.get('final_pnl_proxy')} max_dd={path_d.get('max_dd_pnl_proxy')}"
        )
    lines += [
        "",
        "## Time-split",
        f"- Early best (live): {[r for r in policy_ranking(cohort['early']) if r['policy'] != 'oracle_class'][:2]}",
        f"- Late best (live): {[r for r in policy_ranking(cohort['late']) if r['policy'] != 'oracle_class'][:2]}",
        f"- protect_early={decision.get('protect_early')} protect_late={decision.get('protect_late')}",
        "",
        "## Decision",
        f"- **{decision['decision']}** (`{decision['object']}`) — conf={decision.get('confidence')}",
        f"- Why: {decision['why']}",
        f"- Best live candidate: `{decision.get('best_policy_pooled')}`",
        f"- Note: {decision.get('note')}",
        "",
        "## Identification",
        "- Gate: SSM z*=6 + |ΔP|≥10bps + i_c≥5 (Nanex∩SSM is sibling escalate — not scored here)",
        "- Labels: recovery@5s (V≥0.5, cont<0.2); causal policies use recovery@1–2s only",
        "- Cost: size × signed tape markout (crash-direction); mid when TOB present",
        "- PnL proxy: −(size×mo@5s) event-ordered cumsum — **research metric**, not account PnL",
        "- Inventory risk: |size×mo@5s| cumsum + adverse-only cumsum",
        "- Size schedule: wide=0.25×, restore=1.0× baseline",
        "",
        "## Figures",
    ]
    for f in figs:
        lines.append(f"- `{Path(f).name}`")
    lines += [
        "",
        "## Honesty",
        f"- `{json.dumps(honesty)}`",
        "",
        "## Blockers / non-claims",
        "- Dense mid markout still sparse on Kraken — tape is ceiling",
        "- `oracle_class` is upper bound only (not live)",
        "- Fade-the-V remains **low** alpha until mid CI clears Promote for `exec.tape_markout`",
        "- Tick-level equity curves live in sibling `strategy_lab/` / `paper_harness/` — this package is event-study playbook",
        "- No live quoting; no ClickHouse MCP",
    ]
    path = OUT / "RISK_REPORT.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def write_report(summary: dict[str, Any], decision: dict[str, Any], figs: list[str]) -> Path:
    cohort = summary["cohort"]
    all_ = cohort["all"]
    honesty = summary.get("honesty") or HONESTY
    lines = [
        "# MM quoting — V vs continuation restore — EXP_REPORT",
        "",
        f"Generated: {summary['generated']}",
        f"Sample: days={summary['days']} · symbols={summary['symbols']} · venues={summary['venues']}",
        f"Events gated 10bps/ic5: **n={summary['n_events']}** (cells complete {summary['n_complete']}/{summary['n_cells']})",
        f"Honesty: `{honesty.get('slice')}` · live_orders=`{honesty.get('live_orders')}` · alpha_claim=`{honesty.get('alpha_claim')}`",
        "",
        "## Class shares",
        f"- Pooled share_V={all_.get('share_v'):.3f} · share_cont={all_.get('share_cont'):.3f}",
        f"- Early share_V={cohort['early'].get('share_v')} · Late share_V={cohort['late'].get('share_v')}",
        "",
        "## Class-stratified tape mo@5s (bps)",
    ]
    for lab in ("v_recovery", "continuation", "partial"):
        d = (all_.get("by_class") or {}).get(lab) or {}
        mo = d.get("mo_5s") or {}
        lines.append(
            f"- **{lab}** n={d.get('n')} mean={mo.get('mean')} "
            f"bootCI=[{(mo.get('boot') or {}).get('lo')}, {(mo.get('boot') or {}).get('hi')}]"
        )
    lines += ["", "## Policy sims (continuation adverse = size×mo@5s on continuation events)"]
    for pol in POLICIES:
        d = (all_.get("by_policy") or {}).get(pol) or {}
        cc = d.get("cost_on_continuation") or {}
        pc = d.get("path_cost") or {}
        pnl = d.get("pnl_proxy_5s") or {}
        inv = d.get("inv_excursion_5s") or {}
        lines.append(
            f"- `{pol}`: cont_cost mean={cc.get('mean')} "
            f"boot=[{(cc.get('boot') or {}).get('lo')}, {(cc.get('boot') or {}).get('hi')}] "
            f"| path_cost={pc.get('mean')} pnl_proxy={pnl.get('mean')} "
            f"inv_exc={inv.get('mean')} exposure={((d.get('exposure') or {}).get('mean'))}"
        )
    lines += [
        "",
        "## Time-split",
        f"- Early best path: {policy_ranking(cohort['early'])[:2]}",
        f"- Late best path: {policy_ranking(cohort['late'])[:2]}",
        "",
        "## Decision",
        f"- **{decision['decision']}** (`{decision['object']}`) — conf={decision.get('confidence')}",
        f"- Why: {decision['why']}",
        f"- Best pooled policy (excl. oracle): `{decision.get('best_policy_pooled')}`",
        f"- Note: {decision.get('note')}",
        "",
        "## Identification",
        "- Gate: SSM z*=6 + |ΔP|≥10bps + i_c≥5",
        "- Labels: recovery@5s (V≥0.5, cont<0.2); causal policies use recovery@1–2s only",
        "- Cost: size × signed tape markout (crash-direction); mid markout when TOB present",
        "- Size schedule: wide=0.25×, restore=1.0× baseline",
        "- Desk report: `out/RISK_REPORT.md`",
        "",
        "## Figures",
    ]
    for f in figs:
        lines.append(f"- `{Path(f).name}`")
    lines += [
        "",
        "## Blockers",
        "- Dense mid markout still sparse on Kraken — tape is ceiling",
        "- Oracle_class is upper bound only (not live)",
        "- Fade-the-V remains **low** alpha until mid CI clears Promote for exec.tape_markout",
        "- Event-study only; tick equity in strategy_lab / paper_harness",
    ]
    path = APP / "mm_quoting" / "EXP_REPORT.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def build_metrics(summary: dict[str, Any], decision: dict[str, Any], paths: dict[str, Any]) -> dict[str, Any]:
    all_ = summary["cohort"]["all"]
    by_pol = all_.get("by_policy") or {}
    slim_pols = {}
    for pol in POLICIES:
        d = by_pol.get(pol) or {}
        pd = paths.get(pol) or {}
        slim_pols[pol] = {
            "cont_cost_mean": (d.get("cost_on_continuation") or {}).get("mean"),
            "cont_cost_boot": (d.get("cost_on_continuation") or {}).get("boot"),
            "pnl_proxy_mean": (d.get("pnl_proxy_5s") or {}).get("mean"),
            "inv_excursion_mean": (d.get("inv_excursion_5s") or {}).get("mean"),
            "exposure_mean": (d.get("exposure") or {}).get("mean"),
            "cum_pnl_final": pd.get("final_pnl_proxy"),
            "cum_inv_final": pd.get("final_inv_excursion"),
            "cum_adverse_final": pd.get("final_adverse_cost"),
            "max_dd_pnl_proxy": pd.get("max_dd_pnl_proxy"),
        }
    by_cls = {}
    for lab in ("v_recovery", "continuation", "partial"):
        d = (all_.get("by_class") or {}).get(lab) or {}
        mo = d.get("mo_5s") or {}
        by_cls[lab] = {
            "n": d.get("n"),
            "mo_5s_mean": mo.get("mean"),
            "mo_5s_boot": mo.get("boot"),
            "share": d.get("share"),
        }
    return {
        "generated": summary["generated"],
        "n_events": summary["n_events"],
        "n_complete": summary["n_complete"],
        "n_cells": summary["n_cells"],
        "decision": decision.get("decision"),
        "confidence": decision.get("confidence"),
        "best_policy": decision.get("best_policy_pooled"),
        "share_v": all_.get("share_v"),
        "share_cont": all_.get("share_cont"),
        "by_class": by_cls,
        "by_policy": slim_pols,
        "honesty": summary.get("honesty") or HONESTY,
        "why": decision.get("why"),
    }


def build_notebook(summary: dict[str, Any], decision: dict[str, Any]) -> Path:
    import base64

    def _md(text: str) -> dict:
        return {"cell_type": "markdown", "metadata": {}, "source": [l + "\n" for l in text.split("\n")]}

    def _code(src: str, outputs: list | None = None, n: int = 1) -> dict:
        return {
            "cell_type": "code",
            "execution_count": n,
            "metadata": {},
            "outputs": outputs or [],
            "source": [l + "\n" for l in src.split("\n")],
        }

    def _img(path: Path) -> dict:
        return {
            "output_type": "display_data",
            "data": {
                "image/png": base64.b64encode(path.read_bytes()).decode("ascii"),
                "text/plain": ["<IPython.core.display.Image object>"],
            },
            "metadata": {},
        }

    all_ = summary["cohort"]["all"]
    honesty = summary.get("honesty") or HONESTY
    lines = [
        f"n_events={summary['n_events']} decision={decision['decision']}",
        f"share_V={all_.get('share_v')} best={decision.get('best_policy_pooled')}",
        f"honesty={honesty.get('slice')} live={honesty.get('live_orders')}",
        f"why={decision.get('why')}",
    ]
    stream = {"output_type": "stream", "name": "stdout", "text": [l + "\n" for l in lines]}
    fig_cells = [
        ("## Policy continuation costs (early / late)", "fig_policy_path_cost.png"),
        ("## Class markouts", "fig_class_markout.png"),
        ("## Ranking (live candidates)", "fig_policy_rank.png"),
        ("## Cumulative PnL proxy", "fig_pnl_cumulative.png"),
        ("## Inventory risk", "fig_inventory_risk.png"),
        ("## Markout CI by class", "fig_markout_ci.png"),
        ("## Exposure vs continuation cost", "fig_exposure_vs_cont.png"),
    ]
    cells = [
        _md(
            "# V vs continuation quoting restore\n\n"
            "Gated SSM events → recovery class → size restore vs stay-wide policy sims.\n"
            f"**Decision: {decision['decision']}** — {decision.get('why')}\n\n"
            f"Honesty: `{honesty.get('slice')}` · live_orders=`{honesty.get('live_orders')}` · "
            "not tradable alpha."
        ),
        _code(
            "from pathlib import Path\nimport json\n"
            "OUT = Path('out').resolve()\n"
            "s = json.loads((OUT / 'mm_quoting_summary.json').read_text())\n"
            "m = json.loads((OUT / 'metrics.json').read_text())\n"
            "d = s['decision']\n"
            "print('n_events', s['n_events'], 'decision', d['decision'])\n"
            "print('best', d.get('best_policy_pooled'))\n"
            "print('honesty', m.get('honesty'))\n"
            "print('why', d.get('why'))\n",
            outputs=[stream],
        ),
    ]
    n = 2
    for title, fname in fig_cells:
        fp = FIG / fname
        cells.append(_md(title))
        cells.append(
            _code(
                f"from IPython.display import Image, display\ndisplay(Image('out/figs/{fname}'))\n",
                outputs=[_img(fp)] if fp.exists() else [],
                n=n,
            )
        )
        n += 1
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "cells": cells,
    }
    path = APP / "mm_quoting" / "v_continuation_quoting.ipynb"
    path.write_text(json.dumps(nb, indent=1))
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description="MM V/continuation quoting playbook (research sim)")
    ap.add_argument("--days", nargs="*", default=None)
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--include-sol", action="store_true")
    ap.add_argument("--max-files", type=int, default=24)
    ap.add_argument("--reuse-panel", type=str, default=None, help="Reuse panel_cache.json")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)

    default_cache = OUT / "panel_cache.json"
    reuse = args.reuse_panel or (str(default_cache) if default_cache.exists() and not args.days else None)

    if reuse and Path(reuse).exists():
        print(f"Reusing panel {reuse}", flush=True)
        panel = json.loads(Path(reuse).read_text())
    else:
        print("Building event panel from warehouse tape…", flush=True)
        panel = build_panel(
            days=args.days or DEFAULT_DAYS,
            symbols=args.symbols or DEFAULT_SYMBOLS,
            include_sol=args.include_sol,
            max_files=args.max_files,
        )
    events = panel["events"]
    print(f"n_events={len(events)} complete_cells={panel.get('n_complete')}/{panel.get('n_cells')}", flush=True)

    cohort = cohort_split(events)
    decision = decide_promote(cohort)
    paths = event_paths(events)
    figs = plot_figs(cohort, decision, paths)

    summary = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "days": panel["days"],
        "symbols": panel["symbols"],
        "venues": panel["venues"],
        "n_cells": panel["n_cells"],
        "n_complete": panel["n_complete"],
        "n_events": panel["n_events"],
        "gate": panel["gate"],
        "z_star": panel.get("z_star", 6.0),
        "cohort": cohort,
        "decision": decision,
        "paths_summary": {
            pol: {
                k: (paths.get(pol) or {}).get(k)
                for k in (
                    "final_pnl_proxy",
                    "final_inv_excursion",
                    "final_adverse_cost",
                    "max_dd_pnl_proxy",
                    "mean_exposure",
                    "n_scored",
                )
            }
            for pol in POLICIES
        },
        "figs": figs,
        "wide_size": WIDE_SIZE,
        "restore_size": RESTORE_SIZE,
        "honesty": honesty_block(),
    }
    # Dump summary without running honesty through jsonable (bool is subclass of int → 0/1)
    summary_dump = jsonable({k: v for k, v in summary.items() if k != "honesty"})
    summary_dump["honesty"] = honesty_block()
    (OUT / "mm_quoting_summary.json").write_text(json.dumps(summary_dump, indent=2))
    (OUT / "paths.json").write_text(json.dumps(jsonable(paths), indent=2))
    metrics = build_metrics(summary, decision, paths)
    metrics_out = jsonable({k: v for k, v in metrics.items() if k != "honesty"})
    metrics_out["honesty"] = honesty_block()
    (OUT / "metrics.json").write_text(json.dumps(metrics_out, indent=2))

    # full panel cache for feature_models sibling reuse
    (OUT / "panel_cache.json").write_text(
        json.dumps(
            jsonable(
                {
                    "days": panel["days"],
                    "symbols": panel["symbols"],
                    "venues": panel["venues"],
                    "n_cells": panel["n_cells"],
                    "n_complete": panel["n_complete"],
                    "n_events": panel["n_events"],
                    "gate": panel["gate"],
                    "z_star": panel.get("z_star", 6.0),
                    "cells": panel["cells"],
                    "events": panel["events"],
                }
            ),
            indent=2,
        )
    )
    slim = [
        {
            k: e.get(k)
            for k in (
                "venue",
                "symbol",
                "day",
                "cohort",
                "label",
                "dp_pct",
                "i_c",
                "dt_s",
                "ts_end",
                "z_peak",
                "recovery_5s",
                "recovery_1s",
                "recovery_2s",
                "mo_0.5s",
                "mo_1s",
                "mo_5s",
                "mid_mo_5s",
                "H_v",
            )
        }
        for e in events
    ]
    (OUT / "mm_quoting_events.json").write_text(json.dumps(jsonable(slim), indent=2))

    report = write_report(summary, decision, figs)
    risk = write_risk_report(summary, decision, paths, figs)
    nb = build_notebook(summary, decision)
    print(f"decision={decision['decision']} report={report} risk={risk} nb={nb}", flush=True)
    print(
        json.dumps(
            {
                **jsonable(decision),
                "honesty": honesty_block(),
                "metrics_path": str(OUT / "metrics.json"),
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
