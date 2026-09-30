"""Daily risk report (markdown + HTML) and key PNGs."""

from __future__ import annotations

import html
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .actions import jsonable

NS = 1_000_000_000


def _mean(a: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64)
    a = a[np.isfinite(a)]
    return float(a.mean()) if a.size else float("nan")


def _strat_block(r: dict[str, Any]) -> dict[str, Any]:
    cw = r.get("crash_window") or {}
    return {
        "final_equity_bps": r.get("final_equity_bps"),
        "max_dd_bps": r.get("max_dd_bps"),
        "n_fills": r.get("n_fills"),
        "final_inv": r.get("final_inv"),
        "fills_by_regime": r.get("fills_by_regime"),
        "crash_window": {
            "n_fills_in_fire": cw.get("n_fills_in_fire"),
            "qty_in_fire": cw.get("qty_in_fire"),
            "equity_incr_fire_bps": cw.get("equity_incr_fire_bps"),
            "peak_abs_inv_fire": cw.get("peak_abs_inv_fire"),
        },
    }


def summarize_day(
    cell: dict[str, Any],
    shadow: dict[str, Any],
    action_records: list[dict[str, Any]],
    *,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    ev = cell.get("events") or {}
    tiers = [str(t) for t in list(ev.get("tier", []))]
    tier_counts = dict(Counter(tiers))
    fire = [r for r in action_records if r.get("kind") == "ladder_fire"]
    observe = [r for r in action_records if r.get("kind") == "ladder_observe"]
    nanex_esc = [r for r in fire if r.get("escalate") == "nanex_intersect_ssm"]

    mo5 = np.asarray(ev.get("mo_5s", []), dtype=np.float64)
    fire_mo = np.asarray([r["mo_5s"] for r in fire if r.get("mo_5s") is not None], dtype=np.float64)
    labels = [str(x) for x in list(ev.get("recovery_label", []))]
    fire_labels = [str(r.get("recovery_label")) for r in fire]
    fp_v = (
        float(np.mean([1.0 if x == "v_recovery" else 0.0 for x in fire_labels]))
        if fire_labels
        else float("nan")
    )
    share_v_all = (
        float(np.mean([1.0 if x == "v_recovery" else 0.0 for x in labels])) if labels else float("nan")
    )

    results = shadow.get("results") or {}
    ladder = results.get("kill_ladder_maker") or {}
    baseline = results.get("baseline_maker") or {}
    confirm = results.get("ladder_plus_confirm_before_restore") or {}
    stack = results.get("risk_gate_stack") or {}

    adverse_fire = float(np.mean(fire_mo > 0)) if fire_mo.size else float("nan")
    fire_mo_fin = fire_mo[np.isfinite(fire_mo)]
    mo5_fin = mo5[np.isfinite(mo5)]
    abs_mo_fire = float(np.mean(np.abs(fire_mo_fin))) if fire_mo_fin.size else float("nan")
    abs_mo_all = float(np.mean(np.abs(mo5_fin))) if mo5_fin.size else float("nan")
    delta = shadow.get("delta_vs_baseline") or {}
    delta_c = shadow.get("delta_confirm_vs_baseline")
    delta_s = shadow.get("delta_stack_vs_baseline")

    # Avoided adverse exposure proxy: −Δ fire fills × mean |mo@5s| among fire (bps·fill)
    avoided_adverse = float("nan")
    if delta_s is not None and np.isfinite(abs_mo_fire):
        avoided_adverse = float(-int(delta_s.get("delta_fills_in_fire") or 0)) * abs_mo_fire

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "day": cell.get("day"),
        "symbol": cell.get("symbol"),
        "venue": cell.get("venue"),
        "complete": cell.get("complete"),
        "n_trades": cell.get("n_trades"),
        "ssm_raw_n": cell.get("ssm_raw_n"),
        "ssm_10_n": cell.get("ssm_10_n"),
        "nanex_n": cell.get("nanex_n"),
        "nanex_nested_n": cell.get("nanex_nested_n"),
        "nanex_ssm_precision": cell.get("nanex_ssm_precision"),
        "sigma_m_median": cell.get("sigma_m_median"),
        "ladder_breaks": cell.get("ladder_breaks"),
        "tier_counts": tier_counts,
        "n_observe": len(observe),
        "n_fire": len(fire),
        "n_nanex_escalate": len(nanex_esc),
        "mo5_all_mean": _mean(mo5),
        "mo5_fire_mean": _mean(fire_mo),
        "abs_mo5_all_mean": abs_mo_all,
        "abs_mo5_fire_mean": abs_mo_fire,
        "frac_adverse_mo_fire": adverse_fire,
        "fp_v_recovery_rate_among_fire": fp_v,
        "share_v_all_gated": share_v_all,
        "shadow": {
            "book": shadow.get("book"),
            "fill_model": shadow.get("fill_model"),
            "n_trades_sim": shadow.get("n_trades_sim"),
            "max_inventory": shadow.get("max_inventory"),
            "clock_tier_counts": shadow.get("clock_tier_counts"),
            "stack_regime_counts": shadow.get("stack_regime_counts"),
            "n_fire_pause_prints": shadow.get("n_fire_pause_prints"),
            "n_nest_hard_prints": shadow.get("n_nest_hard_prints"),
            "baseline": _strat_block(baseline),
            "kill_ladder": _strat_block(ladder),
            "ladder_plus_confirm": _strat_block(confirm) if confirm else None,
            "risk_gate_stack": _strat_block(stack) if stack else None,
            "delta_vs_baseline": delta,
            "delta_confirm_vs_baseline": delta_c,
            "delta_stack_vs_baseline": delta_s,
            "avoided_adverse_mo_proxy": avoided_adverse,
        },
        "config": {
            "friction_bps": cfg.get("friction_bps"),
            "max_inventory": cfg.get("max_inventory"),
            "gate": cfg.get("gate"),
            "z_star": cfg.get("z_star"),
            "class": cfg.get("class"),
            "mode": cfg.get("mode"),
            "fill_model": shadow.get("fill_model"),
            "nest_hard_pause": cfg.get("nest_hard_pause", True),
            "fire_pause_5m_s": cfg.get("fire_pause_5m_s", 300.0),
            "run_risk_gate_stack": cfg.get("run_risk_gate_stack", True),
        },
        "honesty": {
            "overlay": "risk_policy_not_pnl_alpha",
            "fills": "shadow_tape_print_only",
            "live_orders": False,
            "clickhouse_mcp": False,
            "max_inventory_note": (
                "research soft-cap so crash-window ladder can bind; "
                "±2 coins historically nullified fire fills"
            ),
            "fill_model_note": (
                "tape-proxy when warehouse BBO median Δt > stale_book_s; "
                "not sub-second L2 queue-position"
            ),
            "overlay_nullified_in_fire": bool(delta.get("overlay_nullified_in_fire")),
            "stack_nullified_in_fire": bool((delta_s or {}).get("overlay_nullified_in_fire"))
            if delta_s
            else None,
            "scoreboard_note": (
                "RISK_GATE_STACK Δ fills / Δ adverse-mo proxy = risk throttle scoreboard, "
                "not tradable alpha"
            ),
        },
    }


