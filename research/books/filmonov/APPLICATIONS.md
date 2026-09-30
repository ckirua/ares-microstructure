# Applications — Filimonov HFT desk (wire-as playbooks)

**Companion:** [`DESK_MEMO.md`](DESK_MEMO.md) · [`STRATEGY_MONEY.md`](STRATEGY_MONEY.md) · [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) · sibling pattern [`../cross_miniflash/TRADING_APPLICATIONS.md`](../cross_miniflash/TRADING_APPLICATIONS.md)  
**Honesty:** **0 Promote / 30 Hold / 11 Kill** on the stats+Bayes board (legacy 21 Hold + 9 new info/Bayes Holds). Everything below is **monitor → rule sketch → paper**, not greenlit α.  
**Objects default to:** risk-policy · MM quoting · exec throttle — **not** inventable tradable edge.  
**Data:** HL + Deribit + Kraken warehouse/collector; Kraken `trade_synth` excluded from native TOB fade/storm.  
**Stats/Bayes dig:** [`applications/feature_stats/EXP_REPORT.md`](applications/feature_stats/EXP_REPORT.md) · `out/feature_stats/` · `out/bayes/` · [`notebooks/info_bayes_board.ipynb`](notebooks/info_bayes_board.ipynb).  
**Money path:** lose-less / fill-better today — full targets, non-goals, graduates in [`STRATEGY_MONEY.md`](STRATEGY_MONEY.md).

Confidence: **high** = wire as dashboard/gate with known failure modes · **med** = rule sketch needs paper · **low** = research feature only.

---

## Money path / strategy targets

Board still **0 Promote**. Indirect pay = protect maker PnL + exec quality (storm throttle · fade→MM pull · ignition escalate · clock avoid), **not** directional α.  
Not yet: smoke/layer farmer · firm attribution · fade-IRF widen · hard P(AS\|storm) size cut · storm/ignition markouts as taker α.  
Next graduates (need ≥10 days + Promote): maker protect · exec gate · cross-link into V-fade/MM labs.  
Detail: [`STRATEGY_MONEY.md`](STRATEGY_MONEY.md).

---

## 0. Research → desk map (feature → claim → Bayes → wire-as)

| Feature | Statistical claim | Bayesian decision quantity | Wire-as | Feed / clock |
|---------|-------------------|----------------------------|---------|--------------|
| Quote storm burst | storms/h day-block CI; ToD hotspot | λ ~ Gamma posterior (HL ≈0.41 CrI[0.32,0.51]) | **exec throttle** / risk strip | L0 TOB 1s bars · UTC ToD |
| Storm AS | storm−placebo markout Δ | P(AS\|storm) Beta (≈0.43; CrI∋0.5) | **MM size cut** if CrI clear of 0.5 | TOB+trades · 1s markout |
| Price fade P | P(fade)@100ms CI | θ_fade Beta (≈0.0114 CrI tight) | **MM pull / widen monitor** | Native TOB · τ=100ms |
| Fade spread IRF | peak Δspread CI | P(widen\|fade) Beta (≈0.60 wide) | temporary widen sketch | TOB IRF lags 0–2s |
| Fade temp/perm | multi-horizon markout | impact horizon profile | research tile | 250ms vs 5s markout |
| Ignition 3-phase | n/day + markout CI | λ_ign ~ Gamma (≈6.4/day-venue) | **risk escalate** vs crash label | trade bars 1s · Phase1–3 |
| Clock cluster | max_z / funding ratio | — (frequentist monitor) | algo-hunter **monitor only** | trade ts · second-of-minute |
| Venue fade | far depth\|home trade | hier θ by venue (HL≫DB) | soft SOR defer | xvenue TOB · lat-aligned |
| OFI/VPIN join | corr / mean VPIN | — | regime **context tile** | continuous OFI/VPIN (cross-link) |

**Non-goals:** no firm-ID attribution · no tradable α without Promote · no ClickHouse MCP · do not merge crash/vstat/lob APIs.

---

## 1. Risk / kill-switches

### 1.1 Quote-storm exec throttle (Hold)

**Objects:** `risk.quote_storm_burst` · `info.bayes_storm_rate_venue` · figs `out/bayes/figs/fig_posterior_storm_rate.png`, `out/feature_stats/figs/fig_tod_storms.png`

| Layer | Rule sketch | Conf |
|-------|-------------|------|
| Count | Publish HL storms/h with day-block CI **and** Gamma posterior CrI | **high** |
| Throttle | When λ posterior mean enters upper descriptive band / ToD hotspot → slow aggressive children | **med** |
| Escalate | Storm→fade lead-lag hit-rate up → MM pull + size-cap | **med** |

**Falsifiers:** early/late storms flip; DB/KR sparse; feed-sample Hz ≠ OE stuffing; CrI→0 after wider days.

### 1.2 Book-fade MM-pull monitor (Hold)

**Objects:** `risk.price_fade_p` · `info.bayes_fade_p_posterior` · `info.fade_spread_widen_irf` · `info.bayes_widen_given_fade`

