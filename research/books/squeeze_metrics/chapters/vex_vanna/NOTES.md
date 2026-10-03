# vex_vanna — NOTES

**Book:** SqueezeMetrics (`sqzme`), *The Implied Order Book* (GEX Ed., 6 July 2020)  
**PDF:** Vanna / VEX (PDF pp. 6–8; cheat sheet pp. 7–8) · **Status:** `notes`  
**Raw:** [`../../_raw/pdf_extract.txt`](../../_raw/pdf_extract.txt) · Formulas: [`../../_raw/formula_extract.md`](../../_raw/formula_extract.md)

---

## 1. Paper formulas (page cites)

### Why VEX (PDF pp. 5–6)

High IV compresses γ → GEX → 0 even when inventory nontrivial. Zero GEX alone cannot explain stress. **VEX** = dealers’ δ sensitivity to **IV** — same BS δ engine, shock $V$ instead of $S$ (PDF p. 6).

### Unit VEX examples (PDF p. 6)

Same dealer-long 2900 put from the GEX example:

| Case | S | V | δ | IV↑ 20→25% | Hedge |
|------|---|---|---|------------|-------|
| OTM | 3000 | 0.20→0.25 | 0.27→0.30 | +3δ | **Buy** ≈ $9{,}000$ SPX |
| ITM | 2800 | 0.20→0.25 | 0.72→0.67 | −5δ | **Sell** SPX |

**Moneyness matters for VEX** (unlike the simple sold-option → +GEX story).

### Flow instability (PDF pp. 7–8)

- IV is itself a liquidity meter: rises when liquidity inadequate (PDF p. 7).
- Selling options: +GEX and lower IV → GEX rises further (liquidity **multiplied**).
- Buying options: −GEX tempered because higher IV shrinks |γ| — why GEX rarely < 0.
- Dominant post-2008 flows: customers **buy OTM puts** + **sell OTM calls** → both asterisked paths force **dealer selling when IV↑** (PDF p. 8) — “vanna, gamma’s evil twin.”

### Aggregate VEX (PDF p. 8)

- Unlike GEX, VEX **knows how to be negative** (late 2008 ≈ **−$400mm / pt**; again in 2020 corona crash).
- Sub-zero VEX ↔ elevated close-to-close SPX vol; can push average daily ranges toward ~6% vs GEX-tight ~0.20%.

---

## 2. Desk mapping

| Object | Paper | Desk |
|--------|-------|------|
| IV shock | VIX / SPX IV | Deribit DVOL / option IV surface |
| VEX unit | $ / pt per IV move | $ per 1-vol-pt (or 1%) IV shock — fix in EXP_REPORT |
| Cheat sheet | cust side × CP × moneyness × IV↑/↓ | Same taxonomy on Deribit OI by moneyness bucket |
| Stress read | VEX < 0 | Regime flag when VEX scarce + IV rising |

---

## 3. Pass checklist

### Pass 0
- [x] Extract VEX definition, OTM/ITM sign flip, hist extremes
- [x] Lock DVOL/IV surface mapping

### Pass 1
- [ ] VEX panel + stress overlays
- [ ] Hold until robustness falsifiers
