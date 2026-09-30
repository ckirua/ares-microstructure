| id | type | lenses | decision | pre-registered gate | evidence |
|----|------|--------|----------|---------------------|----------|
| `cont.tsrv_first_adj` | estimator | cont, risk | **Hold** | fragile_rate=0 ∧ sparse−tsrv CI_lo>0 early∧late ∧ n≥20; not MC alone | Pass 2.6: fragile_rate=0.011 adv_med=-2.75e-07 CI=[-2.31e-06, 1.17e-06] SE=8.3e-07 earlyCI through 0 lateCI through 0; ratio_med=1.017 CI=[0.959,1.052]; roll_ci_lo_pos_frac=0.00 n=90 |
| `cont.noise_dominates_1s_mid` | diagnostic | cont | **Kill** | median fifth/fourth CI_lo>1.5 | calendar med≪1.5 (Pass 2.5/2.6) |
| `cont.noise_trade_clock_bounce` | diagnostic | cont | **Kill** | CI_lo>1.5 | med≪1.5 |
| `cont.noise_tick_bounce_clock` | diagnostic | cont, info | **Kill** | CI_lo>1.5 | med≈1.01 CI_lo≰1.5 |
| `cont.noise_mid_clock` | diagnostic | cont | **Hold** | CI_lo>1.5 | Pass 2.6 dense: med=2.628 CI=[1.172, 5.225] SE=0.971 **n=73** (CI_lo=1.17<1.5). HL med=0.78; Deribit med=9.29; Kraken spot med=1.05 |
| `cont.sparse_rv_only` | policy | cont | **Kill** | MC first_adj RMSE ≪ fourth | MC Kill unchanged |
