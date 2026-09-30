# Market noise / clocks — EXP_REPORT (Pass 2.6)

## TOB paths

- **HL:** warehouse `l2_rebuild` (+ collector when present).
- **Deribit:** warehouse `l2_snapshot_level`.
- **Kraken spot:** warehouse `l2_rebuild` via `spot|BTC/USD` / `spot|ETH/USD` (S3 public-md).
- **Kraken futures:** no L2/BBO in S3 archives; REST ingest → `out/kraken_futures_tob/`.

## Mid-clock

**`cont.noise_mid_clock`:** **Hold** — dense mid median=2.628 CI=[1.172,5.225] SE=0.971 n=73.0 (need CI_lo>1.5)

- n_mid=73; dense CI={'n': 73.0, 'median': 2.6284589596828876, 'mean': 10.007828439892164, 'se': 0.9714218276137652, 'ci95': [1.1720946380170352, 5.225043364195791]}
- coverage={"hyperliquid": {"n_mid": 32, "sources": ["collector", "warehouse:l2_rebuild"], "median": 0.7750183661830599}, "deribit": {"n_mid": 38, "sources": ["warehouse:l2_snapshot_level"], "median": 9.29210208228215}, "kraken": {"n_mid": 3, "sources": ["warehouse:kraken_spot_l2_rebuild"], "median": 1.0519665624141321}}
- calendar/trade/tick remain Kill/Hold per `{'calendar': {'decision': 'Kill', 'why': 'median=0.915 CI=[0.8586127390634848, 0.9847860563669919] n=90 (no bounce domination)'}, 'trade': {'decision': 'Kill', 'why': 'median=0.725 CI=[0.6980714084676117, 0.7820778164503318] n=90 (no bounce domination)'}, 'tick_bounce': {'decision': 'Kill', 'why': 'median=1.011 CI=[0.9510316385967746, 1.069021252716316] n=90 (no bounce domination)'}, 'mid': {'decision': 'Hold', 'why': 'dense mid median=2.628 CI=[1.172,5.225] SE=0.971 n=73.0 (need CI_lo>1.5)'}}`

Artifact: [`../../out/blocker_close/blocker_close.json`](../../out/blocker_close/blocker_close.json)
