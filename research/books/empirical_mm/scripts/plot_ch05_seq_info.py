#!/usr/bin/env python3
"""Ch.5 sequential-trade schematic figures (synthetic Glosten–Milgrom cartoons)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BOOK = Path(__file__).resolve().parents[1]
OUT = BOOK / "out" / "ch05_seq_info"
CHAP = BOOK / "chapters" / "ch05_seq_info"


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


def ask_bid(delta: float, mu: float, v_l: float = 100.0, v_h: float = 150.0) -> tuple[float, float]:
    """Competitive GM quotes: A=E[V|Buy], B=E[V|Sell]; δ=Pr(V_H), μ=informed share.

    First-principles Bayes (OCR of 5.b.10–11 is unreliable). Matches book
    spreadsheet intuition: δ_high=0.6, μ=0.9 → Ask≈148.31, Bid≈103.66.
    """
    pr_vh, pr_vl = float(delta), 1.0 - float(delta)
    pr_buy = pr_vh * (1.0 + mu) / 2.0 + pr_vl * (1.0 - mu) / 2.0
    pr_sell = pr_vh * (1.0 - mu) / 2.0 + pr_vl * (1.0 + mu) / 2.0
    pr_vh_buy = pr_vh * (1.0 + mu) / 2.0 / pr_buy
    pr_vh_sell = pr_vh * (1.0 - mu) / 2.0 / pr_sell
    a = pr_vh_buy * v_h + (1.0 - pr_vh_buy) * v_l
    b = pr_vh_sell * v_h + (1.0 - pr_vh_sell) * v_l
    return float(a), float(b)


def update_delta(delta: float, mu: float, buy: bool) -> float:
    """Bayes update for δ=Pr(V_H) after buy/sell."""
    pr_vh, pr_vl = float(delta), 1.0 - float(delta)
    if buy:
        pr_buy = pr_vh * (1.0 + mu) / 2.0 + pr_vl * (1.0 - mu) / 2.0
        return float(pr_vh * (1.0 + mu) / 2.0 / pr_buy)
    pr_sell = pr_vh * (1.0 - mu) / 2.0 + pr_vl * (1.0 + mu) / 2.0
    return float(pr_vh * (1.0 - mu) / 2.0 / pr_sell)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    _style()
    rng = np.random.default_rng(5)

    # --- Fig 1: spread vs μ at δ=1/2 ---
    mus = np.linspace(0.0, 0.95, 40)
    spreads_sym = []
    for mu in mus:
        a, b = ask_bid(0.5, float(mu))
        spreads_sym.append(a - b)
    # analytic (V_H-V_L)*μ
    analytic = (150.0 - 100.0) * mus
    fig, ax = plt.subplots(figsize=(7.2, 3.8), constrained_layout=True)
    ax.plot(mus, spreads_sym, color="#1f4e79", lw=2, label="GM A−B (δ=½)")
    ax.plot(mus, analytic, color="#e6550d", ls="--", lw=1.4, label="(V_H−V_L)μ")
    ax.set_xlabel("informed share μ")
    ax.set_ylabel("spread")
    ax.set_title("SYNTHETIC · Glosten–Milgrom spread vs μ (δ=½)")
    ax.legend(fontsize=8)
    fig.savefig(OUT / "fig_spread_vs_mu.png", dpi=120)
    plt.close(fig)

    # --- Fig 2: posterior Pr(I|Buy) vs μ ---
    fig, ax = plt.subplots(figsize=(7.2, 3.8), constrained_layout=True)
    for delta, col in [(0.5, "#2c7fb8"), (0.3, "#238b45"), (0.7, "#6a51a3")]:
        pr_i = []
        for mu in mus:
            # Pr(I|Buy) = Pr(Buy|I)Pr(I)/Pr(Buy); Pr(Buy|I)=δ (buy only if VH when informed)
            # Informed arrives with prob μ; buys iff VH. Uninformed buy with 1/2.
            # Pr(I and Buy) = μ * δ
            # Pr(Buy) = μ*δ + (1-μ)*0.5
            den = mu * delta + (1.0 - mu) * 0.5
            pr_i.append(float(mu * delta / den) if den > 0 else np.nan)
        ax.plot(mus, pr_i, color=col, lw=1.8, label=f"δ=Pr(V_H)={delta}")
    ax.set_xlabel("μ")
    ax.set_ylabel("Pr(Informed | Buy)")
    ax.set_title("SYNTHETIC · adverse-selection weight in a buy")
    ax.set_ylim(0, 1.05)
    ax.legend(fontsize=8)
    fig.savefig(OUT / "fig_pr_informed_buy.png", dpi=120)
    plt.close(fig)

    # --- Fig 3: belief / quote path after buys then sells ---
    mu0, d0 = 0.35, 0.5
    # sequence: BBBBB SSSSS BBB (learning cartoon)
    signs = [+1] * 6 + [-1] * 5 + [+1] * 4
    deltas = [d0]
    asks, bids, trades = [], [], []
    d = d0
    for s in signs:
        a, b = ask_bid(d, mu0)
        asks.append(a)
        bids.append(b)
        trades.append(a if s > 0 else b)
        d = update_delta(d, mu0, buy=(s > 0))
        deltas.append(d)
    t = np.arange(1, len(signs) + 1)
    fig, ax = plt.subplots(2, 1, figsize=(9.5, 5.6), sharex=True, constrained_layout=True)
    ax[0].step(t, asks, where="mid", color="#e6550d", label="ask")
    ax[0].step(t, bids, where="mid", color="#2c7fb8", label="bid")
    ax[0].scatter(t, trades, c=["#238b45" if s > 0 else "#a50f15" for s in signs], s=28, zorder=3, label="trade")
    ax[0].set_ylabel("price")
    ax[0].set_title(f"SYNTHETIC · GM quote path (μ={mu0}, start δ={d0})")
    ax[0].legend(fontsize=8, loc="best")
    ax[1].step(np.arange(len(deltas)), deltas, where="mid", color="#6a51a3", lw=1.8)
    ax[1].axhline(0.5, color="k", ls=":", lw=0.8)
    ax[1].set_ylabel("δ = Pr(V_H)")
    ax[1].set_xlabel("trade index")
    ax[1].set_title("Belief recursion (info arrival cartoon)")
    fig.savefig(OUT / "fig_quote_belief_path.png", dpi=120)
    plt.close(fig)

    # --- Fig 4: permanent impact cartoon (mid after signed flow) ---
    # Simulate many paths of δ after +1 buy shock from δ=0.5
    n_paths, horizon = 40, 12
    fig, ax = plt.subplots(figsize=(8.0, 3.8), constrained_layout=True)
    mids = []
    for _ in range(n_paths):
        d = 0.5
        path = []
        # force first trade buy, then random uninformed-ish continuation
        seq = [+1] + list(rng.choice([-1, 1], size=horizon - 1, p=[0.45, 0.55]))
        for s in seq:
            a, b = ask_bid(d, 0.4)
            mid = 0.5 * (a + b)
            path.append(mid)
            d = update_delta(d, 0.4, buy=(s > 0))
        mids.append(path)
        ax.plot(np.arange(1, horizon + 1), path, color="#9ecae1", alpha=0.35, lw=0.9)
    mean_path = np.mean(np.asarray(mids), axis=0)
    ax.plot(np.arange(1, horizon + 1), mean_path, color="#08519c", lw=2.2, label="mean mid path")
    ax.axhline(mean_path[0], color="k", ls=":", lw=0.8)
    ax.set_xlabel("trade after +1 buy shock")
    ax.set_ylabel("mid = (A+B)/2")
    ax.set_title("SYNTHETIC · permanent impact cartoon (bridge to Ch.13 IRF)")
    ax.legend(fontsize=8)
    fig.savefig(OUT / "fig_impact_cartoon.png", dpi=120)
    plt.close(fig)

    figures = [
        "fig_spread_vs_mu.png",
        "fig_pr_informed_buy.png",
        "fig_quote_belief_path.png",
        "fig_impact_cartoon.png",
    ]
    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "kind": "synthetic_glosten_milgrom",
        "label": "SYNTHETIC — not HL tape",
        "figures": figures,
        "params_example": {"mu": mu0, "delta0": d0, "V_L": 100, "V_H": 150},
        "empirics_owners": ["ch13_var_impact", "ch14_structural", "ch15_pin"],
    }
    (OUT / "exp_ch05_synthetic_summary.json").write_text(json.dumps(summary, indent=2))

    report = "\n".join(
        [
            "# Ch.5 Sequential trade — synthetic study figures",
            "",
            "- **All figures SYNTHETIC** (Glosten–Milgrom closed forms / Bayes paths).",
            "- Empirics: Ch.13 markout/λ · Ch.14 GH/MRR/HS · Ch.15 PIN/VPIN.",
            "",
            "## Figures",
            *[f"- `out/ch05_seq_info/{f}`" for f in figures],
            "",
            "## Read",
            "- Spread vs μ: linear AS cost at δ=½ — desk maps to quoted spread / markout regimes.",
            "- Quote path: learning compresses spread; trade prices martingale under pure AS.",
            "- Impact cartoon: mean mid stays elevated after buy cluster → Ch.13 permanent IRF intuition.",
        ]
    ) + "\n"
    (OUT / "exp_ch05_synthetic_REPORT.md").write_text(report)
    (CHAP / "EXP_REPORT.md").write_text(report)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
