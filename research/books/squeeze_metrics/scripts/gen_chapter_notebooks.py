#!/usr/bin/env python3
"""Generate / overwrite squeeze_metrics chapter notebooks + desk / info boards.

Run from repo root or this scripts/ dir. Does not touch Pass-1 experiment scripts.
"""

from __future__ import annotations

import json
from pathlib import Path

BOOK = Path(__file__).resolve().parents[1]
CH = BOOK / "chapters"
NB = BOOK / "notebooks"


def md(s: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": _src(s)}


def code(s: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": _src(s),
    }


def _src(s: str) -> list[str]:
    if not s.endswith("\n"):
        s += "\n"
    return s.splitlines(keepends=True)


def write_nb(path: Path, cells: list[dict], title: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
            "squeeze_metrics_title": title,
        },
        "cells": cells,
    }
    path.write_text(json.dumps(nb, indent=1) + "\n")
    print("wrote", path.relative_to(BOOK), "cells", len(cells))


BOOT = r'''
from pathlib import Path
import json, os, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("module://matplotlib_inline.backend_inline")
import matplotlib.pyplot as plt
from IPython.display import Image, display, Markdown

BOOK = Path(os.environ.get("ARES_MICROSTRUCTURE") or (Path.home() / "srv" / "ares-microstructure")) / "research" / "books" / "squeeze_metrics"
OUT = BOOK / "out"
SCRIPTS = BOOK / "scripts"
ROOT = BOOK.parents[2]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT))
from _nb_common import (
    load_json, gex_day_table, safe_corr, partial_corr_vs_rv, lead_lag_day, SIGNAL_BOARD,
)
from certified_panel import load_certified, primary_days, spot_l2_days, gex_panel_days, DDOI_LABEL, GEX_PROXY_LABEL
from research.lib import squeeze  # noqa: E402

plt.rcParams.update({"figure.dpi": 110, "axes.grid": True, "grid.alpha": 0.25})

def show_pngs(fig_dir: Path, pattern="*.png"):
    if not fig_dir.is_dir():
        print("no figs dir", fig_dir)
        return
    for p in sorted(fig_dir.glob(pattern)):
        display(Markdown(f"**{p.name}** — `{p.relative_to(BOOK)}`"))
        display(Image(filename=str(p)))

def print_board(rows=None):
    rows = rows or SIGNAL_BOARD
    print(f"{'id':34s} {'gate':6s} note")
    print("-" * 88)
    for i, g, n in rows:
        print(f"{i:34s} {g:6s} {n}")

CERT = load_certified()
PRIMARY = primary_days(CERT)
SPOT = spot_l2_days(CERT)
GEX_DAYS = gex_panel_days(CERT)
print("BOOK", BOOK)
print("certified primary n=", len(PRIMARY), PRIMARY)
print("panel_gex_options n=", len(GEX_DAYS), GEX_DAYS)
print("spot_l2 subpanel n=", len(SPOT), SPOT)
print("DDOI label", DDOI_LABEL, "| GEX proxy", GEX_PROXY_LABEL)
print("trade_synth QUARANTINED — never primary; warehouse OI futures-only unused")
'''.strip()


def ch00() -> list[dict]:
    return [
        md(
            """# Ch.00 — Overview: The Implied Order Book (GEX Ed.)

**Paper:** SqueezeMetrics / GEX Ed., *The Implied Order Book* (6 July 2020)  
**NOTES:** [`NOTES.md`](NOTES.md) · **SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md)

Core claim: options dealers' **gamma / vanna** invent an *implied* limit order book that can absorb or amplify spot moves. Desk maps SPX pit GEX → **Deribit ETH options IV + PROXY_trade_flow_DDOI** (warehouse OI is **futures-only**) on certified `panel_gex_options` **n=9**. Visible TOB co-move = context only — **Kill** TOB-cross α. `trade_synth` **QUARANTINED**.
"""
        ),
        code(BOOT),
        md(
            r"""## Crypto map vs paper objects

| Paper | Desk |
|-------|------|
| SPX options chain / pit dealers | Deribit ETH options `implied_vol` + trade tape |
| DDOI (trade dir + ΔOI) | **PROXY_trade_flow_DDOI** (aggressor × qty); futures OI unused |
| GEX = Σ DDOI · γ · $ | `squeeze.chain_exposures` / `aggregate_gex` — `BS_GEX_trade_flow_DDOI` |
| VEX = Σ DDOI · ∂δ/∂σ · $ | Same with BS vanna |
| GEX+ / abundance maps | GEX+VEX; scarce flag vs HL range/RV |
| Visible LOB “bluff” | HL/Deribit TOB + Kraken `spot_l2` — **Kill** as α |
| RTH session | **UTC-day** panels; 24/7 tape |
"""
        ),
        code(
            r'''
gex = load_json(OUT / "gex_implied_book" / "summary.json")
ddoi = load_json(OUT / "ddoi_positions" / "summary.json")
vex = load_json(OUT / "vex_vanna" / "summary.json")
sq = load_json(OUT / "squeeze_regimes" / "summary.json")
comp = load_json(OUT / "panel_completeness" / "certified_panels.json")
print("GEX n_ok", None if not gex else gex.get("n_ok"), "corr_gex_hl_rv", None if not gex else gex.get("corr_gex_hl_rv"))
print("DDOI n_ok", None if not ddoi else ddoi.get("n_ok"), "label", None if not ddoi else ddoi.get("label"))
print("VEX n_ok", None if not vex else vex.get("n_ok"), "corr_vex_range", None if not vex else vex.get("corr_vex_hl_range"))
print("squeeze n_ok", None if not sq else sq.get("n_ok"), "n_scarce", None if not sq else sq.get("n_scarce"))
print("primary panel", (comp or {}).get("primary", {}).get("panel"), "n", (comp or {}).get("primary", {}).get("n"))
print("blockers", (comp or {}).get("blockers"))
'''
        ),
        md("## Pass-1 scoreboard snapshot"),
        code(
            r'''
rows = (gex or {}).get("rows") or load_json(OUT / "gex_implied_book" / "panel_rows.json") or []
tbl = gex_day_table(rows, CERT)
display(tbl.round(4) if len(tbl) else tbl)

fig, axes = plt.subplots(1, 3, figsize=(12.5, 3.6))
ok = tbl[tbl["ok"] == True] if len(tbl) else tbl
if len(ok):
    axes[0].bar(ok["day"], ok["gex"], color="#3d5a80")
    axes[0].tick_params(axis="x", rotation=70)
    axes[0].set_title("Day GEX (PROXY DDOI · BS γ)")
    axes[0].axhline(0, color="k", lw=0.8)
    axes[1].scatter(ok["gex"], ok["hl_rv"], c="#ee6c4d", s=40)
    axes[1].set_xlabel("GEX"); axes[1].set_ylabel("HL RV"); axes[1].set_title("GEX vs HL RV")
    colors = ["#3d5a80" if m == "spot_l2" else "#98c1d9" for m in ok["kraken"]]
    axes[2].bar(ok["day"], ok["hl_range"], color=colors)
    axes[2].tick_params(axis="x", rotation=70)
    axes[2].set_title("HL range (navy=spot_l2)")
else:
    for ax in axes:
        ax.text(0.5, 0.5, "run exp_gex_panel.py", ha="center", transform=ax.transAxes)
plt.tight_layout(); plt.show()
print("ddoi modes:", ok["ddoi_mode"].value_counts().to_dict() if len(ok) else {})
print("kraken modes:", ok["kraken"].value_counts().to_dict() if len(ok) else {})
'''
        ),
        md(
            """## Reading order

1. `ddoi_positions` — PROXY_trade_flow_DDOI coverage  
2. `gex_implied_book` — GEX vs RV/range  
3. `vex_vanna` — VEX / GEX+  
4. `squeeze_regimes` — scarcity / stress–calm  
5. `robustness` — falsifier checklist  
6. `paper_shadow` — living monitor (`live_orders=false`)

Desk rollup: [`../../notebooks/desk_synthesis.ipynb`](../../notebooks/desk_synthesis.ipynb) · Info board: [`../../notebooks/info_stats_board.ipynb`](../../notebooks/info_stats_board.ipynb).
"""
        ),
        md("## Signal board"),
        code(
            r'''
print_board()
print("\\n0 Promote · Hold monitors · Kill TOB-cross α · Kill trade_synth")
'''
        ),
    ]


