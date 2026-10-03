# Ch.00 — Overview: Implied order book via dealer hedges

**Book:** SqueezeMetrics (`sqzme`), *The Implied Order Book* (GEX Ed., 6 July 2020)  
**PDF:** pp. 1–3 claim + taxonomy · **Status:** `notes`  
**Raw extract:** [`../../_raw/pdf_extract.txt`](../../_raw/pdf_extract.txt) · outline: [`../../_raw/paper.txt`](../../_raw/paper.txt)  
**Draft:** [`../../_raw/BOOK_DRAFT.md`](../../_raw/BOOK_DRAFT.md)

Page cites = PDF viewer / file page index (`===== PAGE N =====`; cover narrative = p.1).

---

## 1. Core claim (PDF pp. 1–3)

Paper: venue LOBs are fragmented and strategically noisy; the informative liquidity schedule is the one forced by **option-dealer delta hedges**. Customer option positions invert onto dealers; dealers replicate payoffs in the underlying → options act as a complex order type that either **provides** or **takes** liquidity (PDF pp. 1–2).

Three measurable steps (PDF p. 2):
1. SPX options are the largest transparent slice of the broad “order book.”
2. Transaction data → dealers’ actual option positions (**DDOI**, PDF p. 3).
3. Black–Scholes → dollar locations of required δ-hedges (**GEX**, **VEX**).

Δδ drivers (PDF p. 3): underlying price, IV, time. Charm dropped as too small → retain **GEX** (δ vs S) and **VEX** (δ vs IV).

Desk test: public crypto cannot observe SPX pit dealers. Map onto **Deribit options OI** (+ signed flow when available) hedging against **HL/Deribit ETH** underlyings; Kraken `spot_l2` when dense. Detection/monitor ≠ naked arb α.

| Object | Paper (SPX) | Crypto desk mapping |
|--------|-------------|---------------------|
| Signed inventory | DDOI from trade dir + ΔOI (p. 3) | Deribit OI Δ + aggressor when tape allows |
| GEX | Σ dealer γ in $/pt (pp. 4–5) | Σ signed OI · γ · mult · spot |
| VEX | Σ dealer ∂δ/∂σ in $ (pp. 6–8) | Same vs DVOL / IV shock |
| Implied LOB | GEX+ = GEX+VEX (p. 9) | Additive dealer-liquidity score |
| Abundance / scarce | Conditional maps (pp. 10–11) | (mark, IV) heatmaps → squeeze regimes |
| Visible TOB | “bluff” LOB (p. 1) | HL/Deribit TOB co-movement only — **Kill** TOB-cross α |

---

## 2. Taxonomy (reading order)

| § | Paper focus | Package | Pass-0 status |
|---|-------------|---------|---------------|
| Claim + δ taxonomy | pp. 1–3 | `ch00_overview` | notes |
| DDOI | p. 3 | `ddoi_positions` | notes |
| GEX → implied book | pp. 4–5 | `gex_implied_book` | notes |
| VEX / vanna | pp. 6–8 | `vex_vanna` | notes |
| GEX+ / maps / crash loop | pp. 9–12 | `squeeze_regimes` | notes |
| Falsifiers | hist extremes pp. 5, 8, 10–11 | `robustness` | notes |
| Living monitors | — | `paper_shadow` | notes |

---

## 3. Crypto adaptation (locked)

- **Primary options:** Deribit OI / IV surface (ETH first, then BTC).
- **Underlying TOB:** Hyperliquid + Deribit ETH marks/TOB; Kraken `spot_l2` **when dense**.
- **Forbidden:** `trade_synth` as SoT; soft-Promote of TOB-cross gaps as α.
- **Data:** warehouse / collector only — **no ClickHouse MCP** ([`../../../DATA_PATHS.md`](../../../DATA_PATHS.md)).
- **Honesty:** never Promote TOB-cross as α ([`../../../LOOP.md`](../../../LOOP.md) if present).

---

## 4. Pass checklist

### Pass 0
- [x] Extract claim + taxonomy with page cites
- [x] Lock crypto map in BOOK_DRAFT
- [ ] Empirics live in sibling packages (not this overview)

### Pass 1
- [ ] Signal roadmap vs existing liq / IV monitors
- [ ] Promote only after sibling falsifiers
