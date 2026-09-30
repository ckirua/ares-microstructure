# Ch.9 Estimation of time series models

**PDF:** pp. 72–79 · **Status:** `exp_run` → `iterate` (content pass)  
**Raw:** [`../../_raw/ch09_est.txt`](../../_raw/ch09_est.txt) · Ch.4 toolkit folded from [`../../_raw/ch03_roll.txt`](../../_raw/ch03_roll.txt) (pp. 23–…)  
**Out:** [`../../out/ch09_estimation/`](../../out/ch09_estimation/)  
**Scripts:** [`../../scripts/exp_ch09_estimation.py`](../../scripts/exp_ch09_estimation.py) · `plot_ch09_estimation.py` · notebook `ch09_estimation.ipynb`  
**Lib:** `research/lib/discrete.py` (`ma1_from_acov`, `ar_ols`, `rw_variance_from_ar`, `impact_multipliers_from_ar`)

---

## 1. What the chapter is about

Given a statistical MA for \(\{\Delta p_t\}\), map estimates into structural objects (\(\sigma_w^2\), pricing-error scale, and — under restrictions — Roll \(c\) or AS \(\lambda\)). Book Case Study I does this on one NYSE symbol×day from TAQ. Our remake: **HL ETH trades + collector TOB**, multi-day blocks, same moment/AR hygiene.

Doctrine (book 9.a–c): prefer **moments + truncated AR** over exact Gaussian ML on tick data; prefer **subsampling / day blocks** over delta-method SEs for nonlinear maps (RW decomp, IRFs).

---

## 2. Folded Ch.4 MA/AR toolkit (no separate ch04 dir)

### 2.1 Stationarity / ergodicity

Price **levels** are not covariance-stationary (\(\mathrm{Var}(p_t)\) grows). **Changes** \(\Delta p\) under Roll are. Crypto 24/7 still has intraday seasonality in volume/vol — day-block estimation respects that better than one pooled likelihood.

### 2.2 MA(1) and Wold

\[
x_t = e_t + \theta e_{t-1},\qquad
\gamma_0=(1+\theta^2)\sigma_e^2,\quad
\gamma_1=\theta\sigma_e^2,\quad
\gamma_k=0\ (k>1).
\]

Wold: any zero-mean covariance-stationary series has an MA(\(\infty\)) (+ deterministic). Ansley–Spivey–Wrobleski: if \(\gamma_k=0\) for \(k>K\), an MA(\(K\)) exists — justifies MA(1) for classic Roll even though structural randomness has two shocks (\(u,q\)).

### 2.3 AR approximation and invertibility

MA(1) \(\Leftrightarrow\) infinite AR with geometrically declining coefficients when \(|\theta|<1\) (invertible root). Truncate at \(K\):

\[
x_t = \varphi_1 x_{t-1}+\cdots+\varphi_K x_{t-K}+e_t^a
\]

estimate by OLS. Invert \(\varphi(L)\) by series expansion **or** recursive forecasts (= impact multipliers / IRF). For BN variance only need

\[
\sigma_w^2 = \frac{\sigma_e^2}{\varphi(1)^2}.
\]

### 2.4 Why this belongs in Ch.9 NOTES

Ch.4 is pure toolkit; Ch.9 is where we **estimate**. Folding avoids a hollow `ch04/` package while keeping the MA↔AR / \(\varphi(1)\) story next to the crypto case study.

---

## 3. Book estimation doctrine (dense)

| Topic | Claim | Our practice |
|-------|-------|--------------|
| Why not exact Gaussian ML | Tick grid coarse; \(\Delta p\) mostly 0/1/2 ticks; \(N\) large | Moments + OLS AR; bootstrap / day-blocks |
| Direct MA via GMM | Match \(\gamma_0,\gamma_1\) for MA(1); higher-\(q\) / VAR hard | `ma1_from_acov` |
| AR approximation | Truncate AR(\(\infty\)) at \(K\); White/NW if \(K\) misspecified | `ar_ols` + `rw_variance_from_ar` |
| Invert AR → MA | Series expansion **or** recursive forecasts = IRF | `impact_multipliers_from_ar`; also Ch.13 |
| \(\sigma_w\) from AR | Need only \(\varphi(1)\) | report \(\sigma_w\) + lag sweep |
| Delta method | Poor when maps highly nonlinear | Prefer **subsampling** |
| Fama–MacBeth / days | Estimate per day; mean ± SE of day estimates | calendar-day blocks |
| Starting values | Do **not** glue overnight \(\Delta p\); treat days separate | drop gaps \(>1\)h; crypto day blocks |

---

## 4. Case Study I → crypto walkthrough

1. Build event-time \(\Delta\log\) mid and trade px; calendar 1s \(\Delta\log\) mid.
2. Roll \(c\) from \(\gamma_1\) on **levels** (expect **Kill** — consistent with Ch.3).
3. MA(1) moments on **returns** → \(\theta,\sigma_w,\sigma_s\) when identified.
4. AR(\(K=3\)) and AR(\(K=10\)) → \(\sigma_w\) via \(\varphi(1)\); IRF multipliers.
5. Compare \(\sigma_w\) / Roll / mean quoted spread (bps).
6. Time-split + day-block SEs; AR lag sweep.
7. **Second pass:** variance ratios VR(\(q\)) on event and calendar clocks; noise RV companion.

