#!/usr/bin/env python3
"""Generate / overwrite cd_me chapter notebooks + richer desk_synthesis.

Run from repo root or this scripts/ dir. Does not touch Pass-2 experiment scripts.
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
    lines = s.splitlines(keepends=True)
    return lines


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
            "cd_me_title": title,
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
import matplotlib.pyplot as plt
from IPython.display import Image, display, Markdown

BOOK = Path(os.environ.get("ARES_MICROSTRUCTURE") or (Path.home() / "srv" / "ares-microstructure")) / "research" / "books" / "cd_me"
OUT = BOOK / "out"
SCRIPTS = BOOK / "scripts"
ROOT = BOOK.parents[2]  # ares-microstructure repo root (research.lib absolute imports)
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT))
from _nb_common import (
    load_json, expand_pim_hourly, expand_dcm_hourly, day_summary_table, SIGNAL_BOARD,
    load_kraken_inventory, kraken_mode_for_day,
)
from certified_panel import load_certified, primary_days, spot_l2_days
from research.lib import cdme  # noqa: E402

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

PASS2 = OUT / "pass2"
KR_INV = load_kraken_inventory(BOOK)
CERT = load_certified()
PRIMARY = primary_days(CERT)
SPOT = spot_l2_days(CERT)
print("BOOK", BOOK)
print("certified primary n=", len(PRIMARY), PRIMARY)
print("spot_l2 subpanel n=", len(SPOT), SPOT)
print("pass2 present", PASS2.is_dir(), "falsifiers", (PASS2 / "pass2_falsifiers.json").is_file())
print("trade_synth QUARANTINED — never primary")
'''.strip()


def ch00() -> list[dict]:
    return [
        md(
            """# Ch.00 — Overview: Constrained dealers & PIM taxonomy

**Paper:** Huang–Ranaldo–Schrimpf–Somogyi (Nov 2021, SSRN 3960577) — *Constrained Dealers and Market Efficiency*  
**NOTES:** [`NOTES.md`](NOTES.md) (§1, PDF pp. 2–7) · **SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md)

Core claim: when dealers’ risk-bearing capacity is tight, **liquidity elasticity weakens** and **PIM** (price inefficiency) rises. Desk maps CLS FX triplets → cross-venue ETH LOP on **HL + Deribit** real quotes (+ Kraken **spot_l2** when dense; `trade_synth` **QUARANTINED**) and DCM → public PC1 proxies — **never** soft-Promote TOB-cross as arb α.
"""
        ),
        code(BOOT),
        md(
            r"""## Crypto map vs paper objects

| Paper | Desk |
|-------|------|
| Triangular LOP / VLOOP | `|log(mid_i/mid_j)|` on latency-aligned TOB (HL↔DB; +KR spot_l2) |
| TCOST | Sum of relative half-spreads on arb legs |
| PIM = VLOOP + |TCOST| when VLOOP>0 | `cdme.pim_from_components` |
| DCM (VaR/CDS/…) | PC1 of |funding|, |basis|, RV, imbalance — **Kill** bank vanity |
| Elasticity corr(VLM, PIM) | Hourly notional × PIM, DCM quantile split |
| Kraken leg | Dense **spot_l2** only; else **2-venue**; `trade_synth` QUARANTINED |
"""
        ),
        code(
            r'''
pim = load_json(OUT / "pim_vloop_tcost" / "summary.json")
dcm = load_json(OUT / "dcm_proxies" / "summary.json")
el = load_json(OUT / "elasticity_regimes" / "summary.json")
kr = load_json(OUT / "kraken_probe.json")
p2 = load_json(PASS2 / "pass2_falsifiers.json")
print("PIM days", None if not pim else pim.get("days"), "n_ok", None if not pim else pim.get("n_ok"),
      "venues", None if not pim else pim.get("venues"))
print("DCM n_ok", None if not dcm else dcm.get("n_ok"))
if el:
    pooled = (el.get("pooled") or {}).get("all") or {}
    print("elasticity pooled", {k: pooled.get(k) for k in ("n", "corr", "ci_lo", "ci_hi")})
print("Kraken probe keys", None if not kr else list(kr.keys()))
if p2:
    pp = p2.get("pim_panel") or {}
    print("certified primary", PRIMARY, "spot_l2", SPOT)
    print("pass2 n_ok", pp.get("n_days_ok"),
          "promote_count", (p2.get("decisions") or {}).get("promote_count"))
'''
        ),
        md("## Pass-2 scoreboard snapshot"),
        code(
            r'''
pim_panel = load_json(OUT / "pim_vloop_tcost" / "panel_rows.json") or []
tbl = day_summary_table(pim_panel, inventory=KR_INV)
display(tbl.round(4))

fig, axes = plt.subplots(1, 3, figsize=(12.5, 3.6))
ax = axes[0]
ok = tbl[tbl["ok"] == True]
colors = ["#3d5a80" if str(m) == "spot_l2" else "#98c1d9" for m in ok["kraken"]]
ax.bar(ok["day"], ok["pim_mean"], color=colors)
ax.tick_params(axis="x", rotation=70)
ax.set_title("Day-mean PIM (certified; navy=spot_l2)")
ax.set_ylabel("PIM")

ax = axes[1]
dcm_rows = (dcm or {}).get("day_summaries") or []
days, expl = [], []
for r in dcm_rows:
    d = r.get("dcm") or {}
    if d.get("explained_var") is not None and (d.get("n_valid") or 0) > 0:
        days.append(r["day"]); expl.append(d["explained_var"])
ax.bar(days, expl, color="#98c1d9")
ax.tick_params(axis="x", rotation=70)
ax.set_ylim(0, 1.05)
ax.set_title("DCM̂ PC1 explained var")

ax = axes[2]
pooled = ((el or {}).get("pooled") or {})
allc = pooled.get("all") or {}
reg = pooled.get("regime_point") or {}
labels = ["all", "DCM low", "DCM high"]
vals = [allc.get("corr"), reg.get("corr_low"), reg.get("corr_high")]
ax.bar(labels, [v if v is not None else np.nan for v in vals], color=["#293241", "#ee6c4d", "#e0fbfc"])
ax.axhline(0, color="k", lw=0.8)
ax.set_title("Elasticity corr(VLM,PIM)")
ax.set_ylabel("corr")
plt.tight_layout()
plt.show()
print("kraken modes:", tbl["kraken"].value_counts().to_dict())
'''
        ),
        md(
            """## Reading order

