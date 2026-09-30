# Classic microstructure — EXP_REPORT

**Run:** `uv run python research/scripts/exp_classic_micro.py --symbol ETH` (from startarb env)  
**Out:** `research/out/classic_micro/`

## Headline (ETH, HL tape ∩ collector mid)

| Metric | Value |
|--------|-------|
| Trades / mids | ~37k / ~63k |
| Quoted spread | ~0.39 bps |
| Effective spread | ~0.89 bps |
| Realized 1s | ~0.00 bps |
| Markout 1s | **~0.44 bps** CI ≈ [0.43, 0.46] |
| Roll | unidentified → **Kill** |
| Resilience @1s (large trades) | n≈600; depth ratio dips then refills |
| Session coverage | 11 UTC hours active → **Hold** schedule claim |

## Desk read

Almost all of the effective spread is **adverse selection** (realized≈0, markout>0). Maker quotes earn the half-spread only if they can avoid toxic flow — size-tier markouts in JSON. Depth resilience is a refill proxy (not queue position). Session effects need fuller-day tapes.

## Promote

`tox.markout_1s`, `spread.effective_vs_quoted`, `book.resilience`  
**Kill:** `spread.roll` · **Hold:** `sess.utc_hour_share`
