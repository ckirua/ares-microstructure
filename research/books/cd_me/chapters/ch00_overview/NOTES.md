# Ch.00 — Overview: Constrained dealers & PIM taxonomy

**Book:** Huang–Ranaldo–Schrimpf–Somogyi (Nov 2021, SSRN 3960577)  
**PDF:** §1 Introduction (PDF pp. 2–7) · **Status:** `notes`  
**Raw extract:** [`../../_raw/paper.txt`](../../_raw/paper.txt) (local/gitignored)  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md) · Desk: [`../../DESK_MEMO.md`](../../DESK_MEMO.md)

---

## 1. Core claim (PDF pp. 2–5)

Paper: when FX dealers’ risk-bearing capacity is tight, the **elasticity of liquidity provision weakens**. Episodes of constrained dealers coincide with higher price inefficiency and a weaker co-movement between intermediated volume and inefficiency (PDF p. 2 abstract/intro; motivators pp. 4–5).

Desk test: public crypto tape cannot observe bank VaR/CDS. Map the claim onto **cross-venue LOP stress** (HL↔Deribit↔Kraken ETH) + **public DCM̂** (funding/basis/RV/imbalance PC1). Detection/monitor ≠ naked arb α.

| Object | Paper (FX) | Crypto desk mapping |
|--------|------------|---------------------|
| Dealer constraint | VaR, leverage, CDS, funding costs + FX vol (PDF p. 14) | DCM̂ = PC1 of \|funding\|, \|perp basis\|, RV, trade imbalance |
| VLOOP | Triangular LOP gap on midquotes (Eq. 2, PDF p. 10) | \|log(mid_i/mid_j)\| on latency-aligned TOB |
| TCOST | Cumulative arb half-spreads (Eq. 2, PDF p. 10) | Sum of relative half-spreads on arb legs |
| PIM | VLOOP + abs(TCOST) \| VLOOP>0 (Eq. 3, PDF p. 11) | Same construction on cross-venue pairs |
| VLM | Dealer-intermediated volume | Home-venue trade notional / intensity (HL preferred) |
| Elasticity | corr(VLM, PIM) drops in high-DCM regimes (PDF pp. 15–19) | Hourly corr(notional, PIM) split by DCM̂ quantile |

---

## 2. PIM taxonomy (PDF pp. 3–4, 8–11)

1. **VLOOP** — fundamental violation of the law of one price (midquote triangular / cross-venue gap).
2. **TCOST** — transaction costs an arbitrageur would incur to close the gap (limits-to-arbitrage reading, PDF p. 11).
3. **PIM** — encompassing inefficiency: `PIM_t = E[VLOOP_t + abs(TCOST_t) | VLOOP_t > 0]` (Eq. 3).

Paper facts to remember for Pass-1 honesty (PDF pp. 4, 12):
- PIM rises in stress / high vol / constrained dealers.
- VLOOP and TCOST show **commonality**; in FX, VLOOP is often an **order of magnitude smaller** than TCOST (Table 1, PDF p. 14).
- Quotes in the paper’s Olsen sample are **indicative** — “seemingly profitable” round-trips <0.2% frequency (PDF p. 10 fn. 5). Crypto warehouse TOB is research-grade, not HFT-executable → **Kill** TOB-cross α.

---

## 3. Empirical spine (reading order)

| § | Paper focus | Package | Pass-1 status |
|---|-------------|---------|---------------|
| §1 | Claim + taxonomy | `ch00_overview` | notes |
| §2 | VLOOP/TCOST/PIM construction | `pim_vloop_tcost` | pass1 |
| §3.1 | DCM + motivational elasticity | `dcm_proxies`, `elasticity_regimes` | pass1 |
| §3.2 | LSTAR / logistic G | `lstar_panel` | park (short tape) |
| §4 | Constrained-dealer model | `model_sim` | park |
| §5 | Robustness / falsifiers | `robustness` | Hold pending Pass 2 |
| Living | Monitor harness | `paper_shadow` | pass1 (`live_orders=false`) |

---

## 4. Crypto adaptation (locked)

- **Primary:** cross-venue LOP on ETH across Hyperliquid + Deribit + Kraken (then BTC).
- **Secondary (parked):** native ETH–BTC–USD triangles until multi-pair TOB confirmed.
- **Clock:** UTC-day panels; hourly buckets for PIM/VLM joins (paper uses hourly then daily sums — PDF p. 12).
- **Data:** warehouse / collector only — **no ClickHouse MCP** ([`../../../DATA_PATHS.md`](../../../DATA_PATHS.md)).
- **Honesty:** never soft-Promote TOB-cross as arb α ([`../../../LOOP.md`](../../../LOOP.md)).

---

## 5. Pass checklist

### Pass 1
- [x] Extract paper claim + PIM taxonomy with page cites
- [x] Lock crypto map + reading order
- [ ] Empirics live in sibling packages (not this overview)

### Pass 2
- [ ] Signal roadmap vs xarb / basis monitors
- [ ] Promote only after sibling falsifiers
