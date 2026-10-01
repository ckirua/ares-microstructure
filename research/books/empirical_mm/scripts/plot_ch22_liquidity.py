from __future__ import annotations
#!/usr/bin/env python3
"""Ch.22 liquidity figures + enriched EXP_REPORT (Amihud, spread, turnover, VPIN)."""

import os

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb')) / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import ensure_env, load_hl_tob, load_trades, overlap_trades_with_mids, resolve_days  # noqa: E402
from research.lib import amihud_illiquidity, bootstrap_ci, quoted_spread_bps, vpin_bucket  # noqa: E402
from research.lib.spreads import effective_spread_bps  # noqa: E402

OUT = BOOK / "out" / "ch22_liquidity"
CHAP = BOOK / "chapters" / "ch22_liquidity"


def main() -> int:
    ensure_env()
    OUT.mkdir(parents=True, exist_ok=True)
    symbol = "ETH"
    days = resolve_days(None, n=5)
    tob = load_hl_tob(symbol)
    tape = load_trades(symbol, days, max_files=32)
    ov = overlap_trades_with_mids(tape, tob)
    ok = (
        np.isfinite(ov["side"])
        & (ov["side"] != 0)
        & (ov["qty"] > 0)
        & np.isfinite(ov["px"])
    )
    ts = ov["ts"][ok].astype(np.int64)
    side = ov["side"][ok]
    qty = ov["qty"][ok]
    px = ov["px"][ok]
    mid = ov["mid0"][ok]

    bar = 60_000_000_000
    t0, t1 = int(ts.min()), int(ts.max())
    grid = np.arange(t0, t1 + 1, bar, dtype=np.int64)
    idx = np.searchsorted(ts, grid, side="left")
    bar_ts, rets, dvol, ntr = [], [], [], []
    last_px = np.nan
    for i in range(len(grid) - 1):
        lo, hi = idx[i], idx[i + 1]
        if hi <= lo:
            continue
        p_close = float(px[hi - 1])
        dv = float(np.sum(px[lo:hi] * qty[lo:hi]))
        if np.isfinite(last_px) and last_px > 0 and p_close > 0 and dv > 0:
            bar_ts.append(int(grid[i]))
            rets.append(np.log(p_close / last_px))
            dvol.append(dv)
            ntr.append(hi - lo)
        last_px = p_close

    bar_ts = np.asarray(bar_ts, dtype=np.int64)
    rets = np.asarray(rets, dtype=np.float64)
    dvol = np.asarray(dvol, dtype=np.float64)
    ntr = np.asarray(ntr, dtype=np.float64)
    illiq_bar = np.abs(rets) / dvol
    amihud = amihud_illiquidity(rets, dvol)

    day_keys = bar_ts // 86_400_000_000_000
    daily = []
    for dk in np.unique(day_keys):
        m = day_keys == dk
        if m.sum() < 5:
            continue
        a = amihud_illiquidity(rets[m], dvol[m])
        daily.append(
            {
                "day_key": int(dk),
                "n_bars": int(m.sum()),
                "illiq": a["illiq"],
                "mean_abs_r": float(np.mean(np.abs(rets[m]))),
                "mean_dvol": float(np.mean(dvol[m])),
                "sum_dvol": float(np.sum(dvol[m])),
                "turnover_proxy": float(np.sum(dvol[m]) / np.nanmedian(px)),
            }
        )

    qs = quoted_spread_bps(tob["bid"], tob["ask"], mid=tob["mid"])
    qs_ok = qs[np.isfinite(qs)]
    qs_ci = bootstrap_ci(qs_ok, n_boot=300, seed=55)
    tob_day = tob["ts"] // 86_400_000_000_000
    qs_by_day = {}
    for dk in np.unique(tob_day):
        m = (tob_day == dk) & np.isfinite(qs)
        if m.sum() > 50:
            qs_by_day[int(dk)] = float(np.mean(qs[m]))

    eff = effective_spread_bps(px, mid, side)
    eff_ok = eff[np.isfinite(eff)]
    eff_ci = (
        bootstrap_ci(eff_ok, n_boot=300, seed=56)
        if eff_ok.size > 50
        else {"n": int(eff_ok.size), "point": float("nan")}
    )
    bar_v = float(np.nanmedian(qty) * 100)
    vpin = vpin_bucket(side, qty, bucket_volume=bar_v, n_buckets_window=50)

    # --- figures ---
    roll = 30
    illiq_roll = np.convolve(illiq_bar, np.ones(roll) / roll, mode="valid")
    t_roll = bar_ts[roll - 1 :]
    hours = (t_roll - t_roll[0]) / 3.6e12
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    ax.plot(hours, illiq_roll, color="#1f4e79", lw=1.0)
    ax.axhline(
        amihud["illiq"],
        color="#c45c26",
        ls="--",
        lw=1.0,
        label=f"mean ILLIQ={amihud['illiq']:.3e}",
    )
    ax.set_xlabel("hours from sample start")
    ax.set_ylabel("|r| / dollar-vol  (1m bars, 30-bar roll)")
    ax.set_title("Amihud ILLIQ path — ETH 1m trade bars")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "fig_amihud_ts.png", dpi=120)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.4))
    axes[0].hist(
        illiq_bar[np.isfinite(illiq_bar)],
        bins=40,
        color="#5b8fbe",
        edgecolor="k",
        linewidth=0.3,
    )
    axes[0].axvline(amihud["illiq"], color="#c45c26", ls="--", label="mean")
    axes[0].set_xlabel("ILLIQ bar")
    axes[0].set_ylabel("count")
    axes[0].set_title("Cross-bar ILLIQ distribution")
    axes[0].legend(fontsize=8)
    d_illiq = [row["illiq"] for row in daily]
    axes[1].bar([str(i + 1) for i in range(len(d_illiq))], d_illiq, color="#1f4e79")
    axes[1].set_xlabel("sample day index")
    axes[1].set_ylabel("daily ILLIQ")
    axes[1].set_title("Daily Amihud ILLIQ")
    fig.tight_layout()
    fig.savefig(OUT / "fig_amihud_dist_daily.png", dpi=120)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.4))
    axes[0].hist(qs_ok, bins=50, color="#5b8fbe", edgecolor="k", linewidth=0.2)
    axes[0].axvline(
        qs_ci["point"],
        color="#c45c26",
        ls="--",
        label=f"mean={qs_ci['point']:.3f} bps",
    )
    axes[0].set_xlabel("quoted spread (bps)")
    axes[0].set_title("HL TOB quoted spread")
    axes[0].legend(fontsize=8)
    step = max(1, qs_ok.size // 2000)
    axes[1].plot(np.arange(0, qs_ok.size, step), qs_ok[::step], color="#1f4e79", lw=0.6)
    axes[1].set_xlabel("quote index (subsampled)")
    axes[1].set_ylabel("bps")
    axes[1].set_title("Quoted spread path")
    fig.tight_layout()
    fig.savefig(OUT / "fig_quoted_spread.png", dpi=120)
    plt.close(fig)

    xs, ys = [], []
    for row in daily:
        dk = row["day_key"]
        if dk in qs_by_day and np.isfinite(row["illiq"]):
            xs.append(qs_by_day[dk])
            ys.append(row["illiq"])
    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.4))
    if xs:
        axes[0].scatter(xs, ys, c="#1f4e79", s=50, edgecolors="k", linewidths=0.4)
        axes[0].set_xlabel("daily mean quoted spread (bps)")
        axes[0].set_ylabel("daily ILLIQ")
        axes[0].set_title("Daily ILLIQ vs quoted spread")
    else:
        axes[0].text(
            0.5,
            0.5,
            "no day overlap TOB↔tape",
            ha="center",
            va="center",
            transform=axes[0].transAxes,
        )
        axes[0].set_axis_off()
    labels = ["ILLIQ\n(x1e9)", "qs bps", "eff bps", "VPIN"]
    vals = [
        amihud["illiq"] * 1e9 if np.isfinite(amihud["illiq"]) else np.nan,
        qs_ci["point"],
        eff_ci.get("point", np.nan),
        vpin.get("mean_vpin", np.nan),
    ]
    colors = ["#1f4e79", "#5b8fbe", "#8fbf5b", "#c45c26"]
    axes[1].bar(labels, vals, color=colors)
    axes[1].set_title("Liquidity / toxicity levels (mixed units)")
    axes[1].set_ylabel("level")
    for i, v in enumerate(vals):
        if np.isfinite(v):
            axes[1].text(i, v * 1.02, f"{v:.3g}", ha="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "fig_illiq_vs_spread_vpin.png", dpi=120)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.4))
    axes[0].hist(dvol, bins=40, color="#5b8fbe", edgecolor="k", linewidth=0.3)
    axes[0].set_xlabel("dollar volume per 1m bar")
    axes[0].set_title("Dollar volume distribution")
    axes[0].axvline(
        np.median(dvol),
        color="#c45c26",
        ls="--",
        label=f"median={np.median(dvol):.0f}",
    )
    axes[0].legend(fontsize=8)
    turn = [row["sum_dvol"] for row in daily]
    axes[1].bar([str(i + 1) for i in range(len(turn))], turn, color="#1f4e79")
    axes[1].set_xlabel("sample day index")
    axes[1].set_ylabel("sum dollar-vol")
    axes[1].set_title("Daily dollar volume (turnover proxy)")
    fig.tight_layout()
    fig.savefig(OUT / "fig_turnover.png", dpi=120)
    plt.close(fig)

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "days": days,
        "n_trades": int(ts.size),
        "amihud": amihud,
        "amihud_daily": daily,
        "quoted_spread_bps": qs_ci,
        "effective_spread_bps": eff_ci,
        "turnover": {
            "n_bars": int(dvol.size),
            "median_dvol_1m": float(np.median(dvol)),
            "mean_dvol_1m": float(np.mean(dvol)),
            "mean_trades_per_bar": float(np.mean(ntr)),
            "mean_abs_ret_1m": float(np.mean(np.abs(rets))),
        },
        "vpin_companion": {
            "mean_vpin": vpin.get("mean_vpin"),
            "n_buckets": vpin.get("n_buckets"),
        },
        "decisions": {
            "liq.amihud_1m": (
                "Promote"
                if amihud.get("n", 0) >= 20 and np.isfinite(amihud.get("illiq", np.nan))
                else "Hold"
            ),
            "liq.quoted_spread_bps": "Promote" if qs_ci.get("n", 0) > 100 else "Hold",
        },
        "falsifiers": {
            "liq.amihud_1m": "ILLIQ≈0 or unstable across days",
            "liq.quoted_spread_bps": "non-finite / empty TOB",
        },
        "lenses": {
            "liq.amihud_1m": ["liq", "info", "exec"],
            "liq.quoted_spread_bps": ["liq", "mm", "exec"],
        },
        "figures": [
            "fig_amihud_ts.png",
            "fig_amihud_dist_daily.png",
            "fig_quoted_spread.png",
            "fig_illiq_vs_spread_vpin.png",
            "fig_turnover.png",
        ],
    }
    (OUT / "exp_ch22_eth_summary.json").write_text(json.dumps(payload, indent=2))

    daily_lines = "\n".join(
        f"  - day[{i}]: ILLIQ={row['illiq']:.4e}  n_bars={row['n_bars']}  "
        f"sum_$vol={row['sum_dvol']:.3g}"
        for i, row in enumerate(daily)
    )
    report = f"""# Ch.22 liquidity / Amihud — {symbol}

## Point estimates
- Amihud ILLIQ (1m): n={amihud['n']:.0f}  ILLIQ={amihud['illiq']:.6e}  CI95={amihud.get('illiq_ci95')}
- Quoted spread (bps): n={qs_ci['n']}  point={qs_ci['point']:.4f}  CI95=[{qs_ci['lo']:.4f}, {qs_ci['hi']:.4f}]
- Effective spread (bps): n={eff_ci.get('n')}  point={eff_ci.get('point')}
- VPIN companion (same tape): mean={vpin.get('mean_vpin')}  n_buckets={vpin.get('n_buckets')}
- Sample trades n={ts.size:,}  days={days}

## Turnover / activity
- median $vol / 1m bar = {float(np.median(dvol)):.3g}
- mean trades / 1m bar = {float(np.mean(ntr)):.2f}
- mean |r| / 1m = {float(np.mean(np.abs(rets))):.6g}

## Daily ILLIQ
{daily_lines}

## Decisions
- `liq.amihud_1m`: **{payload['decisions']['liq.amihud_1m']}** — falsifier: ILLIQ≈0 or unstable across days
- `liq.quoted_spread_bps`: **{payload['decisions']['liq.quoted_spread_bps']}** — falsifier: non-finite / empty TOB

## Figures
- `out/ch22_liquidity/fig_amihud_ts.png`
- `out/ch22_liquidity/fig_amihud_dist_daily.png`
- `out/ch22_liquidity/fig_quoted_spread.png`
- `out/ch22_liquidity/fig_illiq_vs_spread_vpin.png`
- `out/ch22_liquidity/fig_turnover.png`

## Desk read
- Spread ~{qs_ci['point']:.2f} bps is the MM/taker **tightness** floor on this window.
- ILLIQ ~{amihud['illiq']:.2e} is **impact per dollar**; watch daily rank, not equity-comparable level.
- Effective vs quoted: eff={eff_ci.get('point')} vs qs={qs_ci['point']:.4f} — gap flags mid-join / AS at touch.
- Crypto caveat: 24/7 1m bars ≠ CRSP daily Amihud; venue=HL only (not consolidated).
"""
    (OUT / "exp_ch22_eth_REPORT.md").write_text(report)
    (CHAP / "EXP_REPORT.md").write_text(report)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
