# Ch.22 Trading and asset pricing with fixed transaction costs / liquidity

**PDF:** pp. 158–164 · **Status:** `exp_run` → `iterate` (content pass)  
**Out:** [`../../out/ch22_liquidity/`](../../out/ch22_liquidity/)  
**Scripts:** [`../../scripts/exp_ch15_ch22.py`](../../scripts/exp_ch15_ch22.py) · notebook `ch22_liquidity.ipynb`  
**Lib:** `research/lib/continuous.py` (`amihud_illiquidity`) · `research/lib/spreads.py` (`quoted_spread_bps`, `effective_spread_bps`)

---

## 1. What the chapter is about

Hasbrouck’s Ch.22 links **microstructure costs** to **asset pricing**. The question is not “how do dealers set the spread?” (Parts I–III) but:

> If agents pay fixed / proportional trading costs, how do equilibrium expected returns and trading volumes respond?

Two classical predictions clash with data:

1. **Theory (Constantinides 1986, Heaton–Lucas 1996):** non-stochastic costs are mostly **second-order** for expected returns — agents widen the no-trade region and trade less.
2. **Fact:** equity **turnover** is large (~100% annual NYSE in the notes’ era); empirical return regressions often find a **positive cross-sectional** link between cost proxies and expected returns (mixed, but not zero).

A modern twist: if costs are **stochastic** and partly **systematic**, then liquidity risk is an aggregate risk factor and assets’ β to that factor should be priced (Amihud–Mendelson clientele + subsequent liquidity-factor literature).

Our empirics on HL ETH do **not** estimate a liquidity risk premium (needs a cross-section of assets + returns). They **measure** the cost proxies the book motivates — Amihud ILLIQ and quoted spread — on the same tape used elsewhere in the book, so the desk can treat them as **state variables** for sizing, stat-arb risk, and MM cost floors.

---

## 2. Theory map (book 22.a)

### 2.1 Roll net return (22.a.1–2)

With log mid \(m_t\), half-spread \(c\):

\[
r_t^{\mathrm{Net}} = r_t^{\mathrm{Gross}} - 2c.
\]

Over holding horizon \(n\) years, annualized cost \(\approx 2c/n\). Long horizons dilute fixed costs; if all investors share the same \(n\) and price net returns, **gross** expected returns rise linearly in spread in the cross-section.

### 2.2 Amihud–Mendelson (1986) clientele

Investors differ by expected holding period \(T_i\) (exponential with intensity \(m_i\)). Assets ordered by relative spread \(S_j\). Equilibrium:

- High-spread assets are held by **long-horizon** clienteles.
- Required **gross** return is a **concave** function of spread (clientele sorting).

Desk translation: a persistent wide spread on a name is not only “expensive to trade once” — it selects who owns the asset and what return they demand.

### 2.3 Constantinides (1986) no-trade region

Continuous-time Merton problem + proportional cost \(k\) on the risky asset ⇒ optimal policy keeps wealth share in \([\underline{\ell},\overline{\ell}]\). Liquidity premium \(d(k)\) needed to make the agent indifferent vs a frictionless twin is **small** relative to \(k\) for modest \(k\), but implied turnover is **far below** observed NYSE turnover. Book punchline: costs look “too small” for returns **and** “too small” for volumes — volumes remain a puzzle.

### 2.4 Heaton–Lucas (1996)

Quadratic trading costs on stocks (and asymmetric on bonds), incomplete markets, labor income. Equity premium near zero when costs small (equity-premium puzzle); trading migrates to the cheaper market when only one market is costly.

---

## 3. Liquidity as a multi-dimensional object

The chapter’s asset-pricing language collapses “cost” into \(c\) or \(S\). Desk practice needs dimensions (Kyle / Hasbrouck / Amihud tradition):

| Dimension | Proxy on our tape | Book / sibling link |
|-----------|-------------------|---------------------|
| **Tightness** | Quoted spread (bps) | Roll \(2c\); Ch.3 Kill on mid-Roll |
| **Depth / impact** | Amihud ILLIQ; Ch.13 \(\lambda\), IRF | Kyle \(\lambda\); GH/MRR/HS |
| **Resilience** | Ch.18 book refill / same-side refill | Part III LOB |
| **Immediacy / toxicity** | VPIN, intensity (Ch.15) | Informed-flow risk |
| **Turnover / activity** | \$vol / mid per bar; trade rate | Constantinides volume puzzle |

