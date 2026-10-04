r"""Huang–Ranaldo–Schrimpf–Somogyi (2021) constrained-dealer objects.

Implements cross-venue / triangular LOP gap (VLOOP), arb-cost proxy (TCOST),
price inefficiency measure (PIM = VLOOP + |TCOST|), public dealer-constraint
proxies (DCM), first principal component DCM̂, and liquidity-elasticity
helpers (regime-split correlations).

**Hard distinction vs ``continuous.py`` Cont–Kukanov OFI:** that module is
order-flow imbalance on a single book. This module is *cross-venue LOP +
dealer-constraint* measurement for ``research/books/cd_me/``. Do **not** merge
the APIs; Pass-2 tables may join both on the same windows.

Paper spirit: Huang et al. (Nov 2021) Eqs. 2–3 (SSRN 3960577). Crypto mapping
uses public TOB mids across Hyperliquid + Deribit + Kraken (not CLS FX
triplets) and public funding/basis/vol/imbalance proxies (not bank VaR/CDS).

Public surface::

    relative_half_spread, vloop_pair, vloop_cross_venue
    tcost_from_spreads, pim_from_components
    align_tob_panel
    realized_vol, trade_imbalance, dcm_proxies, dcm_pc1
    elasticity_corr, regime_split_corr, logistic_G
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
from numpy.typing import NDArray

from ares_micro.book.spreads import quoted_spread_bps
from ares_micro.book.tob import mid_price
from ares_micro.core.arrays import asof_join, normalize_side
from ares_micro.core.constants import NS_PER_S
from ares_micro.stats import pearson_r


# ---------------------------------------------------------------------------
# Spreads / VLOOP / TCOST / PIM
# ---------------------------------------------------------------------------

def relative_half_spread(
    bid: NDArray[np.floating],
    ask: NDArray[np.floating],
) -> NDArray[np.floating]:
    """Relative half-spread (ask-bid)/(2*mid). Invalid rows → nan."""
    qs = quoted_spread_bps(bid, ask)
    out = np.full_like(qs, np.nan, dtype=np.float64)
    ok = np.isfinite(qs)
    out[ok] = qs[ok] / 2e4
    return out


def vloop_pair(
    mid_i: NDArray[np.floating],
    mid_j: NDArray[np.floating],
) -> NDArray[np.floating]:
    """Pairwise LOP gap: |log(mid_i / mid_j)| on aligned arrays."""
    mi = np.asarray(mid_i, dtype=np.float64)
    mj = np.asarray(mid_j, dtype=np.float64)
    out = np.full(mi.shape, np.nan, dtype=np.float64)
    ok = np.isfinite(mi) & np.isfinite(mj) & (mi > 0) & (mj > 0)
    out[ok] = np.abs(np.log(mi[ok] / mj[ok]))
    return out


def vloop_cross_venue(
    mids: Mapping[str, NDArray[np.floating]],
    *,
    pairs: Sequence[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Cross-venue VLOOP on a named mid panel.

    ``mids`` maps venue → aligned mid array (same length / clock).
    Returns per-pair series plus ``vloop_max`` (max pairwise gap) and
    ``vloop_mean`` (mean of finite pairwise gaps).
    """
    names = list(mids.keys())
    if pairs is None:
        pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1 :]]
    pair_series: dict[str, NDArray[np.floating]] = {}
    stack: list[NDArray[np.floating]] = []
    n = None
    for a, b in pairs:
        if a not in mids or b not in mids:
            continue
        v = vloop_pair(mids[a], mids[b])
        key = f"{a}|{b}"
        pair_series[key] = v
        stack.append(v)
        n = int(v.size) if n is None else n
    if not stack or n is None:
        empty = np.zeros(0, dtype=np.float64)
        return {
            "pairs": pair_series,
            "vloop_max": empty,
            "vloop_mean": empty,
            "n": 0,
        }
    mat = np.vstack(stack)
    finite = np.isfinite(mat)
    with np.errstate(invalid="ignore"):
        # manual nanmax/nanmean to avoid All-NaN warnings on sparse TOB
        vmax = np.where(finite.any(axis=0), np.nanmax(np.where(finite, mat, -np.inf), axis=0), np.nan)
        cnt = finite.sum(axis=0)
        vsum = np.nansum(np.where(finite, mat, 0.0), axis=0)
        vmean = np.where(cnt > 0, vsum / cnt, np.nan)
    vmax = np.asarray(vmax, dtype=np.float64)
    # restore true nans where we used -inf sentinel on empty cols
    vmax[~finite.any(axis=0)] = np.nan
    vmean = np.asarray(vmean, dtype=np.float64)
    return {
        "pairs": pair_series,
        "vloop_max": vmax,
        "vloop_mean": vmean,
        "n": int(n),
        "pair_keys": list(pair_series.keys()),
    }


