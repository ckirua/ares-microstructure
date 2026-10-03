# ddoi_positions — NOTES

**Book:** SqueezeMetrics (`sqzme`), *The Implied Order Book* (GEX Ed., 6 July 2020)  
**PDF:** Dealer Directional OI (PDF p. 3; table snippet p. 3) · **Status:** `notes`  
**Raw:** [`../../_raw/pdf_extract.txt`](../../_raw/pdf_extract.txt) · Draft: [`../../_raw/BOOK_DRAFT.md`](../../_raw/BOOK_DRAFT.md)

---

## 1. Paper object (PDF p. 3)

Public OI is **unsigned** — contracts outstanding, not who is long/short. **DDOI** estimates whether dealers are short or long each (expiry, strike, type) by:

1. Taking transaction-level prints.
2. Binning each trade by how it should affect OI (open/close × buy/sell).
3. Verifying direction against the **subsequent actual change in OI**.
4. Tracking every contract through time so dealer exposures stay accurate.

Example table row (PDF p. 3): `2020-06-09 | 3000 Call | vol 102 | OI 5200 | DDOI +2630` vs put row with **negative** DDOI.

Without DDOI, GEX/VEX signs are guesswork (customer vs dealer convention collapses).

---

## 2. Desk mapping (locked)

| Object | Paper | Desk |
|--------|-------|------|
| Universe | SPX listed chain | Deribit ETH (then BTC) options |
| Unsigned OI | End-of-day OI | Deribit OI snapshots |
| Direction | Trade tape + ΔOI verify | Aggressor/side when available; else **Hold**-flagged heuristic |
| Output | DDOI_{expiry,K,type} | `ddoi_proxy` same keys; document coverage |

**Honesty:** unsigned-OI-only “all dealers short” assumptions are **not** paper DDOI — label proxy and Hold.

---

## 3. Units / completeness

- Units: contracts (paper) → desk may also report coin- or $-notional for hedge join.
- Completeness: fraction of chain with finite OI + IV; flag thin expiries.
- No `trade_synth` to invent missing prints.

---

## 4. Pass checklist

### Pass 0
- [x] Extract DDOI definition + page cite
- [x] Lock Deribit proxy + Hold if unsigned

### Pass 1
- [ ] Implement OI + flow join (future lib — out of scope here)
- [ ] Baseline coverage EXP_REPORT
