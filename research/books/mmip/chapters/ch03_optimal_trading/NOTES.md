# Chapter 3 — Optimal Organisations for Optimal Trading

**Book:** Lehalle & Laruelle, *Market Microstructure in Practice* (2014)  
**PDF pages:** 212–247 (printed Ch.3 ≈185–219) + App.A.6 scheduling (≈247–254)  
**Package path:** `research/books/mmip/chapters/ch03_optimal_trading/`  
**Status:** `exp_run` (2026-09-30)  
**Artifacts:** [`../../out/ch03_optimal_trading/`](../../out/ch03_optimal_trading/)  
**Cross-ref Ch.2:** inverted volume curve U≈0.56 (peak 18 UTC); Promote `vol.curve_intraday`, `vol.fei_hourly`, `spread.vol_link`.

---

## 1. What the chapter claims (actionable)

### 1.1 Trading stack is I/O + models + risk envelope + tactics (3.1)
- Dealing desks own TCA, broker comparison, and **benchmark choice** (VWAP, TWAP, Implementation Shortfall, Target Close, Liquidity-seeking) by investment style.
- Architecture (Fig 3.1): consolidated market data → models → algo risk layer → SOR / liquidity-seeking robots → venues.
- Models have three parts: **formula**, **parameter estimation** (daily), **accuracy / activate-deactivate**.

Canonical impact formula used in the stack (book eq. in 3.1.1 / A.6):

\[
I(v) = \kappa\,\sigma\,\Bigl(\frac{v}{V}\Bigr)^{\gamma}
\]

- \(\kappa,\gamma\): stock-dependent parameters (estimate offline).
- \(\sigma\): current volatility; \(V\): market volume over the slice; \(v\): algo volume → **participation rate** \(\rho = v/V\).

### 1.2 Two-layer algo (3.1.2 / A.6)
1. **Risk-control layer** (~1–30 min): trading **envelope** (min/max rate) balancing market impact vs market risk (Almgren–Chriss style).
2. **Tactics / liquidity seekers / SOR**: opportunistic fills inside the envelope (seconds).

TCA decomposition used on desk (book):

\[
\text{AVG Price} = \text{Immediate Price} + \text{Market Moves} + \text{Market Impact}
\]

\[
\text{AVG Price} = \text{Planned Price} + \text{Trading Efficiency} + \text{Market Impact}
\]

### 1.3 Intraday impact stylized facts (3.2.2)
- Impact vs arrival price rises **concavely** over order duration (0→100% of duration).
- After the order ends (100→200%), price **partially reverts** → temporary vs permanent split.
- Impact increases with **participation rate** and with **duration**, even independently (Figs 3.4–3.6).
- Extraday: systematic vs idiosyncratic impact (CAPM-style) → different investor styles (3.2.3–3.2.4). **Shipped** as `style.extraday_idio` on Deribit BTC/ETH/SOL 1m marks (see `EXP_REPORT_POV_IDIO.md`).

### 1.4 Optimal methods / benchmarks (3.3)
| Benchmark | Typical use (book Table 3.2) | Desk note |
|-----------|------------------------------|-----------|
| PoV / %Vol | Follow flow; reactive | Envelope on \(\rho_{\min},\rho_{\max}\) |
| VWAP / TWAP | Any depth; schedule to volume/time curve | Tracking error vs market |
| Implementation Shortfall | Urgency / alpha-timed | Arrival-price risk |
| Liquidity seeking | Fragmented books; dark + lit | SOR + fill-rate / posting |

Liquidity seeking must account for latency / fake depth (Turquoise cancel race example) — connects to Ch.1 `frag.crossed_nbbo` honesty gate.

### 1.5 Scheduling formulas (App A.6) — reference
Fair price: \(S_{n+1}=S_n+\sigma_{n+1}\xi_{n+1}\).  
Slice execution price: \(\tilde S_n(v)=S_n+\kappa\sigma_n(v/V_n)^\gamma\).  
Mean–variance cost \(C=\mathbb{E}(W)+\lambda\mathrm{Var}(W)\) → convex remaining-qty curve \(x_n\) (trade faster when \(\lambda\) large).

