from __future__ import annotations
#!/usr/bin/env python3
"""Run MM quoting + feature models once (shared panel)."""


import os
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent
BOOK = APP.parent
ROOT = BOOK.parents[2]
STARTARB = Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb'))
WAREHOUSE_SRC = Path(os.environ.get('WAREHOUSE_SRC') or ((Path(os.environ.get('WAREHOUSE_ROOT') or (Path.home() / 'lab' / 'lab-n2070' / 'warehouse')) / 'src')))


def _env() -> dict[str, str]:
    env = dict(os.environ)
    paths = [
        str(ROOT),
        str(STARTARB / "src"),
        str(WAREHOUSE_SRC),
        str(BOOK / "scripts"),
        str(APP),
    ]
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(paths + ([prev] if prev else []))
    return env


def main() -> int:
    mm = APP / "mm_quoting" / "exp_v_continuation_quoting.py"
    feat = APP / "feature_models" / "exp_feature_models.py"
    cache = APP / "mm_quoting" / "out" / "panel_cache.json"
    env = _env()
    print("=== MM quoting ===", flush=True)
    mm_args = list(sys.argv[1:])
    if cache.exists() and "--reuse-panel" not in mm_args and "--force-rebuild" not in mm_args:
        mm_args = ["--reuse-panel", str(cache), *mm_args]
    r1 = subprocess.run([sys.executable, str(mm), *mm_args], check=False, env=env)
    if r1.returncode != 0:
        return r1.returncode
    print("=== Feature models ===", flush=True)
    args = list(sys.argv[1:])
    if cache.exists() and "--panel-json" not in args:
        args = ["--panel-json", str(cache), *args]
    r2 = subprocess.run([sys.executable, str(feat), *args], check=False, env=env)
    return r2.returncode


if __name__ == "__main__":
    raise SystemExit(main())
