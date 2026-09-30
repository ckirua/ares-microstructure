# ares-microstructure

Chapter-by-chapter research program extracting actionable trading content from
**Market Microstructure in Practice** (Lehalle & Laruelle) and validating it with
data experiments in the style of [`ares-startarb`](../ares-startarb).

## Quick links

| Artifact | Path |
|----------|------|
| Book PDF | `0675_Market Microstructure in Practice.pdf` |
| Living chapter index | [`research/CHAPTER_INDEX.md`](research/CHAPTER_INDEX.md) |
| Startarb data reuse map | [`research/DATA_PATHS.md`](research/DATA_PATHS.md) |
| Ch.1 notes + results | [`research/chapters/ch01_fragmentation/`](research/chapters/ch01_fragmentation/) |
| Ch.1 experiment script | [`research/scripts/exp_ch01_fragmentation.py`](research/scripts/exp_ch01_fragmentation.py) |
| Experiment outputs | [`research/out/ch01_fragmentation/`](research/out/ch01_fragmentation/) |

## Data policy

- **No ClickHouse MCP.** Prefer: startarb collector parquet → warehouse/`open_day` (S3) → public REST.
- Credentials: `~/.env` (same S3 keys as startarb). Run startarb loaders via `cd ../ares-startarb && uv run …`.

## Run Ch.1 FEI / fragmentation experiment

```bash
python3 research/scripts/exp_ch01_fragmentation.py --symbol ETH --bucket-ms 1000 --live-snapshot
```

Uses local collector TOB under `ares-startarb/results/xarb_md/tob/` by default.

## Status (2026-09-30)

Foundation + **Chapter 1** complete (`exp_run`). Next: Ch.2 intraday volume curves, then spread↔vol↔share.
