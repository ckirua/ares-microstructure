# V-shapes

| Field | Value |
|-------|-------|
| **Authors** | Maria Flora, Roberto Renò (University of Verona) |
| **Title** | *V-shapes* |
| **Edition / provenance** | Working paper dated **2020-09-17** (SSRN [3554122](https://ssrn.com/abstract=3554122)). Local PDF in this folder (gitignored `*.pdf`). |
| **Slug** | `v_shapes` |

Book PDF and verbatim extracts under `_raw/` stay **local-only** (gitignored via repo `research/books/**/_raw/` + `*.pdf`). Do not commit copyrighted text.

This tree mirrors [`../mmip/`](../mmip/), [`../empirical_mm/`](../empirical_mm/), and [`../cross_miniflash/`](../cross_miniflash/): chapter packages, experiment scripts, notebooks, and `out/` artifacts. Shared V-statistic lib: [`../../lib/vstat.py`](../../lib/vstat.py). Quality bar: [`../../LOOP.md`](../../LOOP.md). Data: [`../../DATA_PATHS.md`](../../DATA_PATHS.md).

**Core claim (paper → crypto test):** market inefficiency = sudden **sign change of the price drift** (V / Λ), detected by the **V-statistic** \(V_{\tau,n}=\sqrt{h_n}\,T^+_{\tau,n}\,T^-_{\tau,n}\); negative significant MinV ⇒ reverting drift / fragility, distinct from volatility spikes or jumps.

**Hard distinction:** [`../../lib/crash.py`](../../lib/crash.py) `vshape_events` is a **geometric** Dugast–Foucault move+recovery baseline. Flora–Renò lives in `vstat.py` (kernels, pre-avg+HAC, EGARCH bootstrap). Do not merge APIs.

**Venue set (locked):** Hyperliquid + Deribit + **Kraken** core; Lighter / RiseX opportunistic.

**Lenses:** `risk` · `info` · `exec` · `disc` · `cont` · `liq` · `mm`

**Two-pass protocol (mandatory):** every package ships Pass 1 (faithful paper object on HL+Deribit+Kraken) then Pass 2 (info/signals dig + falsifiers) before Promote/Hold/Kill. See [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md).
