# Microstructure Noise (TSRV) — research index

Living map of Romero (2016) / ZMA05 packages → candidates → experiment status.
Siblings: [`../mmip/`](../mmip/) · [`../empirical_mm/`](../empirical_mm/) · [`../cross_miniflash/`](../cross_miniflash/) · [`../v_shapes/`](../v_shapes/).
Data: [`../../DATA_PATHS.md`](../../DATA_PATHS.md). Desk: [`DESK_MEMO.md`](DESK_MEMO.md).

**Book:** Romero (2016) · ZMA05 TSRV. Slug: `mn_tuwrv`.

**Program status:** **Pass 2.7 expand-panel** — full listing cache **34d** · ETH+BTC+SOL · **n_ok=204** · **n_mid=122**. Mid-clock CI_lo=1.13 < 1.5 → **Hold**. TSRV early clears but late does not → **Hold**. noise↔spread ρ≈0 → **Hold**. **0 Promote**. MC **Kill** sparse stands.


**Shared lib:** [`../../lib/tsrv.py`](../../lib/tsrv.py) · loaders [`scripts/_data.py`](scripts/_data.py) (`load_tob_day`, `load_kraken_spot_tob_day`, futures ingest cache)  
**Blocker/expand script:** [`scripts/exp_expand_panel.py`](scripts/exp_expand_panel.py) · artifact [`out/expand_panel/`](out/expand_panel/)  
**Futures ingest:** [`scripts/ingest_kraken_futures_tob.py`](scripts/ingest_kraken_futures_tob.py) → [`out/kraken_futures_tob/`](out/kraken_futures_tob/)

---

## Package roadmap

| Package | Status | Notes |
|---------|--------|-------|
| `ch00_overview` | `exp_run` | Signal board synced to Pass 2.7 |
| `estimators` | `exp_run` | TSRV OOS Hold; clocks Kill/Hold; n=204 |
| `monte_carlo` | `exp_run` | Kill sparse-only (n=500) |
| `noise_proxy` | `exp_run` | Multi-week noise_std |
| `market_noise` | `exp_run` | ρ≈0 Hold; mid-clock denser still Hold |
| `xvenue_noise` | `exp_run` | concordance Hold n_cells=79 |

---

## Promote rollup

| Candidate | Decision | One-line |
|-----------|----------|----------|
| *(none)* | — | No pre-registered gate cleared |

**Kill:** `cont.sparse_rv_only` · `cont.noise_dominates_1s_mid` · `cont.noise_trade_clock_bounce` · `cont.noise_tick_bounce_clock`  
**Hold:** `cont.tsrv_first_adj` · `cont.noise_var_fifth` · `cont.noise_mid_clock` · `liq.noise_vs_spread` · `frag.xvenue_noise_concord`

---

## Pre-registered gates

| ID | Gate |
|----|------|
| `liq.noise_vs_spread` | ρ>0 ∧ shuffle p<0.05 ∧ early∧late same sign ∧ n≥20 ∧ bootstrap CI_lo>0 |
| `cont.tsrv_first_adj` | fragile_rate=0 ∧ (sparse−tsrv) CI_lo>0 early∧late ∧ n≥20 (not MC alone) |
| `cont.noise_mid_clock` | median fifth/fourth bootstrap CI_lo>1.5 |

---

## Kraken data map (Pass 2.7)

| Stream | Where | Quoted TOB? |
|--------|-------|-------------|
| Futures sealed MRCTCAP1 / public-md | `s3://mercat-kraken-md` | **No** (trade/mark/index/funding/OI) |
| Spot L2 public-md | same bucket, `spot-*` shards | **Yes** → `spot\|ETH/USD` |
| Futures live REST orderbook | public API | **Yes** → ingest cache |
| ClickHouse `kraken_md` | `148.251.90.84:9000` | unreachable from this host |


## Notebooks (Pass 2.7 desk pack)

| Notebook | Role |
|----------|------|
| [`notebooks/desk_synthesis.ipynb`](notebooks/desk_synthesis.ipynb) | Desk signal board, CIs, Kill/Hold/Promote, Kraken TOB |
| [`chapters/ch00_overview/ch00_overview.ipynb`](chapters/ch00_overview/ch00_overview.ipynb) | Overview map |
| [`chapters/monte_carlo/monte_carlo.ipynb`](chapters/monte_carlo/monte_carlo.ipynb) | Heston MC RMSE ladder → Kill sparse |
| [`chapters/estimators/estimators.ipynb`](chapters/estimators/estimators.ipynb) | Clocks + TSRV OOS |
| [`chapters/noise_proxy/noise_proxy.ipynb`](chapters/noise_proxy/noise_proxy.ipynb) | Êε² panel |
| [`chapters/market_noise/market_noise.ipynb`](chapters/market_noise/market_noise.ipynb) | noise↔spread falsifiers |
| [`chapters/xvenue_noise/xvenue_noise.ipynb`](chapters/xvenue_noise/xvenue_noise.ipynb) | concordance Hold |

Figures: [`out/desk_synthesis/figs/`](out/desk_synthesis/figs/). Rebuild: `python3 scripts/build_notebook_figs.py && python3 scripts/build_notebooks.py`.
