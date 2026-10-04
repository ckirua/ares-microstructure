"""Deribit option IV / trades / catalog loaders (squeeze_metrics)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import numpy as np

from ares_micro.core.arrays import day_bounds_ns
from research.md.env import ensure_env
from research.md.marks import load_day_marks
from research.md.symbols import normalize_underlying, venue_instrument


def _column_batch_arrays(batch: Any) -> dict[str, np.ndarray]:
    """Normalize warehouse ColumnBatch / dict to plain ndarray columns."""
    if batch is None:
        return {}
    if isinstance(batch, dict):
        return {str(k): np.asarray(v) for k, v in batch.items()}
    cols = getattr(batch, "columns", None)
    if cols is None and hasattr(batch, "names"):
        cols = batch.names
    if cols is None:
        try:
            cols = list(batch)  # type: ignore[arg-type]
        except Exception:
            return {}
    out: dict[str, np.ndarray] = {}
    for c in cols:
        try:
            out[str(c)] = np.asarray(batch[c])
        except Exception:
            continue
    return out


def load_deribit_table_day(
    table: str,
    symbol: str,
    day: str,
    *,
    max_files: int = 16,
    quiet: bool = True,
) -> dict[str, Any]:
    """Best-effort Deribit warehouse table load (funding / open_interest / implied_vol)."""
    del quiet  # reserved for future quiet logging
    ensure_env()
    from warehouse import open_day
    from startarb.data.instruments import instrument_id as _iid

    inst = venue_instrument(symbol, "deribit")
    try:
        iid = int(_iid("deribit", inst))
        ids: list[int] | None = [iid]
    except Exception:
        ids = None
    try:
        batch = open_day("deribit", day).load(
            table, instrument_ids=ids, max_files=max_files
        )
        arr = _column_batch_arrays(batch)
        n = int(next(iter(arr.values())).size) if arr else 0
        return {
            "venue": "deribit",
            "table": table,
            "instrument": inst,
            "day": day,
            "n": n,
            "columns": arr,
            "ok": n > 0,
            "label": f"warehouse:deribit:{table}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "venue": "deribit",
            "table": table,
            "instrument": inst,
            "day": day,
            "n": 0,
            "columns": {},
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _mercat_deribit_path() -> Path:
    return Path(
        os.environ.get("MERCAT_DERIBIT_SRC")
        or (Path.home() / "lab" / "lab-n2070" / "deribit" / "src")
    )


def load_deribit_instrument_map(*, refresh: bool = False) -> list[dict[str, Any]]:
    """Deribit instrument catalog (options + futures) via mercat_deribit."""
    src = str(_mercat_deribit_path())
    if src not in sys.path:
        sys.path.insert(0, src)
    from mercat_deribit._instruments import load_instrument_map

    return list(load_instrument_map(refresh=refresh))


def deribit_option_catalog(
    underlying: str = "ETH",
    *,
    refresh: bool = False,
) -> dict[int, dict[str, Any]]:
    """instrument_id → compact option row for inverse ETH/BTC options."""
    u = normalize_underlying(underlying)
    rows = load_deribit_instrument_map(refresh=refresh)
    out: dict[int, dict[str, Any]] = {}
    for r in rows:
        if r.get("kind") != "option":
            continue
        name = str(r.get("instrument_name") or r.get("name") or "")
        if not name.startswith(f"{u}-"):
            continue
        if name.count("-") < 3:
            continue
        iid = int(r["instrument_id"])
        out[iid] = r
    return out


def load_eth_option_iv_day(
    day: str,
    *,
    underlying: str = "ETH",
    max_files: int = 64,
    min_rows_per_instrument: int = 1,
) -> dict[str, Any]:
    """Load Deribit ``implied_vol`` for ETH (or BTC) options; join catalog."""
    del min_rows_per_instrument  # reserved for future filtering
    ensure_env()
    from warehouse import open_day

    cat = deribit_option_catalog(underlying)
    if not cat:
        return {"ok": False, "error": "empty_option_catalog", "day": day, "n": 0}

    batch = open_day("deribit", day).load("implied_vol", max_files=max_files)
    ids = np.asarray(batch.columns["instrument_id"])
    ts = np.asarray(batch.columns["source_ts_ns"], dtype=np.uint64)
    iv_ticks = np.asarray(batch.columns["iv_ticks"], dtype=np.float64)
    mask = np.array([int(i) in cat for i in ids], dtype=bool)
    ids, ts, iv_ticks = ids[mask], ts[mask], iv_ticks[mask]
    if ids.size == 0:
        return {
            "ok": False,
            "error": "no_option_iv_rows",
            "day": day,
            "n": 0,
            "n_catalog": len(cat),
        }
    order = np.argsort(ts)
    ids, ts, iv_ticks = ids[order], ts[order], iv_ticks[order]
    last: dict[int, tuple[float, int]] = {}
    for iid, t, iv in zip(ids, ts, iv_ticks):
        last[int(iid)] = (float(iv), int(t))

    raw_vals = np.array([v for v, _ in last.values()], dtype=np.float64)
    scale = 1e8 if np.nanmedian(np.abs(raw_vals)) > 10 else 1.0

    day_end_ns = day_bounds_ns(day)[1]

    flags: list[str] = []
    strikes: list[float] = []
    ttm: list[float] = []
    ivs: list[float] = []
    iids: list[int] = []
    names: list[str] = []
    for iid, (iv_raw, _) in last.items():
        meta = cat[iid]
        strike = meta.get("strike")
        opt = meta.get("option_type") or ""
        exp_ms = meta.get("expiration_timestamp")
        name = str(meta.get("instrument_name") or "")
        if strike is None or exp_ms is None:
            parts = name.split("-")
            if len(parts) >= 4:
                try:
                    strike = float(parts[2])
                    opt = parts[3][:1]
                except Exception:
                    continue
            else:
                continue
        o = str(opt).strip().upper()[:1]
        if o not in ("C", "P"):
            if str(opt).lower().startswith("c"):
                o = "C"
            elif str(opt).lower().startswith("p"):
                o = "P"
            else:
                continue
        exp_ns = int(exp_ms) * 1_000_000
        t_years = max((exp_ns - day_end_ns) / (365.25 * 24 * 3600 * 1e9), 1e-6)
        iv = float(iv_raw) / scale
        flags.append(o)
        strikes.append(float(strike))
        ttm.append(float(t_years))
        ivs.append(iv)
        iids.append(iid)
        names.append(name)

    return {
        "ok": len(iids) > 0,
        "day": day,
        "underlying": normalize_underlying(underlying),
        "n": len(iids),
        "n_iv_raw": int(ids.size),
        "iv_scale": scale,
        "instrument_ids": np.asarray(iids, dtype=np.int64),
        "names": names,
        "flags": np.asarray(flags),
        "strikes": np.asarray(strikes, dtype=np.float64),
        "ttm_years": np.asarray(ttm, dtype=np.float64),
        "iv": np.asarray(ivs, dtype=np.float64),
        "label": "warehouse:deribit:implied_vol:options",
    }


def load_eth_option_trades_day(
    day: str,
    *,
    underlying: str = "ETH",
    max_files: int = 64,
    qty_lot_scale: float = 1e8,
) -> dict[str, Any]:
    """Option trades for trade-flow DDOI proxy."""
    ensure_env()
    from warehouse import open_day

    cat = deribit_option_catalog(underlying)
    batch = open_day("deribit", day).load("trade", max_files=max_files)
    ids = np.asarray(batch.columns["instrument_id"])
    mask = np.array([int(i) in cat for i in ids], dtype=bool)
    if not np.any(mask):
        return {"ok": False, "n": 0, "day": day, "error": "no_option_trades"}
    lots = np.asarray(batch.columns["md_qty_lots"], dtype=np.float64)[mask]
    cols = {
        "instrument_id": ids[mask],
        "source_ts_ns": np.asarray(batch.columns["source_ts_ns"])[mask],
        "price_ticks": np.asarray(batch.columns["price_ticks"], dtype=np.float64)[mask],
        "md_qty_lots": lots,
        "qty": lots / float(qty_lot_scale),
        "aggressor_side": np.asarray(batch.columns["aggressor_side"])[mask],
    }
    return {
        "ok": True,
        "day": day,
        "underlying": normalize_underlying(underlying),
        "n": int(mask.sum()),
        "n_instruments": int(len(set(int(i) for i in cols["instrument_id"]))),
        "qty_lot_scale": float(qty_lot_scale),
        "columns": cols,
        "label": "warehouse:deribit:trade:options",
    }


def load_deribit_underlying_mark(
    day: str,
    *,
    underlying: str = "ETH",
    max_files: int = 16,
) -> dict[str, Any]:
    """Deribit perpetual mark path for underlying S."""
    return load_day_marks("deribit", underlying, day, max_files=max_files)


__all__ = [
    "deribit_option_catalog",
    "load_deribit_instrument_map",
    "load_deribit_table_day",
    "load_deribit_underlying_mark",
    "load_eth_option_iv_day",
    "load_eth_option_trades_day",
    "_column_batch_arrays",
]
