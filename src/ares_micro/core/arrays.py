"""Generic array/time helpers (ns day bounds, asof join, side normalize)."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
from numpy.typing import NDArray

from ares_micro.core.constants import NS_PER_S


def day_bounds_ns(day: str) -> tuple[int, int]:
    """UTC day ``YYYY-MM-DD`` → ``[start_ns, end_ns)``."""
    t0 = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    start = int(t0.timestamp() * NS_PER_S)
    return start, start + 86_400 * NS_PER_S


def normalize_side(side: NDArray[np.floating] | NDArray[np.integer] | np.ndarray) -> NDArray[np.float64]:
    """Map ``{0,1}`` aggressor codes to ±1; leave already-signed sides unchanged."""
    s = np.asarray(side, dtype=np.float64)
    uniq = set(np.unique(s[np.isfinite(s)]).tolist())
    if uniq <= {0.0, 1.0} or uniq <= {0, 1}:
        return np.where(s > 0, 1.0, -1.0)
    return s


def asof_join(
    ts_query_ns: NDArray[np.integer] | np.ndarray,
    ts_ref_ns: NDArray[np.integer] | np.ndarray,
    values: NDArray[np.floating] | np.ndarray,
    *,
    max_lag_ns: int | None = None,
    sort_ref: bool = False,
) -> NDArray[np.float64]:
    """Backward asof join of ``values`` onto ``ts_query_ns`` (NumPy searchsorted)."""
    tq = np.asarray(ts_query_ns, dtype=np.int64)
    tm = np.asarray(ts_ref_ns, dtype=np.int64)
    m = np.asarray(values, dtype=np.float64)
    out = np.full(tq.shape, np.nan, dtype=np.float64)
    if tq.size == 0 or tm.size == 0 or m.size == 0:
        return out
    if sort_ref:
        order = np.argsort(tm, kind="mergesort")
        tm, m = tm[order], m[order]
    idx = np.searchsorted(tm, tq, side="right") - 1
    valid = (idx >= 0) & (idx < tm.size) & (idx < m.size)
    if max_lag_ns is not None:
        lag = np.zeros_like(tq)
        lag[valid] = tq[valid] - tm[idx[valid]]
        valid = valid & (lag <= int(max_lag_ns))
    out[valid] = m[idx[valid]]
    return out


def asof_idx(
    query_ts: NDArray[np.integer] | np.ndarray,
    ref_ts: NDArray[np.integer] | np.ndarray,
) -> NDArray[np.int64]:
    """Largest ref index with ``ref_ts[i] <= query`` (searchsorted right − 1)."""
    q = np.asarray(query_ts, dtype=np.int64)
    r = np.asarray(ref_ts, dtype=np.int64)
    return np.searchsorted(r, q, side="right").astype(np.int64) - 1


def consecutive_log_returns(levels: NDArray[np.floating] | np.ndarray) -> NDArray[np.float64]:
    """``log(x[i]/x[i-1])`` when both finite and prior > 0; else NaN (same length)."""
    x = np.asarray(levels, dtype=np.float64)
    out = np.full(x.shape, np.nan, dtype=np.float64)
    if x.size < 2:
        return out
    prev, cur = x[:-1], x[1:]
    ok = np.isfinite(prev) & np.isfinite(cur) & (prev > 0) & (cur > 0)
    ratio = np.full(cur.shape, np.nan, dtype=np.float64)
    ratio[ok] = np.log(cur[ok] / prev[ok])
    out[1:] = ratio
    return out


def log_returns_on_grid(
    ts_ns: NDArray[np.integer] | np.ndarray,
    px: NDArray[np.floating] | np.ndarray,
    grid_ns: NDArray[np.integer] | np.ndarray,
) -> NDArray[np.float64]:
    """Last-price asof onto ``grid_ns``, then consecutive log returns."""
    last = asof_join(grid_ns, ts_ns, px)
    return consecutive_log_returns(last)


def forward_fill(values: NDArray[np.floating] | np.ndarray) -> NDArray[np.float64]:
    """Forward-fill finite values; leading NaNs preserved."""
    a = np.asarray(values, dtype=np.float64)
    if a.size == 0:
        return a.copy()
    mask = np.isfinite(a)
    if not mask.any():
        return a.copy()
    idx = np.where(mask, np.arange(a.size), 0)
    np.maximum.accumulate(idx, out=idx)
    out = a[idx]
    if not mask[0]:
        first = int(np.argmax(mask))
        out = out.copy()
        out[:first] = np.nan
    return out


def interval_overlap(
    a_start: NDArray[np.integer] | np.ndarray,
    a_end: NDArray[np.integer] | np.ndarray,
    b_start: NDArray[np.integer] | np.ndarray,
    b_end: NDArray[np.integer] | np.ndarray,
    *,
    slack: int = 0,
) -> dict[str, float]:
    """Greedy one-to-one overlap of closed intervals ``[start, end]``.

    Matching is greedy in ``a`` order (first unmatched ``b`` that overlaps
    within ``slack``). Returns counts plus Jaccard / precision / recall of ``a``.
    """
    a0 = np.asarray(a_start, dtype=np.int64)
    a1 = np.asarray(a_end, dtype=np.int64)
    b0 = np.asarray(b_start, dtype=np.int64)
    b1 = np.asarray(b_end, dtype=np.int64)
    slack_i = int(slack)
    n_a, n_b = int(a0.size), int(b0.size)
    if n_a == 0 or n_b == 0:
        return {
            "n_a": float(n_a),
            "n_b": float(n_b),
            "n_overlap": 0.0,
            "jaccard": float("nan"),
            "precision_a": float("nan"),
            "recall_a": float("nan"),
        }
    matched_a = np.zeros(n_a, dtype=bool)
    matched_b = np.zeros(n_b, dtype=bool)
    for i in range(n_a):
        for j in range(n_b):
            if matched_b[j]:
                continue
            if int(a0[i]) <= int(b1[j]) + slack_i and int(b0[j]) <= int(a1[i]) + slack_i:
                matched_a[i] = True
                matched_b[j] = True
                break
    n_ov = int(matched_a.sum())
    union = n_a + n_b - n_ov
    return {
        "n_a": float(n_a),
        "n_b": float(n_b),
        "n_overlap": float(n_ov),
        "jaccard": float(n_ov / union) if union else float("nan"),
        "precision_a": float(n_ov / n_a) if n_a else float("nan"),
        "recall_a": float(n_ov / n_b) if n_b else float("nan"),
    }
