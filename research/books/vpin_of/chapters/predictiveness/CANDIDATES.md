| id | type | lenses | decision | falsifier |
|----|------|--------|----------|-----------|
| `info.vpin_markout` | predict | info,exec | **Hold** | Full HL+DB panel (110 attempted / 68 ok): Promote iff med day IC>0.02 ∧ med early>0 ∧ med late>0 (≥8 ok days); observed med≈0.007, early≈0.023, late≈0.006 — **not** trailing-12-day subset |
| `info.vpin_side_shuffle` | falsifier | info | **Promote** (Pass 1) | pass_rate≈0.98 on real tape |
| `info.vpin_time_split_stable` | falsifier | info | **Promote** (Pass 1) | stable_rate≈0.97 |
