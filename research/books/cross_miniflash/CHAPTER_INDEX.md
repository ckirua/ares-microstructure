# Cross-Section of Mini Flash Crashes — research index

Living map of Tee & Ting (2019) packages → candidates → experiment status.
Book PDF + `_raw/` extracts: **local only** (gitignored). Siblings: [`../mmip/`](../mmip/) · [`../empirical_mm/`](../empirical_mm/).
Data: [`../../DATA_PATHS.md`](../../DATA_PATHS.md). Loop: [`../../LOOP.md`](../../LOOP.md). Desk: [`DESK_MEMO.md`](DESK_MEMO.md).

**Book:** Tee & Ting, *Cross-Section of Mini Flash Crashes…* (2019-06-12), 43 PDF pp. Slug: `cross_miniflash`.

**Program status:** **COMPLETE (Phase 4 hardened)** — **10 Promote / 13 Hold / 3 Kill** on HL+Deribit+Kraken ETH/BTC 2026-09-04…2026-09-10.  
Empirics: [`out/phase2_baselines_ssm/`](out/phase2_baselines_ssm/) · [`out/phase3a_stats_xsec/`](out/phase3a_stats_xsec/) · [`out/frag_xvenue/`](out/frag_xvenue/) · Harden: [`out/phase4_hardening/`](out/phase4_hardening/).

**Shared lib:** [`../../lib/crash.py`](../../lib/crash.py) (Nanex, Kalman SSM, `severity_gate` default **10bps/ic5**, recovery/markout, `volume_herfindahl`, `xvenue_event_concordance`, z*-scan) · NW-OLS [`../../lib/stats.py`](../../lib/stats.py) · loaders [`scripts/_data.py`](scripts/_data.py).

**Reuse (do not rewrite):** mmip `vol.curve_intraday`, `book.resilience`, `frag.crossed_nbbo`, `frag.update_share`, `epps.xvenue_corr`, `vol.fei_hourly`; empirical_mm `cont.vpin`, `disc.jump_sign_concord`, `liq.amihud_1m`, `disc.var_lambda`, markout.

**Status legend:** `todo` · `notes` · `candidates` · `pass1` · `iterate` · `exp_run` · `park`  
**Lenses:** `risk` · `info` · `exec` · `disc` · `cont` · `liq` · `mm`

A package is **not** `exp_run`-complete after Pass 1 alone. Tracking path: **`pass1` → `iterate` → `exp_run`**. All packages below are **`exp_run`** + program **COMPLETE**.

---

## Two-pass checklist (every package)

### Pass 1 — faithfulness
- [x] Extract PDF theory/formulas into NOTES (pages cited)
- [x] Implement paper object on real **HL + Deribit + Kraken**
- [x] Baseline plots + EXP_REPORT with sample / window / **day-completeness** flags
- [x] Draft CANDIDATES (tentative status OK)

### Pass 2 — deep info / signals (mandatory)
- [x] What information does the object carry?
- [x] Signal hypotheses labeled: *risk monitor* vs *tradable* vs *exec throttle*
- [x] Competing defs + ablations (z*, θ, σ_m frac)
- [x] Falsifiers: time-split, σ/z* stress, threshold fragility → Kill failures
- [x] CANDIDATES + notebook “Signal board” + DESK_MEMO entry

### Pass 2.5 — program hardening
- [x] Bootstrap / time-split every Promote
- [x] Kill vanity metrics that fail
- [x] Unified severity-gate note (primary 10bps/ic5; frag also 5bps/ic3)
- [x] DESK_MEMO signal board freeze + `notebooks/desk_synthesis.ipynb`

**Quant bar:** precise units/clocks; ID assumptions stated; effect sizes + CIs; no Promote without a falsifier attempt; notebooks memo-quality.

---

## Package roadmap

| Package | Paper focus (Pass 1) | Pass 2 dig | Status | Path |
|---------|----------------------|------------|--------|------|
| `ch00_overview` | Map 5 defs → SSM | Info taxonomy; reading order + signal roadmap | `exp_run` | [`chapters/ch00_overview/`](chapters/ch00_overview/) |
| `crash_baselines` | Nanex, outside-TOB, V-shape | Overlap / PR vs SSM; toxicity/OFI; θ ablation | `exp_run` | [`chapters/crash_baselines/`](chapters/crash_baselines/) |
| `mc_garch_vol` | h_n,s_j,q fit; σ_p,σ_m | Diurnal signal; σ-split stress; `vol.curve_intraday` link | `exp_run` | [`chapters/mc_garch_vol/`](chapters/mc_garch_vol/) |
| `kalman_ssm` | KF + z=6 flags | z∈[2,12] scan; innov/gain features; lead–lag | `exp_run` | [`chapters/kalman_ssm/`](chapters/kalman_ssm/) |
| `crash_stats` | ΔP,i_c,Δt, recovery | Post-event markout/resilience; V vs continuation | `exp_run` | [`chapters/crash_stats/`](chapters/crash_stats/) |
| `cross_section` | Quintiles + NW-OLS | Ex-ante OI/vol/liq → severity?; ×VPIN | `exp_run` | [`chapters/cross_section/`](chapters/cross_section/) |
| `frag_xvenue` | Herfindahl, venue share (HL+Deribit+Kraken) | Thin-venue concentration; concordance; FEI / Epps | `exp_run` | [`chapters/frag_xvenue/`](chapters/frag_xvenue/) |

**MC-GARCH → σ (locked):** σ_p² ∝ q h s·Δt; σ_m = frac × max(MAD(Δlog p), **1 bp**) — Pass 2 + Phase 4 stress-tested.

