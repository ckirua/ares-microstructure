# VPIN construction — Pass 1

## Smoke day (HL ETH 2026-09-30)

- complete: **True** · n_trades: **160836**
- bucket_volume: **5.72** (median(qty)×50)
- mean_vpin: **0.928** · n_buckets=27382
- gate `cont.vpin_constructed`: **Promote**

Artifact: `out/vpin_day/hyperliquid_ETH_2026-09-30.json`

## Bucket calibration

Documented in `out/vpin_panel/bucket_calibration.json` — SoT **median×50**; target_buckets≈50 lowers levels (diagnostic only). See `chapters/robustness/EXP_REPORT.md`.

## Panel

n_ok=**226** exploratory (HL+DB+Kraken, `--all-days`) · n_ok=**139** HL+Deribit promote slice — `out/vpin_panel/summary.json` · `decisions_panel_promote.json`
