# dcm_proxies — EXP_REPORT (certified real-quote panel)

## Sample
- Symbol: `ETH`
- Days: certified `panel_core_2venue` **n=9** (same as PIM; real quotes only — no trade_synth)
- Runner: `scripts/exp_dcm_elasticity.py` → `out/dcm_proxies/`
- Joins PIM hourly from `out/pim_vloop_tcost/` when present
- Fig: `fig_dcm_coverage.png`

## Per-day DCM̂

| Day | ok | n_valid | explained_var | loadings (abs_fund / rv / imb) | notes |
|-----|----|---------|---------------|--------------------------------|-------|
| 2026-09-14 | yes | 331 | 0.66 | 0.70 / 0.64 / 0.33 | basis≈0 |
| 2026-09-15 | yes | 332 | 0.79 | 0.62 / 0.62 / 0.47 | |
| 2026-09-16 | yes | 330 | 0.64 | 0.71 / 0.71 / ~0 | |
| 2026-09-17 | yes | 333 | 0.99 | 0.71 / 0.71 / 0 | funding+RV dominate |
| 2026-09-18 | yes | 319 | 0.66 | 0.71 / 0.71 / −0.05 | |
| 2026-09-25 | yes | 332 | 0.66 | 0.70 / 0.70 / −0.13 | |
| 2026-09-26 | yes | 325 | 0.67 | 0.70 / 0.70 / 0.13 | |
| 2026-09-27 | yes | 332 | 0.99 | 0.71 / 0.71 / 0 | |
| 2026-10-01 | yes | 0 | — | — | window overlap empty |

Excluded from primary (completeness): 09-19…24, 28–30.

## Blockers / honesty
- `funding_proxy` = rolling |Δlog mid| — **not** exchange funding rate
- \|basis\| often near-zero / degenerate when home≈far marks or HL marks missing (falls back to Deribit)
- Bank VaR/CDS **Kill** (no public analogue)
- PC1 explained_var ~0.64–0.99 on usable days — unstable when only funding+RV load
- `trade_synth` not used in DCM join

## Status
- Pass 2: **done** → Hold `risk.dcm_pc1` (9/9 certified days; DCM placebo inconclusive)

## Pass 2 falsifiers (auto)

- **Certified panel:** n=9; spot_l2=4; trade_synth QUARANTINED.
- **Pooled elasticity:** n=88 corr=-0.461 CI[-0.570, -0.353].
- **Chrono split:** early corr=-0.314 late=-0.544 sign_stable=True.
- **Block bootstrap (by day):** corr=-0.461 CI[-0.548, -0.374].
- **Placebo PIM shuffle:** passes=True; **DCM shuffle:** inconclusive.
- **Decision:** 0 Promote; all monitors **Hold**.
