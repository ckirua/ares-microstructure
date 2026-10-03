# cd_me — research index

Living map of Huang–Ranaldo–Schrimpf–Somogyi (2021) packages → candidates → experiment status.
Book PDF + `_raw/` extracts: **local only** (gitignored). Siblings: [`../v_shapes/`](../v_shapes/) · [`../filmonov/`](../filmonov/) · [`../empirical_mm/`](../empirical_mm/).
Data: [`../../DATA_PATHS.md`](../../DATA_PATHS.md). Loop: [`../../LOOP.md`](../../LOOP.md). Desk: [`DESK_MEMO.md`](DESK_MEMO.md) · Use map: [`APPLICATIONS.md`](APPLICATIONS.md).

**Book:** Huang et al., *Constrained Dealers and Market Efficiency* (Nov 2021), SSRN 3960577. Slug: `cd_me`.

**Program status:** **Pass 2.5 on certified real-quote panel** — **0 Promote**. Retracted “10/10 three-venue + trade_synth.” Primary `panel_core_2venue` **n=9** (2026-09-14…18, 25–27, 2026-10-01); spot_l2 subpanel **n=4**; DCM incremental after RV **Hold**; elasticity after RV **Hold**. Dig: [`out/info_features/`](out/info_features/) · [`out/feature_stats/`](out/feature_stats/) · completeness [`out/panel_completeness/`](out/panel_completeness/). LSTAR/model **park**. BTC widen **next** (DESK_MEMO).

**Shared lib:** [`../../lib/cdme.py`](../../lib/cdme.py) (VLOOP/TCOST/PIM, DCM proxies, elasticity) · loaders [`scripts/_data.py`](scripts/_data.py) (HL + Deribit + Kraken spot_l2) · certified [`scripts/certified_panel.py`](scripts/certified_panel.py) · stats [`scripts/_stats_info.py`](scripts/_stats_info.py).  
**Do not merge** with [`../../lib/continuous.py`](../../lib/continuous.py) Cont–Kukanov OFI.

**Reuse (do not rewrite):** empirical_mm Huang–Stoll inventory proxies; v_shapes / filmonov warehouse+collector loaders; xarb TOB panels.

**Status legend:** `todo` · `notes` · `candidates` · `pass1` · `iterate` · `exp_run` · `park`  
**Lenses:** `risk` · `info` · `exec` · `disc` · `cont` · `liq` · `mm`

A package is **not** `exp_run`-complete after Pass 1 alone. Tracking path: **`pass1` → `iterate` → `exp_run`**.

---

## Two-pass checklist (every package)

### Pass 1 — faithfulness
- [x] Extract PDF theory/formulas into NOTES (pages cited) — core packages
- [x] Implement paper object on real **HL + Deribit** TOB (+ Kraken **spot_l2** when dense; `trade_synth` quarantined)
- [x] Baseline plots + EXP_REPORT with sample / window / **day-completeness** flags
- [x] Draft CANDIDATES (tentative Hold / Kill arb α)

### Pass 2 — deep info / signals (mandatory)
- [x] What information does the object carry? (funding/basis/vol/imbalance joins; stress vs calm)
- [x] Signal hypotheses labeled honestly: *risk monitor* vs *tradable* vs *exec throttle*
- [x] Competing defs (native triangle vs cross-venue LOP; CDS/VaR vanity Kill)
- [x] Falsifiers: time-split, block bootstrap, placebo regimes (venue-drop deferred — synth honesty)
- [x] CANDIDATES + notebook “Signal board” + DESK_MEMO entry

### Pass 2.5 — info / stats expand (filmonov-style)
- [x] Lead-lag / ToD / factor commonality / incremental RV controls
- [x] Day-block CIs · chrono splits · Spearman · light Fisher-z Bayes (descriptive)
- [x] `info.*` candidates + [`APPLICATIONS.md`](APPLICATIONS.md) use map
- [x] Notebook [`notebooks/info_stats_board.ipynb`](notebooks/info_stats_board.ipynb)

**Quant bar:** precise units/clocks; ID assumptions stated; effect sizes + CIs; no Promote without a falsifier attempt; notebooks memo-quality. **Never soft-Promote TOB-cross as arb α.**

---

## Certified panel (locked)