def tcost_from_spreads(
    half_spreads: Sequence[NDArray[np.floating]] | Mapping[str, NDArray[np.floating]],
    *,
    fee_bps: float = 0.0,
) -> NDArray[np.floating]:
    """Arb-cost proxy: sum of relative half-spreads (+ optional fee in decimal).

    Paper TCOST is signed along the arb direction; for PIM we take absolute
    cost of crossing both legs. ``fee_bps`` is converted to relative units
    (bps / 1e4) and added once per leg count.
    """
    if isinstance(half_spreads, Mapping):
        series = list(half_spreads.values())
    else:
        series = list(half_spreads)
    if not series:
        return np.zeros(0, dtype=np.float64)
    mat = np.vstack([np.asarray(s, dtype=np.float64) for s in series])
    with np.errstate(all="ignore"):
        cost = np.nansum(mat, axis=0)
    fee = float(fee_bps) / 1e4 * float(mat.shape[0])
    if fee != 0.0:
        cost = cost + fee
    return cost


def pim_from_components(
    vloop: NDArray[np.floating],
    tcost: NDArray[np.floating],
    *,
    require_positive_vloop: bool = True,
) -> NDArray[np.floating]:
    """PIM = VLOOP + |TCOST| (paper Eq. 2–3 spirit).

    When ``require_positive_vloop``, rows with VLOOP ≤ 0 (or nan) are nan —
    no inefficiency without a LOP gap.
    """
    v = np.asarray(vloop, dtype=np.float64)
    t = np.asarray(tcost, dtype=np.float64)
    out = np.full(v.shape, np.nan, dtype=np.float64)
    ok = np.isfinite(v) & np.isfinite(t)
    if require_positive_vloop:
        ok = ok & (v > 0)
    out[ok] = v[ok] + np.abs(t[ok])
    return out


# ---------------------------------------------------------------------------
# Alignment helpers
# ---------------------------------------------------------------------------

