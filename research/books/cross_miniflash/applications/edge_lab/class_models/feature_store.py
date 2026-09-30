"""Feature store: panel_cache ⊕ event_panel → class-model rows.

Leakage: see LEAKAGE.md. Never put mo_5s / label / recovery_5s in FEATURE_COLS.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

LAB = Path(__file__).resolve().parents[1]
APP = LAB.parent
SCRIPTS = APP / "scripts"

for p in (str(SCRIPTS), str(APP), str(LAB)):
    if p not in sys.path:
        sys.path.insert(0, p)

from _common import assign_ladder_tiers, flatten_events  # noqa: E402

PANEL_CACHE = APP / "mm_quoting" / "out" / "panel_cache.json"
EVENT_PANEL_ROWS = APP / "out" / "event_panel" / "panel_rows.json"
NS = 1_000_000_000
SLACK_NS = NS

# Numeric continuous / binary features (no one-hots yet)
NUMERIC_FEATURES = [
    "dp_pct",
    "i_c",
    "z_peak",
    "dt_s",
    "vol_clock",
    "intensity",
    "intensity_60s",
    "day_intensity",
    "recovery_1s",
    "recovery_2s",
    "vpin_exante",
    "amihud",
    "rv_1m",
    "log_notional_pre",
    "log_notional_event",
    "H_v",
    "FEI",
    "thin_excess",
    "hour_utc",
    "nanex_overlap",  # 0/1
    "thin_venue",  # 0/1
]

VENUE_LEVELS = ["hyperliquid", "deribit", "kraken"]
SYMBOL_LEVELS = ["ETH", "BTC"]
TIER_LEVELS = ["observe", "widen", "size_cap", "halt"]

# Explicit forbid list (documented; stripped if present)
FORBIDDEN_FEATURES = frozenset(
    {
        "mo_5s",
        "mo_1s",
        "mo_0.5s",
        "label",
        "recovery_5s",
        "recovery",  # event_panel recovery@5s path
        "recovery_label",
        "mid_mo_5s",
        "mid_mo_1s",
        "mid_mo_0.5s",
        "mid_0.5s_bps",
        "mid_1.0s_bps",
        "mid_2.0s_bps",
        "mid_5.0s_bps",
        "mid_10.0s_bps",
        "tape_0.5s_bps",
        "tape_1.0s_bps",
        "tape_2.0s_bps",
        "tape_5.0s_bps",
        "tape_10.0s_bps",
        "y_v",
        "y_v_vs_cont",
    }
)


def _f(v: Any) -> float:
    if v is None:
        return float("nan")
    if isinstance(v, (bool, np.bool_)):
        return 1.0 if v else 0.0
    try:
        x = float(v)
        return x if np.isfinite(x) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def causal_class(e: dict[str, Any]) -> str:
    """No look-ahead: recovery@2s + soft 1s (matches edge_lab)."""
    r2 = e.get("recovery_2s")
    r1 = e.get("recovery_1s")
    if r2 is None or not np.isfinite(_f(r2)):
        return "unknown"
    r2 = float(r2)
    r1 = _f(r1)
    if r2 >= 0.5 and (not np.isfinite(r1) or r1 >= 0.35):
        return "v_recovery"
    if r2 < 0.2:
        return "continuation"
    return "partial"


def _join_event_panel(cache_events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = json.loads(EVENT_PANEL_ROWS.read_text())
    flat = flatten_events(rows)
    assign_ladder_tiers(flat)
    by_key: dict[tuple, dict] = {}
    for e in flat:
        key = (e["venue"], e["symbol"], e["day"], int(e["ts_end"]))
        by_key[key] = e

    n_exact = n_slack = n_miss = 0
    out: list[dict[str, Any]] = []
    for e in cache_events:
        row = dict(e)
        key = (e["venue"], e["symbol"], e["day"], int(e["ts_end"]))
        j = by_key.get(key)
        if j is None:
            t = int(e["ts_end"])
            for (v, s, d, t2), cand in by_key.items():
                if v == e["venue"] and s == e["symbol"] and d == e["day"] and abs(t2 - t) <= SLACK_NS:
                    j = cand
                    break
            if j is not None:
                n_slack += 1
            else:
                n_miss += 1
        else:
            n_exact += 1

        if j is not None:
            row["nanex_overlap"] = bool(j.get("nanex_overlap"))
            row["tier"] = j.get("tier", row.get("tier", "unknown"))
            row["intensity_60s"] = int(j.get("intensity_60s") or row.get("intensity_60s") or 1)
            row["FEI"] = j.get("FEI")
            row["thin_excess"] = j.get("thin_excess")
            row["thin_venue"] = bool(j.get("thin_venue"))
            if j.get("H_v") is not None:
                row["H_v"] = j["H_v"]
            if row.get("mo_5s") is None and j.get("mo_5s") is not None:
                row["mo_5s"] = j["mo_5s"]
            if row.get("mo_1s") is None and j.get("mo_1s") is not None:
                row["mo_1s"] = j["mo_1s"]
        else:
            row["nanex_overlap"] = bool(row.get("nanex_overlap") or False)
            row["tier"] = row.get("tier") or "unknown"
            row["intensity_60s"] = int(round(_f(row.get("intensity")) or 1)) if row.get("intensity") else 1
            row["FEI"] = row.get("FEI")
            row["thin_excess"] = row.get("thin_excess")
            row["thin_venue"] = bool(row.get("thin_venue") or False)

        row["causal"] = causal_class(row)
        lab = row.get("label") or "unknown"
        row["y_v"] = 1 if lab == "v_recovery" else 0
        # aux: only among V vs cont
        if lab in ("v_recovery", "continuation"):
            row["y_v_vs_cont"] = 1 if lab == "v_recovery" else 0
        else:
            row["y_v_vs_cont"] = None
        out.append(row)

    meta = {
        "n_cache": len(cache_events),
        "n_joined_exact": n_exact,
        "n_joined_slack": n_slack,
        "n_join_miss": n_miss,
        "panel_cache": str(PANEL_CACHE),
        "event_panel": str(EVENT_PANEL_ROWS),
    }
    return out, meta


def build_feature_store() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load panel_cache, join event_panel nest/FEI/tier, attach targets."""
    cache = json.loads(PANEL_CACHE.read_text())
    events, join_meta = _join_event_panel(list(cache["events"]))
    # chronological
    events = sorted(events, key=lambda e: (e["day"], int(e["ts_end"]), e["venue"], e["symbol"]))
    days = list(cache.get("days") or sorted({e["day"] for e in events}))
    meta = {
        **join_meta,
        "days": days,
        "symbols": cache.get("symbols"),
        "venues": cache.get("venues"),
        "gate": cache.get("gate"),
        "z_star": cache.get("z_star"),
        "n_events": len(events),
        "n_with_mo5": sum(1 for e in events if e.get("mo_5s") is not None and np.isfinite(_f(e["mo_5s"]))),
        "oracle_counts": {
            lab: sum(1 for e in events if e.get("label") == lab)
            for lab in ("v_recovery", "continuation", "partial")
        },
        "causal_counts": {
            lab: sum(1 for e in events if e.get("causal") == lab)
            for lab in ("v_recovery", "continuation", "partial", "unknown")
        },
        "numeric_features": list(NUMERIC_FEATURES),
        "venue_levels": list(VENUE_LEVELS),
        "symbol_levels": list(SYMBOL_LEVELS),
        "tier_levels": list(TIER_LEVELS),
        "forbidden_features": sorted(FORBIDDEN_FEATURES),
        "leakage_doc": str(Path(__file__).resolve().parent / "LEAKAGE.md"),
        "honesty": {
            "target": "y_v = 1{oracle label==v_recovery}",
            "not_mid_prediction": True,
            "mo_5s_is_outcome_only": True,
            "alpha_claim": False,
        },
    }
    return events, meta