def ddoi_nb() -> list[dict]:
    return [
        md(
            """# DDOI positions — PROXY_trade_flow_DDOI

**Paper:** Dealer Directional OI (PDF p. 3) · **NOTES:** [`NOTES.md`](NOTES.md) · **EXP:** [`EXP_REPORT.md`](EXP_REPORT.md)  
**Artifacts:** `out/ddoi_positions/` · **Lib:** `research.lib.squeeze`

Paper DDOI uses trade direction **and** verified ΔOI. Desk warehouse `open_interest` is **futures-only** → option inventory is **PROXY_trade_flow_DDOI** (aggressor × qty by instrument). Never treat futures OI as option DDOI. Decision: **Hold**.
"""
        ),
        code(BOOT),
        code(
            r'''
summary = load_json(OUT / "ddoi_positions" / "summary.json")
rows = (summary or {}).get("rows") or []
df = pd.DataFrame(rows)
print(json.dumps({k: (summary or {}).get(k) for k in ("n_ok","days_ok","mean_abs_ddoi","label","decision")}, indent=2, default=str))
display(df[["day","ok","n_trades","n_instruments","ddoi_sum","ddoi_abs_sum","ddoi_n_nonzero","label"]].round(4) if len(df) and "n_trades" in df.columns else df)
'''
        ),
        md("## Coverage — trades / instruments / |DDOI|"),
        code(
            r'''
ok = df[df["ok"] == True] if len(df) and "ok" in df.columns else df
fig, axes = plt.subplots(1, 3, figsize=(12.5, 3.6))
if len(ok):
    axes[0].bar(ok["day"], ok["n_trades"], color="#3d5a80")
    axes[0].tick_params(axis="x", rotation=70); axes[0].set_title("Option trades / day")
    axes[1].bar(ok["day"], ok["n_instruments"], color="#98c1d9")
    axes[1].tick_params(axis="x", rotation=70); axes[1].set_title("Instruments with flow")
    axes[2].bar(ok["day"], ok["ddoi_abs_sum"], color="#ee6c4d")
    axes[2].tick_params(axis="x", rotation=70); axes[2].set_title("|DDOI| sum (PROXY)")
else:
    for ax in axes:
        ax.text(0.5, 0.5, "run exp_ddoi_panel.py", ha="center", transform=ax.transAxes)
plt.tight_layout(); plt.show()
print("LABEL", DDOI_LABEL, "| futures OI QUARANTINED")
'''
        ),
        md("## Top instruments (latest ok day)"),
        code(
            r'''
if len(ok):
    last = ok.iloc[-1]
    day = last["day"]
    day_rec = load_json(OUT / "ddoi_positions" / f"day_{day}.json") or {}
    top = pd.DataFrame(day_rec.get("top_instruments") or [], columns=["instrument_id","ddoi"])
    display(top.head(15))
    print("honesty:", day_rec.get("honesty"))
else:
    print("no ok days")
'''
        ),
        md("## Signal board"),
        code(
            r'''
print_board([
    ("info.ddoi_coverage", "Hold", f"{DDOI_LABEL}; futures OI unused; n_ok={(summary or {}).get('n_ok')}"),
    ("risk.gex_exposure", "Hold", "Downstream GEX uses this PROXY — not paper DDOI"),
    ("data.trade_synth", "Kill", "never SoT"),
    ("alpha.tob_cross_arb", "Kill", "never Promote"),
])
'''
        ),
    ]