1. `pim_vloop_tcost` — construct VLOOP/TCOST/PIM (certified 2-venue / spot_l2)  
2. `dcm_proxies` — public DCM̂  
3. `elasticity_regimes` — regime corr  
4. `lstar_panel` / `model_sim` — **park**  
5. `robustness` — Pass-2 falsifiers (`out/pass2/`)  
6. `paper_shadow` — living monitor (`live_orders=false`)

Chapter notebooks live beside NOTES under `chapters/<pkg>/`. Desk rollup: [`../../notebooks/desk_synthesis.ipynb`](../../notebooks/desk_synthesis.ipynb).
"""
        ),
        md("## Signal board"),
        code(
            r'''
print_board()
if PASS2.is_dir():
    p2 = load_json(PASS2 / "pass2_falsifiers.json") or {}
    print("\nPass-2 decisions:", json.dumps(p2.get("decisions"), indent=2))
else:
    print("\nFalsifier status: out/pass2/ missing — run scripts/exp_pass2_falsifiers.py")
'''
        ),
    ]


def pim_nb() -> list[dict]:
    return [
        md(
            """# PIM / VLOOP / TCOST — cross-venue LOP gap

**Paper:** §2 Eqs 1–3 (PDF pp. 8–12) · **NOTES:** [`NOTES.md`](NOTES.md) · **EXP:** [`EXP_REPORT.md`](EXP_REPORT.md)  
**Artifacts:** `out/pim_vloop_tcost/` · **Lib:** `research.lib.cdme`

$$\\mathrm{PIM}_t = \\mathbb{E}_t[\\mathrm{VLOOP}_t + |\\mathrm{TCOST}_t| \\mid \\mathrm{VLOOP}_t > 0]$$

Desk: **HL + Deribit** real quotes on ETH (certified `panel_core_2venue` **n=9**). Kraken = dense **spot_l2** only (n=4 subpanel); `trade_synth` **QUARANTINED**. Detection ≠ executable arb → **Kill** `alpha.tob_cross_arb`.
"""
        ),
        code(BOOT),
        code(
            r'''
summary = load_json(OUT / "pim_vloop_tcost" / "summary.json")
panel = load_json(OUT / "pim_vloop_tcost" / "panel_rows.json") or []
hourly = expand_pim_hourly(panel)
tbl = day_summary_table(panel, inventory=KR_INV)
print(json.dumps({k: summary.get(k) for k in ("ok","symbol","days","n_ok","venues","dt_s","bucket_s","honesty")} if summary else {}, indent=2))
display(tbl.round(5))
print("hourly rows", len(hourly), "finite PIM", int(np.isfinite(hourly["pim"]).sum()))
print("kraken modes:", tbl["kraken"].value_counts().to_dict())
'''
        ),
        md("## Existing Pass-2 figures"),
        code(r'''show_pngs(OUT / "pim_vloop_tcost" / "figs")'''),
        md(
            """## Expansion — time-of-day + day panel

