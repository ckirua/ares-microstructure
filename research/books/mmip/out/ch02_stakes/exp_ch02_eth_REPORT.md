# Ch2 stakes experiment — ETH

- Venue: `hyperliquid`
- Days: 2026-09-14, 2026-09-15, 2026-09-16, 2026-09-25, 2026-09-26
- Created: 2026-09-29T22:31:22.411404+00:00

## 2.1 Intraday volume curve (UTC hour shares)

- Mean U-shape ratio (open+close 2h avg / midday 4h avg): **0.558**
- Mean FEI of hourly notional shares: **0.892**

| hour_utc | mean_share |
|----------|------------|
| 00 | 0.0236 |
| 01 | 0.0277 |
| 02 | 0.0253 |
| 03 | 0.0292 |
| 04 | 0.0118 |
| 05 | 0.0164 |
| 06 | 0.0180 |
| 07 | 0.0252 |
| 08 | 0.0365 |
| 09 | 0.0250 |
| 10 | 0.0281 |
| 11 | 0.0475 |
| 12 | 0.0396 |
| 13 | 0.0759 |
| 14 | 0.0807 |
| 15 | 0.0637 |
| 16 | 0.0383 |
| 17 | 0.0425 |
| 18 | 0.1239 |
| 19 | 0.0489 |
| 20 | 0.0616 |
| 21 | 0.0410 |
| 22 | 0.0283 |
| 23 | 0.0415 |

## 2.2 Spread ↔ short-horizon vol

- `2026-09-14`: corr(spread,|Δlog mid|)=0.014, OLS β=1.2 bps per abs-logret, R²=0.000, notional in tight-spread half=27.0%
- `2026-09-15`: corr(spread,|Δlog mid|)=0.524, OLS β=152.2 bps per abs-logret, R²=0.275, notional in tight-spread half=21.9%
- `2026-09-16`: corr(spread,|Δlog mid|)=0.465, OLS β=78.7 bps per abs-logret, R²=0.216, notional in tight-spread half=26.9%
- `2026-09-25`: corr(spread,|Δlog mid|)=0.255, OLS β=33.0 bps per abs-logret, R²=0.065, notional in tight-spread half=47.2%
- `2026-09-26`: corr(spread,|Δlog mid|)=0.377, OLS β=47.3 bps per abs-logret, R²=0.142, notional in tight-spread half=44.0%

## Crypto analogue notes

- No equity-style fixing auction monopoly; hour-of-day + funding windows are the stationarity analogues studied here.
- Single-venue HL panel: 'market share' within day = hourly notional share (spatial share needs multi-venue trade tape).

Artifacts: `/home/dev/srv/ares-microstructure/research/books/mmip/out/ch02_stakes`