def gex_nb() -> list[dict]:
    return [
        md(
            """# GEX implied book — gamma exposure vs RV/range

**Paper:** Gamma → $/pt implied LOB (PDF pp. 4–5) · **NOTES:** [`NOTES.md`](NOTES.md) · **EXP:** [`EXP_REPORT.md`](EXP_REPORT.md)  
**Artifacts:** `out/gex_implied_book/` · Label: `BS_GEX_trade_flow_DDOI`

$$\\mathrm{GEX} = \\sum_i \\mathrm{DDOI}_i \\cdot \\gamma_i \\cdot \\$\\mathrm{mult}$$

DDOI = **PROXY_trade_flow_DDOI**. IV = Deribit warehouse options. Underlying S = Deribit ETH-PERPETUAL mark. HL TOB for RV/range join — **Kill** as α.
"""
        ),
        code(BOOT),
        code(
            r'''
summary = load_json(OUT / "gex_implied_book" / "summary.json")
panel = load_json(OUT / "gex_implied_book" / "panel_rows.json") or (summary or {}).get("rows") or []
tbl = gex_day_table(panel, CERT)
print(json.dumps({k: (summary or {}).get(k) for k in (
    "n_ok","days_ok","gex_mean","vex_mean","gex_plus_mean",
    "corr_gex_hl_rv","corr_gex_hl_range","corr_gexplus_hl_range",
    "ddoi_modes","decision","promote","kill_tob_cross_alpha","title",
)}, indent=2, default=str))
display(tbl.round(5) if len(tbl) else tbl)
'''
        ),
        md("## Existing figs"),
        code(r'''show_pngs(OUT / "gex_implied_book" / "figs")'''),
        md("## GEX vs HL RV / range + stress split"),
        code(
            r'''
ok = tbl[tbl["ok"] == True].copy() if len(tbl) else tbl
fig, axes = plt.subplots(1, 3, figsize=(12.8, 4.0))
if len(ok):
    axes[0].bar(ok["day"], ok["gex"], color="#3d5a80")
    axes[0].axhline(0, color="k", lw=0.8)
    axes[0].tick_params(axis="x", rotation=70)
    axes[0].set_title("Day GEX")
    axes[1].scatter(ok["gex"], ok["hl_rv"], s=50, c="#ee6c4d")
    for _, r in ok.iterrows():
        axes[1].annotate(str(r["day"])[5:], (r["gex"], r["hl_rv"]), fontsize=7, alpha=0.8)
    axes[1].set_xlabel("GEX"); axes[1].set_ylabel("HL RV")
    axes[1].set_title(f"corr={safe_corr(ok['gex'], ok['hl_rv'])}")
    med = float(ok["hl_range"].median()) if len(ok) else np.nan
    ok["stress"] = np.where(ok["hl_range"] >= med, "stress", "calm")
    for lab, c in (("calm", "#98c1d9"), ("stress", "#ee6c4d")):
        g = ok[ok["stress"] == lab]
        axes[2].scatter(g["gex"], g["hl_range"], s=55, c=c, label=f"{lab} n={len(g)}")
    axes[2].set_xlabel("GEX"); axes[2].set_ylabel("HL range")
    axes[2].set_title(f"stress split (med range={med:.4f})")
    axes[2].legend(fontsize=8)
else:
    for ax in axes:
        ax.text(0.5, 0.5, "run exp_gex_panel.py", ha="center", transform=ax.transAxes)
plt.tight_layout(); plt.show()
if len(ok):
    print("corr GEX~RV", safe_corr(ok["gex"], ok["hl_rv"]), "GEX~range", safe_corr(ok["gex"], ok["hl_range"]))
    print(ok.groupby("stress")[["gex","hl_rv","hl_range"]].mean().round(6))
'''
        ),
        md("## Venue / DDOI honesty"),
        code(
            r'''
fig, axes = plt.subplots(1, 2, figsize=(12.0, 3.8))
if len(ok):
    x = np.arange(len(ok)); w = 0.35
    axes[0].bar(x - w/2, ok["opt_iv_n"].fillna(0), w, label="opt IV n", color="#3d5a80")
    axes[0].bar(x + w/2, ok["opt_trade_n"].fillna(0), w, label="opt trades", color="#ee6c4d")
    axes[0].set_xticks(x); axes[0].set_xticklabels(ok["day"], rotation=70, fontsize=8)
    axes[0].set_title("Options coverage"); axes[0].legend(fontsize=8)
    axes[1].bar(ok["day"], ok["hl_tob_n"].fillna(0), color="#98c1d9")
    axes[1].tick_params(axis="x", rotation=70)
    axes[1].set_title("HL TOB n (real quotes)")
else:
    for ax in axes:
        ax.text(0.5, 0.5, "no panel", ha="center", transform=ax.transAxes)
plt.tight_layout(); plt.show()
if len(ok):
    print(ok[["day","ddoi_mode","kraken","opt_iv_n","opt_trade_n","hl_tob_n"]].to_string(index=False))
print("Warehouse OI = futures-only → unused. trade_synth QUARANTINED.")
'''
        ),
        md("## Lib smoke (synthetic)"),
        code(
            r'''
# toy chain — formulas compute without warehouse
flags = np.array(["c","p","c","p"])
S, K = 2500.0, np.array([2400., 2400., 2600., 2600.])
T = np.full(4, 7/365); iv = np.full(4, 0.55)
ddoi = squeeze.ddoi_from_trade_flow(np.array([10., -8., 5., -12.]), np.array([1, -1, 1, -1]))
pack = squeeze.chain_exposures(
    flags=flags, strikes=K, ttm_years=T, iv=iv, ddoi=ddoi, spot=S, r=0.0,
)
print("toy GEX/VEX/GEX+", pack["gex"], pack["vex"], pack["gex_plus"], "label", squeeze.LABEL_TRADE_DDOI)
'''
        ),
        md("## Signal board"),
        code(
            r'''
print_board([
    ("risk.gex_exposure", "Hold", f"n_ok={(summary or {}).get('n_ok')}; {GEX_PROXY_LABEL}"),
    ("liq.gex_rv_link", "Hold", f"corr_rv={(summary or {}).get('corr_gex_hl_rv')} corr_range={(summary or {}).get('corr_gex_hl_range')}"),
    ("alpha.tob_cross_arb", "Kill", "co-move ≠ arb"),
    ("data.trade_synth", "Kill", "quarantined"),
])
'''
        ),
    ]


