# Applications packages — Tee/Ting mini-flash

Post–Phase 4 sims converting Promote *monitors* into **risk-policy / MM playbook / feature / monitor** labels.  
**None are naked tradable alpha.** Desk board: [`../DESK_MEMO.md`](../DESK_MEMO.md) §7 · playbook [`../TRADING_APPLICATIONS.md`](../TRADING_APPLICATIONS.md) · catalog [`../SIGNAL_CATALOG.md`](../SIGNAL_CATALOG.md) · **ledger** [`../EXPERIMENTS.md`](../EXPERIMENTS.md).  
Board JSON: [`out/applications_board.json`](out/applications_board.json). ClickHouse MCP banned.

## Open these first

| Priority | Artifact | Path |
|----------|----------|------|
| 1 | **Full research board** (synthesis) | [`../notebooks/full_research_board.ipynb`](../notebooks/full_research_board.ipynb) |
| 2 | **Edge lab** (non-MM top-3 ideas) | [`edge_lab/`](edge_lab/) · [`TRADE_IDEAS.md`](TRADE_IDEAS.md) · [`EDGE_LAB.md`](edge_lab/EDGE_LAB.md) · [`out/EXP_REPORT.md`](edge_lab/out/EXP_REPORT.md) |
| 3 | Signal boards · MI · stats · Bayesian | [`signal_boards/`](signal_boards/) · figs [`out/signal_boards/figs/`](out/signal_boards/figs/) |
| 4 | **Strategy lab** tick/OB equity (sibling) | [`strategy_lab/STRATEGY_LAB.md`](strategy_lab/STRATEGY_LAB.md) · [`strategy_lab.ipynb`](strategy_lab/strategy_lab.ipynb) · [`strategy_lab/out/figs/`](strategy_lab/out/figs/) |
| 5 | **Expanded lab** (panel/SOL/risk scoreboard) | [`expanded_lab/`](expanded_lab/) · [`EXP_REPORT.md`](expanded_lab/EXP_REPORT.md) · [`out/figs/`](expanded_lab/out/figs/) |
| 6 | **Paper harness** (detect→ladder→shadow→daily risk) | [`paper_harness/`](paper_harness/) · [`paper_harness/README.md`](paper_harness/README.md) |
| 7 | **Horizon lab** (300/9000 sampling clocks) | [`horizon_lab/`](horizon_lab/) · [`HORIZON_RECOMMENDATION.md`](horizon_lab/HORIZON_RECOMMENDATION.md) |
| 8 | Feature models · MM quoting (playbook only) | [`feature_models/`](feature_models/) · [`mm_quoting/`](mm_quoting/) |

**Signal-board PNGs to open:** `fig_gated_intensity_ts.png`, `fig_event_heatmaps.png`, `fig_occurrence_roc.png`, `fig_bayes_v_recovery.png`.  
**Expanded-lab PNGs:** `fig_kill_ladder_robustness.png`, `fig_strategy_risk_scoreboard.png`, `fig_friction_sweep.png`, `fig_book_cadence_compare.png`.

Event-study packages below remain the §7 board evidence; `strategy_lab/` is the executable marked-PnL layer; `expanded_lab/` extends panel + risk scoreboard **without** overwriting `out/event_panel/`; `signal_boards/` does **not** overwrite strategy equity figs.

| Package | Track | Class | Verdict | Path |
|---------|-------|-------|---------|------|
| **Edge lab** | Non-MM | taker / risk gate | V-fade **Promote** · cont-ride **Kill** · int-halt **Promote** · nanex-nest **Promote** | [`edge_lab/`](edge_lab/) |
| **Paper harness** | Ops/sim | risk-policy paper trade | detect→ladder→shadow→daily report | [`paper_harness/`](paper_harness/) |
| **Strategy lab (tick/OB equity)** | Sim | risk-policy / MM playbook sims | equity curves + overlays | [`strategy_lab/`](strategy_lab/) |
| **Expanded lab** | Expand | risk / MM / ops | kill-ladder+Nanex robust on extend; ladder∩confirm best risk; dense TOB ops | [`expanded_lab/`](expanded_lab/) |
| **Horizon lab** | Clocks | risk-policy / detection | event+wall_60s **Promote**; trade_N=300/9000 detect **Kill** | [`horizon_lab/`](horizon_lab/) |
| **Signal boards** | Viz/research | boards | MI · bootstrap/ROC · Bayesian · heatmaps | [`signal_boards/`](signal_boards/) |
| Kill-ladder | Risk/SOR | risk-policy | **Promote-as-risk-policy** | [`kill_ladder/`](kill_ladder/) |
| Nanex∩SSM nested pull | Risk/SOR | risk-policy | **Promote-as-risk-policy** | [`nanex_burst/`](nanex_burst/) |
| HL thin SOR | Risk/SOR | monitor | strip **yes** / hard size-cap **Hold** | [`hl_thin_sor/`](hl_thin_sor/) |
| H^v / FEI capacity | Risk/SOR | monitor | dashboard **yes** / schedule **Hold** | [`hv_fei_capacity/`](hv_fei_capacity/) |
| V-restore quoting | MM/features | MM playbook | **Promote (med)** | [`mm_quoting/`](mm_quoting/) |
| Feature models | MM/features | feature | VPIN×size **Promote (med)** · occurrence **Soft Promote** · tape/duration **Hold** | [`feature_models/`](feature_models/) |

**Runners:** `edge_lab/exp_edge_lab.py` (non-MM top-3) · `paper_harness/run_paper_day.py` · `expanded_lab/exp_expanded_lab.py` · `signal_boards/exp_signal_boards.py` · `strategy_lab/exp_strategy_lab.py` (tick/OB) · `scripts/run_all.py` (Risk/SOR) · `run_mm_features.py` (MM/features). Shared panel: `common/event_panel.py` / `out/event_panel/` · `mm_quoting/out/panel_cache.json` for class/mo.
