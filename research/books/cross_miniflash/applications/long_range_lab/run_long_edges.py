from __future__ import annotations
#!/usr/bin/env python3
"""Long-range NON-MM edges — crash/SSM/V-class over minutes–hours.

Distinct from ``edge_lab`` short-horizon (mo@5s) V-fade / cont-ride. This
package already owns MM risk overlays (``run_long_range.py``); here we push
**taker / event-hold** edges on the same long HL ETH panel:

  1. LR-v-slow-fade     — causal V@2s → fade, hold 1m–60m
  2. LR-cont-long-ride  — causal cont@2s → ride crash sign, hold 1m–60m
  3. LR-cluster-fade    — multi-event regime (≥K gated SSM in 5m) → fade
                          cluster anchor, hold 15m–60m (non-overlapping)

Honesty gates: bootstrap CI excludes 0 · early/late sign-stable · RT friction
(4 bps) cleared · min_n. Research sim on real tape — not live alpha.
ClickHouse MCP banned. No mm_confr.
"""

import os

import argparse
import json
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

LAB = Path(__file__).resolve().parent
APP = LAB.parent
BOOK = APP.parent
ROOT = BOOK.parents[2]
STARTARB = Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb'))
WAREHOUSE_SRC = Path(os.environ.get('WAREHOUSE_SRC') or ((Path(os.environ.get('WAREHOUSE_ROOT') or (Path.home() / 'lab' / 'lab-n2070' / 'warehouse')) / 'src')))
OUT = LAB / "out" / "long_edges"
FIG = OUT / "figs"
PAPER = APP / "paper_harness"
SCRIPTS_APP = APP / "scripts"

PIN_USABLE = [
    "2026-08-28",
    "2026-08-29",
    "2026-08-30",
    "2026-08-31",
    "2026-09-01",
    "2026-09-02",
    "2026-09-03",
    "2026-09-04",
    "2026-09-05",
    "2026-09-06",
    "2026-09-07",
    "2026-09-08",
    "2026-09-09",
    "2026-09-10",
    "2026-09-14",
    "2026-09-15",
    "2026-09-16",
    "2026-09-17",
    "2026-09-18",
    "2026-09-19",
    "2026-09-20",
    "2026-09-21",
    "2026-09-22",
    "2026-09-25",
    "2026-09-26",
    "2026-09-27",
    "2026-09-30",
]
PANEL_CORE = [
    "2026-09-04",
    "2026-09-05",
    "2026-09-06",
    "2026-09-07",
    "2026-09-08",
    "2026-09-09",
    "2026-09-10",
]

# Long holds (seconds). 5s included only as edge_lab sanity contrast — not a primary.
HOLD_S = (60.0, 300.0, 900.0, 1800.0, 3600.0)
HOLD_LABEL = {60.0: "1m", 300.0: "5m", 900.0: "15m", 1800.0: "30m", 3600.0: "60m"}
CLUSTER_WINDOW_S = 300.0  # 5-minute multi-event window
CLUSTER_K = 3
FIRE_TIERS = {"widen", "size_cap", "halt"}
NS = 1_000_000_000
FRICTION_ONE_WAY = 2.0
RT_FRICTION = 2.0 * FRICTION_ONE_WAY

for p in (
    str(LAB),
    str(PAPER),
    str(APP),
    str(SCRIPTS_APP),
    str(BOOK / "scripts"),
    str(ROOT),
    str(STARTARB / "src"),
    str(WAREHOUSE_SRC),
):
    if p not in sys.path:
        sys.path.insert(0, p)

from _common import (  # noqa: E402
    early_late_by_day,
    mean_ci,
    save_fig,
    save_json,
)
from harness.detect import detect_day  # noqa: E402
from ares_micro.vol.crash import classify_recovery, recovery_fraction  # noqa: E402

HONESTY = {
    "slice": "research_sim_on_real_tape_long_holds",
    "live_orders": False,
    "fills": "synthetic_unit_size_x_signed_tape_mo_at_hold",
    "alpha_claim": False,
    "costs_bps_one_way": FRICTION_ONE_WAY,
    "costs_bps_round_trip": RT_FRICTION,
    "capacity": "tape_mo_ceiling_no_queue",
    "clickhouse_mcp": False,
    "mm_confr": False,
    "vs_edge_lab": "edge_lab owns mo@5s V-fade; this lab owns minutes–hours + multi-event",
    "class": "non_mm_taker_event_hold",
}


def jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
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


def _boot_mean(arr: np.ndarray, *, seed: int = 0, n_boot: int = 800) -> dict[str, float]:
    a = np.asarray(arr, dtype=np.float64)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return {"n": 0, "mean": float("nan"), "lo": float("nan"), "hi": float("nan"), "sd": float("nan")}
    ci = mean_ci(a, n_boot=n_boot, seed=seed)
    return {
        "n": int(ci.get("n", a.size)),
        "mean": float(ci.get("point", np.nanmean(a))),
        "lo": float(ci.get("lo", float("nan"))),
        "hi": float(ci.get("hi", float("nan"))),
        "sd": float(np.std(a, ddof=1)) if a.size > 1 else 0.0,
    }


def _ci_excludes_zero(ci: dict[str, float]) -> bool:
    lo, hi = ci.get("lo"), ci.get("hi")
    if lo is None or hi is None or not np.isfinite(lo) or not np.isfinite(hi):
        return False
    return (lo > 0 and hi > 0) or (lo < 0 and hi < 0)


def _sign_stable(early_mean: float, late_mean: float) -> bool:
    if not np.isfinite(early_mean) or not np.isfinite(late_mean):
        return False
    if early_mean == 0 or late_mean == 0:
        return False
    return (early_mean > 0) == (late_mean > 0)


def _verdict(
    *,
    name: str,
    n: int,
    pnl_ci: dict[str, float],
    early_mean: float,
    late_mean: float,
    friction_cleared: bool,
    min_n: int = 30,
    promote_scope: str = "long_hold_research_edge",
) -> dict[str, Any]:
    excludes0 = _ci_excludes_zero(pnl_ci)
    stable = _sign_stable(early_mean, late_mean)
    mean = float(pnl_ci.get("mean", float("nan")))
    # Significant loss is an anti-edge even if slightly underpowered
    if excludes0 and np.isfinite(mean) and mean < 0:
        decision = "Kill"
        why = "significant net loss after costs (anti-edge)"
    elif n < min_n:
        decision = "Hold"
        why = f"underpowered n={n} < {min_n}"
    elif not excludes0:
        decision = "Kill" if (np.isfinite(mean) and mean <= 0) else "Hold"
        why = "net PnL CI includes 0 after costs" if decision == "Hold" else "mean net PnL ≤ 0 and CI includes 0"
    elif not stable:
        decision = "Kill"
        why = f"time-split sign flip early={early_mean:.2f} late={late_mean:.2f}"
    elif not friction_cleared:
        decision = "Hold"
        why = "CI excludes 0 but effect does not clear round-trip friction bar"
    else:
        decision = "Promote"
        why = f"net CI excludes 0, time-split stable, friction cleared ({promote_scope})"
    return {
        "id": name,
        "decision": decision,
        "why": why,
        "n": n,
        "pnl_ci_excludes_0": excludes0,
        "time_split_stable": stable,
        "friction_cleared": friction_cleared,
        "promote_scope": promote_scope if decision == "Promote" else None,
        "honesty": "not_live_alpha",
    }


