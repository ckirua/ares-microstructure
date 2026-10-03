#!/usr/bin/env python3
"""squeeze_metrics paper_shadow SHADOW poller — GEX/VEX/squeeze monitors (no exchange orders).

Examples:
  python3 run_paper_shadow.py --day 2026-09-29 --iterations 1
  python3 run_paper_shadow.py --iterations 1
  python3 run_paper_shadow.py --poll --interval 120

Never mercat/gateway OE. live_orders=False. ClickHouse MCP banned.
Wire Promote only (expect 0 Promote). Never soft-Promote TOB-cross as α.
"""

from __future__ import annotations

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

LOG = logging.getLogger("squeeze_shadow")


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
    root = logging.getLogger("squeeze_shadow")
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


def _fmt(x: Any, nd: int = 4) -> str:
    if x is None:
        return "—"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    if not (v == v):
        return "—"
    return f"{v:.{nd}f}"


def write_shadow_board(out_root: Path, brief: dict[str, Any]) -> Path:
    path = out_root / "SHADOW_BOARD.md"
    gates = brief.get("gates") or {}
    gex = brief.get("gex") or {}
    vex = brief.get("vex") or {}
    sq = brief.get("squeeze") or {}
    sc = brief.get("scarcity") or {}
    deps = brief.get("deps") or {}
    promotes = brief.get("promote_ids") or []
    lines = [
        "# squeeze_metrics SHADOW BOARD",
        "",
        f"**Day:** `{brief.get('day')}` · **Primary:** `{brief.get('venue')}` `{brief.get('symbol')}`",
        f"**UTC:** {brief.get('ts_utc')}",
        "",
        "> SHADOW only · `live_orders=false` · `alpha_claim=false` · "
        "GEX/VEX/squeeze/scarcity = **Hold Monitor** · TOB-cross α = **Kill** · "
        f"Promote count = **{brief.get('promote_count', 0)}** · never mercat/gateway OE",
        "",
        "## Gate labels (pinned)",
        "",
        "| ID | Gate | Role |",
        "|----|------|------|",
        f"| `risk.gex_exposure` | {gates.get('risk.gex_exposure', 'Hold')} | GEX telemetry |",
        f"| `risk.vex_exposure` | {gates.get('risk.vex_exposure', 'Hold')} | VEX telemetry |",
        f"| `risk.squeeze_intensity` | {gates.get('risk.squeeze_intensity', 'Hold')} | GEX+ / squeeze |",
        f"| `liq.implied_book_scarcity` | {gates.get('liq.implied_book_scarcity', 'Hold')} | Implied-book scarcity |",
        f"| `alpha.tob_cross_arb` | {gates.get('alpha.tob_cross_arb', 'Kill')} | Never sized |",
        "",
        "## Promote wiring",
        "",
        f"- Promote IDs: `{promotes or []}` (wire Promote only; expect 0)",
        "",
        "## Monitors",
        "",
        f"- **GEX** ok={gex.get('ok')} mean={_fmt(gex.get('gex_mean') or gex.get('value'), 4)} "
        f"reason={gex.get('reason') or '—'} gate=Hold",
        f"- **VEX** ok={vex.get('ok')} mean={_fmt(vex.get('vex_mean') or vex.get('value'), 4)} "
        f"reason={vex.get('reason') or '—'} gate=Hold",
        f"- **Squeeze** ok={sq.get('ok')} intensity={_fmt(sq.get('intensity') or sq.get('value'), 4)} "
        f"reason={sq.get('reason') or '—'} gate=Hold",
        f"- **Scarcity** ok={sc.get('ok')} scarcity={_fmt(sc.get('scarcity') or sc.get('value'), 4)} "
        f"reason={sc.get('reason') or '—'} gate=Hold",
        f"- **Source** {brief.get('monitor_source') or '—'}",
        f"- **Deps** lib={((deps.get('lib_squeeze') or {}).get('reason') or ((deps.get('lib_squeeze') or {}).get('ok')))} "
        f"data={((deps.get('data_loader') or {}).get('reason') or ((deps.get('data_loader') or {}).get('ok')))}",
        "",
        "## Artifacts",
        "",
        "- `logs/shadow.log`",
        "- `out/events.jsonl`",
        "- `out/shadow_meta.json`",
        "- research `out/squeeze_metrics/` (when joined)",
        "",
    ]
    path.write_text("\n".join(lines) + "\n")
    return path


