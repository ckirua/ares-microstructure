# Desk memo — MM feature / strategy map

**Audience:** crypto perp MM / SOR / execution desk  
**Source program:** Lehalle & Laruelle *Market Microstructure in Practice* → ares-microstructure  
**Bar:** descriptive (D) vs tradable (T) vs execution heuristic (E). Promotes surviving statistical scrutiny only.  
**Data plane:** startarb collector TOB + warehouse trades/marks — **no ClickHouse MCP**.

---

## 1. One-page map

| Desk job | Surviving Promotes | How to use | What it is *not* |
|----------|-------------------|------------|------------------|
| **Quoting** | `tick.spread_bps`, `tick.frac_one_tick`, `tick.spread_leeway`, `liq.quoted_spread_bps`, `spread.vol_link`, `liq.depth_imbalance` | Set width from tick regime + short-horizon vol; skew with imbalance | Not a fair-value signal |
| **Toxicity / make risk** | `tox.markout_1s`, `frag.update_share`, `liq.role_blur_l1`, `hawkes.count_acf` | Widen / pull when markout CI>0 and update≫size; cluster intensity as regime | Not predictive α without fill feedback |
| **SOR / venue select** | `frag.crossed_nbbo` (gate), `lsor.latency_depth_haircut`, `epps.xvenue_corr` | No-naive-take on crossed; haircut depth by RTT; sync hedges via Epps lag | Crossed≠arb; Epps≠edge |
| **Inventory / hedge** | `style.extraday_idio`, `liq.depth_imbalance` | Size residual risk vs BTC factor; lean book with imb | β panel is 1m marks, not HFT |
| **Scheduling / POV** | `vol.curve_intraday`, `vol.fei_hourly`, `sched.vol_curve_share`, `sched.expectation_min`, `sched.pov_envelope`, `impact.algo_pov_sim` | Child π(t) from volume curve; POV prior from sim | Sim has no self-impact |
| **Impact / TCA** | `impact.rho_slope`, `impact.temp_perm`, `spread.effective_vs_quoted` | Participation→impact slope (directional); temp/perm split; effective spread | **Kill** calibrated κ–γ (R²≈0.015) |
| **Book dynamics** | `book.resilience` | Post-trade depth refill monitor | Not queue position (L0 only) |

---

## 2. Surviving Promote list (post-hardening)

From `research/out/promote_hardening/`:

**Promote (24):**  
`frag.update_share`, `frag.crossed_nbbo`, `tick.frac_one_tick`, `tick.spread_bps`, `vol.curve_intraday`, `spread.vol_link`, `vol.fei_hourly`, `impact.rho_slope`, `impact.temp_perm`, `sched.pov_envelope`, `lsor.latency_depth_haircut`, `impact.algo_pov_sim`, `style.extraday_idio`, `tick.spread_leeway`, `tick.rel_tick_bps`, `sched.vol_curve_share`, `sched.expectation_min`, `epps.xvenue_corr`, `hawkes.count_acf`, `liq.role_blur_l1`, `liq.depth_imbalance`, `tox.markout_1s`, `spread.effective_vs_quoted`, `book.resilience`

**Hold:** `harris.mle`, `epps.xasset_corr`, `hawkes.branching_mom`, `sched.mean_variance`, `sess.utc_hour_share`, `liq.update_hz`, `frag.fei_tob_size`, …  

**Kill (this pass):** `impact.kappa_gamma`, `spread.roll` (unidentified), plus prior kills (`frag.duplicate_best`, `dark.toxicity`, `spread.tight_notional_share`).

Multiple-testing honesty: these are **desk feature promotions**, not 24 independent discoveries at α=0.05.

---

## 3. Implementation sketches (column / cadence / latency)

| Feature | Columns | Update | Latency assumption |
|---------|---------|--------|--------------------|
| Quoted spread | `bid, ask → 1e4(A−B)/M` | quote | simultaneous BBO |
| Role blur | 1s `update_share`, `size_share` | 1 Hz | exchange ts preferred |
| Markout 1s | trade `side∈{±1}`, mid as-of, mid+1s | per trade / batch | same-venue clocks |
| Effective spread | `2·side·(p−mid)/mid` | per trade | mid join quality critical |
| Vol curve | hourly `∑p·qty_coin` | daily refresh | n/a |
| POV sim | `π·tape_qty @ trade px` | offline | instant taker, no feedback |
| Crossed gate | `max bid > min ask` aligned | 1s | **must** fee+RTT before take |
| Resilience | L0 `bid_sz+ask_sz` path post large trade | event | L0 only — no queue |

---

## 4. Identification / falsifiers (desk-critical)

| Claim | Falsifier |
|-------|-----------|
| Markout toxicity | 1s CI includes ≤0 on held-out half |
| Spread–vol link | Daily corr bootstrap CI includes ≤0 |
| Impact ρ slope | Spearman(ρ, I) ≤ 0 on time-split |
| Crossed NBBO gate | Fee+latency-adjusted crossed_frac ≈ 0 |
| Role blur | update_share ≈ size_share all venues |
| Resilience | depth_ratio@1s ≈ 1 always |

---

## 5. Honest gaps remaining

1. **No true queue position** — L2 multi-level time series not exported; resilience is L0 refill proxy.
2. **Session / auction analogues** — Hold until full-day tapes (≥12 UTC hours stable across days).
3. **Spatial trade FEI** — multi-venue tape incomplete; TOB FEI still Hold as trade-share substitute.
4. **Calibrated impact model** — κ–γ Kill; need fill-level TCA, not tape ρ buckets alone.
5. **Self-impact / live POV** — sims lack feedback; A/B on OE required before capital.
6. **Clock / fee honesty on crossed books** — raw crossed_frac can be 100% under naive align.
7. **Book PDF / verbatim extracts** — local-only (not in git).

---

## 6. Pointers

| Artifact | Path |
|----------|------|
| Chapter index | `research/CHAPTER_INDEX.md` |
| Hardening JSON | `research/out/promote_hardening/` |
| Shared lib | `research/lib/` |
| Intro package | `research/chapters/intro_liquidity/` |
| Classic micro | `research/chapters/classic_micro/` |
| Synthesis notebook | `research/notebooks/desk_synthesis.ipynb` |
