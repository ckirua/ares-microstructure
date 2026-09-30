# Ch.8 Univariate random-walk decompositions

**PDF:** pp. 61–71 · **Status:** `exp_run` → `iterate` (content pass)  
**Raw:** [`../../_raw/ch08_rw.txt`](../../_raw/ch08_rw.txt)  
**Paired empirics:** [`../ch03_roll/`](../ch03_roll/) · Out [`../../out/ch08_noise/`](../../out/ch08_noise/)  
**Scripts:** `plot_ch03_roll.py` (writes ch08 figs) · notebook `ch08_noise.ipynb`  
**Lib:** `research/lib/continuous.py` (`noise_robust_rv`, `calendar_returns`, `volume_clock_returns`) · Ch.9 AR/BN in `discrete.py`

---

## 1. What the chapter is about

Ch.7 generalized Roll with asymmetric information. Ch.8 steps back: **start from the MA of \(\Delta p\)**, not a structural model. Trading is too complex for definitive structures; implied statistical models are misspecified. If \(\Delta p\) is covariance-stationary, Wold ⇒ an MA exists and is estimable. From that MA alone we recover:

1. Variance of the efficient-price innovation \(\sigma_w^2\)
2. Projection of \(m_t\) on past \(\Delta p\) (Beveridge–Nelson)
3. A **lower bound** on \(\mathrm{Var}(p_t-m_t)\) (pricing-error variance)

without further economic assumptions (Watson 1986 framing; book 8.a–g).

Desk use: when Roll **Kill** (Ch.3), do not abandon permanent-vol measurement — use AR truncation → \(\sigma_w\) (Ch.9) and treat fine/coarse RV as a separate **sampling-noise** diagnostic.

---

## 2. Theory map

### 2.1 Structural sketch (8.a)

\[
m_t = m_{t-1} + w_t,\qquad
p_t = m_t + s_t,\qquad
s_t = q_w(L)w_t + q_h(L)h_t
\]

\(s_t\) absorbs transient costs, inventory, lagged adjustment. Statistical model:

\[
\Delta p_t = q(L)e_t.
\]

Then \(\sigma_w^2 = q(1)^2\sigma_e^2\). If we estimate AR \(\varphi(L)\Delta p_t=e_t\), invert \(q(L)=\varphi(L)^{-1}\):

\[
\sigma_w^2 = \frac{\sigma_e^2}{\varphi(1)^2}.
\]

Only the **sum** of AR coefficients is required for \(\sigma_w\) — full MA series expansion is optional (book 9 / Ch.4 toolkit).

### 2.2 Autocovariance generating function (8.b)

\(g_x(z)=\sum_i \gamma_i z^i\). For MA \(x=q(L)e\): \(g_x(z)=q(z^{-1})q(z)\sigma_e^2\). For AR \(f(L)x=e\): invert \(f\). Tool for proving identification of \(\sigma_w\) and pricing-error bounds without naming \(c\).

### 2.3 Beveridge–Nelson and pricing-error bound (8.g)

Among RW decompositions consistent with the MA, BN minimizes \(\mathrm{Var}(s)\); that minimum is the identifiable lower bound on pricing-error variance. Empirically we report \(\sigma_w\) from AR/MA (Ch.9) and separately report continuous **noise-robust RV** (fine vs coarse) as a sampling-noise diagnostic — **not the same object**.

### 2.4 Why MA-first matters on crypto

HL mid \(\gamma_1\ge 0\) kills Roll’s structural \(c=\sqrt{-\gamma_1}\). The MA/AR route still yields a permanent-innovation scale \(\sigma_w\) usable as a volatility / information prior for MM and TCA. That is the Ch.3 → Ch.8 → Ch.9 pipeline.

---

## 3. disc vs cont delivery

| Object | Discrete | Continuous |
|--------|----------|------------|
| Bounce / \(s_t\) | Roll \(c=\sqrt{-\gamma_1}\) (Ch.3 **Kill**) | — |
| Efficient innov. \(\sigma_w\) | AR→MA / MA(1) moments (Ch.9 **Promote**) | — |
| Sampling noise | — | `cont.noise_rv_ratio` (**Kill** — boot CI≈[0.87,0.91]) |
| Clock dependence | — | `cont.volclock_ac1` (**Hold**) |

---

## 4. Empirical design (cont candidates)

