"""Richer MM / risk strategy variants — event-study size paths + risk metrics.

Variants:
  - ladder_only
  - v_restore_confirm
  - ladder_plus_v_restore (combined)
  - confirm_before_restore (stricter: need 1s AND 2s V confirm)
  - always_stay_wide / always_restore (baselines)

Friction sweeps: {0, 1, 2, 4} bps one-way haircut on adverse continuation cost.
Score on risk metrics: adverse markout, inventory-proxy exposure in holes, max path DD.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from _common import effect_delta_ci, mean_ci  # type: ignore[import-not-found]

WIDE = 0.25
RESTORE = 1.0
TIER_MULT = {
    "observe": 1.0,
    "widen": 0.5,
    "size_cap": 0.25,
    "halt": 0.0,
    "none": 1.0,
}


def _recovery_flags(e: dict[str, Any]) -> tuple[bool, bool, bool]:
    """Return (confirm_v_1, confirm_v_2, confirm_cont_2).

    Event panel may lack recovery_1s/2s — approximate from recovery@5s + dt for causal honesty.
    When only recovery@5s present: confirm_v_2 ≈ (recovery≥0.5), confirm_v_1 = False
    (conservative — delays restore).
    """
    def _g(k: str) -> float:
        v = e.get(k)
        if v is None:
            return float("nan")
        try:
            x = float(v)
        except (TypeError, ValueError):
            return float("nan")
        return x if np.isfinite(x) else float("nan")

    r = _g("recovery")
    r1 = _g("recovery_1s")
    r2 = _g("recovery_2s")
    if not np.isfinite(r2):
        # proxy: use 5s label but treat as 2s-only confirm (no 1s early restore)
        r2 = r
    conf1 = np.isfinite(r1) and r1 >= 0.5
    conf2 = np.isfinite(r2) and r2 >= 0.5
    conf_cont = np.isfinite(r2) and r2 < 0.2
    return conf1, conf2, conf_cont


def size_path(e: dict[str, Any], policy: str) -> dict[str, float]:
    """Relative quote size at 0.5/1/2/5s after event end."""
    conf1, conf2, conf_cont = _recovery_flags(e)
    tier = str(e.get("tier") or "observe")
    ladder_m = float(TIER_MULT.get(tier, 1.0))
    label = str(e.get("recovery_label") or "")

    def wide():
        return {h: WIDE for h in ("0.5s", "1.0s", "2.0s", "5.0s")}

    def full():
        return {h: RESTORE for h in ("0.5s", "1.0s", "2.0s", "5.0s")}

    if policy == "always_restore":
        return full()
    if policy == "always_stay_wide":
        return wide()
    if policy == "ladder_only":
        return {h: ladder_m for h in ("0.5s", "1.0s", "2.0s", "5.0s")}
    if policy == "v_restore_confirm":
        if conf1:
            return {"0.5s": WIDE, "1.0s": 0.7, "2.0s": RESTORE, "5.0s": RESTORE}
        if conf2:
            return {"0.5s": WIDE, "1.0s": WIDE, "2.0s": 0.85, "5.0s": RESTORE}
        return wide()
    if policy == "confirm_before_restore":
        # stricter: both 1s and 2s (or 2s + label V) before full restore
        if conf1 and conf2:
            return {"0.5s": WIDE, "1.0s": WIDE, "2.0s": 0.7, "5.0s": RESTORE}
        if conf2 and label == "v_recovery":
            return {"0.5s": WIDE, "1.0s": WIDE, "2.0s": WIDE, "5.0s": 0.85}
        return wide()
    if policy == "ladder_plus_v_restore":
        # ladder size floor × V-restore schedule
        base = size_path(e, "v_restore_confirm")
        return {h: min(base[h], ladder_m) if ladder_m > 0 else 0.0 for h in base}
    if policy == "ladder_plus_confirm_before_restore":
        base = size_path(e, "confirm_before_restore")
        return {h: min(base[h], ladder_m) if ladder_m > 0 else 0.0 for h in base}
    raise ValueError(policy)


POLICIES = [
    "always_restore",
    "always_stay_wide",
    "ladder_only",
    "v_restore_confirm",
    "confirm_before_restore",
    "ladder_plus_v_restore",
    "ladder_plus_confirm_before_restore",
]


def _f(x: Any, default: float = float("nan")) -> float:
    if x is None:
        return default
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v if np.isfinite(v) else default


def _score_event(e: dict[str, Any], policy: str, friction_bps: float) -> dict[str, float]:
    sizes = size_path(e, policy)
    mo5 = _f(e.get("mo_5s"))
    mo1 = _f(e.get("mo_1s"))
    # exposure ≈ mean size over path
    exp = float(np.mean(list(sizes.values())))
    # path cost = size@5s × mo5 (crash-direction); friction haircuts fill
    sz5 = sizes["5.0s"]
    fr = friction_bps  # applied as adverse cost floor honesty
    path_cost = sz5 * mo5 if np.isfinite(mo5) else float("nan")
    # adverse = positive mo (continuation in crash direction) × size
    adverse = sz5 * mo5 if np.isfinite(mo5) and mo5 > 0 else 0.0
    if adverse > 0:
        adverse = max(0.0, adverse - fr * sz5)  # friction already paid; net residual
    # inventory-in-holes proxy: exposure while tier elevated or crash window
    hole_inv = exp * (1.0 if e.get("tier") in ("size_cap", "halt") or e.get("nanex_overlap") else 0.5)
    # path DD proxy: worst of size×mo1, size×mo5 when positive
    dd_cands = []
    if np.isfinite(mo1) and mo1 > 0:
        dd_cands.append(sizes["1.0s"] * mo1)
    if np.isfinite(mo5) and mo5 > 0:
        dd_cands.append(sz5 * mo5)
    max_dd = float(max(dd_cands)) if dd_cands else 0.0
    return {
        "exposure": exp,
        "path_cost": path_cost,
        "adverse": adverse,
        "hole_inventory": hole_inv,
        "max_dd": max_dd,
        "size_5s": sz5,
        "mo_5s": mo5,
    }


def score_policies(
    evs: list[dict[str, Any]],
    *,
    friction_grid: tuple[float, ...] = (0.0, 1.0, 2.0, 4.0),
) -> dict[str, Any]:
    if not evs:
        return {"n": 0, "error": "empty"}
    cont = [e for e in evs if e.get("recovery_label") == "continuation"]
    vrec = [e for e in evs if e.get("recovery_label") == "v_recovery"]
    by_pol: dict[str, Any] = {}
    for pol in POLICIES:
        fr_rows = {}
        for fr in friction_grid:
            scores = [_score_event(e, pol, fr) for e in evs]
            cont_s = [_score_event(e, pol, fr) for e in cont]
            adv = np.asarray([s["adverse"] for s in scores], dtype=np.float64)
            hole = np.asarray([s["hole_inventory"] for s in scores], dtype=np.float64)
            dd = np.asarray([s["max_dd"] for s in scores], dtype=np.float64)
            path = np.asarray([s["path_cost"] for s in scores], dtype=np.float64)
            cont_adv = np.asarray([s["adverse"] for s in cont_s], dtype=np.float64)
            fr_rows[str(fr)] = {
                "adverse_mean": mean_ci(adv),
                "cont_adverse_mean": mean_ci(cont_adv) if cont_adv.size else None,
                "hole_inventory_mean": mean_ci(hole),
                "max_dd_mean": mean_ci(dd),
                "path_cost_mean": mean_ci(path[np.isfinite(path)]),
                "exposure_mean": float(np.mean([s["exposure"] for s in scores])),
                "n": len(scores),
                "n_cont": len(cont_s),
            }
        # rank metric at 2bps: continuation adverse (risk), then hole inventory
        primary = fr_rows["2.0"]
        by_pol[pol] = {
            "friction_sweep": fr_rows,
            "rank_cont_adverse": primary["cont_adverse_mean"]["point"]
            if primary.get("cont_adverse_mean")
            else primary["adverse_mean"]["point"],
            "rank_hole_inv": primary["hole_inventory_mean"]["point"],
            "rank_max_dd": primary["max_dd_mean"]["point"],
        }

    # vs always_restore deltas at 2bps
    base_adv = np.asarray(
        [_score_event(e, "always_restore", 2.0)["adverse"] for e in evs], dtype=np.float64
    )
    deltas = {}
    for pol in POLICIES:
        if pol == "always_restore":
            continue
        adv = np.asarray([_score_event(e, pol, 2.0)["adverse"] for e in evs], dtype=np.float64)
        deltas[pol] = effect_delta_ci(adv, base_adv, seed=55 + hash(pol) % 40)

    ranked = sorted(
        POLICIES,
        key=lambda p: (
            by_pol[p]["rank_cont_adverse"] if np.isfinite(by_pol[p]["rank_cont_adverse"]) else 1e9,
            by_pol[p]["rank_max_dd"] if np.isfinite(by_pol[p]["rank_max_dd"]) else 1e9,
            by_pol[p]["rank_hole_inv"] if np.isfinite(by_pol[p]["rank_hole_inv"]) else 1e9,
        ),
    )
    return {
        "n": len(evs),
        "n_cont": len(cont),
        "n_v": len(vrec),
        "policies": by_pol,
        "delta_vs_always_restore_adverse": deltas,
        "ranked_by_risk": ranked,
        "best": ranked[0] if ranked else None,
        "friction_grid": list(friction_grid),
    }
