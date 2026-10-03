# Trading / modelling applications — Microstructure Noise / TSRV

**Companion:** [`DESK_MEMO.md`](DESK_MEMO.md) · Index: [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) · Depth artifact: [`out/depth_predict/`](out/depth_predict/)  
**Slice honesty:** Pass 2.7 expand **0 Promote / 5 Hold / 4 Kill**; Pass 2.8 predictive — **Kill weak ICs**, **Hold suggestive**, **no forced Promote**. Everything below is **monitor → rule sketch**, not a greenlit edge.  
**Venues:** Hyperliquid · Deribit · Kraken (spot L2 + futures REST).  
**Lib:** [`../../lib/tsrv.py`](../../lib/tsrv.py)

Confidence: **high** = wire as monitor with known failure modes · **med** = rule sketch needs paper trade · **low** = research feature only.

---

## 1. Risk / RV policy

### 1.1 Never sparse-only RV (Promote-ready policy Kill)

**Object:** `cont.sparse_rv_only` (**Kill**, MC n=500)

| Layer | Rule sketch | Conf |
|-------|-------------|------|
| Risk σ | Use **TSRV first_adj** (or noise-robust ladder) for daily/horizon IV budgets | **high** |
| TCA / markout | Do not mark “1s RV” as true vol — signature plots show noise explosion at fine steps | **high** |
| Research | Keep sparse fourth as **diagnostic** only (fifth/fourth, sparse−tsrv gap) | **high** |

**Falsifier already known:** MC first_adj RMSE ≈ 0.42× fourth.

### 1.2 TSRV vs sparse on tape (Hold — monitor)

**Object:** `cont.tsrv_first_adj` (**Hold**) + Pass 2.8 DM persistence

| Use | Conf |
|-----|------|
| Publish sparse−first_adj gap on risk strip; when gap widens vs own history, prefer first_adj for σ | **med** |
| Do **not** claim tradable forecast edge from TSRV persistence alone (OOS late unstable) | **high** (honesty) |

---

## 2. Market making / quoting

### 2.1 Mid-clock noise (Hold monitor)

**Object:** `cont.noise_mid_clock` (**Hold**, CI_lo=1.13 < 1.5)

| Trigger | Action sketch | Conf |
|---------|---------------|------|
| Quoted TOB available and mid fifth/fourth elevated (esp. **Deribit**, med≫HL) | Treat mid-mark RV as bounce-contaminated; size/widen with **TSRV on mid grid**, not raw mid RV | **med** |
| Calendar/trade/tick clocks | Do **not** widen on “bounce” — those clocks are **Kill** for domination claim | **high** |

**Ops:** Always tag which clock produced fifth/fourth. Venue heterogeneity keeps pooled CI wide — venue-local thresholds.

### 2.2 Noise ↔ spread (Hold — do not auto-widen)

**Object:** `liq.noise_vs_spread` (**Hold**, ρ≈0 on n=144)

| Use | Conf |
|-----|------|
| Research join of Êε² / noise_std to spread & Amihud | **low** until CI_lo>0 |
| Auto-widen on noise_std alone | **Kill** as policy on this slice |

---

## 3. Clock trust

| Clock | Decision | Desk use |
|-------|----------|----------|
| calendar | Kill bounce claim; **default TSRV sampling clock** | Run ZMA05 ladder |
| trade | Kill | Do not use for bounce Promote |
| tick_bounce | Kill | Diagnostic only |
| mid | Hold | Quoting / mid-mark trust when TOB dense |

---

## 4. Predictive / modelling features (Pass 2.8)

Honesty: next-day OOS rank-IC on 34d panel. **Promote only if** late-half \|CI_lo\| > 0.10 and n≥30 (pre-registered in `exp_depth_predict.py`). Most claims **Kill** or **Hold**.

| Feature stack | Role | Conf |
|---------------|------|------|
| noise_std, fifth/fourth, sparse−tsrv, intensity, Amihud | Regime / state for ML — not standalone alpha | **low–med** |
| Signature fine slope, ACF lag-1 | Thesis diagnostics (noise-dominated HF RV; MA(1)-like) | **high** diagnostic |
| Optimal K stability scan | Sensitivity check around book K=300 | **med** |

See [`out/depth_predict/trade_ideas.json`](out/depth_predict/trade_ideas.json) and notebooks `uses_and_information` / `predictive_power`.

---

## 5. Monitor specs (thin applications/)

Optional harness: [`applications/monitors.py`](applications/monitors.py) — emits JSON alerts, **no orders / no fake PnL**.

| Monitor ID | Spec | Action | Conf |
|------------|------|--------|------|
| `mon.noise_std_level` | venue-day noise_std vs rolling median | risk strip flag | low |
| `mon.mid_fifth_fourth` | mid fifth/fourth when TOB quoted | distrust mid RV / prefer TSRV mid | med |
| `mon.tsrv_sparse_gap` | sparse−first_adj vs own history | prefer first_adj for σ | med |
| `mon.signature_slope` | fine-end log(RV)/log(step) < 0 | confirm Kill sparse-only | high |
| `mon.acf_lag1` | return ACF lag1 ≪ 0 | MA(1) noise check | med |

---

## 6. What not to do

- Promote mid-clock or noise↔spread without clearing CI gates.
- Treat Pass 2.8 suggestive ICs as tradable.
- Use trade-clock bounce for MM state.
- Claim crash/V predictive power — **not joined** on this pass.
- Sparse-only RV for risk after MC Kill.
