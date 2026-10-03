#!/usr/bin/env python3
"""Build complementary synthesis PNGs for squeeze_metrics notebooks from out/ JSON.

Does not re-run warehouse panels. Writes under out/desk_synthesis/figs/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

BOOK = Path(__file__).resolve().parents[1]
OUT = BOOK / "out"
FIGS = OUT / "desk_synthesis" / "figs"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _nb_common import SIGNAL_BOARD, gex_day_table, load_json, safe_corr  # noqa: E402
from certified_panel import load_certified  # noqa: E402


def _savefig(name: str) -> Path:
    FIGS.mkdir(parents=True, exist_ok=True)
    path = FIGS / name
    plt.tight_layout()
    plt.savefig(path, dpi=140, bbox_inches="tight")
    plt.close()
    return path


def fig_signal_board() -> Path:
    colors = {"Kill": "#b33a3a", "Hold": "#c4a035", "Park": "#6c757d", "Promote": "#2f7d4a"}
    fig, ax = plt.subplots(figsize=(10.0, 5.8))
    y = np.arange(len(SIGNAL_BOARD))[::-1]
    for i, (cid, dec, _note) in enumerate(SIGNAL_BOARD):
        ax.barh(y[i], 1.0, color=colors.get(dec, "#888"), height=0.72, edgecolor="white")
        ax.text(
            0.02,
            y[i],
            f"{dec:7s}  {cid}",
            va="center",
            ha="left",
            fontsize=8.5,
            color="white",
            fontweight="bold",
        )
    ax.set_xlim(0, 1)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.set_title("squeeze_metrics board — 0 Promote · Hold monitors · Kill TOB-cross α / synth")
    for spine in ax.spines.values():
        spine.set_visible(False)
    return _savefig("signal_board.png")


def _ok_table():
    gex = load_json(OUT / "gex_implied_book" / "summary.json") or {}
    panel = load_json(OUT / "gex_implied_book" / "panel_rows.json") or gex.get("rows") or []
    tbl = gex_day_table(panel, load_certified())
    if tbl.empty:
        return tbl
    return tbl[tbl["ok"] == True]


def fig_gex_bars() -> Path | None:
    ok = _ok_table()
    if ok.empty:
        return None
    fig, ax = plt.subplots(figsize=(9.0, 3.8))
    ax.bar(ok["day"], ok["gex"], color="#3d5a80")
    ax.axhline(0, color="k", lw=0.8)
    ax.tick_params(axis="x", rotation=70)
    ax.set_title("Day GEX (PROXY_trade_flow_DDOI · BS γ)")
    ax.set_ylabel("GEX")
    return _savefig("fig_gex_day.png")


def fig_gex_vs_rv() -> Path | None:
    ok = _ok_table()
    if ok.empty:
        return None
    fig, ax = plt.subplots(figsize=(5.8, 4.2))
    ax.scatter(ok["gex"], ok["hl_rv"], s=50, c="#ee6c4d")
    for _, r in ok.iterrows():
        ax.annotate(str(r["day"])[5:], (r["gex"], r["hl_rv"]), fontsize=7)
    corr = safe_corr(ok["gex"], ok["hl_rv"])
    ax.set_xlabel("GEX")
    ax.set_ylabel("HL RV")
    ax.set_title(f"GEX vs HL RV (corr={corr})")
    return _savefig("fig_gex_vs_rv.png")


def fig_gexplus_scarce() -> Path | None:
    ok = _ok_table()
    if ok.empty:
        return None
    fig, ax = plt.subplots(figsize=(9.0, 3.8))
    colors = ["#ee6c4d" if bool(s) else "#98c1d9" for s in ok["scarce"]]
    ax.bar(ok["day"], ok["gex_plus"], color=colors)
    ax.axhline(0, color="k", lw=0.8)
    ax.tick_params(axis="x", rotation=70)
    ax.set_title("GEX+ by day (red=scarce)")
    return _savefig("fig_gexplus_scarce.png")


def main() -> None:
    written = [fig_signal_board()]
    for fn in (fig_gex_bars, fig_gex_vs_rv, fig_gexplus_scarce):
        p = fn()
        if p:
            written.append(p)
    summary = {
        "figs": [str(p.relative_to(BOOK)) for p in written],
        "promote": False,
        "kill_tob_cross_alpha": True,
        "decision_ceiling": "Hold",
    }
    (OUT / "desk_synthesis").mkdir(parents=True, exist_ok=True)
    (OUT / "desk_synthesis" / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
