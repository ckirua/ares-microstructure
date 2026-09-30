# Quote storms (stuffing bursts)

**Book:** Filimonov, Perm Winter School 2013  
**PDF:** slides (local) · **Status:** `pass1`  
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

## Pass checklist

### Pass 1
- [x] Cite deck pages in NOTES
- [x] Implement on HL + Deribit + Kraken
- [x] EXP_REPORT with day-completeness
- [x] Draft CANDIDATES

### Pass 2
- [ ] Overlap gate vs lob cancel proxy (Kill if rename)
- [ ] Signal board → DESK_MEMO
