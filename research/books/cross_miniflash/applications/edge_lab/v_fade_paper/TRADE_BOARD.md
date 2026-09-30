# V-fade trade board

Generated from `rollup.json` · primary **hyperliquid ETH** · extra `['deribit', 'kraken']`

```bash
cd /home/dev/srv/ares-microstructure/research/books/cross_miniflash/applications/edge_lab/v_fade_paper
python3 run_v_fade_paper.py --panel-days --extra-venues deribit,kraken
python3 write_trade_board.py
```

## Panel scoreboard (lab identity = −mo₅ₛ − RT4)

| metric | value |
|--------|------:|
| n_ok days | 7 |
| n_faded (HL) | 63 |
| lab mean net bps | **13.90** |
| lab CI | [8.55, 19.36] |
| path mean net bps | -7.17 |
| path CI | [-9.75, -4.21] |
| early / late | 9.80 / 15.95 |
| hit-rate (lab) | 0.84 |
| exits time / adverse | 48 / 15 |
| kill decision | **Promote_shadow** |

### Honesty note — lab vs path

Lab scoreboard matches `exp_edge_lab.causal_fade_v_only` (−mo from **event end** @5s − RT).  
Executable path fills at **confirm (+2s)** → exit; residual hold ≈3s. Path CI can be ≤0 while lab Promote — do **not** claim live alpha until OE fill study.

## Kill flags

| flag | status |
|------|--------|
| `K1_rolling_mean_nonpositive` | **ok** |
| `K2_ci_includes_zero` | **ok** |
| `K3_early_late_sign_flip` | **ok** |
| `K4_hit_rate_below_kill` | **ok** |
| `K5_adverse_stop_share_high` | **ok** |
| `K6_friction_blowout` | **ok** |
| `K7_infra_gate_or_detector` | **ok** |
| `K8_live_orders_enabled` | **ok** |

## Per-day (HL ETH)

| day | n_faded | mean lab net | hit |
|-----|---------|--------------|-----|
| 2026-09-04 | 11 | 8.84 | 0.73 |
| 2026-09-05 | 2 | 5.75 | 0.50 |
| 2026-09-06 | 8 | 12.13 | 1.00 |
| 2026-09-07 | 3 | 8.22 | 0.67 |
| 2026-09-08 | 27 | 20.70 | 0.96 |
| 2026-09-09 | 11 | 6.37 | 0.64 |
| 2026-09-10 | 1 | 16.59 | 1.00 |

## Extra venues (sparse)

| day | venue | n_faded | lab mean |
|-----|-------|---------|----------|
| 2026-09-04 | deribit | 1 | -4.81 |
| 2026-09-04 | kraken | 7 | -13.16 |
| 2026-09-05 | deribit | 0 | — |
| 2026-09-05 | kraken | 0 | — |
| 2026-09-06 | deribit | 1 | 18.52 |
| 2026-09-06 | kraken | 1 | -24.18 |
| 2026-09-07 | deribit | 0 | — |
| 2026-09-07 | kraken | 0 | — |
| 2026-09-08 | deribit | 1 | 12.06 |
| 2026-09-08 | kraken | 1 | 11.05 |
| 2026-09-09 | deribit | 0 | — |
| 2026-09-09 | kraken | 0 | — |
| 2026-09-10 | deribit | 0 | — |
| 2026-09-10 | kraken | 1 | -2.76 |

## Trades (first 40 HL ETH)

