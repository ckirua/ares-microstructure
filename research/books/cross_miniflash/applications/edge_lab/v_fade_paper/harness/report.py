"""RISK_REPORT + equity/path figures + summary for v_fade paper."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .causal import jsonable
from .kill import _boot_mean, evaluate_kills
from .shadow import HONESTY_BANNER, honesty_dict

NS = 1_000_000_000


def summarize(
    cell: dict[str, Any],
    sim: dict[str, Any],
    *,
    cfg: dict[str, Any],
    kills: dict[str, Any] | None = None,
) -> dict[str, Any]:
    trades = list(sim.get("trades") or [])
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
    vf = dict(cfg.get("v_fade") or {})
    n_boot = int(vf.get("n_boot", 800))
    lab_ci = _boot_mean(lab, seed=11, n_boot=n_boot)
    path_ci = _boot_mean(path, seed=12, n_boot=n_boot)

    if kills is None:
        kills = evaluate_kills(
            trades,
            cfg=cfg,
            live_orders=bool(cfg.get("live_orders", False)),
            sigma_m_floor_hit=cell.get("sigma_m_floor_hit"),
            detector_skip=bool(cell.get("skip")),
        )

    equity_lab = np.cumsum(lab) if lab.size else np.asarray([], dtype=np.float64)
    max_dd_lab = 0.0
    if equity_lab.size:
        peak = np.maximum.accumulate(equity_lab)
        max_dd_lab = float((equity_lab - peak).min())
    equity_path = np.cumsum(path) if path.size else np.asarray([], dtype=np.float64)
    max_dd_path = 0.0
    if equity_path.size:
        peak_p = np.maximum.accumulate(equity_path)
        max_dd_path = float((equity_path - peak_p).min())

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "day": cell.get("day"),
        "venue": cell.get("venue"),
        "symbol": cell.get("symbol"),
        "complete": cell.get("complete"),
        "n_trades_tape": cell.get("n_trades"),
        "ssm_raw_n": cell.get("ssm_raw_n"),
        "ssm_10_n": cell.get("ssm_10_n") or sim.get("n_events"),
        "nanex_n": cell.get("nanex_n"),
        "nanex_nested_n": cell.get("nanex_nested_n"),
        "sigma_m_median": cell.get("sigma_m_median"),
        "sigma_m_floor_hit": cell.get("sigma_m_floor_hit"),
        "class_counts": sim.get("class_counts"),
        "n_events": sim.get("n_events"),
        "n_faded": sim.get("n_faded"),
        "n_adverse_exits": sum(1 for t in trades if t.get("exit_reason") == "adverse_stop"),
        "n_time_stops": sum(1 for t in trades if t.get("exit_reason") == "time_stop"),
        "lab_pnl_net_bps": lab_ci,
        "path_pnl_net_bps": path_ci,
        "hit_rate_lab": float(np.mean(lab > 0)) if lab.size else float("nan"),
        "hit_rate_path": float(np.mean(path > 0)) if path.size else float("nan"),
        "final_equity_lab_bps": float(equity_lab[-1]) if equity_lab.size else 0.0,
        "max_dd_lab_bps": max_dd_lab,
        "final_equity_path_bps": float(equity_path[-1]) if equity_path.size else 0.0,
        "max_dd_path_bps": max_dd_path,
        "rt_friction_bps": sim.get("rt_friction_bps") or vf.get("rt_friction_bps", 4.0),
        "confirm_s": sim.get("confirm_s"),
        "exit_s": sim.get("exit_s"),
        "adverse_stop_bps": sim.get("adverse_stop_bps"),
        "entry_mode": sim.get("entry_mode") or vf.get("entry_mode"),
        "z_min": sim.get("z_min") if sim.get("z_min") is not None else vf.get("z_min"),
        "kills": kills,
        "config": {
            "gate": cfg.get("gate"),
            "z_star": cfg.get("z_star"),
            "v_fade": vf,
            "mode": cfg.get("mode"),
            "class": cfg.get("class"),
            "live_orders": bool(cfg.get("live_orders", False)),
        },
        "mode": "SHADOW_PAPER",
        "live_orders": False,
        "honesty": honesty_dict(),
    }


def write_figs(
    cell: dict[str, Any],
    sim: dict[str, Any],
    out_dir: Path,
    *,
    day: str,
    venue: str,
    symbol: str,
) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig_dir = out_dir / "figs"
    fig_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    ts = np.asarray(cell.get("ts"), dtype=np.int64)
    px = np.asarray(cell.get("px"), dtype=np.float64)
    trades = list(sim.get("trades") or [])

    if ts.size == 0:
        return paths

    t0 = float(ts[0])
    t_h = (ts.astype(np.float64) - t0) / NS / 3600.0

    # 1) price + entry/exit markers
    fig, ax = plt.subplots(figsize=(11, 4.2))
    ax.plot(t_h, px, color="#2c3e50", lw=0.6, label="tape px")
    for tr in trades:
        et = (float(tr["entry_ts"]) - t0) / NS / 3600.0
        xt = (float(tr["exit_ts"]) - t0) / NS / 3600.0
        color = "#27ae60" if (tr.get("lab_pnl_net_bps") or 0) > 0 else "#c0392b"
        ax.axvspan(et, xt, color=color, alpha=0.12, lw=0)
        ax.scatter([et], [tr["entry_px"]], s=28, c="#2980b9", zorder=5, marker="^")
        ax.scatter([xt], [tr["exit_px"]], s=28, c="#8e44ad", zorder=5, marker="v")
    ax.set_title(f"{day} {venue} {symbol} — V-fade entries/exits (tape)")
    ax.set_xlabel("hours from day start")
    ax.set_ylabel("price")
    ax.legend(fontsize=7, loc="best")
    p = fig_dir / "price_path_trades.png"
    fig.tight_layout()
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p))

    # 2) path equity (Promote scoreboard) + lab diagnostic
    from .equity import write_path_equity_figs

    mode = str(sim.get("entry_mode") or (trades[0].get("entry_mode") if trades else "severity_zend"))
    paths.extend(
        write_path_equity_figs(
            trades,
            fig_dir,
            label=f"{mode} path",
            venue=venue,
            symbol=symbol,
            stem="equity_path",
        )
    )
    lab = [float(t["lab_pnl_net_bps"]) for t in trades if t.get("lab_pnl_net_bps") is not None]
    fig, ax = plt.subplots(figsize=(11, 3.6))
    if lab:
        eq = np.cumsum(lab)
        ax.plot(np.arange(1, len(eq) + 1), eq, color="#1a5276", lw=1.4, marker="o", ms=3)
        ax.axhline(0, color="#7f8c8d", lw=0.8, ls="--")
        ax.set_xlabel("fade #")
        ax.set_ylabel("cum lab net bps")
    else:
        ax.text(0.5, 0.5, "no fades", ha="center", va="center", transform=ax.transAxes)
    ax.set_title(f"{day} {venue} {symbol} — cum lab PnL (−mo₅ₛ − RT4) diagnostic")
    p = fig_dir / "equity_lab.png"
    fig.tight_layout()
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p))

    # 3) path vs lab scatter
    fig, ax = plt.subplots(figsize=(5.5, 5.0))
    xs, ys = [], []
    for t in trades:
        if t.get("lab_pnl_net_bps") is None or t.get("path_pnl_net_bps") is None:
            continue
        xs.append(float(t["lab_pnl_net_bps"]))
        ys.append(float(t["path_pnl_net_bps"]))
    if xs:
        ax.scatter(xs, ys, s=22, c="#1a5276", alpha=0.75)
        lim = max(abs(min(xs + ys)), abs(max(xs + ys)), 1.0) * 1.1
        ax.plot([-lim, lim], [-lim, lim], color="#95a5a6", lw=0.8, ls="--")
        ax.axhline(0, color="#bdc3c7", lw=0.6)
        ax.axvline(0, color="#bdc3c7", lw=0.6)
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-lim, lim)
    ax.set_xlabel("lab net bps (−mo5s−RT)")
    ax.set_ylabel("path net bps (entry→exit)")
    ax.set_title("lab identity vs path PnL")
    p = fig_dir / "lab_vs_path.png"
    fig.tight_layout()
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p))

    return paths


def write_markdown(
    summary: dict[str, Any],
    fig_paths: list[str],
    trades: list[dict[str, Any]],
    path: Path,
) -> Path:
    kills = summary.get("kills") or {}
    flags = kills.get("flags") or {}
    lab = summary.get("lab_pnl_net_bps") or {}
    path_ci = summary.get("path_pnl_net_bps") or {}

    flag_rows = "\n".join(
        f"| `{k}` | **{'TRIP' if v else 'ok'}** |" for k, v in flags.items()
    )
    trade_rows = []
    for t in trades[:40]:
        trade_rows.append(
            f"| {t.get('event_i')} | {t.get('side_name')} | {t.get('exit_reason')} | "
            f"{_fmt(t.get('lab_pnl_net_bps'))} | {_fmt(t.get('path_pnl_net_bps'))} | "
            f"{_fmt(t.get('mo_5s'))} |"
        )
    more = ""
    if len(trades) > 40:
        more = f"\n_… {len(trades) - 40} more trades in `trades.jsonl`._\n"

    figs = "\n".join(f"- `{Path(p).name}`" for p in fig_paths) or "- _(none)_"

    md = f"""# V-fade SHADOW PAPER risk report — {summary.get('day')} {summary.get('venue')} {summary.get('symbol')}

