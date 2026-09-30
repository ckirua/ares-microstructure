# Liquid vs less-liquid split

**Book:** Rindi et al. MMCV #3 Paris 2014  
**PDF:** slides (local) · **Status:** `exp_run`  
**Raw:** [`../../_raw/`](../../_raw/) (local/gitignored)  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md) · Desk: [`../../DESK_MEMO.md`](../../DESK_MEMO.md)  
**Lib:** [`../../../../lib/ticksize.py`](../../../../lib/ticksize.py)  
**Local runner:** [`_run_local.py`](_run_local.py) → [`../../out/liq_book_split/`](../../out/liq_book_split/)

---

## Deck citations (Pass 1)

- **pp. 20–22 / 29:** large tick Δ — liquid vs less-liquid books flip MQ signs (spreads, depth, volume).
- **p. 26:** relative-tick equivalence — ↓τ ≈ ↑v for several quality metrics.
- Crypto adaptation: terciles by quoted spread bps / BBO depth / trade intensity (UTC-day), not CRSP.

## Pass 1 focus

- `liquid_book_classifier` on day-panel `quoted_spread_bps`.
- Heterogeneous Spearman ρ(rel_tick, spread/depth) within liquid vs thin.
- Hourly interaction scatter + slope by book_liq (native TOB).

## Pass 2 dig

- **Placebo:** hours with mid range ≥ 5 bps and rel_tick range/level < 2% (τ fixed). Expect small Δ quoted spread if channel is relative tick.
- **Make/take:** expect ρ(Δrel_tick, undercut_rate) < 0 on liquid (rel↓ → undercut↑); weaker/flipped on thin.
- Kraken `trade_synth` excluded from make/take & placebo native tests.

## Observed (ETH, 2026-09-26/27/30)

- Terciles venue-confounded: HL=liquid, Kraken synth=mid, Deribit=less_liquid (n=3 each).
- ρ(rel_tick, spread): liquid=+1.0, thin=−0.5 (fragile / confounded).
- Placebo: 55 hours; mean |Δqs| ≈ **0.0007 bps** — MQ barely moves when rel_tick flat.
- Make/take: liquid ρ(Δrel, undercut) ≈ **+0.01** (does **not** support deck undercutting channel on this slice).

## Pass checklist

### Pass 1
- [x] Cite deck pages in NOTES
- [x] Implement on HL + Deribit + Kraken
- [x] EXP_REPORT with day-completeness
- [x] Draft CANDIDATES

### Pass 2
- [x] Info joins / falsifiers (placebo + make/take)
- [x] Signal board → notebook / DESK_MEMO
