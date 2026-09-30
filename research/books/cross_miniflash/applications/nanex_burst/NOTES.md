# Nanex∩SSM burst escalate

**Track:** RISK · **Objects:** `info.nanex_subset_of_ssm`  
**Rule:** Nested tag = high-precision burst escalate (temporary protect). Nanex alone = do not fire.

## Design

Compare gated SSM events with Nanex overlap vs SSM-only on severity, markout, recovery.
Precision = P(SSM|Nanex). Early/late + bootstrap on Δ|mo|.

## Honesty

Auto-pull is **med** until friction+CI clear; tag itself is **Promote monitor**.