Generated: `{summary.get('generated_at')}`

> {HONESTY_BANNER}

**Class:** directional causal V-fade (taker **SHADOW**). **Not** MM. **Not** live orders.
**Mode:** `SHADOW_PAPER` · `live_orders=false` · research_sim on real tape · RT={summary.get('rt_friction_bps')} bps · mid_mo null → tape `mo_5s` · fills = asof tape print.
**Confirm / exit:** {summary.get('confirm_s')}s / {summary.get('exit_s')}s · adverse_stop={summary.get('adverse_stop_bps')} bps

## Detection

- Complete day: **{summary.get('complete')}** · tape prints: **{summary.get('n_trades_tape')}**
- SSM raw / gated: **{summary.get('ssm_raw_n')}** / **{summary.get('ssm_10_n')}**
- Nanex n / nested∩SSM: **{summary.get('nanex_n')}** / **{summary.get('nanex_nested_n')}**
- Causal class counts: `{summary.get('class_counts')}`

## Fade scoreboard (lab identity)

- n_faded: **{summary.get('n_faded')}** · time_stop: {summary.get('n_time_stops')} · adverse: {summary.get('n_adverse_exits')}
- Lab net bps (−mo₅ₛ − RT): mean **{_fmt(lab.get('mean'))}** CI[{_fmt(lab.get('lo'))}, {_fmt(lab.get('hi'))}] n={lab.get('n')}
- Path net bps (entry→exit): mean **{_fmt(path_ci.get('mean'))}** CI[{_fmt(path_ci.get('lo'))}, {_fmt(path_ci.get('hi'))}]
- Hit-rate (lab / path): **{_fmt(summary.get('hit_rate_lab'))}** / **{_fmt(summary.get('hit_rate_path'))}**
- Cum **path** equity / max DD: **{_fmt(summary.get('final_equity_path_bps'))}** / **{_fmt(summary.get('max_dd_path_bps'))}** bps
- Cum lab equity / max DD (diagnostic): **{_fmt(summary.get('final_equity_lab_bps'))}** / **{_fmt(summary.get('max_dd_lab_bps'))}** bps
- Entry mode: `{summary.get('entry_mode')}` · z_min={_fmt(summary.get('z_min'))}

