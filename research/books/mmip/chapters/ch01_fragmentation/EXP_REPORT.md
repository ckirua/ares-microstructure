# EXP_REPORT — Ch.1 Fragmentation (MM memo)

**Classification:** Research memo · paper only · no orders  
**Authors/plane:** ares-microstructure ← startarb collector TOB  
**Date:** 2026-09-30  
**Decision summary:** Promote `frag.crossed_nbbo` (gate), `tick.*`, `frag.update_share` (monitor). Hold FEI-size / trade-FEI spatial. Kill duplicate-best on this panel.

---

## 1. Executive takeaway

On a ~71 min HL/Lit/RX ETH collector window, **visible size is concentrated** (HL ~91%, FEI_size ≈ **26%**) while **quote updates are fragmented** (FEI_updates ≈ **82%**). The consolidated book is **crossed in ~100% of 1s buckets** (mean cons. spread ≈ **−6.2 bps**) — treat as latency/fee/segment mismatch, **not** arb. HL is **tick-constrained** (~99% 1-tick). Desk action: use crossedness as a **no-naive-take gate**; use update-vs-size divergence as a **flicker/toxicity monitor**; do not treat TOB FEI as trade market share.

---

## 2. Definitions & formulas

| Symbol | Definition | Units / clock |
|--------|------------|---------------|
| Venue set | \(V=\{\mathrm{HL},\mathrm{Lit},\mathrm{RX}\}\) DEX perps (collector) | taxonomy: crypto DEX |
| TOB size | \(z_v = b^{\mathrm{qty}}_v + a^{\mathrm{qty}}_v\) | coin @ L0 |
| Size share | \(q_v = z_v / \sum_u z_u\) | share ∈ [0,1] |
| Entropy | \(H(q)=-\sum_{q_v>0} q_v\log q_v\) | nats |
| FEI | \(F=H/\log N_{\mathrm{active}}\) | ∈ [0,1] |
| Spread | \(s_v=10^4(A_v-B_v)/M_v\), \(M=(A+B)/2\) | bps |
| Tick | \(\hat\tau=\min\{\Delta p>0\}\) on observed BBO prices | price units |
| 1-tick frac | \(P(A-B \le \hat\tau + \epsilon)\) | fraction |
| NBBO | \(B^\*=\max B_v\), \(A^\*=\min A_v\) | exchange timestamps bucketed |
| Crossed | \(B^\*>A^\*\) | indicator |
| Cons. spread | \(10^4(A^\*-B^\*)/((A^\*+B^\*)/2)\) | bps (neg if crossed) |

**Honesty:** FEI here is on **TOB size**, not book eq. 1.1 trade notional. Update-share FEI is an **activity** metric, not liquidity stock.

---

## 3. Data & method

| Item | Detail |
|------|--------|
| Source | `/home/dev/srv/ares-startarb/results/xarb_md/tob/20260929/` |
| Window | ns `[1790715569912889710, 1790719820774579807]` ≈ **4251 s** (~71 min) |
| Clock | Collector receive / exchange fields as stored in parquet; alignment = **1s floor buckets** last-quote |
| Universe | ETH (+ BTC parallel); RiseX `ETH/USDC`→`ETH` |
| Missing | No fill tape; no fee model in metric; warehouse not used for primary FEI |
| Baseline | Book Table 1.2: 50/50→FEI=1; 70/20/10→0.73; 70/20/5/5→0.63 |
| Survivorship | Single collector session — not multi-day |

Iterate (temporal trade FEI): HL ETH warehouse tape DENSE days 14–16∪25–26; FEI of **UTC hourly notional** mean ≈ **0.89** (see `out/ch01_fragmentation/exp_ch01_trade_fei_eth_*`). Label: **temporal concentration**, not spatial fragmentation.

---

## 4. Results (ETH primary; BTC in summary JSON)

| Metric | ETH | BTC (2-venue) | Baseline / note |
|--------|-----|---------------|-----------------|
| FEI size (time-avg bucket) | **0.259** | 0.141 | ≪ 0.63 (70/20/5/5) → concentrated |
| FEI updates | **0.820** | 0.714 | High activity fragmentation |
| Size share HL | **90.9%** | (dom.) | Monopoly-like size |
| Update share Lit | **63.0%** | — | Flicker candidate |
| Mean spread HL / Lit / RX | 0.38 / 0.43 / 0.68 bps | HL 0.13 / Lit 0.38 | |
| Frac 1-tick HL | **99.1%** | 98.8% | Tick-constrained quoting |
| Dup bid / ask | 0.0% / 1.1% | ~0.2% / 0.7% | Kill duplicate metric |
| Crossed frac | **100%** | (see BTC JSON) | Gate, not arb |
| Mean cons. spread | **−6.25 bps** | — | Stale/fee/segment |

FEI size path p10/p50/p90 (ETH): 0.035 / 0.255 / 0.478.

---

## 5. MM interpretation

| Desk function | Implication |
|---------------|-------------|
| **Quoting** | On HL, spread rarely a free parameter (~1 tick) → compete on **size/skew/cancel**; on Lit, spread more continuous |
| **SOR / take** | Never take “NBBO” naively while `frag.crossed_nbbo=1`; require fee+latency model |
| **Inventory / hedge** | Size share says HL is the depth island; update share says Lit is noisy — hedge primary on HL marks |
| **Toxicity** | `update_share ≫ size_share` → adverse-selection / flicker monitor |
| **Make vs take** | Tick-constrained maker: edge from queue position, not spread capture in bps |

---

## 6. Promote / Hold / Kill

See [`CANDIDATES.md`](CANDIDATES.md). Notebook: [`ch01_fragmentation.ipynb`](ch01_fragmentation.ipynb).

Artifacts: `research/books/mmip/out/ch01_fragmentation/`.
