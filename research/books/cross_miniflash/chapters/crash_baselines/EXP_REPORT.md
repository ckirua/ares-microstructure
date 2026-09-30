# Crash baselines — EXP_REPORT

## Sample
- Days: 2026-09-04…10 · ETH+BTC · HL+Deribit+Kraken · **42/42 complete**
- Script: `exp_phase2_baselines_ssm.py` (+ `outside_tob_smoke.json`)
- Completeness: UTC clip + n≥500 + span≥6h + coverage≥0.25

## Pass 1 counts

| Venue | Nanex 30bps | Nanex 80bps | V-shape | Outside-TOB |
|-------|------------:|------------:|--------:|------------:|
| hyperliquid | 70 | (in pool) | 90 | 0 (no TOB in main run) |
| deribit | 13 | | 16 | smoke only |
| kraken | 22 | | 26 | no L2 stream |
| **TOTAL** | **105** | **8** | **132** | — |

## Pass 2
- Overlap Nanex↔SSM: n_ov=94 / 105 Nanex · Jaccard=0.026 · precision=0.895 · recall=0.026
- Tox: Nanex |imb| pre=0.565 → con=0.707; SSM pre=0.614 → con=0.643
- VPIN day mean≈0.736
- Outside-TOB Deribit 09-05/06: n_tob=6071/8424, outside_rate=0.79/0.15

## Identification assumptions
- Trade-count Nanex (not exchange tick). θ stated per row.  
- Outside-TOB requires contemporaneous TOB; warehouse L2 ≠ collector ms TOB.

## Decisions
See CANDIDATES. Figures under `out/phase2_baselines_ssm/figs/`.

## Blockers → Phase 3
- Dense TOB aligned to vertical-slice days for real outside-BBO / markout
- Severity distribution of Nanex 30bps events (\(\Delta P,i_c,\Delta t\)) in `crash_stats`
