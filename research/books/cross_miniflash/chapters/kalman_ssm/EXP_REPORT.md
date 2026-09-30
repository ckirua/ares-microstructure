# Kalman SSM — EXP_REPORT

## Sample
- 2026-09-04…10 · ETH+BTC · HL+Deribit+Kraken · 42 complete cells  
- σ_m_frac=1.0 · noise_floor_log=1e-4 · z*=6 primary  
- Script: `scripts/exp_phase2_baselines_ssm.py`

## Pass 1 results
| Venue | SSM (z*=6) | Nanex 30bps |
|-------|-----------:|------------:|
| hyperliquid | 3075 | 70 |
| deribit | 349 | 13 |
| kraken | 244 | 22 |
| **TOTAL** | **3668** | **105** |

Overlap: 94/105 Nanex events hit SSM (precision 0.895).

## Pass 2
- z* scan: 2→36416, 6→3668, 12→630 events  
- σ_m frac: 0.5→13832, 1→3668, 2→808, 4→177  
- Lead–lag innov→future Δlog: |corr|≤0.04 for lag∈{0.5,1,2}s  
- Time-split SSM: early 2055 / late 1868

## ID / certification
- KF on UTC-clipped warehouse trades; preferred-shard max_files=24  
- z-score = standardized innovation (documented crypto fix)  
- Incomplete-day cells would be excluded — none in this panel

## Decisions
- Promote `risk.ssm_zstar_scan_table`  
- Hold binary SSM + continuous innov as tradable  
- Kill vanity “z*=6 equity default ports to crypto unchanged”

## Figures
- `figs/fig_zstar_scan.png`
- `figs/fig_innov_leadlag.png`
- `figs/fig_nanex_vs_ssm_venue.png`

## Blockers → Phase 3 (`crash_stats` / `cross_section`)
- Severity filter: drop \(\Delta P\approx0\) micro-flags  
- Ex-ante OI/vol predictors of SSM intensity  
- Cross-venue concordance of event timestamps
