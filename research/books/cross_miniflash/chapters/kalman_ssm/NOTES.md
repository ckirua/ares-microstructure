# Kalman state-space crash detector

**Book:** Tee & Ting (2019)  
**PDF:** §3 SSM pp. 7–10 · §4.2.2 z-score detection pp. 13–15 · Table III \(z\in[2,12]\)  
**Status:** `exp_run`  
**Lib:** [`../../../../lib/crash.py`](../../../../lib/crash.py) — `kalman_ssm_filter`, `ssm_crash_mask`, `zstar_scan`  
**Out:** [`../../out/phase2_baselines_ssm/`](../../out/phase2_baselines_ssm/)

---

## Model (paper + crypto fix)

\[
\begin{aligned}
x_i &= x_{i-1}+\epsilon_{p,i},\quad \mathrm{Var}(\epsilon_p)=\sigma_{p,i}^2\Delta t_i\\
z_i &= x_i+\epsilon_{m,i},\quad \mathrm{Var}(\epsilon_m)=\sigma_{m,i}^2.
\end{aligned}
\]

KF predict / gain / update as usual. **Crash z-score** = standardized innovation

\[
z^\mathrm{crash}_i=\frac{z_i-\hat x_i^-}{\sqrt{P_i^-+\sigma_{m,i}^2}}.
\]

(Posterior residual / √P collapses when κ→1 on ms tape — rejected for detection.)

Default \(z^\*=6\). \(\sigma_m\) from MC-GARCH package with 1 bp noise floor, `frac=1`.

---

## Pass 1 — z*=6 counts by venue

| Venue | SSM events | Nanex 30bps (ref) |
|-------|-----------:|------------------:|
| hyperliquid | **3075** | 70 |
| deribit | **349** | 13 |
| kraken | **244** | 22 |
| **TOTAL** | **3668** | **105** |

Many SSM “events” are short runs with near-zero \(\Delta P\) — outlier prints, not Nanex-style crashes. Severity filtering deferred to `crash_stats`.

---

## Pass 2 — z* scan, continuous features, lead–lag

### Table III analogue (pooled)

| z* | events | flags |
|---:|-------:|------:|
| 2 | 36416 | 132362 |
| 4 | 9578 | 39275 |
| **6** | **3668** | **17884** |
| 8 | 1770 | 10033 |
| 10 | 1028 | 6238 |
| 12 | 630 | 4143 |

### Continuous features
- Mean Kalman gain κ and innov σ logged per cell.  
- Lead–lag corr(innov, Δlog): **backward** lags −0.5…−2s ≈ −0.59…−0.69 (mechanical); **forward** +0.5…+2s ≈ −0.02…−0.04 → **not tradable**.

### Falsifiers
- σ_m frac stress (see mc_garch): **Hold** binary Promote.  
- Time-split SSM early/late 2055/1868 — count stable.  
- Circular-shift placebo of z-path is run-count invariant (weak) — prefer σ/z* stress + severity filters.

---

## Crypto adaptations stated
- Standardized innovation (not posterior band).  
- Trade-scale \(\sigma_m\) + 1 bp floor.  
- UTC complete-day panel only.
