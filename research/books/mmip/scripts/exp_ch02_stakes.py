#!/usr/bin/env python3
"""Chapter 2 experiments: intraday volume curves + spread↔vol↔share.

Book: *Market Microstructure in Practice* Ch.2.1–2.2.
Data: startarb warehouse trade tape + HL l2_rebuild quotes (no ClickHouse MCP).

Paper only. No orders.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

BOOK_ROOT = Path(__file__).resolve().parents[1]
ROOT = BOOK_ROOT.parents[2]  # repo root (mmip → books → research → repo)
OUT_DIR = BOOK_ROOT / "out" / "ch02_stakes"
STARTARB = Path("/home/dev/srv/ares-startarb")


def _ensure_startarb() -> None:
    src = str(STARTARB / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    # Prefer running under `uv run` from startarb; still try import.
    from startarb.env import ensure_env

    ensure_env()


def entropy(q: np.ndarray) -> float:
    q = np.asarray(q, dtype=np.float64)
    q = q[q > 0]
    if q.size == 0:
        return 0.0
    return float(-np.sum(q * np.log(q)))


def fei(q: np.ndarray) -> float:
    q = np.asarray(q, dtype=np.float64)
    s = q.sum()
    if s <= 0:
        return 0.0
    q = q / s
    n = int((q > 0).sum())
    if n <= 1:
        return 0.0
    return entropy(q) / math.log(n)


def hour_of_day_utc(ts_ns: np.ndarray) -> np.ndarray:
    # floor to hour in [0, 23]
    sec = ts_ns.astype(np.int64) // 1_000_000_000
    return ((sec % 86_400) // 3600).astype(np.int64)


def volume_curve_by_hour(
    ts_ns: np.ndarray, notional: np.ndarray, n_hours: int = 24
) -> dict[str, Any]:
    h = hour_of_day_utc(ts_ns)
    vol = np.zeros(n_hours, dtype=np.float64)
    cnt = np.zeros(n_hours, dtype=np.int64)
    for i in range(n_hours):
        m = h == i
        vol[i] = float(notional[m].sum()) if m.any() else 0.0
        cnt[i] = int(m.sum())
    total = vol.sum()
    share = vol / total if total > 0 else vol
    # U-shape proxy: mean of first/last 2h vs midday 4h (UTC 12–15)
    open_close = float(share[[0, 1, 22, 23]].mean()) if total > 0 else float("nan")
    mid = float(share[12:16].mean()) if total > 0 else float("nan")
    return {
        "hour_utc": list(range(n_hours)),
        "notional": vol.tolist(),
        "trade_count": cnt.tolist(),
        "share": share.tolist(),
        "u_shape_ratio": (open_close / mid) if mid > 0 else float("nan"),
        "peak_hour": int(np.argmax(share)) if total > 0 else -1,
        "total_notional": float(total),
        "n_trades": int(cnt.sum()),
        "fei_hourly_share": fei(share),
    }


def align_spread_vol(
    q_ts: np.ndarray,
    bid: np.ndarray,
    ask: np.ndarray,
    t_ts: np.ndarray,
    t_px: np.ndarray,
    t_qty: np.ndarray,
    bucket_s: int = 60,
) -> dict[str, Any]:
    """Bucket quotes & trades; regress mean spread_bps on realized vol."""
    if q_ts.size < 10 or t_ts.size < 10:
        return {"ok": False, "reason": "insufficient_rows"}

    mid = 0.5 * (bid + ask)
    spread_bps = 1e4 * (ask - bid) / np.maximum(mid, 1e-12)
    good = np.isfinite(spread_bps) & (spread_bps >= 0) & (spread_bps < 500)
    q_ts, mid, spread_bps = q_ts[good], mid[good], spread_bps[good]

    t0 = int(min(q_ts[0], t_ts[0]))
    t1 = int(max(q_ts[-1], t_ts[-1]))
    step = bucket_s * 1_000_000_000
    edges = np.arange(t0, t1 + step, step, dtype=np.int64)
    if edges.size < 5:
        return {"ok": False, "reason": "too_few_buckets"}

    q_bin = np.searchsorted(edges, q_ts, side="right") - 1
    t_bin = np.searchsorted(edges, t_ts, side="right") - 1
    n_b = edges.size - 1
    mean_spread = np.full(n_b, np.nan)
    mean_mid = np.full(n_b, np.nan)
    notional = np.zeros(n_b)
    ret = np.full(n_b, np.nan)

    for b in range(n_b):
        mq = q_bin == b
        if mq.any():
            mean_spread[b] = float(np.mean(spread_bps[mq]))
            mean_mid[b] = float(np.mean(mid[mq]))
        mt = t_bin == b
        if mt.any():
            notional[b] = float(np.sum(t_px[mt] * t_qty[mt]))

    # log-return of mid across buckets with valid mid
    valid_mid = np.isfinite(mean_mid)
    mids = mean_mid.copy()
    # fill forward for ret computation where needed
    last = np.nan
    for i in range(n_b):
        if np.isfinite(mids[i]):
            last = mids[i]
        elif np.isfinite(last):
            mids[i] = last
    with np.errstate(divide="ignore", invalid="ignore"):
        lr = np.diff(np.log(mids), prepend=np.nan)
    # realized vol proxy: |log ret| of mid
    abs_ret = np.abs(lr)

    mask = np.isfinite(mean_spread) & np.isfinite(abs_ret) & (abs_ret >= 0)
    if mask.sum() < 20:
        return {"ok": False, "reason": "too_few_regression_points", "n": int(mask.sum())}

    x = abs_ret[mask]
    y = mean_spread[mask]
    # simple OLS y = a + b x
    x_mean, y_mean = float(x.mean()), float(y.mean())
    var_x = float(np.var(x))
    if var_x <= 0:
        return {"ok": False, "reason": "zero_vol_variance"}
    beta = float(np.cov(x, y, ddof=0)[0, 1] / var_x)
    alpha = y_mean - beta * x_mean
    yhat = alpha + beta * x
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - y_mean) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    corr = float(np.corrcoef(x, y)[0, 1])

    # share of notional in tight-spread half of buckets
    med_sp = float(np.nanmedian(mean_spread))
    tight = np.isfinite(mean_spread) & (mean_spread <= med_sp)
    wide = np.isfinite(mean_spread) & (mean_spread > med_sp)
    nt, nw = float(notional[tight].sum()), float(notional[wide].sum())
    return {
        "ok": True,
        "bucket_s": bucket_s,
        "n_buckets": int(n_b),
        "n_reg": int(mask.sum()),
        "ols_alpha_bps": alpha,
        "ols_beta_bps_per_abs_logret": beta,
        "r2": r2,
        "corr_spread_absret": corr,
        "median_spread_bps": med_sp,
        "notional_tight_share": nt / (nt + nw) if (nt + nw) > 0 else float("nan"),
        "mean_spread_bps_series": mean_spread.tolist(),
        "abs_logret_series": abs_ret.tolist(),
        "notional_series": notional.tolist(),
        "hour_utc_bucket_start": [
            int(((int(edges[i]) // 1_000_000_000) % 86_400) // 3600) for i in range(n_b)
        ],
    }


@dataclass
class DayResult:
    venue: str
    symbol: str
    day: str
    volume_curve: dict[str, Any]
    spread_vol: dict[str, Any]
    trade_meta: dict[str, Any]
    quote_meta: dict[str, Any]


def run_day(venue: str, symbol: str, day: str, max_files: int, bucket_s: int) -> DayResult:
    from startarb.data.trades import load_trade_tape
    from startarb.data.bbo_stream import load_quote_stream

    tape = load_trade_tape(venue, symbol, days=[day], max_files=max_files)
    qs = load_quote_stream(
        venue,
        symbol,
        [day],
        table="l2_rebuild" if venue == "hyperliquid" else "bbo",
        max_files=max_files,
        quotes_per_minute=30,
    )
    notional = tape.price * tape.qty_coin
    vc = volume_curve_by_hour(tape.ts_ns, notional)
    sv = align_spread_vol(
        qs.ts_ns, qs.bid, qs.ask, tape.ts_ns, tape.price, tape.qty_coin, bucket_s=bucket_s
    )
    return DayResult(
        venue=venue,
        symbol=symbol,
        day=day,
        volume_curve=vc,
        spread_vol=sv,
        trade_meta=tape.to_meta(),
        quote_meta=qs.to_meta(),
    )


def aggregate_curves(days: list[DayResult]) -> dict[str, Any]:
    shares = np.array([d.volume_curve["share"] for d in days], dtype=np.float64)
    mean_share = shares.mean(axis=0)
    return {
        "n_days": len(days),
        "mean_hourly_share": mean_share.tolist(),
        "std_hourly_share": shares.std(axis=0).tolist(),
        "mean_u_shape_ratio": float(
            np.nanmean([d.volume_curve["u_shape_ratio"] for d in days])
        ),
        "mean_fei_hourly": float(
            np.nanmean([d.volume_curve["fei_hourly_share"] for d in days])
        ),
        "days": [d.day for d in days],
    }


def md_report(payload: dict[str, Any]) -> str:
    lines = [
        f"# Ch2 stakes experiment — {payload['symbol']}",
        "",
        f"- Venue: `{payload['venue']}`",
        f"- Days: {', '.join(payload['days'])}",
        f"- Created: {payload['created_at']}",
        "",
        "## 2.1 Intraday volume curve (UTC hour shares)",
        "",
        f"- Mean U-shape ratio (open+close 2h avg / midday 4h avg): "
        f"**{payload['agg_curve']['mean_u_shape_ratio']:.3f}**",
        f"- Mean FEI of hourly notional shares: "
        f"**{payload['agg_curve']['mean_fei_hourly']:.3f}**",
        "",
        "| hour_utc | mean_share |",
        "|----------|------------|",
    ]
    for h, sh in enumerate(payload["agg_curve"]["mean_hourly_share"]):
        lines.append(f"| {h:02d} | {sh:.4f} |")
    lines += [
        "",
        "## 2.2 Spread ↔ short-horizon vol",
        "",
    ]
    for d in payload["per_day"]:
        sv = d["spread_vol"]
        if not sv.get("ok"):
            lines.append(f"- `{d['day']}`: skip ({sv.get('reason')})")
            continue
        lines.append(
            f"- `{d['day']}`: corr(spread,|Δlog mid|)={sv['corr_spread_absret']:.3f}, "
            f"OLS β={sv['ols_beta_bps_per_abs_logret']:.1f} bps per abs-logret, "
            f"R²={sv['r2']:.3f}, notional in tight-spread half="
            f"{sv['notional_tight_share']:.1%}"
        )
    lines += [
        "",
        "## Crypto analogue notes",
        "",
        "- No equity-style fixing auction monopoly; hour-of-day + funding windows "
        "are the stationarity analogues studied here.",
        "- Single-venue HL panel: 'market share' within day = hourly notional share "
        "(spatial share needs multi-venue trade tape).",
        "",
        f"Artifacts: `{OUT_DIR}`",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--venue", default="hyperliquid")
    ap.add_argument(
        "--days",
        default="2026-09-14,2026-09-15,2026-09-16,2026-09-25,2026-09-26",
        help="comma-separated YYYY-MM-DD (DENSE HL days preferred)",
    )
    ap.add_argument("--max-files", type=int, default=16)
    ap.add_argument("--bucket-s", type=int, default=60)
    args = ap.parse_args()

    _ensure_startarb()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    days = [d.strip() for d in args.days.split(",") if d.strip()]
    results: list[DayResult] = []
    for day in days:
        print(f"=== {args.venue} {args.symbol} {day} ===", flush=True)
        try:
            results.append(
                run_day(args.venue, args.symbol, day, args.max_files, args.bucket_s)
            )
        except Exception as e:
            print(f"FAIL {day}: {e}", flush=True)

    if not results:
        print("No successful days", file=sys.stderr)
        return 1

    agg = aggregate_curves(results)
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "venue": args.venue,
        "symbol": args.symbol,
        "days": [r.day for r in results],
        "agg_curve": agg,
        "per_day": [
            {
                "day": r.day,
                "volume_curve": r.volume_curve,
                "spread_vol": {
                    k: v
                    for k, v in r.spread_vol.items()
                    if k
                    not in (
                        "mean_spread_bps_series",
                        "abs_logret_series",
                        "notional_series",
                        "hour_utc_bucket_start",
                    )
                },
                "spread_vol_full": r.spread_vol,
                "trade_meta": r.trade_meta,
                "quote_meta": r.quote_meta,
            }
            for r in results
        ],
    }
    # Compact summary without full series for the main json
    summary = {
        **{k: v for k, v in payload.items() if k != "per_day"},
        "per_day": [
            {
                "day": d["day"],
                "volume_curve": {
                    k: d["volume_curve"][k]
                    for k in (
                        "share",
                        "u_shape_ratio",
                        "peak_hour",
                        "total_notional",
                        "n_trades",
                        "fei_hourly_share",
                    )
                },
                "spread_vol": d["spread_vol"],
                "trade_meta": d["trade_meta"],
                "quote_meta": d["quote_meta"],
            }
            for d in payload["per_day"]
        ],
    }
    sym = args.symbol.lower()
    summary_path = OUT_DIR / f"exp_ch02_{sym}_summary.json"
    full_path = OUT_DIR / f"exp_ch02_{sym}_full.json"
    report_path = OUT_DIR / f"exp_ch02_{sym}_REPORT.md"
    summary_path.write_text(json.dumps(summary, indent=2, default=float))
    # full includes series for notebooks
    full_path.write_text(json.dumps(payload, indent=2, default=float))
    report_path.write_text(md_report(payload))
    print("wrote", summary_path)
    print("wrote", full_path)
    print("wrote", report_path)
    print(
        "U-shape ratio mean=",
        agg["mean_u_shape_ratio"],
        "hourly FEI=",
        agg["mean_fei_hourly"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
