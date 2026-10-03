#!/usr/bin/env python3
"""Build complementary synthesis PNGs for cd_me notebooks from out/ JSON.

Does not re-run warehouse panels. Writes under out/desk_synthesis/figs/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

BOOK = Path(__file__).resolve().parents[1]
OUT = BOOK / "out"
FIGS = OUT / "desk_synthesis" / "figs"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _nb_common import (  # noqa: E402
    SIGNAL_BOARD,
    day_summary_table,
    expand_dcm_hourly,
    expand_pim_hourly,
    load_json,
)


def _savefig(name: str) -> Path:
    FIGS.mkdir(parents=True, exist_ok=True)
    path = FIGS / name
    plt.tight_layout()
    plt.savefig(path, dpi=140, bbox_inches="tight")
    plt.close()
    return path


def fig_signal_board() -> Path:
    colors = {"Kill": "#b33a3a", "Hold": "#c4a035", "Park": "#6c757d", "Promote": "#2f7d4a"}
    fig, ax = plt.subplots(figsize=(10.0, 5.2))
    y = np.arange(len(SIGNAL_BOARD))[::-1]
    for i, (cid, dec, _note) in enumerate(SIGNAL_BOARD):
        ax.barh(y[i], 1.0, color=colors.get(dec, "#888"), height=0.72, edgecolor="white")
        ax.text(
            0.02,
            y[i],
            f"{dec:7s}  {cid}",
            va="center",
            ha="left",
            fontsize=9,
            color="white",
            fontweight="bold",
        )
    ax.set_xlim(0, 1)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.set_title("cd_me Pass-2 board — 0 Promote · Hold monitors · Kill α · Park LSTAR/model")
    for spine in ax.spines.values():
        spine.set_visible(False)
    return _savefig("signal_board.png")


def fig_pim_tod() -> Path | None:
    panel = load_json(OUT / "pim_vloop_tcost" / "panel_rows.json")
    if not panel:
        return None
    h = expand_pim_hourly(panel)
    tod = h.groupby("hour_utc")["pim"].mean()
    fig, ax = plt.subplots(figsize=(8.0, 3.6))
    ax.bar(tod.index, tod.values, color="#3d5a80")
    ax.set_xlabel("UTC hour")
    ax.set_ylabel("mean PIM")
    ax.set_title("PIM time-of-day (HL↔Deribit real quotes; certified panel)")
    return _savefig("fig_pim_tod.png")


def fig_vloop_tcost() -> Path | None:
    panel = load_json(OUT / "pim_vloop_tcost" / "panel_rows.json")
    if not panel:
        return None
    h = expand_pim_hourly(panel)
    ok = h[np.isfinite(h["vloop"]) & np.isfinite(h["tcost"])]
    fig, ax = plt.subplots(figsize=(5.8, 4.2))
    ax.scatter(ok["vloop"], ok["tcost"], s=22, alpha=0.65, c="#ee6c4d")
    ax.set_xlabel("VLOOP")
    ax.set_ylabel("TCOST")
    corr = float(ok["vloop"].corr(ok["tcost"])) if len(ok) > 2 else float("nan")
    ax.set_title(f"Hourly VLOOP vs TCOST (corr={corr:.3f})")
    return _savefig("fig_vloop_tcost_scatter.png")


def fig_elasticity_scatter() -> Path | None:
    panel = load_json(OUT / "dcm_proxies" / "panel_rows.json")
    if not panel:
        return None
    h = expand_dcm_hourly(panel)
    ok = h[np.isfinite(h["pim"]) & np.isfinite(h["notional"])]
    fig, ax = plt.subplots(figsize=(6.2, 4.2))
    sc = ax.scatter(np.log1p(ok["notional"]), ok["pim"], c=ok["dcm"], cmap="coolwarm", s=30, alpha=0.8)
    ax.set_xlabel("log1p(notional)")
    ax.set_ylabel("PIM")
    ax.set_title("Elasticity scatter colored by DCM̂")
    fig.colorbar(sc, ax=ax, label="DCM̂")
    return _savefig("fig_elasticity_scatter.png")


def fig_day_pim_means() -> Path | None:
    panel = load_json(OUT / "pim_vloop_tcost" / "panel_rows.json")
    if not panel:
        return None
    tbl = day_summary_table(panel)
    ok = tbl[tbl["ok"] == True]  # noqa: E712
    fig, ax = plt.subplots(figsize=(9.0, 3.6))
    ax.bar(ok["day"], ok["pim_mean"], color="#3d5a80")
    ax.tick_params(axis="x", rotation=70)
    ax.set_ylabel("pim_mean")
    ax.set_title(
        f"Day-mean PIM — certified real quotes (n={len(ok)}; HL↔DB; KR=spot_l2 only)"
    )
    return _savefig("fig_day_pim_means_certified.png")


def main() -> None:
    written = []
    for fn in (
        fig_signal_board,
        fig_pim_tod,
        fig_vloop_tcost,
        fig_elasticity_scatter,
        fig_day_pim_means,
    ):
        p = fn()
        if p is not None:
            written.append(p)
            print("wrote", p.relative_to(BOOK))
    meta = {
        "ok": True,
        "figs": [str(p) for p in written],
        "note": "desk_synthesis companion figs from out/ JSON; no warehouse re-pull",
    }
    FIGS.mkdir(parents=True, exist_ok=True)
    (OUT / "desk_synthesis" / "summary.json").write_text(json.dumps(meta, indent=2) + "\n")
    print("done", len(written), "figs")


if __name__ == "__main__":
    main()
