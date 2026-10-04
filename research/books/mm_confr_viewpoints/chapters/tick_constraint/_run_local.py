from __future__ import annotations
#!/usr/bin/env python3
"""Chapter-local empirics for tick_constraint (HL + Deribit + Kraken).

Produces out/tick_constraint/{summary.json, figs/*.png}.
Kraken trade_synth TOB is labeled honestly and excluded from OFI event study.
ClickHouse MCP banned. Does not edit shared lib.
"""


import json
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BOOK = Path(__file__).resolve().parents[2]
ROOT = BOOK.parents[2]
SCRIPTS = BOOK / "scripts"
OUT = BOOK / "out" / "tick_constraint"
FIGS = OUT / "figs"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from _data import (  # noqa: E402
    CORE_VENUES,
    ensure_env,
    load_day_trades,
    load_tob_any,
    resolve_days,
)
from ares_micro.flow.continuous import trade_intensity  # noqa: E402
from ares_micro.book.spreads import quoted_spread_bps  # noqa: E402
from ares_micro.book.ticksize import (  # noqa: E402
    relative_tick,
    spread_in_ticks,
    tick_constrained,
    undercutting_proxy,
    venue_tick,
)

KNOWN_TAU = {"hyperliquid": 0.1, "deribit": 0.05}
KRAKEN_SPOT_TAU = 0.01  # ETH/USD spot; futures PF often 0.05
SYMBOL = "ETH"
BAR_NS = 60_000_000_000  # 1 min
EVENT_HALF_BARS = 10


def is_synth(source: str | None) -> bool:
    s = str(source or "").lower()
    return "trade_synth" in s or s.endswith("/trade") or "synth" in s


def is_kraken_spot(tob: dict[str, Any]) -> bool:
    if bool(tob.get("is_synth")) or is_synth(tob.get("source")):
        return False
    return (
        str(tob.get("market") or "") == "spot"
        or "spot_l2" in str(tob.get("source") or "").lower()
        or "kraken_spot" in str(tob.get("source") or "").lower()
    )


def resolve_tau(venue: str, tob: dict[str, Any], px: np.ndarray) -> dict[str, Any]:
    prices = np.concatenate(
        [np.asarray(tob["bid"], dtype=np.float64), np.asarray(tob["ask"], dtype=np.float64)]
    )
    if is_synth(tob.get("source")):
        # Prefer trade-price inference for synth TOB
        prices = px if px.size else prices
    known: dict[str, float] | None
    if venue in KNOWN_TAU:
        known = {venue: KNOWN_TAU[venue]}
    elif venue == "kraken" and is_kraken_spot(tob):
        known = {"kraken": KRAKEN_SPOT_TAU}
    else:
        known = None
    vt = venue_tick(venue, prices=prices, known_ticks=known)
    tau = float(vt["tau"])
    if venue == "kraken" and (not np.isfinite(tau) or tau < 1e-4):
        vt2 = venue_tick(venue, prices=px if px.size else prices)
        if np.isfinite(vt2["tau"]) and vt2["tau"] >= 1e-4:
            return vt2
        fallback = KRAKEN_SPOT_TAU if is_kraken_spot(tob) else 0.05
        return {
            "venue": "kraken",
            "tau": fallback,
            "inferred": vt.get("inferred"),
            "catalog_tick": None,
            "source": "known_fallback_spot" if is_kraken_spot(tob) else "known_fallback",
        }
    return vt


