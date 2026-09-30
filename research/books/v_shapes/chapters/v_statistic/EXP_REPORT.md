# V-statistic — EXP_REPORT (Pass 1+2)

## Sample
- Symbol: `ETH`
- Days: ['2026-09-28', '2026-09-29', '2026-09-30']
- Venues: HL + Deribit + Kraken
- Grid: 5s last-print (desk speed; paper uses 1s); hn in {1,5,30} min; EGARCH bootstrap

## Per-venue / day MinV
- hyperliquid 2026-09-28 hn=1m: MinV=-11.967 shape=V sig5=False sig1=False complete=False n=14078 coverage_grid=0.97
- hyperliquid 2026-09-28 hn=5m: MinV=-44.080 shape=Lambda sig5=False sig1=False complete=False n=14078 coverage_grid=0.97
- hyperliquid 2026-09-28 hn=5_preavg5m: MinV=-97.640 shape=Lambda sig5=True sig1=False complete=False n=14078 coverage_grid=0.97
- hyperliquid 2026-09-28 hn=30m: MinV=-282.527 shape=V sig5=True sig1=True complete=False n=14078 coverage_grid=0.97
- hyperliquid 2026-09-29 hn=1m: MinV=-11.158 shape=Lambda sig5=False sig1=False complete=False n=3845 coverage_grid=0.97
- hyperliquid 2026-09-29 hn=5m: MinV=-29.326 shape=V sig5=False sig1=False complete=False n=3845 coverage_grid=0.97
- hyperliquid 2026-09-29 hn=5_preavg5m: MinV=-88.569 shape=V sig5=False sig1=False complete=False n=3845 coverage_grid=0.97
- hyperliquid 2026-09-29 hn=30m: MinV=-180.291 shape=Lambda sig5=True sig1=True complete=False n=3845 coverage_grid=0.97
- hyperliquid 2026-09-30 hn=1m: MinV=-17.831 shape=V sig5=False sig1=False complete=True n=139514 coverage_grid=0.97
- hyperliquid 2026-09-30 hn=5m: MinV=-56.804 shape=Lambda sig5=False sig1=False complete=True n=139514 coverage_grid=0.97
- hyperliquid 2026-09-30 hn=5_preavg5m: MinV=-214.728 shape=Lambda sig5=True sig1=True complete=True n=139514 coverage_grid=0.97
- hyperliquid 2026-09-30 hn=30m: MinV=-146.447 shape=Lambda sig5=False sig1=False complete=True n=139514 coverage_grid=0.97
- deribit 2026-09-28 hn=1m: MinV=-21.034 shape=Lambda sig5=False sig1=False complete=False n=4671 coverage_grid=0.45
- deribit 2026-09-28 hn=5m: MinV=-31.233 shape=Lambda sig5=False sig1=False complete=False n=4671 coverage_grid=0.45
- deribit 2026-09-28 hn=5_preavg5m: MinV=-85.094 shape=Lambda sig5=True sig1=True complete=False n=4671 coverage_grid=0.45
- deribit 2026-09-28 hn=30m: MinV=-178.185 shape=V sig5=False sig1=False complete=False n=4671 coverage_grid=0.45
- deribit 2026-09-29 hn=1m: MinV=-15.958 shape=Lambda sig5=False sig1=False complete=False n=3063 coverage_grid=0.47
- deribit 2026-09-29 hn=5m: MinV=-37.220 shape=V sig5=False sig1=False complete=False n=3063 coverage_grid=0.47
- deribit 2026-09-29 hn=5_preavg5m: MinV=-124.388 shape=V sig5=True sig1=True complete=False n=3063 coverage_grid=0.47
- deribit 2026-09-29 hn=30m: MinV=-100.157 shape=Lambda sig5=False sig1=False complete=False n=3063 coverage_grid=0.47
- deribit 2026-09-30 hn=1m: MinV=-17.276 shape=V sig5=False sig1=False complete=True n=73767 coverage_grid=0.67
- deribit 2026-09-30 hn=5m: MinV=-86.551 shape=Lambda sig5=True sig1=True complete=True n=73767 coverage_grid=0.67
- deribit 2026-09-30 hn=5_preavg5m: MinV=-275.658 shape=Lambda sig5=True sig1=True complete=True n=73767 coverage_grid=0.67
- deribit 2026-09-30 hn=30m: MinV=-82.507 shape=Lambda sig5=False sig1=False complete=True n=73767 coverage_grid=0.67
- kraken 2026-09-28 hn=1m: MinV=-39.502 shape=V sig5=True sig1=True complete=False n=4956 coverage_grid=0.49
- kraken 2026-09-28 hn=5m: MinV=-29.397 shape=Lambda sig5=False sig1=False complete=False n=4956 coverage_grid=0.49
- kraken 2026-09-28 hn=5_preavg5m: MinV=-50.030 shape=V sig5=False sig1=False complete=False n=4956 coverage_grid=0.49
- kraken 2026-09-28 hn=30m: MinV=-178.201 shape=V sig5=True sig1=True complete=False n=4956 coverage_grid=0.49
- kraken 2026-09-29 hn=1m: MinV=-11.897 shape=Lambda sig5=False sig1=False complete=False n=3044 coverage_grid=0.73
- kraken 2026-09-29 hn=5m: MinV=-25.018 shape=Lambda sig5=False sig1=False complete=False n=3044 coverage_grid=0.73
- kraken 2026-09-29 hn=5_preavg5m: MinV=-81.331 shape=Lambda sig5=False sig1=False complete=False n=3044 coverage_grid=0.73
- kraken 2026-09-29 hn=30m: MinV=-122.490 shape=Lambda sig5=True sig1=False complete=False n=3044 coverage_grid=0.73
- kraken 2026-09-30 hn=1m: MinV=-16.267 shape=V sig5=False sig1=False complete=True n=81552 coverage_grid=0.67
- kraken 2026-09-30 hn=5m: MinV=-56.518 shape=Lambda sig5=False sig1=False complete=True n=81552 coverage_grid=0.67
- kraken 2026-09-30 hn=5_preavg5m: MinV=-202.632 shape=Lambda sig5=True sig1=True complete=True n=81552 coverage_grid=0.67
- kraken 2026-09-30 hn=30m: MinV=-69.618 shape=V sig5=False sig1=False complete=True n=81552 coverage_grid=0.67

## Pass 2 notes
- Continuous V_t summaries (V_mean, V_p10) and lead-lag vs future r^2 in JSON.
- Pre-avg sensitivity: key `5_preavg5` vs `5`.
- Asymptotic bands 2.18/3.60: **Kill** as desk defaults (see bootstrap_sim).

## Figures / artifacts
- `out/v_statistic/panel_eth.json`

## Certification
- UTC-day clip + day-completeness flags from `scripts/_data.py`.
- Incomplete days flagged; do not Promote on thin tails alone.

## Continuous V_t Pass-2 (widen)
- Artifacts: `out/v_statistic/continuous_v_eth.json`, `continuous_v_btc.json`.
- Lead-lag of `corr_V_*` vs forward mid returns / r²: mean_corr_V≈0.02, CI includes 0 → **Hold** `info.v_path_continuous` (no soft-Promote from pooled T±).
