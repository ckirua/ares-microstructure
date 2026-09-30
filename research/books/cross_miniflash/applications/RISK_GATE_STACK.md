# MONEY-SAVING stack — risk throttle (not alpha)

**Class:** risk-policy overlay · **not** directional PnL  
**Path:** `applications/RISK_GATE_STACK.md`  
**Honesty:** `research_sim_on_real_tape` · shadow paper only · live_orders=False · ClickHouse MCP banned  

This stack **saves money** by cutting size / pausing when venue-local crash intensity fires. It overlays **any** strategy (taker POV, arb, MM, momentum) as a throttle on aggressor notional and quote size — it does not pick direction.

---

## Components (all Promote as risk-policy, 2026-09-30)

| Layer | ID | Horizon | Policy | Δ\|mo\| (bps) | n | Source |
|-------|-----|---------|--------|---------------|---|--------|
| Short intensity | **TI-int-halt** | mo@5s | fire `{widen,size_cap,halt}` → clip/halt aggressor | **+6.54** CI[2.17, 10.68] | 226 fire | [`edge_lab/out/EXP_REPORT.md`](edge_lab/out/EXP_REPORT.md) |
| Nest escalate | **TI-nanex-nest** | mo@5s | Nanex∩SSM → **`nest_hard_pause`** (size→0) | **+5.11** CI[0.53, 10.28] | 66 nest | same · deep join [`edge_lab/nanex_nest/`](edge_lab/nanex_nest/) |
| Long pause | **LR-fire-pause@5m** | \|mo\|@5m | fire tier → **pause 5m** | **+19.83** CI[4.89, 32.92] | 194 fire | [`long_range_lab/out/long_edges/EXP_REPORT.md`](long_range_lab/out/long_edges/EXP_REPORT.md) |
| Executable ladder | **paper_harness kill_ladder** | clock + shadow | `observe→widen→size_cap→halt` size mult | **+6.54** CI[1.76, 10.40] | 230 fire | [`kill_ladder/EXP_REPORT.md`](kill_ladder/EXP_REPORT.md) · [`paper_harness/`](paper_harness/) |

**Reading Δ\|mo\|:** fire − observe (or nest − SSM-only). Positive = fire windows are *more* adverse → pausing / clipping **avoids** that tape. Not naked taker PnL.

**Quiet-day check (2026-09-30 HL ETH paper):** gated SSM **0** · ladder fires **0** · Δ equity ladder−baseline **0** — stack correctly **idle** when intensity is cold ([`paper_live/out/2026-09-30_hyperliquid_ETH/RISK_REPORT.md`](paper_live/out/2026-09-30_hyperliquid_ETH/RISK_REPORT.md)).

---

## Unified throttle table

Map every strategy's **child size / quote size / take permission** through one venue-local state. Default size mult from [`paper_harness/config.yaml`](paper_harness/config.yaml):

| State | `quote_size_mult` / take size | Aggressive takes | Quotes | Hold |
|-------|-------------------------------|------------------|--------|------|
| `none` / cold | **1.0** | allow | normal | — |
| `observe` | **1.0** | allow | normal | log only · `ladder_hold_s` (60s) |
| `widen` | **0.5** | soft_clip | half size | 60s |
| `size_cap` | **0.25** | size_cap | quarter | 60s |
| `halt` | **0.0** | halt | **pull** | 60s |
| `nest_hard_pause` | **0.0** | halt | **pull** | `nanex_pull_s` (15s) min; extend if still nested |
| `fire_pause_5m` | **0.0** | halt | **pull** (MM) / no new children (taker/arb) | **300s** from fire start |

**Max of severity wins** (never average):

```
effective_mult = min(
  ladder_tier_mult,          # TI-int-halt / kill_ladder
  0.0 if nest_hard_pause,    # TI-nanex-nest
  0.0 if in fire_pause_5m,   # LR-fire-pause@5m
)
```

### Cut rules (desk-facing)

| Cut | When |
|-----|------|
| → **0.25** | ladder tier `size_cap` (within-gated z ≥ p50 or intensity escalate without halt) · **or** soft clip after widen if strategy has no half-size knob |
| → **0** | ladder `halt` · **or** Nanex∩SSM `nest_hard_pause` · **or** any fire tier while `fire_pause_5m` clock is live |
| **pause 5m** | first transition into fire `{widen,size_cap,halt}` starts a **300s** no-new-risk window (LR-fire-pause); nest can re-arm halt inside that window |

Widen (0.5) is optional softening before size_cap; desk may collapse widen→size_cap if the book has only {1, 0.25, 0} knobs.

---

## Overlay on ANY strategy

The stack does **not** change signal sign. It multiplies risk.

