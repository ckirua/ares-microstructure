# Signal catalog — Tee/Ting mini-flash-crash (Phase 4)

**Slice:** ETH/BTC · HL + Deribit + Kraken · 2026-09-04…2026-09-10  
**SoT:** [`DESK_MEMO.md`](DESK_MEMO.md) · Harden: [`out/phase4_hardening/hardening_gates.json`](out/phase4_hardening/hardening_gates.json) · Lib: [`../../lib/crash.py`](../../lib/crash.py)  
**Honesty:** Phase 4 cleared **0 tradable** Promotes. Application layer adds risk-policy / MM playbook / feature Promotes — still **not** naked alpha. Classes: `risk monitor` | `risk-policy` | `MM playbook` | `descriptive` | `feature` | `tradable` (none).  
**Lenses:** `risk` · `info` · `exec` · `disc` · `cont` · `liq` · `mm`  
**Application playbook:** [`TRADING_APPLICATIONS.md`](TRADING_APPLICATIONS.md) · board [`DESK_MEMO.md`](DESK_MEMO.md) §7 · packages [`applications/README.md`](applications/README.md)

**Severity gates (locked):** primary **10bps / i_c≥5** (n=275 from raw 3668); frag share/thin also **5bps / i_c≥3** (n=589); strict **30bps / i_c≥10** (n=56).

**Cross-book strengtheners (do not re-derive):**
- mmip: `frag.crossed_nbbo`, `frag.update_share`, `epps.xvenue_corr`, `vol.fei_hourly`, `vol.curve_intraday`, `book.resilience`, `spread.vol_link`, `lsor.latency_depth_haircut`
- empirical_mm: `cont.vpin`, `disc.jump_sign_concord`, `liq.amihud_1m`, `info.markout_1s`, `disc.var_lambda`, `mm.book_resilience_lo`

---

## A. Promote (10) — risk / info / frag monitors

### 1. `risk.ssm_severity_gate_10bps`

| Field | Content |
|-------|---------|
| **Definition** | Keep SSM events with \(\lvert\Delta P\rvert \ge 10\,\mathrm{bps}\) and trade count \(i_c\ge 5\). |
| **Formula / rule** | `severity_gate(events, min_dp_pct=0.10, min_i_c=5)` — primary desk gate. Ablation ladder: raw → 5bps/ic3 → 10bps/ic5 → 30bps/ic10. |
| **Empiric headline** | Ablation **3668 → 589 → 275 → 56**; gated median ΔP cell-boot CI95 **[0.167, 0.214]%** (point ≈0.192%). |
| **Lenses** | `risk` · `disc` |
| **Class** | **risk monitor** (not tradable) |
| **Data / refresh / venue** | Per-venue trade tape (HL, Deribit, Kraken); KF SSM z* first. Refresh: event-time / 1–5s intensity rollups. |
| **Failure modes** | Ungated z*=6 floods with median ΔP≈0 (**Kill** `risk.ssm_raw_ungated_counts`). Gate too tight → underpowered xsec. Crypto % units ≠ equity ticks. |
| **Applications** | **Kill-switch ladder:** gated intensity → observe/widen/size-cap/halt — **Promote-as-risk-policy** ([`applications/kill_ladder/`](applications/kill_ladder/), Δ\|mo\|@5s +6.54 bps) (**high**). **Size caps:** raise when gated intensity spikes on HL (**med** monitor; hard cap still Hold — see hl_thin_sor). **ML regime:** binary crash-regime label (**med**). Never use raw SSM counts (**high**). |

---

### 2. `risk.ssm_zstar_scan_table`

