# Desk memo — Constrained Dealers and Market Efficiency (Huang et al. 2021)

**Audience:** crypto MM / SOR / execution / taker / risk / research  
**Source:** Huang–Ranaldo–Schrimpf–Somogyi (Nov 2021, SSRN 3960577) → `research/books/cd_me/`  
**Philosophy:** lenses `risk | info | exec | disc | cont | liq | mm` — PIM/DCM objects are **monitors**, not automatically tradable.  
**Data:** warehouse trades + marks + collector/warehouse TOB on **HL + Deribit** (primary); Kraken **spot_l2 only** when dense — **no ClickHouse MCP**.  
**Program status:** Pass **2.5** info/stats on **certified real-quote panel** — **0 Promote**. Retracted prior “10/10 three-venue + trade_synth.” Primary `panel_core_2venue` **n=9**; spot_l2 subpanel **n=4**; elasticity pooled **−0.46** (n=88); DCM incremental after RV **Hold** (partial r≈0.38, ΔR²≈0.15).  
**SoT:** [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) · Completeness: [`out/panel_completeness/`](out/panel_completeness/) · Use map: [`APPLICATIONS.md`](APPLICATIONS.md) · Lib: [`../../lib/cdme.py`](../../lib/cdme.py) · Loaders: [`scripts/_data.py`](scripts/_data.py) · Notebooks: [`notebooks/desk_synthesis.ipynb`](notebooks/desk_synthesis.ipynb) · [`notebooks/info_stats_board.ipynb`](notebooks/info_stats_board.ipynb).  
**Living shadow:** [`applications/paper_shadow/`](applications/paper_shadow/) — PIM/DCM monitors (`live_orders=false`); wires **Promote only** (still 0).

---

## 1. Desk jobs × intended outputs

| Job | Paper object | Tentative desk label | Status |
|-----|--------------|----------------------|--------|
| **Risk monitor** | PIM / DCM̂ regime | Monitor — dealer-constraint / LOP-stress days | Hold |
| **Liquidity elasticity** | corr(VLM, PIM) ± RV control | Monitor — survives RV (partial≈−0.46) | Hold |
| **Toxicity / info** | VLOOP vs TCOST; lead-lag map | Info join (stress vs calm) | Hold |
| **SOR / x-venue** | Cross-venue LOP gap HL↔DB (+ KR spot when dense) | Fragmentation / thin-venue concentration | Hold — 2-venue primary |
| **Feed quality** | Kraken spot_l2 vs absent_2venue | Policy flag; `trade_synth` **QUARANTINED** | Hold |
| **Vanity Kill** | Bank VaR / CDS; TOB arb α | Kill | Kill |

---

## 2. Certified panel (real quotes only)

| Panel | n | Days | Def |
|-------|--:|------|-----|
| **Primary** `panel_core_2venue` | **9** | 2026-09-14…18, 25–27, 2026-10-01 | HL TOB + Deribit TOB (Kraken optional absent) |
| Contiguous block | 5 | 2026-09-14 … 2026-09-18 | densest HL↔DB window |
| **Secondary** `panel_3venue_spot` | **4** | 2026-09-25, 26, 27, 2026-10-01 | core + dense Kraken **spot_l2 only** |
| `panel_3venue_any` (synth) | **0** | — | **QUARANTINED** — do not certify |

**Excluded:** 2026-09-19 (PIM n_finite=0 after 2v re-run); 20–24 (missing/thin HL and/or Deribit TOB); 28 (thin HL; KR spot n=6); 29 (DCM n_valid=77<200); 30 (Deribit TOB n=235<500).

**Retracted:** “10/10 three-venue PIM” that counted Kraken `trade_synth` as a third venue on 09-14…18. Synth = **PROXY / NOT TOB** — never primary.

Artifacts: [`out/panel_completeness/certified_panels.json`](out/panel_completeness/certified_panels.json) · [`REPORT.md`](out/panel_completeness/REPORT.md).

---

## 3. Signal board (Pass 2 + 2.5 on certified panel)

