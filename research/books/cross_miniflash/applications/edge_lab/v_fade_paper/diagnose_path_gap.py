from __future__ import annotations
#!/usr/bin/env python3
"""Path-gap diagnose + executable sweep with severity_zend causal fix.

Root cause (ENTRY_TIMING.md): rebound used up by ~+1s on HL ETH V-fades.
confirm_r2@+2s is structurally late. Causal fix: |z|≥z_min enter at ts_end, NO r2.

Compose: suppress_fire_pause (fade@fire ≈+0.34 vs quiet ≈+6.16).

Writes:
  out/PATH_GAP_REPORT.md
  out/gap_summary.json
  out/SHADOW_BOARD.md
  out/figs/gap_*.png

No ClickHouse MCP. No commit. live_orders=False.
"""


import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

PKG = Path(__file__).resolve().parent
sys.path.insert(0, str(PKG))

from harness.causal import jsonable  # noqa: E402
from harness.config import load_config  # noqa: E402
from harness.kill import _boot_mean  # noqa: E402
from harness.pipeline import _detect_cfg, _load_paper_detect  # noqa: E402
from harness.strategy import simulate_day_fades  # noqa: E402

NS = 1_000_000_000
DAYS = [
    "2026-09-04",
    "2026-09-05",
    "2026-09-06",
    "2026-09-07",
    "2026-09-08",
    "2026-09-09",
    "2026-09-10",
]
RT = 4.0
VENUE = "hyperliquid"
SYMBOL = "ETH"


