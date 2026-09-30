#!/usr/bin/env python3
"""Exp 1 — Gated SSM kill-ladder backtest (observe→widen→size-cap→halt).

When ladder fires from rolling gated intensity + z* bands (σ_m floor + 10bps/ic5),
measure subsequent |ΔP|, tape markout, recovery class vs control / placebo.
Time-split + bootstrap; friction honesty (2bps one-way).

ClickHouse MCP banned.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    APP,
    FRICTION_BPS,
    OUT,
    assign_ladder_tiers,
    build_event_panel,
    early_late_by_day,
    effect_delta_ci,
    flatten_events,
    mean_ci,
    readiness_label,
    save_fig,
    save_json,
)

FIG = OUT / "kill_ladder" / "figs"
CH = APP / "kill_ladder"
TIERS = ("observe", "widen", "size_cap", "halt")


def _arr(evs: list[dict], key: str) -> np.ndarray:
    return np.asarray([e[key] for e in evs], dtype=np.float64)


def _tier_bundle(evs: list[dict], tier: str, controls: list[dict]) -> dict[str, Any]:
    t = [e for e in evs if e["tier"] == tier]
    c = controls
    if not t:
        return {"tier": tier, "n": 0}
    dp = _arr(t, "dp_pct")
    mo5 = _arr(t, "mo_5s")
    sub = _arr(t, "sub_dp_30s")
    rec = _arr(t, "recovery")
    labels = [e["recovery_label"] for e in t]
    share_v = float(np.mean([1.0 if x == "v_recovery" else 0.0 for x in labels])) if labels else float("nan")
    # adverse markout = continuation in crash direction (positive mo)
    adverse = mo5[np.isfinite(mo5)]
    # control: below-ladder gated events + placebo sub_dp
    c_mo = _arr(c, "mo_5s") if c else np.zeros(0)
    c_sub = _arr(c, "sub_dp_30s") if c else np.zeros(0)
    c_dp = _arr(c, "dp_pct") if c else np.zeros(0)
    d_mo = effect_delta_ci(mo5, c_mo, seed=11 + hash(tier) % 100)
    d_sub = effect_delta_ci(sub, c_sub, seed=21 + hash(tier) % 100)
    d_dp = effect_delta_ci(dp, c_dp, seed=31 + hash(tier) % 100)
    # friction: |Δ adverse mo| must exceed FRICTION to claim net value of halt
    # For halt/size_cap: we care that adverse (positive) mo is worse → rule avoids taking
    # Effect size for policy: mean |mo| treat vs control
    abs_mo_t = np.abs(mo5[np.isfinite(mo5)])
    abs_mo_c = np.abs(c_mo[np.isfinite(c_mo)]) if c_mo.size else np.zeros(0)
    d_abs = effect_delta_ci(abs_mo_t, abs_mo_c, seed=41)
    friction_cleared = bool(
        np.isfinite(d_abs["delta"]) and abs(d_abs["delta"]) > FRICTION_BPS and d_abs["lo"] > 0
    )
    return {
        "tier": tier,
        "n": len(t),
        "dp_pct": mean_ci(dp),
        "mo_5s": mean_ci(mo5),
        "sub_dp_30s": mean_ci(sub),
        "recovery_mean": mean_ci(rec),
        "share_v": share_v,
        "n_adverse_mo": int(np.sum(adverse > 0)) if adverse.size else 0,
        "frac_adverse_mo": float(np.mean(adverse > 0)) if adverse.size else float("nan"),
        "vs_control_mo5": d_mo,
        "vs_control_sub_dp": d_sub,
        "vs_control_dp": d_dp,
        "vs_control_abs_mo": d_abs,
        "friction_bps": FRICTION_BPS,
        "friction_cleared": friction_cleared,
    }


def run(force: bool = False) -> dict[str, Any]:
    panel = build_event_panel(force=force)
    rows = panel["rows"]
    evs = flatten_events(rows)
    breaks = assign_ladder_tiers(evs)
    early_days, late_days = early_late_by_day(panel["meta"]["days"])

    # controls = observe-tier isolated (intensity≤1); fallback all observe
    controls = [e for e in evs if e["tier"] == "observe" and int(e["intensity_60s"]) <= 1]
    if len(controls) < 15:
        controls = [e for e in evs if e["tier"] == "observe"]
    if len(controls) < 15:
        # placebo-as-control fallback: lowest quartile |mo| events labeled soft
        mos = np.asarray([abs(e["mo_5s"]) for e in evs if np.isfinite(e["mo_5s"])], dtype=np.float64)
        thr = float(np.nanpercentile(mos, 25)) if mos.size else 0.0
        controls = [e for e in evs if np.isfinite(e["mo_5s"]) and abs(e["mo_5s"]) <= thr]

    # placebo pool from rows
    pla_mo = []
    pla_sub = []
    pla_dp = []
    for r in rows:
        p = r.get("placebo") or {}
        pla_mo.extend(p.get("mo_5s") or [])
        pla_sub.extend(p.get("sub_dp") or [])
        pla_dp.extend(p.get("dp_pct") or [])
    placebo = {
        "mo_5s": mean_ci(np.asarray(pla_mo, dtype=np.float64)),
        "sub_dp": mean_ci(np.asarray(pla_sub, dtype=np.float64)),
        "dp_pct": mean_ci(np.asarray(pla_dp, dtype=np.float64)),
        "n": len(pla_mo),
    }

    by_tier = {t: _tier_bundle(evs, t, controls) for t in TIERS}
    # escalate set: widen+size_cap+halt
    fire = [e for e in evs if e["tier"] in ("widen", "size_cap", "halt")]
    fire_bundle = _tier_bundle(
        [{**e, "tier": "fire"} for e in fire],
        "fire",
        controls,
    )

    # intensity ladder: intensity>=3 as escalate regardless of z*
    high_int = [e for e in evs if int(e["intensity_60s"]) >= 3]
    low_int = [e for e in evs if int(e["intensity_60s"]) <= 1]
    int_effect = {
        "n_high": len(high_int),
        "n_low": len(low_int),
        "mo5": effect_delta_ci(_arr(high_int, "mo_5s"), _arr(low_int, "mo_5s"), seed=7),
        "sub_dp": effect_delta_ci(_arr(high_int, "sub_dp_30s"), _arr(low_int, "sub_dp_30s"), seed=8),
        "dp": effect_delta_ci(_arr(high_int, "dp_pct"), _arr(low_int, "dp_pct"), seed=9),
        "share_v_high": float(
            np.mean([1 if e["recovery_label"] == "v_recovery" else 0 for e in high_int])
        )
        if high_int
        else float("nan"),
        "share_v_low": float(
            np.mean([1 if e["recovery_label"] == "v_recovery" else 0 for e in low_int])
        )
        if low_int
        else float("nan"),
    }

    # time split on fire vs control abs mo
    early_f = [e for e in fire if e["day"] in early_days]
    late_f = [e for e in fire if e["day"] in late_days]
    early_c = [e for e in controls if e["day"] in early_days]
    late_c = [e for e in controls if e["day"] in late_days]
    ts_early = effect_delta_ci(_arr(early_f, "mo_5s"), _arr(early_c, "mo_5s"), seed=51)
    ts_late = effect_delta_ci(_arr(late_f, "mo_5s"), _arr(late_c, "mo_5s"), seed=52)
    # sign stability on |mo| elevation
    d_e = effect_delta_ci(
        np.abs(_arr(early_f, "mo_5s")), np.abs(_arr(early_c, "mo_5s")), seed=53
    )
    d_l = effect_delta_ci(
        np.abs(_arr(late_f, "mo_5s")), np.abs(_arr(late_c, "mo_5s")), seed=54
    )
    sign_stable = bool(
        np.isfinite(d_e["delta"])
        and np.isfinite(d_l["delta"])
        and np.sign(d_e["delta"]) == np.sign(d_l["delta"])
        and d_e["delta"] != 0
    )

    tier_counts = Counter(e["tier"] for e in evs)
    venue_tier = {}
    for v in ("hyperliquid", "deribit", "kraken"):
        ve = [e for e in evs if e["venue"] == v]
        venue_tier[v] = dict(Counter(e["tier"] for e in ve))

    fire_abs = effect_delta_ci(
        np.abs(_arr(fire, "mo_5s")),
        np.abs(_arr(controls, "mo_5s")),
        seed=60,
    )
    ci_excludes0 = bool(np.isfinite(fire_abs["lo"]) and fire_abs["lo"] > 0)
    friction_ok = bool(
        np.isfinite(fire_abs["delta"]) and fire_abs["delta"] > FRICTION_BPS and fire_abs["lo"] > 0
    )
    readiness = readiness_label(
        effect_ci_excludes_zero=ci_excludes0,
        time_split_sign_stable=sign_stable,
        n_events=len(fire),
        friction_cleared=friction_ok,
    )

    # false-positive cost: share of fire windows that are V-recovery (hole — halt may be overkill)
    fp_v = float(np.mean([1 if e["recovery_label"] == "v_recovery" else 0 for e in fire])) if fire else float("nan")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_gated_events": len(evs),
        "ladder_breaks": breaks,
        "tier_counts": dict(tier_counts),
        "venue_tier": venue_tier,
        "n_controls_observe_isolated": len(controls),
        "by_tier": by_tier,
        "fire_bundle": fire_bundle,
        "intensity_escalate": int_effect,
        "placebo": placebo,
        "time_split": {
            "early_days": sorted(early_days),
            "late_days": sorted(late_days),
            "fire_vs_ctrl_mo5_early": ts_early,
            "fire_vs_ctrl_mo5_late": ts_late,
            "abs_mo_delta_early": d_e,
            "abs_mo_delta_late": d_l,
            "sign_stable": sign_stable,
        },
        "policy": {
            "rule": "On widen/size_cap/halt: clip or halt aggressive takes on firing venue (venue-local).",
            "abs_mo_elevation_fire_vs_ctrl": fire_abs,
            "friction_bps": FRICTION_BPS,
            "friction_cleared": friction_ok,
            "false_positive_v_share_among_fire": fp_v,
            "readiness": readiness,
            "promote_as_risk_policy": readiness == "promote_as_risk_policy",
        },
        "cached_panel": panel.get("cached"),
    }

    # figures
    _figs(evs, controls, by_tier, summary)
    save_json(OUT / "kill_ladder" / "summary.json", summary)
    _write_report(summary)
    _write_notes()
    return summary


def _figs(evs, controls, by_tier, summary) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG.mkdir(parents=True, exist_ok=True)
    # 1) tier counts + mean |mo|
    tiers = list(TIERS)
    ns = [by_tier[t].get("n", 0) for t in tiers]
    mos = [
        abs(by_tier[t]["mo_5s"]["point"]) if by_tier[t].get("n") and by_tier[t].get("mo_5s") else 0
        for t in tiers
    ]
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.5))
    ax[0].bar(tiers, ns, color="#3d5a5b")
    ax[0].set_title("Gated events by z* ladder tier")
    ax[0].set_ylabel("n")
    ax[1].bar(tiers, mos, color="#c45c26")
    ax[1].set_title("Mean |tape mo @5s| (bps)")
    ax[1].axhline(FRICTION_BPS, color="k", ls="--", lw=0.8, label=f"friction {FRICTION_BPS}bps")
    ax[1].legend(fontsize=8)
    save_fig(FIG / "fig_ladder_tiers.png")

    # 2) intensity vs sub_dp
    intens = np.asarray([e["intensity_60s"] for e in evs], dtype=np.float64)
    sub = np.asarray([e["sub_dp_30s"] for e in evs], dtype=np.float64)
    fig, ax = plt.subplots(figsize=(5.5, 3.8))
    ax.scatter(intens, sub, s=12, alpha=0.45, c="#3d5a5b")
    ax.set_xlabel("Rolling gated intensity (60s)")
    ax.set_ylabel("Subsequent |ΔP| 30s (%)")
    ax.set_title("Intensity vs continuation severity")
    save_fig(FIG / "fig_intensity_vs_subdp.png")

    # 3) fire vs control / placebo mo distributions
    f_mo = np.asarray([e["mo_5s"] for e in evs if e["tier"] in ("widen", "size_cap", "halt")], dtype=np.float64)
    c_mo = np.asarray([e["mo_5s"] for e in controls], dtype=np.float64)
    fig, ax = plt.subplots(figsize=(5.5, 3.8))
    ax.hist(f_mo[np.isfinite(f_mo)], bins=30, alpha=0.55, label="fire tiers", color="#c45c26")
    ax.hist(c_mo[np.isfinite(c_mo)], bins=30, alpha=0.55, label="observe isolated", color="#3d5a5b")
    ax.axvline(0, color="k", lw=0.7)
    ax.set_xlabel("Tape markout @5s (bps, crash-signed)")
    ax.set_title("Fire vs control markout")
    ax.legend(fontsize=8)
    save_fig(FIG / "fig_fire_vs_control_mo.png")


def _write_report(s: dict[str, Any]) -> None:
    pol = s["policy"]
    fp = pol["false_positive_v_share_among_fire"]
    fp_line = (
        f"- V-share among fire (FP cost of halt): **{fp:.3f}**"
        if isinstance(fp, float) and np.isfinite(fp)
        else f"- V-share among fire: {fp}"
    )
    lines = [
        "# kill_ladder — EXP_REPORT",
        "",
        f"Generated: {s['generated_at']}",
        f"Script: `applications/scripts/exp_kill_ladder.py` · Out: `applications/out/kill_ladder/`",
        "",
        "## Setup",
        "",
        "- Gate: 10bps / i_c≥5; σ_m floor on; z*=6 base detection.",
        "- Ladder: within-gated z percentiles (p25/p50/p75) + intensity + Nanex nest.",
        f"- Breaks: `{s.get('ladder_breaks')}`",
        "- Outcomes: event |ΔP|, tape mo@5s, sub |ΔP|@30s, recovery class.",
        "- Control: observe-tier isolated (intensity≤1); placebo = random tape windows.",
        f"- Friction haircut: {FRICTION_BPS} bps one-way (no fantasy fills).",
        "",
        "## Counts",
        "",
        f"- n_gated = **{s['n_gated_events']}**; tiers = `{s['tier_counts']}`",
        f"- fire (widen+) n = **{s['fire_bundle'].get('n')}**; controls = {s['n_controls_observe_isolated']}",
        "",
        "## Effects (fire vs control)",
        "",
        f"- |mo|@5s Δ = **{pol['abs_mo_elevation_fire_vs_ctrl'].get('delta')}** "
        f"CI95 [{pol['abs_mo_elevation_fire_vs_ctrl'].get('lo')}, {pol['abs_mo_elevation_fire_vs_ctrl'].get('hi')}]",
        f"- Intensity≥3 vs ≤1 sub|ΔP| Δ = `{s['intensity_escalate']['sub_dp']}`",
        f"- Time-split |mo| Δ early/late sign stable: **{s['time_split']['sign_stable']}**",
        f"- Friction cleared (Δ|mo| > {FRICTION_BPS} & CI>0): **{pol['friction_cleared']}**",
        fp_line,
        "",
        "## Readiness",
        "",
        f"**{pol['readiness']}** — promote_as_risk_policy={pol['promote_as_risk_policy']}",
        "",
        "Monitor: **yes** (gated intensity + z* ladder). Executable aggressive-halt: "
        + (
            "**candidate** if friction+CI clear"
            if pol["friction_cleared"]
            else "**monitor / soft throttle only**"
        ),
        "",
        "## Figures",
        "",
        "- `figs/fig_ladder_tiers.png`",
        "- `figs/fig_intensity_vs_subdp.png`",
        "- `figs/fig_fire_vs_control_mo.png`",
        "",
    ]
    (CH / "EXP_REPORT.md").write_text("\n".join(lines) + "\n")
    (OUT / "kill_ladder" / "EXP_REPORT.md").write_text("\n".join(lines) + "\n")


def _write_notes() -> None:
    text = r"""# Gated SSM kill-ladder

