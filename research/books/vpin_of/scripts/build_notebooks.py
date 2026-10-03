#!/usr/bin/env python3
"""Author + execute vpin_of desk/chapter notebooks from out/ JSON."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

BOOK = Path(__file__).resolve().parents[1]
META = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}
}


def md(s: str):
    return new_markdown_cell(s.strip() + "\n")


def code(s: str):
    return new_code_cell(s.strip() + "\n")


SETUP = r'''
from pathlib import Path
import json
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import Image, display, Markdown

BOOK = Path(os.environ.get('ARES_MICROSTRUCTURE') or (Path.home() / 'srv' / 'ares-microstructure')) / 'research' / 'books' / 'vpin_of'
OUT = BOOK / 'out'
FIGS = OUT / 'desk_synthesis' / 'figs'

def jload(rel):
    p = OUT / rel
    return json.loads(p.read_text()) if p.is_file() else {}

def jlines(rel):
    p = OUT / rel
    if not p.is_file():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]

def show_fig(name, caption=None):
    p = FIGS / name
    if caption:
        display(Markdown(f'**{caption}** — `{p.relative_to(BOOK)}`'))
    if p.exists():
        display(Image(filename=str(p)))
    else:
        display(Markdown(f'*missing* `{p}` — run `scripts/build_notebook_figs.py`'))

dec = jload('pass4/decisions_pass4.json') or jload('pass3/decisions_pass3.json') or jload('pass2/decisions_pass2.json') or jload('vpin_panel/decisions.json')
dec_promote = jload('vpin_panel/decisions_panel_promote.json')
rows = jlines('vpin_panel/rows.jsonl')
panel_ext = jload('pass2/panel_hl_db_extended.json')
ok_rows = panel_ext if isinstance(panel_ext, list) and panel_ext else [r for r in rows if r.get('ok')]
p4 = jload('pass4/pass4_summary.json')
p3 = jload('pass3/pass3_summary.json')
p2 = jload('pass2/pass2_summary.json')
tag = 'pass4' if p4 else ('pass3' if p3 else ('pass2' if p2 else 'pass1'))
print(tag, 'n_ok', dec.get('n_ok'), 'promote n_ok', dec_promote.get('n_ok'), 'counts', dec.get('decision_counts'), 'book', dec.get('book_status'))
'''


def desk_synthesis() -> nbformat.NotebookNode:
    cells = [
        md(
            """
# VPIN / order flow — desk synthesis

**Pass 1 complete:** warehouse trade tape — **panel_exploratory** n_ok=226 (HL+DB+Kraken, complete UTC); **panel_promote** n_ok=139 (HL+DB only). Kraken: real tape, Hold arm.

**Pass 4 (FINAL):** merged board in `out/pass4/decisions_pass4.json` — SOL DB+Kr arm, fresh xvenue calibration, promote-slice markout holdout, intraday toxicity events.

**SoT:** [`DESK_MEMO.md`](../DESK_MEMO.md) · [`CHAPTER_INDEX.md`](../CHAPTER_INDEX.md) · [`TRADING_APPLICATIONS.md`](../TRADING_APPLICATIONS.md) · `decisions_pass4.json` (latest) · `decisions_panel_promote.json`
"""
        ),
        md("## 0. Setup"),
        code(SETUP),
        md("## 1. Signal board"),
        code(
            """
show_fig('signal_board.png', 'Pass 1 decision board')
if dec.get('decision_table'):
    display(pd.DataFrame(dec['decision_table']))
"""
        ),
        md("## 2. Panel coverage"),
        code(
            """
if ok_rows:
    d = pd.DataFrame(ok_rows)
    display(d.groupby(['venue','symbol']).agg(
        n_ok=('day','count'), med_vpin=('mean_vpin','median'),
        med_buckets=('n_buckets','median'), med_cov=('coverage','median')))
show_fig('fig_vpin_by_day.png', 'Day mean VPIN')
"""
        ),
        md("## 3. Bucket calibration"),
        code(
            """
cal = jload('vpin_panel/bucket_calibration.json')
if cal.get('grid'):
    display(pd.DataFrame(cal['grid']))
