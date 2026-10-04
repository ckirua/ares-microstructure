"""MinV / EGARCH + calendar Ridge monitors + paper Kill throttle state.

Honesty
-------
- MinV vs EGARCH 5% = **Promote** Monitor (risk.egarch_minv_bands / daily_minv_panel).
- Calendar Ridge score = **Promote** Monitor only (never sized).
- Hypothetical widen/cut/POV = **Kill** exec.minv_breach_throttle — observation
  / paper accounting ONLY. Do not soft-Promote. live_orders=False always.
"""


from __future__ import annotations

import os

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

PKG = Path(__file__).resolve().parents[1]
BOOK = PKG.parents[1]
SCRIPTS = BOOK / "scripts"
WAREHOUSE_SRC = Path(os.environ.get('WAREHOUSE_SRC') or ((Path(os.environ.get('WAREHOUSE_ROOT') or (Path.home() / 'lab' / 'lab-n2070' / 'warehouse')) / 'src')))
STARTARB = Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb'))
ROOT = BOOK.parents[2]

for _p in (str(WAREHOUSE_SRC), str(STARTARB / "src"), str(ROOT), str(SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from ares_micro.vol.vstat import (  # noqa: E402
    bootstrap_minv_ci,
    grid_1s,
    min_v,
    returns_from_log_px,
    t_stat_side,
)

GATE_LABELS = {
    "risk.egarch_minv_bands": "Promote",
    "risk.daily_minv_panel": "Promote",
    "risk.v_vs_jump_taxonomy": "Promote",
    "info.v_feature_ridge_calendar": "Promote",
    "exec.minv_breach_throttle": "Kill",
    "exec.minv_throttle_cal_join": "Hold",
    "exec.minv_throttle_as_alpha": "Hold",
}


def jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.floating, float)):
        x = float(obj)
        return x if np.isfinite(x) else None
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, np.ndarray):
        return jsonable(obj.tolist())
    return obj


def _day_start_ns(day: str) -> int:
    t0 = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(t0.timestamp() * 1e9)


def load_cal_coefs(cfg: dict[str, Any]) -> dict[str, float]:
    cal = cfg.get("calendar_ridge") or {}
    if not bool(cal.get("enabled", True)):
        return {}
    path = Path(cal.get("coef_path") or "")
    if not path.is_file():
        # fallback to book out/
        alt = BOOK / "out" / "feature_reg" / "coef_tables.json"
        path = alt if alt.is_file() else path
    if not path.is_file():
        return {}
    try:
        blob = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    prefer = list(cal.get("prefer_targets") or ["y_cal_60s", "y_cal_300s", "y_cal_30s"])
    for key in prefer:
        coef = ((blob.get(key) or {}).get("ridge")) or {}
        if coef:
            return {str(k): float(v) for k, v in coef.items()}
    return {}


def _minv_hn(
    tape: dict[str, Any],
    hn_s: float,
    *,
    n_grid: int = 41,
    n_boot: int = 25,
    dt_s: float = 5.0,
) -> dict[str, Any]:
    g = grid_1s(tape["ts"], tape["px"], dt_s=dt_s)
    if int(g["n_filled"]) < 60:
        return {"ok": False, "reason": "short_grid"}
    t, r = returns_from_log_px(g["log_px"], g["ts_ns"], time_unit_s=1.0)
    t0, t1 = float(t[0] + hn_s), float(t[-1] - hn_s)
    if t1 <= t0:
        return {"ok": False, "reason": "hn_too_wide"}
    taus = np.linspace(t0, t1, n_grid)
    mv = min_v(t, r, taus, hn_s)
    boot = bootstrap_minv_ci(
        r,
        hn_s,
        n_paths=n_boot,
        n_grid=min(n_grid, 41),
        rng=np.random.default_rng(1),
        dt_s=float(g["dt_s"]),
    )
    q5 = boot["quantiles"].get(0.05)
    q1 = boot["quantiles"].get(0.01)
    sig5 = bool(
        np.isfinite(mv["min_v"]) and np.isfinite(q5) and mv["min_v"] < q5
    )
    return {
        "ok": True,
        "min_v": float(mv["min_v"]),
        "tau_star_s": float(mv["tau_star"]),
        "shape": mv["shape"],
        "sig_5": sig5,
        "sig_1": bool(
            np.isfinite(mv["min_v"]) and np.isfinite(q1) and mv["min_v"] < q1
        ),
        "q05": float(q5) if q5 is not None and np.isfinite(q5) else None,
        "q01": float(q1) if q1 is not None and np.isfinite(q1) else None,
        "n_grid_px": int(g["n_filled"]),
        "coverage": float(g["coverage"]),
        "dt_s": float(g["dt_s"]),
        "gate": "Promote",
        "gate_ids": ["risk.egarch_minv_bands", "risk.daily_minv_panel"],
        "label": "Monitor",
    }


