# squeeze_metrics — research index

Living map of SqueezeMetrics / GEX Ed. (2020) packages → candidates → experiment status.
Book PDF + `_raw/` extracts: **local only** (gitignored). Siblings: [`../cd_me/`](../cd_me/) · [`../v_shapes/`](../v_shapes/) · [`../filmonov/`](../filmonov/).
Data: [`../../DATA_PATHS.md`](../../DATA_PATHS.md). Loop: [`../../LOOP.md`](../../LOOP.md). Desk: [`DESK_MEMO.md`](DESK_MEMO.md) · Use map: [`APPLICATIONS.md`](APPLICATIONS.md).

**Book:** SqueezeMetrics (`sqzme`), *The Implied Order Book* (GEX Ed., 6 July 2020). Slug: `squeeze_metrics`.

**Program status:** Pass **2b** on certified `panel_gex_options` **n=9** — **0 Promote**. DDOI=`PROXY_trade_flow_DDOI`; corr(GEX, HL RV)≈−0.22 (paper sign) but day-block CI crosses 0 + chrono range unstable + placebo/LOO fail → Hold. Dig: [`out/pass2/`](out/pass2/) · [`out/info_features/`](out/info_features/) · [`out/feature_stats/`](out/feature_stats/) · completeness [`out/panel_completeness/`](out/panel_completeness/).

**Shared lib:** [`../../lib/squeeze.py`](../../lib/squeeze.py) (BS δ/γ/vanna, DDOI, GEX/VEX/GEX+, squeeze) · loaders [`scripts/_data.py`](scripts/_data.py) · certified [`scripts/certified_panel.py`](scripts/certified_panel.py).  
**Do not merge** with [`../../lib/continuous.py`](../../lib/continuous.py) or [`../../lib/cdme.py`](../../lib/cdme.py).

**Status legend:** `todo` · `notes` · `candidates` · `pass1` · `iterate` · `exp_run` · `park`  
**Lenses:** `risk` · `info` · `exec` · `disc` · `cont` · `liq` · `mm`

---

## Two-pass checklist

### Pass 1 — faithfulness
- [x] PDF NOTES with page cites
- [x] Real HL+Deribit TOB + Deribit option IV; `trade_synth` quarantined
- [x] Baseline EXP_REPORT + notebooks on certified days
- [x] CANDIDATES Hold / Kill arb α

### Pass 2 — info / falsifiers
- [x] Stress/calm, lead-lag, markouts, incremental vs RV / squeeze / VEX
- [x] Chrono split + **day-block** bootstrap + placebo + venue-drop + LOO
- [x] spot_l2 appendix (n=4) · BTC widen probe (n_pass=1 blocked)
- [x] Signal board + DESK_MEMO + APPLICATIONS use-map
- [x] Notebooks desk_synthesis + info_stats_board + feature_stats

**Never soft-Promote TOB-cross as arb α.**

---

## Certified panel (locked)

| Panel | n | Days |
|-------|--:|------|
| `panel_gex_options` (primary) | **9** | 2026-09-14, 15, 16, 17, 18, 25, 26, 27, 2026-10-01 |
| `panel_core_2venue` | **9** | same |
| `panel_3venue_spot` | **4** | 2026-09-25, 26, 27, 2026-10-01 |
| `trade_synth` / `panel_3venue_any` | **0** | **QUARANTINED** |

See [`out/panel_completeness/REPORT.md`](out/panel_completeness/REPORT.md).

---

## Package roadmap

| Package | Paper focus | Pass 2 dig | Status | Path |
|---------|-------------|------------|--------|------|
| `ch00_overview` | Claim, crypto map | Signal roadmap | `exp_run` | [`chapters/ch00_overview/`](chapters/ch00_overview/) |
| `ddoi_positions` | DDOI (p. 3) | Trade-flow proxy honesty | `exp_run` | [`chapters/ddoi_positions/`](chapters/ddoi_positions/) |
| `gex_implied_book` | GEX (pp. 4–5) | RV/range corr + falsifiers | `exp_run` | [`chapters/gex_implied_book/`](chapters/gex_implied_book/) |
| `vex_vanna` | VEX (pp. 6–8) | Range co-move | `exp_run` | [`chapters/vex_vanna/`](chapters/vex_vanna/) |
| `squeeze_regimes` | GEX+ maps (pp. 9–11) | Scarcity / stress | `exp_run` | [`chapters/squeeze_regimes/`](chapters/squeeze_regimes/) |
| `robustness` | Falsifiers | Chrono / bootstrap / placebo | `exp_run` | [`chapters/robustness/`](chapters/robustness/) |
| `paper_shadow` | Living monitor | Promote-only wire | `pass1` | [`applications/paper_shadow/`](applications/paper_shadow/) |

---

## Promote rollup

| Candidate | Decision | One-line |
|-----------|----------|----------|
| *(none)* | — | **0 Promote** |

**Hold:** `risk.gex_exposure`, `risk.vex_exposure`, `risk.squeeze_intensity`, `liq.implied_book_scarcity`, `info.gex_range_incremental`, `info.squeeze_after_gex`, `info.vex_incremental`, `info.gex_leadlag_map`, `info.gex_markout_regimes`, `info.tod_factor_structure`, `info.stress_vs_calm`, `info.object_use_map`  
**Kill:** `alpha.tob_cross_arb`, `data.trade_synth`  
**Blockers:** verified option OI / DDOI; BTC widen ≥3 days; denser intraday IV for ToD GEX; CI/placebo/LOO

---

## Crypto adaptation defaults

| Paper | Desk |
|-------|------|
| SPX options + DDOI | Deribit ETH options IV + **trade-flow DDOI proxy** |
| GEX $/pt | BS γ · DDOI · spot (lot-scaled units) |
| VEX | BS vanna · DDOI |
| GEX+ heatmaps | Day panel + scarce flag; full (S,IV) map in lib |
| Visible LOB | HL+Deribit TOB co-move — **Kill** as α |

---

## Scripts

| Script | Role |
|--------|------|
| `exp_panel_completeness.py` | Certified panels |
| `exp_gex_panel.py` | Pass-1 GEX/VEX/GEX+ |
| `exp_ddoi_panel.py` | Trade-flow DDOI |
| `exp_vex_panel.py` / `exp_squeeze_regimes.py` | VEX / regimes |
| `exp_pass2_falsifiers.py` | Chrono / bootstrap / placebo |
| `exp_info_features.py` | Lead-lag / incremental / PCA |
