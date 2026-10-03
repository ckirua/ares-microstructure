# Experiments changelog

Research-book session catalog for `research/books/`. **Not** the product/repo changelog — that lives at [`../../CHANGELOG.md`](../../CHANGELOG.md).

## How to append a new day

1. Add a new `## YYYY-MM-DD` section **immediately below this how-to** (newest date first).
2. Lead with a one-paragraph “what we got”, then a **Scoreboard** table, then short subsections for each lab (re-run cmd, honesty, key numbers, decision).
3. Keep Promote / Hold / Kill substance and link `out/` reports — do not paste raw dumps.
4. Do **not** create `EXPERIMENTS_YYYY-MM-DD.md` daily files; put the day here.
5. For product/repo Added/Changed/Fixed notes, append under [`../../CHANGELOG.md`](../../CHANGELOG.md) instead (or a brief pointer from that day’s Research experiments bullets back here).

Honesty default across apps: `research_sim_on_real_tape` · live_orders=False · alpha_claim=False · ClickHouse MCP banned · RT friction typically 4 bps. Money map: [`cross_miniflash/applications/HOW_WE_TRADE.md`](cross_miniflash/applications/HOW_WE_TRADE.md).

Program-local “tested vs not” ledgers (e.g. [`cross_miniflash/EXPERIMENTS.md`](cross_miniflash/EXPERIMENTS.md)) stay in their book trees.

---

## 2026-09-30

Session catalog of ares-microstructure research-book runs (chat + parallel workers). **What we got:** edge_lab cleared causal **TI-v-fade** (+11.63 bps), **TI-int-halt**, and **TI-nanex-nest** as Promotes while killing **TI-cont-ride** and all **xvenue_lag** rules (~−4.2 bps net); mm_quoting Promote (playbook, not alpha); mm_confr native Kraken spot L2 rewired but gates stay Hold (sole Promote = taxonomy); long_range non-MM **LR-fire-pause** Promote (Δ|mo| +19.8); MM kill_ladder “wins” on point but CI includes 0; sibling books (v_shapes / filmonov / mn_tuwrv) refreshed desks without new naked alpha.

### Scoreboard