def load_cells(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    detect = _load_paper_detect()
    dcfg = _detect_cfg(cfg)
    cells: list[dict[str, Any]] = []
    for day in DAYS:
        print(f"[gap] detect {day}…", flush=True)
        cell = detect(VENUE, SYMBOL, day, cfg=dcfg, quiet=True)
        if cell.get("skip") or (cfg.get("require_complete_day", True) and not cell.get("complete")):
            print(f"  skip {day}")
            continue
        cells.append(cell)
        print(f"  ssm_10_n={cell.get('ssm_10_n')}")
    return cells


def score_trades(trades: list[dict[str, Any]], *, seed: int = 101) -> dict[str, Any]:
    lab = np.asarray(
        [t["lab_pnl_net_bps"] for t in trades if t.get("lab_pnl_net_bps") is not None],
        dtype=np.float64,
    )
    lab = lab[np.isfinite(lab)]
    path = np.asarray(
        [t["path_pnl_net_bps"] for t in trades if t.get("path_pnl_net_bps") is not None],
        dtype=np.float64,
    )
    path = path[np.isfinite(path)]
    lab_ci = _boot_mean(lab, seed=seed, n_boot=800)
    path_ci = _boot_mean(path, seed=seed + 1, n_boot=800)
    early = {"2026-09-04", "2026-09-05", "2026-09-06"}
    late = {"2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10"}
    e = np.asarray(
        [float(t["path_pnl_net_bps"]) for t in trades if t.get("day") in early and t.get("path_pnl_net_bps") is not None],
        dtype=np.float64,
    )
    l = np.asarray(
        [float(t["path_pnl_net_bps"]) for t in trades if t.get("day") in late and t.get("path_pnl_net_bps") is not None],
        dtype=np.float64,
    )
    e, l = e[np.isfinite(e)], l[np.isfinite(l)]
    lo, hi = path_ci.get("lo"), path_ci.get("hi")
    path_ci_gt_0 = bool(
        path.size
        and lo is not None
        and hi is not None
        and np.isfinite(lo)
        and np.isfinite(hi)
        and lo > 0
    )
    n_fp_flag = sum(1 for t in trades if t.get("fire_tier") or t.get("in_fire_pause_at_entry"))
    n_adv = sum(1 for t in trades if t.get("exit_reason") == "adverse_stop")
    return {
        "n": int(path.size),
        "lab_ci": lab_ci,
        "path_ci": path_ci,
        "path_mean": path_ci.get("mean"),
        "path_lo": lo,
        "path_hi": hi,
        "path_ci_gt_0": path_ci_gt_0,
        "lab_mean": lab_ci.get("mean"),
        "path_hit": float(np.mean(path > 0)) if path.size else float("nan"),
        "lab_hit": float(np.mean(lab > 0)) if lab.size else float("nan"),
        "early_path_mean": float(np.mean(e)) if e.size else float("nan"),
        "late_path_mean": float(np.mean(l)) if l.size else float("nan"),
        "early_late_same_sign": bool(
            e.size and l.size and np.sign(np.mean(e)) == np.sign(np.mean(l)) and np.mean(e) != 0
        ),
        "n_adverse": n_adv,
        "n_fire_flagged": n_fp_flag,
    }


def run_policy(cells: list[dict], base_cfg: dict, **vf_kw: Any) -> dict[str, Any]:
    cfg = copy.deepcopy(base_cfg)
    vf = dict(cfg.get("v_fade") or {})
    vf.update(vf_kw)
    cfg["v_fade"] = vf
    trades: list[dict] = []
    n_fp_skip = 0
    for cell in cells:
        sim = simulate_day_fades(cell, cfg=cfg)
        trades.extend(sim.get("trades") or [])
        n_fp_skip += int(sim.get("n_fire_pause_skipped") or 0)
    sc = score_trades(trades)
    sc.update(
        {
            "entry_mode": vf.get("entry_mode"),
            "confirm_s": vf.get("confirm_s"),
            "exit_s": vf.get("exit_s"),
            "z_min": vf.get("z_min"),
            "adverse_stop_bps": None
            if float(vf.get("adverse_stop_bps", 12)) >= 1e8
            else float(vf.get("adverse_stop_bps", 12)),
            "suppress_fire_pause": vf.get("suppress_fire_pause", "prior_only"),
            "always_fade": bool(vf.get("always_fade", False)),
            "n_fire_pause_skipped": n_fp_skip,
        }
    )
    return sc


def main() -> None:
    out_dir = PKG / "out"
    fig_dir = out_dir / "figs"
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    cfg = load_config(PKG / "config.yaml")
    cfg["venue"] = VENUE
    cfg["symbol"] = SYMBOL
    cfg["extra_venues"] = []
    cells = load_cells(cfg)
    if not cells:
        raise SystemExit("no cells")

    # ---- baselines ----
    print("[gap] baseline confirm_r2@2s…", flush=True)
    base_r2 = run_policy(
        cells,
        cfg,
        entry_mode="confirm_r2",
        confirm_s=2.0,
        exit_s=5.0,
        adverse_stop_bps=12.0,
        suppress_fire_pause="prior_only",
        always_fade=False,
    )
    print(
        f"  path={base_r2['path_mean']:.2f} CI=[{base_r2['path_lo']:.2f},{base_r2['path_hi']:.2f}] "
        f"lab={base_r2['lab_mean']:.2f} n={base_r2['n']}",
        flush=True,
    )

    # ---- sweep severity_zend (prior_only fire pause) ----
    delays = [0.0, 0.5]
    exits = [3.0, 5.0, 8.0, 10.0]
    z_mins = [15.0, 18.0, 20.0]
    adverses = [1e9, 12.0]
    sweep: list[dict] = []
    total = 0
    for dly in delays:
        for ex in exits:
            if ex > dly:
                total += len(z_mins) * len(adverses)
    print(f"[gap] severity_zend sweep ({total} policies, fire_pause=prior_only)…", flush=True)
    done = 0
    for dly in delays:
        for ex in exits:
            if ex <= dly:
                continue
            for zm in z_mins:
                for adv in adverses:
                    row = run_policy(
                        cells,
                        cfg,
                        entry_mode="severity_zend",
                        confirm_s=dly,
                        exit_s=ex,
                        z_min=zm,
                        adverse_stop_bps=adv,
                        suppress_fire_pause="prior_only",
                        always_fade=False,
                    )
                    sweep.append(row)
                    done += 1
                    if done % 8 == 0 or (row.get("path_ci_gt_0") and row.get("n", 0) >= 20):
                        print(
                            f"  [{done}] d={dly} e={ex} z≥{zm} adv={adv if adv < 1e8 else 'off'} "
                            f"n={row['n']} path={row['path_mean']:.2f} clear={row['path_ci_gt_0']}",
                            flush=True,
                        )

    print("[gap] fire-pause mode contrast (z≥15 @0 exit5)…", flush=True)
    fp_prior = run_policy(
        cells, cfg, entry_mode="severity_zend", confirm_s=0.0, exit_s=5.0, z_min=15.0,
        adverse_stop_bps=12.0, suppress_fire_pause="prior_only",
    )
    fp_all = run_policy(
        cells, cfg, entry_mode="severity_zend", confirm_s=0.0, exit_s=5.0, z_min=15.0,
        adverse_stop_bps=12.0, suppress_fire_pause="all",
    )
    fp_off = run_policy(
        cells, cfg, entry_mode="severity_zend", confirm_s=0.0, exit_s=5.0, z_min=15.0,
        adverse_stop_bps=12.0, suppress_fire_pause="off",
    )
    fp_prior_05 = run_policy(
        cells, cfg, entry_mode="severity_zend", confirm_s=0.5, exit_s=5.0, z_min=15.0,
        adverse_stop_bps=12.0, suppress_fire_pause="prior_only",
    )

    clears = [
        r
        for r in sweep
        if r.get("path_ci_gt_0") and int(r.get("n") or 0) >= 20
    ]
    clears.sort(key=lambda r: r.get("path_mean") or -1e9, reverse=True)
    all_sorted = sorted(
        [r for r in sweep if int(r.get("n") or 0) >= 5],
        key=lambda r: r.get("path_mean") or -1e9,
        reverse=True,
    )
    best = clears[0] if clears else (all_sorted[0] if all_sorted else None)
    decision = "Promote_shadow" if clears else "Hold"
    promote_scope = "severity_zend_no_r2" if clears else None

    # ---- figs ----
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figs: list[str] = []
    # decomposition style bars
    fig, ax = plt.subplots(figsize=(8.5, 4.0))
    labels = [
        "confirm_r2\nlab net",
        "confirm_r2\npath net",
        "sev_z≥15@0\npath (prior_only)",
        "sev_z≥15@0.5\npath",
        "sev_z≥15@0\npath (fp off)",
    ]
    vals = [
        base_r2["lab_mean"],
        base_r2["path_mean"],
        fp_prior["path_mean"],
        fp_prior_05["path_mean"],
        fp_off["path_mean"],
    ]
    cols = ["#1a5276", "#c0392b", "#27ae60", "#16a085", "#7f8c8d"]
    ax.bar(labels, vals, color=cols, alpha=0.9)
    ax.axhline(0, color="#7f8c8d", lw=0.8)
    ax.set_ylabel("mean net bps (RT=4)")
    ax.set_title("HL ETH — confirm_r2 path-dead vs severity_zend causal fix")
    fig.tight_layout()
    p = fig_dir / "gap_decomposition.png"
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    figs.append(str(p))

    # heatmap delay × exit for z=15
    heat = {}
    for r in sweep:
        if r.get("z_min") != 15.0:
            continue
        key = (float(r["confirm_s"]), float(r["exit_s"]))
        m = r.get("path_mean")
        if m is None:
            continue
        if key not in heat or m > heat[key]:
            heat[key] = float(m)
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    ds, es = delays, exits
    Z = np.full((len(ds), len(es)), np.nan)
    for i, d in enumerate(ds):
        for j, e in enumerate(es):
            if e <= d:
                continue
            Z[i, j] = heat.get((d, e), np.nan)
    im = ax.imshow(Z, aspect="auto", cmap="RdYlGn", vmin=-10, vmax=15)
    ax.set_xticks(range(len(es)))
    ax.set_xticklabels([str(x) for x in es])
    ax.set_yticks(range(len(ds)))
    ax.set_yticklabels([str(x) for x in ds])
    ax.set_xlabel("exit_s")
    ax.set_ylabel("entry delay")
    ax.set_title("severity_zend |z|≥15 path mean (best adverse) — fire_pause prior_only")
    for i in range(len(ds)):
        for j in range(len(es)):
            if np.isfinite(Z[i, j]):
                ax.text(j, i, f"{Z[i,j]:.1f}", ha="center", va="center", fontsize=9)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    p = fig_dir / "gap_sweep_heatmap.png"
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    figs.append(str(p))

    top = all_sorted[:20]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    xs = np.arange(len(top))
    means = [r["path_mean"] for r in top]
    los = [r["path_lo"] for r in top]
    his = [r["path_hi"] for r in top]
    cols = ["#27ae60" if r.get("path_ci_gt_0") else "#7f8c8d" for r in top]
    ax.bar(xs, means, color=cols, alpha=0.85)
    ax.errorbar(
        xs,
        means,
        yerr=[np.array(means) - np.array(los), np.array(his) - np.array(means)],
        fmt="none",
        ecolor="#2c3e50",
        lw=0.8,
        capsize=2,
    )
    ax.axhline(0, color="#c0392b", lw=0.9, ls="--")
    ax.set_xticks(xs)
    ax.set_xticklabels(
        [
            f"d{r['confirm_s']}/e{r['exit_s']}/z{r['z_min']:g}"
            + ("" if r["adverse_stop_bps"] is None else f"/a{r['adverse_stop_bps']:g}")
            for r in top
        ],
        fontsize=6,
        rotation=70,
        ha="right",
    )
    ax.set_ylabel("path mean net bps")
    ax.set_title("Top severity_zend policies (green = path CI>0 after RT4)")
    fig.tight_layout()
    p = fig_dir / "gap_top_policies.png"
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    figs.append(str(p))

    # ---- reports ----
    gap_mean = (base_r2["lab_mean"] or 0) - (base_r2["path_mean"] or 0)
    lines = [
        "# V-fade PATH GAP REPORT",
        "",
        f"Generated: `{datetime.now(timezone.utc).isoformat()}`",
        f"Panel: **{VENUE} {SYMBOL}** · {DAYS[0]}…{DAYS[-1]} · RT={RT} bps",
        "",
        f"## Verdict: **{decision}**"
        + (f" (`{promote_scope}`)" if promote_scope else ""),
        "",
        "**Root cause:** rebound used up by ~**+1s** (ENTRY_TIMING.md). "
        "Median 100% of +5s rebound by +1s. Lab −mo₅ₛ credits pre-entry bounce; "
        "`confirm_r2@+2s` enters after the move → path ≈ −7 bps. "
        "Waiting for r≥0.5 *is* waiting until the rebound is done.",
        "",
        f"**Baseline confirm_r2@2→5 (fire_pause prior_only):** lab **{base_r2['lab_mean']:.2f}** "
        f"[{base_r2['lab_ci']['lo']:.2f}, {base_r2['lab_ci']['hi']:.2f}] · "
        f"path **{base_r2['path_mean']:.2f}** "
        f"[{base_r2['path_lo']:.2f}, {base_r2['path_hi']:.2f}] · gap ≈ {gap_mean:.1f} bps. "
        "**Path CI does not clear.**",
        "",
        "### Causal fix tested: `severity_zend`",
        "",
        "Enter at `ts_end + delay` if `|z_peak| ≥ z_min`. **No r2 wait.** "
        "Suppress while `fire_pause_5m` live (compose: fire fade +0.34 vs quiet +6.16).",
        "",
    ]
    if best:
        lines += [
            "### Best executable policy",
            "",
            "| param | value |",
            "|-------|------:|",
            f"| entry_mode | {best.get('entry_mode')} |",
            f"| confirm_s (delay) | {best.get('confirm_s')} |",
            f"| exit_s | {best.get('exit_s')} |",
            f"| z_min | {best.get('z_min')} |",
            f"| adverse_stop_bps | {best.get('adverse_stop_bps')} |",
            f"| suppress_fire_pause | {best.get('suppress_fire_pause')} |",
            f"| n | {best.get('n')} |",
            f"| path mean | **{best.get('path_mean'):.3f}** |",
            f"| path CI | [{best.get('path_lo'):.3f}, {best.get('path_hi'):.3f}] |",
            f"| lab mean (identity on selected) | {best.get('lab_mean'):.3f} |",
            f"| path hit | {best.get('path_hit'):.3f} |",
            f"| early / late path | {best.get('early_path_mean'):.2f} / {best.get('late_path_mean'):.2f} |",
            f"| fire_pause skipped | {best.get('n_fire_pause_skipped')} |",
            "",
        ]
    lines += [
        "### Fire-pause compose (severity_zend z≥15 @0 / exit5)",
        "",
        "Note: `|z|≥15` is almost entirely fire-tier (101/103). Mode `all` (skip own onset) "
        "collapses to n≈2 — underpowered. Mode `prior_only` allows fade at own `ts_end`, "
        "blocks follow-ons in the 5m pause. Sibling quiet-vs-fire (+6.16 vs +0.34) is "
        "confirm_r2 lab identity; severity_zend path is a different selection.",
        "",
        "| suppress | n | path mean | path CI |",
        "|----------|--:|----------:|---------|",
        f"| prior_only | {fp_prior['n']} | {fp_prior['path_mean']:.2f} | [{fp_prior['path_lo']:.2f}, {fp_prior['path_hi']:.2f}] |",
        f"| all (incl. own) | {fp_all['n']} | {fp_all['path_mean']:.2f} | [{fp_all['path_lo']:.2f}, {fp_all['path_hi']:.2f}] |",
        f"| off | {fp_off['n']} | {fp_off['path_mean']:.2f} | [{fp_off['path_lo']:.2f}, {fp_off['path_hi']:.2f}] |",
        f"| prior_only @+0.5s | {fp_prior_05['n']} | {fp_prior_05['path_mean']:.2f} | [{fp_prior_05['path_lo']:.2f}, {fp_prior_05['path_hi']:.2f}] |",
        "",
        f"n_clearing severity_zend policies (path CI>0 **and** n≥20): **{len(clears)}** / {len(sweep)}",
        "",
        "### Top 12 by path mean",
        "",
        "| delay | exit | z_min | adverse | n | path mean | path CI | clear |",
        "|------:|-----:|------:|--------:|--:|----------:|---------|:-----:|",
    ]
    for r in all_sorted[:12]:
        adv = "off" if r.get("adverse_stop_bps") is None else f"{r['adverse_stop_bps']}"
        lines.append(
            f"| {r['confirm_s']} | {r['exit_s']} | {r['z_min']} | {adv} | {r['n']} | "
            f"{r['path_mean']:.2f} | [{r['path_lo']:.2f}, {r['path_hi']:.2f}] | "
            f"{'Y' if r.get('path_ci_gt_0') and int(r.get('n') or 0) >= 20 else ''} |"
        )
    lines += [
        "",
        "## Math: why lab ≠ path under confirm_r2",
        "",
        "```text",
        "lab_net  = −mo_5s − RT          # mo from ts_end → +5s",
        "path_net = s·(P_exit/P_entry−1)·1e4 − RT",
        "         entry = ts_end + confirm_s",
        "",
        "−mo_5s ≈ fade(0→confirm) + fade(confirm→exit)",
        "path   ≈ fade(confirm→exit)     # misses pre-entry rebound",
        "```",
        "",
        "With confirm=2s, fade(0→2) ≈ +20 bps on V set; fade(2→5) ≤ 0. Gap ≈ pre-entry.",
        "",
        "## Figures",
        "",
    ]
    for f in figs:
        lines.append(f"- `figs/{Path(f).name}`")
    lines += [
        "",
        "## Honesty",
        "",
        "SHADOW PAPER · RT=4 · mid_mo null → tape · live_orders=False · "
        "**path ≠ lab** · Promote_shadow only if path CI>0 · ClickHouse MCP banned · "
        "see ENTRY_TIMING.md",
        "",
        "CLI:",
        "```bash",
        "python3 run_v_fade_paper.py --panel-days --entry-mode severity_zend --confirm-s 0 --z-min 15",
        "python3 run_v_fade_paper.py --panel-days --entry-mode confirm_r2 --confirm-s 2  # lab board",
        "```",
        "",
    ]
    report = out_dir / "PATH_GAP_REPORT.md"
    report.write_text("\n".join(lines) + "\n")

    # SHADOW_BOARD
    sb = [
        "# V-fade SHADOW BOARD",
        "",
        f"Generated: `{datetime.now(timezone.utc).isoformat()}`",
        "",
        f"**Decision: {decision}**"
        + (f" · scope `{promote_scope}`" if promote_scope else " · causal confirm_r2 path-dead"),
        "",
        "live_orders=false · SHADOW PAPER · not OE live",
        "",
        "## Path scoreboard (RT=4)",
        "",
        "| policy | n | path mean | path CI | clear? |",
        "|--------|--:|----------:|---------|:------:|",
        f"| confirm_r2 @2→5 (legacy) | {base_r2['n']} | {base_r2['path_mean']:.2f} | "
        f"[{base_r2['path_lo']:.2f}, {base_r2['path_hi']:.2f}] | |",
    ]
    if best:
        sb.append(
            f"| **best severity_zend** d={best['confirm_s']} e={best['exit_s']} "
            f"z≥{best['z_min']} | {best['n']} | **{best['path_mean']:.2f}** | "
            f"[{best['path_lo']:.2f}, {best['path_hi']:.2f}] | "
            f"{'Y' if best.get('path_ci_gt_0') else ''} |"
        )
    sb += [
        f"| severity z≥15 @0 exit5 prior_only | {fp_prior['n']} | {fp_prior['path_mean']:.2f} | "
        f"[{fp_prior['path_lo']:.2f}, {fp_prior['path_hi']:.2f}] | "
        f"{'Y' if fp_prior.get('path_ci_gt_0') else ''} |",
        f"| severity z≥15 @0.5 exit5 prior_only | {fp_prior_05['n']} | {fp_prior_05['path_mean']:.2f} | "
        f"[{fp_prior_05['path_lo']:.2f}, {fp_prior_05['path_hi']:.2f}] | "
        f"{'Y' if fp_prior_05.get('path_ci_gt_0') else ''} |",
        "",
        "## Compose rules",
        "",
        "1. **No confirm_r2 for executable path** — rebound spent by ~+1s.",
        "2. **severity_zend**: `|z|≥15` (or 20) enter at `ts_end` (+0 / +0.5s OE buffer); **no r2**.",
        "3. **fire_pause prior_only** — allow fade at own fire `ts_end`; block follow-ons for 300s. "
        "Mode `all` collapses severity book (101/103 of |z|≥15 are fire-tier).",
        "",
        "Details: PATH_GAP_REPORT.md · ENTRY_TIMING.md",
        "",
    ]
    (out_dir / "SHADOW_BOARD.md").write_text("\n".join(sb) + "\n")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "venue": VENUE,
        "symbol": SYMBOL,
        "days": DAYS,
        "rt_friction_bps": RT,
        "decision": decision,
        "promote_scope": promote_scope,
        "n_clearing_policies": len(clears),
        "best_policy": best,
        "baseline_confirm_r2": base_r2,
        "severity_zend_fp_prior_z15_d0_e5": fp_prior,
        "severity_zend_fp_prior_z15_d05_e5": fp_prior_05,
        "severity_zend_fp_all_z15_d0_e5": fp_all,
        "severity_zend_fp_off_z15_d0_e5": fp_off,
        "sweep_top12": all_sorted[:12],
        "root_cause": {
            "summary": "rebound used up by ~+1s; confirm_r2 structurally late",
            "entry_timing_md": str(out_dir / "ENTRY_TIMING.md"),
            "gap_lab_minus_path_confirm_r2": gap_mean,
        },
        "compose": {
            "suppress_fire_pause": True,
            "sibling_fire_vs_quiet": "fade@fire≈+0.34 vs quiet≈+6.16",
            "lr_fire_pause_verdict": "Hold",
        },
        "figures": figs,
        "report_md": str(report),
        "shadow_board_md": str(out_dir / "SHADOW_BOARD.md"),
        "honesty": {
            "path_equals_lab": False,
            "alpha_claim": False,
            "live_orders": False,
            "clickhouse_mcp": False,
            "promote_requires_path_ci_gt_0": True,
        },
    }
    sum_path = out_dir / "gap_summary.json"
    sum_path.write_text(json.dumps(jsonable(summary), indent=2) + "\n")
    print(
        json.dumps(
            {
                "decision": decision,
                "promote_scope": promote_scope,
                "best_path_mean": (best or {}).get("path_mean"),
                "best_path_ci": [(best or {}).get("path_lo"), (best or {}).get("path_hi")],
                "best_params": {
                    k: (best or {}).get(k)
                    for k in (
                        "entry_mode",
                        "confirm_s",
                        "exit_s",
                        "z_min",
                        "adverse_stop_bps",
                        "suppress_fire_pause",
                        "n",
                    )
                },
                "baseline_path": base_r2["path_mean"],
                "baseline_lab": base_r2["lab_mean"],
                "n_clearing": len(clears),
                "report": str(report),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
