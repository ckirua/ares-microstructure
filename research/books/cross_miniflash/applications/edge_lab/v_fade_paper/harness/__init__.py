"""TI-v-fade paper shadow harness (directional taker, not MM)."""

from .pipeline import run_v_fade_day, run_v_fade_panel
from .shadow import apply_vf_overrides, find_latest_complete_day, load_gap_summary

__all__ = [
    "run_v_fade_day",
    "run_v_fade_panel",
    "apply_vf_overrides",
    "find_latest_complete_day",
    "load_gap_summary",
]
