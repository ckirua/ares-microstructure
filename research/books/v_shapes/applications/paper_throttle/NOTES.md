# Paper exec-throttle / risk harness — MinV monitors → desk actions

**Book:** Flora & Renò (2020-09-17)
**Status:** `exp_run`
**Lib:** [`../../../lib/vstat.py`](../../../lib/vstat.py) · loaders [`../../scripts/_data.py`](../../scripts/_data.py)
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md) · Desk [`../../DESK_MEMO.md`](../../DESK_MEMO.md)
**Script:** [`../../scripts/exp_paper_throttle.py`](../../scripts/exp_paper_throttle.py)
**Out:** [`../../out/paper_throttle/`](../../out/paper_throttle/)

---

## Pass 1 — object

Convert **Promoted** risk monitors into simulated maker-desk throttle actions:

| Promote input | Use in harness |
|---------------|----------------|
| `risk.egarch_minv_bands` / `risk.daily_minv_panel` | Breach when MinV < EGARCH 5%; window `[τ★, τ★+h_n]` |
| `risk.v_vs_jump_taxonomy` | Shape label retained (V vs Λ) — narrative only |
| `risk.stress_day_minv` | Stress days in sample for breach density |
| `info.v_feature_ridge_calendar` | **Secondary paper-only weight** — deepen throttle if \|score\| extreme |

**Not used as alpha:** `y_tick_20` (Hold). Calendar Ridge stays Monitor (R²≪1).

### Actions (paper)

- `quote_widen_bps` +5 (+8 with cal boost)
- `size_mult` 0.35 (0.22 cal boost)
- `pov` / participation 0.20 (0.10 cal boost)
- pause aggressive lean (`take_pause`) for `1×h_n` after trough detection

### Benchmark

Always-on baseline on the **same** tape. Metrics: markout (5/30/60s), adverse-selection proxy (−maker mo30), inventory path, participation, equity bps, max drawdown. Honest synthetic maker fills at trade print + friction — no fantasy mid-touch.

### Clocks / causality

- τ★ from daily MinV panel; throttle **starts at trough observation** (no pre-τ★ look-ahead).
- Chronological OOS (~60/40 UTC days, aligned with feature_reg).
- Placebo: random windows of matched duration.

## Pass 2 — signals

- Label: **Exec throttle / risk** — not soft-Promote to sized alpha
- Falsifiers: OOS risk CI, early∧late sign-stability, placebo weaker than real
- Kill if throttle worsens adverse markout / DD with CI

## Empirics

See `EXP_REPORT.md` · `CANDIDATES.md` · memo notebook `paper_throttle.ipynb`.
