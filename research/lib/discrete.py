"""Discrete-time empirics for Hasbrouck *Empirical Market Microstructure* notes.

Clock: **trade-event index** by default; calendar-bar variants take pre-binned series.
Pair with ``research.lib.continuous`` for calendar / volume / intensity clocks.

Public surface (also re-exported from ``research.lib``)::

    # Ch.3 / Ch.9 bounce & MA
    roll_c_from_returns, roll_on_mid_bps, ma1_from_acov
    # Ch.8–9 RW variance via AR truncation
    ar_ols, rw_variance_from_ar, impact_multipliers_from_ar
    # Ch.10 signs
    trade_sign_acf
    # Ch.13–14 structural / reduced form
    glosten_harris_ols, mrr_ols, signed_trade_var, impulse_response_trade
    quote_aligned_delta_mid, contemporaneous_lambda, lambda_time_split_bootstrap
    huang_stoll_basic_ols, huang_stoll_spread_decomp,
    huang_stoll_gmm_split, huang_stoll_restricted_split,
    volume_bucket_hs_panel, dealer_inventory_proxy_ols

Loaders for book scripts: ``research/books/empirical_mm/scripts/_data.py``.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from research.lib.stats import bootstrap_ci, time_split_mask


def roll_c_from_returns(returns: NDArray[np.float64]) -> dict[str, float]:
    """Roll (1984): c = √(−γ₁), σ_u² = γ₀ + 2γ₁ from Δp autocovariances.

    Returns price-unit ``c``, ``spread_2c``, ``sigma_u2``, raw ``g0``/``g1``.
    Unidentified when γ₁ ≥ 0 → NaNs (Kill candidate).
    """
    r = np.asarray(returns, dtype=np.float64)
    r = r[np.isfinite(r)]
    out = {
        "n": float(r.size),
        "g0": float("nan"),
        "g1": float("nan"),
        "c": float("nan"),
        "spread_2c": float("nan"),
        "sigma_u2": float("nan"),
        "identified": 0.0,
    }
    if r.size < 8:
        return out
    g0 = float(np.var(r))
    g1 = float(np.cov(r[1:], r[:-1])[0, 1])
    out["g0"], out["g1"] = g0, g1
    if g1 >= 0:
        return out
    c = float(np.sqrt(-g1))
    out.update(
        {
            "c": c,
            "spread_2c": 2.0 * c,
            "sigma_u2": float(g0 + 2.0 * g1),
            "identified": 1.0,
        }
    )
    return out


def roll_on_mid_bps(
    mid: NDArray[np.float64],
    *,
    step: int = 1,
) -> dict[str, float]:
    """Roll on mid differences; report ``spread_2c`` in bps of mean mid."""
    m = np.asarray(mid, dtype=np.float64)
    m = m[np.isfinite(m) & (m > 0)]
    if m.size < 10:
        return {"identified": 0.0, "spread_bps": float("nan"), "c": float("nan")}
    if step > 1:
        m = m[::step]
    dp = np.diff(m)
    est = roll_c_from_returns(dp)
    mean_m = float(np.mean(m))
    spread_bps = (
        float(1e4 * est["spread_2c"] / mean_m)
        if est["identified"] and mean_m > 0
        else float("nan")
    )
    est["spread_bps"] = spread_bps
    est["mean_mid"] = mean_m
    return est


def glosten_harris_ols(
    d_mid: NDArray[np.float64],
    side: NDArray[np.float64],
    size: NDArray[np.float64] | None = None,
) -> dict[str, Any]:
    """Glosten–Harris style OLS on mid changes (quote-available case).

    Spec (discrete trade time)::

        Δm_t = (z0 + z1 V_t) q_t + e_t

    When quotes exist we use mid (not latent Q). ``size`` defaults to ones.
    Returns z0, z1 (permanent / adverse), R², n. Pair with ``disc.gh_*``.
    """
    y = np.asarray(d_mid, dtype=np.float64)
    q = np.asarray(side, dtype=np.float64)
    v = np.ones_like(y) if size is None else np.asarray(size, dtype=np.float64)
    m = np.isfinite(y) & np.isfinite(q) & np.isfinite(v) & (q != 0) & (v >= 0)
    y, q, v = y[m], q[m], v[m]
    if y.size < 20:
        return {"n": int(y.size), "z0": float("nan"), "z1": float("nan"), "r2": float("nan")}
    # Δm = z0·q + z1·(q·V) + e
    x0 = q
    x1 = q * v
    X = np.column_stack([x0, x1])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    yhat = X @ coef
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return {
        "n": int(y.size),
        "z0": float(coef[0]),
        "z1": float(coef[1]),
        "r2": float(r2),
        "sigma_e": float(np.sqrt(ss_res / max(y.size - 2, 1))),
    }


def mrr_ols(
    d_price: NDArray[np.float64],
    side: NDArray[np.float64],
    *,
    side_lag: NDArray[np.float64] | None = None,
) -> dict[str, Any]:
    """Madhavan–Richardson–Roomans reduced form (discrete).

    Approx::

        Δp_t = θ (q_t − ρ q_{t−1}) + φ (q_t − q_{t−1}) + e_t

    Estimated as OLS of Δp on q_t and q_{t−1}:

        Δp_t = a q_t + b q_{t−1} + e_t

    with ρ = Corr(q_t, q_{t−1}), θ ≈ permanent, φ ≈ temporary (interpretive).
    """
    dp = np.asarray(d_price, dtype=np.float64)
    q = np.asarray(side, dtype=np.float64)
    if side_lag is None:
        q_lag = np.roll(q, 1)
        q_lag[0] = np.nan
    else:
        q_lag = np.asarray(side_lag, dtype=np.float64)
    m = np.isfinite(dp) & np.isfinite(q) & np.isfinite(q_lag) & (q != 0) & (q_lag != 0)
    dp, q, q_lag = dp[m], q[m], q_lag[m]
    if dp.size < 30:
        return {"n": int(dp.size), "a": float("nan"), "b": float("nan"), "rho_q": float("nan")}
    X = np.column_stack([q, q_lag])
    coef, *_ = np.linalg.lstsq(X, dp, rcond=None)
    q0, q1 = q - q.mean(), q_lag - q_lag.mean()
    den = float(np.sqrt((q0 * q0).sum() * (q1 * q1).sum()))
    rho = float((q0 * q1).sum() / den) if den > 0 else float("nan")
    # Interpret: permanent θ ~ a + b*(related); report raw + split heuristics
    # Standard MRR: Δp = (θ+φ)q_t − (φ + ρθ) q_{t-1} + …
    # With a = θ+φ, b = −(φ+ρθ) → θ = (a+b)/(1−ρ) if |ρ|<1, φ = a−θ
    theta = phi = float("nan")
    if np.isfinite(rho) and abs(rho) < 0.999:
        theta = float((coef[0] + coef[1]) / (1.0 - rho))
        phi = float(coef[0] - theta)
    yhat = X @ coef
    ss_res = float(np.sum((dp - yhat) ** 2))
    ss_tot = float(np.sum((dp - dp.mean()) ** 2))
    return {
        "n": int(dp.size),
        "a": float(coef[0]),
        "b": float(coef[1]),
        "rho_q": rho,
        "theta_perm": theta,
        "phi_temp": phi,
        "r2": float(1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan"),
    }


def signed_trade_var(
    d_mid: NDArray[np.float64],
    side: NDArray[np.float64],
    *,
    lags: int = 5,
) -> dict[str, Any]:
    """Bivariate reduced-form: Δm_t on lags of Δm and q; q_t on lags of Δm and q.

    Hasbrouck Ch.12–13 style discrete VAR (no contemporaneous Cholesky here —
    see ``impulse_response_trade`` for trade→price path under Cholesky q first).
    """
    y = np.asarray(d_mid, dtype=np.float64)
    q = np.asarray(side, dtype=np.float64)
    n = y.size
    if n < lags + 30:
        return {"n": int(n), "lags": lags, "ok": False}
    # Build lag matrix
    rows = []
    targets_m, targets_q = [], []
    for t in range(lags, n):
        if not (np.isfinite(y[t]) and np.isfinite(q[t])):
            continue
        feats = []
        good = True
        for k in range(1, lags + 1):
            if not (np.isfinite(y[t - k]) and np.isfinite(q[t - k])):
                good = False
                break
            feats.extend([y[t - k], q[t - k]])
        if not good:
            continue
        rows.append(feats)
        targets_m.append(y[t])
        targets_q.append(q[t])
    if len(rows) < 40:
        return {"n": len(rows), "lags": lags, "ok": False}
    X = np.asarray(rows, dtype=np.float64)
    ym = np.asarray(targets_m, dtype=np.float64)
    yq = np.asarray(targets_q, dtype=np.float64)
    bm, *_ = np.linalg.lstsq(X, ym, rcond=None)
    bq, *_ = np.linalg.lstsq(X, yq, rcond=None)
    # Contemporaneous trade impact: OLS Δm on q_t + lags (structural recursive)
    Xc = np.column_stack([yq, X])  # q_t first
    bc, *_ = np.linalg.lstsq(Xc, ym, rcond=None)
    return {
        "n": int(X.shape[0]),
        "lags": lags,
        "ok": True,
        "coef_dm": bm.tolist(),
        "coef_q": bq.tolist(),
        "lambda_contemp": float(bc[0]),
        "r2_dm": float(1.0 - np.sum((ym - X @ bm) ** 2) / np.sum((ym - ym.mean()) ** 2)),
        "r2_q": float(1.0 - np.sum((yq - X @ bq) ** 2) / np.sum((yq - yq.mean()) ** 2)),
    }


def impulse_response_trade(
    d_mid: NDArray[np.float64],
    side: NDArray[np.float64],
    *,
    lags: int = 5,
    horizon: int = 20,
    shock: float = 1.0,
) -> dict[str, Any]:
    """Cumulative mid IRF to a +1 trade-sign shock (Cholesky: q → Δm).

    Desk/research use: permanent impact ≈ IRF[∞]; temporary = peak − permanent.
    """
    var = signed_trade_var(d_mid, side, lags=lags)
    if not var.get("ok"):
        return {"ok": False, **var}
    # Companion form on state [Δm_{t-1}, q_{t-1}, ..., Δm_{t-L}, q_{t-L}]
    L = lags
    bm = np.asarray(var["coef_dm"], dtype=np.float64)
    bq = np.asarray(var["coef_q"], dtype=np.float64)
    lam = float(var["lambda_contemp"])
    # State dim 2L
    A = np.zeros((2 * L, 2 * L), dtype=np.float64)
    # row 0: Δm_t = lam*q_t + sum bm_k Δm + bm_q q  — need q_t first
    # Iterate nonlinearly: at each step, shock enters q then Δm
    # Simpler path simulation:
    # Reduced-form companion on z_t = [Δm_t, q_t]'.
    # Contemporaneous: q shock first, then Δm_t = λ q_t + lag terms.
    # State stores lags 1..L of (Δm, q) in the same feature order as estimation.
    hist_dm = np.zeros(L)
    hist_q = np.zeros(L)
    irf = []
    cum = 0.0
    for h in range(horizon):
        feats = []
        for k in range(L):
            feats.extend([hist_dm[k], hist_q[k]])
        feats = np.asarray(feats, dtype=np.float64)
        if h == 0:
            # structural shock to trade sign; price responds via λ + dynamics
            eq = shock
            qt = float(bq @ feats) + eq
            dmt = float(lam * eq + bm @ feats)
        else:
            qt = float(bq @ feats)
            dmt = float(bm @ feats)
        cum += dmt
        irf.append({"h": h, "dm": dmt, "cum_dm": cum, "q": qt})
        hist_dm = np.concatenate([[dmt], hist_dm[:-1]])
        hist_q = np.concatenate([[qt], hist_q[:-1]])
    permanent = float(irf[-1]["cum_dm"]) if irf else float("nan")
    return {
        "ok": True,
        "n": var["n"],
        "lags": lags,
        "lambda_contemp": lam,
        "irf": irf,
        "permanent_impact": permanent,
        "peak_cum": float(max((r["cum_dm"] for r in irf), default=float("nan"))),
    }


def huang_stoll_spread_decomp(
    d_price: NDArray[np.float64],
    side: NDArray[np.float64],
    *,
    half_spread: float | NDArray[np.float64] | None = None,
    d_mid: NDArray[np.float64] | None = None,
) -> dict[str, Any]:
    """Huang–Stoll (1997) spread-component decomposition (Hasbrouck Ch.14.d).

    Two-way (λ = a + b unidentified split)::

        ΔP_t = (S/2) ΔQ_t + λ (S/2) Q_{t−1} + e_t

    Three-way when signs reverse with probability π (book 14.d.16)::

        ΔP_t = (S/2) Q_t + (a+b−1)(S/2) Q_{t−1}
               − a (S/2)(1−2π) Q_{t−2} + e_t

    ``half_spread`` may be a scalar S/2 (e.g. mean quoted half-spread in price
    units) or per-trade series; if None, S/2 is left free in the two-way OLS
    (identified as the coef on ΔQ).

    Returns adverse-selection share ``a``, inventory share ``b``, combined
    ``lambda_ab``, estimated ``half_spread``, and π.
    """
    dp = np.asarray(d_price, dtype=np.float64)
    q = np.asarray(side, dtype=np.float64)
    n = min(dp.size, q.size)
    dp, q = dp[:n], q[:n]
    # need lags 1,2 → align from t=2
    if n < 80:
        return {
            "n": int(n),
            "ok": False,
            "message": "too few trades",
            "lambda_ab": float("nan"),
            "a_adverse": float("nan"),
            "b_inventory": float("nan"),
        }

    q0 = q[2:]
    q1 = q[1:-1]
    q2 = q[:-2]
    dpt = dp[2:]
    dq = q0 - q1
    m = (
        np.isfinite(dpt)
        & np.isfinite(q0)
        & np.isfinite(q1)
        & np.isfinite(q2)
        & (q0 != 0)
        & (q1 != 0)
        & (q2 != 0)
    )
    dpt, q0, q1, q2, dq = dpt[m], q0[m], q1[m], q2[m], dq[m]
    if dpt.size < 60:
        return {"n": int(dpt.size), "ok": False, "message": "too few after clean"}

    # reversal probability π = P(Q_t ≠ Q_{t-1})
    pi = float(np.mean(q0 != q1))
    rho = float(np.corrcoef(q0, q1)[0, 1]) if dpt.size > 2 else float("nan")

    # --- two-way: ΔP = β_dq ΔQ + β_q Q_{t-1} ---
    X2 = np.column_stack([dq, q1])
    c2, *_ = np.linalg.lstsq(X2, dpt, rcond=None)
    beta_dq, beta_ql = float(c2[0]), float(c2[1])
    yhat2 = X2 @ c2
    ss_res2 = float(np.sum((dpt - yhat2) ** 2))
    ss_tot = float(np.sum((dpt - dpt.mean()) ** 2))
    r2_two = 1.0 - ss_res2 / ss_tot if ss_tot > 0 else float("nan")

    if half_spread is None:
        hs = abs(beta_dq) if abs(beta_dq) > 1e-12 else float("nan")
        hs_source = "ols_delta_q"
    else:
        hs_arr = np.asarray(half_spread, dtype=np.float64)
        hs = float(np.nanmean(hs_arr)) if hs_arr.size else float("nan")
        hs_source = "quoted"
    lambda_ab = float(beta_ql / hs) if np.isfinite(hs) and abs(hs) > 1e-12 else float("nan")

    # --- three-way on trade prices (fix S/2 = hs) ---
    a_as = b_inv = float("nan")
    r2_three = float("nan")
    coef_three: list[float] = []
    if np.isfinite(hs) and abs(hs) > 1e-12 and abs(1.0 - 2.0 * pi) > 1e-6:
        # ΔP / (S/2) = Q_t + (a+b−1) Q_{t-1} − a(1−2π) Q_{t-2} + e'
        y = dpt / hs
        X3 = np.column_stack([q0, q1, q2])
        c3, *_ = np.linalg.lstsq(X3, y, rcond=None)
        coef_three = [float(c3[0]), float(c3[1]), float(c3[2])]
        yhat3 = X3 @ c3
        ss_res3 = float(np.sum((y - yhat3) ** 2))
        ss_tot3 = float(np.sum((y - y.mean()) ** 2))
        r2_three = 1.0 - ss_res3 / ss_tot3 if ss_tot3 > 0 else float("nan")
        # unconstrained: c0≈1, c1=a+b−1, c2=−a(1−2π)
        a_as = float(-c3[2] / (1.0 - 2.0 * pi))
        ab = float(c3[1] + 1.0)
        b_inv = float(ab - a_as)

    # optional mid equation: ΔM = (a+b)(S/2) Q_{t-1} − a(S/2)(1−2π) Q_{t-2}
    mid_out: dict[str, float] = {}
    if d_mid is not None:
        dm = np.asarray(d_mid, dtype=np.float64)
        nm = min(dm.size, q.size)
        if nm >= 80 and np.isfinite(hs) and abs(hs) > 1e-12:
            dm2 = dm[2:nm]
            qq1 = q[1 : nm - 1]
            qq2 = q[: nm - 2]
            mm = np.isfinite(dm2) & np.isfinite(qq1) & np.isfinite(qq2) & (qq1 != 0) & (qq2 != 0)
            dm2, qq1, qq2 = dm2[mm], qq1[mm], qq2[mm]
            if dm2.size >= 60 and abs(1.0 - 2.0 * pi) > 1e-6:
                ym = dm2 / hs
                Xm = np.column_stack([qq1, qq2])
                cm, *_ = np.linalg.lstsq(Xm, ym, rcond=None)
                # ym = (a+b) Q1 − a(1−2π) Q2
                ab_m = float(cm[0])
                a_m = float(-cm[1] / (1.0 - 2.0 * pi))
                mid_out = {
                    "a_adverse_mid": a_m,
                    "b_inventory_mid": float(ab_m - a_m),
                    "lambda_ab_mid": ab_m,
                    "n_mid": float(dm2.size),
                }

    return {
        "n": int(dpt.size),
        "ok": True,
        "pi_reversal": pi,
        "rho_q": rho,
        "half_spread": hs,
        "half_spread_source": hs_source,
        "beta_delta_q": beta_dq,
        "beta_q_lag": beta_ql,
        "lambda_ab": lambda_ab,
        "a_adverse": a_as,
        "b_inventory": b_inv,
        "r2_two_way": float(r2_two),
        "r2_three_way": float(r2_three),
        "coef_three_way": coef_three,
        "as_share": (
            float(a_as / (a_as + b_inv))
            if np.isfinite(a_as) and np.isfinite(b_inv) and (a_as + b_inv) != 0
            else float("nan")
        ),
        "inv_share": (
            float(b_inv / (a_as + b_inv))
            if np.isfinite(a_as) and np.isfinite(b_inv) and (a_as + b_inv) != 0
            else float("nan")
        ),
        **mid_out,
    }


def _hs_align_lags(
    d_price: NDArray[np.float64],
    side: NDArray[np.float64],
    d_mid: NDArray[np.float64] | None = None,
) -> dict[str, Any] | None:
    """Shared lag-2 alignment for Huang–Stoll three-way panels."""
    dp = np.asarray(d_price, dtype=np.float64)
    q = np.asarray(side, dtype=np.float64)
    n = min(dp.size, q.size)
    dp, q = dp[:n], q[:n]
    if n < 80:
        return None
    q0, q1, q2 = q[2:], q[1:-1], q[:-2]
    dpt = dp[2:]
    m = (
        np.isfinite(dpt)
        & np.isfinite(q0)
        & np.isfinite(q1)
        & np.isfinite(q2)
        & (q0 != 0)
        & (q1 != 0)
        & (q2 != 0)
    )
    dpt, q0, q1, q2 = dpt[m], q0[m], q1[m], q2[m]
    dm2 = None
    if d_mid is not None:
        dm = np.asarray(d_mid, dtype=np.float64)[:n]
        dm2 = dm[2:][m]
        mm = np.isfinite(dm2)
        dpt, q0, q1, q2, dm2 = dpt[mm], q0[mm], q1[mm], q2[mm], dm2[mm]
    if dpt.size < 60:
        return None
    pi = float(np.mean(q0 != q1))
    rho = float(np.corrcoef(q0, q1)[0, 1]) if dpt.size > 2 else float("nan")
    return {
        "dpt": dpt,
        "q0": q0,
        "q1": q1,
        "q2": q2,
        "dm": dm2,
        "pi": pi,
        "rho": rho,
        "n": int(dpt.size),
    }


def huang_stoll_gmm_split(
    d_price: NDArray[np.float64],
    side: NDArray[np.float64],
    *,
    half_spread: float,
    d_mid: NDArray[np.float64] | None = None,
    pi_reversal: float | None = None,
) -> dict[str, Any]:
    """Huang–Stoll α|β via GMM on book 14.d.16 (price ± mid moments).

    Parameters ``(a, b)`` with fixed ``S/2`` and reversal probability ``p``
    (sample or supplied). Just-identified price moments with instruments
    ``(Q_t, Q_{t−1}, Q_{t−2})`` recover the same point as three-way OLS;
    stacking mid moments (14.d.16 ΔM) yields an overidentified 2-step GMM
    when ``d_mid`` is provided.

    Residual (price)::

        e_t = ΔP_t/(S/2) − Q_t − (a+b−1) Q_{t−1} + a(1−2p) Q_{t−2}

    Residual (mid, optional)::

        u_t = ΔM_t/(S/2) − (a+b) Q_{t−1} + a(1−2p) Q_{t−2}
    """
    hs = float(half_spread)
    al = _hs_align_lags(d_price, side, d_mid=d_mid)
    if al is None or not np.isfinite(hs) or abs(hs) < 1e-12:
        return {
            "ok": False,
            "n": 0,
            "a_adverse": float("nan"),
            "b_inventory": float("nan"),
            "lambda_ab": float("nan"),
            "message": "align/half-spread failed",
        }
    dpt, q0, q1, q2 = al["dpt"], al["q0"], al["q1"], al["q2"]
    p = float(pi_reversal) if pi_reversal is not None else float(al["pi"])
    k = 1.0 - 2.0 * p
    if abs(k) < 1e-6:
        return {
            "ok": False,
            "n": al["n"],
            "a_adverse": float("nan"),
            "b_inventory": float("nan"),
            "lambda_ab": float("nan"),
            "message": "1-2p≈0; AS lag unidentified",
            "pi_reversal": p,
        }

    y_p = dpt / hs
    # Just-ID OLS ≡ GMM with Z=(Q0,Q1,Q2): solve for (c0,c1,c2) then map
    X_p = np.column_stack([q0, q1, q2])
    c_p, *_ = np.linalg.lstsq(X_p, y_p, rcond=None)
    a_ols = float(-c_p[2] / k)
    ab_ols = float(c_p[1] + 1.0)
    b_ols = float(ab_ols - a_ols)

    a_hat, b_hat = a_ols, b_ols
    method = "gmm_just_id_price"
    j_stat = float("nan")
    n_moments = 3

    if al["dm"] is not None and al["dm"].size == dpt.size:
        # OverID: parameters θ=(a, λ=a+b). Stack price + mid orthogonality.
        # Price: E[e Q0]=E[e Q1]=E[e Q2]=0; Mid: E[u Q1]=E[u Q2]=0 → 5 moments, 2 params.
        y_m = al["dm"] / hs
        # Linear in (a, λ):
        # e = y_p - Q0 - (λ-1) Q1 + a k Q2 = (y_p - Q0 + Q1) - λ Q1 + a k Q2
        # u = y_m - λ Q1 + a k Q2
        yp_adj = y_p - q0 + q1

        def moments(a: float, lam: float) -> np.ndarray:
            e = yp_adj - lam * q1 + a * k * q2
            u = y_m - lam * q1 + a * k * q2
            return np.array(
                [
                    float(np.mean(e * q0)),
                    float(np.mean(e * q1)),
                    float(np.mean(e * q2)),
                    float(np.mean(u * q1)),
                    float(np.mean(u * q2)),
                ]
            )

        # Step-1: minimize g'g (identity weight) via Gauss–Newton on (a, λ)
        theta = np.array([a_ols, ab_ols], dtype=np.float64)
        for _ in range(25):
            a0, lam0 = float(theta[0]), float(theta[1])
            g = moments(a0, lam0)
            # Numerical Jacobian
            eps = 1e-5
            J = np.column_stack(
                [
                    (moments(a0 + eps, lam0) - g) / eps,
                    (moments(a0, lam0 + eps) - g) / eps,
                ]
            )
            try:
                step, *_ = np.linalg.lstsq(J, -g, rcond=None)
            except np.linalg.LinAlgError:
                break
            theta = theta + step
            if float(np.linalg.norm(step)) < 1e-10:
                break
        a_hat, lam_hat = float(theta[0]), float(theta[1])
        b_hat = float(lam_hat - a_hat)
        g_hat = moments(a_hat, lam_hat)
        # Step-2 optimal weight ≈ diag of outer products of stacked residuals×instr
        e = yp_adj - lam_hat * q1 + a_hat * k * q2
        u = y_m - lam_hat * q1 + a_hat * k * q2
        Gmat = np.column_stack([e * q0, e * q1, e * q2, u * q1, u * q2])
        W_inv = (Gmat.T @ Gmat) / max(Gmat.shape[0], 1)
        # ridge for stability
        W_inv = W_inv + 1e-12 * np.eye(5)
        try:
            W = np.linalg.inv(W_inv)
        except np.linalg.LinAlgError:
            W = np.eye(5)
        # one more Gauss–Newton with W
        theta2 = theta.copy()
        for _ in range(25):
            a0, lam0 = float(theta2[0]), float(theta2[1])
            g = moments(a0, lam0)
            eps = 1e-5
            J = np.column_stack(
                [
                    (moments(a0 + eps, lam0) - g) / eps,
                    (moments(a0, lam0 + eps) - g) / eps,
                ]
            )
            JTW = J.T @ W
            try:
                step = np.linalg.solve(JTW @ J + 1e-12 * np.eye(2), -JTW @ g)
            except np.linalg.LinAlgError:
                break
            theta2 = theta2 + step
            if float(np.linalg.norm(step)) < 1e-10:
                break
        a_hat, lam_hat = float(theta2[0]), float(theta2[1])
        b_hat = float(lam_hat - a_hat)
        g_hat = moments(a_hat, lam_hat)
        j_stat = float(g_hat @ W @ g_hat * al["n"])
        n_moments = 5
        method = "gmm_overid_price_mid"

    lam = float(a_hat + b_hat)
    as_share = (
        float(a_hat / lam) if np.isfinite(lam) and abs(lam) > 1e-12 else float("nan")
    )
    return {
        "ok": True,
        "n": al["n"],
        "method": method,
        "pi_reversal": p,
        "rho_q": al["rho"],
        "half_spread": hs,
        "a_adverse": float(a_hat),
        "b_inventory": float(b_hat),
        "lambda_ab": lam,
        "a_ols_price": a_ols,
        "b_ols_price": b_ols,
        "as_share": as_share,
        "inv_share": float(1.0 - as_share) if np.isfinite(as_share) else float("nan"),
        "j_stat": j_stat,
        "n_moments": n_moments,
        "n_params": 2,
    }


def huang_stoll_restricted_split(
    d_price: NDArray[np.float64],
    side: NDArray[np.float64],
    *,
    half_spread: float,
    d_mid: NDArray[np.float64] | None = None,
    pi_reversal: float | None = None,
) -> dict[str, Any]:
    """Restricted HS split: fix λ̂ from two-way, map â∈[0, λ̂], b̂=λ̂−â.

    Uses the mid (preferred) or price Q_{t−2} moment for a, then projects onto
    the economically signed simplex. Reports whether the unconstrained a was
    already inside [0, λ] (``binding=False``).
    """
    hs = float(half_spread)
    al = _hs_align_lags(d_price, side, d_mid=d_mid)
    if al is None or not np.isfinite(hs) or abs(hs) < 1e-12:
        return {
            "ok": False,
            "n": 0,
            "a_adverse": float("nan"),
            "b_inventory": float("nan"),
            "lambda_ab": float("nan"),
        }
    dpt, q0, q1, q2 = al["dpt"], al["q0"], al["q1"], al["q2"]
    p = float(pi_reversal) if pi_reversal is not None else float(al["pi"])
    k = 1.0 - 2.0 * p
    # two-way λ
    dq = q0 - q1
    X2 = np.column_stack([dq, q1])
    c2, *_ = np.linalg.lstsq(X2, dpt, rcond=None)
    lam = float(c2[1] / hs) if abs(hs) > 1e-12 else float("nan")
    if not np.isfinite(lam) or abs(k) < 1e-6:
        return {
            "ok": False,
            "n": al["n"],
            "a_adverse": float("nan"),
            "b_inventory": float("nan"),
            "lambda_ab": lam,
            "pi_reversal": p,
        }

    # prefer mid equation for a: ym = λ Q1 − a k Q2  ⇒ residual orthogonal to Q2
    a_raw = float("nan")
    source = "price"
    if al["dm"] is not None and al["dm"].size == dpt.size:
        ym = al["dm"] / hs
        # ym − λ q1 = −a k q2 + e  ⇒ a = −cov(ym−λq1, q2) / (k var(q2))
        y_adj = ym - lam * q1
        den = float(np.dot(q2, q2))
        if den > 0:
            a_raw = float(-np.dot(y_adj, q2) / (k * den))
            source = "mid"
    if not np.isfinite(a_raw):
        yp = dpt / hs
        # yp − q0 − (λ−1) q1 = −a k q2 + e
        y_adj = yp - q0 - (lam - 1.0) * q1
        den = float(np.dot(q2, q2))
        if den > 0:
            a_raw = float(-np.dot(y_adj, q2) / (k * den))
            source = "price"

    lo, hi = 0.0, max(float(lam), 0.0)
    if not np.isfinite(a_raw):
        a_c = float("nan")
        binding = True
    elif lam <= 0:
        # economically unsigned λ — cannot project onto [0,λ]
        a_c = float(a_raw)
        binding = True
    else:
        a_c = float(min(max(a_raw, lo), hi))
        binding = bool(a_c != a_raw)
    b_c = float(lam - a_c) if np.isfinite(a_c) else float("nan")
    return {
        "ok": bool(np.isfinite(a_c) and np.isfinite(b_c)),
        "n": al["n"],
        "method": f"restricted_lambda_fix_{source}",
        "pi_reversal": p,
        "rho_q": al["rho"],
        "half_spread": hs,
        "lambda_ab": lam,
        "a_adverse_raw": float(a_raw),
        "a_adverse": a_c,
        "b_inventory": b_c,
        "as_share": float(a_c / lam) if np.isfinite(lam) and abs(lam) > 1e-12 else float("nan"),
        "inv_share": float(b_c / lam) if np.isfinite(lam) and abs(lam) > 1e-12 else float("nan"),
        "binding_constraint": binding,
        "economically_signed": bool(
            np.isfinite(a_c) and np.isfinite(b_c) and a_c >= 0 and b_c >= 0 and lam > 0
        ),
    }


def volume_bucket_hs_panel(
    ts_ns: NDArray[np.int64],
    px: NDArray[np.float64],
    side: NDArray[np.float64],
    qty: NDArray[np.float64],
    mid: NDArray[np.float64],
    *,
    bucket_volume: float,
    q_mode: str = "sign",
) -> dict[str, Any]:
    """Aggregate trades into equal-volume buckets for HS clocks.

    ``q_mode``:
      - ``sign``: Q = sign(net signed qty) ∈ {±1}
      - ``signed_volume``: Q = net signed coin qty (continuous)

    Returns bucket-level ``d_price``, ``d_mid``, ``side`` (Q), ``n_buckets``.
    """
    t = np.asarray(ts_ns, dtype=np.int64)
    p = np.asarray(px, dtype=np.float64)
    s = np.asarray(side, dtype=np.float64)
    q = np.asarray(qty, dtype=np.float64)
    m = np.asarray(mid, dtype=np.float64)
    ok = (
        np.isfinite(p)
        & np.isfinite(s)
        & np.isfinite(q)
        & np.isfinite(m)
        & (p > 0)
        & (q > 0)
        & (s != 0)
        & (m > 0)
    )
    t, p, s, q, m = t[ok], p[ok], s[ok], q[ok], m[ok]
    if t.size < 50 or bucket_volume <= 0:
        return {
            "ok": False,
            "n_buckets": 0,
            "d_price": np.zeros(0),
            "d_mid": np.zeros(0),
            "side": np.zeros(0),
        }
    signed = s * q
    closes_p: list[float] = []
    closes_m: list[float] = []
    closes_q: list[float] = []
    acc_v = 0.0
    acc_sv = 0.0
    last_p = float(p[0])
    last_m = float(m[0])
    open_p = last_p
    open_m = last_m
    for i in range(t.size):
        acc_v += float(q[i])
        acc_sv += float(signed[i])
        last_p = float(p[i])
        last_m = float(m[i])
        if acc_v >= bucket_volume:
            if q_mode == "signed_volume":
                qq = float(acc_sv)
            else:
                qq = 1.0 if acc_sv > 0 else (-1.0 if acc_sv < 0 else 0.0)
            if qq != 0.0 and np.isfinite(last_p) and np.isfinite(open_p):
                closes_p.append(last_p - open_p)
                closes_m.append(last_m - open_m)
                closes_q.append(qq)
            open_p, open_m = last_p, last_m
            acc_v = 0.0
            acc_sv = 0.0
    dp = np.asarray(closes_p, dtype=np.float64)
    dm = np.asarray(closes_m, dtype=np.float64)
    qq = np.asarray(closes_q, dtype=np.float64)
    return {
        "ok": bool(dp.size >= 60),
        "n_buckets": int(dp.size),
        "bucket_volume": float(bucket_volume),
        "q_mode": q_mode,
        "d_price": dp,
        "d_mid": dm,
        "side": qq,
    }


def dealer_inventory_proxy_ols(
    d_mid: NDArray[np.float64],
    side: NDArray[np.float64],
    *,
    qty: NDArray[np.float64] | None = None,
) -> dict[str, Any]:
    """Crypto-honest **proxy** for Huang–Stoll inventory term (14.c / 14.d.10).

    Public tape has no dealer inventory. Proxy::

        I_t = −∑_{i≤t} q_i · v_i     (dealer short after customer buys)

    Mid revision::

        ΔM_t = π Q_{t−1} + γ I_{t−1} + e_t

    Book β>0 loads on accumulated customer flow; with I = −flow we expect γ<0
    if the inventory channel is active (raise mid when dealer is short / I<0).
    Labelled ``proxy`` — not Promote-eligible alone.
    """
    dm = np.asarray(d_mid, dtype=np.float64)
    q = np.asarray(side, dtype=np.float64)
    v = np.ones_like(q) if qty is None else np.asarray(qty, dtype=np.float64)
    n = min(dm.size, q.size, v.size)
    dm, q, v = dm[:n], q[:n], v[:n]
    flow = q * np.where(np.isfinite(v) & (v > 0), v, 1.0)
    # dealer inventory analogue: opposite of cumulative customer signed flow
    I = -np.cumsum(flow)
    q_lag = np.roll(q, 1)
    I_lag = np.roll(I, 1)
    q_lag[0] = np.nan
    I_lag[0] = np.nan
    m = np.isfinite(dm) & np.isfinite(q_lag) & np.isfinite(I_lag) & (q_lag != 0)
    if int(m.sum()) < 60:
        return {
            "ok": False,
            "n": int(m.sum()),
            "pi_q": float("nan"),
            "gamma_inv_proxy": float("nan"),
            "label": "proxy",
        }
    y = dm[m]
    X = np.column_stack([q_lag[m], I_lag[m]])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    yhat = X @ coef
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return {
        "ok": True,
        "n": int(m.sum()),
        "pi_q": float(coef[0]),
        "gamma_inv_proxy": float(coef[1]),
        "r2": float(1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan"),
        "label": "proxy",
        "inventory_definition": "I=−cumsum(q·v) dealer analogue",
        "expected_gamma_sign": "negative if inventory channel active",
        "gamma_signed_ok": bool(np.isfinite(coef[1]) and coef[1] < 0),
    }


def trade_sign_acf(side: NDArray[np.float64], *, max_lag: int = 20) -> dict[str, Any]:
    """ACF of discrete trade signs q_t ∈ {±1} (inventory / herding diagnostic)."""
    q = np.asarray(side, dtype=np.float64)
    q = q[np.isfinite(q) & (q != 0)]
    if q.size < max_lag + 10:
        return {"n": int(q.size), "acf": []}
    q = q - q.mean()
    v = float(np.dot(q, q))
    acf = []
    for k in range(1, max_lag + 1):
        c = float(np.dot(q[k:], q[:-k]) / v) if v > 0 else float("nan")
        acf.append(c)
    return {"n": int(q.size), "acf": acf, "rho1": acf[0] if acf else float("nan")}


def quote_aligned_delta_mid(
    trade_ts_ns: NDArray[np.int64],
    trade_side: NDArray[np.float64],
    quote_ts_ns: NDArray[np.int64],
    quote_mid: NDArray[np.float64],
    *,
    trade_qty: NDArray[np.float64] | None = None,
    mode: str = "next_mid_change",
    max_lag_ns: int = 5_000_000_000,
) -> dict[str, Any]:
    """Align Δm to quote updates / trade timing (fixes asof-mid contamination).

    Contaminated baseline (do **not** use for Hasbrouck λ)::

        mid_pre_t = asof(trade_t);  Δm = mid_pre_{t+1} − mid_pre_t;  pair with q_{t+1}

    That pairs the revision *after* trade t with the *next* sign, and collapses
    many trades onto a stale TOB mid between collector updates.

    Modes
    ------
    ``next_mid_change`` (default, recommended)
        For each trade: mid_pre = last quote mid with ``ts ≤ trade_ts``;
        mid_post = first later quote mid that *differs* from mid_pre within
        ``max_lag_ns``.  Δm_t = mid_post − mid_pre, signed by q_t.
    ``pre_to_next_trade``
        Δm_t = mid_pre_{t+1} − mid_pre_t paired with **q_t** (not q_{t+1}).
        Still stale-mid heavy on sparse TOB; use as robustness only.
    ``quote_clock``
        Event index = quote updates where mid changes; q = most recent prior
        trade sign.  Sparse when TOB is ~0.5s and trades are denser.

    Returns arrays ``d_mid``, ``side``, ``ts``, optional ``qty``, plus diagnostics.
    """
    tt = np.asarray(trade_ts_ns, dtype=np.int64)
    qs = np.asarray(trade_side, dtype=np.float64)
    qt = np.asarray(quote_ts_ns, dtype=np.int64)
    qm = np.asarray(quote_mid, dtype=np.float64)
    qty = None if trade_qty is None else np.asarray(trade_qty, dtype=np.float64)
    n_tr = int(tt.size)
    out: dict[str, Any] = {
        "mode": mode,
        "max_lag_ns": int(max_lag_ns),
        "n_trades_in": n_tr,
        "n": 0,
        "d_mid": np.zeros(0, dtype=np.float64),
        "side": np.zeros(0, dtype=np.float64),
        "ts": np.zeros(0, dtype=np.int64),
        "qty": np.zeros(0, dtype=np.float64),
        "lag_ns": np.zeros(0, dtype=np.int64),
        "corr_dm_q": float("nan"),
        "ok": False,
    }
    if n_tr < 30 or qt.size < 10:
        return out

    if mode == "pre_to_next_trade":
        i_pre = np.searchsorted(qt, tt, side="right") - 1
        valid = (i_pre >= 0) & (i_pre < qm.size) & np.isfinite(qs) & (qs != 0)
        mid_pre = np.full(n_tr, np.nan)
        mid_pre[valid] = qm[i_pre[valid]]
        d_mid = np.diff(mid_pre)
        side_e = qs[:-1]
        ts_e = tt[:-1]
        qty_e = qty[:-1] if qty is not None else np.ones(n_tr - 1)
        m = (
            np.isfinite(d_mid)
            & np.isfinite(side_e)
            & (side_e != 0)
            & np.isfinite(mid_pre[:-1])
            & np.isfinite(mid_pre[1:])
        )
        d_mid, side_e, ts_e, qty_e = d_mid[m], side_e[m], ts_e[m], qty_e[m]
        lag = np.zeros(d_mid.size, dtype=np.int64)
    elif mode == "quote_clock":
        # mid-changing quote rows
        chg = np.flatnonzero(np.diff(qm) != 0) + 1
        if chg.size < 30:
            return out
        # most recent trade strictly before each quote-change timestamp
        ti = np.searchsorted(tt, qt[chg], side="left") - 1
        ok = (ti >= 0) & np.isfinite(qs[ti]) & (qs[ti] != 0)
        # require the trade to fall after the previous quote mid level started
        # (i.e. some trade activity associated with this revision)
        prev_q_ts = qt[chg - 1]
        ok &= tt[ti] >= prev_q_ts
        d_mid = (qm[chg] - qm[chg - 1])[ok]
        side_e = qs[ti[ok]]
        ts_e = qt[chg[ok]]
        qty_e = qty[ti[ok]] if qty is not None else np.ones(int(ok.sum()))
        lag = (qt[chg[ok]] - tt[ti[ok]]).astype(np.int64)
    elif mode == "next_mid_change":
        i_pre = np.searchsorted(qt, tt, side="right") - 1
        # first quote index strictly after trade
        i_after = np.searchsorted(qt, tt, side="right")
        d_list: list[float] = []
        s_list: list[float] = []
        t_list: list[int] = []
        q_list: list[float] = []
        lag_list: list[int] = []
        for i in range(n_tr):
            ip = int(i_pre[i])
            ja = int(i_after[i])
            if ip < 0 or ip >= qm.size or ja >= qm.size:
                continue
            if not (np.isfinite(qs[i]) and qs[i] != 0 and np.isfinite(qm[ip])):
                continue
            m0 = float(qm[ip])
            t0 = int(tt[i])
            j = ja
            # skip same-mid quotes until mid moves or lag exceeds
            while j < qm.size:
                dt = int(qt[j]) - t0
                if dt > max_lag_ns:
                    j = -1
                    break
                if np.isfinite(qm[j]) and float(qm[j]) != m0:
                    break
                j += 1
            else:
                j = -1
            if j < 0:
                continue
            d_list.append(float(qm[j]) - m0)
            s_list.append(float(qs[i]))
            t_list.append(t0)
            q_list.append(float(qty[i]) if qty is not None else 1.0)
            lag_list.append(int(qt[j]) - t0)
        d_mid = np.asarray(d_list, dtype=np.float64)
        side_e = np.asarray(s_list, dtype=np.float64)
        ts_e = np.asarray(t_list, dtype=np.int64)
        qty_e = np.asarray(q_list, dtype=np.float64)
        lag = np.asarray(lag_list, dtype=np.int64)
    else:
        raise ValueError(f"unknown mode={mode!r}")

    if d_mid.size < 30:
        out["n"] = int(d_mid.size)
        return out
    # correlation diagnostic
    q0, d0 = side_e - side_e.mean(), d_mid - d_mid.mean()
    den = float(np.sqrt(np.dot(q0, q0) * np.dot(d0, d0)))
    corr = float(np.dot(q0, d0) / den) if den > 0 else float("nan")
    out.update(
        {
            "n": int(d_mid.size),
            "d_mid": d_mid,
            "side": side_e,
            "ts": ts_e,
            "qty": qty_e,
            "lag_ns": lag,
            "corr_dm_q": corr,
            "median_lag_ms": float(np.median(lag) / 1e6) if lag.size else float("nan"),
            "ok": True,
        }
    )
    return out


def contemporaneous_lambda(
    d_mid: NDArray[np.float64],
    side: NDArray[np.float64],
) -> dict[str, float]:
    """Simple OLS Δm_t = λ q_t + e_t (no lags) — hygiene / bootstrap target."""
    y = np.asarray(d_mid, dtype=np.float64)
    q = np.asarray(side, dtype=np.float64)
    m = np.isfinite(y) & np.isfinite(q) & (q != 0)
    y, q = y[m], q[m]
    if y.size < 20:
        return {"n": float(y.size), "lambda": float("nan"), "r2": float("nan")}
    lam = float(np.dot(q, y) / np.dot(q, q))
    resid = y - lam * q
    ss_res = float(np.dot(resid, resid))
    ss_tot = float(np.dot(y - y.mean(), y - y.mean()))
    return {
        "n": float(y.size),
        "lambda": lam,
        "r2": float(1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan"),
        "sigma_e": float(np.sqrt(ss_res / max(y.size - 1, 1))),
    }


def lambda_time_split_bootstrap(
    d_mid: NDArray[np.float64],
    side: NDArray[np.float64],
    ts_ns: NDArray[np.int64],
    *,
    train_frac: float = 0.7,
    n_boot: int = 400,
    seed: int = 13,
) -> dict[str, Any]:
    """Chronological split + bootstrap CI for contemporaneous λ.

    Promote bar (honest): full-sample λ>0, train λ>0, test λ>0, and bootstrap
    95% CI lower bound > 0.
    """
    y = np.asarray(d_mid, dtype=np.float64)
    q = np.asarray(side, dtype=np.float64)
    t = np.asarray(ts_ns, dtype=np.int64)
    m = np.isfinite(y) & np.isfinite(q) & (q != 0) & np.isfinite(t.astype(np.float64))
    y, q, t = y[m], q[m], t[m]
    full = contemporaneous_lambda(y, q)
    tr, te = time_split_mask(t, train_frac=train_frac)
    train = contemporaneous_lambda(y[tr], q[tr])
    test = contemporaneous_lambda(y[te], q[te])
    # block-ish bootstrap: resample indices (iid) — report family honesty in NOTES
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot, dtype=np.float64)
    n = y.size
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boots[i] = contemporaneous_lambda(y[idx], q[idx])["lambda"]
    lo, hi = np.quantile(boots[np.isfinite(boots)], [0.025, 0.975])
    lam = float(full["lambda"])
    promote = bool(
        np.isfinite(lam)
        and lam > 0
        and float(train["lambda"]) > 0
        and float(test["lambda"]) > 0
        and float(lo) > 0
    )
    return {
        "full": full,
        "train": train,
        "test": test,
        "boot_lo": float(lo),
        "boot_hi": float(hi),
        "boot_point": float(np.nanmean(boots)),
        "n_boot": int(n_boot),
        "promote_ok": promote,
    }


def huang_stoll_basic_ols(
    d_mid: NDArray[np.float64],
    side: NDArray[np.float64],
    *,
    side_lag: NDArray[np.float64] | None = None,
) -> dict[str, Any]:
    """Huang–Stoll (1997) quote-mid revision with inventory proxy (Ch.14.d).

    With quotes observed we use mid changes (not trade prices)::

        ΔM_t = ((α+β) S/2) Q_{t−1} + e_t   ≈  π · Q_{t−1} + e_t

    Book identifies λ=(α+β) only as a lump unless Q is autocorrelated.
    Here we report OLS of Δm_t on q_{t-1} (π̂) and on (q_t, q_{t-1}) for the
    extended form; α vs β not separately identified without GMM + ρ̂.
    """
    dm = np.asarray(d_mid, dtype=np.float64)
    q = np.asarray(side, dtype=np.float64)
    if side_lag is None:
        q_lag = np.roll(q, 1)
        q_lag[0] = np.nan
    else:
        q_lag = np.asarray(side_lag, dtype=np.float64)
    m = np.isfinite(dm) & np.isfinite(q_lag) & (q_lag != 0)
    if int(m.sum()) < 40:
        return {"n": int(m.sum()), "pi_inv_info": float("nan"), "ok": False}
    y = dm[m]
    x = q_lag[m]
    pi = float(np.dot(x, y) / np.dot(x, x))
    resid = y - pi * x
    ss_res = float(np.dot(resid, resid))
    ss_tot = float(np.dot(y - y.mean(), y - y.mean()))
    # two-lag extension when current q also available
    m2 = m & np.isfinite(q) & (q != 0)
    out: dict[str, Any] = {
        "n": int(m.sum()),
        "pi_inv_info": pi,
        "r2": float(1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan"),
        "ok": True,
    }
    if int(m2.sum()) >= 40:
        y2 = dm[m2]
        X = np.column_stack([q[m2], q_lag[m2]])
        coef, *_ = np.linalg.lstsq(X, y2, rcond=None)
        out["coef_q"] = float(coef[0])
        out["coef_q_lag"] = float(coef[1])
    return out


def roll_time_split(
    mid: NDArray[np.float64],
    ts_ns: NDArray[np.int64],
) -> dict[str, Any]:
    """Chronological train/test Roll identification hygiene."""
    tr, te = time_split_mask(ts_ns, train_frac=0.7)
    out = {}
    for name, mask in (("train", tr), ("test", te)):
        m = mid[mask]
        out[name] = roll_on_mid_bps(m)
    return out


def ar_ols(
    x: NDArray[np.float64],
    *,
    lags: int = 10,
) -> dict[str, Any]:
    """OLS AR(K) on a zero-mean-ish series (Hasbrouck Ch.9 truncation of AR(∞)).

    Returns coefficients ``phi`` for ``x_t = Σ φ_k x_{t-k} + e_t``, residual
    variance, and ``phi_at_1 = 1 − Σ φ_k`` (lag polynomial at L=1).
    """
    y = np.asarray(x, dtype=np.float64)
    y = y[np.isfinite(y)]
    n = y.size
    if n < lags + 40:
        return {"ok": False, "n": int(n), "lags": lags}
    rows, targets = [], []
    for t in range(lags, n):
        feats = y[t - lags : t][::-1]  # lag1..lagK
        if not np.all(np.isfinite(feats)) or not np.isfinite(y[t]):
            continue
        rows.append(feats)
        targets.append(y[t])
    if len(rows) < 40:
        return {"ok": False, "n": len(rows), "lags": lags}
    X = np.asarray(rows, dtype=np.float64)
    yt = np.asarray(targets, dtype=np.float64)
    coef, *_ = np.linalg.lstsq(X, yt, rcond=None)
    resid = yt - X @ coef
    sse = float(np.sum(resid * resid))
    sigma_e2 = sse / max(yt.size - lags, 1)
    phi_sum = float(coef.sum())
    phi_at_1 = 1.0 - phi_sum
    return {
        "ok": True,
        "n": int(yt.size),
        "lags": lags,
        "phi": coef.tolist(),
        "phi_sum": phi_sum,
        "phi_at_1": phi_at_1,
        "sigma_e2": sigma_e2,
        "sigma_e": float(np.sqrt(sigma_e2)),
        "r2": float(1.0 - sse / np.sum((yt - yt.mean()) ** 2))
        if np.var(yt) > 0
        else float("nan"),
    }


def rw_variance_from_ar(ar: dict[str, Any]) -> dict[str, float]:
    """Random-walk innovation variance from AR approx to Δp (Ch.8–9).

    With ``φ(L) Δp_t = e_t``, MA ``q(L)=φ(L)^{-1}``, ``σ_w² = [q(1)]² σ_e²
    = σ_e² / φ(1)²``. Book typesetting sometimes writes ``σ_e²/φ(1)``; we use
    the squared long-run multiplier (Beveridge–Nelson / Watson).
    """
    if not ar.get("ok"):
        return {"sigma_w2": float("nan"), "sigma_w": float("nan"), "q1": float("nan")}
    phi1 = float(ar["phi_at_1"])
    se2 = float(ar["sigma_e2"])
    if abs(phi1) < 1e-12:
        return {"sigma_w2": float("nan"), "sigma_w": float("nan"), "q1": float("nan")}
    q1 = 1.0 / phi1
    sw2 = se2 * (q1 * q1)
    return {"sigma_w2": float(sw2), "sigma_w": float(np.sqrt(sw2)), "q1": float(q1)}


def ma1_from_acov(returns: NDArray[np.float64]) -> dict[str, float]:
    """Direct MA(1) moment estimates (Ch.9 GMM-style on γ₀, γ₁).

    ``x_t = e_t + θ e_{t-1}`` ⇒ ``γ₀=(1+θ²)σ_e²``, ``γ₁=θ σ_e²``.
    Invertible root: ``θ = (γ₀ − √(γ₀² − 4γ₁²))/(2γ₁)`` when |γ₁|<γ₀/2.
    Then ``σ_w² = (1+θ)² σ_e²``, pricing-error proxy ``σ_s² ≈ θ² σ_e²`` (Roll-like).
    """
    r = np.asarray(returns, dtype=np.float64)
    r = r[np.isfinite(r)]
    out = {
        "n": float(r.size),
        "g0": float("nan"),
        "g1": float("nan"),
        "theta": float("nan"),
        "sigma_e2": float("nan"),
        "sigma_w2": float("nan"),
        "sigma_s2": float("nan"),
        "identified": 0.0,
    }
    if r.size < 20:
        return out
    g0 = float(np.dot(r, r) / r.size)  # uncentered (microstructure-friendly)
    g1 = float(np.dot(r[1:], r[:-1]) / (r.size - 1))
    out["g0"], out["g1"] = g0, g1
    if abs(g1) < 1e-18 or abs(g1) >= g0 / 2:
        return out
    disc = g0 * g0 - 4.0 * g1 * g1
    if disc < 0:
        return out
    # invertible: |θ|<1 → pick root with smaller |θ|
    th1 = (g0 - np.sqrt(disc)) / (2.0 * g1)
    th2 = (g0 + np.sqrt(disc)) / (2.0 * g1)
    theta = float(th1 if abs(th1) <= abs(th2) else th2)
    if abs(theta) >= 1.0:
        return out
    se2 = g1 / theta
    if se2 <= 0:
        return out
    sw2 = (1.0 + theta) ** 2 * se2
    ss2 = (theta**2) * se2  # transient component scale (interpretive)
    out.update(
        {
            "theta": theta,
            "sigma_e2": float(se2),
            "sigma_w": float(np.sqrt(sw2)),
            "sigma_w2": float(sw2),
            "sigma_s": float(np.sqrt(ss2)),
            "sigma_s2": float(ss2),
            "identified": 1.0,
        }
    )
    return out


def impact_multipliers_from_ar(
    ar: dict[str, Any],
    *,
    horizon: int = 20,
) -> dict[str, Any]:
    """MA / IRF coefficients from AR via recursive forecasting (Ch.9.a).

    ``q_0=1``, ``q_1=φ_1``, ``q_2=φ_1²+φ_2``, … Cumulative sum ≈ level IRF of
    integrated price when ``x=Δp``.
    """
    if not ar.get("ok"):
        return {"ok": False}
    phi = np.asarray(ar["phi"], dtype=np.float64)
    K = phi.size
    q = np.zeros(horizon, dtype=np.float64)
    # E[x_{t+h} | e_t=1] with lags initially 0 except current shock absorbed in x_t=e_t
    # Recurrence: q_h = Σ_{k=1}^{min(K,h)} φ_k q_{h-k} with q_0 = 1 for the level of x response
    q[0] = 1.0
    for h in range(1, horizon):
        s = 0.0
        for k in range(1, min(K, h) + 1):
            s += phi[k - 1] * q[h - k]
        q[h] = s
    cum = np.cumsum(q)
    return {
        "ok": True,
        "q": q.tolist(),
        "cum_q": cum.tolist(),
        "q1_sum": float(cum[-1]) if horizon else float("nan"),
    }
