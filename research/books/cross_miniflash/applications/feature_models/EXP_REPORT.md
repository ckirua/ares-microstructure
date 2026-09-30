# Feature models + Hold→Promote — EXP_REPORT

Generated: 2026-09-30T19:30:03.094521+00:00
Sample: n_events=275 · cells 42/42
Symbols=['ETH', 'BTC'] · days=['2026-09-04', '2026-09-05', '2026-09-06', '2026-09-07', '2026-09-08', '2026-09-09', '2026-09-10']

## 1. Severity / regime model

### Occurrence (logistic, cell half-day)
- n=84 train/test=50/34
- base rates train/test=0.38/0.47058823529411764
- **AUC train/test = 0.8743633276740237 / 0.6354166666666667**
- Brier test=0.24459673728437625 · acc_test=0.5882352941176471
- OOS useful (≥0.60 AUC)? **True**
- Coefs: {'vpin_exante': -0.5334979320124815, 'intensity': 0.8465372325955716, 'rv_1m': 0.0, 'amihud': 0.0, 'log_notional_pre': -0.3434268183725251, 'hour_utc': 0.6220201891102015, 'H_v': -0.4977848730850022}

### Severity |ΔP| (Ridge + NW-OLS, event-level, ex-ante features)
- n=275 train/test=165/110
- **Ridge R² train/test = 0.1977326082205566 / -0.18988789528511285**
- RMSE_te=0.1387996617434326 · NW R²=0.19774465147180664
- Bucket (p75) AUC_te=0.45666666666666667
- OOS useful? **False**
- Ridge coefs: {'vpin_exante': 0.031632607353712455, 'intensity': 0.031119249957046086, 'rv_1m': 0.03492610946503925, 'amihud': -0.021952009342120157, 'log_notional_pre': -0.0003681858045238986, 'hour_utc': -0.023156627439064766, 'H_v': -0.022714451614624227}

### Regime decision: **Promote** — occurrence OOS AUC=0.6354166666666667 (day-level feats, no crash-half leakage); severity OOS R²=-0.18988789528511285 bucketAUC=0.45666666666666667 useful=False
Note: Even if Promote, class=regime/risk feature — not tradable alpha.

## 2. Hold→Promote denser attempts

### `exec.tape_markout_post_crash` → **Hold**
- pooled mo@5s mean=-11.075848263930583
- checks: {'sign_stable_early_late': True, 'class_sep_v_lt_cont': True, 'mid_coverage_ge_50pct': False, 'mid_frac': 0.0, 'early_mean': -9.283630517753648, 'late_mean': -12.017521994972702, 'v_mean': -16.513118646584893, 'cont_mean': 12.12256046244436}
- why: still Hold: sign_stable=True, class_sep=True, mid_ok=False (mid_frac=0.00); tape mo@5s≈-11.08bps

### `risk.duration_post_markout` → **Hold**
- spearman dt/ic/volclock vs |mo| = -0.2950916869763493 / 0.15432889644881578 / 0.18395649384003135
- train/test: {'dt': -0.33856107660455487, 'i_c': 0.16765297906602256, 'vol_clock': 0.22262767425810903, 'n': 165} / {'dt': -0.12063756834399036, 'i_c': 0.16404411083310166, 'vol_clock': 0.06740802520619034, 'n': 110}
- why: still Hold: wall-clock median_dt=0.0, frac_dt0=0.51; test ρ(i_c)=0.164, ρ(vol)=0.067 (need |ρ|≥0.20 sign-stable)

### `info.vpin_x_size_severity` → **Promote**
- n=275 R²=0.08986599256604455 t={'logN': 2.6652292232430037, 'vpin': 3.2163189503906073, 'logN_x_vpin': -2.640215469911062}
- interact boot CI: {'n_boot': 600, 'mean': -0.07855030827424095, 'lo': -0.13668425830955888, 'hi': -0.03201954952096876, 'ci_excludes_0': True}
- size β early/late: 0.0984758258350259 / 0.07295517058776223
- why: ex-ante VPIN×logN interact boot CI excludes 0 + OOS t stable

## Identification / leakage controls
- Occurrence: chronological 60/40 by day×half; features imputed with **train** medians only
- Severity: event-level pre-window features (strictly before event start); time_split on ts_start
- VPIN: rolling bucket series asof before event (`vpin_exante`)
- Plain size→severity remains Kill; only interact re-tested

## Figures
- `fig_occurrence_calibration.png`
- `fig_severity_coefs.png`
- `fig_hold_promote.png`
- `fig_markout_by_class.png`
