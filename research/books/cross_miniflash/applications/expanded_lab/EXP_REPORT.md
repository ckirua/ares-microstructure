# Expanded lab — EXP_REPORT

Generated: 2026-09-30T20:16:49.752536+00:00
Panel days=['2026-09-01', '2026-09-02', '2026-09-03', '2026-09-04', '2026-09-05', '2026-09-06', '2026-09-07', '2026-09-08', '2026-09-09', '2026-09-10'] · symbols=['BTC', 'ETH', 'SOL'] · n_rows=74
Events: core=275 · core+extend=310 · SOL=43 · all=353

## Honesty
- Own cache `expanded_lab/out/panel/` — sibling `applications/out/event_panel` untouched.
- Risk overlays + MM playbooks first; **no naked tradable alpha**.
- Time-split + bootstrap CIs; friction haircut on adverse costs.
- HL SOL empty on flat-era Phase-4 days → SOL = Deribit+Kraken.

## Kill-ladder / Nanex robustness
- Core kill-ladder: `promote_as_risk_policy` Δ|mo|={'n_treat': 227, 'n_control': 43, 'delta': 8.419386599484218, 'lo': 5.390529494890893, 'hi': 11.421431349806536, 'treat_mean': 19.423584278986322, 'control_mean': 11.004197679502104}
- Core+extend: `promote_as_risk_policy` Δ|mo|={'n_treat': 254, 'n_control': 51, 'delta': 8.724820887106223, 'lo': 5.7832235562080925, 'hi': 11.810054836156034, 'treat_mean': 19.088184508674978, 'control_mean': 10.363363621568755}
- SOL: n=43 readiness=`monitor_only`
- Nanex precision core=0.9047619047619048 extend=0.896551724137931 SOL=0.9090909090909091

## Strategy risk scoreboard (2bps)
- Ranked (best→worst cont adverse / DD / hole inv): `['ladder_plus_confirm_before_restore', 'ladder_plus_v_restore', 'ladder_only', 'always_stay_wide', 'confirm_before_restore', 'v_restore_confirm', 'always_restore']`
- Best: **ladder_plus_confirm_before_restore**
- Friction rank stable across grid: `True`

## Models
- Occurrence: verdict=`Hold` AUC_te=0.6456241032998565 Brier=0.26037509105628415 BayesAUC=0.6456241032998565
- Severity: verdict=`Hold` R²_te=0.16293834680561514 BayesR²=0.16948515965400723

## Book realism
- {'dense_days_collector_hits': 6, 'core_days_collector_hits': 0, 'dense_median_collector_dt_s': 0.546212032, 'dense_median_warehouse_dt_s': 5.393999872, 'core_median_warehouse_dt_s': 176.839, 'dense_median_outside_best': 0.38947898254627233, 'note': 'Collector TOB denser on 2026-09-29/30 (HL); Phase-4 core days rely on warehouse BBO/l2_rebuild (~seconds). Prefer best book in strategy_lab.'}
- Rec: Promote denser-book marking for HL on dense-TOB days; Hold ms-L2 claims on Phase-4 warehouse-only days

## Promotes / Holds (new)
- **Promote-as-risk-policy** `kill_ladder (core+extend)` — Δ|mo|=8.724820887106223 friction+time-split OK
- **Promote-as-risk-policy** `nanex∩ssm` — precision core=0.905 extend=0.897
- **Promote (med)** `MM playbook::ladder_plus_confirm_before_restore` — Ranks best on cont adverse + max DD at 2bps friction — playbook not alpha
- **Promote (ops)** `dense TOB marking` — Promote denser-book marking for HL on dense-TOB days; Hold ms-L2 claims on Phase-4 warehouse-only days

### Holds
- **Hold (promising)** `kill_ladder SOL (DB+KR)` — n=43 friction clears but readiness=monitor_only — underpowered time-split
- **Hold** `occurrence model` — AUC_te=0.6456241032998565 — bar not cleared or split issue
- **Hold** `severity |ΔP| model` — ridge R²_te=0.16293834680561514 bayes R²=0.16948515965400723 (excluded contemporaneous abs_z (leak with |ΔP|))

## Figures
- `fig_kill_ladder_robustness.png`
- `fig_nanex_precision_slices.png`
- `fig_strategy_risk_scoreboard.png`
- `fig_friction_sweep.png`
- `fig_occurrence_calibration.png`
- `fig_book_cadence_compare.png`
- `fig_outside_tob_best.png`

## Identification
- Gate: SSM z*=6 + |ΔP|≥10bps + i_c≥5
- Ladder: within-gated z percentiles + intensity + Nanex nest
- Strategy costs: size × signed tape mo (crash direction); rank on risk not rebound PnL

