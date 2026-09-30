# EXP_REPORT — Ch.3 Optimal Organisations / Trading Impact (MM memo)

**Classification:** Research memo · paper only · no orders  
**Authors/plane:** ares-microstructure ← startarb warehouse `trade` (HL ETH)  
**Date:** 2026-09-29  
**Decision summary:** Promote `impact.rho_slope`, `impact.temp_perm`, `sched.pov_envelope`,
`lsor.latency_depth_haircut`. Hold `impact.kappa_gamma` / AC curve / TCA fill metrics.
**Iterate (2026-09-30):** Promote `impact.algo_pov_sim` + `style.extraday_idio` — see
[`EXP_REPORT_POV_IDIO.md`](EXP_REPORT_POV_IDIO.md) / `out/ch03_pov_idio/`.

---

## 1. Executive takeaway

On HL ETH DENSE days (2026-09-14, 2026-09-15, 2026-09-16, 2026-09-25, 2026-09-26), **1424** non-overlapping 5m windows show signed mid impact rising with tape order-flow intensity $\rho=|Q_{\mathrm{net}}|/V$ (Spearman $\rho\!\leftrightarrow\!I_{\mathrm{dur}}\approx\mathbf{0.19}$, $p\sim10^{-12}$). Bucket means: low-$\rho$ $I_{\mathrm{dur}}\sim0$–1 bps vs high-$\rho$ ($\ge0.4$) $\sim$**7.5 bps**. Mean temporary component ≈ **0.23 bps** (weak average reversion at $+5$m; most impact looks persistent on this horizon). Power-law $I=\kappa\sigma\rho^\gamma$ fit is **weak** ($\hat\gamma\approx0.17$, $R^2=0.015$) — do **not** trust $\hat\kappa,\hat\gamma$ for sizing. Treat $\rho$ as **descriptive flow intensity**, not single-algo POV capacity. Cross-ref Ch.2: schedule against `vol.curve_intraday` (peak ~18 UTC, U≈0.56).


## 2. Definitions & formulas

| Symbol | Definition | Units / clock |
|--------|------------|---------------|
| $\rho$ | $\|Q_{\mathrm{net}}\|/V$, $Q_{\mathrm{net}}=\sum s_i q_i$ | share ∈ [0,1]; **proxy** |
| $I_{\mathrm{dur}}$ | $\mathrm{sign}(Q_{\mathrm{net}})\cdot 10^4(S_{\mathrm{end}}-S_0)/S_0$ | bps |
| $I_{\mathrm{perm}}$ | same to first post window end ($+T$) | bps |
| $I_{\mathrm{temp}}$ | $I_{\mathrm{dur}}-I_{\mathrm{perm}}$ | bps |
| IS-arrival | $\mathrm{sign}\cdot 10^4(\mathrm{VWAP}-S_0)/S_0$ | bps (D) |
| Model | $I=\kappa\sigma\rho^\gamma$ (book 3.1.1 / A.6) | fit on $I_{\mathrm{dur}}>0$ |

**Honesty:** No proprietary meta-orders. Side is aggressor from warehouse tape. Price path = trade prints (not BBO mid). Warehouse tape is research-grade / may be tail-windowed per day shard — see DATA_PATHS.md.

## 3. Data & method

| Item | Detail |
|------|--------|
| Source | `startarb.data.trades.load_trade_tape('hyperliquid','ETH')` |
| Days | ['2026-09-14', '2026-09-15', '2026-09-16', '2026-09-25', '2026-09-26'] (DENSE) |
| Trades | n=917074 |
| Windows | 5m primary; 15m secondary; non-overlapping |
| Post horizon | +1× window for permanent |
| Not used | ClickHouse; own fills; multi-venue SOR OE |
| Baseline | Book Fig 3.3–3.4 (CAC40 broker fills) — qualitative only |

## 4. Results

### 5m windows

- n windows: **1424**
- mean ρ: **0.476**
- mean $I_{\mathrm{dur}}$: **6.19 bps**
- mean $I_{\mathrm{perm}}$: **5.97 bps**
- mean $I_{\mathrm{temp}}$: **0.23 bps**
- mean IS-arrival: **4.75 bps**

### Power-law fit (5m, $I_{\mathrm{dur}}>0$, $\rho\ge 0.05$)

- $\hat\kappa$ = **0.8908**, $\hat\gamma$ = **0.165**, $R^2$ = 0.015, n=918
- Square-root reference $\gamma=0.5$: away from classic $\sqrt{\rho}$ heuristic.

### Impact by $\rho$ bucket (5m)

| ρ range | n | mean ρ | $I_{dur}$ | $I_{perm}$ | $I_{temp}$ |
|---------|---|--------|-----------|------------|------------|
| [0.00,0.05) | 85 | 0.025 | 0.64 | 4.98 | -4.34 |
| [0.05,0.10) | 79 | 0.075 | -0.02 | 0.80 | -0.82 |
| [0.10,0.15) | 78 | 0.128 | 4.83 | 6.11 | -1.28 |
| [0.15,0.25) | 143 | 0.199 | 3.34 | 0.97 | 2.39 |
| [0.25,0.40) | 231 | 0.318 | 8.03 | 6.88 | 1.12 |
| [0.40,1.01) | 808 | 0.690 | 7.50 | 7.19 | 0.32 |

### 15m windows: n=475, mean $I_{dur}$=9.66 bps, mean $I_{temp}$=0.15 bps

## 5. MM interpretation

| Desk function | Implication |
|---------------|-------------|
| **Child-order scheduling** | Raise urgency cost with ρ; widen envelope when Ch.2 vol curve peaks (18 UTC) |
| **Quoting / hedging** | Temporary component → inventory can fade; permanent → treat as toxic flow |
| **PoV / VWAP algos** | Use `sched.pov_envelope` with conservative κ,γ; do not trust tape ρ as capacity |
| **Liquidity seeking / SOR** | Haircut unvalidated depth (`lsor.latency_depth_haircut`); Ch.1 crossed gate still applies |
| **TCA** | Arrival–VWAP gap here is market self-measure — score brokers only with *own* fills |

## 6. Promote / Hold / Kill

See [`CANDIDATES.md`](../../chapters/ch03_optimal_trading/CANDIDATES.md). Notebook: [`ch03_optimal_trading.ipynb`](../../chapters/ch03_optimal_trading/ch03_optimal_trading.ipynb).

Artifacts: `research/out/ch03_optimal_trading/`. Plots: ['/home/dev/srv/ares-microstructure/research/out/ch03_optimal_trading/impact_vs_rho_5m.png', '/home/dev/srv/ares-microstructure/research/out/ch03_optimal_trading/impact_scatter_5m.png', '/home/dev/srv/ares-microstructure/research/out/ch03_optimal_trading/ac_schedule_toy.png', '/home/dev/srv/ares-microstructure/research/out/ch03_optimal_trading/temp_impact_hist.png']
