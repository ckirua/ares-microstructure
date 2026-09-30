# TI-v-fade — executable strategy spec (directional, not MM)

**Status:** Promote (research_sim) · `causal_fade_v_only`  
**Source:** [`out/EXP_REPORT.md`](out/EXP_REPORT.md) · [`exp_edge_lab.py`](exp_edge_lab.py) · panel [`../mm_quoting/out/panel_cache.json`](../mm_quoting/out/panel_cache.json)  
**Honesty:** tape `mo_5s` economics · RT friction 4 bps · **mid_mo null** → not naked live alpha · `live_orders=False`  
**Kill sibling:** TI-cont-ride causal is **Kill** — do **not** ride continuation in this bot.

---

## 1. Thesis

Gated SSM hole → wait **causal** recovery@2s → if V-class, **fade taker** (mean-revert vs crash `direction`) → exit on **time stop** (align to mo@5s from event end) or **adverse stop**.

Event-study result (Phase-4 window 2026-09-04…10, ETH+BTC × HL/DB/KR):

| rule | n | net bps (after RT=4) | CI | early / late | decision |
|------|---|:--------------------:|----|--------------|----------|
| `causal_fade_v_only` | 117 | **+11.63** | [7.67, 15.91] | 7.47 / 14.52 | **Promote** |
| `causal_ride_cont_only` | 64 | −2.83 | [−7.40, 1.56] | −2.09 / −3.06 | **Kill** |
| `always_fade` | 270 | +7.08 | [4.57, 9.76] | 5.28 / 8.02 | Promote (wider; not primary) |

Oracle V `mo_5s` mean ≈ **−16.5 bps** (fade gross); friction clears at RT=4 and half-spread ≤5 bps (`friction/`).

---

## 2. Panel fields used (from `panel_cache.json` `events[]`)

| field | role |
|-------|------|
| `venue`, `symbol`, `day` | cell key |
| `ts_start`, `ts_end` | event clock (ns) |
| `direction` | ±1 crash sign (price excursion from start) |
| `dp_pct`, `i_c`, `z_peak` | severity / intensity context (gate already applied in cache) |
| `recovery_1s`, `recovery_2s` | **causal** class inputs — **never** use `recovery_5s` / `label` for live entry |
| `label` | oracle@5s only (backtest upper bound / diagnostics) |
| `mo_1s`, `mo_5s` | tape markout signed **with** crash direction (+ = continued adverse for fade) |
| `mid_mo_*` | **null on this slice** — do not size or score on mid |

Cache meta used by edge_lab: `days`, `symbols`, `venues`, `gate={min_dp_pct:0.10, min_i_c:5}`, `z_star=6.0`, `n_events=275`.

Optional joins (not required for fade entry): `event_panel` `nanex_overlap` / `tier` / `intensity_60s` for risk overlays only.

---

## 3. Parameters (locked to `exp_edge_lab.py`)

| param | value | notes |
|-------|------:|-------|
| `FRICTION_BPS` one-way | **2.0** | `_common.FRICTION_BPS` |
| `RT_FRICTION` | **4.0** bps | `2 × FRICTION_BPS` round-trip taker haircut |
| Gate | `|ΔP|≥10 bps`, `i_c≥5` | `severity_gate` primary |
| SSM `z_star` | 6.0 | detect path |
| `σ_m` floor | ≥1 bp (`sigma_m_frac=1.0`) | infra pre-condition |
| Confirm horizon | **2.0 s** after `ts_end` | causal V/cont |
| Soft confirm | **1.0 s** | `r1 ≥ 0.35` or missing |
| V threshold | `recovery_2s ≥ 0.5` | + soft 1s |
| Cont threshold | `recovery_2s < 0.2` | **flat** in this spec (Kill ride) |
| Partial | `0.2 ≤ r2 < 0.5` | **skip** |
| Hold / markout | exit at **`ts_end + 5s`** | matches sim `mo_5s` |
| Entry time | **`ts_end + 2s`** (after V confirm) | residual hold ≈ 3s |
| Trade size (sim) | unit notional `size=−1` fade | scale later; sim is unit |
| Primary venues | `hyperliquid`, `deribit`, `kraken` | venue-local detect+trade |
| Symbols | `ETH`, `BTC` | Phase-4 panel |
| Primary paper cell | HL ETH | mirror `paper_harness` |
| Adverse stop | see §5 | live/paper only (sim used fixed 5s exit) |

Economics identity (exact match to lab):

```text
size  = -1 if causal_class == v_recovery else 0   # fade only
gross = size * mo_5s                              # mo signed with crash direction
cost  = |size| * 4.0                              # bps RT
pnl   = gross - cost                              # ≡ -mo_5s - 4  when faded
```

Fade wins when tape **reverts** (typical V `mo_5s < 0` ⇒ `-mo > 0`).

---

## 4. State machine

