| id | type | lenses | decision | falsifier |
|----|------|--------|----------|-----------|
| `disc.pin_eho_mle` | D | disc, info | **Promote** | <20 usable days, MLE fail, \|PIN_free−PIN_sym\|≥0.15, or early/late \|ΔPIN\|≥0.25 |
| `disc.pin_proxy_dayimb` | D | disc, info | **Hold** | uncorrelated w/ markout |
| `cont.vpin` | D→E | cont, info, mm, exec | **Promote** | flat / n<20 |
| `cont.trade_intensity` | D | cont, exec, info | **Promote** | empty CI / ac1≈0 |

Deep re-run (`exp_ch15_pin_deep.py`, 2026-09-30 coverage expansion): **34** listing-cache days → **34 with tape** → **28 usable** @ span≥4h / n≥400 after **opaque flat-id** (≤2026-09-10) + **UTC-day clip**. PIN̂≈**0.183** (sym-ε≈0.153, \|Δ\|≈0.030); early/late ≈0.150/0.193; LOO sd≈0.016. Thin public-md days (09-12/13/23/24/28/29) remain a warehouse coverage ceiling — all-shards does not expand ETH span. VPIN/intensity stay Promote. Secondary BTC/SOL/Deribit panels **not required** (ETH alone ≥20).