show_fig('fig_bucket_calibration.png', 'Bucket scale grid (smoke day)')
display(Markdown(cal.get('desk_choice','')))
"""
        ),
        md("## 4. Falsifiers + cross-venue"),
        code(
            """
show_fig('fig_falsifier_rates.png', 'Side-shuffle + time-split')
show_fig('fig_xvenue_scatter.png', 'HL vs Deribit paired days')
display(dec.get('falsifiers', {}))
"""
        ),
        md("## 5. PIN compare (proxy only)"),
        code(
            """
show_fig('fig_pin_proxy_spearman.png', 'Day-level Spearman vs pin_proxy')
display(pd.DataFrame(jload('vpin_panel/pin_compare.json')))
"""
        ),
        md("## 6. Pass 2 — markout + toxicity (HL+Deribit TOB)"),
        code(
            """
mo = jload('pass2/markout.json')
tox = jload('pass2/toxicity.json')
if p2:
    display(Markdown(
        f"**Pass 2 board** (`decisions_pass2.json`): {dec.get('decision_counts')} — "
        f"markout **{p2.get('markout')}**, toxicity **{p2.get('toxicity')}**, xvenue **{p2.get('xvenue')}**"
    ))
if mo.get('n_days_ok'):
    ok = [r for r in mo.get('day_rows', []) if r.get('ok')]
    rhos = pd.Series([r['ic_spearman_vpin_vs_mo30']['rho'] for r in ok])
    display(Markdown(
        f"Ex-ante VPIN vs 30s TOB markout: n_ok days={mo['n_days_ok']}, "
        f"median IC={mo.get('median_ic_by_day'):.4f}, early={mo.get('median_ic_early'):.4f}, late={mo.get('median_ic_late'):.4f}"
    ))
    fig, ax = plt.subplots(figsize=(7,3))
    ax.hist(rhos.dropna(), bins=12, color='#3d5a80', edgecolor='white')
    ax.axvline(0, color='#888', lw=1)
    ax.set_xlabel('Spearman IC (VPIN vs mo30 bps)')
    ax.set_title('Pass 2 markout IC by day')
    plt.tight_layout()
    plt.show()
if tox.get('n_days'):
    display(Markdown(
        f"Toxicity join n={tox['n_days']}: ρ(vpin,spread)={tox['spearman_vpin_spread']['rho']:.3f} "
        f"CI=[{tox['spearman_vpin_spread']['lo']:.3f},{tox['spearman_vpin_spread']['hi']:.3f}] — "
        f"**Hold** (high VPIN ↔ tighter spread on HL+DB sample; monitor-only flag)"
    ))
"""
        ),
        md("## 7. Pass 3 — Hold blocker retest"),
        code(
            """
p3 = jload('pass3/pass3_summary.json')
if p3:
    display(Markdown(
        f"**Pass 3** (`decisions_pass3.json`): {dec.get('decision_counts')} — "
        f"HL SOL days w/trades={jload('pass3/hl_sol_probe.json').get('n_days_with_trades')}, "
        f"markout **{p3.get('markout')}**, xvenue **{p3.get('xvenue')}**, "
        f"toxicity **{p3.get('toxicity')}**, bucket **{p3.get('bucket_robust')}**"
    ))
mo3 = jload('pass3/markout.json')
if mo3.get('n_days_ok'):
    display(Markdown(
        f"Pass 3 markout (dense L2, 120 q/min): n_ok={mo3['n_days_ok']} "
        f"medIC={mo3.get('median_ic_by_day')} rankIC={mo3.get('median_rank_ic_30s')} "
        f"early={mo3.get('median_ic_early')} late={mo3.get('median_ic_late')} "
        f"gate={mo3.get('decision')}"
    ))
xv3 = jload('pass3/xvenue_harmonized.json')
if xv3.get('methods'):
    t50 = xv3['methods'].get('target_50_buckets', {}).get('spearman', {})
    display(Markdown(
        f"xvenue target50: ρ={t50.get('rho')} CI=[{t50.get('lo')},{t50.get('hi')}] "
        f"rank={ (xv3.get('rank_day_concordance') or {}).get('rho') } "
        f"decision={xv3.get('decision')}"
    ))
