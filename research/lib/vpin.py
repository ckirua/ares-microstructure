"""Volume-bucket VPIN / order-flow toxicity utilities.

Desk-usable wrappers around ``continuous.vpin_bucket`` with bucket series,
default volume sizing, and Pass-1 falsifiers (side shuffle, chronological split).

EHO PIN MLE lives in ``pin.py`` — different clock and identification.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from research.lib.continuous import vpin_bucket
from research.lib.stats import bootstrap_ci, spearman_r, time_split_mask


def default_bucket_volume(
    qty: NDArray[np.float64],
    *,
    multiplier: float = 50.0,
    floor: float = 1e-8,
) -> float:
    """Median print size × multiplier (empirical_mm / Ch.15 convention)."""
    q = np.asarray(qty, dtype=np.float64)
    q = q[np.isfinite(q) & (q > 0)]
    if q.size == 0:
        return float(floor)
    return float(max(np.nanmedian(q) * float(multiplier), floor))


def _iter_volume_buckets(
    side: NDArray[np.float64],
    qty: NDArray[np.float64],
    ts_ns: NDArray[np.int64] | None,
    *,
    bucket_volume: float,
) -> tuple[NDArray[np.float64], NDArray[np.int64]]:
    """Per-bucket imbalance and closing timestamp (last trade in bucket)."""
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
    imbalances: list[float] = []
    ends: list[int] = []
    buy_acc = sell_acc = 0.0
    vol_acc = 0.0
    for i in range(s.size):
        if s[i] > 0:
            buy_acc += float(q[i])
        else:
            sell_acc += float(q[i])
        vol_acc += float(q[i])
        if vol_acc >= bucket_volume:
            imbalances.append(abs(buy_acc - sell_acc) / vol_acc)
            ends.append(int(t[i]))
            buy_acc = sell_acc = vol_acc = 0.0
    return np.asarray(imbalances, dtype=np.float64), np.asarray(ends, dtype=np.int64)


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
    boots = []
    n = a.size
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boots.append(float(spearman_r(a[idx], b[idx])))
    ba = np.asarray(boots)
    ba = ba[np.isfinite(ba)]
    lo, hi = (
        (float(np.quantile(ba, 0.025)), float(np.quantile(ba, 0.975))) if ba.size else (float("nan"), float("nan"))
    )
    return {"n": float(a.size), "rho": point, "lo": lo, "hi": hi}
