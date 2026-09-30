"""severity_zend V-fade shadow fills on incremental gated events.

Promote_shadow: |z_peak|≥20 @ ts_end+0.5s → exit ts_end+3s; live_orders=false.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .incremental_ssm import GatedEvent

LOG = logging.getLogger("tick_shadow")
NS = 1_000_000_000
FIRE_TIERS = frozenset({"widen", "size_cap", "halt"})


@dataclass
class OpenFade:
    event_i: int
    direction: int  # crash direction; fade side = -direction
    z_peak: float
    ts_end: int
    entry_t: int
    exit_t: int
    tier: str
    entry_px: float | None = None
    entry_fill_ts: int | None = None
    exit_px: float | None = None
    exit_fill_ts: int | None = None
    exit_reason: str | None = None


@dataclass
class SeverityZendSleeve:
    z_min: float = 20.0
    confirm_s: float = 0.5
    exit_s: float = 3.0
    rt_friction_bps: float = 4.0
    adverse_stop_bps: float = 1e9
    max_concurrent: int = 1
    fire_pause_s: float = 300.0
    fire_pause_mode: str = "prior_only"
    trades_path: Path | None = None

    n_candidates: int = 0
    n_severity_skip: int = 0
    n_fire_skip: int = 0
    n_faded: int = 0
    cum_path_eq_bps: float = 0.0
    open: list[OpenFade] = field(default_factory=list)
    _fp_intervals: list[tuple[int, int, int]] = field(default_factory=list)
    _trades: list[dict[str, Any]] = field(default_factory=list)

    def _tier_for(self, ev: GatedEvent) -> str:
        # Minimal online ladder proxy: |z|≥z_min → fire-tier for pause compose.
        if abs(ev.z_peak) >= float(self.z_min):
            return "size_cap"
        if abs(ev.z_peak) >= 12.0 or abs(ev.dp_pct) >= 0.25:
            return "widen"
        return "observe"

    def _in_fire_pause(self, t_ns: int, *, exclude_event_i: int | None) -> bool:
        mode = str(self.fire_pause_mode or "prior_only").lower()
        if mode in ("off", "false", "0", "none"):
            return False
        for a, b, ei in self._fp_intervals:
            if exclude_event_i is not None and ei == exclude_event_i and mode == "prior_only":
                continue
            if a <= t_ns < b:
                return True
        return False

    def on_gated_event(self, ev: GatedEvent) -> list[dict[str, Any]]:
        """Schedule fade if severity_zend gate passes. Returns loggable actions."""
        actions: list[dict[str, Any]] = []
        tier = self._tier_for(ev)
        if tier in FIRE_TIERS and self.fire_pause_s > 0:
            hold = int(float(self.fire_pause_s) * NS)
            self._fp_intervals.append((ev.ts_end, ev.ts_end + hold, ev.event_i))
            # prune old
            cut = ev.ts_end - hold
            self._fp_intervals = [(a, b, ei) for a, b, ei in self._fp_intervals if b > cut]

        actions.append(
            {
                "kind": "detect",
                "event_i": ev.event_i,
                "ts_start": ev.ts_start,
                "ts_end": ev.ts_end,
                "direction": ev.direction,
                "dp_pct": ev.dp_pct,
                "i_c": ev.i_c,
                "z_peak": ev.z_peak,
                "tier": tier,
            }
        )

        zz = abs(float(ev.z_peak))
        entry_t = int(ev.ts_end + self.confirm_s * NS)
        exit_t = int(ev.ts_end + self.exit_s * NS)
        enter = zz >= float(self.z_min)
        skip: str | None = None
        if not enter:
            skip = f"severity_z_below_{self.z_min:g}"
            self.n_severity_skip += 1
        elif self._in_fire_pause(entry_t, exclude_event_i=ev.event_i):
            enter = False
            skip = "fire_pause_5m"
            self.n_fire_skip += 1
        elif sum(1 for o in self.open if o.entry_px is not None and o.exit_px is None) >= int(
            self.max_concurrent
        ):
            enter = False
            skip = "max_concurrent"

        self.n_candidates += 1
        actions.append(
            {
                "kind": "confirm",
                "event_i": ev.event_i,
                "entry_mode": "severity_zend",
                "z_peak": ev.z_peak,
                "enter": enter,
                "skip_reason": skip,
                "entry_t": entry_t,
                "exit_t": exit_t,
            }
        )
        if not enter:
            return actions

        self.open.append(
            OpenFade(
                event_i=ev.event_i,
                direction=int(ev.direction),
                z_peak=float(ev.z_peak),
                ts_end=int(ev.ts_end),
                entry_t=entry_t,
                exit_t=exit_t,
                tier=tier,
            )
        )
        return actions

    def on_print(self, ts_ns: int, px: float) -> list[dict[str, Any]]:
        """Advance open fades against this print; emit FILL dicts when closed."""
        if not (px > 0):
            return []
        fills: list[dict[str, Any]] = []
        still: list[OpenFade] = []
        for o in self.open:
            if o.entry_px is None and ts_ns >= o.entry_t:
                o.entry_px = float(px)
                o.entry_fill_ts = int(ts_ns)
            if o.entry_px is not None and o.exit_px is None:
                # adverse (usually off)
                side_dir = int(o.direction)
                mtm = float(side_dir) * (px / o.entry_px - 1.0) * 1e4
                if mtm >= float(self.adverse_stop_bps):
                    o.exit_px = float(px)
                    o.exit_fill_ts = int(ts_ns)
                    o.exit_reason = "adverse_stop"
                elif ts_ns >= o.exit_t:
                    o.exit_px = float(px)
                    o.exit_fill_ts = int(ts_ns)
                    o.exit_reason = "time_stop"

            if o.entry_px is not None and o.exit_px is not None:
                side = -int(o.direction)
                path_gross = side * (o.exit_px / o.entry_px - 1.0) * 1e4
                path_net = path_gross - float(self.rt_friction_bps)
                self.n_faded += 1
                self.cum_path_eq_bps += path_net
                row = {
                    "kind": "fill",
                    "entry_mode": "severity_zend",
                    "live_orders": False,
                    "event_i": o.event_i,
                    "direction": o.direction,
                    "side": side,
                    "z_peak": o.z_peak,
                    "tier": o.tier,
                    "ts_end": o.ts_end,
                    "entry_t": o.entry_t,
                    "exit_t": o.exit_t,
                    "entry_ts": o.entry_fill_ts,
                    "exit_ts": o.exit_fill_ts,
                    "entry_px": o.entry_px,
                    "exit_px": o.exit_px,
                    "exit_reason": o.exit_reason,
                    "path_pnl_gross_bps": path_gross,
                    "path_pnl_net_bps": path_net,
                    "cum_path_eq_bps": self.cum_path_eq_bps,
                    "rt_friction_bps": self.rt_friction_bps,
                }
                fills.append(row)
                self._trades.append(row)
                self._append_trade_jsonl(row)
            else:
                still.append(o)
        self.open = still
        return fills

    def _append_trade_jsonl(self, row: dict[str, Any]) -> None:
        if self.trades_path is None:
            return
        self.trades_path.parent.mkdir(parents=True, exist_ok=True)
        with self.trades_path.open("a") as f:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
