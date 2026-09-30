| id | type | lenses | decision | falsifier |
|----|------|--------|----------|-----------|
| `disc.gh_z0` | D | disc, info, exec | **Promote** | R²≈0 or z0≤0 on test |
| `disc.mrr_theta` | D→E | disc, info, liq | **Promote** | θ≤0 |
| `disc.mrr_rho_q` | D | disc, mm | **Hold** | ρ≈0 — falsified: ρ≃0.55–0.68 train/test (always high; not tradable alone) |
| `disc.hs_pi` | D | disc, info, liq, mm | **Promote** | π≤0 on split or R²<1%; α\|β not ID'd |
| `disc.hs_as_inv_split` | D | disc, info, liq, mm | **Hold** | â<0 / b̂≤0 / as_share∉[0,1] / R²₃<1% / split unstable — confirmed across trade/quote/vol clocks + GMM/restricted |

GH / HS-basic use quote-aligned Δm. MRR + HS three-way on trade-price Δp with quoted S/2. HS Promote = lump π only; AS/inv split remains Hold after GMM + multi-clock dig (â<0 primary).
