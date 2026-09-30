"""Long-running paper-live loop (poll interval configurable)."""

from __future__ import annotations

import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .logging_setup import LOG
from .poll import poll_once, utc_day


class _StopFlag:
    def __init__(self) -> None:
        self.stop = False

    def request(self, *_args: Any) -> None:
        self.stop = True
        LOG.info("stop requested (SIGINT/SIGTERM) — finishing current poll…")


def run_loop(
    *,
    cfg: dict[str, Any],
    out_root: Path,
    interval_s: float | None = None,
    iterations: int = 0,
    day: str | None = None,
    write_figs: bool = False,
) -> dict[str, Any]:
    """Poll forever (iterations≤0) or for N polls. Shadow only.

    Day rolls over automatically at UTC midnight when ``day`` is None.
    """
    if bool(cfg.get("live_orders")):
        raise RuntimeError("paper_live refuses live_orders=true")

    interval = float(
        interval_s if interval_s is not None else cfg.get("poll_interval_s") or 10.0
    )
    venue = cfg.get("venue")
    symbol = cfg.get("symbol")
    flag = _StopFlag()
    prev_int = signal.signal(signal.SIGINT, flag.request)
    prev_term = signal.signal(signal.SIGTERM, flag.request)

    LOG.info(
        "paper_live START venue=%s symbol=%s interval=%.1fs iterations=%s "
        "live_orders=False out=%s",
        venue,
        symbol,
        interval,
        "∞" if iterations <= 0 else iterations,
        out_root,
    )
    LOG.info(
        "data: warehouse trade tape (S3→cache, lag typical) + collector TOB if present; "
        "never mercat/gateway orders"
    )

    last: dict[str, Any] = {}
    n = 0
    try:
        while not flag.stop:
            if iterations > 0 and n >= iterations:
                break
            run_day = day or utc_day()
            # UTC day rollover notice
            if last.get("day") and last["day"] != run_day and day is None:
                LOG.info("UTC day rollover %s → %s", last["day"], run_day)

            try:
                last = poll_once(
                    cfg=cfg,
                    out_root=out_root,
                    day=run_day,
                    poll_i=n,
                    write_figs_on_report=write_figs,
                )
            except Exception as exc:  # noqa: BLE001
                LOG.error("poll=%s unhandled: %s", n, exc)
                last = {"ok": False, "error": str(exc), "day": run_day}

            n += 1
            if flag.stop:
                break
            if iterations > 0 and n >= iterations:
                break
            if interval > 0:
                LOG.info("sleep %.1fs until next poll", interval)
                # Sleep in small chunks so SIGINT is responsive
                end = time.monotonic() + interval
                while time.monotonic() < end and not flag.stop:
                    time.sleep(min(0.5, end - time.monotonic()))
    finally:
        signal.signal(signal.SIGINT, prev_int)
        signal.signal(signal.SIGTERM, prev_term)

    LOG.info(
        "paper_live STOP after %s poll(s) last_day=%s ts=%s",
        n,
        last.get("day"),
        datetime.now(timezone.utc).isoformat(),
    )
    return {"n_polls": n, "last": last}