| Book / app | Experiment | Key metric | Decision | Artifact |
|------------|------------|------------|----------|----------|
| edge_lab | TI-v-fade causal | net **+11.63** bps CI[7.67,15.91] n=117 | **Promote** | `cross_miniflash/applications/edge_lab/out/` |
| edge_lab/v_fade_paper | path gap closed | confirm_r2 path **−5.7** Hold; severity_zend z≥20 @0.5→3s path **+20.2** | **Promote_shadow** | `…/edge_lab/v_fade_paper/out/` |
| edge_lab | TI-cont-ride causal | net **−2.83** bps CI[−7.40,1.56] n=64 | **Kill** | same |
| edge_lab | TI-v-fade+cont combo | net **+6.52** bps CI[3.33,9.90] n=181 (fade-dominated) | **Promote** | same |
| edge_lab | TI-int-halt | Δ\|mo\| fire−obs **+6.54** CI[2.17,10.68] n_fire=226 | **Promote** | same |
| edge_lab | TI-nanex-nest (core) | Δ\|mo\| nest−non **+5.11** CI[0.53,10.28] n_nest=66 | **Promote** | same |
| edge_lab/friction | half-spread kill grid | survive ≥1bp: v-fade / cont-ride(oracle) / int-halt; causal cont **DIE** | mixed | `…/edge_lab/friction/out/` |
| edge_lab/nanex_nest | deep join + policy | nest_hard lift **+3.20** CI[1.45,5.04]; OOS Δ\|mo\| **+9.26** | **Promote** (`nest_hard_pause`) | `…/edge_lab/nanex_nest/out/` |
| edge_lab/xvenue_lag | hl_to_thick (primary) | net **−4.17** CI[−4.37,−3.98] n=390; gross≈−0.17 | **Kill** (all 5 rules) | `…/edge_lab/xvenue_lag/out/` |
| long_range_lab | MM kill_ladder_maker | Δeq **+13.79** CI[−14.86,+50.10] n_cells=27 | **Hold** (CI∋0) | `…/long_range_lab/out/summary.json` |
| long_range_lab | LR-fire-pause @5m | Δ\|mo\| fire−obs **+19.8** CI[5.6,32.2] n=194 | **Promote** | `…/long_range_lab/out/long_edges/` |
| long_range_lab | LR-v-slow-fade @1m | net **−0.93** CI[−12.20,8.27] n=34 | **Kill** | same |
| long_range_lab | LR-cluster-fade | anti-edge (fade side loses / isolated fade Kill) | **Kill** (anti-edge) | same |
| long_range_lab | LR-cont-long-ride @15m | net **+19.58** CI[−7.48,51.34] n=27 | **Hold** | same |
| long_range_lab | LR-cluster-ride @60m | net **+46.06** CI[1.27,104.02] n=12 | **Hold** (underpowered) | same |
| long_range_lab | LR-ssm-drift-ride @30m | net **+13.70** CI[−2.53,29.67] n=98 | **Hold** | same |
| mm_quoting | V vs cont restore | V mo@5s=−16.51; cont=+12.12; best=`always_stay_wide` | **Promote** (med playbook) | `…/mm_quoting/out/` |
| strategy_lab | desk equity stubs | baseline final_mean≈−2069.6 bps; best Δ≈+2.75 (`nanex_temp_pull`) | Hold / risk-sim | `…/strategy_lab/out/` |
| paper_harness | HL ETH kill-ladder shadow | 7/7 days; pooled Δeq **+295.9** bps; gated/fire 173/139 | risk shadow (not alpha) | `…/paper_harness/out/RISK_ROLLUP.md` |
| mm_confr_viewpoints | Pass-2.5 + native KR spot | 1 Promote / 9 Hold / 4 Kill; KR spread≈0.037 vs synth 1.5; scorecard hit_rate **0.33** | taxonomy Promote; numeric Hold | `mm_confr_viewpoints/out/` |
| v_shapes | widen+harden + trade_ideas | 4 Promote / 5 Hold / 2 Kill (MinV risk monitors) | Promote monitors only | `v_shapes/` |
| filmonov | Pass-2 harden | 0 Promote / 13 Hold / 11 Kill | no Promote | `filmonov/out/pass2/` |
| mn_tuwrv | Pass-2.6 blocker-close | 0 Promote; sparse RV / noise clocks Kill | Hold TSRV / Kill sparse | `mn_tuwrv/out/pass2/` |

**Catalogued experiments:** **23** (scoreboard rows).

### 1. edge_lab core (TI top-3)

**Re-run:** `cd research/books/cross_miniflash/applications/edge_lab && python3 exp_edge_lab.py`  
**Honesty:** `research_sim_on_real_tape` · RT=4.0 bps · fills=synthetic_size×signed_tape_mo5s · n=275 events · join miss=0 · days 2026-09-04…10 · ETH/BTC · HL/DB/KR.

| id | decision | headline |
|----|----------|----------|
| **TI-v-fade (causal)** | **Promote** | fade-only net **11.63** bps CI[7.67,15.91] n=117 · early=7.47 · late=14.52 |
| **TI-cont-ride (causal)** | **Kill** | ride-only net **−2.83** bps CI[−7.40,1.56] n=64 · early/late both neg |
| **TI-v-fade+cont combo** | **Promote** | causal combo net **6.52** CI[3.33,9.90] n=181 — fade-dominated |
| **TI-int-halt** | **Promote** | Δ\|mo\| fire−obs **6.54** CI[2.17,10.68] n_fire=226 · pnl gate−always Δ=+12.76 |
| **TI-nanex-nest** | **Promote** | Δ\|mo\| nest−non **5.11** CI[0.53,10.28] n_nest=66 · early=8.05 · late=3.18 |

Oracle class mo@5s: V=−16.51 · cont=+12.12 · partial=+4.09. Causal counts: v_recovery=117 · partial=89 · continuation=69.  
Artifacts: `out/EXP_REPORT.md`, `out/summary.json`, `out/EDGE_LAB.md`, `out/figs/`.

