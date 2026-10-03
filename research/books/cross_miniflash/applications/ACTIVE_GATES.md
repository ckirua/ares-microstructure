# ACTIVE GATES — desk worklist (2026-09-30)

Session Promote / Hold / Kill to **keep working**, **keep researching**, or **stop**.  
Honesty: `research_sim_on_real_tape` · `live_orders=False` · `alpha_claim=False` · RT ≈ **4 bps** · ClickHouse MCP banned.

**Parents:** [`../../EXPERIMENTS.md`](../../EXPERIMENTS.md#2026-09-30) · [`HOW_WE_TRADE.md`](HOW_WE_TRADE.md) · [`STRATEGY_RESEARCH_MENU.md`](STRATEGY_RESEARCH_MENU.md) · [`RISK_GATE_STACK.md`](RISK_GATE_STACK.md)

**Counts (desk-active, deduped):** **Promote / Promote_shadow = 7** · **Hold = 18** · **Kill = 14**

---

## 1. Keep working (Promote / Promote_shadow)

Ranked by desk value (earn first, then save, then playbook). Metric + next action.

| # | Gate | Decision | Metric | Next action | Artifact |
|--:|------|----------|--------|-------------|----------|
| **1** | **TI-v-fade causal** (lab earn) | **Promote** | net **+11.63** bps CI[7.67,15.91] n=117 · Survive hs≤5bp | Ship paper aggressor with nest+int hard gates; keep `alpha_claim=False` until OE | [`edge_lab/out/EXP_REPORT.md`](edge_lab/out/EXP_REPORT.md) · [`edge_lab/V_FADE_STRATEGY_SPEC.md`](edge_lab/V_FADE_STRATEGY_SPEC.md) |
| **2** | **severity_zend** (executable path) | **Promote_shadow** | path **+20.16** CI[9.77,29.79] n=23 · \|z\|≥20 @0.5→3s · `prior_only` | **Default live entry** — not `confirm_r2`. Paper bot: `--entry-mode severity_zend --confirm-s 0.5 --exit-s 3 --z-min 20` | [`edge_lab/v_fade_paper/out/PATH_GAP_REPORT.md`](edge_lab/v_fade_paper/out/PATH_GAP_REPORT.md) · [`SHADOW_BOARD.md`](edge_lab/v_fade_paper/out/SHADOW_BOARD.md) |
| **3** | **TI-int-halt** / kill_ladder | **Promote** (risk) | Δ\|mo\| fire−obs **+6.54** CI[2.17,10.68] n_fire=226 | Keep wired in `RISK_GATE_STACK`; extend adapters (POV/arb) beyond MM shadow | [`RISK_GATE_STACK.md`](RISK_GATE_STACK.md) · [`edge_lab/out/EXP_REPORT.md`](edge_lab/out/EXP_REPORT.md) · [`paper_harness/out/RISK_ROLLUP.md`](paper_harness/out/RISK_ROLLUP.md) |
| **4** | **TI-nanex-nest** / `nest_hard_pause` | **Promote** (risk) | Δ\|mo\| nest−non **+5.11**; policy **+3.20** CI[1.45,5.04]; OOS Δ\|mo\| **+9.26** | Enforce size→**0** on Nanex∩SSM in every aggressor book; live Nanex bit on stream | [`edge_lab/nanex_nest/out/NANEX_NEST.md`](edge_lab/nanex_nest/out/NANEX_NEST.md) · [`edge_lab/nanex_nest/out/`](edge_lab/nanex_nest/out/) |
| **5** | **TI-v-fade+cont combo** | **Promote** (fade-dominated) | net **+6.52** CI[3.33,9.90] n=181 | Do **not** credit cont leg; keep as sanity that fade carries combo | [`edge_lab/out/EXP_REPORT.md`](edge_lab/out/EXP_REPORT.md) |
| **6** | **mm_quoting** `always_stay_wide` | **Promote** (playbook, not alpha) | V mo@5s **−16.51**; cont **+12.12**; stay-wide beats blind restore | MM restore only after ladder∩confirm; stay wide on cont | [`mm_quoting/out/`](mm_quoting/out/) |
| **7** | **mm_confr** `disc.tick_rq_taxonomy` | **Promote** (taxonomy only) | framing vs mmip `tick.*` — **no numeric claim** | Use as regime vocabulary / feature naming; do not trade from taxonomy alone | [`../../../mm_confr_viewpoints/DESK_MEMO.md`](../../../mm_confr_viewpoints/DESK_MEMO.md) · `mm_confr_viewpoints/out/hardening/` |

### Note — oracle Promotes (lab ceiling only)

Oracle fade / ride Promotes in edge_lab are **look-ahead ceilings**. Do **not** ship as live rules. Causal ride is Kill; oracle ride Survive ≠ causal Survive ([`edge_lab/friction/out/FRICTION_REPORT.md`](edge_lab/friction/out/FRICTION_REPORT.md)).

### Demoted from Promote (do not treat as cleared)

| Gate | Was | Now | Why |
|------|-----|-----|-----|
| **LR-fire-pause@5m** | Promote (Δ\|mo\| +19.8) | **Hold** | Hardening: exclude_nest / exclude_overlap CI∋0; early half weak; ALL_external Kill; KR_BTC Kill — see §2 |

---

## 2. Keep researching (Hold)

Why Hold + what would Promote.

| Gate | Why Hold | Would Promote if… | Artifact |
|------|----------|-------------------|----------|
| **LR-fire-pause@5m** (hardened) | Survives bootstrap/placebo but demoted: nest/overlap weaken Δ; early Δ≈1.96 CI∋0; transfer mixed (KR_BTC Kill, ALL_external Kill) | Venue-stable Δ\|mo\|@5m with nest-ex / non-overlap CI>0 · early+late both clear · external not Kill | [`long_range_lab/out/long_edges/FIRE_PAUSE_HARDENING.md`](long_range_lab/out/long_edges/FIRE_PAUSE_HARDENING.md) |
| **confirm_r2@2→5** (path) | Lab +13.3 but **path −5.74** — rebound spent by ~+1s | Never for exec; keep lab board only | [`edge_lab/v_fade_paper/out/PATH_GAP_REPORT.md`](edge_lab/v_fade_paper/out/PATH_GAP_REPORT.md) |
| **class_models** soft P(V) size | OOS soft clears baselines only **fragile** (vs_always lo≈0.06 < 0.25 bps bar) | Paired lift CI vs `hard_v_rule` **and** `always_fade` with lo≥**0.25** bps each; net CI>0; early/late stable | [`edge_lab/class_models/out/EXP_REPORT.md`](edge_lab/class_models/out/EXP_REPORT.md) |
| **LR-cont-long-ride@15m** | net +19.58 CI[−7.48,51.34] n=27 · CI∋0 | CI excludes 0 · n≥40 · early/late sign-stable · OE fills | [`long_range_lab/out/long_edges/EXP_REPORT.md`](long_range_lab/out/long_edges/EXP_REPORT.md) |
| **LR-cluster-ride@60m** | +46 CI>0 but **n=12** underpowered | n≥20 (prefer ≥40) non-overlap · early/late stable | same |
| **LR-ssm-drift-ride@30m** | +13.70 CI[−2.53,29.67] n=98 · CI∋0 | CI excludes 0 after RT · early/late stable | same |
| **LR-cluster-fade** (primary n thin) | Underpowered / fade side often loses | Only if fade CI>0 with n≥20 **and** not anti-edge — unlikely; prefer Kill research time | same |
| **MM kill_ladder_maker** (long_range MM) | Δeq +13.79 CI[−14.86,+50.10] · CI∋0 | CI excludes 0 on longer panel; denser TOB equity path | [`long_range_lab/out/summary.json`](long_range_lab/out/summary.json) |
| **mm_confr numeric gates** (9×) | Placebo / FM / ρ / tick-constrain / undercut / xvenue τ / grid / terciles / sign matrix — monitors only | Constraint-relax event study or within-venue FM with vol/OFI clears tradable bar; widen days | [`../../../mm_confr_viewpoints/DESK_MEMO.md`](../../../mm_confr_viewpoints/DESK_MEMO.md) |
| **tick-constrained regime** | Taxonomy Promote; numeric Hold — size dial not alpha | Flag predicts signed mo after costs CI≠0 (does not today) | same · HOW_WE_TRADE card E |
| **occurrence logistic** (feature_models) | Soft Promote day budget (AUC_te≈0.635) — not event alpha | Venue holdout + multi-week recalibration | [`feature_models/EXP_REPORT.md`](feature_models/EXP_REPORT.md) |
| **severity Ridge** | OOS R²&lt;0 | Never as sizer; monitor only | same |
| **Hawkes-lite λ̂** | Not run; intensity_60s already Promote ladder | λ̂ beats intensity_60s on Δ\|mo\| OOS | [`STRATEGY_RESEARCH_MENU.md`](STRATEGY_RESEARCH_MENU.md) §2 |
| **SOR child-size** (xvenue) | Lag-take Kill; child-size only Hold research | Thin-leg deprioritize on fire clears capacity / adverse fill study | [`edge_lab/xvenue_lag/`](edge_lab/xvenue_lag/) quarantine |
| **strategy_lab** stubs | Risk-sim Δ small / synthetic marks | Collector TOB days before claiming equity Δ | [`strategy_lab/out/`](strategy_lab/) |
| **paper_harness Δeq** | Risk shadow (+296 ladder / +1454 stack) ≠ alpha | Already Promote-as-risk; Promote *alpha* never from this scoreboard | [`paper_harness/out/RISK_ROLLUP.md`](paper_harness/out/RISK_ROLLUP.md) |
| **always_ride** (edge_lab) | −15.08 — CI excludes 0 but **fails friction bar** | N/A — treat as anti-pattern; do not chase | [`edge_lab/out/`](edge_lab/out/) |
| **Kraken PF futures L2** | Spot native; PF still synth | Ingest PF L2 → re-run mm_confr numeric gates | `mm_confr_viewpoints/out/kraken_native/` · `out/native_rerun/` |

---

## 3. Stop (Kill)

Do **not** spend sample / bot time.

| Item | Why | Artifact |
|------|-----|----------|
| **TI-cont-ride (causal)** | net **−2.83** CI[−7.40,1.56] n=64; dies @ all friction levels causal | [`edge_lab/out/EXP_REPORT.md`](edge_lab/out/EXP_REPORT.md) · friction |
| **xvenue_lag** (all 5 rules) | hl_to_thick net **−4.17** CI entirely ≤0; gross≈**−0.17** → cost sink | [`edge_lab/xvenue_lag/out/EXP_REPORT.md`](edge_lab/xvenue_lag/out/EXP_REPORT.md) |
| **LR-v-slow-fade** | All holds Kill; 1m −0.93; longer worse; early/late flip | [`long_range_lab/out/long_edges/EXP_REPORT.md`](long_range_lab/out/long_edges/EXP_REPORT.md) |
| **LR-cluster-fade** (as alpha) | Anti-edge — fade side loses; isolated fade Kill | same |
| **always_flat** | Zero edge by construction | edge_lab |
| **Oracle cont-ride as live rule** | Oracle Survive ≠ causal Survive | friction kill grid |
| **mm_confr** `disc.sign_scorecard_tradable` | hit_rate **0.33** | mm_confr DESK_MEMO |
| **mm_confr** LSE/Nasdaq RDD | No sovereign tick ladder | same |
| **mm_confr** welfare tick | Unobservable | same |
| **mm_confr** SEC/IPO channel | Out of scope | same |
| **Predict-mid ML** | mid_frac=0; no dense mid OOS | STRATEGY_RESEARCH_MENU |
| **N=300/9000 as SSM detect clock** | gated/day → 0 | [`horizon_lab/HORIZON_RECOMMENDATION.md`](horizon_lab/HORIZON_RECOMMENDATION.md) |
| **Nanex-solo hard pause** (no SSM) | Nest = Nanex∩SSM only | RISK_GATE_STACK anti-patterns |
| **Absolute-z ladder** {8,10,12} | Use within-gated percentiles | RISK_GATE_STACK |

---

## 4. Compose rules

Hard composition for any live / paper aggressor that touches today’s Promotes.

### 4.1 Size throttle (max severity wins)

```text
effective_mult = min(
  ladder_tier_mult,            # observe=1 · widen=0.5 · size_cap=0.25 · halt=0
  0.0 if nest_hard_pause,      # Nanex∩SSM
  0.0 if fire_pause_5m live,   # keep clock; evidence Hold-hardened — still compose as save overlay on HL ETH
)
```

Spec: [`RISK_GATE_STACK.md`](RISK_GATE_STACK.md). Code: `paper_harness/harness/risk_stack.py`.

### 4.2 V-fade entry (path, not lab identity)

| Do | Do not |
|----|--------|
| Enter **`severity_zend`**: \|z_peak\|≥**20**, delay **0.5s**, exit **3s**, `fire_pause=prior_only` | Enter on **`confirm_r2@+2s`** for executable PnL (path −5.7 Hold) |
| Score lab board with confirm_r2 separately | Claim lab −mo₅ₛ as fillable path |

Source: [`PATH_GAP_REPORT.md`](edge_lab/v_fade_paper/out/PATH_GAP_REPORT.md) · [`SHADOW_BOARD.md`](edge_lab/v_fade_paper/out/SHADOW_BOARD.md).

### 4.3 Don’t fade during fire_pause

Hardening compose: fade-during-pause net **0.34** ≪ quiet **6.16**.

```text
if fire_pause_5m active:
    aggressor_size = 0
    v_fade_entry   = suppress
else:
    v_fade_entry   = severity_zend  # (or causal V for lab board)
```

Source: [`FIRE_PAUSE_HARDENING.md`](long_range_lab/out/long_edges/FIRE_PAUSE_HARDENING.md) § V-fade composition · recommendation `dont_fade_during_pause`.

### 4.4 Class economy

| Class (causal @1–2s) | Action |
|----------------------|--------|
| **V** | Fade (severity_zend / causal rule) |
| **continuation** | Flat aggressor; MM **stay wide** — never causal cont-ride |
| **partial** | Skip |

Combo Promote is **fade-dominated** — do not revive cont leg from combo net.

### 4.5 Risk vs alpha labels

| Layer | Label |
|-------|-------|
| Causal V-fade / severity_zend path | Research earn · `alpha_claim=False` until OE |
| int-halt · nest_hard · fire_pause_5m · paper_harness Δeq · mm_quoting | **Risk-policy / playbook** — not naked PnL |
| class_models soft size | Hold until lift bar clears |
| LR 15–60m rides | Separate book — never inside V-fade state machine |

### 4.6 Quiet-day idle

No gated SSM → stack **no-op** (2026-09-30 HL ETH: gated 0 · fires 0 · Δeq 0). Do not invent pause.

---

## Priority next builds (capture money)

1. **Paper V-fade** with `severity_zend` + nest_hard=0 + int-halt ladder + suppress during `fire_pause_5m`.
2. **RISK_GATE_STACK** adapters on all aggressor books (already wired MM shadow).
3. **class_models** — only if soft-size lift clears 0.25 bps paired bar; else stay Hold.
4. **LR-fire-pause** — widen transfer / nest-ex until Promote or Kill cleanly (currently Hold).
5. **LR cont / drift / cluster-ride** — power sample; do not bot yet.

**Do not build:** xvenue lag-take · causal cont-ride · slow V-fade · mid ML · scorecard-as-tradable.

---

## Pointer index

| Topic | Path |
|-------|------|
| Session catalog | [`../../EXPERIMENTS.md`](../../EXPERIMENTS.md#2026-09-30) |
| Money map | [`HOW_WE_TRADE.md`](HOW_WE_TRADE.md) |
| Research menu | [`STRATEGY_RESEARCH_MENU.md`](STRATEGY_RESEARCH_MENU.md) |
| Risk stack | [`RISK_GATE_STACK.md`](RISK_GATE_STACK.md) |
| Edge lab | [`edge_lab/out/EXP_REPORT.md`](edge_lab/out/EXP_REPORT.md) |
| Path gap / shadow | [`edge_lab/v_fade_paper/out/PATH_GAP_REPORT.md`](edge_lab/v_fade_paper/out/PATH_GAP_REPORT.md) |
| Nest | [`edge_lab/nanex_nest/out/`](edge_lab/nanex_nest/out/) |
| Class models | [`edge_lab/class_models/out/EXP_REPORT.md`](edge_lab/class_models/out/EXP_REPORT.md) |
| Fire-pause harden | [`long_range_lab/out/long_edges/FIRE_PAUSE_HARDENING.md`](long_range_lab/out/long_edges/FIRE_PAUSE_HARDENING.md) |
| Long edges | [`long_range_lab/out/long_edges/EXP_REPORT.md`](long_range_lab/out/long_edges/EXP_REPORT.md) |
| mm_confr gates | [`../../../mm_confr_viewpoints/DESK_MEMO.md`](../../../mm_confr_viewpoints/DESK_MEMO.md) |
