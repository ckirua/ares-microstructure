"""Shared panel + intensity helpers for RISK / EXEC application backtests.

Builds a day×symbol×venue event panel (SSM + Nanex + vol shares) once, then
feeds kill-ladder / burst / thin-SOR / H^v–FEI sims. No fantasy fills: outcomes
are tape ΔP, tape markout, recovery class, and venue-local counterfactuals.

ClickHouse MCP banned.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

BOOK = Path(__file__).resolve().parents[2]
ROOT = BOOK.parents[2]
STARTARB = Path("/home/dev/srv/ares-startarb")
WAREHOUSE_SRC = Path("/home/dev/lab/lab-n2070/warehouse/src")
APP = BOOK / "applications"
OUT = APP / "out"
PANEL_DIR = OUT / "event_panel"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(STARTARB / "src"))
sys.path.insert(0, str(WAREHOUSE_SRC))
sys.path.insert(0, str(BOOK / "scripts"))

from _data import (  # noqa: E402
    CORE_VENUES,
    ensure_env,
    load_core_venues_day,
)

# re-export for application scripts
__all_reexport = ("CORE_VENUES",)
from research.lib.crash import (  # noqa: E402
    classify_recovery,
    detect_ssm_events,
    event_overlap,
    kalman_ssm_filter,
    mc_garch_bar_vol,
    nanex_detect,
    post_event_markout_px,
    recovery_fraction,
    severity_gate,
    sigma_process_meas,
    volume_herfindahl,
)
from research.lib.fei import fei  # noqa: E402
from research.lib.stats import bootstrap_ci, time_split_mask  # noqa: E402

DEFAULT_DAYS = [
    "2026-09-04",
    "2026-09-05",
    "2026-09-06",
    "2026-09-07",
    "2026-09-08",
    "2026-09-09",
    "2026-09-10",
]
DEFAULT_SYMBOLS = ["ETH", "BTC"]
Z_STAR = 6.0
GATE_PRIMARY = {"min_dp_pct": 0.10, "min_i_c": 5}  # 10bps / ic5
GATE_DENSE = {"min_dp_pct": 0.05, "min_i_c": 3}  # 5bps / ic3
# Assumed one-way taker friction (bps) — honesty haircut, not a PnL claim
FRICTION_BPS = 2.0
NS = 1_000_000_000
# Empirical z_peak percentiles on gated set (filled after panel build; defaults ≈ slice)
GATED_Z_BREAKS = {"p25": 12.5, "p50": 15.9, "p75": 20.4}


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
    # bool is a subclass of int — must check before int
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if obj is None:
        return None
    return str(obj)


def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(obj), indent=2) + "\n")


def save_fig(path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=140, bbox_inches="tight")
    plt.close()


def tape_notional(tape: dict[str, np.ndarray], venue: str) -> float:
    px = np.asarray(tape["px"], dtype=np.float64)
    qty = np.asarray(tape["qty"], dtype=np.float64)
    m = np.isfinite(px) & np.isfinite(qty) & (qty > 0)
    if not m.any():
        return 0.0
    if str(venue).lower() == "deribit":
        return float(np.sum(qty[m]))
    m2 = m & (px > 0)
    return float(np.sum(px[m2] * qty[m2])) if m2.any() else 0.0


def ladder_tier(
    z_peak: float,
    *,
    intensity: int = 1,
    nanex_overlap: bool = False,
    dp_pct: float = 0.0,
    z_breaks: dict[str, float] | None = None,
    dp_p90: float = 0.45,
) -> str:
    """Map gated event → observe/widen/size_cap/halt.

    Paper z*=6 is the *detection* cut. On severity-gated crypto tape, peak |z|
    is typically ≫12, so absolute bands {8,10,12} collapse to halt. Desk ladder
    therefore uses **within-gated** z percentiles + intensity + Nanex nest.
    """
    zb = z_breaks or GATED_Z_BREAKS
    z = abs(float(z_peak)) if np.isfinite(z_peak) else 0.0
    inten = int(intensity)
    dp = abs(float(dp_pct)) if np.isfinite(dp_pct) else 0.0
    if (nanex_overlap and inten >= 2) or inten >= 5 or dp >= float(dp_p90):
        return "halt"
    if z >= float(zb["p75"]) or inten >= 3:
        return "size_cap"
    if z >= float(zb["p25"]) or inten == 2 or nanex_overlap:
        return "widen"
    return "observe"


def assign_ladder_tiers(events: list[dict[str, Any]]) -> dict[str, float]:
    """In-place tier assignment using empirical gated z / dp breaks; return breaks."""
    zs = np.asarray(
        [abs(float(e["z_peak"])) for e in events if np.isfinite(e.get("z_peak", np.nan))],
        dtype=np.float64,
    )
    dps = np.asarray(
        [abs(float(e["dp_pct"])) for e in events if np.isfinite(e.get("dp_pct", np.nan))],
        dtype=np.float64,
    )
    breaks = {
        "p25": float(np.nanpercentile(zs, 25)) if zs.size else GATED_Z_BREAKS["p25"],
        "p50": float(np.nanpercentile(zs, 50)) if zs.size else GATED_Z_BREAKS["p50"],
        "p75": float(np.nanpercentile(zs, 75)) if zs.size else GATED_Z_BREAKS["p75"],
    }
    dp_p90 = float(np.nanpercentile(dps, 90)) if dps.size else 0.45
    GATED_Z_BREAKS.update(breaks)
    for e in events:
        e["tier"] = ladder_tier(
            float(e["z_peak"]),
            intensity=int(e.get("intensity_60s") or 1),
            nanex_overlap=bool(e.get("nanex_overlap")),
            dp_pct=float(e.get("dp_pct") or 0.0),
            z_breaks=breaks,
            dp_p90=dp_p90,
        )
    return {**breaks, "dp_p90": dp_p90}


def _attach_nanex_ts(nanex: dict[str, Any], ts: np.ndarray) -> dict[str, Any]:
    n = int(nanex["n_events"])
    ts_s = np.zeros(n, dtype=np.int64)
    ts_e = np.zeros(n, dtype=np.int64)
    for k in range(n):
        a, b = int(nanex["start_i"][k]), int(nanex["end_i"][k])
        ts_s[k], ts_e[k] = int(ts[a]), int(ts[b])
    return {**nanex, "ts_start": ts_s, "ts_end": ts_e, "i_c": nanex["n_trades"]}


def detect_venue_day(
    tape: dict[str, np.ndarray],
    *,
    sigma_m_frac: float = 1.0,
    z_star: float = Z_STAR,
) -> dict[str, Any]:
    """SSM + Nanex + recovery/markout on one clipped tape."""
    ts = np.asarray(tape["ts"], dtype=np.int64)
    px = np.asarray(tape["px"], dtype=np.float64)
    out: dict[str, Any] = {"n_trades": int(ts.size)}
    if ts.size < 200 or not np.isfinite(px).any():
        out["skip"] = "thin_tape"
        return out
    log_px = np.log(np.where(px > 0, px, np.nan))
    mcg = mc_garch_bar_vol(ts, px)
    sig = sigma_process_meas(ts, mcg, sigma_m_frac=sigma_m_frac, log_px=log_px)
    filt = kalman_ssm_filter(ts, px, sig["sigma_p2_dt"], sig["sigma_m2"])
    ssm_raw = detect_ssm_events(ts, px, filt, z_star=z_star)
    ssm_10 = severity_gate(ssm_raw, **GATE_PRIMARY)
    ssm_5 = severity_gate(ssm_raw, **GATE_DENSE)
    nanex = _attach_nanex_ts(
        nanex_detect(ts, px, min_trades=10, max_window_s=1.5, min_pct=0.003, use_trade_count=True),
        ts,
    )
    # recovery / markout on primary gate
    rec = recovery_fraction(
        ts, px, ssm_10["start_i"], ssm_10["end_i"], ssm_10["direction"], horizon_s=5.0
    )
    cls = classify_recovery(rec)
    mo = post_event_markout_px(ts, px, ssm_10["end_i"], ssm_10["direction"])
    # per-event markout arrays @1s / @5s
    mo1, mo5 = _per_event_markout(ts, px, ssm_10["end_i"], ssm_10["direction"], (1.0, 5.0))
    # Nanex ∩ SSM (index overlap on same tape)
    nest = event_overlap(
        nanex["start_i"],
        nanex["end_i"],
        ssm_raw["start_i"],
        ssm_raw["end_i"],
        ts,
        slack_s=0.5,
    )
    nested_mask = _nanex_nested_in_ssm(nanex, ssm_raw, ts, slack_s=0.5)
    out.update(
        {
            "ts": ts,
            "px": px,
            "sigma_m_median": float(np.nanmedian(sig["sigma_m"])) if "sigma_m" in sig else None,
            "sigma_m_floor_hit": bool(
                np.nanmin(sig.get("sigma_m", np.array([np.nan]))) <= 1.01e-4
            )
            if "sigma_m" in sig
            else None,
            "ssm_raw": ssm_raw,
            "ssm_10bps": ssm_10,
            "ssm_5bps": ssm_5,
            "nanex": nanex,
            "recovery": rec,
            "recovery_class": cls,
            "markout_summary": mo,
            "markout_1s": mo1,
            "markout_5s": mo5,
            "nanex_ssm_nest": nest,
            "nanex_nested_mask": nested_mask,
            "z_score": filt["z_score"],
        }
    )
    return out


def _per_event_markout(
    ts: np.ndarray,
    px: np.ndarray,
    end_i: np.ndarray,
    direction: np.ndarray,
    horizons: tuple[float, ...],
) -> tuple[np.ndarray, ...]:
    outs = []
    for h in horizons:
        h_ns = int(h * NS)
        arr = np.full(end_i.shape, np.nan, dtype=np.float64)
        for k in range(end_i.size):
            b = int(end_i[k])
            if b < 0 or b >= px.size or px[b] <= 0 or direction[k] == 0:
                continue
            j = int(np.searchsorted(ts, ts[b] + h_ns, side="right") - 1)
            if j <= b or j >= px.size or not np.isfinite(px[j]):
                continue
            arr[k] = float(direction[k] * (px[j] - px[b]) / px[b] * 1e4)
        outs.append(arr)
    return tuple(outs)


def _nanex_nested_in_ssm(
    nanex: dict[str, Any],
    ssm: dict[str, Any],
    ts: np.ndarray,
    *,
    slack_s: float = 0.5,
) -> np.ndarray:
    """Boolean mask: each Nanex event overlaps some SSM event."""
    n = int(nanex["n_events"])
    mask = np.zeros(n, dtype=bool)
    if n == 0 or int(ssm.get("n_events", 0)) == 0:
        return mask
    slack = int(slack_s * NS)
    a_s, a_e = nanex["start_i"], nanex["end_i"]
    b_s, b_e = ssm["start_i"], ssm["end_i"]
    for i in range(n):
        ta0, ta1 = int(ts[a_s[i]]), int(ts[a_e[i]])
        for j in range(int(ssm["n_events"])):
            tb0, tb1 = int(ts[b_s[j]]), int(ts[b_e[j]])
            if ta0 <= tb1 + slack and tb0 <= ta1 + slack:
                mask[i] = True
                break
    return mask


def subsequent_abs_dp(
    ts: np.ndarray,
    px: np.ndarray,
    end_i: np.ndarray,
    *,
    horizon_s: float = 30.0,
) -> np.ndarray:
    """Max |ΔP| (%) from event end over next horizon_s (continuation severity)."""
    out = np.full(end_i.shape, np.nan, dtype=np.float64)
    h_ns = int(horizon_s * NS)
    for k in range(end_i.size):
        b = int(end_i[k])
        if b < 0 or b >= px.size or px[b] <= 0:
            continue
        j = int(np.searchsorted(ts, ts[b] + h_ns, side="right") - 1)
        if j <= b:
            out[k] = 0.0
            continue
        seg = px[b : j + 1]
        if not np.isfinite(seg).any():
            continue
        out[k] = float(np.nanmax(np.abs(seg - px[b]) / px[b]) * 100.0)
    return out


def rolling_gated_intensity(
    ts_start: np.ndarray,
    *,
    window_s: float = 60.0,
) -> np.ndarray:
    """Count of gated events whose start falls in (t−W, t] for each event."""
    t = np.asarray(ts_start, dtype=np.int64)
    w = int(window_s * NS)
    out = np.zeros(t.size, dtype=np.int64)
    for i in range(t.size):
        out[i] = int(np.sum((t <= t[i]) & (t > t[i] - w)))
    return out


def early_late_by_day(days: list[str]) -> tuple[set[str], set[str]]:
    ds = sorted(days)
    mid = len(ds) // 2
    return set(ds[:mid]), set(ds[mid:])


def mean_ci(arr: np.ndarray, *, n_boot: int = 800, seed: int = 0) -> dict[str, float]:
    return bootstrap_ci(np.asarray(arr, dtype=np.float64), n_boot=n_boot, seed=seed)


def effect_delta_ci(
    treat: np.ndarray,
    control: np.ndarray,
    *,
    n_boot: int = 800,
    seed: int = 1,
) -> dict[str, float]:
    """Bootstrap CI on mean(treat) − mean(control)."""
    a = np.asarray(treat, dtype=np.float64)
    b = np.asarray(control, dtype=np.float64)
    a = a[np.isfinite(a)]
    b = b[np.isfinite(b)]
    if a.size == 0 or b.size == 0:
        return {
            "n_treat": int(a.size),
            "n_control": int(b.size),
            "delta": float("nan"),
            "lo": float("nan"),
            "hi": float("nan"),
        }
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot, dtype=np.float64)
    for i in range(n_boot):
        sa = a[rng.integers(0, a.size, size=a.size)]
        sb = b[rng.integers(0, b.size, size=b.size)]
        boots[i] = float(sa.mean() - sb.mean())
    lo, hi = np.quantile(boots, [0.025, 0.975])
    return {
        "n_treat": int(a.size),
        "n_control": int(b.size),
        "delta": float(a.mean() - b.mean()),
        "lo": float(lo),
        "hi": float(hi),
        "treat_mean": float(a.mean()),
        "control_mean": float(b.mean()),
    }


def placebo_windows(
    ts: np.ndarray,
    px: np.ndarray,
    n: int,
    *,
    seed: int = 42,
    span_s: float = 1.0,
) -> dict[str, Any]:
    """Random tape windows as null regime (no SSM gate)."""
    rng = np.random.default_rng(seed)
    if ts.size < 50 or n <= 0:
        return {
            "n": 0,
            "dp_pct": np.zeros(0),
            "mo_5s": np.zeros(0),
            "sub_dp": np.zeros(0),
        }
    span = int(span_s * NS)
    starts = rng.integers(0, max(ts.size - 10, 1), size=n)
    dp = np.full(n, np.nan)
    mo = np.full(n, np.nan)
    sub = np.full(n, np.nan)
    for k, a in enumerate(starts):
        a = int(a)
        if px[a] <= 0 or not np.isfinite(px[a]):
            continue
        b = int(np.searchsorted(ts, ts[a] + span, side="right") - 1)
        b = max(b, a)
        seg = px[a : b + 1]
        dp[k] = float(np.nanmax(np.abs(seg - px[a]) / px[a]) * 100.0)
        j = int(np.searchsorted(ts, ts[b] + 5 * NS, side="right") - 1)
        if j > b and px[b] > 0:
            mo[k] = float((px[j] - px[b]) / px[b] * 1e4)  # unsigned null
        j2 = int(np.searchsorted(ts, ts[b] + 30 * NS, side="right") - 1)
        if j2 > b and px[b] > 0:
            sub[k] = float(np.nanmax(np.abs(px[b : j2 + 1] - px[b]) / px[b]) * 100.0)
    return {"n": int(n), "dp_pct": dp, "mo_5s": mo, "sub_dp": sub}


def build_event_panel(
    *,
    days: list[str] | None = None,
    symbols: list[str] | None = None,
    venues: tuple[str, ...] = CORE_VENUES,
    force: bool = False,
    quiet: bool = True,
) -> dict[str, Any]:
    """Load / cache day×symbol×venue detections + USD vol shares."""
    days = list(days or DEFAULT_DAYS)
    symbols = list(symbols or DEFAULT_SYMBOLS)
    meta_path = PANEL_DIR / "panel_meta.json"
    rows_path = PANEL_DIR / "panel_rows.json"
    if not force and meta_path.exists() and rows_path.exists():
        meta = json.loads(meta_path.read_text())
        if meta.get("days") == days and meta.get("symbols") == symbols:
            rows = json.loads(rows_path.read_text())
            return {"meta": meta, "rows": rows, "cached": True}

    ensure_env()
    rows: list[dict[str, Any]] = []
    for day in days:
        for sym in symbols:
            pack = load_core_venues_day(sym, day, venues=venues, quiet=quiet)
            vols: dict[str, float] = {}
            for v, rec in pack["venues"].items():
                if "error" in rec or not rec.get("completeness", {}).get("complete"):
                    continue
                vols[v] = tape_notional(rec["tape"], v)
            hv = volume_herfindahl(vols, keys=list(venues))
            fei_v = (
                float(fei([hv["shares"].get(v, 0.0) for v in venues], n_pools=len(venues)))
                if hv["complete"]
                else float("nan")
            )
            thin_venue = (
                min(hv["shares"], key=hv["shares"].get) if hv["complete"] and hv["shares"] else None
            )
            for v, rec in pack["venues"].items():
                if "error" in rec:
                    rows.append(
                        {
                            "day": day,
                            "symbol": sym,
                            "venue": v,
                            "skip": rec.get("error"),
                            "complete": False,
                        }
                    )
                    continue
                det = detect_venue_day(rec["tape"])
                if det.get("skip"):
                    rows.append(
                        {
                            "day": day,
                            "symbol": sym,
                            "venue": v,
                            "skip": det["skip"],
                            "complete": bool(rec.get("completeness", {}).get("complete")),
                            "n_trades": det.get("n_trades", 0),
                        }
                    )
                    continue
                s10 = det["ssm_10bps"]
                n_ev = int(s10["n_events"])
                intens = rolling_gated_intensity(s10["ts_start"], window_s=60.0)
                sub_dp = subsequent_abs_dp(det["ts"], det["px"], s10["end_i"], horizon_s=30.0)
                nx = det["nanex"]
                # provisional tiers; kill_ladder reassigns with pooled gated percentiles
                ssm_has_nanex = _ssm_has_nanex_overlap(s10, nx, det["ts"], slack_s=0.5)
                tiers = [
                    ladder_tier(
                        float(z),
                        intensity=int(intens[i]),
                        nanex_overlap=bool(ssm_has_nanex[i]),
                        dp_pct=float(s10["dp_pct"][i]),
                    )
                    for i, z in enumerate(np.asarray(s10["z_peak"], dtype=np.float64))
                ]
                row = {
                    "day": day,
                    "symbol": sym,
                    "venue": v,
                    "complete": bool(rec.get("completeness", {}).get("complete")),
                    "n_trades": int(det["n_trades"]),
                    "vol_usd": float(vols.get(v, 0.0)),
                    "vol_shares": hv["shares"],
                    "H_v": hv["H_v"],
                    "FEI": fei_v,
                    "thin_venue": thin_venue,
                    "thin_excess": (
                        float(
                            # crash share filled later at pool level; store vol share for now
                            -hv["shares"].get(v, float("nan"))
                        )
                        if thin_venue == v
                        else None
                    ),
                    "ssm_raw_n": int(det["ssm_raw"]["n_events"]),
                    "ssm_10_n": n_ev,
                    "ssm_5_n": int(det["ssm_5bps"]["n_events"]),
                    "nanex_n": int(nx["n_events"]),
                    "nanex_nested_n": int(det["nanex_nested_mask"].sum()),
                    "nanex_ssm_precision": det["nanex_ssm_nest"].get("precision_a"),
                    "sigma_m_median": det.get("sigma_m_median"),
                    "events": {
                        "ts_start": s10["ts_start"].tolist(),
                        "ts_end": s10["ts_end"].tolist(),
                        "dp_pct": s10["dp_pct"].tolist(),
                        "i_c": s10["i_c"].tolist(),
                        "dt_s": s10["dt_s"].tolist(),
                        "direction": s10["direction"].tolist(),
                        "z_peak": s10["z_peak"].tolist(),
                        "intensity_60s": intens.tolist(),
                        "tier": tiers,
                        "recovery": det["recovery"].tolist(),
                        "recovery_label": det["recovery_class"]["labels"].tolist(),
                        "mo_1s": det["markout_1s"].tolist(),
                        "mo_5s": det["markout_5s"].tolist(),
                        "sub_dp_30s": sub_dp.tolist(),
                        "nanex_overlap": ssm_has_nanex.tolist(),
                    },
                    "nanex_events": {
                        "ts_start": nx["ts_start"].tolist(),
                        "ts_end": nx["ts_end"].tolist(),
                        "dp_pct": nx["dp_pct"].tolist(),
                        "nested": det["nanex_nested_mask"].tolist(),
                    },
                    "placebo": placebo_windows(
                        det["ts"], det["px"], max(n_ev, 5), seed=hash((day, sym, v)) % (2**31)
                    ),
                    # keep light tape stats for SOR counterfactuals (not full tape)
                    "tape_summary": {
                        "n": int(det["ts"].size),
                        "t0": int(det["ts"][0]) if det["ts"].size else None,
                        "t1": int(det["ts"][-1]) if det["ts"].size else None,
                        "px0": float(det["px"][0]) if det["px"].size else None,
                        "px1": float(det["px"][-1]) if det["px"].size else None,
                    },
                }
                # serialize placebo arrays
                row["placebo"] = {
                    "n": row["placebo"]["n"],
                    "dp_pct": row["placebo"]["dp_pct"].tolist(),
                    "mo_5s": row["placebo"]["mo_5s"].tolist(),
                    "sub_dp": row["placebo"]["sub_dp"].tolist(),
                }
                rows.append(row)

    # fill crash shares + thin excess per day×symbol
    for day in days:
        for sym in symbols:
            cell = [r for r in rows if r.get("day") == day and r.get("symbol") == sym and "events" in r]
            if not cell:
                continue
            counts = {r["venue"]: int(r["ssm_10_n"]) for r in cell}
            tot = sum(counts.values()) or 1
            crash_shares = {v: counts.get(v, 0) / tot for v in venues}
            vol_shares = cell[0].get("vol_shares") or {}
            thin = cell[0].get("thin_venue")
            for r in cell:
                r["crash_shares"] = crash_shares
                r["crash_share"] = crash_shares.get(r["venue"], float("nan"))
                vs = float(vol_shares.get(r["venue"], float("nan")))
                cs = float(crash_shares.get(r["venue"], float("nan")))
                r["excess"] = cs - vs if np.isfinite(cs) and np.isfinite(vs) else float("nan")
                if thin and r["venue"] == thin:
                    r["thin_excess"] = r["excess"]

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days": days,
        "symbols": symbols,
        "venues": list(venues),
        "gate": GATE_PRIMARY,
        "z_star": Z_STAR,
        "ladder": "within-gated z percentiles + intensity + Nanex nest (see assign_ladder_tiers)",
        "friction_bps": FRICTION_BPS,
        "n_rows": len(rows),
    }
    save_json(meta_path, meta)
    save_json(rows_path, rows)
    return {"meta": meta, "rows": rows, "cached": False}


def _ssm_has_nanex_overlap(
    ssm: dict[str, Any],
    nanex: dict[str, Any],
    ts: np.ndarray,
    *,
    slack_s: float = 0.5,
) -> np.ndarray:
    n = int(ssm["n_events"])
    mask = np.zeros(n, dtype=bool)
    if n == 0 or int(nanex.get("n_events", 0)) == 0:
        return mask
    slack = int(slack_s * NS)
    for i in range(n):
        ta0, ta1 = int(ssm["ts_start"][i]), int(ssm["ts_end"][i])
        for j in range(int(nanex["n_events"])):
            tb0, tb1 = int(nanex["ts_start"][j]), int(nanex["ts_end"][j])
            if ta0 <= tb1 + slack and tb0 <= ta1 + slack:
                mask[i] = True
                break
    return mask


def flatten_events(rows: list[dict[str, Any]], *, venue: str | None = None) -> list[dict[str, Any]]:
    """One dict per gated SSM event with cell metadata."""
    out: list[dict[str, Any]] = []
    for r in rows:
        if "events" not in r:
            continue
        if venue and r.get("venue") != venue:
            continue
        ev = r["events"]
        n = len(ev["dp_pct"])
        for i in range(n):
            out.append(
                {
                    "day": r["day"],
                    "symbol": r["symbol"],
                    "venue": r["venue"],
                    "H_v": r.get("H_v"),
                    "FEI": r.get("FEI"),
                    "vol_share": (r.get("vol_shares") or {}).get(r["venue"]),
                    "crash_share": r.get("crash_share"),
                    "excess": r.get("excess"),
                    "thin_venue": r.get("thin_venue"),
                    "thin_excess": r.get("thin_excess"),
                    "dp_pct": ev["dp_pct"][i],
                    "z_peak": ev["z_peak"][i],
                    "tier": ev["tier"][i],
                    "intensity_60s": ev["intensity_60s"][i],
                    "recovery": ev["recovery"][i],
                    "recovery_label": ev["recovery_label"][i],
                    "mo_1s": ev["mo_1s"][i],
                    "mo_5s": ev["mo_5s"][i],
                    "sub_dp_30s": ev["sub_dp_30s"][i],
                    "nanex_overlap": ev["nanex_overlap"][i],
                    "ts_start": ev["ts_start"][i],
                    "ts_end": ev["ts_end"][i],
                    "i_c": ev["i_c"][i],
                    "dt_s": ev["dt_s"][i],
                    "direction": ev["direction"][i],
                }
            )
    return out


def readiness_label(
    *,
    effect_ci_excludes_zero: bool,
    time_split_sign_stable: bool,
    n_events: int,
    friction_cleared: bool,
    monitor_ok: bool = True,
) -> str:
    """monitor | executable_rule_candidate | hold_rule | kill_rule."""
    if not monitor_ok:
        return "kill_as_rule"
    if n_events < 30:
        return "monitor_only_underpowered"
    if effect_ci_excludes_zero and time_split_sign_stable and friction_cleared:
        return "promote_as_risk_policy"
    if effect_ci_excludes_zero and time_split_sign_stable:
        return "executable_rule_candidate_net_friction"
    if monitor_ok:
        return "monitor_only"
    return "hold_rule"
