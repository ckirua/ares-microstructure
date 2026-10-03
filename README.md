# ares-microstructure

Chapter-by-chapter research program extracting actionable trading content from
market-microstructure books and validating it with data experiments in the style
of [`ares-startarb`](../ares-startarb) (sibling checkout; override with `ARES_STARTARB`).

> **Research only — not financial advice.** See [PUBLIC.md](PUBLIC.md) for what
> is published, what is gitignored, env setup, and known history leftovers.

## Quick links

| Artifact | Path |
|----------|------|
| Changelog (product/repo) | [`CHANGELOG.md`](CHANGELOG.md) |
| Experiments changelog | [`research/books/EXPERIMENTS.md`](research/books/EXPERIMENTS.md) |
| Public notes | [`PUBLIC.md`](PUBLIC.md) |
| Desk memo (MMIP map) | [`research/books/mmip/DESK_MEMO.md`](research/books/mmip/DESK_MEMO.md) |
| Living chapter index | [`research/books/mmip/CHAPTER_INDEX.md`](research/books/mmip/CHAPTER_INDEX.md) |
| Books | [`research/books/`](research/books/) |
| Shared helpers | [`research/lib/`](research/lib/) |
| Startarb data reuse map | [`research/DATA_PATHS.md`](research/DATA_PATHS.md) |

Book PDFs and verbatim extracts stay **local-only** (gitignored). Experiment
`out/`, `logs/`, and `.env` are also gitignored.

## Data policy

- **No ClickHouse MCP.** Prefer: startarb collector parquet → warehouse/`open_day` (S3) → public REST.
- Credentials: `~/.env` (same S3 keys as startarb). Run startarb loaders via `cd "${ARES_STARTARB:-../ares-startarb}" && uv run …`.
- Portable roots: `ARES_STARTARB`, `WAREHOUSE_ROOT` / `WAREHOUSE_SRC`, `ARES_MICROSTRUCTURE` (see `research/lib/paths.py`).

## Run experiments

```bash
# Intro (collector TOB)
python3 research/books/mmip/scripts/exp_intro_liquidity.py --symbol ETH

# Classic micro (needs startarb env + S3)
cd "${ARES_STARTARB:-../ares-startarb}" && uv run python "${ARES_MICROSTRUCTURE:-../ares-microstructure}/research/books/mmip/scripts/exp_classic_micro.py" --symbol ETH

# Promote hardening (reads out/)
python3 research/books/mmip/scripts/exp_harden_promotes.py
```

## Status

Baseline Ch.1–3 + App.A (MMIP) and additional book programs under `research/books/`
(empirical_mm, cross_miniflash, v_shapes, mn_tuwrv, mm_confr_viewpoints, filmonov).