else:
    display(Markdown('Run `scripts/exp_pass3.py` for Pass 3 artifacts.'))
"""
        ),
        md("## 8. Pass 4 — FINAL close-out"),
        code(
            """
p4 = jload('pass4/pass4_summary.json')
dec4 = jload('pass4/decisions_pass4.json') or dec
if p4:
    display(Markdown(
        f"**Pass 4 FINAL** (`decisions_pass4.json`): {dec4.get('decision_counts')} — "
        f"book_status={p4.get('book_status')} promote_slice n={p4.get('n_promote_slice')} "
        f"markout **{p4.get('markout')}** xvenue **{p4.get('xvenue_fresh')}** "
        f"toxicity **{p4.get('toxicity_intraday')}** HL post-08-28 trades={p4.get('hl_sol_post_trades')}"
    ))
mo4 = jload('pass4/markout.json')
if mo4.get('n_days_ok'):
    display(Markdown(
        f"Promote-slice markout: n_ok={mo4['n_days_ok']} medIC60={mo4.get('median_ic_60s')} "
        f"rank60={mo4.get('median_rank_ic_60s')} holdout={mo4.get('venue_holdout')} gate={mo4.get('decision')}"
    ))
sol_arm = jload('pass4/sol_db_kraken_panel.json')
if sol_arm:
    display(Markdown(f"SOL formal arm: {sol_arm.get('formal_arm')}"))
else:
    display(Markdown('Run `scripts/exp_pass4.py` for Pass 4 artifacts.'))
"""
        ),
    ]
    return new_notebook(cells=cells, metadata=META)


def vpin_construction_nb() -> nbformat.NotebookNode:
    cells = [
        md("# VPIN construction — Pass 1"),
        code(SETUP),
        code(
            """
day = jload('vpin_day/hyperliquid_ETH_2026-09-30.json')
vs = day.get('vpin_summary') or day
display(Markdown(
    f"**HL ETH 2026-09-30** complete={day.get('complete')} "
    f"n_trades={day.get('n_trades')} bucket_vol={day.get('bucket_volume')} "
    f"mean_vpin={vs.get('mean_vpin')} n_buckets={vs.get('n_buckets')}"
))
cal = jload('vpin_panel/bucket_calibration.json')
display(pd.DataFrame(cal.get('grid', [])))
show_fig('fig_bucket_calibration.png', 'Calibration grid')
"""
        ),
    ]
    return new_notebook(cells=cells, metadata=META)


def pin_compare_nb() -> nbformat.NotebookNode:
    cells = [
        md("# PIN vs VPIN — Pass 1 compare"),
        code(SETUP),
        code(
            """
blocks = jload('vpin_panel/pin_compare.json')
if isinstance(blocks, list):
    display(pd.DataFrame(blocks))
show_fig('fig_pin_proxy_spearman.png', 'Proxy Spearman by venue×symbol')
display(Markdown(
    '**Hold:** EHO PIN MLE returned 0 usable days after intensity filters; '
    'compare is diagnostic (pooled VPIN + day pin_proxy Spearman), not level-identified PIN.'
))
"""
        ),
    ]
    return new_notebook(cells=cells, metadata=META)


def cross_venue_nb() -> nbformat.NotebookNode:
    cells = [
        md("# Cross-venue VPIN concordance"),
        code(SETUP),
        code(
            """
show_fig('fig_xvenue_scatter.png', 'HL↔DB scatter')
xv = (dec.get('falsifiers') or {}).get('xvenue_spearman', {})
display(Markdown(f"Gate frag.xvenue_vpin_concord: **Hold** — ρ={xv.get('rho')} CI=[{xv.get('lo')},{xv.get('hi')}] n={xv.get('n')}"))
"""
        ),
    ]
    return new_notebook(cells=cells, metadata=META)


def robustness_nb() -> nbformat.NotebookNode:
    cells = [
        md("# Robustness — bucket scale grid (smoke day)"),
        code(SETUP),
        code(
            """
cal = jload('vpin_panel/bucket_calibration.json')
g = pd.DataFrame(cal.get('grid', []))
display(g)
fig, ax = plt.subplots(figsize=(8,4))
if not g.empty and 'n_buckets' in g.columns:
    ax.scatter(g['n_buckets'], g['mean_vpin'], c='#3d5a80', s=60)
    for _, r in g.iterrows():
        ax.annotate(str(r.get('method','')), (r['n_buckets'], r['mean_vpin']), fontsize=7)
