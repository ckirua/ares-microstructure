| id | type | lenses | decision | falsifier |
|----|------|--------|----------|-----------|
| `base.nanex_crypto_30bps` | D | risk, exec, info | **Hold** | θ∈{80,50,30} ablation; Promote only with severity+xsec in Phase 3 |
| `base.nanex_paper_80bps` | D | risk | **Kill** | Fire rate ≈8 / 42 cells |
| `base.vshape_30bps` | D | liq, risk | **Hold** | Sparse; mostly ⊂ SSM |
| `exec.outside_tob_wh_l2` | D | exec, liq | **Hold** | outside_rate 15–79% on Deribit L2 smoke |
| `info.nanex_subset_of_ssm` | D | info, risk | **Promote** | Precision(Nanex→SSM) <0.5 on time-split |

**Promote (`info.nanex_subset_of_ssm`):** Nanex-style bursts are almost always SSM outliers (precision≈0.90) but SSM is far broader — desk can treat Nanex as a **high-precision burst tag** on top of SSM intensity. Time-split early/late Nanex 62/43 still nested. Survives “Nanex ≈ SSM” vanity claim (Kill that claim; Promote the *subset* relation).

## Phase 4 harden

Program-wide bootstrap/time-split applied (`scripts/exp_final_hardening.py` → `out/phase4_hardening/hardening_gates.json`). Gate note: primary **10bps/ic5**; frag share also **5bps/ic3**.
| id | Phase4 decision | harden why |
|----|-----------------|------------|
| `info.nanex_subset_of_ssm` | **Promote** | pooled prec=0.895; cell boot CI95=[0.735,0.970]; early/late mean=0.885/0.830 |
| `base.nanex_crypto_30bps` | **Hold** | high-precision burst tag only with SSM nesting; θ ablation fragile (80→30) |
| `exec.outside_tob_wh_l2` | **Hold** | warehouse L2 outside_rate 15–79%; sparse quotes vs ms trades |
| `base.nanex_paper_80bps` | **Kill** | n=8 / 42 cells — vanity equity cutoff on crypto ms tape |
