from __future__ import annotations
#!/usr/bin/env python3
"""Phase 2 vertical slice: crash_baselines + mc_garch_vol + kalman_ssm.

Pass 1: Nanex / outside-TOB / V-shape / MC-GARCH / SSM-z=6 on HL+Deribit+Kraken
        ETH+BTC complete UTC days.
Pass 2: overlap vs SSM, VPIN/OFI/markout around events, z*∈[2,12] scan,
        σ_m frac stress, diurnal crash intensity, innovation/gain lead-lag.

ClickHouse MCP banned. Data via warehouse + optional collector TOB.
"""

import os

import argparse
import json
import sys
from datetime import datetime, timezone
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
    asof_mid,
    day_bounds_ns,
    ensure_env,
    load_day_trades,
    load_venue_tob,
    normalize_side,
    venue_instrument,
)
from research.lib.continuous import ofi_continuous, trade_intensity, vpin_bucket  # noqa: E402
from research.lib.crash import (  # noqa: E402
    detect_ssm_events,
    diurnal_sj,
    event_overlap,
    kalman_ssm_filter,
    mc_garch_bar_vol,
    nanex_detect,
    outside_tob_flags,
    recovery_fraction,
    sigma_process_meas,
    vshape_events,
    zstar_scan,
)
from research.lib.markout import trade_markouts  # noqa: E402

OUT = BOOK / "out" / "phase2_baselines_ssm"
FIG = OUT / "figs"

# Intersection listing-cache days for HL∩Deribit∩Kraken (verified probe)
DEFAULT_DAYS = [
    "2026-09-04",
    "2026-09-05",
    "2026-09-06",
    "2026-09-07",
    "2026-09-08",
    "2026-09-09",
]
DEFAULT_SYMBOLS = ["ETH", "BTC"]
Z_STAR_DEFAULT = 6.0
SIGMA_M_FRACS = [0.5, 1.0, 2.0, 4.0]
# Paper Nanex 0.8% rarely fires on crypto ms tape — also report 30/50 bps ablations
NANEX_PCTS = (0.008, 0.005, 0.003)


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


