# Applications — cd_me constrained-dealer monitors (wire-as playbooks)

**Companion:** [`DESK_MEMO.md`](DESK_MEMO.md) · [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) · Pass-2.5 dig [`out/info_features/`](out/info_features/) · [`out/feature_stats/`](out/feature_stats/) · notebook [`notebooks/info_stats_board.ipynb`](notebooks/info_stats_board.ipynb)  
**Honesty:** **0 Promote** on Pass-2 + Pass-2.5 info boards. Everything below is **monitor → rule sketch → paper**, not greenlit α.  
**Objects default to:** risk-policy · exec throttle sketch · research tile — **not** inventable tradable edge.  
**Data:** certified `panel_core_2venue` ETH panel (**9** UTC days); Kraken **spot_l2** subpanel n=4; `trade_synth` **QUARANTINED**.  
**Shadow:** [`applications/paper_shadow/`](applications/paper_shadow/) wires **Promote only** (still 0) — hypothetical monitors documented, never soft-Promoted.

Confidence: **high** = dashboard/gate with known failure modes · **med** = rule sketch needs paper · **low** = research feature only.

---

## 0. Object → information → desk use

| Object | What it carries (pre / concurrent / post) | Statistical claim (Pass-2.5) | Wire-as | Tradable? |
|--------|-------------------------------------------|------------------------------|---------|-----------|
| **PIM** | Concurrent LOP gap + arb cost; weak lead-lag vs mid_ret (best lag ≈+2h, pooled r≈−0.13) | day-mean CI; ToD profile; commonality PC1 | **risk monitor** | **no** |
| **VLOOP** | Concurrent cross-venue mid dislocation | corr(VLOOP,TCOST)≈0.62 day-block CI[0.48,0.71] | fragmentation / SOR context | **no** |
| **TCOST** | Concurrent half-spread friction on legs | calm/stress corr ≈0.24 / 0.17 | **exec friction** tile | **no** |
| **DCM̂** | Concurrent constraint PC1 (fund/basis/RV/imb); joins PIM beyond RV | partial r(PIM,DCM\|RV)≈0.38; ΔR²≈0.15 | **risk regime strip** | **no** |
| **VLM↔PIM** | Concurrent elasticity; survives RV control | partial r≈−0.46; ΔR²≈0.20; chrono sign-stable | **liq monitor** | **no** |
| **Kraken mode** | Feed quality (spot_l2 vs absent_2venue); synth quarantined | spot_l2=4 / 2-venue=5 on primary | **policy / data flag** | **no** |

**Non-goals:** sized TOB-cross arb · bank CDS/VaR vanity · LSTAR/model_sim Promote · BTC widen until ETH gates clear · ClickHouse MCP.

---

## 1. Risk / kill-switches (hypothetical — Hold)

### 1.1 PIM LOP-stress strip (Hold)

**Objects:** `risk.pim_cross_venue` · `info.object_leadlag_map` · figs `out/info_features/figs/fig_tod_pim_dcm.png`, `out/feature_stats/figs/fig_irf_pim_midret.png`

| Layer | Rule sketch | Conf |
|-------|-------------|------|
| Monitor | Publish day-mean PIM with day-block CI; flag ToD hotspots | **high** |
| Escalate | When PIM enters upper descriptive band **and** DCM̂ high → risk strip “constrained” | **med** |
| Do not | Size a cross-venue arb on TOB gap (`alpha.tob_cross_arb` **Kill**) | **high** |

**Falsifiers:** chrono sign flip on PIM↔VLM; synth-heavy days dominate; true quoted Kraken TOB changes level.

### 1.2 DCM̂ constraint regime (Hold)

**Objects:** `risk.dcm_pc1` · `info.pim_dcm_incremental`

| Layer | Rule sketch | Conf |
|-------|-------------|------|
| Monitor | Track DCM̂ + explained-var; join with PIM | **high** |
| Incremental | Treat DCM as **additive** to RV (ΔR²≈0.13) — not a vol alias alone | **med** |
| Placebo | Pass-2 DCM shuffle still inconclusive — ceiling Hold | **high** |

### 1.3 Elasticity after RV (Hold)

**Objects:** `liq.elasticity_regime` · `info.elasticity_after_rv`

| Layer | Rule sketch | Conf |
|-------|-------------|------|
| Monitor | corr(VLM,PIM) with day-block CI (≈−0.38 [−0.51,−0.29]) | **high** |
| Control | After RV, partial still ≈−0.47 — not a pure vol artifact | **med** |
| Paper match | Sign ≠ FX paper unconstrained story — report honestly | **high** |

---

## 2. Execution / SOR (hypothetical — Hold)

### 2.1 VLOOP↔TCOST stress commonality (Hold)

**Objects:** `info.vloop_tcost_commonality` · `info.vloop_tcost_stress_split` · fig `out/info_features/figs/fig_vloop_tcost_stress.png`

| Use | Conf |
|-----|------|
| In stress (high PIM) VLOOP/TCOST co-move harder → widen SOR cost buffer | **med** |
| Calm hours: commonality softer — do not over-react to isolated VLOOP spikes | **med** |

### 2.2 Kraken feed-quality gate (Hold)

**Objects:** `info.kraken_spot_vs_2venue` · completeness [`out/panel_completeness/`](out/panel_completeness/)

| Use | Conf |
|-----|------|
| Tag every PIM print with `spot_l2` vs `absent_2venue` (`trade_synth` QUARANTINED) | **high** |
| Defer any future *quoted* throttle rules until futures TOB ingest exists | **high** |
| Never treat synth gap as executable α | **high** |

---

## 3. paper_shadow wiring policy

| Candidate gate | Shadow action today |
|----------------|---------------------|
| **Promote** | Would enable monitor→rule telemetry (count = **0**) |
| **Hold** | Log only; optional dashboard tile; **no** size / **no** `live_orders` |
| **Kill** | Do not surface as actionable |

Hypothetical Hold tiles (not wired as Promote): PIM level, DCM regime, elasticity flag, Kraken mode badge, VLOOP–TCOST stress badge.

---

## 4. What remains unknown

- True exchange **funding rate** series (now mid-move proxy)
- Kraken **futures quoted** TOB history
- BTC widen of the same info dig
- Venue-drop ablation (Deribit off) on spot_l2 subpanel / 2-venue PIM
- Whether DCM incremental ΔR² holds on ≥20 days / denser DCM hours (currently n≈59 joint hours)
- LSTAR γ/c identification (park)
