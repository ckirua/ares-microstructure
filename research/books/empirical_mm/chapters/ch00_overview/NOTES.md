# Ch.0–2 — Book front door (overview + martingale)

**Book:** Joel Hasbrouck, *Empirical Market Microstructure* teaching notes Draft 1.1 (2004-01-08)  
**PDF:** Ch.1 pp. 10–14 · Ch.2 pp. 15–19 · **Status:** `notes` (program framing + roadmap)  
**Raw:** [`../../_raw/ch00_overview.txt`](../../_raw/ch00_overview.txt) (local/gitignored)  
**SoT index:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md) · Desk: [`../../DESK_MEMO.md`](../../DESK_MEMO.md)  
**Notebook:** `ch00_overview.ipynb` · Figure: `out/ch00_overview/fig_roadmap_status.png`  
**Sibling:** [`../../../mmip/`](../../../mmip/)

This package is the **book front door** for the research program — not a free-standing empirics chapter. It answers: what Hasbrouck covers, how we package Ch.1–22, what to read first, and where every Promote / Kill / Hold lives.

---

## 1. What Hasbrouck covers (program view)

Garman (1976) sets the lens: asynchronous, temporally discrete agent activity; moment-to-moment aggregate exchange as the object of study. The notes then develop **economic + statistical** tools for trade dynamics — not a single MM model.

| Theme (Ch.1) | Book claim | Crypto / HL–Lit transfer |
|--------------|------------|--------------------------|
| Private vs common value | Common (resale / liquidating dividend) dominates; private values (horizon, risk, tax) generate trade | Funding / inventory / PPE = private; oracle / index / funding rate = common |
| Mechanisms | Walrasian call rare; continuous dealership vs double auction; real markets are hybrids | HL/Lit continuous CLOB + auction-like opens; RFQ/OTC still bargaining |
| Multiple prices | Trade / bid / ask / mid / venue — no single “the” price | Always join TOB mid + trade tape; never treat last trade as efficient alone |
| Liquidity | Depth, breadth, resilience + time/cost; network externality | `liq.*`, resilience (ch18/22), Amihud |
| Econometrics | Point processes; well-ordered stamps; large-N / short calendar | Warehouse tails = short calendar; collector TOB = dense N → Ch.9 SEs |
| Big questions | Strategies; how info enters prices; failures; fairness; structure ↔ valuation; tape → firm info & long-term risk | Maps to lenses `mm · disc · cont · exec · info · liq` — **not MM-only** |

**Economic ≠ statistical significance.** Desk Promotes need falsifiers + held-out, not p-values alone.

### Ch.2 — martingale overlay

- Long-run: fundamentals. Microstructure = short-run overlay on frictionless martingale / RW for efficient price \(m_t\).
- Observed \(p_t = m_t + s_t\) with transient microstructure \(s_t\) (bounce, inventory, lagged adjustment).
- Drift usually 0 at microstructure horizons; overnight / session breaks need special treatment (→ Ch.9).
- **Gabaix dig (Ch.0/2):** finite-moment caution on trade size → `disc.qty_moment_ceiling` (**Promote**, via ch18/ch10; trunc-var inflation ≈15× at 0.995 vs 0.9 on ETH qty).

### disc vs cont (program stance)

| Axis | Discrete | Continuous |
|------|----------|------------|
| Time | Event index, trade clock | Calendar, volume clock, intensity |
| Price | Tick grid, bid-ask bounce | Latent efficient diffusion + noise |
| Flow | \(q_t=\pm 1\) | OFI / signed volume rate |
| Estimators | VAR, Roll, GH, MRR, PIN MLE | Kernel/intensity, noise-robust RV, VPIN |

**Lib:** `research/lib/{discrete,continuous,lob,pin}.py`.

---

## 2. How packages map Ch.1–22

| Book Ch. | Title (short) | Package | Empirics home |
|----------|---------------|---------|---------------|
| 1–2 | Overview / martingale | **`ch00_overview/`** | Framing + qty-moment dig |
| 3 | Roll | `ch03_roll/` | Roll Kill; noise clocks |
| 4 | MA/AR toolkit | → `ch09_estimation/` NOTES | Folded |
| 5 | Sequential info (GM) | `ch05_seq_info/` | Theory + **synthetic** nbs |
| 6 | Strategic (Kyle) | `ch06_strategic/` | Theory + **synthetic** nbs |
| 7–8 | Gen. Roll / RW decomp | `ch08_noise/` (+ ch03) | Noise Kill after bootstrap |
| 9 | Estimation case | `ch09_estimation/` | MA/AR σ_w Promote |
| 10 | Trade / inventory | `ch10_trades/` | Sign ACF / intensity / size |
| 11–12 | RW / multivariate toolkit | → `ch13_var_impact/` NOTES §7 | Folded |
| 13 | Prices & trades (stat) | `ch13_var_impact/` | λ / IRF / OFI / markout |
| 14 | Structural (GH/MRR/HS) | `ch14_structural/` | π Promote; α\|β Hold |
| 15 | PIN | `ch15_pin/` | PIN **Promote** (28d); VPIN Promote |
| 16 | Asymmetry synthesis | `ch16_asymmetry/` | Measure board |
| 17 | Discovery / cointegration | `ch17_discovery/` | IS / Epps / jumps |
| 18–21 | Limit orders (Part III) | `ch18_limit_orders/` | Touch / Sandas L1 / refill |
| 22 | Liquidity / costs | `ch22_liquidity/` | Amihud / quoted spread |
| Appendix | US equity markets | `appendix_us/` | **`park`** — transfer table only |

