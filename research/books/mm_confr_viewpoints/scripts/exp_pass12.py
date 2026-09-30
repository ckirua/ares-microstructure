#!/usr/bin/env python3
"""Pass-1 + Pass-2 empirics for mm_confr_viewpoints (all locked packages).

ETH (then optional BTC) on HL + Deribit + Kraken. Writes out/ JSON, updates
chapter EXP_REPORT / CANDIDATES, and feeds hardening.

ClickHouse MCP banned.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(Path("/home/dev/lab/lab-n2070/warehouse/src")))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path("/home/dev/srv/ares-startarb") / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import (  # noqa: E402
    CORE_VENUES,
    ensure_env,
    load_day_trades,
    load_tob_any,
    normalize_underlying,
    resolve_days,
)
from research.lib.continuous import ofi_continuous, trade_intensity  # noqa: E402
from research.lib.markout import trade_markouts  # noqa: E402
from research.lib.stats import spearman_r  # noqa: E402
from research.lib.ticksize import (  # noqa: E402
    cross_venue_tau_gap,
    expected_sign_matrix,
    fama_macbeth_slope,
    frac_one_tick,
    grid_pressure_feature,
    liquid_book_classifier,
    mq_vector,
    relative_tick,
    sign_scorecard,
    spread_in_ticks,
    spread_leeway,
    tick_constrained,
    undercutting_proxy,
    venue_tick,
)

OUT = BOOK / "out"


def _json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str))


def build_day_row(symbol: str, day: str, venue: str, *, max_files: int) -> dict[str, Any]:
    ensure_env()
    rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
    tape = rec["tape"]
    px = np.asarray(tape["px"], dtype=np.float64)
    qty = np.asarray(tape["qty"], dtype=np.float64)
    ts = np.asarray(tape["ts"], dtype=np.int64)
    side = np.asarray(tape["side"], dtype=np.float64)

    tob_err = None
    tob: dict[str, Any] | None
    try:
        tob = load_tob_any(venue, symbol, day)
    except Exception as exc:  # noqa: BLE001
        tob = None
        tob_err = f"{type(exc).__name__}: {exc}"

    prices_for_tick = px
    if tob is not None and "trade_synth" not in str(tob.get("source", "")):
        prices_for_tick = np.concatenate(
            [np.asarray(tob["bid"], dtype=np.float64), np.asarray(tob["ask"], dtype=np.float64)]
        )
    # Venue-known ticks when inference from synth quotes is unreliable.
    # Kraken **spot** USD tick ≈0.01 ETH / 0.1 BTC; futures PF_* often 0.05/0.1 — only
    # pin spot when TOB is native spot L2 (not trade_synth).
    _KNOWN = {
        "ETH": {"hyperliquid": 0.1, "deribit": 0.05},
        "BTC": {"hyperliquid": 1.0, "deribit": 0.5},
    }
    _KRAKEN_SPOT_TAU = {"ETH": 0.01, "BTC": 0.1, "SOL": 0.01}
    known = dict(_KNOWN.get(normalize_underlying(symbol), {}))
    tob_is_spot = (
        tob is not None
        and venue == "kraken"
        and (
            str(tob.get("market") or "") == "spot"
            or "spot_l2" in str(tob.get("source") or "").lower()
            or "kraken_spot" in str(tob.get("source") or "").lower()
        )
        and not bool(tob.get("is_synth"))
    )
    if tob_is_spot:
        known["kraken"] = _KRAKEN_SPOT_TAU.get(normalize_underlying(symbol), 0.01)
    vt = venue_tick(venue, prices=prices_for_tick, known_ticks=known if venue in known else None)
    # If Kraken inferred absurdly small vs mid, fall back to 0.05 / 0.01 heuristics from trade grid
    tau = float(vt["tau"])
    if venue == "kraken" and (not np.isfinite(tau) or tau < 1e-4):
        mid_m = float(np.nanmedian(px[px > 0])) if px.size else float("nan")
        # prefer inferred from trades only
        vt2 = venue_tick(venue, prices=px)
        if np.isfinite(vt2["tau"]) and vt2["tau"] >= 1e-4:
            vt, tau = vt2, float(vt2["tau"])
        elif np.isfinite(mid_m) and mid_m > 0:
            # Kraken PF ETH often 0.05 or 0.1 — pick closest matching trade increments ≥1e-4
            fallback = _KRAKEN_SPOT_TAU.get(normalize_underlying(symbol), 0.05) if tob_is_spot else 0.05
            vt = {
                "venue": "kraken",
                "tau": fallback,
                "inferred": vt.get("inferred"),
                "catalog_tick": None,
                "source": "known_fallback_spot" if tob_is_spot else "known_fallback",
            }
            tau = fallback

    mq: dict[str, float]
    constraint: dict[str, Any] = {}
    undercut: dict[str, float] = {}
    grid: dict[str, float] = {}
    intensity = float("nan")
    ofi_corr = float("nan")
    markout_bps = float("nan")
    hour_rows: list[dict[str, Any]] = []

    if tob is not None:
        mq = mq_vector(
            bid=tob["bid"],
            ask=tob["ask"],
            bid_sz=tob.get("bid_sz"),
            ask_sz=tob.get("ask_sz"),
            mid=tob.get("mid"),
            tau=tau if np.isfinite(tau) else None,
            trade_qty=qty,
            trade_px=px,
        )
        st = spread_in_ticks(tob["bid"], tob["ask"], tau) if np.isfinite(tau) else np.array([])
        constrained = tick_constrained(st, max_ticks=2.0) if st.size else False
        if isinstance(constrained, np.ndarray):
            frac_c = float(np.mean(constrained)) if constrained.size else float("nan")
        else:
            frac_c = float(constrained)
        constraint = {
            "frac_constrained_2tick": frac_c,
            "frac_one_tick": frac_one_tick(st) if st.size else float("nan"),
            "spread_leeway": spread_leeway(st) if st.size else float("nan"),
            "median_spread_ticks": float(np.nanmedian(st)) if st.size else float("nan"),
            "tick_constrained_day": bool(np.isfinite(frac_c) and frac_c >= 0.5),
            "tob_source": tob.get("source"),
            "tob_table": tob.get("table"),
        }
        undercut = undercutting_proxy(tob["mid"], tob["bid"], tob["ask"], tau)
        grid = grid_pressure_feature(tob["mid"], tau)
        try:
            ofi = ofi_continuous(
                tob["ts"], tob["bid"], tob["ask"], tob["bid_sz"], tob["ask_sz"], bar_ns=60_000_000_000
            )
            ofi_corr = float(ofi.get("corr_ofi_ret", float("nan")))
            ti = trade_intensity(ts, bar_ns=60_000_000_000)
            intensity = float(ti.get("mean_lambda", float("nan")))
            mo = trade_markouts(ts, px, side, tob["ts"], tob["mid"], horizons_ms=(1000, 5000))
            by_h = mo.get("by_horizon") or {}
            if "1000" in by_h:
                markout_bps = float(by_h["1000"].get("mean_bps", float("nan")))
            # hourly panel for FM
            from research.lib.spreads import quoted_spread_bps as qsb
            from research.lib.ticksize import panel_hour_buckets

            qs = qsb(tob["bid"], tob["ask"], mid=tob["mid"])
            rt = relative_tick(tau, tob["mid"], as_bps=False)
            depth = np.asarray(tob["bid_sz"], dtype=np.float64) + np.asarray(tob["ask_sz"], dtype=np.float64)
            hour_rows = panel_hour_buckets(
                tob["ts"],
                {"quoted_spread_bps": qs, "rel_tick": np.asarray(rt, dtype=np.float64), "bbo_depth": depth},
            )
            for hr in hour_rows:
                hr["day"] = day
                hr["venue"] = venue
                hr["symbol"] = symbol
        except Exception as exc:  # noqa: BLE001
            constraint["info_join_error"] = f"{type(exc).__name__}: {exc}"
    else:
        mq = mq_vector(trade_qty=qty, trade_px=px, tau=tau if np.isfinite(tau) else None)
        if np.isfinite(tau) and px.size and np.nanmedian(px) > 0:
            mid_m = float(np.nanmedian(px))
            mq["mid"] = mid_m
            mq["rel_tick"] = float(relative_tick(tau, mid_m, as_bps=False))
            mq["rel_tick_bps"] = float(relative_tick(tau, mid_m, as_bps=True))
        try:
            ti = trade_intensity(ts, bar_ns=60_000_000_000)
            intensity = float(ti.get("mean_lambda", float("nan")))
        except Exception:
            pass

    ret = np.diff(np.log(np.clip(px[px > 0], 1e-12, None))) if px.size else np.array([])
    ret = ret[np.isfinite(ret)]
    vol = float(np.std(ret) * np.sqrt(max(ret.size, 1))) if ret.size > 10 else float("nan")

    return {
        "venue": venue,
        "symbol": symbol,
        "day": day,
        "completeness": rec["completeness"],
        "instrument": rec.get("instrument"),
        "tau": tau,
        "tau_source": vt["source"],
        "inferred_tau": vt["inferred"],
        "tob_ok": tob is not None,
        "tob_error": tob_err,
        "tob_n": int(tob.get("n", 0)) if tob is not None else 0,
        "tob_source": (tob or {}).get("source"),
        "mq": mq,
        "constraint": constraint,
        "undercut": undercut,
        "grid": grid,
        "vol": vol,
        "intensity": intensity,
        "ofi_corr": ofi_corr,
        "markout_1s_bps": markout_bps,
        "n_trades": int(ts.size),
        "rel_tick": mq.get("rel_tick", float("nan")),
        "rel_tick_bps": mq.get("rel_tick_bps", float("nan")),
        "quoted_spread_bps": mq.get("quoted_spread_bps", float("nan")),
        "relative_spread": mq.get("relative_spread", float("nan")),
        "bbo_depth": mq.get("bbo_depth", float("nan")),
        "volume": mq.get("volume", float("nan")),
        "hour_rows": hour_rows,
    }


def run_panel(symbol: str, days: list[str], *, max_files: int) -> list[dict[str, Any]]:
    rows = []
    for day in days:
        for venue in CORE_VENUES:
            print(f"load {symbol} {venue} {day} …", flush=True)
            try:
                rows.append(build_day_row(symbol, day, venue, max_files=max_files))
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    {
                        "venue": venue,
                        "symbol": symbol,
                        "day": day,
                        "error": f"{type(exc).__name__}: {exc}",
                        "completeness": {"complete": False, "reasons": ["load_error"]},
                        "tob_ok": False,
                        "rel_tick": float("nan"),
                        "quoted_spread_bps": float("nan"),
                        "bbo_depth": float("nan"),
                        "volume": float("nan"),
                    }
                )
    return rows


def flatten_for_fm(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        if r.get("error"):
            continue
        out.append(
            {
                "day": r["day"],
                "venue": r["venue"],
                "symbol": r["symbol"],
                "complete": bool(r.get("completeness", {}).get("complete")),
                "rel_tick": r.get("rel_tick"),
                "rel_tick_bps": r.get("rel_tick_bps"),
                "quoted_spread_bps": r.get("quoted_spread_bps"),
                "relative_spread": r.get("relative_spread"),
                "bbo_depth": r.get("bbo_depth"),
                "volume": r.get("volume"),
                "vol": r.get("vol"),
                "intensity": r.get("intensity"),
                "markout_1s_bps": r.get("markout_1s_bps"),
                "ofi_corr": r.get("ofi_corr"),
                "frac_constrained_2tick": (r.get("constraint") or {}).get("frac_constrained_2tick"),
                "undercut_rate": (r.get("undercut") or {}).get("undercut_rate"),
                "tau": r.get("tau"),
                "tob_ok": r.get("tob_ok"),
                "tob_source": r.get("tob_source"),
            }
        )
    return out


def flatten_hour_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        for hr in r.get("hour_rows") or []:
            out.append(dict(hr))
    return out


def observe_signs_from_panel(flat: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Within-day cross-section: correlate rel_tick with MQ → obs sign for rel_tick_up."""
    by_day: dict[str, list[dict[str, Any]]] = {}
    for r in flat:
        if not r.get("tob_ok"):
            continue
        by_day.setdefault(str(r["day"]), []).append(r)
    # pool all tob rows for Spearman
    xs = np.array([r["rel_tick"] for r in flat if r.get("tob_ok") and np.isfinite(r.get("rel_tick") or np.nan)], dtype=np.float64)
    obs = []
    for metric, key, invert_for_improve in (
        ("relative_spread", "relative_spread", True),
        ("quoted_spread", "quoted_spread_bps", True),
        ("bbo_depth", "bbo_depth", False),
        ("volume", "volume", False),
    ):
        ys = []
        x2 = []
        for r in flat:
            if not r.get("tob_ok"):
                continue
            xv, yv = r.get("rel_tick"), r.get(key)
            try:
                xv, yv = float(xv), float(yv)
            except (TypeError, ValueError):
                continue
            if np.isfinite(xv) and np.isfinite(yv):
                x2.append(xv)
                ys.append(yv)
        if len(x2) < 4:
            obs.append({"regime": "rel_tick_up", "metric": metric, "book": "any", "obs_sign": 0, "rho": float("nan"), "n": len(x2)})
            continue
        rho = spearman_r(np.asarray(x2), np.asarray(ys))
        # for spreads: improve = negative association with rel_tick_up expected (rel spread worsens → rho>0 → obs −1 for improve convention)
        if not np.isfinite(rho):
            s = 0
        elif invert_for_improve:
            # positive rho means spreads widen as rel_tick↑ → worsen → obs_sign −1
            s = -1 if rho > 0.05 else (+1 if rho < -0.05 else 0)
        else:
            s = +1 if rho > 0.05 else (-1 if rho < -0.05 else 0)
        obs.append({"regime": "rel_tick_up", "metric": metric, "book": "any", "obs_sign": s, "rho": rho, "n": len(x2)})
    return obs


