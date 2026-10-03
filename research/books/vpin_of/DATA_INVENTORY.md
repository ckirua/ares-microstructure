# Data inventory — vpin_of

**SoT loaders:** [`scripts/_data.py`](scripts/_data.py) · program paths: [`../../DATA_PATHS.md`](../../DATA_PATHS.md)  
**ClickHouse:** banned on critical path (native driver not required for VPIN — trades only).

**Refresh:** `python3 scripts/exp_data_inventory.py` → [`out/data_inventory/`](out/data_inventory/)

---

## Data provenance (Pass 1)

**All Pass 1 panel rows and `out/vpin_day/*` artifacts = warehouse trade prints** loaded through `startarb.data.trades.load_trade_tape` (S3 / local listing cache under `~/.cache/warehouse/mercat-*-md/`). There are **no synthetic fills or Monte Carlo trade tapes** in published panel outputs.

| Artifact | Source path | Notes |
|----------|-------------|--------|
| `out/vpin_panel/rows.jsonl` | `_data.load_day_trades` → `load_trades` | Pass 1 runner: `--all-days` grid ETH/BTC/SOL × HL+Deribit+Kraken; `complete=True` UTC days only. **Promote provenance:** HL+DB subset → `decisions_panel_promote.json` (n_ok=139). Kraken rows included for coverage/falsifiers but **`frag.kraken_vpin` stays Hold** |
| `out/vpin_day/*.json` | `_data.vpin_day_features` | Single-day smoke / construction reports |
| `out/data_inventory/*.json` | `_data.load_day_trades` probes | Listing span + completeness flags |

**Not empirical tape (by design, labeled in JSON):**

- `side_shuffle` in panel rows — **sign-permutation null** on real `(side, qty)` (`research/lib/vpin.py::falsify_side_shuffle`); does not replace the tape.
- Bootstrap CIs (`vpin_ci95`, panel aggregates) — resampling of **real** bucket statistics.
- Future **robustness** chapter (`chapters/robustness/`) — scale grids on real tape; any pure simulation chapter must be explicitly tagged **sim** (not run in Pass 1).

TOB / mark joins for predictiveness use collector parquet or warehouse L2 (`load_tob_day`); Kraken futures L2 gaps may use Roll/mark **proxies** (`kraken_liquidity_proxies`) — not used as VPIN bucket input.

---

## Coverage table (probe 2026-10-03 UTC)

| Venue | S3 bucket (listing cache) | Calendar span (cached) | Symbols (core) | Grain | VPIN-ready? |
|-------|---------------------------|-------------------------|----------------|-------|-------------|
| Hyperliquid | `mercat-hyperliquid-md` | 2026-08-28 … 2026-10-03 (37d) | BTC, ETH (**SOL gap** on probe day) | `trade` tape, UTC clip | **Yes** ETH/BTC on complete days |
| Deribit | `mercat-deribit-md` | 2026-08-28 … 2026-10-01 (35d) | BTC, ETH, SOL perps | `trade` tape | **Yes** (complete days) |
| Kraken futures | `mercat-kraken-md` | 2026-08-28 … 2026-10-01 (35d) | PF_XBTUSD, PF_ETHUSD, PF_SOLUSD | `trade` (tail window) | **Partial** — low coverage / incomplete |
| Lighter / RiseX | listing caches present | opportunistic | BTC, ETH, SOL | `trade` / `bbo` | Not wired in `_data.py` yet |
| Collector TOB | `ares-startarb/results/xarb_md/tob` | rolling YYYYMMDD | HL, Lighter, RiseX | ms TOB | Predictiveness join (not VPIN input) |
| `research/out` | repo-local | per experiment | — | JSON/JSONL | Read outputs from sibling books only |

### Example complete UTC day (2026-09-30)

| Underlying | Hyperliquid n | Deribit n | Kraken n (2026-09-29 best) | Notes |
|------------|---------------|-----------|----------------------------|-------|
| ETH | 160,836 | 83,559 | 3,044 | Kraken: coverage≈0.05, `complete=False` |
| BTC | 381,404 | 221,630 | 6,486 | same |
| SOL | **0** (empty) | 94,768 | 1,253 | HL SOL instrument / shard gap |

Artifacts: [`out/data_inventory/probe_complete_days.json`](out/data_inventory/probe_complete_days.json)

---

## Side classification

Warehouse `tape.side` → normalized ±1 via `normalize_side` in `_data.py`. VPIN buckets require signed volume (buy vs sell).

---

## Volume-clock calibration default

`default_bucket_volume(qty) = median(qty>0) × 50` (matches [`../empirical_mm/`](../empirical_mm/) Ch.15). Override via `exp_vpin_* --bucket-scale`.

---

## Known blockers for experiments

1. **Kraken futures tape** — S3 tails often fail `day_completeness`; label `complete=False` or exclude from Promote gates.  
2. **Hyperliquid SOL** — empty day on 2026-09-30 probe; verify symbol map / shard availability before SOL panel.  
3. **Latest calendar day** — often incomplete (e.g. HL 2026-10-03 n=0); use T−1 or listing-backed last **complete** day.  
4. **PIN MLE multi-day** — needs ≥20 **complete** days per venue (empirical_mm gate).  
5. **PDF source** — image PDF; OCR not run in Agent 1 (see [`_raw/SOURCE.md`](_raw/SOURCE.md)).
