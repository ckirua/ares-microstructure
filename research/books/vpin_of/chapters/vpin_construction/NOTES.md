# Notes — vpin_construction

Volume-clock buckets, calibration, rolling VPIN path.

## Bucket volume (Pass 1)

**SoT:** `median(qty>0) × 50` via `scripts/_data.resolve_bucket_volume` — same as
`research/lib/vpin.default_bucket_volume` and `empirical_mm` Ch.15 (`continuous.vpin_bucket`).

**Smoke concern:** HL ETH 2026-09-30 `mean_vpin≈0.93` with `bucket_volume≈5.7` is **not**
a mis-calibration bug: rolling mean over 50 micro-buckets stays high when signed flow
autocorrelates within the volume clock. Grid in `out/vpin_panel/bucket_calibration.json`
shows coarser `target_buckets≈50` pulls levels down (~0.35–0.55) but **changes the clock**
— use only for robustness, not Promote gates.

**Levels:** VPIN analogue ∈ [0,1] but **not** comparable to EHO PIN MLE levels; compare
ranks / falsifiers (side shuffle, time split), not absolute toxicity thresholds.

**Deribit qty:** contract-sized prints → larger `bucket_volume` in raw units; always
normalize cross-venue on paired-day Spearman, not level.

Agent 2: add paper pointers (local PDF only).
