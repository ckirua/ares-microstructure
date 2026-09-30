# Market Microstructure Confronting Viewpoints — Tick Size

| Field | Value |
|-------|-------|
| **Authors** | Barbara Rindi (Bocconi/IGIER); joint with Buti, Consonni, Wen, Werner |
| **Title** | *Tick Size: Theory and Evidence* |
| **Edition / provenance** | Slides presented at **Market Microstructure: Confronting Many Viewpoints #3**, Paris, **2014-12-11** (50 pp). Local PDF in this folder (gitignored `*.pdf`; filename typo `vfiewpoints` kept). Later lineage: Buti–Rindi–Wen–Werner *Tick Size, Trading Strategies and Market Quality* (Management Science) — harness stays faithful to **deck** empirics (LSE + Nasdaq/$1 RDD + FM), not later TSE/US Pilot samples. |
| **Slug** | `mm_confr_viewpoints` |

Book PDF and verbatim extracts under `_raw/` stay **local-only** (gitignored via repo `research/books/**/_raw/` + `*.pdf`). Do not commit copyrighted text.

**Not** the Wiley edited volume of the same conference series — single-talk program (like `v_shapes`), not a multi-author book.

This tree mirrors [`../mn_tuwrv/`](../mn_tuwrv/) and [`../v_shapes/`](../v_shapes/): chapter packages, experiment scripts, notebooks, and `out/` artifacts. Shared lib: [`../../lib/ticksize.py`](../../lib/ticksize.py). Quality bar: [`../../LOOP.md`](../../LOOP.md). Data: [`../../DATA_PATHS.md`](../../DATA_PATHS.md).

**Core claim (deck → crypto test):** absolute and **relative tick** \(\tau/v\) reshape LO vs MO incentives; large vs small tick changes and liquid vs less-liquid books flip signs for quoted/relative spread, BBO/total depth, and volume (prediction tables ~pp. 20–29). Relative tick equivalence (\(\downarrow\tau\) ≈ \(\uparrow v\)) holds for several quality metrics.

**Hard distinction:** mmip already Promotes `tick.rel_tick_bps`, `tick.spread_leeway`, `tick.frac_one_tick` as descriptive regime classifiers. This book owns **Rindi prediction tables + panel/RDD-style tests** in `ticksize.py`. Cross-link mmip tick IDs; do **not** merge APIs or re-Promote the same descriptors without new falsifiers.

**Venue set (locked):** Hyperliquid + Deribit + **Kraken** core; Lighter / RiseX opportunistic.

**Lenses:** `risk` · `info` · `exec` · `disc` · `cont` · `liq` · `mm`

**Two-pass protocol (mandatory):** every package ships Pass 1 (faithful deck object on HL+Deribit+Kraken) then Pass 2 (info/signals dig + falsifiers) before Promote/Hold/Kill. See [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md).

**Out of scope:** exact LSE GBX / Nasdaq $1 RDD replication; SEC tick pilot / IPO / analyst-coverage claims; welfare measurement; production LOB game sim (NOTES only under `emp_predictions`).