| day | event_i | side | exit | lab_net | path_net | mo_5s |
|-----|---------|------|------|---------|----------|-------|
| 2026-09-04 | 0 | sell | time_stop | 26.24 | 4.08 | -30.24 |
| 2026-09-04 | 3 | buy | time_stop | 8.65 | -2.99 | -12.65 |
| 2026-09-04 | 4 | sell | time_stop | 21.70 | 3.57 | -25.70 |
| 2026-09-04 | 5 | buy | time_stop | 14.72 | -1.98 | -18.72 |
| 2026-09-04 | 8 | sell | adverse_stop | -3.49 | -27.09 | -0.51 |
| 2026-09-04 | 9 | sell | adverse_stop | 3.17 | -25.04 | -7.17 |
| 2026-09-04 | 10 | sell | time_stop | -13.20 | -12.68 | 9.20 |
| 2026-09-04 | 11 | buy | time_stop | 10.81 | -2.98 | -14.81 |
| 2026-09-04 | 12 | buy | time_stop | 10.91 | -4.00 | -14.91 |
| 2026-09-04 | 13 | buy | time_stop | -3.49 | -0.40 | -0.51 |
| 2026-09-04 | 14 | buy | time_stop | 21.20 | -4.00 | -25.20 |
| 2026-09-05 | 2 | sell | time_stop | 14.48 | -6.57 | -18.48 |
| 2026-09-05 | 7 | sell | adverse_stop | -2.98 | -16.29 | -1.02 |
| 2026-09-06 | 1 | buy | time_stop | 0.56 | -9.06 | -4.56 |
| 2026-09-06 | 2 | buy | time_stop | 0.56 | -4.00 | -4.56 |
| 2026-09-06 | 6 | sell | time_stop | 3.58 | -4.00 | -7.58 |
| 2026-09-06 | 10 | sell | time_stop | 4.60 | -0.46 | -8.60 |
| 2026-09-06 | 12 | buy | time_stop | 23.00 | -1.97 | -27.00 |
| 2026-09-06 | 13 | sell | time_stop | 42.86 | -2.99 | -46.86 |
| 2026-09-06 | 15 | buy | time_stop | 19.37 | -2.99 | -23.37 |
| 2026-09-06 | 18 | sell | time_stop | 2.56 | -12.09 | -6.56 |
| 2026-09-07 | 0 | buy | adverse_stop | -2.99 | -16.12 | -1.01 |
| 2026-09-07 | 3 | buy | time_stop | 21.13 | -4.00 | -25.13 |
| 2026-09-07 | 7 | buy | time_stop | 6.52 | -4.00 | -10.52 |
| 2026-09-08 | 0 | buy | time_stop | 28.31 | 1.95 | -32.31 |
| 2026-09-08 | 1 | sell | time_stop | 17.60 | -4.00 | -21.60 |
| 2026-09-08 | 2 | sell | time_stop | 16.03 | -4.49 | -20.03 |
| 2026-09-08 | 3 | sell | time_stop | 16.47 | -4.49 | -20.47 |
| 2026-09-08 | 5 | sell | adverse_stop | 28.78 | -17.07 | -32.78 |
| 2026-09-08 | 8 | sell | time_stop | 106.93 | -10.52 | -110.93 |
| 2026-09-08 | 11 | sell | time_stop | 47.63 | -1.27 | -51.63 |
| 2026-09-08 | 12 | buy | time_stop | 17.45 | 0.56 | -21.45 |
| 2026-09-08 | 13 | buy | time_stop | 13.80 | -8.55 | -17.80 |
| 2026-09-08 | 14 | buy | time_stop | 19.80 | -4.00 | -23.80 |
| 2026-09-08 | 15 | buy | adverse_stop | 14.37 | -21.40 | -18.37 |
| 2026-09-08 | 28 | buy | adverse_stop | 18.71 | -16.26 | -22.71 |
| 2026-09-08 | 35 | sell | time_stop | 7.82 | 3.10 | -11.82 |
| 2026-09-08 | 37 | sell | adverse_stop | 9.22 | -16.77 | -13.22 |
| 2026-09-08 | 44 | sell | time_stop | 16.90 | -11.75 | -20.90 |
| 2026-09-08 | 45 | buy | time_stop | 27.69 | -1.25 | -31.69 |

_Full log: `out/trades.jsonl`. Per-day: `out/<day>_hyperliquid_ETH/RISK_REPORT.md`. Notebook: `v_fade_board.ipynb`._

## Honesty

research_sim · RT=4bps · mid_mo null → tape mo · live_orders=False · not MM · not live alpha · ClickHouse MCP banned
