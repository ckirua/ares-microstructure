# tick_constraint — EXP_REPORT

## Pass 1 / native spot L2 rerun
- Days: ['2026-09-26', '2026-09-27', '2026-09-30']
- KR mean frac_constrained: native≈0.850 vs baseline synth≈0.000
- KR mean quoted spread bps: native≈0.03724 vs baseline≈1.5
- Venue means: {"hyperliquid": {"mean_frac_c": 0.9915820145022489, "mean_undercut": 0.04853887970039194, "tob_sources": ["collector", "warehouse:l2_rebuild/s3_cache"], "n_relax_flips": 390}, "deribit": {"mean_frac_c": 0.13632397284291783, "mean_undercut": 0.05692476193559934, "tob_sources": ["warehouse:l2_tob/s3_cache"], "n_relax_flips": 647}, "kraken": {"mean_frac_c": 0.8503458234132575, "mean_undercut": 0.05389017034011464, "tob_sources": ["warehouse:kraken_spot_l2_rebuild"], "n_relax_flips": 105}}
- Cross-link mmip `tick.frac_one_tick` / `spread_leeway`.

## Pass 2
- Label: *fragility monitor* when frac_constrained high + undercut bursts; *exec throttle* only if markout worsens.
- Script: `scripts/exp_pass2_info_exec.py` → `out/tick_constraint/pass2_info_exec.json`
- Relax/undercut stacks on venues with real TOB (HL, Deribit, KR-spot).

## Native rerun artifacts
- Panels: `out/pass1_native/` · `out/pass2_native/` (baseline `out/pass1/` preserved).
- Package figs: `out/tick_constraint/figs/` · mirror `out/native_rerun/tick_constraint/`.
- Gate `exec.tick_constrained_flag`: **Hold** — KR spot L2 native frac_c≈0.8503458234132575; HL still dominates; mmip overlap; futures PF_* L2-absent
