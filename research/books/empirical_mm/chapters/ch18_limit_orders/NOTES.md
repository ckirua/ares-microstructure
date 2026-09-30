# Ch.18–21 Limit orders / bidding / dynamic equilibrium (Part III)

**PDF:** pp. 132–157 · **Raw extract:** [`../../_raw/ch18_21_part3.txt`](../../_raw/ch18_21_part3.txt)  
**Status:** `iterate` (NOTES + plot pass) · **Out:** [`../../out/ch18_limit_orders/`](../../out/ch18_limit_orders/)  
**Script:** [`../../scripts/exp_ch18_limit_orders.py`](../../scripts/exp_ch18_limit_orders.py) · `plot_ch18_limit_orders.py`  
**Lib:** `research/lib/lob.py`

---

## 1. Part III map (what the book asks)

Parts I–II are dealer-quote / customer-hit markets. Part III flips to **limit-order books** and markets organized around them.

| Ch | Theme | Book objects | Crypto empirics we ship |
|----|-------|--------------|-------------------------|
| **18** | LO vs dealer quotes; Glosten–Sandas book | Break-even depths \(Q_k\); no-backfill evolution; Seppi hybrid QI | L0 refill / resilience; **L1 Sandas depth moments**; cancel/fill proxies |
| **19** | Bidding under execution uncertainty | Stoll CARA bid \(B=P-\tfrac12 q a\sigma^2\) | **Theory-only** — \(a\) unobserved |
| **20** | Limit submission strategies | CMSW \(P_{\mathrm{hit}}(L)\), gravitational pull → MO | `cont.time_to_touch` + `cont.size_touch_survival` |
| **21** | Dynamic equilibrium | Foucault pick-off; Parlour queue / crowding | Improve-markout (**Kill**); `disc.parlour_depth_side` |

**Ch.5–6 bridge:** sequential/strategic adverse selection → permanent impact. Part III pick-off is the *public*-info free-option analogue (stale LO hit after news). **Ch.9:** GMM reserved for *structural* Sandas; reduced-form L1 moments ship now. **Ch.0 dig:** `disc.qty_moment_ceiling`.

---

## 2. Theory digest (formulas we care about)

### 2.1 Ch.18 — Sandas / Glosten LOB (18.b)

Competitive, risk-neutral limit suppliers cannot condition on incoming size \(m\). Ask schedule \((p_k,Q_k)\). Exponential size density \(f_{\mathrm{Buy}}(m)=e^{-m/\ell}/\ell\). Belief revision \(E[X_{t+1}\mid X_t,m]=X_t+a m\). Zero-expected-profit at the margin yields break-even cumulative depth \(Q_k\) (Sandas). Empirically Sandas (Swedish LOB) finds the **book schedule steeper than dynamic price impact** — GMM break-even moments vs impact moments disagree; order-size distribution misspecification is one candidate.

**Our reduced form:** multilevel HL `l2_snapshot_level` → mean depth by level, decay \(E[Q_k]/E[Q_0]\), behind-touch ratio — **not** structural GMM \(a,g,\ell\).

**Seppi hybrid (18 end):** dealer can quantity-improve inside the book after seeing \(m\). **No specialist / hybrid dealer on HL** → theory-only.

### 2.2 Ch.19 — Stoll CARA bid (19.b)

Dealer at portfolio optimum; CARA \(U=-e^{-aW}\). Bid that restores EU after being hit by \(q\):

\[
B = P - \tfrac12 q\, a\, \sigma_X^2.
\]

Markdown ↑ in risk aversion and size. Extensions: correlated assets → package markdown. **Blocked:** unobserved \(a\), notional \(P\), true inventory.

### 2.3 Ch.20 — CMSW hit probability / gravitational pull

Agent chooses limit price \(L\) trading off better price vs \(P_{\mathrm{hit}}(L)\). As \(L\) approaches the ask, hit probability rises; at some point EU favors a market order — **gravitational pull**. Continuous \(P_{\mathrm{hit}}\) alone may not force a jump; discreteness / discontinuity in hit prob does.

