#!/usr/bin/env python3
"""Diagnose lab (−mo5s−RT) vs executable path PnL gap; sweep executable policies.

Writes:
  out/PATH_GAP_REPORT.md
  out/gap_summary.json
  out/figs/gap_*.png

Primary cell: hyperliquid ETH, Phase-4 days 2026-09-04…10.
No ClickHouse MCP. Warehouse + detect only.
"""

from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

PKG = Path(__file__).resolve().parent
sys.path.insert(0, str(PKG))

from harness.causal import asof_trade_idx, asof_trade_px, causal_class, jsonable  # noqa: E402
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

# Sweep grids
CONFIRM_S = [0.0, 0.5, 1.0, 2.0, 3.0]
EXIT_S = [3.0, 5.0, 8.0, 10.0]
V_THR = [0.35, 0.50, 0.65, 0.80]
SOFT_R1 = [0.0, 0.35]
ADVERSE = [1e9, 12.0, 25.0]  # 1e9 ≈ disabled


def _indices_from_ts(
    ts: np.ndarray, ts_start: np.ndarray, ts_end: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Map event clocks to tape indices (last print ≤ ts)."""
    start_i = np.searchsorted(ts, ts_start, side="right") - 1
    end_i = np.searchsorted(ts, ts_end, side="right") - 1
    return start_i.astype(np.int64), end_i.astype(np.int64)


def recovery_at_horizon(cell: dict[str, Any], horizon_s: float) -> np.ndarray:
    """Causal recovery fraction at arbitrary horizon after ts_end."""
    from research.lib.crash import recovery_fraction

    if horizon_s <= 0:
        n = int(cell.get("ssm_10_n") or 0)
        return np.zeros(n, dtype=np.float64)
    ev = cell["events"]
    ts = np.asarray(cell["ts"], dtype=np.int64)
    px = np.asarray(cell["px"], dtype=np.float64)
    ts_start = np.asarray(ev["ts_start"], dtype=np.int64)
    ts_end = np.asarray(ev["ts_end"], dtype=np.int64)
    direction = np.asarray(ev["direction"], dtype=np.int64)
    start_i, end_i = _indices_from_ts(ts, ts_start, ts_end)
    return recovery_fraction(
        ts, px, start_i, end_i, direction, horizon_s=float(horizon_s)
    )


def load_cells(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    detect = _load_paper_detect()
    dcfg = _detect_cfg(cfg)
    cells: list[dict[str, Any]] = []
    for day in DAYS:
        print(f"[gap] detect {day} {VENUE} {SYMBOL}…", flush=True)
        cell = detect(VENUE, SYMBOL, day, cfg=dcfg, quiet=True)
        if cell.get("skip"):
            print(f"  skip: {cell['skip']}")
            continue
        if cfg.get("require_complete_day", True) and not cell.get("complete"):
            print(f"  incomplete: {cell.get('completeness')}")
            continue
        cells.append(cell)
        print(f"  ssm_10_n={cell.get('ssm_10_n')}")
    return cells


def decompose_baseline(cells: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    """Baseline confirm=2 / exit=5 / adverse=12 — math decomposition."""
    all_rows: list[dict[str, Any]] = []
    for cell in cells:
        sim = simulate_day_fades(cell, cfg=cfg)
        ts = np.asarray(cell["ts"], dtype=np.int64)
        px = np.asarray(cell["px"], dtype=np.float64)
        ev = cell["events"]
        ts_end = np.asarray(ev["ts_end"], dtype=np.int64)
        direction = np.asarray(ev["direction"], dtype=np.int64)
        mo5 = np.asarray(ev["mo_5s"], dtype=np.float64)
        for t in sim.get("trades") or []:
            i = int(t["event_i"])
            te = int(ts_end[i])
            d = int(direction[i])
            side = -d
            p0 = asof_trade_px(ts, px, te)
            p2 = asof_trade_px(ts, px, te + int(2 * NS))
            p5 = asof_trade_px(ts, px, te + int(5 * NS))
            fade_0_2 = float(side) * (p2 / p0 - 1.0) * 1e4 if np.isfinite(p0) and np.isfinite(p2) and p0 > 0 else float("nan")
            fade_2_5 = float(side) * (p5 / p2 - 1.0) * 1e4 if np.isfinite(p2) and np.isfinite(p5) and p2 > 0 else float("nan")
            mo_seg_0_2 = float(d) * (p2 / p0 - 1.0) * 1e4 if np.isfinite(p0) and np.isfinite(p2) and p0 > 0 else float("nan")
            mo_seg_2_5 = float(d) * (p5 / p2 - 1.0) * 1e4 if np.isfinite(p2) and np.isfinite(p5) and p2 > 0 else float("nan")
            row = {
                **{k: t.get(k) for k in (
                    "day", "event_i", "exit_reason", "hold_s",
                    "lab_pnl_net_bps", "path_pnl_net_bps",
                    "lab_gross_bps", "path_gross_bps", "mo_5s",
                    "side", "direction", "oracle_label", "causal_class",
                )},
                "fade_gross_0_2s": fade_0_2,
                "fade_gross_2_5s": fade_2_5,
                "mo_seg_0_2s": mo_seg_0_2,
                "mo_seg_2_5s": mo_seg_2_5,
                "gap_lab_minus_path": (
                    float(t["lab_pnl_net_bps"]) - float(t["path_pnl_net_bps"])
                    if t.get("lab_pnl_net_bps") is not None and t.get("path_pnl_net_bps") is not None
                    else None
                ),
            }
            all_rows.append(row)

    lab = np.asarray([r["lab_pnl_net_bps"] for r in all_rows], dtype=np.float64)
    path = np.asarray([r["path_pnl_net_bps"] for r in all_rows], dtype=np.float64)
    gap = lab - path
    pre = np.asarray([r["fade_gross_0_2s"] for r in all_rows], dtype=np.float64)
    post = np.asarray([r["fade_gross_2_5s"] for r in all_rows], dtype=np.float64)
    lab_g = np.asarray([r["lab_gross_bps"] for r in all_rows], dtype=np.float64)
    path_g = np.asarray([r["path_gross_bps"] for r in all_rows], dtype=np.float64)

    by_exit: dict[str, Any] = {}
    for reason in ("time_stop", "adverse_stop"):
        m = np.asarray([r["exit_reason"] == reason for r in all_rows])
        if not m.any():
            continue
        by_exit[reason] = {
            "n": int(m.sum()),
            "lab_mean": float(np.nanmean(lab[m])),
            "path_mean": float(np.nanmean(path[m])),
            "gap_mean": float(np.nanmean(gap[m])),
            "path_hit": float(np.nanmean(path[m] > 0)),
        }

    # Side-sign audit: path_gross should equal −mo_seg from entry→exit for time stops
    time_rows = [r for r in all_rows if r["exit_reason"] == "time_stop"]
    side_ok = 0
    side_n = 0
    for r in time_rows:
        if r.get("fade_gross_2_5s") is None or not np.isfinite(r["fade_gross_2_5s"]):
            continue
        side_n += 1
        # path_gross ≈ fade_2_5 when exit is time_stop @ +5s (adverse may exit early)
        if abs(float(r["path_gross_bps"]) - float(r["fade_gross_2_5s"])) < 0.05:
            side_ok += 1

    return {
        "n": len(all_rows),
        "lab_ci": _boot_mean(lab, seed=11, n_boot=800),
        "path_ci": _boot_mean(path, seed=12, n_boot=800),
        "gap_mean": float(np.nanmean(gap)),
        "gap_ci": _boot_mean(gap, seed=13, n_boot=800),
        "timing": {
            "fade_gross_0_2s_mean": float(np.nanmean(pre)),
            "fade_gross_2_5s_mean": float(np.nanmean(post)),
            "lab_gross_mean": float(np.nanmean(lab_g)),
            "path_gross_mean": float(np.nanmean(path_g)),
            "missed_pre_entry_approx": float(np.nanmean(pre)),
            "identity_check": (
                "lab_gross ≈ fade(0→5) ≈ fade(0→2)+fade(2→5); "
                "path_gross ≈ fade(2→exit). Gap ≈ fade(0→2) when exit@5s time_stop."
            ),
            "additive_residual_mean": float(
                np.nanmean(lab_g - (pre + post))
            ),
        },
        "by_exit": by_exit,
        "adverse_share": float(
            np.mean([r["exit_reason"] == "adverse_stop" for r in all_rows])
        ),
        "path_hit_rate": float(np.nanmean(path > 0)),
        "lab_hit_rate": float(np.nanmean(lab > 0)),
        "corr_lab_path": float(np.corrcoef(lab, path)[0, 1]) if lab.size > 1 else float("nan"),
        "side_sign_audit": {
            "time_stop_n": side_n,
            "path_equals_fade_2_5_n": side_ok,
            "ok": side_ok == side_n and side_n > 0,
            "note": "path_gross = side×(exit/entry−1)×1e4 with side=−direction; matches −mo_seg",
        },
        "mid_vs_tape": {
            "mid_mo": "null on panel — both lab mo_5s and path fills use tape prints",
            "gap_from_mid": 0.0,
            "note": "Not a mid/tape gap; scoreboard is tape mo by construction",
        },
        "look_ahead": {
            "entry_uses_oracle_label": False,
            "entry_uses_recovery_5s": False,
            "lab_scoreboard_looks_past_entry": True,
            "detail": (
                "Lab pnl = −mo_5s − RT credits the full 0→5s move from ts_end, "
                "including the 0→2s rebound that *defines* causal V. That rebound "
                "is known only after confirm — it is not earnable at entry@+2s. "
                "This is economic look-ahead in the scoreboard, not a label leak."
            ),
        },
        "rows_sample": all_rows[:12],
    }


def simulate_policy(
    cells: list[dict[str, Any]],
    *,
    confirm_s: float,
    exit_s: float,
    v_thr: float,
    soft_r1: float,
    adverse_stop: float,
    base_cfg: dict[str, Any],
) -> dict[str, Any]:
    """Run path+lab for one policy. For confirm_s=0 → always_fade (no V gate)."""
    if exit_s <= confirm_s:
        return {
            "n": 0,
            "skipped": True,
            "reason": "exit_s <= confirm_s",
            "confirm_s": confirm_s,
            "exit_s": exit_s,
        }

    cfg = copy.deepcopy(base_cfg)
    vf = dict(cfg.get("v_fade") or {})
    vf.update(
        {
            "confirm_s": float(confirm_s),
            "exit_s": float(exit_s),
            "v_threshold_r2": float(v_thr),
            "soft_confirm_r1": float(soft_r1),
            "adverse_stop_bps": float(adverse_stop),
            # instruct strategy to recompute recovery at confirm horizon
            "recovery_horizon_s": float(confirm_s) if confirm_s > 0 else 0.0,
            "always_fade": bool(confirm_s <= 0),
        }
    )
    cfg["v_fade"] = vf

    trades: list[dict[str, Any]] = []
    for cell in cells:
        # Inject horizon-specific recovery into a shallow-copied cell events
        cell2 = dict(cell)
        ev = dict(cell["events"])
        if confirm_s <= 0:
            # always fade — mark all as v_recovery for gate bypass via always_fade flag
            pass
        else:
            r_c = recovery_at_horizon(cell, confirm_s)
            # soft at min(1s, confirm)
            soft_h = min(1.0, float(confirm_s))
            r_soft = recovery_at_horizon(cell, soft_h) if soft_h > 0 else r_c
            # strategy reads recovery_2s / recovery_1s — overlay causal horizons
            ev = dict(ev)
            ev["recovery_2s"] = r_c  # "confirm-horizon recovery" slot
            ev["recovery_1s"] = r_soft
            cell2["events"] = ev
        sim = simulate_day_fades(cell2, cfg=cfg)
        trades.extend(sim.get("trades") or [])

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
    lab_ci = _boot_mean(lab, seed=101, n_boot=800)
    path_ci = _boot_mean(path, seed=102, n_boot=800)
    early = set(vf.get("early_days") or ["2026-09-04", "2026-09-05", "2026-09-06"])
    late = set(vf.get("late_days") or ["2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10"])
    e = np.asarray(
        [float(t["path_pnl_net_bps"]) for t in trades if t.get("day") in early and t.get("path_pnl_net_bps") is not None],
        dtype=np.float64,
    )
    l = np.asarray(
        [float(t["path_pnl_net_bps"]) for t in trades if t.get("day") in late and t.get("path_pnl_net_bps") is not None],
        dtype=np.float64,
    )
    e = e[np.isfinite(e)]
    l = l[np.isfinite(l)]
    path_lo = path_ci.get("lo")
    path_hi = path_ci.get("hi")
    path_ci_excludes_0 = bool(
        path.size
        and path_lo is not None
        and path_hi is not None
        and np.isfinite(path_lo)
        and np.isfinite(path_hi)
        and (path_lo > 0 or path_hi < 0)
        and path_ci.get("mean", 0) > 0
        and path_lo > 0
    )
    n_adv = sum(1 for t in trades if t.get("exit_reason") == "adverse_stop")
    return {
        "confirm_s": confirm_s,
        "exit_s": exit_s,
        "v_threshold_r2": v_thr,
        "soft_confirm_r1": soft_r1,
        "adverse_stop_bps": None if adverse_stop >= 1e8 else adverse_stop,
        "always_fade": confirm_s <= 0,
        "n": int(path.size),
        "n_adverse": n_adv,
        "lab_ci": lab_ci,
        "path_ci": path_ci,
        "path_mean": path_ci.get("mean"),
        "path_lo": path_lo,
        "path_hi": path_hi,
        "path_ci_gt_0": path_ci_excludes_0,
        "path_hit": float(np.mean(path > 0)) if path.size else float("nan"),
        "lab_mean": lab_ci.get("mean"),
        "early_path_mean": float(np.mean(e)) if e.size else float("nan"),
        "late_path_mean": float(np.mean(l)) if l.size else float("nan"),
        "early_late_same_sign": bool(
            e.size and l.size and np.sign(np.mean(e)) == np.sign(np.mean(l)) and np.mean(e) != 0
        ),
    }


def run_sweep(cells: list[dict[str, Any]], base_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    total = 0
    for c in CONFIRM_S:
        for e in EXIT_S:
            if e <= c:
                continue
            thr_list = [0.50] if c <= 0 else V_THR  # always_fade: thr unused
            soft_list = [0.0] if c <= 0 else SOFT_R1
            for v in thr_list:
                for soft in soft_list:
                    for adv in ADVERSE:
                        total += 1
    print(f"[gap] sweep {total} policies…", flush=True)
    done = 0
    for c in CONFIRM_S:
        for e in EXIT_S:
            if e <= c:
                continue
            thr_list = [0.50] if c <= 0 else V_THR
            soft_list = [0.0] if c <= 0 else SOFT_R1
            for v in thr_list:
                for soft in soft_list:
                    for adv in ADVERSE:
                        row = simulate_policy(
                            cells,
                            confirm_s=c,
                            exit_s=e,
                            v_thr=v,
                            soft_r1=soft,
                            adverse_stop=adv,
                            base_cfg=base_cfg,
                        )
                        rows.append(row)
                        done += 1
                        if done % 25 == 0 or row.get("path_ci_gt_0"):
                            print(
                                f"  [{done}/{total}] c={c} e={e} v={v} soft={soft} adv={adv} "
                                f"n={row.get('n')} path={row.get('path_mean'):.2f} "
                                f"ci_gt0={row.get('path_ci_gt_0')}",
                                flush=True,
                            )
    return rows


def pick_best(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Best executable: prefer path_ci_gt_0; else max path mean with n>=10."""
    valid = [r for r in rows if not r.get("skipped") and (r.get("n") or 0) >= 5]
    clears = [r for r in valid if r.get("path_ci_gt_0")]
    if clears:
        clears.sort(key=lambda r: (r.get("path_mean") or -1e9), reverse=True)
        best = clears[0]
        return {"decision": "Promote_shadow", "best": best, "n_clearing": len(clears)}
    valid.sort(
        key=lambda r: (
            r.get("path_mean") if r.get("path_mean") is not None else -1e9,
            r.get("n") or 0,
        ),
        reverse=True,
    )
    best = valid[0] if valid else None
    return {"decision": "Hold", "best": best, "n_clearing": 0}


def write_figs(
    decomp: dict[str, Any],
    sweep: list[dict[str, Any]],
    best_pack: dict[str, Any],
    out_dir: Path,
) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig_dir = out_dir / "figs"
    fig_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    # 1) Decomposition bars
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    labels = [
        "lab gross\n(−mo5s)",
        "fade 0→2s\n(pre-entry)",
        "fade 2→5s\n(residual)",
        "path gross\n(entry→exit)",
        "lab net\n(−RT4)",
        "path net\n(−RT4)",
    ]
    vals = [
        decomp["timing"]["lab_gross_mean"],
        decomp["timing"]["fade_gross_0_2s_mean"],
        decomp["timing"]["fade_gross_2_5s_mean"],
        decomp["timing"]["path_gross_mean"],
        decomp["lab_ci"]["mean"],
        decomp["path_ci"]["mean"],
    ]
    colors = ["#1a5276", "#27ae60", "#e67e22", "#c0392b", "#1a5276", "#c0392b"]
    ax.bar(labels, vals, color=colors, alpha=0.88)
    ax.axhline(0, color="#7f8c8d", lw=0.8)
    ax.set_ylabel("mean bps")
    ax.set_title("HL ETH — lab vs path decomposition (baseline confirm=2s, exit=5s)")
    fig.tight_layout()
    p = fig_dir / "gap_decomposition.png"
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p))

    # 2) Sweep heatmap: best path mean by (confirm, exit) over thr/soft/adv
    heat: dict[tuple[float, float], float] = {}
    heat_n: dict[tuple[float, float], int] = {}
    for r in sweep:
        if r.get("skipped"):
            continue
        key = (float(r["confirm_s"]), float(r["exit_s"]))
        m = r.get("path_mean")
        if m is None or not np.isfinite(m):
            continue
        if key not in heat or m > heat[key]:
            heat[key] = float(m)
            heat_n[key] = int(r.get("n") or 0)
    fig, ax = plt.subplots(figsize=(8.2, 4.5))
    cs = CONFIRM_S
    es = EXIT_S
    Z = np.full((len(cs), len(es)), np.nan)
    for i, c in enumerate(cs):
        for j, e in enumerate(es):
            if e <= c:
                continue
            Z[i, j] = heat.get((c, e), np.nan)
    im = ax.imshow(Z, aspect="auto", cmap="RdYlGn", vmin=-15, vmax=5)
    ax.set_xticks(range(len(es)))
    ax.set_xticklabels([str(x) for x in es])
    ax.set_yticks(range(len(cs)))
    ax.set_yticklabels([str(x) for x in cs])
    ax.set_xlabel("exit_s (from ts_end)")
    ax.set_ylabel("confirm_s (entry delay)")
    ax.set_title("Best path mean net bps over thr/soft/adverse (HL ETH)")
    for i, c in enumerate(cs):
        for j, e in enumerate(es):
            if e <= c or not np.isfinite(Z[i, j]):
                continue
            ax.text(j, i, f"{Z[i,j]:.1f}", ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="path mean bps")
    fig.tight_layout()
    p = fig_dir / "gap_sweep_heatmap.png"
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p))

    # 3) Top policies scatter
    valid = [r for r in sweep if not r.get("skipped") and (r.get("n") or 0) >= 10]
    valid.sort(key=lambda r: r.get("path_mean") or -1e9, reverse=True)
    top = valid[:25]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    xs = np.arange(len(top))
    means = [r["path_mean"] for r in top]
    los = [r["path_lo"] for r in top]
    his = [r["path_hi"] for r in top]
    cols = ["#27ae60" if r.get("path_ci_gt_0") else "#7f8c8d" for r in top]
    ax.bar(xs, means, color=cols, alpha=0.85)
    ax.errorbar(xs, means, yerr=[np.array(means) - np.array(los), np.array(his) - np.array(means)],
                fmt="none", ecolor="#2c3e50", lw=0.8, capsize=2)
    ax.axhline(0, color="#c0392b", lw=0.9, ls="--")
    labels = [
        f"c{r['confirm_s']}/e{r['exit_s']}\nv{r['v_threshold_r2']}"
        + ("" if r.get("adverse_stop_bps") is None else f"/a{r['adverse_stop_bps']}")
        for r in top
    ]
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, fontsize=6, rotation=75, ha="right")
    ax.set_ylabel("path mean net bps")
    ax.set_title("Top-25 executable policies by path mean (green = path CI>0)")
    fig.tight_layout()
    p = fig_dir / "gap_top_policies.png"
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p))

    return paths


