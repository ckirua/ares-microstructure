# EXP_REPORT — feature stats + Bayesian layer

**Package:** `filmonov` · **Runners:** `scripts/exp_feature_stats.py`, `scripts/exp_bayes_layer.py`, helpers `scripts/_stats_bayes.py`  
**Panel:** ETH+BTC · HL+Deribit+Kraken · days `2026-09-25/26/27/30` · **n_native_complete=16**  
**Kraken `trade_synth`:** excluded from native TOB storm/fade tests.  
**Board honesty:** **0 Promote** — objects remain monitor / exec throttle / research.

## Artifacts

| Path | Contents |
|------|----------|
| `out/feature_stats/feature_stats.json` | Univariate, dependence, lead-lag, predictive endpoints + BH |
| `out/feature_stats/figs/` | 8 figs (moments, ToD, corr, xcorr, forest, horizons, completeness) |
| `out/bayes/bayes_layer.json` | Conjugate posteriors, hierarchical EB, PPC, prior sensitivity, logistic |
| `out/bayes/figs/` | 7 figs (posterior densities, forests, prior sens, PPC, logit) |
| `notebooks/info_bayes_board.ipynb` | Desk-facing info + Bayes board |

## Primary frequentist endpoints (day-block bootstrap 95% CI)

| Endpoint | Point | CI95 | BH reject | Sign-stable early/late | Decision |
|----------|-------|------|-----------|------------------------|----------|
| `info.storm_adverse_selection` | +0.52 bps | [0.48, 0.57] | yes | **no** (n=2 storm-days) | **Hold** |
| `info.fade_spread_widen_irf` | −0.11 bps | [−0.19, −0.03] | no | no | **Hold** |
| `info.fade_markout_1s` | +15.5 bps | [0.21, 45.7] | no | yes | **Hold** |
| `info.storm_markout_1s` | +0.63 bps | [0.59, 0.65] | yes | no | **Hold** |
| `info.ignition_markout_1s` | +1.60 bps | [0.97, 2.14] | yes | yes | **Hold** |
| `info.fade_temp_vs_perm_impact` | perm_share unstable | wide | no | — | **Hold** |

Pre-registered family size N=6; BH α=0.05. **No Promote** (need ≥10 complete days + sign-stable + non-vacuous storm mass).

## Key Bayesian posteriors (conjugate)

| Quantity | Mean | 95% CrI | Notes |
|----------|------|---------|-------|
| θ = P(fade) @100ms | 0.0114 | [0.0108, 0.0120] | Beta-Binomial; prior-stable (Jeffreys≈same) |
| λ storms/h (HL pool) | 0.409 | [0.316, 0.514] | Poisson-Gamma |
| λ ignition / day-venue | 6.41 | [5.26, 7.67] | Poisson-Gamma |
| P(adverse \| storm) | 0.431 | [0.300, 0.568] | CrI covers 0.5 — not clear toxicity |
| P(widen \| fade) @250ms | 0.60 | [0.19, 0.93] | thin event count; wide CrI |
| P(fade)\|HL (hier) | 0.0180 | [0.0170, 0.0191] | EB venue shrink |
| P(fade)\|Deribit (hier) | 0.0020 | [0.0016, 0.0024] | much lower than HL |

**Prior sensitivity:** skeptical Beta(1,19)/(1,99) barely moves θ_fade (large n_trials).  
**PPC:** Beta predictive for fade counts — see `fig_ppc_fade.png`.  
**Logistic Laplace:** storm coeff on P(adverse) CrI covers 0 → no Promote on toxicity gate.

## Cascade / dependence (desk)

- Storm→fade @1s hit-rate ≈0.03 (n=2 storm days) — sparse.
- Spearman day-level dependence: see `fig_corr_spearman.png`.
- Lead-lag bar-count xcorr: `fig_lead_lag_xcorr.png`.

## Blockers

1. Storm mass concentrated on **2026-09-30** (HL); AS CI thin / not early-late stable.  
2. Fade IRF peak **negative** on this panel (−0.11 bps) vs prior expand (+0.28) — unstable → Hold widen policy.  
3. Kraken native L2 missing; Deribit L2 sparse.  
4. Need ≥10 UTC-complete days before Promote-as-risk-policy.  
5. Laplace widen logistic under-identified (fade-only design) — use Beta P(widen\|fade).

## Non-goals

No firm-ID attribution · no tradable α without Promote · no ClickHouse MCP.
