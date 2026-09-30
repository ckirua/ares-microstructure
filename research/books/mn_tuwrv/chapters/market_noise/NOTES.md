# Market noise — NOTES (Pass 2.6)

- **Deribit:** warehouse `l2_snapshot_level` via `load_tob_day`.
- **HL:** `l2_rebuild` + collector.
- **Kraken spot:** S3 `mercat-kraken-md` public-md L2 → `load_kraken_spot_tob_day("spot|ETH/USD")`.
- **Kraken futures:** sealed archives have **no** BBO/L2 (verified on MRCTCAP1 + typed parquet). Live REST ingest: `scripts/ingest_kraken_futures_tob.py`.
- Mid-clock denser panel n=73 → CI_lo improved 0.83→1.17; still **Hold** vs gate 1.5.
- Venue split matters: Deribit mid ratios elevated; HL not.
