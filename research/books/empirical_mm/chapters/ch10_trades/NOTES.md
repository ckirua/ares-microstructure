# Ch.10 Trade process and inventory control

**PDF:** pp. 80–86 · **Raw:** [`../../_raw/ch10_inv.txt`](../../_raw/ch10_inv.txt)  
**Status:** `iterate` (content + plot pass) · **Out:** [`../../out/ch10_trades/`](../../out/ch10_trades/)  
**Scripts:** `scripts/plot_ch10_trades.py` (figures + summary from Ch.13/15 out + light tape)  
**Siblings:** [`../ch13_var_impact/`](../ch13_var_impact/) · [`../ch14_structural/`](../ch14_structural/) · [`../ch15_pin/`](../ch15_pin/)

---

## 1. Two mechanisms for trade–price dynamics

Hasbrouck’s Part II opens by splitting trade/price dynamics into:

1. **Asymmetric information** (Ch.5–6, then Ch.13–15): informed trade ⇒ **permanent** mid revision (λ, IRF, PIN/VPIN).
2. **Inventory control** (this chapter; predates info models): dealer manages stock/cash ⇒ **transient** quote pressure that mean-reverts as inventory returns to preferred.

Both live in the same signed-trade series \(q_t\). Empirically we **cannot** cleanly split them from public HL tape alone (Ch.14 Huang–Stoll \(\alpha|\beta\) Hold). What we *can* measure are the **process diagnostics** the chapter motivates: arrival intensity, sign autocorrelation, size moments, and an implied cumulative-flow inventory **proxy**.

---

## 2. Book specs

### 2.1 Garman (1976) — dealer as smoother (10.a)

- Buy/sell arrivals = Poisson / exponential waiting times; intensity \(\lambda\) in events/sec.
- Single posted price cannot clear asynchronous arrivals; dealer posts bid \(P_S\) / ask \(P_B\) with balance \(\lambda_S(P_S)=\lambda_B(P_B)\); earns the turn.
- Inventory of stock:

\[
I_s(t)=I_0+N_S(t)-N_B(t).
\]

If intensities are balanced, \(I_s\) is a **zero-drift random walk** → hits any finite barrier w.p. 1 (ruin). Expected time under realistic params is days.

**Punchline:** the dealer **must** relate quotes to inventory; static balanced intensities are not viable.

Modern empirics replace constant \(\lambda\) with time-varying intensity (Engle–Russell ACD; Hawkes analogues in mmip App.A).

### 2.2 Amihud–Mendelson (1980) — active control (10.b)

Risk-neutral dealer maximizes expected profit/time. Key comparative statics:

| Claim | Content |
|-------|---------|
| Quote monotone in \(I\) | Bid & ask **decreasing** in inventory |
| Preferred position | Interior target inventory |
| Spread | Positive; ↑ with distance from preferred |
| Mid ≠ value | Inventory wedge between mid and true value |
| Dynamics | Inventory-driven price moves are **transient** |
| No manipulation | Model rules out strategic quote games |

Spread source in Garman & AM: **market power**, not adverse selection.

### 2.3 How inventories actually behave (10.c)

Book’s own empirical caution (Hasbrouck–Sofianos style facts):

- Inventories are **mean-reverting**, not RW; ruins rare.
- Ruin usually from **price** moving a leverage barrier into inventory, not trade-count hitting a fixed barrier.
- Visible public quote as the inventory-control instrument is **often refuted** — posting a skewed public quote signals desire to buy/sell.
- Alternatives: non-public quotes, interdealer brokers, selective “going along,” pennying, anonymous venues.
- Inventory-control *intuition* survives in **order-strategy** literature even when specialist quote-skew evidence is weak.

### 2.4 Trade-direction series (10.d)

