# Desk memo — VPIN / order flow (Easley et al.)

**Audience:** crypto MM / SOR / execution / taker / risk / research  
**Source:** VPIN / flow-toxicity deck → `research/books/vpin_of/`  
**Data:** warehouse **trade** tape (VPIN primary); TOB/marks for predictiveness — **no ClickHouse MCP**  
**Program status:** **Pass 1 + Pass 2 + Pass 3 complete** — latest board **5 Promote / 6 Hold** on `out/pass3/decisions_pass3.json`  
**SoT:** [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) · Uses: [`TRADING_APPLICATIONS.md`](TRADING_APPLICATIONS.md) · Lib: [`../../lib/continuous.py`](../../lib/continuous.py) · [`../../lib/vpin.py`](../../lib/vpin.py) · [`../../lib/pin.py`](../../lib/pin.py)  
**Artifacts:** [`out/vpin_panel/`](out/vpin_panel/) · [`out/pass2/`](out/pass2/) · [`out/pass3/`](out/pass3/) · [`out/vpin_day/`](out/vpin_day/)  
**Desk notebook:** [`notebooks/desk_synthesis.ipynb`](notebooks/desk_synthesis.ipynb)

---

## Panel modes (reconciled Pass 1 runs)

| Mode | Artifact | Row set | n_ok | Use |
|------|----------|---------|------|-----|
| **panel_exploratory** | [`out/vpin_panel/decisions.json`](out/vpin_panel/decisions.json) | ETH/BTC/SOL × HL+Deribit+Kraken, `--all-days`, complete UTC only | **226** / 315 | Falsifier denominators, coverage board |
| **panel_promote** | [`out/vpin_panel/decisions_panel_promote.json`](out/vpin_panel/decisions_panel_promote.json) | ETH/BTC/SOL × **HL+Deribit only** | **139** | Desk **Promote wiring** (Kraken excluded) |

**HL+DB extended panel (Pass 2/3 TOB joins):** n=**110** symbol-days — [`out/pass2/panel_hl_db_extended.json`](out/pass2/panel_hl_db_extended.json)

---

## Pass 3 signal deltas (vs Pass 2)

| ID | Pass 2 | Pass 3 | Key delta |
|----|--------|--------|-----------|
| `frag.hl_sol_empty` | Hold (n=0 recent) | **Hold** | FNV id **621827265** works; **1/37** days (2026-08-28 only) — shard gap, not flat-id |
| `frag.kraken_vpin` | Hold | **Hold** | strict=30, std=87; **18** tail days standard-only (partial coverage) |
| `frag.xvenue_vpin_concord` | Hold ρ≈−0.32 | **Hold** | target50 ρ≈−0.04 CI [−0.30,0.28]; rank ρ≈−0.17 — gate CI_lo≥0.15 **failed** |
| `info.vpin_markout` | Hold medIC≈0.007 (68d) | **Hold** | dense L2 120 q/min; **69/110** joins; medIC≈**0.011**; rankIC≈0.011 — pre-reg gate **failed** |
| `risk.vpin_toxicity_flag` | Hold ρ≈−0.36 | **Hold** | ρ_resid(spread\|RV)≈−0.05 CI through 0; Q5 spread **below** Q1 |
| `cont.vpin_bucket_robust` | Hold spread 0.678 | **Hold** | extended grid spread **0.725** (no material tightening) |

**Board:** still **5 Promote / 6 Hold** — no decision flips; Pass 3 narrows root causes and documents honest Holds.

Full table: [`out/pass3/decisions_pass3.json`](out/pass3/decisions_pass3.json) · summary [`out/pass3/pass3_summary.json`](out/pass3/pass3_summary.json)

---

## Pass 1 Promote rollup (unchanged)

| ID | Decision |
|----|----------|
| `cont.vpin_constructed` | **Promote** |
| `cont.vpin_bucket_mean` | **Promote** |
| `info.vpin_side_shuffle` | **Promote** |
| `info.vpin_time_split_stable` | **Promote** |
| `disc.pin_proxy_vs_vpin` | **Promote** |

---

## HL SOL (Pass 3 resolution)

- Catalog: `resolve_instrument('hyperliquid','SOL')` → **621827265** (`startarb/config/symbols.yaml` — no flat opaque id needed).
- Flat-era opaque ids remain **BTC/ETH only** (`hyperliquid_flat_ids`).
- Warehouse: trades exist **only on 2026-08-28** in current listing cache; all later days n=0.
- Desk: treat **SOL VPIN = Deribit + Kraken** until HL shard resumes (same as cross_miniflash expanded lab).

---

## Commands

```bash
cd /home/dev/srv/ares-microstructure/research/books/vpin_of
python3 scripts/exp_pass3.py --resume
python3 scripts/build_notebook_figs.py && python3 scripts/build_notebooks.py
python3 applications/monitors.py
```

---

---

## Pass 4 — **FINAL**

**Board:** `{'Promote': 5, 'Hold': 6}` on [`out/pass4/decisions_pass4.json`](out/pass4/decisions_pass4.json) · **book_status=FINAL**

| ID | Pass 3 | Pass 4 | Key delta |
|----|--------|--------|-----------|
| `frag.hl_sol_empty` | Hold | **Hold** | post-08-28 still 0 trades; formal **SOL=DB+Kr** arm documented |
| `frag.kraken_vpin` | Hold | **Hold** | futures TOB cache empty; S3 has no PF_* BBO |
| `frag.xvenue_vpin_concord` | Hold | **Hold** | fresh notional pairs on newest HL↔DB days — CI gate failed |
| `info.vpin_markout` | Hold | **Hold** | promote-slice 60s IC + venue holdout — gate failed |
| `risk.vpin_toxicity_flag` | Hold | **Hold** | intraday spike events — no spread widen |

```bash
python3 scripts/exp_pass4.py --resume
python3 scripts/build_notebook_figs.py && python3 scripts/build_notebooks.py
```
