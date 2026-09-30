| id | type | lenses | decision | pre-registered gate | evidence |
|----|------|--------|----------|---------------------|----------|
| `cont.tsrv_first_adj` | estimator | cont, risk | **Hold** | fragile_rate=0 ∧ sparse−tsrv CI_lo>0 early∧late ∧ n≥20 | Pass 2.7: fragile_rate=0.015 adv_med=5.58e-07 CI=[-5.95e-07, 3.43e-06] earlyCI_lo>0 lateCI through 0; ratio_med=0.984 CI=[0.963,1.011]; roll_ci_lo_pos_frac=0.07 n=204 |
| `cont.noise_dominates_1s_mid` | diagnostic | cont | **Kill** | CI_lo>1.5 | med=1.006 CI=[0.947,1.065] n=204 |
| `cont.noise_trade_clock_bounce` | diagnostic | cont | **Kill** | CI_lo>1.5 | med=0.815 CI=[0.768,0.853] n=204 |
| `cont.noise_tick_bounce_clock` | diagnostic | cont, info | **Kill** | CI_lo>1.5 | med=1.096 CI=[1.061,1.129] n=203 |
| `cont.noise_mid_clock` | diagnostic | cont | **Hold** | CI_lo>1.5 | Pass 2.7 dense: med=2.449 CI=[1.130,3.777] SE=0.693 **n=122** (CI_lo=1.13<1.5). HL=0.77; Deribit=6.12; Kraken spot=1.13 |
| `cont.sparse_rv_only` | policy | cont | **Kill** | MC first_adj RMSE ≪ fourth | MC Kill unchanged |
