"""Rindi et al. tick-size theory/evidence helpers (MMCV #3 Paris 2014).

Owns prediction tables, relative-tick panels, constraint flags, and
cross-venue τ-gap features. Cross-link mmip ``tick.*`` Promotes; do **not**
merge APIs or re-Promote the same descriptors without new falsifiers.

Reuse: ``ares_micro.book.spreads``, ``tob.infer_tick`` / ``mid_price``, ``lob``.
"""

from __future__ import annotations

from typing import Any, Iterable, Literal, Sequence

import numpy as np
from numpy.typing import NDArray

from ares_micro.book.spreads import quoted_spread_bps
from ares_micro.book.tob import infer_tick, mid_price

BookLiq = Literal["liquid", "less_liquid", "any"]
TickRegime = Literal[
    "large_abs_reduction",
    "small_abs_reduction",
    "large_abs_increase",
    "small_abs_increase",
    "rel_tick_up",
    "rel_tick_down",
]
MqMetric = Literal[
    "quoted_spread",
    "relative_spread",
    "bbo_depth",
    "total_depth",
    "volume",
    "welfare",
]

# Deck tables ~pp. 20–29 (Rindi / Buti–Consonni–Wen–Werner slides).
# Sign = expected ΔMQ when the named regime occurs: +1 improve MQ metric
# as conventionally "better" for that column (spread ↓ = +1 for spreads;
# depth/volume ↑ = +1). Welfare cells are Kill/out-of-scope for crypto desk.
_EXPECTED_SIGNS: dict[tuple[TickRegime, BookLiq, MqMetric], int] = {}


def _put(regime: TickRegime, book: BookLiq, metric: MqMetric, sign: int) -> None:
    _EXPECTED_SIGNS[(regime, book, metric)] = int(sign)


# Large absolute tick reduction (pp. 20–22): liquid MQ↑ / volume↑; thin MQ↓ / volume↓
for m in ("quoted_spread", "relative_spread"):
    _put("large_abs_reduction", "liquid", m, +1)  # spreads tighten
    _put("large_abs_reduction", "less_liquid", m, -1)
_put("large_abs_reduction", "liquid", "bbo_depth", -1)  # mass undercuts / spreads across levels
_put("large_abs_reduction", "less_liquid", "bbo_depth", -1)
_put("large_abs_reduction", "liquid", "total_depth", +1)
_put("large_abs_reduction", "less_liquid", "total_depth", -1)
_put("large_abs_reduction", "liquid", "volume", +1)
_put("large_abs_reduction", "less_liquid", "volume", -1)
_put("large_abs_reduction", "liquid", "welfare", 0)  # unobservable
_put("large_abs_reduction", "less_liquid", "welfare", 0)

# Small absolute tick reduction (pp. 24–25): no undercutting → LO→MO; MQ deteriorates
for book in ("liquid", "less_liquid"):
    for m in ("quoted_spread", "relative_spread", "bbo_depth", "total_depth", "volume"):
        # spreads: deterioration = widen = −1; depth/vol fall = −1
        _put("small_abs_reduction", book, m, -1)  # type: ignore[arg-type]
    _put("small_abs_reduction", book, "welfare", 0)  # type: ignore[arg-type]

# Large absolute tick increase ≈ large relative-tick ↑ (p. 29) — flip of large reduction
for book, flip in (("liquid", -1), ("less_liquid", +1)):
    # liquid: MQ deteriorates on increase; thin: opposite of thin-on-reduction
    for m in ("quoted_spread", "relative_spread"):
        _put("large_abs_increase", book, m, -flip)  # type: ignore[arg-type]
    _put("large_abs_increase", book, "bbo_depth", +1 if book == "liquid" else -1)  # type: ignore[arg-type]
    _put("large_abs_increase", book, "total_depth", flip)  # type: ignore[arg-type]
    _put("large_abs_increase", book, "volume", flip)  # type: ignore[arg-type]
    _put("large_abs_increase", book, "welfare", 0)  # type: ignore[arg-type]

