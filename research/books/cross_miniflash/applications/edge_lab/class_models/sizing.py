"""P(V) → fade size multiplier; OOS PnL after RT=4 vs always-fade / hard V-rule."""

from __future__ import annotations

from typing import Any, Callable

import numpy as np

from _common import mean_ci  # type: ignore  # scripts on path via runner

RT_FRICTION = 4.0


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


def _paired_lift_ci(
    treat: np.ndarray,
    control: np.ndarray,
    *,
    seed: int = 0,
    n_boot: int = 1000,
) -> dict[str, float]:
    """Bootstrap CI on mean(treat − control) paired by event."""
    a = np.asarray(treat, dtype=np.float64)
    b = np.asarray(control, dtype=np.float64)
    m = np.isfinite(a) & np.isfinite(b)
    a, b = a[m], b[m]
    if a.size == 0:
        return {"n": 0, "delta": float("nan"), "lo": float("nan"), "hi": float("nan")}
    d = a - b
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot, dtype=np.float64)
    for i in range(n_boot):
        idx = rng.integers(0, d.size, size=d.size)
        boots[i] = float(d[idx].mean())
    lo, hi = np.quantile(boots, [0.025, 0.975])
    return {
        "n": int(d.size),
        "delta": float(d.mean()),
        "lo": float(lo),
        "hi": float(hi),
        "treat_mean": float(a.mean()),
        "control_mean": float(b.mean()),
    }


def fade_pnl(size: np.ndarray, mo_5s: np.ndarray, *, rt: float = RT_FRICTION) -> np.ndarray:
    """Fade multiplier size≥0: pnl = size * (−mo) − |size| * RT."""
    s = np.asarray(size, dtype=np.float64)
    mo = np.asarray(mo_5s, dtype=np.float64)
    return s * (-mo) - np.abs(s) * rt


def size_always_fade(_: np.ndarray) -> np.ndarray:
    return np.ones_like(_, dtype=np.float64)


def size_hard_v_rule(events: list[dict[str, Any]]) -> np.ndarray:
    return np.asarray([1.0 if e.get("causal") == "v_recovery" else 0.0 for e in events], dtype=np.float64)


def size_soft_linear(p_v: np.ndarray) -> np.ndarray:
    """size = clip(P(V), 0, 1)."""
    return np.clip(np.asarray(p_v, dtype=np.float64), 0.0, 1.0)


def size_soft_centered(p_v: np.ndarray) -> np.ndarray:
    """size = clip(2P−1, 0, 1) — fade only when P(V)>0.5."""
    p = np.asarray(p_v, dtype=np.float64)
    return np.clip(2.0 * p - 1.0, 0.0, 1.0)


def size_soft_piecewise(p_v: np.ndarray) -> np.ndarray:
    """0 / 0.5 / 1 by P(V) bands."""
    p = np.asarray(p_v, dtype=np.float64)
    out = np.zeros_like(p)
    out[p >= 0.40] = 0.5
    out[p >= 0.70] = 1.0
    return out


def size_soft_threshold(p_v: np.ndarray, *, thr: float = 0.55) -> np.ndarray:
    p = np.asarray(p_v, dtype=np.float64)
    return (p >= thr).astype(np.float64)


SIZE_FNS: dict[str, Callable[..., np.ndarray]] = {
    "soft_linear": size_soft_linear,
    "soft_centered": size_soft_centered,
    "soft_piecewise": size_soft_piecewise,
    "soft_thr_0.55": lambda p: size_soft_threshold(p, thr=0.55),
    "soft_thr_0.65": lambda p: size_soft_threshold(p, thr=0.65),
}

# Stable seeds (do not use hash() — PYTHONHASHSEED randomizes str hashes)
_SOFT_SEEDS = {
    "soft_linear": (31, 81, 41),
    "soft_centered": (32, 82, 42),
    "soft_piecewise": (33, 83, 43),
    "soft_thr_0.55": (34, 84, 44),
    "soft_thr_0.65": (35, 85, 45),
}


