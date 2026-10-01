from __future__ import annotations
#!/usr/bin/env python3
"""Ch.18–21 Part III figures from exp_ch18_eth_summary.json (+ light report refresh)."""


import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BOOK = Path(__file__).resolve().parents[1]
OUT = BOOK / "out" / "ch18_limit_orders"
CHAP = BOOK / "chapters" / "ch18_limit_orders"


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
    OUT.mkdir(parents=True, exist_ok=True)
    _style()
    summary_path = OUT / "exp_ch18_eth_summary.json"
    d = json.loads(summary_path.read_text())

    # --- Fig 1: time to touch by offset ---
    ttt = d["time_to_touch"]["by_offset"]
    offs = sorted(ttt.keys(), key=int)
    rates = [ttt[k]["touch_rate"] for k in offs]
    means = [ttt[k]["mean_touch_ms"] for k in offs]
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 3.7), constrained_layout=True)
    x = np.arange(len(offs))
    ax[0].bar(x, rates, color="#2c7fb8", alpha=0.9)
    ax[0].set_xticks(x)
    ax[0].set_xticklabels([f"+{k} tick" for k in offs])
    ax[0].set_ylabel("touch rate (≤30s)")
    ax[0].set_title("CMSW-style hit proxy vs offset")
    ax[1].plot(x, means, marker="o", color="#e6550d", lw=2)
    ax[1].set_xticks(x)
    ax[1].set_xticklabels([f"+{k}" for k in offs])
    ax[1].set_ylabel("mean touch ms (uncensored)")
    ax[1].set_title("Time-to-touch rises in offset")
    fig.savefig(OUT / "fig_time_to_touch.png", dpi=120)
    plt.close(fig)

    # --- Fig 2: size-touch survival ---
    sts = d["size_at_touch_survival"]
    by_q = sts["by_size_q"]
    qs = sorted(by_q.keys(), key=float)
    fill_r = [by_q[k]["fill_proxy_rate"] for k in qs]
    fill_ms = [by_q[k]["mean_fill_ms"] for k in qs]
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 3.7), constrained_layout=True)
    x = np.arange(len(qs))
    ax[0].bar(x, fill_r, color="#238b45", alpha=0.9)
    ax[0].set_xticks(x)
    ax[0].set_xticklabels([f"q{k}" for k in qs])
    ax[0].set_ylabel("fill_proxy rate")
    ax[0].set_title(f"Size-touch survival (mono={sts.get('size_monotone_lower_fill')})")
    ax[1].plot(x, fill_ms, marker="s", color="#6a51a3", lw=2)
    ax[1].set_xticks(x)
    ax[1].set_xticklabels([f"q{k}" for k in qs])
    ax[1].set_ylabel("mean fill_proxy ms")
    ax[1].set_title("Larger size → slower fill proxy")
    fig.savefig(OUT / "fig_size_touch_survival.png", dpi=120)
    plt.close(fig)

    # --- Fig 3: cancel vs fill ---
    dep = d["tob_depletion_cancel_proxy"]
    sides = ["bid", "ask", "pooled"]
    labels = []
    cancel_s, fill_s, mixed_s = [], [], []
    for s in sides:
        block = dep["sides"][s] if s in dep["sides"] else dep["pooled"]
        labels.append(s)
        cancel_s.append(block["cancel_proxy_share"])
        fill_s.append(block["fill_proxy_share"])
        mixed_s.append(block["mixed_share"])
    fig, ax = plt.subplots(figsize=(7.2, 3.8), constrained_layout=True)
    x = np.arange(len(labels))
    w = 0.25
    ax.bar(x - w, cancel_s, w, label="cancel", color="#e6550d", alpha=0.9)
    ax.bar(x, fill_s, w, label="fill", color="#2c7fb8", alpha=0.9)
    ax.bar(x + w, mixed_s, w, label="mixed", color="#9e9ac8", alpha=0.9)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("share of depletions")
    ax.set_title("TOB depletion: cancel ≫ fill (public-tape proxy)")
    ax.legend(fontsize=8)
    fig.savefig(OUT / "fig_cancel_vs_fill.png", dpi=120)
    plt.close(fig)

    # --- Fig 4: Sandas depth schedule ---
    sand = d["sandas_depth_moments"]
    decay = sand.get("pooled_decay_Qk_over_Q0") or sand.get("bid", {}).get("decay_Qk_over_Q0")
    behind = sand.get("mean_behind_touch_decay")
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 3.7), constrained_layout=True)
    if decay:
        lv = np.arange(len(decay))
        ax[0].plot(lv, decay, marker="o", color="#08519c", lw=2)
        ax[0].axhline(1.0, color="k", lw=0.5)
        ax[0].set_xlabel("level k")
        ax[0].set_ylabel(r"$E[Q_k]/E[Q_0]$")
        ax[0].set_title(f"Sandas L1 depth decay (behind={behind:.2f})" if behind else "Sandas L1 depth decay")
    for side, color in (("bid", "#2c7fb8"), ("ask", "#e6550d")):
        mq = sand.get(side, {}).get("mean_Q")
        if mq:
            ax[1].plot(np.arange(len(mq)), mq, marker="o", color=color, lw=1.5, label=side)
    ax[1].set_xlabel("level k")
    ax[1].set_ylabel("mean depth (lots)")
    ax[1].set_title("Mean L1 schedule (bid/ask)")
    ax[1].legend(fontsize=8)
    if ax[1].lines:
        ys = np.concatenate([np.asarray(ln.get_ydata(), dtype=float) for ln in ax[1].lines])
        ypos = ys[np.isfinite(ys) & (ys > 0)]
        if ypos.size and float(np.nanmax(ypos)) / float(np.nanmin(ypos)) > 50:
            ax[1].set_yscale("log")
    fig.savefig(OUT / "fig_sandas_depth.png", dpi=120)
    plt.close(fig)

    # --- Fig 5: resilience + refill ---
    res = d.get("resilience_trade") or {}
    refill = d.get("same_side_refill", {})
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 3.7), constrained_layout=True)
    hz = res.get("horizon_ms") or []
    dr = res.get("mean_depth_ratio") or []
    if hz and dr:
        ax[0].plot([h / 1000 for h in hz], dr, marker="o", color="#238b45", lw=2)
        ax[0].axhline(1.0, color="k", lw=0.6, ls=":")
        ax[0].set_xlabel("horizon (s)")
        ax[0].set_ylabel("mean depth_ratio")
        ax[0].set_title("L0 resilience after trade")
    # refill rates bid/ask @ horizons
    horizons = refill.get("horizons_ms") or [100, 500, 1000, 5000]
    for side, color in (("bid", "#2c7fb8"), ("ask", "#e6550d")):
        by_h = refill.get("sides", {}).get(side, {}).get("by_horizon", {})
        ys = [by_h.get(str(h), {}).get("refill_rate", np.nan) for h in horizons]
        ax[1].plot([h / 1000 for h in horizons], ys, marker="o", color=color, lw=2, label=side)
    ax[1].set_xlabel("horizon (s)")
    ax[1].set_ylabel("refill_rate")
    ax[1].set_title("Same-side refill after depth drop")
    ax[1].legend(fontsize=8)
    fig.savefig(OUT / "fig_resilience_refill.png", dpi=120)
    plt.close(fig)

    # --- Fig 6: Parlour + LO clocks ---
    parl = d["parlour"]
    clocks = d["lob_clocks"]
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 3.7), constrained_layout=True)
    names = ["same_ask↔sell", "same_bid↔buy", "opp_bid↔sell", "opp_ask↔buy"]
    keys = ["same_ask_vs_sell", "same_bid_vs_buy", "opp_bid_vs_sell", "opp_ask_vs_buy"]
    rs = [parl[k]["r"] for k in keys]
    los = [parl[k]["lo"] for k in keys]
    his = [parl[k]["hi"] for k in keys]
    x = np.arange(len(names))
    err = np.vstack([np.array(rs) - np.array(los), np.array(his) - np.array(rs)])
    ax[0].bar(x, rs, color="#6a51a3", alpha=0.9, yerr=err, capsize=3, ecolor="#3f007d")
    ax[0].axhline(0, color="k", lw=0.6)
    ax[0].set_xticks(x)
    ax[0].set_xticklabels(names, rotation=20, ha="right")
    ax[0].set_ylabel("corr")
    ax[0].set_title("Parlour depth ↔ aggressor")
    # clocks summary bars
    lam = clocks.get("cont_intensity", {}).get("mean_lambda", np.nan)
    ac1 = clocks.get("disc_event_ac1", np.nan)
    ac1_c = clocks.get("cont_intensity", {}).get("ac1", np.nan)
    ax[1].bar(
        [0, 1, 2],
        [lam, ac1, ac1_c],
        color=["#2c7fb8", "#e6550d", "#238b45"],
        alpha=0.9,
    )
    ax[1].set_xticks([0, 1, 2])
    ax[1].set_xticklabels(["λ̂ LO/s", "disc event ac1", "count ac1"])
    ax[1].axhline(0, color="k", lw=0.6)
    ax[1].set_title(f"LOB clocks (n_events={clocks.get('n_events')})")
    fig.savefig(OUT / "fig_parlour_lob_clocks.png", dpi=120)
    plt.close(fig)

    figures = [
        "fig_time_to_touch.png",
        "fig_size_touch_survival.png",
        "fig_cancel_vs_fill.png",
        "fig_sandas_depth.png",
        "fig_resilience_refill.png",
        "fig_parlour_lob_clocks.png",
    ]

    d["figures"] = figures
    d["plot_meta"] = {
        "script": "plot_ch18_limit_orders.py",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    summary_path.write_text(json.dumps(d, indent=2, default=str))

    # refresh chapter EXP_REPORT lightly with figure list
    report_path = CHAP / "EXP_REPORT.md"
    if report_path.exists():
        txt = report_path.read_text()
        if "## Figures" not in txt:
            txt = txt.rstrip() + "\n\n## Figures\n\n" + "\n".join(f"- `{f}`" for f in figures) + "\n"
            report_path.write_text(txt)
            (OUT / "exp_ch18_eth_REPORT.md").write_text(txt)

    print("wrote", OUT)
    for f in figures:
        p = OUT / f
        print(f, p.stat().st_size if p.exists() else 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
