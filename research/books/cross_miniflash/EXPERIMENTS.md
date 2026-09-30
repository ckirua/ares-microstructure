# Experiments ledger — Tee/Ting mini-flash crash program

**Purpose:** durable inventory of what was **tested vs not** under `research/books/cross_miniflash/`.  
**Honesty:** detection objects ≠ tradable alpha. Classes: risk monitor · risk-policy · MM playbook · feature · monitor · sim.  
**Data path:** warehouse trades + collector/warehouse TOB (HL + Deribit + Kraken). **ClickHouse MCP banned.**  
**SoT companions:** [`DESK_MEMO.md`](DESK_MEMO.md) · [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) · [`SIGNAL_CATALOG.md`](SIGNAL_CATALOG.md) · [`TRADING_APPLICATIONS.md`](TRADING_APPLICATIONS.md) · [`applications/README.md`](applications/README.md).

**Core research slice (Phase 2–4):** ETH+BTC · HL+Deribit+Kraken · UTC **2026-09-04…2026-09-10** · **42/42** complete cells · primary gate **10bps / i_c≥5** (n_gated=**275** from raw SSM z*=6 **3668**).  
**Phase 4 rollup:** **10 Promote / 13 Hold / 3 Kill** monitors — **0 naked tradable**.  
**Logged experiments in this file:** **30** (see §Index). Scaffold-only / future work lives in §NOT YET TESTED.

---

## Index (logged)

| ID | Layer | Short name | Verdict |
|----|-------|------------|---------|
| R01 | chapter | `ch00_overview` taxonomy | **Promote** `info.crash_def_taxonomy` |
| R02 | chapter | `crash_baselines` Nanex / V / outside-TOB | Nanex⊂SSM **Promote**; 80bps **Kill**; outside-TOB **Hold** |
| R03 | chapter | `mc_garch_vol` σ_m / diurnal | σ_m floor **Promote**; diurnal **Hold** |
| R04 | chapter | `kalman_ssm` KF + z* scan | z* menu **Promote**; binary/innov **Hold** |
| R05 | chapter | `crash_stats` severity / recovery / markout | severity gate + V/cont **Promote**; tape/duration **Hold** |
| R06 | chapter | `cross_section` size / VPIN / Amihud | size **Kill**; Amihud **Hold**; VPIN interact → apps |
| R07 | chapter | `frag_xvenue` H^v / FEI / thin / concord | H^v/FEI/thin/share **Promote**; concord/Epps/crossed **Hold** |
| R08 | hardening | Phase 4 bootstrap / time-split freeze | board freeze 10/13/3 |
| A01 | app | kill-ladder aggressor clip | **Promote-as-risk-policy** |
| A02 | app | Nanex∩SSM nested pull | **Promote-as-risk-policy** |
| A03 | app | HL thin SOR size-cap | **Monitor** strip / hard cap **Hold** |
| A04 | app | H^v / FEI capacity POV | **Monitor** dashboard / schedule **Hold** |
| A05 | app | V-restore MM quoting | **Promote (med)** playbook |
| A06 | app | feature models (occurrence / severity / Holds) | occurrence **Soft Promote**; VPIN×size **Promote (med)**; tape/duration **Hold** |
| A07 | app | expanded_lab panel+SOL+scoreboard | kill/Nanex robust; ladder∩confirm best risk; SOL **Hold** |
| A08 | app | strategy_lab tick/OB equity | overlays vs baseline **Hold** as PnL; policy still stands |
| A09 | app | paper_harness HL ETH day shadow | wired shadow days; **not** live |
| A10 | app | long_range_lab multi-day HL ETH | 27-day equity paths; Δ vs baseline CI soft |
| A11 | app | signal_boards MI / stats / Bayes | research boards (not production Bayes) |
| A12 | app | paper_live continuous shadow loop | **tested** continuous poll + `tail -f` log; **systemd user unit** `ares-paper-live.service`; pins **A13** event+wall_60s; **not** live orders |
| A13 | app | horizon_lab sampling clocks (300/9000) | event+wall_60s **Promote** → **A12** paper_live defaults; trade_last_300/9000 detect **Kill**; intensity trade_300–3000 **Promote** |
| E01 | edge | TI-v-fade causal | **Promote** (research_sim; mid_mo null) |
| E02 | edge | TI-cont-ride causal | **Kill** |
| E03 | edge | TI-int-halt | **Promote** risk-policy |
| E04 | edge | TI-nanex-nest (+ deep join) | **Promote** risk-policy |
| E05 | edge | friction kill-grid | fade/halt survive ≥1bp; causal cont-ride dies |
| P4S | catalog | Phase-4 signal board (26 IDs) | see compact table §P4S |

---

## Shared panel / gates

| Item | Value |
|------|------:|
| Venues | Hyperliquid · Deribit · Kraken |
| Symbols (core) | ETH, BTC |
| Days (core) | 2026-09-04 … 2026-09-10 |
| Raw SSM z*=6 | 3668 |
| Gate 5bps/ic3 | 589 |
| Gate **10bps/ic5 (primary)** | **275** |
| Gate 30bps/ic10 | 56 |
| Nanex 30bps | 105 |
| Nanex 80bps (paper) | 8 → **Kill** |
| Bootstrap | n_boot=800, seed=41 (Phase 4) |
| Early / late | Sep4–6 / Sep7–10 |
| Lib | [`../../lib/crash.py`](../../lib/crash.py) |
| App panel cache | `applications/out/event_panel/` · `mm_quoting/out/panel_cache.json` |

