# EXP_REPORT — Ch.3 iterate: simulated POV + extraday sys/idio

**Classification:** Research memo · paper only · *simulated* POV (not live TCA)  
**Date:** 2026-09-29  
**Decision summary:** **Promote** `impact.algo_pov_sim` (D/E scheduling). **Promote** `style.extraday_idio` (D monitor) on minimal BTC/ETH/SOL panel. Tape ρ remains descriptive flow intensity — do not conflate with algo POV.

---

## 1. Executive takeaway

### Blocker 1 — single-algo POV (doable via simulation)

Simulated POV parents on HL ETH DENSE tape (2026-09-14, 2026-09-15, 2026-09-16, 2026-09-25, 2026-09-26): **234** unique 1h windows × π∈[0.01, 0.02, 0.05, 0.1, 0.15, 0.2] (n parent×side×π = 2808). Realized POV tracks π exactly (fill_frac≈1). Book/model impact $I_{\mathrm{model}}$ rises with π (Spearman(POV, $I_{\mathrm{model}}$)≈**0.641**). On unique windows, Spearman(tape ρ, $|I_{\mathrm{dur}}|$)≈**0.054** — tape intensity ≠ algo POV. Passive fill@VWAP does **not** invent impact; scheduling uses $I=\kappa\sigma\pi^\gamma$ (κ=0.9, γ=0.5). Label: **simulated POV**, not live TCA.

### Blocker 2 — extraday sys/idio (doable via beta panel)

Deribit 1m marks (2026-09-25, 2026-09-26, 2026-09-27, 2026-09-28, 2026-09-29), universe **['BTC', 'ETH', 'SOL']**: ETH vs BTC β≈**0.93**, $R^2$≈**0.67**, var share sys/idio ≈ **0.67** / **0.33**. SOL vs BTC: β≈**2.00**, $R^2$≈**0.71**. Equal-weight basket: ETH β≈**0.71**, $R^2$≈**0.77**. Flow link (overlap n=2820): Spearman(ρ,|ε|)≈**-0.062** vs Spearman(ρ,|β r_m|)≈**-0.108** (weak / not style-discriminating on this short overlap).

## 2. Definitions

| Symbol | Definition | Honesty |
|--------|------------|---------|
| $\pi$ | Target participation of simulated POV algo | schedule input |
| $\mathrm{POV}_{\mathrm{algo}}$ | $Q_{\mathrm{algo}}/V_{\mathrm{market}}$ over parent | **simulated** |
| $\rho_{\mathrm{tape}}$ | $\|Q_{\mathrm{net}}\|/V$ over same parent | flow intensity (not POV) |
| $I_{\mathrm{dur}}$ | $\mathrm{sign}\cdot 10^4(S_{\mathrm{end}}-S_0)/S_0$ | market path (indep. of π) |
| IS-passive | fill @ slice VWAP vs $S_0$ | no impact model |
| $I_{\mathrm{model}}$ | fill markup $\kappa\sigma\pi^\gamma$ (bps) | **scheduling prior** |
| IS-impacted | IS-passive + $I_{\mathrm{model}}$ | simulated TCA |
| $r_i=\alpha+\beta_i r_m+\varepsilon_i$ | 1m log returns | Deribit marks |

## 3. Data & method

| Item | Detail |
|------|--------|
| POV tape | `load_trade_tape('hyperliquid','ETH')` DENSE days |
| POV parents | horizon=3600s, slice=60s, stride=30 slices |
| Impact prior | κ=0.9, γ=0.5 (√ρ heuristic + Ch.3 κ scale) |
| Beta marks | `load_mark_bars('deribit', …)` BTC/ETH/SOL |
| Beta days | ['2026-09-25', '2026-09-26', '2026-09-27', '2026-09-28', '2026-09-29'] |
| Not used | ClickHouse; live fills; equity index |

## 4. Results — simulated POV

- n parent×side×π rows: **2808**
- n unique windows (buy, π=0.05): **234**
- Spearman(POV, $I_{\mathrm{model}}$): **0.6415**
- Spearman(tape ρ, $|I_{\mathrm{dur}}|$) unique: **0.0537**
- mean tape ρ on parents: **0.221**