| Panel | n | Days |
|-------|--:|------|
| `panel_core_2venue` (primary) | **9** | 2026-09-14, 15, 16, 17, 18, 25, 26, 27, 2026-10-01 |
| `panel_3venue_spot` (secondary) | **4** | 2026-09-25, 26, 27, 2026-10-01 |
| `trade_synth` / `panel_3venue_any` | **0** | **QUARANTINED** |

Excluded: 19 (PIM empty), 20–24 (thin/missing TOB), 28–30 (thin HL/DB/DCM). See [`out/panel_completeness/REPORT.md`](out/panel_completeness/REPORT.md).

---

## Package roadmap

| Package | Paper focus (Pass 1) | Pass 2 dig | Status | Path |
|---------|----------------------|------------|--------|------|
| `ch00_overview` | §1 claim, PIM taxonomy, crypto map, reading order | Signal roadmap vs xarb / basis monitors | `notes` | [`chapters/ch00_overview/`](chapters/ch00_overview/) |
| `pim_vloop_tcost` | §2 Eqs 1–3 on HL↔Deribit (+ KR spot_l2) | Commonality VLOOP↔TCOST; stress vs calm; lead-lag | `exp_run` | [`chapters/pim_vloop_tcost/`](chapters/pim_vloop_tcost/) |
| `dcm_proxies` | §3 DCM from public funding/basis/vol/imbalance | PC stability; incremental vs RV; Kill vanity CDS | `exp_run` | [`chapters/dcm_proxies/`](chapters/dcm_proxies/) |
| `elasticity_regimes` | §3 VLM↔PIM corr; constrained elasticity drop | Placebo; RV controls; denser buckets | `exp_run` | [`chapters/elasticity_regimes/`](chapters/elasticity_regimes/) |
| `lstar_panel` | §3 LSTAR / logistic smooth transition | Day-panel FE; Kill if γ/c unidentified | `park` | [`chapters/lstar_panel/`](chapters/lstar_panel/) |
| `model_sim` | §4 constrained-dealer partial eq | Crypto-calibrated DGP; qualitative match only | `park` | [`chapters/model_sim/`](chapters/model_sim/) |
| `robustness` | §5 falsifiers | Block bootstrap, venue drop, BTC widen | `Hold` (checklist) | [`chapters/robustness/`](chapters/robustness/) |
| `paper_shadow` | Living PIM/DCM monitor harness | Telemetry only until Promote; `live_orders=false` | `pass1` | [`applications/paper_shadow/`](applications/paper_shadow/) · [`chapters/paper_shadow/`](chapters/paper_shadow/) |

**Pass 2 slice (revised):** certified `panel_core_2venue` n=9 real quotes → DCM̂ + elasticity **n=88** → falsifiers in `out/pass2/` → Hold board, **0 Promote**. Prior synth-as-3-venue **retracted**.  
**Pass 2.5 (revised):** re-ran on certified days → `out/info_features/` + `out/feature_stats/` → `info.*` Holds.

---

## Promote rollup

| Candidate | risk | info | exec | disc | cont | liq | mm | Ch | One-line use |
|-----------|:----:|:----:|:----:|:----:|:----:|:---:|:--:|----|--------------|
| *(none yet)* |  |  |  |  |  |  |  |  | Pass-2 / 2.5 Hold board only |

**Kill / Hold (pre-registered):**
- **Kill (vanity):** bank VaR / CDS single-name analogues without crypto desk mapping
- **Kill (α cosplay):** TOB-cross as naked arb α — detection/monitor only
- **Hold (Pass-2):** `risk.pim_cross_venue`, `info.vloop_tcost_commonality`, `risk.dcm_pc1`, `liq.elasticity_regime`
- **Hold (Pass-2.5 info):** `info.pim_dcm_incremental`, `info.elasticity_after_rv`, `info.vloop_tcost_stress_split`, `info.object_leadlag_map`, `info.kraken_spot_vs_2venue`, `info.day_factor_commonality`, `info.object_use_map`
- **Park:** `disc.lstar_gmm`, `disc.constrained_dealer_dgp`; native ETH–BTC–USD triangles until multi-pair TOB confirmed; **BTC info widen**
- **Quarantine:** Kraken `trade_synth` — PROXY/NOT TOB; never primary

---

## Crypto adaptation defaults

