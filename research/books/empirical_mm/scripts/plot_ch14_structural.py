from __future__ import annotations
#!/usr/bin/env python3
"""Ch.14 GH / MRR / Huang–Stoll figures + enriched EXP_REPORT."""

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

from _data import (  # noqa: E402
    ensure_env,
    load_hl_tob,
    load_trades,
    overlap_trades_with_mids,
    resolve_days,
)
from research.lib import glosten_harris_ols, quote_aligned_delta_mid  # noqa: E402

OUT = BOOK / "out" / "ch14_structural"
OUT13 = BOOK / "out" / "ch13_var_impact"
CHAP = BOOK / "chapters" / "ch14_structural"


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


def main() -> int:
    ensure_env()
    OUT.mkdir(parents=True, exist_ok=True)
    _style()
    d = json.loads((OUT / "exp_ch14_eth_summary.json").read_text())
    d13 = {}
    p13 = OUT13 / "exp_ch13_eth_summary.json"
    if p13.exists():
        d13 = json.loads(p13.read_text())
    symbol = d.get("symbol", "ETH")
    days = d.get("days") or resolve_days(None)

    gh, gh_tr, gh_te = d["gh"], d["gh_train"], d["gh_test"]
    mrr = d["mrr"]
    hs = d.get("huang_stoll") or {}
    hs_tr = d.get("huang_stoll_train") or {}
    hs_te = d.get("huang_stoll_test") or {}
    decomp = d.get("huang_stoll_decomp") or {}
    decomp_free = d.get("huang_stoll_decomp_free_S") or {}
    hs_basic_asof = d.get("huang_stoll_basic") or {}

    # --- Fig 1: GH z0 train/test ---
    fig, ax = plt.subplots(1, 2, figsize=(9.5, 3.6), constrained_layout=True)
    labels = ["full", "train", "test"]
    z0s = [gh["z0"], gh_tr["z0"], gh_te["z0"]]
    r2s = [gh["r2"], gh_tr["r2"], gh_te["r2"]]
    ax[0].bar(labels, z0s, color=["#2c7fb8", "#74c476", "#006d2c"], alpha=0.9)
    ax[0].axhline(0, color="k", lw=0.6)
    ax[0].set_ylabel("z₀ (AS intercept)")
    ax[0].set_title(f"Glosten–Harris z₀ · z₁={gh['z1']:.2e}")
    ax[1].bar(labels, r2s, color=["#3182bd", "#9ecae1", "#08519c"], alpha=0.9)
    ax[1].axhline(0.01, color="#e6550d", ls="--", label="Promote R²≥1%")
    ax[1].set_ylabel("R²")
    ax[1].set_title("GH fit R² (quote-aligned Δm)")
    ax[1].legend(fontsize=8)
    fig.savefig(OUT / "fig_gh_z0.png", dpi=120)
    plt.close(fig)

    # --- Fig 2: MRR θ / φ / ρ ---
    fig, ax = plt.subplots(figsize=(6.8, 3.8), constrained_layout=True)
    labs = ["θ (perm)", "φ (temp)", "ρ(q)"]
    vals = [mrr["theta_perm"], mrr["phi_temp"], mrr["rho_q"]]
    cols = ["#238b45", "#fd8d3c", "#6a51a3"]
    ax.bar(labs, vals, color=cols, alpha=0.9)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_title(f"MRR reduced form · R²={mrr['r2']:.3f} · n={mrr['n']:,}")
    ax.set_ylabel("parameter")
    for i, v in enumerate(vals):
        ax.text(i, v + (0.01 if v >= 0 else -0.02), f"{v:.4f}", ha="center", fontsize=8)
    fig.savefig(OUT / "fig_mrr_decomp.png", dpi=120)
    plt.close(fig)

    # --- Fig 3: HS lump π train/test (quote-aligned) ---
    fig, ax = plt.subplots(1, 2, figsize=(9.5, 3.6), constrained_layout=True)
    pis = [hs.get("pi_inv_info"), hs_tr.get("pi_inv_info"), hs_te.get("pi_inv_info")]
    r2h = [hs.get("r2"), hs_tr.get("r2"), hs_te.get("r2")]
    ax[0].bar(labels, pis, color=["#e6550d", "#fdae6b", "#a63603"], alpha=0.9)
    ax[0].axhline(0, color="k", lw=0.6)
    ax[0].set_ylabel("π̂ ≈ (α+β)S/2")
    ax[0].set_title("Huang–Stoll lump π (quote-aligned Δm)")
    ax[1].bar(labels, r2h, color=["#e6550d", "#fdae6b", "#a63603"], alpha=0.75)
    ax[1].axhline(0.01, color="#2c7fb8", ls="--", label="Promote R²≥1%")
    ax[1].set_ylabel("R²")
    ax[1].set_title("HS π R²")
    ax[1].legend(fontsize=8)
    fig.savefig(OUT / "fig_hs_pi.png", dpi=120)
    plt.close(fig)

    # --- Fig 4: HS two-way / three-way decomp (Hold on AS/inv) ---
    fig, ax = plt.subplots(figsize=(8.2, 4.0), constrained_layout=True)
    names = [
        "two-way λ̂\n(a+b)",
        "a (AS)\nthree-way",
        "b (inv)\nthree-way",
        "as_share",
        "free-S λ̂",
        "mid-path λ̂",
    ]
    vals4 = [
        decomp.get("lambda_ab", np.nan),
        decomp.get("a_adverse", np.nan),
        decomp.get("b_inventory", np.nan),
        decomp.get("as_share", np.nan),
        decomp_free.get("lambda_ab", np.nan),
        decomp.get("lambda_ab_mid", np.nan),
    ]
    colors = []
    for name, v in zip(names, vals4):
        if "AS" in name or "as_share" in name:
            colors.append("#d7301f" if (isinstance(v, float) and v < 0) else "#238b45")
        else:
            colors.append("#2c7fb8")
    ax.bar(names, vals4, color=colors, alpha=0.9)
    ax.axhline(0, color="k", lw=0.6)
    ax.axhline(1.0, color="gray", ls=":", lw=0.8)
    ax.set_title(
        "HS spread decomp — two-way usable; three-way AS/inv Hold "
        f"(R²₃={decomp.get('r2_three_way', float('nan')):.3f})"
    )
    ax.set_ylabel("coefficient / share")
    fig.savefig(OUT / "fig_hs_decomp.png", dpi=120)
    plt.close(fig)

    # --- Fig 5: cross-model permanent / AS comparison (13↔14) ---
    fig, ax = plt.subplots(figsize=(9.0, 4.0), constrained_layout=True)
    items = [
        ("λ_OLS\n(Ch.13)", (d13.get("lambda_hygiene") or {}).get("full", {}).get("lambda")),
        ("λ_VAR\n(Ch.13)", (d13.get("var") or {}).get("lambda_contemp")),
        ("IRF perm\n(Ch.13)", (d13.get("irf") or {}).get("permanent_impact")),
        ("GH z₀\n(Ch.14)", gh["z0"]),
        ("HS π̂\n(aligned)", hs.get("pi_inv_info")),
        ("MRR θ\n(Δp)", mrr["theta_perm"]),
        ("HS two-way λ̂\n(Δp)", decomp.get("lambda_ab")),
    ]
    names5 = [x[0] for x in items]
    vals5 = [float(x[1]) if x[1] is not None and np.isfinite(float(x[1])) else np.nan for x in items]
    ax.bar(names5, vals5, color="#54278f", alpha=0.85)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_ylabel("impact / AS level (price units; not all comparable)")
    ax.set_title("Cross-model impact objects (units differ — sign & order of magnitude)")
    fig.savefig(OUT / "fig_perm_impact_compare.png", dpi=120)
    plt.close(fig)

    # --- Fig 6: GH size slope — binned mean Δm by size × side ---
    tob = load_hl_tob(symbol)
    tape = load_trades(symbol, days, max_files=24)
    ov = overlap_trades_with_mids(tape, tob)
    mid0 = ov["mid0"]
    ok = np.isfinite(mid0) & (mid0 > 0) & np.isfinite(ov["side"]) & (ov["side"] != 0)
    ts, side, qty = ov["ts"][ok], ov["side"][ok], ov["qty"][ok]
    qa = quote_aligned_delta_mid(
        ts, side, tob["ts"], tob["mid"], trade_qty=qty, mode="next_mid_change", max_lag_ns=5_000_000_000
    )
    d_mid = qa["d_mid"]
    side_e = qa["side"]
    qty_e = qa["qty"]
    sz = qty_e / max(float(np.nanmedian(qty_e[qty_e > 0])), 1e-12)
    # signed predicted vs residual by size quintile
    gh_live = glosten_harris_ols(d_mid, side_e, sz)
    # bin by size
    qs = np.nanquantile(sz[np.isfinite(sz) & (sz > 0)], [0.2, 0.4, 0.6, 0.8])
    edges = np.concatenate([[0], qs, [np.inf]])
    bin_x, mean_buy, mean_sell = [], [], []
    for i in range(len(edges) - 1):
        mbin = (sz >= edges[i]) & (sz < edges[i + 1]) & np.isfinite(d_mid)
        bin_x.append(i + 1)
        mb = d_mid[mbin & (side_e > 0)]
        ms = d_mid[mbin & (side_e < 0)]
        mean_buy.append(float(np.mean(mb)) if mb.size else np.nan)
        mean_sell.append(float(np.mean(ms)) if ms.size else np.nan)
    fig, ax = plt.subplots(figsize=(7.2, 3.8), constrained_layout=True)
    ax.plot(bin_x, mean_buy, "o-", color="#238b45", label="mean Δm | buy")
    ax.plot(bin_x, mean_sell, "s-", color="#d7301f", label="mean Δm | sell")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlabel("size quintile (rel. median)")
    ax.set_ylabel("mean quote-aligned Δm")
    ax.set_title(
        f"GH size lens · z₀={gh_live.get('z0', gh['z0']):.3f} z₁={gh_live.get('z1', gh['z1']):.2e}"
    )
    ax.legend(fontsize=8)
    fig.savefig(OUT / "fig_gh_size_bins.png", dpi=120)
    plt.close(fig)

    figures = [
        "fig_gh_z0.png",
        "fig_mrr_decomp.png",
        "fig_hs_pi.png",
        "fig_hs_decomp.png",
        "fig_perm_impact_compare.png",
        "fig_gh_size_bins.png",
    ]

    d["figures"] = figures
    d["plot_meta"] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "gh_live": {k: gh_live.get(k) for k in ("z0", "z1", "r2", "n")},
        "days": days,
    }
    (OUT / "exp_ch14_eth_summary.json").write_text(json.dumps(d, indent=2, default=str))

    # Unified EXP_REPORT
    lines = [
        f"# Ch.14 GH / MRR / Huang–Stoll — {symbol}",
        "",
        "## Sample",
        f"- Quote-aligned Δm shared with Ch.13 (`next_mid_change`); days={days}",
        f"- GH/HS aligned n≈{gh.get('n'):,} · MRR/HS-decomp on trade Δp n≈{mrr.get('n'):,}",
        f"- HS decomp half-spread median={decomp.get('half_spread')} "
        f"(source={decomp.get('half_spread_source')})",
        "",
        "## Glosten–Harris",
        f"- z₀={gh['z0']:.4f} · z₁={gh['z1']:.6e} · R²={gh['r2']:.3f}",
        f"- train z₀={gh_tr['z0']:.4f} · test z₀={gh_te['z0']:.4f}",
        "",
        "## MRR",
        f"- θ={mrr['theta_perm']:.5f} · φ={mrr['phi_temp']:.5f} · ρ_q={mrr['rho_q']:.3f} · R²={mrr['r2']:.3f}",
        "  (note: HS-decomp companion MRR on consecutive Δp; earlier mid-aligned pass had smaller θ)",
        "",
        "## Huang–Stoll",
        f"- Lump π̂ (quote-aligned)={hs.get('pi_inv_info'):.4f} · R²={hs.get('r2'):.3f} "
        f"(train={hs_tr.get('pi_inv_info'):.4f}, test={hs_te.get('pi_inv_info'):.4f})",
        f"- Asof-mid basic π̂ (decomp script)={hs_basic_asof.get('pi_inv_info')} · "
        f"R²={hs_basic_asof.get('r2')} — weaker; prefer quote-aligned lump",
        f"- Two-way λ̂=a+b={decomp.get('lambda_ab'):.4f} · R²₂={decomp.get('r2_two_way'):.3f}",
        f"- Three-way a(AS)={decomp.get('a_adverse'):.4f} · b(inv)={decomp.get('b_inventory'):.4f} · "
        f"as_share={decomp.get('as_share'):.3f} · R²₃={decomp.get('r2_three_way'):.3f}",
        f"- Free-S two-way λ={decomp_free.get('lambda_ab'):.4f}",
        "",
        "## Decisions",
    ]
    for k, v in d["decisions"].items():
        fals = (d.get("falsifiers") or {}).get(k, "")
        lines.append(f"- `{k}`: **{v}** — {fals}")
    if d.get("blockers"):
        lines += ["", "## Blockers"] + [f"- {b}" for b in d["blockers"]]
    lines += ["", "## Figures"]
    for f in figures:
        lines.append(f"- `out/ch14_structural/{f}`")
    lines += [
        "",
        "## Desk / second-pass read",
        "- GH z₀>0 on both halves with R²≈24% — AS intercept usable; z₁ tiny ⇒ size-skew from GH alone is weak.",
        "- MRR θ>0 / φ temporary — schedule prior; ρ(q)≈0.54 is descriptive (Hold as discovery).",
        "- HS lump π Promote on quote-aligned path; three-way â(AS)<0 ⇒ no clean dealer inventory split on HL LOB.",
        "- Cross-link Ch.13: IRF perm / λ_OLS are mid-path impact; MRR/HS two-way are trade-price — same sign family.",
        "- Cross-link Ch.15: high ρ(q) + VPIN regimes are the sequential-toxicity twin of structural AS.",
    ]
    report = "\n".join(lines) + "\n"
    (OUT / f"exp_ch14_{symbol.lower()}_REPORT.md").write_text(report)
    # keep dedicated HS report
    hs_lines = [
        f"# Ch.14 Huang–Stoll spread decomposition — {symbol}",
        "",
        f"- Sample n_event={d.get('hs_sample', {}).get('n_event')} · "
        f"median half-spread={d.get('hs_sample', {}).get('half_spread_median')}",
        f"- Basic π̂ (lump α+β)={hs_basic_asof.get('pi_inv_info')} R²={hs_basic_asof.get('r2')}",
        f"- Two-way λ̂=a+b={decomp.get('lambda_ab')} "
        f"(S/2={decomp.get('half_spread')}, source={decomp.get('half_spread_source')})",
        f"- Three-way a(AS)={decomp.get('a_adverse')} b(inv)={decomp.get('b_inventory')} "
        f"as_share={decomp.get('as_share')} · π_rev={decomp.get('pi_reversal')} ρ_q={decomp.get('rho_q')}",
        f"- Mid-path a={decomp.get('a_adverse_mid')} b={decomp.get('b_inventory_mid')}",
        f"- Free-S two-way λ={decomp_free.get('lambda_ab')} β_ΔQ={decomp_free.get('beta_delta_q')}",
        f"- MRR θ={mrr.get('theta_perm')} φ={mrr.get('phi_temp')} (companion)",
        "",
        "## Decisions",
    ]
    for k, v in d["decisions"].items():
        if k.startswith("disc.hs") or k.startswith("disc.mrr") or k.startswith("disc.gh"):
            hs_lines.append(f"- `{k}`: **{v}**")
    if d.get("blockers"):
        hs_lines += ["", "## Blockers"] + [f"- {b}" for b in d["blockers"]]
    hs_lines += ["", "## Figures"] + [f"- `out/ch14_structural/{f}`" for f in figures]
    (OUT / f"exp_ch14_{symbol.lower()}_hs_REPORT.md").write_text("\n".join(hs_lines) + "\n")
    (CHAP / "EXP_REPORT.md").write_text(report)
    print(report)
    print("Wrote figures:", figures)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
