# Desk memo — Cross-Section of Mini Flash Crashes (Tee & Ting 2019)

**Audience:** crypto MM / SOR / execution / taker / risk / research  
**Source:** Tee & Ting working paper (2019-06-12) → `research/books/cross_miniflash/`  
**Philosophy:** lenses `risk | info | exec | disc | cont | liq | mm` — detection objects are **not** automatically tradable.  
**Data:** warehouse trades + collector/warehouse TOB on **HL + Deribit + Kraken** — **no ClickHouse MCP**.  
**Program status:** **COMPLETE (Phase 4 hardened)** — **10 Promote / 13 Hold / 3 Kill**. Slice ETH/BTC 2026-09-04…2026-09-10.  
**SoT:** [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) · Lib: [`../../lib/crash.py`](../../lib/crash.py) · Out: [`out/phase4_hardening/`](out/phase4_hardening/) · Phase2 [`out/phase2_baselines_ssm/`](out/phase2_baselines_ssm/) · Phase3a [`out/phase3a_stats_xsec/`](out/phase3a_stats_xsec/) · Frag [`out/frag_xvenue/`](out/frag_xvenue/).  
**Experiments ledger (tested vs not):** [`EXPERIMENTS.md`](EXPERIMENTS.md).

**Applications (post–Phase 4):** unified board §7 · packages [`applications/`](applications/) · per-signal [`SIGNAL_CATALOG.md`](SIGNAL_CATALOG.md) · playbook [`TRADING_APPLICATIONS.md`](TRADING_APPLICATIONS.md). *None cleared as naked tradable alpha* — risk-policy / MM playbook / feature / monitor only.

### Open these first

| # | Open | Path |
|---|------|------|
| 1 | **Full research board** (signal / MI / stats / Bayesian) | [`notebooks/full_research_board.ipynb`](notebooks/full_research_board.ipynb) |
| 2 | Signal boards · Info theory · Statistical · Bayesian | [`applications/signal_boards/`](applications/signal_boards/) |
| 3 | Tick / OB equity sims (sibling) | [`applications/strategy_lab/STRATEGY_LAB.md`](applications/strategy_lab/STRATEGY_LAB.md) · [`strategy_lab.ipynb`](applications/strategy_lab/strategy_lab.ipynb) |
| 4 | Expanded lab (longer panel / risk scoreboard) | [`applications/expanded_lab/`](applications/expanded_lab/) · [`EXP_REPORT.md`](applications/expanded_lab/EXP_REPORT.md) · [`expanded_lab.ipynb`](applications/expanded_lab/expanded_lab.ipynb) |
| 5 | **Paper harness** (HL ETH day risk report) | [`applications/paper_harness/`](applications/paper_harness/) · [`README.md`](applications/paper_harness/README.md) · `out/<day>_hyperliquid_ETH/RISK_REPORT.md` |
| 6 | Feature models · MM quoting | [`applications/feature_models/severity_regime.ipynb`](applications/feature_models/severity_regime.ipynb) · [`applications/mm_quoting/v_continuation_quoting.ipynb`](applications/mm_quoting/v_continuation_quoting.ipynb) |

**Key PNGs — signal boards:** [`applications/out/signal_boards/figs/`](applications/out/signal_boards/figs/) — `fig_gated_intensity_ts.png`, `fig_zstar_path_ts.png`, `fig_event_heatmaps.png`, `fig_mi_event.png`, `fig_occurrence_roc.png`, `fig_bayes_v_recovery.png`, `fig_bayes_logistic_ppc.png`.  
**Key PNGs — strategy equity:** [`applications/strategy_lab/out/figs/`](applications/strategy_lab/out/figs/).  
**Key PNGs — expanded risk:** [`applications/expanded_lab/out/figs/`](applications/expanded_lab/out/figs/) — `fig_kill_ladder_robustness.png`, `fig_strategy_risk_scoreboard.png`, `fig_friction_sweep.png`, `fig_book_cadence_compare.png`.

