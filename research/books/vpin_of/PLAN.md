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
- [x] Markout TOB join (`out/pass2/markout.json`, 36/48 ok days) — **Promote** (early∧late IC>0)
- [x] Merge `out/pass2/decisions_pass2.json` + `pass2_summary.json`
- [x] Desk memo, chapter EXP_REPORTs, notebooks § Pass 2

## Follow-ups (not blocking Pass 2 close)

- [ ] HL SOL instrument / flat-id mapping
- [ ] Kraken strict UTC completeness before cross-venue Promote
- [ ] HL↔DB level harmonization for concordance gate
- [ ] Full-history markout (default run used last 12 days per cell for runtime)
