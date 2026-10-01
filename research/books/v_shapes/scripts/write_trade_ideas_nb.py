from __future__ import annotations
#!/usr/bin/env python3
"""Build memo-grade notebooks/trade_ideas.ipynb from frozen cell template.

Used by build_memo_notebooks.write_trade_ideas when the notebook is missing/stub.
Does not soft-Promote Holds. ClickHouse MCP banned.
"""

import json
import uuid
from pathlib import Path

BOOK = Path(__file__).resolve().parents[1]
TPL = Path(__file__).resolve().parent / "_trade_ideas_cells.json"
OUT_NB = BOOK / "notebooks" / "trade_ideas.ipynb"


def _source_lines(text: str) -> list[str]:
    if not text:
        return []
    parts = text.split("\n")
    if parts and parts[-1] == "":
        parts = parts[:-1]
    return [p + "\n" for p in parts]


def build_trade_ideas_notebook() -> Path:
    cells_spec = json.loads(TPL.read_text())
    cells = []
    for spec in cells_spec:
        cell: dict = {
            "cell_type": spec["cell_type"],
            "metadata": {},
            "id": uuid.uuid4().hex[:8],
            "source": _source_lines(spec["source"]),
        }
        if spec["cell_type"] == "code":
            cell["execution_count"] = None
            cell["outputs"] = []
        cells.append(cell)

    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "cells": cells,
    }
    OUT_NB.parent.mkdir(parents=True, exist_ok=True)
    OUT_NB.write_text(json.dumps(nb, indent=1))
    return OUT_NB


if __name__ == "__main__":
    p = build_trade_ideas_notebook()
    print("wrote", p)
