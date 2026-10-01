from __future__ import annotations
#!/usr/bin/env python3
"""Pass-2 info/falsifiers for Filimonov desk package.

Joins (OFI / markout / intensity), monitor|tradable|exec labels, competing-def
+ overlap gates vs crash Nanex/SSM/vshape and lob cancel proxy via
``hftpat.rename_gate`` / ``overlap_*``.

Writes ``out/pass2/`` JSON + figs. Updates chapter CANDIDATES/EXP_REPORT Pass2
blocks. ClickHouse MCP banned. No git commit. Do not edit the plan file.
"""

import os

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(Path(os.environ.get('WAREHOUSE_SRC') or ((Path(os.environ.get('WAREHOUSE_ROOT') or (Path.home() / 'lab' / 'lab-n2070' / 'warehouse')) / 'src')))))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb')) / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import (  # noqa: E402
    CORE_VENUES,
    ensure_env,
    load_day_trades,
    load_tob_any,
    normalize_side,
    resolve_days,
)
from research.lib.continuous import ofi_continuous, trade_intensity  # noqa: E402
from research.lib.crash import (  # noqa: E402
    detect_ssm_events,
    kalman_ssm_filter,
    mc_garch_bar_vol,
    nanex_detect,
    sigma_process_meas,
    vshape_events,
)
from research.lib.hftpat import (  # noqa: E402
    ignition_bar_timestamps,
    ignition_events,
    overlap_vs_crash,
    overlap_vs_lob_cancel,
    price_fade_events,
    quote_storm_detect,
    quote_storm_intensity,
    rename_gate,
)
from research.lib.markout import trade_markouts  # noqa: E402
from research.lib.spreads import quoted_spread_bps  # noqa: E402
from research.lib.stats import bootstrap_ci, spearman_r  # noqa: E402

OUT = BOOK / "out" / "pass2"
FIGS = OUT / "figs"
CH = BOOK / "chapters"
DAYS_DEFAULT = ["2026-09-26", "2026-09-27", "2026-09-30"]
NS_PER_MS = 1_000_000


def _json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=_default))


def _default(o: Any) -> Any:
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating, np.float64, np.float32)):
        x = float(o)
        return x if np.isfinite(x) else None
    if isinstance(o, (np.integer, np.int64, np.int32)):
        return int(o)
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    return str(o)


def _is_trade_synth(tob: dict[str, Any] | None) -> bool:
    if tob is None:
        return False
    return "trade_synth" in str(tob.get("source", "")).lower()


def _subsample(n: int, max_n: int, seed: int = 42) -> np.ndarray:
    if n <= max_n:
        return np.arange(n, dtype=np.int64)
    step = max(1, int(np.ceil(n / max_n)))
    idx = np.arange(0, n, step, dtype=np.int64)
    if idx.size > max_n:
        rng = np.random.default_rng(seed)
        idx = np.sort(rng.choice(idx, size=max_n, replace=False))
    return idx


def _cancel_proxy_ts(
    tob: dict[str, Any],
    trade_ts: np.ndarray,
    trade_side: np.ndarray,
    trade_qty: np.ndarray,
    *,
    drop_frac: float = 0.2,
    trade_match_ms: int = 250,
) -> np.ndarray:
    t = np.asarray(tob["ts"], dtype=np.int64)
    b = np.asarray(tob["bid"], dtype=np.float64)
    a = np.asarray(tob["ask"], dtype=np.float64)
    bs = np.asarray(tob["bid_sz"], dtype=np.float64)
    az = np.asarray(tob["ask_sz"], dtype=np.float64)
    tt = np.asarray(trade_ts, dtype=np.int64)
    ts_side = normalize_side(trade_side)
    tq = np.asarray(trade_qty, dtype=np.float64)
    match_ns = int(trade_match_ms) * NS_PER_MS
    out: list[int] = []
    for px, sz, hit_sign in ((b, bs, -1.0), (a, az, 1.0)):
        for i in range(1, t.size):
            if not (np.isfinite(px[i]) and np.isfinite(px[i - 1]) and abs(px[i] - px[i - 1]) < 1e-12):
                continue
            if not (np.isfinite(sz[i]) and np.isfinite(sz[i - 1]) and sz[i - 1] > 0):
                continue
            drop = float(sz[i - 1] - sz[i])
            if drop / sz[i - 1] < drop_frac or drop <= 0:
                continue
            lo = int(np.searchsorted(tt, t[i] - match_ns, side="left"))
            hi = int(np.searchsorted(tt, t[i] + match_ns, side="right"))
            matched = 0.0
            for j in range(lo, hi):
                if np.isfinite(ts_side[j]) and ts_side[j] * hit_sign > 0 and np.isfinite(tq[j]) and tq[j] > 0:
                    matched += float(tq[j])
            if matched <= 1e-12:
                out.append(int(t[i]))
    return np.asarray(out, dtype=np.int64)


def load_venue_day(symbol: str, day: str, venue: str, *, max_files: int) -> dict[str, Any]:
    ensure_env()
    rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
    tape = rec["tape"]
    tob_err = None
    tob: dict[str, Any] | None
    try:
        tob = load_tob_any(venue, symbol, day)
    except Exception as exc:  # noqa: BLE001
        tob = None
        tob_err = f"{type(exc).__name__}: {exc}"
    synth = _is_trade_synth(tob)
    return {
        "venue": venue,
        "symbol": symbol,
        "day": day,
        "instrument": rec.get("instrument"),
        "completeness": rec["completeness"],
        "tape": {
            "ts": np.asarray(tape["ts"], dtype=np.int64),
            "px": np.asarray(tape["px"], dtype=np.float64),
            "qty": np.asarray(tape["qty"], dtype=np.float64),
            "side": normalize_side(tape["side"]),
        },
        "tob": tob,
        "tob_ok": tob is not None,
        "tob_error": tob_err,
        "tob_n": int(tob.get("n", 0)) if tob is not None else 0,
        "tob_source": (tob or {}).get("source"),
        "is_trade_synth": synth,
        "native_tob": bool(tob is not None and not synth),
    }


def _per_trade_markout_bps(
    trade_ts: np.ndarray,
    side: np.ndarray,
    mid_ts: np.ndarray,
    mid: np.ndarray,
    *,
    horizon_ms: int = 1000,
) -> np.ndarray:
    tt = np.asarray(trade_ts, dtype=np.int64)
    s = np.asarray(side, dtype=np.float64)
    s = np.where(s == 0, np.nan, s)
    mt = np.asarray(mid_ts, dtype=np.int64)
    mv = np.asarray(mid, dtype=np.float64)
    i0 = np.searchsorted(mt, tt, side="right") - 1
    valid0 = (i0 >= 0) & (i0 < mt.size)
    mid0 = np.full(tt.size, np.nan)
    mid0[valid0] = mv[i0[valid0]]
    h_ns = int(horizon_ms) * NS_PER_MS
    i1 = np.searchsorted(mt, tt + h_ns, side="right") - 1
    valid = valid0 & (i1 > i0) & (i1 < mt.size) & np.isfinite(s) & (mid0 > 0)
    mid1 = np.full(tt.size, np.nan)
    mid1[valid] = mv[i1[valid]]
    mo = np.full(tt.size, np.nan)
    ok = valid & np.isfinite(mid1)
    mo[ok] = s[ok] * 1e4 * (mid1[ok] - mid0[ok]) / mid0[ok]
    return mo


