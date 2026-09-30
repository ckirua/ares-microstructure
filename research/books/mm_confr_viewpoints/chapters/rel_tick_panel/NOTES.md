# Relative-tick FM panel

**Book:** Rindi et al. MMCV #3 Paris 2014  
**PDF:** slides (local) · **Status:** `exp_run`  
**Raw:** [`../../_raw/`](../../_raw/) (local/gitignored)  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md) · Desk: [`../../DESK_MEMO.md`](../../DESK_MEMO.md)  
**Lib:** [`../../../../lib/ticksize.py`](../../../../lib/ticksize.py)  
**Pass-2 dig:** [`../../scripts/exp_pass2_info_exec.py`](../../scripts/exp_pass2_info_exec.py) → `out/rel_tick_panel/markout_quartile_within_venue.json`

---

## Pass 1 focus

FM-style: BBO depth, quoted/rel spread, volume vs τ/mid on HL+Deribit+Kraken (deck FM empirics; crypto adaptation table in CHAPTER_INDEX).

## Pass 2 dig

- Markout by rel-tick quartile; time-split; vs mmip `rel_tick_bps` (cross-link descriptor only).
- **Within-venue kill of x-venue confound:** hourly markout ~ rel_tick quartiles **inside HL only** and **inside Deribit only** (τ fixed; mid-driven rel_tick variation).

## Pass checklist

### Pass 1
- [x] Cite deck pages in NOTES
- [x] Implement on HL + Deribit + Kraken
- [x] EXP_REPORT with day-completeness
- [x] Draft CANDIDATES

### Pass 2
- [x] Info joins / falsifiers (within-venue hourly markout quartiles)
- [x] Signal board → DESK_MEMO

---

## Identification caveat

Cross-section day FM is mostly **venue τ gap** (HL 0.1 vs Deribit 0.05) rather than within-venue relative-tick variation. Pooled day-level markout-by-quartile (Q1≈48 bps mixed venues) is **confounded**. Within-venue hourly dig below is the honest info lens.

## Key numbers (ETH, 3 days × 3 venues)

| Object | Result |
|--------|--------|
| Day FM quoted_spread_bps ~ rel_tick | mean_slope ≈ −1.13e5, **t=−3.54**, n_groups=3 |
| Hour FM quoted_spread_bps ~ rel_tick | **t=−3.75** |
| Day FM relative_spread ~ rel_tick | **t=−3.54** |
| Day FM volume ~ rel_tick | **t=−2.09** |
| Day FM bbo_depth ~ rel_tick | **nan** (incomparable depth units / missing Kraken) |
| Time-split early / late t | **nan** / **−2.09** (early=1 day) |
| Spearman ρ(rel_tick, spread) | **−0.60**, CI95 ≈ [−0.92, 0.24] |

### Within-venue markout ~ rel_tick (hourly, Pass-2)

| Venue | n_hours | Q4−Q1 markout (bps) | Spearman ρ (CI95) | Gate |
|-------|---------|---------------------|-------------------|------|
| Hyperliquid | 56 | **+0.48** (Q1=0.52, Q4=1.00) | **0.034** [−0.22, 0.28] | Hold · info_monitor · not tradable |
| Deribit | 39 | **−31.3** (noisy; Q means 37 / −20 / −53 / 6) | **−0.214** [−0.52, 0.17] | Hold · CI includes 0 · not tradable |

Figs: `fig_markout_reltick_q_within_venue.png`, `fig_markout_reltick_q_hl.png`, `fig_markout_reltick_q_deribit.png`.
