# Content coverage audit -- `empirical_mm`

**Date:** 2026-09-30 · **Root:** `research/books/empirical_mm/`

Inventory of chapter packages: NOTES depth, figure count under `out/<pkg>/`, notebook presence, CHAPTER_INDEX status.
Promote / Kill / Hold decisions: [`../CHAPTER_INDEX.md`](../CHAPTER_INDEX.md) · Desk: [`../DESK_MEMO.md`](../DESK_MEMO.md).

## Package table

| Package | Book map | Status | NOTES lines | n_figs | Notebook | Thin / notes |
|---------|----------|--------|------------:|-------:|----------|--------------|
| `ch00_overview` | Ch.0–2 Overview / martingale | `notes` | 140 | 1 | yes (`ch00_overview.ipynb`) | -- |
| `ch03_roll` | Ch.3 Roll | `exp_run` | 176 | 5 | yes (`ch03_roll.ipynb`) | -- |
| `ch05_seq_info` | Ch.5 Sequential info (GM) | `notes` | 137 | 4 | yes (`ch05_seq_info.ipynb`) | synthetic figs only (OK) |
| `ch06_strategic` | Ch.6 Strategic (Kyle) | `notes` | 133 | 4 | yes (`ch06_strategic.ipynb`) | synthetic figs only (OK) |
| `ch08_noise` | Ch.7–8 RW / noise | `exp_run` | 164 | 2 | yes (`ch08_noise.ipynb`) | -- |
| `ch09_estimation` | Ch.9 Estimation (+ Ch.4) | `exp_run` | 171 | 5 | yes (`ch09_estimation.ipynb`) | -- |
| `ch10_trades` | Ch.10 Trade / inventory | `iterate` | 186 | 4 | yes (`ch10_trades.ipynb`) | -- |
| `ch13_var_impact` | Ch.13 VAR / IRF / OFI (+11–12) | `exp_run` | 208 | 7 | yes (`ch13_var_impact.ipynb`) | -- |
| `ch14_structural` | Ch.14 GH / MRR / HS | `exp_run` | 132 | 6 | yes (`ch14_structural.ipynb`) | -- |
| `ch15_pin` | Ch.15 PIN / VPIN | `exp_run` | 152 | 6 | yes (`ch15_pin.ipynb`) | -- |
| `ch16_asymmetry` | Ch.16 Asymmetry synthesis | `notes` | 109 | 4 | yes (`ch16_asymmetry.ipynb`) | -- |
| `ch17_discovery` | Ch.17 Discovery | `iterate` | 174 | 4 | yes (`ch17_discovery.ipynb`) | -- |
| `ch18_limit_orders` | Ch.18–21 Limit orders | `iterate` | 171 | 6 | yes (`ch18_limit_orders.ipynb`) | -- |
| `ch22_liquidity` | Ch.22 Liquidity / Amihud | `iterate` | 221 | 5 | yes (`ch22_liquidity.ipynb`) | -- |
| `appendix_us` | Appendix US equity -> crypto | `park` | 46 | 0 | no (`--`) | intentionally park -- no empirics stream |

## Folded chapters (no dedicated package)

| Book Ch. | Where content lives | Notes |
|----------|---------------------|-------|
| Ch.4 MA/AR | `ch09_estimation/NOTES.md` | Toolkit folded into estimation case |
| Ch.11–12 RW / multivariate | `ch13_var_impact/NOTES.md` §7 | Unit roots / invertibility / VAR->VMA IRF |

## Thin-spot flags

- **`ch05_seq_info`** (`notes`): synthetic figs only (OK)
- **`ch06_strategic`** (`notes`): synthetic figs only (OK)
- **`appendix_us`** (`park`): intentionally park -- no empirics stream

### Intentional parks / non-goals

- **`appendix_us` (`park`):** US equity institutional history is **not** an empirics target. Keep the transfer table in NOTES; do **not** open NYSE/Nasdaq experiment scripts. Price-discovery analogues live in `ch17_discovery`; fragmentation analogues in mmip.
- **`ch05_seq_info` / `ch06_strategic`:** Deep NOTES + labeled **SYNTHETIC** notebooks/figures are the quality bar. Empirics owned by ch13/14/15 (+ mmip POV for Kyle).
- **`ch00_overview`:** Framing package (front door + roadmap figure) -- not a free-standing tape experiment.

## Totals

- Packages: **15** · Notebooks: **14/15** · Figures: **63** · NOTES lines (sum): **2320**
- Public-tape Holds pass: **COMPLETE** (residual Holds are data ceilings, not missing content).

## Figure inventory by package

- `ch00_overview`: `fig_roadmap_status.png`
- `ch03_roll`: `fig_clock_acf.png`, `fig_mid_path.png`, `fig_noise_rv_curve.png`, `fig_roll_acov.png`, `fig_roll_id_map.png`
- `ch05_seq_info`: `fig_impact_cartoon.png`, `fig_pr_informed_buy.png`, `fig_quote_belief_path.png`, `fig_spread_vs_mu.png`
- `ch06_strategic`: `fig_kyle_lambda_statics.png`, `fig_kyle_multiperiod.png`, `fig_kyle_yp_scatter.png`, `fig_order_split_cartoon.png`
- `ch08_noise`: `fig_clock_acf.png`, `fig_noise_rv_curve.png`
- `ch09_estimation`: `fig_ar_irf.png`, `fig_ar_lag_sweep.png`, `fig_return_acf.png`, `fig_sigma_w_compare.png`, `fig_variance_ratio.png`
- `ch10_trades`: `fig_cumflow_inv.png`, `fig_intensity_volclock.png`, `fig_sign_acf.png`, `fig_trade_size.png`
- `ch13_var_impact`: `fig_alignment_corr.png`, `fig_irf_cum.png`, `fig_lambda_hygiene.png`, `fig_markout.png`, `fig_ofi_scatter.png`, `fig_sign_acf.png`, `fig_var_coef.png`
- `ch14_structural`: `fig_gh_size_bins.png`, `fig_gh_z0.png`, `fig_hs_decomp.png`, `fig_hs_pi.png`, `fig_mrr_decomp.png`, `fig_perm_impact_compare.png`
- `ch15_pin`: `fig_bs_scatter.png`, `fig_intensity.png`, `fig_pin_day_panel.png`, `fig_pin_vs_vpin.png`, `fig_vpin_path.png`, `fig_vpin_vs_markout.png`
- `ch16_asymmetry`: `fig_hs_disagreement.png`, `fig_measure_board.png`, `fig_pin_vs_vpin_markout.png`, `fig_status_map.png`
- `ch17_discovery`: `fig_basis.png`, `fig_epps_curve.png`, `fig_info_share_bounds.png`, `fig_jump_leadlag.png`
- `ch18_limit_orders`: `fig_cancel_vs_fill.png`, `fig_parlour_lob_clocks.png`, `fig_resilience_refill.png`, `fig_sandas_depth.png`, `fig_size_touch_survival.png`, `fig_time_to_touch.png`
- `ch22_liquidity`: `fig_amihud_dist_daily.png`, `fig_amihud_ts.png`, `fig_illiq_vs_spread_vpin.png`, `fig_quoted_spread.png`, `fig_turnover.png`
- `appendix_us`: _(none)_

## Regeneration

```bash
# roadmap board
python3 scripts/plot_ch00_overview.py
# chapter figs: scripts/plot_ch*.py
# notebooks: scripts/_build_notebooks.py (+ ch00 / desk_synthesis built ad hoc)
```

