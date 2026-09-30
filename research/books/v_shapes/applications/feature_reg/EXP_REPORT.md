# Feature regressions — EXP_REPORT

## Sampling honesty
- Price grid: **5.0s** last-print (book legacy; matches `continuous_v` / widen).
- Decision subsample: every **30.0s**.
- Primary target: **`y_tick_20`** on **trade_time_next_N_trades** (next-N trade log return from raw tape).
- Secondary: calendar 30s/60s/300s; volume-clock bar.
- Latency: features known at decision print; no exchange-latency model.
- Look-ahead ban: `V_now`, `Tp` (right kernel) = leakage diagnostics only.

## Sample
- n_rows=245928 · ETH days=20 · BTC days=13
- venues=['hyperliquid', 'deribit', 'kraken']
- causal feats=['Tm', 'abs_Tm', 'Tm_1m', 'V_lag', 'abs_V_lag', 'running_min_v', 'abs_running_min_v', 'breach', 'geom_near', 'log_intensity', 'vpin_roll', 'hn5_dummy']

## Primary result (`y_tick_20`)
- n=244938 train/test=159956/84982 α=0.6579332246575679
- Ridge R²_te=-1.2472148427472054 IC=-0.08773154190945692 boot={'lo': -0.1913818998107668, 'hi': 0.01608586849978722, 'excludes_0': False}
- early/late OOS IC=-0.22006015365231976/0.004523387739796098 sign_stable=False
- decision_hint=Hold promote_ok=False

## Other clocks
- `y_tick_10`: R²_te=-1.262814943050432 IC=-0.09472780481074747 ok=False n=244938
- `y_tick_50`: R²_te=-1.2341966287691744 IC=-0.07543249772171742 ok=False n=244934
- `y_cal_30s`: R²_te=0.0033024445810511116 IC=0.06757144916075941 ok=True n=244938
- `y_cal_60s`: R²_te=0.006298684914202601 IC=0.09624789054019979 ok=True n=244938
- `y_cal_300s`: R²_te=0.02582315092272891 IC=0.18739050773955548 ok=True n=244938
- `y_vol`: R²_te=-1.2897365293752845 IC=-0.09482005639221283 ok=False n=244937

## Logistic breach→sign
- AUC_te=0.49077615465167557 base=0.47984279023793275 decision=Hold

## Leakage check (V_now+Tp added)
- {'r2_train': 0.47074935063738543, 'r2_test': -1.2472129531902114, 'ic_test': -0.08299407164024794, 'ic_boot': {'lo': -0.1870226544286362, 'hi': 0.021269621875166934, 'excludes_0': False}, 'rmse_test': 0.004713215625357762, 'coef': {'Tm': 5.1722463710710215e-05, 'abs_Tm': 2.237561715311541e-05, 'Tm_1m': -1.4801539830077112e-05, 'V_lag': -4.148686695148161e-05, 'abs_V_lag': -5.0314416287993456e-05, 'running_min_v': 7.19752817152684e-06, 'abs_running_min_v': 0.00013446168966925985, 'breach': -7.969977605761488e-05, 'geom_near': -0.00010846373924279734, 'log_intensity': 0.0013476121538589343, 'vpin_roll': 8.001047527647977e-05, 'hn5_dummy': 0.0, 'V_now': 3.508332968418558e-05, 'Tp': 2.8856159720809393e-05}, 'ic_early_oos': -0.21565012475868478, 'ic_late_oos': 0.009914145671294831, 'sign_stable': False}

## Gate rollup
- **Hold** `info.v_feature_ridge_tick` — target=y_tick_20 clock=trade_time_next_N_trades; R²_te=-1.2472148427472054 IC=-0.08773154190945692 boot={'lo': -0.1913818998107668, 'hi': 0.01608586849978722, 'excludes_0': False} 
- **Promote** `info.v_feature_ridge_calendar` — y_cal_30s: R²=0.0033024445810511116 IC=0.06757144916075941 ok=True; y_cal_60s: R²=0.006298684914202601 IC=0.09624789054019979 ok=True; y_cal_300s: R²=0.02582315092272891 IC=0.18739
- **Hold** `info.v_feature_ridge_volume_clock` — R²_te=-1.2897365293752845 IC=-0.09482005639221283 n=244937
- **Kill** `info.v_feature_leakage_V_Tp` — leakage design (V_now+Tp+causal) IC=-0.08299407164024794 vs causal IC=-0.08773154190945692; right-kernel T+/contemporaneous V banned at decision time — Kill as live features
- **Hold** `info.breach_sign_logistic` — AUC_te=0.49077615465167557 base=0.47984279023793275 n=244938 coef_breach=-0.005429947766334045

## Artifacts
- `out/feature_reg/summary.json`
- `out/feature_reg/panel_rows.json` / `panel_meta.json`
- `out/feature_reg/coef_tables.json`
- `out/feature_reg/figs/ic_by_horizon.png`, `ridge_path.png`, `oos_scatter_primary.png`, `ridge_coefs_primary.png`, `train_test_split.png`, `ridge_coefs_calendar.png`
