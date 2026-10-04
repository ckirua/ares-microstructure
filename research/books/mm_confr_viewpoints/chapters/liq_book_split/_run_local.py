from __future__ import annotations
#!/usr/bin/env python3
"""Chapter-local empirics for liq_book_split (HL + Deribit + Kraken).

Liquid vs thin terciles × rel_tick interactions; placebo mid moves that do
not change rel_tick; make/take hypothesis vs constraint flags.

Writes out/liq_book_split/{summary.json, figs/*.png}.
Labels Kraken trade_synth TOB honestly. ClickHouse MCP banned.
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
OUT = BOOK / "out" / "liq_book_split"
FIGS = OUT / "figs"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from _data import CORE_VENUES, ensure_env, load_day_trades, load_tob_any  # noqa: E402
from ares_micro.book.spreads import quoted_spread_bps  # noqa: E402
from ares_micro.stats import spearman_r  # noqa: E402
from ares_micro.book.ticksize import (  # noqa: E402
    liquid_book_classifier,
    relative_tick,
    spread_in_ticks,
    tick_constrained,
    undercutting_proxy,
    venue_tick,
)

KNOWN_TAU = {"hyperliquid": 0.1, "deribit": 0.05}
KRAKEN_SPOT_TAU = 0.01
SYMBOL = "ETH"
BAR_NS = 60_000_000_000


def is_synth(source: str | None) -> bool:
    s = str(source or "").lower()
    return "trade_synth" in s or "synth" in s


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
        prices = px if px.size else prices
    if venue in KNOWN_TAU:
        known: dict[str, float] | None = {venue: KNOWN_TAU[venue]}
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


def hour_buckets(tob: dict[str, Any], tau: float) -> list[dict[str, Any]]:
    ts = np.asarray(tob["ts"], dtype=np.int64)
    bid = np.asarray(tob["bid"], dtype=np.float64)
    ask = np.asarray(tob["ask"], dtype=np.float64)
    mid = np.asarray(tob["mid"], dtype=np.float64)
    bs = np.asarray(tob["bid_sz"], dtype=np.float64)
    az = np.asarray(tob["ask_sz"], dtype=np.float64)
    qs = quoted_spread_bps(bid, ask, mid=mid)
    rt = np.asarray(relative_tick(tau, mid, as_bps=False), dtype=np.float64)
    depth = bs + az
    st = spread_in_ticks(bid, ask, tau)
    cons = tick_constrained(st, max_ticks=2.0)
    if not isinstance(cons, np.ndarray):
        cons = np.zeros(ts.size, dtype=bool)

    hours = ts // 3_600_000_000_000
    rows = []
    for h in np.unique(hours):
        m = hours == h
        if int(m.sum()) < 20:
            continue
        mid_h = mid[m]
        rt_h = rt[m]
        # make/take proxy: share of updates that tighten vs widen
        uc = undercutting_proxy(mid_h, bid[m], ask[m], tau)
        rows.append(
            {
                "hour_id": int(h),
                "n": int(m.sum()),
                "quoted_spread_bps": float(np.nanmedian(qs[m])),
                "rel_tick": float(np.nanmedian(rt_h)),
                "rel_tick_bps": float(np.nanmedian(rt_h) * 1e4),
                "bbo_depth": float(np.nanmedian(depth[m])),
                "mid": float(np.nanmedian(mid_h)),
                "frac_constrained": float(np.mean(cons[m])),
                "undercut_rate": uc.get("undercut_rate"),
                "tighten_rate": uc.get("tighten_rate"),
                "mid_range_bps": float(
                    1e4 * (np.nanmax(mid_h) - np.nanmin(mid_h)) / np.nanmedian(mid_h)
                )
                if np.nanmedian(mid_h) > 0
                else float("nan"),
                "rel_tick_range": float(np.nanmax(rt_h) - np.nanmin(rt_h)),
            }
        )
    return rows


def placebo_flags(hour_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flag hours with material mid move but tiny rel_tick change (τ fixed).

    Placebo: price moved but relative tick ≈ flat → MQ Δ should *not* be
    attributed to the rel_tick channel if the Rindi equivalence holds tightly.
    """
    out = []
    for r in hour_rows:
        mid_bps = r.get("mid_range_bps", float("nan"))
        rt_r = r.get("rel_tick_range", float("nan"))
        rt = r.get("rel_tick", float("nan"))
        # tiny rel_tick change: range < 2% of level; mid move > 5 bps
        placebo = (
            np.isfinite(mid_bps)
            and np.isfinite(rt_r)
            and np.isfinite(rt)
            and rt > 0
            and mid_bps >= 5.0
            and (rt_r / rt) < 0.02
        )
        rr = dict(r)
        rr["placebo_mid_move"] = bool(placebo)
        out.append(rr)
    return out


