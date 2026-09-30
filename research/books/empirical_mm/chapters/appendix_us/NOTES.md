# Appendix — US equity markets (ideas that transfer to crypto)

**PDF:** pp. 165–187 · **Status:** `park` (intentional — not unfinished)  
**Raw:** [`../../_raw/app_us.txt`](../../_raw/app_us.txt)  
**Coverage:** flagged in [`../../docs/COVERAGE.md`](../../docs/COVERAGE.md)

## Why this stays parked

Institutional NYSE/Nasdaq history (specialist, SuperMontage, Manning, preferencing, decimalization chronology) is **not** our empirics target. Public HL/Lit tape cannot identify specialist agency, parity rules, or SEC/CFTC splits. Opening a US-equity experiment stream would be cargo-culting the appendix.

**Do:** keep the transfer table below as a design checklist when mapping motifs → crypto analogues.  
**Do not:** add `scripts/exp_appendix_us.py`, notebooks, or figures for this package.  
**Do not:** commit appendix PDF text; keep `_raw/app_us.txt` local.

Empirics that *are* the crypto analogues already live elsewhere:

| Motif class | Empirics owner |
|-------------|----------------|
| Fragmentation / montage / linkages | `ch17_discovery` (IS / Epps / jumps) + mmip |
| LOB fill / queue / touch | `ch18_limit_orders` |
| Session breaks / starting values | `ch09_estimation` doctrine |
| Inventory / dual-trading blur | `ch10_trades` notes + mmip role blur |

---

## Transferable design ideas

| US equity motif | Crypto / HL–Lit analogue | Where we use it |
|-----------------|--------------------------|-----------------|
| Dual trading (broker + dealer conflict) | Venue operator / market-maker / liquidator role blur | mmip `liq.role_blur_l1` |
| Specialist as agent for LOB + residual quote | Maker inventory + queue priority; no single specialist | ch10 inventory notes; mmip depth imbalance |
| Time priority / parity after first fill | Queue position, post-only, latency races | mmip latency depth haircut |
| Opening/closing single-price call | Auction windows / funding settle / infrequent batch crosses | Session breaks in Ch.9 starting-values doctrine |
| Automatic small-order execution vs crowd | IOC/marketable limit vs resting liquidity | Part III LOB fill empirics (`ch18`) |
| Manning / preferencing / internalization | RFQ, OTC internalization, payment-for-order-flow analogues | SOR fairness — Hold |
| Nasdaq quote montage → SuperMontage | Multi-venue TOB montage (collector panel) | ch17 info shares / Epps |
| Fragmentation + intermarket linkages | HL vs Lit vs RX mid cointegration | ch17 **Promote** IS / Epps / jump concordance |
| Regulation split (SEC vs CFTC etc.) | Venue rules + chain governance heterogeneity | Documentation only |
| Tick / decimalization → order splitting | Tick size vs mid; POV splitting | Kyle Ch.6 + mmip POV |

## Pointers

- Price discovery: [`../ch17_discovery/`](../ch17_discovery/)  
- Limit-order empirics: [`../ch18_limit_orders/`](../ch18_limit_orders/)  
- mmip fragmentation: [`../../../mmip/chapters/`](../../../mmip/chapters/)  
- Front door: [`../ch00_overview/`](../ch00_overview/)