## Kill criteria (spec §7)

- Decision: **{kills.get('decision')}** · any_kill={kills.get('any_kill')}
- Early mean / late mean: {_fmt(kills.get('early_mean'))} / {_fmt(kills.get('late_mean'))}

| flag | status |
|------|--------|
{flag_rows or '| — | — |'}

## Trades (sample)

| event_i | side | exit | lab_net | path_net | mo_5s |
|---------|------|------|---------|----------|-------|
{chr(10).join(trade_rows) if trade_rows else '| — | — | — | — | — | — |'}
{more}

## Figures

{figs}

## Honesty

`{json.dumps(summary.get('honesty'), separators=(',', ':'))}`

Labels: lab scoreboard matches `exp_edge_lab.causal_fade_v_only` identity. Path PnL is tape entry@confirm → exit. Lab ≠ path when residual hold ≠ mo window. Neither is live fill PnL. `live_orders=False`. ClickHouse MCP banned.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(md)
    return path


def write_panel_markdown(rollup: dict[str, Any], path: Path) -> Path:
    kills = rollup.get("kills") or {}
    lab = rollup.get("lab_pnl_net_bps") or {}
    flags = kills.get("flags") or {}
    flag_rows = "\n".join(
        f"| `{k}` | **{'TRIP' if v else 'ok'}** |" for k, v in flags.items()
    )
    day_rows = []
    for r in rollup.get("results") or []:
        if not r.get("ok"):
            day_rows.append(
                f"| {r.get('day')} | FAIL | — | — | `{r.get('error') or r.get('skip')}` |"
            )
            continue
        ci = r.get("lab_pnl_net_bps") or {}
        day_rows.append(
            f"| {r.get('day')} | {r.get('n_faded')} | {_fmt(ci.get('mean'))} | "
            f"{_fmt(r.get('hit_rate_lab'))} | {r.get('out_dir')} |"
        )

    vf = ((rollup.get("config") or {}).get("v_fade")) or {}
    md = f"""# V-fade SHADOW PAPER RISK_ROLLUP

Generated: `{rollup.get('generated_at')}`

> {HONESTY_BANNER}

Venue×symbol: **{rollup.get('venue')} {rollup.get('symbol')}** · days={rollup.get('days')}
Extra venues: `{rollup.get('extra_venues')}`
**Mode:** `SHADOW_PAPER` · confirm/exit={_fmt(vf.get('confirm_s', rollup.get('confirm_s')))}s / {_fmt(vf.get('exit_s', rollup.get('exit_s')))}s · `live_orders=false`

## Panel scoreboard

- n_ok days: **{rollup.get('n_ok')}** · n_faded total: **{rollup.get('n_faded')}**
- Lab net bps (−mo₅ₛ − RT4): mean **{_fmt(lab.get('mean'))}** CI[{_fmt(lab.get('lo'))}, {_fmt(lab.get('hi'))}]
- Path net bps (entry@confirm→exit): mean **{_fmt((rollup.get('path_pnl_net_bps') or {}).get('mean'))}** CI[{_fmt((rollup.get('path_pnl_net_bps') or {}).get('lo'))}, {_fmt((rollup.get('path_pnl_net_bps') or {}).get('hi'))}]
- Early / late: {_fmt(rollup.get('early_mean'))} / {_fmt(rollup.get('late_mean'))}
- Hit-rate: **{_fmt(rollup.get('hit_rate'))}**
- Kill decision: **{kills.get('decision')}** · any_kill={kills.get('any_kill')}

> **Honesty:** lab identity matches edge_lab Promote. Path fills after confirm can differ (residual hold). mid_mo null → tape mo only. **Not live alpha.** Lab ≠ path.

| flag | status |
|------|--------|
{flag_rows or '| — | — |'}

## Per-day

| day | n_faded | mean lab net | hit | out |
|-----|---------|--------------|-----|-----|
{chr(10).join(day_rows)}

## Honesty

`{json.dumps(rollup.get('honesty'), separators=(',', ':'))}`

Reproduce: `python3 run_v_fade_paper.py --panel-days --extra-venues deribit,kraken`
Shadow latest day: `python3 run_v_fade_paper.py --shadow` or `python3 run_shadow_day.py`
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(md)
    return path


def save_summary_json(summary: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(summary), indent=2) + "\n")
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