Hourly PIM means by UTC hour (pooled) and a day×hour heatmap. Sparse TOB → many NaNs; interpret as research-grade coverage, not HFT. Primary plots use certified real-quote days only (`has_synth=false`).
"""
        ),
        code(
            r'''
h = hourly.copy()
tod = h.groupby("hour_utc")["pim"].agg(["mean", "count"]).reset_index()
fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.0))
ax = axes[0]
ax.bar(tod["hour_utc"], tod["mean"], color="#3d5a80")
ax.set_xlabel("UTC hour"); ax.set_ylabel("mean PIM"); ax.set_title("ToD pattern — pooled hourly PIM (certified)")
# heatmap
pivot = h.pivot_table(index="day", columns="hour_utc", values="pim", aggfunc="mean")
ax = axes[1]
im = ax.imshow(pivot.values, aspect="auto", cmap="magma", interpolation="nearest")
ax.set_yticks(range(len(pivot.index))); ax.set_yticklabels(list(pivot.index), fontsize=8)
ax.set_xticks(range(0, 24, 2)); ax.set_xticklabels(list(range(0, 24, 2)))
ax.set_title("Day × UTC-hour PIM heatmap")
ax.set_xlabel("UTC hour")
fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
plt.tight_layout(); plt.show()
print(tod.round(5).to_string(index=False))
'''
        ),
        md("## Expansion — VLOOP vs TCOST scatter + stress split"),
        code(
            r'''
ok = h[np.isfinite(h["vloop"]) & np.isfinite(h["tcost"])].copy()
# stress = days with above-median day-mean PIM
day_means = ok.groupby("day")["pim"].mean()
med = float(day_means.median()) if len(day_means) else np.nan
ok["stress"] = ok["day"].map(lambda d: "stress" if day_means.get(d, 0) >= med else "calm")

fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.2))
ax = axes[0]
for name, g in ok.groupby("day"):
    ax.scatter(g["vloop"], g["tcost"], s=18, alpha=0.55, label=name)
ax.set_xlabel("VLOOP"); ax.set_ylabel("TCOST"); ax.set_title("Hourly VLOOP vs TCOST by day")
ax.legend(fontsize=7, ncol=2, framealpha=0.8)

ax = axes[1]
for lab, color in (("calm", "#98c1d9"), ("stress", "#ee6c4d")):
    g = ok[ok["stress"] == lab]
    ax.scatter(g["vloop"], g["tcost"], s=28, alpha=0.7, c=color, label=f"{lab} (n={len(g)})")
ax.set_xlabel("VLOOP"); ax.set_ylabel("TCOST"); ax.set_title(f"Stress split (day-mean PIM median={med:.4f})")
ax.legend()
plt.tight_layout(); plt.show()

corr_all = ok["vloop"].corr(ok["tcost"])
print(f"pooled corr(VLOOP,TCOST)={corr_all:.3f} n={len(ok)}")
print(ok.groupby("stress")[["vloop","tcost","pim"]].mean().round(5))
'''
        ),
        md("## Coverage honesty (HL / Deribit / Kraken spot_l2 vs absent_2venue)"),
        code(
            r'''
fig, ax = plt.subplots(figsize=(10.0, 3.8))
x = np.arange(len(tbl))
w = 0.25
ax.bar(x - w, tbl["cov_hl"].fillna(0), w, label="HL", color="#3d5a80")
ax.bar(x, tbl["cov_db"].fillna(0), w, label="Deribit", color="#ee6c4d")
ax.bar(x + w, tbl["cov_kr"].fillna(0), w, label="Kraken", color="#98c1d9")
ax.set_xticks(x); ax.set_xticklabels(tbl["day"], rotation=70, fontsize=8)
ax.set_ylabel("fraction of 5s grid")
ax.set_title("TOB coverage — certified (KR only when spot_l2)")
ax.legend()
plt.tight_layout(); plt.show()
print(tbl[["day", "venues", "kraken", "cov_kr"]].to_string(index=False))
inv_streams = (KR_INV or {}).get("streams_by_panel_day") or {}
for day, note in inv_streams.items():
    print(f"  {day}: mode={kraken_mode_for_day(day, KR_INV)} | {note}")
if summary:
    ks = summary.get("kraken_status") or []
    print("kraken_status in_tob days", sum(1 for r in ks if r.get("in_tob")), "/", len(ks))
'''
        ),
        md("## Lib smoke (synthetic) — formulas still compute without warehouse"),
        code(
            r'''
# cheap synthetic check of paper objects (not a backtest)
rng = np.random.default_rng(0)
mid_a = 3000 + np.cumsum(rng.normal(0, 0.5, 500))
mid_b = mid_a * np.exp(rng.normal(0, 0.0004, 500))
v = cdme.vloop_pair(mid_a, mid_b)
hs_a = np.full_like(mid_a, 0.0002); hs_b = np.full_like(mid_b, 0.0003)
tc = cdme.tcost_from_spreads({"a": hs_a, "b": hs_b})
pim = cdme.pim_from_components(v, tc)
print("synthetic mean VLOOP/TCOST/PIM", float(np.nanmean(v)), float(np.nanmean(tc)), float(np.nanmean(pim)))
'''
        ),
        md("## Signal board + falsifier status"),
        code(
            r'''
print_board([
    ("risk.pim_cross_venue", "Hold", "n=9 panel_core_2venue; spot_l2 subpanel n=4; synth QUARANTINED"),
    ("info.vloop_tcost_commonality", "Hold", "strong corr on finite hours"),
    ("alpha.tob_cross_arb", "Kill", "detection ≠ sized arb; trade_synth PROXY never Promote"),
])
p2 = load_json(PASS2 / "pass2_falsifiers.json") if PASS2.is_dir() else None
if p2:
    print("pass2 pim_panel:", {k: (p2.get("pim_panel") or {}).get(k)
          for k in ("n_days_ok", "n_days_3_venue_tob", "n_days_kraken_tob", "vloop_tcost_corr_median")})
    print("pass2 decisions:", p2.get("decisions"))
else:
    print("pass2/ not present — run scripts/exp_pass2_falsifiers.py")
'''
        ),
    ]


def dcm_nb() -> list[dict]:
    return [
        md(
            """# DCM proxies — public dealer-constraint measure

**Paper:** §3 DCM construction (PDF pp. 14–16) · **NOTES:** [`NOTES.md`](NOTES.md) · **EXP:** [`EXP_REPORT.md`](EXP_REPORT.md)  
**Artifacts:** `out/dcm_proxies/`

