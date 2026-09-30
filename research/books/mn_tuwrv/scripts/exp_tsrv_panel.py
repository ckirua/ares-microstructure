#!/usr/bin/env python3
"""TSRV + noise-proxy panel on HL + Deribit + Kraken (mn_tuwrv Pass 1).

Builds 1s last-print grids, runs all_estimators + noise_variance_proxy.
ClickHouse MCP banned — warehouse / startarb loaders only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(Path("/home/dev/lab/lab-n2070/warehouse/src")))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path("/home/dev/srv/ares-startarb") / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import (  # noqa: E402
    CORE_VENUES,
    ensure_env,
    load_day_trades,
    resolve_days,
)
from research.lib.tsrv import (  # noqa: E402
    all_estimators,
    grid_log_price_from_tape,
    log_returns,
    noise_variance_proxy,
)

OUT = BOOK / "out" / "tsrv_panel"
CH_NOISE = BOOK / "chapters" / "noise_proxy"
CH_EST = BOOK / "chapters" / "estimators"
CH_XV = BOOK / "chapters" / "xvenue_noise"


def _day_row(tape: dict, completeness: dict, *, K: int, step: int, dt_s: float) -> dict:
    g = grid_log_price_from_tape(tape["ts"], tape["px"], dt_s=dt_s)
    log_px = g["log_px"]
    if int(g["n_filled"]) < 60 or log_px.size < step + 2:
        return {
            "ok": False,
            "reason": "short_grid",
            "n_filled": int(g["n_filled"]),
            "coverage": float(g.get("coverage", 0.0)),
            "complete": bool(completeness.get("complete", False)),
        }
    est = all_estimators(log_px, K=K, step=step)
    noise = noise_variance_proxy(log_returns(log_px))
    fine = all_estimators(log_px, K=max(K // 5, 12), step=max(step // 5, 12))
    return {
        "ok": True,
        "n_trades": int(tape.get("n", len(tape["ts"]))),
        "n_filled": int(g["n_filled"]),
        "n_grid": int(g["n_grid"]),
        "coverage": float(g["coverage"]),
        "complete": bool(completeness.get("complete", False)),
        "completeness": completeness,
        "estimators": {
            k: float(est[k]) for k in ("fifth", "fourth", "third", "second", "first", "first_adj")
        },
        "noise_var": float(noise["noise_var"]),
        "noise_std": float(noise["noise_std"]),
        "n_returns": float(noise["n"]),
        "K": float(K),
        "step": float(step),
        "dt_s": float(dt_s),
        "fifth_over_fourth": (
            float(est["fifth"] / est["fourth"])
            if np.isfinite(est["fifth"]) and np.isfinite(est["fourth"]) and est["fourth"] > 0
            else float("nan")
        ),
        "fine_step_first_adj": float(fine["first_adj"]),
    }


def _write_reports(rows: list[dict], meta: dict) -> None:
    ok_rows = [r for r in rows if r.get("ok")]
    lines = [
        "# Noise proxy — EXP_REPORT (Pass 1)",
        "",
        "## Sample",
        f"- Symbol: `{meta['symbol']}`",
        f"- Days: {meta['days']}",
        f"- Venues: {list(CORE_VENUES)}",
        f"- Grid: {meta['dt_s']}s last-print; K={meta['K']} step={meta['step']}",
        "",
        "## Per-venue / day",
    ]
    for r in rows:
        tag = f"{r['venue']} {r['day']}"
        if not r.get("ok"):
            lines.append(f"- {tag}: FAIL {r.get('reason')} n_filled={r.get('n_filled')}")
            continue
        lines.append(
            f"- {tag}: noise_std={r['noise_std']:.6g} first_adj={r['estimators']['first_adj']:.6g} "
            f"fifth={r['estimators']['fifth']:.6g} fourth={r['estimators']['fourth']:.6g} "
            f"fifth/fourth={r['fifth_over_fourth']:.3g} complete={r['complete']} "
            f"coverage={r['coverage']:.2f} n_trades={r['n_trades']}"
        )
    by_day: dict[str, dict[str, float]] = {}
    for r in ok_rows:
        by_day.setdefault(r["day"], {})[r["venue"]] = float(r["noise_std"])
    lines += ["", "## X-venue noise_std (same day)", ""]
    for day, m in sorted(by_day.items()):
        lines.append(f"- {day}: " + ", ".join(f"{v}={m[v]:.6g}" for v in CORE_VENUES if v in m))
    lines += [
        "",
        "## Pass 1 notes",
        "- Noise variance from fifth-best on calendar grid (Romero eq 9 / ZMA05).",
        "- TSRV first_adj reported alongside sparse fourth for desk contrast.",
        "- Spread join / market_noise ranking deferred to Pass 2 when TOB dense.",
        "",
        f"- JSON: `{OUT.relative_to(BOOK)}/panel_{meta['symbol'].lower()}.json`",
        "",
    ]
    (CH_NOISE / "EXP_REPORT.md").write_text("\n".join(lines))

    est_lines = [
        "# Estimators — EXP_REPORT (Pass 1 tape)",
        "",
        f"- Symbol `{meta['symbol']}` days {meta['days']}; see noise_proxy for full table.",
        f"- ok_rows={len(ok_rows)} / {len(rows)}",
        "",
    ]
    (CH_EST / "EXP_REPORT.md").write_text("\n".join(est_lines))

    xv_lines = [
        "# X-venue noise — EXP_REPORT (Pass 1 stub)",
        "",
        "## Same-day noise_std",
    ]
    for day, m in sorted(by_day.items()):
        xv_lines.append(f"- {day}: " + ", ".join(f"{v}={m[v]:.6g}" for v in CORE_VENUES if v in m))
    xv_lines += [
        "",
        "## Status",
        "- Pass 1 concordance dump only; Pass 2 FEI/Epps + falsifiers pending.",
        "",
    ]
    (CH_XV / "EXP_REPORT.md").write_text("\n".join(xv_lines))
    # mark status bump
    xv_notes = (BOOK / "chapters" / "xvenue_noise" / "NOTES.md").read_text()
    if "**Status:** `todo`" in xv_notes:
        (BOOK / "chapters" / "xvenue_noise" / "NOTES.md").write_text(
            xv_notes.replace("**Status:** `todo`", "**Status:** `pass1`", 1)
        )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--days", default="", help="Comma YYYY-MM-DD; empty = resolve_days")
    ap.add_argument("--n-days", type=int, default=3)
    ap.add_argument("--K", type=int, default=300)
    ap.add_argument("--step", type=int, default=300)
    ap.add_argument("--dt-s", type=float, default=1.0)
    ap.add_argument("--max-files", type=int, default=24)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        ensure_env()
    except Exception as e:  # noqa: BLE001
        print(f"ensure_env warn: {e}", flush=True)

    day_list = [d.strip() for d in args.days.split(",") if d.strip()] or None
    days = resolve_days(day_list, venue="hyperliquid", n=args.n_days)
    if not days:
        print("No days resolved — writing empty panel.", flush=True)

    rows: list[dict] = []
    for day in days:
        for venue in CORE_VENUES:
            print(f"load {venue} {args.symbol} {day} …", flush=True)
            try:
                rec = load_day_trades(venue, args.symbol, day, max_files=args.max_files, quiet=True)
            except Exception as e:  # noqa: BLE001
                rows.append({"ok": False, "venue": venue, "day": day, "reason": f"load:{e}"})
                continue
            tape = rec.get("tape") or {}
            comp = rec.get("completeness") or {}
            if int(tape.get("n", 0)) < 10:
                rows.append(
                    {
                        "ok": False,
                        "venue": venue,
                        "day": day,
                        "reason": "empty_tape",
                        "n_filled": 0,
                        "complete": bool(comp.get("complete", False)),
                    }
                )
                continue
            row = _day_row(tape, comp, K=args.K, step=args.step, dt_s=args.dt_s)
            row["venue"] = venue
            row["day"] = day
            row["symbol"] = args.symbol
            rows.append(row)

    meta = {
        "symbol": args.symbol,
        "days": days,
        "K": args.K,
        "step": args.step,
        "dt_s": args.dt_s,
    }
    payload = {"meta": meta, "rows": rows}
    out_path = OUT / f"panel_{args.symbol.lower()}.json"
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    _write_reports(rows, meta)
    n_ok = sum(1 for r in rows if r.get("ok"))
    print(f"Wrote {out_path} ok={n_ok}/{len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
