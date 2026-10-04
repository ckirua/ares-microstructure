from __future__ import annotations
#!/usr/bin/env python3
"""liq_around_v + xvenue_concord empirics (Pass 1+2) for v_shapes."""

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

from _data import (  # noqa: E402
    CORE_VENUES,
    ensure_env,
    load_core_venues_day,
    load_day_trades,
    load_venue_tob,
    resolve_days,
)
from ares_micro.vol.vstat import bootstrap_minv_ci, grid_1s, min_v, returns_from_log_px  # noqa: E402

try:
    from ares_micro.vol.crash import nanex_detect, vshape_events  # noqa: E402
    from ares_micro.book.spreads import quoted_spread_bps  # noqa: E402
    from ares_micro.book.tob import tob_resilience  # noqa: E402
except Exception:  # noqa: BLE001
    nanex_detect = vshape_events = quoted_spread_bps = tob_resilience = None  # type: ignore

OUT_L = BOOK / "out" / "liq_around_v"
OUT_X = BOOK / "out" / "xvenue_concord"


def _minv_tau(tape: dict, hn_s: float = 300.0, *, dt_s: float = 5.0) -> dict:
    g = grid_1s(tape["ts"], tape["px"], dt_s=dt_s)
    if int(g["n_filled"]) < 60:
        return {"ok": False}
    t, r = returns_from_log_px(g["log_px"], g["ts_ns"], time_unit_s=1.0)
    t0, t1 = float(t[0] + hn_s), float(t[-1] - hn_s)
    if t1 <= t0:
        return {"ok": False}
    taus = np.linspace(t0, t1, 41)
    mv = min_v(t, r, taus, hn_s)
    boot = bootstrap_minv_ci(
        r, hn_s, n_paths=25, n_grid=31, rng=np.random.default_rng(2), dt_s=float(g["dt_s"])
    )
    q5 = boot["quantiles"].get(0.05)
    return {
        "ok": True,
        "min_v": mv["min_v"],
        "tau_star_s": mv["tau_star"],
        "shape": mv["shape"],
        "sig_5": bool(np.isfinite(mv["min_v"]) and np.isfinite(q5) and mv["min_v"] < q5),
        "grid": g,
        "t": t,
        "r": r,
    }


def liq_around(symbol: str, day: str, venue: str, *, max_files: int) -> dict:
    rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
    mv = _minv_tau(rec["tape"], 300.0)
    out: dict = {
        "venue": venue,
        "day": day,
        "completeness": rec["completeness"],
        "minv": {k: mv[k] for k in ("ok", "min_v", "tau_star_s", "shape", "sig_5") if k in mv},
    }
    # TOB join — warehouse L2/BBO first for the UTC day, else collector
    try:
        tob = load_venue_tob(venue, symbol, day=day, max_day_dirs=3, prefer_warehouse=True)
        mid = tob["mid"]
        spread = (tob["ask"] - tob["bid"]) / np.where(mid > 0, mid, np.nan) * 1e4  # bps
        out["tob_source"] = tob.get("source")
        # window around tau*
        if mv.get("ok") and np.isfinite(mv.get("tau_star_s", np.nan)):
            # map tau_star seconds from day start via grid
            g = mv["grid"]
            t0 = int(g["ts_ns"][0])
            tau_ns = t0 + int(float(mv["tau_star_s"]) * 1_000_000_000)
            w = 300 * 1_000_000_000
            m = (tob["ts"] >= tau_ns - w) & (tob["ts"] <= tau_ns + w)
            if m.any():
                out["liq"] = {
                    "spread_bps_mean": float(np.nanmean(spread[m])),
                    "spread_bps_pre": float(np.nanmean(spread[(tob["ts"] >= tau_ns - w) & (tob["ts"] < tau_ns)]))
                    if ((tob["ts"] >= tau_ns - w) & (tob["ts"] < tau_ns)).any()
                    else float("nan"),
                    "spread_bps_post": float(np.nanmean(spread[(tob["ts"] > tau_ns) & (tob["ts"] <= tau_ns + w)]))
                    if ((tob["ts"] > tau_ns) & (tob["ts"] <= tau_ns + w)).any()
                    else float("nan"),
                    "depth_touch_mean": float(np.nanmean(tob["bid_sz"][m] + tob["ask_sz"][m])),
                    "n_tob": int(m.sum()),
                    "tob_source": tob.get("source"),
                }
                # resilience hook if available
                if tob_resilience is not None:
                    try:
                        depth = tob["bid_sz"] + tob["ask_sz"]
                        mid = tob["mid"]
                        evt = np.asarray([tau_ns], dtype=np.int64)
                        res = tob_resilience(tob["ts"], mid, depth, evt)
                        out["liq"]["resilience_keys"] = list(res.keys())[:8] if isinstance(res, dict) else str(type(res))
                    except Exception as exc:  # noqa: BLE001
                        out["liq"]["resilience_error"] = str(exc)
            else:
                out["liq"] = {"note": "no_tob_in_window", "tob_source": tob.get("source")}
        else:
            out["liq"] = {"note": "minv_failed"}
        out["tob_n"] = int(tob["ts"].size)
    except Exception as exc:  # noqa: BLE001
        out["tob_error"] = f"{type(exc).__name__}: {exc}"
        out["liq"] = {"note": "tob_unavailable"}
    # Grossman–Miller mu/sigma heuristic (monitor only)
    if mv.get("ok"):
        r = mv["r"]
        out["gm_monitor"] = {
            "mu_hat": float(np.nanmean(r)),
            "sigma_hat": float(np.nanstd(r)),
            "mu_over_sigma": float(np.nanmean(r) / np.nanstd(r)) if np.nanstd(r) > 0 else float("nan"),
            "label": "monitor_only_not_tradable",
        }
    return out


