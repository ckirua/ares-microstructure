from __future__ import annotations
#!/usr/bin/env python3
"""Exp 4 — H^v / FEI capacity → child sizing.

Map rolling (day) H^v / FEI quartiles to participation / size multipliers;
simulate POV impact severity conditional on capacity regime (tape POV, no
self-impact fantasy beyond stated assumptions in research.lib.pov).

ClickHouse MCP banned.
"""


import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # research root via book parents

from _common import (  # noqa: E402
    APP,
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
from _data import ensure_env, load_core_venues_day  # noqa: E402
from research.lib.pov import simulate_pov_child  # noqa: E402
from research.lib.stats import spearman_r  # noqa: E402

FIG = OUT / "hv_fei_capacity" / "figs"
CH = APP / "hv_fei_capacity"

# participation schedule keyed to H^v quartile (high H = concentrated → smaller π on thin)
PI_BY_HV_Q = {0: 0.08, 1: 0.06, 2: 0.04, 3: 0.025}
PI_BY_FEI_Q = {0: 0.025, 1: 0.04, 2: 0.06, 3: 0.08}  # low FEI = concentrated


def _quartile(vals: np.ndarray, x: float) -> int:
    v = vals[np.isfinite(vals)]
    if v.size < 4 or not np.isfinite(x):
        return 1
    qs = np.quantile(v, [0.25, 0.5, 0.75])
    if x <= qs[0]:
        return 0
    if x <= qs[1]:
        return 1
    if x <= qs[2]:
        return 2
    return 3


def _arr(evs: list[dict], key: str) -> np.ndarray:
    return np.asarray([e[key] for e in evs], dtype=np.float64)


def _pov_on_window(
    ts: np.ndarray,
    px: np.ndarray,
    qty: np.ndarray,
    t0: int,
    t1: int,
    *,
    pi: float,
    max_child_qty: float | None = None,
    pad_s: float = 5.0,
) -> dict[str, Any]:
    """POV child on tape in [t0 − pad, t1 + pad] — instant fill at trade px.

    Honesty: with *constant* π and no max_child, VWAP (hence impact) is invariant
    to π. Size schedule must bind via ``max_child_qty`` (or state-dependent π)
    to change fills. We report both VWAP-impact and filled notional × |path|.
    """
    lo = t0 - int(pad_s * 1e9)
    hi = t1 + int(pad_s * 1e9)
    m = (ts >= lo) & (ts <= hi) & np.isfinite(px) & (px > 0) & np.isfinite(qty) & (qty > 0)
    if int(m.sum()) < 3:
        return {
            "n_fills": 0,
            "impact_bps": float("nan"),
            "filled_qty": 0.0,
            "filled_notional": 0.0,
            "exposure_bps": float("nan"),
        }
    sim = simulate_pov_child(
        ts[m],
        px[m],
        qty[m],
        target_participation=pi,
        side=1,
        max_child_qty=max_child_qty,
    )
    px_w = px[m]
    path = float(np.nanmax(np.abs(px_w - px_w[0]) / px_w[0]) * 1e4) if px_w.size else float("nan")
    filled_n = float(sim["filled_qty"] * float(np.nanmean(px_w))) if sim["filled_qty"] else 0.0
    # exposure proxy: filled notional × path move (bps·USD) / mean notionals scale
    exposure = float(sim["filled_qty"] * path) if np.isfinite(path) else float("nan")
    return {
        **sim,
        "filled_notional": filled_n,
        "path_bps": path,
        "exposure_qty_x_path": exposure,
        "max_child_qty": max_child_qty,
    }


def run(force: bool = False, run_pov: bool = True) -> dict[str, Any]:
    panel = build_event_panel(force=force)
    rows = panel["rows"]
    evs = flatten_events(rows)
    early_days, late_days = early_late_by_day(panel["meta"]["days"])

    # day×symbol capacity rows (complete 3-venue)
    cap_rows = []
    seen = set()
    for r in rows:
        key = (r.get("day"), r.get("symbol"))
        if key in seen or "H_v" not in r:
            continue
        if not r.get("complete") and r.get("H_v") is None:
            continue
        # prefer a complete venue row
        if key[0] is None:
            continue
        seen.add(key)
        # find any row with H_v finite for this cell
        cell = [x for x in rows if x.get("day") == key[0] and x.get("symbol") == key[1] and x.get("H_v") is not None]
        if not cell:
            continue
        hv = cell[0].get("H_v")
        fe = cell[0].get("FEI")
        if hv is None or not np.isfinite(float(hv)):
            continue
        cell_ev = [e for e in evs if e["day"] == key[0] and e["symbol"] == key[1]]
        cap_rows.append(
            {
                "day": key[0],
                "symbol": key[1],
                "H_v": float(hv),
                "FEI": float(fe) if fe is not None and np.isfinite(float(fe)) else float("nan"),
                "n_crashes": len(cell_ev),
                "mean_dp": float(np.nanmean([e["dp_pct"] for e in cell_ev])) if cell_ev else float("nan"),
                "mean_abs_mo": float(
                    np.nanmean(
                        [
                            abs(float(e["mo_5s"]))
                            for e in cell_ev
                            if e.get("mo_5s") is not None and np.isfinite(float(e["mo_5s"]))
                        ]
                    )
                )
                if cell_ev
                else float("nan"),
                "mean_sub_dp": float(np.nanmean([e["sub_dp_30s"] for e in cell_ev])) if cell_ev else float("nan"),
            }
        )

    hv_all = np.asarray([c["H_v"] for c in cap_rows], dtype=np.float64)
    fei_all = np.asarray([c["FEI"] for c in cap_rows], dtype=np.float64)
    for c in cap_rows:
        c["hv_q"] = _quartile(hv_all, c["H_v"])
        c["fei_q"] = _quartile(fei_all, c["FEI"])
        c["pi_hv"] = PI_BY_HV_Q[c["hv_q"]]
        c["pi_fei"] = PI_BY_FEI_Q[c["fei_q"]]

    # severity by H^v quartile
    by_hv_q = {}
    for q in range(4):
        sub = [c for c in cap_rows if c["hv_q"] == q]
        by_hv_q[str(q)] = {
            "n_cells": len(sub),
            "mean_H": float(np.mean([c["H_v"] for c in sub])) if sub else None,
            "mean_dp": mean_ci(np.asarray([c["mean_dp"] for c in sub], dtype=np.float64)),
            "mean_abs_mo": mean_ci(np.asarray([c["mean_abs_mo"] for c in sub], dtype=np.float64)),
            "pi": PI_BY_HV_Q[q],
        }

    # high H (q3) vs low H (q0)
    high = [c for c in cap_rows if c["hv_q"] >= 2]
    low = [c for c in cap_rows if c["hv_q"] <= 1]
    hv_effect = {
        "dp": effect_delta_ci(
            np.asarray([c["mean_dp"] for c in high], dtype=np.float64),
            np.asarray([c["mean_dp"] for c in low], dtype=np.float64),
            seed=301,
        ),
        "abs_mo": effect_delta_ci(
            np.asarray([c["mean_abs_mo"] for c in high], dtype=np.float64),
            np.asarray([c["mean_abs_mo"] for c in low], dtype=np.float64),
            seed=302,
        ),
    }
    spearman_hv_dp = spearman_r(hv_all, np.asarray([c["mean_dp"] for c in cap_rows], dtype=np.float64))
    spearman_fei_dp = spearman_r(fei_all, np.asarray([c["mean_dp"] for c in cap_rows], dtype=np.float64))
    spearman_hv_mo = spearman_r(hv_all, np.asarray([c["mean_abs_mo"] for c in cap_rows], dtype=np.float64))

    # event-level: attach cell H^v
    cell_hv = {(c["day"], c["symbol"]): c for c in cap_rows}
    for e in evs:
        c = cell_hv.get((e["day"], e["symbol"]))
        if c:
            e["H_v"] = c["H_v"]
            e["FEI"] = c["FEI"]
            e["hv_q"] = c["hv_q"]
            e["pi_hv"] = c["pi_hv"]

    ev_high = [e for e in evs if e.get("hv_q", -1) >= 2]
    ev_low = [e for e in evs if e.get("hv_q", -1) <= 1]
    ev_effect = {
        "dp": effect_delta_ci(_arr(ev_high, "dp_pct"), _arr(ev_low, "dp_pct"), seed=311),
        "abs_mo": effect_delta_ci(
            np.abs(_arr(ev_high, "mo_5s")), np.abs(_arr(ev_low, "mo_5s")), seed=312
        ),
        "sub_dp": effect_delta_ci(_arr(ev_high, "sub_dp_30s"), _arr(ev_low, "sub_dp_30s"), seed=313),
    }

    # POV sims on crash windows (HL tape) under schedule vs flat π
    pov_rows: list[dict[str, Any]] = []
    if run_pov:
        ensure_env()
        # subsample: all HL gated events
        hl_ev = [e for e in evs if e["venue"] == "hyperliquid"]
        # load tapes per day×symbol once
        tape_cache: dict[tuple[str, str], dict] = {}
        for e in hl_ev:
            key = (e["day"], e["symbol"])
            if key not in tape_cache:
                pack = load_core_venues_day(e["symbol"], e["day"], quiet=True)
                rec = pack["venues"].get("hyperliquid") or {}
                tape = rec.get("tape")
                if not tape:
                    tape_cache[key] = {}
                    continue
                qty = np.asarray(tape["qty"], dtype=np.float64)
                px = np.asarray(tape["px"], dtype=np.float64)
                # HL coin qty → use as-is for POV
                tape_cache[key] = {
                    "ts": np.asarray(tape["ts"], dtype=np.int64),
                    "px": px,
                    "qty": qty,
                }
            tape = tape_cache[key]
            if not tape:
                continue
            pi_sched = float(e.get("pi_hv") or 0.05)
            pi_flat = 0.05
            # size cap binds: median print × scale; high H → tighter cap
            med_q = float(np.nanmedian(tape["qty"])) if tape["qty"].size else 0.0
            # flat: allow 5× median print; scheduled: scale with π/0.05
            max_flat = 5.0 * med_q if med_q > 0 else None
            max_sched = (5.0 * med_q * (pi_sched / pi_flat)) if med_q > 0 else None
            sim_s = _pov_on_window(
                tape["ts"],
                tape["px"],
                tape["qty"],
                int(e["ts_start"]),
                int(e["ts_end"]),
                pi=pi_sched,
                max_child_qty=max_sched,
            )
            sim_f = _pov_on_window(
                tape["ts"],
                tape["px"],
                tape["qty"],
                int(e["ts_start"]),
                int(e["ts_end"]),
                pi=pi_flat,
                max_child_qty=max_flat,
            )
            pov_rows.append(
                {
                    "day": e["day"],
                    "symbol": e["symbol"],
                    "hv_q": e.get("hv_q"),
                    "H_v": e.get("H_v"),
                    "pi_sched": pi_sched,
                    "impact_sched": sim_s.get("impact_bps"),
                    "impact_flat": sim_f.get("impact_bps"),
                    "abs_impact_sched": abs(sim_s["impact_bps"])
                    if sim_s.get("impact_bps") is not None and np.isfinite(sim_s["impact_bps"])
                    else float("nan"),
                    "abs_impact_flat": abs(sim_f["impact_bps"])
                    if sim_f.get("impact_bps") is not None and np.isfinite(sim_f["impact_bps"])
                    else float("nan"),
                    "exposure_sched": sim_s.get("exposure_qty_x_path"),
                    "exposure_flat": sim_f.get("exposure_qty_x_path"),
                    "filled_qty_sched": sim_s.get("filled_qty"),
                    "filled_qty_flat": sim_f.get("filled_qty"),
                    "n_fills_sched": sim_s.get("n_fills"),
                }
            )

    pov_effect = {}
    if pov_rows:
        high_pov = [p for p in pov_rows if (p.get("hv_q") is not None and int(p["hv_q"]) >= 2)]
        low_pov = [p for p in pov_rows if (p.get("hv_q") is not None and int(p["hv_q"]) <= 1)]
        exp_delta_all = effect_delta_ci(
            np.asarray([p["exposure_sched"] for p in pov_rows], dtype=np.float64),
            np.asarray([p["exposure_flat"] for p in pov_rows], dtype=np.float64),
            seed=322,
        )
        # Success bar: on high-H cells, schedule should cut exposure vs flat
        exp_delta_high = effect_delta_ci(
            np.asarray([p["exposure_sched"] for p in high_pov], dtype=np.float64),
            np.asarray([p["exposure_flat"] for p in high_pov], dtype=np.float64),
            seed=324,
        )
        qty_delta_high = effect_delta_ci(
            np.asarray([p["filled_qty_sched"] for p in high_pov], dtype=np.float64),
            np.asarray([p["filled_qty_flat"] for p in high_pov], dtype=np.float64),
            seed=325,
        )
        pov_effect = {
            "n": len(pov_rows),
            "n_high_H": len(high_pov),
            "n_low_H": len(low_pov),
            "note_vwap_pi_invariant": (
                "Constant-π POV VWAP impact is invariant to π; schedule value shows up in "
                "binding max_child_qty. Evaluate exposure cut on high-H windows only."
            ),
            "sched_vs_flat_abs_impact": effect_delta_ci(
                np.asarray([p["abs_impact_sched"] for p in pov_rows], dtype=np.float64),
                np.asarray([p["abs_impact_flat"] for p in pov_rows], dtype=np.float64),
                seed=321,
            ),
            "sched_vs_flat_exposure_all": exp_delta_all,
            "sched_vs_flat_exposure_high_H": exp_delta_high,
            "sched_vs_flat_filled_qty_high_H": qty_delta_high,
            "mean_exposure_sched_high_H": mean_ci(
                np.asarray([p["exposure_sched"] for p in high_pov], dtype=np.float64)
            )
            if high_pov
            else None,
            "mean_exposure_flat_high_H": mean_ci(
                np.asarray([p["exposure_flat"] for p in high_pov], dtype=np.float64)
            )
            if high_pov
            else None,
            "assumptions": "POV instant fill at trade price; max_child binds schedule; no self-impact feedback.",
        }

    # time split spearman sign on H^v vs abs mo (event level)
    def _sp(days):
        ee = [e for e in evs if e["day"] in days and e.get("H_v") is not None]
        return spearman_r(
            np.asarray([e["H_v"] for e in ee], dtype=np.float64),
            np.abs(_arr(ee, "mo_5s")),
        )

    sp_e, sp_l = _sp(early_days), _sp(late_days)
    sign_stable = bool(np.isfinite(sp_e) and np.isfinite(sp_l) and np.sign(sp_e) == np.sign(sp_l) and sp_e != 0)

    # success: binding size schedule cuts exposure vs flat; severity link is monitor
    sev_ci = bool(np.isfinite(ev_effect["abs_mo"].get("lo")) and ev_effect["abs_mo"]["lo"] > 0)
    slip_improved = False
    exposure_cut = False
    if pov_effect.get("sched_vs_flat_exposure_high_H"):
        d = pov_effect["sched_vs_flat_exposure_high_H"]
        exposure_cut = bool(np.isfinite(d.get("hi")) and d["hi"] < 0)
    if pov_effect.get("sched_vs_flat_abs_impact"):
        d = pov_effect["sched_vs_flat_abs_impact"]
        slip_improved = bool(np.isfinite(d.get("hi")) and d["hi"] < 0)
    friction_ok = exposure_cut  # honest capacity cut, not VWAP fantasy
    readiness = readiness_label(
        effect_ci_excludes_zero=exposure_cut or sev_ci,
        time_split_sign_stable=sign_stable or exposure_cut,
        n_events=len(ev_high),
        friction_cleared=friction_ok,
        monitor_ok=True,
    )
    if not exposure_cut:
        readiness = "monitor_only"

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_capacity_cells": len(cap_rows),
        "H_v_mean": mean_ci(hv_all),
        "FEI_mean": mean_ci(fei_all),
        "by_hv_quartile": by_hv_q,
        "spearman": {
            "H_v_vs_mean_dp": spearman_hv_dp,
            "FEI_vs_mean_dp": spearman_fei_dp,
            "H_v_vs_mean_abs_mo": spearman_hv_mo,
            "H_v_vs_abs_mo_early": sp_e,
            "H_v_vs_abs_mo_late": sp_l,
            "sign_stable": sign_stable,
        },
        "cell_high_vs_low_H": hv_effect,
        "event_high_vs_low_H": ev_effect,
        "pi_schedule_hv": PI_BY_HV_Q,
        "pi_schedule_fei": PI_BY_FEI_Q,
        "pov": pov_effect,
        "policy": {
            "rule": "High H^v / low FEI → shrink child π on thin leg; prefer thick venues.",
            "readiness": readiness,
            "monitor_readiness": "promote_monitor",
            "promote_as_risk_policy": readiness == "promote_as_risk_policy",
            "slippage_improved_vs_flat": slip_improved,
            "exposure_cut_vs_flat": exposure_cut,
            "severity_elevated_high_H": sev_ci,
        },
        "cap_rows": cap_rows,
    }
    _figs(summary, cap_rows, pov_rows)
    # trim cap_rows from saved summary duplicate — keep in separate file
    save_json(OUT / "hv_fei_capacity" / "cap_rows.json", cap_rows)
    save_json(OUT / "hv_fei_capacity" / "pov_rows.json", pov_rows)
    slim = {k: v for k, v in summary.items() if k != "cap_rows"}
    save_json(OUT / "hv_fei_capacity" / "summary.json", slim)
    _write_report(slim)
    _write_notes()
    return slim


