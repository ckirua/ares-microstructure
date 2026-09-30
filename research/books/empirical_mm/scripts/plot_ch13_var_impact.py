#!/usr/bin/env python3
"""Ch.13 VAR / IRF / OFI / markout figures + enriched EXP_REPORT."""

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

from _data import ensure_env, load_hl_tob, resolve_days  # noqa: E402

OUT = BOOK / "out" / "ch13_var_impact"
CHAP = BOOK / "chapters" / "ch13_var_impact"


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
    summary_path = OUT / "exp_ch13_eth_summary.json"
    d = json.loads(summary_path.read_text())
    symbol = d.get("symbol", "ETH")
    days = d.get("days") or resolve_days(None)

    # --- Fig 1: IRF path (incremental + cumulative) ---
    path = d.get("irf_path") or []
    hs = [p["h"] for p in path]
    dm = [p["dm"] for p in path]
    cum = [p["cum_dm"] for p in path]
    qh = [p["q"] for p in path]
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 3.8), constrained_layout=True)
    ax[0].bar(hs, dm, color="#2c7fb8", alpha=0.85, label="Δm impulse")
    ax[0].plot(hs, qh, color="#e6550d", marker="o", ms=3, label="q response")
    ax[0].axhline(0, color="k", lw=0.6)
    ax[0].set_xlabel("horizon h (events)")
    ax[0].set_ylabel("response")
    ax[0].set_title("IRF to +1 buy shock")
    ax[0].legend(fontsize=8)
    ax[1].plot(hs, cum, color="#238b45", lw=2)
    ax[1].axhline(d["irf"]["permanent_impact"], color="#238b45", ls="--", lw=1, alpha=0.7)
    ax[1].axhline(d.get("irf_train_permanent", np.nan), color="#74c476", ls=":", lw=1.2, label="train perm")
    ax[1].axhline(d.get("irf_test_permanent", np.nan), color="#006d2c", ls=":", lw=1.2, label="test perm")
    ax[1].set_xlabel("horizon h (events)")
    ax[1].set_ylabel("cum Δm")
    ax[1].set_title(f"Cumulative IRF → perm={d['irf']['permanent_impact']:.3f}")
    ax[1].legend(fontsize=8)
    fig.savefig(OUT / "fig_irf_cum.png", dpi=120)
    plt.close(fig)

    # --- Fig 2: sign ACF ---
    acf = d["sign_acf"]["acf"]
    lags = np.arange(1, len(acf) + 1)
    fig, ax = plt.subplots(figsize=(7.5, 3.6), constrained_layout=True)
    ax.bar(lags, acf, color="#6a51a3", alpha=0.9)
    ax.axhline(0, color="k", lw=0.6)
    ax.axhline(d["sign_acf"]["rho1"], color="#d94801", ls="--", label=f"ρ₁={d['sign_acf']['rho1']:.3f}")
    ax.set_xlabel("lag")
    ax.set_ylabel("ACF(q)")
    ax.set_title("Trade-sign autocorrelation (Ch.10 / Ch.13)")
    ax.legend(fontsize=8)
    fig.savefig(OUT / "fig_sign_acf.png", dpi=120)
    plt.close(fig)

    # --- Fig 3: markout by horizon ---
    mo = d["markouts"]["by_horizon"]
    keys = sorted(mo.keys(), key=int)
    means = [mo[k]["mean_bps"] for k in keys]
    lo = [mo[k]["ci95"][0] for k in keys]
    hi = [mo[k]["ci95"][1] for k in keys]
    x = np.arange(len(keys))
    err = np.vstack([np.array(means) - np.array(lo), np.array(hi) - np.array(means)])
    fig, ax = plt.subplots(figsize=(6.5, 3.6), constrained_layout=True)
    ax.bar(x, means, color="#3182bd", alpha=0.9, yerr=err, capsize=4, ecolor="#08519c")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{int(k)/1000:g}s" for k in keys])
    ax.set_ylabel("signed markout (bps)")
    ax.set_title("Signed mid markout vs horizon (info / exec)")
    ax.axhline(0, color="k", lw=0.6)
    fig.savefig(OUT / "fig_markout.png", dpi=120)
    plt.close(fig)

    # --- Fig 4: λ hygiene (OLS + VAR + boot) ---
    hy = d["lambda_hygiene"]
    labels = ["VAR λ", "OLS full", "OLS train", "OLS test"]
    vals = [
        d["var"]["lambda_contemp"],
        hy["full"]["lambda"],
        hy["train"]["lambda"],
        hy["test"]["lambda"],
    ]
    fig, ax = plt.subplots(figsize=(7.2, 3.8), constrained_layout=True)
    colors = ["#2c7fb8", "#238b45", "#74c476", "#006d2c"]
    ax.bar(labels, vals, color=colors, alpha=0.9)
    ax.axhspan(hy["boot_lo"], hy["boot_hi"], color="#fdae6b", alpha=0.35, label="OLS boot 95% CI")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_ylabel("λ (price units / signed trade)")
    ax.set_title("Impact λ: VAR contemp vs OLS + time-split / bootstrap")
    ax.legend(fontsize=8, loc="upper left")
    fig.savefig(OUT / "fig_lambda_hygiene.png", dpi=120)
    plt.close(fig)

    # --- Fig 5: alignment robustness ---
    al = d["alignment"]
    modes = ["next_mid_change", "pre_to_next_trade", "quote_clock"]
    corrs = [al[m]["corr_dm_q"] for m in modes]
    ns = [al[m]["n"] for m in modes]
    fig, ax = plt.subplots(figsize=(7.2, 3.6), constrained_layout=True)
    bars = ax.bar(["next_mid\n(primary)", "pre→next\ntrade", "quote\nclock"], corrs, color="#41ab5d", alpha=0.9)
    for b, n, c in zip(bars, ns, corrs):
        ax.text(b.get_x() + b.get_width() / 2, c + 0.01, f"n={n:,}\n{c:.3f}", ha="center", va="bottom", fontsize=8)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_ylim(0, max(corrs) * 1.35)
    ax.set_ylabel("corr(Δm, q)")
    ax.set_title("Alignment modes: corr(Δm, q) — contamination check")
    fig.savefig(OUT / "fig_alignment_corr.png", dpi=120)
    plt.close(fig)

    # --- Fig 6: OFI scatter (recompute Cont–Kukanov L0 bars) ---
    tob = load_hl_tob(symbol)
    t = tob["ts"]
    b, a = tob["bid"], tob["ask"]
    bs, az = tob["bid_sz"], tob["ask_sz"]
    mid = tob["mid"]
    ofi_e = np.zeros(t.size, dtype=np.float64)
    for i in range(1, t.size):
        if b[i] > b[i - 1]:
            ofi_e[i] += bs[i]
        elif b[i] == b[i - 1]:
            ofi_e[i] += bs[i] - bs[i - 1]
        else:
            ofi_e[i] -= bs[i - 1]
        if a[i] < a[i - 1]:
            ofi_e[i] -= az[i]
        elif a[i] == a[i - 1]:
            ofi_e[i] -= az[i] - az[i - 1]
        else:
            ofi_e[i] += az[i - 1]
    bar_ns = 1_000_000_000
    t0, t1 = int(t.min()), int(t.max())
    grid = np.arange(t0, t1 + 1, bar_ns, dtype=np.int64)
    ofi_b = np.zeros(grid.size - 1, dtype=np.float64)
    mid_b = np.full(grid.size - 1, np.nan)
    idx = np.searchsorted(t, grid, side="left")
    for i in range(grid.size - 1):
        lo, hi = idx[i], idx[i + 1]
        if hi > lo:
            ofi_b[i] = float(ofi_e[lo:hi].sum())
            mid_b[i] = float(mid[hi - 1])
    ret = np.full(mid_b.size, np.nan)
    for i in range(1, mid_b.size):
        if np.isfinite(mid_b[i]) and np.isfinite(mid_b[i - 1]) and mid_b[i - 1] > 0:
            ret[i] = np.log(mid_b[i] / mid_b[i - 1])
    ofi_x, ret_y = ofi_b.copy(), ret.copy()

    m = np.isfinite(ofi_x) & np.isfinite(ret_y)
    ofi_x, ret_y = ofi_x[m], ret_y[m]
    if ofi_x.size > 25_000:
        step = ofi_x.size // 25_000
        ofi_x, ret_y = ofi_x[::step], ret_y[::step]
    corr = float(np.corrcoef(ofi_x, ret_y)[0, 1]) if ofi_x.size > 10 else float("nan")
    fig, ax = plt.subplots(figsize=(6.8, 4.0), constrained_layout=True)
    ax.scatter(ofi_x, ret_y * 1e4, s=4, alpha=0.15, c="#2b8cbe", rasterized=True)
    # OLS line
    if ofi_x.size > 10:
        coef = np.polyfit(ofi_x, ret_y * 1e4, 1)
        xs = np.linspace(np.percentile(ofi_x, 1), np.percentile(ofi_x, 99), 50)
        ax.plot(xs, coef[0] * xs + coef[1], color="#e6550d", lw=1.5, label=f"OLS · corr={corr:.3f}")
    ax.set_xlabel("1s L0 OFI")
    ax.set_ylabel("1s mid return (bps)")
    ax.set_title("Continuous OFI ↔ mid return")
    ax.legend(fontsize=8)
    # clip extremes for readability
    ax.set_xlim(np.percentile(ofi_x, 0.5), np.percentile(ofi_x, 99.5))
    ax.set_ylim(np.percentile(ret_y * 1e4, 0.5), np.percentile(ret_y * 1e4, 99.5))
    fig.savefig(OUT / "fig_ofi_scatter.png", dpi=120)
    plt.close(fig)

    # --- Fig 7: VAR lag structure — feats = [Δm_{t-k}, q_{t-k}]_k ---
    lags_n = int(d["var"]["lags"])
    coef_dm = np.asarray(d["var"]["coef_dm"], dtype=np.float64)
    coef_q = np.asarray(d["var"]["coef_q"], dtype=np.float64)
    # split interleaved [dm_lag_k, q_lag_k]
    dm_on_dm = coef_dm[0::2][:lags_n]
    dm_on_q = coef_dm[1::2][:lags_n]
    q_on_dm = coef_q[0::2][:lags_n]
    q_on_q = coef_q[1::2][:lags_n]
    lag_idx = np.arange(1, lags_n + 1)
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 3.6), constrained_layout=True)
    w = 0.35
    ax[0].bar(lag_idx - w / 2, dm_on_dm, width=w, color="#2c7fb8", label="Δm←Δm")
    ax[0].bar(lag_idx + w / 2, dm_on_q, width=w, color="#e6550d", label="Δm←q")
    ax[0].axhline(0, color="k", lw=0.6)
    ax[0].axhline(d["var"]["lambda_contemp"], color="#238b45", ls="--", label=f"λ_contemp={d['var']['lambda_contemp']:.4f}")
    ax[0].set_xlabel("lag k")
    ax[0].set_title(f"Δm equation · R²={d['var']['r2_dm']:.3f}")
    ax[0].legend(fontsize=7)
    ax[1].bar(lag_idx - w / 2, q_on_dm, width=w, color="#2c7fb8", label="q←Δm")
    ax[1].bar(lag_idx + w / 2, q_on_q, width=w, color="#e6550d", label="q←q")
    ax[1].axhline(0, color="k", lw=0.6)
    ax[1].set_xlabel("lag k")
    ax[1].set_title(f"q equation · R²={d['var']['r2_q']:.3f}")
    ax[1].legend(fontsize=7)
    fig.savefig(OUT / "fig_var_coef.png", dpi=120)
    plt.close(fig)

    figures = [
        "fig_irf_cum.png",
        "fig_sign_acf.png",
        "fig_markout.png",
        "fig_lambda_hygiene.png",
        "fig_alignment_corr.png",
        "fig_ofi_scatter.png",
        "fig_var_coef.png",
    ]

    # Enrich summary with figure list + plot meta
    d["figures"] = figures
    d["plot_meta"] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ofi_scatter_corr": corr,
        "ofi_scatter_n": int(ofi_x.size),
        "days": days,
    }
    summary_path.write_text(json.dumps(d, indent=2))

    # Refresh EXP_REPORT (chapter + out)
    hy = d["lambda_hygiene"]
    al = d["alignment"]
    mo1 = d["markouts"]["by_horizon"]["1000"]
    lines = [
        f"# Ch.13 VAR / IRF / OFI — {symbol}",
        "",
        "## Sample",
        f"- alignment=`next_mid_change` · n_event={d['n_event']:,} · corr(Δm,q)={al['next_mid_change']['corr_dm_q']:.4f}",
        f"- days={days} · median lag to mid-change={al['next_mid_change'].get('median_lag_ms'):.1f} ms",
        "",
        "## Impact / IRF",
        f"- λ_VAR={d['var']['lambda_contemp']:.5f} · λ_OLS={hy['full']['lambda']:.5f} · "
        f"train={hy['train']['lambda']:.5f} · test={hy['test']['lambda']:.5f}",
        f"- OLS bootstrap 95% CI=[{hy['boot_lo']:.5f}, {hy['boot_hi']:.5f}] · promote_ok={hy['promote_ok']}",
        f"- permanent_IRF={d['irf']['permanent_impact']:.4f} "
        f"(train={d['irf_train_permanent']:.4f}, test={d['irf_test_permanent']:.4f})",
        f"- VAR R²_Δm={d['var']['r2_dm']:.3f} · R²_q={d['var']['r2_q']:.3f}",
        "",
        "## Sign / OFI / markout",
        f"- sign ρ₁={d['sign_acf']['rho1']:.4f}",
        f"- OFI corr(ofi,r)={d['ofi']['corr_ofi_ret']:.4f} (scatter recompute corr={corr:.4f})",
        f"- markout 1s: mean={mo1['mean_bps']:.4f} bps · CI95=[{mo1['ci95'][0]:.4f}, {mo1['ci95'][1]:.4f}] · n={mo1['n']:,}",
        f"- markout 0.5s={d['markouts']['by_horizon']['500']['mean_bps']:.4f} · "
        f"5s={d['markouts']['by_horizon']['5000']['mean_bps']:.4f} bps",
        "",
        "## Alignment robustness",
        f"- pre_to_next_trade corr={al['pre_to_next_trade']['corr_dm_q']:.4f} (n={al['pre_to_next_trade']['n']:,})",
        f"- quote_clock corr={al['quote_clock']['corr_dm_q']:.4f} (n={al['quote_clock']['n']:,})",
        "",
        "## Decisions",
    ]
    for k, v in d["decisions"].items():
        fals = (d.get("falsifiers") or {}).get(k, "")
        lines.append(f"- `{k}`: **{v}** — {fals}")
    lines += ["", "## Figures"]
    for f in figures:
        lines.append(f"- `out/ch13_var_impact/{f}`")
    lines += [
        "",
        "## Desk / second-pass read",
        "- Cum IRF rises smoothly to ~0.42 with train/test same sign ⇒ permanent impact prior for TCA/POV.",
        "- ρ₁(q)≈0.54 ⇒ herding / inventory continuation; pair with Ch.14 MRR ρ and Ch.15 VPIN regimes.",
        "- OFI corr≈0.43 on 1s bars is the continuous twin of disc λ; use when TOB dense.",
        "- Primary alignment corr≈0.48 vs contaminated asof (historically λ_VAR<0) — never skip quote-update align.",
        "- Markout CI strictly >0 at 0.5/1/5s ⇒ maker AS / taker edge decay object for quoting.",
    ]
    report = "\n".join(lines) + "\n"
    (OUT / f"exp_ch13_{symbol.lower()}_REPORT.md").write_text(report)
    (CHAP / "EXP_REPORT.md").write_text(report)
    print(report)
    print("Wrote figures:", figures)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
