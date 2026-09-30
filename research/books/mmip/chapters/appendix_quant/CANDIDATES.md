# Appendix A candidates — Promote / Hold / Kill (MM desk)

Universe: crypto perps (HL / Lit / RX collector; HL warehouse tape; Deribit marks) unless noted.  
Label: **D** = descriptive · **T** = tradable signal · **E** = execution heuristic.

| id | § | type | definition (units) | desk use | decision | MM rationale |
|----|---|------|-------------------|----------|----------|--------------|
| `tick.frac_one_tick` | A.5 | D | \(P(\varepsilon=1)\) with \(\varepsilon=(A-B)/\hat\tau\) | Quote regime (constrained vs continuous) | **Promote** | HL ETH ~99% 1-tick → size/skew > spread inching; Lit ~15% → continuous |
| `tick.spread_leeway` | A.5 | D | \(\varepsilon-1\) (ticks) | Relative tick pressure / venue compare | **Promote** | Mean leeway HL≈0.02 vs Lit≈10.5 — regime classifier for make/take |
| `tick.rel_tick_bps` | A.5 | D | \(10^4\tau/M\) | Cost floor vs tick grid | **Promote** | Always-on quoting input (pairs with Ch.1 `tick.spread_bps`) |
| `harris.mle_continuous_spread` | A.5 | D | Full gamma MLE continuous→discrete | Tick-change policy / forecast | **Hold** | Needs multi-name tick tables + turnover; crypto panel too thin for book FTSE design |
| `sched.vol_curve_share` | A.10/A.6 | D/E | Hourly notional share \(V_n\) (UTC) | POV / schedule prior | **Promote** | Same object as Ch.2 `vol.curve_intraday` — App.A feeds schedule toys |
| `sched.expectation_min` | A.6 | E | \(v_n\propto V_n/\sigma_n^{1/\gamma}\) | Parent schedule baseline | **Promote** | Mean L1 vs uniform ≈0.40 on HL ETH — material vs flat TWAP |
| `sched.mean_variance` | A.6 | E | Almgren–Chriss-style \(C=\mathbb{E}+\lambda\mathrm{Var}\) (γ=1 toy) | Risk-averse schedule research | **Hold** | λ/κ uncalibrated; use as knobbed toy until TCA fills exist (Ch.3) |
| `epps.xvenue_corr` | A.12 | D/E | corr(HL mid, Deribit mark) vs Δ | Min hedge / sync horizon | **Promote** | Classic Epps: corr≈0 at ≤60s → ~0.87 at 600s on 2026-09-26 ETH |
| `epps.xasset_corr` | A.12 | D | corr(ETH,BTC) Deribit marks vs Δ | Pair hedge horizon | **Hold** | 1m marks already ~0.97 @60s — little microstructure Epps; need tick tape |
| `sig.realized_var` | A.12 | D | \(\hat V_R(\Delta)\) signature | Microstructure noise / sampling choice | **Hold** | Useful diagnostic; not a desk gate alone on 1m marks |
| `hawkes.count_acf` | A.11 | D | ACF of 1s trade counts | Clustering / burst monitor | **Promote** | lag-1 ACF ~0.17–0.44; CV≫1 — real clustering for intensity gates |
| `hawkes.branching_mom` | A.11 | D | MoM \(\hat R=\hat\alpha/\hat\beta\) | Self-excitation strength | **Hold** | Indicative only (not MLE); R̂∈[0.45,0.78] — research, not live α |
| `frag.fei_*` | A.1 | D | See Ch.1 | Regime | **Hold** / Ch.1 owns | Link only; Promote list stays in Ch.1 (`update_share`, `crossed_nbbo`, tick) |
| `sor.toy_ode` | A.3 | E | Market-share ODE | Pedagogy | **Kill** | No production lift without OE feedback |
| `flash.toy` | A.4 | D | Cascading liquidity toy | Pedagogy | **Kill** | No panel stress experiment in this package |

**Promotion rule:** precise definition + MM action + honesty label. Never promote MoM Hawkes or uncalibrated λ-schedules to live routing.
