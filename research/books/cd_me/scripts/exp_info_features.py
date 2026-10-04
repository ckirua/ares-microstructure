#!/usr/bin/env python3
"""Pass-2.5 info dig: what PIM / VLOOP / TCOST / DCM̂ carry.

Reuses Pass-2 ETH day list + ``out/pim_vloop_tcost`` / ``out/dcm_proxies``
hourly panels; enriches with mark-bar mid returns / RV / funding / basis.
Writes ``out/info_features/`` JSON + figs. ClickHouse MCP banned.
No soft-Promote TOB-cross α.
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
WAREHOUSE_SRC = Path(
    os.environ.get("WAREHOUSE_SRC")
    or ((Path(os.environ.get("WAREHOUSE_ROOT") or (Path.home() / "lab" / "lab-n2070" / "warehouse")) / "src"))
)
STARTARB = Path(os.environ.get("ARES_STARTARB") or (Path.home() / "srv" / "ares-startarb"))

for _p in (str(WAREHOUSE_SRC), str(STARTARB / "src"), str(ROOT), str(SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from _data import (  # noqa: E402
    asof_join,
    ensure_env,
    funding_proxy_from_marks,
    load_cross_venue_marks,
)
from _nb_common import kraken_mode_for_day, load_kraken_inventory  # noqa: E402
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
from ares_micro.flow.cdme import realized_vol  # noqa: E402

OUT = BOOK / "out" / "info_features"
FIGS = OUT / "figs"
PIM_OUT = BOOK / "out" / "pim_vloop_tcost"
DCM_OUT = BOOK / "out" / "dcm_proxies"
N_BOOT = 400
SEED = 42
LAGS = (-3, -2, -1, 0, 1, 2, 3)


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
    if isinstance(obj, float) and obj != obj:
        return None
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


def _farr(raw: list | None, n: int) -> np.ndarray:
    out = np.full(n, np.nan, dtype=np.float64)
    if not raw:
        return out
    for i, v in enumerate(raw[:n]):
        if v is None:
            continue
        try:
            x = float(v)
        except (TypeError, ValueError):
            continue
        if np.isfinite(x):
            out[i] = x
    return out


def _early_late(days: list[str]) -> tuple[list[str], list[str]]:
    d = sorted(days)
    mid = max(1, len(d) // 2)
    return d[:mid], d[mid:]


def _enrich_marks(symbol: str, day: str, ts_h: np.ndarray) -> dict[str, np.ndarray]:
    """Hourly mid return, RV, |funding_proxy|, |basis| aligned to PIM centers."""
    n = int(ts_h.size)
    empty = {
        "mid_ret": np.full(n, np.nan),
        "rv": np.full(n, np.nan),
        "abs_funding": np.full(n, np.nan),
        "abs_basis": np.full(n, np.nan),
        "mid": np.full(n, np.nan),
    }
    if n == 0:
        return empty
    try:
        marks = load_cross_venue_marks(symbol, day, quiet=True)
    except Exception as exc:  # noqa: BLE001
        empty["error"] = np.array([f"{type(exc).__name__}: {exc}"], dtype=object)  # type: ignore[assignment]
        return empty
    venues = marks.get("venues") or {}
    home = venues.get("hyperliquid")
    home_name = "hyperliquid"
    if not isinstance(home, dict) or home.get("n", 0) < 15 or "error" in home:
        home = None
        for v, rec in venues.items():
            if isinstance(rec, dict) and rec.get("n", 0) >= 15 and "error" not in rec:
                home = rec
                home_name = v
                break
    if home is None:
        return empty

    h_ts = np.asarray(home["ts"], dtype=np.int64)
    h_mid = np.asarray(home["mid"], dtype=np.float64)
    log_px = np.log(np.clip(h_mid, 1e-12, None))
    rv = realized_vol(log_px, window=30)
    fund = funding_proxy_from_marks(h_mid, h_ts, window=30)["funding_proxy"]
    basis = np.full(h_mid.shape, np.nan, dtype=np.float64)
    for bv in ("deribit", "kraken"):
        rec = venues.get(bv)
        if not isinstance(rec, dict) or rec.get("n", 0) < 10 or "error" in rec:
            continue
        if bv == home_name:
            continue
        far = asof_join(h_ts, np.asarray(rec["ts"], dtype=np.int64), np.asarray(rec["mid"], dtype=np.float64))
        ok = np.isfinite(far) & (far > 0) & np.isfinite(h_mid) & (h_mid > 0)
        basis[ok] = np.log(far[ok] / h_mid[ok])
        break

    mid_h = asof_join(ts_h, h_ts, h_mid)
    rv_h = asof_join(ts_h, h_ts, rv)
    fund_h = asof_join(ts_h, h_ts, fund)
    basis_h = asof_join(ts_h, h_ts, basis)
    # concurrent hourly log-return of mid
    mid_ret = np.full(n, np.nan, dtype=np.float64)
    for i in range(1, n):
        if np.isfinite(mid_h[i]) and np.isfinite(mid_h[i - 1]) and mid_h[i - 1] > 0 and mid_h[i] > 0:
            mid_ret[i] = float(np.log(mid_h[i] / mid_h[i - 1]))
    return {
        "mid_ret": mid_ret,
        "rv": rv_h,
        "abs_funding": np.abs(fund_h),
        "abs_basis": np.abs(basis_h),
        "mid": mid_h,
        "home_venue_marks": np.array([home_name], dtype=object),  # type: ignore[dict-item]
    }


def build_joined_panel(symbol: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pim_rows = json.loads((PIM_OUT / "panel_rows.json").read_text())
    dcm_rows = {r["day"]: r for r in json.loads((DCM_OUT / "panel_rows.json").read_text()) if r.get("ok")}
    inv = load_kraken_inventory(BOOK)
    joined: list[dict[str, Any]] = []
    meta_days: list[str] = []

    for prow in pim_rows:
        if not prow.get("ok"):
            continue
        day = str(prow["day"])
        h = prow.get("hourly") or {}
        ts = np.asarray(h.get("ts") or [], dtype=np.int64)
        n = int(ts.size)
        if n == 0:
            continue
        drow = dcm_rows.get(day) or {}
        hp = drow.get("hourly_pool") or {}
        dcm_arr = _farr(hp.get("dcm"), n)
        # if DCM hourly length differs, asof by ts
        if hp.get("ts") and len(hp["ts"]) != n:
            dts = np.asarray(hp["ts"], dtype=np.int64)
            dcm_raw = _farr(hp.get("dcm"), len(dts))
            dcm_arr = asof_join(ts, dts, dcm_raw)

        marks = _enrich_marks(symbol, day, ts)
        # Prefer PIM row label (post real-quote fix); never invent trade_synth as 3v
        kr_mode = prow.get("kraken_mode") or kraken_mode_for_day(day, inv)
        if kr_mode in ("trade_synth", "PROXY_NOT_TOB_trade_synth"):
            kr_mode = "PROXY_NOT_TOB_trade_synth"
        row = {
            "day": day,
            "symbol": symbol,
            "kraken_mode": kr_mode,
            "panel_kind": prow.get("panel_kind") or (
                "panel_3venue_spot" if kr_mode == "spot_l2" else "panel_core_2venue"
            ),
            "n_hours": n,
            "ts": ts.tolist(),
            "hour_utc": [int(((int(t) // 1_000_000_000) % 86400) // 3600) for t in ts],
            "vloop": _farr(h.get("vloop"), n).tolist(),
            "tcost": _farr(h.get("tcost"), n).tolist(),
            "pim": _farr(h.get("pim"), n).tolist(),
            "notional": _farr(h.get("notional"), n).tolist(),
            "imbalance": _farr(h.get("imbalance"), n).tolist(),
            "dcm": dcm_arr.tolist(),
            "mid_ret": marks["mid_ret"].tolist(),
            "rv": marks["rv"].tolist(),
            "abs_funding": marks["abs_funding"].tolist(),
            "abs_basis": marks["abs_basis"].tolist(),
            "cov": prow.get("coverage") or {},
            "corr_vloop_tcost_day": (prow.get("summary") or {}).get("corr_vloop_tcost"),
            "pim_mean_day": (prow.get("summary") or {}).get("pim_mean"),
            "dcm_explained_var": ((drow.get("dcm") or {}).get("explained_var")),
            "dcm_loadings": (drow.get("dcm") or {}).get("loadings"),
        }
        joined.append(row)
        meta_days.append(day)
    return joined, {"days": meta_days, "n_days": len(meta_days), "symbol": symbol}


def _stack(joined: list[dict[str, Any]], key: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    xs: list[float] = []
    days: list[str] = []
    hours: list[int] = []
    for r in joined:
        arr = np.asarray(r[key], dtype=np.float64)
        hu = np.asarray(r["hour_utc"], dtype=np.int64)
        for i, v in enumerate(arr):
            xs.append(float(v))
            days.append(str(r["day"]))
            hours.append(int(hu[i]) if i < hu.size else -1)
    return (
        np.asarray(xs, dtype=np.float64),
        np.asarray(days, dtype=object),
        np.asarray(hours, dtype=np.float64),
    )


def _pair_stack(
    joined: list[dict[str, Any]], key_x: str, key_y: str
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    xs: list[float] = []
    ys: list[float] = []
    days: list[str] = []
    for r in joined:
        a = np.asarray(r[key_x], dtype=np.float64)
        b = np.asarray(r[key_y], dtype=np.float64)
        n = min(a.size, b.size)
        for i in range(n):
            xs.append(float(a[i]))
            ys.append(float(b[i]))
            days.append(str(r["day"]))
    return np.asarray(xs), np.asarray(ys), np.asarray(days, dtype=object)


def analyze(joined: list[dict[str, Any]]) -> dict[str, Any]:
    days = [r["day"] for r in joined]
    early, late = _early_late(days)

    # --- univariate ---
    uni: dict[str, Any] = {}
    for key in ("pim", "vloop", "tcost", "dcm", "notional", "rv", "mid_ret", "abs_funding", "abs_basis"):
        x, _, _ = _stack(joined, key)
        uni[key] = univariate_moments(x)

    # --- ToD ---
    tod: dict[str, Any] = {}
    for key in ("pim", "vloop", "tcost", "dcm", "notional"):
        x, _, h = _stack(joined, key)
        tod[key] = tod_profile(h, x)

    # --- contemporaneous dependence ---
    dep: dict[str, Any] = {}
    for a, b in (
        ("pim", "dcm"),
        ("pim", "rv"),
        ("pim", "notional"),
        ("pim", "abs_funding"),
        ("pim", "abs_basis"),
        ("pim", "mid_ret"),
        ("vloop", "tcost"),
        ("vloop", "dcm"),
        ("tcost", "dcm"),
        ("dcm", "rv"),
        ("dcm", "notional"),
        ("vloop", "mid_ret"),
        ("tcost", "mid_ret"),
    ):
        xa, ya, da = _pair_stack(joined, a, b)
        dep[f"{a}__{b}"] = {
            **pearson_spearman(xa, ya),
            "day_block": day_block_bootstrap_corr(da, xa, ya, n_boot=N_BOOT, seed=SEED),
        }

    # --- lead-lag (pooled hourly, within-day concat then lag — also per-day avg) ---
    leadlag: dict[str, Any] = {}
    targets = {
        "mid_ret": "concurrent/post mid return",
        "rv": "realized vol",
        "notional": "trade intensity (notional)",
        "abs_funding": "funding proxy",
        "abs_basis": "abs basis",
    }
    carriers = ("pim", "vloop", "tcost", "dcm")
    per_day_ll: dict[str, list[dict[str, Any]]] = {}
    for carr in carriers:
        for tgt, label in targets.items():
            key = f"{carr}->|{tgt}"
            day_best: list[dict[str, Any]] = []
            # pooled: concatenate days with nan separators to avoid cross-day lag bleed
            xs: list[float] = []
            ys: list[float] = []
            for r in joined:
                a = np.asarray(r[carr], dtype=np.float64)
                b = np.asarray(r[tgt], dtype=np.float64)
                xs.extend(a.tolist())
                ys.extend(b.tolist())
                xs.append(float("nan"))
                ys.append(float("nan"))
                ll_d = lead_lag_corr(a, b, lags=LAGS)
                day_best.append({"day": r["day"], **ll_d})
            pooled = lead_lag_corr(np.asarray(xs), np.asarray(ys), lags=LAGS)
            leadlag[key] = {
                "label": label,
                "pooled": pooled,
                "median_best_corr": float(
                    np.nanmedian([d.get("best_corr") for d in day_best])
                ),
                "median_best_lag": float(
                    np.nanmedian(
                        [d.get("best_lag") for d in day_best if d.get("best_lag") is not None]
                    )
                )
                if any(d.get("best_lag") is not None for d in day_best)
                else None,
            }
            per_day_ll[key] = day_best

    # --- incremental information ---
    pim, rv, da = _pair_stack(joined, "pim", "rv")
    dcm = _pair_stack(joined, "pim", "dcm")[1]
    notional = _pair_stack(joined, "pim", "notional")[1]
    # align lengths already matched via pair_stack on same days; rebuild jointly
    pims: list[float] = []
    rvs: list[float] = []
    dcms: list[float] = []
    vols: list[float] = []
    day_tags: list[str] = []
    for r in joined:
        for i in range(len(r["pim"])):
            pims.append(float(r["pim"][i]))
            rvs.append(float(r["rv"][i]))
            dcms.append(float(r["dcm"][i]))
            vols.append(float(r["notional"][i]))
            day_tags.append(str(r["day"]))
    pim_a = np.asarray(pims)
    rv_a = np.asarray(rvs)
    dcm_a = np.asarray(dcms)
    vol_a = np.asarray(vols)
    day_a = np.asarray(day_tags, dtype=object)

    incr = {
        "partial_pim_dcm_ctrl_rv": partial_corr(pim_a, dcm_a, rv_a),
        "partial_pim_vlm_ctrl_rv": partial_corr(pim_a, vol_a, rv_a),
        "partial_vlm_pim_ctrl_dcm": partial_corr(vol_a, pim_a, dcm_a),
        "ols_pim_on_rv": ols_incremental(pim_a, rv_a.reshape(-1, 1), names=["rv"]),
        "ols_pim_on_rv_dcm": ols_incremental(
            pim_a, np.column_stack([rv_a, dcm_a]), names=["rv", "dcm"]
        ),
        "ols_pim_on_rv_vlm": ols_incremental(
            pim_a, np.column_stack([rv_a, vol_a]), names=["rv", "vlm"]
        ),
        "ols_pim_on_rv_dcm_vlm": ols_incremental(
            pim_a, np.column_stack([rv_a, dcm_a, vol_a]), names=["rv", "dcm", "vlm"]
        ),
        "raw_corr_pim_dcm": pearson_spearman(pim_a, dcm_a),
        "raw_corr_pim_vlm": pearson_spearman(pim_a, vol_a),
        "day_block_pim_dcm": day_block_bootstrap_corr(day_a, pim_a, dcm_a, n_boot=N_BOOT, seed=SEED),
        "day_block_pim_vlm": day_block_bootstrap_corr(day_a, pim_a, vol_a, n_boot=N_BOOT, seed=SEED + 1),
    }
    # ΔR² from adding DCM after RV
    r2_rv = incr["ols_pim_on_rv"].get("r2")
    r2_rv_dcm = incr["ols_pim_on_rv_dcm"].get("r2")
    r2_rv_vlm = incr["ols_pim_on_rv_vlm"].get("r2")
    incr["delta_r2_dcm_after_rv"] = (
        float(r2_rv_dcm - r2_rv)
        if np.isfinite(r2_rv) and np.isfinite(r2_rv_dcm)
        else float("nan")
    )
    incr["delta_r2_vlm_after_rv"] = (
        float(r2_rv_vlm - r2_rv)
        if np.isfinite(r2_rv) and np.isfinite(r2_rv_vlm)
        else float("nan")
    )

    # --- VLOOP↔TCOST stress regimes (PIM high vs low) ---
    vl, tc, _ = _pair_stack(joined, "vloop", "tcost")
    pim_s = _pair_stack(joined, "vloop", "pim")[1]
    m = np.isfinite(vl) & np.isfinite(tc) & np.isfinite(pim_s)
    ql, qh = np.nanquantile(pim_s[m], [0.25, 0.75])
    low = m & (pim_s <= ql)
    high = m & (pim_s >= qh)
    stress = {
        "q_low": float(ql),
        "q_high": float(qh),
        "corr_calm": pearson_spearman(vl[low], tc[low]),
        "corr_stress": pearson_spearman(vl[high], tc[high]),
        "corr_all": pearson_spearman(vl[m], tc[m]),
    }

    # --- Kraken spot_l2 vs 2-venue (absent) — synth QUARANTINED ---
    by_mode: dict[str, list[dict[str, Any]]] = {
        "spot_l2": [],
        "absent_2venue": [],
    }
    for r in joined:
        mode = r.get("kraken_mode") or "absent_2venue"
        if mode in ("trade_synth", "PROXY_NOT_TOB_trade_synth"):
            # never mix PROXY into primary sensitivity
            continue
        if mode not in by_mode:
            by_mode.setdefault(mode, [])
        by_mode[mode].append(r)
    kraken_sens: dict[str, Any] = {
        "modes": {},
        "note": "trade_synth QUARANTINED — compare spot_l2 vs absent_2venue only",
    }
    for mode, rows in by_mode.items():
        if not rows:
            continue
        xa, ya, da = _pair_stack(rows, "pim", "dcm")
        xb, yb, db = _pair_stack(rows, "vloop", "tcost")
        xc, yc, dc = _pair_stack(rows, "pim", "notional")
        day_means = [float(r["pim_mean_day"]) for r in rows if r.get("pim_mean_day") is not None]
        kraken_sens["modes"][mode] = {
            "n_days": len(rows),
            "days": [r["day"] for r in rows],
            "pim_mean_of_day_means": float(np.nanmean(day_means)) if day_means else float("nan"),
            "corr_pim_dcm": pearson_spearman(xa, ya),
            "corr_vloop_tcost": pearson_spearman(xb, yb),
            "corr_pim_vlm": pearson_spearman(xc, yc),
            "day_block_pim_dcm": day_block_bootstrap_corr(da, xa, ya, n_boot=N_BOOT, seed=SEED),
        }
    spot_m = kraken_sens["modes"].get("spot_l2", {}).get("pim_mean_of_day_means")
    abs_m = kraken_sens["modes"].get("absent_2venue", {}).get("pim_mean_of_day_means")
    if spot_m is not None and abs_m is not None and np.isfinite(spot_m) and np.isfinite(abs_m):
        kraken_sens["delta_day_mean_pim_spot_minus_2venue"] = float(spot_m - abs_m)

    # --- commonality / factor structure across days ---
    # day × hour matrix of PIM (use hour 0..23 mean)
    hour_mat = np.full((len(joined), 24), np.nan)
    for i, r in enumerate(joined):
        p = np.asarray(r["pim"], dtype=np.float64)
        h = np.asarray(r["hour_utc"], dtype=np.int64)
        for hh in range(24):
            sel = h == hh
            if sel.any() and np.isfinite(p[sel]).any():
                hour_mat[i, hh] = float(np.nanmean(p[sel]))
    factor = {
        "pim_tod_pca": pca_commonality(hour_mat, row_labels=days),
        "day_feature_pca": None,
    }
    # features per day: mean pim, vloop, tcost, dcm, rv, |fund|, corr_vt
    feat_rows = []
    for r in joined:
        feat_rows.append(
            [
                float(np.nanmean(r["pim"])),
                float(np.nanmean(r["vloop"])),
                float(np.nanmean(r["tcost"])),
                float(np.nanmean(r["dcm"])),
                float(np.nanmean(r["rv"])),
                float(np.nanmean(r["abs_funding"])),
                float(r["corr_vloop_tcost_day"]) if r.get("corr_vloop_tcost_day") is not None else float("nan"),
            ]
        )
    feat_mat = np.asarray(feat_rows, dtype=np.float64).T  # features × days for PCA on days
    # PCA across days using day×feature
    factor["day_feature_pca"] = pca_commonality(
        np.asarray(feat_rows, dtype=np.float64),
        row_labels=days,
    )
    factor["feature_names"] = [
        "pim_mean",
        "vloop_mean",
        "tcost_mean",
        "dcm_mean",
        "rv_mean",
        "abs_funding_mean",
        "corr_vloop_tcost",
    ]

    # --- chronological split ---
    early_rows = [r for r in joined if r["day"] in early]
    late_rows = [r for r in joined if r["day"] in late]
    chrono: dict[str, Any] = {"early_days": early, "late_days": late, "splits": {}}
    for label, rows in (("early", early_rows), ("late", late_rows)):
        if not rows:
            continue
        xa, ya, _ = _pair_stack(rows, "pim", "dcm")
        xb, yb, _ = _pair_stack(rows, "pim", "notional")
        xc, yc, _ = _pair_stack(rows, "vloop", "tcost")
        chrono["splits"][label] = {
            "corr_pim_dcm": pearson_spearman(xa, ya),
            "corr_pim_vlm": pearson_spearman(xb, yb),
            "corr_vloop_tcost": pearson_spearman(xc, yc),
        }
    chrono["sign_stable_pim_vlm"] = bool(
        np.sign(chrono["splits"].get("early", {}).get("corr_pim_vlm", {}).get("pearson", 0) or 0)
        == np.sign(chrono["splits"].get("late", {}).get("corr_pim_vlm", {}).get("pearson", 0) or 0)
        and np.isfinite(chrono["splits"].get("early", {}).get("corr_pim_vlm", {}).get("pearson", float("nan")))
        and np.isfinite(chrono["splits"].get("late", {}).get("corr_pim_vlm", {}).get("pearson", float("nan")))
    )

    # --- light Bayes on key corrs ---
    bayes = {}
    for name, block in (
        ("pim_dcm", dep.get("pim__dcm", {})),
        ("vloop_tcost", dep.get("vloop__tcost", {})),
        ("pim_vlm", dep.get("pim__notional", {})),
    ):
        pr = block.get("pearson")
        n = int(block.get("n") or 0)
        bayes[name] = fisher_z_normal_posterior(float(pr) if pr is not None else float("nan"), n)

    # --- candidate board ---
    candidates = _decide_candidates(incr, stress, kraken_sens, chrono, dep, leadlag, factor)

    return {
        "univariate": uni,
        "tod": tod,
        "dependence": dep,
        "lead_lag": leadlag,
        "incremental": incr,
        "vloop_tcost_stress": stress,
        "kraken_sensitivity": kraken_sens,
        "factor": factor,
        "chrono_split": chrono,
        "bayes_corr": bayes,
        "candidates": candidates,
        "per_day_leadlag_sample": {k: v[:2] for k, v in list(per_day_ll.items())[:2]},
    }


def _decide_candidates(
    incr: dict,
    stress: dict,
    kraken: dict,
    chrono: dict,
    dep: dict,
    leadlag: dict,
    factor: dict,
) -> dict[str, Any]:
    """Honest Hold/Kill for info.* — never Promote TOB-cross α."""
    out: dict[str, Any] = {}

    # info.object_leadlag_map
    ll_pim_ret = leadlag.get("pim->|mid_ret", {}).get("pooled", {})
    best = ll_pim_ret.get("best_corr")
    out["info.object_leadlag_map"] = {
        "type": "D",
        "lenses": ["info", "risk", "mm"],
        "decision": "Hold",
        "evidence": (
            f"lead-lag dig vs mid_ret/RV/notional/funding/basis on hourly panel; "
            f"PIM↔mid_ret best_corr≈{best} lag={ll_pim_ret.get('best_lag')} — "
            f"descriptive map only, not tradable IRF α"
        ),
        "use": "research tile / risk context — not sized signal",
    }

    # info.pim_dcm_incremental
    pr = incr.get("partial_pim_dcm_ctrl_rv", {}).get("partial_r")
    dr2 = incr.get("delta_r2_dcm_after_rv")
    raw = incr.get("raw_corr_pim_dcm", {}).get("pearson")
    # Kill if partial ≈0 and ΔR² tiny; else Hold
    if pr is not None and np.isfinite(pr) and abs(float(pr)) < 0.05 and (
        dr2 is None or not np.isfinite(dr2) or abs(float(dr2)) < 0.01
    ):
        dec = "Kill"
        note = f"DCM adds nothing after RV (partial_r≈{pr}, ΔR²≈{dr2})"
    else:
        dec = "Hold"
        note = f"partial corr(PIM,DCM|RV)≈{pr}; ΔR²(DCM|RV)≈{dr2}; raw corr≈{raw}"
    out["info.pim_dcm_incremental"] = {
        "type": "D",
        "lenses": ["info", "risk"],
        "decision": dec,
        "evidence": note,
        "use": "risk monitor join — DCM vs vol-driven PIM",
    }

    # info.elasticity_after_rv
    pr_e = incr.get("partial_pim_vlm_ctrl_rv", {}).get("partial_r")
    dr2_e = incr.get("delta_r2_vlm_after_rv")
    if pr_e is not None and np.isfinite(pr_e) and abs(float(pr_e)) < 0.05 and (
        dr2_e is None or not np.isfinite(dr2_e) or abs(float(dr2_e)) < 0.01
    ):
        dec_e = "Kill"
        note_e = f"VLM↔PIM vanishes after RV (partial≈{pr_e}, ΔR²≈{dr2_e})"
    else:
        dec_e = "Hold"
        note_e = f"partial corr(PIM,VLM|RV)≈{pr_e}; ΔR²≈{dr2_e}; chrono sign_stable={chrono.get('sign_stable_pim_vlm')}"
    out["info.elasticity_after_rv"] = {
        "type": "D",
        "lenses": ["info", "liq", "mm"],
        "decision": dec_e,
        "evidence": note_e,
        "use": "liquidity regime context after vol control — not Promote",
    }

    # info.vloop_tcost_stress_split
    c_calm = stress.get("corr_calm", {}).get("pearson")
    c_stress = stress.get("corr_stress", {}).get("pearson")
    out["info.vloop_tcost_stress_split"] = {
        "type": "D",
        "lenses": ["info", "liq", "exec"],
        "decision": "Hold",
        "evidence": f"corr(VLOOP,TCOST) calm≈{c_calm} vs stress≈{c_stress} (PIM q25/q75)",
        "use": "stress vs calm commonality tile — policy/monitor",
    }

    # info.kraken_spot_vs_2venue (trade_synth QUARANTINED)
    modes = kraken.get("modes") or {}
    n_spot = (modes.get("spot_l2") or {}).get("n_days", 0)
    n_2v = (modes.get("absent_2venue") or {}).get("n_days", 0)
    delta = kraken.get("delta_day_mean_pim_spot_minus_2venue")
    out["info.kraken_spot_vs_2venue"] = {
        "type": "D",
        "lenses": ["info", "cont", "risk"],
        "decision": "Hold",
        "evidence": (
            f"spot_l2 days={n_spot} absent_2venue={n_2v}; "
            f"Δday_mean_PIM(spot−2v)≈{delta}; "
            "trade_synth QUARANTINED (PROXY/NOT TOB)"
        ),
        "use": "feed-quality flag / spot subpanel vs 2-venue — never arb α on PROXY",
        "falsifier": "true Kraken futures quoted TOB for futures legs",
    }

    # info.day_factor_commonality
    pc1 = (factor.get("pim_tod_pca") or {}).get("pc1_explained")
    pc1b = (factor.get("day_feature_pca") or {}).get("pc1_explained")
    out["info.day_factor_commonality"] = {
        "type": "D",
        "lenses": ["info", "risk"],
        "decision": "Hold" if (pc1 and pc1 > 0.35) or (pc1b and pc1b > 0.35) else "Hold",
        "evidence": f"PIM ToD PCA PC1 explained≈{pc1}; day-feature PCA PC1≈{pc1b}",
        "use": "commonality / regime strip across UTC days",
    }

    # info.object_use_map (meta)
    out["info.object_use_map"] = {
        "type": "D",
        "lenses": ["info", "risk", "exec", "mm"],
        "decision": "Hold",
        "evidence": "APPLICATIONS.md use map — risk/exec/policy; 0 Promote",
        "use": "desk routing of objects to monitors vs throttle sketches",
    }

    # always Kill vanity α
    out["alpha.tob_cross_arb"] = {
        "type": "T",
        "lenses": ["exec"],
        "decision": "Kill",
        "evidence": "info dig does not create sized arb; detection ≠ executable",
        "use": "none",
    }

    promote_count = sum(1 for v in out.values() if v.get("decision") == "Promote")
    out["_rollup"] = {
        "promote_count": promote_count,
        "hold_count": sum(1 for k, v in out.items() if not k.startswith("_") and v.get("decision") == "Hold"),
        "kill_count": sum(1 for k, v in out.items() if not k.startswith("_") and v.get("decision") == "Kill"),
        "note": "Pass-2.5 info dig — 0 Promote; monitors / research tiles only",
    }
    return out


def write_figs(joined: list[dict[str, Any]], analysis: dict[str, Any]) -> list[str]:
    paths: list[str] = []

    # 1) lead-lag heatmap for carriers × mid_ret
    carriers = ["pim", "vloop", "tcost", "dcm"]
    lags = list(LAGS)
    mat = np.full((len(carriers), len(lags)), np.nan)
    for i, c in enumerate(carriers):
        ll = analysis["lead_lag"].get(f"{c}->|mid_ret", {}).get("pooled", {})
        corr = ll.get("corr") or []
        for j, _ in enumerate(lags):
            if j < len(corr):
                mat[i, j] = corr[j]
    fig, ax = plt.subplots(figsize=(8.5, 3.8))
    im = ax.imshow(mat, aspect="auto", cmap="RdBu_r", vmin=-0.6, vmax=0.6)
    ax.set_yticks(range(len(carriers)))
    ax.set_yticklabels(carriers)
    ax.set_xticks(range(len(lags)))
    ax.set_xticklabels([str(l) for l in lags])
    ax.set_xlabel("lag hours (y leads x if lag>0 on y=mid_ret)")
    ax.set_title("Lead-lag corr: objects vs mid returns (hourly)")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    paths.append(_savefig(fig, "fig_leadlag_midret.png"))

    # 2) incremental bar: raw vs partial
    labels = ["PIM↔DCM", "PIM↔DCM|RV", "PIM↔VLM", "PIM↔VLM|RV"]
    vals = [
        analysis["incremental"]["raw_corr_pim_dcm"].get("pearson"),
        analysis["incremental"]["partial_pim_dcm_ctrl_rv"].get("partial_r"),
        analysis["incremental"]["raw_corr_pim_vlm"].get("pearson"),
        analysis["incremental"]["partial_pim_vlm_ctrl_rv"].get("partial_r"),
    ]
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    ax.axhline(0, color="#888", lw=0.8)
    colors = ["#1f4e79", "#3d5a80", "#c55a11", "#ee6c4d"]
    ax.bar(labels, [v if v is not None and np.isfinite(v) else 0 for v in vals], color=colors)
    ax.set_ylabel("correlation")
    ax.set_title("Incremental info: raw vs RV-controlled partial corr")
    for i, v in enumerate(vals):
        if v is not None and np.isfinite(v):
            ax.text(i, v + (0.02 if v >= 0 else -0.04), f"{v:.2f}", ha="center", fontsize=9)
    fig.tight_layout()
    paths.append(_savefig(fig, "fig_incremental_partial.png"))

    # 3) ToD PIM / DCM
    tod = analysis["tod"]
    fig, ax = plt.subplots(figsize=(9, 3.8))
    ax.plot(tod["pim"]["hours"], tod["pim"]["means"], "o-", label="PIM", color="#1f4e79")
    ax.plot(tod["dcm"]["hours"], tod["dcm"]["means"], "s-", label="DCM̂", color="#c55a11")
    ax.set_xlabel("UTC hour")
    ax.set_ylabel("mean")
    ax.set_title("ToD profiles — PIM vs DCM̂ (pooled hours)")
    ax.legend(frameon=False)
    fig.tight_layout()
    paths.append(_savefig(fig, "fig_tod_pim_dcm.png"))

    # 4) Kraken mode comparison
    modes = analysis["kraken_sensitivity"].get("modes") or {}
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.6))
    metrics = [
        ("corr_pim_dcm", "PIM↔DCM"),
        ("corr_vloop_tcost", "VLOOP↔TCOST"),
        ("corr_pim_vlm", "PIM↔VLM"),
    ]
    mode_names = [m for m in ("spot_l2", "absent_2venue") if m in modes]
    for ax, (key, title) in zip(axes, metrics):
        ys = []
        for m in mode_names:
            ys.append((modes[m].get(key) or {}).get("pearson"))
        ax.axhline(0, color="#888", lw=0.8)
        ax.bar(
            mode_names,
            [y if y is not None and np.isfinite(y) else 0 for y in ys],
            color=["#3d5a80", "#ee6c4d"][: len(mode_names)],
        )
        ax.set_title(title)
        ax.set_ylim(-1, 1)
        for i, y in enumerate(ys):
            if y is not None and np.isfinite(y):
                ax.text(i, y + 0.05, f"{y:.2f}", ha="center", fontsize=9)
    fig.suptitle("Kraken spot_l2 vs absent_2venue (trade_synth QUARANTINED)", fontsize=11)
    fig.tight_layout()
    paths.append(_savefig(fig, "fig_kraken_mode_sensitivity.png"))

    # 5) stress vs calm VLOOP-TCOST scatter
    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    vl, tc, _ = _pair_stack(joined, "vloop", "tcost")
    pim = _pair_stack(joined, "vloop", "pim")[1]
    m = np.isfinite(vl) & np.isfinite(tc) & np.isfinite(pim)
    ql = analysis["vloop_tcost_stress"]["q_low"]
    qh = analysis["vloop_tcost_stress"]["q_high"]
    calm = m & (pim <= ql)
    stress = m & (pim >= qh)
    ax.scatter(vl[calm], tc[calm], s=18, alpha=0.55, label="calm (PIM≤q25)", color="#3d5a80")
    ax.scatter(vl[stress], tc[stress], s=18, alpha=0.55, label="stress (PIM≥q75)", color="#ee6c4d")
    ax.set_xlabel("VLOOP")
    ax.set_ylabel("TCOST")
    ax.set_title("VLOOP↔TCOST by PIM stress regime")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    paths.append(_savefig(fig, "fig_vloop_tcost_stress.png"))

    # 6) day factor PC1 scores
    pca = analysis["factor"].get("day_feature_pca") or {}
    scores = pca.get("pc1_row_scores") or {}
    if scores:
        fig, ax = plt.subplots(figsize=(8, 3.6))
        ds = list(scores.keys())
        vs = [scores[d] for d in ds]
        ax.bar(ds, vs, color="#1f4e79")
        ax.axhline(0, color="#888", lw=0.8)
        ax.set_ylabel("PC1 score")
        ax.set_title(f"Day-feature commonality PC1 (expl≈{pca.get('pc1_explained'):.2f})")
        ax.tick_params(axis="x", rotation=45)
        fig.tight_layout()
        paths.append(_savefig(fig, "fig_day_factor_pc1.png"))

    # 7) use-map style board (text fig)
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.axis("off")
    lines = [
        "cd_me info use map (Pass-2.5) — 0 Promote",
        "",
        "PIM / VLOOP     → risk monitor (LOP stress) · never sized arb",
        "TCOST           → exec friction context · SOR cost awareness",
        "DCM̂            → constraint regime strip · join with PIM",
        "VLM↔PIM          → liq elasticity monitor (after RV control)",
        "Kraken mode     → feed-quality flag (spot_l2 vs trade_synth)",
        "paper_shadow    → wire Promote only (still 0); hypothetical monitors OK",
    ]
    ax.text(0.02, 0.95, "\n".join(lines), va="top", family="monospace", fontsize=10)
    fig.tight_layout()
    paths.append(_savefig(fig, "fig_use_map.png"))

    return paths


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default="ETH")
    args = ap.parse_args()
    ensure_env()
    OUT.mkdir(parents=True, exist_ok=True)
    FIGS.mkdir(parents=True, exist_ok=True)

    print("building joined panel…", flush=True)
    joined, meta = build_joined_panel(args.symbol)
    print(f"  days={meta['n_days']} {meta['days']}", flush=True)
    _write(OUT / "joined_hourly.json", {"meta": meta, "rows": joined})

    print("analyzing…", flush=True)
    analysis = analyze(joined)
    figs = write_figs(joined, analysis)
    analysis["figs"] = figs
    analysis["meta"] = meta
    _write(OUT / "info_features.json", analysis)
    _write(OUT / "candidates.json", analysis["candidates"])

    # short EXP_REPORT
    cands = analysis["candidates"]
    lines = [
        "# EXP_REPORT — info features (Pass 2.5)",
        "",
        f"- Symbol: **{args.symbol}** · days: {meta['n_days']} · reuse Pass-2 panel",
        f"- Artifacts: `out/info_features/`",
        f"- Promote count: **{cands.get('_rollup', {}).get('promote_count', 0)}**",
        "",
        "## Candidates",
        "",
        "| id | decision | use |",
        "|----|----------|-----|",
    ]
    for k, v in cands.items():
        if k.startswith("_"):
            continue
        lines.append(f"| `{k}` | **{v.get('decision')}** | {v.get('use', '')} |")
    lines += [
        "",
        "## Key numbers",
        "",
        f"- partial corr(PIM,DCM|RV) = `{analysis['incremental']['partial_pim_dcm_ctrl_rv'].get('partial_r')}`",
        f"- ΔR² DCM after RV = `{analysis['incremental'].get('delta_r2_dcm_after_rv')}`",
        f"- partial corr(PIM,VLM|RV) = `{analysis['incremental']['partial_pim_vlm_ctrl_rv'].get('partial_r')}`",
        f"- ΔR² VLM after RV = `{analysis['incremental'].get('delta_r2_vlm_after_rv')}`",
        f"- VLOOP↔TCOST calm/stress = `{analysis['vloop_tcost_stress']['corr_calm'].get('pearson')}` / "
        f"`{analysis['vloop_tcost_stress']['corr_stress'].get('pearson')}`",
        f"- PIM ToD PC1 explained = `{(analysis['factor'].get('pim_tod_pca') or {}).get('pc1_explained')}`",
        "",
        "## Honesty",
        "",
        "- ClickHouse MCP banned · warehouse/marks only",
        "- Never soft-Promote TOB-cross α (esp. Kraken trade_synth)",
        "",
    ]
    (OUT / "EXP_REPORT.md").write_text("\n".join(lines))
    print("wrote", OUT / "info_features.json")
    print("candidates:", json.dumps(_jsonable(cands.get("_rollup")), indent=2))
    for k, v in cands.items():
        if k.startswith("_"):
            continue
        print(f"  {k}: {v.get('decision')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
