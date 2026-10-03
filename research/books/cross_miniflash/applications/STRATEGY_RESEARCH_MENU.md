# Strategy research menu — multi-horizon quant book

**Date:** 2026-09-30  
**Parent playbook:** [`HOW_WE_TRADE.md`](HOW_WE_TRADE.md)  
**Session catalog:** [`../../EXPERIMENTS.md`](../../EXPERIMENTS.md#2026-09-30)  

**Executable earn:** [`edge_lab/V_FADE_STRATEGY_SPEC.md`](edge_lab/V_FADE_STRATEGY_SPEC.md)  
**Executable save:** [`RISK_GATE_STACK.md`](RISK_GATE_STACK.md)  
**Class-model surface:** [`feature_models/`](feature_models/) · join [`mm_quoting/out/panel_cache.json`](mm_quoting/out/panel_cache.json) + [`out/event_panel/`](out/event_panel/)  
**Honesty:** `research_sim_on_real_tape` · `live_orders=False` · `alpha_claim=False` · RT typically **4 bps** · ClickHouse MCP banned.

This expands HOW_WE_TRADE’s timeframe stack into a **research menu**: which horizons pay, which model families fit *our* features, what data unlocks the next Promote, and an opinionated ranking of bets given today’s outs.

---

## 0. Verdict first (read this)

| Rank | Research bet | Economy | Edge type | Evidence (today) | Next unlock |
|-----:|--------------|---------|-----------|------------------|-------------|
| **1** | **Causal V-fade paper → live shadow** | Earn | Seconds (2s–5s hold) | net **+11.63** bps CI[7.67,15.91] n=117 | OE fills + mid_mo (today mid_frac=0) |
| **2** | **Full RISK_GATE_STACK wire** | Save | Sub-s → 5m pause | int-halt Δ\|mo\| **+6.5**; nest **+5.1**; LR-fire-pause@5m **+19.8** | `fire_pause_5m` clock + nest_hard=0 in harness |
| **3** | **P(V\|x) / nest-severity class models** | Earn×Save dial | Event seconds | recovery rule is hard 0.5; occurrence AUC_te≈0.635 Soft Promote | Soft size = f(P̂_V); leak-free panel join |
| **4** | **Hawkes-lite intensity → ladder prior** | Save | Seconds–minutes | intensity_60s already drives fire tiers; LR pause value peaks @5m | Point-process λ̂(t) vs rolling count; denser TOB for nest timing |
| **5** | **Powered 15–60m cont / cluster / drift** | Speculative earn | Intraday Holds | point + but CI∋0 or n&lt;20 | More days + SOL; OE for capacity; **Kill slow V-fade** |

Everything below is justification. Kill list stays hard: causal cont-ride@5s, all xvenue_lag, LR-v-slow-fade, LR-cluster-fade as alpha, mid-predict ML without mid OOS.

---

## 1. Horizon atlas (money by clock)

### 1A. HFT / microstructure — sub-second → ~30s

**Job:** detect gated SSM + Nanex; decide fade vs flat; throttle aggressor.

| Mechanism | Status | Key numbers | Artifact |
|-----------|--------|-------------|----------|
| Event-time SSM detect (trade tape) | **Required** | ~9 gated crashes/day HL ETH; N=300/9000 trade bars → **0** gated/day | [`horizon_lab/HORIZON_RECOMMENDATION.md`](horizon_lab/HORIZON_RECOMMENDATION.md) |
| Causal **V-fade** taker | **Promote earn** | +11.63 after RT=4; Survive hs≤5bp | [`edge_lab/out/EXP_REPORT.md`](edge_lab/out/EXP_REPORT.md) · [`V_FADE_STRATEGY_SPEC.md`](edge_lab/V_FADE_STRATEGY_SPEC.md) |
| Kill-ladder / TI-int-halt | **Promote save** | Δ\|mo\| fire−obs +6.54 CI[2.17,10.68] n_fire=226 | edge_lab · [`RISK_GATE_STACK.md`](RISK_GATE_STACK.md) |
| nest_hard_pause | **Promote save** | Δ\|mo\| +5.11; policy +3.20; OOS Δ\|mo\| +9.26 | [`edge_lab/nanex_nest/out/`](edge_lab/nanex_nest/out/) |
| MM stay-wide / confirm-restore | **Promote playbook** | V mo@5s −16.5; cont +12.1; `always_stay_wide` best | [`mm_quoting/out/`](mm_quoting/out/) |
| xvenue lag-take | **Kill** | hl_to_thick net −4.17; gross≈−0.17 | [`edge_lab/xvenue_lag/out/`](edge_lab/xvenue_lag/out/) |
| Causal cont-ride @5s | **Kill** | −2.83 CI∋0; dies @1bp friction causal | edge_lab · friction |

**Opinion:** This is where the desk’s *earned* edge lives. Horizon_lab killed the fantasy that 300/9000 trade bars are a detection clock — mini-flashes average away. Paper-live stays on **ms trade tape** (coalesce wake ≤1s OK); N-tick bars are **hold/intensity windows**, not KF observation clocks ([`horizon_lab/out/EXP_REPORT.md`](horizon_lab/out/EXP_REPORT.md)).

**Data next (this horizon):**

| Need | Why | Without it |
|------|-----|------------|
| **OE (order entry) shadow fills** | Tape mo × synthetic size is a **ceiling**; slip + queue-position unknown | Cannot flip `alpha_claim` |
| **Denser TOB** (collector, median Δt≃0.55s vs warehouse ~minutes) | Outside-TOB / mid markout / maker adverse selection | mid_frac stays 0 → Hold on tape_markout as exec throttle ([`feature_models/EXP_REPORT.md`](feature_models/EXP_REPORT.md)) |
| Venue-local Nanex bit on live stream | nest_hard already Promote on join; live needs same bit | Soft escalate only |

---

### 1B. Event minutes — ~1–15m

**Job:** keep size off after fire; do **not** extend the V-fade.

| Mechanism | Status | Key numbers | Artifact |
|-----------|--------|-------------|----------|
| **LR-fire-pause @5m** | **Promote save** | Δ\|mo\| +19.8 CI[5.6,32.2] n=194; @15m also Promote; @30m Hold | [`long_range_lab/out/long_edges/EXP_REPORT.md`](long_range_lab/out/long_edges/EXP_REPORT.md) |
| LR-v-slow-fade (1–60m) | **Kill** | 1m −0.93; longer worse; early/late flip | same |
| LR-cont-long-ride @15m | **Hold** | +19.58 CI[−7.48,51.34] n=27 | same |
| LR-ssm-drift-ride @30m | **Hold** | +13.70 CI[−2.53,29.67] n=98 | same |

**Opinion:** Minutes are a **risk horizon**, not a fade horizon. Causal V mean-reverts on the tape by ~5s; stretching the fade to minutes is anti-edge (LR-v-slow-fade Kill across all holds). The one clear Promote is **pause aggressor for 5m after fire** — largest Δ\|mo\| on the board today. Cont-ride at 15m is the only speculative earn worth sample (point positive, CI∋0, n thin).

**Data next:**

| Need | Why |
|------|-----|
| Longer panel (27d HL ETH is better than Phase-4 week, still regime-fragile) | Kill or Promote cont/drift cleanly |
| Sparse-book honesty label on long holds | Warehouse cadence ≠ ms L2; already flagged in long_range honesty |
| OE for any cont-ride paper | 15–60m holds without fill model are fiction |

---

### 1C. Intraday 15–60m Holds

| Id | Best hold | Net / note | Decision | Research stance |
|----|-----------|------------|----------|-----------------|
| LR-cont-long-ride | 15m | +19.58 CI∋0 n=27 | Hold | **#5 bet** — widen sample before building a bot |
| LR-cluster-ride | 60m | +46 CI excludes 0 but **n=12** | Hold (underpowered) | Cluster ≥3 SSM/300s — ride, don’t fade |
| LR-cluster-fade | — | fade side loses / isolated fade Kill | Kill / anti-edge | Do not research further as alpha |
| LR-ssm-drift-ride | 30m | +13.7 CI∋0 n=98 | Hold | Closest to powered Hold; still not Promote |

**Opinion:** Treat 15–60m as a **research queue only** until one of cont / cluster-ride / drift excludes 0 with n≥40 and early/late sign-stable. Cluster-fade is closed (anti-edge). Do not mix these into the V-fade bot.

**Data next:** multi-week ETH+BTC+SOL · dense TOB for entry marks · OE for exit realism · explicit non-overlap + capacity caps (cluster n is tiny because events collide).

---

### 1D. Daily risk-budget models

**Job:** set base size / day prior from ex-ante regime — not pick trades.

| Feature / model | Status | Fit to our stack | Artifact |
|-----------------|--------|------------------|----------|
| Day crash **occurrence** logistic | Soft Promote | AUC_te≈**0.635**; Brier_te≈0.24 | [`feature_models/EXP_REPORT.md`](feature_models/EXP_REPORT.md) |
| Severity \|ΔP\| Ridge | **Hold** | OOS R² **&lt;0** — do not size from predicted hole depth | same |
| VPIN×logN interact | Promote (med) **feature** | boot CI [−0.137,−0.032] | same |
| H^v / FEI | Promote dashboard / schedule Hold | H^v≈0.48 · FEI≈0.75; child schedule exposure CI∋0 | [`hv_fei_capacity/`](hv_fei_capacity/) · [`../../research/lib/fei.py`](../../../lib/fei.py) |
| Tick-constrained regime | Taxonomy Promote; numeric Hold | Native KR spot ~85% 2-tick constrained; HL frac_c≈0.99 | mm_confr / [`EXPERIMENTS.md`](../../EXPERIMENTS.md#2026-09-30) §6 |
| paper_harness Δeq | Risk shadow | pooled +296 bps; day 09-08 dominates | [`paper_harness/out/RISK_ROLLUP.md`](paper_harness/out/RISK_ROLLUP.md) |
| Beta–Binomial V-rate | Monitor | Day/venue posterior P(V) for size prior | [`signal_boards/`](signal_boards/) |

**Opinion:** Daily layer = **budget**, not alpha. Use occurrence + VPIN×size + tick-constrain + nest/fire rates to set `base_clip` and max concurrent fades. Never promote severity regression as a trade signal. Quiet-day check (2026-09-30 HL ETH: gated 0 → stack idle) is the regression test that risk budget correctly goes to sleep.

**Data next:** rolling multi-week cell panel for occurrence recalibration · venue holdout (train HL, test DB/KR) · Kraken PF futures L2 (spot-only today) · hour×FEI joint schedule once denser TOB exists.

---

## 2. Model families — what fits *our* features

Features we actually have on the join surface (`panel_cache` events + `event_panel` nest/tier/intensity):

`direction`, `dp_pct`, `i_c`, `z_peak`, `recovery_1s/2s`, `mo_*`, `intensity` / `intensity_60s`, `nanex_overlap`, ladder `tier`, `H_v`, `vpin_exante`, `log_notional_pre`, `hour_utc`, venue/symbol/day. **Not** reliable: mid_mo, dense OFI, OE fill, per-tick Hawkes fits OOS.

Leakage iron law (HOW_WE_TRADE §3): never train live rules on `label@5s`, `mo_5s`, `recovery_5s`.

| Family | Target that fits | Features | Expected edge vs simple rule | Priority |
|--------|------------------|----------|------------------------------|----------|
| **Simple rules** | Fade / size∈{0,0.25,1} | recovery@2s≥0.5; nest bit; fire tier | **Baseline already Promote** — beat this or don’t ship | Shipped (spec) |
| **Logistic / linear (class_models)** | P(V\|x), P(nest severity), day occurrence | intensity, z_peak, VPIN×logN, H^v, FEI, venue, nest, recovery_1s | Soft size f(P̂) may cut false fades; occurrence Soft Promote already | **Bet #3** |
| **Regression (severity / mo)** | \|ΔP\|, adverse mo | ex-ante VPIN, intensity, Amihud, H^v | Severity OOS dies; use only as **monitoring** (RISK_GATE_STACK §regression) | Low (monitor) |
| **Survival / hazard** | Time-to-V-confirm / hazard of continuation | same + duration-so-far, σ_m; censor @5s/30s | Could replace fixed 2s confirm with “fade when hazard peaks” | Medium research |
| **Hawkes-lite intensity** | λ̂ of gated events / Nanex bursts | event times + marks (z, venue); nest as mark | Better fire prior than rolling `intensity_60s` count; feeds ladder | **Bet #4** |
| **Online / Bayesian** | Posterior P(V), crash rate by venue-day | Beta–Binomial V-rate; hierarchical forget | Day risk budget when base rates shift | Medium (signal_boards exists) |
| **ML classifiers (GBDT / small net)** | V vs cont / nest severity **only** | panel join; **no** mid fantasy | Ship iff Brier/AUC **and** sized-fade PnL beat logistic+rule | After logistic clears |
| **Stat arb / x-venue mean-revert** | Cross-ex mid gap / lag | multi-venue TOB | Today’s lag-take gross≈0 → **Kill**; SOR child-size Hold only | Quarantine |
| **N-tick bar MFT** | Hold on every N TOB closes | resampled panel | Detection Kill at N≥300; maybe hold cadence for xarb/MFT *after* event detect | Out of scope for mini-flash alpha |

### Class-models path (concrete)

```text
applications/feature_models/          # runners + EXP_REPORT (occurrence / VPIN / Hold densify)
applications/mm_quoting/out/panel_cache.json
applications/out/event_panel/panel_rows.json
applications/signal_boards/           # Bayes V-rate, ROC, MI boards
→ training set for P(V), nest severity, day occurrence
→ size mult into V_FADE_STRATEGY_SPEC + RISK_GATE_STACK
```

Re-run feature surface: `python3 applications/run_mm_features.py` (or `feature_models/exp_feature_models.py`).  
Do **not** invent a parallel `class_models/` tree until logistic P(V) beats the hard 0.5 rule on **sized-fade PnL** OOS.

### Hawkes-lite (opinionated design)

We already have a discrete intensity ladder (`intensity_60s` + within-gated z percentiles). Hawkes-lite means:

1. Fit a marked Hawkes (or exponential self-exciting) on **gated SSM event times** per venue×symbol, marks = `{z_peak, nest}`.
2. Compare λ̂(t) quantiles to today’s fire tiers on the **same** Δ\|mo\| scoreboard.
3. Promote only if λ̂ improves Δ\|mo\| avoided vs `intensity_60s` with early/late stable.

Without denser TOB / Nanex timestamps, “quote-storm Hawkes” (filmonov lane) stays sibling Hold — do not conflate with our gated SSM intensity.

### Survival (when it is worth it)

Fixed confirm@2s is already Promote. Survival is justified only if:

- Many fades are late-confirmed Vs that partial-threshold skips, **or**
- Cont hazard rises before 2s and we can flatten sooner.

Censor at 5s to match mo@5s economics; falsifier = sized PnL ≤ causal rule.

---

## 3. Data wishlist by horizon (OE + denser TOB)

| Horizon | Must-have next data | Nice-to-have | Kill if missing forever |
|---------|---------------------|--------------|-------------------------|
| HFT seconds (V-fade) | **OE shadow** (fill px, slip, reject) · mid series with mid_frac≥0.5 | Collector TOB ≤1s; per-venue fees | Live alpha_claim |
| Event minutes (fire-pause) | Live `fire_pause_5m` clock in actions.jsonl | Hawkes λ̂; SOL cells | — (risk still useful on tape mo) |
| 15–60m Holds | More days + non-overlap engine · OE for capacity | Dense TOB entry marks | Promoting on n&lt;20 |
| Daily budget | Multi-week occurrence panel · venue holdout | KR futures L2; hour×FEI | Sizing from severity Ridge |
| Class models | Leak-free join checklist in code | Calibrated P(V) by venue | Training on recovery_5s / mo_5s |
| Stat arb / xvenue | — | denser multi-venue TOB for SOR child-size only | Lag-take (already Kill on gross≈0) |

Warehouse vs collector (horizon_lab): Phase-4 warehouse TOB median Δt≃**177s**; dense collector days ~**0.55s**. Crash SSM detection is **trade-tape** — available at ms even when BBO is sparse. Sub-second queue-position and outside-TOB claims need collector TOB; do not pretend warehouse BBO is HFT.

---

## 4. Opinionated research ranking (expected edge given evidence)

Scored on: (evidence strength) × (earn vs save magnitude) × (path to paper) × (sample honesty).

### Top 5 research bets

1. **Ship causal V-fade paper bot** — only cleared *earn* (+11.6 bps). Spec locked: [`V_FADE_STRATEGY_SPEC.md`](edge_lab/V_FADE_STRATEGY_SPEC.md). Wire nest+int gates; keep `alpha_claim=False` until OE+mid.  
2. **Complete RISK_GATE_STACK in harness** — largest *saved* money (5s Δ\|mo\| ~6–9 + 5m ~20). Gaps: `fire_pause_5m`, nest_hard→0. Spec: [`RISK_GATE_STACK.md`](RISK_GATE_STACK.md).  
3. **Class-model soft P(V) / nest severity** on [`feature_models/`](feature_models/) join — beat hard 0.5 on sized-fade PnL; occurrence already Soft Promote for day budget.  
4. **Hawkes-lite λ̂ vs intensity_60s** for ladder prior — incremental save; uses event times we already log; falsify against TI-int-halt board.  
5. **Power LR-cont / drift / cluster-ride to Promote or Kill** — only open earn at 15–60m; slow V-fade and cluster-fade are closed.

### Deliberately deprioritized

| Item | Why deprioritize |
|------|------------------|
| xvenue lag-take / cross-ex “alpha” | Gross≈0; RT makes −4 bps; all 5 rules Kill |
| Causal cont-ride @5s | Kill; oracle Survive ≠ causal |
| Predict-mid ML | mid_frac=0; fantasy without denser TOB+OE |
| Severity Ridge as sizer | OOS R²&lt;0 |
| N=300/9000 as SSM detection clock | gated/day → 0 ([`horizon_lab`](horizon_lab/HORIZON_RECOMMENDATION.md)) |
| Expanding MM quoting as PnL story | Promote playbook only; paper_harness Δeq ≠ alpha |
| filmonov / mn_tuwrv vanity | 0 Promote today; throttle/monitor only |

---

## 5. Integration map (how bets compose)

```text
                    ┌─────────────────────────┐
  trade tape ms ──► │ SSM detect + Nanex join │
                    └───────────┬─────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
     RISK_GATE_STACK     causal class         day budget
     (Bet #2, #4)        recovery@2s          occurrence/VPIN/H^v
              │                 │                 │
              │          ┌──────┴──────┐          │
              │          ▼             ▼          │
              │     P̂(V) class    hard rule      │
              │     (Bet #3)      ≥0.5           │
              │          └──────┬──────┘          │
              │                 ▼                 │
              │         V-FADE bot (Bet #1)       │
              │         size = clip × P̂ × mult   │
              └────────► effective_mult=0 on      │
                        halt/nest/fire_pause_5m   │
                                                  │
                        base_clip ◄───────────────┘
                        (daily)

  15–60m Holds (Bet #5) — separate book, never inside V-fade state machine
```

Paper path: `paper_harness` (risk shadow) + `edge_lab/v_fade_paper/` (taker scoreboard) + `paper_live` twin. Do not score V-fade on maker Δequity.

---

## 6. Falsifiers (shared)

| Bet | Kill / Hold trigger |
|-----|---------------------|
| V-fade | K1–K8 in [`V_FADE_STRATEGY_SPEC.md`](edge_lab/V_FADE_STRATEGY_SPEC.md) §7; rolling net≤0; early/late flip |
| Risk stack | Δ\|mo\| CI∋0 on intensity/nest; monitoring β₁,β₂ flip; stack fires on quiet days |
| Class models | Sized-fade PnL ≤ hard rule; Brier worse than logistic; any label@5s leakage |
| Hawkes-lite | λ̂ does not beat intensity_60s on Δ\|mo\| OOS |
| LR Holds | Still CI∋0 at n≥40 → Kill or abandon; sign flip → Kill |

---

## 7. Pointers (today’s outs)

| Topic | Path |
|-------|------|
| Session scoreboard | [`../../EXPERIMENTS.md`](../../EXPERIMENTS.md#2026-09-30) |
| Money map | [`HOW_WE_TRADE.md`](HOW_WE_TRADE.md) |
| V-fade spec | [`edge_lab/V_FADE_STRATEGY_SPEC.md`](edge_lab/V_FADE_STRATEGY_SPEC.md) |
| Risk throttle | [`RISK_GATE_STACK.md`](RISK_GATE_STACK.md) |
| Edge lab | [`edge_lab/out/EXP_REPORT.md`](edge_lab/out/EXP_REPORT.md) |
| Nest deep | [`edge_lab/nanex_nest/out/NANEX_NEST.md`](edge_lab/nanex_nest/out/NANEX_NEST.md) |
| Friction | [`edge_lab/friction/out/FRICTION_REPORT.md`](edge_lab/friction/out/FRICTION_REPORT.md) |
| Xvenue Kill | [`edge_lab/xvenue_lag/out/EXP_REPORT.md`](edge_lab/xvenue_lag/out/EXP_REPORT.md) |
| Long edges | [`long_range_lab/out/long_edges/EXP_REPORT.md`](long_range_lab/out/long_edges/EXP_REPORT.md) |
| Horizons | [`horizon_lab/HORIZON_RECOMMENDATION.md`](horizon_lab/HORIZON_RECOMMENDATION.md) |
| Class / features | [`feature_models/EXP_REPORT.md`](feature_models/EXP_REPORT.md) · [`out/event_panel/`](out/event_panel/) |
| Paper risk | [`paper_harness/out/RISK_ROLLUP.md`](paper_harness/out/RISK_ROLLUP.md) |
| Ideas | [`TRADE_IDEAS.md`](TRADE_IDEAS.md) |

**Bottom line:** Rank research by *cleared* economics — **fade Vs in seconds**, **pause fire for minutes**, **model class to dial size**, then either kill or promote the thin 15–60m Holds. Do not spend sample on lag-take, slow fades, or mid ML until OE and denser TOB exist.
