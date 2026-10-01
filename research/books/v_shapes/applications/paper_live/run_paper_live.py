from __future__ import annotations
#!/usr/bin/env python3
"""V-shapes paper_live SHADOW poller — MinV/EGARCH monitors (no exchange orders).

Living warehouse-day shadow, mirroring ``cross_miniflash/.../v_fade_paper``
``run_v_fade_shadow_live.py`` cadence:

  latest complete warehouse day → MinV / EGARCH sig_5 (Promote Monitor)
  → optional calendar Ridge score (Promote Monitor only)
  → paper Kill throttle state (hypothetical / do-not-size)
  → append logs/shadow.log + out/events.jsonl

Desk honesty:
  exec.minv_breach_throttle stays **Kill** — shadow is telemetry + paper
  accounting, NOT production quoting. Never soft-Promote. live_orders=False.

Examples:
  python3 run_paper_live.py --poll
  python3 run_paper_live.py --poll --interval 120 --quiet
  python3 run_paper_live.py --iterations 1
  python3 run_paper_live.py --day 2026-09-30 --iterations 1

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

from harness.config import load_config  # noqa: E402
from harness.monitors import compute_day_monitors, jsonable  # noqa: E402

LOG = logging.getLogger("vshapes_shadow")


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

    root = logging.getLogger("vshapes_shadow")
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
    root.info("logging → %s live_orders=False alpha_claim=False", log_path)
    return root


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(jsonable(record), separators=(",", ":")) + "\n")


def _fmt(x: Any, nd: int = 3) -> str:
    if x is None:
        return "—"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    if not (v == v):  # NaN
        return "—"
    return f"{v:.{nd}f}"


def _emit_events(
    *,
    events_path: Path,
    poll_i: int,
    brief: dict[str, Any],
    prev_fingerprint: str | None,
) -> str:
    """Append JSONL events; return fingerprint of this poll's breach state."""
    day = str(brief.get("day") or "")
    parts: list[str] = []
    for cell in brief.get("per_venue") or []:
        if not cell.get("ok"):
            continue
        venue = cell.get("venue")
        primary = cell.get("primary") or {}
        breached = bool(cell.get("breached"))
        fp_piece = f"{venue}:{int(breached)}:{_fmt(primary.get('min_v'))}:{_fmt(primary.get('tau_star_s'), 0)}"
        parts.append(fp_piece)

        # Always record a heartbeat-ish monitor snapshot for primary venue
        # Breach / score / hypothetical only when state is interesting or new
        event_base = {
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "poll": poll_i,
            "day": day,
            "venue": venue,
            "symbol": cell.get("symbol"),
            "live_orders": False,
            "alpha_claim": False,
        }

        if breached:
            append_jsonl(
                events_path,
                {
                    **event_base,
                    "event": "breach",
                    "kind": "monitor",
                    "gate": "Promote",
                    "gate_ids": ["risk.egarch_minv_bands", "risk.daily_minv_panel"],
                    "label": "Monitor",
                    "hn_min": primary.get("hn_min") or brief.get("primary", {}).get("primary_hn_min"),
                    "min_v": primary.get("min_v"),
                    "q05": primary.get("q05"),
                    "tau_star_s": primary.get("tau_star_s"),
                    "shape": primary.get("shape"),
                    "sig_5": True,
                },
            )
            LOG.info(
                "BREACH Monitor Promote day=%s venue=%s hn=%sm min_v=%s q05=%s "
                "tau_star_s=%s shape=%s gate=risk.egarch_minv_bands|daily_minv_panel "
                "live_orders=false",
                day,
                venue,
                primary.get("hn_min") or 5,
                _fmt(primary.get("min_v")),
                _fmt(primary.get("q05")),
                _fmt(primary.get("tau_star_s"), 1),
                primary.get("shape"),
            )

        cal = cell.get("cal_score")
        if cal is not None:
            append_jsonl(
                events_path,
                {
                    **event_base,
                    "event": "score",
                    "kind": "monitor",
                    "gate": "Promote",
                    "gate_id": "info.v_feature_ridge_calendar",
                    "label": "Monitor",
                    "promote_as": "Monitor",
                    "cal_score": cal,
                    "breached": breached,
                    "note": "calendar Ridge Monitor only — never sized",
                },
            )
            LOG.info(
                "SCORE Monitor Promote day=%s venue=%s cal_score=%s "
                "gate=info.v_feature_ridge_calendar (Monitor only; never sized) "
                "live_orders=false",
                day,
                venue,
                _fmt(cal, 6),
            )

        th = cell.get("throttle_paper") or {}
        hypo = th.get("hypothetical") or {}
        if breached or hypo.get("active"):
            append_jsonl(
                events_path,
                {
                    **event_base,
                    "event": "hypothetical_throttle",
                    "kind": "hypothetical",
                    "label": "Kill/do-not-size",
                    "gate": "Kill",
                    "gate_id": "exec.minv_breach_throttle",
                    "do_not_size": True,
                    "deploy": False,
                    "alpha_claim": False,
                    "cal_join_gate": "Hold",
                    "as_alpha_gate": "Hold",
                    "breached": breached,
                    "cal_score": cell.get("cal_score"),
                    "hypothetical": {
                        "widen_bps": hypo.get("widen_bps"),
                        "size_mult": hypo.get("size_mult"),
                        "pov": hypo.get("pov"),
                        "take_pause": hypo.get("take_pause"),
                        "cal_boost": hypo.get("cal_boost"),
                    },
                    "note": th.get("note"),
                },
            )
            LOG.info(
                "HYPOTHETICAL Kill/do-not-size day=%s venue=%s active=%s "
                "widen_bps=%s size_mult=%s pov=%s take_pause=%s cal_boost=%s "
                "gate=exec.minv_breach_throttle Kill — PAPER ONLY; never deploy "
                "live_orders=false",
                day,
                venue,
                hypo.get("active"),
                hypo.get("widen_bps"),
                hypo.get("size_mult"),
                hypo.get("pov"),
                hypo.get("take_pause"),
                hypo.get("cal_boost"),
            )

    fingerprint = "|".join(parts) + f"|{day}"
    if prev_fingerprint and fingerprint != prev_fingerprint:
        LOG.info("state change fingerprint %s → %s", prev_fingerprint, fingerprint)
    return fingerprint


