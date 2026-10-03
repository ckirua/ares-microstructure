# Desk memo — VPIN / order flow (Easley et al.)

**Audience:** crypto MM / SOR / execution / taker / risk / research  
**Source:** VPIN / flow-toxicity deck → `research/books/vpin_of/`  
**Data:** warehouse **trade** tape (VPIN primary); TOB/marks for predictiveness — **no ClickHouse MCP**  
**Program status:** **Pass 1 + Pass 2 complete** — Pass 2 board **6 Promote / 5 Hold** on merged `decisions_pass2.json`  
**SoT:** [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) · Uses: [`TRADING_APPLICATIONS.md`](TRADING_APPLICATIONS.md) · Lib: [`../../lib/continuous.py`](../../lib/continuous.py) · [`../../lib/vpin.py`](../../lib/vpin.py) · [`../../lib/pin.py`](../../lib/pin.py)  
**Artifacts:** [`out/vpin_panel/`](out/vpin_panel/) · [`out/pass2/`](out/pass2/) · [`out/vpin_day/`](out/vpin_day/) · [`out/data_inventory/`](out/data_inventory/)  
**Desk notebook:** [`notebooks/desk_synthesis.ipynb`](notebooks/desk_synthesis.ipynb)

---

## Panel modes (reconciled Pass 1 runs)

| Mode | Artifact | Row set | n_ok | Use |
|------|----------|---------|------|-----|
| **panel_exploratory** | [`out/vpin_panel/decisions.json`](out/vpin_panel/decisions.json) | ETH/BTC/SOL × HL+Deribit+Kraken, `--all-days`, complete UTC only | **226** / 315 | Falsifier denominators, coverage board, chapter notebooks |
| **panel_promote** | [`out/vpin_panel/decisions_panel_promote.json`](out/vpin_panel/decisions_panel_promote.json) | ETH/BTC/SOL × **HL+Deribit only**, same complete-day filter | **139** | Desk **Promote wiring** provenance (Kraken never in Promote arm) |

**Pass 2 merge:** [`out/pass2/decisions_pass2.json`](out/pass2/decisions_pass2.json) · summary [`out/pass2/pass2_summary.json`](out/pass2/pass2_summary.json) — HL+Deribit extended panel **n=110** symbol-days for TOB joins (markout/toxicity); Pass 1 exploratory counts unchanged in `decisions.json`.

---

## Pass 2 signal deltas (warehouse TOB)

| ID | Decision | Key stats |
|----|----------|-----------|
| `info.vpin_markout` | **Promote** | 36/48 day-cells ok; median day IC≈**0.022** (30s TOB); time-split med IC early≈**0.030**, late≈**0.015** (both >0, pre-registered gate) |
| `risk.vpin_toxicity_flag` | **Hold** | n=73 TOB days; ρ(vpin, spread)≈**−0.36** (CI lo<0) — high VPIN **not** wider spread; monitor-only |
| `cont.vpin_bucket_robust` | **Hold** | Level spread≈0.68 across bucket grid — rank/falsifiers drive Promote, not level equality |
| `frag.xvenue_vpin_concord` | **Hold** | HL↔DB ρ≈−0.32, n=52 pairs (unchanged) |
| `frag.kraken_vpin` | **Hold** | strict_complete=30 / standard=87 — tail fragmentary |
| `frag.hl_sol_empty` | **Hold** | HL SOL n=0 all probed days |

Full table: `decisions_pass2.json`. Markout detail: [`out/pass2/markout.json`](out/pass2/markout.json).

---

## 0. Sample ceiling (listing cache probe, 2026-10-03)

| Venue | Listing days | ETH/BTC complete day example | Kraken caveat |
|-------|--------------|------------------------------|---------------|
| Hyperliquid | 37 (2026-08-28…10-03) | 2026-09-30 ETH n≈161k, coverage≈1.0 | **SOL empty** on 2026-09-30 (instrument gap) |
| Deribit | 35 | 2026-09-30 ETH/BTC/SOL complete | — |
| Kraken futures | 35 | Trades **tail-only** (~3–6k prints, coverage≈0.05) | **Hold only** — real tape, incomplete UTC days |

Full table: [`DATA_INVENTORY.md`](DATA_INVENTORY.md).

---

## 1. Signal board (Pass 1 canonical — `decisions.json`)

| ID | Decision | Evidence |
|----|----------|----------|
| `cont.vpin_constructed` | **Promote** | n_ok=226 (HL+DB=139); loaders + `vpin_bucket`; med mean_vpin≈0.862 |
| `cont.vpin_bucket_mean` | **Promote** | median(qty)×50 SoT |
| `info.vpin_side_shuffle` | **Promote** | pass_rate≈0.98 |
| `info.vpin_time_split_stable` | **Promote** | stable_rate≈0.97 |
| `disc.pin_proxy_vs_vpin` | **Promote** | day-level proxy vs mean_vpin Spearman — not EHO level |
| `frag.xvenue_vpin_concord` | **Hold** | HL↔DB ρ≈−0.32 |
| `frag.kraken_vpin` | **Hold** | partial Kraken futures tape |
| `frag.hl_sol_empty` | **Hold** | HL SOL shard gap |
| `info.vpin_markout` | **Hold** | superseded by Pass 2 **Promote** in `decisions_pass2.json` |

---

## 2. Related desk programs

| Program | VPIN touchpoint |
|---------|-----------------|
| [`../empirical_mm/`](../empirical_mm/) | Ch.15 PIN/VPIN deep runs on ETH |
| [`../cross_miniflash/`](../cross_miniflash/) | `vpin_exante`, VPIN×logN interaction (risk feature) |

---

## 3. Remaining blockers

1. HL SOL opaque flat-id / catalog mapping  
2. Kraken strict UTC completeness for cross-venue arm  
3. HL↔DB level harmonization (contract units) — concordance still Hold  
4. Toxicity flag: inverted spread co-move — do **not** wire as widen trigger without new falsifier

---

## Commands

```bash
cd /home/dev/srv/ares-microstructure/research/books/vpin_of
python3 scripts/exp_vpin_panel.py --all-days --symbols ETH BTC SOL --venues hyperliquid deribit kraken
python3 scripts/exp_pass2.py --resume --markout-max-days 12   # reuse out/pass2/*.json
python3 scripts/build_notebook_figs.py && python3 scripts/build_notebooks.py
```
