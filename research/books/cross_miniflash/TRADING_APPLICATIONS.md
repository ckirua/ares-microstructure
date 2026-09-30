# Trading / modelling / strategy applications — Tee/Ting mini-flash

**Companion:** [`SIGNAL_CATALOG.md`](SIGNAL_CATALOG.md) (per-signal depth) · Desk: [`DESK_MEMO.md`](DESK_MEMO.md) · Money map: [`applications/HOW_WE_TRADE.md`](applications/HOW_WE_TRADE.md)  
**Slice honesty:** Phase 4 → **10 Promote / 13 Hold / 3 Kill**; **0 tradable** Promotes. Everything below is **monitor → rule sketch → backtest**, not a greenlit edge.  
**Venues:** Hyperliquid (thin USD, crash-dense) · Deribit · Kraken (largest USD share).  
**Primary gate:** SSM events with \(\lvert\Delta P\rvert\ge 10\,\mathrm{bps}\), \(i_c\ge 5\) (n=275 from 3668 raw).

Confidence labels: **high** = ready to wire as monitor/gate with known failure modes · **med** = rule sketch needs paper trade / simple backtest · **low** = research feature only.

---

## 1. Risk / kill-switches

### 1.1 Severity-gated SSM intensity (Promote-ready)

**Objects:** `risk.ssm_severity_gate_10bps` + `risk.ssm_zstar_scan_table` + `vol.sigma_m_noise_floor_1bp`

| Layer | Rule sketch | Conf |
|-------|-------------|------|
| Infra | Enforce σ_m ≥ 1 bp floor before any SSM flag | **high** |
| Count | Risk dashboards: **gated** event rate only (never raw z*=6) | **high** |
| Ladder | Map z* bands + gate → actions: observe → widen → size-cap → halt aggressive | **high** |
| Escalate | Nanex∩SSM (`info.nanex_subset_of_ssm`, prec≈0.90) = high-precision burst escalate | **high** |

**Falsifiers already known:** ungated intensity median ΔP≈0; σ_m floor off floods counts.

**Ops note:** Publish ablation ladder (3668→589→275→56) on the same panel so intensity is never a single magic number.

### 1.2 Thin-venue excess kill / size-cap (Promote monitor → med rule)

**Objects:** `frag.thin_venue_crash_excess` + `frag.crash_venue_share`

| Rule sketch | Conf |
|-------------|------|
| When HL thin excess (crash−vol share) elevated **and** gated SSM intensity on HL rises → **cap HL inventory / aggressive takes** | **med** |
| Always show HL crash share (~0.83 @10bps) vs vol share (~4%) on SOR risk strip | **high** |

**Do not:** assume crashes co-fire across venues (`frag.xvenue_crash_concord` placebo p≈0.58 → Hold). Kill-switches should be **venue-local**.

### 1.3 Cross-book honesty gates (mmip)

| Object | Use | Conf |
|--------|-----|------|
| mmip `frag.crossed_nbbo` | Hard no-take until fee+latency model clears | **high** (mmip Promote; crashwin Hold here — TOB gap) |
| mmip `lsor.latency_depth_haircut` | Never count unvalidated far-venue depth in crash regimes | **high** |

---

## 2. Execution / SOR

### 2.1 Capacity & concentration monitors (Promote)

**Objects:** `frag.volume_herfindahl_3venue` (\(H^v\approx 0.48\)) · `frag.fei_volume_3venue` (FEI≈0.75)

| Use | Conf |
|-----|------|
| Rolling \(H^v\) / FEI on 3-venue USD shares = capacity regime | **high** |
| FEI drop / \(H^v\) rise → prefer thick legs (Kraken/Deribit on this slice), shrink child size on thin leg | **med** |
| TCA: bucket slippage by FEI / \(H^v\) quartile | **med** |

Cross-link: mmip `vol.fei_hourly` (temporal concentration) — pair venue FEI with hour FEI for “where × when” capacity.

