# robustness — NOTES

**Book:** SqueezeMetrics (`sqzme`), *The Implied Order Book* (GEX Ed., 6 July 2020)  
**PDF:** Empirical claims / extremes woven through pp. 5, 8–12 · **Status:** `notes` (checklist only)  
**Draft:** [`../../_raw/BOOK_DRAFT.md`](../../_raw/BOOK_DRAFT.md)

Page cites = PDF viewer / file page index.

---

## 1. Paper claims that need falsifiers

| Claim | PDF | Falsify if… |
|-------|-----|-------------|
| Higher GEX ↔ tighter RV | p. 5 | corr(GEX, RV) ≥ 0 or unstable across eras |
| GEX rarely ≪ 0 | p. 5 | crypto GEX deeply negative as norm without stress |
| Zero GEX ambiguous (IV vs inventory) | pp. 5–6 | high-IV days not associated with |GEX| crush |
| −VEX ↔ stress / high RV | p. 8 | −VEX without elevated RV (or converse always) |
| GEX+ tracks move size | p. 9 | no monotone link vs |r| / range |
| Red-zone / map predicts stress | pp. 10–11 | breaches of scarce zone without RV/IV reaction |
| Short-put dominance ↔ crashes | pp. 11–12 | put-sell ratio spike without drawdown cluster |

Paper is a practitioner note (not a formal §5 tables paper) — desk still needs **pre-registered** gates before any Promote.

---

## 2. Desk falsifier checklist (Pass 1+)

| # | Falsifier | Desk implementation | Gate |
|---|-----------|---------------------|------|
| 1 | Time-split calm vs stress | Split by IV or RV tercile; GEX/RV sign stable? | Hold |
| 2 | Block bootstrap CIs | Resample UTC days for corr(GEX+, \|r\|) | Hold |
| 3 | IV placebo | Shuffle IV surface; VEX signal should die | Hold |
| 4 | Unsigned-OI sensitivity | Compare DDOI-proxy vs naïve “dealers short all” | Hold / Kill vanity |
| 5 | Venue-drop TOB | Drop Kraken or Deribit mark; regime labels stable? | Hold |
| 6 | No `trade_synth` | Quarantine synth paths entirely | **Kill** synth SoT |
| 7 | **Kill TOB-cross α** | Never soft-Promote HL↔Deribit↔Kraken mid gap | **Kill** (pre-registered) |
| 8 | Expiry / charm park | Confirm charm still second-order on Deribit | Park unless material |
| 9 | BTC widen | Repeat ETH recipe on BTC options | Hold |
| 10 | Coverage gate | Thin OI/IV days excluded from Promote path | Hold |

---

## 3. Status

**Notes only.** No empirics in this pass. Default board: all monitors **Hold**; TOB-cross and `trade_synth` **Kill**.

---

## 4. Pass checklist

### Pass 0
- [x] List paper claims with page cites
- [x] Pre-register Kill/Hold gates

### Pass 1
- [ ] Run falsifiers once loaders exist
- [ ] Still no soft-Promote
