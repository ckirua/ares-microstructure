# Paper exec-throttle — EXP_REPORT

## Honesty
- Class: `exec_throttle_risk_sim` · live_orders=False · alpha_claim=False
- Fills: synthetic_maker_participation_x_tape_print_plus_friction
- Promote scope: **exec_throttle_risk_not_tradable_alpha** (Hold as alpha always)
- Primary monitors: MinV / EGARCH bands (Promote stack) + calendar Ridge as paper-only secondary
- Tick `y_tick_20`: **Hold** — never sized
- ClickHouse MCP banned

## Sample
- ETH days=['2026-09-04', '2026-09-05', '2026-09-06', '2026-09-07', '2026-09-08', '2026-09-09', '2026-09-10', '2026-09-14', '2026-09-15', '2026-09-16', '2026-09-17', '2026-09-18', '2026-09-19', '2026-09-20', '2026-09-21', '2026-09-22', '2026-09-25', '2026-09-26', '2026-09-27', '2026-09-30']
- BTC days=['2026-09-04', '2026-09-05', '2026-09-06', '2026-09-07', '2026-09-08', '2026-09-09', '2026-09-10', '2026-09-15', '2026-09-18', '2026-09-25', '2026-09-26', '2026-09-27', '2026-09-30']
- train=['2026-09-04', '2026-09-05', '2026-09-06', '2026-09-07', '2026-09-08', '2026-09-09', '2026-09-10', '2026-09-14', '2026-09-15', '2026-09-16', '2026-09-17', '2026-09-18'] · test(OOS)=['2026-09-19', '2026-09-20', '2026-09-21', '2026-09-22', '2026-09-25', '2026-09-26', '2026-09-27', '2026-09-30']
- n_ok_dayvenue=99 · n_breach_dayvenue=16
- venues=['hyperliquid', 'deribit', 'kraken'] · cal_thresh_abs=0.0002007109070232962

## Knobs
- size_mult=0.35 · widen_bps=5.0 · pov=0.2 · take_pause=True
- cal boost: size=0.22 widen=8.0 pov=0.1 @ |score|≥q90
- friction base=2.0 bps · base_size=0.25

