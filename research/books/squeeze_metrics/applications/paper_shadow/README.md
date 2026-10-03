# squeeze_metrics paper_shadow — GEX / VEX / squeeze monitor SHADOW

**Class:** risk-monitor shadow · **not** sized alpha · **not** production quoting  
**Primary cell:** Hyperliquid ETH (+ Deribit / Kraken when loaders available)  
**Sibling pattern:** [`../../../cd_me/applications/paper_shadow/`](../../../cd_me/applications/paper_shadow/)

Long-running **warehouse-day recompute** on a pinned or latest listed tape day. No live exchange orders. Never mercat/gateway OE.

> **Desk honesty:** Pass-1 board is **Hold** (**0 Promote**).  
> Shadow logs monitor telemetry only. **Wire Promote only** (count still 0).  
> **Do not soft-Promote. Do not size. `live_orders=false`.**  
> **Never soft-Promote TOB-cross as α** (`alpha.tob_cross_arb` = **Kill**).

Paper: *The Implied Order Book* (SqueezeMetrics / GEX Ed., 6 Jul 2020).  
Lib: [`../../../../lib/squeeze.py`](../../../../lib/squeeze.py) (import when present — do not edit from this app).  
ClickHouse MCP banned.

---

## What each poll does

1. Resolve day (`--day` or latest listing / prefer recent complete when `scripts/_data.py` exists).
2. Load options / tape via book scripts when ready; else emit dependency stub.
3. Compute **GEX / VEX / squeeze intensity (GEX+) / implied-book liquidity scarcity** via `research.lib.squeeze` when present.
4. Append `logs/shadow.log` + `out/events.jsonl`; refresh `out/SHADOW_BOARD.md`.
5. Surface **Promote-only** actionable IDs (expect empty). All knobs tagged **Monitor/Hold** — never submit orders.

---

## Gate labels in the shadow

| ID | Gate | Shadow role |
|----|------|-------------|
| `risk.gex_exposure` | **Hold** | Dealer gamma exposure (GEX) telemetry |
| `risk.vex_exposure` | **Hold** | Dealer vanna exposure (VEX) telemetry |
| `risk.squeeze_intensity` | **Hold** | GEX+ / squeeze intensity monitor |
| `liq.implied_book_scarcity` | **Hold** | Implied-order-book liquidity scarcity |
| `alpha.tob_cross_arb` | **Kill** | Never sized / never soft-Promote |

**Promote wiring:** when a candidate flips to Promote, surface it on `SHADOW_BOARD.md` as an actionable monitor rule. Until then, Hold tiles above are **documentation only** — do not flip `live_orders`.

---

## Dependencies (Pass-1 scaffold)

Harness is complete. Runtime metrics need:

1. `research/lib/squeeze.py` — GEX/VEX/squeeze/scarcity primitives (sibling agent; **do not edit from here**)
2. `research/books/squeeze_metrics/scripts/_data.py` — warehouse day loaders

Until Pass-1 day packs exist under `out/gex_implied_book/`, dry-runs may fall back to live loaders + `research.lib.squeeze.chain_exposures`. Always `live_orders=false`; Promote count expected **0**.


---

## How to start

```bash
cd research/books/squeeze_metrics/applications/paper_shadow   # from repo root

# smoke: one poll on a historical UTC day
python3 run_paper_shadow.py --day 2026-09-29 --iterations 1

# one poll on latest listing day (when loaders exist)
python3 run_paper_shadow.py --iterations 1

# foreground forever
python3 run_paper_shadow.py --poll --interval 120
```

Requires startarb/warehouse env when `scripts/_data.py` lands.

---

## How to `tail -f` the log

```bash
tail -f logs/shadow.log
```

JSONL events:

```bash
tail -f out/events.jsonl
```

---

## Honesty

- Scoreboard = monitor telemetry — **not** PnL alpha
- `live_orders=False` · ClickHouse MCP banned · warehouse + startarb only
- Hold stays Hold until Pass 2 · Wire Promote only (expect 0)
