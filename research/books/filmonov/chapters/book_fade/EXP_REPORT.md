# Book fade — EXP_REPORT

## Pass 1
- Slice: **ETH** · HL + Deribit + Kraken · days `['2026-09-26', '2026-09-27', '2026-09-30']`
- Detector: `hftpat.price_fade_*` (τ∈{50,100,250}ms, θ=0.2); `venue_fade_*` HL→DB lat=5ms τ=50ms
- **Kraken `trade_synth` excluded** from native TOB fade tests (labeled in JSON).
- **Not a rename** of `lob.tob_depletion_cancel_proxy` (post-trade conditional ≠ unconditional size-drop).

### Headlines (native TOB, complete days)
- **hyperliquid**: P(fade)@100ms mean=0.0193, n_fade=448, n_scored=22844, n_days=3
- **deribit**: P(fade)@100ms mean=0.00283, n_fade=56, n_scored=20800, n_days=3
- **kraken**: blocker=no_native_fade; trade_synth_excluded_days=3

- **Venue fade HL→DB**: P(fade) mean=0.009124427938133587, n_days=3 (lat=5.0ms, τ=50.0ms)

### Figures
- `out/book_fade/figs/fig_fade_p_tau.png`
- `out/book_fade/figs/fig_fade_venue_bars.png`
- `out/book_fade/figs/fig_venue_fade.png`

## Pass 2
- HL P(fade)@100ms=0.019385881444167377; markout_delta=-0.5051363259237963 bps; lob frac=0.01857024622387751
- DB P(fade)=0.0028303739750388675; Kraken native excluded
- Day early/late HL=0.004672290720311486/0.026742676806095322
- Labels: {'risk.price_fade_p': {'decision': 'Hold', 'monitor': True, 'tradable': False, 'exec_throttle': False, 'why': 'HL P(fade)@100ms≈0.019385881444167377; markout_delta≈-0.5051363259237963bps; lob frac≈0.01857024622387751; day early/late=0.004672290720311486/0.026742676806095322'}, 'risk.venue_fade_hl_db': {'decision': 'Hold', 'monitor': True, 'tradable': False, 'exec_throttle': True, 'why': 'Pass1 venue-fade retained; RTT haircut not Promote-ready'}, 'risk.fade_vs_lob_cancel': {'decision': 'Hold', 'monitor': True, 'tradable': False, 'exec_throttle': False, 'why': 'rename gate vs lob.tob_depletion_cancel_proxy'}}
- Artifacts: `out/pass2/book_fade.json`
- Decision: **Hold** MM-pull monitor (falsifiers documented; no Promote).

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
