#!/usr/bin/env python3
"""Ch.10 trade process / inventory figures from Ch.13/15 out + light tape."""

from __future__ import annotations

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
sys.path.insert(0, str(Path("/home/dev/srv/ares-startarb") / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import ensure_env, load_hl_tob, load_trades, overlap_trades_with_mids, resolve_days  # noqa: E402
from research.lib.continuous import trade_intensity, vpin_bucket, volume_clock_returns  # noqa: E402
from research.lib.lob import qty_moment_ceiling  # noqa: E402

OUT = BOOK / "out" / "ch10_trades"
CHAP = BOOK / "chapters" / "ch10_trades"
OUT13 = BOOK / "out" / "ch13_var_impact"
OUT15 = BOOK / "out" / "ch15_pin"


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.grid": True,
            "grid.alpha": 0.25,
            "font.size": 10,
        }
    )


def _acf(x: np.ndarray, nlags: int = 20) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    x = x[np.isfinite(x)]
    if x.size < nlags + 5:
        return np.full(nlags, np.nan)
    x = x - x.mean()
    den = float(np.dot(x, x))
    if den <= 0:
        return np.full(nlags, np.nan)
    out = []
    for k in range(1, nlags + 1):
        out.append(float(np.dot(x[k:], x[:-k]) / den))
    return np.asarray(out, dtype=np.float64)


def _sign_volclock(side: np.ndarray, qty: np.ndarray, bar_volume: float) -> np.ndarray:
    """Net aggressor sign per equal-volume bar."""
    s = np.asarray(side, dtype=np.float64)
    q = np.asarray(qty, dtype=np.float64)
    m = np.isfinite(s) & np.isfinite(q) & (q > 0) & (s != 0)
    s, q = s[m], q[m]
    if s.size < 50 or bar_volume <= 0:
        return np.zeros(0, dtype=np.float64)
    signed = []
    net = vol = 0.0
    for i in range(s.size):
        net += s[i] * q[i]
        vol += q[i]
        if vol >= bar_volume:
            signed.append(1.0 if net > 0 else (-1.0 if net < 0 else 0.0))
            net = vol = 0.0
    return np.asarray(signed, dtype=np.float64)


