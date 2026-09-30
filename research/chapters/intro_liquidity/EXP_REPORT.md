# Intro liquidity — EXP_REPORT

**Run:** `python3 research/scripts/exp_intro_liquidity.py --symbol ETH`  
**Out:** `research/out/intro_liquidity/`

## Headline (ETH collector TOB)

| Metric | Value |
|--------|-------|
| Rows | ~438k |
| Venues | HL, Lighter, RiseX |
| FEI(size) / FEI(updates) | ~0.38 / ~0.73 |
| Max role-blur L1 | ~0.78 (HL size-heavy, Lit update-heavy) |
| HL spread train/test stable | Yes |

## Desk read

Lighter prints **high update share / low size share** → classic role-blur / flicker: treat as unstable make venue unless size confirms. HL carries size; RiseX intermediate. Spread CIs tight — usable cost floor.

## Promote

`liq.quoted_spread_bps`, `liq.depth_imbalance`, `liq.role_blur_l1`