---

## 1. Desk jobs × outputs

| Job | Object | Desk label | Status |
|-----|--------|------------|--------|
| **Risk monitor** | SSM z* + **severity gate** + scan table | Gated counts only; z* menu | **Promote** gate / scan · **Hold** binary z*=6 |
| **Frag / SOR capacity** | 3-venue volume Herfindahl + FEI | Capacity / concentration monitor | **Promote** |
| **Crash venue map** | Severity-gated crash share vs vol share | Where crashes print vs volume | **Promote** (HL thin + crash-dense) |
| **X-venue sync** | HL↔Deribit↔Kraken concordance | Contagion / hedge-sync | **Hold** (placebo fails) |
| **Recovery class** | V-recovery vs continuation @5s | Hole vs news assimilation | **Promote** |
| **Toxicity / info** | VPIN around events; VPIN×size | Concurrent toxicity | Feature OK; xsec **Hold** |
| **Execution throttle** | Outside-TOB / tape markout | Stale L2; mo≈−7bps @5s | **Hold** |
| **Taxonomy** | Nanex ⊂ SSM; V vs continuation | Burst / hole vs news | **Promote** |
| **Xsec size** | log notional → ΔP | Paper MCap path | **Kill** |
| **Scheduling** | UTC hour share / s_j | Prior only | **Hold** |

---

## 2. Signal board (Phase 4 hardened)

