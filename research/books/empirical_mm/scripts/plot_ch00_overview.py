from __future__ import annotations
#!/usr/bin/env python3
"""Ch.00 overview — roadmap status board from CHAPTER_INDEX package inventory."""


import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

BOOK = Path(__file__).resolve().parents[1]
OUT = BOOK / "out" / "ch00_overview"

# (label, package dir or None, status, part)
ROADMAP = [
    ("Ch.0–2 Overview", "ch00_overview", "notes", "I"),
    ("Ch.3 Roll", "ch03_roll", "exp_run", "I"),
    ("Ch.4 MA/AR → ch09", None, "folded", "I"),
    ("Ch.5 Seq. info", "ch05_seq_info", "notes", "I"),
    ("Ch.6 Strategic", "ch06_strategic", "notes", "I"),
    ("Ch.7–8 Noise", "ch08_noise", "exp_run", "I"),
    ("Ch.9 Estimation", "ch09_estimation", "exp_run", "I"),
    ("Ch.10 Trades", "ch10_trades", "iterate", "II"),
    ("Ch.11–12 → ch13", None, "folded", "II"),
    ("Ch.13 VAR/impact", "ch13_var_impact", "exp_run", "II"),
    ("Ch.14 Structural", "ch14_structural", "exp_run", "II"),
    ("Ch.15 PIN/VPIN", "ch15_pin", "exp_run", "II"),
    ("Ch.16 Asymmetry", "ch16_asymmetry", "notes", "II"),
    ("Ch.17 Discovery", "ch17_discovery", "iterate", "II"),
    ("Ch.18–21 LOB", "ch18_limit_orders", "iterate", "III"),
    ("Ch.22 Liquidity", "ch22_liquidity", "iterate", "IV"),
    ("App. US equity", "appendix_us", "park", "App"),
]

STATUS_COLOR = {
    "exp_run": "#1f4e79",
    "iterate": "#2e7d4f",
    "notes": "#b8860b",
    "folded": "#7a7a7a",
    "park": "#8b4513",
    "todo": "#c0c0c0",
}


def _pkg_stats(pkg: str | None) -> dict:
    if not pkg:
        return {"notes_lines": 0, "n_figs": 0, "notebook": False}
    d = BOOK / "chapters" / pkg
    notes = d / "NOTES.md"
    n_lines = len(notes.read_text().splitlines()) if notes.exists() else 0
    out = BOOK / "out" / pkg
    n_figs = len(list(out.glob("*.png"))) if out.exists() else 0
    notebook = any(d.glob("*.ipynb")) if d.exists() else False
    return {"notes_lines": n_lines, "n_figs": n_figs, "notebook": notebook}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for label, pkg, status, part in ROADMAP:
        st = _pkg_stats(pkg)
        rows.append(
            {
                "label": label,
                "pkg": pkg or "—",
                "status": status,
                "part": part,
                **st,
            }
        )

    # --- fig_roadmap_status ---
    fig, ax = plt.subplots(figsize=(11.5, 7.2))
    y = np.arange(len(rows))[::-1]
    colors = [STATUS_COLOR[r["status"]] for r in rows]
    ax.barh(y, [1] * len(rows), color=colors, height=0.72, edgecolor="white", linewidth=0.6)

    for i, r in enumerate(rows):
        yi = y[i]
        nb = "nb✓" if r["notebook"] else ("—" if r["status"] == "folded" else "nb✗")
        meta = f"{r['status']}  ·  NOTES {r['notes_lines']}L  ·  figs {r['n_figs']}  ·  {nb}"
        ax.text(0.02, yi, r["label"], va="center", ha="left", color="white", fontsize=9, fontweight="bold")
        ax.text(0.98, yi, meta, va="center", ha="right", color="white", fontsize=7.5, alpha=0.95)

    ax.set_xlim(0, 1)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.set_title(
        "Empirical MM — chapter status board (from CHAPTER_INDEX)",
        fontsize=13,
        pad=10,
    )
    # part separators as left spine labels via twin text
    handles = [
        mpatches.Patch(color=c, label=s)
        for s, c in [
            ("exp_run", STATUS_COLOR["exp_run"]),
            ("iterate", STATUS_COLOR["iterate"]),
            ("notes", STATUS_COLOR["notes"]),
            ("folded", STATUS_COLOR["folded"]),
            ("park", STATUS_COLOR["park"]),
        ]
    ]
    ax.legend(handles=handles, loc="lower right", framealpha=0.92, fontsize=8, ncol=5)
    ax.set_xlabel("Hasbrouck Draft 1.1 → research packages  ·  public-tape Holds pass COMPLETE (2026-09-30)")
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    fig_path = OUT / "fig_roadmap_status.png"
    fig.savefig(fig_path, dpi=140, bbox_inches="tight")
    plt.close(fig)

    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "kind": "roadmap_status_board",
        "source": "CHAPTER_INDEX roadmap + on-disk package inventory",
        "rows": rows,
        "figures": ["fig_roadmap_status.png"],
        "desk_pointers": {
            "index": "CHAPTER_INDEX.md",
            "memo": "DESK_MEMO.md",
            "coverage": "docs/COVERAGE.md",
            "synthesis": "notebooks/desk_synthesis.ipynb",
        },
    }
    (OUT / "exp_ch00_roadmap_summary.json").write_text(json.dumps(summary, indent=2))
    print("wrote", fig_path, "rows", len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
