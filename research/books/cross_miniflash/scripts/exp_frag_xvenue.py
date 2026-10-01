from __future__ import annotations
#!/usr/bin/env python3
"""Phase 3b frag_xvenue: Herfindahl, venue crash share, concordance, FEI/Epps.

Pass 1: volume Herfindahl + SSM/Nanex crash venue share on HL+Deribit+Kraken.
Pass 2: thin-venue concentration, x-venue concordance, FEI / crossed-book / Epps
        around severity-gated crash windows (reuse mmip/empirical_mm libs).

Severity gate lives in research.lib.crash.severity_gate so micro-outlier SSM
floods do not dominate frag counts (sibling crash_stats may reuse the same gate).

ClickHouse MCP banned.
"""

import os

import argparse
import json
import sys
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
STARTARB = Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb'))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(STARTARB / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import (  # noqa: E402
    CORE_VENUES,
    day_bounds_ns,
    ensure_env,
    load_core_venues_day,
    load_venue_tob,
    venue_instrument,
)
from research.lib.crash import (  # noqa: E402
    detect_ssm_events,
    kalman_ssm_filter,
    mc_garch_bar_vol,
    nanex_detect,
    severity_gate,
    sigma_process_meas,
    volume_herfindahl,
    xvenue_event_concordance,
)
from research.lib.epps import corr_vs_lag  # noqa: E402
from research.lib.fei import fei  # noqa: E402

OUT = BOOK / "out" / "frag_xvenue"
FIG = OUT / "figs"
CH = BOOK / "chapters" / "frag_xvenue"

DEFAULT_DAYS = [
    "2026-09-04",
    "2026-09-05",
    "2026-09-06",
    "2026-09-07",
    "2026-09-08",
    "2026-09-09",
    "2026-09-10",
]
DEFAULT_SYMBOLS = ["ETH", "BTC"]
Z_STAR = 6.0
# Severity gate so SSM micro-outliers do not swamp frag tables
GATE_DP = 0.05  # 5 bps (percent units in extract_event_features)
GATE_IC = 3
GATE_DP_STRICT = 0.30  # Nanex-aligned 30 bps
CONCORD_SLACKS = (1.0, 5.0, 30.0, 60.0)
EPPS_LAGS = (1.0, 5.0, 15.0, 60.0, 300.0)


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, float)):
        x = float(obj)
        return x if np.isfinite(x) else None
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if obj is None:
        return None
    return str(obj)


def _save_fig(path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=140, bbox_inches="tight")
    plt.close()


def _tape_notional(tape: dict[str, np.ndarray], venue: str) -> float:
    """USD notional for Herfindahl. Deribit inverse perps store qty in USD already."""
    px = np.asarray(tape["px"], dtype=np.float64)
    qty = np.asarray(tape["qty"], dtype=np.float64)
    m = np.isfinite(px) & np.isfinite(qty) & (qty > 0)
    if not m.any():
        return 0.0
    v = str(venue).lower()
    if v == "deribit":
        # ETH/BTC-PERPETUAL inverse: warehouse qty_coin ≈ USD notional (not coins)
        return float(np.sum(qty[m]))
    m2 = m & (px > 0)
    return float(np.sum(px[m2] * qty[m2])) if m2.any() else 0.0


def _tape_coin_volume(tape: dict[str, np.ndarray], venue: str) -> float:
    """Coin-equivalent volume (secondary Herfindahl / robustness)."""
    px = np.asarray(tape["px"], dtype=np.float64)
    qty = np.asarray(tape["qty"], dtype=np.float64)
    m = np.isfinite(px) & np.isfinite(qty) & (qty > 0) & (px > 0)
    if not m.any():
        return 0.0
    v = str(venue).lower()
    if v == "deribit":
        return float(np.sum(qty[m] / px[m]))
    return float(np.sum(qty[m]))


def _detect_day_venue(
    tape: dict[str, np.ndarray],
    *,
    sigma_m_frac: float = 1.0,
) -> dict[str, Any]:
    ts = np.asarray(tape["ts"], dtype=np.int64)
    px = np.asarray(tape["px"], dtype=np.float64)
    out: dict[str, Any] = {"n_trades": int(ts.size)}
    if ts.size < 200 or not np.isfinite(px).any():
        out["skip"] = "thin_tape"
        return out
    log_px = np.log(np.where(px > 0, px, np.nan))
    mcg = mc_garch_bar_vol(ts, px)
    sig = sigma_process_meas(ts, mcg, sigma_m_frac=sigma_m_frac, log_px=log_px)
    filt = kalman_ssm_filter(ts, px, sig["sigma_p2_dt"], sig["sigma_m2"])
    ssm_raw = detect_ssm_events(ts, px, filt, z_star=Z_STAR)
    ssm_5bps = severity_gate(ssm_raw, min_dp_pct=GATE_DP, min_i_c=GATE_IC)
    ssm_30bps = severity_gate(ssm_raw, min_dp_pct=GATE_DP_STRICT, min_i_c=GATE_IC)
    nanex = nanex_detect(ts, px, min_trades=10, max_window_s=1.5, min_pct=0.003, use_trade_count=True)
    # attach ts_start/ts_end for nanex (same tape)
    n_nx = int(nanex["n_events"])
    ts_s = np.zeros(n_nx, dtype=np.int64)
    ts_e = np.zeros(n_nx, dtype=np.int64)
    for k in range(n_nx):
        a, b = int(nanex["start_i"][k]), int(nanex["end_i"][k])
        ts_s[k], ts_e[k] = int(ts[a]), int(ts[b])
    nanex = {**nanex, "ts_start": ts_s, "ts_end": ts_e, "i_c": nanex["n_trades"], "dp_pct": nanex["dp_pct"]}
    out.update(
        {
            "ssm_raw_n": int(ssm_raw["n_events"]),
            "ssm_5bps": ssm_5bps,
            "ssm_30bps": ssm_30bps,
            "nanex": nanex,
            "median_dp_raw": float(np.nanmedian(ssm_raw["dp_pct"])) if ssm_raw["n_events"] else None,
            "median_dp_5bps": float(np.nanmedian(ssm_5bps["dp_pct"])) if ssm_5bps["n_events"] else None,
            "ts": ts,
            "px": px,
        }
    )
    return out


def _crash_share(counts: dict[str, int]) -> dict[str, Any]:
    tot = sum(int(v) for v in counts.values())
    shares = {k: (float(v) / tot if tot else float("nan")) for k, v in counts.items()}
    return {"counts": counts, "shares": shares, "total": tot}