def write_shadow_board(out_root: Path, brief: dict[str, Any]) -> Path:
    path = out_root / "SHADOW_BOARD.md"
    day = brief.get("day")
    gates = brief.get("gates") or {}
    lines = [
        "# V-shapes SHADOW BOARD",
        "",
        f"**Day:** `{day}` · **Primary:** `{brief.get('venue')}` `{brief.get('symbol')}`",
        f"**UTC:** {brief.get('ts_utc')}",
        "",
        "> SHADOW only · `live_orders=false` · `alpha_claim=false` · "
        "MinV/EGARCH = **Promote Monitor** · throttle = **Kill/do-not-size** "
        "(paper observation) · never mercat/gateway OE",
        "",
        "## Gate labels (pinned)",
        "",
        "| ID | Gate | Role in shadow |",
        "|----|------|----------------|",
        f"| `risk.egarch_minv_bands` | {gates.get('risk.egarch_minv_bands', 'Promote')} | Monitor telemetry |",
        f"| `risk.daily_minv_panel` | {gates.get('risk.daily_minv_panel', 'Promote')} | Monitor telemetry |",
        f"| `info.v_feature_ridge_calendar` | {gates.get('info.v_feature_ridge_calendar', 'Promote')} | Monitor score only |",
        f"| `exec.minv_breach_throttle` | {gates.get('exec.minv_breach_throttle', 'Kill')} | Hypothetical paper state — **do not size** |",
        f"| `exec.minv_throttle_cal_join` | {gates.get('exec.minv_throttle_cal_join', 'Hold')} | Paper secondary |",
        f"| `exec.minv_throttle_as_alpha` | {gates.get('exec.minv_throttle_as_alpha', 'Hold')} | Never sized alpha |",
        "",
        "## Per-venue",
        "",
    ]
    for cell in brief.get("per_venue") or []:
        if not cell.get("ok"):
            lines.append(
                f"- `{cell.get('venue')}`: FAIL — `{cell.get('error')}`"
            )
            continue
        p = cell.get("primary") or {}
        th = (cell.get("throttle_paper") or {}).get("hypothetical") or {}
        lines.append(
            f"- **{cell.get('venue')}** complete={cell.get('complete')} "
            f"n={cell.get('n_trades')} breached={cell.get('breached')} "
            f"min_v={_fmt(p.get('min_v'))} q05={_fmt(p.get('q05'))} "
            f"τ★={_fmt(p.get('tau_star_s'), 1)}s shape={p.get('shape')} "
            f"cal_score={_fmt(cell.get('cal_score'), 6)} "
            f"hypo_active={th.get('active')} "
            f"(Kill/do-not-size widen={th.get('widen_bps')} size={th.get('size_mult')})"
        )
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            "- `logs/shadow.log` — HEARTBEAT / BREACH / SCORE / HYPOTHETICAL",
            "- `out/events.jsonl` — breach · score · hypothetical_throttle",
            "- `out/shadow_meta.json` — last poll machine summary",
            "",
        ]
    )
    path.write_text("\n".join(lines) + "\n")
    return path


