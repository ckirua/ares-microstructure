# Ch.16 asymmetry synthesis — ETH

## Board (from existing out/)
- `λ_OLS`: value=0.19918673667391243  status=**Promote**
- `IRF_perm`: value=0.42182077878159085  status=**Promote**
- `markout_1s_bps`: value=0.47189332491832336  status=**Promote**
- `sign_ρ1`: value=0.534965134267775  status=**Promote**
- `MRR_θ`: value=0.048070362924417236  status=**Promote**
- `GH_z0`: value=0.18855321422748206  status=**Promote**
- `HS_π_basic`: value=0.010178114872549042  status=**Promote**
- `HS_λ_2way`: value=0.38734258271113076  status=**Promote**
- `HS_a_AS`: value=-0.18039671098921042  status=**Hold**
- `PIN_MLE`: value=0.18318394881173936  status=**Promote**
- `VPIN`: value=0.9137892177101113  status=**Promote**
- `qs_bps`: value=0.3819711135259692  status=**Promote**
- `σ_w_AR10`: value=5.139000291855759e-05  status=**Promote**
- `noise_ratio`: value=0.8692209322328741  status=**Kill**

## Disagreement notes
- VPIN/markout **Promote**; PIN MLE **Promote** (28 usable days, PIN̂≈0.183 — coverage expansion).
- Impact / MRR θ / GH z0 **Promote** while HS three-way a(AS)≈-0.18039671098921042 **Hold**.
- Quoted spread ≈0.3819711135259692 bps with VPIN ≈0.9137892177101113 — tightness ≠ non-toxic.
- Roll **Kill** with sign ρ1≈0.534965134267775 — asymmetry via herding/impact, not bounce.

## Desk rule
- Quoting toxicity → markout, VPIN, OFI (not PIN alone).
- TCA permanent → MRR θ, IRF, λ (not HS α share).
- Cross-section AS papers → report the disagreement set.

## Figures
- `out/ch16_asymmetry/fig_measure_board.png`
- `out/ch16_asymmetry/fig_status_map.png`
- `out/ch16_asymmetry/fig_pin_vs_vpin_markout.png`
- `out/ch16_asymmetry/fig_hs_disagreement.png`

## Links
- DESK_MEMO.md §1–5 · CHAPTER_INDEX promote rollup · ch13/14/15 NOTES
