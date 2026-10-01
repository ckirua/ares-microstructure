from __future__ import annotations
#!/usr/bin/env python3
"""Build memo-quality notebooks + figures from out/ JSON artifacts.

Mirrors empirical_mm density: theory → load artifacts → tables/plots → gate.
Does not require warehouse (plots from existing JSON). ClickHouse MCP banned.
"""

import os

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

BOOK = Path(__file__).resolve().parents[1]
OUT = BOOK / "out"


def _load(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _nb(cells: list) -> dict:
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "cells": cells,
    }


def _md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": [line + "\n" for line in text.strip("\n").split("\n")]}


def _code(text: str) -> dict:
    return {
        "cell_type": "code",
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": [line + "\n" for line in text.strip("\n").split("\n")],
    }


def _savefig(fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def plot_daily_minv(daily: dict) -> Path | None:
    rows = [r for r in (daily or {}).get("rows") or [] if r.get("ok") and np.isfinite(r.get("min_v", np.nan))]
    if not rows:
        return None
    fig, ax = plt.subplots(figsize=(10, 4.2))
    venues = sorted({r["venue"] for r in rows})
    colors = {"hyperliquid": "#1f77b4", "deribit": "#ff7f0e", "kraken": "#2ca02c"}
    for v in venues:
        sub = [r for r in rows if r["venue"] == v and r.get("hn_min") == 5]
        if not sub:
            continue
        xs = list(range(len(sub)))
        ys = [r["min_v"] for r in sub]
        labs = [r["day"][5:] for r in sub]
        ax.plot(xs, ys, "o-", label=v, color=colors.get(v), alpha=0.85)
        for x, y, r in zip(xs, ys, sub):
            if r.get("sig_5"):
                ax.scatter([x], [y], s=90, facecolors="none", edgecolors="red", linewidths=1.5, zorder=5)
        ax.set_xticks(xs)
        ax.set_xticklabels(labs, rotation=45, ha="right")
    ax.axhline(0, color="gray", lw=0.8)
    ax.set_ylabel("MinV (hn=5m)")
    ax.set_title("UTC-day MinV panel — red ring = EGARCH 5% significant")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.3)
    path = OUT / "daily_minv" / "fig_minv_panel.png"
    _savefig(fig, path)
    return path


def plot_hn_fragility(daily: dict) -> Path | None:
    rows = [r for r in (daily or {}).get("rows") or [] if r.get("ok") and r.get("complete")]
    if not rows:
        rows = [r for r in (daily or {}).get("rows") or [] if r.get("ok")]
    if not rows:
        return None
    # mean MinV by hn
    hns = sorted({r["hn_min"] for r in rows if "hn_min" in r})
    fig, ax = plt.subplots(figsize=(7, 3.8))
    for v in sorted({r["venue"] for r in rows}):
        means, ns = [], []
        for h in hns:
            vals = [r["min_v"] for r in rows if r["venue"] == v and r.get("hn_min") == h and np.isfinite(r.get("min_v", np.nan))]
            means.append(float(np.mean(vals)) if vals else np.nan)
            ns.append(len(vals))
        ax.plot(hns, means, "o-", label=f"{v} (n≈{max(ns) if ns else 0})")
    ax.set_xlabel("hn (minutes)")
    ax.set_ylabel("mean MinV")
    ax.set_title("hn fragility — mean MinV across sample days")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    path = OUT / "daily_minv" / "fig_hn_fragility.png"
    _savefig(fig, path)
    return path