def causal_class(r1: float, r2: float) -> str:
    """No look-ahead: recovery@2s (+ soft 1s). Same rule as edge_lab."""
    if not np.isfinite(r2):
        return "unknown"
    if r2 >= 0.5 and (not np.isfinite(r1) or r1 >= 0.35):
        return "v_recovery"
    if r2 < 0.2:
        return "continuation"
    return "partial"


def _per_event_markouts(
    ts: np.ndarray,
    px: np.ndarray,
    end_i: np.ndarray,
    direction: np.ndarray,
    horizons: tuple[float, ...],
) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    for h in horizons:
        h_ns = int(h * NS)
        arr = np.full(end_i.shape, np.nan, dtype=np.float64)
        for k in range(end_i.size):
            b = int(end_i[k])
            if b < 0 or b >= px.size or px[b] <= 0 or direction[k] == 0:
                continue
            j = int(np.searchsorted(ts, int(ts[b]) + h_ns, side="right") - 1)
            if j <= b or j >= px.size or not np.isfinite(px[j]):
                continue
            # crash-signed: + if price continued in crash direction
            arr[k] = float(direction[k] * (px[j] - px[b]) / px[b] * 1e4)
        out[str(h)] = arr
    return out


def _cluster_counts(ts_start: np.ndarray, *, window_s: float = CLUSTER_WINDOW_S) -> np.ndarray:
    t = np.asarray(ts_start, dtype=np.int64)
    w = int(window_s * NS)
    out = np.zeros(t.size, dtype=np.int64)
    for i in range(t.size):
        out[i] = int(np.sum((t <= t[i]) & (t > t[i] - w)))
    return out


def _end_indices(ts: np.ndarray, ts_end: np.ndarray) -> np.ndarray:
    return np.clip(np.searchsorted(ts, ts_end, side="left"), 0, max(ts.size - 1, 0)).astype(np.int64)


def process_day(payload: dict[str, Any]) -> dict[str, Any]:
    day = payload["day"]
    symbol = payload["symbol"]
    venue = payload["venue"]
    try:
        det = detect_day(venue, symbol, day, quiet=True)
        if det.get("skip"):
            return {
                "ok": False,
                "day": day,
                "symbol": symbol,
                "reason": det.get("skip"),
                "events": [],
            }
        if not det.get("complete", True) and det.get("n_trades", 0) < 500:
            return {
                "ok": False,
                "day": day,
                "symbol": symbol,
                "reason": "thin_incomplete",
                "events": [],
            }
        ts = np.asarray(det["ts"], dtype=np.int64)
        px = np.asarray(det["px"], dtype=np.float64)
        ev = det["events"]
        n = int(np.asarray(ev["ts_end"]).size)
        if n == 0:
            return {
                "ok": True,
                "day": day,
                "symbol": symbol,
                "n_trades": int(det.get("n_trades", 0)),
                "n_events": 0,
                "events": [],
            }

        ts_start = np.asarray(ev["ts_start"], dtype=np.int64)
        ts_end = np.asarray(ev["ts_end"], dtype=np.int64)
        direction = np.asarray(ev["direction"], dtype=np.int64)
        end_i = _end_indices(ts, ts_end)
        start_i = _end_indices(ts, ts_start)

        # Causal recovery (always recompute — don't trust recovery_label@5s)
        r1 = recovery_fraction(ts, px, start_i, end_i, direction, horizon_s=1.0)
        r2 = recovery_fraction(ts, px, start_i, end_i, direction, horizon_s=2.0)
        # Oracle label @5s for diagnostics only
        r5 = recovery_fraction(ts, px, start_i, end_i, direction, horizon_s=5.0)
        oracle = classify_recovery(r5)["labels"]

        mos = _per_event_markouts(ts, px, end_i, direction, (5.0,) + HOLD_S)
        cluster_n = _cluster_counts(ts_start, window_s=CLUSTER_WINDOW_S)
        intens = np.asarray(ev.get("intensity_60s", np.ones(n)), dtype=np.int64)
        tiers = np.asarray(ev.get("tier", ["observe"] * n), dtype=object)
        nanex = np.asarray(ev.get("nanex_overlap", np.zeros(n, dtype=bool)), dtype=bool)
        z_peak = np.asarray(ev.get("z_peak", np.full(n, np.nan)), dtype=np.float64)
        dp = np.asarray(ev.get("dp_pct", np.full(n, np.nan)), dtype=np.float64)

        rows: list[dict[str, Any]] = []
        for i in range(n):
            causal = causal_class(float(r1[i]), float(r2[i]))
            row: dict[str, Any] = {
                "day": day,
                "symbol": symbol,
                "venue": venue,
                "i": i,
                "ts_start": int(ts_start[i]),
                "ts_end": int(ts_end[i]),
                "direction": int(direction[i]),
                "causal": causal,
                "oracle": str(oracle[i]),
                "recovery_1s": float(r1[i]) if np.isfinite(r1[i]) else None,
                "recovery_2s": float(r2[i]) if np.isfinite(r2[i]) else None,
                "cluster_n_5m": int(cluster_n[i]),
                "in_cluster": bool(cluster_n[i] >= CLUSTER_K),
                "intensity_60s": int(intens[i]),
                "tier": str(tiers[i]),
                "fire": str(tiers[i]) in FIRE_TIERS,
                "nanex_overlap": bool(nanex[i]),
                "z_peak": float(z_peak[i]) if np.isfinite(z_peak[i]) else None,
                "dp_pct": float(dp[i]) if np.isfinite(dp[i]) else None,
                "mo_5s": float(mos["5.0"][i]) if np.isfinite(mos["5.0"][i]) else None,
            }
            for h in HOLD_S:
                key = f"mo_{HOLD_LABEL[h]}"
                v = mos[str(h)][i]
                row[key] = float(v) if np.isfinite(v) else None
            rows.append(row)

        # Mark cluster anchors = last event in a contiguous cluster run
        # (or every event with cluster_n>=K that is a local max of the count wave)
        for i, row in enumerate(rows):
            is_anchor = False
            if row["in_cluster"]:
                # local peak or last in day-window: next event not also in same cluster wave
                next_in = i + 1 < n and rows[i + 1]["in_cluster"] and (
                    rows[i + 1]["ts_start"] - row["ts_start"]
                ) <= int(CLUSTER_WINDOW_S * NS)
                is_anchor = not next_in
            row["cluster_anchor"] = bool(is_anchor)

        return {
            "ok": True,
            "day": day,
            "symbol": symbol,
            "n_trades": int(det.get("n_trades", 0)),
            "n_events": n,
            "n_cluster_anchors": int(sum(1 for r in rows if r["cluster_anchor"])),
            "n_causal_v": int(sum(1 for r in rows if r["causal"] == "v_recovery")),
            "n_causal_cont": int(sum(1 for r in rows if r["causal"] == "continuation")),
            "events": rows,
        }
    except Exception as exc:  # noqa: BLE001 — collect per-day failures
        return {
            "ok": False,
            "day": day,
            "symbol": symbol,
            "reason": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc()[-1500:],
            "events": [],
        }


