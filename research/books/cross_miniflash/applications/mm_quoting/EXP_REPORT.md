# MM quoting — V vs continuation restore — EXP_REPORT

Generated: 2026-09-30T20:27:37.134679+00:00
Sample: days=['2026-09-04', '2026-09-05', '2026-09-06', '2026-09-07', '2026-09-08', '2026-09-09', '2026-09-10'] · symbols=['ETH', 'BTC'] · venues=['hyperliquid', 'deribit', 'kraken']
Events gated 10bps/ic5: **n=275** (cells complete 42/42)
Honesty: `research_sim_on_real_tape` · live_orders=`False` · alpha_claim=`False`

## Class shares
- Pooled share_V=0.771 · share_cont=0.142
- Early share_V=0.7978723404255319 · Late share_V=0.7569060773480663

## Class-stratified tape mo@5s (bps)
- **v_recovery** n=212 mean=-16.513118646584893 bootCI=[-19.290786683988884, -13.869944402595758]
- **continuation** n=39 mean=12.12256046244436 bootCI=[7.818386401432607, 17.115952988675517]
- **partial** n=24 mean=4.088961087151364 bootCI=[-0.2434395509298798, 9.690721831529636]

## Policy sims (continuation adverse = size×mo@5s on continuation events)
- `always_stay_wide`: cont_cost mean=3.03064011561109 boot=[1.9169484708315452, 4.281355312255864] | path_cost=-2.759452980709703 pnl_proxy=2.7689620659826457 inv_exc=4.520679751433782 exposure=0.25
- `always_restore`: cont_cost mean=12.12256046244436 boot=[7.667793883326181, 17.125421249023457] | path_cost=-11.037811922838811 pnl_proxy=11.075848263930583 inv_exc=18.08271900573513 exposure=1.0
- `oracle_class`: cont_cost mean=3.03064011561109 boot=[1.9169484708315452, 4.281355312255864] | path_cost=-11.086761918030836 pnl_proxy=12.275276233212345 inv_exc=16.7465741463306 exposure=0.7505454545454545
- `confirm_v_restore`: cont_cost mean=3.03064011561109 boot=[1.9169484708315452, 4.281355312255864] | path_cost=-9.282806175806858 pnl_proxy=11.179763186660734 inv_exc=14.907586378321856 exposure=0.5243636363636364
- `confirm_before_restore`: cont_cost mean=3.03064011561109 boot=[1.9169484708315452, 4.281355312255864] | path_cost=-8.585659307188394 pnl_proxy=10.40314439595031 inv_exc=14.094280978293057 exposure=0.4992727272727272
- `cont_protect`: cont_cost mean=3.03064011561109 boot=[1.9169484708315452, 4.281355312255864] | path_cost=-8.169843396206431 pnl_proxy=11.269555501353953 inv_exc=15.694539197021005 exposure=0.5028181818181817

## Time-split
- Early best path: [{'policy': 'always_stay_wide', 'cont_cost_mean': 2.1692356276794644, 'path_cost_mean': -2.287384041338085, 'pnl_proxy_mean': 2.320907629438412, 'inv_excursion_mean': 4.598000098981498, 'adverse_mean': 3.529493327791785, 'v_cost_mean': -3.5079325401358674, 'exposure_mean': 0.25, 'rank_metric': 2.1692356276794644, 'n': 94}, {'policy': 'oracle_class', 'cont_cost_mean': 2.1692356276794644, 'path_cost_mean': -9.269798131250782, 'pnl_proxy_mean': 10.26023594421192, 'inv_excursion_mean': 17.335319562976323, 'adverse_mean': 10.966379609084827, 'v_cost_mean': -14.03173016054347, 'exposure_mean': 0.759441489361702, 'rank_metric': 2.1692356276794644, 'n': 94}]
- Late best path: [{'policy': 'always_stay_wide', 'cont_cost_mean': 3.5004971090283403, 'path_cost_mean': -3.0074892030914007, 'pnl_proxy_mean': 3.0043804987431755, 'inv_excursion_mean': 4.480053806112102, 'adverse_mean': 4.081158990692187, 'v_cost_mean': -4.467885750064302, 'exposure_mean': 0.25, 'rank_metric': 3.5004971090283403, 'n': 181}, {'policy': 'oracle_class', 'cont_cost_mean': 3.5004971090283403, 'path_cost_mean': -12.041437806000015, 'pnl_proxy_mean': 13.334026215568503, 'inv_excursion_mean': 16.43723333419471, 'adverse_mean': 8.582307187450603, 'v_cost_mean': -17.87154300025721, 'exposure_mean': 0.7459254143646408, 'rank_metric': 3.5004971090283403, 'n': 181}]

## Decision
- **Promote** (`info.crash_v_vs_continuation / mm quoting restore`) — conf=med
- Why: class sep stable (V mo early/late=-14.0/-17.9; cont=8.7/14.0); stay-wide/confirm/cont_protect beat blind restore on continuation cost both cohorts
- Best pooled policy (excl. oracle): `always_stay_wide`
- Note: Promote = med quoting playbook (restore after V-confirm; stay wide on cont), not tradable fade. Ranked on continuation adverse cost, not pooled rebound capture. confirm_before_restore aligns with expanded_lab / strategy_lab best-risk stub.

## Identification
- Gate: SSM z*=6 + |ΔP|≥10bps + i_c≥5
- Labels: recovery@5s (V≥0.5, cont<0.2); causal policies use recovery@1–2s only
- Cost: size × signed tape markout (crash-direction); mid markout when TOB present
- Size schedule: wide=0.25×, restore=1.0× baseline
- Desk report: `out/RISK_REPORT.md`

## Figures
- `fig_policy_path_cost.png`
- `fig_class_markout.png`
- `fig_policy_rank.png`
- `fig_pnl_cumulative.png`
- `fig_inventory_risk.png`
- `fig_markout_ci.png`
- `fig_exposure_vs_cont.png`

## Blockers
- Dense mid markout still sparse on Kraken — tape is ceiling
- Oracle_class is upper bound only (not live)
- Fade-the-V remains **low** alpha until mid CI clears Promote for exec.tape_markout
- Event-study only; tick equity in strategy_lab / paper_harness
