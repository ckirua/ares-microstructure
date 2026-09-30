# Ch.15 Probability of Informed Trading (PIN) + VPIN / intensity

**PDF:** pp. 115–123 (fitz `_raw/ch15_pin.txt`)  
**Status:** `exp_run` (plot / densify pass) · **Out:** [`../../out/ch15_pin/`](../../out/ch15_pin/)  
**Scripts:** `scripts/exp_ch15_pin_deep.py` · `scripts/plot_ch15_pin.py` · legacy `exp_ch15_ch22.py`  
**Lib:** `research/lib/pin.py` · `research/lib/continuous.py`  
**Notebook:** `ch15_pin.ipynb`

---

## 1. Book specs (formulas)

### 15.a Easley–Hvidkjaer–O’Hara (EHO) day mixture

Information event at day-open with probability \(\alpha\). Conditional on an event, signal is high with weight \(\delta\) (low with \(1-\delta\)). Uninformed buy/sell arrivals are independent Poissons with intensities \(\varepsilon_B,\varepsilon_S\); informed intensity \(\mu\) adds to the “correct” side.

Unconditional probability a random trade is informed:

\[
\mathrm{PIN}=\frac{\alpha\mu}{\alpha\mu+\varepsilon_B+\varepsilon_S}.
\]

Day-\((B,S)\) mixture density (15.a.2), \(f(\lambda,n)=\mathrm{Poisson}(n;\lambda)\):

\[
\begin{aligned}
f(B,S)
&=(1-\alpha)\,f(\varepsilon_B,B)\,f(\varepsilon_S,S)\\
&\quad+\alpha\delta\,f(\varepsilon_B+\mu,B)\,f(\varepsilon_S,S)\\
&\quad+\alpha(1-\delta)\,f(\varepsilon_B,B)\,f(\varepsilon_S+\mu,S).
\end{aligned}
\]

MLE maximises \(\sum_d\log f(B_d,S_d)\) over calendar days. Book note (15.b–c): \(\mathrm{PIN}\) is essentially a **mixing-weight × intensity-gap product** (\(\alpha\mu\)), so PIN can be better identified than \(\alpha\) and \(\mu\) separately. Free \(\varepsilon_B\neq\varepsilon_S\) vs symmetric-\(\varepsilon\) is the robustness check we publish.

### 15.d Sequential fingerprint

Positive serial correlation in trade signs is the sequential-trade twin of the day mixture: informed agents (when present) keep hitting the same side. Empirically we already Promote `disc.sign_acf` (Ch.13 ρ₁≈0.54) and Prefer VPIN / intensity for *intraday* control — PIN is a slow regime label.

### Continuous analogues (not in 2004 notes; desk extensions)

| Object | Clock | Definition |
|--------|-------|------------|
| VPIN | equal-volume buckets | rolling mean of \(\lvert V_b-V_s\rvert/V\) |
| Trade intensity | 1s calendar | \(\hat\lambda\) counts/s + lag-1 of counts |

PIN and VPIN are **not interchangeable levels**: day-mixture informed probability ≠ volume-bucket imbalance.

---

## 2. Crypto translation & clocks

| Term | Our definition |
|------|----------------|
| Venue / inst | Hyperliquid ETH perp (flat-era: opaque id `3337431014`) |
| Day | UTC calendar day after clip of warehouse objects (24/7; no equity open/close) |
| \(B,S\) | Counts of aggressor buys / sells from warehouse `trade` tape |
| Usable day | `n≥400` trades **and** `span_h≥4` (deep-run filters; not certified full session) |
| VPIN bucket \(V\) | \(\approx 50\times\) median coin size on the concatenated tape |
| Intensity bar | 1s calendar bins |

**Honesty / certification:** Preferred-shard tails (not equity-session full day). Flat parquet (≤2026-09-10) needs opaque HL ids + UTC clip (files bleed across days). Thin public-md days stay unusable — warehouse release gap; all-shards does not expand ETH span. PIN̂ is a crypto day-mixture estimate, not a certified TAQ session PIN.

---

## 3. Specs shipped

| Candidate | Spec | Lenses | Decision bar |
|-----------|------|--------|--------------|
| `disc.pin_eho_mle` | EHO MLE on usable days | disc, info | ≥20 usable, MLE ok, \|PIN_free−PIN_sym\|<0.15, early/late \|Δ\|<0.25 |
| `disc.pin_proxy_dayimb` | \(\mathbb{E}\lvert B-S\rvert/(B+S)\) | disc, info | Correlate w/ markout/VPIN across regimes (else Hold) |
| `cont.vpin` | Volume-bucket rolling imbalance | cont, info, mm, exec | \(n_{\mathrm{buckets}}\ge 20\), mean finite |
| `cont.trade_intensity` | 1s \(\hat\lambda\) + ac1 | cont, exec, info | CI nonempty; clustering not always ≈0 |