**Track:** RISK · **Readiness target:** Promote-as-risk-policy (monitor→soft rule)  
**Objects:** `risk.ssm_severity_gate_10bps` · `risk.ssm_zstar_scan_table` · `vol.sigma_m_noise_floor_1bp`  
**Lib:** `research/lib/crash.py` · shared `applications/scripts/_common.py`

## Rule sketch

Detection: z*=6 + σ_m floor + 10bps/ic5 gate. Escalation uses **within-gated** z percentiles
(absolute {8,10,12} bands collapse on this tape — gated median |z|≈16).

| Tier | Trigger | Action |
|------|---------|--------|
| observe | |z| < p25, intensity=1, no Nanex | Log only |
| widen | p25≤|z|<p50 or intensity=2 or Nanex alone | Soft clip / widen |
| size_cap | p50≤|z| or intensity∈{3,4} | Cap aggressive size |
| halt | intensity≥5 or (Nanex∧intensity≥2) or |ΔP|≥p90 | Halt aggressive (venue-local) |

## Simulation design

1. Build event panel (HL+DB+KR × ETH/BTC × slice days).
2. Label each gated event with ladder tier.
3. Outcomes vs observe-isolated controls + placebo windows.
4. Early/late day split + bootstrap CI on Δ|mo|.
5. Friction: require Δ|mo| > 2bps with CI>0 before executable claim.

## Formulas

Rolling intensity for event \(i\):

\[
I_i(W) = \#\{j:\, t_j \in (t_i-W,\,t_i]\},\quad W=60\mathrm{s}.
\]

Crash-signed tape markout:

\[
\mathrm{mo}_h = d\cdot\frac{p_{t+h}-p_t}{p_t}\times 10^4\ \mathrm{bps}.
\]

## Honesty

- No mid fantasy fills; tape-only markout.
- Venue-local (concordance Hold).
- V-recovery share among fire = false-positive cost of hard halt.
"""
    (CH / "NOTES.md").write_text(text)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    s = run(force=args.force)
    print(json_summary(s))


def json_summary(s: dict[str, Any]) -> str:
    import json

    from _common import jsonable

    slim = {
        "n": s["n_gated_events"],
        "tiers": s["tier_counts"],
        "breaks": s.get("ladder_breaks"),
        "readiness": s["policy"]["readiness"],
        "abs_mo_delta": s["policy"]["abs_mo_elevation_fire_vs_ctrl"],
        "sign_stable": s["time_split"]["sign_stable"],
        "friction_cleared": s["policy"]["friction_cleared"],
    }
    return json.dumps(jsonable(slim), indent=2)


if __name__ == "__main__":
    main()
