| id | type | lenses | decision | evidence |
|----|------|--------|----------|----------|
| `risk.gex_exposure` | D | liq | **Hold** | App gate; dry-run stub `missing_lib_squeeze` |
| `risk.vex_exposure` | D | liq | **Hold** | App gate; dry-run stub |
| `risk.squeeze_intensity` | D | liq,risk | **Hold** | GEX+ / squeeze; stub |
| `liq.implied_book_scarcity` | D | liq | **Hold** | Scarcity monitor; stub |
| `alpha.tob_cross_arb` | T | exec | **Kill** | Never sized / never soft-Promote |
| `data.trade_synth` | D | data | **Kill** | Quarantined |
