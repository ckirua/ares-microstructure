from __future__ import annotations
#!/usr/bin/env python3
"""Build / refresh desk-quality figures for Filimonov.

Reads pass1 + pass2 + hardening JSON; writes desk signal board and copies
index into ``out/desk_synthesis/figs/``. Chapter package figs are owned by
Pass1 runners (SoT) — this script does not delete them.

ClickHouse MCP banned. No git commit.
"""


import json
import shutil
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

BOOK = Path(__file__).resolve().parents[1]
OUT = BOOK / "out"
HARD = OUT / "hardening"
PASS2 = OUT / "pass2"
DESK = OUT / "desk_synthesis" / "figs"


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text())


def main() -> None:
    DESK.mkdir(parents=True, exist_ok=True)
    gates = _load(HARD / "hardening_gates.json")
    gmap = gates.get("gates") or {}
    if not gmap:
        # fallback pass2 rollup
        roll = _load(PASS2 / "pass2_rollup.json")
        flat = {}
        for labs in (roll.get("labels") or {}).values():
            flat.update(labs)
        gmap = flat

    if gmap:
        order = sorted(gmap.keys(), key=lambda k: (gmap[k].get("decision", "Z"), k))
        colors = {"Promote": "#1a7f37", "Hold": "#9a6700", "Kill": "#cf222e"}
        fig, ax = plt.subplots(figsize=(11, max(4.0, 0.26 * len(order) + 1.2)))
        for i, cid in enumerate(order):
            dec = gmap[cid].get("decision", "?")
            ax.barh(i, 1, color=colors.get(dec, "#888"), alpha=0.9)
            why = str(gmap[cid].get("why", ""))[:70]
            ax.text(
                0.02,
                i,
                f"{dec:7s}  {cid}  — {why}",
                va="center",
                fontsize=7.5,
                fontfamily="monospace",
            )
        ax.set_yticks([])
        ax.set_xlim(0, 1)
        ax.set_xticks([])
        p = sum(1 for g in gmap.values() if g.get("decision") == "Promote")
        h = sum(1 for g in gmap.values() if g.get("decision") == "Hold")
        k = sum(1 for g in gmap.values() if g.get("decision") == "Kill")
        ax.set_title(f"Filimonov desk signal board — {p} Promote / {h} Hold / {k} Kill")
        fig.tight_layout()
        for dest in (DESK / "signal_board.png", HARD / "figs" / "signal_board.png"):
            dest.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(dest, dpi=130)
        plt.close(fig)
        print(f"signal_board → {p}/{h}/{k}", flush=True)

    # copy useful pass2 figs into desk_synthesis
    for name in ("fig_overlap_gates.png", "fig_pass2_labels.png", "fig_fade_markout_delta.png"):
        src = PASS2 / "figs" / name
        if src.is_file():
            shutil.copy2(src, DESK / name)
            print(f"copied {name}", flush=True)

    # venue completeness mini-fig from pass1 coverage if present
    cov = _load(OUT / "ch00_overview" / "coverage.json")
    if cov:
        fig, ax = plt.subplots(figsize=(7, 3.2))
        rows = cov.get("rows") or cov.get("venue_days") or []
        if isinstance(rows, list) and rows:
            labels, vals = [], []
            for r in rows:
                if isinstance(r, dict):
                    labels.append(f"{r.get('venue','?')[:2]} {str(r.get('day',''))[-5:]}")
                    vals.append(1.0 if r.get("complete") else 0.0)
            if labels:
                ax.bar(range(len(labels)), vals, color="#1f4e79")
                ax.set_xticks(range(len(labels)))
                ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
                ax.set_ylim(0, 1.2)
                ax.set_ylabel("complete")
                ax.set_title("Venue-day completeness (Pass1)")
                fig.tight_layout()
                fig.savefig(DESK / "fig_completeness.png", dpi=120)
                plt.close(fig)

    # index json
    index = {
        "desk_figs": sorted(p.name for p in DESK.glob("*.png")),
        "package_figs": {
            pkg: sorted(p.name for p in (OUT / pkg / "figs").glob("*.png"))
            if (OUT / pkg / "figs").is_dir()
            else []
            for pkg in (
                "ch00_overview",
                "latency_size_regimes",
                "quote_storms",
                "book_fade",
                "momentum_ignition",
                "spoof_smoke_clock",
            )
        },
    }
    (OUT / "desk_synthesis" / "fig_index.json").write_text(json.dumps(index, indent=2))
    print(f"Wrote {DESK}", flush=True)


if __name__ == "__main__":
    main()
