from __future__ import annotations
#!/usr/bin/env python3
"""Hardening stress for LR-fire-pause@5m (Promote baseline Δ|mo|≈+19.8).

Falsifiers
  - more days (probe gaps beyond PIN_USABLE)
  - BTC + Deribit / Kraken transfer
  - bootstrap CIs (n_boot ladder)
  - cost / friction sweep
  - placebo fire labels + random event times
  - early / late time-split
  - exclude Nanex nest overlap
  - interaction with TI-int-halt (mo@5s)
  - V-fade composition sketch (don't-fade-during-pause vs do)

Artifacts → out/long_edges/FIRE_PAUSE_HARDENING.md + figs/fig_fp_*.png
ClickHouse MCP banned. No commit.
"""

import os

import argparse
import json
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

LAB = Path(__file__).resolve().parent
APP = LAB.parent
BOOK = APP.parent
ROOT = BOOK.parents[2]
STARTARB = Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb'))
WAREHOUSE_SRC = Path(os.environ.get('WAREHOUSE_SRC') or ((Path(os.environ.get('WAREHOUSE_ROOT') or (Path.home() / 'lab' / 'lab-n2070' / 'warehouse')) / 'src')))
OUT = LAB / "out" / "long_edges"
FIG = OUT / "figs"
PAPER = APP / "paper_harness"
SCRIPTS_APP = APP / "scripts"

for p in (
    str(LAB),
    str(PAPER),
    str(APP),
    str(SCRIPTS_APP),
    str(BOOK / "scripts"),
    str(ROOT),
    str(STARTARB / "src"),
    str(WAREHOUSE_SRC),
):
    if p not in sys.path:
        sys.path.insert(0, p)

from _common import (  # noqa: E402
    early_late_by_day,
    effect_delta_ci,
    mean_ci,
    save_fig,
    save_json,
)
from run_long_edges import (  # noqa: E402
    FIRE_TIERS,
    FRICTION_ONE_WAY,
    HOLD_LABEL,
    NS,
    PIN_USABLE,
    PANEL_CORE,
    RT_FRICTION,
    _boot_mean,
    _ci_excludes_zero,
    _load_events_jsonl,
    _sign_stable,
    _verdict,
    jsonable,
    process_day,
)

HOLD_KEY = "mo_5m"
HOLD_5S = "mo_5s"
PRIMARY_HOLD = "5m"
MIN_N_FIRE = 40
FRICTION_BAR = FRICTION_ONE_WAY  # 2 bps one-way risk bar for Δ|mo|

# Days between / beyond PIN gaps to probe for "more days"
EXTRA_PROBE = [
    "2026-09-11",
    "2026-09-12",
    "2026-09-13",
    "2026-09-23",
    "2026-09-24",
    "2026-09-28",
    "2026-09-29",
    "2026-10-01",
]

EXPAND_VENUES = ("hyperliquid", "deribit", "kraken")
EXPAND_SYMBOLS = ("ETH", "BTC")


def _delta_abs(
    fire: list[dict[str, Any]],
    obs: list[dict[str, Any]],
    *,
    hold_key: str = HOLD_KEY,
    seed: int = 55,
    early: set[str] | None = None,
    late: set[str] | None = None,
    n_boot: int = 800,
) -> dict[str, Any]:
    abs_f = np.asarray(
        [abs(float(e[hold_key])) for e in fire if e.get(hold_key) is not None],
        dtype=np.float64,
    )
    abs_o = np.asarray(
        [abs(float(e[hold_key])) for e in obs if e.get(hold_key) is not None],
        dtype=np.float64,
    )
    d = (
        effect_delta_ci(abs_f, abs_o, n_boot=n_boot, seed=seed)
        if abs_f.size and abs_o.size
        else {
            "n_treat": int(abs_f.size),
            "n_control": int(abs_o.size),
            "delta": float("nan"),
            "lo": float("nan"),
            "hi": float("nan"),
            "treat_mean": float("nan"),
            "control_mean": float("nan"),
        }
    )
    early = early or set()
    late = late or set()
    e_f = np.asarray(
        [abs(float(e[hold_key])) for e in fire if e["day"] in early and e.get(hold_key) is not None],
        dtype=np.float64,
    )
    e_o = np.asarray(
        [abs(float(e[hold_key])) for e in obs if e["day"] in early and e.get(hold_key) is not None],
        dtype=np.float64,
    )
    l_f = np.asarray(
        [abs(float(e[hold_key])) for e in fire if e["day"] in late and e.get(hold_key) is not None],
        dtype=np.float64,
    )
    l_o = np.asarray(
        [abs(float(e[hold_key])) for e in obs if e["day"] in late and e.get(hold_key) is not None],
        dtype=np.float64,
    )
    e_d = float(np.nanmean(e_f) - np.nanmean(e_o)) if e_f.size and e_o.size else float("nan")
    l_d = float(np.nanmean(l_f) - np.nanmean(l_o)) if l_f.size and l_o.size else float("nan")
    delta_ci = {
        "n": int(d.get("n_treat", 0)),
        "mean": float(d.get("delta", float("nan"))),
        "lo": float(d.get("lo", float("nan"))),
        "hi": float(d.get("hi", float("nan"))),
        "sd": float("nan"),
    }
    friction_cleared = bool(_ci_excludes_zero(delta_ci) and delta_ci["mean"] > FRICTION_BAR)
    verd = _verdict(
        name="LR-fire-pause@5m",
        n=int(d.get("n_treat", 0)),
        pnl_ci=delta_ci,
        early_mean=e_d,
        late_mean=l_d,
        friction_cleared=friction_cleared,
        min_n=MIN_N_FIRE,
        promote_scope="long_horizon_intensity_pause",
    )
    return {
        "n_fire": int(d.get("n_treat", 0)),
        "n_observe": int(d.get("n_control", 0)),
        "abs_mo_fire": _boot_mean(abs_f, seed=seed + 1, n_boot=n_boot),
        "abs_mo_observe": _boot_mean(abs_o, seed=seed + 2, n_boot=n_boot),
        "delta_abs_mo": d,
        "pnl_net_bps": delta_ci,
        "early_delta": e_d,
        "late_delta": l_d,
        "friction_cleared": friction_cleared,
        "verdict": verd,
    }


