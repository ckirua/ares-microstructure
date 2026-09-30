# Desk memo — Tick Size Viewpoints (Rindi et al. MMCV #3 2014)

**Audience:** crypto MM / SOR / execution / taker / risk / research  
**Source:** Rindi et al. *Tick Size: Theory and Evidence* slides (Paris 2014-12-11) → `research/books/mm_confr_viewpoints/`  
**Philosophy:** lenses `risk | info | exec | disc | cont | liq | mm` — tick objects are **not** automatically tradable.  
**Data:** warehouse trades + collector/warehouse TOB on **HL + Deribit + Kraken** — **no ClickHouse MCP**.  
**Program status:** Pass-2.5 hardened — **1 Promote / 9 Hold / 4 Kill**.  
**SoT:** [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) · Lib: [`../../lib/ticksize.py`](../../lib/ticksize.py) · Loaders: [`scripts/_data.py`](scripts/_data.py) · Bootstrap: [`scripts/exp_bootstrap_btc.py`](scripts/exp_bootstrap_btc.py).

---

## 1. Desk jobs × intended outputs

| Job | Deck object | Tentative desk label | Status |
|-----|-------------|----------------------|--------|
| **Quote regime monitor** | Relative tick; frac 1-tick | Risk / quoting regime (cross-link mmip) | Hold — overlap |
| **Make / take aggressiveness** | Tick-constrained undercutting | Fragility monitor | Hold |
| **Liquidity split** | Liquid vs less-liquid × Δ(rel tick) | Heterogeneous MQ | Hold — thin terciles |
| **Placebo flat-rel_tick** | Mid moves with flat τ/mid → |Δqs|≈0 | Channel falsifier | Hold |
| **SOR / x-venue** | Cross-venue τ gap + grid pressure | Venue preference | Hold |
| **Prediction scorecard** | Expected-sign matrix pp. 20–29 | Theory→crypto hit rate | Hold matrix / Kill as tradable |
| **Competing defs** | vs mmip `tick.*` | Cross-link only | Promote taxonomy framing |

---

## 2. Signal board (Pass 2.5 — day-block bootstrap + BTC)

