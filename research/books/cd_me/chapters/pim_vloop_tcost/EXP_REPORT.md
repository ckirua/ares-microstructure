# pim_vloop_tcost — EXP_REPORT (certified real-quote panel)

## Sample
- Symbol: `ETH`
- **Primary panel** `panel_core_2venue` **n=9**: `2026-09-14, 15, 16, 17, 18, 25, 26, 27, 2026-10-01`
- **Spot_l2 subpanel** `panel_3venue_spot` **n=4**: `2026-09-25, 26, 27, 2026-10-01`
- Venues: HL + Deribit real quotes; Kraken **spot_l2 only** when dense — never `trade_synth`
- Grid: `dt_s=5`, max_lag=30s; hourly buckets
- Runner: `scripts/exp_pim_panel.py --use-certified` → `out/pim_vloop_tcost/`
- Figs: `fig_pim_hourly.png`, `fig_pim_day_means.png`, `fig_vloop_tcost_corr.png`
- Completeness: `out/panel_completeness/`

## Retracted
Prior “**10/10 three-venue TOB**” mixed Kraken `trade_synth` into the triangle on 09-14…18. Synth = **PROXY / NOT TOB** — **quarantined**. Certified PIM outs have `has_synth=false`.

## Per-day summary (certified)

| Day | Panel | Kraken | n_finite_pim | pim_mean | vloop_mean | tcost_mean | corr(VLOOP,TCOST) | HL cov | DB cov | KR cov |
|-----|-------|--------|--------------|----------|------------|------------|-------------------|--------|--------|--------|
| 2026-09-14 | core_2venue | absent_2venue | 668 | 0.0156 | 0.0070 | 0.0044 | 0.831 | 0.043 | 0.493 | — |
| 2026-09-15 | core_2venue | absent_2venue | 165 | 0.0210 | 0.0109 | 0.0030 | 1.000 | 0.044 | 0.490 | — |
| 2026-09-16 | core_2venue | absent_2venue | 621 | 0.0118 | 0.0061 | 0.0039 | 0.994 | 0.043 | 0.473 | — |
| 2026-09-17 | core_2venue | absent_2venue | 582 | 0.0124 | 0.0061 | 0.0033 | 0.943 | 0.043 | 0.496 | — |
| 2026-09-18 | core_2venue | absent_2venue | 717 | 0.0133 | 0.0070 | 0.0045 | 0.995 | 0.044 | 0.485 | — |
| 2026-09-25 | 3venue_spot | spot_l2 | 1876 | 0.0282 | 0.0139 | 0.0052 | 0.909 | 0.043 | 0.485 | 0.098 |
| 2026-09-26 | 3venue_spot | spot_l2 | 1863 | 0.0357 | 0.0179 | 0.0090 | 0.902 | 0.043 | 0.500 | 0.125 |
| 2026-09-27 | 3venue_spot | spot_l2 | 914 | 0.0321 | 0.0153 | 0.0084 | 0.845 | 0.043 | 0.500 | 0.011 |
| 2026-10-01 | 3venue_spot | spot_l2 | 1502 | 0.0469 | 0.0232 | 0.0071 | 0.910 | 0.044 | 0.402 | 0.057 |

(Full coverage + means in `out/pim_vloop_tcost/summary.json`.)

## Aggregate
- **n_ok = 9 / 9** certified primary (`panel_core_2venue`)
- Kraken modes: **absent_2venue=5**, **spot_l2=4**, **trade_synth=0**
- corr(VLOOP,TCOST) strong on most days (median ≈0.94)
- Day means of PIM vary ~0.012 … 0.047
- TOB coverage often sparse on HL (~4–12% of 5s grid) — research-grade, not HFT

## Blockers / honesty
- Primary is **2-venue HL↔Deribit**; Kraken joins only as dense `spot_l2`
- `trade_synth` quarantined — never soft-Promote as quoted α
- Detection ≠ executable arb after fees/latency/inventory → **Kill** `alpha.tob_cross_arb`
- Status: Pass 2 **done** on certified panel → Hold board; venue-drop / BTC widen deferred

## Pass 2 falsifiers (auto)

- **Kraken spot_l2:** **4** / 9 primary days; **0** synth in primary.
- **Pooled elasticity:** n=88 corr=-0.461 CI[-0.570, -0.353].
- **Chrono split:** early corr=-0.314 late=-0.544 sign_stable=True.
- **Block bootstrap (by day):** corr=-0.461 CI[-0.548, -0.374].
- **Placebo PIM shuffle:** passes=True; **DCM shuffle:** inconclusive.
- **Decision:** 0 Promote; all monitors **Hold**.