def evaluate_sizing(
    events: list[dict[str, Any]],
    p_v: np.ndarray,
    te_mask: np.ndarray,
    *,
    model_name: str,
) -> dict[str, Any]:
    """OOS net bps after RT=4 for soft maps vs always-fade / hard V-rule."""
    mo = np.asarray(
        [float(e["mo_5s"]) if e.get("mo_5s") is not None else float("nan") for e in events],
        dtype=np.float64,
    )
    ok = te_mask & np.isfinite(mo) & np.isfinite(p_v)
    if int(ok.sum()) < 15:
        return {"error": "oos_underpowered", "n_oos": int(ok.sum()), "model": model_name}

    idx = np.where(ok)[0]
    mo_o = mo[idx]
    p_o = p_v[idx]
    ev_o = [events[i] for i in idx]

    hard = size_hard_v_rule(ev_o)
    always = np.ones(len(ev_o), dtype=np.float64)
    flat = np.zeros(len(ev_o), dtype=np.float64)

    pnl_hard = fade_pnl(hard, mo_o)
    pnl_always = fade_pnl(always, mo_o)
    pnl_flat = fade_pnl(flat, mo_o)

    rules: dict[str, Any] = {
        "always_fade": {
            "size_mean": float(always.mean()),
            "n_traded": int((always > 0).sum()),
            "pnl": _boot_mean(pnl_always, seed=21),
            "hit_rate": float(np.mean(pnl_always > 0)),
        },
        "hard_v_rule": {
            "size_mean": float(hard.mean()),
            "n_traded": int((hard > 0).sum()),
            "pnl": _boot_mean(pnl_hard, seed=22),
            "hit_rate": float(np.mean(pnl_hard[hard > 0] > 0)) if (hard > 0).any() else float("nan"),
        },
        "always_flat": {
            "size_mean": 0.0,
            "n_traded": 0,
            "pnl": _boot_mean(pnl_flat, seed=23),
            "hit_rate": float("nan"),
        },
    }

    soft_lifts: dict[str, Any] = {}

    for name, fn in SIZE_FNS.items():
        sz = fn(p_o)
        pnl = fade_pnl(sz, mo_o)
        s_hard, s_always, s_pnl = _SOFT_SEEDS[name]
        vs_hard = _paired_lift_ci(pnl, pnl_hard, seed=s_hard)
        vs_always = _paired_lift_ci(pnl, pnl_always, seed=s_always)
        pack = {
            "size_mean": float(np.nanmean(sz)),
            "n_traded": int((sz > 1e-12).sum()),
            "pnl": _boot_mean(pnl, seed=s_pnl),
            "hit_rate": float(np.mean(pnl[sz > 0] > 0)) if (sz > 0).any() else float("nan"),
            "lift_vs_hard_v_rule": vs_hard,
            "lift_vs_always_fade": vs_always,
            "clears_hard": bool(vs_hard["lo"] > 0 and vs_hard["delta"] > 0),
            "clears_always": bool(vs_always["lo"] > 0 and vs_always["delta"] > 0),
        }
        soft_lifts[name] = pack
        rules[name] = pack

    def _soft_rank(item: tuple[str, dict[str, Any]]) -> tuple:
        """Prefer clears-both, then min lower-CI of lifts, then mean net."""
        name, r = item
        both = int(r["clears_hard"] and r["clears_always"])
        one = int(r["clears_hard"] or r["clears_always"])
        min_lo = min(
            float(r["lift_vs_hard_v_rule"].get("lo", float("-inf"))),
            float(r["lift_vs_always_fade"].get("lo", float("-inf"))),
        )
        mean_net = float(r["pnl"].get("mean", float("-inf")))
        return (both, one, min_lo, mean_net)

    primary_soft = max(soft_lifts.items(), key=_soft_rank)[0]
    primary = soft_lifts[primary_soft]
    pnl_primary = fade_pnl(SIZE_FNS[primary_soft](p_o), mo_o)

    # early/late within OOS by day
    days_o = [e["day"] for e in ev_o]
    udays = sorted(set(days_o))
    mid = len(udays) // 2
    early_d, late_d = set(udays[:mid]), set(udays[mid:])

    def _split_mean(pnl: np.ndarray) -> dict[str, float]:
        e = np.asarray([pnl[i] for i, d in enumerate(days_o) if d in early_d], dtype=np.float64)
        l = np.asarray([pnl[i] for i, d in enumerate(days_o) if d in late_d], dtype=np.float64)
        return {
            "early": float(np.nanmean(e)) if e.size else float("nan"),
            "late": float(np.nanmean(l)) if l.size else float("nan"),
            "sign_stable": bool(
                e.size
                and l.size
                and np.isfinite(e.mean())
                and np.isfinite(l.mean())
                and (e.mean() > 0) == (l.mean() > 0)
            ),
        }

    # Fragile clears: require vs_always lo > 0.25 bps so micro-positive CIs stay Hold
    clears_both_robust = bool(
        primary["clears_hard"]
        and primary["clears_always"]
        and float(primary["lift_vs_always_fade"]["lo"]) >= 0.25
        and float(primary["lift_vs_hard_v_rule"]["lo"]) >= 0.25
    )
    clears_both_raw = bool(primary["clears_hard"] and primary["clears_always"])
    promote = bool(
        clears_both_robust
        and primary["pnl"]["mean"] > 0
        and _ci_excludes_zero(primary["pnl"])
        and _split_mean(pnl_primary)["sign_stable"]
    )
    hold_close = bool(
        clears_both_raw
        or (
            (primary["clears_hard"] or primary["clears_always"])
            and primary["pnl"]["mean"] > 0
            and _ci_excludes_zero(primary["pnl"])
        )
    )

    if promote:
        decision = "Promote"
        why = (
            f"OOS soft `{primary_soft}` lift vs hard and vs always-fade both clear robust CI "
            f"(lo≥0.25); net={primary['pnl']['mean']:.2f} bps"
        )
    elif clears_both_raw and not clears_both_robust:
        decision = "Hold"
        why = (
            f"OOS soft `{primary_soft}` clears both baselines only fragile "
            f"(vs_always lo={primary['lift_vs_always_fade']['lo']:.3f} < 0.25 bps robust bar)"
        )
    elif hold_close:
        decision = "Hold"
        why = (
            f"OOS soft `{primary_soft}` clears one baseline but not both "
            f"(vs_hard lo={primary['lift_vs_hard_v_rule']['lo']:.2f}, "
            f"vs_always lo={primary['lift_vs_always_fade']['lo']:.2f})"
        )
    else:
        decision = "Hold"
        why = (
            f"OOS soft-size does not clear lift CI vs hard V-rule / always-fade "
            f"(best={primary_soft} Δhard={primary['lift_vs_hard_v_rule']['delta']:.2f})"
        )

    return {
        "model": model_name,
        "n_oos": int(ok.sum()),
        "rt_friction_bps": RT_FRICTION,
        "p_v_oos": {"mean": float(np.nanmean(p_o)), "sd": float(np.nanstd(p_o))},
        "baselines": {
            "always_fade": rules["always_fade"],
            "hard_v_rule": rules["hard_v_rule"],
            "always_flat": rules["always_flat"],
        },
        "soft_rules": soft_lifts,
        "primary_soft_rule": primary_soft,
        "time_split_primary": _split_mean(pnl_primary),
        "time_split_hard": _split_mean(pnl_hard),
        "time_split_always": _split_mean(pnl_always),
        "verdict": {
            "decision": decision,
            "why": why,
            "promote_requires": (
                "paired lift CI vs hard_v_rule AND always_fade with lo≥0.25 bps each; "
                "net CI>0; early/late sign-stable"
            ),
            "alpha_claim": False,
            "not_mid_ml": True,
        },
        "days_oos": udays,
    }


def _ci_excludes_zero(ci: dict[str, float]) -> bool:
    lo, hi = ci.get("lo"), ci.get("hi")
    if lo is None or hi is None or not np.isfinite(lo) or not np.isfinite(hi):
        return False
    return (lo > 0 and hi > 0) or (lo < 0 and hi < 0)