def write_overview_preds(matrix: dict, scorecard: dict, rows: list[dict]) -> None:
    complete = [
        f"{r['venue']}/{r['day']}"
        for r in rows
        if r.get("completeness", {}).get("complete")
    ]
    # ch00
    ch = BOOK / "chapters" / "ch00_overview"
    (ch / "EXP_REPORT.md").write_text(
        "\n".join(
            [
                "# ch00_overview — EXP_REPORT",
                "",
                "## Pass 1",
                "- RQs locked: large vs small Δτ; relative tick; liquid vs thin; reading order.",
                f"- Core venues: {', '.join(CORE_VENUES)}.",
                f"- Complete venue-days in slice: {len(complete)} → {complete[:12]}{'…' if len(complete)>12 else ''}",
                "",
                "## Pass 2",
                "- Taxonomy vs mmip `tick.rel_tick_bps` / `spread_leeway` / `frac_one_tick`: descriptors cross-linked; this book owns prediction panels.",
                "- Signal roadmap → DESK_MEMO after hardening.",
                "",
            ]
        )
    )
    (ch / "CANDIDATES.md").write_text(
        "| id | type | lenses | decision | falsifier |\n"
        "|----|------|--------|----------|----------|\n"
        "| `disc.tick_rq_taxonomy` | framing | disc, mm | **Promote** (taxonomy) | conflate with mmip descriptor Promote |\n"
        "| `id.lse_nasdaq_rdd_literal` | id | disc | **Kill** | no sovereign tick ladder in crypto sample |\n"
    )
    (ch / "NOTES.md").write_text(
        (ch / "NOTES.md").read_text().replace("**Status:** `todo`", "**Status:** `exp_run`")
        if "**Status:** `todo`" in (ch / "NOTES.md").read_text()
        else (ch / "NOTES.md").read_text()
    )

    # emp_predictions
    ch = BOOK / "chapters" / "emp_predictions"
    hit = scorecard.get("hit_rate", float("nan"))
    (ch / "EXP_REPORT.md").write_text(
        "\n".join(
            [
                "# emp_predictions — EXP_REPORT",
                "",
                "## Pass 1",
                "- Expected-sign matrix from deck pp. 20–29 in `research.lib.ticksize`.",
                f"- Matrix regimes: {list(matrix['matrix'].keys())}",
                f"- Kill metrics: {matrix.get('kill_metrics')}",
                f"- Sign scorecard (rel_tick_up vs MQ Spearman): hits={scorecard.get('hits')} misses={scorecard.get('misses')} skips={scorecard.get('skips')} hit_rate={hit}",
                "",
                "## Pass 2",
                "- Welfare cells → Kill (unobservable).",
                "- SEC/IPO → out of scope.",
                "- LOB backward-induction stays NOTES-only (no production game sim).",
                "",
                "## Day completeness",
                f"- Complete venue-days: {len(complete)}",
                "",
            ]
        )
    )
    (ch / "CANDIDATES.md").write_text(
        "| id | type | lenses | decision | falsifier |\n"
        "|----|------|--------|----------|----------|\n"
        "| `disc.expected_sign_matrix` | theory | disc, liq | **Hold** | crypto hit_rate fragile on thin Tob panel |\n"
        "| `mm.mq_vector` | metric | mm, liq | **Hold** | L0 total_depth = BBO only |\n"
        "| `id.welfare_tick` | theory | mm | **Kill** | unobservable prefs |\n"
        "| `id.sec_ipo_channel` | id | disc | **Kill** | out of scope |\n"
    )


