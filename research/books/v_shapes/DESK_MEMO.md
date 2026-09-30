# Desk memo — V-shapes (Flora & Renò 2020)

**Audience:** crypto MM / SOR / execution / taker / risk / research  
**Source:** Flora & Renò working paper (2020-09-17, SSRN 3554122) → `research/books/v_shapes/`  
**Philosophy:** lenses `risk | info | exec | disc | cont | liq | mm` — V-statistic objects are **not** automatically tradable.  
**Data:** warehouse trades + collector TOB on **HL + Deribit + Kraken** — **no ClickHouse MCP**.  
**Program status:** Widened+hardened + feature-reg + paper-throttle + paper_live shadow — 5 Promote / 10 Hold / 4 Kill · days=20.
**SoT:** [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) · Lib: [`../../lib/vstat.py`](../../lib/vstat.py) · Loaders: [`scripts/_data.py`](scripts/_data.py).
**Living shadow:** [`applications/paper_live/`](applications/paper_live/) — MinV/EGARCH Promote monitors + Kill throttle paper telemetry (`logs/shadow.log`).

---

## 1. Desk jobs × intended outputs (pre-empirics)

| Job | Paper object | Tentative desk label | Status |
|-----|--------------|----------------------|--------|
| **Risk monitor** | Daily MinV vs EGARCH bands | Monitor — fragility / reverting-drift days | Promote monitor (see signal board) |
| **Toxicity / info** | Continuous \(V_t\), \(T^\pm\) around events | Info feature join (VPIN/OFI/markout) | Hold — see signal board |
| **Execution throttle** | Significant MinV + liq deterioration | Exec throttle if falsifiers hold | **Kill** as risk overlay (see §5c) |
| **SOR / x-venue** | HL↔Deribit↔Kraken MinV concordance | Fragmentation / thin-venue concentration | see Promote/Hold rollup |
| **Competing detectors** | vs `crash.vshape_events` / Nanex / SSM | Overlap/PR table — do not merge APIs | pending |

---

## 2. Signal board (Pass 2 + hardening)

