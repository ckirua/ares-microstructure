# elasticity_regimes — EXP_REPORT (certified real-quote panel)

## Sample
- Certified `panel_core_2venue` **n=9** ETH days; PIM = HL↔Deribit real quotes (+ Kraken spot_l2 on 4 days only)
- Artifacts: `out/elasticity_regimes/summary.json`
- Figs: `fig_elasticity_by_day.png`, `fig_elasticity_pooled_ci.png`
- Exploratory `min_n=5`; Promote gate remains `min_n≥15` + falsifiers (never soft-Promote)
- `trade_synth` **QUARANTINED** — not in primary join

## Pooled (certified Pass-2 result)

| Object | Value |
|--------|-------|
| n_hours_pooled | **88** across 8 days |
| corr(notional, PIM) | **−0.461** |
| 95% bootstrap CI | **[−0.570, −0.353]** (n_boot=800) |
| regime corr_low (DCM≤q25) | −0.489 (n=15), CI [−0.771, −0.108] |
| regime corr_high (DCM≥q75) | −0.596 (n=26), CI [−0.777, −0.364] |
| Δ (high−low) | **−0.106** |
| meets_promote_n_gate | true (n only — **decision_ceiling=Hold**) |

## Per-day (hourly overlap)

| Day | all corr | n | regime ok |
|-----|----------|---|-----------|
| 09-14 | −0.32 | 13 | no |
| 09-15 | — | 3 | no |
| 09-16 | −0.44 | 11 | yes Δ≈0 |
| 09-17 | −0.34 | 10 | no |
| 09-18 | −0.63 | 13 | yes Δ≈0 |
| 09-25 | −0.50 | 13 | yes Δ≈+0.25 |
| 09-26 | −0.18 | 13 | yes Δ≈0 |
| 09-27 | −0.50 | 12 | no |
| 10-01 | — | 0 | no |

## Interpretation (honest)
- Sign of pooled corr is **negative** on this crypto TOB×home-notional join — **not** a soft-Promote of the paper’s positive FX elasticity; clock/unit mismatch and sparse TOB likely.
- Regime Δ ≈ −0.11 with overlapping CIs; several per-day regimes degenerate.
- **Hold** `liq.elasticity_regime` — Pass-2 falsifiers run (chrono sign-stable; placebo PIM ok; DCM shuffle inconclusive).

## Status
- Pass 2: **done** on certified panel — pooled CI + falsifiers; decision ceiling remains **Hold**

## Pass 2 falsifiers (auto)

- **Certified panel:** n=9; spot_l2=4; trade_synth QUARANTINED.
- **Pooled elasticity:** n=88 corr=-0.461 CI[-0.570, -0.353].
- **Chrono split:** early corr=-0.314 late=-0.544 sign_stable=True.
- **Block bootstrap (by day):** corr=-0.461 CI[-0.548, -0.374].
- **Placebo PIM shuffle:** passes=True; **DCM shuffle:** inconclusive.
- **Decision:** 0 Promote; all monitors **Hold**.