### 2. edge_lab / xvenue_lag → Kill

**Re-run:** `cd …/edge_lab/xvenue_lag && python3 exp_xvenue_lag.py`  
**Honesty:** `research_sim_on_real_multi_venue_tape` · latency=100ms · RT=4 bps.

| rule | n | net mean [lo,hi] | early | late | decision |
|------|--:|------------------|------:|-----:|----------|
| all_pairs | 461 | −4.32 [−4.90,−3.72] | −4.62 | −4.16 | **Kill** |
| **hl_to_thick (primary)** | **390** | **−4.17 [−4.37,−3.98]** | −4.17 | −4.16 | **Kill** |
| any_to_thick | 414 | −4.23 [−4.81,−3.60] | −4.46 | −4.12 | **Kill** |
| hl_nest_to_thick | 78 | −4.02 [−4.43,−3.61] | −4.19 | −3.97 | **Kill** |
| hl_intensity2_thick | 150 | −4.23 [−4.57,−3.90] | −4.43 | −4.18 | **Kill** |

Primary hl_to_thick: gross ≈ **−0.17** bps — edge ≈ 0 before costs; after 4 bps RT the CI sits entirely ≤0. All 5 rules Kill.  
Paths: `applications/edge_lab/xvenue_lag/{exp_xvenue_lag.py,out/EXP_REPORT.md,out/summary.json,out/figs/,XVENUE_LAG.md}`.

### 3. edge_lab / nanex_nest deep join → Promote

**Re-run:** `cd …/edge_lab/nanex_nest && python3 exp_nanex_nest.py`  
Join: panel 275 / exact 275 / miss 0 · n_nest=**66** · nest_rate=0.244.

- Severity: \|mo\| nest=21.95 · SSM-only=16.83 · **Δ\|mo\|=5.11** CI[0.75,9.86] · friction_cleared · time-split stable  
- Policy: **nest_hard** vs baseline **+3.20** CI[1.45,5.04] n=270; nest_soft +2.40  
- Preferred: `nest_hard_pause` · readiness=`promote_as_risk_policy`  
- OOS expanded: n=346 nest=85 · Δ\|mo\| **9.26** CI[4.93,13.58]  
Artifacts: `out/EXP_REPORT.md`, `out/summary.json`, `out/NANEX_NEST.md`, figs.

### 4. edge_lab / friction kill grid

**Re-run:** `cd …/edge_lab/friction && python3 run_friction.py`  
Oracle primary · half-spread grid {0, 0.5, 1, 2, 5} · RT=2×half for taker.

- **Survive @≥1bp:** `TI-v-fade`, `TI-cont-ride` (oracle), `TI-int-halt` · Die @1bp: none (oracle)  
- Max surviving half-spread: v-fade **5.0** · cont-ride **2.0** · int-halt **5.0**  
- At hs=2 (RT=4): v-fade net **+12.51** SURVIVE · cont-ride **+8.12** SURVIVE · int-halt **+4.54** SURVIVE  
- **Causal aux:** `TI-v-fade_causal` @1bp **SURVIVE** (+13.63); **`TI-cont-ride_causal` @1bp DIE** (−0.83) — matches core Kill  
Artifacts: `out/kill_grid.json`, `out/FRICTION_REPORT.md`, `out/figs/fig_kill_grid.png`.

### 5. long_range_lab

**MM overlays** (`run_long_range.py` / `out/summary.json`) — 27 HL ETH days · friction 2 bps one-way · fire Δadverse_mo5=+9.63 (n_fire=199).

| stub | Δ vs baseline (bps) | CI | note |
|------|---------------------|----|------|
| **kill_ladder_maker** | **+13.79** | **[−14.86, +50.10]** | point winner among MM; **CI∋0** → Hold |
| ladder_plus_v_restore | +14.70 | [−14.75, +52.80] | same CI∋0 |
| nanex_temp_pull | +10.73 | [−13.07, +45.78] | CI∋0 |
| confirm_before_restore | +0.05 | [−5.94, +6.62] | flat |

