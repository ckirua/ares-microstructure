# Filimonov HFT — research index

Living map of Filimonov (Perm Winter School 2013) packages → candidates → experiment status.
Book PDF + `_raw/` extracts: **local only** (gitignored). Siblings: [`../mm_confr_viewpoints/`](../mm_confr_viewpoints/) · [`../cross_miniflash/`](../cross_miniflash/) · [`../v_shapes/`](../v_shapes/) · [`../mmip/`](../mmip/).
Data: [`../../DATA_PATHS.md`](../../DATA_PATHS.md). Loop: [`../../LOOP.md`](../../LOOP.md). Desk: [`DESK_MEMO.md`](DESK_MEMO.md) · Wire-as: [`APPLICATIONS.md`](APPLICATIONS.md).

**Book:** Filimonov, *High-Frequency Trading. Technology, Strategies, Regulations* (2013 slides, 43 pp). Slug: `filmonov`.

**Program status:** **Pass-2 expand** — **0 Promote / 21 Hold / 11 Kill** on ETH+BTC HL+Deribit+Kraken (days ['2026-09-25', '2026-09-26', '2026-09-27', '2026-09-30']); legacy freeze 0/13/11 + 8 info Holds in `out/pass2_expand/`.

**Shared lib:** [`../../lib/hftpat.py`](../../lib/hftpat.py) · loaders [`scripts/_data.py`](scripts/_data.py).  
**Do not merge** with `crash.nanex_detect` / `vshape_events`, `vstat.min_v`, or `lob.tob_depletion_cancel_proxy` — cross-link + overlap gates only.

**Status legend:** `todo` · `notes` · `candidates` · `pass1` · `iterate` · `exp_run` · `park`  
**Lenses:** `risk` · `info` · `exec` · `disc` · `cont` · `liq` · `mm`

A package is **`exp_run`-complete** after Pass 1 + Pass 2 falsifiers + hardening freeze; expand digs add info Holds without Promote inflation.

---

## Two-pass checklist (every package)

### Pass 1 — faithfulness
- [x] Extract PDF taxonomy / formulas into NOTES (slide pages cited)
- [x] Implement objects on real **HL + Deribit + Kraken**
- [x] Baseline plots + EXP_REPORT with sample / window / **day-completeness** flags
- [x] Draft CANDIDATES (tentative status OK)

### Pass 2 — deep info / signals (mandatory)
- [x] Info joins (OFI/VPIN/markout/intensity where useful)
- [x] Signal labels: *risk monitor* vs *tradable* vs *exec throttle*
- [x] Competing defs + **overlap gates** vs Nanex∩SSM / `vshape_events` / lob cancel proxy
- [x] Falsifiers: time-split, day-block bootstrap, placebo → Kill failures
- [x] CANDIDATES + notebook Signal board + DESK_MEMO entry

### Pass-2 expand (this dig)
- [x] Wider day panel (+2026-09-25) + BTC
- [x] Richer stats/plots under `out/pass2_expand/figs/`
- [x] Info candidates in `hftpat` + `exp_info_features.py`
- [x] APPLICATIONS.md wire-as playbooks (no invented α)

**Quant bar:** precise units/clocks; ID assumptions stated; effect sizes + CIs; no Promote without a falsifier attempt; notebooks memo-quality. Kill if fade/ignition/storms are essentially a rename of crash/vstat/lob.

---

## Package roadmap

| Package | Deck focus (Pass 1) | Pass 2 dig | Status | Path |
|---------|---------------------|------------|--------|------|
| `ch00_overview` | SEC HFT attrs, strategy map, reading order, sibling reuse (slides 1–9) | Taxonomy Hold; Kill Hibernia/triangle | `exp_run` | [`chapters/ch00_overview/`](chapters/ch00_overview/) |
| `latency_size_regimes` | TOB update Hz, trade-size quantiles, reaction proxies (slides 10–20) | Feed-sample Hz Hold; Kill co-lo vanity; size×storm expand | `exp_run` | [`chapters/latency_size_regimes/`](chapters/latency_size_regimes/) |
| `quote_storms` | Burst detectors, intensity vs baseline (slides 27–29) | Storm→AS/intensity/OFI; ToD; exec throttle Hold | `exp_run` | [`chapters/quote_storms/`](chapters/quote_storms/) |
| `book_fade` | Same-venue price fade; venue-fade when sync allows (slide 33) | τ-sens; spread IRF; markout; Kraken synth excluded | `exp_run` | [`chapters/book_fade/`](chapters/book_fade/) |
| `momentum_ignition` | 3-phase classifier + duration/move dists (slide 34) | Unique-mass + lead-lag cascade; Hold (no Promote) | `exp_run` | [`chapters/momentum_ignition/`](chapters/momentum_ignition/) |
| `spoof_smoke_clock` | Smoking/layering/tape + clock hunting + OTR (slides 29–30, 35–37, 41–43) | Clock vs funding; smoke/layer Kill; OTR policy Hold | `exp_run` | [`chapters/spoof_smoke_clock/`](chapters/spoof_smoke_clock/) |

