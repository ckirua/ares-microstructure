from __future__ import annotations
#!/usr/bin/env python3
"""TI-nanex-nest deep join — escalate size/taker on Nanex∩SSM vs SSM-only.

Owns applications/edge_lab/nanex_nest/ exclusively.
Joins Nanex nest bit from event_panel (and expanded_lab OOS panel) onto
mm_quoting panel_cache SSM events. Backtests nest escalate vs SSM-only;
costs; early/late split; Kill if nest adds nothing over blanket SSM gate.

Honesty: research_sim · costs · capacity — not live alpha.
No MM quoting. ClickHouse MCP banned. No commit.
"""


import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

NEST = Path(__file__).resolve().parent
LAB = NEST.parent
APP = LAB.parent
BOOK = APP.parent
ROOT = BOOK.parents[2]
SCRIPTS = APP / "scripts"
OUT = NEST / "out"
FIG = OUT / "figs"

for p in (str(ROOT), str(SCRIPTS), str(APP)):
    if p not in sys.path:
        sys.path.insert(0, p)

from _common import (  # noqa: E402
    FRICTION_BPS,
    early_late_by_day,
    effect_delta_ci,
    flatten_events,
    mean_ci,
    readiness_label,
    save_fig,
    save_json,
)

PANEL_CACHE = APP / "mm_quoting" / "out" / "panel_cache.json"
EVENT_PANEL = APP / "out" / "event_panel" / "panel_rows.json"
EXPANDED_PANEL = APP / "expanded_lab" / "out" / "panel" / "panel_rows.json"
RT_FRICTION = 2.0 * FRICTION_BPS
NS = 1_000_000_000
SLACK_NS = NS  # ±1s join slack

