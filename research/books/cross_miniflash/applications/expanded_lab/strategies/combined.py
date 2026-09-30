"""Combined ladder + V-restore quote stubs (strategy_lab-compatible)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Imported by strategy_lab when path includes expanded_lab/strategies
try:
    from sim.engine import QuoteIntent
except ImportError:  # pragma: no cover
    from dataclasses import dataclass as _dc

    @_dc
    class QuoteIntent:  # type: ignore[no-redef]
        bid_sz: float
        ask_sz: float
        pulled: bool = False
        regime: str = "normal"


@dataclass
class LadderPlusVRestore:
    """Kill-ladder size floor × V-confirm restore schedule."""

    clock: object
    base_size: float = 0.25
    wide_mult: float = 0.25
    name: str = "ladder_plus_v_restore"
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
        t = str(self.clock.tier[i])  # type: ignore[attr-defined]
        ladder_m = float(self.size_mult.get(t, 1.0))
        if ladder_m <= 0:
            return QuoteIntent(0.0, 0.0, pulled=True, regime=f"ladder_{t}")
        if not bool(self.clock.crash_active[i]):  # type: ignore[attr-defined]
            s = self.base_size * ladder_m
            return QuoteIntent(s, s, pulled=False, regime=t)
        r1 = float(self.clock.recovery_1s[i])  # type: ignore[attr-defined]
        r2 = float(self.clock.recovery_2s[i])  # type: ignore[attr-defined]
        confirm_v = (np.isfinite(r1) and r1 >= 0.5) or (np.isfinite(r2) and r2 >= 0.5)
        if confirm_v:
            s = self.base_size * ladder_m
            return QuoteIntent(s, s, pulled=False, regime="ladder_v_restore")
        s = self.base_size * min(self.wide_mult, ladder_m)
        return QuoteIntent(s, s, pulled=False, regime="ladder_stay_wide")


@dataclass
class ConfirmBeforeRestore:
    """Stricter: require 1s AND 2s V confirm before full restore; else stay wide."""

    clock: object
    base_size: float = 0.25
    wide_mult: float = 0.25
    name: str = "confirm_before_restore"

    def reset(self) -> None:
        return None

    def quote(self, i: int, **kw) -> QuoteIntent:
        if not bool(self.clock.crash_active[i]):  # type: ignore[attr-defined]
            s = self.base_size
            return QuoteIntent(s, s, pulled=False, regime="normal")
        r1 = float(self.clock.recovery_1s[i])  # type: ignore[attr-defined]
        r2 = float(self.clock.recovery_2s[i])  # type: ignore[attr-defined]
        both = (np.isfinite(r1) and r1 >= 0.5) and (np.isfinite(r2) and r2 >= 0.5)
        if both:
            return QuoteIntent(self.base_size, self.base_size, pulled=False, regime="confirm_restore")
        s = self.base_size * self.wide_mult
        return QuoteIntent(s, s, pulled=False, regime="await_confirm")


@dataclass
class LadderPlusConfirmBeforeRestore:
    """Kill-ladder floor × dual-horizon V confirm (expanded_lab best risk playbook)."""

    clock: object
    base_size: float = 0.25
    wide_mult: float = 0.25
    name: str = "ladder_plus_confirm_before_restore"
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
        t = str(self.clock.tier[i])  # type: ignore[attr-defined]
        ladder_m = float(self.size_mult.get(t, 1.0))
        if ladder_m <= 0:
            return QuoteIntent(0.0, 0.0, pulled=True, regime=f"ladder_{t}")
        if not bool(self.clock.crash_active[i]):  # type: ignore[attr-defined]
            s = self.base_size * ladder_m
            return QuoteIntent(s, s, pulled=False, regime=t)
        r1 = float(self.clock.recovery_1s[i])  # type: ignore[attr-defined]
        r2 = float(self.clock.recovery_2s[i])  # type: ignore[attr-defined]
        both = (np.isfinite(r1) and r1 >= 0.5) and (np.isfinite(r2) and r2 >= 0.5)
        if both:
            s = self.base_size * ladder_m
            return QuoteIntent(s, s, pulled=False, regime="ladder_confirm_restore")
        s = self.base_size * min(self.wide_mult, ladder_m)
        return QuoteIntent(s, s, pulled=False, regime="ladder_await_confirm")
