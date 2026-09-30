#!/usr/bin/env python3
"""Build memo-quality notebooks for Phase 2 packages from phase2_summary + figs."""

from __future__ import annotations

import base64
import json
from pathlib import Path

BOOK = Path(__file__).resolve().parents[1]
OUT = BOOK / "out" / "phase2_baselines_ssm"


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
    s = json.loads((OUT / "phase2_summary.json").read_text())
    ct = s["counts_total"]
    byv = s["counts_by_venue"]
    ov = s["overlap_pooled"]["nanex_vs_ssm"]
    lines = [
        f"counts_total {ct}",
        f"by_venue {byv}",
        f"overlap_nanex_ssm {ov}",
        f"sigma_stress {s['sigma_stress_pooled']}",
        f"zstar_z6 {[r for r in s['zstar_pooled'] if r['z_star']==6]}",
        f"tox {s['tox_summary']}",
        f"time_split {s['time_split_pooled']}",
        f"hour_peak_utc {s.get('hour_peak_utc')}",
    ]
    stream = {"output_type": "stream", "name": "stdout", "text": [l + "\n" for l in lines]}

    common_load = (
        "from pathlib import Path\nimport json\n"
        "OUT = Path('../../out/phase2_baselines_ssm').resolve()\n"
        "s = json.loads((OUT / 'phase2_summary.json').read_text())\n"
        "print('counts_total', s['counts_total'])\n"
        "print('by_venue', s['counts_by_venue'])\n"
        "print('overlap_nanex_ssm', s['overlap_pooled']['nanex_vs_ssm'])\n"
        "print('sigma_stress', s['sigma_stress_pooled'])\n"
        "print('zstar_z6', [r for r in s['zstar_pooled'] if r['z_star']==6])\n"
        "print('tox', s['tox_summary'])\n"
        "print('time_split', s['time_split_pooled'])\n"
        "print('hour_peak_utc', s.get('hour_peak_utc'))\n"
    )

    packages = {
        "ch00_overview": {
            "title": "# Ch.00 — Overview: crash defs → SSM (Phase 2)\n\nTee & Ting (2019). Vertical slice HL+Deribit+Kraken ETH/BTC.",
            "theory": r"""## Theory map

Five paper defs → crypto desk:

1. **Nanex** — uni-dir tape burst (≥10 trades, ≤1.5s, |ΔP|≥0.8% paper).
2. **Outside-TOB** — print beyond asof bid/ask.
3. **Residual EPM** — model residual extremes (→ SSM innovation).
4. **Lee–Mykland** — local-vol jumps (competing).
5. **V-shape** — large move + recovery (Dugast–Foucault).

**SSM core:** \(z_i=\log S_i\), latent \(x_i\), crash when standardized innovation \(|\nu_i|/\sqrt{S_i}\ge z^\*\).
""",
            "figs": [
                ("Nanex vs SSM by venue", "figs/fig_nanex_vs_ssm_venue.png"),
                ("Signal roadmap / overlap", "figs/fig_overlap_jaccard.png"),
            ],
            "takeaway": """## Signal board (desk)

| Object | Label | Decision |
|--------|-------|----------|
| Nanex 80 bps (paper) | baseline | **Kill** on crypto (≈8 events / 42 cells) |
| Nanex 30 bps | baseline / PR | **Hold** — high precision vs SSM, threshold fragile |
| SSM z*=6 binary | risk monitor | **Hold** — σ_m / noise-floor fragile |
| SSM innovation path | info diagnostic | **Hold** — no forward lead vs mid |
| Outside-TOB (warehouse L2) | exec | **Hold** — sparse L2 → false outside |

Reading order: baselines → mc_garch → kalman_ssm → crash_stats.
""",
        },
        "crash_baselines": {
            "title": "# Crash baselines — Nanex / outside-TOB / V-shape",
            "theory": r"""## Pass 1 formulas

**Nanex (crypto clock):** ≥10 uni-dir trades, ≤1.5s, |ΔP|≥θ. Paper θ=0.8%; desk primary θ=0.3%.

**V-shape:** first leg ≥θ within 1.5s, recovery ≥50% within next 1.5s.

**Outside-TOB:** \(p_t \notin [b_{t^-}, a_{t^-}]\).
""",
            "figs": [
                ("Nanex vs SSM counts", "figs/fig_nanex_vs_ssm_venue.png"),
                ("Overlap Jaccard", "figs/fig_overlap_jaccard.png"),
            ],
            "takeaway": """## Pass 2 — incremental info

- Nanex∩SSM precision ≈ **0.90** (Nanex events almost always SSM); recall ≈ **0.026** (SSM much broader).
- Concurrent |imbalance| rises Nanex pre→con (≈0.56→0.71).
- Paper 80 bps **Kill**; warehouse outside-TOB **Hold** (Deribit smoke outside_rate 15–79% on sparse L2).
""",
        },
        "mc_garch_vol": {
            "title": "# MC-GARCH vol feed — \(h_n,s_j,q\) → \(\\sigma_p,\\sigma_m\)",
            "theory": r"""## Pass 1

UTC 5m bars (288/day). Daily \(h_n=\sum_j r_{n,j}^2\). Diurnal
\(\hat s_j \propto \mathrm{mean}(r^2/h)\). Intraday \(q\) via GARCH(1,1) on
\(z=r/\sqrt{h s}\).

\[\sigma_p^2\Delta t \propto q\,h\,s\cdot\Delta t,\quad
\sigma_m = \texttt{frac}\cdot\max(\mathrm{MAD}(\Delta\log p),\,10^{-4}).\]
""",
            "figs": [
                ("Diurnal s_j vs crash intensity", "figs/fig_diurnal_vs_crashes.png"),
                ("Hourly notional (vol.curve_intraday link)", "figs/fig_hour_share.png"),
                (r"σ_m frac stress", "figs/fig_sigma_m_stress.png"),
            ],
            "takeaway": """## Pass 2

- Hourly notional peak **UTC 12** (share ≈0.09) — link mmip `vol.curve_intraday` (peak ~18 UTC on other samples; sample-dependent).
- σ_m frac stress @ z*=6: **0.5→13832**, **1→3668**, **2→808**, **4→177** events — **Kill vanity** of any single frac without floor + stress table.
- Diurnal s_j usable as **schedule prior** (Hold Promote until multi-week stable peak).
""",
        },
        "kalman_ssm": {
            "title": "# Kalman SSM crash detector",
            "theory": r"""## Model

\[
x_i=x_{i-1}+\epsilon_{p},\quad z_i=x_i+\epsilon_{m}.
\]

Standardized innovation \(z^\mathrm{crash}=\nu_i/\sqrt{P_i^-+\sigma_m^2}\). Flag \(|z|\ge z^\*\) (default 6).
""",
            "figs": [
                ("z* scan", "figs/fig_zstar_scan.png"),
                ("Innovation lead–lag", "figs/fig_innov_leadlag.png"),
                ("Nanex vs SSM", "figs/fig_nanex_vs_ssm_venue.png"),
            ],
            "takeaway": """## Pass 2

| z* | pooled events |
|----|---------------|
| 2 | 36416 |
| 6 | **3668** |
| 12 | 630 |

Venue SSM @ z*=6 (noise floor 1bp): HL **3075**, Deribit **349**, Kraken **244**.

Lead–lag: strong **backward** corr (mechanical), forward ≈0 → not tradable.
Binary SSM **Hold** pending Phase 3 severity filters (median |ΔP| of raw flags ≈0).
""",
        },
    }

    for pkg, meta in packages.items():
        chap = BOOK / "chapters" / pkg
        chap.mkdir(parents=True, exist_ok=True)
        cells = [
            _md(meta["title"]),
            _md(meta["theory"]),
            _md("## Empirics summary"),
            _code(common_load, outputs=[stream], n=1),
        ]
        for i, (cap, fig) in enumerate(meta["figs"], start=2):
            cells.append(_md(f"### {cap}\n\n`{fig}`"))
            fp = OUT / fig
            outs = [_img(fp)] if fp.exists() else []
            cells.append(
                _code(
                    f"from IPython.display import Image, display\n"
                    f"display(Image(filename=str(OUT / '{fig}')))\n",
                    outputs=outs,
                    n=i,
                )
            )
        cells.append(_md(meta["takeaway"]))
        cells.append(_md("## Signal board\n\nSee `CANDIDATES.md` + `../../DESK_MEMO.md`."))
        path = chap / f"{pkg}.ipynb"
        path.write_text(json.dumps(_nb(cells), indent=1))
        print("wrote", path)


if __name__ == "__main__":
    main()
