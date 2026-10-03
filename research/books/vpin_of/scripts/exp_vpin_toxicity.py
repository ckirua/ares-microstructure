#!/usr/bin/env python3
"""Pass 2 toxicity TOB join — writes ``out/pass2/toxicity.json``."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from exp_pass2 import OUT, run_toxicity  # noqa: E402


def _panel() -> list:
    cache = OUT / "panel_hl_db_extended.json"
    if cache.is_file():
        return json.loads(cache.read_text())
    raise SystemExit("missing out/pass2/panel_hl_db_extended.json — run exp_pass2.py first")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    toxicity = run_toxicity(_panel())
    (OUT / "toxicity.json").write_text(json.dumps(toxicity, indent=2) + "\n")
    print(json.dumps({"decision": toxicity.get("decision"), "n_days": toxicity.get("n_days")}, indent=2))


if __name__ == "__main__":
    main()
