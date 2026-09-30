# X-venue lag taker (edge_lab lens)

When gated SSM / Nanex∩SSM fires on venue A, take crash direction on lagging venue B
(HL↔Deribit↔Kraken). Concordance Hold is the enabler (asynchronous fires).

```bash
cd research/books/cross_miniflash/applications/edge_lab/xvenue_lag
python3 exp_xvenue_lag.py
```

Outputs: `out/summary.json`, `out/EXP_REPORT.md`, `out/figs/`.
ClickHouse MCP banned. No commits from this lens.
