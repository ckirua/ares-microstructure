from __future__ import annotations
#!/usr/bin/env python3
"""Thin orchestrator: Pass1 sibling runners remain SoT; this chains them.

Usage::

    python scripts/exp_pass12.py              # pass1 all + pass2
    python scripts/exp_pass12.py --pass2-only
    python scripts/exp_pass12.py --harden

ClickHouse MCP banned.
"""


import argparse
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
PY = sys.executable


def _run(script: str, extra: list[str] | None = None) -> None:
    cmd = [PY, str(SCRIPTS / script), *(extra or [])]
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pass2-only", action="store_true")
    ap.add_argument("--harden", action="store_true", help="Also run exp_final_hardening")
    ap.add_argument("--skip-btc", action="store_true")
    ap.add_argument("--days", nargs="*", default=["2026-09-26", "2026-09-27", "2026-09-30"])
    args = ap.parse_args()
    day_args = ["--days", *args.days]

    if not args.pass2_only:
        _run("exp_ch00_latency.py", day_args)
        _run("exp_core_detectors.py", day_args)
        _run("exp_spoof_clock.py", day_args)
    _run("exp_pass2_info.py", day_args)
    if args.harden:
        harden_args = list(day_args)
        if args.skip_btc:
            harden_args.append("--skip-btc")
        _run("exp_final_hardening.py", harden_args)
        _run("exp_build_figs.py", [])


if __name__ == "__main__":
    main()