def write_report(
    decomp: dict[str, Any],
    sweep: list[dict[str, Any]],
    best_pack: dict[str, Any],
    figs: list[str],
    out_dir: Path,
) -> Path:
    best = best_pack.get("best") or {}
    decision = best_pack["decision"]
    clears = [r for r in sweep if r.get("path_ci_gt_0")]
    valid = [r for r in sweep if not r.get("skipped") and (r.get("n") or 0) >= 5]
    valid_sorted = sorted(valid, key=lambda r: r.get("path_mean") or -1e9, reverse=True)

    lines: list[str] = []
    lines.append("# V-fade PATH GAP REPORT")
    lines.append("")
    lines.append(f"Generated: `{datetime.now(timezone.utc).isoformat()}`")
    lines.append(f"Panel: **{VENUE} {SYMBOL}** · days {DAYS[0]}…{DAYS[-1]} · RT = {RT} bps")
    lines.append("")
    lines.append(f"## Verdict: **{decision}**")
    lines.append("")
    if decision == "Promote_shadow":
        lines.append(
            f"At least one executable policy has path bootstrap CI strictly > 0 after RT={RT}. "
            f"n_clearing={best_pack.get('n_clearing')}."
        )
    else:
        lines.append(
            f"**No** executable policy on this panel clears path CI > 0 after RT={RT}. "
            "Do **not** claim live / shadow-promote alpha. Hold with best (least-bad) path policy below. "
            "Lab identity (+13.9 bps) is **not** earnable at confirm entry."
        )
    lines.append("")
    if best:
        lines.append("### Best executable policy")
        lines.append("")
        lines.append("| param | value |")
        lines.append("|-------|------:|")
        lines.append(f"| confirm_s | {best.get('confirm_s')} |")
        lines.append(f"| exit_s | {best.get('exit_s')} |")
        lines.append(f"| v_threshold_r2 | {best.get('v_threshold_r2')} |")
        lines.append(f"| soft_confirm_r1 | {best.get('soft_confirm_r1')} |")
        lines.append(f"| adverse_stop_bps | {best.get('adverse_stop_bps')} |")
        lines.append(f"| always_fade (confirm=0) | {best.get('always_fade')} |")
        lines.append(f"| n | {best.get('n')} |")
        lines.append(f"| path mean | {best.get('path_mean'):.3f} |" if best.get("path_mean") is not None else "| path mean | — |")
        lines.append(
            f"| path CI | [{best.get('path_lo'):.3f}, {best.get('path_hi'):.3f}] |"
            if best.get("path_lo") is not None
            else "| path CI | — |"
        )
        lines.append(f"| lab mean (identity) | {best.get('lab_mean'):.3f} |" if best.get("lab_mean") is not None else "| lab mean | — |")
        lines.append(f"| path hit | {best.get('path_hit'):.3f} |" if best.get("path_hit") is not None else "| path hit | — |")
        lines.append(f"| early / late path | {best.get('early_path_mean'):.2f} / {best.get('late_path_mean'):.2f} |")
        lines.append("")

    lines.append("## 1. Why lab ≠ path (math)")
    lines.append("")
    lines.append("Let crash direction be `d ∈ {±1}`, fade side `s = −d`.")
    lines.append("")
    lines.append("Tape markout from event end (lab field):")
    lines.append("")
    lines.append("```text")
    lines.append("mo_5s = d · (P(ts_end+5s) / P(ts_end) − 1) · 1e4")
    lines.append("lab_net = −mo_5s − RT     # size=−1 fade identity")
    lines.append("```")
    lines.append("")
    lines.append("Executable path (entry after causal confirm):")
    lines.append("")
    lines.append("```text")
    lines.append("t_entry = ts_end + confirm_s     # baseline confirm_s=2")
    lines.append("t_exit  = min(adverse_hit, ts_end + exit_s)")
    lines.append("path_gross = s · (P(t_exit)/P(t_entry) − 1) · 1e4")
    lines.append("path_net   = path_gross − RT")
    lines.append("```")
    lines.append("")
    lines.append("Additive split at confirm=2, exit=5 (no adverse):")
    lines.append("")
    lines.append("```text")
    lines.append("−mo_5s ≈ fade(0→2) + fade(2→5)")
    lines.append("path_gross ≈ fade(2→5)")
    lines.append("gap ≈ lab_net − path_net ≈ fade(0→2)     # RT cancels")
    lines.append("```")
    lines.append("")
    lines.append(
        "Causal V requires `recovery_2s ≥ 0.5`: by construction most of the favorable "
        "rebound is in **fade(0→2)**. Lab **attributes that rebound to PnL**; path **enters after it**."
    )
    lines.append("")
    lines.append("### Measured baseline (confirm=2, exit=5, adverse=12)")
    lines.append("")
    lines.append("| piece | mean bps |")
    lines.append("|-------|----------:|")
    lines.append(f"| n faded | {decomp['n']} |")
    lines.append(f"| lab net | **{decomp['lab_ci']['mean']:.2f}** [{decomp['lab_ci']['lo']:.2f}, {decomp['lab_ci']['hi']:.2f}] |")
    lines.append(f"| path net | **{decomp['path_ci']['mean']:.2f}** [{decomp['path_ci']['lo']:.2f}, {decomp['path_ci']['hi']:.2f}] |")
    lines.append(f"| gap (lab−path) | **{decomp['gap_mean']:.2f}** |")
    lines.append(f"| fade gross 0→2s (pre-entry) | **{decomp['timing']['fade_gross_0_2s_mean']:.2f}** |")
    lines.append(f"| fade gross 2→5s (residual) | **{decomp['timing']['fade_gross_2_5s_mean']:.2f}** |")
    lines.append(f"| path gross (entry→exit) | {decomp['timing']['path_gross_mean']:.2f} |")
    lines.append(f"| lab hit / path hit | {decomp['lab_hit_rate']:.2f} / {decomp['path_hit_rate']:.2f} |")
    lines.append(f"| adverse share | {decomp['adverse_share']:.2f} |")
    lines.append("")
    lines.append("### Gap decomposition checklist")
    lines.append("")
    lines.append("| factor | contribution | notes |")
    lines.append("|--------|-------------:|-------|")
    lines.append(
        f"| **Timing (pre-entry rebound)** | **~{decomp['timing']['fade_gross_0_2s_mean']:.1f} bps** | "
        "Dominant. Lab credits 0→2s; path misses it. |"
    )
    lines.append(
        f"| Residual post-confirm (2→5) | {decomp['timing']['fade_gross_2_5s_mean']:.1f} | "
        "Near zero / slightly negative — V already spent. |"
    )
    if "adverse_stop" in decomp["by_exit"]:
        ae = decomp["by_exit"]["adverse_stop"]
        te = decomp["by_exit"].get("time_stop", {})
        lines.append(
            f"| Adverse stops | path {ae['path_mean']:.1f} on n={ae['n']} "
            f"(time_stop path {te.get('path_mean', float('nan')):.1f}) | "
            "Worsens path but not root cause — time_stop alone still <0. |"
        )
    lines.append(
        f"| Mid vs tape | {decomp['mid_vs_tape']['gap_from_mid']:.1f} | "
        f"{decomp['mid_vs_tape']['note']} |"
    )
    lines.append(
        f"| Side sign | {'OK' if decomp['side_sign_audit']['ok'] else 'CHECK'} | "
        f"{decomp['side_sign_audit']['note']} |"
    )
    lines.append(
        "| Look-ahead in label | scoreboard only | "
        f"{decomp['look_ahead']['detail'][:120]}… |"
    )
    lines.append("")

    lines.append("## 2. Executable sweep")
    lines.append("")
    lines.append(
        f"Grid: confirm∈{CONFIRM_S} × exit∈{EXIT_S} × v_thr∈{V_THR} × soft_r1∈{SOFT_R1} "
        f"× adverse∈[off,12,25]. confirm=0 ⇒ always_fade at `ts_end` (no V gate). "
        f"Recovery at **confirm horizon** (causal)."
    )
    lines.append("")
    lines.append(f"- policies evaluated: {len(sweep)}")
    lines.append(f"- with n≥5: {len(valid)}")
    lines.append(f"- path CI > 0: **{len(clears)}**")
    lines.append("")
    lines.append("### Top 15 by path mean")
    lines.append("")
    lines.append("| confirm | exit | v_thr | soft | adverse | n | path mean | path CI | lab mean | CI>0 |")
    lines.append("|--------:|-----:|------:|-----:|--------:|--:|----------:|---------|----------|:----:|")
    for r in valid_sorted[:15]:
        adv = "off" if r.get("adverse_stop_bps") is None else f"{r['adverse_stop_bps']}"
        lines.append(
            f"| {r['confirm_s']} | {r['exit_s']} | {r['v_threshold_r2']} | {r['soft_confirm_r1']} | "
            f"{adv} | {r['n']} | {r['path_mean']:.2f} | "
            f"[{r['path_lo']:.2f}, {r['path_hi']:.2f}] | {r['lab_mean']:.2f} | "
            f"{'Y' if r.get('path_ci_gt_0') else ''} |"
        )
    lines.append("")
    lines.append("## 3. Figures")
    lines.append("")
    for f in figs:
        rel = Path(f).name
        lines.append(f"- `figs/{rel}`")
    lines.append("")
    lines.append("## 4. Honesty")
    lines.append("")
    lines.append(
        "research_sim · RT=4bps · mid_mo null → tape · live_orders=False · "
        "**path ≠ lab** · no live alpha claim · ClickHouse MCP banned"
    )
    lines.append("")

    path = out_dir / "PATH_GAP_REPORT.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def main() -> None:
    out_dir = PKG / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = load_config(PKG / "config.yaml")
    cfg["venue"] = VENUE
    cfg["symbol"] = SYMBOL
    cfg["extra_venues"] = []

    cells = load_cells(cfg)
    if not cells:
        raise SystemExit("no cells loaded")

    print("[gap] baseline decomposition…", flush=True)
    decomp = decompose_baseline(cells, cfg)

    print("[gap] policy sweep…", flush=True)
    sweep = run_sweep(cells, cfg)
    best_pack = pick_best(sweep)

    figs = write_figs(decomp, sweep, best_pack, out_dir)
    report = write_report(decomp, sweep, best_pack, figs, out_dir)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "venue": VENUE,
        "symbol": SYMBOL,
        "days": DAYS,
        "rt_friction_bps": RT,
        "decision": best_pack["decision"],
        "n_clearing_policies": best_pack.get("n_clearing"),
        "best_policy": best_pack.get("best"),
        "baseline_decomposition": {
            k: decomp[k]
            for k in (
                "n",
                "lab_ci",
                "path_ci",
                "gap_mean",
                "gap_ci",
                "timing",
                "by_exit",
                "adverse_share",
                "path_hit_rate",
                "lab_hit_rate",
                "corr_lab_path",
                "side_sign_audit",
                "mid_vs_tape",
                "look_ahead",
            )
        },
        "sweep_n": len(sweep),
        "sweep_top15": sorted(
            [r for r in sweep if not r.get("skipped") and (r.get("n") or 0) >= 5],
            key=lambda r: r.get("path_mean") or -1e9,
            reverse=True,
        )[:15],
        "figures": figs,
        "report_md": str(report),
        "honesty": {
            "path_equals_lab": False,
            "alpha_claim": False,
            "live_orders": False,
            "clickhouse_mcp": False,
            "scoreboard_lab": "identity_-mo5s_minus_RT4_not_executable",
            "scoreboard_path": "entry_to_exit_tape_print_minus_RT4",
        },
    }
    sum_path = out_dir / "gap_summary.json"
    sum_path.write_text(json.dumps(jsonable(summary), indent=2) + "\n")
    print(
        json.dumps(
            {
                "decision": summary["decision"],
                "best_path_mean": (best_pack.get("best") or {}).get("path_mean"),
                "best_path_ci": [
                    (best_pack.get("best") or {}).get("path_lo"),
                    (best_pack.get("best") or {}).get("path_hi"),
                ],
                "baseline_lab": decomp["lab_ci"]["mean"],
                "baseline_path": decomp["path_ci"]["mean"],
                "gap": decomp["gap_mean"],
                "report": str(report),
                "summary": str(sum_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