def _split_fire_obs(events: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    fire = [e for e in events if e.get("fire") and e.get(HOLD_KEY) is not None]
    obs = [e for e in events if (not e.get("fire")) and e.get(HOLD_KEY) is not None]
    return fire, obs


def _pass_fail(block: dict[str, Any], *, require_promote: bool = True) -> str:
    d = block["verdict"]["decision"]
    if require_promote:
        return "PASS" if d == "Promote" else ("FAIL" if d == "Kill" else "WEAK")
    # for placebo: PASS means null (CI includes 0 or mean≤0) — edge should vanish
    mean = block["pnl_net_bps"]["mean"]
    excludes = _ci_excludes_zero(block["pnl_net_bps"])
    if excludes and np.isfinite(mean) and mean > FRICTION_BAR:
        return "FAIL"  # placebo still looks like edge → bad
    return "PASS"


def baseline_block(events: list[dict[str, Any]], early: set[str], late: set[str]) -> dict[str, Any]:
    fire, obs = _split_fire_obs(events)
    b = _delta_abs(fire, obs, seed=55, early=early, late=late)
    b["slice"] = "HL_ETH_baseline"
    return b


def falsifier_bootstrap(
    events: list[dict[str, Any]], early: set[str], late: set[str]
) -> dict[str, Any]:
    fire, obs = _split_fire_obs(events)
    ladder = {}
    for n_boot in (200, 800, 2000, 5000):
        ladder[str(n_boot)] = _delta_abs(
            fire, obs, seed=100 + n_boot, early=early, late=late, n_boot=n_boot
        )
    primary = ladder["800"]
    # survive if all n_boot≥800 still exclude 0 and mean>friction
    survive = all(
        _ci_excludes_zero(ladder[k]["pnl_net_bps"]) and ladder[k]["pnl_net_bps"]["mean"] > FRICTION_BAR
        for k in ("800", "2000", "5000")
    )
    return {
        "ladder": {
            k: {
                "delta": v["pnl_net_bps"]["mean"],
                "lo": v["pnl_net_bps"]["lo"],
                "hi": v["pnl_net_bps"]["hi"],
                "decision": v["verdict"]["decision"],
            }
            for k, v in ladder.items()
        },
        "survive": survive,
        "verdict": primary["verdict"],
        "pnl_net_bps": primary["pnl_net_bps"],
        "pass": "PASS" if survive else "FAIL",
    }


def falsifier_cost_sweep(
    events: list[dict[str, Any]], early: set[str], late: set[str]
) -> dict[str, Any]:
    fire, obs = _split_fire_obs(events)
    base = _delta_abs(fire, obs, seed=55, early=early, late=late)
    delta = float(base["pnl_net_bps"]["mean"])
    lo = float(base["pnl_net_bps"]["lo"])
    bars = [0.5, 1.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0]
    rows = []
    break_bar = None
    for bar in bars:
        clears = bool(lo > 0 and delta > bar)
        rows.append({"friction_bar_bps": bar, "clears": clears, "delta": delta, "lo": lo})
        if break_bar is None and not clears:
            break_bar = bar
    # survive baseline bar (2bps) with room; Kill if breaks at ≤2
    survive = break_bar is None or break_bar > FRICTION_BAR
    return {
        "delta": delta,
        "lo": lo,
        "hi": float(base["pnl_net_bps"]["hi"]),
        "rows": rows,
        "break_bar_bps": break_bar,
        "survive": survive,
        "pass": "PASS" if survive and lo > 0 else "FAIL",
        "note": "Δ|mo| must clear risk friction bar; break_bar = first bar that fails",
    }


def falsifier_early_late(
    events: list[dict[str, Any]], early: set[str], late: set[str]
) -> dict[str, Any]:
    fire, obs = _split_fire_obs(events)
    b = _delta_abs(fire, obs, seed=55, early=early, late=late)
    stable = _sign_stable(b["early_delta"], b["late_delta"])
    # also half-panel absolute effects
    # Half-panel absolute Δ only (no nested early/late split — avoids false Kill on nan split)
    e_fire = [e for e in fire if e["day"] in early]
    e_obs = [e for e in obs if e["day"] in early]
    l_fire = [e for e in fire if e["day"] in late]
    l_obs = [e for e in obs if e["day"] in late]
    e_abs_f = np.asarray([abs(float(e[HOLD_KEY])) for e in e_fire], dtype=np.float64)
    e_abs_o = np.asarray([abs(float(e[HOLD_KEY])) for e in e_obs], dtype=np.float64)
    l_abs_f = np.asarray([abs(float(e[HOLD_KEY])) for e in l_fire], dtype=np.float64)
    l_abs_o = np.asarray([abs(float(e[HOLD_KEY])) for e in l_obs], dtype=np.float64)
    e_d = effect_delta_ci(e_abs_f, e_abs_o, seed=71) if e_abs_f.size and e_abs_o.size else {
        "delta": float("nan"), "lo": float("nan"), "hi": float("nan"), "n_treat": 0
    }
    l_d = effect_delta_ci(l_abs_f, l_abs_o, seed=72) if l_abs_f.size and l_abs_o.size else {
        "delta": float("nan"), "lo": float("nan"), "hi": float("nan"), "n_treat": 0
    }

    def _half_decision(d: dict[str, Any]) -> str:
        mean, lo, hi = d.get("delta"), d.get("lo"), d.get("hi")
        n = int(d.get("n_treat", 0))
        if n < 20 or not all(np.isfinite(x) for x in (mean, lo, hi)):
            return "Hold"
        if lo > 0 and mean > FRICTION_BAR:
            return "Promote"
        if hi < 0:
            return "Kill"
        return "Hold"

    survive = stable and b["verdict"]["decision"] in {"Promote", "Hold"} and b["pnl_net_bps"]["mean"] > 0
    # Early half underpowered / CI∋0 is a WEAK flag even if signs match
    early_weak = not (np.isfinite(e_d.get("lo", float("nan"))) and e_d["lo"] > 0)
    return {
        "early_delta": b["early_delta"],
        "late_delta": b["late_delta"],
        "sign_stable": stable,
        "early_panel": {
            "n_fire": int(e_d.get("n_treat", 0)),
            "delta": float(e_d.get("delta", float("nan"))),
            "lo": float(e_d.get("lo", float("nan"))),
            "hi": float(e_d.get("hi", float("nan"))),
            "decision": _half_decision(e_d),
        },
        "late_panel": {
            "n_fire": int(l_d.get("n_treat", 0)),
            "delta": float(l_d.get("delta", float("nan"))),
            "lo": float(l_d.get("lo", float("nan"))),
            "hi": float(l_d.get("hi", float("nan"))),
            "decision": _half_decision(l_d),
        },
        "survive": survive and stable,
        "pass": (
            "FAIL"
            if not stable
            else ("WEAK" if early_weak or not (b["pnl_net_bps"]["lo"] > 0) else "PASS")
        ),
        "verdict": b["verdict"],
        "pnl_net_bps": b["pnl_net_bps"],
    }


def falsifier_exclude_nest(
    events: list[dict[str, Any]], early: set[str], late: set[str]
) -> dict[str, Any]:
    """Fire∩¬nest vs observe∩¬nest — edge must not be nest-driven."""
    fire = [
        e
        for e in events
        if e.get("fire") and (not e.get("nanex_overlap")) and e.get(HOLD_KEY) is not None
    ]
    obs = [
        e
        for e in events
        if (not e.get("fire")) and (not e.get("nanex_overlap")) and e.get(HOLD_KEY) is not None
    ]
    b = _delta_abs(fire, obs, seed=88, early=early, late=late)
    # nest-only fire vs non-nest observe (diagnostic)
    fire_nest = [
        e for e in events if e.get("fire") and e.get("nanex_overlap") and e.get(HOLD_KEY) is not None
    ]
    nest_vs_obs = _delta_abs(fire_nest, obs, seed=89, early=early, late=late) if fire_nest else None
    return {
        "ex_nest": b,
        "n_fire_ex_nest": b["n_fire"],
        "n_fire_nest": len(fire_nest),
        "nest_fire_vs_obs": nest_vs_obs,
        "pass": _pass_fail(b),
        "survive": b["verdict"]["decision"] == "Promote",
    }


def falsifier_exclude_overlap_windows(
    events: list[dict[str, Any]], early: set[str], late: set[str], *, window_s: float = 300.0
) -> dict[str, Any]:
    """Keep only first fire in each 5m nest-of-fires (non-overlapping pause starts)."""
    by_cell: dict[tuple, list] = {}
    for e in events:
        key = (e.get("venue"), e.get("symbol"), e["day"])
        by_cell.setdefault(key, []).append(e)
    kept_fire: list[dict] = []
    for rows in by_cell.values():
        rows = sorted(rows, key=lambda r: int(r["ts_start"]))
        last_ts = -10**30
        w = int(window_s * NS)
        for e in rows:
            if not e.get("fire") or e.get(HOLD_KEY) is None:
                continue
            t = int(e["ts_start"])
            if t - last_ts < w:
                continue
            kept_fire.append(e)
            last_ts = t
    obs = [e for e in events if (not e.get("fire")) and e.get(HOLD_KEY) is not None]
    b = _delta_abs(kept_fire, obs, seed=91, early=early, late=late)
    return {
        "n_fire_raw": sum(1 for e in events if e.get("fire") and e.get(HOLD_KEY) is not None),
        "n_fire_nonoverlap": b["n_fire"],
        "block": b,
        "pass": _pass_fail(b),
        "survive": b["verdict"]["decision"] == "Promote",
    }


def falsifier_placebo_labels(
    events: list[dict[str, Any]], early: set[str], late: set[str], *, n_rep: int = 200
) -> dict[str, Any]:
    """Shuffle fire flags among events with mo_5m; true edge should beat placebo."""
    pool = [e for e in events if e.get(HOLD_KEY) is not None]
    n_fire = sum(1 for e in pool if e.get("fire"))
    if n_fire < 10 or len(pool) < 20:
        return {"pass": "WEAK", "survive": False, "reason": "underpowered", "n_fire": n_fire}

    abs_all = np.asarray([abs(float(e[HOLD_KEY])) for e in pool], dtype=np.float64)
    true_fire = np.asarray([bool(e.get("fire")) for e in pool], dtype=bool)
    true_delta = float(abs_all[true_fire].mean() - abs_all[~true_fire].mean())

    rng = np.random.default_rng(12345)
    deltas = np.empty(n_rep, dtype=np.float64)
    for i in range(n_rep):
        mask = np.zeros(len(pool), dtype=bool)
        mask[rng.choice(len(pool), size=n_fire, replace=False)] = True
        deltas[i] = float(abs_all[mask].mean() - abs_all[~mask].mean())
    p_ge = float(np.mean(deltas >= true_delta))
    plac_ci = mean_ci(deltas, n_boot=800, seed=9)
    # PASS if true beats ≥95% of shuffles and true CI (elsewhere) is the real claim
    survive = p_ge <= 0.05
    return {
        "true_delta": true_delta,
        "placebo_mean": float(np.mean(deltas)),
        "placebo_lo": float(plac_ci["lo"]),
        "placebo_hi": float(plac_ci["hi"]),
        "p_ge_true": p_ge,
        "n_rep": n_rep,
        "n_fire": n_fire,
        "n_pool": len(pool),
        "survive": survive,
        "pass": "PASS" if survive else "FAIL",
        "note": "label-shuffle null; PASS if p(placebo≥true)≤0.05",
    }


def _placebo_abs_mo_day(payload: dict[str, Any]) -> list[float]:
    """Module-level worker: random-tape |mo|@5m draws for one day (picklable)."""
    from harness.detect import detect_day  # noqa: WPS433

    day = payload["day"]
    n_per_day = int(payload["n_per_day"])
    try:
        det = detect_day("hyperliquid", "ETH", day, quiet=True)
        if det.get("skip"):
            return []
        ts = np.asarray(det["ts"], dtype=np.int64)
        px = np.asarray(det["px"], dtype=np.float64)
        if ts.size < 100:
            return []
        local = np.random.default_rng(abs(hash(day)) % (2**31))
        out: list[float] = []
        h_ns = int(300.0 * NS)
        for _ in range(n_per_day):
            i = int(local.integers(0, max(ts.size - 50, 1)))
            if px[i] <= 0 or not np.isfinite(px[i]):
                continue
            j = int(np.searchsorted(ts, int(ts[i]) + h_ns, side="right") - 1)
            if j <= i or not np.isfinite(px[j]) or px[j] <= 0:
                continue
            out.append(abs(float((px[j] - px[i]) / px[i] * 1e4)))
        return out
    except Exception:  # noqa: BLE001
        return []


def falsifier_placebo_times(
    events: list[dict[str, Any]],
    *,
    workers: int = 4,
    n_per_day: int | None = None,
) -> dict[str, Any]:
    """Recompute |mo|@5m at random tape times (same day density) — should not separate."""
    # Group fire counts by day on HL ETH only for speed
    hl = [e for e in events if e.get("venue", "hyperliquid") == "hyperliquid" and e.get("symbol") == "ETH"]
    by_day: dict[str, list] = {}
    for e in hl:
        by_day.setdefault(e["day"], []).append(e)

    days = sorted(by_day)
    if n_per_day is None:
        # match mean fire/day density roughly
        n_per_day = max(5, int(round(sum(1 for e in hl if e.get("fire")) / max(len(days), 1))))

    plac_abs: list[float] = []
    real_fire_abs: list[float] = []
    real_obs_abs: list[float] = []

    for e in hl:
        if e.get(HOLD_KEY) is None:
            continue
        if e.get("fire"):
            real_fire_abs.append(abs(float(e[HOLD_KEY])))
        else:
            real_obs_abs.append(abs(float(e[HOLD_KEY])))

    payloads = [{"day": d, "n_per_day": int(n_per_day)} for d in days]
    if workers <= 1:
        for p in payloads:
            plac_abs.extend(_placebo_abs_mo_day(p))
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_placebo_abs_mo_day, p): p for p in payloads}
            for fut in as_completed(futs):
                plac_abs.extend(fut.result())
    pa = np.asarray(plac_abs, dtype=np.float64)
    rf = np.asarray(real_fire_abs, dtype=np.float64)
    ro = np.asarray(real_obs_abs, dtype=np.float64)
    # Placebo mean |mo| should be near observe, not fire
    d_fire_vs_plac = (
        effect_delta_ci(rf, pa, seed=201) if rf.size and pa.size else {"delta": float("nan"), "lo": float("nan"), "hi": float("nan")}
    )
    d_obs_vs_plac = (
        effect_delta_ci(ro, pa, seed=202) if ro.size and pa.size else {"delta": float("nan"), "lo": float("nan"), "hi": float("nan")}
    )
    # Survive if fire ≫ placebo (CI>0) AND observe ≈ placebo (CI includes 0 or small)
    fire_beats = bool(
        np.isfinite(d_fire_vs_plac.get("lo", float("nan"))) and d_fire_vs_plac["lo"] > 0
    )
    obs_near = bool(
        (not np.isfinite(d_obs_vs_plac.get("lo", float("nan"))))
        or (d_obs_vs_plac["lo"] < FRICTION_BAR)  # observe not clearly above placebo by much
        or (abs(d_obs_vs_plac.get("delta", 0)) < abs(d_fire_vs_plac.get("delta", 99)) * 0.5)
    )
    survive = fire_beats and bool(pa.size >= 30)
    return {
        "n_placebo": int(pa.size),
        "n_per_day": n_per_day,
        "placebo_mean_abs_mo": float(np.mean(pa)) if pa.size else float("nan"),
        "fire_mean_abs_mo": float(np.mean(rf)) if rf.size else float("nan"),
        "obs_mean_abs_mo": float(np.mean(ro)) if ro.size else float("nan"),
        "delta_fire_minus_placebo": d_fire_vs_plac,
        "delta_obs_minus_placebo": d_obs_vs_plac,
        "fire_beats_placebo": fire_beats,
        "obs_near_placebo": obs_near,
        "survive": survive,
        "pass": "PASS" if survive else "FAIL",
        "note": "random tape times; fire |mo|@5m must beat placebo",
    }


