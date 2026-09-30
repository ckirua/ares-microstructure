"""Main tick_shadow loop: WS prints → incremental SSM → severity_zend shadow."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from .hl_trades_ws import HlTradesFeed
from .incremental_ssm import IncrementalKalmanSSM
from .sleeve import SeverityZendSleeve

LOG = logging.getLogger("tick_shadow")


def _vf(cfg: dict[str, Any]) -> dict[str, Any]:
    return dict(cfg.get("v_fade") or {})


def build_from_config(cfg: dict[str, Any], *, root: Path) -> tuple[HlTradesFeed, IncrementalKalmanSSM, SeverityZendSleeve]:
    coin = str(cfg.get("coin") or cfg.get("symbol") or "ETH").upper()
    gate = dict(cfg.get("gate") or {})
    vf = _vf(cfg)
    out_dir = root / str(cfg.get("out_dir") or "out")
    feed = HlTradesFeed(
        coin=coin,
        reconnect_s=float(cfg.get("ws_reconnect_s", 2.0)),
        rest_fallback_poll_s=float(cfg.get("rest_fallback_poll_s", 1.0)),
    )
    ssm = IncrementalKalmanSSM(
        z_star=float(cfg.get("z_star", 6.0)),
        sigma_m_frac=float(cfg.get("sigma_m_frac", 1.0)),
        noise_floor_log=float(cfg.get("noise_floor_log", 1e-4)),
        process_rate=float(cfg.get("process_rate", 1e-8)),
        min_dp_pct=float(gate.get("min_dp_pct", 0.10)),
        min_i_c=int(gate.get("min_i_c", 5)),
    )
    sfp = vf.get("suppress_fire_pause", "prior_only")
    if isinstance(sfp, bool):
        fp_mode = "prior_only" if sfp else "off"
    else:
        fp_mode = str(sfp).strip().lower() or "prior_only"
    sleeve = SeverityZendSleeve(
        z_min=float(vf.get("z_min", 20.0)),
        confirm_s=float(vf.get("confirm_s", 0.5)),
        exit_s=float(vf.get("exit_s", 3.0)),
        rt_friction_bps=float(vf.get("rt_friction_bps", 4.0)),
        adverse_stop_bps=float(vf.get("adverse_stop_bps", 1e9)),
        max_concurrent=int(vf.get("max_concurrent", 1)),
        fire_pause_s=float(vf.get("fire_pause_5m_s", cfg.get("fire_pause_5m_s", 300.0))),
        fire_pause_mode=fp_mode,
        trades_path=out_dir / "trades_severity_zend.jsonl",
    )
    return feed, ssm, sleeve


def run_loop(
    cfg: dict[str, Any],
    *,
    root: Path,
    max_seconds: float | None = None,
) -> dict[str, Any]:
    if bool(cfg.get("live_orders")):
        raise SystemExit("REFUSE: live_orders=true — tick_shadow is shadow-only")

    feed, ssm, sleeve = build_from_config(cfg, root=root)
    coin = feed.coin
    hb_s = float(cfg.get("heartbeat_s", 10.0))
    vf = _vf(cfg)

    LOG.info(
        "START tick_shadow coin=%s feed=HL_WS_trades live_orders=false "
        "severity_zend |z|≥%g @%gs→%gs prior_only process_rate=%g",
        coin,
        float(vf.get("z_min", 20.0)),
        float(vf.get("confirm_s", 0.5)),
        float(vf.get("exit_s", 3.0)),
        float(cfg.get("process_rate", 1e-8)),
    )
    LOG.info(
        "NOTE warehouse poll peers (paper_live / v_fade_paper) remain audit — not deleted"
    )

    n_warm = feed.warm_rest()
    LOG.info("REST warm recentTrades n=%d", n_warm)
    # seed KF from warm prints (already deduped into queue — drain without sleeve fills)
    warm_prints = 0
    while True:
        batch = list(feed.iter_timeout(0.01))
        if not batch:
            break
        for p in batch:
            ssm.update(p.ts_ns, p.px)
            warm_prints += 1
    LOG.info("KF warm-started from %d REST prints n_prints=%d", warm_prints, ssm.n_prints)

    feed.start()
    t0 = time.monotonic()
    last_hb = t0
    n_ws_since_hb = 0
    last_z = float("nan")

    try:
        while True:
            if max_seconds is not None and (time.monotonic() - t0) >= float(max_seconds):
                LOG.info("STOP max_seconds=%.1f", float(max_seconds))
                break

            got = False
            for p in feed.iter_timeout(0.5):
                got = True
                if p.source.startswith("ws"):
                    n_ws_since_hb += 1
                diag = ssm.update(p.ts_ns, p.px)
                last_z = float(diag.get("z") or float("nan"))
                ev = diag.get("gated_event")
                if ev is not None:
                    LOG.info(
                        "FIRE gated event_i=%d |z_peak|=%.2f dp=%.3f%% i_c=%d "
                        "dir=%+d dt=%.3fs",
                        ev.event_i,
                        abs(ev.z_peak),
                        ev.dp_pct,
                        ev.i_c,
                        ev.direction,
                        ev.dt_s,
                    )
                    for act in sleeve.on_gated_event(ev):
                        if act.get("kind") == "confirm" and act.get("enter"):
                            LOG.info(
                                "SCHEDULE fade event_i=%d entry_t_ns=%d exit_t_ns=%d z=%.2f",
                                act["event_i"],
                                act["entry_t"],
                                act["exit_t"],
                                abs(float(act.get("z_peak") or 0.0)),
                            )
                        elif act.get("kind") == "confirm" and not act.get("enter"):
                            LOG.info(
                                "SKIP fade event_i=%d reason=%s z=%.2f",
                                act["event_i"],
                                act.get("skip_reason"),
                                abs(float(act.get("z_peak") or 0.0)),
                            )
                for fill in sleeve.on_print(p.ts_ns, p.px):
                    LOG.info(
                        "FILL shadow event_i=%d side=%+d entry=%.2f exit=%.2f "
                        "path_net=%+.2f bps cum=%+.2f bps reason=%s live_orders=false",
                        fill["event_i"],
                        fill["side"],
                        fill["entry_px"],
                        fill["exit_px"],
                        fill["path_pnl_net_bps"],
                        fill["cum_path_eq_bps"],
                        fill["exit_reason"],
                    )

            now = time.monotonic()
            if now - last_hb >= hb_s:
                age = (
                    (time.time_ns() - feed.last_print_ts_ns) / 1e9
                    if feed.last_print_ts_ns
                    else float("nan")
                )
                LOG.info(
                    "HEARTBEAT coin=%s connected=%s n_prints=%d n_ws=%d n_rest=%d "
                    "n_dup=%d last_age_s=%.2f last_z=%s gated=%d faded=%d "
                    "cum_eq_bps=%+.2f open=%d live_orders=false",
                    coin,
                    feed.connected,
                    ssm.n_prints,
                    feed.n_ws,
                    feed.n_rest,
                    feed.n_dup,
                    age,
                    f"{last_z:.2f}" if last_z == last_z else "nan",
                    ssm.n_events_gated,
                    sleeve.n_faded,
                    sleeve.cum_path_eq_bps,
                    len(sleeve.open),
                )
                if feed.last_error:
                    LOG.info("HEARTBEAT last_ws_error=%s", feed.last_error)
                last_hb = now
                n_ws_since_hb = 0
            elif not got:
                continue
    finally:
        feed.stop()
        LOG.info(
            "END n_prints=%d gated=%d faded=%d cum_eq_bps=%+.2f",
            ssm.n_prints,
            ssm.n_events_gated,
            sleeve.n_faded,
            sleeve.cum_path_eq_bps,
        )

    return {
        "n_prints": ssm.n_prints,
        "n_gated": ssm.n_events_gated,
        "n_faded": sleeve.n_faded,
        "cum_path_eq_bps": sleeve.cum_path_eq_bps,
        "n_ws": feed.n_ws,
        "n_rest": feed.n_rest,
    }
