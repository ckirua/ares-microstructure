# tick_shadow — trades stream + incremental SSM sleeve

**Status:** living shadow sleeve (design + minimal impl).  
`live_orders=false` always. No mercat/gateway OE. Warehouse poll peers stay.

---

## Problem

`paper_live` and `v_fade_paper` are **warehouse day harnesses on a timer**
(see [`../SHADOW_POLL_VS_WS.md`](../SHADOW_POLL_VS_WS.md)):

| Sleeve | Wake | Tape | Detect |
|--------|------|------|--------|
| `paper_live` | 10s poll | S3 warehouse `load_day_trades` | full-day rebuild |
| `v_fade_paper` | 120s poll | complete gated-SSM day only | full `run_shadow` (~140s) |
| **`tick_shadow`** | **print arrival** | **HL public trades WS** | **incremental KF** |

Warehouse lag (minutes–hours) dominates poll wake. Faster poll does not create
prints. This sleeve is the honest tick path: **subscribe prints → update SSM →
shadow-fill severity_zend**.

---

## Feed decision (honest)

| Candidate | Verdict |
|-----------|---------|
| startarb `ExchangeWsHub` | **l2Book / TOB only** — no trades channel wired |
| xarb_collector parquet | TOB MD archive — not a print tape |
| `/dev/shm/atras-md-trade*` | Stale lab rings (Sep 15–16 mtimes); not trusted as live HL ETH |
| HL REST `recentTrades` | Works (~10 prints); good **warm-start / WS fallback** |
| **HL public WS `trades`** | **Primary.** Venue documents `{type:"trades", coin}` on `wss://api.hyperliquid.xyz/ws`. Confirmed live for ETH. |

**Feed used (locked):** Hyperliquid public WebSocket **`trades`** for ETH

```json
{"method":"subscribe","subscription":{"type":"trades","coin":"ETH"}}
```

on `wss://api.hyperliquid.xyz/ws`. Bootstrap: REST `recentTrades`. Dedup
`(time_ms, coin, tid)`. **Do not wait for startarb `ExchangeWsHub`** (TOB-only).
No SHM/Redis trade path on this host.

Implementation note: async `websockets` / `aiohttp` segfault on this host’s
TLS stack; sleeve uses **`websocket-client`** (sync) in a daemon thread.
On disconnect: reconnect + brief REST `recentTrades` so the KF does not go dark.

Warehouse pollers are **not deleted** — they remain the Promote / audit peer
(complete-day equity, gap_summary). tick_shadow is a **dual-running live sleeve**,
not a replacement scoreboard.

---

## SSM: batch API vs online

`research.lib.crash.kalman_ssm_filter` is a **batch** scalar KF over a full
tape (Tee & Ting §3.2). Math is **already recursive**:

\[
P^- = P + \sigma_p^2\Delta t,\quad
S = P^- + \sigma_m^2,\quad
\kappa = P^-/S,\quad
z = ( \log p - \hat x ) / \sqrt{S}
\]

There is **no** `filter.update(trade)` in `crash.py` today. tick_shadow carries
an **`IncrementalKalmanSSM`** that keeps `(x̂, P, last_ts)` and applies one
measurement update per print — same innovation z-score contract.

**Noise (minimal, documented Δ vs day harness):**

| Offline (`detect_venue_day`) | tick_shadow online |
|------------------------------|--------------------|
| MC-GARCH 5m composite → `σ_p²Δt` | EWMA / floor process rate × `Δt` |
| Tape MAD(`Δlog p`) → `σ_m²` | Rolling MAD ring (same floor `1e-4`) |
| Full-day severity gate after batch detect | Online run-length: enter `|z|≥z*`, exit when `|z|<z*`, then gate |

Online z will **not** bit-match warehouse day rebuilds (different noise path +
incomplete day). That is expected; audit peer remains warehouse.

Detection defaults mirror research: `z_star=6`, gate `min_dp_pct=0.10` (10 bps),
`min_i_c=5`.

---

## severity_zend hook (Promote_shadow)

Same executable defaults as `v_fade_paper`:

| Knob | Value |
|------|-------|
| `entry_mode` | `severity_zend` (no r2 wait) |
| `|z_peak|` | ≥ **20** |
| enter | `ts_end + 0.5s` |
| exit | `ts_end + 3s` |
| side | fade = `−direction` |
| friction | RT 4 bps (path mark) |
| `fire_pause` | `prior_only` — simplified: any gated event with `|z_peak|≥20` opens a 300 s pause for **follow-on** fades |
| `live_orders` | **false** (hard refuse) |

Fills are **shadow at the next WS print at/after** entry/exit time (print
integrity, not mid). Adverse stop off (`1e9` bps) matching Promote.

Kill-ladder MM overlay (`paper_live`) is **out of scope** here — this is the
directional V-fade path only.

---

## Process topology

```
                    HL wss …/ws  trades:ETH
                              │
                    ┌─────────▼─────────┐
                    │  HlTradesFeed     │  thread + queue
                    │  (+ REST warm)    │
                    └─────────┬─────────┘
                              │ Print(ts_ns, px, sz, tid)
                    ┌─────────▼─────────┐
                    │ IncrementalKalman │  x̂,P,z per print
                    │ EventRun machine  │  fire/gate on z*
                    └─────────┬─────────┘
                              │ GatedEvent
                    ┌─────────▼─────────┐
                    │ SeverityZendSleeve│  schedule + shadow fills
                    └─────────┬─────────┘
                              │
              logs/tick_shadow.log  (HEARTBEAT / FIRE / FILL)
              out/trades.jsonl      (shadow only)

   audit peer (unchanged):
     v_fade_paper --poll 120s / paper_live --poll 10s  → warehouse tape
```

---

## What this deliberately does **not** claim

1. Equity / Promote scoreboard parity with complete-day warehouse panels.
2. Nanex∩SSM nest (Nanex needs denser offline context; deferred).
3. TOB / QuoteHub as a trade substitute.
4. Live orders / OE.

---

## Ops

**Preferred — user systemd** (`ares-tick-shadow.service`, like `ares-vfade-shadow` / `ares-paper-live`):

```bash
systemctl --user daemon-reload
systemctl --user enable --now ares-tick-shadow.service
systemctl --user status ares-tick-shadow.service
journalctl --user -u ares-tick-shadow.service -f
tail -f logs/tick_shadow.log
systemctl --user stop ares-tick-shadow.service
systemctl --user restart ares-tick-shadow.service
```

Stop any stray manual `run_tick_shadow.py` first (duplicate WS clients).  
ExecStart cwd = this directory; `python3 -u run_tick_shadow.py --coin ETH` (severity defaults from `config.yaml`). Logs append to `logs/tick_shadow.log` (+ journal). Restart on failure.

**Manual smoke:**

```bash
cd research/books/cross_miniflash/applications/tick_shadow
python3 -u run_tick_shadow.py --coin ETH
# tail -f logs/tick_shadow.log
```

Hard stop if config sets `live_orders: true`.
