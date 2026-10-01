from __future__ import annotations
#!/usr/bin/env python3
"""Rebuild TRADE_BOARD.md from out/rollup.json + trades.jsonl."""


import json
from pathlib import Path

PKG = Path(__file__).resolve().parent
OUT = PKG / "out"


def _fmt(x) -> str:
    if x is None:
        return "—"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    if v != v:  # nan
        return "—"
    return f"{v:.2f}"


def main() -> None:
    rollup_path = OUT / "rollup.json"
    trades_path = OUT / "trades.jsonl"
    if not rollup_path.is_file():
        print(f"missing {rollup_path}; run --panel-days first")
        return

    rollup = json.loads(rollup_path.read_text())
    trades = []
    if trades_path.is_file():
        for line in trades_path.read_text().splitlines():
            if line.strip():
                trades.append(json.loads(line))

    lab = rollup.get("lab_pnl_net_bps") or {}
    path = rollup.get("path_pnl_net_bps") or {}
    kills = rollup.get("kills") or {}
    flags = kills.get("flags") or {}

    flag_rows = "\n".join(
        f"| `{k}` | **{'TRIP' if v else 'ok'}** |" for k, v in flags.items()
    )

    # HL ETH trades (panel trades.jsonl is primary venue only)
    show = [t for t in trades if t.get("venue") == "hyperliquid" and t.get("symbol") == "ETH"]
    if not show:
        show = list(trades)
    show = show[:40]
    trade_rows = []
    for t in show:
        trade_rows.append(
            f"| {t.get('day')} | {t.get('event_i')} | {t.get('side_name')} | "
            f"{t.get('exit_reason')} | {_fmt(t.get('lab_pnl_net_bps'))} | "
            f"{_fmt(t.get('path_pnl_net_bps'))} | {_fmt(t.get('mo_5s'))} |"
        )

    day_rows = []
    xvenue_rows = []
    for r in rollup.get("results") or []:
        if not r.get("ok"):
            day_rows.append(f"| {r.get('day')} | — | FAIL | `{r.get('error') or r.get('skip')}` |")
            continue
        ci = r.get("lab_pnl_net_bps") or {}
        day_rows.append(
            f"| {r.get('day')} | {r.get('n_faded')} | {_fmt(ci.get('mean'))} | {_fmt(r.get('hit_rate_lab'))} |"
        )
        for ex in r.get("extra_venues") or []:
            xvenue_rows.append(
                f"| {r.get('day')} | {ex.get('venue')} | {ex.get('n_faded')} | {_fmt(ex.get('lab_mean'))} |"
            )

    adverse_n = sum(1 for t in trades if t.get("exit_reason") == "adverse_stop")
    time_n = sum(1 for t in trades if t.get("exit_reason") == "time_stop")

    md = f"""# V-fade trade board

Generated from `{rollup_path.name}` · primary **{rollup.get('venue')} {rollup.get('symbol')}** · extra `{rollup.get('extra_venues')}`

```bash
cd {PKG}
python3 run_v_fade_paper.py --panel-days --extra-venues deribit,kraken
python3 write_trade_board.py
```

## Panel scoreboard (lab identity = −mo₅ₛ − RT4)

| metric | value |
|--------|------:|
| n_ok days | {rollup.get('n_ok')} |
| n_faded (HL) | {rollup.get('n_faded')} |
| lab mean net bps | **{_fmt(lab.get('mean'))}** |
| lab CI | [{_fmt(lab.get('lo'))}, {_fmt(lab.get('hi'))}] |
| path mean net bps | {_fmt(path.get('mean'))} |
| path CI | [{_fmt(path.get('lo'))}, {_fmt(path.get('hi'))}] |
| early / late | {_fmt(rollup.get('early_mean'))} / {_fmt(rollup.get('late_mean'))} |
| hit-rate (lab) | {_fmt(rollup.get('hit_rate'))} |
| exits time / adverse | {time_n} / {adverse_n} |
| kill decision | **{kills.get('decision')}** |

### Honesty note — lab vs path

Lab scoreboard matches `exp_edge_lab.causal_fade_v_only` (−mo from **event end** @5s − RT).  
Executable path fills at **confirm (+2s)** → exit; residual hold ≈3s. Path CI can be ≤0 while lab Promote — do **not** claim live alpha until OE fill study.

## Kill flags

| flag | status |
|------|--------|
{flag_rows or '| — | — |'}

## Per-day (HL ETH)

| day | n_faded | mean lab net | hit |
|-----|---------|--------------|-----|
{chr(10).join(day_rows) or '| — | — | — | — |'}

## Extra venues (sparse)

| day | venue | n_faded | lab mean |
|-----|-------|---------|----------|
{chr(10).join(xvenue_rows) or '| — | — | — | — |'}

## Trades (first 40 HL ETH)

| day | event_i | side | exit | lab_net | path_net | mo_5s |
|-----|---------|------|------|---------|----------|-------|
{chr(10).join(trade_rows) or '| — | — | — | — | — | — | — |'}

_Full log: `out/trades.jsonl`. Per-day: `out/<day>_hyperliquid_ETH/RISK_REPORT.md`. Notebook: `v_fade_board.ipynb`._

## Honesty

research_sim · RT=4bps · mid_mo null → tape mo · live_orders=False · not MM · not live alpha · ClickHouse MCP banned
"""
    out = PKG / "TRADE_BOARD.md"
    out.write_text(md)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
