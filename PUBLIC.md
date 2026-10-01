# Going public

This repository is prepared for a **public** GitHub visibility flip. Visibility is **not** changed by this doc — flip it manually when ready (`gh repo edit --visibility public` or the GitHub UI).

## Disclaimer

**Research only. Not financial advice.** Notebooks, memos, and Promote/Hold/Kill labels are desk research artifacts. They are not trading recommendations, live strategy code for real capital, or guarantees of edge. Shadow apps keep `live_orders=false`.

## What is published

- Research book trees under `research/books/` (NOTES, CANDIDATES, EXP_REPORT, DESK_MEMO, scripts, notebooks)
- Shared helpers in `research/lib/`
- Shadow / paper harness source and example systemd user units
- Data path documentation (`research/DATA_PATHS.md`)

## What is gitignored (local only)

| Class | Pattern / note |
|-------|----------------|
| Secrets | `.env`, `.env.*`, credentials, keys, `.aws/`, `.netrc` |
| Book PDFs + extracts | `*.pdf`, `**/_raw/` |
| Experiment artifacts | `**/out/**` (`.gitkeep` placeholders kept) |
| Logs | `**/logs/**`, `*.log`, named poller logs |
| Heavy caches | `*.parquet`, `*.pkl`, `*.npy`, `fig_cache/`, checkpoints |
| Host overrides | `**/systemd.local/`, `*.service.d/`, `override.conf` |

## Configure environment

Sibling packages are resolved via env vars (defaults under `$HOME`):

```bash
export ARES_STARTARB="${ARES_STARTARB:-$HOME/srv/ares-startarb}"          # or ../ares-startarb
export WAREHOUSE_ROOT="${WAREHOUSE_ROOT:-$HOME/lab/lab-n2070/warehouse}"
export WAREHOUSE_SRC="${WAREHOUSE_SRC:-$WAREHOUSE_ROOT/src}"
export ARES_MICROSTRUCTURE="${ARES_MICROSTRUCTURE:-$HOME/srv/ares-microstructure}"

# S3 / warehouse credentials (same keys as startarb)
set -a && source ~/.env && set +a
```

Python helpers: `research/lib/paths.py`. systemd user units use `%h/...` and `EnvironmentFile=-%h/.env`.

See [README.md](README.md) and [research/DATA_PATHS.md](research/DATA_PATHS.md).

## Known leftovers (no history rewrite)

Git history was **not** filtered. Expect:

- Older commits may still contain `out/` experiment JSON and other artifacts that are now gitignored
- Historic commit author emails remain as written (no `git filter-repo` / email rewrite)

Treat those as archival noise; do not rely on them as the current tree. Current `main` tip should not stage PDFs, `_raw/`, live logs, or `.env`.
