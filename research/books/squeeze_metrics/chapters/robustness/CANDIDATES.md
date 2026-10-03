| id | type | lenses | decision | evidence |
|----|------|--------|----------|----------|
| `risk.gex_exposure` | D | liq | **Hold** | Falsifiers not run |
| `risk.vex_exposure` | D | liq | **Hold** | Falsifiers not run |
| `risk.squeeze_intensity` | D | liq | **Hold** | Falsifiers not run |
| `liq.implied_book_scarcity` | D | liq | **Hold** | Falsifiers not run |
| `alpha.tob_cross_arb` | T | exec | **Kill** | Pre-registered |
| `data.trade_synth` | D | data | **Kill** | Pre-registered |


## Pass 2b addendum (auto)

- **Panel locked:** `panel_gex_options` ETH **n=9** (2026-09-14…18, 25–27, 2026-10-01). spot_l2 **n=4** appendix only.
- **Falsifiers:** day-block corr(GEX, HL RV)=−0.216 CI[−0.74, +0.59] crosses 0; chrono GEX↔range **unstable**; placebo fails p95; LOO sign flip; HL↔DB venue sign **concordant**.
- **Info dig:** partial(range,GEX|RV)≈0 · ΔR²(GEX|RV)≈0 · ΔR²(VEX|RV+GEX)≈0 · ΔR²(squeeze|GEX)≈0; day PCA PC1≈0.66; scarce={18,25,26,10-01}.
- **Widen:** BTC n_pass=1 (2026-10-01) — blocked (<3). Extra ETH days fail HL collector / marks gates (`out/panel_completeness/widen_probe.json`).
- **Decision:** **0 Promote**. Hold monitors. Kill `alpha.tob_cross_arb`, `data.trade_synth`.
- Artifacts: `out/pass2/` · `out/info_features/` · `out/feature_stats/`.