| Field | Content |
|-------|---------|
| **Definition** | Desk menu of crash counts vs outlier threshold \(z^*\) (paper Table III analogue). |
| **Formula / rule** | Event count where \(\lvert z\rvert\ge z^*\), \(z^*=(x-\hat x^-)/\sqrt{P^-+\sigma_m^2}\); scan \(z\in\{2,\ldots,12\}\). |
| **Empiric headline** | Monotone pooled/early/late; n(z*) = **[36416, 17340, 9578, 5747, 3668, 2476, 1770, 1331, 1028, 796, 630]** for z*=2…12. |
| **Lenses** | `risk` · `disc` |
| **Class** | **risk monitor** / calibration table |
| **Data / refresh / venue** | Same SSM path; publish daily + rolling 1h menus per venue. |
| **Failure modes** | Binary cut alone without severity gate (**Hold** `risk.ssm_z6_binary`). σ_m floor off → non-monotone flood. |
| **Applications** | **Policy ladder:** map z* bands → widen / pull / halt levels (**high**). **TCA stress:** report fills under each z* regime (**med**). **Model calibration:** choose operating point jointly with severity gate (**high**). |

---

### 3. `vol.sigma_m_noise_floor_1bp`

| Field | Content |
|-------|---------|
| **Definition** | Measurement noise for KF must not collapse below ~1 bp on tick-clustered crypto tape. |
| **Formula / rule** | \(\sigma_m = f\cdot\max(\mathrm{MAD}(\Delta\log p),\,10^{-4})\); default \(f=1\). |
| **Empiric headline** | σ_m frac stress n_SSM: **{0.5: 13832, 1.0: 3668, 2.0: 808, 4.0: 177}**; floor prevents tick-MAD collapse (esp. Deribit/Kraken). |
| **Lenses** | `risk` · `disc` |
| **Class** | **descriptive** calibration constraint (enables all SSM monitors) |
| **Data / refresh / venue** | Trade returns per venue; estimate MAD per day×symbol (or rolling 1h). All three venues. |
| **Failure modes** | \(f\) too small / floor removed → vanity intensity. \(f\) too large → miss real bursts. |
| **Applications** | **Hard infra rule** before any SSM kill-switch (**high**). **Vol filter:** treat floor hits as “tick-dominated” regime for quoting (**med**). Cross-link mmip `spread.vol_link` for widen on realized vol (**med**). |

---

### 4. `info.crash_def_taxonomy`

| Field | Content |
|-------|---------|
| **Definition** | Operational labeling of five crash defs into desk classes: tape-burst / broad outlier / stale-quote artifact / hole (V) / news (continuation). |
| **Formula / rule** | Map Nanex θ, SSM z*, outside-TOB, recovery@5s onto mutually informative labels — not a single numeric claim. |
| **Empiric headline** | Taxonomy survives Nanex⊂SSM precision (**0.895**) + outside-TOB stale-quote class; framing object. |
| **Lenses** | `info` |
| **Class** | **descriptive** |
| **Data / refresh / venue** | Trades + (when available) TOB; event-time. All venues. |
| **Failure modes** | Collapsing Nanex≡SSM vanity; treating outside-TOB as edge when L2 sparse. |
| **Applications** | **Incident postmortems / desk language** (**high**). **Feature engineering:** one-hot crash class into MM state (**med**). **SOR:** route differently for hole vs news labels once recovery Promote is live (**med**). |

---

### 5. `info.nanex_subset_of_ssm`

| Field | Content |
|-------|---------|
| **Definition** | Nanex-style bursts are a high-precision subset of SSM outliers, not the converse. |
| **Formula / rule** | Precision = P(SSM | Nanex match within pad); recall = P(Nanex | SSM) ≪ 1. Crypto Nanex default θ=30bps, ≤1.5s, ≥10 trades. |
| **Empiric headline** | Pooled precision **0.895**; cell boot CI95 **[0.735, 0.970]**; early/late mean **0.885 / 0.830**. |
| **Lenses** | `info` · `risk` |
| **Class** | **risk monitor** (burst tag) |
| **Data / refresh / venue** | Trade tape; event match Nanex↔SSM; HL/DB/KR. |
| **Failure modes** | θ ablation 80→30 fragile for standalone Nanex (**Hold** `base.nanex_crypto_30bps`). Paper 80bps **Kill** (n=8). |
| **Applications** | **Burst kill-switch / nested auto-pull:** Nanex-on-SSM = high-precision escalate — **Promote-as-risk-policy** ([`applications/nanex_burst/`](applications/nanex_burst/), prec=0.905) (**high**). **Do not** use Nanex alone as intensity (**high**). |

