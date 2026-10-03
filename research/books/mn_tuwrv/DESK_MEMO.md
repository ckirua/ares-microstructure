# Desk memo — Microstructure Noise / TSRV (Romero 2016 · ZMA05)

**Audience:** crypto MM / SOR / execution / taker / risk / research  
**Source:** Romero MA thesis (2016) / ZMA05 TSRV → `research/books/mn_tuwrv/`  
**Data:** warehouse trades + collector/warehouse TOB + Kraken spot L2 + futures REST ingest — **no ClickHouse MCP**  
**Program status:** **Pass 2.8 depth/predict** — **0 Promote** (Pass 2.7 board unchanged; predictive 0 Promote after encompassing) · MC **Kill** sparse stands  
**SoT:** [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) · Uses: [`TRADING_APPLICATIONS.md`](TRADING_APPLICATIONS.md) · Lib: [`../../lib/tsrv.py`](../../lib/tsrv.py)  
**Artifacts:** [`out/expand_panel/`](out/expand_panel/) · [`out/depth_predict/`](out/depth_predict/) · [`out/blocker_close/`](out/blocker_close/)  
**Desk notebooks:** [`notebooks/desk_synthesis.ipynb`](notebooks/desk_synthesis.ipynb) · [`notebooks/uses_and_information.ipynb`](notebooks/uses_and_information.ipynb) · [`notebooks/predictive_power.ipynb`](notebooks/predictive_power.ipynb)

---

## 0. Sample (Pass 2.7 ceiling — unchanged)

| | **Pass 2.7 / 2.8** |
|--|---------------------|
| Days | **34** (2026-08-28…09-30) |
| Symbols | ETH+BTC+SOL |
| n_ok | **204** · n_mid **122** · n_spread **144** |
| Predictive pairs | **180** next-day · split **2026-09-13** · early 86 / late 94 |

**Data ceiling:** listing caches 34d; no older S3 on this host. Crash/V not joined.

---

## 1. Signal board (Pass 2.7 + 2.8 predictive)

| ID | Decision | Evidence |
|----|----------|----------|
| `cont.sparse_rv_only` | **Kill** | MC first_adj RMSE ≈ 0.42× fourth |
| `cont.noise_dominates_1s_mid` | **Kill** | calendar med≈1.01 |
| `cont.noise_trade_clock_bounce` | **Kill** | med≈0.82 |
| `cont.noise_tick_bounce_clock` | **Kill** | CI fails 1.5 |
| `cont.noise_mid_clock` | **Hold** | med≈2.45 CI≈[1.13, 3.78] n=122 |
| `cont.tsrv_first_adj` | **Hold** | early CI_lo>0; late through 0 |
| `cont.noise_var_fifth` | **Hold** | liquidity proxy |
| `liq.noise_vs_spread` | **Hold** | ρ≈0.02 CI through 0 · same_sign=False |
| `frag.xvenue_noise_concord` | **Hold** | frac_close≈0.63 |
| `pred.noise_to_next_rv` | **Hold** | raw OOS IC≈0.36 CI=[0.16,0.53] but **encompassing fails** (noise⊥fourth≈0.06) |
| `pred.noise_to_next_spread` | **Hold** | late same-sign; early opposite sign |
| `pred.noise_to_spread_widen` | **Kill** | CI through 0 |
| `pred.fifth_fourth_to_next_rv` | **Kill** | CI through 0 |
| `pred.tsrv_gap_to_next_rv` | **Kill** | CI through 0 |
| `pred.intensity_to_next_noise` | **Hold** | late strong; early null |
| `pred.amihud_to_next_amihud` | **Hold** | persistence (not Êε claim) |
| `pred.model_score_next_rv` | **Hold** | late CI_lo≈0.05 < 0.10 |
| `pred.tsrv_beats_sparse_rv_forecast` | **Kill** | DM late prefer **sparse** (t≈−2.0) |

---

## 2. Thesis empirics (Pass 2.8 tape subset n=16)

| Object | Result |
|--------|--------|
| Signature fine-end log(RV)/log(step) slope | med≈**+0.03** · frac_neg≈0.31 — weak classical “explosion”; crypto 1s still noisy but slope not uniformly negative |
| Return ACF lag-1 | med≈**+0.006** · MA(1) frac≈0.06 — **weak** vs ZMA05 i.i.d. noise implication |
| Optimal K (stability) | med≈**180** (book default 300) |
| TOD ACF | see `fig_tod_acf.png` |

---

## 3. Information content

Contemporaneous Spearman (n≈204), paired bootstrap CI:

| noise_std vs | ρ | CI95 | read |
|--------------|---|------|------|
| spread_bps | ≈0.02 | through 0 | friction link **absent** on slice |
| Amihud | ≈0.41 | [0.31, 0.51] | co-moves with illiquidity |
| intensity | ≈0.00 | through 0 | not activity |
| sparse/TSRV RV | ≈0.76 | [0.68, 0.83] | **vol-level / information-arrival** co-move |

**Read:** Êε tracks **vol and Amihud**, not quoted spread → treat as **vol/illiquidity state**, not a pure bid–ask friction meter on this crypto panel.

---

## 4. Uses (one-liners)

1. **Risk RV:** always TSRV/first_adj over sparse-only (MC Kill). Tape DM does **not** add a tradable TSRV forecast edge.  
2. **Quoting:** mid-clock bounce Hold — venue-local (Deribit≫HL); distrust mid-mark RV when mid fifth/fourth elevated.  
3. **Do not** auto-widen on noise_std (spread link Hold/Kill).  
4. Monitors: [`applications/monitors.py`](applications/monitors.py) · memo [`TRADING_APPLICATIONS.md`](TRADING_APPLICATIONS.md).

---

## 5. Open

1. Listing history ceiling 34d.  
2. Kraken futures historical quoted TOB still missing.  
3. Deribit≫HL mid heterogeneity unexplained.  
4. Crash/V predictive join not wired.  
5. Signature/ACF only weakly match classical equity thesis on this tape subset — revisit sampling/grid.