ax.set_xlabel('n_buckets')
ax.set_ylabel('mean_vpin')
ax.set_title('Scale vs level (Pass 1 diagnostic — Promote stays median×50)')
plt.tight_layout()
plt.show()
display(Markdown(cal.get('desk_choice','')))
"""
        ),
    ]
    return new_notebook(cells=cells, metadata=META)


def toxicity_events_nb() -> nbformat.NotebookNode:
    cells = [
        md("# Toxicity events — Pass 2 (TOB spread/vol join)"),
        code(SETUP),
        code(
            """
tox = jload('pass2/toxicity.json')
if tox:
    display(Markdown(f"**{tox.get('decision')}** — n_days={tox.get('n_days')} ρ_vpin,spread={((tox.get('spearman_vpin_spread') or {}).get('rho'))}"))
    display(pd.DataFrame(tox.get('sample_top_days', [])))
else:
    d = pd.DataFrame(ok_rows)
    q90 = d['mean_vpin'].quantile(0.9) if not d.empty else float('nan')
    display(Markdown(f'Top decile tape preview (mean_vpin ≥ {q90:.3f}) — run `scripts/exp_pass2.py` for TOB join'))
"""
        ),
    ]
    return new_notebook(cells=cells, metadata=META)


def predictiveness_nb() -> nbformat.NotebookNode:
    cells = [
        md("# Predictiveness — Pass 2 markout"),
        code(SETUP),
        code(
            """
mo = jload('pass2/markout.json')
if mo:
    display(Markdown(
        f"**{mo.get('decision')}** — n_ok days={mo.get('n_days_ok')} "
        f"median IC={mo.get('median_ic_by_day')} early={mo.get('median_ic_early')} late={mo.get('median_ic_late')}"
    ))
    display(pd.DataFrame(mo.get('day_rows', [])).head(20))
else:
    display(Markdown('Run `scripts/exp_pass2.py` for ex-ante VPIN vs 30s TOB markout.'))
display(pd.DataFrame(dec.get('decision_table', []))[['id','decision','evidence']])
"""
        ),
    ]
    return new_notebook(cells=cells, metadata=META)


def ch00_nb() -> nbformat.NotebookNode:
    cells = [
        md("# VPIN book overview"),
        code(SETUP),
        code(
            """
show_fig('signal_board.png', 'Program board')
display(Markdown(dec.get('data_provenance','')))
"""
        ),
    ]
    return new_notebook(cells=cells, metadata=META)


def execute(nb: nbformat.NotebookNode, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(nb, path)
    client = NotebookClient(nb, timeout=600, kernel_name="python3")
    client.execute()
    nbformat.write(nb, path)


def main() -> None:
    fig_script = BOOK / "scripts" / "build_notebook_figs.py"
    subprocess.run([sys.executable, str(fig_script)], check=True, cwd=str(BOOK))

    targets = [
        (desk_synthesis(), BOOK / "notebooks" / "desk_synthesis.ipynb"),
        (ch00_nb(), BOOK / "chapters" / "ch00_overview" / "ch00_overview.ipynb"),
        (vpin_construction_nb(), BOOK / "chapters" / "vpin_construction" / "vpin_construction.ipynb"),
        (pin_compare_nb(), BOOK / "chapters" / "pin_compare" / "pin_compare.ipynb"),
        (cross_venue_nb(), BOOK / "chapters" / "cross_venue" / "cross_venue.ipynb"),
        (robustness_nb(), BOOK / "chapters" / "robustness" / "robustness.ipynb"),
        (toxicity_events_nb(), BOOK / "chapters" / "toxicity_events" / "toxicity_events.ipynb"),
        (predictiveness_nb(), BOOK / "chapters" / "predictiveness" / "predictiveness.ipynb"),
    ]
    for nb, path in targets:
        print("execute", path.relative_to(BOOK))
        execute(nb, path)
    print("done", len(targets), "notebooks")


if __name__ == "__main__":
    main()
