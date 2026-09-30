# Estimators — five ladders → TSRV

**Status:** `exp_run`  
**Lib:** [`../../../lib/tsrv.py`](../../../lib/tsrv.py)  
**Pass 2:** K/step ablation + trade-clock in `scripts/exp_pass2_harden.py`.

## Pass results
- Ablation: first_adj CV < 0.5 on all 18 ETH+BTC venue-days (`fragile=0`).
- Calendar fifth/fourth median ≈ 0.95 → Kill noise-domination claim.
- Trade-clock fifth/fourth median ≈ 0.74 → Kill bounce-domination on last-print trades.
- `cont.tsrv_first_adj` **Hold** (stable but no OOS Promote).
