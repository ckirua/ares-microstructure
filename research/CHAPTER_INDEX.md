# Market Microstructure in Practice — research index

Living map of book chapters → candidate signals/features/strategies → experiment status.
Book PDF: `0675_Market Microstructure in Practice.pdf` (Lehalle & Laruelle, World Scientific, 2014).
Raw extracts: `research/_raw/`. Data inventory: [`DATA_PATHS.md`](DATA_PATHS.md).
Loop / quality bar: [`LOOP.md`](LOOP.md).

**Status legend:** `todo` · `notes` · `candidates` · `exp_run` · `iterate` · `park`

**Quality bar:** MM / quant-desk memo grade (precise defs, formulas, descriptive vs tradable vs execution heuristic, experiment hygiene, Promote/Hold/Kill). Do not mark `exp_run` complete without NOTES + CANDIDATES + EXP_REPORT + notebook.

**Program status (2026-09-30):** Ch.1 · Ch.2 · Ch.3 · App.A are all **`exp_run` complete**. Pipeline finished — further work is optional polish / Hold iterates only (see [`LOOP.md`](LOOP.md)).

---

## Promote rollup (MM desk scan)

| Candidate | Chapter | Desk use (one line) |
|-----------|---------|---------------------|
| `frag.update_share` | 1 | Flicker / toxicity monitor when updates ≫ size |
| `frag.crossed_nbbo` | 1 | Hard SOR / no-naive-take gate |
| `tick.frac_one_tick` | 1 / A.5 | Tick-constrained quote regime |
| `tick.spread_bps` | 1 | Cost floor / make–take input |
| `tick.spread_leeway` | A.5 | Headroom above 1 tick for quote skew |
| `tick.rel_tick_bps` | A.5 | Relative tick vs mid (regime / venue compare) |
| `vol.curve_intraday` | 2 | Hourly size / risk schedule |
| `vol.fei_hourly` | 2 | Temporal concentration monitor |
| `spread.vol_link` | 2 | Widen quotes with short-horizon vol |
| `impact.rho_slope` | 3 | Participation → impact slope |
| `impact.temp_perm` | 3 | Temporary vs permanent impact split |
| `impact.algo_pov_sim` | 3 | Simulated single-algo POV + impact prior |
| `sched.pov_envelope` | 3 | POV participation envelope |
| `lsor.latency_depth_haircut` | 3 | Haircut visible depth for latency |
| `style.extraday_idio` | 3 | Sys vs idio variance (BTC/ETH/SOL β) |
| `sched.vol_curve_share` | A.6 | Real \(V_n\) share curve for scheduling |
| `sched.expectation_min` | A.6 | Expectation-minimizing schedule heuristic |
| `epps.xvenue_corr` | A.12 | Cross-venue corr vs lag (sync / hedge) |
| `hawkes.count_acf` | A.11 | Trade-count clustering / self-excitement |

---

## Parallel ownership (historical)

| Package | Path | Owner | Status |
|---------|------|-------|--------|
| **Ch.1** | `chapters/ch01_fragmentation/` | Coordinator | **Complete** |
| **Ch.2** | `chapters/ch02_stakes/` | Coordinator | **Complete** |
| **Ch.3** | `chapters/ch03_optimal_trading/` | Sibling | **Complete** |
| **App.A** | `chapters/appendix_quant/` | Sibling | **Complete** |

---

## Roadmap (chapters)

| ID | Title (book) | PDF pp. | Focus for trading research | Status | Owner |
|----|--------------|---------|----------------------------|--------|-------|
| **Intro** | Introduction — liquidity, regulation, best execution, role blur | 28–55 | Context + vocabulary; no primary α yet | `notes` | — |
| **Ch.1** | Monitoring the Fragmentation at Any Scale | 56–135 | Market share, FEI/entropy, SOR, tick size, dark pools | **`exp_run`** | coordinator |
| **Ch.2** | Understanding the Stakes and the Roots of Fragmentation | 136–211 | Intraday volume curves, spread↔vol↔share, HFT / systemic | **`exp_run`** | coordinator |
| **Ch.3** | Optimal Organisations for Optimal Trading | 212–247 | Trading-stack I/O, market impact, liquidity-seeking algos | **`exp_run`** | sibling |
| **App.A** | Quantitative Appendix | 248–315 | Harris tick, schedule on \(V_n\), xvenue Epps, Hawkes ACF, FEI↔Ch.1 | **`exp_run`** | sibling |
| **App.B** | Glossary | 316–323 | Term lookup | — | — |

