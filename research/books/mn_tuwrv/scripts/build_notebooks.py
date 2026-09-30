#!/usr/bin/env python3
"""Author + execute desk-quality mn_tuwrv notebooks from out/ artifacts.

Writes/updates:
  notebooks/desk_synthesis.ipynb
  chapters/*/ *.ipynb

Run from anywhere; paths resolve via absolute BOOK root.
"""

from __future__ import annotations

import json
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]  # research/


def md(s: str):
    return new_markdown_cell(s.strip() + "\n")


def code(s: str):
    return new_code_cell(s.strip() + "\n")


SETUP = r'''
from pathlib import Path
import json
import math
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import Image, display, Markdown

BOOK = Path('/home/dev/srv/ares-microstructure/research/books/mn_tuwrv')
OUT = BOOK / 'out'
FIGS = OUT / 'desk_synthesis' / 'figs'
sys.path.insert(0, str(BOOK.parents[2]))  # research/

def jload(rel):
    return json.loads((OUT / rel).read_text())

def show_fig(name, caption=None):
    p = FIGS / name
    if caption:
        display(Markdown(f'**{caption}** — `{p.relative_to(BOOK)}`'))
    if p.exists():
        display(Image(filename=str(p)))
    else:
        display(Markdown(f'*missing figure* `{p}` — run `scripts/build_notebook_figs.py`'))

bc = jload('blocker_close/blocker_close.json')
gc = jload('gap_close/gap_close.json')
mc = jload('monte_carlo/mc_summary.json')
p2 = jload('pass2/pass2_gates.json')
print('BOOK', BOOK)
print('figs', sorted(p.name for p in FIGS.glob('*.png')))
'''