---

### 6. `info.crash_v_vs_continuation`

| Field | Content |
|-------|---------|
| **Definition** | Classify gated crashes as V-recovery (liquidity hole) vs continuation (news assimilation) from post-event price recovery. |
| **Formula / rule** | \(R =\) fraction of event move reversed by +5s; V if \(R\ge 0.5\); continuation if \(R < 0.2\). |
| **Empiric headline** | share_V **0.771** boot CI **[0.706, 0.806]**; early/late **0.798 / 0.757**; obs cell-median recovery ≈**1.24** vs placebo ≈**0.67**. |
| **Lenses** | `info` · `risk` · `liq` |
| **Class** | **risk monitor** / **feature** (not tradable mean-revert edge on this slice) |
| **Data / refresh / venue** | Trades through +5s post-event; gated SSM; all venues. Dense mid preferred for future promote of fade rules. |
| **Failure modes** | Placebo recovery ≥ obs → Kill class. Tape-only markout still Hold for throttle. Horizon choice (1s vs 5s) shifts share. |
| **Applications** | **Quoting playbook (Promote med):** restore size after V-confirm @1–2s; stay wide on continuation — sim [`applications/mm_quoting/`](applications/mm_quoting/) (**med**). **Inventory fade:** still **low** until mid markout Promote. **ML:** binary class feature (**high** as label, **low** as alpha). Cross-link empirical_mm `info.markout_1s`, mmip `book.resilience`. |

---

### 7. `frag.volume_herfindahl_3venue`

| Field | Content |
|-------|---------|
| **Definition** | USD volume concentration across HL + Deribit + Kraken. |
| **Formula / rule** | \(H^v=\sum_k (s^k)^2\), \(s^k=V^k/\sum V\); complete 3-venue days only. |
| **Empiric headline** | Mean \(H^v\) **0.482**; boot CI95 **[0.463, 0.499]**; early/late **0.500 / 0.468** (\(\lvert\Delta\rvert=0.032\)). |
| **Lenses** | `liq` · `mm` |
| **Class** | **risk monitor** (capacity / concentration) |
| **Data / refresh / venue** | Day or rolling 1h USD notional per venue (Deribit inverse: qty=USD). 14/14 complete day×symbol. |
| **Failure modes** | Incomplete legs → NaN / biased H. Coin-share vs USD-share mix. Treating H as tradable edge. |
| **Applications** | **SOR capacity monitor:** high \(H^v\) → prefer thick legs (**high** dashboard). **Executable child-size schedule:** **Hold** — qty cut on high-H clears CI; exposure cut does not ([`applications/hv_fei_capacity/`](applications/hv_fei_capacity/)). Companion to FEI (**high**). |

---

### 8. `frag.fei_volume_3venue`

| Field | Content |
|-------|---------|
| **Definition** | Fragmentation Efficiency Index on 3-venue USD shares (dispersion companion to Herfindahl). |
| **Formula / rule** | \(\mathrm{FEI}=H_{\mathrm{Shannon}}(s)/\log N\), \(N=3\); equal shares → 1. |
| **Empiric headline** | FEI_vol point **0.750**; boot CI95 **[0.721, 0.784]** on complete 3-venue days. |
| **Lenses** | `liq` · `mm` |
| **Class** | **risk monitor** |
| **Data / refresh / venue** | Same as Herfindahl; refresh 5–60m. |
| **Failure modes** | FEI on incomplete venue set; confusing with hourly FEI (`vol.fei_hourly`). |
| **Applications** | **Regime flag:** FEI drop = concentration spike → tighten SOR / size (**high**). **Dashboard pair** with \(H^v\) (**high**). **TCA:** attribute slippage by FEI bucket (**med**). |

---

### 9. `frag.crash_venue_share`

