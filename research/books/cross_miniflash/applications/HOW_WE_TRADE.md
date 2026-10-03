# How we trade — desk playbook (2026-09-30)

**Where is the money?** On this tape slice the clear *earned* edge is **causal V-fade** (~+12 bps after 4 bps RT). The larger *saved* money is **not trading through fire/nest** (int-halt, nest_hard_pause, LR-fire-pause@5m). Everything else is Hold research, MM collateral, or Kill.

**Honesty default:** `research_sim_on_real_tape` · `live_orders=False` · `alpha_claim=False` · fills = synthetic size × signed tape mo · RT friction typically **4 bps**. These are **not** live fill PnL, **not** Sharpes, **not** capacity-scaled account equity. Paper_harness Δeq is a **risk-policy shadow**, not alpha.

**Sources:** [`EXPERIMENTS.md`](../../EXPERIMENTS.md#2026-09-30) · [`TRADE_IDEAS.md`](TRADE_IDEAS.md) · edge_lab / nanex_nest / xvenue_lag / friction / long_range / mm_quoting / paper_harness outs.

---

## 1. Executive money map

Ranked by expected desk value (earn first, then save, then ignore).

| Rank | What | Economy | Evidence | Live status |
|-----:|------|---------|----------|-------------|
| **1** | **Causal V-fade taker** | **Earn** ~**+11.6 bps**/trade after RT | n=117 · CI[7.67,15.91] · early/late both + · friction Survive @5bp hs | **Promote** → paper bot next |
| **2** | **Intensity / nest / fire-pause gate** | **Save** adverse \|mo\| | int-halt Δ\|mo\| **+6.5** (n_fire=226); nest Δ\|mo\| **+5.1** (n=66); nest_hard policy **+3.2**; LR-fire-pause@5m Δ\|mo\| **+19.8** (n=194) | **Promote as risk policy** on *any* aggressor book |
| **3** | **MM stay-wide / confirm-restore** | **Save** cont inventory cost | cont mo@5s **+12.1**; `always_stay_wide` beats blind restore | **Promote playbook**, not fade alpha |
| **4** | Class / regime features (tick-constrain, VPIN×size, occurrence) | Size / aggressiveness dials | mm_confr taxonomy Promote; numeric gates Hold | **Hold as alpha**; use as risk feature |
| **5** | 15–60m cont-ride / cluster | Speculative | CI∋0 or n&lt;20 | **Hold** research queue only |

### Earn vs save

| Bucket | Mechanism | Do not confuse with |
|--------|-----------|---------------------|
| **Earned** | Fade V-holes against crash sign @2s–30s | Oracle V labels; slow minute fades (Kill) |
| **Saved** | Size→0 / clip when fire·nest·intensity; MM stay wide on cont | Shadow maker Δeq (+296 bps pooled) = risk scoreboard, not PnL claim |
| **Neither** | Cross-venue lag take; causal cont-ride; LR-v-slow-fade | “Gross ≈0 then RT kills you” |

### Explicit Kill list (do not trade)

| Item | Why |
|------|-----|
| **TI-cont-ride (causal)** | net **−2.83** CI[−7.40,1.56] n=64; dies at all friction levels |
| **xvenue_lag** (all 5 rules) | primary hl_to_thick net **−4.17** CI entirely ≤0; gross≈**−0.17** → pure cost sink |
| **LR-v-slow-fade** | all holds Kill; 1m −0.93 CI∋0; longer worse |
| **always_ride** | −15.08 (fails friction bar as alpha) |
| **mm_confr sign_scorecard_tradable** | hit_rate **0.33** |
| Oracle cont-ride as *live* rule | Oracle Survive ≠ causal Survive — do not promote look-ahead |

---

## 2. Strategy cards

### A. Event V-fade taker (seconds–minutes)

| Field | Spec |
|-------|------|
| **Thesis** | After gated SSM crash, if recovery@**2s** ≥0.5 (causal V), mean-revert vs crash direction; tape mo@5s is strongly negative on V (−16.5 oracle). |
| **Timeframe** | Detect crash → confirm 1–2s → hold **2s–30s** (edge_lab primary = mo@5s). **Not** 1–60m (LR-v-slow-fade Kill). |
| **Signals** | Gated SSM (10bps / i_c≥5); `recovery_1s`/`recovery_2s`; crash `direction`; optional intensity soft-clip (do not fade into nest_hard). |
| **Entry / exit** | Enter fade only on causal V; exit at fixed horizon (~5s research) or recovery flatten; **skip** partial & continuation. |
| **Sizing** | Base unit × (1 − nest) × intensity ladder; zero on nest_hard / halt tier. |
| **Costs** | RT **4 bps** baseline; Survive to hs=5bp (oracle + causal at 1bp). |
| **Falsifier** | Causal fade CI∋0 after costs; early/late sign flip; mid markout nullifies tape edge OOS. |
| **Status** | **Promote** (causal_fade_v_only +11.63 bps). |
| **Implementation** | Paper first: `edge_lab` rule → `paper_harness` aggressor shadow → live taker bot with nest+int gates. |

Path markout closed the lab→exec gap: `confirm_r2@2s` is path-dead (−5.7 Hold) because the rebound is spent by ~+1s; executable default is `severity_zend` (`|z|≥20` @0.5→3s, no r2) at **+20.2** Promote_shadow — see [`edge_lab/v_fade_paper/out/PATH_GAP_REPORT.md`](edge_lab/v_fade_paper/out/PATH_GAP_REPORT.md). CLI: `python3 run_v_fade_paper.py --panel-days --entry-mode severity_zend --confirm-s 0 --z-min 15` (or best-policy `--confirm-s 0.5 --exit-s 3 --z-min 20`); keep `--entry-mode confirm_r2 --confirm-s 2` for the lab board only.

### B. Intensity / Nanex nest halt (risk overlay)

| Field | Spec |
|-------|------|
| **Thesis** | Fire-tier gated intensity and Nanex∩SSM nests mark *worse* adverse \|mo\|; pausing aggressor **saves** markout, not earns it. |
| **Timeframe** | Sub-second detect → halt **seconds**; LR-fire-pause extends pause value to **5–15m** (Δ\|mo\|@5m **+19.8**). |
| **Signals** | Ladder tiers {widen, size_cap, halt}; `nanex_overlap` nest bit; within-gated z* / intensity. |
| **Entry / exit** | No directional entry — **size→0** (nest_hard) or clip (soft); resume after tier cool-down / non-fire. |
| **Sizing** | nest_hard: 0; nest_soft: 0.25; fire halt: 0; observe-only baseline for A/B. |
| **Costs** | Opportunity cost of skipped flow; risk bar = Δ\|mo\| &gt; friction (cleared). |
| **Falsifier** | Δ\|mo\| fire−obs CI∋0; nest placebo (bare Nanex) matches nest severity; early/late flip. |
| **Status** | **Promote** risk policy: TI-int-halt · nest_hard_pause · LR-fire-pause@5m (@15m also Promote; @30m Hold). |
| **Implementation** | Wire into *any* aggressor book (shadow → live risk service). Preferred: `nest_hard_pause`. |

### C. Class-conditional playbook

| Field | Spec |
|-------|------|
| **Thesis** | V and continuation are different economies. Fade V; **do not ride** causal continuation at 5s. |
| **Timeframe** | Class @1–2s causal; outcome measured @5s (research). |
| **Signals** | recovery threshold (≥0.5 V / &lt;0.2 cont); taxonomy label as monitor only. |
| **Entry / exit** | V → fade card A; cont → flat (or MM stay-wide); never causal cont-ride. |
| **Sizing** | Fade only when P̂(V) high; else 0. |
| **Costs** | Same RT as A. Combo causal fade+ride **+6.52** is **fade-dominated** — do not credit cont leg. |
| **Falsifier** | Class separation collapses (V mo CI≥0 or cont mo≤0 after costs on causal labels). |
| **Status** | V fade **Promote** · cont-ride **Kill**. |
| **Implementation** | Classifier / rule on recovery@2s; feed size mult to A. |

### D. MM microstructure only as collateral

| Field | Spec |
|-------|------|
| **Thesis** | Quoting widen / stay-wide on continuation **reduces adverse inventory**, not a tradable fade. |
| **Timeframe** | Event window + restore after V-confirm @1–2s. |
| **Signals** | Same class labels; intensity widen; Nanex temp pull. |
| **Entry / exit** | Maker: stay wide (0.25×) on cont / unconfirmed; restore after V confirm. Best live candidate: `always_stay_wide`. |
| **Sizing** | wide=0.25× · restore=1.0× baseline (sim schedule). |
| **Costs** | Maker fees / rebate separate; sim uses size×signed markout. |
| **Falsifier** | Blind restore beats stay-wide on cont_cost both cohorts. |
| **Status** | **Promote** med quoting playbook — **not** alpha. |
| **Implementation** | Keep in mm_quoting / strategy_lab; do not expand as PnL story. paper_harness kill-ladder = related risk shadow. |

### E. Regime from mm_confr (tick-constrained)

| Field | Spec |
|-------|------|
| **Thesis** | Native spot L2 shows **~85%** 2-tick constrained (vs synth ~0); HL frac_constrained ≈0.99. Use as **size/aggressiveness regime**, not standalone alpha. |
| **Timeframe** | Intraday / day regime feature. |
| **Signals** | `exec.tick_constrained_flag` · frac_constrained_2tick · rel_tick vs spread. |
| **Entry / exit** | No trade from tick flag alone. When constrained: smaller aggressor clips, wider MM. |
| **Sizing** | Scale base size down in high frac_constrained regimes. |
| **Costs** | N/A as alpha. |
| **Falsifier** | Constrained flag predicts signed mo after costs with CI excluding 0 (it does not today). |
| **Status** | Taxonomy **Promote**; numeric gates **Hold as alpha**. |
| **Implementation** | Feature store column → risk budget / size mult only. |

### F. X-venue

| Field | Spec |
|-------|------|
| **Thesis** | Lag-take crash direction on thick leg after HL fire is **not** an edge (gross≈0). Concordance Hold enables async fires but does not pay. |
| **Timeframe** | ~100ms latency sim; mo@5s. |
| **Signals** | — (killed). Optional Hold research: SOR **child-size** deprioritize thin HL on fire (not lag take). |
| **Entry / exit** | **Do not** enter lag taker. |
| **Sizing** | Child-size research only. |
| **Costs** | 4 bps RT turns ~0 gross into **−4.2** net. |
| **Falsifier** | Already failed — CI entirely ≤0 on all 5 rules. |
| **Status** | Lag taker **Kill**; SOR child-size **Hold** research. |
| **Implementation** | Quarantine `edge_lab/xvenue_lag`; no bot. |

---

## 3. Model menu by complexity

Same economics (V vs cont · nest · intensity); richer estimators only if they beat the simple rule OOS.

| Model | Features (from panels) | Target | Train / test | Why it might beat simple rule |
|-------|------------------------|--------|--------------|-------------------------------|
| **Simple rules** | recovery@2s≥0.5; nest bit; fire tier | Fade / size∈{0,0.25,1} | Early days[:3] / late[3:]; bootstrap CI; friction grid | Baseline — already Promote. Beat this or don’t ship. |
| **Logistic / linear** | intensity, z_peak, VPIN×logN, H^v, FEI, venue, nest, recovery_1s | P(V\|x) or P(nest severity) | Time-split + venue holdout; calibrate on platform day | Soft size = f(P̂); fewer false fades than hard 0.5 threshold. |
| **Survival / hazard** | same + duration so far, σ_m | Time-to-recovery / hazard of cont | Censor at 5s/30s; early/late | Time fade entry (“fade when hazard of V peaks”) vs fixed 2s confirm. |
| **Online / Bayesian** | venue-day class rates, nest rate, fire rate | Posterior P(V), crash rate | Hierarchical by venue; forget factor | Day risk budget & size prior when base rates shift. |
| **ML (GBDT / small net)** | panel_cache + event_panel join only | **Classifier** V vs cont / nest severity — **not** mid prediction | Strict time OOS; **no** recovery_5s / mo_5s / label leakage in features; no mid fantasy without mid OOS | Nonlinear interactions (intensity×venue×nest). Ship only if Brier/AUC beats logistic **and** sized-fade PnL beats causal rule. |

**Leakage rules:** never train on `label@5s`, `mo_5s`, `recovery_5s` as features for a live rule. Causal confirm uses recovery@1–2s only.

---

## 4. Timeframe stack

| Horizon | Job | Status |
|---------|-----|--------|
| **Sub-second–5s** | Detect gated SSM + Nanex; **halt/clip** aggressor | Promote risk |
| **2s–30s** | Causal **V-fade** (card A) | Promote earn |
| **1–5m** | **Fire-pause** / adverse mo continue; keep size off | Promote risk (LR-fire-pause@5m) |
| **15–60m** | Cont-ride / cluster / drift | **Hold only** — research queue (CI∋0 or n&lt;20) |
| **Daily** | Crash rate, nest rate, frac_constrained → risk budget | Ops feature |

---

## 5. Concrete next builds

**Prioritized (capture money):**

1. **Shadow aggressor book** — size = base × nest_hard(0) × int-halt ladder × (optional P̂_V fade). Reuse paper_harness; log avoided Δ\|mo\| + faded tape PnL separately.
2. **V-fade execution bot (paper first)** — causal recovery@2s entry; 5s horizon; RT haircut; nest+intensity hard gates; honesty labels forced.
3. **Feature store** — join `mm_quoting/out/panel_cache.json` + `applications/out/event_panel/` → class-model training set (P(V), nest severity) with leakage checklist.

**Do not build next:**

- xvenue lag taker (Kill, ~0 gross)
- causal / live cont-ride (Kill)
- slow V-fade (1–60m Kill)
- “predict mid” ML without dense mid OOS
- Expanding MM quoting as alpha narrative

---

## 6. Capacity & honesty

| Claim | Reality |
|-------|---------|
| Fill model | Tape mo × synthetic size — **ceiling**, not queueable size |
| Live impact | Unmodeled; larger clips → worse than research_sim |
| Fees | RT 4 bps research default; venue maker/taker schedules not fully in edge_lab |
| Promote ≠ PnL | int-halt, nest_hard, LR-fire-pause, mm_quoting, paper_harness Δeq = **risk-policy / playbook** |
| Promote ≈ PnL research | **Causal V-fade only** among today’s clears — still `alpha_claim=False` until paper→live |
| paper_harness | 7/7 days · gated 173 / fire 139 · mean Δeq **+296 bps** — shadow maker overlay, day 09-08 dominates |
| Sample | ~1 week · ETH/BTC · HL/DB/KR · n≈275 gated events — fragile to regime shift |

**Bottom line:** Trade the **V-fade** with hard **nest/intensity** brakes; treat MM widen and fire-pause as **insurance**; quarantine lag-take and cont-ride.

---

## Pointers

- Catalog: [`../../EXPERIMENTS.md`](../../EXPERIMENTS.md#2026-09-30)
- Hypotheses: [`TRADE_IDEAS.md`](TRADE_IDEAS.md)
- App map: [`../TRADING_APPLICATIONS.md`](../TRADING_APPLICATIONS.md)
- Labs: `edge_lab/` · `edge_lab/nanex_nest/` · `edge_lab/xvenue_lag/` · `edge_lab/friction/` · `long_range_lab/out/long_edges/` · `mm_quoting/` · `paper_harness/out/RISK_ROLLUP.md`
