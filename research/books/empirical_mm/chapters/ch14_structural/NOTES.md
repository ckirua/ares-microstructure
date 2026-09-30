# Ch.14 Structural models (GH, MRR, Huang–Stoll)

**PDF:** pp. 111–114 (fitz `_raw/ch14_struct.txt`)  
**Status:** `exp_run` · **Out:** [`../../out/ch14_structural/`](../../out/ch14_structural/)  
**Scripts:** `scripts/exp_ch13_ch14.py` · `scripts/exp_ch14_hs_decomp.py` · **Lib:** `research/lib/discrete.py`

---

## 1. Book models & identification

### 14.a Glosten–Harris (1988)

\[
m_t=m_{t-1}+e_t+Q_t Z_t,\quad P_t=m_t+Q_t C_t,\quad
Z_t=z_0+z_1 V_t,\quad C_t=c_0+c_1 V_t
\]

- Trade revises efficient price by \(Q_t(z_0+z_1 V_t)\) (adverse selection × size).
- Transitory cost \(C_t\) also size-dependent; price discreteness via rounding.
- **Original equities:** no quotes ⇒ \(Q_t\) latent ⇒ nonlinear filtering / MCMC.
- **With quotes (our case):** book says GH is superseded by quote-based methods; we still estimate the **observable-quote reduced form**

\[
\Delta m_t=(z_0+z_1 V_t)q_t+e_t
\]

OLS (`glosten_harris_ols`) on **quote-aligned** \(\Delta m\) (same Ch.13 construction). Not latent-Q MCMC.

**ID assumptions:** \(q_t\) observed; mid revision attributed to trade \(t\); \(V_t\) scaled size; no separate discreteness filter on crypto tick grid.

### 14.b Madhavan–Richardson–Roomans (1997)

- \(x_t\in\{+1,-1,0\}\) (0 = inside spread); \(\mathrm{Corr}(x_t,x_{t-1})=\rho\); innov. \(x_t-\rho x_{t-1}\).
- Efficient price: \(m_t=m_{t-1}+\theta(x_t-E[x_t\mid x_{t-1}])+e_t\).
- Trade price: \(p_t=m_t+\phi x_t+\xi_t\) (non-info cost + rounding).
- Parameters \(\{\theta,\phi,\lambda_{\mathrm{MRR}},\rho,\ldots\}\); GMM on first four.
- **Our reduced form:** OLS \(\Delta p_t=a q_t+b q_{t-1}+e_t\) with

\[
\theta=\frac{a+b}{1-\rho},\quad \phi=a-\theta
\]

(`mrr_ols`). Uses **trade-price** Δp (not mid) — closer to MRR’s \(p_t\) equation. Inside-spread \(x=0\) dropped (binary sides only).

**ID assumptions:** exogenous-ish AR(1) signs; ρ from sample ACF; no GMM over-ID tests this pass.

**`disc.mrr_rho_q`:** ρ̂≈0.55–0.68 on HL ETH trade-time (train/test); signed-volume ρ lower (~0.22). Always high / split-stable → **Hold** (herding diagnostic, not a tradable feature).

### 14.c–d Huang–Stoll (1997) / spread components

Quote-mid return with inventory:

\[
r_t^q=E[r_t^*\mid W_{t-1}]+\gamma(\mathrm{DI}_{t-1})+e_t
\]

Efficient price / mid (14.d.9–11):

\[
V_t=V_{t-1}+\frac{\alpha S}{2}Q_{t-1}+e_t,\quad
M_t=V_t+\frac{\beta S}{2}\sum_{i=1}^{t-1}Q_i,\quad
\Delta M_t=\frac{(\alpha+\beta)S}{2}Q_{t-1}+e_t
\]

Trade-price form (14.d.13): \(\Delta P_t=\frac{S}{2}\Delta Q_t+\underbrace{(\alpha+\beta)}_{=\lambda_{\mathrm{HS}}}\frac{S}{2}Q_{t-1}+e_t\).

**Key ID result:** without autocorrelation in \(Q\), only the **lump** \(\lambda_{\mathrm{HS}}=\alpha+\beta\) is identified — not adverse-selection \(\alpha\) vs inventory \(\beta\) separately. With \(\Pr(Q_t\neq Q_{t-1})=p\), unexpected trade enters AS and full \(Q\) enters inventory (14.d.14–16) ⇒ GMM recovers both:

\[
\Delta P_t=\frac{S}{2}Q_t+(\alpha+\beta-1)\frac{S}{2}Q_{t-1}-\alpha\frac{S}{2}(1-2p)Q_{t-2}+e_t
\]

**Our estimators** (`discrete.py`):

1. `huang_stoll_basic_ols` — OLS \(\Delta m_t=\pi q_{t-1}+e_t\) → lump π (**Promote** when π>0 on splits + R²≥1%).
2. `huang_stoll_spread_decomp` — two-way λ + three-way OLS just-ID on (14.d.16).
3. `huang_stoll_gmm_split` — just-ID price GMM ≡ OLS; overID stacking mid moments (2-step).
4. `huang_stoll_restricted_split` — fix λ̂ from two-way, project â∈[0,λ̂] (binds when â_raw<0 — **not** Promote).
5. `volume_bucket_hs_panel` — equal-volume clock; Q = sign(net) or signed volume.
6. `dealer_inventory_proxy_ols` — **proxy** \(I_t=-\sum q_i v_i\); \(\Delta M=\pi Q_{t-1}+\gamma I_{t-1}\).

**α|β dig (2026-09-30):** trade-time / quote-clock / volume-bucket × {±1, signed vol}; train/test splits.

| Clock | OLS â | OLS b̂ | Note |
|-------|-------|--------|------|
| trade_time ±1 | **<0** | >0 | primary; restricted binds |
| quote_clock | **≪0** | >0 | same failure, worse |
| vol-bucket ±1 | >0 | **≤0** | OLS–GMM disagree; split fails |
| signed-volume Q | ~0 | ~1 | continuous Q breaks spread-share units |

→ **`disc.hs_as_inv_split` Hold** (deepened falsifier). Lump `disc.hs_pi` remains **Promote**. Two-way λ̂≈0.35–0.39 with quoted S/2.

Script: `scripts/exp_ch14_hs_decomp.py` · report `out/ch14_structural/exp_ch14_eth_hs_REPORT.md`.

Decimalization / LOB caveat (book close): quoted spread less informative for large orders; dealer-set-spread assumption weak on electronic LOBs — same on HL.

---

## 2. Crypto translation

| Object | Implementation |
|--------|------------------|
| \(\Delta m\) | Quote-aligned (`next_mid_change`) — shared with Ch.13; HS dig also asof / quote-clock / vol-bucket |
| \(V_t\) | Coin size / median size |
| \(\Delta p\) | Consecutive trade prices for MRR / HS three-way |
| Spread \(S/2\) | Median quoted half-spread at trade time (also free-S OLS) |
| Dealer inv. | **Proxy only:** \(I=-\mathrm{cumsum}(q\cdot v)\) |

---

## 3. Candidates

| id | type | lenses | decision logic |
|----|------|--------|----------------|
| `disc.gh_z0` | D | disc, info, exec | z0>0 on train+test and R²≥1% |
| `disc.mrr_theta` | D→E | disc, info, liq | θ>0 |
| `disc.mrr_rho_q` | D | disc, mm | Hold — ρ always high / split-stable; not discovery |
| `disc.hs_pi` | D | disc, info, liq, mm | π>0 on splits + R²≥1%; α\|β not ID'd |
| `disc.hs_as_inv_split` | D | disc, info, liq, mm | OLS â>0, b̂>0, share∈[0,1], R²₃≥1%, **time-split stable** on a ±1-Q clock |

---

## 4. Desk relevance

| Function | Implication |
|----------|-------------|
| TCA | MRR θ ≈ permanent; φ ≈ temporary — schedule prior |
| Quoting | GH z0 weak R² ⇒ do not size-skew from GH alone; prefer markout / λ |
| Inventory | Two-way λ̂ usable with quoted S; separate α vs β **not** ID'd on public HL tape |
| LOB reality | Structural dealer spread decomposition is analogue only |

See `EXP_REPORT.md` / `exp_ch14_*_hs_REPORT.md` for live Promote/Hold.
