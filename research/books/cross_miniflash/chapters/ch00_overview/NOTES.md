# Ch.00 — Overview: five crash defs → state-space detection

**Book:** Tee & Ting (2019-06-12)  
**PDF:** §1 Introduction pp. 2–6 · roadmap §3–4 · **Status:** `exp_run` (Pass 1+2 vertical slice)  
**Raw:** [`../../_raw/`](../../_raw/) (local/gitignored)  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md) · Desk: [`../../DESK_MEMO.md`](../../DESK_MEMO.md)  
**Empirics:** [`../../out/phase2_baselines_ssm/`](../../out/phase2_baselines_ssm/)

---

## 1. Five definitions (§1) — info taxonomy (Pass 2)

| # | Source | Rule (paper) | Crypto mapping | Empirical class (this slice) |
|---|--------|--------------|----------------|------------------------------|
| 1 | **Nanex** | ≥10 uni-dir ticks, ≤1.5s, \|ΔP\|≥0.8% | Trade-count; θ∈{80,50,30} bps | **Liquidity hole / tape burst** — paper θ nearly empty; 30 bps fires |
| 2 | Outside BBO | Prints beyond bid/ask | Warehouse L2 / collector TOB | **Stale-book artifact** on sparse L2 (Hold) |
| 3 | Residual EPM | Top residual percentile | SSM standardized innovation | **Jump / tape outlier** — broader than Nanex |
| 4 | Lee–Mykland | Local-vol jumps | Competing (not run this phase) | Jump (deferred) |
| 5 | Dugast–Foucault | Large move + reversal | V / inv-V, 50% recovery | **Transient liq hole** — sparse; high SSM overlap when present |

**Paper claim (tested):** SSM captures a *broader* set than Nanex. **Supported:** Nanex→SSM precision ≈0.90, recall ≈0.026 on 42 cells (HL+Deribit+Kraken × ETH/BTC × 7 UTC days).

---


## PDF dig (pp. 2–6, 7–10, 11–15)

- **pp. 2–3:** Nanex (≥10 ticks, ≤1.5s, ≥0.8%), outside-BBO, residual EPM, Lee–Mykland, Dugast–Foucault V — five competing defs.  
- **pp. 4–6:** Motivation — mini crashes as microstructure objects; SSM as common detector.  
- **pp. 7–10:** State-space + MC-GARCH feed for σ_p, σ_m; standardized innovation z-score.  
- **pp. 11–15:** Crash stats ΔP / i_c / Δt / recovery; severity matters (raw outliers ≠ Nanex-style events).

Crypto desk: equity tick→trade count; RTH diurnal→UTC 5m; MCap→notional/OI proxy; 17 venues→HL+Deribit+Kraken.

## 2. Reading order

1. This overview → taxonomy + signal roadmap  
2. `crash_baselines` → Nanex / outside-TOB / V-shape  
3. `mc_garch_vol` → \(h_n,s_j,q\) → \(\sigma_p,\sigma_m\)  
4. `kalman_ssm` → KF + \(z^\*\) scan  
5. `crash_stats` → severity / recovery (Phase 3)  
6. `cross_section` + `frag_xvenue`  
7. Hardening → DESK_MEMO signal board

---

## 3. Signal roadmap (post Pass 2)

| Object | Desk label | Decision | Falsifier result |
|--------|------------|----------|------------------|
| Nanex 80 bps | baseline | **Kill** | 8 events / 42 cells |
| Nanex 30 bps | baseline PR | **Hold** | High SSM precision; θ fragile (80→30) |
| SSM \(z^*=6\) binary | risk monitor | **Hold** | σ_m frac 1→4 cuts events 3668→177 |
| SSM innovation / κ | info feature | **Hold** | Forward lead–lag ≈0 (not tradable) |
| Diurnal \(s_j\) / hour share | schedule | **Hold** | Peak UTC 12 this sample; mmip peak ~18 elsewhere |
| Outside-TOB (L2) | exec throttle | **Hold** | Warehouse L2 outside_rate 15–79% |

---

## 4. Pass checklist

- [x] Pass 1: PDF defs mapped; three-venue sample locked  
- [x] Pass 2: taxonomy + overlap tables + falsifiers  
- [x] EXP_REPORT + notebook Signal board → `exp_run`
