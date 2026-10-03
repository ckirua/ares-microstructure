# squeeze_regimes — NOTES

**Book:** SqueezeMetrics (`sqzme`), *The Implied Order Book* (GEX Ed., 6 July 2020)  
**PDF:** GEX+ · conditional maps · crash / squeeze loop (PDF pp. 9–12) · **Status:** `notes`  
**Raw:** [`../../_raw/pdf_extract.txt`](../../_raw/pdf_extract.txt) · Draft: [`../../_raw/BOOK_DRAFT.md`](../../_raw/BOOK_DRAFT.md)

---

## 1. Paper objects (page cites)

### GEX+ (PDF p. 9)

$$
\mathrm{GEX}^{+} = \mathrm{GEX} + \mathrm{VEX}
$$

Additive implied top-of-book liquidity. Hist range cited ≈ **+$2bn** provided → **−$500mm** taking. Index moves track available option-originated liquidity; VIX is a coarse proxy but not the full book.

### Crash / squeeze loop (PDF pp. 9–10)

Sold puts look great near spot:
1. +GEX → better TOB liquidity, dips bought.
2. Sold **OTM** puts also raise VEX → IV↑ can force dealer **buying**.

Catch: once those puts go **ITM**, vanna flips — IV↑ forces dealer **selling**. Feedback: liquidity deteriorates → IV↑ → more selling → ends only when IV cannot rise further; IV↓ then forces violent buybacks (bear rallies).

Paper: crash risk is “how many investors have sold puts, plain and simple” (PDF p. 9).

### Conditional liquidity maps (PDF pp. 10–11)

Map GEX+ (and **GIV** = gamma-implied vol) over (SPX level, VIX). Example 5 Mar 2020:
- **Red:** GEX+ < 0 — stop-like illiquidity zone (break below ~3000).
- **Map ends** (e.g. SPX < 2800, VIX > 60): demand so large (GEX+ < −$500mm) that no historical analog exists.
- GIV yellow/offsides: e.g. SPX→2800 even with VIX flat → ~80 vol; with VIX→64 → ~120 vol — VIX underprices because rising VIX itself destroys liquidity via vanna.

### Long vs short puts (PDF pp. 11–12)

- Customer **long** puts: short dealer γ (worse TOB) but ITM + IV↑ → dealer **buys** — short sharp corrections, not crashes.
- **Short**-put dominance in buy/sell ratio ↔ crash episodes.
- Irony: bought puts reduce TOB liquidity but add depth when things fall apart; sold-put “liquidity supply” withdraws exactly when needed (PDF p. 12).

Closing: “options *are* the order book” (PDF p. 12).

---

## 2. Desk regimes (Pass 0 lock)

| Regime | Rule (desk) | Paper analogue |
|--------|-------------|----------------|
| Abundance | GEX+ high / positive | +GEX / +GEX+ (pp. 5, 9) |
| Scarce / red | GEX+ ≤ 0 or bottom quantile | Red zone map (pp. 10–11) |
| Squeeze / stress | Scarce + IV rising + VEX ≤ 0 | Vanna feedback (pp. 8–10) |
| Offsides IV | Realized/GIV ≫ quoted IV | GIV map (p. 11) |
| Put-skew flow | Deribit put sell vs buy imbalance | Put buy/sell ratio (pp. 11–12) |

Surface axes: (ETH mark, DVOL/IV). Underlying TOB only for co-movement diagnostics.

---

## 3. Pass checklist

### Pass 0
- [x] Extract GEX+, crash loop, map/GIV cites
- [x] Lock abundance / scarce / squeeze labels

### Pass 1
- [ ] Build (S, IV) heatmaps on Deribit inventory
- [ ] Hold monitors; never Promote TOB-cross α