def plot_post_trough(daily: dict) -> Path | None:
    rows = [r for r in (daily or {}).get("rows") or [] if r.get("ok") and r.get("sig_5") and r.get("post_trough")]
    if not rows:
        rows = [r for r in (daily or {}).get("rows") or [] if r.get("ok") and r.get("post_trough")]
    if not rows:
        return None
    horizons = ["ret_60s", "ret_300s", "ret_1800s"]
    data = {h: [r["post_trough"].get(h) for r in rows if np.isfinite(r["post_trough"].get(h, np.nan))] for h in horizons}
    fig, ax = plt.subplots(figsize=(7, 3.8))
    xs = np.arange(len(horizons))
    means = [float(np.mean(data[h])) if data[h] else np.nan for h in horizons]
    stds = [float(np.std(data[h])) if data[h] else np.nan for h in horizons]
    ax.bar(xs, means, yerr=stds, capsize=4, color="#4c72b0", alpha=0.85)
    ax.axhline(0, color="gray", lw=0.8)
    ax.set_xticks(xs)
    ax.set_xticklabels(["60s", "300s", "1800s"])
    ax.set_ylabel("mean post-trough return")
    ax.set_title(f"Post-trough returns (n={len(rows)} rows with post paths)")
    ax.grid(True, axis="y", alpha=0.3)
    path = OUT / "daily_minv" / "fig_post_trough.png"
    _savefig(fig, path)
    return path


def plot_xvenue(xven: dict) -> Path | None:
    rows = (xven or {}).get("rows") or []
    if not rows:
        return None
    fig, ax = plt.subplots(figsize=(9, 4))
    days = [r.get("day", "?") for r in rows]
    n_complete = [r.get("n_complete", 0) for r in rows]
    n_sig = [len(r.get("sig_venues") or []) for r in rows]
    n_conc = [sum(1 for p in (r.get("pairs") or []) if p.get("concord_5m")) for r in rows]
    x = np.arange(len(days))
    w = 0.25
    ax.bar(x - w, n_complete, width=w, label="n_complete venues")
    ax.bar(x, n_sig, width=w, label="n sig@5%")
    ax.bar(x + w, n_conc, width=w, label="concordant pairs")
    ax.set_xticks(x)
    ax.set_xticklabels([d[5:] for d in days], rotation=45, ha="right")
    ax.set_ylabel("count")
    ax.set_title("Cross-venue MinV concordance by UTC day")
    ax.legend(fontsize=8)
    ax.grid(True, axis="y", alpha=0.3)
    path = OUT / "xvenue_concord" / "fig_concord.png"
    _savefig(fig, path)
    return path