def _score_rule(
    trades: list[dict[str, Any]],
    *,
    name: str,
    early: set[str],
    late: set[str],
    hold_key: str,
    min_n: int = 30,
    promote_scope: str = "long_hold_research_edge",
) -> dict[str, Any]:
    """trades already have size (+1 ride / −1 fade) and mo at hold."""
    if not trades:
        empty = {"n": 0, "mean": float("nan"), "lo": float("nan"), "hi": float("nan"), "sd": float("nan")}
        return {
            "id": name,
            "n_traded": 0,
            "hold": hold_key,
            "pnl_net_bps": empty,
            "gross_bps": empty,
            "early_mean": float("nan"),
            "late_mean": float("nan"),
            "hit_rate": float("nan"),
            "verdict": _verdict(
                name=name,
                n=0,
                pnl_ci=empty,
                early_mean=float("nan"),
                late_mean=float("nan"),
                friction_cleared=False,
                min_n=min_n,
                promote_scope=promote_scope,
            ),
        }

    pnls = []
    gross = []
    e_pnls = []
    l_pnls = []
    for t in trades:
        mo = t.get(hold_key)
        size = float(t["size"])
        if mo is None or not np.isfinite(float(mo)) or size == 0:
            continue
        mo = float(mo)
        g = size * mo
        net = g - abs(size) * RT_FRICTION
        pnls.append(net)
        gross.append(g)
        if t["day"] in early:
            e_pnls.append(net)
        elif t["day"] in late:
            l_pnls.append(net)

    pnls_a = np.asarray(pnls, dtype=np.float64)
    gross_a = np.asarray(gross, dtype=np.float64)
    ci = _boot_mean(pnls_a, seed=17 + abs(hash(name)) % 200)
    gci = _boot_mean(gross_a, seed=19 + abs(hash(name)) % 200)
    early_m = float(np.nanmean(e_pnls)) if e_pnls else float("nan")
    late_m = float(np.nanmean(l_pnls)) if l_pnls else float("nan")
    friction_cleared = bool(
        _ci_excludes_zero(ci)
        and ci["mean"] > 0
        and np.isfinite(gci["mean"])
        and gci["mean"] > RT_FRICTION
    )
    verd = _verdict(
        name=name,
        n=int(pnls_a.size),
        pnl_ci=ci,
        early_mean=early_m,
        late_mean=late_m,
        friction_cleared=friction_cleared,
        min_n=min_n,
        promote_scope=promote_scope,
    )
    return {
        "id": name,
        "n_traded": int(pnls_a.size),
        "hold": hold_key,
        "pnl_net_bps": ci,
        "gross_bps": gci,
        "early_mean": early_m,
        "late_mean": late_m,
        "hit_rate": float(np.mean(pnls_a > 0)) if pnls_a.size else float("nan"),
        "verdict": verd,
    }


def _nonoverlap_filter(cands: list[dict[str, Any]], *, hold_s: float) -> list[dict[str, Any]]:
    """Keep trades whose entry is after prior hold expires (multi-event honesty)."""
    hold_ns = int(hold_s * NS)
    kept: list[dict[str, Any]] = []
    free_at = -1
    for t in sorted(cands, key=lambda x: (x["day"], x["ts_end"])):
        if t["ts_end"] < free_at:
            continue
        kept.append(t)
        free_at = int(t["ts_end"]) + hold_ns
    return kept