def xvenue(symbol: str, day: str, *, max_files: int) -> dict:
    bundle = load_core_venues_day(symbol, day, max_files=max_files, quiet=True)
    per = {}
    for venue, rec in bundle.get("venues", {}).items():
        if "error" in rec:
            per[venue] = {"error": rec["error"], "complete": False}
            continue
        mv = _minv_tau(rec["tape"], 300.0)
        geom = {}
        if mv.get("ok") and vshape_events is not None:
            g = mv["grid"]
            ve = vshape_events(g["ts_ns"], g["px"], min_pct=0.005, max_leg_s=300.0, min_recovery=0.4)
            geom["n_geom_v"] = int(ve["n_events"])
            if nanex_detect is not None:
                nx = nanex_detect(g["ts_ns"], g["px"], min_pct=0.005)
                geom["n_nanex"] = int(nx["n_events"])
        per[venue] = {
            "complete": rec.get("completeness", {}).get("complete"),
            "n_trades": rec.get("completeness", {}).get("n"),
            "min_v": mv.get("min_v"),
            "tau_star_s": mv.get("tau_star_s"),
            "sig_5": mv.get("sig_5"),
            "shape": mv.get("shape"),
            "geom": geom,
        }
    # concordance: pairwise |tau_i - tau_j| < hn among significant
    sig = {v: p for v, p in per.items() if p.get("sig_5") and np.isfinite(p.get("tau_star_s", np.nan))}
    pairs = []
    venues = list(sig.keys())
    for i in range(len(venues)):
        for j in range(i + 1, len(venues)):
            a, b = venues[i], venues[j]
            dt = abs(float(sig[a]["tau_star_s"]) - float(sig[b]["tau_star_s"]))
            pairs.append({"a": a, "b": b, "dt_s": dt, "concord_5m": dt <= 300.0})
    return {
        "symbol": symbol,
        "day": day,
        "n_complete": bundle.get("n_complete"),
        "per_venue": per,
        "sig_venues": list(sig.keys()),
        "pairs": pairs,
    }


def write_reports(liq_rows: list, xrows: list, symbol: str) -> None:
    OUT_L.mkdir(parents=True, exist_ok=True)
    OUT_X.mkdir(parents=True, exist_ok=True)
    (OUT_L / f"liq_{symbol.lower()}.json").write_text(json.dumps({"rows": liq_rows}, indent=2, default=str))
    (OUT_X / f"xvenue_{symbol.lower()}.json").write_text(json.dumps({"rows": xrows}, indent=2, default=str))

    ch_l = BOOK / "chapters" / "liq_around_v"
    ch_x = BOOK / "chapters" / "xvenue_concord"
    ch_l.mkdir(parents=True, exist_ok=True)
    ch_x.mkdir(parents=True, exist_ok=True)

    (ch_l / "EXP_REPORT.md").write_text(
        "\n".join(
            [
                "# Liquidity around V — EXP_REPORT (Pass 1+2)",
                "",
                f"## Sample rows: {len(liq_rows)}",
                *[
                    f"- {r.get('venue')} {r.get('day')}: minv={r.get('minv')} liq={r.get('liq')} gm={r.get('gm_monitor')}"
                    for r in liq_rows[:12]
                ],
                "",
                "## Pass 2",
                "- Grossman–Miller μ/σ: **monitor only** (not Promote tradable).",
                "- Incremental lead of spread vs MinV: compare spread_bps_pre vs post when TOB present.",
                "",
                f"## Artifact: `out/liq_around_v/liq_{symbol.lower()}.json`",
                "",
            ]
        )
    )
    # CANDIDATES / notebooks owned by hardening + build_memo_notebooks — do not stub-overwrite.
    # EXP_REPORT still refreshed from latest empirics for the symbol.
    (ch_x / "EXP_REPORT.md").write_text(
        "\n".join(
            [
                "# Cross-venue concordance — EXP_REPORT (Pass 1+2)",
                "",
                *[
                    f"- {r.get('day')}: complete={r.get('n_complete')} sig={r.get('sig_venues')} pairs={r.get('pairs')}"
                    for r in xrows
                ],
                "",
                "## Competing detectors",
                "- Geometric `crash.vshape_events` + Nanex counts stored per venue under `geom`.",
                "- Cross-link: see cross_miniflash `crash_baselines` for Tee–Ting SSM overlap claims.",
                "",
                f"## Artifact: `out/xvenue_concord/xvenue_{symbol.lower()}.json`",
                "",
            ]
        )
    )
    # notebooks owned by build_memo_notebooks.py
    return


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--n-days", type=int, default=3)
    ap.add_argument("--days", nargs="*", default=None)
    ap.add_argument("--max-files", type=int, default=24)
    args = ap.parse_args()
    ensure_env()
    days = resolve_days(args.days, venue="hyperliquid", n=args.n_days)
    liq_rows = []
    xrows = []
    for day in days:
        xrows.append(xvenue(args.symbol, day, max_files=args.max_files))
        for venue in CORE_VENUES:
            try:
                liq_rows.append(liq_around(args.symbol, day, venue, max_files=args.max_files))
            except Exception as exc:  # noqa: BLE001
                liq_rows.append({"venue": venue, "day": day, "error": str(exc)})
    write_reports(liq_rows, xrows, args.symbol)
    print(json.dumps({"days": days, "n_liq": len(liq_rows), "n_x": len(xrows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
