"""Book / tick realism — prefer denser Deribit/HL L2 / collector TOB when present.

Documents cadence (median Δt) and outside-TOB rate on dense days vs warehouse BBO.
Does not invent ms fills on sparse warehouse books.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np

LAB = Path(__file__).resolve().parent
APP = LAB.parent
BOOK = APP.parent
STRAT = APP / "strategy_lab"

for p in (str(STRAT), str(APP / "scripts"), str(BOOK / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from _data import ensure_env, load_day_trades  # noqa: E402
from sim.book import load_best_book, load_collector_tob_day, load_warehouse_tob  # noqa: E402


def _outside_rate(ts: np.ndarray, px: np.ndarray, book) -> dict[str, float]:
    if book is None or book.n < 20 or ts.size < 50:
        return {"n": 0, "outside_rate": float("nan"), "median_dt_s": float("nan")}
    asof = book.asof(ts)
    bid, ask = asof["bid"], asof["ask"]
    valid = asof["valid"] & np.isfinite(bid) & np.isfinite(ask) & (ask >= bid) & np.isfinite(px)
    if not valid.any():
        return {"n": 0, "outside_rate": float("nan"), "median_dt_s": float(book.median_dt_s)}
    out = (px[valid] < bid[valid]) | (px[valid] > ask[valid])
    return {
        "n": int(valid.sum()),
        "outside_rate": float(np.mean(out)),
        "median_dt_s": float(book.median_dt_s),
        "book_n": int(book.n),
        "source": book.source,
        "table": book.table,
    }


def probe_cell_books(venue: str, symbol: str, day: str) -> dict[str, Any]:
    ensure_env()
    out: dict[str, Any] = {"venue": venue, "symbol": symbol, "day": day}
    try:
        rec = load_day_trades(venue, symbol, day, quiet=True)
        tape = rec["tape"]
        ts = np.asarray(tape["ts"], dtype=np.int64)
        px = np.asarray(tape["px"], dtype=np.float64)
        out["n_trades"] = int(ts.size)
        out["complete"] = bool(rec.get("completeness", {}).get("complete"))
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out

    # downsample trades for outside check
    if ts.size > 80_000:
        step = int(np.ceil(ts.size / 80_000))
        ts, px = ts[::step], px[::step]

    coll = load_collector_tob_day(venue, symbol, day)
    wh = load_warehouse_tob(venue, symbol, day)
    best = load_best_book(venue, symbol, day)
    out["collector"] = _outside_rate(ts, px, coll) if coll else {"n": 0, "missing": True}
    out["warehouse"] = _outside_rate(ts, px, wh) if wh else {"n": 0, "missing": True}
    out["best"] = _outside_rate(ts, px, best) if best else {"n": 0, "missing": True}
    # denser if collector median_dt << warehouse
    c_dt = out["collector"].get("median_dt_s", float("nan"))
    w_dt = out["warehouse"].get("median_dt_s", float("nan"))
    out["collector_denser"] = bool(
        np.isfinite(c_dt) and np.isfinite(w_dt) and c_dt > 0 and c_dt < 0.5 * w_dt
    ) or bool(coll and coll.n > 1000 and (wh is None or coll.median_dt_s < (wh.median_dt_s or 99)))
    return out


def run_book_realism(
    *,
    dense_days: list[str] | None = None,
    core_days: list[str] | None = None,
    symbols: list[str] | None = None,
) -> dict[str, Any]:
    dense_days = dense_days or ["2026-09-29", "2026-09-30"]
    core_days = core_days or ["2026-09-04", "2026-09-07"]
    symbols = symbols or ["ETH", "BTC"]
    venues = ["hyperliquid", "deribit", "kraken"]
    probes = []
    for day in dense_days + core_days:
        for sym in symbols:
            for v in venues:
                # SOL only on dense for HL check
                print(f"[book] {day} {sym} {v}", flush=True)
                probes.append(probe_cell_books(v, sym, day))
    # also SOL HL on dense
    for day in dense_days:
        probes.append(probe_cell_books("hyperliquid", "SOL", day))

    dense = [p for p in probes if p.get("day") in dense_days and "error" not in p]
    core = [p for p in probes if p.get("day") in core_days and "error" not in p]
    n_dense_coll = sum(1 for p in dense if not p.get("collector", {}).get("missing"))
    n_core_coll = sum(1 for p in core if not p.get("collector", {}).get("missing"))

    def _med_dt(ps, key):
        vals = [
            p[key].get("median_dt_s")
            for p in ps
            if isinstance(p.get(key), dict) and np.isfinite(p[key].get("median_dt_s", np.nan) or np.nan)
        ]
        return float(np.median(vals)) if vals else float("nan")

    return {
        "n_probes": len(probes),
        "probes": probes,
        "summary": {
            "dense_days_collector_hits": n_dense_coll,
            "core_days_collector_hits": n_core_coll,
            "dense_median_collector_dt_s": _med_dt(dense, "collector"),
            "dense_median_warehouse_dt_s": _med_dt(dense, "warehouse"),
            "core_median_warehouse_dt_s": _med_dt(core, "warehouse"),
            "dense_median_outside_best": float(
                np.nanmedian(
                    [
                        p["best"].get("outside_rate", np.nan)
                        for p in dense
                        if isinstance(p.get("best"), dict)
                    ]
                )
            ),
            "note": (
                "Collector TOB denser on 2026-09-29/30 (HL); Phase-4 core days rely on "
                "warehouse BBO/l2_rebuild (~seconds). Prefer best book in strategy_lab."
            ),
        },
        "recommendation": (
            "Promote denser-book marking for HL on dense-TOB days; "
            "Hold ms-L2 claims on Phase-4 warehouse-only days"
        ),
    }
