# Microstructure Noise (TSRV)

| Field | Value |
|-------|-------|
| **Author** | Aristides A. Romero Moreno (Utah State University) |
| **Title** | *Microstructure Noise: The Use of Two Scales Realized Volatility for the Noisy High-Frequency Data and its Implications for Market Efficiency and Financial Forecasting* |
| **Edition / provenance** | MA Plan B report, **May 2016**. DigitalCommons@USU [gradreports/826](https://digitalcommons.usu.edu/gradreports/826). Local PDF in this folder (gitignored `*.pdf`). |
| **Slug** | `mn_tuwrv` |

Book PDF and verbatim extracts under `_raw/` stay **local-only** (gitignored via repo `research/books/**/_raw/` + `*.pdf`). Do not commit copyrighted text.

This tree mirrors [`../mmip/`](../mmip/), [`../empirical_mm/`](../empirical_mm/), [`../cross_miniflash/`](../cross_miniflash/), and [`../v_shapes/`](../v_shapes/): chapter packages, experiment scripts, notebooks, and `out/` artifacts. Shared TSRV lib: [`../../lib/tsrv.py`](../../lib/tsrv.py). Quality bar: [`../../LOOP.md`](../../LOOP.md). Data: [`../../DATA_PATHS.md`](../../DATA_PATHS.md).

**Core claim (thesis → crypto test):** high-frequency RV is contaminated by microstructure noise \(Y=X+\epsilon\); Zhang–Mykland–Aït-Sahalia **TSRV** (first-best) consistently estimates integrated volatility using all data, while the **fifth-best** all-sample RV consistently estimates noise variance \(\widehat{E\epsilon^2}=[Y,Y]_T^{(all)}/(2n)\). Wider spreads / thinner liquidity ⇒ more noise.

**Hard distinction:** [`../../lib/continuous.py`](../../lib/continuous.py) `noise_robust_rv` is a **fine/coarse RV ratio diagnostic**. This book implements the full TSRV ladder in `tsrv.py`. Cross-link; do not merge APIs.

**Venue set (locked):** Hyperliquid + Deribit + **Kraken** core; Lighter / RiseX opportunistic.

**Lenses:** `risk` · `info` · `exec` · `disc` · `cont` · `liq` · `mm`

**Two-pass protocol (mandatory):** every package ships Pass 1 (faithful paper object on HL+Deribit+Kraken) then Pass 2 (info/signals dig + falsifiers) before Promote/Hold/Kill. See [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md).
