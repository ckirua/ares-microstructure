# Crash statistics — \(\Delta P\), \(i_c\), \(\Delta t\), recovery

**Book:** Tee & Ting (2019)  
**PDF:** §4.2–4.3 crash stats pp. 11–15 · Figs 3–4 · Tables V–VIII  
**Status:** `exp_run`  
**Lib:** [`../../../../lib/crash.py`](../../../../lib/crash.py) — `extract_event_features`, `severity_gate`, `recovery_fraction`, `classify_recovery`, `post_event_markout_px`  
**Out:** [`../../out/phase3a_stats_xsec/`](../../out/phase3a_stats_xsec/) · Script: [`../../scripts/exp_phase3a_stats_xsec.py`](../../scripts/exp_phase3a_stats_xsec.py)

---

## Pass 1 — paper objects

Per event (Nanex 30bps + **severity-gated** SSM \(z^*=6\)):

| Stat | Definition | Crypto unit |
|------|------------|-------------|
| \(\Delta P\) | Peak excursion from event start | % (and bps) |
| \(i_c\) | Trade count in run | count |
| \(\Delta t\) | Event duration | s (median 0 on ms clusters) |
| Recovery | Fraction of move reversed @ 5s post end | fraction |

### Severity gate (mandatory)

Phase 2 raw SSM = **3668** (mostly micro-outliers). Primary gate:

\[
|\Delta P|\ge 10\,\mathrm{bps},\quad i_c\ge 5.
\]

| Gate | kept |
|------|-----:|
| raw z*=6 | 3668 |
| 5bps / \(i_c\ge3\) | 589 |
| **10bps / \(i_c\ge5\)** | **275** |
| 30bps / \(i_c\ge10\) | 56 |

Nanex 30bps (by construction severe): **105**.

### Pooled gated SSM (42 complete cells, ETH+BTC × HL+Deribit+Kraken, 2026-09-04…10)

| | mean | median | p25–p75 |
|--|-----:|-------:|---------|
| \(\Delta P\) (%) | 0.234 | 0.177 | 0.130–0.283 |
| \(i_c\) | 25.4 | 17 | 10–28 |
| \(\Delta t\) (s) | 3.28 | **0.0** | 0–0.58 |
| recovery@5s | 1.26 | 1.15 | 0.55–1.58 |

Nanex \(\Delta P\) median **0.40%** (harder by construction). Median \(\Delta t=0\) = same-timestamp trade clusters on crypto tape — duration clock is weak; trade-count \(i_c\) is the primary length measure (paper equity ticks → crypto trades).

---

## Pass 2 — info / signals dig

### Continuation vs V-recovery
Classify recovery@5s: V if ≥0.5, continuation if <0.2, else partial.

| Class | n | share |
|-------|--:|------:|
| V-recovery | 212 | **0.77** |
| partial | 24 | 0.09 |
| continuation | 39 | 0.14 |

Most gated SSM bursts are **liquidity-hole / V-shape**, not one-way news assimilation. Placebo random times: recovery median ≈0–0.2 vs obs ≈1.15.

### Post-event markout (tape-price; TOB mid when available)
Signed markout in crash direction (positive = continuation):

| horizon | mean bps (25 cells) |
|--------:|--------------------:|
| 0.5s | −4.9 |
| 1s | −7.6 |
| 5s | **−7.1** |

Negative markout = mean-revert after the burst — aligns with V-class dominance. Dense TOB resilience only on HL/Deribit warehouse quotes (Kraken tob_cells=0) — **ceiling** documented.

### Duration as risk feature
Cell-weighted Spearman(\(\Delta t\), |mo@5s|) ≈ **−0.28**: longer events less adverse post-move (more time to fill / less pure print outlier). Risk monitor candidate, not tradable alpha.

### Identification
- Gate thresholds stated; ablate 5/10/30 bps.  
- Recovery horizon fixed 5s.  
- Tape markout when mid sparse.  
- No Promote on ungated SSM counts.

## Phase 4 harden

Bootstrap cell-median ΔP CI and V-share time-split survive → `risk.ssm_severity_gate_10bps`, `info.crash_v_vs_continuation` remain **Promote**. Frag packages also publish 5bps/ic3 for venue shares; primary remains **10bps/ic5** (see `DESK_MEMO.md` §3).
