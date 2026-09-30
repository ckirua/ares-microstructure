# Ch.14 GH / MRR / Huang–Stoll — ETH

## Sample
- Quote-aligned Δm shared with Ch.13 (`next_mid_change`); days=['2026-09-28', '2026-09-29', '2026-09-30']
- GH/HS aligned n≈35,044 · MRR/HS-decomp on trade Δp n≈57,253
- HS decomp half-spread median=0.049999999999954525 (source=quoted)

## Glosten–Harris
- z₀=0.1886 · z₁=3.808900e-04 · R²=0.237
- train z₀=0.1697 · test z₀=0.2320

## MRR
- θ=0.03351 · φ=0.01595 · ρ_q=0.535 · R²=0.174
  (note: HS-decomp companion MRR on consecutive Δp; earlier mid-aligned pass had smaller θ)

## Huang–Stoll
- Lump π̂ (quote-aligned)=0.1899 · R²=0.206 (train=0.1693, test=0.2378)
- Asof-mid basic π̂ (decomp script)=0.011468394669274724 · R²=0.011446501854736835 — weaker; prefer quote-aligned lump
- Two-way λ̂=a+b=0.3117 · R²₂=0.174
- Three-way a(AS)=-0.1874 · b(inv)=0.4635 · as_share=-0.679 · R²₃=0.176
- Free-S two-way λ=0.3151

## Decisions
- `disc.gh_z0`: **Promote** — z0≤0 on test half or R²≈0
- `disc.mrr_theta`: **Promote** — θ≤0 or unidentified ρ
- `disc.mrr_rho_q`: **Hold** — ρ≃0.55–0.68 train/test (always high; not tradable alone)
- `disc.hs_pi`: **Promote** — π≤0 on a split or R²<1% (α|β not separately ID'd)
- `disc.hs_as_inv_split`: **Hold** — â<0 / clock-unstable after GMM+restricted dig

## Blockers
- Three-way HS split not Promote-ready (see α|β dig below: primary OLS â≈−0.18).

## Figures
- `out/ch14_structural/fig_gh_z0.png`
- `out/ch14_structural/fig_mrr_decomp.png`
- `out/ch14_structural/fig_hs_pi.png`
- `out/ch14_structural/fig_hs_decomp.png`
- `out/ch14_structural/fig_perm_impact_compare.png`
- `out/ch14_structural/fig_gh_size_bins.png`

## Desk / second-pass read
- GH z₀>0 on both halves with R²≈24% — AS intercept usable; z₁ tiny ⇒ size-skew from GH alone is weak.
- MRR θ>0 / φ temporary — schedule prior; ρ(q)≈0.54–0.60 is descriptive (Hold as discovery).
- HS lump π Promote on quote-aligned path; three-way â(AS)<0 ⇒ no clean dealer inventory split on HL LOB.
- Cross-link Ch.13: IRF perm / λ_OLS are mid-path impact; MRR/HS two-way are trade-price — same sign family.
- Cross-link Ch.15: high ρ(q) + VPIN regimes are the sequential-toxicity twin of structural AS.

# Ch.14 Huang–Stoll α|β dig — ETH

- Sample n_event=116,948 · median half-spread=0.050000 · vol_bucket=3.845
- Basic π̂ (lump α+β)=0.010178114872549042 R²=0.00677925581949268
- Primary method=ols_three_way+gmm_overid_price_mid: â=-0.18039671098921042 b̂=0.4056862999135994
- Free-S two-way λ=0.3487407253733782 β_ΔQ=0.05553446364717963
- Inventory proxy: π_q=0.01021386000386113 γ=-4.6307763897520916e-08 R²=0.006806155994312335 (label=proxy)
- MRR ρ: full=0.5971130387501131 train=0.5506172554795513 test=0.6835854261317946 signed_vol_ρ=0.22035277970151113

## Clocks
- `quote_clock`: OLS â=-4.24665813625793 b̂=6.180025996161481 λ=2.207234158283193 share=-2.1965080853623906 · GMM â=-4.112167078682909 b̂=5.963680834317678 (gmm_overid_price_mid) · restr â_raw=-3.653506582463973 â=0.0 bind=True · split_ok=False
- `trade_time_sign`: OLS â=-0.18039671098921042 b̂=0.4056862999135994 λ=0.38734258271113076 share=-0.8007325675832923 · GMM â=-0.27212968264234655 b̂=0.48727196295040454 (gmm_overid_price_mid) · restr â_raw=-0.06539573328035067 â=0.0 bind=True · split_ok=False
- `trade_time_signed_volume`: OLS â=0.0001813007885997863 b̂=0.9995282342926 λ=0.0003401093883269795 share=0.0001813534654193935 · GMM â=-0.06142483433241083 b̂=0.3476837303425455 (gmm_overid_price_mid) · restr â_raw=0.0004056488942224818 â=0.0003401093883269795 bind=True · split_ok=True
- `volume_bucket_sign`: OLS â=0.5943653964479788 b̂=-0.1023983939489106 λ=0.8697153620769711 share=1.208140776573942 · GMM â=0.33751479478174595 b̂=0.6860238782009921 (gmm_overid_price_mid) · restr â_raw=0.16111634022277313 â=0.16111634022277313 bind=False · split_ok=False
- `volume_bucket_signed_volume`: OLS â=0.000879011614135401 b̂=1.0010549481081656 λ=0.021258670537647975 share=0.0008773149224116831 · GMM â=-0.05798063894681316 b̂=0.2751782884609474 (gmm_overid_price_mid) · restr â_raw=0.0072445679316210185 â=0.0072445679316210185 bind=False · split_ok=True

## Decisions
- `disc.gh_z0`: **Promote**
- `disc.mrr_theta`: **Promote**
- `disc.mrr_rho_q`: **Hold**
- `disc.hs_pi`: **Promote**
- `disc.hs_as_inv_split`: **Hold**

## Falsifiers
- `disc.hs_as_inv_split`: Unconstrained â(AS)<0 (or as_share∉[0,1]) on trade/quote clocks; volume-bucket OLS b̂ often ≤0 / GMM–OLS disagree; restricted a∈[0,λ] binds when â_raw<0 — projection ≠ economic ID; dealer inventory only via cum-flow proxy. Clocks tried: quote_clock, trade_time_sign, trade_time_signed_volume, volume_bucket_sign, volume_bucket_signed_volume.
- `disc.mrr_rho_q`: ρ(q)≈0.5971130387501131 full / train=0.5506172554795513 / test=0.6835854261317946 — always high & split-stable; not a tradable feature alone (herding/persistence diagnostic)

## Blockers
- HS α|β Hold: unconstrained â<0 across clocks (primary a=-0.18039671098921042, b=0.4056862999135994, method=ols_three_way+gmm_overid_price_mid); restricted binds=True; inv_proxy γ=-4.6307763897520916e-08 (signed_ok=True).
