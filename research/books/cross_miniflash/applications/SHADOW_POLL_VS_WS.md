# Shadow poll vs WS ticks — frank memo

**Verdict:** Both living shadows are **warehouse poll loops**, not tick-driven.
Startarb already has **live TOB WS** (HL `l2Book`, Lighter, RiseX) for xarb / collector.
There is **no wired public trade-print WS** feeding paper shadows. Poll was chosen
because detect + shadow fills are **event-time SSM on a complete trade tape**, and
that tape only arrives via S3 warehouse (minutes–hours lag). Wiring WS ticks without
rewriting SSM + fill integrity would be theater.

`live_orders=false` everywhere below. No mercat/gateway OE. ClickHouse MCP banned.

---

## 1. `paper_live/` — how it gets tape

| Knob | Evidence |
|------|----------|
| Wake | `poll_interval_s: 10` (`config.yaml`); systemd `run_paper_live.py --poll --interval 10` |
| Trade tape | Warehouse S3 → `~/.cache/warehouse` via `load_day_trades` / `detect_day` each poll (`live/poll.py`) |
| Book | Optional collector TOB under `ares-startarb/results/xarb_md/tob/YYYYMMDD` (`use_collector_tob: true`) |
| Completeness | `require_complete_day: false` — runs on **live UTC day** (incomplete by design) |
| Fills | Shadow at **warehouse trade print** (`run_shadow` / `fill_action_records`) |
| Orders | Hard refuse `live_orders=true` |

Pipeline per poll (`live/poll.py` docstring + README):

1. Re-list/load warehouse trades for UTC day  
2. Probe collector TOB (mtime / lag only — not a trade substitute)  
3. Full-day gated SSM detect + kill-ladder  
4. Shadow fills on tape growth; else heartbeat `(no new tape)`

Observed 2026-09-30 ~21:30Z: tape stuck at `n_trades=152584`, `last_age_s` climbing
past 400s while still polling every 10s — **wake faster than warehouse ingest**.
Collector TOB day dir present but `lag_s` ~1.7ks (archive mtime not a live stream
into this process).

Config honesty (`config.yaml` `data.note`):

> Trade tape = warehouse … typically lags live by minutes–hours … Collector TOB
> is denser for book when the UTC day dir exists, but does **not** replace the
> trade tape.

---

## 2. `v_fade_paper/` — `run_v_fade_shadow_live.py`

| Knob | Evidence |
|------|----------|
| Wake | `poll_interval_s: 120` — “Warehouse lag is minutes–hours; 120s is enough” |
| Source | **Warehouse only** — log line: `warehouse tape only; never mercat/gateway OE` |
| Day selection | `find_latest_complete_day(..., require_gated_ssm=True)` — not “today” |
| Completeness | `require_complete_day: true` — incomplete live day **refused** |
| Work per poll | Full `run_shadow` → re-detect + causal fade on that complete day (~140s wall in logs) |
| WS | **None** — no QuoteHub, no `ExchangeWsHub`, no trade subscribe |

Living shadow is a **re-runner of the offline day harness** on a cadence, not a
streaming strategy. Observed day pin: `2026-09-22` while wall clock is `2026-09-30`
(`shadow_meta.json`) — waiting for a **complete + gated-SSM** warehouse day.

Distinct from `paper_live` (kill-ladder MM risk overlay). See package READMEs /
`SHADOW_BOARD.md` comparison table.

---

## 3. Real-time WS / tick paths that *do* exist (startarb)

These feed **xarb / TOB research**, not cross_miniflash shadow tape:

| Path | What | File |
|------|------|------|
| `ExchangeWsHub` | HL `wss://…/ws` **`l2Book`**, Lighter `order_book/{id}`, RiseX `orderbook` | `startarb/data/exchange_ws.py` |
| `QuoteHub` | In-process TOB buffer; strategies **pull** on decision, not every frame | `startarb/data/live_quotes.py` |
| `xarb_collector` | WS → parquet TOB under `results/xarb_md/tob/` (MD only, no OE) | `startarb/data/xarb_collector.py` |
| `xarb` paper soak | `--quote-source live` uses QuoteHub; warehouse is fallback | `startarb/research/xarb.py`, `config/xarb.yaml` |
| Warehouse trades | Offline prints via `startarb/data/trades.py` / `_data.load_day_trades` | S3 listing cache |

