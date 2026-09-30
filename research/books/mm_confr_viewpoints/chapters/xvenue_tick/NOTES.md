# Cross-venue τ gaps / grid pressure

**Book:** Rindi et al. MMCV #3 Paris 2014  
**PDF:** slides (local) · **Status:** `exp_run`  
**Raw:** [`../../_raw/`](../../_raw/) (local/gitignored)  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md) · Desk: [`../../DESK_MEMO.md`](../../DESK_MEMO.md)  
**Lib:** [`../../../../lib/ticksize.py`](../../../../lib/ticksize.py) · helpers [`../../../../lib/epps.py`](../../../../lib/epps.py), [`../../../../lib/fei.py`](../../../../lib/fei.py)  
**Out:** [`../../out/xvenue_tick/`](../../out/xvenue_tick/)

---

## Deck mapping (Pass 1)

| Slide theme | Crypto QE here |
|-------------|----------------|
| LSE price→tick RDD (pp. ~15–19) | **Park / Kill vanity RD** — no discrete schedule |
| Cross-listing / fragmentation | Same-coin τ gap HL↔Deribit↔Kraken (primary QE) |
| Relative tick / grid pressure (p. ~28) | Within-venue Δ(τ/mid) with τ fixed; residual MQ |
| Liquid vs thin × Δτ | Depth/spread MQ Δ vs τ gap (see also `liq_book_split`) |

## Pass 1 focus

Same-coin τ gaps HL↔Deribit↔Kraken → MQ Δ; grid-pressure residuals.

## Pass 2 dig

Concordance of high-rel-tick hours; FEI on 3-venue volume; Epps curve around high-τ/mid windows; SOR venue preference panel.

## Findings (this slice)

- ETH absolute τ: HL **0.1** (known) · Deribit **0.05** (known) · Kraken **~0.1** (inferred) → HL−DB gap **+0.05** stable.
- MQ: HL quoted spread tighter than Deribit on pair-days (spread_gap HL−DB < 0) despite **higher** τ — venue confound (book, fees, inventory) dominates pure tick story.
- Grid pressure: within-day rel_tick drift small; residual spread ρ vs pressure = 5.716481177995095e-16 (Hold).
- Concordance mean Jaccard (high-τ/mid hours) = 0.2992857142857143; FEI volume mean ≈ 0.019.
- Epps: ETH 2026-09-26; n_pairs=3.
- SOR composite prefer counts: {'kraken': 5}.

## Data limitations

- Kraken TOB often trade-synthesized or inferred τ — treat absolute τ as soft.
- Depth units not cross-venue comparable (contracts vs coin); depth_gap is directional only.
- ETH slice = 3 UTC days from pass1 panel; BTC opportunistic if loaders succeed.
- No fee / latency / markout fill label for SOR — preference is MQ-rank heuristic.
- Epps assumes comparable exchange clocks; no latency haircut.
- ClickHouse MCP banned; warehouse + collector TOB only.

## Pass checklist

### Pass 1
- [x] Cite deck pages in NOTES
- [x] Implement on HL + Deribit + Kraken
- [x] EXP_REPORT with day-completeness
- [x] Draft CANDIDATES

### Pass 2
- [x] Info joins / falsifiers (concordance + FEI + Epps attempt)
- [x] Signal board → CANDIDATES / EXP_REPORT (DESK_MEMO owned by hardening package)
