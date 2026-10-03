# cd_me paper_shadow — PIM / DCM monitor SHADOW

**Class:** risk-monitor shadow · **not** sized alpha · **not** production quoting  
**Primary cell:** Hyperliquid ETH (+ Deribit / Kraken when TOB available)  
**Sibling pattern:** [`../../../v_shapes/applications/paper_live/`](../../../v_shapes/applications/paper_live/)

Long-running **warehouse-day recompute** on a pinned or latest listed tape day. No live exchange orders. Never mercat/gateway OE.

> **Desk honesty:** Pass-2 + Pass-2.5 boards are **Hold** (**0 Promote**).  
> Shadow logs monitor telemetry only. **Wire Promote only** (count still 0).  
> **Do not soft-Promote. Do not size. `live_orders=false`.**

Desk: [`../../DESK_MEMO.md`](../../DESK_MEMO.md) · Use map: [`../../APPLICATIONS.md`](../../APPLICATIONS.md) · Index: [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md) · Lib: [`../../../../lib/cdme.py`](../../../../lib/cdme.py).  
Info dig: [`../../out/info_features/`](../../out/info_features/) · ClickHouse MCP banned.

---

## What each poll does

1. Resolve day (`--day` or latest listing / prefer recent complete).
2. Load aligned TOB + trades via `scripts/_data.py`.
3. Compute VLOOP / TCOST / PIM + DCM̂ + elasticity regime flag (when data allows).
4. Append `logs/shadow.log` + `out/events.jsonl`; refresh `out/SHADOW_BOARD.md`.
5. All action knobs tagged **Monitor/Hold** — never submit orders.

---

## Gate labels in the shadow

| ID | Gate | Shadow role |
|----|------|-------------|
| `risk.pim_cross_venue` | **Hold** | PIM monitor telemetry |
| `risk.dcm_pc1` | **Hold** | DCM̂ regime flag |
| `liq.elasticity_regime` | **Hold** | Elasticity split (often thin-n) |
| `info.vloop_tcost_commonality` | **Hold** | corr(VLOOP,TCOST) |
| `info.pim_dcm_incremental` | **Hold** | Hypothetical: DCM-vs-RV join tile (not wired as Promote) |
| `info.elasticity_after_rv` | **Hold** | Hypothetical: RV-controlled elasticity flag |
| `info.kraken_spot_vs_synth` | **Hold** | Hypothetical: Kraken mode badge on board |
| `alpha.tob_cross_arb` | **Kill** | Never sized |
| `risk.bank_cds_var` | **Kill** | Vanity |

**Promote wiring:** when a candidate flips to Promote, surface it on `SHADOW_BOARD.md` as an actionable monitor rule. Until then, Hold tiles above are **documentation only** — do not flip `live_orders`.

---

## How to start

```bash
cd research/books/cd_me/applications/paper_shadow   # from repo root

# smoke: one poll on a historical UTC day
python3 run_paper_shadow.py --day 2026-09-29 --iterations 1

# one poll on latest listing day
python3 run_paper_shadow.py --iterations 1

# foreground forever
python3 run_paper_shadow.py --poll --interval 120
```

Requires startarb/warehouse env (`startarb.env.ensure_env`) — same as `_data.py`.

---

## How to `tail -f` the log

```bash
tail -f logs/shadow.log
```

JSONL events:

```bash
tail -f out/events.jsonl
```

---

## Honesty

- Scoreboard = monitor telemetry — **not** PnL alpha
- `live_orders=False` · ClickHouse MCP banned · warehouse + startarb only
- Hold stays Hold until Pass 2