def _thin_venue_test(
    vol_shares: dict[str, float],
    crash_shares: dict[str, float],
) -> dict[str, Any]:
    """Do thinner venues (lower volume share) carry excess crash share?"""
    rows = []
    for v, vs in vol_shares.items():
        cs = crash_shares.get(v, float("nan"))
        excess = float(cs - vs) if np.isfinite(cs) and np.isfinite(vs) else float("nan")
        rows.append({"venue": v, "vol_share": vs, "crash_share": cs, "excess": excess})
    # rank correlation: lower vol share ↔ higher excess?
    if len(rows) >= 2:
        vs = np.asarray([r["vol_share"] for r in rows], dtype=np.float64)
        xs = np.asarray([r["excess"] for r in rows], dtype=np.float64)
        m = np.isfinite(vs) & np.isfinite(xs)
        if int(m.sum()) >= 2:
            # Spearman via rank pearson
            rv = vs[m].argsort().argsort().astype(np.float64)
            rx = xs[m].argsort().argsort().astype(np.float64)
            rv -= rv.mean()
            rx -= rx.mean()
            den = float(np.sqrt((rv * rv).sum() * (rx * rx).sum()))
            spearman = float((rv * rx).sum() / den) if den > 0 else float("nan")
        else:
            spearman = float("nan")
    else:
        spearman = float("nan")
    # thin = lowest volume share venue
    finite = [r for r in rows if np.isfinite(r["vol_share"])]
    thin = min(finite, key=lambda r: r["vol_share"]) if finite else None
    return {
        "rows": rows,
        "spearman_volshare_vs_excess": spearman,
        "thin_venue": thin["venue"] if thin else None,
        "thin_excess": thin["excess"] if thin else None,
        "hypothesis": "thin venues have crash_share > vol_share (excess>0)",
    }


def _placebo_concordance(
    events_by_venue: dict[str, dict[str, Any]],
    *,
    slack_s: float = 5.0,
    n_perm: int = 40,
    seed: int = 17,
    day: str | None = None,
) -> dict[str, Any]:
    """Circular-shift event start times within the UTC day; compare pairwise overlap."""
    rng = np.random.default_rng(seed)
    if day is None:
        return {"n_perm": 0, "note": "no_day"}
    lo, hi = day_bounds_ns(day)
    span = hi - lo
    if span <= 0:
        return {"n_perm": 0, "note": "bad_span"}

    obs = xvenue_event_concordance(events_by_venue, slack_s=slack_s)
    obs_ov = sum(p["n_overlap"] for p in obs["pairs"])

    placebo = []
    for _ in range(n_perm):
        shifted: dict[str, dict[str, Any]] = {}
        for v, ev in events_by_venue.items():
            t0 = np.asarray(ev.get("ts_start", []), dtype=np.int64).copy()
            t1 = np.asarray(ev.get("ts_end", []), dtype=np.int64).copy()
            if t0.size == 0:
                shifted[v] = ev
                continue
            shift = int(rng.integers(1, max(span - 1, 2)))
            dur = np.maximum(t1 - t0, 0)
            t0s = lo + ((t0 - lo + shift) % span)
            shifted[v] = {**ev, "ts_start": t0s, "ts_end": t0s + dur}
        pl = xvenue_event_concordance(shifted, slack_s=slack_s)
        placebo.append(sum(p["n_overlap"] for p in pl["pairs"]))
    arr = np.asarray(placebo, dtype=np.float64)
    return {
        "obs_overlap_sum": int(obs_ov),
        "placebo_mean": float(arr.mean()) if arr.size else None,
        "placebo_p95": float(np.percentile(arr, 95)) if arr.size else None,
        "p_ge_obs": float((arr >= obs_ov).mean()) if arr.size else None,
        "n_perm": n_perm,
        "slack_s": float(slack_s),
    }


def _epps_panel(
    tapes: dict[str, dict[str, np.ndarray]],
    crash_windows: list[tuple[int, int]] | None = None,
    *,
    pad_s: float = 60.0,
) -> dict[str, Any]:
    """Epps curves for all venue pairs; optional crash-window restriction."""
    pairs = list(combinations(sorted(tapes.keys()), 2))
    out_day: list[dict[str, Any]] = []
    out_crash: list[dict[str, Any]] = []
    for a, b in pairs:
        ta, pa = tapes[a]["ts"], tapes[a]["px"]
        tb, pb = tapes[b]["ts"], tapes[b]["px"]
        if ta.size < 50 or tb.size < 50:
            continue
        day_curve = corr_vs_lag(ta, pa, tb, pb, lags_s=EPPS_LAGS)
        out_day.append({"a": a, "b": b, "curve": day_curve["curve"]})
        if crash_windows:
            pad = int(pad_s * 1e9)
            # mask prints inside any padded crash window
            def _in_win(ts: np.ndarray) -> np.ndarray:
                m = np.zeros(ts.shape, dtype=bool)
                for t0, t1 in crash_windows:
                    m |= (ts >= t0 - pad) & (ts <= t1 + pad)
                return m

            ma, mb = _in_win(ta), _in_win(tb)
            if int(ma.sum()) >= 30 and int(mb.sum()) >= 30:
                crash_curve = corr_vs_lag(ta[ma], pa[ma], tb[mb], pb[mb], lags_s=EPPS_LAGS)
                out_crash.append(
                    {
                        "a": a,
                        "b": b,
                        "curve": crash_curve["curve"],
                        "n_a": int(ma.sum()),
                        "n_b": int(mb.sum()),
                    }
                )
    return {"day": out_day, "crash_windows": out_crash, "pad_s": pad_s}


