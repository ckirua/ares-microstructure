"""Continuous-time / continuous-path analogues for Hasbrouck empirics.

Pairs with ``ares_micro.flow.discrete`` (event-time Roll / VAR / MRR / PIN)::

    calendar_returns, volume_clock_returns   # sampling clocks
    noise_robust_rv, noise_rv_ratio_bootstrap  # Ch.8 noise diagnostic + block bootstrap
    ofi_continuous                           # Cont–Kukanov L0 OFI
    trade_intensity                          # Ch.10 / Ch.15 point process
    amihud_illiquidity                       # Ch.22
    hasbrouck_info_share_2                   # Ch.17 VECM-lite IS bounds

Also re-exported from ``ares_micro``. LOB helpers: ``ares_micro.book.lob``.
Loaders: ``research.md``.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from ares_micro.book.tob import mid_price
from ares_micro.core.arrays import consecutive_log_returns, log_returns_on_grid
from ares_micro.core.constants import NS_PER_S
from ares_micro.core.rv import realized_variance
from ares_micro.stats import bootstrap_ci, pearson_r


def calendar_returns(
    ts_ns: NDArray[np.int64],
    px: NDArray[np.float64],
    *,
    bar_ns: int = NS_PER_S,
) -> tuple[NDArray[np.int64], NDArray[np.float64]]:
    """Last-price calendar bars → log returns (continuous-path sampling)."""
    t = np.asarray(ts_ns, dtype=np.int64)
    p = np.asarray(px, dtype=np.float64)
    m = np.isfinite(p) & (p > 0)
    t, p = t[m], p[m]
    if t.size < 3:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float64)
    t0, t1 = int(t.min()), int(t.max())
    grid = np.arange(t0, t1 + 1, bar_ns, dtype=np.int64)
    lr = log_returns_on_grid(t, p, grid)
    if int(np.isfinite(lr).sum()) < 2:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float64)
    return grid, lr


def volume_clock_returns(
    ts_ns: NDArray[np.int64],
    px: NDArray[np.float64],
    qty: NDArray[np.float64],
    *,
    bar_volume: float,
) -> tuple[NDArray[np.int64], NDArray[np.float64]]:
    """Volume-time bars: each bar closes after ``bar_volume`` coin qty."""
    t = np.asarray(ts_ns, dtype=np.int64)
    p = np.asarray(px, dtype=np.float64)
    q = np.asarray(qty, dtype=np.float64)
    m = np.isfinite(p) & np.isfinite(q) & (p > 0) & (q > 0)
    t, p, q = t[m], p[m], q[m]
    if t.size < 10 or bar_volume <= 0:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float64)
    cum = np.cumsum(q)
    n_bars = int(cum[-1] // bar_volume)
    if n_bars < 3:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float64)
    targets = (np.arange(1, n_bars + 1, dtype=np.float64)) * float(bar_volume)
    j = np.searchsorted(cum, targets, side="left")
    j = j[j < cum.size]
    if j.size < 3:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float64)
    ct = t[j]
    cp = p[j]
    lr = np.diff(np.log(cp))
    return ct[1:], lr


def noise_robust_rv(
    ts_ns: NDArray[np.int64],
    px: NDArray[np.float64],
    *,
    fine_ns: int = 100_000_000,
    coarse_ns: int = NS_PER_S,
) -> dict[str, float]:
    """Microstructure-noise diagnostic: RV_fine vs RV_coarse (Zhang-style intuition).

    If RV rises sharply at fine sampling, bounce/noise dominates continuous path.
    Pair with discrete Roll: noise ⇒ Roll often unidentified or c inflated.
    """
    _, r_f = calendar_returns(ts_ns, px, bar_ns=fine_ns)
    _, r_c = calendar_returns(ts_ns, px, bar_ns=coarse_ns)
    rv_f = realized_variance(r_f)
    rv_c = realized_variance(r_c)
    # scale to per-second for rough compare
    dur_s = float((int(np.asarray(ts_ns).max()) - int(np.asarray(ts_ns).min())) / NS_PER_S)
    if dur_s <= 0:
        dur_s = float("nan")
    return {
        "rv_fine": rv_f,
        "rv_coarse": rv_c,
        "rv_fine_per_s": rv_f / dur_s if dur_s and dur_s > 0 else float("nan"),
        "rv_coarse_per_s": rv_c / dur_s if dur_s and dur_s > 0 else float("nan"),
        "noise_ratio": rv_f / rv_c if rv_c and rv_c > 0 else float("nan"),
        "fine_ns": float(fine_ns),
        "coarse_ns": float(coarse_ns),
        "duration_s": dur_s,
    }


def noise_rv_ratio_bootstrap(
    ts_ns: NDArray[np.int64],
    px: NDArray[np.float64],
    *,
    fine_ns: int = 100_000_000,
    coarse_ns: int = NS_PER_S,
    n_blocks: int = 24,
    n_boot: int = 400,
    seed: int = 19,
) -> dict[str, Any]:
    """Block-bootstrap CI for ``noise_ratio`` = RV_fine / RV_coarse.

    Split the path into ``n_blocks`` contiguous time blocks; resample blocks
    with replacement and recompute the pooled ratio. Promote-claim for
    microstructure noise is ratio ≫ 1; if CI sits ≤1 (or barely above), Kill.
    """
    t = np.asarray(ts_ns, dtype=np.int64)
    p = np.asarray(px, dtype=np.float64)
    m = np.isfinite(p) & (p > 0)
    t, p = t[m], p[m]
    point = noise_robust_rv(t, p, fine_ns=fine_ns, coarse_ns=coarse_ns)
    out: dict[str, Any] = {
        **point,
        "n_blocks": int(n_blocks),
        "n_boot": int(n_boot),
        "block_ratios": [],
        "ratio_ci95": [float("nan"), float("nan")],
        "ok": False,
    }
    if t.size < 500:
        return out
    t0, t1 = int(t.min()), int(t.max())
    edges = np.linspace(t0, t1, n_blocks + 1)
    block_rvs: list[tuple[float, float]] = []
    for i in range(n_blocks):
        lo, hi = int(edges[i]), int(edges[i + 1])
        msk = (t >= lo) & (t < hi) if i < n_blocks - 1 else (t >= lo) & (t <= hi)
        if int(msk.sum()) < 30:
            continue
        blk = noise_robust_rv(t[msk], p[msk], fine_ns=fine_ns, coarse_ns=coarse_ns)
        rf, rc = blk["rv_fine"], blk["rv_coarse"]
        if np.isfinite(rf) and np.isfinite(rc) and rc > 0:
            block_rvs.append((float(rf), float(rc)))
            out["block_ratios"].append(float(rf / rc))
    if len(block_rvs) < 6:
        return out
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot, dtype=np.float64)
    n_b = len(block_rvs)
    arr = np.asarray(block_rvs, dtype=np.float64)
    for i in range(n_boot):
        idx = rng.integers(0, n_b, size=n_b)
        rf = float(arr[idx, 0].sum())
        rc = float(arr[idx, 1].sum())
        boots[i] = rf / rc if rc > 0 else float("nan")
    boots = boots[np.isfinite(boots)]
    if boots.size < 10:
        return out
    lo, hi = np.quantile(boots, [0.025, 0.975])
    out["ratio_ci95"] = [float(lo), float(hi)]
    out["ratio_boot_mean"] = float(np.mean(boots))
    out["n_blocks_used"] = int(n_b)
    out["ok"] = True
    return out


def ofi_continuous(
    ts_ns: NDArray[np.int64],
    bid: NDArray[np.float64],
    ask: NDArray[np.float64],
    bid_sz: NDArray[np.float64],
    ask_sz: NDArray[np.float64],
    *,
    bar_ns: int = NS_PER_S,
) -> dict[str, Any]:
    """Cont–Kukanov-style L0 order-flow imbalance on calendar bars.

    ΔBID size when bid up/same; −ΔASK when ask down/same — continuous analogue
    of discrete trade signs. Correlate with mid returns for impact.
    """
    t = np.asarray(ts_ns, dtype=np.int64)
    b = np.asarray(bid, dtype=np.float64)
    a = np.asarray(ask, dtype=np.float64)
    bs = np.asarray(bid_sz, dtype=np.float64)
    az = np.asarray(ask_sz, dtype=np.float64)
    mid = mid_price(b, a)
    # event-level OFI contribution (Cont–Kukanov), vectorized
    ofi_e = np.zeros(t.size, dtype=np.float64)
    if t.size >= 2:
        bid_up = b[1:] > b[:-1]
        bid_same = b[1:] == b[:-1]
        bid_dn = ~(bid_up | bid_same)
        ofi_bid = np.where(bid_up, bs[1:], 0.0)
        ofi_bid = np.where(bid_same, bs[1:] - bs[:-1], ofi_bid)
        ofi_bid = np.where(bid_dn, -bs[:-1], ofi_bid)
        ask_dn = a[1:] < a[:-1]
        ask_same = a[1:] == a[:-1]
        ask_up = ~(ask_dn | ask_same)
        ofi_ask = np.where(ask_dn, -az[1:], 0.0)
        ofi_ask = np.where(ask_same, -(az[1:] - az[:-1]), ofi_ask)
        ofi_ask = np.where(ask_up, az[:-1], ofi_ask)
        ofi_e[1:] = ofi_bid + ofi_ask
    t0, t1 = int(t.min()), int(t.max())
    grid = np.arange(t0, t1 + 1, bar_ns, dtype=np.int64)
    # sum OFI and last mid per bar via cumsum + searchsorted edges
    ofi_b = np.zeros(max(grid.size - 1, 0), dtype=np.float64)
    mid_b = np.full(max(grid.size - 1, 0), np.nan)
    if grid.size >= 2:
        idx = np.searchsorted(t, grid, side="left")
        lo, hi = idx[:-1], idx[1:]
        has = hi > lo
        cs = np.concatenate([[0.0], np.cumsum(ofi_e)])
        ofi_b[has] = cs[hi[has]] - cs[lo[has]]
        mid_b[has] = mid[hi[has] - 1]
    ret = consecutive_log_returns(mid_b)
    m = np.isfinite(ret) & np.isfinite(ofi_b)
    r, o = ret[m], ofi_b[m]
    if r.size < 20:
        return {"n": int(r.size), "corr_ofi_ret": float("nan"), "beta_ofi": float("nan")}
    o0, r0 = o - o.mean(), r - r.mean()
    beta = float(np.dot(o0, r0) / np.dot(o0, o0)) if np.dot(o0, o0) > 0 else float("nan")
    return {
        "n": int(r.size),
        "bar_ns": bar_ns,
        "corr_ofi_ret": pearson_r(o, r),
        "beta_ofi": beta,
        "ofi_std": float(np.std(o)),
        "ret_std": float(np.std(r)),
    }


def trade_intensity(
    ts_ns: NDArray[np.int64],
    *,
    bar_ns: int = NS_PER_S,
) -> dict[str, Any]:
    """Point-process intensity λ̂ on calendar bins (counts / second)."""
    t = np.asarray(ts_ns, dtype=np.int64)
    if t.size < 5:
        return {"n_bars": 0, "mean_lambda": float("nan")}
    t0, t1 = int(t.min()), int(t.max())
    grid = np.arange(t0, t1 + 1, bar_ns, dtype=np.int64)
    idx = np.searchsorted(t, grid, side="left")
    counts = np.diff(idx).astype(np.float64)
    dt_s = bar_ns / NS_PER_S
    lam = counts / dt_s
    ci = bootstrap_ci(lam, n_boot=400, seed=41)
    ac1 = pearson_r(counts[1:], counts[:-1]) if counts.size > 3 else float("nan")
    return {
        "n_bars": int(counts.size),
        "mean_lambda": ci["point"],
        "lambda_ci95": [ci["lo"], ci["hi"]],
        "count_ac1": ac1,
        "bar_s": dt_s,
    }


def amihud_illiquidity(
    returns: NDArray[np.float64],
    dollar_volume: NDArray[np.float64],
) -> dict[str, float]:
    """Amihud ILLIQ = mean(|r| / $volume) on aligned bars (Ch.22)."""
    r = np.asarray(returns, dtype=np.float64)
    v = np.asarray(dollar_volume, dtype=np.float64)
    m = np.isfinite(r) & np.isfinite(v) & (v > 0)
    r, v = r[m], v[m]
    if r.size < 5:
        return {"n": float(r.size), "illiq": float("nan")}
    x = np.abs(r) / v
    ci = bootstrap_ci(x, n_boot=400, seed=45)
    return {"n": float(r.size), "illiq": ci["point"], "illiq_ci95": [ci["lo"], ci["hi"]]}


def hasbrouck_info_share_2(
    mid_a: NDArray[np.float64],
    mid_b: NDArray[np.float64],
    *,
    lags: int = 5,
) -> dict[str, Any]:
    """Two-market Hasbrouck information-share bounds (VECM-lite via differenced VAR).

    Uses Δp VAR + Cholesky orderings for upper/lower IS. Continuous-path mids
    on a common calendar grid (pre-aligned). Not full Johansen — research-grade.
    """
    a = np.asarray(mid_a, dtype=np.float64)
    b = np.asarray(mid_b, dtype=np.float64)
    m = np.isfinite(a) & np.isfinite(b) & (a > 0) & (b > 0)
    a, b = a[m], b[m]
    if a.size < lags + 50:
        return {"n": int(a.size), "ok": False}
    da, db = np.diff(np.log(a)), np.diff(np.log(b))
    n = min(da.size, db.size)
    da, db = da[:n], db[:n]
    # VAR(L) on y=[da, db]
    Y, X = [], []
    for t in range(lags, n):
        if not all(np.isfinite([da[t], db[t]])):
            continue
        feats = []
        ok = True
        for k in range(1, lags + 1):
            if not (np.isfinite(da[t - k]) and np.isfinite(db[t - k])):
                ok = False
                break
            feats.extend([da[t - k], db[t - k]])
        if not ok:
            continue
        Y.append([da[t], db[t]])
        X.append(feats)
    if len(Y) < 40:
        return {"n": len(Y), "ok": False}
    Y = np.asarray(Y, dtype=np.float64)
    X = np.asarray(X, dtype=np.float64)
    # residuals for cov
    B, *_ = np.linalg.lstsq(X, Y, rcond=None)
    resid = Y - X @ B
    Omega = resid.T @ resid / max(resid.shape[0] - X.shape[1], 1)
    # Long-run multiplier Ψ ≈ (I − sum A_i)^{-1}; A_i from B blocks
    A_sum = np.zeros((2, 2))
    for k in range(lags):
        A_sum += B[2 * k : 2 * k + 2, :].T  # careful: B is (2L, 2) from lstsq X→Y
    # B shape (nfeat, 2) with feat = [da1,db1,da2,db2,...]
    A_sum = np.zeros((2, 2))
    for k in range(lags):
        Ak = B[2 * k : 2 * k + 2, :].T  # 2x2
        A_sum += Ak
    Psi = np.linalg.inv(np.eye(2) - A_sum)
    # IS for orderings
    def _is(chol_order: str) -> tuple[float, float]:
        if chol_order == "ab":
            # factor Omega = F F' with a first
            try:
                F = np.linalg.cholesky(Omega)
            except np.linalg.LinAlgError:
                return float("nan"), float("nan")
        else:
            # permute b first
            P = np.array([[0.0, 1.0], [1.0, 0.0]])
            try:
                F = P.T @ np.linalg.cholesky(P @ Omega @ P.T)
            except np.linalg.LinAlgError:
                return float("nan"), float("nan")
        psi_f = Psi @ F
        # contribution of shock j to common factor (row-sum of first row of psi_f squared)
        # For identical random walk, use psi = Psi[0,:] approx common
        # Hasbrouck: IS_j = (ψ F)_j^2 / (ψ Ω ψ') with ψ long-run row
        psi = Psi[0, :]  # long-run response of price 1; for IS use average
        # Better: use (1,1) weighted — both prices share factor; use mean of rows
        psi = 0.5 * (Psi[0, :] + Psi[1, :])
        num = (psi @ F) ** 2
        den = float(psi @ Omega @ psi)
        if den <= 0:
            return float("nan"), float("nan")
        shares = num / den
        return float(shares[0]), float(shares[1])

    is_ab = _is("ab")
    is_ba = _is("ba")
    # bounds for market A
    a_lo = min(is_ab[0], is_ba[0])
    a_hi = max(is_ab[0], is_ba[0])
    return {
        "n": int(Y.shape[0]),
        "ok": True,
        "lags": lags,
        "omega": Omega.tolist(),
        "is_a_low": a_lo,
        "is_a_high": a_hi,
        "is_b_low": 1.0 - a_hi if np.isfinite(a_hi) else float("nan"),
        "is_b_high": 1.0 - a_lo if np.isfinite(a_lo) else float("nan"),
        "ordering_ab": {"a": is_ab[0], "b": is_ab[1]},
        "ordering_ba": {"a": is_ba[0], "b": is_ba[1]},
    }
