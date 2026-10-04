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
| Canonical package | [`src/ares_micro/`](src/ares_micro/) |
| Notebook compat shims | [`research/lib/`](research/lib/) |
| Startarb data reuse map | [`research/DATA_PATHS.md`](research/DATA_PATHS.md) |

Book PDFs and verbatim extracts stay **local-only** (gitignored). Experiment
`out/`, `logs/`, and `.env` are also gitignored.

## Install

```bash
set -a && source ~/.env && set +a
cd "${ARES_MICROSTRUCTURE:-$HOME/srv/ares-microstructure}"
uv sync
```

Path deps default to `$HOME/srv/ares-startarb` and `$HOME/lab/lab-n2070/warehouse`
(same absolute pins as startarb). Override layout with `ARES_STARTARB` /
`WAREHOUSE_ROOT` / `WAREHOUSE_SRC` (see `research.md.paths`).

Canonical imports: `from ares_micro…` for estimators; `from research.md…` for
proprietary loaders. `research.md` is **not** in the wheel — put the repo root
on `PYTHONPATH` (or run via `uv run` from a checkout). `research.lib` remains a
thin backward-compat shim for older notebooks.

## Data policy

- **No ClickHouse MCP.** Prefer: startarb collector parquet → warehouse/`open_day` (S3) → public REST.
- Credentials: `~/.env` (same S3 keys as startarb).
- Shared loaders: [`research/md/`](research/md/) (`research.md`; book `scripts/_data.py` are thin re-exports).

## Run experiments

```bash
# After uv sync (repo root on path for research.md)
uv run python research/books/mmip/scripts/exp_intro_liquidity.py --symbol ETH

# Classic micro (needs startarb env + S3)
uv run python research/books/mmip/scripts/exp_classic_micro.py --symbol ETH

# Promote hardening (reads out/)
uv run python research/books/mmip/scripts/exp_harden_promotes.py
```

## Status

Baseline Ch.1–3 + App.A (MMIP) and additional book programs under `research/books/`
(empirical_mm, cross_miniflash, v_shapes, mn_tuwrv, mm_confr_viewpoints, filmonov).
