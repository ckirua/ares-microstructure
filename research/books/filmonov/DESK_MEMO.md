# Desk memo — Filimonov HFT (Perm Winter School 2013)

**Audience:** crypto MM / SOR / execution / risk / research  
**Source:** Vladimir Filimonov, *High-Frequency Trading. Technology, Strategies, Regulations* (43 slides) → `research/books/filmonov/`  
**Philosophy:** named abuse/latency detector catalog — objects default to **monitor / exec throttle / risk-policy**, not α.  
**Data:** warehouse trades + collector/warehouse TOB on **HL + Deribit + Kraken** — **no ClickHouse MCP**.  
**Program status:** Stats+Bayes dig — **0 Promote / 30 Hold / 11 Kill** (legacy 0/21/11 + 9 info/Bayes Holds).  
**SoT:** [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) · Lib: [`../../lib/hftpat.py`](../../lib/hftpat.py) · Loaders: [`scripts/_data.py`](scripts/_data.py) · Wire-as: [`APPLICATIONS.md`](APPLICATIONS.md) · Money: [`STRATEGY_MONEY.md`](STRATEGY_MONEY.md) · Stats: [`applications/feature_stats/EXP_REPORT.md`](applications/feature_stats/EXP_REPORT.md).

---

## 1. Desk jobs × intended outputs (actionable)

| Job | Concrete output | Metric / plot | Status |
|-----|-----------------|---------------|--------|
| **Storm exec throttle** | Soft-throttle when HL λ_storm posterior / ToD hotspot elevated | `risk.quote_storm_burst` · `info.bayes_storm_rate_venue` · `fig_posterior_storm_rate` | Hold |
| **Fade MM-pull / widen** | Temporary widen when θ_fade↑ **and** IRF Δ>0 sign-stable | `info.bayes_fade_p_posterior` · `info.bayes_widen_given_fade` · IRF forest | Hold |
| **Ignition escalate** | Escalate vs crash when Phase1 unique + markout CI>0 | `info.ignition_markout_1s` · `info.bayes_ignition_rate_venue` | Hold |
| **Storm toxicity strip** | Cut make size only if P(AS\|storm) CrI clear of 0.5 | `info.bayes_adverse_given_storm` · `fig_logit_adverse` | Hold |
| **Size×storm clip** | Clip large aggressive children near storms | `size_storm_interaction` | Hold |
| **Clock / funding monitor** | Algo-hunter z + funding-window excess — no auto-trade | `spoof.clock_cluster` · `info.clock_vs_funding_window` | Hold |
| **Venue-fade SOR defer** | Soft defer far-leg takes; hier θ_fade HL≫DB | `risk.venue_fade_hl_db` · hier fade forest | Hold |
| **OFI/VPIN regime tile** | Same-panel OFI–ret + VPIN with storm rate | `info.ofi_*` · `info.vpin_*` | Hold |
| **Stats/Bayes research layer** | Univariate/dependence/predictive + conjugate posteriors | `out/feature_stats/` · `out/bayes/` · `info_bayes_board.ipynb` | Hold |
| **Vanity Kill list** | Do not ship Hibernia/co-lo/triangle/participant OTR/smoke-α | `id.*` · `spoof.smoke/layer` | Kill |

---

