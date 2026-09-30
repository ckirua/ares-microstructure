# Empirical predictions — expected-sign matrix

**Book:** Rindi et al. MMCV #3 Paris 2014  
**PDF:** slides (local) · **Status:** `exp_run`  
**Raw:** [`../../_raw/`](../../_raw/) (local/gitignored)  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md) · Desk: [`../../DESK_MEMO.md`](../../DESK_MEMO.md)  
**Lib:** [`../../../../lib/ticksize.py`](../../../../lib/ticksize.py)

---

## Pass 1 focus

Codify sign tables **pp. 20–29** + LOB undercutting story; MQ vector in `ticksize.py`. LOB game = NOTES only.

## Pass 2 dig

Map each cell to desk metric + falsifier; Kill welfare/SEC cells; Kill sign-scorecard-as-tradable when hit_rate fragile.

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

## LOB undercutting story (NOTES only — no production game sim)

Deck **pp. 21–24**: large absolute tick reduction on **liquid** books enables undercutting at the BBO
(traders switch MO→LO → MQ improves / volume↑). On **less-liquid** books there is nothing to undercut
but fear of being undercut → switch LO→MO → MQ deteriorates. Small reductions: price improvement from
LO < execution-probability loss → no undercutting; LO→MO. Welfare unobservable on crypto desk → **Kill**.

## Expected-sign matrix

Implemented in `research.lib.ticksize.expected_sign_matrix` from tables pp. 20–29.

Regimes: `large_abs_reduction`, `small_abs_reduction`, `large_abs_increase`, `small_abs_increase`, `rel_tick_up`, `rel_tick_down`.  
Metrics: quoted/relative spread, BBO/total depth, volume, **welfare (Kill)**.

## Empirical scorecard (ETH, n=9 venue-days)

| metric | Spearman ρ | obs_sign | expected (`rel_tick_up`) | match |
|--------|------------|----------|--------------------------|-------|
| relative_spread | −0.600 | +1 | −1 | MISS |
| quoted_spread | −0.600 | +1 | 0 | SKIP |
| bbo_depth | −0.714 | −1 | +1 | MISS |
| volume | −0.600 | −1 | −1 | HIT |

**hit_rate = 0.333** (1 hit / 2 miss / 1 skip) → Kill as tradable; Hold matrix as theory codification.
