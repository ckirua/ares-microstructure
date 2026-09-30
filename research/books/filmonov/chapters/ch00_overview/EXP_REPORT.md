# ch00_overview — EXP_REPORT

## Pass 1
- Slice: **ETH** · venues ['hyperliquid', 'deribit', 'kraken'] · days ['2026-09-26', '2026-09-27', '2026-09-30']
- Complete venue-days: **9/9** → [`hyperliquid/2026-09-26`, `deribit/2026-09-26`, `kraken/2026-09-26`, `hyperliquid/2026-09-27`, `deribit/2026-09-27`, `kraken/2026-09-27`, `hyperliquid/2026-09-30`, `deribit/2026-09-30`, `kraken/2026-09-30`]
- TOB venue-days: **9/9** (trade_synth=3)
- Taxonomy: SEC attrs (p. 9) + strategy map (p. 17) → package reading order locked
- Sibling reuse: crash / vstat / lob / ticksize / mmip Hawkes — cross-link only (see `out/ch00_overview/sibling_reuse.json`)
- Runner: [`../../scripts/exp_ch00_latency.py`](../../scripts/exp_ch00_latency.py)

## Pass 2
- Taxonomy **Hold** (labels useful; not beyond crash/mmip Promote bar).
- Kill: Hibernia / co-lo vanity; fee-free FX triangle.
- Labels: {'disc.hft_taxonomy_tile': {'decision': 'Hold', 'monitor': True, 'tradable': False, 'exec_throttle': False, 'why': 'taxonomy framing useful but does not clear rename-beyond-crash/mmip Promote bar'}, 'disc.sec_attr_crypto_map': {'decision': 'Hold', 'monitor': True, 'tradable': False, 'exec_throttle': False, 'why': 'co-lo / flat-EOD attrs unobservable on public tape'}, 'id.colo_hibernia_vanity': {'decision': 'Kill', 'monitor': False, 'tradable': False, 'exec_throttle': False, 'why': 'equity co-lo / Hibernia without crypto RTT panel'}, 'id.fx_triangle_fee_free': {'decision': 'Kill', 'monitor': False, 'tradable': False, 'exec_throttle': False, 'why': 'fee-free FX triangle vanity'}}
- Artifacts: `out/pass2/ch00_latency.json`

## Pass 2.5 hardening
- Day-block bootstrap ETH+BTC → `out/hardening/`
- Early/late: ['2026-09-26'] / ['2026-09-27', '2026-09-30']
- Program freeze: **0 Promote / 13 Hold / 11 Kill**
- Boots: `{"hl_storms_per_hour": {"boot": {"n": 3, "point": 0.5294467018620957, "lo": 0.0, "hi": 1.5883401055862876, "alpha": 0.05, "n_boot": 500}, "early_mean": 0.0, "late_mean": 0.7941700527931437, "n": 3, "btc_mean": 0.5294391320374869}, "hl_p_fade_100ms": {"boot": {"n": 3, "point": 0.0194400253855552, "lo": 0.003980616130148841, "hi": 0.048213081591368855, "alpha": 0.05, "n_boot": 500}, "early_mean": 0.003980616130148841, "late_mean": 0.027169730013258377, "n": 3, "btc_mean": 0.024681680355299555}, "h…`
