from __future__ import annotations
#!/usr/bin/env python3
"""Build desk-synthesis figures for mn_tuwrv notebooks from existing out/ JSON.

Does not re-run multi-hour panels. Writes PNGs under out/desk_synthesis/figs/.
"""


import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

BOOK = Path(__file__).resolve().parents[1]
OUT = BOOK / "out"
FIGS = OUT / "desk_synthesis" / "figs"


def _load(rel: str):
    return json.loads((OUT / rel).read_text())


def _savefig(name: str) -> Path:
    FIGS.mkdir(parents=True, exist_ok=True)
    path = FIGS / name
    plt.tight_layout()
    plt.savefig(path, dpi=140, bbox_inches="tight")
    plt.close()
    return path


def fig_signal_board() -> Path:
    decisions = [
        ("cont.sparse_rv_only", "Kill"),
        ("cont.noise_dominates_1s_mid", "Kill"),
        ("cont.noise_trade_clock_bounce", "Kill"),
        ("cont.noise_tick_bounce_clock", "Kill"),
        ("cont.noise_mid_clock", "Hold"),
        ("cont.tsrv_first_adj", "Hold"),
        ("cont.noise_var_fifth", "Hold"),
        ("liq.noise_vs_spread", "Hold"),
        ("frag.xvenue_noise_concord", "Hold"),
    ]
    colors = {"Kill": "#b33a3a", "Hold": "#c4a035", "Promote": "#2f7d4a"}
    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    y = np.arange(len(decisions))[::-1]
    for i, (cid, dec) in enumerate(decisions):
        ax.barh(y[i], 1.0, color=colors[dec], height=0.72, edgecolor="white")
        ax.text(0.02, y[i], f"{dec:7s}  {cid}", va="center", ha="left", fontsize=10, color="white", fontweight="bold")
    ax.set_xlim(0, 1)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.set_title("MN/TSRV Pass 2.7 — signal board (0 Promote / 5 Hold / 4 Kill)")
    for spine in ax.spines.values():
        spine.set_visible(False)
    return _savefig("signal_board.png")


def fig_gate_counts() -> Path:
    counts = {"Promote": 0, "Hold": 5, "Kill": 4}
    colors = {"Promote": "#2f7d4a", "Hold": "#c4a035", "Kill": "#b33a3a"}
    fig, ax = plt.subplots(figsize=(5.5, 3.8))
    keys = list(counts)
    ax.bar(keys, [counts[k] for k in keys], color=[colors[k] for k in keys], edgecolor="white")
    for i, k in enumerate(keys):
        ax.text(i, counts[k] + 0.08, str(counts[k]), ha="center", fontsize=12, fontweight="bold")
    ax.set_ylim(0, max(counts.values()) + 1.2)
    ax.set_ylabel("candidates")
    ax.set_title("Gate counts — Pass 2.7")
    return _savefig("fig_gate_counts.png")


def fig_mc_rmse_ladder() -> Path:
    mc = _load("monte_carlo/mc_summary.json")
    est = mc["estimators"]
    order = ["fifth", "fourth", "third", "second", "first", "first_adj"]
    rmse = [est[k]["rmse"] for k in order]
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    bars = ax.bar(order, rmse, color=["#888"] * 4 + ["#4a7ab5", "#2f7d4a"])
    ax.set_yscale("log")
    ax.set_ylabel("RMSE (log)")
    ax.set_title(f"Heston MC ladder — n={mc['n_sims']} (Kill sparse: first_adj RMSE ≪ fourth)")
    ratio = est["first_adj"]["rmse"] / est["fourth"]["rmse"]
    ax.annotate(
        f"first_adj / fourth = {ratio:.2f}",
        xy=(5, est["first_adj"]["rmse"]),
        xytext=(2.2, est["fifth"]["rmse"] * 0.4),
        arrowprops=dict(arrowstyle="->", color="#333"),
        fontsize=10,
    )
    return _savefig("fig_mc_rmse_ladder.png")


