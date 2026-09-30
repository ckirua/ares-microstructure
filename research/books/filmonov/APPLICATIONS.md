# Applications — Filimonov HFT desk (wire-as playbooks)

**Companion:** [`DESK_MEMO.md`](DESK_MEMO.md) · [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) · sibling pattern [`../cross_miniflash/TRADING_APPLICATIONS.md`](../cross_miniflash/TRADING_APPLICATIONS.md)  
**Honesty:** **0 Promote / 21 Hold / 11 Kill** on the expand board. Everything below is **monitor → rule sketch → paper**, not greenlit α.  
**Objects default to:** risk-policy · MM quoting · exec throttle — **not** inventable tradable edge.  
**Data:** HL + Deribit + Kraken warehouse/collector; Kraken `trade_synth` excluded from native TOB fade/storm.

Confidence: **high** = wire as dashboard/gate with known failure modes · **med** = rule sketch needs paper · **low** = research feature only.

---

## 1. Risk / kill-switches

### 1.1 Quote-storm exec throttle (Hold)

**Objects:** `risk.quote_storm_burst` · figs `out/pass2_expand/figs/fig_boot_hist_storms.png`, `fig_tod_heatmap_storms.png`, `fig_lead_lag_cascade.png`

| Layer | Rule sketch | Conf |
|-------|-------------|------|
| Count | Publish HL storms/h with day-block CI (never a point alone) | **high** |
| Throttle | When storms/h rises into upper CI / ToD hotspot → slow aggressive child orders; widen IOC timeout | **med** |
| Escalate | Storm→fade / storm→ignition lead-lag hit-rate up → escalate to MM pull + size-cap | **med** |

**Falsifiers:** early/late storms flip; DB/KR sparse; feed-sample Hz ≠ OE stuffing.

### 1.2 Book-fade MM-pull monitor (Hold)

**Objects:** `risk.price_fade_p` · `info.fade_spread_widen_irf` · figs `fig_fade_tau_sensitivity.png`, `fig_info_fade_spread_irf.png`

| Layer | Rule sketch | Conf |
|-------|-------------|------|
| Monitor | Track P(fade)@100ms + τ-curve; flag when late-day P ≫ early | **high** |
| Quote | On fade cluster + positive spread IRF → temporary widen / cut size | **med** |
| Gate | Exclude Kraken synth; lob-cancel rename gate must stay non-kill_rename | **high** |

### 1.3 Ignition escalate-vs-crash (Hold)

**Objects:** `risk.momentum_ignition_3phase` · `info.ignition_phase1_unique_mass` · fig `fig_info_ignition_unique_mass.png`

| Layer | Rule sketch | Conf |
|-------|-------------|------|
| Label | Tag 3-phase events separately from Nanex/SSM/V on risk strip | **high** |
| Escalate | Only escalate when Phase1 unique_mass is material (not rename) | **med** |
| Do not | Rebadge Nanex/V as ignition (`id.rebadge_nanex_as_ignition` **Kill**) | **high** |

### 1.4 Storm adverse-selection strip (Hold)

**Objects:** `info.storm_adverse_selection` · fig `fig_info_storm_as.png`

| Layer | Rule sketch | Conf |
|-------|-------------|------|
| Toxicity | Compare storm-window markout vs placebo timestamps | **med** |
| Action | If storm−placebo Δmarkout persistently >0 → cut make size in storm bars | **low**→**med** after wider days |

---

## 2. Execution / SOR

### 2.1 Size × storm interaction (Hold)

**Objects:** size×storm helper · fig `fig_size_storm_interaction.png`

| Use | Conf |
|-----|------|
| If top size-quantile prints show elevated P(near storm) → clip large aggressive children in storm regimes | **med** |
| TCA: bucket slippage by size-q × storm flag | **med** |

### 2.2 Clock / funding alignment (Hold)

**Objects:** `spoof.clock_cluster` · `info.clock_vs_funding_window` · fig `fig_info_clock_funding.png`

| Use | Conf |
|-----|------|
| Algo-hunter monitor: second-of-minute excess z | **high** |
| Compare excess inside vs outside funding hours (0/8/16 UTC ±5m) — do not auto-trade the clock | **med** |

### 2.3 Venue-fade SOR haircut (Hold)

**Objects:** `risk.venue_fade_hl_db` · `info.xvenue_is_around_fade`

| Use | Conf |
|-----|------|
| Far-venue depth drop | home trade = soft SOR defer (RTT haircut not Promote-ready) | **med** |
| Hasbrouck IS around fade = research info share, **not** arb | **low** |

---

## 3. Market making

### 3.1 Widen / pull on fade + storm (Hold → med)

| Trigger | Action sketch | Conf |
|---------|---------------|------|
| Rising HL storms/h + fade IRF Δspread>0 | Widen; cut size; skew flat | **med** |
| Ignition with high unique_mass | Protect / pull faster than soft widen | **med** |
| Smoke/layer proxies | **Do not wire** (FP≈1.79 Kill) | **high** |

### 3.2 OFI / VPIN regime joins (Hold)

**Objects:** `info.ofi_around_storm_regime` · `info.vpin_storm_join` · fig `fig_info_ofi_vpin.png`

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
| Hibernia / co-lo / fee-free triangle / participant OTR | **Kill** — do not ship | **high** |

---

## 5. Optional thin applications/

Only stand up `applications/<playbook>/` after a **Promote-as-risk-policy** freezes. Current expand keeps playbooks in this doc + desk notebooks. Sibling notebooks to mirror later (if Promote): risk-policy throttle, MM quoting widen, exec size-cap — parity light with cross_miniflash `applications/`.

---

## 6. Day-completeness (expand panel)

| Symbol | Venue | Days complete (trades) | Native TOB fade/storm |
|--------|-------|------------------------|------------------------|
| ETH/BTC | Hyperliquid | 2026-09-25/26/27/30 | Yes (collector/warehouse) |
| ETH/BTC | Deribit | same | Yes (sparse L2) |
| ETH/BTC | Kraken | tape often empty / synth BBO | **Excluded** from native fade |

Pass-2.5 freeze used 26/27/30; expand adds **2026-09-25**. Coverage ~0.5 on complete days (warehouse span filter).

**Expand headlines (HL ETH):** storms/h≈0.391 CI[0,1.17]; P(fade)≈0.017 CI[0.006,0.039]; n_ign/day≈7.25; fade IRF peak Δspread≈0.28bps; OFI–ret≈0.42; VPIN≈0.58; storm λ ratio≈1.69.
