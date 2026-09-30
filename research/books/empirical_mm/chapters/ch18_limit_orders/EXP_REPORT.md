# Ch.18–21 limit-order empirics — ETH

- Days: ['2026-09-28', '2026-09-29', '2026-09-30']
- TOB rows: **104,926** · trades overlap: **116,949**
- Touch@0ticks rate: **0.557** (mean touch 9138 ms) · @1tick **0.502**
- Size-touch fill_proxy@L0: **0.154** (q25=0.123, q75=0.037; size_mono=True)
- TOB cancel_proxy share: **0.776** · fill_proxy **0.023** (n=24273)
- Bid refill@1s: **0.151** (n=9121)
- Improve adverse markout 1s: **-0.2578** bps CI [-0.2726613605525385, -0.24337985364510206] · n=11928
- Parlour same ask↔sell r: {'n': 116949, 'r': 0.14068195027553243, 'lo': 0.1348556288286306, 'hi': 0.14672075794337713, 'alpha': 0.05}
- LO events: **79764** · λ̂=1.243/s · disc ac1=-0.119
- Resilience depth_ratio@1s (trade): **14.521897197956017** n=793
- Sandas L1: snaps=130 · pooled_decay=[1.0, 0.3863382504064159, 0.6193896186682093, 0.7236702771610288, 0.9392018921480578, 1.0410064263572667] · behind=0.7419212929481958
- Qty moment ceiling: var_infl(0.995/0.9)=**15.424** n=116949

## Decisions

- `cont.time_to_touch`: **Promote**
- `cont.size_touch_survival`: **Promote**
- `cont.tob_cancel_proxy`: **Promote**
- `cont.same_side_refill`: **Promote**
- `info.improve_markout`: **Kill**
- `disc.parlour_depth_side`: **Promote**
- `cont.lob_event_intensity`: **Promote**
- `disc.lob_event_ac1`: **Promote**
- `mm.book_resilience_lo`: **Promote**
- `disc.sandas_depth_moments`: **Promote**
- `disc.qty_moment_ceiling`: **Promote**
- `mm.queue_value_tick`: **Hold**
- `mm.limit_fill_hazard_oe`: **Hold**
- `theory.sandas_gmm_multilevel`: **Hold**
- `theory.stoll_cara_bid`: **Hold**
- `theory.cmsw_optimal_L`: **Hold**
- `theory.foucault_parlour_eq`: **Hold**

## Data ceilings

- **oe_fills:** startarb/oe is dry_gateway + SHM rings only — no historical own-order fill/cancel tape
- **mercat_collectors:** xarb_collector TOB is L0; no OE ack stream in results/xarb_md
- **l2_multilevel:** HL l2_snapshot_level depth>1 AVAILABLE (cache files=60, rows=6000, snaps≈130, ask_level_offset=20) — L1 moments ship; full Sandas GMM still blocked (no structural break-even ID)
- **warehouse_l2_cadence:** ~snapshot/delta rebuild ~5s — not ms HFT book

## Theory-only (explicit gaps)

- True OE fill/cancel hazard (needs own-order feedback) — public-tape proxies shipped
- Sandas GMM multilevel break-even schedule (L1 moments shipped; structural GMM Hold)
- Stoll CARA bid markdown (unobserved risk aversion / inventory)
- CMSW optimal limit price via EU (agent preferences)
- Foucault/Parlour structural equilibrium / welfare
- Seppi dealer quantity-improvement (no hybrid specialist on HL)
- Multi-level queue position / time priority (L0/Lk size ≠ queue rank)

JSON: `exp_ch18_eth_summary.json`

## Figures

- `fig_time_to_touch.png`
- `fig_size_touch_survival.png`
- `fig_cancel_vs_fill.png`
- `fig_sandas_depth.png`
- `fig_resilience_refill.png`
- `fig_parlour_lob_clocks.png`
