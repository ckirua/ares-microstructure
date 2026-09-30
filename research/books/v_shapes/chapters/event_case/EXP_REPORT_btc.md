# Event case — EXP_REPORT (Pass 1+2)

## Stress day pick
- Venue: `hyperliquid` day `2026-09-30` hn=5m
- MinV=-74.7631 shape=Lambda sig5=True sig1=False
- Post-trough returns: {'ret_60s': -0.0015083586101560797, 'ret_300s': -0.0024001912663429437, 'ret_1800s': -0.001223140059510186}
- Geometric overlap: {'n_vshape_events': 5, 'n_nanex': 0}

## Regime proxy (Pass 2)
- BaU → trough → post: use pre/post return windows above; not an auction mechanism.
- Markout / maker-inventory analogue deferred to `liq_around_v` TOB join when available.

## Hold
- Causal taxpayer-loss / wealth-transfer ID: **Hold** (no crypto sovereign auction).

## Artifact
- `out/event_case/event_btc.json`
