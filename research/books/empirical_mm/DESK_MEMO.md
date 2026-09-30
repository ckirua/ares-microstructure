# Desk memo — Empirical Market Microstructure (Hasbrouck notes)

**Audience:** crypto MM / SOR / execution / taker / stat-arb / research  
**Source:** Joel Hasbrouck teaching notes Draft 1.1 (2004) → `research/books/empirical_mm/`  
**Philosophy:** **not MM-only** — lenses `mm | disc | cont | exec | info | liq`.  
**Data:** collector TOB + warehouse trades + cached HL `l2_snapshot_level` — **no ClickHouse MCP**.  
**Program status (2026-09-30): Holds pass COMPLETE** on public-tape OE/Sandas/noise residuals.  
**SoT:** [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) rollup · Coverage: [`docs/COVERAGE.md`](docs/COVERAGE.md) · Front door: [`chapters/ch00_overview/`](chapters/ch00_overview/) · Board: [`notebooks/desk_synthesis.ipynb`](notebooks/desk_synthesis.ipynb).

---

## 1. Desk jobs × Promotes

| Job | Promotes | Avoid |
|-----|----------|-------|
| **Quoting / MM** | spread, OFI, VPIN, markout, touch/size-touch/cancel-proxy/refill/resilience, Sandas L1 depths, HS lump π | Roll; improve-markout; noise-RV |
| **Toxicity / info** | markout, VPIN, **EHO PIN**, sign ACF, AR σ_w, GH/MRR/HS π | PIN day-imb proxy |
| **Execution / POV** | MRR θ, quote-aligned λ/IRF, intensity, Amihud, time_to_touch, size_touch_survival | True OE fill hazard (Hold) |
| **SOR / x-venue** | info shares, Epps, jump concordance | Treating IS as arb |
| **Stat-arb / research** | Amihud, AR/MA σ_w, Epps/IS, qty moment ceiling | Noise-RV as alpha (**Kill**) |

---

## 2. Final Promote / Hold / Kill

### Promote (all lenses)

`liq.quoted_spread_bps`, `mm.book_resilience_lo`, `cont.same_side_refill`, `cont.time_to_touch`, `cont.size_touch_survival`, `cont.tob_cancel_proxy`, `cont.lob_event_intensity`, `disc.lob_event_ac1`, `disc.parlour_depth_side`, `disc.sandas_depth_moments`, `disc.qty_moment_ceiling`, `disc.sign_acf`, `cont.ofi_mid_corr`, `info.markout_1s`, `disc.var_lambda`, `disc.irf_permanent`, `disc.mrr_theta`, `disc.gh_z0`, `disc.hs_pi`, `disc.ma1_moments`, `disc.ar_sigma_w`, `disc.pin_eho_mle`, `cont.vpin`, `cont.trade_intensity`, `cont.info_share_hl_lit`, `cont.epps_xvenue`, `disc.jump_sign_concord`, `liq.amihud_1m`

### Hold (blockers noted)

| ID | Why Hold |
|----|----------|
| `disc.pin_proxy_dayimb` | Day-imbalance proxy only |
| `disc.hs_as_inv_split` | Two-way λ̂≈0.39 OK; three-way **â≈−0.18** |
| `disc.mrr_rho_q` | Not standalone tradable (ρ(q)≃0.60 herding) |
| `cont.volclock_ac1` | Diagnostic / weak |
| `mm.limit_fill_hazard_oe` | No OE fill tape — use public size-touch / cancel proxies |
| `theory.sandas_gmm_multilevel` | L1 moments shipped; structural GMM still blocked |
| Part III theory.\* | Stoll CARA, CMSW, Foucault/Parlour eq, Seppi, queue value |

### Kill

`disc.roll_event_mid`, `disc.roll_trade_px`, `disc.roll_vs_quote`, `info.improve_markout`, **`cont.noise_rv_ratio`** (boot CI≈[0.87,0.91] — no fine-RV inflation)

---

## 3. ETH numeric snapshot (desk board)

Aligned with `out/ch16_asymmetry` board + sibling summaries (HL ETH overlap windows):

