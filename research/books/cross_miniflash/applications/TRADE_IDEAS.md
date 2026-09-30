# Trade-idea map — non-MM (taker / SOR / risk gate / event fade / vol)

**Source:** Phase 4 Promote/Hold rollup · [`../DESK_MEMO.md`](../DESK_MEMO.md) §2+§7 · [`../TRADING_APPLICATIONS.md`](../TRADING_APPLICATIONS.md) · app outs under `applications/out/`.  
**How we trade:** [`HOW_WE_TRADE.md`](HOW_WE_TRADE.md) — earn (causal V-fade) vs save (nest/int/fire-pause) vs Kill.  
**Honesty:** desk cleared **0 naked tradable** Promotes. Rows are **hypotheses** for an edge lab — not greenlit PnL.  
**Scope:** taker · SOR · risk gate · event fade · vol. **MM quoting left as-is** (V-restore stay-wide is playbook only; not expanded here).  
**Preferred features:** gated SSM intensity · V vs continuation · mo@5s · Nanex∩SSM · xvenue (thin / H^v / concordance-as-negative).  
**Panel:** `mm_quoting/out/panel_cache.json` (n=275 events: `label`, `intensity`, `z_peak`, `mo_5s`, `recovery_*`, `H_v`, VPIN…; **no per-event Nanex bit** — join `out/event_panel/` for nest).

---

## Promote → non-MM hypotheses

| id | lens | hypothesis | falsifier | status |
|----|------|------------|-----------|--------|
| `TI-int-halt` | risk | **Clip/halt aggressive takes** when venue-local gated SSM intensity ≥ fire tier (widen+); save |Δmo@5s| vs observe-only | Early/late Δ\|mo\| sign flip, or Δ\|mo\| CI ≤ friction (2bps) | **Promote** `risk.ssm_severity_gate_10bps` · `risk.ssm_zstar_scan_table` · `vol.sigma_m_noise_floor_1bp` (app Δ\|mo\|≈+6.5bps) |
| `TI-zstar-grid` | risk | Graded taker size = f(within-gated z\* pctile p25/p50/p75), not absolute z∈{8,10,12} | Absolute-z bands outperform pctile ladder OOS on \|mo\| | **Promote** `risk.ssm_zstar_scan_table` |
| `TI-nanex-nest` | risk | Nanex∩SSM nest = **hard escalate** (taker pause / child-size→0) vs SSM-only soft clip | Nest Δ\|mo\| CI includes 0; or Nanex-failing-SSM placebo matches nest severity | **Promote** `info.nanex_subset_of_ssm` (prec≈0.90; Δ\|mo\|≈+5.1bps) |
| `TI-v-fade` | info | **Fade V-holes only** (label=`v_recovery`): mean-revert vs crash direction @1–5s; **skip / lean with continuation** | V mo@5s CI ≥0 after costs; or V/cont class sep collapses OOS | **Promote** `info.crash_v_vs_continuation` (V mo≈−16.5 / cont≈+12; fade still **low** conf) |
| `TI-cont-ride` | info | On `continuation`, **ride short-horizon** with crash sign (taker add) instead of fade | Cont mo@5s CI ≤0 or worse than hold-flat after friction | **Promote** `info.crash_v_vs_continuation` |
| `TI-hl-reroute` | liq | When HL crash-share / thin-excess elevated **and** HL intensity fires → SOR **deprioritize HL aggressive** to DB/KR | Venue-local Δ\|mo\| HL-fire−thick CI includes 0 **and** thick-leg fill rate collapses (already soft: size-cap Hold) | **Promote** `frag.thin_venue_crash_excess` · `frag.crash_venue_share` (strip yes / hard cap Hold) |
| `TI-hv-child` | liq | High \(H^v\) / low FEI → shrink POV child on thin leg; prefer thick USD share | High-H exposure cut CI includes 0; Spearman(\(H^v\),\|mo\|) sign-unstable (known) | **Promote** `frag.volume_herfindahl_3venue` · `frag.fei_volume_3venue` (dashboard; schedule Hold) |
| `TI-tax-gate` | info | Taxonomy label (burst / hole / stale) gates which of {fade, ride, halt} may fire — no single rule on all defs | Auto-label disagrees with desk postmortems; or rule PnL identical w/o taxonomy | **Promote** `info.crash_def_taxonomy` |
| `TI-sigma-floor` | disc | σ_m≥1bp is **infra pre-condition** for any intensity-linked taker/risk rule | Turning floor off improves OOS rule PnL (should not) | **Promote** `vol.sigma_m_noise_floor_1bp` |

---

## Hold → non-MM hypotheses (research / blocked)

