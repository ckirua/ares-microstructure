# Signal boards — visualization / research

Desk-quality **signal boards**, **information theory**, **statistical**, and **Bayesian** panels on the gated SSM event set (n=275).

**Does not overwrite** [`../strategy_lab/`](../strategy_lab/) equity curves — cross-link only.

## Open these first

| Notebook | What |
|----------|------|
| [`../../notebooks/full_research_board.ipynb`](../../notebooks/full_research_board.ipynb) | Synthesis of all boards |
| [`signal_boards.ipynb`](signal_boards.ipynb) | Promote feature time series + heatmaps |
| [`info_theory.ipynb`](info_theory.ipynb) | MI / lagged MI / venue entropy |
| [`statistical.ipynb`](statistical.ipynb) | Bootstrap · time-split · ROC · calibration |
| [`bayesian.ipynb`](bayesian.ipynb) | Beta–Binomial V-rate + MH logistic occurrence |

**Key PNGs:** [`../out/signal_boards/figs/`](../out/signal_boards/figs/)

| PNG | Content |
|-----|---------|
| `fig_gated_intensity_ts.png` | Gated SSM intensity by venue×day |
| `fig_zstar_path_ts.png` | z*-path (median peak) |
| `fig_nanex_ssm_ts.png` | Nanex∩SSM nested counts |
| `fig_vpin_x_size_ts.png` | VPIN×size interact |
| `fig_hv_fei_ts.png` | H^v / FEI capacity |
| `fig_thin_excess_ts.png` | HL thin excess |
| `fig_event_heatmaps.png` | Event-aligned feature heatmaps |
| `fig_mi_event.png` / `fig_mi_occurrence.png` | Mutual information |
| `fig_occurrence_roc.png` / `fig_occurrence_calibration.png` | Occurrence model |
| `fig_bayes_v_recovery.png` / `fig_bayes_logistic_*.png` | Bayesian PPC |

## Run

```bash
cd applications
PYTHONPATH=... python3 signal_boards/exp_signal_boards.py
```

Reuses `mm_quoting/out/panel_cache.json` + `out/event_panel/panel_rows.json`. ClickHouse MCP banned.

## Bayesian honesty

- **V-recovery:** Beta(1,1) prior → Beta–Binomial posterior; PPC on share_V.
- **Occurrence:** β ~ N(0, 2²) on standardized day-level features; RW-MH; PPC on mean crash rate; holdout AUC from posterior mean.
- PyMC/numpyro not installed on host — conjugate + MH chosen deliberately.