| Layer | Rule sketch | Conf |
|-------|-------------|------|
| Monitor | Track θ_fade posterior mean+CrI; flag venue hierarchy HL≫DB | **high** |
| Quote | On fade cluster + positive stable IRF → temporary widen / cut size | **low**→**med** (IRF sign **unstable** this dig) |
| Gate | Exclude Kraken synth; lob-cancel rename gate must stay non-kill_rename | **high** |

### 1.3 Ignition escalate-vs-crash (Hold)

**Objects:** `risk.momentum_ignition_3phase` · `info.ignition_markout_1s` · `info.bayes_ignition_rate_venue`

| Layer | Rule sketch | Conf |
|-------|-------------|------|
| Label | Tag 3-phase events separately from Nanex/SSM/V on risk strip | **high** |
| Escalate | Only when Phase1 unique_mass material **and** markout CI clear of 0 | **med** |
| Do not | Rebadge Nanex/V as ignition (`id.rebadge_nanex_as_ignition` **Kill**) | **high** |

### 1.4 Storm adverse-selection strip (Hold)

**Objects:** `info.storm_adverse_selection` · `info.bayes_adverse_given_storm` · fig `out/bayes/figs/fig_logit_adverse.png`

| Layer | Rule sketch | Conf |
|-------|-------------|------|
| Toxicity | Compare storm-window markout vs placebo; Beta P(AS\|storm) | **med** |
| Action | Cut make size only if P(AS\|storm) CrI clear of 0.5 (**not yet**) | **low** |

---

## 2. Execution / SOR

### 2.1 Size × storm interaction (Hold)

**Objects:** size×storm helper · fig `out/pass2_expand/figs/fig_size_storm_interaction.png`

| Use | Conf |
|-----|------|
| If top size-quantile prints show elevated P(near storm) → clip large aggressive children in storm regimes | **med** |
| TCA: bucket slippage by size-q × storm flag | **med** |

### 2.2 Clock / funding alignment (Hold)

**Objects:** `spoof.clock_cluster` · `info.clock_vs_funding_window`

| Use | Conf |
|-----|------|
| Algo-hunter monitor: second-of-minute excess z | **high** |
| Compare excess inside vs outside funding hours — do not auto-trade the clock | **med** |

### 2.3 Venue-fade SOR haircut (Hold)

**Objects:** `risk.venue_fade_hl_db` · `info.xvenue_is_around_fade` · hier fade venue posteriors

| Use | Conf |
|-----|------|
| Far-venue depth drop \| home trade = soft SOR defer (RTT haircut not Promote-ready) | **med** |
| Hasbrouck IS around fade = research info share, **not** arb | **low** |

---

## 3. Market making

### 3.1 Widen / pull on fade + storm (Hold)

| Trigger | Action sketch | Conf |
|---------|---------------|------|
| Rising HL λ_storm + fade IRF Δspread>0 **and** sign-stable | Widen; cut size; skew flat | **low** (IRF unstable) |
| Ignition with high unique_mass + markout CI>0 | Protect / pull faster than soft widen | **med** |
| Smoke/layer proxies | **Do not wire** (FP≈1.79 Kill) | **high** |

### 3.2 OFI / VPIN regime joins (Hold)

**Objects:** `info.ofi_around_storm_regime` · `info.vpin_storm_join`

| Use | Conf |
|-----|------|
| Show OFI–ret corr + VPIN on same panel as storm rate (regime context) | **high** |
| Do not treat as standalone α | **high** |

---

## 4. Research / taxonomy

| Object | Wire-as | Conf |
|--------|---------|------|
| `disc.hft_taxonomy_tile` / `disc.sec_attr_crypto_map` | Reading-order + crypto attr map on desk wiki | **high** |
| `mm.size_latency_regime_panel` | Feed-sample TOB Hz regime tile (label **not** OE µs) | **high** |
| Feature stats + Bayes dig | Desk research layer (`applications/feature_stats/`) | **high** |
| Hibernia / co-lo / fee-free triangle / participant OTR | **Kill** — do not ship | **high** |

---

## 5. Thin applications/

[`applications/feature_stats/EXP_REPORT.md`](applications/feature_stats/EXP_REPORT.md) — presentability for stats/Bayes dig. Full risk-policy playbooks only after a **Promote-as-risk-policy** freezes (still **0 Promotes**).

---

## 6. Day-completeness (stats panel)

| Symbol | Venue | Days complete (trades) | Native TOB fade/storm |
|--------|-------|------------------------|------------------------|
| ETH/BTC | Hyperliquid | 2026-09-25/26/27/30 | Yes (collector/warehouse) |
| ETH/BTC | Deribit | same | Yes (sparse L2) |
| ETH/BTC | Kraken | tape often empty / synth BBO | **Excluded** from native fade |

**Bayes headlines:** θ_fade≈0.0114 CrI[0.0108,0.0120]; λ_storm HL≈0.409; P(AS\|storm)≈0.43 CrI∋0.5; P(widen\|fade)≈0.60 wide.  
**Frequentist:** storm AS Δ≈+0.52bps (n=2); ignition markout≈+1.6bps; fade IRF peak **−0.11bps** (unstable).
