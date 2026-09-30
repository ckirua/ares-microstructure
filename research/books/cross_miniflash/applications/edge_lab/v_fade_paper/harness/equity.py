"""Path equity curves (event-time + calendar-time) with drawdown.

Primary scoreboard for Promote_shadow is **path** PnL (entry→exit tape − RT),
not lab identity (−mo₅ₛ−RT). Lab curves remain diagnostic only.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .causal import jsonable

NS = 1_000_000_000


def order_trades(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        trades,
        key=lambda t: (str(t.get("day") or ""), int(t.get("entry_ts") or 0)),
    )


def path_pnls(trades: list[dict[str, Any]]) -> np.ndarray:
    ordered = order_trades(trades)
    arr = np.asarray(
        [float(t["path_pnl_net_bps"]) for t in ordered if t.get("path_pnl_net_bps") is not None],
        dtype=np.float64,
    )
    return arr[np.isfinite(arr)]


def equity_stats(pnls: np.ndarray) -> dict[str, float]:
    if pnls.size == 0:
        return {
            "n": 0,
            "final_bps": 0.0,
            "max_dd_bps": 0.0,
            "mean_bps": float("nan"),
            "hit_rate": float("nan"),
        }
    eq = np.cumsum(pnls)
    peak = np.maximum.accumulate(eq)
    dd = eq - peak
    return {
        "n": int(pnls.size),
        "final_bps": float(eq[-1]),
        "max_dd_bps": float(dd.min()),
        "mean_bps": float(np.mean(pnls)),
        "hit_rate": float(np.mean(pnls > 0)),
    }


def _drawdown(eq: np.ndarray) -> np.ndarray:
    if eq.size == 0:
        return eq
    peak = np.maximum.accumulate(eq)
    return eq - peak


def _calendar_x(trades: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    """Return (x_hours_from_first, path_pnls, used_trades) sorted by entry_ts."""
    rows = []
    for t in order_trades(trades):
        if t.get("path_pnl_net_bps") is None or t.get("entry_ts") is None:
            continue
        try:
            pnl = float(t["path_pnl_net_bps"])
            ts = int(t["entry_ts"])
        except (TypeError, ValueError):
            continue
        if not np.isfinite(pnl):
            continue
        rows.append({"ts": ts, "pnl": pnl, "day": str(t.get("day") or ""), "trade": t})
    if not rows:
        return np.asarray([], dtype=np.float64), np.asarray([], dtype=np.float64), []
    t0 = float(rows[0]["ts"])
    x = np.asarray([(r["ts"] - t0) / NS / 3600.0 for r in rows], dtype=np.float64)
    y = np.asarray([r["pnl"] for r in rows], dtype=np.float64)
    return x, y, rows


def write_path_equity_figs(
    trades: list[dict[str, Any]],
    fig_dir: Path,
    *,
    label: str,
    venue: str = "hyperliquid",
    symbol: str = "ETH",
    peer_trades: list[dict[str, Any]] | None = None,
    peer_label: str | None = None,
    stem: str = "equity_path",
) -> list[str]:
    """Write event-time + calendar-time path equity PNGs (with drawdown subplot).

    If peer_trades given, also write a side-by-side comparison PNG.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    ordered = order_trades(trades)
    pnls = path_pnls(ordered)
    stats = equity_stats(pnls)

    # --- event-time (fade #) + drawdown ---
    fig, (ax, ax_dd) = plt.subplots(
        2, 1, figsize=(11, 5.2), sharex=True, gridspec_kw={"height_ratios": [2.4, 1.0]}
    )
    if pnls.size:
        eq = np.cumsum(pnls)
        xs = np.arange(1, len(eq) + 1)
        ax.plot(xs, eq, color="#1a5276", lw=1.5, marker="o", ms=3.5, label=label)
        ax.axhline(0, color="#7f8c8d", lw=0.8, ls="--")
        days = [str(t.get("day")) for t in ordered if t.get("path_pnl_net_bps") is not None]
        prev = None
        for i, d in enumerate(days):
            if d != prev:
                ax.axvline(i + 1, color="#ecf0f1", lw=0.9, zorder=0)
                ax_dd.axvline(i + 1, color="#ecf0f1", lw=0.9, zorder=0)
                prev = d
        dd = _drawdown(eq)
        ax_dd.fill_between(xs, dd, 0, color="#c0392b", alpha=0.35, lw=0)
        ax_dd.plot(xs, dd, color="#922b21", lw=1.0)
        ax_dd.axhline(0, color="#7f8c8d", lw=0.6)
        ax.set_ylabel("cum path net bps")
        ax_dd.set_ylabel("drawdown")
        ax_dd.set_xlabel("fade # (event order)")
        ax.legend(fontsize=8, loc="best")
        ax.set_title(
            f"{venue} {symbol} — {label}\n"
            f"path equity event-time · n={stats['n']} · final={stats['final_bps']:.1f} bps · "
            f"maxDD={stats['max_dd_bps']:.1f} · mean={stats['mean_bps']:.2f}"
        )
    else:
        ax.text(0.5, 0.5, "no path fades", ha="center", va="center", transform=ax.transAxes)
        ax.set_title(f"{venue} {symbol} — {label} (empty)")
    fig.tight_layout()
    p = fig_dir / f"{stem}_event.png"
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p))

    # --- calendar-time + drawdown ---
    x_h, y_pnl, _rows = _calendar_x(ordered)
    fig, (ax, ax_dd) = plt.subplots(
        2, 1, figsize=(11, 5.2), sharex=True, gridspec_kw={"height_ratios": [2.4, 1.0]}
    )
    if y_pnl.size:
        eq = np.cumsum(y_pnl)
        ax.step(x_h, eq, where="post", color="#117a65", lw=1.5, label=label)
        ax.plot(x_h, eq, "o", color="#117a65", ms=3.5)
        ax.axhline(0, color="#7f8c8d", lw=0.8, ls="--")
        dd = _drawdown(eq)
        ax_dd.fill_between(x_h, dd, 0, step="post", color="#c0392b", alpha=0.35, lw=0)
        ax_dd.step(x_h, dd, where="post", color="#922b21", lw=1.0)
        ax_dd.axhline(0, color="#7f8c8d", lw=0.6)
        ax.set_ylabel("cum path net bps")
        ax_dd.set_ylabel("drawdown")
        ax_dd.set_xlabel("hours from first entry (panel clock)")
        ax.legend(fontsize=8, loc="best")
        ax.set_title(
            f"{venue} {symbol} — {label}\n"
            f"path equity calendar-time · n={stats['n']} · final={stats['final_bps']:.1f} bps · "
            f"maxDD={stats['max_dd_bps']:.1f}"
        )
    else:
        ax.text(0.5, 0.5, "no path fades", ha="center", va="center", transform=ax.transAxes)
        ax.set_title(f"{venue} {symbol} — {label} (empty)")
    fig.tight_layout()
    p = fig_dir / f"{stem}_calendar.png"
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p))

    # --- side-by-side vs peer ---
    if peer_trades is not None:
        peer_label = peer_label or "peer"
        fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.0), sharey=True)
        for ax, trs, lab, color in (
            (axes[0], ordered, label, "#1a5276"),
            (axes[1], order_trades(peer_trades), peer_label, "#7d3c98"),
        ):
            pp = path_pnls(trs)
            st = equity_stats(pp)
            if pp.size:
                eq = np.cumsum(pp)
                ax.plot(np.arange(1, len(eq) + 1), eq, color=color, lw=1.5, marker="o", ms=3)
                ax.axhline(0, color="#7f8c8d", lw=0.8, ls="--")
            ax.set_title(f"{lab}\nn={st['n']} final={st['final_bps']:.1f} maxDD={st['max_dd_bps']:.1f}")
            ax.set_xlabel("fade #")
            ax.set_ylabel("cum path net bps")
        fig.suptitle(
            f"{venue} {symbol} path equity — Promote vs Hold (event-time)",
            fontsize=11,
            y=1.02,
        )
        fig.tight_layout()
        p = fig_dir / f"{stem}_vs_confirm_r2.png"
        fig.savefig(p, dpi=140, bbox_inches="tight")
        plt.close(fig)
        paths.append(str(p))

    return paths


