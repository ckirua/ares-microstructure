# Tick Size Viewpoints — research index

Living map of Rindi et al. (MMCV #3 Paris 2014) packages → candidates → experiment status.
Book PDF + `_raw/` extracts: **local only** (gitignored). Siblings: [`../mmip/`](../mmip/) · [`../empirical_mm/`](../empirical_mm/) · [`../v_shapes/`](../v_shapes/) · [`../mn_tuwrv/`](../mn_tuwrv/).
Data: [`../../DATA_PATHS.md`](../../DATA_PATHS.md). Loop: [`../../LOOP.md`](../../LOOP.md). Desk: [`DESK_MEMO.md`](DESK_MEMO.md).

**Book:** Rindi et al., *Tick Size: Theory and Evidence* (2014-12-11 slides). Slug: `mm_confr_viewpoints`.

**Program status:** **Pass-2.5 hardened** — 1 Promote / 9 Hold / 4 Kill (ETH+BTC day-block bootstrap in `out/hardening/`).

**Shared lib:** [`../../lib/ticksize.py`](../../lib/ticksize.py) · loaders [`scripts/_data.py`](scripts/_data.py).  
**Do not merge** with mmip `tick.rel_tick_bps` / `tick.spread_leeway` / `tick.frac_one_tick` APIs — cross-link only.

**Status legend:** `todo` · `notes` · `candidates` · `pass1` · `iterate` · `exp_run` · `park`  
**Lenses:** `risk` · `info` · `exec` · `disc` · `cont` · `liq` · `mm`

A package is **not** `exp_run`-complete after Pass 1 alone. Tracking path: **`pass1` → `iterate` → `exp_run`**.

---

## Two-pass checklist (every package)

### Pass 1 — faithfulness
- [x] Extract PDF prediction tables / formulas into NOTES (slide pages cited)
- [x] Implement objects on real **HL + Deribit + Kraken**
- [x] Baseline plots + EXP_REPORT with sample / window / **day-completeness** flags
- [x] Draft CANDIDATES (tentative status OK)

### Pass 2 — deep info / signals (mandatory)
- [x] Info around tick regimes (OFI/VPIN/markout/intensity)
- [x] Signal labels: *risk monitor* vs *tradable* vs *exec throttle*
- [x] Competing defs (mmip leeway / frac_one_tick; Harris continuous-spread Hold)
- [x] Falsifiers: time-split, block bootstrap, placebo thresholds → Kill failures
- [x] CANDIDATES + notebook Signal board + DESK_MEMO entry

**Quant bar:** precise units/clocks; ID assumptions stated; effect sizes + CIs; no Promote without a falsifier attempt; notebooks memo-quality.

---

## Package roadmap

| Package | Deck focus (Pass 1) | Pass 2 dig | Status | Path |
|---------|---------------------|------------|--------|------|
| `ch00_overview` | RQ: large vs small Δτ; relative tick; liquid vs thin; reading order | Taxonomy vs mmip `tick.*`; signal roadmap | `exp_run` | [`chapters/ch00_overview/`](chapters/ch00_overview/) |
| `emp_predictions` | Sign tables pp. 20–29 + LOB undercutting story → expected-sign matrix; MQ vector | Map cells → desk metric + falsifier; Kill welfare/SEC | `exp_run` | [`chapters/emp_predictions/`](chapters/emp_predictions/) |
| `rel_tick_panel` | FM-style: BBO depth, quoted/rel spread, volume vs \(\tau/\mathrm{mid}\) | Markout by rel-tick quartile; time-split; vs mmip `rel_tick_bps` | `exp_run` | [`chapters/rel_tick_panel/`](chapters/rel_tick_panel/) |
| `tick_constraint` | Flag tick-constrained books (spread ≤ 1–2 ticks); undercutting when rel-tick falls | Queue/cancel proxy; OFI/VPIN around relax bursts; exec throttle vs fragility | `exp_run` | [`chapters/tick_constraint/`](chapters/tick_constraint/) |
| `liq_book_split` | Heterogeneous effects: liquid vs less-liquid terciles × rel-tick ↑ | Placebo price moves; exec make/take hypothesis | `exp_run` | [`chapters/liq_book_split/`](chapters/liq_book_split/) |
| `xvenue_tick` | Same-coin τ gaps HL↔Deribit↔Kraken → MQ Δ; grid-pressure residuals | Concordance; FEI/Epps; SOR venue preference | `exp_run` | [`chapters/xvenue_tick/`](chapters/xvenue_tick/) |

### Figure index (PNG)

Chapter notebooks load `fig_*.png`; desk synthesis also keeps short aliases from `scripts/exp_build_figs.py`.

| Package | Figs dir | Primary PNGs |
|---------|----------|--------------|
| `ch00_overview` | [`out/ch00_overview/figs/`](out/ch00_overview/figs/) | `fig_coverage.png`, `fig_venue_tau.png`, `fig_reading_order.png` (+ alias `coverage.png`) |
| `emp_predictions` | [`out/emp_predictions/figs/`](out/emp_predictions/figs/) | `fig_sign_heatmap.png`, `fig_scorecard.png`, `fig_kill_cells.png` (+ aliases `sign_matrix.png`, `scorecard.png`) |
| `rel_tick_panel` | [`out/rel_tick_panel/figs/`](out/rel_tick_panel/figs/) | `fig_scatter_{spread,volume,depth}.png`, `fig_fm_coefs.png`, `fig_time_split.png`, `fig_markout_quartile.png` (+ aliases `scatter_mq.png`, `fm_coefs.png`, `time_split.png`) |
| `tick_constraint` | [`out/tick_constraint/figs/`](out/tick_constraint/figs/) | `fig_frac_constrained_panel.png`, `fig_spread_ticks_hist.png`, `fig_undercut_vs_constraint.png`, `fig_relax_event_study.png`, `fig_intraday_constraint_hl.png`, `fig_desk_labels.png` (+ aliases `frac_constrained.png`, `spread_ticks_hist.png`, `relax_events.png`) |
| `liq_book_split` | [`out/liq_book_split/figs/`](out/liq_book_split/figs/) | `fig_tercile_rel_tick_spread.png`, `fig_het_rho_bars.png`, `fig_hour_interaction.png`, `fig_depth_vs_rel_tick.png`, `fig_placebo_mid_move.png`, `fig_make_take_rho.png` (+ aliases `tercile_interaction.png`, `placebo.png`) |
| `xvenue_tick` | [`out/xvenue_tick/figs/`](out/xvenue_tick/figs/) | `fig_tau_gap_heatmap.png`, `fig_mq_delta_vs_tau_gap.png`, `fig_grid_pressure_residuals.png`, `fig_concord_fei_epps.png`, `fig_sor_preference.png` (+ aliases `tau_gap_heatmap.png`, `mq_vs_gap.png`, `grid_pressure.png`) |
| desk synthesis | [`out/desk_synthesis/figs/`](out/desk_synthesis/figs/) | `signal_board.png` |

**First vertical slice (still two-pass):** τ + relative tick + MQ + constraint on HL+Deribit+Kraken ETH (complete UTC days) → sign scorecard + FM/x-venue table → Pass 2 markout/OFI + liquid split → widen BTC after Promote gate.

---

## Promote rollup

| Candidate | risk | info | exec | disc | cont | liq | mm | Ch | One-line use |
|-----------|:----:|:----:|:----:|:----:|:----:|:---:|:--:|----|--------------|
| `disc.tick_rq_taxonomy` |  |  |  | ✓ |  |  | ✓ | ch00_overview | Taxonomy vs mmip tick.*; reading order |

**Kill:**
- `id.lse_nasdaq_rdd_literal` — no sovereign tick ladder / vanity RD
- `id.welfare_tick` — unobservable
- `id.sec_ipo_channel` — out of scope
- `disc.sign_scorecard_tradable` — hit_rate≈0.33 on ETH slice; not a tradable signal

**Hold:**
- `liq.placebo_flat_rel_tick` — native rerun: mean|Δqs|≈0.000562 n_hours=75 (KR-spot=19); BTC pooled historically weak — still Hold
- `liq.fm_rel_tick_spread` — baseline FM t=-3.54 ρ=-0.6; **native spot panel** FM t=+2.89 ρ=+0.5 (sign flip — KR spot tiny τ/mid + tight spreads); xvenue τ confound remains
- `liq.rho_rel_tick_spread` — baseline ρ=-0.6; native pooled ρ=+0.5; KR-spot within-venue ρ=+1.0 (n=3 days — thin)
- `exec.tick_constrained_flag` — HL frac≈0.992; DB≈0.136; **KR-spot≈0.850** (was 0 under trade_synth); overlaps mmip; PF futures still L2-absent
- `exec.undercut_rate` — native KR eligible (relax flips=105); L0 proxy, no queue ID — Hold
- `disc.expected_sign_matrix` — codified pp.20–29; crypto scorecard fragile on 3-day slice
- `frag.xvenue_tau_gap` — HL↔Deribit stable; dual slices: KR futures synth + KR spot L2 (spot≠perp) — Hold
- `frag.grid_pressure` — feature computed; residual MQ Δ needs FE / wider sample
- `liq.book_tercile_het` — n=3 per tercile; liquid tercile now KR-spot (spread≈0.037 bps) — still thin

**Native SoT:** `out/pass1_native/` · `out/pass2_native/` · `out/native_rerun/` (baseline synth-era `out/pass1/` preserved).

---

## Crypto adaptation defaults

| Deck / equity design | Crypto desk mapping |
|----------------------|---------------------|
| LSE price→tick grid RDD (GBX thresholds) | **No sovereign tick ladder on perps.** Primary QE: **cross-venue tick gap** (HL vs Deribit vs Kraken τ). Secondary: within-venue **relative tick** \(\tau/\mathrm{mid}\) as mid moves |
| LSE / Nasdaq $1 RDD | **Park** — identification template only; no vanity RD Promote |
| Fama–MacBeth on \(\tau/P\) | Daily/hourly FM-style panel: \(y \sim \tau/\mathrm{mid}\) + controls across coins×venues |
| Liquid vs less-liquid books | Terciles by quoted spread bps / BBO depth / trade intensity (UTC-day) |
| Tick-constrained books | Flag when quoted spread ≤ 1–2 ticks |
| Grid pressure | Price moves that change \(\tau/\mathrm{mid}\) without venue tick change |
| SEC tick pilot / IPO channel | **Out of scope** |
| Welfare / LOB game sim | **Hold** — NOTES under `emp_predictions` only |
