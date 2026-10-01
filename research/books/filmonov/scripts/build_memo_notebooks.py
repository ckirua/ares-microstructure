from __future__ import annotations
#!/usr/bin/env python3
"""Refresh memo notebooks after hardening (desk_synthesis + light chapter stubs).

Chapter package notebooks remain owned by Pass1 runners; this ensures
``notebooks/desk_synthesis.ipynb`` exists and points at frozen artifacts.
"""


import json
import sys
from pathlib import Path

BOOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Re-use hardening notebook writer if gates exist
HARD = BOOK / "out" / "hardening" / "hardening_gates.json"


def main() -> None:
    if not HARD.is_file():
        print("missing hardening_gates.json — run exp_final_hardening.py first", flush=True)
        sys.exit(1)
    artifact = json.loads(HARD.read_text())
    from exp_final_hardening import write_desk_synthesis_nb  # noqa: E402

    write_desk_synthesis_nb(artifact)
    print(f"Wrote {BOOK / 'notebooks' / 'desk_synthesis.ipynb'}", flush=True)


if __name__ == "__main__":
    main()
