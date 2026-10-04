"""Equity / drawdown / early-late metrics for strategy lab."""

from __future__ import annotations

from typing import Any

import numpy as np

from ares_micro.stats import bootstrap_ci


def equity_stats(equity_bps: np.ndarray) -> dict[str, Any]:
    eq = np.asarray(equity_bps, dtype=np.float64)
    if eq.size == 0 or not np.isfinite(eq).any():
        return {
            "n": 0,
            "final_bps": float("nan"),
            "mean_step_bps": float("nan"),
            "max_dd_bps": float("nan"),
            "vol_step_bps": float("nan"),
            "sharpe_like": float("nan"),
        }
    eq = eq[np.isfinite(eq)]
    peak = np.maximum.accumulate(eq)
    dd = eq - peak
    steps = np.diff(eq, prepend=eq[0])
    vol = float(np.std(steps, ddof=1)) if steps.size > 1 else 0.0
    mean_step = float(np.mean(steps))
    sharpe = mean_step / vol if vol > 1e-12 else float("nan")
    return {
        "n": int(eq.size),
        "final_bps": float(eq[-1]),
        "mean_step_bps": mean_step,
        "max_dd_bps": float(np.min(dd)),
        "vol_step_bps": vol,
        "sharpe_like": sharpe,
        "final_boot": bootstrap_ci(steps, n_boot=600, seed=17),
    }


def early_late_metrics(
    day_equity: dict[str, float],
    early_days: set[str],
    late_days: set[str],
) -> dict[str, Any]:
    e = np.asarray([v for d, v in day_equity.items() if d in early_days], dtype=np.float64)
    l = np.asarray([v for d, v in day_equity.items() if d in late_days], dtype=np.float64)
    e = e[np.isfinite(e)]
    l = l[np.isfinite(l)]
    return {
        "early_mean_final_bps": float(e.mean()) if e.size else float("nan"),
        "late_mean_final_bps": float(l.mean()) if l.size else float("nan"),
        "early_n_days": int(e.size),
        "late_n_days": int(l.size),
        "sign_stable": bool(
            e.size and l.size and np.sign(e.mean()) == np.sign(l.mean()) and abs(e.mean()) > 0
        ),
        "early_boot": bootstrap_ci(e, n_boot=400, seed=3) if e.size else None,
        "late_boot": bootstrap_ci(l, n_boot=400, seed=4) if l.size else None,
    }


def max_drawdown(equity_bps: np.ndarray) -> np.ndarray:
    eq = np.asarray(equity_bps, dtype=np.float64)
    peak = np.maximum.accumulate(eq)
    return eq - peak