## OOS risk / PnL (throttle − always_on)
- all: Δmax_dd={'mean': 2.380758234212206, 'lo': -8.270923266180034, 'hi': 7.250310978126962, 'n': 36} · Δadverse_mo30={'mean': 0.0014121358114352026, 'lo': 0.0, 'hi': 0.0024180441757507562, 'n': 36} · Δpnl={'mean': 2.380947935884857, 'lo': -8.270923266180034, 'hi': 7.250510164883247, 'n': 36}
- breach-only: Δmax_dd={'mean': 17.14145928632788, 'lo': -75.80812122106872, 'hi': 70.22538386792658, 'n': 5} · Δadverse_mo30={'mean': 0.010167377842333458, 'lo': 0.004401993392844528, 'hi': 0.014693676653755539, 'n': 5} · n=5
- early: {'n': 12, 'd_max_dd_throttle': {'mean': 0.5614984956109765, 'lo': -24.812769798540103, 'hi': 12.64988664255361, 'n': 12}, 'd_adverse_mo_throttle': {'mean': 0.003720121751777753, 'lo': 0.0, 'hi': 0.006122365272398141, 'n': 12}, 'd_pnl_throttle': {'mean': 0.5614984956109765, 'lo': -24.812769798540103, 'hi': 12.64988664255361, 'n': 12}, 'd_part_throttle': {'mean': -6.829381431874601e-05, 'lo': -0.00013661911561597164, 'hi': 1.4120349991502842e-07, 'n': 12}, 'd_abs_inv_throttle': {'mean': 0.006594377237909991, 'lo': 0.0, 'hi': 0.014080790178042035, 'n': 12}, 'd_max_dd_cal': {'mean': 1.2934302920248228, 'lo': -24.812769798540103, 'hi': 14.113750235381303, 'n': 12}, 'd_adverse_mo_cal': {'mean': 0.0038796906902693884, 'lo': 0.0, 'hi': 0.006441503149381411, 'n': 12}, 'd_pnl_cal': {'mean': 1.2934302920248228, 'lo': -24.812769798540103, 'hi': 14.113750235381303, 'n': 12}, 'd_max_dd_placebo': {'mean': -19.23095827767626, 'lo': -47.98016793832843, 'hi': 0.0, 'n': 12}, 'd_adverse_mo_placebo': {'mean': 0.002374039312379117, 'lo': 0.0, 'hi': 0.004306704063634166, 'n': 12}}
- late: {'n': 24, 'd_max_dd_throttle': {'mean': 3.29038810351282, 'lo': 0.0, 'hi': 9.871164310538461, 'n': 24}, 'd_adverse_mo_throttle': {'mean': 0.0002581428412639271, 'lo': 0.0, 'hi': 0.0007744285237917814, 'n': 24}, 'd_pnl_throttle': {'mean': 3.2906726560217976, 'lo': 0.0, 'hi': 9.872017968065393, 'n': 24}, 'd_part_throttle': {'mean': -4.842648454942098e-05, 'lo': -0.00014527945364826295, 'hi': 0.0, 'n': 24}, 'd_abs_inv_throttle': {'mean': 5.962432914068579e-05, 'lo': 0.0, 'hi': 0.00017887298742205737, 'n': 24}, 'd_max_dd_cal': {'mean': 4.50865146355856, 'lo': 0.0, 'hi': 13.525954390675679, 'n': 24}, 'd_adverse_mo_cal': {'mean': 0.00023535060558218154, 'lo': 0.0, 'hi': 0.0007060518167465446, 'n': 24}, 'd_pnl_cal': {'mean': 4.508928990236352, 'lo': 0.0, 'hi': 13.526786970709054, 'n': 24}, 'd_max_dd_placebo': {'mean': 0.3164273878106201, 'lo': -1.595232140356984, 'hi': 2.5445143037888442, 'n': 24}, 'd_adverse_mo_placebo': {'mean': 8.93636598513492e-05, 'lo': 0.0, 'hi': 0.0001982964397481711, 'n': 24}}
- placebo: Δmax_dd={'mean': -6.19936783401834, 'lo': -14.828390414099509, 'hi': 0.7763992149379343, 'n': 36} · Δadverse={'mean': 0.0008509222106939385, 'lo': 3.3799399754625486e-05, 'hi': 0.0017425729524507448, 'n': 36}

## Gate rollup
- **Kill** `exec.minv_breach_throttle` — OOS Δmax_dd=17.14 boot={'mean': 17.14145928632788, 'lo': -75.80812122106872, 'hi': 70.22538386792658, 'n': 5}; Δadverse_mo30=0.01017 boot={'mean': 0.010167377842333458, 'lo': 0.004401993392844528, 'hi
- **Hold** `exec.minv_throttle_cal_join` — cal-join OOS Δdd=24.75 Δadv=0.01044 vs plain Δdd=17.14 Δadv=0.01017; calendar Ridge Monitor-only paper weight
- **Hold** `exec.minv_throttle_as_alpha` — PnL Δ OOS=2.381 — flat/negative expected; never Promote as sized alpha. y_tick_20 remains Hold.
- **Hold** `exec.placebo_throttle` — placebo Δdd=-6.199 Δadv=0.0008509 vs real Δdd=17.14 Δadv=0.01017

## Artifacts
- `out/paper_throttle/summary.json`
- `out/paper_throttle/delta_rows.json`
- `out/paper_throttle/gates.json`
- `out/paper_throttle/figs/breach_timeline.png`, `oos_risk_deltas.png`, `cumulative_risk.png`,
  `throttle_state_path.png`, `policy_slice_bars.png`, `pnl_vs_risk.png`
