#!/usr/bin/env python3
"""Appendix A toolbox: extractable MM features from Market Microstructure in Practice.

Implements (priority order):
  A.5  Harris tick / tick-constrained spread analytics
  A.6  Optimal schedule toys on real intraday volume curves
  A.12 Signature / Epps (corr vs sampling freq)
  A.11 Hawkes-style self-excitation (descriptive + simple parametric)
  A.1  FEI formal link to Ch.1 (extend, do not redo)

Reusable feature functions are module-level so MM research can import them.

Data: collector TOB + warehouse trade/marks (no ClickHouse MCP). Paper only.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq

BOOK_ROOT = Path(__file__).resolve().parents[1]
ROOT = BOOK_ROOT.parents[2]  # repo root (mmip → books → research → repo)
OUT_DIR = BOOK_ROOT / "out" / "appendix_quant"
STARTARB = Path("/home/dev/srv/ares-startarb")
DEFAULT_TOB = Path("/home/dev/srv/ares-startarb/results/xarb_md/tob")
CH01_OUT = BOOK_ROOT / "out" / "ch01_fragmentation"

# ---------------------------------------------------------------------------
# Reusable feature library (lift into production research)
# ---------------------------------------------------------------------------


def entropy(q: np.ndarray) -> float:
    """Shannon entropy H = -∑ q log q (nats). 0·log0 := 0."""
    q = np.asarray(q, dtype=np.float64)
    q = q[q > 0]
    if q.size == 0:
        return 0.0
    return float(-np.sum(q * np.log(q)))


def fei(q: np.ndarray) -> float:
    """FEI = H(q) / log(N_active) ∈ [0,1]. App.A.1 / Ch.1."""
    q = np.asarray(q, dtype=np.float64)
    s = q.sum()
    if s <= 0:
        return 0.0
    q = q / s
    n = int((q > 0).sum())
    if n <= 1:
        return 0.0
    return entropy(q) / math.log(n)


def infer_tick(prices: np.ndarray) -> float:
    """Min positive price increment from observed BBO prices."""
    p = np.unique(np.round(np.asarray(prices, dtype=np.float64), 10))
    if p.size < 2:
        return float("nan")
    d = np.diff(np.sort(p))
    d = d[d > 1e-12]
    return float(np.min(d)) if d.size else float("nan")


def harris_tick_features(
    bid: np.ndarray,
    ask: np.ndarray,
    tick: float | None = None,
) -> dict[str, Any]:
    """A.5 Harris tick analytics (descriptive; no full MLE gamma).

    Observed spread in ticks ε = (A−B)/τ. Spread leeway = ε−1.
    Frac one-tick = P(ε ≤ 1+ε_tol). Relative tick = τ/mid.

    Label: **descriptive metric** / quoting regime — not a tradable signal.
    """
    bid = np.asarray(bid, dtype=np.float64)
    ask = np.asarray(ask, dtype=np.float64)
    mid = 0.5 * (bid + ask)
    spread = ask - bid
    ok = np.isfinite(spread) & np.isfinite(mid) & (mid > 0) & (spread >= 0)
    bid, ask, mid, spread = bid[ok], ask[ok], mid[ok], spread[ok]
    if tick is None or not np.isfinite(tick) or tick <= 0:
        tick = infer_tick(np.concatenate([bid, ask]))
    if not np.isfinite(tick) or tick <= 0:
        return {"tick": float("nan"), "n": 0}

    eps = spread / tick  # spread in ticks
    leeway = eps - 1.0
    one = eps <= 1.0 + 1e-9
    rel_tick_bps = 1e4 * tick / mid
    spread_bps = 1e4 * spread / mid
    # Harris intuition: when ε≈1, discrete spread ≫ continuous lower bound
    # Proxy continuous floor ≈ max(0, mean(eps)-bias); here report excess over 1 tick
    excess_bps = np.where(one, 0.0, (eps - 1.0) * rel_tick_bps)

    return {
        "tick": float(tick),
        "n": int(spread.size),
        "mean_spread_ticks": float(np.mean(eps)),
        "median_spread_ticks": float(np.median(eps)),
        "frac_one_tick": float(np.mean(one)),
        "mean_leeway": float(np.mean(leeway)),
        "p90_leeway": float(np.percentile(leeway, 90)),
        "mean_spread_bps": float(np.mean(spread_bps)),
        "median_spread_bps": float(np.median(spread_bps)),
        "mean_rel_tick_bps": float(np.mean(rel_tick_bps)),
        "mean_excess_over_1tick_bps": float(np.mean(excess_bps)),
        "spread_ticks_hist": {
            "edges": [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 8.5, 20.5],
            "counts": np.histogram(eps, bins=[0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 8.5, 20.5])[0].tolist(),
        },
    }


def schedule_expectation_min(
    V: np.ndarray,
    sigma: np.ndarray,
    v_star: float,
    gamma: float = 1.0,
) -> np.ndarray:
    """A.6 Prop.1 — expectation-min schedule (impact only).

    v_n ∝ V_n / σ_n^{1/γ}, ∑ v = v*.
    Units: V = market volume per slice; σ = local currency (or mid-units) vol.
    Label: **execution heuristic** (toy; κ/γ not calibrated on fills).
    """
    V = np.asarray(V, dtype=np.float64)
    sigma = np.asarray(sigma, dtype=np.float64)
    sigma = np.maximum(sigma, 1e-12)
    w = V / (sigma ** (1.0 / gamma))
    s = w.sum()
    if s <= 0 or v_star == 0:
        return np.zeros_like(w)
    return (w / s) * float(v_star)


def schedule_uniform(n: int, v_star: float) -> np.ndarray:
    """A.6 Prop.2 — constant market context → uniform schedule."""
    if n <= 0:
        return np.array([], dtype=np.float64)
    return np.full(n, float(v_star) / n, dtype=np.float64)


def schedule_mean_variance_linear(
    V: np.ndarray,
    sigma: np.ndarray,
    v_star: float,
    kappa: float = 1.0,
    lam: float = 1e-4,
    n_iter: int = 500,
    lr: float = 0.02,
) -> np.ndarray:
    """A.6 mean–variance toy with linear impact (γ=1).

    Cost ≈ κ ∑ σ_n (x_n−x_{n+1})² / V_n + λ ∑ x_n² σ_n²,
    x_0=v*, x_N=0, v_n = x_n − x_{n+1}.

    Projected gradient on remaining inventory (nonincreasing, ≥0).
    Label: **execution heuristic** — λ/κ are research knobs, not production TCA.
    """
    V = np.asarray(V, dtype=np.float64)
    sigma = np.asarray(sigma, dtype=np.float64)
    N = len(V)
    if N == 0:
        return np.array([], dtype=np.float64)
    V = np.maximum(V, 1e-12)
    sigma = np.maximum(sigma, 1e-12)
    x = np.linspace(float(v_star), 0.0, N + 1)
    for _ in range(n_iter):
        v = x[:-1] - x[1:]
        grad = np.zeros(N - 1)
        for n in range(1, N):
            # v_i = x_i - x_{i+1}
            # ∂C_imp/∂x_n = −2κ σ_{n-1} v_{n-1}/V_{n-1} + 2κ σ_n v_n/V_n
            term = -2.0 * kappa * sigma[n - 1] * v[n - 1] / V[n - 1]
            term += 2.0 * kappa * sigma[n] * v[n] / V[n]
            sig_r = sigma[min(n, N - 1)]
            term += 2.0 * lam * x[n] * (sig_r**2)
            grad[n - 1] = term
        x[1:N] -= lr * grad
        x[0] = float(v_star)
        x[N] = 0.0
        x[1:N] = np.clip(x[1:N], 0.0, abs(float(v_star)))
        # enforce nonincreasing remaining inventory
        for i in range(1, N):
            if x[i] > x[i - 1]:
                x[i] = x[i - 1]
            if x[i] < x[i + 1]:
                x[i] = x[i + 1]
    return x[:-1] - x[1:]


def volume_curve_shares(
    ts_ns: np.ndarray,
    notional: np.ndarray,
    n_slots: int = 24,
) -> dict[str, Any]:
    """Intraday volume share curve (feeds A.6 V_n). UTC hour slots by default."""
    ts_ns = np.asarray(ts_ns, dtype=np.int64)
    notional = np.asarray(notional, dtype=np.float64)
    sec = ts_ns // 1_000_000_000
    slot = ((sec % 86_400) * n_slots) // 86_400
    vol = np.zeros(n_slots, dtype=np.float64)
    for i in range(n_slots):
        m = slot == i
        vol[i] = float(notional[m].sum()) if m.any() else 0.0
    total = float(vol.sum())
    share = vol / total if total > 0 else vol
    return {
        "n_slots": n_slots,
        "notional": vol.tolist(),
        "share": share.tolist(),
        "total_notional": total,
        "fei_slot_share": fei(share),
        "peak_slot": int(np.argmax(share)) if total > 0 else -1,
    }


def realized_variance_signature(
    ts_ns: np.ndarray,
    mid: np.ndarray,
    deltas_s: list[float],
) -> list[dict[str, Any]]:
    """A.12.1 signature plot: ˆVR(Δ) = ∑ r_Δ² vs sampling step Δ."""
    ts_ns = np.asarray(ts_ns, dtype=np.int64)
    mid = np.asarray(mid, dtype=np.float64)
    order = np.argsort(ts_ns)
    ts_ns, mid = ts_ns[order], mid[order]
    logp = np.log(np.maximum(mid, 1e-12))
    t0, t1 = int(ts_ns[0]), int(ts_ns[-1])
    out = []
    for dt in deltas_s:
        step = int(dt * 1e9)
        if step <= 0:
            continue
        grid = np.arange(t0, t1 + 1, step)
        if grid.size < 3:
            continue
        idx = np.searchsorted(ts_ns, grid, side="right") - 1
        idx = np.clip(idx, 0, len(logp) - 1)
        x = logp[idx]
        # drop duplicate stamps from flat idx
        r = np.diff(x)
        vr = float(np.sum(r * r))
        out.append({"delta_s": float(dt), "n_returns": int(r.size), "realized_var": vr})
    return out


def epps_correlation(
    ts_a: np.ndarray,
    mid_a: np.ndarray,
    ts_b: np.ndarray,
    mid_b: np.ndarray,
    deltas_s: list[float],
) -> list[dict[str, Any]]:
    """A.12.2 Epps: corr(r_a, r_b) vs sampling frequency (synchronous last-tick).

    Honesty: last-tick sync induces asynchronicity bias at fine Δ — that *is* Epps.
    Label: **descriptive metric** for xasset / xvenue hedge horizon choice.
    """
    ts_a = np.asarray(ts_a, dtype=np.int64)
    ts_b = np.asarray(ts_b, dtype=np.int64)
    mid_a = np.asarray(mid_a, dtype=np.float64)
    mid_b = np.asarray(mid_b, dtype=np.float64)
    oa, ob = np.argsort(ts_a), np.argsort(ts_b)
    ts_a, mid_a = ts_a[oa], mid_a[oa]
    ts_b, mid_b = ts_b[ob], mid_b[ob]
    t0 = max(int(ts_a[0]), int(ts_b[0]))
    t1 = min(int(ts_a[-1]), int(ts_b[-1]))
    rows = []
    for dt in deltas_s:
        step = int(dt * 1e9)
        if step <= 0:
            continue
        grid = np.arange(t0, t1 + 1, step)
        if grid.size < 5:
            continue
        ia = np.clip(np.searchsorted(ts_a, grid, side="right") - 1, 0, len(mid_a) - 1)
        ib = np.clip(np.searchsorted(ts_b, grid, side="right") - 1, 0, len(mid_b) - 1)
        ra = np.diff(np.log(np.maximum(mid_a[ia], 1e-12)))
        rb = np.diff(np.log(np.maximum(mid_b[ib], 1e-12)))
        if ra.std() < 1e-15 or rb.std() < 1e-15:
            corr = float("nan")
        else:
            corr = float(np.corrcoef(ra, rb)[0, 1])
        rows.append(
            {
                "delta_s": float(dt),
                "n_returns": int(ra.size),
                "corr": corr,
                "cov": float(np.mean(ra * rb)),
            }
        )
    return rows


def hawkes_descriptive(
    event_ts_ns: np.ndarray,
    bin_s: float = 1.0,
    max_lag: int = 30,
) -> dict[str, Any]:
    """A.11 descriptive self-excitation on event counts (honest limits).

    - Bin count process N_t
    - ACF of counts (clustering proxy)
    - Simple exponential Hawkes MoM: fit α,β on conditional intensity
      via OLS of λ̂_t on exponentially decayed event kernel (1-param grid).

    Not a full MLE Hawkes; branching ratio R=α/β is **indicative**.
    Label: **descriptive metric** → intensity gate research, not live α.
    """
    event_ts_ns = np.asarray(event_ts_ns, dtype=np.int64)
    event_ts_ns = np.sort(event_ts_ns[np.isfinite(event_ts_ns)])
    if event_ts_ns.size < 10:
        return {"n_events": int(event_ts_ns.size), "ok": False}
    t0, t1 = int(event_ts_ns[0]), int(event_ts_ns[-1])
    step = max(int(bin_s * 1e9), 1)
    n_bins = max(int((t1 - t0) // step) + 1, 2)
    counts = np.zeros(n_bins, dtype=np.float64)
    idx = ((event_ts_ns - t0) // step).astype(np.int64)
    idx = idx[(idx >= 0) & (idx < n_bins)]
    np.add.at(counts, idx, 1.0)
    # ACF
    c = counts - counts.mean()
    var = float(np.dot(c, c))
    acf = []
    for lag in range(max_lag + 1):
        if lag == 0:
            acf.append(1.0)
        elif var <= 0:
            acf.append(float("nan"))
        else:
            acf.append(float(np.dot(c[lag:], c[:-lag]) / var))
    # Method-of-moments style: search β, set excitation = ∑ α e^{-β Δ} ≈ α * kernel
    # Regress counts[t] on K[t] where K updates: K <- K*e^{-β Δ} + counts[t-1]
    best = {"rss": float("inf")}
    dt = float(bin_s)
    mean_rate = float(counts.mean() / dt)  # per second
    for beta in (0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0):
        decay = math.exp(-beta * dt)
        K = 0.0
        xs, ys = [], []
        for n in counts:
            xs.append(K)
            ys.append(n / dt)  # intensity proxy
            K = K * decay + n
        X = np.column_stack([np.ones(len(xs)), np.asarray(xs)])
        y = np.asarray(ys)
        try:
            coef, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
        except np.linalg.LinAlgError:
            continue
        lam0, alpha = float(coef[0]), float(coef[1])
        if alpha < 0 or lam0 < 0:
            continue
        pred = X @ coef
        rss = float(np.sum((y - pred) ** 2))
        R = alpha / beta if beta > 0 else float("nan")
        if rss < best["rss"] and R < 1.0:
            best = {
                "rss": rss,
                "lambda0": lam0,
                "alpha": alpha,
                "beta": beta,
                "branching_ratio": R,
                "E_lambda": lam0 / (1.0 - R) if R < 1 else float("nan"),
            }
    # Inter-event CV (Poisson → CV≈1; clustered → CV>1)
    durs = np.diff(event_ts_ns.astype(np.float64)) / 1e9
    cv = float(durs.std() / durs.mean()) if durs.mean() > 0 else float("nan")
    return {
        "ok": True,
        "n_events": int(event_ts_ns.size),
        "bin_s": float(bin_s),
        "duration_s": float((t1 - t0) / 1e9),
        "mean_count_per_bin": float(counts.mean()),
        "mean_rate_per_s": mean_rate,
        "acf": acf,
        "interarrival_cv": cv,
        "hawkes_mom": best if "lambda0" in best else None,
        "note": "MoM/OLS Hawkes is indicative; not MLE. Use as clustering diagnostic.",
    }


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------


def _ensure_startarb() -> None:
    src = str(STARTARB / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from startarb.env import ensure_env

    ensure_env()


def _base_symbol(sym: str) -> str:
    s = str(sym or "").strip().upper()
    if "/" in s:
        s = s.split("/", 1)[0]
    for suf in ("USDT", "USDC", "-PERPETUAL"):
        if s.endswith(suf):
            s = s[: -len(suf)]
    return s


def load_collector_tob(tob_root: Path, day: str | None, symbol: str):
    import pandas as pd

    if day:
        day_dirs = [tob_root / day]
    else:
        day_dirs = sorted(p for p in tob_root.iterdir() if p.is_dir())
        day_dirs = [day_dirs[-1]] if day_dirs else []
    frames = []
    for d in day_dirs:
        for f in sorted(d.glob("tob_*.parquet")):
            frames.append(pq.read_table(f).to_pandas())
    if not frames:
        raise FileNotFoundError(f"No TOB under {tob_root}")
    df = pd.concat(frames, ignore_index=True)
    want = symbol.upper()
    df = df[df["symbol"].map(_base_symbol) == want].copy()
    df["venue"] = df["venue"].astype(str).str.lower()
    df["mid"] = 0.5 * (df["bid"] + df["ask"])
    df["spread"] = df["ask"] - df["bid"]
    return df


# ---------------------------------------------------------------------------
# Experiment runners
# ---------------------------------------------------------------------------


def run_harris(df) -> dict[str, Any]:
    by_venue = {}
    for v, g in df.groupby("venue"):
        by_venue[str(v)] = harris_tick_features(g["bid"].values, g["ask"].values)
    return {"venues": by_venue, "n_rows": int(len(df))}


def run_schedule(days: list[str], symbol: str = "ETH") -> dict[str, Any]:
    _ensure_startarb()
    from startarb.data.trades import load_trade_tape

    curves = []
    for day in days:
        tape = load_trade_tape("hyperliquid", symbol, days=[day], max_files=12)
        notional = tape.price * tape.qty_coin
        curve = volume_curve_shares(tape.ts_ns, notional, n_slots=24)
        # local vol proxy: hour-of-day std of log returns on mid≈trade price
        h = ((tape.ts_ns // 1_000_000_000) % 86_400) // 3600
        px = tape.price.astype(np.float64)
        sigma = np.zeros(24)
        for i in range(24):
            m = h == i
            if m.sum() < 5:
                sigma[i] = np.nan
                continue
            lp = np.log(np.maximum(px[m], 1e-12))
            # per-trade increments; scale to hour-ish
            r = np.diff(lp)
            sigma[i] = float(np.std(r) * math.sqrt(max(m.sum(), 1))) if r.size else np.nan
        # fill nan with median
        med = float(np.nanmedian(sigma)) if np.isfinite(np.nanmedian(sigma)) else 1.0
        sigma = np.where(np.isfinite(sigma) & (sigma > 0), sigma, med)
        V = np.asarray(curve["share"], dtype=np.float64)  # relative market volume
        v_star = 1.0  # unit parent order
        v_exp = schedule_expectation_min(V, sigma, v_star, gamma=1.0)
        v_uni = schedule_uniform(24, v_star)
        v_mv = schedule_mean_variance_linear(V, sigma, v_star, kappa=1.0, lam=5e-3)
        curves.append(
            {
                "day": day,
                "n_trades": int(len(tape.ts_ns)),
                "volume_curve": curve,
                "sigma_proxy": sigma.tolist(),
                "sched_expectation_min": v_exp.tolist(),
                "sched_uniform": v_uni.tolist(),
                "sched_mean_var": v_mv.tolist(),
                "participation_peak_exp": float(v_exp.max()),
                "participation_peak_mv": float(v_mv.max()),
                "l1_exp_vs_uniform": float(np.abs(v_exp - v_uni).sum()),
                "l1_mv_vs_uniform": float(np.abs(v_mv - v_uni).sum()),
            }
        )
    # average schedule across days
    shares = np.mean([c["volume_curve"]["share"] for c in curves], axis=0)
    sig = np.mean([c["sigma_proxy"] for c in curves], axis=0)
    return {
        "days": curves,
        "mean_share": shares.tolist(),
        "mean_sigma": sig.tolist(),
        "mean_sched_exp": schedule_expectation_min(shares, sig, 1.0).tolist(),
        "mean_sched_mv": schedule_mean_variance_linear(shares, sig, 1.0, lam=5e-3).tolist(),
        "mean_l1_exp_vs_uni": float(
            np.mean([c["l1_exp_vs_uniform"] for c in curves])
        ),
    }


def run_epps_hawkes(days: list[str]) -> dict[str, Any]:
    _ensure_startarb()
    from startarb.data.marks import load_mark_bars
    from startarb.data.trades import load_trade_tape
    from startarb.data.bbo_stream import load_quote_stream

    deltas = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600]
    # Cross-asset Epps on Deribit marks (synchronous 1m → resample)
    def _mark_ts_px(bars: dict) -> tuple[np.ndarray, np.ndarray]:
        # load_mark_bars: close + time (datetime64[ns]) — no ts_ns key
        t = np.asarray(bars["time"], dtype="datetime64[ns]").astype(np.int64)
        px = np.asarray(bars["close"], dtype=np.float64)
        return t, px

    eth = load_mark_bars("deribit", "ETH-PERPETUAL", days=days, bar_ns=int(60e9))
    btc = load_mark_bars("deribit", "BTC-PERPETUAL", days=days, bar_ns=int(60e9))
    ts_e, px_e = _mark_ts_px(eth)
    ts_b, px_b = _mark_ts_px(btc)
    epps_xasset = epps_correlation(ts_e, px_e, ts_b, px_b, [60, 120, 300, 600, 900, 1800])
    sig_eth = realized_variance_signature(ts_e, px_e, [60, 120, 300, 600, 900, 1800])

    # Cross-venue Epps: HL ETH mid vs Deribit ETH mark (overlap day)
    day0 = days[-1]
    q = load_quote_stream(
        "hyperliquid",
        "ETH",
        [day0],
        table="l2_rebuild",
        max_files=10,
        quotes_per_minute=60,
    )
    eth1 = load_mark_bars("deribit", "ETH-PERPETUAL", days=[day0], bar_ns=int(60e9))
    ts1, px1 = _mark_ts_px(eth1)
    epps_xvenue = epps_correlation(
        q.ts_ns,
        0.5 * (q.bid + q.ask),
        ts1,
        px1,
        [5, 10, 15, 30, 60, 120, 300, 600],
    )

    # Hawkes on HL trade events
    hawkes_days = []
    for day in days:
        tape = load_trade_tape("hyperliquid", "ETH", days=[day], max_files=12)
        h = hawkes_descriptive(tape.ts_ns, bin_s=1.0, max_lag=40)
        h["day"] = day
        hawkes_days.append(h)

    return {
        "epps_xasset_eth_btc_deribit": epps_xasset,
        "signature_eth_deribit": sig_eth,
        "epps_xvenue_hl_deribit_eth": epps_xvenue,
        "epps_xvenue_day": day0,
        "hawkes_hl_eth": hawkes_days,
    }


def run_fei_link() -> dict[str, Any]:
    """Link A.1 FEI formalisms to Ch.1 artifacts — do not redo full Ch.1."""
    eth = CH01_OUT / "exp_ch01_eth_summary.json"
    trade = CH01_OUT / "exp_ch01_trade_fei_eth_summary.json"
    out: dict[str, Any] = {
        "book_table_1_2": {
            "50/50": fei(np.array([0.5, 0.5])),
            "70/20/10": fei(np.array([0.7, 0.2, 0.1])),
            "70/20/5/5": fei(np.array([0.7, 0.2, 0.05, 0.05])),
            "25/25/25/25": fei(np.array([0.25, 0.25, 0.25, 0.25])),
        },
        "ch01_path": str(eth),
    }
    if eth.exists():
        s = json.loads(eth.read_text())
        sm = s.get("summary", {})
        out["ch01_fei_size"] = sm.get("fei_size")
        out["ch01_fei_updates"] = sm.get("fei_updates")
        out["ch01_size_share"] = sm.get("size_share")
        out["honesty"] = (
            "Ch.1 FEI is TOB-size / update-count; A.1 definition is market-share entropy. "
            "Trade-notional spatial FEI still Hold (see Ch.1 iterate)."
        )
    if trade.exists():
        t = json.loads(trade.read_text())
        out["ch01_trade_hourly_fei_mean"] = t.get("mean_fei_hourly")
        out["ch01_trade_note"] = t.get("note")
    return out


def write_plots(payload: dict[str, Any]) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = []

    # Harris: frac one-tick by venue
    h = payload["harris"]["venues"]
    fig, ax = plt.subplots(figsize=(7, 3.5))
    venues = list(h.keys())
    fracs = [h[v].get("frac_one_tick", float("nan")) for v in venues]
    means = [h[v].get("mean_spread_ticks", float("nan")) for v in venues]
    x = np.arange(len(venues))
    ax.bar(x - 0.2, fracs, width=0.4, label="frac 1-tick")
    ax.bar(x + 0.2, [m / 5 for m in means], width=0.4, label="mean ε/5 (scale)")
    ax.set_xticks(x)
    ax.set_xticklabels(venues, rotation=15)
    ax.set_ylabel("fraction / scaled ε")
    ax.set_title("A.5 Harris tick regime (collector TOB)")
    ax.legend()
    ax.set_ylim(0, 1.05)
    p = OUT_DIR / "fig_harris_tick.png"
    fig.tight_layout()
    fig.savefig(p, dpi=120)
    plt.close(fig)
    paths.append(str(p))

    # Schedule
    sch = payload["schedule"]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    hrs = np.arange(24)
    ax.plot(hrs, sch["mean_share"], "k-", lw=2, label="mean vol share V_n")
    ax.plot(hrs, sch["mean_sched_exp"], label="E-min schedule (A.6 Prop.1)")
    ax.plot(hrs, sch["mean_sched_mv"], label="mean–var toy (λ>0)")
    ax.axhline(1 / 24, color="gray", ls="--", lw=1, label="uniform")
    ax.set_xlabel("UTC hour")
    ax.set_ylabel("share of parent / market")
    ax.set_title("A.6 schedule toys on HL ETH volume curve")
    ax.legend(fontsize=8)
    p = OUT_DIR / "fig_schedule.png"
    fig.tight_layout()
    fig.savefig(p, dpi=120)
    plt.close(fig)
    paths.append(str(p))

    # Epps xasset
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ep = payload["epps_hawkes"]["epps_xasset_eth_btc_deribit"]
    ax.plot([r["delta_s"] / 60 for r in ep], [r["corr"] for r in ep], "o-")
    ax.set_xlabel("Δt (minutes)")
    ax.set_ylabel("corr(r_ETH, r_BTC)")
    ax.set_title("A.12 Epps — Deribit ETH vs BTC marks")
    p = OUT_DIR / "fig_epps_xasset.png"
    fig.tight_layout()
    fig.savefig(p, dpi=120)
    plt.close(fig)
    paths.append(str(p))

    # Epps xvenue
    fig, ax = plt.subplots(figsize=(7, 3.5))
    epv = payload["epps_hawkes"]["epps_xvenue_hl_deribit_eth"]
    ax.plot([r["delta_s"] for r in epv], [r["corr"] for r in epv], "s-", color="C1")
    ax.set_xlabel("Δt (seconds)")
    ax.set_ylabel("corr(HL mid, Deribit mark)")
    ax.set_title(f"A.12 Epps xvenue ETH ({payload['epps_hawkes']['epps_xvenue_day']})")
    ax.set_xscale("log")
    p = OUT_DIR / "fig_epps_xvenue.png"
    fig.tight_layout()
    fig.savefig(p, dpi=120)
    plt.close(fig)
    paths.append(str(p))

    # Hawkes ACF
    fig, ax = plt.subplots(figsize=(7, 3.5))
    for hrow in payload["epps_hawkes"]["hawkes_hl_eth"]:
        if not hrow.get("ok"):
            continue
        ax.plot(hrow["acf"][:31], alpha=0.7, label=hrow["day"])
    ax.axhline(0, color="gray", lw=0.8)
    ax.set_xlabel("lag (1s bins)")
    ax.set_ylabel("ACF of trade counts")
    ax.set_title("A.11 trade-count ACF (clustering proxy)")
    ax.legend(fontsize=7)
    p = OUT_DIR / "fig_hawkes_acf.png"
    fig.tight_layout()
    fig.savefig(p, dpi=120)
    plt.close(fig)
    paths.append(str(p))

    return paths


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--tob-day", default="20260929")
    ap.add_argument(
        "--days",
        default="2026-09-14,2026-09-15,2026-09-16,2026-09-25,2026-09-26",
    )
    ap.add_argument("--skip-plots", action="store_true")
    args = ap.parse_args()
    days = [d.strip() for d in args.days.split(",") if d.strip()]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("loading collector TOB…")
    df = load_collector_tob(DEFAULT_TOB, args.tob_day, args.symbol)
    harris = run_harris(df)
    print("harris venues", list(harris["venues"].keys()))

    print("schedule on warehouse trades…")
    schedule = run_schedule(days, symbol=args.symbol)
    print("mean L1(exp vs uni)", schedule["mean_l1_exp_vs_uni"])

    print("epps + hawkes…")
    epps_hawkes = run_epps_hawkes(days)
    fei_link = run_fei_link()

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": args.symbol,
        "tob_day": args.tob_day,
        "warehouse_days": days,
        "harris": harris,
        "schedule": {
            k: v
            for k, v in schedule.items()
            if k != "days"
        },
        "schedule_days_summary": [
            {
                "day": c["day"],
                "n_trades": c["n_trades"],
                "peak_slot": c["volume_curve"]["peak_slot"],
                "fei_slot": c["volume_curve"]["fei_slot_share"],
                "l1_exp_vs_uniform": c["l1_exp_vs_uniform"],
                "l1_mv_vs_uniform": c["l1_mv_vs_uniform"],
                "participation_peak_exp": c["participation_peak_exp"],
                "participation_peak_mv": c["participation_peak_mv"],
            }
            for c in schedule["days"]
        ],
        "epps_hawkes": {
            "epps_xasset_eth_btc_deribit": epps_hawkes["epps_xasset_eth_btc_deribit"],
            "signature_eth_deribit": epps_hawkes["signature_eth_deribit"],
            "epps_xvenue_hl_deribit_eth": epps_hawkes["epps_xvenue_hl_deribit_eth"],
            "epps_xvenue_day": epps_hawkes["epps_xvenue_day"],
            "hawkes_hl_eth": [
                {
                    "day": h["day"],
                    "n_events": h.get("n_events"),
                    "interarrival_cv": h.get("interarrival_cv"),
                    "mean_rate_per_s": h.get("mean_rate_per_s"),
                    "acf_lag1": (h.get("acf") or [None, None])[1],
                    "acf_lag5": (h.get("acf") or [None] * 6)[5],
                    "hawkes_mom": h.get("hawkes_mom"),
                }
                for h in epps_hawkes["hawkes_hl_eth"]
            ],
            # keep full ACF for plots
            "_hawkes_full": epps_hawkes["hawkes_hl_eth"],
        },
        "fei_link": fei_link,
    }

    # plots need full hawkes
    plot_payload = {
        "harris": harris,
        "schedule": schedule,
        "epps_hawkes": {
            **{k: v for k, v in epps_hawkes.items() if k != "hawkes_hl_eth"},
            "hawkes_hl_eth": epps_hawkes["hawkes_hl_eth"],
        },
    }
    if not args.skip_plots:
        paths = write_plots(plot_payload)
        payload["figures"] = paths

    # strip heavy for json
    payload["epps_hawkes"].pop("_hawkes_full", None)
    out_json = OUT_DIR / "exp_appa_summary.json"
    out_json.write_text(json.dumps(payload, indent=2, default=str))
    print("wrote", out_json)

    # short markdown report stub (full EXP_REPORT lives in chapter folder)
    lines = [
        "# App.A toolbox — experiment summary",
        "",
        f"- Created: {payload['created_at']}",
        f"- Symbol: {args.symbol}",
        f"- TOB day: {args.tob_day}",
        f"- Warehouse days: {', '.join(days)}",
        "",
        "## Harris (A.5)",
    ]
    for v, m in harris["venues"].items():
        lines.append(
            f"- **{v}**: frac_1tick={m.get('frac_one_tick', float('nan')):.3f}, "
            f"mean_ε={m.get('mean_spread_ticks', float('nan')):.2f}, "
            f"tick={m.get('tick')}"
        )
    lines += [
        "",
        "## Schedule (A.6)",
        f"- Mean L1(|exp−uniform|)={schedule['mean_l1_exp_vs_uni']:.4f}",
        "",
        "## Epps / Hawkes",
    ]
    if epps_hawkes["epps_xasset_eth_btc_deribit"]:
        e0 = epps_hawkes["epps_xasset_eth_btc_deribit"][0]
        e1 = epps_hawkes["epps_xasset_eth_btc_deribit"][-1]
        lines.append(
            f"- Xasset corr @ {e0['delta_s']}s={e0['corr']:.3f} → "
            f"@ {e1['delta_s']}s={e1['corr']:.3f}"
        )
    for h in payload["epps_hawkes"]["hawkes_hl_eth"]:
        mom = h.get("hawkes_mom") or {}
        lines.append(
            f"- Hawkes {h['day']}: CV={h.get('interarrival_cv')}, "
            f"acf1={h.get('acf_lag1')}, R̂={mom.get('branching_ratio')}"
        )
    (OUT_DIR / "exp_appa_REPORT.md").write_text("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
