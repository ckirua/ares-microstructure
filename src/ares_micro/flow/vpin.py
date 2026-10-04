"""Volume-bucket VPIN / order-flow toxicity utilities.

Equal-volume bucket VPIN, rolling series, default volume sizing, and Pass-1
falsifiers (side shuffle, chronological split).

EHO PIN MLE lives in ``pin.py`` — different clock and identification.

"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from ares_micro.stats import bootstrap_ci, spearman_r, time_split_mask


def default_bucket_volume(
    qty: NDArray[np.float64],
    *,
    multiplier: float | None = None,
    scale: float | None = None,
    floor: float = 1e-8,
) -> float:
    """Median print size × multiplier (empirical_mm / Ch.15 convention).

    ``scale`` is accepted as an alias for ``multiplier`` (book ``_data`` API).
    """
    mult = 50.0
    if multiplier is not None:
        mult = float(multiplier)
    elif scale is not None:
        mult = float(scale)
    q = np.asarray(qty, dtype=np.float64)
    q = q[np.isfinite(q) & (q > 0)]
    if q.size == 0:
        return float(floor)
    return float(max(np.nanmedian(q) * mult, floor))


def resolve_bucket_volume(
    qty: NDArray[np.float64],
    *,
    bucket_scale: float = 50.0,
    target_buckets: float | None = None,
    floor: float = 1e-8,
) -> tuple[float, str]:
    """Desk bucket sizing: Ch.15 median×scale (default) or total_vol/target_buckets.

    Returns ``(bucket_volume, method_tag)``. Target-bucket mode coarsens buckets
    (~50/day) so rolling VPIN levels sit in a comparable range across venues;
    median×50 is the repo SoT for cross-book parity with ``empirical_mm`` Ch.15.
    """
    q = np.asarray(qty, dtype=np.float64)
    qpos = q[np.isfinite(q) & (q > 0)]
    if target_buckets is not None and float(target_buckets) > 0 and qpos.size:
        total = float(np.nansum(qpos))
        if total > 0:
            return max(total / float(target_buckets), floor), "target_buckets"
    return float(default_bucket_volume(q, scale=bucket_scale, floor=floor)), "median_x_scale"


def rolling_vpin_series(
    side: NDArray[np.float64],
    qty: NDArray[np.float64],
    ts: NDArray[np.int64],
    *,
    bucket_volume: float,
    n_buckets_window: int = 50,
) -> tuple[NDArray[np.int64], NDArray[np.float64]]:
    """Return ``(bucket_end_ts_ns, rolling_vpin)`` for ex-ante event lookup."""
    s = np.asarray(side, dtype=np.float64)
    q = np.asarray(qty, dtype=np.float64)
    t = np.asarray(ts, dtype=np.int64)
    m = np.isfinite(s) & np.isfinite(q) & (q > 0) & (s != 0)
    s, q, t = s[m], q[m], t[m]
    if s.size < 50 or bucket_volume <= 0:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float64)
    imb, end_ts = _iter_volume_buckets(s, q, t, bucket_volume=float(bucket_volume))
    if imb.size < 5:
        return end_ts, np.full(end_ts.shape, np.nan, dtype=np.float64)
    w = min(int(n_buckets_window), int(imb.size))
    roll = np.full(imb.size, np.nan, dtype=np.float64)
    if w >= 1:
        roll[w - 1 :] = np.convolve(imb, np.ones(w, dtype=np.float64) / w, mode="valid")
    return end_ts, roll


def _iter_volume_buckets(
    side: NDArray[np.float64],
    qty: NDArray[np.float64],
    ts_ns: NDArray[np.int64] | None,
    *,
    bucket_volume: float,
) -> tuple[NDArray[np.float64], NDArray[np.int64]]:
    """Per-bucket imbalance and closing timestamp (last trade in bucket).

    Buckets reset when cumulative volume since the prior close reaches
    ``bucket_volume`` (overshoot stays in the closing bucket). Implemented via
    ``cumsum`` + ``searchsorted`` over bucket ends, not a per-trade Python loop.
    """
    s = np.asarray(side, dtype=np.float64)
    q = np.asarray(qty, dtype=np.float64)
    t = (
        np.asarray(ts_ns, dtype=np.int64)
        if ts_ns is not None
        else np.zeros(s.shape, dtype=np.int64)
    )
    m = np.isfinite(s) & np.isfinite(q) & (q > 0) & (s != 0)
    if ts_ns is not None:
        m &= np.isfinite(t)
    s, q, t = s[m], q[m], t[m]
    if s.size == 0 or bucket_volume <= 0:
        return np.zeros(0, dtype=np.float64), np.zeros(0, dtype=np.int64)
    c = np.cumsum(q)
    buy_c = np.cumsum(np.where(s > 0, q, 0.0))
    sell_c = np.cumsum(np.where(s < 0, q, 0.0))
    end_idx: list[int] = []
    base = 0.0
    n = int(s.size)
    while True:
        j = int(np.searchsorted(c, base + bucket_volume, side="left"))
        if j >= n:
            break
        end_idx.append(j)
        base = float(c[j])
    if not end_idx:
        return np.zeros(0, dtype=np.float64), np.zeros(0, dtype=np.int64)
    ends_i = np.asarray(end_idx, dtype=np.int64)
    prev = np.concatenate([[-1], ends_i[:-1]])
    # volume / buy / sell in (prev, ends_i]
    c_pad = np.concatenate([[0.0], c])
    b_pad = np.concatenate([[0.0], buy_c])
    s_pad = np.concatenate([[0.0], sell_c])
    vol = c_pad[ends_i + 1] - c_pad[prev + 1]
    buy = b_pad[ends_i + 1] - b_pad[prev + 1]
    sell = s_pad[ends_i + 1] - s_pad[prev + 1]
    imbalances = np.abs(buy - sell) / np.maximum(vol, 1e-18)
    return imbalances.astype(np.float64), t[ends_i].astype(np.int64)


def vpin_bucket(
    side: NDArray[np.float64],
    qty: NDArray[np.float64],
    *,
    bucket_volume: float,
    n_buckets_window: int = 50,
) -> dict[str, Any]:
    """Volume-synchronized VPIN-ish toxicity (continuous-flow analogue of PIN).

    |V_buy − V_sell| / V in equal-volume buckets; rolling mean over window.
    Not EHO PIN MLE — desk-usable intensity imbalance proxy.
    """
    s = np.asarray(side, dtype=np.float64)
    q = np.asarray(qty, dtype=np.float64)
    m = np.isfinite(s) & np.isfinite(q) & (q > 0) & (s != 0)
    if int(m.sum()) < 50 or bucket_volume <= 0:
        return {"n_buckets": 0, "mean_vpin": float("nan")}
    imb, _ = _iter_volume_buckets(s, q, None, bucket_volume=float(bucket_volume))
    if imb.size < 5:
        return {"n_buckets": int(imb.size), "mean_vpin": float("nan")}
    w = min(int(n_buckets_window), int(imb.size))
    roll = np.convolve(imb, np.ones(w, dtype=np.float64) / w, mode="valid")
    ci = bootstrap_ci(roll, n_boot=400, seed=43)
    return {
        "n_buckets": int(imb.size),
        "bucket_volume": float(bucket_volume),
        "mean_vpin": ci["point"],
        "vpin_ci95": [ci["lo"], ci["hi"]],
        "p50_vpin": float(np.median(roll)),
        "last_vpin": float(roll[-1]),
    }


def rolling_vpin(
    imbalances: NDArray[np.float64],
    *,
    n_buckets_window: int = 50,
) -> NDArray[np.float64]:
    """Rolling mean of bucket imbalances (VPIN-style)."""
    imb = np.asarray(imbalances, dtype=np.float64)
    imb = imb[np.isfinite(imb)]
    if imb.size == 0:
        return np.zeros(0, dtype=np.float64)
    w = min(int(n_buckets_window), int(imb.size))
    if w < 1:
        return np.zeros(0, dtype=np.float64)
    return np.convolve(imb, np.ones(w, dtype=np.float64) / w, mode="valid")


def vpin_from_tape(
    side: NDArray[np.float64],
    qty: NDArray[np.float64],
    ts_ns: NDArray[np.int64] | None = None,
    *,
    bucket_volume: float | None = None,
    multiplier: float = 50.0,
    n_buckets_window: int = 50,
) -> dict[str, Any]:
    """Full day (or tape window) VPIN summary + rolling series for falsifiers."""
    q = np.asarray(qty, dtype=np.float64)
    bv = float(bucket_volume) if bucket_volume is not None else default_bucket_volume(q, multiplier=multiplier)
    imb, ends = _iter_volume_buckets(side, q, ts_ns, bucket_volume=bv)
    roll = rolling_vpin(imb, n_buckets_window=n_buckets_window)
    base = vpin_bucket(side, q, bucket_volume=bv, n_buckets_window=n_buckets_window)
    total_vol = float(np.nansum(q[np.isfinite(q) & (q > 0)]))
    out: dict[str, Any] = {
        **base,
        "bucket_volume": bv,
        "total_volume": total_vol,
        "n_trades": int(np.sum(np.isfinite(side) & (side != 0))),
        "imbalance_series": imb,
        "roll_series": roll,
        "bucket_end_ts": ends,
    }
    if roll.size >= 4:
        med_roll = float(np.median(roll))
        ci_roll = bootstrap_ci(roll, stat=np.median, n_boot=400, seed=44)
        out["p50_roll_vpin"] = med_roll
        out["p50_roll_ci95"] = [ci_roll["lo"], ci_roll["hi"]]
    else:
        out["p50_roll_vpin"] = float("nan")
        out["p50_roll_ci95"] = [float("nan"), float("nan")]
    return out


def vpin_time_split(
    roll: NDArray[np.float64],
    bucket_end_ts: NDArray[np.int64] | None = None,
    *,
    train_frac: float = 0.5,
) -> dict[str, Any]:
    """Chronological early/late split on rolling VPIN (in-bucket clock)."""
    r = np.asarray(roll, dtype=np.float64)
    r = r[np.isfinite(r)]
    if r.size < 8:
        return {"ok": False, "n": int(r.size), "reason": "short_roll"}
    if bucket_end_ts is not None and bucket_end_ts.size >= r.size + 1:
        # roll[i] aligns with bucket window ending near index i + window - 1
        ts = np.asarray(bucket_end_ts, dtype=np.int64)
        ts = ts[np.isfinite(ts)]
        if ts.size >= r.size:
            ts_r = ts[-r.size :]
            tr, te = time_split_mask(ts_r, train_frac=train_frac)
        else:
            n = r.size
            cut = int(n * train_frac)
            tr = np.zeros(n, dtype=bool)
            tr[:cut] = True
            te = ~tr
    else:
        n = r.size
        cut = max(1, int(n * train_frac))
        tr = np.zeros(n, dtype=bool)
        tr[:cut] = True
        te = np.zeros(n, dtype=bool)
        te[cut:] = True
    early, late = r[tr], r[te]
    if early.size < 3 or late.size < 3:
        return {"ok": False, "n": int(r.size), "reason": "split_thin"}
    ce = bootstrap_ci(early, n_boot=400, seed=51)
    cl = bootstrap_ci(late, n_boot=400, seed=52)
    return {
        "ok": True,
        "n": int(r.size),
        "early_mean": ce["point"],
        "early_ci95": [ce["lo"], ce["hi"]],
        "late_mean": cl["point"],
        "late_ci95": [cl["lo"], cl["hi"]],
        "delta": float(ce["point"] - cl["point"]),
        "train_frac": float(train_frac),
    }


def falsify_side_shuffle(
    side: NDArray[np.float64],
    qty: NDArray[np.float64],
    *,
    bucket_volume: float,
    n_buckets_window: int = 50,
    n_shuffle: int = 200,
    seed: int = 17,
) -> dict[str, Any]:
    """Permute trade signs — real bucket imbalance should exceed null if signed flow."""
    s = np.asarray(side, dtype=np.float64)
    q = np.asarray(qty, dtype=np.float64)
    m = np.isfinite(s) & np.isfinite(q) & (q > 0) & (s != 0)
    s, q = s[m], q[m]
    if s.size < 50:
        return {"ok": False, "n_trades": int(s.size), "reason": "short_tape"}
    real = vpin_bucket(s, q, bucket_volume=bucket_volume, n_buckets_window=n_buckets_window)
    obs = float(real.get("mean_vpin", float("nan")))
    rng = np.random.default_rng(seed)
    null: list[float] = []
    for _ in range(n_shuffle):
        sp = s * rng.choice([-1.0, 1.0], size=s.size)
        v = vpin_bucket(sp, q, bucket_volume=bucket_volume, n_buckets_window=n_buckets_window)
        mv = float(v.get("mean_vpin", float("nan")))
        if np.isfinite(mv):
            null.append(mv)
    na = np.asarray(null, dtype=np.float64)
    na = na[np.isfinite(na)]
    p_exceed = float(np.mean(na >= obs)) if na.size and np.isfinite(obs) else float("nan")
    return {
        "ok": bool(np.isfinite(obs) and na.size >= 20),
        "obs_mean_vpin": obs,
        "null_median": float(np.median(na)) if na.size else float("nan"),
        "null_p95": float(np.quantile(na, 0.95)) if na.size else float("nan"),
        "p_exceed": p_exceed,
        "n_shuffle": int(n_shuffle),
        "n_null_finite": int(na.size),
        "real_n_buckets": int(real.get("n_buckets", 0)),
    }


def summarize_panel_vpin(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate ok panel rows: medians + bootstrap CIs for desk JSON."""
    ok = [r for r in rows if r.get("ok")]
    if not ok:
        return {"n_ok": 0}
    mv = np.array([r["mean_vpin"] for r in ok], dtype=np.float64)
    nb = np.array([r["n_buckets"] for r in ok], dtype=np.float64)
    cov = np.array([r.get("coverage", float("nan")) for r in ok], dtype=np.float64)
    mv = mv[np.isfinite(mv)]
    nb = nb[np.isfinite(nb)]
    out: dict[str, Any] = {
        "n_ok": len(ok),
        "mean_vpin": bootstrap_ci(mv, stat=np.median, n_boot=800, seed=61) if mv.size else {},
        "n_buckets": bootstrap_ci(nb, stat=np.median, n_boot=800, seed=62) if nb.size else {},
        "coverage": bootstrap_ci(cov[np.isfinite(cov)], stat=np.median, n_boot=800, seed=63)
        if np.isfinite(cov).any()
        else {},
    }
    return out