| ID | Formula / clock | Monitor | Tradable | Exec throttle | Decision |
|----|-----------------|---------|----------|---------------|----------|
| `frag.crash_venue_share` | gated SSM/Nanex venue mix | ✓ | — | — | **Promote** — HL crash share @10bps=0.829 (early 0.660 / late 0.917); frag tables al |
| `frag.fei_volume_3venue` | FEI on 3-venue shares | ✓ | — | — | **Promote** — FEI_vol boot CI95=[0.721,0.784] on complete 3-venue days |
| `frag.thin_venue_crash_excess` | crash−vol share thin leg | ✓ | — | maybe | **Promote** — HL thin excess @5bps bootCI=[0.628,0.828] early/late=0.745/0.714; @30b |
| `frag.volume_herfindahl_3venue` | H^v=∑s_k² USD | ✓ | — | — | **Promote** — H^v boot CI95=[0.463,0.499]; early/late=0.500/0.468 /Δ/=0.032 |
| `info.crash_def_taxonomy` | 5 defs → class | ✓ | — | — | **Promote** — Framing taxonomy survives Nanex⊂SSM precision + outside-TOB stale-quot |
| `info.crash_v_vs_continuation` | recovery≥0.5 @5s | ✓ | ✗ | maybe | **Promote** — share_V=0.771 bootCI=[0.706,0.806]; early/late=0.798/0.757; obs_rec_me |
| `info.nanex_subset_of_ssm` | Nanex 30bps ∩ SSM | ✓ | — | maybe | **Promote** — pooled prec=0.895; cell boot CI95=[0.735,0.970]; early/late mean=0.885 |
| `risk.ssm_severity_gate_10bps` | |ΔP|≥10bps, i_c≥5 | ✓ | — | — | **Promote** — ablation 3668→589→275→56; gated median ΔP cell-boot CI95=[0.167,0.214] |
| `risk.ssm_zstar_scan_table` | events(z*), z∈[2,12] | ✓ | — | — | **Promote** — monotone pooled=True; early=True late=True; z*=[2.0, 3.0, 4.0, 5.0, 6. |
| `vol.sigma_m_noise_floor_1bp` | σ_m≥10^{-4} | ✓ | — | — | **Promote** — σ_m frac stress n_SSM {0.5: 13832, 1.0: 3668, 2.0: 808, 4.0: 177}; flo |
| `base.nanex_crypto_30bps` | θ=0.3% | ✓ | — | tent. | **Hold** — high-precision burst tag only with SSM nesting; θ ablation fragile (80 |
| `epps.crash_window_corr` | Epps @ crash±60s | diag | ✗ | — | **Hold** — crash-window Epps not reliably < day Epps |
| `exec.outside_tob_wh_l2` | p∉[b,a] asof L2 | — | — | ✗ | **Hold** — warehouse L2 outside_rate 15–79%; sparse quotes vs ms trades |
| `exec.tape_markout_post_crash` | tape mo post crash | — | ✗ | maybe | **Hold** — apps: mo@5s≈−11bps, class sep OK, mid_frac=0 |
| `frag.crossed_nbbo_crashwin` | cons. cross crash±pad | — | — | mmip | **Hold** — n_crossed_available=0 on slice; mmip crossed_nbbo still stands |
| `frag.xvenue_crash_concord` | ±5s Jaccard HL↔DB↔KR | maybe | ✗ | — | **Hold** — placebo p(ge obs)≈0.58; Jaccard@5s={'hyperliquid_deribit': 0.0, 'hyper |
| `info.ssm_innov_continuous` | innov, κ path | diag | ✗ | — | **Hold** — forward lead–lag /corr/≈0.04 — diagnostic only, not tradable |
| `info.vpin_x_size_severity` | VPIN×logN → ΔP | maybe | ✗ | — | **Promote (med) feature** — apps denser: interact boot CI excludes 0; not live sizing |
| `risk.duration_post_markout` | Spearman(dt,|mo|) | maybe | ✗ | maybe | **Hold** — Spearman(dt,/mo/)≈−0.28 but median Δt=0 weakens clock |
| `risk.exante_amihud_severity` | lag1 Amihud→ΔP | maybe | ✗ | — | **Hold** — n_pred=20; Amihud t≈−2.5 direction OK but underpowered |
| `risk.ssm_z6_binary` | |innov|/√S ≥ 6 | tent. | ✗ | — | **Hold** — raw median ΔP≈0; use severity gate + z* menu instead |
| `vol.curve_intraday_link` | mmip curve link | prior | — | — | **Hold** — cross-book peak mismatch until joint panel |
| `vol.mc_garch_sj_utc` | UTC diurnal s_j | prior | — | — | **Hold** — UTC-12 peak this cohort vs mmip ~18 elsewhere — schedule prior only |
| `base.nanex_paper_80bps` | θ=0.8%, 1.5s | — | — | — | **Kill** — n=8 / 42 cells — vanity equity cutoff on crypto ms tape |
| `risk.ssm_raw_ungated_counts` | raw z*=6 counts | — | — | — | **Kill** — raw z*=6 median ΔP≈0; intensity without severity gate is vanity |
| `xsec.size_reduces_severity` | logN → |ΔP| | — | — | — | **Kill** — R²≈0.02; time-split β sign flip early=0.0010321979810437483 late=-0.00 |

**Monitor (Promote):** `info.crash_def_taxonomy`, `info.nanex_subset_of_ssm`, `vol.sigma_m_noise_floor_1bp`, `risk.ssm_zstar_scan_table`, `risk.ssm_severity_gate_10bps`, `info.crash_v_vs_continuation`, `frag.volume_herfindahl_3venue`, `frag.fei_volume_3venue`, `frag.crash_venue_share`, `frag.thin_venue_crash_excess`  
**App-layer Promote:** risk-policy kill-ladder + Nanex nested pull · MM playbook V-restore (med) · feature `info.vpin_x_size_severity` (med) · Soft Promote day-level occurrence  
**Tradable:** *none* (all Promotes are risk-policy / MM playbook / feature / monitor).  
**Exec throttle:** Hold — `exec.outside_tob_wh_l2`, `exec.tape_markout_post_crash` (mid_frac=0), `risk.duration_post_markout`.  
**Kill list:** `base.nanex_paper_80bps`, `xsec.size_reduces_severity`, `risk.ssm_raw_ungated_counts`

**Hold blockers:** dense multi-venue TOB; concordance placebo; volume-clock duration OOS.

**mmip / empirical_mm cross-links:** `frag.crossed_nbbo`, `frag.update_share`, `epps.xvenue_corr`, `vol.fei_hourly`; empirical_mm `disc.jump_sign_concord`, `cont.vpin`, markout.

---

## 3. Severity gate (unified)

| Gate | Use | Pooled n (raw 3668) |
|------|-----|--------------------:|
| **10bps / i_c≥5 (PRIMARY)** | Promote risk intensity, ΔP/recovery stats, xsec | **275** |
| 5bps / i_c≥3 | Frag venue-share / thin-excess denser counts | 589 |
| 30bps / i_c≥10 | Strict ablation / Nanex-like severity | 56 |

Lib default: `severity_gate(..., min_dp_pct=0.10, min_i_c=5)`. Frag Pass-2 share tables also publish 5bps/ic3 — **both documented; primary Promote = 10bps/ic5**.

---

## 4. Headline numbers (hardened)

| Object | Value |
|--------|------:|
| Nanex→SSM precision (pooled) | **0.895** |
| Gated median ΔP / share_V @5s | see phase3a · **share_V≈0.77** |
| H^v mean (USD, 3-venue) | **0.482** |
| HL thin excess @5bps / @10bps | **0.78** / **0.79** |
| Concordance placebo p | ≈0.58 → Hold |
| Plain size OLS | **Kill** (sign-unstable) |

Bootstrap: n_boot=800, seed=41; early days ['2026-09-04', '2026-09-05', '2026-09-06']; late ['2026-09-07', '2026-09-08', '2026-09-09', '2026-09-10'].  
Artifact: [`out/phase4_hardening/hardening_gates.json`](out/phase4_hardening/hardening_gates.json).

---

## 5. Venue completeness (locked)

| Venue | Role | Notes |
|-------|------|-------|
| Hyperliquid | DEX anchor | Thin USD share; crash-dense |
| Deribit | CEX inverse perps | qty = USD |
| Kraken | CEX futures | Largest USD share on slice |

Panel: 42/42 complete cells · 14/14 day×symbol all-3 for Herfindahl.

---

## 6. Program status

**COMPLETE.** Optional backlog (not blocking): dense TOB for crossed NBBO; true OI; widen days/SOL for ex-ante xsec power.

**Next (applications):** board §7 · playbook [`TRADING_APPLICATIONS.md`](TRADING_APPLICATIONS.md) · catalog [`SIGNAL_CATALOG.md`](SIGNAL_CATALOG.md) · index [`applications/README.md`](applications/README.md).

---

## 7. Applications board (rollup)

Both tracks finished on the same gated panel (n=275, 10bps/ic5). **Class = risk-policy / MM playbook / feature / monitor — never naked tradable alpha.**  
Artifacts: [`applications/`](applications/) · board JSON [`applications/out/applications_board.json`](applications/out/applications_board.json) · index [`applications/README.md`](applications/README.md).

| Package | Class | Verdict | Headline | Path |
|---------|-------|---------|----------|------|
| **Strategy lab (tick/OB)** | **sim** | equity + overlays | Marked maker equity curves; kill-ladder / Nanex pull / V-restore / HL size-cap vs baseline; friction 2bps; cadence honesty · desk board maps Promote IDs → action → risk | [`applications/strategy_lab/`](applications/strategy_lab/) **← open for sims** |
| **Paper harness** | **risk-policy paper** | detect→ladder→shadow→daily report | Complete HL ETH UTC day; Promote IDs in `RISK_REPORT.md`; tape-proxy when BBO stale | [`applications/paper_harness/`](applications/paper_harness/) |
| Gated SSM kill-ladder | **risk-policy** | **Promote-as-risk-policy** | Δ\|mo\|@5s fire−observe **+6.54 bps** CI95 **[1.76, 10.40]**; friction 2bps cleared; time-split stable · IDs `risk.ssm_severity_gate_10bps` · `risk.ssm_zstar_scan_table` · `vol.sigma_m_noise_floor_1bp` | [`applications/kill_ladder/`](applications/kill_ladder/) |
| Nanex∩SSM nested auto-pull | **risk-policy** | **Promote-as-risk-policy** (+ burst tag) | prec **0.905**; nested Δ\|ΔP\| **+0.113%** CI **[0.075, 0.152]** · ID `info.nanex_subset_of_ssm` | [`applications/nanex_burst/`](applications/nanex_burst/) |
| HL thin-excess SOR | **monitor** | **Monitor / Hold as live size-cap** | crash share HL **0.829**; strip **yes**; hard size-cap **no** (Δ\|mo\| CI includes 0) | [`applications/hl_thin_sor/`](applications/hl_thin_sor/) |
| H^v / FEI capacity | **monitor** | **Monitor / Hold as schedule** | dashboard **yes**; qty cut on high-H clears; exposure CI does not; π-VWAP invariant | [`applications/hv_fei_capacity/`](applications/hv_fei_capacity/) |
| V-restore quoting | **MM playbook** | **Promote (med)** | class sep stable (V mo@5s ≈−16.5 / cont ≈+12.1); stay-wide / confirm-V beat blind restore on cont cost | [`applications/mm_quoting/`](applications/mm_quoting/) |
| `info.vpin_x_size_severity` | **feature** | **Promote (med)** | interact boot CI excludes 0 **[−0.137, −0.032]**; OOS t stable | [`applications/feature_models/`](applications/feature_models/) |
| Day-level crash occurrence | **feature** | **Soft Promote** | AUC_te≈**0.635**; severity \|ΔP\| still **Hold** (OOS R²\<0) | [`applications/feature_models/`](applications/feature_models/) |
| `exec.tape_markout_post_crash` | **feature** | **Hold** | mid_frac=0; tape mo@5s≈−11 bps — class-useful, not exec throttle | [`applications/feature_models/`](applications/feature_models/) |
| `risk.duration_post_markout` | **feature** | **Hold** | median Δt=0; OOS \|ρ\| vol-clock / i_c below bar | [`applications/feature_models/`](applications/feature_models/) |
| **Expanded lab** | **risk / MM / ops** | **see Survives** | Longer panel n=310 (+SOL 43); ladder+confirm best on **risk** scoreboard; Nanex prec≈0.90 extend; dense HL TOB ops | [`applications/expanded_lab/`](applications/expanded_lab/) |

**Survives (expanded_lab, honest):**
- **Promote-as-risk-policy:** kill-ladder on **core+extend** (Δ\|mo\|@5s ≈**+8.7** bps, friction+time-split OK) · Nanex∩SSM precision **≈0.90** stable on extend
- **Promote (med) MM playbook:** `ladder_plus_confirm_before_restore` ranks #1 on cont adverse / max DD / hole inventory; friction grid {0,1,2,4} rank-stable
- **Promote (ops):** denser HL collector TOB on 2026-09-29/30 (median Δt≈**0.55s** vs warehouse ~5s+; core days collector miss)
- **Hold (promising):** SOL kill-ladder (Deribit+Kraken, n=43) — friction clears, time-split underpowered
- **Hold:** occurrence (ex-ante H^v/hour/trades AUC_te≈0.65 but Brier not under base) · severity \|ΔP\| (no contemporaneous z)

**Wire as policy:** kill-ladder (venue-local) · Nanex∩SSM nested pull.  
**Wire as MM playbook (med):** V-confirm restore / stay-wide on continuation — prefer **ladder∩confirm** combined; not fade-the-V.  
**Wire as feature:** VPIN×size interact · soft occurrence regime score.  
**Dashboard only:** HL thin strip · H^v/FEI capacity.  

Ops constraints: do **not** use absolute z*∈{8,10,12} on gated tape — within-gated percentiles (p25/p50/p75 ≈ 12.5/15.9/20.4). Concordance Hold → kill-switches **venue-local**. HL SOL absent in warehouse → SOL robustness = DB+KR only.