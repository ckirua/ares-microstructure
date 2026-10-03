# EXP_REPORT — gex_implied_book (Pass 1)

**Panel:** `panel_gex_options` **n=9** · 2026-09-14, 2026-09-15, 2026-09-16, 2026-09-17, 2026-09-18, 2026-09-25, 2026-09-26, 2026-09-27, 2026-10-01  
**DDOI:** `PROXY_trade_flow_DDOI` (warehouse option OI absent; futures OI quarantined)  
**IV:** Deribit options `implied_vol` · **S:** Deribit ETH-PERPETUAL mark · **RV join:** HL real TOB  

## Numbers

| Metric | Value |
|--------|------:|
| GEX mean | -8.357e+11 |
| VEX mean | 2.822e+12 |
| GEX+ mean | 1.987e+12 |
| corr(GEX, HL RV) | **-0.216** |
| corr(GEX, HL range) | **-0.161** |
| corr(GEX+, HL range) | 0.271 |

Paper claim direction (higher GEX → tighter vol): **corr(GEX, RV) negative** — matches sign on this panel.

## Decision

**Hold** — monitor only. Units are BS·trade-flow lot-scaled (not paper $/pt SPX). Small n=9.  
**Kill** `alpha.tob_cross_arb`. **0 Promote.**

## Honesty

- Real HL+Deribit TOB only; Kraken spot_l2 secondary (n=4 densest days).
- No trade_synth. ClickHouse MCP banned.
- Crypto GEX can be negative more often than SPX paper stylized fact — report honestly.


## Pass 2b falsifiers (auto)

- **Panel:** panel_gex_options n=9 · DDOI=`PROXY_trade_flow_DDOI`.
- **Day-block corr(GEX, HL RV):** -0.2162754128722743 CI[-0.7386447742588608, 0.5912940092387926].
- **Chrono:** early=['2026-09-14', '2026-09-15', '2026-09-16', '2026-09-17'] late=['2026-09-18', '2026-09-25', '2026-09-26', '2026-09-27', '2026-10-01'] · GEX↔RV stable=True.
- **Placebo shuffle GEX:** exceeds_p95_rv=False.
- **Venue-drop HL vs DB sign concordant:** True.
- **spot_l2:** appendix only (n=4).
- **Decision:** 0 Promote; monitors **Hold**; Kill TOB-cross α / trade_synth.


## Pass 2b addendum (auto)

- **Panel locked:** `panel_gex_options` ETH **n=9** (2026-09-14…18, 25–27, 2026-10-01). spot_l2 **n=4** appendix only.
- **Falsifiers:** day-block corr(GEX, HL RV)=−0.216 CI[−0.74, +0.59] crosses 0; chrono GEX↔range **unstable**; placebo fails p95; LOO sign flip; HL↔DB venue sign **concordant**.
- **Info dig:** partial(range,GEX|RV)≈0 · ΔR²(GEX|RV)≈0 · ΔR²(VEX|RV+GEX)≈0 · ΔR²(squeeze|GEX)≈0; day PCA PC1≈0.66; scarce={18,25,26,10-01}.
- **Widen:** BTC n_pass=1 (2026-10-01) — blocked (<3). Extra ETH days fail HL collector / marks gates (`out/panel_completeness/widen_probe.json`).
- **Decision:** **0 Promote**. Hold monitors. Kill `alpha.tob_cross_arb`, `data.trade_synth`.
- Artifacts: `out/pass2/` · `out/info_features/` · `out/feature_stats/`.
