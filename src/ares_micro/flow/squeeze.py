r"""SqueezeMetrics / GEX Ed. (2020) implied-order-book objects.

Implements Black–Scholes δ/γ/vanna, dealer-directional OI proxies (DDOI),
gamma exposure (GEX), vanna exposure (VEX), GEX+, implied-book maps, and
squeeze / liquidity-regime helpers for ``research/books/squeeze_metrics/``.

**Hard distinction vs siblings**
- ``continuous.py`` Cont–Kukanov OFI — single-book flow; do **not** merge.
- ``cdme.py`` VLOOP/TCOST/PIM — cross-venue LOP; cross-link only.
- ``tob.py`` TOB utilities — underlying quotes only; cross-link only.

Paper: SqueezeMetrics (“GEX Ed.”), *The Implied Order Book*, 6 July 2020.
Crypto mapping uses Deribit options IV + option trades (warehouse) and
HL/Deribit underlying marks/TOB. Warehouse ``open_interest`` is **futures-
only** today — option DDOI is a **trade-flow / API-OI proxy**, labeled
honestly. Never soft-Promote TOB-cross as α. ClickHouse MCP banned.

Public surface::

    bs_d1, bs_delta, bs_gamma, bs_vanna
    contract_gex, contract_vex, aggregate_gex, aggregate_vex, gex_plus
    ddoi_from_trade_flow, unsigned_unit_ddoi
    implied_book_map, implied_book_levels, squeeze_intensity, regime_split_corr
    dealer_sign_proxy, gamma_exposure_proxy, vanna_exposure_proxy, regime_splits
    realized_vol, mid_range
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
from numpy.typing import NDArray

from ares_micro.core.arrays import consecutive_log_returns
from ares_micro.stats import pearson_r

SQRT_2PI = np.sqrt(2.0 * np.pi)

# Honesty labels for desk reports / notebooks
LABEL_TRADE_DDOI = "PROXY_trade_flow_DDOI"
LABEL_UNIT_OI = "PROXY_unit_OI_surface"
LABEL_API_OI = "live_API_OI_snapshot"
LABEL_FUTURES_OI = "QUARANTINE_futures_OI_not_options"


# ---------------------------------------------------------------------------
# Black–Scholes primitives (paper PDF p. 4)
# ---------------------------------------------------------------------------

def bs_d1(
    s: NDArray[np.floating] | float,
    k: NDArray[np.floating] | float,
    t: NDArray[np.floating] | float,
    r: float,
    v: NDArray[np.floating] | float,
) -> NDArray[np.floating]:
    """Black–Scholes d1. Invalid / tiny T or σ → nan."""
    s, k, t, v = np.broadcast_arrays(
        np.asarray(s, dtype=np.float64),
        np.asarray(k, dtype=np.float64),
        np.asarray(t, dtype=np.float64),
        np.asarray(v, dtype=np.float64),
    )
    out = np.full(s.shape, np.nan, dtype=np.float64)
    ok = (
        np.isfinite(s)
        & np.isfinite(k)
        & np.isfinite(t)
        & np.isfinite(v)
        & (s > 0)
        & (k > 0)
        & (t > 1e-8)
        & (v > 1e-8)
    )
    if not np.any(ok):
        return out
    sqrt_t = np.sqrt(t[ok])
    out[ok] = (np.log(s[ok] / k[ok]) + (r + 0.5 * v[ok] * v[ok]) * t[ok]) / (
        v[ok] * sqrt_t
    )
    return out


def _norm_cdf(x: NDArray[np.floating]) -> NDArray[np.floating]:
    """Φ(x) via erf (no scipy dependency required)."""
    return 0.5 * (1.0 + np.erf(np.asarray(x, dtype=np.float64) / np.sqrt(2.0)))


def _norm_pdf(x: NDArray[np.floating]) -> NDArray[np.floating]:
    x = np.asarray(x, dtype=np.float64)
    return np.exp(-0.5 * x * x) / SQRT_2PI


def bs_delta(
    flag: str | NDArray[np.str_] | Sequence[str],
    s: NDArray[np.floating] | float,
    k: NDArray[np.floating] | float,
    t: NDArray[np.floating] | float,
    r: float,
    v: NDArray[np.floating] | float,
) -> NDArray[np.floating]:
    """BS delta. Calls: Φ(d1). Puts: −Φ(−d1) (paper signed-put convention)."""
    d1 = bs_d1(s, k, t, r, v)
    out = np.full_like(d1, np.nan, dtype=np.float64)
    ok = np.isfinite(d1)
    if not np.any(ok):
        return out
    flags = np.asarray(flag)
    if flags.shape == ():
        flags = np.full(d1.shape, str(flags), dtype=object)
    else:
        flags = flags.astype(object)
        if flags.shape != d1.shape:
            flags = np.broadcast_to(flags, d1.shape)
    is_call = np.char.upper(np.asarray(flags, dtype=str)) 
    # np.char on object can fail — manual
    call_mask = np.zeros(d1.shape, dtype=bool)
    put_mask = np.zeros(d1.shape, dtype=bool)
    flat_f = flags.ravel()
    flat_call = call_mask.ravel()
    flat_put = put_mask.ravel()
    for i, f in enumerate(flat_f):
        u = str(f).strip().upper()[:1]
        if u == "C":
            flat_call[i] = True
        elif u == "P":
            flat_put[i] = True
    call_mask = flat_call.reshape(d1.shape)
    put_mask = flat_put.reshape(d1.shape)
    out[ok & call_mask] = _norm_cdf(d1[ok & call_mask])
    out[ok & put_mask] = -_norm_cdf(-d1[ok & put_mask])
    return out


def bs_gamma(
    s: NDArray[np.floating] | float,
    k: NDArray[np.floating] | float,
    t: NDArray[np.floating] | float,
    r: float,
    v: NDArray[np.floating] | float,
) -> NDArray[np.floating]:
    """BS gamma = φ(d1) / (S σ √T). Same for calls and puts."""
    d1 = bs_d1(s, k, t, r, v)
    s = np.asarray(s, dtype=np.float64)
    t = np.asarray(t, dtype=np.float64)
    v = np.asarray(v, dtype=np.float64)
    # broadcast
    s, t, v, d1 = np.broadcast_arrays(s, t, v, d1)
    out = np.full_like(d1, np.nan, dtype=np.float64)
    ok = np.isfinite(d1) & (s > 0) & (v > 1e-8) & (t > 1e-8)
    out[ok] = _norm_pdf(d1[ok]) / (s[ok] * v[ok] * np.sqrt(t[ok]))
    return out


def bs_vanna(
    s: NDArray[np.floating] | float,
    k: NDArray[np.floating] | float,
    t: NDArray[np.floating] | float,
    r: float,
    v: NDArray[np.floating] | float,
) -> NDArray[np.floating]:
    """∂δ/∂σ = −φ(d1) · d2 / σ  (common BS vanna form).

    Paper VEX uses finite-difference Δδ under IV shock; analytic vanna is the
    continuous analogue used for aggregation speed.
    """
    d1 = bs_d1(s, k, t, r, v)
    s_a = np.asarray(s, dtype=np.float64)
    k_a = np.asarray(k, dtype=np.float64)
    t_a = np.asarray(t, dtype=np.float64)
    v_a = np.asarray(v, dtype=np.float64)
    s_a, k_a, t_a, v_a, d1 = np.broadcast_arrays(s_a, k_a, t_a, v_a, d1)
    out = np.full_like(d1, np.nan, dtype=np.float64)
    ok = np.isfinite(d1) & (v_a > 1e-8) & (t_a > 1e-8)
    d2 = d1[ok] - v_a[ok] * np.sqrt(t_a[ok])
    out[ok] = -_norm_pdf(d1[ok]) * d2 / v_a[ok]
    return out


def delta_shock(
    flag: str | Sequence[str],
    s: float,
    k: NDArray[np.floating],
    t: NDArray[np.floating],
    r: float,
    v: NDArray[np.floating],
    *,
    ds: float = 0.0,
    dv: float = 0.0,
) -> NDArray[np.floating]:
    """Finite-difference Δδ under spot and/or IV shock (paper GEX/VEX spirit)."""
    k = np.asarray(k, dtype=np.float64)
    t = np.asarray(t, dtype=np.float64)
    v = np.asarray(v, dtype=np.float64)
    d0 = bs_delta(flag, s, k, t, r, v)
    d1 = bs_delta(flag, s + ds, k, np.maximum(t - 0.0, 1e-8), r, np.maximum(v + dv, 1e-8))
    return d1 - d0


# ---------------------------------------------------------------------------
# Contract / aggregate exposures
# ---------------------------------------------------------------------------

def contract_gex(
    ddoi: NDArray[np.floating],
    gamma: NDArray[np.floating],
    spot: float,
    *,
    contract_multiplier: float = 1.0,
    per_point: float = 1.0,
) -> NDArray[np.floating]:
    """Dollar gamma exposure per contract row.

    Paper: dealer hedge $ change per 1-pt move ≈ DDOI · γ · S · mult.
    ``per_point`` scales the move size (1.0 = $1 underlying move).
    Sign: positive DDOI (dealer long option / customer short) → +GEX
    (stabilizing) when using dealer-inventory convention from sold options.
    """
    ddoi = np.asarray(ddoi, dtype=np.float64)
    gamma = np.asarray(gamma, dtype=np.float64)
    return ddoi * gamma * float(spot) * float(contract_multiplier) * float(per_point)


def contract_vex(
    ddoi: NDArray[np.floating],
    vanna: NDArray[np.floating],
    spot: float,
    *,
    contract_multiplier: float = 1.0,
    d_sigma: float = 0.01,
) -> NDArray[np.floating]:
    """Dollar vanna exposure for a 1-vol-point (default 0.01) IV move."""
    ddoi = np.asarray(ddoi, dtype=np.float64)
    vanna = np.asarray(vanna, dtype=np.float64)
    return ddoi * vanna * float(d_sigma) * float(spot) * float(contract_multiplier)


def aggregate_gex(contract_gex_arr: NDArray[np.floating]) -> float:
    x = np.asarray(contract_gex_arr, dtype=np.float64)
    return float(np.nansum(x)) if x.size else float("nan")


def aggregate_vex(contract_vex_arr: NDArray[np.floating]) -> float:
    x = np.asarray(contract_vex_arr, dtype=np.float64)
    return float(np.nansum(x)) if x.size else float("nan")


def gex_plus(gex: float, vex: float) -> float:
    """GEX+ = GEX + VEX (paper PDF p. 9)."""
    if not (np.isfinite(gex) and np.isfinite(vex)):
        return float("nan")
    return float(gex) + float(vex)


# ---------------------------------------------------------------------------
# DDOI proxies
# ---------------------------------------------------------------------------

def ddoi_from_trade_flow(
    qty: NDArray[np.floating],
    aggressor_side: NDArray[np.integer] | NDArray[np.floating],
    *,
    customer_buy_is_dealer_short: bool = True,
) -> NDArray[np.floating]:
    """Trade-flow DDOI proxy (warehouse has option trades, not option OI).

    Convention: aggressor buy (+1) = customer buys option → dealer short
    that option → DDOI negative (destabilizing for γ of long customer).
    Sell aggressor (−1 / 2 depending on encoding) → dealer long → +DDOI.

    ``aggressor_side``: 1=buy/bid-hit, 2=sell/ask-hit (mercat common), or
    ±1 already signed.
    """
    q = np.asarray(qty, dtype=np.float64)
    side = np.asarray(aggressor_side, dtype=np.float64)
    signed = np.zeros_like(q)
    # map encodings
    buy = (side == 1) | ((side > 0) & (side != 2))
    sell = (side == 2) | (side < 0)
    # refine: if only ±1
    if np.all((side == 1) | (side == -1) | ~np.isfinite(side)):
        buy = side > 0
        sell = side < 0
    customer_sign = np.zeros_like(q)
    customer_sign[buy] = 1.0
    customer_sign[sell] = -1.0
    # dealer inventory opposite customer
    dealer = -customer_sign if customer_buy_is_dealer_short else customer_sign
    return dealer * np.abs(q)


def unsigned_unit_ddoi(n: int, sign: float = 1.0) -> NDArray[np.floating]:
    """Unit-OI surface (shape-only GEX). Label ``LABEL_UNIT_OI``."""
    return np.full(int(n), float(sign), dtype=np.float64)


def accumulate_ddoi_by_instrument(
    instrument_ids: NDArray[np.integer],
    trade_ddoi: NDArray[np.floating],
) -> dict[int, float]:
    """Sum trade-flow DDOI per instrument id."""
    out: dict[int, float] = {}
    ids = np.asarray(instrument_ids)
    flow = np.asarray(trade_ddoi, dtype=np.float64)
    for iid, x in zip(ids, flow):
        if not np.isfinite(x):
            continue
        k = int(iid)
        out[k] = out.get(k, 0.0) + float(x)
    return out


# ---------------------------------------------------------------------------
# Chain panel → GEX / VEX summary
# ---------------------------------------------------------------------------

def chain_exposures(
    *,
    flags: Sequence[str] | NDArray[np.str_],
    strikes: NDArray[np.floating],
    ttm_years: NDArray[np.floating],
    iv: NDArray[np.floating],
    ddoi: NDArray[np.floating],
    spot: float,
    r: float = 0.0,
    contract_multiplier: float = 1.0,
    per_point: float = 1.0,
    d_sigma: float = 0.01,
) -> dict[str, Any]:
    """Compute per-contract and aggregate GEX/VEX/GEX+ for one chain snapshot."""
    k = np.asarray(strikes, dtype=np.float64)
    t = np.asarray(ttm_years, dtype=np.float64)
    v = np.asarray(iv, dtype=np.float64)
    ddoi_a = np.asarray(ddoi, dtype=np.float64)
    # IV may be percent (e.g. 45) or decimal (0.45)
    v_use = np.where(np.isfinite(v) & (v > 1.5), v / 100.0, v)
    gamma = bs_gamma(spot, k, t, r, v_use)
    vanna = bs_vanna(spot, k, t, r, v_use)
    g_row = contract_gex(
        ddoi_a, gamma, spot, contract_multiplier=contract_multiplier, per_point=per_point
    )
    v_row = contract_vex(
        ddoi_a, vanna, spot, contract_multiplier=contract_multiplier, d_sigma=d_sigma
    )
    g = aggregate_gex(g_row)
    vx = aggregate_vex(v_row)
    return {
        "spot": float(spot),
        "n_contracts": int(k.size),
        "n_finite_gex": int(np.isfinite(g_row).sum()),
        "gamma": gamma,
        "vanna": vanna,
        "contract_gex": g_row,
        "contract_vex": v_row,
        "gex": g,
        "vex": vx,
        "gex_plus": gex_plus(g, vx),
    }


def implied_book_map(
    *,
    flags: Sequence[str] | NDArray[np.str_],
    strikes: NDArray[np.floating],
    ttm_years: NDArray[np.floating],
    iv: NDArray[np.floating],
    ddoi: NDArray[np.floating],
    spot_grid: NDArray[np.floating],
    iv_shock_grid: NDArray[np.floating],
    spot0: float,
    r: float = 0.0,
    contract_multiplier: float = 1.0,
) -> dict[str, Any]:
    """GEX+ heatmap over (spot, IV-shock) — paper PDF pp. 10–11 map spirit."""
    sg = np.asarray(spot_grid, dtype=np.float64)
    vg = np.asarray(iv_shock_grid, dtype=np.float64)
    z = np.full((sg.size, vg.size), np.nan, dtype=np.float64)
    for i, s in enumerate(sg):
        for j, dv in enumerate(vg):
            # shift IV surface by dv (absolute vol points in decimal)
            iv_s = np.asarray(iv, dtype=np.float64)
            iv_s = np.where(np.isfinite(iv_s) & (iv_s > 1.5), iv_s / 100.0, iv_s)
            pack = chain_exposures(
                flags=flags,
                strikes=strikes,
                ttm_years=ttm_years,
                iv=iv_s + float(dv),
                ddoi=ddoi,
                spot=float(s),
                r=r,
                contract_multiplier=contract_multiplier,
            )
            z[i, j] = pack["gex_plus"]
    return {
        "spot_grid": sg,
        "iv_shock_grid": vg,
        "gex_plus": z,
        "spot0": float(spot0),
        "scarce_mask": z < 0,
    }


def squeeze_intensity(
    gex: float,
    vex: float,
    *,
    gex_scale: float = 1.0,
    vex_scale: float = 1.0,
) -> float:
    """Higher = more squeeze / liquidity-taking pressure.

    Uses negative GEX+ mass: intensity = −min(GEX+, 0) scaled plus |VEX|− when
    VEX is negative (paper: negative VEX ↔ sustained vol).
    """
    gp = gex_plus(gex, vex)
    if not np.isfinite(gp):
        return float("nan")
    g_part = max(0.0, -float(gex) / max(gex_scale, 1e-12))
    v_part = max(0.0, -float(vex) / max(vex_scale, 1e-12))
    return float(g_part + v_part)


def scarcity_flag(gex_plus_val: float, *, threshold: float = 0.0) -> bool:
    """True when option-originated liquidity is scarce (GEX+ ≤ threshold)."""
    if not np.isfinite(gex_plus_val):
        return False
    return float(gex_plus_val) <= float(threshold)


# ---------------------------------------------------------------------------
# Realized vol / regime helpers (validation vs paper scatters)
# ---------------------------------------------------------------------------

def realized_vol(
    mid: NDArray[np.floating],
    *,
    dt_s: float = 1.0,
    annualize: bool = False,
) -> float:
    """Simple RV from mid path: std of log returns (optionally annualized)."""
    m = np.asarray(mid, dtype=np.float64)
    lr = consecutive_log_returns(m)
    lr = lr[np.isfinite(lr)]
    if lr.size < 2:
        return float("nan")
    sig = float(np.std(lr, ddof=1))
    if annualize and dt_s > 0:
        sig *= np.sqrt(365.25 * 24 * 3600 / dt_s)
    return sig


def mid_range(mid: NDArray[np.floating]) -> float:
    m = np.asarray(mid, dtype=np.float64)
    m = m[np.isfinite(m)]
    if m.size < 2:
        return float("nan")
    return float((np.max(m) - np.min(m)) / np.mean(m))


def regime_split_corr(
    x: NDArray[np.floating],
    y: NDArray[np.floating],
    regime: NDArray[np.bool_],
) -> dict[str, Any]:
    """corr(x,y) in True vs False regime masks."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    regime = np.asarray(regime, dtype=bool)

    def _c(a: NDArray[np.floating], b: NDArray[np.floating]) -> dict[str, float]:
        ok = np.isfinite(a) & np.isfinite(b)
        n = float(ok.sum())
        if n < 5:
            return {"r": float("nan"), "n": n}
        return {"r": pearson_r(a[ok], b[ok]), "n": n}

    return {
        "all": _c(x, y),
        "regime_true": _c(x[regime], y[regime]),
        "regime_false": _c(x[~regime], y[~regime]),
    }


