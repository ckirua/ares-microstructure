# Ch.10 trade process / inventory — ETH

- Days: ['2026-09-28', '2026-09-29', '2026-09-30']
- Overlap trades: **116,949**
- Sign ρ₁ (Ch.13): **0.535**
- Intensity λ̂ Ch.15 / overlap: **1.137** / **2.006**/s (ac1=0.282)
- VPIN (Ch.15): **0.905**
- Vol-clock sign ρ₁: **0.735** (bar≈3.08)
- Size p50/mean/p99: 0.0769 / 2.178 / 27.81
- Size trunc-var infl 0.995/0.9: **15.42×**

## Decisions

- `disc.sign_acf`: **Promote**
- `cont.trade_intensity`: **Promote**
- `cont.vpin`: **Promote** (via Ch.15)
- `disc.qty_moment_ceiling`: **Promote**
- `mm.inventory_quote_skew` / true dealer inventory: **Hold**

## SECOND PASS

- Ch.13: permanent IRF/markout = info channel; ρ₁ feeds endogenous-q models.
- Ch.15: intensity + VPIN = toxicity/arrival overlays on the same herding fingerprint.
- Ch.14: HS α|β split remains Hold on public tape.

Figures: fig_sign_acf.png, fig_intensity_volclock.png, fig_trade_size.png, fig_cumflow_inv.png

JSON: `exp_ch10_eth_summary.json`