def write_figs(shadow: dict[str, Any], out_dir: Path, *, day: str, symbol: str, venue: str) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig_dir = out_dir / "figs"
    fig_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    results = shadow.get("results") or {}
    ladder = results.get("kill_ladder_maker")
    baseline = results.get("baseline_maker")
    confirm = results.get("ladder_plus_confirm_before_restore")
    if not ladder:
        return paths

    ts = np.asarray(ladder["ts"], dtype=np.int64)
    t0 = float(ts[0]) if ts.size else 0.0
    t_h = (ts.astype(np.float64) - t0) / NS / 3600.0

    # 1) price + regimes + fills
    fig, ax = plt.subplots(figsize=(11, 4.2))
    ax.plot(t_h, ladder["px"], color="#2c3e50", lw=0.7, label="trade px")
    reg = np.asarray(ladder["regime"], dtype=object)
    for label, color, alpha in (
        ("halt", "#e74c3c", 0.25),
        ("size_cap", "#e67e22", 0.18),
        ("widen", "#f1c40f", 0.12),
    ):
        m = reg == label
        if not m.any():
            continue
        idx = np.where(m)[0]
        breaks = np.where(np.diff(idx) > 1)[0]
        starts = np.r_[idx[0], idx[breaks + 1]]
        ends = np.r_[idx[breaks], idx[-1]]
        for a, b in zip(starts, ends):
            ax.axvspan(t_h[a], t_h[b], color=color, alpha=alpha, lw=0)
    fts = np.asarray(ladder.get("fill_ts", []), dtype=np.int64)
    fpx = np.asarray(ladder.get("fill_px", []), dtype=np.float64)
    fside = np.asarray(ladder.get("fill_side", []), dtype=np.int64)
    fi = np.asarray(ladder.get("fill_i", []), dtype=np.int64)
    if fts.size:
        if fi.size == fts.size and fi.size and int(fi.max()) < ts.size:
            ft = (ts[fi].astype(np.float64) - t0) / NS / 3600.0
            fy = np.asarray(ladder["px"], dtype=np.float64)[fi]
        else:
            ft = (fts.astype(np.float64) - t0) / NS / 3600.0
            fy = fpx
        ax.scatter(ft[fside > 0], fy[fside > 0], s=8, c="#27ae60", label="buy fill", zorder=5)
        ax.scatter(ft[fside < 0], fy[fside < 0], s=8, c="#c0392b", label="sell fill", zorder=5)
    ax.set_title(f"{day} {venue} {symbol} — price + ladder shades + shadow fills")
    ax.legend(fontsize=7, loc="best")
    p = fig_dir / "price_regimes_fills.png"
    fig.tight_layout()
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p))

    # 2) equity overlay
    fig, ax = plt.subplots(figsize=(11, 3.8))
    if baseline:
        ax.plot(t_h, baseline["equity_bps"], label="baseline_maker", color="#7f8c8d", lw=1.0)
    ax.plot(t_h, ladder["equity_bps"], label="kill_ladder_maker", color="#c45c26", lw=1.2)
    if confirm and "equity_bps" in confirm:
        ax.plot(
            t_h,
            confirm["equity_bps"],
            label="ladder+confirm",
            color="#2980b9",
            lw=1.0,
            ls="--",
        )
    stack = results.get("risk_gate_stack")
    if stack and "equity_bps" in stack:
        ax.plot(
            t_h,
            stack["equity_bps"],
            label="risk_gate_stack",
            color="#1a7a4c",
            lw=1.3,
        )
    ax.axhline(0, color="k", lw=0.6)
    ax.set_ylabel("equity (bps)")
    ax.set_title("Shadow marked equity (friction haircut) — risk-policy, not PnL alpha")
    ax.legend(fontsize=8)
    p = fig_dir / "equity_overlay.png"
    fig.tight_layout()
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p))

    # 3) inventory
    fig, ax = plt.subplots(figsize=(11, 3.2))
    if baseline:
        ax.plot(t_h, baseline["inventory"], label="baseline", color="#7f8c8d", lw=1.0)
    ax.plot(t_h, ladder["inventory"], label="kill_ladder", color="#3d5a5b", lw=1.1)
    if confirm and "inventory" in confirm:
        ax.plot(t_h, confirm["inventory"], label="ladder+confirm", color="#2980b9", lw=1.0, ls="--")
    if stack and "inventory" in stack:
        ax.plot(t_h, stack["inventory"], label="risk_gate_stack", color="#1a7a4c", lw=1.1)
    ax.set_ylabel("coins")
    ax.set_title("Inventory path")
    ax.legend(fontsize=8)
    p = fig_dir / "inventory_path.png"
    fig.tight_layout()
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p))

    # 4) tier pie / bar from clock
    counts = shadow.get("clock_tier_counts") or {}
    fig, ax = plt.subplots(figsize=(6, 3.5))
    keys = [k for k in ("observe", "widen", "size_cap", "halt") if counts.get(k, 0) > 0]
    vals = [counts.get(k, 0) for k in keys]
    ax.bar(keys, vals, color=["#95a5a6", "#f1c40f", "#e67e22", "#e74c3c"][: len(keys)])
    ax.set_title("Tape prints under ladder tier")
    ax.set_ylabel("n prints")
    p = fig_dir / "tier_print_counts.png"
    fig.tight_layout()
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p))

    # 5) crash-window fill comparison
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    names = ["baseline", "kill_ladder"]
    fire_fills = [
        int((baseline.get("crash_window") or {}).get("n_fills_in_fire") or 0),
        int((ladder.get("crash_window") or {}).get("n_fills_in_fire") or 0),
    ]
    colors = ["#7f8c8d", "#c45c26"]
    if confirm:
        names.append("ladder+confirm")
        fire_fills.append(int((confirm.get("crash_window") or {}).get("n_fills_in_fire") or 0))
        colors.append("#2980b9")
    if stack:
        names.append("risk_gate_stack")
        fire_fills.append(int((stack.get("crash_window") or {}).get("n_fills_in_fire") or 0))
        colors.append("#1a7a4c")
    ax.bar(names, fire_fills, color=colors[: len(names)])
    ax.set_ylabel("fills in fire windows")
    ax.set_title("Crash-window shadow fills (widen/size_cap/halt) — baseline vs stack")
    p = fig_dir / "crash_window_fills.png"
    fig.tight_layout()
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p))

    # 6) stack regime print counts (nest / fire_pause)
    stack_counts = shadow.get("stack_regime_counts") or {}
    if stack_counts:
        fig, ax = plt.subplots(figsize=(7.5, 3.6))
        skeys = [
            k
            for k in (
                "observe",
                "widen",
                "size_cap",
                "halt",
                "nest_hard_pause",
                "fire_pause_5m",
            )
            if stack_counts.get(k, 0) > 0
        ]
        svals = [stack_counts.get(k, 0) for k in skeys]
        scolors = {
            "observe": "#95a5a6",
            "widen": "#f1c40f",
            "size_cap": "#e67e22",
            "halt": "#e74c3c",
            "nest_hard_pause": "#8e44ad",
            "fire_pause_5m": "#16a085",
        }
        ax.bar(skeys, svals, color=[scolors.get(k, "#34495e") for k in skeys])
        ax.set_title("RISK_GATE_STACK effective regimes (prints)")
        ax.set_ylabel("n prints")
        ax.tick_params(axis="x", rotation=20)
        p = fig_dir / "stack_regime_counts.png"
        fig.tight_layout()
        fig.savefig(p, dpi=140, bbox_inches="tight")
        plt.close(fig)
        paths.append(str(p))

    return paths


