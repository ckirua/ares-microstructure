# Desk memo — The Implied Order Book (SqueezeMetrics / GEX Ed. 2020)

**Audience:** crypto MM / SOR / execution / taker / risk / research  
**Source:** SqueezeMetrics (`sqzme`), *The Implied Order Book* (GEX Ed., 6 July 2020) → `research/books/squeeze_metrics/`  
**Philosophy:** lenses `risk | info | exec | disc | cont | liq | mm` — GEX/VEX/GEX+ are **monitors**, not automatically tradable.  
**Data:** Deribit options `implied_vol` + option trades (DDOI proxy); HL+Deribit real TOB/marks; Kraken **spot_l2** when dense — **no ClickHouse MCP**. Warehouse `open_interest` is **futures-only** (quarantined for option DDOI).  
**Program status:** Pass **2b** on certified `panel_gex_options` **n=9** — **0 Promote**. corr(GEX, HL RV)≈**−0.22** (paper sign) but day-block CI crosses 0, chrono range unstable, placebo fails p95, LOO sign-flips → **Hold**.  
**SoT:** [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) · Completeness: [`out/panel_completeness/`](out/panel_completeness/) · Dig: [`out/pass2/`](out/pass2/) · [`out/info_features/`](out/info_features/) · [`out/feature_stats/`](out/feature_stats/) · Use map: [`APPLICATIONS.md`](APPLICATIONS.md) · Lib: [`../../lib/squeeze.py`](../../lib/squeeze.py) · Notebooks: [`notebooks/desk_synthesis.ipynb`](notebooks/desk_synthesis.ipynb) · [`notebooks/info_stats_board.ipynb`](notebooks/info_stats_board.ipynb).  
**Living shadow:** [`applications/paper_shadow/`](applications/paper_shadow/) — GEX/VEX/squeeze monitors (`live_orders=false`); wires **Promote only** (still 0).

---

## 1. Desk jobs × intended outputs

| Job | Paper object | Desk label | Status |
|-----|--------------|------------|--------|
| **Risk monitor** | GEX / VEX / GEX+ | Dealer γ/vanna / squeeze intensity | Hold |
| **Liquidity map** | Abundance / scarce GEX+ | Implied-book scarcity | Hold |
| **Inventory proxy** | DDOI | `PROXY_trade_flow_DDOI` (not verified ΔOI) | Hold |
| **Info dig** | GEX↔RV; lead-lag; markouts; incremental | After-RV ΔR²≈0; descriptive | Hold |
| **SOR / x-venue** | Visible TOB vs implied book | Co-movement only | Hold — never α |
| **Feed quality** | Kraken spot_l2 densify | Policy flag; `trade_synth` **QUARANTINED** | Hold |
| **Vanity Kill** | TOB-cross arb α; synth SoT | Kill | Kill |

---

## 2. Certified panel (real quotes + option IV)

| Panel | n | Days | Def |
|-------|--:|------|-----|
| **Primary** `panel_gex_options` | **9** | 2026-09-14…18, 25–27, 2026-10-01 | HL+Deribit TOB + Deribit ETH option IV |
| Contiguous block | 5 | 2026-09-14 … 18 | densest early window |
| **Secondary** `panel_3venue_spot` | **4** | 2026-09-25, 26, 27, 2026-10-01 | core + dense Kraken **spot_l2** (appendix) |
| `panel_3venue_any` (synth) | **0** | — | **QUARANTINED** |
| BTC widen appendix | **1** pass | 2026-10-01 only | need ≥3 days — **blocked** |

Artifacts: [`out/panel_completeness/certified_panels.json`](out/panel_completeness/certified_panels.json) · [`btc_widen_appendix.json`](out/panel_completeness/btc_widen_appendix.json) · [`widen_probe.json`](out/panel_completeness/widen_probe.json).

---

## 3. Signal board (Pass 2b)

| ID | Formula / clock | Monitor | Tradable | Decision |
|----|-----------------|---------|----------|----------|
| `risk.gex_exposure` | BS γ · trade-flow DDOI · UTC day · ETH | yes | no | **Hold** |
| `risk.vex_exposure` | BS vanna · same DDOI | yes | no | **Hold** |
| `risk.squeeze_intensity` | GEX+ / scarcity | yes | no | **Hold** |
| `liq.implied_book_scarcity` | GEX+ ≤ 0 days (n_scarce=4) | yes | no | **Hold** |
| `info.gex_range_incremental` | partial(range,GEX\|RV)≈0 · ΔR²≈0 | maybe | no | **Hold** |
| `info.squeeze_after_gex` | ΔR²(squeeze\|GEX)≈0 | maybe | no | **Hold** |
| `info.vex_incremental` | ΔR²(VEX\|RV+GEX)≈0 | maybe | no | **Hold** |
| `info.gex_leadlag_map` | day-lag + markout regimes | maybe | no | **Hold** |
| `info.gex_markout_regimes` | scarce/stress vs calm cum mid-ret | maybe | no | **Hold** |
| `info.tod_factor_structure` | ToD RV by regime · day PCA | maybe | no | **Hold** |
| `info.stress_vs_calm` | \|GEX\| / scarce splits | maybe | no | **Hold** |
| `info.object_use_map` | APPLICATIONS routing | yes | no | **Hold** |
| `alpha.tob_cross_arb` | TOB mid gap as sized arb | no | no | **Kill** |
| `data.trade_synth` | Synthetic fills as SoT | no | no | **Kill** |

---

## 4. Key numbers (Pass-2b · certified n=9)

| Claim | Number |
|-------|--------|
| corr(GEX, HL RV) | **−0.216** · day-block CI **[−0.74, +0.59]** crosses 0 |
| corr(GEX, HL range) | **−0.161** · CI crosses 0 |
| chrono GEX↔RV / GEX↔range sign stable | **True** / **False** |
| placebo \|obs\| > null p95 (RV) | **False** |
| venue HL vs DB GEX↔RV sign concordant | **True** |
| LOO corr(GEX,RV) range | **[−0.37, +0.34]** · sign flip any **True** |
| partial(range, GEX \| RV) | **≈0** · ΔR²≈**1e−5** |
| ΔR² VEX after RV+GEX | **≈5e−4** |
| ΔR² squeeze after GEX | **≈4e−4** |
| day-feature PCA PC1 | **0.66** |
| scarce days | 2026-09-18, 25, 26, 2026-10-01 |
| spot_l2 appendix corr(GEX,RV) | −0.38 (n=4) vs absent −0.80 (n=5) |
| DDOI mode | `PROXY_trade_flow_DDOI` |

**Falsifier verdict:** paper sign on pooled GEX↔RV appears, but CI / chrono range / placebo / LOO → **Hold ceiling**. **0 Promote.**

---

## 5. Next gate

1. True option OI / verified DDOI (API snapshot history or warehouse options OI) — Lift Hold blockers.
2. Denser HL collector TOB on more UTC days (BTC widen needs ≥3 gate-passing days; currently **1**).
3. Intraday option-IV refresh for true ToD GEX (today: day GEX × hourly mid markouts).
4. Never soft-Promote; never flip `live_orders`; never resurrect `trade_synth`.
