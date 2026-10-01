from __future__ import annotations
#!/usr/bin/env python3
"""daily_minv + event_case empirics (Pass 1+2) for v_shapes."""

import os

import argparse
import json
import sys
from pathlib import Path

import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(Path(os.environ.get('WAREHOUSE_SRC') or ((Path(os.environ.get('WAREHOUSE_ROOT') or (Path.home() / 'lab' / 'lab-n2070' / 'warehouse')) / 'src')))))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb')) / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import CORE_VENUES, ensure_env, load_day_trades, resolve_days  # noqa: E402
from research.lib.vstat import bootstrap_minv_ci, grid_1s, min_v, returns_from_log_px  # noqa: E402

try:
    from research.lib.crash import nanex_detect, vshape_events  # noqa: E402
except Exception:  # noqa: BLE001
    nanex_detect = vshape_events = None  # type: ignore

OUT_D = BOOK / "out" / "daily_minv"
OUT_E = BOOK / "out" / "event_case"
HN_MIN = (1, 5, 30)


def _minv_day(tape: dict, hn_s: float, *, n_grid: int = 51, n_boot: int = 40, dt_s: float = 5.0) -> dict:
    g = grid_1s(tape["ts"], tape["px"], dt_s=dt_s)
    if int(g["n_filled"]) < 60:
        return {"ok": False, "reason": "short_grid"}
    t, r = returns_from_log_px(g["log_px"], g["ts_ns"], time_unit_s=1.0)
    t0, t1 = float(t[0] + hn_s), float(t[-1] - hn_s)
    if t1 <= t0:
        return {"ok": False, "reason": "hn_too_wide"}
    taus = np.linspace(t0, t1, n_grid)
    mv = min_v(t, r, taus, hn_s)
    boot = bootstrap_minv_ci(r, hn_s, n_paths=n_boot, n_grid=min(n_grid, 41), rng=np.random.default_rng(1), dt_s=float(g["dt_s"]))
    q5, q1 = boot["quantiles"].get(0.05), boot["quantiles"].get(0.01)
    post = {}
    if np.isfinite(mv["tau_star"]):
        i0 = int(np.searchsorted(t, mv["tau_star"]))
        for horizon in (60, 300, 1800):
            # horizon in seconds → index steps ≈ horizon / dt
            step = max(1, int(horizon / float(g["dt_s"])))
            i1 = min(r.size, i0 + step)
            if i1 > i0:
                post[f"ret_{horizon}s"] = float(np.sum(r[i0:i1]))
    geom = {}
    if vshape_events is not None and g["px"].size > 50:
        ve = vshape_events(g["ts_ns"], g["px"], min_pct=0.005, max_leg_s=float(hn_s), min_recovery=0.4)
        geom["n_vshape_events"] = int(ve["n_events"])
    if nanex_detect is not None and g["px"].size > 50:
        nx = nanex_detect(g["ts_ns"], g["px"], min_pct=0.005, max_window_s=min(1.5, hn_s))
        geom["n_nanex"] = int(nx["n_events"])
    return {
        "ok": True,
        "min_v": mv["min_v"],
        "tau_star_s": mv["tau_star"],
        "shape": mv["shape"],
        "sig_5": bool(np.isfinite(mv["min_v"]) and np.isfinite(q5) and mv["min_v"] < q5),
        "sig_1": bool(np.isfinite(mv["min_v"]) and np.isfinite(q1) and mv["min_v"] < q1),
        "q05": q5,
        "q01": q1,
        "post_trough": post,
        "geom": geom,
        "n_grid_px": int(g["n_filled"]),
        "coverage": float(g["coverage"]),
        "dt_s": float(g["dt_s"]),
    }


def build_panel(symbol: str, days: list[str], *, max_files: int, fast: bool) -> dict:
    ensure_env()
    n_grid = 41 if fast else 51
    n_boot = 25 if fast else 40
    panel = {"symbol": symbol, "days": days, "rows": []}
    for venue in CORE_VENUES:
        for day in days:
            try:
                rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
            except Exception as exc:  # noqa: BLE001
                panel["rows"].append({"venue": venue, "day": day, "error": str(exc)})
                continue
            for hm in HN_MIN:
                try:
                    out = _minv_day(rec["tape"], float(hm * 60), n_grid=n_grid, n_boot=n_boot)
                except Exception as exc:  # noqa: BLE001
                    out = {"ok": False, "error": str(exc)}
                panel["rows"].append(
                    {
                        "venue": venue,
                        "day": day,
                        "hn_min": hm,
                        "complete": rec["completeness"].get("complete"),
                        "n_trades": rec["completeness"].get("n"),
                        **out,
                    }
                )
    OUT_D.mkdir(parents=True, exist_ok=True)
    (OUT_D / f"daily_minv_{symbol.lower()}.json").write_text(json.dumps(panel, indent=2, default=str))
    return panel


def pick_stress_day(panel: dict) -> dict | None:
    """Most negative significant MinV among complete days (5m preferred)."""
    cands = [
        r
        for r in panel["rows"]
        if r.get("ok") and r.get("complete") and r.get("hn_min") == 5 and np.isfinite(r.get("min_v", np.nan))
    ]
    if not cands:
        cands = [r for r in panel["rows"] if r.get("ok") and np.isfinite(r.get("min_v", np.nan))]
    if not cands:
        return None
    return min(cands, key=lambda r: r["min_v"])


