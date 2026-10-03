# VPIN & order-flow toxicity

| Field | Value |
|-------|-------|
| **Authors** | David Easley, Marcos López de Prado, Maureen O'Hara (core VPIN line); related PIN / flow-toxicity notes |
| **Title** | *Flow Toxicity and Liquidity in a High Frequency World* (VPIN family) — local deck: **VPIN orderflow toxidity.pdf** |
| **Edition / provenance** | Working-paper / deck PDF (ReportLab export; image-heavy — extract via OCR if needed). Wikipedia anchors in PDF metadata point to [David Easley](https://en.wikipedia.org/wiki/David_Easley). |
| **Slug** | `vpin_of` |

Book PDF and verbatim extracts under `_raw/` stay **local-only** (gitignored via repo `research/books/**/_raw/` + `*.pdf`). Do not commit copyrighted text.

This tree mirrors [`../mn_tuwrv/`](../mn_tuwrv/), [`../empirical_mm/`](../empirical_mm/), [`../v_shapes/`](../v_shapes/), and [`../cross_miniflash/`](../cross_miniflash/): chapter packages, experiment scripts, notebooks, and `out/` artifacts.

**Core claim (paper → crypto test):** volume-clock **order-flow imbalance** (VPIN) rises ahead of **toxic** / informed flow and stress; useful as **risk & sizing** feature (see cross_miniflash VPIN×size), distinct from full **PIN MLE** (EHO).

**Hard distinction:** [`../../lib/continuous.py`](../../lib/continuous.py) `vpin_bucket` is a **desk VPIN analogue** (equal-volume buckets). [`../../lib/pin.py`](../../lib/pin.py) hosts **PIN MLE** + `compare_pin_vpin`. Do not merge APIs.

**Venue set (locked):** Hyperliquid + Deribit + **Kraken** core; Lighter / RiseX opportunistic.

**Lenses:** `risk` · `info` · `exec` · `disc` · `cont` · `liq` · `mm`

**Two-pass protocol (mandatory):** Pass 1 (faithful VPIN construction + calibration on HL+Deribit+Kraken) then Pass 2 (predictiveness, toxicity events, cross-venue, falsifiers) before Promote/Hold/Kill. See [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md).

**Data:** [`../../DATA_PATHS.md`](../../DATA_PATHS.md) · book inventory [`DATA_INVENTORY.md`](DATA_INVENTORY.md) · loaders [`scripts/_data.py`](scripts/_data.py).