| id | lens | hypothesis | falsifier | status |
|----|------|------------|-----------|--------|
| `TI-xvenue-local` | cont | **Do not wait** for HL↔DB↔KR crash concordance before venue-local gate (negative product) | Concordance placebo p≪0.5 and Jaccard meaningfully >0 OOS | **Hold** `frag.xvenue_crash_concord` (placebo p≈0.58) |
| `TI-vpin-size` | cont | High VPIN×logN → tighter aggressor clip / toxicity regime for taker | Interact boot CI includes 0 OOS (apps CI excludes 0 → feature only) | **Hold→Promote(med) feature** `info.vpin_x_size_severity` |
| `TI-z6-raw` | risk | *(anti-idea)* raw z\*=6 without severity gate is **not** a taker signal | — | **Hold** `risk.ssm_z6_binary` · use gated intensity |
| `TI-nanex-solo` | risk | Nanex-30bps alone (no SSM nest) as burst taker pause | Precision ≪ nest; θ ablation fragile | **Hold** `base.nanex_crypto_30bps` |
| `TI-outside-tob` | exec | Outside-TOB → hard no-take | outside_rate unexplained on dense collector TOB | **Hold** `exec.outside_tob_wh_l2` |
| `TI-innov-lead` | info | KF innov/κ leads returns for taker | \|corr\| stays ≈0.04 OOS | **Hold** `info.ssm_innov_continuous` |
| `TI-dur-mo` | risk | Longer crash duration → larger \|mo\| → longer pause | Vol-clock Spearman OOS below bar (median Δt=0) | **Hold** `risk.duration_post_markout` |
| `TI-tape-mo` | exec | Tape mo@5s as exec throttle / fade sizing | mid_frac>0 and mid-mo class sep required; tape-only stays Hold | **Hold** `exec.tape_markout_post_crash` (mo@5s≈−11bps) |
| `TI-amihud` | liq | Ex-ante Amihud predicts \|ΔP\| for pre-trade risk budget | n_pred powered + sign-stable early/late | **Hold** `risk.exante_amihud_severity` |
| `TI-crossed` | exec | Crossed NBBO in crash±pad → no-take (mmip wire) | n_crossed stays 0 on dense TOB | **Hold** `frag.crossed_nbbo_crashwin` |
| `TI-epps` | cont | Crash-window Epps drop → widen hedge horizon / cut xvenue hedge | Crash Epps reliably < day Epps | **Hold** `epps.crash_window_corr` |
| `TI-utc-vol` | vol | UTC diurnal s_j / mmip curve peaks schedule vol/taker aggression | Peak-hour CI overlap across books | **Hold** `vol.mc_garch_sj_utc` · `vol.curve_intraday_link` |
| `TI-occur` | risk | Day-level occurrence score → reduce day risk budget / taker notional | AUC_te\<0.60 or Brier ≥ base-rate (soft≈0.635) | **Soft Promote** occurrence · severity \|\|ΔP\|\| still Hold |

**Kill (do not map to edge):** `base.nanex_paper_80bps`, `risk.ssm_raw_ungated_counts`, `xsec.size_reduces_severity`.

---

## Top 3 by expected edge (on existing `panel_cache`)

| Rank | id | Why | Needs beyond cache? |
|-----:|----|-----|---------------------|
| **1** | `TI-v-fade` / `TI-cont-ride` | Cleanest signed class edge already on cache: `label` ∈ {v_recovery,continuation} · `mo_5s` · `direction` — V≈−16.5bps vs cont≈+9…+12bps; no new detection | Friction + early/late + **no look-ahead** on `recovery_5s` (use 1–2s confirm) |
| **2** | `TI-int-halt` | Strongest policy evidence (Δ\|mo\|≈+6.5bps, friction+split OK); intensity/`z_peak` on every event | Map pctile ladder → size mult; venue-local only |
| **3** | `TI-nanex-nest` | High-precision severity escalate (Δ\|mo\|≈+5.1bps) | **Join** `applications/out/event_panel/` Nanex nest flags (not on `panel_cache` events) |

**HL reroute / H^v child** rank below: monitor-quality; hard-cap CIs include 0.

---

## Handoff → sibling `edge_lab`

`edge_lab` does not exist yet under `research/books/`. Suggested bootstrap:

1. **Read** `applications/mm_quoting/out/panel_cache.json` (`events[]`) + optional join `applications/out/event_panel/panel_rows.json` for Nanex nest / thin_excess / FEI.
2. **Primary A/B** on Rank-1: confirm-lagged V-fade vs cont-ride vs flat, haircut 2bps, early `days[:3]` / late `days[3:]`, report mean `mo_5s`×sign(rule) and bootstrap CI.
3. **Secondary:** intensity fire (e.g. `intensity` ≥ p50 of gated) → aggressor size∈{0,0.25,1} vs observe; reuse kill_ladder tier logic from `applications/out/kill_ladder/`.
4. **Tertiary:** nest bit from event_panel → escalate size→0; control = gated non-nest.
5. **Do not** expand MM quoting sims; consume class labels / mo only. ClickHouse MCP banned — warehouse/panel paths only.

**Most likely first green CI on cache alone:** Rank-1 class-conditioned fade/ride (features present; mid_mo null so stick to tape `mo_5s` until dense mid).
