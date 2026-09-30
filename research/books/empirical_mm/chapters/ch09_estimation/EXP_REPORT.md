# Ch.9 estimation case — ETH

## Sample
- n_event=116,949 · n_Δp=116,948 · days=['2026-09-28', '2026-09-29', '2026-09-30']

## Roll vs MA/AR
- Roll mid identified=False g1=0.0004404168977769924 · Roll px identified=True
- MA(1) mid identified=True θ=0.028935839247007024 σ_w=4.7212237187093826e-05 σ_s=1.32770737846693e-06
- MA(1) px identified=True θ=-0.005344917924484329 σ_w=4.0874405428374475e-05
- AR(3) φ(1)=0.9360759358579498 σ_w=4.899898204320778e-05
- AR(10) φ(1)=0.8923913243986175 σ_e=4.585999276534043e-05 σ_w=5.139000291855759e-05 (train=4.81569081147044e-05, test=5.8281585601635244e-05)
- Day-block σ_w mean±SE=4.71141596399295e-05±4.548814835581829e-06 (n_blocks=2)
- Calendar 1s AR(10) σ_w=8.120251705392395e-05
- IRF cum@20=1.1203998413909746
- Quoted spread bps point=0.3884749104129241 CI=[0.3875381848225953, 0.38944492840972855]
- Noise RV ratio=0.8692209322328741 · block-boot CI95≈[0.867, 0.905] (n_blocks=24) → **Kill**

## Variance ratios (second pass)
### Event Δlog mid
  - q=1: VR=1.0000  n=116948
  - q=2: VR=1.0289  n=116947
  - q=5: VR=1.0873  n=116944
  - q=10: VR=1.1416  n=116939
  - q=20: VR=1.2219  n=116929
  - q=50: VR=1.3245  n=116899
  - q=100: VR=1.4201  n=116849
### Calendar 1s
  - q=1: VR=1.0000  n=64166
  - q=2: VR=1.1317  n=64165
  - q=5: VR=1.2997  n=64162
  - q=10: VR=1.4063  n=64157
  - q=30: VR=1.5881  n=64137
  - q=60: VR=1.6809  n=64107

## AR lag sweep σ_w
- K=1:4.725e-05, K=2:4.828e-05, K=3:4.900e-05, K=5:4.958e-05, K=10:5.139e-05, K=15:5.280e-05, K=20:5.356e-05, K=30:5.416e-05

## Decisions
- `disc.ma1_moments`: **Promote**
- `disc.ar_sigma_w`: **Promote**
- `disc.roll_vs_quote`: **Kill**
- `cont.noise_rv_ratio`: **Kill**

## Figures
- `out/ch09_estimation/fig_return_acf.png`
- `out/ch09_estimation/fig_sigma_w_compare.png`
- `out/ch09_estimation/fig_ar_irf.png`
- `out/ch09_estimation/fig_variance_ratio.png`
- `out/ch09_estimation/fig_ar_lag_sweep.png`

## Desk / second-pass read
- BN σ_w is the permanent-vol prior when Roll Kill; prefer AR(10) + day-block SE over delta-method.
- VR(q)≠1 ⇒ naive √T scaling of event variance is wrong for TCA / risk — use MA/AR structure.
- Lag truncation moves σ_w; publish the sweep, not a single K.
- Ch.4 toolkit (MA↔AR invertibility, φ(1) only for σ_w) is the estimation hygiene for this chapter.
