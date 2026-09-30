# Market Microstructure in Practice — research index

Living map of book chapters → candidate signals/features/strategies → experiment status.
Book PDF + verbatim `_raw/` extracts: **local only** (gitignored). Data inventory: [`DATA_PATHS.md`](../../DATA_PATHS.md).
Loop / quality bar: [`LOOP.md`](../../LOOP.md). Desk synthesis: [`DESK_MEMO.md`](DESK_MEMO.md). Sibling program: [`../empirical_mm/`](../empirical_mm/) (Hasbrouck notes).

**Status legend:** `todo` · `notes` · `candidates` · `exp_run` · `iterate` · `park`

**Quality bar:** MM / quant-desk memo grade (precise defs, formulas, descriptive vs tradable vs execution heuristic, experiment hygiene, Promote/Hold/Kill, falsifiers, CIs). Do not mark `exp_run` complete without NOTES + CANDIDATES + EXP_REPORT + notebook.

**Program status (2026-09-30):** Intro · Ch.1 · Ch.2 · Ch.3 · App.A · classic micro package · Promote hardening — **desk-ready expansion**.

---

## Promote rollup (post-hardening MM desk scan)

Source of truth: [`out/promote_hardening/`](out/promote_hardening/).

| Candidate | Chapter | Desk use (one line) |
|-----------|---------|---------------------|
| `liq.quoted_spread_bps` | Intro | Cost floor / make–take |
| `liq.depth_imbalance` | Intro | Skew / inventory lean |
| `liq.role_blur_l1` | Intro | Flicker vs size monitor |
| `frag.update_share` | 1 | Flicker / toxicity when updates ≫ size |
| `frag.crossed_nbbo` | 1 | Hard SOR / no-naive-take gate |
| `tick.frac_one_tick` | 1 / A.5 | Tick-constrained quote regime |
| `tick.spread_bps` | 1 | Cost floor |
| `tick.spread_leeway` | A.5 | Headroom above 1 tick |
| `tick.rel_tick_bps` | A.5 | Relative tick vs mid |
| `vol.curve_intraday` | 2 | Hourly size / risk schedule |
| `vol.fei_hourly` | 2 | Temporal concentration |
| `spread.vol_link` | 2 | Widen with short-horizon vol |
| `impact.rho_slope` | 3 | Participation → impact (directional) |
| `impact.temp_perm` | 3 | Temporary vs permanent split |
| `impact.algo_pov_sim` | 3 | Sim POV impact prior |
| `sched.pov_envelope` | 3 | POV participation envelope |
| `lsor.latency_depth_haircut` | 3 | Haircut visible depth for latency |
| `style.extraday_idio` | 3 | Sys vs idio variance |
| `sched.vol_curve_share` | A.6 | Real \(V_n\) share curve |
| `sched.expectation_min` | A.6 | Expectation-minimizing schedule |
| `epps.xvenue_corr` | A.12 | Cross-venue corr vs lag |
| `hawkes.count_acf` | A.11 | Trade-count clustering |
| `tox.markout_1s` | classic | Maker adverse-selection proxy |
| `spread.effective_vs_quoted` | classic | TCA effective spread |
| `book.resilience` | classic | L0 depth refill after large trades |

**Killed this pass:** `impact.kappa_gamma` (R²≈0.015), `spread.roll` (unidentified).  
**Hold (notable):** `sess.utc_hour_share` (incomplete UTC coverage), Harris MLE, Hawkes MoM, mean–var λ, 1m xasset Epps.

---

## Roadmap (chapters)

| ID | Title | Focus | Status |
|----|-------|-------|--------|
| **Intro** | Liquidity, best execution, role blur | Extractable MM features | **`exp_run`** → `chapters/intro_liquidity/` |
| **Ch.1** | Fragmentation at any scale | FEI, SOR, tick | **`exp_run`** |
| **Ch.2** | Stakes / roots of fragmentation | Vol curves, spread↔vol | **`exp_run`** |
| **Ch.3** | Optimal organisations / trading | Impact, POV, idio | **`exp_run`** |
| **App.A** | Quantitative appendix | Harris, schedule, Epps, Hawkes | **`exp_run`** |
| **Classic** | Under-covered micro | Markout, spreads, resilience, sessions | **`exp_run`** → `chapters/classic_micro/` |
| **App.B** | Glossary | Term lookup | — |

---

## Candidate → experiment matrix (delta vs baseline)

| Candidate | Type | Status | Decision | Artifact |
|-----------|------|--------|----------|----------|
| `liq.role_blur_l1` | D | exp_run | **Promote** | `out/intro_liquidity/` |
| `liq.depth_imbalance` | D→E | exp_run | **Promote** | same |
| `liq.quoted_spread_bps` | D | exp_run | **Promote** | same |
| `tox.markout_1s` | D→E | exp_run | **Promote** | `out/classic_micro/` |
| `spread.effective_vs_quoted` | D | exp_run | **Promote** | same |
| `book.resilience` | D | exp_run | **Promote** | same |
| `sess.utc_hour_share` | D | exp_run | **Hold** | thin UTC coverage |
| `spread.roll` | D | exp_run | **Kill** | cov≥0 |
| `impact.kappa_gamma` | D fit | exp_run | **Kill** | R²≈0.015 |

Prior Ch.1–3 / App.A matrix retained in git history / chapter `CANDIDATES.md`; hardening overrides in `out/promote_hardening/`.

---

## Headline results (expansion)

### Intro
Role-blur max L1 ≈ **0.78** (HL size-heavy / Lit update-heavy); HL spread train/test **stable**.

### Classic micro
Markout 1s ≈ **0.45 bps** (CI>0); effective ≈ **0.89** vs quoted ≈ **0.39**; realized 1s ≈ **0** → toxicity dominates make P&L; Roll **Kill**; resilience **Promote** (n≈600 large trades).

### Hardening
24 Promote · 5 Hold · 2 Kill — see [`DESK_MEMO.md`](DESK_MEMO.md).

---

## Layout

```
research/
  LOOP.md                   ← program-wide quality bar
  DATA_PATHS.md             ← shared data inventory
  lib/                      ← shared FEI, spreads, markout, Epps, POV, stats
  books/
    README.md
    mmip/                   ← Market Microstructure in Practice
      BOOK.md
      CHAPTER_INDEX.md
      DESK_MEMO.md
      notebooks/desk_synthesis.ipynb
      chapters/
        intro_liquidity/
        classic_micro/
        ch01_fragmentation/
        ch02_stakes/
        ch03_optimal_trading/
        appendix_quant/
      scripts/
        exp_intro_liquidity.py
        exp_classic_micro.py
        exp_harden_promotes.py
        exp_ch01_*.py …
      out/
        intro_liquidity/
        classic_micro/
        promote_hardening/
        ch01_fragmentation/ …
```

Hard rule: **no ClickHouse MCP**. Prefer collector parquet → warehouse `open_day` → public REST.