def write_markdown(summary: dict[str, Any], fig_paths: list[str], path: Path) -> Path:
    sh = summary.get("shadow") or {}
    kl = sh.get("kill_ladder") or {}
    bl = sh.get("baseline") or {}
    conf = sh.get("ladder_plus_confirm") or {}
    stack = sh.get("risk_gate_stack") or {}
    delta = sh.get("delta_vs_baseline") or {}
    delta_c = sh.get("delta_confirm_vs_baseline") or {}
    delta_s = sh.get("delta_stack_vs_baseline") or {}
    fp = summary.get("fp_v_recovery_rate_among_fire")
    fp_s = f"{fp:.3f}" if isinstance(fp, float) and np.isfinite(fp) else str(fp)
    nullified = (summary.get("honesty") or {}).get("overlay_nullified_in_fire")
    stack_null = (summary.get("honesty") or {}).get("stack_nullified_in_fire")
    lines = [
        f"# Paper harness risk report — {summary.get('day')} {summary.get('venue')} {summary.get('symbol')}",
        "",
        f"Generated: `{summary.get('generated_at')}`",
        "",
        "**Class:** risk-policy overlay (not PnL alpha). **Fills:** shadow only — no live orders.",
        "",
        "## Detection",
        "",
        f"- Complete day: **{summary.get('complete')}** · trades: **{summary.get('n_trades')}**",
        f"- SSM raw / gated(10bps·ic5): **{summary.get('ssm_raw_n')}** / **{summary.get('ssm_10_n')}**",
        f"- Nanex n / nested∩SSM: **{summary.get('nanex_n')}** / **{summary.get('nanex_nested_n')}** "
        f"(prec≈{summary.get('nanex_ssm_precision')})",
        f"- σ_m median: `{summary.get('sigma_m_median')}` · ladder breaks: `{summary.get('ladder_breaks')}`",
        "",
        "## Ladder fires",
        "",
        f"- Tier counts: `{summary.get('tier_counts')}`",
        f"- Observe / fire / Nanex escalate: "
        f"**{summary.get('n_observe')}** / **{summary.get('n_fire')}** / **{summary.get('n_nanex_escalate')}**",
        f"- Mean mo@5s all / fire: "
        f"`{summary.get('mo5_all_mean')}` / `{summary.get('mo5_fire_mean')}` bps",
        f"- Mean |mo@5s| all / fire: "
        f"`{summary.get('abs_mo5_all_mean')}` / `{summary.get('abs_mo5_fire_mean')}` bps",
        f"- Frac adverse (mo>0) among fire: `{summary.get('frac_adverse_mo_fire')}`",
        f"- FP V-recovery rate among fire: **{fp_s}**",
        f"- Share V all gated: `{summary.get('share_v_all_gated')}`",
        "",
        "## Shadow fills (desk risk metrics)",
        "",
        f"- Fill model: `{sh.get('fill_model')}` · max_inventory (research soft-cap): "
        f"**{sh.get('max_inventory')}**",
        f"- Book source: `{sh.get('book')}`",
        f"- Sim prints: **{sh.get('n_trades_sim')}** · clock tier print counts: `{sh.get('clock_tier_counts')}`",
        f"- Stack regime counts: `{sh.get('stack_regime_counts')}` · "
        f"fire_pause prints `{sh.get('n_fire_pause_prints')}` · nest prints `{sh.get('n_nest_hard_prints')}`",
        f"- Baseline: equity `{bl.get('final_equity_bps')}` bps · dd `{bl.get('max_dd_bps')}` · "
        f"fills `{bl.get('n_fills')}` · inv `{bl.get('final_inv')}` · "
        f"fire_fills `{ (bl.get('crash_window') or {}).get('n_fills_in_fire') }`",
        f"- Kill-ladder: equity `{kl.get('final_equity_bps')}` bps · dd `{kl.get('max_dd_bps')}` · "
        f"fills `{kl.get('n_fills')}` · inv `{kl.get('final_inv')}` · "
        f"fire_fills `{ (kl.get('crash_window') or {}).get('n_fills_in_fire') }`",
        f"- **Δ ladder−baseline:** equity `{delta.get('delta_equity_bps')}` bps · "
        f"dd `{delta.get('delta_max_dd_bps')}` · fills `{delta.get('delta_n_fills')}` · "
        f"fire_fills `{delta.get('delta_fills_in_fire')}` · "
        f"fire equity incr `{delta.get('delta_equity_incr_fire_bps')}` bps",
        f"- Overlay nullified in fire windows: **{nullified}**",
    ]
    if conf:
        lines.append(
            f"- Ladder+confirm: equity `{conf.get('final_equity_bps')}` bps · "
            f"dd `{conf.get('max_dd_bps')}` · fills `{conf.get('n_fills')}` · "
            f"fire_fills `{(conf.get('crash_window') or {}).get('n_fills_in_fire')}` · "
            f"Δequity `{delta_c.get('delta_equity_bps')}` bps"
        )
    if stack:
        lines += [
            "",
            "## RISK_GATE_STACK (baseline vs full stack)",
            "",
            f"- Stack: equity `{stack.get('final_equity_bps')}` bps · dd `{stack.get('max_dd_bps')}` · "
            f"fills `{stack.get('n_fills')}` · "
            f"fire_fills `{(stack.get('crash_window') or {}).get('n_fills_in_fire')}`",
            f"- **Δ stack−baseline:** equity `{delta_s.get('delta_equity_bps')}` bps · "
            f"fills `{delta_s.get('delta_n_fills')}` · "
            f"fire_fills `{delta_s.get('delta_fills_in_fire')}` · "
            f"qty_fire `{delta_s.get('delta_qty_in_fire')}` · "
            f"fire equity incr `{delta_s.get('delta_equity_incr_fire_bps')}` bps",
            f"- Avoided adverse-mo proxy (−Δfire_fills × mean|mo@5s|fire): "
            f"`{sh.get('avoided_adverse_mo_proxy')}`",
            f"- Stack nullified in fire: **{stack_null}**",
            "",
            "Honesty: scoreboard is risk throttle (cut size / pause under fire·nest), "
            "**not** tradable alpha.",
        ]
    lines += [
        "",
        "## Figures",
        "",
    ]
    for fp_path in fig_paths:
        rel = Path(fp_path).name
        lines.append(f"- `figs/{rel}`")
    lines += [
        "",
        "## Honesty",
        "",
        f"- `{summary.get('honesty')}`",
        "",
        "Labels: marked maker equity is a **risk overlay scoreboard**, not tradable PnL. "
        "Tape-proxy fill eligibility when warehouse BBO is minute-stale. "
        "Promote-as-risk-policy still rests on event-study Δ|mo| (kill_ladder package), "
        "not on this shadow equity clearing a CI.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path


def write_html(summary: dict[str, Any], fig_paths: list[str], path: Path) -> Path:
    title = (
        f"Paper harness — {summary.get('day')} "
        f"{summary.get('venue')} {summary.get('symbol')}"
    )
    imgs = "\n".join(
        f'<p><img src="figs/{html.escape(Path(p).name)}" '
        f'style="max-width:100%;border:1px solid #ddd"/></p>'
        for p in fig_paths
    )
    sh = summary.get("shadow") or {}
    delta = sh.get("delta_vs_baseline") or {}
    delta_s = sh.get("delta_stack_vs_baseline") or {}
    body = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/><title>{html.escape(title)}</title>
<style>
body{{font-family:ui-sans-serif,system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;color:#222}}
code,pre{{background:#f4f4f4;padding:.1rem .3rem;border-radius:3px}}
.badge{{display:inline-block;background:#3d5a5b;color:#fff;padding:.15rem .5rem;border-radius:3px;font-size:.85rem}}
table{{border-collapse:collapse;width:100%;margin:1rem 0}}
td,th{{border:1px solid #ddd;padding:.4rem .6rem;text-align:left}}
.warn{{color:#a04000}}
</style></head><body>
<h1>{html.escape(title)}</h1>
<p><span class="badge">paper · risk-policy · shadow fills only</span></p>
<p>Generated: <code>{html.escape(str(summary.get('generated_at')))}</code></p>
<h2>Snapshot</h2>
<table>
<tr><th>Gated events</th><td>{summary.get('ssm_10_n')}</td></tr>
<tr><th>Fire / observe</th><td>{summary.get('n_fire')} / {summary.get('n_observe')}</td></tr>
<tr><th>Nanex escalate</th><td>{summary.get('n_nanex_escalate')}</td></tr>
<tr><th>FP V-recovery @ fire</th><td>{summary.get('fp_v_recovery_rate_among_fire')}</td></tr>
<tr><th>mo@5s fire mean</th><td>{summary.get('mo5_fire_mean')} bps</td></tr>
<tr><th>|mo@5s| fire mean</th><td>{summary.get('abs_mo5_fire_mean')} bps</td></tr>
<tr><th>Fill model</th><td><code>{html.escape(str(sh.get('fill_model')))}</code></td></tr>
<tr><th>Δ equity (ladder−base)</th><td>{delta.get('delta_equity_bps')} bps</td></tr>
<tr><th>Δ fire fills (ladder)</th><td>{delta.get('delta_fills_in_fire')}</td></tr>
<tr><th>Δ equity (stack−base)</th><td>{delta_s.get('delta_equity_bps')}</td></tr>
<tr><th>Δ fire fills (stack)</th><td>{delta_s.get('delta_fills_in_fire')}</td></tr>
<tr><th>Avoided adverse-mo proxy</th><td>{sh.get('avoided_adverse_mo_proxy')}</td></tr>
<tr><th>Overlay nullified?</th><td class="{'warn' if delta.get('overlay_nullified_in_fire') else ''}">{delta.get('overlay_nullified_in_fire')}</td></tr>
<tr><th>Ladder equity bps</th><td>{(sh.get('kill_ladder') or {}).get('final_equity_bps')}</td></tr>
<tr><th>Stack equity bps</th><td>{(sh.get('risk_gate_stack') or {}).get('final_equity_bps')}</td></tr>
<tr><th>Book</th><td><code>{html.escape(str(sh.get('book')))}</code></td></tr>
</table>
<h2>Figures</h2>
{imgs}
<p><em>No live orders. ClickHouse MCP not used. RISK_GATE_STACK scoreboard — not tradable PnL.</em></p>
</body></html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def save_summary_json(summary: dict[str, Any], path: Path) -> Path:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(summary), indent=2) + "\n")
    return path


def write_rollup_markdown(rollup: dict[str, Any], path: Path) -> Path:
    """Multi-day desk rollup with honest risk labels — baseline vs RISK_GATE_STACK."""
    lines = [
        f"# Paper harness RISK_ROLLUP — {rollup.get('venue')} {rollup.get('symbol')}",
        "",
        f"Days: `{rollup.get('days')}` · ok: **{rollup.get('n_ok')}** / {len(rollup.get('days') or [])}",
        "",
        "**Class:** risk-policy shadow (not PnL alpha). Primary compare: **baseline vs full RISK_GATE_STACK** "
        "(TI-int-halt + nest_hard_pause + LR-fire-pause@5m).",
        "",
        "| Day | gated | fire | |mo|fire | Δfills stack | Δfire fills | avoided |mo| proxy | Δeq stack | nullified |",
        "|-----|------:|-----:|--------:|-------------:|------------:|----------------------:|----------:|:---------:|",
    ]
    for r in rollup.get("results") or []:
        if not r.get("ok"):
            lines.append(
                f"| {r.get('day')} | — | — | — | — | — | — | — | err=`{r.get('error') or r.get('skipped')}` |"
            )
            continue
        lines.append(
            f"| {r.get('day')} | {r.get('ssm_10_n')} | {r.get('n_fire')} | "
            f"{_fmt(r.get('abs_mo5_fire_mean'))} | {r.get('delta_stack_n_fills')} | "
            f"{r.get('delta_stack_fills_in_fire')} | {_fmt(r.get('avoided_adverse_mo_proxy'))} | "
            f"{_fmt(r.get('delta_stack_equity_bps'))} | {r.get('stack_nullified')} |"
        )
    pool = rollup.get("pool") or {}
    lines += [
        "",
        "## Pooled (ok days) — baseline vs full stack",
        "",
        f"- n_ok: **{pool.get('n')}**",
        f"- mean Δ fills (stack−base): `{pool.get('mean_delta_stack_n_fills')}`",
        f"- mean Δ fire fills: `{pool.get('mean_delta_stack_fills_in_fire')}`",
        f"- mean |mo@5s| among fire: `{pool.get('mean_abs_mo5_fire')}` bps",
        f"- mean avoided adverse-mo proxy (−Δfire_fills × |mo|fire): `{pool.get('mean_avoided_adverse_mo_proxy')}`",
        f"- mean Δ equity (stack−base): `{pool.get('mean_delta_stack_equity_bps')}` bps",
        f"- mean Δ fire equity incr: `{pool.get('mean_delta_stack_equity_incr_fire_bps')}` bps",
        f"- frac stack nullified: `{pool.get('frac_stack_nullified')}`",
        f"- total gated / fire: **{pool.get('sum_gated')}** / **{pool.get('sum_fire')}**",
        "",
        "### Ladder-only (reference)",
        "",
        f"- mean Δ equity ladder−base: `{pool.get('mean_delta_equity_bps')}` bps",
        f"- mean Δ fire fills ladder: `{pool.get('mean_delta_fills_in_fire')}`",
        "",
        "## Honesty",
        "",
        "- Shadow maker equity ≠ tradable edge; Promote-as-risk-policy is event-study Δ|mo|.",
        "- Avoided adverse-mo proxy is a **desk risk scoreboard**, not PnL alpha.",
        "- Tape-proxy fill model when warehouse BBO is stale vs ms tape.",
        "- max_inventory is a research soft-cap so crash windows are not inventory-dead.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path


def _fmt(x: Any) -> str:
    if x is None:
        return "—"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    if not np.isfinite(v):
        return "—"
    return f"{v:.2f}"
