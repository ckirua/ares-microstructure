#!/usr/bin/env python3
"""Pass 2 markout only — writes ``out/pass2/markout.json``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from exp_pass2 import OUT, run_markout  # noqa: E402


def _panel() -> list:
    cache = OUT / "panel_hl_db_extended.json"
    if cache.is_file():
        return json.loads(cache.read_text())
    raise SystemExit("missing out/pass2/panel_hl_db_extended.json — run exp_pass2.py first")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--markout-max-days", type=int, default=0)
    ap.add_argument("--trade-stride", type=int, default=50)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    panel = _panel()
    max_d = args.markout_max_days or None
    markout = run_markout(panel, max_days=max_d, trade_stride=args.trade_stride)
    (OUT / "markout.json").write_text(json.dumps(markout, indent=2) + "\n")
    print(json.dumps({"decision": markout.get("decision"), "n_days_ok": markout.get("n_days_ok")}, indent=2))


if __name__ == "__main__":
    main()
