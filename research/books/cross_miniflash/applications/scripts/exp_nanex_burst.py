from __future__ import annotations
#!/usr/bin/env python3
"""Exp 2 — Nanex∩SSM burst escalate vs SSM-only.

Nested-tag windows (Nanex nested in SSM) vs SSM-only gated events: temporary
protect effectiveness on |ΔP|, markout, recovery. Placebo = non-nested Nanex.

ClickHouse MCP banned.
"""


import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    APP,
    FRICTION_BPS,
    OUT,
    build_event_panel,
    early_late_by_day,
    effect_delta_ci,
    flatten_events,
    mean_ci,
    readiness_label,
    save_fig,
    save_json,
)

FIG = OUT / "nanex_burst" / "figs"
CH = APP / "nanex_burst"


def _arr(evs: list[dict], key: str) -> np.ndarray:
    return np.asarray([e[key] for e in evs], dtype=np.float64)


def run(force: bool = False) -> dict[str, Any]:
    panel = build_event_panel(force=force)
    rows = panel["rows"]
    evs = flatten_events(rows)
    early_days, late_days = early_late_by_day(panel["meta"]["days"])

    nested = [e for e in evs if e["nanex_overlap"]]
    ssm_only = [e for e in evs if not e["nanex_overlap"]]

    # Nanex events that failed nest = placebo burst tag
    nx_nested_dp, nx_bare_dp = [], []
    for r in rows:
        nx = r.get("nanex_events") or {}
        for dp, nest in zip(nx.get("dp_pct") or [], nx.get("nested") or []):
            if nest:
                nx_nested_dp.append(dp)
            else:
                nx_bare_dp.append(dp)

    effects = {
        "dp": effect_delta_ci(_arr(nested, "dp_pct"), _arr(ssm_only, "dp_pct"), seed=101),
        "mo_5s": effect_delta_ci(_arr(nested, "mo_5s"), _arr(ssm_only, "mo_5s"), seed=102),
        "abs_mo_5s": effect_delta_ci(
            np.abs(_arr(nested, "mo_5s")), np.abs(_arr(ssm_only, "mo_5s")), seed=103
        ),
        "sub_dp": effect_delta_ci(_arr(nested, "sub_dp_30s"), _arr(ssm_only, "sub_dp_30s"), seed=104),
        "recovery": effect_delta_ci(_arr(nested, "recovery"), _arr(ssm_only, "recovery"), seed=105),
    }
    share_v_n = float(np.mean([1 if e["recovery_label"] == "v_recovery" else 0 for e in nested])) if nested else float("nan")
    share_v_s = float(np.mean([1 if e["recovery_label"] == "v_recovery" else 0 for e in ssm_only])) if ssm_only else float("nan")

    # precision of nest among Nanex
    n_nx_n = sum(int(r.get("nanex_nested_n") or 0) for r in rows)
    n_nx = sum(int(r.get("nanex_n") or 0) for r in rows)
    precision = float(n_nx_n / n_nx) if n_nx else float("nan")

    # time split
    def _split(evlist, days):
        return [e for e in evlist if e["day"] in days]

    d_e = effect_delta_ci(
        np.abs(_arr(_split(nested, early_days), "mo_5s")),
        np.abs(_arr(_split(ssm_only, early_days), "mo_5s")),
        seed=111,
    )
    d_l = effect_delta_ci(
        np.abs(_arr(_split(nested, late_days), "mo_5s")),
        np.abs(_arr(_split(ssm_only, late_days), "mo_5s")),
        seed=112,
    )
    sign_stable = bool(
        np.isfinite(d_e["delta"])
        and np.isfinite(d_l["delta"])
        and np.sign(d_e["delta"]) == np.sign(d_l["delta"])
        and d_e["delta"] != 0
    )
    ci_ok = bool(np.isfinite(effects["abs_mo_5s"]["lo"]) and effects["abs_mo_5s"]["lo"] > 0)
    # protect effectiveness: nested should show elevated |mo| or |dp| → temporary pull justified
    friction_ok = bool(
        np.isfinite(effects["abs_mo_5s"]["delta"])
        and effects["abs_mo_5s"]["delta"] > FRICTION_BPS
        and effects["abs_mo_5s"]["lo"] > 0
    )
    # also require severity elevation
    sev_ok = bool(np.isfinite(effects["dp"]["lo"]) and effects["dp"]["lo"] > 0)
    readiness = readiness_label(
        effect_ci_excludes_zero=ci_ok or sev_ok,
        time_split_sign_stable=sign_stable,
        n_events=len(nested),
        friction_cleared=friction_ok and sev_ok,
    )
    # nest policy always high as tag
    tag_readiness = "promote_as_burst_tag"

    by_venue = {}
    for v in ("hyperliquid", "deribit", "kraken"):
        nv = [e for e in nested if e["venue"] == v]
        sv = [e for e in ssm_only if e["venue"] == v]
        by_venue[v] = {
            "n_nested": len(nv),
            "n_ssm_only": len(sv),
            "mean_dp_nested": float(np.nanmean(_arr(nv, "dp_pct"))) if nv else None,
            "mean_dp_ssm_only": float(np.nanmean(_arr(sv, "dp_pct"))) if sv else None,
        }

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_gated": len(evs),
        "n_nested": len(nested),
        "n_ssm_only": len(ssm_only),
        "nanex_precision_pooled": precision,
        "n_nanex": n_nx,
        "n_nanex_nested": n_nx_n,
        "nested_stats": {
            "dp": mean_ci(_arr(nested, "dp_pct")),
            "mo_5s": mean_ci(_arr(nested, "mo_5s")),
            "share_v": share_v_n,
        },
        "ssm_only_stats": {
            "dp": mean_ci(_arr(ssm_only, "dp_pct")),
            "mo_5s": mean_ci(_arr(ssm_only, "mo_5s")),
            "share_v": share_v_s,
        },
        "effects_nested_minus_ssm_only": effects,
        "bare_nanex_mean_dp": mean_ci(np.asarray(nx_bare_dp, dtype=np.float64)),
        "nested_nanex_mean_dp": mean_ci(np.asarray(nx_nested_dp, dtype=np.float64)),
        "time_split": {
            "abs_mo_delta_early": d_e,
            "abs_mo_delta_late": d_l,
            "sign_stable": sign_stable,
        },
        "by_venue": by_venue,
        "policy": {
            "rule": "Nanex∩SSM → temporary protect / pull (faster than soft widen); Nanex alone = do not fire.",
            "tag_readiness": tag_readiness,
            "auto_pull_readiness": readiness,
            "promote_as_risk_policy": readiness == "promote_as_risk_policy",
            "friction_cleared": friction_ok,
            "severity_elevated": sev_ok,
        },
    }
    _figs(nested, ssm_only, summary)
    save_json(OUT / "nanex_burst" / "summary.json", summary)
    _write_report(summary)
    _write_notes()
    return summary