def write_panel_constraint(flat: list[dict], fm: dict, rows: list[dict]) -> None:
    complete_n = sum(1 for r in rows if r.get("completeness", {}).get("complete"))
    tob_n = sum(1 for r in rows if r.get("tob_ok"))
    # FM time-split
    days = sorted({r["day"] for r in flat})
    early_days = set(days[: max(1, len(days) // 2)])
    late_days = set(days) - early_days
    early = [r for r in flat if r["day"] in early_days]
    late = [r for r in flat if r["day"] in late_days]
    fm_early = fama_macbeth_slope(early, y_key="quoted_spread_bps", x_key="rel_tick") if early else {}
    fm_late = fama_macbeth_slope(late, y_key="quoted_spread_bps", x_key="rel_tick") if late else {}

    ch = BOOK / "chapters" / "rel_tick_panel"
    (ch / "EXP_REPORT.md").write_text(
        "\n".join(
            [
                "# rel_tick_panel — EXP_REPORT",
                "",
                "## Pass 1",
                f"- FM mean_slope(quoted_spread_bps ~ rel_tick) = {fm.get('quoted_spread_bps', {}).get('mean_slope')} t={fm.get('quoted_spread_bps', {}).get('t')} n_groups={fm.get('quoted_spread_bps', {}).get('n_groups')}",
                f"- FM mean_slope(bbo_depth ~ rel_tick) = {fm.get('bbo_depth', {}).get('mean_slope')} t={fm.get('bbo_depth', {}).get('t')}",
                f"- FM mean_slope(volume ~ rel_tick) = {fm.get('volume', {}).get('mean_slope')} t={fm.get('volume', {}).get('t')}",
                f"- Complete venue-days: {complete_n}; TOB venue-days: {tob_n}",
                "",
                "## Pass 2",
                f"- Time-split FM quoted_spread early t={fm_early.get('t')} late t={fm_late.get('t')}",
                "- Cross-link mmip `tick.rel_tick_bps` as descriptor — panel slope is this book's object.",
                "- Markout vs rel_tick quartile: see out/pass1/panel.json markout fields.",
                "",
            ]
        )
    )
    # gate: need finite t and consistent early/late sign for Promote
    t = fm.get("quoted_spread_bps", {}).get("t", float("nan"))
    te, tl = fm_early.get("t", float("nan")), fm_late.get("t", float("nan"))
    consistent = (
        np.isfinite(t)
        and abs(t) >= 1.5
        and np.isfinite(te)
        and np.isfinite(tl)
        and (te * tl > 0)
    )
    decision = "Hold"  # prefer Hold unless strong — Promote only after hardening bootstrap
    (ch / "CANDIDATES.md").write_text(
        "| id | type | lenses | decision | falsifier |\n"
        "|----|------|--------|----------|----------|\n"
        f"| `liq.fm_rel_tick_spread` | panel | liq, disc | **{decision}** | time-split early/late t={te}/{tl}; consistent={consistent} |\n"
        "| `liq.fm_rel_tick_depth` | panel | liq | **Hold** | thin TOB cross-section |\n"
        "| `info.markout_by_rel_tick` | info | info, exec | **Hold** | need denser markout join |\n"
    )
    # update NOTES status
    txt = (ch / "NOTES.md").read_text()
    (ch / "NOTES.md").write_text(txt.replace("**Status:** `todo`", "**Status:** `iterate`"))

    # tick_constraint
    fracs = [
        float((r.get("constraint") or {}).get("frac_constrained_2tick", np.nan))
        for r in rows
        if r.get("tob_ok")
    ]
    fracs_f = [x for x in fracs if np.isfinite(x)]
    under = [
        float((r.get("undercut") or {}).get("undercut_rate", np.nan))
        for r in rows
        if r.get("tob_ok")
    ]
    under_f = [x for x in under if np.isfinite(x)]
    ch = BOOK / "chapters" / "tick_constraint"
    (ch / "EXP_REPORT.md").write_text(
        "\n".join(
            [
                "# tick_constraint — EXP_REPORT",
                "",
                "## Pass 1",
                f"- TOB venue-days with constraint metric: {len(fracs_f)}",
                f"- Median frac_constrained_2tick: {float(np.median(fracs_f)) if fracs_f else float('nan')}",
                f"- Median undercut_rate: {float(np.median(under_f)) if under_f else float('nan')}",
                "- Cross-link mmip `tick.frac_one_tick` / `spread_leeway` (descriptor overlap).",
                "",
                "## Pass 2",
                "- Label: *fragility monitor* when frac_constrained high + undercut bursts; *exec throttle* only if markout worsens — Hold pending denser OFI.",
                "",
            ]
        )
    )
    (ch / "CANDIDATES.md").write_text(
        "| id | type | lenses | decision | falsifier |\n"
        "|----|------|--------|----------|----------|\n"
        "| `exec.tick_constrained_flag` | regime | exec, disc | **Hold** | overlaps mmip frac_one_tick — need incremental falsifier |\n"
        "| `exec.undercut_rate` | proxy | exec, mm | **Hold** | L0 tighten ≠ true undercut queue |\n"
    )
    txt = (ch / "NOTES.md").read_text()
    (ch / "NOTES.md").write_text(txt.replace("**Status:** `todo`", "**Status:** `iterate`"))


def write_liq_xvenue(rows: list[dict], flat: list[dict]) -> dict[str, Any]:
    classified = liquid_book_classifier(
        [r for r in flat if r.get("tob_ok") and np.isfinite(r.get("quoted_spread_bps") or np.nan)],
        by="quoted_spread_bps",
    )
    # heterogeneous: Spearman rel_tick vs spread within liquid vs less_liquid
    het = {}
    for book in ("liquid", "less_liquid"):
        sub = [r for r in classified if r.get("book_liq") == book]
        xs = [float(r["rel_tick"]) for r in sub if np.isfinite(float(r.get("rel_tick") or np.nan))]
        ys = [float(r["quoted_spread_bps"]) for r in sub if np.isfinite(float(r.get("quoted_spread_bps") or np.nan))]
        n = min(len(xs), len(ys))
        het[book] = {
            "n": n,
            "rho_rel_tick_spread": spearman_r(np.asarray(xs[:n]), np.asarray(ys[:n])) if n >= 3 else float("nan"),
        }

    # placebo: correlate mid level with spread after residualizing rel_tick roughly —
    # use vol as placebo driver that shouldn't match sign matrix
    placebo_xs = [float(r["vol"]) for r in flat if r.get("tob_ok") and np.isfinite(r.get("vol") or np.nan)]
    placebo_ys = [
        float(r["quoted_spread_bps"])
        for r in flat
        if r.get("tob_ok") and np.isfinite(r.get("quoted_spread_bps") or np.nan)
    ]
    n = min(len(placebo_xs), len(placebo_ys))
    placebo_rho = spearman_r(np.asarray(placebo_xs[:n]), np.asarray(placebo_ys[:n])) if n >= 3 else float("nan")

    ch = BOOK / "chapters" / "liq_book_split"
    (ch / "EXP_REPORT.md").write_text(
        "\n".join(
            [
                "# liq_book_split — EXP_REPORT",
                "",
                "## Pass 1",
                f"- Tercile classifier on quoted_spread_bps; liquid n={het.get('liquid',{}).get('n')} less_liquid n={het.get('less_liquid',{}).get('n')}",
                f"- rho(rel_tick, spread) liquid={het.get('liquid',{}).get('rho_rel_tick_spread')} thin={het.get('less_liquid',{}).get('rho_rel_tick_spread')}",
                "",
                "## Pass 2",
                f"- Placebo rho(vol, spread)={placebo_rho} (expect nonzero; not a clean placebo for rel-tick channel).",
                "- Exec make/take hypothesis: Hold — need constraint-relax event study.",
                "",
            ]
        )
    )
    (ch / "CANDIDATES.md").write_text(
        "| id | type | lenses | decision | falsifier |\n"
        "|----|------|--------|----------|----------|\n"
        "| `liq.book_tercile_het` | panel | liq | **Hold** | small n per tercile; placebo weak |\n"
    )
    txt = (ch / "NOTES.md").read_text()
    (ch / "NOTES.md").write_text(txt.replace("**Status:** `todo`", "**Status:** `iterate`"))

    # xvenue
    xvenue_days = {}
    for r in rows:
        if r.get("error"):
            continue
        xvenue_days.setdefault(r["day"], {})[r["venue"]] = r
    pair_summaries = []
    for day, by_v in sorted(xvenue_days.items()):
        taus = {v: float(by_v[v]["tau"]) for v in by_v if np.isfinite(by_v[v].get("tau") or np.nan)}
        mids = {
            v: float(by_v[v].get("mq", {}).get("mid") or by_v[v].get("rel_tick") and (by_v[v]["tau"] / by_v[v]["rel_tick"]) or np.nan)
            for v in by_v
        }
        # fix mid extraction
        mids = {}
        for v, rec in by_v.items():
            mid = (rec.get("mq") or {}).get("mid")
            if mid and np.isfinite(mid):
                mids[v] = float(mid)
        gaps = cross_venue_tau_gap(taus, mid_by_venue=mids or None)
        # MQ delta vs tau gap for pairs with TOB
        for p in gaps.get("pairs", []):
            va, vb = p["a"], p["b"]
            ra, rb = by_v.get(va, {}), by_v.get(vb, {})
            if not (ra.get("tob_ok") and rb.get("tob_ok")):
                continue
            pair_summaries.append(
                {
                    "day": day,
                    **p,
                    "spread_gap_bps": float(ra["quoted_spread_bps"] - rb["quoted_spread_bps"])
                    if np.isfinite(ra.get("quoted_spread_bps") or np.nan) and np.isfinite(rb.get("quoted_spread_bps") or np.nan)
                    else float("nan"),
                    "depth_gap": float(ra["bbo_depth"] - rb["bbo_depth"])
                    if np.isfinite(ra.get("bbo_depth") or np.nan) and np.isfinite(rb.get("bbo_depth") or np.nan)
                    else float("nan"),
                    "grid_pressure_a": (ra.get("grid") or {}).get("pressure_std"),
                    "grid_pressure_b": (rb.get("grid") or {}).get("pressure_std"),
                }
            )

    # concordance: same-day ranking of venues by rel_tick_bps
    concord_hits = 0
    concord_n = 0
    for day, by_v in xvenue_days.items():
        vals = [(v, by_v[v].get("rel_tick_bps")) for v in by_v if by_v[v].get("tob_ok")]
        vals = [(v, float(x)) for v, x in vals if x is not None and np.isfinite(float(x))]
        if len(vals) >= 2:
            concord_n += 1
            # "concordant" if max/min rel-tick ratio stable definition — flag large gap
            xs = [x for _, x in vals]
            if max(xs) > 0 and (max(xs) - min(xs)) / max(xs) < 0.5:
                concord_hits += 1

    ch = BOOK / "chapters" / "xvenue_tick"
    (ch / "EXP_REPORT.md").write_text(
        "\n".join(
            [
                "# xvenue_tick — EXP_REPORT",
                "",
                "## Pass 1",
                f"- Cross-venue τ-gap pair-days with dual TOB: {len(pair_summaries)}",
                f"- Sample pairs (head): {json.dumps(pair_summaries[:5], default=str)}",
                "",
                "## Pass 2",
                f"- Rel-tick concordance days (range/max < 50%): {concord_hits}/{concord_n}",
                "- FEI/Epps around high rel-tick: deferred (Hold) — needs aligned multi-venue clocks.",
                "- SOR: prefer venue with lower rel_tick_bps when spreads comparable — Hold pending exec PnL.",
                "",
            ]
        )
    )
    (ch / "CANDIDATES.md").write_text(
        "| id | type | lenses | decision | falsifier |\n"
        "|----|------|--------|----------|----------|\n"
        "| `frag.xvenue_tau_gap` | qe | frag, disc | **Hold** | τ often inferred; catalog decimals missing |\n"
        "| `frag.grid_pressure` | feature | disc, liq | **Hold** | residual MQ Δ needs FE |\n"
        "| `exec.sor_rel_tick` | policy | exec | **Hold** | no fill-quality label in slice |\n"
        "| `id.vanity_price_rdd` | id | disc | **Kill** | no discrete tick schedule thresholds |\n"
    )
    txt = (ch / "NOTES.md").read_text()
    (ch / "NOTES.md").write_text(txt.replace("**Status:** `todo`", "**Status:** `iterate`"))

    return {"het": het, "placebo_rho": placebo_rho, "pair_summaries": pair_summaries, "concord": {"hits": concord_hits, "n": concord_n}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--days", nargs="*", default=None)
    ap.add_argument("--n-days", type=int, default=3)
    ap.add_argument("--max-files", type=int, default=24)
    args = ap.parse_args()

    ensure_env()
    days = args.days or resolve_days(None, venue="hyperliquid", n=args.n_days)
    print(f"days={days}", flush=True)

    matrix = expected_sign_matrix()
    _json(OUT / "pass1" / "expected_sign_matrix.json", matrix)

    rows = run_panel(args.symbol, days, max_files=args.max_files)
    _json(OUT / "pass1" / "panel.json", {"symbol": args.symbol, "days": days, "rows": rows})

    flat = flatten_for_fm(rows)
    hour_flat = flatten_hour_rows(rows)
    fm = {
        "quoted_spread_bps": fama_macbeth_slope(flat, y_key="quoted_spread_bps", x_key="rel_tick"),
        "bbo_depth": fama_macbeth_slope(flat, y_key="bbo_depth", x_key="rel_tick"),
        "volume": fama_macbeth_slope(flat, y_key="volume", x_key="rel_tick"),
        "relative_spread": fama_macbeth_slope(flat, y_key="relative_spread", x_key="rel_tick"),
        "quoted_spread_bps_by_venue": fama_macbeth_slope(
            flat, y_key="quoted_spread_bps", x_key="rel_tick", group_key="venue"
        ),
        "hour_quoted_spread_bps": fama_macbeth_slope(
            hour_flat, y_key="quoted_spread_bps", x_key="rel_tick", group_key="day"
        ),
        "hour_bbo_depth": fama_macbeth_slope(
            hour_flat, y_key="bbo_depth", x_key="rel_tick", group_key="day"
        ),
    }
    _json(OUT / "pass1" / "fm.json", fm)

    obs = observe_signs_from_panel(flat)
    scorecard = sign_scorecard(obs)
    _json(OUT / "pass1" / "sign_scorecard.json", {"observed": obs, "scorecard": scorecard})

    write_overview_preds(matrix, scorecard, rows)
    write_panel_constraint(flat, fm, rows)
    xmeta = write_liq_xvenue(rows, flat)
    _json(OUT / "pass2" / "liq_xvenue.json", xmeta)

    # completeness summary
    comp = []
    for r in rows:
        c = r.get("completeness") or {}
        comp.append(
            {
                "venue": r.get("venue"),
                "day": r.get("day"),
                "complete": c.get("complete"),
                "n": c.get("n"),
                "coverage": c.get("coverage"),
                "reasons": c.get("reasons"),
                "tob_ok": r.get("tob_ok"),
                "tau": r.get("tau"),
                "tau_source": r.get("tau_source"),
            }
        )
    _json(OUT / "pass1" / "completeness.json", comp)
    print("done", json.dumps({"n_rows": len(rows), "complete": sum(1 for x in comp if x.get("complete")), "tob": sum(1 for x in comp if x.get("tob_ok"))}, indent=2))


if __name__ == "__main__":
    main()
