#!/usr/bin/env python3
"""Pass-2b info dig for squeeze_metrics (cd_me Pass-2.5 quality).

Certified ``panel_gex_options`` day GEX/VEX panel + HL/Deribit marks for:
  - day-scale lead-lag (GEX/VEX/squeeze → range/RV/next mid-return)
  - intraday markout profiles stratified by scarce / high-squeeze / |GEX| stress
  - incremental: GEX after RV; squeeze after GEX; VEX incremental
  - ToD factor structure on HL mid-returns / RV / spread by regime
  - stress vs calm splits
  - explicit info.* candidates + APPLICATIONS use map

Writes ``out/info_features/`` JSON + figs + EXP_REPORT.
Never soft-Promote TOB-cross α. ClickHouse MCP banned.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
SCRIPTS = Path(__file__).resolve().parent
for _p in (
    str(Path(os.environ.get("WAREHOUSE_SRC") or (Path.home() / "lab" / "lab-n2070" / "warehouse" / "src"))),
    str((Path(os.environ.get("ARES_STARTARB") or (Path.home() / "srv" / "ares-startarb")) / "src")),
    str(ROOT),
    str(SCRIPTS),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from _data import ensure_env, load_day_marks, load_venue_tob  # noqa: E402
from _stats_info import (  # noqa: E402
    day_block_bootstrap_corr,
    fisher_z_normal_posterior,
    lead_lag_corr,
    ols_incremental,
    partial_corr,
    pca_commonality,
    pearson_spearman,
    tod_profile,
    univariate_moments,
)
from certified_panel import gex_panel_days, load_certified, spot_l2_days  # noqa: E402
from research.lib.squeeze import mid_range, realized_vol  # noqa: E402

OUT = BOOK / "out" / "info_features"
FIGS = OUT / "figs"
GEX_ROWS = BOOK / "out" / "gex_implied_book" / "panel_rows.json"
GEX_SUM = BOOK / "out" / "gex_implied_book" / "summary.json"
N_BOOT = 400
SEED = 42
LAGS = (-3, -2, -1, 0, 1, 2, 3)
NS_PER_H = 3_600_000_000_000


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.floating, float)):
        x = float(obj)
        return x if np.isfinite(x) else None
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, np.ndarray):
        return _jsonable(obj.tolist())
    return obj


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(obj), indent=2))


def _savefig(fig: plt.Figure, name: str) -> str:
    FIGS.mkdir(parents=True, exist_ok=True)
    path = FIGS / name
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return str(path.relative_to(BOOK))


def _load_rows(primary: list[str]) -> list[dict[str, Any]]:
    if GEX_ROWS.is_file():
        rows = json.loads(GEX_ROWS.read_text())
    elif GEX_SUM.is_file():
        rows = [r for r in json.loads(GEX_SUM.read_text()).get("rows") or [] if r.get("ok")]
    else:
        return []
    prim = set(primary)
    out = [r for r in rows if r.get("ok") and (not prim or str(r.get("day")) in prim)]
    return sorted(out, key=lambda r: str(r["day"]))


def _arr(rows: list[dict[str, Any]], key: str) -> np.ndarray:
    return np.asarray([r.get(key) for r in rows], dtype=np.float64)


def _hourly_from_tob(symbol: str, day: str) -> dict[str, Any]:
    """Build hourly mid_ret / RV / spread / range from HL TOB (fallback marks)."""
    empty = {
        "ok": False,
        "day": day,
        "hour_utc": [],
        "mid": [],
        "mid_ret": [],
        "rv": [],
        "spread_bps": [],
        "range_1h": [],
        "n": 0,
    }
    source = "warehouse_tob"
    try:
        # Prefer warehouse real quotes (collector archive only covers a subset of days).
        tob = load_venue_tob("hyperliquid", symbol, day=day, prefer_warehouse=True)
        source = str(tob.get("source") or "warehouse_tob")
    except Exception as exc:  # noqa: BLE001
        empty["error"] = f"{type(exc).__name__}: {exc}"
        return empty
    ts = np.asarray(tob.get("ts"), dtype=np.int64) if tob.get("ts") is not None else np.asarray([], dtype=np.int64)
    mid = np.asarray(tob.get("mid"), dtype=np.float64) if tob.get("mid") is not None else np.asarray([])
    bid = np.asarray(tob.get("bid"), dtype=np.float64) if tob.get("bid") is not None else np.full_like(mid, np.nan)
    ask = np.asarray(tob.get("ask"), dtype=np.float64) if tob.get("ask") is not None else np.full_like(mid, np.nan)
    if mid.size < 10 or ts.size != mid.size:
        # fallback marks (1m bars) — still real quotes, never trade_synth
        try:
            marks = load_day_marks("hyperliquid", symbol, day)
            ts = np.asarray(marks.get("ts"), dtype=np.int64)
            mid = np.asarray(
                marks.get("mid") if marks.get("mid") is not None else marks.get("price"),
                dtype=np.float64,
            )
            bid = ask = np.full_like(mid, np.nan)
            source = f"marks:{marks.get('source') or 'mark_bars'}"
        except Exception as exc:  # noqa: BLE001
            empty["error"] = f"marks_fail:{type(exc).__name__}:{exc}"
            return empty
    m = np.isfinite(mid) & (mid > 0) & np.isfinite(ts)
    ts, mid = ts[m], mid[m]
    if bid.size == m.size:
        bid, ask = bid[m], ask[m]
    if mid.size < 10:
        empty["error"] = "thin_mid"
        return empty
    # hour bins
    hour = (ts // NS_PER_H) % 24
    hours, mids, rets, rvs, spreads, ranges = [], [], [], [], [], []
    for h in range(24):
        sel = hour == h
        if int(sel.sum()) < 2:
            continue
        mh = mid[sel]
        hours.append(h)
        mids.append(float(np.nanmedian(mh)))
        # within-hour RV / range
        rvs.append(float(realized_vol(mh, dt_s=60.0, annualize=False)) if mh.size > 3 else float("nan"))
        ranges.append(float(mid_range(mh)))
        if np.isfinite(bid).any() and np.isfinite(ask).any():
            sp = (ask[sel] - bid[sel]) / np.clip(mh, 1e-12, None) * 1e4
            spreads.append(float(np.nanmedian(sp[np.isfinite(sp)])) if np.isfinite(sp).any() else float("nan"))
        else:
            spreads.append(float("nan"))
    mids_a = np.asarray(mids, dtype=np.float64)
    rets_a = np.full(mids_a.size, np.nan)
    for i in range(1, mids_a.size):
        if mids_a[i - 1] > 0 and np.isfinite(mids_a[i]) and np.isfinite(mids_a[i - 1]):
            rets_a[i] = float(np.log(mids_a[i] / mids_a[i - 1]))
    return {
        "ok": True,
        "day": day,
        "source": source,
        "hour_utc": hours,
        "mid": mids_a.tolist(),
        "mid_ret": rets_a.tolist(),
        "rv": rvs,
        "spread_bps": spreads,
        "range_1h": ranges,
        "n": int(len(hours)),
        "n_raw": int(mid.size),
        "day_mid_ret": float(np.log(mids_a[-1] / mids_a[0])) if mids_a.size >= 2 and mids_a[0] > 0 else float("nan"),
        "day_rv_from_hourly": float(np.nanstd(rets_a) * np.sqrt(np.isfinite(rets_a).sum())) if np.isfinite(rets_a).sum() > 2 else float("nan"),
    }


def _regimes(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    gex = _arr(rows, "gex")
    gp = _arr(rows, "gex_plus")
    sq = _arr(rows, "squeeze_intensity")
    med_abs = float(np.nanmedian(np.abs(gex))) if gex.size else 0.0
    med_sq = float(np.nanmedian(sq)) if sq.size else 0.0
    scarce = [str(r["day"]) for r in rows if r.get("scarce")]
    stress = [str(r["day"]) for r, g in zip(rows, gex) if np.isfinite(g) and abs(g) >= med_abs]
    calm = [str(r["day"]) for r, g in zip(rows, gex) if np.isfinite(g) and abs(g) < med_abs]
    high_sq = [str(r["day"]) for r, s in zip(rows, sq) if np.isfinite(s) and s >= med_sq]
    low_gp = [str(r["day"]) for r, g in zip(rows, gp) if np.isfinite(g) and g <= 0]
    return {
        "scarce": scarce,
        "stress_abs_gex": stress,
        "calm_abs_gex": calm,
        "high_squeeze": high_sq,
        "gex_plus_le_0": low_gp,
        "med_abs_gex": med_abs,  # type: ignore[dict-item]
        "med_squeeze": med_sq,  # type: ignore[dict-item]
    }


def _leadlag_day(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    carriers = ("gex", "vex", "gex_plus", "squeeze_intensity")
    targets = ("hl_rv", "hl_range", "db_rv", "db_range")
    for c in carriers:
        x = _arr(rows, c)
        for t in targets:
            y = _arr(rows, t)
            # day-scale: use lead_lag_corr but with min_n lowered via manual
            lags, corrs, ns = [], [], []
            for lag in LAGS:
                if lag == 0:
                    a, b = x, y
                elif lag > 0:
                    a, b = x[:-lag], y[lag:]
                else:
                    s = -lag
                    a, b = x[s:], y[:-s]
                m = np.isfinite(a) & np.isfinite(b)
                n = int(m.sum())
                r = float(np.corrcoef(a[m], b[m])[0, 1]) if n >= 3 else float("nan")
                lags.append(int(lag))
                corrs.append(r)
                ns.append(n)
            best_i = int(np.nanargmax(np.abs(corrs))) if any(np.isfinite(corrs)) else 0
            out[f"{c}->{t}"] = {
                "lags": lags,
                "corr": corrs,
                "n": ns,
                "best_lag": lags[best_i],
                "best_corr": corrs[best_i],
            }
    # next-day mid return from hourly packs attached later — placeholder filled in main
    return out


def _incremental(rows: list[dict[str, Any]]) -> dict[str, Any]:
    gex = _arr(rows, "gex")
    vex = _arr(rows, "vex")
    gp = _arr(rows, "gex_plus")
    sq = _arr(rows, "squeeze_intensity")
    rng = _arr(rows, "hl_range")
    rv = _arr(rows, "hl_rv")
    incr = {
        "partial_range_gex_ctrl_rv": partial_corr(rng, gex, rv),
        "partial_range_vex_ctrl_rv": partial_corr(rng, vex, rv),
        "partial_range_gexplus_ctrl_rv": partial_corr(rng, gp, rv),
        "partial_rv_gex_ctrl_range": partial_corr(rv, gex, rng),
        "partial_range_squeeze_ctrl_gex": partial_corr(rng, sq, gex),
        "partial_rv_squeeze_ctrl_gex": partial_corr(rv, sq, gex),
        "partial_range_vex_ctrl_gex": partial_corr(rng, vex, gex),
        "ols_range_on_rv": ols_incremental(rng, rv.reshape(-1, 1), names=["rv"]),
        "ols_range_on_rv_gex": ols_incremental(rng, np.column_stack([rv, gex]), names=["rv", "gex"]),
        "ols_range_on_rv_gex_vex": ols_incremental(
            rng, np.column_stack([rv, gex, vex]), names=["rv", "gex", "vex"]
        ),
        "ols_range_on_gex_squeeze": ols_incremental(
            rng, np.column_stack([gex, sq]), names=["gex", "squeeze"]
        ),
        "raw_corr_gex_rv": pearson_spearman(gex, rv),
        "raw_corr_gex_range": pearson_spearman(gex, rng),
        "raw_corr_vex_range": pearson_spearman(vex, rng),
        "raw_corr_squeeze_rv": pearson_spearman(sq, rv),
    }
    r2_rv = incr["ols_range_on_rv"].get("r2")
    r2_rv_gex = incr["ols_range_on_rv_gex"].get("r2")
    r2_rv_gex_vex = incr["ols_range_on_rv_gex_vex"].get("r2")
    incr["delta_r2_gex_after_rv"] = (
        float(r2_rv_gex - r2_rv) if np.isfinite(r2_rv) and np.isfinite(r2_rv_gex) else float("nan")
    )
    incr["delta_r2_vex_after_rv_gex"] = (
        float(r2_rv_gex_vex - r2_rv_gex)
        if np.isfinite(r2_rv_gex) and np.isfinite(r2_rv_gex_vex)
        else float("nan")
    )
    # squeeze after GEX for range
    r2_gex = ols_incremental(rng, gex.reshape(-1, 1), names=["gex"]).get("r2")
    r2_gex_sq = incr["ols_range_on_gex_squeeze"].get("r2")
    incr["delta_r2_squeeze_after_gex"] = (
        float(r2_gex_sq - r2_gex) if np.isfinite(r2_gex) and np.isfinite(r2_gex_sq) else float("nan")
    )
    return incr


def _stress_calm(rows: list[dict[str, Any]], regimes: dict[str, Any]) -> dict[str, Any]:
    by = {
        "stress": [r for r in rows if str(r["day"]) in set(regimes.get("stress_abs_gex") or [])],
        "calm": [r for r in rows if str(r["day"]) in set(regimes.get("calm_abs_gex") or [])],
        "scarce": [r for r in rows if str(r["day"]) in set(regimes.get("scarce") or [])],
        "abundant": [r for r in rows if not r.get("scarce")],
        "high_squeeze": [r for r in rows if str(r["day"]) in set(regimes.get("high_squeeze") or [])],
    }
    out: dict[str, Any] = {}
    for label, sub in by.items():
        if len(sub) < 3:
            out[label] = {"ok": False, "n": len(sub), "days": [r["day"] for r in sub]}
            continue
        out[label] = {
            "ok": True,
            "n": len(sub),
            "days": [r["day"] for r in sub],
            "corr_gex_hl_rv": pearson_spearman(_arr(sub, "gex"), _arr(sub, "hl_rv")),
            "corr_gex_hl_range": pearson_spearman(_arr(sub, "gex"), _arr(sub, "hl_range")),
            "corr_vex_hl_range": pearson_spearman(_arr(sub, "vex"), _arr(sub, "hl_range")),
            "mean_hl_rv": float(np.nanmean(_arr(sub, "hl_rv"))),
            "mean_hl_range": float(np.nanmean(_arr(sub, "hl_range"))),
            "mean_spread_proxy_range": float(np.nanmean(_arr(sub, "hl_range"))),
        }
    return out


def _tod_factor(hourly: list[dict[str, Any]], regimes: dict[str, Any]) -> dict[str, Any]:
    """Pool hourly mid_ret/RV/spread; ToD profiles by regime; day×hour PCA."""
    stress_days = set(regimes.get("stress_abs_gex") or [])
    scarce_days = set(regimes.get("scarce") or [])
    pools: dict[str, dict[str, list[float]]] = {
        "all": {"hour": [], "mid_ret": [], "rv": [], "spread_bps": []},
        "stress": {"hour": [], "mid_ret": [], "rv": [], "spread_bps": []},
        "calm": {"hour": [], "mid_ret": [], "rv": [], "spread_bps": []},
        "scarce": {"hour": [], "mid_ret": [], "rv": [], "spread_bps": []},
    }
    day_labels = []
    ret_mat = []
    for hrow in hourly:
        if not hrow.get("ok"):
            continue
        day = str(hrow["day"])
        hours = np.asarray(hrow["hour_utc"], dtype=np.float64)
        mid_ret = np.asarray(hrow["mid_ret"], dtype=np.float64)
        rv = np.asarray(hrow["rv"], dtype=np.float64)
        sp = np.asarray(hrow["spread_bps"], dtype=np.float64)
        for i, hh in enumerate(hours):
            for key in ("all",):
                pools[key]["hour"].append(float(hh))
                pools[key]["mid_ret"].append(float(mid_ret[i]) if i < mid_ret.size else float("nan"))
                pools[key]["rv"].append(float(rv[i]) if i < rv.size else float("nan"))
                pools[key]["spread_bps"].append(float(sp[i]) if i < sp.size else float("nan"))
            bucket = "stress" if day in stress_days else "calm"
            pools[bucket]["hour"].append(float(hh))
            pools[bucket]["mid_ret"].append(float(mid_ret[i]) if i < mid_ret.size else float("nan"))
            pools[bucket]["rv"].append(float(rv[i]) if i < rv.size else float("nan"))
            pools[bucket]["spread_bps"].append(float(sp[i]) if i < sp.size else float("nan"))
            if day in scarce_days:
                pools["scarce"]["hour"].append(float(hh))
                pools["scarce"]["mid_ret"].append(float(mid_ret[i]) if i < mid_ret.size else float("nan"))
                pools["scarce"]["rv"].append(float(rv[i]) if i < rv.size else float("nan"))
                pools["scarce"]["spread_bps"].append(float(sp[i]) if i < sp.size else float("nan"))
        # day × hour mid_ret matrix for PCA
        row = np.full(24, np.nan)
        for i, hh in enumerate(hours.astype(int)):
            if 0 <= hh < 24 and i < mid_ret.size:
                row[hh] = mid_ret[i]
        day_labels.append(day)
        ret_mat.append(row)

    tod = {}
    for label, p in pools.items():
        tod[label] = {
            "mid_ret": tod_profile(np.asarray(p["hour"]), np.asarray(p["mid_ret"])),
            "rv": tod_profile(np.asarray(p["hour"]), np.asarray(p["rv"])),
            "spread_bps": tod_profile(np.asarray(p["hour"]), np.asarray(p["spread_bps"])),
            "uni_mid_ret": univariate_moments(np.asarray(p["mid_ret"])),
            "uni_rv": univariate_moments(np.asarray(p["rv"])),
        }
    mat = np.asarray(ret_mat, dtype=np.float64) if ret_mat else np.zeros((0, 24))
    factor = {
        "mid_ret_tod_pca": pca_commonality(mat, row_labels=day_labels),
        "n_days": len(day_labels),
    }
    return {"tod": tod, "factor": factor}


def _markouts(hourly: list[dict[str, Any]], regimes: dict[str, Any]) -> dict[str, Any]:
    """Cumulative mid-return markout from hour 0..H stratified by regime."""
    horizons = list(range(1, 9))
    groups = {
        "all": set(h["day"] for h in hourly if h.get("ok")),
        "scarce": set(regimes.get("scarce") or []),
        "stress": set(regimes.get("stress_abs_gex") or []),
        "calm": set(regimes.get("calm_abs_gex") or []),
        "high_squeeze": set(regimes.get("high_squeeze") or []),
    }
    out: dict[str, Any] = {"horizons_h": horizons, "groups": {}}
    for gname, gdays in groups.items():
        curves = []
        for hrow in hourly:
            if not hrow.get("ok") or str(hrow["day"]) not in gdays:
                continue
            rets = np.asarray(hrow["mid_ret"], dtype=np.float64)
            # align by hour index order
            cum = []
            s = 0.0
            for i, r in enumerate(rets):
                if i == 0:
                    cum.append(0.0)
                    continue
                if np.isfinite(r):
                    s += float(r)
                cum.append(s)
            curves.append(np.asarray(cum, dtype=np.float64))
        if not curves:
            out["groups"][gname] = {"ok": False, "n_days": 0}
            continue
        max_len = max(c.size for c in curves)
        stacked = np.full((len(curves), max_len), np.nan)
        for i, c in enumerate(curves):
            stacked[i, : c.size] = c
        mean_path = np.nanmean(stacked, axis=0)
        # sample at horizons (hour index)
        at_h = {}
        for H in horizons:
            idx = min(H, mean_path.size - 1)
            at_h[str(H)] = float(mean_path[idx]) if idx >= 0 and np.isfinite(mean_path[idx]) else None
        out["groups"][gname] = {
            "ok": True,
            "n_days": len(curves),
            "mean_cum_mid_ret_by_hour_index": mean_path.tolist(),
            "markout_at_h": at_h,
        }
    return out


def _candidates(incr: dict, leadlag: dict, stress: dict, tod_pack: dict, regimes: dict) -> list[dict[str, Any]]:
    pr = (incr.get("partial_range_gex_ctrl_rv") or {}).get("partial_r")
    dr2 = incr.get("delta_r2_gex_after_rv")
    dr2_sq = incr.get("delta_r2_squeeze_after_gex")
    dr2_vex = incr.get("delta_r2_vex_after_rv_gex")
    ll = leadlag.get("gex->hl_rv") or {}
    pc1 = ((tod_pack.get("factor") or {}).get("mid_ret_tod_pca") or {}).get("pc1_explained")

    def hold(cid: str, note: str, use: str, lenses: list[str] | None = None) -> dict[str, Any]:
        return {
            "id": cid,
            "decision": "Hold",
            "note": note,
            "use": use,
            "wire_as": "monitor",
            "tradable": False,
            "lenses": lenses or ["info", "risk"],
        }

    cands = [
        hold(
            "risk.gex_exposure",
            "GEX day monitor on PROXY_trade_flow_DDOI; falsifiers Hold",
            "risk monitor strip — never sized α",
            ["risk", "mm"],
        ),
        hold(
            "risk.vex_exposure",
            f"VEX; ΔR² after RV+GEX≈{dr2_vex}",
            "risk / IV-join monitor",
            ["risk", "mm"],
        ),
        hold(
            "risk.squeeze_intensity",
            f"GEX+ scarcity; ΔR² squeeze after GEX≈{dr2_sq}",
            "squeeze / scarcity strip",
            ["risk", "liq"],
        ),
        hold(
            "liq.implied_book_scarcity",
            f"scarce days={regimes.get('scarce')}",
            "liquidity friction context",
            ["liq", "exec"],
        ),
        hold(
            "info.gex_range_incremental",
            f"partial(range,GEX|RV)≈{pr}; ΔR²(GEX|RV)≈{dr2}",
            "research tile — vol-overlap check",
            ["info", "risk"],
        ),
        hold(
            "info.squeeze_after_gex",
            f"ΔR²(squeeze|GEX) on range≈{dr2_sq}",
            "research — incremental squeeze",
            ["info", "liq"],
        ),
        hold(
            "info.vex_incremental",
            f"ΔR²(VEX|RV+GEX)≈{dr2_vex}",
            "research — VEX beyond GEX/RV",
            ["info", "risk"],
        ),
        hold(
            "info.gex_leadlag_map",
            f"best lag GEX→HL RV = {ll.get('best_lag')} corr≈{ll.get('best_corr')}",
            "research tile / risk context — not IRF α",
            ["info", "risk"],
        ),
        hold(
            "info.gex_markout_regimes",
            "scarce/stress vs calm cumulative mid-ret markouts (hourly)",
            "research / risk context",
            ["info", "risk", "exec"],
        ),
        hold(
            "info.tod_factor_structure",
            f"mid_ret ToD PC1 explained≈{pc1}",
            "commonality / regime strip",
            ["info", "disc"],
        ),
        hold(
            "info.stress_vs_calm",
            f"stress n={(stress.get('stress') or {}).get('n')} calm n={(stress.get('calm') or {}).get('n')}",
            "policy/monitor regime split",
            ["info", "liq"],
        ),
        hold(
            "info.object_use_map",
            "APPLICATIONS routing: monitor vs throttle vs never-tradable",
            "desk routing",
            ["info", "mm"],
        ),
        hold(
            "info.kraken_spot_vs_2venue",
            "spot_l2 appendix n=4 — feed quality only",
            "feed-quality flag / never arb α",
            ["info", "exec"],
        ),
        {
            "id": "alpha.tob_cross_arb",
            "decision": "Kill",
            "note": "never soft-Promote TOB-cross α",
            "use": "none",
            "wire_as": "never-tradable",
            "tradable": False,
            "lenses": ["exec"],
        },
        {
            "id": "data.trade_synth",
            "decision": "Kill",
            "note": "QUARANTINED — never SoT",
            "use": "none",
            "wire_as": "never-tradable",
            "tradable": False,
            "lenses": ["disc"],
        },
    ]
    # Kill incremental if truly null
    for c in cands:
        if c["id"] == "info.gex_range_incremental" and pr is not None and abs(float(pr)) < 0.05 and (
            dr2 is None or not np.isfinite(dr2) or abs(float(dr2)) < 0.01
        ):
            c["note"] = f"GEX adds ~nothing after RV (partial≈{pr}, ΔR²≈{dr2}) — keep as descriptive Hold tile"
            c["wire_as"] = "monitor"  # still Hold research, not Kill — useful honesty tile
    return cands


def _use_map(cands: list[dict[str, Any]]) -> dict[str, Any]:
    monitor, throttle, never = [], [], []
    for c in cands:
        wire = c.get("wire_as") or "monitor"
        if c.get("decision") == "Kill" or wire == "never-tradable":
            never.append(c["id"])
        elif "throttle" in wire:
            throttle.append(c["id"])
        else:
            monitor.append(c["id"])
    return {
        "monitor": monitor,
        "throttle": throttle,
        "never_tradable": never,
        "note": "Pass-2b: all Hold objects are monitors; Kill = never-tradable; no Promote wire",
    }


def _figs(
    rows: list[dict[str, Any]],
    leadlag: dict,
    incr: dict,
    stress: dict,
    tod_pack: dict,
    markouts: dict,
    use_map: dict,
) -> list[str]:
    paths: list[str] = []
    # lead-lag GEX → RV / range
    fig, axes = plt.subplots(1, 2, figsize=(9.0, 3.6))
    for ax, key, title in (
        (axes[0], "gex->hl_rv", "GEX → HL RV"),
        (axes[1], "gex->hl_range", "GEX → HL range"),
    ):
        ll = leadlag.get(key) or {}
        ax.bar(ll.get("lags") or [], [c if c is not None and np.isfinite(c) else 0 for c in (ll.get("corr") or [])], color="#3d5a80")
        ax.axhline(0, color="k", lw=0.7)
        ax.set_xlabel("lag (days; + ⇒ target leads)")
        ax.set_ylabel("corr")
        ax.set_title(title)
    fig.suptitle("Pass-2b day lead-lag", fontsize=11)
    paths.append(_savefig(fig, "fig_leadlag_day.png"))

    # incremental bars
    fig, ax = plt.subplots(figsize=(6.5, 3.5))
    labels = ["ΔR² GEX|RV", "ΔR² VEX|RV+GEX", "ΔR² squeeze|GEX", "partial range,GEX|RV"]
    vals = [
        incr.get("delta_r2_gex_after_rv"),
        incr.get("delta_r2_vex_after_rv_gex"),
        incr.get("delta_r2_squeeze_after_gex"),
        (incr.get("partial_range_gex_ctrl_rv") or {}).get("partial_r"),
    ]
    ax.bar(labels, [v if v is not None and np.isfinite(v) else 0 for v in vals], color=["#3d5a80", "#98c1d9", "#ee6c4d", "#293241"])
    ax.axhline(0, color="k", lw=0.7)
    ax.tick_params(axis="x", rotation=20)
    ax.set_title("Incremental / partial (certified n-day)")
    paths.append(_savefig(fig, "fig_incremental.png"))

    # stress vs calm RV means
    fig, ax = plt.subplots(figsize=(6.0, 3.5))
    names, means = [], []
    for k in ("calm", "stress", "scarce", "abundant", "high_squeeze"):
        rec = stress.get(k) or {}
        if rec.get("ok"):
            names.append(f"{k}\nn={rec['n']}")
            means.append(rec.get("mean_hl_rv") or 0)
    ax.bar(names, means, color="#3d5a80")
    ax.set_ylabel("mean HL RV")
    ax.set_title("Regime mean HL RV")
    paths.append(_savefig(fig, "fig_stress_calm_rv.png"))

    # ToD RV all vs scarce
    fig, ax = plt.subplots(figsize=(8.0, 3.6))
    tod = tod_pack.get("tod") or {}
    for label, color in (("all", "#3d5a80"), ("scarce", "#ee6c4d"), ("stress", "#98c1d9")):
        rec = (tod.get(label) or {}).get("rv") or {}
        hrs, means = rec.get("hours") or [], rec.get("means") or []
        if means:
            ax.plot(hrs, means, "-o", ms=3, label=label, color=color)
    ax.set_xlabel("UTC hour")
    ax.set_ylabel("mean hourly RV")
    ax.legend(fontsize=8)
    ax.set_title("ToD RV by regime")
    paths.append(_savefig(fig, "fig_tod_rv.png"))

    # markouts
    fig, ax = plt.subplots(figsize=(7.0, 3.8))
    for gname, color in (("calm", "#98c1d9"), ("stress", "#3d5a80"), ("scarce", "#ee6c4d"), ("high_squeeze", "#293241")):
        g = (markouts.get("groups") or {}).get(gname) or {}
        path = g.get("mean_cum_mid_ret_by_hour_index") or []
        if path:
            ax.plot(range(len(path)), path, label=f"{gname} n={g.get('n_days')}", color=color)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlabel("hour index in day")
    ax.set_ylabel("cum log mid-ret")
    ax.legend(fontsize=8)
    ax.set_title("Intraday markout by GEX regime")
    paths.append(_savefig(fig, "fig_markout_regimes.png"))

    # use map
    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    cats = ["monitor", "throttle", "never_tradable"]
    counts = [len(use_map.get(c) or []) for c in cats]
    ax.bar(cats, counts, color=["#c4a035", "#6c757d", "#b33a3a"])
    ax.set_ylabel("# candidates")
    ax.set_title("APPLICATIONS use map (Pass-2b)")
    for i, c in enumerate(cats):
        ids = use_map.get(c) or []
        ax.text(i, counts[i] + 0.1, str(len(ids)), ha="center", fontsize=9)
    paths.append(_savefig(fig, "fig_use_map.png"))
    return paths


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--skip-hourly", action="store_true", help="Skip warehouse hourly rebuild")
    args = ap.parse_args()

    ensure_env()
    OUT.mkdir(parents=True, exist_ok=True)
    FIGS.mkdir(parents=True, exist_ok=True)
    cert = load_certified()
    primary = gex_panel_days(cert)
    spot = spot_l2_days(cert)
    rows = _load_rows(primary)
    if not rows:
        print(json.dumps({"ok": False, "blocker": "no gex rows"}))
        return 2

    regimes = _regimes(rows)
    # cast med keys properly for JSON
    regimes_json = {k: v for k, v in regimes.items()}

    leadlag = _leadlag_day(rows)
    incr = _incremental(rows)
    stress = _stress_calm(rows, regimes)

    hourly: list[dict[str, Any]] = []
    if not args.skip_hourly:
        for r in rows:
            print(f"hourly {r['day']}…", flush=True)
            hourly.append(_hourly_from_tob(args.symbol, str(r["day"])))
    tod_pack = _tod_factor(hourly, regimes) if hourly else {"tod": {}, "factor": {}}
    markouts = _markouts(hourly, regimes) if hourly else {"groups": {}}

    # attach next-day mid return lead-lag if hourly ok
    day_rets = []
    for h in hourly:
        day_rets.append(h.get("day_mid_ret") if h.get("ok") else float("nan"))
    if day_rets and len(day_rets) == len(rows):
        gex = _arr(rows, "gex")
        y = np.asarray(day_rets, dtype=np.float64)
        lags, corrs, ns = [], [], []
        for lag in LAGS:
            if lag == 0:
                a, b = gex, y
            elif lag > 0:
                a, b = gex[:-lag], y[lag:]
            else:
                s = -lag
                a, b = gex[s:], y[:-s]
            m = np.isfinite(a) & np.isfinite(b)
            n = int(m.sum())
            r = float(np.corrcoef(a[m], b[m])[0, 1]) if n >= 3 else float("nan")
            lags.append(int(lag))
            corrs.append(r)
            ns.append(n)
        best_i = int(np.nanargmax(np.abs(corrs))) if any(np.isfinite(corrs)) else 0
        leadlag["gex->day_mid_ret"] = {
            "lags": lags,
            "corr": corrs,
            "n": ns,
            "best_lag": lags[best_i],
            "best_corr": corrs[best_i],
        }

    # day feature PCA
    feat = np.column_stack(
        [
            _arr(rows, "gex"),
            _arr(rows, "vex"),
            _arr(rows, "gex_plus"),
            _arr(rows, "squeeze_intensity"),
            _arr(rows, "hl_rv"),
            _arr(rows, "hl_range"),
            _arr(rows, "db_rv"),
            _arr(rows, "db_range"),
        ]
    )
    day_pca = pca_commonality(feat, row_labels=[str(r["day"]) for r in rows])

    cands = _candidates(incr, leadlag, stress, tod_pack, regimes)
    use_map = _use_map(cands)
    fig_paths = _figs(rows, leadlag, incr, stress, tod_pack, markouts, use_map)

    # bayes on key corrs
    bayes = {
        "gex_hl_rv": fisher_z_normal_posterior(
            float((incr.get("raw_corr_gex_rv") or {}).get("pearson") or np.nan),
            int((incr.get("raw_corr_gex_rv") or {}).get("n") or 0),
        ),
        "gex_hl_range": fisher_z_normal_posterior(
            float((incr.get("raw_corr_gex_range") or {}).get("pearson") or np.nan),
            int((incr.get("raw_corr_gex_range") or {}).get("n") or 0),
        ),
        "vex_hl_range": fisher_z_normal_posterior(
            float((incr.get("raw_corr_vex_range") or {}).get("pearson") or np.nan),
            int((incr.get("raw_corr_vex_range") or {}).get("n") or 0),
        ),
    }

    # day-block on day panel (each day one obs — still honest CI via day resample)
    days_arr = np.asarray([str(r["day"]) for r in rows], dtype=object)
    day_block = {
        "gex_hl_rv": day_block_bootstrap_corr(
            days_arr, _arr(rows, "gex"), _arr(rows, "hl_rv"), n_boot=N_BOOT, seed=SEED, min_n=4
        ),
        "gex_hl_range": day_block_bootstrap_corr(
            days_arr, _arr(rows, "gex"), _arr(rows, "hl_range"), n_boot=N_BOOT, seed=SEED, min_n=4
        ),
    }

    joined = {
        "n_days": len(rows),
        "days": [str(r["day"]) for r in rows],
        "rows": [
            {
                **{k: r.get(k) for k in (
                    "day", "gex", "vex", "gex_plus", "squeeze_intensity", "scarce",
                    "hl_rv", "hl_range", "db_rv", "db_range", "ddoi_mode", "opt_iv_n",
                )},
                "hourly": next((h for h in hourly if h.get("day") == r["day"]), None),
                "kraken_mode": "spot_l2" if str(r["day"]) in set(spot) else "absent_2venue",
            }
            for r in rows
        ],
    }

    out = {
        "ok": True,
        "pass": "2b",
        "panel": "panel_gex_options",
        "symbol": args.symbol,
        "n": len(rows),
        "days": [str(r["day"]) for r in rows],
        "spot_l2_days": spot,
        "regimes": regimes_json,
        "lead_lag": leadlag,
        "incremental": incr,
        "stress_calm": stress,
        "tod_factor": tod_pack,
        "markouts": markouts,
        "day_feature_pca": day_pca,
        "day_block": day_block,
        "bayes_corr": bayes,
        "candidates": cands,
        "use_map": use_map,
        "figs": fig_paths,
        "promote_count": 0,
        "decision": "Hold",
        "honesty": (
            "Pass-2b info dig; DDOI=PROXY_trade_flow; hourly from real HL TOB/marks; "
            "spot_l2 appendix; 0 Promote; ClickHouse MCP banned"
        ),
    }
    _write(OUT / "info_features.json", out)
    _write(OUT / "candidates.json", cands)
    _write(OUT / "joined_day_hourly.json", joined)
    _write(OUT / "use_map.json", use_map)

    pr = (incr.get("partial_range_gex_ctrl_rv") or {}).get("partial_r")
    report = "\n".join(
        [
            "# Pass-2b info dig — squeeze_metrics",
            "",
            f"- Symbol: **{args.symbol}** · certified `panel_gex_options` n={len(rows)}",
            f"- Days: {', '.join(str(r['day']) for r in rows)}",
            f"- spot_l2 appendix: {', '.join(spot)} (n={len(spot)})",
            f"- DDOI: `PROXY_trade_flow_DDOI` · Promote count: **0**",
            "",
            "## Candidates",
            "",
            "| id | decision | wire-as | use |",
            "|----|----------|---------|-----|",
            *[
                f"| `{c['id']}` | **{c['decision']}** | {c.get('wire_as')} | {c.get('use')} |"
                for c in cands
            ],
            "",
            "## Key numbers",
            "",
            f"- partial(range, GEX | RV) = `{pr}` · ΔR² GEX after RV = `{incr.get('delta_r2_gex_after_rv')}`",
            f"- ΔR² VEX after RV+GEX = `{incr.get('delta_r2_vex_after_rv_gex')}`",
            f"- ΔR² squeeze after GEX = `{incr.get('delta_r2_squeeze_after_gex')}`",
            f"- day PCA PC1 explained = `{(day_pca or {}).get('pc1_explained')}`",
            f"- ToD mid_ret PC1 = `{((tod_pack.get('factor') or {}).get('mid_ret_tod_pca') or {}).get('pc1_explained')}`",
            f"- lead-lag GEX→HL RV best = lag `{((leadlag.get('gex->hl_rv') or {}).get('best_lag'))}` corr `{((leadlag.get('gex->hl_rv') or {}).get('best_corr'))}`",
            f"- scarce days: `{regimes.get('scarce')}`",
            "",
            "## Figs",
            "",
            *[f"- `{p}`" for p in fig_paths],
            "",
            "## Honesty",
            "",
            "- ClickHouse MCP banned · real HL+Deribit quotes + Deribit option IV",
            "- Never soft-Promote TOB-cross α · `trade_synth` QUARANTINED",
            "- DDOI is PROXY_trade_flow — warehouse OI futures-only unused",
            "",
        ]
    )
    (OUT / "EXP_REPORT.md").write_text(report)
    print(json.dumps(_jsonable({"written": str(OUT / "info_features.json"), "n": len(rows), "figs": fig_paths, "promote_count": 0}), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
