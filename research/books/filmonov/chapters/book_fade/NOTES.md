# Book fade (price / venue)

**Book:** Filimonov, Perm Winter School 2013  
**PDF:** slides (local) · **Status:** `pass1`  
**Raw:** [`../../_raw/`](../../_raw/) (local/gitignored)  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md)  
**Lib:** [`../../../../lib/hftpat.py`](../../../../lib/hftpat.py) · `price_fade_*` · `venue_fade_*`

---

## Pass 1 focus

Same-venue price fade event study; venue-fade when xvenue sync allows (deck slide **33**).

### Deck citations
- Slide **33**: liquidity fade after aggressor trade — same-side depth pulled within a short horizon; cross-venue analogue when latency-aligned.
- Crypto map: P(same-side TOB depth↓ > θ within τ | aggressor) on native TOB; far-venue fade = HL trade → Deribit depth (lat=5ms assumption stated in EXP_REPORT).

### Not a rename
- **Not** `lob.tob_depletion_cancel_proxy` — fade is **post-trade conditional**; lob cancel is unconditional size-drop classification.

### Kraken
- Collector/warehouse rows with source containing **`trade_synth`** are **excluded** from native same-venue TOB fade tests (labeled in JSON / EXP_REPORT).

## Pass 2 dig

Markout after fade; τ grid; Kraken `trade_synth` excluded from native TOB. Not a rename of `lob.tob_depletion_cancel_proxy`.

## Info / Bayesian dig

**Question:** is fade **temporary liquidity pull** (widen then revert) or **permanent** adverse impact?

| Lens | Finding | Path |
|------|---------|------|
| P(fade) Beta-Binomial | θ≈0.0114 CrI[0.0108,0.0120]; prior-stable; HL≫Deribit (hier) | `out/bayes/` |
| Spread IRF | peak Δ **−0.11bps** this dig vs +0.28 prior expand → **unstable** | `out/feature_stats/` |
| P(widen \| fade) | ≈0.60 CrI[0.19,0.93] thin | `info.bayes_widen_given_fade` |
| Temp vs perm markout | 250ms vs 5s share unstable | `info.fade_temp_vs_perm_impact` |
| Xvenue IS | sparse Hasbrouck around fade | research-only |

**Wire-as:** MM temporary widen / size cut sketch when θ_fade + IRF agree — **Hold** until IRF sign-stable on ≥10 days.

## Pass checklist

### Pass 1
- [x] Cite deck pages in NOTES
- [x] Implement on HL + Deribit + Kraken
- [x] EXP_REPORT with day-completeness
- [x] Draft CANDIDATES

### Pass 2
- [x] Overlap gate vs lob cancel proxy
- [x] Signal board → DESK_MEMO
- [x] Info/Bayes deep dig