| Strategy | What gets throttled | What stays |
|----------|---------------------|------------|
| **Taker POV** | Child notional × `effective_mult`; halt → cancel resting children, no new takes | POV schedule / participation *target* (resume after pause) |
| **Cross-ex arb / xarb** | Aggressor leg size; halt → no cross; nest → both legs flat | Fair-value / gap signal (still computed) |
| **MM / quoting** | `quote_size_mult` + `pull` on halt/nest/5m pause; widen softens | Mid/skew model; restore policy *after* pause (prefer ladder∩confirm, not blind) |
| **Momentum / cont-ride** | Position add size; halt/nest/5m → flat adds only (may hold existing if desk policy allows) | Direction from momentum model |

**Anti-patterns:** do not use absolute z\*∈{8,10,12}; do not wait for HL↔DB↔KR concordance; do not treat Nanex-solo (no SSM) as hard pause; do not claim stack PnL as alpha.

---

## Detection → ladder (shared)

Same gate as kill_ladder / paper_harness:

1. SSM detect (`σ_m` floor, z\*=6) → severity gate **10 bps / i_c≥5**
2. Within-gated z percentiles + rolling **intensity_60s** + Nanex∩SSM → tier  
   Breaks (Phase-4 defaults): p25≈12.5 · p50≈15.9 · p75≈20.4 · dp_p90≈0.45  
3. Emit action record (`ladder.py` / `event_action_records`) with `nanex_overlap` escalate bit
4. Apply size mult + optional **5m fire pause** clock + nest hard pause

Venue-local only (concordance Hold).

---

## paper_harness implementation map

| Spec piece | Code / config | Status |
|------------|----------------|--------|
| Tier → size / pull | [`paper_harness/harness/ladder.py`](paper_harness/harness/ladder.py) `TIER_ACTIONS` · `FIRE_TIERS` | **Wired** |
| Size mult 1 / 0.5 / 0.25 / 0 | [`paper_harness/config.yaml`](paper_harness/config.yaml) `size_mult` | **Wired** |
| Detect + Nanex nest | `harness/detect.py` · `nanex_pull_s` / `nanex_slack_s` | **Wired** |
| Action JSONL | `harness/actions.py` · `pipeline.py` → `actions.jsonl` | **Wired** |
| Shadow bind | `harness/shadow_fills.py` (`KillLadderOverlay` + **`RiskGateStackOverlay`**) | **Wired** |
| Combined throttle | [`harness/risk_stack.py`](paper_harness/harness/risk_stack.py) `effective_mult_at` · nest_hard · fire_pause_5m | **Wired** |
| Daily scoreboard | `RISK_REPORT.md` · mo@5s · tier counts · Δ equity (risk label) | **Wired** |
| Multi-day rollup | [`paper_harness/out/RISK_ROLLUP.md`](paper_harness/out/RISK_ROLLUP.md) baseline vs **full stack** | **Wired** |
| Live poll twin | [`paper_live/live/poll.py`](paper_live/live/poll.py) (same ladder; still shadow) | ladder only |

**Wired (2026-09-30 deep build):**

1. **`fire_pause_5m` clock** — `fire_pause_5m_s: 300` in config; parallel mask in `build_risk_gate_clock`; `kind: fire_pause_5m` in `actions.jsonl`.
2. **`nest_hard_pause` as hard 0** — Nanex∩SSM forces `quote_size_mult=0` / `pull=True` even on widen-only (`apply_nest_hard_pause`).
3. **Strategy adapter** — `RiskGateStackOverlay` applies `effective_mult(ts)` (max severity); MM shadow path in paper_harness. POV/arb/momentum adapters reuse the same clock hook.

Run:

```bash
cd research/books/cross_miniflash/applications/paper_harness
python3 run_paper_day.py --day 2026-09-04          # historical fire day
python3 run_paper_day.py --day 2026-09-30          # quiet → expect idle
python3 run_paper_day.py --panel-days --extra-venues deribit,kraken
```

---

## Paper harness panel — baseline vs full stack (HL ETH)

**Window:** 2026-09-04…10 · venue `hyperliquid` · symbol `ETH` · 7/7 ok  
**Artifact:** [`paper_harness/out/RISK_ROLLUP.md`](paper_harness/out/RISK_ROLLUP.md) · `out/rollup.json` · per-day `figs/stack_regime_counts.png`

| Metric (mean over 7 days) | Ladder-only | **Full RISK_GATE_STACK** |
|---------------------------|------------:|-------------------------:|
| Δ fills (overlay−baseline) | — | **−4312** |
| Δ fire-window fills | **−479** | **−1647** |
| mean \|mo@5s\| among fire | 18.07 bps | (tape; shared) |
| avoided adverse-mo proxy (−Δfire_fills × \|mo\|fire) | — | **~3.2e4** (scoreboard units) |
| Δ marked equity (bps) | +296 | +1454 |
| frac overlay nullified | 0 | **0** |
| total gated / fire | 173 / 139 | same |

