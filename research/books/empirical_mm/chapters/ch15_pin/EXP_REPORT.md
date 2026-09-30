# Ch.15 PIN / VPIN / intensity — ETH (deep + plot pass)

## Sample
- Sample: 2026-08-28T01:04:34.526000+00:00 → 2026-09-30T15:23:43.465000+00:00 (806.3h, n_trades=3517827)
- Days requested=34 · with tape=34 · MLE usable=28

## PIN (disc)
- PIN MLE (free ε)=0.18318394881173936 · α=0.28395905875994015 · μ=82027.85206414672 · εb=47160.08970852673 · εs=56701.24855769743
- PIN symmetric-ε=0.15331361575395389 · |ΔPIN|=0.0299
- proxy E|B−S|/(B+S)=0.10622636712145574 · usable day_keys=['2026-08-28', '2026-08-29', '2026-08-30', '2026-08-31', '2026-09-01', '2026-09-02', '2026-09-03', '2026-09-04', '2026-09-05', '2026-09-06', '2026-09-07', '2026-09-08', '2026-09-09', '2026-09-10', '2026-09-11', '2026-09-14', '2026-09-15', '2026-09-16', '2026-09-17', '2026-09-18', '2026-09-19', '2026-09-20', '2026-09-21', '2026-09-22', '2026-09-25', '2026-09-26', '2026-09-27', '2026-09-30']

## VPIN / intensity (cont)
- VPIN mean=0.9137892177101113 · CI=[0.9135131868707607, 0.91404718649679] · n_buckets=537824 · p50=0.9471270727644002
- Intensity λ=1.2118950732202727 /s · CI=[1.2066348336128385, 1.2179692226125036] · ac1=0.2754896292132107
- Path reload days=['2026-09-25', '2026-09-26', '2026-09-27', '2026-09-30'] · n_roll=62,293

## Cross-link Ch.13 markout
- markout 0.5/1/5s bps = 0.09259216471100418 / 0.47189332491832336 / 0.7148349508882635
- VPIN and markout are **different clocks/units** — panel is regime vs AS-edge, not a regression.

## Decisions
- `disc.pin_eho_mle`: **Promote** — <20 usable days (span/trades filters), MLE fail, |PIN_free−PIN_sym|≥0.15, or early/late |ΔPIN|≥0.25 → Hold
- `disc.pin_proxy_dayimb`: **Hold** — proxy uncorrelated with markout/VPIN across regimes
- `cont.vpin`: **Promote** — flat VPIN across buckets / n_buckets<20
- `cont.trade_intensity`: **Promote** — λ̂ CI empty or no clustering (ac1≈0 always)

## Figures
- `out/ch15_pin/fig_bs_scatter.png`
- `out/ch15_pin/fig_pin_day_panel.png`
- `out/ch15_pin/fig_pin_vs_vpin.png`
- `out/ch15_pin/fig_vpin_path.png`
- `out/ch15_pin/fig_vpin_vs_markout.png`
- `out/ch15_pin/fig_intensity.png`

## Desk / second-pass read
- Day panel: **28 usable** ≥4h days → EHO MLE **Promote** (opaque flat-id + UTC clip; thin public-md days still warehouse gaps).
- Free vs sym-ε PIN ≈0.183 vs 0.153 (|Δ|=0.030<0.15) — product αμ better ID'd than α,μ alone (Ch.15.b).
- Time-split early/late ≈0.14973883307505623/0.19322968744762475 (ok).
- VPIN mean≈0.914 on ~5e+05 buckets → **Promote** volume-clock toxicity.
- Markout 1s (Ch.13) is the tick AS object; use VPIN to *when* to widen, markout for *how much*.
- Intensity λ≈1.21/s with ac1≈0.28 → clustering; POV / delay-take.
- PIN day-mixture ≠ VPIN level — never scale one into the other.

## Certification
- Flat-era (≤2026-09-10): opaque HL id from symbols.yaml hyperliquid_flat_ids (ETH→3337431014); catalog FNV(coin) empty on flat parquet.
- UTC-day clip of warehouse objects — flat files often bleed across calendar days; clip avoids double-counting across adjacent warehouse days.
- Preferred-shard tails (HL trade shard 02) + high max_files walk; all-shards does not expand ETH span on thin public-md days (instrument shard-local).
- Thin public-md days (e.g. 09-12/13/23/24/28/29) remain unusable — warehouse release coverage gap, not a loader miss. Not certified equity-session full-day B/S.
