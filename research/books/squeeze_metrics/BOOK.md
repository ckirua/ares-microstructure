# The Implied Order Book

| Field | Value |
|-------|-------|
| **Authors** | SqueezeMetrics (`sqzme`) / GEX Edition |
| **Title** | *The Implied Order Book* |
| **Edition / provenance** | 6 July 2020. Local PDF in this folder (gitignored `*.pdf`). |
| **Slug** | `squeeze_metrics` |

Book PDF and verbatim extracts under `_raw/` stay **local-only** (gitignored via repo `research/books/**/_raw/` + `*.pdf`). Do not commit copyrighted text.

This tree mirrors [`../cd_me/`](../cd_me/) and [`../v_shapes/`](../v_shapes/): chapter packages, experiment scripts, notebooks, and `out/` artifacts. Shared lib: [`../../lib/squeeze.py`](../../lib/squeeze.py). Thematic sibling (dealer constraints / LOP stress): [`../cd_me/`](../cd_me/). Quality bar: [`../../LOOP.md`](../../LOOP.md). Data: [`../../DATA_PATHS.md`](../../DATA_PATHS.md).

**Core claim (paper → crypto test):** options imprint an **implied order book** via dealer δ-hedges. **DDOI → GEX → VEX → GEX+** maps dealer inventory into liquidity abundance / scarcity and squeeze / stress regimes on the underlying. Detection / liquidity map ≠ naked arb α.

**Hard distinction:** do **not** merge into [`../../lib/continuous.py`](../../lib/continuous.py) Cont–Kukanov OFI or [`../../lib/cdme.py`](../../lib/cdme.py) PIM/DCM. New objects live in `squeeze.py`. Cross-link only (e.g. RV / imbalance helpers).

**Venue set (locked):** Hyperliquid + Deribit + **Kraken** `spot_l2`. Primary cell: **ETH** (Deribit options IV + trade-flow DDOI; HL/Deribit underlying); BTC widen after gates.

**Crypto adaptation (locked):**
- Options IV → **Deribit** `implied_vol` (options present). Warehouse `open_interest` is **futures-only** → option DDOI = **`PROXY_trade_flow_DDOI`** from option trades (API OI for live only).
- Underlying mark / TOB → **Hyperliquid** + **Deribit** ETH (then BTC), latency-aligned
- Spot L2 densify → **Kraken** `spot_l2` **only when dense**; document gaps; do not invent TOB
- **`trade_synth` quarantined / forbidden** — never SoT for DDOI / GEX / VEX
- Cross-venue mid gap HL ↔ Deribit (± Kraken) → monitor / risk only — **Kill** Promote as arb α
- Clock: UTC-day certified `panel_gex_options` **n=9** (2026-09-14…18, 25–27, 2026-10-01)
**Program status:** Pass 2/2.5 complete — **0 Promote** (chrono/CI fail Promote bar despite paper-sign GEX↔RV).

**Lenses:** `risk` · `info` · `exec` · `disc` · `cont` · `liq` · `mm`

**Two-pass protocol (mandatory):** every package ships Pass 1 (faithful paper object on HL+Deribit+Kraken) then Pass 2 (info/signals dig + falsifiers) before Promote/Hold/Kill. See [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md).

**Honesty:** TOB-cross never Promote-as-α. ClickHouse MCP banned — warehouse / startarb / collector only.