Roll assumed \(\mathrm{Corr}(q_t,q_{t-k})=0\). Empirically **strong positive ACF** (Hasbrouck–Ho 1987) — herding, order splitting, delayed reaction. This is the chapter’s direct empirical object and the bridge into Ch.13 Models 2–4 (autocorrelated / endogenous \(q\)).

---

## 3. Crypto translation

| Book object | HL / our definition |
|-------------|---------------------|
| Specialist inventory \(I_t\) | **Unobserved**. Proxy: \(I_t^{\mathrm{proxy}}=-\sum_{i\le t} q_i v_i\) (cum signed volume; Ch.14 `dealer_inventory_proxy_ols`) |
| Poisson \(\lambda\) | `cont.trade_intensity` — 1s calendar trade counts |
| Sign series \(q_t\) | Aggressor side ∈ {±1} from warehouse tape |
| Volume clock | Equal-volume bars; sign ACF / VPIN on that clock |
| Trade size | Coin qty; heavy tail → `disc.qty_moment_ceiling` (Ch.00 / Ch.18) |
| Quote skew vs \(I\) | **Hold** — no maker-state; TOB imbalance is a weak public proxy only |

Venue: Hyperliquid ETH perp. Warehouse tapes are preferred-shard tails — not certified full sessions.

---

## 4. Specs shipped (this chapter’s Promotes)

| Candidate | Delivery | Decision (ETH) | Role in Ch.10 |
|-----------|----------|----------------|---------------|
| `disc.sign_acf` | ch13 → ch10 figs | **Promote** ρ₁≈0.535 | 10.d herding / continuation |
| `cont.trade_intensity` | ch15 → ch10 figs | **Promote** λ̂≈1.14/s, ac1≈0.29 | Garman arrival process |
| `cont.vpin` | ch15 (link) | **Promote** ≈0.905 | Volume-clock toxicity twin |
| `disc.qty_moment_ceiling` | ch18 (size) | **Promote** var infl≈15× | Size process / heavy tails |
| Cum-flow inv proxy | ch14 Hold path | **Hold** as control instrument | Not Promote as inventory ID |

Falsifiers: ρ₁≈0 or undefined; λ̂ undefined / n_bars≪; size moments flat (no tail inflation).

---

## 5. Desk relevance

| Function | Use of Ch.10 diagnostics |
|----------|--------------------------|
| **Quoting / MM** | High ρ₁ ⇒ expect **continuation**, not bounce; do not fade as if inventory mean-reversion will reverse mid |
| **Exec / POV** | Intensity λ̂ + clustering for pacing; size tail for child-order sizing |
| **Toxicity overlay** | Pair sign ACF with Ch.15 VPIN — same herding fingerprint at different clocks |
| **TCA impact** | Permanent IRF / λ (Ch.13) is the info channel; inventory is the *transient* residual we cannot identify cleanly |

---

## 6. Results (figure pass)

Artifacts: `out/ch10_trades/` · notebook `ch10_trades.ipynb` · regenerator `scripts/plot_ch10_trades.py`.

Headline numbers (reused Ch.13 / Ch.15 windows + light overlapping tape):

| Object | Value |
|--------|-------|
| sign ρ₁ (trade clock) | **≈0.535** (ACF slow decay through lag 20) |
| intensity λ̂ (1s) | **≈1.14**/s · count ac1≈**0.29** |
| VPIN (vol buckets) | **≈0.905** (Ch.15 Promote) |
| size p50 / mean / p99 | heavy right tail (mean ≫ median); trunc-var infl large |

### 6.1 Figure read

| Figure | What it shows | Desk take |
|--------|---------------|-----------|
| `fig_sign_acf.png` | ACF(q) lags 1…20 | Herding / splits — Roll’s uncorrelated-\(q\) assumption fails hard |
| `fig_intensity_volclock.png` | Calendar λ̂ path + volume-clock sign ACF | Garman arrivals are clustered; vol-clock partially whitening but ρ still >0 |
| `fig_trade_size.png` | Size histogram + cum mass / moment ratios | Child orders must budget for heavy tails; links Ch.18 qty ceiling |
| `fig_cumflow_inv.png` | Cum signed volume proxy \(I^{\mathrm{proxy}}\) | Looks mean-reverting-ish over windows — **not** certified dealer inventory |