def build_edges(events: list[dict[str, Any]], early: set[str], late: set[str]) -> dict[str, Any]:
    """Score LR-v-slow-fade, LR-cont-long-ride, LR-cluster-fade across holds."""
    lenses: dict[str, Any] = {}

    # --- 1) Slow V-fade ---
    v_by_hold: dict[str, Any] = {}
    for h in HOLD_S:
        hold_key = f"mo_{HOLD_LABEL[h]}"
        cands = [
            {**e, "size": -1.0}
            for e in events
            if e["causal"] == "v_recovery" and e.get(hold_key) is not None
        ]
        # Non-overlap within day for long holds
        cands = _nonoverlap_filter(cands, hold_s=h)
        scored = _score_rule(
            cands,
            name=f"LR-v-slow-fade@{HOLD_LABEL[h]}",
            early=early,
            late=late,
            hold_key=hold_key,
            min_n=25,
            promote_scope="causal_v_long_hold_fade",
        )
        v_by_hold[HOLD_LABEL[h]] = scored

    # pick best hold by mean net among those with n>=25 (for headline); verdict honest
    best_v = max(
        v_by_hold.values(),
        key=lambda s: (
            s["verdict"]["decision"] == "Promote",
            s["pnl_net_bps"]["mean"] if np.isfinite(s["pnl_net_bps"]["mean"]) else -1e18,
        ),
    )
    # class diagnostics: oracle vs causal mean mo at 15m
    def _class_mo(lab_key: str, lab_val: str, hold_key: str) -> dict[str, float]:
        mos = np.asarray(
            [
                float(e[hold_key])
                for e in events
                if e.get(lab_key) == lab_val and e.get(hold_key) is not None
            ],
            dtype=np.float64,
        )
        return _boot_mean(mos[np.isfinite(mos)], seed=31 + abs(hash(lab_val + hold_key)) % 50)

    lenses["LR-v-slow-fade"] = {
        "id": "LR-v-slow-fade",
        "hypothesis": (
            "Causal V@2s rebound continues over minutes–hours — fade crash sign, "
            "hold 1m–60m (NOT edge_lab mo@5s)"
        ),
        "by_hold": v_by_hold,
        "primary": best_v,
        "primary_verdict": best_v["verdict"],
        "class_mo_15m_causal": {
            "v_recovery": _class_mo("causal", "v_recovery", "mo_15m"),
            "continuation": _class_mo("causal", "continuation", "mo_15m"),
            "partial": _class_mo("causal", "partial", "mo_15m"),
        },
        "class_mo_15m_oracle": {
            "v_recovery": _class_mo("oracle", "v_recovery", "mo_15m"),
            "continuation": _class_mo("oracle", "continuation", "mo_15m"),
            "partial": _class_mo("oracle", "partial", "mo_15m"),
        },
        "n_causal_v": int(sum(1 for e in events if e["causal"] == "v_recovery")),
        "edge_lab_contrast_mo5s_fade": _score_rule(
            [
                {**e, "size": -1.0}
                for e in events
                if e["causal"] == "v_recovery" and e.get("mo_5s") is not None
            ],
            name="edge_lab_contrast:causal_v_fade@5s",
            early=early,
            late=late,
            hold_key="mo_5s",
            min_n=25,
            promote_scope="sanity_contrast_only",
        ),
    }

    # --- 2) Cont long-ride ---
    c_by_hold: dict[str, Any] = {}
    for h in HOLD_S:
        hold_key = f"mo_{HOLD_LABEL[h]}"
        cands = [
            {**e, "size": 1.0}
            for e in events
            if e["causal"] == "continuation" and e.get(hold_key) is not None
        ]
        cands = _nonoverlap_filter(cands, hold_s=h)
        c_by_hold[HOLD_LABEL[h]] = _score_rule(
            cands,
            name=f"LR-cont-long-ride@{HOLD_LABEL[h]}",
            early=early,
            late=late,
            hold_key=hold_key,
            min_n=20,
            promote_scope="causal_cont_long_hold_ride",
        )
    best_c = max(
        c_by_hold.values(),
        key=lambda s: (
            s["verdict"]["decision"] == "Promote",
            s["pnl_net_bps"]["mean"] if np.isfinite(s["pnl_net_bps"]["mean"]) else -1e18,
        ),
    )
    lenses["LR-cont-long-ride"] = {
        "id": "LR-cont-long-ride",
        "hypothesis": (
            "Causal continuation@2s = news assimilation — ride crash sign over minutes–hours "
            "(edge_lab killed @5s; re-test longer)"
        ),
        "by_hold": c_by_hold,
        "primary": best_c,
        "primary_verdict": best_c["verdict"],
        "n_causal_cont": int(sum(1 for e in events if e["causal"] == "continuation")),
        "edge_lab_contrast_mo5s_ride": _score_rule(
            [
                {**e, "size": 1.0}
                for e in events
                if e["causal"] == "continuation" and e.get("mo_5s") is not None
            ],
            name="edge_lab_contrast:causal_cont_ride@5s",
            early=early,
            late=late,
            hold_key="mo_5s",
            min_n=20,
            promote_scope="sanity_contrast_only",
        ),
    }

    # --- 3) Multi-event cluster fade ---
    cl_by_hold: dict[str, Any] = {}
    anchors = [e for e in events if e.get("cluster_anchor")]
    for h in (900.0, 1800.0, 3600.0):  # 15m–60m only — this is the multi-event lens
        hold_key = f"mo_{HOLD_LABEL[h]}"
        cands = [{**e, "size": -1.0} for e in anchors if e.get(hold_key) is not None]
        cands = _nonoverlap_filter(cands, hold_s=h)
        cl_by_hold[HOLD_LABEL[h]] = _score_rule(
            cands,
            name=f"LR-cluster-fade@{HOLD_LABEL[h]}",
            early=early,
            late=late,
            hold_key=hold_key,
            min_n=20,
            promote_scope="multi_event_cluster_fade",
        )

    # Isolated-event control: fade non-cluster at same holds
    iso_by_hold: dict[str, Any] = {}
    isolated = [e for e in events if not e.get("in_cluster")]
    for h in (900.0, 1800.0, 3600.0):
        hold_key = f"mo_{HOLD_LABEL[h]}"
        cands = [{**e, "size": -1.0} for e in isolated if e.get(hold_key) is not None]
        cands = _nonoverlap_filter(cands, hold_s=h)
        iso_by_hold[HOLD_LABEL[h]] = _score_rule(
            cands,
            name=f"LR-isolated-fade@{HOLD_LABEL[h]}",
            early=early,
            late=late,
            hold_key=hold_key,
            min_n=20,
            promote_scope="isolated_control_fade",
        )

    best_cl = max(
        cl_by_hold.values(),
        key=lambda s: (
            s["verdict"]["decision"] == "Promote",
            s["pnl_net_bps"]["mean"] if np.isfinite(s["pnl_net_bps"]["mean"]) else -1e18,
        ),
    )

    # Cluster ride = anti-fade (fade@15m was significant loss → test ride)
    cr_by_hold: dict[str, Any] = {}
    for h in (900.0, 1800.0, 3600.0):
        hold_key = f"mo_{HOLD_LABEL[h]}"
        cands = [{**e, "size": 1.0} for e in anchors if e.get(hold_key) is not None]
        cands = _nonoverlap_filter(cands, hold_s=h)
        cr_by_hold[HOLD_LABEL[h]] = _score_rule(
            cands,
            name=f"LR-cluster-ride@{HOLD_LABEL[h]}",
            early=early,
            late=late,
            hold_key=hold_key,
            min_n=20,  # cascade anchors are rare — do not Promote on n≈12
            promote_scope="multi_event_cluster_ride",
        )
    best_cr = max(
        cr_by_hold.values(),
        key=lambda s: (
            s["verdict"]["decision"] == "Promote",
            s["pnl_net_bps"]["mean"] if np.isfinite(s["pnl_net_bps"]["mean"]) else -1e18,
        ),
    )

    lenses["LR-cluster-fade"] = {
        "id": "LR-cluster-fade",
        "hypothesis": (
            f"Multi-event regime: ≥{CLUSTER_K} gated SSM in {CLUSTER_WINDOW_S:.0f}s → "
            "fade cluster anchor, hold 15–60m (non-overlapping)"
        ),
        "cluster_window_s": CLUSTER_WINDOW_S,
        "cluster_k": CLUSTER_K,
        "n_anchors": len(anchors),
        "n_isolated": len(isolated),
        "by_hold": cl_by_hold,
        "isolated_control_by_hold": iso_by_hold,
        "primary": best_cl,
        "primary_verdict": best_cl["verdict"],
        "anti_edge_note": (
            "If fade shows significant loss, see LR-cluster-ride (ride crash after cascade)"
        ),
    }

    lenses["LR-cluster-ride"] = {
        "id": "LR-cluster-ride",
        "hypothesis": (
            f"After multi-event cascade (≥{CLUSTER_K} in {CLUSTER_WINDOW_S:.0f}s), "
            "ride crash sign from cluster anchor 15–60m (anti-fade)"
        ),
        "n_anchors": len(anchors),
        "by_hold": cr_by_hold,
        "primary": best_cr,
        "primary_verdict": best_cr["verdict"],
    }

    # --- 4) Fire-tier long pause @15m (risk gate, edge_lab int-halt analogue at long H) ---
    from _common import effect_delta_ci  # noqa: WPS433

    fire_pause_by_hold: dict[str, Any] = {}
    for h_lab in ("5m", "15m", "30m"):
        hold_key = f"mo_{h_lab}"
        fire = [e for e in events if e.get("fire") and e.get(hold_key) is not None]
        obs = [e for e in events if (not e.get("fire")) and e.get(hold_key) is not None]
        abs_f = np.asarray([abs(float(e[hold_key])) for e in fire], dtype=np.float64)
        abs_o = np.asarray([abs(float(e[hold_key])) for e in obs], dtype=np.float64)
        d_abs = (
            effect_delta_ci(abs_f, abs_o, seed=55 + abs(hash(h_lab)) % 20)
            if abs_f.size and abs_o.size
            else {
                "delta": float("nan"),
                "lo": float("nan"),
                "hi": float("nan"),
                "n_treat": 0,
                "n_control": 0,
            }
        )
        # early/late Δ|mo|
        early_f = np.asarray(
            [abs(float(e[hold_key])) for e in fire if e["day"] in early], dtype=np.float64
        )
        early_o = np.asarray(
            [abs(float(e[hold_key])) for e in obs if e["day"] in early], dtype=np.float64
        )
        late_f = np.asarray(
            [abs(float(e[hold_key])) for e in fire if e["day"] in late], dtype=np.float64
        )
        late_o = np.asarray(
            [abs(float(e[hold_key])) for e in obs if e["day"] in late], dtype=np.float64
        )
        e_d = (
            float(np.nanmean(early_f) - np.nanmean(early_o))
            if early_f.size and early_o.size
            else float("nan")
        )
        l_d = (
            float(np.nanmean(late_f) - np.nanmean(late_o))
            if late_f.size and late_o.size
            else float("nan")
        )
        # risk gate: Δ|mo| > 0 means fire is more adverse → pause saves
        delta_ci = {
            "n": int(d_abs.get("n_treat", 0)),
            "mean": float(d_abs.get("delta", float("nan"))),
            "lo": float(d_abs.get("lo", float("nan"))),
            "hi": float(d_abs.get("hi", float("nan"))),
            "sd": float("nan"),
        }
        friction_cleared = bool(
            _ci_excludes_zero(delta_ci)
            and delta_ci["mean"] > FRICTION_ONE_WAY
        )
        verd = _verdict(
            name=f"LR-fire-pause@{h_lab}",
            n=len(fire),
            pnl_ci=delta_ci,
            early_mean=e_d,
            late_mean=l_d,
            friction_cleared=friction_cleared,
            min_n=40,
            promote_scope="long_horizon_intensity_pause",
        )
        fire_pause_by_hold[h_lab] = {
            "hold": h_lab,
            "n_fire": len(fire),
            "n_observe": len(obs),
            "abs_mo_fire": _boot_mean(abs_f, seed=81),
            "abs_mo_observe": _boot_mean(abs_o, seed=82),
            "delta_abs_mo_fire_minus_obs": d_abs,
            "early_delta": e_d,
            "late_delta": l_d,
            "pnl_net_bps": delta_ci,  # here = Δ|mo| saved by pausing
            "n_traded": len(fire),
            "verdict": verd,
        }

    best_fp = max(
        fire_pause_by_hold.values(),
        key=lambda s: (
            s["verdict"]["decision"] == "Promote",
            s["pnl_net_bps"]["mean"] if np.isfinite(s["pnl_net_bps"]["mean"]) else -1e18,
        ),
    )
    lenses["LR-fire-pause"] = {
        "id": "LR-fire-pause",
        "hypothesis": (
            "Ladder fire (widen+) → pause aggressor; long-horizon |mo| on fire ≫ observe "
            "(edge_lab TI-int-halt analogue at 5–30m)"
        ),
        "by_hold": fire_pause_by_hold,
        "primary": best_fp,
        "primary_verdict": best_fp["verdict"],
        "note": "risk_policy — Δ|mo| is avoided adverse tape, not naked taker PnL",
    }

    # --- 5) Unconditional SSM drift ride @15m (class-agnostic long hold) ---
    drift_by_hold: dict[str, Any] = {}
    for h in (300.0, 900.0, 1800.0):
        hold_key = f"mo_{HOLD_LABEL[h]}"
        cands = [{**e, "size": 1.0} for e in events if e.get(hold_key) is not None]
        cands = _nonoverlap_filter(cands, hold_s=h)
        drift_by_hold[HOLD_LABEL[h]] = _score_rule(
            cands,
            name=f"LR-ssm-drift-ride@{HOLD_LABEL[h]}",
            early=early,
            late=late,
            hold_key=hold_key,
            min_n=40,
            promote_scope="gated_ssm_long_drift_ride",
        )
    best_dr = max(
        drift_by_hold.values(),
        key=lambda s: (
            s["verdict"]["decision"] == "Promote",
            s["pnl_net_bps"]["mean"] if np.isfinite(s["pnl_net_bps"]["mean"]) else -1e18,
        ),
    )
    lenses["LR-ssm-drift-ride"] = {
        "id": "LR-ssm-drift-ride",
        "hypothesis": (
            "After any gated SSM, ride crash sign for 5–30m "
            "(class mo@15m positive for both V and cont — short V rebound does not persist)"
        ),
        "by_hold": drift_by_hold,
        "primary": best_dr,
        "primary_verdict": best_dr["verdict"],
    }

    return lenses


