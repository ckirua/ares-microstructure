# Ch.13 Prices & trades (statistical) + Ch.10 sign dynamics

**PDF:** pp. 101–110 (toolkit 87–100; fitz text `_raw/ch13_var.txt`)  
**Status:** `iterate` (plot pass) · **Out:** [`../../out/ch13_var_impact/`](../../out/ch13_var_impact/)  
**Script:** `scripts/exp_ch13_ch14.py` · `plot_ch13_var_impact.py` · **Lib:** `research/lib/discrete.py`

---

## 1. Book specs (formulas)

### Trade direction (13.a)

With quotes: \(q_t=+1\) if trade above mid (buy), \(q_t=-1\) if below (sell). Midpoint prints and trade/quote sequencing errors contaminate \(q_t\). On HL we use aggressor side from the tape (not Lee–Ready).

### Model 1 — generalized Roll with observed \(q_t\) (13.b.1)

\[
m_t=m_{t-1}+w_t,\quad w_t=\lambda q_t+u_t,\quad p_t=m_t+c q_t
\]
\[
\Delta p_t=-c q_{t-1}+c q_t+\lambda q_t+u_t
\]

OLS on \(\Delta p_t\) identifies \(\{c,\lambda,\sigma_u^2\}\) when \(q\) is known and predetermined wrt \(\Delta p\). Random-walk variance (13.b.3):

\[
\sigma_w^2=\lambda^2\sigma_q^2+\sigma_u^2
\]

(trade-related / private vs public). Relative private-info share \(\lambda^2\sigma_q^2/\sigma_w^2\) (13.b.4).

### Autocorrelated / endogenous trades (Models 2–4)

- **MA(1) \(q\)** (13.b.5–14): information innov. is \(e_t^q=q_t-E[q_t\mid q_{t-1},\ldots]\); \(\Delta p\) regression on \(q\) lags or joint VAR.
- **Recursive contemporaneous structure** (13.b.15): \(y_t=\Phi_0 y_t+\sum_k\Phi_k y_{t-k}+e_t\) with \(\Phi_0=\begin{bmatrix}0&\lambda+c\\0&0\end{bmatrix}\) — \(q_t\to\Delta p_t\) only.
- **Endogenous \(q\)** (13.b.16+): inventory / momentum feedback \(q_t=a u_{t-1}+\cdots\) ⇒ must estimate joint dynamics; permanent impact still \(\sigma_w^2=\mathrm{Var}(e_t^q)\lambda^2+\sigma_u^2\) (13.b.25).
- **Contemporaneous public info in \(q\)** (13.b.27–31): no clean recursive \(\Phi_0\); interpretation of OLS residuals is ambiguous.

### Impulse response / permanent impact

Cumulative mid response to a +1 buy shock under Cholesky \(q\to\Delta m\) is the desk permanent-impact object (Model 3–4 VMA sum of price row → \(\lambda\)).

---

## 2. Crypto translation & clocks

| Term | Our definition |
|------|----------------|
| Venue / inst | Hyperliquid ETH perp |
| Quotes | Collector TOB (`xarb_md/tob`), ~0.5s median Δt |
| Trades | Warehouse `trade` tape (`load_trade_tape`) |
| \(q_t\) | Aggressor side ∈ {±1} |
| Clock (disc) | Trade → **first subsequent mid change** (primary) |
| Clock (cont) | 1s calendar OFI ↔ mid return |
| Markout | Signed mid move at fixed horizons (bridges disc/cont) |

**Honesty:** Collector TOB is research-grade (sub-second but not exchange matching-engine). Warehouse trades are tail-windowed per day — not certified full sessions.

---

## 3. Identification: asof-mid contamination → fix

### Contaminated construction (prior Hold)

```
mid_pre_t = asof(trade_t)          # last TOB mid with ts ≤ trade_ts
Δm_t      = mid_pre_{t+1} − mid_pre_t
pair with q_{t+1}                  # BUG: revision after trade t signed by next trade
```

Also: many trades share one stale mid between TOB updates ⇒ most Δm=0, jumps attributed to the wrong event. Empirically λ_VAR ≈ **−0.011** (wrong sign).

### Quote-update-aligned construction (shipped)

`quote_aligned_delta_mid(..., mode="next_mid_change")`:

