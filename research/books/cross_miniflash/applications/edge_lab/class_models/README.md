# Class models — V vs continuation (soft fade size)

**Job:** classify oracle V@5s from causal + nest/intensity features → map P̂(V) to fade size.  
**Not** mid prediction. **`mo_5s` is outcome only** (see [`LEAKAGE.md`](LEAKAGE.md)).

## Layout

| path | role |
|------|------|
| `feature_store.py` | panel_cache ⊕ event_panel join; design matrix |
| `models.py` | logistic + sklearn GBM; chrono AUC/Brier/calibration |
| `sizing.py` | P(V)→size; OOS net bps after RT=4 vs always-fade / hard V-rule |
| `run_class_models.py` | experiment runner → `out/` |
| `class_models.ipynb` | desk notebook (reload summary + figs) |
| `LEAKAGE.md` | leakage checklist |
| `out/EXP_REPORT.md` | scoreboard + verdict |

## Run

```bash
cd research/books/cross_miniflash/applications/edge_lab/class_models
python3 run_class_models.py
```

## Promote bar

Soft-size OOS **paired lift** vs `hard_v_rule` **and** vs `always_fade` must clear bootstrap CI with lo ≥ 0.25 bps each (fragile clears → Hold). Classifier AUC alone → Hold.

Honesty: `research_sim` · `alpha_claim=False` · no ClickHouse MCP · no commit required for this lab.
