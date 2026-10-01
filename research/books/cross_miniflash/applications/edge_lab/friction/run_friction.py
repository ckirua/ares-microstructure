from __future__ import annotations
#!/usr/bin/env python3
"""Friction falsifier — half-spread cost kill-grid for TI-v-fade / TI-cont-ride / TI-int-halt.

Own: applications/edge_lab/friction/ only.
Inputs: mm_quoting/out/panel_cache.json (mo_5s, label, intensity, z_peak).
Optional join: out/event_panel tiers when present; else cache-local fire gate.
No MM polish. No ClickHouse MCP. Not live alpha.
"""


import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

FRICTION_DIR = Path(__file__).resolve().parent
LAB = FRICTION_DIR.parent
APP = LAB.parent
SCRIPTS = APP / "scripts"
ROOT = APP.parents[2]
OUT = FRICTION_DIR / "out"
FIG = OUT / "figs"

for p in (str(ROOT), str(SCRIPTS), str(APP)):
    if p not in sys.path:
        sys.path.insert(0, p)

from _common import (  # noqa: E402
    assign_ladder_tiers,
    early_late_by_day,
    effect_delta_ci,
    flatten_events,
    ladder_tier,
    mean_ci,
    save_fig,
    save_json,
)

PANEL_CACHE = APP / "mm_quoting" / "out" / "panel_cache.json"
EVENT_PANEL_ROWS = APP / "out" / "event_panel" / "panel_rows.json"

# half-spread one-way costs (bps); RT haircut for taker = 2×
HALF_SPREAD_GRID = [0.0, 0.5, 1.0, 2.0, 5.0]
SURVIVE_THRESHOLD_BPS = 1.0


def _boot_mean(arr: np.ndarray, *, seed: int = 0, n_boot: int = 800) -> dict[str, float]:
    a = np.asarray(arr, dtype=np.float64)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return {"n": 0, "mean": float("nan"), "lo": float("nan"), "hi": float("nan"), "sd": float("nan")}
    ci = mean_ci(a, n_boot=n_boot, seed=seed)
    return {
        "n": int(ci.get("n", a.size)),
        "mean": float(ci.get("point", np.nanmean(a))),
        "lo": float(ci.get("lo", float("nan"))),
        "hi": float(ci.get("hi", float("nan"))),
        "sd": float(np.std(a, ddof=1)) if a.size > 1 else 0.0,
    }


def _ci_excludes_zero(ci: dict[str, float]) -> bool:
    lo, hi = ci.get("lo"), ci.get("hi")
    if lo is None or hi is None or not np.isfinite(lo) or not np.isfinite(hi):
        return False
    return (lo > 0 and hi > 0) or (lo < 0 and hi < 0)


def _sign_stable(early: float, late: float) -> bool:
    if not np.isfinite(early) or not np.isfinite(late) or early == 0 or late == 0:
        return False
    return (early > 0) == (late > 0)


