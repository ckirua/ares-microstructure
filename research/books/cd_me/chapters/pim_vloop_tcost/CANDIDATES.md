| id | type | lenses | decision | evidence |
|----|------|--------|----------|----------|
| `risk.pim_cross_venue` | D | risk,liq,mm | **Hold** | Certified **n=9** `panel_core_2venue` (HL↔Deribit real quotes); spot_l2 subpanel n=4; `trade_synth` **QUARANTINED** — monitor only |
| `info.vloop_tcost_commonality` | D | info,liq | **Hold** | median day corr≈**0.94**; pooled hourly r≈**0.62** day-block CI[0.48,0.71] n=98 |
| `info.vloop_tcost_stress_split` | D | info,liq,exec | **Hold** | calm r≈**0.24** vs stress r≈**0.17** (PIM q25/q75); Pass-2.5 on certified panel |
| `info.object_leadlag_map` | D | info,risk,mm | **Hold** | hourly lead-lag vs mid_ret/RV/notional/funding; PIM↔mid_ret weak (best lag≈+2h, pooled r≈−0.13) — map not α |
| `info.kraken_spot_vs_2venue` | D | info,cont,risk | **Hold** | spot_l2=4 / absent_2venue=5; synth quarantined — feed-quality flag |
| `alpha.tob_cross_arb` | T | exec | **Kill** | Detection/monitor ≠ executable arb after fees/latency/inventory |
