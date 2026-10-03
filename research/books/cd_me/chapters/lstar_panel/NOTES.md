# lstar_panel — NOTES

**Book:** Huang–Ranaldo–Schrimpf–Somogyi (Nov 2021)  
**PDF:** §3.2 LSTAR / logistic smooth transition (PDF pp. 16–20; Eqs 4–7; Table 3–4) · **Status:** `park`  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md) · Lib: [`../../../lib/cdme.py`](../../../lib/cdme.py) `logistic_G`

---

## 1. Paper formulas (page cites)

### Logistic transition (PDF p. 17)

$$G(z_{t-1}) = \frac{1}{1 + \exp\!\big(-\gamma\,(z_{t-1} - c)\big)}$$

- $z_{t-1}$ = 1-day lagged DCM
- $c$ = central location; $\gamma$ = steepness
- Paper also uses simple logistic $1/[1+\exp(-\gamma\,\mathrm{DCM})]$ with $\gamma=1$ (PDF p. 18)

### LSTAR Eq. (5) (PDF p. 17)

$$y_{k,t} = \lambda_t + \alpha_k + [1-G(z_{t-1})]\beta_1' f_{k,t} + G(z_{t-1})\beta_2' f_{k,t} + \beta_3' w_{k,t} + \varepsilon_{k,t}$$

- $y$ ∈ {VLOOP, TCOST, PIM}; $f$ = state-dependent (esp. VLM); $w$ = state-independent (esp. RV)
- Triplet FE $\alpha_k$ + time FE $\lambda_t$
- Estimation: GMM; $(\gamma,c)$ by NLS on concentrated SSE (PDF p. 17)
- Boundary: $\beta_1=\beta_2$ → linear; $\gamma\to\infty$ → dummy regime

### Linear interaction approx Eq. (6) (PDF p. 18)

$$\mathrm{PIM}_{k,t} = \lambda_t + \alpha_k + \beta_1' f_{k,t} + \rho' f_{k,t}\cdot D_{t-1} + \delta' w_{k,t} + \epsilon_{k,t}$$

$D$ = DCM, DCM>q75 dummy, or logistic transform. $\rho$ ≈ $\beta_2-\beta_1$.

### Per-triplet linear Eq. (7) (PDF p. 20)

$$\mathrm{PIM}_{k,t} = \alpha_k + \beta_k\,\mathrm{VLM}_{k,t} + \delta_k\,\mathrm{RV}_{k,t} + \epsilon_{k,t}$$

(logs and first differences throughout — PDF p. 18).

Table 3 headline (PDF p. 19): unconstrained volume slope ≈ 0.11, constrained ≈ 0.02, Δ ≈ −0.09 (LSTAR).

---

## 2. Desk status — **park** (honest)

| Need | Warehouse reality |
|------|-------------------|
| Long day panel with FE | Pass-1 ETH slice is a handful of UTC days |
| Identify $(\gamma,c)$ | Short tape → unidentified / unstable |
| Triplet cross-section $k=1..15$ | We have **one** cross-venue cell (ETH), not 15 FX triplets |

Pass-1 helper only: `logistic_G(DCM̂)` inside `elasticity_regimes` / `paper_shadow`.  
**No LSTAR GMM fit attempted on this tape.** Candidate stays **Hold/park** — not Kill of the paper method.

---

## 3. Pass checklist

### Pass 1
- [x] Extract Eqs 4–7 + Table 3 cites
- [x] Honest park with ID reason
- [ ] Full panel FE — blocked by day count

### Pass 2
- [ ] Revisit when ≥20 complete multi-venue days (or synthetic panel)
- [ ] Kill if γ/c still unidentified after widen
