#!/usr/bin/env python3
"""Living V-fade SHADOW day — latest complete warehouse day.

  python3 run_shadow_day.py
  python3 run_shadow_day.py --confirm-s 1.0 --exit-s 8.0
  python3 run_shadow_day.py --gap-summary out/gap_summary.json

Writes: out/SHADOW_BOARD.md · out/trades.jsonl · out/shadow_meta.json
Never routes live orders. ClickHouse MCP banned.
"""

from __future__ import annotations

import sys

# Delegate to the main CLI with --shadow prepended (idempotent if already present).
argv = sys.argv[1:]
if "--shadow" not in argv:
    argv = ["--shadow", *argv]
sys.argv = [sys.argv[0], *argv]

from run_v_fade_paper import main  # noqa: E402

if __name__ == "__main__":
    main()
