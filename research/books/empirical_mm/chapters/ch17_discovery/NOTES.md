# Ch.17 Linked prices: cointegration and price discovery

**PDF:** pp. 125–131 · **Status:** `exp_run` → `iterate` (content pass)  
**Out:** [`../../out/ch17_discovery/`](../../out/ch17_discovery/)  
**Scripts:** [`../../scripts/exp_ch17_discovery.py`](../../scripts/exp_ch17_discovery.py) · `plot_ch17_discovery.py` · notebook `ch17_discovery.ipynb`  
**Lib:** `research/lib/continuous.py` (`hasbrouck_info_share_2`) · `research/lib/epps.py` (`corr_vs_lag`)

---

## 1. What the chapter is about

Many microstructure hypotheses are statements about **multiple prices**: bid vs ask, NYSE vs regional, cash vs futures, or (our case) **HL vs Lighter** mid for the same ETH perpetual. When prices share a common efficient value, they are **cointegrated** — each is I(1), but a linear combination (usually the difference) is stationary.

Hasbrouck (1995) information shares (IS) attribute the variance of the common random-walk component to each market. The chapter also covers VECM representation, arbitrage-based cointegrating vectors, and case-study practice on multi-venue bids/asks.

Desk use in this program: **SOR / hedge lead**, not arb — measure which venue’s innovations dominate permanent mid moves and at what lag venues re-synchronize (Epps).

---

## 2. Theory map

### 2.1 Two Roll securities vs one security, two markets (17.a–b)

Two **different** securities: efficient prices \(m_{1,t}, m_{2,t}\) can diverge via firm-specific walks → not cointegrated (unless values are identical).

One security, two markets:

\[
m_t = m_{t-1}+u_t,\qquad
\begin{pmatrix}p_{1,t}\\ p_{2,t}\end{pmatrix}
=
\begin{pmatrix}1\\1\end{pmatrix}m_t
+
\begin{pmatrix}c_1 q_{1,t}\\ c_2 q_{2,t}\end{pmatrix}.
\]

Short-run \(p_1\neq p_2\) from market-specific costs and imperfect arbitrage; long-run \(p_1-p_2\) stays stationary → **cointegration**.

