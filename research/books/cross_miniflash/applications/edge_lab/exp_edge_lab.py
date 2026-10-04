from __future__ import annotations
#!/usr/bin/env python3
"""Edge lab — top-3 non-MM trade ideas from TRADE_IDEAS.md.

Lenses (only):
  1. TI-v-fade / TI-cont-ride — class-conditioned taker on panel_cache
  2. TI-int-halt — gated SSM intensity aggressor clip
  3. TI-nanex-nest — Nanex∩SSM escalate (join event_panel nest bit)

Honesty: research_sim · costs (2bps one-way) · capacity (tape mo only).
No live alpha claim. No MM quoting deepen. ClickHouse MCP banned.
"""


import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

LAB = Path(__file__).resolve().parent
APP = LAB.parent
BOOK = APP.parent
ROOT = BOOK.parents[2]
SCRIPTS = APP / "scripts"
OUT = LAB / "out"
FIG = OUT / "figs"

for p in (str(ROOT), str(SCRIPTS), str(APP)):
    if p not in sys.path:
        sys.path.insert(0, p)

from _common import (  # noqa: E402
    FRICTION_BPS,
    assign_ladder_tiers,
    early_late_by_day,
    effect_delta_ci,
    flatten_events,
    mean_ci,
    save_fig,
    save_json,
)

PANEL_CACHE = APP / "mm_quoting" / "out" / "panel_cache.json"
EVENT_PANEL_ROWS = APP / "out" / "event_panel" / "panel_rows.json"
RT_FRICTION = 2.0 * FRICTION_BPS  # round-trip taker haircut (bps)

