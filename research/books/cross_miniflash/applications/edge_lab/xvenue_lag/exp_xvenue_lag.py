#!/usr/bin/env python3
"""X-venue lag taker — when SSM/Nanex fires on A, take on lagging B.

Hypothesis
----------
HL↔Deribit↔Kraken crashes are *not* synchronous (concordance Hold). When gated
SSM (optionally Nanex∩SSM) fires on venue A, ride crash direction on venue B if
B has not yet co-fired — capture B's catch-up markout after costs.

Honesty: research_sim on real multi-venue tape · 2bps one-way / 4bps RT ·
entry at signal_end + latency_ms · no fantasy TOB fills · ClickHouse MCP banned.
Own folder only — does not edit edge_lab core.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

LAB = Path(__file__).resolve().parent
EDGE = LAB.parent
APP = EDGE.parent
BOOK = APP.parent
ROOT = BOOK.parents[2]
SCRIPTS_APP = APP / "scripts"
SCRIPTS_BOOK = BOOK / "scripts"
STARTARB = Path("/home/dev/srv/ares-startarb")
WAREHOUSE_SRC = Path("/home/dev/lab/lab-n2070/warehouse/src")
OUT = LAB / "out"
FIG = OUT / "figs"

for p in (
    str(ROOT),
    str(SCRIPTS_APP),
    str(SCRIPTS_BOOK),
    str(STARTARB / "src"),
    str(WAREHOUSE_SRC),
    str(APP),
):
    if p not in sys.path:
        sys.path.insert(0, p)

from _common import (  # noqa: E402
    FRICTION_BPS,
    early_late_by_day,
    flatten_events,
    mean_ci,
    save_fig,
    save_json,
)
from _data import CORE_VENUES, ensure_env, load_core_venues_day  # noqa: E402
from research.lib.crash import xvenue_event_concordance  # noqa: E402
from research.lib.epps import corr_vs_lag  # noqa: E402
from research.lib.fei import fei  # noqa: E402

NS = 1_000_000_000
RT_FRICTION = 2.0 * FRICTION_BPS
PANEL_ROWS = APP / "out" / "event_panel" / "panel_rows.json"
PANEL_META = APP / "out" / "event_panel" / "panel_meta.json"
HORIZONS_S = (1.0, 5.0)
DEFAULT_LATENCY_MS = 100.0
DEFAULT_SLACK_S = 2.0  # B co-fire window — tighter than desk concordance 5s

HONESTY = {
    "slice": "research_sim_on_real_multi_venue_tape",
    "live_orders": False,
    "fills": "synthetic_unit_size_x_signed_B_tape_mo",
    "entry": "signal_end_plus_latency_ms",
    "alpha_claim": False,
    "costs_bps_one_way": FRICTION_BPS,
    "costs_bps_round_trip": RT_FRICTION,
    "clickhouse_mcp": False,
    "book_objects": [
        "frag.xvenue_crash_concord",
        "info.nanex_subset_of_ssm",
        "frag.fei_volume_3venue",
        "epps.crash_window_corr",
    ],
    "note": "Concordance Hold is the *enabler* (asynchronous fires), not a hedge trigger.",
}


def jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, float)):
        x = float(obj)
        return x if np.isfinite(x) else None
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if obj is None:
        return None
    return str(obj)


def _boot_mean(arr: np.ndarray, *, seed: int = 0, n_boot: int = 800) -> dict[str, float]:
    a = np.asarray(arr, dtype=np.float64)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return {"n": 0, "mean": float("nan"), "lo": float("nan"), "hi": float("nan"), "sd": float("nan")}
    ci = mean_ci(a, n_boot=n_boot, seed=seed)
    return {
        "n": int(ci.get("n", a.size)),
        "mean": float(ci.get("point", np.nanmean(a))),
        "lo": float(ci.get("lo", float("nan"))),
        "hi": float(ci.get("hi", float("nan"))),
        "sd": float(np.std(a, ddof=1)) if a.size > 1 else 0.0,
    }


def _ci_excludes_zero(ci: dict[str, float]) -> bool:
    lo, hi = ci.get("lo"), ci.get("hi")
    if lo is None or hi is None or not np.isfinite(lo) or not np.isfinite(hi):
        return False
    return (lo > 0 and hi > 0) or (lo < 0 and hi < 0)


def _sign_stable(early_mean: float, late_mean: float) -> bool:
    if not np.isfinite(early_mean) or not np.isfinite(late_mean):
        return False
    if early_mean == 0 or late_mean == 0:
        return False
    return (early_mean > 0) == (late_mean > 0)


def verdict(
    *,
    name: str,
    n: int,
    pnl_ci: dict[str, float],
    early_mean: float,
    late_mean: float,
    friction_cleared: bool,
    min_n: int = 30,
    promote_scope: str = "xvenue_lag_taker",
) -> dict[str, Any]:
    excludes0 = _ci_excludes_zero(pnl_ci)
    stable = _sign_stable(early_mean, late_mean)
    mean = float(pnl_ci.get("mean", float("nan")))
    if n < min_n:
        decision = "Hold"
        why = f"underpowered n={n} < {min_n}"
    elif np.isfinite(mean) and mean <= 0 and excludes0:
        decision = "Kill"
        why = f"net PnL CI entirely ≤0 after costs (mean={mean:.2f})"
    elif not excludes0:
        decision = "Kill" if (np.isfinite(mean) and mean <= 0) else "Hold"
        why = (
            "net PnL CI includes 0 after costs"
            if decision == "Hold"
            else "mean net PnL ≤ 0 and CI includes 0"
        )
    elif not stable:
        decision = "Kill"
        why = f"time-split sign flip early={early_mean:.2f} late={late_mean:.2f}"
    elif not friction_cleared:
        decision = "Hold"
        why = "CI excludes 0 but effect does not clear round-trip friction bar"
    else:
        decision = "Promote"
        why = f"net CI excludes 0, time-split stable, friction cleared ({promote_scope})"
    return {
        "id": name,
        "decision": decision,
        "why": why,
        "n": n,
        "pnl_ci_excludes_0": excludes0,
        "time_split_stable": stable,
        "friction_cleared": friction_cleared,
        "promote_scope": promote_scope if decision == "Promote" else None,
        "honesty": "not_live_alpha",
    }


def _asof_px(ts: np.ndarray, px: np.ndarray, t_ns: int) -> float:
    if ts.size == 0:
        return float("nan")
    j = int(np.searchsorted(ts, t_ns, side="right") - 1)
    if j < 0 or j >= px.size:
        return float("nan")
    p = float(px[j])
    return p if np.isfinite(p) and p > 0 else float("nan")


def _markout_bps(
    ts: np.ndarray,
    px: np.ndarray,
    *,
    t0_ns: int,
    horizon_s: float,
    direction: int,
) -> float:
    """Signed continuation markout on take tape from t0 over horizon."""
    p0 = _asof_px(ts, px, t0_ns)
    if not np.isfinite(p0) or direction == 0:
        return float("nan")
    t1 = t0_ns + int(horizon_s * NS)
    p1 = _asof_px(ts, px, t1)
    if not np.isfinite(p1):
        return float("nan")
    return float(direction * (p1 - p0) / p0 * 1e4)


def _overlaps(a0: int, a1: int, b0: int, b1: int, slack_ns: int) -> bool:
    return a0 <= b1 + slack_ns and b0 <= a1 + slack_ns


def _b_already_moved(
    ts_b: np.ndarray,
    px_b: np.ndarray,
    *,
    t_start: int,
    t_end: int,
    direction: int,
    signal_dp_pct: float,
    frac: float = 0.5,
) -> bool:
    """True if B already captured ≥frac of |signal ΔP| by signal end."""
    p0 = _asof_px(ts_b, px_b, t_start)
    p1 = _asof_px(ts_b, px_b, t_end)
    if not np.isfinite(p0) or not np.isfinite(p1) or p0 <= 0:
        return False
    moved_pct = direction * (p1 - p0) / p0 * 100.0  # + if with crash
    thr = abs(float(signal_dp_pct)) * float(frac)
    return bool(np.isfinite(moved_pct) and moved_pct >= thr and thr > 0)


def load_panel() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = json.loads(PANEL_ROWS.read_text())
    meta = json.loads(PANEL_META.read_text()) if PANEL_META.exists() else {}
    return rows, meta


def index_events_by_cell(
    flat: list[dict[str, Any]],
) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    out: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for e in flat:
        out[(e["day"], e["symbol"], e["venue"])].append(e)
    for k in out:
        out[k].sort(key=lambda x: int(x["ts_end"]))
    return out


def load_tapes(
    days: list[str],
    symbols: list[str],
    *,
    quiet: bool = True,
) -> dict[tuple[str, str], dict[str, dict[str, np.ndarray]]]:
    """(day, symbol) → venue → {ts, px}."""
    ensure_env()
    cache: dict[tuple[str, str], dict[str, dict[str, np.ndarray]]] = {}
    for day in days:
        for sym in symbols:
            pack = load_core_venues_day(sym, day, venues=CORE_VENUES, quiet=quiet)
            cell: dict[str, dict[str, np.ndarray]] = {}
            for v, rec in pack["venues"].items():
                if "error" in rec or "tape" not in rec:
                    continue
                tape = rec["tape"]
                cell[v] = {
                    "ts": np.asarray(tape["ts"], dtype=np.int64),
                    "px": np.asarray(tape["px"], dtype=np.float64),
                }
            cache[(day, sym)] = cell
    return cache


def simulate_trades(
    flat: list[dict[str, Any]],
    tapes: dict[tuple[str, str], dict[str, dict[str, np.ndarray]]],
    rows: list[dict[str, Any]],
    *,
    slack_s: float = DEFAULT_SLACK_S,
    latency_ms: float = DEFAULT_LATENCY_MS,
    early: set[str],
    late: set[str],
) -> list[dict[str, Any]]:
    by_cell = index_events_by_cell(flat)
    vol_share: dict[tuple[str, str, str], float] = {}
    fei_cell: dict[tuple[str, str], float] = {}
    hv_cell: dict[tuple[str, str], float] = {}
    for r in rows:
        if "events" not in r:
            continue
        key = (r["day"], r["symbol"], r["venue"])
        vs = (r.get("vol_shares") or {}).get(r["venue"])
        if vs is not None:
            vol_share[key] = float(vs)
        ds = (r["day"], r["symbol"])
        if r.get("FEI") is not None:
            fei_cell[ds] = float(r["FEI"])
        if r.get("H_v") is not None:
            hv_cell[ds] = float(r["H_v"])

    slack_ns = int(slack_s * NS)
    lat_ns = int(latency_ms * 1e6)
    thick = {"deribit", "kraken"}
    trades: list[dict[str, Any]] = []

    for sig in flat:
        day, sym, va = sig["day"], sig["symbol"], sig["venue"]
        tape_pack = tapes.get((day, sym))
        if not tape_pack or va not in tape_pack:
            continue
        t0 = int(sig["ts_start"])
        t1 = int(sig["ts_end"])
        direction = int(sig["direction"])
        if direction == 0:
            continue
        entry_t = t1 + lat_ns
        nest = bool(sig.get("nanex_overlap"))
        inten = int(sig.get("intensity_60s") or 1)

        for vb in CORE_VENUES:
            if vb == va:
                continue
            if vb not in tape_pack:
                continue
            # lag filter: no overlapping gated event on B
            b_evs = by_cell.get((day, sym, vb), [])
            cofire = any(
                _overlaps(t0, t1, int(b["ts_start"]), int(b["ts_end"]), slack_ns) for b in b_evs
            )
            if cofire:
                continue
            ts_b = tape_pack[vb]["ts"]
            px_b = tape_pack[vb]["px"]
            if _b_already_moved(
                ts_b,
                px_b,
                t_start=t0,
                t_end=t1,
                direction=direction,
                signal_dp_pct=float(sig.get("dp_pct") or 0.0),
            ):
                continue

            row: dict[str, Any] = {
                "day": day,
                "symbol": sym,
                "signal_venue": va,
                "take_venue": vb,
                "pair": f"{va}->{vb}",
                "ts_signal_end": t1,
                "ts_entry": entry_t,
                "direction": direction,
                "dp_pct": float(sig.get("dp_pct") or 0.0),
                "z_peak": float(sig.get("z_peak") or float("nan")),
                "intensity_60s": inten,
                "nanex_overlap": nest,
                "vol_share_take": vol_share.get((day, sym, vb), float("nan")),
                "vol_share_sig": vol_share.get((day, sym, va), float("nan")),
                "FEI": fei_cell.get((day, sym), float("nan")),
                "H_v": hv_cell.get((day, sym), float("nan")),
                "cohort": "early" if day in early else ("late" if day in late else "mid"),
                "hl_to_thick": va == "hyperliquid" and vb in thick,
                "any_to_thick": vb in thick,
            }
            ok = True
            for h in HORIZONS_S:
                mo = _markout_bps(ts_b, px_b, t0_ns=entry_t, horizon_s=h, direction=direction)
                row[f"mo_{h:g}s"] = mo
                if not np.isfinite(mo):
                    ok = False
            if not ok:
                continue
            # primary horizon 5s net of RT friction (unit size ride)
            gross = float(row["mo_5s"])
            row["gross_bps"] = gross
            row["cost_bps"] = RT_FRICTION
            row["pnl_bps"] = gross - RT_FRICTION
            # also 1s
            row["pnl_1s_bps"] = float(row["mo_1s"]) - RT_FRICTION
            trades.append(row)

    return trades


def score_rule(
    trades: list[dict[str, Any]],
    *,
    name: str,
    predicate,
    promote_scope: str,
    min_n: int = 30,
    seed: int = 21,
) -> dict[str, Any]:
    sel = [t for t in trades if predicate(t)]
    if not sel:
        empty = {"n": 0, "mean": float("nan"), "lo": float("nan"), "hi": float("nan"), "sd": float("nan")}
        return {
            "id": name,
            "n": 0,
            "pnl_net_bps": empty,
            "gross_bps": empty,
            "mo_5s": empty,
            "mo_1s": empty,
            "early_mean": float("nan"),
            "late_mean": float("nan"),
            "primary_verdict": verdict(
                name=name,
                n=0,
                pnl_ci=empty,
                early_mean=float("nan"),
                late_mean=float("nan"),
                friction_cleared=False,
                min_n=min_n,
                promote_scope=promote_scope,
            ),
            "by_pair": {},
            "n_nest": 0,
        }

    pnls = np.asarray([t["pnl_bps"] for t in sel], dtype=np.float64)
    gross = np.asarray([t["gross_bps"] for t in sel], dtype=np.float64)
    mo5 = np.asarray([t["mo_5s"] for t in sel], dtype=np.float64)
    mo1 = np.asarray([t["mo_1s"] for t in sel], dtype=np.float64)
    ci = _boot_mean(pnls, seed=seed)
    gci = _boot_mean(gross, seed=seed + 1)
    e_pnls = np.asarray([t["pnl_bps"] for t in sel if t["cohort"] == "early"], dtype=np.float64)
    l_pnls = np.asarray([t["pnl_bps"] for t in sel if t["cohort"] == "late"], dtype=np.float64)
    early_m = float(np.nanmean(e_pnls)) if e_pnls.size else float("nan")
    late_m = float(np.nanmean(l_pnls)) if l_pnls.size else float("nan")
    friction_cleared = bool(
        _ci_excludes_zero(ci)
        and ci["mean"] > 0
        and np.isfinite(np.nanmean(gross))
        and float(np.nanmean(gross)) > RT_FRICTION
    )
    by_pair: dict[str, Any] = {}
    for pair in sorted({t["pair"] for t in sel}):
        pp = [t for t in sel if t["pair"] == pair]
        by_pair[pair] = {
            "n": len(pp),
            "pnl_net_bps": _boot_mean(np.asarray([t["pnl_bps"] for t in pp], dtype=np.float64), seed=seed + 3),
            "mo_5s": _boot_mean(np.asarray([t["mo_5s"] for t in pp], dtype=np.float64), seed=seed + 4),
        }

    return {
        "id": name,
        "n": len(sel),
        "n_nest": sum(1 for t in sel if t["nanex_overlap"]),
        "n_early": int(e_pnls.size),
        "n_late": int(l_pnls.size),
        "pnl_net_bps": ci,
        "gross_bps": gci,
        "mo_5s": _boot_mean(mo5, seed=seed + 5),
        "mo_1s": _boot_mean(mo1, seed=seed + 6),
        "early_mean": early_m,
        "late_mean": late_m,
        "friction_cleared": friction_cleared,
        "primary_verdict": verdict(
            name=name,
            n=len(sel),
            pnl_ci=ci,
            early_mean=early_m,
            late_mean=late_m,
            friction_cleared=friction_cleared,
            min_n=min_n,
            promote_scope=promote_scope,
        ),
        "by_pair": by_pair,
    }


def concordance_diag(flat: list[dict[str, Any]], days: list[str], symbols: list[str]) -> dict[str, Any]:
    """Reuse crash.xvenue_event_concordance on panel events (@2s and @5s)."""
    rows_out = []
    for day in days:
        for sym in symbols:
            by_v: dict[str, dict[str, Any]] = {}
            for v in CORE_VENUES:
                evs = [e for e in flat if e["day"] == day and e["symbol"] == sym and e["venue"] == v]
                by_v[v] = {
                    "ts_start": np.asarray([e["ts_start"] for e in evs], dtype=np.int64),
                    "ts_end": np.asarray([e["ts_end"] for e in evs], dtype=np.int64),
                }
            for slack in (2.0, 5.0):
                c = xvenue_event_concordance(by_v, slack_s=slack)
                for pr in c["pairs"]:
                    rows_out.append(
                        {
                            "day": day,
                            "symbol": sym,
                            "slack_s": slack,
                            **{k: pr[k] for k in ("a", "b", "n_a", "n_b", "n_overlap", "jaccard")},
                        }
                    )
    # pooled mean Jaccard by pair@slack
    pooled: dict[str, list[float]] = defaultdict(list)
    for r in rows_out:
        if np.isfinite(r.get("jaccard", float("nan"))):
            pooled[f"{r['a']}_{r['b']}@{r['slack_s']:g}s"].append(float(r["jaccard"]))
    return {
        "rows": rows_out,
        "mean_jaccard": {k: float(np.mean(v)) for k, v in pooled.items()},
    }


def epps_sample(
    tapes: dict[tuple[str, str], dict[str, dict[str, np.ndarray]]],
    flat: list[dict[str, Any]],
    *,
    max_cells: int = 6,
) -> dict[str, Any]:
    """Day Epps @1s vs crash-window Epps for a few cells (diagnostic)."""
    cells = sorted({(d, s) for (d, s) in tapes.keys()})[:max_cells]
    out_rows = []
    for day, sym in cells:
        pack = tapes[(day, sym)]
        if len(pack) < 2:
            continue
        venues = [v for v in CORE_VENUES if v in pack]
        for i in range(len(venues)):
            for j in range(i + 1, len(venues)):
                a, b = venues[i], venues[j]
                day_curve = corr_vs_lag(
                    pack[a]["ts"],
                    pack[a]["px"],
                    pack[b]["ts"],
                    pack[b]["px"],
                    lags_s=(1.0, 5.0),
                )
                # crash windows: ±30s around each signal end on either venue
                evs = [
                    e
                    for e in flat
                    if e["day"] == day and e["symbol"] == sym and e["venue"] in (a, b)
                ]
                crash_corrs = []
                for e in evs[:40]:
                    t_mid = int(e["ts_end"])
                    w0, w1 = t_mid - 30 * NS, t_mid + 30 * NS

                    def _clip(v: str) -> tuple[np.ndarray, np.ndarray]:
                        ts = pack[v]["ts"]
                        px = pack[v]["px"]
                        m = (ts >= w0) & (ts <= w1)
                        return ts[m], px[m]

                    ta, pa = _clip(a)
                    tb, pb = _clip(b)
                    if ta.size < 20 or tb.size < 20:
                        continue
                    c = corr_vs_lag(ta, pa, tb, pb, lags_s=(1.0,))
                    corr = c["curve"][0].get("corr")
                    if corr is not None and np.isfinite(corr):
                        crash_corrs.append(float(corr))
                day_1 = next((pt["corr"] for pt in day_curve["curve"] if abs(pt["lag_s"] - 1.0) < 1e-9), float("nan"))
                out_rows.append(
                    {
                        "day": day,
                        "symbol": sym,
                        "pair": f"{a}_{b}",
                        "epps_day_1s": float(day_1) if day_1 is not None else float("nan"),
                        "epps_crash_1s_mean": float(np.mean(crash_corrs)) if crash_corrs else float("nan"),
                        "n_crash_windows": len(crash_corrs),
                    }
                )
    day_vals = [r["epps_day_1s"] for r in out_rows if np.isfinite(r["epps_day_1s"])]
    crash_vals = [r["epps_crash_1s_mean"] for r in out_rows if np.isfinite(r["epps_crash_1s_mean"])]
    return {
        "rows": out_rows,
        "mean_day_1s": float(np.mean(day_vals)) if day_vals else float("nan"),
        "mean_crash_1s": float(np.mean(crash_vals)) if crash_vals else float("nan"),
    }


def make_figs(summary: dict[str, Any], trades: list[dict[str, Any]]) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    paths: list[str] = []
    FIG.mkdir(parents=True, exist_ok=True)

    # 1) net PnL by rule
    rules = summary["rules"]
    names = list(rules.keys())
    means = [rules[n]["pnl_net_bps"]["mean"] for n in names]
    los = [rules[n]["pnl_net_bps"]["lo"] for n in names]
    his = [rules[n]["pnl_net_bps"]["hi"] for n in names]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    x = np.arange(len(names))
    ax.bar(x, means, color="#2a9d8f", alpha=0.85)
    ax.errorbar(x, means, yerr=[np.array(means) - np.array(los), np.array(his) - np.array(means)], fmt="none", ecolor="k", capsize=3)
    ax.axhline(0, color="k", lw=0.8)
    ax.axhline(-RT_FRICTION, color="#e76f51", ls="--", lw=0.8, label=f"−RT friction ({RT_FRICTION:g}bps)")
    ax.set_xticks(x)
    ax.set_xticklabels([n.replace("TI-xvenue-lag:", "") for n in names], rotation=25, ha="right")
    ax.set_ylabel("net PnL (bps)")
    ax.set_title("X-venue lag taker — net PnL after RT costs")
    ax.legend(fontsize=8)
    p = FIG / "fig_rule_net_pnl.png"
    save_fig(p)
    paths.append(str(p))

    # 2) HL→thick mo histogram
    hl = [t["mo_5s"] for t in trades if t["hl_to_thick"] and np.isfinite(t["mo_5s"])]
    fig, ax = plt.subplots(figsize=(7, 4))
    if hl:
        ax.hist(hl, bins=40, color="#264653", alpha=0.85)
        ax.axvline(float(np.mean(hl)), color="#e9c46a", lw=1.5, label=f"mean={np.mean(hl):.2f}")
        ax.axvline(RT_FRICTION, color="#e76f51", ls="--", label=f"RT={RT_FRICTION:g}")
        ax.legend(fontsize=8)
    ax.set_xlabel("mo@5s on take venue (bps, crash-signed)")
    ax.set_title(f"HL→thick lag takes — n={len(hl)}")
    p = FIG / "fig_hl_thick_mo5_hist.png"
    save_fig(p)
    paths.append(str(p))

    # 3) early/late for primary
    primary = "TI-xvenue-lag:hl_to_thick"
    if primary in rules:
        fig, ax = plt.subplots(figsize=(5.5, 4))
        e_m, l_m = rules[primary]["early_mean"], rules[primary]["late_mean"]
        ax.bar(["early", "late"], [e_m, l_m], color=["#457b9d", "#1d3557"])
        ax.axhline(0, color="k", lw=0.8)
        ax.set_ylabel("mean net PnL (bps)")
        ax.set_title(f"{primary} time-split")
        p = FIG / "fig_hl_thick_time_split.png"
        save_fig(p)
        paths.append(str(p))

    # 4) concordance Jaccard
    cj = summary.get("concordance", {}).get("mean_jaccard") or {}
    if cj:
        fig, ax = plt.subplots(figsize=(8, 3.8))
        keys = sorted(cj.keys())
        ax.bar(range(len(keys)), [cj[k] for k in keys], color="#6d6875")
        ax.set_xticks(range(len(keys)))
        ax.set_xticklabels(keys, rotation=30, ha="right", fontsize=8)
        ax.set_ylabel("mean Jaccard")
        ax.set_title("Cross-venue crash concordance (panel) — lag enabler")
        p = FIG / "fig_concordance_jaccard.png"
        save_fig(p)
        paths.append(str(p))

    # 5) Epps day vs crash
    ep = summary.get("epps") or {}
    if ep.get("rows"):
        fig, ax = plt.subplots(figsize=(5.5, 4))
        ax.bar(
            ["day@1s", "crash@1s"],
            [ep.get("mean_day_1s", float("nan")), ep.get("mean_crash_1s", float("nan"))],
            color=["#2a9d8f", "#e76f51"],
        )
        ax.set_ylabel("mean Epps corr")
        ax.set_title("Epps day vs crash-window (sample cells)")
        p = FIG / "fig_epps_day_vs_crash.png"
        save_fig(p)
        paths.append(str(p))

    # 6) FEI vs |mo| scatter for HL→thick
    pts = [(t["FEI"], abs(t["mo_5s"])) for t in trades if t["hl_to_thick"] and np.isfinite(t.get("FEI", np.nan))]
    fig, ax = plt.subplots(figsize=(5.5, 4))
    if pts:
        xs, ys = zip(*pts)
        ax.scatter(xs, ys, s=12, alpha=0.55, c="#264653")
    ax.set_xlabel("FEI (day×symbol)")
    ax.set_ylabel("|mo@5s| take venue (bps)")
    ax.set_title("FEI vs |take markout| (HL→thick)")
    p = FIG / "fig_fei_vs_abs_mo.png"
    save_fig(p)
    paths.append(str(p))

    return paths


def write_report(summary: dict[str, Any], fig_paths: list[str]) -> Path:
    rules = summary["rules"]
    lines = [
        "# X-venue lag taker — EXP_REPORT",
        "",
        f"Generated: {summary['generated_at']}",
        f"Script: `applications/edge_lab/xvenue_lag/exp_xvenue_lag.py`",
        f"Panel: `{PANEL_ROWS}`",
        "",
        "## Honesty",
        "",
        f"- slice: `{HONESTY['slice']}` · live_orders={HONESTY['live_orders']} · alpha_claim={HONESTY['alpha_claim']}",
        f"- costs: {FRICTION_BPS:g}bps one-way / {RT_FRICTION:g}bps RT · entry latency={summary['params']['latency_ms']:g}ms",
        f"- lag filter: no B co-fire within ±{summary['params']['slack_s']:g}s + B not already ≥50% of signal |ΔP|",
        f"- ClickHouse MCP: banned",
        "",
        "## Verdict board",
        "",
        "| rule | decision | n | net mean [lo,hi] | early | late | why |",
        "|------|----------|--:|------------------|------:|-----:|-----|",
    ]
    for name, r in rules.items():
        v = r["primary_verdict"]
        ci = r["pnl_net_bps"]
        lines.append(
            f"| **{name}** | **{v['decision']}** | {r['n']} | "
            f"{ci['mean']:.2f} [{ci['lo']:.2f},{ci['hi']:.2f}] | "
            f"{r['early_mean']:.2f} | {r['late_mean']:.2f} | {v['why']} |"
        )

    conc = summary.get("concordance", {}).get("mean_jaccard") or {}
    ep = summary.get("epps") or {}
    lines += [
        "",
        "## Diagnostics (enablers, not edges)",
        "",
        f"- mean Jaccard (panel): `{json.dumps(conc)}`",
        f"- Epps day@1s={ep.get('mean_day_1s')} · crash@1s={ep.get('mean_crash_1s')}",
        f"- FEI pooled (from panel cells): {summary.get('fei_pooled')}",
        "",
        "## Primary lens",
        "",
        "When HL gated SSM fires and Deribit/Kraken have not co-fired (lag), take crash "
        "direction on the thick leg. Nanex∩SSM nest is a severity overlay variant.",
        "",
        "## Reproduce",
        "",
        "```bash",
        "cd research/books/cross_miniflash/applications/edge_lab/xvenue_lag",
        "python3 exp_xvenue_lag.py",
        "```",
        "",
        "## Figures",
        "",
    ]
    for p in fig_paths:
        lines.append(f"- `{p}`")
    lines.append("")
    path = OUT / "EXP_REPORT.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def run(
    *,
    slack_s: float = DEFAULT_SLACK_S,
    latency_ms: float = DEFAULT_LATENCY_MS,
    quiet: bool = True,
) -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)

    rows, meta = load_panel()
    flat = flatten_events(rows)
    days = list(meta.get("days") or sorted({e["day"] for e in flat}))
    symbols = list(meta.get("symbols") or sorted({e["symbol"] for e in flat}))
    early, late = early_late_by_day(days)

    print(f"[xvenue_lag] panel events={len(flat)} days={days} symbols={symbols}", flush=True)
    print("[xvenue_lag] loading multi-venue tapes…", flush=True)
    tapes = load_tapes(days, symbols, quiet=quiet)
    print(f"[xvenue_lag] tape cells={len(tapes)}", flush=True)

    trades = simulate_trades(
        flat,
        tapes,
        rows,
        slack_s=slack_s,
        latency_ms=latency_ms,
        early=early,
        late=late,
    )
    print(f"[xvenue_lag] lag-eligible takes={len(trades)}", flush=True)

    rules = {
        "TI-xvenue-lag:all_pairs": score_rule(
            trades,
            name="TI-xvenue-lag:all_pairs",
            predicate=lambda t: True,
            promote_scope="xvenue_lag_all_pairs",
            seed=31,
        ),
        "TI-xvenue-lag:hl_to_thick": score_rule(
            trades,
            name="TI-xvenue-lag:hl_to_thick",
            predicate=lambda t: bool(t["hl_to_thick"]),
            promote_scope="hl_signal_thick_lag_take",
            seed=32,
        ),
        "TI-xvenue-lag:any_to_thick": score_rule(
            trades,
            name="TI-xvenue-lag:any_to_thick",
            predicate=lambda t: bool(t["any_to_thick"]),
            promote_scope="any_signal_thick_lag_take",
            seed=33,
        ),
        "TI-xvenue-lag:hl_nest_to_thick": score_rule(
            trades,
            name="TI-xvenue-lag:hl_nest_to_thick",
            predicate=lambda t: bool(t["hl_to_thick"] and t["nanex_overlap"]),
            promote_scope="hl_nanex_nest_thick_lag_take",
            min_n=20,
            seed=34,
        ),
        "TI-xvenue-lag:hl_intensity2_thick": score_rule(
            trades,
            name="TI-xvenue-lag:hl_intensity2_thick",
            predicate=lambda t: bool(t["hl_to_thick"] and int(t["intensity_60s"]) >= 2),
            promote_scope="hl_intensity_gate_thick_lag_take",
            seed=35,
        ),
    }

    # pick primary = hl_to_thick (desk-aligned); board picks best Promote else Hold/Kill
    primary_name = "TI-xvenue-lag:hl_to_thick"
    board = {n: r["primary_verdict"]["decision"] for n, r in rules.items()}

    conc = concordance_diag(flat, days, symbols)
    epps = epps_sample(tapes, flat)

    # FEI pooled from panel
    fei_vals = []
    for r in rows:
        if r.get("FEI") is not None and np.isfinite(float(r["FEI"])):
            fei_vals.append(float(r["FEI"]))
        vs = r.get("vol_shares")
        if isinstance(vs, dict) and len(vs) >= 3:
            # sanity: also compute from shares once per day×symbol
            pass
    fei_by_cell = {}
    for r in rows:
        if "vol_shares" not in r:
            continue
        k = (r["day"], r["symbol"])
        if k in fei_by_cell:
            continue
        shares = [float((r.get("vol_shares") or {}).get(v, 0.0)) for v in CORE_VENUES]
        fei_by_cell[k] = fei(shares, n_pools=3)

    summary: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hypothesis": (
            "SSM/Nanex fire on venue A → take crash direction on lagging venue B "
            "(HL↔Deribit↔Kraken); concordance Hold enables lag takes"
        ),
        "honesty": HONESTY,
        "params": {
            "slack_s": slack_s,
            "latency_ms": latency_ms,
            "horizons_s": list(HORIZONS_S),
            "friction_bps_one_way": FRICTION_BPS,
            "friction_bps_rt": RT_FRICTION,
            "already_moved_frac": 0.5,
        },
        "panel": {
            "path": str(PANEL_ROWS),
            "n_events": len(flat),
            "n_trades_lag": len(trades),
            "days": days,
            "symbols": symbols,
            "early_days": sorted(early),
            "late_days": sorted(late),
        },
        "rules": rules,
        "board": board,
        "primary_rule": primary_name,
        "primary_verdict": rules[primary_name]["primary_verdict"],
        "concordance": {
            "mean_jaccard": conc["mean_jaccard"],
            "n_rows": len(conc["rows"]),
        },
        "epps": {
            "mean_day_1s": epps["mean_day_1s"],
            "mean_crash_1s": epps["mean_crash_1s"],
            "rows": epps["rows"],
        },
        "fei_pooled": {
            "mean_panel_FEI": float(np.mean(fei_vals)) if fei_vals else float("nan"),
            "mean_recomputed": float(np.mean(list(fei_by_cell.values()))) if fei_by_cell else float("nan"),
            "n_cells": len(fei_by_cell),
        },
    }

    fig_paths = make_figs(summary, trades)
    summary["figures"] = fig_paths

    save_json(OUT / "summary.json", summary)
    save_json(OUT / "trades.json", {"n": len(trades), "trades": trades[:5000], "truncated": len(trades) > 5000})
    report = write_report(summary, fig_paths)
    summary["report"] = str(report)

    # short board md
    board_md = [
        "# X-venue lag taker",
        "",
        f"Primary (`{primary_name}`): **{rules[primary_name]['primary_verdict']['decision']}** — "
        f"{rules[primary_name]['primary_verdict']['why']}",
        "",
        "| rule | decision |",
        "|------|----------|",
    ]
    for n, d in board.items():
        board_md.append(f"| {n} | **{d}** |")
    board_md += [
        "",
        "```bash",
        "cd research/books/cross_miniflash/applications/edge_lab/xvenue_lag",
        "python3 exp_xvenue_lag.py",
        "```",
        "",
    ]
    (OUT / "XVENUE_LAG.md").write_text("\n".join(board_md))
    (LAB / "XVENUE_LAG.md").write_text("\n".join(board_md))

    print(json.dumps(jsonable({"board": board, "primary": rules[primary_name]["primary_verdict"]}), indent=2))
    return summary


def rescore_from_cache() -> dict[str, Any]:
    """Re-apply verdicts from out/trades.json + prior summary params (no tape reload)."""
    trades_path = OUT / "trades.json"
    prev_path = OUT / "summary.json"
    if not trades_path.exists() or not prev_path.exists():
        raise SystemExit("no cached trades/summary — run full sim first")
    blob = json.loads(trades_path.read_text())
    trades = list(blob["trades"])
    # if truncated, refuse silent partial rescore
    if blob.get("truncated"):
        raise SystemExit("trades.json truncated; re-run full sim")
    prev = json.loads(prev_path.read_text())
    params = prev.get("params") or {}
    rules = {
        "TI-xvenue-lag:all_pairs": score_rule(
            trades, name="TI-xvenue-lag:all_pairs", predicate=lambda t: True,
            promote_scope="xvenue_lag_all_pairs", seed=31,
        ),
        "TI-xvenue-lag:hl_to_thick": score_rule(
            trades, name="TI-xvenue-lag:hl_to_thick", predicate=lambda t: bool(t["hl_to_thick"]),
            promote_scope="hl_signal_thick_lag_take", seed=32,
        ),
        "TI-xvenue-lag:any_to_thick": score_rule(
            trades, name="TI-xvenue-lag:any_to_thick", predicate=lambda t: bool(t["any_to_thick"]),
            promote_scope="any_signal_thick_lag_take", seed=33,
        ),
        "TI-xvenue-lag:hl_nest_to_thick": score_rule(
            trades, name="TI-xvenue-lag:hl_nest_to_thick",
            predicate=lambda t: bool(t["hl_to_thick"] and t["nanex_overlap"]),
            promote_scope="hl_nanex_nest_thick_lag_take", min_n=20, seed=34,
        ),
        "TI-xvenue-lag:hl_intensity2_thick": score_rule(
            trades, name="TI-xvenue-lag:hl_intensity2_thick",
            predicate=lambda t: bool(t["hl_to_thick"] and int(t["intensity_60s"]) >= 2),
            promote_scope="hl_intensity_gate_thick_lag_take", seed=35,
        ),
    }
    primary_name = "TI-xvenue-lag:hl_to_thick"
    board = {n: r["primary_verdict"]["decision"] for n, r in rules.items()}
    prev["rules"] = rules
    prev["board"] = board
    prev["primary_verdict"] = rules[primary_name]["primary_verdict"]
    prev["generated_at"] = datetime.now(timezone.utc).isoformat()
    prev["params"] = params
    fig_paths = make_figs(prev, trades)
    prev["figures"] = fig_paths
    save_json(OUT / "summary.json", prev)
    report = write_report(prev, fig_paths)
    prev["report"] = str(report)
    board_md = [
        "# X-venue lag taker",
        "",
        f"Primary (`{primary_name}`): **{rules[primary_name]['primary_verdict']['decision']}** — "
        f"{rules[primary_name]['primary_verdict']['why']}",
        "",
        "| rule | decision |",
        "|------|----------|",
    ]
    for n, d in board.items():
        board_md.append(f"| {n} | **{d}** |")
    board_md += [
        "",
        "```bash",
        "cd research/books/cross_miniflash/applications/edge_lab/xvenue_lag",
        "python3 exp_xvenue_lag.py",
        "```",
        "",
    ]
    (OUT / "XVENUE_LAG.md").write_text("\n".join(board_md))
    (LAB / "XVENUE_LAG.md").write_text("\n".join(board_md))
    print(json.dumps(jsonable({"board": board, "primary": rules[primary_name]["primary_verdict"]}), indent=2))
    return prev


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slack-s", type=float, default=DEFAULT_SLACK_S)
    ap.add_argument("--latency-ms", type=float, default=DEFAULT_LATENCY_MS)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--rescore", action="store_true", help="rescore cached trades only")
    args = ap.parse_args()
    if args.rescore:
        rescore_from_cache()
    else:
        run(slack_s=args.slack_s, latency_ms=args.latency_ms, quiet=not args.verbose)


if __name__ == "__main__":
    main()
