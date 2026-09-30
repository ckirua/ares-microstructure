# Ch.2 candidates — Promote / Hold / Kill (MM desk)

Universe: **Hyperliquid ETH** warehouse tape + `l2_rebuild` quotes (DENSE days).  
Label: **D** descriptive · **T** tradable signal · **E** execution heuristic.

| id | type | definition (units) | desk use | decision | MM rationale |
|----|------|-------------------|----------|----------|--------------|
| `vol.curve_intraday` | D | UTC hour notional shares \(q_h\) (USD) | Size/schedule by hour; risk budget | **Promote** (schedule input) | Stable enough across 5 days to shape quoting capacity by hour |
| `vol.u_shape_ratio` | D | \(U\) open/close vs midday hour means | Detect equity-like vs crypto seasonality | **Hold** | \(U\!\approx\!0.56\) mean — useful diagnostic, not a trade trigger |
| `vol.fei_hourly` | D | FEI of \(\{q_h\}\) over 24h | Temporal concentration monitor | **Promote** (monitor) | Mean FEI≈0.89 → dispersed day; spikes flag event days |
| `spread.vol_link` | D→E | OLS \(\beta\) of spread_bps on \({\lvert}\Delta\log M{\rvert}\) @ 1m | Quote widen rule / vol skew | **Promote** (quote rule input) | Mean corr≈0.33; β>0 most days — classic MM inventory/AS reward |
| `spread.tight_notional_share` | D | \(\pi_{\mathrm{tight}}\) notional in below-median spread buckets | Test “tight gets flow” | **Kill** (as share proxy) | Mean \(\pi\!\approx\!0.33\) <0.5 — activity clusters with **wide** spreads; vanity if used as SOR share |
| `share.spread_elasticity` | T | Cross-venue notional share vs relative spread | True book §2.2 claim | **Hold** | Needs Lit/RX/Binance trade tape |
| `hft.coverage_proxy` | D | Quote update intensity / coverage | Universe expansion | **Hold** | §2.3 qualitative only this pass |
| `sys.flash_proxy` | E/risk | Liquidation/gap event flags | Kill switches | **Kill** (until labeled) | §2.4 / A.4 — no clean event set yet |

**Promotion rule:** Promote only with formula, units, MM action, and honesty label. Single-venue \(\pi_{\mathrm{tight}}\) is **not** European market-share elasticity.