| Field | Content |
|-------|---------|
| **Definition** | Where severity-gated crashes print across the 3-venue panel. |
| **Formula / rule** | Venue share of gated SSM (and Nanex) events; primary report @10bps/ic5; denser @5bps/ic3. |
| **Empiric headline** | @10bps: HL **0.829** / DB **0.076** / KR **0.095** (early HL 0.661 / late **0.917**); @5bps HL≈0.825. |
| **Lenses** | `risk` · `liq` |
| **Class** | **risk monitor** |
| **Data / refresh / venue** | Gated events + venue id; daily and intraday. |
| **Failure modes** | Ungated SSM → HL micro-flood dominates. Late-week HL dominance may be cohort-specific. |
| **Applications** | **Venue risk map:** HL crash-dense despite thin USD (**high**). **SOR:** de-prioritize HL aggressive takes in high gated-intensity windows (**med**). **MM:** HL quotes need wider crash buffer than vol share suggests (**med**). |

---

### 10. `frag.thin_venue_crash_excess`

| Field | Content |
|-------|---------|
| **Definition** | Thin (lowest USD share) venue carries excess crash share vs volume share. |
| **Formula / rule** | \(\mathrm{excess}=\mathrm{crash\_share}-\mathrm{vol\_share}\) on thin leg (HL on this slice). Hypothesis: excess > 0. |
| **Empiric headline** | HL thin excess @5bps boot CI **[0.628, 0.828]** (point≈0.73 day-mean; pooled≈**0.78**); @10bps point **0.789**; early/late **0.745 / 0.714**; @30bps lo still >0.53. |
| **Lenses** | `risk` · `liq` · `mm` |
| **Class** | **risk monitor** (exec throttle candidate — not cleared tradable) |
| **Data / refresh / venue** | Joint vol shares + gated crash shares; daily + rolling. |
| **Failure modes** | Excess≤0 or flips on 30bps / time-split → Kill. Identifying “thin” wrong if USD mapping broken (Deribit qty). |
| **Applications** | **Kill / size-cap on thin leg:** **Promote monitor** strip; **Hold as live hard size-cap** — Δ\|mo\| fire vs thick CI includes 0 ([`applications/hl_thin_sor/`](applications/hl_thin_sor/)). **Inventory:** reduce HL when thin excess + gated intensity co-fire (**med** soft). Cross-link mmip `lsor.latency_depth_haircut`. |

---

## A2. Application-layer Promotes (not naked alpha)

### `info.vpin_x_size_severity` — **Promote (med) feature**

| Field | Content |
|-------|---------|
| **Definition** | Interaction: ex-ante VPIN × log notional → crash \(\lvert\Delta P\rvert\). |
| **Formula / rule** | NW-OLS interact on gated events; VPIN asof before event start (`vpin_exante`). |
| **Empiric headline** | n=275 R²≈0.09; interact boot CI95 **[−0.137, −0.032]** excludes 0; train/test t_interact stable; size β early/late same sign. |
| **Lenses** | `info` · `risk` · `cont` |
| **Class** | **feature** (Promote med — **not** tradable / live sizing) |
| **Data / refresh / venue** | Gated events + rolling VPIN; all venues; refresh event-time. |
| **Failure modes** | Plain size main effect remains **Kill**; live quote size from interact alone overfit risk. |
| **Applications** | ML toxicity×size co-feature (**med** Promote — [`applications/feature_models/`](applications/feature_models/)); live sizing (**low**). Cross-link `cont.vpin`. |

### Soft Promote — day-level crash occurrence (apps only)

| Field | Content |
|-------|---------|
| **Object** | `feature.crash_occurrence_dayhalf` (not a Phase-4 catalog ID) |
| **Empiric** | Logistic AUC_te≈**0.635** on day×half cells; severity \|ΔP\| ridge OOS R²\<0 → severity **Hold** |
| **Class** | **feature** Soft Promote (regime score only) |
| **Path** | [`applications/feature_models/`](applications/feature_models/) |

### MM playbook — V-restore quoting (apps only)