def cross_section_spearman(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    *,
    n_boot: int = 800,
    seed: int = 7,
) -> dict[str, float]:
    """Spearman with bootstrap CI (panel rows)."""
    a = np.asarray(x, dtype=np.float64)
    b = np.asarray(y, dtype=np.float64)
    m = np.isfinite(a) & np.isfinite(b)
    a, b = a[m], b[m]
    if a.size < 5:
        return {"n": float(a.size), "rho": float("nan"), "lo": float("nan"), "hi": float("nan")}
    rng = np.random.default_rng(seed)
    point = float(spearman_r(a, b))
    n = a.size
    idx = rng.integers(0, n, size=(n_boot, n))
    # Rank within each bootstrap row, then Pearson on ranks.
    aa = a[idx]
    bb = b[idx]
    ra = np.argsort(np.argsort(aa, axis=1), axis=1).astype(np.float64)
    rb = np.argsort(np.argsort(bb, axis=1), axis=1).astype(np.float64)
    ra -= ra.mean(axis=1, keepdims=True)
    rb -= rb.mean(axis=1, keepdims=True)
    den = np.sqrt((ra * ra).sum(axis=1) * (rb * rb).sum(axis=1))
    num = (ra * rb).sum(axis=1)
    ba = np.where(den > 0, num / den, np.nan)
    ba = ba[np.isfinite(ba)]
    lo, hi = (
        (float(np.quantile(ba, 0.025)), float(np.quantile(ba, 0.975))) if ba.size else (float("nan"), float("nan"))
    )
    return {"n": float(a.size), "rho": point, "lo": lo, "hi": hi}