def load_rows(days: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ensure_env()
    day_rows: list[dict[str, Any]] = []
    hour_rows: list[dict[str, Any]] = []
    for day in days:
        for venue in CORE_VENUES:
            print(f"liq_book_split load {venue} {day}", flush=True)
            try:
                trades = load_day_trades(venue, SYMBOL, day, quiet=True)
                px = np.asarray(trades["tape"]["px"], dtype=np.float64)
                qty = np.asarray(trades["tape"]["qty"], dtype=np.float64)
                tob = load_tob_any(venue, SYMBOL, day)
            except Exception as exc:  # noqa: BLE001
                day_rows.append(
                    {"venue": venue, "day": day, "error": f"{type(exc).__name__}: {exc}", "tob_ok": False}
                )
                continue
            vt = resolve_tau(venue, tob, px)
            tau = float(vt["tau"])
            qs = quoted_spread_bps(tob["bid"], tob["ask"], mid=tob["mid"])
            mid_m = float(np.nanmedian(tob["mid"]))
            rt = float(relative_tick(tau, mid_m, as_bps=False))
            depth = float(
                np.nanmedian(
                    np.asarray(tob["bid_sz"], dtype=np.float64) + np.asarray(tob["ask_sz"], dtype=np.float64)
                )
            )
            st = spread_in_ticks(tob["bid"], tob["ask"], tau)
            cons = tick_constrained(st, max_ticks=2.0)
            frac_c = float(np.mean(cons)) if isinstance(cons, np.ndarray) else float(cons)
            uc = undercutting_proxy(tob["mid"], tob["bid"], tob["ask"], tau)
            synth = is_synth(tob.get("source"))
            vol = float("nan")
            if px.size > 50:
                ret = np.diff(np.log(np.clip(px[px > 0], 1e-12, None)))
                ret = ret[np.isfinite(ret)]
                if ret.size > 10:
                    vol = float(np.std(ret) * np.sqrt(ret.size))
            day_rows.append(
                {
                    "venue": venue,
                    "day": day,
                    "symbol": SYMBOL,
                    "tob_ok": True,
                    "tob_source": tob.get("source"),
                    "is_synth": synth,
                    "tau": tau,
                    "tau_source": vt.get("source"),
                    "quoted_spread_bps": float(np.nanmedian(qs)),
                    "rel_tick": rt,
                    "rel_tick_bps": rt * 1e4,
                    "bbo_depth": depth,
                    "volume": float(qty[np.isfinite(qty) & (qty > 0)].sum()) if qty.size else float("nan"),
                    "frac_constrained_2tick": frac_c,
                    "undercut_rate": uc.get("undercut_rate"),
                    "tighten_rate": uc.get("tighten_rate"),
                    "vol": vol,
                    "n_trades": int(trades["tape"]["ts"].size),
                    "completeness": trades.get("completeness"),
                    "trade_intensity": float(trades["tape"]["ts"].size) / 86400.0,
                }
            )
            hrs = hour_buckets(tob, tau)
            hrs = placebo_flags(hrs)
            for h in hrs:
                h["venue"] = venue
                h["day"] = day
                h["is_synth"] = synth
                hour_rows.append(h)
    return day_rows, hour_rows


def het_by_tercile(classified: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for book in ("liquid", "mid", "less_liquid"):
        sub = [r for r in classified if r.get("book_liq") == book]
        xs = np.asarray([float(r["rel_tick"]) for r in sub if np.isfinite(float(r.get("rel_tick") or np.nan))])
        ys = np.asarray(
            [float(r["quoted_spread_bps"]) for r in sub if np.isfinite(float(r.get("quoted_spread_bps") or np.nan))]
        )
        yd = np.asarray([float(r["bbo_depth"]) for r in sub if np.isfinite(float(r.get("bbo_depth") or np.nan))])
        n = min(xs.size, ys.size)
        out[book] = {
            "n": int(n),
            "rho_rel_tick_spread": float(spearman_r(xs[:n], ys[:n])) if n >= 3 else float("nan"),
            "rho_rel_tick_depth": float(spearman_r(xs[: min(xs.size, yd.size)], yd[: min(xs.size, yd.size)]))
            if min(xs.size, yd.size) >= 3
            else float("nan"),
            "mean_spread_bps": float(np.nanmean(ys)) if ys.size else float("nan"),
            "mean_rel_tick": float(np.nanmean(xs)) if xs.size else float("nan"),
        }
    return out


def make_take_hypothesis(hour_rows: list[dict[str, Any]], classified_days: list[dict[str, Any]]) -> dict[str, Any]:
    """Deck: liquid books undercut when rel_tick falls; thin books shift LO→MO.

    Proxy: within liquid tercile, corr(Δrel_tick, undercut_rate) should be negative
    (rel_tick ↓ → undercut ↑). Within thin: corr(Δrel_tick, tighten_rate) weaker /
    volume proxy via n quotes.
    """
    day_book = {(r["venue"], r["day"]): r.get("book_liq") for r in classified_days}
    by_book: dict[str, list[dict[str, Any]]] = {"liquid": [], "less_liquid": [], "mid": []}
    # sort hours and compute Δrel_tick within venue-day
    keyed: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for h in hour_rows:
        if h.get("is_synth"):
            continue
        keyed.setdefault((h["venue"], h["day"]), []).append(h)
    for key, hrs in keyed.items():
        hrs = sorted(hrs, key=lambda z: z["hour_id"])
        book = day_book.get(key, "unknown")
        for i in range(1, len(hrs)):
            d_rt = hrs[i]["rel_tick"] - hrs[i - 1]["rel_tick"]
            row = {
                "d_rel_tick": d_rt,
                "undercut_rate": hrs[i]["undercut_rate"],
                "tighten_rate": hrs[i]["tighten_rate"],
                "quoted_spread_bps": hrs[i]["quoted_spread_bps"],
                "book_liq": book,
            }
            if book in by_book:
                by_book[book].append(row)

    result: dict[str, Any] = {}
    for book, rows in by_book.items():
        if len(rows) < 5:
            result[book] = {"n": len(rows), "rho_drel_undercut": float("nan")}
            continue
        xs = np.asarray([r["d_rel_tick"] for r in rows], dtype=np.float64)
        ys = np.asarray([r["undercut_rate"] for r in rows], dtype=np.float64)
        m = np.isfinite(xs) & np.isfinite(ys)
        result[book] = {
            "n": int(m.sum()),
            "rho_drel_undercut": float(spearman_r(xs[m], ys[m])) if m.sum() >= 5 else float("nan"),
            "hypothesis": (
                "expect rho(Δrel_tick, undercut)<0 on liquid (rel↓ → undercut↑)"
                if book == "liquid"
                else "expect weaker / flipped undercut channel on thin"
            ),
        }
    return result


def save_figs(
    day_rows: list[dict[str, Any]],
    hour_rows: list[dict[str, Any]],
    classified: list[dict[str, Any]],
    het: dict[str, Any],
    make_take: dict[str, Any],
) -> list[str]:
    FIGS.mkdir(parents=True, exist_ok=True)
    produced: list[str] = []
    ok = [r for r in classified if r.get("tob_ok")]

    # 1) scatter rel_tick vs spread colored by tercile
    fig, ax = plt.subplots(figsize=(7, 4.8))
    colors = {"liquid": "#2c5f7c", "mid": "#8a8a8a", "less_liquid": "#b07d4f", "unknown": "#cccccc"}
    for book, c in colors.items():
        sub = [r for r in ok if r.get("book_liq") == book]
        if not sub:
            continue
        xs = [r["rel_tick"] * 1e4 for r in sub]
        ys = [r["quoted_spread_bps"] for r in sub]
        markers = ["x" if r.get("is_synth") else "o" for r in sub]
        for x, y, m, r in zip(xs, ys, markers, sub):
            ax.scatter(x, y, c=c, marker=m, s=60, label=book if m == "o" and r is sub[0] else None)
        # legend once
        ax.scatter([], [], c=c, marker="o", s=60, label=book)
    ax.set_xlabel("relative tick (bps)")
    ax.set_ylabel("quoted spread (bps)")
    ax.set_title("Liquid vs thin tercile × rel_tick (day panel; ×=synth)")
    # dedupe legend
    handles, labels = ax.get_legend_handles_labels()
    uniq = dict(zip(labels, handles))
    ax.legend(uniq.values(), uniq.keys(), fontsize=8)
    fig.tight_layout()
    p = FIGS / "fig_tercile_rel_tick_spread.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    produced.append(p.name)

    # 2) het rho bars
    fig, ax = plt.subplots(figsize=(6, 3.8))
    books = ["liquid", "mid", "less_liquid"]
    rhos = [het.get(b, {}).get("rho_rel_tick_spread", np.nan) for b in books]
    ns = [het.get(b, {}).get("n", 0) for b in books]
    ax.bar(books, rhos, color=["#2c5f7c", "#8a8a8a", "#b07d4f"])
    for i, (rho, n) in enumerate(zip(rhos, ns)):
        if np.isfinite(rho):
            ax.text(i, rho, f"n={n}\n{rho:.2f}", ha="center", va="bottom" if rho >= 0 else "top", fontsize=8)
    ax.axhline(0, color="gray", lw=0.8)
    ax.set_ylabel("Spearman ρ(rel_tick, quoted_spread)")
    ax.set_title("Heterogeneous rel_tick↔spread by book liquidity")
    fig.tight_layout()
    p = FIGS / "fig_het_rho_bars.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    produced.append(p.name)

    # 3) interaction: hour-level, liquid vs thin slopes
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    day_book = {(r["venue"], r["day"]): r.get("book_liq") for r in ok}
    for ax, book in zip(axes, ("liquid", "less_liquid")):
        pts = [
            h
            for h in hour_rows
            if day_book.get((h["venue"], h["day"])) == book and not h.get("is_synth")
        ]
        if pts:
            xs = np.asarray([h["rel_tick"] * 1e4 for h in pts])
            ys = np.asarray([h["quoted_spread_bps"] for h in pts])
            ax.scatter(xs, ys, s=18, alpha=0.7, c="#2c5f7c" if book == "liquid" else "#b07d4f")
            if xs.size >= 3 and np.nanstd(xs) > 0:
                coef = np.polyfit(xs[np.isfinite(xs) & np.isfinite(ys)], ys[np.isfinite(xs) & np.isfinite(ys)], 1)
                xline = np.linspace(np.nanmin(xs), np.nanmax(xs), 50)
                ax.plot(xline, coef[0] * xline + coef[1], color="crimson", lw=1.5)
                ax.set_title(f"{book} hours (slope={coef[0]:.2f})")
            else:
                ax.set_title(f"{book} hours")
        else:
            ax.set_title(f"{book} (no hours)")
        ax.set_xlabel("rel_tick (bps)")
    axes[0].set_ylabel("quoted spread (bps)")
    fig.suptitle("Hourly interaction: rel_tick × book liquidity (native TOB)", y=1.02)
    fig.tight_layout()
    p = FIGS / "fig_hour_interaction.png"
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    produced.append(p.name)

    # 4) placebo: mid-move hours with flat rel_tick — Δ spread distribution
    fig, ax = plt.subplots(figsize=(7, 4.2))
    # Δ spread for placebo vs non-placebo consecutive hours
    keyed: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for h in hour_rows:
        if h.get("is_synth"):
            continue
        keyed.setdefault((h["venue"], h["day"]), []).append(h)
    placebo_dqs, other_dqs = [], []
    for hrs in keyed.values():
        hrs = sorted(hrs, key=lambda z: z["hour_id"])
        for i in range(1, len(hrs)):
            dqs = hrs[i]["quoted_spread_bps"] - hrs[i - 1]["quoted_spread_bps"]
            if hrs[i].get("placebo_mid_move"):
                placebo_dqs.append(dqs)
            else:
                other_dqs.append(dqs)
    if placebo_dqs:
        ax.hist(placebo_dqs, bins=20, alpha=0.75, label=f"placebo mid-move (n={len(placebo_dqs)})", color="#b07d4f")
    if other_dqs:
        ax.hist(other_dqs, bins=20, alpha=0.45, label=f"other hours (n={len(other_dqs)})", color="#2c5f7c")
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlabel("Δ quoted_spread_bps (hour)")
    ax.set_ylabel("count")
    ax.set_title("Placebo: mid moves with flat rel_tick — spread still moves?")
    ax.legend(fontsize=8)
    fig.tight_layout()
    p = FIGS / "fig_placebo_mid_move.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    produced.append(p.name)

    # 5) make/take: rho bars
    fig, ax = plt.subplots(figsize=(6, 3.8))
    books = ["liquid", "mid", "less_liquid"]
    rhos = [make_take.get(b, {}).get("rho_drel_undercut", np.nan) for b in books]
    ax.bar(books, rhos, color=["#2c5f7c", "#8a8a8a", "#b07d4f"])
    ax.axhline(0, color="gray", lw=0.8)
    ax.set_ylabel("ρ(Δrel_tick, undercut_rate)")
    ax.set_title("Make/take proxy: undercut responds to Δrel_tick?")
    for i, b in enumerate(books):
        n = make_take.get(b, {}).get("n", 0)
        ax.text(i, 0, f"n={n}", ha="center", va="bottom", fontsize=8)
    fig.tight_layout()
    p = FIGS / "fig_make_take_rho.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    produced.append(p.name)

    # 6) depth vs rel_tick by tercile
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for book, c in (("liquid", "#2c5f7c"), ("less_liquid", "#b07d4f"), ("mid", "#8a8a8a")):
        sub = [r for r in ok if r.get("book_liq") == book and not r.get("is_synth")]
        if not sub:
            continue
        ax.scatter(
            [r["rel_tick"] * 1e4 for r in sub],
            [np.log10(max(r["bbo_depth"], 1e-12)) for r in sub],
            c=c,
            label=book,
            s=55,
        )
    ax.set_xlabel("rel_tick (bps)")
    ax.set_ylabel("log10 BBO depth")
    ax.set_title("BBO depth vs relative tick by liquidity tercile")
    ax.legend(fontsize=8)
    fig.tight_layout()
    p = FIGS / "fig_depth_vs_rel_tick.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    produced.append(p.name)

    return produced


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    panel_path = BOOK / "out" / "pass1" / "panel.json"
    if panel_path.is_file():
        days = json.loads(panel_path.read_text()).get("days") or ["2026-09-26", "2026-09-27", "2026-09-30"]
    else:
        days = ["2026-09-26", "2026-09-27", "2026-09-30"]

    day_rows, hour_rows = load_rows(days)
    classified = liquid_book_classifier(
        [r for r in day_rows if r.get("tob_ok") and np.isfinite(r.get("quoted_spread_bps") or np.nan)],
        by="quoted_spread_bps",
    )
    # merge classification back
    key_to_book = {(r["venue"], r["day"]): r for r in classified}
    for r in day_rows:
        k = (r.get("venue"), r.get("day"))
        if k in key_to_book:
            r["book_liq"] = key_to_book[k].get("book_liq")
            r["liq_tercile"] = key_to_book[k].get("liq_tercile")

    het = het_by_tercile(classified)
    make_take = make_take_hypothesis(hour_rows, classified)

    # placebo summary
    n_placebo = sum(1 for h in hour_rows if h.get("placebo_mid_move") and not h.get("is_synth"))
    placebo_dqs = []
    keyed: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for h in hour_rows:
        if h.get("is_synth"):
            continue
        keyed.setdefault((h["venue"], h["day"]), []).append(h)
    for hrs in keyed.values():
        hrs = sorted(hrs, key=lambda z: z["hour_id"])
        for i in range(1, len(hrs)):
            if hrs[i].get("placebo_mid_move"):
                placebo_dqs.append(hrs[i]["quoted_spread_bps"] - hrs[i - 1]["quoted_spread_bps"])

    figs = save_figs(day_rows, hour_rows, classified, het, make_take)

    summary = {
        "symbol": SYMBOL,
        "days": days,
        "venues": list(CORE_VENUES),
        "n_day_rows": len(day_rows),
        "n_hour_rows": len(hour_rows),
        "n_synth_days": sum(1 for r in day_rows if r.get("is_synth")),
        "het": het,
        "make_take": make_take,
        "placebo": {
            "n_hours_flagged": n_placebo,
            "mean_abs_dqs_bps": float(np.mean(np.abs(placebo_dqs))) if placebo_dqs else float("nan"),
            "mean_dqs_bps": float(np.mean(placebo_dqs)) if placebo_dqs else float("nan"),
            "rule": "mid_range≥5bps and rel_tick_range/rel_tick < 2%",
        },
        "figs": figs,
        "note_kraken": "Kraken TOB often warehouse:trade_synth — labeled is_synth; excluded from make/take & placebo native tests",
        "day_rows": day_rows,
        "hour_rows_sample": hour_rows[:40],
        "n_hour_rows_full": len(hour_rows),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    # full hour rows separately (lighter main)
    (OUT / "hour_rows.json").write_text(json.dumps(hour_rows, indent=2, default=str))
    print("wrote", OUT / "summary.json", "figs", figs)


if __name__ == "__main__":
    main()