```text
IDLE
  │  gated SSM event ends (ts_end)
  ▼
WAIT_RECOVERY
  │  at t = ts_end + 2s: compute recovery_2s (and recovery_1s)
  │  causal_class:
  │    v_recovery  → ENTER
  │    partial     → IDLE (skip)
  │    continuation→ IDLE (skip; do not ride)
  │    unknown     → IDLE (missing recovery)
  ▼
IN_FADE
  │  taker fill @ confirm clock, side = -direction  (fade crash)
  │  exits:
  │    TIME_STOP   if t ≥ ts_end + 5s
  │    ADVERSE     if live markout from entry ≥ adverse_stop_bps (crash-continue)
  │    HARD_KILL   if kill criteria trip (§7)
  ▼
FLAT → IDLE
```

### Causal class (no look-ahead) — copy of `causal_class()`

```python
def causal_class(recovery_2s, recovery_1s) -> str:
    if recovery_2s is None or not finite(recovery_2s):
        return "unknown"
    r2 = float(recovery_2s)
    r1 = float(recovery_1s) if recovery_1s is not None and finite(recovery_1s) else nan
    if r2 >= 0.5 and (not finite(r1) or r1 >= 0.35):
        return "v_recovery"
    if r2 < 0.2:
        return "continuation"
    return "partial"
```

`recovery_*` = `research.lib.crash.recovery_fraction(..., horizon_s=H)` from event start/end/`direction` on the **same venue tape**.

---

## 5. Executable steps / pseudo-code

Matches `exp_edge_lab.sim_v_cont` rule `causal_fade_v_only`, plus explicit entry/exit for paper/live shadow.

```python
# --- constants (lab-locked) ---
RT_BPS = 4.0
GATE = dict(min_dp_pct=0.10, min_i_c=5)
CONFIRM_S, EXIT_S = 2.0, 5.0
ADVERSE_STOP_BPS = 12.0   # paper default: ~½ typical |oracle V mo|; tune in shadow
MAX_CONCURRENT = 1        # per venue×symbol
CLIP_NOTIONAL = ...       # paper: small fixed; live shadow: research clip only

def on_tape_tick(state, tape, t_ns):
    if state.mode == "IDLE":
        for ev in new_gated_ssm_events(tape):  # z*=6, severity_gate, σ_m floor
            state.arm(ev)  # WAIT_RECOVERY, store ts_end, direction, px_end
        return

    if state.mode == "WAIT_RECOVERY":
        if t_ns < state.ts_end + CONFIRM_S * 1e9:
            return
        r1 = recovery_fraction(..., horizon_s=1.0)[state.idx]
        r2 = recovery_fraction(..., horizon_s=2.0)[state.idx]
        if causal_class(r2, r1) != "v_recovery":
            state.reset()  # skip partial / cont / unknown
            return
        # ENTER FADE — taker against crash
        side = -state.direction          # +1 crash up → sell; -1 crash down → buy
        px = asof_trade_px(tape, t_ns)   # tape print (paper_harness honesty)
        fill_shadow(side, CLIP_NOTIONAL, px, cost_one_way_bps=2.0)
        state.mode = "IN_FADE"
        state.entry_px, state.entry_t = px, t_ns
        return

    if state.mode == "IN_FADE":
        # adverse: markout from entry in crash-continue direction (same sign as mo)
        mtm_bps = state.direction * (asof_trade_px(tape, t_ns) / state.entry_px - 1.0) * 1e4
        # for a fade position, adverse = crash continuation = +mtm in direction frame
        pos_pnl_bps = -mtm_bps - accrued_cost_bps(state)  # fade PnL proxy
        if mtm_bps >= ADVERSE_STOP_BPS:
            exit_shadow(reason="adverse_stop")
            state.reset()
            return
        if t_ns >= state.ts_end + EXIT_S * 1e9:
            exit_shadow(reason="time_stop")     # aligns with mo_5s scoreboard
            # paper scoreboard: pnl_net_bps = -mo_5s - RT_BPS  (lab identity)
            state.reset()
            return
```

**Backtest / replay scoring (must match lab):** on each faded event with finite `mo_5s`, record `pnl = -mo_5s - 4.0`. Bootstrap CI + early(2026-09-04…06)/late(07…10) sign-stable + `mean(gross) > 4` for Promote.

---

## 6. Paper-trading harness (implemented)

Do **not** fork MM kill-ladder equity as the alpha claim. Reuse `paper_harness` **detect** + warehouse day I/O; replace ladder/maker with **taker fade**.

**Path:** [`v_fade_paper/`](v_fade_paper/) · CLI [`v_fade_paper/run_v_fade_paper.py`](v_fade_paper/run_v_fade_paper.py)