**Not present for shadow:**

- No HL `trades` / print channel in `exchange_ws.py` (TOB only).
- No Kraken public WS in startarb’s hub (Kraken appears as **warehouse** venue in v_fade panels, not live WS).
- Collector TOB ≠ trade prints; SSM + V-fade path PnL are defined on **prints**.

---

## 4. Why poll was chosen (honest)

1. **Tape source of truth is warehouse.** Detect and shadow fills are built on the
   same integrity rule as paper_harness: event-time SSM + fill-at-print on the
   listed day tape. Live WS TOB cannot substitute prints without a new MD contract.
2. **Warehouse lag dominates wake.** paper_live at 10s already outruns S3
   refresh (heartbeats show growing `last_age_s` with no new trades). Faster poll
   or WS book does not create new gated crashes.
3. **SSM is full-day / batch.** `detect_day` loads the day’s tape and rebuilds
   gated events. There is no incremental SSM state machine in the shadow loops.
   V-fade also needs day completeness + fire-pause history over the day.
4. **V-fade Promote_shadow is evaluated on complete days.** Incomplete live UTC
   days are excluded so living board matches the equity panel methodology
   (`require_complete_day`, `require_gated_ssm`).
5. **Separation of concerns.** Live TOB WS already powers xarb collector / soak.
   Shadow sleeves reuse the **research day harness** for auditability vs inventing
   a second, unvalidated streaming path.

---

## 5. Minimal path to WS-tick shadow (what would actually be needed)

Not a weekend config flip. Minimum viable:

| Piece | Need |
|-------|------|
| **Subscribe** | HL public **trades** (prints) for ETH (+ optional BBO via existing `l2Book`). Extend `exchange_ws` / sibling hub — today only TOB. |
| **State to keep** | Ring buffer of prints; rolling SSM sufficient stats (or warm-start from warehouse tail); open fade / ladder inventory; fire-pause clock; last processed `ts`. |
| **Detect** | Incremental or windowed SSM — **breaks** if you keep calling full-day `detect_day` on every print. |
| **Fills** | Shadow at WS print with explicit latency model; stop pretending warehouse_asof ≡ live. |
| **Completeness** | Drop or redefine `require_complete_day` for a “live sleeve”; keep warehouse day jobs for Promote scoreboard. |
| **What breaks** | Equity / gap_summary comparability; Nanex∩SSM nest if Nanex lags; collector-only book age vs tape; CPU if you naïvely rebuild full day each tick (v_fade already ~140s/poll). |

**Safe non-architecture improvements (sketch only):**

1. **Do not shorten poll as a “latency fix.”** paper_live 10s is already finer than
   warehouse; v_fade 120s matches multi-minute lag + ~2 min rebuild cost. Cutting
   intervals mostly burns S3 list/CPU.
2. **Optional: book freshness without OE** — pull ETH mid from existing
   `QuoteHub` / collector `*.parquet.tmp` for *display / stale_book* only, while
   fills remain warehouse prints. Improves honesty of book age; does **not** make
   detect tick-live.
3. **V-fade poll skip** — fingerprint complete-day object listing / `n` + mtime;
   skip full `run_shadow` when unchanged (saves ~2 min/wake). Still not WS.
4. **Real tick shadow** = new small sleeve next to xarb (WS trades + incremental
   detect), dual-running warehouse shadow for Promote audit — not a rewrite of
   these two pollers in place.

---

## Bottom line

Shadows are on poll because they are **warehouse day harnesses on a timer**.
Startarb WS is a **TOB plane for xarb**. Until there is a trade-print feed +
incremental SSM, “WS tick shadow” would either lie (TOB-as-tape) or require a
new path. Poll is the honest design for the current data contract.
