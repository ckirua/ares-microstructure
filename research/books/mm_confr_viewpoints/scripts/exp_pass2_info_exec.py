#!/usr/bin/env python3
"""Pass-2 info/exec deep dig: tick_constraint + rel_tick_panel.

1) HL constraint-relax / undercut-burst event stacks joining OFI, trade
   intensity, short-horizon markout — with event-bootstrap bands.
2) Markout by rel_tick quartile *within HL only* and *within Deribit only*
   (kills x-venue confound on the info lens).

Writes NEW figs under out/tick_constraint/figs/ and out/rel_tick_panel/figs/
(does not delete existing required figs). ClickHouse MCP banned. No git.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
SCRIPTS = BOOK / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from _data import ensure_env, load_day_trades, load_tob_any  # noqa: E402
from research.lib.markout import trade_markouts  # noqa: E402
from research.lib.spreads import quoted_spread_bps  # noqa: E402
from research.lib.stats import bootstrap_ci, spearman_r  # noqa: E402
from research.lib.ticksize import (  # noqa: E402
    markout_by_rel_tick_quartile,
    relative_tick,
    spread_in_ticks,
    tick_constrained,
    undercutting_proxy,
    venue_tick,
)

SYMBOL = "ETH"
KNOWN_TAU = {"hyperliquid": 0.1, "deribit": 0.05}
BAR_NS = 60_000_000_000
HOUR_NS = 3_600_000_000_000
HALF = 10
N_BOOT = 400
SEED = 17

TC_OUT = BOOK / "out" / "tick_constraint"
TC_FIGS = TC_OUT / "figs"
RTP_OUT = BOOK / "out" / "rel_tick_panel"
RTP_FIGS = RTP_OUT / "figs"


def is_synth(source: str | None) -> bool:
    s = str(source or "").lower()
    return "trade_synth" in s or "synth" in s


def days_from_panel() -> list[str]:
    p = BOOK / "out" / "pass1" / "panel.json"
    if p.is_file():
        return list(json.loads(p.read_text()).get("days") or [])
    flat = BOOK / "out" / "rel_tick_panel" / "panel_flat.json"
    if flat.is_file():
        rows = json.loads(flat.read_text()).get("rows") or []
        return sorted({r["day"] for r in rows})
    return ["2026-09-26", "2026-09-27", "2026-09-30"]


def resolve_tau(venue: str, tob: dict[str, Any]) -> float:
    known = {venue: KNOWN_TAU[venue]} if venue in KNOWN_TAU else None
    prices = np.concatenate(
        [np.asarray(tob["bid"], dtype=np.float64), np.asarray(tob["ask"], dtype=np.float64)]
    )
    return float(venue_tick(venue, prices=prices, known_ticks=known)["tau"])


def per_trade_markout_bps(
    trade_ts: np.ndarray,
    side: np.ndarray,
    mid_ts: np.ndarray,
    mid: np.ndarray,
    *,
    horizon_ms: int = 1000,
) -> np.ndarray:
    """Signed per-trade markout (bps); same convention as research.lib.markout."""
    tt = np.asarray(trade_ts, dtype=np.int64)
    s = np.asarray(side, dtype=np.float64)
    s = np.where(s == 0, np.nan, s)
    mt = np.asarray(mid_ts, dtype=np.int64)
    mv = np.asarray(mid, dtype=np.float64)
    i0 = np.searchsorted(mt, tt, side="right") - 1
    valid0 = (i0 >= 0) & (i0 < mt.size)
    mid0 = np.full(tt.size, np.nan)
    mid0[valid0] = mv[i0[valid0]]
    h_ns = int(horizon_ms) * 1_000_000
    i1 = np.searchsorted(mt, tt + h_ns, side="right") - 1
    valid = valid0 & (i1 > i0) & (i1 < mt.size) & np.isfinite(s) & (mid0 > 0)
    mid1 = np.full(tt.size, np.nan)
    mid1[valid] = mv[i1[valid]]
    mo = np.full(tt.size, np.nan)
    ok = valid & np.isfinite(mid1)
    mo[ok] = s[ok] * 1e4 * (mid1[ok] - mid0[ok]) / mid0[ok]
    return mo


def minute_joint(
    tob: dict[str, Any],
    tau: float,
    trade_ts: np.ndarray,
    trade_mo: np.ndarray,
) -> dict[str, np.ndarray]:
    """1m bars: constraint, undercut, OFI, intensity, markout, qs, rel_tick."""
    ts = np.asarray(tob["ts"], dtype=np.int64)
    bid = np.asarray(tob["bid"], dtype=np.float64)
    ask = np.asarray(tob["ask"], dtype=np.float64)
    mid = np.asarray(tob["mid"], dtype=np.float64)
    bs = np.asarray(tob["bid_sz"], dtype=np.float64)
    az = np.asarray(tob["ask_sz"], dtype=np.float64)
    st = spread_in_ticks(bid, ask, tau)
    cons = tick_constrained(st, max_ticks=2.0)
    if not isinstance(cons, np.ndarray):
        cons = np.array([cons], dtype=bool)
    qs = quoted_spread_bps(bid, ask, mid=mid)
    rt = np.asarray(relative_tick(tau, mid, as_bps=False), dtype=np.float64)

    db = np.diff(bid, prepend=bid[0])
    da = np.diff(ask, prepend=ask[0])
    dbs = np.diff(bs, prepend=0.0)
    daz = np.diff(az, prepend=0.0)
    bs_prev = np.roll(bs, 1)
    az_prev = np.roll(az, 1)
    bs_prev[0], az_prev[0] = bs[0], az[0]
    ofi_e = np.where(db > 0, bs, np.where(db == 0, dbs, -bs_prev))
    ofi_e = ofi_e + np.where(da < 0, -az, np.where(da == 0, -daz, az_prev))
    ofi_e[0] = 0.0

    t0, t1 = int(ts.min()), int(ts.max())
    grid = np.arange(t0, t1 + 1, BAR_NS, dtype=np.int64)
    if grid.size < 3:
        return {}
    idx = np.searchsorted(ts, grid, side="left")
    tr_idx = np.searchsorted(trade_ts, grid, side="left")
    n = grid.size - 1
    out = {
        "t_mid": 0.5 * (grid[:-1] + grid[1:]),
        "frac_c": np.full(n, np.nan),
        "undercut_rate": np.full(n, np.nan),
        "ofi_sum": np.full(n, np.nan),
        "intensity": np.full(n, np.nan),
        "markout_1s_bps": np.full(n, np.nan),
        "med_qs_bps": np.full(n, np.nan),
        "med_rel_tick": np.full(n, np.nan),
        "n_quotes": np.zeros(n, dtype=np.int64),
        "n_trades": np.zeros(n, dtype=np.int64),
    }
    dt_s = BAR_NS / 1e9
    for i in range(n):
        lo, hi = int(idx[i]), int(idx[i + 1])
        tlo, thi = int(tr_idx[i]), int(tr_idx[i + 1])
        if hi > lo:
            sl = slice(lo, hi)
            out["n_quotes"][i] = hi - lo
            out["frac_c"][i] = float(np.mean(cons[sl]))
            out["ofi_sum"][i] = float(ofi_e[sl].sum())
            out["med_qs_bps"][i] = float(np.nanmedian(qs[sl]))
            out["med_rel_tick"][i] = float(np.nanmedian(rt[sl]))
            if hi - lo >= 3:
                uc = undercutting_proxy(mid[sl], bid[sl], ask[sl], tau)
                out["undercut_rate"][i] = uc.get("undercut_rate", np.nan)
        if thi > tlo:
            out["n_trades"][i] = thi - tlo
            out["intensity"][i] = (thi - tlo) / dt_s
            sub_mo = trade_mo[tlo:thi]
            sub_mo = sub_mo[np.isfinite(sub_mo)]
            if sub_mo.size:
                out["markout_1s_bps"][i] = float(np.mean(sub_mo))
    return out


def quote_relax_bars(ts: np.ndarray, cons: np.ndarray, t_mid: np.ndarray, *, min_gap: int = 3) -> list[int]:
    c = np.asarray(cons, dtype=bool)
    if c.size < 3 or t_mid.size < 3:
        return []
    d = np.diff(c.astype(np.int8))
    relax_ts = ts[1:][d == -1]
    if relax_ts.size == 0:
        return []
    bars = np.searchsorted(t_mid, relax_ts, side="left")
    bars = bars[(bars >= 0) & (bars < t_mid.size)]
    out: list[int] = []
    last = -10**9
    for b in bars.tolist():
        if b - last >= min_gap:
            out.append(int(b))
            last = b
    return out


def undercut_burst_bars(undercut: np.ndarray, *, q: float = 0.85, min_gap: int = 5) -> list[int]:
    u = np.asarray(undercut, dtype=np.float64)
    finite = u[np.isfinite(u)]
    if finite.size < 30:
        return []
    thr = float(np.nanquantile(finite, q))
    thr = max(thr, 0.08)
    out: list[int] = []
    last = -10**9
    above = False
    for i, v in enumerate(u):
        if not np.isfinite(v):
            continue
        if v >= thr and not above and i - last >= min_gap:
            out.append(i)
            last = i
            above = True
        elif v < thr * 0.7:
            above = False
    return out


def stack_events(
    series: dict[str, np.ndarray],
    events: list[int],
    keys: tuple[str, ...],
    *,
    half: int = HALF,
) -> dict[str, Any]:
    lags = np.arange(-half, half + 1)
    mats: dict[str, list[np.ndarray]] = {k: [] for k in keys}
    for e in events:
        if e < half or e + half >= series["frac_c"].size:
            continue
        for k in keys:
            mats[k].append(np.asarray(series[k][e - half : e + half + 1], dtype=np.float64))
    rng = np.random.default_rng(SEED)
    out: dict[str, Any] = {"n_events": 0, "lags": lags.tolist(), "half": half}
    for k, rows in mats.items():
        if not rows:
            out[k] = {
                "mean": [float("nan")] * lags.size,
                "lo": [float("nan")] * lags.size,
                "hi": [float("nan")] * lags.size,
                "n": 0,
            }
            continue
        m = np.vstack(rows)
        n_ev = int(m.shape[0])
        out["n_events"] = n_ev
        mean = np.nanmean(m, axis=0)
        if n_ev >= 5:
            boots = np.empty((N_BOOT, lags.size), dtype=np.float64)
            for b in range(N_BOOT):
                idx = rng.integers(0, n_ev, size=n_ev)
                boots[b] = np.nanmean(m[idx], axis=0)
            lo, hi = np.nanquantile(boots, [0.025, 0.975], axis=0)
        else:
            lo = hi = np.full(lags.size, np.nan)
        # post−pre effect (lags >0 vs <0)
        pre = mean[lags < 0]
        post = mean[lags > 0]
        delta = float(np.nanmean(post) - np.nanmean(pre)) if pre.size and post.size else float("nan")
        out[k] = {
            "mean": [float(x) for x in mean],
            "lo": [float(x) for x in lo],
            "hi": [float(x) for x in hi],
            "n": n_ev,
            "delta_post_minus_pre": delta,
        }
    return out


def plot_stack(stack: dict[str, Any], title: str, path: Path, panels: list[tuple[str, str]]) -> str:
    fig, axes = plt.subplots(2, 2, figsize=(10, 7))
    lags = np.asarray(stack.get("lags") or list(range(-HALF, HALF + 1)))
    n_ev = int(stack.get("n_events") or 0)
    for ax, (key, ylab) in zip(axes.ravel(), panels):
        blk = stack.get(key) or {}
        mean = np.asarray(blk.get("mean") or [], dtype=np.float64)
        lo = np.asarray(blk.get("lo") or [], dtype=np.float64)
        hi = np.asarray(blk.get("hi") or [], dtype=np.float64)
        if mean.size == lags.size and np.isfinite(mean).any():
            ax.plot(lags, mean, color="#1f4e6b", lw=2, label="mean")
            if lo.size == lags.size and np.isfinite(lo).any():
                ax.fill_between(lags, lo, hi, color="#1f4e6b", alpha=0.22, label="boot 95%")
            dlt = blk.get("delta_post_minus_pre")
            ax.set_title(f"{ylab}  Δpost−pre={dlt:.3g}" if np.isfinite(dlt or np.nan) else ylab, fontsize=10)
        else:
            ax.text(0.5, 0.5, "no events", ha="center", va="center", transform=ax.transAxes)
            ax.set_title(ylab)
        ax.axvline(0, color="crimson", ls="--", lw=1)
        ax.axhline(0, color="gray", ls=":", lw=0.7, alpha=0.6)
        ax.set_xlabel("minutes from event")
        ax.grid(True, alpha=0.25)
    fig.suptitle(f"{title}  (n_events≈{n_ev})", y=1.01)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return path.name


def hour_rows_with_markout(
    venue: str,
    day: str,
    tob: dict[str, Any],
    tau: float,
    trade_ts: np.ndarray,
    trade_mo: np.ndarray,
) -> list[dict[str, Any]]:
    ts = np.asarray(tob["ts"], dtype=np.int64)
    mid = np.asarray(tob["mid"], dtype=np.float64)
    bid = np.asarray(tob["bid"], dtype=np.float64)
    ask = np.asarray(tob["ask"], dtype=np.float64)
    qs = quoted_spread_bps(bid, ask, mid=mid)
    rt = np.asarray(relative_tick(tau, mid, as_bps=False), dtype=np.float64)
    hours = ts // HOUR_NS
    tr_hours = trade_ts // HOUR_NS
    rows = []
    for h in np.unique(hours):
        m = hours == h
        if int(m.sum()) < 20:
            continue
        tm = tr_hours == h
        mo_sub = trade_mo[tm]
        mo_sub = mo_sub[np.isfinite(mo_sub)]
        if mo_sub.size < 5:
            continue
        rows.append(
            {
                "venue": venue,
                "day": day,
                "hour_id": int(h),
                "n_quotes": int(m.sum()),
                "n_trades": int(tm.sum()),
                "rel_tick": float(np.nanmedian(rt[m])),
                "rel_tick_bps": float(np.nanmedian(rt[m]) * 1e4),
                "quoted_spread_bps": float(np.nanmedian(qs[m])),
                "markout_1s_bps": float(np.mean(mo_sub)),
                "markout_1s_ci": bootstrap_ci(mo_sub, n_boot=200, seed=SEED),
            }
        )
    return rows


def quartile_effect(mq: dict[str, Any]) -> dict[str, Any]:
    means = mq.get("means") or []
    ns = mq.get("ns") or []
    if len(means) < 4:
        return {"q4_minus_q1": float("nan"), "spearman_proxy": float("nan")}
    q1, q4 = float(means[0]), float(means[3])
    return {
        "q4_minus_q1_bps": q4 - q1,
        "q1_mean_bps": q1,
        "q4_mean_bps": q4,
        "n_q1": int(ns[0]) if ns else 0,
        "n_q4": int(ns[3]) if len(ns) > 3 else 0,
    }


def plot_within_venue_quartiles(
    by_venue: dict[str, dict[str, Any]],
    hour_pts: dict[str, list[dict[str, Any]]],
) -> list[str]:
    produced = []
    # combined 1×2
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2), sharey=False)
    for ax, venue, color in zip(axes, ("hyperliquid", "deribit"), ("#1f4e6b", "#b07d4f")):
        mq = by_venue.get(venue) or {}
        means = mq.get("means") or []
        ns = mq.get("ns") or []
        labels = mq.get("quartiles") or [f"Q{i+1}" for i in range(4)]
        if means:
            x = np.arange(len(means))
            ax.bar(x, means, color=color, alpha=0.85)
            for i, (m, n) in enumerate(zip(means, ns)):
                ax.text(i, m, f"n={n}", ha="center", va="bottom", fontsize=8)
            ax.set_xticks(x)
            ax.set_xticklabels([f"Q{i+1}" for i in range(len(means))], fontsize=9)
            eff = quartile_effect(mq)
            pts = hour_pts.get(venue) or []
            xs = np.array([p["rel_tick"] for p in pts], dtype=np.float64)
            ys = np.array([p["markout_1s_bps"] for p in pts], dtype=np.float64)
            rho = spearman_r(xs, ys) if xs.size >= 3 else float("nan")
            ax.set_title(
                f"{venue}\nQ4−Q1={eff.get('q4_minus_q1_bps', float('nan')):.3g} bps · ρ={rho:.3g} · n_h={len(pts)}",
                fontsize=10,
            )
        else:
            ax.text(0.5, 0.5, "insufficient hours", ha="center", va="center", transform=ax.transAxes)
            ax.set_title(venue)
        ax.axhline(0, color="k", lw=0.6)
        ax.set_ylabel("mean markout 1s (bps)")
        ax.set_xlabel("rel_tick quartile (within venue)")
        ax.grid(True, axis="y", alpha=0.3)
    fig.suptitle("Markout by rel_tick quartile — within venue only (kills x-venue confound)", y=1.03)
    fig.tight_layout()
    p = RTP_FIGS / "fig_markout_reltick_q_within_venue.png"
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    produced.append(p.name)

    for venue, color in (("hyperliquid", "#1f4e6b"), ("deribit", "#b07d4f")):
        mq = by_venue.get(venue) or {}
        pts = hour_pts.get(venue) or []
        fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.8))
        ax = axes[0]
        means = mq.get("means") or []
        ns = mq.get("ns") or []
        if means:
            x = np.arange(len(means))
            ax.bar(x, means, color=color, alpha=0.9)
            for i, n in enumerate(ns):
                ax.text(i, means[i], f"n={n}", ha="center", va="bottom", fontsize=8)
            ax.set_xticks(x)
            ax.set_xticklabels([f"Q{i+1}" for i in range(len(means))])
        ax.axhline(0, color="k", lw=0.6)
        ax.set_ylabel("mean markout 1s (bps)")
        ax.set_title(f"{venue}: quartile means")
        ax.grid(True, axis="y", alpha=0.3)

        ax = axes[1]
        if pts:
            xs = np.array([p["rel_tick_bps"] for p in pts], dtype=np.float64)
            ys = np.array([p["markout_1s_bps"] for p in pts], dtype=np.float64)
            ax.scatter(xs, ys, s=28, color=color, alpha=0.75)
            rho = spearman_r(xs, ys)
            ax.set_title(f"hour scatter · Spearman ρ={rho:.3g}")
            ax.set_xlabel("rel_tick (bps)")
            ax.set_ylabel("markout 1s (bps)")
            ax.axhline(0, color="k", lw=0.5)
            ax.grid(True, alpha=0.3)
        else:
            ax.text(0.5, 0.5, "no hours", ha="center", va="center", transform=ax.transAxes)
        fig.suptitle(f"Within-{venue} info lens (hourly; τ fixed → mid-driven rel_tick)", y=1.03)
        fig.tight_layout()
        name = f"fig_markout_reltick_q_{'hl' if venue == 'hyperliquid' else 'deribit'}.png"
        path = RTP_FIGS / name
        fig.savefig(path, dpi=140, bbox_inches="tight")
        plt.close(fig)
        produced.append(path.name)
    return produced


def desk_gate_summary(
    relax: dict[str, Any],
    burst: dict[str, Any],
    hl_day_marks: list[float],
) -> dict[str, Any]:
    """Honest labels: risk monitor vs exec throttle vs tradable."""
    ofi_d = (relax.get("ofi_sum") or {}).get("delta_post_minus_pre", float("nan"))
    inten_d = (relax.get("intensity") or {}).get("delta_post_minus_pre", float("nan"))
    mo_d = (relax.get("markout_1s_bps") or {}).get("delta_post_minus_pre", float("nan"))
    uc_d = (burst.get("undercut_rate") or {}).get("delta_post_minus_pre", float("nan"))
    mo_burst = (burst.get("markout_1s_bps") or {}).get("delta_post_minus_pre", float("nan"))

    # exec throttle only if markout clearly worsens (positive adverse for maker)
    mark_worsens = np.isfinite(mo_d) and mo_d > 0.5
    flow_moves = (np.isfinite(ofi_d) and abs(ofi_d) > 0) or (np.isfinite(inten_d) and abs(inten_d) > 0.01)
    burst_mo_bad = np.isfinite(mo_burst) and mo_burst > 0.5

    if mark_worsens or burst_mo_bad:
        label = "exec_throttle_candidate"
        decision = "Hold"
        why = (
            "HL post-event markout Δ>0.5 bps on relax/burst — possible exec throttle, "
            "but need time-split + denser sample before Promote"
        )
    elif flow_moves or (np.isfinite(uc_d) and abs(uc_d) > 0.01):
        label = "risk_monitor"
        decision = "Hold"
        why = (
            "HL constraint/undercut events show flow or undercut response without "
            "clear markout deterioration — risk/fragility monitor, not tradable"
        )
    else:
        label = "constrained_quiet"
        decision = "Hold"
        why = "HL ~always constrained; event responses weak — monitor only"

    day_mo = float(np.nanmean(hl_day_marks)) if hl_day_marks else float("nan")
    return {
        "desk_label": label,
        "decision": decision,
        "tradable": False,
        "exec_throttle": label.startswith("exec_throttle"),
        "risk_monitor": label == "risk_monitor" or label.startswith("exec_throttle"),
        "why": why,
        "effects": {
            "relax_ofi_delta": ofi_d,
            "relax_intensity_delta": inten_d,
            "relax_markout_delta_bps": mo_d,
            "burst_undercut_delta": uc_d,
            "burst_markout_delta_bps": mo_burst,
            "hl_day_mean_markout_1s_bps": day_mo,
            "n_relax_events": int(relax.get("n_events") or 0),
            "n_burst_events": int(burst.get("n_events") or 0),
        },
    }


def run_hl_stacks(days: list[str]) -> dict[str, Any]:
    ensure_env()
    keys = ("ofi_sum", "intensity", "markout_1s_bps", "undercut_rate")
    panels = [
        ("ofi_sum", "OFI sum (1m)"),
        ("intensity", "trade intensity λ (1/s)"),
        ("markout_1s_bps", "markout 1s (bps)"),
        ("undercut_rate", "undercut rate"),
    ]
    relax_days: list[dict[str, Any]] = []
    burst_days: list[dict[str, Any]] = []
    # also collect raw event matrices across days for true event bootstrap
    relax_mats: dict[str, list[np.ndarray]] = {k: [] for k in keys}
    burst_mats: dict[str, list[np.ndarray]] = {k: [] for k in keys}
    day_marks: list[float] = []
    day_meta: list[dict[str, Any]] = []

    for day in days:
        print(f"HL dig {day}", flush=True)
        trades = load_day_trades("hyperliquid", SYMBOL, day, quiet=True)
        tape = trades["tape"]
        ts_tr = np.asarray(tape["ts"], dtype=np.int64)
        px = np.asarray(tape["px"], dtype=np.float64)
        side = np.asarray(tape["side"], dtype=np.float64)
        tob = load_tob_any("hyperliquid", SYMBOL, day)
        if is_synth(tob.get("source")):
            continue
        tau = resolve_tau("hyperliquid", tob)
        mo = per_trade_markout_bps(ts_tr, side, tob["ts"], tob["mid"], horizon_ms=1000)
        # day aggregate via lib for cross-check
        try:
            agg = trade_markouts(ts_tr, px, side, tob["ts"], tob["mid"], horizons_ms=(1000,))
            day_marks.append(float((agg.get("by_horizon") or {}).get("1000", {}).get("mean_bps", np.nan)))
        except Exception:
            sample = mo[np.isfinite(mo)]
            day_marks.append(float(np.mean(sample)) if sample.size else float("nan"))

        series = minute_joint(tob, tau, ts_tr, mo)
        if not series:
            continue
        st = spread_in_ticks(tob["bid"], tob["ask"], tau)
        cons = tick_constrained(st, max_ticks=2.0)
        if not isinstance(cons, np.ndarray):
            cons = np.zeros(tob["ts"].size, dtype=bool)
        relax_ev = quote_relax_bars(
            np.asarray(tob["ts"], dtype=np.int64),
            cons,
            series["t_mid"],
            min_gap=3,
        )
        burst_ev = undercut_burst_bars(series["undercut_rate"], q=0.85, min_gap=5)
        r_stack = stack_events(series, relax_ev, keys)
        b_stack = stack_events(series, burst_ev, keys)
        relax_days.append(r_stack)
        burst_days.append(b_stack)
        day_meta.append(
            {
                "day": day,
                "tau": tau,
                "n_relax": len(relax_ev),
                "n_burst": len(burst_ev),
                "frac_c": float(np.nanmean(series["frac_c"])),
                "undercut_med": float(np.nanmedian(series["undercut_rate"])),
                "day_markout_1s_bps": day_marks[-1],
                "relax_deltas": {k: (r_stack.get(k) or {}).get("delta_post_minus_pre") for k in keys},
                "burst_deltas": {k: (b_stack.get(k) or {}).get("delta_post_minus_pre") for k in keys},
            }
        )
        # raw mats for pooled event bootstrap
        half = HALF
        for e in relax_ev:
            if e < half or e + half >= series["frac_c"].size:
                continue
            for k in keys:
                relax_mats[k].append(np.asarray(series[k][e - half : e + half + 1], dtype=np.float64))
        for e in burst_ev:
            if e < half or e + half >= series["frac_c"].size:
                continue
            for k in keys:
                burst_mats[k].append(np.asarray(series[k][e - half : e + half + 1], dtype=np.float64))

    def _from_mats(mats: dict[str, list[np.ndarray]]) -> dict[str, Any]:
        lags = np.arange(-HALF, HALF + 1)
        out: dict[str, Any] = {"n_events": 0, "lags": lags.tolist(), "half": HALF}
        rng = np.random.default_rng(SEED)
        for k, rows in mats.items():
            if not rows:
                out[k] = {
                    "mean": [float("nan")] * lags.size,
                    "lo": [float("nan")] * lags.size,
                    "hi": [float("nan")] * lags.size,
                    "n": 0,
                    "delta_post_minus_pre": float("nan"),
                }
                continue
            m = np.vstack(rows)
            n_ev = int(m.shape[0])
            out["n_events"] = max(out["n_events"], n_ev)
            mean = np.nanmean(m, axis=0)
            boots = np.empty((N_BOOT, lags.size), dtype=np.float64)
            for b in range(N_BOOT):
                idx = rng.integers(0, n_ev, size=n_ev)
                boots[b] = np.nanmean(m[idx], axis=0)
            lo, hi = np.nanquantile(boots, [0.025, 0.975], axis=0)
            delta = float(np.nanmean(mean[lags > 0]) - np.nanmean(mean[lags < 0]))
            out[k] = {
                "mean": [float(x) for x in mean],
                "lo": [float(x) for x in lo],
                "hi": [float(x) for x in hi],
                "n": n_ev,
                "delta_post_minus_pre": delta,
            }
        return out

    relax_pool = _from_mats(relax_mats)
    burst_pool = _from_mats(burst_mats)
    gate = desk_gate_summary(relax_pool, burst_pool, day_marks)

    figs = []
    figs.append(
        plot_stack(
            relax_pool,
            "HL constraint-relax stacks (OFI / intensity / markout / undercut)",
            TC_FIGS / "fig_hl_relax_stack_ofi_intensity_markout.png",
            panels,
        )
    )
    figs.append(
        plot_stack(
            burst_pool,
            "HL undercut-burst stacks (OFI / intensity / markout / undercut)",
            TC_FIGS / "fig_hl_undercut_burst_stack.png",
            panels,
        )
    )

    # gate board fig
    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    eff = gate["effects"]
    labels = [
        "relax ΔOFI",
        "relax Δλ",
        "relax Δmo (bps)",
        "burst Δuc",
        "burst Δmo (bps)",
    ]
    vals = [
        eff["relax_ofi_delta"],
        eff["relax_intensity_delta"],
        eff["relax_markout_delta_bps"],
        eff["burst_undercut_delta"],
        eff["burst_markout_delta_bps"],
    ]
    # normalize OFI for display (sign only scale)
    display = []
    for lab, v in zip(labels, vals):
        if "OFI" in lab and np.isfinite(v):
            display.append(np.sign(v) * np.log1p(abs(v)))
        else:
            display.append(v if np.isfinite(v) else 0.0)
    colors = ["#8b1e1e" if gate["exec_throttle"] else "#2c5f7c"] * len(display)
    ax.barh(np.arange(len(labels)), display, color=colors)
    ax.set_yticks(np.arange(len(labels)))
    ax.set_yticklabels(labels)
    ax.axvline(0, color="k", lw=0.7)
    ax.set_title(
        f"HL desk gate: {gate['desk_label']} · decision={gate['decision']} · tradable={gate['tradable']}"
    )
    ax.set_xlabel("Δ post−pre (OFI shown as sign·log1p|Δ|)")
    fig.tight_layout()
    p = TC_FIGS / "fig_hl_info_exec_gate.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    figs.append(p.name)

    return {
        "days": days,
        "day_meta": day_meta,
        "relax_stack": relax_pool,
        "burst_stack": burst_pool,
        "gate": gate,
        "figs": figs,
    }


def run_within_venue_markout(days: list[str]) -> dict[str, Any]:
    ensure_env()
    hour_pts: dict[str, list[dict[str, Any]]] = {"hyperliquid": [], "deribit": []}
    for venue in ("hyperliquid", "deribit"):
        for day in days:
            print(f"within-venue markout {venue} {day}", flush=True)
            trades = load_day_trades(venue, SYMBOL, day, quiet=True)
            tape = trades["tape"]
            ts_tr = np.asarray(tape["ts"], dtype=np.int64)
            side = np.asarray(tape["side"], dtype=np.float64)
            tob = load_tob_any(venue, SYMBOL, day)
            if is_synth(tob.get("source")):
                continue
            tau = resolve_tau(venue, tob)
            mo = per_trade_markout_bps(ts_tr, side, tob["ts"], tob["mid"], horizon_ms=1000)
            rows = hour_rows_with_markout(venue, day, tob, tau, ts_tr, mo)
            hour_pts[venue].extend(rows)

    by_venue = {}
    effects = {}
    for venue, rows in hour_pts.items():
        mq = markout_by_rel_tick_quartile(rows, rel_key="rel_tick", markout_key="markout_1s_bps")
        xs = np.array([r["rel_tick"] for r in rows], dtype=np.float64)
        ys = np.array([r["markout_1s_bps"] for r in rows], dtype=np.float64)
        rho = spearman_r(xs, ys) if xs.size >= 3 else float("nan")
        # bootstrap ρ
        if xs.size >= 8:
            rng = np.random.default_rng(SEED + 9)
            boots = []
            n = xs.size
            for _ in range(N_BOOT):
                idx = rng.integers(0, n, size=n)
                boots.append(spearman_r(xs[idx], ys[idx]))
            lo, hi = np.nanquantile(boots, [0.025, 0.975])
            rho_ci = [float(lo), float(hi)]
        else:
            rho_ci = [float("nan"), float("nan")]
        by_venue[venue] = mq
        effects[venue] = {
            **quartile_effect(mq),
            "spearman_rho": rho,
            "spearman_ci95": rho_ci,
            "n_hours": len(rows),
            "quartiles": mq.get("quartiles"),
            "means": mq.get("means"),
            "ns": mq.get("ns"),
            "decision": "Hold",
            "tradable": False,
            "label": "info_monitor_within_venue",
            "why": (
                "Within-venue hourly markout~rel_tick (τ fixed; mid-driven). "
                "Not tradable; kills day-level x-venue confound on this lens only."
            ),
        }

    figs = plot_within_venue_quartiles(by_venue, hour_pts)
    # slim hour dump
    slim_hours = {
        v: [
            {k: r[k] for k in ("day", "hour_id", "rel_tick", "rel_tick_bps", "markout_1s_bps", "n_trades", "quoted_spread_bps")}
            for r in rows
        ]
        for v, rows in hour_pts.items()
    }
    return {"effects": effects, "by_venue": by_venue, "hours": slim_hours, "figs": figs}


def main() -> None:
    TC_FIGS.mkdir(parents=True, exist_ok=True)
    RTP_FIGS.mkdir(parents=True, exist_ok=True)
    days = days_from_panel()
    print("days", days, flush=True)

    hl = run_hl_stacks(days)
    (TC_OUT / "pass2_info_exec.json").write_text(json.dumps(hl, indent=2, default=str))

    wv = run_within_venue_markout(days)
    (RTP_OUT / "markout_quartile_within_venue.json").write_text(json.dumps(wv, indent=2, default=str))

    print("HL figs", hl["figs"])
    print("HL gate", json.dumps(hl["gate"], indent=2, default=str))
    print("within-venue effects", json.dumps(wv["effects"], indent=2, default=str))
    print("RTP figs", wv["figs"])


if __name__ == "__main__":
    main()
