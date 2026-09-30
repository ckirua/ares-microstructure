r"""Mini flash-crash detectors and event features (Tee & Ting 2019).

Implements Nanex-style baselines, Kalman state-space detection, MC-GARCH
variance feed helpers, event feature extractors, and \(z^*\)-scan utilities for
``research/books/cross_miniflash/``.

Clock defaults follow the paper on equities; crypto adaptations (UTC diurnal,
trade-count primary vs tick-count) are explicit kwargs — callers must state
which clock they used in EXP_REPORT.

Public surface::

    nanex_detect, outside_tob_flags, vshape_events
    diurnal_sj, garch11_forecast, mc_garch_bar_vol, sigma_process_meas
    kalman_ssm_filter, ssm_crash_mask, detect_ssm_events
    extract_event_features, severity_gate, recovery_fraction
    classify_recovery, post_event_markout_px
    zstar_scan, event_overlap, xvenue_event_concordance
    volume_herfindahl
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

NS_PER_S = 1_000_000_000


# ---------------------------------------------------------------------------
# Nanex / baseline detectors
# ---------------------------------------------------------------------------


def _infer_tick_size(px: NDArray[np.float64], *, fallback: float = 1e-8) -> float:
    """Median positive consecutive |Δp| as tick proxy (desk fallback, not exchange tick)."""
    p = np.asarray(px, dtype=np.float64)
    if p.size < 3:
        return float(fallback)
    d = np.diff(p)
    d = d[np.isfinite(d) & (np.abs(d) > 0)]
    if d.size == 0:
        return float(fallback)
    t = float(np.median(np.abs(d)))
    return t if t > 0 else float(fallback)


def nanex_detect(
    ts_ns: NDArray[np.int64],
    px: NDArray[np.float64],
    *,
    min_trades: int = 10,
    max_window_s: float = 1.5,
    min_pct: float = 0.008,
    tick_size: float | None = None,
    min_ticks: int | None = None,
    use_trade_count: bool = True,
) -> dict[str, Any]:
    """Nanex-style uni-directional mini-crash scan (Tee & Ting §1 / §4.2.1).

    Paper equity rule: ≥10 uni-dir ticks, ≤1.5s, |ΔP|≥0.8%. Crypto default uses
    **trade count** as the primary length measure (``use_trade_count=True``);
    set ``min_ticks`` + ``tick_size`` for the classic tick path.

    Returns arrays of event ``start_i``, ``end_i``, ``direction`` (±1),
    ``dp_pct``, ``n_trades``, ``n_ticks``, ``dt_s``, plus ``n_events``.
    """
    ts = np.asarray(ts_ns, dtype=np.int64)
    p = np.asarray(px, dtype=np.float64)
    n = int(ts.size)
    empty = {
        "start_i": np.zeros(0, dtype=np.int64),
        "end_i": np.zeros(0, dtype=np.int64),
        "direction": np.zeros(0, dtype=np.int64),
        "dp_pct": np.zeros(0, dtype=np.float64),
        "n_trades": np.zeros(0, dtype=np.int64),
        "n_ticks": np.zeros(0, dtype=np.int64),
        "dt_s": np.zeros(0, dtype=np.float64),
        "n_events": 0,
        "tick_size": float("nan"),
    }
    if n < max(min_trades, 3):
        return empty

    tick = float(tick_size) if tick_size is not None else _infer_tick_size(p)
    max_ns = int(max_window_s * NS_PER_S)
    length_thr = int(min_trades if use_trade_count else (min_ticks or min_trades))

    starts: list[int] = []
    ends: list[int] = []
    dirs: list[int] = []
    dps: list[float] = []
    ntr: list[int] = []
    ntk: list[int] = []
    dts: list[float] = []

    i = 0
    while i < n - 1:
        # skip flat prints
        j = i + 1
        while j < n and p[j] == p[i]:
            j += 1
        if j >= n:
            break
        direction = 1 if p[j] > p[i] else -1
        k = j
        while k + 1 < n:
            if ts[k + 1] - ts[i] > max_ns:
                break
            dp = p[k + 1] - p[k]
            if dp == 0:
                k += 1
                continue
            step = 1 if dp > 0 else -1
            if step != direction:
                break
            k += 1
        # event spans i..k
        dt = int(ts[k] - ts[i])
        if dt <= 0 or dt > max_ns:
            i = max(i + 1, j)
            continue
        n_trades = int(k - i + 1)
        move = float(p[k] - p[i])
        dp_pct = abs(move) / float(p[i]) if p[i] > 0 else float("nan")
        n_ticks = int(round(abs(move) / tick)) if tick > 0 else 0
        length_ok = n_trades >= length_thr if use_trade_count else n_ticks >= length_thr
        if length_ok and np.isfinite(dp_pct) and dp_pct >= min_pct:
            starts.append(i)
            ends.append(k)
            dirs.append(direction)
            dps.append(float(dp_pct * 100.0))  # percent
            ntr.append(n_trades)
            ntk.append(n_ticks)
            dts.append(dt / NS_PER_S)
            i = k + 1
        else:
            i = max(i + 1, j)

    return {
        "start_i": np.asarray(starts, dtype=np.int64),
        "end_i": np.asarray(ends, dtype=np.int64),
        "direction": np.asarray(dirs, dtype=np.int64),
        "dp_pct": np.asarray(dps, dtype=np.float64),
        "n_trades": np.asarray(ntr, dtype=np.int64),
        "n_ticks": np.asarray(ntk, dtype=np.int64),
        "dt_s": np.asarray(dts, dtype=np.float64),
        "n_events": int(len(starts)),
        "tick_size": tick,
    }


def outside_tob_flags(
    trade_ts: NDArray[np.int64],
    trade_px: NDArray[np.float64],
    tob_ts: NDArray[np.int64],
    bid: NDArray[np.float64],
    ask: NDArray[np.float64],
    *,
    eps: float = 0.0,
) -> dict[str, Any]:
    """Flag trades strictly outside contemporaneous TOB (asof bid/ask).

    ``eps`` is an absolute price slack (default 0). Returns boolean mask and
    counts; empty TOB → all-False with ``n_tob=0``.
    """
    tt = np.asarray(trade_ts, dtype=np.int64)
    px = np.asarray(trade_px, dtype=np.float64)
    qt = np.asarray(tob_ts, dtype=np.int64)
    b = np.asarray(bid, dtype=np.float64)
    a = np.asarray(ask, dtype=np.float64)
    out = {
        "outside": np.zeros(tt.shape, dtype=bool),
        "below_bid": np.zeros(tt.shape, dtype=bool),
        "above_ask": np.zeros(tt.shape, dtype=bool),
        "n_outside": 0,
        "n_tob": int(qt.size),
        "asof_bid": np.full(tt.shape, np.nan),
        "asof_ask": np.full(tt.shape, np.nan),
    }
    if tt.size == 0 or qt.size == 0:
        return out
    i0 = np.searchsorted(qt, tt, side="right") - 1
    valid = (i0 >= 0) & (i0 < qt.size) & np.isfinite(b[np.clip(i0, 0, max(qt.size - 1, 0))])
    asof_b = np.full(tt.shape, np.nan)
    asof_a = np.full(tt.shape, np.nan)
    asof_b[valid] = b[i0[valid]]
    asof_a[valid] = a[i0[valid]]
    below = valid & np.isfinite(px) & (px < asof_b - eps)
    above = valid & np.isfinite(px) & (px > asof_a + eps)
    outside = below | above
    out.update(
        {
            "outside": outside,
            "below_bid": below,
            "above_ask": above,
            "n_outside": int(outside.sum()),
            "asof_bid": asof_b,
            "asof_ask": asof_a,
        }
    )
    return out


def vshape_events(
    ts_ns: NDArray[np.int64],
    px: NDArray[np.float64],
    *,
    min_pct: float = 0.008,
    max_leg_s: float = 1.5,
    min_recovery: float = 0.5,
) -> dict[str, Any]:
    """Dugast–Foucault-style V / inverted-V: large move then partial reversal.

    Scans for a first leg meeting ``min_pct`` within ``max_leg_s``, then a
    reverse leg recovering at least ``min_recovery`` of the first move within
    another ``max_leg_s``. Coarse O(n) greedy scan suitable for Pass 1 baselines.
    """
    ts = np.asarray(ts_ns, dtype=np.int64)
    p = np.asarray(px, dtype=np.float64)
    n = int(ts.size)
    max_ns = int(max_leg_s * NS_PER_S)
    starts: list[int] = []
    troughs: list[int] = []
    ends: list[int] = []
    shapes: list[int] = []  # -1 = V (down then up), +1 = inv-V
    dps: list[float] = []
    recs: list[float] = []

    i = 0
    while i < n - 2:
        # find extremum within window from i
        j = i
        t_lim = ts[i] + max_ns
        while j + 1 < n and ts[j + 1] <= t_lim:
            j += 1
        if j <= i:
            i += 1
            continue
        seg = p[i : j + 1]
        imin = int(np.nanargmin(seg))
        imax = int(np.nanargmax(seg))
        # prefer larger absolute move as first leg
        down = float(p[i] - seg[imin]) / p[i] if p[i] > 0 else 0.0
        up = float(seg[imax] - p[i]) / p[i] if p[i] > 0 else 0.0
        if down >= min_pct and down >= up:
            mid = i + imin
            direction = -1
            move = down
        elif up >= min_pct:
            mid = i + imax
            direction = 1
            move = up
        else:
            i += 1
            continue
        # recovery leg
        k = mid
        t_lim2 = ts[mid] + max_ns
        while k + 1 < n and ts[k + 1] <= t_lim2:
            k += 1
        if k <= mid:
            i = mid + 1
            continue
        if direction < 0:
            # V: rebound from trough
            peak = float(np.nanmax(p[mid : k + 1]))
            recovered = (peak - p[mid]) / (p[i] - p[mid]) if p[i] != p[mid] else 0.0
        else:
            trough = float(np.nanmin(p[mid : k + 1]))
            recovered = (p[mid] - trough) / (p[mid] - p[i]) if p[mid] != p[i] else 0.0
        if recovered >= min_recovery:
            starts.append(i)
            troughs.append(mid)
            ends.append(k)
            shapes.append(direction)
            dps.append(float(move * 100.0))
            recs.append(float(recovered))
            i = k + 1
        else:
            i = mid + 1

    return {
        "start_i": np.asarray(starts, dtype=np.int64),
        "mid_i": np.asarray(troughs, dtype=np.int64),
        "end_i": np.asarray(ends, dtype=np.int64),
        "shape": np.asarray(shapes, dtype=np.int64),
        "dp_pct": np.asarray(dps, dtype=np.float64),
        "recovery": np.asarray(recs, dtype=np.float64),
        "n_events": int(len(starts)),
    }


# ---------------------------------------------------------------------------
# MC-GARCH / variance feed (Engle–Sokalska style components)
# ---------------------------------------------------------------------------


def _bar_log_returns(
    ts_ns: NDArray[np.int64],
    log_px: NDArray[np.float64],
    *,
    bar_ns: int = 5 * 60 * NS_PER_S,
) -> tuple[NDArray[np.int64], NDArray[np.float64]]:
    """Last log-price per calendar bar → bar returns; empty bars dropped."""
    ts = np.asarray(ts_ns, dtype=np.int64)
    x = np.asarray(log_px, dtype=np.float64)
    if ts.size < 2:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float64)
    t0 = int(ts[0] // bar_ns * bar_ns)
    bucket = (ts - t0) // bar_ns
    # last observation in each bucket
    order = np.argsort(bucket, kind="mergesort")
    b_sorted = bucket[order]
    x_sorted = x[order]
    ts_sorted = ts[order]
    change = np.ones(b_sorted.shape, dtype=bool)
    change[1:] = b_sorted[1:] != b_sorted[:-1]
    last = np.r_[change[1:], True]
    bar_ts = ts_sorted[last]
    bar_x = x_sorted[last]
    if bar_x.size < 2:
        return bar_ts, np.zeros(0, dtype=np.float64)
    r = np.diff(bar_x)
    return bar_ts[1:], r.astype(np.float64)


def diurnal_sj(
    bar_ts: NDArray[np.int64],
    bar_ret: NDArray[np.float64],
    day_h: NDArray[np.float64] | float,
    *,
    bar_ns: int = 5 * 60 * NS_PER_S,
    n_bars_day: int = 288,
) -> NDArray[np.float64]:
    r"""UTC diurnal \(\hat s_j\) — mean of \(r_{n,j}^2 / h_n\) by intraday slot.

    ``day_h`` is scalar (same h for sample) or per-bar array aligned to returns.
    Length ``n_bars_day`` (default 288 = 24h × 12 five-minute bars).
    """
    ts = np.asarray(bar_ts, dtype=np.int64)
    r = np.asarray(bar_ret, dtype=np.float64)
    s = np.ones(n_bars_day, dtype=np.float64)
    if ts.size == 0:
        return s
    if np.isscalar(day_h):
        h = np.full(r.shape, float(day_h), dtype=np.float64)
    else:
        h = np.asarray(day_h, dtype=np.float64)
    slot = ((ts % (86_400 * NS_PER_S)) // bar_ns).astype(np.int64) % n_bars_day
    acc = np.zeros(n_bars_day, dtype=np.float64)
    cnt = np.zeros(n_bars_day, dtype=np.float64)
    m = np.isfinite(r) & np.isfinite(h) & (h > 0)
    np.add.at(acc, slot[m], (r[m] ** 2) / h[m])
    np.add.at(cnt, slot[m], 1.0)
    pos = cnt > 0
    s[pos] = acc[pos] / cnt[pos]
    # normalize E[s]≈1 over observed slots
    if pos.any() and float(s[pos].mean()) > 0:
        s = s / float(s[pos].mean())
    return s


def garch11_forecast(
    returns: NDArray[np.float64],
    *,
    omega: float = 1e-6,
    alpha: float = 0.05,
    beta: float = 0.90,
    h0: float | None = None,
) -> dict[str, Any]:
    r"""Simple GARCH(1,1) variance path + one-step-ahead forecast.

    Desk utility for Pass 1 daily \(h_n\); not a full MLE. Returns in-sample
    ``h`` and ``h_next``. Stationarity soft-check: α+β < 1.
    """
    r = np.asarray(returns, dtype=np.float64)
    r = r[np.isfinite(r)]
    out = {
        "h": np.zeros(0, dtype=np.float64),
        "h_next": float("nan"),
        "omega": float(omega),
        "alpha": float(alpha),
        "beta": float(beta),
        "stationary": float(alpha + beta < 1.0),
        "n": int(r.size),
    }
    if r.size < 2:
        return out
    h = np.empty(r.size, dtype=np.float64)
    h[0] = float(h0) if h0 is not None else float(np.var(r))
    for t in range(1, r.size):
        h[t] = omega + alpha * (r[t - 1] ** 2) + beta * h[t - 1]
    h_next = omega + alpha * (r[-1] ** 2) + beta * h[-1]
    out["h"] = h
    out["h_next"] = float(h_next)
    return out


def mc_garch_bar_vol(
    ts_ns: NDArray[np.int64],
    px: NDArray[np.float64],
    *,
    bar_ns: int = 5 * 60 * NS_PER_S,
    n_bars_day: int = 288,
    q_alpha: float = 0.05,
    q_beta: float = 0.90,
) -> dict[str, Any]:
    r"""Build bar-level \(h_n\cdot s_j\cdot q_{n,j}\) composite for KF process noise.

    Single-day / short-panel path: \(h_n\) = sum of bar \(r^2\) (RV) for the UTC
    day of each bar; \(s_j\) via ``diurnal_sj``; \(q`` via GARCH(1,1) on
    \(z=r/\sqrt{h s}\). Multi-day GARCH(1,1) on daily RV is preferred when
    callers pass a longer history through ``garch11_forecast`` separately.
    """
    ts = np.asarray(ts_ns, dtype=np.int64)
    p = np.asarray(px, dtype=np.float64)
    m = np.isfinite(p) & (p > 0)
    ts, p = ts[m], p[m]
    x = np.log(p)
    bar_ts, bar_r = _bar_log_returns(ts, x, bar_ns=bar_ns)
    empty = {
        "bar_ts": bar_ts,
        "bar_ret": bar_r,
        "h": np.zeros(0, dtype=np.float64),
        "s": np.ones(n_bars_day, dtype=np.float64),
        "q": np.zeros(0, dtype=np.float64),
        "composite": np.zeros(0, dtype=np.float64),
        "n_bars": int(bar_r.size),
    }
    if bar_r.size < 4:
        return empty

    day_id = bar_ts // (86_400 * NS_PER_S)
    h_bar = np.empty(bar_r.size, dtype=np.float64)
    for d in np.unique(day_id):
        mask = day_id == d
        rv = float(np.sum(bar_r[mask] ** 2))
        h_bar[mask] = max(rv, 1e-18)

    s = diurnal_sj(bar_ts, bar_r, h_bar, bar_ns=bar_ns, n_bars_day=n_bars_day)
    slot = ((bar_ts % (86_400 * NS_PER_S)) // bar_ns).astype(np.int64) % n_bars_day
    s_bar = s[slot]
    z = bar_r / np.sqrt(np.maximum(h_bar * s_bar, 1e-18))
    g = garch11_forecast(z, omega=1e-4, alpha=q_alpha, beta=q_beta, h0=1.0)
    q = g["h"]
    # Engle–Sokalska normalize E[q]=1
    if q.size and np.isfinite(q).any():
        q = q / max(float(np.nanmean(q)), 1e-12)
    composite = h_bar * s_bar * q
    return {
        "bar_ts": bar_ts,
        "bar_ret": bar_r,
        "h": h_bar,
        "s": s,
        "s_bar": s_bar,
        "q": q,
        "composite": composite,
        "n_bars": int(bar_r.size),
        "garch_q": g,
    }


def sigma_process_meas(
    ts_ns: NDArray[np.int64],
    composite_bar: dict[str, Any],
    *,
    sigma_m_frac: float = 1.0,
    floor: float = 1e-12,
    log_px: NDArray[np.float64] | None = None,
    noise_floor_log: float = 1e-4,
) -> dict[str, NDArray[np.float64]]:
    r"""Map MC-GARCH composite onto per-trade \(\sigma_p^2\Delta t\) and \(\sigma_m^2\).

    Locked plan: \(\sigma_p^2 \propto q h s\cdot\Delta t\) via asof bar composite.

    Measurement noise (crypto desk): \(\sigma_m^2 = (\texttt{sigma_m_frac}\cdot
    \mathrm{MAD}(\Delta\log p))^2\) with a hard floor ``noise_floor_log`` (default
    \(10^{-4}\) ≈ 1 bp) so tick-clustered tapes cannot collapse R and flood z-flags.
    Pass 2 stresses ``sigma_m_frac`` on crash-rate stability.
    """
    ts = np.asarray(ts_ns, dtype=np.int64)
    bar_ts = np.asarray(composite_bar.get("bar_ts", []), dtype=np.int64)
    comp = np.asarray(composite_bar.get("composite", []), dtype=np.float64)
    n = ts.size
    sigma_p2_dt = np.full(n, floor, dtype=np.float64)
    sigma_m2 = np.full(n, floor, dtype=np.float64)
    if n == 0:
        return {"sigma_p2_dt": sigma_p2_dt, "sigma_m2": sigma_m2}

    dt = np.ones(n, dtype=np.float64)
    if n > 1:
        dt[1:] = np.maximum((ts[1:] - ts[:-1]) / NS_PER_S, 1e-9)
        dt[0] = dt[1]

    # trade-scale MAD of consecutive log-returns → σ_m
    noise_ref = float(noise_floor_log)
    if log_px is not None:
        lp = np.asarray(log_px, dtype=np.float64)
        if lp.size == n:
            dlp = np.diff(lp)
            dlp = dlp[np.isfinite(dlp)]
            if dlp.size > 10:
                mad = float(np.median(np.abs(dlp - np.median(dlp)))) / 0.6745
                noise_ref = max(mad, float(noise_floor_log), floor)

    if bar_ts.size == 0 or comp.size == 0 or comp.size != bar_ts.size:
        rate = floor
        sigma_p2_dt[:] = rate * dt
        sigma_m2[:] = max((sigma_m_frac * noise_ref) ** 2, floor)
        return {
            "sigma_p2_dt": sigma_p2_dt,
            "sigma_m2": sigma_m2,
            "rate_ref": rate,
            "noise_ref": noise_ref,
            "sigma_m_frac": float(sigma_m_frac),
            "noise_floor_log": float(noise_floor_log),
        }

    i0 = np.searchsorted(bar_ts, ts, side="right") - 1
    i0 = np.clip(i0, 0, bar_ts.size - 1)
    bar_s = 300.0
    rate = np.maximum(comp[i0] / bar_s, floor)
    sigma_p2_dt = rate * dt
    rate_ref = float(np.median(rate[np.isfinite(rate)])) if np.isfinite(rate).any() else floor
    sigma_m2[:] = max((sigma_m_frac * noise_ref) ** 2, floor)
    return {
        "sigma_p2_dt": sigma_p2_dt.astype(np.float64),
        "sigma_m2": sigma_m2.astype(np.float64),
        "rate": rate.astype(np.float64),
        "rate_ref": rate_ref,
        "noise_ref": noise_ref,
        "sigma_m_frac": float(sigma_m_frac),
        "noise_floor_log": float(noise_floor_log),
    }


# ---------------------------------------------------------------------------
# Kalman SSM detector
# ---------------------------------------------------------------------------


def kalman_ssm_filter(
    ts_ns: NDArray[np.int64],
    px: NDArray[np.float64],
    sigma_p2_dt: NDArray[np.float64] | float,
    sigma_m2: NDArray[np.float64] | float,
    *,
    x0: float | None = None,
    p0: float | None = None,
) -> dict[str, NDArray[np.float64]]:
    r"""Scalar Kalman filter on log-price (Tee & Ting §3.2).

    ``sigma_p2_dt[i]`` is process-noise variance for the step into trade \(i\)
    (already includes \(\Delta t\)); ``sigma_m2[i]`` is measurement variance.

    Returns ``x_hat``, ``p_post``, ``kappa``, ``innov``, ``z_score`` where
    crash z-score is the **standardized innovation**
    \(z=(z_i-\hat x_i^-)/\sqrt{P_i^-+\sigma_m^2}\) (Tee & Ting outlier band).

    Posterior residual / √P collapses when κ→1 (tiny P) and floods false
    positives on crypto ms tape — do not use that form for detection.
    """
    ts = np.asarray(ts_ns, dtype=np.int64)
    p = np.asarray(px, dtype=np.float64)
    m = np.isfinite(p) & (p > 0)
    # keep alignment: filter only valid prints but return full-length with NaN holes
    n = int(p.size)
    x_hat = np.full(n, np.nan, dtype=np.float64)
    p_post = np.full(n, np.nan, dtype=np.float64)
    p_prior_a = np.full(n, np.nan, dtype=np.float64)
    kappa = np.full(n, np.nan, dtype=np.float64)
    innov = np.full(n, np.nan, dtype=np.float64)
    z_sc = np.full(n, np.nan, dtype=np.float64)
    if int(m.sum()) < 2:
        return {
            "x_hat": x_hat,
            "p_post": p_post,
            "p_prior": p_prior_a,
            "kappa": kappa,
            "innov": innov,
            "z_score": z_sc,
            "log_z": np.full(n, np.nan),
        }

    if np.isscalar(sigma_p2_dt):
        sp = np.full(n, float(sigma_p2_dt), dtype=np.float64)
    else:
        sp = np.asarray(sigma_p2_dt, dtype=np.float64)
        if sp.size == 1:
            sp = np.full(n, float(sp[0]), dtype=np.float64)
    if np.isscalar(sigma_m2):
        sm = np.full(n, float(sigma_m2), dtype=np.float64)
    else:
        sm = np.asarray(sigma_m2, dtype=np.float64)
        if sm.size == 1:
            sm = np.full(n, float(sm[0]), dtype=np.float64)

    log_z = np.full(n, np.nan, dtype=np.float64)
    log_z[m] = np.log(p[m])
    idx = np.flatnonzero(m)
    i0 = int(idx[0])
    x = float(log_z[i0] if x0 is None else x0)
    P = float(p0) if p0 is not None else float(max(sm[i0], 1e-12))
    x_hat[i0] = x
    p_post[i0] = P
    p_prior_a[i0] = P
    kappa[i0] = 0.0
    innov[i0] = 0.0
    z_sc[i0] = 0.0

    for k in range(1, idx.size):
        i = int(idx[k])
        # time update
        P_prior = P + max(float(sp[i]), 1e-18)
        x_prior = x
        # measurement update
        R = max(float(sm[i]), 1e-18)
        S = P_prior + R
        K = P_prior / S
        inn = float(log_z[i] - x_prior)
        x = x_prior + K * inn
        P = (1.0 - K) * P_prior
        x_hat[i] = x
        p_post[i] = P
        p_prior_a[i] = P_prior
        kappa[i] = K
        innov[i] = inn
        # standardized innovation (crash band) — Tee & Ting §4.2.2 intent
        z_sc[i] = inn / np.sqrt(S) if S > 0 else np.nan

    return {
        "x_hat": x_hat,
        "p_post": p_post,
        "p_prior": p_prior_a,
        "kappa": kappa,
        "innov": innov,
        "z_score": z_sc,
        "log_z": log_z,
    }


def ssm_crash_mask(
    z_score: NDArray[np.float64],
    *,
    z_star: float = 6.0,
) -> NDArray[np.bool_]:
    """Boolean mask where |z_score| ≥ z* (paper default 6)."""
    z = np.asarray(z_score, dtype=np.float64)
    return np.isfinite(z) & (np.abs(z) >= float(z_star))


def _runs_from_mask(mask: NDArray[np.bool_]) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    m = np.asarray(mask, dtype=bool)
    if m.size == 0:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
    d = np.diff(m.astype(np.int8), prepend=0, append=0)
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1) - 1
    return starts.astype(np.int64), ends.astype(np.int64)


def detect_ssm_events(
    ts_ns: NDArray[np.int64],
    px: NDArray[np.float64],
    filter_out: dict[str, NDArray[np.float64]],
    *,
    z_star: float = 6.0,
) -> dict[str, Any]:
    """Collapse consecutive SSM crash flags into events with basic stats."""
    mask = ssm_crash_mask(filter_out["z_score"], z_star=z_star)
    starts, ends = _runs_from_mask(mask)
    return extract_event_features(ts_ns, px, starts, ends, z_score=filter_out["z_score"])


# ---------------------------------------------------------------------------
# Event features / recovery / z* scan
# ---------------------------------------------------------------------------


def extract_event_features(
    ts_ns: NDArray[np.int64],
    px: NDArray[np.float64],
    start_i: NDArray[np.int64],
    end_i: NDArray[np.int64],
    *,
    z_score: NDArray[np.float64] | None = None,
) -> dict[str, Any]:
    r"""Per-event \(\Delta P\) (%), \(i_c\) (trade count), \(\Delta t\) (s), direction.

    Optional peak |z| over the event when ``z_score`` provided.
    """
    ts = np.asarray(ts_ns, dtype=np.int64)
    p = np.asarray(px, dtype=np.float64)
    s = np.asarray(start_i, dtype=np.int64)
    e = np.asarray(end_i, dtype=np.int64)
    n_ev = int(s.size)
    dp = np.full(n_ev, np.nan, dtype=np.float64)
    ic = np.zeros(n_ev, dtype=np.int64)
    dt = np.full(n_ev, np.nan, dtype=np.float64)
    direction = np.zeros(n_ev, dtype=np.int64)
    z_peak = np.full(n_ev, np.nan, dtype=np.float64)
    t0 = np.zeros(n_ev, dtype=np.int64)
    t1 = np.zeros(n_ev, dtype=np.int64)

    for k in range(n_ev):
        a, b = int(s[k]), int(e[k])
        if a < 0 or b >= p.size or b < a:
            continue
        seg = p[a : b + 1]
        if not np.isfinite(seg).any() or p[a] <= 0:
            continue
        imin = int(np.nanargmin(seg))
        imax = int(np.nanargmax(seg))
        # severity = max excursion from start
        down = (p[a] - float(seg[imin])) / p[a]
        up = (float(seg[imax]) - p[a]) / p[a]
        if down >= up:
            direction[k] = -1
            dp[k] = down * 100.0
        else:
            direction[k] = 1
            dp[k] = up * 100.0
        ic[k] = int(b - a + 1)
        dt[k] = float(ts[b] - ts[a]) / NS_PER_S
        t0[k], t1[k] = int(ts[a]), int(ts[b])
        if z_score is not None:
            zz = np.asarray(z_score[a : b + 1], dtype=np.float64)
            if np.isfinite(zz).any():
                z_peak[k] = float(zz[np.nanargmax(np.abs(zz))])

    return {
        "start_i": s,
        "end_i": e,
        "ts_start": t0,
        "ts_end": t1,
        "dp_pct": dp,
        "i_c": ic,
        "dt_s": dt,
        "direction": direction,
        "z_peak": z_peak,
        "n_events": n_ev,
    }


def severity_gate(
    events: dict[str, Any],
    *,
    min_dp_pct: float = 0.10,
    min_i_c: int = 5,
    min_dt_s: float = 0.0,
    min_abs_z: float | None = None,
) -> dict[str, Any]:
    r"""Keep events with enough severity so micro-outliers do not dominate counts.

    Phase 2 raw SSM z*=6 floods (~3.7k) with near-zero \(\Delta P\). Default
    crypto gate: \(|\Delta P|\ge 10\) bps (``min_dp_pct=0.10`` percent) and
    \(i_c\ge 5\) trades. Optional ``min_abs_z`` further gates on peak |z|.
    Ablate to 5 bps / \(i_c\ge 3\) in Pass 2 fragility tables.

    Returns a shallow copy of ``events`` with array fields masked to survivors
    plus ``n_raw``, ``n_events``, ``gate``, and boolean ``keep``.
    """
    n = int(events.get("n_events", len(np.asarray(events.get("dp_pct", [])))))
    keep = np.ones(n, dtype=bool) if n else np.zeros(0, dtype=bool)
    if n:
        dp = np.asarray(events.get("dp_pct", np.full(n, np.nan)), dtype=np.float64)
        ic = np.asarray(events.get("i_c", np.zeros(n)), dtype=np.float64)
        dt = np.asarray(events.get("dt_s", np.full(n, np.nan)), dtype=np.float64)
        keep &= np.isfinite(dp) & (np.abs(dp) >= float(min_dp_pct))
        keep &= np.isfinite(ic) & (ic >= int(min_i_c))
        if min_dt_s > 0:
            keep &= np.isfinite(dt) & (dt >= float(min_dt_s))
        if min_abs_z is not None and "z_peak" in events:
            zp = np.asarray(events["z_peak"], dtype=np.float64)
            keep &= np.isfinite(zp) & (np.abs(zp) >= float(min_abs_z))

    out: dict[str, Any] = {
        "n_raw": n,
        "n_events": int(keep.sum()) if keep.size else 0,
        "n_kept": int(keep.sum()) if keep.size else 0,
        "keep": keep,
        "gate": {
            "min_dp_pct": float(min_dp_pct),
            "min_i_c": int(min_i_c),
            "min_dt_s": float(min_dt_s),
            "min_abs_z": float(min_abs_z) if min_abs_z is not None else None,
        },
    }
    for key, val in events.items():
        if key in ("n_events", "n_raw", "n_kept", "keep", "gate"):
            continue
        if isinstance(val, np.ndarray) and val.shape[:1] == (n,):
            out[key] = val[keep]
        else:
            out[key] = val
    return out


def volume_herfindahl(
    volumes: dict[str, float] | NDArray[np.float64],
    *,
    keys: list[str] | None = None,
) -> dict[str, Any]:
    r"""Volume Herfindahl \(H^v=\sum_k (s^k)^2\) and venue shares.

    ``volumes`` may be a venue→notional map or a non-negative array (use ``keys``).
    Incomplete / zero-total days return ``complete=False`` and NaN \(H^v\).
    """
    if isinstance(volumes, dict):
        keys_u = list(keys) if keys is not None else list(volumes.keys())
        vols = np.asarray([float(volumes.get(k, 0.0)) for k in keys_u], dtype=np.float64)
    else:
        vols = np.asarray(volumes, dtype=np.float64)
        keys_u = list(keys) if keys is not None else [str(i) for i in range(vols.size)]
    vols = np.where(np.isfinite(vols) & (vols > 0), vols, 0.0)
    tot = float(vols.sum())
    vol_map = {k: float(vols[i]) for i, k in enumerate(keys_u)}
    if tot <= 0 or vols.size == 0:
        return {
            "H_v": float("nan"),
            "shares": {k: float("nan") for k in keys_u},
            "volumes": vol_map,
            "n_positive": 0,
            "complete": False,
            "total": 0.0,
        }
    shares = vols / tot
    return {
        "H_v": float(np.sum(shares * shares)),
        "shares": {k: float(shares[i]) for i, k in enumerate(keys_u)},
        "volumes": {k: float(vols[i]) for i, k in enumerate(keys_u)},
        "n_positive": int((vols > 0).sum()),
        "complete": bool((vols > 0).all()),
        "total": tot,
    }


def xvenue_event_concordance(
    events_by_venue: dict[str, dict[str, Any]],
    *,
    slack_s: float = 5.0,
    pairs: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Match crash events across venues by absolute time (not same-tape index).

    An event on venue A matches B if intervals overlap within ``slack_s``.
    Returns pairwise Jaccard / precision / recall plus optional triple hits
    (events matched on all three venues under greedy pairwise chaining).
    """
    venues = list(events_by_venue.keys())
    if pairs is None:
        pairs = [(venues[i], venues[j]) for i in range(len(venues)) for j in range(i + 1, len(venues))]
    slack = int(float(slack_s) * NS_PER_S)

    def _intervals(ev: dict[str, Any]) -> list[tuple[int, int]]:
        t0 = np.asarray(ev.get("ts_start", []), dtype=np.int64)
        t1 = np.asarray(ev.get("ts_end", []), dtype=np.int64)
        return [(int(a), int(b)) for a, b in zip(t0.tolist(), t1.tolist()) if b >= a]

    iv = {v: _intervals(events_by_venue[v]) for v in venues}
    pair_rows = []
    for a, b in pairs:
        ia, ib = iv.get(a, []), iv.get(b, [])
        matched_a = np.zeros(len(ia), dtype=bool)
        matched_b = np.zeros(len(ib), dtype=bool)
        for i, (ta0, ta1) in enumerate(ia):
            for j, (tb0, tb1) in enumerate(ib):
                if matched_b[j]:
                    continue
                if ta0 <= tb1 + slack and tb0 <= ta1 + slack:
                    matched_a[i] = True
                    matched_b[j] = True
                    break
        n_ov = int(matched_a.sum())
        n_a, n_b = len(ia), len(ib)
        union = n_a + n_b - n_ov
        pair_rows.append(
            {
                "a": a,
                "b": b,
                "n_a": n_a,
                "n_b": n_b,
                "n_overlap": n_ov,
                "jaccard": float(n_ov / union) if union else float("nan"),
                "precision_a": float(n_ov / n_a) if n_a else float("nan"),
                "recall_a": float(n_ov / n_b) if n_b else float("nan"),
                "slack_s": float(slack_s),
            }
        )

    # triple: A event that matches some B and some C (greedy)
    triple = None
    if len(venues) >= 3:
        a, b, c = venues[0], venues[1], venues[2]
        ia, ib, ic = iv[a], iv[b], iv[c]
        n_trip = 0
        used_b = np.zeros(len(ib), dtype=bool)
        used_c = np.zeros(len(ic), dtype=bool)
        for ta0, ta1 in ia:
            jb = -1
            for j, (tb0, tb1) in enumerate(ib):
                if used_b[j]:
                    continue
                if ta0 <= tb1 + slack and tb0 <= ta1 + slack:
                    jb = j
                    break
            if jb < 0:
                continue
            jc = -1
            for j, (tc0, tc1) in enumerate(ic):
                if used_c[j]:
                    continue
                if ta0 <= tc1 + slack and tc0 <= ta1 + slack:
                    jc = j
                    break
            if jc < 0:
                continue
            used_b[jb] = True
            used_c[jc] = True
            n_trip += 1
        triple = {
            "venues": [a, b, c],
            "n_triple": n_trip,
            "n_a": len(ia),
            "frac_a_triple": float(n_trip / len(ia)) if ia else float("nan"),
        }

    return {"pairs": pair_rows, "triple": triple, "slack_s": float(slack_s), "venues": venues}


def recovery_fraction(
    ts_ns: NDArray[np.int64],
    px: NDArray[np.float64],
    start_i: NDArray[np.int64],
    end_i: NDArray[np.int64],
    direction: NDArray[np.int64],
    *,
    horizon_s: float = 5.0,
) -> NDArray[np.float64]:
    """Fraction of event move reversed by ``horizon_s`` after event end."""
    ts = np.asarray(ts_ns, dtype=np.int64)
    p = np.asarray(px, dtype=np.float64)
    s = np.asarray(start_i, dtype=np.int64)
    e = np.asarray(end_i, dtype=np.int64)
    d = np.asarray(direction, dtype=np.int64)
    out = np.full(s.shape, np.nan, dtype=np.float64)
    horiz = int(horizon_s * NS_PER_S)
    for k in range(s.size):
        a, b = int(s[k]), int(e[k])
        if a < 0 or b >= p.size or b < a or p[a] <= 0:
            continue
        move = p[b] - p[a]
        if move == 0 or d[k] == 0:
            continue
        t_lim = ts[b] + horiz
        j = b
        while j + 1 < ts.size and ts[j + 1] <= t_lim:
            j += 1
        if j <= b:
            out[k] = 0.0
            continue
        # recovery toward start
        if d[k] < 0:
            # price fell; recovery = rebound / |move|
            rebound = float(np.nanmax(p[b : j + 1]) - p[b])
            out[k] = rebound / abs(move)
        else:
            giveback = float(p[b] - np.nanmin(p[b : j + 1]))
            out[k] = giveback / abs(move)
    return out


def classify_recovery(
    recovery: NDArray[np.float64],
    *,
    v_thr: float = 0.5,
    cont_thr: float = 0.2,
) -> dict[str, Any]:
    """Label events as V-recovery / continuation / partial from recovery fraction.

    ``v_thr``: recover ≥ half the move → V-class (Dugast–Foucault style).
    ``cont_thr``: recover < threshold → continuation / news assimilation.
    """
    r = np.asarray(recovery, dtype=np.float64)
    labels = np.full(r.shape, "unknown", dtype=object)
    m = np.isfinite(r)
    labels[m & (r >= float(v_thr))] = "v_recovery"
    labels[m & (r < float(cont_thr))] = "continuation"
    labels[m & (r >= float(cont_thr)) & (r < float(v_thr))] = "partial"
    n = int(r.size)
    n_v = int((labels == "v_recovery").sum())
    n_c = int((labels == "continuation").sum())
    n_p = int((labels == "partial").sum())
    return {
        "labels": labels,
        "n": n,
        "n_v_recovery": n_v,
        "n_continuation": n_c,
        "n_partial": n_p,
        "share_v": float(n_v / n) if n else float("nan"),
        "share_continuation": float(n_c / n) if n else float("nan"),
        "v_thr": float(v_thr),
        "cont_thr": float(cont_thr),
    }


def post_event_markout_px(
    ts_ns: NDArray[np.int64],
    px: NDArray[np.float64],
    end_i: NDArray[np.int64],
    direction: NDArray[np.int64],
    *,
    horizons_s: tuple[float, ...] = (0.5, 1.0, 5.0),
) -> dict[str, Any]:
    """Trade-price markout after event end (signed with crash direction).

    Positive ⇒ price continued in the crash direction (adverse for mean-revert /
    recovery bets). Dense mid/TOB markout preferred when available — this is the
    tape-only ceiling when L2 is sparse.
    """
    ts = np.asarray(ts_ns, dtype=np.int64)
    p = np.asarray(px, dtype=np.float64)
    e = np.asarray(end_i, dtype=np.int64)
    d = np.asarray(direction, dtype=np.int64)
    out: dict[str, Any] = {"horizons_s": list(horizons_s), "by_horizon": {}}
    for h in horizons_s:
        h_ns = int(h * NS_PER_S)
        mos: list[float] = []
        for k in range(e.size):
            b = int(e[k])
            if b < 0 or b >= p.size or p[b] <= 0 or d[k] == 0:
                continue
            t_lim = ts[b] + h_ns
            j = int(np.searchsorted(ts, t_lim, side="right") - 1)
            if j <= b or j >= p.size or not np.isfinite(p[j]):
                continue
            # signed: +1 if continued in crash direction
            move = (p[j] - p[b]) / p[b]
            mos.append(float(d[k] * move * 1e4))  # bps
        arr = np.asarray(mos, dtype=np.float64)
        out["by_horizon"][str(h)] = {
            "n": int(arr.size),
            "mean_bps": float(np.nanmean(arr)) if arr.size else float("nan"),
            "median_bps": float(np.nanmedian(arr)) if arr.size else float("nan"),
            "p25_bps": float(np.nanpercentile(arr, 25)) if arr.size else float("nan"),
            "p75_bps": float(np.nanpercentile(arr, 75)) if arr.size else float("nan"),
        }
    return out


def zstar_scan(
    z_score: NDArray[np.float64],
    ts_ns: NDArray[np.int64],
    px: NDArray[np.float64],
    *,
    z_grid: NDArray[np.float64] | None = None,
) -> dict[str, Any]:
    r"""Table III analogue: crash counts and median severity vs \(z^*\).

    Default grid \(z\in\{2,3,\ldots,12\}\).
    """
    if z_grid is None:
        z_grid = np.arange(2, 13, dtype=np.float64)
    else:
        z_grid = np.asarray(z_grid, dtype=np.float64)
    rows = []
    for z in z_grid:
        mask = ssm_crash_mask(z_score, z_star=float(z))
        st, en = _runs_from_mask(mask)
        feats = extract_event_features(ts_ns, px, st, en, z_score=z_score)
        rows.append(
            {
                "z_star": float(z),
                "n_events": int(feats["n_events"]),
                "n_flags": int(mask.sum()),
                "median_dp_pct": float(np.nanmedian(feats["dp_pct"]))
                if feats["n_events"]
                else float("nan"),
                "median_i_c": float(np.nanmedian(feats["i_c"]))
                if feats["n_events"]
                else float("nan"),
                "median_dt_s": float(np.nanmedian(feats["dt_s"]))
                if feats["n_events"]
                else float("nan"),
            }
        )
    return {"grid": z_grid, "rows": rows}


def event_overlap(
    a_start: NDArray[np.int64],
    a_end: NDArray[np.int64],
    b_start: NDArray[np.int64],
    b_end: NDArray[np.int64],
    ts_ns: NDArray[np.int64],
    *,
    slack_s: float = 0.0,
) -> dict[str, float]:
    """Index-space overlap of two event sets (Jaccard on event hits).

    Events match if time intervals overlap within ``slack_s``.
    """
    ts = np.asarray(ts_ns, dtype=np.int64)
    slack = int(slack_s * NS_PER_S)
    a_s = np.asarray(a_start, dtype=np.int64)
    a_e = np.asarray(a_end, dtype=np.int64)
    b_s = np.asarray(b_start, dtype=np.int64)
    b_e = np.asarray(b_end, dtype=np.int64)
    if a_s.size == 0 or b_s.size == 0:
        return {
            "n_a": float(a_s.size),
            "n_b": float(b_s.size),
            "n_overlap": 0.0,
            "jaccard": float("nan"),
            "precision_a": float("nan"),
            "recall_a": float("nan"),
        }
    matched_a = np.zeros(a_s.size, dtype=bool)
    matched_b = np.zeros(b_s.size, dtype=bool)
    for i in range(a_s.size):
        ta0, ta1 = int(ts[a_s[i]]), int(ts[a_e[i]])
        for j in range(b_s.size):
            if matched_b[j]:
                continue
            tb0, tb1 = int(ts[b_s[j]]), int(ts[b_e[j]])
            if ta0 <= tb1 + slack and tb0 <= ta1 + slack:
                matched_a[i] = True
                matched_b[j] = True
                break
    n_ov = int(matched_a.sum())
    n_a, n_b = int(a_s.size), int(b_s.size)
    union = n_a + n_b - n_ov
    return {
        "n_a": float(n_a),
        "n_b": float(n_b),
        "n_overlap": float(n_ov),
        "jaccard": float(n_ov / union) if union else float("nan"),
        "precision_a": float(n_ov / n_a) if n_a else float("nan"),
        "recall_a": float(n_ov / n_b) if n_b else float("nan"),
    }