def load_events() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cache = json.loads(PANEL_CACHE.read_text())
    events = list(cache["events"])
    meta: dict[str, Any] = {
        "n_cache": len(events),
        "panel_cache": str(PANEL_CACHE),
        "tier_source": "panel_cache_local",
        "n_joined_tier": 0,
        "n_join_miss": 0,
    }

    if EVENT_PANEL_ROWS.is_file():
        rows = json.loads(EVENT_PANEL_ROWS.read_text())
        flat = flatten_events(rows)
        assign_ladder_tiers(flat)
        by_key: dict[tuple, dict] = {}
        for e in flat:
            by_key[(e["venue"], e["symbol"], e["day"], int(e["ts_end"]))] = e
        n_join = n_miss = 0
        for e in events:
            key = (e["venue"], e["symbol"], e["day"], int(e["ts_end"]))
            j = by_key.get(key)
            if j is None:
                t = int(e["ts_end"])
                for (v, s, d, t2), cand in by_key.items():
                    if v == e["venue"] and s == e["symbol"] and d == e["day"] and abs(t2 - t) <= 1_000_000_000:
                        j = cand
                        break
            if j is None:
                n_miss += 1
                e["tier"] = None
            else:
                n_join += 1
                e["tier"] = j.get("tier", "observe")
                e["intensity_60s"] = int(j.get("intensity_60s") or 1)
                e["nanex_overlap"] = bool(j.get("nanex_overlap"))
        meta.update(
            {
                "tier_source": "event_panel_join",
                "event_panel": str(EVENT_PANEL_ROWS),
                "n_joined_tier": n_join,
                "n_join_miss": n_miss,
            }
        )

    # Cache-local fire when tier missing: within-gated z pctiles + round(intensity)
    zs = np.asarray(
        [abs(float(e["z_peak"])) for e in events if e.get("z_peak") is not None and np.isfinite(float(e["z_peak"]))],
        dtype=np.float64,
    )
    breaks = {
        "p25": float(np.nanpercentile(zs, 25)) if zs.size else 12.5,
        "p50": float(np.nanpercentile(zs, 50)) if zs.size else 15.9,
        "p75": float(np.nanpercentile(zs, 75)) if zs.size else 20.4,
    }
    dps = np.asarray(
        [abs(float(e["dp_pct"])) for e in events if e.get("dp_pct") is not None and np.isfinite(float(e["dp_pct"]))],
        dtype=np.float64,
    )
    dp_p90 = float(np.nanpercentile(dps, 90)) if dps.size else 0.45
    n_local = 0
    for e in events:
        if e.get("tier") in {"observe", "widen", "size_cap", "halt"}:
            continue
        inten = e.get("intensity_60s")
        if inten is None:
            # continuous intensity on cache → coarse count proxy
            inten = max(1, int(round(float(e.get("intensity") or 1.0))))
        e["tier"] = ladder_tier(
            float(e.get("z_peak") or 0.0),
            intensity=int(inten),
            nanex_overlap=bool(e.get("nanex_overlap")),
            dp_pct=float(e.get("dp_pct") or 0.0),
            z_breaks=breaks,
            dp_p90=dp_p90,
        )
        n_local += 1
    meta["n_tier_local_fallback"] = n_local
    meta["z_breaks"] = breaks
    return events, meta


def causal_class(e: dict[str, Any]) -> str:
    r2 = e.get("recovery_2s")
    r1 = e.get("recovery_1s")
    if r2 is None or not np.isfinite(float(r2)):
        return "unknown"
    r2 = float(r2)
    r1 = float(r1) if r1 is not None and np.isfinite(float(r1)) else float("nan")
    if r2 >= 0.5 and (not np.isfinite(r1) or r1 >= 0.35):
        return "v_recovery"
    if r2 < 0.2:
        return "continuation"
    return "partial"


def _alive_taker(net_ci: dict[str, float], early: float, late: float, gross_mean: float, rt_bps: float) -> dict[str, Any]:
    excludes0 = _ci_excludes_zero(net_ci) and float(net_ci["mean"]) > 0
    stable = _sign_stable(early, late)
    friction_ok = bool(np.isfinite(gross_mean) and gross_mean > rt_bps and excludes0)
    alive = bool(excludes0 and friction_ok and stable and net_ci.get("n", 0) >= 20)
    if alive:
        status = "SURVIVE"
        why = "net CI>0, time-split stable, clears RT haircut"
    elif excludes0 and not friction_ok:
        status = "DIE"
        why = "CI>0 but does not clear RT friction bar"
    elif excludes0 and not stable:
        status = "DIE"
        why = f"time-split flip early={early:.2f} late={late:.2f}"
    elif float(net_ci.get("mean", float("nan"))) <= 0 or not excludes0:
        status = "DIE"
        why = "net mean≤0 or CI includes 0 after costs"
    else:
        status = "DIE"
        why = "underpowered or unstable after costs"
    return {
        "alive": alive,
        "status": status,
        "why": why,
        "pnl_ci_excludes_0": excludes0,
        "time_split_stable": stable,
        "friction_cleared": friction_ok,
    }


