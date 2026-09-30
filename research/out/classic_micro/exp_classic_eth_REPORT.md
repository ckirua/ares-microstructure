# Classic microstructure — ETH

- Days: ['2026-09-28', '2026-09-29', '2026-09-30']
- Trades in window: **36,835** · mids: **63,382** (collector_tob)
- Quoted spread: **0.387** bps CI95 [0.385,0.388]
- Effective spread: **0.894** bps · Realized 1s: **0.003** bps
- Roll implied: **nan** (Kill)
- Markout 1s mean: **0.44468497206722396** CI [0.43523480005645465, 0.45579601594651925] · decision **Promote**
- Peak hour UTC: **0** · off/EU-aft ratio: **nan**
- Resilience n@1s: **613** · depth_ratio means: [1.2739402965502362, 1.1200128527023316, 0.8357156382499722, 1.1423733444331092] · hours_active=11

## Decisions

- `tox.markout_1s`: **Promote** — falsifier: CI includes ≤0 at 1s on held-out half, or flips sign by side
- `spread.effective_vs_quoted`: **Promote** — falsifier: effective ≪ 0.5·quoted persistently (bad side/mid join)
- `spread.roll`: **Kill** — falsifier: —
- `book.resilience`: **Promote** — falsifier: depth_ratio@1s ≈ 1 always (no impact events) or mid move uncorrelated
- `sess.utc_hour_share`: **Hold** — falsifier: hourly shares flat within bootstrap noise across days, or <12 active UTC hours in sample

JSON: `exp_classic_eth_summary.json`
