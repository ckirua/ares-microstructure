"""Occurrence / severity model upgrades — more features, calibration, Bayesian update.

Honesty: severity |ΔP| remains OOS-hard; occurrence Soft Promote only if AUC/Brier clear.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.linear_model import BayesianRidge, LogisticRegression, Ridge
from sklearn.metrics import brier_score_loss, r2_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

FEAT_BASE = [
    "vpin_proxy",
    "intensity_60s",
    "log_ic",
    "hour_sin",
    "hour_cos",
    "H_v",
    "nanex_bit",
]
# abs_z / z×intensity excluded — contemporaneous with |ΔP| (leak)
FEAT_INTERACT = FEAT_BASE + ["vpin_x_logn"]


def _hour_from_ts(ts_ns: int) -> float:
    # UTC hour from ns
    s = (int(ts_ns) // 1_000_000_000) % 86400
    return s / 3600.0


def events_to_design(evs: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    """Design for severity |ΔP| and occurrence (cell half) built from events.

    Occurrence: day×venue×symbol×half crash bit from event presence.
    Severity: |dp_pct| on gated events.
    """
    # severity design
    rows = []
    for e in evs:
        hour = _hour_from_ts(int(e.get("ts_end") or e.get("ts_start") or 0))
        vpin = float(e.get("vpin_exante") or e.get("intensity_60s") or 1.0)
        # proxy: normalize intensity as toxicity stand-in when vpin absent
        inten = float(e.get("intensity_60s") or 1.0)
        log_n = float(np.log(max(float(e.get("i_c") or 1.0), 1.0)))
        z = abs(float(e.get("z_peak") or 0.0))
        hv = float(e.get("H_v") if e.get("H_v") is not None else np.nan)
        nx = 1.0 if e.get("nanex_overlap") else 0.0
        feat = {
            "vpin_proxy": vpin,
            "intensity_60s": inten,
            "log_ic": log_n,
            "hour_sin": np.sin(2 * np.pi * hour / 24.0),
            "hour_cos": np.cos(2 * np.pi * hour / 24.0),
            "H_v": hv if np.isfinite(hv) else 0.5,
            "nanex_bit": nx,
            "vpin_x_logn": vpin * log_n,
            "y_dp": abs(float(e.get("dp_pct") or np.nan)),
            "day": e["day"],
            "ts": int(e.get("ts_start") or 0),
            "_abs_z_diag": z,  # not in design
        }
        rows.append(feat)
    rows = sorted(rows, key=lambda r: r["ts"])
    X = np.column_stack([np.asarray([r[c] for r in rows], dtype=np.float64) for c in FEAT_INTERACT])
    y = np.asarray([r["y_dp"] for r in rows], dtype=np.float64)
    days = np.asarray([r["day"] for r in rows], dtype=object)
    return X, y, days, FEAT_INTERACT


def build_occurrence_rows(evs: list[dict[str, Any]], rows_panel: list[dict]) -> list[dict[str, Any]]:
    """Day×venue×symbol×am/pm occurrence with cell-level features."""
    by_cell: dict[tuple, list] = {}
    for e in evs:
        by_cell.setdefault((e["venue"], e["symbol"], e["day"]), []).append(e)
    cell_meta = {(r["venue"], r["symbol"], r["day"]): r for r in rows_panel if "venue" in r}
    out = []
    for key, evlist in by_cell.items():
        meta = cell_meta.get(key, {})
        hv = meta.get("H_v")
        for half, (h0, h1, hour) in (("am", (0, 12, 6)), ("pm", (12, 24, 18))):
            half_ev = []
            for e in evlist:
                hr = _hour_from_ts(int(e.get("ts_end") or 0))
                if h0 <= hr < h1:
                    half_ev.append(e)
            # features from day aggregates — avoid leaking event |ΔP|
            inten = float(np.mean([e.get("intensity_60s") or 1 for e in evlist])) if evlist else 1.0
            z_med = float(np.median([abs(e.get("z_peak") or 0) for e in evlist])) if evlist else 0.0
            nx_rate = float(np.mean([1 if e.get("nanex_overlap") else 0 for e in evlist])) if evlist else 0.0
            out.append(
                {
                    "venue": key[0],
                    "symbol": key[1],
                    "day": key[2],
                    "half": half,
                    "y_crash": 1 if half_ev else 0,
                    "hour_utc": hour,
                    "intensity": inten,
                    "abs_z_day": z_med,
                    "nanex_rate": nx_rate,
                    "H_v": float(hv) if hv is not None and np.isfinite(float(hv)) else 0.5,
                    "log_n_events_day": float(np.log(max(len(evlist), 1))),
                    "n_trades_cell": float(meta.get("n_trades") or 0),
                }
            )
    # also add quiet cells (complete rows with 0 events)
    seen = {(r["venue"], r["symbol"], r["day"], r["half"]) for r in out}
    for r in rows_panel:
        if not r.get("complete"):
            continue
        key3 = (r["venue"], r["symbol"], r["day"])
        if key3 in by_cell:
            continue
        for half, hour in (("am", 6), ("pm", 18)):
            k4 = (*key3, half)
            if k4 in seen:
                continue
            out.append(
                {
                    "venue": r["venue"],
                    "symbol": r["symbol"],
                    "day": r["day"],
                    "half": half,
                    "y_crash": 0,
                    "hour_utc": hour,
                    "intensity": 0.0,
                    "abs_z_day": 0.0,
                    "nanex_rate": 0.0,
                    "H_v": float(r["H_v"]) if r.get("H_v") is not None else 0.5,
                    "log_n_events_day": 0.0,
                    "n_trades_cell": float(r.get("n_trades") or 0),
                }
            )
    return out


OCC_FEATS = [
    "H_v",
    "hour_utc",
    "log_n_trades",
    # deliberately exclude same-day crash counts / intensity / z — those leak occurrence
]


def fit_occurrence(occ_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if len(occ_rows) < 24:
        return {"n": len(occ_rows), "error": "too_few"}
    days = sorted({r["day"] for r in occ_rows})
    day_ord = {d: i for i, d in enumerate(days)}
    rows_s = sorted(occ_rows, key=lambda r: (day_ord[r["day"]], 0 if r["half"] == "am" else 1))
    for r in rows_s:
        r["log_n_trades"] = float(np.log(max(r.get("n_trades_cell") or 1.0, 1.0)))
    y = np.asarray([r["y_crash"] for r in rows_s], dtype=np.float64)
    X = np.column_stack([np.asarray([r[c] for r in rows_s], dtype=np.float64) for c in OCC_FEATS])
    n = len(rows_s)
    cut = int(0.6 * n)
    X_tr, X_te = X[:cut].copy(), X[cut:].copy()
    y_tr, y_te = y[:cut], y[cut:]
    med = np.nanmedian(X_tr, axis=0)
    med = np.where(np.isfinite(med), med, 0.0)
    for j in range(X_tr.shape[1]):
        X_tr[np.isnan(X_tr[:, j]), j] = med[j]
        X_te[np.isnan(X_te[:, j]), j] = med[j]
    if len(np.unique(y_tr)) < 2 or len(np.unique(y_te)) < 2:
        return {"n": n, "error": "single_class_split", "base_rate_test": float(y_te.mean())}

    base = Pipeline(
        [
            ("sc", StandardScaler()),
            ("clf", LogisticRegression(C=0.5, max_iter=2000, class_weight="balanced")),
        ]
    )
    base.fit(X_tr, y_tr)
    # calibrated
    try:
        cal = CalibratedClassifierCV(base, method="isotonic", cv=3)
        cal.fit(X_tr, y_tr)
        proba_te = cal.predict_proba(X_te)[:, 1]
        cal_name = "isotonic_cv3"
    except Exception:
        proba_te = base.predict_proba(X_te)[:, 1]
        cal_name = "none"
    proba_tr = base.predict_proba(X_tr)[:, 1]

    def _auc(yt, p):
        try:
            return float(roc_auc_score(yt, p))
        except ValueError:
            return float("nan")

    try:
        frac, mean_p = calibration_curve(y_te, proba_te, n_bins=5, strategy="quantile")
        cal_curve = {"frac_pos": frac.tolist(), "mean_pred": mean_p.tolist()}
    except Exception as exc:  # noqa: BLE001
        cal_curve = {"error": str(exc)}

    brier = float(brier_score_loss(y_te, proba_te))
    base_brier = float(np.mean((y_te - y_tr.mean()) ** 2))
    auc_te = _auc(y_te, proba_te)
    # Bayesian update: Beta prior from train base rate → test posterior mean vs model
    a0, b0 = 1.0 + y_tr.sum(), 1.0 + (len(y_tr) - y_tr.sum())
    post_means = []
    for p, yt in zip(proba_te, y_te):
        a = a0 + p
        b = b0 + (1 - p)
        post_means.append(a / (a + b))
    post_means = np.asarray(post_means)
    bayes_auc = _auc(y_te, post_means)
    bayes_brier = float(brier_score_loss(y_te, post_means))

    soft_promote = bool(np.isfinite(auc_te) and auc_te >= 0.60 and brier < base_brier)
    return {
        "n": n,
        "n_train": cut,
        "n_test": n - cut,
        "features": OCC_FEATS,
        "feature_note": "ex-ante cell state only (H^v, hour, log trades) — no same-day crash intensity/z",
        "base_rate_train": float(y_tr.mean()),
        "base_rate_test": float(y_te.mean()),
        "auc_train": _auc(y_tr, proba_tr),
        "auc_test": auc_te,
        "brier_test": brier,
        "base_rate_brier": base_brier,
        "calibration": cal_curve,
        "calibrator": cal_name,
        "bayes_beta_auc": bayes_auc,
        "bayes_beta_brier": bayes_brier,
        "soft_promote": soft_promote,
        "coef": {
            OCC_FEATS[i]: float(base.named_steps["clf"].coef_.ravel()[i])
            for i in range(len(OCC_FEATS))
        },
        "verdict": "Soft Promote" if soft_promote else "Hold",
    }


def fit_severity(evs: list[dict[str, Any]]) -> dict[str, Any]:
    X, y, days, cols = events_to_design(evs)
    m = np.isfinite(X).all(axis=1) & np.isfinite(y)
    X, y, days = X[m], y[m], days[m]
    n = X.shape[0]
    if n < 40:
        return {"n": n, "error": "too_few"}
    cut = int(0.6 * n)
    X_tr, X_te = X[:cut], X[cut:]
    y_tr, y_te = y[:cut], y[cut:]
    ridge = Pipeline([("sc", StandardScaler()), ("reg", Ridge(alpha=5.0))])
    ridge.fit(X_tr, y_tr)
    pred_te = ridge.predict(X_te)
    r2_te = float(r2_score(y_te, pred_te))
    # Bayesian ridge
    br = Pipeline([("sc", StandardScaler()), ("reg", BayesianRidge())])
    br.fit(X_tr, y_tr)
    pred_br = br.predict(X_te)
    r2_br = float(r2_score(y_te, pred_br))
    # early/late by day index
    uniq = sorted(set(days.tolist()))
    mid = len(uniq) // 2
    early_set, late_set = set(uniq[:mid]), set(uniq[mid:])
    e_m = np.array([d in early_set for d in days])
    l_m = np.array([d in late_set for d in days])
    # OOS interact coef stability via ridge on early vs late
    def _coef(mask):
        if mask.sum() < 20:
            return None
        pipe = Pipeline([("sc", StandardScaler()), ("reg", Ridge(alpha=5.0))])
        pipe.fit(X[mask], y[mask])
        return pipe.named_steps["reg"].coef_

    c_e, c_l = _coef(e_m), _coef(l_m)
    interact_idx = cols.index("vpin_x_logn")
    interact_stable = False
    if c_e is not None and c_l is not None:
        interact_stable = bool(np.sign(c_e[interact_idx]) == np.sign(c_l[interact_idx]))
    # Honesty bar: Soft Promote only if OOS R²≥0.05 WITHOUT contemporaneous z
    soft = bool(r2_te >= 0.05 and interact_stable)
    return {
        "n": n,
        "n_train": cut,
        "n_test": n - cut,
        "features": cols,
        "feature_note": "excluded contemporaneous abs_z (leak with |ΔP|)",
        "ridge_r2_test": r2_te,
        "bayes_ridge_r2_test": r2_br,
        "interact_vpin_x_logn_sign_stable": interact_stable,
        "verdict": "Soft Promote" if soft else "Hold",
        "note": "Severity OOS usually weak once z removed — do not Promote for live sizing",
    }


def run_models(evs: list[dict[str, Any]], rows_panel: list[dict]) -> dict[str, Any]:
    occ_rows = build_occurrence_rows(evs, rows_panel)
    return {
        "occurrence": fit_occurrence(occ_rows),
        "severity": fit_severity(evs),
        "n_occ_rows": len(occ_rows),
        "n_events": len(evs),
    }
