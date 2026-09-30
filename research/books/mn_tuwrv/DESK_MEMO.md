# Desk memo — Microstructure Noise / TSRV (Romero 2016 · ZMA05)

**Audience:** crypto MM / SOR / execution / taker / risk / research  
**Source:** Romero MA thesis (2016) / ZMA05 TSRV → `research/books/mn_tuwrv/`  
**Data:** warehouse trades + collector/warehouse TOB + Kraken spot L2 + futures REST ingest — **no ClickHouse MCP**  
**Program status:** **Pass 2.7 expand-panel** — **0 Promote**; MC **Kill** sparse stands  
**SoT:** [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) · Lib: [`../../lib/tsrv.py`](../../lib/tsrv.py)  
**Artifacts:** [`out/expand_panel/`](out/expand_panel/) · [`out/blocker_close/`](out/blocker_close/) · [`out/gap_close/`](out/gap_close/)  
**Desk notebooks:** [`notebooks/desk_synthesis.ipynb`](notebooks/desk_synthesis.ipynb) · figs [`out/desk_synthesis/figs/`](out/desk_synthesis/figs/)

---

## 0. Sample expansion (Pass 2.7)

| | Pass 2.5 gap | Pass 2.6 blocker | **Pass 2.7 expand** |
|--|-------------|------------------|---------------------|
| Days | 14 | 21 | **34** (2026-08-28…09-30) |
| Symbols | ETH+BTC | ETH+BTC | **ETH+BTC+SOL** |
| n_ok | 68 | 90 | **204** |
| n_mid (quoted TOB) | 46 | 73 | **122** |
| n_spread join | 57 | — | **144** |

**Data ceiling:** listing caches stop at 34 days for HL/Deribit/Kraken; no older S3 history on this host. Kraken futures historical L2 still absent.

---

## 1. TOB paths

| Venue | Quoted TOB | Expand coverage |
|-------|------------|-----------------|
| Hyperliquid | collector ∪ `l2_rebuild` | n_ok=69 · quoted mid n=33 |
| Deribit | `l2_snapshot_level` | n_ok=102 · mid n=82 |
| Kraken spot | `spot\|*/USD` L2 rebuild | mid n=7 (8 quoted days) |
| Kraken futures | S3: no L2/BBO | proxy n=21 · REST ingest live only |

---

## 2. Signal board (Pass 2.7)

| ID | Decision | Evidence |
|----|----------|----------|
| `cont.sparse_rv_only` | **Kill** | MC first_adj RMSE ≈ 0.42× fourth |
| `cont.noise_dominates_1s_mid` | **Kill** | calendar med=1.006 CI=[0.95,1.06] n=204 |
| `cont.noise_trade_clock_bounce` | **Kill** | med=0.815 CI=[0.77,0.85] n=204 |
| `cont.noise_tick_bounce_clock` | **Kill** | med=1.096 CI=[1.06,1.13] n=203 |
| `cont.noise_mid_clock` | **Hold** | med=**2.45** CI=**[1.13, 3.78]** SE=0.69 **n=122** — CI_lo=1.13 < gate 1.5 |
| `cont.tsrv_first_adj` | **Hold** | overall CI through 0; **early CI_lo>0** but **late CI through 0**; ratio med=0.98; roll CI_lo>0 frac=0.07; n=204 |
| `cont.noise_var_fifth` | **Hold** | liquidity proxy |
| `liq.noise_vs_spread` | **Hold** | ρ=**0.016** CI=[-0.17,0.17] shuffle_p=0.84 n=144 · **same_sign=False** |
| `frag.xvenue_noise_concord` | **Hold** | frac_close=0.63 n_cells=79 |

**Venue mid split:** HL 0.77 (n=33) · Deribit 6.12 (n=82) · Kraken spot 1.13 (n=7).

---

## 3. Pre-registered gates (unchanged)

| Claim | Promote only if |
|-------|-----------------|
| `cont.noise_mid_clock` | CI_lo(fifth/fourth) **> 1.5** |
| `cont.tsrv_first_adj` | fragile_rate=0 ∧ sparse−tsrv CI_lo>0 **early∧late** ∧ n≥20 |
| `liq.noise_vs_spread` | ρ>0 ∧ shuffle p<0.05 ∧ early∧late same sign ∧ CI_lo>0 ∧ n≥20 |

---

## 4. What more data changed

- Mid-clock: n 73→122, SE 0.97→0.69 — **tighter but CI_lo still <1.5** (1.17→1.13).  
- TSRV: early window now clears CI_lo>0; late does **not** → still Hold (gate needs both).  
- noise↔spread: ρ collapsed 0.16→**0.02**; early/late **disagree in sign** → weaker, not Promote.  
- No decision flips to Promote.

---

## 5. Remaining ceilings

1. Listing history ends 2026-08-28 on this host.  
2. Kraken futures historical quoted TOB still missing in S3.  
3. Mid-clock heterogeneity (Deribit vs HL) keeps pooled CI wide.  
4. Tape TSRV late-split still insignificant.
