# dcm_proxies — NOTES

**Book:** Huang–Ranaldo–Schrimpf–Somogyi (Nov 2021)  
**PDF:** §3.1 dealer constraint measure (PDF pp. 14–16) · **Status:** `pass1`  
**Lib:** [`../../../lib/cdme.py`](../../../lib/cdme.py) · Runner: [`../../scripts/exp_dcm_elasticity.py`](../../scripts/exp_dcm_elasticity.py)

---

## 1. Paper DCM (PDF pp. 14–15)

Paper builds DCM in **two steps**:

1. **Four bank factors** (cross-sectional averages of top-10 FX dealers, Euromoney surveys) plus FX stress:
   - Trading-book **VaR** (quarterly)
   - He et al. (2017) **leverage ratio** (quarterly)
   - **CDS** premia (daily)
   - Debt **funding costs** (daily)
   - + JP Morgan Global **FX Volatility** index (daily)
2. Extract the **first principal component** — paper reports PC1 explains ~**72%** of total variance (PDF p. 15). That PC1 is the composite **dealer constraint measure (DCM)**.

Motivation: high leverage / CDS / funding stress → dealers curtail intermediation; FX dealers operate globally so constraints spill across pairs (PDF p. 14–15 citing Kyle–Xiong, Cespa–Foucault).

**Desk Kill:** bank VaR / CDS single-name analogues without a public crypto mapping — vanity (`risk.bank_cds_var`).

---

## 2. Public DCM̂ (locked crypto map)

No bank VaR/CDS on the warehouse path. Pass-1 DCM̂ = PC1 of **public** proxies:

| Proxy | Construction | Notes |
|-------|--------------|-------|
| \|funding\| | Rolling \|Δlog mid\| mean (`funding_proxy`) when exchange funding table absent | Labeled proxy — **not** HL/DB funding rate |
| \|basis\| | \|log(far_mid / home_mid)\| asof-aligned (Deribit or Kraken vs home marks) | Home prefers HL marks; falls back to Deribit |
| RV | Rolling std of Δlog mid | `realized_vol` window≈30 bars |
| \|imbalance\| | \|signed trade imbalance\| from home tape buckets | Inventory proxy |

Lib: `dcm_proxies` → `dcm_pc1` (z-scored SVD; orient so abs_funding loading ≥ 0). Also `logistic_G(DCM; γ, c)` for smooth regime weight (PDF p. 18 sets γ=1 as simple logistic).

---

## 3. Paper predictions tying DCM → PIM / VLM (PDF pp. 15–16)

- corr(PIM, VLM) ≈ **67%** on smoothed series (Figure 4 note / text).
- Correlation **weakens** when DCM spikes (grey stress bands).
- Table 2 (PDF p. 17): conditional corr(PIM, VLM) falls from ~0.31 (least constrained) toward ~0.17 (most constrained top decile); mean PIM rises across DCM quantiles.

Desk object: `regime_split_corr(notional, PIM, DCM̂)` at DCM 25/75 quantiles — see `elasticity_regimes`.

---

## 4. Units / clocks / honesty

- Marks: 1m bars via `load_cross_venue_marks`.
- PC1 scores: dimensionless z-units; report explained_var + loadings + n_valid.
- Prefer true funding rate series when warehouse table exists — until then label `funding_proxy`.
- Incomplete mark/imbalance overlap → n_valid=0 days are **data gaps**, not code success.

---

## 5. Pass checklist

### Pass 1
- [x] Extract paper DCM construction + PC1 claim (pp. 14–15)
- [x] Implement public proxy PC1 on ETH
- [x] Kill vanity CDS/VaR; Hold `risk.dcm_pc1`

### Pass 2
- [ ] PC stability across days / venues
- [ ] Real funding loader if available
- [ ] Placebo DCM (noise PC) falsifier