| Choice | Value | Rationale |
|--------|-------|-----------|
| Fine / coarse | 100 ms / 1 s mid RV | Bounce would inflate fine RV |
| RV curve | 100ms…30s | Shape check — rising fine RV = noise |
| Calendar | 1 s Δlog mid | Standard cont clock |
| Volume clock | \(50\times\) median qty bars | Activity time |

**Promote** `cont.noise_rv_ratio` only if ratio \(\gg 1\).  
**Kill** if ratio ≤1 (or boot CI hi ≤1.2) — no fine-RV inflation (our case ≈0.87, CI≈[0.87,0.91]).
**Promote** only if CI lo >1.2.

---

## 5. Results interpretation (see EXP_REPORT)

Same ETH window as Ch.3:

- **noise_ratio ≈ 0.90** — fine RV below coarse; collector mid is **not** bounce-dominated.
- RV vs horizon is roughly flat / slightly rising toward coarser bars (opposite of classic noise signature).
- Calendar AC1 ≈ 0.12 vs volclock ≈ 0.06 — same order of magnitude; no clock-alpha claim.

Desk reading:

| Function | Implication |
|----------|-------------|
| **HFT RV “correction”** | Do not apply equity-style noise corrections blindly to HL mid |
| **σ_w prior** | Prefer Ch.9 AR/BN on event Δlog mid |
| **Exec clocks** | Volume clock changes ACF mildly; not a standalone Promote |

---

## 6. SECOND PASS — BN vs RV vs Roll

### 6.1 Three different “noise” words

| Term | Meaning | Our metric |
|------|---------|------------|
| Roll bounce | Bid–ask reflection in trade px | \(\gamma_1\) / \(c\) — **Kill** |
| BN pricing error | Transient \(s_t=p_t-m_t\) | Lower bound via MA; report \(\sigma_w,\sigma_s\) in Ch.9 |
| Sampling noise | Discretization / collector jitter | `noise_rv_ratio` — **Kill** |

Conflating them produces bad desk features (e.g. “noise ratio as toxicity”).

### 6.2 Positive γ₁ and BN

When \(\gamma_1>0\), the Roll MA(1) with \(\theta<0\) (bounce) is the wrong structural story, but an invertible MA/AR on **returns** can still exist with small positive \(\theta\) (Ch.9 MA(1) mid \(\theta\approx 0.031\)). Permanent variance \(\sigma_w\) remains well-defined; the pricing-error interpretation of \(\sigma_s\) changes (momentum-like transient, not bounce).

### 6.3 Links

- **Ch.3:** Roll Kill is the motivation for Ch.8’s MA-first stance.
- **Ch.9:** Estimation case — moments, AR truncation, day-block SEs, VR pitfalls.
- **Ch.17 Epps:** Microstructure noise depresses short-lag cross-corr; our low fine-RV inflation implies Epps here is mostly **asynchronicity**, not bounce.

---

## 7. Code map

| Piece | Location |
|-------|----------|
| Noise RV | `continuous.noise_robust_rv` |
| Clocks | `calendar_returns`, `volume_clock_returns` |
| BN \(\sigma_w\) | `discrete.ar_ols` + `rw_variance_from_ar` (Ch.9) |
| Figures | `scripts/plot_ch03_roll.py` → `out/ch08_noise/` |

---

## 8. Candidates (summary)

| id | lenses | decision | falsifier |
|----|--------|----------|-----------|
| `cont.noise_rv_ratio` | cont, info | **Kill** | ratio ≤1 / boot CI hi≤1.2 |
| `cont.volclock_ac1` | cont, exec | **Hold** | AC1 ≈ calendar |

Paired Kill: `disc.roll_*` — see Ch.3.  
See `EXP_REPORT.md` and Ch.9 for \(\sigma_w\) Promotes.

---

## 9. Worked numbers (ETH snapshot)

| Object | Value |
|--------|-------|
| noise_ratio RV_fine/RV_coarse | ≈0.902 |
| RV_fine (100ms) / RV_coarse (1s) | ≈8.92e-5 / 9.89e-5 |
| calendar 1s AC1 | ≈0.118 |
| volclock AC1 | ≈0.065 |
| Companion Ch.9 AR(10) \(\sigma_w\) | ≈4.59e-5 (Promote there) |

Content-pass figures: `out/ch08_noise/fig_noise_rv_curve.png`, `fig_clock_acf.png`.