| ID | Formula / clock | Monitor | Tradable | Exec throttle | Decision |
|----|-----------------|---------|----------|---------------|----------|
| `risk.v_vs_jump_taxonomy` | Def 1 / Prop 1 framing | yes | no | maybe | **Promote** |
| `risk.egarch_minv_bands` | MinV / EGARCH · UTC-day · hn∈{1,5,30}m | yes | no | maybe | **Promote** |
| `risk.daily_minv_panel` | UTC-day MinV panel + time-split | yes | no | maybe | **Promote** |
| `risk.stress_day_minv` | multi-day stress MinV | yes | no | maybe | **Promote** |
| `risk.xvenue_minv_concord` | — | maybe | no | no | **Hold** — no concordant significant pair in slice |
| `info.v_path_continuous` | — | maybe | no | no | **Hold** — mean_corr_V=0.021 CI=[-0.006,0.048] n=220 (V-only; CI does not clear Promote bar |
| `info.post_trough_ret` | — | maybe | no | no | **Hold** — post300 mean=0.00020 CI=[-0.00129,0.00169] n=17 |
| `liq.spread_around_minv` | — | maybe | no | no | **Hold** — TOB usable rows=14 days=['2026-09-08', '2026-09-15', '2026-09-25', '2026-09-27', |
| `id.auction_loss` | — | maybe | no | no | **Hold** — no crypto sovereign auction analogue |
| `info.v_feature_ridge_calendar` | Causal V-feats → cal 30s/60s/300s Ridge | yes | no | maybe | **Promote** — Monitor only; IC stable, \(R^2\) small (0.3–2.6%); not sized |
| `info.v_feature_ridge_tick` | Causal V-feats → next-20 trades | maybe | no | no | **Hold** — primary trade clock; \(R^2_\mathrm{te}<0\), IC CI includes 0 |
| `info.v_feature_ridge_volume_clock` | Causal V-feats → vol-clock fwd | maybe | no | no | **Hold** — same OOS collapse as tick |
| `info.breach_sign_logistic` | Breach → sign(tick ret) | maybe | no | no | **Hold** — AUC_te≈0.49 |
| `risk.asymptotic_218_360` | — | no | no | no | **Kill** — paper §3.1: too small for realistic DGP + multiple testing; use EGARCH bootstrap |
| `risk.gm_mu_sigma_tradable` | — | no | no | no | **Kill** — Grossman–Miller mu/sigma monitor only — vanity as tradable |
| `info.v_feature_leakage_V_Tp` | Contemporaneous \(V/T^+\) in X | no | no | no | **Kill** — right-kernel look-ahead; diagnostic only |
| `exec.minv_breach_throttle` | MinV τ★ → widen/size/POV paper sim | no | no | yes | **Kill** — OOS adverse mo30 worsens CI>0 (n_breach=5); DD CI includes 0 |
| `exec.minv_throttle_cal_join` | Calendar Ridge deepen on breach | maybe | no | paper | **Hold** — parent Kill; cal deepen does not clear adverse falsifier |
| `exec.minv_throttle_as_alpha` | Throttle PnL as alpha | no | no | no | **Hold** — never sized; Δpnl OOS≈+2.4 bps; y_tick_20 Hold |

**Kill list:** asymptotic 2.18/3.60; GM μ/σ as tradable; live use of contemporaneous \(V/T^+\); MinV-breach exec throttle as risk overlay (adverse-selection falsifier)
**Hold blockers:** risk.xvenue_minv_concord; info.v_path_continuous; info.post_trough_ret; liq.spread_around_minv; info.v_feature_ridge_tick; info.v_feature_ridge_volume_clock; info.breach_sign_logistic; exec.minv_throttle_cal_join; exec.minv_throttle_as_alpha

---

## 3. Venue completeness (locked)

| Venue | Role | Symbol examples | Notes |
|-------|------|-----------------|-------|
| Hyperliquid | DEX anchor | `ETH`, `BTC` (flat ids ≤2026-09-10) | UTC clip required |
| Deribit | CEX perps | `ETH-PERPETUAL`, `BTC-PERPETUAL` | mark + trade + L2→TOB |
| Kraken | CEX futures | `PF_ETHUSD`, `PF_XBTUSD` | normalize from `ETH` / `ETH/USD` in `_data.py` |

Incomplete UTC days → flag in EXP_REPORT; do not Promote on thin tails alone.

---

## 4. Next gate (post-widen)

1. Sample days in rollup: `['2026-09-04', '2026-09-05', '2026-09-06', '2026-09-07', '2026-09-08', '2026-09-09', '2026-09-10', '2026-09-14', '2026-09-15', '2026-09-16', '2026-09-17', '2026-09-18', '2026-09-19', '2026-09-20', '2026-09-21', '2026-09-22', '2026-09-25', '2026-09-26', '2026-09-27', '2026-09-30']`.
2. TOB reality: usable=14 days=['2026-09-08', '2026-09-15', '2026-09-25', '2026-09-27', '2026-09-29', '2026-09-30']; Kraken warehouse L2 empty; collector only 2026-09-29/30; Deribit L2 multi-day when present — no fake TOB.
3. Keep EGARCH bootstrap CIs; asymptotic 2.18/3.60 stay **Kill**.
4. `id.auction_loss` stays Hold (identification).
5. Trade ideas: see §5 — Monitor / Exec throttle only until post-trough / xvenue Promotes.
6. Feature-reg (§5b): primary = trade-time next-20 (**Hold**); calendar Ridge **Promote as Monitor only**; no sized alpha.
7. Paper throttle (§5c): MinV-breach exec throttle **Kill** as risk overlay (adverse mo CI>0); Hold as alpha; cal join Hold/paper.

## 5. Trade ideas / strategies (desk-honest)

Memo-grade board in [`notebooks/trade_ideas.ipynb`](notebooks/trade_ideas.ipynb) (loads rollup + daily MinV / continuous-V / xvenue / liq JSON + figures). Labels: **Monitor** / **Exec throttle** / **paper-only**. Sized tradable **only** if a Promote (or explicit paper-only Hold) survives falsifiers. **Do not soft-Promote Holds.** No alpha cosplay on Kill objects.

| Idea | Label | Depends | Gate | Falsifier / evidence |
|------|-------|---------|------|----------------------|
| `ti.risk_monitor_minv_breach` MinV breach → widen / cut size / pause takes | **Monitor** | `risk.egarch_minv_bands`, `risk.v_vs_jump_taxonomy`, `risk.daily_minv_panel` (+ stress) | all **Promote** | time-split early/late sig=11/6; hn_means≈{1: −18.9, 5: −41.5, 30: −105.8}; figs `out/daily_minv/fig_minv_panel.png`, `fig_hn_fragility.png` |
| `ti.exec_throttle_avoid_chase` Avoid chase through trough; delay POV | **Exec throttle** (paper) | `info.v_path_continuous`, `risk.egarch_minv_bands` | v_path **Hold** / bands Promote | mean_corr_V≈0.021 CI≈[−0.006,0.048]; `out/v_statistic/continuous_v_{eth,btc}.json` |
| `ti.mean_reversion_fade` Post-trough fade | **Monitor** (paper / not sized) | `info.post_trough_ret` | **Hold** | post300 mean≈0.00020 CI≈[−0.00129,0.00169] n=17; `fig_post_trough.png` |
| `ti.xvenue_sor_caution` Thin-venue SOR caution during V | **Exec throttle** (Hold) | `risk.xvenue_minv_concord` | **Hold** | concordant_pair_in_slice=False; `out/xvenue_concord/fig_concord.png` |
| `ti.liq_spread_widen` Spread/depth around MinV as secondary flag | **Monitor** (Hold) | `liq.spread_around_minv` | **Hold** | TOB usable≈14 days; Δspread CI includes 0; no fake TOB; `fig_spread_around.png` |
| `ti.v_feature_cal_monitor` Causal V Ridge score on calendar clock | **Monitor** | `info.v_feature_ridge_calendar` | **Promote** | cal30/60/300 IC≈0.068/0.096/0.187, \(R^2\)≈0.003/0.006/0.026, sign-stable; `out/feature_reg/` |
| `ti.v_feature_ridge_monitor` Trade-clock Ridge IC watch | **Monitor** (Hold) | `info.v_feature_ridge_tick` | **Hold** | \(R^2_\mathrm{te}\)≈−1.25 IC≈−0.088 CI includes 0; intensity-dominated |
| `ti.v_feature_throttle_join` Calendar Ridge → paper avoid-chase score | **Exec throttle** (paper) | calendar Promote + `info.v_path_continuous` | calendar **Promote** / v_path **Hold** | live POV still paper until v_path clears |
| `ti.paper_minv_exec_throttle` Paper harness MinV→throttle vs always-on | **Monitor** (killed overlay) | `exec.minv_breach_throttle` | **Kill** | OOS breach Δadv_mo30=+0.010 CI=[0.004,0.015] n=5; Δdd CI includes 0; `out/paper_throttle/` |
| `ti.paper_cal_throttle_join` Cal Ridge deepen on breach (paper) | **Exec throttle** (paper) | calendar Promote + cal join | cal join **Hold** | parent Kill; paper-only weight |
| `ti.paper_live_shadow` Living warehouse shadow telemetry | **Monitor** (shadow) | MinV Promote + Kill throttle | monitors **Promote** / throttle **Kill** | [`applications/paper_live/`](applications/paper_live/) · `logs/shadow.log` — hypo only |

### 5b. Feature-reg / next ideas (tradable vs monitor)

| Target / clock | Status | Desk label |
|----------------|--------|------------|
| `y_tick_20` trade-time (primary) | **Hold** | Monitor-only IC watch — **not tradable** |
| `y_cal_{30,60,300}s` calendar | **Promote** | **Monitor** info feature — not sized (\(R^2\)≪1) |
| `y_vol` volume-clock | **Hold** | Monitor-only |
| Breach→sign logistic | **Hold** | Coin-flip AUC |
| \(V_\tau/T^+_\tau\) leakage set | **Kill** | Never live |

Paths: [`applications/feature_reg/`](applications/feature_reg/) · [`out/feature_reg/summary.json`](out/feature_reg/summary.json) · notebook [`applications/feature_reg/feature_reg.ipynb`](applications/feature_reg/feature_reg.ipynb).

### 5c. Paper exec-throttle harness

Harness: [`applications/paper_throttle/`](applications/paper_throttle/) · script [`scripts/exp_paper_throttle.py`](scripts/exp_paper_throttle.py) · artifacts [`out/paper_throttle/`](out/paper_throttle/) · memo [`applications/paper_throttle/paper_throttle.ipynb`](applications/paper_throttle/paper_throttle.ipynb).

### 5d. Living paper_live SHADOW (monitor telemetry)

Package: [`applications/paper_live/`](applications/paper_live/) · runner `run_paper_live.py` · log [`applications/paper_live/logs/shadow.log`](applications/paper_live/logs/shadow.log) · events `out/events.jsonl` · board [`applications/paper_live/shadow_board.ipynb`](applications/paper_live/shadow_board.ipynb).

Mirrors cross_miniflash `v_fade_shadow` cadence (warehouse latest-complete-day poll). Logs **Promote** MinV/EGARCH breaches + optional calendar Ridge score + **hypothetical** Kill throttle state. **Does not** soft-Promote `exec.minv_breach_throttle`. `live_orders=false`.

```bash
cd research/books/v_shapes/applications/paper_live
python3 run_paper_live.py --poll --interval 120
tail -f logs/shadow.log
```

| Slice | Δmax_dd (throttle−base) | Δadverse mo30 | Δpnl | n |
|-------|-------------------------|---------------|------|---|
| OOS all | +2.38 CI≈[−8.3,+7.3] | +0.0014 | +2.38 | 36 |
| OOS breach | +17.1 CI≈[−76,+70] | **+0.010 CI≈[0.004,0.015]** | +17.1 | 5 |
| OOS calm | 0 | 0 | 0 | 31 |

**Verdict:** point-estimate DD softens on breach days, but **adverse selection worsens with CI excluding 0** → **Kill** `exec.minv_breach_throttle` as risk overlay. **Hold** as alpha. Calendar deepen **Hold**. Monitor stack (EGARCH/MinV) unchanged Promote.

### Per-idea (thesis → trigger → action → falsifier)

**ti.risk_monitor_minv_breach** — **Monitor** (Promote stack)

- **Thesis:** UTC-day MinV vs EGARCH 5% is a fragility / reverting-drift **monitor**, not PnL.
- **Trigger:** \(\mathrm{MinV}_{d,v}(h_n) < q_{0.05}^{\mathrm{EGARCH}}(h_n)\) for \(h_n\in\{1,5,30\}\)m on home venue (EGARCH bootstrap — not asymptotic 2.18/3.60).
- **Action knobs:** `quote_widen_bps` +2…+8; `size_mult` 0.25–0.50; pause aggressive takes for \(1\times h_n\).
- **Size:** N/A — Monitor only. Evidence: daily panel + stress days (ETH 2026-09-20, BTC 2026-09-30).

**ti.exec_throttle_avoid_chase** — **Exec throttle** (paper-only while Hold)

- **Thesis:** Chasing mid through \(\tau^\star\) is an execution leak; throttle POV / participation until mid recovers past \(\tau^\star+h_n/2\).
- **Trigger:** sig MinV day ∧ live path in \([\tau^\star-h_n,\ \tau^\star+h_n/2]\). Continuity join Hold.
- **Action knobs (paper):** `pov_pause`, `participation_mult` 0–0.3, `chase_disable`.
- **Size:** Paper-only. Falsifier: V→fwdret CI does not clear 0 / thin continuous-V events.

**ti.mean_reversion_fade** — **Monitor** (failed sized fade)

- **Thesis:** Only candidate that *looks* like alpha; **not** sized until post-trough CI excludes 0 on early∧late.
- **Trigger (blocked):** fade post-\(\tau^\star\) iff \(\mathrm{CI}(\bar r_{300\mathrm{s}})\) excludes 0 after time-split/bootstrap.
- **Size:** Not sized — post300 CI includes 0 (n=17). Keep as CI monitor only.

**ti.xvenue_sor_caution** — **Exec throttle** (Hold)

- **Thesis:** Concordant troughs ⇒ cut thin-venue child size during V windows (fragmentation caution, not lead-lag alpha).
- **Trigger (blocked):** pairwise \(|\Delta\tau^\star|\le h_n\) among sig venues.
- **Size:** Not sized — no concordant significant pair in slice.

**ti.liq_spread_widen** — **Monitor** (Hold / secondary)

- **Thesis:** TOB spread widening into trough reinforces quote widen; never a standalone Promote without honest TOB.
- **Hard ceiling:** Kraken warehouse L2 empty; collector TOB only 2026-09-29/30; Deribit L2 multi-day when present; refuse trade_synth.
- **Size:** N/A — Monitor; Δspread not Promote-grade.

**ti.v_feature_cal_monitor** — **Monitor** (Promote calendar gate)

- **Thesis:** Causal \(T^-\) / lagged-\(V\) / running-MinV Ridge score predicts calendar-horizon mid returns with stable OOS IC — fragility / info **monitor**, not PnL.
- **Trigger:** elevated |score| from causal feature Ridge at \(h\in\{30,60,300\}\)s on home venue (5s grid, 30s decisions).
- **Action knobs:** reinforce `quote_widen_bps` / cut `size_mult` when score extreme with MinV breach; never standalone size.
- **Size:** N/A — Monitor. \(R^2\) 0.3–2.6% — do not size as alpha.

**ti.v_feature_ridge_monitor** — **Monitor** (Hold primary tick)

- **Thesis:** Trade-time next-20 was the honest primary; OOS failed (intensity leak / regime). Keep IC watch only.
- **Size:** Not sized. Do not soft-Promote.

**ti.v_feature_throttle_join** — **Exec throttle** (paper)

- **Thesis:** Join calendar Ridge score into avoid-chase POV throttle as a paper score; live params still blocked by `info.v_path_continuous` Hold.
- **Size:** Paper-only.

**ti.paper_minv_exec_throttle** — **Monitor** (Kill as risk overlay)

- **Thesis:** Post-τ★ widen/cut-size/POV on EGARCH-sig MinV days should cut drawdown / adverse markout vs always-on maker.
- **Trigger:** Promote MinV `sig_5` at τ★ for duration \(h_n\); knobs size_mult=0.35, widen=+5bps, pov=0.20.
- **Falsifier (hit):** OOS breach Δadverse_mo30=+0.010 CI=[0.004,0.015] n=5 — adverse selection **worsens**; Δmax_dd point-helps but CI includes 0.
- **Size:** Not deployed. MinV remains **Monitor**; do not soft-Promote.

**ti.paper_cal_throttle_join** — **Exec throttle** (paper / Hold)

- **Thesis:** Calendar Ridge Monitor deepens throttle when \|score\|≥train q90.
- **Size:** Paper-only; parent Kill blocks Promote.

### What we will NOT trade

- `risk.asymptotic_218_360` — **Kill**; paper §3.1 bands too small under realistic DGP; use EGARCH bootstrap. No trade idea.
- `risk.gm_mu_sigma_tradable` — **Kill**; Grossman–Miller μ/σ monitor vanity as tradable. No trade idea.
- `info.v_feature_leakage_V_Tp` — **Kill**; contemporaneous \(V/T^+\) look-ahead. No trade idea.
- `exec.minv_breach_throttle` — **Kill** as risk overlay; OOS adverse markout CI>0 on breach days. Keep MinV as **Monitor** only — do not deploy widen/size/POV from breach alone.
- Sized mean-reversion fade, live POV throttle as alpha, thin-venue SOR cut, TOB-only Promotes, and trade-clock Ridge alpha — **blocked** by Holds above. Do not soft-Promote.

### Next experiments (Holds only)

1. `info.post_trough_ret` — widen complete sig sample; require post300 CI excludes 0 on early∧late before any fade size.
2. `info.v_path_continuous` — more continuous-V events; corr(V, fwdret) CIs at 5/30/60s before live throttle params.
3. `risk.xvenue_minv_concord` — multi-venue complete days; need ≥1 replicated concordant sig pair.
4. `liq.spread_around_minv` — Deribit L2 + collector TOB only; Δspread CI with honest source labels.
5. `id.auction_loss` — stays identification Hold; no invented auction proxy trade.
6. `info.v_feature_ridge_tick` — ablate intensity; venue FE; shorter N; require IC CI excludes 0 before any tick-clock Promote.
7. `ti.v_feature_throttle_join` / paper throttle — redesign trigger (running breach / recovery confirm) after Kill of naïve post-τ★ size cut; need adverse mo not worsen.