def write_equity_markdown(
    *,
    out_path: Path,
    severity_trades: list[dict[str, Any]],
    confirm_trades: list[dict[str, Any]] | None,
    fig_paths: list[str],
    policy: dict[str, Any],
) -> Path:
    sev = equity_stats(path_pnls(severity_trades))
    conf = equity_stats(path_pnls(confirm_trades or []))
    figs = "\n".join(f"- `{Path(p).name}`" for p in fig_paths) or "- _(none)_"
    md = f"""# V-fade path EQUITY

Generated: `{datetime.now(timezone.utc).isoformat()}`

> **SHADOW PAPER** · `live_orders=false` · path = entry@delay→exit tape − RT4 · **not** live OE

## How to read the curve

1. **Y-axis = cumulative path net bps** — each fade’s realized tape PnL after RT=4, summed in order.
2. **Event-time** (`equity_path_event.png`) — x = fade # (1…n). Day separators are vertical lines. Bottom panel = drawdown from running peak.
3. **Calendar-time** (`equity_path_calendar.png`) — x = hours from the first panel entry. Same PnL, wall-clock spacing.
4. **Side-by-side** (`equity_path_vs_confirm_r2.png`) — Promote `severity_zend` vs Hold `confirm_r2@2→5` on the same panel days.
5. **Lab identity is not this curve.** Lab = `−mo_5s − RT` (credits rebound before entry). Path is what an executable shadow would mark.

## Caveat — n={sev['n']}

Panel HL ETH 09-04…10 under locked Promote defaults yields **n={sev['n']}** fades.
That is enough for a path CI>0 Promote_shadow gate, but **not** a large-sample equity claim.
Treat the shape as descriptive; do not overfit single-trade spikes (e.g. one +67 bps day).

## Locked policy (Promote_shadow +20.2)

| param | value |
|-------|------:|
| entry_mode | `{policy.get('entry_mode', 'severity_zend')}` |
| z_min | {policy.get('z_min', 20)} |
| confirm_s | {policy.get('confirm_s', 0.5)} |
| exit_s | {policy.get('exit_s', 3.0)} |
| fire_pause | `{policy.get('suppress_fire_pause', 'prior_only')}` |
| adverse | off |

## Scoreboard

| policy | n | path mean | final cum | max DD | hit |
|--------|--:|----------:|----------:|-------:|----:|
| **severity_zend** Promote | {sev['n']} | {sev['mean_bps']:.2f} | **{sev['final_bps']:.1f}** | {sev['max_dd_bps']:.1f} | {sev['hit_rate']:.2f} |
| confirm_r2 @2→5 Hold | {conf['n']} | {conf['mean_bps']:.2f} | {conf['final_bps']:.1f} | {conf['max_dd_bps']:.1f} | {conf['hit_rate']:.2f} |

## Figures

{figs}

Reproduce:

```bash
cd v_fade_paper
python3 build_equity_curves.py
# or full panel:
python3 run_v_fade_paper.py --panel-days
```

research_sim · live_orders=false · lab ≠ path · ClickHouse MCP banned.
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md)
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "severity_zend": sev,
        "confirm_r2": conf,
        "policy": policy,
        "figures": fig_paths,
        "live_orders": False,
    }
    (out_path.parent / "equity_meta.json").write_text(
        json.dumps(jsonable(meta), indent=2) + "\n"
    )
    return out_path