def write_event_case(symbol: str, stress: dict | None, panel: dict) -> None:
    OUT_E.mkdir(parents=True, exist_ok=True)
    ch = BOOK / "chapters" / "event_case"
    ch.mkdir(parents=True, exist_ok=True)
    payload = {"symbol": symbol, "stress": stress, "note": "Hold auction-loss ID"}
    (OUT_E / f"event_{symbol.lower()}.json").write_text(json.dumps(payload, indent=2, default=str))

    if stress is None:
        body = [
            "# Event case — EXP_REPORT",
            "",
            "No usable stress day found (empty / incomplete panel).",
            "",
            "## Pass 2 Hold",
            "- Italian auction wealth-transfer ID: **Hold** (out of scope).",
        ]
    else:
        body = [
            "# Event case — EXP_REPORT (Pass 1+2)",
            "",
            f"## Stress day pick",
            f"- Venue: `{stress['venue']}` day `{stress['day']}` hn={stress['hn_min']}m",
            f"- MinV={stress['min_v']:.4f} shape={stress['shape']} sig5={stress['sig_5']} sig1={stress['sig_1']}",
            f"- Post-trough returns: {stress.get('post_trough')}",
            f"- Geometric overlap: {stress.get('geom')}",
            "",
            "## Regime proxy (Pass 2)",
            "- BaU → trough → post: use pre/post return windows above; not an auction mechanism.",
            "- Markout / maker-inventory analogue deferred to `liq_around_v` TOB join when available.",
            "",
            "## Hold",
            "- Causal taxpayer-loss / wealth-transfer ID: **Hold** (no crypto sovereign auction).",
            "",
            f"## Artifact",
            f"- `out/event_case/event_{symbol.lower()}.json`",
        ]
    report_name = "EXP_REPORT.md" if symbol.upper() == "ETH" else f"EXP_REPORT_{symbol.lower()}.md"
    (ch / report_name).write_text("\n".join(body) + "\n")
    # Notebooks owned by build_memo_notebooks.py — never stub-overwrite here.
    cand = ch / "CANDIDATES.md"
    if not cand.exists():
        cand.write_text(
            """| id | type | lenses | decision | falsifier |
|----|------|--------|----------|-----------|
| `risk.stress_day_minv` | case | risk, info | **Hold** (narrative monitor) | not reproducible across months |
| `id.auction_loss` | ID | mm | **Hold** | no crypto analogue — out of scope |
"""
        )


def write_daily_reports(panel: dict) -> None:
    ch = BOOK / "chapters" / "daily_minv"
    ch.mkdir(parents=True, exist_ok=True)
    # counts
    ok = [r for r in panel["rows"] if r.get("ok")]
    sig5 = [r for r in ok if r.get("sig_5")]
    v_shapes = [r for r in sig5 if r.get("shape") == "V"]
    lam = [r for r in sig5 if r.get("shape") == "Lambda"]
    # time-split: first half vs second half of days
    days = sorted({r["day"] for r in ok if "day" in r})
    mid = len(days) // 2
    early, late = set(days[:mid]), set(days[mid:])
    early_sig = sum(1 for r in sig5 if r.get("day") in early)
    late_sig = sum(1 for r in sig5 if r.get("day") in late)

    lines = [
        "# Daily MinV — EXP_REPORT (Pass 1+2)",
        "",
        f"## Sample",
        f"- Symbol: `{panel['symbol']}` days={panel['days']}",
        f"- Rows ok={len(ok)} sig@5%={len(sig5)} V={len(v_shapes)} Lambda={len(lam)}",
        "",
        "## Time-split (Pass 2)",
        f"- Early days {sorted(early)}: sig5 count={early_sig}",
        f"- Late days {sorted(late)}: sig5 count={late_sig}",
        "",
        "## Post-trough (Table-2 style)",
    ]
    for r in sorted(sig5, key=lambda x: x.get("min_v", 0))[:8]:
        lines.append(
            f"- {r['venue']} {r['day']} hn={r['hn_min']}: MinV={r['min_v']:.3f} post={r.get('post_trough')} geom={r.get('geom')}"
        )
    lines += [
        "",
        "## Artifacts",
        f"- `out/daily_minv/daily_minv_{panel['symbol'].lower()}.json`",
        "",
    ]
    # Only rewrite EXP_REPORT for ETH primary panel; BTC appends a note file.
    if str(panel.get("symbol", "")).upper() == "ETH":
        (ch / "EXP_REPORT.md").write_text("\n".join(lines))
    else:
        (ch / f"EXP_REPORT_{str(panel['symbol']).lower()}.md").write_text("\n".join(lines))
    # Notebooks owned by build_memo_notebooks.py — never stub-overwrite here.


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--n-days", type=int, default=5)
    ap.add_argument("--days", nargs="*", default=None)
    ap.add_argument("--max-files", type=int, default=24)
    ap.add_argument("--fast", action="store_true")
    args = ap.parse_args()
    ensure_env()
    days = resolve_days(args.days, venue="hyperliquid", n=args.n_days)
    panel = build_panel(args.symbol, days, max_files=args.max_files, fast=args.fast)
    write_daily_reports(panel)
    stress = pick_stress_day(panel)
    write_event_case(args.symbol, stress, panel)
    print(json.dumps({"days": days, "n_rows": len(panel["rows"]), "stress": stress}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
