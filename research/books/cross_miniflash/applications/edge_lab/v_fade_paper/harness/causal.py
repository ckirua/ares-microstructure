"""Causal V/cont class + tape helpers (no look-ahead)."""

from __future__ import annotations

from typing import Any

import numpy as np

NS = 1_000_000_000


def causal_class(
    recovery_2s: float | None,
    recovery_1s: float | None = None,
    *,
    v_threshold_r2: float = 0.5,
    cont_threshold_r2: float = 0.2,
    soft_confirm_r1: float = 0.35,
) -> str:
    """Copy of exp_edge_lab.causal_class — recovery@2s only (1s soft)."""
    if recovery_2s is None or not np.isfinite(float(recovery_2s)):
        return "unknown"
    r2 = float(recovery_2s)
    r1 = (
        float(recovery_1s)
        if recovery_1s is not None and np.isfinite(float(recovery_1s))
        else float("nan")
    )
    if r2 >= v_threshold_r2 and (not np.isfinite(r1) or r1 >= soft_confirm_r1):
        return "v_recovery"
    if r2 < cont_threshold_r2:
        return "continuation"
    return "partial"


def asof_trade_px(ts: np.ndarray, px: np.ndarray, t_ns: int) -> float:
    """Last tape print at or before t_ns (paper honesty — not BBO)."""
    ts = np.asarray(ts, dtype=np.int64)
    px = np.asarray(px, dtype=np.float64)
    if ts.size == 0:
        return float("nan")
    j = int(np.searchsorted(ts, int(t_ns), side="right") - 1)
    if j < 0 or j >= px.size:
        return float("nan")
    p = float(px[j])
    return p if np.isfinite(p) and p > 0 else float("nan")


def asof_trade_idx(ts: np.ndarray, t_ns: int) -> int:
    ts = np.asarray(ts, dtype=np.int64)
    if ts.size == 0:
        return -1
    j = int(np.searchsorted(ts, int(t_ns), side="right") - 1)
    return j if 0 <= j < ts.size else -1


def jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        if obj.dtype == object:
            return [jsonable(x) for x in obj.tolist()]
        return obj.tolist()
    if isinstance(obj, (np.floating, float)):
        x = float(obj)
        return x if np.isfinite(x) else None
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if obj is None:
        return None
    return str(obj)


def write_jsonl(path, records: list[dict]) -> None:
    from pathlib import Path
    import json

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for rec in records:
            f.write(json.dumps(jsonable(rec), separators=(",", ":")) + "\n")


def append_jsonl(path, record: dict) -> None:
    from pathlib import Path
    import json

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(jsonable(record), separators=(",", ":")) + "\n")
