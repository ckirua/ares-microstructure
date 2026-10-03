#!/usr/bin/env python3
"""vpin_of Pass 2 — real warehouse tape only.

Runs: Kraken probe, HL SOL, markout predictiveness, toxicity, cross-venue,
PIN MLE diagnose, bucket robustness. Writes ``out/pass2/`` and merges panel
decisions into ``out/vpin_panel/decisions_pass2.json``.

  python3 scripts/exp_pass2.py
  python3 scripts/exp_pass2.py --markout-max-days 20 --skip-markout
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
    asof_mid,
    load_day_trades,
    load_tob_day,
    normalize_side,
    normalize_venue,
    resolve_bucket_volume,
    resolve_days,
    rolling_vpin_series,
    vpin_day_features,
)
from research.lib.markout import trade_markouts  # noqa: E402
from research.lib.pin import (  # noqa: E402
    compare_pin_vpin,
    daily_buy_sell_counts,
    eho_pin_mle,
    pin_proxy_from_days,
)
from research.lib.stats import bootstrap_ci, spearman_r  # noqa: E402
from research.lib.vpin import (  # noqa: E402
    cross_section_spearman,
    falsify_side_shuffle,
    summarize_panel_vpin,
    vpin_from_tape,
    vpin_time_split,
)

OUT = BOOK / "out" / "pass2"
PANEL = BOOK / "out" / "vpin_panel"
LISTING = Path.home() / ".cache" / "warehouse" / "listings"


def _listing_days(bucket: str) -> list[str]:
    root = LISTING / bucket
    if not root.is_dir():
        return []
    return sorted(p.stem for p in root.glob("*.json"))


def _hl_db_intersection() -> list[str]:
    sets = [
        set(_listing_days("mercat-hyperliquid-md")),
        set(_listing_days("mercat-deribit-md")),
    ]
    if not all(sets):
        return []
    return sorted(set.intersection(*sets))


def _load_panel_rows() -> list[dict[str, Any]]:
    p = PANEL / "rows.jsonl"
    if not p.is_file():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


def kraken_probe(*, strict_coverage: float = 0.95) -> dict[str, Any]:
    days = resolve_days(None, "kraken", n=999)
    rows: list[dict[str, Any]] = []
    for sym in ("ETH", "BTC", "SOL"):
        for day in days:
            try:
                rec = load_day_trades("kraken", sym, day, max_files=24, quiet=True)
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    {"symbol": sym, "day": day, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
                )
                continue
            c = rec["completeness"]
            strict_ok = bool(c.get("complete") and float(c.get("coverage", 0)) >= strict_coverage)
            rows.append(
                {
                    "symbol": sym,
                    "day": day,
                    "n": c.get("n"),
                    "complete": c.get("complete"),
                    "coverage": c.get("coverage"),
                    "span_s": c.get("span_s"),
                    "reasons": c.get("reasons"),
                    "strict_complete": strict_ok,
                    "instrument": rec.get("instrument"),
                }
            )
    n_std = sum(1 for r in rows if r.get("complete"))
    n_strict = sum(1 for r in rows if r.get("strict_complete"))
    return {
        "n_listing_days": len(days),
        "n_rows": len(rows),
        "n_complete_standard_gate": n_std,
        "n_strict_coverage": n_strict,
        "strict_coverage_threshold": strict_coverage,
        "note": (
            "Kraken PF_* futures trade tape in S3; many calendar days pass min_trades+span "
            "but recent tail days (e.g. 2026-09-29) are fragmentary. "
            "Desk: Hold frag.kraken_vpin — use strict_complete for any cross-venue compare."
        ),
        "rows": rows,
    }


def hl_sol_probe(days: list[str] | None = None) -> dict[str, Any]:
    days = days or resolve_days(None, "hyperliquid", n=8)[-5:]
    attempts: list[dict[str, Any]] = []
    for day in days:
        rec = load_day_trades("hyperliquid", "SOL", day, quiet=True)
        c = rec["completeness"]
        attempts.append(
            {
                "day": day,
                "instrument": rec.get("instrument"),
                "n": c.get("n"),
                "complete": c.get("complete"),
                "reasons": c.get("reasons"),
            }
        )
    any_n = any(int(a.get("n") or 0) > 0 for a in attempts)
    return {
        "any_trades": any_n,
        "attempts": attempts,
        "fix_applied": False,
        "blocker": (
            "Warehouse mercat-hyperliquid-md returns n=0 for catalog symbol SOL on all probed "
            "days (2026-08-28…2026-10-03); flat-era opaque id unknown (BTC/ETH ids only in HL_FLAT_IDS). "
            "No synthetic fill — Hold frag.hl_sol_empty until catalog/shard maps SOL."
        ),
    }


def _exante_vpin_at(ts_ns: int, vpin_ts: np.ndarray, vpin_roll: np.ndarray) -> float:
    j = int(np.searchsorted(vpin_ts, ts_ns, side="left") - 1)
    if j < 0 or j >= vpin_roll.size:
        return float("nan")
    v = float(vpin_roll[j])
    return v if np.isfinite(v) else float("nan")


def markout_day(
    venue: str,
    symbol: str,
    day: str,
    *,
    max_files: int = 24,
    trade_stride: int = 40,
    max_trades: int = 4000,
) -> dict[str, Any]:
    feat = vpin_day_features(venue, symbol, day, max_files=max_files)
    if not feat.get("completeness", {}).get("complete"):
        return {"ok": False, "reason": "incomplete_day", "day": day, "venue": venue, "symbol": symbol}
    try:
        tob = load_tob_day(venue, symbol, day, max_files=max_files)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"tob:{type(exc).__name__}", "day": day}

    tape = feat["tape"]
    side = normalize_side(np.asarray(tape["side"], dtype=np.float64))
    qty = np.asarray(tape["qty"], dtype=np.float64)
    ts = np.asarray(tape["ts"], dtype=np.int64)
    px = np.asarray(tape["px"], dtype=np.float64)
    v_ts = np.asarray(feat["vpin_ts"], dtype=np.int64)
    v_roll = np.asarray(feat["vpin_roll"], dtype=np.float64)

    idx = np.arange(0, ts.size, max(1, trade_stride))
    if idx.size > max_trades:
        idx = idx[:max_trades]
    ts_s = ts[idx]
    px_s = px[idx]
    side_s = side[idx]

    vpin_ex = np.array([_exante_vpin_at(int(t), v_ts, v_roll) for t in ts_s], dtype=np.float64)
    mo = trade_markouts(ts_s, px_s, side_s, tob["ts"], tob["mid"], horizons_ms=(30000, 60000))
    mo30 = np.full(ts_s.size, np.nan)
    # reconstruct per-trade 30s markout from mid path
    mt, mv = tob["ts"], tob["mid"]
    i0 = np.searchsorted(mt, ts_s, side="right") - 1
    h_ns = 30_000_000_000
    i1 = np.searchsorted(mt, ts_s + h_ns, side="right") - 1
    valid = (i0 >= 0) & (i1 > i0) & (i1 < mt.size) & np.isfinite(side_s) & (side_s != 0)
    mid0 = np.full(ts_s.size, np.nan)
    mid1 = np.full(ts_s.size, np.nan)
    mid0[valid] = mv[i0[valid]]
    mid1[valid] = mv[i1[valid]]
    ok = valid & (mid0 > 0) & np.isfinite(mid1)
    mo30[ok] = side_s[ok] * 1e4 * (mid1[ok] - mid0[ok]) / mid0[ok]

    m = np.isfinite(vpin_ex) & np.isfinite(mo30)
    vpin_ex, mo30 = vpin_ex[m], mo30[m]
    if vpin_ex.size < 80:
        return {"ok": False, "reason": "thin_join", "n": int(vpin_ex.size), "day": day}

    # chronological split on trade time
    ts_ok = ts_s[m]
    cut = int(ts_ok.size * 0.5)
    early_m = np.zeros(ts_ok.size, dtype=bool)
    early_m[:cut] = True

    def _ic(v: np.ndarray, y: np.ndarray) -> dict[str, float]:
        if v.size < 30:
            return {"n": float(v.size), "rho": float("nan"), "lo": float("nan"), "hi": float("nan")}
        return cross_section_spearman(v, y, n_boot=400, seed=31)

    ic_all = _ic(vpin_ex, mo30)
    ic_early = _ic(vpin_ex[early_m], mo30[early_m])
    ic_late = _ic(vpin_ex[~early_m], mo30[~early_m])

    # quintile spread (Q5 − Q1 mean markout)
    qs = np.quantile(vpin_ex, [0.2, 0.4, 0.6, 0.8])
    qbin = np.searchsorted(qs, vpin_ex, side="right")
    q_means = [float(np.nanmean(mo30[qbin == k])) for k in range(5)]
    q_spread = float(q_means[4] - q_means[0]) if all(np.isfinite(x) for x in q_means) else float("nan")

    return {
        "ok": True,
        "venue": normalize_venue(venue),
        "symbol": symbol,
        "day": day,
        "n_join": int(vpin_ex.size),
        "tob_source": tob.get("source"),
        "ic_spearman_vpin_vs_mo30": ic_all,
        "ic_early": ic_early,
        "ic_late": ic_late,
        "quintile_mean_mo30_bps": q_means,
        "quintile_spread_q5_q1_bps": q_spread,
        "markout_summary_30s": mo.get("by_horizon", {}).get("30000"),
        "markout_summary_60s": mo.get("by_horizon", {}).get("60000"),
    }


def run_markout(
    panel_ok: list[dict[str, Any]],
    *,
    max_days: int | None,
    trade_stride: int,
) -> dict[str, Any]:
    cells = sorted({(r["venue"], r["symbol"]) for r in panel_ok if r["venue"] in ("hyperliquid", "deribit")})
    day_rows: list[dict[str, Any]] = []
    for v, sym in cells:
        days = sorted({r["day"] for r in panel_ok if r["venue"] == v and r["symbol"] == sym})
        if max_days:
            days = days[-max_days:]
        for j, day in enumerate(days):
            print(f"markout {j+1}/{len(days)} {v} {sym} {day}", flush=True)
            day_rows.append(markout_day(v, sym, day, trade_stride=trade_stride))

    ok_rows = [r for r in day_rows if r.get("ok")]
    rhos = np.array(
        [r["ic_spearman_vpin_vs_mo30"]["rho"] for r in ok_rows if np.isfinite(r["ic_spearman_vpin_vs_mo30"]["rho"])],
        dtype=np.float64,
    )
    early_r = np.array(
        [r["ic_early"]["rho"] for r in ok_rows if np.isfinite(r["ic_early"]["rho"])],
        dtype=np.float64,
    )
    late_r = np.array(
        [r["ic_late"]["rho"] for r in ok_rows if np.isfinite(r["ic_late"]["rho"])],
        dtype=np.float64,
    )
    pooled_v, pooled_m = [], []
    for r in ok_rows:
        # re-load not needed — aggregate day-level IC weighted by n_join using stored spread as proxy
        pass
    # Pool IC: stack day-level rho with bootstrap on day rhos
    day_ic = cross_section_spearman(
        np.arange(len(rhos), dtype=np.float64), rhos, n_boot=400, seed=33
    ) if rhos.size >= 5 else {"n": float(rhos.size), "rho": float("nan"), "lo": float("nan"), "hi": float("nan")}

    promote = (
        rhos.size >= 8
        and np.isfinite(early_r).sum() >= 5
        and np.isfinite(late_r).sum() >= 5
        and float(np.nanmedian(early_r)) > 0
        and float(np.nanmedian(late_r)) > 0
        and float(np.nanmedian(rhos)) > 0.02
    )
    compact = [
        {
            k: r[k]
            for k in (
                "venue",
                "symbol",
                "day",
                "n_join",
                "ic_spearman_vpin_vs_mo30",
                "ic_early",
                "ic_late",
                "quintile_spread_q5_q1_bps",
                "tob_source",
            )
            if k in r
        }
        for r in ok_rows
    ]
    return {
        "n_days_attempted": len(day_rows),
        "n_days_ok": len(ok_rows),
        "day_rows": compact,
        "median_ic_by_day": float(np.nanmedian(rhos)) if rhos.size else float("nan"),
        "median_ic_early": float(np.nanmedian(early_r)) if early_r.size else float("nan"),
        "median_ic_late": float(np.nanmedian(late_r)) if late_r.size else float("nan"),
        "ic_ci_across_days": bootstrap_ci(rhos, stat=np.median, n_boot=500, seed=34) if rhos.size >= 5 else {},
        "decision": "Promote" if promote else "Hold",
        "gate_note": "Promote if median day IC>0 early∧late (ex-ante VPIN vs 30s TOB markout)",
    }


def toxicity_day(venue: str, symbol: str, day: str, mean_vpin: float) -> dict[str, Any]:
    try:
        tob = load_tob_day(venue, symbol, day)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "day": day, "error": str(exc)}
    mid = np.asarray(tob["mid"], dtype=np.float64)
    bid = np.asarray(tob["bid"], dtype=np.float64)
    ask = np.asarray(tob["ask"], dtype=np.float64)
    sp_bps = 1e4 * (ask - bid) / np.maximum(mid, 1e-12)
    sp_bps = sp_bps[np.isfinite(sp_bps) & (sp_bps > 0) & (sp_bps < 200)]
    lr = np.diff(np.log(mid[np.isfinite(mid) & (mid > 0)]))
    rv = float(np.sqrt(np.nansum(lr**2))) if lr.size > 10 else float("nan")
    return {
        "ok": True,
        "venue": venue,
        "symbol": symbol,
        "day": day,
        "mean_vpin": mean_vpin,
        "spread_bps_mean": float(np.mean(sp_bps)) if sp_bps.size else float("nan"),
        "spread_bps_p90": float(np.quantile(sp_bps, 0.9)) if sp_bps.size else float("nan"),
        "rv_log_mid": rv,
        "tob_source": tob.get("source"),
    }


def run_toxicity(panel_ok: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    todo = [r for r in panel_ok if r["venue"] in ("hyperliquid", "deribit")]
    for i, r in enumerate(todo):
        if i % 5 == 0:
            print(f"toxicity {i}/{len(todo)} {r['venue']} {r['symbol']} {r['day']}", flush=True)
        t = toxicity_day(r["venue"], r["symbol"], r["day"], float(r["mean_vpin"]))
        if t.get("ok"):
            rows.append(t)
    if len(rows) < 10:
        return {"n": len(rows), "decision": "Hold", "reason": "thin_tob_join", "rows": rows}
    vpin = np.array([x["mean_vpin"] for x in rows], dtype=np.float64)
    sp = np.array([x["spread_bps_mean"] for x in rows], dtype=np.float64)
    rv = np.array([x["rv_log_mid"] for x in rows], dtype=np.float64)
    q90 = float(np.quantile(vpin, 0.9))
    top = [x for x in rows if x["mean_vpin"] >= q90]
    bot = [x for x in rows if x["mean_vpin"] <= float(np.quantile(vpin, 0.5))]
    rho_sp = cross_section_spearman(vpin, sp, n_boot=400, seed=41)
    rho_rv = cross_section_spearman(vpin, rv, n_boot=400, seed=42)
    top_sp = float(np.nanmean([x["spread_bps_mean"] for x in top]))
    bot_sp = float(np.nanmean([x["spread_bps_mean"] for x in bot]))
    promote = rho_sp.get("lo", -1) > 0.05 or (top_sp > bot_sp * 1.05 and len(top) >= 3)
    return {
        "n_days": len(rows),
        "top_decile_threshold": q90,
        "n_top_decile": len(top),
        "top_vs_median_spread_bps": {"top_mean": top_sp, "bottom_half_mean": bot_sp},
        "spearman_vpin_spread": rho_sp,
        "spearman_vpin_rv": rho_rv,
        "sample_top_days": sorted(top, key=lambda x: -x["mean_vpin"])[:8],
        "decision": "Promote" if promote else "Hold",
        "falsifier": "High VPIN days without wider spread / vol — Hold toxicity flag as monitor-only",
    }


def bucket_robust(panel_ok: list[dict[str, Any]], *, max_days_per_cell: int = 8) -> dict[str, Any]:
    scales = (25.0, 50.0, 100.0)
    targets = (30.0, 50.0, 100.0)
    by_cell: dict[str, list[dict[str, Any]]] = {}
    for r in panel_ok:
        if r["venue"] not in ("hyperliquid", "deribit"):
            continue
        key = f"{r['venue']}|{r['symbol']}"
        by_cell.setdefault(key, []).append(r)
    grid_stats: list[dict[str, Any]] = []
    for key, rs in by_cell.items():
        rs = sorted(rs, key=lambda x: x["day"])[-max_days_per_cell:]
        venue, sym = key.split("|", 1)
        for day_rec in rs:
            day = day_rec["day"]
            rec = load_day_trades(venue, sym, day, quiet=True)
            tape = rec["tape"]
            side = normalize_side(np.asarray(tape["side"], dtype=np.float64))
            qty = np.asarray(tape["qty"], dtype=np.float64)
            ts = np.asarray(tape["ts"], dtype=np.int64)
            for scale in scales:
                bv, _ = resolve_bucket_volume(qty, bucket_scale=scale)
                v = vpin_from_tape(side, qty, ts, bucket_volume=bv, n_buckets_window=50)
                grid_stats.append(
                    {
                        "cell": key,
                        "day": day,
                        "method": f"median_x_{int(scale)}",
                        "mean_vpin": v.get("mean_vpin"),
                        "n_buckets": v.get("n_buckets"),
                    }
                )
            for tb in targets:
                bv, _ = resolve_bucket_volume(qty, target_buckets=tb)
                v = vpin_from_tape(side, qty, ts, bucket_volume=bv, n_buckets_window=50)
                grid_stats.append(
                    {
                        "cell": key,
                        "day": day,
                        "method": f"target_{int(tb)}",
                        "mean_vpin": v.get("mean_vpin"),
                        "n_buckets": v.get("n_buckets"),
                    }
                )
    df_methods: dict[str, list[float]] = {}
    for g in grid_stats:
        m = g["method"]
        mv = g.get("mean_vpin")
        if mv is not None and np.isfinite(mv):
            df_methods.setdefault(m, []).append(float(mv))
    sens = []
    ref = np.nanmedian(df_methods.get("median_x_50", [float("nan")]))
    for method, vals in sorted(df_methods.items()):
        med = float(np.nanmedian(vals))
        sens.append({"method": method, "median_mean_vpin": med, "delta_vs_sot": med - ref if np.isfinite(ref) else float("nan")})
    spread = float(np.nanmax([s["median_mean_vpin"] for s in sens]) - np.nanmin([s["median_mean_vpin"] for s in sens]))
    return {
        "n_grid_points": len(grid_stats),
        "sensitivity": sens,
        "median_level_spread_across_methods": spread,
        "decision": "Hold",
        "note": "Levels shift with bucket clock; rank/construction falsifiers drive Promote — not level equality across scales",
    }


def pin_mle_diagnose(panel_ok: list[dict[str, Any]]) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    for venue in ("hyperliquid", "deribit"):
        for sym in ("ETH", "BTC"):
            ok = [r for r in panel_ok if r["venue"] == venue and r["symbol"] == sym]
            days_bs: dict[str, dict[str, float]] = {}
            for r in ok:
                try:
                    rec = load_day_trades(venue, sym, r["day"], quiet=True)
                except Exception:
                    continue
                tape = rec["tape"]
                ts = np.asarray(tape["ts"], dtype=np.int64)
                side = normalize_side(np.asarray(tape["side"], dtype=np.float64))
                n = int(side.size)
                if n == 0:
                    continue
                bs = daily_buy_sell_counts(ts, side, day_labels=[r["day"]] * n)[str(r["day"])]
                days_bs[str(r["day"])] = bs
            mle_strict = eho_pin_mle(days_bs, min_trades_per_day=500, min_span_h=4.0)
            mle_relaxed = eho_pin_mle(days_bs, min_trades_per_day=200, min_span_h=1.0)
            proxy = pin_proxy_from_days(days_bs)
            mv = np.array([r["mean_vpin"] for r in ok if np.isfinite(r.get("mean_vpin", float("nan")))])
            pp = np.array([proxy["pin_proxy"]] * len(mv))  # pooled proxy scalar — day-level below
            day_pp = []
            day_mv = []
            for d, bs in days_bs.items():
                day_pp.append(
                    float(abs(bs["B"] - bs["S"]) / max(bs["B"] + bs["S"], 1))
                )
                m = next((r["mean_vpin"] for r in ok if r["day"] == d), float("nan"))
                day_mv.append(float(m))
            rho = cross_section_spearman(np.array(day_pp), np.array(day_mv)) if len(day_pp) >= 5 else {}
            blocks.append(
                {
                    "venue": venue,
                    "symbol": sym,
                    "n_ok_days": len(ok),
                    "n_days_bs": len(days_bs),
                    "mle_default_filters": mle_strict,
                    "mle_relaxed_filters": mle_relaxed,
                    "pin_proxy_pooled": proxy,
                    "day_vpin_vs_abs_imb_spearman": rho,
                    "diagnosis": (
                        "Pass 1 pin_compare had empty day_bs in JSON rows (field omitted in stale run). "
                        "MLE needs ≥3 UTC days of (B,S); relaxed filters enable PIN when span/trade gates pass. "
                        "PIN level ≠ VPIN level — compare ranks/proxy only."
                    ),
                }
            )
    any_mle = any(b["mle_default_filters"].get("ok") for b in blocks)
    return {"blocks": blocks, "any_mle_ok": any_mle, "decision": "Hold"}


def xvenue_concord(panel_ok: list[dict[str, Any]]) -> dict[str, Any]:
    pairs: list[tuple[float, float]] = []
    by_key: dict[tuple[str, str, str], float] = {}
    for r in panel_ok:
        if r["venue"] in ("hyperliquid", "deribit"):
            by_key[(r["symbol"], r["day"], r["venue"])] = float(r["mean_vpin"])
    for sym in sorted({k[0] for k in by_key}):
        days = sorted({k[1] for k in by_key if k[0] == sym})
        for d in days:
            a = by_key.get((sym, d, "hyperliquid"))
            b = by_key.get((sym, d, "deribit"))
            if a is not None and b is not None and np.isfinite(a) and np.isfinite(b):
                pairs.append((a, b))
    xv = cross_section_spearman(
        np.array([p[0] for p in pairs]),
        np.array([p[1] for p in pairs]),
    ) if len(pairs) >= 5 else {"n": float(len(pairs)), "rho": float("nan"), "lo": float("nan"), "hi": float("nan")}
    dec = (
        "Promote"
        if xv.get("n", 0) >= 15 and np.isfinite(xv.get("rho", float("nan"))) and xv.get("lo", -1) >= 0.15
        else "Hold"
    )
    return {"n_pairs": len(pairs), "spearman": xv, "decision": dec}


def extend_panel_all_days(symbols: tuple[str, ...] = ("ETH", "BTC")) -> list[dict[str, Any]]:
    """Recompute HL+DB rows on full intersection (for cross-venue max history)."""
    days = _hl_db_intersection()
    rows: list[dict[str, Any]] = []
    for v in ("hyperliquid", "deribit"):
        for sym in symbols:
            for day in days:
                try:
                    rec = load_day_trades(v, sym, day, quiet=True)
                    comp = rec["completeness"]
                    if not comp.get("complete"):
                        continue
                    tape = rec["tape"]
                    side = normalize_side(np.asarray(tape["side"], dtype=np.float64))
                    qty = np.asarray(tape["qty"], dtype=np.float64)
                    ts = np.asarray(tape["ts"], dtype=np.int64)
                    bv, _ = resolve_bucket_volume(qty, bucket_scale=50.0)
                    vpin = vpin_from_tape(side, qty, ts, bucket_volume=bv, n_buckets_window=50)
                    rows.append(
                        {
                            "ok": True,
                            "venue": v,
                            "symbol": sym,
                            "day": day,
                            "mean_vpin": vpin.get("mean_vpin"),
                            "n_buckets": vpin.get("n_buckets"),
                            "coverage": comp.get("coverage"),
                            "complete": True,
                        }
                    )
                except Exception:
                    continue
    return rows


def merge_decisions(
    pass1: dict[str, Any],
    *,
    markout: dict[str, Any],
    toxicity: dict[str, Any],
    robust: dict[str, Any],
    pin: dict[str, Any],
    xvenue: dict[str, Any],
    kraken: dict[str, Any],
    sol: dict[str, Any],
) -> dict[str, Any]:
    table = list(pass1.get("decision_table", []))
    # update / append pass2 ids
    updates = {
        "info.vpin_markout": markout.get("decision", "Hold"),
        "risk.vpin_toxicity_flag": toxicity.get("decision", "Hold"),
        "cont.vpin_bucket_robust": robust.get("decision", "Hold"),
        "frag.xvenue_vpin_concord": xvenue.get("decision", "Hold"),
        "frag.kraken_vpin": "Hold",
        "frag.hl_sol_empty": "Hold",
    }
    kr_ev = (
        f"Kraken strict_complete={kraken.get('n_strict_coverage')} "
        f"standard_complete={kraken.get('n_complete_standard_gate')} — partial tail; Hold"
    )
    sol_ev = sol.get("blocker", "HL SOL empty")[:160]
    def _f4(x: Any) -> str:
        try:
            v = float(x)
            return f"{v:.4f}" if np.isfinite(v) else "nan"
        except (TypeError, ValueError):
            return "nan"

    mark_ev = (
        f"n_ok={markout.get('n_days_ok')} medIC={_f4(markout.get('median_ic_by_day'))} "
        f"early={_f4(markout.get('median_ic_early'))} late={_f4(markout.get('median_ic_late'))}"
    )
    tox_ev = f"n={toxicity.get('n_days')} ρ_vpin,spread={((toxicity.get('spearman_vpin_spread') or {}).get('rho'))}"
    rob_ev = f"level_spread={robust.get('median_level_spread_across_methods'):.3f} — monitor sensitivity"
    xv = xvenue.get("spearman") or {}
    xv_ev = f"HL↔DB ρ={xv.get('rho')} CI=[{xv.get('lo')},{xv.get('hi')}] n={xv.get('n')}"
    extra = {
        "info.vpin_markout": mark_ev,
        "risk.vpin_toxicity_flag": tox_ev,
        "cont.vpin_bucket_robust": rob_ev,
        "frag.xvenue_vpin_concord": xv_ev,
        "frag.kraken_vpin": kr_ev,
        "frag.hl_sol_empty": sol_ev,
    }
    seen = {t["id"] for t in table}
    for tid, dec in updates.items():
        ev = extra.get(tid, "")
        if tid in seen:
            for t in table:
                if t["id"] == tid:
                    t["decision"] = dec
                    if ev:
                        t["evidence"] = ev
        else:
            table.append({"id": tid, "decision": dec, "evidence": ev})
    counts: dict[str, int] = {}
    for t in table:
        counts[t["decision"]] = counts.get(t["decision"], 0) + 1
    out = dict(pass1)
    out["decision_table"] = table
    out["decision_counts"] = counts
    out["pass2"] = {
        "markout": {k: markout.get(k) for k in ("n_days_ok", "median_ic_by_day", "median_ic_early", "median_ic_late", "decision")},
        "toxicity": {k: toxicity.get(k) for k in ("n_days", "decision", "spearman_vpin_spread")},
        "xvenue": xvenue,
        "kraken": {k: kraken.get(k) for k in ("n_strict_coverage", "n_complete_standard_gate")},
        "hl_sol": {"any_trades": sol.get("any_trades"), "blocker": sol.get("blocker")},
    }
    out["data_provenance"] = (
        pass1.get("data_provenance", "")
        + "; Pass2: TOB from warehouse L2/collector; markout/toxicity on HL+Deribit complete days; Kraken probed"
    )
    return out


def write_exp_reports(dec: dict[str, Any], artifacts: dict[str, Any]) -> None:
    def _table_rows(ids: list[str]) -> str:
        lines = []
        by_id = {t["id"]: t for t in dec.get("decision_table", [])}
        for i in ids:
            t = by_id.get(i, {"decision": "Hold", "evidence": "—"})
            lines.append(f"| `{i}` | **{t['decision']}** | {str(t.get('evidence', ''))[:140]} |")
        return "\n".join(lines)

    (BOOK / "chapters/predictiveness/EXP_REPORT.md").write_text(
        "# predictiveness — Pass 2\n\n"
        f"Markout join: **{artifacts['markout'].get('decision')}** — "
        f"n_ok days={artifacts['markout'].get('n_days_ok')}, "
        f"median IC={artifacts['markout'].get('median_ic_by_day')}.\n\n"
        "| id | decision | evidence |\n|----|----------|----------|\n"
        + _table_rows(["info.vpin_markout", "info.vpin_side_shuffle", "info.vpin_time_split_stable"])
        + "\n"
    )
    (BOOK / "chapters/toxicity_events/EXP_REPORT.md").write_text(
        "# toxicity_events — Pass 2\n\n"
        f"Toxicity flag: **{artifacts['toxicity'].get('decision')}** (spread/vol join on panel days).\n\n"
        "| id | decision | evidence |\n|----|----------|----------|\n"
        + _table_rows(["risk.vpin_toxicity_flag"])
        + "\n"
    )
    (BOOK / "chapters/robustness/EXP_REPORT.md").write_text(
        "# robustness — Pass 2\n\n"
        f"Bucket grid on HL+DB panel sample — level spread {artifacts['robust'].get('median_level_spread_across_methods')}.\n\n"
        "| id | decision | evidence |\n|----|----------|----------|\n"
        + _table_rows(["cont.vpin_bucket_robust"])
        + "\n"
    )
    (BOOK / "chapters/cross_venue/EXP_REPORT.md").write_text(
        "# cross_venue — Pass 2\n\n"
        f"Paired HL↔DB days n={artifacts['xvenue'].get('n_pairs')}.\n\n"
        "| id | decision | evidence |\n|----|----------|----------|\n"
        + _table_rows(["frag.xvenue_vpin_concord", "frag.kraken_vpin"])
        + "\n"
    )
    (BOOK / "chapters/pin_compare/EXP_REPORT.md").write_text(
        "# pin_compare — Pass 2\n\n"
        "MLE re-diagnosed with fresh day_bs from tape (≥3 days required).\n\n"
        f"any_mle_ok={artifacts['pin'].get('any_mle_ok')}\n\n"
        "| id | decision | evidence |\n|----|----------|----------|\n"
        + _table_rows(["disc.pin_proxy_vs_vpin"])
        + "\n"
    )
    ch00 = BOOK / "chapters/ch00_overview/EXP_REPORT.md"
    if ch00.is_file():
        base = ch00.read_text().split("Pass 2")[0].strip()
    else:
        base = "# ch00 overview"
    ch00.write_text(
        base
        + f"\n\nPass 2 complete: HL+DB panel n={dec.get('n_ok_pass2_hl_db_panel')} — counts {dec.get('decision_counts')}\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--markout-max-days", type=int, default=0, help="0 = all ok days per cell")
    ap.add_argument("--skip-markout", action="store_true")
    ap.add_argument("--trade-stride", type=int, default=50)
    ap.add_argument(
        "--refresh-xvenue-panel",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Recompute HL+DB full intersection panel (slow S3); default loads cache",
    )
    ap.add_argument(
        "--panel-json",
        type=Path,
        default=None,
        help="Use this panel row list instead of rows.jsonl / refresh",
    )
    ap.add_argument("--resume", action="store_true", help="Reuse existing out/pass2/*.json where present")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    pass1_path = PANEL / "decisions.json"
    pass1 = json.loads(pass1_path.read_text()) if pass1_path.is_file() else {"decision_table": [], "n_ok": 0}

    def _load_or_run(name: str, fn):
        path = OUT / name
        if args.resume and path.is_file():
            return json.loads(path.read_text())
        val = fn()
        path.write_text(json.dumps(val, indent=2) + "\n")
        return val

    print("kraken_probe", flush=True)
    kraken = _load_or_run("kraken_probe.json", kraken_probe)

    print("hl_sol_probe", flush=True)
    sol = _load_or_run("hl_sol_probe.json", hl_sol_probe)

    panel_cache = OUT / "panel_hl_db_extended.json"
    if args.panel_json is not None:
        panel_ok = json.loads(args.panel_json.read_text())
        print(f"panel from {args.panel_json}", flush=True)
    elif args.refresh_xvenue_panel:
        print("extend_panel_all_days", flush=True)
        panel_ok = extend_panel_all_days()
        panel_cache.write_text(json.dumps(panel_ok, indent=2) + "\n")
    elif panel_cache.is_file():
        panel_ok = json.loads(panel_cache.read_text())
        print(f"panel cache n={len(panel_ok)}", flush=True)
    else:
        panel_ok = [r for r in _load_panel_rows() if r.get("ok")]
        if len(panel_ok) < 10:
            print("extend_panel_all_days (thin rows.jsonl)", flush=True)
            panel_ok = extend_panel_all_days()
            panel_cache.write_text(json.dumps(panel_ok, indent=2) + "\n")

    print("xvenue", flush=True)
    xvenue = _load_or_run("xvenue_concord.json", lambda: xvenue_concord(panel_ok))

    print("pin_mle", flush=True)
    pin = _load_or_run("pin_mle_diagnose.json", lambda: pin_mle_diagnose(panel_ok))

    print("bucket_robust", flush=True)
    robust = _load_or_run("bucket_robust.json", lambda: bucket_robust(panel_ok))

    print("toxicity", flush=True)
    toxicity = _load_or_run("toxicity.json", lambda: run_toxicity(panel_ok))

    if args.skip_markout:
        markout = {"n_days_ok": 0, "decision": "Hold", "skipped": True}
    else:
        print("markout", flush=True)
        max_d = args.markout_max_days or None
        mo_path = OUT / "markout.json"
        if args.resume and mo_path.is_file():
            markout = json.loads(mo_path.read_text())
        else:
            markout = run_markout(panel_ok, max_days=max_d, trade_stride=args.trade_stride)
            mo_path.write_text(json.dumps(markout, indent=2) + "\n")

    merged = merge_decisions(
        pass1,
        markout=markout,
        toxicity=toxicity,
        robust=robust,
        pin=pin,
        xvenue=xvenue,
        kraken=kraken,
        sol=sol,
    )
    merged["n_ok_pass2_hl_db_panel"] = len(panel_ok)
    merged["falsifiers"] = dict(pass1.get("falsifiers") or {})
    merged["falsifiers"]["xvenue_spearman"] = xvenue.get("spearman")
    (OUT / "decisions_pass2.json").write_text(json.dumps(merged, indent=2) + "\n")
    (PANEL / "decisions_pass2.json").write_text(json.dumps(merged, indent=2) + "\n")

    artifacts = {
        "markout": markout,
        "toxicity": toxicity,
        "robust": robust,
        "pin": pin,
        "xvenue": xvenue,
    }
    write_exp_reports(merged, artifacts)
    (OUT / "pass2_summary.json").write_text(
        json.dumps(
            {
                "n_ok_panel": len(panel_ok),
                "decision_counts": merged.get("decision_counts"),
                "markout": markout.get("decision"),
                "toxicity": toxicity.get("decision"),
                "xvenue": xvenue.get("decision"),
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(merged.get("decision_counts"), indent=2))


if __name__ == "__main__":
    main()