def vex_nb() -> list[dict]:
    return [
        md(
            """# VEX / vanna — VEX vs IV / range

**Paper:** Vanna / VEX (PDF pp. 6–8) · **NOTES:** [`NOTES.md`](NOTES.md) · **EXP:** [`EXP_REPORT.md`](EXP_REPORT.md)  
**Artifacts:** `out/vex_vanna/`

VEX uses the same PROXY DDOI × BS vanna. Join to HL range/RV for stress context. IV placebo belongs in `robustness`. **Hold**.
"""
        ),
        code(BOOT),
        code(
            r'''
summary = load_json(OUT / "vex_vanna" / "summary.json")
rows = (summary or {}).get("rows") or []
tbl = gex_day_table(rows, CERT)
print(json.dumps({k: (summary or {}).get(k) for k in ("n_ok","days_ok","vex_mean","corr_vex_hl_range","decision")}, indent=2, default=str))
display(tbl.round(5) if len(tbl) else tbl)
'''
        ),
        md("## VEX / GEX+ vs range"),
        code(
            r'''
ok = tbl[tbl["ok"] == True].copy() if len(tbl) else tbl
fig, axes = plt.subplots(1, 3, figsize=(12.8, 4.0))
if len(ok):
    axes[0].bar(ok["day"], ok["vex"], color="#3d5a80")
    axes[0].axhline(0, color="k", lw=0.8)
    axes[0].tick_params(axis="x", rotation=70); axes[0].set_title("Day VEX")
    axes[1].scatter(ok["vex"], ok["hl_range"], s=50, c="#ee6c4d")
    axes[1].set_xlabel("VEX"); axes[1].set_ylabel("HL range")
    axes[1].set_title(f"corr={safe_corr(ok['vex'], ok['hl_range'])}")
    axes[2].scatter(ok["gex"], ok["vex"], s=50, c=ok["hl_range"], cmap="magma")
    axes[2].set_xlabel("GEX"); axes[2].set_ylabel("VEX"); axes[2].set_title("GEX vs VEX (color=range)")
else:
    for ax in axes:
        ax.text(0.5, 0.5, "run exp_vex_panel.py", ha="center", transform=ax.transAxes)
plt.tight_layout(); plt.show()
if len(ok):
    print("corr VEX~range", safe_corr(ok["vex"], ok["hl_range"]), "GEX+~range", safe_corr(ok["gex_plus"], ok["hl_range"]))
'''
        ),
        md("## Signal board"),
        code(
            r'''
print_board([
    ("risk.vex_exposure", "Hold", f"n_ok={(summary or {}).get('n_ok')}; corr_range={(summary or {}).get('corr_vex_hl_range')}"),
    ("risk.squeeze_intensity", "Hold", "GEX+ downstream"),
    ("alpha.tob_cross_arb", "Kill", "never Promote"),
])
'''
        ),
    ]


def squeeze_nb() -> list[dict]:
    return [
        md(
            """# Squeeze regimes — GEX+ scarcity / stress–calm

**Paper:** GEX+ · abundance/scarce · squeeze/stress (PDF pp. 9–12) · **NOTES:** [`NOTES.md`](NOTES.md) · **EXP:** [`EXP_REPORT.md`](EXP_REPORT.md)  
**Artifacts:** `out/squeeze_regimes/`

Regime split: stress = above-median `|squeeze_intensity|` vs calm. Scarcity from GEX+ sign/threshold. **Hold** — not a Promote path.
"""
        ),
        code(BOOT),
        code(
            r'''
summary = load_json(OUT / "squeeze_regimes" / "summary.json")
panel = load_json(OUT / "squeeze_regimes" / "panel_rows.json") or (summary or {}).get("rows") or []
tbl = gex_day_table(panel, CERT)
print(json.dumps({k: (summary or {}).get(k) for k in (
    "n_ok","days_ok","n_scarce","gex_plus_mean","regime_split_gexplus_vs_range","decision","promote",
)}, indent=2, default=str))
display(tbl.round(5) if len(tbl) else tbl)
'''
        ),
        md("## Scarcity map + stress/calm corr"),
        code(
            r'''
ok = tbl[tbl["ok"] == True].copy() if len(tbl) else tbl
fig, axes = plt.subplots(1, 3, figsize=(12.8, 4.0))
if len(ok):
    colors = ["#ee6c4d" if bool(s) else "#98c1d9" for s in ok["scarce"]]
    axes[0].bar(ok["day"], ok["gex_plus"], color=colors)
    axes[0].axhline(0, color="k", lw=0.8)
    axes[0].tick_params(axis="x", rotation=70)
    axes[0].set_title("GEX+ (red=scarce)")
    axes[1].scatter(ok["squeeze_intensity"], ok["hl_range"], s=55, c=ok["gex_plus"], cmap="coolwarm")
    axes[1].set_xlabel("squeeze intensity"); axes[1].set_ylabel("HL range")
    axes[1].set_title("Intensity vs range")
    med = float(ok["squeeze_intensity"].median()) if len(ok) else np.nan
    ok["regime"] = np.where(ok["squeeze_intensity"] >= med, "stress", "calm")
    for lab, c in (("calm", "#98c1d9"), ("stress", "#ee6c4d")):
        g = ok[ok["regime"] == lab]
        axes[2].scatter(g["gex_plus"], g["hl_range"], s=55, c=c, label=f"{lab} n={len(g)}")
    axes[2].set_xlabel("GEX+"); axes[2].set_ylabel("HL range"); axes[2].legend(fontsize=8)
    axes[2].set_title("Stress/calm (intensity median split)")
else:
    for ax in axes:
        ax.text(0.5, 0.5, "run exp_squeeze_regimes.py", ha="center", transform=ax.transAxes)
plt.tight_layout(); plt.show()
print("regime_split artifact:", (summary or {}).get("regime_split_gexplus_vs_range"))
if len(ok):
    print(ok.groupby("regime")[["gex_plus","hl_range","hl_rv"]].mean().round(6))
'''
        ),
        md("## Signal board"),
        code(
            r'''
print_board([
    ("risk.squeeze_intensity", "Hold", f"n_ok={(summary or {}).get('n_ok')} n_scarce={(summary or {}).get('n_scarce')}"),
    ("liq.implied_book_scarcity", "Hold", "scarce flags from GEX+"),
    ("alpha.tob_cross_arb", "Kill", "never Promote"),
])
'''
        ),
    ]


