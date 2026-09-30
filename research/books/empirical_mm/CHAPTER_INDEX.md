# Empirical Market Microstructure — research index

Living map of Hasbrouck teaching-notes chapters → candidates → experiment status.
Book PDF + `_raw/` extracts: **local only** (gitignored). Sibling: [`../mmip/`](../mmip/).
Data: [`../../DATA_PATHS.md`](../../DATA_PATHS.md). Loop: [`../../LOOP.md`](../../LOOP.md). Desk: [`DESK_MEMO.md`](DESK_MEMO.md).

**Book:** Joel Hasbrouck, *Empirical Market Microstructure* notes Draft 1.1 (2004-01-08), 203 PDF pp. Slug: `empirical_mm`.

**Program status (2026-09-30): Holds pass COMPLETE** for public-tape OE/Sandas/noise residuals. Residual theory Holds need OE fills / prefs / structural GMM — not unfinished scripts.

**Content / plot pass:** Deep NOTES+nb+figs across empirics packages. **Final wave:** `ch00_overview` front door + roadmap board; `notebooks/desk_synthesis.ipynb` multi-lens figure board; coverage audit [`docs/COVERAGE.md`](docs/COVERAGE.md).

**Shared lib:** [`../../lib/discrete.py`](../../lib/discrete.py) · [`../../lib/continuous.py`](../../lib/continuous.py) · [`../../lib/lob.py`](../../lib/lob.py) · [`../../lib/pin.py`](../../lib/pin.py) · loaders [`scripts/_data.py`](scripts/_data.py).

**Status legend:** `todo` · `notes` · `candidates` · `exp_run` · `iterate` · `park`  
**Lenses:** `mm` · `disc` · `cont` · `exec` · `info` · `liq`

**Coverage SoT:** [`docs/COVERAGE.md`](docs/COVERAGE.md) (package → NOTES lines / n_figs / notebook / thin flags).

---

## Promote rollup by lens (final)

| Candidate | mm | disc | cont | exec | info | liq | Ch | One-line use |
|-----------|:--:|:----:|:----:|:----:|:----:|:---:|----|--------------|
| `liq.quoted_spread_bps` | ✓ | | | ✓ | | ✓ | 22 | Cost floor |
| `mm.book_resilience_lo` | ✓ | | ✓ | | | ✓ | 18 | L0 depth refill after trade |
| `cont.same_side_refill` | ✓ | | ✓ | | | ✓ | 18 | Same-side size recovery |
| `cont.time_to_touch` | ✓ | | ✓ | ✓ | | | 18 | Geometric touch / fill-proxy |
| `cont.size_touch_survival` | ✓ | | ✓ | ✓ | | | 18 | Size-stratified public fill hazard |
| `cont.tob_cancel_proxy` | ✓ | | ✓ | ✓ | | | 18 | TOB depletion cancel vs fill |
| `cont.lob_event_intensity` | ✓ | | ✓ | ✓ | | | 18 | LOB-event λ̂ |
| `disc.lob_event_ac1` | ✓ | ✓ | | | | | 18 | LOB-event clustering |
| `disc.parlour_depth_side` | ✓ | ✓ | | ✓ | | | 18 | Depth ↔ aggressor |
| `disc.sandas_depth_moments` | ✓ | ✓ | | | ✓ | ✓ | 18 | L1 depth schedule E[Q_k]/E[Q_0] |
| `disc.qty_moment_ceiling` | | ✓ | | ✓ | | ✓ | 0/18 | Volume trunc-var inflation |
| `disc.sign_acf` | ✓ | ✓ | | | ✓ | | 10/13 | Sign herding / inventory regime |
| `cont.ofi_mid_corr` | ✓ | | ✓ | | ✓ | | 13 | OFI ↔ mid return |
| `info.markout_1s` | ✓ | | | ✓ | ✓ | | 13 | Maker AS / taker edge decay |
| `disc.var_lambda` | | ✓ | | ✓ | ✓ | | 13 | Quote-aligned impact λ |
| `disc.irf_permanent` | | ✓ | | ✓ | ✓ | | 13 | Permanent mid IRF |
| `disc.mrr_theta` | | ✓ | | | ✓ | ✓ | 14 | Permanent impact prior |
| `disc.gh_z0` | | ✓ | | ✓ | ✓ | | 14 | GH AS intercept |
| `disc.hs_pi` | ✓ | ✓ | | | ✓ | ✓ | 14 | HS **lump** π (α+β) |
| `disc.ma1_moments` | | ✓ | | | ✓ | | 9 | MA(1) σ_w when Roll fails |
| `disc.ar_sigma_w` | ✓ | ✓ | | | ✓ | | 9 | BN σ_w via AR truncation |
| `cont.vpin` | ✓ | | ✓ | ✓ | ✓ | | 15 | Vol-clock toxicity (~0.914) |
| `cont.trade_intensity` | | | ✓ | ✓ | ✓ | | 10/15 | Point-process λ̂ |
| `disc.pin_eho_mle` | | ✓ | | | ✓ | | 15 | EHO day-mixture PIN̂≈0.183 (28 usable) |
| `cont.info_share_hl_lit` | | | ✓ | ✓ | ✓ | | 17 | HL vs Lit discovery weights |
| `cont.epps_xvenue` | | | ✓ | ✓ | ✓ | | 17 | Sync horizon |
| `disc.jump_sign_concord` | | ✓ | | | ✓ | | 17 | Large-move concordance |
| `liq.amihud_1m` | | | | ✓ | ✓ | ✓ | 22 | Illiquidity bar |