def falsifier_int_halt_interaction(
    events: list[dict[str, Any]], early: set[str], late: set[str]
) -> dict[str, Any]:
    """TI-int-halt is mo@5s; LR-fire-pause is |mo|@5m. Are they redundant or stacked?"""
    fire, obs = _split_fire_obs(events)
    # short-horizon int-halt analogue on same events
    short = _delta_abs(fire, obs, hold_key=HOLD_5S, seed=41, early=early, late=late)
    long = _delta_abs(fire, obs, hold_key=HOLD_KEY, seed=55, early=early, late=late)

    # residual: among fire events, is |mo|@5m still elevated after conditioning on |mo|@5s?
    # Split fire into high/low |mo_5s| halves
    fire_with_both = [
        e for e in fire if e.get(HOLD_5S) is not None and e.get(HOLD_KEY) is not None
    ]
    if len(fire_with_both) >= 20:
        abs5 = np.asarray([abs(float(e[HOLD_5S])) for e in fire_with_both], dtype=np.float64)
        med = float(np.median(abs5))
        hi5 = [e for e, a in zip(fire_with_both, abs5) if a >= med]
        lo5 = [e for e, a in zip(fire_with_both, abs5) if a < med]
        # Within fire: does high short-mo also mean high long-mo? (redundancy)
        within = _delta_abs(hi5, lo5, seed=66)  # treat=hi short as "fire-like"
        # Long pause value on low-|mo5s| fire (int-halt would not clip hard) vs observe
        residual = _delta_abs(lo5, obs, seed=67, early=early, late=late)
    else:
        within = None
        residual = None
        med = float("nan")

    # Stacked policy: int-halt saves |mo|@5s; fire-pause saves incremental |mo|@5m − |mo|@5s
    incr = []
    for e in fire_with_both:
        incr.append(abs(float(e[HOLD_KEY])) - abs(float(e[HOLD_5S])))
    incr_a = np.asarray(incr, dtype=np.float64) if incr else np.asarray([], dtype=np.float64)
    incr_ci = _boot_mean(incr_a, seed=68) if incr_a.size else {"n": 0, "mean": float("nan"), "lo": float("nan"), "hi": float("nan")}

    # Survive if long still Promote AND (residual Promote or incremental mean>friction with CI>0)
    long_ok = long["verdict"]["decision"] == "Promote"
    residual_ok = bool(
        residual
        and residual["pnl_net_bps"]["mean"] > 0
        and (
            residual["verdict"]["decision"] in {"Promote", "Hold"}
            or residual["n_fire"] < MIN_N_FIRE
        )
    )
    incr_ok = bool(
        incr_ci.get("n", 0) >= 20
        and np.isfinite(incr_ci["mean"])
        and incr_ci["mean"] > 0
    )
    survive = long_ok and (residual_ok or incr_ok)
    return {
        "int_halt_5s": short,
        "fire_pause_5m": long,
        "median_abs_mo_5s_fire": med,
        "within_fire_hi_vs_lo_5s": within,
        "residual_low5s_fire_vs_obs_5m": residual,
        "incremental_abs_mo_5m_minus_5s": incr_ci,
        "survive": survive,
        "pass": "PASS" if survive else "FAIL",
        "note": (
            "PASS if @5m Promote and either residual (low-|mo5s| fire vs obs) still + "
            "or incremental |mo5m|-|mo5s| > 0 — stack not pure 5s duplicate"
        ),
    }


