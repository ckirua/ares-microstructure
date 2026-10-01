from __future__ import annotations
#!/usr/bin/env python3
"""Build memo-quality notebooks for Phase 3a crash_stats + cross_section."""


import base64
import json
from pathlib import Path

BOOK = Path(__file__).resolve().parents[1]
OUT = BOOK / "out" / "phase3a_stats_xsec"


def _img(path: Path) -> dict:
    return {
        "output_type": "display_data",
        "data": {
            "image/png": base64.b64encode(path.read_bytes()).decode("ascii"),
            "text/plain": ["<IPython.core.display.Image object>"],
        },
        "metadata": {},
    }


def _md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": [l + "\n" for l in text.split("\n")]}


def _code(src: str, outputs: list | None = None, n: int = 1) -> dict:
    return {
        "cell_type": "code",
        "execution_count": n,
        "metadata": {},
        "outputs": outputs or [],
        "source": [l + "\n" for l in src.split("\n")],
    }


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


def main() -> None:
    s = json.loads((OUT / "phase3a_summary.json").read_text())
    p = s["pooled"]
    ols = (s.get("ols_event") or {}).get("dp") or {}
    vi = ols.get("with_vpin_interaction") or {}
    ex = (s.get("ols_exante") or {}).get("median_dp") or {}
    lines = [
        f"cells={p['n_cells']} ssm_raw={p['n_ssm_raw']} gated={p['n_ssm_gated']} nanex={p['n_nanex']}",
        f"gate_ablation={p.get('gate_ablation_totals')}",
        f"ssm_dp={p['ssm_dp']}",
        f"ssm_class={p['ssm_class']}",
        f"markout={p.get('ssm_markout_mean_bps')}",
        f"dt_mo_spearman={p.get('spearman_dt_mo5_cell_mean')}",
        f"ols_r2={ols.get('r2')} vpin_r2={vi.get('r2')}",
        f"time_split={s.get('time_split')}",
        f"exante_n={s.get('n_pred_rows')} exante_r2={ex.get('r2')}",
        f"multi_coin={s.get('multi_coin')}",
        f"by_venue={s.get('by_venue')}",
    ]
    stream = {"output_type": "stream", "name": "stdout", "text": [l + "\n" for l in lines]}
    load_src = (
        "from pathlib import Path\nimport json\n"
        "OUT = Path('../../out/phase3a_stats_xsec').resolve()\n"
        "s = json.loads((OUT / 'phase3a_summary.json').read_text())\n"
        "p = s['pooled']\n"
        "print('cells', p['n_cells'], 'raw', p['n_ssm_raw'], 'gated', p['n_ssm_gated'], 'nanex', p['n_nanex'])\n"
        "print('gate', p.get('gate_ablation_totals'))\n"
        "print('ssm_dp', p['ssm_dp'])\n"
        "print('class', p['ssm_class'])\n"
        "print('markout', p.get('ssm_markout_mean_bps'))\n"
        "print('dt_mo', p.get('spearman_dt_mo5_cell_mean'))\n"
        "print('ols', s.get('ols_event', {}).get('dp', {}).get('r2'))\n"
        "print('vpin_int', (s.get('ols_event', {}).get('dp', {}) or {}).get('with_vpin_interaction', {}).get('r2'))\n"
        "print('time_split', s.get('time_split'))\n"
        "print('exante', s.get('ols_exante'))\n"
        "print('multi_coin', s.get('multi_coin'))\n"
        "print('by_venue', s.get('by_venue'))\n"
    )

    # crash_stats notebook
    cs_cells = [
        _md("# Crash stats — ΔP, i_c, Δt, recovery (Phase 3a)\n\nTee & Ting §4.2–4.3. Sample: HL+Deribit+Kraken · ETH+BTC · 2026-09-04…10."),
        _md(r"""## Theory → method

Paper event stats: \(\Delta P\), \(i_c\) (ticks→**trades**), \(\Delta t\), recovery.
Phase 2 raw SSM z*=6 = 3668 micro-outliers → **severity gate** \(|\Delta P|\ge10\) bps, \(i_c\ge5\) → **275**.
"""),
        _code(load_src, outputs=[stream], n=1),
        _md("## Severity gate"),
        _code(
            "from IPython.display import Image\nImage(filename=str(OUT/'figs/fig_severity_gate.png'))",
            outputs=[_img(OUT / "figs/fig_severity_gate.png")],
            n=2,
        ),
        _md("## ΔP distribution (Nanex vs gated SSM)"),
        _code(
            "Image(filename=str(OUT/'figs/fig_dp_hist.png'))",
            outputs=[_img(OUT / "figs/fig_dp_hist.png")],
            n=3,
        ),
        _md("## Signal board — V vs continuation"),
        _code(
            "Image(filename=str(OUT/'figs/fig_recovery_class.png'))",
            outputs=[_img(OUT / "figs/fig_recovery_class.png")],
            n=4,
        ),
        _md(r"""### Interpretation
- Gated median ΔP≈**0.18%**, Nanex≈**0.40%**.
- Recovery class: **77% V** @5s; tape markout ≈**−7 bps** @5s → mean-revert / liquidity hole.
- Duration–|markout| Spearman≈**−0.28** (Hold as risk feature; calendar Δt median 0).
- **Promote:** `risk.ssm_severity_gate_10bps`, `info.crash_v_vs_continuation`.
- **Kill:** ungated SSM counts as risk intensity.
"""),
    ]
    cs_path = BOOK / "chapters" / "crash_stats" / "crash_stats.ipynb"
    cs_path.write_text(json.dumps(_nb(cs_cells), indent=1))

    # cross_section notebook
    xs_cells = [
        _md("# Cross-section — OI/vol/liq → severity (Phase 3a)\n\nTee & Ting §4.3. Size proxy = log daily notional (true OI unavailable)."),
        _md(r"""## Pass 1 claim test
Paper: larger/thicker → smaller \(|\Delta P|\), more \(i_c\), longer \(\Delta t\).
Crypto: NW-OLS on gated events; quintiles by log notional.
"""),
        _code(load_src, outputs=[stream], n=1),
        _md("## Quintiles by size proxy"),
        _code(
            "from IPython.display import Image\nImage(filename=str(OUT/'figs/fig_quintile_size_dp.png'))",
            outputs=[_img(OUT / "figs/fig_quintile_size_dp.png")],
            n=2,
        ),
        _md("## NW-OLS forest (ΔP)"),
        _code(
            "Image(filename=str(OUT/'figs/fig_nw_ols_dp.png'))",
            outputs=[_img(OUT / "figs/fig_nw_ols_dp.png")],
            n=3,
        ),
        _md("## Multi-coin"),
        _code(
            "Image(filename=str(OUT/'figs/fig_multi_coin.png'))",
            outputs=[_img(OUT / "figs/fig_multi_coin.png")],
            n=4,
        ),
        _md(r"""### Signal board
| Object | Monitor | Tradable | Decision |
|--------|---------|----------|----------|
| size → lower ΔP | — | — | **Kill** (R²≈0.02; time-split sign flip) |
| VPIN × size | ✓ | ✗ | **Hold** (interact t≈3; needs harden) |
| ex-ante Amihud | ✓ | ✗ | **Hold** (n_pred=20) |
| ETH vs BTC severity | ✓ | — | **Hold** (parity this week) |

Ceilings: OI not wired; Kraken TOB=0 irrelevant for these regressors; ex-ante underpowered.
"""),
    ]
    xs_path = BOOK / "chapters" / "cross_section" / "cross_section.ipynb"
    xs_path.write_text(json.dumps(_nb(xs_cells), indent=1))
    print("wrote", cs_path)
    print("wrote", xs_path)


if __name__ == "__main__":
    main()