| Field | Content |
|-------|---------|
| **Object** | `info.crash_v_vs_continuation` → quote-size restore policy |
| **Empiric** | V mo@5s≈−16.5 / cont≈+12.1; stay-wide & confirm-V beat blind restore on cont cost |
| **Class** | **MM playbook** Promote (med) — not fade alpha |
| **Path** | [`applications/mm_quoting/`](applications/mm_quoting/) |

### Risk-policy (apps only)

| Object | Verdict | Path |
|--------|---------|------|
| Gated SSM kill-ladder | **Promote-as-risk-policy** | [`applications/kill_ladder/`](applications/kill_ladder/) |
| Nanex∩SSM nested auto-pull | **Promote-as-risk-policy** | [`applications/nanex_burst/`](applications/nanex_burst/) |

---

## B. Hold (12) — blockers + path to Promote

*Note: `info.vpin_x_size_severity` flipped to app-layer **Promote (med) feature** (A2). Phase-4 Hold count was 13.*

### 11. `base.nanex_crypto_30bps`

| Field | Content |
|-------|---------|
| **Definition** | Crypto Nanex: uni-dir move ≥30bps, ≤1.5s, ≥10 trades. |
| **Formula / rule** | `nanex_detect(..., min_pct=0.003, max_window_s=1.5, min_trades=10)`. |
| **Empiric headline** | n=105 on slice; nests in SSM (prec≈0.90) but θ ablation 80→30 fragile. |
| **Lenses** | `risk` · `exec` · `info` |
| **Class** | **feature** / tentative burst tag (not standalone Promote) |
| **Data / refresh / venue** | Trade tape; all venues. |
| **Failure modes** | θ instability; paper 80bps vanity (**Kill**). |
| **Promote needs** | Nest-required policy (only fire if also SSM+severity); θ grid stable across ≥4 weeks + SOL/extra symbols; bootstrap CI on precision not just count. |
| **Applications** | Escalation tag under SSM (**med**); standalone intensity (**low**). |

---

### 12. `risk.ssm_z6_binary`

| Field | Content |
|-------|---------|
| **Definition** | Paper default binary \(\lvert z\rvert\ge 6\). |
| **Formula / rule** | `ssm_crash_mask(z, z_star=6)`. |
| **Empiric headline** | Raw median ΔP≈0; n_raw=3668 — vanity without severity. |
| **Lenses** | `risk` · `mm` |
| **Class** | **descriptive** (Hold) |
| **Promote needs** | Always publish with severity gate + z* menu; Promote only severity-weighted intensity, not raw binary. |
| **Applications** | Do not drive kill-switches off raw z*=6 (**high** negative). Use as intermediate flag into gate (**high**). |

---

### 13. `info.ssm_innov_continuous`

| Field | Content |
|-------|---------|
| **Definition** | Continuous KF innovation / gain path as a signal. |
| **Formula / rule** | Standardized innovation \(z_t\); optional κ / gain series. |
| **Empiric headline** | Forward lead–lag \(\lvert\mathrm{corr}\rvert\approx 0.04\) — diagnostic only. |
| **Lenses** | `info` · `risk` |
| **Class** | **feature** (research) |
| **Promote needs** | \(\lvert\mathrm{corr}\rvert\gtrsim 0.1\) OOS vs mid/trade returns, or proven value as MM state feature (not alpha). |
| **Applications** | Regime feature for ML (**low–med**); tradable (**Kill** on this slice). |

---

### 14. `exec.outside_tob_wh_l2`

| Field | Content |
|-------|---------|
| **Definition** | Trade prints outside warehouse L2 [bid, ask] asof join. |
| **Formula / rule** | \(1\{p\notin[b,a]\}\) asof L2. |
| **Empiric headline** | outside_rate **15–79%**; sparse quotes vs ms trades. |
| **Lenses** | `exec` · `liq` |
| **Class** | **descriptive** / stale-quote detector (Hold as throttle) |
| **Data / refresh / venue** | Dense collector TOB + trades; currently warehouse L2 insufficient. |
| **Promote needs** | Dense multi-venue TOB on same clock; separate stale-feed vs true crossed prints; stable outside_rate ≪ tape noise. |
| **Applications** | Taxonomy stale-quote class (**med**); exec throttle (**low** until dense L2). Cross-link mmip `frag.crossed_nbbo` (**Promote** there as honesty gate). |