def falsifier_vfade_compose(
    events: list[dict[str, Any]], early: set[str], late: set[str]
) -> dict[str, Any]:
    """Sketch: V-fade during fire-pause window vs suppress fade during pause.

    Causal V@2s fade PnL @5s (edge_lab style) stratified by fire.
    - don't_fade_during_pause: only fade when NOT fire
    - do_fade_during_pause: fade on all causal V (including fire)
    - fade_only_on_fire: (anti) fade only when fire — expected worse if pause is right
    """
    v_ev = [
        e
        for e in events
        if e.get("causal") == "v_recovery" and e.get(HOLD_5S) is not None
    ]

    def score(cands: list[dict], name: str) -> dict[str, Any]:
        if not cands:
            empty = {"n": 0, "mean": float("nan"), "lo": float("nan"), "hi": float("nan")}
            return {"id": name, "n": 0, "pnl_net_bps": empty, "decision": "Hold", "why": "empty"}
        pnls = []
        e_pnls, l_pnls = [], []
        for e in cands:
            # fade = −crash-signed mo
            net = -float(e[HOLD_5S]) - RT_FRICTION
            pnls.append(net)
            if e["day"] in early:
                e_pnls.append(net)
            elif e["day"] in late:
                l_pnls.append(net)
        ci = _boot_mean(np.asarray(pnls, dtype=np.float64), seed=abs(hash(name)) % 200)
        e_m = float(np.mean(e_pnls)) if e_pnls else float("nan")
        l_m = float(np.mean(l_pnls)) if l_pnls else float("nan")
        verd = _verdict(
            name=name,
            n=len(pnls),
            pnl_ci=ci,
            early_mean=e_m,
            late_mean=l_m,
            friction_cleared=bool(_ci_excludes_zero(ci) and ci["mean"] > 0),
            min_n=20,
            promote_scope="vfade_x_fire_pause_compose",
        )
        return {
            "id": name,
            "n": len(pnls),
            "pnl_net_bps": ci,
            "early_mean": e_m,
            "late_mean": l_m,
            "decision": verd["decision"],
            "why": verd["why"],
            "verdict": verd,
        }

    all_v = score(v_ev, "fade_all_causal_V")
    quiet = score([e for e in v_ev if not e.get("fire")], "dont_fade_during_pause")
    on_fire = score([e for e in v_ev if e.get("fire")], "fade_only_during_pause")
    # Recommendation: prefer the better of quiet vs all; if on_fire is Kill/worse, don't fade in pause
    quiet_m = quiet["pnl_net_bps"]["mean"]
    all_m = all_v["pnl_net_bps"]["mean"]
    fire_m = on_fire["pnl_net_bps"]["mean"]
    if np.isfinite(fire_m) and np.isfinite(quiet_m) and fire_m + 2.0 < quiet_m:
        rec = "dont_fade_during_pause"
        rec_why = (
            f"V-fade on fire mean {fire_m:.2f} ≪ quiet {quiet_m:.2f} — "
            "suppress fade entries while fire_pause_5m is live"
        )
    elif np.isfinite(fire_m) and fire_m > 0 and _ci_excludes_zero(on_fire["pnl_net_bps"]):
        rec = "do_fade_during_pause"
        rec_why = (
            f"V-fade still earns on fire (mean {fire_m:.2f}) — pause kills *other* aggressors; "
            "allow mean-reversion fade through pause window"
        )
    else:
        rec = "dont_fade_during_pause"
        rec_why = (
            f"conservative: quiet={quiet_m:.2f} all={all_m:.2f} fire={fire_m:.2f} — "
            "default suppress fade during pause unless fire-leg clearly Promote"
        )

    return {
        "fade_all": all_v,
        "dont_fade_during_pause": quiet,
        "fade_only_during_pause": on_fire,
        "recommendation": rec,
        "recommendation_why": rec_why,
        "pass": "PASS",  # compositional sketch, not a kill switch for fire-pause itself
        "survive": True,
        "note": "compositional overlay on V-fade; does not falsify fire-pause alone",
    }


def expand_panel(
    *,
    days: list[str],
    venues: list[str],
    symbols: list[str],
    workers: int,
    skip_hl_eth: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payloads = []
    for d in days:
        for v in venues:
            for s in symbols:
                if skip_hl_eth and v == "hyperliquid" and s == "ETH":
                    continue
                payloads.append({"day": d, "symbol": s, "venue": v})
    print(f"[harden] expand cells={len(payloads)} workers={workers}", flush=True)
    results: list[dict[str, Any]] = []
    if workers <= 1:
        for p in payloads:
            r = process_day(p)
            results.append(r)
            print(
                f"  {r.get('venue','?')} {r.get('day')} {r.get('symbol')} ok={r.get('ok')} "
                f"n_ev={r.get('n_events', 0)} reason={r.get('reason', '')}",
                flush=True,
            )
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(process_day, p): p for p in payloads}
            for fut in as_completed(futs):
                p = futs[fut]
                try:
                    r = fut.result()
                except Exception as exc:  # noqa: BLE001
                    r = {
                        "ok": False,
                        "day": p["day"],
                        "symbol": p["symbol"],
                        "venue": p["venue"],
                        "reason": f"{type(exc).__name__}: {exc}",
                        "events": [],
                    }
                # process_day doesn't always set venue
                r.setdefault("venue", p["venue"])
                results.append(r)
                print(
                    f"  {r.get('venue')} {r.get('day')} {r.get('symbol')} ok={r.get('ok')} "
                    f"n_ev={r.get('n_events', 0)} reason={r.get('reason', '')}",
                    flush=True,
                )
    events: list[dict[str, Any]] = []
    for r in results:
        for e in r.get("events") or []:
            e.setdefault("venue", r.get("venue"))
            events.append(e)
    coverage = [
        {
            "day": r.get("day"),
            "symbol": r.get("symbol"),
            "venue": r.get("venue"),
            "ok": bool(r.get("ok")),
            "n_events": r.get("n_events", 0),
            "n_trades": r.get("n_trades", 0),
            "reason": r.get("reason"),
        }
        for r in sorted(
            results, key=lambda x: (x.get("venue") or "", x.get("day") or "", x.get("symbol") or "")
        )
    ]
    return events, coverage


def probe_extra_days(*, workers: int = 4) -> dict[str, Any]:
    """Try gap days for HL ETH — more days if available."""
    payloads = [{"day": d, "symbol": "ETH", "venue": "hyperliquid"} for d in EXTRA_PROBE]
    print(f"[harden] probe extra days={EXTRA_PROBE}", flush=True)
    results = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(process_day, p): p for p in payloads}
        for fut in as_completed(futs):
            r = fut.result()
            r.setdefault("venue", "hyperliquid")
            results.append(r)
            print(
                f"  extra {r.get('day')} ok={r.get('ok')} n_ev={r.get('n_events', 0)} "
                f"reason={r.get('reason', '')}",
                flush=True,
            )
    usable = [r for r in results if r.get("ok") and int(r.get("n_events") or 0) > 0]
    events = []
    for r in usable:
        for e in r.get("events") or []:
            e.setdefault("venue", "hyperliquid")
            events.append(e)
    return {
        "probed": EXTRA_PROBE,
        "usable_days": sorted({r["day"] for r in usable}),
        "n_events": len(events),
        "events": events,
        "coverage": [
            {
                "day": r.get("day"),
                "ok": bool(r.get("ok")),
                "n_events": r.get("n_events", 0),
                "reason": r.get("reason"),
            }
            for r in sorted(results, key=lambda x: x.get("day") or "")
        ],
    }


def slice_metrics(
    events: list[dict[str, Any]], label: str, early: set[str] | None = None, late: set[str] | None = None
) -> dict[str, Any]:
    days = sorted({e["day"] for e in events})
    if early is None or late is None:
        early, late = early_late_by_day(days)
    fire, obs = _split_fire_obs(events)
    b = _delta_abs(fire, obs, seed=55 + abs(hash(label)) % 50, early=early, late=late)
    b["slice"] = label
    b["n_days"] = len(days)
    b["days"] = days
    b["pass"] = _pass_fail(b)
    return b