---

## Candidate → experiment matrix

| Candidate | Chapter | Type | Data plane | Status | Decision | Artifact |
|-----------|---------|------|------------|--------|----------|----------|
| `frag.fei_tob_size` | 1 / A.1 | D regime | collector TOB HL/Lit/RX | exp_run | Hold | `out/ch01_fragmentation/` |
| `frag.update_share` | 1 | D monitor | same | exp_run | **Promote** | same |
| `frag.crossed_nbbo` | 1.2 | E gate | aligned multi-venue TOB | exp_run | **Promote** | same |
| `frag.duplicate_best` | 1.2 | E | same | exp_run | **Kill** | rare |
| `tick.frac_one_tick` | 1.3 / A.5 | D→quote | TOB + inferred tick | exp_run | **Promote** | ch01 + appendix |
| `tick.spread_bps` | 1.3 | D | same | exp_run | **Promote** | `out/ch01_fragmentation/` |
| `tick.spread_leeway` | A.5 | D regime | collector TOB | exp_run | **Promote** | `out/appendix_quant/` |
| `tick.rel_tick_bps` | A.5 | D | same | exp_run | **Promote** | same |
| `harris.mle` | A.5 | D fit | same | exp_run | **Hold** | MLE unstable / unused |
| `frag.fei_trade` (spatial) | 1 | D | multi-venue tape | iterate | Hold | temporal HL hourly only |
| `vol.curve_intraday` | 2.1 | D schedule | warehouse `trade` | exp_run | **Promote** | `out/ch02_stakes/` |
| `vol.fei_hourly` | 2.1 | D monitor | same | exp_run | **Promote** | same |
| `spread.vol_link` | 2.2 | D→E quote | BBO + mid ret | exp_run | **Promote** | same |
| `spread.tight_notional_share` | 2.2 | D | same | exp_run | **Kill** | π≈0.33 |
| `share.spread_elasticity` | 2.2 | T | multi-venue trades | todo | Hold | needs Lit/RX tape |
| `impact.rho_slope` | 3.2 | D→E | HL trade tape (5m) | exp_run | **Promote** | `out/ch03_optimal_trading/` |
| `impact.temp_perm` | 3.2 | D | same | exp_run | **Promote** | same |
| `impact.algo_pov_sim` | 3.2 | D/E | HL tape + sim POV | exp_run | **Promote** | `out/ch03_pov_idio/` |
| `style.extraday_idio` | 3.2 | D | Deribit BTC/ETH/SOL 1m | exp_run | **Promote** | same |
| `sched.pov_envelope` | 3.3 | E | same | exp_run | **Promote** | `out/ch03_optimal_trading/` |
| `lsor.latency_depth_haircut` | 3.1 / SOR | E | TOB + latency | exp_run | **Promote** | same |
| `impact.kappa_gamma` | 3.2 | D fit | HL tape | exp_run | **Hold** | R²≈0.015 |
| `sched.vol_curve_share` | A.6 | D/E | HL real \(V_n\) | exp_run | **Promote** | `out/appendix_quant/` |
| `sched.expectation_min` | A.6 | E | HL \(V_n/\sigma_n\) | exp_run | **Promote** | same |
| `sched.mean_variance` | 3.3 / A.6 | E toy | vol curve + σ | exp_run | **Hold** | λ / mean–var uncalibrated |
| `epps.xvenue_corr` | A.12 | D/E | HL mid vs Deribit mark | exp_run | **Promote** | same |
| `epps.xasset_corr` | A.12 | D | Deribit ETH–BTC 1m | exp_run | **Hold** | already high @60s |
| `hawkes.count_acf` | A.11 | D | HL trade 1s counts | exp_run | **Promote** | same |
| `hawkes.branching_mom` | A.11 | D | MoM \(R=\alpha/\beta\) | exp_run | **Hold** | indicative ≠ MLE |

---

## Ch.2 headline results (coordinator)

