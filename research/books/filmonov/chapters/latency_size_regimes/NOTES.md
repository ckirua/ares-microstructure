# Latency / size regimes

**Book:** Filimonov, Perm Winter School 2013  
**PDF:** slides (local) · **Status:** `pass1`  
**Raw:** [`../../_raw/`](../../_raw/) (local/gitignored)  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md)  
**Lib:** [`../../../../lib/hftpat.py`](../../../../lib/hftpat.py) · `size_latency_panel`

---

## Pass 1 focus

TOB update Hz, trade-size quantiles, reaction-time proxies on HL+Deribit+Kraken (deck slides **10–20**).

### Deck citations
- Client–broker–market / DMA: **p. 10**
- Typical trading process (quote→decision→risk→gateway): **pp. 11–12**
- Speed-of-light annoyance quote (Bach / NYSE): **p. 13**
- Co-location RTT <40–50 µs (NASDAQ OMX): **p. 14** — **Kill vanity** for crypto desk unless remapped
- Distance / fiber RTT table (NY–Chicago etc.): **p. 15**
- Hibernia Express ($300M / −6 ms): **p. 16** — **Kill** as equity vanity
- Strategy map (MM first): **p. 17**
- Market making / spread + rebates: **p. 18**
- MM reaction-time history (ms→sub-ms): **p. 19**
- Typical trade volume median vs average (commodities / E-mini): **p. 20**

## Pass 2 dig

Regime **monitor** vs tradable; keep Kill on co-lo / Hibernia unless crypto venue RTT panel exists. Early/late day split + bootstrap on size/Hz when n allows.

## Pass checklist

### Pass 1
- [x] Cite deck pages in NOTES
- [x] Implement on HL + Deribit + Kraken
- [x] EXP_REPORT with day-completeness
- [x] Draft CANDIDATES

### Pass 2
- [ ] Info joins / falsifiers
- [ ] Signal board → DESK_MEMO

## Key numbers (ETH, 3 days × 3 venues)

| Venue | complete | tob | median TOB Hz | median Δt ms | median size q50 | median trade Hz |
|-------|----------|-----|---------------|--------------|-----------------|-----------------|
| hyperliquid | 3/3 | 3 | 0.1863 | 5390 | 0.105 | 1.215 |
| deribit | 3/3 | 3 | 0.3236 | 2544 | 150 | 0.5678 |
| kraken | 3/3 | 3 | 0.1716 | 3242 | 0.02 | 0.9293 |

Days: 2026-09-26, 2026-09-27, 2026-09-30 — complete **9/9**; TOB **9** (synth=3).