---

### 15. `exec.tape_markout_post_crash`

| Field | Content |
|-------|---------|
| **Definition** | Signed trade-price markout after gated crash end. |
| **Formula / rule** | \(\mathrm{mo}_h = d\cdot(p_{t+h}-p_t)/p_t\) in bps; h∈{0.5,1,5}s. |
| **Empiric headline** | Tape mo@5s ≈ **−11.1 bps** (apps denser); early/late sign stable; V≈−16.5 vs cont≈+12.1 class sep OK; **mid_frac=0** → still Hold as exec throttle. |
| **Lenses** | `exec` · `mm` |
| **Class** | **feature** / tentative throttle |
| **Promote needs** | Mid/mark markout with CI (mid coverage ≥50%); venue-split; V vs continuation stratified (class sep already OK). |
| **Applications** | Class diagnostic for MM playbook (**med**); fade / exec throttle (**Hold** — [`applications/feature_models/`](applications/feature_models/)). Pair empirical_mm `info.markout_1s`. |

---

### 16. `risk.duration_post_markout`

| Field | Content |
|-------|---------|
| **Definition** | Longer crash duration ↔ post-event markout magnitude. |
| **Formula / rule** | Spearman(\(\Delta t\), \(\lvert\mathrm{mo}\rvert\)); also \(i_c\) and volume-clock. |
| **Empiric headline** | Spearman(dt) ≈ **−0.30** but median \(\Delta t=0\) (frac0≈0.51); OOS \|ρ\|(i_c)\≈0.16, vol-clock≈0.07 — below \|ρ\|≥0.20 bar → **Hold**. |
| **Lenses** | `risk` · `exec` |
| **Class** | **feature** |
| **Promote needs** | Volume-clock / trade-count duration with OOS \|ρ\|≥0.20 sign-stable. |
| **Applications** | Throttle on long multi-trade bursts (**Hold** — [`applications/feature_models/`](applications/feature_models/)). |

---

### 17. *(moved)* `info.vpin_x_size_severity` → see **A2** Promote (med) feature

---

### 18. `risk.exante_amihud_severity`

| Field | Content |
|-------|---------|
| **Definition** | Lagged Amihud illiquidity predicts crash severity. |
| **Formula / rule** | lag-1 Amihud → \(\lvert\Delta P\rvert\); empirical_mm `liq.amihud_1m`. |
| **Empiric headline** | n_pred=**20**; Amihud t≈**−2.5** direction OK but underpowered. |
| **Lenses** | `risk` · `liq` |
| **Class** | **feature** |
| **Promote needs** | n≫20 (multi-week, multi-coin); cell bootstrap; time-split sign stable. |
| **Applications** | Pre-trade severity prior (**med** if powered); quote widen in high Amihud (**med** speculative). |

---

### 19. `frag.xvenue_crash_concord`

| Field | Content |
|-------|---------|
| **Definition** | Cross-venue crash time concordance (contagion / hedge-sync). |
| **Formula / rule** | Jaccard of event intervals ±5s across HL↔DB↔KR; placebo circular-shift. |
| **Empiric headline** | Jaccard@5s HL–DB **0**, HL–KR **0**, DB–KR **0.126**; placebo p(ge obs)≈**0.58** — not above chance. |
| **Lenses** | `risk` · `info` |
| **Class** | **descriptive** (Hold) |
| **Promote needs** | Concordance ≫ placebo on wider window / coarser pad; or prove useful as *absence* of sync (venue-idiosyncratic holes). |
| **Applications** | Do **not** assume multi-venue crash sync for hedges (**high**). Venue-local kill-switches (**high**). Cross-link `disc.jump_sign_concord`, `epps.xvenue_corr` for *price* sync vs *crash* sync. |

---

### 20. `frag.crossed_nbbo_crashwin`