def cal_score_at_trough(
    ts: np.ndarray,
    px: np.ndarray,
    *,
    day: str,
    tau_s: float,
    coefs: dict[str, float],
    hn_s: float = 300.0,
    dt_s: float = 5.0,
) -> float:
    """Lightweight causal calendar Ridge score at τ★ (Monitor only)."""
    if not coefs or not np.isfinite(tau_s):
        return float("nan")
    t0 = _day_start_ns(day)
    tau_ns = t0 + int(tau_s * 1e9)
    m = ts <= tau_ns
    if int(m.sum()) < 50:
        return float("nan")
    g = grid_1s(ts[m], px[m], dt_s=dt_s)
    gpx = np.asarray(g["px"], dtype=float)
    gts = np.asarray(g["ts_ns"], dtype=np.int64)
    if gpx.size < 40:
        return float("nan")
    log_px = np.log(np.clip(gpx, 1e-12, None))
    try:
        t_u, r = returns_from_log_px(log_px, gts, time_unit_s=dt_s)
        tau_u = float(t_u[-1]) if t_u.size else float("nan")
        tm = (
            float(t_stat_side(t_u, r, tau_u, hn_s / dt_s, side="left"))
            if t_u.size > 10
            else float("nan")
        )
    except Exception:
        tm = float("nan")
    feats = {
        "Tm": tm if np.isfinite(tm) else 0.0,
        "abs_Tm": abs(tm) if np.isfinite(tm) else 0.0,
        "Tm_1m": 0.0,
        "V_lag": 0.0,
        "abs_V_lag": 0.0,
        "running_min_v": 0.0,
        "abs_running_min_v": 0.0,
        "breach": 1.0,
        "geom_near": 0.0,
        "log_intensity": float(np.log(max(int(m.sum()), 1))),
        "vpin_roll": 0.0,
        "hn5_dummy": 1.0,
    }
    score = 0.0
    for k, c in coefs.items():
        score += float(c) * float(feats.get(k, 0.0))
    return float(score)


