# Leakage rules — class models (V vs continuation)

**Job:** classify / soft-size the fade. **Not** mid prediction. `mid_mo_*` is null on this slice — never a feature or target.

## Allowed features (known by confirm clock ≈ `ts_end + 2s`)

| group | fields | notes |
|-------|--------|-------|
| severity | `dp_pct`, `i_c`, `z_peak`, `dt_s`, `vol_clock` | gated event attrs |
| intensity | `intensity`, `intensity_60s`, `day_intensity` | SSM / cell |
| recovery paths (causal) | `recovery_1s`, `recovery_2s` | **≤2s only** |
| microstructure | `vpin_exante`, `amihud`, `rv_1m`, `log_notional_pre`, `log_notional_event` | pre / event |
| venue structure | `H_v`, `FEI`, `thin_excess`, `thin_venue`, venue/symbol one-hots | event_panel cell join |
| nest / ladder | `nanex_overlap`, tier one-hots (`observe/widen/size_cap/halt`) | event_panel join |
| clock | `hour_utc` | diurnal |

## Forbidden as features (leakage / look-ahead / fantasy)

| field | why |
|-------|-----|
| **`mo_5s`**, `mo_1s`, `mo_*` | **outcome** for fade PnL — never a covariate |
| **`label`**, `recovery_5s`, `recovery` @5s | oracle class — **target only**, not feature |
| `mid_mo_*`, `mid_*_bps` | null / mid fantasy; not alpha |
| `tape_*_bps` post-event | post-confirm path; do not use for decision-time P̂(V) |
| future day aggregates built with test days | chrono split: impute medians on **train only** |

## Targets

- **Primary:** `y_v = 1{label == v_recovery}` (oracle@5s). Soft-size uses P̂(V).
- **Aux binary:** V vs continuation only (drop `partial`) for diagnostics.
- **Never:** regress / classify on raw mid or claim ML mid alpha.

## Decision-time honesty

- Live / paper entry must use the same feature vector as train (recovery@1–2s + pre-confirm covariates).
- Hard V-rule baseline = causal `recovery_2s ≥ 0.5` ∧ (`recovery_1s ≥ 0.35` ∨ missing) — no oracle label.
- Soft size = `f(P̂(V))` applied as fade multiplier; PnL identity: `pnl = size * (−mo_5s) − |size| * 4` bps RT.

## Promote bar

OOS soft-size **paired lift** vs `always_fade` **and** vs `hard_v_rule` must clear bootstrap CI with **robust** lower bounds (lo ≥ 0.25 bps each), positive mean net after RT=4, and early/late sign-stable. Fragile clears (lo barely > 0) → **Hold**. Classifier AUC/Brier alone is **not** enough to Promote.