**Non-MM long edges** (`run_long_edges.py` / `out/long_edges/EXP_REPORT.md`) — 27 ETH days · **242** gated SSM · RT=4 bps · minutes–hours holds · **not** edge_lab mo@5s duplicate.

| id | best hold | net / Δ\|mo\| | decision |
|----|-----------|---------------|----------|
| **LR-fire-pause** | 5m | Δ\|mo\| fire−obs **+19.8** [5.6, 32.2] n=194 | **Promote** (long_horizon_intensity_pause; risk policy) |
| **LR-v-slow-fade** | 1m | net −0.93 [−12.20,8.27] n=34 | **Kill** (all holds Kill) |
| **LR-cluster-fade** | — | fade side loses; isolated fade Kill | **Kill** (anti-edge) |
| **LR-cont-long-ride** | 15m | net +19.58 [−7.48,51.34] n=27 | **Hold** (CI∋0) |
| **LR-cluster-ride** | 60m | net +46.06 [1.27,104.02] n=12 | **Hold** (underpowered n&lt;20) |
| **LR-ssm-drift-ride** | 30m | net +13.70 [−2.53,29.67] n=98 | **Hold** (CI∋0) |

Re-run: `cd …/long_range_lab && python3 run_long_edges.py --workers 8`.  
Honesty: `research_sim_on_real_tape_long_holds` · long holds + sparse book cadence — not sub-second L2 claims.

### 6. mm_confr_viewpoints (native Kraken spot + gates)

**Program:** Pass-2.5 hardened — **1 Promote / 9 Hold / 4 Kill** (`DESK_MEMO.md`, `out/hardening/`).  
**Sole Promote:** `disc.tick_rq_taxonomy` (framing vs mmip tick.* — not numeric).  
**Kill:** LSE/Nasdaq RDD; welfare; SEC/IPO; `disc.sign_scorecard_tradable` (ETH **hit_rate=0.33** hits=1 misses=2 in `out/pass1/sign_scorecard.json`).

**Native Kraken spot L2 vs trade_synth** (days 2026-09-26/27/30):

| | synth baseline | native L2 |
|--|----------------|-----------|
| quoted_spread_bps (mean) | ≈**1.50** | ≈**0.037** |
| frac_constrained_2tick | ≈**0.00** | ≈**0.85** |
| τ | 0.1 | 0.01 |
| ρ(rel_tick, spread) pooled | −0.6 | +0.5 (native_rerun) |

Paths: `out/kraken_native/`, `out/pass1_native/`, `out/pass2_native/`, `out/native_rerun/` (+ package figs under `out/<pkg>/`).  
Pass-2 info/exec HL+KR-spot stacks: dual slice documented (spot≠perp); **no new numeric Promotes**. Bootstrap/BTC: placebo BTC weak hi=0.1633; HL frac_c≈0.99.  
Re-run: book harness + `scripts/exp_bootstrap_btc.py` + native rerun scripts under `mm_confr_viewpoints/scripts/`. Notebook: `notebooks/desk_synthesis.ipynb`.

### 7. cross_miniflash applications (other)

#### TRADE_IDEAS / TRADING_APPLICATIONS
Desk playbooks refreshed today: `cross_miniflash/applications/TRADE_IDEAS.md`, `cross_miniflash/TRADING_APPLICATIONS.md` (pointer docs; numbers live in labs above).

#### v_fade_paper — path gap closed → Promote_shadow
Lab mo@5s credited rebound already spent before `confirm_r2@+2s` entry → path **−5.74** Hold. Causal fix `severity_zend` (no r2): `|z_peak|≥20` @ delay **0.5s** → exit **3s** · path **+20.16** CI[9.77,29.79] n=23 · **Promote_shadow**. Artifacts: `applications/edge_lab/v_fade_paper/out/{PATH_GAP_REPORT.md,SHADOW_BOARD.md,gap_summary.json,figs/}`.

#### mm_quoting (V continuation quoting)
**Promote** med quoting playbook — restore after V-confirm; stay wide on cont. **Not** tradable fade.  
n=275 · share_V=0.771 · V mo@5s=**−16.51** CI[−19.29,−13.87] · cont=**+12.12** CI[7.82,17.12] · best pooled excl. oracle: `always_stay_wide` (cont_cost≈3.03 vs blind restore 12.12).  
Re-run: `…/mm_quoting` exp script · `out/metrics.json`, `out/RISK_REPORT.md`, `EXP_REPORT.md`.

