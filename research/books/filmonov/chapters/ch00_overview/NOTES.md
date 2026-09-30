# Ch.00 — Overview: HFT taxonomy

**Book:** Filimonov, Perm Winter School 2013  
**PDF:** slides (local) · **Status:** `pass1`  
**Raw:** [`../../_raw/`](../../_raw/) (local/gitignored)  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md) · Desk: [`../../DESK_MEMO.md`](../../DESK_MEMO.md)  
**Lib:** [`../../../../lib/hftpat.py`](../../../../lib/hftpat.py)

---

## Pass 1 focus

SEC-style HFT attributes, strategy map, reading order, sibling reuse table (deck slides **1–9**, strategy tile **17**).

### Deck citations
- Title / provenance: **p. 1** (Perm Winter School 2013)
- Hot topic / SSRN counts: **p. 2**
- Flash-crash framing (May 6 2010): **p. 3**
- CFTC HFT subcommittee (definition task): **p. 4**
- HFT market size / share (Aite, TABB): **p. 5**
- Technical revolutions / electronic milestones: **pp. 6–8**
- SEC (2010) HFT attribute list + latency×holding taxonomy: **p. 9**
- Strategy map (MM, stuffing, smoking, layering, ignition, hunting): **p. 17**

### SEC attributes → crypto desk mapping

| SEC attr (p. 9) | Crypto public-tape proxy |
|-----------------|--------------------------|
| High-speed programs | Venue TOB update Hz / trade Hz (`size_latency_panel`) |
| Co-location / private feeds | **Kill vanity** unless mapped to venue RTT panel (Pass 2+) |
| Short holding periods | Not directly observed without IDs — framing only |
| Numerous cancels | `quote_storm_*` / OTR aggregate (later packages) |
| Flat EOD | Not observable on public tape — framing only |

## Pass 2 dig

Taxonomy Promote only if desk labels add beyond `crash` / mmip / `lob`. Sibling reuse table is framing; detectors live in later packages.

## Pass checklist

### Pass 1
- [x] Cite deck pages in NOTES
- [x] Implement on HL + Deribit + Kraken
- [x] EXP_REPORT with day-completeness
- [x] Draft CANDIDATES

### Pass 2
- [ ] Info joins / falsifiers / overlap gates
- [ ] Signal board → DESK_MEMO

---

## Reading order

1. `ch00_overview` — taxonomy + sibling reuse
2. `latency_size_regimes` — size / TOB Hz framing
3. `quote_storms` — stuffing bursts
4. `book_fade` — post-trade depth fade
5. `momentum_ignition` — 3-phase events
6. `spoof_smoke_clock` — smoke / clock / OTR

## Sample snapshot (ETH slice)

Days: 2026-09-26, 2026-09-27, 2026-09-30 — **9/9** complete venue-days; TOB 9/9 (synth=3).

Artifacts: `out/ch00_overview/`.
