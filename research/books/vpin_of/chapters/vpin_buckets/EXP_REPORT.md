# VPIN buckets — panel Pass 1

- n_rows=315 n_ok=226 (HL+DB ok=139)
- bucket SoT: median(qty)×50.0 — see `out/vpin_panel/bucket_calibration.json`

| id | decision | evidence |
|----|----------|----------|
| `cont.vpin_constructed` | **Promote** | n_ok=226 HL+DB=139; med mean_vpin bootstrap={'n': 226, 'point': 0.8617372988179428, 'lo': 0.8450918426114366, 'hi': 0.87 |
| `cont.vpin_bucket_mean` | **Promote** | median×50 SoT; n_ok=226 |
| `info.vpin_side_shuffle` | **Promote** | pass_rate=0.98 (p_exceed≤0.05); n_ok=226 |
| `info.vpin_time_split_stable` | **Promote** | stable_rate=0.97 |Δearly-late|<0.12; n_ok=226 |
| `frag.xvenue_vpin_concord` | **Hold** | HL↔DB ρ=-0.3243831640058055 CI=[-0.5657998709885502,-0.04216053862280308] n=53.0 |
| `disc.pin_proxy_vs_vpin` | **Promote** | day-level proxy vs mean_vpin Spearman (not EHO level match) |
| `frag.kraken_vpin` | **Hold** | Kraken n_ok=87 — partial futures tape; label only |
| `frag.hl_sol_empty` | **Hold** | HL SOL empty on probe — no Promote until instrument fix |
