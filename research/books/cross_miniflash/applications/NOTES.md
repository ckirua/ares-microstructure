# Applications — unified notes

**Slice:** ETH/BTC · HL + Deribit + Kraken · 2026-09-04…10 · gated n=275  
**SoT board:** [`../DESK_MEMO.md`](../DESK_MEMO.md) §7 · index [`README.md`](README.md) · JSON [`out/applications_board.json`](out/applications_board.json)

Honesty: Phase 4 cleared **0 tradable** Promotes. Sims label **risk-policy / MM playbook / feature / monitor** only.

| # | Package | Class | Verdict |
|---|---------|-------|---------|
| 1 | [`kill_ladder/`](kill_ladder/) | risk-policy | **Promote-as-risk-policy** (venue-local) |
| 2 | [`nanex_burst/`](nanex_burst/) | risk-policy | **Promote-as-risk-policy** + burst tag |
| 3 | [`hl_thin_sor/`](hl_thin_sor/) | monitor | strip yes / hard size-cap **Hold** |
| 4 | [`hv_fei_capacity/`](hv_fei_capacity/) | monitor | dashboard yes / schedule **Hold** |
| 5 | [`mm_quoting/`](mm_quoting/) | MM playbook | **Promote (med)** V-restore |
| 6 | [`feature_models/`](feature_models/) | feature | VPIN×size **Promote (med)** · occurrence Soft Promote · tape/duration Hold |
| 7 | [`signal_boards/`](signal_boards/) | viz/research | MI · bootstrap/ROC · Beta–Binomial + MH logistic · heatmaps |
| 8 | [`strategy_lab/`](strategy_lab/) | tick/OB equity sims | Marked PnL curves · ladder/Nanex/V/HL overlays · [`STRATEGY_LAB.md`](strategy_lab/STRATEGY_LAB.md) |

**Open first (equity/sims):** [`strategy_lab/strategy_lab.ipynb`](strategy_lab/strategy_lab.ipynb) · figs [`strategy_lab/out/figs/`](strategy_lab/out/figs/).  
**Signal/info-theory boards:** [`../notebooks/full_research_board.ipynb`](../notebooks/full_research_board.ipynb) · [`out/signal_boards/figs/`](out/signal_boards/figs/).

See [`../TRADING_APPLICATIONS.md`](../TRADING_APPLICATIONS.md) §5b.