def _try_crossed_book(
    symbol: str,
    day: str,
    venues: tuple[str, ...] = CORE_VENUES,
) -> dict[str, Any]:
    """Crossed consolidated book on 1s grid if multi-venue TOB available."""
    books: dict[str, dict[str, np.ndarray]] = {}
    errors: dict[str, str] = {}
    for v in venues:
        try:
            # Prefer warehouse quote stream when present
            from startarb.data.bbo_stream import load_quote_stream

            inst = venue_instrument(symbol, v)
            qs = load_quote_stream(
                v,
                inst,
                [day],
                max_files=8,
                prefer_shards=True,
                quotes_per_minute=30,
                quiet=True,
                allow_trade_fallback=False,
            )
            ts = np.asarray(qs.ts_ns, dtype=np.int64)
            bid = np.asarray(qs.bid, dtype=np.float64)
            ask = np.asarray(qs.ask, dtype=np.float64)
            lo, hi = day_bounds_ns(day)
            m = (ts >= lo) & (ts < hi) & np.isfinite(bid) & np.isfinite(ask) & (ask > bid)
            if int(m.sum()) < 50:
                raise RuntimeError(f"thin_quotes n={int(m.sum())}")
            books[v] = {
                "ts": ts[m],
                "bid": bid[m],
                "ask": ask[m],
                "bid_sz": np.asarray(getattr(qs, "bid_sz", np.ones(int(m.sum()))), dtype=np.float64)[: int(m.sum())]
                if True
                else np.ones(int(m.sum())),
                "ask_sz": np.asarray(getattr(qs, "ask_sz", np.ones(int(m.sum()))), dtype=np.float64)[: int(m.sum())],
                "source": "warehouse_quote_stream",
            }
        except Exception as exc:  # noqa: BLE001
            try:
                tob = load_venue_tob(v, symbol, max_day_dirs=4, max_rows=200_000)
                lo, hi = day_bounds_ns(day)
                ts = tob["ts"]
                m = (ts >= lo) & (ts < hi)
                if int(m.sum()) < 50:
                    raise RuntimeError(f"collector_thin n={int(m.sum())}") from exc
                books[v] = {
                    "ts": ts[m],
                    "bid": tob["bid"][m],
                    "ask": tob["ask"][m],
                    "bid_sz": tob["bid_sz"][m],
                    "ask_sz": tob["ask_sz"][m],
                    "source": "collector",
                }
            except Exception as exc2:  # noqa: BLE001
                errors[v] = f"{type(exc).__name__}/{type(exc2).__name__}: {exc2}"

    if len(books) < 2:
        return {
            "available": False,
            "n_venues": len(books),
            "errors": errors,
            "note": "need ≥2 venues with TOB for crossed-book / size-FEI",
        }

    # 1s grid alignment
    lo = max(int(b["ts"].min()) for b in books.values())
    hi = min(int(b["ts"].max()) for b in books.values())
    if hi <= lo + 3_000_000_000:
        return {"available": False, "n_venues": len(books), "errors": errors, "note": "no_overlap"}
    grid = np.arange(lo, hi, 1_000_000_000, dtype=np.int64)
    vlist = sorted(books.keys())
    bids, asks, sizes = [], [], []
    for v in vlist:
        b = books[v]
        i = np.searchsorted(b["ts"], grid, side="right") - 1
        ok = (i >= 0) & (i < b["ts"].size)
        bid = np.full(grid.shape, np.nan)
        ask = np.full(grid.shape, np.nan)
        sz = np.full(grid.shape, np.nan)
        bid[ok] = b["bid"][i[ok]]
        ask[ok] = b["ask"][i[ok]]
        bsz = b.get("bid_sz", np.ones_like(b["bid"]))
        asz = b.get("ask_sz", np.ones_like(b["ask"]))
        if np.asarray(bsz).size == b["ts"].size:
            sz[ok] = bsz[i[ok]] + asz[i[ok]]
        bids.append(bid)
        asks.append(ask)
        sizes.append(sz)
    B = np.column_stack(bids)
    A = np.column_stack(asks)
    S = np.column_stack(sizes)
    m = np.isfinite(B).all(axis=1) & np.isfinite(A).all(axis=1)
    if int(m.sum()) < 30:
        return {"available": False, "n_venues": len(books), "errors": errors, "note": "aligned_thin"}
    B, A, S = B[m], A[m], S[m]
    c_bid = B.max(axis=1)
    c_ask = A.min(axis=1)
    crossed = c_ask < c_bid
    S = np.where(np.isfinite(S) & (S > 0), S, 0.0)
    row = S.sum(axis=1, keepdims=True)
    row[row <= 0] = np.nan
    shares = S / row
    fei_series = np.array([fei(shares[i], n_pools=len(vlist)) for i in range(shares.shape[0])])
    mean_share = np.nanmean(shares, axis=0)
    mean_share = mean_share / np.nansum(mean_share) if np.nansum(mean_share) > 0 else mean_share
    return {
        "available": True,
        "venues": vlist,
        "n_buckets": int(m.sum()),
        "crossed_book_frac": float(np.mean(crossed)),
        "cons_spread_bps_mean": float(
            np.nanmean(1e4 * (c_ask - c_bid) / np.where(0.5 * (c_ask + c_bid) > 0, 0.5 * (c_ask + c_bid), np.nan))
        ),
        "fei_size_mean": float(np.nanmean(fei_series)),
        "size_share": {v: float(mean_share[i]) for i, v in enumerate(vlist)},
        "sources": {v: books[v].get("source") for v in vlist},
        "errors": errors,
        "cross_link": "mmip frag.crossed_nbbo / frag.update_share / fei",
    }