def feature_matrix(
    events: list[dict[str, Any]],
    *,
    include_recovery: bool = True,
) -> tuple[np.ndarray, list[str], np.ndarray]:
    """Design matrix + column names + finite-row mask (before impute).

    One-hots: venue, symbol, tier. Drops forbidden cols defensively.
    """
    cols: list[str] = []
    blocks: list[np.ndarray] = []

    num_cols = list(NUMERIC_FEATURES)
    if not include_recovery:
        num_cols = [c for c in num_cols if not c.startswith("recovery_")]
    for c in num_cols:
        if c in FORBIDDEN_FEATURES:
            raise RuntimeError(f"forbidden feature slipped into NUMERIC: {c}")
        cols.append(c)
        blocks.append(np.asarray([_f(e.get(c)) for e in events], dtype=np.float64))

    for v in VENUE_LEVELS:
        cols.append(f"venue_{v}")
        blocks.append(np.asarray([1.0 if e.get("venue") == v else 0.0 for e in events], dtype=np.float64))
    for s in SYMBOL_LEVELS:
        cols.append(f"symbol_{s}")
        blocks.append(np.asarray([1.0 if e.get("symbol") == s else 0.0 for e in events], dtype=np.float64))
    for t in TIER_LEVELS:
        cols.append(f"tier_{t}")
        blocks.append(np.asarray([1.0 if e.get("tier") == t else 0.0 for e in events], dtype=np.float64))

    # leak check
    for c in cols:
        if c in FORBIDDEN_FEATURES:
            raise RuntimeError(f"forbidden column in design: {c}")

    X = np.column_stack(blocks) if blocks else np.zeros((len(events), 0))
    # row usable for classification if y finite; feature NaNs imputed later
    y = np.asarray([_f(e.get("y_v")) for e in events], dtype=np.float64)
    row_ok = np.isfinite(y)
    return X, cols, row_ok