---

## R01 — `ch00_overview` (taxonomy map)

| Field | Content |
|-------|---------|
| **Hypothesis** | Five crash defs map to desk classes (burst / outlier / stale / V-hole / continuation); Nanex nests in SSM. |
| **Data** | HL+DB+KR · ETH+BTC · 2026-09-04…10 · 42/42 cells |
| **Method** | Count Nanex 30bps vs SSM z*=6 vs V-shape; Jaccard / precision overlap. |
| **Key result** | Nanex 105 · SSM 3668 · V 132; Nanex→SSM precision ≈0.90; paper 80bps n=8. |
| **Verdict** | **Promote** `info.crash_def_taxonomy` |
| **Artifacts** | [`chapters/ch00_overview/EXP_REPORT.md`](chapters/ch00_overview/EXP_REPORT.md) · [`out/phase2_baselines_ssm/`](out/phase2_baselines_ssm/) |
| **Gaps** | Outside-TOB needs dense TOB; taxonomy not a numeric alpha claim. |

---

## R02 — `crash_baselines`

| Field | Content |
|-------|---------|
| **Hypothesis** | Nanex / V-shape / outside-TOB are operational detectors on crypto ms tape; Nanex is high-precision SSM subset. |
| **Data** | Same core slice; outside-TOB smoke on Deribit warehouse L2 (09-05/06). |
| **Method** | `nanex_detect` θ∈{30,80}bps; V-shape; asof outside-[b,a]; tox/VPIN around events. |
| **Key result** | Overlap n_ov=94/105; prec=0.895; outside_rate Deribit 0.79/0.15; VPIN day≈0.736. |
| **Verdict** | **Promote** `info.nanex_subset_of_ssm` · **Hold** `base.nanex_crypto_30bps` standalone · **Kill** `base.nanex_paper_80bps` · **Hold** `exec.outside_tob_wh_l2` |
| **Artifacts** | [`chapters/crash_baselines/EXP_REPORT.md`](chapters/crash_baselines/EXP_REPORT.md) · `out/phase2_baselines_ssm/` |
| **Gaps** | Dense multi-venue collector TOB on core days; θ grid multi-week + SOL. |

---

## R03 — `mc_garch_vol`

| Field | Content |
|-------|---------|
| **Hypothesis** | MC-GARCH diurnal \(s_j\) + σ_m floor feed KF; crypto needs ~1bp measurement floor. |
| **Data** | Same 42 cells; 5m UTC diurnal. |
| **Method** | Per-cell MC-GARCH path; σ_m frac stress {0.5,1,2,4}; link vs mmip `vol.curve_intraday`. |
| **Key result** | Peak UTC-**12** this cohort; σ_m stress n_SSM 13832/3668/808/177; mmip peak ~18 elsewhere. |
| **Verdict** | **Promote** `vol.sigma_m_noise_floor_1bp` · **Hold** `vol.mc_garch_sj_utc` · **Hold** `vol.curve_intraday_link` |
| **Artifacts** | [`chapters/mc_garch_vol/EXP_REPORT.md`](chapters/mc_garch_vol/EXP_REPORT.md) · `out/phase2_baselines_ssm/figs/` |
| **Gaps** | Joint multi-book diurnal panel; longer calendar for peak CI. |

---

## R04 — `kalman_ssm`

| Field | Content |
|-------|---------|
| **Hypothesis** | Paper KF + z*=6 flags mini-crashes; z* menu + standardized innov are the desk objects. |
| **Data** | Same core slice; σ_m_frac=1 · floor 1e-4. |
| **Method** | KF on trade tape; z* scan 2…12; innov→future Δlog lead–lag. |
| **Key result** | n(z*=6)=3668; scan monotone; \|corr\| innov lead ≤0.04. |
| **Verdict** | **Promote** `risk.ssm_zstar_scan_table` · **Hold** `risk.ssm_z6_binary` · **Hold** `info.ssm_innov_continuous` · **Kill** ungated vanity |
| **Artifacts** | [`chapters/kalman_ssm/EXP_REPORT.md`](chapters/kalman_ssm/EXP_REPORT.md) |
| **Gaps** | Severity filter (owned by R05); never use absolute z∈{8,10,12} on gated crypto tape — use within-gated percentiles. |

---

## R05 — `crash_stats`

| Field | Content |
|-------|---------|
| **Hypothesis** | Severity gate makes SSM intensity informative; recovery@5s separates V-hole vs continuation; post markout / duration carry exec info. |
| **Data** | Same panel · gated n=275 (HL 228 / DB 21 / KR 26). |
| **Method** | `severity_gate`; recovery class; tape mo@{0.5,1,5}s; Spearman(Δt,\|mo\|); placebo ends. |
| **Key result** | med ΔP≈0.177%; share_V≈77%; mo@5s≈−7bps (phase3a cells); Spearman(dt)≈−0.28 but med Δt=0. |
| **Verdict** | **Promote** `risk.ssm_severity_gate_10bps` · **Promote** `info.crash_v_vs_continuation` · **Hold** tape markout / duration · **Kill** `risk.ssm_raw_ungated_counts` |
| **Artifacts** | [`chapters/crash_stats/EXP_REPORT.md`](chapters/crash_stats/EXP_REPORT.md) · [`out/phase3a_stats_xsec/`](out/phase3a_stats_xsec/) |
| **Gaps** | Dense mid markout (Kraken tob_cells=0); volume-clock duration OOS. |

