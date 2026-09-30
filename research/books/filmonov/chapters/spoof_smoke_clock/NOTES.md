# Spoof / smoke / clock / OTR

**Book:** Filimonov, Perm Winter School 2013  
**PDF:** slides (local) · **Status:** `pass1`  
**Raw:** [`../../_raw/`](../../_raw/) (local/gitignored)  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md)  
**Lib:** [`../../../../lib/hftpat.py`](../../../../lib/hftpat.py) · `smoke_spoof_proxy` · `clock_cluster_*` · `otr_aggregate`  
**Script:** [`../../scripts/exp_spoof_clock.py`](../../scripts/exp_spoof_clock.py) → [`../../out/spoof_smoke_clock/`](../../out/spoof_smoke_clock/)

---

## Pass 1 focus

Smoking / layering / tape-paint proxies + clock hunting + venue OTR aggregate on **ETH · HL + Deribit + Kraken**.

### Deck citations
| Slides | Object | Crypto map |
|--------|--------|------------|
| **29** | Quote smoking — alluring quote → MO → cancel → worse fill | `smoke_spoof_proxy` attractive→cancel→worse-fill chain |
| **30** | Layering / spoofing — away pressure then cancel | large away-from-touch add that cancels w/o trade |
| **33** | Painting the tape (Nanex cancel-after-print cartoon) | noted only; not a separate Promote object |
| **35–36** | Execution / human hunting — excess fills at second-of-minute | `clock_cluster_scores` + `clock_cluster_excess` |
| **37** | Quote dangling (O’Hara) | NOTES cross-link; no firm-ID chase detector |
| **41–43** | OTR fees / state regs / MiFID surveillance asks | `otr_aggregate` **venue policy metric only** (no participant IDs) |

Slides **31–32** (price/venue fade, momentum ignition) are owned by `book_fade` / `momentum_ignition` — not re-run here.

## Pass 2 dig

Expect mostly **Hold/Kill**. Frank false-positive rates from time-shift placebo. OTR stays policy-monitor. Kill firm-ID / participant OTR vanity.

## Pass checklist

### Pass 1
- [x] Cite deck pages in NOTES
- [x] Implement on HL + Deribit + Kraken
- [x] EXP_REPORT with day-completeness
- [x] Draft CANDIDATES

### Pass 2
- [ ] FP rates documented; Kill firm-ID OTR vanity
- [ ] Signal board → DESK_MEMO

## Blockers (Pass 1)
- Public L0 TOB has **no firm IDs** → smoke/layer hits are unlabeled cartoons.
- Kraken TOB is often `warehouse:trade_synth` → **excluded from Promote**; OTR day = 0 on cancel proxy.
- Deck `cancel_ms≈200` rarely fires on sparse crypto TOB; primary sweep uses **2000 ms** (with 200/500 grid) — franker FP, not equity co-lo timing.
- Size outliers on some feeds force winsorization before layering quantile.
