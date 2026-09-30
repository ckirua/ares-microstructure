"""Expanded lab — longer panel, richer strategies, risk scoreboard.

Sibling to ``strategy_lab`` / ``paper_harness``. Own ``out/`` cache so shared
``applications/out/event_panel`` is never overwritten.
"""

__all__ = ["LAB", "OUT"]

from pathlib import Path

LAB = Path(__file__).resolve().parent
OUT = LAB / "out"