def minute_series(tob: dict[str, Any], tau: float) -> dict[str, np.ndarray]:
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

    t0, t1 = int(ts.min()), int(ts.max())
    grid = np.arange(t0, t1 + 1, BAR_NS, dtype=np.int64)
    if grid.size < 3:
        return {}
    idx = np.searchsorted(ts, grid, side="left")
    n = grid.size - 1
    out = {
        "t_mid": 0.5 * (grid[:-1] + grid[1:]),
        "frac_c": np.full(n, np.nan),
        "med_spread_ticks": np.full(n, np.nan),
        "med_qs_bps": np.full(n, np.nan),
        "med_rel_tick": np.full(n, np.nan),
        "n_quotes": np.zeros(n, dtype=np.int64),
        "undercut_rate": np.full(n, np.nan),
        "ofi_sum": np.full(n, np.nan),
        "mid_last": np.full(n, np.nan),
    }
    # vectorized Cont–Kukanov L0 OFI contributions
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

    for i in range(n):
        lo, hi = int(idx[i]), int(idx[i + 1])
        if hi <= lo:
            continue
        sl = slice(lo, hi)
        c = cons[sl]
        s = st[sl]
        out["n_quotes"][i] = hi - lo
        out["frac_c"][i] = float(np.mean(c)) if c.size else np.nan
        out["med_spread_ticks"][i] = float(np.nanmedian(s))
        out["med_qs_bps"][i] = float(np.nanmedian(qs[sl]))
        out["med_rel_tick"][i] = float(np.nanmedian(rt[sl]))
        out["ofi_sum"][i] = float(ofi_e[sl].sum())
        out["mid_last"][i] = float(mid[hi - 1])
        if hi - lo >= 3:
            uc = undercutting_proxy(mid[sl], bid[sl], ask[sl], tau)
            out["undercut_rate"][i] = uc.get("undercut_rate", np.nan)
    return out


def detect_flips(frac_c: np.ndarray, *, enter_thr: float = 0.55, exit_thr: float = 0.45) -> dict[str, list[int]]:
    """Constraint enter (relax→constrained) and relax (constrained→loose) bar indices."""
    state = None
    enter, relax = [], []
    for i, f in enumerate(frac_c):
        if not np.isfinite(f):
            continue
        if state is None:
            state = "c" if f >= enter_thr else "u"
            continue
        if state == "u" and f >= enter_thr:
            enter.append(i)
            state = "c"
        elif state == "c" and f <= exit_thr:
            relax.append(i)
            state = "u"
    return {"enter": enter, "relax": relax}


def quote_level_flip_bars(
    ts: np.ndarray,
    constrained: np.ndarray,
    t_mid: np.ndarray,
    *,
    min_gap_bars: int = 3,
) -> dict[str, list[int]]:
    """Map quote-level constrained↔unconstrained flips onto minute-bar indices."""
    c = np.asarray(constrained, dtype=bool)
    if c.size < 3 or t_mid.size < 3:
        return {"enter": [], "relax": []}
    # True→False = relax; False→True = enter
    d = np.diff(c.astype(np.int8))
    relax_ts = ts[1:][d == -1]
    enter_ts = ts[1:][d == 1]
    def _map(event_ts: np.ndarray) -> list[int]:
        if event_ts.size == 0:
            return []
        bars = np.searchsorted(t_mid, event_ts, side="left")
        bars = bars[(bars >= 0) & (bars < t_mid.size)]
        # dedupe close flips
        out: list[int] = []
        last = -10**9
        for b in bars.tolist():
            if b - last >= min_gap_bars:
                out.append(int(b))
                last = b
        return out
    return {"enter": _map(enter_ts), "relax": _map(relax_ts)}


def event_stack(
    series: dict[str, np.ndarray],
    events: list[int],
    keys: tuple[str, ...] = ("frac_c", "undercut_rate", "ofi_sum", "med_qs_bps"),
) -> dict[str, Any]:
    half = EVENT_HALF_BARS
    lags = np.arange(-half, half + 1)
    mats = {k: [] for k in keys}
    for e in events:
        if e < half or e + half >= series["frac_c"].size:
            continue
        for k in keys:
            mats[k].append(series[k][e - half : e + half + 1])
    out: dict[str, Any] = {"n_events": 0, "lags": lags.tolist()}
    for k, rows in mats.items():
        if not rows:
            out[k] = {"mean": [float("nan")] * lags.size, "n": 0}
            continue
        m = np.vstack(rows)
        out[k] = {
            "mean": [float(np.nanmean(m[:, j])) for j in range(m.shape[1])],
            "n": int(m.shape[0]),
        }
        out["n_events"] = int(m.shape[0])
    return out


