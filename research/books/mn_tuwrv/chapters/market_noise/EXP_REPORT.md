# Market noise — EXP_REPORT (Pass 2.7 expand)

## Coverage
- hyperliquid: n=33 quoted (collector ∪ l2_rebuild)
- deribit: n=82 quoted (l2_snapshot_level)
- kraken: n=29 (quoted spot L2=8, proxy=21)

## noise_std vs spread_bps
- Spearman ρ = **0.016** CI95=[-0.169, 0.168] n=144
- shuffle_p = 0.8375 · block_shuffle_p = 0.7462
- time-split: early ρ≈-0.29 · late ρ≈0.22 · **same_sign=False**

## Gate
- `liq.noise_vs_spread` → **Hold** — ρ near 0; CI through 0; early/late disagree.

## Mid-clock (shared panel)
- `cont.noise_mid_clock` → **Hold** — med=2.449 CI=[1.130, 3.777] n=122

Artifact: [`../../out/expand_panel/`](../../out/expand_panel/)