def robust_nb() -> list[dict]:
    return [
        md(
            """# Robustness / falsifiers — Hold checklist

**NOTES:** [`NOTES.md`](NOTES.md) · **EXP:** [`EXP_REPORT.md`](EXP_REPORT.md)

Desk falsifiers without SPX GIV: chronological split, IV placebo (shuffle IV within day if hourly arrives), venue-drop (2-venue vs spot_l2), no-synth. **Never** soft-Promote TOB-cross α. Warehouse OI futures-only remains quarantined.
"""
        ),
        code(BOOT),
        code(
            r'''
gex = load_json(OUT / "gex_implied_book" / "summary.json")
sq = load_json(OUT / "squeeze_regimes" / "summary.json")
comp = load_json(OUT / "panel_completeness" / "completeness.json")
pass2 = load_json(OUT / "pass2" / "pass2_falsifiers.json")
panel = load_json(OUT / "gex_implied_book" / "panel_rows.json") or (gex or {}).get("rows") or []
tbl = gex_day_table(panel, CERT)
ok = tbl[tbl["ok"] == True].copy() if len(tbl) else tbl
print("n_ok", len(ok), "spot_l2 days in panel", int((ok["kraken"]=="spot_l2").sum()) if len(ok) else 0)
print("blockers", (load_json(OUT / "panel_completeness" / "certified_panels.json") or {}).get("blockers"))
fals = (pass2 or {}).get("falsifiers") or {}
dec = (pass2 or {}).get("decisions") or {}
if pass2:
    print("pass2b decision", dec.get("decision"), "promote", dec.get("promote"), "count", dec.get("promote_count"))
    chrono = fals.get("chrono_split") or {}
    print("chrono GEX↔RV stable", chrono.get("any_gex_rv_stable"), "GEX↔range", chrono.get("any_gex_range_stable"))
    boot = ((fals.get("day_block_bootstrap") or {}).get("gex__hl_rv") or {}).get("day_block") or {}
    print("day-block corr(GEX,HL RV)", boot.get("corr"), "CI", [boot.get("ci_lo"), boot.get("ci_hi")])
    print("kill", dec.get("kill"))
    show_pngs(OUT / "pass2" / "figs")
else:
    print("pass2 missing — run scripts/exp_pass2_falsifiers.py")
btc = load_json(OUT / "panel_completeness" / "btc_widen_appendix.json") or {}
print("BTC widen n_pass", btc.get("n_pass"), "pass_days", btc.get("pass_days"), "blocker", btc.get("blocker"))
'''
        ),
        md("## Chronological split + venue honesty"),
        code(
            r'''
chrono = ((pass2 or {}).get("falsifiers") or {}).get("chrono_split") or {}
if chrono.get("ok"):
    print("early", chrono.get("early_days"))
    print("late", chrono.get("late_days"))
    print(json.dumps(chrono.get("sign_stable"), indent=2))
elif len(ok) >= 4:
    days = list(ok["day"])
    mid = len(days) // 2
    early, late = days[:mid], days[mid:]
    for label, subset in (("early", early), ("late", late)):
        g = ok[ok["day"].isin(subset)]
        print(label, subset,
              "corr(GEX,RV)", safe_corr(g["gex"], g["hl_rv"]),
              "corr(GEX,range)", safe_corr(g["gex"], g["hl_range"]),
              "n", len(g))
else:
    print("need ≥4 ok days for chrono split")

venue = ((pass2 or {}).get("falsifiers") or {}).get("venue_drop") or {}
if venue:
    print("venue-drop HL corr", (venue.get("hl_only") or {}).get("corr_gex_rv"))
    print("venue-drop DB corr", (venue.get("db_only") or {}).get("corr_gex_rv"))
    print("HL↔DB sign concordant", venue.get("sign_concordant_hl_db"))
if len(ok):
    for mode, g in ok.groupby("kraken"):
        print("spot appendix", mode, "n", len(g),
              "corr(GEX,range)", safe_corr(g["gex"], g["hl_range"]))

placebo = ((pass2 or {}).get("falsifiers") or {}).get("placebo_shuffle_gex") or {}
print("placebo exceeds_p95_rv", placebo.get("exceeds_p95_rv"), "obs", placebo.get("obs_corr_gex_rv"))
print("trade_synth QUARANTINED; synth-as-venue n=0; spot_l2 appendix only")
'''
        ),
        md("## Checklist"),
        code(
            r'''
fals = (pass2 or {}).get("falsifiers") or {}
dec = (pass2 or {}).get("decisions") or {}
chrono = fals.get("chrono_split") or {}
checks = [
    ("time-split GEX↔RV", f"stable={chrono.get('any_gex_rv_stable')}", "Hold"),
    ("time-split GEX↔range", f"stable={chrono.get('any_gex_range_stable')}", "Hold"),
    ("day-block bootstrap CI", "CI crosses 0 → Hold", "Hold"),
    ("placebo GEX shuffle", f"exceeds_p95_rv={((fals.get('placebo_shuffle_gex') or {}).get('exceeds_p95_rv'))}", "Hold"),
    ("venue drop HL vs DB", f"concordant={((fals.get('venue_drop') or {}).get('sign_concordant_hl_db'))}", "Hold"),
    ("spot_l2 appendix", "n=4 not primary", "Hold"),
    ("LOO sign flip", f"{((fals.get('leave_one_out') or {}).get('sign_flip_any'))}", "Hold"),
    ("no synth", "trade_synth QUARANTINED", "Kill"),
    ("futures OI as option DDOI", "unused / quarantined", "Kill"),
    ("BTC widen", f"n_pass={btc.get('n_pass')} need≥3", "Hold"),
    ("TOB-cross α", "Kill", "Kill"),
]
print(f"{'check':32s} {'status':40s} gate")
print("-"*90)
for a,b,g in checks:
    print(f"{a:32s} {b:40s} {g}")
print("pass2b promote=", dec.get("promote"), "| 0 Promote ceiling")
'''
        ),
        md("## Signal board"),
        code(
            r'''
print_board([
    ("risk.squeeze_falsifier_board", "Hold", "chrono + placebo + venue; 0 Promote"),
    ("data.trade_synth", "Kill", "quarantined"),
    ("alpha.tob_cross_arb", "Kill", "never Promote"),
])
'''
        ),
    ]


def paper_shadow_nb() -> list[dict]:
    return [
        md(
            """# Paper shadow — living GEX/VEX/squeeze monitor

**Harness:** [`../../applications/paper_shadow/`](../../applications/paper_shadow/) · `live_orders=false`  
Telemetry only until Promote (still **0**). Wires Hold monitors; never flips TOB-cross to α.
"""
        ),
        code(BOOT),
        code(
            r'''
SHADOW = BOOK / "applications" / "paper_shadow" / "out"
meta = load_json(SHADOW / "shadow_meta.json")
board = SHADOW / "SHADOW_BOARD.md"
events = SHADOW / "events.jsonl"
print("shadow_meta", json.dumps(meta, indent=2)[:1200] if meta else None)
if board.exists():
    display(Markdown(board.read_text()[:4000]))
if events.exists():
    print("events.jsonl lines", sum(1 for _ in events.open()))
print("live_orders must remain false; 0 Promote")
'''
        ),
        md("## Signal board"),
        code(
            r'''
print_board([
    ("risk.gex_exposure", "Hold", "shadow telemetry"),
    ("risk.vex_exposure", "Hold", "shadow telemetry"),
    ("risk.squeeze_intensity", "Hold", "shadow telemetry"),
    ("alpha.tob_cross_arb", "Kill", "never Promote"),
])
'''
        ),
    ]


