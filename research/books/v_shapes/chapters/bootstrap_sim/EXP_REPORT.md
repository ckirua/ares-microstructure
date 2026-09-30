# Bootstrap / simulations — EXP_REPORT (Pass 1+2)

## Size / power (Models 0–3)
- Model 0: rej@5%=100.0% rej@1%=100.0% mean_MinV=-0.596 (n_mc=20)
- Model 1: rej@5%=100.0% rej@1%=100.0% mean_MinV=-0.536 (n_mc=20)
- Model 2: rej@5%=100.0% rej@1%=100.0% mean_MinV=-0.590 (n_mc=20)
- Model 3: rej@5%=100.0% rej@1%=100.0% mean_MinV=-0.436 (n_mc=20)

Meta: {"n": 2500, "hn": 0.05, "n_grid": 41, "n_boot": 20, "note": "desk-scale MC (paper uses 1000); asymptotic 2.18/3.60 Kill as desk defaults"}

## Kill
- Asymptotic |V| bands **2.18 / 3.6**: Kill as desk defaults.
- Use EGARCH simulated bootstrap quantiles for MinV.

## Artifacts
- `out/bootstrap_sim/size_power_models0_3.json`
- `out/bootstrap_sim/kill_asymptotic_bands.json`