def _try_warehouse_tob(venue: str, symbol: str, day: str, *, max_files: int = 8) -> dict[str, Any] | None:
    """Prefer warehouse quote stream; fall back to collector TOB."""
    try:
        from startarb.data.bbo_stream import load_quote_stream

        inst = venue_instrument(symbol, venue)
        # HL flat-era: opaque id required for trade; quotes may use catalog
        qs = load_quote_stream(
            venue,
            inst,
            [day],
            max_files=max_files,
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
            return None
        bsz = np.asarray(getattr(qs, "bid_sz", np.ones(ts.size)), dtype=np.float64)
        asz = np.asarray(getattr(qs, "ask_sz", np.ones(ts.size)), dtype=np.float64)
        return {
            "ts": ts[m],
            "bid": bid[m],
            "ask": ask[m],
            "mid": 0.5 * (bid[m] + ask[m]),
            "bid_sz": bsz[m] if bsz.size == ts.size else np.ones(int(m.sum())),
            "ask_sz": asz[m] if asz.size == ts.size else np.ones(int(m.sum())),
            "source": "warehouse_quote_stream",
            "n": int(m.sum()),
        }
    except Exception as exc:  # noqa: BLE001
        # collector fallback (often only recent days)
        try:
            tob = load_venue_tob(venue, symbol, max_day_dirs=4, max_rows=200_000)
            return {**tob, "source": "collector", "n": int(tob["ts"].size), "error_wh": str(exc)}
        except Exception as exc2:  # noqa: BLE001
            return {"error": f"wh:{type(exc).__name__}:{exc}; col:{type(exc2).__name__}:{exc2}", "n": 0}


def _signed_imbalance(side: np.ndarray, qty: np.ndarray, window: int = 50) -> np.ndarray:
    """Rolling buy−sell qty imbalance / volume (tape OFI proxy)."""
    s = normalize_side(side)
    q = np.asarray(qty, dtype=np.float64)
    signed = s * q
    # cumulative then window diff
    c = np.cumsum(signed)
    v = np.cumsum(np.abs(q))
    out = np.full(s.shape, np.nan)
    for i in range(s.size):
        j = max(0, i - window + 1)
        num = c[i] - (c[j - 1] if j > 0 else 0.0)
        den = v[i] - (v[j - 1] if j > 0 else 0.0)
        out[i] = num / den if den > 0 else np.nan
    return out


def _event_window_tox(
    ts: np.ndarray,
    side: np.ndarray,
    qty: np.ndarray,
    px: np.ndarray,
    starts: np.ndarray,
    ends: np.ndarray,
    tob: dict[str, Any] | None,
    *,
    pre_s: float = 5.0,
    post_s: float = 5.0,
) -> dict[str, Any]:
    """VPIN-ish + signed imbalance + optional markout around events."""
    if starts.size == 0:
        return {"n_events": 0}
    imb = _signed_imbalance(side, qty, window=40)
    pre_imb, post_imb, concurrent = [], [], []
    mark_1s = []
    for a, b in zip(starts.tolist(), ends.tolist()):
        a, b = int(a), int(b)
        t0, t1 = int(ts[a]), int(ts[b])
        pre_lo = t0 - int(pre_s * 1e9)
        post_hi = t1 + int(post_s * 1e9)
        pre_m = (ts >= pre_lo) & (ts < t0)
        con_m = (ts >= t0) & (ts <= t1)
        post_m = (ts > t1) & (ts <= post_hi)
        if pre_m.any():
            pre_imb.append(float(np.nanmean(np.abs(imb[pre_m]))))
        if con_m.any():
            concurrent.append(float(np.nanmean(np.abs(imb[con_m]))))
        if post_m.any():
            post_imb.append(float(np.nanmean(np.abs(imb[post_m]))))
    # VPIN on whole day + event-local bucket volume
    side_n = normalize_side(side)
    med_q = float(np.median(qty[qty > 0])) if (qty > 0).any() else 1.0
    vpin = vpin_bucket(side_n, qty, bucket_volume=max(50.0 * med_q, 1e-6), n_buckets_window=30)
    intensity = trade_intensity(ts, bar_ns=1_000_000_000)
    out: dict[str, Any] = {
        "n_events": int(starts.size),
        "pre_abs_imb_mean": float(np.mean(pre_imb)) if pre_imb else None,
        "concurrent_abs_imb_mean": float(np.mean(concurrent)) if concurrent else None,
        "post_abs_imb_mean": float(np.mean(post_imb)) if post_imb else None,
        "vpin_day": vpin,
        "intensity": intensity,
    }
    if tob and tob.get("n", 0) and tob.get("ts") is not None:
        try:
            mo = trade_markouts(
                ts,
                px,
                side_n,
                tob["ts"],
                tob["mid"],
                horizons_ms=(500, 1000, 5000),
            )
            out["markout_day"] = {
                h: mo["by_horizon"][h] for h in mo["by_horizon"] if h in ("500", "1000", "5000")
            }
            # Cont OFI if sizes present
            if "bid_sz" in tob and "ask_sz" in tob:
                ofi = ofi_continuous(
                    tob["ts"], tob["bid"], tob["ask"], tob["bid_sz"], tob["ask_sz"], bar_ns=1_000_000_000
                )
                out["ofi"] = {k: ofi.get(k) for k in ("n", "corr_ofi_ret", "beta_ofi")}
        except Exception as exc:  # noqa: BLE001
            out["markout_error"] = f"{type(exc).__name__}: {exc}"
    return out


def _lead_lag_innov(
    ts: np.ndarray,
    innov: np.ndarray,
    px: np.ndarray,
    mid: np.ndarray | None,
    *,
    lags_s: tuple[float, ...] = (-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0),
) -> dict[str, Any]:
    """Corr(innovation_t, future mid/trade return) as continuous info probe."""
    logp = np.log(np.asarray(px, dtype=np.float64))
    inn = np.asarray(innov, dtype=np.float64)
    m = np.isfinite(inn) & np.isfinite(logp)
    if mid is not None and np.isfinite(mid).sum() > 100:
        # use mid path asof
        ref = np.log(np.where(np.asarray(mid) > 0, mid, np.nan))
    else:
        ref = logp
    m &= np.isfinite(ref)
    idx = np.flatnonzero(m)
    if idx.size < 200:
        return {"n": int(idx.size), "rows": []}
    t = ts[m]
    x = inn[m]
    r0 = ref[m]
    rows = []
    for lag in lags_s:
        # lag>0: return after innovation; lag<0: return before
        shift_ns = int(lag * 1e9)
        # approximate with index shift using searchsorted
        tgt = t + shift_ns
        j = np.searchsorted(t, tgt, side="left")
        valid = (j >= 0) & (j < t.size) & (j != np.arange(t.size))
        # for lag≈0 use next print
        if abs(lag) < 1e-9:
            j = np.arange(t.size) + 1
            valid = j < t.size
        rr = np.full(t.size, np.nan)
        ok = valid & (j < t.size)
        rr[ok] = r0[j[ok]] - r0[np.arange(t.size)[ok]]
        mm = np.isfinite(rr) & np.isfinite(x)
        if int(mm.sum()) < 50:
            rows.append({"lag_s": lag, "corr": None, "n": int(mm.sum())})
            continue
        a, b = x[mm] - x[mm].mean(), rr[mm] - rr[mm].mean()
        den = float(np.sqrt((a * a).sum() * (b * b).sum()))
        corr = float((a * b).sum() / den) if den > 0 else None
        rows.append({"lag_s": float(lag), "corr": corr, "n": int(mm.sum())})
    return {"n": int(idx.size), "rows": rows}


def _placebo_rate(mask: np.ndarray, n_perm: int = 40, seed: int = 7) -> dict[str, Any]:
    """Shuffle crash-flag run starts in time; compare count distribution."""
    rng = np.random.default_rng(seed)
    m = np.asarray(mask, dtype=bool)
    n_flags = int(m.sum())
    if m.size < 100 or n_flags == 0:
        return {"n_flags": n_flags, "placebo_mean": None, "p_exceed": None}
    counts = []
    for _ in range(n_perm):
        # random contiguous blocks of same total length
        perm = rng.permutation(m.size)
        counts.append(int(m[perm].sum()))  # same by construction — use block shift
    # better: circular shift
    counts = []
    for _ in range(n_perm):
        shift = int(rng.integers(1, max(m.size - 1, 2)))
        counts.append(int(np.roll(m, shift).sum()))
    # flag count invariant under roll — use event-rate of random thresholds on z
    return {
        "n_flags": n_flags,
        "note": "flag_count_shift_invariant; use z-path placebo in caller",
    }


def _z_placebo(
    z_score: NDArray[np.float64],
    z_star: float,
    *,
    n_perm: int = 50,
    seed: int = 11,
) -> dict[str, Any]:
    """Placebo: circular-shift the z path (keeps dependence) vs iid shuffle.

    Flag-*count* is shuffle-invariant; we compare **event run counts** after
    circular shifts of the z series (null: no time localization).
    """
    rng = np.random.default_rng(seed)
    z = np.asarray(z_score, dtype=np.float64)
    m = np.isfinite(z)
    if int(m.sum()) < 100:
        return {"obs_events": 0, "placebo_mean_events": None, "p_ge_obs": None}

    def _n_runs(zz: np.ndarray) -> int:
        mask = np.isfinite(zz) & (np.abs(zz) >= z_star)
        if not mask.any():
            return 0
        d = np.diff(mask.astype(np.int8), prepend=0, append=0)
        return int((d == 1).sum())

    obs = _n_runs(z)
    # circular shifts of finite segment
    vals = z.copy()
    placebo = []
    for _ in range(n_perm):
        shift = int(rng.integers(1, max(vals.size - 1, 2)))
        placebo.append(_n_runs(np.roll(vals, shift)))
    arr = np.asarray(placebo, dtype=np.float64)
    return {
        "obs_events": obs,
        "placebo_mean_events": float(arr.mean()),
        "placebo_p95_events": float(np.percentile(arr, 95)),
        "p_ge_obs": float((arr >= obs).mean()),
        "n_perm": n_perm,
        "note": "circular_shift_preserves_marginal; tests time-localization weakly",
    }


def run_one(
    venue: str,
    symbol: str,
    day: str,
    *,
    sigma_m_frac: float = 1.0,
    max_files: int = 24,
    skip_tob: bool = False,
) -> dict[str, Any]:
    rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
    tape = rec["tape"]
    comp = rec["completeness"]
    ts = np.asarray(tape["ts"], dtype=np.int64)
    px = np.asarray(tape["px"], dtype=np.float64)
    qty = np.asarray(tape["qty"], dtype=np.float64)
    side = np.asarray(tape["side"], dtype=np.float64)
    out: dict[str, Any] = {
        "venue": venue,
        "symbol": symbol,
        "day": day,
        "instrument": rec.get("instrument"),
        "completeness": comp,
        "n_trades": int(ts.size),
    }
    if ts.size < 200 or not np.isfinite(px).any():
        out["skip"] = "thin_tape"
        return out

    log_px = np.log(np.where(px > 0, px, np.nan))

    # --- Pass 1 baselines ---
    nanex = nanex_detect(ts, px, min_trades=10, max_window_s=1.5, min_pct=0.008, use_trade_count=True)
    nanex_50bps = nanex_detect(ts, px, min_trades=10, max_window_s=1.5, min_pct=0.005, use_trade_count=True)
    nanex_30bps = nanex_detect(ts, px, min_trades=10, max_window_s=1.5, min_pct=0.003, use_trade_count=True)
    nanex_20bps = nanex_detect(ts, px, min_trades=8, max_window_s=1.5, min_pct=0.002, use_trade_count=True)
    nanex_tight = nanex_detect(ts, px, min_trades=10, max_window_s=0.5, min_pct=0.003, use_trade_count=True)
    # primary crypto Nanex for overlap = 30 bps (paper 80 bps almost never fires)
    nanex_primary = nanex_30bps
    vshape = vshape_events(ts, px, min_pct=0.003, max_leg_s=1.5, min_recovery=0.5)

    tob = None if skip_tob else _try_warehouse_tob(venue, symbol, day)
    outside = {"n_outside": 0, "n_tob": 0}
    if tob and tob.get("n", 0):
        outside = outside_tob_flags(ts, px, tob["ts"], tob["bid"], tob["ask"])
        out["tob_source"] = tob.get("source")
        out["tob_n"] = int(tob.get("n", 0))
    else:
        out["tob_error"] = (tob or {}).get("error", "no_tob")

    # --- MC-GARCH + SSM ---
    mcg = mc_garch_bar_vol(ts, px)
    sig = sigma_process_meas(ts, mcg, sigma_m_frac=sigma_m_frac, log_px=log_px)
    filt = kalman_ssm_filter(ts, px, sig["sigma_p2_dt"], sig["sigma_m2"])
    ssm = detect_ssm_events(ts, px, filt, z_star=Z_STAR_DEFAULT)
    recov = recovery_fraction(
        ts, px, ssm["start_i"], ssm["end_i"], ssm["direction"], horizon_s=5.0
    )

    # overlaps (crypto Nanex 50bps primary)
    ov_nanex = event_overlap(
        nanex_primary["start_i"],
        nanex_primary["end_i"],
        ssm["start_i"],
        ssm["end_i"],
        ts,
        slack_s=0.25,
    )
    ov_vshape = event_overlap(
        vshape["start_i"], vshape["end_i"], ssm["start_i"], ssm["end_i"], ts, slack_s=0.25
    )

    # z* scan
    zscan = zstar_scan(filt["z_score"], ts, px)

    # σ_m frac stress (crash counts at z=6)
    sigma_stress = []
    for frac in SIGMA_M_FRACS:
        sig_f = sigma_process_meas(ts, mcg, sigma_m_frac=frac, log_px=log_px)
        filt_f = kalman_ssm_filter(ts, px, sig_f["sigma_p2_dt"], sig_f["sigma_m2"])
        zf = filt_f["z_score"]
        mf = np.isfinite(zf)
        ssm_f = detect_ssm_events(ts, px, filt_f, z_star=Z_STAR_DEFAULT)
        sigma_stress.append(
            {
                "sigma_m_frac": frac,
                "n_ssm": int(ssm_f["n_events"]),
                "n_flags": int((np.abs(zf[mf]) >= Z_STAR_DEFAULT).sum()) if mf.any() else 0,
                "median_dp": float(np.nanmedian(ssm_f["dp_pct"])) if ssm_f["n_events"] else None,
                "noise_ref": float(sig_f.get("noise_ref", float("nan"))),
            }
        )

    # time-split (early/late half of day by trade index)
    mid_i = ts.size // 2

    def _half_counts(sl: slice) -> dict[str, int]:
        ts_h, px_h = ts[sl], px[sl]
        if ts_h.size < 100:
            return {"nanex": 0, "ssm": 0}
        n1 = nanex_detect(ts_h, px_h, min_pct=0.003)["n_events"]
        mcg_h = mc_garch_bar_vol(ts_h, px_h)
        lp_h = np.log(np.where(px_h > 0, px_h, np.nan))
        sig_h = sigma_process_meas(ts_h, mcg_h, sigma_m_frac=sigma_m_frac, log_px=lp_h)
        f_h = kalman_ssm_filter(ts_h, px_h, sig_h["sigma_p2_dt"], sig_h["sigma_m2"])
        n2 = detect_ssm_events(ts_h, px_h, f_h, z_star=Z_STAR_DEFAULT)["n_events"]
        return {"nanex": int(n1), "ssm": int(n2)}

    time_split = {"early": _half_counts(slice(0, mid_i)), "late": _half_counts(slice(mid_i, None))}

    # diurnal crash intensity (SSM event starts by UTC 5m slot)
    n_slots = 288
    slot_counts = np.zeros(n_slots, dtype=np.float64)
    if ssm["n_events"]:
        slots = ((ssm["ts_start"] % (86_400 * 1_000_000_000)) // (5 * 60 * 1_000_000_000)).astype(np.int64)
        for s in slots:
            if 0 <= s < n_slots:
                slot_counts[s] += 1.0

    # Pass 2 toxicity around Nanex + SSM
    tox_nanex = _event_window_tox(
        ts, side, qty, px, nanex_primary["start_i"], nanex_primary["end_i"], tob
    )
    tox_ssm = _event_window_tox(ts, side, qty, px, ssm["start_i"], ssm["end_i"], tob)

    mid_asof = None
    if tob and tob.get("n", 0):
        mid_asof = asof_mid(ts, tob["ts"], tob["mid"])
    leadlag = _lead_lag_innov(ts, filt["innov"], px, mid_asof)
    placebo = _z_placebo(filt["z_score"], Z_STAR_DEFAULT)

    # volume curve hourly (link vol.curve_intraday)
    hour = ((ts // 1_000_000_000) % 86_400) // 3600
    notional = px * qty
    hour_share = np.zeros(24, dtype=np.float64)
    for h in range(24):
        hour_share[h] = float(notional[hour == h].sum())
    if hour_share.sum() > 0:
        hour_share = hour_share / hour_share.sum()

    out.update(
        {
            "nanex_n_paper80bps": int(nanex["n_events"]),
            "nanex_n_50bps": int(nanex_50bps["n_events"]),
            "nanex_n": int(nanex_primary["n_events"]),  # 30 bps crypto primary
            "nanex_n_20bps": int(nanex_20bps["n_events"]),
            "nanex_n_30bps": int(nanex_30bps["n_events"]),
            "nanex_tight_n": int(nanex_tight["n_events"]),
            "vshape_n": int(vshape["n_events"]),
            "outside_n": int(outside.get("n_outside", 0)),
            "outside_tob_n": int(outside.get("n_tob", 0)),
            "ssm_n": int(ssm["n_events"]),
            "ssm_median_dp": float(np.nanmedian(ssm["dp_pct"])) if ssm["n_events"] else None,
            "ssm_median_ic": float(np.nanmedian(ssm["i_c"])) if ssm["n_events"] else None,
            "ssm_median_dt": float(np.nanmedian(ssm["dt_s"])) if ssm["n_events"] else None,
            "ssm_median_recovery_5s": float(np.nanmedian(recov)) if ssm["n_events"] else None,
            "overlap_nanex_ssm": ov_nanex,
            "overlap_vshape_ssm": ov_vshape,
            "mcg_n_bars": int(mcg["n_bars"]),
            "diurnal_s": mcg["s"].tolist() if isinstance(mcg.get("s"), np.ndarray) else None,
            "hour_share": hour_share.tolist(),
            "zstar_scan": zscan["rows"],
            "sigma_stress": sigma_stress,
            "time_split": time_split,
            "slot_crash_counts": slot_counts.tolist(),
            "tox_nanex": tox_nanex,
            "tox_ssm": tox_ssm,
            "leadlag_innov": leadlag,
            "placebo_z": placebo,
            "sigma_m_frac": sigma_m_frac,
            "noise_ref": float(sig.get("noise_ref", float("nan"))),
            "kappa_mean": float(np.nanmean(filt["kappa"])),
            "innov_std": float(np.nanstd(filt["innov"])),
            "z_abs_p99": float(np.nanpercentile(np.abs(filt["z_score"][np.isfinite(filt["z_score"])]), 99))
            if np.isfinite(filt["z_score"]).any()
            else None,
        }
    )
    out["_events"] = {
        "ssm_ts_start": ssm["ts_start"].tolist() if ssm["n_events"] else [],
        "ssm_ts_end": ssm["ts_end"].tolist() if ssm["n_events"] else [],
        "nanex_ts_start": [int(ts[i]) for i in nanex_primary["start_i"]]
        if nanex_primary["n_events"]
        else [],
        "vshape_ts_start": [int(ts[i]) for i in vshape["start_i"]] if vshape["n_events"] else [],
    }
    return out


def _pool_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_venue: dict[str, dict[str, float]] = {}
    for r in rows:
        if r.get("skip"):
            continue
        v = r["venue"]
        d = by_venue.setdefault(
            v,
            {
                "nanex": 0,
                "ssm": 0,
                "vshape": 0,
                "outside": 0,
                "days": 0,
                "complete_days": 0,
                "trades": 0,
            },
        )
        d["nanex"] += r.get("nanex_n") or 0
        d["ssm"] += r.get("ssm_n") or 0
        d["vshape"] += r.get("vshape_n") or 0
        d["outside"] += r.get("outside_n") or 0
        d["days"] += 1
        d["complete_days"] += 1 if r.get("completeness", {}).get("complete") else 0
        d["trades"] += r.get("n_trades") or 0
    return by_venue


def make_plots(summary: dict[str, Any]) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIGS: list[str] = []
    FIG.mkdir(parents=True, exist_ok=True)

    # 1. Nanex vs SSM by venue
    byv = summary["counts_by_venue"]
    venues = list(byv.keys())
    if venues:
        x = np.arange(len(venues))
        w = 0.35
        fig, ax = plt.subplots(figsize=(7.2, 4.2))
        ax.bar(x - w / 2, [byv[v]["nanex"] for v in venues], w, label="Nanex")
        ax.bar(x + w / 2, [byv[v]["ssm"] for v in venues], w, label="SSM z*=6")
        ax.set_xticks(x)
        ax.set_xticklabels(venues)
        ax.set_ylabel("event count (pooled days)")
        ax.set_title("Nanex vs SSM crash counts by venue")
        ax.legend()
        p = FIG / "fig_nanex_vs_ssm_venue.png"
        _save_fig(p)
        FIGS.append(str(p.relative_to(OUT)))

    # 2. z* scan pooled
    zscan = summary.get("zstar_pooled")
    if zscan:
        zs = [r["z_star"] for r in zscan]
        ns = [r["n_events"] for r in zscan]
        fig, ax = plt.subplots(figsize=(7.2, 4.2))
        ax.plot(zs, ns, "o-", lw=1.5)
        ax.axvline(6, color="C3", ls="--", label="z*=6")
        ax.set_xlabel("z*")
        ax.set_ylabel("pooled SSM events")
        ax.set_title("Table III analogue: crash count vs z*")
        ax.legend()
        p = FIG / "fig_zstar_scan.png"
        _save_fig(p)
        FIGS.append(str(p.relative_to(OUT)))

    # 3. diurnal s_j vs crash slots
    sj = summary.get("diurnal_s_mean")
    slots = summary.get("slot_crash_mean")
    if sj and slots:
        fig, ax1 = plt.subplots(figsize=(8.5, 4.0))
        t = np.arange(len(sj)) * 5 / 60.0
        ax1.plot(t, sj, color="C0", alpha=0.85, label="diurnal s_j")
        ax1.set_xlabel("UTC hour")
        ax1.set_ylabel("s_j", color="C0")
        ax2 = ax1.twinx()
        # smooth crash slots
        sc = np.asarray(slots, dtype=np.float64)
        if sc.size == len(sj):
            ax2.fill_between(t, sc, color="C3", alpha=0.35, label="SSM crash starts")
        ax2.set_ylabel("crash starts / day-slot", color="C3")
        ax1.set_title("UTC diurnal s_j vs SSM crash intensity")
        p = FIG / "fig_diurnal_vs_crashes.png"
        _save_fig(p)
        FIGS.append(str(p.relative_to(OUT)))

    # 4. sigma_m frac stress
    stress = summary.get("sigma_stress_pooled")
    if stress:
        fig, ax = plt.subplots(figsize=(6.5, 4.0))
        fr = [r["sigma_m_frac"] for r in stress]
        ns = [r["n_ssm"] for r in stress]
        ax.plot(fr, ns, "s-", color="C2")
        ax.set_xlabel(r"$\sigma_m / \sigma_p$ fraction")
        ax.set_ylabel("pooled SSM events @ z*=6")
        ax.set_title(r"$\sigma_m$ calibration stress")
        p = FIG / "fig_sigma_m_stress.png"
        _save_fig(p)
        FIGS.append(str(p.relative_to(OUT)))

    # 5. lead-lag innov
    ll = summary.get("leadlag_pooled")
    if ll:
        fig, ax = plt.subplots(figsize=(6.5, 4.0))
        lags = [r["lag_s"] for r in ll]
        corrs = [r["corr"] if r["corr"] is not None else np.nan for r in ll]
        ax.plot(lags, corrs, "o-")
        ax.axhline(0, color="k", lw=0.8)
        ax.set_xlabel("lag (s) of return vs innovation (+ = future return)")
        ax.set_ylabel("corr(innov, Δlog)")
        ax.set_title("SSM innovation lead–lag vs price")
        p = FIG / "fig_innov_leadlag.png"
        _save_fig(p)
        FIGS.append(str(p.relative_to(OUT)))

    # 6. hour share (vol.curve_intraday link)
    hs = summary.get("hour_share_mean")
    if hs:
        fig, ax = plt.subplots(figsize=(7.5, 3.8))
        ax.bar(np.arange(24), hs, color="steelblue", alpha=0.85)
        ax.set_xlabel("UTC hour")
        ax.set_ylabel("notional share")
        ax.set_title("Intraday notional curve (link mmip vol.curve_intraday)")
        p = FIG / "fig_hour_share.png"
        _save_fig(p)
        FIGS.append(str(p.relative_to(OUT)))

    # 7. overlap Jaccard heatmap-ish table as bars
    ov = summary.get("overlap_pooled")
    if ov:
        fig, ax = plt.subplots(figsize=(6.5, 4.0))
        labels = list(ov.keys())
        jacs = [ov[k].get("jaccard") or 0 for k in labels]
        ax.bar(labels, jacs, color="C4")
        ax.set_ylabel("Jaccard")
        ax.set_title("Baseline overlap vs SSM (pooled)")
        ax.set_ylim(0, max(0.2, max(jacs) * 1.2 if jacs else 0.2))
        p = FIG / "fig_overlap_jaccard.png"
        _save_fig(p)
        FIGS.append(str(p.relative_to(OUT)))

    return FIGS


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", nargs="*", default=DEFAULT_DAYS)
    ap.add_argument("--symbols", nargs="*", default=DEFAULT_SYMBOLS)
    ap.add_argument("--venues", nargs="*", default=list(CORE_VENUES))
    ap.add_argument("--sigma-m-frac", type=float, default=1.0)
    ap.add_argument("--max-files", type=int, default=24)
    ap.add_argument("--skip-tob", action="store_true")
    ap.add_argument("--complete-only", action="store_true", default=True)
    ap.add_argument("--allow-incomplete", action="store_false", dest="complete_only")
    args = ap.parse_args()

    ensure_env()
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for sym in args.symbols:
        for day in args.days:
            for venue in args.venues:
                print(f"[run] {venue} {sym} {day}", flush=True)
                try:
                    r = run_one(
                        venue,
                        sym,
                        day,
                        sigma_m_frac=args.sigma_m_frac,
                        max_files=args.max_files,
                        skip_tob=args.skip_tob,
                    )
                except Exception as exc:  # noqa: BLE001
                    r = {
                        "venue": venue,
                        "symbol": sym,
                        "day": day,
                        "error": f"{type(exc).__name__}: {exc}",
                        "skip": "error",
                    }
                if args.complete_only and not r.get("completeness", {}).get("complete"):
                    if not r.get("skip"):
                        r["skip"] = "incomplete"
                    r["excluded_from_pool"] = True
                rows.append(r)
                print(
                    f"  -> nanex={r.get('nanex_n')} ssm={r.get('ssm_n')} "
                    f"complete={r.get('completeness', {}).get('complete')} skip={r.get('skip')}",
                    flush=True,
                )

    pooled = [r for r in rows if not r.get("excluded_from_pool") and not r.get("skip")]
    # if nothing complete, fall back to all non-error
    if not pooled:
        pooled = [r for r in rows if not r.get("skip") or r.get("skip") == "incomplete"]
        for r in pooled:
            r["excluded_from_pool"] = False

    counts = _pool_counts(pooled)

    # pool z* scan (sum events)
    z_map: dict[float, dict[str, float]] = {}
    for r in pooled:
        for row in r.get("zstar_scan") or []:
            z = float(row["z_star"])
            d = z_map.setdefault(z, {"z_star": z, "n_events": 0, "n_flags": 0})
            d["n_events"] += int(row.get("n_events") or 0)
            d["n_flags"] += int(row.get("n_flags") or 0)
    zstar_pooled = [z_map[z] for z in sorted(z_map)]

    # sigma stress pool
    s_map: dict[float, dict[str, float]] = {}
    for r in pooled:
        for row in r.get("sigma_stress") or []:
            f = float(row["sigma_m_frac"])
            d = s_map.setdefault(f, {"sigma_m_frac": f, "n_ssm": 0})
            d["n_ssm"] += int(row.get("n_ssm") or 0)
    sigma_stress_pooled = [s_map[f] for f in sorted(s_map)]

    # diurnal averages
    sj_acc = []
    slot_acc = []
    hs_acc = []
    for r in pooled:
        if r.get("diurnal_s"):
            sj_acc.append(np.asarray(r["diurnal_s"], dtype=np.float64))
        if r.get("slot_crash_counts"):
            slot_acc.append(np.asarray(r["slot_crash_counts"], dtype=np.float64))
        if r.get("hour_share"):
            hs_acc.append(np.asarray(r["hour_share"], dtype=np.float64))

    # overlap pool (sum n_a,n_b,n_overlap)
    def _ov_pool(key: str) -> dict[str, float]:
        na = nb = nov = 0.0
        for r in pooled:
            o = r.get(key) or {}
            na += float(o.get("n_a") or 0)
            nb += float(o.get("n_b") or 0)
            nov += float(o.get("n_overlap") or 0)
        union = na + nb - nov
        return {
            "n_a": na,
            "n_b": nb,
            "n_overlap": nov,
            "jaccard": (nov / union) if union else None,
            "precision_a": (nov / na) if na else None,
            "recall_a": (nov / nb) if nb else None,
        }

    # leadlag: average corrs
    ll_map: dict[float, list[float]] = {}
    for r in pooled:
        for row in (r.get("leadlag_innov") or {}).get("rows") or []:
            if row.get("corr") is None:
                continue
            ll_map.setdefault(float(row["lag_s"]), []).append(float(row["corr"]))
    leadlag_pooled = [
        {"lag_s": lag, "corr": float(np.mean(vs)), "n_series": len(vs)}
        for lag, vs in sorted(ll_map.items())
    ]

    # tox summary
    tox_summary = {
        "nanex_pre_imb": [],
        "nanex_con_imb": [],
        "ssm_pre_imb": [],
        "ssm_con_imb": [],
        "vpin_means": [],
    }
    for r in pooled:
        tn = r.get("tox_nanex") or {}
        ts_ = r.get("tox_ssm") or {}
        if tn.get("pre_abs_imb_mean") is not None:
            tox_summary["nanex_pre_imb"].append(tn["pre_abs_imb_mean"])
        if tn.get("concurrent_abs_imb_mean") is not None:
            tox_summary["nanex_con_imb"].append(tn["concurrent_abs_imb_mean"])
        if ts_.get("pre_abs_imb_mean") is not None:
            tox_summary["ssm_pre_imb"].append(ts_["pre_abs_imb_mean"])
        if ts_.get("concurrent_abs_imb_mean") is not None:
            tox_summary["ssm_con_imb"].append(ts_["concurrent_abs_imb_mean"])
        vp = (tn.get("vpin_day") or {}).get("mean_vpin")
        if vp is not None and np.isfinite(vp):
            tox_summary["vpin_means"].append(float(vp))

    # placebo pooled
    placebo_rows = [r.get("placebo_z") for r in pooled if r.get("placebo_z")]
    # time-split
    early_ssm = sum((r.get("time_split") or {}).get("early", {}).get("ssm", 0) for r in pooled)
    late_ssm = sum((r.get("time_split") or {}).get("late", {}).get("ssm", 0) for r in pooled)
    early_nx = sum((r.get("time_split") or {}).get("early", {}).get("nanex", 0) for r in pooled)
    late_nx = sum((r.get("time_split") or {}).get("late", {}).get("nanex", 0) for r in pooled)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days": args.days,
        "symbols": args.symbols,
        "venues": args.venues,
        "sigma_m_frac": args.sigma_m_frac,
        "n_rows": len(rows),
        "n_pooled": len(pooled),
        "counts_by_venue": counts,
        "counts_total": {
            "nanex": sum(v["nanex"] for v in counts.values()),
            "ssm": sum(v["ssm"] for v in counts.values()),
            "vshape": sum(v["vshape"] for v in counts.values()),
            "outside": sum(v["outside"] for v in counts.values()),
        },
        "zstar_pooled": zstar_pooled,
        "sigma_stress_pooled": sigma_stress_pooled,
        "diurnal_s_mean": (np.mean(np.stack(sj_acc), axis=0).tolist() if sj_acc else None),
        "slot_crash_mean": (np.mean(np.stack(slot_acc), axis=0).tolist() if slot_acc else None),
        "hour_share_mean": (np.mean(np.stack(hs_acc), axis=0).tolist() if hs_acc else None),
        "overlap_pooled": {
            "nanex_vs_ssm": _ov_pool("overlap_nanex_ssm"),
            "vshape_vs_ssm": _ov_pool("overlap_vshape_ssm"),
        },
        "leadlag_pooled": leadlag_pooled,
        "tox_summary": {
            "nanex_pre_abs_imb_mean": float(np.mean(tox_summary["nanex_pre_imb"]))
            if tox_summary["nanex_pre_imb"]
            else None,
            "nanex_con_abs_imb_mean": float(np.mean(tox_summary["nanex_con_imb"]))
            if tox_summary["nanex_con_imb"]
            else None,
            "ssm_pre_abs_imb_mean": float(np.mean(tox_summary["ssm_pre_imb"]))
            if tox_summary["ssm_pre_imb"]
            else None,
            "ssm_con_abs_imb_mean": float(np.mean(tox_summary["ssm_con_imb"]))
            if tox_summary["ssm_con_imb"]
            else None,
            "vpin_day_mean": float(np.mean(tox_summary["vpin_means"]))
            if tox_summary["vpin_means"]
            else None,
        },
        "time_split_pooled": {
            "early_nanex": early_nx,
            "late_nanex": late_nx,
            "early_ssm": early_ssm,
            "late_ssm": late_ssm,
        },
        "placebo_sample": placebo_rows[:8],
        "hour_peak_utc": int(np.argmax(np.mean(np.stack(hs_acc), axis=0))) if hs_acc else None,
    }

    figs = make_plots(summary)
    summary["figures"] = figs

    # strip heavy _events before write
    rows_light = []
    for r in rows:
        rr = {k: v for k, v in r.items() if k != "_events"}
        rows_light.append(_jsonable(rr))

    (OUT / "phase2_rows.json").write_text(json.dumps(rows_light, indent=2))
    (OUT / "phase2_summary.json").write_text(json.dumps(_jsonable(summary), indent=2))

    # short markdown report
    lines = [
        "# Phase 2 baselines–SSM summary",
        "",
        f"Generated: {summary['generated_at']}",
        f"Days: {args.days}",
        f"Symbols: {args.symbols} · Venues: {args.venues}",
        f"Pooled day×venue×symbol cells: **{summary['n_pooled']}** / {summary['n_rows']}",
        "",
        "## Crash counts (Nanex vs SSM z*=6)",
        "",
        "| Venue | Nanex | SSM | V-shape | Outside-TOB | Complete cells |",
        "|-------|------:|----:|--------:|------------:|---------------:|",
    ]
    for v, d in counts.items():
        lines.append(
            f"| {v} | {int(d['nanex'])} | {int(d['ssm'])} | {int(d['vshape'])} | "
            f"{int(d['outside'])} | {int(d['complete_days'])}/{int(d['days'])} |"
        )
    ct = summary["counts_total"]
    lines += [
        f"| **TOTAL** | **{ct['nanex']}** | **{ct['ssm']}** | **{ct['vshape']}** | **{ct['outside']}** | — |",
        "",
        f"Overlap Nanex↔SSM Jaccard={summary['overlap_pooled']['nanex_vs_ssm'].get('jaccard')}",
        f"Overlap Vshape↔SSM Jaccard={summary['overlap_pooled']['vshape_vs_ssm'].get('jaccard')}",
        f"Time-split SSM early/late={early_ssm}/{late_ssm}; Nanex={early_nx}/{late_nx}",
        f"Hour peak UTC={summary.get('hour_peak_utc')}",
        "",
        "## Figures",
        "",
    ]
    for f in figs:
        lines.append(f"- `{f}`")
    (OUT / "phase2_REPORT.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(_jsonable(summary["counts_by_venue"]), indent=2))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
