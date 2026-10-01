from __future__ import annotations
#!/usr/bin/env python3
"""Merge Pass-2 expand + info candidates into desk board artifacts.

Updates ``out/pass2_expand/expand_board.json``, signal board PNG under
``out/pass2_expand/figs/`` + desk_synthesis, and refreshes desk notebook.
Does not rewrite Pass-2.5 freeze file; expand is additive.
"""

import os

import json
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BOOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

HARD = BOOK / "out" / "hardening" / "hardening_gates.json"
INFO = BOOK / "out" / "pass2_expand" / "info_features.json"
EXPAND = BOOK / "out" / "pass2_expand" / "pass2_expand_rollup.json"
OUT = BOOK / "out" / "pass2_expand"


def _default(o: Any) -> Any:
    if isinstance(o, float) and (o != o):
        return None
    return str(o)


def write_signal_board(gates: dict[str, dict], path: Path) -> None:
    order = sorted(gates.keys(), key=lambda k: (gates[k].get("decision", "Z"), k))
    n = len(order)
    fig_h = max(6.0, 0.28 * n + 1.5)
    fig, ax = plt.subplots(figsize=(11.5, fig_h))
    colors = {"Promote": "#2a9d8f", "Hold": "#e9c46a", "Kill": "#e76f51"}
    y = list(range(n))
    for i, cid in enumerate(order):
        dec = gates[cid].get("decision", "?")
        ax.barh(i, 1.0, color=colors.get(dec, "#adb5bd"), height=0.8)
        why = str(gates[cid].get("why", ""))[:78]
        ax.text(0.02, i, f"{dec:7s}  {cid}", va="center", fontsize=7, fontfamily="monospace")
        ax.text(1.05, i, why, va="center", fontsize=6, color="#333")
    ax.set_yticks([])
    ax.set_xlim(0, 3.2)
    ax.set_xticks([])
    n_p = sum(1 for g in gates.values() if g.get("decision") == "Promote")
    n_h = sum(1 for g in gates.values() if g.get("decision") == "Hold")
    n_k = sum(1 for g in gates.values() if g.get("decision") == "Kill")
    ax.set_title(f"Filimonov expand board — {n_p} Promote / {n_h} Hold / {n_k} Kill", fontsize=11)
    for spine in ax.spines.values():
        spine.set_visible(False)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def write_desk_nb(artifact: dict[str, Any]) -> None:
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "# Desk synthesis — Filimonov HFT (Pass-2 expand)\n",
                    "\n",
                    f"**{artifact['n_promote']} Promote / {artifact['n_hold']} Hold / {artifact['n_kill']} Kill** "
                    f"on ETH+BTC HL+Deribit+Kraken (days {', '.join(artifact['days'])}).\n",
                    "\n",
                    "Frozen Pass-2.5 (0/13/11) + expand info dig (+8 Hold). Defaults: **monitor / exec throttle / risk-policy**.\n",
                    "Kraken TOB is **trade_synth** — excluded from native fade. See [`APPLICATIONS.md`](../APPLICATIONS.md).\n",
                ],
            },
            {
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": [
                    "import json\n",
                    "from pathlib import Path\n",
                    "from IPython.display import Image, display\n",
                    "BOOK = (Path(os.environ.get('ARES_MICROSTRUCTURE') or (Path.home() / 'srv' / 'ares-microstructure')) / 'research' / 'books' / 'filmonov')\n",
                    "board = json.loads((BOOK/'out/pass2_expand/expand_board.json').read_text())\n",
                    "print('days', board['days'], 'early', board.get('early'), 'late', board.get('late'))\n",
                    "print('counts', board['n_promote'], board['n_hold'], board['n_kill'])\n",
                    "print('expand boots', board.get('expand_boots'))\n",
                    "for cid, g in sorted(board['gates'].items(), key=lambda kv: (kv[1]['decision'], kv[0])):\n",
                    "    print(f\"{g['decision']:7s}  {cid}\")\n",
                ],
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": ["### Signal board\n", "\n", "`out/pass2_expand/figs/signal_board.png` + desk copy\n"],
            },
            {
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": [
                    "display(Image(filename=str(BOOK/'out/pass2_expand/figs/signal_board.png')))\n",
                ],
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "### Expand dig figs\n",
                    "\n",
                    "Forest / ToD / τ-sensitivity / lead-lag / info IRFs under `out/pass2_expand/figs/`.\n",
                ],
            },
            {
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": [
                    "figs = sorted((BOOK/'out/pass2_expand/figs').glob('fig_*.png'))\n",
                    "print(len(figs), 'expand figs')\n",
                    "for p in figs[:8]:\n",
                    "    print(p.name); display(Image(filename=str(p)))\n",
                ],
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "### Desk jobs × wire-as\n",
                    "\n",
                    "See `DESK_MEMO.md` §1 and `APPLICATIONS.md` — storm throttle, fade MM-pull, "
                    "ignition escalate, clock/funding monitor, size×storm exec clip.\n",
                ],
            },
        ],
    }
    path = BOOK / "notebooks" / "desk_synthesis.ipynb"
    path.write_text(json.dumps(nb, indent=1))
    print("Wrote", path)


