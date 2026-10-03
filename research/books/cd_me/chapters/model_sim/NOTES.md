# model_sim — NOTES

**Book:** Huang–Ranaldo–Schrimpf–Somogyi (Nov 2021)  
**PDF:** §4 Constrained-dealer model **pp. 23–30** · Eqs **(8)–(20)** · Prop 1–2 · Lemma 1 · Figs 6–7 · **Status:** `park` (Pass-2 DGP)  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md) · Desk: [`../../DESK_MEMO.md`](../../DESK_MEMO.md)

Page cites = PDF viewer / file page index (cover = p.1).

---

## 1. Paper model (§4)

**Setup (pp. 23–25):** static partial equilibrium; two periods; three FX pairs; risk-averse debt-financed competitive dealer + liquidity traders with exogenous demands (Grossman–Miller; Hendershott–Menkveld; Foucault–Pagano–Roell). Fundamentals linked by \(e_x=e_y e_z\).

### Liquidity demand — Eq (8) (p. 25)

Mass \(L=\lambda\sigma(1-s)\) per pair (↑ in vol \(\sigma\), ↓ in spread \(s\)). Imbalance from private-value heterogeneity (\(\pi>1/2\)):

\[
d = \lambda\sigma(1-s)\times[2\pi-1,\,1-2\pi,\,0]^\top
\]

### Dealer utility — Eq (9) (p. 25)

Mean–variance utility with debt cost \(\delta\gamma\mathbf{1}^\top|q|\); risk aversion \(\rho\). Constraints of §3 enter via (i) mean–variance / VaR-like risk and (ii) debt funding (leverage, CDS, DFC).

### Clearing & supply — Eqs (10)–(15) (pp. 26–27)

\(d=q\). FOC supply (11)–(12) with constraint intensity \(\eta=\delta\gamma\):

\[
q_k =
\begin{cases}
(a_k-\eta-e_k)/(\rho\sigma^2) & q_k>0 \\
(b_k+\eta-e_k)/(\rho\sigma^2) & q_k<0
\end{cases}
\]

Market clearing (13)–(15) pins bid/ask per pair.

### Equilibrium objects — Eqs (16)–(19) (pp. 27–29)

\[
s = \frac{2\eta+\lambda\rho\sigma^3}{1+\lambda\rho\sigma^3}
\quad\Rightarrow\quad
s\uparrow\text{ in }\eta,\sigma;\quad \eta<1/2
\]

Midquotes (17): \(m_x,m_y\) deviate from fundamentals with imbalance; \(m_z=e_z\) in baseline.

**PIM in model — Eq (18) (p. 28):**

\[
\mathrm{PIM}=\mathrm{VLOOP}+|\mathrm{TCOST}|
=\log\!\left(\frac{m_x}{m_y m_z}\right)
+\log\!\left(\frac{(1-s/(2m_x))}{(1+s/(2m_y))(1+s/(2m_z))}\right)
\]

**Volume — Eq (19) (p. 29):**

\[
\mathrm{VLM}=3\lambda\sigma\,\frac{1-2\eta}{1+\lambda\rho\sigma^3}
\]

\(\partial\mathrm{VLM}/\partial\sigma\) (20): for \(\rho<1/(2\lambda\sigma^3)\), volume ↑ in vol; slower when \(\eta\) high (**Lemma 1** p. 29).

### Propositions (pp. 28–30)

- **Prop 1:** PIM higher when (i) vol higher, (ii) dealer more levered, (iii) debt funding cost higher.  
- **Prop 2:** VLM positively correlates with PIM; that elasticity **weakens** when dealer more constrained.  
- Fig 6 (p. 29): PIM/VLOOP/TCOST vs \(\sigma\) and vs \(\eta\). Fig 7 (p. 31): (VLM, PIM) locus flatter when constrained.  
- Baseline params (Fig 6 note): \(\pi=0.7,\lambda=1,\sigma=1,\gamma=1.5,\delta=0.1,\rho=1\), \(e_x=1.32,e_y=1.1,e_z=1.2\).

---

## 2. Crypto desk mapping

| Paper | Desk |
|-------|------|
| Three FX legs + triangular PIM | Cross-venue ETH mids (HL, Deribit, Kraken) + half-spreads → desk PIM |
| \(\eta=\delta\gamma\) constraint | DCM̂ (funding/basis/RV/imbalance PC1) as proxy for \(\eta\) |
| \(\sigma\) disagreement / vol | Realised vol on home mid |
| VLM | Home notional / trade intensity |
| Qualitative predictions | Prop 1–2: PIM↑ with RV & DCM̂; corr(VLM,PIM)↓ in high-DCM̂ — testable without full DGP |

---

## 3. Park status (honest)

**Park — crypto-calibrated DGP deferred to Pass 2.**

Pass 1 delivers formula extraction + qualitative map only. Implementing a calibrated simulator (choose \(\lambda,\rho,\eta\) from crypto TOB/spreads/RV; match mean PIM and VLOOP≪TCOST) is **Pass-2** work after longer tape and stable DCM̂. Until then: no synthetic α stories; no Promote.

**Qualitative checks already on roadmap via empirics siblings** (pim / dcm / elasticity) — model package waits for DGP code + qualitative match table.

---

## 4. Pass checklist

### Pass 1
- [x] Extract §4 Eqs (8)–(20) + Prop 1–2 with page cites
- [x] Crypto map of \(\eta,\sigma,\mathrm{PIM},\mathrm{VLM}\)
- [ ] Implement crypto-calibrated DGP — **parked → Pass 2**

### Pass 2
- [ ] Calibrate to HL+Deribit ETH moments; qualitative match Prop 1–2 only
- [ ] Hold / Kill if simulated elasticity sign fails under desk-parameter ranges