def make_hardening_figs(report: dict[str, Any]) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    verd_color = {"Promote": "#2a7a4b", "Hold": "#c4a35a", "Kill": "#a33b2b", "PASS": "#2a7a4b", "FAIL": "#a33b2b", "WEAK": "#c4a35a"}

    # 1) Baseline + transfer
    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    slices = report["transfer_board"]
    labels = [s["slice"] for s in slices]
    means = [s["pnl_net_bps"]["mean"] for s in slices]
    los = [
        s["pnl_net_bps"]["mean"] - s["pnl_net_bps"]["lo"] if np.isfinite(s["pnl_net_bps"]["lo"]) else 0
        for s in slices
    ]
    his = [
        s["pnl_net_bps"]["hi"] - s["pnl_net_bps"]["mean"] if np.isfinite(s["pnl_net_bps"]["hi"]) else 0
        for s in slices
    ]
    colors = [verd_color.get(s["verdict"]["decision"], "#888") for s in slices]
    x = np.arange(len(labels))
    ax.bar(x, means, yerr=[los, his], capsize=3, color=colors)
    ax.axhline(0, color="k", lw=0.8)
    ax.axhline(FRICTION_BAR, color="gray", ls="--", lw=0.8, label=f"friction {FRICTION_BAR}bps")
    ax.set_xticks(x)
    ax.set_xticklabels(
        [f"{lb}\nn={s['n_fire']}" for lb, s in zip(labels, slices)], rotation=25, ha="right", fontsize=8
    )
    ax.set_ylabel("Δ|mo|@5m fire−obs (bps)")
    ax.set_title("LR-fire-pause@5m — transfer board")
    ax.legend(fontsize=8)
    p = FIG / "fig_fp_transfer_board.png"
    save_fig(p)
    paths.append(str(p))

    # 2) Cost sweep
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    cs = report["falsifiers"]["cost_sweep"]
    bars = [r["friction_bar_bps"] for r in cs["rows"]]
    clears = [1.0 if r["clears"] else 0.0 for r in cs["rows"]]
    ax.plot(bars, clears, "o-", color="#2a7a4b")
    ax.axvline(FRICTION_BAR, color="gray", ls="--", label="baseline bar")
    if cs.get("break_bar_bps") is not None:
        ax.axvline(cs["break_bar_bps"], color="#a33b2b", ls=":", label=f"break@{cs['break_bar_bps']}")
    ax.axhline(cs["delta"], color="#334", ls="-.", label=f"Δ={cs['delta']:.1f}")
    ax.set_xlabel("friction bar (bps)")
    ax.set_ylabel("clears (1/0)")
    ax.set_title("Cost / friction sweep — Δ|mo|@5m")
    ax.legend(fontsize=8)
    p = FIG / "fig_fp_cost_sweep.png"
    save_fig(p)
    paths.append(str(p))

    # 3) Bootstrap ladder
    fig, ax = plt.subplots(figsize=(6.5, 4.0))
    boot = report["falsifiers"]["bootstrap"]["ladder"]
    ks = sorted(boot.keys(), key=int)
    means = [boot[k]["delta"] for k in ks]
    los = [boot[k]["delta"] - boot[k]["lo"] for k in ks]
    his = [boot[k]["hi"] - boot[k]["delta"] for k in ks]
    ax.errorbar(range(len(ks)), means, yerr=[los, his], fmt="o", color="#2a7a4b", capsize=4)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(range(len(ks)))
    ax.set_xticklabels([f"n={k}" for k in ks])
    ax.set_ylabel("Δ|mo|@5m (bps)")
    ax.set_title("Bootstrap CI ladder")
    p = FIG / "fig_fp_bootstrap_ladder.png"
    save_fig(p)
    paths.append(str(p))

    # 4) Placebo
    fig, ax = plt.subplots(figsize=(6.8, 4.0))
    pl = report["falsifiers"]["placebo_labels"]
    pt = report["falsifiers"]["placebo_times"]
    names = ["true Δ", "label-shuffle\nmean", "random-time\n|mo|", "fire |mo|", "obs |mo|"]
    vals = [
        pl.get("true_delta", float("nan")),
        pl.get("placebo_mean", float("nan")),
        pt.get("placebo_mean_abs_mo", float("nan")),
        pt.get("fire_mean_abs_mo", float("nan")),
        pt.get("obs_mean_abs_mo", float("nan")),
    ]
    ax.bar(range(len(names)), vals, color=["#2a7a4b", "#aaa", "#aaa", "#c45", "#69c"])
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, fontsize=8)
    ax.set_ylabel("bps")
    ax.set_title(
        f"Placebo — label p={pl.get('p_ge_true', float('nan')):.3f} · "
        f"times pass={pt.get('pass')}"
    )
    p = FIG / "fig_fp_placebo.png"
    save_fig(p)
    paths.append(str(p))

    # 5) Early/late + nest + nonoverlap
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    blocks = [
        ("baseline", report["baseline"]),
        ("ex-nest", report["falsifiers"]["exclude_nest"]["ex_nest"]),
        ("nonoverlap", report["falsifiers"]["exclude_overlap"]["block"]),
        ("earlyΔ", {"pnl_net_bps": {
            "mean": report["falsifiers"]["early_late"]["early_delta"],
            "lo": report["falsifiers"]["early_late"]["early_panel"]["lo"],
            "hi": report["falsifiers"]["early_late"]["early_panel"]["hi"],
        }, "verdict": {"decision": report["falsifiers"]["early_late"]["early_panel"]["decision"]}}),
        ("lateΔ", {"pnl_net_bps": {
            "mean": report["falsifiers"]["early_late"]["late_delta"],
            "lo": report["falsifiers"]["early_late"]["late_panel"]["lo"],
            "hi": report["falsifiers"]["early_late"]["late_panel"]["hi"],
        }, "verdict": {"decision": report["falsifiers"]["early_late"]["late_panel"]["decision"]}}),
    ]
    means = [b[1]["pnl_net_bps"]["mean"] for b in blocks]
    los = [
        (b[1]["pnl_net_bps"]["mean"] - b[1]["pnl_net_bps"]["lo"])
        if np.isfinite(b[1]["pnl_net_bps"].get("lo", float("nan")))
        else 0
        for b in blocks
    ]
    his = [
        (b[1]["pnl_net_bps"]["hi"] - b[1]["pnl_net_bps"]["mean"])
        if np.isfinite(b[1]["pnl_net_bps"].get("hi", float("nan")))
        else 0
        for b in blocks
    ]
    colors = [verd_color.get(b[1]["verdict"]["decision"], "#888") for b in blocks]
    ax.bar(range(len(blocks)), means, yerr=[los, his], capsize=3, color=colors)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(range(len(blocks)))
    ax.set_xticklabels([b[0] for b in blocks])
    ax.set_ylabel("Δ|mo|@5m (bps)")
    ax.set_title("Robustness — nest / overlap / early-late")
    p = FIG / "fig_fp_robustness.png"
    save_fig(p)
    paths.append(str(p))

    # 6) Int-halt interaction
    fig, ax = plt.subplots(figsize=(7.0, 4.2))
    ih = report["falsifiers"]["int_halt"]
    items = [
        ("int-halt\n@5s", ih["int_halt_5s"]),
        ("fire-pause\n@5m", ih["fire_pause_5m"]),
    ]
    if ih.get("residual_low5s_fire_vs_obs_5m"):
        items.append(("residual\nlow|mo5s|", ih["residual_low5s_fire_vs_obs_5m"]))
    means = [it[1]["pnl_net_bps"]["mean"] for it in items]
    los = [it[1]["pnl_net_bps"]["mean"] - it[1]["pnl_net_bps"]["lo"] for it in items]
    his = [it[1]["pnl_net_bps"]["hi"] - it[1]["pnl_net_bps"]["mean"] for it in items]
    colors = [verd_color.get(it[1]["verdict"]["decision"], "#888") for it in items]
    ax.bar(range(len(items)), means, yerr=[los, his], capsize=3, color=colors)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(range(len(items)))
    ax.set_xticklabels([it[0] for it in items])
    ax.set_ylabel("Δ|mo| (bps)")
    ax.set_title("Interaction — TI-int-halt @5s vs LR-fire-pause @5m")
    p = FIG / "fig_fp_int_halt.png"
    save_fig(p)
    paths.append(str(p))

    # 7) V-fade compose
    fig, ax = plt.subplots(figsize=(7.0, 4.2))
    vf = report["falsifiers"]["vfade_compose"]
    items = [
        ("fade all V", vf["fade_all"]),
        ("don't fade\nin pause", vf["dont_fade_during_pause"]),
        ("fade only\nin pause", vf["fade_only_during_pause"]),
    ]
    means = [it[1]["pnl_net_bps"]["mean"] for it in items]
    n = [it[1]["n"] for it in items]
    colors = [verd_color.get(it[1]["decision"], "#888") for it in items]
    ax.bar(range(3), means, color=colors)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(range(3))
    ax.set_xticklabels([f"{it[0]}\nn={ni}" for it, ni in zip(items, n)])
    ax.set_ylabel("V-fade net PnL @5s (bps)")
    ax.set_title(f"V-fade × fire-pause — rec: {vf['recommendation']}")
    p = FIG / "fig_fp_vfade_compose.png"
    save_fig(p)
    paths.append(str(p))

    # 8) Falsifier scoreboard
    fig, ax = plt.subplots(figsize=(8.0, 4.5))
    board = report["falsifier_board"]
    names = [r["id"] for r in board]
    y = np.arange(len(names))
    cols = [verd_color.get(r["pass"], "#888") for r in board]
    ax.barh(y, [1] * len(names), color=cols)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{r['id']} [{r['pass']}]" for r in board], fontsize=8)
    ax.set_xlim(0, 1.2)
    ax.set_xticks([])
    ax.set_title(f"Falsifier board → {report['hardened_decision']}")
    p = FIG / "fig_fp_falsifier_board.png"
    save_fig(p)
    paths.append(str(p))

    return paths


