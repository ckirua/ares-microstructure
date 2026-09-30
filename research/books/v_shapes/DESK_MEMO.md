# Desk memo — V-shapes (Flora & Renò 2020)

**Audience:** crypto MM / SOR / execution / taker / risk / research  
**Source:** Flora & Renò working paper (2020-09-17, SSRN 3554122) → `research/books/v_shapes/`  
**Philosophy:** lenses `risk | info | exec | disc | cont | liq | mm` — V-statistic objects are **not** automatically tradable.  
**Data:** warehouse trades + collector TOB on **HL + Deribit + Kraken** — **no ClickHouse MCP**.  
**Program status:** Widened+hardened — 4 Promote / 5 Hold / 2 Kill · days=20.
**SoT:** [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) · Lib: [`../../lib/vstat.py`](../../lib/vstat.py) · Loaders: [`scripts/_data.py`](scripts/_data.py).

---

## 1. Desk jobs × intended outputs (pre-empirics)

| Job | Paper object | Tentative desk label | Status |
|-----|--------------|----------------------|--------|
| **Risk monitor** | Daily MinV vs EGARCH bands | Monitor — fragility / reverting-drift days | Promote monitor (see signal board) |
| **Toxicity / info** | Continuous \(V_t\), \(T^\pm\) around events | Info feature join (VPIN/OFI/markout) | Hold — see signal board |
| **Execution throttle** | Significant MinV + liq deterioration | Exec throttle if falsifiers hold | pending |
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
| `risk.asymptotic_218_360` | — | no | no | no | **Kill** — paper §3.1: too small for realistic DGP + multiple testing; use EGARCH bootstrap |
| `risk.gm_mu_sigma_tradable` | — | no | no | no | **Kill** — Grossman–Miller mu/sigma monitor only — vanity as tradable |

**Kill list:** asymptotic 2.18/3.60; GM μ/σ as tradable
**Hold blockers:** risk.xvenue_minv_concord; info.v_path_continuous; info.post_trough_ret; liq.spread_around_minv

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

## 5. Trade ideas / strategies (desk-honest)

Memo-grade board in [`notebooks/trade_ideas.ipynb`](notebooks/trade_ideas.ipynb) (loads rollup + daily MinV / continuous-V / xvenue / liq JSON + figures). Labels: **Monitor** / **Exec throttle** / **paper-only**. Sized tradable **only** if a Promote (or explicit paper-only Hold) survives falsifiers. **Do not soft-Promote Holds.** No alpha cosplay on Kill objects.

| Idea | Label | Depends | Gate | Falsifier / evidence |
|------|-------|---------|------|----------------------|
| `ti.risk_monitor_minv_breach` MinV breach → widen / cut size / pause takes | **Monitor** | `risk.egarch_minv_bands`, `risk.v_vs_jump_taxonomy`, `risk.daily_minv_panel` (+ stress) | all **Promote** | time-split early/late sig=11/6; hn_means≈{1: −18.9, 5: −41.5, 30: −105.8}; figs `out/daily_minv/fig_minv_panel.png`, `fig_hn_fragility.png` |
| `ti.exec_throttle_avoid_chase` Avoid chase through trough; delay POV | **Exec throttle** (paper) | `info.v_path_continuous`, `risk.egarch_minv_bands` | v_path **Hold** / bands Promote | mean_corr_V≈0.021 CI≈[−0.006,0.048]; `out/v_statistic/continuous_v_{eth,btc}.json` |
| `ti.mean_reversion_fade` Post-trough fade | **Monitor** (paper / not sized) | `info.post_trough_ret` | **Hold** | post300 mean≈0.00020 CI≈[−0.00129,0.00169] n=17; `fig_post_trough.png` |
| `ti.xvenue_sor_caution` Thin-venue SOR caution during V | **Exec throttle** (Hold) | `risk.xvenue_minv_concord` | **Hold** | concordant_pair_in_slice=False; `out/xvenue_concord/fig_concord.png` |
| `ti.liq_spread_widen` Spread/depth around MinV as secondary flag | **Monitor** (Hold) | `liq.spread_around_minv` | **Hold** | TOB usable≈14 days; Δspread CI includes 0; no fake TOB; `fig_spread_around.png` |

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

### What we will NOT trade

- `risk.asymptotic_218_360` — **Kill**; paper §3.1 bands too small under realistic DGP; use EGARCH bootstrap. No trade idea.
- `risk.gm_mu_sigma_tradable` — **Kill**; Grossman–Miller μ/σ monitor vanity as tradable. No trade idea.
- Sized mean-reversion fade, live POV throttle as alpha, thin-venue SOR cut, and TOB-only Promotes — **blocked** by Holds above. Do not soft-Promote.

### Next experiments (Holds only)

1. `info.post_trough_ret` — widen complete sig sample; require post300 CI excludes 0 on early∧late before any fade size.
2. `info.v_path_continuous` — more continuous-V events; corr(V, fwdret) CIs at 5/30/60s before live throttle params.
3. `risk.xvenue_minv_concord` — multi-venue complete days; need ≥1 replicated concordant sig pair.
4. `liq.spread_around_minv` — Deribit L2 + collector TOB only; Δspread CI with honest source labels.
5. `id.auction_loss` — stays identification Hold; no invented auction proxy trade.

