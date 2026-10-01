# Paper-live — continuous crash-risk overlay (shadow only)

**Class:** risk-policy · **not** PnL alpha · **not** V-fade  
**Primary cell:** Hyperliquid ETH  
**Base:** [`../paper_harness/`](../paper_harness/) (detect → kill-ladder → shadow fills → risk report)

Long-running **rolling shadow sim**. No live exchange orders. Never submits to mercat/gateway.

> **severity_zend** (`|z|≥20` @0.5→3s, Promote_shadow) is **not** this package.  
> Run it from [`../edge_lab/v_fade_paper/`](../edge_lab/v_fade_paper/) — see [Restart with severity](#restart-with-severity-zend-not-this-unit) below.  
> `confirm_r2@2→5` is Hold / path-late; do not use it as the executable default.

Desk context: [`../../TRADING_APPLICATIONS.md`](../../TRADING_APPLICATIONS.md) · [`../paper_harness/README.md`](../paper_harness/README.md).  
Data inventory: [`../../../../DATA_PATHS.md`](../../../../DATA_PATHS.md). ClickHouse MCP banned.

---

## Pipeline (each poll)

1. **Refresh tape** — re-list/load warehouse trades for the UTC day via startarb/`_data.load_day_trades` (S3 → `~/.cache/warehouse`).
2. **Book** — strategy_lab `load_best_book` (collector TOB under `ares-startarb/results/xarb_md/tob` when the day dir exists; else warehouse BBO / tape-proxy).
3. **Detect** — **event-time** SSM on the trade tape (`σ_m` floor, z*=6) gated **10 bps / i_c≥5** + Nanex∩SSM nest. Not `trade_last_300` / `trade_last_9000` observation bars ([A13](../../EXPERIMENTS.md) Kill).
4. **Ladder** — within-gated z percentiles + **`wall_60s` intensity** (default) + Nanex escalate → `observe → widen → size_cap → halt`; optional **ladder × confirm-before-restore** (expanded_lab best-risk). MFT intensity alts `trade_300`–`trade_3000` are research-only; do not use N-tick bars for detection.
5. **Shadow fills** — at **trade print** (same integrity rule as paper_harness).
6. **Persist** — append `actions.jsonl`, refresh `RISK_REPORT.md`, heartbeat in the log.

Horizon defaults (A13 Promote): see [`../horizon_lab/HORIZON_RECOMMENDATION.md`](../horizon_lab/HORIZON_RECOMMENDATION.md). Config pins `detection_clock: event` + `intensity_clock: wall_60s` (`intensity_window_s: 60`). Poll wake may coalesce ≤1 s; `poll_interval_s` is decision wake, not the SSM observation clock.

---

## How to start

### Preferred: systemd user unit (background)

Unit: `~/.config/systemd/user/ares-paper-live.service`  
WorkingDirectory: this package · ExecStart: `python3 run_paper_live.py --poll --interval 10 --quiet` · shadow only (`live_orders=False`).

```bash
systemctl --user daemon-reload
systemctl --user enable --now ares-paper-live.service
systemctl --user status ares-paper-live.service
systemctl --user stop ares-paper-live.service
systemctl --user restart ares-paper-live.service
```

Requires a logged-in user session (or `loginctl enable-linger $USER` for boot persistence). Uses `/usr/bin/python3`, `EnvironmentFile=-%h/.env`, and `PYTHONPATH` for warehouse/startarb/ares-microstructure.

### Foreground / smoke

```bash
cd research/books/cross_miniflash/applications/paper_live   # from repo root

# continuous (Ctrl-C / SIGTERM to stop)
python3 run_paper_live.py --poll

# custom interval (default ~10s; config allows 5–15)
python3 run_paper_live.py --poll --interval 8

# smoke: 3 polls then exit
python3 run_paper_live.py --iterations 3 --interval 5

# pin a historical UTC day (still shadow / warehouse refresh)
python3 run_paper_live.py --day 2026-09-30 --iterations 1 --figs
```

Requires startarb/warehouse env (`startarb.env.ensure_env`) — same as paper_harness.

---

## How to `tail -f` the log

Absolute path (works from any cwd — relative `logs/paper_live.log` only works inside this package):

```bash
tail -f logs/paper_live.log
```

Log handlers **flush each record**. Optional daily UTC rotate (`log_rotate: daily` in `config.yaml`). systemd also appends stdout/stderr to the same file.

You will see: session start (incl. **v_fade Promote pointer** `severity_zend |z|≥20 @0.5→3s`), heartbeats with **`cum_eq_ladder_bps` / `Δeq_bps`**, tier changes, FIRE lines, shadow fill summaries, RISK_REPORT refreshes, and errors.

> paper_live is the crash-risk **ladder overlay** (maker equity scoreboard). Executable V-fade alpha curves live in [`../edge_lab/v_fade_paper/out/EQUITY.md`](../edge_lab/v_fade_paper/out/EQUITY.md).

---

## How to stop

- systemd: `systemctl --user stop ares-paper-live.service`
- Foreground: `Ctrl-C` (SIGINT) — finishes the current poll, then exits.
- Ad-hoc process: `pkill -f run_paper_live.py` (SIGTERM also handled).

---

## Restart with severity_zend (not this unit)

This service is crash-risk kill-ladder only. For the Promote_shadow V-fade use the **separate** unit:

```bash
# durable living shadow (DISTINCT from ares-paper-live.service)
systemctl --user enable --now ares-vfade-shadow.service
systemctl --user status ares-vfade-shadow.service
tail -f ../edge_lab/v_fade_paper/logs/v_fade_shadow.log

# one-shot / foreground under v_fade_paper/
cd research/books/cross_miniflash/applications/edge_lab/v_fade_paper   # from repo root
python3 run_shadow_day.py
python3 run_v_fade_shadow_live.py --poll --interval 120
# ≡ severity_zend |z|≥20 @0.5→3s prior_only · live_orders=false
```

Restart **this** crash-risk loop (unchanged class):

```bash
systemctl --user restart ares-paper-live.service
# or foreground:
cd research/books/cross_miniflash/applications/paper_live   # from repo root
python3 run_paper_live.py --poll --interval 10 --quiet
```

---

## Where reports land

| Artifact | Path |
|----------|------|
| Live log | `logs/paper_live.log` |
| Action log (append) | `out/<day>_hyperliquid_ETH/actions.jsonl` (ladder fires + `shadow_fills_summary` + `poll_tick`; not per-fill spam) |
| Risk report | `out/<day>_hyperliquid_ETH/RISK_REPORT.md` (+ `.html`) |
| Summary / state | `out/<day>_hyperliquid_ETH/summary.json` · `state.json` |
| Figures (optional `--figs`) | `out/<day>_hyperliquid_ETH/figs/*.png` |

Config: [`config.yaml`](config.yaml).

---

## What “live” data means (honesty)

| Source | Role | Lag |
|--------|------|-----|
| **Warehouse trade tape** (S3 → cache) | Primary prints for detect + shadow fills | Typically **minutes–hours** behind exchange; each poll re-lists objects / refreshes cache |
| **Collector TOB** (`results/xarb_md/tob/YYYYMMDD`) | Book for fill eligibility when day dir exists | Denser (~sub-second–1s) when collector is running; **not** a trade tape substitute |
| mercat / gateway OE | — | **Never used** |
| Live order submission | — | **Never** |

Cadence: warehouse BBO can lag the tape; fills still book at the trade print (tape-proxy fallback when book is stale).

---

## Wired vs not

| Component | Status |
|-----------|--------|
| paper_harness detect / ladder / shadow / report | **Reused** |
| Warehouse trades via DATA_PATHS / startarb loaders | **Wired** (refresh each poll) |
| Collector TOB probe + book | **Wired if day dir present** |
| `tail -f` log + daily rotate | **Wired** |
| startarb `shadow_live` (pairs z-fade PnL sleeve) | **Not this package** (different alpha lane) |
| `v_fade_paper` severity_zend Promote_shadow | **Not this package** — run under `edge_lab/v_fade_paper/` |
| mercat / gateway live path | **Not used** |
| ClickHouse MCP | **Banned** |
