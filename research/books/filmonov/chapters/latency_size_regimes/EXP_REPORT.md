# latency_size_regimes — EXP_REPORT

## Pass 1
- Slice: **ETH** · venues ['hyperliquid', 'deribit', 'kraken'] · days ['2026-09-26', '2026-09-27', '2026-09-30']
- Complete venue-days: **9/9**
- TOB venue-days: **9/9** (trade_synth=3)
- Detector: `hftpat.size_latency_panel` (trade-size quantiles + TOB Hz + median Δt + trade Hz)
- By venue (day-medians):

| Venue | complete | tob | median TOB Hz | median Δt ms | median size q50 | median trade Hz |
|-------|----------|-----|---------------|--------------|-----------------|-----------------|
| hyperliquid | 3/3 | 3 | 0.1863 | 5390 | 0.105 | 1.215 |
| deribit | 3/3 | 3 | 0.3236 | 2544 | 150 | 0.5678 |
| kraken | 3/3 | 3 | 0.1716 | 3242 | 0.02 | 0.9293 |

- Kill list applied: co-lo µs vanity (p.14), Hibernia (p.16), fiber distance table (p.15) — candidates marked **Kill**
- **Caveat:** TOB Hz / median Δt are **feed-sample** rates (warehouse `quotes_per_minute` / collector cadence), not exchange OE µs — do not map to deck co-lo RTT claims. HL 2026-09-30 uses denser collector TOB (Hz≈1.68). Kraken TOB is `trade_synth` (3/3 days) — size/Hz for KR are trade-proxy only.
- Deribit size units are **contracts** (q50≈110–200); HL/KR are coin qty — cross-venue size levels not directly comparable.
- Runner: [`../../scripts/exp_ch00_latency.py`](../../scripts/exp_ch00_latency.py)
- JSON: `out/latency_size_regimes/panel.json`, `summary.json`

## Pass 2
- TOB Hz by venue (feed-sample): {'hyperliquid': {'median_hz': 0.18625413738866262, 'bootstrap_ci': {'n': 3, 'point': 0.6830018392082849, 'lo': 0.18621356972160816, 'hi': 1.6765378105145838, 'alpha': 0.05, 'n_boot': 400}, 'early_median_hz': 0.18621356972160816, 'late_median_hz': 0.9313959739516232, 'n': 3}, 'deribit': {'median_hz': 0.3235863300504641, 'bootstrap_ci': {'n': 3, 'point': 0.32002266913124955, 'lo': 0.28872797076361695, 'hi': 0.3477537065796677, 'alpha': 0.05, 'n_boot': 400}, 'early_median_hz': 0.28872797076361695, 'late_median_hz': 0.33567001831506593, 'n': 3}, 'kraken': {'median_hz': 0.171561289773928, 'bootstrap_ci': {'n': 3, 'point': 0.16836803402847397, 'lo': 0.11174685312464909, 'hi': 0.2217959591868449, 'alpha': 0.05, 'n_boot': 400}, 'early_median_hz': 0.11174685312464909, 'late_median_hz': 0.19667862448038642, 'n': 3}}
- Early/late days: ['2026-09-26'] / ['2026-09-27', '2026-09-30']
- Regime panel **Hold** monitor; Kill co-lo/Hibernia/fiber vanity.
- Labels: {'mm.size_latency_regime_panel': {'decision': 'Hold', 'monitor': True, 'tradable': False, 'exec_throttle': False, 'why': 'feed-sample TOB Hz — hyperliquid med=0.1863; deribit med=0.3236; kraken med=0.1716'}, 'mm.trade_size_quantile_curve': {'decision': 'Hold', 'monitor': True, 'tradable': False, 'exec_throttle': False, 'why': 'size quantiles framing; units differ DB contracts vs coin'}, 'id.colo_rtt_40us_claim': {'decision': 'Kill', 'monitor': False, 'tradable': False, 'exec_throttle': False, 'why': 'NASDAQ co-lo µs vanity'}, 'id.hibernia_express_6ms': {'decision': 'Kill', 'monitor': False, 'tradable': False, 'exec_throttle': False, 'why': 'Hibernia Express vanity'}, 'id.fiber_distance_table': {'decision': 'Kill', 'monitor': False, 'tradable': False, 'exec_throttle': False, 'why': 'fiber distance table vanity'}}
- Artifacts: `out/pass2/ch00_latency.json`

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
