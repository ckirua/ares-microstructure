from __future__ import annotations
#!/usr/bin/env python3
"""Exp 3 — HL thin-excess + crash-share SOR / size-cap.

When HL excess co-fires with gated intensity, compare venue-local outcomes vs
Deribit/Kraken counterfactuals (no fantasy x-venue fill — same-clock severity /
markout on each venue's own tape).

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

FIG = OUT / "hl_thin_sor" / "figs"
CH = APP / "hl_thin_sor"


def _arr(evs: list[dict], key: str) -> np.ndarray:
    return np.asarray([e[key] for e in evs], dtype=np.float64)


def run(force: bool = False) -> dict[str, Any]:
    panel = build_event_panel(force=force)
    rows = panel["rows"]
    evs = flatten_events(rows)
    early_days, late_days = early_late_by_day(panel["meta"]["days"])

    hl = [e for e in evs if e["venue"] == "hyperliquid"]
    db = [e for e in evs if e["venue"] == "deribit"]
    kr = [e for e in evs if e["venue"] == "kraken"]
    thick = db + kr

    # co-fire: HL event with intensity>=2 OR excess day (from cell) elevated
    # use cell thin_excess from row join
    hl_cell_excess = {}
    for r in rows:
        if r.get("venue") == "hyperliquid" and "excess" in r:
            hl_cell_excess[(r["day"], r["symbol"])] = r.get("excess")

    def _cof(e):
        ex = hl_cell_excess.get((e["day"], e["symbol"]))
        return e["venue"] == "hyperliquid" and (
            int(e["intensity_60s"]) >= 2 or (ex is not None and np.isfinite(ex) and ex > 0.5)
        )

    hl_fire = [e for e in hl if _cof(e)]
    hl_quiet = [e for e in hl if not _cof(e)]

    # venue-local outcome comparison (not matched fills — honesty)
    venue_outcomes = {}
    for name, group in (("hyperliquid", hl), ("deribit", db), ("kraken", kr), ("thick", thick)):
        venue_outcomes[name] = {
            "n": len(group),
            "dp": mean_ci(_arr(group, "dp_pct")),
            "mo_5s": mean_ci(_arr(group, "mo_5s")),
            "abs_mo_5s": mean_ci(np.abs(_arr(group, "mo_5s"))),
            "sub_dp": mean_ci(_arr(group, "sub_dp_30s")),
            "share_v": float(
                np.mean([1 if e["recovery_label"] == "v_recovery" else 0 for e in group])
            )
            if group
            else float("nan"),
        }

    # HL fire vs thick-venue events (same slice, not same timestamp — concordance Hold)
    cmp_fire_thick = {
        "dp": effect_delta_ci(_arr(hl_fire, "dp_pct"), _arr(thick, "dp_pct"), seed=201),
        "abs_mo": effect_delta_ci(
            np.abs(_arr(hl_fire, "mo_5s")), np.abs(_arr(thick, "mo_5s")), seed=202
        ),
        "sub_dp": effect_delta_ci(_arr(hl_fire, "sub_dp_30s"), _arr(thick, "sub_dp_30s"), seed=203),
    }
    cmp_hl_thick = {
        "dp": effect_delta_ci(_arr(hl, "dp_pct"), _arr(thick, "dp_pct"), seed=211),
        "abs_mo": effect_delta_ci(np.abs(_arr(hl, "mo_5s")), np.abs(_arr(thick, "mo_5s")), seed=212),
    }
    cmp_fire_quiet = {
        "dp": effect_delta_ci(_arr(hl_fire, "dp_pct"), _arr(hl_quiet, "dp_pct"), seed=221),
        "abs_mo": effect_delta_ci(
            np.abs(_arr(hl_fire, "mo_5s")), np.abs(_arr(hl_quiet, "mo_5s")), seed=222
        ),
    }

    # size-cap simulation: if we clip HL aggressive in fire windows, "saved" adverse =
    # mean abs mo on HL fire − thick abs mo (routing counterfactual upper bound)
    # honesty: this is NOT a fill — it's venue-local severity differential
    saved = cmp_fire_thick["abs_mo"]
    friction_ok = bool(
        np.isfinite(saved.get("delta")) and saved["delta"] > FRICTION_BPS and saved.get("lo", -1) > 0
    )

    # day-level thin excess distribution
    excess_vals = []
    for (d, s), ex in hl_cell_excess.items():
        if ex is not None and np.isfinite(ex):
            excess_vals.append({"day": d, "symbol": s, "thin_excess": ex})

    # crash share pooled
    crash_n = {v: len([e for e in evs if e["venue"] == v]) for v in ("hyperliquid", "deribit", "kraken")}
    tot = sum(crash_n.values()) or 1
    crash_share = {v: crash_n[v] / tot for v in crash_n}

    # time split HL fire vs thick
    def _d(evlist, days):
        return [e for e in evlist if e["day"] in days]

    d_e = effect_delta_ci(
        np.abs(_arr(_d(hl_fire, early_days), "mo_5s")),
        np.abs(_arr(_d(thick, early_days), "mo_5s")),
        seed=231,
    )
    d_l = effect_delta_ci(
        np.abs(_arr(_d(hl_fire, late_days), "mo_5s")),
        np.abs(_arr(_d(thick, late_days), "mo_5s")),
        seed=232,
    )
    sign_stable = bool(
        np.isfinite(d_e["delta"])
        and np.isfinite(d_l["delta"])
        and np.sign(d_e["delta"]) == np.sign(d_l["delta"])
        and d_e["delta"] != 0
    )
    ci_ok = bool(np.isfinite(saved.get("lo")) and saved["lo"] > 0)
    readiness = readiness_label(
        effect_ci_excludes_zero=ci_ok,
        time_split_sign_stable=sign_stable,
        n_events=len(hl_fire),
        friction_cleared=friction_ok,
    )

    # SOR schedule sketch: size multiplier on HL
    # fire → 0.25×; quiet HL → 0.75×; thick always 1.0× (monitor schedule)
    sor_schedule = {
        "hl_fire_size_mult": 0.25,
        "hl_quiet_size_mult": 0.75,
        "thick_size_mult": 1.0,
        "note": "Multipliers are policy sketches keyed to observed severity differential — not calibrated POV fills.",
    }

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "crash_share_gated": crash_share,
        "crash_counts": crash_n,
        "n_hl_fire": len(hl_fire),
        "n_hl_quiet": len(hl_quiet),
        "n_thick": len(thick),
        "thin_excess_cells": excess_vals,
        "thin_excess_mean": mean_ci(np.asarray([x["thin_excess"] for x in excess_vals], dtype=np.float64)),
        "venue_outcomes": venue_outcomes,
        "hl_fire_vs_thick": cmp_fire_thick,
        "hl_all_vs_thick": cmp_hl_thick,
        "hl_fire_vs_quiet": cmp_fire_quiet,
        "time_split": {"early": d_e, "late": d_l, "sign_stable": sign_stable},
        "sor_schedule": sor_schedule,
        "policy": {
            "rule": "When HL thin excess elevated AND gated intensity co-fires → cap HL aggressive / prefer DB+KR (venue-local).",
            "do_not": "Wait for x-venue crash confirm (concordance Hold).",
            "severity_differential_bps_proxy": saved,
            "friction_cleared": friction_ok,
            "readiness": readiness,
            "promote_as_risk_policy": readiness == "promote_as_risk_policy",
            "monitor_readiness": "promote_monitor",
        },
    }
    _figs(summary, hl_fire, hl_quiet, thick)
    save_json(OUT / "hl_thin_sor" / "summary.json", summary)
    _write_report(summary)
    _write_notes()
    return summary


def _figs(summary, hl_fire, hl_quiet, thick) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG.mkdir(parents=True, exist_ok=True)
    vo = summary["venue_outcomes"]
    names = ["hyperliquid", "deribit", "kraken"]
    labels = ["HL", "DB", "KR"]
    dps = [vo[n]["dp"]["point"] if vo[n]["n"] else 0 for n in names]
    mos = [vo[n]["abs_mo_5s"]["point"] if vo[n]["n"] else 0 for n in names]
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.5))
    ax[0].bar(labels, dps, color=["#c45c26", "#3d5a5b", "#6b8f71"])
    ax[0].set_title("Mean gated |ΔP| by venue (%)")
    ax[1].bar(labels, mos, color=["#c45c26", "#3d5a5b", "#6b8f71"])
    ax[1].set_title("Mean |mo|@5s by venue (bps)")
    ax[1].axhline(FRICTION_BPS, color="k", ls="--", lw=0.8)
    save_fig(FIG / "fig_venue_severity.png")

    fig, ax = plt.subplots(figsize=(5.5, 3.8))
    shares = summary["crash_share_gated"]
    ax.bar(
        ["HL crash", "DB", "KR"],
        [shares["hyperliquid"], shares["deribit"], shares["kraken"]],
        color=["#c45c26", "#3d5a5b", "#6b8f71"],
    )
    ax.set_ylim(0, 1)
    ax.set_title("Gated crash venue share")
    save_fig(FIG / "fig_crash_share.png")

    fig, ax = plt.subplots(figsize=(5.5, 3.8))
    ax.boxplot(
        [
            np.abs(_arr(hl_fire, "mo_5s"))[np.isfinite(_arr(hl_fire, "mo_5s"))],
            np.abs(_arr(hl_quiet, "mo_5s"))[np.isfinite(_arr(hl_quiet, "mo_5s"))],
            np.abs(_arr(thick, "mo_5s"))[np.isfinite(_arr(thick, "mo_5s"))],
        ],
        tick_labels=["HL fire", "HL quiet", "DB+KR"],
        showfliers=False,
    )
    ax.set_ylabel("|mo|@5s (bps)")
    ax.set_title("HL co-fire vs quiet vs thick")
    save_fig(FIG / "fig_hl_fire_vs_thick.png")


def _write_report(s: dict[str, Any]) -> None:
    pol = s["policy"]
    lines = [
        "# hl_thin_sor — EXP_REPORT",
        "",
        f"Generated: {s['generated_at']}",
        f"Script: `applications/scripts/exp_hl_thin_sor.py` · Out: `applications/out/hl_thin_sor/`",
        "",
        "## Setup",
        "",
        "- Co-fire: HL gated event with intensity≥2 or day thin_excess>0.5.",
        "- Counterfactual: Deribit+Kraken gated outcomes on same slice (venue-local; not matched fills).",
        "- Concordance Hold → do not assume simultaneous crash.",
        "",
        "## Headline",
        "",
        f"- Crash share: `{s['crash_share_gated']}`",
        f"- Thin excess mean: `{s['thin_excess_mean']}`",
        f"- n HL fire / quiet / thick = {s['n_hl_fire']} / {s['n_hl_quiet']} / {s['n_thick']}",
        f"- HL fire − thick Δ|mo| = `{s['hl_fire_vs_thick']['abs_mo']}`",
        f"- Time-split stable: **{s['time_split']['sign_stable']}**",
        f"- SOR size mult sketch: `{s['sor_schedule']}`",
        f"- Readiness: **{pol['readiness']}** (monitor={pol['monitor_readiness']}; promote_policy={pol['promote_as_risk_policy']})",
        "",
        "## Figures",
        "",
        "- `figs/fig_venue_severity.png`",
        "- `figs/fig_crash_share.png`",
        "- `figs/fig_hl_fire_vs_thick.png`",
        "",
    ]
    (CH / "EXP_REPORT.md").write_text("\n".join(lines) + "\n")
    (OUT / "hl_thin_sor" / "EXP_REPORT.md").write_text("\n".join(lines) + "\n")


def _write_notes() -> None:
    (CH / "NOTES.md").write_text(
        """# HL thin-excess + crash-share SOR / size-cap

**Track:** EXEC/SOR · **Objects:** `frag.thin_venue_crash_excess` · `frag.crash_venue_share`

## Rule sketch

When HL thin excess elevated **and** gated SSM intensity rises → cap HL inventory / aggressive takes;
prefer Deribit/Kraken. Always show HL crash share vs vol share on SOR risk strip.

## Counterfactual honesty

No fantasy cross-venue fills. Compare **venue-local** gated severity/markout on HL vs thick legs
on the same day×symbol panel. Concordance placebo fails → kill-switches stay venue-local.

## Size schedule (sketch)

| Regime | HL size mult | Thick mult |
|--------|-------------:|-----------:|
| HL co-fire | 0.25 | 1.0 |
| HL quiet | 0.75 | 1.0 |
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
                    "crash_share": s["crash_share_gated"],
                    "n_hl_fire": s["n_hl_fire"],
                    "delta_abs_mo": s["hl_fire_vs_thick"]["abs_mo"],
                    "readiness": s["policy"]["readiness"],
                }
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
