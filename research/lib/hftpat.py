r"""Filimonov (2013) HFT abuse/latency detector catalog.

Crypto-adaptable public-tape fingerprints for ``research/books/filmonov/``:
quote stuffing storms, post-trade price/venue fade, momentum ignition,
smoking/spoof proxies, clock-aligned fill clusters, venue OTR, and
size/latency regime panels.

**Hard distinctions (do not merge APIs):**
- ``crash.nanex_detect`` / SSM / ``vshape_events`` — geometric crash/recovery
  tags ≠ ignition’s **3-phase volume→move→reversion** fingerprint.
- ``vstat.min_v`` — econometric drift-burst product ≠ ignition cause sequence.
- ``lob.tob_depletion_cancel_proxy`` — unconditional same-price size-drop cancel
  proxy ≠ **post-trade conditional** price/venue fade.

Cross-link via overlap helpers only. Deck: Filimonov, *High-Frequency Trading.
Technology, Strategies, Regulations* (Perm Winter School 2013).

Public surface::

    quote_storm_intensity, quote_storm_detect, quote_storm_summary
    price_fade_events, price_fade_prob
    venue_fade_events, venue_fade_prob
    ignition_events
    smoke_spoof_proxy
    clock_cluster_scores, clock_cluster_excess
    otr_aggregate
    size_latency_panel
    overlap_vs_crash, overlap_vs_lob_cancel, rename_gate
    event_window_markout, spread_irf_after_events
    lead_lag_cascade, fade_tau_sensitivity, size_storm_interaction
    clock_vs_funding_windows, tod_event_heatmap
    ignition_phase1_unique_mass, xvenue_fade_info_share
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

NS_PER_S = 1_000_000_000
NS_PER_MS = 1_000_000

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _empty_int() -> NDArray[np.int64]:
    return np.zeros(0, dtype=np.int64)

def _empty_float() -> NDArray[np.float64]:
    return np.zeros(0, dtype=np.float64)

def _asof_idx(query_ts: NDArray[np.int64], ref_ts: NDArray[np.int64]) -> NDArray[np.int64]:
    """Largest ref index with ref_ts[i] <= query (searchsorted right - 1)."""
    q = np.asarray(query_ts, dtype=np.int64)
    r = np.asarray(ref_ts, dtype=np.int64)
    return np.searchsorted(r, q, side="right").astype(np.int64) - 1

def _normalize_side(side: NDArray[np.floating] | NDArray[np.integer]) -> NDArray[np.float64]:
    """Map {0,1} or signed sides to ±1 (buy=+1, sell=-1)."""
    s = np.asarray(side, dtype=np.float64)
    uniq = set(np.unique(s[np.isfinite(s)]).tolist())
    if uniq <= {0.0, 1.0} or uniq <= {0, 1}:
        return np.where(s > 0, 1.0, -1.0)
    return np.where(s >= 0, 1.0, -1.0)

# ---------------------------------------------------------------------------
# Quote storms (deck stuffing bursts ~slides 27–29)
# ---------------------------------------------------------------------------

def quote_storm_intensity(
    tob_ts: NDArray[np.int64],
    bid: NDArray[np.float64],
    ask: NDArray[np.float64],
    bid_sz: NDArray[np.float64],
    ask_sz: NDArray[np.float64],
    *,
    bar_s: float = 1.0,
) -> dict[str, Any]:
    """Per-bar quote-activity intensity from L0 TOB (stuffing proxy).

    Deck object: quote stuffing / flickering — high add+cancel rate with little
    mid move. Without OE message types we proxy:

    - **update**: any TOB row (feed cadence)
    - **add_proxy**: same-side size ↑ with price unchanged
    - **cancel_proxy**: same-side size ↓ with price unchanged
    - **price_change**: bid or ask price tick

    Returns bar arrays: ``ts``, ``n_updates``, ``n_add``, ``n_cancel``,
    ``n_price``, ``cancel_frac``, ``intensity_hz``, ``mid_range_bps``.
    """
    t = np.asarray(tob_ts, dtype=np.int64)
    b = np.asarray(bid, dtype=np.float64)
    a = np.asarray(ask, dtype=np.float64)
    bs = np.asarray(bid_sz, dtype=np.float64)
    az = np.asarray(ask_sz, dtype=np.float64)
    empty = {
        "ts": _empty_int(),
        "n_updates": _empty_int(),
        "n_add": _empty_int(),
        "n_cancel": _empty_int(),
        "n_price": _empty_int(),
        "cancel_frac": _empty_float(),
        "intensity_hz": _empty_float(),
        "size_intensity_hz": _empty_float(),
        "mid_range_bps": _empty_float(),
        "bar_s": float(bar_s),
        "n_bars": 0,
    }
    n = int(t.size)
    if n < 3:
        return empty

    add_flag = np.zeros(n, dtype=np.int64)
    cancel_flag = np.zeros(n, dtype=np.int64)
    price_flag = np.zeros(n, dtype=np.int64)
    # L0 has no OE message type: any size↑ / size↓ is an add/cancel *proxy*
    # (includes replaces). Price ticks tracked separately for mid-range filter.
    for i in range(1, n):
        bid_px_chg = not (
            np.isfinite(b[i]) and np.isfinite(b[i - 1]) and abs(b[i] - b[i - 1]) < 1e-12
        )
        ask_px_chg = not (
            np.isfinite(a[i]) and np.isfinite(a[i - 1]) and abs(a[i] - a[i - 1]) < 1e-12
        )
        if bid_px_chg or ask_px_chg:
            price_flag[i] = 1
        if np.isfinite(bs[i]) and np.isfinite(bs[i - 1]):
            if bs[i] > bs[i - 1] * 1.0000001:
                add_flag[i] = 1
            elif bs[i] < bs[i - 1] * 0.9999999:
                cancel_flag[i] = 1
        if np.isfinite(az[i]) and np.isfinite(az[i - 1]):
            if az[i] > az[i - 1] * 1.0000001:
                add_flag[i] = 1
            elif az[i] < az[i - 1] * 0.9999999:
                cancel_flag[i] = 1

    step = int(max(bar_s, 1e-6) * NS_PER_S)
    bar0 = int(t[0] // step * step)
    bar1 = int(t[-1] // step * step)
    n_bars = int((bar1 - bar0) // step) + 1
    if n_bars <= 0:
        return empty
    bar_ts = bar0 + np.arange(n_bars, dtype=np.int64) * step
    bar_ix = ((t - bar0) // step).astype(np.int64)
    bar_ix = np.clip(bar_ix, 0, n_bars - 1)

    n_upd = np.bincount(bar_ix, minlength=n_bars).astype(np.int64)
    n_add = np.bincount(bar_ix, weights=add_flag, minlength=n_bars).astype(np.int64)
    n_can = np.bincount(bar_ix, weights=cancel_flag, minlength=n_bars).astype(np.int64)
    n_px = np.bincount(bar_ix, weights=price_flag, minlength=n_bars).astype(np.int64)

    mid = 0.5 * (b + a)
    mid_ok = np.isfinite(mid) & (mid > 0)
    mid_min = np.full(n_bars, np.nan)
    mid_max = np.full(n_bars, np.nan)
    for i in range(n):
        if not mid_ok[i]:
            continue
        k = int(bar_ix[i])
        m = float(mid[i])
        if not np.isfinite(mid_min[k]) or m < mid_min[k]:
            mid_min[k] = m
        if not np.isfinite(mid_max[k]) or m > mid_max[k]:
            mid_max[k] = m
    mid_mid = 0.5 * (mid_min + mid_max)
    mid_range_bps = np.where(
        np.isfinite(mid_mid) & (mid_mid > 0),
        (mid_max - mid_min) / mid_mid * 1e4,
        np.nan,
    )

    ac = (n_add + n_can).astype(np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        cancel_frac = np.where(ac > 0, n_can.astype(np.float64) / ac, np.nan)
    # Primary stuffing intensity: TOB update Hz (message-rate proxy).
    # Secondary: add+cancel proxy Hz (size flicker).
    intensity = n_upd.astype(np.float64) / float(bar_s)
    size_intensity = ac / float(bar_s)

    return {
        "ts": bar_ts,
        "n_updates": n_upd,
        "n_add": n_add,
        "n_cancel": n_can,
        "n_price": n_px,
        "cancel_frac": cancel_frac.astype(np.float64),
        "intensity_hz": intensity,
        "size_intensity_hz": size_intensity.astype(np.float64),
        "mid_range_bps": mid_range_bps.astype(np.float64),
        "bar_s": float(bar_s),
        "n_bars": int(n_bars),
    }

def quote_storm_detect(
    intensity: dict[str, Any],
    *,
    z_thresh: float = 4.0,
    min_cancel_frac: float = 0.4,
    max_mid_range_bps: float = 10.0,
    min_intensity_hz: float = 10.0,
    use_size_intensity: bool = False,
) -> dict[str, Any]:
    """Flag stuffing-like bars: high intensity vs day baseline, high cancel frac.

    Deck: bursts of adds+cancels with little price discovery. Baseline =
    sample mean/std of ``intensity_hz`` (day-level caller responsibility).
    Set ``use_size_intensity=True`` to z-score size flicker Hz instead of
    TOB update Hz.
    """
    key = "size_intensity_hz" if use_size_intensity else "intensity_hz"
    hz = np.asarray(intensity.get(key, intensity.get("intensity_hz", [])), dtype=np.float64)
    cf = np.asarray(intensity.get("cancel_frac", []), dtype=np.float64)
    mr = np.asarray(intensity.get("mid_range_bps", []), dtype=np.float64)
    ts = np.asarray(intensity.get("ts", []), dtype=np.int64)
    n = int(hz.size)
    empty = {
        "bar_i": _empty_int(),
        "ts": _empty_int(),
        "intensity_hz": _empty_float(),
        "cancel_frac": _empty_float(),
        "z": _empty_float(),
        "n_events": 0,
        "z_thresh": float(z_thresh),
        "baseline_mean": float("nan"),
        "baseline_std": float("nan"),
    }
    if n < 5:
        return empty
    ok = np.isfinite(hz)
    mu = float(np.nanmean(hz[ok])) if ok.any() else float("nan")
    sd = float(np.nanstd(hz[ok])) if ok.any() else float("nan")
    if not np.isfinite(sd) or sd < 1e-12:
        z = np.zeros(n, dtype=np.float64)
    else:
        z = (hz - mu) / sd
    # cancel_frac filter soft: NaN cancel_frac still allowed (update-rate storms)
    cf_ok = ~np.isfinite(cf) | (cf >= float(min_cancel_frac))
    storm = (
        ok
        & (z >= float(z_thresh))
        & (hz >= float(min_intensity_hz))
        & cf_ok
        & (~np.isfinite(mr) | (mr <= float(max_mid_range_bps)))
    )
    idx = np.flatnonzero(storm).astype(np.int64)
    return {
        "bar_i": idx,
        "ts": ts[idx] if ts.size == n else _empty_int(),
        "intensity_hz": hz[idx],
        "cancel_frac": cf[idx] if cf.size == n else _empty_float(),
        "z": z[idx],
        "n_events": int(idx.size),
        "z_thresh": float(z_thresh),
        "baseline_mean": mu,
        "baseline_std": sd,
        "max_burst_hz": float(np.nanmax(hz)) if ok.any() else float("nan"),
        "max_burst_vs_mean": float(np.nanmax(hz) / mu) if ok.any() and mu > 0 else float("nan"),
        "intensity_key": key,
    }

def quote_storm_summary(intensity: dict[str, Any], storms: dict[str, Any]) -> dict[str, Any]:
    """Compact desk headline for storm intensity + detections."""
    hz = np.asarray(intensity.get("intensity_hz", []), dtype=np.float64)
    shz = np.asarray(intensity.get("size_intensity_hz", []), dtype=np.float64)
    cf = np.asarray(intensity.get("cancel_frac", []), dtype=np.float64)
    with np.errstate(all="ignore"):
        mean_cf = float(np.nanmean(cf)) if cf.size and np.isfinite(cf).any() else float("nan")
        mean_hz = float(np.nanmean(hz)) if hz.size else float("nan")
        p99_hz = float(np.nanpercentile(hz, 99)) if hz.size else float("nan")
        mean_shz = float(np.nanmean(shz)) if shz.size else float("nan")
    return {
        "n_bars": int(intensity.get("n_bars", hz.size)),
        "bar_s": float(intensity.get("bar_s", float("nan"))),
        "mean_intensity_hz": mean_hz,
        "p99_intensity_hz": p99_hz,
        "mean_size_intensity_hz": mean_shz,
        "mean_cancel_frac": mean_cf,
        "n_storms": int(storms.get("n_events", 0)),
        "max_burst_hz": float(storms.get("max_burst_hz", float("nan"))),
        "max_burst_vs_mean": float(storms.get("max_burst_vs_mean", float("nan"))),
    }

# ---------------------------------------------------------------------------
# Price fade (deck ~slide 33) — post-trade same-venue depth drop
# ---------------------------------------------------------------------------

def price_fade_events(
    trade_ts: NDArray[np.int64],
    trade_side: NDArray[np.floating] | NDArray[np.integer],
    tob_ts: NDArray[np.int64],
    bid: NDArray[np.float64],
    ask: NDArray[np.float64],
    bid_sz: NDArray[np.float64],
    ask_sz: NDArray[np.float64],
    *,
    tau_ms: float = 100.0,
    drop_frac: float = 0.2,
) -> dict[str, Any]:
    """Same-venue price-fade events after aggressor trades.

    Deck: P(same-side depth ↓ > θ within τ | aggressor). Buy aggressor → ask
    depth; sell aggressor → bid depth. Distinct from
    ``lob.tob_depletion_cancel_proxy`` (unconditional size-drop classification).
    """
    tt = np.asarray(trade_ts, dtype=np.int64)
    side = _normalize_side(trade_side)
    t = np.asarray(tob_ts, dtype=np.int64)
    b = np.asarray(bid, dtype=np.float64)
    a = np.asarray(ask, dtype=np.float64)
    bs = np.asarray(bid_sz, dtype=np.float64)
    az = np.asarray(ask_sz, dtype=np.float64)
    empty = {
        "trade_i": _empty_int(),
        "fade": _empty_int(),
        "drop_frac": _empty_float(),
        "side": _empty_float(),
        "n_trades": 0,
        "n_fade": 0,
        "tau_ms": float(tau_ms),
        "theta": float(drop_frac),
    }
    if tt.size == 0 or t.size < 2:
        return empty

    tau_ns = int(float(tau_ms) * NS_PER_MS)
    i0 = _asof_idx(tt, t)
    fade_flags: list[int] = []
    drops: list[float] = []
    sides: list[float] = []
    trade_is: list[int] = []

    for k in range(int(tt.size)):
        i = int(i0[k])
        if i < 0 or i >= t.size - 1:
            continue
        s = float(side[k])
        if s > 0:
            sz0 = float(az[i]) if np.isfinite(az[i]) else float("nan")
            px0 = float(a[i]) if np.isfinite(a[i]) else float("nan")
            sz_arr, px_arr = az, a
        else:
            sz0 = float(bs[i]) if np.isfinite(bs[i]) else float("nan")
            px0 = float(b[i]) if np.isfinite(b[i]) else float("nan")
            sz_arr, px_arr = bs, b
        if not (np.isfinite(sz0) and sz0 > 0 and np.isfinite(px0)):
            continue
        j_end = int(np.searchsorted(t, tt[k] + tau_ns, side="right"))
        j_end = min(j_end, t.size)
        faded = 0
        max_drop = 0.0
        for j in range(i + 1, j_end):
            if not (np.isfinite(px_arr[j]) and abs(px_arr[j] - px0) < 1e-12):
                # price moved away — still count size at new touch as fade of prior quote
                pass
            if not np.isfinite(sz_arr[j]):
                continue
            drop = (sz0 - float(sz_arr[j])) / sz0
            if drop > max_drop:
                max_drop = drop
            if drop >= float(drop_frac):
                faded = 1
                break
        trade_is.append(k)
        fade_flags.append(faded)
        drops.append(float(max_drop))
        sides.append(s)

    fade_a = np.asarray(fade_flags, dtype=np.int64)
    return {
        "trade_i": np.asarray(trade_is, dtype=np.int64),
        "fade": fade_a,
        "drop_frac": np.asarray(drops, dtype=np.float64),
        "side": np.asarray(sides, dtype=np.float64),
        "n_trades": int(len(trade_is)),
        "n_fade": int(fade_a.sum()) if fade_a.size else 0,
        "tau_ms": float(tau_ms),
        "theta": float(drop_frac),
    }

def price_fade_prob(events: dict[str, Any]) -> dict[str, Any]:
    """Aggregate P(fade) and side splits from ``price_fade_events``."""
    fade = np.asarray(events.get("fade", []), dtype=np.float64)
    side = np.asarray(events.get("side", []), dtype=np.float64)
    n = int(fade.size)
    if n == 0:
        return {
            "p_fade": float("nan"),
            "p_fade_buy": float("nan"),
            "p_fade_sell": float("nan"),
            "n": 0,
            "tau_ms": float(events.get("tau_ms", float("nan"))),
            "theta": float(events.get("theta", float("nan"))),
        }
    buy = side > 0
    sell = side < 0
    return {
        "p_fade": float(np.mean(fade)),
        "p_fade_buy": float(np.mean(fade[buy])) if buy.any() else float("nan"),
        "p_fade_sell": float(np.mean(fade[sell])) if sell.any() else float("nan"),
        "n": n,
        "n_buy": int(buy.sum()),
        "n_sell": int(sell.sum()),
        "tau_ms": float(events.get("tau_ms", float("nan"))),
        "theta": float(events.get("theta", float("nan"))),
    }

# ---------------------------------------------------------------------------
# Venue fade (deck ~slide 33) — far-venue depth drop | home trade
# ---------------------------------------------------------------------------

def venue_fade_events(
    home_trade_ts: NDArray[np.int64],
    home_trade_side: NDArray[np.floating] | NDArray[np.integer],
    far_tob_ts: NDArray[np.int64],
    far_bid: NDArray[np.float64],
    far_ask: NDArray[np.float64],
    far_bid_sz: NDArray[np.float64],
    far_ask_sz: NDArray[np.float64],
    *,
    tau_ms: float = 50.0,
    latency_ms: float = 5.0,
    drop_frac: float = 0.2,
) -> dict[str, Any]:
    """Far-venue same-side depth fade conditioned on home aggressor trade.

    Latency-aligned: look at far TOB in ``[t_home + latency, t_home + latency + τ]``.
    Desk use: SOR / xvenue risk. Caller must state RTT assumptions in EXP_REPORT.
    """
    ht = np.asarray(home_trade_ts, dtype=np.int64)
    side = _normalize_side(home_trade_side)
    ft = np.asarray(far_tob_ts, dtype=np.int64)
    fb = np.asarray(far_bid, dtype=np.float64)
    fa = np.asarray(far_ask, dtype=np.float64)
    fbs = np.asarray(far_bid_sz, dtype=np.float64)
    faz = np.asarray(far_ask_sz, dtype=np.float64)
    empty = {
        "trade_i": _empty_int(),
        "fade": _empty_int(),
        "drop_frac": _empty_float(),
        "side": _empty_float(),
        "n_trades": 0,
        "n_fade": 0,
        "tau_ms": float(tau_ms),
        "latency_ms": float(latency_ms),
        "theta": float(drop_frac),
    }
    if ht.size == 0 or ft.size < 2:
        return empty

    lat_ns = int(float(latency_ms) * NS_PER_MS)
    tau_ns = int(float(tau_ms) * NS_PER_MS)
    trade_is: list[int] = []
    fades: list[int] = []
    drops: list[float] = []
    sides: list[float] = []

    for k in range(int(ht.size)):
        t0 = int(ht[k]) + lat_ns
        t1 = t0 + tau_ns
        i0 = int(np.searchsorted(ft, t0, side="left")) - 1
        if i0 < 0:
            continue
        s = float(side[k])
        if s > 0:
            sz0 = float(faz[i0]) if np.isfinite(faz[i0]) else float("nan")
            px0 = float(fa[i0]) if np.isfinite(fa[i0]) else float("nan")
            sz_arr, px_arr = faz, fa
        else:
            sz0 = float(fbs[i0]) if np.isfinite(fbs[i0]) else float("nan")
            px0 = float(fb[i0]) if np.isfinite(fb[i0]) else float("nan")
            sz_arr, px_arr = fbs, fb
        if not (np.isfinite(sz0) and sz0 > 0 and np.isfinite(px0)):
            continue
        j_lo = int(np.searchsorted(ft, t0, side="left"))
        j_hi = int(np.searchsorted(ft, t1, side="right"))
        faded = 0
        max_drop = 0.0
        for j in range(max(j_lo, i0 + 1), j_hi):
            if not np.isfinite(sz_arr[j]):
                continue
            # Prefer same-price depth drop; still count retreat as fade
            drop = (sz0 - float(sz_arr[j])) / sz0
            if np.isfinite(px_arr[j]) and abs(px_arr[j] - px0) > 1e-12:
                # touch moved away — treat as full fade of prior quote
                drop = max(drop, 1.0)
            if drop > max_drop:
                max_drop = drop
            if drop >= float(drop_frac):
                faded = 1
                break
        trade_is.append(k)
        fades.append(faded)
        drops.append(float(max_drop))
        sides.append(s)

    fade_a = np.asarray(fades, dtype=np.int64)
    return {
        "trade_i": np.asarray(trade_is, dtype=np.int64),
        "fade": fade_a,
        "drop_frac": np.asarray(drops, dtype=np.float64),
        "side": np.asarray(sides, dtype=np.float64),
        "n_trades": int(len(trade_is)),
        "n_fade": int(fade_a.sum()) if fade_a.size else 0,
        "tau_ms": float(tau_ms),
        "latency_ms": float(latency_ms),
        "theta": float(drop_frac),
    }

def venue_fade_prob(events: dict[str, Any]) -> dict[str, Any]:
    """Aggregate far-venue fade probability."""
    return price_fade_prob(events)

# ---------------------------------------------------------------------------
# Momentum ignition (deck ~slide 34)
# ---------------------------------------------------------------------------

def ignition_events(
    ts_ns: NDArray[np.int64],
    px: NDArray[np.float64],
    qty: NDArray[np.float64] | None = None,
    *,
    bar_s: float = 1.0,
    phase1_bars: int = 5,
    phase2_bars: int = 5,
    phase3_bars: int = 10,
    vol_z: float = 2.0,
    mid_quiet_bps: float = 2.0,
    move_bps: float = 15.0,
    min_recovery: float = 0.3,
) -> dict[str, Any]:
    """3-phase momentum-ignition classifier on trade/mid bars.

    Deck fingerprint:
    - **Phase1:** volume ↑ and |Δmid| ≈ 0 (build pressure without move)
    - **Phase2:** large directional move + elevated volume
    - **Phase3:** lower volume + partial recovery

    Hard distinction vs ``crash.vshape_events`` / Nanex: those tag move+recovery
    geometry; ignition **requires** the quiet-mid high-vol pre-phase.
    """
    ts = np.asarray(ts_ns, dtype=np.int64)
    p = np.asarray(px, dtype=np.float64)
    q = np.ones(ts.shape, dtype=np.float64) if qty is None else np.asarray(qty, dtype=np.float64)
    empty = {
        "start_i": _empty_int(),
        "phase1_i": _empty_int(),
        "phase2_i": _empty_int(),
        "end_i": _empty_int(),
        "direction": _empty_int(),
        "move_bps": _empty_float(),
        "recovery": _empty_float(),
        "vol_z_p1": _empty_float(),
        "n_events": 0,
        "bar_s": float(bar_s),
    }
    m = np.isfinite(p) & (p > 0) & np.isfinite(ts)
    ts, p, q = ts[m], p[m], q[m]
    if ts.size < 20:
        return empty

    step = int(max(bar_s, 1e-6) * NS_PER_S)
    t0 = int(ts[0] // step * step)
    t1 = int(ts[-1] // step * step)
    n_bars = int((t1 - t0) // step) + 1
    if n_bars < phase1_bars + phase2_bars + phase3_bars + 3:
        return empty

    bar_ts = t0 + np.arange(n_bars, dtype=np.int64) * step
    bar_ix = ((ts - t0) // step).astype(np.int64)
    bar_ix = np.clip(bar_ix, 0, n_bars - 1)
    vol = np.bincount(bar_ix, weights=q, minlength=n_bars).astype(np.float64)
    # last mid per bar
    last_px = np.full(n_bars, np.nan)
    for i in range(int(ts.size)):
        last_px[int(bar_ix[i])] = p[i]
    # forward-fill
    for i in range(1, n_bars):
        if not np.isfinite(last_px[i]) and np.isfinite(last_px[i - 1]):
            last_px[i] = last_px[i - 1]
    if not np.isfinite(last_px).any():
        return empty

    # rolling baseline vol (exclude current windows via expanding past mean/std)
    vol_mu = np.full(n_bars, np.nan)
    vol_sd = np.full(n_bars, np.nan)
    csum = np.cumsum(vol)
    csum2 = np.cumsum(vol * vol)
    for i in range(n_bars):
        n = i  # past only
        if n < 10:
            continue
        s = float(csum[i - 1])
        s2 = float(csum2[i - 1])
        mu = s / n
        var = max(0.0, s2 / n - mu * mu)
        vol_mu[i] = mu
        vol_sd[i] = np.sqrt(var)

    p1, p2, p3 = int(phase1_bars), int(phase2_bars), int(phase3_bars)
    starts: list[int] = []
    p1_ends: list[int] = []
    p2_ends: list[int] = []
    ends: list[int] = []
    dirs: list[int] = []
    moves: list[float] = []
    recs: list[float] = []
    vzs: list[float] = []

    i = p1
    while i + p2 + p3 < n_bars:
        i1 = i
        i0 = i - p1
        i2 = i1 + p2
        i3 = i2 + p3
        if not (np.isfinite(last_px[i0]) and np.isfinite(last_px[i1 - 1]) and np.isfinite(last_px[i2 - 1])):
            i += 1
            continue
        # Phase1: elevated vol, quiet mid
        v1 = float(np.mean(vol[i0:i1]))
        mu = float(vol_mu[i1]) if np.isfinite(vol_mu[i1]) else float("nan")
        sd = float(vol_sd[i1]) if np.isfinite(vol_sd[i1]) else float("nan")
        if not (np.isfinite(mu) and np.isfinite(sd) and sd > 1e-12):
            i += 1
            continue
        z1 = (v1 - mu) / sd
        mid0 = float(last_px[i0])
        mid1 = float(last_px[i1 - 1])
        quiet_bps = abs(mid1 - mid0) / mid0 * 1e4 if mid0 > 0 else float("inf")
        if z1 < float(vol_z) or quiet_bps > float(mid_quiet_bps):
            i += 1
            continue
        # Phase2: large move + elevated vol
        mid2 = float(last_px[i2 - 1])
        move = (mid2 - mid1) / mid1 * 1e4 if mid1 > 0 else 0.0
        v2 = float(np.mean(vol[i1:i2]))
        z2 = (v2 - mu) / sd
        if abs(move) < float(move_bps) or z2 < float(vol_z) * 0.5:
            i += 1
            continue
        direction = 1 if move > 0 else -1
        # Phase3: lower vol + partial recovery toward mid1
        v3 = float(np.mean(vol[i2:i3]))
        mid3 = float(last_px[i3 - 1]) if np.isfinite(last_px[i3 - 1]) else mid2
        if v3 > v2:  # need cooling
            i += 1
            continue
        if direction > 0:
            # inv-V style: up then down toward mid1
            recovered = (mid2 - mid3) / (mid2 - mid1) if mid2 != mid1 else 0.0
        else:
            recovered = (mid3 - mid2) / (mid1 - mid2) if mid1 != mid2 else 0.0
        if recovered < float(min_recovery):
            i += 1
            continue

        starts.append(i0)
        p1_ends.append(i1)
        p2_ends.append(i2)
        ends.append(i3)
        dirs.append(direction)
        moves.append(float(abs(move)))
        recs.append(float(recovered))
        vzs.append(float(z1))
        i = i3  # non-overlapping
    return {
        "start_i": np.asarray(starts, dtype=np.int64),
        "phase1_i": np.asarray(p1_ends, dtype=np.int64),
        "phase2_i": np.asarray(p2_ends, dtype=np.int64),
        "end_i": np.asarray(ends, dtype=np.int64),
        "direction": np.asarray(dirs, dtype=np.int64),
        "move_bps": np.asarray(moves, dtype=np.float64),
        "recovery": np.asarray(recs, dtype=np.float64),
        "vol_z_p1": np.asarray(vzs, dtype=np.float64),
        "n_events": int(len(starts)),
        "bar_s": float(bar_s),
        "bar_ts": bar_ts,
        "bar_vol": vol,
        "bar_px": last_px,
    }

# ---------------------------------------------------------------------------
# Smoking / spoof proxy (deck ~slides 30–32) — high FP expected
# ---------------------------------------------------------------------------

def smoke_spoof_proxy(
    tob_ts: NDArray[np.int64],
    bid: NDArray[np.float64],
    ask: NDArray[np.float64],
    bid_sz: NDArray[np.float64],
    ask_sz: NDArray[np.float64],
    trade_ts: NDArray[np.int64],
    trade_side: NDArray[np.floating] | NDArray[np.integer],
    trade_px: NDArray[np.float64],
    *,
    attractive_improve_ticks: float = 1.0,
    cancel_ms: float = 200.0,
    away_ticks: float = 3.0,
    large_size_quantile: float = 0.9,
    tick_size: float | None = None,
) -> dict[str, Any]:
    """Smoking / layering proxies without firm IDs (expect high false positives).

    Two public-tape heuristics (deck smoking/spoof cartoons):

    1. **Attractive→cancel→worse fill:** touch improves by ≥1 tick, then same-side
       size vanishes within ``cancel_ms`` without a covering trade, then an
       aggressor prints through at a worse price.
    2. **Large away-from-touch add that cancels w/o trade:** size appears ≥
       ``away_ticks`` from touch (price jump), size in top quantile, then
       cancels with no trade match.

    Returns event arrays + frank ``n_*`` counts for FP rate reporting.
    """
    t = np.asarray(tob_ts, dtype=np.int64)
    b = np.asarray(bid, dtype=np.float64)
    a = np.asarray(ask, dtype=np.float64)
    bs = np.asarray(bid_sz, dtype=np.float64)
    az = np.asarray(ask_sz, dtype=np.float64)
    tt = np.asarray(trade_ts, dtype=np.int64)
    ts_side = _normalize_side(trade_side)
    tpx = np.asarray(trade_px, dtype=np.float64)

    if tick_size is None or not (tick_size and tick_size > 0):
        d = np.abs(np.diff(np.concatenate([b[np.isfinite(b)], a[np.isfinite(a)]])))
        d = d[d > 0]
        tick = float(np.median(d)) if d.size else 1e-4
    else:
        tick = float(tick_size)

    cancel_ns = int(float(cancel_ms) * NS_PER_MS)
    smoke_i: list[int] = []
    smoke_side: list[float] = []
    layer_i: list[int] = []
    layer_side: list[float] = []

    sizes = np.concatenate([bs[np.isfinite(bs)], az[np.isfinite(az)]])
    size_thr = float(np.nanquantile(sizes, large_size_quantile)) if sizes.size else float("inf")

    n = int(t.size)
    for i in range(1, n - 1):
        # attractive bid improve
        if (
            np.isfinite(b[i])
            and np.isfinite(b[i - 1])
            and b[i] >= b[i - 1] + attractive_improve_ticks * tick - 1e-12
            and np.isfinite(bs[i])
            and bs[i] > 0
        ):
            j_end = int(np.searchsorted(t, t[i] + cancel_ns, side="right"))
            for j in range(i + 1, min(j_end, n)):
                if not np.isfinite(b[j]):
                    continue
                if b[j] < b[i] - 0.5 * tick or (np.isfinite(bs[j]) and bs[j] < 0.2 * bs[i]):
                    # no covering sell trade near cancel
                    k0 = int(np.searchsorted(tt, t[i], side="left"))
                    k1 = int(np.searchsorted(tt, t[j], side="right"))
                    covered = False
                    for k in range(k0, k1):
                        if ts_side[k] < 0 and np.isfinite(tpx[k]) and abs(tpx[k] - b[i]) < 1.5 * tick:
                            covered = True
                            break
                    if not covered:
                        # worse fill after: buy aggressor above prior ask
                        for k in range(k1, min(k1 + 20, tt.size)):
                            if ts_side[k] > 0 and np.isfinite(tpx[k]) and np.isfinite(a[i]):
                                if tpx[k] > a[i] + 0.5 * tick:
                                    smoke_i.append(i)
                                    smoke_side.append(-1.0)
                                    break
                    break
        # symmetric ask improve
        if (
            np.isfinite(a[i])
            and np.isfinite(a[i - 1])
            and a[i] <= a[i - 1] - attractive_improve_ticks * tick + 1e-12
            and np.isfinite(az[i])
            and az[i] > 0
        ):
            j_end = int(np.searchsorted(t, t[i] + cancel_ns, side="right"))
            for j in range(i + 1, min(j_end, n)):
                if not np.isfinite(a[j]):
                    continue
                if a[j] > a[i] + 0.5 * tick or (np.isfinite(az[j]) and az[j] < 0.2 * az[i]):
                    k0 = int(np.searchsorted(tt, t[i], side="left"))
                    k1 = int(np.searchsorted(tt, t[j], side="right"))
                    covered = False
                    for k in range(k0, k1):
                        if ts_side[k] > 0 and np.isfinite(tpx[k]) and abs(tpx[k] - a[i]) < 1.5 * tick:
                            covered = True
                            break
                    if not covered:
                        for k in range(k1, min(k1 + 20, tt.size)):
                            if ts_side[k] < 0 and np.isfinite(tpx[k]) and np.isfinite(b[i]):
                                if tpx[k] < b[i] - 0.5 * tick:
                                    smoke_i.append(i)
                                    smoke_side.append(1.0)
                                    break
                    break

        # layering: large size appears via price jump away then cancels
        if (
            np.isfinite(b[i])
            and np.isfinite(b[i - 1])
            and b[i] <= b[i - 1] - away_ticks * tick
            and np.isfinite(bs[i])
            and bs[i] >= size_thr
        ):
            j_end = int(np.searchsorted(t, t[i] + cancel_ns, side="right"))
            for j in range(i + 1, min(j_end, n)):
                if np.isfinite(bs[j]) and bs[j] < 0.2 * bs[i]:
                    k0 = int(np.searchsorted(tt, t[i], side="left"))
                    k1 = int(np.searchsorted(tt, t[j], side="right"))
                    if k1 <= k0:
                        layer_i.append(i)
                        layer_side.append(-1.0)
                    break
        if (
            np.isfinite(a[i])
            and np.isfinite(a[i - 1])
            and a[i] >= a[i - 1] + away_ticks * tick
            and np.isfinite(az[i])
            and az[i] >= size_thr
        ):
            j_end = int(np.searchsorted(t, t[i] + cancel_ns, side="right"))
            for j in range(i + 1, min(j_end, n)):
                if np.isfinite(az[j]) and az[j] < 0.2 * az[i]:
                    k0 = int(np.searchsorted(tt, t[i], side="left"))
                    k1 = int(np.searchsorted(tt, t[j], side="right"))
                    if k1 <= k0:
                        layer_i.append(i)
                        layer_side.append(1.0)
                    break

    return {
        "smoke_i": np.asarray(smoke_i, dtype=np.int64),
        "smoke_side": np.asarray(smoke_side, dtype=np.float64),
        "layer_i": np.asarray(layer_i, dtype=np.int64),
        "layer_side": np.asarray(layer_side, dtype=np.float64),
        "n_smoke": int(len(smoke_i)),
        "n_layer": int(len(layer_i)),
        "tick_size": tick,
        "size_thr": size_thr,
        "cancel_ms": float(cancel_ms),
        "note": "high_FP_proxy_no_firm_id",
    }

# ---------------------------------------------------------------------------
# Clock clustering (deck ~slides 35–37)
# ---------------------------------------------------------------------------

def clock_cluster_scores(
    trade_ts: NDArray[np.int64],
    *,
    bin_ms: int = 1000,
) -> dict[str, Any]:
    """Histogram of fills by position within the UTC second / minute.

    Deck: clock hunting — excess activity at round clock patterns.
    ``bin_ms`` defaults to 1000 → second-of-minute (60 bins). Use 100 for
    decisecond-of-second patterns.
    """
    ts = np.asarray(trade_ts, dtype=np.int64)
    empty = {
        "bin_ms": int(bin_ms),
        "n_bins": 0,
        "counts": _empty_int(),
        "frac": _empty_float(),
        "n_trades": 0,
    }
    if ts.size == 0:
        return empty
    bin_ns = int(max(bin_ms, 1) * NS_PER_MS)
    # within-minute offset for second-of-minute; generalize to mod 60s
    period_ns = 60 * NS_PER_S
    if bin_ns > period_ns:
        period_ns = bin_ns * max(2, int(np.ceil(60_000 / bin_ms)))
    n_bins = int(period_ns // bin_ns)
    if n_bins < 2:
        return empty
    offset = (ts % period_ns) // bin_ns
    counts = np.bincount(offset.astype(np.int64), minlength=n_bins).astype(np.int64)
    frac = counts.astype(np.float64) / float(ts.size)
    return {
        "bin_ms": int(bin_ms),
        "n_bins": n_bins,
        "counts": counts,
        "frac": frac,
        "n_trades": int(ts.size),
        "period_s": float(period_ns / NS_PER_S),
    }

def clock_cluster_excess(
    scores: dict[str, Any],
    *,
    z_thresh: float = 3.0,
) -> dict[str, Any]:
    """Flag bins with excess fill mass vs uniform null."""
    counts = np.asarray(scores.get("counts", []), dtype=np.float64)
    n_bins = int(scores.get("n_bins", counts.size))
    n = int(scores.get("n_trades", 0))
    if n_bins < 2 or n < n_bins:
        return {
            "excess_bins": _empty_int(),
            "z": _empty_float(),
            "n_excess": 0,
            "max_z": float("nan"),
            "uniform_p": float("nan"),
        }
    expected = n / float(n_bins)
    # Poisson-ish z
    z = (counts - expected) / np.sqrt(max(expected, 1e-9))
    excess = np.flatnonzero(z >= float(z_thresh)).astype(np.int64)
    return {
        "excess_bins": excess,
        "z": z.astype(np.float64),
        "n_excess": int(excess.size),
        "max_z": float(np.max(z)),
        "uniform_p": 1.0 / float(n_bins),
        "expected_count": float(expected),
        "z_thresh": float(z_thresh),
    }

# ---------------------------------------------------------------------------
# OTR aggregate (deck ~slides 41–43) — venue policy metric only
# ---------------------------------------------------------------------------

def otr_aggregate(
    n_cancel: float | NDArray[np.floating] | int,
    n_trade: float | NDArray[np.floating] | int,
    *,
    venue: str | None = None,
    window_label: str | None = None,
) -> dict[str, Any]:
    """Venue-level order-to-trade (cancel/trade) ratio regimes.

    Deck: OTR as regulatory/policy metric. **No firm IDs** — aggregate only.
    Accepts scalars or equal-length arrays (e.g. per-bar from quote_storm).
    """
    c = np.asarray(n_cancel, dtype=np.float64).ravel()
    tr = np.asarray(n_trade, dtype=np.float64).ravel()
    if c.size != tr.size:
        raise ValueError("n_cancel and n_trade must have the same shape")
    with np.errstate(divide="ignore", invalid="ignore"):
        otr = np.where(tr > 0, c / tr, np.nan)
    return {
        "otr": otr if otr.size > 1 else float(otr[0]) if otr.size == 1 else float("nan"),
        "otr_mean": float(np.nanmean(otr)) if otr.size else float("nan"),
        "otr_median": float(np.nanmedian(otr)) if otr.size else float("nan"),
        "n_cancel_sum": float(np.nansum(c)),
        "n_trade_sum": float(np.nansum(tr)),
        "venue": venue,
        "window_label": window_label,
        "policy_only": True,
        "note": "no_participant_ids",
    }

# ---------------------------------------------------------------------------
# Size / latency panel (deck ~slides 10–20)
# ---------------------------------------------------------------------------

def size_latency_panel(
    trade_qty: NDArray[np.float64],
    tob_ts: NDArray[np.int64],
    *,
    trade_ts: NDArray[np.int64] | None = None,
    quantiles: tuple[float, ...] = (0.1, 0.25, 0.5, 0.75, 0.9, 0.99),
) -> dict[str, Any]:
    """Trade-size quantiles + TOB update Hz (reaction-time proxy).

    Deck: latency/size technology context for MM regimes — framing, not α.
    """
    q = np.asarray(trade_qty, dtype=np.float64)
    q = q[np.isfinite(q) & (q > 0)]
    t = np.asarray(tob_ts, dtype=np.int64)
    t = np.sort(t[np.isfinite(t)])
    size_q = {
        f"q{int(100 * qq)}": float(np.quantile(q, qq)) if q.size else float("nan")
        for qq in quantiles
    }
    if t.size >= 2:
        span_s = max((int(t[-1]) - int(t[0])) / NS_PER_S, 1e-9)
        update_hz = float(t.size / span_s)
        dt_ms = np.diff(t.astype(np.float64)) / NS_PER_MS
        med_dt_ms = float(np.median(dt_ms)) if dt_ms.size else float("nan")
    else:
        update_hz = float("nan")
        med_dt_ms = float("nan")
        span_s = 0.0

    trade_hz = float("nan")
    if trade_ts is not None:
        tt = np.asarray(trade_ts, dtype=np.int64)
        tt = np.sort(tt[np.isfinite(tt)])
        if tt.size >= 2:
            tspan = max((int(tt[-1]) - int(tt[0])) / NS_PER_S, 1e-9)
            trade_hz = float(tt.size / tspan)

    return {
        "n_trades_sized": int(q.size),
        "size_quantiles": size_q,
        "mean_size": float(np.mean(q)) if q.size else float("nan"),
        "tob_update_hz": update_hz,
        "tob_median_dt_ms": med_dt_ms,
        "tob_span_s": float(span_s),
        "trade_hz": trade_hz,
        "n_tob": int(t.size),
    }

# ---------------------------------------------------------------------------
# Overlap helpers vs crash / lob (rename gates)
# ---------------------------------------------------------------------------

def overlap_vs_crash(
    ign_start_ts: NDArray[np.int64],
    ign_end_ts: NDArray[np.int64],
    crash_start_ts: NDArray[np.int64],
    crash_end_ts: NDArray[np.int64],
    *,
    slack_s: float = 2.0,
    label: str = "nanex_or_vshape",
) -> dict[str, Any]:
    """Time-interval overlap between ignition and crash/V events.

    Accepts **absolute timestamps** (ns), not index space — converts to a
    shared synthetic clock for Jaccard via ``crash.event_overlap`` semantics
    without importing crash internals beyond optional reuse.

    Kill / Hold guidance: if ``frac_ignition_in_crash`` ≈ 1 and Phase1 adds no
    unique mass, treat as rename of Nanex/SSM/V.
    """
    a0 = np.asarray(ign_start_ts, dtype=np.int64)
    a1 = np.asarray(ign_end_ts, dtype=np.int64)
    b0 = np.asarray(crash_start_ts, dtype=np.int64)
    b1 = np.asarray(crash_end_ts, dtype=np.int64)
    slack = int(float(slack_s) * NS_PER_S)
    if a0.size == 0 or b0.size == 0:
        return {
            "label": label,
            "n_ignition": float(a0.size),
            "n_crash": float(b0.size),
            "n_overlap": 0.0,
            "frac_ignition_in_crash": float("nan"),
            "frac_crash_in_ignition": float("nan"),
            "jaccard": float("nan"),
            "slack_s": float(slack_s),
        }
    matched_a = np.zeros(a0.size, dtype=bool)
    matched_b = np.zeros(b0.size, dtype=bool)
    for i in range(a0.size):
        for j in range(b0.size):
            if matched_b[j]:
                continue
            if int(a0[i]) <= int(b1[j]) + slack and int(b0[j]) <= int(a1[i]) + slack:
                matched_a[i] = True
                matched_b[j] = True
                break
    n_ov = int(matched_a.sum())
    n_a, n_b = int(a0.size), int(b0.size)
    union = n_a + n_b - n_ov
    return {
        "label": label,
        "n_ignition": float(n_a),
        "n_crash": float(n_b),
        "n_overlap": float(n_ov),
        "frac_ignition_in_crash": float(n_ov / n_a) if n_a else float("nan"),
        "frac_crash_in_ignition": float(n_ov / n_b) if n_b else float("nan"),
        "jaccard": float(n_ov / union) if union else float("nan"),
        "slack_s": float(slack_s),
    }

def overlap_vs_lob_cancel(
    fade_trade_ts: NDArray[np.int64],
    fade_flags: NDArray[np.integer] | NDArray[np.floating],
    cancel_event_ts: NDArray[np.int64],
    *,
    slack_ms: float = 250.0,
) -> dict[str, Any]:
    """Overlap of post-trade fade positives vs lob cancel-proxy event times.

    Kill if fade events are essentially the same timestamps as unconditional
    ``tob_depletion_cancel_proxy`` cancels (rename gate).
    """
    ft = np.asarray(fade_trade_ts, dtype=np.int64)
    ff = np.asarray(fade_flags, dtype=np.float64)
    ct = np.asarray(cancel_event_ts, dtype=np.int64)
    slack = int(float(slack_ms) * NS_PER_MS)
    pos = ft[ff > 0]
    if pos.size == 0 or ct.size == 0:
        return {
            "n_fade": float(pos.size),
            "n_cancel": float(ct.size),
            "n_overlap": 0.0,
            "frac_fade_in_cancel": float("nan"),
            "slack_ms": float(slack_ms),
        }
    ct_sorted = np.sort(ct)
    n_ov = 0
    for t in pos:
        j = int(np.searchsorted(ct_sorted, t, side="left"))
        hit = False
        for k in (j - 1, j):
            if 0 <= k < ct_sorted.size and abs(int(ct_sorted[k]) - int(t)) <= slack:
                hit = True
                break
        if hit:
            n_ov += 1
    return {
        "n_fade": float(pos.size),
        "n_cancel": float(ct.size),
        "n_overlap": float(n_ov),
        "frac_fade_in_cancel": float(n_ov / pos.size),
        "slack_ms": float(slack_ms),
    }

def rename_gate(
    overlap: dict[str, Any],
    *,
    frac_key: str = "frac_ignition_in_crash",
    kill_frac: float = 0.85,
) -> dict[str, Any]:
    """Promote/Hold/Kill hint from an overlap dict.

    Returns ``decision`` in {``pass``, ``hold``, ``kill_rename``} plus reason.
    Desk still owns the final call; this is a mechanical gate helper.
    """
    frac = overlap.get(frac_key, overlap.get("frac_fade_in_cancel", float("nan")))
    try:
        f = float(frac)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        f = float("nan")
    n_ov = float(overlap.get("n_overlap", 0.0))
    if not np.isfinite(f):
        return {
            "decision": "hold",
            "reason": "insufficient_overlap_sample",
            "frac": f,
            "kill_frac": float(kill_frac),
        }
    if f >= float(kill_frac) and n_ov >= 3:
        return {
            "decision": "kill_rename",
            "reason": f"{frac_key}>={kill_frac}",
            "frac": f,
            "kill_frac": float(kill_frac),
        }
    if f >= 0.5:
        return {
            "decision": "hold",
            "reason": f"{frac_key}_elevated",
            "frac": f,
            "kill_frac": float(kill_frac),
        }
    return {
        "decision": "pass",
        "reason": "overlap_below_hold",
        "frac": f,
        "kill_frac": float(kill_frac),
    }

def ignition_bar_timestamps(ign: dict[str, Any]) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    """Map ignition bar indices → absolute ns using ``bar_ts`` from detector."""
    bar_ts = np.asarray(ign.get("bar_ts", []), dtype=np.int64)
    s = np.asarray(ign.get("start_i", []), dtype=np.int64)
    e = np.asarray(ign.get("end_i", []), dtype=np.int64)
    if bar_ts.size == 0 or s.size == 0:
        return _empty_int(), _empty_int()
    return bar_ts[s], bar_ts[np.clip(e - 1, 0, bar_ts.size - 1)]

# ---------------------------------------------------------------------------
# Pass-2 expand / info-lens helpers (desk dig — do not Promote renames)
# ---------------------------------------------------------------------------

def event_window_markout(
    event_ts: NDArray[np.int64],
    trade_ts: NDArray[np.int64],
    trade_side: NDArray[np.floating] | NDArray[np.integer],
    mid_ts: NDArray[np.int64],
    mid: NDArray[np.float64],
    *,
    pre_ms: float = 0.0,
    post_ms: float = 1000.0,
    horizon_ms: float = 1000.0,
    max_trades_per_event: int = 40,
) -> dict[str, Any]:
    """Mean signed markout (bps) for trades in ``[event+pre, event+post]``.

    Desk info lens: storm→adverse selection, fade→toxicity, ignition→impact.
    Positive mean ⇒ price continues with aggressor (adverse for resting MM).
    """
    et = np.asarray(event_ts, dtype=np.int64)
    tt = np.asarray(trade_ts, dtype=np.int64)
    side = _normalize_side(trade_side)
    mt = np.asarray(mid_ts, dtype=np.int64)
    mv = np.asarray(mid, dtype=np.float64)
    empty = {
        "n_events": 0,
        "n_trades": 0,
        "mean_bps": float("nan"),
        "median_bps": float("nan"),
        "per_event_mean": _empty_float(),
    }
    if et.size == 0 or tt.size == 0 or mt.size < 2:
        return empty
    pre_ns = int(float(pre_ms) * NS_PER_MS)
    post_ns = int(float(post_ms) * NS_PER_MS)
    h_ns = int(float(horizon_ms) * NS_PER_MS)
    i0 = _asof_idx(tt, mt)
    i1 = _asof_idx(tt + h_ns, mt)
    mid0 = np.full(tt.size, np.nan)
    mid1 = np.full(tt.size, np.nan)
    ok0 = (i0 >= 0) & (i0 < mt.size)
    ok1 = (i1 >= 0) & (i1 < mt.size) & (i1 > i0)
    mid0[ok0] = mv[i0[ok0]]
    mid1[ok1] = mv[i1[ok1]]
    mo = np.full(tt.size, np.nan)
    valid = ok0 & ok1 & np.isfinite(side) & (mid0 > 0) & np.isfinite(mid1)
    mo[valid] = side[valid] * 1e4 * (mid1[valid] - mid0[valid]) / mid0[valid]

    per_ev: list[float] = []
    n_tr = 0
    for e in et:
        lo, hi = int(e) + pre_ns, int(e) + post_ns
        m = (tt >= lo) & (tt <= hi) & np.isfinite(mo)
        if not m.any():
            continue
        idx = np.flatnonzero(m)
        if idx.size > max_trades_per_event:
            idx = idx[:max_trades_per_event]
        sub = mo[idx]
        per_ev.append(float(np.nanmean(sub)))
        n_tr += int(sub.size)
    arr = np.asarray(per_ev, dtype=np.float64)
    return {
        "n_events": int(arr.size),
        "n_trades": int(n_tr),
        "mean_bps": float(np.nanmean(arr)) if arr.size else float("nan"),
        "median_bps": float(np.nanmedian(arr)) if arr.size else float("nan"),
        "per_event_mean": arr,
        "pre_ms": float(pre_ms),
        "post_ms": float(post_ms),
        "horizon_ms": float(horizon_ms),
    }

def spread_irf_after_events(
    event_ts: NDArray[np.int64],
    tob_ts: NDArray[np.int64],
    bid: NDArray[np.float64],
    ask: NDArray[np.float64],
    *,
    lags_ms: tuple[float, ...] = (0.0, 50.0, 100.0, 250.0, 500.0, 1000.0, 2000.0),
    baseline_pre_ms: float = 1000.0,
) -> dict[str, Any]:
    """Impulse-response of quoted spread (bps) after event timestamps.

    Desk: fade→spread widen IRF / storm→liquidity thin. Returns mean Δspread
    vs pre-event baseline at each lag.
    """
    et = np.asarray(event_ts, dtype=np.int64)
    t = np.asarray(tob_ts, dtype=np.int64)
    b = np.asarray(bid, dtype=np.float64)
    a = np.asarray(ask, dtype=np.float64)
    mid = 0.5 * (b + a)
    with np.errstate(divide="ignore", invalid="ignore"):
        spr = np.where(mid > 0, 1e4 * (a - b) / mid, np.nan)
    lags = tuple(float(x) for x in lags_ms)
    empty = {
        "lags_ms": list(lags),
        "mean_delta_bps": [float("nan")] * len(lags),
        "n_events": 0,
        "baseline_mean_bps": float("nan"),
    }
    if et.size == 0 or t.size < 5:
        return empty
    pre_ns = int(float(baseline_pre_ms) * NS_PER_MS)
    deltas = {lag: [] for lag in lags}
    baselines: list[float] = []
    for e in et:
        i_ev = int(np.searchsorted(t, int(e), side="right") - 1)
        if i_ev < 1:
            continue
        i_pre0 = int(np.searchsorted(t, int(e) - pre_ns, side="left"))
        base_slice = spr[i_pre0:i_ev]
        base_slice = base_slice[np.isfinite(base_slice)]
        if base_slice.size < 2:
            continue
        base = float(np.nanmean(base_slice))
        if not np.isfinite(base):
            continue
        baselines.append(base)
        for lag in lags:
            j = int(np.searchsorted(t, int(e) + int(lag * NS_PER_MS), side="right") - 1)
            if j < 0 or j >= spr.size or not np.isfinite(spr[j]):
                continue
            deltas[lag].append(float(spr[j] - base))
    mean_d = [
        float(np.nanmean(deltas[lag])) if deltas[lag] else float("nan") for lag in lags
    ]
    return {
        "lags_ms": list(lags),
        "mean_delta_bps": mean_d,
        "n_events": int(len(baselines)),
        "baseline_mean_bps": float(np.nanmean(baselines)) if baselines else float("nan"),
        "n_obs_per_lag": [int(len(deltas[lag])) for lag in lags],
    }

def lead_lag_cascade(
    storm_ts: NDArray[np.int64],
    fade_ts: NDArray[np.int64],
    ignition_ts: NDArray[np.int64],
    *,
    windows_ms: tuple[float, ...] = (100.0, 250.0, 500.0, 1000.0, 2000.0, 5000.0),
) -> dict[str, Any]:
    """Lead-lag cascade: storm→fade→ignition forward hit rates.

    For each storm, P(fade within w) and P(ignition within w); for each fade,
    P(ignition within w). Desk sequence monitor — not α.
    """
    s = np.asarray(storm_ts, dtype=np.int64)
    f = np.asarray(fade_ts, dtype=np.int64)
    g = np.asarray(ignition_ts, dtype=np.int64)
    wins = tuple(float(x) for x in windows_ms)

    def _hit_rate(src: NDArray[np.int64], dst: NDArray[np.int64], w_ms: float) -> float:
        if src.size == 0 or dst.size == 0:
            return float("nan")
        w = int(w_ms * NS_PER_MS)
        hits = 0
        for t0 in src:
            j = int(np.searchsorted(dst, int(t0), side="left"))
            if j < dst.size and int(dst[j]) <= int(t0) + w:
                hits += 1
                continue
            # also allow dst slightly before? no — forward only
        return float(hits / src.size)

    out: dict[str, Any] = {
        "windows_ms": list(wins),
        "n_storm": int(s.size),
        "n_fade": int(f.size),
        "n_ignition": int(g.size),
        "storm_to_fade": [],
        "storm_to_ignition": [],
        "fade_to_ignition": [],
    }
    for w in wins:
        out["storm_to_fade"].append(_hit_rate(s, f, w))
        out["storm_to_ignition"].append(_hit_rate(s, g, w))
        out["fade_to_ignition"].append(_hit_rate(f, g, w))
    return out

def fade_tau_sensitivity(
    trade_ts: NDArray[np.int64],
    trade_side: NDArray[np.floating] | NDArray[np.integer],
    tob_ts: NDArray[np.int64],
    bid: NDArray[np.float64],
    ask: NDArray[np.float64],
    bid_sz: NDArray[np.float64],
    ask_sz: NDArray[np.float64],
    *,
    taus_ms: tuple[float, ...] = (25.0, 50.0, 100.0, 250.0, 500.0, 1000.0),
    drop_frac: float = 0.2,
    max_trades: int = 8000,
) -> dict[str, Any]:
    """P(fade) across τ grid — sensitivity of Filimonov fade clock."""
    tt = np.asarray(trade_ts, dtype=np.int64)
    if tt.size > max_trades:
        step = max(1, int(np.ceil(tt.size / max_trades)))
        idx = np.arange(0, tt.size, step, dtype=np.int64)
        tt = tt[idx]
        side = np.asarray(trade_side, dtype=np.float64)[idx]
    else:
        side = trade_side
    rows: list[dict[str, Any]] = []
    for tau in taus_ms:
        ev = price_fade_events(
            tt,
            side,
            tob_ts,
            bid,
            ask,
            bid_sz,
            ask_sz,
            tau_ms=float(tau),
            drop_frac=float(drop_frac),
        )
        pr = price_fade_prob(ev)
        rows.append(
            {
                "tau_ms": float(tau),
                "p_fade": pr["p_fade"],
                "n": pr["n"],
                "n_fade": int(ev["n_fade"]),
            }
        )
    return {
        "taus_ms": [float(t) for t in taus_ms],
        "p_fade": [float(r["p_fade"]) for r in rows],
        "n": [int(r["n"]) for r in rows],
        "n_fade": [int(r["n_fade"]) for r in rows],
        "drop_frac": float(drop_frac),
        "rows": rows,
    }

def size_storm_interaction(
    trade_ts: NDArray[np.int64],
    trade_qty: NDArray[np.float64],
    storm_ts: NDArray[np.int64],
    *,
    window_ms: float = 1000.0,
    n_quantiles: int = 4,
) -> dict[str, Any]:
    """Storm co-occurrence rate by trade-size quantile (size×storm).

    Desk: large prints near storms → exec throttle / size-cap candidate.
    """
    tt = np.asarray(trade_ts, dtype=np.int64)
    q = np.asarray(trade_qty, dtype=np.float64)
    st = np.asarray(storm_ts, dtype=np.int64)
    empty = {
        "n_trades": 0,
        "n_storm": int(st.size),
        "quantile_edges": [],
        "storm_rate": [],
        "n_per_q": [],
    }
    m = np.isfinite(q) & (q > 0) & np.isfinite(tt)
    tt, q = tt[m], q[m]
    if tt.size < 20:
        return empty
    w = int(float(window_ms) * NS_PER_MS)
    near = np.zeros(tt.size, dtype=np.float64)
    if st.size:
        for i, t0 in enumerate(tt):
            j = int(np.searchsorted(st, int(t0), side="left"))
            best = False
            if j < st.size and abs(int(st[j]) - int(t0)) <= w:
                best = True
            if j > 0 and abs(int(st[j - 1]) - int(t0)) <= w:
                best = True
            near[i] = 1.0 if best else 0.0
    qs = np.linspace(0, 1, int(n_quantiles) + 1)
    edges = np.quantile(q, qs)
    # uniquify edges
    edges = np.unique(edges)
    if edges.size < 3:
        return {
            **empty,
            "n_trades": int(tt.size),
            "storm_rate_all": float(np.mean(near)),
        }
    rates: list[float] = []
    counts: list[int] = []
    for i in range(edges.size - 1):
        lo, hi = float(edges[i]), float(edges[i + 1])
        if i == edges.size - 2:
            mask = (q >= lo) & (q <= hi)
        else:
            mask = (q >= lo) & (q < hi)
        counts.append(int(mask.sum()))
        rates.append(float(np.mean(near[mask])) if mask.any() else float("nan"))
    return {
        "n_trades": int(tt.size),
        "n_storm": int(st.size),
        "window_ms": float(window_ms),
        "quantile_edges": edges.tolist(),
        "storm_rate": rates,
        "n_per_q": counts,
        "storm_rate_all": float(np.mean(near)),
        "rate_q_hi_minus_lo": (
            float(rates[-1] - rates[0])
            if rates and np.isfinite(rates[0]) and np.isfinite(rates[-1])
            else float("nan")
        ),
    }

def clock_vs_funding_windows(
    trade_ts: NDArray[np.int64],
    *,
    funding_hours_utc: tuple[int, ...] = (0, 8, 16),
    window_min: float = 5.0,
    bin_ms: int = 1000,
) -> dict[str, Any]:
    """Compare clock-cluster excess inside vs outside funding/mark windows.

    Crypto adaptation of Filimonov clock hunting: funding/mark prints often
    cluster near :00. Returns max_z in-window vs out-of-window.
    """
    ts = np.asarray(trade_ts, dtype=np.int64)
    if ts.size < 100:
        return {
            "n_in": 0,
            "n_out": 0,
            "max_z_in": float("nan"),
            "max_z_out": float("nan"),
            "excess_ratio": float("nan"),
        }
    # seconds since midnight UTC
    day_ns = 86_400 * NS_PER_S
    sod = ts % day_ns
    win_ns = int(float(window_min) * 60 * NS_PER_S)
    in_mask = np.zeros(ts.size, dtype=bool)
    for h in funding_hours_utc:
        center = int(h) * 3600 * NS_PER_S
        # wrap-safe distance to hour mark
        dist = np.minimum(np.abs(sod - center), day_ns - np.abs(sod - center))
        in_mask |= dist <= win_ns
    scores_in = clock_cluster_scores(ts[in_mask], bin_ms=bin_ms)
    scores_out = clock_cluster_scores(ts[~in_mask], bin_ms=bin_ms)
    ex_in = clock_cluster_excess(scores_in)
    ex_out = clock_cluster_excess(scores_out)
    mz_in = float(ex_in.get("max_z", float("nan")))
    mz_out = float(ex_out.get("max_z", float("nan")))
    return {
        "n_in": int(in_mask.sum()),
        "n_out": int((~in_mask).sum()),
        "max_z_in": mz_in,
        "max_z_out": mz_out,
        "n_excess_in": int(ex_in.get("n_excess", 0)),
        "n_excess_out": int(ex_out.get("n_excess", 0)),
        "excess_ratio": (
            float(mz_in / mz_out) if np.isfinite(mz_in) and np.isfinite(mz_out) and mz_out > 0 else float("nan")
        ),
        "funding_hours_utc": list(funding_hours_utc),
        "window_min": float(window_min),
    }

def tod_event_heatmap(
    event_ts: NDArray[np.int64],
    *,
    hour_bins: int = 24,
    minute_bins: int = 12,
) -> dict[str, Any]:
    """UTC hour × minute-of-hour heatmap counts for event timestamps."""
    ts = np.asarray(event_ts, dtype=np.int64)
    H, M = int(hour_bins), int(minute_bins)
    grid = np.zeros((H, M), dtype=np.int64)
    if ts.size == 0:
        return {"grid": grid, "n": 0, "hour_bins": H, "minute_bins": M}
    day_ns = 86_400 * NS_PER_S
    sod = ts % day_ns
    hour = (sod // (3600 * NS_PER_S)).astype(np.int64) % H
    minute = ((sod % (3600 * NS_PER_S)) // (60 * NS_PER_S)).astype(np.int64)
    mb = np.clip(minute * M // 60, 0, M - 1)
    for h, m in zip(hour, mb):
        grid[int(h), int(m)] += 1
    return {
        "grid": grid,
        "n": int(ts.size),
        "hour_bins": H,
        "minute_bins": M,
        "hour_ marginal": grid.sum(axis=1),
        "peak_hour": int(np.argmax(grid.sum(axis=1))) if ts.size else -1,
    }

def ignition_phase1_unique_mass(
    ign: dict[str, Any],
    crash_starts: NDArray[np.int64],
    crash_ends: NDArray[np.int64],
    *,
    slack_ms: float = 2000.0,
) -> dict[str, Any]:
    """Fraction of ignition events whose Phase1 window is outside crash spans.

    Info / risk lens: unique-mass vs Nanex/SSM/V — high unique_mass supports
    escalate-vs-crash Hold; low unique_mass keeps rename Kill pressure.
    """
    starts, ends = ignition_bar_timestamps(ign)
    # prefer phase1 end if available
    bar_ts = np.asarray(ign.get("bar_ts", []), dtype=np.int64)
    p1 = np.asarray(ign.get("phase1_i", []), dtype=np.int64)
    if bar_ts.size and p1.size == starts.size:
        p1_ts = bar_ts[np.clip(p1, 0, bar_ts.size - 1)]
    else:
        p1_ts = starts
    cs = np.asarray(crash_starts, dtype=np.int64)
    ce = np.asarray(crash_ends, dtype=np.int64)
    slack = int(float(slack_ms) * NS_PER_MS)
    n = int(starts.size)
    if n == 0:
        return {"n": 0, "unique_mass": float("nan"), "n_unique": 0, "n_overlap": 0}
    unique = 0
    for s, p1t, e in zip(starts, p1_ts, ends):
        # overlap if any crash interval intersects [s-slack, e+slack]
        lo, hi = int(s) - slack, int(e) + slack
        hit = False
        if cs.size:
            for a, b in zip(cs, ce if ce.size == cs.size else cs):
                if int(a) <= hi and int(b) >= lo:
                    hit = True
                    break
                # also check phase1 stamp alone
                if abs(int(p1t) - int(a)) <= slack:
                    hit = True
                    break
        if not hit:
            unique += 1
    return {
        "n": n,
        "n_unique": int(unique),
        "n_overlap": int(n - unique),
        "unique_mass": float(unique / n),
        "slack_ms": float(slack_ms),
    }

def xvenue_fade_info_share(
    home_fade_ts: NDArray[np.int64],
    home_mid_ts: NDArray[np.int64],
    home_mid: NDArray[np.float64],
    far_mid_ts: NDArray[np.int64],
    far_mid: NDArray[np.float64],
    *,
    pre_ms: float = 2000.0,
    post_ms: float = 2000.0,
    bar_ms: float = 100.0,
    max_events: int = 80,
) -> dict[str, Any]:
    """Hasbrouck-lite info-share around home fade events (xvenue info lens).

    Aligns home/far mids on a calendar grid in ``[fade−pre, fade+post]`` and
    aggregates two-market IS bounds via ``continuous.hasbrouck_info_share_2``.
    Cross-link only — does not invent arb α.
    """
    # lazy import to keep hftpat free of hard continuous dep at module import
    from research.lib.continuous import hasbrouck_info_share_2

    ft = np.asarray(home_fade_ts, dtype=np.int64)
    ht = np.asarray(home_mid_ts, dtype=np.int64)
    hm = np.asarray(home_mid, dtype=np.float64)
    ft2 = np.asarray(far_mid_ts, dtype=np.int64)
    fm = np.asarray(far_mid, dtype=np.float64)
    if ft.size == 0 or ht.size < 20 or ft2.size < 20:
        return {"n_events": 0, "mean_is_home_lo": float("nan"), "mean_is_home_hi": float("nan")}
    if ft.size > max_events:
        rng = np.random.default_rng(17)
        ft = np.sort(rng.choice(ft, size=max_events, replace=False))
    pre = int(float(pre_ms) * NS_PER_MS)
    post = int(float(post_ms) * NS_PER_MS)
    step = int(float(bar_ms) * NS_PER_MS)
    lo_s: list[float] = []
    hi_s: list[float] = []
    n_ok = 0
    for e in ft:
        grid = np.arange(int(e) - pre, int(e) + post + 1, step, dtype=np.int64)
        if grid.size < 30:
            continue
        ih = _asof_idx(grid, ht)
        iff = _asof_idx(grid, ft2)
        ok = (ih >= 0) & (ih < ht.size) & (iff >= 0) & (iff < ft2.size)
        if int(ok.sum()) < 30:
            continue
        a = hm[ih[ok]]
        b = fm[iff[ok]]
        res = hasbrouck_info_share_2(a, b, lags=5)
        if not res.get("ok", False):
            continue
        lo = res.get("is_a_low")
        hi = res.get("is_a_high")
        if lo is None or hi is None or not (np.isfinite(lo) and np.isfinite(hi)):
            continue
        lo_s.append(float(lo))
        hi_s.append(float(hi))
        n_ok += 1
    return {
        "n_events": int(n_ok),
        "mean_is_home_lo": float(np.nanmean(lo_s)) if lo_s else float("nan"),
        "mean_is_home_hi": float(np.nanmean(hi_s)) if hi_s else float("nan"),
        "pre_ms": float(pre_ms),
        "post_ms": float(post_ms),
        "bar_ms": float(bar_ms),
    }