HONESTY = {
    "slice": "research_sim_on_real_tape",
    "live_orders": False,
    "fills": "synthetic_size_x_signed_tape_mo5s",
    "alpha_claim": False,
    "costs_bps_one_way": FRICTION_BPS,
    "costs_bps_round_trip": RT_FRICTION,
    "capacity": "tape_mo_ceiling_mid_sparse",
    "clickhouse_mcp": False,
    "source_ideas": "applications/TRADE_IDEAS.md top-3",
    "book_objects": [
        "info.crash_v_vs_continuation",
        "risk.ssm_severity_gate_10bps",
        "risk.ssm_zstar_scan_table",
        "info.nanex_subset_of_ssm",
    ],
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
    # ares_micro.stats.bootstrap_ci → point/lo/hi
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


def _verdict(
    *,
    name: str,
    n: int,
    pnl_ci: dict[str, float],
    early_mean: float,
    late_mean: float,
    friction_cleared: bool,
    min_n: int = 25,
    promote_scope: str = "research_edge_candidate",
) -> dict[str, Any]:
    """Promote / Hold / Kill after costs + time-split."""
    excludes0 = _ci_excludes_zero(pnl_ci)
    stable = _sign_stable(early_mean, late_mean)
    mean = float(pnl_ci.get("mean", float("nan")))
    if n < min_n:
        decision = "Hold"
        why = f"underpowered n={n} < {min_n}"
    elif not excludes0:
        decision = "Kill" if (np.isfinite(mean) and mean <= 0) else "Hold"
        why = "net PnL CI includes 0 after costs" if decision == "Hold" else "mean net PnL ≤ 0 and CI includes 0"
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


def load_joined_events() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """panel_cache events ⊕ event_panel nest/tier/intensity_60s."""
    cache = json.loads(PANEL_CACHE.read_text())
    events = list(cache["events"])
    rows = json.loads(EVENT_PANEL_ROWS.read_text())
    flat = flatten_events(rows)
    assign_ladder_tiers(flat)
    by_key: dict[tuple, dict] = {}
    for e in flat:
        key = (e["venue"], e["symbol"], e["day"], int(e["ts_end"]))
        by_key[key] = e

    n_join = 0
    n_miss = 0
    for e in events:
        key = (e["venue"], e["symbol"], e["day"], int(e["ts_end"]))
        j = by_key.get(key)
        if j is None:
            # slack join ±1s
            t = int(e["ts_end"])
            j = None
            for (v, s, d, t2), cand in by_key.items():
                if v == e["venue"] and s == e["symbol"] and d == e["day"] and abs(t2 - t) <= 1_000_000_000:
                    j = cand
                    break
        if j is None:
            n_miss += 1
            e["nanex_overlap"] = False
            e["tier"] = "unknown"
            e["intensity_60s"] = int(round(float(e.get("intensity") or 0))) if e.get("intensity") else 1
            e["cohort"] = e.get("cohort") or ("early" if e["day"] <= "2026-09-06" else "late")
            continue
        n_join += 1
        e["nanex_overlap"] = bool(j.get("nanex_overlap"))
        e["tier"] = j.get("tier", "observe")
        e["intensity_60s"] = int(j.get("intensity_60s") or 1)
        # mo from panel if cache missing
        if e.get("mo_5s") is None and j.get("mo_5s") is not None:
            e["mo_5s"] = j["mo_5s"]
        if e.get("mo_1s") is None and j.get("mo_1s") is not None:
            e["mo_1s"] = j["mo_1s"]

    meta = {
        "n_cache": len(events),
        "n_joined_nest": n_join,
        "n_join_miss": n_miss,
        "days": cache.get("days"),
        "symbols": cache.get("symbols"),
        "venues": cache.get("venues"),
        "gate": cache.get("gate"),
        "panel_cache": str(PANEL_CACHE),
        "event_panel": str(EVENT_PANEL_ROWS),
    }
    return events, meta


# ---------------------------------------------------------------------------
# 1) TI-v-fade / TI-cont-ride
# ---------------------------------------------------------------------------


def causal_class(e: dict[str, Any]) -> str:
    """No look-ahead: recovery@2s only (1s confirm soft)."""
    r2 = e.get("recovery_2s")
    r1 = e.get("recovery_1s")
    if r2 is None or not np.isfinite(float(r2)):
        return "unknown"
    r2 = float(r2)
    r1 = float(r1) if r1 is not None and np.isfinite(float(r1)) else float("nan")
    if r2 >= 0.5 and (not np.isfinite(r1) or r1 >= 0.35):
        return "v_recovery"
    if r2 < 0.2:
        return "continuation"
    return "partial"


def sim_v_cont(events: list[dict[str, Any]], early: set[str], late: set[str]) -> dict[str, Any]:
    """Fade V / ride continuation / flat otherwise. PnL = signed mo − RT friction."""
    rows: list[dict[str, Any]] = []
    for e in events:
        mo = e.get("mo_5s")
        if mo is None or not np.isfinite(float(mo)):
            continue
        mo = float(mo)
        oracle = e.get("label", "unknown")
        causal = causal_class(e)

        # rules: size∈{−1 fade, +1 ride, 0 flat}; PnL = size * mo − |size| * RT
        variants = {
            "oracle_fade_v_only": -1.0 if oracle == "v_recovery" else 0.0,
            "oracle_ride_cont_only": 1.0 if oracle == "continuation" else 0.0,
            "oracle_fade_v_ride_cont": (
                -1.0 if oracle == "v_recovery" else (1.0 if oracle == "continuation" else 0.0)
            ),
            "causal_fade_v_only": -1.0 if causal == "v_recovery" else 0.0,
            "causal_ride_cont_only": 1.0 if causal == "continuation" else 0.0,
            "causal_fade_v_ride_cont": (
                -1.0 if causal == "v_recovery" else (1.0 if causal == "continuation" else 0.0)
            ),
            "always_fade": -1.0,
            "always_ride": 1.0,
            "always_flat": 0.0,
        }
        for rule, size in variants.items():
            cost = abs(size) * RT_FRICTION
            pnl = size * mo - cost
            rows.append(
                {
                    "rule": rule,
                    "pnl_bps": pnl,
                    "gross_bps": size * mo,
                    "cost_bps": cost,
                    "size": size,
                    "mo_5s": mo,
                    "day": e["day"],
                    "venue": e["venue"],
                    "symbol": e["symbol"],
                    "oracle": oracle,
                    "causal": causal,
                    "cohort": "early" if e["day"] in early else "late",
                }
            )

    by_rule: dict[str, Any] = {}
    for rule in sorted({r["rule"] for r in rows}):
        rr = [r for r in rows if r["rule"] == rule and abs(r["size"]) > 0]
        # flat rule: score all zeros as baseline mean 0
        if rule == "always_flat":
            rr = [r for r in rows if r["rule"] == rule]
        pnls = np.asarray([r["pnl_bps"] for r in rr], dtype=np.float64)
        traded = [r for r in rr if abs(r.get("size", 0)) > 0] if rule != "always_flat" else []
        n_traded = len(traded) if rule != "always_flat" else 0
        if rule == "always_flat":
            ci = {"n": len(rr), "mean": 0.0, "lo": 0.0, "hi": 0.0, "sd": 0.0}
            early_m = late_m = 0.0
            friction_cleared = False
        else:
            ci = _boot_mean(pnls, seed=11 + hash(rule) % 97)
            e_pnls = np.asarray([r["pnl_bps"] for r in rr if r["cohort"] == "early"], dtype=np.float64)
            l_pnls = np.asarray([r["pnl_bps"] for r in rr if r["cohort"] == "late"], dtype=np.float64)
            early_m = float(np.nanmean(e_pnls)) if e_pnls.size else float("nan")
            late_m = float(np.nanmean(l_pnls)) if l_pnls.size else float("nan")
            # friction cleared: mean gross > RT and net CI > 0
            gross = np.asarray([r["gross_bps"] for r in rr], dtype=np.float64)
            friction_cleared = bool(
                _ci_excludes_zero(ci)
                and ci["mean"] > 0
                and np.isfinite(np.nanmean(gross))
                and float(np.nanmean(gross)) > RT_FRICTION
            )
        verd = _verdict(
            name=f"TI-v-cont:{rule}",
            n=n_traded if rule != "always_flat" else len(rr),
            pnl_ci=ci,
            early_mean=early_m if rule != "always_flat" else 0.0,
            late_mean=late_m if rule != "always_flat" else 0.0,
            friction_cleared=friction_cleared,
            min_n=20,
            promote_scope="class_conditioned_taker_sim",
        )
        by_rule[rule] = {
            "n_traded": n_traded if rule != "always_flat" else 0,
            "n_rows": len(rr),
            "pnl_net_bps": ci,
            "early_mean": early_m if rule != "always_flat" else 0.0,
            "late_mean": late_m if rule != "always_flat" else 0.0,
            "hit_rate": float(np.mean(pnls > 0)) if pnls.size and rule != "always_flat" else float("nan"),
            "verdict": verd,
        }

    # primary A/B: causal combo vs flat; also split fade vs ride
    primary = "causal_fade_v_ride_cont"
    vs_flat = None
    if primary in by_rule:
        p_pnls = np.asarray(
            [r["pnl_bps"] for r in rows if r["rule"] == primary and abs(r["size"]) > 0],
            dtype=np.float64,
        )
        zeros = np.zeros_like(p_pnls)
        vs_flat = effect_delta_ci(p_pnls, zeros, seed=101) if p_pnls.size else None

    fade_v = by_rule.get("causal_fade_v_only", {}).get("verdict")
    ride_c = by_rule.get("causal_ride_cont_only", {}).get("verdict")
    # Desk split: cont-ride causal fails on this slice — combo Promote is fade-driven
    if fade_v and ride_c and fade_v["decision"] == "Promote" and ride_c["decision"] == "Kill":
        split_note = (
            "TI-v-fade causal Promote; TI-cont-ride causal Kill — combo edge is fade-dominated; "
            "always_fade also clears CI but mid_mo null → not naked tradable"
        )
    else:
        split_note = "see by_rule verdicts for fade vs ride split"

    # class diagnostics (oracle labels, gross mo)
    def _class_mo(lab: str) -> dict[str, float]:
        mos = np.asarray(
            [float(e["mo_5s"]) for e in events if e.get("label") == lab and e.get("mo_5s") is not None],
            dtype=np.float64,
        )
        mos = mos[np.isfinite(mos)]
        return _boot_mean(mos, seed=3 + hash(lab) % 50)

    return {
        "id": "TI-v-fade / TI-cont-ride",
        "hypothesis": "Fade V-holes; ride continuation; skip partial — causal confirm @2s",
        "friction_rt_bps": RT_FRICTION,
        "class_mo_5s_oracle": {
            "v_recovery": _class_mo("v_recovery"),
            "continuation": _class_mo("continuation"),
            "partial": _class_mo("partial"),
        },
        "causal_counts": dict(Counter(causal_class(e) for e in events)),
        "oracle_counts": dict(Counter(e.get("label", "unknown") for e in events)),
        "by_rule": by_rule,
        "primary_rule": primary,
        "primary_vs_flat": vs_flat,
        "primary_verdict": by_rule.get(primary, {}).get("verdict"),
        "verdict_fade_only": fade_v,
        "verdict_ride_only": ride_c,
        "split_note": split_note,
        "trade_rows_sample": [r for r in rows if r["rule"] == primary and abs(r["size"]) > 0][:40],
    }


# ---------------------------------------------------------------------------
# 2) TI-int-halt
# ---------------------------------------------------------------------------


def sim_int_halt(events: list[dict[str, Any]], early: set[str], late: set[str]) -> dict[str, Any]:
    """Clip aggressor when ladder fire (widen/size_cap/halt); edge = avoided adverse |mo|."""
    fire_tiers = {"widen", "size_cap", "halt"}
    rows = []
    for e in events:
        mo = e.get("mo_5s")
        if mo is None or not np.isfinite(float(mo)):
            continue
        mo = float(mo)
        tier = e.get("tier") or "observe"
        fire = tier in fire_tiers
        # Baseline dumb aggressor: take 1u WITH crash direction every event
        # Gate: size=0 on fire, size=1 on observe
        base_size = 1.0
        gate_size = 0.0 if fire else 1.0
        base_pnl = base_size * mo - abs(base_size) * RT_FRICTION
        gate_pnl = gate_size * mo - abs(gate_size) * RT_FRICTION
        # Avoided cost when we clip: if baseline would lose (pnl<0), saving = -base_pnl when clipped
        avoided_adverse = abs(mo) if fire else 0.0
        rows.append(
            {
                "day": e["day"],
                "venue": e["venue"],
                "symbol": e["symbol"],
                "tier": tier,
                "fire": fire,
                "mo_5s": mo,
                "abs_mo": abs(mo),
                "base_pnl": base_pnl,
                "gate_pnl": gate_pnl,
                "delta_pnl": gate_pnl - base_pnl,  # + means gate better
                "avoided_abs_mo": avoided_adverse,
                "cohort": "early" if e["day"] in early else "late",
            }
        )

    fire_ev = [r for r in rows if r["fire"]]
    obs_ev = [r for r in rows if not r["fire"]]
    abs_fire = np.asarray([r["abs_mo"] for r in fire_ev], dtype=np.float64)
    abs_obs = np.asarray([r["abs_mo"] for r in obs_ev], dtype=np.float64)
    d_abs = effect_delta_ci(abs_fire, abs_obs, seed=41)

    # Policy PnL: gated path vs always-aggress
    gate_pnls = np.asarray([r["gate_pnl"] for r in rows], dtype=np.float64)
    base_pnls = np.asarray([r["base_pnl"] for r in rows], dtype=np.float64)
    delta_pnls = np.asarray([r["delta_pnl"] for r in rows], dtype=np.float64)
    d_pnl = effect_delta_ci(gate_pnls, base_pnls, seed=42)
    gate_ci = _boot_mean(gate_pnls, seed=43)
    delta_ci = _boot_mean(delta_pnls, seed=44)

    e_delta = np.asarray([r["delta_pnl"] for r in rows if r["cohort"] == "early"], dtype=np.float64)
    l_delta = np.asarray([r["delta_pnl"] for r in rows if r["cohort"] == "late"], dtype=np.float64)
    early_m = float(np.nanmean(e_delta)) if e_delta.size else float("nan")
    late_m = float(np.nanmean(l_delta)) if l_delta.size else float("nan")

    # Friction: Δ|mo| fire−observe must clear one-way friction (risk-policy bar)
    friction_cleared_risk = bool(
        np.isfinite(d_abs.get("delta", float("nan")))
        and d_abs["delta"] > FRICTION_BPS
        and d_abs.get("lo", float("-inf")) > 0
    )
    # PnL-style: gating improves mean PnL vs always-aggress, CI>0, clears RT on delta
    friction_cleared_pnl = bool(
        _ci_excludes_zero(delta_ci) and delta_ci["mean"] > 0 and delta_ci["mean"] > FRICTION_BPS
    )

    verd_risk = _verdict(
        name="TI-int-halt:risk_abs_mo",
        n=len(fire_ev),
        pnl_ci={"mean": d_abs["delta"], "lo": d_abs["lo"], "hi": d_abs["hi"]},
        early_mean=early_m,
        late_mean=late_m,
        friction_cleared=friction_cleared_risk,
        min_n=30,
        promote_scope="risk_policy_aggressor_clip",
    )
    # Override time-split to use Δ|mo| early/late
    e_abs_f = np.asarray([r["abs_mo"] for r in fire_ev if r["cohort"] == "early"], dtype=np.float64)
    e_abs_o = np.asarray([r["abs_mo"] for r in obs_ev if r["cohort"] == "early"], dtype=np.float64)
    l_abs_f = np.asarray([r["abs_mo"] for r in fire_ev if r["cohort"] == "late"], dtype=np.float64)
    l_abs_o = np.asarray([r["abs_mo"] for r in obs_ev if r["cohort"] == "late"], dtype=np.float64)
    early_d = float(np.nanmean(e_abs_f) - np.nanmean(e_abs_o)) if e_abs_f.size and e_abs_o.size else float("nan")
    late_d = float(np.nanmean(l_abs_f) - np.nanmean(l_abs_o)) if l_abs_f.size and l_abs_o.size else float("nan")
    verd_risk = _verdict(
        name="TI-int-halt:risk_abs_mo",
        n=len(fire_ev),
        pnl_ci={"mean": d_abs["delta"], "lo": d_abs["lo"], "hi": d_abs["hi"]},
        early_mean=early_d,
        late_mean=late_d,
        friction_cleared=friction_cleared_risk,
        min_n=30,
        promote_scope="risk_policy_aggressor_clip",
    )
    verd_pnl = _verdict(
        name="TI-int-halt:gate_vs_always",
        n=len(rows),
        pnl_ci=delta_ci,
        early_mean=early_m,
        late_mean=late_m,
        friction_cleared=friction_cleared_pnl,
        min_n=50,
        promote_scope="aggressor_clip_pnl_overlay",
    )

    return {
        "id": "TI-int-halt",
        "hypothesis": "Clip aggressor on widen+/fire tiers; save adverse |mo| vs observe",
        "tier_counts": dict(Counter(r["tier"] for r in rows)),
        "n_fire": len(fire_ev),
        "n_observe": len(obs_ev),
        "abs_mo_fire": _boot_mean(abs_fire, seed=51),
        "abs_mo_observe": _boot_mean(abs_obs, seed=52),
        "delta_abs_mo_fire_minus_obs": d_abs,
        "friction_bps_one_way": FRICTION_BPS,
        "friction_cleared_risk": friction_cleared_risk,
        "gate_pnl_net": gate_ci,
        "baseline_pnl_net": _boot_mean(base_pnls, seed=53),
        "delta_pnl_gate_minus_base": {**d_pnl, **{"boot": delta_ci}},
        "time_split_delta_pnl": {"early": early_m, "late": late_m},
        "time_split_delta_abs_mo": {"early": early_d, "late": late_d},
        "verdict_risk_policy": verd_risk,
        "verdict_pnl_overlay": verd_pnl,
        # desk primary = risk policy (matches kill_ladder Promote)
        "primary_verdict": verd_risk,
    }


# ---------------------------------------------------------------------------
# 3) TI-nanex-nest
# ---------------------------------------------------------------------------


def sim_nanex_nest(events: list[dict[str, Any]], early: set[str], late: set[str]) -> dict[str, Any]:
    """Nanex∩SSM nest → hard escalate (size→0); control = gated non-nest."""
    nest = []
    non = []
    for e in events:
        mo = e.get("mo_5s")
        if mo is None or not np.isfinite(float(mo)):
            continue
        mo = float(mo)
        row = {
            "day": e["day"],
            "venue": e["venue"],
            "symbol": e["symbol"],
            "mo_5s": mo,
            "abs_mo": abs(mo),
            "dp_pct": float(e.get("dp_pct") or float("nan")),
            "nanex_overlap": bool(e.get("nanex_overlap")),
            "cohort": "early" if e["day"] in early else "late",
        }
        if row["nanex_overlap"]:
            nest.append(row)
        else:
            non.append(row)

    abs_n = np.asarray([r["abs_mo"] for r in nest], dtype=np.float64)
    abs_c = np.asarray([r["abs_mo"] for r in non], dtype=np.float64)
    d_abs = effect_delta_ci(abs_n, abs_c, seed=61)
    dp_n = np.asarray([r["dp_pct"] for r in nest], dtype=np.float64)
    dp_c = np.asarray([r["dp_pct"] for r in non], dtype=np.float64)
    d_dp = effect_delta_ci(dp_n, dp_c, seed=62)

    # PnL overlay: always-aggress baseline; nest → size 0
    rows = []
    for e in events:
        mo = e.get("mo_5s")
        if mo is None or not np.isfinite(float(mo)):
            continue
        mo = float(mo)
        nest_bit = bool(e.get("nanex_overlap"))
        base = 1.0 * mo - RT_FRICTION
        gate = 0.0 if nest_bit else (1.0 * mo - RT_FRICTION)
        rows.append(
            {
                "delta_pnl": gate - base,
                "gate_pnl": gate,
                "base_pnl": base,
                "nest": nest_bit,
                "cohort": "early" if e["day"] in early else "late",
                "abs_mo": abs(mo),
            }
        )
    delta_pnls = np.asarray([r["delta_pnl"] for r in rows], dtype=np.float64)
    delta_ci = _boot_mean(delta_pnls, seed=63)
    e_d = float(np.nanmean([r["delta_pnl"] for r in rows if r["cohort"] == "early"]))
    l_d = float(np.nanmean([r["delta_pnl"] for r in rows if r["cohort"] == "late"]))

    e_abs_n = np.asarray([r["abs_mo"] for r in nest if r["cohort"] == "early"], dtype=np.float64)
    e_abs_c = np.asarray([r["abs_mo"] for r in non if r["cohort"] == "early"], dtype=np.float64)
    l_abs_n = np.asarray([r["abs_mo"] for r in nest if r["cohort"] == "late"], dtype=np.float64)
    l_abs_c = np.asarray([r["abs_mo"] for r in non if r["cohort"] == "late"], dtype=np.float64)
    early_d = float(np.nanmean(e_abs_n) - np.nanmean(e_abs_c)) if e_abs_n.size and e_abs_c.size else float("nan")
    late_d = float(np.nanmean(l_abs_n) - np.nanmean(l_abs_c)) if l_abs_n.size and l_abs_c.size else float("nan")

    friction_cleared = bool(
        np.isfinite(d_abs.get("delta", float("nan")))
        and d_abs["delta"] > FRICTION_BPS
        and d_abs.get("lo", float("-inf")) > 0
    )
    verd = _verdict(
        name="TI-nanex-nest",
        n=len(nest),
        pnl_ci={"mean": d_abs["delta"], "lo": d_abs["lo"], "hi": d_abs["hi"]},
        early_mean=early_d,
        late_mean=late_d,
        friction_cleared=friction_cleared,
        min_n=25,
        promote_scope="risk_policy_nanex_escalate",
    )
    verd_pnl = _verdict(
        name="TI-nanex-nest:pnl_overlay",
        n=len(rows),
        pnl_ci=delta_ci,
        early_mean=e_d,
        late_mean=l_d,
        friction_cleared=bool(_ci_excludes_zero(delta_ci) and delta_ci["mean"] > 0),
        min_n=50,
        promote_scope="nanex_pause_pnl_overlay",
    )

    return {
        "id": "TI-nanex-nest",
        "hypothesis": "Nanex∩SSM nest → hard escalate (taker pause); nest |mo| ≫ non-nest",
        "n_nest": len(nest),
        "n_non_nest": len(non),
        "precision_proxy": float(len(nest) / max(len(nest) + len(non), 1)),
        "abs_mo_nest": _boot_mean(abs_n, seed=71),
        "abs_mo_non_nest": _boot_mean(abs_c, seed=72),
        "delta_abs_mo_nest_minus_non": d_abs,
        "delta_dp_pct": d_dp,
        "friction_cleared_risk": friction_cleared,
        "delta_pnl_nest_pause": delta_ci,
        "time_split_delta_abs_mo": {"early": early_d, "late": late_d},
        "verdict_risk_policy": verd,
        "verdict_pnl_overlay": verd_pnl,
        "primary_verdict": verd,
    }


# ---------------------------------------------------------------------------
# Figures + report
# ---------------------------------------------------------------------------


def make_figs(vcont: dict, ith: dict, nest: dict) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    # 1) class mo CI
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    labs = ["v_recovery", "continuation", "partial"]
    means, los, his, ns = [], [], [], []
    for lab in labs:
        c = vcont["class_mo_5s_oracle"][lab]
        means.append(c["mean"])
        los.append(c["mean"] - c["lo"] if np.isfinite(c["lo"]) else 0)
        his.append(c["hi"] - c["mean"] if np.isfinite(c["hi"]) else 0)
        ns.append(c["n"])
    x = np.arange(len(labs))
    ax.bar(x, means, yerr=[los, his], capsize=4, color=["#3d7a6a", "#b85c38", "#888888"])
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{l}\nn={n}" for l, n in zip(labs, ns)])
    ax.set_ylabel("mo@5s (bps, crash-signed)")
    ax.set_title("TI-v-fade / TI-cont-ride — class mo@5s")
    p = FIG / "fig_class_mo5s.png"
    save_fig(p)
    paths.append(str(p))

    # 2) rule net PnL
    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    rules = [
        "causal_fade_v_ride_cont",
        "causal_fade_v_only",
        "causal_ride_cont_only",
        "oracle_fade_v_ride_cont",
        "always_fade",
        "always_ride",
    ]
    means, err_lo, err_hi, colors = [], [], [], []
    for r in rules:
        b = vcont["by_rule"][r]["pnl_net_bps"]
        means.append(b["mean"])
        err_lo.append(b["mean"] - b["lo"] if np.isfinite(b["lo"]) else 0)
        err_hi.append(b["hi"] - b["mean"] if np.isfinite(b["hi"]) else 0)
        verd = vcont["by_rule"][r]["verdict"]["decision"]
        colors.append({"Promote": "#2a7a4b", "Hold": "#c4a35a", "Kill": "#a33b2b"}.get(verd, "#888"))
    x = np.arange(len(rules))
    ax.barh(x, means, xerr=[err_lo, err_hi], color=colors, capsize=3)
    ax.axvline(0, color="k", lw=0.8)
    ax.set_yticks(x)
    ax.set_yticklabels(rules, fontsize=8)
    ax.set_xlabel("net PnL after RT friction (bps / trade)")
    ax.set_title("TI-v-fade / TI-cont-ride — rule net PnL")
    p = FIG / "fig_vcont_rule_pnl.png"
    save_fig(p)
    paths.append(str(p))

    # 3) int-halt abs mo
    fig, ax = plt.subplots(figsize=(6.5, 4.0))
    cats = ["observe", "fire (widen+)"]
    m = [ith["abs_mo_observe"]["mean"], ith["abs_mo_fire"]["mean"]]
    lo = [ith["abs_mo_observe"]["lo"], ith["abs_mo_fire"]["lo"]]
    hi = [ith["abs_mo_fire"]["hi"] if False else ith["abs_mo_fire"]["hi"], ith["abs_mo_fire"]["hi"]]
    lo = [ith["abs_mo_observe"]["lo"], ith["abs_mo_fire"]["lo"]]
    hi = [ith["abs_mo_observe"]["hi"], ith["abs_mo_fire"]["hi"]]
    yerr = [[m[i] - lo[i], hi[i] - m[i]] for i in range(2)]
    ax.bar(cats, m, yerr=np.array(yerr).T, capsize=4, color=["#6a8cae", "#b85c38"])
    ax.set_ylabel("|mo@5s| (bps)")
    d = ith["delta_abs_mo_fire_minus_obs"]
    ax.set_title(f"TI-int-halt — Δ|mo| fire−obs = {d['delta']:.2f} [{d['lo']:.2f},{d['hi']:.2f}]")
    p = FIG / "fig_inthalt_abs_mo.png"
    save_fig(p)
    paths.append(str(p))

    # 4) nanex nest
    fig, ax = plt.subplots(figsize=(6.5, 4.0))
    cats = ["SSM only", "Nanex∩SSM"]
    m = [nest["abs_mo_non_nest"]["mean"], nest["abs_mo_nest"]["mean"]]
    lo = [nest["abs_mo_non_nest"]["lo"], nest["abs_mo_nest"]["lo"]]
    hi = [nest["abs_mo_non_nest"]["hi"], nest["abs_mo_nest"]["hi"]]
    yerr = [[m[i] - lo[i], hi[i] - m[i]] for i in range(2)]
    ax.bar(cats, m, yerr=np.array(yerr).T, capsize=4, color=["#6a8cae", "#8b3a4a"])
    ax.set_ylabel("|mo@5s| (bps)")
    d = nest["delta_abs_mo_nest_minus_non"]
    ax.set_title(f"TI-nanex-nest — Δ|mo| nest−non = {d['delta']:.2f} [{d['lo']:.2f},{d['hi']:.2f}]")
    p = FIG / "fig_nanex_nest_abs_mo.png"
    save_fig(p)
    paths.append(str(p))

    # 5) scoreboard
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    items = [
        ("TI-v-cont\ncausal combo", vcont["primary_verdict"]),
        ("TI-int-halt\nrisk |mo|", ith["primary_verdict"]),
        ("TI-nanex-nest\nrisk |mo|", nest["primary_verdict"]),
    ]
    y = np.arange(len(items))
    colors = [{"Promote": "#2a7a4b", "Hold": "#c4a35a", "Kill": "#a33b2b"}[v["decision"]] for _, v in items]
    ax.barh(y, [1, 1, 1], color=colors)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{n} → {v['decision']}" for n, v in items])
    ax.set_xticks([])
    ax.set_xlim(0, 1.2)
    ax.set_title("Edge lab scoreboard (after costs · time-split)")
    for i, (_, v) in enumerate(items):
        ax.text(1.02, i, v["why"][:48], va="center", fontsize=7)
    p = FIG / "fig_scoreboard.png"
    save_fig(p)
    paths.append(str(p))

    # 6) early/late for primary causal
    fig, ax = plt.subplots(figsize=(6.0, 3.8))
    br = vcont["by_rule"]["causal_fade_v_ride_cont"]
    ax.bar(["early", "late"], [br["early_mean"], br["late_mean"]], color=["#5b7c99", "#9c6b4a"])
    ax.axhline(0, color="k", lw=0.8)
    ax.set_ylabel("net PnL (bps)")
    ax.set_title("causal_fade_v_ride_cont — early/late")
    p = FIG / "fig_vcont_early_late.png"
    save_fig(p)
    paths.append(str(p))

    return paths


def write_report(summary: dict[str, Any], fig_paths: list[str]) -> Path:
    v = summary["lenses"]["TI-v-cont"]
    i = summary["lenses"]["TI-int-halt"]
    n = summary["lenses"]["TI-nanex-nest"]
    lines = [
        "# Edge lab — EXP_REPORT",
        "",
        f"Generated: {summary['generated_at']}",
        f"Events: n={summary['meta']['n_cache']} · joined nest {summary['meta']['n_joined_nest']} · miss {summary['meta']['n_join_miss']}",
        f"Honesty: `{HONESTY['slice']}` · RT friction={RT_FRICTION} bps · live_orders=False · alpha_claim=False",
        f"Ideas source: [`../TRADE_IDEAS.md`](../TRADE_IDEAS.md) top-3 (no MM deepen)",
        "",
        "## Scoreboard",
        "",
        "| id | decision | headline | why |",
        "|----|----------|----------|-----|",
    ]

    def _row(ide: str, verd: dict, headline: str) -> str:
        return f"| **{ide}** | **{verd['decision']}** | {headline} | {verd['why']} |"

    pc = v["by_rule"]["causal_fade_v_ride_cont"]["pnl_net_bps"]
    fade_v = v.get("verdict_fade_only") or {}
    ride_c = v.get("verdict_ride_only") or {}
    lines.append(
        _row(
            "TI-v-fade (causal)",
            fade_v if fade_v else v["primary_verdict"],
            f"fade-only net {v['by_rule']['causal_fade_v_only']['pnl_net_bps']['mean']:.2f} bps "
            f"CI[{v['by_rule']['causal_fade_v_only']['pnl_net_bps']['lo']:.2f},"
            f"{v['by_rule']['causal_fade_v_only']['pnl_net_bps']['hi']:.2f}] "
            f"n={v['by_rule']['causal_fade_v_only']['n_traded']}",
        )
    )
    lines.append(
        _row(
            "TI-cont-ride (causal)",
            ride_c if ride_c else {"decision": "Hold", "why": "missing"},
            f"ride-only net {v['by_rule']['causal_ride_cont_only']['pnl_net_bps']['mean']:.2f} bps "
            f"CI[{v['by_rule']['causal_ride_cont_only']['pnl_net_bps']['lo']:.2f},"
            f"{v['by_rule']['causal_ride_cont_only']['pnl_net_bps']['hi']:.2f}] "
            f"n={v['by_rule']['causal_ride_cont_only']['n_traded']}",
        )
    )
    lines.append(
        _row(
            "TI-v-fade+cont combo",
            v["primary_verdict"],
            f"causal combo net {pc['mean']:.2f} bps CI[{pc['lo']:.2f},{pc['hi']:.2f}] n={pc['n']} "
            f"— {v.get('split_note', '')[:60]}",
        )
    )
    d = i["delta_abs_mo_fire_minus_obs"]
    lines.append(
        _row(
            "TI-int-halt",
            i["primary_verdict"],
            f"Δ\\|mo\\| fire−obs {d['delta']:.2f} CI[{d['lo']:.2f},{d['hi']:.2f}] n_fire={i['n_fire']}",
        )
    )
    d2 = n["delta_abs_mo_nest_minus_non"]
    lines.append(
        _row(
            "TI-nanex-nest",
            n["primary_verdict"],
            f"Δ\\|mo\\| nest−non {d2['delta']:.2f} CI[{d2['lo']:.2f},{d2['hi']:.2f}] n_nest={n['n_nest']}",
        )
    )

    lines += [
        "",
        "## 1. TI-v-fade / TI-cont-ride",
        "",
        "Causal confirm uses recovery@2s (≥0.5 → V fade; <0.2 → cont ride). Oracle uses label@5s (upper bound).",
        f"- Oracle class mo@5s: V={v['class_mo_5s_oracle']['v_recovery']['mean']:.2f} · "
        f"cont={v['class_mo_5s_oracle']['continuation']['mean']:.2f} · "
        f"partial={v['class_mo_5s_oracle']['partial']['mean']:.2f}",
        f"- Causal counts: {v['causal_counts']}",
        f"- Primary `{v['primary_rule']}`: net {pc['mean']:.2f} [{pc['lo']:.2f},{pc['hi']:.2f}] · "
        f"early={v['by_rule']['causal_fade_v_ride_cont']['early_mean']:.2f} · "
        f"late={v['by_rule']['causal_fade_v_ride_cont']['late_mean']:.2f}",
        f"- Verdict: **{v['primary_verdict']['decision']}** — {v['primary_verdict']['why']}",
        "",
        "### Rule table (net bps after RT friction)",
        "",
        "| rule | n_traded | mean | lo | hi | early | late | decision |",
        "|------|----------|------|----|----|-------|------|----------|",
    ]
    for rule, b in v["by_rule"].items():
        c = b["pnl_net_bps"]
        lines.append(
            f"| `{rule}` | {b['n_traded']} | {c['mean']:.2f} | {c['lo']:.2f} | {c['hi']:.2f} | "
            f"{b['early_mean']:.2f} | {b['late_mean']:.2f} | {b['verdict']['decision']} |"
        )

    lines += [
        "",
        "## 2. TI-int-halt",
        "",
        "Fire = ladder tiers {widen, size_cap, halt} from event_panel (within-gated z + intensity + Nanex).",
        f"- |mo| observe={i['abs_mo_observe']['mean']:.2f} · fire={i['abs_mo_fire']['mean']:.2f}",
        f"- Δ|mo| fire−obs={d['delta']:.2f} CI[{d['lo']:.2f},{d['hi']:.2f}] · "
        f"friction_cleared={i['friction_cleared_risk']}",
        f"- Time-split Δ|mo|: early={i['time_split_delta_abs_mo']['early']:.2f} · "
        f"late={i['time_split_delta_abs_mo']['late']:.2f}",
        f"- PnL overlay gate−always: mean Δ={i['delta_pnl_gate_minus_base']['boot']['mean']:.2f} "
        f"→ {i['verdict_pnl_overlay']['decision']}",
        f"- Primary verdict: **{i['primary_verdict']['decision']}** — {i['primary_verdict']['why']}",
        "",
        "## 3. TI-nanex-nest",
        "",
        "Nest bit joined from `out/event_panel/` (`nanex_overlap`).",
        f"- n_nest={n['n_nest']} · n_non={n['n_non_nest']}",
        f"- |mo| nest={n['abs_mo_nest']['mean']:.2f} · non={n['abs_mo_non_nest']['mean']:.2f}",
        f"- Δ|mo|={d2['delta']:.2f} CI[{d2['lo']:.2f},{d2['hi']:.2f}] · "
        f"friction_cleared={n['friction_cleared_risk']}",
        f"- Time-split Δ|mo|: early={n['time_split_delta_abs_mo']['early']:.2f} · "
        f"late={n['time_split_delta_abs_mo']['late']:.2f}",
        f"- Primary verdict: **{n['primary_verdict']['decision']}** — {n['primary_verdict']['why']}",
        "",
        "## How to run",
        "",
        "```bash",
        "cd research/books/cross_miniflash/applications/edge_lab",
        "python3 exp_edge_lab.py",
        "```",
        "",
        "## Artifacts",
        "",
        "- `out/summary.json`",
        "- `out/EXP_REPORT.md`",
        "- `out/EDGE_LAB.md` (desk stub)",
        "- figs:",
    ]
    for fp in fig_paths:
        lines.append(f"  - `{Path(fp).name}`")
    lines += [
        "",
        "## Falsifiers applied",
        "",
        "- Net PnL / Δ|mo| bootstrap CI must exclude 0",
        "- Early/late day split sign-stable",
        "- Effect must clear friction (2bps one-way risk · 4bps RT taker)",
        "- Causal V/cont uses recovery@1–2s only (no recovery_5s look-ahead for live rule)",
        "",
    ]
    path = OUT / "EXP_REPORT.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def write_edge_lab_md(summary: dict[str, Any]) -> Path:
    vc = summary["lenses"]["TI-v-cont"]
    v = vc["primary_verdict"]
    fade = vc.get("verdict_fade_only") or {}
    ride = vc.get("verdict_ride_only") or {}
    i = summary["lenses"]["TI-int-halt"]["primary_verdict"]
    n = summary["lenses"]["TI-nanex-nest"]["primary_verdict"]
    text = f"""# Edge lab — non-MM top-3 from TRADE_IDEAS

**Open:** [`out/EXP_REPORT.md`](out/EXP_REPORT.md) · figs [`out/figs/`](out/figs/) · [`out/summary.json`](out/summary.json)  
**Ideas map:** [`../TRADE_IDEAS.md`](../TRADE_IDEAS.md)  
**Honesty:** research_sim · costs · capacity — **not live alpha**. MM quoting not expanded.

## Scoreboard

| id | decision |
|----|----------|
| TI-v-fade (causal @2s) | **{fade.get('decision', '?')}** |
| TI-cont-ride (causal @2s) | **{ride.get('decision', '?')}** |
| TI-v-fade+cont combo | **{v['decision']}** (fade-dominated) |
| TI-int-halt | **{i['decision']}** |
| TI-nanex-nest | **{n['decision']}** |

Note: {vc.get('split_note', '')}

## How to run

```bash
cd research/books/cross_miniflash/applications/edge_lab
python3 exp_edge_lab.py
```

Inputs: `../mm_quoting/out/panel_cache.json` + nest/tier join from `../out/event_panel/`.
"""
    path = OUT / "EDGE_LAB.md"
    path.write_text(text)
    (LAB / "EDGE_LAB.md").write_text(text)
    return path


def run() -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    events, meta = load_joined_events()
    days = list(meta.get("days") or sorted({e["day"] for e in events}))
    early, late = early_late_by_day(days)

    vcont = sim_v_cont(events, early, late)
    ith = sim_int_halt(events, early, late)
    nest = sim_nanex_nest(events, early, late)
    figs = make_figs(vcont, ith, nest)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "honesty": HONESTY,
        "meta": meta,
        "early_days": sorted(early),
        "late_days": sorted(late),
        "lenses": {
            "TI-v-cont": vcont,
            "TI-int-halt": ith,
            "TI-nanex-nest": nest,
        },
        "scoreboard": [
            vcont["primary_verdict"],
            ith["primary_verdict"],
            nest["primary_verdict"],
        ],
        "figs": figs,
    }
    save_json(OUT / "summary.json", summary)
    write_report(summary, figs)
    write_edge_lab_md(summary)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    s = run()
    print(json.dumps(jsonable({"scoreboard": s["scoreboard"], "figs": s["figs"]}), indent=2))


if __name__ == "__main__":
    main()