Live numbers: see `EXP_REPORT.md` / `out/ch15_pin/exp_ch15_eth_summary.json`.

---

## 4. Desk relevance

| Function | Use |
|----------|-----|
| MM quoting | High VPIN → widen / pull; PIN as **day** regime, not tick control |
| Take / exec | Delay aggressive take into high-VPIN buckets; \(\hat\lambda\) for POV pacing |
| Info / AS | Pair with Ch.13 markout (how much edge) + Ch.14 GH/HS (structural AS narrative) |
| Inventory / herding | Sign ACF (Ch.13) is the sequential fingerprint; VPIN aggregates it on volume clock |

---

## 5. Results interpretation (figure pass)

ETH deep window in `out/ch15_pin/` (densify pass 2026-09-30). Regenerator: `scripts/plot_ch15_pin.py`. Notebook: `ch15_pin.ipynb`.

Headline (coverage expansion 2026-09-30):

| Object | Value |
|--------|-------|
| Days with tape / MLE usable | **34 / 28** (requested 34; opaque flat-id + UTC clip) |
| PIN MLE free ε | **≈0.183** (α≈0.28, μ≈82.0k) — **Promote** |
| PIN symmetric-ε | **≈0.153** (\|Δ\|≈0.030) |
| Time-split early / late | ≈0.150 / 0.193 (n=14/14) |
| LOO PIN sd | ≈0.016 |
| Day-imb proxy | **≈0.106** |
| VPIN mean | **≈0.914** (n_buckets≈5.4e5) |
| Intensity λ̂ | **≈1.21 /s** · ac1≈**0.275** |

### 5.1 Figure read

| Figure | What it shows | Desk take |
|--------|---------------|-----------|
| `fig_bs_scatter.png` | Day \((B,S)\) colored by span_h; usable vs thin | Mixture inputs; thin tails pull away from B=S diagonal |
| `fig_pin_day_panel.png` | Daily signed imb + span_h; usable in green | **28** usable days clear the 4h / 400-trade bar |
| `fig_pin_vs_vpin.png` | PIN free / sym / proxy vs VPIN mean | Levels differ by construction — do not rescale |
| `fig_vpin_path.png` | Rolling VPIN on recent usable days | Intraday / bucket toxicity path for widen timing |
| `fig_vpin_vs_markout.png` | Toxicity card vs Ch.13 markout horizons | VPIN = *when*; markout = *how much* AS edge |
| `fig_intensity.png` | λ̂ with CI + count ac1 | Clustering exists → POV / intensity-aware pacing |

### 5.2 Promote / Hold (honest)

- **Promote `disc.pin_eho_mle`** — 28≥20 usable; free vs sym \|Δ\|≈0.030; early/late split ok; LOO sd≈0.016.
- **Promote `cont.vpin`**, **`cont.trade_intensity`** — dense volume clock + finite λ̂.
- **Hold `disc.pin_proxy_dayimb`** — descriptive; not certified vs markout/VPIN as a Promote feature.

---

## 6. SECOND PASS — cross-links (15 ↔ 13 ↔ 14 ↔ 5)

### 6.1 Ch.15 → Ch.13 (toxicity ↔ impact)

| Ch.15 object | Ch.13 twin | Notes |
|--------------|------------|-------|
| VPIN high buckets | markout / λ / IRF widen | Same AS story; clocks differ (vol vs event/1s) |
| Intensity ac1 | sign ρ₁≈0.54 | Clustering at count vs sign level |
| PIN day label | too coarse for tick λ | Use markout+OFI intraday; PIN as overnight/regime |

### 6.2 Ch.15 → Ch.14 (toxicity ↔ structural AS)

- GH z₀ / HS lump π are **event-mid** AS; PIN is **day-mixture** AS probability.
- High ρ(q) (MRR Hold as discovery) is consistent with informed same-side flow that PIN/VPIN summarize at coarser clocks.
- Do not expect PIN̂ ≈ HS α share — different ID, different sampling.

### 6.3 Theory parent (Ch.5 sequential trade)

Glosten–Milgrom learning → permanent impact + wider quotes when μ high. Empirics live here (PIN/VPIN) and in Ch.14 (GH/MRR/HS), not in the theory-only `ch05_seq_info/` package.

### 6.4 Code / artifact map

| Piece | Location |
|-------|----------|
| Daily \(B,S\) + EHO MLE | `research/lib/pin.py` |
| VPIN / intensity | `research/lib/continuous.py` |
| Deep batch | `scripts/exp_ch15_pin_deep.py` |
| Figures + report | `scripts/plot_ch15_pin.py` · `out/ch15_pin/fig_*.png` |
| Notebook | `chapters/ch15_pin/ch15_pin.ipynb` |
