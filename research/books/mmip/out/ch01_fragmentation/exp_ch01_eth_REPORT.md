# Ch1 fragmentation experiment — ETH

- Window: `1790715569912889710` → `1790719820774579807` (4250.9s)
- Rows: 45,771 | venues: hyperliquid, lighter, risex | aligned buckets@1000ms: 1,451
- **FEI (mean TOB-size shares, time-avg of bucket FEI): 25.9%**
- FEI (update-count shares): 82.0%
- Entropy H(size): 0.3655 nats

## Size / update shares

| venue | size_share | update_share | mean_spread_bps | median_spread_bps | frac_1tick | tick |
|-------|------------|--------------|-----------------|-------------------|------------|------|
| hyperliquid | 90.9% | 13.4% | 0.380 | 0.373 | 99.1% | 0.09999999999990905 |
| lighter | 3.5% | 63.0% | 0.429 | 0.447 | 15.2% | 0.009999999999763531 |
| risex | 5.6% | 23.5% | 0.678 | 0.037 | 50.1% | 0.009999999999763531 |

## NBBO / duplicate liquidity

- Duplicate best bid (≥2 venues): **0.0%**
- Duplicate best ask (≥2 venues): **1.1%**
- Crossed consolidated book (max bid > min ask): **100.0%**
- Mean consolidated spread (bps): **-6.248565438958314**

| venue | frac_on_NBBO_bid | frac_on_NBBO_ask |
|-------|------------------|------------------|
| hyperliquid | 99.9% | 0.1% |
| lighter | 0.0% | 64.5% |
| risex | 0.1% | 36.5% |

## Book FEI references (App A.1 / Table 1.2 style)

```json
{
  "25/25/25/25": 1.0,
  "50/50": 1.0,
  "70/20/5/5": 0.6283898247235197,
  "70/20/10": 0.7298466991620975,
  "observed_mean_size": 0.332715340291178
}
```

Artifacts: `/home/dev/srv/ares-microstructure/research/books/mmip/out/ch01_fragmentation/exp_ch01_eth_summary.json`
