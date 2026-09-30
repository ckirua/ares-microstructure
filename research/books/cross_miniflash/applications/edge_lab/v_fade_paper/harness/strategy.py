"""Causal V-fade shadow strategy — taker fills on tape print."""

from __future__ import annotations

from typing import Any

import numpy as np

from .causal import asof_trade_idx, asof_trade_px, causal_class

NS = 1_000_000_000


def _vf(cfg: dict[str, Any]) -> dict[str, Any]:
    return dict(cfg.get("v_fade") or {})


def simulate_day_fades(
    cell: dict[str, Any],
    *,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Detect cell → causal V-fade shadow trades for one venue×symbol×day.

    Scoring:
      - lab_pnl_net_bps = -mo_5s - RT  (matches exp_edge_lab causal_fade_v_only)
      - path_pnl_net_bps = fade side × (exit/entry − 1)×1e4 − RT  (tape path)

    mid_mo is ignored (null on this slice). Fills at tape print only.
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
    confirm_s = float(vf.get("confirm_s", 2.0))
    exit_s = float(vf.get("exit_s", 5.0))
    rt_bps = float(vf.get("rt_friction_bps", 4.0))
    one_way = float(vf.get("friction_bps_one_way", 2.0))
    adverse_stop = float(vf.get("adverse_stop_bps", 12.0))
    max_conc = int(vf.get("max_concurrent", 1))
    clip = float(vf.get("clip_notional", 1.0))
    v_thr = float(vf.get("v_threshold_r2", 0.5))
    cont_thr = float(vf.get("cont_threshold_r2", 0.2))
    soft_r1 = float(vf.get("soft_confirm_r1", 0.35))
    always_fade = bool(vf.get("always_fade", False))
    if exit_s <= confirm_s:
        return {
            "trades": [],
            "actions": [],
            "skipped": True,
            "skip": "exit_s_le_confirm_s",
            "n_events": 0,
            "n_faded": 0,
        }

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

    day = cell.get("day")
    venue = cell.get("venue")
    symbol = cell.get("symbol")

    actions: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    open_until: list[int] = []  # exit timestamps of open fades

    class_counts = {"v_recovery": 0, "continuation": 0, "partial": 0, "unknown": 0}

    for i in range(n):
        te = int(ts_end[i])
        d = int(direction[i])
        rr1 = float(r1[i]) if i < r1.size else float("nan")
        rr2 = float(r2[i]) if i < r2.size else float("nan")
        if always_fade:
            cls = "v_recovery"
        else:
            cls = causal_class(
                rr2,
                rr1,
                v_threshold_r2=v_thr,
                cont_threshold_r2=cont_thr,
                soft_confirm_r1=soft_r1,
            )
        class_counts[cls] = class_counts.get(cls, 0) + 1

        detect_rec = {
            "kind": "detect",
            "day": day,
            "venue": venue,
            "symbol": symbol,
            "event_i": i,
            "ts_start": int(ts_start[i]),
            "ts_end": te,
            "direction": d,
            "dp_pct": float(dp[i]) if i < dp.size else None,
            "i_c": int(ic[i]) if i < ic.size else None,
            "z_peak": float(zpk[i]) if i < zpk.size else None,
            "recovery_1s": rr1 if np.isfinite(rr1) else None,
            "recovery_2s": rr2 if np.isfinite(rr2) else None,
            "mo_5s": float(mo5[i]) if i < mo5.size and np.isfinite(mo5[i]) else None,
            "mo_1s": float(mo1[i]) if i < mo1.size and np.isfinite(mo1[i]) else None,
            "tier": str(tiers[i]) if i < tiers.size else None,
            "nanex_overlap": bool(nanex[i]) if i < nanex.size else False,
            "oracle_label": str(labels[i]) if i < labels.size else None,
            "causal_class": cls,
        }
        actions.append(detect_rec)

        confirm_t = te + int(confirm_s * NS)
        exit_deadline = te + int(exit_s * NS)

        actions.append(
            {
                "kind": "confirm",
                "day": day,
                "venue": venue,
                "symbol": symbol,
                "event_i": i,
                "ts": confirm_t,
                "causal_class": cls,
                "recovery_1s": rr1 if np.isfinite(rr1) else None,
                "recovery_2s": rr2 if np.isfinite(rr2) else None,
                "enter": cls == "v_recovery",
            }
        )

        if cls != "v_recovery":
            actions.append(
                {
                    "kind": "skip",
                    "day": day,
                    "venue": venue,
                    "symbol": symbol,
                    "event_i": i,
                    "reason": f"causal_{cls}",
                    "ts": confirm_t,
                }
            )
            continue

        # concurrency: drop expired opens, refuse if at cap
        open_until = [t for t in open_until if t > confirm_t]
        if len(open_until) >= max_conc:
            actions.append(
                {
                    "kind": "skip",
                    "day": day,
                    "venue": venue,
                    "symbol": symbol,
                    "event_i": i,
                    "reason": "max_concurrent",
                    "ts": confirm_t,
                }
            )
            continue

        entry_px = asof_trade_px(ts, px, confirm_t)
        if not np.isfinite(entry_px):
            actions.append(
                {
                    "kind": "skip",
                    "day": day,
                    "venue": venue,
                    "symbol": symbol,
                    "event_i": i,
                    "reason": "no_entry_print",
                    "ts": confirm_t,
                }
            )
            continue

        side = -d  # fade crash
        entry_i = asof_trade_idx(ts, confirm_t)
        exit_i_dead = asof_trade_idx(ts, exit_deadline)

        # Scan tape for adverse stop (crash-continue markout from entry)
        exit_reason = "time_stop"
        exit_t = exit_deadline
        exit_px = asof_trade_px(ts, px, exit_deadline)
        peak_mtm = 0.0

        lo = max(entry_i, 0)
        hi = exit_i_dead if exit_i_dead >= lo else lo
        if entry_i >= 0 and ts.size:
            for j in range(lo, min(hi + 1, ts.size)):
                tj = int(ts[j])
                if tj < confirm_t:
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
                    "ts": confirm_t,
                }
            )
            continue

        # Path PnL for fade position
        path_gross = float(side) * (exit_px / entry_px - 1.0) * 1e4
        path_net = path_gross - rt_bps

        # Lab identity (mo from event end @5s) — primary scoreboard
        mo = float(mo5[i]) if i < mo5.size else float("nan")
        if np.isfinite(mo):
            lab_gross = -mo  # fade size=-1
            lab_net = lab_gross - rt_bps
        else:
            lab_gross = float("nan")
            lab_net = float("nan")

        hold_s = (exit_t - confirm_t) / NS
        hit = bool(np.isfinite(lab_net) and lab_net > 0)

        trade = {
            "kind": "trade",
            "day": day,
            "venue": venue,
            "symbol": symbol,
            "event_i": i,
            "causal_class": cls,
            "oracle_label": str(labels[i]) if i < labels.size else None,
            "direction": d,
            "side": side,
            "side_name": "sell" if side < 0 else "buy",
            "clip_notional": clip,
            "entry_ts": confirm_t,
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
            "tier": str(tiers[i]) if i < tiers.size else None,
            "nanex_overlap": bool(nanex[i]) if i < nanex.size else False,
            "dp_pct": float(dp[i]) if i < dp.size else None,
            "z_peak": float(zpk[i]) if i < zpk.size else None,
            "fill_model": "tape_print_asof",
            "mid_mo_used": False,
            "live_orders": False,
            "confirm_s": confirm_s,
            "exit_s": exit_s,
            "always_fade": always_fade,
            "v_threshold_r2": v_thr,
            "soft_confirm_r1": soft_r1,
            "adverse_stop_bps": adverse_stop,
            # Dual scoreboard always present: lab identity ≠ path executable.
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
                "ts": confirm_t,
                "side": side,
                "side_name": trade["side_name"],
                "px": entry_px,
                "causal_class": cls,
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
        "class_counts": class_counts,
        "rt_friction_bps": rt_bps,
        "adverse_stop_bps": adverse_stop,
        "confirm_s": confirm_s,
        "exit_s": exit_s,
        "always_fade": always_fade,
        "v_threshold_r2": v_thr,
        "soft_confirm_r1": soft_r1,
    }
