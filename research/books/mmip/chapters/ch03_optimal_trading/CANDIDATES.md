# Ch.3 candidates — Promote / Hold / Kill (MM desk)

Universe: **HL ETH** warehouse trade tape (DENSE days) unless noted.  
Beta panel: **Deribit** 1m marks BTC/ETH/SOL.  
Label: **D** = descriptive metric · **T** = tradable signal · **E** = execution heuristic.

| id | type | definition (units) | desk use | decision | MM rationale |
|----|------|-------------------|----------|----------|--------------|
| `impact.rho_slope` | D | Mean signed mid move (bps) by \(\rho=\|Q_{\mathrm{net}}\|/V\) bucket | Pre-trade impact schedule / quote widen on high-\(\rho\) regimes | **Promote** (monitor) | Spearman \(\rho\!\leftrightarrow\!I_{\mathrm{dur}}\approx0.19\); high-\(\rho\) buckets ~7.5 bps vs ~0–1 at low \(\rho\). Tape **flow intensity**, not algo POV. |
| `impact.algo_pov_sim` | D/E | Simulated POV \(\pi=Q_{\mathrm{algo}}/V\); \(I_{\mathrm{model}}=\kappa\sigma\pi^\gamma\) on child fills | Child-order rate bounds / risk caps | **Promote** (heuristic) | Realized POV tracks \(\pi\); \(I_{\mathrm{model}}\) 0.57→2.55 bps as \(\pi\) 1%→20% (κ=0.9, γ=0.5). **Simulated**, not live TCA. |
| `impact.temp_perm` | D | \(I_{\mathrm{dur}}\) during window vs \(I_{\mathrm{perm}}\) to \(t_{\mathrm{end}}+T\); temp \(=I_{\mathrm{dur}}-I_{\mathrm{perm}}\) | Separate adverse selection (perm) from temporary pressure | **Promote** (monitor) | Mean temp only 0.23 bps @+5m (mostly persistent); still needed for posting/fade vs toxic-flow split |
| `impact.kappa_gamma` | D | OLS on $\log(I/\sigma)=\log\kappa+\gamma\log\rho$ | Daily param store for envelope model | **Hold** | $R^2\approx0.015$ on tape proxy — unusable for live sizing; keep book formula with conservative priors |
| `tca.is_arrival` | D | \(\mathrm{sign}\cdot 10^4(\mathrm{VWAP}-S_0)/S_0\) (bps) | TCA / broker scorecard input | **Hold** | Descriptive only until attributed to *our* child orders |
| `tca.vwap_track` | D | Window VWAP vs market VWAP (same) | VWAP-algo residual | **Hold** | Needs algo fill tape; market self-VWAP is tautological here |
| `sched.pov_envelope` | E | \(\rho\in[\rho_{\min},\rho_{\max}]\) from \(\kappa\sigma\rho^\gamma\) vs \(\sigma\sqrt{\Delta t}\) risk | Child-order rate bounds | **Promote** (heuristic) | Book 3.1.2 risk layer — pair with `impact.algo_pov_sim` π caps |
| `sched.ac_curve` | E | Almgren–Chriss \(x_n\) recurrence (A.28) for risk aversion \(\lambda\) | Parent schedule / hedging unwind path | **Hold** | Needs trusted \(\kappa,\gamma,V_n,\sigma_n\); paper toy OK, live later |
| `lsor.seek_inside_env` | E | Opportunistic take/post inside envelope | Liquidity-seeking / SOR | **Hold** | Connect to Ch.1 `frag.crossed_nbbo` + fill honesty; no OE in this exp |
| `lsor.latency_depth_haircut` | E | Haircut far-venue TOB size by RTT / cancel race | Quoting / SOR size | **Promote** (gate) | Book §3.3.2 Turquoise race — never count unvalidated depth |
| `style.extraday_idio` | D | \(r_i=\alpha+\beta_i r_m+\varepsilon_i\); var shares sys/idio | Match algo to investor style (sys vs idio) | **Promote** (monitor) | Deribit BTC/ETH/SOL panel: ETH β≈0.93, sys/idio ≈**67%/33%**; SOL β≈2.0, ~71%/29%. Short sample — document limits. |

**Promotion rule:** Promote monitors/heuristics with precise formulas + honesty labels. Never promote tape-flow \(\rho\) as a **tradable** edge or as certified single-agent participation capacity. Simulated POV is for **scheduling / risk caps**, not broker TCA.
