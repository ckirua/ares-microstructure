#!/usr/bin/env python3
"""Multi-day VPIN panel — Pass 1 desk runner.

  python3 scripts/exp_vpin_panel.py --symbols ETH BTC --venues hyperliquid deribit --last-n-days 25

Writes:
  out/vpin_panel/rows.jsonl
  out/vpin_panel/summary.json
  out/vpin_panel/decisions.json
  out/vpin_panel/pin_compare.json
  out/vpin_panel/bucket_calibration.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import (  # noqa: E402
    CORE_VENUES,
    load_day_trades,
    normalize_side,
    normalize_venue,
    resolve_bucket_volume,
    resolve_days,
)
from ares_micro.flow.continuous import trade_intensity, vpin_bucket  # noqa: E402  # noqa: E402
from ares_micro.flow.vpin import vpin_bucket  # noqa: E402
from ares_micro.flow.pin import (  # noqa: E402
    compare_pin_vpin,
    daily_buy_sell_counts,
    eho_pin_mle,
    pin_proxy_from_days,
)
from ares_micro.stats import bootstrap_ci  # noqa: E402
from ares_micro.flow.vpin import (  # noqa: E402
    falsify_side_shuffle,
    rolling_vpin,
    vpin_from_tape,
    vpin_time_split,
    cross_section_spearman,
    summarize_panel_vpin,
)

OUT = BOOK / "out" / "vpin_panel"
LISTING = Path.home() / ".cache" / "warehouse" / "listings"


def _listing_days(bucket: str) -> list[str]:
    root = LISTING / bucket
    if not root.is_dir():
        return []
    return sorted(p.stem for p in root.glob("*.json"))


def _all_intersection_days() -> list[str]:
    sets = [
        set(_listing_days("mercat-hyperliquid-md")),
        set(_listing_days("mercat-deribit-md")),
        set(_listing_days("mercat-kraken-md")),
    ]
    if not all(sets):
        return []
    return sorted(set.intersection(*sets))


def _panel_day_row(
    venue: str,
    symbol: str,
    day: str,
    *,
    max_files: int,
    n_buckets_window: int,
    bucket_scale: float,
    target_buckets: float | None,
    n_shuffle: int,
) -> dict[str, Any]:
    rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
    comp = rec.get("completeness") or {}
    tape = rec["tape"]
    side = normalize_side(np.asarray(tape["side"], dtype=np.float64))
    qty = np.asarray(tape["qty"], dtype=np.float64)
    ts = np.asarray(tape["ts"], dtype=np.int64)
    bucket_v, bucket_method = resolve_bucket_volume(
        qty, bucket_scale=bucket_scale, target_buckets=target_buckets
    )
    vpin = vpin_from_tape(
        side,
        qty,
        ts,
        bucket_volume=bucket_v,
        multiplier=bucket_scale,
        n_buckets_window=n_buckets_window,
    )
    roll = np.asarray(vpin.get("roll_series", []), dtype=np.float64)
    ends = np.asarray(vpin.get("bucket_end_ts", []), dtype=np.int64)
    tsplit = vpin_time_split(roll, ends if ends.size else None)
    shuffle = falsify_side_shuffle(
        side,
        qty,
        bucket_volume=bucket_v,
        n_buckets_window=n_buckets_window,
        n_shuffle=n_shuffle,
    )
    intens = trade_intensity(ts, bar_ns=1_000_000_000)
    n = int(side.size)
    buy = int((side > 0).sum())
    sell = int((side < 0).sum())
    imb = float(buy - sell) / max(n, 1)
    days_bs = daily_buy_sell_counts(ts, side, day_labels=[day] * n)
    proxy = pin_proxy_from_days(days_bs)
    day_bs = days_bs.get(day) or days_bs.get(str(day)) or next(iter(days_bs.values()), {})
    row: dict[str, Any] = {
        "ok": bool(comp.get("complete") and vpin.get("n_buckets", 0) >= 20),
        "venue": normalize_venue(venue),
        "symbol": symbol,
        "day": day,
        "instrument": rec.get("instrument"),
        "n_trades": comp.get("n"),
        "n_buckets": vpin.get("n_buckets"),
        "bucket_volume": bucket_v,
        "bucket_method": bucket_method,
        "total_volume": vpin.get("total_volume"),
        "mean_vpin": vpin.get("mean_vpin"),
        "vpin_ci95": vpin.get("vpin_ci95"),
        "p50_vpin": vpin.get("p50_vpin"),
        "p50_roll_vpin": vpin.get("p50_roll_vpin"),
        "last_vpin": vpin.get("last_vpin"),
        "pin_proxy": proxy.get("pin_proxy"),
        "day_bs": day_bs,
        "buy_sell_imb": imb,
        "intensity_lambda": intens.get("mean_lambda"),
        "coverage": comp.get("coverage"),
        "complete": comp.get("complete"),
        "completeness": comp,
        "time_split": tsplit,
        "side_shuffle": shuffle,
        "n_buckets_window": n_buckets_window,
    }
    if rec.get("error"):
        row["error"] = rec["error"]
        row["ok"] = False
    return row


def _bucket_calibration(
    venue: str,
    symbol: str,
    day: str,
    *,
    max_files: int,
    n_buckets_window: int,
) -> dict[str, Any]:
    """Grid: median×scale vs target ~50 buckets/day (desk level check)."""
    rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
    tape = rec["tape"]
    side = normalize_side(np.asarray(tape["side"], dtype=np.float64))
    qty = np.asarray(tape["qty"], dtype=np.float64)
    ts = np.asarray(tape["ts"], dtype=np.int64)
    grid: list[dict[str, Any]] = []
    for scale in (25.0, 50.0, 100.0):
        bv, _ = resolve_bucket_volume(qty, bucket_scale=scale)
        v = vpin_from_tape(side, qty, ts, bucket_volume=bv, n_buckets_window=n_buckets_window)
        grid.append(
            {
                "method": f"median_x_{int(scale)}",
                "bucket_scale": scale,
                "bucket_volume": bv,
                "n_buckets": v.get("n_buckets"),
                "mean_vpin": v.get("mean_vpin"),
                "p50_vpin": v.get("p50_vpin"),
            }
        )
    for tb in (30.0, 50.0, 100.0):
        bv, _ = resolve_bucket_volume(qty, target_buckets=tb)
        v = vpin_from_tape(side, qty, ts, bucket_volume=bv, n_buckets_window=n_buckets_window)
        grid.append(
            {
                "method": f"target_{int(tb)}_buckets",
                "target_buckets": tb,
                "bucket_volume": bv,
                "n_buckets": v.get("n_buckets"),
                "mean_vpin": v.get("mean_vpin"),
                "p50_vpin": v.get("p50_vpin"),
            }
        )
    default_bv, default_tag = resolve_bucket_volume(qty, bucket_scale=50.0)
    return {
        "venue": normalize_venue(venue),
        "symbol": symbol,
        "day": day,
        "completeness": rec.get("completeness"),
        "default_method": default_tag,
        "default_bucket_volume": default_bv,
        "grid": grid,
        "desk_choice": (
            "Keep median(qty)×50 as SoT (matches empirical_mm Ch.15 / continuous.vpin_bucket). "
            "High rolling mean_vpin (~0.6–0.95) on crypto is expected: 50-bucket roll smooths "
            "micro-bucket imbalances; levels are not comparable to EHO PIN∈(0,1). "
            "Use target_buckets≈50 only for robustness / level diagnostics, not Promote gates."
        ),
    }


def _pin_pool(rows: list[dict[str, Any]], venue: str, symbol: str) -> dict[str, Any]:
    ok = [r for r in rows if r.get("ok") and r["venue"] == venue and r["symbol"] == symbol]
    days_bs: dict[str, dict[str, float]] = {}
    for r in ok:
        bs = r.get("day_bs")
        if isinstance(bs, dict) and bs.get("B") is not None:
            days_bs[str(r["day"])] = bs
    mle = eho_pin_mle(days_bs, symmetric=False, delta_fixed=0.5, min_trades_per_day=500, min_span_h=4.0)
    proxy = pin_proxy_from_days(days_bs)
    # Pooled VPIN: volume-weighted mean of day means (avoid re-loading full tapes).
    mv = np.array([r["mean_vpin"] for r in ok if np.isfinite(r.get("mean_vpin", float("nan")))])
    nb = np.array([r.get("n_buckets", 0) for r in ok], dtype=np.float64)
    if mv.size:
        w = nb[: mv.size]
        w = np.where(w > 0, w, 1.0)
        vpin = {
            "n_buckets": int(np.nansum(nb)),
            "mean_vpin": float(np.average(mv, weights=w)),
            "note": "bucket-weighted mean of day-level VPIN (Pass 1 fast pool)",
        }
    else:
        vpin = {"n_buckets": 0, "mean_vpin": float("nan")}
    cmp_ = compare_pin_vpin(mle, vpin)
    pp = np.array([r["pin_proxy"] for r in ok if np.isfinite(r.get("pin_proxy", float("nan")))])
    mv = np.array([r["mean_vpin"] for r in ok if np.isfinite(r.get("mean_vpin", float("nan")))])
    rho = cross_section_spearman(pp, mv) if pp.size >= 5 else {"n": float(pp.size), "rho": float("nan")}
    return {
        "venue": venue,
        "symbol": symbol,
        "n_ok_days": len(ok),
        "mle": mle,
        "proxy": proxy,
        "vpin_pooled": vpin,
        "compare": cmp_,
        "day_mean_vpin_vs_pin_proxy_spearman": rho,
    }


def _decisions(rows: list[dict[str, Any]], pin_blocks: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rows if r.get("ok")]
    hl_db = [r for r in ok if r["venue"] in ("hyperliquid", "deribit")]
    kr_ok = [r for r in ok if r["venue"] == "kraken"]

    agg = summarize_panel_vpin(ok)
    shuffle_pass = [
        r
        for r in ok
        if (r.get("side_shuffle") or {}).get("ok")
        and float((r["side_shuffle"] or {}).get("p_exceed", 1.0)) <= 0.05
    ]
    shuffle_rate = len(shuffle_pass) / max(len(ok), 1)
    tsplit_stable = []
    for r in ok:
        ts = r.get("time_split") or {}
        if not ts.get("ok"):
            continue
        e, l = ts.get("early_mean"), ts.get("late_mean")
        if np.isfinite(e) and np.isfinite(l) and abs(float(e) - float(l)) < 0.12:
            tsplit_stable.append(r)
    tsplit_rate = len(tsplit_stable) / max(len(ok), 1)

    # HL↔DB paired days (ETH/BTC)
    pairs: list[tuple[float, float]] = []
    by_key: dict[tuple[str, str, str], float] = {}
    for r in hl_db:
        by_key[(r["symbol"], r["day"], r["venue"])] = float(r["mean_vpin"])
    for sym in sorted({r["symbol"] for r in hl_db}):
        days = sorted({r["day"] for r in hl_db if r["symbol"] == sym})
        for d in days:
            a = by_key.get((sym, d, "hyperliquid"))
            b = by_key.get((sym, d, "deribit"))
            if a is not None and b is not None and np.isfinite(a) and np.isfinite(b):
                pairs.append((a, b))
    xvenue = cross_section_spearman(
        np.array([p[0] for p in pairs]),
        np.array([p[1] for p in pairs]),
    ) if len(pairs) >= 5 else {"n": float(len(pairs)), "rho": float("nan")}

    n_hl_db_ok = len(hl_db)
    construct_promote = n_hl_db_ok >= 30 and agg.get("n_ok", 0) >= 30
    construct_dec = "Promote" if construct_promote else "Hold"
    shuffle_dec = "Promote" if shuffle_rate >= 0.55 and len(ok) >= 20 else "Hold"
    tsplit_dec = "Promote" if tsplit_rate >= 0.7 and len(ok) >= 20 else "Hold"
    xvenue_dec = (
        "Promote"
        if xvenue.get("n", 0) >= 15 and np.isfinite(xvenue.get("rho", float("nan"))) and xvenue.get("lo", -1) >= 0.15
        else "Hold"
    )
    kr_dec = "Hold"  # partial tape — never Promote per desk memo
    pin_dec = "Hold"
    for blk in pin_blocks:
        if blk.get("n_ok_days", 0) >= 20 and blk.get("mle", {}).get("ok"):
            pin_dec = "Hold"  # level mismatch expected; correlation gate only
            rho = blk.get("day_mean_vpin_vs_pin_proxy_spearman", {})
            if rho.get("n", 0) >= 20 and np.isfinite(rho.get("rho", float("nan"))) and rho.get("lo", -1) > 0:
                pin_dec = "Promote"
            break

    table = [
        {
            "id": "cont.vpin_constructed",
            "decision": construct_dec,
            "evidence": f"n_ok={agg.get('n_ok')} HL+DB={n_hl_db_ok}; med mean_vpin bootstrap={agg.get('mean_vpin')}",
        },
        {
            "id": "cont.vpin_bucket_mean",
            "decision": construct_dec,
            "evidence": f"median×50 SoT; n_ok={agg.get('n_ok')}",
        },
        {
            "id": "info.vpin_side_shuffle",
            "decision": shuffle_dec,
            "evidence": f"pass_rate={shuffle_rate:.2f} (p_exceed≤0.05); n_ok={len(ok)}",
        },
        {
            "id": "info.vpin_time_split_stable",
            "decision": tsplit_dec,
            "evidence": f"stable_rate={tsplit_rate:.2f} |Δearly-late|<0.12; n_ok={len(ok)}",
        },
        {
            "id": "frag.xvenue_vpin_concord",
            "decision": xvenue_dec,
            "evidence": f"HL↔DB ρ={xvenue.get('rho')} CI=[{xvenue.get('lo')},{xvenue.get('hi')}] n={xvenue.get('n')}",
        },
        {
            "id": "disc.pin_proxy_vs_vpin",
            "decision": pin_dec,
            "evidence": "day-level proxy vs mean_vpin Spearman (not EHO level match)",
        },
        {
            "id": "frag.kraken_vpin",
            "decision": kr_dec,
            "evidence": f"Kraken n_ok={len(kr_ok)} — partial futures tape; label only",
        },
        {
            "id": "frag.hl_sol_empty",
            "decision": "Hold",
            "evidence": "HL SOL empty on probe — no Promote until instrument fix",
        },
    ]
    counts = {}
    for t in table:
        counts[t["decision"]] = counts.get(t["decision"], 0) + 1
    return {
        "n_rows": len(rows),
        "n_ok": len(ok),
        "n_ok_hl_db": n_hl_db_ok,
        "aggregate": agg,
        "falsifiers": {
            "side_shuffle_pass_rate": shuffle_rate,
            "time_split_stable_rate": tsplit_rate,
            "xvenue_spearman": xvenue,
        },
        "decision_table": table,
        "decision_counts": counts,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=["ETH", "BTC", "SOL"])
    ap.add_argument("--venues", nargs="+", default=list(CORE_VENUES))
    ap.add_argument("--last-n-days", type=int, default=25)
    ap.add_argument(
        "--all-days",
        action="store_true",
        help="Use intersection of HL+Deribit+Kraken listing caches (max history).",
    )
    ap.add_argument("--max-files", type=int, default=24)
    ap.add_argument("--n-buckets-window", type=int, default=50)
    ap.add_argument("--bucket-scale", type=float, default=50.0)
    ap.add_argument("--target-buckets", type=float, default=None)
    ap.add_argument("--n-shuffle", type=int, default=80)
    ap.add_argument(
        "--include-incomplete",
        action="store_true",
        help="Keep incomplete UTC days (default: complete-only panel).",
    )
    ap.add_argument("--calibration-day", default="2026-09-30")
    ap.add_argument("--calibration-venue", default="hyperliquid")
    ap.add_argument("--calibration-symbol", default="ETH")
    args = ap.parse_args()
    complete_only = not args.include_incomplete

    OUT.mkdir(parents=True, exist_ok=True)
    log_path = OUT / "run.log"
    rows: list[dict[str, Any]] = []

    if args.all_days:
        all_days = _all_intersection_days()
    else:
        all_days = []

    for v in args.venues:
        vnorm = normalize_venue(v)
        days = all_days if all_days else resolve_days(None, vnorm, n=args.last_n_days)
        for sym in args.symbols:
            for day in days:
                msg = f"vpin {vnorm} {sym} {day}"
                print(msg, flush=True)
                with log_path.open("a") as lf:
                    lf.write(msg + "\n")
                try:
                    row = _panel_day_row(
                        vnorm,
                        sym,
                        day,
                        max_files=args.max_files,
                        n_buckets_window=args.n_buckets_window,
                        bucket_scale=args.bucket_scale,
                        target_buckets=args.target_buckets,
                        n_shuffle=args.n_shuffle,
                    )
                except Exception as exc:  # noqa: BLE001
                    row = {
                        "ok": False,
                        "venue": vnorm,
                        "symbol": sym,
                        "day": day,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                if complete_only and not row.get("complete"):
                    row["ok"] = False
                rows.append(row)

    jsonl = OUT / "rows.jsonl"
    with jsonl.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    cal = _bucket_calibration(
        args.calibration_venue,
        args.calibration_symbol,
        args.calibration_day,
        max_files=args.max_files,
        n_buckets_window=args.n_buckets_window,
    )
    (OUT / "bucket_calibration.json").write_text(json.dumps(cal, indent=2) + "\n")

    pin_blocks = []
    for v in args.venues:
        vnorm = normalize_venue(v)
        for sym in args.symbols:
            pin_blocks.append(_pin_pool(rows, vnorm, sym))
    (OUT / "pin_compare.json").write_text(json.dumps(pin_blocks, indent=2) + "\n")

    decisions = _decisions(rows, pin_blocks)
    decisions["symbols"] = args.symbols
    decisions["venues"] = [normalize_venue(v) for v in args.venues]
    decisions["bucket_scale"] = args.bucket_scale
    decisions["target_buckets"] = args.target_buckets
    decisions["panel_mode"] = "panel_exploratory"
    decisions["companion_artifact"] = "decisions_panel_promote.json"
    decisions["data_provenance"] = (
        "warehouse trade tape via startarb.data.trades.load_trade_tape; "
        "complete UTC days only when --include-incomplete unset; "
        "side_shuffle is sign-permutation null on real (side,qty), not synthetic tape"
    )
    hl_db_ok = [r for r in rows if r.get("ok") and r["venue"] in ("hyperliquid", "deribit")]
    pin_promote = [
        _pin_pool(hl_db_ok, normalize_venue(v), sym)
        for v in ("hyperliquid", "deribit")
        for sym in args.symbols
    ]
    promote = _decisions(hl_db_ok, pin_promote)
    promote["panel_mode"] = "panel_promote"
    promote["companion_artifact"] = "decisions.json"
    promote["symbols"] = args.symbols
    promote["venues"] = ["hyperliquid", "deribit"]
    promote["bucket_scale"] = args.bucket_scale
    promote["target_buckets"] = args.target_buckets
    promote["data_provenance"] = (
        "HL+Deribit warehouse trade tape only (Kraken excluded from row set); "
        "complete UTC days when --include-incomplete unset; "
        "desk provenance for Promote wiring claims"
    )
    (OUT / "summary.json").write_text(json.dumps(decisions, indent=2) + "\n")
    (OUT / "decisions.json").write_text(json.dumps(decisions, indent=2) + "\n")
    (OUT / "decisions_panel_promote.json").write_text(json.dumps(promote, indent=2) + "\n")
    panel_bundle = {
        **decisions,
        "meta": {
            "symbols": args.symbols,
            "venues": [normalize_venue(v) for v in args.venues],
            "days": sorted({r["day"] for r in rows}),
            "all_days": bool(args.all_days),
            "bucket_scale": args.bucket_scale,
            "complete_only": complete_only,
        },
        "coverage": {"n_rows": len(rows), "n_ok": decisions["n_ok"]},
        "rows": rows,
        "bucket_calibration": cal,
        "pin_compare": pin_blocks,
    }
    (OUT / "vpin_panel.json").write_text(json.dumps(panel_bundle, indent=2) + "\n")

    # chapter EXP_REPORT stubs
    ch = BOOK / "chapters" / "vpin_buckets" / "EXP_REPORT.md"
    lines = [
        "# VPIN buckets — panel Pass 1",
        "",
        f"- n_rows={decisions['n_rows']} n_ok={decisions['n_ok']} (HL+DB ok={decisions['n_ok_hl_db']})",
        f"- bucket SoT: median(qty)×{args.bucket_scale} — see `out/vpin_panel/bucket_calibration.json`",
        "",
        "| id | decision | evidence |",
        "|----|----------|----------|",
    ]
    for t in decisions["decision_table"]:
        lines.append(f"| `{t['id']}` | **{t['decision']}** | {t['evidence'][:120]} |")
    ch.write_text("\n".join(lines) + "\n")

    print(json.dumps({"n_ok": decisions["n_ok"], "counts": decisions["decision_counts"]}, indent=2))


if __name__ == "__main__":
    main()