Price-change VMA (17.b.3) implies identical long-run forecasts of both prices. The common RW variance is \(s_w^2 = \psi\,\Omega\,\psi'\) with \(\psi\) the long-run multiplier row. When \(\Omega=\mathrm{Var}(e_t)\) is diagonal,

\[
\mathrm{IS}_i = \frac{\psi_i^2\,\mathrm{Var}(e_{i,t})}{s_w^2}.
\]

When \(\Omega\) is nondiagonal, **Cholesky orderings** give **bounds** (IS low/high) rather than a point. Narrower spread / higher precision quotes typically raise a market’s share.

### 2.2 VECM (17.b.9, 17.c)

Cointegration ⇒ level VAR of \(\Delta p\) alone is incomplete; include error-correction:

\[
\Delta p_t = \Phi(L)\Delta p_t + \gamma\,(p_{1,t-1}-p_{2,t-1}-a) + e_t.
\]

\(\gamma\) signs describe which venue **adjusts toward** the other; they are **not** unique under basis rotations of the cointegrating space. Book advice: prefer **VMA / impulse responses / IS** over storytelling from \(\gamma\) alone.

### 2.3 Multi-price and arbitrage (17.c–d)

Bids/asks across venues → \(a\neq 0\) (mean basis). Index–futures: cost-of-carry \(c\) in the EC term; threshold EC when arb only fires outside cost bounds. Nonlinear arb (options): invert pricing function to a common underlying metric.

### 2.4 Microstructure vs macro cointegration testing

High-frequency short panels have little power for “are prices RW?” / Johansen rank. Book stance: **assume** integration + economically dictated cointegrating vectors; focus on representation and attribution.

---

## 3. Our estimators (crypto)

| Candidate | Lens | Construction |
|-----------|------|--------------|
| `cont.info_share_hl_lit` | cont, info, exec | Align HL & Lighter mids on 1s calendar; differenced VAR(5) + Cholesky bounds (`hasbrouck_info_share_2`) |
| `cont.epps_xvenue` | cont, info, exec | Pearson corr of log-returns vs sampling lag 1s…300s (`corr_vs_lag`) |
| `disc.jump_sign_concord` | disc, info | On p90 \|Δ log mid_HL\| bars, fraction with matching Lit sign |

**Promote logic**

- IS: `ok` and finite bounds (not collapsed to trivial [0,1] noise / singular Ψ).
- Epps: curve informative — typically corr **rising** in lag (asynchronicity); falsifier = flat curve on overlapping window.
- Jump concordance: >0.55 on large HL moves (≠ coin-flip).

---

## 4. Empirical design

| Choice | Value | Rationale |
|--------|-------|-----------|
| Venues | Hyperliquid vs Lighter ETH TOB | Same underlying perp; collector coverage |
| Grid | 1s last-mid alignment | IS on contemporaneous Δlog mid |
| Lags | VAR(5) | Book case-study style truncation |
| Epps lags | 1, 5, 15, 60, 300 s | Sync horizon for hedging / lead-lag |
| Downsample | if \(n>20\mathrm{k}\), stride | Numerical stability |

**Not full Johansen VECM** — research-grade differenced VAR + long-run Ψ approximation. Good enough for ordinal venue weights; not a substitution for exchange surveillance papers’ full stack.

---

## 5. Results interpretation (see EXP_REPORT)

ETH window in `out/ch17_discovery/` (content-pass refresh):

- Aligned 1s mids \(n\sim 53\mathrm{k}\) (IS on ~26k after stride).
- IS HL bounds **[0.34, 0.97]**, Lit **[0.03, 0.66]** — one Cholesky ordering puts Lit ahead; bounds are **wide** (nondagonal \(\Omega\)).
- Epps: corr ≈ **0.10** at 1s → **0.61** at 5s → **0.81** at 15s → **0.94** at 60s → **0.99** at 300s — classic **Epps effect**; hedge sync horizon ≈ 15–60s for corr≳0.8.
- Jump sign concordance on **true 1s** p90 HL moves ≈ **0.56** (marginal vs coin-flip). Earlier ~0.74 came from stride-downsampled bars (longer effective Δt) — do not treat discrete concordance as a strong Promote alone.
- Mid basis (HL−Lit)/HL ≈ **5.4 bps** median (stable level, not exploding) — cointegration / EC story plausible as a nonzero \(a\).

Desk reading:

| Function | Implication |
|----------|-------------|
| **Hedge lead** | Prefer venue with higher IS **lower** bound as information leg; still size to bound width |
| **SOR** | Wide IS bounds ⇒ do not hard-code 100% HL; use Epps lag where corr exceeds hedge threshold (e.g. 0.8 ≈ 15s here) |
| **Arb** | Mild concordance + nonzero basis ≠ riskless arb; fees/funding/latency bind |
| **Risk** | Flat Epps ⇒ sync already or broken overlap — check clocks / collector gaps |

---

## 6. SECOND PASS — multi-venue caveats

### 6.1 HL vs Lit (crypto Tob) vs equity “lit”

Equity “Lit” usually means primary/displayed lit books vs dark. Here **Lighter** is another electronic perp venue, not a dark pool. Both are continuous limit-order venues with different:

- participant sets and maker/taker fees,
- collector sampling / WS cadence,
- possible index / mark conventions.

IS attributes **innovation variance in our mid streams**, not legal “who is the listing exchange.”

### 6.2 Lead–lag vs information share

| Metric | Asks | Weakness |
|--------|------|----------|
| **Lead–lag / Epps** | At what lag do returns correlate? Who moves first in event time? | Sensitive to sampling, clocks, and which side you condition on |
| **IS** | What fraction of permanent RW variance comes from each venue’s innovations? | Bounds wide when residuals correlated; ordering-dependent |
| **Jump concordance** | Do large moves agree in sign? | Discrete; ignores magnitude; contemporaneous by construction on 1s grid |

They answer different questions. High concordance + rising Epps + HL IS lower-bound ≫ 0.3 ⇒ HL is a useful **lead/info** venue for ETH in this window, but Lit still contributes under alternate Cholesky order.

### 6.3 Collector / clock caveats

- TOB from `xarb_md` is **not** exchange matching-engine time — use for research ordinal claims, not latency arb.
- Mutual overlap window only; missing Lit quotes ⇒ no Epps / IS.
- Downsampling for IS changes effective lag structure — report \(n\) and bar size.

### 6.4 Links to other chapters

- **Ch.13 IRF / λ:** single-venue permanent impact; Ch.17 is **cross-venue** permanent variance share.
- **Ch.22 ILLIQ:** liquidity state; discovery can migrate when one venue’s ILLIQ spikes (wider IS bounds / Epps shift).
- **Ch.8 noise:** microstructure noise inflates high-frequency return variance and **depresses** short-lag Epps corr — another reason corr rises with lag.

---

## 7. Code map

| Piece | Location |
|-------|----------|
| IS bounds | `research/lib/continuous.py` → `hasbrouck_info_share_2` |
| Epps curve | `research/lib/epps.py` → `corr_vs_lag` |
| Align mids | `scripts/_data.py` → `align_mids_calendar`, `load_venue_tob` |
| Batch Promote | `scripts/exp_ch17_discovery.py` |
| Figures | `scripts/plot_ch17_discovery.py` · notebook |

---

## 8. Candidates (summary)

| id | lenses | decision | falsifier |
|----|--------|----------|-----------|
| `cont.info_share_hl_lit` | cont, info, exec | **Promote** | bounds → [0,1] noise / Ψ singular |
| `cont.epps_xvenue` | cont, info, exec | **Promote** | corr flat in lag on overlap |
| `disc.jump_sign_concord` | disc, info | **Promote** | concordance ≈ 0.5 |

See `EXP_REPORT.md` for live numbers and figures.
