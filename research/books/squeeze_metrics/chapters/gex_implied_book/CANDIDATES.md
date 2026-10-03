| id | type | lenses | decision | evidence |
|----|------|--------|----------|----------|
| `risk.gex_exposure` | D | liq,mm,risk | **Hold** | n=9; corr(GEX,HL RV)=−0.22; chrono unstable; CI crosses 0 |
| `liq.gex_rv_link` | D | liq | **Hold** | Paper sign present; falsifiers fail Promote bar |
| `risk.vex_exposure` | D | liq,risk | **Hold** | VEX mean>0 panel; corr(VEX,range)=+0.42 CI wide |
| `risk.squeeze_intensity` | D | risk,liq | **Hold** | GEX+ scarce n=4/9 |
| `info.gex_range_incremental` | D | info | **Hold** | partial≈0 after RV |
| `alpha.tob_cross_arb` | T | exec | **Kill** | Co-movement ≠ arb |


## Pass 2b addendum (auto)

- **Panel locked:** `panel_gex_options` ETH **n=9** (2026-09-14…18, 25–27, 2026-10-01). spot_l2 **n=4** appendix only.
- **Falsifiers:** day-block corr(GEX, HL RV)=−0.216 CI[−0.74, +0.59] crosses 0; chrono GEX↔range **unstable**; placebo fails p95; LOO sign flip; HL↔DB venue sign **concordant**.
- **Info dig:** partial(range,GEX|RV)≈0 · ΔR²(GEX|RV)≈0 · ΔR²(VEX|RV+GEX)≈0 · ΔR²(squeeze|GEX)≈0; day PCA PC1≈0.66; scarce={18,25,26,10-01}.
- **Widen:** BTC n_pass=1 (2026-10-01) — blocked (<3). Extra ETH days fail HL collector / marks gates (`out/panel_completeness/widen_probe.json`).
- **Decision:** **0 Promote**. Hold monitors. Kill `alpha.tob_cross_arb`, `data.trade_synth`.
- Artifacts: `out/pass2/` · `out/info_features/` · `out/feature_stats/`.
