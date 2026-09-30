# book_fade — CANDIDATES (Pass 2 hardened)

**Bias:** Hold/monitor — MM pull candidacy; Kraken synth excluded

| id | type | lenses | decision | falsifier / Pass2 |
|----|------|--------|----------|-------------------|
| `risk.price_fade_p` | monitor | risk | **Hold** | HL P(fade)@100ms≈0.019385881444167377; markout_delta≈-0.5051363259237963bps; lob frac≈0.01857024622387751; day early/late=0.004672290720311486/0.026742676806095 |
| `risk.venue_fade_hl_db` | monitor / exec throttle | risk | **Hold** | Pass1 venue-fade retained; RTT haircut not Promote-ready |
| `risk.fade_vs_lob_cancel` | monitor | risk | **Hold** | rename gate vs lob.tob_depletion_cancel_proxy |

**Default labels:** monitor / exec throttle / risk-policy — not tradable α. Zero Promotes unless falsifier+overlap clear.

### Pass-2 expand (info)

| id | type | lenses | decision | falsifier / expand |
|----|------|--------|----------|-------------------|
| `info.fade_spread_widen_irf` | E | info,mm,liq | **Hold** | feature_stats peak Δ≈**−0.11bps** (prior expand +0.28) — **unstable** → Hold widen |
| `info.fade_markout_1s` | E | info,mm | **Hold** | day-block ≈15.5bps CI[0.21,45.7]; fat tails / not BH-reject |
| `info.fade_temp_vs_perm_impact` | E | info,cont | **Hold** | 250ms vs 5s markout share unstable; need ≥10 days |
| `info.xvenue_is_around_fade` | E | info,disc | **Hold** | Hasbrouck IS sparse; not arb; RTT haircut missing |
| `info.bayes_fade_p_posterior` | E | info,mm | **Hold** | Beta θ≈0.0114 CrI[0.0108,0.0120]; prior-stable; MM pull quantity |
| `info.bayes_widen_given_fade` | E | info,mm,liq | **Hold** | P(widen\|fade)≈0.60 CrI[0.19,0.93] thin — not clear of 0.5 |
