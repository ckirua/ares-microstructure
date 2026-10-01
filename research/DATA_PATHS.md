# ares-startarb market-data paths (for ares-microstructure reuse)

**Source repo:** `${ARES_STARTARB:-../ares-startarb}`  
**Truth plane:** S3 / `warehouse` parquet via `open_day` / `list_days` — **not ClickHouse** (MCP banned; treat CH as optional/off the critical path).  
**Sibling package:** `${WAREHOUSE_ROOT:-$HOME/lab/lab-n2070/warehouse}` (editable dep in `pyproject.toml`).

---

## 1. Primary data loaders

| Domain | Module | Key API | Notes |
|--------|--------|---------|-------|
| **Public exports** | `src/startarb/data/__init__.py` | re-exports below | Venue-agnostic S3/warehouse only |
| **Marks / 1m bars** | `src/startarb/data/marks.py` | `load_mark_ticks`, `load_mark_bars`, `resample_mark` | Tables: `mark_price` (Deribit/HL/Kraken/Extended/RiseX); **Lighter → `bbo` mid** |
| **OHLC bucketing** | `src/startarb/data/bars.py` | `ohlc_time_buckets` | Used by marks |
| **Latest BBO / poll** | `src/startarb/data/bbo.py` | `load_latest_bbo`, `load_latest_l2_rebuild`, `BboQuote`, `normalize_hl_source` | Tail-of-day parquet; not full tape. HL: `snap` vs `l2_rebuild` |
| **Historical quote stream** | `src/startarb/data/bbo_stream.py` | `load_quote_stream`, `QuoteStream`, `asof_index` | Replay arrays; optional downsample (`quotes_per_minute`); HL table `l2_rebuild` |
| **L2 → TOB rebuild** | `src/startarb/data/l2_rebuild.py` | `rebuild_tob_arrays` | `l2_snapshot_level` + `l2_delta`; ~5s HL cadence in warehouse |
| **Trades** | `src/startarb/data/trades.py` | `load_trade_tape`, `TradeTape` | `trade` table; preferred-shard tails; not guaranteed full-day |
| **Instrument IDs / ticks** | `src/startarb/data/instruments.py` | `resolve_instrument`, `instrument_id`, `price_scale` | FNV catalog; DEX price decimals |
| **Symbol map** | `src/startarb/data/symbols.py` | `venue_symbol`, `resolve_leg_instrument`, `xvenue_seed_pairs` | Backed by `src/startarb/config/symbols.yaml` |
| **Retries / env** | `src/startarb/data/retry.py`, `src/startarb/env.py` | `with_retries`, `ensure_env` | Fills `S3_*_MD_BUCKET` defaults from `MD_BUCKETS` |
| **Live WS TOB** | `src/startarb/data/exchange_ws.py` | `ExchangeWsHub`, `parse_hl_l2_payload`, `discover_*_market_id` | HL / Lighter / RiseX public WS |
| **Live buffer + REST** | `src/startarb/data/live_quotes.py` | `QuoteHub`, `BestQuoteBuffer`, `try_shm_md`, `fetch_hl` / `fetch_lighter` | Paper/live plane; optional HL SHM via mercat |
| **WS → disk collector** | `src/startarb/data/xarb_collector.py` | `XarbCollector`, `RotatingTobArchive`, CLI `-m startarb.data.xarb_collector` | `results/xarb_md/tob/YYYYMMDD/tob_*.parquet` |
| **Research panel I/O** | `src/startarb/research/xarb_md_io.py` | `load_collector_panel`, `load_warehouse_hist_panel`, `load_deep_md` | Pandas normalization for cross-venue TOB |
| **Volclock bus** | `src/startarb/research/volclock_bus.py` | `build_volclock_bus`, `load_trade_tape` + HL rebuild | Publishes `results/volclock_bus/volclock_bus.npz` |

**Warehouse primitives (used everywhere):**

```python
from warehouse import list_days, open_day, list_objects

days = list_days("hyperliquid")  # unions flat parquet/ + public-md/
batch = open_day("deribit", "2026-09-28").load(
    "mark_price",
    instrument_ids=[...],
    max_files=256,
)
```

Tables commonly loaded: `mark_price`, `bbo`, `trade`, `l2_snapshot_level`, `l2_delta`, (rebuild path uses snap+delta).

---

## 2. Venues & symbols

### Wired in `warehouse.VENUES` + startarb loaders

| Venue | Role in lab | Typical instruments | Mark/bar table | BBO / TOB primary |
|-------|-------------|---------------------|----------------|-------------------|
| **Deribit** | CEX marks, statarb, BTC/ETH xvenue | `BTC-PERPETUAL`, `ETH-PERPETUAL`, `SOL_USDC-PERPETUAL` | `mark_price` | `l2_snapshot_level` → TOB |
| **Hyperliquid** | DEX anchor, volclock, xarb | `BTC`, `ETH`, `SOL` (+ opaque flat ids) | `mark_price` | `l2_snapshot_level` or **`l2_rebuild`** |
| **Kraken** | CEX futures marks | `PF_XBTUSD`, `PF_ETHUSD`, `PF_SOLUSD` | `mark_price` (futures-000) | `l2_snapshot_level` |
| **Lighter** | DEX BBO | `BTC`, `ETH`, `SOL` | **`bbo` mid** (no mark in public-md) | native `bbo` |
| **Extended** | DEX marks | `BTC-USD`, `ETH-USD`, `SOL-USD` | `mark_price` | `bbo` |
| **RiseX** | DEX BBO | `BTC/USDC`, `ETH/USDC`, `SOL/USDC` | `mark_price` | native `bbo` |