---

## R06 — `cross_section`

| Field | Content |
|-------|---------|
| **Hypothesis** | Paper: larger / cheaper names → smaller % crashes (MCap path). Crypto proxies: log notional, VPIN×size, Amihud. |
| **Data** | Gated n=275; ex-ante lag-1 n_pred=20. |
| **Method** | Quintiles + NW-OLS; VPIN interact; time-split β(logN). |
| **Key result** | Plain size R²≈0.02; early/late β **sign flip**; Amihud t≈−2.5 underpowered; VPIN interact in-sample fragile → apps denser Promote. |
| **Verdict** | **Kill** `xsec.size_reduces_severity` · **Hold** `risk.exante_amihud_severity` · VPIN×size → **A06 Promote (med)** |
| **Artifacts** | [`chapters/cross_section/EXP_REPORT.md`](chapters/cross_section/EXP_REPORT.md) · `out/phase3a_stats_xsec/` |
| **Gaps** | True OI; multi-week + SOL power for Amihud; do not use plain size for budgets. |

---

## R07 — `frag_xvenue`

| Field | Content |
|-------|---------|
| **Hypothesis** | 3-venue H^v / FEI measure capacity; thin venue (HL) is crash-dense; crashes co-fire across venues. |
| **Data** | Complete all-3 day×symbol **14/14**; vol shares HL≈4% / DB≈36% / KR≈60%. |
| **Method** | Herfindahl + FEI; gated crash share / thin excess; Jaccard±5s + placebo; Epps day vs crash; crossed NBBO if TOB. |
| **Key result** | H^v≈0.482; FEI≈0.75; HL crash share@10bps≈0.83; thin excess@5bps≈0.73; Jaccard HL–DB/KR=0; placebo p≈0.58; n_crossed=0. |
| **Verdict** | **Promote** H^v · FEI · crash_venue_share · thin_excess · **Hold** concordance · Epps crashwin · crossed_nbbo_crashwin |
| **Artifacts** | [`chapters/frag_xvenue/EXP_REPORT.md`](chapters/frag_xvenue/EXP_REPORT.md) · [`out/frag_xvenue/`](out/frag_xvenue/) |
| **Gaps** | Dense multi-venue TOB for crossed; concordance as *negative* product (venue-local kills) documented but not productized automation. |

---

## R08 — Phase 4 hardening

| Field | Content |
|-------|---------|
| **Hypothesis** | Every Promote survives bootstrap CI + early/late split; Kill vanity metrics. |
| **Data** | Same core slice; n_boot=800 seed=41. |
| **Method** | Re-gate candidates; cell bootstrap; time-split; freeze DESK_MEMO board. |
| **Key result** | **10 Promote / 13 Hold / 3 Kill**; primary gate 10bps/ic5 locked; frag also publishes 5bps/ic3. |
| **Verdict** | Program **COMPLETE (Phase 4 hardened)** — applications are post-board. |
| **Artifacts** | [`out/phase4_hardening/hardening_REPORT.md`](out/phase4_hardening/hardening_REPORT.md) · [`hardening_gates.json`](out/phase4_hardening/hardening_gates.json) · [`DESK_MEMO.md`](DESK_MEMO.md) |
| **Gaps** | Dense TOB; true OI; widen days/SOL for ex-ante xsec (backlog, non-blocking). |

---

## P4S — Phase-4 signal board (compact)

Full per-signal depth: [`SIGNAL_CATALOG.md`](SIGNAL_CATALOG.md). Decisions from [`out/phase4_hardening/hardening_REPORT.md`](out/phase4_hardening/hardening_REPORT.md) (+ apps flips noted).

| ID | Verdict | One-line |
|----|---------|----------|
| `risk.ssm_severity_gate_10bps` | **Promote** | Ablation 3668→589→275→56 |
| `risk.ssm_zstar_scan_table` | **Promote** | Monotone z* menu |
| `vol.sigma_m_noise_floor_1bp` | **Promote** | Required KF floor |
| `info.crash_def_taxonomy` | **Promote** | Framing labels |
| `info.nanex_subset_of_ssm` | **Promote** | prec≈0.895 |
| `info.crash_v_vs_continuation` | **Promote** | share_V≈0.77 |
| `frag.volume_herfindahl_3venue` | **Promote** | H^v≈0.48 |
| `frag.fei_volume_3venue` | **Promote** | FEI≈0.75 |
| `frag.crash_venue_share` | **Promote** | HL share≈0.83 |
| `frag.thin_venue_crash_excess` | **Promote** | HL excess≈0.78 |
| `info.vpin_x_size_severity` | **Hold→Promote(med) feature** (A06) | Phase-4 Hold; apps CI excludes 0 |
| `base.nanex_crypto_30bps` | **Hold** | Nest-required only |
| `risk.ssm_z6_binary` | **Hold** | Raw median ΔP≈0 |
| `info.ssm_innov_continuous` | **Hold** | \|corr\|≈0.04 |
| `exec.outside_tob_wh_l2` | **Hold** | Sparse L2 |
| `exec.tape_markout_post_crash` | **Hold** | mid_frac=0 |
| `risk.duration_post_markout` | **Hold** | med Δt=0 |
| `risk.exante_amihud_severity` | **Hold** | n=20 |
| `frag.xvenue_crash_concord` | **Hold** | placebo≈0.58 |
| `frag.crossed_nbbo_crashwin` | **Hold** | n_crossed=0 |
| `epps.crash_window_corr` | **Hold** | Not < day Epps |
| `vol.mc_garch_sj_utc` | **Hold** | Prior only |
| `vol.curve_intraday_link` | **Hold** | Peak mismatch |
| `base.nanex_paper_80bps` | **Kill** | n=8 |
| `risk.ssm_raw_ungated_counts` | **Kill** | Vanity intensity |
| `xsec.size_reduces_severity` | **Kill** | Sign-unstable |

