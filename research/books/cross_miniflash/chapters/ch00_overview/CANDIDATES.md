| id | type | lenses | decision | falsifier |
|----|------|--------|----------|-----------|
| `info.crash_def_taxonomy` | D | info, risk | **Promote** | Overlap tables empty / Nanex⊄SSM claim fails |
| `risk.ssm_z6_binary` | D | risk, mm | **Hold** | σ_m / z* fragility (see kalman_ssm) |
| `base.nanex_paper_80bps` | D | risk | **Kill** | Near-zero fire rate on crypto ms tape |
| `base.nanex_crypto_30bps` | D | risk, exec | **Hold** | θ ablation instability; needs severity filter |
| `exec.outside_tob_l2` | D | exec, liq | **Hold** | Sparse warehouse L2 false positives |

**Promote rationale (`info.crash_def_taxonomy`):** Pass 2 overlap + threshold ablations cleanly separate *tape-burst* (Nanex 30bps), *broad outlier* (SSM), and *stale-quote artifact* (outside-TOB on L2). Survives the falsifier that Nanex events are almost entirely inside SSM (precision≈0.90) while SSM is not Nanex (recall≈0.026) — taxonomy is operationally useful for desk labeling.

## Phase 4 harden

Program-wide bootstrap/time-split applied (`scripts/exp_final_hardening.py` → `out/phase4_hardening/hardening_gates.json`). Gate note: primary **10bps/ic5**; frag share also **5bps/ic3**.
| id | Phase4 decision | harden why |
|----|-----------------|------------|
| `info.crash_def_taxonomy` | **Promote** | Framing taxonomy survives Nanex⊂SSM precision + outside-TOB stale-quote class; not a numeric claim |
| `risk.ssm_z6_binary` | **Hold** | raw median ΔP≈0; use severity gate + z* menu instead |
| `base.nanex_crypto_30bps` | **Hold** | high-precision burst tag only with SSM nesting; θ ablation fragile (80→30) |
| `base.nanex_paper_80bps` | **Kill** | n=8 / 42 cells — vanity equity cutoff on crypto ms tape |