### 2.2 Avoid thin venues in crash regimes (Promote → med)

| Use | Conf |
|-----|------|
| In windows with elevated gated SSM on HL, SOR: **deprioritize HL for aggressive / large takes**; keep HL for make-only or clipped size | **med** |
| Venue share map for routing priors (not for arb) | **high** |

### 2.3 Exec throttles still Hold

| Object | Blocker | Next |
|--------|---------|------|
| `exec.outside_tob_wh_l2` | outside_rate 15–79%, sparse L2 | Dense collector TOB |
| `exec.tape_markout_post_crash` | tape mo@5s≈−7bps; mid preferred | Mid/mark markout + V-class stratify |
| `frag.crossed_nbbo_crashwin` | n_available=0 on slice | Wire mmip crossed gate when TOB present |

Until then: use **gated intensity + thin excess** as soft throttle proxies (**med**), not outside-TOB.

---

## 3. Market making

### 3.1 Widen / pull on gated crash intensity (Promote → med)

| Trigger | Action sketch | Conf |
|---------|---------------|------|
| Rising gated SSM intensity (10bps/ic5) on quoting venue | Widen quotes; cut size; skew inventory toward flat | **med** |
| Nanex∩SSM fire | Temporary pull / protect; faster than soft widen | **med** |
| Thin excess HL elevated | HL quotes: extra buffer vs vol-share-implied risk | **med** |

Cross-link: mmip `spread.vol_link` (spread↑ with \(\lvert\Delta\log M\rvert\)) — combine vol widen with crash-intensity widen.

### 3.2 V-recovery vs continuation (Promote MM playbook — med)

**Object:** `info.crash_v_vs_continuation` (share_V≈0.77 @5s) · sim [`applications/mm_quoting/`](applications/mm_quoting/)

| Class | Quoting sketch | Conf |
|-------|----------------|------|
| **V (hole)** | After recovery confirm @1–2s, restore size; do **not** fade until mid markout clears | **med** playbook / fade **low** |
| **Continuation (news)** | Stay wide (0.25×); do not blind-restore; inventory lean with move | **med** |

**Sim verdict:** **Promote (med)** MM playbook — V mo@5s ≈−16.5 bps vs cont ≈+12.1; `always_stay_wide` / `confirm_v_restore` / `cont_protect` beat `always_restore` on continuation adverse cost both cohorts. Not tradable alpha.

Resilience still Hold: `exec.tape_markout_post_crash` (mid_frac=0), `risk.duration_post_markout`. Cross-link mmip `book.resilience`, empirical_mm `mm.book_resilience_lo`.

### 3.3 What not to do

- Raw z*=6 or ungated counts as MM state (**Kill** / Hold).
- Plain log-notional → severity for size budgets (**Kill** `xsec.size_reduces_severity`).
- Assume multi-venue crash sync for hedge timing (**Hold** concordance).

---

## 4. Alpha / modelling features

Honesty: **no Promote cleared as tradable**. Features below are for **regime / risk / ML state**, not standalone PnL claims.

| Feature | Source | Role | Conf |
|---------|--------|------|------|
| Gated crash intensity (count / notional-weighted) | severity_gate | Regime flag | **high** |
| z* path / band | zstar_scan + continuous z | Graded stress | **high** monitor / **low** alpha |
| V vs continuation label | recovery@5s | Event class | **high** label / **low** alpha |
| Crash venue one-hot + thin excess | frag Promotes | Venue-risk state | **high** |
| \(H^v\), FEI | frag Promotes | Capacity state | **high** |
| Nanex∩SSM burst bit | nanex_subset | High-precision burst | **med** |
| Day-level crash occurrence score | feature_models Soft Promote | Regime / risk feature | **med** soft (AUC_te≈0.635); severity \|ΔP\| **Hold** |
| VPIN × logN interact | **Promote (med)** feature | Toxicity×size | **med** (boot CI excludes 0; not live sizing) |
| KF innovation z continuous | Hold innov | Research state | **low** (\(\lvert\mathrm{corr}\rvert\approx0.04\)) |
| Ex-ante Amihud | Hold | Severity prior | **low** (n=20) |
| empirical_mm `cont.vpin` | sibling Promote | Toxicity level | **med** as co-feature |
| empirical_mm `disc.jump_sign_concord` | sibling | Cross-venue jump sign (≠ crash Jaccard) | **med** |
| mmip `epps.xvenue_corr` | sibling | Hedge horizon (day Epps) | **med** |

