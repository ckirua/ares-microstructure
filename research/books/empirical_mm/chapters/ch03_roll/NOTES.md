# Ch.3 A dealer market with fixed transaction costs: the Roll model

**PDF:** pp. 20–22 · **Status:** `exp_run` → `iterate` (content pass)  
**Paired:** Ch.7–8 noise → [`../ch08_noise/`](../ch08_noise/)  
**Out:** [`../../out/ch03_roll/`](../../out/ch03_roll/)  
**Scripts:** [`../../scripts/exp_ch03_roll.py`](../../scripts/exp_ch03_roll.py) · `plot_ch03_roll.py` · notebook `ch03_roll.ipynb`  
**Lib:** `research/lib/discrete.py` (`roll_on_mid_bps`, `roll_c_from_returns`) · `research/lib/continuous.py` (`noise_robust_rv`)

---

## 1. What the chapter is about

Roll (1984) is the “basic black dress” of microstructure: a dealer posts bid/ask around an efficient mid with half-spread \(c\), and trades hit those quotes. The model maps cleanly into a **statistical** object — the autocovariance of price changes — so it teaches both economics and time-series hygiene.

Structure:

\[
m_t = m_{t-1} + u_t,\qquad
b_t = m_t - c,\quad a_t = m_t + c,\qquad
p_t = m_t + c\,q_t
\]

with \(q_t \in \{+1,-1\}\) the trade direction. Price changes:

\[
\Delta p_t = c(q_t - q_{t-1}) + u_t.
\]

Under buys/sells equally likely, \(q\) serial-independent, and \(q \perp u\):

\[
\gamma_0 = \mathrm{Var}(\Delta p) = 2c^2 + \sigma_u^2,\qquad
\gamma_1 = \mathrm{Cov}(\Delta p_t,\Delta p_{t-1}) = -c^2,\qquad
\gamma_k = 0\ (k\ge 2).
\]

Inference: \(c=\sqrt{-\gamma_1}\), \(\sigma_u^2=\gamma_0+2\gamma_1\). **Identification fails when \(\gamma_1\ge 0\)**.

Desk translation on crypto: if Roll does not identify on HL mid/trade px, do **not** invent a “implied spread” from \(\sqrt{|\gamma_1|}\) — Kill the candidate and move to quote-based tightness + AR/MA \(\sigma_w\) (Ch.9) and impact (Ch.13–14).

---

## 2. Theory map (book 3.a–b)

### 2.1 Assumptions that break in real tape

Hasbrouck’s CBL equity example already shows:

| Assumption | Reality |
|------------|---------|
| Constant \(2c\) | Spreads vary (ticks / regime) |
| \(q \perp u\) | Trades revise quotes (AS / inventory) |
| \(q\) i.i.d. | Buys follow buys (herding / splits) |

Yet Roll often still “works” as a coarse characterization when bounce dominates. Our falsifier is stricter: **Promote only if identified on train and held-out test**.

### 2.2 Why Roll is often low vs quoted

Book: Roll \(2c\) understates time-weighted quoted spread (sampling error; agents wait for tight spreads; price improvement inside quotes → effective < quoted). Crypto analogue: mid-join, maker rebates, and continuous mid updates erase bounce even more than equity floors.

### 2.3 Bridge to Ch.4 toolkit (no separate ch04 dir)

\(\Delta p\) under Roll is covariance-stationary MA(1). Ch.4 develops MA/AR representations, invertibility (\(|\theta|<1\)), and forecasting — used heavily in Ch.8–9 for \(\sigma_w\) without needing Roll \(c\). See Ch.9 NOTES for the folded MA/AR toolkit.

---

## 3. Our estimators (crypto)

| Candidate | Lens | Construction |
|-----------|------|--------------|
| `disc.roll_event_mid` | disc, liq, mm | Roll on as-of mid at trade events; train/test split |
| `disc.roll_trade_px` | disc, info | Same on trade prices (classic no-quote setting) |
| `cont.noise_rv_ratio` | cont, info | RV(100ms)/RV(1s) on collector mid |
| `cont.volclock_ac1` | cont, exec | AC1 of 1s calendar returns vs volume-clock returns |

**Promote logic**

- Roll: `identified` on train **and** test (\(\gamma_1<0\) and finite \(c\)).
- Noise ratio: Promote only if \(\gg 1\) (fine-RV inflation = bounce/noise). Hold if \(\approx 1\) or \(<1\).
- Volclock AC1: descriptive Hold unless clocks clearly diverge into a tradable feature.

---

## 4. Empirical design