---

## 7. SECOND PASS — inventory / trades ↔ Ch.13 impact & Ch.15 toxicity

### 7.1 Ch.10 → Ch.13 (inventory intuition ↔ permanent impact)

| Ch.10 object | Ch.13 twin | How to read jointly |
|--------------|------------|---------------------|
| ρ₁(q)≫0 | Models 2–4 (MA / endogenous \(q\)); IRF to +1 buy | Autocorrelated signs ⇒ information innov. is \(e_t^q=q_t-E[q_t\mid\cdot]\), not raw \(q_t\) |
| Inventory transient claim | permanent IRF ≈0.42; markout 1s >0 | Positive permanent response ⇒ **info / flow** dominates transient inventory bounce on this tape |
| Cum-flow \(I^{\mathrm{proxy}}\) | `disc.hs_as_inv_split` Hold (â≈−0.18) | Proxy inventory does **not** recover AM-style quote control; do not Promote inventory channel |

**Desk rule:** treat Ch.13 λ / IRF / markout as the **actionable** permanent channel; treat Ch.10 inventory story as prior that public quote-skew won’t cleanly identify MM inventory on crypto CLOB.

### 7.2 Ch.10 → Ch.15 (arrivals ↔ toxicity)

| Ch.10 object | Ch.15 twin | How to read jointly |
|--------------|------------|---------------------|
| Poisson / intensity λ̂ | `cont.trade_intensity` | Same estimator — Promote when CI tight and ac1 shows clustering |
| Sign herding | sequential fingerprint behind PIN (15.d) | Day-PIN Promote (28d); intraday use ACF + VPIN |
| Volume clock | `cont.vpin` ≈0.905 | Volume-synchronized imbalance is the **toxicity regime** overlay when ρ₁ and λ̂ are elevated together |

**Desk rule:** widen / delay take when **VPIN high and intensity clustered**; do not wait for day-PIN MLE.

### 7.3 Ch.10 → Ch.14 (structural inventory)

Huang–Stoll wants \(\alpha\) (AS) vs \(\beta\) (inventory). Public tape identifies lump \(\pi=\alpha+\beta\) (**Promote** `disc.hs_pi`) but not the split (**Hold** `disc.hs_as_inv_split`). That is exactly Ch.10’s empirical caution in structural clothing: inventory control is real, quote-visible ID is not.

### 7.4 Disc vs cont clocks (this chapter)

| Clock | Candidate | Prefer when |
|-------|-----------|-------------|
| Trade event | `disc.sign_acf` | Herding / split detection |
| 1s calendar | `cont.trade_intensity` | Exec pacing, clustering |
| Equal volume | `cont.vpin` (+ vol-clock sign ACF) | Toxicity regime, clock whitening |

---

## 8. Code / artifact map

| Piece | Location |
|-------|----------|
| Sign ACF / VAR / IRF | `research/lib/discrete.py` · `out/ch13_var_impact/` |
| Intensity / VPIN | `research/lib/continuous.py` · `out/ch15_pin/` |
| Size moments | `research/lib/lob.py` `qty_moment_ceiling` · ch18 out |
| Figures + ch10 summary | `scripts/plot_ch10_trades.py` · `out/ch10_trades/` |
| Notebook | `chapters/ch10_trades/ch10_trades.ipynb` |

---

## 9. Honest Holds

- **True dealer inventory / quote-skew control** — needs maker-state or specialist series.
- **`disc.hs_as_inv_split`** — structural inventory vs AS (Ch.14).
- **ACD / Hawkes parametric intensity** — point-process λ̂ + ac1 shipped; full ACD estimation is mmip territory.
