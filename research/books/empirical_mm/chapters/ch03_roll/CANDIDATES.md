# Ch.3 / Ch.8 candidates

| id | type | lenses | decision | falsifier |
|----|------|--------|----------|-----------|
| `disc.roll_event_mid` | D | disc, liq, mm | **Kill** | γ₁≥0 |
| `disc.roll_trade_px` | D | disc, info | **Kill** | γ₁≥0 |
| `cont.noise_rv_ratio` | D | cont, info | **Kill** | ratio≤1 (boot CI⊂(0,1.05]) — no bounce inflation |
| `cont.volclock_ac1` | D | cont, exec | **Hold** | AC1 same as calendar |