| Field | Content |
|-------|---------|
| **Definition** | Consolidated cross (max bid > min ask) in crash ±pad. |
| **Formula / rule** | mmip `frag.crossed_nbbo` on aligned multi-venue TOB. |
| **Empiric headline** | **n_crossed_available=0** on this slice (TOB gap); mmip Promote still stands elsewhere. |
| **Lenses** | `exec` · `liq` |
| **Class** | **risk monitor** candidate (Hold here) |
| **Promote needs** | Dense multi-venue TOB on crash days; then re-run crash-window rates. |
| **Applications** | Hard no-take honesty gate when available (**high** via mmip). Crashwin-specific Promote pending data. |

---

### 21. `epps.crash_window_corr`

| Field | Content |
|-------|---------|
| **Definition** | Epps corr in crash ±60s vs full-day Epps. |
| **Formula / rule** | corr(HL mid, Deribit mark) vs lag; compare day vs crash windows. |
| **Empiric headline** | Crash-window Epps not reliably < day Epps on slice. |
| **Lenses** | `cont` · `liq` |
| **Class** | **descriptive** |
| **Promote needs** | Systematic Δ(corr) with CI; align with mmip `epps.xvenue_corr` Promote (day Epps still useful for hedge horizon). |
| **Applications** | Hedge sync horizon from **day** Epps (**med** via mmip); crash-special Epps (**low**). |

---

### 22. `vol.mc_garch_sj_utc`

| Field | Content |
|-------|---------|
| **Definition** | UTC diurnal seasonality \(s_j\) from MC-GARCH path. |
| **Formula / rule** | 5m UTC diurnal on 24/7 tape; peak hour as schedule prior. |
| **Empiric headline** | UTC-**12** peak this cohort vs mmip ~**18** elsewhere — schedule prior only. |
| **Lenses** | `risk` · `mm` |
| **Class** | **descriptive** prior |
| **Promote needs** | Joint multi-book panel; stable peak across cohorts; else keep as soft prior. |
| **Applications** | Soft quoting capacity by hour (**low–med**); prefer mmip `vol.curve_intraday` when available (**med**). |

---

### 23. `vol.curve_intraday_link`

| Field | Content |
|-------|---------|
| **Definition** | Link Tee/Ting diurnal to mmip `vol.curve_intraday` / FEI hourly. |
| **Formula / rule** | Align hourly notional shares / FEI across books. |
| **Empiric headline** | Cross-book peak mismatch until joint panel. |
| **Lenses** | `mm` · `exec` |
| **Class** | **descriptive** |
| **Promote needs** | Same days/venues joint curve; document peak delta CI. |
| **Applications** | Unified schedule once peaks agree (**med**); until then use mmip curve for HL scheduling (**med**). |

---

## C. Kill (3) — do not operationalize

| ID | Why (one line) |
|----|----------------|
| `base.nanex_paper_80bps` | n=8 / 42 cells — equity vanity cutoff on crypto ms tape |
| `risk.ssm_raw_ungated_counts` | Raw z*=6 median ΔP≈0 — intensity without severity is vanity |
| `xsec.size_reduces_severity` | R²≈0.02; time-split β(logN) sign flip — notional≠paper MCap |

---

## D. Quick lens index

| Lens | Promote IDs | Hold IDs (application-relevant) |
|------|-------------|----------------------------------|
| **risk** | severity_gate, zstar_scan, nanex_subset, v_vs_cont, crash_venue_share, thin_excess | z6_binary, nanex_30bps, duration_mo, exante_amihud, xvenue_concord |
| **info** | taxonomy, nanex_subset, v_vs_cont, **vpin×size (apps med)** | ssm_innov |
| **exec** | — (none Promote) | outside_tob, tape_markout, crossed_nbbo_crashwin |
| **liq / mm** | H^v, FEI, thin_excess, v_vs_cont (+ MM playbook) | curve_link, mc_garch_sj |
| **disc / cont** | sigma_m floor, zstar, severity, vpin×size | epps crash |

**App-layer extras:** Soft Promote day-level occurrence; kill-ladder / Nanex nested pull = risk-policy; HL thin & H^v/FEI = monitor.
