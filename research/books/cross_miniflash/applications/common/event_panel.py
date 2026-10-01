"""Build gated SSM event panels for MM / feature applications.

Reuses ``research.lib.crash`` + book ``scripts/_data`` loaders.
ClickHouse MCP banned — warehouse/tape only.
"""


from __future__ import annotations

import os

import sys
from pathlib import Path
from typing import Any

import numpy as np

BOOK = Path(__file__).resolve().parents[2]
ROOT = BOOK.parents[2]
STARTARB = Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb'))
WAREHOUSE_SRC = Path(os.environ.get('WAREHOUSE_SRC') or ((Path(os.environ.get('WAREHOUSE_ROOT') or (Path.home() / 'lab' / 'lab-n2070' / 'warehouse')) / 'src')))
SCRIPTS = BOOK / "scripts"

for p in (str(ROOT), str(STARTARB / "src"), str(WAREHOUSE_SRC), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from _data import (  # noqa: E402
    CORE_VENUES,
    ensure_env,
    load_day_trades,
    load_venue_tob,
    normalize_side,
    venue_instrument,
)
from research.lib.continuous import (  # noqa: E402
    amihud_illiquidity,
    trade_intensity,
    vpin_bucket,
)
from research.lib.crash import (  # noqa: E402
    classify_recovery,
    detect_ssm_events,
    kalman_ssm_filter,
    mc_garch_bar_vol,
    post_event_markout_px,
    recovery_fraction,
    severity_gate,
    sigma_process_meas,
    volume_herfindahl,
)
from research.lib.stats import bootstrap_ci  # noqa: E402

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
GATE_PRIMARY = {"min_dp_pct": 0.10, "min_i_c": 5}
RECOVERY_H_S = 5.0
NS_PER_S = 1_000_000_000
EARLY_DAYS = {"2026-09-04", "2026-09-05", "2026-09-06"}
LATE_DAYS = {"2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10"}


def jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        if obj.dtype == object:
            return [jsonable(x) for x in obj.tolist()]
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


def summarize(arr: np.ndarray) -> dict[str, float]:
    a = np.asarray(arr, dtype=np.float64)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return {
            "n": 0,
            "mean": float("nan"),
            "median": float("nan"),
            "sd": float("nan"),
            "p25": float("nan"),
            "p75": float("nan"),
        }
    return {
        "n": int(a.size),
        "mean": float(a.mean()),
        "median": float(np.median(a)),
        "sd": float(a.std(ddof=1)) if a.size > 1 else 0.0,
        "p25": float(np.percentile(a, 25)),
        "p75": float(np.percentile(a, 75)),
    }


def try_tob(venue: str, symbol: str, day: str) -> dict[str, Any] | None:
    try:
        from startarb.data.bbo_stream import load_quote_stream

        inst = venue_instrument(symbol, venue)
        qs = load_quote_stream(
            venue,
            inst,
            [day],
            max_files=6,
            prefer_shards=True,
            quotes_per_minute=30,
            quiet=True,
            allow_trade_fallback=False,
        )
        ts = np.asarray(qs.ts_ns, dtype=np.int64)
        bid = np.asarray(qs.bid, dtype=np.float64)
        ask = np.asarray(qs.ask, dtype=np.float64)
        mid = 0.5 * (bid + ask)
        depth = np.asarray(qs.bid_sz, dtype=np.float64) + np.asarray(qs.ask_sz, dtype=np.float64)
        return {
            "ts": ts,
            "mid": mid,
            "bid": bid,
            "ask": ask,
            "bid_sz": np.asarray(qs.bid_sz, dtype=np.float64),
            "ask_sz": np.asarray(qs.ask_sz, dtype=np.float64),
            "depth": depth,
            "n": int(ts.size),
            "source": "warehouse_bbo",
        }
    except Exception:
        try:
            tob = load_venue_tob(venue, symbol, max_day_dirs=4, max_rows=150_000)
            return {
                "ts": tob["ts"],
                "mid": tob["mid"],
                "bid": tob["bid"],
                "ask": tob["ask"],
                "bid_sz": tob["bid_sz"],
                "ask_sz": tob["ask_sz"],
                "depth": tob["bid_sz"] + tob["ask_sz"],
                "n": int(tob["ts"].size),
                "source": "collector",
            }
        except Exception:
            return None


def asof_lookup(query_ts: np.ndarray, ref_ts: np.ndarray, values: np.ndarray) -> np.ndarray:
    i0 = np.searchsorted(ref_ts, query_ts, side="right") - 1
    out = np.full(query_ts.shape, np.nan, dtype=np.float64)
    valid = (i0 >= 0) & (i0 < ref_ts.size)
    out[valid] = values[i0[valid]]
    return out


def rolling_vpin_series(
    side: np.ndarray,
    qty: np.ndarray,
    ts: np.ndarray,
    *,
    bucket_volume: float,
    n_buckets_window: int = 30,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (bucket_end_ts, rolling_vpin) for ex-ante lookup."""
    s = np.asarray(side, dtype=np.float64)
    q = np.asarray(qty, dtype=np.float64)
    t = np.asarray(ts, dtype=np.int64)
    m = np.isfinite(s) & np.isfinite(q) & (q > 0) & (s != 0)
    s, q, t = s[m], q[m], t[m]
    if s.size < 50 or bucket_volume <= 0:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float64)
    buy_acc = sell_acc = vol_acc = 0.0
    end_ts: list[int] = []
    imb: list[float] = []
    for i in range(s.size):
        if s[i] > 0:
            buy_acc += q[i]
        else:
            sell_acc += q[i]
        vol_acc += q[i]
        if vol_acc >= bucket_volume:
            imb.append(abs(buy_acc - sell_acc) / vol_acc)
            end_ts.append(int(t[i]))
            buy_acc = sell_acc = vol_acc = 0.0
    imb_a = np.asarray(imb, dtype=np.float64)
    if imb_a.size < 5:
        return np.asarray(end_ts, dtype=np.int64), np.full(len(end_ts), np.nan)
    w = min(n_buckets_window, imb_a.size)
    roll = np.full(imb_a.size, np.nan, dtype=np.float64)
    csum = np.cumsum(imb_a)
    for i in range(w - 1, imb_a.size):
        lo = i - w
        roll[i] = (csum[i] - (csum[lo] if lo >= 0 else 0.0)) / w
    return np.asarray(end_ts, dtype=np.int64), roll


def prewindow_features(
    ts: np.ndarray,
    px: np.ndarray,
    qty: np.ndarray,
    side: np.ndarray,
    event_start_i: int,
    *,
    pre_s: float = 60.0,
    vpin_ts: np.ndarray | None = None,
    vpin_roll: np.ndarray | None = None,
) -> dict[str, float]:
    """Ex-ante features in (t0 − pre_s, t0) — no leakage into event."""
    a = int(event_start_i)
    if a <= 1:
        return {
            "intensity": float("nan"),
            "rv_1m": float("nan"),
            "amihud": float("nan"),
            "vpin_exante": float("nan"),
            "log_notional_pre": float("nan"),
            "hour_utc": float("nan"),
            "n_pre": 0,
        }
    t0 = int(ts[a])
    t_lo = t0 - int(pre_s * NS_PER_S)
    lo = int(np.searchsorted(ts, t_lo, side="left"))
    hi = a  # exclusive of event start
    if hi - lo < 5:
        return {
            "intensity": float("nan"),
            "rv_1m": float("nan"),
            "amihud": float("nan"),
            "vpin_exante": float("nan"),
            "log_notional_pre": float("nan"),
            "hour_utc": float((t0 / NS_PER_S) % 86400) / 3600.0,
            "n_pre": int(max(hi - lo, 0)),
        }
    ts_w, px_w, qty_w, side_w = ts[lo:hi], px[lo:hi], qty[lo:hi], side[lo:hi]
    span_s = max((ts_w[-1] - ts_w[0]) / NS_PER_S, 1e-6)
    intensity = float(ts_w.size / span_s)
    notional = px_w * qty_w
    # 1s RV in window
    bar_ns = NS_PER_S
    t_base = int(ts_w[0] // bar_ns * bar_ns)
    bucket = (ts_w - t_base) // bar_ns
    last_px, last_not = [], []
    for b in np.unique(bucket):
        m = bucket == b
        pp = px_w[m]
        nn = notional[m]
        if (pp > 0).any():
            last_px.append(float(pp[pp > 0][-1]))
            last_not.append(float(np.nansum(nn)))
    last_px_a = np.asarray(last_px, dtype=np.float64)
    last_not_a = np.asarray(last_not, dtype=np.float64)
    if last_px_a.size >= 3:
        r = np.diff(np.log(last_px_a))
        rv = float(np.sqrt(np.nansum(r**2)))
        am = amihud_illiquidity(r, last_not_a[1:])
        amihud = float(am.get("illiq", float("nan")))
    else:
        rv, amihud = float("nan"), float("nan")
    vpin_ex = float("nan")
    if vpin_ts is not None and vpin_roll is not None and vpin_ts.size:
        # last completed bucket strictly before event
        j = int(np.searchsorted(vpin_ts, t0, side="left") - 1)
        if j >= 0:
            vpin_ex = float(vpin_roll[j])
    return {
        "intensity": intensity,
        "rv_1m": rv,
        "amihud": amihud,
        "vpin_exante": vpin_ex,
        "log_notional_pre": float(np.log(max(float(np.nansum(notional)), 1.0))),
        "hour_utc": float((t0 / NS_PER_S) % 86400) / 3600.0,
        "n_pre": int(hi - lo),
    }


def mid_path_after(
    ts: np.ndarray,
    px: np.ndarray,
    end_i: int,
    *,
    horizons_s: tuple[float, ...] = (0.5, 1.0, 2.0, 5.0, 10.0),
    mid_ts: np.ndarray | None = None,
    mid: np.ndarray | None = None,
) -> dict[str, float]:
    """Tape and optional mid markout path after event end (unsigned Δp/p in bps)."""
    b = int(end_i)
    out: dict[str, float] = {}
    if b < 0 or b >= px.size or px[b] <= 0:
        for h in horizons_s:
            out[f"tape_{h}s_bps"] = float("nan")
            out[f"mid_{h}s_bps"] = float("nan")
        return out
    p0 = float(px[b])
    t0 = int(ts[b])
    for h in horizons_s:
        t_lim = t0 + int(h * NS_PER_S)
        j = int(np.searchsorted(ts, t_lim, side="right") - 1)
        if j > b and j < px.size and np.isfinite(px[j]) and px[j] > 0:
            out[f"tape_{h}s_bps"] = float(1e4 * (px[j] - p0) / p0)
        else:
            out[f"tape_{h}s_bps"] = float("nan")
        if mid_ts is not None and mid is not None and mid_ts.size:
            m0 = asof_lookup(np.array([t0]), mid_ts, mid)[0]
            m1 = asof_lookup(np.array([t_lim]), mid_ts, mid)[0]
            if np.isfinite(m0) and np.isfinite(m1) and m0 > 0:
                out[f"mid_{h}s_bps"] = float(1e4 * (m1 - m0) / m0)
            else:
                out[f"mid_{h}s_bps"] = float("nan")
        else:
            out[f"mid_{h}s_bps"] = float("nan")
    return out


def process_cell(
    venue: str,
    symbol: str,
    day: str,
    *,
    max_files: int = 24,
    pre_s: float = 60.0,
) -> dict[str, Any] | None:
    """One venue×symbol×day: gated SSM events + features + paths."""
    rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
    flags = rec["completeness"]
    if not flags.get("complete"):
        return {
            "venue": venue,
            "symbol": symbol,
            "day": day,
            "complete": False,
            "skip": flags.get("reasons"),
            "n_trades": flags.get("n", 0),
            "events": [],
        }
    tape = rec["tape"]
    ts = np.asarray(tape["ts"], dtype=np.int64)
    px = np.asarray(tape["px"], dtype=np.float64)
    qty = np.asarray(tape["qty"], dtype=np.float64)
    side = normalize_side(tape["side"])
    m = np.isfinite(px) & (px > 0) & np.isfinite(ts)
    ts, px, qty, side = ts[m], px[m], qty[m], side[m]
    if ts.size < 500:
        return {
            "venue": venue,
            "symbol": symbol,
            "day": day,
            "complete": False,
            "skip": ["n_after_clean<500"],
            "n_trades": int(ts.size),
            "events": [],
        }

    comp = mc_garch_bar_vol(ts, px)
    log_px = np.log(px)
    sig = sigma_process_meas(ts, comp, sigma_m_frac=1.0, log_px=log_px)
    filt = kalman_ssm_filter(ts, px, sig["sigma_p2_dt"], sig["sigma_m2"])
    ssm_raw = detect_ssm_events(ts, px, filt, z_star=Z_STAR)
    gated = severity_gate(ssm_raw, **GATE_PRIMARY)

    med_q = float(np.median(qty[qty > 0])) if (qty > 0).any() else 1.0
    bucket_vol = max(50.0 * med_q, 1e-6)
    vpin_ts, vpin_roll = rolling_vpin_series(side, qty, ts, bucket_volume=bucket_vol)
    day_vpin = vpin_bucket(side, qty, bucket_volume=bucket_vol, n_buckets_window=30)
    intens = trade_intensity(ts, bar_ns=NS_PER_S)

    tob = try_tob(venue, symbol, day)
    mid_ts = tob["ts"] if tob else None
    mid = tob["mid"] if tob else None

    day_notional = float(np.nansum(px * qty))
    events: list[dict[str, Any]] = []
    n = int(gated.get("n_events", 0))
    if n > 0:
        recov = recovery_fraction(
            ts, px, gated["start_i"], gated["end_i"], gated["direction"], horizon_s=RECOVERY_H_S
        )
        cls = classify_recovery(recov)
        mo = post_event_markout_px(ts, px, gated["end_i"], gated["direction"])
        # per-event markouts for dense analysis
        for k in range(n):
            a, b = int(gated["start_i"][k]), int(gated["end_i"][k])
            pre = prewindow_features(
                ts, px, qty, side, a, pre_s=pre_s, vpin_ts=vpin_ts, vpin_roll=vpin_roll
            )
            path = mid_path_after(ts, px, b, mid_ts=mid_ts, mid=mid)
            # trade-count / volume-clock duration
            i_c = int(gated["i_c"][k])
            dt_s = float(gated["dt_s"][k])
            vol_clock = float(np.nansum(qty[a : b + 1]))
            # signed markouts at horizons (keys: mo_0.5s / mo_1s / mo_5s)
            signed_mo: dict[str, float] = {}
            d = int(gated["direction"][k])
            h_keys = [(0.5, "0.5"), (1.0, "1"), (5.0, "5")]
            for h, tag in h_keys:
                key = f"tape_{h}s_bps"
                if key in path and np.isfinite(path[key]) and d != 0:
                    signed_mo[f"mo_{tag}s"] = float(d * path[key])
                else:
                    signed_mo[f"mo_{tag}s"] = float("nan")
                mk = f"mid_{h}s_bps"
                if mk in path and np.isfinite(path[mk]) and d != 0:
                    signed_mo[f"mid_mo_{tag}s"] = float(d * path[mk])
                else:
                    signed_mo[f"mid_mo_{tag}s"] = float("nan")
            # early recovery confirm at +1s / +2s for policy
            rec_1 = recovery_fraction(
                ts,
                px,
                np.array([a]),
                np.array([b]),
                np.array([d]),
                horizon_s=1.0,
            )[0]
            rec_2 = recovery_fraction(
                ts,
                px,
                np.array([a]),
                np.array([b]),
                np.array([d]),
                horizon_s=2.0,
            )[0]
            events.append(
                {
                    "venue": venue,
                    "symbol": symbol,
                    "day": day,
                    "cohort": "early" if day in EARLY_DAYS else "late",
                    "start_i": a,
                    "end_i": b,
                    "ts_start": int(gated["ts_start"][k]),
                    "ts_end": int(gated["ts_end"][k]),
                    "dp_pct": float(gated["dp_pct"][k]),
                    "i_c": i_c,
                    "dt_s": dt_s,
                    "vol_clock": vol_clock,
                    "direction": d,
                    "z_peak": float(gated["z_peak"][k]) if np.isfinite(gated["z_peak"][k]) else float("nan"),
                    "recovery_5s": float(recov[k]) if np.isfinite(recov[k]) else float("nan"),
                    "recovery_1s": float(rec_1) if np.isfinite(rec_1) else float("nan"),
                    "recovery_2s": float(rec_2) if np.isfinite(rec_2) else float("nan"),
                    "label": str(cls["labels"][k]),
                    "log_notional_event": float(np.log(max(float(np.nansum(px[a : b + 1] * qty[a : b + 1])), 1.0))),
                    "day_log_notional": float(np.log(max(day_notional, 1.0))),
                    "day_vpin": float(day_vpin.get("mean_vpin", float("nan"))),
                    "day_intensity": float(intens.get("mean_lambda", float("nan"))),
                    **pre,
                    **path,
                    **signed_mo,
                }
            )

    return {
        "venue": venue,
        "symbol": symbol,
        "day": day,
        "complete": True,
        "n_trades": int(ts.size),
        "n_ssm_raw": int(ssm_raw["n_events"]),
        "n_gated": n,
        "day_notional": day_notional,
        "day_vpin": float(day_vpin.get("mean_vpin", float("nan"))),
        "day_intensity": float(intens.get("mean_lambda", float("nan"))),
        "tob_n": int(tob["n"]) if tob else 0,
        "tob_source": tob["source"] if tob else None,
        "events": events,
        # keep tape for intra-cell sims if needed (heavy) — omit by default
    }


def build_panel(
    *,
    days: list[str] | None = None,
    symbols: list[str] | None = None,
    venues: tuple[str, ...] = CORE_VENUES,
    max_files: int = 24,
    include_sol: bool = False,
) -> dict[str, Any]:
    """Full multi-venue panel of gated events + cell metadata."""
    ensure_env()
    days = list(days or DEFAULT_DAYS)
    symbols = list(symbols or DEFAULT_SYMBOLS)
    if include_sol and "SOL" not in symbols:
        symbols = symbols + ["SOL"]

    cells: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for day in days:
        # cross-venue H^v for the day (per symbol)
        for sym in symbols:
            vols: dict[str, float] = {}
            day_cells: list[dict[str, Any]] = []
            for v in venues:
                try:
                    cell = process_cell(v, sym, day, max_files=max_files)
                except Exception as exc:  # noqa: BLE001
                    cell = {
                        "venue": v,
                        "symbol": sym,
                        "day": day,
                        "complete": False,
                        "skip": [f"{type(exc).__name__}: {exc}"],
                        "events": [],
                        "n_trades": 0,
                    }
                day_cells.append(cell)
                if cell.get("complete") and cell.get("day_notional"):
                    vols[v] = float(cell["day_notional"])
            hv = volume_herfindahl(vols, keys=list(venues))
            for cell in day_cells:
                cell["H_v"] = hv.get("H_v")
                cell["H_v_complete"] = hv.get("complete")
                cell["vol_shares"] = hv.get("shares")
                for ev in cell.get("events") or []:
                    ev["H_v"] = hv.get("H_v")
                    ev["H_v_complete"] = bool(hv.get("complete"))
                    events.append(ev)
                cells.append({k: v for k, v in cell.items() if k != "events"})

    n_complete = sum(1 for c in cells if c.get("complete"))
    return {
        "days": days,
        "symbols": symbols,
        "venues": list(venues),
        "n_cells": len(cells),
        "n_complete": n_complete,
        "n_events": len(events),
        "cells": cells,
        "events": events,
        "gate": dict(GATE_PRIMARY),
        "z_star": Z_STAR,
        "recovery_h_s": RECOVERY_H_S,
    }


def event_arrays(events: list[dict[str, Any]], key: str) -> np.ndarray:
    return np.asarray([e.get(key, np.nan) for e in events], dtype=np.float64)


def boot_mean(arr: np.ndarray, *, seed: int = 0) -> dict[str, float]:
    return bootstrap_ci(arr, n_boot=800, seed=seed)
