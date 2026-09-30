# Desk memo — Filimonov HFT (Perm Winter School 2013)

**Audience:** crypto MM / SOR / execution / risk / research  
**Source:** Vladimir Filimonov, *High-Frequency Trading. Technology, Strategies, Regulations* (43 slides) → `research/books/filmonov/`  
**Philosophy:** named abuse/latency detector catalog — objects default to **monitor / exec throttle / risk-policy**, not α.  
**Data:** warehouse trades + collector/warehouse TOB on **HL + Deribit + Kraken** — **no ClickHouse MCP**.  
**Program status:** Pass-2 expand — **0 Promote / 21 Hold / 11 Kill** (legacy freeze 0/13/11 + 8 info Holds).  
**SoT:** [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) · Lib: [`../../lib/hftpat.py`](../../lib/hftpat.py) · Loaders: [`scripts/_data.py`](scripts/_data.py) · Wire-as: [`APPLICATIONS.md`](APPLICATIONS.md).

---

## 1. Desk jobs × intended outputs (actionable)

| Job | Concrete output | Metric / plot | Status |
|-----|-----------------|---------------|--------|
| **Storm exec throttle** | Soft-throttle aggressive children when HL storms/h enters upper day-block CI or ToD hotspot | `risk.quote_storm_burst` · `fig_boot_hist_storms` · `fig_tod_heatmap_storms` · lead-lag cascade | Hold |
| **Fade MM-pull / widen** | Temporary widen + size cut when P(fade)↑ and fade→spread IRF Δ>0 | `risk.price_fade_p` · `info.fade_spread_widen_irf` · `fig_fade_tau_sensitivity` · `fig_info_fade_spread_irf` | Hold |
| **Ignition escalate** | Escalate risk strip vs plain crash **only** when Phase1 unique-mass material (not Nanex rename) | `risk.momentum_ignition_3phase` · `info.ignition_phase1_unique_mass` · `fig_info_ignition_unique_mass` | Hold |
| **Storm toxicity strip** | Storm-window markout vs placebo → cut make size if Δ persistently >0 | `info.storm_adverse_selection` · `fig_info_storm_as` | Hold |
| **Size×storm clip** | Clip large aggressive children when top size-q near-storm rate elevated | `size_storm_interaction` · `fig_size_storm_interaction` | Hold |
| **Clock / funding monitor** | Algo-hunter z + funding-window excess ratio (0/8/16 UTC ±5m) — no auto-trade | `spoof.clock_cluster` · `info.clock_vs_funding_window` · `fig_info_clock_funding` | Hold |
| **Venue-fade SOR defer** | Soft defer far-leg takes when home-trade→far depth fade; RTT haircut later | `risk.venue_fade_hl_db` · `info.xvenue_is_around_fade` | Hold |
| **OFI/VPIN regime tile** | Same-panel OFI–ret corr + VPIN with storm rate (context, not α) | `info.ofi_around_storm_regime` · `info.vpin_storm_join` · `fig_info_ofi_vpin` | Hold |
| **Taxonomy / latency regime** | Desk wiki reading order + feed-sample TOB Hz tile (label ≠ OE µs) | `disc.*` · `mm.size_latency_regime_panel` | Hold |
| **Vanity Kill list** | Do not ship Hibernia/co-lo/triangle/participant OTR/smoke-α | `id.*` · `spoof.smoke/layer` | Kill |

---

## 2. Signal board (Pass-2.5 freeze + expand info)

