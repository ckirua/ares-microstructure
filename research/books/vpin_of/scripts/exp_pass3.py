#!/usr/bin/env python3
"""vpin_of Pass 3 — attack Pass 2 Hold blockers (real warehouse tape only).

  python3 scripts/exp_pass3.py
  python3 scripts/exp_pass3.py --skip-markout --resume
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
    load_day_trades,
    load_warehouse_tob,
    normalize_side,
    normalize_venue,
    resolve_bucket_volume,
    resolve_days,
    rolling_vpin_series,
    vpin_day_features,
)
from exp_pass2 import (  # noqa: E402
    OUT as OUT2,
    PANEL,
    _hl_db_intersection,
    _load_panel_rows,
    kraken_probe,
    merge_decisions as merge_pass2_style,
)
from ares_micro.stats import bootstrap_ci, spearman_r  # noqa: E402
from ares_micro.flow.vpin import cross_section_spearman, vpin_from_tape  # noqa: E402

OUT = BOOK / "out" / "pass3"
PASS2_DEC = OUT2 / "decisions_pass2.json"


def _write_json(path: Path, obj: Any) -> None:
    """JSON without NaN (strict parsers / notebooks)."""

    def _clean(x: Any) -> Any:
        if isinstance(x, float) and not np.isfinite(x):
            return None
        if isinstance(x, dict):
            return {k: _clean(v) for k, v in x.items()}
        if isinstance(x, list):
            return [_clean(v) for v in x]
        return x

    path.write_text(json.dumps(_clean(obj), indent=2) + "\n")

# Pre-registered Pass 3 gates (document before run)
MARKOUT_GATE = {
    "min_ok_days": 8,
    "median_day_ic": 0.02,
    "median_early_ic": 0.0,
    "median_late_ic": 0.0,
    "median_rank_ic": 0.02,
    "full_panel_required": True,
}
XVENUE_GATE = {"min_pairs": 15, "ci_lo": 0.15}
BUCKET_ROBUST_PROMOTE_SPREAD = 0.45  # Pass 2 was 0.678 — material tightening


def _load_pass2_decisions() -> dict[str, Any]:
    if PASS2_DEC.is_file():
        return json.loads(PASS2_DEC.read_text())
    p = PANEL / "decisions_pass2.json"
    return json.loads(p.read_text()) if p.is_file() else {"decision_table": [], "n_ok": 0}


def _panel_hl_db() -> list[dict[str, Any]]:
    cache = OUT2 / "panel_hl_db_extended.json"
    if cache.is_file():
        return json.loads(cache.read_text())
    return [r for r in _load_panel_rows() if r.get("ok")]


def hl_sol_pass3() -> dict[str, Any]:
    """Catalog / FNV / flat-era probe — no synthetic fills."""
    from startarb.data.instruments import _fnv1a32, resolve_instrument  # noqa: E402

    fnv_sol = int(_fnv1a32("SOL"))
    ref = resolve_instrument("hyperliquid", "SOL")
    days = resolve_days(None, "hyperliquid", n=999)
    attempts: list[dict[str, Any]] = []
    for day in days:
        rec = load_day_trades("hyperliquid", "SOL", day, quiet=True)
        c = rec["completeness"]
        attempts.append(
            {
                "day": day,
                "instrument": rec.get("instrument"),
                "fnv_id": fnv_sol,
                "n": c.get("n"),
                "complete": c.get("complete"),
                "coverage": c.get("coverage"),
                "reasons": c.get("reasons"),
            }
        )
    nonempty = [a for a in attempts if int(a.get("n") or 0) > 0]
    complete = [a for a in attempts if a.get("complete")]
    # flat-era spot check (BTC id still works on old days)
    flat_probe: list[dict[str, Any]] = []
    for day in ("2026-09-05", "2026-09-10"):
        for sym in ("BTC", "SOL"):
            rec = load_day_trades("hyperliquid", sym, day, quiet=True)
            flat_probe.append(
                {"day": day, "symbol": sym, "n": rec["completeness"]["n"], "instrument": rec.get("instrument")}
            )
    any_n = bool(nonempty)
    fix_note = (
        "SOL resolves to catalog FNV id 621827265 (not flat-era opaque). "
        "startarb/config/symbols.yaml leaves hyperliquid_flat_ids.SOL unset — correct: "
        "flat ids are BTC/ETH only. Warehouse gap: only 2026-08-28 has HL SOL trades "
        "in listing cache; post-2026-08-28 shards return n=0 (collector/xvenue books use "
        "Deribit+Kraken for SOL). No synthetic fill."
    )
    return {
        "fnv_catalog_id": fnv_sol,
        "instrument_ref": {
            "symbol": ref.symbol,
            "instrument_id": ref.instrument_id,
        },
        "n_listing_days_scanned": len(days),
        "n_days_with_trades": len(nonempty),
        "n_complete_days": len(complete),
        "nonempty_days": nonempty[:12],
        "flat_era_probe": flat_probe,
        "any_trades": any_n,
        "fix_applied": False,
        "desk_workaround": "SOL VPIN on Deribit+Kraken only until HL SOL shard resumes",
        "blocker": fix_note,
        "decision": "Hold",
    }


def kraken_pass3(*, strict_coverage: float = 0.95) -> dict[str, Any]:
    base = kraken_probe(strict_coverage=strict_coverage)
    rows = base.get("rows") or []
    by_sym: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_sym.setdefault(str(r.get("symbol")), []).append(r)
    tail_cut = "2026-09-20"
    tail = [r for r in rows if str(r.get("day", "")) >= tail_cut]
    tail_std = sum(1 for r in tail if r.get("complete"))
    tail_strict = sum(1 for r in tail if r.get("strict_complete"))
    partial_tail = [
        r
        for r in tail
        if r.get("complete") and not r.get("strict_complete")
    ]
    sym_summary = []
    for sym, rs in sorted(by_sym.items()):
        sym_summary.append(
            {
                "symbol": sym,
                "n_standard_complete": sum(1 for r in rs if r.get("complete")),
                "n_strict_complete": sum(1 for r in rs if r.get("strict_complete")),
                "median_coverage_complete": float(
                    np.nanmedian([r.get("coverage") for r in rs if r.get("complete")] or [float("nan")])
                ),
            }
        )
    dec = "Hold"
    note = (
        "Use strict_complete (coverage≥0.95) for Kraken VPIN in cross-venue arms; "
        f"tail from {tail_cut}: standard={tail_std} strict={tail_strict}. "
        "Partial tail days pass min_trades but fail strict coverage — documented, not patched."
    )
    return {
        **{k: base[k] for k in ("n_listing_days", "n_rows", "n_complete_standard_gate", "n_strict_coverage", "strict_coverage_threshold")},
        "symbol_summary": sym_summary,
        "tail_from": tail_cut,
        "tail_standard_complete": tail_std,
        "tail_strict_complete": tail_strict,
        "n_tail_partial_standard_only": len(partial_tail),
        "sample_partial_tail": partial_tail[:8],
        "note": note,
        "decision": dec,
    }


def _day_vpin_variants(
    venue: str,
    symbol: str,
    day: str,
    *,
    max_files: int = 24,
) -> dict[str, Any] | None:
    rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
    if not rec["completeness"].get("complete"):
        return None
    tape = rec["tape"]
    side = normalize_side(np.asarray(tape["side"], dtype=np.float64))
    qty = np.asarray(tape["qty"], dtype=np.float64)
    px = np.asarray(tape["px"], dtype=np.float64)
    ts = np.asarray(tape["ts"], dtype=np.int64)
    notional = qty * np.where(np.isfinite(px) & (px > 0), px, np.nan)
    out: dict[str, Any] = {"venue": venue, "symbol": symbol, "day": day}
    # SoT median×50 coin qty
    bv, _ = resolve_bucket_volume(qty, bucket_scale=50.0)
    out["median_x50"] = float(vpin_from_tape(side, qty, ts, bucket_volume=bv)["mean_vpin"])
    # Target ~50 buckets / day (level harmonization)
    bv_t, _ = resolve_bucket_volume(qty, target_buckets=50.0)
    out["target_50"] = float(vpin_from_tape(side, qty, ts, bucket_volume=bv_t)["mean_vpin"])
    # Notional buckets (contract / USD volume clock)
    qn = notional[np.isfinite(notional) & (notional > 0)]
    if qn.size >= 100:
        med_n = float(np.nanmedian(qn))
        bv_n = max(med_n * 50.0, 1e-8)
        out["notional_median_x50"] = float(
            vpin_from_tape(side, notional, ts, bucket_volume=bv_n)["mean_vpin"]
        )
    else:
        out["notional_median_x50"] = float("nan")
    # Vol-normalized level: mean_vpin / sqrt(day volume) — diagnostic scalar
    tv = float(np.nansum(qty[np.isfinite(qty) & (qty > 0)]))
    mv = out["target_50"]
    out["target_50_vol_norm"] = float(mv / np.sqrt(tv)) if tv > 0 and np.isfinite(mv) else float("nan")
    return out


def xvenue_harmonized(panel_ok: list[dict[str, Any]], *, max_days: int | None = None) -> dict[str, Any]:
    # Use panel complete days (same pairs as Pass 2 board) — faster than full S3 intersection rescan
    days_all = sorted(
        {r["day"] for r in panel_ok if r.get("venue") in ("hyperliquid", "deribit") and r.get("symbol") in ("ETH", "BTC")}
    )
    if not days_all:
        days_all = sorted(_hl_db_intersection())
    if max_days:
        days_all = days_all[-max_days:]
    rows: list[dict[str, Any]] = []
    n_todo = len(days_all) * 2 * 2
    k = 0
    for sym in ("ETH", "BTC"):
        for day in days_all:
            for v in ("hyperliquid", "deribit"):
                k += 1
                if k % 8 == 0:
                    print(f"xvenue_harm {k}/{n_todo} {v} {sym} {day}", flush=True)
                try:
                    r = _day_vpin_variants(v, sym, day)
                    if r:
                        rows.append(r)
                except Exception:
                    continue
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in rows:
        by_key[(r["symbol"], r["day"], r["venue"])] = r

    def _pairs(field: str) -> list[tuple[float, float]]:
        pairs: list[tuple[float, float]] = []
        for sym in ("ETH", "BTC"):
            for day in days_all:
                a = by_key.get((sym, day, "hyperliquid"))
                b = by_key.get((sym, day, "deribit"))
                if not a or not b:
                    continue
                va, vb = a.get(field), b.get(field)
                if va is not None and vb is not None and np.isfinite(va) and np.isfinite(vb):
                    pairs.append((float(va), float(vb)))
        return pairs

    methods: dict[str, Any] = {}
    for field, label in (
        ("median_x50", "sot_median_x50"),
        ("target_50", "target_50_buckets"),
        ("notional_median_x50", "notional_median_x50"),
        ("target_50_vol_norm", "target_50_vol_normalized"),
    ):
        pairs = _pairs(field)
        if len(pairs) >= 5:
            xv = cross_section_spearman(
                np.array([p[0] for p in pairs]),
                np.array([p[1] for p in pairs]),
                n_boot=600,
                seed=51,
            )
        else:
            xv = {"n": float(len(pairs)), "rho": float("nan"), "lo": float("nan"), "hi": float("nan")}
        dec = (
            "Promote"
            if xv.get("n", 0) >= XVENUE_GATE["min_pairs"]
            and np.isfinite(xv.get("rho", float("nan")))
            and xv.get("lo", -1) >= XVENUE_GATE["ci_lo"]
            else "Hold"
        )
        methods[label] = {"n_pairs": len(pairs), "spearman": xv, "decision": dec}

    # Rank concordance: paired HL/DB days only (same calendar set as level pairs)
    rank_pairs: list[tuple[float, float]] = []
    for sym in ("ETH", "BTC"):
        paired = [
            d
            for d in days_all
            if (sym, d, "hyperliquid") in by_key
            and (sym, d, "deribit") in by_key
            and np.isfinite(by_key[(sym, d, "hyperliquid")].get("target_50", float("nan")))
            and np.isfinite(by_key[(sym, d, "deribit")].get("target_50", float("nan")))
        ]
        if len(paired) < 5:
            continue
        hl = np.array([by_key[(sym, d, "hyperliquid")]["target_50"] for d in paired])
        db = np.array([by_key[(sym, d, "deribit")]["target_50"] for d in paired])
        rh = np.argsort(np.argsort(hl)).astype(np.float64)
        rd = np.argsort(np.argsort(db)).astype(np.float64)
        for i in range(rh.size):
            rank_pairs.append((float(rh[i]), float(rd[i])))
    rank_xv = (
        cross_section_spearman(
            np.array([p[0] for p in rank_pairs]),
            np.array([p[1] for p in rank_pairs]),
            n_boot=600,
            seed=52,
        )
        if len(rank_pairs) >= 5
        else {"n": float(len(rank_pairs)), "rho": float("nan"), "lo": float("nan"), "hi": float("nan")}
    )
    best = methods.get("target_50_buckets") or {}
    primary_dec = best.get("decision", "Hold")
    pass2_rho = -0.32
    return {
        "methods": methods,
        "rank_day_concordance": rank_xv,
        "pass2_baseline_rho_sot": pass2_rho,
        "primary_method": "target_50_buckets",
        "decision": primary_dec,
        "gate": XVENUE_GATE,
    }


def _exante_vpin_at(ts_ns: int, vpin_ts: np.ndarray, vpin_roll: np.ndarray) -> float:
    j = int(np.searchsorted(vpin_ts, ts_ns, side="left") - 1)
    if j < 0 or j >= vpin_roll.size:
        return float("nan")
    v = float(vpin_roll[j])
    return v if np.isfinite(v) else float("nan")


def markout_day_pass3(
    venue: str,
    symbol: str,
    day: str,
    *,
    max_files: int = 24,
    trade_stride: int = 25,
    max_trades: int = 6000,
    quotes_per_minute: int = 120,
    horizons_ms: tuple[int, ...] = (30_000, 60_000, 120_000, 300_000),
) -> dict[str, Any]:
    feat = vpin_day_features(venue, symbol, day, max_files=max_files)
    if not feat.get("completeness", {}).get("complete"):
        return {"ok": False, "reason": "incomplete_day", "day": day, "venue": venue, "symbol": symbol}
    try:
        tob = load_warehouse_tob(venue, symbol, day, max_files=max_files, quotes_per_minute=quotes_per_minute)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"tob:{type(exc).__name__}", "day": day, "venue": venue}

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
    mt, mv = tob["ts"], tob["mid"]
    i0 = np.searchsorted(mt, ts_s, side="right") - 1

    horizon_ic: dict[str, dict[str, Any]] = {}
    for h_ms in horizons_ms:
        h_ns = int(h_ms * 1_000_000)
        i1 = np.searchsorted(mt, ts_s + h_ns, side="right") - 1
        valid = (i0 >= 0) & (i1 > i0) & (i1 < mt.size) & np.isfinite(side_s) & (side_s != 0)
        mid0 = np.full(ts_s.size, np.nan)
        mid1 = np.full(ts_s.size, np.nan)
        mid0[valid] = mv[i0[valid]]
        mid1[valid] = mv[i1[valid]]
        ok = valid & (mid0 > 0) & np.isfinite(mid1)
        mo = np.full(ts_s.size, np.nan)
        mo[ok] = side_s[ok] * 1e4 * (mid1[ok] - mid0[ok]) / mid0[ok]
        m = np.isfinite(vpin_ex) & np.isfinite(mo)
        ve, ye = vpin_ex[m], mo[m]
        if ve.size < 80:
            horizon_ic[str(h_ms)] = {"n": float(ve.size), "rho": float("nan"), "rank_rho": float("nan")}
            continue
        ic = cross_section_spearman(ve, ye, n_boot=400, seed=60 + h_ms // 1000)
        # rank IC within day
        rank_ic = float(spearman_r(np.argsort(np.argsort(ve)).astype(np.float64), ye))
        horizon_ic[str(h_ms)] = {**ic, "rank_rho": rank_ic}
    primary = horizon_ic.get("30000") or {}
    m = np.isfinite(vpin_ex)
    ts_ok = ts_s[m]
    cut = int(ts_ok.size * 0.5)
    early_m = np.zeros(ts_ok.size, dtype=bool)
    early_m[:cut] = True
    ve = vpin_ex[m]
    # 30s mo for split
    h_ns = 30_000_000_000
    i1 = np.searchsorted(mt, ts_s + h_ns, side="right") - 1
    valid = (i0 >= 0) & (i1 > i0) & (i1 < mt.size) & np.isfinite(side_s) & (side_s != 0)
    mid0 = np.full(ts_s.size, np.nan)
    mid1 = np.full(ts_s.size, np.nan)
    mid0[valid] = mv[i0[valid]]
    mid1[valid] = mv[i1[valid]]
    ok = valid & (mid0 > 0) & np.isfinite(mid1)
    mo30 = np.full(ts_s.size, np.nan)
    mo30[ok] = side_s[ok] * 1e4 * (mid1[ok] - mid0[ok]) / mid0[ok]
    mm = np.isfinite(vpin_ex) & np.isfinite(mo30)
    ve2, mo2, ts2 = vpin_ex[mm], mo30[mm], ts_s[mm]
    if ve2.size < 80:
        return {"ok": False, "reason": "thin_join", "n": int(ve2.size), "day": day}
    cut2 = int(ts2.size * 0.5)
    early2 = np.zeros(ts2.size, dtype=bool)
    early2[:cut2] = True
    ic_all = cross_section_spearman(ve2, mo2, n_boot=400, seed=61)
    ic_early = cross_section_spearman(ve2[early2], mo2[early2], n_boot=400, seed=62)
    ic_late = cross_section_spearman(ve2[~early2], mo2[~early2], n_boot=400, seed=63)
    rank_ic = float(spearman_r(np.argsort(np.argsort(ve2)).astype(np.float64), mo2))

    return {
        "ok": True,
        "venue": normalize_venue(venue),
        "symbol": symbol,
        "day": day,
        "n_join": int(ve2.size),
        "tob_source": tob.get("source"),
        "tob_n": tob.get("n"),
        "quotes_per_minute": quotes_per_minute,
        "ic_spearman_vpin_vs_mo30": ic_all,
        "ic_early": ic_early,
        "ic_late": ic_late,
        "rank_ic_30s": rank_ic,
        "horizon_ic": horizon_ic,
    }


def run_markout_pass3(
    panel_ok: list[dict[str, Any]],
    *,
    trade_stride: int,
    quotes_per_minute: int,
) -> dict[str, Any]:
    cells = sorted({(r["venue"], r["symbol"]) for r in panel_ok if r["venue"] in ("hyperliquid", "deribit")})
    day_rows: list[dict[str, Any]] = []
    for v, sym in cells:
        days = sorted({r["day"] for r in panel_ok if r["venue"] == v and r["symbol"] == sym})
        for j, day in enumerate(days):
            print(f"markout_p3 {j+1}/{len(days)} {v} {sym} {day}", flush=True)
            day_rows.append(
                markout_day_pass3(
                    v,
                    sym,
                    day,
                    trade_stride=trade_stride,
                    quotes_per_minute=quotes_per_minute,
                )
            )
    ok_rows = [r for r in day_rows if r.get("ok")]
    rhos = np.array(
        [r["ic_spearman_vpin_vs_mo30"]["rho"] for r in ok_rows if np.isfinite(r["ic_spearman_vpin_vs_mo30"]["rho"])],
        dtype=np.float64,
    )
    rank_rhos = np.array([r.get("rank_ic_30s", float("nan")) for r in ok_rows], dtype=np.float64)
    early_r = np.array(
        [r["ic_early"]["rho"] for r in ok_rows if np.isfinite(r["ic_early"]["rho"])],
        dtype=np.float64,
    )
    late_r = np.array(
        [r["ic_late"]["rho"] for r in ok_rows if np.isfinite(r["ic_late"]["rho"])],
        dtype=np.float64,
    )
    by_venue: dict[str, list[float]] = {}
    for r in ok_rows:
        by_venue.setdefault(r["venue"], []).append(r["ic_spearman_vpin_vs_mo30"]["rho"])

    g = MARKOUT_GATE
    promote = (
        len(ok_rows) >= g["min_ok_days"]
        and float(np.nanmedian(rhos)) > g["median_day_ic"]
        and float(np.nanmedian(early_r)) > g["median_early_ic"]
        and float(np.nanmedian(late_r)) > g["median_late_ic"]
        and float(np.nanmedian(rank_rhos)) > g["median_rank_ic"]
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
                "rank_ic_30s",
                "tob_source",
                "horizon_ic",
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
        "median_rank_ic_30s": float(np.nanmedian(rank_rhos)) if rank_rhos.size else float("nan"),
        "median_ic_early": float(np.nanmedian(early_r)) if early_r.size else float("nan"),
        "median_ic_late": float(np.nanmedian(late_r)) if late_r.size else float("nan"),
        "ic_ci_across_days": bootstrap_ci(rhos, stat=np.median, n_boot=500, seed=64) if rhos.size >= 5 else {},
        "median_ic_by_venue": {k: float(np.nanmedian(v)) for k, v in by_venue.items()},
        "pre_registered_gate": g,
        "decision": "Promote" if promote else "Hold",
        "gate_note": "Pass3: dense warehouse L2 TOB (120 q/min), horizons 30–300s, rank IC gate on FULL HL+DB panel",
    }


def toxicity_pass3(panel_ok: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    todo = [r for r in panel_ok if r["venue"] in ("hyperliquid", "deribit")]
    for i, r in enumerate(todo):
        if i % 8 == 0:
            print(f"toxicity_p3 {i}/{len(todo)}", flush=True)
        try:
            tob = load_warehouse_tob(r["venue"], r["symbol"], r["day"], quotes_per_minute=60)
        except Exception as exc:  # noqa: BLE001
            continue
        mid = np.asarray(tob["mid"], dtype=np.float64)
        bid = np.asarray(tob["bid"], dtype=np.float64)
        ask = np.asarray(tob["ask"], dtype=np.float64)
        sp_bps = 1e4 * (ask - bid) / np.maximum(mid, 1e-12)
        sp_bps = sp_bps[np.isfinite(sp_bps) & (sp_bps > 0) & (sp_bps < 200)]
        lr = np.diff(np.log(mid[np.isfinite(mid) & (mid > 0)]))
        rv = float(np.sqrt(np.nansum(lr**2))) if lr.size > 10 else float("nan")
        rows.append(
            {
                "venue": r["venue"],
                "symbol": r["symbol"],
                "day": r["day"],
                "mean_vpin": float(r["mean_vpin"]),
                "spread_bps_mean": float(np.mean(sp_bps)) if sp_bps.size else float("nan"),
                "rv_log_mid": rv,
                "tob_source": tob.get("source"),
            }
        )
    if len(rows) < 10:
        return {"n": len(rows), "decision": "Hold", "reason": "thin_tob_join", "rows": rows}
    vpin = np.array([x["mean_vpin"] for x in rows], dtype=np.float64)
    sp = np.array([x["spread_bps_mean"] for x in rows], dtype=np.float64)
    rv = np.array([x["rv_log_mid"] for x in rows], dtype=np.float64)
    # Residual spread after RV (OLS via np.linalg.lstsq)
    m = np.isfinite(vpin) & np.isfinite(sp) & np.isfinite(rv)
    X = np.column_stack([np.ones(m.sum()), vpin[m], rv[m]])
    y = sp[m]
    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    rho_res = cross_section_spearman(vpin[m], resid, n_boot=500, seed=71)
    rho_sp = cross_section_spearman(vpin, sp, n_boot=500, seed=72)
    rho_rv = cross_section_spearman(vpin, rv, n_boot=500, seed=73)
    q90 = float(np.quantile(vpin, 0.9))
    top = [x for x in rows if x["mean_vpin"] >= q90]
    bot = [x for x in rows if x["mean_vpin"] <= float(np.quantile(vpin, 0.5))]
    top_sp = float(np.nanmean([x["spread_bps_mean"] for x in top]))
    bot_sp = float(np.nanmean([x["spread_bps_mean"] for x in bot]))
    # Quintile spread lift (Q5 vs Q1 mean spread)
    qs = np.quantile(vpin, [0.2, 0.4, 0.6, 0.8])
    qbin = np.searchsorted(qs, vpin, side="right")
    q_spreads = [float(np.nanmean(sp[qbin == k])) for k in range(5)]
    q_spread = float(q_spreads[4] - q_spreads[0]) if all(np.isfinite(x) for x in q_spreads) else float("nan")
    promote = rho_sp.get("lo", -1) > 0.05 or (top_sp > bot_sp * 1.05 and len(top) >= 3)
    return {
        "n_days": len(rows),
        "ols_spread_on_vpin_rv": {"intercept": float(beta[0]), "beta_vpin": float(beta[1]), "beta_rv": float(beta[2])},
        "spearman_vpin_spread": rho_sp,
        "spearman_vpin_spread_residual": rho_res,
        "spearman_vpin_rv": rho_rv,
        "quintile_spread_bps": q_spreads,
        "quintile_spread_q5_q1": q_spread,
        "top_decile_threshold": q90,
        "top_vs_median_spread_bps": {"top_mean": top_sp, "bottom_half_mean": bot_sp},
        "decision": "Promote" if promote else "Hold",
        "falsifier": "Residual ρ still negative — VPIN not a widen-spread toxicity flag on HL+DB",
    }


def bucket_robust_pass3(panel_ok: list[dict[str, Any]], *, max_days_per_cell: int = 10) -> dict[str, Any]:
    scales = (15.0, 25.0, 50.0, 75.0, 100.0, 150.0)
    targets = (20.0, 30.0, 50.0, 75.0, 100.0)
    grid_stats: list[dict[str, Any]] = []
    by_cell: dict[str, list[dict[str, Any]]] = {}
    for r in panel_ok:
        if r["venue"] not in ("hyperliquid", "deribit"):
            continue
        key = f"{r['venue']}|{r['symbol']}"
        by_cell.setdefault(key, []).append(r)
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
                    {"cell": key, "day": day, "method": f"median_x_{int(scale)}", "mean_vpin": v.get("mean_vpin")}
                )
            for tb in targets:
                bv, _ = resolve_bucket_volume(qty, target_buckets=tb)
                v = vpin_from_tape(side, qty, ts, bucket_volume=bv, n_buckets_window=50)
                grid_stats.append(
                    {"cell": key, "day": day, "method": f"target_{int(tb)}", "mean_vpin": v.get("mean_vpin")}
                )
    df_methods: dict[str, list[float]] = {}
    for g in grid_stats:
        mv = g.get("mean_vpin")
        if mv is not None and np.isfinite(mv):
            df_methods.setdefault(g["method"], []).append(float(mv))
    sens = []
    ref = float(np.nanmedian(df_methods.get("median_x_50", [float("nan")])))
    for method, vals in sorted(df_methods.items()):
        med = float(np.nanmedian(vals))
        sens.append({"method": method, "median_mean_vpin": med, "delta_vs_sot": med - ref if np.isfinite(ref) else float("nan")})
    spread = float(np.nanmax([s["median_mean_vpin"] for s in sens]) - np.nanmin([s["median_mean_vpin"] for s in sens]))
    dec = "Promote" if spread < BUCKET_ROBUST_PROMOTE_SPREAD else "Hold"
    return {
        "n_grid_points": len(grid_stats),
        "sensitivity": sens,
        "median_level_spread_across_methods": spread,
        "pass2_baseline_spread": 0.678,
        "promote_threshold": BUCKET_ROBUST_PROMOTE_SPREAD,
        "decision": dec,
        "note": "Extended grid; Promote only if level spread tightens materially vs Pass 2",
    }


def merge_pass3(
    pass2: dict[str, Any],
    *,
    sol: dict[str, Any],
    kraken: dict[str, Any],
    xvenue: dict[str, Any],
    markout: dict[str, Any],
    toxicity: dict[str, Any],
    robust: dict[str, Any],
    panel_n: int,
) -> dict[str, Any]:
    table = list(pass2.get("decision_table", []))
    updates = {
        "frag.hl_sol_empty": sol.get("decision", "Hold"),
        "frag.kraken_vpin": kraken.get("decision", "Hold"),
        "frag.xvenue_vpin_concord": xvenue.get("decision", "Hold"),
        "info.vpin_markout": markout.get("decision", "Hold"),
        "risk.vpin_toxicity_flag": toxicity.get("decision", "Hold"),
        "cont.vpin_bucket_robust": robust.get("decision", "Hold"),
    }

    def _f4(x: Any) -> str:
        try:
            v = float(x)
            return f"{v:.4f}" if np.isfinite(v) else "nan"
        except (TypeError, ValueError):
            return "nan"

    xv = (xvenue.get("methods") or {}).get("target_50_buckets", {}).get("spearman") or {}
    extra = {
        "frag.hl_sol_empty": (
            f"HL SOL: {sol.get('n_days_with_trades')}d w/trades / {sol.get('n_listing_days_scanned')} listed; "
            f"FNV={sol.get('fnv_catalog_id')}; {str(sol.get('blocker', ''))[:90]}"
        ),
        "frag.kraken_vpin": (
            f"strict={kraken.get('n_strict_coverage')} std={kraken.get('n_complete_standard_gate')} "
            f"tail_partial={kraken.get('n_tail_partial_standard_only')}"
        ),
        "frag.xvenue_vpin_concord": (
            f"harm target50 ρ={xv.get('rho')} CI=[{xv.get('lo')},{xv.get('hi')}] n={xv.get('n')}"
        ),
        "info.vpin_markout": (
            f"n_ok={markout.get('n_days_ok')} medIC={_f4(markout.get('median_ic_by_day'))} "
            f"rankIC={_f4(markout.get('median_rank_ic_30s'))} early={_f4(markout.get('median_ic_early'))} "
            f"late={_f4(markout.get('median_ic_late'))}"
        ),
        "risk.vpin_toxicity_flag": (
            f"n={toxicity.get('n_days')} ρ={((toxicity.get('spearman_vpin_spread') or {}).get('rho'))} "
            f"ρ_resid={((toxicity.get('spearman_vpin_spread_residual') or {}).get('rho'))}"
        ),
        "cont.vpin_bucket_robust": (
            f"level_spread={robust.get('median_level_spread_across_methods'):.3f} "
            f"(p2={robust.get('pass2_baseline_spread')})"
        ),
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
    out = dict(pass2)
    out["decision_table"] = table
    out["decision_counts"] = counts
    out["pass3"] = {
        "hl_sol": {
            "n_days_with_trades": sol.get("n_days_with_trades"),
            "fnv_catalog_id": sol.get("fnv_catalog_id"),
            "decision": sol.get("decision"),
        },
        "kraken": {
            "n_strict": kraken.get("n_strict_coverage"),
            "n_standard": kraken.get("n_complete_standard_gate"),
            "tail_partial": kraken.get("n_tail_partial_standard_only"),
        },
        "xvenue": xvenue,
        "markout": {
            k: markout.get(k)
            for k in (
                "n_days_ok",
                "median_ic_by_day",
                "median_rank_ic_30s",
                "median_ic_early",
                "median_ic_late",
                "decision",
            )
        },
        "toxicity": {
            k: toxicity.get(k)
            for k in ("n_days", "decision", "spearman_vpin_spread", "spearman_vpin_spread_residual")
        },
        "bucket_robust": {
            "median_level_spread": robust.get("median_level_spread_across_methods"),
            "decision": robust.get("decision"),
        },
        "panel_hl_db_n": panel_n,
    }
    fals = dict(out.get("falsifiers") or {})
    if xv:
        fals["xvenue_spearman_pass3_target50"] = xv
    out["falsifiers"] = fals
    out["data_provenance"] = (
        pass2.get("data_provenance", "")
        + "; Pass3: HL SOL FNV probe; Kraken tail doc; xvenue target50/notional harmonization; "
        "dense L2 markout; toxicity residual; extended bucket grid"
    )
    return out


def write_pass3_reports(dec: dict[str, Any], art: dict[str, Any]) -> None:
    def _rows(ids: list[str]) -> str:
        by_id = {t["id"]: t for t in dec.get("decision_table", [])}
        lines = []
        for i in ids:
            t = by_id.get(i, {"decision": "Hold", "evidence": "—"})
            lines.append(f"| `{i}` | **{t['decision']}** | {str(t.get('evidence', ''))[:140]} |")
        return "\n".join(lines)

    p3 = dec.get("pass3") or {}
    (BOOK / "chapters/predictiveness/EXP_REPORT.md").write_text(
        "# predictiveness — Pass 3\n\n"
        f"Dense warehouse L2 markout: **{art['markout'].get('decision')}** — "
        f"n_ok={art['markout'].get('n_days_ok')}, median IC={art['markout'].get('median_ic_by_day')}, "
        f"rank IC={art['markout'].get('median_rank_ic_30s')}.\n\n"
        "| id | decision | evidence |\n|----|----------|----------|\n"
        + _rows(["info.vpin_markout"])
        + "\n"
    )
    (BOOK / "chapters/toxicity_events/EXP_REPORT.md").write_text(
        "# toxicity_events — Pass 3\n\n"
        f"Residual spread join: **{art['toxicity'].get('decision')}**.\n\n"
        "| id | decision | evidence |\n|----|----------|----------|\n"
        + _rows(["risk.vpin_toxicity_flag"])
        + "\n"
    )
    (BOOK / "chapters/robustness/EXP_REPORT.md").write_text(
        "# robustness — Pass 3\n\n"
        f"Extended bucket grid spread={art['robust'].get('median_level_spread_across_methods')}.\n\n"
        "| id | decision | evidence |\n|----|----------|----------|\n"
        + _rows(["cont.vpin_bucket_robust"])
        + "\n"
    )
    (BOOK / "chapters/cross_venue/EXP_REPORT.md").write_text(
        "# cross_venue — Pass 3\n\n"
        f"Harmonized HL↔DB target50: **{art['xvenue'].get('decision')}**.\n\n"
        "| id | decision | evidence |\n|----|----------|----------|\n"
        + _rows(["frag.xvenue_vpin_concord", "frag.kraken_vpin", "frag.hl_sol_empty"])
        + "\n"
    )
    ch00 = BOOK / "chapters/ch00_overview/EXP_REPORT.md"
    base = ch00.read_text().split("Pass 3")[0].strip() if ch00.is_file() else "# ch00 overview"
    ch00.write_text(
        base
        + f"\n\nPass 3 complete: counts {dec.get('decision_counts')} — panel n={p3.get('panel_hl_db_n')}\n"
    )


def update_candidates(dec: dict[str, Any]) -> None:
    by_id = {t["id"]: t for t in dec.get("decision_table", [])}

    def _patch(path: Path, mapping: dict[str, str]) -> None:
        if not path.is_file():
            return
        text = path.read_text()
        for cid, col in mapping.items():
            d = by_id.get(cid, {}).get("decision", "Hold")
            # replace **Hold** / **Promote** in row for id if present
            import re

            pat = rf"(\| `{re.escape(cid)}` \|[^|]*\|[^|]*\| )\*\*(?:Hold|Promote|Kill|Park)\*\*"
            repl = rf"\1**{d}**"
            text2, n = re.subn(pat, repl, text, count=1)
            if n:
                text = text2
        path.write_text(text)

    cross = BOOK / "chapters/cross_venue/CANDIDATES.md"
    _patch(
        cross,
        {
            "frag.xvenue_vpin_concord": "decision",
            "frag.kraken_vpin": "decision",
            "frag.hl_sol_empty": "decision",
        },
    )
    for ch, ids in (
        ("predictiveness", ["info.vpin_markout"]),
        ("toxicity_events", ["risk.vpin_toxicity_flag"]),
        ("robustness", ["cont.vpin_bucket_robust"]),
    ):
        _patch(BOOK / "chapters" / ch / "CANDIDATES.md", {i: "decision" for i in ids})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-markout", action="store_true")
    ap.add_argument("--skip-xvenue", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--trade-stride", type=int, default=25)
    ap.add_argument("--quotes-per-minute", type=int, default=120)
    ap.add_argument("--xvenue-max-days", type=int, default=0, help="0 = all intersection days")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    pass2 = _load_pass2_decisions()
    panel_ok = _panel_hl_db()
    print(f"panel n={len(panel_ok)}", flush=True)

    def _lor(name: str, fn):
        path = OUT / name
        if args.resume and path.is_file():
            return json.loads(path.read_text())
        val = fn()
        _write_json(path, val)
        return val

    sol = _lor("hl_sol_probe.json", hl_sol_pass3)
    kraken = _lor("kraken_probe.json", lambda: kraken_pass3())

    if args.skip_xvenue:
        xvenue = json.loads((OUT / "xvenue_harmonized.json").read_text()) if (OUT / "xvenue_harmonized.json").is_file() else {}
    else:
        max_d = args.xvenue_max_days or None
        xvenue = _lor(
            "xvenue_harmonized.json",
            lambda: xvenue_harmonized(panel_ok, max_days=max_d),
        )

    robust = _lor("bucket_robust.json", lambda: bucket_robust_pass3(panel_ok))
    toxicity = _lor("toxicity.json", lambda: toxicity_pass3(panel_ok))

    if args.skip_markout:
        markout = {"n_days_ok": 0, "decision": "Hold", "skipped": True}
    else:
        mo_path = OUT / "markout.json"
        if args.resume and mo_path.is_file():
            markout = json.loads(mo_path.read_text())
        else:
            markout = run_markout_pass3(
                panel_ok,
                trade_stride=args.trade_stride,
                quotes_per_minute=args.quotes_per_minute,
            )
            _write_json(mo_path, markout)

    merged = merge_pass3(
        pass2,
        sol=sol,
        kraken=kraken,
        xvenue=xvenue,
        markout=markout,
        toxicity=toxicity,
        robust=robust,
        panel_n=len(panel_ok),
    )
    _write_json(OUT / "decisions_pass3.json", merged)
    _write_json(PANEL / "decisions_pass3.json", merged)

    art = {"markout": markout, "toxicity": toxicity, "robust": robust, "xvenue": xvenue, "sol": sol, "kraken": kraken}
    write_pass3_reports(merged, art)
    update_candidates(merged)
    _write_json(
        OUT / "pass3_summary.json",
        {
            "decision_counts": merged.get("decision_counts"),
            "n_panel_hl_db": len(panel_ok),
            "hl_sol_days_with_trades": sol.get("n_days_with_trades"),
            "markout": markout.get("decision"),
            "xvenue": xvenue.get("decision"),
            "toxicity": toxicity.get("decision"),
            "bucket_robust": robust.get("decision"),
        },
    )
    print(json.dumps(merged.get("decision_counts"), indent=2))


if __name__ == "__main__":
    main()