Paper DCM blends VaR / leverage / CDS / funding / FX vol. Desk **Kill**s bank vanity and uses PC1 of public proxies: `|funding|`, `|perp basis|`, RV, `|imbalance|`. Honesty: `funding_proxy` = rolling `|Δlog mid|`, **not** exchange funding rate; basis often degenerate when home≈far marks.
"""
        ),
        code(BOOT),
        code(
            r'''
summary = load_json(OUT / "dcm_proxies" / "summary.json")
panel = load_json(OUT / "dcm_proxies" / "panel_rows.json") or []
hourly = expand_dcm_hourly(panel)
print("n_ok", None if not summary else summary.get("n_ok"), "kill_cds", None if not summary else summary.get("kill_cds_var"))
rows = []
for d in panel:
    meta = d.get("dcm") or {}
    load = meta.get("loadings") or {}
    rows.append({
        "day": d.get("day"), "ok": d.get("ok"), "home": d.get("home_venue"),
        "n_valid": meta.get("n_valid"), "explained": meta.get("explained_var"),
        "G_mean": meta.get("G_mean"),
        **{f"L_{k}": load.get(k) for k in ("abs_funding","abs_basis","rv","abs_imbalance")},
    })
load_df = pd.DataFrame(rows)
display(load_df.round(4))
'''
        ),
        md("## Pass-2 coverage figure"),
        code(r'''show_pngs(OUT / "dcm_proxies" / "figs")'''),
        md("## Expansion — loadings heatmap + explained variance"),
        code(
            r'''
keys = ["L_abs_funding","L_abs_basis","L_rv","L_abs_imbalance"]
mat = load_df.set_index("day")[keys]
fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.2))
ax = axes[0]
im = ax.imshow(mat.values.astype(float), aspect="auto", cmap="coolwarm", vmin=-1, vmax=1)
ax.set_yticks(range(len(mat.index))); ax.set_yticklabels(list(mat.index), fontsize=8)
ax.set_xticks(range(len(keys))); ax.set_xticklabels(["|fund|","|basis|","RV","|imb|"], rotation=0)
ax.set_title("PC1 loadings by day")
fig.colorbar(im, ax=ax, fraction=0.046)

ax = axes[1]
valid = load_df[load_df["n_valid"].fillna(0) > 0]
ax.bar(valid["day"], valid["explained"], color="#3d5a80")
ax.tick_params(axis="x", rotation=70)
ax.set_ylim(0, 1.05); ax.set_title("Explained variance (days with n_valid>0)")
plt.tight_layout(); plt.show()
print("basis loading near-zero days:", int((load_df["L_abs_basis"].abs() < 1e-8).sum()))
'''
        ),
        md("## Expansion — hourly DCM̂ vs PIM (joined days)"),
        code(
            r'''
ok = hourly[np.isfinite(hourly["dcm"]) & np.isfinite(hourly["pim"])].copy()
fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.0))
ax = axes[0]
for day, g in ok.groupby("day"):
    ax.plot(g["hour_utc"], g["dcm"], marker="o", ms=3, lw=1, label=day)
ax.set_xlabel("UTC hour"); ax.set_ylabel("DCM̂ PC1"); ax.set_title("Hourly DCM̂ traces")
ax.legend(fontsize=7, ncol=2)

ax = axes[1]
sc = ax.scatter(ok["dcm"], ok["pim"], c=ok["hour_utc"], cmap="viridis", s=28, alpha=0.75)
ax.set_xlabel("DCM̂"); ax.set_ylabel("PIM"); ax.set_title("DCM̂ vs PIM (hourly join)")
fig.colorbar(sc, ax=ax, label="UTC hour")
plt.tight_layout(); plt.show()
print("corr(DCM,PIM)", float(ok["dcm"].corr(ok["pim"])) if len(ok)>2 else None, "n", len(ok))
'''
        ),
        md("## Signal board"),
        code(
            r'''
print_board([
    ("risk.dcm_pc1", "Hold", "PC1 usable on most days; unstable when only funding+RV load"),
    ("risk.bank_cds_var", "Kill", "no public crypto CDS/VaR analogue"),
])
print("Falsifier: PC stability across days + placebo DCM shuffle → Pass-2")
'''
        ),
    ]


def elast_nb() -> list[dict]:
    return [
        md(
            """# Elasticity regimes — corr(VLM, PIM) by DCM

**Paper:** §3 motivational elasticity (PDF pp. 15–19) · **NOTES:** [`NOTES.md`](NOTES.md) · **EXP:** [`EXP_REPORT.md`](EXP_REPORT.md)  
**Artifacts:** `out/elasticity_regimes/`

Paper: volume–inefficiency co-movement **weakens** when dealers are constrained. Certified-panel crypto join finds **negative** pooled corr(VLM, PIM) **n=88** corr≈**−0.46** CI[−0.57,−0.35] — **not** a soft-Promote of the FX result (clock/unit/TOB sparsity). Decision ceiling remains **Hold**. `trade_synth` quarantined.
"""
        ),
        code(BOOT),
        code(
            r'''
el = load_json(OUT / "elasticity_regimes" / "summary.json")
dcm_panel = load_json(OUT / "dcm_proxies" / "panel_rows.json") or []
hourly = expand_dcm_hourly(dcm_panel)
pooled = (el or {}).get("pooled") or {}
print(json.dumps({
    "n_ok": None if not el else el.get("n_ok"),
    "pooled_all": pooled.get("all"),
    "regime_point": pooled.get("regime_point"),
    "decision_ceiling": pooled.get("decision_ceiling"),
    "honesty": None if not el else el.get("honesty"),
}, indent=2, default=str))
day_el = pd.DataFrame((el or {}).get("day_elasticity") or [])
if len(day_el):
    display(day_el)
'''
        ),
        md("## Pass-2 figures"),
        code(r'''show_pngs(OUT / "elasticity_regimes" / "figs")'''),
        md("## Expansion — scatter VLM vs PIM with DCM color + regime strips"),
        code(
            r'''
ok = hourly[np.isfinite(hourly["pim"]) & np.isfinite(hourly["notional"])].copy()
fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.2))
ax = axes[0]
c = ok["dcm"] if "dcm" in ok else np.zeros(len(ok))
sc = ax.scatter(np.log1p(ok["notional"]), ok["pim"], c=c, cmap="coolwarm", s=32, alpha=0.8)
ax.set_xlabel("log1p(home notional)"); ax.set_ylabel("PIM"); ax.set_title("Hourly elasticity scatter")
fig.colorbar(sc, ax=ax, label="DCM̂")

# regime split using pooled quantiles when available
reg = pooled.get("regime_point") or {}
q_lo, q_hi = reg.get("q_low"), reg.get("q_high")
ax = axes[1]
if q_lo is not None and q_hi is not None and np.isfinite(ok["dcm"]).any():
    low = ok[ok["dcm"] <= q_lo]
    high = ok[ok["dcm"] >= q_hi]
    mid = ok[(ok["dcm"] > q_lo) & (ok["dcm"] < q_hi)]
    ax.scatter(np.log1p(mid["notional"]), mid["pim"], s=20, alpha=0.35, c="#bbb", label="mid")
    ax.scatter(np.log1p(low["notional"]), low["pim"], s=36, alpha=0.8, c="#98c1d9", label=f"DCM≤q25 n={len(low)}")
    ax.scatter(np.log1p(high["notional"]), high["pim"], s=36, alpha=0.8, c="#ee6c4d", label=f"DCM≥q75 n={len(high)}")
    ax.legend(fontsize=8)
else:
    ax.text(0.5, 0.5, "regime quantiles unavailable", ha="center", transform=ax.transAxes)
ax.set_xlabel("log1p(notional)"); ax.set_ylabel("PIM"); ax.set_title("Regime strips (pooled q25/q75)")
plt.tight_layout(); plt.show()
print("pooled corr", ok["notional"].corr(ok["pim"]), "n", len(ok))
'''
        ),
        md("## Expansion — day-by-day corr + chronological sensitivity"),
        code(
            r'''
# recompute per-day corr from hourly join
rows = []
for day, g in ok.groupby("day"):
    if len(g) >= 3:
        rows.append({"day": day, "n": len(g), "corr": float(g["notional"].corr(g["pim"]))})
dd = pd.DataFrame(rows)
fig, ax = plt.subplots(figsize=(9.5, 3.6))
ax.bar(dd["day"], dd["corr"], color="#3d5a80")
ax.axhline(0, color="k", lw=0.8)
ax.tick_params(axis="x", rotation=70)
ax.set_title("Per-day corr(notional, PIM)"); ax.set_ylabel("corr")
plt.tight_layout(); plt.show()
display(dd.round(4))

# chronological split (first half days vs second)
days = sorted(ok["day"].unique())
if len(days) >= 4:
    mid = len(days) // 2
    for label, subset in (("early", days[:mid]), ("late", days[mid:])):
        g = ok[ok["day"].isin(subset)]
        print(label, "days", subset, "corr", float(g["notional"].corr(g["pim"])), "n", len(g))
'''
        ),
        md("## Signal board"),
        code(
            r'''
print_board([
    ("liq.elasticity_regime", "Hold", "pooled n=88 corr≈−0.46 CI excludes 0; sign ≠ paper; ceiling Hold"),
    ("alpha.tob_cross_arb", "Kill", "elasticity monitor ≠ arb α"),
])
p2 = load_json(PASS2 / "pass2_falsifiers.json") if PASS2.is_dir() else None
if p2:
    print("pass2 elasticity_pooled_pass1.all:", (p2.get("elasticity_pooled_pass1") or {}).get("all"))
    print("pass2 falsifiers keys:", list((p2.get("falsifiers") or {}).keys()))
else:
    print("Falsifiers: out/pass2/ missing")
'''
        ),
    ]


def lstar_nb() -> list[dict]:
    return [
        md(
            """# LSTAR panel — **PARK**