**Kill:** `disc.roll_event_mid`, `disc.roll_trade_px`, `disc.roll_vs_quote`, `info.improve_markout`, **`cont.noise_rv_ratio`**.

**Hold (blockers — not unfinished siblings):**

| Candidate | Blocker |
|-----------|---------|
| `disc.pin_proxy_dayimb` | Proxy only; not certified vs markout/VPIN |
| `disc.hs_as_inv_split` | Three-way **â(AS)<0** — no dealer inventory analogue |
| `disc.mrr_rho_q` | ρ(q) always high / not tradable alone |
| `cont.volclock_ac1` | Weak / unstable |
| `mm.limit_fill_hazard_oe` | No historical OE fill/cancel (dry_gateway/SHM only) — public proxies Promote instead |
| `theory.sandas_gmm_multilevel` | L1 moments Promote; structural break-even GMM still blocked |
| Part III theory.\* | Stoll CARA, CMSW EU, Foucault/Parlour eq, Seppi, queue-position — prefs / OE |

---

## Sibling deep results (integrated)

### Ch.0–2 front door — **FINISHED (final content wave)**
- Artifacts: [`chapters/ch00_overview/`](chapters/ch00_overview/) · [`scripts/plot_ch00_overview.py`](scripts/plot_ch00_overview.py) · `out/ch00_overview/fig_roadmap_status.png`
- NOTES = book front door (Hasbrouck themes, Ch.1–22 map, reading order, P/K/H → CHAPTER_INDEX)
- Coverage audit: [`docs/COVERAGE.md`](docs/COVERAGE.md) · Desk board: [`notebooks/desk_synthesis.ipynb`](notebooks/desk_synthesis.ipynb)

### Ch.10 trade / inventory — **FINISHED (content + plot pass)**
- Artifacts: [`scripts/plot_ch10_trades.py`](scripts/plot_ch10_trades.py) · [`chapters/ch10_trades/`](chapters/ch10_trades/) · `out/ch10_trades/`
- Reuses Ch.13 `disc.sign_acf` (ρ₁≈0.535) + Ch.15 intensity/VPIN; light tape for size + vol-clock sign ACF + cum-flow \(I^{\mathrm{proxy}}\)
- **Promote** sign ACF, trade intensity, VPIN, qty moment ceiling
- **Hold** `mm.inventory_quote_skew` / true dealer \(I_t\) (links Ch.14 `hs_as_inv_split`)
- SECOND PASS: permanent IRF/markout = info channel; intensity+VPIN = toxicity overlay on same herding fingerprint
- Figures: `fig_sign_acf`, `fig_intensity_volclock`, `fig_trade_size`, `fig_cumflow_inv`

### Ch.18–21 Part III — **FINISHED (empirics + NOTES/plot pass)**
- Lib: `size_at_touch_survival`, `tob_depletion_cancel_proxy`, `sandas_depth_moments`, `qty_moment_ceiling`, …
- Script: [`scripts/exp_ch18_limit_orders.py`](scripts/exp_ch18_limit_orders.py) · [`scripts/plot_ch18_limit_orders.py`](scripts/plot_ch18_limit_orders.py)
- **Promote** touch, size-touch, cancel proxy, refill, resilience, Parlour, LO clocks, Sandas L1, qty ceiling
- **Kill** `info.improve_markout`
- **Hold** OE fill hazard, queue value, structural Sandas GMM, Stoll/CMSW EU, Foucault–Parlour eq, Seppi
- SECOND PASS: TOB delivers spread/touch/cancel/refill proxies; L2 ships L1 moments; OE/queue/prefs still Hold
- Figures: `fig_time_to_touch`, `fig_size_touch_survival`, `fig_cancel_vs_fill`, `fig_sandas_depth`, `fig_resilience_refill`, `fig_parlour_lob_clocks`

