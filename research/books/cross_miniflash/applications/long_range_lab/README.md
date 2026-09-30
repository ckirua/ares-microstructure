# Long-range lab — crash-risk MM overlays + non-MM long holds

Two tracks on the longest clean Hyperliquid ETH panel (PIN-usable ~28 days):

1. **MM risk overlays** (`run_long_range.py`) — shadow maker equity / DD under kill-ladder / Nanex / V-confirm stubs. **Not** tradable alpha.
2. **Non-MM long-hold edges** (`run_long_edges.py`) — taker / pause rules using crash·SSM·V-class at **minutes–hours**, plus multi-event cluster regimes. Distinct from [`../edge_lab/`](../edge_lab/) mo@5s V-fade.

Sibling [`../expanded_lab/`](../expanded_lab/) owns the event-study risk scoreboard on the 7-day core. Detection via [`../paper_harness/`](../paper_harness/). ClickHouse MCP banned. No `mm_confr`.

## Open

| Artifact | Path |
|----------|------|
| **Notebook** | [`long_range_strategies.ipynb`](long_range_strategies.ipynb) |
| MM summary | [`out/summary.json`](out/summary.json) |
| **Non-MM edges report** | [`out/long_edges/EXP_REPORT.md`](out/long_edges/EXP_REPORT.md) |
| Non-MM summary | [`out/long_edges/summary.json`](out/long_edges/summary.json) |
| Non-MM figs | [`out/long_edges/figs/`](out/long_edges/figs/) |
| Per-day MM | [`out/days/`](out/days/) |

```bash
cd research/books/cross_miniflash/applications/long_range_lab
jupyter notebook long_range_strategies.ipynb
```

## Run / regenerate

```bash
cd research/books/cross_miniflash/applications/long_range_lab

# MM overlays (existing)
python3 run_long_range.py --workers 8
python3 run_long_range.py --smoke 3 --workers 4

# Non-MM minutes–hours edges (crash/SSM/V-class)
python3 run_long_edges.py --workers 8
python3 run_long_edges.py --smoke 3 --workers 4
python3 run_long_edges.py --rescore   # rebuild report from events.jsonl
```

Requires warehouse + startarb env (`startarb.env.ensure_env`).

## Non-MM edges (long hold)

| id | Role | Primary result (ETH long panel) |
|----|------|----------------------------------|
| `LR-v-slow-fade` | Causal V@2s → fade, hold 1–60m | **Kill** — short V rebound does not persist |
| `LR-cont-long-ride` | Causal cont@2s → ride, hold 1–60m | **Hold** — mean + at 15m, CI includes 0 |
| `LR-cluster-fade` | ≥3 SSM / 5m → fade anchor 15–60m | **Kill/Hold** — fade is anti-edge @15m/60m |
| `LR-cluster-ride` | Cascade → ride crash 15–60m | **Hold** @60m mean +46bps but n=12 underpowered |
| `LR-fire-pause` | Fire tier → pause; Δ\|mo\| vs observe | **Promote** @5m (Δ\|mo\|≈+20bps, n=194) |
| `LR-ssm-drift-ride` | Ride all gated SSM 5–30m | **Hold** — CI includes 0 |

Honesty gates: bootstrap CI · early/late sign-stable · RT 4bps friction · non-overlapping holds · causal recoveries @1–2s only.

## MM strategies (unchanged)

1. `baseline_maker` — no overlay  
2. `kill_ladder_maker` — kill-ladder protect  
3. `nanex_temp_pull` — Nanex∩SSM escalate / temporary pull  
4. `ladder_plus_v_restore` / `confirm_before_restore` — expanded_lab quote stubs  
5. `ladder_plus_confirm_before_restore` — combined best  

## Cadence honesty

- **Tape:** ms trade prints  
- **Book (MM track):** collector TOB → HL L2 snapshot / warehouse BBO or Deribit TOB — **not** sub-second L2  
- **Non-MM fills:** synthetic unit size × crash-signed tape markout at hold — research_sim, not live alpha  
- **MM fills:** trade print + `fill_i`
