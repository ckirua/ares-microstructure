# V-shapes — research index

Living map of Flora & Renò (2020) packages → candidates → experiment status.
Book PDF + `_raw/` extracts: **local only** (gitignored). Siblings: [`../mmip/`](../mmip/) · [`../empirical_mm/`](../empirical_mm/) · [`../cross_miniflash/`](../cross_miniflash/).
Data: [`../../DATA_PATHS.md`](../../DATA_PATHS.md). Loop: [`../../LOOP.md`](../../LOOP.md). Desk: [`DESK_MEMO.md`](DESK_MEMO.md).

**Book:** Flora & Renò, *V-shapes* (2020-09-17), 38 PDF pp. SSRN 3554122. Slug: `v_shapes`.

**Program status:** **Widened+hardened** — 20 UTC days · 4 Promote / 5 Hold / 2 Kill.

**Shared lib:** [`../../lib/vstat.py`](../../lib/vstat.py) (kernels, \(T^\pm\), \(V\), MinV, pre-avg/HAC, EGARCH bootstrap) · loaders [`scripts/_data.py`](scripts/_data.py) (HL + Deribit + Kraken).  
**Do not merge** with [`../../lib/crash.py`](../../lib/crash.py) `vshape_events` (geometric Dugast–Foucault).

**Reuse (do not rewrite):** cross_miniflash `crash.nanex_detect` / `vshape_events` / `kalman_ssm_*`; mmip Epps / resilience; empirical_mm `cont.vpin`, markout, `liq.amihud_1m`.

**Status legend:** `todo` · `notes` · `candidates` · `pass1` · `iterate` · `exp_run` · `park`  
**Lenses:** `risk` · `info` · `exec` · `disc` · `cont` · `liq` · `mm`

A package is **not** `exp_run`-complete after Pass 1 alone. Tracking path: **`pass1` → `iterate` → `exp_run`**.

---

## Two-pass checklist (every package)

### Pass 1 — faithfulness
- [x] Extract PDF theory/formulas into NOTES (pages cited)
- [x] Implement paper object on real **HL + Deribit + Kraken**
- [x] Baseline plots + EXP_REPORT with sample / window / **day-completeness** flags
- [x] Draft CANDIDATES (tentative status OK)

### Pass 2 — deep info / signals (mandatory)
- [x] What information does the object carry? (pre / concurrent / post: VPIN, OFI, sign-ACF, markout, intensity, spread, depth, resilience)
- [x] Signal hypotheses labeled honestly: *risk monitor* vs *tradable* vs *exec throttle*
- [x] Competing defs (geometric V, Nanex, Tee–Ting SSM) + ablations (\(h_n\), pre-avg, clocks)
- [x] Falsifiers: time-split, block bootstrap, placebo times, \(h_n\) fragility → Kill failures
- [x] CANDIDATES + notebook “Signal board” + DESK_MEMO entry

**Quant bar:** precise units/clocks; ID assumptions stated; effect sizes + CIs; no Promote without a falsifier attempt; notebooks memo-quality.

---

## Package roadmap

| Package | Paper focus (Pass 1) | Pass 2 dig | Status | Path |
|---------|----------------------|------------|--------|------|
| `ch00_overview` | §1–2 Def 1; vol/jumps ≠ inefficiency; reading order | Taxonomy: V vs jump vs liq hole vs Tee–Ting mini-crash; signal roadmap | `exp_run` | [`chapters/ch00_overview/`](chapters/ch00_overview/) |
| `v_statistic` | §3 \(T^\pm\), \(V_{\tau,n}\), kernels, pre-avg+HAC; `lib/vstat.py` | Continuous \(V_t\) / \(T^\pm\) as info features; lead-lag vs mid; pre-avg sensitivity | `exp_run` | [`chapters/v_statistic/`](chapters/v_statistic/) |
| `bootstrap_sim` | §3.1 EGARCH bands; §4 Models 0–3 size/power | Crypto-calibrated DGP; Kill asymptotic 2.18/3.60; \(h_n\) power curve | `exp_run` | [`chapters/bootstrap_sim/`](chapters/bootstrap_sim/) |
| `daily_minv` | §5 daily MinV panel; V vs Λ at 1/5/30m | Post-trough returns; toxicity/OFI; time-split stress vs calm | `exp_run` | [`chapters/daily_minv/`](chapters/daily_minv/) |
| `event_case` | §6-style dive on 1–2 crypto stress days | Regime proxy; markout path; Hold auction-loss ID | `exp_run` | [`chapters/event_case/`](chapters/event_case/) |
| `liq_around_v` | §6.2 liquidity around V (spread, depth, impact) | Incremental liq info vs MinV; resilience; GM \(\mu/\sigma\) monitor only | `exp_run` | [`chapters/liq_around_v/`](chapters/liq_around_v/) |
| `xvenue_concord` | Multi-venue MinV on ETH/BTC | HL↔Deribit↔Kraken concordance; FEI/Epps around V | `exp_run` | [`chapters/xvenue_concord/`](chapters/xvenue_concord/) |

