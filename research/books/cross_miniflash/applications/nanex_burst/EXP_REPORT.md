# nanex_burst — EXP_REPORT

Generated: 2026-09-30T19:21:52.486238+00:00
Script: `applications/scripts/exp_nanex_burst.py` · Out: `applications/out/nanex_burst/`

## Setup

- Treat = gated SSM events overlapping Nanex 30bps (nest).
- Control = gated SSM without Nanex overlap.
- Placebo tag = Nanex events failing SSM nest.

## Headline

- n_nested=**67** / n_ssm_only=**208**; Nanex precision=**0.905**
- Δ|ΔP| (nested−SSM-only) = `{'n_treat': 67, 'n_control': 208, 'delta': 0.11296647015022801, 'lo': 0.07469843271290219, 'hi': 0.15192095503603892, 'treat_mean': 0.31928089590818937, 'control_mean': 0.20631442575796136}`
- Δ|mo|@5s = `{'n_treat': 66, 'n_control': 204, 'delta': 5.112653733670719, 'lo': 0.44206253713894866, 'hi': 9.218644545730854, 'treat_mean': 21.945612937841897, 'control_mean': 16.83295920417118}`
- Time-split sign stable: **True**
- Tag readiness: **promote_as_burst_tag**
- Auto-pull readiness: **promote_as_risk_policy** (promote_as_risk_policy=True)

## Figures

- `figs/fig_nested_vs_ssm_only.png`
- `figs/fig_nested_venue_counts.png`

