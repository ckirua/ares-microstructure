# Appendix A — Quantitative Toolbox

**Book:** Lehalle & Laruelle, *Market Microstructure in Practice* (2014)  
**PDF pages:** 248–315 (App.A)  
**Status:** `exp_run` (2026-09-30)  
**Artifacts:** [`../../out/appendix_quant/`](../../out/appendix_quant/)  
**Script:** [`../../scripts/exp_appa_toolbox.py`](../../scripts/exp_appa_toolbox.py)  
**Notebook:** [`appendix_quant.ipynb`](appendix_quant.ipynb)

Raw extracts: `research/_raw/appA_*.txt`, `appA_toolbox.txt`.

---

## 1. Scope (what we ship vs leave)

Highest-value App.A items that yield **liftable feature functions** for MM research (priority order):

| § | Tool | Shipped | Label |
|---|------|---------|-------|
| **A.5** | Harris tick / tick-constrained spread | **Yes** — `harris_tick_features` | D / quoting regime |
| **A.6** | Optimal schedule (E-min + mean–var toy) on real \(V_n\) | **Yes** — `schedule_*` + HL vol curve | E heuristic |
| **A.12** | Signature / Epps (corr vs Δ) | **Yes** — xasset + xvenue | D / hedge horizon |
| **A.11** | Hawkes / liquidity clusters | **Yes** — descriptive ACF + MoM | D intensity (honest limits) |
| **A.1** | FEI formalisms | **Link only** to Ch.1 (no redo) | D regime |
| A.3 / A.4 | SOR ODE / flash-crash toy | Not shipped (sim-only, low lift) | — |
| A.7–A.9, A.13 | Stats toolbox / averaging warning | Documented; no new exp | — |
| A.10 | Seasonality / volume model | Used as \(V_n\) input; Ch.2 owns vol curves | — |

---

## 2. Formulas (App.A → code)

### A.1 FEI (link)
\[
H(q)=-\sum_n q_n\log q_n,\qquad F=\frac{H}{\log N_{\mathrm{active}}}\in[0,1].
\]
Ch.1 implements TOB-size / update-count FEI; A.1 definition is **market-share** entropy. Spatial trade-notional FEI remains Hold.

### A.5 Harris tick
Observed spread in ticks \(\varepsilon=(A-B)/\tau\). Spread leeway \(\varepsilon-1\).  
Frac one-tick \(P(\varepsilon\le 1)\). Relative tick \(10^4\tau/M\).

Book continuous→discrete model (gamma MLE on FTSE) is **not** re-fit here; we ship the **regime diagnostics** the desk uses daily. Full MLE is Hold until multi-name equity-style tick tables exist.

### A.6 Schedule
Fair price \(S_{n+1}=S_n+\sigma_{n+1}\xi_{n+1}\). Impact
\[
\tilde S_n(v)=S_n+\kappa\sigma_n\Bigl(\frac{v}{V_n}\Bigr)^\gamma.
\]
**Prop.1 (E-min):** \(v_n\propto V_n/\sigma_n^{1/\gamma}\).  
**Prop.2:** constant context → uniform.  
**Mean–var:** \(C=\mathbb{E}(W)+\lambda\mathrm{Var}(W)\) with remaining inventory \(x_n\) (γ=1 toy via projected gradient).

κ, γ, λ are **research knobs**, not TCA-calibrated.

### A.11 Hawkes (1D, P=1)
\[
\lambda(t)=\lambda_0+\sum_{\tau_i<t}\alpha e^{-\beta(t-\tau_i)},\qquad
\mathbb{E}[\lambda]=\frac{\lambda_0}{1-\alpha/\beta}\ \ (\alpha/\beta<1).
\]
We report inter-arrival CV, count ACF, and a **MoM/OLS** \((\hat\lambda_0,\hat\alpha,\hat\beta)\) — **not** MLE. Branching ratio is indicative.

### A.12 Epps / signature
\[
\hat V_R(\Delta)=\sum_j r_\Delta(j)^2,\qquad
\hat C_R(\Delta)=\sum_j r^1_\Delta(j)\,r^2_\Delta(j).
\]
Epps: measured correlation rises with Δ under asynchronicity / microstructure.

---

## 3. Data & clocks

| Plane | Use |
|-------|-----|
| Collector TOB `xarb_md/tob/20260929` | Harris (HL/Lit/RX ETH) |
| Warehouse `load_trade_tape` HL ETH DENSE days | Volume curve \(V_n\), Hawkes events |
| Deribit `load_mark_bars` ETH/BTC | Xasset Epps / signature (1m marks) |
| HL `l2_rebuild` vs Deribit mark | Xvenue Epps |
| Ch.1 `out/ch01_fragmentation/` | FEI link only |

**No ClickHouse MCP.** Clocks: collector receive/exchange fields as stored; warehouse trade `ts_ns`; mark bars on `time` datetime64[ns].

---

## 4. MM use (one-liners)

| Feature | Desk action |
|---------|-------------|
| `tick.frac_one_tick` / leeway | Quote regime: tick-constrained → compete on size/skew/cancel |
| `sched.expectation_min` | Parent child weights ∝ \(V_n/\sigma_n\) (POV baseline) |
| `epps.xvenue_corr(Δ)` | Min hedge/sync horizon before cross-venue corr is usable |
| `hawkes.branching_proxy` | Intensity / toxicity gate research (do not live-trade MoM) |
| FEI (Ch.1) | Regime monitor — see Ch.1 Promote list |

---

## 5. Honesty

- Harris: descriptive regime, not decimalization forecast MLE.  
- Schedule: no fill feedback; σ from trade-price increments is a **proxy**.  
- Epps xasset on 1m marks is already coarse → little classic decay; **xvenue** shows the effect.  
- Hawkes MoM ≠ production point-process fit.  
- FEI: do not confuse TOB-size FEI with trade market share.
