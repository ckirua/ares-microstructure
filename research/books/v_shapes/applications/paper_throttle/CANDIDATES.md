| id | type | lenses | decision | evidence |
|----|------|--------|----------|----------|
| `exec.minv_breach_throttle` | D | exec, risk, mm | **Kill** | OOS Δmax_dd=17.14 boot={'mean': 17.14145928632788, 'lo': -75.80812122106872, 'hi': 70.22538386792658, 'n': 5}; Δadverse_mo30=0.01017 boot={'mean': 0.010167377842333458, 'lo': 0.004401993392844528, 'hi': 0.014693676653755539, 'n': 5}; Δpnl=2 |
| `exec.minv_throttle_cal_join` | D | exec, info, risk | **Hold** | cal-join OOS Δdd=24.75 Δadv=0.01044 vs plain Δdd=17.14 Δadv=0.01017; calendar Ridge Monitor-only paper weight |
| `exec.minv_throttle_as_alpha` | D | exec | **Hold** | PnL Δ OOS=2.381 — flat/negative expected; never Promote as sized alpha. y_tick_20 remains Hold. |
| `exec.placebo_throttle` | D | exec | **Hold** | placebo Δdd=-6.199 Δadv=0.0008509 vs real Δdd=17.14 Δadv=0.01017 |
