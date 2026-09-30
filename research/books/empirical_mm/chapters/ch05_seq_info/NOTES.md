# Ch.5 Sequential trade models of asymmetric information

**PDF:** pp. 29–40 · **Status:** `notes` (theory study guide; empirics owned by Ch.14–15)  
**Raw:** [`../../_raw/ch05_seq.txt`](../../_raw/ch05_seq.txt)  
**Notebook:** `ch05_seq_info.ipynb` (synthetic Glosten–Milgrom cartoons — labeled as such)  
**Out:** [`../../out/ch05_seq_info/`](../../out/ch05_seq_info/) · **Plot:** `scripts/plot_ch05_seq_info.py`

---

## 1. Why this chapter exists

Hasbrouck opens asymmetric-information microstructure with two lineages:

1. **Sequential trade** (this chapter) — many informed agents, each trades at most once when “drawn”; Glosten–Milgrom (1985).
2. **Strategic trade** (Ch.6) — one informed agent who chooses size and may revisit; Kyle (1985).

Both predict: trades reveal private information ⇒ **wider quotes** when asymmetry is larger, and **permanent price impact** after signed flow. Those are the desk-usable empirical hooks; the closed forms live here as intuition, not as HL estimators.

---

## 2. Common-value / private-value setup (5.a)

- **Common value** \(V\): terminal liquidating dividend / resale value — same for all holders. Models are dominated by common-value considerations.
- **Private values** (liquidity / hedging / risk-sharing) are often ad hoc; they exist so uninformed agents still trade.
- Public information starts as common knowledge of probabilities (distribution of \(V\), agent types). Updates come mainly from **market data** (bids, asks, trade prices/volumes). Many models **omit nontrade public news** during the session — a stylization that is especially strained in crypto (oracle, funding, social).
- Private information: signal about \(V\), or perfect knowledge of \(V\).
- **Symmetric** agents: idiosyncratic variables identically distributed — does *not* rule out private info, only rules out a privileged subset.
- **Asymmetric information:** a subset has superior private information.
- Typical focus: **one information event**. At end of trading, \(V\) is revealed. Dynamics are an **adjustment** between information sets — **not stationary ongoing trading**. Empirically we “stack” days (EHO PIN) or use continuous-flow proxies (VPIN).

---

## 3. Simple sequential trade model (5.b) — Glosten–Milgrom skeleton

### Primitives

- Terminal value \(V\in\{V_L,V_H\}\) with prior \(\delta=\Pr(V=V_H)\).
- Fraction informed \(\mu\); informed always trade in the direction of \(V\) (buy if high, sell if low).
- Uninformed buy or sell with equal probability \(1/2\).
- Competitive dealer posts ask \(A\) and bid \(B\); one trader drawn at random; always a trade in the basic model.

### Zero-profit quotes

Dealer cannot cross-subsidize buys with sells under competition. Ask recovers conditional expectation given a buy:

\[
A=\mathbb{E}[V\mid\text{Buy}],\qquad B=\mathbb{E}[V\mid\text{Sell}].
\]

Losses to informed are passed to uninformed (5.b.7). With \(\delta=1/2\), spread collapses to

\[
A-B=(V_H-V_L)\,\mu
\]

(5.b.13) — **spread rises linearly in informed fraction**. Numerical example in the notes (δ=0.4, μ=0.9, \(V\in\{100,150\}\)): Bid≈103.66, Ask≈148.31, Spread≈44.65.

### Dynamics after each trade

Belief \(\delta_k\) updates by Bayes after buy/sell (5.b.14). Features:

| Feature | Implication |
|---------|-------------|
| Trade prices are a martingale | \(p_k=\mathbb{E}[V\mid\mathcal{F}_k]\) with expanding sign history |
| Order flow not symmetric | \(\mathbb{E}[q_k]\) generally ≠0 when δ≠1/2 |
| Serial correlation of orders | Informed always same side ⇒ buys follow buys |
| Permanent price impact | Next buy revises δ up ⇒ quotes jump |
| Spread declines over time | Learning reduces uncertainty about \(V\) |

