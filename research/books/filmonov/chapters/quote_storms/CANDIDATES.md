# quote_storms — CANDIDATES (Pass 2 hardened)

**Bias:** Hold — exec throttle / risk monitor; not tradable α

| id | type | lenses | decision | falsifier / Pass2 |
|----|------|--------|----------|-------------------|
| `risk.quote_storm_burst` | monitor / exec throttle | risk | **Hold** | HL storms/h≈0.5294467018620957; lob-cancel frac≈0.3125; early/late=0.0/0.7941700527931437; sparse DB/KR → monitor/exec-throttle only |
| `risk.quote_storm_vs_lob` | monitor | risk | **Hold** | competing-def gate vs lob cancel_proxy |

**Default labels:** monitor / exec throttle / risk-policy — not tradable α. Zero Promotes unless falsifier+overlap clear.

### Pass-2 expand (info)

| id | type | lenses | decision | falsifier / expand |
|----|------|--------|----------|-------------------|
| `info.storm_adverse_selection` | E | info,risk,mm | **Hold** | storm−placebo markout; n_storm-days=1 on panel; CI thin |
| `info.storm_trade_intensity_burst` | E | info,exec | **Hold** | λ_storm/λ_base≈1.69; Kill if ≈1 |
| `info.ofi_around_storm_regime` | E | info,cont | **Hold** | OFI–ret corr≈0.42; regime join not α |
| `info.vpin_storm_join` | E | info,liq | **Hold** | mean VPIN≈0.58 |