def poll_once(
    *,
    cfg: dict[str, Any],
    out_root: Path,
    events_path: Path,
    poll_i: int,
    day: str | None,
    prev_day: str | None,
    prev_fp: str | None,
) -> dict[str, Any]:
    if bool(cfg.get("live_orders")):
        raise RuntimeError("K8 hard refuse: live_orders=True")

    t0 = time.monotonic()
    brief = compute_day_monitors(cfg=cfg, day=day)
    day_s = str(brief.get("day") or "")
    if prev_day and day_s and prev_day != day_s:
        LOG.info("warehouse day rollover %s → %s", prev_day, day_s)

    fp = _emit_events(
        events_path=events_path,
        poll_i=poll_i,
        brief=brief,
        prev_fingerprint=prev_fp,
    )
    board = write_shadow_board(out_root, brief)
    meta_path = out_root / "shadow_meta.json"
    meta_path.write_text(json.dumps(jsonable(brief), indent=2) + "\n")

    # Day out dir snapshot
    venue = brief.get("venue")
    symbol = brief.get("symbol")
    day_dir = out_root / f"{day_s}_{venue}_{symbol}"
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "summary.json").write_text(
        json.dumps(jsonable(brief), indent=2) + "\n"
    )

    elapsed = time.monotonic() - t0
    primary = (brief.get("primary") or {}) if isinstance(brief.get("primary"), dict) else {}
    p = primary.get("primary") or {}
    th = (primary.get("throttle_paper") or {}).get("hypothetical") or {}

    LOG.info(
        "HEARTBEAT poll=%s day=%s venue=%s symbol=%s breached=%s "
        "min_v=%s q05=%s tau_star_s=%s shape=%s cal_score=%s "
        "hypo_active=%s hypo_widen=%s hypo_size=%s "
        "throttle_gate=Kill/do-not-size cal_coefs=%s "
        "elapsed=%.1fs live_orders=false board=%s",
        poll_i,
        day_s,
        venue,
        symbol,
        brief.get("any_breach"),
        _fmt(p.get("min_v")),
        _fmt(p.get("q05")),
        _fmt(p.get("tau_star_s"), 1),
        p.get("shape"),
        _fmt(primary.get("cal_score"), 6),
        th.get("active"),
        th.get("widen_bps"),
        th.get("size_mult"),
        brief.get("cal_coefs_loaded"),
        elapsed,
        board,
    )
    return {
        "ok": True,
        "day": day_s,
        "fingerprint": fp,
        "any_breach": brief.get("any_breach"),
        "elapsed_s": elapsed,
        "shadow_board": str(board),
        "live_orders": False,
        "brief": brief,
    }


