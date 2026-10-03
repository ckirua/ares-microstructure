# gex_implied_book — NOTES

**Book:** SqueezeMetrics (`sqzme`), *The Implied Order Book* (GEX Ed., 6 July 2020)  
**PDF:** Gamma exposure → $/pt implied LOB (PDF pp. 4–5) · **Status:** `notes`  
**Raw:** [`../../_raw/pdf_extract.txt`](../../_raw/pdf_extract.txt) · Formulas: [`../../_raw/formula_extract.md`](../../_raw/formula_extract.md)

---

## 1. Paper formulas (page cites)

### Black–Scholes δ (PDF p. 4)

$$
d_1 = \frac{\ln(S/K) + (r + \sigma^2/2)\,T}{\sigma\sqrt{T}},\quad
\delta_{\mathrm{call}} = \Phi(d_1),\quad
\delta_{\mathrm{put}} = -\Phi(-d_1)
$$

(paper’s signed put convention in the snippet). Plug new $S$ (and $T$) to get Δδ.

### Unit GEX example (PDF p. 4)

Fund **sold** 2900-strike put, $T=30/365$, $\sigma=0.20$, $S=3000$, $r=0$:
- δ ≈ 0.27 → dealer long put needs ≈ $81{,}000$ SPX ($3000 \times 27$) to flatten.
- At $S=2950$, δ ≈ 0.37 → need ≈ $109{,}150$ → **+$28{,}150$ bid** between 3000 and 2950.
- Per-point: at $S=2999$, GEX ≈ **$393 / SPX point** for that one contract — dealer **buys** on dips and **sells** on rallies (liquidity provision).

### Aggregate GEX (PDF pp. 4–5)

$$
\mathrm{GEX} = \sum_{c \in \mathrm{DDOI}} \mathrm{GEX}_c
$$

- **GEX > 0:** customers sold enough options → dealers provide stabilizing liquidity.
- **GEX < 0:** customers long options → dealers short γ → take liquidity (destabilizing).

### Stylized facts (PDF p. 5)

- SPX GEX **rarely negative**; when negative, not below ≈ **−$200mm / pt**.
- Often **>$1bn / pt** (≈ 6{,}666 E-minis / pt at SPX 3000).
- Scatter: higher GEX ↔ tighter 1d close-to-close returns.
- **Zero GEX is ambiguous** — small inventory vs high IV compressing γ (pp. 5–6).

---

## 2. Desk mapping

| Object | Paper | Desk |
|--------|-------|------|
| S | SPX | ETH (BTC) mark — HL/Deribit |
| Chain | SPX options | Deribit options |
| GEX unit | $ / index point | $ / $1 (or bps) mark move — fix unit in EXP_REPORT |
| Sign | DDOI-weighted | `ddoi_proxy`-weighted; Hold if unsigned |
| RV link | 1d |c-to-c| vs GEX | Hourly/daily RV of ETH mark vs GEX |

Underlying TOB (HL/Deribit; Kraken `spot_l2` when dense) is for **co-movement / regime checks**, not executable book α.

---

## 3. Pass checklist

### Pass 0
- [x] Extract BS δ + unit/agg GEX with page cites
- [x] Lock crypto units + Hold on unsigned inventory

### Pass 1
- [ ] Chain GEX panel + RV scatter
- [ ] Never Promote TOB-cross as α