Canonical map: `src/startarb/config/symbols.yaml` (`underlyings`, `hyperliquid_flat_ids`, `xvenue_seed_pairs`).

### Granularities

| Grain | Loader | Typical use |
|-------|--------|-------------|
| **1m mark bars** | `load_mark_bars(..., bar_ns=60e9)` | spread_z, statarb, shadow_live |
| **Tick marks** | `load_mark_ticks` | resample / custom bars |
| **Warehouse TOB** | `load_quote_stream` / `load_latest_bbo` | spreads, replay, persist-edge |
| **HL denser TOB** | `hl_source=l2_rebuild` | ~5.4s median vs ~349s snap-only |
| **Live TOB** | WS / collector | ms–sub-second (not warehouse) |
| **Trades** | `load_trade_tape` | VPIN, intensity, volume-clock bars |
| **Full L2 book** | *not exported as series* | only internal to `rebuild_tob_arrays` |

### Broader mercat universe (docs only)

`docs/DATA.md` lists Binance/Bybit/OKX/Bitget/Coinbase + historical buckets — **not** in `warehouse.VENUES` today. Microstructure repo can add venues by extending warehouse specs or reading S3 directly.

---

## 3. Storage layouts

### S3-compatible object storage — source of truth

Bucket names and endpoints come from env (`S3_*_MD_BUCKET`, `S3_URL`, … — see startarb `MD_BUCKETS`). Typical layouts:

- **Flat research:** `s3://{venue-md-bucket}/parquet/{venue}/YYYY/MM/DD/*.parquet`
- **Release-bound:** `s3://{venue-md-bucket}/public-md/{release_id}/{venue}/{shard}/parquet/...`
- **Type-split public-md:** filenames like `*.type-00008-mark_price.*.parquet`
- Env: `S3_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION`, `S3_*_MD_BUCKET`

### Local resolve order (`warehouse.io.resolve.ensure_local`)

| Root | Default path | Purpose |
|------|--------------|---------|
| **Raw mirror** | `WAREHOUSE_RAW_ROOT` → **`/srv/raw`** | `{bucket}/parquet/...` and `public-md/...` |
| **Object cache** | `WAREHOUSE_CACHE_ROOT` → **`~/.cache/warehouse`** | `objects/{bucket}/{etag}/file.parquet` after S3 fetch |
| **Listings** | under cache | `~/.cache/warehouse/listings/` (day index metadata) |

If the raw mirror is absent, loads succeed via **S3 → cache** when `~/.env` has keys.

### ClickHouse

Documented in `docs/DATA.md` as query cache over S3; **not on startarb critical path**. Native `clickhouse_driver` only if you add it separately — repo does not use CH for loaders.

### Local research artifacts (ares-startarb)

| Path | Contents |
|------|----------|
| `results/xarb_md/tob/YYYYMMDD/tob_*.parquet` | WS collector TOB (schema in `xarb_collector.py`) |
| `results/xarb_md/meta.json`, `summary.json` | Collector run metadata |
| `results/volclock_bus/volclock_bus.npz` | Published volclock feature bus |
| `results/<exp_id>/` | Harness outputs (CSV/MD, not primary MD) |
| `data/xarb_collect/` | Alternate collector root (optional) |

### Gateway SHM (live / HFT path)

- **MD rings** (probe only in startarb): `hype_gateway_md`, `lighter_gateway_md`, `risex_gateway_md`, … — see `src/startarb/oe/rings.py`
- **HL SHM quotes:** `live_quotes.try_shm_md` → `mercat.strategies.hype_mm.shm_binder` when installed
- **Volclock JSON stub:** `/dev/shm/startarb_volclock_eth.json` (optional consumer in soft gates)
- **OE rings:** separate from MD; dry-run only in research

---

## 4. How experiments load data (minimal patterns)

**Statarb / marks (numpy):**

```python
from startarb.data import load_mark_bars

bars = load_mark_bars("deribit", "ETH-PERPETUAL", days=["2026-09-28"])
close = bars["close"]  # 1m OHLC from mark ticks
```

**Cross-venue TOB replay (warehouse):**

```python
from startarb.data.bbo_stream import load_quote_stream

hl = load_quote_stream(
    "hyperliquid", "ETH", ["2026-09-26", "2026-09-27"],
    table="l2_rebuild", max_files=12, quotes_per_minute=30,
)
lit = load_quote_stream("lighter", "ETH", ["2026-09-26"], table="bbo")
```