def main() -> int:
    ensure_env()
    OUT.mkdir(parents=True, exist_ok=True)
    _style()

    d13 = json.loads((OUT13 / "exp_ch13_eth_summary.json").read_text())
    d15 = json.loads((OUT15 / "exp_ch15_eth_summary.json").read_text())
    symbol = d13.get("symbol", "ETH")
    days = d13.get("days") or resolve_days(None)

    # Light tape for size / intensity path / vol-clock signs
    tob = load_hl_tob(symbol)
    tape = load_trades(symbol, days, max_files=24)
    ov = overlap_trades_with_mids(tape, tob)
    ok = np.isfinite(ov["side"]) & (ov["side"] != 0) & (ov["qty"] > 0) & np.isfinite(ov["px"])
    ts = ov["ts"][ok].astype(np.int64)
    side = ov["side"][ok]
    qty = ov["qty"][ok]
    px = ov["px"][ok]

    sign_acf = d13["sign_acf"]
    intens15 = d15.get("cont_intensity") or {}
    vpin15 = d15.get("cont_vpin") or {}

    # Live intensity on overlap window (for path plot)
    intens_live = trade_intensity(ts, bar_ns=1_000_000_000)
    # rebuild 1s counts for path
    t0, t1 = int(ts.min()), int(ts.max())
    grid = np.arange(t0, t1 + 1, 1_000_000_000, dtype=np.int64)
    idx = np.searchsorted(ts, grid, side="left")
    counts = np.diff(idx).astype(np.float64)

    bar_vol = float(np.median(qty) * 40) if qty.size else 1.0
    if not np.isfinite(bar_vol) or bar_vol <= 0:
        bar_vol = float(np.percentile(qty, 50) * 40)
    q_vol = _sign_volclock(side, qty, bar_vol)
    acf_vol = _acf(q_vol[q_vol != 0], nlags=20) if q_vol.size > 30 else np.full(20, np.nan)

    size_moms = qty_moment_ceiling(qty)
    # also classic percentiles
    pcts = {p: float(np.percentile(qty, p)) for p in (50, 75, 90, 95, 99)}

    # --- Fig 1: sign ACF (from Ch.13) ---
    acf = sign_acf["acf"]
    lags = np.arange(1, len(acf) + 1)
    fig, ax = plt.subplots(figsize=(7.5, 3.6), constrained_layout=True)
    ax.bar(lags, acf, color="#6a51a3", alpha=0.9)
    ax.axhline(0, color="k", lw=0.6)
    ax.axhline(sign_acf["rho1"], color="#d94801", ls="--", label=f"ρ₁={sign_acf['rho1']:.3f}")
    ax.set_xlabel("lag (trades)")
    ax.set_ylabel("ACF(q)")
    ax.set_title("Trade-sign autocorrelation (Ch.10.d / Ch.13)")
    ax.legend(fontsize=8)
    fig.savefig(OUT / "fig_sign_acf.png", dpi=120)
    plt.close(fig)

    # --- Fig 2: intensity path + volume-clock sign ACF ---
    fig, ax = plt.subplots(1, 2, figsize=(11.0, 3.8), constrained_layout=True)
    # downsample path for readability
    step = max(1, counts.size // 800)
    x = np.arange(counts.size)[::step]
    ax[0].plot(x, counts[::step], color="#2c7fb8", lw=0.8, alpha=0.85)
    ax[0].axhline(intens_live.get("mean_lambda", np.nan), color="#e6550d", ls="--", lw=1.2,
                  label=f"λ̂={intens_live.get('mean_lambda', float('nan')):.2f}/s")
    ax[0].set_xlabel("1s bar index (overlap window)")
    ax[0].set_ylabel("trade count / s")
    ax[0].set_title(f"Calendar intensity (ac1={intens_live.get('count_ac1', float('nan')):.2f})")
    ax[0].legend(fontsize=8)
    lags_v = np.arange(1, len(acf_vol) + 1)
    ax[1].bar(lags_v, acf_vol, color="#238b45", alpha=0.9)
    ax[1].axhline(0, color="k", lw=0.6)
    rho1v = float(acf_vol[0]) if np.isfinite(acf_vol[0]) else float("nan")
    ax[1].axhline(rho1v, color="#d94801", ls="--", label=f"vol-clock ρ₁={rho1v:.3f}")
    ax[1].set_xlabel("lag (volume bars)")
    ax[1].set_ylabel("ACF(sign)")
    ax[1].set_title(f"Volume-clock sign ACF (bar≈{bar_vol:.3g})")
    ax[1].legend(fontsize=8)
    fig.savefig(OUT / "fig_intensity_volclock.png", dpi=120)
    plt.close(fig)

    # --- Fig 3: trade size ---
    fig, ax = plt.subplots(1, 2, figsize=(11.0, 3.8), constrained_layout=True)
    q_clip = qty[qty <= np.percentile(qty, 99.5)]
    ax[0].hist(q_clip, bins=60, color="#3182bd", alpha=0.85, density=True)
    ax[0].axvline(pcts[50], color="#e6550d", ls="--", label=f"p50={pcts[50]:.3g}")
    ax[0].axvline(float(np.mean(qty)), color="#238b45", ls=":", label=f"mean={float(np.mean(qty)):.3g}")
    ax[0].set_xlabel("trade size (coin)")
    ax[0].set_ylabel("density")
    ax[0].set_title("Trade size (clip p99.5)")
    ax[0].legend(fontsize=8)
    # cum mass / trunc var ratios
    keys = sorted(size_moms["trunc_var_ratio"].keys(), key=float)
    xs = [float(k) for k in keys]
    ys = [size_moms["trunc_var_ratio"][k] for k in keys]
    ax[1].plot(xs, ys, marker="o", color="#6a51a3", lw=2)
    ax[1].axhline(1.0, color="k", lw=0.6)
    ax[1].set_xlabel("truncation quantile")
    ax[1].set_ylabel("Var(q≤q̃) / Var(q≤0.9)")
    ax[1].set_title(f"Size moment ceiling (infl 0.995/0.9={size_moms.get('var_inflation_0p995_over_0p9', float('nan')):.1f}×)")
    fig.savefig(OUT / "fig_trade_size.png", dpi=120)
    plt.close(fig)

    # --- Fig 4: cum-flow inventory proxy ---
    signed_vol = side * qty
    I = -np.cumsum(signed_vol)
    # subsample for plot
    step = max(1, I.size // 2000)
    fig, ax = plt.subplots(figsize=(8.5, 3.6), constrained_layout=True)
    ax.plot(np.arange(I.size)[::step], I[::step], color="#08519c", lw=0.9)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlabel("trade index (overlap)")
    ax.set_ylabel(r"$I^{proxy}=-\sum q\cdot v$")
    ax.set_title("Implied inventory proxy (NOT certified dealer inventory)")
    fig.savefig(OUT / "fig_cumflow_inv.png", dpi=120)
    plt.close(fig)

    figures = [
        "fig_sign_acf.png",
        "fig_intensity_volclock.png",
        "fig_trade_size.png",
        "fig_cumflow_inv.png",
    ]

    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "days": days,
        "n_trades_overlap": int(ts.size),
        "sources": {
            "sign_acf": "out/ch13_var_impact/exp_ch13_eth_summary.json",
            "intensity_vpin": "out/ch15_pin/exp_ch15_eth_summary.json",
            "size_intensity_path": "light tape via _data.py",
        },
        "sign_acf": sign_acf,
        "cont_intensity_ch15": intens15,
        "cont_intensity_overlap": intens_live,
        "cont_vpin_ch15": vpin15,
        "volclock_sign_acf": {
            "bar_volume": bar_vol,
            "n_bars": int((q_vol != 0).sum()),
            "acf": [float(x) for x in acf_vol.tolist()],
            "rho1": rho1v,
        },
        "trade_size": {
            "n": int(qty.size),
            "mean": float(np.mean(qty)),
            "percentiles": pcts,
            "qty_moment_ceiling": size_moms,
        },
        "cumflow_inv": {
            "n": int(I.size),
            "end": float(I[-1]) if I.size else float("nan"),
            "std": float(np.std(I)) if I.size else float("nan"),
            "note": "proxy only; Ch.14 hs_as_inv_split remains Hold",
        },
        "decisions": {
            "disc.sign_acf": "Promote",
            "cont.trade_intensity": "Promote",
            "cont.vpin": "Promote",
            "disc.qty_moment_ceiling": "Promote",
            "mm.inventory_quote_skew": "Hold",
        },
        "second_pass": {
            "ch13": "ρ₁ feeds endogenous-q VAR; permanent IRF dominates transient inventory bounce",
            "ch15": "intensity+VPIN are toxicity/arrival twins of sign herding",
            "ch14": "hs_as_inv_split Hold — public tape cannot split AS vs inventory",
        },
        "figures": figures,
        "plot_meta": {"script": "plot_ch10_trades.py"},
    }
    (OUT / "exp_ch10_eth_summary.json").write_text(json.dumps(summary, indent=2, default=str))

    report = [
        "# Ch.10 trade process / inventory — ETH",
        "",
        f"- Days: {days}",
        f"- Overlap trades: **{ts.size:,}**",
        f"- Sign ρ₁ (Ch.13): **{sign_acf['rho1']:.3f}**",
        f"- Intensity λ̂ Ch.15 / overlap: **{intens15.get('mean_lambda', float('nan')):.3f}** / "
        f"**{intens_live.get('mean_lambda', float('nan')):.3f}**/s "
        f"(ac1={intens_live.get('count_ac1', float('nan')):.3f})",
        f"- VPIN (Ch.15): **{vpin15.get('mean_vpin', float('nan')):.3f}**",
        f"- Vol-clock sign ρ₁: **{rho1v:.3f}** (bar≈{bar_vol:.3g})",
        f"- Size p50/mean/p99: {pcts[50]:.4g} / {float(np.mean(qty)):.4g} / {pcts[99]:.4g}",
        f"- Size trunc-var infl 0.995/0.9: **{size_moms.get('var_inflation_0p995_over_0p9', float('nan')):.2f}×**",
        "",
        "## Decisions",
        "",
        "- `disc.sign_acf`: **Promote**",
        "- `cont.trade_intensity`: **Promote**",
        "- `cont.vpin`: **Promote** (via Ch.15)",
        "- `disc.qty_moment_ceiling`: **Promote**",
        "- `mm.inventory_quote_skew` / true dealer inventory: **Hold**",
        "",
        "## SECOND PASS",
        "",
        "- Ch.13: permanent IRF/markout = info channel; ρ₁ feeds endogenous-q models.",
        "- Ch.15: intensity + VPIN = toxicity/arrival overlays on the same herding fingerprint.",
        "- Ch.14: HS α|β split remains Hold on public tape.",
        "",
        f"Figures: {', '.join(figures)}",
        "",
        "JSON: `exp_ch10_eth_summary.json`",
    ]
    (OUT / "exp_ch10_eth_REPORT.md").write_text("\n".join(report) + "\n")
    (CHAP / "EXP_REPORT.md").write_text("\n".join(report) + "\n")

    print("wrote", OUT)
    for f in figures:
        p = OUT / f
        print(f, p.stat().st_size if p.exists() else 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