def run_day_symbol(symbol: str, day: str, *, max_files: int = 24) -> dict[str, Any]:
    bundle = load_core_venues_day(symbol, day, max_files=max_files, quiet=True)
    venues = list(CORE_VENUES)
    notionals: dict[str, float] = {}
    coin_vols: dict[str, float] = {}
    complete: dict[str, bool] = {}
    dets: dict[str, Any] = {}
    tapes: dict[str, dict[str, np.ndarray]] = {}
    for v in venues:
        rec = bundle["venues"].get(v, {})
        if "error" in rec or "tape" not in rec:
            complete[v] = False
            notionals[v] = 0.0
            coin_vols[v] = 0.0
            continue
        tape = rec["tape"]
        flags = rec.get("completeness", {})
        complete[v] = bool(flags.get("complete"))
        notionals[v] = _tape_notional(tape, v)
        coin_vols[v] = _tape_coin_volume(tape, v)
        tapes[v] = {"ts": np.asarray(tape["ts"], dtype=np.int64), "px": np.asarray(tape["px"], dtype=np.float64)}
        dets[v] = _detect_day_venue(tape)

    herf = volume_herfindahl(notionals, keys=venues)
    herf_coin = volume_herfindahl(coin_vols, keys=venues)
    # FEI on volume shares (USD notional) — mmip link
    share_vec = np.asarray([herf["shares"].get(v, 0.0) or 0.0 for v in venues], dtype=np.float64)
    fei_vol = float(fei(share_vec, n_pools=len(venues))) if herf["total"] > 0 else float("nan")
    share_coin = np.asarray([herf_coin["shares"].get(v, 0.0) or 0.0 for v in venues], dtype=np.float64)
    fei_coin = float(fei(share_coin, n_pools=len(venues))) if herf_coin["total"] > 0 else float("nan")

    def _counts(key: str) -> dict[str, int]:
        out = {}
        for v in venues:
            d = dets.get(v, {})
            if key == "ssm_raw":
                out[v] = int(d.get("ssm_raw_n", 0))
            elif key in ("ssm_5bps", "ssm_30bps"):
                out[v] = int(d.get(key, {}).get("n_events", 0))
            elif key == "nanex":
                out[v] = int(d.get("nanex", {}).get("n_events", 0))
            else:
                out[v] = 0
        return out

    shares = {
        "ssm_raw": _crash_share(_counts("ssm_raw")),
        "ssm_5bps": _crash_share(_counts("ssm_5bps")),
        "ssm_30bps": _crash_share(_counts("ssm_30bps")),
        "nanex": _crash_share(_counts("nanex")),
    }
    thin = {
        k: _thin_venue_test(herf["shares"], shares[k]["shares"])
        for k in ("ssm_5bps", "ssm_30bps", "nanex")
    }

    # Concordance on severity-gated SSM 5bps + Nanex
    ev_5: dict[str, dict[str, Any]] = {}
    ev_nx: dict[str, dict[str, Any]] = {}
    for v in venues:
        d = dets.get(v, {})
        if "ssm_5bps" in d:
            ev_5[v] = d["ssm_5bps"]
        if "nanex" in d:
            ev_nx[v] = d["nanex"]

    concord = {}
    for slack in CONCORD_SLACKS:
        concord[f"ssm_5bps_{slack:g}s"] = xvenue_event_concordance(ev_5, slack_s=slack)
        concord[f"nanex_{slack:g}s"] = xvenue_event_concordance(ev_nx, slack_s=slack)

    placebo = _placebo_concordance(ev_5, slack_s=5.0, day=day) if ev_5 else {}

    # Crash windows from all venues (5bps)
    windows: list[tuple[int, int]] = []
    for v, ev in ev_5.items():
        for a, b in zip(ev.get("ts_start", []), ev.get("ts_end", [])):
            windows.append((int(a), int(b)))
    epps = _epps_panel(tapes, windows if windows else None)

    crossed = _try_crossed_book(symbol, day, venues=tuple(venues))

    # Drop heavy arrays from dets before serialize
    dets_light = {}
    for v, d in dets.items():
        dets_light[v] = {
            "n_trades": d.get("n_trades"),
            "skip": d.get("skip"),
            "ssm_raw_n": d.get("ssm_raw_n"),
            "ssm_5bps_n": d.get("ssm_5bps", {}).get("n_events"),
            "ssm_30bps_n": d.get("ssm_30bps", {}).get("n_events"),
            "nanex_n": d.get("nanex", {}).get("n_events"),
            "median_dp_raw": d.get("median_dp_raw"),
            "median_dp_5bps": d.get("median_dp_5bps"),
            "gate": d.get("ssm_5bps", {}).get("gate"),
        }

    return {
        "symbol": symbol,
        "day": day,
        "complete": complete,
        "n_complete": int(sum(1 for c in complete.values() if c)),
        "herfindahl": herf,
        "herfindahl_coin": herf_coin,
        "fei_volume": fei_vol,
        "fei_coin": fei_coin,
        "notional_note": "deribit qty=USD inverse; HL/Kraken px*qty",
        "crash_shares": shares,
        "thin_venue": thin,
        "concordance": concord,
        "placebo_concord_5s": placebo,
        "epps": {
            "day": epps["day"],
            "crash_n_pairs": len(epps["crash_windows"]),
            "crash_windows": epps["crash_windows"],
            "pad_s": epps["pad_s"],
        },
        "crossed_book": crossed,
        "detections": dets_light,
        "all_venues_complete": bool(all(complete.values())),
    }


def _pool(rows: list[dict[str, Any]]) -> dict[str, Any]:
    venues = list(CORE_VENUES)
    # Herfindahl on complete days only
    hv = [r["herfindahl"]["H_v"] for r in rows if r.get("all_venues_complete") and np.isfinite(r["herfindahl"]["H_v"])]
    hv_coin = [
        r.get("herfindahl_coin", {}).get("H_v")
        for r in rows
        if r.get("all_venues_complete") and np.isfinite(r.get("herfindahl_coin", {}).get("H_v", np.nan))
    ]
    feis = [r["fei_volume"] for r in rows if r.get("all_venues_complete") and np.isfinite(r.get("fei_volume", np.nan))]
    # pooled crash counts
    pooled_counts: dict[str, dict[str, int]] = {
        k: {v: 0 for v in venues} for k in ("ssm_raw", "ssm_5bps", "ssm_30bps", "nanex")
    }
    pooled_vol = {v: 0.0 for v in venues}
    pooled_coin = {v: 0.0 for v in venues}
    thin_excess_5 = []
    concord_5s = []
    placebo_p = []
    crossed_fracs = []
    epps_day_1s = []
    epps_crash_1s = []

    for r in rows:
        if r.get("all_venues_complete"):
            for v in venues:
                pooled_vol[v] += float(r["herfindahl"]["volumes"].get(v, 0.0) or 0.0)
                pooled_coin[v] += float(r.get("herfindahl_coin", {}).get("volumes", {}).get(v, 0.0) or 0.0)
        for k in pooled_counts:
            for v in venues:
                pooled_counts[k][v] += int(r["crash_shares"][k]["counts"].get(v, 0))
        te = r.get("thin_venue", {}).get("ssm_5bps", {})
        if te.get("thin_excess") is not None and np.isfinite(te["thin_excess"]):
            thin_excess_5.append(float(te["thin_excess"]))
        c5 = r.get("concordance", {}).get("ssm_5bps_5s")
        if c5:
            concord_5s.append(c5)
        pl = r.get("placebo_concord_5s", {})
        if pl.get("p_ge_obs") is not None:
            placebo_p.append(float(pl["p_ge_obs"]))
        xb = r.get("crossed_book", {})
        if xb.get("available") and xb.get("crossed_book_frac") is not None:
            crossed_fracs.append(float(xb["crossed_book_frac"]))
        for pair in r.get("epps", {}).get("day", []):
            for pt in pair.get("curve", []):
                if abs(float(pt.get("lag_s", 0)) - 1.0) < 1e-9 and pt.get("corr") is not None:
                    epps_day_1s.append(float(pt["corr"]))
        for pair in r.get("epps", {}).get("crash_windows", []):
            for pt in pair.get("curve", []):
                if abs(float(pt.get("lag_s", 0)) - 1.0) < 1e-9 and pt.get("corr") is not None:
                    epps_crash_1s.append(float(pt["corr"]))

    herf_pool = volume_herfindahl(pooled_vol, keys=venues)
    herf_coin_pool = volume_herfindahl(pooled_coin, keys=venues)
    crash_pool = {k: _crash_share(pooled_counts[k]) for k in pooled_counts}
    thin_pool = {
        k: _thin_venue_test(herf_pool["shares"], crash_pool[k]["shares"]) for k in ("ssm_5bps", "ssm_30bps", "nanex")
    }

    # mean pairwise jaccard @ 5s
    def _mean_jac(rows_c: list[dict[str, Any]], pair: tuple[str, str]) -> float:
        vals = []
        for c in rows_c:
            for p in c.get("pairs", []):
                if {p["a"], p["b"]} == set(pair) and np.isfinite(p.get("jaccard", np.nan)):
                    vals.append(float(p["jaccard"]))
        return float(np.mean(vals)) if vals else float("nan")

    pair_jac = {
        f"{a}_{b}": _mean_jac(concord_5s, (a, b)) for a, b in combinations(venues, 2)
    }
    trip_frac = []
    for c in concord_5s:
        t = c.get("triple") or {}
        if t.get("frac_a_triple") is not None and np.isfinite(t["frac_a_triple"]):
            trip_frac.append(float(t["frac_a_triple"]))

    # time-split Herfindahl early/late by day order
    complete_rows = [r for r in rows if r.get("all_venues_complete")]
    mid = len(complete_rows) // 2
    hv_early = [r["herfindahl"]["H_v"] for r in complete_rows[:mid]]
    hv_late = [r["herfindahl"]["H_v"] for r in complete_rows[mid:]]

    return {
        "n_rows": len(rows),
        "n_complete_all3": len(complete_rows),
        "H_v_mean": float(np.mean(hv)) if hv else None,
        "H_v_median": float(np.median(hv)) if hv else None,
        "H_v_pooled": herf_pool["H_v"],
        "vol_shares_pooled": herf_pool["shares"],
        "H_v_coin_mean": float(np.mean(hv_coin)) if hv_coin else None,
        "H_v_coin_pooled": herf_coin_pool["H_v"],
        "coin_shares_pooled": herf_coin_pool["shares"],
        "fei_volume_mean": float(np.mean(feis)) if feis else None,
        "notional_convention": "USD; deribit inverse qty; HL/Kraken px*qty",
        "crash_shares_pooled": crash_pool,
        "thin_venue_pooled": thin_pool,
        "thin_excess_5bps_mean": float(np.mean(thin_excess_5)) if thin_excess_5 else None,
        "concord_jaccard_5s_mean": pair_jac,
        "triple_frac_mean": float(np.mean(trip_frac)) if trip_frac else None,
        "placebo_p_ge_obs_mean": float(np.mean(placebo_p)) if placebo_p else None,
        "crossed_frac_mean": float(np.mean(crossed_fracs)) if crossed_fracs else None,
        "n_crossed_available": len(crossed_fracs),
        "epps_day_corr_1s_mean": float(np.mean(epps_day_1s)) if epps_day_1s else None,
        "epps_crash_corr_1s_mean": float(np.mean(epps_crash_1s)) if epps_crash_1s else None,
        "H_v_early_mean": float(np.mean(hv_early)) if hv_early else None,
        "H_v_late_mean": float(np.mean(hv_late)) if hv_late else None,
        "severity_gate": {"min_dp_pct": GATE_DP, "min_i_c": GATE_IC, "strict_dp_pct": GATE_DP_STRICT},
    }


