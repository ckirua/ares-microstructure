# EXP_REPORT — Appendix A Quantitative Toolbox (MM memo)

**Classification:** Research memo · paper only · no orders  
**Authors/plane:** ares-microstructure ← startarb collector + warehouse  
**Date:** 2026-09-30  
**Decision summary:** Promote Harris tick regime + leeway, expectation-min schedule on real \(V_n\), xvenue Epps horizon, trade-count ACF. Hold full Harris MLE, mean–var λ, xasset Epps on 1m marks, Hawkes MoM branching. Kill SOR/flash toys.

---

## 1. Executive takeaway

App.A tools map cleanly onto the crypto panel: **HL is tick-constrained** (frac 1-tick ≈ **99%**, leeway ≈ 0), while **Lighter is continuous** (≈15% 1-tick, mean ε ≈ **11.5**). Expectation-min schedules on HL ETH volume curves deviate from uniform by mean L1 ≈ **0.40** — flat TWAP is a bad prior. **Cross-venue Epps is real**: HL mid vs Deribit ETH mark correlation is ~0 at Δ≤60s and rises to **~0.87 at 600s**. Trade arrivals are clustered (CV≫1; lag-1 ACF 0.17–0.44). Do **not** treat MoM Hawkes \(R\) or uncalibrated mean–var λ as production signals.

---

## 2. Definitions & formulas

See [`NOTES.md`](NOTES.md). Units: spreads in **bps** and **ticks**; schedules as **shares of parent** (∑v=1); correlations dimensionless; Hawkes rates in **events/s**; FEI ∈ [0,1].

---

## 3. Data & method

| Item | Detail |
|------|--------|
| Harris | Collector TOB `/ares-startarb/results/xarb_md/tob/20260929/` ETH; venues HL/Lit/RX; tick = min positive Δp on BBO |
| Schedule / Hawkes | `load_trade_tape` HL ETH days 2026-09-14,15,16,25,26 (DENSE); hourly UTC \(V_n\); σ proxy = std of within-hour trade log-increments |
| Epps xasset | Deribit `load_mark_bars` ETH-PERPETUAL & BTC-PERPETUAL, 60s bars, same days |
| Epps xvenue | HL `l2_rebuild` ETH mid vs Deribit ETH mark on **2026-09-26**; last-tick sync |
| FEI link | Read Ch.1 JSON only — no recompute of spatial FEI |
| Missing | Lit/RX trade tape; fill/TCA logs for κ,λ; tick-level marks for xasset Epps |
| Survivorship | Single collector session for Harris; 5 DENSE HL days for tape |

Script: `research/scripts/exp_appa_toolbox.py` → `research/out/appendix_quant/`.

---

## 4. Results

### A.5 Harris (collector ETH)

| Venue | \(\hat\tau\) | frac 1-tick | mean ε (ticks) | mean leeway | mean spread bps |
|-------|-------------|-------------|----------------|-------------|-----------------|
| hyperliquid | 0.10 | **0.991** | 1.02 | 0.02 | 0.38 |
| lighter | 0.01 | **0.152** | 11.52 | 10.52 | 0.43 |
| risex | 0.01 | 0.501 | 18.19 | 17.19 | 0.68 |

### A.6 Schedule (HL ETH, 5 days)

| Metric | Value |
|--------|-------|
| Mean L1(\|E-min − uniform\|) | **0.397** |
| Peak E-min participation (day range) | 0.075–0.116 of parent |
| Volume peak hours (examples) | 18–20 UTC common; day-dependent |

Mean–var toy (λ=5e−3) pulls toward flatter / earlier participation vs pure E-min — **Hold** until κ/λ calibrated.

### A.12 Epps

| Pair | Δ | corr |
|------|---|------|
| Deribit ETH–BTC marks | 60s … 1800s | **0.971 → 0.975** (no classic decay — already coarse/sync) |
| HL mid vs Deribit ETH | 5s | ≈ **0** |
| same | 60s | ≈ **−0.01** |
| same | 300s | **0.805** |
| same | 600s | **0.871** |

### A.11 Hawkes descriptive (HL ETH trades)

| Day | n | rate /s | interarrival CV | ACF lag1 | MoM \(R=\alpha/\beta\) |
|-----|---|---------|-----------------|----------|------------------------|
| 09-14 | 230k | 2.68 | 8.68 | 0.175 | 0.70 |
| 09-15 | 267k | 3.11 | 2.80 | 0.311 | 0.70 |
| 09-16 | 198k | 2.30 | 2.56 | 0.247 | 0.78 |
| 09-25 | 148k | 1.78 | 2.44 | 0.308 | 0.45 |
| 09-26 | 70k | 0.81 | 1.97 | 0.435 | 0.54 |

### A.1 FEI link (Ch.1)

| Metric | Value |
|--------|-------|
| Ch.1 FEI size / updates | 0.259 / 0.820 |
| HL size share | 90.9% |
| Trade hourly FEI (temporal) | 0.892 |
| Book Table 1.2 70/20/5/5 | 0.628 |

---

## 5. MM interpretation

| Desk function | Implication |
|---------------|-------------|
| **Quoting** | HL: tick-bound → skew/size/cancel; Lit: manage continuous spread in ticks |
| **Execution / POV** | Weight children by \(V_n/\sigma_n\); do not default to uniform on HL ETH |
| **Hedge / xvenue** | Sub-minute HL↔Deribit corr is noise; plan sync ≥ minutes (Epps) |
| **Toxicity / intensity** | Elevated count ACF / CV → burst regime; widen or pause take |
| **Fragmentation** | Continue Ch.1 monitors; App.A does not replace trade-share FEI |

---

## 6. Promote / Hold / Kill

See [`CANDIDATES.md`](CANDIDATES.md). Notebook: [`appendix_quant.ipynb`](appendix_quant.ipynb).

Artifacts: `research/out/appendix_quant/` (`exp_appa_summary.json`, figures).
