# Ch.1 candidates — Promote / Hold / Kill (MM desk)

Universe: crypto perps panel **HL + Lighter + RiseX** (collector TOB) unless noted.  
Label: **D** = descriptive metric · **T** = tradable signal · **E** = execution heuristic.

| id | type | definition (units) | desk use | decision | MM rationale |
|----|------|-------------------|----------|----------|--------------|
| `frag.fei_tob_size` | D | \(\mathrm{FEI}=H(q)/\log N\) on 1s TOB size shares \(q_v\propto b_v+a_v\) (coin qty @ L0) | Regime input to risk limits / venue weight caps | **Hold** | Useful monitor; TOB≠trade share — do not size inventory off FEI alone |
| `frag.fei_trade` | D | Same FEI on **notional** shares \(\sum p\cdot q\) | True fragmentation regime for TCA/SOR capacity | **Hold** | Spatial multi-venue tape incomplete; HL hourly FEI is *temporal*, not spatial |
| `frag.venue_size_share` | D/E | \(s_v=(b_v+a_v)/\sum(b+a)\) per 1s bucket | Quoting size allocation / which book to lean on | **Hold** | HL ~91% ETH size — informs where to post size; needs trade confirmation |
| `frag.update_share` | D | Event-count share of BBO updates | Toxicity / flicker detector vs size share | **Promote** (monitor) | High update + low size (Lit) = unstable quote — widen or avoid take |
| `frag.crossed_nbbo` | E | \(1\{\max bid > \min ask\}\) on exchange-ts aligned 1s grid | SOR kill / no-take gate until fee+latency model clears | **Promote** (gate) | Crossed≠PnL; use as **hard honesty gate**, not arb signal |
| `frag.duplicate_best` | E | ≥2 venues within ½ tick of NBBO | Discount mirrored depth in SOR | **Kill** (this panel) | Incidence ~0–1% — vanity here; revisit if equity-style mirroring appears |
| `tick.frac_one_tick` | D | \(P(s=\text{1 tick})\) with tick inferred from price grid | Quote regime: constrained vs continuous spread | **Promote** (regime) | HL ETH ~99% 1-tick → skew/size matter more than spread inching |
| `tick.spread_bps` | D | \(10^4(A-B)/M\) | Cost floor, make vs take | **Promote** (input) | Core quoting/hedge cost — always on desk panel |
| `sor.split_by_share` | E | Route child ∝ size share with FEI/cross caps | SOR | **Hold** | Needs OE + fill feedback; TOB weights insufficient |
| `dark.toxicity` | T | Midpoint toxicity | Dark routing | **Kill** | No dark pool in current MD set |

**Promotion rule:** Promote only with (i) precise definition, (ii) MM action, (iii) honesty label. Never promote TOB-cross to live arb.
