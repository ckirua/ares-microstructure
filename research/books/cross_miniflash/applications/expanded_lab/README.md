# Expanded lab — cross_miniflash

Longer panel / SOL robustness, richer MM+ladder variants, occurrence upgrades, denser-book honesty, **risk** scoreboard.

**Sibling-safe:** writes only under `expanded_lab/out/` — does **not** overwrite `applications/out/event_panel` (paper_harness / kill_ladder cache).

Desk: [`../../DESK_MEMO.md`](../../DESK_MEMO.md) · playbook [`../../TRADING_APPLICATIONS.md`](../../TRADING_APPLICATIONS.md).

## Open

| Artifact | Path |
|----------|------|
| Notebook | [`expanded_lab.ipynb`](expanded_lab.ipynb) |
| EXP_REPORT | [`EXP_REPORT.md`](EXP_REPORT.md) |
| Summary | [`out/summary.json`](out/summary.json) |
| Scoreboard | [`out/scoreboard.json`](out/scoreboard.json) |
| Figs | [`out/figs/`](out/figs/) |

## Run

```bash
cd research/books/cross_miniflash/applications/expanded_lab
python3 exp_expanded_lab.py --workers 4          # core + Sep1–3 + SOL(DB/KR)
python3 exp_expanded_lab.py --core-only --skip-book   # smoke
python3 exp_expanded_lab.py --include-dense      # optional thin Sep29/30 cells
```

## Extensions

| Slice | Content | Note |
|-------|---------|------|
| core | ETH/BTC · Sep4–10 · 3 venues | Phase-4 locked |
| extend | ETH/BTC · Sep1–3 | Longer panel |
| sol | SOL · Sep4–10 · Deribit+Kraken | HL SOL empty in warehouse |
| dense TOB | collector TOB Sep29–30 | Book realism only (tapes incomplete) |

## Class

Risk-policy / MM playbook / feature — **not** tradable alpha. Rank strategies on adverse markout, max DD, inventory-in-holes.