**Vertical slice counts @ z*=6 (noise floor on):** Nanex 30bps **105** vs SSM raw **3668** → gated 5bps/ic3 **589** · **10bps/ic5 275** · 30bps/ic10 **56**. Paper Nanex 80bps: **8** (Kill).

---

## Promote rollup (Phase 4 hardened) by lens

| Candidate | risk | info | exec | disc | cont | liq | mm | Ch | One-line use |
|-----------|:----:|:----:|:----:|:----:|:----:|:---:|:--:|----|--------------|
| `info.crash_def_taxonomy` |  | ✓ |  |  |  |  |  | ch00 | Label bursts vs broad outliers vs stale-quote artifacts |
| `info.nanex_subset_of_ssm` | ✓ | ✓ |  |  |  |  |  | baselines | Nanex = high-precision SSM subset |
| `vol.sigma_m_noise_floor_1bp` | ✓ |  |  | ✓ |  |  |  | mcgarch | Required σ_m floor so KF z-scores don't flood |
| `risk.ssm_zstar_scan_table` | ✓ |  |  | ✓ |  |  |  | ssm | Publish z* menu with any binary cut |
| `risk.ssm_severity_gate_10bps` | ✓ |  |  | ✓ |  |  |  | stats | Gate raw SSM before intensity/risk counts |
| `info.crash_v_vs_continuation` | ✓ | ✓ |  |  |  | ✓ |  | stats | V@5s — hole vs news class |
| `frag.volume_herfindahl_3venue` |  |  |  |  |  | ✓ | ✓ | frag | 3-venue USD H^v capacity monitor |
| `frag.fei_volume_3venue` |  |  |  |  |  | ✓ | ✓ | frag | FEI companion to Herfindahl |
| `frag.crash_venue_share` | ✓ |  |  |  |  | ✓ |  | frag | Gated SSM/Nanex venue mix (HL-heavy) |
| `frag.thin_venue_crash_excess` | ✓ |  |  |  |  | ✓ | ✓ | frag | HL thin on USD but crash-dense |

**Kill:** `base.nanex_paper_80bps`, `xsec.size_reduces_severity`, `risk.ssm_raw_ungated_counts`  
**Hold:** `frag.xvenue_crash_concord`, `info.vpin_x_size_severity`, `risk.ssm_z6_binary`, `base.nanex_crypto_30bps`, `exec.outside_tob_wh_l2`, `info.ssm_innov_continuous`, `risk.duration_post_markout`, `exec.tape_markout_post_crash`, `risk.exante_amihud_severity`, `frag.crossed_nbbo_crashwin`, `epps.crash_window_corr`, `vol.mc_garch_sj_utc`, `vol.curve_intraday_link`

**Gate note:** primary Promote = **10bps/ic5**; frag share/thin tables also report **5bps/ic3** (denser).  
**Stats headline:** gated median ΔP≈0.18%; V-share≈77%; tape mo@5s≈−7bps; plain size **Kill**.  
**Frag headline:** H^v≈0.48; HL thin excess @5bps≈0.78 / @10bps≈0.79; concordance **Hold**.

### Executable apps (Promote IDs → action)

| Promote ID(s) | App overlay | Path |
|---------------|-------------|------|
| `risk.ssm_severity_gate_10bps` · `risk.ssm_zstar_scan_table` · `vol.sigma_m_noise_floor_1bp` | kill-ladder observe→widen→size_cap→halt | [`applications/kill_ladder/`](applications/kill_ladder/) · paper [`applications/paper_harness/`](applications/paper_harness/) |
| `info.nanex_subset_of_ssm` | Nanex∩SSM nested temp pull | [`applications/nanex_burst/`](applications/nanex_burst/) · `nanex_temp_pull` in strategy_lab |
| `info.crash_v_vs_continuation` | V-confirm restore / stay-wide | [`applications/mm_quoting/`](applications/mm_quoting/) · `v_restore_confirm` in strategy_lab |
| `frag.thin_venue_crash_excess` · `frag.crash_venue_share` | HL thin strip / optional size-cap | [`applications/hl_thin_sor/`](applications/hl_thin_sor/) · `hl_thin_size_cap` |
| `frag.volume_herfindahl_3venue` · `frag.fei_volume_3venue` | capacity dashboard | [`applications/hv_fei_capacity/`](applications/hv_fei_capacity/) |
| `info.vpin_x_size_severity` | feature (not live sizing) | [`applications/feature_models/`](applications/feature_models/) |

Desk board: [`applications/strategy_lab/strategy_lab.ipynb`](applications/strategy_lab/strategy_lab.ipynb) · paper day report: [`applications/paper_harness/out/`](applications/paper_harness/out/) · SoT [`DESK_MEMO.md`](DESK_MEMO.md) §7.

---

## Crypto adaptation defaults

| Paper | Desk mapping |
|-------|----------------|
| S&P500 MCap | OI / 24h notional (HL) |
| Compustat vol / avg price | Realized vol + mark/mid |
| RTH diurnal s_j | **UTC-day** 5m diurnal on 24/7 tape |
| Equity ticks i_c | Trade count + bps move; tick-count secondary |
| 17 venues / Herfindahl | HL + Deribit + Kraken core |
| TAQ ms trades | Warehouse + collector; incomplete-day flags (flat-id + UTC clip) |
| SSM z-score | **Standardized innovation** (not posterior/√P) |
| σ_m | frac × max(MAD(Δlog p), **1 bp**) |
| Severity gate | **Primary 10bps / i_c≥5**; frag also 5bps / i_c≥3 |
