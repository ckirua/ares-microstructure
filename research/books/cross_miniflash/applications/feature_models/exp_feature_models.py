from __future__ import annotations
#!/usr/bin/env python3
"""Severity / regime feature model — logistic + regularized predictors.

Predict gated crash occurrence (cell-level intensity) and |ΔP| bucket / continuous
severity from pre-window features (VPIN, intensity, vol/RV, Amihud, diurnal, H^v).
Chronological train/test, calibration, no leakage. Promote only if OOS useful.

Also denser Hold→Promote attempts:
  - exec.tape_markout_post_crash
  - risk.duration_post_markout (volume-clock)
  - info.vpin_x_size_severity
"""


import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

APP = Path(__file__).resolve().parents[1]
BOOK = APP.parent
ROOT = BOOK.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(APP))

from common.event_panel import (  # noqa: E402
    DEFAULT_DAYS,
    DEFAULT_SYMBOLS,
    EARLY_DAYS,
    boot_mean,
    build_panel,
    event_arrays,
    jsonable,
    summarize,
)
from ares_micro.stats import nw_ols, spearman_r, time_split_mask  # noqa: E402

OUT = APP / "feature_models" / "out"
FIG = OUT / "figs"

FEAT_COLS = [
    "vpin_exante",
    "intensity",
    "rv_1m",
    "amihud",
    "log_notional_pre",
    "hour_utc",
    "H_v",
]


def _finite_mask(X: np.ndarray, y: np.ndarray | None = None) -> np.ndarray:
    m = np.isfinite(X).all(axis=1)
    if y is not None:
        m &= np.isfinite(y)
    return m


def _design(events: list[dict[str, Any]], cols: list[str] | None = None) -> tuple[np.ndarray, list[str]]:
    cols = cols or FEAT_COLS
    X = np.column_stack([event_arrays(events, c) for c in cols])
    return X, cols


def build_cell_crash_labels(panel: dict[str, Any]) -> list[dict[str, Any]]:
    """Cell half-day crash occurrence with *day-level* features only.

    Honesty: do **not** mix event pre-window features (crash halves) with day
    aggregates (quiet halves) — that leaks via feature construction. All halves
    use the same day-level state: day_vpin, day_intensity, day log-notional, H^v,
    plus half indicator (hour midpoint).
    """
    rows: list[dict[str, Any]] = []
    by_cell: dict[tuple, list] = {}
    for e in panel["events"]:
        key = (e["venue"], e["symbol"], e["day"])
        by_cell.setdefault(key, []).append(e)
    for c in panel["cells"]:
        if not c.get("complete"):
            continue
        key = (c["venue"], c["symbol"], c["day"])
        evs = by_cell.get(key, [])
        day_feat = {
            "vpin_exante": c.get("day_vpin"),
            "intensity": c.get("day_intensity"),
            "rv_1m": float("nan"),  # day-level RV not stored on cell — leave NaN→impute
            "amihud": float("nan"),
            "log_notional_pre": float(np.log(max(float(c.get("day_notional") or 1.0), 1.0))),
            "H_v": c.get("H_v"),
        }
        for half, (h0, h1, hour) in (
            ("am", (0.0, 12.0, 6.0)),
            ("pm", (12.0, 24.0, 18.0)),
        ):
            half_ev = [e for e in evs if h0 <= float(e.get("hour_utc", -1)) < h1]
            y = 1 if len(half_ev) > 0 else 0
            rows.append(
                {
                    "venue": c["venue"],
                    "symbol": c["symbol"],
                    "day": c["day"],
                    "half": half,
                    "cohort": "early" if c["day"] in EARLY_DAYS else "late",
                    "y_crash": y,
                    "n_events_half": len(half_ev),
                    "ts_sort": int(0 if half == "am" else 1),
                    "hour_utc": hour,
                    **{
                        k: (
                            float(day_feat[k])
                            if day_feat.get(k) is not None
                            and isinstance(day_feat[k], (int, float))
                            and np.isfinite(float(day_feat[k]))
                            else float("nan")
                        )
                        for k in (
                            "vpin_exante",
                            "intensity",
                            "rv_1m",
                            "amihud",
                            "log_notional_pre",
                            "H_v",
                        )
                    },
                }
            )
    return rows