| π | n | POV | |I_dur| | IS-pass | I_model | I_book | tape ρ |
|---|---|-----|--------|---------|---------|--------|--------|
| 0.01 | 468 | 0.010 | 35.50 | -0.00 | 0.57 | 0.31 | 0.221 |
| 0.02 | 468 | 0.020 | 35.50 | -0.00 | 0.81 | 0.44 | 0.221 |
| 0.05 | 468 | 0.050 | 35.50 | 0.00 | 1.28 | 0.69 | 0.221 |
| 0.10 | 468 | 0.100 | 35.50 | 0.00 | 1.81 | 0.98 | 0.221 |
| 0.15 | 468 | 0.150 | 35.50 | 0.00 | 2.21 | 1.20 | 0.221 |
| 0.20 | 468 | 0.200 | 35.50 | 0.00 | 2.55 | 1.38 | 0.221 |

## 5. Results — beta panel

Universe: {'BTC': 'BTC-PERPETUAL', 'ETH': 'ETH-PERPETUAL', 'SOL': 'SOL_USDC-PERPETUAL'}
n 1m bars≈3740, returns=3739

### Market = BTC

| Asset | β | R² | share_sys | share_idio | n |
|-------|---|----|-----------|------------|---|
| BTC | 1.000 | 1.000 | 1.000 | 0.000 | 3739 |
| ETH | 0.930 | 0.672 | 0.672 | 0.328 | 3739 |
| SOL | 1.999 | 0.709 | 0.709 | 0.291 | 3739 |

### Market = equal-weight (BTC/ETH/SOL)

| Asset | β | R² | share_sys | share_idio | n |
|-------|---|----|-----------|------------|---|
| BTC | 0.665 | 0.871 | 0.871 | 0.129 | 3739 |
| ETH | 0.709 | 0.770 | 0.770 | 0.230 | 3739 |
| SOL | 1.626 | 0.924 | 0.924 | 0.076 | 3739 |

**Limitations:** Short panel (days listed); 1m Deribit marks; crypto beta ≠ equity CAPM; warehouse may be incomplete on thin days (e.g. 09-28/29).

### Flow vs residual (ETH)

- Spearman(ρ, |ε|): **-0.0622**
- Spearman(ρ, |β r_m|): **-0.1076**
- n overlap: 2820

## 6. MM interpretation

| Desk function | Implication |
|---------------|-------------|
| **Child-order scheduling** | Cap π via `sched.pov_envelope` using *algo* POV + $I=\kappa\sigma\pi^\gamma$; never treat tape ρ as capacity |
| **Risk caps** | $I_{\mathrm{model}}$ monotonic in π (table §4) — tighten near Ch.2 vol peaks (18 UTC) |
| **Investor style (extraday)** | ETH ~67% systematic vs BTC on this panel; idio sleeve ~33% — match hedge vs own-tape tactics |
| **TCA** | Simulated IS ≠ broker scorecard — Hold until shadow/own fills |

## 7. Promote / Hold / Kill

| id | decision | rationale |
|----|----------|-----------|
| `impact.algo_pov_sim` | **Promote** (D/E) | Single-algo POV via simulation + impact prior for scheduling / risk caps |
| `impact.rho_slope` | **Promote** (D) | Tape ρ = flow-intensity monitor only (unchanged) |
| `style.extraday_idio` | **Promote** (D) | Minimal BTC/ETH/SOL beta panel; document short sample |
| `tca.is_arrival` (own fills) | **Hold** | Still needs proprietary / shadow fills |

Artifacts: `research/books/mmip/out/ch03_pov_idio/`. Plots: ['research/books/mmip/out/ch03_pov_idio/impact_vs_algo_pov.png', 'research/books/mmip/out/ch03_pov_idio/impact_pov_vs_tape_rho.png', 'research/books/mmip/out/ch03_pov_idio/beta_var_shares.png']
