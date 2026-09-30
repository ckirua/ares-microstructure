# Ch.6 Strategic trade models (Kyle)

**PDF:** pp. 41–51 · **Status:** `notes` (theory study guide; empirics via impact / POV)  
**Raw:** [`../../_raw/ch06_strat.txt`](../../_raw/ch06_strat.txt)  
**Notebook:** `ch06_strategic.ipynb` (synthetic Kyle paths — labeled as such)  
**Out:** [`../../out/ch06_strategic/`](../../out/ch06_strategic/) · **Plot:** `scripts/plot_ch06_strategic.py`

---

## 1. Sequential vs strategic (why Kyle)

In sequential trade (Ch.5), informed agents trade once if drawn; if size is a choice, they take the maximum. Kyle (1985) differs in both respects:

- **One** informed trader who chooses size strategically (internalizes price impact).
- In the multiperiod version she **returns**, splitting orders over time.

Order splitting to minimize impact is ubiquitous in practice (decimalization, fragmentation). Uninformed agents split too — the book stresses this is not “insiders only.”

Kyle is more stylized elsewhere: **no bid/ask**; all flow clears at one informationally efficient price \(p\). Useful extensions: Admati–Pfleiderer, Foster–Viswanathan, Holden–Subrahmanyam, Back continuous-time; Back–Baruch synthesis with sequential trade.

---

## 2. Single-period Kyle (6.a)

### Players and objects

| Object | Law / role |
|--------|------------|
| Terminal value \(v\) | \(v\sim N(p_0,\Sigma_0)\) |
| Informed demand \(x\) | chooses size knowing \(v\) |
| Noise / liquidity flow \(u\) | \(u\sim N(0,\sigma_u^2)\), independent of \(v\) |
| Net order flow \(y\) | \(y=x+u\) (MM observes \(y\), not \(x\)) |
| Clearing price \(p\) | set by MM after seeing \(y\) |

Nobody knows the clearing price when submitting.

### Linear conjectures and equilibrium

Informed conjectures \(p=\lambda y+\mu\). Expected profit \(\mathbb{E}[(v-p)x]\) yields

\[
x=\frac{v-\mu}{2\lambda}.
\]

MM conjectures \(x=a+bv\), computes \(\mathbb{E}[v\mid y]\), imposes market efficiency \(p=\mathbb{E}[v\mid y]\). Canonical Gaussian solution:

\[
\lambda=\frac{\Sigma_0^{1/2}}{2\,\sigma_u},\qquad
b=\frac{\sigma_u}{\Sigma_0^{1/2}},\qquad
\mu=p_0,\quad a=-b p_0.
\]

**λ is inverse liquidity:** larger noise variance ⇒ more camouflage ⇒ smaller λ; larger prior value variance ⇒ larger λ.

### Properties (desk intuition)

- Informed expected profits rise in \(|v-p_0|\) and in \(\sigma_u\) (noise as camouflage) — insider edge larger in widely traded names *before* apprehension.
- Conditional variance: \(\mathrm{Var}(v\mid y)=\Sigma_0/2\) — **half** of private information is impounded in the single-period price, independent of noise intensity (6.a.21).
- Informed can lose ex post if noise surges against her (unlike always-profitable sequential informed).

Problems 6.1–6.3 (informative noise, noisy signal, broker front-running \(g x\)) modify Cov / signal variance / piggyback — same linear–Gaussian toolkit.

---

## 3. Multiperiod Kyle (6.b)

\(N\) auctions on a unit interval; noise per auction \(u_k\sim N(0,\sigma_u^2\Delta t)\). Informed demand \(\Delta x_n=\Delta t\,(v-p_{n-1})b_n\); MM \(\Delta p_n=(\Delta u_n+\Delta x_n)\lambda_n\).