**Empirical gold:** trade-price impact is estimable from market data and is a proxy for information asymmetry (→ Ch.13 λ/IRF/markout, Ch.14 GH/MRR/HS).

---

## 4. Extensions (5.c) — what breaks / what maps

### Fixed transaction cost \(c\)

\[
A_k=\mathbb{E}[V\mid\mathcal{F}_k]+c,\qquad B_k=\mathbb{E}[V\mid\mathcal{F}_k]-c.
\]

Ask and bid sequences remain martingales; **trade prices** are not (bounce ±c). Asymmetric info breaks independence between \(q_t\) and the efficient-price innovation (link to generalized Roll / Ch.13 Models).

### Price-sensitive uninformed / market failure

If uninformed demand is elastic (GM random-utility \(U=rxV+c\)), fewer uninformed trade at wide quotes ⇒ equilibrium spread wider than inelastic case. Extreme: **no finite quotes** with nonnegative dealer EV (blank screen) — market failure. Remedies: halt pending news, force market presence / reputation. Insider-trading law discussion in the text is fairness + efficiency (uninformed exit destroys liquidity).

### Event uncertainty (Easley–O’Hara lineage → PIN)

Allow probability that **no** information event occurred. Then a **non-trade** (or quiet tape) is informative. Day-level mixtures of Poisson \((B,S)\) with event probability \(\alpha\) become the EHO PIN likelihood (Ch.15). Sequential GM learning within a day and PIN across days are the same economic story at different clocks.

---

## 5. Empirical map (do not re-estimate GM here)

| Book implication | Our candidate | Package | Decision |
|------------------|---------------|---------|----------|
| Spread ↑ in \(\mu\) | `liq.quoted_spread_bps` | ch22 | Promote |
| Permanent impact of signed trade | `disc.var_lambda`, `disc.irf_permanent`, `info.markout_1s`, `disc.mrr_theta`, `disc.gh_z0` | ch13 / ch14 | Promote (aligned clocks) |
| Trade reveals type / day toxicity | `disc.pin_eho_mle`, `cont.vpin` | ch15 | PIN Promote; VPIN Promote |
| Sign clustering | `disc.sign_acf` | ch13 | Promote (ρ₁≫0) |

This folder stays **theory + cartoons**. Empirics ownership: [`../ch14_structural/`](../ch14_structural/), [`../ch15_pin/`](../ch15_pin/), [`../ch13_var_impact/`](../ch13_var_impact/).

---

## 6. Crypto transfer

- No specialist / designated dealer — adverse selection still shows in **markout**, **OFI–mid**, and **VPIN**.
- Continuous news flow violates “no nontrade public info” — treat day-mixture PIN cautiously; prefer volume-clock / markout for control.
- 24/7 sessions: “day” is a warehouse/UTC label, not an equity open.
- Cross-link mmip: `tox.markout_1s` ↔ `info.markout_1s`.

---

## 7. Study checklist (figures in notebook)

Synthetic (labeled) plots under `out/ch05_seq_info/`:

1. **Event tree / posterior odds** — how μ and δ shape Pr(I|Buy).
2. **Spread vs μ** — linear GM benchmark at δ=1/2.
3. **Belief / quote path** after a string of buys (learning, spread compression).
4. **Impact cartoon** — mid jump after signed trade (bridge to Ch.13 IRF).

Read these, then jump to Ch.13–15 for real HL numbers.

---

## 8. Code / artifact map

| Piece | Location |
|-------|----------|
| Notes (this file) | `chapters/ch05_seq_info/NOTES.md` |
| Candidates | `CANDIDATES.md` (theory Hold) |
| Schematic plots | `scripts/plot_ch05_seq_info.py` |
| Notebook | `ch05_seq_info.ipynb` |
| Empirics | ch13 / ch14 / ch15 |