**Kill as features for severity prediction:** plain size/MCap (`xsec.size_reduces_severity`). Severity \|ΔP\| ridge still OOS-useless — occurrence only Soft Promote.

---

## 5. Proposed next experiments (ranked)

Priority = (desk value) × (feasibility on current warehouse) × (path to Promote or simple rule backtest).

| Rank | Experiment | Goal | Inputs | Success bar | Effort |
|-----:|------------|------|--------|-------------|--------|
| **1** | **Backtest: halt / clip aggressive takes when gated SSM intensity > X on HL** | Convert thin-excess + severity gate → exec rule | Gated events, HL fills/taker tape, X grid from z* menu | Reduces adverse markout in crash windows without killing normal fills; time-split stable | **S** (rule on existing events) |
| **2** | **MM paper: widen/size-cut schedule keyed to gated intensity ladder** | Quoting playbook | Quote logs or synthetic AS quotes × intensity bands | Spread/size respond; inventory drawdown in gated windows ↓ | **S–M** |
| **3** | **Dense TOB pass: outside-TOB + crossed NBBO in crash ±pad** | Unblock exec Holds; link mmip crossed gate | Collector TOB HL+DB+KR on same days | outside_rate explained; n_crossed>0; crashwin rates with CI | **M** (data) |
| **4** | **Mid/mark markout stratified by V vs continuation** | Promote tape_markout or Kill fade fantasy | Mid series + recovery labels | mo CI by class; V fade only if CI supports | **S–M** |
| **5** | **Widen panel: VPIN×size + ex-ante Amihud OOS** | Hold → Promote or Kill interact | +weeks, +SOL if 3-venue complete; `cont.vpin`, `liq.amihud_1m` | Interact / Amihud β sign-stable early/late + boot CI | **M** |
| **6** | **Volume-clock duration ↔ markout** | Fix duration Hold (median Δt=0) | Trade-count / volume Δt | \(\lvert\mathrm{Spearman}\rvert\) stable OOS | **S** |
| **7** | **Concordance as negative result product** | Document venue-idiosyncratic holes for hedge policy | Existing Jaccard + placebo | Desk policy: “do not wait for x-venue confirm” | **S** (memo) |
| **8** | **Joint diurnal panel** (mc_garch_sj × mmip curve) | Schedule prior Promote or permanent soft-prior | Same UTC hours multi-book | Peak hour CI overlap or documented mismatch | **M** |
| **9** | **FEI/\(H^v\) → SOR child-size schedule** | Capacity → action | Rolling frag + POV/child sims (mmip `impact.algo_pov_sim`) | Slippage ↓ in high-H windows | **M** |
| **10** | **Taxonomy → incident auto-labeler** | Ops | Existing defs | Labels match desk postmortems | **S** |

**Explicit non-goals (Kill):** Nanex 80bps intensity; raw ungated SSM counts; plain notional→severity OLS.

---

## 5b. Application backtest results (unified board)