### Ch.15 PIN deep — **FINISHED** (coverage expansion 2026-09-30 → **Promote**)
- Sample: HL ETH **2026-08-28→30**, opaque flat-id + UTC clip; **34 tape / 28 usable** ≥4h
- **Promote** `disc.pin_eho_mle` (PIN̂≈0.183, sym-ε≈0.153); **Promote** VPIN / intensity
- **Hold** `disc.pin_proxy_dayimb` only
- Thin public-md days (09-12/13/23/24/28/29) remain warehouse coverage gaps (not loader)
- Figures: B/S scatter, PIN day panel, PIN vs VPIN, VPIN path, VPIN↔markout, intensity
- NOTES + notebook: [`chapters/ch15_pin/`](chapters/ch15_pin/) · `scripts/exp_ch15_pin_deep.py`

### Ch.5–6 theory densify — **FINISHED (this wave)**
- NOTES expanded from `_raw` (~130+ lines each) to study-guide depth
- Lightweight synthetic notebooks + `out/ch05_seq_info/`, `out/ch06_strategic/` schematic PNGs (labeled SYNTHETIC)
- Empirics remain owned by ch13/14/15 (+ mmip POV for Kyle split)

### Ch.14 Huang–Stoll — **FINISHED**
- **Promote** lump π; **Hold** α\|β split

### Ch.11–12 toolkit
- Short fold-in into `ch13_var_impact/NOTES.md` §7 (unit roots / invertibility / VAR→VMA IRF)

---

## Roadmap (all 22 chapters)

| ID | Title | Status | Package |
|----|-------|--------|---------|
| Ch.0–2 | Overview / martingale | `notes` | `ch00_overview/` front door + roadmap fig (+ qty moment dig) |
| Ch.3 / 7–8 | Roll + RW noise | `exp_run` | `ch03_roll/` + `ch08_noise/` — noise **Kill** |
| Ch.4 | MA/AR toolkit | notes → ch09 | — |
| Ch.5–6 | GM / Kyle theory | `notes` | `ch05_seq_info/`, `ch06_strategic/` — densified NOTES + **synthetic** nbs |
| Ch.9 | Estimation case | `exp_run` | `ch09_estimation/` |
| Ch.10 | Trade / inventory | `iterate` | `ch10_trades/` (NOTES+nb+figs; ↔13/15) |
| Ch.11–12 | VAR toolkit | notes → ch13 | folded into `ch13_var_impact/NOTES.md` §7 |
| Ch.13 | VAR / IRF / OFI | `exp_run` | `ch13_var_impact/` |
| Ch.14 | GH / MRR / HS | `exp_run` | `ch14_structural/` |
| Ch.15 | PIN / VPIN | `exp_run` | `ch15_pin/` — densify pass (day panel + VPIN↔markout) |
| Ch.16 | Asymmetry synthesis | `notes` | `ch16_asymmetry/` |
| Ch.17 | Discovery | `iterate` | `ch17_discovery/` |
| Ch.18–21 | Limit orders | `iterate` | `ch18_limit_orders/` (NOTES+nb+figs) |
| Ch.22 | Liquidity / Amihud | `iterate` | `ch22_liquidity/` |
| App. | US equity → crypto | `park` | `appendix_us/` — **intentional park** (transfer table only; no US-equity exp stream) |

---

## Remaining Holds (true data ceilings)

1. **`disc.pin_proxy_dayimb`** — descriptive proxy only (EHO MLE now Promote).
2. **`disc.hs_as_inv_split`** — dealer inventory analogue or constrained GMM.
3. **`mm.limit_fill_hazard_oe` + structural Sandas GMM + prefs theory** — OE ack tape / structural ID.
4. **`cont.volclock_ac1`**, **`disc.mrr_rho_q`** — weak diagnostics.

Public multilevel L2 is **no longer** a ceiling for L1 moments (shipped). PIN usable-day ceiling cleared via opaque flat-id + UTC clip (28≥20).