def fig_clock_medians() -> Path:
    bc = _load("blocker_close/blocker_close.json")
    clocks = bc["mid_clock"]["bootstrap_all_clocks"]["clocks"]
    names = ["calendar", "trade", "tick_bounce", "mid"]
    med = []
    lo = []
    hi = []
    for n in names:
        st = clocks[n]
        med.append(st["median"])
        ci = st.get("ci95") or [np.nan, np.nan]
        lo.append(ci[0])
        hi.append(ci[1])
    # Prefer denser mid CI from mid_dense_ci
    md = bc["mid_clock"]["mid_dense_ci"]
    med[3], lo[3], hi[3] = md["median"], md["ci95"][0], md["ci95"][1]

    x = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ax.errorbar(
        x,
        med,
        yerr=[np.asarray(med) - np.asarray(lo), np.asarray(hi) - np.asarray(med)],
        fmt="o",
        color="#2c3e50",
        ecolor="#7f8c8d",
        capsize=5,
        ms=8,
    )
    ax.axhline(1.5, color="#b33a3a", ls="--", lw=1.2, label="Promote gate CI_lo > 1.5")
    ax.axhline(1.0, color="#999", ls=":", lw=1)
    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_ylabel("median fifth / fourth")
    ax.set_title("Clock bounce ratios — Pass 2.7 expand panel (bootstrap CI95)")
    ax.legend(loc="upper left", fontsize=9)
    return _savefig("fig_clock_medians.png")


def fig_mid_venue_split() -> Path:
    bc = _load("blocker_close/blocker_close.json")
    cov = bc["mid_clock"]["mid_coverage_by_venue"]
    venues = ["hyperliquid", "deribit", "kraken"]
    meds = [cov[v]["median"] for v in venues]
    ns = [cov[v]["n_mid"] for v in venues]
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    bars = ax.bar(venues, meds, color=["#4a7ab5", "#8e5aa8", "#5a9e6f"])
    for b, n, m in zip(bars, ns, meds):
        ax.text(b.get_x() + b.get_width() / 2, m + 0.15, f"n={n}\n{m:.2f}", ha="center", va="bottom", fontsize=9)
    ax.axhline(1.5, color="#b33a3a", ls="--", lw=1)
    ax.set_ylabel("median fifth/fourth (mid clock)")
    ax.set_title("Mid-clock venue split — why pooled CI stays wide")
    return _savefig("fig_mid_venue_split.png")


def fig_tsrv_oos() -> Path:
    bc = _load("blocker_close/blocker_close.json")
    t = bc["tsrv_oos"]["sparse_minus_tsrv"]
    labels = ["overall", "early", "late"]
    med = [t[k]["median"] for k in labels]
    lo = [t[k]["ci95"][0] for k in labels]
    hi = [t[k]["ci95"][1] for k in labels]
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    ax.errorbar(
        x,
        med,
        yerr=[np.asarray(med) - np.asarray(lo), np.asarray(hi) - np.asarray(med)],
        fmt="s",
        color="#2c3e50",
        ecolor="#7f8c8d",
        capsize=5,
        ms=8,
    )
    ax.axhline(0.0, color="#b33a3a", ls="--", lw=1.2, label="Promote needs CI_lo > 0")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("median (sparse − first_adj)")
    ax.set_title("Tape TSRV vs sparse — time-split OOS (Hold)")
    ax.legend(fontsize=9)
    return _savefig("fig_tsrv_oos.png")


def fig_noise_vs_spread() -> Path:
    # Prefer existing PNG if present; also rebuild from gap_close rows for notebook consistency
    gc = _load("gap_close/gap_close.json")
    rows = [r for r in gc["rows"] if r.get("ok") and (r.get("spread") or {}).get("ok")]
    noise = np.asarray([r["noise_std"] for r in rows], dtype=float)
    spread = np.asarray([r["spread"]["spread_bps_mean"] for r in rows], dtype=float)
    venues = [r["venue"] for r in rows]
    cmap = {"hyperliquid": "#4a7ab5", "deribit": "#8e5aa8", "kraken": "#5a9e6f"}
    fig, ax = plt.subplots(figsize=(6.8, 4.2))
    for v in sorted(set(venues)):
        m = np.asarray([x == v for x in venues])
        ax.scatter(spread[m], noise[m], s=36, alpha=0.75, label=v, color=cmap.get(v, "#333"))
    sf = gc["spread_falsify"]["rho_spread"]
    ax.set_xlabel("spread_bps_mean (quoted or proxy)")
    ax.set_ylabel("noise_std (Êε)")
    ax.set_title(
        f"noise vs spread — ρ={sf['rho']:.3f} CI=[{sf['lo']:.3f},{sf['hi']:.3f}] n={int(sf['n'])} → Hold"
    )

    ax.legend(fontsize=9)
    return _savefig("fig_noise_vs_spread.png")