Full living map + Promote rollup: **[`CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md)**.

---

## 3. Reading order (desk)

Recommended path for someone joining the program:

1. **This front door** (`ch00_overview`) + [`DESK_MEMO.md`](../../DESK_MEMO.md) — jobs × Promotes.
2. **Theory spine (study guides):** `ch05_seq_info` → `ch06_strategic` (synthetic figures; empirics owned downstream).
3. **Bounce / noise hygiene:** `ch03_roll` + `ch08_noise` + `ch09_estimation` (Kill Roll/noise-RV; Promote AR/MA σ_w).
4. **Core impact stack:** `ch13_var_impact` → `ch14_structural` → `ch15_pin` → `ch16_asymmetry`.
5. **Trade process + LOB:** `ch10_trades` → `ch18_limit_orders`.
6. **X-venue + cost state:** `ch17_discovery` → `ch22_liquidity`.
7. **Appendix** only for institutional transfer ideas (`appendix_us`, parked).

Multi-lens board (embeds key figs): [`../../notebooks/desk_synthesis.ipynb`](../../notebooks/desk_synthesis.ipynb).

---

## 4. Promote / Kill / Hold map (points at CHAPTER_INDEX)

Do **not** duplicate the full candidate table here — the SoT is [`CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md) §Promote rollup + Remaining Holds.

### Snapshot (2026-09-30)

| Bucket | Count (approx) | Where to look |
|--------|----------------|---------------|
| **Promote** | ~28 candidates across lenses | CHAPTER_INDEX Promote table; DESK_MEMO §2 |
| **Kill** | Roll\*, `info.improve_markout`, `cont.noise_rv_ratio` | ch03 / ch09 / ch18 |
| **Hold** | PIN proxy, HS α\|β, OE fill hazard, Part III theory.\*, weak ρ / volclock | CHAPTER_INDEX Holds table |

### Desk-job shortcuts

| Job | Start with Promotes from… |
|-----|---------------------------|
| Quoting / MM | ch22 spread · ch18 touch/refill/Sandas · ch15 VPIN · ch13 markout/OFI · ch14 HS π |
| Toxicity / info | ch13 markout · ch15 VPIN · ch10/13 sign ACF · ch09 σ_w · ch14 GH/MRR |
| Execution / POV | ch13 λ/IRF · ch14 MRR θ · ch18 time_to_touch · ch22 Amihud |
| SOR / x-venue | ch17 IS / Epps / jump concordance |
| Stat-arb / research | ch22 Amihud · ch09 AR/MA · ch17 Epps · ch18 qty ceiling |

Falsifiers: DESK_MEMO §4. Public-tape ceilings: DESK_MEMO §5 / CHAPTER_INDEX Remaining Holds.

---

## 5. Program status board

See notebook figure `fig_roadmap_status.png` (built from CHAPTER_INDEX roadmap rows). Narrative rollup:

- **Holds pass COMPLETE** for public-tape OE/Sandas/noise residuals.
- Deep empirics packages (ch03/08/09/10/13–18/22) have NOTES + notebooks + figures.
- Theory densify (ch05/06) finished with labeled SYNTHETIC notebooks.
- **`appendix_us` stays `park`** — institutional history is not an empirics target; keep the transfer table, do not open a US-equity exp stream.

---

## 6. Candidates owned here

See [`CANDIDATES.md`](CANDIDATES.md): conceptual Holds plus **`disc.qty_moment_ceiling`** (Promote; measured in ch18/ch10).

## 7. Pointers

| | Path |
|--|------|
| Index / Promote SoT | `CHAPTER_INDEX.md` |
| Desk memo | `DESK_MEMO.md` |
| Coverage audit | `docs/COVERAGE.md` |
| Desk synthesis nb | `notebooks/desk_synthesis.ipynb` |
| mmip sibling | `../mmip/CHAPTER_INDEX.md` |