def paper_throttle_state(
    *,
    breached: bool,
    cal_score: float | None,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Hypothetical Kill throttle knobs — observation / paper accounting ONLY."""
    th = cfg.get("throttle") or {}
    cal = cfg.get("calendar_ridge") or {}
    thresh = float(cal.get("cal_thresh_abs") or 0.0)
    score = float(cal_score) if cal_score is not None and np.isfinite(cal_score) else None
    cal_boost = bool(
        breached and score is not None and abs(score) >= thresh and thresh > 0
    )

    if not breached:
        hypo = {
            "active": False,
            "size_mult": 1.0,
            "widen_bps": 0.0,
            "pov": 1.0,
            "take_pause": False,
            "cal_boost": False,
        }
    elif cal_boost:
        hypo = {
            "active": True,
            "size_mult": float(cal.get("boost_size_mult") or 0.22),
            "widen_bps": float(cal.get("boost_widen_bps") or 8.0),
            "pov": float(cal.get("boost_pov") or 0.10),
            "take_pause": bool(th.get("take_pause", True)),
            "cal_boost": True,
        }
    else:
        hypo = {
            "active": True,
            "size_mult": float(th.get("size_mult") or 0.35),
            "widen_bps": float(th.get("widen_bps") or 5.0),
            "pov": float(th.get("pov") or 0.20),
            "take_pause": bool(th.get("take_pause", True)),
            "cal_boost": False,
        }

    return {
        "kind": "hypothetical",
        "label": "Kill/do-not-size",
        "gate": str(th.get("gate") or "Kill"),
        "gate_id": str(th.get("gate_id") or "exec.minv_breach_throttle"),
        "do_not_size": True,
        "alpha_claim": False,
        "deploy": False,
        "cal_join_gate": "Hold",
        "cal_join_gate_id": "exec.minv_throttle_cal_join",
        "as_alpha_gate": "Hold",
        "as_alpha_gate_id": "exec.minv_throttle_as_alpha",
        "breached": breached,
        "cal_score": score,
        "cal_thresh_abs": thresh,
        "hypothetical": hypo,
        "note": (
            "PAPER OBSERVATION ONLY — exec.minv_breach_throttle is Kill "
            "(adverse mo worsens). Do not soft-Promote. Do not size."
        ),
    }


def compute_venue_day(
    *,
    venue: str,
    symbol: str,
    day: str,
    cfg: dict[str, Any],
    tape_rec: dict[str, Any] | None = None,
    coefs: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Compute MinV/EGARCH rows + paper throttle state for one venue/day."""
    from _data import ensure_env, load_day_trades

    ensure_env()
    max_files = int(cfg.get("max_files") or 48)
    if tape_rec is None:
        tape_rec = load_day_trades(
            venue, symbol, day, max_files=max_files, quiet=True
        )
    tape = tape_rec["tape"]
    comp = tape_rec.get("completeness") or {}
    hn_list = [int(x) for x in (cfg.get("hn_min") or [1, 5, 30])]
    hn_primary = int(cfg.get("hn_primary_min") or 5)
    n_grid = int(cfg.get("n_grid") or 41)
    n_boot = int(cfg.get("n_boot") or 25)
    dt_s = float(cfg.get("dt_s") or 5.0)
    if coefs is None:
        coefs = load_cal_coefs(cfg)

    rows: list[dict[str, Any]] = []
    for hm in hn_list:
        try:
            out = _minv_hn(
                tape,
                float(hm * 60),
                n_grid=n_grid,
                n_boot=n_boot,
                dt_s=dt_s,
            )
        except Exception as exc:  # noqa: BLE001
            out = {"ok": False, "error": str(exc)}
        rows.append({"hn_min": hm, **out})

    primary = next((r for r in rows if r.get("hn_min") == hn_primary and r.get("ok")), None)
    if primary is None:
        primary = next((r for r in rows if r.get("ok")), None)

    breached = bool(primary and primary.get("sig_5"))
    tau = float(primary["tau_star_s"]) if primary and primary.get("tau_star_s") is not None else float("nan")
    cal_score = float("nan")
    if breached and coefs and np.isfinite(tau):
        try:
            cal_score = cal_score_at_trough(
                np.asarray(tape["ts"], dtype=np.int64),
                np.asarray(tape["px"], dtype=float),
                day=day,
                tau_s=tau,
                coefs=coefs,
                dt_s=dt_s,
            )
        except Exception:
            cal_score = float("nan")

    throttle = paper_throttle_state(
        breached=breached,
        cal_score=cal_score if np.isfinite(cal_score) else None,
        cfg=cfg,
    )

    return {
        "ok": True,
        "venue": venue,
        "symbol": symbol,
        "day": day,
        "complete": bool(comp.get("complete")),
        "n_trades": int(comp.get("n") or 0),
        "coverage": comp.get("coverage"),
        "hn_rows": rows,
        "primary_hn_min": hn_primary,
        "primary": primary,
        "breached": breached,
        "cal_score": float(cal_score) if np.isfinite(cal_score) else None,
        "cal_coefs_loaded": bool(coefs),
        "throttle_paper": throttle,
        "gates": dict(cfg.get("gates") or GATE_LABELS),
        "live_orders": False,
        "alpha_claim": False,
    }


def compute_day_monitors(
    *,
    cfg: dict[str, Any],
    day: str | None = None,
    venues: list[str] | None = None,
) -> dict[str, Any]:
    """Run monitors for primary (+ optional extra) venues on a warehouse day."""
    from _data import ensure_env

    ensure_env()
    venue = str(cfg.get("venue") or "hyperliquid").lower()
    symbol = str(cfg.get("symbol") or "ETH").upper()
    extras = [str(v).lower() for v in (cfg.get("extra_venues") or [])]
    if venues is None:
        venues = [venue] + [v for v in extras if v != venue]
    else:
        venues = [str(v).lower() for v in venues]

    from .shadow import find_latest_complete_day

    lookback = int(cfg.get("lookback_days") or 21)
    max_files = int(cfg.get("max_files") or 48)
    require_complete = bool(cfg.get("require_complete_day", True))

    found = None
    if day is None:
        found = find_latest_complete_day(
            venue,
            symbol,
            lookback=lookback,
            quiet=True,
            max_files=max_files,
        )
        day = str(found["day"])
        primary_rec = found.get("rec")
    else:
        primary_rec = None
        if require_complete:
            # still allow pinned incomplete days for replay, but flag them
            pass

    coefs = load_cal_coefs(cfg)
    per_venue: list[dict[str, Any]] = []
    for v in venues:
        try:
            rec = primary_rec if (v == venue and primary_rec is not None) else None
            cell = compute_venue_day(
                venue=v,
                symbol=symbol,
                day=day,
                cfg=cfg,
                tape_rec=rec,
                coefs=coefs,
            )
            per_venue.append(cell)
        except Exception as exc:  # noqa: BLE001
            per_venue.append(
                {
                    "ok": False,
                    "venue": v,
                    "symbol": symbol,
                    "day": day,
                    "error": f"{type(exc).__name__}: {exc}",
                    "live_orders": False,
                }
            )

    primary_cell = next((c for c in per_venue if c.get("venue") == venue), None)
    any_breach = any(bool(c.get("breached")) for c in per_venue if c.get("ok"))

    return {
        "ok": True,
        "day": day,
        "venue": venue,
        "symbol": symbol,
        "venues": venues,
        "primary": primary_cell,
        "per_venue": per_venue,
        "any_breach": any_breach,
        "cal_coefs_loaded": bool(coefs),
        "gates": dict(cfg.get("gates") or GATE_LABELS),
        "found": (
            {k: found[k] for k in ("day", "completeness", "probed") if k in found}
            if found
            else None
        ),
        "live_orders": False,
        "alpha_claim": False,
        "ts_utc": datetime.now(timezone.utc).isoformat(),
    }
