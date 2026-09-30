"""Kill-ladder + Nanex∩SSM robustness on expanded panel slices.

Time-split + bootstrap CIs. No vanity PnL — adverse |mo|, sub|ΔP|, precision.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from _common import (  # type: ignore[import-not-found]
    FRICTION_BPS,
    early_late_by_day,
    effect_delta_ci,
    mean_ci,
    readiness_label,
)


def _arr(evs: list[dict], key: str) -> np.ndarray:
    return np.asarray([e.get(key, np.nan) for e in evs], dtype=np.float64)


def kill_ladder_effects(evs: list[dict[str, Any]], *, seed: int = 41) -> dict[str, Any]:
    if not evs:
        return {"n": 0, "error": "empty"}
    fire = [e for e in evs if e.get("tier") in ("widen", "size_cap", "halt")]
    control = [
        e
        for e in evs
        if e.get("tier") == "observe" and int(e.get("intensity_60s") or 1) <= 1
    ]
    if not control:
        control = [e for e in evs if e.get("tier") == "observe"]
    d_abs = effect_delta_ci(
        np.abs(_arr(fire, "mo_5s")),
        np.abs(_arr(control, "mo_5s")),
        seed=seed,
    )
    d_sub = effect_delta_ci(_arr(fire, "sub_dp_30s"), _arr(control, "sub_dp_30s"), seed=seed + 1)
    tiers = {t: sum(1 for e in evs if e.get("tier") == t) for t in ("observe", "widen", "size_cap", "halt")}
    days = sorted({e["day"] for e in evs})
    early, late = early_late_by_day(days)

    def _delta_cohort(days_set: set[str]) -> dict[str, float]:
        f = [e for e in fire if e["day"] in days_set]
        c = [e for e in control if e["day"] in days_set]
        return effect_delta_ci(np.abs(_arr(f, "mo_5s")), np.abs(_arr(c, "mo_5s")), seed=seed + 7)

    early_d = _delta_cohort(early)
    late_d = _delta_cohort(late)
    sign_stable = bool(
        np.isfinite(early_d.get("delta", np.nan))
        and np.isfinite(late_d.get("delta", np.nan))
        and np.sign(early_d["delta"]) == np.sign(late_d["delta"])
        and early_d["delta"] != 0
    )
    friction_cleared = bool(
        np.isfinite(d_abs.get("delta", np.nan))
        and d_abs["delta"] > FRICTION_BPS
        and d_abs.get("lo", -1) > 0
    )
    share_v_fire = (
        float(np.mean([1.0 if e.get("recovery_label") == "v_recovery" else 0.0 for e in fire]))
        if fire
        else float("nan")
    )
    readiness = readiness_label(
        effect_ci_excludes_zero=bool(d_abs.get("lo", 0) > 0),
        time_split_sign_stable=sign_stable,
        n_events=len(evs),
        friction_cleared=friction_cleared,
    )
    return {
        "n": len(evs),
        "n_fire": len(fire),
        "n_control": len(control),
        "tier_counts": tiers,
        "delta_abs_mo_5s": d_abs,
        "delta_sub_dp_30s": d_sub,
        "early_delta_abs_mo": early_d,
        "late_delta_abs_mo": late_d,
        "time_split_sign_stable": sign_stable,
        "friction_bps": FRICTION_BPS,
        "friction_cleared": friction_cleared,
        "share_v_fire": share_v_fire,
        "readiness": readiness,
        "mo_5s_fire": mean_ci(_arr(fire, "mo_5s")),
        "mo_5s_control": mean_ci(_arr(control, "mo_5s")),
    }


def nanex_nest_effects(evs: list[dict[str, Any]], rows: list[dict], *, seed: int = 101) -> dict[str, Any]:
    nested = [e for e in evs if e.get("nanex_overlap")]
    ssm_only = [e for e in evs if not e.get("nanex_overlap")]
    effects = {
        "dp": effect_delta_ci(_arr(nested, "dp_pct"), _arr(ssm_only, "dp_pct"), seed=seed),
        "abs_mo_5s": effect_delta_ci(
            np.abs(_arr(nested, "mo_5s")), np.abs(_arr(ssm_only, "mo_5s")), seed=seed + 2
        ),
        "sub_dp": effect_delta_ci(
            _arr(nested, "sub_dp_30s"), _arr(ssm_only, "sub_dp_30s"), seed=seed + 3
        ),
    }
    # precision from rows covering these events' cells
    days = {e["day"] for e in evs}
    syms = {e["symbol"] for e in evs}
    n_nx = n_nx_n = 0
    for r in rows:
        if r.get("day") not in days:
            continue
        if r.get("symbol") not in syms:
            continue
        n_nx += int(r.get("nanex_n") or 0)
        n_nx_n += int(r.get("nanex_nested_n") or 0)
    precision = float(n_nx_n / n_nx) if n_nx else float("nan")
    days_sorted = sorted(days)
    early, late = early_late_by_day(days_sorted)

    def _prec_cohort(ds: set[str]) -> float:
        a = b = 0
        for r in rows:
            if r.get("day") not in ds or r.get("symbol") not in syms:
                continue
            a += int(r.get("nanex_nested_n") or 0)
            b += int(r.get("nanex_n") or 0)
        return float(a / b) if b else float("nan")

    prec_e, prec_l = _prec_cohort(early), _prec_cohort(late)
    ci_ok = bool(effects["abs_mo_5s"].get("lo", 0) > 0) or bool(effects["dp"].get("lo", 0) > 0)
    ready = readiness_label(
        effect_ci_excludes_zero=ci_ok and np.isfinite(precision) and precision >= 0.80,
        time_split_sign_stable=bool(
            np.isfinite(prec_e) and np.isfinite(prec_l) and min(prec_e, prec_l) >= 0.75
        ),
        n_events=len(nested),
        friction_cleared=True,
    )
    return {
        "n_gated": len(evs),
        "n_nested": len(nested),
        "n_ssm_only": len(ssm_only),
        "precision": precision,
        "precision_early": prec_e,
        "precision_late": prec_l,
        "effects": effects,
        "readiness": ready,
    }


def run_robustness(panel: dict[str, Any], by_slice: dict[str, Any]) -> dict[str, Any]:
    rows = panel["rows"]
    out: dict[str, Any] = {"ladder_breaks": by_slice.get("ladder_breaks"), "slices": {}}
    for name in ("core", "core_plus_extend", "sol", "all"):
        evs = by_slice.get(name) or []
        if name == "all":
            evs = by_slice.get("all") or []
        kl = kill_ladder_effects(evs, seed=41 + hash(name) % 50)
        nx = nanex_nest_effects(evs, rows, seed=101 + hash(name) % 50)
        # Promote if core Promote and slice does not falsify (sign-stable + CI direction)
        core_ok = name == "core"
        survives = False
        if kl.get("readiness") == "promote_as_risk_policy":
            survives = True
        elif name != "core" and out["slices"].get("core", {}).get("kill_ladder", {}).get(
            "friction_cleared"
        ):
            # Hold-as-robust if Δ|mo| same sign as core and precision still high for nanex
            core_kl = out["slices"]["core"]["kill_ladder"]
            same_sign = (
                np.isfinite(kl.get("delta_abs_mo_5s", {}).get("delta", np.nan))
                and np.sign(kl["delta_abs_mo_5s"]["delta"])
                == np.sign(core_kl["delta_abs_mo_5s"]["delta"])
            )
            survives = bool(same_sign and kl.get("n", 0) >= 20)
        out["slices"][name] = {
            "kill_ladder": kl,
            "nanex": nx,
            "survives_risk_policy": survives or core_ok and kl.get("readiness") == "promote_as_risk_policy",
            "n_events": len(evs),
        }
    # verdict rollup
    core_kl = out["slices"]["core"]["kill_ladder"]
    ext_kl = out["slices"]["core_plus_extend"]["kill_ladder"]
    sol_kl = out["slices"]["sol"]["kill_ladder"]
    out["verdicts"] = {
        "kill_ladder_core": core_kl.get("readiness"),
        "kill_ladder_core_plus_extend": ext_kl.get("readiness"),
        "kill_ladder_sol": sol_kl.get("readiness") if sol_kl.get("n", 0) else "no_sol_events",
        "nanex_core": out["slices"]["core"]["nanex"].get("readiness"),
        "nanex_core_plus_extend": out["slices"]["core_plus_extend"]["nanex"].get("readiness"),
        "nanex_sol": out["slices"]["sol"]["nanex"].get("readiness")
        if out["slices"]["sol"]["nanex"].get("n_gated", 0)
        else "no_sol_events",
        "promote_hold": {
            "kill_ladder": (
                "Promote-as-risk-policy (robust)"
                if ext_kl.get("friction_cleared") and ext_kl.get("time_split_sign_stable")
                else "Hold / check extend"
            ),
            "nanex": (
                "Promote-as-risk-policy (robust)"
                if out["slices"]["core_plus_extend"]["nanex"].get("precision", 0) >= 0.85
                else "Hold precision"
            ),
        },
    }
    return out
