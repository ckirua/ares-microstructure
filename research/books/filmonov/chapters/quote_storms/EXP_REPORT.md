# Quote storms — EXP_REPORT

## Pass 1
- Slice: **ETH** · HL + Deribit + Kraken · days `['2026-09-26', '2026-09-27', '2026-09-30']`
- Detector: `hftpat.quote_storm_intensity` / `quote_storm_detect` (1s bars, z≥3 update-Hz; min_hz=0 crypto-adapted)
- Sparse warehouse TOB (mean Hz < 0.5) flagged; collector day (HL 09-30) carries most storm mass.
- **Not a rename** of `lob.tob_depletion_cancel_proxy` (burst intensity vs unconditional cancel class) nor equity Nanex quote-rate vanity.

### Headlines (complete days)
- **hyperliquid**: storms/hour=0.553, n_storms_update=33, n_storms_size=316, median max_burst/mean=5.37, baseline Hz=0.683, sparse_tob_days=2/3
- **deribit**: storms/hour=0, n_storms=0 (all days sparse TOB), median max_burst/mean=3.09, baseline Hz=0.32, n_days=3
- **kraken**: storms/hour=0, n_storms=0; all 3 days `trade_synth` TOB (intensity still reported; stuffing semantics weaker)

### Completeness
- Day×venue rows: 9; complete: 9. Incomplete days flagged in `out/quote_storms/pass1.json`.

### Figures
- `out/quote_storms/figs/fig_burst_intensity.png`
- `out/quote_storms/figs/fig_cancel_frac.png`
- `out/quote_storms/figs/fig_day_baseline.png`

## Pass 2
- Early/late days: ['2026-09-26'] / ['2026-09-27', '2026-09-30']
- HL storms/h=0.5294467018620957; CI={'n': 3, 'point': 0.5294467018620957, 'lo': 0.0, 'hi': 1.0588934037241915, 'alpha': 0.05, 'n_boot': 400}; lob-cancel frac=0.3125
- DB/KR storms sparse (sph=0.0/0.0)
- Labels: {'risk.quote_storm_burst': {'decision': 'Hold', 'monitor': True, 'tradable': False, 'exec_throttle': True, 'why': 'HL storms/h≈0.5294467018620957; lob-cancel frac≈0.3125; early/late=0.0/0.7941700527931437; sparse DB/KR → monitor/exec-throttle only'}, 'risk.quote_storm_vs_lob': {'decision': 'Hold', 'monitor': True, 'tradable': False, 'exec_throttle': False, 'why': 'competing-def gate vs lob cancel_proxy'}}
- Artifacts: `out/pass2/quote_storms.json`, `out/pass2/figs/`
- Decision: **Hold** exec-throttle / risk monitor (not tradable).

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