HONESTY = {
    "slice": "research_sim_on_real_tape",
    "live_orders": False,
    "fills": "synthetic_size_x_signed_tape_mo5s",
    "alpha_claim": False,
    "costs_bps_one_way": FRICTION_BPS,
    "costs_bps_round_trip": RT_FRICTION,
    "capacity": "tape_mo_ceiling_mid_sparse",
    "clickhouse_mcp": False,
    "mm_quoting_expanded": False,
    "idea": "TI-nanex-nest",
    "book_object": "info.nanex_subset_of_ssm",
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
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
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


def _ci_excludes_zero(ci: dict[str, float], *, lo_key: str = "lo", hi_key: str = "hi") -> bool:
    lo, hi = ci.get(lo_key), ci.get(hi_key)
    if lo is None or hi is None or not np.isfinite(lo) or not np.isfinite(hi):
        return False
    return (lo > 0 and hi > 0) or (lo < 0 and hi < 0)


def _sign_stable(a: float, b: float) -> bool:
    if not np.isfinite(a) or not np.isfinite(b) or a == 0 or b == 0:
        return False
    return (a > 0) == (b > 0)


def _index_flat(flat: list[dict[str, Any]]) -> dict[tuple, dict[str, Any]]:
    by: dict[tuple, dict[str, Any]] = {}
    for e in flat:
        key = (e["venue"], e["symbol"], e["day"], int(e["ts_end"]))
        by[key] = e
    return by


def _lookup(
    by: dict[tuple, dict[str, Any]],
    venue: str,
    symbol: str,
    day: str,
    ts_end: int,
) -> dict[str, Any] | None:
    key = (venue, symbol, day, int(ts_end))
    hit = by.get(key)
    if hit is not None:
        return hit
    t = int(ts_end)
    best = None
    best_dt = SLACK_NS + 1
    for (v, s, d, t2), cand in by.items():
        if v != venue or s != symbol or d != day:
            continue
        dt = abs(int(t2) - t)
        if dt <= SLACK_NS and dt < best_dt:
            best, best_dt = cand, dt
    return best


def join_cache_to_nest(
    cache_events: list[dict[str, Any]],
    panel_rows: list[dict[str, Any]],
    *,
    source_name: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Attach nanex_overlap (+ panel mo/dp/sub) onto panel_cache SSM events."""
    flat = flatten_events(panel_rows)
    by = _index_flat(flat)
    joined: list[dict[str, Any]] = []
    n_exact = n_slack = n_miss = 0
    for e in cache_events:
        hit = by.get((e["venue"], e["symbol"], e["day"], int(e["ts_end"])))
        how = "exact"
        if hit is None:
            hit = _lookup(by, e["venue"], e["symbol"], e["day"], int(e["ts_end"]))
            how = "slack" if hit is not None else "miss"
        if how == "exact":
            n_exact += 1
        elif how == "slack":
            n_slack += 1
        else:
            n_miss += 1

        mo = e.get("mo_5s")
        if mo is None or not np.isfinite(float(mo)):
            if hit is not None and hit.get("mo_5s") is not None:
                mo = hit["mo_5s"]
        if mo is None or not np.isfinite(float(mo)):
            continue
        mo = float(mo)
        nest = bool(hit.get("nanex_overlap")) if hit is not None else False
        row = {
            "venue": e["venue"],
            "symbol": e["symbol"],
            "day": e["day"],
            "ts_start": int(e.get("ts_start") or (hit or {}).get("ts_start") or 0),
            "ts_end": int(e["ts_end"]),
            "direction": int(e.get("direction") or (hit or {}).get("direction") or 0),
            "dp_pct": float(e.get("dp_pct") if e.get("dp_pct") is not None else (hit or {}).get("dp_pct") or np.nan),
            "z_peak": float(e.get("z_peak") if e.get("z_peak") is not None else (hit or {}).get("z_peak") or np.nan),
            "mo_5s": mo,
            "abs_mo": abs(mo),
            "label": e.get("label") or (hit or {}).get("recovery_label"),
            "intensity": float(e.get("intensity") or np.nan),
            "intensity_60s": int((hit or {}).get("intensity_60s") or 1),
            "tier": (hit or {}).get("tier", "unknown"),
            "nanex_overlap": nest,
            "sub_dp_30s": float((hit or {}).get("sub_dp_30s") or np.nan),
            "recovery": float((hit or {}).get("recovery") or e.get("recovery_5s") or np.nan),
            "join_how": how,
            "panel_source": source_name,
            "cohort": e.get("cohort"),
        }
        joined.append(row)

    meta = {
        "source": source_name,
        "n_cache": len(cache_events),
        "n_joined_rows": len(joined),
        "n_exact": n_exact,
        "n_slack": n_slack,
        "n_miss": n_miss,
        "n_nest": int(sum(1 for r in joined if r["nanex_overlap"])),
        "n_ssm_only": int(sum(1 for r in joined if not r["nanex_overlap"])),
    }
    return joined, meta


def events_from_panel_only(panel_rows: list[dict[str, Any]], *, source_name: str) -> list[dict[str, Any]]:
    """Fallback / OOS: flatten panel events directly (already have nest bit)."""
    flat = flatten_events(panel_rows)
    out = []
    for e in flat:
        mo = e.get("mo_5s")
        if mo is None or not np.isfinite(float(mo)):
            continue
        mo = float(mo)
        out.append(
            {
                "venue": e["venue"],
                "symbol": e["symbol"],
                "day": e["day"],
                "ts_start": int(e["ts_start"]),
                "ts_end": int(e["ts_end"]),
                "direction": int(e.get("direction") or 0),
                "dp_pct": float(e["dp_pct"]),
                "z_peak": float(e["z_peak"]),
                "mo_5s": mo,
                "abs_mo": abs(mo),
                "label": e.get("recovery_label"),
                "intensity": float("nan"),
                "intensity_60s": int(e.get("intensity_60s") or 1),
                "tier": e.get("tier", "unknown"),
                "nanex_overlap": bool(e.get("nanex_overlap")),
                "sub_dp_30s": float(e.get("sub_dp_30s") or np.nan),
                "recovery": float(e.get("recovery") or np.nan),
                "join_how": "native",
                "panel_source": source_name,
                "cohort": None,
            }
        )
    return out


def bare_nanex_placebo(panel_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Nanex events that fail SSM nest — placebo severity."""
    bare_dp, nest_dp = [], []
    for r in panel_rows:
        nx = r.get("nanex_events") or {}
        for dp, nest in zip(nx.get("dp_pct") or [], nx.get("nested") or []):
            if nest:
                nest_dp.append(float(dp))
            else:
                bare_dp.append(float(dp))
    bare = np.asarray(bare_dp, dtype=np.float64)
    nested = np.asarray(nest_dp, dtype=np.float64)
    return {
        "n_bare": int(bare.size),
        "n_nested_nanex": int(nested.size),
        "bare_dp": _boot_mean(bare, seed=201),
        "nested_nanex_dp": _boot_mean(nested, seed=202),
        "delta_nested_minus_bare_dp": effect_delta_ci(nested, bare, seed=203),
        "note": "If bare Nanex matches nest severity, nest tag adds nothing → Kill",
    }


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------

# size_mult on event: synthetic PnL ≈ size * mo_5s − |size| * RT_FRICTION
# (taker haircut scales with |size|; size=0 → flat)


def _pnl(size: float, mo: float) -> float:
    if size == 0.0:
        return 0.0
    return float(size) * float(mo) - abs(float(size)) * RT_FRICTION


def policy_matrix(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare nest escalate vs SSM-only / blanket / baseline.

    Policies (size on crash-sign taker):
      baseline:       size=1 always
      nest_hard:      nest → 0; else 1
      nest_soft:      nest → 0.25; else 1
      nest_taker_off: nest → 0 (taker pause); else 1  [alias nest_hard for PnL]
      ssm_blanket:    all gated SSM → 0; (counterfactual: nest adds nothing?)
      ssm_soft:       all gated SSM → 0.25
    """
    rows = []
    for e in events:
        mo = float(e["mo_5s"])
        nest = bool(e["nanex_overlap"])
        base = _pnl(1.0, mo)
        nest_hard = _pnl(0.0 if nest else 1.0, mo)
        nest_soft = _pnl(0.25 if nest else 1.0, mo)
        ssm_blanket = _pnl(0.0, mo)  # pause all SSM
        ssm_soft = _pnl(0.25, mo)
        # incremental lift of nest_hard over ssm_soft-on-non-nest only already in nest_hard
        # nest_vs_blanket: does nest-selective pause beat pausing everything?
        # (blanket always 0; nest_hard only pauses nest → nest_hard − blanket = non-nest aggress PnL)
        rows.append(
            {
                "day": e["day"],
                "venue": e["venue"],
                "symbol": e["symbol"],
                "nest": nest,
                "mo": mo,
                "abs_mo": abs(mo),
                "dp_pct": float(e["dp_pct"]),
                "baseline": base,
                "nest_hard": nest_hard,
                "nest_soft": nest_soft,
                "ssm_blanket": ssm_blanket,
                "ssm_soft": ssm_soft,
                "lift_nest_hard_vs_base": nest_hard - base,
                "lift_nest_soft_vs_base": nest_soft - base,
                "lift_nest_hard_vs_ssm_soft": nest_hard - ssm_soft,
                "lift_nest_hard_vs_blanket": nest_hard - ssm_blanket,
            }
        )
    return {"rows": rows}


def _cohort(day: str, early: set[str], late: set[str]) -> str:
    if day in early:
        return "early"
    if day in late:
        return "late"
    return "other"


def severity_lift(events: list[dict[str, Any]], early: set[str], late: set[str]) -> dict[str, Any]:
    nest = [e for e in events if e["nanex_overlap"]]
    non = [e for e in events if not e["nanex_overlap"]]

    def arr(xs, key):
        return np.asarray([e[key] for e in xs], dtype=np.float64)

    d_abs = effect_delta_ci(arr(nest, "abs_mo"), arr(non, "abs_mo"), seed=301)
    d_dp = effect_delta_ci(arr(nest, "dp_pct"), arr(non, "dp_pct"), seed=302)
    d_sub = effect_delta_ci(arr(nest, "sub_dp_30s"), arr(non, "sub_dp_30s"), seed=303)

    def split_delta(days: set[str]) -> dict[str, float]:
        n = [e for e in nest if e["day"] in days]
        c = [e for e in non if e["day"] in days]
        if not n or not c:
            return {"delta": float("nan"), "n_nest": len(n), "n_non": len(c)}
        return effect_delta_ci(arr(n, "abs_mo"), arr(c, "abs_mo"), seed=310 + len(days))

    early_d = split_delta(early)
    late_d = split_delta(late)
    sign_ok = _sign_stable(float(early_d.get("delta", np.nan)), float(late_d.get("delta", np.nan)))
    friction_ok = bool(
        np.isfinite(d_abs.get("delta", np.nan))
        and d_abs["delta"] > FRICTION_BPS
        and d_abs.get("lo", float("-inf")) > 0
    )
    sev_ok = bool(np.isfinite(d_dp.get("lo", np.nan)) and d_dp["lo"] > 0)
    ci_ok = _ci_excludes_zero(d_abs)

    by_venue = {}
    for v in sorted({e["venue"] for e in events}):
        nv = [e for e in nest if e["venue"] == v]
        cv = [e for e in non if e["venue"] == v]
        by_venue[v] = {
            "n_nest": len(nv),
            "n_ssm_only": len(cv),
            "mean_abs_mo_nest": float(np.nanmean(arr(nv, "abs_mo"))) if nv else None,
            "mean_abs_mo_ssm_only": float(np.nanmean(arr(cv, "abs_mo"))) if cv else None,
            "mean_dp_nest": float(np.nanmean(arr(nv, "dp_pct"))) if nv else None,
            "mean_dp_ssm_only": float(np.nanmean(arr(cv, "dp_pct"))) if cv else None,
        }

    return {
        "n_nest": len(nest),
        "n_ssm_only": len(non),
        "nest_rate": float(len(nest) / max(len(nest) + len(non), 1)),
        "abs_mo_nest": _boot_mean(arr(nest, "abs_mo"), seed=321),
        "abs_mo_ssm_only": _boot_mean(arr(non, "abs_mo"), seed=322),
        "delta_abs_mo": d_abs,
        "delta_dp_pct": d_dp,
        "delta_sub_dp_30s": d_sub,
        "time_split": {"early": early_d, "late": late_d, "sign_stable": sign_ok},
        "friction_cleared": friction_ok,
        "severity_elevated": sev_ok,
        "ci_excludes_0": ci_ok,
        "by_venue": by_venue,
    }


def policy_backtest(events: list[dict[str, Any]], early: set[str], late: set[str]) -> dict[str, Any]:
    pm = policy_matrix(events)
    rows = pm["rows"]
    for r in rows:
        r["cohort"] = _cohort(r["day"], early, late)

    def series(key: str) -> np.ndarray:
        return np.asarray([r[key] for r in rows], dtype=np.float64)

    lifts = {
        "nest_hard_vs_baseline": _boot_mean(series("lift_nest_hard_vs_base"), seed=401),
        "nest_soft_vs_baseline": _boot_mean(series("lift_nest_soft_vs_base"), seed=402),
        "nest_hard_vs_ssm_soft": _boot_mean(series("lift_nest_hard_vs_ssm_soft"), seed=403),
        "nest_hard_vs_blanket_pause": _boot_mean(series("lift_nest_hard_vs_blanket"), seed=404),
        "mean_baseline_pnl": _boot_mean(series("baseline"), seed=405),
        "mean_nest_hard_pnl": _boot_mean(series("nest_hard"), seed=406),
        "mean_nest_soft_pnl": _boot_mean(series("nest_soft"), seed=407),
    }

    def split_mean(key: str, cohort: str) -> float:
        xs = [r[key] for r in rows if r["cohort"] == cohort]
        return float(np.nanmean(xs)) if xs else float("nan")

    time_split = {
        "nest_hard_vs_baseline": {
            "early": split_mean("lift_nest_hard_vs_base", "early"),
            "late": split_mean("lift_nest_hard_vs_base", "late"),
        },
        "nest_soft_vs_baseline": {
            "early": split_mean("lift_nest_soft_vs_base", "early"),
            "late": split_mean("lift_nest_soft_vs_base", "late"),
        },
    }
    for k, v in time_split.items():
        v["sign_stable"] = _sign_stable(v["early"], v["late"])

    # incremental: nest-selective pause vs soft-clipping ALL SSM
    # If nest_hard does not beat ssm_soft on non-nest retention, nest may still win on severity tag.
    # Kill gate: nest severity Δ|mo| CI includes 0 OR nest_hard lift CI includes 0 / ≤0 mean.
    return {"n_events": len(rows), "lifts": lifts, "time_split": time_split, "friction_bps_rt": RT_FRICTION}


def verdict(
    sev: dict[str, Any],
    pol: dict[str, Any],
    placebo: dict[str, Any],
) -> dict[str, Any]:
    """Kill if nest adds nothing; else Promote / Hold."""
    d_abs = sev["delta_abs_mo"]
    lift = pol["lifts"]["nest_hard_vs_baseline"]
    soft = pol["lifts"]["nest_soft_vs_baseline"]
    ts = sev["time_split"]["sign_stable"]
    lift_ts = pol["time_split"]["nest_hard_vs_baseline"]["sign_stable"]

    # Placebo: bare Nanex should NOT match nested Nanex severity (dp)
    place_d = placebo.get("delta_nested_minus_bare_dp") or {}
    placebo_ok = bool(
        placebo.get("n_bare", 0) < 5  # underpowered placebo → don't kill on it
        or (
            np.isfinite(place_d.get("delta", np.nan))
            and place_d.get("delta", 0) > 0
            and (place_d.get("lo", 0) > 0 or place_d.get("n_control", 0) < 5)
        )
    )

    nest_adds = bool(sev["ci_excludes_0"] and d_abs.get("delta", 0) > 0 and sev["friction_cleared"])
    pnl_adds = bool(_ci_excludes_zero(lift) and lift.get("mean", 0) > 0)

    reasons = []
    if sev["n_nest"] < 25:
        decision = "Hold"
        reasons.append(f"underpowered n_nest={sev['n_nest']}<25")
    elif not nest_adds and not pnl_adds:
        decision = "Kill"
        reasons.append("nest Δ|mo| and pause-PnL add nothing (CI∋0 or ≤0)")
    elif not ts:
        decision = "Kill"
        reasons.append(
            f"time-split sign flip early={sev['time_split']['early'].get('delta')} "
            f"late={sev['time_split']['late'].get('delta')}"
        )
    elif not placebo_ok and placebo.get("n_bare", 0) >= 5:
        decision = "Kill"
        reasons.append("bare-Nanex placebo severity matches nest (tag adds nothing)")
    elif nest_adds and (lift_ts or pnl_adds) and sev["severity_elevated"]:
        decision = "Promote"
        reasons.append("Δ|mo| nest−SSM-only clears friction; time-split stable; severity↑")
    elif nest_adds:
        decision = "Hold"
        reasons.append("severity lift ok but PnL overlay / split soft")
    else:
        decision = "Hold"
        reasons.append("mixed: severity soft, awaiting more nest events")

    return {
        "id": "TI-nanex-nest",
        "decision": decision,
        "why": "; ".join(reasons),
        "nest_adds_severity": nest_adds,
        "nest_adds_pnl": pnl_adds,
        "time_split_stable": ts,
        "lift_time_split_stable": lift_ts,
        "placebo_ok": placebo_ok,
        "promote_scope": "risk_policy_nanex_escalate" if decision == "Promote" else None,
        "honesty": "not_live_alpha",
        "preferred_policy": "nest_hard_pause" if decision == "Promote" else (
            "nest_soft_0.25" if soft.get("mean", 0) > 0 and _ci_excludes_zero(soft) else None
        ),
        "readiness": readiness_label(
            effect_ci_excludes_zero=sev["ci_excludes_0"] or sev["severity_elevated"],
            time_split_sign_stable=ts,
            n_events=sev["n_nest"],
            friction_cleared=sev["friction_cleared"] and sev["severity_elevated"],
        ),
    }


# ---------------------------------------------------------------------------
# Figures + report
# ---------------------------------------------------------------------------


def make_figs(sev: dict, pol: dict, verd: dict) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    # 1) |mo| nest vs SSM-only
    fig, ax = plt.subplots(figsize=(6.5, 4.0))
    cats = ["SSM-only", "Nanex∩SSM"]
    m = [sev["abs_mo_ssm_only"]["mean"], sev["abs_mo_nest"]["mean"]]
    lo = [sev["abs_mo_ssm_only"]["lo"], sev["abs_mo_nest"]["lo"]]
    hi = [sev["abs_mo_ssm_only"]["hi"], sev["abs_mo_nest"]["hi"]]
    yerr = np.array([[m[i] - lo[i], hi[i] - m[i]] for i in range(2)]).T
    ax.bar(cats, m, yerr=yerr, capsize=5, color=["#5b7c99", "#c45c26"], alpha=0.9)
    d = sev["delta_abs_mo"]
    ax.set_ylabel("|mo|@5s (bps)")
    ax.set_title(
        f"Nest lift Δ|mo|={d['delta']:.2f} [{d['lo']:.2f},{d['hi']:.2f}]  ·  {verd['decision']}"
    )
    p = FIG / "fig_nest_abs_mo_lift.png"
    save_fig(p)
    paths.append(str(p))

    # 2) policy lifts
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    keys = [
        ("nest_hard_vs_baseline", "nest hard\nvs base"),
        ("nest_soft_vs_baseline", "nest soft\nvs base"),
        ("nest_hard_vs_ssm_soft", "nest hard\nvs SSM-soft"),
        ("nest_hard_vs_blanket_pause", "nest hard\nvs blanket"),
    ]
    means = [pol["lifts"][k]["mean"] for k, _ in keys]
    los = [pol["lifts"][k]["lo"] for k, _ in keys]
    his = [pol["lifts"][k]["hi"] for k, _ in keys]
    x = np.arange(len(keys))
    yerr = np.array([[means[i] - los[i], his[i] - means[i]] for i in range(len(keys))]).T
    ax.bar(x, means, yerr=yerr, capsize=4, color="#2f6f4e", alpha=0.85)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([lab for _, lab in keys])
    ax.set_ylabel("Δ PnL (bps / unit size)")
    ax.set_title("Escalate policies vs baselines (after RT friction)")
    p = FIG / "fig_nest_policy_lifts.png"
    save_fig(p)
    paths.append(str(p))

    # 3) time split Δ|mo|
    fig, ax = plt.subplots(figsize=(5.5, 3.8))
    e = sev["time_split"]["early"]
    l = sev["time_split"]["late"]
    ax.bar(
        ["early", "late"],
        [e.get("delta", np.nan), l.get("delta", np.nan)],
        color=["#3d6b8a", "#8a5a3d"],
        alpha=0.9,
    )
    ax.axhline(0, color="k", lw=0.8)
    ax.set_ylabel("Δ|mo| nest−SSM-only (bps)")
    ax.set_title(f"Time-split · stable={sev['time_split']['sign_stable']}")
    p = FIG / "fig_nest_time_split.png"
    save_fig(p)
    paths.append(str(p))

    # 4) venue counts
    fig, ax = plt.subplots(figsize=(6.0, 3.8))
    venues = list(sev["by_venue"].keys())
    nd = [sev["by_venue"][v]["n_nest"] for v in venues]
    so = [sev["by_venue"][v]["n_ssm_only"] for v in venues]
    x = np.arange(len(venues))
    ax.bar(x - 0.2, nd, 0.4, label="nest", color="#c45c26")
    ax.bar(x + 0.2, so, 0.4, label="SSM-only", color="#5b7c99")
    ax.set_xticks(x)
    ax.set_xticklabels(venues, rotation=15)
    ax.legend(frameon=False)
    ax.set_title("Nest vs SSM-only counts by venue")
    p = FIG / "fig_nest_venue_counts.png"
    save_fig(p)
    paths.append(str(p))

    return paths


def write_report(summary: dict[str, Any]) -> Path:
    sev = summary["primary"]["severity"]
    pol = summary["primary"]["policy"]
    verd = summary["primary"]["verdict"]
    d = sev["delta_abs_mo"]
    lift = pol["lifts"]["nest_hard_vs_baseline"]
    lines = [
        "# TI-nanex-nest — deep join EXP_REPORT",
        "",
        f"Generated: {summary['generated_at']}",
        f"Script: `applications/edge_lab/nanex_nest/exp_nanex_nest.py`",
        f"Out: `applications/edge_lab/nanex_nest/out/`",
        "",
        "## Honesty",
        "",
        f"- slice=`{HONESTY['slice']}` · live_orders=False · alpha_claim=False",
        f"- costs: one-way={FRICTION_BPS}bps · RT={RT_FRICTION}bps",
        "- fills: synthetic size × signed tape mo@5s (capacity = tape mo ceiling)",
        "- MM quoting **not** expanded · ClickHouse MCP banned",
        "",
        "## Join",
        "",
        f"- panel_cache events: **{summary['join']['primary']['n_cache']}**",
        f"- joined (exact/slack/miss): "
        f"**{summary['join']['primary']['n_exact']}** / "
        f"{summary['join']['primary']['n_slack']} / "
        f"{summary['join']['primary']['n_miss']}",
        f"- n_nest=**{sev['n_nest']}** · n_ssm_only=**{sev['n_ssm_only']}** · nest_rate={sev['nest_rate']:.3f}",
        "",
        "## Nest lift (severity)",
        "",
        f"- |mo| nest={sev['abs_mo_nest']['mean']:.2f} · SSM-only={sev['abs_mo_ssm_only']['mean']:.2f}",
        f"- **Δ|mo| nest−SSM-only = {d['delta']:.2f} bps** CI[{d['lo']:.2f}, {d['hi']:.2f}]",
        f"- Δdp% = {sev['delta_dp_pct']['delta']:.3f} CI[{sev['delta_dp_pct']['lo']:.3f}, {sev['delta_dp_pct']['hi']:.3f}]",
        f"- time-split Δ|mo| early={sev['time_split']['early'].get('delta')} "
        f"late={sev['time_split']['late'].get('delta')} · stable={sev['time_split']['sign_stable']}",
        f"- friction_cleared={sev['friction_cleared']} · severity_elevated={sev['severity_elevated']}",
        "",
        "## Policy backtest (after RT friction)",
        "",
        f"- nest_hard (size→0 on nest) vs baseline: "
        f"**{lift['mean']:.2f}** CI[{lift['lo']:.2f}, {lift['hi']:.2f}] n={lift['n']}",
        f"- nest_soft (size→0.25 on nest): "
        f"{pol['lifts']['nest_soft_vs_baseline']['mean']:.2f} "
        f"CI[{pol['lifts']['nest_soft_vs_baseline']['lo']:.2f}, "
        f"{pol['lifts']['nest_soft_vs_baseline']['hi']:.2f}]",
        f"- nest_hard vs blanket-pause-all-SSM: "
        f"{pol['lifts']['nest_hard_vs_blanket_pause']['mean']:.2f} "
        f"(positive ⇒ selective nest pause retains non-nest aggressor PnL)",
        "",
        "## Placebo (bare Nanex failing nest)",
        "",
        f"- n_bare={summary['placebo']['n_bare']} · n_nested_nanex={summary['placebo']['n_nested_nanex']}",
        f"- Δdp nested−bare = {summary['placebo']['delta_nested_minus_bare_dp']}",
        "",
        "## Verdict",
        "",
        f"- **{verd['decision']}** — {verd['why']}",
        f"- preferred_policy=`{verd.get('preferred_policy')}` · readiness=`{verd.get('readiness')}`",
        "",
        "## OOS / expanded panel",
        "",
    ]
    oos = summary.get("oos_expanded")
    if oos:
        od = oos["severity"]["delta_abs_mo"]
        lines += [
            f"- expanded flat n={oos['n_events']} nest={oos['severity']['n_nest']}",
            f"- Δ|mo|={od['delta']:.2f} CI[{od['lo']:.2f}, {od['hi']:.2f}] · "
            f"sign_stable={oos['severity']['time_split']['sign_stable']}",
            f"- OOS verdict echo: nest_adds_severity={oos['severity']['ci_excludes_0'] and oos['severity']['friction_cleared']}",
            "",
        ]
    else:
        lines += ["- (expanded panel unavailable)", ""]

    lines += [
        "## Figures",
        "",
    ]
    for f in summary.get("figs") or []:
        lines.append(f"- `{Path(f).name}`")
    lines.append("")

    path = OUT / "EXP_REPORT.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def write_readme(summary: dict[str, Any]) -> Path:
    verd = summary["primary"]["verdict"]
    d = summary["primary"]["severity"]["delta_abs_mo"]
    text = f"""# nanex_nest — TI-nanex-nest deep join

**Open:** [`out/EXP_REPORT.md`](out/EXP_REPORT.md) · [`out/summary.json`](out/summary.json) · figs [`out/figs/`](out/figs/)  
**Idea:** [`../../TRADE_IDEAS.md`](../../TRADE_IDEAS.md) `TI-nanex-nest`  
**Honesty:** research_sim · costs · capacity — **not live alpha**. No MM. No ClickHouse MCP.

## Verdict

| field | value |
|-------|-------|
| decision | **{verd['decision']}** |
| Δ\\|mo\\| nest−SSM-only | {d['delta']:.2f} bps CI[{d['lo']:.2f}, {d['hi']:.2f}] |
| why | {verd['why']} |
| preferred_policy | `{verd.get('preferred_policy')}` |

## How to run

```bash
cd research/books/cross_miniflash/applications/edge_lab/nanex_nest
python3 exp_nanex_nest.py
```

Inputs: `mm_quoting/out/panel_cache.json` ⊕ `out/event_panel/panel_rows.json`  
OOS echo: `expanded_lab/out/panel/panel_rows.json`
"""
    path = NEST / "NANEX_NEST.md"
    path.write_text(text)
    (OUT / "NANEX_NEST.md").write_text(text)
    return path


def run(*, include_oos: bool = True) -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)

    cache = json.loads(PANEL_CACHE.read_text())
    panel_rows = json.loads(EVENT_PANEL.read_text())
    days = list(cache.get("days") or sorted({e["day"] for e in cache["events"]}))
    early, late = early_late_by_day(days)

    joined, join_meta = join_cache_to_nest(cache["events"], panel_rows, source_name="event_panel")
    for e in joined:
        e["cohort"] = _cohort(e["day"], early, late)

    placebo = bare_nanex_placebo(panel_rows)
    sev = severity_lift(joined, early, late)
    pol = policy_backtest(joined, early, late)
    verd = verdict(sev, pol, placebo)

    # persist joined rows for sibling / audit
    save_json(OUT / "joined_events.json", joined)

    summary: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "honesty": HONESTY,
        "join": {
            "primary": join_meta,
            "panel_cache": str(PANEL_CACHE),
            "event_panel": str(EVENT_PANEL),
            "days": days,
            "early_days": sorted(early),
            "late_days": sorted(late),
        },
        "placebo": placebo,
        "primary": {
            "severity": sev,
            "policy": pol,
            "verdict": verd,
        },
        "headline": {
            "delta_abs_mo_bps": sev["delta_abs_mo"]["delta"],
            "delta_abs_mo_ci": [sev["delta_abs_mo"]["lo"], sev["delta_abs_mo"]["hi"]],
            "n_nest": sev["n_nest"],
            "n_ssm_only": sev["n_ssm_only"],
            "nest_hard_lift_bps": pol["lifts"]["nest_hard_vs_baseline"]["mean"],
            "decision": verd["decision"],
        },
    }

    if include_oos and EXPANDED_PANEL.exists():
        erows = json.loads(EXPANDED_PANEL.read_text())
        # Prefer join cache∩expanded where days overlap; else panel-native flatten
        oos_events = events_from_panel_only(erows, source_name="expanded_lab")
        oos_days = sorted({e["day"] for e in oos_events})
        o_early, o_late = early_late_by_day(oos_days)
        o_sev = severity_lift(oos_events, o_early, o_late)
        o_pol = policy_backtest(oos_events, o_early, o_late)
        summary["oos_expanded"] = {
            "n_events": len(oos_events),
            "days": oos_days,
            "severity": o_sev,
            "policy_lifts": {
                "nest_hard_vs_baseline": o_pol["lifts"]["nest_hard_vs_baseline"],
                "nest_soft_vs_baseline": o_pol["lifts"]["nest_soft_vs_baseline"],
            },
            "path": str(EXPANDED_PANEL),
        }

    figs = make_figs(sev, pol, verd)
    summary["figs"] = figs
    save_json(OUT / "summary.json", summary)
    write_report(summary)
    write_readme(summary)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-oos", action="store_true", help="Skip expanded_lab OOS panel")
    args = ap.parse_args()
    summary = run(include_oos=not args.no_oos)
    h = summary["headline"]
    print(
        f"TI-nanex-nest · {h['decision']} · Δ|mo|={h['delta_abs_mo_bps']:.2f} "
        f"CI{h['delta_abs_mo_ci']} · n_nest={h['n_nest']} · "
        f"nest_hard_lift={h['nest_hard_lift_bps']:.2f}bps → {OUT}"
    )


if __name__ == "__main__":
    main()
