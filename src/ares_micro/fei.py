"""Keep legacy import path ``from ares_micro.fei import fei`` working."""

from research.lib.fei import entropy, fei

__all__ = ["entropy", "fei"]
