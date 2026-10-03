# Constrained Dealers and Market Efficiency

| Field | Value |
|-------|-------|
| **Authors** | Wenqian Huang, Angelo Ranaldo, Andreas Schrimpf, Gyuri Somogyi |
| **Title** | *Constrained Dealers and Market Efficiency* |
| **Edition / provenance** | Nov 2021 working paper (SSRN [3960577](https://ssrn.com/abstract=3960577)). Local PDF in this folder (gitignored `*.pdf`). |
| **Slug** | `cd_me` |

Book PDF and verbatim extracts under `_raw/` stay **local-only** (gitignored via repo `research/books/**/_raw/` + `*.pdf`). Do not commit copyrighted text.

This tree mirrors [`../v_shapes/`](../v_shapes/) and [`../filmonov/`](../filmonov/): chapter packages, experiment scripts, notebooks, and `out/` artifacts. Shared lib: [`../../lib/cdme.py`](../../lib/cdme.py). Thematic sibling (inventory): [`../empirical_mm/`](../empirical_mm/). Quality bar: [`../../LOOP.md`](../../LOOP.md). Data: [`../../DATA_PATHS.md`](../../DATA_PATHS.md).

**Core claim (paper → crypto test):** dealer risk-bearing constraints weaken **liquidity elasticity**; **PIM = VLOOP + \|TCOST\|** (triangular / cross-venue LOP gap + arb costs) rises when dealers are constrained. Detection / monitor ≠ naked arb α.

**Hard distinction:** do **not** merge into [`../../lib/continuous.py`](../../lib/continuous.py) Cont–Kukanov OFI. New objects live in `cdme.py`. Closest inventory sibling is Huang–Stoll in `discrete.py` — cross-link only.

**Venue set (locked):** Hyperliquid + Deribit + **Kraken** core. Primary Pass-1 cell: **ETH** cross-venue LOP; BTC widen after gates.

**Crypto adaptation (locked):**
- `VLOOP` = \|log(mid_i / mid_j)\| on latency-aligned TOB (cross-venue pairs)
- `TCOST` from sum of relative half-spreads on the arb legs
- `PIM` = VLOOP + \|TCOST\| when VLOOP > 0 (paper Eq. 2–3 spirit)
- Volume proxy = trade intensity / notional on home venue
- **DCM̂** = first PC of public constraint proxies: funding \|level\|, perp basis \|level\|, realized vol, trade-imbalance inventory proxy (no bank VaR/CDS)
- Native multi-pair triangles (ETH–BTC–USD) **parked** until multi-pair TOB coverage is confirmed

**Lenses:** `risk` · `info` · `exec` · `disc` · `cont` · `liq` · `mm`

**Two-pass protocol (mandatory):** every package ships Pass 1 (faithful paper object on HL+Deribit+Kraken) then Pass 2 (info/signals dig + falsifiers) before Promote/Hold/Kill. See [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md).

**Honesty:** TOB-cross never Promote-as-α. ClickHouse MCP banned — warehouse / startarb / collector only.