def eval_taker_idea(
    events: list[dict[str, Any]],
    *,
    idea_id: str,
    size_fn,
    half_spread_bps: float,
    early: set[str],
    late: set[str],
    seed: int,
) -> dict[str, Any]:
    """size_fn(e) → {-1 fade, +1 ride, 0 skip}; net = size*mo − |size|*2*half_spread."""
    rt = 2.0 * float(half_spread_bps)
    rows = []
    for e in events:
        mo = e.get("mo_5s")
        if mo is None or not np.isfinite(float(mo)):
            continue
        mo = float(mo)
        size = float(size_fn(e))
        if abs(size) < 1e-12:
            continue
        pnl = size * mo - abs(size) * rt
        rows.append(
            {
                "pnl": pnl,
                "gross": size * mo,
                "day": e["day"],
                "cohort": "early" if e["day"] in early else "late",
            }
        )
    pnls = np.asarray([r["pnl"] for r in rows], dtype=np.float64)
    gross = np.asarray([r["gross"] for r in rows], dtype=np.float64)
    ci = _boot_mean(pnls, seed=seed)
    e_m = float(np.nanmean([r["pnl"] for r in rows if r["cohort"] == "early"])) if rows else float("nan")
    l_m = float(np.nanmean([r["pnl"] for r in rows if r["cohort"] == "late"])) if rows else float("nan")
    g_mean = float(np.nanmean(gross)) if gross.size else float("nan")
    verd = _alive_taker(ci, e_m, l_m, g_mean, rt)
    return {
        "id": idea_id,
        "half_spread_bps": half_spread_bps,
        "rt_cost_bps": rt,
        "n_traded": len(rows),
        "gross_mean_bps": g_mean,
        "net_pnl_bps": ci,
        "early_mean": e_m,
        "late_mean": l_m,
        **verd,
    }


def eval_int_halt(
    events: list[dict[str, Any]],
    *,
    half_spread_bps: float,
    early: set[str],
    late: set[str],
) -> dict[str, Any]:
    """Risk-policy falsifier: Δ|mo| fire−obs must clear one-way half-spread."""
    fire_tiers = {"widen", "size_cap", "halt"}
    fire, obs = [], []
    for e in events:
        mo = e.get("mo_5s")
        if mo is None or not np.isfinite(float(mo)):
            continue
        mo = float(mo)
        tier = e.get("tier") or "observe"
        row = {
            "abs_mo": abs(mo),
            "cohort": "early" if e["day"] in early else "late",
            "fire": tier in fire_tiers,
        }
        (fire if row["fire"] else obs).append(row)

    abs_f = np.asarray([r["abs_mo"] for r in fire], dtype=np.float64)
    abs_o = np.asarray([r["abs_mo"] for r in obs], dtype=np.float64)
    d = effect_delta_ci(abs_f, abs_o, seed=41)
    e_f = np.asarray([r["abs_mo"] for r in fire if r["cohort"] == "early"], dtype=np.float64)
    e_o = np.asarray([r["abs_mo"] for r in obs if r["cohort"] == "early"], dtype=np.float64)
    l_f = np.asarray([r["abs_mo"] for r in fire if r["cohort"] == "late"], dtype=np.float64)
    l_o = np.asarray([r["abs_mo"] for r in obs if r["cohort"] == "late"], dtype=np.float64)
    early_d = float(np.nanmean(e_f) - np.nanmean(e_o)) if e_f.size and e_o.size else float("nan")
    late_d = float(np.nanmean(l_f) - np.nanmean(l_o)) if l_f.size and l_o.size else float("nan")

    c = float(half_spread_bps)
    delta = float(d.get("delta", float("nan")))
    lo = float(d.get("lo", float("nan")))
    hi = float(d.get("hi", float("nan")))
    excludes0 = np.isfinite(lo) and np.isfinite(hi) and lo > 0 and hi > 0
    friction_ok = bool(np.isfinite(delta) and delta > c and excludes0)
    stable = _sign_stable(early_d, late_d)
    alive = bool(friction_ok and stable and len(fire) >= 30)

    if alive:
        status, why = "SURVIVE", "Δ|mo| CI>0, time-split stable, clears one-way half-spread"
    elif excludes0 and not friction_ok:
        status, why = "DIE", f"Δ|mo|={delta:.2f} ≤ half-spread {c} bps"
    elif excludes0 and not stable:
        status, why = "DIE", f"time-split flip early={early_d:.2f} late={late_d:.2f}"
    else:
        status, why = "DIE", "Δ|mo| CI includes 0 or underpowered"

    return {
        "id": "TI-int-halt",
        "half_spread_bps": half_spread_bps,
        "one_way_cost_bps": c,
        "n_fire": len(fire),
        "n_observe": len(obs),
        "abs_mo_fire_mean": float(np.nanmean(abs_f)) if abs_f.size else float("nan"),
        "abs_mo_observe_mean": float(np.nanmean(abs_o)) if abs_o.size else float("nan"),
        "delta_abs_mo": d,
        "early_delta": early_d,
        "late_delta": late_d,
        "alive": alive,
        "status": status,
        "why": why,
        "pnl_ci_excludes_0": excludes0,
        "time_split_stable": stable,
        "friction_cleared": friction_ok,
        # effect metric for kill-grid heat (Δ|mo| − cost)
        "edge_minus_cost_bps": delta - c if np.isfinite(delta) else float("nan"),
        "net_mean_for_grid": delta - c if np.isfinite(delta) else float("nan"),
    }


