# ares-microstructure

Chapter-by-chapter research program extracting actionable trading content from
**Market Microstructure in Practice** (Lehalle & Laruelle) and validating it with
data experiments in the style of [`ares-startarb`](../ares-startarb).

## Quick links

| Artifact | Path |
|----------|------|
| Desk memo (MM map) | [`research/books/mmip/DESK_MEMO.md`](research/books/mmip/DESK_MEMO.md) |
| Living chapter index | [`research/books/mmip/CHAPTER_INDEX.md`](research/books/mmip/CHAPTER_INDEX.md) |
| Books | [`research/books/`](research/books/) |
| Shared helpers | [`research/lib/`](research/lib/) |
| Startarb data reuse map | [`research/DATA_PATHS.md`](research/DATA_PATHS.md) |
| Intro liquidity | [`research/books/mmip/chapters/intro_liquidity/`](research/books/mmip/chapters/intro_liquidity/) |
| Classic micro | [`research/books/mmip/chapters/classic_micro/`](research/books/mmip/chapters/classic_micro/) |
| Ch.1–3 + App.A | [`research/books/mmip/chapters/`](research/books/mmip/chapters/) |
| Experiment outputs | [`research/books/mmip/out/`](research/books/mmip/out/) |

Book PDF and verbatim extracts stay **local-only** (gitignored).

## Data policy

- **No ClickHouse MCP.** Prefer: startarb collector parquet → warehouse/`open_day` (S3) → public REST.
- Credentials: `~/.env` (same S3 keys as startarb). Run startarb loaders via `cd ../ares-startarb && uv run …`.

## Run experiments

```bash
# Intro (collector TOB)
python3 research/books/mmip/scripts/exp_intro_liquidity.py --symbol ETH

# Classic micro (needs startarb env + S3)
cd ../ares-startarb && uv run python ../ares-microstructure/research/books/mmip/scripts/exp_classic_micro.py --symbol ETH

# Promote hardening (reads out/)
python3 research/books/mmip/scripts/exp_harden_promotes.py
```

## Status (2026-09-30)

Baseline Ch.1–3 + App.A snapshot committed; **Jane Street–grade expansion** adds intro package,
classic markout/spreads/resilience, shared `research/lib/`, desk memo, and hardened Promote rollup.