def desk() -> list[dict]:
    return [
        md(
            """# squeeze_metrics — desk synthesis

SqueezeMetrics / GEX Ed. (2020) *The Implied Order Book*.

Lib: `research.lib.squeeze` · Data: Deribit ETH options IV + **PROXY_trade_flow_DDOI** · HL+Deribit TOB · Kraken **spot_l2** when dense · **No ClickHouse MCP**.

**Board:** GEX / VEX / GEX+ / scarcity = **Hold Monitor** · TOB-cross α = **Kill** · `trade_synth` = **Kill** · `live_orders=false` · **0 Promote**.

**Pass-2b:** hardened falsifiers + expanded info dig on certified n=9 — still **0 Promote**.

## Certified panel

- **Primary:** `panel_gex_options` **n=9** — 2026-09-14…18, 25–27, 2026-10-01 ([`out/panel_completeness/`](../out/panel_completeness/))
- **Spot_l2 subpanel:** **n=4** — 2026-09-25, 26, 27, 2026-10-01 (appendix)
- **DDOI:** `PROXY_trade_flow_DDOI` — warehouse OI futures-only unused
- **GEX/VEX:** `BS_GEX_trade_flow_DDOI`
- **BTC widen:** appendix only — see `out/panel_completeness/btc_widen_appendix.json` (n_pass=1 → blocked)

Chapter deep-dives under `chapters/*/`. Info board: [`info_stats_board.ipynb`](info_stats_board.ipynb).

See [`../DESK_MEMO.md`](../DESK_MEMO.md) · [`../CHAPTER_INDEX.md`](../CHAPTER_INDEX.md).
"""
        ),
        code(BOOT),
        code(
            r'''
SHADOW = BOOK / "applications" / "paper_shadow" / "out"
gex = load_json(OUT / "gex_implied_book" / "summary.json")
ddoi = load_json(OUT / "ddoi_positions" / "summary.json")
vex = load_json(OUT / "vex_vanna" / "summary.json")
sq = load_json(OUT / "squeeze_regimes" / "summary.json")
pass2 = load_json(OUT / "pass2" / "pass2_falsifiers.json")
info_feat = load_json(OUT / "info_features" / "info_features.json")
panel = load_json(OUT / "gex_implied_book" / "panel_rows.json") or (gex or {}).get("rows") or []
tbl = gex_day_table(panel, CERT)
print("GEX n_ok", None if not gex else gex.get("n_ok"),
      "corr_rv", None if not gex else gex.get("corr_gex_hl_rv"),
      "corr_range", None if not gex else gex.get("corr_gex_hl_range"))
print("DDOI n_ok", None if not ddoi else ddoi.get("n_ok"), "label", None if not ddoi else ddoi.get("label"))
print("VEX n_ok", None if not vex else vex.get("n_ok"))
print("squeeze n_ok", None if not sq else sq.get("n_ok"), "n_scarce", None if not sq else sq.get("n_scarce"))
print("pass2b", None if not pass2 else (pass2.get("decisions") or {}).get("decision"),
      "promote_count", None if not pass2 else (pass2.get("decisions") or {}).get("promote_count"))
print("info promote_count", None if not info_feat else info_feat.get("promote_count"))
print("promote", False, "kill_tob_cross", True)
'''
        ),
        md("## 1. Signal board (pinned) — Hold · 0 Promote · Kill α"),
        code(
            r'''
print_board()
board = SHADOW / "SHADOW_BOARD.md"
if board.exists():
    display(Markdown(board.read_text()[:3000]))
promote_count = 0
kill_alpha = True
print(f"\\nROLLUP: Promote={promote_count}  Kill_TOB_cross_α={kill_alpha}  Hold_monitors=yes")
'''
        ),
        md("## 2. GEX / VEX / squeeze findings"),
        code(
            r'''
display(tbl.round(4) if len(tbl) else tbl)
show_pngs(OUT / "desk_synthesis" / "figs")
ok = tbl[tbl["ok"] == True] if len(tbl) else tbl
fig, axes = plt.subplots(1, 3, figsize=(12.5, 3.8))
if len(ok):
    axes[0].bar(ok["day"], ok["gex"], color="#3d5a80")
    axes[0].axhline(0, color="k", lw=0.8)
    axes[0].tick_params(axis="x", rotation=70); axes[0].set_title("GEX")
    axes[1].bar(ok["day"], ok["vex"], color="#ee6c4d")
    axes[1].axhline(0, color="k", lw=0.8)
    axes[1].tick_params(axis="x", rotation=70); axes[1].set_title("VEX")
    colors = ["#ee6c4d" if bool(s) else "#98c1d9" for s in ok["scarce"]]
    axes[2].bar(ok["day"], ok["gex_plus"], color=colors)
    axes[2].axhline(0, color="k", lw=0.8)
    axes[2].tick_params(axis="x", rotation=70); axes[2].set_title("GEX+ (red=scarce)")
plt.tight_layout(); plt.show()
'''
        ),
        md("## 3. Pass-2b falsifiers + info dig figs"),
        code(
            r'''
show_pngs(OUT / "pass2" / "figs")
show_pngs(OUT / "info_features" / "figs")
show_pngs(OUT / "feature_stats" / "figs")
if pass2:
    fals = pass2.get("falsifiers") or {}
    boot = ((fals.get("day_block_bootstrap") or {}).get("gex__hl_rv") or {}).get("day_block") or {}
    print("day-block corr(GEX,HL RV)", boot.get("corr"), "CI", [boot.get("ci_lo"), boot.get("ci_hi")])
    print("chrono", (fals.get("chrono_split") or {}).get("sign_stable"))
    print("reasons", (pass2.get("decisions") or {}).get("reasons"))
if info_feat:
    incr = info_feat.get("incremental") or {}
    print("ΔR² GEX after RV", incr.get("delta_r2_gex_after_rv"))
    print("ΔR² VEX after RV+GEX", incr.get("delta_r2_vex_after_rv_gex"))
    print("ΔR² squeeze after GEX", incr.get("delta_r2_squeeze_after_gex"))
    print("use_map", info_feat.get("use_map"))
'''
        ),
        md("## 4. GEX vs RV/range + venue honesty"),
        code(
            r'''
ok = tbl[tbl["ok"] == True].copy() if len(tbl) else tbl
fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.0))
if len(ok):
    axes[0].scatter(ok["gex"], ok["hl_rv"], s=50, c="#3d5a80", label="RV")
    axes[0].scatter(ok["gex"], ok["hl_range"], s=50, c="#ee6c4d", marker="s", label="range")
    axes[0].set_xlabel("GEX"); axes[0].legend(); axes[0].set_title("GEX vs HL RV/range")
    axes[1].bar(ok["day"], ok["opt_iv_n"], color="#98c1d9", label="IV n")
    axes[1].plot(ok["day"], ok["opt_trade_n"], "o-", color="#ee6c4d", label="trades")
    axes[1].tick_params(axis="x", rotation=70); axes[1].legend(fontsize=8)
    axes[1].set_title("Options coverage honesty")
plt.tight_layout(); plt.show()
print("kraken modes", ok["kraken"].value_counts().to_dict() if len(ok) else {})
print("ddoi modes", ok["ddoi_mode"].value_counts().to_dict() if len(ok) else {})
print("corr GEX~RV", safe_corr(ok["gex"], ok["hl_rv"]) if len(ok) else None,
      "GEX~range", safe_corr(ok["gex"], ok["hl_range"]) if len(ok) else None)
btc = load_json(OUT / "panel_completeness" / "btc_widen_appendix.json") or {}
print("BTC widen n_pass", btc.get("n_pass"), "days", btc.get("pass_days"), "blocker", btc.get("blocker"))
'''
        ),
        md(
            """## 5. Honesty

- Scoreboard = **monitor telemetry**, not PnL alpha  
- DDOI = **PROXY_trade_flow_DDOI**; warehouse OI futures-only unused  
- Primary = `panel_gex_options` real IV + real TOB; Kraken spot_l2 **appendix**; `trade_synth` **QUARANTINED**  
- Pass-2b: day-block CI crosses 0 · chrono range unstable · placebo fails p95 · LOO sign flip → **Hold ceiling**  
- **0 Promote** · Hold monitors · **Kill** TOB-cross α
"""
        ),
        code(
            r'''
print_board()
print("\\nChapter notebooks under chapters/*/ — see CHAPTER_INDEX.")
'''
        ),
    ]