| paper_harness piece | reuse | change for v_fade |
|---------------------|-------|-------------------|
| `harness/detect.py` | **yes** | imported via `importlib` (emits `recovery_1s` / `recovery_2s`) |
| day loop / `--panel-days` | pattern | `run_v_fade_paper.py` |
| `config.yaml` gate / z_star | pattern | `v_fade_paper/config.yaml` + `v_fade:` block |
| `harness/ladder.py` + maker fills | **no** | taker clip at confirm (+ adverse stop) |
| report | pattern | lab scoreboard = −mo₅ₛ − RT4; path PnL separate |
| warehouse tape | **yes** | `_data.load_day_trades`; **no ClickHouse MCP** |

### How to run

```bash
cd /home/dev/srv/ares-microstructure/research/books/cross_miniflash/applications/edge_lab/v_fade_paper

# Primary cell
python3 run_v_fade_paper.py --day 2026-09-04 --venue hyperliquid --symbol ETH

# Phase-4 panel (2026-09-04…10)
python3 run_v_fade_paper.py --panel-days

# Optional thick venues
python3 run_v_fade_paper.py --panel-days --extra-venues deribit,kraken

# Rebuild trade board from outs
python3 write_trade_board.py
```

Layout:

```text
applications/edge_lab/v_fade_paper/
  run_v_fade_paper.py   # CLI
  config.yaml
  write_trade_board.py  # TRADE_BOARD.md from rollup
  TRADE_BOARD.md
  harness/
    pipeline.py         # day + panel orchestration
    strategy.py         # causal fade + adverse stop
    kill.py             # K1–K8 flags
    report.py           # RISK_REPORT + figs
    causal.py           # causal_class + asof tape px
  out/                  # per-day + panel rollup
```

Daily artifacts:

- `out/<day>_<venue>_<symbol>/actions.jsonl` — detect, confirm, enter, exit/skip  
- `trades.jsonl` — fade trade log (lab + path PnL)  
- `summary.json` — n_faded, bootstrap CIs, kill flags  
- `RISK_REPORT.md` · `figs/` — equity / price path / lab vs path  

Panel: `out/RISK_REPORT.md` · `out/rollup.json` · `out/trades.jsonl`

Primary paper cell: **hyperliquid ETH**, then Deribit/Kraken via `--extra-venues`.

---

## 7. Failure modes & kill criteria (live shadow)

### Failure modes

1. **Look-ahead leak** — using `label` / `recovery_5s` for entry (oracle upper bound only).  
2. **Mid fantasy** — sizing on `mid_mo_*` while null; stick to tape print.  
3. **Stale book** — warehouse BBO lag; fill at **tape print** (same honesty as paper_harness tape-proxy).  
4. **Continuation bleed** — entering on partial/cont; causal ride is Kill.  
5. **Friction blowout** — effective half-spread > ~5 bps kills edge (friction grid).  
6. **Capacity** — simultaneous multi-venue fades on same shock; clip + `MAX_CONCURRENT`.  
7. **Regime shift** — late-window edge weaker / sign flip vs early.

### Kill criteria (shadow → stop promoting / halt bot)

Trip **any** → flatten, set `decision=Kill` for the window, page desk:

| id | rule |
|----|------|
| K1 | Rolling 5-day mean **net** bps ≤ 0 after RT=4 on faded trades with n≥20 |
| K2 | Bootstrap CI for net includes 0 (same recipe as `_verdict`, n_boot≥800) |
| K3 | Early/late (or first-half/second-half of shadow calendar) **sign flip** on mean net |
| K4 | Hit-rate on fade exits < 0.55 over n≥40 (lab causal hit≈0.79; soft warn <0.65) |
| K5 | Adverse-stop share > 40% of entries over n≥30 (confirm not holding) |
| K6 | Realized one-way cost proxy > 5 bps median (friction DIE band) |
| K7 | Gate violation / σ_m floor off / detector skip storm (infra) |
| K8 | Any live order path enabled (`live_orders=True`) without separate desk sign-off — hard refuse |

**Hold (do not Promote further)** if n underpowered (<20 faded/week) or mid still null and OE fill slippage unmeasured — keep research_sim label.

---

## 8. Out of scope

- MM quoting / V-restore stay-wide (A05) — different playbook.  
- TI-cont-ride, combo ride leg, always_ride.  
- Nanex nest / int-halt as entry — optional **risk pause** overlays only.  
- ClickHouse MCP — banned; warehouse + panel_cache only.  
- Claiming tradable PnL until mid_mo / OE fill study clears.

---

## 9. Reproduce lab scoreboard + paper shadow

```bash
cd /home/dev/srv/ares-microstructure/research/books/cross_miniflash/applications/edge_lab
python3 exp_edge_lab.py
# primary Promote row: TI-v-fade (causal) in out/EXP_REPORT.md

cd v_fade_paper
python3 run_v_fade_paper.py --panel-days
# paper artifacts: out/RISK_REPORT.md · out/rollup.json · TRADE_BOARD.md (via write_trade_board.py)
```
