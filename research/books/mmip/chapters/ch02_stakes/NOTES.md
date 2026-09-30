# Chapter 2 — Stakes & Roots of Fragmentation (MM notes)

**Book:** Lehalle & Laruelle, Ch.2 (PDF pp. 136–211; fitz idx 135–210)  
**Extract:** `research/books/mmip/_raw/ch02.txt`  
**Owner:** coordinator agent (Ch.2)  
**Status:** `exp_run` (MM bar)  
**Artifacts:** `NOTES` · `CANDIDATES` · `EXP_REPORT` · `ch02_stakes.ipynb` · `out/ch02_stakes/`

---

## 1. Precise setting (crypto translation)

| Term | Definition |
|------|------------|
| Venue | Hyperliquid (DEX perp) — primary experiment venue |
| Instrument | ETH perp; price in USD-stable quote; qty via `TradeTape.qty_coin` |
| Notional | \(N_i = p_i \cdot q_i^{\mathrm{coin}}\) (USD) |
| Clock | Exchange `source_ts_ns` on warehouse trades/quotes; hours = UTC |
| Taxonomy | Single-venue **temporal** fragmentation here; spatial multi-venue share = Hold |

**Honesty:** Equity “primary fixing monopoly” (NAV/EDSP) has **no** crypto twin. We use UTC hour-of-day + (later) funding windows as stationarity factors — labeled **analogue**, not identity.

---

## 2. Formulas → columns

### §2.1 Volume curve / stationarity

Hour \(h \in \{0,\ldots,23\}\) UTC:
\[
v_h = \sum_{i:\, h(t_i)=h} p_i q_i,\quad
q_h = v_h\big/\sum_k v_k,\quad
\mathrm{FEI}_{\mathrm{hour}} = H(q)/\log 24.
\]
U-shape ratio (crypto proxy; “open/close” = hours \{0,1,22,23\}, “midday” = \{12..15\}):
\[
U = \frac{\mathrm{mean}(q_0,q_1,q_{22},q_{23})}{\mathrm{mean}(q_{12},\ldots,q_{15})}.
\]
Equity-like continuous-session U-shape \(\Rightarrow U>1\). Crypto 24/7 often \(U<1\) (US hours dominate).

**Code map:** `ts_ns`, `price`, `qty_coin` from `load_trade_tape` → `volume_curve_by_hour`.

### §2.2 Spread ↔ short-horizon vol ↔ “share”

1-minute buckets on mid \(M_t = (B+A)/2\):
\[
s_t = 10^4 \frac{A_t-B_t}{M_t}\ \mathrm{(bps)},\quad
r_t = |\Delta \log M_t|.
\]
OLS: \(s_t = \alpha + \beta r_t + \varepsilon_t\).

Within-venue flow “share” proxy (not book market share):
\[
\pi_{\mathrm{tight}} = \frac{\sum_{t:\, s_t \le \mathrm{med}(s)} N_t}{\sum_t N_t}.
\]
Book claim (Europe): tighter **venue** spread → higher **venue** market share via SOR. Our \(\pi_{\mathrm{tight}}\) is only a **same-venue** time-series proxy — spatial elasticity remains Hold.

**Code map:** `load_quote_stream` (`l2_rebuild`) + tape → `align_spread_vol`.

### §2.3–2.4
HFT coverage / systemic flash — qualitative only; no promote without event labels.

---

## 3. Desk relevance

| Desk function | Ch.2 implication |
|---------------|------------------|
| **Quoting** | Widen with \(r_t\); schedule size by hour curve (avoid posting max size in dead UTC hours) |
| **Inventory** | Expect notional concentration in US afternoon UTC — inventory risk budget by hour |
| **SOR** | Do **not** infer “tight → more flow” from within-HL \(\pi_{\mathrm{tight}}\) alone |
| **Toxicity / make-take** | High \(s_t\) co-moving with \(r_t\) and notional = adverse-selection / inventory stress regime |

---

## 4. Experiment pointer

Script `research/books/mmip/scripts/exp_ch02_stakes.py` · Out `research/books/mmip/out/ch02_stakes/` · See `EXP_REPORT.md`.
