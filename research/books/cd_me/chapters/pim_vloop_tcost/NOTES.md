# pim_vloop_tcost — NOTES

**Book:** Huang–Ranaldo–Schrimpf–Somogyi (Nov 2021)  
**PDF:** §2 Eqs 1–3 (PDF pp. 8–12) · **Status:** `pass1`  
**Raw:** [`../../_raw/paper.txt`](../../_raw/paper.txt) · SoT: [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md)  
**Lib:** [`../../../lib/cdme.py`](../../../lib/cdme.py) · Runner: [`../../scripts/exp_pim_panel.py`](../../scripts/exp_pim_panel.py)

---

## 1. Paper formulas (page cites)

### Eq. (1) — triangular round-trip (PDF p. 9)

Trader exchanges through three midquotes; final amount in starting currency:

$$\Delta_t \equiv \prod_{i=1}^{3} P_{i,t}$$

with $P_{i,t}$ midquote rates for the direct/indirect legs (example EUR→USD→CAD→EUR). Seemingly profitable LOP violation when $\Delta_t > 1$ (or reverse direction if $\Delta_t < 1$).

### Eq. (2) — VLOOP + TCOST decomposition (PDF p. 10)

Taking logs and replacing mids with bid/ask = mid ± half-spread:

$$\log(\Delta_t) \equiv \underbrace{\log\left(\frac{\mathrm{USDCAD}^{mid}_t}{\mathrm{USDEUR}^{mid}_t \cdot \mathrm{EURCAD}^{mid}_t}\right)}_{\mathrm{VLOOP}_t} + \underbrace{\log\left(\frac{1 - \mathrm{USDCAD}^{bas}_t/2}{(1+\mathrm{USDEUR}^{bas}_t/2)\,(1+\mathrm{EURCAD}^{bas}_t/2)}\right)}_{\mathrm{TCOST}_t}$$

- **VLOOP:** midquote LOP gap (can be ± by trade direction; abs for interpretation, PDF p. 11–12).
- **TCOST:** cumulative relative spread costs; paper notes TCOST is **always negative** as the min return needed to break even (limits-to-arbitrage, PDF p. 11). Superscript `bas` = relative bid–ask (ask−bid)/mid.

### Eq. (3) — PIM (PDF p. 11)

$$\mathrm{PIM}_t = \mathbb{E}_t\!\left[\mathrm{VLOOP}_t + \mathrm{abs}(\mathrm{TCOST}_t) \mid \mathrm{VLOOP}_t > 0\right]$$

PIM is positive by construction; higher = more inefficiency. Computed on 15 FX triplets in the paper; hourly series pruned at top/bottom 1.5% outliers; daily = sum of hourly (PDF p. 12).

### Stylized facts (PDF pp. 12, 14)

- corr(VLOOP, TCOST) positive across triplets (~12–39% in paper sample).
- Mean hourly VLOOP ≪ mean |TCOST| (order of magnitude; Table 1).
- Both surge in stress (e.g. COVID spike, PDF p. 12).

---

## 2. Desk mapping (locked crypto adaptation)

| Object | Paper | Desk |
|--------|-------|------|
| Triplet LOP | CLS FX three-pair product | Cross-venue LOP on **same underlying** (ETH) across HL + Deribit + Kraken |
| VLOOP | log mid ratio (Eq. 2) | `vloop_pair` = \|log(mid_i/mid_j)\|; panel uses **max** pairwise gap |
| TCOST | log of relative half-spread product | Sum of relative half-spreads `(ask−bid)/(2·mid)` on venues in panel (`tcost_from_spreads`) |
| PIM | Eq. 3 | `pim_from_components(vloop, tcost)` with VLOOP>0 |
| Clock | Hourly → daily sum | UTC-day grid `dt_s=5`, max_lag=30s; hourly mean buckets |
| Volume | Direct / synthetic FX volume | Home-venue trade notional (HL preferred) |

Native ETH–BTC–USD triangles **parked** until multi-pair TOB coverage is confirmed.

---

## 3. Units / latency / completeness

- **Units:** log relative (dimensionless); report means in absolute log gap (≈ bps × 1e4 for small x).
- **Alignment:** backward asof join onto common UTC grid; quotes older than `max_lag_s` → nan.
- **Coverage:** fraction of grid with finite mid per venue — flag in EXP_REPORT; do not Promote on thin coverage alone.
- **Kraken:** warehouse L2 often empty — document gaps; do not invent TOB.
- **Honesty:** warehouse/collector TOB ≠ executable; **Kill** `alpha.tob_cross_arb`.

---

## 4. Implementation pointers

- Lib: `align_tob_panel`, `vloop_cross_venue`, `tcost_from_spreads`, `pim_from_components`, `bucket_panel`
- Loaders: `scripts/_data.py` → `load_cross_venue_tob`, `load_core_venues_day`
- Artifacts: `out/pim_vloop_tcost/{summary,panel_rows,day_*.json,figs/}`

---

## 5. Pass checklist

### Pass 1
- [x] Extract Eqs 1–3 with page cites
- [x] Implement on HL + Deribit (+ Kraken when present) ETH
- [x] Baseline EXP_REPORT + CANDIDATES (Hold / Kill arb α)

### Pass 2
- [ ] Stress vs calm time-split; block bootstrap CIs
- [ ] Venue-drop falsifier; BTC widen
- [ ] Promote only after falsifiers — never soft-Promote
