# momentum_ignition — CANDIDATES (Pass 2 hardened)

**Bias:** Hold unless Phase1 unique-mass clears — default Hold

| id | type | lenses | decision | falsifier / Pass2 |
|----|------|--------|----------|-------------------|
| `risk.momentum_ignition_3phase` | monitor | risk | **Hold** | Phase1 unique-mass + Nanex/V overlap gates; hyperliquid: n=21 ∩N=0.19444444444444442 ∩V=0.46527777777777773 uniq=0.5347222222222222; deribit: n=14 ∩N=0.41666666 |
| `risk.ignition_vs_nanex_vshape` | monitor | risk | **Hold** | elevated ∩vshape on some venues; rename_gate not kill_rename but not Promote |

**Default labels:** monitor / exec throttle / risk-policy — not tradable α. Zero Promotes unless falsifier+overlap clear.

### Pass-2 expand (info)

| id | type | lenses | decision | falsifier / expand |
|----|------|--------|----------|-------------------|
| `info.ignition_phase1_unique_mass` | D | info,risk | **Hold** | unique_mass≈1.0 may be vacuous if Nanex n=0 @default %; Kill if ≪0.15 |
