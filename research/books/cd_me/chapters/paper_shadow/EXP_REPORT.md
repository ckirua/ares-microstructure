# paper_shadow — EXP_REPORT

## Dry-runs
| Day | PIM | DCM̂ | Elasticity | live_orders |
|-----|-----|------|------------|-------------|
| 2026-09-29 | ok n_finite=1265 mean≈0.049 corr_VT≈0.82 | ok n_valid=77 explained≈0.98 home=deribit | hourly artifact n=2 → ok=false (thin) | false |
| 2026-09-14 | ok n_finite=668 mean≈0.016 corr_VT≈0.83 | ok n_valid=291 constrained_flag=True | all corr≈−0.32 n=13 ok | false |

Command: `python3 applications/paper_shadow/run_paper_shadow.py --day <DAY> --iterations 1`

## Board improvements
- Elasticity prefers `out/pim_vloop_tcost` hourly PIM×notional
- DCM proxies omit all-NaN columns (basis/imbalance) so PC1 is not vacuously empty
- Board prints elasticity source / corr / n and Kraken mode (`spot_l2` vs labeled `trade_synth`)

## Status
- Monitor-only; Hold board pinned in `config.yaml`
- Pass 2 falsifiers done — still **Hold**; never flip `live_orders`