def dealer_sign_from_gex(gex: float) -> str:
    """Desk label: stabilizing / destabilizing / neutral."""
    if not np.isfinite(gex):
        return "unknown"
    if gex > 0:
        return "stabilizing_long_dealer_gamma"
    if gex < 0:
        return "destabilizing_short_dealer_gamma"
    return "neutral"


# ---------------------------------------------------------------------------
# Requested book-facing aliases (wrappers over BS / DDOI primitives)
# ---------------------------------------------------------------------------

def dealer_sign_proxy(
    trade_ddoi_by_instrument: Mapping[int, float] | None = None,
    *,
    gex: float | None = None,
) -> dict[str, Any]:
    """Dealer directional sign from trade-flow DDOI (or aggregate GEX).

    Positive net DDOI / GEX → stabilizing (paper long-dealer-gamma spirit).
    Label: ``LABEL_TRADE_DDOI``.
    """
    if trade_ddoi_by_instrument:
        net = float(sum(trade_ddoi_by_instrument.values()))
        sign = 1 if net > 0 else (-1 if net < 0 else 0)
        return {
            "sign": sign,
            "net_ddoi": net,
            "n_instruments": len(trade_ddoi_by_instrument),
            "label": LABEL_TRADE_DDOI,
            "desk": dealer_sign_from_gex(float(gex) if gex is not None else net),
        }
    if gex is not None and np.isfinite(gex):
        sign = 1 if gex > 0 else (-1 if gex < 0 else 0)
        return {
            "sign": sign,
            "net_ddoi": float("nan"),
            "n_instruments": 0,
            "label": LABEL_TRADE_DDOI,
            "desk": dealer_sign_from_gex(float(gex)),
        }
    return {
        "sign": 0,
        "net_ddoi": float("nan"),
        "n_instruments": 0,
        "label": LABEL_TRADE_DDOI,
        "desk": "unknown",
    }


