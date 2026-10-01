from __future__ import annotations
#!/usr/bin/env python3
"""Thin Kraken **futures** quoted-TOB ingest → local parquet cache.

Why this exists
---------------
S3 ``mercat-kraken-md`` futures sealed MRCTCAP1 / public-md typed parquet carry
trade / mark / index / funding / OI / liquidation only — **no BBO or L2**.
Spot shards *do* have L2 (wired via ``_data.load_kraken_spot_tob_day``). Futures
quoted bid/ask therefore need a live collector.

This script polls the public REST orderbook (no ClickHouse MCP) and writes
xarb-compatible ``tob_*.parquet`` under ``out/kraken_futures_tob/YYYYMMDD/``.

Usage::

    python3 scripts/ingest_kraken_futures_tob.py --seconds 120 --interval 1.0
    python3 scripts/ingest_kraken_futures_tob.py --once   # single snapshot
"""


import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

BOOK = Path(__file__).resolve().parents[1]
OUT = BOOK / "out" / "kraken_futures_tob"
REST = "https://futures.kraken.com/derivatives/api/v3/orderbook"
DEFAULT_SYMBOLS = ("PF_XBTUSD", "PF_ETHUSD")

SCHEMA = pa.schema(
    [
        ("ts", pa.int64()),
        ("venue", pa.string()),
        ("symbol", pa.string()),
        ("bid", pa.float64()),
        ("ask", pa.float64()),
        ("bid_sz", pa.float64()),
        ("ask_sz", pa.float64()),
        ("source", pa.string()),
        ("seq", pa.int64()),
    ]
)


def _best_tob(order_book: dict) -> tuple[float, float, float, float] | None:
    """Best bid = max bid px; best ask = min ask px. Levels are [price, qty]."""
    bids = order_book.get("bids") or []
    asks = order_book.get("asks") or []
    if not bids or not asks:
        return None
    try:
        bid_px = max(float(lvl[0]) for lvl in bids if float(lvl[0]) > 0)
        ask_px = min(float(lvl[0]) for lvl in asks if float(lvl[0]) > 0)
        bid_sz = float(next(float(lvl[1]) for lvl in bids if float(lvl[0]) == bid_px))
        ask_sz = float(next(float(lvl[1]) for lvl in asks if float(lvl[0]) == ask_px))
    except (TypeError, ValueError, StopIteration):
        return None
    if not (ask_px > bid_px > 0):
        return None
    # reject absurd stubs (REST books can include far levels at $1 etc.)
    mid = 0.5 * (bid_px + ask_px)
    if 1e4 * (ask_px - bid_px) / mid > 200.0:
        # try second-best-ish: filter bids within 5% of ask
        near_bids = [lvl for lvl in bids if float(lvl[0]) > 0.95 * ask_px]
        near_asks = [lvl for lvl in asks if float(lvl[0]) < 1.05 * bid_px or float(lvl[0]) > bid_px]
        if not near_bids:
            return None
        bid_px = max(float(lvl[0]) for lvl in near_bids)
        bid_sz = float(next(float(lvl[1]) for lvl in near_bids if float(lvl[0]) == bid_px))
        ask_px = min(float(lvl[0]) for lvl in asks if float(lvl[0]) > bid_px)
        ask_sz = float(next(float(lvl[1]) for lvl in asks if float(lvl[0]) == ask_px))
        mid = 0.5 * (bid_px + ask_px)
        if not (ask_px > bid_px > 0) or 1e4 * (ask_px - bid_px) / mid > 200.0:
            return None
    return bid_px, ask_px, bid_sz, ask_sz


def fetch_tob(symbol: str, *, timeout: float = 10.0) -> dict | None:
    url = f"{REST}?symbol={symbol}"
    req = urllib.request.Request(url, headers={"User-Agent": "mn_tuwrv-ingest/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"fetch fail {symbol}: {exc}", flush=True)
        return None
    ob = payload.get("orderBook") or {}
    tob = _best_tob(ob)
    if tob is None:
        print(f"empty/invalid book {symbol}", flush=True)
        return None
    bid, ask, bsz, asz = tob
    ts_ns = time.time_ns()
    return {
        "ts": ts_ns,
        "venue": "kraken",
        "symbol": symbol,
        "bid": bid,
        "ask": ask,
        "bid_sz": bsz,
        "ask_sz": asz,
        "source": "rest:kraken_futures_orderbook",
        "spread_bps": 1e4 * (ask - bid) / (0.5 * (ask + bid)),
    }


def _day_dir(root: Path, ts_ns: int) -> Path:
    day = datetime.fromtimestamp(ts_ns / 1e9, tz=timezone.utc).strftime("%Y%m%d")
    d = root / day
    d.mkdir(parents=True, exist_ok=True)
    return d


def _next_idx(day_dir: Path) -> int:
    idxs = []
    for p in day_dir.glob("tob_*.parquet"):
        try:
            idxs.append(int(p.stem.split("_", 1)[1]))
        except (IndexError, ValueError):
            continue
    return (max(idxs) + 1) if idxs else 0


def write_rows(rows: list[dict], root: Path) -> Path:
    if not rows:
        raise RuntimeError("no rows to write")
    day_dir = _day_dir(root, int(rows[0]["ts"]))
    idx = _next_idx(day_dir)
    path = day_dir / f"tob_{idx:06d}.parquet"
    table = pa.table(
        {
            "ts": np.asarray([r["ts"] for r in rows], dtype=np.int64),
            "venue": [r["venue"] for r in rows],
            "symbol": [r["symbol"] for r in rows],
            "bid": np.asarray([r["bid"] for r in rows], dtype=np.float64),
            "ask": np.asarray([r["ask"] for r in rows], dtype=np.float64),
            "bid_sz": np.asarray([r["bid_sz"] for r in rows], dtype=np.float64),
            "ask_sz": np.asarray([r["ask_sz"] for r in rows], dtype=np.float64),
            "source": [r["source"] for r in rows],
            "seq": np.arange(len(rows), dtype=np.int64),
        },
        schema=SCHEMA,
    )
    pq.write_table(table, path, compression="zstd")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    ap.add_argument("--seconds", type=float, default=90.0, help="poll duration")
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between polls")
    ap.add_argument("--once", action="store_true", help="single snapshot then exit")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    deadline = time.time() + (0.0 if args.once else float(args.seconds))
    while True:
        for sym in args.symbols:
            rec = fetch_tob(sym)
            if rec is None:
                continue
            rows.append(rec)
            print(
                f"{sym} bid={rec['bid']:.4g} ask={rec['ask']:.4g} "
                f"spr={rec['spread_bps']:.3f}bps n={len(rows)}",
                flush=True,
            )
        if args.once or time.time() >= deadline:
            break
        time.sleep(max(0.2, float(args.interval)))

    if not rows:
        raise SystemExit("no TOB rows collected")
    path = write_rows(rows, args.out)
    meta = {
        "n_rows": len(rows),
        "symbols": sorted({r["symbol"] for r in rows}),
        "path": str(path),
        "spread_bps_med": float(np.median([r["spread_bps"] for r in rows])),
        "ts_first": int(rows[0]["ts"]),
        "ts_last": int(rows[-1]["ts"]),
        "note": "Futures quoted TOB from REST; historical S3 archives lack futures L2/BBO.",
    }
    (path.with_suffix(".meta.json")).write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
