from __future__ import annotations
#!/usr/bin/env python3
"""Run tick_shadow living sleeve — HL trades WS + incremental SSM severity_zend.

Shadow fills only. Refuses live_orders=true. Warehouse poll peers unchanged.
"""


import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from live.logging_setup import setup_logging  # noqa: E402
from live.loop import run_loop  # noqa: E402


def load_config(path: Path) -> dict:
    with path.open() as f:
        cfg = yaml.safe_load(f) or {}
    if not isinstance(cfg, dict):
        raise SystemExit(f"bad config: {path}")
    return cfg


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="tick_shadow HL trades WS sleeve (shadow only)")
    ap.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    ap.add_argument("--coin", type=str, default=None, help="override coin (default ETH)")
    ap.add_argument("--heartbeat-s", type=float, default=None)
    ap.add_argument("--max-seconds", type=float, default=None, help="smoke: stop after N seconds")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    if bool(cfg.get("live_orders")):
        print("REFUSE: live_orders=true", file=sys.stderr)
        return 2
    if args.coin:
        cfg["coin"] = args.coin.upper()
        cfg["symbol"] = args.coin.upper()
    if args.heartbeat_s is not None:
        cfg["heartbeat_s"] = float(args.heartbeat_s)

    log_dir = ROOT / str(cfg.get("log_dir") or "logs")
    log_file = str(cfg.get("log_file") or "tick_shadow.log")
    setup_logging(log_dir / log_file, quiet=bool(args.quiet))

    run_loop(cfg, root=ROOT, max_seconds=args.max_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