def main() -> None:
    hard = json.loads(HARD.read_text())
    info = json.loads(INFO.read_text())
    expand = json.loads(EXPAND.read_text())
    gates = dict(hard.get("gates") or {})
    # add info candidates
    for cid, g in (info.get("decisions") or {}).get("labels", {}).items():
        gates[cid] = {
            "decision": g["decision"],
            "why": g.get("why", ""),
            "type": g.get("type"),
            "lenses": g.get("lenses"),
            "monitor": g.get("monitor"),
            "tradable": g.get("tradable"),
            "exec_throttle": g.get("exec_throttle"),
            "falsifier": g.get("falsifier"),
            "source": "pass2_expand_info",
        }
    n_p = sum(1 for g in gates.values() if g.get("decision") == "Promote")
    n_h = sum(1 for g in gates.values() if g.get("decision") == "Hold")
    n_k = sum(1 for g in gates.values() if g.get("decision") == "Kill")
    artifact = {
        "days": expand.get("days"),
        "symbols": expand.get("symbols"),
        "early": (expand.get("summary") or {}).get("early"),
        "late": (expand.get("summary") or {}).get("late"),
        "n_promote": n_p,
        "n_hold": n_h,
        "n_kill": n_k,
        "legacy_freeze": {"n_promote": 0, "n_hold": 13, "n_kill": 11},
        "expand_info_added": {
            "n_promote": info["decisions"]["n_promote"],
            "n_hold": info["decisions"]["n_hold"],
            "n_kill": info["decisions"]["n_kill"],
        },
        "expand_boots": (expand.get("summary") or {}).get("boots"),
        "gates": gates,
        "fig_paths": list(expand.get("fig_paths") or []) + list(info.get("fig_paths") or []),
        "applications": "APPLICATIONS.md",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "expand_board.json").write_text(json.dumps(artifact, indent=2, default=_default))
    board_path = OUT / "figs" / "signal_board.png"
    write_signal_board(gates, board_path)
    # desk + hardening copies for notebook compatibility
    import shutil

    desk_figs = BOOK / "out" / "desk_synthesis" / "figs"
    desk_figs.mkdir(parents=True, exist_ok=True)
    shutil.copy2(board_path, desk_figs / "signal_board.png")
    shutil.copy2(board_path, BOOK / "out" / "hardening" / "figs" / "signal_board.png")
    (BOOK / "out" / "desk_synthesis" / "fig_index.json").write_text(
        json.dumps({"figs": artifact["fig_paths"] + ["out/pass2_expand/figs/signal_board.png"]}, indent=2)
    )
    write_desk_nb(artifact)
    print(f"Board {n_p}/{n_h}/{n_k} → {OUT / 'expand_board.json'}")
    print("signal_board", board_path)


if __name__ == "__main__":
    main()
