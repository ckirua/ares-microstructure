# hv_fei_capacity — EXP_REPORT

Generated: 2026-09-30T19:25:01.576889+00:00
Script: `applications/scripts/exp_hv_fei_sizing.py` · Out: `applications/out/hv_fei_capacity/`

## Setup

- Capacity: day×symbol complete-leg H^v / FEI (3 venues).
- Map H^v quartiles → POV π schedule; compare crash severity by quartile.
- POV sim: `research.lib.pov.simulate_pov_child` on HL crash windows (instant fill @ trade px).

## Headline

- n_cells=**14**; H^v mean=`{'n': 14, 'point': 0.48173741550321825, 'lo': 0.4623628027680543, 'hi': 0.5017568825883171, 'alpha': 0.05, 'n_boot': 800}`; FEI=`{'n': 14, 'point': 0.7503412681118781, 'lo': 0.7198487748918403, 'hi': 0.7824502508125475, 'alpha': 0.05, 'n_boot': 800}`
- Spearman(H^v, |mo|)=**-0.042**; early/late=0.048/-0.152; stable=**False**
- Event high-H vs low-H Δ|mo|=`{'n_treat': 85, 'n_control': 185, 'delta': 1.3696475149953002, 'lo': -2.7500384160836187, 'hi': 5.694276194450938, 'treat_mean': 19.021181191935614, 'control_mean': 17.651533676940314}`
- POV sched vs flat: `{'n': 228, 'n_high_H': 63, 'n_low_H': 165, 'note_vwap_pi_invariant': 'Constant-π POV VWAP impact is invariant to π; schedule value shows up in binding max_child_qty. Evaluate exposure cut on high-H windows only.', 'sched_vs_flat_abs_impact': {'n_treat': 228, 'n_control': 228, 'delta': 3.872457909892546e-13, 'lo': -2.1197101420388416, 'hi': 2.273934322073124, 'treat_mean': 18.572676398879455, 'control_mean': 18.572676398879068}, 'sched_vs_flat_exposure_all': {'n_treat': 228, 'n_control': 228, 'delta': 10.061100568528502, 'lo': 0.05796041264288349, 'hi': 21.262232343016194, 'treat_mean': 48.17726030560176, 'control_mean': 38.11615973707326}, 'sched_vs_flat_exposure_high_H': {'n_treat': 63, 'n_control': 63, 'delta': -13.751430681101311, 'lo': -31.25840636952614, 'hi': 2.17643888700516, 'treat_mean': 35.0388715081781, 'control_mean': 48.79030218927941}, 'sched_vs_flat_filled_qty_high_H': {'n_treat': 63, 'n_control': 63, 'delta': -0.33935669047619055, 'lo': -0.5832257777777776, 'hi': -0.08365519166666681, 'treat_mean': 0.8025471190476191, 'control_mean': 1.1419038095238097}, 'mean_exposure_sched_high_H': {'n': 63, 'point': 35.0388715081781, 'lo': 25.313730341028005, 'hi': 45.357499901042864, 'alpha': 0.05, 'n_boot': 800}, 'mean_exposure_flat_high_H': {'n': 63, 'point': 48.79030218927941, 'lo': 36.135912004059264, 'hi': 62.11712363302433, 'alpha': 0.05, 'n_boot': 800}, 'assumptions': 'POV instant fill at trade price; max_child binds schedule; no self-impact feedback.'}`
- Readiness: **monitor_only** (monitor=promote_monitor; promote_policy=False)

## Figures

- `figs/fig_hv_quartile_severity.png`
- `figs/fig_hv_vs_absmo.png`
- `figs/fig_pov_schedule_vs_flat.png`