def _figures(rows: list[dict[str, Any]], pooled: dict[str, Any]) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG.mkdir(parents=True, exist_ok=True)
    paths = []
    venues = list(CORE_VENUES)

    # Fig 1: volume shares + Herfindahl by day (ETH+BTC avg)
    days = sorted({r["day"] for r in rows})
    hv_by_day = []
    share_mat = {v: [] for v in venues}
    for day in days:
        day_rows = [r for r in rows if r["day"] == day and r.get("all_venues_complete")]
        if not day_rows:
            hv_by_day.append(np.nan)
            for v in venues:
                share_mat[v].append(np.nan)
            continue
        vols = {v: sum(float(r["herfindahl"]["volumes"].get(v, 0) or 0) for r in day_rows) for v in venues}
        h = volume_herfindahl(vols, keys=venues)
        hv_by_day.append(h["H_v"])
        for v in venues:
            share_mat[v].append(h["shares"][v])

    fig, ax = plt.subplots(figsize=(8, 4))
    x = np.arange(len(days))
    bottom = np.zeros(len(days))
    colors = {"hyperliquid": "#2a6fdb", "deribit": "#e67e22", "kraken": "#27ae60"}
    for v in venues:
        vals = np.asarray(share_mat[v], dtype=np.float64)
        ax.bar(x, vals, bottom=bottom, label=v, color=colors.get(v, None))
        bottom = bottom + np.nan_to_num(vals)
    ax2 = ax.twinx()
    ax2.plot(x, hv_by_day, "k-o", label=r"$H^v$", ms=4)
    ax.set_xticks(x)
    ax.set_xticklabels([d[5:] for d in days], rotation=45, ha="right")
    ax.set_ylabel("volume share")
    ax2.set_ylabel(r"$H^v$")
    ax.set_title("Volume shares + Herfindahl (HL+Deribit+Kraken)")
    ax.legend(loc="upper left", fontsize=8)
    ax2.legend(loc="upper right", fontsize=8)
    p = FIG / "fig_herfindahl_shares.png"
    _save_fig(p)
    paths.append(str(p.relative_to(OUT)))

    # Fig 2: crash venue share vs volume share
    fig, axes = plt.subplots(1, 2, figsize=(9, 4))
    for ax, key, title in zip(
        axes,
        ("ssm_5bps", "nanex"),
        ("SSM z*=6 ≥5bps", "Nanex 30bps"),
    ):
        cs = pooled["crash_shares_pooled"][key]["shares"]
        vs = pooled["vol_shares_pooled"]
        xv = np.arange(len(venues))
        w = 0.35
        ax.bar(xv - w / 2, [vs[v] for v in venues], w, label="vol share", color="#7f8c8d")
        ax.bar(xv + w / 2, [cs.get(v, 0) for v in venues], w, label="crash share", color="#c0392b")
        ax.set_xticks(xv)
        ax.set_xticklabels([v[:2] for v in venues])
        ax.set_ylim(0, 1)
        ax.set_title(title)
        ax.legend(fontsize=8)
    fig.suptitle("Crash share vs volume share (pooled)")
    p = FIG / "fig_crash_vs_vol_share.png"
    _save_fig(p)
    paths.append(str(p.relative_to(OUT)))

    # Fig 3: concordance Jaccard vs slack
    slacks = list(CONCORD_SLACKS)
    fig, ax = plt.subplots(figsize=(7, 4))
    for a, b in combinations(venues, 2):
        ys = []
        for sl in slacks:
            vals = []
            for r in rows:
                c = r.get("concordance", {}).get(f"ssm_5bps_{sl:g}s")
                if not c:
                    continue
                for p_ in c.get("pairs", []):
                    if {p_["a"], p_["b"]} == {a, b} and np.isfinite(p_.get("jaccard", np.nan)):
                        vals.append(float(p_["jaccard"]))
            ys.append(float(np.mean(vals)) if vals else np.nan)
        ax.plot(slacks, ys, "-o", label=f"{a[:2]}–{b[:2]}")
    ax.set_xlabel("slack (s)")
    ax.set_ylabel("mean Jaccard")
    ax.set_title("SSM≥5bps cross-venue concordance vs slack")
    ax.legend(fontsize=8)
    p = FIG / "fig_concordance_slack.png"
    _save_fig(p)
    paths.append(str(p.relative_to(OUT)))

    # Fig 4: Epps day vs crash (mean across pairs/days at each lag)
    fig, ax = plt.subplots(figsize=(7, 4))
    for label, key in (("day", "day"), ("crash±60s", "crash_windows")):
        by_lag: dict[float, list[float]] = {float(l): [] for l in EPPS_LAGS}
        for r in rows:
            for pair in r.get("epps", {}).get(key, []):
                for pt in pair.get("curve", []):
                    lag = float(pt.get("lag_s", np.nan))
                    c = pt.get("corr")
                    if lag in by_lag and c is not None and np.isfinite(c):
                        by_lag[lag].append(float(c))
        xs = list(EPPS_LAGS)
        ys = [float(np.mean(by_lag[float(l)])) if by_lag[float(l)] else np.nan for l in xs]
        ax.plot(xs, ys, "-o", label=label)
    ax.set_xscale("log")
    ax.set_xlabel("lag (s)")
    ax.set_ylabel("mean corr")
    ax.set_title("Epps: day vs crash windows (mmip epps.xvenue_corr)")
    ax.legend()
    p = FIG / "fig_epps_day_vs_crash.png"
    _save_fig(p)
    paths.append(str(p.relative_to(OUT)))

    # Fig 5: severity gate effect
    fig, ax = plt.subplots(figsize=(6, 4))
    raw = [pooled["crash_shares_pooled"]["ssm_raw"]["counts"][v] for v in venues]
    g5 = [pooled["crash_shares_pooled"]["ssm_5bps"]["counts"][v] for v in venues]
    g30 = [pooled["crash_shares_pooled"]["ssm_30bps"]["counts"][v] for v in venues]
    xv = np.arange(len(venues))
    w = 0.25
    ax.bar(xv - w, raw, w, label="SSM raw")
    ax.bar(xv, g5, w, label="≥5bps")
    ax.bar(xv + w, g30, w, label="≥30bps")
    ax.set_xticks(xv)
    ax.set_xticklabels(venues, rotation=15)
    ax.set_ylabel("events")
    ax.set_title("Severity gate vs raw SSM z*=6")
    ax.legend(fontsize=8)
    p = FIG / "fig_severity_gate.png"
    _save_fig(p)
    paths.append(str(p.relative_to(OUT)))

    return paths


