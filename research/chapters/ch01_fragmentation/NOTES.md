# Chapter 1 — Monitoring the Fragmentation at Any Scale

**Book:** Lehalle & Laruelle, *Market Microstructure in Practice* (2014)  
**PDF pages:** 56–135 (plus App A.1 FEI formulas, pp. 248–250)  
**Status:** `exp_run` (2026-09-30)  
**Artifacts:** [`../../out/ch01_fragmentation/`](../../out/ch01_fragmentation/)

---

## 1. What the chapter claims (actionable)

### 1.1 Market share is *a* liquidity metric, not *the* liquidity metric
- Fragmentation exists at operator / venue / orderbook / **order** scales.
- Market share \(M_k(n;[t_1,t_2])\) = venue notional / total notional (eq. 1.1); trade-count share is a cruder alternative (eq. 1.2).
- Shares are **interval-dependent** (open vs close; continuous vs auctions). Fixing auctions often monopolized by primary venues — omitting them biases “continuous” share.

### 1.2 Entropy / FEI measures how “relaxed” liquidity is across pools
- Entropy \(H(q)=-\sum q_n\log q_n\); max over \(N\) pools is \(\log N\).
- **FEI** \(F=H/\log N\) ∈ [0,1] (reported as %). Perfect equal share → FEI=100%; monopoly → 0%.
- Table 1.2 benchmarks: 70/20/5/5 → ~63%; 50/50 → 100%.

### 1.3 SOR is structural, not optional
- Child orders must split in **time and space**.
- Aggregate visible liquidity; beware **duplicate liquidity** from multi-venue HFT makers (same size mirrored → naive SOR overstates depth).
- Primary-market variance / flow quality feeds secondary share dynamics.

### 1.4 Tick size shapes quality and participant PnL
- Tick = price grid → min spread, queue priority value, “queue jumping” cost.
- Constrained (large) tick → spread often **1 tick**; smaller tick → tighter quoted spread but thinner sizes, more instability / flickering.
- Venues can weaponize tick regimes for market share.

### 1.5 Dark pools
- Midpoint / reference-price mechanisms; toxicity and price-discovery leakage risks.
- **Not directly testable** on current crypto HL/Lit/RX lit panel → parked.

---

## 2. Candidate features / signals / strategies

| ID | Idea | Implementation sketch | Edge hypothesis |
|----|------|----------------------|-----------------|
| `frag.fei_tob_size` | FEI from visible TOB size shares | 1s aligned TOB; \(q_n\propto\) bid_sz+ask_sz | Low FEI = liquidity monopoly → worse SOR / higher impact on thin venues |
| `frag.venue_size_share` | Per-venue size share time series | same | Rising share predicts short-horizon quote leadership |
| `frag.update_share` | Quote-update intensity share | event counts | High update + low size = “flickering” / unstable liquidity (Ch.1.3) |
| `frag.crossed_nbbo` | Consolidated max-bid > min-ask | multi-venue asof join | Persistent cross = latency/fee basis → xarb / SOR urgency |
| `frag.duplicate_best` | ≥2 venues on NBBO same price | tol = ½ tick | High duplicate → discount mirrored depth in SOR (book warning) |
| `tick.frac_one_tick` | P(spread = 1 tick) | inferred tick from grid | High = tick-constrained regime; maker edge vs taker differs |
| `tick.spread_bps` | Quoted spread | BBO | Regime input to cost floor / gate |
| `sor.child_split` | Size-proportional route to venues with FEI-aware caps | needs live OE | Better fill vs single-venue when FEI mid/high and books not crossed |

See also [`CANDIDATES.md`](CANDIDATES.md).

---

## 3. Experiment (2026-09-30)

**Script:** `research/scripts/exp_ch01_fragmentation.py`  
**Data:** `/home/dev/srv/ares-startarb/results/xarb_md/tob/20260929/` (WS collector; HL + Lighter + RiseX). RiseX symbols normalized (`ETH/USDC` → `ETH`).  
**Not used:** ClickHouse. Warehouse trade tape deferred to iterate backlog (true notional share).

### ETH (~71 min collector window)

| Metric | Result |
|--------|--------|
| Venues in panel | hyperliquid, lighter, risex |
| Aligned 1s buckets | 1,451 |
| **FEI (time-avg of bucket TOB-size FEI)** | **25.9%** |
| FEI (update-count shares) | 82.0% |
| Size shares | HL **90.9%** / Lit 3.5% / RX 5.6% |
| Update shares | HL 13.4% / Lit **63.0%** / RX 23.5% |
| Mean spread (bps) | HL 0.38 / Lit 0.43 / RX 0.68 |
| Frac 1-tick spread | HL **99.1%** / Lit 15.2% / RX 50.1% |
| Duplicate best bid / ask | 0.0% / 1.1% |
| **Crossed consolidated book** | **~100%** (mean cons. spread ≈ **−6.2 bps**) |

**Live public REST snapshot (HL L2 + Binance spot bookTicker):** FEI_size ≈ 67% (HL 82% / BN 18% TOB size); BN spread ~0.04 bps vs HL ~0.37 bps — different venue class, sanity check only.

### Interpretation vs the book
1. **FEI low on size (~26%) but high on updates (~82%)** — mirrors the chapter’s warning that “activity” ≠ “liquidity stock”. Lit/RX chatter; HL holds the size.
2. **HL is tick-constrained** (≈1 tick almost always); Lit is not — matches 1.3 qualitative split between large-tick and small-tick regimes.
3. **Persistent HL bid > Lit/RX ask** (~6 bps mid gap) is exactly why SOR / spatial split matters (1.2): a naive single-venue view misses the consolidated (here: crossed) book. Treat as **latency/basis/fee artifact** until fill-level honesty (startarb persist-edge style) validates takable edge — do **not** promote to live arb from TOB alone.
4. **Duplicate liquidity rare** on this panel — different from equity HFT mirroring anecdote; crypto venues here look **segmented**, not mirrored.

### Honesty / blockers
- TOB size ≠ trade notional market share (eq. 1.1). Need `load_trade_tape` for FEI_trade.
- Collector window is short (~1h); not a day-scale FEI path like the book’s CAC40 charts.
- RiseX symbol naming required base normalization.
- No dark-pool analogue in this MD set.
- Warehouse `/srv/raw` absent on host; S3 cache works for marks/trades when needed via startarb `uv run`.

---

## 4. Next on this chapter
- FEI from **trade notional** shares (warehouse) on DENSE days.
- Hour-bucket FEI path (link to Ch.2 intraday rhythms).
- Soft-gate prototype: skip Lit/RX taker when `frag.crossed_nbbo` and mid gap < fee+slip floor (connects to startarb xarb kill list).
