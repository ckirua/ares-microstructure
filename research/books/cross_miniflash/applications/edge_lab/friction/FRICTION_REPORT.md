# Friction falsifier — COST / half-spread sensitivity

Generated: 2026-09-30T20:35:33.021455+00:00
Panel: n=275 · mo_5s/labels from `panel_cache` · tier=event_panel_join
Honesty: research_sim · not live alpha · no MM polish · ClickHouse MCP off

## Verdict: survive ≥1bp half-spread

- **Survive @1bp:** `TI-v-fade`, `TI-cont-ride`, `TI-int-halt`
- **Die @1bp:** none (oracle labels)

Max surviving half-spread (bps): `{"TI-v-fade": 5.0, "TI-cont-ride": 2.0, "TI-int-halt": 5.0}`

![kill-grid](figs/fig_kill_grid.png)

## Kill grid (oracle labels · RT=2×half-spread for taker; one-way for halt)

| idea | 0bp | 0.5bp | 1bp | 2bp | 5bp |
|------|------|------|------|------|------|
| `TI-v-fade` | +16.5 SURVIVE | +15.5 SURVIVE | +14.5 SURVIVE | +12.5 SURVIVE | +6.5 SURVIVE |
| `TI-cont-ride` | +12.1 SURVIVE | +11.1 SURVIVE | +10.1 SURVIVE | +8.1 SURVIVE | +2.1 DIE |
| `TI-int-halt` | +6.5 SURVIVE | +6.0 SURVIVE | +5.5 SURVIVE | +4.5 SURVIVE | +1.5 SURVIVE |

### Causal aux (recovery@2s — not primary)

- `TI-v-fade_causal` @1bp: **SURVIVE** net=+13.63 [9.38,17.59] n=117
- `TI-cont-ride_causal` @1bp: **DIE** net=-0.83 [-5.65,3.88] n=64

### Notes

- `TI-v-fade`: fade `label=v_recovery`; net = −mo_5s − 2c
- `TI-cont-ride`: ride `label=continuation`; net = +mo_5s − 2c
- `TI-int-halt`: fire={widen,size_cap,halt}; alive iff Δ|mo| fire−obs > c and CI>0 (risk bar)
- Oracle labels are primary (per brief). Causal cont-ride dies at all costs — fade-dominated.
- `TI-cont-ride` oracle dies only at 5bp half-spread (RT=10bps).

## How to run

```bash
cd research/books/cross_miniflash/applications/edge_lab/friction
python3 run_friction.py
```
