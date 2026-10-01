# V-shapes paper_live — MinV / EGARCH monitor SHADOW

**Class:** risk-monitor shadow · **not** sized alpha · **not** production quoting  
**Primary cell:** Hyperliquid ETH (+ Deribit / Kraken when available)  
**Sibling pattern:** [`../../../cross_miniflash/applications/edge_lab/v_fade_paper/`](../../../cross_miniflash/applications/edge_lab/v_fade_paper/) living shadow

Long-running **warehouse-day recompute** on the latest complete tape day (same shape as `v_fade_shadow`). No live exchange orders. Never mercat/gateway OE.

> **Desk honesty:** `exec.minv_breach_throttle` stays **Kill** (adverse markout worsens on OOS breach days — see [`../paper_throttle/EXP_REPORT.md`](../paper_throttle/EXP_REPORT.md)).  
> Shadow logs **Promote** MinV/EGARCH monitors + **hypothetical** Kill throttle state for observation / paper accounting only. **Do not soft-Promote. Do not size.**

Desk: [`../../DESK_MEMO.md`](../../DESK_MEMO.md) §5c · Index: [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md) · Lib: [`../../../../lib/vstat.py`](../../../../lib/vstat.py).  
ClickHouse MCP banned.

---

## What each poll does

1. Resolve **latest complete warehouse day** (HL ETH primary; pin with `--day` for replay).
2. Load tape via `scripts/_data.load_day_trades` (S3 → `~/.cache/warehouse`).
3. Compute **MinV vs EGARCH 5%** at \(h_n\in\{1,5,30\}\)m — **Promote** Monitor (`risk.egarch_minv_bands` / `risk.daily_minv_panel`).
4. If breach + coef artifacts exist: **calendar Ridge score** — **Promote** Monitor only (`info.v_feature_ridge_calendar`).
5. Log **paper** throttle knobs (widen / size / POV) tagged **`Kill/do-not-size`** — hypothetical, never deploy.
6. Append `logs/shadow.log` + `out/events.jsonl`; refresh `out/SHADOW_BOARD.md`.

---

## Gate labels in the shadow

| ID | Gate | Shadow role |
|----|------|-------------|
| `risk.egarch_minv_bands` | **Promote** | Breach monitor telemetry |
| `risk.daily_minv_panel` | **Promote** | Breach monitor telemetry |
| `risk.v_vs_jump_taxonomy` | **Promote** | Framing (not re-scored live) |
| `info.v_feature_ridge_calendar` | **Promote** | Score log — Monitor only, never sized |
| `exec.minv_breach_throttle` | **Kill** | Hypothetical widen/cut — **do not size** |
| `exec.minv_throttle_cal_join` | **Hold** | Paper secondary deepen |
| `exec.minv_throttle_as_alpha` | **Hold** | Never sized alpha |

---

## How to start

### Preferred: background poller (match v_fade_shadow)

```bash
cd research/books/v_shapes/applications/paper_live   # from repo root

# durable (systemd user unit)
cp ares-vshapes-shadow.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now ares-vshapes-shadow.service
systemctl --user status ares-vshapes-shadow.service

# or foreground forever
python3 run_paper_live.py --poll --interval 120

# smoke: one poll on latest complete warehouse day
python3 run_paper_live.py --iterations 1

# pin a historical UTC day (rolling replay)
python3 run_paper_live.py --day 2026-09-30 --iterations 1

# primary venue only (skip Deribit/Kraken)
python3 run_paper_live.py --iterations 1 --no-extra-venues
```

Unit `ExecStart`: `python3 run_paper_live.py --poll --interval 120 --quiet` · `live_orders=false` hard-pinned.

Requires startarb/warehouse env (`startarb.env.ensure_env`) — same as paper_throttle / `_data.py`.

### Attach “more live” later

Today the tape is **warehouse** (typically minutes–hours behind exchange), same as `v_fade_shadow`. When a denser live feed is wired:

1. Keep the same monitor + Kill throttle honesty contract.
2. Swap / supplement the day loader in `harness/shadow.py` + `harness/monitors.py`.
3. Do **not** flip `live_orders` or soft-Promote Kill throttle.

---

## How to `tail -f` the log

```bash
tail -f logs/shadow.log
```

You will see:

- `START` — venue/symbol + pinned gate labels
- `HEARTBEAT` — day, breached?, min_v / q05 / τ★, cal_score, hypo knobs
- `BREACH` — Promote Monitor (EGARCH MinV sig_5)
- `SCORE` — calendar Ridge Monitor only
- `HYPOTHETICAL Kill/do-not-size` — paper throttle state (never deploy)
- `STOP`

JSONL events (append):

```bash
tail -f out/events.jsonl
```

Event types: `breach` · `score` · `hypothetical_throttle` (all labeled; throttle = `kind=hypothetical`, `gate=Kill`).

---

## How to stop

```bash
systemctl --user stop ares-vshapes-shadow.service
# or foreground: Ctrl-C
# or: pkill -f 'v_shapes/applications/paper_live/run_paper_live.py'
```

---

## Artifacts

| Artifact | Path |
|----------|------|
| Live log | `logs/shadow.log` |
| Events JSONL | `out/events.jsonl` |
| Board | `out/SHADOW_BOARD.md` |
| Meta | `out/shadow_meta.json` |
| Per-day summary | `out/<day>_hyperliquid_ETH/summary.json` |

Board notebook: [`shadow_board.ipynb`](shadow_board.ipynb).

---

## vs paper_throttle / cross_miniflash

| | **this package** | `../paper_throttle/` | `cross_miniflash/.../v_fade_paper` | `cross_miniflash/.../paper_live` |
|--|--|--|--|--|
| job | living MinV/EGARCH monitor shadow | offline OOS Kill harness | V-fade taker shadow | crash-risk kill-ladder |
| log | `logs/shadow.log` | EXP_REPORT | `v_fade_shadow.log` | `paper_live.log` |
| throttle | **Kill** — hypo only | **Kill** verdict | n/a | ladder overlay |
| orders | never | never | never | never |

---

## Honesty

- Scoreboard = monitor telemetry + paper accounting — **not** PnL alpha
- Fills / widen / size in logs = **hypothetical** (labeled)
- `live_orders=False` · ClickHouse MCP banned · warehouse + startarb only
- Kill stays Kill — redesign trigger elsewhere before any deploy attempt
