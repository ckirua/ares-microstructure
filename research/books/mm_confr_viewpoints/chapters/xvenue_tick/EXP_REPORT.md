# xvenue_tick — EXP_REPORT

## Dual slices (native rerun)
- (a) HL–Deribit–KR-**futures synth**: 9 pair-rows — labeled trade_synth / PF market.
- (b) HL–Deribit–KR-**spot L2**: 9 pair-rows — **spot≠perp** honesty for τ/MQ concordance.
- Figs: `out/xvenue_tick/figs/` + `out/native_rerun/figs/fig_xvenue_dual_slices.png`
- Artifacts: `out/xvenue_tick/pairs.json` · `out/native_rerun/xvenue_tick/dual_slices.json`

- Gate `frag.xvenue_tau_gap`: **Hold** — HL↔DB stable; KR-spot τ usable but spot≠perp — dual slice documented, no Promote