**Built:** [`applications/`](applications/) · board [`applications/out/applications_board.json`](applications/out/applications_board.json) · index [`applications/README.md`](applications/README.md) · panel n_gated=**275**.  
**Edge lab (non-MM top-3):** [`applications/edge_lab/`](applications/edge_lab/) · ideas [`TRADE_IDEAS.md`](applications/TRADE_IDEAS.md) · [`EDGE_LAB.md`](applications/edge_lab/EDGE_LAB.md) · [`EXP_REPORT.md`](applications/edge_lab/out/EXP_REPORT.md) — **MM is one of many**; do not deepen quoting here.  
**Tick/OB equity:** [`applications/strategy_lab/`](applications/strategy_lab/) · desk board [`strategy_lab.ipynb`](applications/strategy_lab/strategy_lab.ipynb) · figs [`out/figs/`](applications/strategy_lab/out/figs/) · [`STRATEGY_LAB.md`](applications/strategy_lab/STRATEGY_LAB.md).  
**Paper harness (HL ETH day):** [`applications/paper_harness/`](applications/paper_harness/) · `python3 run_paper_day.py --day 2026-09-04` · [`RISK_REPORT.md`](applications/paper_harness/out/2026-09-04_hyperliquid_ETH/RISK_REPORT.md).  
Methodology: early/late day split, bootstrap CI, friction haircut where applicable, **no fantasy fills**. Desk SoT: [`DESK_MEMO.md`](DESK_MEMO.md) §7 · Promote IDs: [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md).

### Edge lab (non-MM · TRADE_IDEAS top-3)

| id | Package | Headline | Class / readiness |
|----|---------|----------|-------------------|
| **TI-v-fade** | [`edge_lab/`](applications/edge_lab/) | causal fade-V net ≈**+11.6 bps** after 4bps RT; V mo≈−16.5; early/late stable | **taker sim · Promote (research)** — mid_mo null, not live alpha |
| **TI-cont-ride** | same | causal ride-cont net ≈**−2.8 bps** CI includes/≤0 | **taker sim · Kill** (oracle@5s still green — look-ahead) |
| **TI-int-halt** | same | Δ\|mo\| fire−obs ≈**+6.54 bps** CI clears friction; time-split OK | **risk-policy · Promote** (aggressor clip) |
| **TI-nanex-nest** | same | Δ\|mo\| nest−non ≈**+5.11 bps**; n_nest=66; nest join from event_panel | **risk-policy · Promote** (escalate pause) |

### Risk / SOR (track 517aeba3)

| Exp | Package | Headline | Class / readiness |
|-----|---------|----------|-------------------|
| **1 Kill-ladder** | [`kill_ladder/`](applications/kill_ladder/) | Δ\|mo\|@5s fire−observe **+6.54 bps** CI **[1.76, 10.40]**; tiers 45/105/37/88; friction cleared; time-split stable | **risk-policy · Promote-as-risk-policy** |
| **2 Nanex∩SSM** | [`nanex_burst/`](applications/nanex_burst/) | n_nested=67; prec=**0.905**; Δ\|ΔP\| **+0.113%** CI **[0.075, 0.152]**; Δ\|mo\| **+5.11 bps** | **risk-policy · Promote-as-risk-policy** (+ tag) |
| **3 HL thin SOR** | [`hl_thin_sor/`](applications/hl_thin_sor/) | HL crash share **0.829**; thin excess **0.62** CI **[0.44, 0.77]**; size-cap Δ\|mo\| CI includes 0 | **monitor · strip yes / hard size-cap Hold** |
| **4 H^v/FEI sizing** | [`hv_fei_capacity/`](applications/hv_fei_capacity/) | Spearman unstable; high-H qty Δ **−0.34** CI clears; exposure CI does not; π-VWAP invariant | **monitor · dashboard / schedule Hold** |

### MM / features (track 56e6eb83)

