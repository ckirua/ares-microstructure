| id | type | lenses | decision | evidence |
|----|------|--------|----------|----------|
| `info.v_feature_ridge_tick` | D | info, cont, exec | **Hold** | target=y_tick_20 clock=trade_time_next_N_trades; R²_te=0.10906877757716038 IC=0.1314943705126694 boot={'lo': -0.0026058611767147528, 'hi': 0.2195816148474652, 'excludes_0': False} early/late IC=nan/0.1314943705126694 sig |
| `info.v_feature_ridge_calendar` | D | info, cont | **Hold** | y_cal_30s: R²=0.0005142061796874486 IC=0.030117000118909623 ok=False; y_cal_60s: R²=0.0016369602693375729 IC=0.049346192026537804 ok=False; y_cal_300s: R²=0.010812793882740146 IC=0.12522343261573068 ok=False |
| `info.v_feature_ridge_volume_clock` | D | info, cont | **Hold** | R²_te=0.11448359188620527 IC=0.418948581739881 n=92135 |
| `info.v_feature_leakage_V_Tp` | D | info | **Kill** | leakage design (V_now+Tp+causal) IC=0.15054695081377734 vs causal IC=0.1314943705126694; right-kernel T+/contemporaneous V banned at decision time — Kill as live features |
| `info.breach_sign_logistic` | D | info, exec | **Hold** | AUC_te=0.5411055227637661 base=0.45321051928981443 n=92135 coef_breach=0.0 |