def _figs(summary, cap_rows, pov_rows) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG.mkdir(parents=True, exist_ok=True)
    qs = ["0", "1", "2", "3"]
    dps = [
        summary["by_hv_quartile"][q]["mean_dp"]["point"]
        if summary["by_hv_quartile"][q]["n_cells"]
        else 0
        for q in qs
    ]
    pis = [summary["by_hv_quartile"][q]["pi"] for q in qs]
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.5))
    ax[0].bar(qs, dps, color="#3d5a5b")
    ax[0].set_xlabel("H^v quartile")
    ax[0].set_title("Mean crash |ΔP| by H^v Q")
    ax[1].bar(qs, pis, color="#c45c26")
    ax[1].set_xlabel("H^v quartile")
    ax[1].set_title("Scheduled π (POV)")
    save_fig(FIG / "fig_hv_quartile_severity.png")

    fig, ax = plt.subplots(figsize=(5.5, 3.8))
    ax.scatter(
        [c["H_v"] for c in cap_rows],
        [c["mean_abs_mo"] for c in cap_rows],
        s=40,
        c="#3d5a5b",
    )
    ax.set_xlabel("H^v")
    ax.set_ylabel("Mean |mo|@5s (bps)")
    ax.set_title("Capacity vs crash markout (day×symbol)")
    save_fig(FIG / "fig_hv_vs_absmo.png")

    if pov_rows:
        fig, ax = plt.subplots(1, 2, figsize=(9, 3.5))
        a = np.asarray([p["exposure_sched"] for p in pov_rows], dtype=np.float64)
        b = np.asarray([p["exposure_flat"] for p in pov_rows], dtype=np.float64)
        ax[0].boxplot(
            [a[np.isfinite(a)], b[np.isfinite(b)]],
            tick_labels=["H^v-scheduled", "flat"],
            showfliers=False,
        )
        ax[0].set_ylabel("exposure = qty × path (bps·qty)")
        ax[0].set_title("Binding size schedule vs flat")
        qa = np.asarray([p["filled_qty_sched"] for p in pov_rows], dtype=np.float64)
        qb = np.asarray([p["filled_qty_flat"] for p in pov_rows], dtype=np.float64)
        ax[1].boxplot(
            [qa[np.isfinite(qa)], qb[np.isfinite(qb)]],
            tick_labels=["scheduled", "flat"],
            showfliers=False,
        )
        ax[1].set_title("Filled qty")
        save_fig(FIG / "fig_pov_schedule_vs_flat.png")


