# Class models — V vs continuation (soft fade size)

Generated: 2026-09-30T20:48:39.849374+00:00
Script: `applications/edge_lab/class_models/run_class_models.py`
Out: `applications/edge_lab/class_models/out/`

## Honesty

- job=`class_V_vs_continuation_soft_fade_size` · **not mid prediction** · live_orders=False · alpha_claim=False
- RT friction = **4.0 bps** · fills = synthetic size × signed tape mo@5s
- **`mo_5s` is outcome only — never a feature** (see [`LEAKAGE.md`](../LEAKAGE.md))
- ClickHouse MCP banned

## Feature store

- panel_cache events: **275**
- join exact/slack/miss: **275** / 0 / 0
- oracle counts: `{'v_recovery': 212, 'continuation': 39, 'partial': 24}`
- causal counts: `{'v_recovery': 117, 'continuation': 69, 'partial': 89, 'unknown': 0}`
- numeric features (21): `['dp_pct', 'i_c', 'z_peak', 'dt_s', 'vol_clock', 'intensity', 'intensity_60s', 'day_intensity', 'recovery_1s', 'recovery_2s', 'vpin_exante', 'amihud', 'rv_1m', 'log_notional_pre', 'log_notional_event', 'H_v', 'FEI', 'thin_excess', 'hour_utc', 'nanex_overlap', 'thin_venue']`
- forbidden (stripped): `['label', 'mid_0.5s_bps', 'mid_1.0s_bps', 'mid_10.0s_bps', 'mid_2.0s_bps', 'mid_5.0s_bps', 'mid_mo_0.5s', 'mid_mo_1s']…`

## Chrono split

- train n=165 days=['2026-09-04', '2026-09-05', '2026-09-06', '2026-09-07', '2026-09-08']
- test  n=110 days=['2026-09-08', '2026-09-09', '2026-09-10']
- cut_index=165 · cut_day_hint=2026-09-08

## Classifier OOS metrics

| model | AUC train | AUC test | Brier test | base Brier | beats base |
|-------|----------:|---------:|-----------:|-----------:|:----------:|
| logistic | 0.968 | 0.892 | 0.1384 | 0.1898 | True |
| gbm ★ | 0.998 | 0.863 | 0.1286 | 0.1898 | True |

Primary sizing model: **gbm** (better OOS Brier / AUC among ok models).

### Top logistic coefficients (by |coef|)

- `recovery_2s`: +2.680
- `recovery_1s`: +1.177
- `amihud`: +0.461
- `tier_observe`: -0.443
- `vpin_exante`: -0.420
- `z_peak`: +0.411
- `rv_1m`: -0.356
- `tier_size_cap`: +0.308
- `thin_excess`: -0.299
- `hour_utc`: -0.269
- `intensity_60s`: +0.237
- `dt_s`: -0.223

### Top GBM importances

- `recovery_2s`: 0.736
- `dt_s`: 0.123
- `log_notional_event`: 0.032
- `rv_1m`: 0.022
- `hour_utc`: 0.013
- `vpin_exante`: 0.012
- `intensity`: 0.011
- `z_peak`: 0.011
- `amihud`: 0.009
- `intensity_60s`: 0.009
- `i_c`: 0.007
- `log_notional_pre`: 0.005

## OOS fade sizing (net bps after RT=4)

n_oos=109 · P̂(V) mean=0.725

### Baselines

| rule | n_traded | mean net | lo | hi | hit |
|------|----------|---------:|---:|---:|----:|
| `always_fade` | 109 | 5.00 | 1.79 | 8.03 | 0.62 |
| `hard_v_rule` | 40 | 3.95 | 1.62 | 6.49 | 0.82 |

### Soft maps P(V)→size

| rule | n_traded | mean net | Δ vs hard (lo,hi) | Δ vs always (lo,hi) | clears both |
|------|----------|---------:|-------------------:|--------------------:|:-----------:|
| `soft_linear` | 109 | 6.13 | 2.18 [0.74,3.66] | 1.13 [-0.14,2.69] | False |
| `soft_centered` | 73 | 6.31 | 2.36 [1.00,4.01] | 1.31 [-0.26,3.17] | False |
| `soft_piecewise` | 79 | 6.50 | 2.55 [1.11,4.03] | 1.50 [0.01,3.41] | True |
| `soft_thr_0.55` ★ | 72 | 6.54 | 2.59 [1.17,4.25] | 1.54 [0.06,3.30] | True |
| `soft_thr_0.65` | 69 | 6.57 | 2.62 [1.23,4.11] | 1.57 [0.05,3.45] | True |

Time-split (primary soft `soft_thr_0.55`): early=7.91 · late=5.10 · stable=True

## Verdict

- **Hold** — OOS soft `soft_thr_0.55` clears both baselines only fragile (vs_always lo=0.059 < 0.25 bps robust bar)
- promote_requires: `paired lift CI vs hard_v_rule AND always_fade with lo≥0.25 bps each; net CI>0; early/late sign-stable`
- Classifier metrics alone do **not** Promote; soft-size lift must clear CI.
- No ML alpha claim on raw mid (`mid_mo_*` null).

## Figures

- `out/figs/fig_calibration.png`
- `out/figs/fig_proba_hist_oos.png`
- `out/figs/fig_feature_weights.png`
- `out/figs/fig_oos_pnl_rules.png`
- `out/figs/fig_oos_lifts.png`
- `out/figs/fig_class_counts.png`

## How to run

```bash
cd research/books/cross_miniflash/applications/edge_lab/class_models
python3 run_class_models.py
```

## Artifacts

- `out/summary.json`
- `out/EXP_REPORT.md`
- `out/store/feature_store.jsonl`
- `out/store/meta.json`
- `LEAKAGE.md`
- `class_models.ipynb`

