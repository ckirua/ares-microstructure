# Feature regressions — EXP_REPORT

## Sampling honesty
- Price grid: **5.0s** last-print (book legacy; matches `continuous_v` / widen).
- Decision subsample: every **30.0s**.
- Primary target: **`y_tick_20`** on **trade_time_next_N_trades** (next-N trade log return from raw tape).
- Secondary: calendar 30s/60s/300s; volume-clock bar.
- Latency: features known at decision print; no exchange-latency model.
- Look-ahead ban: `V_now`, `Tp` (right kernel) = leakage diagnostics only.

## Sample
- n_rows=92495 · ETH days=8 · BTC days=4
- venues=['hyperliquid', 'deribit', 'kraken']
- causal feats=['Tm', 'abs_Tm', 'Tm_1m', 'V_lag', 'abs_V_lag', 'running_min_v', 'abs_running_min_v', 'breach', 'geom_near', 'log_intensity', 'vpin_roll', 'hn5_dummy']

## Primary result (`y_tick_20`)
- n=92135 train/test=69662/22473 α=1000.0
- Ridge R²_te=0.10906877757716038 IC=0.1314943705126694 boot={'lo': -0.0026058611767147528, 'hi': 0.2195816148474652, 'excludes_0': False}
- early/late IC=nan/0.1314943705126694 sign_stable=False
- decision_hint=Hold promote_ok=False

## Other clocks
- `y_tick_10`: R²_te=0.1021779016870169 IC=0.11497857894888437 ok=False n=92135
- `y_tick_50`: R²_te=0.0921069136215299 IC=0.1631237885416038 ok=False n=92134
- `y_cal_30s`: R²_te=0.0005142061796874486 IC=0.030117000118909623 ok=False n=92135
- `y_cal_60s`: R²_te=0.0016369602693375729 IC=0.049346192026537804 ok=False n=92135
- `y_cal_300s`: R²_te=0.010812793882740146 IC=0.12522343261573068 ok=False n=92135
- `y_vol`: R²_te=0.11448359188620527 IC=0.418948581739881 ok=False n=92135

## Logistic breach→sign
- AUC_te=0.5411055227637661 base=0.45321051928981443 decision=Hold

## Leakage check (V_now+Tp added)
- {'r2_train': 0.04902492478109144, 'r2_test': 0.11275367047720175, 'ic_test': 0.15054695081377734, 'ic_boot': {'lo': 0.020530866320747094, 'hi': 0.24017867616706198, 'excludes_0': True}, 'rmse_test': 0.0014259337169518246, 'coef': {'Tm': 1.930345309113999e-05, 'abs_Tm': 5.0781825819766656e-06, 'Tm_1m': -1.5934573161575086e-05, 'V_lag': -2.9937713569240635e-07, 'abs_V_lag': -2.6747497198486847e-06, 'running_min_v': -2.4176414026696215e-05, 'abs_running_min_v': -2.100512728238587e-05, 'breach': 0.0, 'geom_near': -5.449425690166835e-06, 'log_intensity': 6.656377213739728e-05, 'vpin_roll': -2.2639775193142748e-06, 'hn5_dummy': 0.0, 'V_now': -4.357880655564721e-06, 'Tp': 1.787821461536448e-05}, 'ic_early': nan, 'ic_late': 0.15054695081377734, 'sign_stable': False}

## Gate rollup
- **Hold** `info.v_feature_ridge_tick` — target=y_tick_20 clock=trade_time_next_N_trades; R²_te=0.10906877757716038 IC=0.1314943705126694 boot={'lo': -0.0026058611767147528, 'hi': 0.2195816148474652, 'excludes_0': False} 
- **Hold** `info.v_feature_ridge_calendar` — y_cal_30s: R²=0.0005142061796874486 IC=0.030117000118909623 ok=False; y_cal_60s: R²=0.0016369602693375729 IC=0.049346192026537804 ok=False; y_cal_300s: R²=0.010812793882740146 IC=0
- **Hold** `info.v_feature_ridge_volume_clock` — R²_te=0.11448359188620527 IC=0.418948581739881 n=92135
- **Kill** `info.v_feature_leakage_V_Tp` — leakage design (V_now+Tp+causal) IC=0.15054695081377734 vs causal IC=0.1314943705126694; right-kernel T+/contemporaneous V banned at decision time — Kill as live features
- **Hold** `info.breach_sign_logistic` — AUC_te=0.5411055227637661 base=0.45321051928981443 n=92135 coef_breach=0.0

## Artifacts
- `out/feature_reg/summary.json`
- `out/feature_reg/panel_rows.json` / `panel_meta.json`
- `out/feature_reg/coef_tables.json`
- `out/feature_reg/figs/ic_by_horizon.png`, `ridge_path.png`, `oos_scatter_primary.png`, `ridge_coefs_primary.png`
