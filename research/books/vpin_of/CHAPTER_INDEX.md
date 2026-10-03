# VPIN / order flow — research index

Living map of Easley–López de Prado–O'Hara VPIN packages → candidates → experiment status.
Siblings: [`../mn_tuwrv/`](../mn_tuwrv/) · [`../empirical_mm/`](../empirical_mm/) · [`../cross_miniflash/`](../cross_miniflash/) · [`../v_shapes/`](../v_shapes/) · [`../cd_me/`](../cd_me/).
Data: [`../../DATA_PATHS.md`](../../DATA_PATHS.md). Desk: [`DESK_MEMO.md`](DESK_MEMO.md). Uses: [`TRADING_APPLICATIONS.md`](TRADING_APPLICATIONS.md).

**Book:** VPIN / flow toxicity (Easley et al. line). Slug: `vpin_of`.

**Program status:** **Pass 1 + Pass 2 + Pass 3 complete** — Pass 1 **n_ok=226**/315 · HL+DB promote **n_ok=139**. **Latest board:** [`out/pass3/decisions_pass3.json`](out/pass3/decisions_pass3.json) (**5 Promote / 6 Hold** — Pass 3 retested all six Hold blockers; no flips).

**Shared lib:** [`../../lib/vpin.py`](../../lib/vpin.py) · [`../../lib/continuous.py`](../../lib/continuous.py) (`vpin_bucket`) · [`../../lib/pin.py`](../../lib/pin.py) · loaders [`scripts/_data.py`](scripts/_data.py)

**Inventory:** [`scripts/exp_data_inventory.py`](scripts/exp_data_inventory.py) → [`out/data_inventory/`](out/data_inventory/)

**Day VPIN hook:** [`scripts/exp_vpin_day.py`](scripts/exp_vpin_day.py) → [`out/vpin_day/`](out/vpin_day/)

**Panel hook (Agent 2):** [`scripts/exp_vpin_panel.py`](scripts/exp_vpin_panel.py) → [`out/vpin_panel/`](out/vpin_panel/)

**Monitors:** [`applications/monitors.py`](applications/monitors.py)

---

## Chapter map (source → empirics)

| Package | Paper object | Primary data |
|---------|--------------|--------------|
| `ch00_overview` | VPIN definition, volume clock, toxicity narrative | inventory + pointers |
| `vpin_construction` | Bucket size, window, imbalance \|V_buy−V_sell\|/V | trade tape, UTC day |
| `pin_compare` | PIN MLE vs VPIN levels & dynamics | multi-day tape (≥20d) |
| `toxicity_events` | High-VPIN regimes, stress days | tape + optional mark/TOB |
| `predictiveness` | VPIN → short-horizon markout / spread / vol | tape + TOB/marks |
| `cross_venue` | HL vs Deribit vs Kraken concordance | core trio panel |
| `robustness` | Bucket scale, window, side rules | same panel, perturbations |

---

## Package roadmap

| Package | Status | Notes |
|---------|--------|-------|
| `ch00_overview` | `pass1` | Board from `decisions.json` |
| `vpin_construction` | `pass1` | Smoke day + calibration grid |
| `vpin_buckets` | `pass1` | Panel gates + falsifiers |
| `pin_compare` | `pass1` | Proxy Spearman; MLE Hold |
| `toxicity_events` | `pass3` | Residual spread join — **Hold** (ρ_resid CI through 0) |
| `predictiveness` | `pass3` | Dense L2 markout **Hold** (69/110; medIC≈0.011; gate failed) |
| `cross_venue` | `pass3` | Harmonized target50 concordance **Hold** |
| `robustness` | `pass3` | Extended bucket grid **Hold** (spread 0.725) |

---

## Panel modes

| Mode | File | n_ok | Row set |
|------|------|------|---------|
| `panel_exploratory` | `out/vpin_panel/decisions.json` | 226 | HL+DB+Kraken, `--all-days`, complete UTC |
| `panel_promote` | `out/vpin_panel/decisions_panel_promote.json` | 139 | HL+DB only (Kraken excluded) |

Both modes share the same **5 Promote / 3 Hold** gate table below.

## Promote rollup (Pass 1)

| Candidate | Decision | One-line |
|-----------|----------|----------|
| `cont.vpin_constructed` | **Promote** | n_ok=226 (HL+DB=139) complete days |
| `cont.vpin_bucket_mean` | **Promote** | median×50 SoT |
| `info.vpin_side_shuffle` | **Promote** | pass_rate≈0.98 vs side-permute |
| `info.vpin_time_split_stable` | **Promote** | stable_rate≈0.97 in-day split |
| `disc.pin_proxy_vs_vpin` | **Promote** | day proxy ↔ mean_vpin rank (HL ETH CI_lo>0); not level match |
| `frag.xvenue_vpin_concord` | **Hold** | HL↔DB ρ≈−0.32 (CI through 0) |
| `frag.kraken_vpin` | **Hold** | real tape, incomplete UTC — label only |
| `frag.hl_sol_empty` | **Hold** | HL SOL: 1/37 listing days (FNV 621827265); post-2026-08-28 empty |

---

## Pre-registered gates (Pass 1)

| ID | Gate |
|----|------|
| `cont.vpin_constructed` | `n_buckets≥20` ∧ finite `mean_vpin` on **complete** UTC day |
| `cont.vpin_vs_pin` | PIN MLE vs VPIN same-sign regime split on ≥20 days (not level equality) |
| `info.vpin_markout` | High VPIN quintile worse 30s markout vs low; bootstrap CI, venue holdout |
| `frag.xvenue_vpin` | Spearman VPIN across HL–DB within day ≥0.3 on ≥15 paired days |
| `risk.vpin_toxicity_flag` | Top-decile VPIN days align with spread widen / vol spike (monitor, not alpha) |

**Kill falsifiers (draft):** flat VPIN across buckets · VPIN inverted vs markout · Kraken-only Promote without completeness flag

---

## Notebooks

| Notebook | Role |
|----------|------|
| [`notebooks/desk_synthesis.ipynb`](notebooks/desk_synthesis.ipynb) | Desk board + Pass 2 markout/toxicity section |
| [`chapters/*/`](chapters/) | Per-package chapter packs |

Rebuild: `python3 scripts/build_notebook_figs.py` · `python3 scripts/build_notebooks.py` · plan [`PLAN.md`](PLAN.md)
