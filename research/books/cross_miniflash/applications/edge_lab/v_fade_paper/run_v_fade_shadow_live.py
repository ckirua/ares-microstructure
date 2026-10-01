from __future__ import annotations
#!/usr/bin/env python3
"""V-fade living SHADOW poller — severity_zend Promote_shadow (no exchange orders).

DISTINCT from ``applications/paper_live`` (kill-ladder crash-risk overlay).
This loop re-runs the causal V-fade taker on the latest complete warehouse day.

Defaults (Promote_shadow lock):
  entry_mode=severity_zend · |z|≥20 · enter +0.5s · exit 3s · fire_pause=prior_only
  live_orders=false  (hard refuse)

Examples:
  python3 run_v_fade_shadow_live.py --poll
  python3 run_v_fade_shadow_live.py --poll --interval 120 --quiet
  python3 run_v_fade_shadow_live.py --iterations 1

Log: logs/v_fade_shadow.log  (heartbeats + cum path equity when trades fire)
Never mercat/gateway OE. ClickHouse MCP banned.
"""


import argparse
import json
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

PKG = Path(__file__).resolve().parent
sys.path.insert(0, str(PKG))

from harness.causal import jsonable  # noqa: E402
from harness.config import load_config  # noqa: E402
from harness.shadow import apply_vf_overrides  # noqa: E402
from run_v_fade_paper import DEFAULT_PANEL_DAYS, run_shadow  # noqa: E402

LOG = logging.getLogger("v_fade_shadow")

# Promote_shadow lock — CLI may tighten but may not enable live orders.
PROMOTE_DEFAULTS = {
    "entry_mode": "severity_zend",
    "confirm_s": 0.5,
    "exit_s": 3.0,
    "z_min": 20.0,
    "adverse_stop_bps": 1e9,
    "suppress_fire_pause": "prior_only",
    "always_fade": False,
}


class FlushTimedRotatingFileHandler(TimedRotatingFileHandler):
    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


class _StopFlag:
    def __init__(self) -> None:
        self.stop = False

    def request(self, *_args: Any) -> None:
        self.stop = True
        LOG.info("stop requested (SIGINT/SIGTERM) — finishing current poll…")