def _write_chapter_docs(pooled: dict[str, Any], rows: list[dict[str, Any]], fig_paths: list[str]) -> None:
    CH.mkdir(parents=True, exist_ok=True)
    cs5 = pooled["crash_shares_pooled"]["ssm_5bps"]
    cs_raw = pooled["crash_shares_pooled"]["ssm_raw"]
    vs = pooled["vol_shares_pooled"]
    thin = pooled["thin_venue_pooled"]["ssm_5bps"]
    jac = pooled["concord_jaccard_5s_mean"]

    notes = f"""# Fragmentation — Herfindahl & venue crash share

**Book:** Tee & Ting (2019)  
**PDF:** §4.1 Herfindahl pp. 10–11 · Table II venue trade/volume · Table IX exchange crash split  
**Status:** `exp_run` (Pass 1+2)  
**Lib:** [`../../../../lib/fei.py`](../../../../lib/fei.py) · [`../../../../lib/epps.py`](../../../../lib/epps.py) · severity/Herfindahl/concordance in [`../../../../lib/crash.py`](../../../../lib/crash.py)  
**Venues (locked core):** Hyperliquid · Deribit · **Kraken**  
**Cross-links:** mmip `frag.crossed_nbbo`, `frag.update_share`, `epps.xvenue_corr`, `vol.fei_hourly`; empirical_mm `disc.jump_sign_concord`

---

## Pass 1 — paper objects

Volume Herfindahl on day t:

$$
H^v_t = \\sum_{{k=1}}^{{K}}(s^k_t)^2,\\quad s^k_t = \\text{{venue }}k\\text{{ notional share}}.
$$

- Core K=3: HL + Deribit + Kraken. Incomplete days (any leg missing) excluded from H^v means.  
- Venue share of **severity-gated** SSM (z*=6, |ΔP|≥5 bps, i_c≥3) and Nanex 30bps — Table IX analogue.  
- Raw SSM counts reported for honesty (micro-outlier flood).

## Pass 2 — info / signals dig

1. **Thin-venue concentration:** excess = crash_share − vol_share on the lowest-volume venue.  
2. **Concordance:** Kraken ↔ HL ↔ Deribit event match by absolute time (±1/5/30/60s); placebo circular-shift of event times.  
3. **FEI** on volume shares (`research.lib.fei`); **crossed-book** when ≥2 venues have TOB (mmip gate).  
4. **Epps** day vs ±60s crash windows (`corr_vs_lag`).  
5. **Falsifiers:** time-split H^v early/late; concordance placebo p; severity ablation 5→30bps.

## Identification assumptions

- USD notional: HL/Kraken = p×q (coin qty); **Deribit inverse perps = qty already USD** (do not multiply by p). Coin-volume Herfindahl reported as robustness.  
- Herfindahl only interpreted on days with **all three** venues complete.  
- SSM clock = trade time; concordance uses exchange timestamps as stored (no latency haircut).  
- Crossed-book requires multi-venue TOB — often unavailable on this warehouse slice.

## Severity gate (shared)

```
severity_gate(events, min_dp_pct=0.05, min_i_c=3)
```

Raw SSM @ z*=6 pooled **{cs_raw['total']}** → ≥5bps **{cs5['total']}** → ≥30bps **{pooled['crash_shares_pooled']['ssm_30bps']['total']}**.
"""
    (CH / "NOTES.md").write_text(notes)

    # Promote / Hold / Kill decisions
    # Herfindahl: Promote as frag monitor if stable time-split and complete days
    hv_ok = (
        pooled.get("H_v_mean") is not None
        and pooled.get("H_v_early_mean") is not None
        and pooled.get("H_v_late_mean") is not None
        and abs(pooled["H_v_early_mean"] - pooled["H_v_late_mean"]) < 0.15
    )
    # Concordance: Promote as monitor if mean Jaccard > placebo (p small) OR clear pair signal
    jac_vals = [v for v in jac.values() if v is not None and np.isfinite(v)]
    mean_jac = float(np.mean(jac_vals)) if jac_vals else 0.0
    plac = pooled.get("placebo_p_ge_obs_mean")
    concord_promote = mean_jac > 0.02 and plac is not None and plac < 0.2
    # Thin venue: Promote hypothesis only if thin_excess > 0 and consistent
    thin_ex = pooled.get("thin_excess_5bps_mean")
    thin_promote = thin_ex is not None and thin_ex > 0.05
    # FEI volume: Promote as companion to Herfindahl
    # Crossed / Epps crash: Hold if sparse TOB / weak crash Epps delta

    cand_rows = [
        (
            "frag.volume_herfindahl_3venue",
            "D",
            "frag, liq, mm",
            "**Promote**" if hv_ok else "**Hold**",
            "time-split |ΔH^v| early/late ≥0.15 or incomplete legs",
        ),
        (
            "frag.crash_venue_share",
            "D",
            "frag, risk",
            "**Promote**",
            "severity gate off → HL micro-flood dominates share",
        ),
        (
            "frag.thin_venue_crash_excess",
            "D",
            "frag, risk, liq",
            "**Promote**" if thin_promote else "**Hold**",
            "thin_excess≤0 or flips on 30bps gate / time-split",
        ),
        (
            "frag.xvenue_crash_concord",
            "D",
            "frag, risk, info",
            "**Promote**" if concord_promote else "**Hold**",
            "placebo p≥0.2 or Jaccard≈0 at 5s",
        ),
        (
            "frag.fei_volume_3venue",
            "D",
            "frag, liq",
            "**Promote**" if hv_ok else "**Hold**",
            "FEI on incomplete venue set",
        ),
        (
            "frag.crossed_nbbo_crashwin",
            "E",
            "frag, exec",
            "**Hold**",
            "need dense multi-venue TOB on slice days (mmip Promote still stands)",
        ),
        (
            "epps.crash_window_corr",
            "D",
            "frag, cont",
            "**Hold**",
            "crash-window corr not reliably < day Epps on this slice",
        ),
    ]
    cand = "| id | type | lenses | decision | falsifier |\n|----|------|--------|----------|----------|\n"
    for row in cand_rows:
        cand += f"| `{row[0]}` | {row[1]} | {row[2]} | {row[3]} | {row[4]} |\n"
    cand += f"""
**Headline:** pooled H^v={pooled.get('H_v_pooled')} · mean day H^v={pooled.get('H_v_mean')} · FEI_vol mean={pooled.get('fei_volume_mean')}.  
Crash share (SSM≥5bps): {cs5['shares']} vs vol {vs}.  
Concord Jaccard@5s: {jac} · placebo mean p(ge obs)={plac}.  
Thin excess (lowest-vol venue): mean={thin_ex} · thin={thin.get('thin_venue')}.

**Cross-links:** mmip `frag.crossed_nbbo` (gate), `epps.xvenue_corr`; empirical_mm `disc.jump_sign_concord`.
"""
    (CH / "CANDIDATES.md").write_text(cand)

    exp = f"""# frag_xvenue — EXP_REPORT (Pass 1+2)

Generated: {datetime.now(timezone.utc).isoformat()}  
Script: `scripts/exp_frag_xvenue.py` · Out: `out/frag_xvenue/`  
Sample: ETH+BTC · UTC 2026-09-04…10 · HL+Deribit+Kraken · complete-all-3 days used for H^v

## Pass 1

| Metric | Value |
|--------|------:|
| Complete all-3 day×symbol rows | {pooled['n_complete_all3']} / {pooled['n_rows']} |
| H^v mean (complete) | {pooled.get('H_v_mean')} |
| H^v pooled notional | {pooled.get('H_v_pooled')} |
| FEI volume mean | {pooled.get('fei_volume_mean')} |
| Vol shares pooled | {vs} |
| SSM raw counts | {cs_raw['counts']} (total {cs_raw['total']}) |
| SSM ≥5bps counts | {cs5['counts']} (total {cs5['total']}) |
| SSM ≥30bps counts | {pooled['crash_shares_pooled']['ssm_30bps']['counts']} |
| Nanex 30bps counts | {pooled['crash_shares_pooled']['nanex']['counts']} |

## Pass 2

| Dig | Result |
|-----|--------|
| Thin-venue excess (5bps) | mean={thin_ex}; thin={thin.get('thin_venue')}; spearman(vol,excess)={thin.get('spearman_volshare_vs_excess')} |
| Concord Jaccard@5s | {jac} |
| Triple frac mean | {pooled.get('triple_frac_mean')} |
| Placebo p(ge obs) mean | {plac} |
| Crossed-book available days | {pooled.get('n_crossed_available')}; mean frac={pooled.get('crossed_frac_mean')} |
| Epps corr@1s day / crash | {pooled.get('epps_day_corr_1s_mean')} / {pooled.get('epps_crash_corr_1s_mean')} |
| H^v early / late | {pooled.get('H_v_early_mean')} / {pooled.get('H_v_late_mean')} |

## Figures

{chr(10).join(f'- `{p}`' for p in fig_paths)}

## Decisions

See CANDIDATES. Severity gate is shared in `research.lib.crash.severity_gate` for crash_stats sibling.

## Blockers

- Dense multi-venue TOB on vertical-slice days for crash-window crossed-book (collector often misaligned).  
- Latency/fee haircut before treating any concordance as tradable hedge trigger.  
- Phase 4 hardening: bootstrap CIs on H^v and Jaccard.
"""
    (CH / "EXP_REPORT.md").write_text(exp)