def notebook_desk_synthesis() -> nbformat.NotebookNode:
    cells = [
        md(
            """
# Desk synthesis — Microstructure Noise / TSRV

Romero (2016) / ZMA05 TSRV on crypto perps (**HL · Deribit · Kraken**).

**Program status (Pass 2.7):** **0 Promote / 5 Hold / 4 Kill** · n_ok=**204** · n_mid=**122** · 34d ETH+BTC+SOL

Hard rule: sized claims only if a **Promote** clears the pre-registered gate. Holds are monitors / research debt — not soft-Promotes.

**SoT:** [`DESK_MEMO.md`](../DESK_MEMO.md) · [`CHAPTER_INDEX.md`](../CHAPTER_INDEX.md)  
**Artifacts:** `out/blocker_close/` · `out/gap_close/` · `out/monte_carlo/` · `out/desk_synthesis/figs/`
"""
        ),
        md("## 0. Setup — load Pass 2.6 artifacts (no multi-hour recompute)"),
        code(SETUP),
        md("## 1. Signal board"),
        code(
            """
show_fig('signal_board.png', 'Signal board')
show_fig('fig_gate_counts.png', 'Gate counts')

board = [
    ('cont.sparse_rv_only', 'Kill', 'MC first_adj RMSE ≈ 0.42× fourth'),
    ('cont.noise_dominates_1s_mid', 'Kill', 'calendar fifth/fourth med ≪ 1.5'),
    ('cont.noise_trade_clock_bounce', 'Kill', 'trade-clock med ≪ 1.5'),
    ('cont.noise_tick_bounce_clock', 'Kill', 'CI_lo ≰ 1.5'),
    ('cont.noise_mid_clock', 'Hold', bc['mid_clock']['gate']['why']),
    ('cont.tsrv_first_adj', 'Hold', bc['tsrv_oos']['gate']['why'][:160] + '…'),
    ('cont.noise_var_fifth', 'Hold', 'liquidity proxy only'),
    ('liq.noise_vs_spread', 'Hold', gc['spread_falsify']['gate']['why']),
    ('frag.xvenue_noise_concord', 'Hold', 'level concordance ≠ edge'),
]
df = pd.DataFrame(board, columns=['id', 'decision', 'evidence'])
display(df)
print('counts:', df.decision.value_counts().to_dict())
"""
        ),
        md(
            """
## 2. Pre-registered gates (do not move posts)

| ID | Promote only if |
|----|-----------------|
| `cont.noise_mid_clock` | bootstrap CI_lo of median fifth/fourth **> 1.5** |
| `cont.tsrv_first_adj` | fragile_rate=0 ∧ sparse−tsrv CI_lo>0 early **and** late ∧ n≥20 (**not** MC alone) |
| `liq.noise_vs_spread` | ρ>0 ∧ shuffle p<0.05 ∧ early∧late same sign ∧ n≥20 ∧ CI_lo>0 |
| `cont.sparse_rv_only` | already **Kill** on MC |
"""
        ),
        md("## 3. Monte Carlo — Kill sparse RV policy"),
        code(
            """
show_fig('fig_mc_rmse_ladder.png', 'Heston MC RMSE ladder')
est = mc['estimators']
rows = []
for k in ['fifth','fourth','third','second','first','first_adj']:
    e = est[k]
    rows.append({'estimator': k, 'bias': e['bias'], 'rmse': e['rmse'], 'n': e['n']})
display(pd.DataFrame(rows))
ratio = est['first_adj']['rmse'] / est['fourth']['rmse']
print(f"first_adj / fourth RMSE = {ratio:.3f}  -> Kill cont.sparse_rv_only (MC n={mc['n_sims']})")
print('pass2 gate:', p2['cont.sparse_rv_only'])
"""
        ),
        md(
            """
## 4. Mid-clock — denser TOB, still **Hold**

Pass 2.5 had mid CI ≈ [0.83, 8.17] (n=46). Pass 2.6 expands dense quoted TOB (HL + Deribit + Kraken spot L2) → **n=73**, CI **[1.17, 5.23]**. Point elevated (med≈2.63) but **CI_lo=1.17 < 1.5 gate**.
"""
        ),
        code(
            """
show_fig('fig_clock_medians.png', 'Clock medians ± CI95')
show_fig('fig_mid_venue_split.png', 'Venue split')
show_fig('fig_ratio_hist.png', 'Ratio histograms')

md_ci = bc['mid_clock']['mid_dense_ci']
print('dense mid CI:', md_ci)
print('gate:', bc['mid_clock']['gate'])
print('coverage:', json.dumps(bc['mid_clock']['mid_coverage_by_venue'], indent=2))
print('per_clock decisions:')
for k,v in bc['mid_clock']['per_clock'].items():
    print(f"  {v['decision']:7s}  {k:12s}  {v['why']}")
"""
        ),
        md(
            """
## 5. Tape-level TSRV vs sparse — **Hold** (MC Kill stands)

MC already Kills sparse-only policy. Tape OOS must clear CI_lo>0 on early∧late to Promote `cont.tsrv_first_adj`. It does **not**.
"""
        ),
        code(
            """
show_fig('fig_tsrv_oos.png', 'sparse − first_adj time-split')
ts = bc['tsrv_oos']
display(pd.DataFrame(ts['sparse_minus_tsrv']).T)
display(pd.DataFrame(ts['tsrv_over_sparse']).T)
print('fragile_rate', ts['fragile_rate'])
print('rolling 5d frac CI_lo>0:', ts['rolling_5d']['frac_ci_lo_pos'])
print('decision:', ts['gate'])
print('MC sparse policy:', ts['mc_sparse_policy'])
"""
        ),
        md("## 6. Noise vs spread — cross-venue ρ collapses"),
        code(
            """
show_fig('fig_noise_vs_spread.png', 'Pass 2.5/2.6 join')
sf = gc['spread_falsify']
print('ρ_spread:', sf['rho_spread'])
print('ρ_amihud:', sf['rho_amihud'])
print('shuffle_p', sf['shuffle_p'], 'block_shuffle_p', sf['block_shuffle_p'])
print('time_split:', sf['time_split'])
print('coverage_by_venue:', sf['coverage_by_venue'])
print('gate:', sf['gate'])
"""
        ),
        md(
            """
## 7. Kraken TOB inventory (honest)

| Stream | Status |
|--------|--------|
| Futures S3 MRCTCAP1 / public-md | trade/mark/index/funding/OI **only** — no BBO/L2 |
| Spot S3 public-md L2 | **Wired** via `spot|ETH/USD` / `spot|BTC/USD` |
| Futures live REST orderbook | ingest → `out/kraken_futures_tob/` |
| ClickHouse `kraken_md` | unreachable from this host |
"""
        ),
        code(
            """
show_fig('fig_tob_coverage.png', 'TOB coverage by venue')
meta = json.loads((OUT/'kraken_futures_tob/20260930/tob_000000.meta.json').read_text())
print('futures ingest sample meta:', meta)
# spot L2 sources in blocker panel
from collections import Counter
srcs = Counter(str((r.get('spread') or {}).get('source')) for r in bc['rows'] if r.get('ok'))
print('blocker spread sources:', dict(srcs))
print('kraken_days in panel:', bc['meta'].get('kraken_days'))
"""
        ),
        md(
            """
## 8. Desk takeaway

1. **Do not** run sparse-only RV for risk — MC Kill is decisive.  
2. **Do not** Promote mid-clock bounce domination yet — CI_lo still below 1.5; Deribit elevates, HL does not.  
3. **Do not** Promote tape TSRV first_adj on MC alone — OOS advantage CI includes 0.  
4. Noise↔spread is thesis-signed but **not** Promote-grade cross-venue.  
5. Kraken futures historical quoted TOB remains a data-plane gap; spot L2 + live REST ingest are the honest paths.

See chapter notebooks under `chapters/*/`.
"""
        ),
    ]
    nb = new_notebook(cells=cells, metadata={"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}})
    return nb


def notebook_ch00() -> nbformat.NotebookNode:
    return new_notebook(
        cells=[
            md(
                """
# Ch.00 Overview — Microstructure Noise / TSRV

Pass 2.6 signal board for desk readers. Empirics live in sibling chapter notebooks; this page is the map.
"""
            ),
            code(SETUP),
            md("## Signal board"),
            code(
                """
show_fig('signal_board.png')
show_fig('fig_gate_counts.png')
print((BOOK/'DESK_MEMO.md').read_text()[:1800])
"""
            ),
            md("## Pre-registered gates"),
            code(
                """
print(json.dumps(bc['meta'].get('gates'), indent=2))
print('blocker decisions:', json.dumps(bc['decisions'], indent=2)[:1500])
"""
            ),
        ],
        metadata={"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
    )


def notebook_monte_carlo() -> nbformat.NotebookNode:
    return new_notebook(
        cells=[
            md(
                """
# Monte Carlo — Heston + microstructure noise

ZMA05 ladder on simulated paths: fifth (all-sample RV) → fourth (sparse) → … → first_adj (TSRV).

**Decision:** `cont.sparse_rv_only` = **Kill** — first_adj RMSE ≈ 0.42× fourth (n=500).
"""
            ),
            code(SETUP),
            code(
                """
show_fig('fig_mc_rmse_ladder.png', 'RMSE ladder')
est = mc['estimators']
df = pd.DataFrame(est).T
display(df[['bias','var','rmse','n']])
print('first_adj/fourth RMSE', est['first_adj']['rmse']/est['fourth']['rmse'])
print('heston params', mc['heston'])
print('EXP_REPORT:\\n', (BOOK/'chapters/monte_carlo/EXP_REPORT.md').read_text())
"""
            ),
            md(
                """
### Desk read

MC Kills **sparse-only** as a policy for this noise regime. That Kill is **independent** of tape OOS — tape may still Hold `cont.tsrv_first_adj` if the advantage is not significant out of sample.
"""
            ),
        ],
        metadata={"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
    )


def notebook_estimators() -> nbformat.NotebookNode:
    return new_notebook(
        cells=[
            md(
                """
# Estimators / clocks — Pass 2.6

Four sampling clocks on the same venue-days: **calendar**, **trade**, **tick_bounce**, **mid**.

Pre-registered Promote for bounce domination: median fifth/fourth bootstrap **CI_lo > 1.5**.
"""
            ),
            code(SETUP),
            code(
                """
show_fig('fig_clock_medians.png')
show_fig('fig_mid_venue_split.png')
show_fig('fig_ratio_hist.png')
show_fig('fig_tsrv_oos.png')

rows = [r for r in bc['rows'] if r.get('ok')]
summary = []
for clock, key in [('calendar','fifth_over_fourth_cal'),('trade','fifth_over_fourth_tc'),
                   ('tick_bounce','fifth_over_fourth_bounce'),('mid','fifth_over_fourth_mid')]:
    vals = np.asarray([r[key] for r in rows if np.isfinite(r.get(key, np.nan))], dtype=float)
    summary.append({
        'clock': clock, 'n': int(vals.size), 'median': float(np.median(vals)) if vals.size else np.nan,
        'p10': float(np.quantile(vals,0.1)) if vals.size else np.nan,
        'p90': float(np.quantile(vals,0.9)) if vals.size else np.nan,
        'decision': bc['mid_clock']['per_clock'][clock]['decision'],
    })
display(pd.DataFrame(summary))
print('mid dense CI', bc['mid_clock']['mid_dense_ci'])
print('tsrv OOS gate', bc['tsrv_oos']['gate']['decision'], bc['tsrv_oos']['gate']['why'][:240])
print('\\n', (BOOK/'chapters/estimators/EXP_REPORT.md').read_text())
"""
            ),
            md(
                """
### Narrative

- Calendar / trade / tick_bounce: **Kill** — ratios sit near or below 1; no bounce domination.  
- Mid-clock: **Hold** — median ~2.6 looks interesting, but CI_lo=1.17 fails the pre-registered 1.5 gate; Deribit pulls the median up, HL does not.  
- `cont.tsrv_first_adj`: **Hold** — tape sparse−tsrv advantage CI includes 0 on early and late splits.
"""
            ),
        ],
        metadata={"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
    )


def notebook_noise_proxy() -> nbformat.NotebookNode:
    return new_notebook(
        cells=[
            md(
                """
# Noise proxy — $\\widehat{E}\\epsilon^2$

Proxy from fifth-best (all-sample) RV structure. Empirics: Pass 1 ETH panel + Pass 2.6 blocker noise_std joins.
"""
            ),
            code(SETUP),
            code(
                """
panel = jload('tsrv_panel/panel_eth.json')
rows = [r for r in panel['rows'] if r.get('ok')]
print('panel meta', panel['meta'], 'n_ok', len(rows))
if rows:
    df = pd.DataFrame([
        {
            'day': r.get('day'), 'venue': r.get('venue'),
            'noise_std': r.get('noise_std') or r.get('calendar',{}).get('noise_std'),
            'first_adj': r.get('first_adj') or r.get('calendar',{}).get('first_adj'),
            'fifth_over_fourth': r.get('fifth_over_fourth') or r.get('calendar',{}).get('fifth_over_fourth'),
        }
        for r in rows
    ])
    display(df)
    display(df.select_dtypes(include=[np.number]).describe())

# blocker noise_std distribution if present via calendar
brows = [r for r in bc['rows'] if r.get('ok')]
ns = []
for r in brows:
    cal = r.get('calendar') or {}
    if np.isfinite(cal.get('noise_std', np.nan)):
        ns.append({'venue': r['venue'], 'day': r['day'], 'symbol': r['symbol'], 'noise_std': float(cal['noise_std'])})
bdf = pd.DataFrame(ns)
print('blocker noise_std n', len(bdf))
if len(bdf):
    display(bdf.groupby('venue')['noise_std'].describe())
    fig, ax = plt.subplots(figsize=(6.5,3.6))
    for v, g in bdf.groupby('venue'):
        ax.hist(g['noise_std'].astype(float), bins=14, alpha=0.55, label=v)
    ax.set_xlabel('noise_std'); ax.legend(); ax.set_title('Pass 2.6 noise_std by venue')
    plt.show()
print((BOOK/'chapters/noise_proxy/EXP_REPORT.md').read_text()[:1200])
"""
            ),
        ],
        metadata={"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
    )


def notebook_market_noise() -> nbformat.NotebookNode:
    return new_notebook(
        cells=[
            md(
                """
# Market noise — multi-week falsifiers

Joins noise_std to quoted/proxy spreads across venues. Artifact spine: `out/gap_close/` + denser mid-clock in `out/blocker_close/`.
"""
            ),
            code(SETUP),
            code(
                """
show_fig('fig_noise_vs_spread.png')
show_fig('fig_tob_coverage.png')
show_fig('fig_clock_medians.png')

mn = jload('market_noise/market_noise.json')
print('market_noise gate', mn.get('gate'))
print('corr', mn.get('corr'))

sf = gc['spread_falsify']
print('\\n=== liq.noise_vs_spread ===')
print('rho', sf['rho_spread'])
print('shuffle_p', sf['shuffle_p'], 'block_p', sf['block_shuffle_p'])
print('time_split early/late', sf['time_split']['early'], sf['time_split']['late'])
print('decision', sf['gate'])

print('\\n=== mid-clock blocker ===')
print(bc['mid_clock']['gate'])
print('coverage', bc['mid_clock']['mid_coverage_by_venue'])
print('\\n', (BOOK/'chapters/market_noise/EXP_REPORT.md').read_text())
"""
            ),
            md(
                """
### Kraken TOB status

- Spot L2 from S3 is **quoted** (not invented).  
- Futures historical L2 **absent** in sealed archives — proxies only for history; live REST ingest for forward TOB.  
- Do not Promote liquidity claims that depend on futures quoted spreads until the md plane captures book.
"""
            ),
        ],
        metadata={"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
    )


def notebook_xvenue() -> nbformat.NotebookNode:
    return new_notebook(
        cells=[
            md(
                """
# X-venue noise concordance

`frag.xvenue_noise_concord` — **Hold**. Same-day noise levels can move together without implying a tradable edge or FEI/Epps claim.
"""
            ),
            code(SETUP),
            code(
                """
print('pass2 xvenue gate:', p2.get('frag.xvenue_noise_concord'))
# same-day noise concordance from blocker panel
rows = [r for r in bc['rows'] if r.get('ok')]
# pivot noise_std by day×symbol if calendar present
recs = []
for r in rows:
    ns = (r.get('calendar') or {}).get('noise_std', np.nan)
    if np.isfinite(ns):
        recs.append({'day': r['day'], 'symbol': r['symbol'], 'venue': r['venue'], 'noise_std': ns})
df = pd.DataFrame(recs)
display(df.head(20))
# pairwise day concordance: relative range across venues
conc = []
for (day, sym), g in df.groupby(['day','symbol']):
    if g['venue'].nunique() < 2:
        continue
    vals = g['noise_std'].to_numpy()
    rel = (vals.max() - vals.min()) / max(np.median(vals), 1e-12)
    conc.append({'day': day, 'symbol': sym, 'n_venues': int(g['venue'].nunique()), 'rel_range': float(rel),
                 **{f"ns_{r.venue}": float(r.noise_std) for r in g.itertuples()}})
cdf = pd.DataFrame(conc)
display(cdf)
if len(cdf):
    print('frac rel_range < 0.35:', float((cdf['rel_range'] < 0.35).mean()))
    fig, ax = plt.subplots(figsize=(6.2,3.4))
    ax.hist(cdf['rel_range'], bins=12, color='#4a7ab5', edgecolor='white')
    ax.axvline(0.35, color='#b33a3a', ls='--', label='pass2 close band 35%')
    ax.set_xlabel('cross-venue relative range of noise_std'); ax.legend()
    ax.set_title('X-venue noise concordance (descriptive)')
    plt.show()
print((BOOK/'chapters/xvenue_noise/EXP_REPORT.md').read_text()[:1500])
"""
            ),
        ],
        metadata={"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
    )


def write_and_execute(path: Path, nb: nbformat.NotebookNode) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(nb, path)
    print(f"wrote {path}")
    client = NotebookClient(
        nb,
        timeout=180,
        kernel_name="python3",
        resources={"metadata": {"path": str(BOOK)}},
    )
    client.execute()
    nbformat.write(nb, path)
    n_out = sum(1 for c in nb.cells if c.get("outputs"))
    print(f"executed {path.name}: cells={len(nb.cells)} with_output={n_out}")


def main() -> None:
    # ensure figs exist
    import subprocess

    subprocess.check_call([sys_executable(), str(BOOK / "scripts" / "build_notebook_figs.py")])
    targets = [
        (BOOK / "notebooks" / "desk_synthesis.ipynb", notebook_desk_synthesis()),
        (BOOK / "chapters" / "ch00_overview" / "ch00_overview.ipynb", notebook_ch00()),
        (BOOK / "chapters" / "monte_carlo" / "monte_carlo.ipynb", notebook_monte_carlo()),
        (BOOK / "chapters" / "estimators" / "estimators.ipynb", notebook_estimators()),
        (BOOK / "chapters" / "noise_proxy" / "noise_proxy.ipynb", notebook_noise_proxy()),
        (BOOK / "chapters" / "market_noise" / "market_noise.ipynb", notebook_market_noise()),
        (BOOK / "chapters" / "xvenue_noise" / "xvenue_noise.ipynb", notebook_xvenue()),
    ]
    for path, nb in targets:
        write_and_execute(path, nb)


def sys_executable() -> str:
    import sys

    return sys.executable


if __name__ == "__main__":
    main()