def make_figs(lenses: dict[str, Any], day_equity: dict[str, Any] | None = None) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    verd_color = {"Promote": "#2a7a4b", "Hold": "#c4a35a", "Kill": "#a33b2b"}

    # 1) V-slow-fade net by hold
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    holds = list(HOLD_LABEL[h] for h in HOLD_S)
    block = lenses["LR-v-slow-fade"]["by_hold"]
    means = [block[h]["pnl_net_bps"]["mean"] for h in holds]
    los = [block[h]["pnl_net_bps"]["mean"] - block[h]["pnl_net_bps"]["lo"] for h in holds]
    his = [block[h]["pnl_net_bps"]["hi"] - block[h]["pnl_net_bps"]["mean"] for h in holds]
    colors = [verd_color.get(block[h]["verdict"]["decision"], "#888") for h in holds]
    x = np.arange(len(holds))
    ax.bar(x, means, yerr=[los, his], capsize=3, color=colors)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{h}\nn={block[h]['n_traded']}" for h in holds])
    ax.set_ylabel("net PnL after RT (bps / trade)")
    ax.set_title("LR-v-slow-fade — causal V fade by hold")
    p = FIG / "fig_v_slow_fade_by_hold.png"
    save_fig(p)
    paths.append(str(p))

    # 2) Cont long-ride by hold
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    block = lenses["LR-cont-long-ride"]["by_hold"]
    means = [block[h]["pnl_net_bps"]["mean"] for h in holds]
    los = [block[h]["pnl_net_bps"]["mean"] - block[h]["pnl_net_bps"]["lo"] for h in holds]
    his = [block[h]["pnl_net_bps"]["hi"] - block[h]["pnl_net_bps"]["mean"] for h in holds]
    colors = [verd_color.get(block[h]["verdict"]["decision"], "#888") for h in holds]
    ax.bar(x, means, yerr=[los, his], capsize=3, color=colors)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{h}\nn={block[h]['n_traded']}" for h in holds])
    ax.set_ylabel("net PnL after RT (bps / trade)")
    ax.set_title("LR-cont-long-ride — causal cont ride by hold")
    p = FIG / "fig_cont_long_ride_by_hold.png"
    save_fig(p)
    paths.append(str(p))

    # 3) Cluster fade vs ride @15/30/60m
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    holds_cl = ["15m", "30m", "60m"]
    cl = lenses["LR-cluster-fade"]["by_hold"]
    cr = lenses["LR-cluster-ride"]["by_hold"]
    x = np.arange(len(holds_cl))
    w = 0.35
    m_cl = [cl[h]["pnl_net_bps"]["mean"] for h in holds_cl]
    m_cr = [cr[h]["pnl_net_bps"]["mean"] for h in holds_cl]
    ax.bar(x - w / 2, m_cl, w, label="cluster fade", color="#8b3a4a")
    ax.bar(x + w / 2, m_cr, w, label="cluster ride (anti)", color="#2a7a4b")
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(holds_cl)
    ax.set_ylabel("net PnL after RT (bps)")
    ax.set_title("LR-cluster-fade vs LR-cluster-ride")
    ax.legend(fontsize=8)
    p = FIG / "fig_cluster_fade_vs_ride.png"
    save_fig(p)
    paths.append(str(p))

    # 4) Class mo @15m (causal)
    fig, ax = plt.subplots(figsize=(6.8, 4.0))
    labs = ["v_recovery", "continuation", "partial"]
    cm = lenses["LR-v-slow-fade"]["class_mo_15m_causal"]
    means = [cm[l]["mean"] for l in labs]
    los = [cm[l]["mean"] - cm[l]["lo"] if np.isfinite(cm[l]["lo"]) else 0 for l in labs]
    his = [cm[l]["hi"] - cm[l]["mean"] if np.isfinite(cm[l]["hi"]) else 0 for l in labs]
    ns = [cm[l]["n"] for l in labs]
    x = np.arange(len(labs))
    ax.bar(x, means, yerr=[los, his], capsize=4, color=["#3d7a6a", "#b85c38", "#888888"])
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{l}\nn={n}" for l, n in zip(labs, ns)])
    ax.set_ylabel("mo@15m (bps, crash-signed)")
    ax.set_title("Causal class markout @15m (long-range panel)")
    p = FIG / "fig_class_mo_15m.png"
    save_fig(p)
    paths.append(str(p))

    # 5) Fire-pause Δ|mo|
    fig, ax = plt.subplots(figsize=(6.8, 4.0))
    fp = lenses["LR-fire-pause"]["by_hold"]
    holds_fp = ["5m", "15m", "30m"]
    deltas = [fp[h]["pnl_net_bps"]["mean"] for h in holds_fp]
    los = [fp[h]["pnl_net_bps"]["mean"] - fp[h]["pnl_net_bps"]["lo"] for h in holds_fp]
    his = [fp[h]["pnl_net_bps"]["hi"] - fp[h]["pnl_net_bps"]["mean"] for h in holds_fp]
    colors = [verd_color.get(fp[h]["verdict"]["decision"], "#888") for h in holds_fp]
    x = np.arange(len(holds_fp))
    ax.bar(x, deltas, yerr=[los, his], capsize=3, color=colors)
    ax.axhline(FRICTION_ONE_WAY, color="#888", ls="--", lw=0.8, label=f"friction {FRICTION_ONE_WAY}bps")
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{h}\nn_fire={fp[h]['n_fire']}" for h in holds_fp])
    ax.set_ylabel("Δ|mo| fire − observe (bps)")
    ax.set_title("LR-fire-pause — long-horizon intensity gate")
    ax.legend(fontsize=8)
    p = FIG / "fig_fire_pause_delta_mo.png"
    save_fig(p)
    paths.append(str(p))

    # 6) SSM drift ride
    fig, ax = plt.subplots(figsize=(6.5, 4.0))
    dr = lenses["LR-ssm-drift-ride"]["by_hold"]
    holds_dr = ["5m", "15m", "30m"]
    means = [dr[h]["pnl_net_bps"]["mean"] for h in holds_dr]
    los = [dr[h]["pnl_net_bps"]["mean"] - dr[h]["pnl_net_bps"]["lo"] for h in holds_dr]
    his = [dr[h]["pnl_net_bps"]["hi"] - dr[h]["pnl_net_bps"]["mean"] for h in holds_dr]
    colors = [verd_color.get(dr[h]["verdict"]["decision"], "#888") for h in holds_dr]
    x = np.arange(len(holds_dr))
    ax.bar(x, means, yerr=[los, his], capsize=3, color=colors)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{h}\nn={dr[h]['n_traded']}" for h in holds_dr])
    ax.set_ylabel("net PnL after RT (bps)")
    ax.set_title("LR-ssm-drift-ride — ride all gated SSM")
    p = FIG / "fig_ssm_drift_ride.png"
    save_fig(p)
    paths.append(str(p))

    # 7) Scoreboard
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    items = [
        ("LR-v-slow-fade", lenses["LR-v-slow-fade"]["primary_verdict"], lenses["LR-v-slow-fade"]["primary"]),
        ("LR-cont-long-ride", lenses["LR-cont-long-ride"]["primary_verdict"], lenses["LR-cont-long-ride"]["primary"]),
        ("LR-cluster-fade", lenses["LR-cluster-fade"]["primary_verdict"], lenses["LR-cluster-fade"]["primary"]),
        ("LR-cluster-ride", lenses["LR-cluster-ride"]["primary_verdict"], lenses["LR-cluster-ride"]["primary"]),
        ("LR-fire-pause", lenses["LR-fire-pause"]["primary_verdict"], lenses["LR-fire-pause"]["primary"]),
        ("LR-ssm-drift-ride", lenses["LR-ssm-drift-ride"]["primary_verdict"], lenses["LR-ssm-drift-ride"]["primary"]),
    ]
    y = np.arange(len(items))
    colors = [verd_color[v["decision"]] for _, v, _ in items]
    ax.barh(y, [1] * len(items), color=colors)
    ax.set_yticks(y)
    labels = []
    for n, v, prim in items:
        hold = str(prim.get("hold", "?")).replace("mo_", "")
        m = prim["pnl_net_bps"]["mean"]
        labels.append(
            f"{n}@{hold} → {v['decision']} ({m:+.1f})" if np.isfinite(m) else f"{n} → {v['decision']}"
        )
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xticks([])
    ax.set_xlim(0, 1.15)
    ax.set_title("Long-range non-MM scoreboard (after costs · time-split)")
    p = FIG / "fig_scoreboard_long_edges.png"
    save_fig(p)
    paths.append(str(p))

    # 8) Early/late for primary drift or cont
    fig, ax = plt.subplots(figsize=(5.8, 3.6))
    prim = lenses["LR-ssm-drift-ride"]["primary"]
    ax.bar(["early", "late"], [prim["early_mean"], prim["late_mean"]], color=["#5b7c99", "#9c6b4a"])
    ax.axhline(0, color="k", lw=0.8)
    ax.set_ylabel("net PnL (bps)")
    ax.set_title(f"{prim['id']} — early/late")
    p = FIG / "fig_drift_early_late.png"
    save_fig(p)
    paths.append(str(p))

    # 9) Optional cumulative day equity
    if day_equity and day_equity.get("days"):
        fig, ax = plt.subplots(figsize=(8.0, 4.0))
        days = day_equity["days"]
        cum = np.cumsum(day_equity["daily_pnl_bps"])
        ax.plot(days, cum, color="#2a5a4a", lw=1.6)
        ax.axhline(0, color="k", lw=0.7)
        ax.set_ylabel("cumulative net bps (unit size)")
        ax.set_title(day_equity.get("title", "Cumulative long-hold edge"))
        ax.tick_params(axis="x", labelrotation=60, labelsize=7)
        p = FIG / "fig_cum_equity_primary.png"
        save_fig(p)
        paths.append(str(p))

    return paths


