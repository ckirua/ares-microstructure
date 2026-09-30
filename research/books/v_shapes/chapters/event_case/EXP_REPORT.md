# Event case — EXP_REPORT (Pass 1+2)

## Stress day pick
- Venue: `deribit` day `2026-09-20` hn=5m
- MinV=-93.0565 shape=V sig5=True sig1=True
- Post-trough returns: {'ret_60s': 0.002276509169839791, 'ret_300s': 0.007181568491014367, 'ret_1800s': 0.00791622294648242}
- Geometric overlap: {'n_vshape_events': 8, 'n_nanex': 0}

## Regime proxy (Pass 2)
- BaU → trough → post: use pre/post return windows above; not an auction mechanism.
- Markout / maker-inventory analogue deferred to `liq_around_v` TOB join when available.

## Hold
- Causal taxpayer-loss / wealth-transfer ID: **Hold** (no crypto sovereign auction).

## Artifact
- `out/event_case/event_eth.json`