---

## 5. Our estimators

| Candidate | Lens | Construction |
|-----------|------|--------------|
| `disc.ma1_moments` | disc, info | MA(1) from \(\gamma_0,\gamma_1\) of \(\Delta\log\) mid/px |
| `disc.ar_sigma_w` | disc, info, mm | AR(10) BN \(\sigma_w\); train/test + day-block SE |
| `disc.roll_vs_quote` | disc, liq | Roll level ID vs quoted spread — **Kill** |
| `cont.noise_rv_ratio` | cont, mm | Fine/coarse RV (Ch.8 companion) — **Hold** |

**Promote** MA/AR when identified / finite \(\sigma_w\) and train/test both positive.

---

## 6. Results interpretation (see EXP_REPORT)

ETH window (refresh via `plot_ch09_estimation.py`):

- Roll mid/px **unidentified** (\(\gamma_1>0\)) — Kill vs quote.
- MA(1) mid **identified** with small **positive** \(\theta\approx 0.031\), \(\sigma_w\approx 4.1\times 10^{-5}\) (momentum-like transient, not bounce).
- AR(10) \(\sigma_w\approx 4.6\times 10^{-5}\); train/test both finite; day-block mean±SE available.
- Quoted spread ≈ **0.38 bps**; noise ratio ≈ **0.90**.
- VR(\(q\)) departs from 1 on both clocks — RW variance does **not** scale linearly in horizon.
- Lag sweep: \(\sigma_w\) moves with \(K\) — publish sensitivity.

Desk reading:

| Function | Implication |
|----------|-------------|
| **Vol prior** | Use AR/BN \(\sigma_w\) (and day-block SE), not Roll \(2c\) |
| **TCA / risk** | VR≠1 ⇒ do not √T-scale event variance blindly |
| **Research** | Positive MA \(\theta\) + Roll Kill = herding/impact world (Ch.13–14) |

---

## 7. SECOND PASS — BN / variance ratio / pitfalls on HL tape

### 7.1 Beveridge–Nelson on crypto mid

BN \(\sigma_w\) answers: “what is the scale of the permanent innovation in the observed price?” It does **not** require Roll’s \(q\perp u\). On HL, mid is continuous enough that \(\sigma_w\) from event \(\Delta\log\) mid is a usable permanent-vol state for MM inventory / POV risk.

### 7.2 Variance ratios

\[
\mathrm{VR}(q)=\frac{\mathrm{Var}(r_t+\cdots+r_{t+q-1})}{q\,\mathrm{Var}(r_t)}.
\]

Under pure RW, VR\(=1\). Microstructure MA structure, sign herding, and diurnal vol push VR away from 1. Empirically we plot VR on **event** and **1s calendar** clocks — both reject naive RW scaling in this window.

### 7.3 Estimation pitfalls (desk checklist)

| Pitfall | Symptom on HL | Mitigation |
|---------|---------------|------------|
| Glue large gaps | Overnight-like jumps as one \(\Delta p\) | Drop gaps \(>1\)h |
| Single \(K\) | \(\sigma_w\) shifts across lag sweep | Report sweep + prefer day-block SE |
| Delta-method SE | Overconfident on IRF / RW maps | Subsample by day |
| Equating Roll & MA | Levels Kill but returns MA IDs | Keep both; don’t force \(c=\sqrt{-\gamma_1}\) |
| Equating BN \(\sigma_s\) & RV noise | Different objects | Ch.8 NOTES §6 |
| Pooled ML on ticks | Discrete support / non-Gaussian | Moments + OLS |

### 7.4 Links

- **Ch.3/8:** motivation — Roll dead, MA-first alive.
- **Ch.13:** multivariate IRF / \(\lambda\) — same AR→MA inversion idea in VAR form.
- **Ch.16:** \(\sigma_w\) / impact / PIN disagreement when labeling “asymmetry.”

---

## 8. Code map

| Piece | Location |
|-------|----------|
| MA(1) moments | `discrete.ma1_from_acov` |
| AR + BN | `ar_ols`, `rw_variance_from_ar` |
| IRF | `impact_multipliers_from_ar` |
| Batch | `exp_ch09_estimation.py` |
| Figures + VR | `plot_ch09_estimation.py` |

---

## 9. Candidates (summary)

| id | lenses | decision | falsifier |
|----|--------|----------|-----------|
| `disc.ma1_moments` | disc, info | **Promote** | unidentified / \(\sigma_w\le 0\) |
| `disc.ar_sigma_w` | disc, info, mm | **Promote** | \(\sigma_w\) fails train or test |
| `disc.roll_vs_quote` | disc, liq | **Kill** | \(\gamma_1\ge 0\) |
| `cont.noise_rv_ratio` | cont, mm | **Hold** | no fine inflation |

See `EXP_REPORT.md` for live numbers and figures.