def setup_logging(log_path: Path, *, quiet: bool = False) -> logging.Logger:
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
        except Exception:
            pass

    root = logging.getLogger("v_fade_shadow")
    for h in list(root.handlers):
        root.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass
    root.setLevel(logging.INFO)
    root.propagate = False
    fmt = logging.Formatter(
        fmt="%(asctime)sZ %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    fmt.converter = time.gmtime  # type: ignore[attr-defined]
    fh = FlushTimedRotatingFileHandler(
        log_path,
        when="midnight",
        interval=1,
        backupCount=14,
        encoding="utf-8",
        utc=True,
    )
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if not quiet:
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(logging.INFO)
        sh.setFormatter(fmt)
        root.addHandler(sh)
    root.info("logging → %s live_orders=False", log_path)
    return root


def _pin_promote(cfg: dict[str, Any], cli_ov: dict[str, Any] | None = None) -> dict[str, Any]:
    """Force severity_zend Promote defaults; refuse live_orders."""
    if bool(cfg.get("live_orders")):
        raise RuntimeError("K8 hard refuse: live_orders=True is not allowed in v_fade shadow")
    ov = dict(PROMOTE_DEFAULTS)
    if cli_ov:
        for k, v in cli_ov.items():
            if v is not None and k != "entry_mode":
                ov[k] = v
    ov["entry_mode"] = "severity_zend"
    ov["always_fade"] = False
    ov.setdefault("suppress_fire_pause", "prior_only")
    out = apply_vf_overrides(cfg, ov)
    out["live_orders"] = False
    out["v_fade"]["entry_mode"] = "severity_zend"
    out["v_fade"]["suppress_fire_pause"] = str(
        out["v_fade"].get("suppress_fire_pause") or "prior_only"
    )
    return out


def _cum_path_from_trades_jsonl(path: Path) -> tuple[int, float, list[dict[str, Any]]]:
    trades: list[dict[str, Any]] = []
    if not path.is_file():
        return 0, 0.0, trades
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                trades.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    ordered = sorted(
        trades,
        key=lambda t: (str(t.get("day") or ""), int(t.get("entry_ts") or 0)),
    )
    cum = 0.0
    n = 0
    for t in ordered:
        v = t.get("path_pnl_net_bps")
        if v is None:
            continue
        try:
            cum += float(v)
            n += 1
        except (TypeError, ValueError):
            continue
    return n, cum, ordered


def _log_trades(
    *,
    poll_i: int,
    day: str,
    trades: list[dict[str, Any]],
    prev_n: int,
) -> float:
    cum = 0.0
    for i, t in enumerate(trades):
        pnl = t.get("path_pnl_net_bps")
        try:
            p = float(pnl) if pnl is not None else None
        except (TypeError, ValueError):
            p = None
        if p is not None:
            cum += p
        if i < prev_n:
            continue
        # New / re-fired trade relative to prior poll fingerprint count
        LOG.info(
            "TRADE fire poll=%s day=%s event_i=%s side=%s z_peak=%s "
            "path_net=%s cum_path_eq_bps=%.2f exit=%s live_orders=false",
            poll_i,
            day,
            t.get("event_i"),
            t.get("side_name") or t.get("side"),
            t.get("z_peak"),
            f"{p:.2f}" if p is not None else "—",
            cum,
            t.get("exit_reason"),
        )
    return cum


def poll_once(
    *,
    cfg: dict[str, Any],
    out_root: Path,
    poll_i: int,
    prev_day: str | None,
    prev_n_faded: int,
    gap_path: Path | None = None,
) -> dict[str, Any]:
    if bool(cfg.get("live_orders")):
        raise RuntimeError("K8 hard refuse: live_orders=True")

    t0 = time.monotonic()
    vf = cfg.get("v_fade") or {}
    brief = run_shadow(
        cfg=cfg,
        out_root=out_root,
        quiet=True,
        gap_path=gap_path,
        cli_overrides=None,
        panel_days=DEFAULT_PANEL_DAYS,
    )
    day = str(brief.get("day") or "")
    living = brief.get("living_day_severity_zend") or {}
    n_faded = int(living.get("n_faded") or 0)
    path_block = living.get("path_pnl_net_bps") or {}
    # Prefer severity sleeve jsonl (not confirm_r2 fallback in trades.jsonl)
    sev_trades_path = out_root / "trades_severity_zend.jsonl"
    trades_path = sev_trades_path if sev_trades_path.is_file() else out_root / "trades.jsonl"
    n_tr, cum_eq, trades = _cum_path_from_trades_jsonl(trades_path)
    if n_tr == 0:
        cum_eq = 0.0
        trades = []
    if n_tr == 0 and isinstance(path_block, dict) and path_block.get("mean") is not None and n_faded:
        try:
            cum_eq = float(path_block["mean"]) * n_faded
        except (TypeError, ValueError):
            pass

    if prev_day and day and prev_day != day:
        LOG.info("warehouse day rollover %s → %s", prev_day, day)

    if n_faded > prev_n_faded or (day != prev_day and n_faded > 0):
        _log_trades(
            poll_i=poll_i,
            day=day,
            trades=trades,
            prev_n=prev_n_faded if day == prev_day else 0,
        )

    elapsed = time.monotonic() - t0
    path_mean = None
    if isinstance(path_block, dict):
        path_mean = path_block.get("mean")
    elif living.get("path_pnl_net_bps") is not None:
        # run_shadow brief nests path under living_day as scalar summary fields
        pass
    # brief living_day uses top-level path_pnl_net_bps from summary — may be dict
    s_path = living.get("path_pnl_net_bps")
    if isinstance(s_path, (int, float)):
        path_mean = float(s_path)
    elif isinstance(s_path, dict):
        path_mean = s_path.get("mean")

    LOG.info(
        "HEARTBEAT poll=%s day=%s venue=%s symbol=%s entry_mode=%s z_min=%s "
        "confirm_s=%s exit_s=%s fire_pause=%s n_faded=%s cum_path_eq_bps=%.2f "
        "path_mean=%s elapsed=%.1fs live_orders=false board=%s",
        poll_i,
        day,
        brief.get("venue"),
        brief.get("symbol"),
        vf.get("entry_mode", "severity_zend"),
        vf.get("z_min", 20.0),
        vf.get("confirm_s", 0.5),
        vf.get("exit_s", 3.0),
        vf.get("suppress_fire_pause", "prior_only"),
        n_faded,
        cum_eq,
        f"{float(path_mean):.2f}" if path_mean is not None else "—",
        elapsed,
        brief.get("shadow_board"),
    )
    return {
        "ok": True,
        "day": day,
        "n_faded": n_faded,
        "cum_path_eq_bps": cum_eq,
        "path_mean": path_mean,
        "elapsed_s": elapsed,
        "shadow_board": brief.get("shadow_board"),
        "live_orders": False,
        "brief": brief,
    }


def run_loop(
    *,
    cfg: dict[str, Any],
    out_root: Path,
    interval_s: float,
    iterations: int,
    gap_path: Path | None = None,
) -> dict[str, Any]:
    if bool(cfg.get("live_orders")):
        raise RuntimeError("K8 hard refuse: live_orders=True")

    vf = cfg.get("v_fade") or {}
    flag = _StopFlag()
    prev_int = signal.signal(signal.SIGINT, flag.request)
    prev_term = signal.signal(signal.SIGTERM, flag.request)

    LOG.info(
        "v_fade_shadow START venue=%s symbol=%s interval=%.1fs iterations=%s "
        "entry_mode=%s z_min=%s confirm_s=%s exit_s=%s fire_pause=%s "
        "live_orders=False out=%s",
        cfg.get("venue"),
        cfg.get("symbol"),
        interval_s,
        "∞" if iterations <= 0 else iterations,
        vf.get("entry_mode"),
        vf.get("z_min"),
        vf.get("confirm_s"),
        vf.get("exit_s"),
        vf.get("suppress_fire_pause"),
        out_root,
    )
    LOG.info(
        "class=directional_v_fade_taker ≠ paper_live kill-ladder; "
        "warehouse tape only; never mercat/gateway OE"
    )

    last: dict[str, Any] = {}
    prev_day: str | None = None
    prev_n = 0
    n = 0
    try:
        while not flag.stop:
            if iterations > 0 and n >= iterations:
                break
            try:
                last = poll_once(
                    cfg=cfg,
                    out_root=out_root,
                    poll_i=n,
                    prev_day=prev_day,
                    prev_n_faded=prev_n,
                    gap_path=gap_path,
                )
                prev_day = str(last.get("day") or prev_day or "")
                prev_n = int(last.get("n_faded") or 0)
            except Exception as exc:  # noqa: BLE001
                LOG.error("poll=%s unhandled: %s", n, exc)
                last = {"ok": False, "error": str(exc), "live_orders": False}
            n += 1
            if flag.stop:
                break
            if iterations > 0 and n >= iterations:
                break
            if interval_s > 0:
                LOG.info("sleep %.1fs until next poll", interval_s)
                end = time.monotonic() + interval_s
                while time.monotonic() < end and not flag.stop:
                    time.sleep(min(0.5, end - time.monotonic()))
    finally:
        signal.signal(signal.SIGINT, prev_int)
        signal.signal(signal.SIGTERM, prev_term)

    LOG.info(
        "v_fade_shadow STOP after %s poll(s) last_day=%s ts=%s live_orders=false",
        n,
        last.get("day"),
        datetime.now(timezone.utc).isoformat(),
    )
    return {"n_polls": n, "last": last}


def main() -> None:
    ap = argparse.ArgumentParser(
        description="V-fade living SHADOW poller (severity_zend; no exchange orders)"
    )
    ap.add_argument("--config", default=str(PKG / "config.yaml"))
    ap.add_argument("--venue", default="", help="Override venue (default hyperliquid)")
    ap.add_argument("--symbol", default="", help="Override symbol (default ETH)")
    ap.add_argument(
        "--interval",
        type=float,
        default=None,
        help="Poll interval seconds (default: config poll_interval_s ≈ 120)",
    )
    ap.add_argument(
        "--iterations",
        type=int,
        default=1,
        help="Number of polls (0 = forever). Default 1 for safe smoke.",
    )
    ap.add_argument(
        "--poll",
        action="store_true",
        help="Run forever (iterations=0)",
    )
    ap.add_argument("--out-dir", default="", help="Override output root")
    ap.add_argument(
        "--log-file",
        default="",
        help="Override log path (default logs/v_fade_shadow.log)",
    )
    ap.add_argument("--gap-summary", default="", help="Path to gap_summary.json")
    ap.add_argument("--confirm-s", type=float, default=None)
    ap.add_argument("--exit-s", type=float, default=None)
    ap.add_argument("--z-min", type=float, default=None)
    ap.add_argument(
        "--allow-fire-pause",
        action="store_true",
        help="Diagnostic: do NOT suppress follow-on fire_pause (not Promote default)",
    )
    ap.add_argument("--quiet", action="store_true", help="Log file only (no stdout)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.venue:
        cfg["venue"] = args.venue.lower()
    if args.symbol:
        cfg["symbol"] = args.symbol.upper()

    cli_ov: dict[str, Any] = {}
    if args.confirm_s is not None:
        cli_ov["confirm_s"] = args.confirm_s
    if args.exit_s is not None:
        cli_ov["exit_s"] = args.exit_s
    if args.z_min is not None:
        cli_ov["z_min"] = args.z_min
    if args.allow_fire_pause:
        cli_ov["suppress_fire_pause"] = "off"

    try:
        cfg = _pin_promote(cfg, cli_ov)
    except RuntimeError as exc:
        print(f"[v_fade_shadow] REFUSE: {exc}", file=sys.stderr)
        sys.exit(2)

    out_root = Path(args.out_dir) if args.out_dir else PKG / str(cfg.get("out_dir") or "out")
    out_root.mkdir(parents=True, exist_ok=True)

    log_path = (
        Path(args.log_file)
        if args.log_file
        else PKG / "logs" / "v_fade_shadow.log"
    )
    setup_logging(log_path, quiet=args.quiet)

    interval = float(
        args.interval
        if args.interval is not None
        else cfg.get("poll_interval_s") or 120.0
    )
    iterations = 0 if args.poll else int(args.iterations)
    gap_path = Path(args.gap_summary) if args.gap_summary else None

    result = run_loop(
        cfg=cfg,
        out_root=out_root,
        interval_s=interval,
        iterations=iterations,
        gap_path=gap_path,
    )
    brief = {
        "n_polls": result.get("n_polls"),
        "last_ok": (result.get("last") or {}).get("ok"),
        "last_day": (result.get("last") or {}).get("day"),
        "cum_path_eq_bps": (result.get("last") or {}).get("cum_path_eq_bps"),
        "n_faded": (result.get("last") or {}).get("n_faded"),
        "shadow_board": (result.get("last") or {}).get("shadow_board"),
        "log_file": str(log_path),
        "live_orders": False,
        "entry_mode": (cfg.get("v_fade") or {}).get("entry_mode"),
        "z_min": (cfg.get("v_fade") or {}).get("z_min"),
        "confirm_s": (cfg.get("v_fade") or {}).get("confirm_s"),
        "exit_s": (cfg.get("v_fade") or {}).get("exit_s"),
        "suppress_fire_pause": (cfg.get("v_fade") or {}).get("suppress_fire_pause"),
    }
    print(json.dumps(jsonable(brief), indent=2))


if __name__ == "__main__":
    main()
