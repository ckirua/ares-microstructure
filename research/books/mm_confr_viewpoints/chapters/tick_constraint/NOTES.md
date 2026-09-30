# Tick-constrained books / undercutting

**Book:** Rindi et al. MMCV #3 Paris 2014  
**PDF:** slides (local) · **Status:** `exp_run`  
**Raw:** [`../../_raw/`](../../_raw/) (local/gitignored)  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md) · Desk: [`../../DESK_MEMO.md`](../../DESK_MEMO.md)  
**Lib:** [`../../../../lib/ticksize.py`](../../../../lib/ticksize.py)  
**Local runner:** [`_run_local.py`](_run_local.py) → [`../../out/tick_constraint/`](../../out/tick_constraint/)  
**Pass-2 dig:** [`../../scripts/exp_pass2_info_exec.py`](../../scripts/exp_pass2_info_exec.py) → `out/tick_constraint/pass2_info_exec.json`

---

## Deck citations (Pass 1)

- **pp. 20–22:** large absolute tick reduction → undercutting / spreads across levels on *liquid* books; thin books deteriorate.
- **pp. 24–25:** small absolute tick reduction → no undercutting → LO→MO; MQ worsens.
- **Tick-constrained books:** when quoted spread ≤ 1–2 ticks, further relative-tick ↓ activates undercutting (crypto map: flag `tick_constrained`, track `undercut_rate`).

## Pass 1 focus

- Fraction of quotes with spread ≤ 2 ticks over venue×day (and intraday 1m series).
- Spread-in-ticks histograms by venue.
- Cross-link mmip `tick.frac_one_tick` / `spread_leeway` as *descriptors* — this package owns regime + undercutting channel tests.

## Pass 2 dig (info/exec joins)

- **HL-only** quote-level constraint→relax flips and undercut-rate bursts → 1m event stacks of OFI, trade intensity λ, undercut rate, short-horizon markout (1s), with **event bootstrap 95% bands**.
- Desk labels (honest): `risk_monitor` vs `exec_throttle` vs `tradable` — throttle only if post-event markout worsens; tradable never claimed on this slice.
- **Kraken:** `warehouse:trade_synth` TOB labeled `is_synth`; excluded from OFI/flip studies.

## Observed (ETH, 2026-09-26/27/30)

### Pass 1 venue-days
- HL ≈ 98–99% constrained (≈1-tick book); Deribit ≈ 9–22%; Kraken synth reports 0% (unreliable).
- Median undercut_rate ≈ 0.06 (native); synth Kraken inflated (~0.24–0.36).
- Desk labels on day slice: `constrained_quiet`×3 (HL), `unconstrained`×3 (Deribit), `n/a_synth_tob`×3 (Kraken).

### Pass 2 HL event stacks (new)
| Object | n_events | Δ post−pre (mean) | Read |
|--------|----------|-------------------|------|
| Relax → OFI sum | 364 | **+2.58e9** (day-het: large on 09-26/27, ~0 on 09-30) | Flow responds at relax |
| Relax → intensity λ | 364 | **−0.031**/s | Mild slowdown, not surge |
| Relax → markout 1s | 364 | **−0.010 bps** | **No** adverse worsening |
| Burst → undercut | 292 | **+0.007** | Burst definition holds |
| Burst → markout 1s | 292 | **−0.005 bps** | Flat — not throttle |

**Gate:** `risk_monitor` · decision **Hold** · `exec_throttle=false` · `tradable=false`.  
Figs: `fig_hl_relax_stack_ofi_intensity_markout.png`, `fig_hl_undercut_burst_stack.png`, `fig_hl_info_exec_gate.png`.

## Pass checklist

### Pass 1
- [x] Cite deck pages in NOTES
- [x] Implement on HL + Deribit + Kraken
- [x] EXP_REPORT with day-completeness
- [x] Draft CANDIDATES

### Pass 2
- [x] Info joins / falsifiers (OFI + intensity + markout around HL flips/bursts; bootstrap bands; synth exclusion)
- [x] Signal board → DESK_MEMO / notebook