---

## 2. Labels (desk taxonomy)

| Label | Meaning |
|-------|---------|
| **D** | Descriptive metric (monitor / TCA input) |
| **T** | Tradable signal (edge hypothesis; paper until honesty clears) |
| **E** | Execution heuristic (schedule / SOR / envelope) |

---

## 3. Candidate features / signals / strategies

| ID | Type | Idea |
|----|------|------|
| `impact.kappa_gamma` | D | Fit \(\kappa,\gamma\) of \(I=\kappa\sigma\rho^\gamma\) on tape-proxy meta-orders |
| `impact.temp_perm` | D | Temporary vs permanent signed mid move around flow bursts |
| `impact.rho_slope` | D | Impact vs participation-rate schedule (book Fig 3.4) |
| `tca.is_vwap_gap` | D | Arrival mid vs window VWAP (IS-style descriptive) |
| `sched.pov_envelope` | E | Min/max \(\rho\) from impact+vol risk (A.6 stylized) |
| `sched.ac_curve` | E | Almgren–Chriss remaining-qty path for given \(\lambda\) |
| `lsor.fill_rate` | E | Venue fill-rate / posting (book §3.3.2) — needs OE |
| `lsor.latency_discount` | E | Discount depth on slow/far venues (book race example) |

See [`CANDIDATES.md`](CANDIDATES.md).

---

## 4. Experiment (2026-09-30)

**Script:** `research/books/mmip/scripts/exp_ch03_trading_impact.py` → artifacts in `out/ch03_optimal_trading/`  
**Data:** HL ETH warehouse `load_trade_tape` on DENSE days 2026-09-14…16 ∪ 25–26 (no ClickHouse).  
**Method:** Non-overlapping 5m / 15m windows; **proxy** meta-orders = net signed aggressor flow (not proprietary fills).  
**Honesty:** \(\rho=|Q_{\mathrm{net}}|/V\) is **tape order-flow intensity**, not a single-algo POV. Temporary/permanent are mid returns aligned to that flow sign — stylized-fact proxies only.

### Headline results (see EXP_REPORT)
- 917k HL ETH trades → 1424×5m windows; Spearman(\(\rho\), \(I_{\mathrm{dur}}\))≈**0.19** (\(p\sim10^{-12}\)).
- High-\(\rho\) buckets ≈ **7.5 bps** duration impact vs ~0–1 bps at low \(\rho\).
- Mean \(I_{\mathrm{temp}}\) only **0.23 bps** at +5m post — impact mostly persistent on this horizon.
- \(\hat\gamma\approx0.17\), \(R^2=0.015\) → **Hold** `impact.kappa_gamma`.
- Promote: `impact.rho_slope`, `impact.temp_perm`, `sched.pov_envelope`, `lsor.latency_depth_haircut`.
- Cross-ref Ch.2: `vol.curve_intraday` (U≈0.56, peak 18 UTC) for schedule timing.

### Iterate 2026-09-30 — simulated POV + beta panel
**Script:** `research/books/mmip/scripts/exp_ch03_pov_idio.py` → `out/ch03_pov_idio/` + [`EXP_REPORT_POV_IDIO.md`](EXP_REPORT_POV_IDIO.md).

1. **Single-algo POV (simulated):** child = \(\pi\cdot V_t\) on HL ETH volume curve; realized POV tracks \(\pi\); \(I_{\mathrm{model}}=\kappa\sigma\pi^\gamma\) rises 0.57→2.55 bps as \(\pi\) 1%→20%. **Promote** `impact.algo_pov_sim` for scheduling / risk caps (not live TCA).
2. **Extraday sys/idio:** Deribit BTC/ETH/SOL 1m marks; ETH β≈0.93 vs BTC, var share sys/idio ≈**67%/33%**. **Promote** `style.extraday_idio` (was Kill). Short panel — document limits.

---

## 5. Next on this chapter
- Own paper-fill TCA (startarb shadow / persist) for true IS vs VWAP.
- Multi-venue child schedule + latency-discounted SOR (link Ch.1 crossed gate).
- Longer beta panel / equity-style index if available; calibrate κ,γ off shadow fills.
