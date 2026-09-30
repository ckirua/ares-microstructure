"""Kill-ladder action mapping (risk-policy, venue-local)."""

from __future__ import annotations

from typing import Any

# Desk action sketch — observe → widen → size_cap → halt (+ Nanex escalate)
TIER_ACTIONS: dict[str, dict[str, Any]] = {
    "observe": {
        "action": "log_only",
        "aggressive_takes": "allow",
        "quote_size_mult": 1.0,
        "pull": False,
    },
    "widen": {
        "action": "widen_soft_clip",
        "aggressive_takes": "soft_clip",
        "quote_size_mult": 0.5,
        "pull": False,
    },
    "size_cap": {
        "action": "cap_aggressive_size",
        "aggressive_takes": "size_cap",
        "quote_size_mult": 0.25,
        "pull": False,
    },
    "halt": {
        "action": "halt_aggressive",
        "aggressive_takes": "halt",
        "quote_size_mult": 0.0,
        "pull": True,
    },
}

FIRE_TIERS = frozenset({"widen", "size_cap", "halt"})


def tier_action(tier: str, *, size_mult: dict[str, float] | None = None) -> dict[str, Any]:
    t = str(tier)
    base = dict(TIER_ACTIONS.get(t, TIER_ACTIONS["observe"]))
    base["tier"] = t
    if size_mult and t in size_mult:
        base["quote_size_mult"] = float(size_mult[t])
        if float(size_mult[t]) <= 0:
            base["pull"] = True
            base["action"] = "halt_aggressive"
            base["aggressive_takes"] = "halt"
    return base


def apply_nest_hard_pause(rec: dict[str, Any]) -> dict[str, Any]:
    """TI-nanex-nest: Nanex∩SSM → size→0 / pull even if tier is only widen."""
    out = dict(rec)
    out["escalate"] = "nanex_intersect_ssm"
    out["nest_hard_pause"] = True
    out["quote_size_mult"] = 0.0
    out["pull"] = True
    out["aggressive_takes"] = "halt"
    out["action"] = "nest_hard_pause"
    return out


def event_action_records(
    cell: dict[str, Any],
    *,
    size_mult: dict[str, float] | None = None,
    nest_hard_pause: bool = True,
) -> list[dict[str, Any]]:
    """One JSONL-able record per gated event (detector → ladder action)."""
    ev = cell.get("events") or {}
    n = int(len(ev.get("ts_end", [])))
    out: list[dict[str, Any]] = []
    for i in range(n):
        tier = str(ev["tier"][i]) if i < len(ev.get("tier", [])) else "observe"
        act = tier_action(tier, size_mult=size_mult)
        nanex = bool(ev["nanex_overlap"][i]) if i < len(ev.get("nanex_overlap", [])) else False
        rec = {
            "kind": "ladder_fire" if tier in FIRE_TIERS else "ladder_observe",
            "day": cell.get("day"),
            "symbol": cell.get("symbol"),
            "venue": cell.get("venue"),
            "event_i": i,
            "ts_start": int(ev["ts_start"][i]),
            "ts_end": int(ev["ts_end"][i]),
            "z_peak": float(ev["z_peak"][i]),
            "dp_pct": float(ev["dp_pct"][i]),
            "i_c": int(ev["i_c"][i]),
            "intensity_60s": int(ev["intensity_60s"][i]),
            "direction": int(ev["direction"][i]),
            "nanex_overlap": nanex,
            "recovery": float(ev["recovery"][i]) if i < len(ev.get("recovery", [])) else None,
            "recovery_label": str(ev["recovery_label"][i])
            if i < len(ev.get("recovery_label", []))
            else None,
            "mo_1s": float(ev["mo_1s"][i]) if i < len(ev.get("mo_1s", [])) else None,
            "mo_5s": float(ev["mo_5s"][i]) if i < len(ev.get("mo_5s", [])) else None,
            **act,
        }
        if nanex:
            if nest_hard_pause:
                # Preferred policy: hard 0 on any Nanex∩SSM (even widen-only).
                rec = apply_nest_hard_pause(rec)
            elif tier in FIRE_TIERS:
                rec["escalate"] = "nanex_intersect_ssm"
        out.append(rec)
    return out
