# Ch.00 — Overview: tick-size RQs

**Book:** Rindi et al. MMCV #3 Paris 2014  
**PDF:** slides (local) · **Status:** `exp_run`  
**Raw:** [`../../_raw/`](../../_raw/) (local/gitignored)  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md) · Desk: [`../../DESK_MEMO.md`](../../DESK_MEMO.md)  
**Lib:** [`../../../../lib/ticksize.py`](../../../../lib/ticksize.py)

---

## Pass 1 focus

Large vs small Δτ; relative tick; liquid vs thin; reading order (deck framing).

### Deck citations
- Absolute vs relative tick / prediction tables: slides **pp. 20–29**
- Liquid vs less-liquid undercutting channel: **pp. 21–24**
- Relative-tick equivalence (↓τ ≈ ↑v): **p. 26**

## Pass 2 dig

Taxonomy vs mmip `tick.rel_tick_bps` / `spread_leeway` / `frac_one_tick`: descriptors cross-linked; this book owns prediction panels + FM/x-venue tests. Signal roadmap → DESK_MEMO.

## Pass checklist

### Pass 1
- [x] Cite deck pages in NOTES
- [x] Implement on HL + Deribit + Kraken
- [x] EXP_REPORT with day-completeness
- [x] Draft CANDIDATES

### Pass 2
- [x] Info joins / falsifiers
- [x] Signal board → DESK_MEMO

---

## Reading order

1. `ch00_overview` — RQs + taxonomy vs mmip `tick.*`
2. `emp_predictions` — sign matrix + MQ vector (LOB theory NOTES)
3. `rel_tick_panel` ∥ `tick_constraint`
4. `liq_book_split` ∥ `xvenue_tick`
5. Hardening → DESK_MEMO + desk_synthesis

## Sample snapshot (ETH slice)

| Venue | τ | Source | Typical rel_tick_bps | Tick-constrained day? |
|-------|---|--------|----------------------|------------------------|
| hyperliquid | 0.1 | known | ~0.372 | yes (~99% frac_one_tick) |
| deribit | 0.05 | known | ~0.186 | no (median ~10–20 ticks) |
| kraken | ~0.1 | inferred | ~0.372 | no (trade_synth BBO) |

Days: 2026-09-26, 2026-09-27, 2026-09-30 — **9/9** complete venue-days; TOB 9/9.
