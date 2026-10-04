"""Mark bars, cross-venue TOB panels, volume buckets, funding proxies."""

from __future__ import annotations

from typing import Any

import numpy as np

from research.md.constants import CORE_VENUES
from research.md.env import ensure_env
from research.md.symbols import normalize_underlying, normalize_venue, venue_instrument
from research.md.tob import load_kraken_spot_tob_day, load_venue_tob
from ares_micro.core.arrays import day_bounds_ns, normalize_side
from research.md.trades import load_day_trades


def load_day_marks(
    venue: str,
    symbol: str,
    day: str,
    *,
    bar_ns: int = 60_000_000_000,
    max_files: int = 24,
    quiet: bool = True,
) -> dict[str, Any]:
    """1m (default) mark/mid bars for DCM / basis construction."""
    ensure_env()
    from startarb.data.marks import load_mark_bars

    v = normalize_venue(venue)
    inst = venue_instrument(symbol, v)
    bars = load_mark_bars(v, inst, days=[day], bar_ns=bar_ns, max_files=max_files, quiet=quiet)
    close = np.asarray(bars["close"], dtype=np.float64)
    time = bars["time"]
    if hasattr(time, "dtype") and np.issubdtype(time.dtype, np.datetime64):
        ts = time.astype("datetime64[ns]").astype(np.int64)
    else:
        ts = np.asarray(time, dtype=np.int64)
    return {
        "venue": v,
        "instrument": inst,
        "day": day,
        "ts": ts,
        "mid": close,
        "n": int(close.size),
        "source": bars.get("source"),
        "dt_s": float(bars.get("dt_s") or bar_ns / 1e9),
    }


def load_cross_venue_marks(
    symbol: str,
    day: str,
    *,
    venues: tuple[str, ...] = CORE_VENUES,
    bar_ns: int = 60_000_000_000,
    max_files: int = 24,
    quiet: bool = True,
) -> dict[str, Any]:
    """Per-venue mark bars for one UTC day (basis = log(perp/home) later)."""
    out: dict[str, Any] = {"underlying": normalize_underlying(symbol), "day": day, "venues": {}}
    for v in venues:
        try:
            out["venues"][normalize_venue(v)] = load_day_marks(
                v, symbol, day, bar_ns=bar_ns, max_files=max_files, quiet=quiet
            )
        except Exception as exc:  # noqa: BLE001
            out["venues"][normalize_venue(v)] = {
                "venue": normalize_venue(v),
                "error": f"{type(exc).__name__}: {exc}",
                "n": 0,
            }
    return out


def load_cross_venue_tob(
    symbol: str,
    day: str,
    *,
    venues: tuple[str, ...] = ("hyperliquid", "deribit"),
    prefer_warehouse: bool = True,
    warehouse_max_files: int = 8,
    allow_kraken_synth: bool = False,
    require_real_quotes: bool = True,
) -> dict[str, Any]:
    """Best-effort TOB per venue for one UTC day (warehouse then collector)."""
    out: dict[str, Any] = {
        "underlying": normalize_underlying(symbol),
        "day": day,
        "venues": {},
        "errors": {},
        "kraken_mode": None,
    }
    for v in venues:
        vn = normalize_venue(v)
        try:
            tob = load_venue_tob(
                vn,
                symbol,
                day=day,
                prefer_warehouse=prefer_warehouse,
                warehouse_max_files=warehouse_max_files,
                allow_kraken_synth=allow_kraken_synth and vn == "kraken",
            )
            is_synth = bool(tob.get("is_synth")) or ("trade_synth" in str(tob.get("source") or ""))
            if vn == "kraken":
                out["kraken_mode"] = "trade_synth" if is_synth else "spot_l2"
            if require_real_quotes and is_synth:
                out["errors"][vn] = (
                    "refused_trade_synth_PROXY_NOT_TOB "
                    f"(source={tob.get('source')})"
                )
                continue
            out["venues"][vn] = tob
        except Exception as exc:  # noqa: BLE001
            out["errors"][vn] = f"{type(exc).__name__}: {exc}"
            if vn == "kraken":
                out["kraken_mode"] = "missing"
    out["n_venues"] = len(out["venues"])
    return out