**Paper:** §3.2 LSTAR / logistic smooth transition (PDF pp. 16–20; Eqs 4–7) · **NOTES:** [`NOTES.md`](NOTES.md)  
**Status:** `park` — γ / c unidentified on short crypto day-panel; full GMM + FE not attempted.

Paper transition:

$$G(z_{t-1}) = \\frac{1}{1+\\exp(-\\gamma(z_{t-1}-c))}$$

Desk keeps `cdme.logistic_G` as a continuous constrained weight for monitors, not a Promote path.
"""
        ),
        code(BOOT),
        md("## Why parked"),
        code(
            r'''
dcm_panel = load_json(OUT / "dcm_proxies" / "panel_rows.json") or []
hourly = expand_dcm_hourly(dcm_panel)
n_days = hourly["day"].nunique() if len(hourly) else 0
n_finite = int(np.isfinite(hourly.get("dcm", pd.Series(dtype=float))).sum()) if len(hourly) else 0
print(f"usable DCM hours={n_finite} across {n_days} days — far below paper's multi-year FX panel")
print("Park reasons: (1) short tape (2) no triplet FE design (3) γ/c NLS unidentified (4) funding proxy ≠ bank DCM")
'''
        ),
        md("## Toy / illustrative — logistic G on synthetic + observed DCM̂"),
        code(
            r'''
z = np.linspace(-3, 3, 200)
fig, axes = plt.subplots(1, 2, figsize=(11.5, 3.8))
ax = axes[0]
for g in (0.5, 1.0, 5.0, 20.0):
    ax.plot(z, cdme.logistic_G(z, gamma=g, c=0.0), label=f"γ={g}")
ax.set_xlabel("z (DCM)"); ax.set_ylabel("G"); ax.set_title("Paper-style logistic G (toy)")
ax.legend(fontsize=8)

ax = axes[1]
d = hourly["dcm"].to_numpy(dtype=float) if len(hourly) else np.array([])
finite = d[np.isfinite(d)]
if finite.size:
    G = cdme.logistic_G(finite, gamma=1.0)
    ax.hist(G, bins=20, color="#3d5a80", alpha=0.85)
    ax.set_title(f"G(DCM̂) on Pass-1 hours (n={finite.size})")
    ax.set_xlabel("G")
else:
    ax.text(0.5, 0.5, "no DCM hours", ha="center", transform=ax.transAxes)
plt.tight_layout(); plt.show()
'''
        ),
        md("## Signal board"),
        code(
            r'''
print_board([
    ("disc.lstar_gmm", "Park", "γ/c + FE unidentified on short tape — do not Promote"),
    ("risk.dcm_pc1", "Hold", "logistic_G helper OK for monitor weight only"),
])
print("Falsifier status: N/A while parked; re-open if multi-month panel + real funding arrives")
'''
        ),
    ]


def model_nb() -> list[dict]:
    return [
        md(
            """# Constrained-dealer model — **PARK**

**Paper:** §4 partial-equilibrium model (PDF pp. 23–30; Eqs 8–20) · **NOTES:** [`NOTES.md`](NOTES.md)  
**Status:** `park` — qualitative crypto-calibrated DGP only; not a trading engine.

