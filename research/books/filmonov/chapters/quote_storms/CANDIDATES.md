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
| `info.storm_adverse_selection` | E | info,risk,mm | **Hold** | storm−placebo Δ≈+0.52bps CI[0.48,0.57]; BH-reject but **n=2** storm-days / not early-late stable |
| `info.storm_markout_1s` | E | info,risk | **Hold** | day-block mean≈0.63bps; BH-reject; sign unstable |
| `info.storm_trade_intensity_burst` | E | info,exec | **Hold** | λ_storm/λ_base≈1.69; Kill if ≈1 |
| `info.ofi_around_storm_regime` | E | info,cont | **Hold** | OFI–ret corr≈0.42; regime join not α |
| `info.vpin_storm_join` | E | info,liq | **Hold** | mean VPIN≈0.58 |
| `info.bayes_storm_rate_venue` | E | info,risk,exec | **Hold** | Poisson-Gamma λ≈0.409 CrI[0.316,0.514] HL pool; throttle quantity not α |
| `info.bayes_adverse_given_storm` | E | info,mm,risk | **Hold** | P(AS\|storm)≈0.431 CrI[0.30,0.57] covers 0.5; logit storm coeff CrI∋0 |
