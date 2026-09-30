# EXP_REPORT — Ch.2 Stakes (MM memo)

**Classification:** Research memo · paper only · no orders  
**Owner:** Ch.2 coordinator  
**Date:** 2026-09-30  
**Decision summary:** Promote `vol.curve_intraday`, `vol.fei_hourly`, `spread.vol_link` (quote/schedule inputs). Hold `vol.u_shape_ratio`, cross-venue `share.spread_elasticity`. Kill `spread.tight_notional_share` as a share proxy; park flash/HFT coverage.

---

## 1. Executive takeaway

On five DENSE Hyperliquid ETH days (warehouse trades + `l2_rebuild` quotes):

1. **Not an equity U-shape:** mean \(U = 0.558\) (std 0.37); peak mean hour **18:00 UTC** (~12.4% of daily notional). Flow is US-afternoon heavy, not open/close heavy.
2. **Temporal FEI high:** mean hourly-share FEI \(= 0.892\) — day is dispersed, with a clear afternoon bump (not a monopoly hour).
3. **Spreads rise with short-horizon vol:** mean corr\((s_t,|\Delta\log M_t|) = 0.327\) (range 0.01–0.52); mean OLS \(\beta \approx 62\) bps per unit abs-logret; mean \(R^2 \approx 0.14\).
4. **Tight spreads do not win notional:** mean \(\pi_{\mathrm{tight}} = 0.334\) — majority notional prints in **wider**-spread buckets (vol clustering). Do **not** use this as evidence for European-style “tighter venue → share.”

---

## 2. Definitions & honesty

| Object | Label | Note |
|--------|-------|------|
| \(q_h\), \(U\), \(\mathrm{FEI}_{hour}\) | **D** | Temporal seasonality — not spatial market share |
| \(s_t \sim \alpha+\beta r_t\) | **D → E** | Supports quote widen; not a alpha signal alone |
| \(\pi_{\mathrm{tight}}\) | **D (failed share proxy)** | Within-venue only; opposite sign vs “tight gets flow” |
| Cross-venue share vs spread | **T (missing)** | Book §2.2 claim — Hold |

Tape honesty: warehouse `trade` is **preferred-shard / file-capped** (not certified full-day). Quotes downsampled (~30/min) on `l2_rebuild` (~seconds cadence) — research-grade, not HFT.

---

## 3. Data & method

| Item | Detail |
|------|--------|
| Venue / symbol | `hyperliquid` / `ETH` |
| Days | 2026-09-14, 15, 16, 25, 26 |
| Trades | `load_trade_tape(..., max_files=16)` → \(n\) from 70k–269k/day; notional ~0.27e9–2.4e9 USD/day |
| Quotes | `load_quote_stream` table `l2_rebuild`, `quotes_per_minute=30` |
| Spread–vol buckets | 60s; mid from TOB; \(r_t=\|\Delta\log M\|\) |
| Alignment | Independent hour agg on trades; bucket join via `searchsorted` on ns edges |
| Missing / bias | File caps → possible under-weight of some hours; no funding clock conditioned yet |
| Baseline | Equity \(U>1\); equal-hour FEI\(=1\); \(\pi_{\mathrm{tight}}=0.5\) under independence of notional & spread |

Script: `research/scripts/exp_ch02_stakes.py`  
JSON: `out/ch02_stakes/exp_ch02_eth_{summary,full}.json`

---

## 4. Effect sizes (per day)

| Day | \(U\) | \(\mathrm{FEI}_h\) | corr\((s,\|r\|)\) | \(\beta\) | \(R^2\) | \(\pi_{\mathrm{tight}}\) | n trades |
|-----|-------|--------------------|--------------------|-----------|---------|------------------------|----------|
| 09-14 | 0.588 | (in JSON) | 0.014 | 1.2 | 0.000 | 0.270 | 232,342 |
| 09-15 | 0.306 | | 0.524 | 152.2 | 0.275 | 0.219 | 269,045 |
| 09-16 | 0.507 | | 0.465 | 78.7 | 0.216 | 0.269 | 198,274 |
| 09-25 | 0.149 | | 0.255 | 33.0 | 0.065 | 0.472 | 147,652 |
| 09-26 | 1.242 | | 0.377 | 47.3 | 0.142 | 0.440 | 69,761 |
| **Mean** | **0.558** | **0.892** | **0.327** | **62.5** | **0.140** | **0.334** | |

09-14 near-zero corr is an outlier (sparse early `l2_rebuild` TOB n=3.9k vs ~13–16k other days) — report, don’t average away.

---

## 5. MM interpretation

| Desk | Action |
|------|--------|
| Quoting | Scale reservation spread with short-horizon \(\|r\|\); use hour curve to set **max size** by UTC hour |
| Inventory | Pre-hedge / reduce risk into 13–20 UTC mass; low-size hours (e.g. 04–06 UTC) = thin exit |
| SOR | Cross-venue “tight wins share” **untested** — Hold `share.spread_elasticity` |
| Toxicity | Wide-spread + high notional minutes = stress; don’t chase tight TOB as “safe flow” |

---

## 6. Promote / Hold / Kill

See [`CANDIDATES.md`](CANDIDATES.md). Notebook: [`ch02_stakes.ipynb`](ch02_stakes.ipynb).