ILLIQ is an **impact / price-per-dollar** average, not a spread. Quoted spread is **tightness**. They can co-move (illiquid regimes) or diverge (tight quotes, thin depth).

---

## 4. Amihud ILLIQ — definition and design

### 4.1 Classic daily ILLIQ

Amihud (2002) average daily ratio:

\[
\mathrm{ILLIQ}_i = \frac{1}{D_i}\sum_{d=1}^{D_i}\frac{|r_{i,d}|}{\mathrm{DVol}_{i,d}}.
\]

Interpretation: absolute return per dollar of volume — a coarse **Kyle-λ / impact** proxy when order-flow data are absent. High ILLIQ ⇒ prices move a lot per unit of dollar activity.

### 4.2 Our 1-minute trade-bar construction (`liq.amihud_1m`)

Crypto sessions are 24/7; we use **1-minute calendar bars** from HL trades (signed tape not required):

1. Partition \([t_0,t_1]\) into 60s bins.
2. Bar close = last trade price; \(\mathrm{DVol}=\sum p\cdot q\) in bar.
3. \(r_t=\log(p_t/p_{t-1})\) when both closes and DVol exist and DVol\(>0\).
4. \(\mathrm{ILLIQ}=\mathrm{mean}(|r|/\mathrm{DVol})\) with bootstrap CI (`amihud_illiquidity`).

**Promote** if \(n\ge 20\) bars and ILLIQ finite / not ≈0.

Falsifier: ILLIQ≈0 or **unstable across days** (order-of-magnitude jumps without microstructure regime change).

### 4.3 Units and magnitude

ILLIQ has units of **1 / \$**. On ETH with large \$vol per minute, levels are \(\sim 10^{-9}\) in our sample — tiny next to equity small-caps, but **ordinal** variation across days/hours still informative. Do **not** compare raw ILLIQ levels to CRSP equities without rescaling (price, volume units, session length).

---

## 5. Quoted spread companion (`liq.quoted_spread_bps`)

\[
s^{\mathrm{q}}_t = 10^4\cdot\frac{\mathrm{ask}_t-\mathrm{bid}_t}{m_t}.
\]

From collector TOB (HL). Bootstrap CI on the pooled sample. **Promote** when \(n>100\) finite quotes.

Links:

- **Roll (Ch.3):** Roll recovers \(2c\) from trade-price serial covariance under strong assumptions — **Kill** on event/mid constructions in this program. Quoted spread is the direct tightness measure.
- **Effective spread:** \(2\cdot 10^4\cdot q_t(p_t-m_t)/m_t\) — paid cost vs mid; use when as-of mid join is clean (`effective_spread_bps`).
- **HS / MRR (Ch.14):** structural split of spread into permanent vs temporary; ILLIQ is closer to **permanent impact / activity** than to half-spread \(c\).

---

## 6. Empirical design (this package)

| Step | Choice | Why |
|------|--------|-----|
| Symbol | ETH | densest HL tape + TOB overlap |
| Days | last ~5 warehouse days (script default) | matches sibling ch15/22 run |
| Clock | 1m calendar for ILLIQ | Amihud needs \$vol + return; trade clock alone lacks \$ normalisation without size |
| TOB | HL collector parquet | quoted tightness |
| Companion | daily ILLIQ series + vs spread/VPIN in notebook | second-pass diagnostics |

**Not identified here:** AM clientele concavity, Constantinides \(d(k)\), HL equity premium, liquidity-factor β. Those need multi-asset panels and longer horizons.

---

## 7. Results interpretation (see EXP_REPORT)

Typical Promote pattern on ETH:

- ILLIQ \(\sim 5\times 10^{-9}\) on ~700 one-minute bars — **detectable**, CI away from 0.
- Quoted spread \(\sim 0.38\) bps — **tight** electronic perp; cost floor for MM / taker.

Desk reading:

| Use | How to read ILLIQ / spread |
|-----|----------------------------|
| **Stat-arb risk** | Rising daily ILLIQ ⇒ same \$ notional moves mid more; shrink gross or widen bands |
| **Exec sizing** | High ILLIQ + high VPIN ⇒ delay / slice; tight spread alone is not enough |
| **MM cost floor** | Quoted spread ≈ minimum round-trip tightness; ILLIQ flags when depth/impact regime worsens without spread widening |
| **Info / toxicity** | Pair with Ch.15 VPIN — ILLIQ↑ with VPIN↑ is impact+toxicity; ILLIQ↑ with VPIN flat is “empty book / low activity” |

---

## 8. Links to Roll / PIN / impact

```
Ch.3 Roll ──(Kill on mid)──► quoted/effective spread (Ch.22)
Ch.13 λ, IRF ──────────────► same economic object as ILLIQ (finer, signed)
Ch.14 GH/MRR/HS ───────────► permanent vs temporary split of costs
Ch.15 PIN/VPIN ────────────► who is trading (toxicity), not how much mid moves per \$
Ch.18 resilience ──────────► recovery after trade (dynamic depth)
```

ILLIQ averages \(|r|/\$vol\) **without** signing order flow. Ch.13 `disc.var_lambda` / IRF use signed aggressor and quote-aligned Δm — prefer those for causal impact; keep Amihud as a **robust, low-assumption** bar when signs are noisy or for cross-asset screens.

---

## 9. SECOND PASS — related liquidity topics in book scope

### 9.1 Turnover vs Constantinides

Book: \(d(k)\approx \mathrm{Turnover}\times k\) implies tiny turnover at plausible \(k\). On HL perps, **turnover is enormous** vs equity buy-and-hold — funding, leverage, and market-making inventories dominate “investor holding period.” Do not import equity AM clientele mapping one-for-one.

Notebook reports: mean \$vol per 1m bar, trades/hour, and ILLIQ×\$vol ≈ mean\(|r|\) as a sanity check.

### 9.2 Effective spread link

When trades join cleanly to TOB mid:

\[
s^{\mathrm{eff}}=2\cdot 10^4\cdot q(p-m)/m.
\]

Compare median \(s^{\mathrm{eff}}\) to median \(s^{\mathrm{q}}\). If effective ≫ quoted, mid join lag / fee / adverse selection at the touch. Useful exec TCA companion to ILLIQ (which ignores side).

### 9.3 Crypto Tob vs equity Amihud — caveats

| Equity Amihud | HL / crypto perp |
|---------------|------------------|
| Daily CRSP close, \$vol | 1m trade bars, continuous session |
| Heterogeneous tick / lot | Tiny relative tick; spread often sub-bp |
| Overnight / open auction | No primary auction; funding cycles |
| ILLIQ priced in monthly sorts | We use ILLIQ as **intraday state**, not premium estimate |
| Volume includes lit+dark aggregation issues | Single-venue tape (HL) — **venue ILLIQ**, not consolidated |

Also: dollar volume in coin-margined or multi-collateral venues can misstate “economic” volume; we use \(p\cdot q\) in quote currency as on the tape.

### 9.4 Spread–ILLIQ co-movement

Second-pass plots: daily mean quoted spread vs daily ILLIQ; optional VPIN from `out/ch15_pin/`. Concordant rises ⇒ liquidity stress. Divergence (tight spread, high ILLIQ) ⇒ **misleading tightness** — depth/impact problem.

---

## 10. Code map

| Piece | Location |
|-------|----------|
| Amihud mean + CI | `research/lib/continuous.py` → `amihud_illiquidity` |
| Quoted / effective spread | `research/lib/spreads.py` |
| Batch Promote run | `scripts/exp_ch15_ch22.py` → `out/ch22_liquidity/` |
| Figures + daily series | `chapters/ch22_liquidity/ch22_liquidity.ipynb` → `out/ch22_liquidity/fig_*.png` |

---

## 11. Candidates (summary)

| id | lenses | decision | falsifier |
|----|--------|----------|-----------|
| `liq.amihud_1m` | liq, info, exec | **Promote** | ILLIQ≈0 or unstable across days |
| `liq.quoted_spread_bps` | liq, mm, exec | **Promote** | non-finite / empty TOB |

See `CANDIDATES.md` / `EXP_REPORT.md` for live numbers.