def write_report(summary: dict[str, Any], fig_paths: list[str]) -> Path:
    v = summary["lenses"]["LR-v-slow-fade"]
    c = summary["lenses"]["LR-cont-long-ride"]
    cl = summary["lenses"]["LR-cluster-fade"]
    cr = summary["lenses"]["LR-cluster-ride"]
    fp = summary["lenses"]["LR-fire-pause"]
    dr = summary["lenses"]["LR-ssm-drift-ride"]
    lines = [
        "# Long-range non-MM edges — EXP_REPORT",
        "",
        f"Generated: {summary['generated_at']}",
        f"Panel: {summary['meta']['n_days_ok']} days · {summary['meta']['n_events']} gated SSM events · "
        f"venue={summary['meta']['venue']} · symbols={summary['meta']['symbols']}",
        f"Honesty: `{HONESTY['slice']}` · RT friction={RT_FRICTION} bps · live_orders=False · alpha_claim=False",
        f"Scope: **minutes–hours** holds + multi-event regimes — **not** edge_lab mo@5s V-fade duplicate.",
        f"MM overlays remain in `run_long_range.py` / `long_range_strategies.ipynb` (unchanged).",
        "",
        "## Scoreboard",
        "",
        "| id | best hold | decision | net / Δ|mo| | why |",
        "|----|-----------|----------|-------------|-----|",
    ]

    def _row(ide: str, prim: dict, *, unit: str = "net") -> str:
        verd = prim["verdict"]
        ci = prim["pnl_net_bps"]
        hold = str(prim.get("hold", "?")).replace("mo_", "")
        return (
            f"| **{ide}** | {hold} | **{verd['decision']}** | "
            f"{unit} {ci['mean']:.2f} [{ci['lo']:.2f},{ci['hi']:.2f}] n={prim['n_traded']} | {verd['why']} |"
        )

    lines.append(_row("LR-v-slow-fade", v["primary"]))
    lines.append(_row("LR-cont-long-ride", c["primary"]))
    lines.append(_row("LR-cluster-fade", cl["primary"]))
    lines.append(_row("LR-cluster-ride", cr["primary"]))
    lines.append(_row("LR-fire-pause", fp["primary"], unit="Δ|mo|"))
    lines.append(_row("LR-ssm-drift-ride", dr["primary"]))

    lines += [
        "",
        "## 1. LR-v-slow-fade",
        "",
        v["hypothesis"],
        f"- n_causal_v={v['n_causal_v']}",
        f"- Causal class mo@15m: V={v['class_mo_15m_causal']['v_recovery']['mean']:.2f} · "
        f"cont={v['class_mo_15m_causal']['continuation']['mean']:.2f} · "
        f"partial={v['class_mo_15m_causal']['partial']['mean']:.2f}",
        f"- Primary: **{v['primary_verdict']['decision']}** — {v['primary_verdict']['why']}",
        f"- edge_lab contrast (same causal V, hold@5s): "
        f"net={v['edge_lab_contrast_mo5s_fade']['pnl_net_bps']['mean']:.2f} "
        f"→ {v['edge_lab_contrast_mo5s_fade']['verdict']['decision']} (sanity only)",
        "",
        "| hold | n | mean | lo | hi | early | late | decision |",
        "|------|---|------|----|----|-------|------|----------|",
    ]
    for h, b in v["by_hold"].items():
        ci = b["pnl_net_bps"]
        lines.append(
            f"| {h} | {b['n_traded']} | {ci['mean']:.2f} | {ci['lo']:.2f} | {ci['hi']:.2f} | "
            f"{b['early_mean']:.2f} | {b['late_mean']:.2f} | {b['verdict']['decision']} |"
        )

    lines += [
        "",
        "## 2. LR-cont-long-ride",
        "",
        c["hypothesis"],
        f"- n_causal_cont={c['n_causal_cont']}",
        f"- Primary: **{c['primary_verdict']['decision']}** — {c['primary_verdict']['why']}",
        f"- edge_lab contrast (cont ride@5s): "
        f"net={c['edge_lab_contrast_mo5s_ride']['pnl_net_bps']['mean']:.2f} "
        f"→ {c['edge_lab_contrast_mo5s_ride']['verdict']['decision']}",
        "",
        "| hold | n | mean | lo | hi | early | late | decision |",
        "|------|---|------|----|----|-------|------|----------|",
    ]
    for h, b in c["by_hold"].items():
        ci = b["pnl_net_bps"]
        lines.append(
            f"| {h} | {b['n_traded']} | {ci['mean']:.2f} | {ci['lo']:.2f} | {ci['hi']:.2f} | "
            f"{b['early_mean']:.2f} | {b['late_mean']:.2f} | {b['verdict']['decision']} |"
        )

    lines += [
        "",
        "## 3. LR-cluster-fade / LR-cluster-ride (multi-event)",
        "",
        cl["hypothesis"],
        f"- n_anchors={cl['n_anchors']} · n_isolated={cl['n_isolated']}",
        f"- Fade primary: **{cl['primary_verdict']['decision']}** — {cl['primary_verdict']['why']}",
        f"- Ride primary: **{cr['primary_verdict']['decision']}** — {cr['primary_verdict']['why']}",
        "",
        "| hold | fade n / net | ride n / net | isolated fade |",
        "|------|--------------|--------------|---------------|",
    ]
    for h in ["15m", "30m", "60m"]:
        b = cl["by_hold"][h]
        r = cr["by_hold"][h]
        iso = cl["isolated_control_by_hold"][h]
        lines.append(
            f"| {h} | {b['n_traded']} / {b['pnl_net_bps']['mean']:.2f} ({b['verdict']['decision']}) | "
            f"{r['n_traded']} / {r['pnl_net_bps']['mean']:.2f} ({r['verdict']['decision']}) | "
            f"{iso['n_traded']} / {iso['pnl_net_bps']['mean']:.2f} ({iso['verdict']['decision']}) |"
        )

    lines += [
        "",
        "## 4. LR-fire-pause (long-horizon intensity gate)",
        "",
        fp["hypothesis"],
        f"- Primary: **{fp['primary_verdict']['decision']}** — {fp['primary_verdict']['why']}",
        f"- {fp['note']}",
        "",
        "| hold | n_fire | |mo|_fire | |mo|_obs | Δ|mo| | earlyΔ | lateΔ | decision |",
        "|------|--------|----------|---------|-------|--------|-------|----------|",
    ]
    for h, b in fp["by_hold"].items():
        d = b["delta_abs_mo_fire_minus_obs"]
        lines.append(
            f"| {h} | {b['n_fire']} | {b['abs_mo_fire']['mean']:.2f} | {b['abs_mo_observe']['mean']:.2f} | "
            f"{d.get('delta', float('nan')):.2f} [{d.get('lo', float('nan')):.2f},"
            f"{d.get('hi', float('nan')):.2f}] | {b['early_delta']:.2f} | {b['late_delta']:.2f} | "
            f"{b['verdict']['decision']} |"
        )

    lines += [
        "",
        "## 5. LR-ssm-drift-ride",
        "",
        dr["hypothesis"],
        f"- Primary: **{dr['primary_verdict']['decision']}** — {dr['primary_verdict']['why']}",
        "",
        "| hold | n | mean | lo | hi | early | late | decision |",
        "|------|---|------|----|----|-------|------|----------|",
    ]
    for h, b in dr["by_hold"].items():
        ci = b["pnl_net_bps"]
        lines.append(
            f"| {h} | {b['n_traded']} | {ci['mean']:.2f} | {ci['lo']:.2f} | {ci['hi']:.2f} | "
            f"{b['early_mean']:.2f} | {b['late_mean']:.2f} | {b['verdict']['decision']} |"
        )

    lines += [
        "",
        "## How to run",
        "",
        "```bash",
        "cd research/books/cross_miniflash/applications/long_range_lab",
        "python3 run_long_edges.py --workers 8",
        "python3 run_long_edges.py --smoke 3 --workers 4   # quick",
        "python3 run_long_edges.py --rescore               # rebuild from events.jsonl",
        "```",
        "",
        "## Artifacts",
        "",
        "- `out/long_edges/summary.json`",
        "- `out/long_edges/EXP_REPORT.md`",
        "- `out/long_edges/events.jsonl`",
        "- figs:",
    ]
    for fp_path in fig_paths:
        lines.append(f"  - `{Path(fp_path).name}`")
    lines += [
        "",
        "## Falsifiers",
        "",
        "- Net PnL / Δ|mo| bootstrap CI must exclude 0 after costs",
        "- Early/late day split sign-stable",
        "- Gross / Δ|mo| must clear friction bar",
        "- Causal V/cont uses recovery@1–2s only (no @5s look-ahead)",
        "- Cluster / V / cont / drift trades non-overlapping within hold window",
        "- Distinct from edge_lab: primary holds are minutes–hours, not mo@5s",
        "- Significant loss CI → Kill (anti-edge), not Hold",
        "",
    ]
    path = OUT / "EXP_REPORT.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def _load_events_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def score_from_events(events: list[dict[str, Any]], *, meta_extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Score lenses + figs + report from already-built event rows."""
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    ok_days = sorted({e["day"] for e in events})
    early, late = early_late_by_day(ok_days)
    lenses = build_edges(events, early, late)

    # Prefer equity of first Promote alpha lens, else drift, else cont
    equity_rule = "drift"
    hold_lab = "15m"
    for key, rule in (
        ("LR-ssm-drift-ride", "drift"),
        ("LR-cont-long-ride", "cont_ride"),
        ("LR-cluster-ride", "cluster_ride"),
        ("LR-v-slow-fade", "v_fade"),
    ):
        prim = lenses[key]["primary"]
        if prim["verdict"]["decision"] == "Promote":
            equity_rule = rule
            hold_lab = str(prim.get("hold", "mo_15m")).replace("mo_", "")
            break
    else:
        prim = lenses["LR-ssm-drift-ride"]["primary"]
        hold_lab = str(prim.get("hold", "mo_15m")).replace("mo_", "")
        equity_rule = "drift"

    day_eq = build_day_equity(events, hold_label=hold_lab, rule=equity_rule)
    figs = make_figs(lenses, day_eq)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "honesty": HONESTY,
        "meta": {
            "venue": (meta_extra or {}).get("venue", "hyperliquid"),
            "symbols": (meta_extra or {}).get("symbols", ["ETH"]),
            "n_days_ok": len(ok_days),
            "days_ok": ok_days,
            "n_events": len(events),
            "hold_s": list(HOLD_S),
            "cluster_window_s": CLUSTER_WINDOW_S,
            "cluster_k": CLUSTER_K,
            "friction_rt_bps": RT_FRICTION,
            "early_days": sorted(early),
            "late_days": sorted(late),
            **{k: v for k, v in (meta_extra or {}).items() if k not in {"venue", "symbols"}},
        },
        "lenses": lenses,
        "day_equity_primary": day_eq,
        "figs": figs,
        "artifacts": {
            "summary": str(OUT / "summary.json"),
            "report": str(OUT / "EXP_REPORT.md"),
            "events": str(OUT / "events.jsonl"),
            "coverage": str(OUT / "coverage.json"),
            "figs": str(FIG),
        },
    }
    save_json(OUT / "summary.json", jsonable(summary))
    report = write_report(summary, figs)
    print(f"[long_edges] scored n_events={len(events)} days={len(ok_days)} report={report}", flush=True)
    for name, block in lenses.items():
        verd = block["primary_verdict"]
        p = block["primary"]
        print(
            f"  {name:22s} {str(p.get('hold','?')).replace('mo_',''):6s} → {verd['decision']:7s} "
            f"mean={p['pnl_net_bps']['mean']:+.2f} n={p['n_traded']} | {verd['why'][:60]}",
            flush=True,
        )
    return summary