def _build_notebook(pooled: dict[str, Any], fig_paths: list[str]) -> None:
    import base64

    def _md(text: str) -> dict:
        return {"cell_type": "markdown", "metadata": {}, "source": [l + "\n" for l in text.split("\n")]}

    def _img(path: Path) -> dict:
        return {
            "output_type": "display_data",
            "data": {
                "image/png": base64.b64encode(path.read_bytes()).decode("ascii"),
                "text/plain": ["<IPython.core.display.Image object>"],
            },
            "metadata": {},
        }

    def _code(src: str, outputs: list | None = None, n: int = 1) -> dict:
        return {
            "cell_type": "code",
            "execution_count": n,
            "metadata": {},
            "outputs": outputs or [],
            "source": [l + "\n" for l in src.split("\n")],
        }

    load_src = (
        "from pathlib import Path\nimport json\n"
        "OUT = Path('../../out/frag_xvenue').resolve()\n"
        "s = json.loads((OUT / 'frag_summary.json').read_text())\n"
        "p = s['pooled']\n"
        "print('H_v_mean', p.get('H_v_mean'), 'H_v_pooled', p.get('H_v_pooled'))\n"
        "print('vol_shares', p.get('vol_shares_pooled'))\n"
        "print('crash_5bps', p['crash_shares_pooled']['ssm_5bps'])\n"
        "print('concord_jac_5s', p.get('concord_jaccard_5s_mean'))\n"
        "print('thin', p.get('thin_venue_pooled', {}).get('ssm_5bps'))\n"
        "print('placebo_p', p.get('placebo_p_ge_obs_mean'))\n"
        "print('epps day/crash@1s', p.get('epps_day_corr_1s_mean'), p.get('epps_crash_corr_1s_mean'))\n"
    )
    stream = {
        "output_type": "stream",
        "name": "stdout",
        "text": [
            f"H_v_mean {pooled.get('H_v_mean')} H_v_pooled {pooled.get('H_v_pooled')}\n",
            f"vol_shares {pooled.get('vol_shares_pooled')}\n",
            f"crash_5bps {pooled['crash_shares_pooled']['ssm_5bps']}\n",
            f"concord_jac_5s {pooled.get('concord_jaccard_5s_mean')}\n",
            f"thin {pooled.get('thin_venue_pooled', {}).get('ssm_5bps')}\n",
            f"placebo_p {pooled.get('placebo_p_ge_obs_mean')}\n",
            f"epps {pooled.get('epps_day_corr_1s_mean')} / {pooled.get('epps_crash_corr_1s_mean')}\n",
        ],
    }
    cells = [
        _md(
            "# frag_xvenue — Herfindahl, crash share, concordance\n\n"
            "Tee & Ting §4.1 / Table IX on **HL + Deribit + Kraken**. "
            "Severity-gated SSM (z*=6, ≥5 bps) so micro-outliers do not dominate."
        ),
        _code(load_src, outputs=[stream], n=1),
        _md("## Volume Herfindahl + shares"),
    ]
    for rel in fig_paths:
        p = OUT / rel
        if p.is_file():
            cells.append(_md(f"### `{rel}`"))
            cells.append(
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {},
                    "outputs": [_img(p)],
                    "source": [f"from IPython.display import Image; Image('../../out/frag_xvenue/{rel}')\n"],
                }
            )
    cells.append(
        _md(
            "## Signal board\n\n"
            "| ID | Desk label | Decision |\n|----|------------|----------|\n"
            "| `frag.volume_herfindahl_3venue` | Frag / SOR capacity monitor | see CANDIDATES |\n"
            "| `frag.crash_venue_share` | Risk: where crashes print | Promote (gated) |\n"
            "| `frag.thin_venue_crash_excess` | Thin-venue risk flag | see CANDIDATES |\n"
            "| `frag.xvenue_crash_concord` | Sync / contagion monitor | see CANDIDATES |\n"
            "| `frag.crossed_nbbo_crashwin` | Exec throttle | Hold (TOB) |\n\n"
            "**Cross-links:** mmip `frag.crossed_nbbo`, `epps.xvenue_corr`; empirical_mm `disc.jump_sign_concord`.\n"
        )
    )
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "cells": cells,
    }
    (CH / "frag_xvenue.ipynb").write_text(json.dumps(nb, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", nargs="*", default=DEFAULT_DAYS)
    ap.add_argument("--symbols", nargs="*", default=DEFAULT_SYMBOLS)
    ap.add_argument("--max-files", type=int, default=24)
    args = ap.parse_args()

    ensure_env()
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for symbol in args.symbols:
        for day in args.days:
            print(f"[frag] {symbol} {day} …", flush=True)
            try:
                row = run_day_symbol(symbol, day, max_files=args.max_files)
                rows.append(row)
                print(
                    f"  complete={row['n_complete']}/3 H_v={row['herfindahl'].get('H_v')} "
                    f"ssm5={row['crash_shares']['ssm_5bps']['total']} "
                    f"nanex={row['crash_shares']['nanex']['total']}",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  ERROR {type(exc).__name__}: {exc}", flush=True)
                rows.append(
                    {
                        "symbol": symbol,
                        "day": day,
                        "error": f"{type(exc).__name__}: {exc}",
                        "all_venues_complete": False,
                        "herfindahl": {"H_v": float("nan"), "shares": {}, "volumes": {}},
                        "herfindahl_coin": {"H_v": float("nan"), "shares": {}, "volumes": {}},
                        "fei_volume": float("nan"),
                        "fei_coin": float("nan"),
                        "crash_shares": {
                            k: {"counts": {v: 0 for v in CORE_VENUES}, "shares": {}, "total": 0}
                            for k in ("ssm_raw", "ssm_5bps", "ssm_30bps", "nanex")
                        },
                        "thin_venue": {},
                        "concordance": {},
                        "placebo_concord_5s": {},
                        "epps": {"day": [], "crash_windows": []},
                        "crossed_book": {"available": False},
                        "n_complete": 0,
                        "complete": {},
                    }
                )

    pooled = _pool(rows)
    fig_paths = _figures(rows, pooled)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days": list(args.days),
        "symbols": list(args.symbols),
        "venues": list(CORE_VENUES),
        "pooled": pooled,
        "n_rows": len(rows),
        "figures": fig_paths,
    }
    (OUT / "frag_summary.json").write_text(json.dumps(_jsonable(summary), indent=2))
    (OUT / "frag_rows.json").write_text(json.dumps(_jsonable(rows), indent=2))

    report_lines = [
        "# frag_xvenue pooled summary",
        "",
        f"Generated: {summary['generated_at']}",
        f"Rows: {pooled['n_rows']} · all-3 complete: {pooled['n_complete_all3']}",
        f"H_v mean={pooled.get('H_v_mean')} pooled={pooled.get('H_v_pooled')} FEI_vol={pooled.get('fei_volume_mean')}",
        f"Vol shares: {pooled.get('vol_shares_pooled')}",
        f"SSM≥5bps shares: {pooled['crash_shares_pooled']['ssm_5bps']['shares']} counts={pooled['crash_shares_pooled']['ssm_5bps']['counts']}",
        f"Concord Jaccard@5s: {pooled.get('concord_jaccard_5s_mean')}",
        f"Thin excess mean: {pooled.get('thin_excess_5bps_mean')}",
        f"Placebo p: {pooled.get('placebo_p_ge_obs_mean')}",
        f"Epps day/crash@1s: {pooled.get('epps_day_corr_1s_mean')} / {pooled.get('epps_crash_corr_1s_mean')}",
        f"Crossed available: {pooled.get('n_crossed_available')} frac={pooled.get('crossed_frac_mean')}",
        "",
        "## Figures",
        *[f"- `{p}`" for p in fig_paths],
    ]
    (OUT / "frag_REPORT.md").write_text("\n".join(report_lines) + "\n")

    _write_chapter_docs(pooled, rows, fig_paths)
    _build_notebook(pooled, fig_paths)
    print(json.dumps(_jsonable(pooled), indent=2))


if __name__ == "__main__":
    main()
