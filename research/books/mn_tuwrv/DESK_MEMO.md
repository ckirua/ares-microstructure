# Desk memo — Microstructure Noise / TSRV (Romero 2016 · ZMA05)

**Audience:** crypto MM / SOR / execution / taker / risk / research  
**Source:** Romero MA thesis (2016) / ZMA05 TSRV → `research/books/mn_tuwrv/`  
**Data:** warehouse trades + collector/warehouse TOB + Kraken spot L2 + futures REST ingest — **no ClickHouse MCP**  
**Program status:** **Pass 2.6 blocker-close** — **0 Promote** on mid-clock / tape TSRV; MC **Kill** sparse stands  
**SoT:** [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) · Lib: [`../../lib/tsrv.py`](../../lib/tsrv.py)  
**Artifacts:** [`out/blocker_close/`](out/blocker_close/) · [`out/gap_close/`](out/gap_close/) · [`out/kraken_futures_tob/`](out/kraken_futures_tob/)  
**Desk notebooks:** [`notebooks/desk_synthesis.ipynb`](notebooks/desk_synthesis.ipynb) · chapter notebooks under [`chapters/`](chapters/) · figs [`out/desk_synthesis/figs/`](out/desk_synthesis/figs/)

---

## 1. TOB path diagnosis (Pass 2.6)

| Venue | Quoted TOB path | Status |
|-------|-----------------|--------|
| Hyperliquid | collector ∪ warehouse `l2_rebuild` | Dense |
| Deribit | warehouse `l2_snapshot_level` | Dense |
| Kraken **spot** | warehouse `l2_rebuild` via `spot\|BTC/USD` / `spot\|ETH/USD` (S3 `mercat-kraken-md` public-md) | **Wired** |
| Kraken **futures** | S3 MRCTCAP1 / public-md: trade/mark/index/funding/OI **only** — no BBO/L2 | Proxies for history; **REST ingest** → `out/kraken_futures_tob/` for live quotes |

Do **not** invent spreads. Futures sealed captures were scanned: message types exclude BBO/L2.

---

## 2. Signal board (Pass 2.6 denser panel)

Pre-registered gates unchanged. Sample: **n_ok=90** venue-days (21d ETH+BTC); **n_mid=73**; **n_quoted=74**.

| ID | Decision | Evidence (headline) |
|----|----------|---------------------|
| `cont.sparse_rv_only` | **Kill** | MC n=500: first_adj RMSE ≈ 0.42× fourth (**unchanged**) |
| `cont.noise_dominates_1s_mid` | **Kill** | calendar fifth/fourth med≪1.5 |
| `cont.noise_trade_clock_bounce` | **Kill** | med≪1.5 |
| `cont.noise_tick_bounce_clock` | **Kill** | CI_lo≰1.5 |
| `cont.noise_mid_clock` | **Hold** | dense mid med=**2.63** CI95=**[1.17, 5.23]** SE=0.97 **n=73** — elevated point, **CI_lo=1.17 < gate 1.5** |
| `cont.tsrv_first_adj` | **Hold** | fragile_rate=0.011; sparse−tsrv adv CI through 0 early∧late; ratio med=1.017 CI=[0.96,1.05]; roll CI_lo>0 frac=**0** |
| `cont.noise_var_fifth` | **Hold** | liquidity proxy; not efficiency |
| `liq.noise_vs_spread` | **Hold** | Pass 2.5: ρ=0.161 CI through 0 (unchanged pending re-join) |
| `frag.xvenue_noise_concord` | **Hold** | level concordance ≠ edge |

**Venue split (mid fifth/fourth medians):** HL 0.78 (n=32) · Deribit 9.29 (n=38) · Kraken spot 1.05 (n=3). Heterogeneity keeps the pooled CI wide.

---

## 3. Pre-registered gates (explicit)

| Claim | Promote only if |
|-------|-----------------|
| `cont.noise_mid_clock` | bootstrap CI_lo of median fifth/fourth **> 1.5** |
| `cont.tsrv_first_adj` | fragile_rate=0 ∧ sparse−tsrv CI_lo>0 on early **and** late time-split ∧ n≥20; **not** on MC alone |
| `cont.sparse_rv_only` | — already **Kill** (MC) |

---

## 4. Remaining honest blockers

1. **Kraken futures historical L2** — not in S3; needs continuous futures book capture in md plane (ingest script covers live REST only).  
2. **Mid-clock Promote** — denser n=73 tightened CI_lo from ~0.83 → **1.17**, still below 1.5; Deribit drives elevation, HL does not.  
3. **Tape TSRV OOS** — not significant; Hold with SE/CI documented. MC Kill of sparse policy still stands.

No Promotes this pass.
