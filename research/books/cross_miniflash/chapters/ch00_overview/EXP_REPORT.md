# Ch.00 overview — EXP_REPORT (Phase 2)

## Sample
- Venues: **hyperliquid, deribit, kraken** · Symbols: **ETH, BTC**
- UTC days: 2026-09-04 … 2026-09-10 (7) · **42/42** complete cells (clip + coverage gates)
- Trades pooled: HL 1.21M · Deribit 0.96M · Kraken 1.09M
- Script: `scripts/exp_phase2_baselines_ssm.py` · Out: `out/phase2_baselines_ssm/`

## Key counts (Nanex 30 bps vs SSM z*=6)

| Venue | Nanex | SSM | V-shape |
|-------|------:|----:|--------:|
| hyperliquid | 70 | 3075 | 90 |
| deribit | 13 | 349 | 16 |
| kraken | 22 | 244 | 26 |
| **TOTAL** | **105** | **3668** | **132** |

Paper Nanex 80 bps: **8** events total → **Kill**.

## Overlap / taxonomy
- Nanex↔SSM: Jaccard≈0.026 · precision(Nanex)≈0.90 · recall≈0.026
- V-shape↔SSM: Jaccard≈0.021 · precision≈0.86

## Decisions
- `info.crash_def_taxonomy`: **Promote**
- Binary detectors: **Hold/Kill** per CANDIDATES (see sibling packages)

## Figures
- `out/phase2_baselines_ssm/figs/fig_nanex_vs_ssm_venue.png`
- `out/phase2_baselines_ssm/figs/fig_overlap_jaccard.png`

## Blockers for Phase 3
- Outside-TOB needs dense TOB (collector or HL `l2_rebuild`) on the same UTC days
- SSM binary needs severity gate (\(\Delta P\), \(i_c\)) before risk Promote
