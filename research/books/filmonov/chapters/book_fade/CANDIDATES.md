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
| `info.fade_spread_widen_irf` | E | info,mm,liq | **Hold** | IRF peak Δspread≈0.28bps; Kill if ≤0 or unstable |
| `info.xvenue_is_around_fade` | E | info,disc | **Hold** | Hasbrouck IS sparse; not arb; RTT haircut missing |
