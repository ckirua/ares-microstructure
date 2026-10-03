# elasticity_regimes — NOTES

**Book:** Huang–Ranaldo–Schrimpf–Somogyi (Nov 2021)  
**PDF:** §3 liquidity elasticity under constraints (PDF pp. 15–19; Table 2–3) · **Status:** `pass1`  
**Lib:** [`../../../lib/cdme.py`](../../../lib/cdme.py) `elasticity_corr` / `regime_split_corr` / `logistic_G`  
**Runner:** [`../../scripts/exp_dcm_elasticity.py`](../../scripts/exp_dcm_elasticity.py) → `out/elasticity_regimes/`

---

## 1. Object (paper)

**Claim:** dealers’ liquidity provision is elastic in normal times (positive corr / slope between volume and PIM) and becomes **less elastic** when constrained (PDF pp. 5–6, 15–19).

Motivational evidence (PDF pp. 15–17):
- Unconditional corr(PIM, VLM) positive (~0.31 on Δlog panel; ~0.67 on smoothed levels in Figure 4 narrative).
- Conditional corr **falls** in high-DCM quantiles (Table 2: ~0.31 → ~0.17 in most-constrained decile).
- Mean PIM rises across DCM quantiles.

Econometric spine (PDF pp. 17–19):
- Preferred: **LSTAR** Eq. (5) with logistic $G(z_{t-1})$ on lagged DCM (see `lstar_panel`).
- Simple approximations (Eq. 6 / Table 3): DCM interaction, DCM>75% dummy, logistic $1/[1+\exp(-\gamma\,\mathrm{DCM})]$ with γ=1.
- Result: constrained−unconstrained volume slope **negative** and significant (Table 3: Δ ≈ −0.09 in LSTAR column).

---

## 2. Desk object (Pass 1)

On UTC hourly buckets:

$$\widehat{\rho} = \mathrm{corr}(\mathrm{notional},\mathrm{PIM})$$

split by DCM̂ quantiles:

| Regime | Rule | Expectation |
|--------|------|-------------|
| Unconstrained | DCM̂ ≤ q25 | corr more positive / stronger |
| Constrained | DCM̂ ≥ q75 | corr closer to 0 / weaker |
| Δ | corr_high − corr_low | paper: negative |

Continuous weight: `G = logistic_G(DCM̂; γ=1, c=median)` (PDF p. 18).

Controls for Pass 2: RV on home mid (paper controls RV in non-dollar pair).

---

## 3. Statistical hygiene + Pass-2 pooled outcome

- Exploratory `min_n=5`; Promote gate remains `min_n≥15` + falsifiers (Pass-2 run; still Hold).
- Certified `panel_core_2venue` **n=9** → **pooled n=88** hours: corr(VLM,PIM)=**−0.461**, 95% CI **[−0.570, −0.353]** (see `EXP_REPORT.md`). Sign ≠ paper FX positive elasticity → **Hold**, never soft-Promote.
- Regime Δ ≈ −0.11 with overlapping CIs; several per-day regimes still degenerate/thin.
- Pass-2 falsifiers: chrono sign-stable; placebo PIM ok; DCM shuffle inconclusive; venue-drop deferred (`trade_synth` quarantined).
- Never Promote on a single thin day.

---

## 4. Pass checklist

### Pass 1
- [x] Extract elasticity claim + Table 2/3 cites
- [x] Implement regime-split corr on ETH panel
- [x] Pooled bootstrap CI + Hold ceiling in CANDIDATES / EXP_REPORT

### Pass 2
- [ ] Placebo regimes; RV controls; chronological split
- [ ] Align closer to LSTAR once day count supports γ,c ID
