# Feature regressions — V-statistic info features × honest clocks

**Book:** Flora & Renò (2020-09-17)  
**Status:** `exp_run`  
**Lib:** [`../../../lib/vstat.py`](../../../lib/vstat.py) · [`../../../lib/continuous.py`](../../../lib/continuous.py) · [`../../../lib/crash.py`](../../../lib/crash.py)  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md) · Desk [`../../DESK_MEMO.md`](../../DESK_MEMO.md)  
**Script:** [`../../scripts/exp_feature_reg.py`](../../scripts/exp_feature_reg.py)  
**Out:** [`../../out/feature_reg/`](../../out/feature_reg/)

---

## Pass 1 — object

Build a **causal** feature panel from continuous \(V_t\), \(T^\pm\), MinV / EGARCH breach, optional geometric `crash.vshape_events` overlap, intensity / VPIN — then regress forward returns under **named clocks**.

### Sampling honesty (locked)

| Item | Choice | Why |
|------|--------|-----|
| Price grid for \(V_t\) | **5s** last-print | Book legacy (`continuous_v`, widen, core panel). Not 1s — say so. |
| Decision grid | every **30s** on that path | Desk-speed; still dense enough for IC |
| **Primary target** | `y_tick_20` = next **20 trades** log return | Trade-time clock — MM / SOR decisions hit prints; calendar conflates intensity |
| Secondary | calendar 30s / 60s / 300s (= \(h_n\) primary) | Continuity with prior V→fwdret Holds |
| Optional | volume-clock next bar | Cont-clock falsifier |
| Latency | features known at decision print | No exchange RTT model |
| Look-ahead ban | **no** contemporaneous \(V_\tau\) or \(T^+_\tau\) in primary X | Right kernel looks *after* \(\tau\) |

### Causal feature set

- \(T^-_\tau\) (left kernel) + \(|T^-|\); \(T^-\) at \(h_n=1\)m
- \(V_{\tau-h_n}\) (lagged completed V — right window closed at \(\tau\)) + abs
- Running MinV of path points with \(\tau_i\le\tau\); EGARCH-band **breach** vs panel \(q_{0.05}\)
- Geometric V overlap flag (`crash.vshape_events`, separate API)
- \(\log\) trade intensity (past \(h_n\)); rolling VPIN (tape sides/qty — **no invented TOB**)
- Leakage diagnostics only: \(V_\tau\), \(T^+_\tau\)

### Models

Ridge **primary** (α via time-blocked CV); OLS; ElasticNet; logistic breach→sign(\(y\)). Chronological day split (~60/40) + block-bootstrap IC CI. Promote only if \(R^2_\mathrm{te}>0\), IC CI excludes 0, \(|\mathrm{IC}|\ge0.05\), early∧late sign-stable.

## Pass 2 — signals

- Label: *info feature* / *monitor* / *paper throttle join* — **not** soft-Promote to sized alpha
- Falsifiers: leakage lift from \(V/T^+\); calendar vs tick disagreement; volume-clock
- Fold into trade ideas as Monitor / Throttle / paper-only — never Promote Holds

## Empirics

See `EXP_REPORT.md` · `CANDIDATES.md` · notebook `feature_reg.ipynb`.