### Figure index (PNG)

Chapter notebooks load `fig_*.png` from `out/<pkg>/figs/`. Expand dig: `out/pass2_expand/figs/`. Desk board: `out/desk_synthesis/figs/signal_board.png`.

| Package | Figs dir | Primary PNGs |
|---------|----------|--------------|
| `ch00_overview` | `out/ch00_overview/figs/` | coverage, taxonomy, reading order, sibling reuse |
| `latency_size_regimes` | `out/latency_size_regimes/figs/` | size quantiles, TOB Hz, reaction scatter, size curve, size×storm |
| `quote_storms` | `out/quote_storms/figs/` | burst intensity, cancel frac, day baseline, ToD, boot hist |
| `book_fade` | `out/book_fade/figs/` | fade P(τ), event study, venue-fade, τ-sens, CDF |
| `momentum_ignition` | `out/momentum_ignition/figs/` | 3-phase counts, move/recovery, overlap, unique mass, lead-lag |
| `spoof_smoke_clock` | `out/spoof_smoke_clock/figs/` | smoke FP, clock cluster, OTR, clock×funding |
| pass2 | `out/pass2/figs/` | overlap gates, labels, fade markout delta |
| pass2_expand | `out/pass2_expand/figs/` | forest CI, ToD, τ-sens, lead-lag, size×storm, info IRFs, signal_board |
| hardening / desk | `out/hardening/figs/` · `out/desk_synthesis/figs/` | signal_board |

**Runners:** `scripts/exp_ch00_latency.py`, `exp_core_detectors.py`, `exp_spoof_clock.py`, `exp_pass2_info.py`, `exp_final_hardening.py`, `exp_pass2_expand.py`, `exp_info_features.py`, `exp_expand_board.py`, `exp_build_figs.py`.

---

## Promote rollup

**0 Promote / 21 Hold / 11 Kill** (honest zero-Promote expand OK).

**Kill:** *(unchanged from freeze)*
- Hibernia / co-lo RTT vanity without crypto desk mapping
- Fee-free FX triangle arb narrative
- Participant-level OTR without firm IDs
- Rebadged Nanex/SSM/V events as “ignition”
- Equity quote-rate charts as crypto intensity vanity
- Smoke / layering proxies as α (FP≈1.79)
- Tape-paint equity cartoon

**Hold (monitor / exec / policy) — legacy:**
- Taxonomy tile; size/latency regime panel (feed-sample)
- Quote-storm burst (HL) as exec throttle
- Price / venue fade as MM-pull monitor
- Momentum ignition 3-phase as escalate-vs-crash (not Promote)
- Clock cluster algo-hunter monitor; venue OTR policy-only

**Hold (info expand — new):**
- `info.storm_adverse_selection`, `info.fade_spread_widen_irf`
- `info.ignition_phase1_unique_mass`, `info.clock_vs_funding_window`
- `info.xvenue_is_around_fade`, `info.ofi_around_storm_regime`
- `info.vpin_storm_join`, `info.storm_trade_intensity_burst`

**Promote:** *(none — falsifier/overlap gates not cleared)*

---

## Crypto adaptation defaults

| Deck / equity design | Crypto desk mapping |
|----------------------|---------------------|
| Firm-ID quote stuffing / OTR | Venue-aggregate cancel/trade proxies; no participant IDs |
| Same-venue price fade | P(same-side TOB depth↓ \| aggressor) on HL/DB native TOB |
| Cross-venue fade | Far-venue depth drop latency-aligned to home trade; RTT haircut later |
| Momentum ignition | 3-phase vol↑→move→partial recovery; overlap-gate vs crash/vstat |
| Smoking / layering | Attractive quote→cancel→worse fill; large away-from-touch cancel w/o trade |
| Clock hunting | Excess fills at second-of-minute; compare to funding/mark windows |
| Co-lo / Hibernia | **Kill** as vanity unless mapped to crypto venue RTT panel |
