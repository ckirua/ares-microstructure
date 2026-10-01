from __future__ import annotations
#!/usr/bin/env python3
"""Build REAL path equity curves for Promote severity_zend (+ confirm_r2 peer).

Locks defaults: severity_zend |z|≥20 @+0.5s→3s fire_pause=prior_only adverse=off.
Writes:
  out/figs/equity_path_event.png
  out/figs/equity_path_calendar.png
  out/figs/equity_path_vs_confirm_r2.png
  out/trades_panel_severity_zend.jsonl
  out/trades_panel_confirm_r2.jsonl
  out/EQUITY.md
  patches SHADOW_BOARD.md + RISK_REPORT.md with embeds

live_orders=false. No ClickHouse MCP. No commit.
"""


import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PKG = Path(__file__).resolve().parent
sys.path.insert(0, str(PKG))

from harness.causal import jsonable  # noqa: E402
from harness.config import load_config  # noqa: E402
from harness.equity import (  # noqa: E402
    equity_stats,
    path_pnls,
    write_equity_markdown,
    write_path_equity_figs,
)
from harness.pipeline import _detect_cfg, _load_paper_detect  # noqa: E402
from harness.strategy import simulate_day_fades  # noqa: E402

DAYS = [
    "2026-09-04",
    "2026-09-05",
    "2026-09-06",
    "2026-09-07",
    "2026-09-08",
    "2026-09-09",
    "2026-09-10",
]
VENUE = "hyperliquid"
SYMBOL = "ETH"

PROMOTE = {
    "entry_mode": "severity_zend",
    "confirm_s": 0.5,
    "exit_s": 3.0,
    "z_min": 20.0,
    "adverse_stop_bps": 1e9,
    "suppress_fire_pause": "prior_only",
    "always_fade": False,
}

HOLD = {
    "entry_mode": "confirm_r2",
    "confirm_s": 2.0,
    "exit_s": 5.0,
    "adverse_stop_bps": 12.0,
    "suppress_fire_pause": "prior_only",
    "always_fade": False,
}


