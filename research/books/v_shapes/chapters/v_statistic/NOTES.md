# V-statistic — kernels, \(T^\pm\), \(V_{\tau,n}\)

**Book:** Flora & Renò (2020-09-17)  
**PDF:** §3 pp. 9–12 eqs. (3.2)–(3.7); noise (3.8) pre-avg+HAC · **Status:** `exp_run`  
**Lib:** [`../../../lib/vstat.py`](../../../lib/vstat.py)  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md)

---

## Pass 1 — paper object

- [ ] \(T^-_{\tau,n}=\sqrt{h_n/K_2^-}\,\hat\mu^-/\hat\sigma^-\) (3.2)–(3.4); right-sided twin (3.6)
- [ ] \(V_{\tau,n}=\sqrt{h_n}\,T^+\,T^-\) (3.5); MinV (3.7)
- [ ] Exponential one-sided kernels; \(h_n\in\{1,5,30\}\) min on 1s grid
- [ ] Pre-averaging + HAC hooks (`preaverage_returns`, `hac_bandwidth`)
- [ ] HL + Deribit + Kraken ETH complete UTC days → EXP_REPORT + plots

**Distinction:** not `crash.vshape_events` (geometric move+recovery).

## Pass 2 — info / signals

- [ ] Continuous \(V_t\), \(T^\pm\) as features (not only MinV binary)
- [ ] Lead-lag vs mid returns / markout around \(\tau^\*\)
- [ ] Pre-avg \(k_n\) sensitivity; Kill fragile thresholds
- [ ] CANDIDATES + Signal board labels: monitor vs tradable vs exec throttle

## Empirics status
Pass 1+2 executed via `scripts/exp_core_vstat.py` — see EXP_REPORT.md / CANDIDATES.md / out/.