def run_loop(
    *,
    cfg: dict[str, Any],
    out_root: Path,
    events_path: Path,
    interval_s: float,
    iterations: int,
    day: str | None = None,
) -> dict[str, Any]:
    if bool(cfg.get("live_orders")):
        raise RuntimeError("K8 hard refuse: live_orders=True")

    flag = _StopFlag()
    prev_int = signal.signal(signal.SIGINT, flag.request)
    prev_term = signal.signal(signal.SIGTERM, flag.request)

    gates = cfg.get("gates") or {}
    LOG.info(
        "vshapes_shadow START venue=%s symbol=%s extras=%s interval=%.1fs "
        "iterations=%s live_orders=False alpha_claim=False out=%s",
        cfg.get("venue"),
        cfg.get("symbol"),
        cfg.get("extra_venues"),
        interval_s,
        "∞" if iterations <= 0 else iterations,
        out_root,
    )
    LOG.info(
        "gates: egarch/minv=%s calendar=%s throttle=%s cal_join=%s as_alpha=%s "
        "— Kill throttle is paper observation ONLY; never soft-Promote",
        gates.get("risk.egarch_minv_bands", "Promote"),
        gates.get("info.v_feature_ridge_calendar", "Promote"),
        gates.get("exec.minv_breach_throttle", "Kill"),
        gates.get("exec.minv_throttle_cal_join", "Hold"),
        gates.get("exec.minv_throttle_as_alpha", "Hold"),
    )
    LOG.info(
        "class=risk_monitor_shadow ≠ sized alpha; warehouse tape; "
        "never mercat/gateway OE; ClickHouse MCP banned"
    )

    last: dict[str, Any] = {}
    prev_day: str | None = None
    prev_fp: str | None = None
    n = 0
    try:
        while not flag.stop:
            if iterations > 0 and n >= iterations:
                break
            try:
                last = poll_once(
                    cfg=cfg,
                    out_root=out_root,
                    events_path=events_path,
                    poll_i=n,
                    day=day,
                    prev_day=prev_day,
                    prev_fp=prev_fp,
                )
                prev_day = str(last.get("day") or prev_day or "")
                prev_fp = str(last.get("fingerprint") or prev_fp or "")
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
        "vshapes_shadow STOP after %s poll(s) last_day=%s ts=%s live_orders=false",
        n,
        last.get("day"),
        datetime.now(timezone.utc).isoformat(),
    )
    return {"n_polls": n, "last": last}


def main() -> None:
    ap = argparse.ArgumentParser(
        description="V-shapes MinV/EGARCH SHADOW poller (no exchange orders)"
    )
    ap.add_argument("--config", default=str(PKG / "config.yaml"))
    ap.add_argument("--venue", default="", help="Override venue (default hyperliquid)")
    ap.add_argument("--symbol", default="", help="Override symbol (default ETH)")
    ap.add_argument(
        "--day",
        default="",
        help="Pin UTC day YYYY-MM-DD (default: latest complete warehouse day)",
    )
    ap.add_argument(
        "--interval",
        type=float,
        default=None,
        help="Poll interval seconds (default: config ≈ 120)",
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
        help="Override log path (default logs/shadow.log)",
    )
    ap.add_argument(
        "--no-extra-venues",
        action="store_true",
        help="Primary venue only (skip Deribit/Kraken)",
    )
    ap.add_argument("--quiet", action="store_true", help="Log file only (no stdout)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.venue:
        cfg["venue"] = args.venue.lower()
    if args.symbol:
        cfg["symbol"] = args.symbol.upper()
    if args.no_extra_venues:
        cfg["extra_venues"] = []
    cfg["live_orders"] = False
    cfg["alpha_claim"] = False

    if bool(cfg.get("live_orders")):
        print("[vshapes_shadow] REFUSE: live_orders=True", file=sys.stderr)
        sys.exit(2)

    out_root = Path(args.out_dir) if args.out_dir else PKG / str(cfg.get("out_dir") or "out")
    out_root.mkdir(parents=True, exist_ok=True)

    log_path = (
        Path(args.log_file)
        if args.log_file
        else PKG / str(cfg.get("log_dir") or "logs") / str(cfg.get("log_file") or "shadow.log")
    )
    setup_logging(log_path, quiet=args.quiet)

    events_path = out_root / str(cfg.get("events_jsonl") or "events.jsonl")
    interval = float(
        args.interval
        if args.interval is not None
        else cfg.get("poll_interval_s") or 120.0
    )
    iterations = 0 if args.poll else int(args.iterations)
    day = args.day.strip() or None

    result = run_loop(
        cfg=cfg,
        out_root=out_root,
        events_path=events_path,
        interval_s=interval,
        iterations=iterations,
        day=day,
    )
    brief = {
        "n_polls": result.get("n_polls"),
        "last_ok": (result.get("last") or {}).get("ok"),
        "last_day": (result.get("last") or {}).get("day"),
        "any_breach": (result.get("last") or {}).get("any_breach"),
        "shadow_board": (result.get("last") or {}).get("shadow_board"),
        "log_file": str(log_path),
        "events_jsonl": str(events_path),
        "live_orders": False,
        "alpha_claim": False,
        "throttle_gate": "Kill",
        "throttle_gate_id": "exec.minv_breach_throttle",
        "monitor_gates": ["risk.egarch_minv_bands", "risk.daily_minv_panel"],
    }
    print(json.dumps(jsonable(brief), indent=2))


if __name__ == "__main__":
    main()
