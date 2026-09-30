# kill_ladder — EXP_REPORT

Generated: 2026-09-30T19:21:51.951622+00:00
Script: `applications/scripts/exp_kill_ladder.py` · Out: `applications/out/kill_ladder/`

## Setup

- Gate: 10bps / i_c≥5; σ_m floor on; z*=6 base detection.
- Ladder: within-gated z percentiles (p25/p50/p75) + intensity + Nanex nest.
- Breaks: `{'p25': 12.542394804373876, 'p50': 15.865926627251527, 'p75': 20.381035970651197, 'dp_p90': 0.4505073913401462}`
- Outcomes: event |ΔP|, tape mo@5s, sub |ΔP|@30s, recovery class.
- Control: observe-tier isolated (intensity≤1); placebo = random tape windows.
- Friction haircut: 2.0 bps one-way (no fantasy fills).

## Counts

- n_gated = **275**; tiers = `{'widen': 105, 'size_cap': 37, 'observe': 45, 'halt': 88}`
- fire (widen+) n = **230**; controls = 45

## Effects (fire vs control)

- |mo|@5s Δ = **6.537298390097813** CI95 [1.7633914541712985, 10.396745276744905]
- Intensity≥3 vs ≤1 sub|ΔP| Δ = `{'n_treat': 69, 'n_control': 162, 'delta': 0.2518564598535031, 'lo': 0.1721554451745607, 'hi': 0.33945378362693407, 'treat_mean': 0.5707032889326954, 'control_mean': 0.3188468290791923}`
- Time-split |mo| Δ early/late sign stable: **True**
- Friction cleared (Δ|mo| > 2.0 & CI>0): **True**
- V-share among fire (FP cost of halt): **0.783**

## Readiness

**promote_as_risk_policy** — promote_as_risk_policy=True

Monitor: **yes** (gated intensity + z* ladder). Executable aggressive-halt: **candidate** if friction+CI clear

## Figures

- `figs/fig_ladder_tiers.png`
- `figs/fig_intensity_vs_subdp.png`
- `figs/fig_fire_vs_control_mo.png`