# Small absolute tick increase (p. 29 bottom): weaker / high-priced nuance → Hold cells
for book in ("liquid", "less_liquid"):
    for m in ("quoted_spread", "relative_spread", "bbo_depth", "total_depth", "volume", "welfare"):
        _put("small_abs_increase", book, m, 0)  # type: ignore[arg-type]

# Relative tick equivalence (p. 26): ↓τ ≈ ↑v for rel spread / depth / volume
# Relative tick UP (τ/mid ↑): like large abs increase on liquid books for most MQ
for m, s in (
    ("quoted_spread", 0),  # quoted $ spread ∝ value; not pure equivalence
    ("relative_spread", -1),  # τ/mid ↑ → relative spread pressure ↑ (worsen)
    ("bbo_depth", +1),
    ("total_depth", +1),
    ("volume", -1),
    ("welfare", 0),
):
    _put("rel_tick_up", "any", m, s)  # type: ignore[arg-type]
    _put("rel_tick_up", "liquid", m, s)  # type: ignore[arg-type]
    _put("rel_tick_up", "less_liquid", m, s)  # type: ignore[arg-type]
    _put("rel_tick_down", "any", m, -s if s != 0 else 0)  # type: ignore[arg-type]
    _put("rel_tick_down", "liquid", m, -s if s != 0 else 0)  # type: ignore[arg-type]
    _put("rel_tick_down", "less_liquid", m, -s if s != 0 else 0)  # type: ignore[arg-type]


MQ_METRICS: tuple[MqMetric, ...] = (
    "quoted_spread",
    "relative_spread",
    "bbo_depth",
    "total_depth",
    "volume",
    "welfare",
)


def expected_sign(
    regime: TickRegime,
    metric: MqMetric,
    *,
    book: BookLiq = "any",
) -> int:
    """Return deck expected sign ∈ {−1, 0, +1} for (regime, book, metric).

    Spread metrics: +1 means *improve* (tighten). Depth/volume: +1 means rise.
    ``0`` = ambiguous / out-of-scope (welfare) / weak small-Δ Hold.
    """
    key = (regime, book, metric)
    if key in _EXPECTED_SIGNS:
        return _EXPECTED_SIGNS[key]
    if book != "any" and (regime, "any", metric) in _EXPECTED_SIGNS:
        return _EXPECTED_SIGNS[(regime, "any", metric)]
    return 0


def expected_sign_matrix(
    *,
    regimes: Sequence[TickRegime] | None = None,
    books: Sequence[BookLiq] = ("liquid", "less_liquid"),
    metrics: Sequence[MqMetric] | None = None,
) -> dict[str, Any]:
    """Serialize deck prediction tables as a nested dict + flat rows."""
    regs = list(regimes) if regimes is not None else [
        "large_abs_reduction",
        "small_abs_reduction",
        "large_abs_increase",
        "small_abs_increase",
        "rel_tick_up",
        "rel_tick_down",
    ]
    mets = list(metrics) if metrics is not None else list(MQ_METRICS)
    rows: list[dict[str, Any]] = []
    nested: dict[str, dict[str, dict[str, int]]] = {}
    for r in regs:
        nested[r] = {}
        for b in books:
            nested[r][b] = {}
            for m in mets:
                s = expected_sign(r, m, book=b)
                nested[r][b][m] = s
                rows.append({"regime": r, "book": b, "metric": m, "sign": s})
    return {
        "source": "Rindi et al. MMCV#3 2014 slides pp.20–29",
        "sign_convention": (
            "spreads: +1=tighten; depth/volume: +1=increase; "
            "0=ambiguous/out-of-scope/welfare"
        ),
        "kill_metrics": ["welfare"],
        "matrix": nested,
        "rows": rows,
    }