def trade_volume_buckets(
    tape: dict[str, np.ndarray],
    *,
    bucket_s: float = 3600.0,
    day: str | None = None,
) -> dict[str, np.ndarray]:
    """Notional + count + signed imbalance per UTC bucket from clipped tape."""
    ts = np.asarray(tape["ts"], dtype=np.int64)
    px = np.asarray(tape.get("px", np.ones(ts.shape)), dtype=np.float64)
    qty = np.asarray(tape.get("qty", np.ones(ts.shape)), dtype=np.float64)
    side = normalize_side(tape.get("side", np.ones(ts.shape)))
    if ts.size == 0:
        empty = np.zeros(0, dtype=np.float64)
        return {
            "ts": np.zeros(0, dtype=np.int64),
            "notional": empty,
            "n_trades": empty,
            "imbalance": empty,
            "bucket_s": float(bucket_s),
        }
    step = int(float(bucket_s) * 1e9)
    if day:
        lo, _ = day_bounds_ns(day)
        t0 = lo
    else:
        t0 = int(ts.min() // step * step)
    bin_id = ((ts - t0) // step).astype(np.int64)
    n_bins = int(bin_id.max()) + 1
    centers = t0 + (np.arange(n_bins, dtype=np.int64) + 1) * step // 2
    notional = px * qty
    signed = side * qty
    notional_b = np.bincount(bin_id, weights=notional, minlength=n_bins).astype(np.float64)
    qty_b = np.bincount(bin_id, weights=qty, minlength=n_bins).astype(np.float64)
    signed_b = np.bincount(bin_id, weights=signed, minlength=n_bins).astype(np.float64)
    n_b = np.bincount(bin_id, minlength=n_bins).astype(np.float64)
    imb = np.full(n_bins, np.nan, dtype=np.float64)
    ok = qty_b > 0
    imb[ok] = signed_b[ok] / qty_b[ok]
    return {
        "ts": centers,
        "notional": notional_b,
        "n_trades": n_b,
        "imbalance": imb,
        "bucket_s": float(bucket_s),
    }


def funding_proxy_from_marks(
    home_mid: np.ndarray,
    home_ts: np.ndarray,
    *,
    window: int = 60,
) -> dict[str, np.ndarray]:
    """Crude public funding-stress proxy when funding table is absent."""
    mid = np.asarray(home_mid, dtype=np.float64)
    ts = np.asarray(home_ts, dtype=np.int64)
    r = np.diff(np.log(np.clip(mid, 1e-12, None)), prepend=np.nan)
    abs_r = np.abs(r)
    out = np.full(mid.shape, np.nan, dtype=np.float64)
    w = max(int(window), 2)
    for i in range(mid.size):
        j0 = i - w + 1
        if j0 < 0:
            continue
        chunk = abs_r[j0 : i + 1]
        chunk = chunk[np.isfinite(chunk)]
        if chunk.size >= w // 2:
            out[i] = float(np.mean(chunk))
    return {"ts": ts, "funding_proxy": out}


def load_squeeze_feature_inputs(
    symbol: str,
    day: str,
    *,
    venues: tuple[str, ...] = ("hyperliquid", "deribit"),
    warehouse_max_files: int = 8,
    allow_kraken_synth: bool = False,
    include_kraken_spot: bool = True,
) -> dict[str, Any]:
    """One-shot panel inputs for squeeze proxies: real TOB + marks + trades."""
    from research.md.options import (
        load_deribit_table_day,
        load_eth_option_iv_day,
        load_eth_option_trades_day,
    )

    ensure_env()
    vlist = list(venues)
    tob = load_cross_venue_tob(
        symbol,
        day,
        venues=tuple(vlist),
        warehouse_max_files=warehouse_max_files,
        allow_kraken_synth=allow_kraken_synth,
        require_real_quotes=True,
    )
    if include_kraken_spot and "kraken" not in tob["venues"]:
        try:
            kr = load_kraken_spot_tob_day(symbol, day, max_files=max(warehouse_max_files, 12))
            tob["venues"]["kraken"] = kr
            tob["kraken_mode"] = "spot_l2"
            tob["n_venues"] = len(tob["venues"])
        except Exception as exc:  # noqa: BLE001
            tob["errors"]["kraken"] = f"{type(exc).__name__}: {exc}"
            tob["kraken_mode"] = tob.get("kraken_mode") or "missing"

    marks = load_cross_venue_marks(symbol, day, venues=("hyperliquid", "deribit", "kraken"))
    trades: dict[str, Any] = {}
    for v in ("hyperliquid", "deribit"):
        try:
            trades[v] = load_day_trades(v, symbol, day, quiet=True)
        except Exception as exc:  # noqa: BLE001
            trades[v] = {"venue": v, "error": f"{type(exc).__name__}: {exc}"}

    funding = load_deribit_table_day("funding", symbol, day, max_files=8)
    oi = load_deribit_table_day("open_interest", symbol, day, max_files=8)
    try:
        opt_iv = load_eth_option_iv_day(day, underlying=normalize_underlying(symbol), max_files=12)
    except Exception as exc:  # noqa: BLE001
        opt_iv = {"ok": False, "n": 0, "error": f"{type(exc).__name__}: {exc}"}
    try:
        opt_tr = load_eth_option_trades_day(day, underlying=normalize_underlying(symbol), max_files=16)
    except Exception as exc:  # noqa: BLE001
        opt_tr = {"ok": False, "n": 0, "error": f"{type(exc).__name__}: {exc}"}

    return {
        "underlying": normalize_underlying(symbol),
        "day": day,
        "tob": tob,
        "marks": marks,
        "trades": trades,
        "deribit_funding": funding,
        "deribit_oi": oi,
        "option_iv": opt_iv,
        "option_trades": opt_tr,
        "options_chain_available": bool(opt_iv.get("ok")),
        "honesty": (
            "Deribit implied_vol covers OPTIONS; open_interest table is FUTURES-ONLY. "
            "DDOI = trade-flow proxy from option trades (or live API OI). "
            "GEX/VEX from BS γ/vanna on IV chain. Underlying TOB = HL+Deribit real quotes; "
            "Kraken spot_l2 only when dense. Never trade_synth; never TOB-cross α."
        ),
    }


__all__ = [
    "funding_proxy_from_marks",
    "load_cross_venue_marks",
    "load_cross_venue_tob",
    "load_day_marks",
    "load_squeeze_feature_inputs",
    "trade_volume_buckets",
]