**Volclock / microstructure features:**

```python
from startarb.data.trades import load_trade_tape
from startarb.research.volclock_bus import build_volclock_bus

tape = load_trade_tape("hyperliquid", "ETH", days=["2026-09-14"], max_files=16)
# combine with load_quote_stream(..., table="l2_rebuild") in volume_clock_alpha.py
```

**Collector + warehouse (deep xarb):**

```python
from startarb.research.xarb_md_io import load_collector_panel, load_warehouse_hist_panel

df, meta = load_collector_panel(roots=["results/xarb_md"], bases=["ETH"])
df_wh, wh_meta = load_warehouse_hist_panel(["ETH"], ["2026-09-25"], hl_source="l2_rebuild")
```

**Live (not historical):**

```python
from startarb.data.live_quotes import QuoteHub

hub = QuoteHub(symbols=("ETH", "BTC"))
hub.start()
q = hub.get("hyperliquid", "ETH")
```

**Reuse in ares-microstructure:** add dependency on `startarb` (path/git) + same `warehouse` editable path, call `ensure_env()` before any loader, set `PYTHONPATH=src` or install package.

---

## 5. Microstructure research mapping

| Research need | Existing loader / artifact | Gap |
|---------------|---------------------------|-----|
| **Bid–ask spreads** | `BboQuote.spread_bps`; `load_quote_stream`; collector parquet (`bid`/`ask`/`mid`) | Warehouse HL still seconds-scale unless live WS |
| **Depth / imbalance (TOB)** | `bid_qty`/`ask_qty` on BBO/L2 TOB; soft-gate `imb` from volclock stack | **No multi-level depth time series** exported; full book only inside rebuild |
| **Depth beyond L0** | — | Need new loader on `l2_snapshot_level` (all levels) or raw delta book builder |
| **Fragmentation / cross-venue share** | `load_mark_bars` + `xvenue`; `load_trade_tape` per venue; `xarb_md_io` panels | Volume share needs consistent qty units (`TradeTape.qty_coin`); alt bases thin on HL hist |
| **Tick size / price grid** | `instruments.price_scale`, `_DEX_PRICE_DECIMALS` | No standalone “min tick” API — infer from decimals / tick columns in parquet |
| **Volume curves (time ↔ volume)** | `volclock_bus.py`, `volume_clock_alpha.py`, `build_volclock_bus` | DEX legs use BBO mid gaps when trades absent |
| **Trade intensity / VPIN / L** | `load_trade_tape` + liquidity gates in `hft_replay` / `persist_edge_*` | Tape is **tail-windowed**, not certified complete day |
| **Funding / basis micro** | Marks only in statarb | `load_warehouse_hist_panel` notes `funding_basis: unavailable_no_funding_loader` |
| **Extended venue** | marks + bbo in warehouse | Less used in live xarb than Lit/RX |

**Recommended DENSE HL days (documented in lab):** 2026-09-14 … 18 and 25–26 for volclock / BBO density experiments.

---

## 6. Practical setup checklist

| Check | Expectation |
|-------|-------------|
| **`uv run` in ares-startarb** | `uv run python -c "import startarb; from warehouse import list_days"` succeeds |
| **`warehouse` importable** | Editable install from `${WAREHOUSE_ROOT:-$HOME/lab/lab-n2070/warehouse}` (or `WAREHOUSE_SRC` on `PYTHONPATH`) |
| **`list_days('<venue>')`** | Returns recent days when S3/cache credentials work (first listing can be slow) |
| **`/srv/raw`** | Optional; without it, rely on `~/.cache/warehouse/objects/...` |
| **ClickHouse** | **Not used** by loaders; do not use ClickHouse MCP |
| **Local collector parquet** | Optional under `${ARES_STARTARB:-../ares-startarb}/results/xarb_md/` |

**Sample paths (portable):**

1. `${ARES_STARTARB:-../ares-startarb}/results/xarb_md/tob/YYYYMMDD/tob_000000.parquet`
2. `$HOME/.cache/warehouse/objects/{bucket}/{etag}/…parquet`

**Integration checklist for ares-microstructure:**

1. Depend on `startarb` + `warehouse`; `source ~/.env` (S3 keys). Set `ARES_STARTARB` / `WAREHOUSE_ROOT` if not under `$HOME/srv` / `$HOME/lab/...`.
2. Prefer `load_quote_stream` / `load_trade_tape` over re-parsing S3 keys.
3. Treat warehouse TOB as **research-grade**, not HFT; use `xarb_collector` or live WS for ms work.
4. Do not use ClickHouse MCP; optional CH via native driver only where your ops docs say it works.

---

## Doc pointers (ares-startarb)

- `docs/DATA.md` — S3/CH inventory (CH optional)
- `docs/RESEARCH.md` — harness, Phase 0 data API
- `docs/alphas.md` — which sleeves consume which MD plane
- `docs/XARB_DEEP.md`, `docs/ENCODE_VOLCLOCK.md` — warehouse vs collector segmentation
