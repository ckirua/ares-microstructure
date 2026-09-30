# Liquidity around V — EXP_REPORT (Pass 1+2)

## Sample rows: 21
- hyperliquid 2026-09-08: minv={'ok': True, 'min_v': -59.7041155411445, 'tau_star_s': 2431.0, 'shape': 'V', 'sig_5': False} liq={'note': 'tob_unavailable'} gm={'mu_hat': -1.1682468466229843e-06, 'sigma_hat': 0.00037676371595728045, 'mu_over_sigma': -0.0031007413854986145, 'label': 'monitor_only_not_tradable'}
- deribit 2026-09-08: minv={'ok': True, 'min_v': -40.82764898304968, 'tau_star_s': 70446.5, 'shape': 'V', 'sig_5': False} liq={'spread_bps_mean': 92.79411123917312, 'spread_bps_pre': 173.7057054834506, 'spread_bps_post': 4.526917518143146, 'depth_touch_mean': 17756326086956.523, 'n_tob': 46, 'tob_source': 'warehouse:l2_snapshot_level/warehouse:l2_tob/s3_cache', 'resilience_keys': ['horizon_ms', 'mean_depth_ratio', 'mean_abs_mid_bps', 'n_events']} gm={'mu_hat': -4.703507857690773e-07, 'sigma_hat': 0.00011716980254565011, 'mu_over_sigma': -0.0040142662661382025, 'label': 'monitor_only_not_tradable'}
- kraken 2026-09-08: minv={'ok': True, 'min_v': -48.49521811403369, 'tau_star_s': 49383.75, 'shape': 'V', 'sig_5': False} liq={'note': 'tob_unavailable'} gm={'mu_hat': 9.113858313901404e-08, 'sigma_hat': 0.0001258629576031555, 'mu_over_sigma': 0.0007241096576355131, 'label': 'monitor_only_not_tradable'}
- hyperliquid 2026-09-15: minv={'ok': True, 'min_v': -43.80528205796837, 'tau_star_s': 47209.0, 'shape': 'Lambda', 'sig_5': False} liq={'spread_bps_mean': 0.12978417999408254, 'spread_bps_pre': 0.12974628114721662, 'spread_bps_post': 0.12982207884094848, 'depth_touch_mean': 1289329500.0, 'n_tob': 2, 'tob_source': 'warehouse:l2_snapshot_level/warehouse:l2_tob/s3_cache', 'resilience_keys': ['horizon_ms', 'mean_depth_ratio', 'mean_abs_mid_bps', 'n_events']} gm={'mu_hat': -1.9018865277544163e-06, 'sigma_hat': 0.00018449938157182803, 'mu_over_sigma': -0.010308362616456722, 'label': 'monitor_only_not_tradable'}
- deribit 2026-09-15: minv={'ok': True, 'min_v': -25.82746322301349, 'tau_star_s': 36402.375, 'shape': 'V', 'sig_5': False} liq={'note': 'no_tob_in_window', 'tob_source': 'warehouse:l2_snapshot_level/warehouse:l2_tob/s3_cache'} gm={'mu_hat': -1.9311918148689253e-06, 'sigma_hat': 0.0001921950337480647, 'mu_over_sigma': -0.01004808385111757, 'label': 'monitor_only_not_tradable'}
- kraken 2026-09-15: minv={'ok': True, 'min_v': -18.375843100996242, 'tau_star_s': 70484.75, 'shape': 'V', 'sig_5': False} liq={'note': 'tob_unavailable'} gm={'mu_hat': -1.9270390484228678e-06, 'sigma_hat': 0.00019006057621263022, 'mu_over_sigma': -0.01013907821823603, 'label': 'monitor_only_not_tradable'}
- hyperliquid 2026-09-20: minv={'ok': True, 'min_v': -60.20328845305473, 'tau_star_s': 47316.25, 'shape': 'Lambda', 'sig_5': False} liq={'note': 'tob_unavailable'} gm={'mu_hat': -5.2898585146061825e-08, 'sigma_hat': 9.860917745889479e-05, 'mu_over_sigma': -0.0005364468755264954, 'label': 'monitor_only_not_tradable'}
- deribit 2026-09-20: minv={'ok': True, 'min_v': -57.70496338785505, 'tau_star_s': 10961.875, 'shape': 'V', 'sig_5': False} liq={'note': 'no_tob_in_window', 'tob_source': 'warehouse:l2_snapshot_level/warehouse:l2_tob/s3_cache'} gm={'mu_hat': 3.617072920819386e-08, 'sigma_hat': 0.00010799929621632407, 'mu_over_sigma': 0.000334916341822667, 'label': 'monitor_only_not_tradable'}
- kraken 2026-09-20: minv={'ok': True, 'min_v': -41.43223152891457, 'tau_star_s': 34844.75, 'shape': 'Lambda', 'sig_5': False} liq={'note': 'tob_unavailable'} gm={'mu_hat': -3.2341130479411185e-08, 'sigma_hat': 0.00011412334987690768, 'mu_over_sigma': -0.00028338749707482305, 'label': 'monitor_only_not_tradable'}
- hyperliquid 2026-09-25: minv={'ok': True, 'min_v': -33.33250239006189, 'tau_star_s': 10580.0, 'shape': 'Lambda', 'sig_5': False} liq={'note': 'no_tob_in_window', 'tob_source': 'warehouse:l2_snapshot_level/warehouse:l2_tob/s3_cache'} gm={'mu_hat': -3.88181769829555e-07, 'sigma_hat': 0.00013030710343799398, 'mu_over_sigma': -0.002978976276717481, 'label': 'monitor_only_not_tradable'}
- deribit 2026-09-25: minv={'ok': True, 'min_v': -67.49269830573277, 'tau_star_s': 25250.0, 'shape': 'V', 'sig_5': True} liq={'note': 'no_tob_in_window', 'tob_source': 'warehouse:l2_snapshot_level/warehouse:l2_tob/s3_cache'} gm={'mu_hat': -3.9827914740352413e-07, 'sigma_hat': 0.00014366203223343523, 'mu_over_sigma': -0.0027723340761069263, 'label': 'monitor_only_not_tradable'}
- kraken 2026-09-25: minv={'ok': True, 'min_v': -58.812708331731045, 'tau_star_s': 6692.75, 'shape': 'V', 'sig_5': False} liq={'note': 'tob_unavailable'} gm={'mu_hat': -8.16838769658789e-07, 'sigma_hat': 0.000170340599164998, 'mu_over_sigma': -0.004795326385271016, 'label': 'monitor_only_not_tradable'}

## Pass 2
- Grossman–Miller μ/σ: **monitor only** (not Promote tradable).
- Incremental lead of spread vs MinV: compare spread_bps_pre vs post when TOB present.

## Artifact: `out/liq_around_v/liq_btc.json`

## TOB coverage reality (widen)
- Collector archive: only 2026-09-29/30.
- Warehouse Deribit `l2_snapshot_level` → multi-day TOB usable.
- Warehouse Kraken L2: **empty** (hard ceiling).
- HL warehouse L2 sparse; trade-synth refused for liq Promotes.
- Gate: multi-day TOB present but Δspread(post-pre) CI does not clear 0 on sane spreads → **Hold** `liq.spread_around_minv`.