\[
m_t^{\mathrm{pre}}=\mathrm{asof}(t),\quad
m_t^{\mathrm{post}}=\text{first quote mid after }t\text{ with }m\neq m_t^{\mathrm{pre}}\ (\Delta t\le 5\mathrm{s})
\]
\[
\Delta m_t=m_t^{\mathrm{post}}-m_t^{\mathrm{pre}}\quad\text{paired with }q_t
\]

Robustness modes: `pre_to_next_trade` (correct \(q_t\) on asof diffs), `quote_clock` (events = mid-changing quotes).

Lib: VAR via `signed_trade_var` / IRF via `impulse_response_trade`; hygiene via `lambda_time_split_bootstrap`.

---

## 4. Specs shipped

| Candidate | Spec | Lenses |
|-----------|------|--------|
| `disc.var_lambda` | Contemporaneous λ in recursive VAR + OLS hygiene | disc, info, exec |
| `disc.irf_permanent` | Cum IRF to +1 buy; train/test sign check | disc, info, exec |
| `disc.sign_acf` | ρ₁(q) clustering (Ch.10) | disc, mm, info |
| `cont.ofi_mid_corr` | L0 OFI ↔ 1s mid return | cont, info, mm |
| `info.markout_1s` | Signed 1s markout CI | info, mm, exec |

**Promote bar (λ):** full λ>0, train λ>0, test λ>0, bootstrap 95% CI lo>0.  
**Promote bar (IRF):** permanent same sign as λ on full + both chronological halves.

---

## 5. Desk relevance

| Function | Use |
|----------|-----|
| Quoting / AS | Positive λ + markout ⇒ widen / skew with signed flow |
| TCA / POV | Permanent IRF as prior for schedule impact |
| Cont path | Prefer `cont.ofi_mid_corr` when TOB dense; event λ when tape dense |
| Inventory | `disc.sign_acf` ρ₁≫0 ⇒ expect continuation, not bounce |

See `EXP_REPORT.md` / `out/ch13_var_impact/` for numbers.

---

## 6. Results interpretation (figure pass)

ETH window in `out/ch13_var_impact/` (plot pass 2026-09-30). Notebook: `ch13_var_impact.ipynb`. Regenerator: `scripts/plot_ch13_var_impact.py`.

Live headline numbers (quote-aligned `next_mid_change`, n_event≈35k):

| Object | Value |
|--------|-------|
| corr(Δm, q) primary | **0.477** (median lag ≈ 767 ms) |
| λ_VAR / λ_OLS | **0.027** / **0.199** |
| OLS train / test | 0.182 / 0.240 · boot CI **[0.195, 0.203]** |
| permanent IRF | **0.422** (train 0.378, test 0.414) |
| sign ρ₁ | **0.535** |
| OFI corr | **0.434** (scatter recompute ≈0.429) |
| markout 1s | **0.472 bps** CI [0.463, 0.481] |

### 6.1 Figure read

| Figure | What it shows | Desk take |
|--------|---------------|-----------|
| `fig_irf_cum.png` | Incremental Δm + q decay after +1 buy; cum IRF rises smoothly to ≈0.42 | Permanent impact prior for TCA/POV; train/test overlays same sign |
| `fig_var_coef.png` | Lagged Δm←Δm / Δm←q and q←Δm / q←q | High R²_Δm (≈0.87) partly persistence; λ_contemp is the structural contemporaneous hit |
| `fig_lambda_hygiene.png` | VAR λ vs OLS full/train/test + boot band | OLS λ ≫ VAR contemp (different conditioning); both >0 with CI lo>0 ⇒ Promote |
| `fig_alignment_corr.png` | corr(Δm,q) by mode | Primary 0.48 ≫ pre→next-trade 0.11 ≫ quote-clock 0.28 — alignment choice dominates sign of λ |
| `fig_sign_acf.png` | ACF(q) lags 1…20 | Slow decay from ρ₁≈0.54 — herding / inventory continuation, not bounce |
| `fig_ofi_scatter.png` | 1s L0 OFI vs mid return (bps) | Cont twin of disc impact; dense TOB → prefer this path |
| `fig_markout.png` | Signed markout 0.5 / 1 / 5s with CI | Strictly positive CIs — maker AS / taker edge decay for quoting |

### 6.2 Contaminated vs aligned (why plots matter)

Prior asof-mid + \(q_{t+1}\) produced λ_VAR≈**−0.011** (wrong sign). The alignment panel and IRF path are the visual hygiene check: if cum IRF flips sign on a half or corr(Δm,q) collapses toward 0 under the primary mode, do not Promote.