def load_cells(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    detect = _load_paper_detect()
    dcfg = _detect_cfg(cfg)
    cells: list[dict[str, Any]] = []
    for day in DAYS:
        print(f"[equity] detect {day}…", flush=True)
        cell = detect(VENUE, SYMBOL, day, cfg=dcfg, quiet=True)
        if cell.get("skip") or (cfg.get("require_complete_day", True) and not cell.get("complete")):
            print(f"  skip {day}")
            continue
        cells.append(cell)
        print(f"  ssm_10_n={cell.get('ssm_10_n')}")
    return cells


def run_policy(cells: list[dict], base_cfg: dict, **vf_kw: Any) -> list[dict[str, Any]]:
    cfg = copy.deepcopy(base_cfg)
    vf = dict(cfg.get("v_fade") or {})
    vf.update(vf_kw)
    cfg["v_fade"] = vf
    trades: list[dict] = []
    for cell in cells:
        sim = simulate_day_fades(cell, cfg=cfg)
        trades.extend(sim.get("trades") or [])
    return trades


def _write_jsonl(path: Path, trades: list[dict[str, Any]], policy: str) -> None:
    with path.open("w") as f:
        for t in trades:
            row = dict(t)
            row.update(policy=policy, shadow_mode=True, live_orders=False)
            f.write(json.dumps(jsonable(row)) + "\n")


def _patch_md_equity_section(path: Path, section: str) -> None:
    if not path.is_file():
        return
    text = path.read_text()
    marker = "## Path equity curves"
    if marker in text:
        # replace existing section through next ## or end
        pre, rest = text.split(marker, 1)
        # drop old section body until next top-level ## (not ###)
        lines = rest.splitlines(keepends=True)
        body_end = 0
        for i, ln in enumerate(lines[1:], start=1):
            if ln.startswith("## ") and not ln.startswith("###"):
                body_end = i
                break
        else:
            body_end = len(lines)
        tail = "".join(lines[body_end:])
        text = pre.rstrip() + "\n\n" + section.rstrip() + "\n\n" + tail.lstrip()
    else:
        # insert before ## Honesty if present
        if "## Honesty" in text:
            text = text.replace("## Honesty", section.rstrip() + "\n\n## Honesty", 1)
        else:
            text = text.rstrip() + "\n\n" + section.rstrip() + "\n"
    path.write_text(text)


def main() -> None:
    out = PKG / "out"
    fig_dir = out / "figs"
    out.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    cfg = load_config(PKG / "config.yaml")
    cfg["venue"] = VENUE
    cfg["symbol"] = SYMBOL
    cfg["extra_venues"] = []
    cfg["live_orders"] = False
    # lock Promote defaults into cfg
    vf = dict(cfg.get("v_fade") or {})
    vf.update(PROMOTE)
    cfg["v_fade"] = vf

    cells = load_cells(cfg)
    if not cells:
        raise SystemExit("no cells")

    print("[equity] severity_zend Promote…", flush=True)
    sev = run_policy(cells, cfg, **PROMOTE)
    print("[equity] confirm_r2 Hold…", flush=True)
    conf = run_policy(cells, cfg, **HOLD)

    _write_jsonl(out / "trades_panel_severity_zend.jsonl", sev, "severity_zend")
    _write_jsonl(out / "trades_panel_confirm_r2.jsonl", conf, "confirm_r2")
    # keep primary trades.jsonl = Promote panel path (not living-day overwrite)
    _write_jsonl(out / "trades.jsonl", sev, "severity_zend")

    sev_label = "severity_zend |z|≥20 @0.5→3s prior_only"
    conf_label = "confirm_r2 @2→5 (path-late Hold)"
    figs = write_path_equity_figs(
        sev,
        fig_dir,
        label=sev_label,
        venue=VENUE,
        symbol=SYMBOL,
        peer_trades=conf,
        peer_label=conf_label,
        stem="equity_path",
    )
    write_equity_markdown(
        out_path=out / "EQUITY.md",
        severity_trades=sev,
        confirm_trades=conf,
        fig_paths=figs,
        policy=PROMOTE,
    )

    sev_st = equity_stats(path_pnls(sev))
    conf_st = equity_stats(path_pnls(conf))

    # Also refresh panel RISK_REPORT equity callout
    section = f"""## Path equity curves

**Promote default:** `severity_zend` · `|z|≥20` · `+0.5s→3s` · `fire_pause=prior_only` · adverse off · `live_orders=false`

| | n | path mean | final cum bps | max DD | hit |
|--|--:|----------:|--------------:|-------:|----:|
| **severity_zend** | {sev_st['n']} | {sev_st['mean_bps']:.2f} | **{sev_st['final_bps']:.1f}** | {sev_st['max_dd_bps']:.1f} | {sev_st['hit_rate']:.2f} |
| confirm_r2 @2→5 | {conf_st['n']} | {conf_st['mean_bps']:.2f} | {conf_st['final_bps']:.1f} | {conf_st['max_dd_bps']:.1f} | {conf_st['hit_rate']:.2f} |

![path equity event-time](figs/equity_path_event.png)

![path equity calendar-time](figs/equity_path_calendar.png)

![severity vs confirm_r2](figs/equity_path_vs_confirm_r2.png)

See [`EQUITY.md`](EQUITY.md) for how to read the curve and the **n={sev_st['n']}** caveat.
Generated: `{datetime.now(timezone.utc).isoformat()}`
"""
    _patch_md_equity_section(out / "SHADOW_BOARD.md", section)
    _patch_md_equity_section(out / "RISK_REPORT.md", section)
    _patch_md_equity_section(out / "RISK_ROLLUP.md", section)

    brief = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "live_orders": False,
        "policy": PROMOTE,
        "severity_zend": sev_st,
        "confirm_r2": conf_st,
        "figures": figs,
        "equity_md": str(out / "EQUITY.md"),
        "trades_severity": str(out / "trades_panel_severity_zend.jsonl"),
        "trades_confirm": str(out / "trades_panel_confirm_r2.jsonl"),
    }
    (out / "equity_meta.json").write_text(json.dumps(jsonable(brief), indent=2) + "\n")
    print(json.dumps(jsonable(brief), indent=2))
    print(f"[equity] wrote {len(figs)} figs → {fig_dir}", flush=True)


if __name__ == "__main__":
    main()