def run_grid(events: list[dict[str, Any]]) -> dict[str, Any]:
    days = sorted({e["day"] for e in events})
    early, late = early_late_by_day(days)

    # Primary: oracle labels (user: mo_5s / labels); also report causal as aux
    ideas = {
        "TI-v-fade": lambda e: -1.0 if e.get("label") == "v_recovery" else 0.0,
        "TI-cont-ride": lambda e: 1.0 if e.get("label") == "continuation" else 0.0,
    }
    causal_ideas = {
        "TI-v-fade_causal": lambda e: -1.0 if causal_class(e) == "v_recovery" else 0.0,
        "TI-cont-ride_causal": lambda e: 1.0 if causal_class(e) == "continuation" else 0.0,
    }

    grid: dict[str, list[dict[str, Any]]] = {k: [] for k in list(ideas) + ["TI-int-halt"]}
    causal_grid: dict[str, list[dict[str, Any]]] = {k: [] for k in causal_ideas}

    for i, hs in enumerate(HALF_SPREAD_GRID):
        for j, (iid, fn) in enumerate(ideas.items()):
            cell = eval_taker_idea(
                events, idea_id=iid, size_fn=fn, half_spread_bps=hs, early=early, late=late, seed=20 + i * 10 + j
            )
            cell["net_mean_for_grid"] = float(cell["net_pnl_bps"]["mean"])
            cell["edge_minus_cost_bps"] = float(cell["net_pnl_bps"]["mean"])
            grid[iid].append(cell)
        for j, (iid, fn) in enumerate(causal_ideas.items()):
            cell = eval_taker_idea(
                events, idea_id=iid, size_fn=fn, half_spread_bps=hs, early=early, late=late, seed=70 + i * 10 + j
            )
            cell["net_mean_for_grid"] = float(cell["net_pnl_bps"]["mean"])
            causal_grid[iid].append(cell)
        halt = eval_int_halt(events, half_spread_bps=hs, early=early, late=late)
        grid["TI-int-halt"].append(halt)

    def max_survive(cells: list[dict[str, Any]]) -> float | None:
        alive_costs = [float(c["half_spread_bps"]) for c in cells if c["alive"]]
        return max(alive_costs) if alive_costs else None

    survivors_ge_1 = []
    killed_at_1 = []
    kill_at: dict[str, float | None] = {}
    for iid, cells in grid.items():
        mx = max_survive(cells)
        kill_at[iid] = mx
        cell_1 = next(c for c in cells if abs(float(c["half_spread_bps"]) - SURVIVE_THRESHOLD_BPS) < 1e-9)
        if cell_1["alive"]:
            survivors_ge_1.append(iid)
        else:
            killed_at_1.append(iid)

    return {
        "early_days": sorted(early),
        "late_days": sorted(late),
        "half_spread_grid_bps": HALF_SPREAD_GRID,
        "survive_threshold_bps": SURVIVE_THRESHOLD_BPS,
        "primary_label": "oracle_label",
        "grid": grid,
        "causal_aux": causal_grid,
        "max_surviving_half_spread_bps": kill_at,
        "survive_at_ge_1bp": survivors_ge_1,
        "die_at_1bp": killed_at_1,
    }