def fig_tob_coverage() -> Path:
    bc = _load("blocker_close/blocker_close.json")
    rows = [r for r in bc["rows"] if r.get("ok")]
    # count quoted by venue
    venues = ["hyperliquid", "deribit", "kraken"]
    quoted = []
    proxy = []
    missing = []
    for v in venues:
        subv = [r for r in rows if r["venue"] == v]
        q = sum(1 for r in subv if (r.get("spread") or {}).get("quoted_available"))
        p = sum(
            1
            for r in subv
            if not (r.get("spread") or {}).get("quoted_available")
            and (r.get("spread") or {}).get("ok")
        )
        m = len(subv) - q - p
        quoted.append(q)
        proxy.append(p)
        missing.append(max(m, 0))
    x = np.arange(len(venues))
    fig, ax = plt.subplots(figsize=(6.8, 3.8))
    ax.bar(x, quoted, label="quoted TOB", color="#2f7d4a")
    ax.bar(x, proxy, bottom=quoted, label="proxy", color="#c4a035")
    ax.bar(x, missing, bottom=np.asarray(quoted) + np.asarray(proxy), label="missing/fail", color="#b33a3a")
    ax.set_xticks(x)
    ax.set_xticklabels(venues)
    ax.set_ylabel("venue-days (ok rows)")
    ax.set_title("TOB coverage — Pass 2.7 expand panel")
    ax.legend(fontsize=9)
    return _savefig("fig_tob_coverage.png")


def fig_fifth_hist() -> Path:
    bc = _load("blocker_close/blocker_close.json")
    rows = [r for r in bc["rows"] if r.get("ok")]
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.6), sharey=False)
    cal = np.asarray([r["fifth_over_fourth_cal"] for r in rows], dtype=float)
    mid = np.asarray(
        [r["fifth_over_fourth_mid"] for r in rows if np.isfinite(r.get("fifth_over_fourth_mid", np.nan))],
        dtype=float,
    )
    axes[0].hist(cal[np.isfinite(cal)], bins=18, color="#4a7ab5", edgecolor="white")
    axes[0].axvline(1.5, color="#b33a3a", ls="--")
    axes[0].set_title("calendar fifth/fourth")
    axes[0].set_xlabel("ratio")
    axes[1].hist(mid, bins=18, color="#8e5aa8", edgecolor="white")
    axes[1].axvline(1.5, color="#b33a3a", ls="--", label="gate 1.5")
    axes[1].set_title("mid-clock fifth/fourth")
    axes[1].set_xlabel("ratio")
    axes[1].legend(fontsize=8)
    fig.suptitle("Distribution of bounce ratios across venue-days", y=1.02)
    return _savefig("fig_ratio_hist.png")


def main() -> None:
    paths = [
        fig_signal_board(),
        fig_gate_counts(),
        fig_mc_rmse_ladder(),
        fig_clock_medians(),
        fig_mid_venue_split(),
        fig_tsrv_oos(),
        fig_noise_vs_spread(),
        fig_tob_coverage(),
        fig_fifth_hist(),
    ]
    # copy gap_close fig if useful
    src = OUT / "gap_close" / "fig_noise_vs_spread.png"
    if src.exists():
        dest = FIGS / "fig_noise_vs_spread_gap_close.png"
        dest.write_bytes(src.read_bytes())
        paths.append(dest)
    print(json.dumps({"figs": [str(p) for p in paths]}, indent=2))


if __name__ == "__main__":
    main()