Intuition: higher constraint intensity η raises effective spreads / weakens liquidity supply; PIM-like gaps widen when dealers cannot absorb inventory.
"""
        ),
        code(BOOT),
        md("## Toy simulation — constraint intensity vs clearing spread"),
        code(
            r'''
# Extremely reduced toy (not paper Prop 1 proof): mean-variance dealer with funding wedge η.
# q = (a - η - e) / (ρ σ²) for long side; spread proxy ↑ in η.

rho, sigma2, e = 1.0, 0.02, 0.0
demand = 1.5  # exogenous imbalance to clear
etas = np.linspace(0.0, 0.08, 40)
spreads = []
pim_proxy = []
for eta in etas:
    # ask needed to induce supply q=demand: a = e + η + q ρ σ²
    a = e + eta + demand * rho * sigma2
    b = e - eta - demand * rho * sigma2
    spr = a - b
    spreads.append(spr)
    # naive VLOOP-like residual if constrained mid stuck: grow with η
    pim_proxy.append(0.001 + 2.5 * eta)

fig, axes = plt.subplots(1, 2, figsize=(11.5, 3.8))
ax = axes[0]
ax.plot(etas, spreads, color="#3d5a80", lw=2)
ax.set_xlabel("constraint η"); ax.set_ylabel("bid-ask proxy"); ax.set_title("Toy: spread widens in η")
ax = axes[1]
ax.plot(etas, pim_proxy, color="#ee6c4d", lw=2)
ax.set_xlabel("constraint η"); ax.set_ylabel("PIM-like proxy"); ax.set_title("Toy: inefficiency rises in η")
plt.tight_layout(); plt.show()
print("Qualitative match only — park quantitative DGP until crypto-calibrated params exist")
'''
        ),
        md("## Signal board"),
        code(
            r'''
print_board([
    ("disc.constrained_dealer_dgp", "Park", "toy qualitative; no Promote path"),
])
print("Falsifier status: N/A while parked")
'''
        ),
    ]


def robust_nb() -> list[dict]:
    return [
        md(
            """# Robustness / falsifiers — Hold checklist

**Paper:** §5 (PDF pp. 30–35; Tables 6–9) · **NOTES:** [`NOTES.md`](NOTES.md) · **EXP:** [`EXP_REPORT.md`](EXP_REPORT.md)  
**Scripts:** `scripts/exp_pass2_falsifiers.py` → [`out/pass2/pass2_falsifiers.json`](../../out/pass2/pass2_falsifiers.json)

Paper: GIV for volume, DCM constituents, customer vs inter-bank split. Desk map without bank series: chronological split, block bootstrap, placebo DCM, venue drop, BTC widen. **Never** soft-Promote TOB-cross α.
"""
        ),
        code(BOOT),
        code(
            r'''
el = load_json(OUT / "elasticity_regimes" / "summary.json")
pim_panel = load_json(OUT / "pim_vloop_tcost" / "panel_rows.json") or []
dcm_panel = load_json(OUT / "dcm_proxies" / "panel_rows.json") or []
hourly = expand_dcm_hourly(dcm_panel)
p2 = load_json(PASS2 / "pass2_falsifiers.json") if PASS2.is_dir() else None
pass2_files = sorted(PASS2.rglob("*.json")) if PASS2.is_dir() else []
print("pass2 json files", [str(p.relative_to(OUT)) for p in pass2_files[:30]])
if p2:
    print("pass2 decisions", p2.get("decisions"))
    print("pass2 falsifier ok flags:")
    for k, v in (p2.get("falsifiers") or {}).items():
        print(f"  {k}: ok={v.get('ok') if isinstance(v, dict) else v}")
'''
        ),
        md("## Pass-2 falsifiers (artifact) + light notebook preview"),
        code(
            r'''
if p2:
    print(json.dumps({
        "chrono_split": (p2.get("falsifiers") or {}).get("chrono_split"),
        "block_bootstrap_by_day": (p2.get("falsifiers") or {}).get("block_bootstrap_by_day"),
        "placebo_pim_shuffle": (p2.get("falsifiers") or {}).get("placebo_pim_shuffle"),
        "placebo_dcm_regime": (p2.get("falsifiers") or {}).get("placebo_dcm_regime"),
    }, indent=2, default=str)[:3500])

ok = hourly[np.isfinite(hourly["pim"]) & np.isfinite(hourly["notional"])].copy()
# 1) chronological split (preview; canonical numbers in pass2 json)
days = sorted(ok["day"].unique())
mid = max(1, len(days)//2)
early, late = days[:mid], days[mid:]
def corr_sub(sub):
    g = ok[ok["day"].isin(sub)]
    return float(g["notional"].corr(g["pim"])) if len(g)>=5 else float("nan"), len(g)
ce, ne = corr_sub(early); cl, nl = corr_sub(late)
print(f"notebook chrono preview: early {early} corr={ce:.3f} n={ne} | late {late} corr={cl:.3f} n={nl}")

# 2) placebo DCM: shuffle within day then recompute regime delta if possible
rng = np.random.default_rng(42)
placebo_deltas = []
reg = ((el or {}).get("pooled") or {}).get("regime_point") or {}
q_lo, q_hi = reg.get("q_low"), reg.get("q_high")
real_delta = reg.get("delta")
if q_lo is not None and np.isfinite(ok["dcm"]).sum() > 10:
    for _ in range(200):
        shuf = ok.copy()
        shuf["dcm"] = shuf.groupby("day")["dcm"].transform(lambda s: rng.permutation(s.to_numpy()))
        low = shuf[shuf["dcm"] <= q_lo]
        high = shuf[shuf["dcm"] >= q_hi]
        if len(low)>=5 and len(high)>=5:
            dlt = float(high["notional"].corr(high["pim"]) - low["notional"].corr(low["pim"]))
            placebo_deltas.append(dlt)
    placebo_deltas = np.asarray(placebo_deltas)
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    ax.hist(placebo_deltas, bins=25, color="#98c1d9", edgecolor="white")
    if real_delta is not None:
        ax.axvline(real_delta, color="#ee6c4d", lw=2, label=f"real Δ={real_delta:.3f}")
    ax.set_title("Placebo regime Δ (shuffle DCM within day)"); ax.legend()
    plt.tight_layout(); plt.show()
    if real_delta is not None and placebo_deltas.size:
        p = float(np.mean(np.abs(placebo_deltas) >= abs(real_delta)))
        print(f"placebo two-sided p≈{p:.3f} (exploratory — not Promote; pass2 placebo_dcm ok=0)")
else:
    print("skip placebo — regime quantiles or DCM sparse")

# 3) venue honesty on certified panel
tbl = day_summary_table(pim_panel, inventory=KR_INV)
n3 = int((tbl["n_venues"] >= 3).sum()) if len(tbl) else 0
n_synth = int(tbl["kraken"].isin(["trade_synth", "PROXY_NOT_TOB_trade_synth"]).sum()) if len(tbl) else 0
n_spot = int((tbl["kraken"] == "spot_l2").sum()) if len(tbl) else 0
n_2v = int((tbl["kraken"] == "absent_2venue").sum()) if len(tbl) else 0
print(f"venue panel: {n3}/{len(tbl)} days with KR spot_l2; 2-venue={n_2v} spot_l2={n_spot} synth={n_synth}")
print("trade_synth QUARANTINED; venue-drop ablation deferred — Hold")
'''
        ),
        md("## Checklist vs paper §5"),
        code(
            r'''
checks = [
    ("time-split elasticity", "pass2 chrono_split sign-stable", "Hold"),
    ("block bootstrap CI", "pass2 block_bootstrap_by_day", "Hold"),
    ("placebo PIM shuffle", "pass2 passes", "Hold"),
    ("placebo DCM regime", "inconclusive (ok=0)", "Hold"),
    ("venue drop", "certified 2-venue + spot_l2; synth quarantined — deferred", "Hold"),
    ("BTC widen", "not run", "Hold"),
    ("bank CDS/VaR constituents", "Kill vanity", "Kill"),
    ("TOB-cross α", "Kill", "Kill"),
]
print(f"{'check':32s} {'status':40s} gate")
print("-"*90)
for a,b,g in checks:
    print(f"{a:32s} {b:40s} {g}")
'''
        ),
        md("## Signal board"),
        code(
            r'''
print_board([
    ("risk.cdme_falsifier_board", "Hold", "Pass-2 falsifiers run; 0 Promote"),
    ("risk.bank_cds_var", "Kill", "vanity"),
    ("alpha.tob_cross_arb", "Kill", "never Promote"),
])
'''
        ),
    ]


def desk() -> list[dict]:
    return [
        md(
            """# cd_me — desk synthesis

