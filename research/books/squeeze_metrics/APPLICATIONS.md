# Applications — squeeze_metrics implied-book monitors (wire-as playbooks)

**Companion:** [`DESK_MEMO.md`](DESK_MEMO.md) · [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) · Pass-2b dig [`out/pass2/`](out/pass2/) · [`out/info_features/`](out/info_features/) · [`out/feature_stats/`](out/feature_stats/) · notebook [`notebooks/info_stats_board.ipynb`](notebooks/info_stats_board.ipynb)  
**Honesty:** **0 Promote** on Pass-2b. Monitor → rule sketch → paper — not greenlit α.  
**Data:** certified `panel_gex_options` ETH **n=9**; Kraken spot_l2 n=4 appendix; DDOI=`PROXY_trade_flow_DDOI`; `trade_synth` **QUARANTINED**.  
**Shadow:** [`applications/paper_shadow/`](applications/paper_shadow/) wires **Promote only** (still 0).

Confidence: **high** = known failure modes · **med** = needs paper · **low** = research only.

---

## 0. Object → information → desk use

| Object | What it carries | Statistical claim (Pass-2b) | Wire-as | Tradable? |
|--------|-----------------|------------------------------|---------|-----------|
| **DDOI** | Trade-flow dealer-proxy inventory | Proxy only — not verified ΔOI | **monitor** | **no** |
| **GEX** | Dealer γ exposure | corr(GEX, HL RV)≈−0.22; day-block CI crosses 0; LOO flips | **monitor** | **no** |
| **VEX** | Dealer vanna | ΔR² after RV+GEX≈0 | **monitor** | **no** |
| **GEX+** | Additive liquidity score | scarce n=4/9 | **monitor** / escalate strip | **no** |
| **Squeeze intensity** | Scarcity / stress label | ΔR² after GEX≈0 | **monitor** | **no** |
| **Incremental** | GEX beyond RV | partial≈0 · ΔR²≈0 | research **monitor** | **no** |
| **Lead-lag / markout** | Day lag + intraday cum mid-ret | descriptive; lag−2 RV corr large but n thin | research **monitor** | **no** |
| **ToD / factor** | Hourly RV by regime · day PCA | commonality tile | research **monitor** | **no** |
| **Visible TOB** | HL/DB co-move | venue-drop concordant sign | **context** | **no** |
| **TOB-cross / synth** | — | — | **never-tradable** | **no** |

**Non-goals:** sized TOB-cross arb · synth-as-TOB · ClickHouse MCP · soft-Promote Holds.

### Use-map buckets (Pass-2b)

| Bucket | Candidates |
|--------|------------|
| **monitor** | `risk.gex_exposure`, `risk.vex_exposure`, `risk.squeeze_intensity`, `liq.implied_book_scarcity`, all `info.*` Holds |
| **throttle** | *(none wired — scarcity escalate stays sketch)* |
| **never-tradable** | `alpha.tob_cross_arb`, `data.trade_synth` |

Artifact: [`out/info_features/use_map.json`](out/info_features/use_map.json).

---

## 1. Risk / kill-switches (Hold)

### 1.1 GEX dealer-γ strip

| Layer | Rule sketch | Conf |
|-------|-------------|------|
| Monitor | Day GEX + coverage (opt IV n, DDOI mode) | **high** |
| Escalate | GEX scarce **and** IV↑ → “dealer short γ” strip | **med** |
| Do not | Size TOB-cross arb (**Kill**) | **high** |

**Falsifiers (Pass-2b):** chrono range flip; day-block CI crosses 0; placebo fails p95; LOO sign flip — ceiling Hold.

### 1.2 VEX / squeeze intensity

| Layer | Rule sketch | Conf |
|-------|-------------|------|
| Monitor | VEX + GEX+ scarce flag | **high** |
| Escalate | Negative VEX cluster → liquidity-take regime | **med** |
| Ceiling | Hold until verified option OI | **high** |

---

## 2. Execution / SOR (Hold)

| Use | Conf |
|-----|------|
| Treat implied-book scarcity as **friction / risk context**, not SOR α | **high** |
| Kraken spot_l2 densify = feed-quality gate only (appendix) | **high** |

---

## 3. Research tiles (Hold)

| Tile | Artifact |
|------|----------|
| Lead-lag day map | `out/info_features/info_features.json` → `lead_lag` |
| Markout regimes | `out/info_features/figs/fig_markout_regimes.png` |
| Incremental after RV | ΔR²≈0 — GEX mostly vol-overlapping |
| ToD / stress | `fig_tod_rv.png` · `fig_stress_calm_rv.png` |
| Feature stats | `out/feature_stats/` |
| Desk synthesis figs | `out/desk_synthesis/figs/` + Pass-2b figs |

---

## 4. Wire policy

- Shadow `live_orders=false` forever until Promote exists.
- Promote count = **0**.
- Kill list sticky: `alpha.tob_cross_arb`, `data.trade_synth`.
