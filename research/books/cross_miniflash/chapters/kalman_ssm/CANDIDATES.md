| id | type | lenses | decision | falsifier |
|----|------|--------|----------|-----------|
| `risk.ssm_z6_binary` | D | risk, mm | **Hold** | σ_m frac / z* stress; median ΔP of raw events ≈0 |
| `info.ssm_innov_continuous` | D | info, risk | **Hold** | Forward lead–lag \|corr\|≥0.1 would Promote as tradable — observed ≈0.04 |
| `risk.ssm_zstar_scan_table` | D | risk, disc | **Promote** | Monotone event count in z* fails |
| `risk.ssm_intensity_monitor` | D | risk, mm | **Hold** | Needs severity-weighted intensity in crash_stats |

**Promote (`risk.ssm_zstar_scan_table`):** Full \(z\in[2,12]\) scan is desk-usable as a **threshold menu** (like paper Table III). Survives falsifier: counts fall monotonically 36416→630; publish beside any binary cut. Binary \(z^*=6\) itself remains **Hold** until severity-weighted.

**Hold (`info.ssm_innov_continuous`):** Useful diagnostic / risk monitor candidate, but **Kill as tradable** on this slice (no forward lead vs mid/trade returns).

## Phase 4 harden

Program-wide bootstrap/time-split applied (`scripts/exp_final_hardening.py` → `out/phase4_hardening/hardening_gates.json`). Gate note: primary **10bps/ic5**; frag share also **5bps/ic3**.
| id | Phase4 decision | harden why |
|----|-----------------|------------|
| `risk.ssm_zstar_scan_table` | **Promote** | monotone pooled=True; early=True late=True; z*=[2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0,  |
| `risk.ssm_z6_binary` | **Hold** | raw median ΔP≈0; use severity gate + z* menu instead |
| `info.ssm_innov_continuous` | **Hold** | forward lead–lag |corr|≈0.04 — diagnostic only, not tradable |