def gamma_exposure_proxy(**kwargs: Any) -> dict[str, Any]:
    """Alias → ``chain_exposures`` GEX (paper γ × DDOI)."""
    pack = chain_exposures(**kwargs)
    return {
        "gex": pack["gex"],
        "contract_gex": pack["contract_gex"],
        "n_contracts": pack["n_contracts"],
        "n_finite": pack["n_finite_gex"],
        "spot": pack["spot"],
        "label": LABEL_TRADE_DDOI,
        "pack": pack,
    }


def vanna_exposure_proxy(**kwargs: Any) -> dict[str, Any]:
    """Alias → ``chain_exposures`` VEX (paper vanna × DDOI)."""
    pack = chain_exposures(**kwargs)
    return {
        "vex": pack["vex"],
        "contract_vex": pack["contract_vex"],
        "n_contracts": pack["n_contracts"],
        "n_finite": pack["n_finite_gex"],
        "spot": pack["spot"],
        "label": LABEL_TRADE_DDOI,
        "pack": pack,
    }


def implied_book_levels(
    *,
    flags: Sequence[str] | NDArray[np.str_],
    strikes: NDArray[np.floating],
    ttm_years: NDArray[np.floating],
    iv: NDArray[np.floating],
    ddoi: NDArray[np.floating],
    spot: float,
    n_spot: int = 11,
    spot_bps: float = 50.0,
    iv_shocks: Sequence[float] = (-0.05, 0.0, 0.05),
    r: float = 0.0,
    contract_multiplier: float = 1.0,
) -> dict[str, Any]:
    """Alias → ``implied_book_map`` on a tight spot/IV grid around ``spot``."""
    step = float(spot) * float(spot_bps) / 1e4
    half = int(n_spot) // 2
    spot_grid = float(spot) + (np.arange(int(n_spot), dtype=np.float64) - half) * step
    return implied_book_map(
        flags=flags,
        strikes=strikes,
        ttm_years=ttm_years,
        iv=iv,
        ddoi=ddoi,
        spot_grid=spot_grid,
        iv_shock_grid=np.asarray(list(iv_shocks), dtype=np.float64),
        spot0=float(spot),
        r=r,
        contract_multiplier=contract_multiplier,
    )


def regime_splits(
    x: NDArray[np.floating],
    y: NDArray[np.floating],
    gex_or_regime: NDArray[np.floating] | NDArray[np.bool_],
    *,
    high_q: float = 0.75,
) -> dict[str, Any]:
    """Split corr(x,y) by high-GEX regime (or pass a bool mask)."""
    g = np.asarray(gex_or_regime)
    if g.dtype == bool or g.dtype == np.bool_:
        regime = g
    else:
        g = np.asarray(g, dtype=np.float64)
        thr = float(np.nanquantile(g[np.isfinite(g)], high_q)) if np.isfinite(g).any() else 0.0
        regime = np.isfinite(g) & (g >= thr)
    return regime_split_corr(x, y, regime)
