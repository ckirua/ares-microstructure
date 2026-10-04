"""Kill criteria K1–K8 from V_FADE_STRATEGY_SPEC §7."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np


def _boot_mean(arr: np.ndarray, *, seed: int = 0, n_boot: int = 800) -> dict[str, float]:
    """Bootstrap mean CI — same recipe as edge_lab (_verdict / mean_ci)."""
    a = np.asarray(arr, dtype=np.float64)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return {"n": 0, "mean": float("nan"), "lo": float("nan"), "hi": float("nan"), "sd": float("nan")}
    # Prefer ares_micro / _common if importable
    try:
        import sys
        from pathlib import Path

        scripts = Path(__file__).resolve().parents[3] / "scripts"
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        from _common import mean_ci  # noqa: WPS433

        ci = mean_ci(a, n_boot=n_boot, seed=seed)
        return {
            "n": int(ci.get("n", a.size)),
            "mean": float(ci.get("point", np.nanmean(a))),
            "lo": float(ci.get("lo", float("nan"))),
            "hi": float(ci.get("hi", float("nan"))),
            "sd": float(np.std(a, ddof=1)) if a.size > 1 else 0.0,
        }
    except Exception:  # noqa: BLE001
        rng = np.random.default_rng(seed)
        boots = np.empty(n_boot, dtype=np.float64)
        for b in range(n_boot):
            boots[b] = float(np.mean(rng.choice(a, size=a.size, replace=True)))
        lo, hi = np.percentile(boots, [2.5, 97.5])
        return {
            "n": int(a.size),
            "mean": float(np.mean(a)),
            "lo": float(lo),
            "hi": float(hi),
            "sd": float(np.std(a, ddof=1)) if a.size > 1 else 0.0,
        }


def _ci_includes_zero(ci: dict[str, float]) -> bool:
    lo, hi = ci.get("lo"), ci.get("hi")
    if lo is None or hi is None or not np.isfinite(lo) or not np.isfinite(hi):
        return True  # treat unknown as not excluding 0
    return lo <= 0 <= hi


def evaluate_kills(
    trades: list[dict[str, Any]],
    *,
    cfg: dict[str, Any],
    early_days: set[str] | None = None,
    late_days: set[str] | None = None,
    live_orders: bool = False,
    sigma_m_floor_hit: bool | None = None,
    detector_skip: bool = False,
) -> dict[str, Any]:
    """Wire spec §7 kill criteria as boolean flags + overall decision."""
    kcfg = dict(cfg.get("kill") or {})
    vf = dict(cfg.get("v_fade") or {})
    early = early_days or set(vf.get("early_days") or [])
    late = late_days or set(vf.get("late_days") or [])

    pnls = np.asarray(
        [t["lab_pnl_net_bps"] for t in trades if t.get("lab_pnl_net_bps") is not None],
        dtype=np.float64,
    )
    pnls = pnls[np.isfinite(pnls)]
    n = int(pnls.size)

    n_boot = int(kcfg.get("k2_n_boot") or vf.get("n_boot") or 800)
    ci = _boot_mean(pnls, seed=42, n_boot=n_boot)

    # Early / late
    e_pnls = np.asarray(
        [
            float(t["lab_pnl_net_bps"])
            for t in trades
            if t.get("day") in early and t.get("lab_pnl_net_bps") is not None
        ],
        dtype=np.float64,
    )
    l_pnls = np.asarray(
        [
            float(t["lab_pnl_net_bps"])
            for t in trades
            if t.get("day") in late and t.get("lab_pnl_net_bps") is not None
        ],
        dtype=np.float64,
    )
    e_pnls = e_pnls[np.isfinite(e_pnls)]
    l_pnls = l_pnls[np.isfinite(l_pnls)]
    early_mean = float(np.mean(e_pnls)) if e_pnls.size else float("nan")
    late_mean = float(np.mean(l_pnls)) if l_pnls.size else float("nan")
    sign_flip = (
        np.isfinite(early_mean)
        and np.isfinite(late_mean)
        and early_mean != 0
        and late_mean != 0
        and (early_mean > 0) != (late_mean > 0)
    )

    hit_rate = float(np.mean(pnls > 0)) if n else float("nan")
    adverse_n = sum(1 for t in trades if t.get("exit_reason") == "adverse_stop")
    adverse_share = float(adverse_n / len(trades)) if trades else float("nan")

    # K1: rolling 5-day mean net ≤ 0 with n≥20
    by_day: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        if t.get("lab_pnl_net_bps") is None:
            continue
        v = float(t["lab_pnl_net_bps"])
        if np.isfinite(v):
            by_day[str(t["day"])].append(v)
    days_sorted = sorted(by_day.keys())
    roll_n = int(kcfg.get("k1_rolling_days", 5))
    k1_min_n = int(kcfg.get("k1_min_n", 20))
    k1_trip = False
    k1_detail: dict[str, Any] = {"windows": []}
    if len(days_sorted) >= 1:
        # sliding window over available calendar days
        for i in range(len(days_sorted)):
            window = days_sorted[max(0, i + 1 - roll_n) : i + 1]
            if len(window) < min(roll_n, len(days_sorted)):
                # still evaluate if we have all available days and they span the panel
                pass
            xs = [x for d in window for x in by_day[d]]
            if len(xs) >= k1_min_n and float(np.mean(xs)) <= 0:
                k1_trip = True
                k1_detail["windows"].append(
                    {"days": window, "n": len(xs), "mean": float(np.mean(xs))}
                )
        # Also: if total panel days ≤ roll_n, evaluate full sample
        all_xs = [x for d in days_sorted for x in by_day[d]]
        if len(days_sorted) <= roll_n and len(all_xs) >= k1_min_n and float(np.mean(all_xs)) <= 0:
            k1_trip = True
            k1_detail["windows"].append(
                {"days": days_sorted, "n": len(all_xs), "mean": float(np.mean(all_xs))}
            )

    # K2: CI∋0 kills only when powered (n≥20); underpowered → Hold via decision ladder
    k2_min_n = int(kcfg.get("k1_min_n", 20))
    k2_trip = n >= k2_min_n and _ci_includes_zero(ci)
    k3_trip = bool(sign_flip) and (int(e_pnls.size) + int(l_pnls.size) >= k2_min_n)

    k4_min = int(kcfg.get("k4_min_n", 40))
    k4_kill = float(kcfg.get("k4_hit_rate_kill", 0.55))
    k4_warn = float(kcfg.get("k4_hit_rate_warn", 0.65))
    k4_trip = bool(n >= k4_min and np.isfinite(hit_rate) and hit_rate < k4_kill)
    k4_warn_flag = bool(n >= k4_min and np.isfinite(hit_rate) and hit_rate < k4_warn)

    k5_min = int(kcfg.get("k5_min_n", 30))
    k5_thr = float(kcfg.get("k5_adverse_share", 0.40))
    k5_trip = bool(
        len(trades) >= k5_min and np.isfinite(adverse_share) and adverse_share > k5_thr
    )

    # K6: realized one-way cost proxy — paper uses fixed 2bps; trip if config > thr
    one_way = float(vf.get("friction_bps_one_way", 2.0))
    k6_thr = float(kcfg.get("k6_median_one_way_bps", 5.0))
    k6_trip = bool(one_way > k6_thr)

    k7_trip = bool(detector_skip) or (sigma_m_floor_hit is False)
    # sigma_m_floor_hit True means floor engaged (OK); False/None = unknown/off
    # Spec: "Gate violation / σ_m floor off / detector skip storm"
    if sigma_m_floor_hit is False:
        k7_trip = True

    k8_trip = bool(live_orders)

    flags = {
        "K1_rolling_mean_nonpositive": k1_trip,
        "K2_ci_includes_zero": k2_trip,
        "K3_early_late_sign_flip": k3_trip,
        "K4_hit_rate_below_kill": k4_trip,
        "K5_adverse_stop_share_high": k5_trip,
        "K6_friction_blowout": k6_trip,
        "K7_infra_gate_or_detector": k7_trip,
        "K8_live_orders_enabled": k8_trip,
    }
    warns = {
        "K4_hit_rate_soft_warn": k4_warn_flag and not k4_trip,
    }
    any_kill = any(flags.values())
    decision = "Kill" if any_kill else ("Hold" if n < 20 else "Promote_shadow")

    return {
        "decision": decision,
        "any_kill": any_kill,
        "flags": flags,
        "warns": warns,
        "n_faded": n,
        "pnl_ci": ci,
        "early_mean": early_mean,
        "late_mean": late_mean,
        "hit_rate": hit_rate,
        "adverse_share": adverse_share,
        "adverse_n": adverse_n,
        "one_way_cost_bps": one_way,
        "k1_detail": k1_detail,
        "early_n": int(e_pnls.size),
        "late_n": int(l_pnls.size),
    }