def poll_once(
    *,
    cfg: dict[str, Any],
    out_root: Path,
    events_path: Path,
    poll_i: int,
    day: str | None,
) -> dict[str, Any]:
    if bool(cfg.get("live_orders")):
        raise RuntimeError("hard refuse: live_orders=True")

    t0 = time.monotonic()
    brief = compute_day_monitors(cfg=cfg, day=day)
    day_s = str(brief.get("day") or "")
    gex = brief.get("gex") or {}
    vex = brief.get("vex") or {}
    sq = brief.get("squeeze") or {}
    sc = brief.get("scarcity") or {}
    promote_ids = brief.get("promote_ids") or []

    append_jsonl(
        events_path,
        {
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "poll": poll_i,
            "event": "heartbeat",
            "day": day_s,
            "symbol": brief.get("symbol"),
            "live_orders": False,
            "gex_ok": gex.get("ok"),
            "vex_ok": vex.get("ok"),
            "squeeze_ok": sq.get("ok"),
            "scarcity_ok": sc.get("ok"),
            "promote_count": brief.get("promote_count"),
            "promote_ids": promote_ids,
            "gates": brief.get("gates"),
            "deps": brief.get("deps"),
        },
    )

    for name, block, gate_id, event in (
        ("GEX", gex, "risk.gex_exposure", "gex"),
        ("VEX", vex, "risk.vex_exposure", "vex"),
        ("Squeeze", sq, "risk.squeeze_intensity", "squeeze"),
        ("Scarcity", sc, "liq.implied_book_scarcity", "scarcity"),
    ):
        if block.get("ok"):
            append_jsonl(
                events_path,
                {
                    "ts_utc": datetime.now(timezone.utc).isoformat(),
                    "poll": poll_i,
                    "event": event,
                    "kind": "monitor",
                    "gate": "Hold",
                    "gate_id": gate_id,
                    "day": day_s,
                    "live_orders": False,
                    "block": {k: block.get(k) for k in ("value", "gex_mean", "vex_mean", "intensity", "scarcity") if k in block},
                },
            )
            LOG.info(
                "%s Hold Monitor day=%s ok=true gate=%s live_orders=false",
                name,
                day_s,
                gate_id,
            )
        else:
            LOG.info(
                "%s unavailable day=%s reason=%s",
                name,
                day_s,
                block.get("reason") or "unknown",
            )

    # Promote-only action surface (expect empty)
    if promote_ids:
        append_jsonl(
            events_path,
            {
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "poll": poll_i,
                "event": "promote",
                "kind": "actionable",
                "promote_ids": promote_ids,
                "day": day_s,
                "live_orders": False,
            },
        )
        LOG.info("PROMOTE surface day=%s ids=%s (still no orders)", day_s, promote_ids)
    else:
        LOG.info("Promote count=0 day=%s (wire Promote only)", day_s)

    board = write_shadow_board(out_root, brief)
    meta_path = out_root / "shadow_meta.json"
    meta_path.write_text(json.dumps(jsonable(brief), indent=2) + "\n")

    day_dir = out_root / f"{day_s}_{brief.get('venue')}_{brief.get('symbol')}"
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "summary.json").write_text(json.dumps(jsonable(brief), indent=2) + "\n")

    elapsed = time.monotonic() - t0
    LOG.info(
        "HEARTBEAT poll=%s day=%s gex_ok=%s vex_ok=%s squeeze_ok=%s scarcity_ok=%s "
        "promote_count=%s elapsed_s=%.1f board=%s live_orders=false",
        poll_i,
        day_s,
        gex.get("ok"),
        vex.get("ok"),
        sq.get("ok"),
        sc.get("ok"),
        brief.get("promote_count"),
        elapsed,
        board.name,
    )
    return brief


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=None)
    ap.add_argument("--day", default=None, help="UTC day YYYY-MM-DD")
    ap.add_argument("--poll", action="store_true", help="Run forever")
    ap.add_argument("--interval", type=float, default=None)
    ap.add_argument("--iterations", type=int, default=None, help="Finite polls (default 1 if not --poll)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    cfg = load_config(args.config)
    cfg["live_orders"] = False
    out_root = PKG / str(cfg.get("out_dir") or "out")
    log_dir = PKG / str(cfg.get("log_dir") or "logs")
    out_root.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(log_dir / str(cfg.get("log_file") or "shadow.log"), quiet=args.quiet)
    events_path = out_root / str(cfg.get("events_jsonl") or "events.jsonl")

    interval = float(args.interval if args.interval is not None else cfg.get("poll_interval_s") or 120.0)
    n_iter = args.iterations
    if n_iter is None:
        n_iter = None if args.poll else 1

    LOG.info(
        "START venue=%s symbol=%s live_orders=false gates=%s",
        cfg.get("venue"),
        cfg.get("symbol"),
        cfg.get("gates"),
    )
    stop = _StopFlag()
    signal.signal(signal.SIGINT, stop.request)
    signal.signal(signal.SIGTERM, stop.request)

    poll_i = 0
    while not stop.stop:
        poll_i += 1
        try:
            poll_once(
                cfg=cfg,
                out_root=out_root,
                events_path=events_path,
                poll_i=poll_i,
                day=args.day,
            )
        except Exception as exc:  # noqa: BLE001
            LOG.exception("poll failed: %s", exc)
        if n_iter is not None and poll_i >= n_iter:
            break
        if stop.stop:
            break
        slept = 0.0
        while slept < interval and not stop.stop:
            time.sleep(min(1.0, interval - slept))
            slept += 1.0

    LOG.info("STOP polls=%s", poll_i)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