def build_day_equity(events: list[dict[str, Any]], *, hold_label: str, rule: str) -> dict[str, Any]:
    """Per-day net PnL for primary rule (unit size)."""
    hold_key = f"mo_{hold_label}"
    hold_s = {v: k for k, v in HOLD_LABEL.items()}[hold_label]
    if rule == "v_fade":
        cands = [
            {**e, "size": -1.0}
            for e in events
            if e["causal"] == "v_recovery" and e.get(hold_key) is not None
        ]
    elif rule == "cont_ride":
        cands = [
            {**e, "size": 1.0}
            for e in events
            if e["causal"] == "continuation" and e.get(hold_key) is not None
        ]
    elif rule == "cluster_ride":
        cands = [
            {**e, "size": 1.0}
            for e in events
            if e.get("cluster_anchor") and e.get(hold_key) is not None
        ]
    else:  # drift
        cands = [{**e, "size": 1.0} for e in events if e.get(hold_key) is not None]
    cands = _nonoverlap_filter(cands, hold_s=hold_s)
    by_day: dict[str, float] = {}
    for t in cands:
        mo = float(t[hold_key])
        net = float(t["size"]) * mo - abs(float(t["size"])) * RT_FRICTION
        by_day[t["day"]] = by_day.get(t["day"], 0.0) + net
    days = sorted(by_day)
    return {
        "days": days,
        "daily_pnl_bps": [by_day[d] for d in days],
        "n_trades": len(cands),
        "title": f"Cumulative {rule} @{hold_label} (non-overlap)",
        "hold": hold_label,
        "rule": rule,
    }