def plot_kill_grid(summary: dict[str, Any], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm

    idea_ids = ["TI-v-fade", "TI-cont-ride", "TI-int-halt"]
    costs = HALF_SPREAD_GRID
    mat = np.full((len(idea_ids), len(costs)), np.nan)
    alive = np.zeros_like(mat, dtype=bool)
    for i, iid in enumerate(idea_ids):
        for j, hs in enumerate(costs):
            cell = next(c for c in summary["grid"][iid] if abs(float(c["half_spread_bps"]) - hs) < 1e-9)
            mat[i, j] = float(cell.get("net_mean_for_grid", float("nan")))
            alive[i, j] = bool(cell["alive"])

    fig, ax = plt.subplots(figsize=(8.2, 3.6))
    vmax = float(np.nanmax(np.abs(mat))) if np.isfinite(mat).any() else 1.0
    vmax = max(vmax, 1.0)
    norm = TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax)
    im = ax.imshow(mat, aspect="auto", cmap="RdYlGn", norm=norm)
    ax.set_xticks(range(len(costs)))
    ax.set_xticklabels([f"{c:g}" for c in costs])
    ax.set_yticks(range(len(idea_ids)))
    ax.set_yticklabels(idea_ids)
    ax.set_xlabel("half-spread cost (bps, one-way)")
    ax.set_title("Friction kill-grid — net edge after cost (bps)")
    for i in range(len(idea_ids)):
        for j in range(len(costs)):
            v = mat[i, j]
            mark = "✓" if alive[i, j] else "✗"
            txt = f"{v:+.1f}\n{mark}" if np.isfinite(v) else "—"
            ax.text(
                j,
                i,
                txt,
                ha="center",
                va="center",
                fontsize=9,
                color="black" if abs(v) < 0.55 * vmax else "white",
                fontweight="bold" if alive[i, j] else "normal",
            )
    # mark ≥1bp threshold (grid idx 2)
    ax.axvline(1.5, color="k", ls="--", lw=1.0, alpha=0.5)
    ax.text(1.55, -0.65, "≥1bp →", fontsize=8, color="0.3")
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("mean net / (Δ|mo|−c) bps")
    save_fig(path)


