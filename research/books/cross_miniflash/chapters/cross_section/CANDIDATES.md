# Cross-section — CANDIDATES

| id | type | lenses | decision | falsifier |
|----|------|--------|----------|-----------|
| `xsec.size_reduces_severity` | D | liq, risk | **Kill** | Time-split β(logN) sign flip; univariate OLS \|t\|≪2 |
| `info.vpin_x_size_severity` | D | info, risk, cont | **Hold** | Interaction t collapses out-of-sample / ex-ante n tiny |
| `risk.exante_amihud_severity` | D | risk, liq | **Hold** | n_pred=20; needs wider panel bootstrap |
| `xsec.multi_coin_eth_btc_parity` | D | disc | **Hold** | Only 1 week; SOL not in complete tri-venue set |

**Kill (`xsec.size_reduces_severity`):** Paper’s plain MCap→smaller |ΔP| does **not** survive crypto vertical slice (R²≈0.02; time-split sign unstable). Do not Promote notional-as-MCap alone.

**Hold (`info.vpin_x_size_severity`):** Conditional size×toxicity is the interesting object (t≈3 on interact). Label **risk/info monitor**. Needs hardening Pass (bootstrap + more days) before Promote.

**Hold (`risk.exante_amihud_severity`):** Direction paper-consistent (illiquid→worse), but n=20 — Hold.

## Phase 4 harden

Program-wide bootstrap/time-split applied (`scripts/exp_final_hardening.py` → `out/phase4_hardening/hardening_gates.json`). Gate note: primary **10bps/ic5**; frag share also **5bps/ic3**.
| id | Phase4 decision | harden why |
|----|-----------------|------------|
| `info.vpin_x_size_severity` | **Hold** | interact t≈2.9 in-sample; time-split size sign unstable; needs wider OOS before Promote |
| `risk.exante_amihud_severity` | **Hold** | n_pred=20; Amihud t≈−2.5 direction OK but underpowered |
| `xsec.size_reduces_severity` | **Kill** | R²≈0.02; time-split β sign flip early=0.0010321979810437483 late=-0.008326975452582236 |
