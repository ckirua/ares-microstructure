"""Incremental scalar Kalman SSM + online crash-run detector.

Mirrors ``ares_micro.vol.crash.kalman_ssm_filter`` recursion one print at a time.
Noise is a documented online Δ vs offline MC-GARCH day harness (see ARCHITECTURE).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

NS = 1_000_000_000


@dataclass
class GatedEvent:
    ts_start: int
    ts_end: int
    px_start: float
    px_end: float
    direction: int
    dp_pct: float
    i_c: int
    dt_s: float
    z_peak: float
    event_i: int


@dataclass
class IncrementalKalmanSSM:
    z_star: float = 6.0
    sigma_m_frac: float = 1.0
    noise_floor_log: float = 1e-4
    process_rate: float = 1e-8
    min_dp_pct: float = 0.10
    min_i_c: int = 5
    dlog_maxlen: int = 2048

    x: float | None = None
    P: float | None = None
    last_ts_ns: int | None = None
    n_prints: int = 0
    n_events_raw: int = 0
    n_events_gated: int = 0
    last_z: float = float("nan")
    last_px: float = float("nan")
    last_innov: float = float("nan")

    _dlog: deque[float] = field(default_factory=deque, repr=False)
    _in_event: bool = False
    _ev_start_ts: int = 0
    _ev_start_px: float = 0.0
    _ev_z_peak: float = 0.0
    _ev_px_min: float = 0.0
    _ev_px_max: float = 0.0
    _ev_n: int = 0
    _ev_end_ts: int = 0
    _ev_end_px: float = 0.0
    _event_i: int = 0

    def __post_init__(self) -> None:
        self._dlog = deque(maxlen=int(self.dlog_maxlen))

    def _noise_ref(self) -> float:
        floor = float(self.noise_floor_log)
        if len(self._dlog) < 10:
            return floor
        arr = np.asarray(self._dlog, dtype=np.float64)
        mad = float(np.median(np.abs(arr - np.median(arr)))) / 0.6745
        return max(mad, floor, 1e-12)

    def update(self, ts_ns: int, px: float) -> dict[str, Any]:
        """One KF step. Returns diagnostics; may include ``gated_event`` when a run ends."""
        out: dict[str, Any] = {
            "z": float("nan"),
            "innov": float("nan"),
            "kappa": float("nan"),
            "flag": False,
            "gated_event": None,
            "warm": False,
        }
        if not (px > 0 and np.isfinite(px)):
            return out
        log_z = float(np.log(px))
        ts_ns = int(ts_ns)

        if self.x is None or self.P is None or self.last_ts_ns is None:
            sm = max((self.sigma_m_frac * self._noise_ref()) ** 2, 1e-18)
            self.x = log_z
            self.P = sm
            self.last_ts_ns = ts_ns
            self.last_px = px
            self.last_z = 0.0
            self.n_prints = 1
            out.update(z=0.0, innov=0.0, kappa=0.0, warm=True)
            return out

        dt = max((ts_ns - self.last_ts_ns) / NS, 1e-9)
        dlog = log_z - float(np.log(self.last_px)) if self.last_px > 0 else 0.0
        if np.isfinite(dlog):
            self._dlog.append(float(dlog))

        noise_ref = self._noise_ref()
        R = max((float(self.sigma_m_frac) * noise_ref) ** 2, 1e-18)
        sp_dt = max(float(self.process_rate), 1e-18) * dt

        P_prior = float(self.P) + sp_dt
        S = P_prior + R
        K = P_prior / S
        inn = log_z - float(self.x)
        self.x = float(self.x) + K * inn
        self.P = (1.0 - K) * P_prior
        z = inn / np.sqrt(S) if S > 0 else float("nan")

        self.last_ts_ns = ts_ns
        self.last_px = px
        self.last_z = float(z) if np.isfinite(z) else float("nan")
        self.last_innov = float(inn)
        self.n_prints += 1

        flag = bool(np.isfinite(z) and abs(z) >= float(self.z_star))
        gated = self._step_event(ts_ns, px, float(z) if np.isfinite(z) else 0.0, flag)

        out.update(
            z=float(z) if np.isfinite(z) else float("nan"),
            innov=float(inn),
            kappa=float(K),
            flag=flag,
            gated_event=gated,
            warm=False,
            noise_ref=noise_ref,
            R=R,
            P=float(self.P),
        )
        return out

    def _step_event(
        self, ts_ns: int, px: float, z: float, flag: bool
    ) -> GatedEvent | None:
        if flag:
            if not self._in_event:
                self._in_event = True
                self._ev_start_ts = ts_ns
                self._ev_start_px = px
                self._ev_z_peak = z
                self._ev_px_min = px
                self._ev_px_max = px
                self._ev_n = 1
            else:
                self._ev_n += 1
                if abs(z) > abs(self._ev_z_peak):
                    self._ev_z_peak = z
                if px < self._ev_px_min:
                    self._ev_px_min = px
                if px > self._ev_px_max:
                    self._ev_px_max = px
            self._ev_end_ts = ts_ns
            self._ev_end_px = px
            return None

        if not self._in_event:
            return None

        # close run
        self._in_event = False
        self.n_events_raw += 1
        a_px = self._ev_start_px
        if not (a_px > 0):
            return None
        down = (a_px - self._ev_px_min) / a_px
        up = (self._ev_px_max - a_px) / a_px
        if down >= up:
            direction = -1
            dp = down * 100.0
        else:
            direction = 1
            dp = up * 100.0
        ic = int(self._ev_n)
        dt_s = (self._ev_end_ts - self._ev_start_ts) / NS
        if abs(dp) < float(self.min_dp_pct) or ic < int(self.min_i_c):
            return None

        self.n_events_gated += 1
        self._event_i += 1
        return GatedEvent(
            ts_start=int(self._ev_start_ts),
            ts_end=int(self._ev_end_ts),
            px_start=float(a_px),
            px_end=float(self._ev_end_px),
            direction=int(direction),
            dp_pct=float(dp),
            i_c=ic,
            dt_s=float(dt_s),
            z_peak=float(self._ev_z_peak),
            event_i=int(self._event_i),
        )
