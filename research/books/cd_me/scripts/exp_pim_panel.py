#!/usr/bin/env python3
"""Pass-1 PIM panel: VLOOP / TCOST / PIM on HL↔Deribit↔Kraken ETH.

Writes ``out/pim_vloop_tcost/`` JSON (+ optional figs). Warehouse / collector
TOB only — ClickHouse MCP banned. Monitor ≠ arb α.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
SCRIPTS = Path(__file__).resolve().parent
WAREHOUSE_SRC = Path(
    os.environ.get("WAREHOUSE_SRC")
    or (
        (Path(os.environ.get("WAREHOUSE_ROOT") or (Path.home() / "lab" / "lab-n2070" / "warehouse")) / "src")
    )
)
STARTARB = Path(os.environ.get("ARES_STARTARB") or (Path.home() / "srv" / "ares-startarb"))

for _p in (str(WAREHOUSE_SRC), str(STARTARB / "src"), str(ROOT), str(SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from _data import (  # noqa: E402
    day_bounds_ns,
    ensure_env,
    load_core_venues_day,
    load_cross_venue_tob,
    resolve_days,
    trade_volume_buckets,
)
from certified_panel import (  # noqa: E402
    GATE_DB_TOB_N,
    GATE_HL_TOB_N,
    GATE_PIM_2V_N_FINITE,
    annotate_title,
    primary_days as certified_primary_days,
)
from ares_micro.flow.cdme import (  # noqa: E402
    align_tob_panel,
    bucket_panel,
    pim_from_components,
    tcost_from_spreads,
    vloop_cross_venue,
)

OUT = BOOK / "out" / "pim_vloop_tcost"
# Real-quote default: HL↔Deribit. Kraken only via --include-kraken-spot (spot_l2).
DEFAULT_VENUES = ("hyperliquid", "deribit")



def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.floating, float)):
        x = float(obj)
        return x if np.isfinite(x) else None
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, np.ndarray):
        return _jsonable(obj.tolist())
    return obj


def _day_pim(
    symbol: str,
    day: str,
    *,
    dt_s: float = 5.0,
    bucket_s: float = 3600.0,
    max_lag_s: float = 30.0,
    venues: tuple[str, ...] = DEFAULT_VENUES,
    allow_kraken_synth: bool = False,
    min_pim_finite: int = GATE_PIM_2V_N_FINITE,
) -> dict[str, Any]:
    tob_pack = load_cross_venue_tob(
        symbol,
        day,
        venues=venues,
        allow_kraken_synth=allow_kraken_synth,
        require_real_quotes=True,
    )
    trades = load_core_venues_day(symbol, day, quiet=True)
    venues_tob = tob_pack.get("venues") or {}
    # Density gates on real quotes
    for v, floor in (("hyperliquid", GATE_HL_TOB_N), ("deribit", GATE_DB_TOB_N)):
        if v not in venues:
            continue
        tob = venues_tob.get(v)
        n = int((tob or {}).get("n") or (len(tob["ts"]) if tob and "ts" in tob else 0))
        if tob is None or n < floor:
            return {
                "ok": False,
                "day": day,
                "reason": f"incomplete_{v}_tob_n={n}<{floor}",
                "skipped": True,
                "tob_errors": tob_pack.get("errors"),
                "n_venues_tob": len(venues_tob),
                "kraken_mode": tob_pack.get("kraken_mode"),
            }
    if len(venues_tob) < 2:
        return {
            "ok": False,
            "day": day,
            "reason": "need_ge_2_venue_real_tob",
            "skipped": True,
            "tob_errors": tob_pack.get("errors"),
            "n_venues_tob": len(venues_tob),
            "kraken_mode": tob_pack.get("kraken_mode"),
        }
    # Refuse synth Kraken if it somehow slipped in
    kr = venues_tob.get("kraken")
    if kr and (kr.get("is_synth") or "trade_synth" in str(kr.get("source") or "")):
        return {
            "ok": False,
            "day": day,
            "reason": "refused_kraken_trade_synth_PROXY_NOT_TOB",
            "skipped": True,
            "kraken_mode": "trade_synth",
        }

    lo, hi = day_bounds_ns(day)
    panel = align_tob_panel(
        venues_tob,
        dt_s=dt_s,
        max_lag_s=max_lag_s,
        day_start_ns=lo,
        day_end_ns=hi,
    )
    if panel["n"] < 60:
        return {
            "ok": False,
            "day": day,
            "reason": "short_aligned_panel",
            "n": panel["n"],
            "coverage": panel.get("coverage"),
            "tob_errors": tob_pack.get("errors"),
        }

    vl = vloop_cross_venue(panel["mid"])
    hs = panel["half_spread"]
    # use venues that appear in both mid and half_spread
    hs_list = [hs[v] for v in panel["venues"] if v in hs]
    tcost = tcost_from_spreads(hs_list)
    vloop = vl["vloop_max"]
    pim = pim_from_components(vloop, tcost)

    # home-venue volume (HL preferred)
    home = "hyperliquid" if "hyperliquid" in (trades.get("venues") or {}) else next(
        iter(trades.get("venues") or {}), None
    )
    vol_bucket = None
    home_complete = None
    if home and isinstance(trades["venues"].get(home), dict):
        rec = trades["venues"][home]
        home_complete = rec.get("completeness")
        if "tape" in rec:
            vol_bucket = trade_volume_buckets(rec["tape"], bucket_s=bucket_s, day=day)

    values = {
        "vloop": vloop,
        "tcost": tcost,
        "pim": pim,
    }
    for k, series in (vl.get("pairs") or {}).items():
        values[f"vloop_{k}"] = series
    buck = bucket_panel(panel["ts"], values, bucket_s=bucket_s)

    # join home notional onto hourly buckets by nearest center
    hourly = {
        "ts": buck["ts"].tolist(),
        "counts": buck["counts"].tolist(),
        "vloop": buck["means"].get("vloop"),
        "tcost": buck["means"].get("tcost"),
        "pim": buck["means"].get("pim"),
        "notional": None,
        "imbalance": None,
    }
    for key in ("vloop", "tcost", "pim"):
        arr = buck["means"].get(key)
        hourly[key] = [float(x) if np.isfinite(x) else None for x in (arr if arr is not None else [])]

    if vol_bucket is not None and vol_bucket["ts"].size and buck["ts"].size:
        # asof map volume centers → pim centers
        vts = vol_bucket["ts"]
        pts = buck["ts"]
        idx = np.searchsorted(vts, pts)
        idx = np.clip(idx, 0, vts.size - 1)
        # also try left neighbor if closer
        left = np.clip(idx - 1, 0, vts.size - 1)
        use_left = np.abs(pts - vts[left]) < np.abs(pts - vts[idx])
        idx = np.where(use_left, left, idx)
        hourly["notional"] = [float(vol_bucket["notional"][i]) for i in idx]
        hourly["imbalance"] = [
            float(vol_bucket["imbalance"][i]) if np.isfinite(vol_bucket["imbalance"][i]) else None
            for i in idx
        ]
    else:
        n_h = len(hourly["ts"])
        hourly["notional"] = [None] * n_h
        hourly["imbalance"] = [None] * n_h

    finite_pim = pim[np.isfinite(pim)]
    finite_vl = vloop[np.isfinite(vloop)]
    finite_tc = tcost[np.isfinite(tcost)]
    common = np.isfinite(vloop) & np.isfinite(tcost)
    corr_vt = (
        float(np.corrcoef(vloop[common], tcost[common])[0, 1])
        if int(common.sum()) >= 20
        else float("nan")
    )
    n_finite = int(finite_pim.size)
    if n_finite < min_pim_finite:
        return {
            "ok": False,
            "day": day,
            "reason": f"pim_n_finite={n_finite}<{min_pim_finite}",
            "skipped": True,
            "venues_tob": list(panel["venues"]),
            "coverage": panel.get("coverage"),
            "summary": {"n_finite_pim": n_finite},
            "kraken_mode": tob_pack.get("kraken_mode") or "absent",
        }

    kr_mode = tob_pack.get("kraken_mode")
    if "kraken" not in panel["venues"]:
        kr_mode = "absent_2venue"
    elif kr_mode is None:
        kr_mode = "spot_l2"

    return {
        "ok": True,
        "day": day,
        "symbol": symbol,
        "venues_tob": list(panel["venues"]),
        "panel_kind": (
            "panel_3venue_spot"
            if "kraken" in panel["venues"]
            else "panel_core_2venue"
        ),
        "kraken_mode": kr_mode,
        "coverage": panel.get("coverage"),
        "tob_errors": tob_pack.get("errors"),
        "dt_s": dt_s,
        "bucket_s": bucket_s,
        "n_grid": panel["n"],
        "pair_keys": vl.get("pair_keys"),
        "home_venue": home,
        "home_completeness": home_complete,
        "trades_n_complete": trades.get("n_complete"),
        "summary": {
            "pim_mean": float(np.nanmean(finite_pim)) if finite_pim.size else None,
            "pim_p50": float(np.nanmedian(finite_pim)) if finite_pim.size else None,
            "pim_p90": float(np.nanpercentile(finite_pim, 90)) if finite_pim.size else None,
            "vloop_mean": float(np.nanmean(finite_vl)) if finite_vl.size else None,
            "tcost_mean": float(np.nanmean(finite_tc)) if finite_tc.size else None,
            "corr_vloop_tcost": corr_vt if np.isfinite(corr_vt) else None,
            "n_finite_pim": n_finite,
        },
        "hourly": hourly,
    }


def _write_figs(ok_rows: list[dict[str, Any]], out_dir: Path) -> list[str]:
    """Matplotlib PNGs for desk review (hourly PIM + day bar means)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    paths: list[str] = []
    # Drop days with all-null PIM hourly
    plot_rows = []
    for row in ok_rows:
        h = row.get("hourly") or {}
        pim = h.get("pim") or []
        if any(x is not None and np.isfinite(float(x)) for x in pim):
            plot_rows.append(row)
    if not plot_rows:
        return paths
    days = [r.get("day") for r in plot_rows]
    day_ann = annotate_title("cd_me PIM (real quotes HL↔Deribit)", days)

    n = len(plot_rows)
    fig, axes = plt.subplots(n, 1, figsize=(10, max(2.2 * n, 3.5)), sharex=False, squeeze=False)
    for ax, row in zip(axes[:, 0], plot_rows):
        h = row.get("hourly") or {}
        pim = [x if x is not None else float("nan") for x in (h.get("pim") or [])]
        ax.plot(range(len(pim)), pim, color="#1f4e79", lw=1.2)
        ax.set_ylabel("PIM")
        kind = row.get("panel_kind") or "panel_core_2venue"
        ax.set_title(
            f"{row.get('day')} {kind} venues={row.get('venues_tob')} "
            f"n_finite={(row.get('summary') or {}).get('n_finite_pim')}"
        )
        ax.grid(True, alpha=0.3)
    axes[-1, 0].set_xlabel("hour bucket index (UTC)")
    fig.suptitle(day_ann + "\nmonitor ≠ arb α · trade_synth excluded", fontsize=10)
    fig.tight_layout()
    p1 = out_dir / "fig_pim_hourly.png"
    fig.savefig(p1, dpi=140, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p1))

    pim_m = [(r.get("summary") or {}).get("pim_mean") for r in plot_rows]
    vl_m = [(r.get("summary") or {}).get("vloop_mean") for r in plot_rows]
    tc_m = [(r.get("summary") or {}).get("tcost_mean") for r in plot_rows]
    x = np.arange(len(days))
    w = 0.25
    fig, ax = plt.subplots(figsize=(max(8, 1.2 * len(days)), 4.2))
    ax.bar(x - w, [v or 0 for v in pim_m], w, label="pim_mean", color="#1f4e79")
    ax.bar(x, [v or 0 for v in vl_m], w, label="vloop_mean", color="#c55a11")
    ax.bar(x + w, [v or 0 for v in tc_m], w, label="tcost_mean", color="#548235")
    ax.set_xticks(x)
    ax.set_xticklabels(days, rotation=45, ha="right")
    ax.set_ylabel("mean (log units)")
    ax.set_title(annotate_title("day means: PIM / VLOOP / TCOST (real quotes)", days))
    ax.legend(frameon=False)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    p2 = out_dir / "fig_pim_day_means.png"
    fig.savefig(p2, dpi=140, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p2))

    corrs = [(r.get("summary") or {}).get("corr_vloop_tcost") for r in plot_rows]
    fig, ax = plt.subplots(figsize=(max(7, 1.0 * len(days)), 3.6))
    ax.axhline(0, color="#888", lw=0.8)
    ax.plot(days, [c if c is not None else float("nan") for c in corrs], "o-", color="#7030a0")
    ax.set_ylabel("corr(VLOOP, TCOST)")
    ax.set_title(annotate_title("VLOOP–TCOST commonality by day", days))
    ax.tick_params(axis="x", rotation=45)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    p3 = out_dir / "fig_vloop_tcost_corr.png"
    fig.savefig(p3, dpi=140, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p3))
    return paths


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--days", nargs="*", default=None, help="UTC days YYYY-MM-DD")
    ap.add_argument("--n-days", type=int, default=7, help="If --days omitted, take last N listing days")
    ap.add_argument("--dt-s", type=float, default=5.0)
    ap.add_argument("--bucket-s", type=float, default=3600.0)
    ap.add_argument("--fast", action="store_true", help="Cap to 3 days")
    ap.add_argument(
        "--include-kraken-spot",
        action="store_true",
        help="Also load Kraken spot_l2 when dense (never trade_synth)",
    )
    ap.add_argument(
        "--use-certified",
        action="store_true",
        default=True,
        help="Prefer certified primary days from out/panel_completeness/",
    )
    ap.add_argument("--no-certified", action="store_true", help="Ignore certified panel file")
    args = ap.parse_args()

    ensure_env()
    OUT.mkdir(parents=True, exist_ok=True)

    venues: tuple[str, ...] = DEFAULT_VENUES
    if args.include_kraken_spot:
        venues = ("hyperliquid", "deribit", "kraken")

    if args.days:
        days = list(args.days)
    elif not args.no_certified:
        days = certified_primary_days()
        if not days:
            days = resolve_days(None, "hyperliquid", n=args.n_days)
    else:
        days = resolve_days(None, "hyperliquid", n=args.n_days)
    if args.fast:
        days = days[-3:]
    if not days:
        report = {
            "ok": False,
            "blocker": "no_warehouse_listing_days",
            "hint": "Run exp_panel_completeness.py or check listings",
        }
        (OUT / "summary.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        return 2

    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for day in days:
        print(f"[pim] {args.symbol} {day} venues={venues} …", flush=True)
        try:
            row = _day_pim(
                args.symbol,
                day,
                dt_s=args.dt_s,
                bucket_s=args.bucket_s,
                venues=venues,
                allow_kraken_synth=False,
            )
        except Exception as exc:  # noqa: BLE001
            row = {"ok": False, "day": day, "error": f"{type(exc).__name__}: {exc}", "skipped": True}
        rows.append(row)
        (OUT / f"day_{day}.json").write_text(json.dumps(_jsonable(row), indent=2))
        if row.get("skipped") or not row.get("ok"):
            skipped.append({"day": day, "reason": row.get("reason") or row.get("error")})
            print(f"  SKIP {day}: {row.get('reason') or row.get('error')}", flush=True)

    ok_rows = [r for r in rows if r.get("ok")]
    fig_paths: list[str] = []
    try:
        fig_dir = OUT / "figs"
        fig_dir.mkdir(parents=True, exist_ok=True)
        fig_paths = _write_figs(ok_rows, fig_dir)
    except Exception as exc:  # noqa: BLE001
        fig_paths = []
        print(f"[pim] fig write skipped: {type(exc).__name__}: {exc}", flush=True)

    kraken_status = []
    for r in rows:
        errs = r.get("tob_errors") or {}
        venues_r = r.get("venues_tob") or []
        kraken_status.append(
            {
                "day": r.get("day"),
                "in_tob": "kraken" in venues_r,
                "kraken_mode": r.get("kraken_mode") or ("missing" if "kraken" not in venues_r else None),
                "error": errs.get("kraken"),
            }
        )

    summary = {
        "ok": bool(ok_rows),
        "symbol": args.symbol,
        "days": [r["day"] for r in ok_rows],
        "days_requested": days,
        "n_ok": len(ok_rows),
        "n_fail": len(rows) - len(ok_rows),
        "skipped": skipped,
        "venues": list(venues),
        "panel": "panel_core_2venue" if "kraken" not in venues else "panel_3venue_spot",
        "dt_s": args.dt_s,
        "bucket_s": args.bucket_s,
        "figs": fig_paths,
        "kraken_status": kraken_status,
        "day_summaries": [
            {
                "day": r.get("day"),
                "ok": r.get("ok"),
                "venues_tob": r.get("venues_tob"),
                "panel_kind": r.get("panel_kind"),
                "kraken_mode": r.get("kraken_mode"),
                "summary": r.get("summary"),
                "reason": r.get("reason") or r.get("error"),
                "coverage": r.get("coverage"),
                "tob_errors": r.get("tob_errors"),
            }
            for r in rows
        ],
        "honesty": (
            "PIM on real quotes only (HL↔Deribit; Kraken spot_l2 optional). "
            "trade_synth QUARANTINED — never Promote TOB-cross as arb α"
        ),
        "retraction": "Prior '10/10 three-venue' included trade_synth — retracted",
    }
    (OUT / "summary.json").write_text(json.dumps(_jsonable(summary), indent=2))
    (OUT / "panel_rows.json").write_text(json.dumps(_jsonable(rows), indent=2))
    print(
        json.dumps(
            _jsonable(
                {
                    "n_ok": summary["n_ok"],
                    "n_fail": summary["n_fail"],
                    "days": summary["days"],
                    "skipped": skipped,
                    "figs": fig_paths,
                }
            ),
            indent=2,
        )
    )
    return 0 if ok_rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
