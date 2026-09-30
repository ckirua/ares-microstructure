# Classic micro candidates

| id | type | decision | falsifier |
|----|------|----------|-----------|
| `tox.markout_1s` | D→E toxicity | **Promote** (if CI>0) | Held-out CI ≤0 or side flip |
| `spread.effective_vs_quoted` | D TCA | **Promote** | Effective ≪ ½ quoted (bad join) |
| `spread.roll` | D | **Kill** when unidentified | cov(Δp)≥0 |
| `book.resilience` | D | **Promote/Hold** by n_events | Flat depth ratio |
| `sess.utc_hour_share` | D schedule | **Promote/Hold** by coverage | Flat hours / thin sample |