#### strategy_lab desk board
Risk-policy / MM equity sims (friction 2 bps). baseline_maker final_mean≈**−2069.6** bps · Δ vs baseline: `nanex_temp_pull` +2.75 · `hl_thin_size_cap` +2.57 · `kill_ladder_maker` −8.58 · V-restore stubs ≈−2.5. Focus cell 2026-09-08 ETH HL n_events=82. Book honesty: median book Δt ≈**349s** on Phase-4 slice (warehouse snapshot, not ms L2).  
Re-run: `python3 exp_strategy_lab.py --workers 14` · `out/summary.json` · notebook `strategy_lab.ipynb`.

#### paper_harness kill ladder + RISK_ROLLUP
HL ETH shadow maker · days 09-04…10 · **7/7 ok** · gated **173** / fire **139** · mean Δ equity **+295.9** bps · mean Δ fire fills **−478.7** · nullified frac **0.0**. Class: risk-policy shadow ≠ PnL alpha.  
Artifacts: `out/RISK_ROLLUP.md`, per-day `out/2026-09-0*_hyperliquid_ETH/{RISK_REPORT.md,summary.json}`.

### 8. Sibling books (touched today — no invented edges)

| Book | Today status | Notes |
|------|--------------|-------|
| **v_shapes** | 4 Promote / 5 Hold / 2 Kill | MinV risk monitors Promote; feature_reg ridge Hold (IC CI∋0); `out/trade_ideas.json` refreshed |
| **filmonov** | 0 Promote / 13 Hold / 11 Kill | Pass-2 harden; quote-storm / fade / ignition Hold (throttle/monitor) |
| **mn_tuwrv** | 0 Promote | Pass-2.6: sparse RV + noise clocks **Kill**; TSRV first-adj **Hold** |

### Kill list (why)

| Item | Why |
|------|-----|
| **TI-cont-ride** (causal) | mean net ≤0 · CI includes 0 (−2.83 [−7.40,1.56]); causal aux dies at all friction levels |
| **xvenue_lag** (all 5) | net ≈−4.2 after 4bps RT; gross≈0 → pure cost sink; early+late both neg |
| **LR-v-slow-fade** | all holds Kill; 1m −0.93 CI∋0; longer holds more negative |
| **LR-cluster-fade** | anti-edge — fade side loses; isolated-fade nets Kill across holds |
| **always_ride** (edge_lab) | −15.08 — Hold on CI but fails friction bar |
| **mm_confr scorecard tradable** | hit_rate **0.33** on ETH slice |
| **mm_confr vanity IDs** | no sovereign tick RDD / welfare / SEC-IPO |
| **filmonov vanity** | colo / Hibernia / equity quote-rate vanity Kills |
| **mn_tuwrv sparse / noise clocks** | MC + panel Kill sparse_rv_only and noise_dominates_* |

### Still running / incomplete

- **xvenue_lag:** complete Kill (not incomplete) — closed.  
- **mm_confr:** Kraken **futures PF_*** still L2-absent (spot native only). Check `out/native_rerun/` / `out/pass2_native/` if a later worker refreshed gates.  
- **strategy_lab / paper_harness:** equity paths are synthetic touch-maker marks; do not over-read as live fill PnL.

### Suggested next digs

1. Ship **TI-v-fade** + **nest_hard_pause** + **int-halt** as risk/playbook overlays into paper_harness (keep honesty labels).  
2. Drop or quarantine **xvenue_lag** / causal **cont-ride**; don’t spend more sample chasing ~0 gross.  
3. Ship **LR-fire-pause** as long-horizon intensity overlay; widen cont/cluster-ride / ssm-drift until CI excludes 0 or Kill cleanly.  
4. mm_confr: ingest Kraken PF futures L2; within-venue hourly FM with vol/OFI controls.  
5. strategy_lab: prefer collector TOB days before claiming equity Δ vs kill_ladder.