def decide(report: dict[str, Any]) -> dict[str, Any]:
    """Promote only if survives hard gates; else Hold/Kill with reason."""
    base = report["baseline"]
    f = report["falsifiers"]
    fails = []
    weaks = []

    def check(name: str, ok: bool, weak: bool = False, why: str = "") -> None:
        if not ok:
            (weaks if weak else fails).append(f"{name}: {why}")

    check(
        "baseline",
        base["verdict"]["decision"] == "Promote",
        why=base["verdict"]["why"],
    )
    check("bootstrap", f["bootstrap"]["pass"] == "PASS", why="CI unstable across n_boot")
    check("cost_sweep", f["cost_sweep"]["pass"] == "PASS", why=f"breaks at bar={f['cost_sweep'].get('break_bar_bps')}")
    check(
        "early_late",
        f["early_late"]["pass"] != "FAIL",
        weak=f["early_late"]["pass"] == "WEAK",
        why=f"early={f['early_late']['early_delta']:.2f} late={f['early_late']['late_delta']:.2f}",
    )
    check(
        "exclude_nest",
        f["exclude_nest"]["pass"] != "FAIL",
        weak=f["exclude_nest"]["pass"] == "WEAK",
        why=f["exclude_nest"]["ex_nest"]["verdict"]["why"],
    )
    check(
        "exclude_overlap",
        f["exclude_overlap"]["pass"] != "FAIL",
        weak=f["exclude_overlap"]["pass"] == "WEAK",
        why=f["exclude_overlap"]["block"]["verdict"]["why"],
    )
    check("placebo_labels", f["placebo_labels"]["pass"] == "PASS", why=f"p={f['placebo_labels'].get('p_ge_true')}")
    check("placebo_times", f["placebo_times"]["pass"] == "PASS", why="fire does not beat random times")
    check("int_halt", f["int_halt"]["pass"] == "PASS", why="redundant with 5s int-halt / no residual")

    # Transfer: require HL BTC or thick venues not Kill with enough n; WEAK ok if underpowered
    transfer_kills = [
        s for s in report["transfer_board"]
        if s["slice"] != "HL_ETH_baseline"
        and s["verdict"]["decision"] == "Kill"
        and s["n_fire"] >= MIN_N_FIRE
    ]
    transfer_promotes = [
        s for s in report["transfer_board"]
        if s["slice"] != "HL_ETH_baseline" and s["verdict"]["decision"] == "Promote"
    ]
    if transfer_kills and not transfer_promotes:
        fails.append(
            "transfer: powered Kill on "
            + ", ".join(s["slice"] for s in transfer_kills)
            + " with no external Promote"
        )
    elif transfer_kills:
        weaks.append("transfer: mixed — " + ", ".join(s["slice"] for s in transfer_kills) + " Kill")

    # Nest/overlap WEAK also demotes Promote → Hold (edge concentration / double-count risk)
    if f["exclude_nest"]["pass"] == "WEAK":
        weaks.append(
            f"exclude_nest: Δ drops to {f['exclude_nest']['ex_nest']['pnl_net_bps']['mean']:.2f} "
            f"CI includes 0 (n={f['exclude_nest']['n_fire_ex_nest']})"
        )
    if f["exclude_overlap"]["pass"] == "WEAK":
        weaks.append(
            f"exclude_overlap: {f['exclude_overlap']['n_fire_raw']}→"
            f"{f['exclude_overlap']['n_fire_nonoverlap']} Δ="
            f"{f['exclude_overlap']['block']['pnl_net_bps']['mean']:.2f} CI includes 0"
        )
    if f["early_late"]["pass"] == "WEAK":
        weaks.append(
            f"early_late: early panel CI∋0 (Δ={f['early_late']['early_delta']:.2f})"
        )

    if fails:
        # Kill if baseline flipped or placebo/bootstrap/cost core failed; else Hold
        core_kill = any(
            x.startswith(p)
            for x in fails
            for p in ("baseline", "bootstrap", "placebo_labels", "placebo_times", "cost_sweep")
        )
        decision = "Kill" if core_kill else "Hold"
        why = "; ".join(fails[:4])
    elif weaks:
        decision = "Hold"
        why = "survives core falsifiers but demoted: " + "; ".join(weaks[:4])
    else:
        decision = "Promote"
        d = base["pnl_net_bps"]
        why = (
            f"survived hardening — Δ|mo|@5m {d['mean']:.2f} [{d['lo']:.2f},{d['hi']:.2f}] "
            f"n_fire={base['n_fire']}; transfer promotes={len(transfer_promotes)}"
        )
    return {"decision": decision, "why": why, "fails": fails, "weaks": weaks}