**Day extremes (stack):** fire-fills cut ranges −332 (09-10) … −4365 (09-08). On fire days `fire_pause_5m` often zeros crash-window fills entirely (e.g. 09-04 stack fire_fills **0** vs baseline **1603**).

**Honesty:** Δ equity / avoided-mo proxy = **risk throttle scoreboard**, not tradable alpha. Promote still rests on event-study Δ\|mo\| (int-halt / nest / LR-fire-pause packages above).

---

## Monitoring regression (not alpha)

Fit on gated events (panel / `actions.jsonl` join), **monitoring only**:

\[
\texttt{adverse\_mo\_5s}_i \;=\; \beta_0 + \beta_1\,\texttt{intensity\_60s}_i + \beta_2\,\texttt{nest}_i + \boldsymbol{\gamma}'\texttt{venue}_i + \boldsymbol{\delta}'\texttt{class}_i + \varepsilon_i
\]

| Term | Definition |
|------|------------|
| `adverse_mo_5s` | \|mo@5s\| or signed adverse vs inventory/crash (desk choice; default \|mo@5s\|) |
| `intensity` | gated `intensity_60s` (or tier ordinal observe=0…halt=3) |
| `nest` | 1 if Nanex∩SSM |
| `venue` | HL / DB / KR dummies (venue-local fits preferred) |
| `class` | V / cont / partial (recovery@1–2s causal) |

**Use:** coefficient signs/stability as a **health check** that fire/nest still predict adverse tape. Refit weekly; if \(\hat\beta_1,\hat\beta_2\) CI∋0 or early/late sign flip → **Hold** stack (do not turn off blindly on one quiet day).

**Do not:** trade on residual; size from \(\hat y\); claim R² as edge.

Falsifiers already in apps: Δ\|mo\| CI must exclude 0 after friction · time-split stable · nest precision ≫ Nanex-solo.

---

## When the desk should turn this on

**Turn ON (paper → candidate live risk wire) when all hold:**

1. Venue cell has warehouse/collector tape + SSM gate wired (HL ETH primary today).
2. Event-study Δ\|mo\| still clears friction (int-halt ~6.5bps @5s · nest ~5bps · fire-pause ~20bps @5m) with early/late stable on the current panel.
3. paper_harness shows ladder **binding** on fire days (Δ fills / fire-window equity move) and **idle** on quiet days (2026-09-30 pattern).
4. Strategy adapters expose a single `size_mult` / pause hook (POV, arb, MM, momentum).

**Keep OFF / idle when:**

- No gated SSM (cold intensity) — stack should no-op, not invent pause.
- Concordance-only or Nanex-solo without SSM.
- Absolute-z ladder proposed instead of within-gated percentiles.
- Monitoring regression \(\beta\) on intensity/nest collapses OOS.

**First wire:** HL ETH venue-local kill_ladder + nest_hard_pause + `fire_pause_5m` in paper_harness (done as shadow); paper_live still ladder twin. MM restore stays **ladder∩confirm**, not this stack's job.

---

## Artifact index

| Evidence | Path |
|----------|------|
| Edge lab scoreboard (today) | [`edge_lab/out/EXP_REPORT.md`](edge_lab/out/EXP_REPORT.md) |
| Nanex nest deep join | [`edge_lab/nanex_nest/out/NANEX_NEST.md`](edge_lab/nanex_nest/out/NANEX_NEST.md) |
| Long-range fire-pause | [`long_range_lab/out/long_edges/EXP_REPORT.md`](long_range_lab/out/long_edges/EXP_REPORT.md) |
| Kill-ladder package | [`kill_ladder/EXP_REPORT.md`](kill_ladder/EXP_REPORT.md) |
| Paper harness + stack rollup | [`paper_harness/README.md`](paper_harness/README.md) · [`paper_harness/out/RISK_ROLLUP.md`](paper_harness/out/RISK_ROLLUP.md) |
| Ideas map | [`TRADE_IDEAS.md`](TRADE_IDEAS.md) `TI-int-halt` · `TI-nanex-nest` |
| Desk board | [`../DESK_MEMO.md`](../DESK_MEMO.md) §7 |

**Verdict:** Promote-as-**risk-policy** stack. Money saved = avoided adverse \|mo\| under fire/nest/5m pause — often more valuable than the directional edges still on Hold/Kill in the long-range lab. Shadow panel shows the combined throttle **binds** (Δ fire fills ≪ 0, nullified=0); do **not** read Δ equity as alpha.
