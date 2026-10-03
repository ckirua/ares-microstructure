# paper_shadow — NOTES

**Book:** Huang–Ranaldo–Schrimpf–Somogyi (Nov 2021)  
**Status:** `pass1` (scaffold + dry-run)  
**Path:** [`../../applications/paper_shadow/`](../../applications/paper_shadow/)  
**Honesty:** Monitor/Hold only · `live_orders=false` · never TOB-cross α

Page cites = PDF viewer / file page index (cover = p.1).

---

## 1. What the harness mirrors from paper objects

Living warehouse-day shadow (pattern after `v_shapes/applications/paper_live`). Each poll / day replay computes the same Pass-1 objects as the research scripts and tags them **Monitor/Hold** — telemetry only.

| Paper object | PDF | Shadow monitor | Gate label |
|--------------|-----|----------------|------------|
| VLOOP (eq 2) | p. 10 | `vloop_cross_venue` on latency-aligned TOB | feeds PIM |
| TCOST (eq 2) | p. 10 | `tcost_from_spreads` (sum relative half-spreads) | feeds PIM |
| PIM (eq 3) | p. 11 | `pim_from_components` (VLOOP+\|TCOST\|, VLOOP>0) | `risk.pim_cross_venue` **Hold** |
| VLOOP↔TCOST commonality | p. 12 | corr on finite grid | `info.vloop_tcost_commonality` **Hold** |
| DCM = PC1 constraints | pp. 14–16 | `dcm_pc1` of public proxies | `risk.dcm_pc1` **Hold** |
| Elasticity / regime | pp. 13–17 | `regime_split_corr` + `logistic_G` | `liq.elasticity_regime` **Hold** |
| Bank VaR / CDS | p. 14 | — | `risk.bank_cds_var` **Kill** |
| Executable triangular arb | p. 8 fn.5 | — | `alpha.tob_cross_arb` **Kill** |

**Not mirrored (parked):** full LSTAR Eqs (4)–(5) (unidentified short tape); §4 DGP simulator; §5 GIV second stage.

---

## 2. I/O & clocks

- Config: primary cell HL ETH; venues Deribit/Kraken; `dt_s`, `bucket_s`, day-completeness gates (`config.yaml`).  
- Outputs: `logs/shadow.log`, `out/events.jsonl`, `out/SHADOW_BOARD.md`, per-day `summary.json`.  
- Clock: UTC warehouse day; same alignment spirit as CLS hourly (paper p. 8) but 5s TOB grid.

---

## 3. Pass checklist

### Pass 1
- [x] Wire PIM/DCM/elasticity monitors to `cdme` lib
- [x] Dry-run one historical day; `live_orders=false` hard refuse
- [x] Gate labels Hold/Kill only

### Pass 2
- [ ] Promote path only after sibling falsifiers; still no orders