| ID | Formula / clock | Monitor | Tradable | Exec throttle | Decision |
|----|-----------------|---------|----------|---------------|----------|
| `disc.tick_rq_taxonomy` | RQ taxonomy · framing | yes | no | no | **Promote** — framing taxonomy vs mmip tick.*; not a numeric claim |
| `liq.placebo_flat_rel_tick` | |Δqs| | mid↑ & rel_tick flat | yes | no | no | **Hold** — blockers: BTC pooled weak (point=0.05862, hi=0.1633, n=53); HL-only clean (point=0.00021598791709739 |
| `disc.expected_sign_matrix` | deck pp.20–29 signs | yes | no | no | **Hold** — codified pp.20–29; crypto scorecard fragile on 3-day slice |
| `liq.fm_rel_tick_spread` | FM y~τ/mid · UTC-day/hour | maybe | no | no | **Hold** — pooled day FM t=-3.540854265584256; ρ day-block=-0.6 CI=[-0.833,-0.383]; xvenue τ confound; HL hour  |
| `liq.rho_rel_tick_spread` | Spearman(τ/mid, spread) | maybe | no | no | **Hold** — Spearman ρ=-0.6 dayCI=[-0.833,-0.383]; native ρ=-0.714; BTC ρ=-0.667 |
| `exec.tick_constrained_flag` | spread≤2 ticks | yes | no | maybe | **Hold** — HL frac=0.992 dayCI=[0.985,0.997]; DB=0.136; Kraken **spot L2** now native (futures PF still synth); overlaps mmip  |
| `exec.undercut_rate` | L0 tighten ≤1.5 ticks | maybe | no | maybe | **Hold** — ρ(uc,frac_c)=-0.371 dayCI=[-0.771,1] native n_days=3; L0 proxy, no queue ID; synth excluded |
| `frag.xvenue_tau_gap` | HL↔Deribit↔Kraken Δτ | yes | no | maybe | **Hold** — HL↔Deribit τ gap stable on ETH+BTC; Kraken spot L2 native but spot≠PF futures market |
| `frag.grid_pressure` | Δ(τ/mid) | τ fixed | maybe | no | no | **Hold** — feature computed; residual MQ Δ needs FE / wider sample |
| `liq.book_tercile_het` | liquid×rel_tick het | maybe | no | no | **Hold** — n=3 per tercile; BTC replicates pattern but still thin |
| `id.lse_nasdaq_rdd_literal` | equity RDD template | no | no | no | **Kill** — no sovereign tick ladder / vanity RD |
| `id.welfare_tick` | welfare | no | no | no | **Kill** — unobservable |
| `id.sec_ipo_channel` | SEC/IPO | no | no | no | **Kill** — out of scope |
| `disc.sign_scorecard_tradable` | sign hit-rate | no | no | no | **Kill** — hit_rate≈0.33 on ETH slice; not a tradable signal |

**Kill list:** literal LSE/Nasdaq RDD; welfare; SEC/IPO; sign-scorecard-as-tradable  
**Hold blockers:** x-venue τ confound for FM; Kraken futures PF still L2-absent (spot L2 now native); mmip descriptor overlap; thin Deribit L2 cadence

### Bootstrap snapshot (day-block 95% CI)

| Object | ETH | BTC |
|--------|-----|-----|
| placebo mean\|Δqs\| bps | 0.000696 [0.0003853,0.001013] n=52 | 0.05862 [9.239e-05,0.1633] n=53 |
| ρ(rel_tick, spread) | -0.6 [-0.833,-0.383] | -0.667 [-0.833,-0.65] |
| HL frac_constrained | 0.992 | 0.989 |
| ρ(uc, frac_c) native | -0.371 | 0.657 |

Artifacts: `out/hardening/hardening_pass25.json` · figs under `out/hardening/figs/` · Kraken spot vs synth: `out/kraken_native/`.

---

## 3. Venue completeness (locked)

| Venue | Role | TOB in slice | Notes |
|-------|------|--------------|-------|
| Hyperliquid | DEX anchor | Yes (collector + l2_rebuild) | native TOB |
| Deribit | CEX perps | Yes (warehouse L2 TOB) | native TOB |
| Kraken | CEX spot L2 + futures tape | Spot `l2_rebuild` (`spot|ETH/USD`); futures `PF_*` trade_synth | **Spot native** for MQ/constraint; PF futures still no L2 in S3 |

Slice days: 2026-09-26, 2026-09-27, 2026-09-30  
ETH complete venue-days 9/9; TOB 9.  
BTC complete venue-days 9/9; TOB 9 — panel `out/pass1/panel_btc.json`.

**Figures:** `out/hardening/figs/` (placebo CI, FM ρ forest, constraint, undercut, within-venue slopes, time-split, gate board) + package figs under `out/<pkg>/figs/` + Kraken native vs synth under `out/kraken_native/figs/`. Notebook: [`notebooks/desk_synthesis.ipynb`](notebooks/desk_synthesis.ipynb).

---

## 4. Next gate (optional backlog)

1. Kraken futures PF L2 ingest (spot L2 already wired; drop remaining trade_synth for PF joins).  
2. Within-venue hourly FM with vol/OFI controls (remove residual mid-drift).  
3. Constraint-relax event study for exec throttle Promote (HL rarely relaxes).  
4. Widen days before flipping FM / undercut gates.

---

## Native Kraken spot L2 rerun (addendum)

- Panels: `out/pass1_native/` + `out/pass2_native/` (baseline `out/pass1/` = prior synth-era SoT).
- KR spread bps mean native≈0.03724 vs baseline≈1.5; frac_c native≈0.850 vs baseline≈0.000.
- ρ(rel_tick,spread) native=0.5 vs baseline=-0.6.
- xvenue: dual slices in `out/native_rerun/xvenue_tick/dual_slices.json` (futures synth labeled + spot L2 with spot≠perp).
- **No new Promotes** from numeric falsifiers; `disc.tick_rq_taxonomy` remains sole Promote.
- Gate board snapshot: `out/native_rerun/gates.json`.
- Figs: `out/native_rerun/figs/` + refreshed `out/<pkg>/figs/`.
