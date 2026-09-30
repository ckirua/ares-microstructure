# Ch.16 What do measures of information asymmetry tell us?

**PDF:** p. 124 · **Status:** `notes` → `iterate` (synthesis pass)  
**Raw:** [`../../_raw/ch16_asym.txt`](../../_raw/ch16_asym.txt)  
**Out:** [`../../out/ch16_asymmetry/`](../../out/ch16_asymmetry/)  
**Scripts:** `plot_ch16_asymmetry.py` · notebook `ch16_asymmetry.ipynb`  
**Upstream:** Ch.13 VAR/impact · Ch.14 GH/MRR/HS · Ch.15 PIN/VPIN · desk [`../../DESK_MEMO.md`](../../DESK_MEMO.md)

---

## 1. Book message (one page, heavy implications)

Spreads, trade autocorrelations, and price-impact coefficients are routinely used as **microstructure proxies for information asymmetry** in corporate finance / accounting. Hasbrouck’s cautionary notes:

| Caution (book) | Implication |
|----------------|-------------|
| Closed-end fund spreads too wide vs transparent NAV (Neal–Wheatley) | Spread ≠ pure adverse selection |
| Predictable index-rebalance spread changes (Saar–Yu) | Spread variation ≠ cash-flow uncertainty |
| FX / Treasury order flow has impact (Lyons) | Private info can be about **transient** components, not only long-run value |

Equity models often equate “informed” with predicting **permanent** value. Lyons: an agent who buys low / sells high on temporary dislocations still has valuable private information. Crypto MM inherits both channels — toxic flow *and* short-horizon predictive edge on microstructure states.

---

## 2. Synthesis across Ch.13–15 measures (desk map)

This chapter does **not** introduce a new estimator. It ranks what we already Promote/Hold and when they **disagree**.

| Family | Candidates (this program) | What it actually measures | Status |
|--------|---------------------------|---------------------------|--------|
| **Impact / permanent mid** | `disc.var_lambda`, `disc.irf_permanent`, `disc.mrr_theta`, `disc.gh_z0` | Signed-flow → mid move (quote-aligned) | **Promote** |
| **Spread decomposition** | `disc.hs_pi` (lump); `disc.hs_as_inv_split` | Permanent vs transient in spread | **Promote** π; **Hold** α\|β |
| **Sign / herding** | `disc.sign_acf`, `disc.mrr_rho_q` | Serial dependence in \(q\) | Promote ρ₁; Hold ρ alone |
| **Toxicity clocks** | `cont.vpin`, `cont.trade_intensity`, `info.markout_1s` | Flow imbalance / intensity / maker AS | **Promote** |
| **PIN family** | `disc.pin_eho_mle`, `disc.pin_proxy_dayimb` | Daily B/S structural toxicity | **Promote** EHO (28d); proxy **Hold** |
| **Tightness / ILLIQ** | `liq.quoted_spread_bps`, `liq.amihud_1m` | Cost / impact-per-dollar state | **Promote** (Ch.22) |
| **Efficient innov.** | `disc.ar_sigma_w`, `disc.ma1_moments` | Permanent vol scale (Ch.9) | **Promote** |

**Desk memo links:** DESK_MEMO §1 (jobs×Promotes), §2 (final P/H/K), §4 (falsifiers), §5 (public-tape ceiling).

---

## 3. Comparative levels (ETH snapshots — see EXP_REPORT / notebook)

Pulling existing `out/` (do not re-fit structures here):

| Metric | Approx level | Source |
|--------|--------------|--------|
| Quote-aligned λ (OLS) | ≈0.20 | ch13 |
| Permanent IRF | ≈0.42 | ch13 |
| Markout 1s (bps) | ≈0.47 | ch13 |
| Sign ρ₁ | ≈0.53 | ch13 |
| MRR θ | ≈0.034 | ch14 |
| HS lump π | ≈0.011 (basic) / two-way λ̂≈0.31 | ch14 |
| PIN MLE | ≈0.183 (28 usable days) | ch15 **Promote** |
| VPIN mean | ≈0.90 | ch15 **Promote** |
| Quoted spread (bps) | ≈0.38 | ch22 |
| AR(10) σ_w | ≈4.6e-5 | ch09 |

Figures in `out/ch16_asymmetry/` compare these on a common board and flag disagreements.

---

## 4. SECOND PASS — when PIN vs impact vs HS disagree

### 4.1 High VPIN / markout, middling PIN

**Observed pattern:** VPIN ≈0.91 and markout 1s >0 with PIN MLE **Promote** (28 usable days after flat-id expansion).  
**Reading:** Volume-clock toxicity and short-horizon maker AS can fire without a stable Easley–HHO daily PIN. Do **not** wait for PIN to size toxic-flow defenses — prefer VPIN + markout + OFI.

### 4.2 Impact Promote, HS three-way Hold

**Observed:** λ / IRF / MRR θ Promote; HS α\|β split gives \(\hat a<0\).  
**Reading:** Permanent impact exists; **labeling** it “adverse selection vs inventory” on public tape without dealer inventory is not identified. Use lump π / two-way λ̂ for risk; do not deploy three-way shares.

### 4.3 Tight spread, high VPIN

**Observed:** Quoted ≈0.38 bps with VPIN ≈0.9.  
**Reading:** Tightness ≠ safe. Neal–Wheatley caution in reverse: a narrow crypto spread can coexist with toxic flow (rebate / maker competition). Pair Ch.22 spread with Ch.15 VPIN.

### 4.4 Roll Kill + positive sign ACF + impact

**Observed:** γ₁≥0 (Ch.3), ρ₁(q)≈0.53, λ>0.  
**Reading:** Classic “spread = AS” Roll story is false; herding + permanent impact is the asymmetry channel. Lyons transient-info point applies to inventory/skew traders as well as fundamental informed.

### 4.5 Decision rule (desk)

| If you need… | Prefer | Avoid as sole signal |
|--------------|--------|----------------------|
| Quoting toxicity | markout, VPIN, OFI | PIN MLE, Roll |
| TCA permanent cost | MRR θ, IRF, λ | HS α share |
| Cross-sectional “AS proxy” paper | report disagreement set | single PIN number |
| Regime flag | VPIN + ILLIQ + σ_w | noise_rv_ratio |

---

## 5. Code map

| Piece | Location |
|-------|----------|
| Upstream summaries | `out/ch13_var_impact/`, `ch14_structural/`, `ch15_pin/`, `ch09_estimation/`, `ch22_liquidity/` |
| Comparative figs | `scripts/plot_ch16_asymmetry.py` |
| Notebook | `ch16_asymmetry.ipynb` |

---

## 6. Candidates

No new IDs. Synthesis status: **iterate** on interpretation; empirics remain those of Ch.13–15/9/22.
