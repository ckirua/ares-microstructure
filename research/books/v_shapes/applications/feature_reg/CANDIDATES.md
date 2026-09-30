| id | type | lenses | decision | evidence |
|----|------|--------|----------|----------|
| `info.v_feature_ridge_tick` | D | info, cont, exec | **Hold** | Primary `y_tick_20` trade-time; R²_te≈−1.25 IC≈−0.088 boot CI includes 0; early/late OOS IC unstable; n≈245k; intensity-dominated |
| `info.v_feature_ridge_calendar` | D | info, cont | **Promote** | Monitor only (not sized). cal30/60/300: R²≈0.003/0.006/0.026 IC≈0.068/0.096/0.187; IC CI excludes 0; sign-stable; leading coef T− |
| `info.v_feature_ridge_volume_clock` | D | info, cont | **Hold** | R²_te≈−1.29 IC≈−0.095; same OOS collapse as tick |
| `info.v_feature_leakage_V_Tp` | D | info | **Kill** | Contemporaneous V/T+ right-kernel look-ahead; banned live (diagnostic only) |
| `info.breach_sign_logistic` | D | info, exec | **Hold** | AUC_te≈0.49 base≈0.48 — coin-flip |