def align_tob_panel(
    venue_tob: Mapping[str, Mapping[str, Any]],
    *,
    grid_ns: NDArray[np.integer] | None = None,
    dt_s: float = 5.0,
    max_lag_s: float = 30.0,
    day_start_ns: int | None = None,
    day_end_ns: int | None = None,
) -> dict[str, Any]:
    """Latency-align multi-venue TOB onto a common UTC grid.

    Each ``venue_tob[v]`` must provide ``ts`` (ns) and either ``mid`` or
    ``bid``/``ask``. Returns aligned ``mid``, ``bid``, ``ask``, half-spreads,
    and meta (coverage per venue).
    """
    max_lag_ns = int(float(max_lag_s) * NS_PER_S)
    step = int(float(dt_s) * NS_PER_S)

    cleaned: dict[str, dict[str, NDArray[Any]]] = {}
    t_lo: int | None = None
    t_hi: int | None = None
    for venue, tob in venue_tob.items():
        ts = np.asarray(tob["ts"], dtype=np.int64)
        bid = np.asarray(tob.get("bid", tob.get("mid")), dtype=np.float64)
        ask = np.asarray(tob.get("ask", tob.get("mid")), dtype=np.float64)
        if "mid" in tob:
            mid = np.asarray(tob["mid"], dtype=np.float64)
        else:
            mid = mid_price(bid, ask)
        if ts.size == 0:
            continue
        order = np.argsort(ts, kind="mergesort")
        ts, mid, bid, ask = ts[order], mid[order], bid[order], ask[order]
        cleaned[str(venue)] = {"ts": ts, "mid": mid, "bid": bid, "ask": ask}
        t_lo = int(ts[0]) if t_lo is None else min(t_lo, int(ts[0]))
        t_hi = int(ts[-1]) if t_hi is None else max(t_hi, int(ts[-1]))

    if not cleaned:
        empty = np.zeros(0, dtype=np.int64)
        return {
            "ts": empty,
            "mid": {},
            "bid": {},
            "ask": {},
            "half_spread": {},
            "coverage": {},
            "dt_s": float(dt_s),
            "n": 0,
        }

    if grid_ns is None:
        lo = int(day_start_ns) if day_start_ns is not None else int(t_lo // step * step)
        hi = int(day_end_ns) if day_end_ns is not None else int(t_hi // step * step)
        if hi < lo:
            lo, hi = hi, lo
        n_bin = int((hi - lo) // step) + 1
        grid = lo + np.arange(max(n_bin, 0), dtype=np.int64) * step
    else:
        grid = np.asarray(grid_ns, dtype=np.int64)

    mids: dict[str, NDArray[np.floating]] = {}
    bids: dict[str, NDArray[np.floating]] = {}
    asks: dict[str, NDArray[np.floating]] = {}
    hs: dict[str, NDArray[np.floating]] = {}
    coverage: dict[str, float] = {}
    for venue, arr in cleaned.items():
        mids[venue] = asof_join(
            grid, arr["ts"], arr["mid"], max_lag_ns=max_lag_ns, sort_ref=True
        )
        bids[venue] = asof_join(
            grid, arr["ts"], arr["bid"], max_lag_ns=max_lag_ns, sort_ref=True
        )
        asks[venue] = asof_join(
            grid, arr["ts"], arr["ask"], max_lag_ns=max_lag_ns, sort_ref=True
        )
        hs[venue] = relative_half_spread(bids[venue], asks[venue])
        coverage[venue] = float(np.isfinite(mids[venue]).mean()) if grid.size else 0.0

    return {
        "ts": grid,
        "mid": mids,
        "bid": bids,
        "ask": asks,
        "half_spread": hs,
        "coverage": coverage,
        "dt_s": float(dt_s),
        "n": int(grid.size),
        "venues": list(cleaned.keys()),
    }


# ---------------------------------------------------------------------------
# DCM proxies / PC1
# ---------------------------------------------------------------------------

def realized_vol(
    log_px: NDArray[np.floating],
    *,
    window: int = 12,
) -> NDArray[np.floating]:
    """Rolling realized vol of log-returns (std of Δlog over ``window``)."""
    x = np.asarray(log_px, dtype=np.float64)
    out = np.full(x.shape, np.nan, dtype=np.float64)
    if x.size < 2:
        return out
    r = np.diff(x, prepend=np.nan)
    w = max(int(window), 2)
    # rolling std via cumulative sums of r and r^2 (vectorized windows)
    r0 = np.where(np.isfinite(r), r, 0.0)
    m = np.isfinite(r).astype(np.float64)
    cs_pad = np.concatenate([[0.0], np.cumsum(r0)])
    cs2_pad = np.concatenate([[0.0], np.cumsum(r0 * r0)])
    cm_pad = np.concatenate([[0.0], np.cumsum(m)])
    i = np.arange(w - 1, x.size, dtype=np.int64)
    if i.size == 0:
        return out
    j0 = i - w + 1
    n = cm_pad[i + 1] - cm_pad[j0]
    s = cs_pad[i + 1] - cs_pad[j0]
    s2 = cs2_pad[i + 1] - cs2_pad[j0]
    ok = n >= max(w // 2, 2)
    var = np.zeros_like(n)
    var[ok] = (s2[ok] - (s[ok] * s[ok]) / n[ok]) / np.maximum(n[ok] - 1.0, 1.0)
    var = np.maximum(var, 0.0)
    out[i[ok]] = np.sqrt(var[ok])
    return out


def trade_imbalance(
    side: NDArray[np.floating],
    qty: NDArray[np.floating] | None = None,
    *,
    window: int = 60,
) -> NDArray[np.floating]:
    """Signed trade-imbalance inventory proxy on a trade clock.

    ``side`` should be +1 buy / −1 sell (aggressor). Optional ``qty`` weights.
    Returns rolling mean imbalance in (−1, 1).
    """
    s = normalize_side(side)
    if qty is None:
        w = np.ones_like(s)
    else:
        w = np.asarray(qty, dtype=np.float64)
        w = np.where(np.isfinite(w) & (w > 0), w, 0.0)
    signed = np.where(np.isfinite(s), s * w, 0.0)
    abs_w = np.where(np.isfinite(s), w, 0.0)
    out = np.full(s.shape, np.nan, dtype=np.float64)
    win = max(int(window), 1)
    cs_pad = np.concatenate([[0.0], np.cumsum(signed)])
    cw_pad = np.concatenate([[0.0], np.cumsum(abs_w)])
    i = np.arange(win - 1, s.size, dtype=np.int64)
    if i.size == 0:
        return out
    j0 = i - win + 1
    num = cs_pad[i + 1] - cs_pad[j0]
    den = cw_pad[i + 1] - cw_pad[j0]
    ok = den > 0
    out[i[ok]] = num[ok] / den[ok]
    return out


def dcm_proxies(
    *,
    funding: NDArray[np.floating] | None = None,
    basis: NDArray[np.floating] | None = None,
    rv: NDArray[np.floating] | None = None,
    imbalance: NDArray[np.floating] | None = None,
) -> dict[str, NDArray[np.floating]]:
    """Public dealer-constraint proxy bundle (abs levels where signed).

    Returns dict with available keys: ``abs_funding``, ``abs_basis``, ``rv``,
    ``abs_imbalance``. Missing inputs omitted.
    """
    out: dict[str, NDArray[np.floating]] = {}
    if funding is not None:
        out["abs_funding"] = np.abs(np.asarray(funding, dtype=np.float64))
    if basis is not None:
        out["abs_basis"] = np.abs(np.asarray(basis, dtype=np.float64))
    if rv is not None:
        out["rv"] = np.asarray(rv, dtype=np.float64)
    if imbalance is not None:
        out["abs_imbalance"] = np.abs(np.asarray(imbalance, dtype=np.float64))
    return out


def dcm_pc1(
    proxies: Mapping[str, NDArray[np.floating]],
    *,
    zscore: bool = True,
) -> dict[str, Any]:
    """First principal component of DCM proxies (row-aligned).

    Standardizes columns (optional), drops rows with any nan, returns PC1
    series (nan where input invalid), loadings, explained variance fraction.
    """
    keys = [k for k, v in proxies.items() if np.asarray(v).size]
    if not keys:
        return {
            "pc1": np.zeros(0, dtype=np.float64),
            "loadings": {},
            "explained_var": float("nan"),
            "keys": [],
            "n_valid": 0,
        }
    mat = np.column_stack([np.asarray(proxies[k], dtype=np.float64) for k in keys])
    n = mat.shape[0]
    pc1 = np.full(n, np.nan, dtype=np.float64)
    valid = np.all(np.isfinite(mat), axis=1)
    n_valid = int(valid.sum())
    if n_valid < max(len(keys) + 1, 5):
        return {
            "pc1": pc1,
            "loadings": {k: float("nan") for k in keys},
            "explained_var": float("nan"),
            "keys": keys,
            "n_valid": n_valid,
        }
    X = mat[valid].copy()
    if zscore:
        mu = X.mean(axis=0)
        sd = X.std(axis=0)
        sd = np.where(sd > 1e-12, sd, 1.0)
        X = (X - mu) / sd
    # SVD PCA
    Xc = X - X.mean(axis=0)
    _, s, vt = np.linalg.svd(Xc, full_matrices=False)
    scores = Xc @ vt[0]
    # orient so mean abs_funding loading (if present) is non-negative
    load = vt[0].copy()
    if "abs_funding" in keys:
        i = keys.index("abs_funding")
        if load[i] < 0:
            load = -load
            scores = -scores
    elif load[0] < 0:
        load = -load
        scores = -scores
    pc1[valid] = scores
    var = (s ** 2)
    explained = float(var[0] / var.sum()) if var.sum() > 0 else float("nan")
    return {
        "pc1": pc1,
        "loadings": {k: float(load[i]) for i, k in enumerate(keys)},
        "explained_var": explained,
        "keys": keys,
        "n_valid": n_valid,
    }


# ---------------------------------------------------------------------------
# Elasticity / regime helpers
# ---------------------------------------------------------------------------

def elasticity_corr(
    volume: NDArray[np.floating],
    pim: NDArray[np.floating],
    *,
    min_n: int = 20,
) -> dict[str, Any]:
    """Pearson corr(volume, PIM) — paper liquidity-elasticity object."""
    v = np.asarray(volume, dtype=np.float64)
    p = np.asarray(pim, dtype=np.float64)
    m = np.isfinite(v) & np.isfinite(p)
    n = int(m.sum())
    if n < min_n:
        return {"corr": float("nan"), "n": n, "ok": False}
    return {"corr": pearson_r(v[m], p[m]), "n": n, "ok": True}


def regime_split_corr(
    volume: NDArray[np.floating],
    pim: NDArray[np.floating],
    dcm: NDArray[np.floating],
    *,
    high_q: float = 0.75,
    low_q: float = 0.25,
    min_n: int = 15,
) -> dict[str, Any]:
    """Elasticity corr in unconstrained (DCM low) vs constrained (DCM high).

    Paper prediction: |elasticity| drops (corr closer to 0 / less negative
    volume↑→inefficiency↓) when dealers are constrained — we report both
    regime corrs and Δ = corr_high − corr_low for desk inspection.
    """
    v = np.asarray(volume, dtype=np.float64)
    p = np.asarray(pim, dtype=np.float64)
    d = np.asarray(dcm, dtype=np.float64)
    m = np.isfinite(v) & np.isfinite(p) & np.isfinite(d)
    if int(m.sum()) < min_n * 2:
        return {
            "ok": False,
            "corr_low": float("nan"),
            "corr_high": float("nan"),
            "delta": float("nan"),
            "n_low": 0,
            "n_high": 0,
            "q_low": float("nan"),
            "q_high": float("nan"),
        }
    ql = float(np.nanquantile(d[m], low_q))
    qh = float(np.nanquantile(d[m], high_q))
    low = m & (d <= ql)
    high = m & (d >= qh)
    c_low = elasticity_corr(v[low], p[low], min_n=min_n)
    c_high = elasticity_corr(v[high], p[high], min_n=min_n)
    delta = (
        float(c_high["corr"] - c_low["corr"])
        if c_low["ok"] and c_high["ok"]
        else float("nan")
    )
    return {
        "ok": bool(c_low["ok"] and c_high["ok"]),
        "corr_low": c_low["corr"],
        "corr_high": c_high["corr"],
        "delta": delta,
        "n_low": c_low["n"],
        "n_high": c_high["n"],
        "q_low": ql,
        "q_high": qh,
        "low_q": float(low_q),
        "high_q": float(high_q),
    }


def logistic_G(
    dcm: NDArray[np.floating],
    *,
    gamma: float = 1.0,
    c: float | None = None,
) -> NDArray[np.floating]:
    """LSTAR-style smooth transition G(DCM; γ, c) ∈ (0, 1).

    ``c`` defaults to sample median of finite DCM. Used as a continuous
    constrained-regime weight (Pass-1 helper; full LSTAR panel is a sibling
    package).
    """
    d = np.asarray(dcm, dtype=np.float64)
    out = np.full(d.shape, np.nan, dtype=np.float64)
    finite = np.isfinite(d)
    if not finite.any():
        return out
    center = float(np.nanmedian(d)) if c is None else float(c)
    g = float(gamma)
    # numerically stable logistic
    z = np.clip(g * (d[finite] - center), -60.0, 60.0)
    out[finite] = 1.0 / (1.0 + np.exp(-z))
    return out


def bucket_panel(
    ts_ns: NDArray[np.integer],
    values: Mapping[str, NDArray[np.floating]],
    *,
    bucket_s: float = 3600.0,
) -> dict[str, Any]:
    """Mean-aggregate aligned series into fixed UTC buckets (default hourly)."""
    ts = np.asarray(ts_ns, dtype=np.int64)
    step = int(float(bucket_s) * NS_PER_S)
    if ts.size == 0 or step <= 0:
        return {"ts": np.zeros(0, dtype=np.int64), "means": {}, "n": 0, "counts": np.zeros(0, dtype=np.int64)}
    t0 = int(ts[0] // step * step)
    bin_id = ((ts - t0) // step).astype(np.int64)
    n_bins = int(bin_id.max()) + 1 if bin_id.size else 0
    centers = t0 + (np.arange(n_bins, dtype=np.int64) + 1) * step // 2
    counts = np.bincount(bin_id, minlength=n_bins).astype(np.int64)
    means: dict[str, NDArray[np.floating]] = {}
    for k, arr in values.items():
        a = np.asarray(arr, dtype=np.float64)
        w = np.where(np.isfinite(a), 1.0, 0.0)
        a0 = np.where(np.isfinite(a), a, 0.0)
        s = np.bincount(bin_id, weights=a0, minlength=n_bins)
        c = np.bincount(bin_id, weights=w, minlength=n_bins)
        m = np.full(n_bins, np.nan, dtype=np.float64)
        ok = c > 0
        m[ok] = s[ok] / c[ok]
        means[k] = m
    return {"ts": centers, "means": means, "n": n_bins, "counts": counts, "bucket_s": float(bucket_s)}
