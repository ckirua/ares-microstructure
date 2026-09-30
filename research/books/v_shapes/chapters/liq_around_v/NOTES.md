# Liquidity around V — spread / depth / impact

**Book:** Flora & Renò (2020-09-17)  
**PDF:** §6.2 liquidity around V · **Status:** `exp_run`

---

## Pass 1 — paper object

- [ ] Around MinV \(\tau^\*\): quoted/effective spread, TOB depth, short-horizon impact
- [ ] Align collector TOB with trade 1s grid (HL+Deribit+Kraken where TOB exists)
- [ ] EXP_REPORT with event windows ±\(h_n\)

## Pass 2 — deep dig

- [ ] Incremental info: does liq deterioration lead MinV?
- [ ] Resilience / refill (reuse mmip `tob_resilience` / book helpers)
- [ ] Grossman–Miller \(\mu/\sigma\) as **monitor only** (not Promote tradable)
- [ ] CANDIDATES + falsifiers (placebo times, time-split)

## Empirics status
Pass 1+2 executed — see EXP_REPORT.md / CANDIDATES.md / out/.