| ID | Formula / clock | Monitor | Tradable | Exec throttle | Decision |
|----|-----------------|---------|----------|---------------|----------|
| `disc.hft_taxonomy_tile` | SEC/strategy taxonomy · framing | yes | no | no | **Hold** |
| `disc.sec_attr_crypto_map` | SEC attrs → crypto map | yes | no | no | **Hold** |
| `mm.size_latency_regime_panel` | TOB Hz + size quantiles (feed-sample) | yes | no | no | **Hold** |
| `mm.trade_size_quantile_curve` | trade-size quantile curve | yes | no | no | **Hold** |
| `risk.fade_vs_lob_cancel` | fade ∩ lob cancel_proxy | yes | no | no | **Hold** |
| `risk.ignition_vs_nanex_vshape` | ignition ∩ Nanex/V/SSM | yes | no | no | **Hold** |
| `risk.momentum_ignition_3phase` | vol↑→move→partial recovery | yes | no | no | **Hold** |
| `risk.price_fade_p` | P(same-side depth↓\|agg) @100ms | yes | no | no | **Hold** |
| `risk.quote_storm_burst` | stuffing burst Hz z≥3 · 1s bars | yes | no | yes | **Hold** |
| `risk.quote_storm_vs_lob` | storm ∩ lob cancel_proxy | yes | no | no | **Hold** |
| `risk.venue_fade_hl_db` | far-venue depth\|home trade | yes | no | maybe | **Hold** |
| `spoof.clock_cluster` | second-of-minute excess z | yes | no | no | **Hold** |
| `spoof.otr_venue` | venue cancel_proxy/trade | policy | no | no | **Hold** |
| `info.storm_adverse_selection` | storm−placebo markout @1s | yes | no | yes | **Hold** — n=1 storm-day; Δ≈−0.07bps |
| `info.fade_spread_widen_irf` | Δspread IRF post-fade | yes | no | no | **Hold** — peak Δ≈0.28bps |
| `info.ignition_phase1_unique_mass` | Phase1 outside Nanex/V spans | yes | no | no | **Hold** — uniq≈1.0 (vacuous if Nanex n=0 @default %) |
| `info.clock_vs_funding_window` | clock max_z in/out funding hrs | yes | no | no | **Hold** — ratio≈0.57 |
| `info.xvenue_is_around_fade` | Hasbrouck IS @ fade windows | yes | no | no | **Hold** — sparse IS / research-only |
| `info.ofi_around_storm_regime` | day OFI–ret corr | yes | no | no | **Hold** — corr≈0.42 |
| `info.vpin_storm_join` | VPIN toxicity join | yes | no | no | **Hold** — mean VPIN≈0.58 |
| `info.storm_trade_intensity_burst` | λ_storm / λ_base | yes | no | yes | **Hold** — ratio≈1.69 |
| `id.colo_hibernia_vanity` | co-lo / Hibernia vanity | no | no | no | **Kill** |
| `id.colo_rtt_40us_claim` | NASDAQ <40–50µs | no | no | no | **Kill** |
| `id.equity_quote_rate_vanity` | equity quote-rate vanity | no | no | no | **Kill** |
| `id.fiber_distance_table` | NY–Chicago fiber | no | no | no | **Kill** |
| `id.fx_triangle_fee_free` | fee-free FX triangle | no | no | no | **Kill** |
| `id.hibernia_express_6ms` | Hibernia −6ms | no | no | no | **Kill** |
| `id.participant_otr` | firm-ID OTR | no | no | no | **Kill** |
| `id.rebadge_nanex_as_ignition` | Nanex-as-ignition rename | no | no | no | **Kill** |
| `spoof.layer_proxy` | away-from-touch cancel w/o trade | no | no | no | **Kill** |
| `spoof.smoke_proxy` | attractive→cancel→worse fill | no | no | no | **Kill** |
| `spoof.tape_paint` | equity tape-paint cartoon | no | no | no | **Kill** |

### Numeric headlines (expand panel ETH+BTC · 4 days)
- **Quote storms (HL ETH):** storms/h point≈0.391 CI95≈[0.0, 1.17] n=4 (mass on 2026-09-30); BTC HL similar
- **Price fade (HL ETH):** P(fade)@100ms point≈0.017 CI95≈[0.006, 0.039] n=4; Kraken synth excluded
- **Ignition (HL ETH):** n/day point≈7.25 CI95≈[2.6, 12.8]; crypto-relaxed 3-phase params
- **Info dig:** fade IRF peak Δspread≈0.28bps; OFI–ret≈0.42; VPIN≈0.58; storm λ ratio≈1.69; clock funding ratio≈0.57
- **Latency panel:** TOB Hz is **feed-sample** (not OE µs) — Kill Hibernia/co-lo vanity

**Kill list:** Hibernia/co-lo RTT; fee-free FX triangle; participant OTR; rebadged Nanex/SSM/V as ignition; equity quote-rate vanity; smoke/layer as α; tape-paint cartoon.

**Hold blockers:** sparse TOB outside HL; Kraken synth/empty tape; storm days concentrated on 09-30; ignition unique_mass vacuous when Nanex n=0; xvenue IS thin; BTC Deribit 09-30 storms/h outlier (sparse L2 z-score).

---

## 3. Venue completeness (expand)

| Venue | Role | TOB in slice | Notes |
|-------|------|--------------|-------|
| Hyperliquid | DEX anchor | Yes (collector + l2_rebuild) | densest storm/fade mass |
| Deribit | CEX perps | Yes (warehouse L2) | sparse L2; fade P≪HL; BTC 09-30 storm outlier |
| Kraken | CEX futures | Synth BBO / empty tape on panel | **excluded** from native fade; OTR meaningless |

Slice: ETH + BTC days **2026-09-25, 2026-09-26, 2026-09-27, 2026-09-30** (adds 09-25 vs Pass-2.5 freeze).  
Early=['2026-09-25','2026-09-26'] late=['2026-09-27','2026-09-30'].  
HL+DB trade-complete on all four; Kraken tape empty on this warehouse pull.

**Figures:** `out/<pkg>/figs/` · Pass2 `out/pass2/figs/` · expand `out/pass2_expand/figs/` · board `signal_board.png` · desk [`notebooks/desk_synthesis.ipynb`](notebooks/desk_synthesis.ipynb).

---

## 4. Next gate (backlog)

1. Native Kraken futures L2 (drop `trade_synth`) for fade/storm joins.  
2. Wider day panel (≥10 complete UTC days) before any Promote revisit.  
3. Storm→ignition lead-lag calibrated + xvenue fade RTT haircut (cross-link mmip).  
4. Nanex threshold sweep so ignition unique_mass is non-vacuous.  
5. `applications/` risk-policy playbooks **only after** a Promote-as-risk-policy freezes (still **0 Promotes**).
