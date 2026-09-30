# Strategy lab — tick / order-book sims + equity curves

**Open first:** [`strategy_lab.ipynb`](strategy_lab.ipynb) (desk board: Promote IDs → signal → action → risk + equity + paper day) · HTML optional via `jupyter nbconvert` · PNGs in [`out/figs/`](out/figs/).

Desk context: [`../../DESK_MEMO.md`](../../DESK_MEMO.md) §7 · Promote rollup [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md) · applications index [`../README.md`](../README.md) · playbook [`../../TRADING_APPLICATIONS.md`](../../TRADING_APPLICATIONS.md) · paper day [`../paper_harness/`](../paper_harness/).

**Class:** risk-policy / MM playbook **simulations** — not naked tradable alpha. Friction haircut default **2 bps** one-way.

---

## Where to look (paths)

| Artifact | Path |
|----------|------|
| **Notebook (start here)** | `applications/strategy_lab/strategy_lab.ipynb` |
| **HTML** | `applications/strategy_lab/out/strategy_lab.html` |
| **Summary JSON** | `applications/strategy_lab/out/summary.json` |
| **Cell rollup** | `applications/strategy_lab/out/cells_rollup.json` |
| **Equity curves** | `applications/strategy_lab/out/figs/equity_curves_focus.png` |
| **Drawdowns** | `applications/strategy_lab/out/figs/drawdown_baseline_vs_ladder.png` |
| **Price + regime shades + fills** | `applications/strategy_lab/out/figs/price_regimes_fills.png` |
| **Inventory** | `applications/strategy_lab/out/figs/inventory_path.png` |
| **Book around events** | `applications/strategy_lab/out/figs/book_depth_events.png` |
| **Δ vs baseline** | `applications/strategy_lab/out/figs/delta_vs_baseline.png` |
| **Early/late** | `applications/strategy_lab/out/figs/early_late_split.png` |
| **Book source honesty** | `applications/strategy_lab/out/figs/book_source_counts.png` |

Sibling event-study packages (no full equity path): `../kill_ladder/`, `../nanex_burst/`, `../mm_quoting/`, `../hl_thin_sor/`.

---

## How to run

```bash
cd research/books/cross_miniflash/applications/strategy_lab
python3 exp_strategy_lab.py --workers 14          # full HL+DB+KR cells with events
python3 exp_strategy_lab.py --hl-only --workers 10 # faster book-focused pass
# optional HTML:
# jupyter nbconvert --to html strategy_lab.ipynb --output out/strategy_lab.html
```

Requires warehouse env (`startarb.env.ensure_env`), same Phase-4 days as the applications panel (`2026-09-04`…`10`, ETH/BTC). Reuses `applications/out/event_panel/` when present.

---

## Simulator (honest)

**Clock:** trade-tape event loop (ms prints).

**Book:** best available asof join:

1. Collector TOB (`ares-startarb/results/xarb_md/tob/YYYYMMDD`) when that UTC day exists  
2. Else warehouse BBO / HL `l2_rebuild` (~**seconds** median cadence)  
3. Optional HL multilevel `l2_snapshot_level` depth (L1–L5 sum) when cache present  

**Cadence limits:** Phase-4 slice days usually **lack** collector TOB → warehouse book is **not** ms L2. Do not read equity curves as sub-second queue-position claims.

**Fills:** synthetic touch maker — aggressive opposite trade fills `min(our_size, trade_qty)` when the print reaches asof bid/ask; **fill px = trade print** (not stale asof touch — warehouse BBO can lag the ms tape by minutes). Inventory marked to asof mid; friction subtracted each fill. Inventory soft-capped. **No fantasy latency edge.**

---

## Strategies

| Stub | Behaviour |
|------|-----------|
| `baseline_maker` | Always-on small size at touch |
| `kill_ladder_maker` | Size mult by ladder tier; halt → pull |
| `nanex_temp_pull` | Pull ~15s after Nanex∩SSM nest |
| `v_restore_confirm` | Post-crash stay-wide; restore on recovery@1–2s ≥0.5 |
| `always_stay_wide` | Stay wide through crash manage window |
| `hl_thin_size_cap` | Extra size cut on HL when thin excess elevated |
| `ladder_plus_v_restore` | Ladder size floor × V-confirm restore (expanded_lab) |
| `confirm_before_restore` | Require 1s **and** 2s V confirm before full restore |

Ladder tiers come from the shared applications panel (within-gated z percentiles + intensity + Nanex nest) — same object as `kill_ladder/`. Combined stubs also live under `../expanded_lab/strategies/`.

---

## How to interpret curves

1. **Equity (bps of ref notional)** — cumulative marked PnL after friction. Compare overlays to `baseline_maker` on the same cell.
2. **Δ vs baseline** — cell-pooled mean with bootstrap CI. CI including 0 → overlay does not clear noise on this slice (Hold as live PnL claim; may still be Promote-as-risk-policy from event-study markout).
3. **Drawdown** — max equity peak-to-trough; ladder should cut crash-window inventory bleed vs baseline.
4. **Regime shades** — widen / size_cap / halt windows on the price path; markers are synthetic fills.
5. **Book depth panels** — touch size (± depth when available) around gated event ends; stale BBO → treat as regime context not microstructure edge.
6. **Early / late split** — sign-stable day cohorts strengthen desk confidence; flips → Hold.
7. **Inventory path** — position through the day; halt/pull should flatten risk in fire windows.

---

## Relation to §7 board

| Board package | This lab |
|---------------|----------|
| Kill-ladder event Δ\|mo\| | + marked maker equity with ladder overlay |
| Nanex∩SSM precision / nested pull | + temporary pull equity path |
| V-restore quoting playbook | + confirm-V vs stay-wide equity |
| HL thin SOR | + optional size-cap overlay equity |

Event-study Promote labels in DESK_MEMO §7 still stand; this package adds **executable tick/OB equity deliverables** the desk asked for.
