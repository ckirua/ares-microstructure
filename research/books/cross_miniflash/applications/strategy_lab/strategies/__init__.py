"""Executable strategy stubs for tick/OB backtests (not event studies)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from sim.engine import QuoteIntent  # type: ignore[import-not-found]


@dataclass
class EventClock:
    """Precomputed gated events aligned to tape indices."""

    # for each trade index i: active tier / flags from most recent event still in force
    tier: np.ndarray  # object: observe/widen/size_cap/halt/none
    nanex_active: np.ndarray  # bool — inside pull window after Nanex∩SSM
    crash_active: np.ndarray  # bool — inside post-crash manage window
    recovery_label: np.ndarray  # object at crash onset (unknown until confirm)
    recovery_1s: np.ndarray
    recovery_2s: np.ndarray
    thin_cap: bool = False


def build_event_clock(
    ts: np.ndarray,
    events: dict,
    *,
    ladder_hold_s: float = 60.0,
    nanex_pull_s: float = 15.0,
    crash_manage_s: float = 5.0,
    thin_cap: bool = False,
) -> EventClock:
    n = int(ts.size)
    tier = np.array(["none"] * n, dtype=object)
    nanex = np.zeros(n, dtype=bool)
    crash = np.zeros(n, dtype=bool)
    rec_lab = np.array(["unknown"] * n, dtype=object)
    rec1 = np.full(n, np.nan, dtype=np.float64)
    rec2 = np.full(n, np.nan, dtype=np.float64)

    ts_end = np.asarray(events.get("ts_end", []), dtype=np.int64)
    tiers = list(events.get("tier", []))
    labels = list(events.get("recovery_label", []))
    r1 = np.asarray(events.get("recovery_1s", [np.nan] * len(ts_end)), dtype=np.float64)
    r2 = np.asarray(events.get("recovery_2s", [np.nan] * len(ts_end)), dtype=np.float64)
    nanex_ov = np.asarray(events.get("nanex_overlap", [False] * len(ts_end)), dtype=bool)

    hold = int(ladder_hold_s * 1e9)
    pull = int(nanex_pull_s * 1e9)
    manage = int(crash_manage_s * 1e9)

    for k, t_end in enumerate(ts_end):
        if t_end <= 0:
            continue
        i0 = int(np.searchsorted(ts, t_end, side="left"))
        i1 = int(np.searchsorted(ts, t_end + hold, side="right"))
        tname = str(tiers[k]) if k < len(tiers) else "observe"
        for i in range(max(i0, 0), min(i1, n)):
            # escalate-only overwrite
            cur = tier[i]
            rank = {"none": 0, "observe": 1, "widen": 2, "size_cap": 3, "halt": 4}
            if rank.get(tname, 0) >= rank.get(str(cur), 0):
                tier[i] = tname
        # crash manage window
        j1 = int(np.searchsorted(ts, t_end + manage, side="right"))
        lab = str(labels[k]) if k < len(labels) else "unknown"
        for i in range(max(i0, 0), min(j1, n)):
            crash[i] = True
            rec_lab[i] = lab
            if k < r1.size:
                rec1[i] = r1[k]
            if k < r2.size:
                rec2[i] = r2[k]
        if k < nanex_ov.size and bool(nanex_ov[k]):
            p1 = int(np.searchsorted(ts, t_end + pull, side="right"))
            nanex[max(i0, 0) : min(p1, n)] = True

    return EventClock(
        tier=tier,
        nanex_active=nanex,
        crash_active=crash,
        recovery_label=rec_lab,
        recovery_1s=rec1,
        recovery_2s=rec2,
        thin_cap=thin_cap,
    )


@dataclass
class BaselineMaker:
    """Always-on small maker at touch."""

    base_size: float = 0.25
    name: str = "baseline_maker"

    def reset(self) -> None:
        return None

    def quote(self, i: int, **kw) -> QuoteIntent:
        s = self.base_size
        return QuoteIntent(bid_sz=s, ask_sz=s, pulled=False, regime="normal")


@dataclass
class KillLadderOverlay:
    """Ladder-gated maker: size schedule by observe→widen→size_cap→halt."""

    clock: EventClock
    base_size: float = 0.25
    name: str = "kill_ladder_maker"
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
        t = str(self.clock.tier[i])
        m = float(self.size_mult.get(t, 1.0))
        if m <= 0:
            return QuoteIntent(0.0, 0.0, pulled=True, regime=t)
        s = self.base_size * m
        return QuoteIntent(s, s, pulled=False, regime=t)


@dataclass
class NanexTemporaryPull:
    """Baseline maker with temporary pull on Nanex∩SSM."""

    clock: EventClock
    base_size: float = 0.25
    name: str = "nanex_temp_pull"

    def reset(self) -> None:
        return None

    def quote(self, i: int, **kw) -> QuoteIntent:
        if bool(self.clock.nanex_active[i]):
            return QuoteIntent(0.0, 0.0, pulled=True, regime="nanex_pull")
        s = self.base_size
        return QuoteIntent(s, s, pulled=False, regime="normal")


@dataclass
class VRestoreVsStayWide:
    """After gated crash: stay wide; restore only on causal V confirm @1–2s."""

    clock: EventClock
    base_size: float = 0.25
    wide_mult: float = 0.25
    name: str = "v_restore_confirm"

    def reset(self) -> None:
        return None

    def quote(self, i: int, **kw) -> QuoteIntent:
        if not bool(self.clock.crash_active[i]):
            s = self.base_size
            return QuoteIntent(s, s, pulled=False, regime="normal")
        r1 = float(self.clock.recovery_1s[i])
        r2 = float(self.clock.recovery_2s[i])
        confirm_v = (np.isfinite(r1) and r1 >= 0.5) or (np.isfinite(r2) and r2 >= 0.5)
        if confirm_v:
            s = self.base_size
            return QuoteIntent(s, s, pulled=False, regime="v_restore")
        s = self.base_size * self.wide_mult
        return QuoteIntent(s, s, pulled=False, regime="stay_wide")


@dataclass
class ThinVenueSizeCap:
    """HL thin-excess size-cap overlay (when day flagged thin)."""

    clock: EventClock
    base_size: float = 0.25
    cap_mult: float = 0.25
    name: str = "hl_thin_size_cap"

    def reset(self) -> None:
        return None

    def quote(self, i: int, **kw) -> QuoteIntent:
        s = self.base_size
        regime = "normal"
        if self.clock.thin_cap:
            # tighten further when ladder elevated
            t = str(self.clock.tier[i])
            if t in ("widen", "size_cap", "halt"):
                s = self.base_size * self.cap_mult
                regime = f"thin_cap_{t}"
            else:
                s = self.base_size * 0.5
                regime = "thin_cap"
        return QuoteIntent(s, s, pulled=False, regime=regime)


@dataclass
class AlwaysStayWidePostCrash:
    """Comparator: stay wide through entire crash manage window."""

    clock: EventClock
    base_size: float = 0.25
    wide_mult: float = 0.25
    name: str = "always_stay_wide"

    def reset(self) -> None:
        return None

    def quote(self, i: int, **kw) -> QuoteIntent:
        if bool(self.clock.crash_active[i]):
            s = self.base_size * self.wide_mult
            return QuoteIntent(s, s, pulled=False, regime="stay_wide")
        s = self.base_size
        return QuoteIntent(s, s, pulled=False, regime="normal")


@dataclass
class LadderPlusVRestore:
    """Kill-ladder size floor × V-confirm restore (expanded_lab combined)."""

    clock: EventClock
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
        t = str(self.clock.tier[i])
        ladder_m = float(self.size_mult.get(t, 1.0))
        if ladder_m <= 0:
            return QuoteIntent(0.0, 0.0, pulled=True, regime=f"ladder_{t}")
        if not bool(self.clock.crash_active[i]):
            s = self.base_size * ladder_m
            return QuoteIntent(s, s, pulled=False, regime=t)
        r1 = float(self.clock.recovery_1s[i])
        r2 = float(self.clock.recovery_2s[i])
        confirm_v = (np.isfinite(r1) and r1 >= 0.5) or (np.isfinite(r2) and r2 >= 0.5)
        if confirm_v:
            s = self.base_size * ladder_m
            return QuoteIntent(s, s, pulled=False, regime="ladder_v_restore")
        s = self.base_size * min(self.wide_mult, ladder_m)
        return QuoteIntent(s, s, pulled=False, regime="ladder_stay_wide")


@dataclass
class ConfirmBeforeRestore:
    """Require 1s AND 2s V confirm before full restore."""

    clock: EventClock
    base_size: float = 0.25
    wide_mult: float = 0.25
    name: str = "confirm_before_restore"

    def reset(self) -> None:
        return None

    def quote(self, i: int, **kw) -> QuoteIntent:
        if not bool(self.clock.crash_active[i]):
            s = self.base_size
            return QuoteIntent(s, s, pulled=False, regime="normal")
        r1 = float(self.clock.recovery_1s[i])
        r2 = float(self.clock.recovery_2s[i])
        both = (np.isfinite(r1) and r1 >= 0.5) and (np.isfinite(r2) and r2 >= 0.5)
        if both:
            return QuoteIntent(self.base_size, self.base_size, pulled=False, regime="confirm_restore")
        s = self.base_size * self.wide_mult
        return QuoteIntent(s, s, pulled=False, regime="await_confirm")


@dataclass
class LadderPlusConfirmBeforeRestore:
    """Kill-ladder floor × strict dual-horizon V confirm (expanded_lab best risk playbook)."""

    clock: EventClock
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
        t = str(self.clock.tier[i])
        ladder_m = float(self.size_mult.get(t, 1.0))
        if ladder_m <= 0:
            return QuoteIntent(0.0, 0.0, pulled=True, regime=f"ladder_{t}")
        if not bool(self.clock.crash_active[i]):
            s = self.base_size * ladder_m
            return QuoteIntent(s, s, pulled=False, regime=t)
        r1 = float(self.clock.recovery_1s[i])
        r2 = float(self.clock.recovery_2s[i])
        both = (np.isfinite(r1) and r1 >= 0.5) and (np.isfinite(r2) and r2 >= 0.5)
        if both:
            s = self.base_size * ladder_m
            return QuoteIntent(s, s, pulled=False, regime="ladder_confirm_restore")
        s = self.base_size * min(self.wide_mult, ladder_m)
        return QuoteIntent(s, s, pulled=False, regime="ladder_await_confirm")