| Paper | Desk mapping |
|-------|----------------|
| CLS FX triplets / triangular LOP | Cross-venue LOP on ETH (then BTC) across **HL + Deribit** (+ Kraken spot_l2 when dense) |
| VLOOP | \|log(mid_i / mid_j)\| on latency-aligned TOB |
| TCOST | Sum of relative half-spreads on arb legs |
| PIM | VLOOP + \|TCOST\| when VLOOP > 0 |
| DCM (dealer constraint measure) | PC1 of \|funding\|, \|perp basis\|, RV, trade-imbalance inventory proxy |
| Volume / VLM | Trade intensity / notional on home venue (HL primary) |
| Bank VaR / CDS | **Kill** vanity — no public crypto analogue in Pass 1 |
| RTH / FX session | **UTC-day** panels; 24/7 tape |

---

## Notebook / figure index

Executed chapter notebooks (memo-quality analysis over certified `out/` artifacts; regenerate companion figs with `scripts/build_notebook_figs.py`).

| Notebook | Focus / plots | Gate row |
|----------|---------------|----------|
| [`chapters/ch00_overview/ch00_overview.ipynb`](chapters/ch00_overview/ch00_overview.ipynb) | Taxonomy map; day-mean PIM / DCM explained-var / pooled elasticity bars | Hold / Kill / Park roadmap |
| [`chapters/pim_vloop_tcost/pim_vloop_tcost.ipynb`](chapters/pim_vloop_tcost/pim_vloop_tcost.ipynb) | Pass-1 figs + ToD heatmap, VLOOP↔TCOST scatter, stress/calm split, TOB coverage | Hold PIM + Kill α |
| [`chapters/dcm_proxies/dcm_proxies.ipynb`](chapters/dcm_proxies/dcm_proxies.ipynb) | Loadings heatmap, explained var, hourly DCM̂ vs PIM | Hold DCM̂ + Kill CDS |
| [`chapters/elasticity_regimes/elasticity_regimes.ipynb`](chapters/elasticity_regimes/elasticity_regimes.ipynb) | Regime scatter, per-day corr, chronological split | Hold elasticity |
| [`chapters/lstar_panel/lstar_panel.ipynb`](chapters/lstar_panel/lstar_panel.ipynb) | Park rationale + toy logistic \(G\) + observed \(G(\widehat{\mathrm{DCM}})\) | **Park** |
| [`chapters/model_sim/model_sim.ipynb`](chapters/model_sim/model_sim.ipynb) | Park rationale + toy η→spread/PIM curves | **Park** |
| [`chapters/robustness/robustness.ipynb`](chapters/robustness/robustness.ipynb) | §5 checklist; chrono split + placebo DCM shuffle preview; loads `out/pass2/` if present | Hold falsifier board |
| [`notebooks/desk_synthesis.ipynb`](notebooks/desk_synthesis.ipynb) | Multi-section rollup + shadow board + chapter links | Desk SoT |
| [`notebooks/info_stats_board.ipynb`](notebooks/info_stats_board.ipynb) | Pass-2.5 info dig + stats figs + candidate board | **info.* Hold** |

**Figure dirs**

| Path | Contents |
|------|----------|
| `out/panel_completeness/figs/` | completeness heatmap |
| `out/pim_vloop_tcost/figs/` | `fig_pim_hourly`, `fig_pim_day_means`, `fig_vloop_tcost_corr` |
| `out/dcm_proxies/figs/` | `fig_dcm_coverage` |
| `out/elasticity_regimes/figs/` | `fig_elasticity_by_day`, `fig_elasticity_pooled_ci` |
| `out/desk_synthesis/figs/` | `signal_board`, `fig_pim_tod`, `fig_vloop_tcost_scatter`, `fig_elasticity_scatter`, `fig_day_pim_means_certified` |
| `out/info_features/figs/` | lead-lag, incremental partials, ToD, Kraken mode, stress, day factor, use map |
| `out/feature_stats/figs/` | univariate hists, corr forest, ToD heatmap, chrono split, Bayes CrI, IRF |

**Honesty:** Certified primary = **HL↔Deribit real quotes** (n=9). Kraken = dense `spot_l2` only (n=4 subpanel). `trade_synth` **QUARANTINED** — never primary 3-venue. Never soft-Promote TOB-cross α.
