# emp_predictions — EXP_REPORT

## Pass 1
- Expected-sign matrix from deck pp. 20–29 in `research.lib.ticksize`.
- Matrix regimes: ['large_abs_reduction', 'small_abs_reduction', 'large_abs_increase', 'small_abs_increase', 'rel_tick_up', 'rel_tick_down']
- Kill metrics: ['welfare']
- Sign scorecard (rel_tick_up vs MQ Spearman): hits=1 misses=2 skips=1 hit_rate=0.3333333333333333

## Pass 2
- Welfare cells → Kill (unobservable).
- SEC/IPO → out of scope.
- LOB backward-induction stays NOTES-only (no production game sim).

## Day completeness
- Complete venue-days: 9

## Figures
- Notebook: [`emp_predictions.ipynb`](emp_predictions.ipynb)
- `out/emp_predictions/figs/fig_sign_heatmap.png` (alias `sign_matrix.png`)
- `out/emp_predictions/figs/fig_scorecard.png` (alias `scorecard.png`)
- `out/emp_predictions/figs/fig_kill_cells.png`
- Manifest: [`../../out/fig_manifest.json`](../../out/fig_manifest.json)
