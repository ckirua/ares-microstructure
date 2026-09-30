# Ch.13 VAR / IRF / OFI — ETH

## Sample
- alignment=`next_mid_change` · n_event=35,044 · corr(Δm,q)=0.4773
- days=['2026-09-28', '2026-09-29', '2026-09-30'] · median lag to mid-change=766.7 ms

## Impact / IRF
- λ_VAR=0.02695 · λ_OLS=0.19919 · train=0.18155 · test=0.24038
- OLS bootstrap 95% CI=[0.19526, 0.20265] · promote_ok=True
- permanent_IRF=0.4218 (train=0.3778, test=0.4138)
- VAR R²_Δm=0.874 · R²_q=0.458

## Sign / OFI / markout
- sign ρ₁=0.5350
- OFI corr(ofi,r)=0.4341 (scatter recompute corr=0.4286)
- markout 1s: mean=0.4719 bps · CI95=[0.4634, 0.4812] · n=57,136
- markout 0.5s=0.0926 · 5s=0.7148 bps

## Alignment robustness
- pre_to_next_trade corr=0.1096 (n=57,254)
- quote_clock corr=0.2789 (n=2,572)

## Decisions
- `disc.var_lambda`: **Promote** — λ≤0 on full/train/test or bootstrap CI lo≤0
- `disc.irf_permanent`: **Promote** — cum IRF → 0, opposite sign to λ, or train/test sign flip
- `disc.sign_acf`: **Promote** — ρ₁(q) ≤ 0 (no clustering)
- `cont.ofi_mid_corr`: **Promote** — corr(OFI, r) CI includes 0
- `info.markout_1s`: **Promote** — 1s markout CI ≤ 0

## Figures
- `out/ch13_var_impact/fig_irf_cum.png`
- `out/ch13_var_impact/fig_sign_acf.png`
- `out/ch13_var_impact/fig_markout.png`
- `out/ch13_var_impact/fig_lambda_hygiene.png`
- `out/ch13_var_impact/fig_alignment_corr.png`
- `out/ch13_var_impact/fig_ofi_scatter.png`
- `out/ch13_var_impact/fig_var_coef.png`

## Desk / second-pass read
- Cum IRF rises smoothly to ~0.42 with train/test same sign ⇒ permanent impact prior for TCA/POV.
- ρ₁(q)≈0.54 ⇒ herding / inventory continuation; pair with Ch.14 MRR ρ and Ch.15 VPIN regimes.
- OFI corr≈0.43 on 1s bars is the continuous twin of disc λ; use when TOB dense.
- Primary alignment corr≈0.48 vs contaminated asof (historically λ_VAR<0) — never skip quote-update align.
- Markout CI strictly >0 at 0.5/1/5s ⇒ maker AS / taker edge decay object for quoting.
