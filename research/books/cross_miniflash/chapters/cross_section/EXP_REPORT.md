# Cross-section — EXP_REPORT

## Sample
- Same Phase 3a panel: 2026-09-04…10 · ETH+BTC · HL+Deribit+Kraken · 42 complete cells
- Events: severity-gated SSM (10bps, \(i_c\)≥5) **n=275**
- Script / out: `exp_phase3a_stats_xsec.py` · `out/phase3a_stats_xsec/`

## Pass 1
- Quintiles by log(notional): ΔP means ~0.21–0.26% (no clear decreasing pattern)
- NW-OLS ΔP: R²=0.020; all |t|<1.6 without VPIN
- Size proxy = daily notional (OI unavailable)

## Pass 2
- VPIN×size interaction: logN t=−3.1, logN×VPIN t=2.9 (event-level)
- Ex-ante lag-1: n=20; Amihud t≈−2.46; VPIN interact R²=0.33 (fragile n)
- Time-split: early/late β(logN) **sign flip** (sign_stable=False)
- Multi-coin: ETH≈BTC median severity
- By venue gated: HL 228 · DB 21 · KR 26

## Identification
- HAC lags Andrews-ish \(L=\lfloor 4(n/100)^{2/9}\rfloor\)
- Features contemporaneous day-level for event OLS; lag-1 day for ex-ante
- Residualize via multivariate NW-OLS (not univariate quintile alone)

## Decisions
See CANDIDATES. Figures: `fig_quintile_size_dp.png`, `fig_nw_ols_dp.png`, `fig_multi_coin.png`.

## Blockers
- Wire true OI / 24h notional from marks if available
- Widen calendar + SOL for ex-ante power
- frag_xvenue owns venue concentration (sibling)
