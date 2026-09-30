# Ch.3 / Ch.8 Roll & noise — ETH

## Sample
- Days: ['2026-09-28', '2026-09-29', '2026-09-30'] · trades=116,949 · mids=104,926

## Disc — Roll identification
- event-mid: identified=False  g0=0.015280894025784569  g1=0.0004404168977769924  spread_bps=nan
- trade-px: identified=True  g0=0.01223483936901434  g1=-6.738157916157323e-05
- calendar subsample: identified=False  g1=0.004974107485238196
- train/test identified=False/False
- event AC1(Δmid)=0.0288

## Cont — noise & clocks
- RV_fine(100ms)=0.00022990122878072624  RV_coarse(1s)=0.00026449113252501966  **noise_ratio=0.8692**
- calendar 1s AC1=0.1317 · volclock AC1=0.0545 · bar_volume=3.845 · n_vol=66,245

## Decisions
- `disc.roll_event_mid`: **Kill** — γ₁≥0 on held-out half (unidentified) or spread_bps ≫ quoted
- `disc.roll_trade_px`: **Hold** — γ₁≥0 (bounce absent / dominated by drift)
- `cont.noise_rv_ratio`: **Kill** — RV_fine/RV_coarse ≤ 1 on dense collector (no bounce inflation)
- `cont.volclock_ac1`: **Hold** — AC1 indistinguishable across calendar vs volume clocks

## Figures
- `out/ch03_roll/fig_roll_acov.png`
- `out/ch03_roll/fig_roll_id_map.png`
- `out/ch03_roll/fig_noise_rv_curve.png`
- `out/ch03_roll/fig_clock_acf.png`
- `out/ch03_roll/fig_mid_path.png`

## Desk / second-pass read
- γ1 ≥ 0 on mid **and** trade px ⇒ classic Roll bounce is **not** the dominant Δp structure on HL collector tape (sign herding / drift / continuous mid).
- noise_ratio ≈ 0.87 < 1 ⇒ fine sampling does **not** inflate RV — collector mid is not bounce-dominated; Hold as diagnostic, not alpha.
- Volume-clock AC1 (0.055) vs calendar (0.132) same order ⇒ clock choice does not unlock a tradable ACF feature alone.