def chrono_split_indices(
    events: list[dict[str, Any]],
    *,
    train_frac: float = 0.6,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Chronological train/test by sorted ts_end (already sorted in store)."""
    n = len(events)
    cut = int(round(train_frac * n))
    cut = max(20, min(n - 15, cut))
    tr = np.zeros(n, dtype=bool)
    te = np.zeros(n, dtype=bool)
    tr[:cut] = True
    te[cut:] = True
    days_tr = sorted({events[i]["day"] for i in range(n) if tr[i]})
    days_te = sorted({events[i]["day"] for i in range(n) if te[i]})
    info = {
        "n": n,
        "n_train": int(tr.sum()),
        "n_test": int(te.sum()),
        "train_frac": train_frac,
        "cut_index": cut,
        "days_train": days_tr,
        "days_test": days_te,
        "cut_day_hint": events[cut]["day"] if cut < n else None,
    }
    return tr, te, info


def impute_train_median(X_tr: np.ndarray, X_te: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    med = np.nanmedian(X_tr, axis=0)
    med = np.where(np.isfinite(med), med, 0.0)
    a, b = X_tr.copy(), X_te.copy()
    for j in range(a.shape[1]):
        a[np.isnan(a[:, j]), j] = med[j]
        b[np.isnan(b[:, j]), j] = med[j]
        # also any remaining non-finite
        a[~np.isfinite(a[:, j]), j] = med[j]
        b[~np.isfinite(b[:, j]), j] = med[j]
    return a, b, med


def save_store_jsonl(path: Path, events: list[dict[str, Any]], cols: list[str]) -> None:
    """Compact JSONL for inspection (features + targets + keys; mo_5s outcome tagged)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for e in events:
            rec = {
                "venue": e["venue"],
                "symbol": e["symbol"],
                "day": e["day"],
                "ts_end": int(e["ts_end"]),
                "label": e.get("label"),
                "causal": e.get("causal"),
                "y_v": e.get("y_v"),
                "y_v_vs_cont": e.get("y_v_vs_cont"),
                "mo_5s": e.get("mo_5s"),  # outcome only — not in FEATURE_COLS
                "features": {c: (None if not np.isfinite(_f(e.get(c))) else _f(e.get(c))) for c in NUMERIC_FEATURES},
                "tier": e.get("tier"),
                "nanex_overlap": bool(e.get("nanex_overlap")),
            }
            f.write(json.dumps(rec) + "\n")