---

## A01 — kill-ladder (risk-policy)

| Field | Content |
|-------|---------|
| **Hypothesis** | Within-gated z percentiles + intensity + Nanex nest → observe→widen→size_cap→halt; fire tiers have higher adverse \|mo\|@5s than observe. |
| **Data** | Core gated n=275 · tiers observe45 / widen105 / size_cap37 / halt88 · fire n=230 |
| **Method** | Event-study Δ\|mo\| fire−observe; friction 2bps; early/late; placebo random windows. |
| **Key result** | Δ\|mo\|@5s **+6.54 bps** CI **[1.76, 10.40]**; friction cleared; time-split stable; V-share among fire≈0.78 (FP halt cost). |
| **Verdict** | **Promote-as-risk-policy** |
| **Artifacts** | [`applications/kill_ladder/EXP_REPORT.md`](applications/kill_ladder/EXP_REPORT.md) · [`applications/out/kill_ladder/`](applications/out/kill_ladder/) |
| **Gaps** | Absolute z∈{8,10,12} collapses — use p25/p50/p75 ≈12.5/15.9/20.4; venue-local only (concordance Hold). |

---

## A02 — Nanex∩SSM nested auto-pull

| Field | Content |
|-------|---------|
| **Hypothesis** | Nested Nanex∩SSM is higher-severity escalate vs SSM-only; nested pause beats blanket pause-all-SSM. |
| **Data** | n_nested=67 / SSM-only=208 · precision=0.905 |
| **Method** | Nest vs non Δ\|ΔP\| and Δ\|mo\|; placebo bare-Nanex; policy nest_hard vs soft. |
| **Key result** | Δ\|ΔP\| **+0.113%** CI[0.075,0.152]; Δ\|mo\| **+5.11 bps**; time-split stable. |
| **Verdict** | **Promote-as-risk-policy** (+ burst tag) |
| **Artifacts** | [`applications/nanex_burst/EXP_REPORT.md`](applications/nanex_burst/EXP_REPORT.md) · [`applications/out/nanex_burst/`](applications/out/nanex_burst/) · deep join [`edge_lab/nanex_nest/out/EXP_REPORT.md`](applications/edge_lab/nanex_nest/out/EXP_REPORT.md) |
| **Gaps** | Do not fire Nanex alone; θ multi-week OOS. |

---

## A03 — HL thin SOR

| Field | Content |
|-------|---------|
| **Hypothesis** | When HL thin-excess + intensity fire, hard size-cap on HL aggressive improves adverse markout vs thick legs. |
| **Data** | HL crash share 0.829; thin excess point 0.62 CI[0.44,0.77]; n fire/quiet/thick 219/9/47 |
| **Method** | Co-fire rule; HL fire−thick Δ\|mo\|; size-mult sketch (not POV fills). |
| **Key result** | Δ\|mo\| fire−thick CI **includes 0**; time-split **unstable**. |
| **Verdict** | **Monitor / Promote strip** · hard size-cap **Hold** |
| **Artifacts** | [`applications/hl_thin_sor/EXP_REPORT.md`](applications/hl_thin_sor/EXP_REPORT.md) · [`applications/out/hl_thin_sor/`](applications/out/hl_thin_sor/) |
| **Gaps** | Matched fill SOR backtest; calibrated POV; multi-week thin excess. |

---

## A04 — H^v / FEI capacity

| Field | Content |
|-------|---------|
| **Hypothesis** | High H^v / low FEI → shrink POV child on thin leg / cut exposure in crash windows. |
| **Data** | 14 complete cells; H^v≈0.482; FEI≈0.75 |
| **Method** | Spearman(H,\|mo\|); quartile severity; POV sched vs flat (`simulate_pov_child`, instant fill @ trade px). |
| **Key result** | Spearman unstable; high-H qty Δ **−0.34** CI clears; exposure cut CI does **not**; π-VWAP invariant. |
| **Verdict** | **Monitor** dashboard **yes** · executable schedule **Hold** |
| **Artifacts** | [`applications/hv_fei_capacity/EXP_REPORT.md`](applications/hv_fei_capacity/EXP_REPORT.md) · [`applications/out/hv_fei_capacity/`](applications/out/hv_fei_capacity/) |
| **Gaps** | Self-impact feedback; binding max_child under real latency; TCA by FEI quartile live. |

---

## A05 — V-restore MM quoting

| Field | Content |
|-------|---------|
| **Hypothesis** | After crash, restore size only on V-confirm; stay wide on continuation (not blind restore; not fade alpha). |
| **Data** | n=275 · share_V=0.771 · V mo@5s≈−16.5 · cont≈+12.1 |
| **Method** | Policy sims: always_stay_wide / always_restore / confirm_v / confirm_before_restore / cont_protect; rank on cont adverse cost. |
| **Key result** | Stay-wide / confirm / cont_protect beat blind restore on cont cost both cohorts; best excl. oracle = `always_stay_wide`. |
| **Verdict** | **Promote (med)** MM playbook — **not** fade-the-V tradable |
| **Artifacts** | [`applications/mm_quoting/EXP_REPORT.md`](applications/mm_quoting/EXP_REPORT.md) · [`out/RISK_REPORT.md`](applications/mm_quoting/out/RISK_REPORT.md) · notebook `v_continuation_quoting.ipynb` |
| **Gaps** | Mid markout sparse (tape ceiling); fade alpha **low** until mid_mo Promote; event-study only (tick equity → A08/A09). |

