# Horizon lab — sampling clocks for mini-flash / risk-overlay

Answers: can Tee/Ting SSM + kill-ladder run at **300 / 9000 trade-count bars** (and calendar / volume clocks), or only on pure event-time tape?

## Clocks

| Family | Meaning |
|--------|---------|
| `event` | Trade-by-trade SSM (desk baseline) |
| `trade_last_N` | Last print every N trades |
| `trade_ohlc_N` | Open→extreme→close per N trades |
| `cal_1s` / `5s` / `60s` | Calendar last-print |
| `vol_USD` | Volume-clock closes |
| policy intensity | Event detection + wall/trade intensity window |

**300 / 9000 = event counts, not ms.** On HL ETH, N=300 ≈ 3–4 min wall; N=9000 ≈ 45 min.

## Run

```bash
cd research/books/cross_miniflash/applications/horizon_lab
python3 run_horizon_sweep.py --workers 8
python3 run_horizon_sweep.py --smoke 4 --workers 4
```

## Artifacts

- [`HORIZON_RECOMMENDATION.md`](HORIZON_RECOMMENDATION.md) — short answer
- [`out/EXP_REPORT.md`](out/EXP_REPORT.md) — full scoreboard + CIs
- [`out/summary.json`](out/summary.json)
- [`out/figs/`](out/figs/)
- [`horizon_lab.ipynb`](horizon_lab.ipynb)

## Verdict (HL ETH, 27 days)

- **Detection:** event **Promote**; `trade_last_300/9000` **Kill**; `cal_1s` Hold.
- **Intensity on event tape:** `wall_60s` and `trade_300`…`trade_3000` **Promote**; `trade_9000` Hold.
- **Liquidity:** Amihud-high days have more gated crashes; they still need event/≤1s detection — N=300 does not become viable.

No live orders. ClickHouse MCP banned.
