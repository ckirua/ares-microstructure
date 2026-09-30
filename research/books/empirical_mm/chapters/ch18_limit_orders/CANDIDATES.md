| id | type | lenses | decision | falsifier |
|----|------|--------|----------|-----------|
| `cont.time_to_touch` | E | cont, exec, mm | **Promote** | touch_rate not ↓ in tick offset / n<50 |
| `cont.size_touch_survival` | E | cont, exec, mm | **Promote** | fill_proxy flat/empty / n<50 |
| `cont.tob_cancel_proxy` | E | cont, exec, mm | **Promote** | cancel≈0 or fill≈0 / n<100 |
| `cont.same_side_refill` | D→E | cont, mm, liq | **Promote** | refill@1s≈0 (Sandas conj.1) / n<30 |
| `info.improve_markout` | E | info, mm, exec | **Kill** | adverse CI entirely <0 (continuation, not pick-off) |
| `disc.parlour_depth_side` | D | disc, mm, exec | **Promote** | same-side depth–aggressor CI∋0 |
| `cont.lob_event_intensity` | D | cont, exec, mm | **Promote** | λ̂ undefined / n_events<200 |
| `disc.lob_event_ac1` | D | disc, mm | **Promote** | n<200 / ac1 undefined |
| `mm.book_resilience_lo` | D | mm, liq, cont | **Promote** | depth_ratio@1s≈1 / n<50 |
| `disc.sandas_depth_moments` | D | disc, mm, info, liq | **Promote** | no multilevel L2 / behind-touch≈0 |
| `disc.qty_moment_ceiling` | D | disc, exec, liq | **Promote** | trunc-var infl<1.5 (ch00 dig) |
| `mm.queue_value_tick` | D | mm, disc | **Hold** | L0≠queue position (mmip tick.*) |
| `mm.limit_fill_hazard_oe` | E | mm, exec | **Hold** | needs OE fills (dry-run/SHM only) |
| `theory.sandas_gmm_multilevel` | T | mm, info | **Hold** | L1 moments ≠ structural GMM |
| `theory.stoll_cara_bid` | T | mm | **Hold** | utility unobserved |
| `theory.cmsw_optimal_L` | T | exec, mm | **Hold** | agent EU; touch proxy only |
| `theory.foucault_parlour_eq` | T | mm, info | **Hold** | structural eq / welfare |
