"""Continuous-time / continuous-path analogues for Hasbrouck empirics.

Pairs with ``research.lib.discrete`` (event-time Roll / VAR / MRR / PIN)::

    calendar_returns, volume_clock_returns   # sampling clocks
    noise_robust_rv, noise_rv_ratio_bootstrap  # Ch.8 noise diagnostic + block bootstrap
    ofi_continuous                           # Cont–Kukanov L0 OFI
    trade_intensity                          # Ch.10 / Ch.15 point process
    vpin_bucket                              # continuous-flow PIN analogue
    amihud_illiquidity                       # Ch.22
    hasbrouck_info_share_2                   # Ch.17 VECM-lite IS bounds

Also re-exported from ``research.lib``. Part III LOB helpers live in
``research.lib.lob`` (sibling-owned). Loaders: ``scripts/_data.py``.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from research.lib.stats import bootstrap_ci


def calendar_returns(
    ts_ns: NDArray[np.int64],
    px: NDArray[np.float64],
    *,
    bar_ns: int = 1_000_000_000,
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
    idx = np.searchsorted(t, grid, side="right") - 1
    ok = (idx >= 0) & (idx < t.size)
    last = np.full(grid.shape, np.nan)
    last[ok] = p[idx[ok]]
    # drop leading empties
    finite = np.isfinite(last)
    if finite.sum() < 3:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float64)
    lr = np.full(last.size, np.nan)
    for i in range(1, last.size):
        if finite[i] and finite[i - 1] and last[i - 1] > 0:
            lr[i] = np.log(last[i] / last[i - 1])
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
    closes_t = []
    closes_p = []
    target = bar_volume
    j = 0
    for _ in range(n_bars):
        while j < cum.size and cum[j] < target:
            j += 1
        if j >= cum.size:
            break
        closes_t.append(int(t[j]))
        closes_p.append(float(p[j]))
        target += bar_volume
    ct = np.asarray(closes_t, dtype=np.int64)
    cp = np.asarray(closes_p, dtype=np.float64)
    lr = np.diff(np.log(cp))
    return ct[1:], lr


def realized_variance(returns: NDArray[np.float64]) -> float:
    r = np.asarray(returns, dtype=np.float64)
    r = r[np.isfinite(r)]
    return float(np.sum(r * r)) if r.size else float("nan")


def noise_robust_rv(
    ts_ns: NDArray[np.int64],
    px: NDArray[np.float64],
    *,
    fine_ns: int = 100_000_000,
    coarse_ns: int = 1_000_000_000,
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
    dur_s = float((int(np.asarray(ts_ns).max()) - int(np.asarray(ts_ns).min())) / 1e9)
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
    coarse_ns: int = 1_000_000_000,
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
    bar_ns: int = 1_000_000_000,
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
    mid = 0.5 * (b + a)
    # event-level OFI contribution
    ofi_e = np.zeros(t.size, dtype=np.float64)
    for i in range(1, t.size):
        # bid contribution
        if b[i] > b[i - 1]:
            ofi_e[i] += bs[i]
        elif b[i] == b[i - 1]:
            ofi_e[i] += bs[i] - bs[i - 1]
        else:
            ofi_e[i] -= bs[i - 1]
        # ask contribution
        if a[i] < a[i - 1]:
            ofi_e[i] -= az[i]
        elif a[i] == a[i - 1]:
            ofi_e[i] -= az[i] - az[i - 1]
        else:
            ofi_e[i] += az[i - 1]
    t0, t1 = int(t.min()), int(t.max())
    grid = np.arange(t0, t1 + 1, bar_ns, dtype=np.int64)
    # sum OFI and last mid per bar
    ofi_b = np.zeros(grid.size - 1, dtype=np.float64)
    mid_b = np.full(grid.size - 1, np.nan)
    idx = np.searchsorted(t, grid, side="left")
    for i in range(grid.size - 1):
        lo, hi = idx[i], idx[i + 1]
        if hi > lo:
            ofi_b[i] = float(ofi_e[lo:hi].sum())
            mid_b[i] = float(mid[hi - 1])
    # mid returns
    ret = np.full(mid_b.size, np.nan)
    for i in range(1, mid_b.size):
        if np.isfinite(mid_b[i]) and np.isfinite(mid_b[i - 1]) and mid_b[i - 1] > 0:
            ret[i] = np.log(mid_b[i] / mid_b[i - 1])
    m = np.isfinite(ret) & np.isfinite(ofi_b)
    r, o = ret[m], ofi_b[m]
    if r.size < 20:
        return {"n": int(r.size), "corr_ofi_ret": float("nan"), "beta_ofi": float("nan")}
    o0, r0 = o - o.mean(), r - r.mean()
    den = float(np.sqrt((o0 * o0).sum() * (r0 * r0).sum()))
    corr = float((o0 * r0).sum() / den) if den > 0 else float("nan")
    beta = float(np.dot(o0, r0) / np.dot(o0, o0)) if np.dot(o0, o0) > 0 else float("nan")
    return {
        "n": int(r.size),
        "bar_ns": bar_ns,
        "corr_ofi_ret": corr,
        "beta_ofi": beta,
        "ofi_std": float(np.std(o)),
        "ret_std": float(np.std(r)),
    }


def trade_intensity(
    ts_ns: NDArray[np.int64],
    *,
    bar_ns: int = 1_000_000_000,
) -> dict[str, Any]:
    """Point-process intensity λ̂ on calendar bins (counts / second)."""
    t = np.asarray(ts_ns, dtype=np.int64)
    if t.size < 5:
        return {"n_bars": 0, "mean_lambda": float("nan")}
    t0, t1 = int(t.min()), int(t.max())
    grid = np.arange(t0, t1 + 1, bar_ns, dtype=np.int64)
    idx = np.searchsorted(t, grid, side="left")
    counts = np.diff(idx).astype(np.float64)
    dt_s = bar_ns / 1e9
    lam = counts / dt_s
    ci = bootstrap_ci(lam, n_boot=400, seed=41)
    # clustering: lag-1 corr of counts
    if counts.size > 3:
        c0 = counts[1:] - counts[1:].mean()
        c1 = counts[:-1] - counts[:-1].mean()
        den = float(np.sqrt((c0 * c0).sum() * (c1 * c1).sum()))
        ac1 = float((c0 * c1).sum() / den) if den > 0 else float("nan")
    else:
        ac1 = float("nan")
    return {
        "n_bars": int(counts.size),
        "mean_lambda": ci["point"],
        "lambda_ci95": [ci["lo"], ci["hi"]],
        "count_ac1": ac1,
        "bar_s": dt_s,
    }


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
    s, q = s[m], q[m]
    if s.size < 50 or bucket_volume <= 0:
        return {"n_buckets": 0, "mean_vpin": float("nan")}
    buy_acc = sell_acc = 0.0
    vol_acc = 0.0
    imbalances = []
    for i in range(s.size):
        if s[i] > 0:
            buy_acc += q[i]
        else:
            sell_acc += q[i]
        vol_acc += q[i]
        if vol_acc >= bucket_volume:
            imbalances.append(abs(buy_acc - sell_acc) / vol_acc)
            buy_acc = sell_acc = vol_acc = 0.0
    imb = np.asarray(imbalances, dtype=np.float64)
    if imb.size < 5:
        return {"n_buckets": int(imb.size), "mean_vpin": float("nan")}
    # rolling
    w = min(n_buckets_window, imb.size)
    roll = np.convolve(imb, np.ones(w) / w, mode="valid")
    ci = bootstrap_ci(roll, n_boot=400, seed=43)
    return {
        "n_buckets": int(imb.size),
        "bucket_volume": float(bucket_volume),
        "mean_vpin": ci["point"],
        "vpin_ci95": [ci["lo"], ci["hi"]],
        "p50_vpin": float(np.median(roll)),
        "last_vpin": float(roll[-1]),
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