---

## A06 — feature models

| Field | Content |
|-------|---------|
| **Hypothesis** | Ex-ante features predict day-level crash occurrence and/or event \|ΔP\|; denser Hold→Promote for tape mo, duration, VPIN×size. |
| **Data** | n_events=275 · occurrence cells 84 (train/test 50/34) |
| **Method** | Logistic occurrence; Ridge severity; NW-OLS VPIN×logN; checks on tape mo / duration. |
| **Key result** | Occurrence AUC_te≈**0.635** Soft Promote; severity OOS R²\<0 **Hold**; VPIN interact CI **[−0.137,−0.032]** **Promote (med)**; tape mo mid_frac=0 **Hold**; duration OOS \|ρ\| below bar **Hold**. |
| **Verdict** | Mixed — see sub-rows |
| **Artifacts** | [`applications/feature_models/EXP_REPORT.md`](applications/feature_models/EXP_REPORT.md) · `applications/feature_models/out/` |
| **Gaps** | Severity model needs non-leak features + power; mid markout; volume-clock duration. |

---

## A07 — expanded_lab

| Field | Content |
|-------|---------|
| **Hypothesis** | Core Promotes survive Sep1–3 extend + SOL (DB+KR); combined ladder∩confirm beats single stubs on risk scoreboard; denser collector TOB improves book honesty. |
| **Data** | core n=275 · core+extend=310 · SOL=43 · all=353 · days Sep1–10 · symbols BTC/ETH/SOL |
| **Method** | Own panel cache (does not overwrite `applications/out/event_panel`); kill/Nanex robustness; strategy risk scoreboard @2bps; occurrence/severity; book cadence compare Sep29/30. |
| **Key result** | Core+extend Δ\|mo\|≈**+8.7 bps** Promote-as-risk-policy; Nanex prec≈0.90; best strategy **`ladder_plus_confirm_before_restore`**; SOL kill-ladder **Hold (promising)**; collector median Δt≈0.55s vs warehouse ~5s+ on dense days (core collector hits=0). |
| **Verdict** | **Promote-as-risk-policy** kill/Nanex on extend · **Promote (med)** ladder∩confirm · **Promote (ops)** dense TOB marking · SOL / occurrence / severity **Hold** |
| **Artifacts** | [`applications/expanded_lab/EXP_REPORT.md`](applications/expanded_lab/EXP_REPORT.md) · [`out/figs/`](applications/expanded_lab/out/figs/) · [`README.md`](applications/expanded_lab/README.md) |
| **Gaps** | HL SOL empty in warehouse; core-day dense TOB miss; occurrence Brier not under base on expand. |

---

## A08 — strategy_lab (tick/OB equity)

| Field | Content |
|-------|---------|
| **Hypothesis** | Marked maker equity with kill-ladder / Nanex pull / V-restore / HL size-cap overlays beats baseline on same cells. |
| **Data** | Phase-4 days · ETH+BTC · n_cells_ok=26 · friction 2bps |
| **Method** | Trade-tape clock; book = collector TOB else warehouse L2/BBO; fill @ trade print + `fill_i`. |
| **Key result** | Δ vs baseline CIs **include 0** for kill_ladder / nanex / v_restore / hl_thin (e.g. kill_ladder Δ≈−8.6 CI[−33,12]); book mostly warehouse/tape_proxy. |
| **Verdict** | Sims **Hold as live PnL** · desk still treats event-study Promotes as **policy** (not alpha) |
| **Artifacts** | [`applications/strategy_lab/STRATEGY_LAB.md`](applications/strategy_lab/STRATEGY_LAB.md) · [`out/summary.json`](applications/strategy_lab/out/summary.json) · `strategy_lab.ipynb` · `out/figs/` |
| **Gaps** | Sub-second queue-position claims invalid on warehouse cadence; denser TOB required for equity Promote. |

---

## A09 — paper_harness (HL ETH day shadow)

| Field | Content |
|-------|---------|
| **Hypothesis** | Detect→ladder→shadow maker→daily RISK_REPORT is operable on warehouse days without live orders. |
| **Data** | HL ETH days 2026-09-04…10 (7/7 ok); optional DB/KR detect extras |
| **Method** | `run_paper_day.py`; shared ladder; tape-proxy fills when BBO stale; max_inventory research soft-cap=10. |
| **Key result** | Rollup: gated/fire **173/139**; mean Δ equity ~296 bps (risk-policy label, not alpha); frac nullified=0; tape-proxy used when stale. |
| **Verdict** | **Wired shadow** · class=risk-policy paper · **live orders never** · startarb `shadow_live` / mercat **not wired** |
| **Artifacts** | [`applications/paper_harness/README.md`](applications/paper_harness/README.md) · [`out/RISK_ROLLUP.md`](applications/paper_harness/out/RISK_ROLLUP.md) · `out/<day>_hyperliquid_ETH/` |
| **Gaps** | OE fill realism; continuous collector TOB on Phase-4 days. Continuous loop → **A12 paper_live**. |

