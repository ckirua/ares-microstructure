# Ch.8 univariate RW / noise — ETH

Paired empirics with Ch.3 (`out/ch03_roll/`). Cont candidates only here.

## Cont results
- noise_ratio RV_fine/RV_coarse = **0.8692**
- RV curve (sum r²): 100ms=2.299e-04, 500ms=2.343e-04, 1s=2.645e-04, 5s=3.418e-04, 30s=4.279e-04
- calendar AC1=0.1317 · volclock AC1=0.0545

## Decisions
- `cont.noise_rv_ratio`: **Hold** — RV_fine/RV_coarse ≤ 1 on dense collector (no bounce inflation)
- `cont.volclock_ac1`: **Hold** — AC1 indistinguishable across calendar vs volume clocks

## Figures
- `out/ch08_noise/fig_noise_rv_curve.png`
- `out/ch08_noise/fig_clock_acf.png`

## BN / pricing-error link
- Roll Kill (γ1≥0) ⇒ MA(1) bounce parameterization fails; efficient-innovation σ_w still recoverable via AR truncation (see Ch.9 `disc.ar_sigma_w`).
- Fine/coarse RV is a **sampling-noise** diagnostic, not the BN pricing-error variance bound — do not equate them.
