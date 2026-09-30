# TI-v-fade paper shadow

Executable causal V-fade taker on real warehouse tape. **Not** MM. **Not** live orders.

**Spec:** [`../V_FADE_STRATEGY_SPEC.md`](../V_FADE_STRATEGY_SPEC.md) · desk [`../../HOW_WE_TRADE.md`](../../HOW_WE_TRADE.md)

## How to run

```bash
cd /home/dev/srv/ares-microstructure/research/books/cross_miniflash/applications/edge_lab/v_fade_paper

# Single day (primary cell HL ETH)
python3 run_v_fade_paper.py --day 2026-09-04

# Full Phase-4 panel
python3 run_v_fade_paper.py --panel-days

# Expand venues (same days/symbol)
python3 run_v_fade_paper.py --panel-days --extra-venues deribit,kraken
```

## Outputs

Per day under `out/<day>_<venue>_<symbol>/`:

| artifact | content |
|----------|---------|
| `RISK_REPORT.md` | detection + lab/path PnL + kill flags |
| `summary.json` | machine summary + CIs |
| `trades.jsonl` | fade trade log |
| `actions.jsonl` | detect → confirm → enter/exit/skip |
| `figs/` | price path, equity, lab vs path |

Panel rollup: `out/RISK_REPORT.md` · `out/RISK_ROLLUP.md` · `out/rollup.json` · `out/trades.jsonl` · `out/figs/`

Trade board: [`TRADE_BOARD.md`](TRADE_BOARD.md) (regenerate after a panel run).

## Honesty

- Scoreboard = lab identity `pnl = −mo_5s − 4` (matches `exp_edge_lab.causal_fade_v_only`)
- Fills = asof **tape print** at confirm (+2s) / exit; **mid_mo ignored** (null)
- `live_orders=False` · ClickHouse MCP banned · warehouse + startarb only
