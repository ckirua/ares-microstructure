# Crash statistics — EXP_REPORT

## Sample
- Days: 2026-09-04…10 · ETH+BTC · HL+Deribit+Kraken · **42/42 complete**
- Script: `scripts/exp_phase3a_stats_xsec.py`
- Out: `out/phase3a_stats_xsec/`
- Completeness: UTC clip + n≥500 + span≥6h + coverage≥0.25 (same as Phase 2)

## Pass 1 — severity + paper stats

| Source | n | median ΔP (%) | median \(i_c\) | median Δt (s) | median recov@5s |
|--------|--:|-------------:|-------------:|-------------:|----------------:|
| SSM raw z*=6 | 3668 | (~0 micro) | — | — | — |
| SSM gated 10bps/\(i_c\)≥5 | **275** | **0.177** | **17** | **0.0** | **1.15** |
| Nanex 30bps | 105 | 0.396 | (trade-count) | — | — |

Gate ablation kept: 5bps/ic3=**589** · 10bps/ic5=**275** · 30bps/ic10=**56**.

By venue (gated): HL **228** · Deribit **21** · Kraken **26**.

## Pass 2 — recovery / markout / duration

- Class shares (gated): V **77%** · partial 9% · continuation **14%**
- Tape markout mean bps: 0.5s **−4.9** · 1s **−7.6** · 5s **−7.1** (25 cells)
- Spearman(Δt, |mo@5s|) cell-weighted ≈ **−0.28**
- Placebo random ends: recovery median ≈0–0.2 ≪ obs 1.15
- TOB: HL+Deribit warehouse quotes present; **Kraken tob_cells=0** — resilience / mid-markout ceiling

## Identification assumptions
- Severity gate stated; Nanex θ=30bps Hold from Phase 2.  
- \(i_c\) = trade count (not exchange tick).  
- Recovery horizon 5s calendar.  
- Markout = tape price when mid sparse (signed with crash direction).

## Decisions
See CANDIDATES. Figures: `figs/fig_severity_gate.png`, `fig_dp_hist.png`, `fig_recovery_class.png`.

## Blockers
- True OI for xsec size (using daily notional proxy) — owned by `cross_section`
- Dense Kraken TOB for mid-markout / resilience
- Volume-clock duration (calendar Δt median 0)
