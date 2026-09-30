# Estimators — EXP_REPORT (Pass 2.6 blocker-close)

**`cont.tsrv_first_adj`:** **Hold** — fragile_rate=0.011 adv_med=-2.75e-07 CI=[-2.306071822364372e-06, 1.1699299344884352e-06] SE=8.31e-07 earlyCI=[-4.654016190012627e-06, 1.3038927370727255e-05] lateCI=[-2.862172387962406e-06, 1.019566994153289e-06] ratio_med=1.0171 ratioCI=[0.9594350796515484, 1.0516421957379292] roll_ci_lo_pos_frac=0.00 n=90 (MC Kill sparse still stands; Promote needs OOS CI_lo>0 early∧late)

- sparse−tsrv overall: {'n': 90.0, 'median': -2.747479641365083e-07, 'mean': -1.0759664019689518e-05, 'se': 8.306201301512939e-07, 'ci95': [-2.306071822364372e-06, 1.1699299344884352e-06]}
- early/late: {'n': 40.0, 'median': 3.4908770417389824e-07, 'mean': -1.8631476095667503e-05, 'se': 4.959528934185611e-06, 'ci95': [-4.654016190012627e-06, 1.3038927370727255e-05]} / {'n': 50.0, 'median': -5.438004162805318e-07, 'mean': -4.462214358907126e-06, 'se': 9.83031907868457e-07, 'ci95': [-2.862172387962406e-06, 1.019566994153289e-06]}
- tsrv/sparse ratio: {'n': 90.0, 'median': 1.017116835942236, 'mean': 1.0226128288195953, 'se': 0.025718414696119976, 'ci95': [0.9594350796515484, 1.0516421957379292]}
- rolling 5d frac CI_lo>0: 0.0
- **`cont.sparse_rv_only` remains Kill** (MC first_adj RMSE ≪ fourth).

Artifact: [`../../out/blocker_close/blocker_close.json`](../../out/blocker_close/blocker_close.json)
