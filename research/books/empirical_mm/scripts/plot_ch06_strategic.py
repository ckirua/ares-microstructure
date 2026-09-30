#!/usr/bin/env python3
"""Ch.6 Kyle strategic-trade schematic figures (synthetic)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BOOK = Path(__file__).resolve().parents[1]
OUT = BOOK / "out" / "ch06_strategic"
CHAP = BOOK / "chapters" / "ch06_strategic"


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


def kyle_lambda(sigma0: float, sigma_u: float) -> float:
    return float(np.sqrt(sigma0) / (2.0 * sigma_u))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    _style()
    rng = np.random.default_rng(6)

    # --- Fig 1: comparative statics λ(σ_u), λ(Σ0) ---
    fig, ax = plt.subplots(1, 2, figsize=(10.0, 3.6), constrained_layout=True)
    su = np.linspace(0.2, 3.0, 50)
    ax[0].plot(su, [kyle_lambda(1.0, s) for s in su], color="#c45c26", lw=2)
    ax[0].set_xlabel(r"noise σ_u")
    ax[0].set_ylabel(r"Kyle λ")
    ax[0].set_title(r"SYNTHETIC · λ vs σ_u (Σ₀=1)")
    s0 = np.linspace(0.2, 4.0, 50)
    ax[1].plot(s0, [kyle_lambda(s, 1.0) for s in s0], color="#1f4e79", lw=2)
    ax[1].set_xlabel(r"prior Σ₀")
    ax[1].set_ylabel(r"Kyle λ")
    ax[1].set_title(r"SYNTHETIC · λ vs Σ₀ (σ_u=1)")
    fig.savefig(OUT / "fig_kyle_lambda_statics.png", dpi=120)
    plt.close(fig)

    # --- Fig 2: single-period (y,p) cloud ---
    p0, sigma0, sigma_u = 100.0, 4.0, 1.5
    lam = kyle_lambda(sigma0, sigma_u)
    b = sigma_u / np.sqrt(sigma0)
    n = 400
    v = rng.normal(p0, np.sqrt(sigma0), size=n)
    u = rng.normal(0.0, sigma_u, size=n)
    x = b * (v - p0)  # a = -b p0 ⇒ x = a + b v = b(v-p0)
    y = x + u
    p = p0 + lam * y  # μ=p0
    fig, ax = plt.subplots(figsize=(6.5, 4.2), constrained_layout=True)
    ax.scatter(y, p, s=12, alpha=0.45, c="#3182bd", edgecolors="none")
    yr = np.linspace(y.min(), y.max(), 50)
    ax.plot(yr, p0 + lam * yr, color="#e6550d", lw=2, label=f"p=p0+λy · λ={lam:.3f}")
    ax.set_xlabel("net order flow y = x+u")
    ax.set_ylabel("clearing price p")
    ax.set_title("SYNTHETIC · single-period Kyle (y,p) cloud")
    ax.legend(fontsize=8)
    fig.savefig(OUT / "fig_kyle_yp_scatter.png", dpi=120)
    plt.close(fig)

    # --- Fig 3: multiperiod book numbers T=4, σu²=Σ0=1 ---
    # From Hasbrouck table (approx):
    # k: 1..4
    # a: 0.591587, 0.541962, 0.43462, 0
    # λ: 0.662334, 0.655372, 0.63844, 0.575215
    # b: 1.07417, 1.37071, 1.92957, 3.47696
    # Sk: 0.822136, 0.637499, 0.441163, 0.220582  (after auction; S0=1)
    k = np.array([1, 2, 3, 4])
    Sk = np.array([0.822136, 0.637499, 0.441163, 0.220582])
    bk = np.array([1.07417, 1.37071, 1.92957, 3.47696])
    lk = np.array([0.662334, 0.655372, 0.63844, 0.575215])
    fig, ax = plt.subplots(1, 3, figsize=(11.0, 3.4), constrained_layout=True)
    ax[0].plot(k, Sk, "o-", color="#238b45", lw=1.8)
    ax[0].set_title(r"SYNTHETIC · $S_k$ informativeness")
    ax[0].set_xlabel("auction k")
    ax[0].set_ylabel(r"$S_k=\mathrm{Var}(v\mid\mathcal{F}_k)$")
    ax[1].plot(k, bk, "o-", color="#6a51a3", lw=1.8)
    ax[1].set_title(r"informed demand $b_k$")
    ax[1].set_xlabel("auction k")
    ax[2].plot(k, lk, "o-", color="#c45c26", lw=1.8)
    ax[2].set_title(r"impact $\lambda_k$")
    ax[2].set_xlabel("auction k")
    fig.suptitle("Book numerical example T=4, σ_u²=Σ₀=1 (Hasbrouck 6.b)", fontsize=11)
    fig.savefig(OUT / "fig_kyle_multiperiod.png", dpi=120)
    plt.close(fig)

    # --- Fig 4: split vs dump inventory cartoon ---
    T = 20
    v_star = 2.0
    # dump: trade all early
    dump = np.zeros(T)
    dump[0] = v_star
    # split: equal slices
    split = np.full(T, v_star / T)
    # impact toy: cost rises with cum flow * declining λ
    lam_t = 0.7 * np.exp(-0.08 * np.arange(T))
    fig, ax = plt.subplots(1, 2, figsize=(10.0, 3.6), constrained_layout=True)
    ax[0].step(np.arange(T), np.cumsum(dump), where="post", color="#a50f15", label="dump")
    ax[0].step(np.arange(T), np.cumsum(split), where="post", color="#238b45", label="split")
    ax[0].set_xlabel("time")
    ax[0].set_ylabel("cum informed inventory")
    ax[0].set_title("SYNTHETIC · order splitting cartoon")
    ax[0].legend(fontsize=8)
    cost_dump = float(np.sum(dump * lam_t * np.cumsum(dump)))
    cost_split = float(np.sum(split * lam_t * np.cumsum(split)))
    ax[1].bar(["dump", "split"], [cost_dump, cost_split], color=["#a50f15", "#238b45"], alpha=0.85)
    ax[1].set_ylabel("toy impact cost")
    ax[1].set_title("why split (declining λ schedule)")
    fig.savefig(OUT / "fig_order_split_cartoon.png", dpi=120)
    plt.close(fig)

    figures = [
        "fig_kyle_lambda_statics.png",
        "fig_kyle_yp_scatter.png",
        "fig_kyle_multiperiod.png",
        "fig_order_split_cartoon.png",
    ]
    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "kind": "synthetic_kyle",
        "label": "SYNTHETIC — not HL tape",
        "figures": figures,
        "single_period": {"p0": p0, "Sigma0": sigma0, "sigma_u": sigma_u, "lambda": lam},
        "empirics_owners": ["ch13_var_impact", "ch14_structural", "mmip_ch03"],
    }
    (OUT / "exp_ch06_synthetic_summary.json").write_text(json.dumps(summary, indent=2))

    report = "\n".join(
        [
            "# Ch.6 Strategic trade — synthetic study figures",
            "",
            "- **All figures SYNTHETIC** (Kyle closed forms / book T=4 table / split cartoon).",
            "- Empirics: Ch.13 λ/IRF/OFI · Ch.14 MRR θ · mmip POV schedules.",
            "",
            "## Figures",
            *[f"- `out/ch06_strategic/{f}`" for f in figures],
            "",
            "## Read",
            "- λ falls in σ_u (camouflage) and rises in Σ₀ — inverse liquidity prior for TCA.",
            "- (y,p) slope is the single-period impact object; HL estimates use quote-aligned clocks.",
            "- Multiperiod: S↓, b↑, λ↓ — earlier flow more informative / costly.",
            "- Split cartoon: declining λ schedule rewards patience (POV intuition).",
        ]
    ) + "\n"
    (OUT / "exp_ch06_synthetic_REPORT.md").write_text(report)
    (CHAP / "EXP_REPORT.md").write_text(report)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