---

## A10 — long_range_lab

| Field | Content |
|-------|---------|
| **Hypothesis** | Kill-ladder / Nanex / ladder∩confirm overlays improve multi-day HL ETH equity / DD vs baseline maker on longest clean PIN-usable panel. |
| **Data** | HL ETH · **27** included days spanning **2026-08-28…2026-09-30** (gaps in calendar); friction 2bps |
| **Method** | Reuse expanded panel events when available else `paper_harness.detect_day`; same fill model as strategy_lab. |
| **Key result** | Fire scoreboard n_fire=199 · Δ adverse mo5≈+9.6 bps; overlay Δ vs baseline CIs soft (e.g. kill_ladder Δ≈+14 CI includes 0); heavy late-panel equity bleed on baseline path. |
| **Verdict** | **Hold as equity alpha** · risk overlays still policy-class; cadence honesty: median book Δt≈5.4s |
| **Artifacts** | [`applications/long_range_lab/README.md`](applications/long_range_lab/README.md) · [`out/summary.json`](applications/long_range_lab/out/summary.json) · `out/coverage.json` · `long_range_strategies.ipynb` |
| **Gaps** | BTC optional not in this run (ETH only); denser TOB; SOL multi-week. Continuous shadow loop → **A12**. |

---

## A11 — signal_boards

| Field | Content |
|-------|---------|
| **Hypothesis** | Desk-quality boards (MI, bootstrap/ROC, Bayesian PPC) clarify Promote features without claiming production Bayes. |
| **Data** | Gated n=275 panel_cache + event_panel |
| **Method** | `exp_signal_boards.py`; Beta–Binomial V-rate; MH logistic occurrence; conjugate/MH (PyMC/numpyro **not** installed). |
| **Key result** | Figs under `applications/out/signal_boards/figs/`; boards are research viz. |
| **Verdict** | **Research monitor** · Bayesian **not production** |
| **Artifacts** | [`applications/signal_boards/README.md`](applications/signal_boards/README.md) · [`notebooks/full_research_board.ipynb`](notebooks/full_research_board.ipynb) · `applications/out/signal_boards/` |
| **Gaps** | Bayesian production stack; joint panel refresh automation. |

---

## A12 — paper_live (continuous shadow loop)

