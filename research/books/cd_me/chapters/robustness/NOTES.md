# robustness — NOTES

**Book:** Huang–Ranaldo–Schrimpf–Somogyi (Nov 2021)  
**PDF:** §5 Additional tests and robustness **pp. 30–35** · Tables 6–9 · Fig 8 · **Status:** `Hold` (checklist ready; Pass-2 runs pending)  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md) · Desk: [`../../DESK_MEMO.md`](../../DESK_MEMO.md)

Page cites = PDF viewer / file page index (cover = p.1).

---

## 1. Paper falsifiers (§5)

Paper motivation (p. 30): PIM and VLM are **joint equilibrium** outcomes → OLS of PIM on VLM risks OVB. Three robustness blocks:

### A. Granular IV (GIV) — Eq (21) pp. 31–32

\[
\mathrm{GIV}_t = \sum_{i=1}^{15} S_{i,t-1}\,\mathrm{VLM}_{i,t} - \frac{1}{15}\sum_{i=1}^{15}\mathrm{VLM}_{i,t}
\]

with \(S_{i,t}=\mathrm{VLM}_{i,t}/\sum_j\mathrm{VLM}_{j,t}\). Daily GIV = sum of hourly. Washes common component; residual = idiosyncratic volume shock (Gabaix–Koijen 2020). First-stage F≫10 (p. 32). Table 6 (p. 33): second-stage LSTAR still shows constrained−unconstrained Δ ≈ **−0.06** for PIM (~50%+ elasticity drop). Narrative top-20 shocks: MP announcements, large asset moves, political uncertainty (Table 7 p. 34; e.g. SNB de-peg 15 Jan 2015).

### B. DCM constituents as separate regimes (pp. 32–33, Table 8 p. 36)

Replace composite DCM with lagged VaR, HKM leverage, CDS, DFC, VXY (and all five jointly). Constrained−unconstrained volume slope **negative and significant** in all six specs; magnitudes aligned with baseline DCM.

### C. Customer-bank vs inter-bank volume (pp. 34–35, Table 9 p. 37)

Split VLM into CLS customer-bank (corporates/funds/non-bank fins) vs inter-bank. Elasticity weakens under constraints in **both** segments; larger economic drop in **inter-bank** (dealers curtail bank–bank liquidity more).

**Also mentioned:** OA control for cross-currency basis as funding-liquidity control (p. 18); OA Table B.3 volume PCs as controls (p. 32).

---

## 2. Desk falsifier checklist (Pass-2)

Map paper blocks → crypto lab without bank VaR/CDS:

| # | Falsifier | Paper analogue | Desk implementation | Gate |
|---|-----------|----------------|---------------------|------|
| 1 | Time-split stress vs calm | Fig 3 / Covid spike | Split by DCM̂ quantile or RV tercile | Hold until run |
| 2 | Block bootstrap CIs | DK SEs spirit | Resample UTC days / hours for corr(VLM,PIM) Δ | Hold |
| 3 | Placebo regimes | — | Shuffle DCM̂ labels; Δ should vanish | Hold |
| 4 | Venue drop | Triplet heterogeneity | Drop Deribit or Kraken; PIM panel stable? | Hold |
| 5 | BTC widen | Cross-section of pairs | Repeat ETH recipe on BTC | Hold |
| 6 | Proxy drop / PC stability | Table 8 constituents | Leave-one-proxy-out PC1; Kill if single vanity factor | Hold |
| 7 | RV control | \(w_{k,t}=\) RV in LSTAR | Partial out RV before elasticity | Hold |
| 8 | GIV-style (optional) | Eq (21) | Needs multi-symbol/venue panel granularity — park if \(N\) tiny | Park if thin |
| 9 | **Kill TOB-cross α** | Indicative ≠ executable (p. 8) | Never soft-Promote cross-venue TOB gap as arb | **Kill** (pre-registered) |
| 10 | **Kill bank CDS/VaR** | Paper factors unavailable | No vanity crypto CDS/VaR series | **Kill** (pre-registered) |

---

## 3. Status

**Hold after Pass-2 falsifiers.** Chrono / block-boot / placebo PIM in `out/pass2/` on certified n=9; DCM shuffle inconclusive; venue-drop / BTC widen deferred (`trade_synth` quarantined). No Promote.

---

## 4. Pass checklist

### Pass 1
- [x] Extract §5 GIV / constituents / customer-split with page cites
- [x] Desk falsifier checklist mapped
- [ ] Execute falsifier scripts — **Hold → Pass 2**

### Pass 2
- [ ] Run checklist; update CANDIDATES with CIs
- [ ] Kill failures; no soft-Promote TOB-cross α
