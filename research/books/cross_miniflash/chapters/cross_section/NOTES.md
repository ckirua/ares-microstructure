# Cross-section — size, vol, liquidity vs crash severity

**Book:** Tee & Ting (2019)  
**PDF:** §4.3 quintiles + OLS pp. 15–21 · Tables V–VIII, X  
**Status:** `exp_run`  
**Lib:** event features + `severity_gate` in [`../../../../lib/crash.py`](../../../../lib/crash.py); NW-OLS in [`../../../../lib/stats.py`](../../../../lib/stats.py) `nw_ols`  
**Out:** [`../../out/phase3a_stats_xsec/`](../../out/phase3a_stats_xsec/)

---

## Paper claim

Larger MCap / lower vol / higher price / thicker liquidity → smaller \(|\Delta P|\), more ticks, longer \(\Delta t\) when crashes occur (faster news assimilation on thick names).

## Crypto mapping (this slice)

| Paper | Desk proxy | Status |
|-------|------------|--------|
| MCap / OI | \(\log\) daily notional | **proxy** — true OI loader unavailable |
| Volatility | 1m realized vol (day) | OK |
| Avg price | \(\log\) mean trade px | OK |
| Liquidity | Amihud ILLIQ on 1m bars | OK |
| Toxicity interact | day VPIN mean | Pass 2 |

## Pass 1 — quintiles + NW-OLS (gated SSM events, n=275)

Quintiles of \(\Delta P\) by \(\log\) notional: means ≈0.21–0.26% — **flat / weakly increasing**, not the paper’s monotone decreasing severity with size. (Quintile edges compress: many cells share similar HL notionals.)

Event-level NW-OLS of \(\Delta P\) on \(\{\log N, \mathrm{RV}, \log P, \mathrm{Amihud}\}\):

| coef | β | t |
|------|--:|--:|
| log_notional | +0.0003 | 0.11 |
| rv | +1.51 | 1.51 |
| log_px | +0.0088 | 0.80 |
| amihud | −3.0e4 | −0.47 |
| R² | 0.020 | |

**Simple size story fails** in-sample on this vertical slice.

## Pass 2 — predictive / VPIN / multi-coin / falsifiers

### VPIN interaction (event-level)
Add VPIN + \(\log N\times\mathrm{VPIN}\): R²→0.035; \(\beta_{\log N}=-0.057\) (t=−3.1), \(\beta_{\log N\times\mathrm{VPIN}}=+0.065\) (t=2.9). Size matters **conditional on toxicity** — thick names with high VPIN still print severe bursts. Label: **info / risk monitor**, not standalone tradable.

### Ex-ante (lag-1 day features → next-day median ΔP)
n_pred=**20** (small). Baseline Amihud t≈−2.5 (more illiquid → larger severity, paper-consistent direction). With VPIN interaction R²≈0.33 but **n=20** — Hold as evidence, do not Promote.

### Time-split falsifier
Early β(logN)=+0.001 vs late β=−0.008 — **sign unstable** → Kill naive size→severity Promote.

### Multi-coin
ETH mean cell-median ΔP≈0.193% · BTC≈0.189% — no material coin gap on this week.

### Venue panel
Gated events: HL 228 / Deribit 21 / Kraken 26 — HL dominates counts; xsec coefficients are HL-heavy.

## Ceilings / blockers
- True open interest (HL/Deribit) not wired — notional proxy only.  
- Ex-ante n=20; widen days/coins before Promote.  
- Dense TOB not required for xsec regressors here.

## Phase 4

`xsec.size_reduces_severity` remains **Kill** (time-split sign flip). `info.vpin_x_size_severity` / `risk.exante_amihud_severity` remain **Hold**. Events use primary gate **10bps/ic5**.