| Field | Content |
|-------|---------|
| **Hypothesis** | Rolling detect→ladder→shadow→RISK_REPORT can run as a continuous poll loop with `tail -f` logging, without live orders. |
| **Data** | HL ETH UTC **2026-09-30** smoke · warehouse trade tape (S3→cache) · collector TOB present (`xarb_md/tob/20260930`, median Δt≈0.54s) |
| **Method** | `applications/paper_live/run_paper_live.py --iterations 2 --interval 2 --figs`; reuses paper_harness detect/ladder/shadow/report; poll refreshes warehouse listing; append `actions.jsonl` (`shadow_fills_summary` + `poll_tick`); heartbeat when tape unchanged. Continuous ops via user systemd `~/.config/systemd/user/ares-paper-live.service` (`--poll --interval 10`). |
| **Key result** | Poll0: trades≈150k · gated(10bps·ic5)=**0** that tip · shadow fills≈53k @ trade print (`warehouse_asof`) · warehouse_lag≈**26s** · collector=True · RISK_REPORT written. Poll1: **heartbeat** (no new tape). Log flushes each record. |
| **Verdict** | **Tested continuous shadow** · class=risk-policy paper-live · **live orders never** · mercat/gateway OE **not used** · runnable as **systemd user service** |
| **Artifacts** | [`applications/paper_live/README.md`](applications/paper_live/README.md) · `~/.config/systemd/user/ares-paper-live.service` · [`logs/paper_live.log`](applications/paper_live/logs/paper_live.log) · `out/<day>_hyperliquid_ETH/{RISK_REPORT.md,actions.jsonl,summary.json}` |
| **Gaps** | Live order submission still **not** tested (and refused). Warehouse tape still lags exchange; gated fires depend on day severity. startarb `shadow_live` (pairs z-fade) is a different lane. |
| **Cross-link** | Horizon defaults from **[A13](#a13--horizon_lab-sampling-clocks--300--9000-ticks)**: `detection_clock: event` + `intensity_clock: wall_60s` pinned in `applications/paper_live/config.yaml` (refuse `trade_last_*` detect). |

---

## A13 — horizon_lab (sampling clocks / 300 & 9000 ticks)

| Field | Content |
|-------|---------|
| **Hypothesis** | Mini-flash SSM + kill-ladder remain useful at medium/HFT sampling sizes (trade-count N∈{100,300,900,3000,9000}, calendar 1s/5s/1m, volume clocks) vs pure event-time; optimal horizon may shift with Amihud / diurnal liquidity. |
| **Data** | HL ETH · **27** PIN-usable days spanning **2026-08-28…2026-09-30** (1 incomplete skip) · warehouse trade tape via `_data.py` |
| **Method** | Resample clocks → SSM z*=6 + gate 10bps/ic≥1 on bars (ic≥5 on event) → ladder tiers; markout always on full tape; bootstrap Δ\|mo\| fire−obs + early/late; separate **policy intensity** sweep on fixed event detection (wall + trade-count windows). |
| **Key result** | Event gated/day≈**9.0** · Δ\|mo\|≈**+9.6** CI[6.1,13.5] **Promote**. `trade_last_300` (~202s) / `9000` (~2704s) gated/day=**0** **Kill** for detection. Intensity `wall_60s` + `trade_300`…`trade_3000` **Promote**; `trade_9000` intensity **Hold**. `cal_1s` ~3.1/day Hold. Amihud-high days denser crashes but trade_300 detection stays 0 — horizon does **not** shift into MFT bars. |
| **Verdict** | **Promote** event + wall_60s (paper default) · **Promote** intensity trade_300–3000 as MFT alts · **Kill** trade_last_300/9000 as SSM observation clocks · **Hold** cal_1s research robustness |
| **Artifacts** | [`applications/horizon_lab/HORIZON_RECOMMENDATION.md`](applications/horizon_lab/HORIZON_RECOMMENDATION.md) · [`out/EXP_REPORT.md`](applications/horizon_lab/out/EXP_REPORT.md) · `horizon_lab.ipynb` · `out/figs/` |
| **Gaps** | FEI×horizon (3-venue day panel not rebuilt); xarb tick-bar PnL is a separate startarb lane; dense ms TOB decision path; BTC/SOL clocks. |
| **Cross-link** | Applied to **[A12](#a12--paper_live-continuous-shadow-loop)** `paper_live` config/README (`event` detect + `wall_60s` intensity; MFT trade_N intensity optional, not detect). |

---

## E01 — TI-v-fade (causal)

| Field | Content |
|-------|---------|
| **Hypothesis** | Fade only V-holes after recovery@2s confirm; capture rebound vs crash direction after RT friction. |
| **Data** | n=275 panel; causal v_recovery n=117 |
| **Method** | Class-conditioned taker sim; net after RT=4bps; early/late; oracle@5s upper bound. |
| **Key result** | Causal fade-only net **+11.63 bps** CI[7.67,15.91]; friction cleared; time-split stable. |
| **Verdict** | **Promote (research_sim)** — **mid_mo null** → not naked live alpha |
| **Artifacts** | [`applications/edge_lab/out/EXP_REPORT.md`](applications/edge_lab/out/EXP_REPORT.md) · [`EDGE_LAB.md`](applications/edge_lab/EDGE_LAB.md) · [`TRADE_IDEAS.md`](applications/TRADE_IDEAS.md) |
| **Gaps** | Mid/mark markout; fill realism vs OE; live / paper continuous. |

---

## E02 — TI-cont-ride (causal)

| Field | Content |
|-------|---------|
| **Hypothesis** | On continuation, ride crash sign short-horizon instead of fade. |
| **Data** | Causal continuation n=64 |
| **Method** | Same taker sim / friction / splits as E01. |
| **Key result** | Causal ride-only net **−2.83 bps** CI includes 0; oracle@5s still green (look-ahead). |
| **Verdict** | **Kill** (causal) |
| **Artifacts** | `applications/edge_lab/out/EXP_REPORT.md` |
| **Gaps** | None for causal rule — do not revive without new ID/data. |

---

## E03 — TI-int-halt

| Field | Content |
|-------|---------|
| **Hypothesis** | Clip aggressor when ladder fire tiers (widen+) vs observe — same object as A01, edge-lab scoreboard. |
| **Data** | n_fire≈226 from event_panel tiers |
| **Method** | Δ\|mo\| fire−obs; RT friction; time-split. |
| **Key result** | Δ\|mo\| **+6.54** CI[2.17,10.68]; Promote. |
| **Verdict** | **Promote** risk-policy (aggressor clip) |
| **Artifacts** | `applications/edge_lab/out/EXP_REPORT.md` |
| **Gaps** | Same as A01. |

---

## E04 — TI-nanex-nest

| Field | Content |
|-------|---------|
| **Hypothesis** | Nest bit escalates pause vs SSM-only (joins event_panel; not on panel_cache alone). |
| **Data** | n_nest=66 · joined 275/275 |
| **Method** | Edge scoreboard + deep join package `edge_lab/nanex_nest`. |
| **Key result** | Δ\|mo\| nest−non **+5.11**; nest_hard preferred; OOS expanded Δ\|mo\|≈+9.26. |
| **Verdict** | **Promote** risk-policy |
| **Artifacts** | `edge_lab/out/EXP_REPORT.md` · [`edge_lab/nanex_nest/out/EXP_REPORT.md`](applications/edge_lab/nanex_nest/out/EXP_REPORT.md) |
| **Gaps** | Same as A02. |

---

## E05 — friction kill-grid

| Field | Content |
|-------|---------|
| **Hypothesis** | Top ideas survive ≥1bp half-spread haircut. |
| **Data** | n=275 panel_cache + event_panel tiers |
| **Method** | Grid half-spread {0,0.5,1,2,5}bps; oracle primary; causal aux. |
| **Key result** | Survive@1bp: TI-v-fade, TI-cont-ride (oracle), TI-int-halt; causal cont-ride **DIE** all costs; fade max half-spread 5bps. |
| **Verdict** | Cost falsifier **pass** for fade/halt; causal ride dead |
| **Artifacts** | [`applications/edge_lab/friction/FRICTION_REPORT.md`](applications/edge_lab/friction/FRICTION_REPORT.md) · `friction/out/` |
| **Gaps** | Venue-fee realism; maker/taker asymmetric fees. |

---

## NOT YET TESTED / FUTURE EXPAND

| Item | Status on disk | Notes |
|------|----------------|-------|
| **Live order submission** | Explicitly **never** | paper_live / paper_harness / mm_quoting / edge_lab `live_orders=False`. mercat / gateway path unused. **Keep here until deliberately tested (do not).** |
| **startarb `shadow_live` / xarb poll** | **Not wired** into crash package | Different alpha lane (1m z-fade ETH HL↔Lit/RX); crash `paper_live` is risk-policy overlay only. |
| **Xarb N-tick bar sim (300/9000 TOB)** | Plan only | [`xarb_tick_horizons` plan](~/.cursor/plans/xarb_tick_horizons_ad2ad769.plan.md) — cross-ex pairs lane; **not** the crash SSM horizon_lab (A13). A13 kills trade-count bars for *crash detection*; xarb may still differ. |
| **X-venue lag taker (`edge_lab/xvenue_lag`)** | Partial / run if EXP present | Package under `applications/edge_lab/xvenue_lag/`; concordance Hold is the enabler hypothesis — confirm `out/EXP_REPORT.md` before Promote claims. |
| **Denser ms TOB on Phase-4 core days** | Partial | Collector denser on **2026-09-29/30** only; core Sep4–10 collector hits=**0** → warehouse BBO/l2_rebuild. Blocks outside-TOB / crossed_nbbo_crashwin / mid_mo Promote. |
| **Hard SOR size-cap (HL thin)** | Tested → **Hold** | CI includes 0 (A03); needs matched fills / longer panel. |
| **H^v/FEI executable child schedule** | Tested → **Hold** | Qty cut clears; exposure CI does not (A04). |
| **FEI × detection-horizon interaction** | **Not tested** | A13 liquidity slice uses Amihud/activity; 3-venue FEI day panel not crossed with clocks. |
| **Fade alpha as live/tradable** | Research_sim only | E01 Promote research; mid_mo null; A05 explicitly **not** fade. |
| **Bayesian production** | Not installed | Conjugate + MH boards only; no PyMC/numpyro production path. |
| **Multi-week SOL (3-venue)** | Partial | SOL n=43 on **Deribit+Kraken only** (HL SOL empty); kill-ladder **Hold promising**. No multi-week 3-venue SOL. |
| **BTC / multi-coin horizon_lab** | ETH-only in A13 | Same clocks not swept on BTC/SOL. |
| **BTC in long_range_lab** | Optional flag unused in logged run | Summary symbols=`['ETH']` only. |
| **Other coins / venues** | Not run | Lighter/RiseX opportunistic for Herfindahl completeness mentioned in BOOK; not in Phase-4 empirics. |
| **Fill realism vs OE / self-impact** | Not tested | Sims: print + `fill_i` / instant POV @ trade px; no exchange OE / queue-position / self-impact feedback. |
| **Volume-clock duration ↔ markout OOS** | Attempted → Hold | Median wall-clock Δt=0; need powered vol-clock. A13 vol_$ buckets are detection clocks, not duration features. |
| **Ex-ante Amihud powered** | Underpowered n=20 | Multi-week + multi-coin required. A13 uses day Amihud only as horizon-interaction slice. |
| **Crash-window Epps / concordance Promote** | Hold / negative | Placebo fails; productize “do not wait for x-venue confirm” as policy memo only (partially in TRADING_APPLICATIONS). |
| **Joint diurnal mmip×mc_garch** | Hold | Peak 12 vs ~18 mismatch. |
| **True OI / Compustat-style size** | Not available | Daily notional proxy; size path **Kill**. |
| **TI-hl-reroute / TI-hv-child as edge PnL** | Monitor only | Ranked below top-3 in TRADE_IDEAS; no separate Promote edge report beyond A03/A04. |
| **TI-tax-gate auto-labeler ops** | Not built | Taxonomy Promote as framing; no postmortem auto-labeler. |

**Ranked next experiments** (from [`TRADING_APPLICATIONS.md`](TRADING_APPLICATIONS.md) §5): dense TOB pass · mid markout by V/cont · volume-clock duration · FEI→SOR schedule · widen panel VPIN/Amihud · concordance negative-product memo · joint diurnal — plus finish **`xvenue_lag`** / optional **xarb tick-bar** lane. Continuous paper shadow loop is **A12** (tested); horizon defaults are **A13**; **live orders remain NOT YET TESTED**.

---

## Artifact map (quick)

| Path | Contents |
|------|----------|
| `out/phase2_baselines_ssm/` | Nanex/SSM/MC-GARCH/KF Phase 2 |
| `out/phase3a_stats_xsec/` | Severity / recovery / xsec |
| `out/frag_xvenue/` | H^v / FEI / thin / concord |
| `out/phase4_hardening/` | Bootstrap freeze |
| `applications/out/event_panel/` | Shared gated panel + tiers |
| `applications/out/{kill_ladder,nanex_burst,hl_thin_sor,hv_fei_capacity}/` | Risk/SOR app outs |
| `applications/out/signal_boards/` | Board figs + Bayes draws |
| `applications/{mm_quoting,feature_models,expanded_lab,strategy_lab,paper_harness,paper_live,long_range_lab,horizon_lab,edge_lab}/` | Package-local EXP_REPORT / outs |

---

## Count

**Logged experiments in this ledger: 30**  
(R01–R08 = 8 · A01–A13 = 13 · E01–E05 = 5 · P4S catalog rollup = 1 compact entry covering 26 Phase-4 signal IDs)

*Last inventoried from files on disk (no invent). Update this file when a new EXP_REPORT lands.*