| ID | Formula / clock | Monitor | Tradable | Exec throttle | Decision |
|----|-----------------|---------|----------|---------------|----------|
| `risk.pim_cross_venue` | PIM = VLOOP+\|TCOST\| · UTC hour/day · ETH | yes | no | maybe | **Hold** |
| `risk.dcm_pc1` | PC1(\|fund\|, \|basis\|, RV, imb) | yes | no | maybe | **Hold** |
| `liq.elasticity_regime` | corr(VLM, PIM) by DCM quantile | yes | no | maybe | **Hold** −0.46 [−0.57,−0.35] |
| `info.vloop_tcost_commonality` | corr(VLOOP, TCOST) | maybe | no | no | **Hold** pooled ≈0.62 |
| `info.vloop_tcost_stress_split` | corr calm vs stress PIM | maybe | no | maybe | **Hold** 0.24 vs 0.17 |
| `info.pim_dcm_incremental` | partial(PIM,DCM\|RV) / ΔR² | yes | no | no | **Hold** partial≈0.38 ΔR²≈0.15 |
| `info.elasticity_after_rv` | partial(PIM,VLM\|RV) | yes | no | maybe | **Hold** partial≈−0.46 |
| `info.object_leadlag_map` | hourly xcorr vs mid_ret/RV/… | maybe | no | no | **Hold** descriptive |
| `info.kraken_spot_vs_2venue` | spot_l2 vs absent_2venue | yes | no | no | **Hold** feed flag |
| `info.day_factor_commonality` | day / ToD PCA | maybe | no | no | **Hold** PC1≈0.995 / 0.42 |
| `info.object_use_map` | APPLICATIONS routing | yes | no | no | **Hold** |
| `alpha.tob_cross_arb` | TOB mid gap as sized arb | no | no | no | **Kill** |
| `risk.bank_cds_var` | Equity CDS / VaR vanity | no | no | no | **Kill** |

**Kill list:** TOB-cross as sized arb α; bank VaR/CDS vanity.  
**Hold blockers:** True Kraken futures quoted TOB; denser DCM joint hours; never resurrect `trade_synth` into primary.

---

## 4. Info board — key statistical findings (certified n=9)

| Claim | Number |
|-------|--------|
| corr(VLOOP,TCOST) day-block | **0.62** CI[**0.48**, **0.71**] n=98 |
| corr(PIM,VLM) day-block / pooled | **−0.46** CI[**−0.54**, **−0.38**] n=88 |
| elasticity pooled (Pass-2) | **−0.46** CI[**−0.57**, **−0.35**] n=88 · 8 days |
| partial(PIM,DCM \| RV) | **0.38** (n=59) · ΔR² **0.15** |
| partial(PIM,VLM \| RV) | **−0.46** (n=66) · ΔR² **0.20** |
| VLOOP↔TCOST calm / stress | **0.24** / **0.17** |
| PIM day-mean CI (9d block) | **0.022** [**0.016**, **0.027**] |
| Day-feature PCA PC1 | **0.995** explained |
| PIM ToD PCA PC1 | **0.42** explained |
| PIM↔mid_ret lead-lag (pooled) | best lag **+2h**, r≈**−0.13** (weak) |
| Fisher-z Bayes PIM↔VLM CrI | [**−0.61**, **−0.28**] (descriptive) |

Artifacts: `out/info_features/` · `out/feature_stats/` · notebook `notebooks/info_stats_board.ipynb`.

---

## 5. Venue completeness (locked)

| Venue | Role | Symbol examples | Certified TOB |
|-------|------|-----------------|---------------|
| Hyperliquid | DEX anchor / home VLM | `ETH`, `BTC` | usable (sparse coverage ~4–12% of 5s grid) |
| Deribit | CEX perps | `ETH-PERPETUAL` | usable (coverage day-dependent) |
| Kraken | CEX spot L2 only | `spot\|ETH/USD` | **4/9** primary days with dense `spot_l2`; else **2-venue** |
| Kraken futures synth | PROXY / NOT TOB | `PF_ETHUSD` trade_synth | **QUARANTINED** — appendix only |

Incomplete UTC days → excluded in `out/panel_completeness/`; do not Promote on thin tails alone.

---

## 6. Next gate

1. Kraken **futures quoted** history via `mn_tuwrv/scripts/ingest_kraken_futures_tob.py`.
2. Prefer true funding rate series over `funding_proxy`.
3. Venue-drop ablation (Deribit off) on spot_l2 subpanel; denser DCM hours.
4. **BTC widen** of info dig — Hold as next step (ETH certified panel first).
5. Never soft-Promote Holds; never flip `live_orders`; never resurrect `trade_synth` into primary.

---

## 7. Honesty

- Scoreboard = monitor telemetry — **not** PnL alpha
- `live_orders=False` · ClickHouse MCP banned · warehouse + startarb only
- Detection of LOP gaps ≠ executable arb after fees / latency / inventory
- Negative pooled corr(VLM,PIM) reported honestly — not forced to match FX paper sign
- Pass-2.5 Bayes / partials are **descriptive** — do not invent α
- `trade_synth ≠ quoted TOB` — retracted from primary; `has_synth=false` on certified PIM outs
