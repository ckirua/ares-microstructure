# vpin_of program plan

## Pass 1 — **complete** (2026-10-03)

- [x] Data inventory + provenance (`out/data_inventory/`, `DATA_INVENTORY.md`)
- [x] Single-day smoke (`out/vpin_day/hyperliquid_ETH_2026-09-30.json`)
- [x] Panel `--all-days` ETH/BTC/SOL × HL+DB+Kraken (`out/vpin_panel/`, n_ok=226; promote slice n_ok=139)
- [x] Bucket calibration documented (`out/vpin_panel/bucket_calibration.json`)
- [x] PIN compare artifact (`out/vpin_panel/pin_compare.json`) — MLE Hold
- [x] Chapter EXP_REPORT + CANDIDATES Kill/Hold/Promote
- [x] Executed desk + chapter notebooks (`scripts/build_notebooks.py`)
- [x] TRADING_APPLICATIONS + `applications/monitors.py` aligned with decisions

## Pass 2 — **complete** (2026-10-03)

- [x] Kraken probe + strict coverage counts (`out/pass2/kraken_probe.json`) — **Hold**
- [x] HL SOL empty probe (`out/pass2/hl_sol_probe.json`) — **Hold**
- [x] HL+DB extended panel (`out/pass2/panel_hl_db_extended.json`, n=110)
- [x] Cross-venue concordance refresh (`out/pass2/xvenue_concord.json`) — **Hold**
- [x] PIN MLE diagnose (`out/pass2/pin_mle_diagnose.json`)
- [x] Bucket robustness grid (`out/pass2/bucket_robust.json`) — **Hold**
- [x] Toxicity TOB join (`out/pass2/toxicity.json`) — **Hold**
- [x] Markout TOB join (`out/pass2/markout.json`, 68/110 ok day-joins) — **Hold** (medIC≈0.007; OOS gate failed)
- [x] Merge `out/pass2/decisions_pass2.json` + `pass2_summary.json`
- [x] Desk memo, chapter EXP_REPORTs, notebooks § Pass 2

## Pass 3 — **complete** (2026-10-03)

- [x] `scripts/exp_pass3.py` → [`out/pass3/`](out/pass3/)
- [x] HL SOL catalog probe (`hl_sol_probe.json`) — FNV **621827265**; **1/37** listing days with trades (2026-08-28 only); **Hold** (warehouse shard gap, not missing flat id)
- [x] Kraken strict vs standard + tail partial doc (`kraken_probe.json`) — strict=30, std=87, tail_partial=18 — **Hold**
- [x] xvenue harmonization (`xvenue_harmonized.json`) — target50 ρ≈−0.04 CI crosses 0; rank ρ≈−0.17 — gate CI_lo≥0.15 **failed** — **Hold**
- [x] Dense L2 markout full panel (`markout.json`) — **69/110** ok joins; medIC≈0.011; rankIC≈0.011; pre-reg gate **failed** — **Hold**
- [x] Toxicity residual (`toxicity.json`) — ρ_spread≈−0.37; ρ_resid≈−0.05 (CI through 0) — **Hold**
- [x] Extended bucket grid (`bucket_robust.json`) — level spread **0.725** (>0.45 Promote threshold) — **Hold**
- [x] Merge [`out/pass3/decisions_pass3.json`](out/pass3/decisions_pass3.json) — **5 Promote / 6 Hold** (unchanged vs Pass 2)
- [x] Desk memo, EXP_REPORTs, notebooks § Pass 3, monitors

## Pass 4 — **complete (FINAL)** (2026-10-03)

- [x] HL SOL post-2026-08-28 probe + formal **SOL=Deribit+Kraken** panel arm (`sol_db_kraken_panel.json`)
- [x] Kraken futures TOB markout probe (no S3 BBO; ingest cache documented) — **Hold**
- [x] xvenue notional/target50 on ≥20 fresh paired HL↔DB days — gate **failed** — **Hold**
- [x] Markout promote-slice only; venue holdout; 60s+ horizons — pre-reg gate **failed** — **Hold**
- [x] Intraday VPIN-spike toxicity event study — **Hold**
- [x] [`out/pass4/decisions_pass4.json`](out/pass4/decisions_pass4.json) — merged final board
- [x] Desk memo § Pass 4, notebooks §8, monitors, chapter reports

**Book status: FINAL** (no Pass 5 planned).
