#!/usr/bin/env python3
"""Build desk PNGs for vpin_of notebooks from out/ JSON (no tape recompute)."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

BOOK = Path(__file__).resolve().parents[1]
OUT = BOOK / "out"
FIGS = OUT / "desk_synthesis" / "figs"


def _load(rel: str):
    p = OUT / rel
    if not p.is_file():
        return {}
    return json.loads(p.read_text())


def _lines(rel: str) -> list[dict]:
    p = OUT / rel
    if not p.is_file():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


def _savefig(name: str) -> Path:
    FIGS.mkdir(parents=True, exist_ok=True)
    path = FIGS / name
    plt.tight_layout()
    plt.savefig(path, dpi=140, bbox_inches="tight")
    plt.close()
    return path


def decision_table() -> list[tuple[str, str, str]]:
    dec = _load("pass2/decisions_pass2.json") or _load("vpin_panel/decisions.json")
    rows = []
    for t in dec.get("decision_table", []):
        rows.append((t["id"], t["decision"], t.get("evidence", "")[:100]))
    return rows


def fig_signal_board() -> Path:
    board = decision_table()
    colors = {"Kill": "#b33a3a", "Hold": "#c4a035", "Park": "#6c757d", "Promote": "#2f7d4a"}
    fig, ax = plt.subplots(figsize=(10.0, max(4.2, 0.42 * len(board))))
    y = np.arange(len(board))[::-1]
    for i, (cid, dec, _note) in enumerate(board):
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
    dec = _load("vpin_panel/decisions.json")
    n_ok = dec.get("n_ok", "?")
    p2 = _load("pass2/pass2_summary.json")
    tag = "Pass 2" if p2 else "Pass 1"
    ax.set_title(f"vpin_of {tag} board — n_ok={n_ok} (HL+Deribit warehouse tape)")
    ax.set_xlim(0, 1)
    ax.set_yticks([])
    ax.set_xticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    return _savefig("signal_board.png")


def fig_bucket_calibration() -> Path | None:
    cal = _load("vpin_panel/bucket_calibration.json")
    grid = cal.get("grid")
    if not grid:
        return None
    g = pd.DataFrame(grid)
    fig, ax = plt.subplots(figsize=(9.0, 4.0))
    ax.bar(g["method"].astype(str), g["mean_vpin"], color="#3d5a80", alpha=0.88)
    ax.set_ylabel("mean rolling VPIN")
    ax.set_title(
        f"Bucket grid — {cal.get('venue')} {cal.get('symbol')} {cal.get('day')} "
        f"(SoT median×50 = {cal.get('default_bucket_volume')})"
    )
    plt.xticks(rotation=35, ha="right")
    return _savefig("fig_bucket_calibration.png")


def fig_vpin_by_day() -> Path | None:
    rows = [r for r in _lines("vpin_panel/rows.jsonl") if r.get("ok")]
    if not rows:
        return None
    d = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(10.0, 4.2))
    for (v, s), g in d.groupby(["venue", "symbol"]):
        g = g.sort_values("day")
        ax.plot(g["day"], g["mean_vpin"], marker=".", ms=4, label=f"{v} {s}", alpha=0.85)
    ax.set_ylabel("day mean VPIN")
    ax.set_title("Complete-day mean VPIN — Pass 1 panel")
    ax.legend(fontsize=8, ncol=2)
    plt.xticks(rotation=45, ha="right")
    return _savefig("fig_vpin_by_day.png")


def fig_xvenue_scatter() -> Path | None:
    rows = [r for r in _lines("vpin_panel/rows.jsonl") if r.get("ok")]
    if not rows:
        return None
    by_key: dict[tuple[str, str, str], float] = {}
    for r in rows:
        if r["venue"] in ("hyperliquid", "deribit"):
            by_key[(r["symbol"], r["day"], r["venue"])] = float(r["mean_vpin"])
    xs, ys, labs = [], [], []
    for sym in sorted({k[0] for k in by_key}):
        days = sorted({k[1] for k in by_key if k[0] == sym})
        for d in days:
            a = by_key.get((sym, d, "hyperliquid"))
            b = by_key.get((sym, d, "deribit"))
            if a is not None and b is not None:
                xs.append(a)
                ys.append(b)
                labs.append(sym)
    if len(xs) < 3:
        return None
    fig, ax = plt.subplots(figsize=(5.5, 5.0))
    for sym in sorted(set(labs)):
        idx = [i for i, s in enumerate(labs) if s == sym]
        ax.scatter([xs[i] for i in idx], [ys[i] for i in idx], label=sym, s=28, alpha=0.75)
    lo = min(min(xs), min(ys))
    hi = max(max(xs), max(ys))
    ax.plot([lo, hi], [lo, hi], "k--", alpha=0.25, lw=1)
    dec = _load("pass2/decisions_pass2.json") or _load("vpin_panel/decisions.json")
    xv = (dec.get("falsifiers") or {}).get("xvenue_spearman") or {}
    if not xv:
        xv = (_load("pass2/xvenue_concord.json") or {}).get("spearman") or {}
    ax.set_xlabel("HL mean VPIN")
    ax.set_ylabel("Deribit mean VPIN")
    ax.set_title(f"HL↔DB paired days (ρ={xv.get('rho', float('nan')):.3f}, n={int(xv.get('n', 0))})")
    ax.legend()
    return _savefig("fig_xvenue_scatter.png")


def fig_pin_proxy_spearman() -> Path | None:
    blocks = _load("vpin_panel/pin_compare.json")
    if not blocks:
        return None
    rows = []
    for b in blocks:
        rho = b.get("day_mean_vpin_vs_pin_proxy_spearman") or {}
        rows.append(
            {
                "cell": f"{b.get('venue')} {b.get('symbol')}",
                "rho": rho.get("rho"),
                "lo": rho.get("lo"),
                "hi": rho.get("hi"),
                "n": rho.get("n"),
                "mle_ok": (b.get("mle") or {}).get("ok"),
            }
        )
    df = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(8.0, 3.8))
    x = np.arange(len(df))
    y = df["rho"].astype(float)
    yerr = [
        y - df["lo"].astype(float),
        df["hi"].astype(float) - y,
    ]
    ax.errorbar(x, y, yerr=yerr, fmt="o", color="#ee6c4d", capsize=4)
    ax.axhline(0, color="gray", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(df["cell"], rotation=25, ha="right")
    ax.set_ylabel("Spearman ρ (day mean VPIN vs pin_proxy)")
    ax.set_title("PIN proxy vs VPIN — MLE PIN unavailable on tape filters (Hold)")
    return _savefig("fig_pin_proxy_spearman.png")


def fig_falsifier_rates() -> Path | None:
    dec = _load("vpin_panel/decisions.json")
    fals = dec.get("falsifiers") or {}
    if not fals:
        return None
    labels = ["side_shuffle\npass_rate", "time_split\nstable_rate"]
    vals = [fals.get("side_shuffle_pass_rate"), fals.get("time_split_stable_rate")]
    fig, ax = plt.subplots(figsize=(5.5, 3.6))
    ax.bar(labels, vals, color=["#2f7d4a", "#2f7d4a"], alpha=0.85)
    ax.axhline(0.55, color="#c4a035", ls="--", label="shuffle gate 0.55")
    ax.axhline(0.70, color="#3d5a80", ls="--", label="time-split gate 0.70")
    ax.set_ylim(0, 1.05)
    ax.set_title("Pass 1 falsifiers (real-tape sign nulls)")
    ax.legend(fontsize=8)
    return _savefig("fig_falsifier_rates.png")


def main() -> None:
    paths = []
    for fn in (
        fig_signal_board,
        fig_bucket_calibration,
        fig_vpin_by_day,
        fig_xvenue_scatter,
        fig_pin_proxy_spearman,
        fig_falsifier_rates,
    ):
        p = fn()
        if p:
            paths.append(p)
            print("wrote", p.relative_to(BOOK))
    print("done", len(paths), "figures")


if __name__ == "__main__":
    main()
