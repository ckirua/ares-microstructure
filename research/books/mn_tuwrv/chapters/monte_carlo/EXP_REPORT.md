# Monte Carlo — EXP_REPORT (Pass 2)

## Sample
- n_sims: 500
- K: 300  step: 300
- Heston σ_ε=0.0005

| Estimator | Bias | Var | RMSE | n |
|-----------|------|-----|------|---|
| fifth | 0.0116949 | 1.91177e-08 | 0.0116957 | 500 |
| fourth | 3.83496e-05 | 1.02114e-09 | 4.98977e-05 | 500 |
| third | 3.83496e-05 | 1.02114e-09 | 4.98977e-05 | 500 |
| second | 3.52445e-05 | 4.24783e-10 | 4.0818e-05 | 500 |
| first | -3.76187e-06 | 4.25356e-10 | 2.09441e-05 | 500 |
| first_adj | -3.25097e-06 | 4.27987e-10 | 2.09213e-05 | 500 |

## Gate
- `cont.sparse_rv_only` → **Kill** — first_adj_rmse=2.09213e-05 fourth_rmse=4.98977e-05
- Artifact: `out/monte_carlo/mc_summary_pass2.json`
