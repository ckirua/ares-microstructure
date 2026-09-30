# Bootstrap / simulations — EGARCH bands & Models 0–3

**Book:** Flora & Renò (2020-09-17)  
**PDF:** §3.1 pp. 11–12 · §4 Simulations pp. 12–15 · Table 1 · **Status:** `exp_run`  
**Lib:** [`../../../lib/vstat.py`](../../../lib/vstat.py) (`fit_egarch11`, `bootstrap_minv_ci`, `simulate_model_*`)

---

## Pass 1 — paper object

- [ ] EGARCH(1,1) zero-drift simulated bootstrap for MinV CIs
- [ ] Kill asymptotic 2.18 / 3.60 as desk defaults (paper: too small + multiple testing)
- [ ] Models 0–3 size/power table (desk-scale MC OK; note vs paper N=1000)
- [ ] EXP_REPORT with rejection rates under null (0,1,2) vs alt (3)

## Pass 2 — deep dig

- [ ] Crypto-calibrated DGP (HL-like jump+burst path)
- [ ] \(h_n\) power curve; leverage EGARCH stress
- [ ] CANDIDATES: Promote bootstrap bands as *monitor* CI source; Kill asymptotic bands

## Empirics status
Pass 1+2 executed via `scripts/exp_core_vstat.py` — see EXP_REPORT.md / CANDIDATES.md / out/.