## 2. Signal board (stats + Bayes freeze)

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
| `info.storm_adverse_selection` | storm−placebo markout @1s | yes | no | yes | **Hold** — Δ≈+0.52bps; n=2; not sign-stable |
| `info.storm_markout_1s` | storm event markout | yes | no | yes | **Hold** — ≈0.63bps BH-rej; unstable |
| `info.fade_spread_widen_irf` | Δspread IRF post-fade | yes | no | no | **Hold** — peak≈**−0.11bps** unstable |
| `info.fade_markout_1s` | fade markout @1s | yes | no | no | **Hold** — ≈15.5bps wide CI |
| `info.fade_temp_vs_perm_impact` | 250ms vs 5s markout share | yes | no | no | **Hold** |
| `info.ignition_phase1_unique_mass` | Phase1 outside Nanex/V spans | yes | no | no | **Hold** |
| `info.ignition_markout_1s` | ignition markout @1s | yes | no | no | **Hold** — ≈1.60bps CI[0.97,2.14] |
| `info.clock_vs_funding_window` | clock max_z in/out funding hrs | yes | no | no | **Hold** |
| `info.xvenue_is_around_fade` | Hasbrouck IS @ fade windows | yes | no | no | **Hold** |
| `info.ofi_around_storm_regime` | day OFI–ret corr | yes | no | no | **Hold** |
| `info.vpin_storm_join` | VPIN toxicity join | yes | no | no | **Hold** |
| `info.storm_trade_intensity_burst` | λ_storm / λ_base | yes | no | yes | **Hold** |
| `info.bayes_fade_p_posterior` | Beta θ_fade | yes | no | no | **Hold** — mean≈0.0114 CrI[0.0108,0.0120] |
| `info.bayes_storm_rate_venue` | Gamma λ_storm HL | yes | no | yes | **Hold** — mean≈0.409 CrI[0.316,0.514] |
| `info.bayes_ignition_rate_venue` | Gamma λ_ign | yes | no | no | **Hold** — mean≈6.41 CrI[5.26,7.67] |
| `info.bayes_adverse_given_storm` | Beta P(AS\|storm) | yes | no | yes | **Hold** — mean≈0.43 CrI∋0.5 |
| `info.bayes_widen_given_fade` | Beta P(widen\|fade) | yes | no | no | **Hold** — mean≈0.60 CrI wide |
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

### Numeric headlines (stats+Bayes · ETH+BTC · 4 days · n_native=16)
- **θ_fade (Beta):** mean≈0.0114 CrI95≈[0.0108, 0.0120]; HL hier≈0.018 vs Deribit≈0.002
- **λ_storm HL (Gamma):** mean≈0.409 CrI≈[0.316, 0.514] storms/h
- **λ_ign:** ≈6.41 / day-venue CrI≈[5.26, 7.67]
- **P(AS\|storm):** ≈0.431 CrI≈[0.300, 0.568] — **covers 0.5**
- **P(widen\|fade):** ≈0.60 CrI≈[0.19, 0.93] thin
- **Predictive:** storm AS Δ≈+0.52bps (n=2); ignition markout≈+1.60bps; fade IRF peak **−0.11bps** (unstable vs prior +0.28)
- **BH family (N=6):** some rejects but Promote blocked by thin storm days / instability

**Kill list:** Hibernia/co-lo RTT; fee-free FX triangle; participant OTR; rebadged Nanex/SSM/V as ignition; equity quote-rate vanity; smoke/layer as α; tape-paint cartoon.

**Hold blockers:** storm mass on 09-30; fade IRF sign flip; Kraken synth; P(AS\|storm) CrI∋0.5; need ≥10 complete UTC days.

---

## 3. Venue completeness (stats panel)

| Venue | Role | TOB in slice | Notes |
|-------|------|--------------|-------|
| Hyperliquid | DEX anchor | Yes (collector + l2_rebuild) | densest storm/fade mass |
| Deribit | CEX perps | Yes (warehouse L2) | sparse L2; fade P≪HL |
| Kraken | CEX futures | Synth BBO / empty tape | **excluded** from native fade |

Slice: ETH + BTC days **2026-09-25, 2026-09-26, 2026-09-27, 2026-09-30**.  
**Figures:** `out/feature_stats/figs/` · `out/bayes/figs/` · expand `out/pass2_expand/figs/` · notebook [`notebooks/info_bayes_board.ipynb`](notebooks/info_bayes_board.ipynb).

---

## 4. Next gate (backlog)

1. Native Kraken futures L2 (drop `trade_synth`) for fade/storm joins.  
2. Wider day panel (≥10 complete UTC days) before any Promote revisit.  
3. Storm→ignition lead-lag calibrated + xvenue fade RTT haircut (cross-link mmip).  
4. Nanex threshold sweep so ignition unique_mass is non-vacuous.  
5. Re-test fade IRF sign stability; only then revisit widen-on-fade confidence.  
6. Full `applications/` risk-policy playbooks **only after** a Promote-as-risk-policy freezes (still **0 Promotes**).

**Money / strategy graduates** (maker protect · exec gate · V-fade/MM cross-link — still Hold): [`STRATEGY_MONEY.md`](STRATEGY_MONEY.md).
