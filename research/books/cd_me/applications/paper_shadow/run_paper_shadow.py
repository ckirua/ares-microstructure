#!/usr/bin/env python3
"""cd_me paper_shadow SHADOW poller — PIM/DCM monitors (no exchange orders).

Examples:
  python3 run_paper_shadow.py --day 2026-09-29 --iterations 1
  python3 run_paper_shadow.py --iterations 1
  python3 run_paper_shadow.py --poll --interval 120

Never mercat/gateway OE. live_orders=False. ClickHouse MCP banned.
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

LOG = logging.getLogger("cdme_shadow")


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
    root = logging.getLogger("cdme_shadow")
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
    pim = brief.get("pim") or {}
    dcm = brief.get("dcm") or {}
    el = brief.get("elasticity") or {}
    lines = [
        "# cd_me SHADOW BOARD",
        "",
        f"**Day:** `{brief.get('day')}` · **Primary:** `{brief.get('venue')}` `{brief.get('symbol')}`",
        f"**UTC:** {brief.get('ts_utc')}",
        "",
        "> SHADOW only · `live_orders=false` · `alpha_claim=false` · "
        "PIM/DCM = **Hold Monitor** · TOB-cross α = **Kill** · never mercat/gateway OE",
        "",
        "## Gate labels (pinned)",
        "",
        "| ID | Gate | Role |",
        "|----|------|------|",
        f"| `risk.pim_cross_venue` | {gates.get('risk.pim_cross_venue', 'Hold')} | PIM telemetry |",
        f"| `risk.dcm_pc1` | {gates.get('risk.dcm_pc1', 'Hold')} | DCM̂ regime |",
        f"| `liq.elasticity_regime` | {gates.get('liq.elasticity_regime', 'Hold')} | Elasticity split |",
        f"| `info.vloop_tcost_commonality` | {gates.get('info.vloop_tcost_commonality', 'Hold')} | VLOOP↔TCOST |",
        f"| `alpha.tob_cross_arb` | {gates.get('alpha.tob_cross_arb', 'Kill')} | Never sized |",
        f"| `risk.bank_cds_var` | {gates.get('risk.bank_cds_var', 'Kill')} | Vanity |",
        "",
        "## Monitors",
        "",
        f"- **PIM** ok={pim.get('ok')} venues={pim.get('venues_tob')} "
        f"n_finite={pim.get('n_finite_pim')} mean={_fmt(pim.get('pim_mean'), 6)} "
        f"p50={_fmt(pim.get('pim_p50'), 6)} corr(V,T)={_fmt(pim.get('corr_vloop_tcost'), 3)} "
        f"gate=Hold",
        f"- **DCM̂** ok={dcm.get('ok')} home={dcm.get('home_venue')} "
        f"n_valid={dcm.get('n_valid')} explained={_fmt(dcm.get('explained_var'), 3)} "
        f"constrained_flag={dcm.get('constrained_flag')} gate=Hold",
        f"- **Elasticity** ok={el.get('ok')} source={el.get('source') or '—'} "
        f"all_corr={_fmt((el.get('all') or {}).get('corr'), 3)} "
        f"n={(el.get('all') or {}).get('n')} "
        f"regime_ok={(el.get('regime') or {}).get('ok')} "
        f"note={el.get('note') or el.get('reason')} gate=Hold",
        f"- **TOB gaps** {brief.get('tob_errors') or '{}'}",
        "",
        "## Artifacts",
        "",
        "- `logs/shadow.log`",
        "- `out/events.jsonl`",
        "- `out/shadow_meta.json`",
        "- research `out/pim_vloop_tcost/` / `out/dcm_proxies/` (when joined)",
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
    pim = brief.get("pim") or {}
    dcm = brief.get("dcm") or {}

    append_jsonl(
        events_path,
        {
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "poll": poll_i,
            "event": "heartbeat",
            "day": day_s,
            "symbol": brief.get("symbol"),
            "live_orders": False,
            "pim_ok": pim.get("ok"),
            "pim_mean": pim.get("pim_mean"),
            "pim_n_finite": pim.get("n_finite_pim"),
            "corr_vloop_tcost": pim.get("corr_vloop_tcost"),
            "dcm_ok": dcm.get("ok"),
            "dcm_n_valid": dcm.get("n_valid"),
            "constrained_flag": dcm.get("constrained_flag"),
            "gates": brief.get("gates"),
        },
    )
    if pim.get("ok"):
        append_jsonl(
            events_path,
            {
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "poll": poll_i,
                "event": "pim",
                "kind": "monitor",
                "gate": "Hold",
                "gate_id": "risk.pim_cross_venue",
                "day": day_s,
                "pim_mean": pim.get("pim_mean"),
                "venues_tob": pim.get("venues_tob"),
                "n_finite_pim": pim.get("n_finite_pim"),
                "live_orders": False,
            },
        )
        LOG.info(
            "PIM Hold Monitor day=%s venues=%s n_finite=%s mean=%s corr_VT=%s live_orders=false",
            day_s,
            pim.get("venues_tob"),
            pim.get("n_finite_pim"),
            _fmt(pim.get("pim_mean"), 6),
            _fmt(pim.get("corr_vloop_tcost"), 3),
        )
    else:
        LOG.info("PIM unavailable day=%s reason=%s", day_s, pim.get("reason") or pim.get("tob_errors"))

    if dcm.get("ok"):
        append_jsonl(
            events_path,
            {
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "poll": poll_i,
                "event": "dcm",
                "kind": "monitor",
                "gate": "Hold",
                "gate_id": "risk.dcm_pc1",
                "day": day_s,
                "n_valid": dcm.get("n_valid"),
                "constrained_flag": dcm.get("constrained_flag"),
                "live_orders": False,
            },
        )
        LOG.info(
            "DCM Hold Monitor day=%s home=%s n_valid=%s constrained=%s live_orders=false",
            day_s,
            dcm.get("home_venue"),
            dcm.get("n_valid"),
            dcm.get("constrained_flag"),
        )

    board = write_shadow_board(out_root, brief)
    meta_path = out_root / "shadow_meta.json"
    meta_path.write_text(json.dumps(jsonable(brief), indent=2) + "\n")

    # per-day summary
    day_dir = out_root / f"{day_s}_{brief.get('venue')}_{brief.get('symbol')}"
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "summary.json").write_text(json.dumps(jsonable(brief), indent=2) + "\n")

    elapsed = time.monotonic() - t0
    LOG.info(
        "HEARTBEAT poll=%s day=%s pim_ok=%s dcm_ok=%s elapsed_s=%.1f board=%s live_orders=false",
        poll_i,
        day_s,
        pim.get("ok"),
        dcm.get("ok"),
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
        # sleep in chunks for responsive stop
        slept = 0.0
        while slept < interval and not stop.stop:
            time.sleep(min(1.0, interval - slept))
            slept += 1.0

    LOG.info("STOP polls=%s", poll_i)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