def label_desk(day_row: dict[str, Any]) -> str:
    """exec throttle vs fragility monitor vs n/a."""
    frac = day_row.get("frac_constrained_2tick")
    under = day_row.get("undercut_rate")
    markout = day_row.get("markout_1s_bps")
    synth = day_row.get("is_synth")
    if synth:
        return "n/a_synth_tob"
    if not (np.isfinite(frac) and np.isfinite(under)):
        return "n/a"
    high_c = frac >= 0.5
    high_u = under >= 0.08
    mark_bad = np.isfinite(markout) and markout > 5.0
    if high_c and high_u and mark_bad:
        return "exec_throttle"
    if high_c and high_u:
        return "fragility_monitor"
    if high_c:
        return "constrained_quiet"
    return "unconstrained"


def load_slice(days: list[str]) -> list[dict[str, Any]]:
    ensure_env()
    rows = []
    for day in days:
        for venue in CORE_VENUES:
            print(f"tick_constraint load {venue} {day}", flush=True)
            try:
                trades = load_day_trades(venue, SYMBOL, day, quiet=True)
                tape = trades["tape"]
                px = np.asarray(tape["px"], dtype=np.float64)
                ts_tr = np.asarray(tape["ts"], dtype=np.int64)
                tob = load_tob_any(venue, SYMBOL, day)
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    {
                        "venue": venue,
                        "day": day,
                        "error": f"{type(exc).__name__}: {exc}",
                        "tob_ok": False,
                    }
                )
                continue
            vt = resolve_tau(venue, tob, px)
            tau = float(vt["tau"])
            st = spread_in_ticks(tob["bid"], tob["ask"], tau)
            cons = tick_constrained(st, max_ticks=2.0)
            frac_c = float(np.mean(cons)) if isinstance(cons, np.ndarray) and cons.size else float("nan")
            uc = undercutting_proxy(tob["mid"], tob["bid"], tob["ask"], tau)
            synth = is_synth(tob.get("source"))
            ofi_corr = float("nan")
            intensity = float("nan")
            series = {}
            flips = {"enter": [], "relax": []}
            stacks = {}
            if not synth and tob["ts"].size >= 200:
                try:
                    series = minute_series(tob, tau)
                    st = spread_in_ticks(tob["bid"], tob["ask"], tau)
                    cons = tick_constrained(st, max_ticks=2.0)
                    if not isinstance(cons, np.ndarray):
                        cons = np.zeros(tob["ts"].size, dtype=bool)
                    flips_bar = detect_flips(series.get("frac_c", np.array([])))
                    flips_q = quote_level_flip_bars(
                        np.asarray(tob["ts"], dtype=np.int64),
                        cons,
                        np.asarray(series.get("t_mid", []), dtype=np.float64),
                    )
                    # prefer quote-level flips when minute regime never crosses
                    flips = {
                        "enter": flips_q["enter"] or flips_bar["enter"],
                        "relax": flips_q["relax"] or flips_bar["relax"],
                    }
                    stacks = {
                        "relax": event_stack(series, flips["relax"]),
                        "enter": event_stack(series, flips["enter"]),
                        "flip_source": "quote" if flips_q["relax"] or flips_q["enter"] else "minute",
                    }
                    # OFI–return corr from 1m bars
                    ofi_b = np.asarray(series.get("ofi_sum", []), dtype=np.float64)
                    mid_b = np.asarray(series.get("mid_last", []), dtype=np.float64)
                    if ofi_b.size > 20 and mid_b.size == ofi_b.size:
                        ret = np.full(mid_b.size, np.nan)
                        okm = np.isfinite(mid_b) & (mid_b > 0)
                        for i in range(1, mid_b.size):
                            if okm[i] and okm[i - 1]:
                                ret[i] = np.log(mid_b[i] / mid_b[i - 1])
                        m = np.isfinite(ret) & np.isfinite(ofi_b)
                        if int(m.sum()) >= 20:
                            o0 = ofi_b[m] - ofi_b[m].mean()
                            r0 = ret[m] - ret[m].mean()
                            den = float(np.sqrt((o0 * o0).sum() * (r0 * r0).sum()))
                            ofi_corr = float((o0 * r0).sum() / den) if den > 0 else float("nan")
                except Exception as exc:  # noqa: BLE001
                    stacks = {"error": f"{type(exc).__name__}: {exc}"}
            try:
                ti = trade_intensity(ts_tr, bar_ns=BAR_NS)
                intensity = float(ti.get("mean_lambda", np.nan))
            except Exception:
                pass

            # crude markout: mid move 1s after trade
            markout = float("nan")
            try:
                from ares_micro.flow.markout import trade_markouts

                side = np.asarray(tape["side"], dtype=np.float64)
                mo = trade_markouts(ts_tr, px, side, tob["ts"], tob["mid"], horizons_ms=(1000,))
                by_h = mo.get("by_horizon") or {}
                if "1000" in by_h:
                    markout = float(by_h["1000"].get("mean_bps", np.nan))
            except Exception:
                pass

            st_finite = st[np.isfinite(st)]
            row = {
                "venue": venue,
                "day": day,
                "symbol": SYMBOL,
                "tob_ok": True,
                "tob_n": int(tob.get("n", tob["ts"].size)),
                "tob_source": tob.get("source"),
                "is_synth": synth,
                "tau": tau,
                "tau_source": vt.get("source"),
                "frac_constrained_2tick": frac_c,
                "frac_one_tick": float(np.mean(np.abs(st_finite - 1.0) <= 0.05)) if st_finite.size else float("nan"),
                "median_spread_ticks": float(np.nanmedian(st)) if st.size else float("nan"),
                "undercut_rate": uc.get("undercut_rate"),
                "tighten_rate": uc.get("tighten_rate"),
                "ofi_corr": ofi_corr,
                "intensity": intensity,
                "markout_1s_bps": markout,
                "n_trades": int(ts_tr.size),
                "completeness": trades.get("completeness"),
                "spread_ticks_sample": st_finite[:: max(1, st_finite.size // 5000)].tolist()
                if st_finite.size
                else [],
                "series": {
                    k: (v.tolist() if isinstance(v, np.ndarray) else v)
                    for k, v in series.items()
                    if k in ("t_mid", "frac_c", "undercut_rate", "ofi_sum", "med_spread_ticks", "med_rel_tick")
                },
                "n_flips_enter": len(flips.get("enter", [])),
                "n_flips_relax": len(flips.get("relax", [])),
                "event_stacks": stacks,
            }
            row["desk_label"] = label_desk(row)
            rows.append(row)
    return rows


def save_figs(rows: list[dict[str, Any]]) -> list[str]:
    FIGS.mkdir(parents=True, exist_ok=True)
    produced: list[str] = []
    ok = [r for r in rows if r.get("tob_ok")]

    # 1) frac constrained by venue over days
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    venues = list(CORE_VENUES)
    days = sorted({r["day"] for r in ok})
    x = np.arange(len(days))
    width = 0.25
    for i, v in enumerate(venues):
        ys = []
        for d in days:
            hit = next((r for r in ok if r["venue"] == v and r["day"] == d), None)
            ys.append(hit["frac_constrained_2tick"] if hit else np.nan)
        ax.bar(x + i * width, ys, width, label=v)
    ax.set_xticks(x + width)
    ax.set_xticklabels(days, rotation=20)
    ax.set_ylabel("frac quotes with spread ≤ 2 ticks")
    ax.set_title("Tick-constrained fraction by venue × day (ETH)")
    ax.legend(fontsize=8)
    ax.set_ylim(0, 1.05)
    ax.axhline(0.5, color="gray", ls="--", lw=0.8, alpha=0.7)
    fig.tight_layout()
    p = FIGS / "fig_frac_constrained_panel.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    produced.append(str(p.name))

    # 2) spread-in-ticks hist by venue (pool days; annotate synth)
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.6), sharey=True)
    for ax, v in zip(axes, venues):
        samples = []
        synth = False
        for r in ok:
            if r["venue"] != v:
                continue
            samples.extend(r.get("spread_ticks_sample") or [])
            synth = synth or bool(r.get("is_synth"))
        samples = np.asarray(samples, dtype=np.float64)
        samples = samples[np.isfinite(samples) & (samples > 0) & (samples < 20)]
        if samples.size:
            ax.hist(samples, bins=40, color="#2c5f7c" if not synth else "#b07d4f", alpha=0.85)
        ax.set_title(f"{v}" + (" [synth TOB]" if synth else ""))
        ax.set_xlabel("spread (ticks)")
        ax.axvline(1.0, color="crimson", ls="--", lw=1)
        ax.axvline(2.0, color="orange", ls=":", lw=1)
    axes[0].set_ylabel("quote count (subsampled)")
    fig.suptitle("Spread-in-ticks distribution (≤20 ticks shown)", y=1.02)
    fig.tight_layout()
    p = FIGS / "fig_spread_ticks_hist.png"
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    produced.append(str(p.name))

    # 3) undercut rate vs frac constrained scatter
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    for v in venues:
        sub = [r for r in ok if r["venue"] == v]
        xs = [r["frac_constrained_2tick"] for r in sub]
        ys = [r["undercut_rate"] for r in sub]
        marker = "x" if any(r.get("is_synth") for r in sub) else "o"
        ax.scatter(xs, ys, label=v, s=55, marker=marker)
        for r in sub:
            ax.annotate(r["day"][-5:], (r["frac_constrained_2tick"], r["undercut_rate"]), fontsize=7, alpha=0.7)
    ax.set_xlabel("frac_constrained_2tick")
    ax.set_ylabel("undercut_rate (L0 tighten ≤1.5τ)")
    ax.set_title("Undercutting vs constraint (× = Kraken synth)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    p = FIGS / "fig_undercut_vs_constraint.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    produced.append(str(p.name))

    # 4) event study: stack relax events (non-synth only)
    fig, axes = plt.subplots(2, 2, figsize=(9, 6.5))
    metrics = [
        ("frac_c", "frac constrained"),
        ("undercut_rate", "undercut rate"),
        ("ofi_sum", "OFI sum (1m)"),
        ("med_qs_bps", "quoted spread bps"),
    ]
    # pool stacks across non-synth venue-days
    pooled: dict[str, list[list[float]]] = {k: [] for k, _ in metrics}
    n_ev = 0
    for r in ok:
        if r.get("is_synth"):
            continue
        stack = (r.get("event_stacks") or {}).get("relax") or {}
        if not stack or stack.get("n_events", 0) == 0:
            continue
        n_ev += int(stack["n_events"])
        for k, _ in metrics:
            m = (stack.get(k) or {}).get("mean")
            if m:
                pooled[k].append(m)
    lags = list(range(-EVENT_HALF_BARS, EVENT_HALF_BARS + 1))
    for ax, (k, title) in zip(axes.ravel(), metrics):
        if pooled[k]:
            mat = np.asarray(pooled[k], dtype=np.float64)
            mean = np.nanmean(mat, axis=0)
            ax.plot(lags, mean, color="#1f4e6b", lw=2)
            ax.axvline(0, color="crimson", ls="--", lw=1)
            ax.set_title(f"{title} (n_ev≈{n_ev})")
        else:
            ax.text(0.5, 0.5, "no relax events", ha="center", va="center", transform=ax.transAxes)
            ax.set_title(title)
        ax.set_xlabel("minutes from relax flip")
    fig.suptitle("Constraint-relax event study (HL+Deribit; Kraken synth excluded)", y=1.01)
    fig.tight_layout()
    p = FIGS / "fig_relax_event_study.png"
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    produced.append(str(p.name))

    # 5) time series frac_c for one HL day
    hl = [r for r in ok if r["venue"] == "hyperliquid" and r.get("series", {}).get("frac_c")]
    if hl:
        r = max(hl, key=lambda z: len(z["series"]["frac_c"]))
        t = np.asarray(r["series"]["t_mid"], dtype=np.float64)
        t0 = t[0]
        hours = (t - t0) / 3.6e12
        fig, ax = plt.subplots(figsize=(9, 3.4))
        ax.plot(hours, r["series"]["frac_c"], color="#1f4e6b", lw=1.2, label="frac ≤2 ticks")
        ax.plot(hours, r["series"]["undercut_rate"], color="#b07d4f", lw=1.0, alpha=0.85, label="undercut")
        ax.set_xlabel(f"hours from start ({r['day']} HL)")
        ax.set_ylabel("rate")
        ax.set_ylim(-0.05, 1.05)
        ax.legend(fontsize=8)
        ax.set_title("Intraday constraint & undercutting (Hyperliquid)")
        fig.tight_layout()
        p = FIGS / "fig_intraday_constraint_hl.png"
        fig.savefig(p, dpi=140)
        plt.close(fig)
        produced.append(str(p.name))

    # 6) desk labels board
    fig, ax = plt.subplots(figsize=(8, 3.8))
    labels = [r.get("desk_label", "n/a") for r in ok]
    venues_l = [r["venue"][:2] + "/" + r["day"][-5:] for r in ok]
    colors = {
        "exec_throttle": "#8b1e1e",
        "fragility_monitor": "#c47a20",
        "constrained_quiet": "#2c5f7c",
        "unconstrained": "#5a8f5a",
        "n/a_synth_tob": "#999999",
        "n/a": "#cccccc",
    }
    y = np.arange(len(ok))
    ax.barh(y, [1] * len(ok), color=[colors.get(l, "#ddd") for l in labels])
    ax.set_yticks(y)
    ax.set_yticklabels(venues_l, fontsize=8)
    ax.set_xlim(0, 1)
    ax.set_xticks([])
    ax.set_title("Desk labels: exec_throttle vs fragility_monitor")
    for i, lab in enumerate(labels):
        ax.text(0.02, i, lab, va="center", fontsize=8, color="white" if lab.startswith("exec") else "black")
    fig.tight_layout()
    p = FIGS / "fig_desk_labels.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    produced.append(str(p.name))

    return produced


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    # Prefer days already in pass1 panel if present
    panel_path = BOOK / "out" / "pass1" / "panel.json"
    if panel_path.is_file():
        days = json.loads(panel_path.read_text()).get("days") or resolve_days(None, "hyperliquid", n=3)
    else:
        days = resolve_days(None, "hyperliquid", n=3)
    rows = load_slice(days)
    figs = save_figs(rows)

    # strip heavy series from summary JSON (keep event stacks means)
    slim = []
    for r in rows:
        s = {k: v for k, v in r.items() if k not in ("spread_ticks_sample", "series")}
        # keep short series stats only
        ser = r.get("series") or {}
        if ser.get("frac_c"):
            fc = np.asarray(ser["frac_c"], dtype=np.float64)
            s["series_summary"] = {
                "n_bars": int(fc.size),
                "mean_frac_c": float(np.nanmean(fc)),
                "std_frac_c": float(np.nanstd(fc)),
            }
        slim.append(s)

    summary = {
        "symbol": SYMBOL,
        "days": days,
        "venues": list(CORE_VENUES),
        "n_rows": len(rows),
        "n_tob_ok": sum(1 for r in rows if r.get("tob_ok")),
        "n_synth": sum(1 for r in rows if r.get("is_synth")),
        "median_frac_c": float(
            np.nanmedian([r["frac_constrained_2tick"] for r in rows if r.get("tob_ok")])
        ),
        "median_undercut": float(
            np.nanmedian([r["undercut_rate"] for r in rows if r.get("tob_ok") and np.isfinite(r.get("undercut_rate") or np.nan)])
        ),
        "desk_label_counts": {
            lab: sum(1 for r in rows if r.get("desk_label") == lab)
            for lab in sorted({r.get("desk_label") for r in rows if r.get("tob_ok")})
        },
        "figs": figs,
        "note_kraken": "Kraken TOB often warehouse:trade_synth — labeled is_synth; excluded from OFI event study",
        "rows": slim,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print("wrote", OUT / "summary.json", "figs", figs)


if __name__ == "__main__":
    main()
