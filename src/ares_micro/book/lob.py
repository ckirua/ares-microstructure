"""Limit-order book empirics proxies (Hasbrouck Part III / Sandas–Parlour–Foucault).

L0-only feeds cannot observe queue position or true OE fills. These helpers
build *proxies* from TOB + trades:
- time-to-touch / virtual fill hazard
- size-at-touch survival + TOB-depletion cancel proxies (public-tape hazard)
- same-side refill (Sandas backfill)
- Sandas depth-schedule L1 moments (when multilevel L2 snapshots exist)
- adverse markout after quote improvement (picking-off / free option)
- Parlour-style depth → aggressor-side associations
- discrete LO-event sequences vs continuous event intensity
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from ares_micro.book.tob import mid_price
from ares_micro.core.arrays import asof_idx
from ares_micro.core.constants import NS_PER_MS, NS_PER_S
from ares_micro.stats import bootstrap_ci, pearson_r_ci


def _tick_from_quotes(
    bid: NDArray[np.float64],
    ask: NDArray[np.float64],
    *,
    fallback: float = 1e-4,
) -> float:
    from ares_micro.book.tob import infer_tick

    t = infer_tick(np.concatenate([bid, ask]))
    if not np.isfinite(t) or t <= 0:
        return float(fallback)
    return float(t)


def time_to_touch(
    ts_ns: NDArray[np.int64],
    bid: NDArray[np.float64],
    ask: NDArray[np.float64],
    *,
    offsets_ticks: tuple[int, ...] = (0, 1, 2),
    max_horizon_ms: int = 30_000,
    sample_stride: int = 50,
    side: str = "buy",
) -> dict[str, Any]:
    """Virtual limit touch times (continuous-clock fill proxy).

    For a buy limit at ``L = bid - k·tick`` (k in ``offsets_ticks``), a *touch*
    is the first later quote with ``ask <= L`` (would cross). Censor at
    ``max_horizon_ms`` or end of sample.

    Units: times in ms. Update frequency: TOB cadence. No OE — this is a
    geometric touch proxy, not exchange fill confirmation.
    """
    t = np.asarray(ts_ns, dtype=np.int64)
    b = np.asarray(bid, dtype=np.float64)
    a = np.asarray(ask, dtype=np.float64)
    n = t.size
    tick = _tick_from_quotes(b, a)
    h_ns = int(max_horizon_ms) * NS_PER_MS
    out: dict[str, Any] = {
        "tick": tick,
        "side": side,
        "max_horizon_ms": max_horizon_ms,
        "sample_stride": sample_stride,
        "by_offset": {},
    }
    if n < sample_stride + 5:
        return out

    idxs = np.arange(0, n - 2, max(1, sample_stride), dtype=np.int64)
    # precompute first-touch index via running min ask / max bid for speed
    for k in offsets_ticks:
        times_ms: list[float] = []
        filled = 0
        censored = 0
        for i in idxs:
            i = int(i)
            j_end = int(np.searchsorted(t, t[i] + h_ns, side="right"))
            j_end = min(j_end, n)
            if j_end <= i + 1:
                censored += 1
                continue
            if side == "buy":
                L = b[i] - k * tick
                if not np.isfinite(L):
                    continue
                seg = a[i + 1 : j_end]
                ok = np.isfinite(seg) & (seg <= L + 1e-12)
                if ok.any():
                    j = i + 1 + int(np.argmax(ok))
                    times_ms.append(float((t[j] - t[i]) / 1e6))
                    filled += 1
                else:
                    censored += 1
            else:
                L = a[i] + k * tick
                if not np.isfinite(L):
                    continue
                seg = b[i + 1 : j_end]
                ok = np.isfinite(seg) & (seg >= L - 1e-12)
                if ok.any():
                    j = i + 1 + int(np.argmax(ok))
                    times_ms.append(float((t[j] - t[i]) / 1e6))
                    filled += 1
                else:
                    censored += 1
        arr = np.asarray(times_ms, dtype=np.float64)
        ci = bootstrap_ci(arr, n_boot=400, seed=41 + k) if arr.size else {
            "n": 0, "point": float("nan"), "lo": float("nan"), "hi": float("nan")
        }
        n_tot = filled + censored
        out["by_offset"][str(k)] = {
            "n_starts": int(n_tot),
            "n_touch": int(filled),
            "n_censored": int(censored),
            "touch_rate": float(filled / n_tot) if n_tot else float("nan"),
            "mean_touch_ms": ci["point"],
            "touch_ms_ci95": [ci.get("lo", float("nan")), ci.get("hi", float("nan"))],
            "p50_touch_ms": float(np.median(arr)) if arr.size else float("nan"),
        }
    return out


def same_side_refill(
    ts_ns: NDArray[np.int64],
    bid: NDArray[np.float64],
    ask: NDArray[np.float64],
    bid_sz: NDArray[np.float64],
    ask_sz: NDArray[np.float64],
    *,
    drop_frac: float = 0.3,
    horizons_ms: tuple[int, ...] = (100, 500, 1000, 5000),
) -> dict[str, Any]:
    """Sandas-style backfill proxy at L0 (same price).

    Event: best price unchanged, same-side size drops by ≥ ``drop_frac``.
    Outcome: within horizon, size recovers ≥50% of the drop *before* the
    best price worsens on that side.

    Conjecture 1 in notes: no backfill in pure Sandas — empirics reject if
    refill rates are systematically high.
    """
    t = np.asarray(ts_ns, dtype=np.int64)
    b = np.asarray(bid, dtype=np.float64)
    a = np.asarray(ask, dtype=np.float64)
    bs = np.asarray(bid_sz, dtype=np.float64)
    a_s = np.asarray(ask_sz, dtype=np.float64)
    n = t.size
    out: dict[str, Any] = {"drop_frac": drop_frac, "horizons_ms": list(horizons_ms), "sides": {}}

    for side, px, sz, worsen_fn in (
        (
            "bid",
            b,
            bs,
            lambda j, i: np.isfinite(b[j]) and b[j] < b[i] - 1e-12,
        ),
        (
            "ask",
            a,
            a_s,
            lambda j, i: np.isfinite(a[j]) and a[j] > a[i] + 1e-12,
        ),
    ):
        events: list[int] = []
        drops: list[float] = []
        for i in range(1, n):
            if not (np.isfinite(px[i]) and np.isfinite(px[i - 1]) and abs(px[i] - px[i - 1]) < 1e-12):
                continue
            if not (np.isfinite(sz[i]) and np.isfinite(sz[i - 1]) and sz[i - 1] > 0):
                continue
            drop = sz[i - 1] - sz[i]
            if drop / sz[i - 1] >= drop_frac and drop > 0:
                events.append(i)
                drops.append(float(drop))
        ev = np.asarray(events, dtype=np.int64)
        side_row: dict[str, Any] = {"n_events": int(ev.size), "by_horizon": {}}
        for h_ms in horizons_ms:
            h_ns = int(h_ms) * NS_PER_MS
            refill = 0
            worsen = 0
            neither = 0
            frac_rec: list[float] = []
            for idx, e in enumerate(ev):
                d0 = drops[idx]
                s0 = float(sz[e])
                j_end = int(np.searchsorted(t, t[e] + h_ns, side="right"))
                recovered = False
                worsened = False
                best_frac = 0.0
                for j in range(int(e) + 1, min(j_end, n)):
                    if worsen_fn(j, int(e)):
                        worsened = True
                        break
                    if abs(px[j] - px[e]) > 1e-12:
                        # price changed other direction counted separately
                        if (side == "bid" and px[j] > px[e]) or (side == "ask" and px[j] < px[e]):
                            break
                    if np.isfinite(sz[j]):
                        gain = sz[j] - s0
                        best_frac = max(best_frac, float(gain / d0) if d0 > 0 else 0.0)
                        if gain >= 0.5 * d0:
                            recovered = True
                            break
                if recovered:
                    refill += 1
                elif worsened:
                    worsen += 1
                else:
                    neither += 1
                frac_rec.append(best_frac)
            tot = refill + worsen + neither
            fr = np.asarray(frac_rec, dtype=np.float64)
            ci = bootstrap_ci(fr, n_boot=300, seed=17 + h_ms) if fr.size else {
                "point": float("nan"), "lo": float("nan"), "hi": float("nan")
            }
            side_row["by_horizon"][str(h_ms)] = {
                "n": int(tot),
                "refill_rate": float(refill / tot) if tot else float("nan"),
                "worsen_rate": float(worsen / tot) if tot else float("nan"),
                "mean_max_refill_frac": ci["point"],
                "refill_frac_ci95": [ci.get("lo", float("nan")), ci.get("hi", float("nan"))],
            }
        out["sides"][side] = side_row
    return out


def improve_adverse_markout(
    ts_ns: NDArray[np.int64],
    bid: NDArray[np.float64],
    ask: NDArray[np.float64],
    mid: NDArray[np.float64],
    *,
    horizons_ms: tuple[int, ...] = (100, 500, 1000, 5000),
) -> dict[str, Any]:
    """Picking-off / free-option proxy after quote improvement.

    Bid improvement (bid↑): adverse if mid subsequently falls.
    Ask improvement (ask↓): adverse if mid subsequently rises.
    Report signed *adverse* markout in bps (positive ⇒ improver hurt).
    """
    t = np.asarray(ts_ns, dtype=np.int64)
    b = np.asarray(bid, dtype=np.float64)
    a = np.asarray(ask, dtype=np.float64)
    m = np.asarray(mid, dtype=np.float64)
    n = t.size
    if n >= 2:
        bid_imp = (
            np.flatnonzero(
                np.isfinite(b[1:]) & np.isfinite(b[:-1]) & (b[1:] > b[:-1] + 1e-12)
            )
            + 1
        )
        ask_imp = (
            np.flatnonzero(
                np.isfinite(a[1:]) & np.isfinite(a[:-1]) & (a[1:] < a[:-1] - 1e-12)
            )
            + 1
        )
    else:
        bid_imp = np.zeros(0, dtype=np.int64)
        ask_imp = np.zeros(0, dtype=np.int64)

    out: dict[str, Any] = {
        "n_bid_improve": int(bid_imp.size),
        "n_ask_improve": int(ask_imp.size),
        "by_horizon": {},
    }
    for h_ms in horizons_ms:
        h_ns = int(h_ms) * NS_PER_MS
        chunks: list[NDArray[np.float64]] = []
        if bid_imp.size:
            j = np.searchsorted(t, t[bid_imp] + h_ns, side="right") - 1
            ok = (j > bid_imp) & (j < n) & np.isfinite(m[bid_imp]) & np.isfinite(m[j]) & (m[bid_imp] > 0)
            if np.any(ok):
                iok, jok = bid_imp[ok], j[ok]
                chunks.append((-1e4 * (m[jok] - m[iok]) / m[iok]).astype(np.float64))
        if ask_imp.size:
            j = np.searchsorted(t, t[ask_imp] + h_ns, side="right") - 1
            ok = (j > ask_imp) & (j < n) & np.isfinite(m[ask_imp]) & np.isfinite(m[j]) & (m[ask_imp] > 0)
            if np.any(ok):
                iok, jok = ask_imp[ok], j[ok]
                chunks.append((1e4 * (m[jok] - m[iok]) / m[iok]).astype(np.float64))
        arr = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float64)
        ci = bootstrap_ci(arr, n_boot=500, seed=23 + h_ms) if arr.size else {
            "n": 0, "point": float("nan"), "lo": float("nan"), "hi": float("nan")
        }
        out["by_horizon"][str(h_ms)] = {
            "n": int(arr.size),
            "mean_adverse_bps": ci["point"],
            "ci95": [ci.get("lo", float("nan")), ci.get("hi", float("nan"))],
            "p50_bps": float(np.median(arr)) if arr.size else float("nan"),
        }
    return out


def parlour_depth_aggressor(
    trade_ts: NDArray[np.int64],
    side: NDArray[np.float64],
    tob_ts: NDArray[np.int64],
    bid_sz: NDArray[np.float64],
    ask_sz: NDArray[np.float64],
) -> dict[str, Any]:
    """Parlour (1998) crowding-out proxies on L0 depth.

    Same-side depth vs market-order aggressor:
    - high ask_sz → more sell aggressors (crowding on ask)
    - high bid_sz → more buy aggressors
    Opposite-side:
    - high bid_sz → fewer sell aggressors (limit sells more attractive)
    """
    tt = np.asarray(trade_ts, dtype=np.int64)
    s = np.asarray(side, dtype=np.float64)
    mt = np.asarray(tob_ts, dtype=np.int64)
    bs = np.asarray(bid_sz, dtype=np.float64)
    a_s = np.asarray(ask_sz, dtype=np.float64)
    i0 = asof_idx(tt, mt)
    valid = (i0 >= 0) & (i0 < mt.size) & np.isfinite(s) & (s != 0)
    if int(valid.sum()) < 50:
        return {"n": int(valid.sum()), "ok": False}
    i0 = i0[valid]
    s = s[valid]
    bsz, asz = bs[i0], a_s[i0]
    sell = (s < 0).astype(np.float64)
    buy = (s > 0).astype(np.float64)
    # standardize depths
    def _z(x: NDArray[np.float64]) -> NDArray[np.float64]:
        m = np.isfinite(x)
        out = np.full_like(x, np.nan)
        if m.sum() < 3:
            return out
        mu, sd = float(np.nanmean(x)), float(np.nanstd(x))
        if sd <= 0:
            return out
        out[m] = (x[m] - mu) / sd
        return out

    zb, za = _z(bsz), _z(asz)
    return {
        "n": int(s.size),
        "ok": True,
        "same_ask_vs_sell": pearson_r_ci(za, sell, n_boot=400, seed=31),
        "same_bid_vs_buy": pearson_r_ci(zb, buy, n_boot=400, seed=32),
        "opp_bid_vs_sell": pearson_r_ci(zb, sell, n_boot=400, seed=33),
        "opp_ask_vs_buy": pearson_r_ci(za, buy, n_boot=400, seed=34),
        "mean_ask_sz_given_sell": float(np.nanmean(asz[s < 0])),
        "mean_ask_sz_given_buy": float(np.nanmean(asz[s > 0])),
        "mean_bid_sz_given_buy": float(np.nanmean(bsz[s > 0])),
        "mean_bid_sz_given_sell": float(np.nanmean(bsz[s < 0])),
    }


def lob_event_clocks(
    ts_ns: NDArray[np.int64],
    bid: NDArray[np.float64],
    ask: NDArray[np.float64],
    bid_sz: NDArray[np.float64],
    ask_sz: NDArray[np.float64],
    *,
    bar_ns: int = NS_PER_S,
    size_eps_frac: float = 0.05,
) -> dict[str, Any]:
    """Discrete LO-event sequence + continuous event intensity.

    Event codes (disc): +1 bid improve, -1 bid worsen, +2 ask improve, -2 ask worsen,
    +3 bid refill-ish size↑, -3 bid size↓, +4 ask size↑, -4 ask size↓ (price fixed).
    """
    t = np.asarray(ts_ns, dtype=np.int64)
    b = np.asarray(bid, dtype=np.float64)
    a = np.asarray(ask, dtype=np.float64)
    bs = np.asarray(bid_sz, dtype=np.float64)
    a_s = np.asarray(ask_sz, dtype=np.float64)
    if t.size < 2:
        c = np.zeros(0, dtype=np.int64)
        et = np.zeros(0, dtype=np.int64)
    else:
        codes = np.zeros(t.size - 1, dtype=np.int64)
        b_ok = np.isfinite(b[1:]) & np.isfinite(b[:-1])
        codes = np.where(b_ok & (b[1:] > b[:-1] + 1e-12), 1, codes)
        codes = np.where(b_ok & (codes == 0) & (b[1:] < b[:-1] - 1e-12), -1, codes)
        bs_ok = (
            b_ok
            & (codes == 0)
            & np.isfinite(bs[1:])
            & np.isfinite(bs[:-1])
            & (bs[:-1] > 0)
        )
        ch_b = np.zeros(t.size - 1, dtype=np.float64)
        ch_b[bs_ok] = (bs[1:][bs_ok] - bs[:-1][bs_ok]) / bs[:-1][bs_ok]
        codes = np.where(bs_ok & (ch_b >= size_eps_frac), 3, codes)
        codes = np.where(bs_ok & (ch_b <= -size_eps_frac), -3, codes)
        a_ok = (codes == 0) & np.isfinite(a[1:]) & np.isfinite(a[:-1])
        codes = np.where(a_ok & (a[1:] < a[:-1] - 1e-12), 2, codes)
        codes = np.where(a_ok & (codes == 0) & (a[1:] > a[:-1] + 1e-12), -2, codes)
        as_ok = (
            (codes == 0)
            & np.isfinite(a[1:])
            & np.isfinite(a[:-1])
            & np.isfinite(a_s[1:])
            & np.isfinite(a_s[:-1])
            & (a_s[:-1] > 0)
        )
        ch_a = np.zeros(t.size - 1, dtype=np.float64)
        ch_a[as_ok] = (a_s[1:][as_ok] - a_s[:-1][as_ok]) / a_s[:-1][as_ok]
        codes = np.where(as_ok & (ch_a >= size_eps_frac), 4, codes)
        codes = np.where(as_ok & (ch_a <= -size_eps_frac), -4, codes)
        hit = codes != 0
        c = codes[hit]
        et = t[1:][hit]
    # discrete: event-type ACF at lag 1 (improve persistence)
    ac1 = float("nan")
    if c.size > 20:
        x = c[:-1].astype(np.float64)
        y = c[1:].astype(np.float64)
        x0, y0 = x - x.mean(), y - y.mean()
        den = float(np.sqrt((x0 * x0).sum() * (y0 * y0).sum()))
        ac1 = float((x0 * y0).sum() / den) if den > 0 else float("nan")

    # continuous intensity
    intens = {"n_bars": 0, "mean_lambda": float("nan"), "ac1": float("nan")}
    if et.size >= 5:
        t0, t1 = int(et.min()), int(et.max())
        grid = np.arange(t0, t1 + 1, bar_ns, dtype=np.int64)
        if grid.size >= 3:
            idx = np.searchsorted(et, grid, side="left")
            counts = np.diff(idx).astype(np.float64)
            # λ per second
            lam = counts / (bar_ns / NS_PER_S)
            ci = bootstrap_ci(lam, n_boot=300, seed=51)
            if lam.size > 5:
                x = lam[:-1] - lam[:-1].mean()
                y = lam[1:] - lam[1:].mean()
                den = float(np.sqrt((x * x).sum() * (y * y).sum()))
                lac1 = float((x * y).sum() / den) if den > 0 else float("nan")
            else:
                lac1 = float("nan")
            intens = {
                "n_bars": int(lam.size),
                "mean_lambda": ci["point"],
                "lambda_ci95": [ci["lo"], ci["hi"]],
                "ac1": lac1,
            }

    improve = int(((c == 1) | (c == 2)).sum())
    worsen = int(((c == -1) | (c == -2)).sum())
    return {
        "n_events": int(c.size),
        "n_improve": improve,
        "n_worsen": worsen,
        "improve_share": float(improve / c.size) if c.size else float("nan"),
        "disc_event_ac1": ac1,
        "cont_intensity": intens,
    }


def size_at_touch_survival(
    ts_ns: NDArray[np.int64],
    bid: NDArray[np.float64],
    ask: NDArray[np.float64],
    bid_sz: NDArray[np.float64],
    ask_sz: NDArray[np.float64],
    trade_ts: NDArray[np.int64],
    trade_side: NDArray[np.float64],
    trade_qty: NDArray[np.float64],
    *,
    offsets_ticks: tuple[int, ...] = (0, 1),
    size_quantiles: tuple[float, ...] = (0.25, 0.5, 0.75),
    max_horizon_ms: int = 30_000,
    sample_stride: int = 80,
    side: str = "buy",
) -> dict[str, Any]:
    """Public-tape fill hazard: first-touch + size-at-touch survival.

    Extends geometric touch (``time_to_touch``) with a *size* dimension:
    after a virtual buy limit at ``L = bid - k·tick`` with resting size equal to
    the contemporaneous same-side L0 size (or a quantile thereof), deplete that
    size with subsequent *sell*-aggressor trade qty while the ask is at/through
    ``L``. Censor at ``max_horizon_ms``.

    Not OE: no own-order ack/fill — trade-tape depletion is a public proxy.
    """
    t = np.asarray(ts_ns, dtype=np.int64)
    b = np.asarray(bid, dtype=np.float64)
    a = np.asarray(ask, dtype=np.float64)
    bs = np.asarray(bid_sz, dtype=np.float64)
    az = np.asarray(ask_sz, dtype=np.float64)
    tt = np.asarray(trade_ts, dtype=np.int64)
    ts_side = np.asarray(trade_side, dtype=np.float64)
    tq = np.asarray(trade_qty, dtype=np.float64)
    tick = _tick_from_quotes(b, a)
    h_ns = int(max_horizon_ms) * NS_PER_MS
    n = t.size
    out: dict[str, Any] = {
        "tick": tick,
        "side": side,
        "max_horizon_ms": max_horizon_ms,
        "by_offset": {},
        "by_size_q": {},
    }
    if n < sample_stride + 5 or tt.size < 50:
        return out

    idxs = np.arange(0, n - 2, max(1, sample_stride), dtype=np.int64)
    same_sz = bs if side == "buy" else az
    finite_sz = same_sz[np.isfinite(same_sz) & (same_sz > 0)]
    q_cuts = (
        {str(q): float(np.quantile(finite_sz, q)) for q in size_quantiles}
        if finite_sz.size >= 20
        else {}
    )
    out["size_quantile_cuts"] = q_cuts

    # aggressor that hits our resting side: buy limit filled by sell aggressors (side<0)
    hit_sign = -1.0 if side == "buy" else 1.0

    def _run(k: int, size0: float | None) -> dict[str, Any]:
        times_ms: list[float] = []
        filled = 0
        censored = 0
        for i in idxs:
            i = int(i)
            j_end = int(np.searchsorted(t, t[i] + h_ns, side="right"))
            j_end = min(j_end, n)
            if j_end <= i + 1:
                censored += 1
                continue
            if side == "buy":
                L = b[i] - k * tick
                s0 = float(size0) if size0 is not None else float(bs[i])
            else:
                L = a[i] + k * tick
                s0 = float(size0) if size0 is not None else float(az[i])
            if not (np.isfinite(L) and np.isfinite(s0) and s0 > 0):
                continue
            # trades in (t[i], t[j_end])
            lo = int(np.searchsorted(tt, t[i], side="right"))
            hi = int(np.searchsorted(tt, t[i] + h_ns, side="right"))
            rem = s0
            done_t = None
            for j in range(lo, hi):
                # require geometric touch: opposite quote through L
                qi = int(np.searchsorted(t, tt[j], side="right") - 1)
                if qi < 0:
                    continue
                if side == "buy":
                    if not (np.isfinite(a[qi]) and a[qi] <= L + 1e-12):
                        continue
                else:
                    if not (np.isfinite(b[qi]) and b[qi] >= L - 1e-12):
                        continue
                if not (np.isfinite(ts_side[j]) and ts_side[j] * hit_sign > 0):
                    continue
                if not (np.isfinite(tq[j]) and tq[j] > 0):
                    continue
                rem -= float(tq[j])
                if rem <= 0:
                    done_t = float((tt[j] - t[i]) / 1e6)
                    break
            if done_t is not None:
                times_ms.append(done_t)
                filled += 1
            else:
                censored += 1
        arr = np.asarray(times_ms, dtype=np.float64)
        ci = bootstrap_ci(arr, n_boot=350, seed=61 + k) if arr.size else {
            "n": 0, "point": float("nan"), "lo": float("nan"), "hi": float("nan")
        }
        n_tot = filled + censored
        return {
            "n_starts": int(n_tot),
            "n_fill_proxy": int(filled),
            "n_censored": int(censored),
            "fill_proxy_rate": float(filled / n_tot) if n_tot else float("nan"),
            "mean_fill_ms": ci["point"],
            "fill_ms_ci95": [ci.get("lo", float("nan")), ci.get("hi", float("nan"))],
            "p50_fill_ms": float(np.median(arr)) if arr.size else float("nan"),
            "size0": float(size0) if size0 is not None else float("nan"),
        }

    for k in offsets_ticks:
        out["by_offset"][str(k)] = _run(k, None)
    # size quantile stratification at offset 0 (touch)
    for q_str, cut in q_cuts.items():
        out["by_size_q"][q_str] = _run(0, cut)
    # monotone check: larger resting size ⇒ lower fill_proxy_rate @ same offset
    rates = [
        out["by_size_q"][str(q)].get("fill_proxy_rate", float("nan"))
        for q in size_quantiles
        if str(q) in out["by_size_q"]
    ]
    mono = False
    if len(rates) >= 2:
        mono = all(
            np.isfinite(rates[i]) and np.isfinite(rates[i + 1]) and rates[i] >= rates[i + 1] - 1e-9
            for i in range(len(rates) - 1)
        )
    out["size_monotone_lower_fill"] = bool(mono)
    return out


def tob_depletion_cancel_proxy(
    ts_ns: NDArray[np.int64],
    bid: NDArray[np.float64],
    ask: NDArray[np.float64],
    bid_sz: NDArray[np.float64],
    ask_sz: NDArray[np.float64],
    trade_ts: NDArray[np.int64],
    trade_side: NDArray[np.float64],
    trade_qty: NDArray[np.float64],
    *,
    drop_frac: float = 0.2,
    trade_match_ms: int = 250,
) -> dict[str, Any]:
    """Cancel vs fill-depletion proxies from L0 TOB size drops.

    Event: best price unchanged, same-side size drops ≥ ``drop_frac``.
    Classify within ``trade_match_ms``:
    - **fill_proxy**: opposite-aggressor trade(s) with qty covering ≥50% of drop
    - **cancel_proxy**: no such trade match (pull / cancel / invisible fill)
    - **mixed**: some trade flow but <50% of drop
    """
    t = np.asarray(ts_ns, dtype=np.int64)
    b = np.asarray(bid, dtype=np.float64)
    a = np.asarray(ask, dtype=np.float64)
    bs = np.asarray(bid_sz, dtype=np.float64)
    az = np.asarray(ask_sz, dtype=np.float64)
    tt = np.asarray(trade_ts, dtype=np.int64)
    ts_side = np.asarray(trade_side, dtype=np.float64)
    tq = np.asarray(trade_qty, dtype=np.float64)
    match_ns = int(trade_match_ms) * NS_PER_MS
    out: dict[str, Any] = {"drop_frac": drop_frac, "trade_match_ms": trade_match_ms, "sides": {}}

    for side_name, px, sz, hit_sign in (
        ("bid", b, bs, -1.0),  # sell aggressors hit bids
        ("ask", a, az, 1.0),
    ):
        n_fill = n_cancel = n_mixed = 0
        drop_fracs: list[float] = []
        for i in range(1, t.size):
            if not (np.isfinite(px[i]) and np.isfinite(px[i - 1]) and abs(px[i] - px[i - 1]) < 1e-12):
                continue
            if not (np.isfinite(sz[i]) and np.isfinite(sz[i - 1]) and sz[i - 1] > 0):
                continue
            drop = float(sz[i - 1] - sz[i])
            if drop / sz[i - 1] < drop_frac or drop <= 0:
                continue
            drop_fracs.append(drop / float(sz[i - 1]))
            lo = int(np.searchsorted(tt, t[i] - match_ns, side="left"))
            hi = int(np.searchsorted(tt, t[i] + match_ns, side="right"))
            matched = 0.0
            for j in range(lo, hi):
                if np.isfinite(ts_side[j]) and ts_side[j] * hit_sign > 0 and np.isfinite(tq[j]) and tq[j] > 0:
                    matched += float(tq[j])
            if matched >= 0.5 * drop:
                n_fill += 1
            elif matched <= 1e-12:
                n_cancel += 1
            else:
                n_mixed += 1
        tot = n_fill + n_cancel + n_mixed
        fr = np.asarray(drop_fracs, dtype=np.float64)
        ci = bootstrap_ci(fr, n_boot=300, seed=71) if fr.size else {
            "point": float("nan"), "lo": float("nan"), "hi": float("nan")
        }
        out["sides"][side_name] = {
            "n_events": int(tot),
            "fill_proxy_share": float(n_fill / tot) if tot else float("nan"),
            "cancel_proxy_share": float(n_cancel / tot) if tot else float("nan"),
            "mixed_share": float(n_mixed / tot) if tot else float("nan"),
            "n_fill_proxy": int(n_fill),
            "n_cancel_proxy": int(n_cancel),
            "n_mixed": int(n_mixed),
            "mean_drop_frac": ci["point"],
            "drop_frac_ci95": [ci.get("lo", float("nan")), ci.get("hi", float("nan"))],
        }
    # pooled
    nf = sum(out["sides"][s]["n_fill_proxy"] for s in out["sides"])
    nc = sum(out["sides"][s]["n_cancel_proxy"] for s in out["sides"])
    nm = sum(out["sides"][s]["n_mixed"] for s in out["sides"])
    tot = nf + nc + nm
    out["pooled"] = {
        "n_events": int(tot),
        "fill_proxy_share": float(nf / tot) if tot else float("nan"),
        "cancel_proxy_share": float(nc / tot) if tot else float("nan"),
        "mixed_share": float(nm / tot) if tot else float("nan"),
    }
    return out


def sandas_depth_moments(
    snap_ts: NDArray[np.int64],
    side: NDArray[np.int64],
    level: NDArray[np.int64],
    qty: NDArray[np.float64],
    price_ticks: NDArray[np.int64],
    snapshot_id: NDArray[np.int64],
    *,
    max_level: int = 5,
    ask_level_offset: int = 20,
) -> dict[str, Any]:
    """Sandas / Glosten L1 depth-schedule moments from multilevel L2 snaps.

    Builds per-snapshot depth ``Q_k`` (k=0..max_level) on each side, reports
    E[Q_k], decay Q_k/Q_0, and reduced-form moment Corr(cumDepth_0:k, |Δmid|)
    across consecutive snapshots. This is **not** full Sandas GMM (break-even
    depths vs structural impact) — ship as L1 diagnostics when depth>1 exists.

    HL warehouse encoding: bid levels 0..19, ask levels 20..39 (offset 20).
    """
    st = np.asarray(snap_ts, dtype=np.int64)
    sd = np.asarray(side, dtype=np.int64)
    lv = np.asarray(level, dtype=np.int64)
    q = np.asarray(qty, dtype=np.float64)
    px = np.asarray(price_ticks, dtype=np.int64)
    sid = np.asarray(snapshot_id, dtype=np.int64)
    uniq = np.unique(sid)
    out: dict[str, Any] = {
        "n_rows": int(sid.size),
        "n_snapshots": int(uniq.size),
        "max_level": int(max_level),
        "ask_level_offset": int(ask_level_offset),
        "ok": False,
    }
    if uniq.size < 10:
        return out

    # level matrices: rows=snaps, cols=0..max_level
    Qb = np.full((uniq.size, max_level + 1), np.nan)
    Qa = np.full((uniq.size, max_level + 1), np.nan)
    bid0 = np.full(uniq.size, np.nan)
    ask0 = np.full(uniq.size, np.nan)
    ts_u = np.full(uniq.size, 0, dtype=np.int64)
    sid_to_i = {int(s): i for i, s in enumerate(uniq)}
    for i in range(sid.size):
        si = sid_to_i.get(int(sid[i]))
        if si is None:
            continue
        ts_u[si] = int(st[i])
        s = int(sd[i])
        raw_l = int(lv[i])
        if s == 1:
            lev = raw_l
            if 0 <= lev <= max_level and np.isfinite(q[i]):
                Qb[si, lev] = float(q[i])
            if lev == 0 and np.isfinite(px[i]):
                bid0[si] = float(px[i])
        elif s == 2:
            lev = raw_l - ask_level_offset if raw_l >= ask_level_offset else raw_l
            if 0 <= lev <= max_level and np.isfinite(q[i]):
                Qa[si, lev] = float(q[i])
            if lev == 0 and np.isfinite(px[i]):
                ask0[si] = float(px[i])
    mid = mid_price(bid0, ask0)

    def _side_moments(Q: NDArray[np.float64], label: str) -> dict[str, Any]:
        means = []
        decays_rom = []  # ratio of means E[Qk]/E[Q0]
        decays_mor = []  # mean of ratios (can explode on thin L0)
        for k in range(max_level + 1):
            col = Q[:, k]
            m = col[np.isfinite(col) & (col >= 0)]
            means.append(float(np.mean(m)) if m.size else float("nan"))
            if k == 0:
                decays_rom.append(1.0 if m.size else float("nan"))
                decays_mor.append(1.0 if m.size else float("nan"))
            else:
                q0 = Q[:, 0]
                e0 = float(np.nanmean(q0)) if np.isfinite(q0).any() else float("nan")
                ek = float(np.nanmean(col)) if np.isfinite(col).any() else float("nan")
                decays_rom.append(float(ek / e0) if e0 and e0 > 0 and np.isfinite(ek) else float("nan"))
                ok = np.isfinite(col) & np.isfinite(q0) & (q0 > 0)
                decays_mor.append(float(np.mean(col[ok] / q0[ok])) if ok.any() else float("nan"))
        # cum depth 0..k vs |Δmid|
        dmid = np.full(uniq.size, np.nan)
        dmid[1:] = np.abs(np.diff(mid))
        corrs = {}
        for k in range(max_level + 1):
            cum = np.nansum(Q[:, : k + 1], axis=1)
            x = cum[:-1]
            y = dmid[1:]
            msk = np.isfinite(x) & np.isfinite(y) & np.isfinite(mid[:-1])
            if int(msk.sum()) >= 30:
                corrs[str(k)] = pearson_r_ci(x[msk], y[msk], n_boot=300, seed=81 + k)
            else:
                corrs[str(k)] = {
                    "n": int(msk.sum()),
                    "r": float("nan"),
                    "lo": float("nan"),
                    "hi": float("nan"),
                }
        return {
            "side": label,
            "mean_Q": means,
            "decay_Qk_over_Q0": decays_rom,
            "decay_mean_of_ratios": decays_mor,
            "corr_cumQ_abs_dmid": corrs,
            "n_finite_L0": int(np.isfinite(Q[:, 0]).sum()),
        }

    bid_m = _side_moments(Qb, "bid")
    ask_m = _side_moments(Qa, "ask")
    # pooled decay shape: mean decay across sides
    decay = [
        float(np.nanmean([bid_m["decay_Qk_over_Q0"][k], ask_m["decay_Qk_over_Q0"][k]]))
        for k in range(max_level + 1)
    ]
    # Promote-ready shape: depth not concentrated only at L0 (some behind-touch size)
    behind = float(np.nanmean(decay[1:])) if len(decay) > 1 else float("nan")
    out.update(
        {
            "ok": True,
            "bid": bid_m,
            "ask": ask_m,
            "pooled_decay_Qk_over_Q0": decay,
            "mean_behind_touch_decay": behind,
            "n_mid_moves": int(np.isfinite(mid).sum()),
            "span_ns": int(ts_u.max() - ts_u.min()) if ts_u.size else 0,
        }
    )
    return out


def qty_moment_ceiling(
    qty: NDArray[np.float64],
    *,
    powers: tuple[float, ...] = (1.0, 1.5, 2.0, 2.5, 3.0, 4.0),
    trunc_fracs: tuple[float, ...] = (0.9, 0.95, 0.99, 0.995),
) -> dict[str, Any]:
    """Ch.0/2 Gabaix-style moment ceiling diagnostic on trade size.

    Book: volume moments may exist only up to ~1.5. We report raw power means
    and truncated-variance ratios as truncation → 1 (explosion ⇒ infinite Var).
    """
    q = np.asarray(qty, dtype=np.float64)
    q = q[np.isfinite(q) & (q > 0)]
    out: dict[str, Any] = {"n": int(q.size), "powers": {}, "trunc_var_ratio": {}, "ok": False}
    if q.size < 200:
        return out
    for p in powers:
        out["powers"][str(p)] = float(np.mean(np.power(q, p)))
    # truncated variance: Var(q | q≤q_α) / Var(q | q≤q_0.9)
    base_cut = float(np.quantile(q, 0.9))
    base = q[q <= base_cut]
    base_var = float(np.var(base)) if base.size > 10 else float("nan")
    ratios = []
    for f in trunc_fracs:
        cut = float(np.quantile(q, f))
        sub = q[q <= cut]
        v = float(np.var(sub)) if sub.size > 10 else float("nan")
        r = v / base_var if base_var and base_var > 0 and np.isfinite(v) else float("nan")
        out["trunc_var_ratio"][str(f)] = r
        ratios.append(r)
    # ceiling claim: variance grows with truncation (ratio@0.995 >> ratio@0.9)
    r99 = out["trunc_var_ratio"].get("0.995", float("nan"))
    r90 = out["trunc_var_ratio"].get("0.9", float("nan"))
    out["var_inflation_0p995_over_0p9"] = (
        float(r99 / r90) if np.isfinite(r99) and np.isfinite(r90) and r90 > 0 else float("nan")
    )
    out["ok"] = True
    out["mean"] = float(np.mean(q))
    out["p50"] = float(np.median(q))
    out["p99"] = float(np.quantile(q, 0.99))
    return out
