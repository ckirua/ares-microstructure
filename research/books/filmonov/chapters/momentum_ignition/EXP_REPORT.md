# Momentum ignition — EXP_REPORT

## Pass 1
- Slice: **ETH** · HL + Deribit + Kraken · days `['2026-09-26', '2026-09-27', '2026-09-30']`
- Detector: `hftpat.ignition_events` (crypto Pass1 params: bar=1s, phases 3/3/5, vol_z=1, quiet≤15bps, move≥5bps, recovery≥0.15)
- Overlap draft: `overlap_vs_crash` vs Nanex/vshape (min_pct=0.1%) / SSM + `rename_gate`
- **Not a rename** of Nanex/SSM/V or `vstat.min_v`. Promote only if Phase1 adds info — **Pass1 → Hold**.
- Overlap headline: HL frac∩Nanex≈0.19 / ∩vshape≈0.47; Deribit ≈0.42 / 0.63; Kraken ≈0.48 / 0.44 (elevated → Hold, not Promote).

### Headlines (complete days)
- **hyperliquid**: n_ignition=21, mean |move| bps=7.536365037022055, mean frac∩Nanex=0.19444444444444442, mean frac∩vshape=0.46527777777777773, decision=Hold
- **deribit**: n_ignition=14, mean |move| bps=8.673220342193027, mean frac∩Nanex=0.4166666666666667, mean frac∩vshape=0.625, decision=Hold
- **kraken**: n_ignition=12, mean |move| bps=8.021456218965858, mean frac∩Nanex=0.48148148148148145, mean frac∩vshape=0.4444444444444444, decision=Hold

### Overlap table
- See `out/momentum_ignition/overlap_draft.json` and `figs/fig_overlap_table.png`

### Figures
- `out/momentum_ignition/figs/fig_ignition_counts.png`
- `out/momentum_ignition/figs/fig_ignition_move_recovery.png`
- `out/momentum_ignition/figs/fig_overlap_table.png`

## Pass 2
- Venue summary: {'hyperliquid': {'n_days': 3, 'n_ignition_total': 21, 'mean_frac_in_nanex': 0.19444444444444442, 'mean_frac_in_vshape': 0.46527777777777773, 'mean_phase1_unique_frac': 0.5347222222222222, 'early_n': 2, 'late_n': 19, 'kill_rename': False, 'promote_gate_ok': False, 'decision': 'Hold'}, 'deribit': {'n_days': 3, 'n_ignition_total': 14, 'mean_frac_in_nanex': 0.4166666666666667, 'mean_frac_in_vshape': 0.625, 'mean_phase1_unique_frac': 0.20833333333333334, 'early_n': 4, 'late_n': 10, 'kill_rename': False, 'promote_gate_ok': False, 'decision': 'Hold'}, 'kraken': {'n_days': 3, 'n_ignition_total': 12, 'mean_frac_in_nanex': 0.48148148148148145, 'mean_frac_in_vshape': 0.48148148148148145, 'mean_phase1_unique_frac': 0.48148148148148145, 'early_n': 1, 'late_n': 11, 'kill_rename': False, 'promote_gate_ok': False, 'decision': 'Hold'}}
- any_promote=False
- Labels: {'risk.momentum_ignition_3phase': {'decision': 'Hold', 'monitor': True, 'tradable': False, 'exec_throttle': False, 'why': 'Phase1 unique-mass + Nanex/V overlap gates; hyperliquid: n=21 ∩N=0.19444444444444442 ∩V=0.46527777777777773 uniq=0.5347222222222222; deribit: n=14 ∩N=0.4166666666666667 ∩V=0.625 uniq=0.20833333333333334; kraken: n=12 ∩N=0.48148148148148145 ∩V=0.48148148148148145 uniq=0.48148148148148145'}, 'risk.ignition_vs_nanex_vshape': {'decision': 'Hold', 'monitor': True, 'tradable': False, 'exec_throttle': False, 'why': 'elevated ∩vshape on some venues; rename_gate not kill_rename but not Promote'}}
- Artifacts: `out/pass2/momentum_ignition.json`
- Decision: **Hold** — Phase1 unique-mass / overlap gates do not clear Promote.

## Pass 2.5 hardening
- Day-block bootstrap ETH+BTC → `out/hardening/`
- Early/late: ['2026-09-26'] / ['2026-09-27', '2026-09-30']
- Program freeze: **0 Promote / 13 Hold / 11 Kill**
- Boots: `{"hl_storms_per_hour": {"boot": {"n": 3, "point": 0.5294467018620957, "lo": 0.0, "hi": 1.5883401055862876, "alpha": 0.05, "n_boot": 500}, "early_mean": 0.0, "late_mean": 0.7941700527931437, "n": 3, "btc_mean": 0.5294391320374869}, "hl_p_fade_100ms": {"boot": {"n": 3, "point": 0.0194400253855552, "lo": 0.003980616130148841, "hi": 0.048213081591368855, "alpha": 0.05, "n_boot": 500}, "early_mean": 0.003980616130148841, "late_mean": 0.027169730013258377, "n": 3, "btc_mean": 0.024681680355299555}, "h…`

---

## Pass-2 expand dig

- Panel: ETH+BTC · days 2026-09-25/26/27/30 · HL+Deribit native TOB; Kraken synth/empty excluded
- Runners: `scripts/exp_pass2_expand.py`, `exp_info_features.py`, `exp_expand_board.py`
- Artifacts: `out/pass2_expand/pass2_expand_rollup.json`, `info_features.json`, `expand_board.json`
- Board impact: +8 info Holds (still **0 Promote**); package figs synced from expand dig
- See desk `DESK_MEMO.md` §1 jobs and `APPLICATIONS.md` wire-as