Huang–Ranaldo–Schrimpf–Somogyi (2021) *Constrained Dealers and Market Efficiency*.

Lib: `research.lib.cdme` · Data: **HL + Deribit** real quotes (+ Kraken **spot_l2** when dense) · **No ClickHouse MCP**.

**Board:** PIM / DCM̂ / elasticity = **Hold Monitor** · TOB-cross α = **Kill** · LSTAR/model = **Park** · `live_orders=false` · **0 Promote**.

## Certified panel status

- **Primary:** `panel_core_2venue` **n=9** — 2026-09-14…18, 25–27, 2026-10-01 ([`out/panel_completeness/`](../out/panel_completeness/))
- **Spot_l2 subpanel:** **n=4** — 2026-09-25, 26, 27, 2026-10-01
- **Retracted:** “10/10 three-venue + trade_synth” — synth **QUARANTINED** (`has_synth=false` on PIM outs)
- **Elasticity:** n=88 corr=−0.46 CI[−0.57,−0.35]; falsifiers [`out/pass2/pass2_falsifiers.json`](../out/pass2/pass2_falsifiers.json)

Chapter deep-dives:
- [`../chapters/ch00_overview/ch00_overview.ipynb`](../chapters/ch00_overview/ch00_overview.ipynb)
- [`../chapters/pim_vloop_tcost/pim_vloop_tcost.ipynb`](../chapters/pim_vloop_tcost/pim_vloop_tcost.ipynb)
- [`../chapters/dcm_proxies/dcm_proxies.ipynb`](../chapters/dcm_proxies/dcm_proxies.ipynb)
- [`../chapters/elasticity_regimes/elasticity_regimes.ipynb`](../chapters/elasticity_regimes/elasticity_regimes.ipynb)
- park: `lstar_panel`, `model_sim` · checklist: `robustness`