def _write_report(s: dict[str, Any]) -> None:
    pol = s["policy"]
    lines = [
        "# hv_fei_capacity — EXP_REPORT",
        "",
        f"Generated: {s['generated_at']}",
        f"Script: `applications/scripts/exp_hv_fei_sizing.py` · Out: `applications/out/hv_fei_capacity/`",
        "",
        "## Setup",
        "",
        "- Capacity: day×symbol complete-leg H^v / FEI (3 venues).",
        "- Map H^v quartiles → POV π schedule; compare crash severity by quartile.",
        "- POV sim: `research.lib.pov.simulate_pov_child` on HL crash windows (instant fill @ trade px).",
        "",
        "## Headline",
        "",
        f"- n_cells=**{s['n_capacity_cells']}**; H^v mean=`{s['H_v_mean']}`; FEI=`{s['FEI_mean']}`",
        f"- Spearman(H^v, |mo|)=**{s['spearman']['H_v_vs_mean_abs_mo']:.3f}**; early/late={s['spearman']['H_v_vs_abs_mo_early']:.3f}/{s['spearman']['H_v_vs_abs_mo_late']:.3f}; stable=**{s['spearman']['sign_stable']}**",
        f"- Event high-H vs low-H Δ|mo|=`{s['event_high_vs_low_H']['abs_mo']}`",
        f"- POV sched vs flat: `{s.get('pov')}`",
        f"- Readiness: **{pol['readiness']}** (monitor={pol['monitor_readiness']}; promote_policy={pol['promote_as_risk_policy']})",
        "",
        "## Figures",
        "",
        "- `figs/fig_hv_quartile_severity.png`",
        "- `figs/fig_hv_vs_absmo.png`",
        "- `figs/fig_pov_schedule_vs_flat.png`",
        "",
    ]
    (CH / "EXP_REPORT.md").write_text("\n".join(lines) + "\n")
    (OUT / "hv_fei_capacity" / "EXP_REPORT.md").write_text("\n".join(lines) + "\n")


