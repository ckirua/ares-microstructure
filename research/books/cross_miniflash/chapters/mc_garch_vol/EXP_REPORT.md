# MC-GARCH vol — EXP_REPORT

## Sample
Same Phase 2 vertical slice: 7 UTC days × ETH/BTC × 3 venues (42 complete cells).  
MC-GARCH fit per cell; diurnal \(s_j\) averaged across pooled cells.

## Pass 1 fit diagnostics
- Typical bars/day ≈280–288 (empty bars dropped in return construction)
- Composite median order \(10^{-6}\) (log-return variance per 5m)
- noise_ref: MAD(\(\Delta\log p\)) floored at \(10^{-4}\)

## Pass 2 results
- Hour-share peak UTC **12** (max share≈0.091)
- σ_m frac stress: 0.5/1/2/4 → **13832 / 3668 / 808 / 177** SSM events @ z*=6
- Link: mmip `vol.curve_intraday` (U≈0.56, peak ~18 UTC on HL 09-14…26) ≠ this cohort’s peak 12 — **Hold** joint Promote

## ID assumptions
- Single-day \(h_n\) = intraday RV (not multi-day GARCH MLE) — sufficient for KF feed; Hold “daily GARCH forecasting” claim
- Sparse 5m slots inflate \(s_j\) — report slot occupancy in hardening

## Decisions
- Promote `vol.sigma_m_noise_floor_1bp`
- Hold diurnal / frac defaults pending longer panel

## Figures
- `figs/fig_diurnal_vs_crashes.png`
- `figs/fig_hour_share.png`
- `figs/fig_sigma_m_stress.png`
