# Estimators — EXP_REPORT (Pass 2.7 expand)

**Sample:** 34d · ETH+BTC+SOL · HL+Deribit+Kraken · **n_ok=204** · **n_mid=122**

## Clocks (fifth/fourth)

| Clock | Decision | median | CI95 | n |
|-------|----------|--------|------|---|
| calendar | **Kill** | 1.006 | [0.947, 1.065] | 204 |
| trade | **Kill** | 0.815 | [0.768, 0.853] | 204 |
| tick_bounce | **Kill** | 1.096 | [1.061, 1.129] | 203 |
| mid | **Hold** | 2.449 | [1.130, 3.777] | 122 |

Gate CI_lo>1.5 **not** met for mid (CI_lo=1.13). Venue split: HL 0.77 · Deribit 6.12 · Kraken spot 1.13.

## TSRV first_adj OOS

**Hold** — early CI_lo>0 but late CI through 0; overall CI through 0; ratio med=0.984. MC Kill of `cont.sparse_rv_only` unchanged.

Artifact: [`../../out/expand_panel/expand_panel.json`](../../out/expand_panel/expand_panel.json)
