| id | type | lenses | decision | falsifier |
|----|------|--------|----------|-----------|
| `vol.mc_garch_sj_utc` | D | vol, risk, mm | **Hold** | Peak hour unstable across cohorts (12 vs mmip 18) |
| `vol.sigma_m_noise_floor_1bp` | D | risk, disc | **Promote** | Removing floor floods SSM on tick-clustered tape |
| `vol.sigma_m_frac_default` | D | risk | **Hold** | Stress table 0.5→4 changes n_SSM by ~80× |
| `vol.curve_intraday_link` | D | mm, exec | **Hold** | Cross-book peak mismatch until joint panel |

**Promote (`vol.sigma_m_noise_floor_1bp`):** Desk-critical calibration constraint — \(\sigma_m\) must be trade-scale (MAD of \(\Delta\log p\)) with ≥1 bp floor. Survives falsifier: without floor, Deribit/Kraken cells with MAD≪1bp produced hundreds–thousands of spurious SSM events; with floor, Kraken SSM 1990→244 and Deribit 775→349 on the same sample.

## Phase 4 harden

Program-wide bootstrap/time-split applied (`scripts/exp_final_hardening.py` → `out/phase4_hardening/hardening_gates.json`). Gate note: primary **10bps/ic5**; frag share also **5bps/ic3**.
| id | Phase4 decision | harden why |
|----|-----------------|------------|
| `vol.sigma_m_noise_floor_1bp` | **Promote** | σ_m frac stress n_SSM {0.5: 13832, 1.0: 3668, 2.0: 808, 4.0: 177}; floor prevents tick-MAD collapse |
| `vol.mc_garch_sj_utc` | **Hold** | UTC-12 peak this cohort vs mmip ~18 elsewhere — schedule prior only |
| `vol.curve_intraday_link` | **Hold** | cross-book peak mismatch until joint panel |