def plot_liq(liq: dict) -> Path | None:
    rows = (liq or {}).get("rows") or []
    usable = [r for r in rows if isinstance(r.get("liq"), dict) and "spread_bps_mean" in r["liq"]]
    if not usable:
        # coverage bar instead
        fig, ax = plt.subplots(figsize=(8, 3.5))
        venues = sorted({r.get("venue", "?") for r in rows})
        has = [sum(1 for r in rows if r.get("venue") == v and "tob_error" not in r and r.get("liq", {}).get("note") != "tob_unavailable") for v in venues]
        miss = [sum(1 for r in rows if r.get("venue") == v) - h for v, h in zip(venues, has)]
        ax.bar(venues, has, label="TOB join ok")
        ax.bar(venues, miss, bottom=has, label="TOB missing/err")
        ax.set_title("TOB coverage around MinV (honest)")
        ax.legend()
        path = OUT / "liq_around_v" / "fig_tob_coverage.png"
        _savefig(fig, path)
        return path
    fig, ax = plt.subplots(figsize=(8, 3.8))
    pre = [r["liq"].get("spread_bps_pre", np.nan) for r in usable]
    post = [r["liq"].get("spread_bps_post", np.nan) for r in usable]
    labs = [f"{r['venue'][:2]} {r['day'][5:]}" for r in usable]
    x = np.arange(len(usable))
    ax.bar(x - 0.2, pre, width=0.4, label="spread pre (bps)")
    ax.bar(x + 0.2, post, width=0.4, label="spread post (bps)")
    ax.set_xticks(x)
    ax.set_xticklabels(labs, rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("spread bps")
    ax.set_title("Quoted spread around MinV τ*")
    ax.legend(fontsize=8)
    path = OUT / "liq_around_v" / "fig_spread_around.png"
    _savefig(fig, path)
    return path


def plot_bootstrap(boot: dict, kill: dict) -> Path | None:
    if not boot:
        return None
    models = [k for k in ("0", "1", "2", "3") if k in boot]
    if not models:
        return None
    fig, ax = plt.subplots(figsize=(7, 3.8))
    x = np.arange(len(models))
    rej5 = [boot[m].get("pct_rej_5", np.nan) for m in models]
    rej1 = [boot[m].get("pct_rej_1", np.nan) for m in models]
    ax.bar(x - 0.2, rej5, width=0.4, label="% rej @5%")
    ax.bar(x + 0.2, rej1, width=0.4, label="% rej @1%")
    ax.axhline(5, color="red", ls="--", lw=0.9, label="nominal 5%")
    ax.set_xticks(x)
    ax.set_xticklabels([f"M{m}" for m in models])
    ax.set_ylabel("% reject")
    title = "Models 0–3 size/power (desk-scale MC)"
    if kill:
        title += " — asymptotic bands Kill"
    ax.set_title(title)
    ax.legend(fontsize=8)
    ax.set_ylim(0, 110)
    path = OUT / "bootstrap_sim" / "fig_size_power.png"
    _savefig(fig, path)
    return path


def plot_vstat_panel(panel: dict) -> Path | None:
    venues = (panel or {}).get("venues") or {}
    if not venues:
        return None
    # Schema: venues[venue][day] = {completeness, instrument, hn: {1|5|30|...: rec}}
    points = []
    for venue, days in venues.items():
        if not isinstance(days, dict):
            continue
        for day, day_rec in days.items():
            if not isinstance(day_rec, dict):
                continue
            hn_map = day_rec.get("hn") if isinstance(day_rec.get("hn"), dict) else day_rec
            if not isinstance(hn_map, dict):
                continue
            for hn, rec in hn_map.items():
                if hn in ("completeness", "instrument"):
                    continue
                if isinstance(rec, dict) and rec.get("ok") and np.isfinite(rec.get("min_v", np.nan)):
                    points.append(
                        {
                            "venue": venue,
                            "day": day,
                            "hn": str(hn),
                            "min_v": rec["min_v"],
                            "sig_5": rec.get("sig_5"),
                        }
                    )
    if not points:
        return None
    fig, ax = plt.subplots(figsize=(10, 4))
    for v in sorted({p["venue"] for p in points}):
        sub = [p for p in points if p["venue"] == v and str(p["hn"]).startswith("5") and "preavg" not in str(p["hn"])]
        if not sub:
            sub = [p for p in points if p["venue"] == v]
        sub = sorted(sub, key=lambda z: z["day"])
        ax.plot([p["day"][5:] for p in sub], [p["min_v"] for p in sub], "o-", label=v)
        for p in sub:
            if p.get("sig_5"):
                ax.scatter([p["day"][5:]], [p["min_v"]], s=80, facecolors="none", edgecolors="red", zorder=5)
    ax.set_title("V-statistic MinV by venue/day (core panel, hn≈5m)")
    ax.legend(fontsize=8)
    ax.tick_params(axis="x", rotation=45)
    ax.grid(True, alpha=0.3)
    path = OUT / "v_statistic" / "fig_minv_core.png"
    _savefig(fig, path)
    return path


def plot_rollup(rollup: dict) -> Path | None:
    if not rollup:
        return None
    counts = {
        "Promote": len(rollup.get("promotes") or []),
        "Hold": len(rollup.get("holds") or []),
        "Kill": len(rollup.get("kills") or []),
    }
    fig, ax = plt.subplots(figsize=(5.5, 3.5))
    colors = {"Promote": "#2ca02c", "Hold": "#ff7f0e", "Kill": "#d62728"}
    ax.bar(list(counts.keys()), list(counts.values()), color=[colors[k] for k in counts])
    ax.set_title("Hardening gate counts")
    ax.set_ylabel("candidates")
    for i, (k, v) in enumerate(counts.items()):
        ax.text(i, v + 0.1, str(v), ha="center")
    path = OUT / "fig_gate_counts.png"
    _savefig(fig, path)
    return path


def write_ch00(rollup: dict) -> None:
    cells = [
        _md(
            """# Ch.00 Overview — V-shapes

Flora & Renò (2020), SSRN 3554122. Core claim: market inefficiency = sudden **sign change of drift** (V / Λ), detected by the econometric V-statistic — **not** a volatility spike and **not** the geometric Dugast–Foucault detector in `research.lib.crash.vshape_events`.

$$V_{\\tau,n}=\\sqrt{h_n}\\,T^+_{\\tau,n}\\,T^-_{\\tau,n}$$

Negative significant MinV ⇒ reverting-drift / fragility day.
"""
        ),
        _code(
            """from pathlib import Path
import json
OUT = Path('../../out').resolve()
rollup = json.loads((OUT / 'hardening_rollup.json').read_text())
print('Promotes:', [p['id'] for p in rollup.get('promotes', [])])
print('Holds:', [h['id'] for h in rollup.get('holds', [])])
print('Kills:', [k['id'] for k in rollup.get('kills', [])])
print('n_sig5_complete:', rollup.get('n_sig5_complete'))
"""
        ),
        _md("### Gate rollup figure\n\n`out/fig_gate_counts.png`"),
        _code(
            """from IPython.display import Image, display
from pathlib import Path
p = Path('../../out/fig_gate_counts.png')
print(p.resolve(), 'exists', p.exists(), 'bytes', p.stat().st_size if p.exists() else 0)
if p.exists():
    display(Image(filename=str(p)))
"""
        ),
        _md(
            """## Taxonomy (Pass 2)

| Object | What it detects | Desk use |
|--------|-----------------|----------|
| Flora–Renò MinV | Sign-change of drift on kernel half-windows | **risk monitor** (EGARCH bands) |
| Jump / vol spike | Large |r| or σ̂, not necessarily drift flip | risk, not V |
| Geometric V (`crash.vshape_events`) | Move + recovery path geometry | Tee–Ting baseline; do not merge APIs |
| Liq hole | Spread/depth collapse without V | exec / liq |

## Desk takeaway

- Promote framing: `risk.v_vs_jump_taxonomy` + EGARCH MinV bands.
- Auction-loss ID stays **Hold** (no crypto sovereign auction analogue).
"""
        ),
    ]
    path = BOOK / "chapters" / "ch00_overview" / "ch00_overview.ipynb"
    path.write_text(json.dumps(_nb(cells), indent=1))


def write_vstat(panel: dict, daily: dict) -> None:
    cells = [
        _md(
            """# V-statistic — continuous path + MinV

Pass 1 implements §3 kernels / \(T^\\pm\) / \(V\) in `research.lib.vstat`. Pass 2 treats continuous \(V_t\) as an **info feature** (lead-lag vs future \(r^2\)), not only the MinV binary.

Grid: **5s** last-print (desk speed; paper 1s). Bandwidth \(h_n \\in \\{1,5,30\\}\) minutes. EGARCH bootstrap CIs — asymptotic 2.18/3.60 **Kill**.
"""
        ),
        _code(
            """from pathlib import Path
import json
import pandas as pd
OUT = Path('../../out/v_statistic').resolve()
panel = json.loads((OUT / 'panel_eth.json').read_text()) if (OUT / 'panel_eth.json').exists() else {}
daily = json.loads(Path('../../out/daily_minv/daily_minv_eth.json').resolve().read_text())
rows = [r for r in daily.get('rows', []) if r.get('ok')]
df = pd.DataFrame(rows)
print('days', daily.get('days'))
print('ok rows', len(df), 'sig5', int(df['sig_5'].sum()) if len(df) else 0)
print(df.groupby(['venue','hn_min'])['min_v'].mean().unstack().round(2) if len(df) else 'empty')
"""
        ),
        _md("### Core / daily MinV figures\n\n`fig_minv_core.png` (if present) · `../daily_minv/fig_minv_panel.png`"),
        _code(
            """from IPython.display import Image, display
from pathlib import Path
for p in [Path('../../out/v_statistic/fig_minv_core.png'), Path('../../out/daily_minv/fig_minv_panel.png')]:
    print(p, p.exists())
    if p.exists():
        display(Image(filename=str(p)))
"""
        ),
        _md(
            """## Interpretation

- Significant MinV is a **fragility flag**, not a trade signal by itself.
- Pre-averaging sensitivity (`5_preavg5`) often deepens MinV — report both; do not cherry-pick.
- Candidate `info.v_path_continuous`: Promote only if lead-lag vs markout / future \(r^2\) survives time-split (see hardening).

## Gate

See `CANDIDATES.md` / DESK_MEMO signal board.
"""
        ),
    ]
    (BOOK / "chapters" / "v_statistic" / "v_statistic.ipynb").write_text(json.dumps(_nb(cells), indent=1))


def write_bootstrap(boot: dict, kill: dict) -> None:
    cells = [
        _md(
            """# Bootstrap / Models 0–3

Paper §3.1: EGARCH(1,1) simulated bootstrap for MinV critical values. §4 Models 0–3 size/power.

**Kill** `risk.asymptotic_218_360` as desk defaults (too small under realistic DGP + multiple testing).
**Promote** `risk.egarch_minv_bands` as the monitor CI.
"""
        ),
        _code(
            """from pathlib import Path
import json
OUT = Path('../../out/bootstrap_sim').resolve()
boot = json.loads((OUT / 'size_power_models0_3.json').read_text())
kill = json.loads((OUT / 'kill_asymptotic_bands.json').read_text())
print('kill', kill)
print('models', {k: boot[k] for k in boot if k != 'meta'})
print('meta', boot.get('meta'))
"""
        ),
        _md("### Size/power figure\n\n`fig_size_power.png`"),
        _code(
            """from IPython.display import Image, display
from pathlib import Path
p = Path('../../out/bootstrap_sim/fig_size_power.png')
print(p.resolve(), p.exists())
if p.exists():
    display(Image(filename=str(p)))
"""
        ),
        _md(
            """## Desk takeaway

- Always quote MinV vs **EGARCH bootstrap** quantiles on the same grid/dt.
- Desk-scale MC here is smaller than paper (see `meta.n_mc`); directionally supports Kill asymptotic bands.
"""
        ),
    ]
    (BOOK / "chapters" / "bootstrap_sim" / "bootstrap_sim.ipynb").write_text(json.dumps(_nb(cells), indent=1))


def write_daily(daily: dict) -> None:
    cells = [
        _md(
            """# Daily MinV panel

UTC-day MinV vs EGARCH 5%/1% bands on HL + Deribit + Kraken. Paper Table-2 style post-trough returns + \(h_n\) fragility + time-split falsifier.
"""
        ),
        _code(
            """from pathlib import Path
import json
import pandas as pd
import numpy as np
OUT = Path('../../out/daily_minv').resolve()
daily = json.loads((OUT / 'daily_minv_eth.json').read_text())
df = pd.DataFrame([r for r in daily['rows'] if r.get('ok')])
print('symbol', daily.get('symbol'), 'days', daily.get('days'))
print('n_ok', len(df), 'n_complete', int(df['complete'].sum()) if len(df) else 0)
print('sig5', int(df['sig_5'].sum()) if len(df) else 0, 'sig5&complete', int((df['sig_5'] & df['complete']).sum()) if len(df) else 0)
days = sorted(df['day'].unique())
mid = len(days)//2
early, late = set(days[:mid]), set(days[mid:])
print('time-split early', sorted(early), 'sig', int(df[df.day.isin(early) & df.sig_5].shape[0]))
print('time-split late ', sorted(late), 'sig', int(df[df.day.isin(late) & df.sig_5].shape[0]))
print(df.pivot_table(index='venue', columns='hn_min', values='min_v', aggfunc='mean').round(2))
"""
        ),
        _md("### MinV panel\n\n`fig_minv_panel.png`"),
        _code(
            """from IPython.display import Image, display
from pathlib import Path
display(Image(filename=str(Path('../../out/daily_minv/fig_minv_panel.png'))))
"""
        ),
        _md("### \(h_n\) fragility\n\n`fig_hn_fragility.png`"),
        _code(
            """from IPython.display import Image, display
from pathlib import Path
p = Path('../../out/daily_minv/fig_hn_fragility.png')
if p.exists():
    display(Image(filename=str(p)))
"""
        ),
        _md("### Post-trough returns\n\n`fig_post_trough.png`"),
        _code(
            """from IPython.display import Image, display
from pathlib import Path
p = Path('../../out/daily_minv/fig_post_trough.png')
if p.exists():
    display(Image(filename=str(p)))
"""
        ),
        _md(
            """## Gate

- `risk.daily_minv_panel` → **Promote** if ≥1 complete-day sig@5% appears in **both** early and late halves.
- `info.post_trough_ret` → **Promote** only if mean post-ret CI excludes 0 with time-split; else Hold.
"""
        ),
    ]
    (BOOK / "chapters" / "daily_minv" / "daily_minv.ipynb").write_text(json.dumps(_nb(cells), indent=1))


def write_event(event: dict) -> None:
    cells = [
        _md(
            """# Event case — stress-day dive

Paper §6-style deep dive on the most negative significant MinV among complete venue-days. Causal Italian-auction wealth transfer stays **Hold** (`id.auction_loss`).
"""
        ),
        _code(
            """from pathlib import Path
import json
ev = json.loads(Path('../../out/event_case/event_eth.json').resolve().read_text())
print(json.dumps(ev, indent=2, default=str))
"""
        ),
        _md(
            """## Regime proxy

BaU → trough → post using post-trough return windows on the stress day. Not an auction mechanism.

## Holds

| ID | Why |
|----|-----|
| `risk.stress_day_minv` | Narrative unless reproduced across multiple stress days / months |
| `id.auction_loss` | No crypto sovereign auction analogue — out of scope |
"""
        ),
        _code(
            """from pathlib import Path
import json
daily = json.loads(Path('../../out/daily_minv/daily_minv_eth.json').resolve().read_text())
stress_rows = [r for r in daily.get('rows', []) if r.get('ok') and r.get('complete') and r.get('sig_5') and r.get('hn_min')==5]
print('complete+sig5 @5m rows', len(stress_rows))
for r in sorted(stress_rows, key=lambda z: z.get('min_v', 0))[:8]:
    print(r['venue'], r['day'], 'MinV', round(r['min_v'],3), 'shape', r.get('shape'), 'post', r.get('post_trough'))
"""
        ),
    ]
    (BOOK / "chapters" / "event_case" / "event_case.ipynb").write_text(json.dumps(_nb(cells), indent=1))


def write_liq(liq: dict) -> None:
    cells = [
        _md(
            """# Liquidity around V

Paper §6.2: spread / depth / impact around MinV. Collector TOB under `ares-startarb/results/xarb_md/tob` — coverage is uneven (honest).

Grossman–Miller \(\\mu/\\sigma\): **monitor only** — Kill as tradable (`risk.gm_mu_sigma_tradable`).
"""
        ),
        _code(
            """from pathlib import Path
import json
import pandas as pd
liq = json.loads(Path('../../out/liq_around_v/liq_eth.json').resolve().read_text())
rows = liq.get('rows', [])
print('n_rows', len(rows))
for r in rows[:12]:
    print(r.get('venue'), r.get('day'), 'minv', r.get('minv'), 'liq', r.get('liq'), 'tob_err', r.get('tob_error', '')[:60])
"""
        ),
        _md("### TOB / spread figures"),
        _code(
            """from IPython.display import Image, display
from pathlib import Path
for name in ['fig_spread_around.png', 'fig_tob_coverage.png']:
    p = Path('../../out/liq_around_v') / name
    print(name, p.exists())
    if p.exists():
        display(Image(filename=str(p)))
"""
        ),
        _md(
            """## Gate

- `liq.spread_around_minv` → Promote only with multi-day TOB pre/post differential surviving placebo times.
- Otherwise **Hold** with documented TOB day coverage.
"""
        ),
    ]
    (BOOK / "chapters" / "liq_around_v" / "liq_around_v.ipynb").write_text(json.dumps(_nb(cells), indent=1))


def write_xvenue(xven: dict) -> None:
    cells = [
        _md(
            """# Cross-venue concordance

HL ↔ Deribit ↔ Kraken MinV \(\\tau^\\star\) concordance within \(h_n=5\)m among EGARCH-significant venues. Competing geometric V / Nanex counts stored per venue.
"""
        ),
        _code(
            """from pathlib import Path
import json
x = json.loads(Path('../../out/xvenue_concord/xvenue_eth.json').resolve().read_text())
for r in x.get('rows', []):
    print(r.get('day'), 'complete', r.get('n_complete'), 'sig', r.get('sig_venues'), 'pairs', r.get('pairs'))
"""
        ),
        _md("### Concordance figure\n\n`fig_concord.png`"),
        _code(
            """from IPython.display import Image, display
from pathlib import Path
p = Path('../../out/xvenue_concord/fig_concord.png')
if p.exists():
    display(Image(filename=str(p)))
"""
        ),
        _md(
            """## Gate

- `risk.xvenue_minv_concord` → **Promote** if ≥1 concordant significant pair on a day with ≥2 complete venues.
- Geometric overlap stays Hold / PR-table (do not merge with `crash.vshape_events`).
"""
        ),
    ]
    (BOOK / "chapters" / "xvenue_concord" / "xvenue_concord.ipynb").write_text(json.dumps(_nb(cells), indent=1))


def write_desk(rollup: dict) -> None:
    cells = [
        _md(
            """# V-shapes — desk synthesis

Program rollup for Flora & Renò (2020). Lib: `research.lib.vstat` (**not** `crash.vshape_events`). Data: HL + Deribit + Kraken warehouse trades + warehouse/collector TOB. No ClickHouse MCP.
"""
        ),
        _code(
            """from pathlib import Path
import json
OUT = (Path(os.environ.get('ARES_MICROSTRUCTURE') or (Path.home() / 'srv' / 'ares-microstructure')) / 'research' / 'books' / 'v_shapes' / 'out')
rollup = json.loads((OUT / 'hardening_rollup.json').read_text())
print(json.dumps(rollup, indent=2))
plan = OUT / 'widen_day_plan.json'
if plan.exists():
    print('widen plan', json.dumps(json.loads(plan.read_text()), indent=2)[:1600])
ti = OUT / 'trade_ideas.json'
if ti.exists():
    print('trade ideas', json.dumps(json.loads(ti.read_text()), indent=2)[:2000])
"""
        ),
        _md("### Gate counts\n\n`fig_gate_counts.png`"),
        _code(
            """from IPython.display import Image, display
from pathlib import Path
p = (Path(os.environ.get('ARES_MICROSTRUCTURE') or (Path.home() / 'srv' / 'ares-microstructure')) / 'research' / 'books' / 'v_shapes' / 'out' / 'fig_gate_counts.png')
if p.exists():
    display(Image(filename=str(p)))
"""
        ),
        _md("### Daily MinV + concordance + continuous V"),
        _code(
            """from IPython.display import Image, display
from pathlib import Path
import json
OUT = (Path(os.environ.get('ARES_MICROSTRUCTURE') or (Path.home() / 'srv' / 'ares-microstructure')) / 'research' / 'books' / 'v_shapes' / 'out')
for rel in ['daily_minv/fig_minv_panel.png', 'xvenue_concord/fig_concord.png', 'bootstrap_sim/fig_size_power.png', 'liq_around_v/fig_tob_coverage.png']:
    p = OUT / rel
    print(rel, p.exists())
    if p.exists():
        display(Image(filename=str(p)))
for name in ['continuous_v_eth.json', 'continuous_v_btc.json']:
    p = OUT / 'v_statistic' / name
    if p.exists():
        c = json.loads(p.read_text())
        print(name, 'n_ok', c.get('n_ok'), 'post300', c.get('post300'))
        print('leadlag_agg keys', list((c.get('leadlag_agg') or {}))[:8])
"""
        ),
        _md(
            """## Signal board + trade ideas

See `DESK_MEMO.md` §2 (gates) and §5 (trade ideas). EGARCH MinV bands = **Monitor**; asymptotic 2.18/3.60 and GM μ/σ-as-tradable stay **Kill**. Mean-reversion fade stays paper-only until `info.post_trough_ret` Promotes.
"""
        ),
        _code(
            """from pathlib import Path
import json
ideas = json.loads((Path(os.environ.get('ARES_MICROSTRUCTURE') or (Path.home() / 'srv' / 'ares-microstructure')) / 'research' / 'books' / 'v_shapes' / 'out' / 'trade_ideas.json').read_text())
for idea in ideas.get('ideas', []):
    print(idea['id'], '|', idea['label'], '|', idea['title'])
    print('  gates:', idea.get('gate_status'))
    print('  size:', idea.get('tradable_size'))
print('kill_no_alpha', ideas.get('kill_no_alpha'))
"""
        ),
    ]
    (BOOK / "notebooks" / "desk_synthesis.ipynb").write_text(json.dumps(_nb(cells), indent=1))


def write_trade_ideas() -> None:
    """Memo-grade trade_ideas notebook — never stub-overwrite.

    Dense notebook lives at notebooks/trade_ideas.ipynb (template:
    scripts/_trade_ideas_cells.json; regenerator: scripts/write_trade_ideas_nb.py).
    If present and already memo-grade (>=10 cells / >=200 src lines), preserve it.
    If missing or thin stub, rebuild from the frozen template — not the old 3-cell stub.
    """
    path = BOOK / "notebooks" / "trade_ideas.ipynb"
    if path.exists():
        try:
            nb = json.loads(path.read_text())
            n = len(nb.get("cells") or [])
            src_lines = sum(
                len("".join(c.get("source") or []).splitlines()) for c in (nb.get("cells") or [])
            )
        except Exception:
            n, src_lines = 0, 0
        if n >= 10 and src_lines >= 200:
            print(f"trade_ideas.ipynb preserved ({n} cells, {src_lines} src lines) — refusing stub overwrite")
            return
    # Missing or stub → regenerate memo-grade from frozen template
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "write_trade_ideas_nb", Path(__file__).resolve().parent / "write_trade_ideas_nb.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    out = mod.build_trade_ideas_notebook()
    print(f"trade_ideas.ipynb rebuilt memo-grade from template → {out}")


def main() -> int:
    daily = _load(OUT / "daily_minv" / "daily_minv_eth.json") or {}
    daily_btc = _load(OUT / "daily_minv" / "daily_minv_btc.json") or {}
    # merge for figures when BTC present
    if daily_btc.get("rows"):
        daily = {
            "symbol": "ETH+BTC",
            "days": sorted(set((daily.get("days") or []) + (daily_btc.get("days") or []))),
            "rows": (daily.get("rows") or []) + (daily_btc.get("rows") or []),
        }
    event = _load(OUT / "event_case" / "event_eth.json") or {}
    liq = _load(OUT / "liq_around_v" / "liq_eth.json") or {}
    liq_btc = _load(OUT / "liq_around_v" / "liq_btc.json") or {}
    if liq_btc.get("rows"):
        liq = {"rows": (liq.get("rows") or []) + (liq_btc.get("rows") or [])}
    xven = _load(OUT / "xvenue_concord" / "xvenue_eth.json") or {}
    xven_btc = _load(OUT / "xvenue_concord" / "xvenue_btc.json") or {}
    if xven_btc.get("rows"):
        xven = {"rows": (xven.get("rows") or []) + (xven_btc.get("rows") or [])}
    panel = _load(OUT / "v_statistic" / "panel_eth.json") or {}
    boot = _load(OUT / "bootstrap_sim" / "size_power_models0_3.json") or {}
    kill = _load(OUT / "bootstrap_sim" / "kill_asymptotic_bands.json") or {}
    rollup = _load(OUT / "hardening_rollup.json") or {}

    figs = {
        "daily": plot_daily_minv(daily),
        "hn": plot_hn_fragility(daily),
        "post": plot_post_trough(daily),
        "xvenue": plot_xvenue(xven),
        "liq": plot_liq(liq),
        "boot": plot_bootstrap(boot, kill),
        "vstat": plot_vstat_panel(panel),
        "rollup": plot_rollup(rollup),
    }
    print("figures", {k: (str(v) if v else None) for k, v in figs.items()})

    write_ch00(rollup)
    write_vstat(panel, daily)
    write_bootstrap(boot, kill)
    write_daily(daily)
    write_event(event)
    write_liq(liq)
    write_xvenue(xven)
    write_desk(rollup)
    write_trade_ideas()
    print("notebooks rebuilt (incl. trade_ideas.ipynb)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