Backward recursions for \(\{a_k,d_k,b_k,\lambda_k\}\) with terminal \(a_N=d_N=0\); forward recursion for conditional variance \(S_n\). Numerical example (\(T=4\), \(\sigma_u^2=\Sigma_0=1\)):

- **\(S_k\) falls** over time — price becomes more informative.
- **\(b_k\) rises** — informed trades more aggressively later.
- **\(\lambda_k\) falls** — early trades have more impact than same-size later trades.

### Autocorrelation paradox (important)

Informed same-side splitting *seems* to imply positive order-flow autocorrelation (as in GM). In Kyle multiperiod, **market efficiency ⇒ martingale prices ⇒ uncorrelated price increments**. Since \(\Delta p\propto\) net flow, **net order flow is not positively autocorrelated** either — the informed “hides” behind noise so MM cannot forecast her next trade from \(y\). Contrast with Ch.5 / empirical HL sign ACF (ρ₁≫0): real tapes mix inventory, herding, and multi-agent info — not pure single-insider Kyle.

### More auctions, fixed total noise

As \(T\) rises, noise *per* auction falls; informativeness paths and λ schedules change (book figures for \(T=1,2,4,8\)). Continuous-time Back limit is the natural extension.

---

## 4. Empirical map (do not fit closed-form Kyle λ on HL here)

| Book object | Our candidate | Package | Decision |
|-------------|---------------|---------|----------|
| λ (impact of signed flow) | `disc.var_lambda`, `disc.irf_permanent`, `disc.mrr_theta` | ch13 / ch14 | Promote (aligned); use as TCA prior |
| Continuous-flow impact | `cont.ofi_mid_corr` | ch13 | Promote |
| Order splitting / schedule | mmip `sched.pov_*`, `impact.temp_perm` | mmip ch03 | Promote (mmip) |
| Camouflage / toxicity timing | `cont.vpin` | ch15 | Promote |

Identification warning: λ from trades needs **quote-aligned** Δmid (Ch.13). Contaminated asof-mid historically gave wrong-sign λ_VAR — documented Hold until fixed.

---

## 5. Crypto transfer

- No batch clearing price; continuous CLOB + maker/taker. Still treat empirical λ / IRF / MRR θ as **permanent-impact priors** for TCA and POV sizing.
- “Hide in noise” ↔ prefer taking in high-intensity / high-VPIN regimes carefully (toxicity vs camouflage — opposite desk uses of the same volume clock).
- Multi-agent informed flow + inventory ⇒ empirical sign ACF looks more GM than pure Kyle.

Cross-links:

- mmip optimal trading: [`../../../mmip/chapters/ch03_optimal_trading/`](../../../mmip/chapters/ch03_optimal_trading/)
- Hasbrouck structural / VAR: [`../ch14_structural/`](../ch14_structural/), [`../ch13_var_impact/`](../ch13_var_impact/)
- Sequential parent: [`../ch05_seq_info/`](../ch05_seq_info/)

---

## 6. Study checklist (figures in notebook)

Synthetic (labeled) plots under `out/ch06_strategic/`:

1. **λ vs \(\sigma_u\)** and **λ vs \(\Sigma_0\)** — inverse liquidity comparative statics.
2. **Single-period scatter** — simulated \((y,p)\) cloud with slope λ.
3. **Multiperiod paths** — cartoon \(S_k\), \(b_k\), \(\lambda_k\) over auctions (book T=4 numbers).
4. **Split vs dump** — schematic cumulative inventory of informed under splitting (intuition only).

Then read Ch.13 IRF / Ch.14 MRR for measured impact on ETH.

---

## 7. Code / artifact map

| Piece | Location |
|-------|----------|
| Notes (this file) | `chapters/ch06_strategic/NOTES.md` |
| Candidates | `CANDIDATES.md` (theory Hold) |
| Schematic plots | `scripts/plot_ch06_strategic.py` |
| Notebook | `ch06_strategic.ipynb` |
| Empirics | ch13 / ch14 / mmip ch03 |
