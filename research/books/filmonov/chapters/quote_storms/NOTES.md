# Quote storms (stuffing bursts)

**Book:** Filimonov, Perm Winter School 2013  
**PDF:** slides (local) · **Status:** `exp_run`  
**Raw:** [`../../_raw/`](../../_raw/) (local/gitignored)  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md)  
**Lib:** [`../../../../lib/hftpat.py`](../../../../lib/hftpat.py) · `quote_storm_*`

---

## Pass 1 focus

Burst detectors: adds+cancels/s proxies, cancel fraction, max burst vs day baseline (deck slides **27–29**).

### Deck citations
- Slides **27–29**: quote stuffing / flickering quotes — bursts of adds+cancels with little price discovery; intensity vs quieter baseline.
- Crypto map: L0 TOB update Hz + same-price size↑/↓ as add/cancel proxies (no firm IDs / OE message types).

### Not a rename
- **Not** `lob.tob_depletion_cancel_proxy` (unconditional same-price size-drop class).
- **Not** equity Nanex quote-rate vanity charts.

## Pass 2 dig

Storm→spread / adverse selection join; overlap vs `lob.tob_depletion_cancel_proxy`; exec-throttle candidacy.

## Info / Bayesian dig

**Question:** do storms carry **toxicity** (adverse selection) or only quote-noise?

| Lens | Finding | Path |
|------|---------|------|
| Storm−placebo markout | Δ≈+0.52bps on HL storm days; **n=2** · not early/late stable | `out/feature_stats/` |
| P(AS \| storm) Beta | mean≈0.43 CrI covers 0.5 | `out/bayes/` |
| λ storms/h Gamma | HL ≈0.41 CrI[0.32,0.51] | `out/bayes/figs/fig_posterior_storm_rate.png` |
| OFI/VPIN regime | context tile (corr≈0.42 / VPIN≈0.58) | `out/pass2_expand/` |
| Lead-lag | storm→fade @1s hit≈0.03 (sparse) | `fig_lead_lag_xcorr.png` |

**Wire-as:** exec throttle / risk strip on λ posterior + ToD — **not α**. Cross-link `continuous.ofi` / `vpin` — do not merge APIs.

## Pass checklist

### Pass 1
- [x] Cite deck pages in NOTES
- [x] Implement on HL + Deribit + Kraken
- [x] EXP_REPORT with day-completeness
- [x] Draft CANDIDATES

### Pass 2
- [x] Overlap gate vs lob cancel proxy (Kill if rename)
- [x] Signal board → DESK_MEMO
- [x] Info/Bayes deep dig (`notebooks/info_bayes_board.ipynb`)
