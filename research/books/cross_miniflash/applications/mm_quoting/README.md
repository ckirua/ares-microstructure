# MM quoting — V vs continuation restore

**Desk object:** `info.crash_v_vs_continuation` · [`TRADING_APPLICATIONS.md`](../../TRADING_APPLICATIONS.md) §3.2 / §5b  
**Class:** MM playbook **research sim** on real warehouse tape — **not** live orders, **not** tradable alpha.

| Artifact | Path |
|----------|------|
| Script | `exp_v_continuation_quoting.py` |
| Desk risk report | [`out/RISK_REPORT.md`](out/RISK_REPORT.md) |
| EXP report | [`EXP_REPORT.md`](EXP_REPORT.md) |
| Metrics (slim) | [`out/metrics.json`](out/metrics.json) |
| Summary | [`out/mm_quoting_summary.json`](out/mm_quoting_summary.json) |
| Cum paths | [`out/paths.json`](out/paths.json) |
| Figs | [`out/figs/`](out/figs/) |
| Notebook | `v_continuation_quoting.ipynb` |

Shared panel: `../common/event_panel.py` (gated SSM 10bps/ic5, recovery labels). Sibling tick equity: `../strategy_lab/`, shadow day: `../paper_harness/`.

## Run

```bash
cd research/books/cross_miniflash/applications/mm_quoting
# reuse cached panel (fast):
python3 exp_v_continuation_quoting.py --reuse-panel out/panel_cache.json
# or rebuild from warehouse tape:
python3 exp_v_continuation_quoting.py
```

Also: `python3 ../run_mm_features.py` (rebuilds panel + feature_models).

## Honesty labels

| Label | Value |
|-------|-------|
| slice | `research_sim_on_real_tape` |
| live_orders | `false` |
| fills | synthetic size × signed tape markout |
| alpha_claim | `false` |
| promote_scope | med quoting playbook (restore after V-confirm; stay wide on cont) |
| clickhouse_mcp | banned |

**Promote (med)** = playbook rule sketch, not a greenlit edge. Fade-the-V remains **low** until mid markout clears.

## Policies

`always_stay_wide` · `confirm_v_restore` · `confirm_before_restore` (dual 1s∧2s) · `cont_protect` · `always_restore` · `oracle_class` (bound only)

Ranked on **continuation adverse cost**, not pooled rebound capture.