def info_stats() -> list[dict]:
    return [
        md(
            """# squeeze_metrics — Pass-2b info / stats board

**Purpose:** lead-lag, markouts, incremental vs RV, ToD / stress regimes, use-map for GEX/VEX/squeeze.  
**Panel:** `panel_gex_options` **n=9**; spot_l2 **n=4** appendix; DDOI=**PROXY_trade_flow_DDOI**.  
**Artifacts:** `out/info_features/` · `out/feature_stats/` · `out/pass2/` · [`../APPLICATIONS.md`](../APPLICATIONS.md)  
**Gate:** **0 Promote** — Hold research tiles / monitors only. Never soft-Promote TOB-cross α.
"""
        ),
        code(BOOT),
        code(
            r'''
gex = load_json(OUT / "gex_implied_book" / "summary.json")
ddoi = load_json(OUT / "ddoi_positions" / "summary.json")
info_feat = load_json(OUT / "info_features" / "info_features.json")
feat_stats = load_json(OUT / "feature_stats" / "feature_stats.json")
cands = load_json(OUT / "info_features" / "candidates.json") or (info_feat or {}).get("candidates") or []
use_map = load_json(OUT / "info_features" / "use_map.json") or (info_feat or {}).get("use_map") or {}
panel = load_json(OUT / "gex_implied_book" / "panel_rows.json") or (gex or {}).get("rows") or []
tbl = gex_day_table(panel, CERT)
ok = tbl[tbl["ok"] == True].copy() if len(tbl) else tbl
print("n_ok", len(ok), "days", list(ok["day"]) if len(ok) else [])
print("info ok", bool(info_feat), "feature_stats ok", bool(feat_stats))
if info_feat:
    incr = info_feat.get("incremental") or {}
    print("promote_count", info_feat.get("promote_count"))
    print("partial(range,GEX|RV)", (incr.get("partial_range_gex_ctrl_rv") or {}).get("partial_r"))
    print("ΔR² GEX|RV", incr.get("delta_r2_gex_after_rv"),
          "VEX|RV+GEX", incr.get("delta_r2_vex_after_rv_gex"),
          "squeeze|GEX", incr.get("delta_r2_squeeze_after_gex"))
    print("day_feature PC1", (info_feat.get("day_feature_pca") or {}).get("pc1_explained"))
    print("scarce", (info_feat.get("regimes") or {}).get("scarce"))
else:
    print("info_features missing — run scripts/exp_info_features.py")
# persist light stats artifact (notebook-local mirror)
stats = {
    "n_ok": int(len(ok)),
    "days": list(ok["day"]) if len(ok) else [],
    "corr": {
        "gex_hl_rv": safe_corr(ok["gex"], ok["hl_rv"]) if len(ok) else None,
        "gex_hl_range": safe_corr(ok["gex"], ok["hl_range"]) if len(ok) else None,
        "vex_hl_rv": safe_corr(ok["vex"], ok["hl_rv"]) if len(ok) else None,
        "vex_hl_range": safe_corr(ok["vex"], ok["hl_range"]) if len(ok) else None,
        "gexplus_hl_range": safe_corr(ok["gex_plus"], ok["hl_range"]) if len(ok) else None,
        "gex_vex": safe_corr(ok["gex"], ok["vex"]) if len(ok) else None,
    },
    "partial_vs_rv": {
        "gexplus_range_given_rv": partial_corr_vs_rv(ok["gex_plus"], ok["hl_range"], ok["hl_rv"]) if len(ok) else None,
        "gex_range_given_rv": partial_corr_vs_rv(ok["gex"], ok["hl_range"], ok["hl_rv"]) if len(ok) else None,
    },
    "lead_lag_gex_rv": lead_lag_day(ok["gex"].to_numpy(), ok["hl_rv"].to_numpy()) if len(ok) >= 3 else {},
    "lead_lag_gex_range": lead_lag_day(ok["gex"].to_numpy(), ok["hl_range"].to_numpy()) if len(ok) >= 3 else {},
    "pass2b_incremental": (info_feat or {}).get("incremental"),
    "use_map": use_map,
    "ddoi_label": DDOI_LABEL,
    "promote": False,
    "decision_ceiling": "Hold",
}
stats_dir = OUT / "info_stats"
stats_dir.mkdir(parents=True, exist_ok=True)
(stats_dir / "info_stats.json").write_text(json.dumps(stats, indent=2, default=str))
print("wrote", stats_dir / "info_stats.json")
'''
        ),
        md("## Pass-2b figs (info + feature_stats)"),
        code(
            r'''
show_pngs(OUT / "info_features" / "figs")
show_pngs(OUT / "feature_stats" / "figs")
show_pngs(OUT / "pass2" / "figs")
'''
        ),
        md("## Correlation matrix (day panel)"),
        code(
            r'''
cols = ["gex","vex","gex_plus","squeeze_intensity","hl_rv","hl_range","opt_trade_n"]
if len(ok):
    c = ok[cols].astype(float).corr()
    display(c.round(3))
    fig, ax = plt.subplots(figsize=(6.8, 5.4))
    im = ax.imshow(c.values, cmap="coolwarm", vmin=-1, vmax=1)
    ax.set_xticks(range(len(cols))); ax.set_xticklabels(cols, rotation=45, ha="right")
    ax.set_yticks(range(len(cols))); ax.set_yticklabels(cols)
    ax.set_title("Day-panel corr (certified GEX options n=9)")
    fig.colorbar(im, ax=ax, fraction=0.046)
    plt.tight_layout(); plt.show()
else:
    print("no ok days — run Pass-1 panels first")
'''
        ),
        md("## Lead-lag + incremental (Pass-2b)"),
        code(
            r'''
ll = (info_feat or {}).get("lead_lag") or {}
incr = (info_feat or {}).get("incremental") or {}
fig, axes = plt.subplots(1, 2, figsize=(11.5, 3.8))
for ax, key, title in (
    (axes[0], "gex->hl_rv", "GEX → HL RV"),
    (axes[1], "gex->hl_range", "GEX → HL range"),
):
    rec = ll.get(key) or {}
    lags, corrs = rec.get("lags") or [], rec.get("corr") or []
    if lags:
        ax.bar(lags, [c if c is not None else np.nan for c in corrs], color="#3d5a80")
        ax.axhline(0, color="k", lw=0.8)
        ax.set_title(f"{title} best_lag={rec.get('best_lag')}")
    else:
        ax.text(0.5, 0.5, "missing", ha="center", transform=ax.transAxes)
plt.tight_layout(); plt.show()
print("ΔR² GEX after RV", incr.get("delta_r2_gex_after_rv"))
print("ΔR² VEX after RV+GEX", incr.get("delta_r2_vex_after_rv_gex"))
print("ΔR² squeeze after GEX", incr.get("delta_r2_squeeze_after_gex"))
print("partial(range,GEX|RV)", (incr.get("partial_range_gex_ctrl_rv") or {}).get("partial_r"))
print("Note: descriptive only — not tradable IRF α")
'''
        ),
        md("## Stress / calm + use map"),
        code(
            r'''
stress = (info_feat or {}).get("stress_calm") or {}
for k, rec in stress.items():
    if isinstance(rec, dict):
        print(k, "n", rec.get("n"), "mean_HL_RV", rec.get("mean_hl_rv"),
              "corr_gex_rv", (rec.get("corr_gex_hl_rv") or {}).get("pearson"))
print("use_map", json.dumps(use_map, indent=2))
if isinstance(cands, list) and cands:
    cdf = pd.DataFrame(cands)
    display(cdf[["id","decision","wire_as","use"]] if set(cdf.columns)>= {"id","decision","wire_as","use"} else cdf)
'''
        ),
        md("## DDOI coverage join"),
        code(
            r'''
ddoi_rows = (ddoi or {}).get("rows") or []
ddf = pd.DataFrame(ddoi_rows)
if len(ddf) and len(ok):
    m = ok.merge(ddf[["day","n_trades","ddoi_abs_sum","ddoi_n_nonzero"]], on="day", how="left")
    display(m[["day","gex","hl_range","n_trades","ddoi_abs_sum","ddoi_mode","kraken"]].round(4))
    print("corr(|DDOI|, |GEX|)", safe_corr(m["ddoi_abs_sum"].abs(), m["gex"].abs()))
else:
    print("ddoi summary missing — run exp_ddoi_panel.py")
'''
        ),
        md("## Signal board (info.*)"),
        code(
            r'''
print_board([r for r in SIGNAL_BOARD if r[0].startswith("info.") or r[0] in (
    "risk.gex_exposure","risk.squeeze_falsifier_board","liq.gex_rv_link","alpha.tob_cross_arb","data.trade_synth"
)])
print("\\nArtifact written:", OUT / "info_stats" / "info_stats.json")
print("0 Promote · Hold tiles only · Kill TOB-cross α / trade_synth")
'''
        ),
    ]


def main() -> None:
    write_nb(CH / "ch00_overview" / "ch00_overview.ipynb", ch00(), "ch00")
    write_nb(CH / "ddoi_positions" / "ddoi_positions.ipynb", ddoi_nb(), "ddoi")
    write_nb(CH / "gex_implied_book" / "gex_implied_book.ipynb", gex_nb(), "gex")
    write_nb(CH / "vex_vanna" / "vex_vanna.ipynb", vex_nb(), "vex")
    write_nb(CH / "squeeze_regimes" / "squeeze_regimes.ipynb", squeeze_nb(), "squeeze")
    write_nb(CH / "robustness" / "robustness.ipynb", robust_nb(), "robust")
    write_nb(CH / "paper_shadow" / "paper_shadow.ipynb", paper_shadow_nb(), "shadow")
    write_nb(NB / "desk_synthesis.ipynb", desk(), "desk")
    write_nb(NB / "info_stats_board.ipynb", info_stats(), "info_stats_board")


if __name__ == "__main__":
    main()
