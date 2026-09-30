# Ch1 fragmentation experiment — BTC

- Window: `1790715569912813484` → `1790719820625419881` (4250.7s)
- Rows: 33,179 | venues: hyperliquid, lighter | aligned buckets@1000ms: 3,757
- **FEI (mean TOB-size shares, time-avg of bucket FEI): 14.1%**
- FEI (update-count shares): 71.4%
- Entropy H(size): 0.1291 nats

## Size / update shares

| venue | size_share | update_share | mean_spread_bps | median_spread_bps | frac_1tick | tick |
|-------|------------|--------------|-----------------|-------------------|------------|------|
| hyperliquid | 97.2% | 19.6% | 0.126 | 0.120 | 98.8% | 1.0 |
| lighter | 2.8% | 80.4% | 0.377 | 0.407 | 19.2% | 0.09999999999126885 |

## NBBO / duplicate liquidity

- Duplicate best bid (≥2 venues): **0.2%**
- Duplicate best ask (≥2 venues): **0.7%**

| venue | frac_on_NBBO_bid | frac_on_NBBO_ask |
|-------|------------------|------------------|
| hyperliquid | 85.7% | 19.5% |
| lighter | 14.6% | 81.2% |

## Book FEI references (App A.1 / Table 1.2 style)

```json
{
  "25/25/25/25": 1.0,
  "50/50": 1.0,
  "70/20/5/5": 0.6283898247235197,
  "70/20/10": 0.7298466991620975,
  "observed_mean_size": 0.18626507893215394
}
```

Artifacts: `/home/dev/srv/ares-microstructure/research/books/mmip/out/ch01_fragmentation/exp_ch01_btc_summary.json`