def venue_tick(
    venue: str,
    *,
    prices: NDArray[np.float64] | None = None,
    catalog_tick: float | None = None,
    known_ticks: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Resolve absolute tick τ: inferred from prices, else catalog/known.

    ``instruments.price_scale`` often returns 1e8 without decimals — prefer
    ``infer_tick`` on TOB/trade prices. Optional ``known_ticks`` overrides.
    """
    v = str(venue).strip().lower()
    known = known_ticks or {}
    inferred = float("nan")
    if prices is not None:
        inferred = float(infer_tick(np.asarray(prices, dtype=np.float64)))
    tau = float("nan")
    source = "missing"
    if v in known and np.isfinite(known[v]) and known[v] > 0:
        tau = float(known[v])
        source = "known"
    elif np.isfinite(inferred) and inferred > 0:
        tau = inferred
        source = "inferred"
    elif catalog_tick is not None and np.isfinite(catalog_tick) and catalog_tick > 0:
        # Reject absurd micro-ticks from 1e8 scale defaults
        if catalog_tick >= 1e-6:
            tau = float(catalog_tick)
            source = "catalog"
    return {
        "venue": v,
        "tau": tau,
        "inferred": inferred,
        "catalog_tick": catalog_tick,
        "source": source,
    }


def relative_tick(
    tau: float | NDArray[np.float64],
    mid: float | NDArray[np.float64],
    *,
    as_bps: bool = False,
) -> NDArray[np.float64] | float:
    """Relative tick τ/mid (fraction) or 1e4·τ/mid in bps when ``as_bps``.

    Cross-link: mmip ``tick.rel_tick_bps`` is the bps form as a *descriptor*.
    This book uses the same definition for panel/prediction tests only.
    """
    t = np.asarray(tau, dtype=np.float64)
    m = np.asarray(mid, dtype=np.float64)
    out = np.full(np.broadcast(t, m).shape, np.nan, dtype=np.float64)
    # broadcast manually
    t2, m2 = np.broadcast_arrays(t, m)
    out = np.full(t2.shape, np.nan, dtype=np.float64)
    ok = np.isfinite(t2) & np.isfinite(m2) & (m2 > 0) & (t2 > 0)
    scale = 1e4 if as_bps else 1.0
    out[ok] = scale * t2[ok] / m2[ok]
    if out.shape == ():
        return float(out)
    return out


def mq_vector(
    *,
    bid: NDArray[np.float64] | None = None,
    ask: NDArray[np.float64] | None = None,
    bid_sz: NDArray[np.float64] | None = None,
    ask_sz: NDArray[np.float64] | None = None,
    mid: NDArray[np.float64] | None = None,
    tau: float | None = None,
    trade_qty: NDArray[np.float64] | None = None,
    trade_px: NDArray[np.float64] | None = None,
) -> dict[str, float]:
    """Market-quality summary: quoted/rel spread, BBO depth, volume proxies."""
    out: dict[str, float] = {
        "quoted_spread_bps": float("nan"),
        "relative_spread": float("nan"),  # (ask-bid)/mid
        "spread_ticks": float("nan"),
        "bbo_depth": float("nan"),
        "total_depth": float("nan"),  # L0-only: = bbo_depth unless cum supplied
        "volume": float("nan"),
        "notional": float("nan"),
        "n_quotes": 0,
        "n_trades": 0,
        "mid": float("nan"),
        "rel_tick": float("nan"),
        "rel_tick_bps": float("nan"),
    }
    if bid is not None and ask is not None:
        b = np.asarray(bid, dtype=np.float64)
        a = np.asarray(ask, dtype=np.float64)
        m = mid_price(b, a) if mid is None else np.asarray(mid, dtype=np.float64)
        qs = quoted_spread_bps(b, a, mid=m)
        rel = (a - b) / m
        ok = np.isfinite(qs) & np.isfinite(m) & (m > 0)
        out["n_quotes"] = int(ok.sum())
        if ok.any():
            out["quoted_spread_bps"] = float(np.nanmedian(qs[ok]))
            out["relative_spread"] = float(np.nanmedian(rel[ok]))
            out["mid"] = float(np.nanmedian(m[ok]))
        if tau is not None and np.isfinite(tau) and tau > 0 and ok.any():
            ticks = (a[ok] - b[ok]) / float(tau)
            out["spread_ticks"] = float(np.nanmedian(ticks))
            rt = relative_tick(float(tau), out["mid"], as_bps=False)
            out["rel_tick"] = float(rt)
            out["rel_tick_bps"] = float(relative_tick(float(tau), out["mid"], as_bps=True))
        if bid_sz is not None and ask_sz is not None:
            bs = np.asarray(bid_sz, dtype=np.float64)
            az = np.asarray(ask_sz, dtype=np.float64)
            depth = bs + az
            dok = ok & np.isfinite(depth)
            if dok.any():
                out["bbo_depth"] = float(np.nanmedian(depth[dok]))
                out["total_depth"] = out["bbo_depth"]
    if trade_qty is not None:
        q = np.asarray(trade_qty, dtype=np.float64)
        q = q[np.isfinite(q) & (q > 0)]
        out["n_trades"] = int(q.size)
        out["volume"] = float(q.sum()) if q.size else float("nan")
        if trade_px is not None and q.size:
            px = np.asarray(trade_px, dtype=np.float64)
            # align lengths cautiously
            n = min(q.size, np.asarray(trade_px, dtype=np.float64).size)
            if n > 0:
                px = px[:n]
                qq = np.asarray(trade_qty, dtype=np.float64)
                qq = qq[np.isfinite(qq) & (qq > 0)][:n]
                px = px[np.isfinite(px)][: qq.size]
                if px.size == qq.size and px.size:
                    out["notional"] = float((px * qq).sum())
    return out


def tick_constrained(
    spread_ticks: float | NDArray[np.float64],
    *,
    max_ticks: float = 2.0,
) -> NDArray[np.bool_] | bool:
    """True when quoted spread ≤ ``max_ticks`` (undercutting channel active zone)."""
    s = np.asarray(spread_ticks, dtype=np.float64)
    out = np.isfinite(s) & (s > 0) & (s <= float(max_ticks))
    if out.shape == ():
        return bool(out)
    return out


def spread_in_ticks(
    bid: NDArray[np.float64],
    ask: NDArray[np.float64],
    tau: float,
) -> NDArray[np.float64]:
    """(ask − bid) / τ."""
    b = np.asarray(bid, dtype=np.float64)
    a = np.asarray(ask, dtype=np.float64)
    out = np.full_like(b, np.nan, dtype=np.float64)
    if not (np.isfinite(tau) and tau > 0):
        return out
    ok = np.isfinite(b) & np.isfinite(a) & (a >= b)
    out[ok] = (a[ok] - b[ok]) / float(tau)
    return out


def frac_one_tick(
    spread_ticks: NDArray[np.float64],
    *,
    tol: float = 0.05,
) -> float:
    """Share of quotes with spread ≈ 1 tick. Cross-link mmip ``tick.frac_one_tick``."""
    s = np.asarray(spread_ticks, dtype=np.float64)
    s = s[np.isfinite(s)]
    if s.size == 0:
        return float("nan")
    return float(np.mean(np.abs(s - 1.0) <= tol))


def spread_leeway(spread_ticks: NDArray[np.float64]) -> float:
    """Mean (spread_ticks − 1). Cross-link mmip ``tick.spread_leeway``."""
    s = np.asarray(spread_ticks, dtype=np.float64)
    s = s[np.isfinite(s)]
    if s.size == 0:
        return float("nan")
    return float(np.mean(s - 1.0))


def liquid_book_classifier(
    rows: Sequence[dict[str, Any]],
    *,
    by: Literal["quoted_spread_bps", "bbo_depth", "volume", "trade_intensity"] = "quoted_spread_bps",
    n_terciles: int = 3,
) -> list[dict[str, Any]]:
    """Assign liquid / mid / less_liquid terciles across panel rows (UTC-day).

    Low spread / high depth / high volume ⇒ liquid. Returns copies with
    ``liq_tercile`` ∈ {0,1,2} and ``book_liq`` ∈ {liquid, mid, less_liquid}.
    """
    vals = []
    for i, r in enumerate(rows):
        v = r.get(by, np.nan)
        try:
            fv = float(v) if v is not None else float("nan")
        except (TypeError, ValueError):
            fv = float("nan")
        vals.append((i, fv))
    finite = [(i, v) for i, v in vals if np.isfinite(v)]
    out = [dict(r) for r in rows]
    for r in out:
        r["liq_tercile"] = None
        r["book_liq"] = "unknown"
    if len(finite) < n_terciles:
        return out
    # sort ascending
    finite.sort(key=lambda x: x[1])
    # for spread: low = liquid; for depth/volume: high = liquid
    invert = by in ("bbo_depth", "volume", "trade_intensity")
    n = len(finite)
    for rank, (i, _) in enumerate(finite):
        # tercile 0 = lowest values
        t = min(n_terciles - 1, int(rank * n_terciles / n))
        if invert:
            # high value → liquid → map high tercile index to liquid
            book = ("less_liquid", "mid", "liquid")[t] if n_terciles == 3 else f"t{t}"
            liq_t = t
        else:
            book = ("liquid", "mid", "less_liquid")[t] if n_terciles == 3 else f"t{t}"
            liq_t = n_terciles - 1 - t
        out[i]["liq_tercile"] = int(liq_t)
        out[i]["book_liq"] = book
    return out


def undercutting_proxy(
    mid: NDArray[np.float64],
    bid: NDArray[np.float64],
    ask: NDArray[np.float64],
    tau: float,
    *,
    max_improve_ticks: float = 1.5,
) -> dict[str, float]:
    """Proxy undercutting rate: fraction of TOB updates that tighten BBO by ≤N ticks.

    L0-only: detect ask↓ or bid↑ by ~1 tick while mid moves little.
    """
    m = np.asarray(mid, dtype=np.float64)
    b = np.asarray(bid, dtype=np.float64)
    a = np.asarray(ask, dtype=np.float64)
    if m.size < 3 or not (np.isfinite(tau) and tau > 0):
        return {"n": 0, "undercut_rate": float("nan"), "tighten_rate": float("nan")}
    db = np.diff(b)
    da = np.diff(a)
    # tighten: bid up or ask down
    improve_bid = db > 0.5 * tau
    improve_ask = da < -0.5 * tau
    improve = improve_bid | improve_ask
    # magnitude in ticks
    mag = np.where(improve_bid, db / tau, np.where(improve_ask, -da / tau, np.nan))
    under = improve & np.isfinite(mag) & (mag <= max_improve_ticks)
    n = int(improve.size)
    return {
        "n": n,
        "tighten_rate": float(np.mean(improve)) if n else float("nan"),
        "undercut_rate": float(np.mean(under)) if n else float("nan"),
        "mean_improve_ticks": float(np.nanmean(mag[improve])) if improve.any() else float("nan"),
    }


def grid_pressure_feature(
    mid: NDArray[np.float64],
    tau: float,
    *,
    ref_mid: float | None = None,
) -> dict[str, float]:
    """Grid pressure from relative-tick drift without venue τ change (deck p.28).

    ``pressure = τ/mid_t − τ/mid_0`` (signed). Large |pressure| ⇒ relative grid
    bite changes as price moves.
    """
    m = np.asarray(mid, dtype=np.float64)
    m = m[np.isfinite(m) & (m > 0)]
    if m.size < 2 or not (np.isfinite(tau) and tau > 0):
        return {"pressure_mean": float("nan"), "pressure_std": float("nan"), "rel_tick_range": float("nan")}
    m0 = float(ref_mid) if ref_mid is not None and np.isfinite(ref_mid) else float(m[0])
    rt = tau / m
    rt0 = tau / m0
    pressure = rt - rt0
    return {
        "pressure_mean": float(np.mean(pressure)),
        "pressure_std": float(np.std(pressure)),
        "rel_tick_range": float(np.nanmax(rt) - np.nanmin(rt)),
        "rel_tick_start": float(rt0),
        "rel_tick_end": float(rt[-1]),
        "mid_start": m0,
        "mid_end": float(m[-1]),
    }


def cross_venue_tau_gap(
    venue_taus: dict[str, float],
    *,
    mid_by_venue: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Same-coin absolute and relative tick gaps across venues."""
    items = [(v, float(t)) for v, t in venue_taus.items() if np.isfinite(t) and t > 0]
    out: dict[str, Any] = {"venues": [v for v, _ in items], "pairs": []}
    if len(items) < 2:
        return out
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            va, ta = items[i]
            vb, tb = items[j]
            row: dict[str, Any] = {
                "a": va,
                "b": vb,
                "tau_a": ta,
                "tau_b": tb,
                "tau_gap": ta - tb,
                "tau_gap_abs": abs(ta - tb),
                "tau_ratio": ta / tb if tb > 0 else float("nan"),
            }
            if mid_by_venue:
                ma = mid_by_venue.get(va)
                mb = mid_by_venue.get(vb)
                if ma and mb and ma > 0 and mb > 0:
                    rta, rtb = ta / ma, tb / mb
                    row["rel_tick_a"] = rta
                    row["rel_tick_b"] = rtb
                    row["rel_tick_gap"] = rta - rtb
            out["pairs"].append(row)
    gaps = [p["tau_gap_abs"] for p in out["pairs"]]
    out["max_abs_tau_gap"] = float(max(gaps)) if gaps else float("nan")
    return out


def fama_macbeth_slope(
    panels: Sequence[dict[str, Any]],
    *,
    y_key: str,
    x_key: str = "rel_tick",
    group_key: str = "day",
) -> dict[str, Any]:
    """Crude FM: cross-section OLS slope each group, then mean slope ± t.

    ``panels`` rows need ``group_key``, ``x_key``, ``y_key``. No controls —
    Pass-1 scaffold; Pass-2 adds vol/OFI via caller.
    """
    groups: dict[Any, list[dict[str, Any]]] = {}
    for r in panels:
        g = r.get(group_key)
        if g is None:
            continue
        groups.setdefault(g, []).append(r)
    slopes: list[float] = []
    n_cs: list[int] = []
    for g, rows in sorted(groups.items(), key=lambda kv: str(kv[0])):
        xs, ys = [], []
        for r in rows:
            try:
                x = float(r[x_key])
                y = float(r[y_key])
            except (KeyError, TypeError, ValueError):
                continue
            if np.isfinite(x) and np.isfinite(y):
                xs.append(x)
                ys.append(y)
        if len(xs) < 3:
            continue
        x_arr = np.asarray(xs, dtype=np.float64)
        y_arr = np.asarray(ys, dtype=np.float64)
        x_c = x_arr - x_arr.mean()
        y_c = y_arr - y_arr.mean()
        den = float((x_c * x_c).sum())
        if den <= 0:
            continue
        slopes.append(float((x_c * y_c).sum() / den))
        n_cs.append(len(xs))
    if not slopes:
        return {
            "y": y_key,
            "x": x_key,
            "n_groups": 0,
            "mean_slope": float("nan"),
            "se": float("nan"),
            "t": float("nan"),
            "slopes": [],
        }
    s = np.asarray(slopes, dtype=np.float64)
    mean = float(s.mean())
    se = float(s.std(ddof=1) / np.sqrt(s.size)) if s.size > 1 else float("nan")
    t = mean / se if np.isfinite(se) and se > 0 else float("nan")
    return {
        "y": y_key,
        "x": x_key,
        "n_groups": int(s.size),
        "mean_cs_n": float(np.mean(n_cs)),
        "mean_slope": mean,
        "se": se,
        "t": t,
        "slopes": [float(x) for x in s],
    }


def sign_scorecard(
    observed_signs: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Compare observed Δ signs to ``expected_sign`` cells.

    Each row: ``regime``, ``metric``, ``book``, ``obs_sign`` ∈ {−1,0,+1}.
    """
    hits = misses = skips = 0
    detail = []
    for r in observed_signs:
        exp = expected_sign(r["regime"], r["metric"], book=r.get("book", "any"))
        obs = int(r.get("obs_sign", 0))
        if exp == 0 or r.get("metric") == "welfare":
            skips += 1
            match = None
        elif obs == 0:
            skips += 1
            match = None
        else:
            match = obs == exp
            if match:
                hits += 1
            else:
                misses += 1
        detail.append({**r, "expected": exp, "match": match})
    n = hits + misses
    return {
        "hits": hits,
        "misses": misses,
        "skips": skips,
        "hit_rate": float(hits / n) if n else float("nan"),
        "detail": detail,
    }


def panel_hour_buckets(
    ts_ns: NDArray[np.float64],
    values: dict[str, NDArray[np.float64]],
) -> list[dict[str, Any]]:
    """Aggregate arrays into UTC-hour rows for FM-style panels."""
    t = np.asarray(ts_ns, dtype=np.int64)
    if t.size == 0:
        return []
    hours = t // 3_600_000_000_000
    out = []
    for h in np.unique(hours):
        m = hours == h
        row: dict[str, Any] = {"hour_id": int(h), "n": int(m.sum())}
        for k, arr in values.items():
            a = np.asarray(arr)
            if a.shape[0] != t.shape[0]:
                continue
            sub = a[m]
            sub = sub[np.isfinite(sub.astype(np.float64))] if sub.dtype != object else sub
            try:
                row[k] = float(np.nanmedian(np.asarray(sub, dtype=np.float64)))
            except (TypeError, ValueError):
                row[k] = float("nan")
        out.append(row)
    return out


def fm_ci_from_slopes(
    slopes: Sequence[float],
    *,
    alpha: float = 0.05,
) -> dict[str, float]:
    """Normal approx CI for mean FM slope from cross-section slope list."""
    s = np.asarray(list(slopes), dtype=np.float64)
    s = s[np.isfinite(s)]
    if s.size == 0:
        return {"mean": float("nan"), "se": float("nan"), "lo": float("nan"), "hi": float("nan"), "n": 0}
    mean = float(s.mean())
    se = float(s.std(ddof=1) / np.sqrt(s.size)) if s.size > 1 else float("nan")
    # z≈1.96 for 95%; fall back to mean±nan when n=1
    from math import erfc  # noqa: F401 — keep stdlib only

    z = 1.959963984540054  # Φ^{-1}(0.975)
    if not np.isfinite(se):
        return {"mean": mean, "se": se, "lo": float("nan"), "hi": float("nan"), "n": int(s.size)}
    half = z * se
    return {"mean": mean, "se": se, "lo": mean - half, "hi": mean + half, "n": int(s.size)}


def markout_by_rel_tick_quartile(
    rows: Sequence[dict[str, Any]],
    *,
    rel_key: str = "rel_tick",
    markout_key: str = "markout_1s_bps",
) -> dict[str, Any]:
    """Mean markout by relative-tick quartile (desk Pass-2 info lens)."""
    pts = []
    for r in rows:
        try:
            x = float(r.get(rel_key))
            y = float(r.get(markout_key))
        except (TypeError, ValueError):
            continue
        if np.isfinite(x) and np.isfinite(y):
            pts.append((x, y))
    if len(pts) < 4:
        return {"n": len(pts), "quartiles": [], "means": [], "ns": []}
    xs = np.asarray([p[0] for p in pts], dtype=np.float64)
    ys = np.asarray([p[1] for p in pts], dtype=np.float64)
    qs = np.quantile(xs, [0.0, 0.25, 0.5, 0.75, 1.0])
    means, ns, labels = [], [], []
    for i in range(4):
        lo, hi = qs[i], qs[i + 1]
        if i < 3:
            m = (xs >= lo) & (xs < hi)
        else:
            m = (xs >= lo) & (xs <= hi)
        means.append(float(np.mean(ys[m])) if m.any() else float("nan"))
        ns.append(int(m.sum()))
        labels.append(f"Q{i+1} [{lo:.3g},{hi:.3g}]")
    return {
        "n": int(xs.size),
        "edges": [float(x) for x in qs],
        "quartiles": labels,
        "means": means,
        "ns": ns,
    }


def constraint_flip_windows(
    ts_ns: NDArray[np.int64],
    constrained: NDArray[np.bool_],
    *,
    intensity: NDArray[np.float64] | None = None,
    ofi: NDArray[np.float64] | None = None,
    pre_n: int = 20,
    post_n: int = 20,
) -> dict[str, Any]:
    """Event study around constrained→unconstrained (relax) flips.

    Returns flip timestamps + mean intensity/OFI in pre/post windows (index units).
    """
    t = np.asarray(ts_ns, dtype=np.int64)
    c = np.asarray(constrained, dtype=bool)
    if t.size < pre_n + post_n + 2:
        return {"n_flips": 0, "relax_ts": [], "tighten_ts": [], "relax_intensity_delta": float("nan")}
    # flip: True→False = relax; False→True = tighten
    prev = c[:-1]
    nxt = c[1:]
    relax_i = np.where(prev & ~nxt)[0] + 1
    tight_i = np.where(~prev & nxt)[0] + 1

    def _win_mean(arr: NDArray[np.float64] | None, idx: NDArray[np.int64], side: str) -> float:
        if arr is None or idx.size == 0:
            return float("nan")
        a = np.asarray(arr, dtype=np.float64)
        vals = []
        for i in idx:
            if side == "pre":
                lo, hi = max(0, int(i) - pre_n), int(i)
            else:
                lo, hi = int(i), min(a.size, int(i) + post_n)
            chunk = a[lo:hi]
            chunk = chunk[np.isfinite(chunk)]
            if chunk.size:
                vals.append(float(np.mean(chunk)))
        return float(np.mean(vals)) if vals else float("nan")

    pre_i = _win_mean(intensity, relax_i, "pre")
    post_i = _win_mean(intensity, relax_i, "post")
    pre_o = _win_mean(ofi, relax_i, "pre")
    post_o = _win_mean(ofi, relax_i, "post")
    return {
        "n_flips": int(relax_i.size + tight_i.size),
        "n_relax": int(relax_i.size),
        "n_tighten": int(tight_i.size),
        "relax_ts": [int(t[i]) for i in relax_i[:200]],
        "tighten_ts": [int(t[i]) for i in tight_i[:200]],
        "relax_intensity_pre": pre_i,
        "relax_intensity_post": post_i,
        "relax_intensity_delta": (post_i - pre_i) if np.isfinite(pre_i) and np.isfinite(post_i) else float("nan"),
        "relax_ofi_pre": pre_o,
        "relax_ofi_post": post_o,
        "relax_ofi_delta": (post_o - pre_o) if np.isfinite(pre_o) and np.isfinite(post_o) else float("nan"),
    }


def tercile_interaction(
    rows: Sequence[dict[str, Any]],
    *,
    x_key: str = "rel_tick",
    y_key: str = "quoted_spread_bps",
    book_key: str = "book_liq",
) -> dict[str, Any]:
    """Mean y by (book_liq × x tercile) for interaction plots."""
    classified = liquid_book_classifier(list(rows), by=y_key if y_key == "quoted_spread_bps" else "quoted_spread_bps")
    # re-classify on spread; keep x for binning within book
    xs_all = []
    for r in classified:
        try:
            xs_all.append(float(r.get(x_key)))
        except (TypeError, ValueError):
            xs_all.append(float("nan"))
    finite_x = [x for x in xs_all if np.isfinite(x)]
    if len(finite_x) < 3:
        return {"cells": [], "n": 0}
    edges = np.quantile(finite_x, [0.0, 1 / 3, 2 / 3, 1.0])
    cells = []
    for book in ("liquid", "mid", "less_liquid"):
        for ti in range(3):
            ys = []
            for r, x in zip(classified, xs_all):
                if r.get(book_key) != book or not np.isfinite(x):
                    continue
                if ti < 2:
                    ok = edges[ti] <= x < edges[ti + 1]
                else:
                    ok = edges[ti] <= x <= edges[ti + 1]
                if not ok:
                    continue
                try:
                    y = float(r.get(y_key))
                except (TypeError, ValueError):
                    continue
                if np.isfinite(y):
                    ys.append(y)
            cells.append(
                {
                    "book": book,
                    "x_tercile": ti,
                    "x_lo": float(edges[ti]),
                    "x_hi": float(edges[ti + 1]),
                    "mean_y": float(np.mean(ys)) if ys else float("nan"),
                    "n": len(ys),
                }
            )
    return {"cells": cells, "n": sum(c["n"] for c in cells), "x_edges": [float(e) for e in edges], "y_key": y_key, "x_key": x_key}
