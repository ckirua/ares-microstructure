# nanex_nest — TI-nanex-nest deep join

**Open:** [`out/EXP_REPORT.md`](out/EXP_REPORT.md) · [`out/summary.json`](out/summary.json) · figs [`out/figs/`](out/figs/)  
**Idea:** [`../../TRADE_IDEAS.md`](../../TRADE_IDEAS.md) `TI-nanex-nest`  
**Honesty:** research_sim · costs · capacity — **not live alpha**. No MM. No ClickHouse MCP.

## Verdict

| field | value |
|-------|-------|
| decision | **Promote** |
| Δ\|mo\| nest−SSM-only | 5.11 bps CI[0.75, 9.86] |
| why | Δ|mo| nest−SSM-only clears friction; time-split stable; severity↑ |
| preferred_policy | `nest_hard_pause` |

## How to run

```bash
cd research/books/cross_miniflash/applications/edge_lab/nanex_nest
python3 exp_nanex_nest.py
```

Inputs: `mm_quoting/out/panel_cache.json` ⊕ `out/event_panel/panel_rows.json`  
OOS echo: `expanded_lab/out/panel/panel_rows.json`