def run(
    *,
    days: list[str] | None = None,
    symbols: list[str] | None = None,
    venue: str = "hyperliquid",
    workers: int = 8,
    smoke: int | None = None,
) -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    symbols = list(symbols or ["ETH"])
    if smoke:
        # Prefer core panel days for smoke
        base = [d for d in PANEL_CORE if d in PIN_USABLE] + [d for d in PIN_USABLE if d not in PANEL_CORE]
        days = base[: int(smoke)]
    else:
        days = list(days or PIN_USABLE)

    payloads = [{"day": d, "symbol": s, "venue": venue} for d in days for s in symbols]
    print(f"[long_edges] cells={len(payloads)} workers={workers}", flush=True)

    results: list[dict[str, Any]] = []
    if workers <= 1:
        for p in payloads:
            r = process_day(p)
            results.append(r)
            print(
                f"  {r.get('day')} {r.get('symbol')} ok={r.get('ok')} "
                f"n_ev={r.get('n_events', 0)} reason={r.get('reason', '')}",
                flush=True,
            )
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(process_day, p): p for p in payloads}
            for fut in as_completed(futs):
                r = fut.result()
                results.append(r)
                print(
                    f"  {r.get('day')} {r.get('symbol')} ok={r.get('ok')} "
                    f"n_ev={r.get('n_events', 0)} reason={r.get('reason', '')}",
                    flush=True,
                )

    ok = [r for r in results if r.get("ok")]
    events: list[dict[str, Any]] = []
    for r in ok:
        events.extend(r.get("events") or [])

    ev_path = OUT / "events.jsonl"
    with ev_path.open("w") as f:
        for e in events:
            f.write(json.dumps(jsonable(e)) + "\n")

    coverage = [
        {
            "day": r.get("day"),
            "symbol": r.get("symbol"),
            "ok": bool(r.get("ok")),
            "n_events": r.get("n_events", 0),
            "n_trades": r.get("n_trades", 0),
            "reason": r.get("reason"),
        }
        for r in sorted(results, key=lambda x: (x.get("day") or "", x.get("symbol") or ""))
    ]
    save_json(OUT / "coverage.json", coverage)

    summary = score_from_events(
        events,
        meta_extra={
            "venue": venue,
            "symbols": symbols,
            "days_requested": days,
            "n_cells": len(payloads),
            "n_cells_ok": len(ok),
            "errors": [
                {"day": r.get("day"), "symbol": r.get("symbol"), "reason": r.get("reason")}
                for r in results
                if not r.get("ok")
            ],
        },
    )
    print(f"[long_edges] DONE", flush=True)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--symbols", type=str, default="ETH")
    ap.add_argument("--venue", type=str, default="hyperliquid")
    ap.add_argument("--smoke", type=int, default=None, help="run first N panel-preferring days")
    ap.add_argument("--days", type=str, default=None, help="comma-separated UTC days")
    ap.add_argument(
        "--rescore",
        action="store_true",
        help="rebuild summary/figs/report from out/long_edges/events.jsonl (no detect)",
    )
    args = ap.parse_args()
    if args.rescore:
        ev_path = OUT / "events.jsonl"
        if not ev_path.exists():
            raise SystemExit(f"missing {ev_path} — run full detect first")
        events = _load_events_jsonl(ev_path)
        score_from_events(
            events,
            meta_extra={"venue": args.venue, "symbols": [s.strip() for s in args.symbols.split(",") if s.strip()]},
        )
        return
    days = [d.strip() for d in args.days.split(",")] if args.days else None
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    run(days=days, symbols=symbols, venue=args.venue, workers=args.workers, smoke=args.smoke)


if __name__ == "__main__":
    main()
