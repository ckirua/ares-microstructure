# Crash statistics — CANDIDATES

| id | type | lenses | decision | falsifier |
|----|------|--------|----------|-----------|
| `risk.ssm_severity_gate_10bps` | D | risk, disc | **Promote** | Gate ablation non-monotone / gated median ΔP→0 |
| `info.crash_v_vs_continuation` | D | info, liq, risk | **Promote** | Placebo recovery ≥ obs; share_V collapses |
| `risk.duration_post_markout` | D | risk, exec | **Hold** | \|Spearman(dt,|mo|)\| <0.1 or sign flip |
| `exec.tape_markout_post_crash` | D | exec, mm | **Hold** | Needs dense mid; tape-only ceiling |
| `risk.ssm_raw_ungated_counts` | D | risk | **Kill** | Median ΔP≈0 on raw z*=6 (Phase 2) |

**Promote (`risk.ssm_severity_gate_10bps`):** Raw 3668→275 @ 10bps/\(i_c\)≥5; ablation monotone 589→275→56. Desk must publish gated intensity, not raw z*=6 counts. Survives: gated median ΔP=0.18% ≫ 0.

**Promote (`info.crash_v_vs_continuation`):** 77% V-recovery @5s; tape markout −7 bps @5s; placebo recovery ≪ obs. Label: **risk / liq monitor** (hole vs news), not tradable.

**Hold (`risk.duration_post_markout`):** Spearman≈−0.28 useful for throttle/risk, but median Δt=0 weakens the clock — Hold until volume-clock duration.

**Kill (`risk.ssm_raw_ungated_counts`):** Confirms Phase 2 Hold on binary z*=6 without severity.

## Phase 4 harden

Program-wide bootstrap/time-split applied (`scripts/exp_final_hardening.py` → `out/phase4_hardening/hardening_gates.json`). Gate note: primary **10bps/ic5**; frag share also **5bps/ic3**.
| id | Phase4 decision | harden why |
|----|-----------------|------------|
| `risk.ssm_severity_gate_10bps` | **Promote** | ablation 3668→589→275→56; gated median ΔP cell-boot CI95=[0.167,0.214]% (primary gate 10bps/ic5) |
| `info.crash_v_vs_continuation` | **Promote** | share_V=0.771 bootCI=[0.706,0.806]; early/late=0.798/0.757; obs_rec_med≈1.24 vs placebo≈0.67 |
| `risk.duration_post_markout` | **Hold** | Spearman(dt,|mo|)≈−0.28 but median Δt=0 weakens clock |
| `exec.tape_markout_post_crash` | **Hold** | tape mo@5s≈−7bps; needs dense mid for Promote as exec throttle |
| `risk.ssm_raw_ungated_counts` | **Kill** | raw z*=6 median ΔP≈0; intensity without severity gate is vanity |
