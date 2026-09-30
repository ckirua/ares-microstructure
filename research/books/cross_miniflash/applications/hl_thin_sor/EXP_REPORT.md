# hl_thin_sor — EXP_REPORT

Generated: 2026-09-30T19:21:52.768826+00:00
Script: `applications/scripts/exp_hl_thin_sor.py` · Out: `applications/out/hl_thin_sor/`

## Setup

- Co-fire: HL gated event with intensity≥2 or day thin_excess>0.5.
- Counterfactual: Deribit+Kraken gated outcomes on same slice (venue-local; not matched fills).
- Concordance Hold → do not assume simultaneous crash.

## Headline

- Crash share: `{'hyperliquid': 0.8290909090909091, 'deribit': 0.07636363636363637, 'kraken': 0.09454545454545454}`
- Thin excess mean: `{'n': 14, 'point': 0.6236271513046804, 'lo': 0.4449085382024075, 'hi': 0.7733116979147902, 'alpha': 0.05, 'n_boot': 800}`
- n HL fire / quiet / thick = 219 / 9 / 47
- HL fire − thick Δ|mo| = `{'n_treat': 215, 'n_control': 46, 'delta': 1.196202843307045, 'lo': -3.5078713691038157, 'hi': 5.842117241118655, 'treat_mean': 18.271087237249905, 'control_mean': 17.07488439394286}`
- Time-split stable: **False**
- SOR size mult sketch: `{'hl_fire_size_mult': 0.25, 'hl_quiet_size_mult': 0.75, 'thick_size_mult': 1.0, 'note': 'Multipliers are policy sketches keyed to observed severity differential — not calibrated POV fills.'}`
- Readiness: **monitor_only** (monitor=promote_monitor; promote_policy=False)

## Figures

- `figs/fig_venue_severity.png`
- `figs/fig_crash_share.png`
- `figs/fig_hl_fire_vs_thick.png`