See [`../DESK_MEMO.md`](../DESK_MEMO.md) · [`../CHAPTER_INDEX.md`](../CHAPTER_INDEX.md) · shadow [`../applications/paper_shadow/`](../applications/paper_shadow/).
"""
        ),
        code(BOOT),
        code(
            r'''
SHADOW = BOOK / "applications" / "paper_shadow" / "out"
pim = load_json(OUT / "pim_vloop_tcost" / "summary.json")
dcm = load_json(OUT / "dcm_proxies" / "summary.json")
el = load_json(OUT / "elasticity_regimes" / "summary.json")
p2 = load_json(PASS2 / "pass2_falsifiers.json") if PASS2.is_dir() else None
pim_panel = load_json(OUT / "pim_vloop_tcost" / "panel_rows.json") or []
dcm_panel = load_json(OUT / "dcm_proxies" / "panel_rows.json") or []
hourly_pim = expand_pim_hourly(pim_panel)
hourly_dcm = expand_dcm_hourly(dcm_panel)
print("pim days", None if not pim else pim.get("days"), "n_ok", None if not pim else pim.get("n_ok"),
      "venues", None if not pim else pim.get("venues"))
print("dcm n_ok", None if not dcm else dcm.get("n_ok"))
print("elasticity days", None if not el else el.get("days"))
print("pass2", PASS2.is_dir(), "promote_count", None if not p2 else (p2.get("decisions") or {}).get("promote_count"))
'''
        ),
        md("## 1. Signal board (pinned)"),
        code(
            r'''
print_board()
board = SHADOW / "SHADOW_BOARD.md"
if board.exists():
    display(Markdown(board.read_text()))
'''
        ),
        md("## 2. PIM chapter findings (certified real quotes)"),
        code(
            r'''
tbl = day_summary_table(pim_panel, inventory=KR_INV)
display(tbl.round(4))
print("kraken modes:", tbl["kraken"].value_counts().to_dict())
show_pngs(OUT / "pim_vloop_tcost" / "figs")
'''
        ),
        md("### Inline — ToD + VLOOP–TCOST"),
        code(
            r'''
h = hourly_pim
fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.0))
tod = h.groupby("hour_utc")["pim"].mean()
axes[0].bar(tod.index, tod.values, color="#3d5a80")
axes[0].set_title("PIM ToD (UTC, certified)"); axes[0].set_xlabel("hour")
ok = h[np.isfinite(h["vloop"]) & np.isfinite(h["tcost"])]
axes[1].scatter(ok["vloop"], ok["tcost"], s=22, alpha=0.6, c="#ee6c4d")
axes[1].set_xlabel("VLOOP"); axes[1].set_ylabel("TCOST"); axes[1].set_title("VLOOP vs TCOST (hourly)")
plt.tight_layout(); plt.show()
print("corr(V,T)", float(ok["vloop"].corr(ok["tcost"])) if len(ok)>2 else None)
'''
        ),
        md("## 3. DCM̂ findings"),
        code(
            r'''
rows = []
for d in dcm_panel:
    meta = d.get("dcm") or {}
    load = meta.get("loadings") or {}
    rows.append({"day": d.get("day"), "n_valid": meta.get("n_valid"), "explained": meta.get("explained_var"),
                 "L_fund": load.get("abs_funding"), "L_rv": load.get("rv"), "L_imb": load.get("abs_imbalance")})
display(pd.DataFrame(rows).round(4))
show_pngs(OUT / "dcm_proxies" / "figs")
'''
        ),
        md("## 4. Elasticity findings"),
        code(
            r'''
pooled = (el or {}).get("pooled") or {}
print(json.dumps({"all": pooled.get("all"), "regime": pooled.get("regime_point"),
                  "ceiling": pooled.get("decision_ceiling")}, indent=2, default=str))
show_pngs(OUT / "elasticity_regimes" / "figs")
ok = hourly_dcm[np.isfinite(hourly_dcm["pim"]) & np.isfinite(hourly_dcm["notional"])]
fig, ax = plt.subplots(figsize=(6.5, 4.0))
sc = ax.scatter(np.log1p(ok["notional"]), ok["pim"], c=ok["dcm"], cmap="coolwarm", s=30, alpha=0.8)
ax.set_xlabel("log1p(notional)"); ax.set_ylabel("PIM"); ax.set_title("Desk elasticity scatter")
fig.colorbar(sc, ax=ax, label="DCM̂")
plt.tight_layout(); plt.show()
'''
        ),
        md("## 5. Pass-2 / Kraken honesty / shadow"),
        code(
            r'''
print("Kraken: dense spot_l2 only; else absent_2venue. trade_synth QUARANTINED (PROXY/NOT TOB).")
print("certified primary:", PRIMARY)
print("spot_l2 subpanel:", SPOT)
ks = (pim or {}).get("kraken_status") or []
for row in ks:
    print(f"  {row.get('day')}: {row.get('kraken_mode')} in_tob={row.get('in_tob')}")

if p2:
    print("pass2 decisions:", json.dumps(p2.get("decisions"), indent=2))
    pp = p2.get("pim_panel") or {}
    print("pass2 n_ok", pp.get("n_days_ok"), "has_synth", (pim or {}).get("has_synth"))
else:
    print("out/pass2/ not present")

meta = load_json(SHADOW / "shadow_meta.json")
print("shadow_meta", json.dumps(meta, indent=2)[:800] if meta else None)
events = SHADOW / "events.jsonl"
if events.exists():
    n = sum(1 for _ in events.open())
    print("events.jsonl lines", n)
'''
        ),
        md("## 5b. Companion synthesis figs (`out/desk_synthesis/figs/`)"),
        code(
            r'''
show_pngs(OUT / "desk_synthesis" / "figs")
'''
        ),
        md(
            """## 6. Honesty

- Scoreboard = **monitor telemetry**, not PnL alpha  
- Primary = HL↔Deribit real quotes; Kraken spot_l2 secondary; `trade_synth` **QUARANTINED**  
- Negative crypto elasticity corr ≠ soft-Promote of paper FX result  
- 0 Promote · Hold monitors · Kill TOB-cross α · Park LSTAR/model
"""
        ),
        code(
            r'''
print_board()
print("\\nChapter notebooks ready under chapters/*/ — see CHAPTER_INDEX notebook section.")
'''
        ),
    ]


def main() -> None:
    write_nb(CH / "ch00_overview" / "ch00_overview.ipynb", ch00(), "ch00")
    write_nb(CH / "pim_vloop_tcost" / "pim_vloop_tcost.ipynb", pim_nb(), "pim")
    write_nb(CH / "dcm_proxies" / "dcm_proxies.ipynb", dcm_nb(), "dcm")
    write_nb(CH / "elasticity_regimes" / "elasticity_regimes.ipynb", elast_nb(), "elast")
    write_nb(CH / "lstar_panel" / "lstar_panel.ipynb", lstar_nb(), "lstar")
    write_nb(CH / "model_sim" / "model_sim.ipynb", model_nb(), "model")
    write_nb(CH / "robustness" / "robustness.ipynb", robust_nb(), "robust")
    write_nb(NB / "desk_synthesis.ipynb", desk(), "desk")


if __name__ == "__main__":
    main()
