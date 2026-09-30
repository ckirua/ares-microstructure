# Introduction — Liquidity, Best Execution, Role Blur

PDF pp. 28–55 (Lehalle & Laruelle). Vocabulary chapter upgraded to **extractable MM features**.

## Book themes → desk objects

| Theme | Operational definition | Feature id |
|-------|------------------------|------------|
| Liquidity is multi-dimensional | Quoted spread (bps), L0 size, update intensity | `liq.quoted_spread_bps`, `liq.update_hz` |
| Best execution under fragmentation | Cross-venue size vs update shares; FEI | `frag.*` (Ch.1), `liq.role_blur_l1` |
| Maker / taker role blur | Same venue can dominate updates while thin on size | `liq.role_blur_l1` = \|upd_share − size_share\| |
| Inventory / skew | L0 imbalance \((b-a)/(b+a)\) | `liq.depth_imbalance` |

## Experiment hygiene

- Data: collector TOB (`ares-startarb/results/xarb_md/tob`), no ClickHouse.
- Stats: bootstrap CI on spreads/imbalance; chronological 70/30 train–test for HL spread stability.
- Falsifiers: see `CANDIDATES.md`.

## Status

`exp_run` — script `research/scripts/exp_intro_liquidity.py`, outputs `research/out/intro_liquidity/`.
