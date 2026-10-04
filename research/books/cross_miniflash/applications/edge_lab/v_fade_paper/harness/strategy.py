"""Causal V-fade shadow strategy — taker fills on tape print.

Entry modes
-----------
confirm_r2   : wait confirm_s, require causal V (r2≥thr) — lab-locked, path-late
severity_zend : enter at ts_end(+delay) if |z_peak|≥z_min — NO r2 wait (causal fix)

Compose: suppress entries while fire_pause_5m is live (widen/size_cap/halt → 300s).
Always report BOTH lab identity (−mo5s−RT) and path PnL (entry→exit−RT).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .causal import asof_trade_idx, asof_trade_px, causal_class

NS = 1_000_000_000
FIRE_TIERS = frozenset({"widen", "size_cap", "halt"})


def _vf(cfg: dict[str, Any]) -> dict[str, Any]:
    return dict(cfg.get("v_fade") or {})


def _overlay_confirm_recovery(
    cell: dict[str, Any],
    *,
    confirm_s: float,
) -> dict[str, Any]:
    """Replace recovery_1s/2s with causal recovery at confirm horizon (and soft≤1s)."""
    if confirm_s <= 0 or abs(confirm_s - 2.0) < 1e-9:
        return cell
    try:
        from ares_micro.vol.crash import recovery_fraction
    except Exception:  # noqa: BLE001
        return cell

    ev = dict(cell.get("events") or {})
    ts = np.asarray(cell.get("ts"), dtype=np.int64)
    px = np.asarray(cell.get("px"), dtype=np.float64)
    ts_start = np.asarray(ev.get("ts_start", []), dtype=np.int64)
    ts_end = np.asarray(ev.get("ts_end", []), dtype=np.int64)
    direction = np.asarray(ev.get("direction", []), dtype=np.int64)
    if ts.size == 0 or ts_end.size == 0:
        return cell
    start_i = (np.searchsorted(ts, ts_start, side="right") - 1).astype(np.int64)
    end_i = (np.searchsorted(ts, ts_end, side="right") - 1).astype(np.int64)
    r_c = recovery_fraction(ts, px, start_i, end_i, direction, horizon_s=float(confirm_s))
    soft_h = min(1.0, float(confirm_s))
    r_soft = recovery_fraction(ts, px, start_i, end_i, direction, horizon_s=float(soft_h))
    ev["recovery_2s"] = np.asarray(r_c, dtype=np.float64)
    ev["recovery_1s"] = np.asarray(r_soft, dtype=np.float64)
    out = dict(cell)
    out["events"] = ev
    return out


def _fire_pause_intervals(
    ts_end: np.ndarray,
    tiers: np.ndarray,
    *,
    fire_pause_s: float,
) -> list[tuple[int, int, int]]:
    """(ts_start, ts_end_pause, event_i) for each fire-tier event."""
    if fire_pause_s <= 0:
        return []
    hold = int(float(fire_pause_s) * NS)
    out: list[tuple[int, int, int]] = []
    for k, te in enumerate(ts_end):
        te_i = int(te)
        if te_i <= 0:
            continue
        tname = str(tiers[k]) if k < len(tiers) else "observe"
        if tname not in FIRE_TIERS:
            continue
        out.append((te_i, te_i + hold, int(k)))
    return out


def _in_fire_pause(
    t_ns: int,
    intervals: list[tuple[int, int, int]],
    *,
    exclude_event_i: int | None = None,
    mode: str = "prior_only",
) -> bool:
    """mode: all | prior_only | off

    prior_only: suppress if inside another event's fire pause (not own onset).
    Allows severity_zend fade at a fire event's own ts_end while still blocking
    follow-on fades during the 5m pause — matches compose without n→0.
    """
    if mode in ("off", "false", "0", "none"):
        return False
    for a, b, ei in intervals:
        if exclude_event_i is not None and ei == exclude_event_i:
            if mode == "prior_only":
                continue
        if a <= t_ns < b:
            return True
    return False


def simulate_day_fades(
    cell: dict[str, Any],
    *,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Detect cell → shadow fade trades.

    Scoring (ALWAYS both):
      - lab_pnl_net_bps = -mo_5s - RT
      - path_pnl_net_bps = side × (exit/entry − 1)×1e4 − RT
    """
    if cell.get("skip"):
        return {
            "trades": [],
            "actions": [],
            "skipped": True,
            "skip": cell.get("skip"),
            "n_events": 0,
            "n_faded": 0,
        }

    vf = _vf(cfg)
    # Promote_shadow default: severity_zend |z|≥20 @+0.5s→3s (not confirm_r2 path-late)
    entry_mode = str(vf.get("entry_mode") or "severity_zend").strip().lower()
    if entry_mode in ("severity", "z_end", "zend", "severity_at_end"):
        entry_mode = "severity_zend"
    if entry_mode not in ("confirm_r2", "severity_zend"):
        entry_mode = "severity_zend"

    # confirm_s = entry delay after ts_end for both modes
    confirm_s = float(vf.get("confirm_s", 2.0 if entry_mode == "confirm_r2" else 0.5))
    exit_s = float(vf.get("exit_s", 5.0 if entry_mode == "confirm_r2" else 3.0))
    rt_bps = float(vf.get("rt_friction_bps", 4.0))
    one_way = float(vf.get("friction_bps_one_way", 2.0))
    # severity Promote: adverse off; confirm_r2 legacy keeps 12 bps
    adverse_stop = float(
        vf.get("adverse_stop_bps", 12.0 if entry_mode == "confirm_r2" else 1e9)
    )
    max_conc = int(vf.get("max_concurrent", 1))
    clip = float(vf.get("clip_notional", 1.0))
    v_thr = float(vf.get("v_threshold_r2", 0.5))
    cont_thr = float(vf.get("cont_threshold_r2", 0.2))
    soft_r1 = float(vf.get("soft_confirm_r1", 0.35))
    always_fade = bool(vf.get("always_fade", False))
    z_min = float(vf.get("z_min", vf.get("severity_z_min", 20.0)))
    # suppress_fire_pause: True→prior_only, False→off, or explicit str
    sfp = vf.get("suppress_fire_pause", "prior_only")
    if isinstance(sfp, bool):
        fp_mode = "prior_only" if sfp else "off"
    else:
        fp_mode = str(sfp).strip().lower() or "prior_only"
        if fp_mode in ("true", "1", "yes", "on"):
            fp_mode = "prior_only"
        if fp_mode in ("false", "0", "no"):
            fp_mode = "off"
        if fp_mode not in ("prior_only", "all", "off"):
            fp_mode = "prior_only"
    fire_pause_s = float(
        vf.get("fire_pause_5m_s", cfg.get("fire_pause_5m_s", 300.0))
    )

    if exit_s <= confirm_s:
        return {
            "trades": [],
            "actions": [],
            "skipped": True,
            "skip": "exit_s_le_confirm_s",
            "n_events": 0,
            "n_faded": 0,
        }

    if entry_mode == "confirm_r2" and abs(confirm_s - 2.0) > 1e-9 and confirm_s > 0:
        cell = _overlay_confirm_recovery(cell, confirm_s=confirm_s)

    ev = cell.get("events") or {}
    ts = np.asarray(cell.get("ts"), dtype=np.int64)
    px = np.asarray(cell.get("px"), dtype=np.float64)
    n = int(cell.get("ssm_10_n") or 0)

    ts_start = np.asarray(ev.get("ts_start", []), dtype=np.int64)
    ts_end = np.asarray(ev.get("ts_end", []), dtype=np.int64)
    direction = np.asarray(ev.get("direction", []), dtype=np.int64)
    r1 = np.asarray(ev.get("recovery_1s", []), dtype=np.float64)
    r2 = np.asarray(ev.get("recovery_2s", []), dtype=np.float64)
    mo5 = np.asarray(ev.get("mo_5s", []), dtype=np.float64)
    mo1 = np.asarray(ev.get("mo_1s", []), dtype=np.float64)
    dp = np.asarray(ev.get("dp_pct", []), dtype=np.float64)
    ic = np.asarray(ev.get("i_c", []), dtype=np.int64)
    zpk = np.asarray(ev.get("z_peak", []), dtype=np.float64)
    tiers = np.asarray(ev.get("tier", []), dtype=object)
    nanex = np.asarray(ev.get("nanex_overlap", []), dtype=bool)
    labels = np.asarray(ev.get("recovery_label", []), dtype=object)

    fp_intervals = _fire_pause_intervals(ts_end, tiers, fire_pause_s=fire_pause_s)

    day = cell.get("day")
    venue = cell.get("venue")
    symbol = cell.get("symbol")

    actions: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    open_until: list[int] = []
    class_counts = {"v_recovery": 0, "continuation": 0, "partial": 0, "unknown": 0}
    n_fire_skipped = 0
    n_severity_skip = 0

    for i in range(n):
        te = int(ts_end[i])
        d = int(direction[i])
        zz = float(zpk[i]) if i < zpk.size else float("nan")
        rr1 = float(r1[i]) if i < r1.size else float("nan")
        rr2 = float(r2[i]) if i < r2.size else float("nan")
        tier_i = str(tiers[i]) if i < tiers.size else "observe"
        fire_tier = tier_i in FIRE_TIERS

        # Diagnostic causal class (always computed; only gates confirm_r2)
        cls = causal_class(
            rr2,
            rr1,
            v_threshold_r2=v_thr,
            cont_threshold_r2=cont_thr,
            soft_confirm_r1=soft_r1,
        )
        class_counts[cls] = class_counts.get(cls, 0) + 1

        entry_t = te + int(confirm_s * NS)
        exit_deadline = te + int(exit_s * NS)
        in_fp = _in_fire_pause(
            entry_t, fp_intervals, exclude_event_i=i, mode=fp_mode
        )
        # Flag: would this entry sit in *any* pause including own? (diagnostics)
        in_fp_any = _in_fire_pause(
            entry_t, fp_intervals, exclude_event_i=None, mode="all"
        )

        # --- entry gate ---
        enter = False
        skip_reason: str | None = None
        if always_fade and entry_mode != "severity_zend":
            enter = True
        elif entry_mode == "severity_zend":
            if not np.isfinite(zz) or abs(zz) < z_min:
                skip_reason = f"severity_z_below_{z_min:g}"
                n_severity_skip += 1
            else:
                enter = True
        else:  # confirm_r2
            if cls != "v_recovery":
                skip_reason = f"causal_{cls}"
            else:
                enter = True

        if enter and fp_mode != "off" and in_fp:
            enter = False
            skip_reason = "fire_pause_5m"
            n_fire_skipped += 1

        actions.append(
            {
                "kind": "detect",
                "day": day,
                "venue": venue,
                "symbol": symbol,
                "event_i": i,
                "ts_start": int(ts_start[i]) if i < ts_start.size else None,
                "ts_end": te,
                "direction": d,
                "dp_pct": float(dp[i]) if i < dp.size else None,
                "i_c": int(ic[i]) if i < ic.size else None,
                "z_peak": zz if np.isfinite(zz) else None,
                "recovery_1s": rr1 if np.isfinite(rr1) else None,
                "recovery_2s": rr2 if np.isfinite(rr2) else None,
                "mo_5s": float(mo5[i]) if i < mo5.size and np.isfinite(mo5[i]) else None,
                "mo_1s": float(mo1[i]) if i < mo1.size and np.isfinite(mo1[i]) else None,
                "tier": tier_i,
                "fire_tier": fire_tier,
                "in_fire_pause_at_entry": in_fp_any,
                "fire_pause_blocked": in_fp,
                "nanex_overlap": bool(nanex[i]) if i < nanex.size else False,
                "oracle_label": str(labels[i]) if i < labels.size else None,
                "causal_class": cls,
                "entry_mode": entry_mode,
            }
        )
        actions.append(
            {
                "kind": "confirm",
                "day": day,
                "venue": venue,
                "symbol": symbol,
                "event_i": i,
                "ts": entry_t,
                "causal_class": cls,
                "entry_mode": entry_mode,
                "z_peak": zz if np.isfinite(zz) else None,
                "enter": enter,
                "in_fire_pause": in_fp_any,
                "fire_pause_blocked": in_fp,
                "skip_reason": None if enter else skip_reason,
            }
        )

        if not enter:
            actions.append(
                {
                    "kind": "skip",
                    "day": day,
                    "venue": venue,
                    "symbol": symbol,
                    "event_i": i,
                    "reason": skip_reason or "no_enter",
                    "ts": entry_t,
                    "in_fire_pause": in_fp,
                    "fire_tier": fire_tier,
                }
            )
            continue

        open_until = [t for t in open_until if t > entry_t]
        if len(open_until) >= max_conc:
            actions.append(
                {
                    "kind": "skip",
                    "day": day,
                    "venue": venue,
                    "symbol": symbol,
                    "event_i": i,
                    "reason": "max_concurrent",
                    "ts": entry_t,
                }
            )
            continue

        entry_px = asof_trade_px(ts, px, entry_t)
        if not np.isfinite(entry_px):
            actions.append(
                {
                    "kind": "skip",
                    "day": day,
                    "venue": venue,
                    "symbol": symbol,
                    "event_i": i,
                    "reason": "no_entry_print",
                    "ts": entry_t,
                }
            )
            continue

        side = -d
        entry_i = asof_trade_idx(ts, entry_t)
        exit_i_dead = asof_trade_idx(ts, exit_deadline)

        exit_reason = "time_stop"
        exit_t = exit_deadline
        exit_px = asof_trade_px(ts, px, exit_deadline)
        peak_mtm = 0.0

        lo = max(entry_i, 0)
        hi = exit_i_dead if exit_i_dead >= lo else lo
        if entry_i >= 0 and ts.size:
            for j in range(lo, min(hi + 1, ts.size)):
                tj = int(ts[j])
                if tj < entry_t:
                    continue
                if tj > exit_deadline:
                    break
                pj = float(px[j])
                if not np.isfinite(pj) or pj <= 0:
                    continue
                mtm = float(d) * (pj / entry_px - 1.0) * 1e4
                if mtm > peak_mtm:
                    peak_mtm = mtm
                if mtm >= adverse_stop:
                    exit_reason = "adverse_stop"
                    exit_t = tj
                    exit_px = pj
                    break

        if not np.isfinite(exit_px):
            actions.append(
                {
                    "kind": "skip",
                    "day": day,
                    "venue": venue,
                    "symbol": symbol,
                    "event_i": i,
                    "reason": "no_exit_print",
                    "ts": entry_t,
                }
            )
            continue

        path_gross = float(side) * (exit_px / entry_px - 1.0) * 1e4
        path_net = path_gross - rt_bps

        mo = float(mo5[i]) if i < mo5.size else float("nan")
        if np.isfinite(mo):
            lab_gross = -mo
            lab_net = lab_gross - rt_bps
        else:
            lab_gross = float("nan")
            lab_net = float("nan")

        hold_s = (exit_t - entry_t) / NS
        hit = bool(np.isfinite(lab_net) and lab_net > 0)
        hit_path = bool(np.isfinite(path_net) and path_net > 0)

        trade = {
            "kind": "trade",
            "day": day,
            "venue": venue,
            "symbol": symbol,
            "event_i": i,
            "entry_mode": entry_mode,
            "causal_class": cls,
            "oracle_label": str(labels[i]) if i < labels.size else None,
            "direction": d,
            "side": side,
            "side_name": "sell" if side < 0 else "buy",
            "clip_notional": clip,
            "entry_ts": entry_t,
            "entry_px": entry_px,
            "exit_ts": exit_t,
            "exit_px": exit_px,
            "exit_reason": exit_reason,
            "hold_s": hold_s,
            "peak_crash_mtm_bps": peak_mtm,
            "mo_5s": mo if np.isfinite(mo) else None,
            "lab_gross_bps": lab_gross if np.isfinite(lab_gross) else None,
            "lab_pnl_net_bps": lab_net if np.isfinite(lab_net) else None,
            "path_gross_bps": path_gross,
            "path_pnl_net_bps": path_net,
            "rt_friction_bps": rt_bps,
            "one_way_cost_bps": one_way,
            "hit_lab": hit,
            "hit_path": hit_path,
            "tier": tier_i,
            "fire_tier": fire_tier,
            "in_fire_pause_at_entry": in_fp_any,
            "fire_pause_blocked": False,
            "fire_pause_mode": fp_mode,
            "nanex_overlap": bool(nanex[i]) if i < nanex.size else False,
            "dp_pct": float(dp[i]) if i < dp.size else None,
            "z_peak": zz if np.isfinite(zz) else None,
            "z_min": z_min if entry_mode == "severity_zend" else None,
            "fill_model": "tape_print_asof",
            "mid_mo_used": False,
            "live_orders": False,
            "confirm_s": confirm_s,
            "exit_s": exit_s,
            "always_fade": always_fade,
            "v_threshold_r2": v_thr if entry_mode == "confirm_r2" else None,
            "soft_confirm_r1": soft_r1 if entry_mode == "confirm_r2" else None,
            "adverse_stop_bps": adverse_stop if adverse_stop < 1e8 else None,
            "suppress_fire_pause": fp_mode != "off",
            "fire_pause_mode": fp_mode,
            "scoreboard_lab": "identity_-mo5s_minus_RT",
            "scoreboard_path": "entry_to_exit_tape_minus_RT",
        }
        trades.append(trade)
        open_until.append(exit_t)

        actions.append(
            {
                "kind": "enter",
                "day": day,
                "venue": venue,
                "symbol": symbol,
                "event_i": i,
                "ts": entry_t,
                "side": side,
                "side_name": trade["side_name"],
                "px": entry_px,
                "entry_mode": entry_mode,
                "causal_class": cls,
                "z_peak": zz if np.isfinite(zz) else None,
                "cost_one_way_bps": one_way,
            }
        )
        actions.append(
            {
                "kind": "exit",
                "day": day,
                "venue": venue,
                "symbol": symbol,
                "event_i": i,
                "ts": exit_t,
                "reason": exit_reason,
                "px": exit_px,
                "lab_pnl_net_bps": trade["lab_pnl_net_bps"],
                "path_pnl_net_bps": path_net,
                "cost_one_way_bps": one_way,
            }
        )

    return {
        "trades": trades,
        "actions": actions,
        "skipped": False,
        "n_events": n,
        "n_faded": len(trades),
        "n_fire_pause_skipped": n_fire_skipped,
        "n_severity_skipped": n_severity_skip,
        "class_counts": class_counts,
        "rt_friction_bps": rt_bps,
        "adverse_stop_bps": adverse_stop if adverse_stop < 1e8 else None,
        "confirm_s": confirm_s,
        "exit_s": exit_s,
        "entry_mode": entry_mode,
        "z_min": z_min if entry_mode == "severity_zend" else None,
        "suppress_fire_pause": fp_mode != "off",
        "fire_pause_mode": fp_mode,
        "fire_pause_5m_s": fire_pause_s,
        "always_fade": always_fade,
        "v_threshold_r2": v_thr,
        "soft_confirm_r1": soft_r1,
    }