| Choice | Value | Rationale |
|--------|-------|-----------|
| Venue / symbol | HL ETH | Same tape family as rest of book |
| Event clock | Trade-time as-of mid | Overlap trades with TOB |
| Train/test | 70/30 time split | Holdout identification |
| Fine / coarse | 100 ms / 1 s | Zhang-style intuition on collector mid |
| Vol bar | \(50\times\) median trade qty | Dense enough bars |

---

## 5. Results interpretation (see EXP_REPORT)

ETH window in `out/ch03_roll/`:

- \(n\approx 57\mathrm{k}\) trades · \(n\approx 78\mathrm{k}\) mids · days 2026-09-28→30.
- **All Roll variants unidentified:** event-mid \(\gamma_1\approx +3.5\times 10^{-4}\), trade-px \(\gamma_1\approx +9.4\times 10^{-5}\), calendar subsample also \(\gamma_1>0\); train/test both fail.
- Event AC1(\(\Delta\)mid) \(\approx 0.03\) (mild positive — opposite of bounce).
- **noise_ratio ≈ 0.90** (fine RV *below* coarse) → no bounce inflation on dense collector mid.
- Calendar AC1 ≈ 0.12 · volclock AC1 ≈ 0.06 — same order; Hold.

Desk reading:

| Function | Implication |
|----------|-------------|
| **MM cost floor** | Use **quoted** / effective spread (Ch.22), not Roll \(2c\) |
| **Research** | Positive \(\gamma_1\) flags herding / drift — hand off to sign ACF (Ch.10/13) and AR \(\sigma_w\) (Ch.9) |
| **Noise** | Do not treat HL mid as microstructure-noise-dominated for high-freq RV “correction” |

---

## 6. SECOND PASS — why Roll dies on HL tape

### 6.1 Mid is not a transaction price

Roll’s \(p_t=m_t+c q_t\) is a **trade** price. Applying Roll to **mid** changes mixes continuous quote updates with discrete trades. Positive \(\gamma_1\) on mid is expected when mid follows a near-RW with short-horizon momentum / inventory skew, not bid–ask bounce.

### 6.2 Trade prices also fail

Even on trade px, \(\gamma_1\ge 0\). Likely contributors on HL:

- Strong **sign autocorrelation** (\(\rho_1(q)\approx 0.53\) in Ch.13) violates i.i.d. \(q\) → Roll \(\gamma_1=-c^2\) derivation fails.
- Permanent impact (\(u\) correlated with \(q\)) adds positive serial covariance to \(\Delta p\).
- Tick size / mid-join reduces mechanical bounce relative to equity 2003 TAQ examples.

### 6.3 Links

- **Ch.8:** BN / MA recovers \(\sigma_w\) without Roll \(c\).
- **Ch.9:** Case study — MA(1) moments may still identify \(\theta,\sigma_w\) on **log returns** even when level-Roll Kill.
- **Ch.14 HS / MRR:** Structural AS/inventory when Roll is dead.
- **Ch.22:** Quoted spread is the tightness prior.

---

## 7. Code map

| Piece | Location |
|-------|----------|
| Roll moments | `research/lib/discrete.py` → `roll_on_mid_bps` |
| Noise RV | `research/lib/continuous.py` → `noise_robust_rv` |
| Batch | `scripts/exp_ch03_roll.py` |
| Figures | `scripts/plot_ch03_roll.py` · notebook |

---

## 8. Candidates (summary)

| id | lenses | decision | falsifier |
|----|--------|----------|-----------|
| `disc.roll_event_mid` | disc, liq, mm | **Kill** | \(\gamma_1\ge 0\) held-out |
| `disc.roll_trade_px` | disc, info | **Kill** | \(\gamma_1\ge 0\) |
| `cont.noise_rv_ratio` | cont, info | **Kill** | ratio \(\le 1\) always |
| `cont.volclock_ac1` | cont, exec | **Hold** | AC1 ≈ calendar |

See `EXP_REPORT.md` for live numbers and figures.

---

## 9. Worked numbers (ETH snapshot)

From `out/ch03_roll/exp_ch03_eth_summary.json` (content-pass refresh):

| Object | Value |
|--------|-------|
| \(n\) trades / mids | ≈57,255 / 78,489 |
| event-mid \(\gamma_0,\gamma_1\) | ≈0.0115, **+0.000353** (unidentified) |
| trade-px \(\gamma_1\) | **+9.4e-5** (unidentified) |
| train/test identified | 0 / 0 |
| noise_ratio | ≈0.902 |
| calendar AC1 / volclock AC1 | ≈0.118 / 0.065 |

These are the numbers cited in DESK_MEMO Kill/Hold rows for Roll and noise diagnostics.
