# Classic microstructure (under-covered book themes)

## Coverage

| Theme | Experiment | Decision bar |
|-------|------------|--------------|
| Adverse selection / markout by side & size | `tox.markout_*` | CI(mean 1s markout) > 0 |
| Effective vs quoted / realized spread | `spread.effective_vs_quoted` | Identified mid join; Roll separate |
| Roll implied spread | `spread.roll` | Kill if cov≥0 |
| Depth resilience after large trades | `book.resilience` | n≥50 events; depth ratio path |
| Session / UTC hour effects (crypto open analogue) | `sess.utc_hour_share` | ≥12 active UTC hours |

## Data

HL trade tape (warehouse) + HL mid from collector TOB overlap (fallback: `l2_rebuild`). No ClickHouse MCP.

## Paths

- Script: `research/books/mmip/scripts/exp_classic_micro.py`
- Out: `research/books/mmip/out/classic_micro/`
- Lib: `research/lib/markout.py`, `spreads.py`, `tob.py`
