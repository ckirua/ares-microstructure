# Microstructure Noise (TSRV) — research index

Living map of Romero (2016) / ZMA05 packages → candidates → experiment status.
Siblings: [`../mmip/`](../mmip/) · [`../empirical_mm/`](../empirical_mm/) · [`../cross_miniflash/`](../cross_miniflash/) · [`../v_shapes/`](../v_shapes/) · [`../cd_me/`](../cd_me/).
Data: [`../../DATA_PATHS.md`](../../DATA_PATHS.md). Desk: [`DESK_MEMO.md`](DESK_MEMO.md). Uses: [`TRADING_APPLICATIONS.md`](TRADING_APPLICATIONS.md).

**Book:** Romero (2016) · ZMA05 TSRV. Slug: `mn_tuwrv`.

**Program status:** **Pass 2.8 depth / information / predictive** on Pass 2.7 panel (**34d** · ETH+BTC+SOL · **n_ok=204** · **n_mid=122** · predictive pairs **180**). Pass 2.7 gates unchanged (**0 Promote**). Predictive board: **0 Promote** after encompassing (noise→RV raw IC Hold; DM Kill TSRV-beats-sparse). MC **Kill** sparse stands.


**Shared lib:** [`../../lib/tsrv.py`](../../lib/tsrv.py) (`signature_rv_curve`, `noise_return_acf`, `optimal_K_scan`) · loaders [`scripts/_data.py`](scripts/_data.py)  
**Expand:** [`scripts/exp_expand_panel.py`](scripts/exp_expand_panel.py) → [`out/expand_panel/`](out/expand_panel/)  
**Depth/predict:** [`scripts/exp_depth_predict.py`](scripts/exp_depth_predict.py) → [`out/depth_predict/`](out/depth_predict/)  
**Monitors:** [`applications/monitors.py`](applications/monitors.py)

---

## Package roadmap

| Package | Status | Notes |
|---------|--------|-------|
| `ch00_overview` | `exp_run` | Signal board + Pass 2.8 pointers |
| `estimators` | `exp_run` | TSRV OOS Hold; clocks Kill/Hold; n=204 |
| `monte_carlo` | `exp_run` | Kill sparse-only (n=500) |
| `noise_proxy` | `exp_run` | Multi-week noise_std |
| `market_noise` | `exp_run` | ρ≈0 Hold; info content vs Amihud/RV |
| `xvenue_noise` | `exp_run` | concordance Hold n_cells=79 |
| depth_predict | `exp_run` | signature/ACF/K · OOS IC · uses memo |

---

## Promote rollup

| Candidate | Decision | One-line |
|-----------|----------|----------|
| *(none)* | — | No pre-registered gate cleared (incl. predictive encompassing) |

**Kill:** `cont.sparse_rv_only` · `cont.noise_dominates_1s_mid` · `cont.noise_trade_clock_bounce` · `cont.noise_tick_bounce_clock` · `pred.noise_to_spread_widen` · `pred.fifth_fourth_to_next_rv` · `pred.tsrv_gap_to_next_rv` · `pred.tsrv_beats_sparse_rv_forecast`  
**Hold:** `cont.tsrv_first_adj` · `cont.noise_var_fifth` · `cont.noise_mid_clock` · `liq.noise_vs_spread` · `frag.xvenue_noise_concord` · `pred.noise_to_next_rv` (encompassed) · `pred.noise_to_next_spread` · `pred.intensity_to_next_noise` · `pred.amihud_to_next_amihud` · `pred.model_score_next_rv`

---

## Pre-registered gates

| ID | Gate |
|----|------|
| `liq.noise_vs_spread` | ρ>0 ∧ shuffle p<0.05 ∧ early∧late same sign ∧ n≥20 ∧ bootstrap CI_lo>0 |
| `cont.tsrv_first_adj` | fragile_rate=0 ∧ (sparse−tsrv) CI_lo>0 early∧late ∧ n≥20 (not MC alone) |
| `cont.noise_mid_clock` | median fifth/fourth bootstrap CI_lo>1.5 |
| `pred.*` (Pass 2.8) | late OOS \|CI_lo\|>0.10 ∧ n≥30 ∧ early same-sign CI; noise→RV also needs encompassing partial IC |

---

## Kraken data map (Pass 2.7)

| Stream | Where | Quoted TOB? |
|--------|-------|-------------|
| Futures sealed MRCTCAP1 / public-md | `s3://mercat-kraken-md` | **No** |
| Spot L2 public-md | same bucket, `spot-*` shards | **Yes** → `spot\|ETH/USD` |
| Futures live REST orderbook | public API | **Yes** → ingest cache |
| ClickHouse `kraken_md` | `148.251.90.84:9000` | unreachable from this host |

---

## Notebooks

| Notebook | Role |
|----------|------|
| [`notebooks/desk_synthesis.ipynb`](notebooks/desk_synthesis.ipynb) | Desk signal board + Pass 2.8 depth |
| [`notebooks/uses_and_information.ipynb`](notebooks/uses_and_information.ipynb) | Info content · uses · monitors |
| [`notebooks/predictive_power.ipynb`](notebooks/predictive_power.ipynb) | OOS IC / DM / encompassing |
| [`chapters/*/`](chapters/) | Per-package chapter packs |

Figures: [`out/desk_synthesis/figs/`](out/desk_synthesis/figs/). Rebuild: `python3 scripts/build_notebook_figs.py && python3 scripts/build_notebooks.py`.