| Metric | Value |
|--------|-------|
| Mean U-shape ratio | **0.558** (inverted vs equity) |
| Mean hourly FEI | **0.892** |
| Peak hour | **18 UTC** (~12.4% share) |
| Mean corr(spread, \|Δlog mid\|) | **0.327** |
| Mean π_tight | **0.334** |

Notebook: `chapters/ch02_stakes/ch02_stakes.ipynb`

---

## Ch.3 headline results (sibling)

| Metric | Value |
|--------|-------|
| Sample | HL ETH **917k** trades · **1424×5m** buckets |
| Spearman(ρ, impact) | **≈0.19** |
| High-ρ impact | **≈7.5 bps** |
| Mean \(I_{\mathrm{temp}}\) @ +5m | **0.23 bps** |
| Sim POV \(I_{\mathrm{model}}\) @ π=1%→20% | **0.57 → 2.55 bps** |
| ETH β vs BTC (1m) | **≈0.93** · sys/idio **67%/33%** |

**Promote:** `impact.rho_slope`, `impact.temp_perm`, `impact.algo_pov_sim`, `style.extraday_idio`, `sched.pov_envelope`, `lsor.latency_depth_haircut`  
**Hold:** `impact.kappa_gamma` (R²≈0.015)

Paths: `chapters/ch03_optimal_trading/` · `out/ch03_optimal_trading/` · `out/ch03_pov_idio/` · `scripts/exp_ch03_trading_impact.py` · `scripts/exp_ch03_pov_idio.py`

---

## App.A headline results (sibling)

| Topic | Coverage |
|-------|----------|
| Harris tick | `tick.frac_one_tick`, `tick.spread_leeway`, `tick.rel_tick_bps` (MLE **Hold**) |
| Schedule on real \(V_n\) | `sched.vol_curve_share`, `sched.expectation_min` (mean–var λ **Hold**) |
| Xvenue Epps | `epps.xvenue_corr` (**Promote**); 1m xasset Epps **Hold** |
| Hawkes | `hawkes.count_acf` (**Promote**); MoM \(R\) **Hold** |
| FEI | Linked to Ch.1 / A.1 (TOB FEI Hold as trade-share substitute) |

| Metric | Value |
|--------|-------|
| HL / Lit frac 1-tick | **0.991** / **0.152** |
| Mean L1(E-min vs uniform) | **0.397** |
| Xvenue Epps corr @5s → 600s | **~0 → 0.87** |
| Trade-count ACF lag1 | **0.17–0.44** |

**Promote:** `tick.frac_one_tick`, `tick.spread_leeway`, `tick.rel_tick_bps`, `sched.vol_curve_share`, `sched.expectation_min`, `epps.xvenue_corr`, `hawkes.count_acf`  
**Hold:** Harris MLE, mean–var λ, 1m xasset Epps, Hawkes MoM \(R\)

Paths: `chapters/appendix_quant/` · `out/appendix_quant/` · `scripts/exp_appa_toolbox.py` · notebook `appendix_quant.ipynb`

---

## Optional iterate backlog (not blocking)

1. Ch.1 spatial multi-venue trade FEI (Hold).
2. Funding-conditioned volume curves; calibrate `sched.mean_variance` with TCA fills.
3. Tick-level xasset Epps (finer than 1m marks); Harris MLE if denser tick panel.

---

## Layout

```
research/
  CHAPTER_INDEX.md
  LOOP.md
  DATA_PATHS.md
  _raw/
  chapters/
    ch01_fragmentation/       ← COMPLETE
    ch02_stakes/              ← COMPLETE
    ch03_optimal_trading/     ← COMPLETE
    appendix_quant/           ← COMPLETE
  scripts/
    exp_ch01_fragmentation.py
    exp_ch01_trade_fei.py
    exp_ch02_stakes.py
    exp_ch03_trading_impact.py
    exp_ch03_pov_idio.py
    exp_appa_toolbox.py
  out/
    ch01_fragmentation/
    ch02_stakes/
    ch03_optimal_trading/
    ch03_pov_idio/
    appendix_quant/
```

Hard rule: **no ClickHouse MCP**. Prefer collector parquet → warehouse `open_day` → public REST.
