# spoof_smoke_clock — CANDIDATES (Pass 2 hardened)

**Bias:** Hold/Kill — smoke/layer Kill; clock Hold monitor; OTR policy-only

| id | type | lenses | decision | falsifier / Pass2 |
|----|------|--------|----------|-------------------|
| `spoof.smoke_proxy` | risk cartoon | risk | **Kill** | FP contam≈1.79 (placebo≥obs); unlabeled without firm IDs |
| `spoof.layer_proxy` | risk cartoon | risk | **Kill** | same FP contamination; Hold only as deck cartoon |
| `spoof.clock_cluster` | monitor | risk | **Hold** | max_z mean≈22.30706778053844; early/late max_z=25.9813825659611/20.46991038782711; shuffle placebo n_excess=0 |
| `spoof.otr_venue` | monitor | risk | **Hold** | venue cancel_proxy/trade aggregates — policy-only; Kill participant OTR |
| `spoof.tape_paint` | risk cartoon | risk | **Kill** | Nanex equity cartoon; no crypto OE cancel-after-print ID path |

**Default labels:** monitor / exec throttle / risk-policy — not tradable α. Zero Promotes unless falsifier+overlap clear.

### Pass-2 expand (info)

| id | type | lenses | decision | falsifier / expand |
|----|------|--------|----------|-------------------|
| `info.clock_vs_funding_window` | E | info,exec | **Hold** | max_z_in/out≈0.57; Kill funding-specific clock if ratio≈1 |
