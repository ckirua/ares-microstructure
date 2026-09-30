# Paper-trade harness — risk-policy overlay (shadow only)

**Class:** risk-policy · **not** PnL alpha  
**Primary cell:** Hyperliquid ETH (venue-local)  
**Pipeline:** gated SSM detect → kill-ladder actions → shadow fills → daily risk report  

Desk context: [`../../TRADING_APPLICATIONS.md`](../../TRADING_APPLICATIONS.md) §1.1 · [`../kill_ladder/`](../kill_ladder/) · [`../strategy_lab/`](../strategy_lab/) · lib [`../../../lib/crash.py`](../../../lib/crash.py).

**No live order submission.** ClickHouse MCP is banned.

---

## What it does

1. **Detect** — warehouse trade tape via `scripts/_data.load_day_trades` + `research.lib.crash` SSM (`σ_m` floor, z*=6) gated at **10 bps / i_c≥5**; Nanex∩SSM nest flag.
2. **Ladder** — within-gated z percentiles + rolling intensity + Nanex escalate → tiers `observe → widen → size_cap → halt` (same rule as `applications/scripts/_common.ladder_tier`).
3. **RISK_GATE_STACK** — combined throttle (`harness/risk_stack.py`): ladder size mult ∩ **`nest_hard_pause`** (Nanex∩SSM → 0) ∩ **`fire_pause_5m`** (300s from fire → 0). Max severity wins.
4. **Shadow fills** — strategy_lab maker sim: baseline vs kill-ladder vs **risk_gate_stack**; fill at **tape print**; friction haircut; inventory mark-to-mid.
5. **Report** — `actions.jsonl` (incl. `kind: fire_pause_5m`) + `RISK_REPORT.md` / `.html` + PNGs + multi-day `RISK_ROLLUP.md` (baseline vs full stack).

---

## How to run (paper only)

```bash
cd /home/dev/srv/ares-microstructure/research/books/cross_miniflash/applications/paper_harness

# one UTC day (HL ETH)
python3 run_paper_day.py --day 2026-09-04

# Phase-4 research window → out/RISK_ROLLUP.md (baseline vs full stack)
python3 run_paper_day.py --panel-days --extra-venues deribit,kraken

# optional Deribit/Kraken detect+log (same day); shadow stays on primary venue
python3 run_paper_day.py --day 2026-09-04 --extra-venues deribit,kraken

# unit tests + one historical dry-run
python3 -m pytest tests/test_paper_harness.py -q
python3 -m pytest tests/test_paper_harness.py -q -m slow   # needs warehouse day
```

Requires startarb/warehouse env (`startarb.env.ensure_env`) — same as other cross_miniflash apps.

---

## Outputs

| Artifact | Path |
|----------|------|
| Action log | `out/<day>_<venue>_<symbol>/actions.jsonl` |
| Risk report (md) | `out/<day>_<venue>_<symbol>/RISK_REPORT.md` |
| Risk report (html) | `out/<day>_<venue>_<symbol>/RISK_REPORT.html` |
| Summary JSON | `out/<day>_<venue>_<symbol>/summary.json` |
| Figures | `out/<day>_<venue>_<symbol>/figs/*.png` (incl. `stack_regime_counts.png`) |
| Multi-day rollup | `out/rollup.json` · `out/RISK_ROLLUP.md` |

Config: [`config.yaml`](config.yaml) (`nest_hard_pause`, `fire_pause_5m_s`, `run_risk_gate_stack`, ladder breaks, size mult, friction, gate).

Stack spec: [`../RISK_GATE_STACK.md`](../RISK_GATE_STACK.md).

---

## Wired vs not wired

| Component | Status |
|-----------|--------|
| Warehouse trade tape (HL / Deribit / Kraken) via startarb loaders | **Wired** |
| `research.lib.crash` SSM + Nanex + severity gate | **Wired** |
| Kill-ladder tiers (shared `_common.ladder_tier`) | **Wired** |
| `nest_hard_pause` + `fire_pause_5m` combined throttle | **Wired** (`risk_stack.py`) |
| strategy_lab shadow maker + book asof (TOB / l2_rebuild) | **Wired** |
| Collector TOB under `ares-startarb/results/xarb_md/tob` | **Used if day exists** (Phase-4 days usually miss → warehouse BBO) |
| startarb `shadow_live` / xarb poll loop | **Not wired** (different alpha lane; paper harness is crash risk-policy) |
| mercat / gateway live path | **Not used** |
| Live order submission | **Never** — shadow fills only |
| ClickHouse MCP | **Banned** |

Cadence honesty: warehouse BBO can lag ms tape by seconds–minutes; fills still book at the trade print.

---

## Report metrics

- Fires by tier + Nanex∩SSM escalate / nest_hard count  
- Adverse tape \|mo\| @5s among fire + avoided-mo proxy (−Δfire_fills × \|mo\|)  
- Inventory / marked equity (baseline vs ladder vs **stack**) + **Δ fills / Δ fire fills**  
- Fills by ladder / stack regime (incl. `fire_pause_5m`, `nest_hard_pause`)  
- FP V-recovery rate among fire (halt overkill cost)  
- Promote ID cross-links (`risk.ssm_severity_gate_10bps`, `info.nanex_subset_of_ssm`, …)

**Fill-model honesty:** when warehouse/collector book median Δt > `stale_book_s` (default 5s), fill eligibility falls back to **tape-proxy** touch (`bid=ask=mid=px`, half-spread **0**) so kill-ladder size/pull binds on the print clock. Fill **price** remains the trade print (no stale-touch fantasy). Without this fallback, minute-scale L2 yields fills only in `regime=none` and overlay ≡ baseline. Positive proxy half-spread makes prints unreachable → zero fills.

**Inventory soft-cap:** default `max_inventory: 10` (research). ±2 coins historically nullified crash-window fills (cap hit in minutes). Not a live risk limit.

**Crash-window scoreboard:** Δ fills / qty / equity increment inside widen·size_cap·halt — desk metric for whether the overlay binds. Day equity Δ is labeled risk-policy, not tradable PnL. 
