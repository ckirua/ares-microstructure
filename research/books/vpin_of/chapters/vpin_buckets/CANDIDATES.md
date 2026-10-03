| id | type | lenses | decision | gate |
|----|------|--------|----------|------|
| `cont.vpin_bucket_mean` | proxy | cont, info, exec | **Promote** | n_ok=226 (HL+DB=139) ∧ med n_buckets≈6.5k ∧ finite mean_vpin |
| `info.vpin_side_shuffle` | falsifier | info | **Promote** | pass_rate≈0.98 (p_exceed≤0.05) ∧ n_ok=226 |
| `info.vpin_time_split_stable` | falsifier | info | **Promote** | stable_rate≈0.97 ∧ n_ok=226 |
| `frag.xvenue_vpin_concord` | diagnostic | frag, info | **Hold** | HL↔DB Spearman ρ≈−0.32, CI through 0 (n≈53) |
| `disc.pin_proxy_vs_vpin` | compare | disc, info | **Promote** | day-level proxy vs mean_vpin Spearman CI_lo>0 (HL ETH); not EHO level match |
| `frag.kraken_vpin` | blocker | frag | **Hold** | partial tape — real prints, incomplete UTC — no Promote |
| `frag.hl_sol_empty` | blocker | frag | **Hold** | SOL empty on HL probe day |
