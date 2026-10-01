# TI-v-fade SHADOW PAPER

Executable causal V-fade taker on real warehouse tape. **Not** MM. **Not** live orders.

**Spec:** [`../V_FADE_STRATEGY_SPEC.md`](../V_FADE_STRATEGY_SPEC.md) · desk [`../../HOW_WE_TRADE.md`](../../HOW_WE_TRADE.md)

> **SHADOW PAPER** · `research_sim` · `live_orders=false` · lab = −mo₅ₛ−RT4 · path = entry@confirm→exit · **not** live OE

**Promote_shadow lock:** `severity_zend` · `|z|≥20` · enter `+0.5s` · exit `3s` · `fire_pause=prior_only` · `live_orders=false`

> **≠** [`../../paper_live/`](../../paper_live/) — that package is the crash-risk **kill-ladder** overlay (`ares-paper-live.service`). This package is the directional V-fade sleeve.

## How to run

```bash
cd research/books/cross_miniflash/applications/edge_lab/v_fade_paper   # from repo root

# Single day (primary cell HL ETH)
python3 run_v_fade_paper.py --day 2026-09-04

# Full Phase-4 panel (+ optional DB/KR)
python3 run_v_fade_paper.py --panel-days --extra-venues deribit,kraken

# One-shot living shadow on latest complete warehouse day
python3 run_shadow_day.py
# default: severity_zend |z|≥20 @+0.5s→3s prior_only (Promote_shadow)
```

## Living shadow poller (durable)

Preferred background path — **distinct** from `ares-paper-live.service`:

```bash
# install unit (once)
cp ares-vfade-shadow.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now ares-vfade-shadow.service
systemctl --user status ares-vfade-shadow.service

# or foreground
python3 run_v_fade_shadow_live.py --poll --interval 120
```

Unit `ExecStart`: `python3 run_v_fade_shadow_live.py --poll --interval 120 --quiet` · WorkingDirectory = this package · `live_orders=false` hard-pinned.

### Tail the log

```bash
tail -f ../edge_lab/v_fade_paper/logs/v_fade_shadow.log
```

You will see: session START (severity_zend defaults), **HEARTBEAT** lines (`n_faded`, `cum_path_eq_bps`), **TRADE** lines when new fades appear, SHADOW_BOARD refresh path, and errors.

### vs paper_live kill-ladder

| | **this package** (`v_fade_paper`) | **paper_live** |
|--|--|--|
| systemd | `ares-vfade-shadow.service` | `ares-paper-live.service` |
| log | `logs/v_fade_shadow.log` | `paper_live/logs/paper_live.log` |
| job | causal V-fade taker on latest warehouse day | crash-risk ladder overlay |
| scoreboard | path equity entry@+0.5s→3s | ladder maker equity |
| orders | never | never |

Do **not** restart `ares-paper-live` expecting V-fade alpha — use this unit / script.

```bash
systemctl --user stop ares-vfade-shadow.service
# or: pkill -f run_v_fade_shadow_live.py
```

## Outputs

Per day under `out/<day>_<venue>_<symbol>/`:

| artifact | content |
|----------|---------|
| `RISK_REPORT.md` | SHADOW-labeled detection + lab/path PnL + kill flags |
| `summary.json` | machine summary + CIs |
| `trades.jsonl` | fade trade log |
| `actions.jsonl` | detect → confirm → enter/exit/skip |
| `figs/` | **path equity** (event + calendar + DD) · vs confirm_r2 · lab diagnostic |

Panel rollup: `out/RISK_REPORT.md` · `out/RISK_ROLLUP.md` · `out/rollup.json` · `out/trades.jsonl`

Living shadow: `out/SHADOW_BOARD.md` · `out/shadow_meta.json` · `out/trades.jsonl` · poller log `logs/v_fade_shadow.log`

**Path equity:** `out/EQUITY.md` · `out/figs/equity_path_*.png` · `python3 build_equity_curves.py`

Default CLI:

```bash
python3 run_v_fade_paper.py --panel-days
# ≡ severity_zend --z-min 20 --confirm-s 0.5 --exit-s 3  (config.yaml)
python3 run_shadow_day.py
python3 run_v_fade_shadow_live.py --poll
```

## Honesty

- Scoreboard = lab identity `pnl = −mo_5s − 4` (matches `exp_edge_lab.causal_fade_v_only`)
- Path PnL = tape entry@confirm → exit; **lab ≠ path** when residual hold ≠ mo window
- Fills = asof **tape print**; **mid_mo ignored** (null)
- `live_orders=False` · ClickHouse MCP banned · warehouse + startarb only
- Path-optimized candidate (if `gap_summary.json`) is reported separately — never silently replaces lab identity