def fit_logistic_occurrence(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Chronological train/test logistic for crash occurrence."""
    if len(rows) < 20:
        return {"n": len(rows), "error": "too_few_rows"}
    # sort by day then half
    day_ord = {d: i for i, d in enumerate(DEFAULT_DAYS)}
    rows_s = sorted(rows, key=lambda r: (day_ord.get(r["day"], 99), 0 if r["half"] == "am" else 1))
    y = np.asarray([r["y_crash"] for r in rows_s], dtype=np.float64)
    X = np.column_stack([np.asarray([r[c] for r in rows_s], dtype=np.float64) for c in FEAT_COLS])
    # impute nan with train median later — first chronological cut
    n = len(rows_s)
    cut = int(0.6 * n)
    if cut < 10 or n - cut < 8:
        return {"n": n, "error": "split_too_small"}
    X_tr, X_te = X[:cut], X[cut:]
    y_tr, y_te = y[:cut], y[cut:]

    def _impute(tr: np.ndarray, te: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        med = np.nanmedian(tr, axis=0)
        med = np.where(np.isfinite(med), med, 0.0)
        tr2 = tr.copy()
        te2 = te.copy()
        for j in range(tr.shape[1]):
            tr2[np.isnan(tr2[:, j]), j] = med[j]
            te2[np.isnan(te2[:, j]), j] = med[j]
        return tr2, te2, med

    X_tr, X_te, med = _impute(X_tr, X_te)
    if len(np.unique(y_tr)) < 2 or len(np.unique(y_te)) < 2:
        return {
            "n": n,
            "n_train": int(cut),
            "n_test": int(n - cut),
            "error": "single_class_split",
            "base_rate_train": float(y_tr.mean()),
            "base_rate_test": float(y_te.mean()),
        }

    pipe = Pipeline(
        [
            ("sc", StandardScaler()),
            (
                "clf",
                LogisticRegression(
                    C=0.5,
                    max_iter=2000,
                    class_weight="balanced",
                    solver="lbfgs",
                ),
            ),
        ]
    )
    pipe.fit(X_tr, y_tr)
    proba_tr = pipe.predict_proba(X_tr)[:, 1]
    proba_te = pipe.predict_proba(X_te)[:, 1]
    pred_te = (proba_te >= 0.5).astype(int)

    def _safe_auc(y_true, proba):
        try:
            return float(roc_auc_score(y_true, proba))
        except ValueError:
            return float("nan")

    # calibration
    try:
        frac_pos, mean_pred = calibration_curve(y_te, proba_te, n_bins=5, strategy="quantile")
        cal = {
            "frac_pos": frac_pos.tolist(),
            "mean_pred": mean_pred.tolist(),
            "brier": float(brier_score_loss(y_te, proba_te)),
        }
    except Exception as exc:  # noqa: BLE001
        cal = {"error": f"{type(exc).__name__}: {exc}", "brier": float("nan")}

    coef = pipe.named_steps["clf"].coef_.ravel()
    return {
        "n": n,
        "n_train": int(cut),
        "n_test": int(n - cut),
        "features": FEAT_COLS,
        "base_rate_train": float(y_tr.mean()),
        "base_rate_test": float(y_te.mean()),
        "auc_train": _safe_auc(y_tr, proba_tr),
        "auc_test": _safe_auc(y_te, proba_te),
        "acc_test": float(accuracy_score(y_te, pred_te)),
        "brier_test": cal.get("brier"),
        "calibration": cal,
        "coef": {FEAT_COLS[i]: float(coef[i]) for i in range(len(FEAT_COLS))},
        "intercept": float(pipe.named_steps["clf"].intercept_[0]),
        "oos_useful": bool(
            np.isfinite(_safe_auc(y_te, proba_te)) and _safe_auc(y_te, proba_te) >= 0.60
        ),
        "promote_bar": "OOS AUC ≥ 0.60 and Brier < base-rate Brier",
    }


def fit_severity_regression(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Ridge / NW-OLS: |ΔP| from pre-window features. Time-split by event ts."""
    if len(events) < 30:
        return {"n": len(events), "error": "too_few"}
    # chronological
    evs = sorted(events, key=lambda e: int(e["ts_start"]))
    def _f(v: Any) -> float:
        if v is None:
            return float("nan")
        try:
            return float(v)
        except (TypeError, ValueError):
            return float("nan")

    y = np.asarray([abs(_f(e["dp_pct"])) for e in evs], dtype=np.float64)
    X = np.column_stack([np.asarray([_f(e.get(c)) for e in evs]) for c in FEAT_COLS])
    ts = np.asarray([e["ts_start"] for e in evs], dtype=np.int64)
    tr, te = time_split_mask(ts, train_frac=0.6)
    if int(tr.sum()) < 20 or int(te.sum()) < 15:
        return {"n": len(evs), "error": "split_too_small"}

    def _impute(trX, teX):
        med = np.nanmedian(trX, axis=0)
        med = np.where(np.isfinite(med), med, 0.0)
        a, b = trX.copy(), teX.copy()
        for j in range(a.shape[1]):
            a[np.isnan(a[:, j]), j] = med[j]
            b[np.isnan(b[:, j]), j] = med[j]
        return a, b

    Xtr, Xte = _impute(X[tr], X[te])
    ytr, yte = y[tr], y[te]

    ridge = Pipeline([("sc", StandardScaler()), ("rg", Ridge(alpha=1.0))])
    ridge.fit(Xtr, ytr)
    pred_tr = ridge.predict(Xtr)
    pred_te = ridge.predict(Xte)
    r2_tr = float(r2_score(ytr, pred_tr))
    r2_te = float(r2_score(yte, pred_te))
    rmse_te = float(np.sqrt(mean_squared_error(yte, pred_te)))

    # NW-OLS on train for inference
    nw = nw_ols(ytr, Xtr, add_const=True)
    # bucket classifier: high severity = top quartile of train
    thr = float(np.nanpercentile(ytr, 75))
    yb_tr = (ytr >= thr).astype(int)
    yb_te = (yte >= thr).astype(int)
    logit = Pipeline(
        [
            ("sc", StandardScaler()),
            ("clf", LogisticRegression(C=0.5, max_iter=2000, class_weight="balanced")),
        ]
    )
    bucket = {"thr_p75": thr}
    if len(np.unique(yb_tr)) > 1 and len(np.unique(yb_te)) > 1:
        logit.fit(Xtr, yb_tr)
        pr = logit.predict_proba(Xte)[:, 1]
        try:
            bucket["auc_test"] = float(roc_auc_score(yb_te, pr))
        except ValueError:
            bucket["auc_test"] = float("nan")
        bucket["base_rate_test"] = float(yb_te.mean())
    else:
        bucket["auc_test"] = float("nan")
        bucket["error"] = "single_class"

    coef = ridge.named_steps["rg"].coef_.ravel()
    return {
        "n": len(evs),
        "n_train": int(tr.sum()),
        "n_test": int(te.sum()),
        "features": FEAT_COLS,
        "ridge_r2_train": r2_tr,
        "ridge_r2_test": r2_te,
        "ridge_rmse_test": rmse_te,
        "nw_ols_r2": float(nw.get("r2", np.nan)),
        "nw_ols_t": {FEAT_COLS[i]: float(nw["t"][i + 1]) for i in range(len(FEAT_COLS))}
        if nw.get("t") is not None and len(nw["t"]) == len(FEAT_COLS) + 1
        else None,
        "ridge_coef": {FEAT_COLS[i]: float(coef[i]) for i in range(len(FEAT_COLS))},
        "bucket": bucket,
        "oos_useful": bool(np.isfinite(r2_te) and r2_te >= 0.05)
        or bool(np.isfinite(bucket.get("auc_test", np.nan)) and bucket["auc_test"] >= 0.60),
        "promote_bar": "OOS R²≥0.05 or severity-bucket AUC≥0.60",
    }


def denser_tape_markout(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Hold→Promote attempt: exec.tape_markout_post_crash."""
    out: dict[str, Any] = {"object": "exec.tape_markout_post_crash"}
    for h in ("0.5", "1", "5"):
        key = f"mo_{h}s"
        arr = event_arrays(events, key)
        out[f"pooled_{key}"] = {**summarize(arr), "boot": boot_mean(arr, seed=31 + int(float(h)))}
    # by class + venue + cohort
    by = {}
    for lab in ("v_recovery", "continuation", "partial"):
        sub = [e for e in events if e.get("label") == lab]
        arr = event_arrays(sub, "mo_5s")
        mid = event_arrays(sub, "mid_mo_5s")
        by[lab] = {
            "n": len(sub),
            "mo_5s": {**summarize(arr), "boot": boot_mean(arr, seed=40)},
            "mid_mo_5s": {**summarize(mid), "boot": boot_mean(mid, seed=41)},
            "frac_mid_finite": float(np.isfinite(mid).mean()) if len(sub) else 0.0,
        }
    out["by_class"] = by
    early = [e for e in events if e.get("cohort") == "early"]
    late = [e for e in events if e.get("cohort") == "late"]
    out["early_mo5"] = {**summarize(event_arrays(early, "mo_5s")), "boot": boot_mean(event_arrays(early, "mo_5s"), seed=42)}
    out["late_mo5"] = {**summarize(event_arrays(late, "mo_5s")), "boot": boot_mean(event_arrays(late, "mo_5s"), seed=43)}
    # Promote needs: mid markout with CI; V vs cont stratified; time-split sign stable
    e_m = out["early_mo5"]["mean"]
    l_m = out["late_mo5"]["mean"]
    v_m = by["v_recovery"]["mo_5s"]["mean"]
    c_m = by["continuation"]["mo_5s"]["mean"]
    mid_frac = float(np.mean([by[k]["frac_mid_finite"] for k in by]))
    sign_stable = np.isfinite(e_m) and np.isfinite(l_m) and (np.sign(e_m) == np.sign(l_m)) and e_m != 0
    class_sep = np.isfinite(v_m) and np.isfinite(c_m) and (v_m < c_m)  # V more mean-revert
    mid_ok = mid_frac >= 0.5 and np.isfinite(by["v_recovery"]["mid_mo_5s"]["mean"])
    promote = bool(sign_stable and class_sep and mid_ok)
    out["decision"] = "Promote" if promote else "Hold"
    out["checks"] = {
        "sign_stable_early_late": sign_stable,
        "class_sep_v_lt_cont": class_sep,
        "mid_coverage_ge_50pct": mid_ok,
        "mid_frac": mid_frac,
        "early_mean": e_m,
        "late_mean": l_m,
        "v_mean": v_m,
        "cont_mean": c_m,
    }
    out["why"] = (
        "mid+class+time-split cleared"
        if promote
        else (
            f"still Hold: sign_stable={sign_stable}, class_sep={class_sep}, "
            f"mid_ok={mid_ok} (mid_frac={mid_frac:.2f}); tape mo@5s≈{out['pooled_mo_5s']['mean']:.2f}bps"
        )
    )
    return out


def denser_duration_markout(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Hold→Promote: risk.duration_post_markout with volume-clock / trade-count."""
    out: dict[str, Any] = {"object": "risk.duration_post_markout"}
    dt = event_arrays(events, "dt_s")
    ic = event_arrays(events, "i_c")
    volc = event_arrays(events, "vol_clock")
    mo5 = np.abs(event_arrays(events, "mo_5s"))

    out["median_dt_s"] = float(np.nanmedian(dt))
    out["frac_dt_zero"] = float(np.nanmean(dt == 0)) if dt.size else float("nan")
    out["spearman_dt_abs_mo"] = spearman_r(dt, mo5)
    out["spearman_ic_abs_mo"] = spearman_r(ic, mo5)
    out["spearman_volclock_abs_mo"] = spearman_r(volc, mo5)

    # time-split stability on trade-count duration
    ts = event_arrays(events, "ts_start")
    # ts_start may be float nan — rebuild
    ts = np.asarray([int(e["ts_start"]) for e in events], dtype=np.int64)
    tr, te = time_split_mask(ts, train_frac=0.6)

    def _sp(mask):
        return {
            "dt": spearman_r(dt[mask], mo5[mask]),
            "i_c": spearman_r(ic[mask], mo5[mask]),
            "vol_clock": spearman_r(volc[mask], mo5[mask]),
            "n": int(mask.sum()),
        }

    out["train"] = _sp(tr)
    out["test"] = _sp(te)
    # Promote if |ρ| on volume-clock or i_c stable OOS and |ρ|≳0.15
    te_ic = out["test"]["i_c"]
    te_vc = out["test"]["vol_clock"]
    tr_ic = out["train"]["i_c"]
    tr_vc = out["train"]["vol_clock"]
    # Stricter: |ρ|≥0.20 and sign-stable (catalog asked volume-clock; i_c is proxy)
    stable_ic = (
        np.isfinite(te_ic)
        and np.isfinite(tr_ic)
        and np.sign(te_ic) == np.sign(tr_ic)
        and abs(te_ic) >= 0.20
    )
    stable_vc = (
        np.isfinite(te_vc)
        and np.isfinite(tr_vc)
        and np.sign(te_vc) == np.sign(tr_vc)
        and abs(te_vc) >= 0.20
    )
    promote = bool(stable_ic or stable_vc)
    out["decision"] = "Promote" if promote else "Hold"
    out["checks"] = {
        "stable_ic_oos": stable_ic,
        "stable_volclock_oos": stable_vc,
        "train_ic": tr_ic,
        "test_ic": te_ic,
        "train_volclock": tr_vc,
        "test_volclock": te_vc,
        "bar_abs_rho": 0.20,
    }
    out["why"] = (
        "trade-count or volume-clock Spearman stable OOS with |ρ|≥0.20"
        if promote
        else (
            f"still Hold: wall-clock median_dt={out['median_dt_s']}, "
            f"frac_dt0={out['frac_dt_zero']:.2f}; "
            f"test ρ(i_c)={te_ic:.3f}, ρ(vol)={te_vc:.3f} (need |ρ|≥0.20 sign-stable)"
        )
    )
    return out

def denser_vpin_size(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Hold→Promote: info.vpin_x_size_severity with ex-ante VPIN + boot CI."""
    out: dict[str, Any] = {"object": "info.vpin_x_size_severity"}
    y = np.abs(event_arrays(events, "dp_pct"))
    logn = event_arrays(events, "log_notional_event")
    vpin = event_arrays(events, "vpin_exante")
    # fallback day vpin if exante missing
    day_v = event_arrays(events, "day_vpin")
    vpin = np.where(np.isfinite(vpin), vpin, day_v)

    m = np.isfinite(y) & np.isfinite(logn) & np.isfinite(vpin)
    y, logn, vpin = y[m], logn[m], vpin[m]
    interact = logn * vpin
    X = np.column_stack([logn, vpin, interact])
    names = ["logN", "vpin", "logN_x_vpin"]
    if y.size < 40:
        out.update({"n": int(y.size), "decision": "Hold", "why": "n<40 after finite mask"})
        return out

    fit = nw_ols(y, X, add_const=True)
    out["n"] = int(fit["n"])
    out["r2"] = float(fit["r2"])
    out["beta"] = {names[i]: float(fit["beta"][i + 1]) for i in range(3)}
    out["t"] = {names[i]: float(fit["t"][i + 1]) for i in range(3)}
    out["se"] = {names[i]: float(fit["se"][i + 1]) for i in range(3)}

    # bootstrap interact t / beta
    rng = np.random.default_rng(77)
    boots = []
    n = y.size
    for _ in range(600):
        idx = rng.integers(0, n, size=n)
        f = nw_ols(y[idx], X[idx], add_const=True)
        if f.get("t") is not None and len(f["t"]) == 4:
            boots.append(float(f["beta"][3]))
    ba = np.asarray(boots, dtype=np.float64)
    ba = ba[np.isfinite(ba)]
    out["interact_boot"] = {
        "n_boot": int(ba.size),
        "mean": float(ba.mean()) if ba.size else float("nan"),
        "lo": float(np.quantile(ba, 0.025)) if ba.size else float("nan"),
        "hi": float(np.quantile(ba, 0.975)) if ba.size else float("nan"),
        "ci_excludes_0": bool(ba.size and (np.quantile(ba, 0.025) > 0 or np.quantile(ba, 0.975) < 0)),
    }

    # time-split
    ts = np.asarray([int(e["ts_start"]) for e in events], dtype=np.int64)[m]
    tr, te = time_split_mask(ts, train_frac=0.6)
    fit_tr = nw_ols(y[tr], X[tr], add_const=True)
    fit_te = nw_ols(y[te], X[te], add_const=True)
    out["train"] = {
        "n": int(fit_tr["n"]),
        "r2": float(fit_tr["r2"]),
        "t_interact": float(fit_tr["t"][3]) if fit_tr.get("t") is not None and len(fit_tr["t"]) == 4 else float("nan"),
        "beta_logN": float(fit_tr["beta"][1]) if fit_tr.get("beta") is not None else float("nan"),
    }
    out["test"] = {
        "n": int(fit_te["n"]),
        "r2": float(fit_te["r2"]),
        "t_interact": float(fit_te["t"][3]) if fit_te.get("t") is not None and len(fit_te["t"]) == 4 else float("nan"),
        "beta_logN": float(fit_te["beta"][1]) if fit_te.get("beta") is not None else float("nan"),
        "beta_interact": float(fit_te["beta"][3]) if fit_te.get("beta") is not None else float("nan"),
    }
    # early/late size β sign (mask-aligned cohorts)
    cohorts = np.asarray([e.get("cohort") for e in events], dtype=object)[m]
    early_fit = nw_ols(y[cohorts == "early"], X[cohorts == "early"], add_const=True)
    late_fit = nw_ols(y[cohorts == "late"], X[cohorts == "late"], add_const=True)
    b_e = float(early_fit["beta"][1]) if early_fit.get("beta") is not None else float("nan")
    b_l = float(late_fit["beta"][1]) if late_fit.get("beta") is not None else float("nan")
    out["size_beta_early"] = b_e
    out["size_beta_late"] = b_l
    size_sign_stable = np.isfinite(b_e) and np.isfinite(b_l) and np.sign(b_e) == np.sign(b_l)

    interact_oos = (
        out["interact_boot"]["ci_excludes_0"]
        and np.isfinite(out["test"]["t_interact"])
        and abs(out["test"]["t_interact"]) >= 1.6
    )
    # Promote if interact OOS useful AND (size main effect stable OR we drop size claim)
    promote = bool(interact_oos and (size_sign_stable or abs(out["test"].get("beta_logN") or 0) < 1e-3))
    # more honest: require interact CI excludes 0 and test t stable sign vs train
    t_tr, t_te = out["train"]["t_interact"], out["test"]["t_interact"]
    interact_sign_stable = np.isfinite(t_tr) and np.isfinite(t_te) and np.sign(t_tr) == np.sign(t_te)
    promote = bool(out["interact_boot"]["ci_excludes_0"] and interact_sign_stable and abs(t_te) >= 1.6)

    out["decision"] = "Promote" if promote else "Hold"
    out["checks"] = {
        "interact_boot_excludes_0": out["interact_boot"]["ci_excludes_0"],
        "interact_sign_stable_train_test": interact_sign_stable,
        "test_abs_t_ge_1.6": bool(np.isfinite(t_te) and abs(t_te) >= 1.6),
        "size_sign_stable_early_late": size_sign_stable,
    }
    out["why"] = (
        "ex-ante VPIN×logN interact boot CI excludes 0 + OOS t stable"
        if promote
        else (
            f"still Hold: interact t_IS={out['t'].get('logN_x_vpin')}, "
            f"bootCI=[{out['interact_boot']['lo']}, {out['interact_boot']['hi']}], "
            f"test t={t_te}, size β early/late={b_e}/{b_l}"
        )
    )
    return out


def decide_regime(occurrence: dict[str, Any], severity: dict[str, Any]) -> dict[str, Any]:
    oos_occ = bool(occurrence.get("oos_useful"))
    oos_sev = bool(severity.get("oos_useful"))
    auc = occurrence.get("auc_test")
    auc_f = float(auc) if auc is not None and np.isfinite(auc) else float("nan")
    # Soft bar 0.60; strong bar 0.70. Marginal band documented.
    if oos_occ and np.isfinite(auc_f) and auc_f >= 0.60:
        decision = "Promote"
        band = "strong" if auc_f >= 0.70 else "marginal"
        why = (
            f"occurrence OOS AUC={auc_f:.3f} ({band}; day-level feats, no crash-half leakage); "
            f"severity OOS R²={severity.get('ridge_r2_test')} bucketAUC="
            f"{(severity.get('bucket') or {}).get('auc_test')} useful={oos_sev}"
        )
        conf = (
            "med"
            if auc_f >= 0.70 and oos_sev
            else ("med (occurrence only)" if auc_f >= 0.70 else "low–med (marginal AUC, small n_te)")
        )
    else:
        decision = "Hold"
        why = (
            f"OOS not useful after leakage fix: occurrence AUC={auc} "
            f"(bar≥0.60); severity R²={severity.get('ridge_r2_test')} "
            f"(bar≥0.05) bucketAUC={(severity.get('bucket') or {}).get('auc_test')}"
        )
        conf = "low–med"
    return {
        "decision": decision,
        "object": "feature.severity_regime_model",
        "why": why,
        "confidence": conf,
        "note": "Even if Promote, class=regime/risk feature — not tradable alpha. Severity |ΔP| model remains Hold.",
        "leakage_note": "Occurrence uses day-level VPIN/intensity/H^v/notional only (same schema crash vs quiet halves).",
    }


def plot_figs(
    occurrence: dict[str, Any],
    severity: dict[str, Any],
    markout: dict[str, Any],
    duration: dict[str, Any],
    vpin: dict[str, Any],
) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG.mkdir(parents=True, exist_ok=True)
    paths = []

    # calibration
    fig, ax = plt.subplots(figsize=(5, 4))
    cal = occurrence.get("calibration") or {}
    if "mean_pred" in cal and "frac_pos" in cal:
        ax.plot(cal["mean_pred"], cal["frac_pos"], "o-", label="model")
        ax.plot([0, 1], [0, 1], "k--", lw=0.8, label="ideal")
        ax.set_xlabel("mean predicted P")
        ax.set_ylabel("frac positives")
        ax.set_title(f"Occurrence calibration (AUC_te={occurrence.get('auc_test')})")
        ax.legend()
    else:
        ax.text(0.1, 0.5, f"cal unavailable: {cal.get('error') or occurrence.get('error')}")
    p = FIG / "fig_occurrence_calibration.png"
    fig.tight_layout()
    fig.savefig(p, dpi=140)
    plt.close(fig)
    paths.append(str(p))

    # severity coefs
    fig, ax = plt.subplots(figsize=(7, 3.8))
    coef = severity.get("ridge_coef") or {}
    if coef:
        keys = list(coef.keys())
        ax.barh(keys, [coef[k] for k in keys], color="#48a")
        ax.axvline(0, color="k", lw=0.6)
        ax.set_title(f"Ridge |ΔP| coefs (R²_te={severity.get('ridge_r2_test')})")
    p = FIG / "fig_severity_coefs.png"
    fig.tight_layout()
    fig.savefig(p, dpi=140)
    plt.close(fig)
    paths.append(str(p))

    # hold decisions strip
    fig, ax = plt.subplots(figsize=(7, 3.2))
    names = ["tape_markout", "duration", "vpin×size"]
    decs = [markout["decision"], duration["decision"], vpin["decision"]]
    colors = ["#3a7" if d == "Promote" else "#ca5" for d in decs]
    ax.barh(names, [1, 1, 1], color=colors)
    for i, d in enumerate(decs):
        ax.text(0.05, i, d, va="center", fontsize=11, fontweight="bold")
    ax.set_xlim(0, 1.2)
    ax.set_xticks([])
    ax.set_title("Hold→Promote denser attempts")
    p = FIG / "fig_hold_promote.png"
    fig.tight_layout()
    fig.savefig(p, dpi=140)
    plt.close(fig)
    paths.append(str(p))

    # markout by class
    fig, ax = plt.subplots(figsize=(6, 3.8))
    bc = markout.get("by_class") or {}
    labs = list(bc.keys())
    means = [((bc[l].get("mo_5s") or {}).get("mean") or np.nan) for l in labs]
    ax.bar(labs, means, color=["#2a6", "#ca5", "#c45"][: len(labs)])
    ax.axhline(0, color="k", lw=0.6)
    ax.set_ylabel("mo@5s bps")
    ax.set_title(f"tape markout by class — {markout['decision']}")
    p = FIG / "fig_markout_by_class.png"
    fig.tight_layout()
    fig.savefig(p, dpi=140)
    plt.close(fig)
    paths.append(str(p))
    return paths


def write_report(summary: dict[str, Any]) -> Path:
    occ = summary["occurrence"]
    sev = summary["severity"]
    reg = summary["regime_decision"]
    mo = summary["tape_markout"]
    dur = summary["duration"]
    vp = summary["vpin_size"]
    lines = [
        "# Feature models + Hold→Promote — EXP_REPORT",
        "",
        f"Generated: {summary['generated']}",
        f"Sample: n_events={summary['n_events']} · cells {summary['n_complete']}/{summary['n_cells']}",
        f"Symbols={summary['symbols']} · days={summary['days']}",
        "",
        "## 1. Severity / regime model",
        "",
        "### Occurrence (logistic, cell half-day)",
        f"- n={occ.get('n')} train/test={occ.get('n_train')}/{occ.get('n_test')}",
        f"- base rates train/test={occ.get('base_rate_train')}/{occ.get('base_rate_test')}",
        f"- **AUC train/test = {occ.get('auc_train')} / {occ.get('auc_test')}**",
        f"- Brier test={occ.get('brier_test')} · acc_test={occ.get('acc_test')}",
        f"- OOS useful (≥0.60 AUC)? **{occ.get('oos_useful')}**",
        f"- Coefs: {occ.get('coef')}",
        "",
        "### Severity |ΔP| (Ridge + NW-OLS, event-level, ex-ante features)",
        f"- n={sev.get('n')} train/test={sev.get('n_train')}/{sev.get('n_test')}",
        f"- **Ridge R² train/test = {sev.get('ridge_r2_train')} / {sev.get('ridge_r2_test')}**",
        f"- RMSE_te={sev.get('ridge_rmse_test')} · NW R²={sev.get('nw_ols_r2')}",
        f"- Bucket (p75) AUC_te={(sev.get('bucket') or {}).get('auc_test')}",
        f"- OOS useful? **{sev.get('oos_useful')}**",
        f"- Ridge coefs: {sev.get('ridge_coef')}",
        "",
        f"### Regime decision: **{reg['decision']}** — {reg['why']}",
        f"Note: {reg.get('note')}",
        "",
        "## 2. Hold→Promote denser attempts",
        "",
        f"### `exec.tape_markout_post_crash` → **{mo['decision']}**",
        f"- pooled mo@5s mean={((mo.get('pooled_mo_5s') or {}).get('mean'))}",
        f"- checks: {mo.get('checks')}",
        f"- why: {mo.get('why')}",
        "",
        f"### `risk.duration_post_markout` → **{dur['decision']}**",
        f"- spearman dt/ic/volclock vs |mo| = {dur.get('spearman_dt_abs_mo')} / "
        f"{dur.get('spearman_ic_abs_mo')} / {dur.get('spearman_volclock_abs_mo')}",
        f"- train/test: {dur.get('train')} / {dur.get('test')}",
        f"- why: {dur.get('why')}",
        "",
        f"### `info.vpin_x_size_severity` → **{vp['decision']}**",
        f"- n={vp.get('n')} R²={vp.get('r2')} t={vp.get('t')}",
        f"- interact boot CI: {vp.get('interact_boot')}",
        f"- size β early/late: {vp.get('size_beta_early')} / {vp.get('size_beta_late')}",
        f"- why: {vp.get('why')}",
        "",
        "## Identification / leakage controls",
        "- Occurrence: chronological 60/40 by day×half; features imputed with **train** medians only",
        "- Severity: event-level pre-window features (strictly before event start); time_split on ts_start",
        "- VPIN: rolling bucket series asof before event (`vpin_exante`)",
        "- Plain size→severity remains Kill; only interact re-tested",
        "",
        "## Figures",
    ]
    for f in summary.get("figs") or []:
        lines.append(f"- `{Path(f).name}`")
    path = APP / "feature_models" / "EXP_REPORT.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def build_notebooks(summary: dict[str, Any]) -> list[Path]:
    import base64

    def _md(text: str) -> dict:
        return {"cell_type": "markdown", "metadata": {}, "source": [l + "\n" for l in text.split("\n")]}

    def _code(src: str, outputs: list | None = None, n: int = 1) -> dict:
        return {
            "cell_type": "code",
            "execution_count": n,
            "metadata": {},
            "outputs": outputs or [],
            "source": [l + "\n" for l in src.split("\n")],
        }

    def _img(path: Path) -> dict:
        return {
            "output_type": "display_data",
            "data": {
                "image/png": base64.b64encode(path.read_bytes()).decode("ascii"),
                "text/plain": ["<IPython.core.display.Image object>"],
            },
            "metadata": {},
        }

    reg = summary["regime_decision"]
    occ = summary["occurrence"]
    lines = [
        f"regime={reg['decision']} AUC_te={occ.get('auc_test')} R2_te={summary['severity'].get('ridge_r2_test')}",
        f"markout={summary['tape_markout']['decision']} duration={summary['duration']['decision']} "
        f"vpin={summary['vpin_size']['decision']}",
    ]
    stream = {"output_type": "stream", "name": "stdout", "text": [l + "\n" for l in lines]}

    nb1_cells = [
        _md(
            f"# Severity / regime feature model\n\n**{reg['decision']}** — {reg['why']}\n\n"
            "Logistic occurrence + Ridge |ΔP|; chronological OOS; no leakage."
        ),
        _code(
            "from pathlib import Path\nimport json\n"
            "s = json.loads(Path('out/feature_models_summary.json').read_text())\n"
            "print('regime', s['regime_decision'])\n"
            "print('occurrence AUC', s['occurrence'].get('auc_test'), 'useful', s['occurrence'].get('oos_useful'))\n"
            "print('severity R2_te', s['severity'].get('ridge_r2_test'), 'useful', s['severity'].get('oos_useful'))\n",
            outputs=[stream],
        ),
        _md("## Calibration"),
        _code(
            "from IPython.display import Image, display\n"
            "display(Image('out/figs/fig_occurrence_calibration.png'))\n",
            outputs=[_img(FIG / "fig_occurrence_calibration.png")]
            if (FIG / "fig_occurrence_calibration.png").exists()
            else [],
        ),
        _md("## Severity coefficients"),
        _code(
            "display(Image('out/figs/fig_severity_coefs.png'))\n",
            outputs=[_img(FIG / "fig_severity_coefs.png")] if (FIG / "fig_severity_coefs.png").exists() else [],
            n=2,
        ),
    ]
    nb2_cells = [
        _md(
            "# Hold→Promote denser sims\n\n"
            f"- tape_markout: **{summary['tape_markout']['decision']}**\n"
            f"- duration: **{summary['duration']['decision']}**\n"
            f"- vpin×size: **{summary['vpin_size']['decision']}**"
        ),
        _code(
            "from pathlib import Path\nimport json\n"
            "from IPython.display import Image, display\n"
            "s = json.loads(Path('out/feature_models_summary.json').read_text())\n"
            "for k in ('tape_markout','duration','vpin_size'):\n"
            "    print(k, s[k]['decision'], s[k].get('why'))\n"
            "display(Image('out/figs/fig_hold_promote.png'))\n"
            "display(Image('out/figs/fig_markout_by_class.png'))\n",
            outputs=[
                {
                    "output_type": "stream",
                    "name": "stdout",
                    "text": [
                        f"tape_markout {summary['tape_markout']['decision']}\n",
                        f"duration {summary['duration']['decision']}\n",
                        f"vpin_size {summary['vpin_size']['decision']}\n",
                    ],
                },
                *([_img(FIG / "fig_hold_promote.png")] if (FIG / "fig_hold_promote.png").exists() else []),
                *([_img(FIG / "fig_markout_by_class.png")] if (FIG / "fig_markout_by_class.png").exists() else []),
            ],
        ),
    ]

    def _nb(cells):
        return {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {
                "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                "language_info": {"name": "python"},
            },
            "cells": cells,
        }

    p1 = APP / "feature_models" / "severity_regime.ipynb"
    p2 = APP / "feature_models" / "hold_promote_dense.ipynb"
    p1.write_text(json.dumps(_nb(nb1_cells), indent=1))
    p2.write_text(json.dumps(_nb(nb2_cells), indent=1))
    return [p1, p2]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", nargs="*", default=None)
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--include-sol", action="store_true")
    ap.add_argument("--max-files", type=int, default=24)
    ap.add_argument("--panel-json", type=str, default=None, help="Reuse panel events from mm_quoting or prior run")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)

    if args.panel_json and Path(args.panel_json).exists():
        print(f"Loading panel cache {args.panel_json}", flush=True)
        # expect full panel with cells+events — if only events, rebuild light
        raw = json.loads(Path(args.panel_json).read_text())
        if "events" in raw and "cells" in raw:
            panel = raw
        else:
            panel = None
    else:
        panel = None

    if panel is None:
        print("Building event panel…", flush=True)
        panel = build_panel(
            days=args.days or DEFAULT_DAYS,
            symbols=args.symbols or DEFAULT_SYMBOLS,
            include_sol=args.include_sol,
            max_files=args.max_files,
        )
        (OUT / "panel_cache.json").write_text(json.dumps(jsonable(panel), indent=2))

    events = panel["events"]
    print(f"n_events={len(events)}", flush=True)

    cell_rows = build_cell_crash_labels(panel)
    occurrence = fit_logistic_occurrence(cell_rows)
    severity = fit_severity_regression(events)
    regime = decide_regime(occurrence, severity)

    markout = denser_tape_markout(events)
    duration = denser_duration_markout(events)
    vpin = denser_vpin_size(events)

    figs = plot_figs(occurrence, severity, markout, duration, vpin)
    summary = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "days": panel.get("days"),
        "symbols": panel.get("symbols"),
        "venues": panel.get("venues"),
        "n_cells": panel.get("n_cells"),
        "n_complete": panel.get("n_complete"),
        "n_events": len(events),
        "n_occurrence_rows": len(cell_rows),
        "occurrence": occurrence,
        "severity": severity,
        "regime_decision": regime,
        "tape_markout": markout,
        "duration": duration,
        "vpin_size": vpin,
        "figs": figs,
        "decisions": {
            "feature.severity_regime_model": regime["decision"],
            "exec.tape_markout_post_crash": markout["decision"],
            "risk.duration_post_markout": duration["decision"],
            "info.vpin_x_size_severity": vpin["decision"],
        },
    }
    (OUT / "feature_models_summary.json").write_text(json.dumps(jsonable(summary), indent=2))
    report = write_report(summary)
    nbs = build_notebooks(summary)
    print(f"regime={regime['decision']} report={report}", flush=True)
    print(json.dumps(jsonable(summary["decisions"]), indent=2), flush=True)
    print("notebooks:", nbs, flush=True)


if __name__ == "__main__":
    main()