**First vertical slice (still two-pass):** \(V_{\tau,n}\) + EGARCH bands on HL+Deribit+Kraken ETH (complete UTC week) → daily MinV → info joins + concordance vs `crash.vshape_events` / SSM → widen BTC after Promote gate.

---

## Promote rollup

| Candidate | risk | info | exec | disc | cont | liq | mm | Ch | One-line use |
|-----------|:----:|:----:|:----:|:----:|:----:|:---:|:--:|----|--------------|
| `risk.v_vs_jump_taxonomy` | ✓ | ✓ |  |  |  |  |  | ch00_overview | V ≠ jump ≠ vol spike ≠ geometric V |
| `risk.egarch_minv_bands` | ✓ |  |  |  |  |  |  | bootstrap_sim | EGARCH simulated bootstrap CIs for MinV |
| `risk.daily_minv_panel` | ✓ |  |  |  |  |  |  | daily_minv | UTC-day MinV vs EGARCH 5% as fragility monitor |
| `risk.stress_day_minv` | ✓ | ✓ |  |  |  |  |  | event_case | Stress-day MinV narrative reproduced across ≥3 complete days |

**Kill / Hold:**
- **Kill** `risk.asymptotic_218_360`: paper §3.1: too small for realistic DGP + multiple testing; use EGARCH bootstrap
- **Kill** `risk.gm_mu_sigma_tradable`: Grossman–Miller mu/sigma monitor only — vanity as tradable
- **Hold** `risk.xvenue_minv_concord`: no concordant significant pair in slice
- **Hold** `info.v_path_continuous`: mean_corr_V=0.021 CI=[-0.006,0.048] n=220 (V-only; CI does not clear Promote bar / thin events)
- **Hold** `info.post_trough_ret`: post300 mean=0.00020 CI=[-0.00129,0.00169] n=17
- **Hold** `liq.spread_around_minv`: TOB usable rows=14 days=['2026-09-08', '2026-09-15', '2026-09-25', '2026-09-27', '2026-09-29', '2026-09-30'] sources=['collector', 'warehouse:l2_snapshot_level/warehouse:l2_tob/s3_cache']; Δspread(post-pre) mean=-0.0749 CI=[-0.2234,0.0737] n_sane=8 (Kraken warehouse L2 empty; collector only 0929-30; Deribit L2 multi-day but Δ not Promote-grade)
- **Hold** `id.auction_loss`: no crypto sovereign auction analogue

---

## Crypto adaptation defaults

| Paper | Desk mapping |
|-------|----------------|
| SPY 1s grid trades | Trade mid / last on 1s grid; incomplete-day flags |
| RTH day MinV | **UTC-day** MinV; 24/7 tape (no close) |
| \(h_n\) = 1 / 5 / 30 min (stocks); 2d (bonds) | Primary: **1 / 5 / 30 min**; secondary stress: **1–4 h** |
| EGARCH(1,1) bootstrap on 1s | Same on venue 1s returns; leverage OK |
| Italian bond auction wealth transfer | **No sovereign auction**: funding / liq-stress / liquidation-cascade days; maker inventory / adverse markout around MinV (Hold causal claims) |
| Flash-crash lit link | Concordance vs `crash.vshape_events`, Nanex, Tee–Ting SSM |
