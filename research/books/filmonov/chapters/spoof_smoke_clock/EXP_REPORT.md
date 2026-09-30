# spoof_smoke_clock — EXP_REPORT

## Pass 1 — ETH · HL + Deribit + Kraken

**Script:** `scripts/exp_spoof_clock.py`  
**Artifacts:** `out/spoof_smoke_clock/pass1.json` · `summary.json` · `completeness.json` · `figs/`

### Sample / window
| Field | Value |
|-------|-------|
| Symbol | ETH |
| Days | 2026-09-26, 2026-09-27, 2026-09-30 (UTC) |
| Venues | hyperliquid, deribit, kraken |
| Venue-days OK | **9 / 9** |
| Complete (coverage gates) | **9 / 9** |
| Kraken `trade_synth` TOB | **3 / 3** days (flagged; excluded from Promote) |
| Primary `cancel_ms` | **2000** (grid also 200, 500) |
| Clock | bin_ms=1000, z_thresh=3 |
| Placebos | n=2 time-shifts per venue-day |

### Day completeness
All nine venue-days pass `_data.day_completeness` (clipped, n≥500, span≥6h, coverage≥0.25). Coverage range ≈0.49–0.998. Thin-coverage recent listing-cache days (09-28/29) deliberately **not** used for headline Pass 1.

### Smoke / layer (deck 29–30) — frank FP rates
Primary window `cancel_ms=2000` (deck 200 ms almost never fires on sparse crypto TOB).

| Venue-day | n_smoke | n_layer | hit_rate (smoke/improves) | smoke FP contam (plac/obs) | surplus share |
|-----------|---------|---------|---------------------------|----------------------------|---------------|
| HL 09-26 | 0 | 0 | 0 | — | — |
| DB 09-26 | 398 | 143 | 0.037 | **2.03** | **0** |
| KR 09-26 | 0 | 0 | 0 | — (synth) | — |
| HL 09-27 | 0 | 0 | 0 | — | — |
| DB 09-27 | 346 | 79 | 0.054 | **1.53** | **0** |
| KR 09-27 | 0 | 0 | 0 | — (synth) | — |
| HL 09-30 | 610 | 0 | 0.063 | **1.67** | **0** |
| DB 09-30 | 9 | 3 | 0.041 | **1.94** | **0** |
| KR 09-30 | 0 | 0 | 0 | — (synth) | — |

**Headline FP (n_smoke>0, n=4):** mean smoke FP contamination **1.79** (placebo ≥ observed); mean surplus share **0.0**; mean hit rate among touch improves **≈4.9%**.  
**cancel_ms=200:** essentially zero hits everywhere. **500:** rare hits with contam ≥1.  
→ **Kill** as prosecution / α detector; Hold only as unlabeled risk cartoon.

### Clock cluster (deck 35–36)
| Metric | Value |
|--------|-------|
| Mean max_z vs uniform | **≈22.3** |
| Mean n_excess bins (z≥3) | **≈13.2** |
| Placebo (uniform within-minute offsets) n_excess | **0** on all 9 days |
| Excess vs placebo | **≈13.2** |

Strong clock excess vs uniform null survives shuffle placebo → **Hold** as algo-hunter / TWAP-pattern **monitor**, not tradable.

### OTR aggregate (deck 41–43) — policy only
| Venue | mean day OTR (cancel_proxy / trades) |
|-------|--------------------------------------|
| hyperliquid | **≈0.29** |
| deribit | **≈0.36** |
| kraken | **0.00** (`trade_synth` — no meaningful cancel proxy) |

`otr_aggregate(..., policy_only=True)`. **Kill** participant-level OTR without firm IDs.

### Figures (≥3)
- `out/spoof_smoke_clock/figs/fig_smoke_fp_rates.png`
- `out/spoof_smoke_clock/figs/fig_clock_cluster.png`
- `out/spoof_smoke_clock/figs/fig_otr_regimes.png`
- `out/spoof_smoke_clock/figs/fig_completeness_fp.png`

### Blockers
1. No firm IDs → smoke/layer unlabeled; placebo ≥ obs ⇒ FP-dominated.
2. Kraken native TOB missing → synth flagged.
3. Equity-style 200 ms smoking window does not transfer to crypto L0 cadence.
4. OTR is cancel-*proxy* over TOB size drops, not exchange OE message counts.

## Pass 2
- Smoke FP contam≈1.7947859169606946 → **Kill**
- Clock max_z bootstrap CI={'n': 9, 'point': 22.30706778053844, 'lo': 15.949451381302355, 'hi': 29.574629928536698, 'alpha': 0.05, 'n_boot': 400} → **Hold** monitor
- Labels: {'spoof.smoke_proxy': {'decision': 'Kill', 'monitor': False, 'tradable': False, 'exec_throttle': False, 'why': 'FP contam≈1.79 (placebo≥obs); unlabeled without firm IDs'}, 'spoof.layer_proxy': {'decision': 'Kill', 'monitor': False, 'tradable': False, 'exec_throttle': False, 'why': 'same FP contamination; Hold only as deck cartoon'}, 'spoof.clock_cluster': {'decision': 'Hold', 'monitor': True, 'tradable': False, 'exec_throttle': False, 'why': 'max_z mean≈22.30706778053844; early/late max_z=25.9813825659611/20.46991038782711; shuffle placebo n_excess=0'}, 'spoof.otr_venue': {'decision': 'Hold', 'monitor': True, 'tradable': False, 'exec_throttle': False, 'why': 'venue cancel_proxy/trade aggregates — policy-only; Kill participant OTR'}, 'spoof.tape_paint': {'decision': 'Kill', 'monitor': False, 'tradable': False, 'exec_throttle': False, 'why': 'Nanex equity cartoon; no crypto OE cancel-after-print ID path'}}
- Artifacts: `out/pass2/spoof_smoke_clock.json`

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