| Metric | Level | Status | Package |
|--------|------:|--------|---------|
| Quote-aligned λ (OLS) | ≈0.199 | Promote | ch13 |
| Permanent IRF | ≈0.422 | Promote | ch13 |
| Markout 1s (bps) | ≈0.472 | Promote | ch13 |
| OFI↔mid corr | ≈0.43 | Promote | ch13 |
| Sign ρ₁ | ≈0.535 | Promote | ch10/13 |
| MRR θ | ≈0.048 | Promote | ch14 |
| GH z₀ | ≈0.189 | Promote | ch14 |
| HS lump π / two-way λ̂ | ≈0.010 / ≈0.39 | Promote | ch14 |
| HS â (AS three-way) | ≈−0.18 | **Hold** | ch14 |
| PIN MLE (28 days) | ≈0.183 | **Promote** | ch15 |
| VPIN mean | ≈0.914 | Promote | ch15 |
| Trade intensity λ̂ (1s) | ≈1.21 | Promote | ch15/10 |
| Quoted spread (bps) | ≈0.382 | Promote | ch22 |
| Amihud ILLIQ (1m) | ≈4.7e-9 | Promote | ch22 |
| AR(10) σ_w | ≈5.1e-5 | Promote | ch09 |
| Noise RV ratio | ≈0.87 | **Kill** | ch03/09 |
| Qty trunc-var × (0.995/0.9) | ≈15.4 | Promote | ch18/10 |
| IS HL bounds | ≈[0.34, 0.97] | Promote | ch17 |
| Epps corr @60s | ≈0.94 | Promote | ch17 |
| Jump sign concord (p90) | ≈0.56 | Promote | ch17 |

Figure board: [`notebooks/desk_synthesis.ipynb`](notebooks/desk_synthesis.ipynb).

---

## 4. Confirmed sibling landings

| Stream | Status |
|--------|--------|
| Quote-aligned λ / IRF / GH / MRR (ch13–14) | **Promote** |
| Huang–Stoll lump π + deep decomp (ch14) | **Promote** π; **Hold** α\|β |
| PIN deep + VPIN (ch15) | **Promote** PIN (28d, PIN̂≈0.183); **Promote** VPIN / intensity |
| Part III LOB (ch18–21) | **Promote** ×10 (+ size-touch, cancel, Sandas L1, qty ceiling); Kill improve-markout |
| Noise RV (ch3/8/9) | **Kill** after block bootstrap |
| Theory dig + Ch.9 estimation | **Complete** |
| Front door + coverage audit (ch00 / docs) | **Complete** (this wave) |

Artifacts: `research/lib/{discrete,continuous,lob,pin}.py` · `scripts/exp_ch18_limit_orders.py` · `scripts/exp_ch09_estimation.py`

---

## 5. Falsifiers (desk)

| Claim | Falsifier |
|-------|-----------|
| Markout | 1s CI ≤0 held-out |
| VPIN | flat / n_buckets<20 |
| Quote-aligned λ / IRF | ≤0 or train/test flip |
| MRR θ / HS π | ≤0 or R² collapse |
| PIN MLE | usable days <20 or free/sym unstable → Hold (cleared: 28 usable) |
| HS α\|β | â≤0 or inventory share absurd |
| Touch / size-touch / refill | non-monotone / ≈0 |
| Cancel proxy | cancel≈0 or fill≈0 |
| Sandas L1 | no multilevel / behind-touch≈0 |
| Noise RV | ratio≤1 / boot CI hi≤1.2 → Kill |
| Roll | γ₁≥0 → Kill |

---

## 6. Public-tape ceiling (not open work)

| Need | Status |
|------|--------|
| Multilevel L2 for L1 moments | **Available** — shipped `disc.sandas_depth_moments` |
| OE fill/cancel historical tape | **Absent** — dry_gateway/SHM only |
| Structural Sandas GMM | **Blocked** — needs break-even ID, not just E[Q_k] |
| Full-day B/S (≥20) / dealer inventory | **B/S days cleared** (opaque flat-id); dealer inventory still **Absent** — HS α\|β Hold |

Re-open OE/GMM/HS-split only with those feeds. PIN usable-day ceiling cleared 2026-09-30. Until then remaining identifiable public-tape empirics are **complete**.

---

## 7. Pointers

| | Path |
|--|------|
| Index | `CHAPTER_INDEX.md` |
| Coverage table | `docs/COVERAGE.md` |
| Front door | `chapters/ch00_overview/` |
| Desk synthesis | `notebooks/desk_synthesis.ipynb` |
| Lib | `research/lib/{discrete,continuous,lob,pin}.py` |
| Ch.9 / Ch.15 / Ch.18 | `chapters/ch09_estimation/`, `ch15_pin/`, `ch18_limit_orders/` |
| mmip | `../mmip/` |