**Our proxy:** geometric **time-to-touch** by tick offset (survival under 30s censor) and **size-at-touch fill proxy** (trade-tape depletion while ask crosses a virtual limit). Not agent EU; not optimal \(L^*\).

### 2.4 Ch.21 — Foucault / Parlour

- **Foucault (1999):** public-news pick-off risk ⇒ LO traders fade prices; higher volatility → wider book / more MO.
- **Parlour (1998):** same-side depth crowds the queue ⇒ more MO on that side; opposite-side depth encourages providing.

**Our proxies:** `info.improve_markout` after bid↑/ask↓ (Kill on ETH — continuation, not pick-off); `disc.parlour_depth_side` corr(depth, aggressor).

---

## 3. Identification / data ceilings

| Need | What we have | Ceiling |
|------|--------------|---------|
| Queue position / time priority | L0 TOB size; Lk depth from snapshots | Size ≠ rank → `mm.queue_value_tick` **Hold** |
| OE fill / cancel hazard | startarb `oe/` = dry_gateway + SHM | No historical own-order tape → `mm.limit_fill_hazard_oe` **Hold** |
| Structural Sandas GMM | L1 moments from `l2_snapshot_level` | Moments ≠ break-even GMM ID → theory Hold |
| CMSW / Stoll EU | touch / size-touch proxies | Preferences unobserved |
| Foucault eq / welfare | improve-markout only | Structural eq Hold; pick-off Kill empirically |
| Collector TOB cadence | ~0.5s median L0 | Not matching-engine ms |
| L2 cadence | snapshot/delta rebuild ~5s | Schedule shape OK; HFT book dynamics not |

Public-tape **cancel proxy** = TOB depth drop without matching trade within 250ms; **fill proxy** = drop coincident with trade. Touch/size-fill censor at 30s.

---

## 4. Specs & decisions (ETH)

See `CANDIDATES.md` / `EXP_REPORT.md` / `out/ch18_limit_orders/exp_ch18_eth_summary.json`.

**Promote (public-tape):** touch monotone in offset; size-touch survival (q25 fill ≫ q75); cancel_proxy≈0.78 vs fill_proxy≈0.02; same-side refill ~15%@1s; Parlour same-ask↔sell; LO λ̂ + disc ac1; L0 resilience; Sandas L1 decay (E[Q₁]/E[Q₀]≈0.39, behind≈0.74); qty moment ceiling (var infl≈15×).

**Kill:** `info.improve_markout` — adverse CI entirely <0 (continuation).

**Hold:** OE fills, Sandas structural GMM, Stoll/CMSW EU, Foucault–Parlour eq, Seppi QI, queue-position value.

---

## 5. Desk relevance

| Job | Use |
|-----|-----|
| **MM quoting** | Resilience + refill after trade; cancel_proxy high ⇒ most “depletions” are cancels not fills |
| **Passive entry** | time_to_touch by offset; size_touch_survival for child size |
| **Queue / crowding** | Parlour depth↔aggressor; do not treat L0 size as position value |
| **Toxicity / pick-off** | Do **not** use improve-markout on this tape (Kill); use Ch.13 markout / Ch.15 VPIN |
| **Depth schedule** | Sandas L1 decay as prior for how much size sits behind touch |

---

## 6. Results interpretation (figure pass)

Notebook: `ch18_limit_orders.ipynb`. Regenerator: `scripts/plot_ch18_limit_orders.py`.

