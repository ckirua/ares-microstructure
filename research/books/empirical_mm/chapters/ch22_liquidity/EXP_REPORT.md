# Ch.22 liquidity / Amihud — ETH

## Point estimates
- Amihud ILLIQ (1m): n=781  ILLIQ=4.701704e-09  CI95=[3.924772827485599e-09, 5.721399888853766e-09]
- Quoted spread (bps): n=84585  point=0.3820  CI95=[0.3814, 0.3827]
- Effective spread (bps): n=62371  point=0.9372923487659395
- VPIN companion (same tape): mean=0.9110895262875583  n_buckets=9797
- Sample trades n=62,371  days=['2026-09-26', '2026-09-27', '2026-09-28', '2026-09-29', '2026-09-30']

## Turnover / activity
- median $vol / 1m bar = 1.22e+05
- mean trades / 1m bar = 79.77
- mean |r| / 1m = 0.000310797

## Daily ILLIQ
  - day[0]: ILLIQ=7.0362e-09  n_bars=82  sum_$vol=2.21e+07
  - day[1]: ILLIQ=4.4278e-09  n_bars=699  sum_$vol=2.49e+08

## Decisions
- `liq.amihud_1m`: **Promote** — falsifier: ILLIQ≈0 or unstable across days
- `liq.quoted_spread_bps`: **Promote** — falsifier: non-finite / empty TOB

## Figures
- `out/ch22_liquidity/fig_amihud_ts.png`
- `out/ch22_liquidity/fig_amihud_dist_daily.png`
- `out/ch22_liquidity/fig_quoted_spread.png`
- `out/ch22_liquidity/fig_illiq_vs_spread_vpin.png`
- `out/ch22_liquidity/fig_turnover.png`

## Desk read
- Spread ~0.38 bps is the MM/taker **tightness** floor on this window.
- ILLIQ ~4.70e-09 is **impact per dollar**; watch daily rank, not equity-comparable level.
- Effective vs quoted: eff=0.9372923487659395 vs qs=0.3820 — gap flags mid-join / AS at touch.
- Crypto caveat: 24/7 1m bars ≠ CRSP daily Amihud; venue=HL only (not consolidated).