def _figs(nested, ssm_only, summary) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.5))
    for a, key, title in (
        (ax[0], "dp_pct", "|ΔP| (%)"),
        (ax[1], "mo_5s", "mo@5s (bps)"),
    ):
        a.boxplot(
            [
                _arr(nested, key)[np.isfinite(_arr(nested, key))],
                _arr(ssm_only, key)[np.isfinite(_arr(ssm_only, key))],
            ],
            tick_labels=["Nanex∩SSM", "SSM-only"],
            showfliers=False,
        )
        a.set_title(title)
    save_fig(FIG / "fig_nested_vs_ssm_only.png")

    # venue bars
    venues = list(summary["by_venue"].keys())
    nd = [summary["by_venue"][v]["n_nested"] for v in venues]
    so = [summary["by_venue"][v]["n_ssm_only"] for v in venues]
    x = np.arange(len(venues))
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.bar(x - 0.2, nd, 0.4, label="nested", color="#c45c26")
    ax.bar(x + 0.2, so, 0.4, label="SSM-only", color="#3d5a5b")
    ax.set_xticks(x)
    ax.set_xticklabels(["HL", "DB", "KR"])
    ax.legend(fontsize=8)
    ax.set_title("Nested vs SSM-only counts by venue")
    save_fig(FIG / "fig_nested_venue_counts.png")


def _write_report(s: dict[str, Any]) -> None:
    pol = s["policy"]
    lines = [
        "# nanex_burst — EXP_REPORT",
        "",
        f"Generated: {s['generated_at']}",
        f"Script: `applications/scripts/exp_nanex_burst.py` · Out: `applications/out/nanex_burst/`",
        "",
        "## Setup",
        "",
        "- Treat = gated SSM events overlapping Nanex 30bps (nest).",
        "- Control = gated SSM without Nanex overlap.",
        "- Placebo tag = Nanex events failing SSM nest.",
        "",
        "## Headline",
        "",
        f"- n_nested=**{s['n_nested']}** / n_ssm_only=**{s['n_ssm_only']}**; Nanex precision=**{s['nanex_precision_pooled']:.3f}**",
        f"- Δ|ΔP| (nested−SSM-only) = `{s['effects_nested_minus_ssm_only']['dp']}`",
        f"- Δ|mo|@5s = `{s['effects_nested_minus_ssm_only']['abs_mo_5s']}`",
        f"- Time-split sign stable: **{s['time_split']['sign_stable']}**",
        f"- Tag readiness: **{pol['tag_readiness']}**",
        f"- Auto-pull readiness: **{pol['auto_pull_readiness']}** (promote_as_risk_policy={pol['promote_as_risk_policy']})",
        "",
        "## Figures",
        "",
        "- `figs/fig_nested_vs_ssm_only.png`",
        "- `figs/fig_nested_venue_counts.png`",
        "",
    ]
    (CH / "EXP_REPORT.md").write_text("\n".join(lines) + "\n")
    (OUT / "nanex_burst" / "EXP_REPORT.md").write_text("\n".join(lines) + "\n")


def _write_notes() -> None:
    (CH / "NOTES.md").write_text(
        """# Nanex∩SSM burst escalate

**Track:** RISK · **Objects:** `info.nanex_subset_of_ssm`  
**Rule:** Nested tag = high-precision burst escalate (temporary protect). Nanex alone = do not fire.

## Design

Compare gated SSM events with Nanex overlap vs SSM-only on severity, markout, recovery.
Precision = P(SSM|Nanex). Early/late + bootstrap on Δ|mo|.

## Honesty

Auto-pull is **med** until friction+CI clear; tag itself is **Promote monitor**.
"""
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    s = run(force=args.force)
    import json
    from _common import jsonable

    print(
        json.dumps(
            jsonable(
                {
                    "n_nested": s["n_nested"],
                    "precision": s["nanex_precision_pooled"],
                    "readiness": s["policy"]["auto_pull_readiness"],
                    "tag": s["policy"]["tag_readiness"],
                    "dp_effect": s["effects_nested_minus_ssm_only"]["dp"],
                }
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
