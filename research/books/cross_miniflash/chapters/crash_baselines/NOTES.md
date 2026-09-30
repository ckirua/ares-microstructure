# Crash baselines — Nanex, outside-TOB, V-shape

**Book:** Tee & Ting (2019)  
**PDF:** §1 Nanex / outside-BBO / V-shape defs pp. 2–3 · §4.2.1 Standard Approach pp. 11–13  
**Status:** `exp_run`  
**Lib:** [`../../../../lib/crash.py`](../../../../lib/crash.py) — `nanex_detect`, `outside_tob_flags`, `vshape_events`  
**Data:** HL + Deribit + Kraken via [`../../scripts/_data.py`](../../scripts/_data.py)  
**Out:** [`../../out/phase2_baselines_ssm/`](../../out/phase2_baselines_ssm/)

---

## Pass 1 — paper objects on crypto

### Nanex
Uni-directional run on trade clock: ≥`min_trades` (10), ≤`max_window_s` (1.5), |ΔP|≥θ.  
Equity ticks → **trade count** primary. Ablation θ ∈ {0.8%, 0.5%, 0.3%}.

### V-shape (Dugast–Foucault style)
First leg ≥θ in 1.5s, reverse leg recovers ≥50% in next 1.5s.

### Outside-TOB
Trade vs asof bid/ask. Collector TOB does **not** overlap 2026-09-04…10; warehouse L2 smoke on Deribit only.

### Sample
Complete UTC days 2026-09-04…10 × ETH/BTC × HL/Deribit/Kraken (**42 cells**).

---

## Pass 2 — overlap, toxicity, incremental info

| Detector | Pooled n | vs SSM precision | vs SSM recall | Jaccard |
|----------|----------|------------------|---------------|---------|
| Nanex 30 bps | 105 | **0.895** | 0.026 | 0.026 |
| V-shape 30 bps | 132 | ~0.86 | ~0.02 | ~0.021 |
| Nanex 80 bps (paper) | 8 | — | — | — |

**Toxicity (signed |imbalance| window):** Nanex pre≈0.56 → concurrent≈0.71 (toxicity rises into event). Day VPIN mean≈0.74 (reuse `cont.vpin` style buckets).

**Incremental info:** Conditional on SSM, Nanex adds a *severity/tape-burst* label (high precision subset). SSM alone is not a Nanex surrogate (low recall). V-shape mostly nested in SSM when it fires.

**Outside-TOB falsifier:** Deribit warehouse L2 outside_rate **0.15–0.79** — sparse quotes vs ms trades → **not** a crash detector on this path.

---

## Crypto clock notes
- 1.5s window retained for paper fidelity; 0.5s tight Nanex also logged.  
- Do not Promote paper 80 bps cutoffs on crypto without restating θ.

## Cross-link: Flora–Renò V-statistic (`v_shapes`)

Geometric Dugast–Foucault `crash.vshape_events` remains the Tee–Ting baseline.
Econometric Flora–Renò MinV lives in `research/lib/vstat.py` / `research/books/v_shapes/`.
Promote overlap IDs from v_shapes hardening: `risk.v_vs_jump_taxonomy`, `risk.egarch_minv_bands`, `risk.daily_minv_panel`, `risk.stress_day_minv`.
Do **not** merge APIs; use Pass-2 PR/overlap tables only.