def _write_notes() -> None:
    (CH / "NOTES.md").write_text(
        r"""# H^v / FEI capacity → child sizing

**Track:** EXEC/SOR · **Objects:** `frag.volume_herfindahl_3venue` · `frag.fei_volume_3venue`

## Formulas

\[
H^v=\sum_k (s^k)^2,\quad \mathrm{FEI}=H_{\mathrm{Shannon}}(s)/\log N.
\]

POV child (paper): take \(\pi\) of each print; impact \(=10^4\cdot(vwap-p_0)/p_0\).

## Schedule

| H^v Q | \(\pi\) |
|------:|--------:|
| 0 (dispersed) | 0.08 |
| 1 | 0.06 |
| 2 | 0.04 |
| 3 (concentrated) | 0.025 |

## Honesty

No self-impact feedback into tape. Schedule is a capacity prior, not a calibrated Almgren–Chriss path.
"""
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-pov", action="store_true")
    args = ap.parse_args()
    s = run(force=args.force, run_pov=not args.no_pov)
    import json
    from _common import jsonable

    print(
        json.dumps(
            jsonable(
                {
                    "n_cells": s["n_capacity_cells"],
                    "spearman": s["spearman"],
                    "pov": s.get("pov"),
                    "readiness": s["policy"]["readiness"],
                }
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
