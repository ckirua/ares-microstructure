"""Best-effort TOB / L2 loaders for tick sims.

Cadence honesty (Phase-4 slice 2026-09-04…10):
- Trade tape: ms prints (warehouse ``trade``).
- Warehouse HL ``l2_rebuild``: ~5s median BBO update — **not** ms book.
- Collector TOB under ``results/xarb_md/tob``: denser, but days on disk are
  recent (e.g. 20260929+) and typically **miss** the Phase-4 window.
- Multilevel ``l2_snapshot_level``: depth snapshots; sparse vs trade clock.

Sims therefore mark to asof mid / touch with documented staleness — never claim
sub-second L2 fidelity on warehouse-only days.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

BOOK = Path(__file__).resolve().parents[3]
ROOT = BOOK.parents[2]
STARTARB = Path("/home/dev/srv/ares-startarb")
WAREHOUSE_SRC = Path("/home/dev/lab/lab-n2070/warehouse/src")
DEFAULT_TOB = STARTARB / "results" / "xarb_md" / "tob"

for p in (str(ROOT), str(STARTARB / "src"), str(WAREHOUSE_SRC), str(BOOK / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)


@dataclass
class BookState:
    ts: np.ndarray
    bid: np.ndarray
    ask: np.ndarray
    mid: np.ndarray
    bid_sz: np.ndarray
    ask_sz: np.ndarray
    source: str
    table: str | None = None
    median_dt_s: float = float("nan")
    n: int = 0
    depth_bid_l1_5: np.ndarray | None = None  # optional summed L1–L5
    depth_ask_l1_5: np.ndarray | None = None

    def asof(self, query_ts: np.ndarray) -> dict[str, np.ndarray]:
        i0 = np.searchsorted(self.ts, query_ts, side="right") - 1
        valid = (i0 >= 0) & (i0 < self.ts.size)
        out: dict[str, np.ndarray] = {}
        for key in ("bid", "ask", "mid", "bid_sz", "ask_sz"):
            arr = getattr(self, key)
            o = np.full(query_ts.shape, np.nan, dtype=np.float64)
            o[valid] = arr[i0[valid]]
            out[key] = o
        out["book_i"] = i0.astype(np.int64)
        out["valid"] = valid
        if self.depth_bid_l1_5 is not None:
            db = np.full(query_ts.shape, np.nan, dtype=np.float64)
            da = np.full(query_ts.shape, np.nan, dtype=np.float64)
            db[valid] = self.depth_bid_l1_5[i0[valid]]
            da[valid] = self.depth_ask_l1_5[i0[valid]]  # type: ignore[index]
            out["depth_bid"] = db
            out["depth_ask"] = da
        return out


def _median_dt_s(ts: np.ndarray) -> float:
    if ts.size < 3:
        return float("nan")
    d = np.diff(ts.astype(np.float64)) / 1e9
    d = d[d > 0]
    return float(np.median(d)) if d.size else float("nan")


def _from_arrays(
    ts: np.ndarray,
    bid: np.ndarray,
    ask: np.ndarray,
    bid_sz: np.ndarray,
    ask_sz: np.ndarray,
    *,
    source: str,
    table: str | None = None,
) -> BookState:
    m = np.isfinite(bid) & np.isfinite(ask) & (bid > 0) & (ask > 0) & (ask >= bid)
    # drop absurd spreads (>100 bps)
    mid = 0.5 * (bid + ask)
    spr = (ask - bid) / mid * 1e4
    m &= np.isfinite(spr) & (spr < 100.0)
    ts = np.asarray(ts, dtype=np.int64)[m]
    bid = np.asarray(bid, dtype=np.float64)[m]
    ask = np.asarray(ask, dtype=np.float64)[m]
    bid_sz = np.asarray(bid_sz, dtype=np.float64)[m]
    ask_sz = np.asarray(ask_sz, dtype=np.float64)[m]
    order = np.argsort(ts)
    ts, bid, ask, bid_sz, ask_sz = ts[order], bid[order], ask[order], bid_sz[order], ask_sz[order]
    mid = 0.5 * (bid + ask)
    return BookState(
        ts=ts,
        bid=bid,
        ask=ask,
        mid=mid,
        bid_sz=bid_sz,
        ask_sz=ask_sz,
        source=source,
        table=table,
        median_dt_s=_median_dt_s(ts),
        n=int(ts.size),
    )


def load_warehouse_tob(
    venue: str,
    symbol: str,
    day: str,
    *,
    max_files: int = 24,
    quotes_per_minute: int = 60,
) -> BookState | None:
    from _data import ensure_env, normalize_venue, venue_instrument
    from startarb.data.bbo_stream import load_quote_stream

    ensure_env()
    v = normalize_venue(venue)
    inst = venue_instrument(symbol, v)
    table = "l2_rebuild" if v == "hyperliquid" else None
    try:
        qs = load_quote_stream(
            v,
            inst,
            [day],
            table=table,
            max_files=max_files,
            prefer_shards=True,
            quotes_per_minute=quotes_per_minute,
            quiet=True,
            allow_trade_fallback=False,
        )
    except Exception:
        if v == "hyperliquid":
            return load_hl_l2_tob_from_snapshots(symbol, day, max_files=max(max_files, 96))
        return None
    bid_sz = np.asarray(getattr(qs, "bid_sz", getattr(qs, "bid_qty", None)), dtype=np.float64)
    ask_sz = np.asarray(getattr(qs, "ask_sz", getattr(qs, "ask_qty", None)), dtype=np.float64)
    return _from_arrays(
        qs.ts_ns,
        qs.bid,
        qs.ask,
        bid_sz,
        ask_sz,
        source=f"warehouse:{getattr(qs, 'table', table or 'bbo')}",
        table=getattr(qs, "table", table),
    )


def load_hl_l2_tob_from_snapshots(
    symbol: str,
    day: str,
    *,
    max_files: int = 128,
    trade_px: np.ndarray | None = None,
    trade_ts: np.ndarray | None = None,
) -> BookState | None:
    """Rebuild HL L0 TOB from ``l2_snapshot_level`` when catalog id misses flat-era rows.

    HL ask levels are encoded 20..39. Instrument id is chosen by max corr of
    L0 mid vs trade mid (scale = median(bid_ticks)/median(trade_px)). Cadence
    is snapshot-sparse (seconds), not ms.
    """
    from _data import ensure_env, load_day_trades, normalize_underlying
    from warehouse import open_day

    ensure_env()
    u = normalize_underlying(symbol)
    cache_dir = Path(__file__).resolve().parents[1] / "out" / "book_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"hl_l2tob_{u}_{day}.npz"
    if cache_path.exists():
        try:
            z = np.load(cache_path)
            return BookState(
                ts=z["ts"],
                bid=z["bid"],
                ask=z["ask"],
                mid=z["mid"],
                bid_sz=z["bid_sz"],
                ask_sz=z["ask_sz"],
                source=str(z["source"]),
                table=str(z["table"]),
                median_dt_s=float(z["median_dt_s"]),
                n=int(z["ts"].size),
            )
        except Exception:
            pass

    if trade_px is None or trade_ts is None:
        try:
            rec = load_day_trades("hyperliquid", u, day, quiet=True)
            trade_ts = np.asarray(rec["tape"]["ts"], dtype=np.int64)
            trade_px = np.asarray(rec["tape"]["px"], dtype=np.float64)
        except Exception:
            return None
    trade_ts = np.asarray(trade_ts, dtype=np.int64)
    trade_px = np.asarray(trade_px, dtype=np.float64)
    mtr = np.isfinite(trade_px) & (trade_px > 0)
    if int(mtr.sum()) < 200:
        return None
    trade_ts, trade_px = trade_ts[mtr], trade_px[mtr]
    t_med = float(np.median(trade_px))

    try:
        batch = open_day("hyperliquid", day).load("l2_snapshot_level", max_files=max_files)
    except Exception:
        return None
    if batch is None or int(getattr(batch, "n_rows", len(batch.columns.get("source_ts_ns", [])))) < 100:
        return None

    iid = np.asarray(batch.columns["instrument_id"], dtype=np.int64)
    side = np.asarray(batch.columns["side"], dtype=np.int64)
    level = np.asarray(batch.columns["level"], dtype=np.int64)
    pt = np.asarray(batch.columns["price_ticks"], dtype=np.float64)
    ts = np.asarray(batch.columns["source_ts_ns"], dtype=np.int64)
    qty = np.asarray(batch.columns["md_qty_lots"], dtype=np.float64)

    # 2s grid for matching
    t0, t1 = int(trade_ts.min()), int(trade_ts.max())
    grid = np.arange(t0, t1, int(2e9), dtype=np.int64)
    if grid.size < 50:
        return None
    ti = np.searchsorted(trade_ts, grid, side="right") - 1
    ok = ti >= 0
    t_mid = trade_px[np.clip(ti, 0, trade_px.size - 1)]

    best = None  # (corr, rel, u, scale)
    for u_id in np.unique(iid):
        bid_m = (iid == u_id) & (side == 1) & (level == 0)
        ask_m = (iid == u_id) & (side == 2) & (level == 20)
        if int(bid_m.sum()) < 30 or int(ask_m.sum()) < 30:
            continue
        scale = float(np.median(pt[bid_m]) / t_med)
        if not np.isfinite(scale) or scale <= 0:
            continue
        order_b = np.argsort(ts[bid_m])
        tba = ts[bid_m][order_b]
        bpx = (pt[bid_m] / scale)[order_b]
        bsz = qty[bid_m][order_b]
        order_a = np.argsort(ts[ask_m])
        taa = ts[ask_m][order_a]
        apx = (pt[ask_m] / scale)[order_a]
        asz = qty[ask_m][order_a]
        ib = np.searchsorted(tba, grid, side="right") - 1
        ia = np.searchsorted(taa, grid, side="right") - 1
        valid = (ib >= 0) & (ia >= 0) & ok
        if int(valid.sum()) < 80:
            continue
        mid = 0.5 * (bpx[ib[valid]] + apx[ia[valid]])
        tm = t_mid[valid]
        if float(np.std(mid)) < 1e-12 or float(np.std(tm)) < 1e-12:
            continue
        corr = float(np.corrcoef(mid, tm)[0, 1])
        rel = float(np.median(np.abs(mid - tm) / tm))
        if not np.isfinite(corr) or corr < 0.4 or rel > 0.08:
            continue
        cand = (corr, -rel, int(u_id), scale, tba, bpx, bsz, taa, apx, asz)
        if best is None or cand[0] > best[0] or (cand[0] == best[0] and cand[1] > best[1]):
            best = cand
    if best is None:
        return None

    _, _, u_id, scale, tba, bpx, bsz, taa, apx, asz = best
    # merge bid/ask onto union of timestamps (asof)
    all_ts = np.unique(np.concatenate([tba, taa]))
    ib = np.searchsorted(tba, all_ts, side="right") - 1
    ia = np.searchsorted(taa, all_ts, side="right") - 1
    valid = (ib >= 0) & (ia >= 0)
    all_ts = all_ts[valid]
    bid = bpx[ib[valid]]
    ask = apx[ia[valid]]
    bid_sz = bsz[ib[valid]]
    ask_sz = asz[ia[valid]]
    # qty lots → coin-ish (relative depth OK for plots); keep raw lots
    book = _from_arrays(
        all_ts,
        bid,
        ask,
        bid_sz,
        ask_sz,
        source=f"warehouse:l2_snapshot_level:iid={u_id}",
        table="l2_snapshot_level",
    )
    try:
        np.savez_compressed(
            cache_path,
            ts=book.ts,
            bid=book.bid,
            ask=book.ask,
            mid=book.mid,
            bid_sz=book.bid_sz,
            ask_sz=book.ask_sz,
            source=np.asarray(book.source),
            table=np.asarray(book.table or ""),
            median_dt_s=np.asarray(book.median_dt_s),
        )
    except Exception:
        pass
    return book


def load_collector_tob_day(
    venue: str,
    symbol: str,
    day: str,
    *,
    tob_root: Path = DEFAULT_TOB,
    max_rows: int = 400_000,
) -> BookState | None:
    """Collector TOB clipped to UTC day (when day dir exists)."""
    import pandas as pd
    import pyarrow.parquet as pq

    from _data import day_bounds_ns, normalize_underlying, normalize_venue, venue_instrument

    v = normalize_venue(venue)
    u = normalize_underlying(symbol)
    native = venue_instrument(u, v).upper()
    aliases = {u.upper(), native, str(symbol).strip().upper()}
    day_tag = day.replace("-", "")
    day_dir = tob_root / day_tag
    if not day_dir.is_dir():
        return None
    frames = []
    for f in sorted(day_dir.glob("tob_*.parquet")):
        t = pq.read_table(
            f, columns=["ts", "venue", "symbol", "bid", "ask", "bid_sz", "ask_sz"]
        ).to_pandas()
        frames.append(t)
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)
    sym = df["symbol"].astype(str).str.upper()
    df = df[(df["venue"].astype(str).str.lower() == v) & sym.isin(aliases)]
    lo, hi = day_bounds_ns(day)
    df = df[(df["ts"] >= lo) & (df["ts"] < hi)].sort_values("ts")
    if df.empty:
        return None
    if len(df) > max_rows:
        df = df.iloc[:: max(1, len(df) // max_rows)]
    return _from_arrays(
        df["ts"].to_numpy(np.int64),
        df["bid"].to_numpy(np.float64),
        df["ask"].to_numpy(np.float64),
        df["bid_sz"].to_numpy(np.float64),
        df["ask_sz"].to_numpy(np.float64),
        source="collector",
        table="xarb_md/tob",
    )


def attach_hl_l2_depth(book: BookState, symbol: str, *, max_files: int = 40) -> BookState:
    """Optionally attach summed L1–L5 depth from warehouse snapshot cache."""
    try:
        emp = str(ROOT / "research" / "books" / "empirical_mm" / "scripts")
        if emp not in sys.path:
            sys.path.insert(0, emp)
        import importlib

        # empirical_mm scripts/_data.py (not cross_miniflash) — load by path
        import importlib.util

        path = Path(emp) / "_data.py"
        spec = importlib.util.spec_from_file_location("emp_mm_data", path)
        if spec is None or spec.loader is None:
            return book
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if not hasattr(mod, "load_hl_l2_levels"):
            return book
        l2 = mod.load_hl_l2_levels(symbol, max_files=max_files)
    except Exception:
        return book
    ts = np.asarray(l2.get("ts", []), dtype=np.int64)
    if ts.size < 10:
        return book
    # Aggregate per snapshot_id: sum qty on levels 0..4 bid / ask
    snap = np.asarray(l2["snapshot_id"], dtype=np.int64)
    side = np.asarray(l2["side"], dtype=np.int64)
    level = np.asarray(l2["level"], dtype=np.int64)
    qty = np.asarray(l2["qty"], dtype=np.float64)
    # HL ask levels often 20..39
    is_bid = (side == 0) | ((level >= 0) & (level < 20) & (side != 1))
    is_ask = (side == 1) | (level >= 20)
    lev_norm = np.where(level >= 20, level - 20, level)
    near = lev_norm <= 4
    # reduce by unique snapshot order of first ts
    order = np.argsort(ts)
    ts, snap, is_bid, is_ask, near, qty = (
        ts[order],
        snap[order],
        is_bid[order],
        is_ask[order],
        near[order],
        qty[order],
    )
    uniq, first = np.unique(snap, return_index=True)
    snap_ts = ts[first]
    bid_d = np.zeros(uniq.size, dtype=np.float64)
    ask_d = np.zeros(uniq.size, dtype=np.float64)
    # map snap -> index
    snap_to_i = {int(s): i for i, s in enumerate(uniq)}
    for i in range(ts.size):
        if not near[i]:
            continue
        j = snap_to_i.get(int(snap[i]))
        if j is None:
            continue
        if is_bid[i]:
            bid_d[j] += float(qty[i]) if np.isfinite(qty[i]) else 0.0
        elif is_ask[i]:
            ask_d[j] += float(qty[i]) if np.isfinite(qty[i]) else 0.0
    # asof onto book timestamps
    i0 = np.searchsorted(snap_ts, book.ts, side="right") - 1
    valid = (i0 >= 0) & (i0 < snap_ts.size)
    db = np.full(book.ts.shape, np.nan, dtype=np.float64)
    da = np.full(book.ts.shape, np.nan, dtype=np.float64)
    db[valid] = bid_d[i0[valid]]
    da[valid] = ask_d[i0[valid]]
    book.depth_bid_l1_5 = db
    book.depth_ask_l1_5 = da
    return book


def load_best_book(
    venue: str,
    symbol: str,
    day: str,
    *,
    prefer_collector: bool = True,
    attach_l2_depth: bool = True,
) -> BookState | None:
    """Collector TOB if available for day, else warehouse BBO/l2_rebuild."""
    book = None
    if prefer_collector:
        book = load_collector_tob_day(venue, symbol, day)
    if book is None or book.n < 50:
        book = load_warehouse_tob(venue, symbol, day)
    if book is None or book.n < 10:
        return None
    if attach_l2_depth and str(venue).lower() in ("hyperliquid", "hl"):
        book = attach_hl_l2_depth(book, symbol)
    return book


def book_meta(book: BookState | None) -> dict[str, Any]:
    if book is None:
        return {"available": False, "source": None, "n": 0, "median_dt_s": None}
    return {
        "available": True,
        "source": book.source,
        "table": book.table,
        "n": book.n,
        "median_dt_s": book.median_dt_s,
        "has_l2_depth": book.depth_bid_l1_5 is not None,
        "cadence_note": (
            "collector ms-ish TOB"
            if book.source == "collector"
            else (
                "HL l2_snapshot_level rebuild (~minutes median on flat-era); not ms L2"
                if "l2_snapshot_level" in str(book.source)
                else "warehouse BBO/l2_rebuild (~seconds); not ms L2"
            )
        ),
    }
