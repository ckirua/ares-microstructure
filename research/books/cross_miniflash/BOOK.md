# Cross-Section of Mini Flash Crashes

| Field | Value |
|-------|-------|
| **Authors** | Chyng Wen Tee, Christopher Ting (SMU Lee Kong Chian) |
| **Title** | *Cross-Section of Mini Flash Crashes and Their Detection by a State-Space Approach* |
| **Edition / provenance** | Working paper dated **2019-06-12** (SSRN). Local PDF in this folder (gitignored `*.pdf`). |
| **Slug** | `cross_miniflash` |

Book PDF and verbatim extracts under `_raw/` stay **local-only** (gitignored via repo `research/books/**/_raw/` + `*.pdf`). Do not commit copyrighted text.

This tree mirrors [`../mmip/`](../mmip/) and [`../empirical_mm/`](../empirical_mm/): chapter packages, experiment scripts, notebooks, and `out/` artifacts. Shared crash detectors: [`../../lib/crash.py`](../../lib/crash.py). Quality bar: [`../../LOOP.md`](../../LOOP.md). Data: [`../../DATA_PATHS.md`](../../DATA_PATHS.md).

**Core claim (paper → crypto test):** mini crashes = trade prices outside a Kalman-filtered “true” log-price band (±\(z^\*\sigma_e\)); larger / cheaper-to-trade names absorb news with smaller % moves over more trades / longer windows.

**Venue set (locked):** Hyperliquid + Deribit + **Kraken** core; Lighter / RiseX opportunistic for Herfindahl completeness.

**Lenses:** `risk` · `info` · `exec` · `disc` · `cont` · `liq` · `mm`

**Two-pass protocol (mandatory):** every package ships Pass 1 (faithful paper object on HL+Deribit+Kraken) then Pass 2 (info/signals dig + falsifiers) before Promote/Hold/Kill. See [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md).

**Program status:** **COMPLETE (Phase 4 hardened)** — desk signal board in [`DESK_MEMO.md`](DESK_MEMO.md); gates in [`out/phase4_hardening/`](out/phase4_hardening/); synthesis [`notebooks/desk_synthesis.ipynb`](notebooks/desk_synthesis.ipynb). Primary severity gate **10bps/ic5** (frag share tables also document **5bps/ic3**).  
**Experiments ledger:** [`EXPERIMENTS.md`](EXPERIMENTS.md) — what was tested vs not (chapters + applications).
