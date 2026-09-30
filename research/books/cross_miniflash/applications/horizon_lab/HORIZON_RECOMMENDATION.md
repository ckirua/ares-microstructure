# Horizon recommendation — mini-flash / risk-overlay sampling

_Generated 2026-09-30T20:45:19.720033+00:00. Evidence: `applications/horizon_lab/out/EXP_REPORT.md`._

## One-paragraph answer

**300 / 9000 are doable as intensity windows on event-time detection — not as SSM observation bars.** On HL ETH (27 days), trade-by-trade SSM yields ~9.0 gated crashes/day with kill-ladder Δ|mo|≈**+9.6 bps** CI[6.1, 13.5] (**Promote**). Last-print **N=300** (~3.4 min) and **N=9000** (~45 min) detection bars yield **0** gated crashes/day (**Kill**) — mini-flashes die inside the bar. As **intensity** knobs on the same event tape, trade_300…trade_3000 still **Promote**; trade_9000 softens to **Hold** (CI includes 0, early/late unstable). Calendar **1s** is the only coarse *detection* channel that retains usable rate (~3.1/day, Hold). Default paper-live: **event SSM + wall_60s intensity** (wake coalesce ≤1 s OK); research add **cal_1s** robustness. Do not put the KF on 300/9000 trade closes.

## Recommended defaults

1. **Paper-live / kill-ladder:** **event-time SSM + `wall_60s` intensity** (optional coalesce ≤1 s). Acceptable MFT intensity alts: `trade_300`–`trade_3000`. Avoid `trade_9000` intensity as default.
2. **Research detection:** **primary `event`; secondary `cal_1s`** (~3.1 gated/day, Hold). OHLC-300 is underpowered Hold — not a default.
3. **Avoid for detection:** **`trade_last_300` / `trade_last_9000` / ≥900 OHLC / 1m calendar** (gated≈0).

## Clock cheat-sheet (HL ETH)

| N trades | ≈ wall time | Detection? |
|---------:|------------:|:-----------|
| 100 | 64s | **Hold** (0.30 gated/day) |
| 300 | 202s | **Kill** (0.00 gated/day) |
| 900 | 605s | **Kill** (0.00 gated/day) |
| 3000 | 1924s | **Kill** (0.00 gated/day) |
| 9000 | 2704s | **Kill** (0.00 gated/day) |

## Warehouse vs ms tape

Warehouse TOB on Phase-4 core days is **seconds–minutes** (expanded_lab: core median Δt≃177s; dense collector days ~0.55s). Sub-second queue-position / outside-TOB claims need collector TOB. Crash SSM here is **trade-tape** event-time — that path is available at ms resolution even when BBO is sparse. Do not confuse warehouse quote cadence with trade-tick horizons.

## Liquidity

Day Amihud vs event gated Spearman=-0.06501547987616099; mean gated event/cal1s/trade300=8.962962962962964/3.074074074074074/0.0. Coarse trade-N clocks stay near-zero across Amihud terciles — optimal **detection** horizon does **not** shift into 300/9000 when liquidity worsens; thin/Amihud-high days still need event or ≤1s clocks. Diurnal scheduling (UTC peak) remains a prior (R03 Hold), not a bar-size switch.