---

## 7. Toolkit fold-in — Ch.11–12 (no separate packages)

Ch.11–12 are time-series toolkit chapters; empirics live here (and Ch.9 univariate). Short pointers from `_raw/ch11_rw.txt` / `_raw/ch12_mvar.txt`:

### Ch.11 Random walks / unit roots / invertibility

- Inventory \(I_t\) linked to signs via \(q_t=-\Delta I_t\) (unit size). Independent \(q\) ⇒ \(I\) is a random walk (Garman divergence); stationary \(I\) constrains \(q\).
- Ask “does the series contain a **unit root**?” not just “is it a RW.” AR lag polynomial roots outside the unit circle ⇒ stationarity.
- Microstructure trap: large bounce + small \(\sigma_w\) can *look* stationary on eyeball/unit-root tests even when a martingale component exists (Roll mixture).
- **Over-differencing** a already-stationary series (e.g. inventory) destroys invertibility of the MA — do not blindly Δ everything “to be safe.”
- Desk map: mid / trade price → work in differences (Ch.9 VR / AR σ_w; Ch.13 Δm VAR). Sign \(q\) and inventory proxies → levels / ACF, not forced unit-root filters.

### Ch.12 Multivariate (VAR / VMA / IRF)

- Vector \(y_t=(\Delta p_t,q_t)'\) (or Δm,q): VMA \(y=q(L)e\), VAR \(f(L)y=e\); estimate truncated VAR by OLS, invert to VMA via forecasting unit shocks (12.a.6–7).
- **IRF** = VMA coefficients; permanent impact = long-horizon cumulated price response to a trade shock — exactly `disc.irf_permanent` here.
- Identification needs a recursive contemporaneous structure (Ch.13 Models 2–4 / Φ₀); public-info-in-\(q\) breaks clean recursion.
- Desk map: shipped quote-aligned VAR λ + cum IRF + OFI/markout bridges. SEs via bootstrap / day blocks (same spirit as Hamilton / Hasbrouck delta-method notes).

---

## 8. SECOND PASS — cross-links (13 ↔ 14 ↔ 15)

### 8.1 Ch.13 → Ch.14 (statistical → structural)

| Ch.13 object | Ch.14 twin | Notes |
|--------------|------------|-------|
| λ_OLS / λ_VAR on quote-aligned Δm | GH z₀, HS lump π̂ | Same mid-revision clock; GH R²≈24% ↔ HS π R²≈21% |
| permanent IRF ≈0.42 | MRR θ (trade Δp), HS two-way λ̂≈0.31 | Units differ (mid vs trade price); **sign family** and order of magnitude for schedule priors |
| ρ₁(q)≈0.54 | MRR ρ_q (Hold as discovery) | Same ACF; structural models need it for ID of unexpected trade |

Structural models **do not replace** the IRF — they decompose / reparameterize. Prefer IRF + markout for desk TCA; use GH/HS for AS narrative and spread-component talk.

### 8.2 Ch.13 → Ch.15 (impact → toxicity regimes)

- Sign clustering (ρ₁≫0) is the sequential fingerprint that PIN/VPIN summarize at day / volume-clock scale.
- High VPIN buckets (Ch.15 Promote ≈0.9) are when **widening from λ / markout** should be most aggressive.
- PIN day-mixture is too coarse for tick control; use Ch.13 markout + OFI intraday, Ch.15 VPIN as regime overlay.

### 8.3 Disc vs cont clocks (same chapter)

| Clock | Candidate | When to prefer |
|-------|-----------|----------------|
| Event (trade → next mid change) | `disc.var_lambda`, `disc.irf_permanent` | Tape dense, need permanent shock size |
| 1s calendar | `cont.ofi_mid_corr` | TOB dense, continuous quoting |
| Horizon markout | `info.markout_1s` | Bridge: signed mid move without VAR |

### 8.4 Code / artifact map

| Piece | Location |
|-------|----------|
| Quote-aligned Δm / VAR / IRF | `research/lib/discrete.py` |
| OFI / markout | `continuous.py` · `markout.py` |
| Batch Promote | `scripts/exp_ch13_ch14.py` |
| Figures | `scripts/plot_ch13_var_impact.py` · `out/ch13_var_impact/fig_*.png` |
| Notebook | `chapters/ch13_var_impact/ch13_var_impact.ipynb` |