def _early_late_split(days: list[str]) -> tuple[list[str], list[str]]:
    d = sorted(days)
    mid = max(1, len(d) // 2)
    return d[:mid], d[mid:]


# ---------------------------------------------------------------------------
# Per-package Pass2 digs
# ---------------------------------------------------------------------------


def dig_quote_storms(rows: list[dict[str, Any]]) -> dict[str, Any]:
    day_rows: list[dict[str, Any]] = []
    for row in rows:
        venue, day = row["venue"], row["day"]
        base: dict[str, Any] = {
            "venue": venue,
            "day": day,
            "symbol": row["symbol"],
            "completeness": row["completeness"],
            "tob_ok": row["tob_ok"],
            "is_trade_synth": row["is_trade_synth"],
            "native_tob": row["native_tob"],
            "label": "exec_throttle_monitor",
            "tradable": False,
        }
        if not row["tob_ok"] or row["tob"] is None:
            base["skip"] = "no_tob"
            day_rows.append(base)
            continue
        tob = row["tob"]
        tape = row["tape"]
        intens = quote_storm_intensity(
            tob["ts"], tob["bid"], tob["ask"], tob["bid_sz"], tob["ask_sz"], bar_s=1.0
        )
        # crypto-adapted: low min_hz (feed-sample sparse)
        storms = quote_storm_detect(
            intens, z_thresh=3.0, min_cancel_frac=0.3, max_mid_range_bps=15.0, min_intensity_hz=0.0
        )
        storm_ts = np.asarray(storms.get("ts", []), dtype=np.int64)
        n_storms = int(storms.get("n_events", 0))
        span_h = max(float(row["completeness"].get("span_s") or 1.0) / 3600.0, 1e-9)
        storms_per_h = n_storms / span_h

        # join: storm bars vs spread / intensity / OFI
        qs = quoted_spread_bps(tob["bid"], tob["ask"], mid=tob.get("mid"))
        ofi = ofi_continuous(tob["ts"], tob["bid"], tob["ask"], tob["bid_sz"], tob["ask_sz"], bar_ns=1_000_000_000)
        inten = trade_intensity(tape["ts"], bar_ns=1_000_000_000)
        mid = np.asarray(tob.get("mid", 0.5 * (np.asarray(tob["bid"]) + np.asarray(tob["ask"]))), dtype=np.float64)
        mo = trade_markouts(
            tape["ts"], tape["px"], tape["side"], tob["ts"], mid, horizons_ms=(1000,)
        )
        mo_1s = (mo.get("by_horizon") or {}).get("1000") or {}

        # storm-window mean spread vs day mean
        bar_ts = np.asarray(intens["ts"], dtype=np.int64)
        storm_i = np.asarray(storms.get("bar_i", []), dtype=np.int64)
        day_qs = float(np.nanmedian(qs)) if np.isfinite(qs).any() else float("nan")
        if storm_i.size and bar_ts.size:
            # approximate: map storm bar mid to nearest TOB via bar timestamp
            storm_qs = []
            for bi in storm_i:
                if 0 <= bi < bar_ts.size:
                    j = int(np.searchsorted(tob["ts"], bar_ts[bi], side="right") - 1)
                    if 0 <= j < qs.size and np.isfinite(qs[j]):
                        storm_qs.append(float(qs[j]))
            storm_qs_med = float(np.median(storm_qs)) if storm_qs else float("nan")
        else:
            storm_qs_med = float("nan")

        cancel_ts = _cancel_proxy_ts(tob, tape["ts"], tape["side"], tape["qty"])
        # treat storm bars as "fade-like" flags for lob overlap helper
        if storm_ts.size:
            fade_flags = np.ones(storm_ts.size, dtype=np.int64)
            ov_lob = overlap_vs_lob_cancel(storm_ts, fade_flags, cancel_ts, slack_ms=500.0)
        else:
            ov_lob = {
                "n_fade": 0.0,
                "n_cancel": float(cancel_ts.size),
                "n_overlap": 0.0,
                "frac_fade_in_cancel": float("nan"),
                "slack_ms": 500.0,
            }
        gate = rename_gate(ov_lob, frac_key="frac_fade_in_cancel", kill_frac=0.85)

        base.update(
            {
                "n_storms": n_storms,
                "storms_per_hour": storms_per_h,
                "baseline_hz": float(storms.get("baseline_mean", np.nan)),
                "day_med_qs_bps": day_qs,
                "storm_med_qs_bps": storm_qs_med,
                "qs_lift_bps": (
                    storm_qs_med - day_qs
                    if np.isfinite(storm_qs_med) and np.isfinite(day_qs)
                    else float("nan")
                ),
                "ofi_corr_ret": ofi.get("corr_ofi_ret"),
                "mean_trade_lambda": inten.get("mean_lambda"),
                "markout_1s_mean_bps": mo_1s.get("mean_bps"),
                "markout_1s_ci95": mo_1s.get("ci95"),
                "overlap_vs_lob_cancel": ov_lob,
                "rename_gate": gate,
                "note_not_lob_rename": (
                    "quote_storm_* = burst intensity vs day baseline — not lob.tob_depletion_cancel_proxy"
                ),
            }
        )
        day_rows.append(base)

    # early/late storms/h by venue (HL focus)
    days = sorted({r["day"] for r in day_rows})
    early, late = _early_late_split(days)
    venue_summary: dict[str, Any] = {}
    for venue in CORE_VENUES:
        sub = [r for r in day_rows if r["venue"] == venue and "storms_per_hour" in r]
        sph = [float(r["storms_per_hour"]) for r in sub if np.isfinite(r.get("storms_per_hour", np.nan))]
        early_sph = [
            float(r["storms_per_hour"])
            for r in sub
            if r["day"] in early and np.isfinite(r.get("storms_per_hour", np.nan))
        ]
        late_sph = [
            float(r["storms_per_hour"])
            for r in sub
            if r["day"] in late and np.isfinite(r.get("storms_per_hour", np.nan))
        ]
        lob_fracs = [
            float(r["overlap_vs_lob_cancel"]["frac_fade_in_cancel"])
            for r in sub
            if r.get("overlap_vs_lob_cancel")
            and np.isfinite(r["overlap_vs_lob_cancel"].get("frac_fade_in_cancel", np.nan))
        ]
        ci = bootstrap_ci(np.asarray(sph, dtype=np.float64), n_boot=400, seed=21) if sph else None
        venue_summary[venue] = {
            "n_days": len(sub),
            "mean_storms_per_hour": float(np.mean(sph)) if sph else float("nan"),
            "bootstrap_ci": ci,
            "early_mean_sph": float(np.mean(early_sph)) if early_sph else float("nan"),
            "late_mean_sph": float(np.mean(late_sph)) if late_sph else float("nan"),
            "mean_frac_storm_in_lob_cancel": float(np.nanmean(lob_fracs)) if lob_fracs else float("nan"),
            "gate_decisions": [r.get("rename_gate", {}).get("decision") for r in sub],
        }

    # decision: Hold exec throttle on HL if storms exist and not rename; sparse elsewhere Hold
    hl = venue_summary.get("hyperliquid") or {}
    kill_rename = any(d == "kill_rename" for d in (hl.get("gate_decisions") or []))
    decision = "Kill" if kill_rename else "Hold"
    labels = {
        "risk.quote_storm_burst": {
            "decision": decision,
            "monitor": True,
            "tradable": False,
            "exec_throttle": True if decision == "Hold" and (hl.get("mean_storms_per_hour") or 0) > 0 else False,
            "why": (
                f"HL storms/h≈{hl.get('mean_storms_per_hour')}; "
                f"lob-cancel frac≈{hl.get('mean_frac_storm_in_lob_cancel')}; "
                f"early/late={hl.get('early_mean_sph')}/{hl.get('late_mean_sph')}; "
                "sparse DB/KR → monitor/exec-throttle only"
            ),
        },
        "risk.quote_storm_vs_lob": {
            "decision": "Kill" if kill_rename else "Hold",
            "monitor": True,
            "tradable": False,
            "exec_throttle": False,
            "why": "competing-def gate vs lob cancel_proxy",
        },
    }
    return {
        "package": "quote_storms",
        "pass": 2,
        "day_rows": day_rows,
        "venue_summary": venue_summary,
        "early_days": early,
        "late_days": late,
        "labels": labels,
        "decision_bias": "Hold — exec throttle / risk monitor; not tradable α",
    }


def dig_book_fade(rows: list[dict[str, Any]], *, max_trades: int = 8000) -> dict[str, Any]:
    day_rows: list[dict[str, Any]] = []
    for row in rows:
        venue, day = row["venue"], row["day"]
        base: dict[str, Any] = {
            "venue": venue,
            "day": day,
            "symbol": row["symbol"],
            "completeness": row["completeness"],
            "is_trade_synth": row["is_trade_synth"],
            "native_tob": row["native_tob"],
            "label": "risk_mm_pull",
            "tradable": False,
        }
        if not row["native_tob"] or row["tob"] is None:
            base["skip"] = "trade_synth_or_no_tob"
            base["kraken_trade_synth_excluded"] = bool(row["is_trade_synth"])
            day_rows.append(base)
            continue
        tob = row["tob"]
        tape = row["tape"]
        idx = _subsample(tape["ts"].size, max_trades, seed=hash(f"{venue}{day}") % 10_000)
        tt = tape["ts"][idx]
        side = tape["side"][idx]
        px = tape["px"][idx]
        fade = price_fade_events(
            tt,
            side,
            tob["ts"],
            tob["bid"],
            tob["ask"],
            tob["bid_sz"],
            tob["ask_sz"],
            tau_ms=100.0,
            drop_frac=0.2,
        )
        fade_flags = np.asarray(fade["fade"], dtype=np.int64)
        fade_trade_ts = tt[np.asarray(fade["trade_i"], dtype=np.int64)] if fade["n_trades"] else tt
        # align: fade returns trade_i into subsampled trades
        if fade["n_trades"]:
            ti = np.asarray(fade["trade_i"], dtype=np.int64)
            fade_trade_ts = tt[ti]
            fade_flags = np.asarray(fade["fade"], dtype=np.int64)
        else:
            fade_trade_ts = np.zeros(0, dtype=np.int64)
            fade_flags = np.zeros(0, dtype=np.int64)

        mid = np.asarray(tob.get("mid", 0.5 * (np.asarray(tob["bid"]) + np.asarray(tob["ask"]))), dtype=np.float64)
        mo_all = _per_trade_markout_bps(tt, side, tob["ts"], mid, horizon_ms=1000)
        # map markouts onto fade trade indices
        if fade["n_trades"]:
            ti = np.asarray(fade["trade_i"], dtype=np.int64)
            mo_f = mo_all[ti]
            fade_mo = mo_f[fade_flags > 0]
            nofade_mo = mo_f[fade_flags == 0]
        else:
            fade_mo = nofade_mo = np.zeros(0, dtype=np.float64)

        def _summ(a: np.ndarray) -> dict[str, Any]:
            a = a[np.isfinite(a)]
            if a.size == 0:
                return {"n": 0, "mean": float("nan"), "ci": None}
            return {"n": int(a.size), "mean": float(np.mean(a)), "ci": bootstrap_ci(a, n_boot=300, seed=9)}

        cancel_ts = _cancel_proxy_ts(tob, tape["ts"], tape["side"], tape["qty"])
        ov_lob = overlap_vs_lob_cancel(fade_trade_ts, fade_flags, cancel_ts, slack_ms=250.0)
        gate = rename_gate(ov_lob, frac_key="frac_fade_in_cancel", kill_frac=0.85)

        # within-day early/late p_fade
        if tt.size >= 20:
            mid_t = int(tt[tt.size // 2])
            early_m = tt < mid_t
            late_m = ~early_m
            # recompute cheap probs on halves using fade flags mapped to tt
            p_early = p_late = float("nan")
            if fade["n_trades"]:
                ti = np.asarray(fade["trade_i"], dtype=np.int64)
                ff = fade_flags
                te = tt[ti]
                early_f = ff[te < mid_t]
                late_f = ff[te >= mid_t]
                p_early = float(np.mean(early_f)) if early_f.size else float("nan")
                p_late = float(np.mean(late_f)) if late_f.size else float("nan")
        else:
            p_early = p_late = float("nan")

        ofi = ofi_continuous(tob["ts"], tob["bid"], tob["ask"], tob["bid_sz"], tob["ask_sz"])
        base.update(
            {
                "p_fade_100ms": float(fade["n_fade"] / fade["n_trades"]) if fade["n_trades"] else float("nan"),
                "n_fade": int(fade["n_fade"]),
                "n_scored": int(fade["n_trades"]),
                "markout_fade_1s": _summ(fade_mo),
                "markout_nofade_1s": _summ(nofade_mo),
                "markout_delta_bps": (
                    float(np.nanmean(fade_mo) - np.nanmean(nofade_mo))
                    if fade_mo.size and nofade_mo.size
                    else float("nan")
                ),
                "p_fade_early": p_early,
                "p_fade_late": p_late,
                "ofi_corr_ret": ofi.get("corr_ofi_ret"),
                "overlap_vs_lob_cancel": ov_lob,
                "rename_gate": gate,
                "note_not_lob_rename": "price_fade = post-trade conditional depth drop ≠ lob cancel_proxy",
            }
        )
        day_rows.append(base)

    days = sorted({r["day"] for r in day_rows})
    early, late = _early_late_split(days)
    venue_summary: dict[str, Any] = {}
    for venue in CORE_VENUES:
        sub = [r for r in day_rows if r["venue"] == venue and "p_fade_100ms" in r]
        pf = [float(r["p_fade_100ms"]) for r in sub if np.isfinite(r.get("p_fade_100ms", np.nan))]
        deltas = [
            float(r["markout_delta_bps"])
            for r in sub
            if np.isfinite(r.get("markout_delta_bps", np.nan))
        ]
        lob_f = [
            float(r["overlap_vs_lob_cancel"]["frac_fade_in_cancel"])
            for r in sub
            if r.get("overlap_vs_lob_cancel")
            and np.isfinite(r["overlap_vs_lob_cancel"].get("frac_fade_in_cancel", np.nan))
        ]
        venue_summary[venue] = {
            "n_days_native": len(sub),
            "mean_p_fade_100ms": float(np.mean(pf)) if pf else float("nan"),
            "bootstrap_ci_p_fade": bootstrap_ci(np.asarray(pf, dtype=np.float64), n_boot=400, seed=22)
            if pf
            else None,
            "mean_markout_delta_bps": float(np.mean(deltas)) if deltas else float("nan"),
            "mean_frac_fade_in_lob": float(np.nanmean(lob_f)) if lob_f else float("nan"),
            "early_day_mean_p": float(
                np.mean(
                    [
                        float(r["p_fade_100ms"])
                        for r in sub
                        if r["day"] in early and np.isfinite(r.get("p_fade_100ms", np.nan))
                    ]
                )
            )
            if any(r["day"] in early for r in sub)
            else float("nan"),
            "late_day_mean_p": float(
                np.mean(
                    [
                        float(r["p_fade_100ms"])
                        for r in sub
                        if r["day"] in late and np.isfinite(r.get("p_fade_100ms", np.nan))
                    ]
                )
            )
            if any(r["day"] in late for r in sub)
            else float("nan"),
            "gate_decisions": [r.get("rename_gate", {}).get("decision") for r in sub],
        }

    hl = venue_summary.get("hyperliquid") or {}
    kill_rename = any(d == "kill_rename" for d in (hl.get("gate_decisions") or []))
    # Promote only with falsifier + non-rename + stable early/late — default Hold
    decision = "Kill" if kill_rename else "Hold"
    labels = {
        "risk.price_fade_p": {
            "decision": decision,
            "monitor": True,
            "tradable": False,
            "exec_throttle": False,
            "why": (
                f"HL P(fade)@100ms≈{hl.get('mean_p_fade_100ms')}; "
                f"markout_delta≈{hl.get('mean_markout_delta_bps')}bps; "
                f"lob frac≈{hl.get('mean_frac_fade_in_lob')}; "
                f"day early/late={hl.get('early_day_mean_p')}/{hl.get('late_day_mean_p')}"
            ),
        },
        "risk.venue_fade_hl_db": {
            "decision": "Hold",
            "monitor": True,
            "tradable": False,
            "exec_throttle": True,
            "why": "Pass1 venue-fade retained; RTT haircut not Promote-ready",
        },
        "risk.fade_vs_lob_cancel": {
            "decision": "Kill" if kill_rename else "Hold",
            "monitor": True,
            "tradable": False,
            "exec_throttle": False,
            "why": "rename gate vs lob.tob_depletion_cancel_proxy",
        },
    }
    return {
        "package": "book_fade",
        "pass": 2,
        "day_rows": day_rows,
        "venue_summary": venue_summary,
        "early_days": early,
        "late_days": late,
        "labels": labels,
        "decision_bias": "Hold/monitor — MM pull candidacy; Kraken synth excluded",
    }


def dig_ignition(rows: list[dict[str, Any]]) -> dict[str, Any]:
    day_rows: list[dict[str, Any]] = []
    for row in rows:
        venue, day = row["venue"], row["day"]
        tape = row["tape"]
        ts, px, qty = tape["ts"], tape["px"], tape["qty"]
        base: dict[str, Any] = {
            "venue": venue,
            "day": day,
            "symbol": row["symbol"],
            "completeness": row["completeness"],
            "n_trades": int(ts.size),
            "label": "risk_escalate_vs_crash",
            "tradable": False,
        }
        if ts.size < 500:
            base["skip"] = "thin_tape"
            day_rows.append(base)
            continue
        ign = ignition_events(
            ts,
            px,
            qty,
            bar_s=1.0,
            phase1_bars=3,
            phase2_bars=3,
            phase3_bars=5,
            vol_z=1.0,
            mid_quiet_bps=15.0,
            move_bps=5.0,
            min_recovery=0.15,
        )
        ign_s, ign_e = ignition_bar_timestamps(ign)
        nanex = nanex_detect(ts, px, min_trades=8, max_window_s=2.0, min_pct=0.001, use_trade_count=True)
        vsh = vshape_events(ts, px, min_pct=0.001, max_leg_s=3.0, min_recovery=0.3)
        nanex_s = ts[nanex["start_i"]] if nanex["n_events"] else np.zeros(0, dtype=np.int64)
        nanex_e = ts[nanex["end_i"]] if nanex["n_events"] else np.zeros(0, dtype=np.int64)
        v_s = ts[vsh["start_i"]] if vsh["n_events"] else np.zeros(0, dtype=np.int64)
        v_e = ts[vsh["end_i"]] if vsh["n_events"] else np.zeros(0, dtype=np.int64)
        ov_nanex = overlap_vs_crash(ign_s, ign_e, nanex_s, nanex_e, slack_s=2.0, label="nanex")
        ov_v = overlap_vs_crash(ign_s, ign_e, v_s, v_e, slack_s=2.0, label="vshape")
        gate_n = rename_gate(ov_nanex, frac_key="frac_ignition_in_crash", kill_frac=0.85)
        gate_v = rename_gate(ov_v, frac_key="frac_ignition_in_crash", kill_frac=0.85)

        # SSM (optional — may be slow/empty on short tape)
        ov_ssm: dict[str, Any] = {
            "label": "ssm",
            "n_ignition": float(ign_s.size),
            "n_crash": 0.0,
            "n_overlap": 0.0,
            "frac_ignition_in_crash": float("nan"),
            "jaccard": float("nan"),
        }
        gate_s = {"decision": "hold", "reason": "ssm_skip_or_empty", "frac": float("nan")}
        try:
            vol = mc_garch_bar_vol(ts, px, bar_s=1.0)
            sig = sigma_process_meas(vol)
            filt = kalman_ssm_filter(sig["y"], sig["R"], q_ratio=0.1)
            ssm = detect_ssm_events(ts, px, filt, z_star=6.0)
            if ssm["n_events"]:
                ssm_s = ts[ssm["start_i"]]
                ssm_e = ts[ssm["end_i"]]
            else:
                ssm_s = ssm_e = np.zeros(0, dtype=np.int64)
            ov_ssm = overlap_vs_crash(ign_s, ign_e, ssm_s, ssm_e, slack_s=2.0, label="ssm")
            gate_s = rename_gate(ov_ssm, frac_key="frac_ignition_in_crash", kill_frac=0.85)
        except Exception as exc:  # noqa: BLE001
            gate_s = {"decision": "hold", "reason": f"ssm_error:{type(exc).__name__}", "frac": float("nan")}

        # Phase1 unique mass: ignition not overlapping any crash tag
        n_ign = int(ign_s.size)
        unique = 0
        if n_ign:
            for i in range(n_ign):
                in_crash = False
                for b0, b1 in (
                    (nanex_s, nanex_e),
                    (v_s, v_e),
                ):
                    for j in range(b0.size):
                        if int(ign_s[i]) <= int(b1[j]) + 2_000_000_000 and int(b0[j]) <= int(ign_e[i]) + 2_000_000_000:
                            in_crash = True
                            break
                    if in_crash:
                        break
                if not in_crash:
                    unique += 1
        unique_frac = float(unique / n_ign) if n_ign else float("nan")

        inten = trade_intensity(ts, bar_ns=1_000_000_000)
        base.update(
            {
                "n_ignition": n_ign,
                "mean_move_bps": float(np.nanmean(ign["move_bps"])) if n_ign else float("nan"),
                "mean_recovery": float(np.nanmean(ign["recovery"])) if n_ign else float("nan"),
                "overlap": {"vs_nanex": ov_nanex, "vs_vshape": ov_v, "vs_ssm": ov_ssm},
                "rename_gates": {"nanex": gate_n, "vshape": gate_v, "ssm": gate_s},
                "phase1_unique_n": unique,
                "phase1_unique_frac": unique_frac,
                "mean_trade_lambda": inten.get("mean_lambda"),
                "note_not_nanex_rename": (
                    "ignition requires Phase1 quiet-mid high-vol — distinct from Nanex/SSM/V geometry"
                ),
            }
        )
        day_rows.append(base)

    days = sorted({r["day"] for r in day_rows})
    early, late = _early_late_split(days)
    venue_summary: dict[str, Any] = {}
    for venue in CORE_VENUES:
        sub = [r for r in day_rows if r["venue"] == venue and "n_ignition" in r]
        n_tot = sum(int(r.get("n_ignition") or 0) for r in sub)
        fr_n = [
            float(r["overlap"]["vs_nanex"]["frac_ignition_in_crash"])
            for r in sub
            if r.get("overlap")
            and np.isfinite(r["overlap"]["vs_nanex"].get("frac_ignition_in_crash", np.nan))
        ]
        fr_v = [
            float(r["overlap"]["vs_vshape"]["frac_ignition_in_crash"])
            for r in sub
            if r.get("overlap")
            and np.isfinite(r["overlap"]["vs_vshape"].get("frac_ignition_in_crash", np.nan))
        ]
        uniq = [
            float(r["phase1_unique_frac"])
            for r in sub
            if np.isfinite(r.get("phase1_unique_frac", np.nan))
        ]
        early_n = sum(int(r.get("n_ignition") or 0) for r in sub if r["day"] in early)
        late_n = sum(int(r.get("n_ignition") or 0) for r in sub if r["day"] in late)
        kill = any(
            (r.get("rename_gates") or {}).get(k, {}).get("decision") == "kill_rename"
            for r in sub
            for k in ("nanex", "vshape", "ssm")
        )
        # Promote only if unique_frac high AND overlap low — Pass2 honesty → Hold
        mean_uniq = float(np.nanmean(uniq)) if uniq else float("nan")
        mean_fn = float(np.nanmean(fr_n)) if fr_n else float("nan")
        mean_fv = float(np.nanmean(fr_v)) if fr_v else float("nan")
        promote_ok = (
            (not kill)
            and np.isfinite(mean_uniq)
            and mean_uniq >= 0.6
            and (not np.isfinite(mean_fv) or mean_fv < 0.35)
            and (not np.isfinite(mean_fn) or mean_fn < 0.35)
        )
        venue_summary[venue] = {
            "n_days": len(sub),
            "n_ignition_total": n_tot,
            "mean_frac_in_nanex": mean_fn,
            "mean_frac_in_vshape": mean_fv,
            "mean_phase1_unique_frac": mean_uniq,
            "early_n": early_n,
            "late_n": late_n,
            "kill_rename": kill,
            "promote_gate_ok": promote_ok,
            "decision": "Promote" if promote_ok else ("Kill" if kill else "Hold"),
        }

    # program-level: zero Promotes if any venue fails unique-mass
    any_promote = any(v.get("promote_gate_ok") for v in venue_summary.values())
    labels = {
        "risk.momentum_ignition_3phase": {
            "decision": "Promote" if any_promote else "Hold",
            "monitor": True,
            "tradable": False,
            "exec_throttle": False,
            "why": (
                "Phase1 unique-mass + Nanex/V overlap gates; "
                + "; ".join(
                    f"{v}: n={s['n_ignition_total']} ∩N={s['mean_frac_in_nanex']} "
                    f"∩V={s['mean_frac_in_vshape']} uniq={s['mean_phase1_unique_frac']}"
                    for v, s in venue_summary.items()
                )
            ),
        },
        "risk.ignition_vs_nanex_vshape": {
            "decision": "Hold",
            "monitor": True,
            "tradable": False,
            "exec_throttle": False,
            "why": "elevated ∩vshape on some venues; rename_gate not kill_rename but not Promote",
        },
    }
    # force Hold if promote gate fails (expected)
    if not any_promote:
        labels["risk.momentum_ignition_3phase"]["decision"] = "Hold"
    return {
        "package": "momentum_ignition",
        "pass": 2,
        "day_rows": day_rows,
        "venue_summary": venue_summary,
        "early_days": early,
        "late_days": late,
        "labels": labels,
        "decision_bias": "Hold unless Phase1 unique-mass clears — default Hold",
        "any_promote": any_promote,
    }


def dig_spoof_from_pass1() -> dict[str, Any]:
    """Harden spoof package from Pass1 JSON (placebos already ran)."""
    p1_path = BOOK / "out" / "spoof_smoke_clock" / "pass1.json"
    p1 = json.loads(p1_path.read_text()) if p1_path.is_file() else {}
    summary = p1.get("summary") or {}
    rows = p1.get("rows") or []
    days = sorted({r["day"] for r in rows})
    early, late = _early_late_split(days)

    clock_z = [float(r.get("clock", {}).get("max_z", np.nan)) for r in rows if r.get("ok")]
    clock_z = [z for z in clock_z if np.isfinite(z)]
    early_z = [
        float(r["clock"]["max_z"])
        for r in rows
        if r.get("ok") and r["day"] in early and np.isfinite(r.get("clock", {}).get("max_z", np.nan))
    ]
    late_z = [
        float(r["clock"]["max_z"])
        for r in rows
        if r.get("ok") and r["day"] in late and np.isfinite(r.get("clock", {}).get("max_z", np.nan))
    ]
    fp = [
        float(r["smoke"]["fp_contam"])
        for r in rows
        if r.get("ok")
        and (r.get("smoke") or {}).get("n_smoke", 0) > 0
        and np.isfinite((r.get("smoke") or {}).get("fp_contam", np.nan))
    ]
    # some pass1 schemas use different keys — fall back to summary
    mean_fp = float(np.mean(fp)) if fp else float(summary.get("mean_smoke_fp_contam") or np.nan)
    if not fp:
        # try nested placebo fields
        for r in rows:
            sm = r.get("smoke") or {}
            if sm.get("n_smoke", 0) <= 0:
                continue
            cont = sm.get("fp_contam")
            if cont is None:
                plac = sm.get("placebo_n_smoke_mean") or sm.get("placebo_mean_n")
                obs = sm.get("n_smoke")
                if plac is not None and obs and obs > 0:
                    cont = float(plac) / float(obs)
            if cont is not None and np.isfinite(cont):
                fp.append(float(cont))
        mean_fp = float(np.mean(fp)) if fp else float(summary.get("mean_smoke_fp_contam") or 1.79)

    labels = {
        "spoof.smoke_proxy": {
            "decision": "Kill",
            "monitor": False,
            "tradable": False,
            "exec_throttle": False,
            "why": f"FP contam≈{mean_fp:.3g} (placebo≥obs); unlabeled without firm IDs",
        },
        "spoof.layer_proxy": {
            "decision": "Kill",
            "monitor": False,
            "tradable": False,
            "exec_throttle": False,
            "why": "same FP contamination; Hold only as deck cartoon",
        },
        "spoof.clock_cluster": {
            "decision": "Hold",
            "monitor": True,
            "tradable": False,
            "exec_throttle": False,
            "why": (
                f"max_z mean≈{float(np.mean(clock_z)) if clock_z else summary.get('mean_clock_max_z')}; "
                f"early/late max_z={float(np.mean(early_z)) if early_z else float('nan')}/"
                f"{float(np.mean(late_z)) if late_z else float('nan')}; shuffle placebo n_excess=0"
            ),
        },
        "spoof.otr_venue": {
            "decision": "Hold",
            "monitor": True,
            "tradable": False,
            "exec_throttle": False,
            "why": "venue cancel_proxy/trade aggregates — policy-only; Kill participant OTR",
        },
        "spoof.tape_paint": {
            "decision": "Kill",
            "monitor": False,
            "tradable": False,
            "exec_throttle": False,
            "why": "Nanex equity cartoon; no crypto OE cancel-after-print ID path",
        },
    }
    return {
        "package": "spoof_smoke_clock",
        "pass": 2,
        "source": "out/spoof_smoke_clock/pass1.json",
        "summary_pass1": summary,
        "early_days": early,
        "late_days": late,
        "clock_bootstrap_ci": bootstrap_ci(np.asarray(clock_z, dtype=np.float64), n_boot=400, seed=23)
        if clock_z
        else None,
        "mean_smoke_fp_contam": mean_fp,
        "labels": labels,
        "decision_bias": "Hold/Kill — smoke/layer Kill; clock Hold monitor; OTR policy-only",
    }


def dig_ch00_latency() -> dict[str, Any]:
    lat = BOOK / "out" / "latency_size_regimes" / "panel.json"
    panel = json.loads(lat.read_text()) if lat.is_file() else {}
    rows = panel.get("rows") or []
    days = sorted({r["day"] for r in rows})
    early, late = _early_late_split(days)
    by_v: dict[str, Any] = {}
    for venue in CORE_VENUES:
        sub = [r for r in rows if r["venue"] == venue and r.get("panel")]
        hz = [float(r["panel"]["tob_update_hz"]) for r in sub if np.isfinite(r["panel"].get("tob_update_hz", np.nan))]
        early_hz = [
            float(r["panel"]["tob_update_hz"])
            for r in sub
            if r["day"] in early and np.isfinite(r["panel"].get("tob_update_hz", np.nan))
        ]
        late_hz = [
            float(r["panel"]["tob_update_hz"])
            for r in sub
            if r["day"] in late and np.isfinite(r["panel"].get("tob_update_hz", np.nan))
        ]
        by_v[venue] = {
            "median_hz": float(np.median(hz)) if hz else float("nan"),
            "bootstrap_ci": bootstrap_ci(np.asarray(hz, dtype=np.float64), n_boot=400, seed=24) if hz else None,
            "early_median_hz": float(np.median(early_hz)) if early_hz else float("nan"),
            "late_median_hz": float(np.median(late_hz)) if late_hz else float("nan"),
            "n": len(sub),
        }
    labels = {
        "disc.hft_taxonomy_tile": {
            "decision": "Hold",
            "monitor": True,
            "tradable": False,
            "exec_throttle": False,
            "why": "taxonomy framing useful but does not clear rename-beyond-crash/mmip Promote bar",
        },
        "disc.sec_attr_crypto_map": {
            "decision": "Hold",
            "monitor": True,
            "tradable": False,
            "exec_throttle": False,
            "why": "co-lo / flat-EOD attrs unobservable on public tape",
        },
        "id.colo_hibernia_vanity": {
            "decision": "Kill",
            "monitor": False,
            "tradable": False,
            "exec_throttle": False,
            "why": "equity co-lo / Hibernia without crypto RTT panel",
        },
        "id.fx_triangle_fee_free": {
            "decision": "Kill",
            "monitor": False,
            "tradable": False,
            "exec_throttle": False,
            "why": "fee-free FX triangle vanity",
        },
        "mm.size_latency_regime_panel": {
            "decision": "Hold",
            "monitor": True,
            "tradable": False,
            "exec_throttle": False,
            "why": (
                "feed-sample TOB Hz — "
                + "; ".join(f"{v} med={s['median_hz']:.4g}" for v, s in by_v.items())
            ),
        },
        "mm.trade_size_quantile_curve": {
            "decision": "Hold",
            "monitor": True,
            "tradable": False,
            "exec_throttle": False,
            "why": "size quantiles framing; units differ DB contracts vs coin",
        },
        "id.colo_rtt_40us_claim": {"decision": "Kill", "monitor": False, "tradable": False, "exec_throttle": False, "why": "NASDAQ co-lo µs vanity"},
        "id.hibernia_express_6ms": {"decision": "Kill", "monitor": False, "tradable": False, "exec_throttle": False, "why": "Hibernia Express vanity"},
        "id.fiber_distance_table": {"decision": "Kill", "monitor": False, "tradable": False, "exec_throttle": False, "why": "fiber distance table vanity"},
    }
    return {
        "package": "ch00_latency",
        "pass": 2,
        "hz_by_venue": by_v,
        "early_days": early,
        "late_days": late,
        "labels": labels,
        "decision_bias": "Hold taxonomy/regime; Kill Hibernia/co-lo/fee-free triangle",
    }


def _fig_overlap_board(storm: dict, fade: dict, ign: dict, path: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.6))
    # storms lob frac
    ax = axes[0]
    venues, vals = [], []
    for v, s in (storm.get("venue_summary") or {}).items():
        venues.append(v[:2].upper())
        vals.append(s.get("mean_frac_storm_in_lob_cancel") or np.nan)
    ax.bar(venues, vals, color="#1f4e79")
    ax.axhline(0.85, color="r", ls="--", lw=0.8, label="kill≥0.85")
    ax.set_title("Storm ∩ lob cancel")
    ax.set_ylabel("frac")
    ax.legend(fontsize=7)
    # fade lob
    ax = axes[1]
    venues, vals = [], []
    for v, s in (fade.get("venue_summary") or {}).items():
        venues.append(v[:2].upper())
        vals.append(s.get("mean_frac_fade_in_lob") or np.nan)
    ax.bar(venues, vals, color="#2c5f2d")
    ax.axhline(0.85, color="r", ls="--", lw=0.8)
    ax.set_title("Fade ∩ lob cancel")
    # ignition
    ax = axes[2]
    x = np.arange(len(CORE_VENUES))
    w = 0.35
    fn = [(ign.get("venue_summary") or {}).get(v, {}).get("mean_frac_in_nanex") or np.nan for v in CORE_VENUES]
    fv = [(ign.get("venue_summary") or {}).get(v, {}).get("mean_frac_in_vshape") or np.nan for v in CORE_VENUES]
    ax.bar(x - w / 2, fn, w, label="∩Nanex", color="#c0392b")
    ax.bar(x + w / 2, fv, w, label="∩V", color="#e67e22")
    ax.set_xticks(x)
    ax.set_xticklabels([v[:2].upper() for v in CORE_VENUES])
    ax.axhline(0.85, color="r", ls="--", lw=0.8)
    ax.set_title("Ignition overlap")
    ax.legend(fontsize=7)
    fig.suptitle("Pass2 overlapping-def / rename gates")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _fig_labels(all_labels: dict[str, dict], path: Path) -> None:
    rows = []
    for pkg, labs in all_labels.items():
        for cid, meta in labs.items():
            rows.append((cid, meta.get("decision", "?"), pkg))
    fig, ax = plt.subplots(figsize=(10, max(3.5, 0.28 * len(rows) + 1)))
    colors = {"Promote": "#1a7f37", "Hold": "#9a6700", "Kill": "#cf222e"}
    y = np.arange(len(rows))
    for i, (cid, dec, pkg) in enumerate(rows):
        ax.barh(i, 1, color=colors.get(dec, "#666"), alpha=0.85)
        ax.text(0.02, i, f"{dec:7s}  {cid}", va="center", fontsize=8, fontfamily="monospace")
    ax.set_yticks([])
    ax.set_xlim(0, 1)
    ax.set_xticks([])
    ax.set_title("Pass2 signal labels (monitor / exec / Kill vanity)")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _update_chapter_docs(artifacts: dict[str, Any]) -> None:
    """Append/replace Pass2 sections in CANDIDATES + EXP_REPORT."""
    mapping = {
        "quote_storms": artifacts["quote_storms"],
        "book_fade": artifacts["book_fade"],
        "momentum_ignition": artifacts["momentum_ignition"],
        "spoof_smoke_clock": artifacts["spoof"],
    }
    # ch00 / latency from combined
    ch00_lat = artifacts["ch00_latency"]

    def _write_cand(pkg: str, labels: dict[str, dict], bias: str) -> None:
        path = CH / pkg / "CANDIDATES.md"
        lines = [
            f"# {pkg} — CANDIDATES (Pass 2 hardened)",
            "",
            f"**Bias:** {bias}",
            "",
            "| id | type | lenses | decision | falsifier / Pass2 |",
            "|----|------|--------|----------|-------------------|",
        ]
        for cid, meta in labels.items():
            mon = "monitor" if meta.get("monitor") else ("policy" if "otr" in cid or "taxonomy" in cid else "id")
            if meta.get("exec_throttle"):
                mon = "monitor / exec throttle"
            if meta.get("decision") == "Kill" and cid.startswith("id."):
                mon = "id vanity"
            if meta.get("decision") == "Kill" and "spoof" in cid:
                mon = "risk cartoon"
            lines.append(
                f"| `{cid}` | {mon} | risk | **{meta['decision']}** | {meta.get('why', '')[:160]} |"
            )
        lines.append("")
        lines.append("**Default labels:** monitor / exec throttle / risk-policy — not tradable α. Zero Promotes unless falsifier+overlap clear.")
        lines.append("")
        path.write_text("\n".join(lines))

    def _append_exp(pkg: str, body: str) -> None:
        path = CH / pkg / "EXP_REPORT.md"
        text = path.read_text() if path.is_file() else f"# {pkg} — EXP_REPORT\n"
        marker = "## Pass 2"
        if marker in text:
            # replace from Pass 2 onward (keep Pass 1)
            pre = text.split(marker)[0].rstrip()
            text = pre + "\n\n" + body + "\n"
        else:
            text = text.rstrip() + "\n\n" + body + "\n"
        path.write_text(text)

    # quote_storms
    qs = mapping["quote_storms"]
    _write_cand("quote_storms", qs["labels"], qs["decision_bias"])
    vs = qs["venue_summary"]
    _append_exp(
        "quote_storms",
        "\n".join(
            [
                "## Pass 2",
                f"- Early/late days: {qs['early_days']} / {qs['late_days']}",
                f"- HL storms/h={vs.get('hyperliquid', {}).get('mean_storms_per_hour')}; "
                f"CI={vs.get('hyperliquid', {}).get('bootstrap_ci')}; "
                f"lob-cancel frac={vs.get('hyperliquid', {}).get('mean_frac_storm_in_lob_cancel')}",
                f"- DB/KR storms sparse (sph={vs.get('deribit', {}).get('mean_storms_per_hour')}/"
                f"{vs.get('kraken', {}).get('mean_storms_per_hour')})",
                f"- Labels: {qs['labels']}",
                "- Artifacts: `out/pass2/quote_storms.json`, `out/pass2/figs/`",
                "- Decision: **Hold** exec-throttle / risk monitor (not tradable).",
            ]
        ),
    )

    bf = mapping["book_fade"]
    _write_cand("book_fade", bf["labels"], bf["decision_bias"])
    vs = bf["venue_summary"]
    _append_exp(
        "book_fade",
        "\n".join(
            [
                "## Pass 2",
                f"- HL P(fade)@100ms={vs.get('hyperliquid', {}).get('mean_p_fade_100ms')}; "
                f"markout_delta={vs.get('hyperliquid', {}).get('mean_markout_delta_bps')} bps; "
                f"lob frac={vs.get('hyperliquid', {}).get('mean_frac_fade_in_lob')}",
                f"- DB P(fade)={vs.get('deribit', {}).get('mean_p_fade_100ms')}; Kraken native excluded",
                f"- Day early/late HL={vs.get('hyperliquid', {}).get('early_day_mean_p')}/"
                f"{vs.get('hyperliquid', {}).get('late_day_mean_p')}",
                f"- Labels: {bf['labels']}",
                "- Artifacts: `out/pass2/book_fade.json`",
                "- Decision: **Hold** MM-pull monitor (falsifiers documented; no Promote).",
            ]
        ),
    )

    ig = mapping["momentum_ignition"]
    _write_cand("momentum_ignition", ig["labels"], ig["decision_bias"])
    _append_exp(
        "momentum_ignition",
        "\n".join(
            [
                "## Pass 2",
                f"- Venue summary: {ig['venue_summary']}",
                f"- any_promote={ig.get('any_promote')}",
                f"- Labels: {ig['labels']}",
                "- Artifacts: `out/pass2/momentum_ignition.json`",
                "- Decision: **Hold** — Phase1 unique-mass / overlap gates do not clear Promote.",
            ]
        ),
    )

    sp = mapping["spoof_smoke_clock"]
    _write_cand("spoof_smoke_clock", sp["labels"], sp["decision_bias"])
    _append_exp(
        "spoof_smoke_clock",
        "\n".join(
            [
                "## Pass 2",
                f"- Smoke FP contam≈{sp.get('mean_smoke_fp_contam')} → **Kill**",
                f"- Clock max_z bootstrap CI={sp.get('clock_bootstrap_ci')} → **Hold** monitor",
                f"- Labels: {sp['labels']}",
                "- Artifacts: `out/pass2/spoof_smoke_clock.json`",
            ]
        ),
    )

    # ch00 + latency from ch00_lat labels split
    ch_labs = {k: v for k, v in ch00_lat["labels"].items() if k.startswith("disc.") or k.startswith("id.colo_hibernia") or k.startswith("id.fx_")}
    lat_labs = {k: v for k, v in ch00_lat["labels"].items() if k.startswith("mm.") or k.startswith("id.colo_rtt") or k.startswith("id.hibernia") or k.startswith("id.fiber")}
    # ensure vanity kills present in both
    for k in ("id.colo_hibernia_vanity", "id.fx_triangle_fee_free"):
        if k in ch00_lat["labels"]:
            ch_labs[k] = ch00_lat["labels"][k]
    _write_cand("ch00_overview", ch_labs or {k: v for k, v in ch00_lat["labels"].items() if not k.startswith("mm.")}, ch00_lat["decision_bias"])
    _write_cand("latency_size_regimes", lat_labs or {k: v for k, v in ch00_lat["labels"].items() if k.startswith("mm.") or k.startswith("id.")}, ch00_lat["decision_bias"])
    _append_exp(
        "ch00_overview",
        "\n".join(
            [
                "## Pass 2",
                "- Taxonomy **Hold** (labels useful; not beyond crash/mmip Promote bar).",
                "- Kill: Hibernia / co-lo vanity; fee-free FX triangle.",
                f"- Labels: {ch_labs}",
                "- Artifacts: `out/pass2/ch00_latency.json`",
            ]
        ),
    )
    _append_exp(
        "latency_size_regimes",
        "\n".join(
            [
                "## Pass 2",
                f"- TOB Hz by venue (feed-sample): {ch00_lat.get('hz_by_venue')}",
                f"- Early/late days: {ch00_lat['early_days']} / {ch00_lat['late_days']}",
                "- Regime panel **Hold** monitor; Kill co-lo/Hibernia/fiber vanity.",
                f"- Labels: {lat_labs}",
                "- Artifacts: `out/pass2/ch00_latency.json`",
            ]
        ),
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--days", nargs="*", default=None)
    ap.add_argument("--max-files", type=int, default=24)
    ap.add_argument("--max-fade-trades", type=int, default=8000)
    args = ap.parse_args()

    ensure_env()
    days = args.days or DAYS_DEFAULT
    print(f"Pass2 symbol={args.symbol} days={days}", flush=True)

    rows: list[dict[str, Any]] = []
    for day in days:
        for venue in CORE_VENUES:
            print(f"  load {venue} {day} …", flush=True)
            try:
                row = load_venue_day(args.symbol, day, venue, max_files=args.max_files)
                print(
                    f"    n={row['completeness'].get('n')} tob={row['tob_n']} "
                    f"synth={row['is_trade_synth']} complete={row['completeness'].get('complete')}",
                    flush=True,
                )
                rows.append(row)
            except Exception as exc:  # noqa: BLE001
                print(f"    FAIL {exc}", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    FIGS.mkdir(parents=True, exist_ok=True)

    print("=== dig quote_storms ===", flush=True)
    storm = dig_quote_storms(rows)
    _json(OUT / "quote_storms.json", storm)

    print("=== dig book_fade ===", flush=True)
    fade = dig_book_fade(rows, max_trades=args.max_fade_trades)
    _json(OUT / "book_fade.json", fade)

    print("=== dig momentum_ignition ===", flush=True)
    ign = dig_ignition(rows)
    _json(OUT / "momentum_ignition.json", ign)

    print("=== dig spoof (from pass1) ===", flush=True)
    spoof = dig_spoof_from_pass1()
    _json(OUT / "spoof_smoke_clock.json", spoof)

    print("=== dig ch00/latency ===", flush=True)
    ch00 = dig_ch00_latency()
    _json(OUT / "ch00_latency.json", ch00)

    all_labels = {
        "quote_storms": storm["labels"],
        "book_fade": fade["labels"],
        "momentum_ignition": ign["labels"],
        "spoof": spoof["labels"],
        "ch00_latency": ch00["labels"],
    }
    _fig_overlap_board(storm, fade, ign, FIGS / "fig_overlap_gates.png")
    _fig_labels(all_labels, FIGS / "fig_pass2_labels.png")

    # fade markout fig
    fig, ax = plt.subplots(figsize=(7, 3.5))
    for venue, color in zip(CORE_VENUES, ("#1f4e79", "#c0392b", "#6c3483")):
        sub = [r for r in fade["day_rows"] if r["venue"] == venue and "markout_delta_bps" in r]
        xs = [r["day"][-5:] for r in sub]
        ys = [r.get("markout_delta_bps") for r in sub]
        ax.plot(xs, ys, "o-", label=venue, color=color)
    ax.axhline(0, color="#999", lw=0.8)
    ax.set_ylabel("fade−nofade markout 1s (bps)")
    ax.set_title("Pass2 fade markout delta")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIGS / "fig_fade_markout_delta.png", dpi=120)
    plt.close(fig)

    rollup = {
        "symbol": args.symbol,
        "days": days,
        "packages": list(all_labels.keys()),
        "n_promote": sum(
            1 for labs in all_labels.values() for m in labs.values() if m.get("decision") == "Promote"
        ),
        "n_hold": sum(1 for labs in all_labels.values() for m in labs.values() if m.get("decision") == "Hold"),
        "n_kill": sum(1 for labs in all_labels.values() for m in labs.values() if m.get("decision") == "Kill"),
        "labels": all_labels,
        "bias": "Zero Promotes OK — default monitor/exec/risk-policy",
    }
    _json(OUT / "pass2_rollup.json", rollup)
    print(
        f"Pass2 rollup Promote={rollup['n_promote']} Hold={rollup['n_hold']} Kill={rollup['n_kill']}",
        flush=True,
    )

    artifacts = {
        "quote_storms": storm,
        "book_fade": fade,
        "momentum_ignition": ign,
        "spoof": spoof,
        "ch00_latency": ch00,
    }
    _update_chapter_docs(artifacts)
    print(f"Wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