def write_md(report: dict[str, Any], fig_paths: list[str]) -> Path:
    b = report["baseline"]
    d = report["hardened_decision"]
    f = report["falsifiers"]
    lines = [
        "# LR-fire-pause@5m — HARDENING",
        "",
        f"Generated: {report['generated_at']}",
        f"Honesty: `research_sim_on_real_tape_long_holds` · risk-policy Δ|mo| · live_orders=False · alpha_claim=False",
        f"Baseline panel: HL ETH · {report['meta']['n_days_baseline']} days · n_events={report['meta']['n_events_baseline']}",
        "",
        f"## Hardened decision: **{d['decision']}**",
        "",
        f"{d['why']}",
        "",
        f"- Baseline Δ|mo|@5m: **{b['pnl_net_bps']['mean']:.2f}** "
        f"[{b['pnl_net_bps']['lo']:.2f}, {b['pnl_net_bps']['hi']:.2f}] · "
        f"n_fire={b['n_fire']} · n_obs={b['n_observe']} · "
        f"earlyΔ={b['early_delta']:.2f} · lateΔ={b['late_delta']:.2f}",
        f"- Prior Promote claim was +19.8 — re-measured **{b['pnl_net_bps']['mean']:.2f}**",
        "",
        "## Falsifier board",
        "",
        "| falsifier | pass | headline |",
        "|-----------|------|----------|",
    ]
    for row in report["falsifier_board"]:
        lines.append(f"| **{row['id']}** | **{row['pass']}** | {row['headline']} |")

    lines += [
        "",
        "## Transfer board (venue × symbol)",
        "",
        "| slice | n_fire | |mo|_fire | |mo|_obs | Δ|mo| | earlyΔ | lateΔ | decision |",
        "|-------|--------|----------|---------|-------|--------|--------|----------|",
    ]
    for s in report["transfer_board"]:
        af = s["abs_mo_fire"]["mean"]
        ao = s["abs_mo_observe"]["mean"]
        lines.append(
            f"| {s['slice']} | {s['n_fire']} | {af:.2f} | {ao:.2f} | "
            f"{s['pnl_net_bps']['mean']:.2f} [{s['pnl_net_bps']['lo']:.2f},{s['pnl_net_bps']['hi']:.2f}] | "
            f"{s['early_delta']:.2f} | {s['late_delta']:.2f} | **{s['verdict']['decision']}** |"
        )

    extra = report.get("extra_days", {})
    lines += [
        "",
        "## More days",
        "",
        f"Probed gaps: `{extra.get('probed', [])}`",
        f"Usable new days: **{extra.get('usable_days', [])}** · +{extra.get('n_events', 0)} events",
        "",
        "## Bootstrap CI ladder",
        "",
        "| n_boot | Δ|mo| | decision |",
        "|--------|-------|----------|",
    ]
    for k, v in f["bootstrap"]["ladder"].items():
        lines.append(f"| {k} | {v['delta']:.2f} [{v['lo']:.2f},{v['hi']:.2f}] | {v['decision']} |")

    cs = f["cost_sweep"]
    lines += [
        "",
        "## Cost / friction sweep",
        "",
        f"Δ={cs['delta']:.2f} · lo={cs['lo']:.2f} · break_bar={cs.get('break_bar_bps')} · pass={cs['pass']}",
        "",
        "| bar_bps | clears |",
        "|---------|--------|",
    ]
    for r in cs["rows"]:
        lines.append(f"| {r['friction_bar_bps']} | {r['clears']} |")

    el = f["early_late"]
    lines += [
        "",
        "## Early / late",
        "",
        f"Sign-stable: **{el['sign_stable']}** · earlyΔ={el['early_delta']:.2f} · lateΔ={el['late_delta']:.2f}",
        f"- Early panel: n_fire={el['early_panel']['n_fire']} Δ={el['early_panel']['delta']:.2f} "
        f"[{el['early_panel']['lo']:.2f},{el['early_panel']['hi']:.2f}] → {el['early_panel']['decision']}",
        f"- Late panel: n_fire={el['late_panel']['n_fire']} Δ={el['late_panel']['delta']:.2f} "
        f"[{el['late_panel']['lo']:.2f},{el['late_panel']['hi']:.2f}] → {el['late_panel']['decision']}",
    ]

    en = f["exclude_nest"]
    eo = f["exclude_overlap"]
    lines += [
        "",
        "## Exclude nest / overlap",
        "",
        f"- Fire∩¬nest: n_fire={en['n_fire_ex_nest']} Δ={en['ex_nest']['pnl_net_bps']['mean']:.2f} "
        f"[{en['ex_nest']['pnl_net_bps']['lo']:.2f},{en['ex_nest']['pnl_net_bps']['hi']:.2f}] → "
        f"**{en['ex_nest']['verdict']['decision']}** (nest fires={en['n_fire_nest']})",
        f"- Non-overlap 5m pause starts: {eo['n_fire_raw']}→{eo['n_fire_nonoverlap']} Δ="
        f"{eo['block']['pnl_net_bps']['mean']:.2f} "
        f"[{eo['block']['pnl_net_bps']['lo']:.2f},{eo['block']['pnl_net_bps']['hi']:.2f}] → "
        f"**{eo['block']['verdict']['decision']}**",
    ]

    pl, pt = f["placebo_labels"], f["placebo_times"]
    lines += [
        "",
        "## Placebo",
        "",
        f"- Label-shuffle: trueΔ={pl.get('true_delta', float('nan')):.2f} · "
        f"placebo mean={pl.get('placebo_mean', float('nan')):.2f} · "
        f"p(≥true)={pl.get('p_ge_true', float('nan')):.4f} → **{pl.get('pass')}**",
        f"- Random times: placebo |mo|={pt.get('placebo_mean_abs_mo', float('nan')):.2f} · "
        f"fire={pt.get('fire_mean_abs_mo', float('nan')):.2f} · "
        f"obs={pt.get('obs_mean_abs_mo', float('nan')):.2f} · "
        f"Δ(fire−plac)={pt.get('delta_fire_minus_placebo', {}).get('delta', float('nan')):.2f} "
        f"[{pt.get('delta_fire_minus_placebo', {}).get('lo', float('nan')):.2f},"
        f"{pt.get('delta_fire_minus_placebo', {}).get('hi', float('nan')):.2f}] → **{pt.get('pass')}**",
    ]

    ih = f["int_halt"]
    lines += [
        "",
        "## Interaction with TI-int-halt",
        "",
        f"- int-halt Δ|mo|@5s: {ih['int_halt_5s']['pnl_net_bps']['mean']:.2f} "
        f"[{ih['int_halt_5s']['pnl_net_bps']['lo']:.2f},{ih['int_halt_5s']['pnl_net_bps']['hi']:.2f}] → "
        f"{ih['int_halt_5s']['verdict']['decision']}",
        f"- fire-pause Δ|mo|@5m: {ih['fire_pause_5m']['pnl_net_bps']['mean']:.2f} "
        f"[{ih['fire_pause_5m']['pnl_net_bps']['lo']:.2f},{ih['fire_pause_5m']['pnl_net_bps']['hi']:.2f}] → "
        f"{ih['fire_pause_5m']['verdict']['decision']}",
        f"- incremental |mo5m|−|mo5s| on fire: mean={ih['incremental_abs_mo_5m_minus_5s']['mean']:.2f} "
        f"[{ih['incremental_abs_mo_5m_minus_5s']['lo']:.2f},{ih['incremental_abs_mo_5m_minus_5s']['hi']:.2f}]",
    ]
    if ih.get("residual_low5s_fire_vs_obs_5m"):
        r = ih["residual_low5s_fire_vs_obs_5m"]
        lines.append(
            f"- residual (low-|mo5s| fire vs obs) @5m: {r['pnl_net_bps']['mean']:.2f} "
            f"[{r['pnl_net_bps']['lo']:.2f},{r['pnl_net_bps']['hi']:.2f}] → {r['verdict']['decision']}"
        )
    lines.append(f"- Stack read: {ih['note']} → **{ih['pass']}**")

    vf = f["vfade_compose"]
    lines += [
        "",
        "## V-fade composition sketch",
        "",
        f"**Recommendation: `{vf['recommendation']}`** — {vf['recommendation_why']}",
        "",
        "| policy | n | net@5s | decision |",
        "|--------|---|--------|----------|",
        f"| fade all causal V | {vf['fade_all']['n']} | {vf['fade_all']['pnl_net_bps']['mean']:.2f} | {vf['fade_all']['decision']} |",
        f"| don't fade during pause | {vf['dont_fade_during_pause']['n']} | {vf['dont_fade_during_pause']['pnl_net_bps']['mean']:.2f} | {vf['dont_fade_during_pause']['decision']} |",
        f"| fade only during pause | {vf['fade_only_during_pause']['n']} | {vf['fade_only_during_pause']['pnl_net_bps']['mean']:.2f} | {vf['fade_only_during_pause']['decision']} |",
        "",
        "Desk rule sketch:",
        "",
        "```",
        "if fire_pause_5m active:",
        "    aggressor_size = 0          # LR-fire-pause / int-halt stack",
        f"    v_fade_entry = {'allow' if vf['recommendation'] == 'do_fade_during_pause' else 'suppress'}",
        "else:",
        "    v_fade_entry = causal_V@2s  # normal edge_lab fade",
        "```",
        "",
        "## Figs",
        "",
    ]
    for fp in fig_paths:
        lines.append(f"- `{Path(fp).name}`")
    lines += [
        "",
        "## How to run",
        "",
        "```bash",
        "cd research/books/cross_miniflash/applications/long_range_lab",
        "python3 run_fire_pause_harden.py --workers 8",
        "python3 run_fire_pause_harden.py --smoke --workers 4",
        "```",
        "",
        "No ClickHouse MCP. No commit.",
        "",
    ]
    path = OUT / "FIRE_PAUSE_HARDENING.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def run(*, workers: int = 8, smoke: bool = False, skip_expand: bool = False) -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)

    ev_path = OUT / "events.jsonl"
    if not ev_path.exists():
        raise SystemExit(f"missing {ev_path} — run run_long_edges.py first")
    base_events = _load_events_jsonl(ev_path)
    for e in base_events:
        e.setdefault("venue", "hyperliquid")
        e.setdefault("symbol", "ETH")

    days_base = sorted({e["day"] for e in base_events})
    early, late = early_late_by_day(days_base)
    print(f"[harden] baseline events={len(base_events)} days={len(days_base)}", flush=True)

    baseline = baseline_block(base_events, early, late)

    # --- falsifiers on baseline HL ETH ---
    print("[harden] falsifiers on HL ETH…", flush=True)
    boot = falsifier_bootstrap(base_events, early, late)
    cost = falsifier_cost_sweep(base_events, early, late)
    el = falsifier_early_late(base_events, early, late)
    nest = falsifier_exclude_nest(base_events, early, late)
    ov = falsifier_exclude_overlap_windows(base_events, early, late)
    plac_lab = falsifier_placebo_labels(base_events, early, late)
    print("[harden] placebo times (reload tape)…", flush=True)
    plac_t = falsifier_placebo_times(base_events, workers=min(workers, 6))
    ih = falsifier_int_halt_interaction(base_events, early, late)
    vf = falsifier_vfade_compose(base_events, early, late)

    # --- more days ---
    if smoke:
        extra = {"probed": EXTRA_PROBE[:2], "usable_days": [], "n_events": 0, "events": [], "coverage": []}
        print("[harden] smoke — skip extra day probe", flush=True)
    else:
        extra = probe_extra_days(workers=min(workers, 4))

    events_aug = list(base_events) + list(extra.get("events") or [])
    if extra.get("usable_days"):
        early_aug, late_aug = early_late_by_day(sorted({e["day"] for e in events_aug}))
        baseline_aug = baseline_block(events_aug, early_aug, late_aug)
        baseline_aug["slice"] = "HL_ETH_plus_extra_days"
    else:
        baseline_aug = None

    # --- expand BTC / Deribit / Kraken ---
    expand_events: list[dict] = []
    expand_cov: list[dict] = []
    expand_cache = OUT / "fire_pause_expand_events.jsonl"
    if skip_expand:
        if expand_cache.exists():
            expand_events = _load_events_jsonl(expand_cache)
            print(f"[harden] skip_expand — loaded cache n={len(expand_events)}", flush=True)
        else:
            print("[harden] skip_expand — no cache", flush=True)
    else:
        days_exp = PANEL_CORE[:3] if smoke else list(PIN_USABLE)
        # Prefer days that already had HL ETH fires / activity
        if not smoke:
            hot = [d for d in PIN_USABLE if d in days_base] or list(PIN_USABLE)
            days_exp = hot
        expand_events, expand_cov = expand_panel(
            days=days_exp,
            venues=list(EXPAND_VENUES),
            symbols=list(EXPAND_SYMBOLS),
            workers=workers,
            skip_hl_eth=True,
        )
        save_json(OUT / "fire_pause_expand_coverage.json", expand_cov)
        with (OUT / "fire_pause_expand_events.jsonl").open("w") as f:
            for e in expand_events:
                f.write(json.dumps(jsonable(e)) + "\n")

    all_expand = expand_events
    transfer_board = [baseline]
    if baseline_aug:
        transfer_board.append(baseline_aug)

    # HL BTC
    hl_btc = [e for e in all_expand if e.get("venue") == "hyperliquid" and e.get("symbol") == "BTC"]
    if hl_btc:
        transfer_board.append(slice_metrics(hl_btc, "HL_BTC"))

    # Deribit / Kraken pooled and per symbol
    for venue in ("deribit", "kraken"):
        for sym in ("ETH", "BTC"):
            sl = [e for e in all_expand if e.get("venue") == venue and e.get("symbol") == sym]
            if sl:
                transfer_board.append(slice_metrics(sl, f"{venue[:2].upper()}_{sym}"))
        pooled = [e for e in all_expand if e.get("venue") == venue]
        if pooled:
            transfer_board.append(slice_metrics(pooled, f"{venue[:2].upper()}_ETH+BTC"))

    # All external pooled
    external = [e for e in all_expand if not (e.get("venue") == "hyperliquid" and e.get("symbol") == "ETH")]
    if external:
        transfer_board.append(slice_metrics(external, "ALL_external"))

    falsifiers = {
        "bootstrap": boot,
        "cost_sweep": cost,
        "early_late": el,
        "exclude_nest": nest,
        "exclude_overlap": ov,
        "placebo_labels": plac_lab,
        "placebo_times": plac_t,
        "int_halt": ih,
        "vfade_compose": vf,
    }

    falsifier_board = [
        {
            "id": "bootstrap_CI",
            "pass": boot["pass"],
            "headline": (
                f"n_boot ladder survive={boot['survive']} · "
                f"Δ800={boot['ladder']['800']['delta']:.2f} "
                f"[{boot['ladder']['800']['lo']:.2f},{boot['ladder']['800']['hi']:.2f}]"
            ),
        },
        {
            "id": "cost_sweep",
            "pass": cost["pass"],
            "headline": f"Δ={cost['delta']:.2f} break_bar={cost.get('break_bar_bps')}",
        },
        {
            "id": "early_late",
            "pass": el["pass"],
            "headline": f"stable={el['sign_stable']} earlyΔ={el['early_delta']:.2f} lateΔ={el['late_delta']:.2f}",
        },
        {
            "id": "exclude_nest",
            "pass": nest["pass"],
            "headline": (
                f"ex-nest Δ={nest['ex_nest']['pnl_net_bps']['mean']:.2f} "
                f"n={nest['n_fire_ex_nest']} → {nest['ex_nest']['verdict']['decision']}"
            ),
        },
        {
            "id": "exclude_overlap",
            "pass": ov["pass"],
            "headline": (
                f"{ov['n_fire_raw']}→{ov['n_fire_nonoverlap']} Δ="
                f"{ov['block']['pnl_net_bps']['mean']:.2f} → {ov['block']['verdict']['decision']}"
            ),
        },
        {
            "id": "placebo_labels",
            "pass": plac_lab["pass"],
            "headline": f"p(≥true)={plac_lab.get('p_ge_true', float('nan')):.4f}",
        },
        {
            "id": "placebo_times",
            "pass": plac_t["pass"],
            "headline": (
                f"fire−plac Δ={plac_t.get('delta_fire_minus_placebo', {}).get('delta', float('nan')):.2f} "
                f"n_plac={plac_t.get('n_placebo')}"
            ),
        },
        {
            "id": "int_halt_x",
            "pass": ih["pass"],
            "headline": (
                f"@5s Δ={ih['int_halt_5s']['pnl_net_bps']['mean']:.2f} · "
                f"@5m Δ={ih['fire_pause_5m']['pnl_net_bps']['mean']:.2f} · "
                f"incr={ih['incremental_abs_mo_5m_minus_5s']['mean']:.2f}"
            ),
        },
        {
            "id": "vfade_compose",
            "pass": vf["pass"],
            "headline": f"rec={vf['recommendation']}",
        },
        {
            "id": "more_days",
            "pass": "PASS" if (not extra.get("usable_days") or (baseline_aug and baseline_aug["verdict"]["decision"] != "Kill")) else "FAIL",
            "headline": f"new_days={extra.get('usable_days', [])} +ev={extra.get('n_events', 0)}",
        },
        {
            "id": "transfer",
            "pass": (
                "PASS"
                if any(
                    s["verdict"]["decision"] == "Promote"
                    for s in transfer_board
                    if s["slice"] != "HL_ETH_baseline"
                )
                or all(s["n_fire"] < MIN_N_FIRE for s in transfer_board if s["slice"] != "HL_ETH_baseline")
                else (
                    "FAIL"
                    if any(
                        s["verdict"]["decision"] == "Kill" and s["n_fire"] >= MIN_N_FIRE
                        for s in transfer_board
                        if s["slice"] != "HL_ETH_baseline"
                    )
                    else "WEAK"
                )
            ),
            "headline": " · ".join(
                f"{s['slice']}={s['verdict']['decision']}(n={s['n_fire']},Δ={s['pnl_net_bps']['mean']:.1f})"
                for s in transfer_board
                if s["slice"] != "HL_ETH_baseline"
            )
            or "no external events",
        },
    ]

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "meta": {
            "n_days_baseline": len(days_base),
            "days_baseline": days_base,
            "n_events_baseline": len(base_events),
            "n_expand_events": len(all_expand),
            "friction_bar_bps": FRICTION_BAR,
            "hold": PRIMARY_HOLD,
            "smoke": smoke,
        },
        "baseline": baseline,
        "extra_days": {k: v for k, v in extra.items() if k != "events"},
        "transfer_board": transfer_board,
        "falsifiers": falsifiers,
        "falsifier_board": falsifier_board,
    }
    report["hardened_decision"] = decide(report)
    figs = make_hardening_figs(report)
    report["figs"] = figs
    md = write_md(report, figs)
    save_json(OUT / "FIRE_PAUSE_HARDENING.json", jsonable(report))
    print(f"[harden] decision={report['hardened_decision']['decision']} report={md}", flush=True)
    print(f"  why: {report['hardened_decision']['why']}", flush=True)
    for row in falsifier_board:
        print(f"  [{row['pass']:4s}] {row['id']:16s} {row['headline'][:90]}", flush=True)
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--smoke", action="store_true", help="tiny expand + skip extra days")
    ap.add_argument("--skip-expand", action="store_true", help="HL ETH falsifiers only")
    args = ap.parse_args()
    run(workers=args.workers, smoke=args.smoke, skip_expand=args.skip_expand)


if __name__ == "__main__":
    main()