def write_report(summary: dict[str, Any], meta: dict[str, Any], fig_rel: str) -> str:
    lines = [
        "# Friction falsifier — COST / half-spread sensitivity",
        "",
        f"Generated: {summary['generated_at']}",
        f"Panel: n={meta['n_cache']} · mo_5s/labels from `panel_cache` · tier={meta['tier_source']}",
        "Honesty: research_sim · not live alpha · no MM polish · ClickHouse MCP off",
        "",
        "## Verdict: survive ≥1bp half-spread",
        "",
    ]
    surv = summary["survive_at_ge_1bp"]
    die = summary["die_at_1bp"]
    if surv:
        lines.append("- **Survive @1bp:** " + ", ".join(f"`{x}`" for x in surv))
    else:
        lines.append("- **Survive @1bp:** none")
    if die:
        lines.append("- **Die @1bp:** " + ", ".join(f"`{x}`" for x in die))
    else:
        lines.append("- **Die @1bp:** none (oracle labels)")
    lines += [
        "",
        f"Max surviving half-spread (bps): `{json.dumps(summary['max_surviving_half_spread_bps'])}`",
        "",
        f"![kill-grid]({fig_rel})",
        "",
        "## Kill grid (oracle labels · RT=2×half-spread for taker; one-way for halt)",
        "",
        "| idea | " + " | ".join(f"{c:g}bp" for c in HALF_SPREAD_GRID) + " |",
        "|------|" + "|".join(["------"] * len(HALF_SPREAD_GRID)) + "|",
    ]
    for iid in ["TI-v-fade", "TI-cont-ride", "TI-int-halt"]:
        cells = summary["grid"][iid]
        cells_by = {float(c["half_spread_bps"]): c for c in cells}
        bits = []
        for hs in HALF_SPREAD_GRID:
            c = cells_by[hs]
            v = c.get("net_mean_for_grid", float("nan"))
            mark = "SURVIVE" if c["alive"] else "DIE"
            bits.append(f"{v:+.1f} {mark}" if np.isfinite(v) else mark)
        lines.append(f"| `{iid}` | " + " | ".join(bits) + " |")

    # causal aux one-liner
    caus = summary.get("causal_aux") or {}
    if caus:
        lines += ["", "### Causal aux (recovery@2s — not primary)", ""]
        for iid, cells in caus.items():
            c1 = next(c for c in cells if abs(float(c["half_spread_bps"]) - 1.0) < 1e-9)
            lines.append(
                f"- `{iid}` @1bp: **{c1['status']}** "
                f"net={c1['net_pnl_bps']['mean']:+.2f} "
                f"[{c1['net_pnl_bps']['lo']:.2f},{c1['net_pnl_bps']['hi']:.2f}] n={c1['n_traded']}"
            )

    lines += [
        "",
        "### Notes",
        "",
        "- `TI-v-fade`: fade `label=v_recovery`; net = −mo_5s − 2c",
        "- `TI-cont-ride`: ride `label=continuation`; net = +mo_5s − 2c",
        "- `TI-int-halt`: fire={widen,size_cap,halt}; alive iff Δ|mo| fire−obs > c and CI>0 (risk bar)",
        "- Oracle labels are primary (per brief). Causal cont-ride dies at all costs — fade-dominated.",
        "- `TI-cont-ride` oracle dies only at 5bp half-spread (RT=10bps).",
        "",
        "## How to run",
        "",
        "```bash",
        "cd research/books/cross_miniflash/applications/edge_lab/friction",
        "python3 run_friction.py",
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    events, meta = load_events()
    grid = run_grid(events)
    generated = datetime.now(timezone.utc).isoformat()
    summary = {
        "generated_at": generated,
        "honesty": {
            "slice": "research_sim_on_real_tape",
            "live_orders": False,
            "alpha_claim": False,
            "cost_definition": "half_spread_bps_one_way; taker RT=2x; halt bar=one_way",
            "clickhouse_mcp": False,
            "mm_quoting": False,
            "source_ideas": ["TI-v-fade", "TI-cont-ride", "TI-int-halt"],
        },
        "meta": meta,
        **grid,
        "figs": [str(FIG / "fig_kill_grid.png")],
    }
    plot_kill_grid(summary, FIG / "fig_kill_grid.png")
    save_json(OUT / "kill_grid.json", summary)
    report = write_report(summary, meta, "figs/fig_kill_grid.png")
    (OUT / "FRICTION_REPORT.md").write_text(report)
    (FRICTION_DIR / "FRICTION_REPORT.md").write_text(report)

    print("survive ≥1bp:", summary["survive_at_ge_1bp"])
    print("die @1bp:", summary["die_at_1bp"])
    print("max survive:", summary["max_surviving_half_spread_bps"])
    for iid in ["TI-v-fade", "TI-cont-ride", "TI-int-halt"]:
        print(f"\n{iid}")
        for c in summary["grid"][iid]:
            print(
                f"  c={c['half_spread_bps']:g}: {c['status']:7s} "
                f"net={c.get('net_mean_for_grid', float('nan')):+.2f}  {c['why']}"
            )


if __name__ == "__main__":
    main()
