# Ch.17 price discovery — ETH

## Sample
- Aligned 1s mids n=52,837 (IS subsample n=26,419)
- Overlap window mutual HL∩Lit TOB

## Information share (Hasbrouck bounds)
- HL: [0.34341121935333296, 0.966626843036892]
- Lit: [0.03337315696310805, 0.656588780646667]
- ordering_ab: {'a': 0.34341121935333296, 'b': 0.6565887806466669}
- ordering_ba: {'a': 0.966626843036892, 'b': 0.03337315696310801}
- ok=True lags=5

## Epps curve
  - lag=1.0s  corr=0.1017  n=52835
  - lag=5.0s  corr=0.6073  n=10567
  - lag=15.0s  corr=0.8085  n=3522
  - lag=60.0s  corr=0.9366  n=880
  - lag=300.0s  corr=0.9889  n=176

## Jump / lead–lag
- Contemporaneous sign concordance (p90 HL |Δm|): 0.5608
  - k=0: concord=0.5608  n_big=5287
  - k=1: concord=0.5608  n_big=5287
  - k=2: concord=0.5672  n_big=5287
  - k=5: concord=0.5612  n_big=5287
  - k=10: concord=0.5287  n_big=5287

## Basis (HL−Lit)/HL bps
- median=5.4387  mean=5.4340  std=1.4269
- p05=3.0876  p95=7.7233

## Decisions
- `cont.info_share_hl_lit`: **Promote** — IS bounds collapse to [0,1] noise or Ψ singular
- `cont.epps_xvenue`: **Promote** — corr flat in lag (no Epps) on overlapping window
- `disc.jump_sign_concord`: **Promote** — concordance ≈ 0.5 on large HL moves

## Figures
- `out/ch17_discovery/fig_epps_curve.png`
- `out/ch17_discovery/fig_info_share_bounds.png`
- `out/ch17_discovery/fig_basis.png`
- `out/ch17_discovery/fig_jump_leadlag.png`

## Desk / second-pass read
- Rising Epps corr with lag ⇒ asynchronicity; use lag where corr≳0.8 as sync horizon for hedges.
- Wide IS bounds ⇒ residual correlation; report interval, not a point weight for SOR.
- Lead–lag concordance climbing in k means Lit catches HL jumps within a few seconds — complementary to IS, not a substitute.
- HL vs Lit here ≠ equity lit/dark; both are continuous LOB perps with collector-clock mids.