| Exp | Package | Headline | Class / readiness |
|-----|---------|----------|-------------------|
| **5 V-restore quoting** | [`mm_quoting/`](applications/mm_quoting/) | V mo@5s≈**−16.5** / cont≈**+12.1**; stay-wide & confirm-V beat blind restore on cont cost both cohorts | **MM playbook · Promote (med)** |
| **6 VPIN×size** | [`feature_models/`](applications/feature_models/) | interact boot CI **[−0.137, −0.032]** excludes 0; OOS t stable | **feature · Promote (med)** |
| **7 Occurrence regime** | [`feature_models/`](applications/feature_models/) | day-level AUC_te≈**0.635**; severity \|ΔP\| OOS R²\<0 | **feature · Soft Promote** (occurrence only) |
| **8 Tape markout** | [`feature_models/`](applications/feature_models/) | mid_frac=0; mo@5s≈−11 bps; class sep OK | **feature · Hold** |
| **9 Duration↔markout** | [`feature_models/`](applications/feature_models/) | median Δt=0; OOS \|ρ\| below bar | **feature · Hold** |
| **10 Expanded lab** | [`expanded_lab/`](applications/expanded_lab/) | core+extend n=310 · SOL n=43; ladder+confirm best on risk scoreboard; Nanex prec≈0.90; dense TOB ops | **risk/MM expand · Promotes below** |

**Ladder honesty:** absolute z∈{8,10,12} collapses on gated crypto tape. Use within-gated percentiles (p25/p50/p75 ≈ 12.5/15.9/20.4) + intensity + Nanex nest.

**Promote-as-risk-policy:** kill-ladder · Nanex∩SSM nested pull — **robust on core+extend** (n=310, Δ|mo|≈+8.7 bps CI clears friction).  
**Promote MM playbook (med):** V-confirm restore / stay-wide on cont · **expanded best-risk = `ladder_plus_confirm_before_restore`** (friction-stable).  
**Promote feature (med):** VPIN×size; Soft Promote occurrence (day-level; expanded ex-ante feats still Hold on Brier).  
**Promote (ops):** denser HL collector TOB marking on 2026-09-29/30 (median Δt≈0.55s vs warehouse ~5s+).  
**Monitor / Hold live rule:** HL thin strip · H^v/FEI dashboard · **SOL kill-ladder Hold (promising)** n=43 DB+KR.  
**Expanded lab:** [`applications/expanded_lab/`](applications/expanded_lab/) · [`EXP_REPORT.md`](applications/expanded_lab/EXP_REPORT.md) · figs [`out/figs/`](applications/expanded_lab/out/figs/).

---

## 6. Readiness snapshot (strategy ideas)

| # | Idea | Class | Readiness | Primary signals |
|---|------|-------|-----------|-----------------|
| 1 | Gated SSM kill-ladder (observe→widen→halt) | risk-policy | **Promote-as-risk-policy** | severity_gate, zstar_scan, σ_m floor |
| 2 | Nanex∩SSM burst escalate / nested pull | risk-policy | **Promote-as-risk-policy** | nanex_subset |
| 3 | HL thin-excess SOR / size-cap | monitor | **High** strip / **Hold** hard cap | thin_excess, crash_venue_share |
| 4 | \(H^v\)/FEI capacity child sizing | monitor | **High** dashboard / **Hold** schedule | herfindahl, fei_volume |
| 5 | V vs continuation quoting restore | MM playbook | **Promote (med)** | crash_v_vs_continuation |
| 5b | Ladder + confirm-before-restore (combined) | MM playbook | **Promote (med)** — best on risk scoreboard | kill_ladder ∩ V-confirm |
| 6 | VPIN×logN severity interact | feature | **Promote (med)** | vpin_x_size_severity |
| 7 | Day-level crash occurrence score | feature | **Soft Promote** | intensity, H^v, hour, VPIN (ex-ante) |
| 8 | Expanded panel robustness (Sep1–10 + SOL DB/KR) | risk-policy | **Promote** kill-ladder/Nanex on extend · SOL **Hold** | expanded_lab |

Detail: [`SIGNAL_CATALOG.md`](SIGNAL_CATALOG.md) · board: [`DESK_MEMO.md`](DESK_MEMO.md) §7 · packages: [`applications/README.md`](applications/README.md) · expand: [`applications/expanded_lab/`](applications/expanded_lab/).
