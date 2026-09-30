"""RISK_GATE_STACK combined throttle — size → 0.25 / 0 / pause.

Layers (max severity wins, never average):
  1. TI-int-halt / kill_ladder tier → size_mult {1, 0.5, 0.25, 0}
  2. nest_hard_pause (Nanex∩SSM) → effective_mult = 0
  3. LR-fire-pause@5m → effective_mult = 0 for 300s from fire onset

Risk-policy overlay only — not directional PnL / tradable alpha.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

# strategy_lab provides sim.* / strategies (same as shadow_fills)
_LAB = Path(__file__).resolve().parents[2] / "strategy_lab"
if str(_LAB) not in sys.path:
    sys.path.insert(0, str(_LAB))

from sim.engine import QuoteIntent  # type: ignore[import-not-found]
from strategies import EventClock, build_event_clock  # type: ignore[import-not-found]

FIRE_TIERS = frozenset({"widen", "size_cap", "halt"})
NS = 1_000_000_000


@dataclass
class RiskGateClock:
    """EventClock + fire_pause_5m bit + nest_hard policy flag."""

    tier: np.ndarray
    nanex_active: np.ndarray
    fire_pause_active: np.ndarray
    crash_active: np.ndarray
    recovery_label: np.ndarray
    recovery_1s: np.ndarray
    recovery_2s: np.ndarray
    nest_hard_pause: bool = True
    fire_pause_s: float = 300.0
    thin_cap: bool = False

    @classmethod
    def from_event_clock(
        cls,
        clock: EventClock,
        fire_pause_active: np.ndarray,
        *,
        nest_hard_pause: bool = True,
        fire_pause_s: float = 300.0,
    ) -> "RiskGateClock":
        return cls(
            tier=clock.tier,
            nanex_active=clock.nanex_active,
            fire_pause_active=np.asarray(fire_pause_active, dtype=bool),
            crash_active=clock.crash_active,
            recovery_label=clock.recovery_label,
            recovery_1s=clock.recovery_1s,
            recovery_2s=clock.recovery_2s,
            nest_hard_pause=bool(nest_hard_pause),
            fire_pause_s=float(fire_pause_s),
            thin_cap=bool(getattr(clock, "thin_cap", False)),
        )


def _fire_pause_mask(
    ts: np.ndarray,
    events: dict[str, Any],
    *,
    fire_pause_s: float,
) -> np.ndarray:
    """Union of [ts_end, ts_end + fire_pause_s) over fire-tier gated events."""
    n = int(ts.size)
    out = np.zeros(n, dtype=bool)
    if fire_pause_s <= 0 or n == 0:
        return out
    ts_end = np.asarray(events.get("ts_end", []), dtype=np.int64)
    tiers = list(events.get("tier", []))
    hold = int(float(fire_pause_s) * NS)
    for k, t_end in enumerate(ts_end):
        if t_end <= 0:
            continue
        tname = str(tiers[k]) if k < len(tiers) else "observe"
        if tname not in FIRE_TIERS:
            continue
        i0 = int(np.searchsorted(ts, t_end, side="left"))
        i1 = int(np.searchsorted(ts, int(t_end) + hold, side="right"))
        out[max(i0, 0) : min(i1, n)] = True
    return out


def build_risk_gate_clock(
    ts: np.ndarray,
    events: dict[str, Any],
    *,
    ladder_hold_s: float = 60.0,
    nanex_pull_s: float = 15.0,
    fire_pause_s: float = 300.0,
    nest_hard_pause: bool = True,
    crash_manage_s: float = 5.0,
) -> RiskGateClock:
    """Shared detect clock + parallel 5m fire-pause overlay."""
    base = build_event_clock(
        ts,
        events,
        ladder_hold_s=float(ladder_hold_s),
        nanex_pull_s=float(nanex_pull_s),
        crash_manage_s=float(crash_manage_s),
    )
    # Nest hard: keep Nanex∩SSM pull bit; optionally extend to full ladder_hold
    # while nest is live (nanex_pull_s is the minimum desk pull).
    fire_pause = _fire_pause_mask(ts, events, fire_pause_s=float(fire_pause_s))
    return RiskGateClock.from_event_clock(
        base,
        fire_pause,
        nest_hard_pause=bool(nest_hard_pause),
        fire_pause_s=float(fire_pause_s),
    )


def effective_mult_at(
    i: int,
    clock: RiskGateClock,
    size_mult: dict[str, float],
) -> tuple[float, str]:
    """Return (size_mult, regime_label) with max-severity wins.

    Cut rules:
      → 0.25 : ladder size_cap (or widen if desk collapsed half→quarter)
      → 0    : ladder halt · OR nest_hard_pause · OR fire_pause_5m
    """
    t = str(clock.tier[i])
    ladder_m = float(size_mult.get(t, size_mult.get("none", 1.0)))
    if bool(clock.fire_pause_active[i]):
        return 0.0, "fire_pause_5m"
    if bool(clock.nest_hard_pause) and bool(clock.nanex_active[i]):
        return 0.0, "nest_hard_pause"
    if ladder_m <= 0:
        return 0.0, t if t != "none" else "halt"
    return ladder_m, t


def clock_regime_counts(clock: RiskGateClock) -> dict[str, int]:
    n = int(clock.tier.size)
    counts = {
        "none": 0,
        "observe": 0,
        "widen": 0,
        "size_cap": 0,
        "halt": 0,
        "nest_hard_pause": 0,
        "fire_pause_5m": 0,
    }
    sm = {"none": 1.0, "observe": 1.0, "widen": 0.5, "size_cap": 0.25, "halt": 0.0}
    for i in range(n):
        _, regime = effective_mult_at(i, clock, sm)
        if regime in counts:
            counts[regime] += 1
        else:
            counts[regime] = counts.get(regime, 0) + 1
    return counts


def fire_pause_action_records(
    cell: dict[str, Any],
    *,
    fire_pause_s: float = 300.0,
) -> list[dict[str, Any]]:
    """One actions.jsonl record per fire onset that arms the 5m pause clock."""
    ev = cell.get("events") or {}
    n = int(len(ev.get("ts_end", [])))
    out: list[dict[str, Any]] = []
    hold_ns = int(float(fire_pause_s) * NS)
    for i in range(n):
        tier = str(ev["tier"][i]) if i < len(ev.get("tier", [])) else "observe"
        if tier not in FIRE_TIERS:
            continue
        ts_end = int(ev["ts_end"][i])
        out.append(
            {
                "kind": "fire_pause_5m",
                "day": cell.get("day"),
                "symbol": cell.get("symbol"),
                "venue": cell.get("venue"),
                "event_i": i,
                "tier": tier,
                "ts_start": ts_end,
                "ts_end": ts_end + hold_ns,
                "pause_s": float(fire_pause_s),
                "quote_size_mult": 0.0,
                "pull": True,
                "aggressive_takes": "halt",
                "action": "fire_pause_5m",
                "z_peak": float(ev["z_peak"][i]) if i < len(ev.get("z_peak", [])) else None,
                "intensity_60s": int(ev["intensity_60s"][i])
                if i < len(ev.get("intensity_60s", []))
                else None,
                "mo_5s": float(ev["mo_5s"][i]) if i < len(ev.get("mo_5s", [])) else None,
            }
        )
    return out


@dataclass
class RiskGateStackOverlay:
    """Combined MONEY-SAVING throttle maker (ladder ∩ nest_hard ∩ fire_pause_5m)."""

    clock: RiskGateClock
    base_size: float = 0.25
    name: str = "risk_gate_stack"
    size_mult: dict = field(
        default_factory=lambda: {
            "none": 1.0,
            "observe": 1.0,
            "widen": 0.5,
            "size_cap": 0.25,
            "halt": 0.0,
        }
    )

    def reset(self) -> None:
        return None

    def quote(self, i: int, **kw) -> QuoteIntent:
        m, regime = effective_mult_at(i, self.clock, self.size_mult)
        if m <= 0:
            return QuoteIntent(0.0, 0.0, pulled=True, regime=regime)
        s = self.base_size * m
        return QuoteIntent(s, s, pulled=False, regime=regime)
