# Edge lab — non-MM top-3 from TRADE_IDEAS

**Open:** [`out/EXP_REPORT.md`](out/EXP_REPORT.md) · figs [`out/figs/`](out/figs/) · [`out/summary.json`](out/summary.json)  
**Ideas map:** [`../TRADE_IDEAS.md`](../TRADE_IDEAS.md)  
**Honesty:** research_sim · costs · capacity — **not live alpha**. MM quoting not expanded.

## Scoreboard

| id | decision |
|----|----------|
| TI-v-fade (causal @2s) | **Promote** |
| TI-cont-ride (causal @2s) | **Kill** |
| TI-v-fade+cont combo | **Promote** (fade-dominated) |
| TI-int-halt | **Promote** |
| TI-nanex-nest | **Promote** |

Note: TI-v-fade causal Promote; TI-cont-ride causal Kill — combo edge is fade-dominated; always_fade also clears CI but mid_mo null → not naked tradable

## How to run

```bash
cd research/books/cross_miniflash/applications/edge_lab
python3 exp_edge_lab.py
```

Inputs: `../mm_quoting/out/panel_cache.json` + nest/tier join from `../out/event_panel/`.