| Figure | Read |
|--------|------|
| `fig_time_to_touch.png` | Touch rate ↓ and mean touch time ↑ in tick offset — CMSW-style hit-prob monotone |
| `fig_size_touch_survival.png` | Fill-proxy rate ↓ in size quantile — larger resting size survives longer |
| `fig_cancel_vs_fill.png` | Cancel ≫ fill on TOB depletions — public “liquidity disappearance” is mostly cancel |
| `fig_sandas_depth.png` | Mean \(Q_k/Q_0\) decay + behind-touch — Glosten–Sandas schedule shape |
| `fig_resilience_refill.png` | Depth ratio / refill vs horizon after trade — book comes back, not permanently thin |
| `fig_parlour_lob_clocks.png` | Depth–aggressor corrs + LO-event intensity / ac1 |

Headline (3-day ETH window in summary JSON): TOB≈105k, trades≈117k; touch@0≈0.56; cancel_proxy≈0.78; refill@1s≈0.15; Sandas Q₁/Q₀≈0.39; Parlour ask↔sell r≈0.14; improve-markout 1s≈−0.26 bps.

---

## 7. SECOND PASS — queue / spread / fill proxies on TOB; what OE/L2 still Holds

### 7.1 What TOB already delivers (Promote and keep)

| Proxy | TOB ingredient | Desk use |
|-------|----------------|----------|
| Spread / tightness | bid–ask (Ch.22 quoted spread) | Cost floor |
| Touch / gravitational | mid path vs virtual limit offset | Passive vs take timing |
| Size-touch fill | trade qty depleting ask while crossed | Child-size survival |
| Cancel vs fill | depth drop ± trade match window | Don’t confuse cancel storms with fill toxicity |
| Same-side refill | size recovery after drop | Sandas “no backfill” falsified in reduced form @1s |
| Resilience | depth_ratio after trade | MM risk after being hit |
| Parlour | asof L0 depth × aggressor | Crowding → MO inclination |
| LO clocks | improve/worsen events | Intensity + clustering of quote updates |

These are **L0 event / size proxies**, not queue rank or OE ack outcomes.

### 7.2 What multilevel L2 adds (shipped) vs still Holds

| Shipped from L2 | Still Hold |
|-----------------|------------|
| `disc.sandas_depth_moments` — \(E[Q_k]\), decay, behind-touch | `theory.sandas_gmm_multilevel` — break-even GMM for \((a,g,\ell)\) |
| Schedule shape prior for desk depth | Dynamic book evolution under Sandas no-backfill conjecture at ms scale (snapshot cadence ~5s) |

### 7.3 What OE would unlock (explicit Holds)

| Hold ID | Needs |
|---------|-------|
| `mm.limit_fill_hazard_oe` | Own-order fill/cancel/ack timestamps |
| `mm.queue_value_tick` | Queue position or reliable priority inference |
| `theory.cmsw_optimal_L` | Agent prefs + true \(P_{\mathrm{hit}}\) for *our* orders |
| `theory.stoll_cara_bid` | Risk aversion + inventory |
| `theory.foucault_parlour_eq` | Structural equilibrium / welfare |
| Seppi QI | Hybrid dealer with size discretion |

Until OE tape exists, **use** size-touch + cancel proxies as the fill/cancel stand-ins; do not claim hazard rates.

### 7.4 Cross-links

- **Ch.13 markout / λ:** true adverse-selection for *taking*; Ch.18 improve-markout Kill means public-news pick-off is not the dominant improve story on this window.
- **Ch.15 VPIN / intensity:** toxicity regime when deciding whether to rest or take (CMSW switch).
- **Ch.10 sign ACF:** herding changes fill race dynamics on the same side.
- **Ch.22 spread / Amihud:** tightness vs impact dimensions; Part III adds resilience / immediacy.

---

## 8. Code map

| Piece | Location |
|-------|----------|
| touch / size-touch / cancel / refill / Sandas / Parlour / clocks | `research/lib/lob.py` |
| Batch empirics | `scripts/exp_ch18_limit_orders.py` |
| Figures | `scripts/plot_ch18_limit_orders.py` |
| Loaders (TOB, L2, trades) | `scripts/_data.py` |
| Notebook | `chapters/ch18_limit_orders/ch18_limit_orders.ipynb` |
