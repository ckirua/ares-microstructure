"""Classifiers: logistic + optional sklearn GBM for P(V). Chrono train/test."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

try:
    from .feature_store import FORBIDDEN_FEATURES, feature_matrix, impute_train_median
except ImportError:  # script / flat path
    from feature_store import FORBIDDEN_FEATURES, feature_matrix, impute_train_median


def _safe_auc(y: np.ndarray, p: np.ndarray) -> float:
    y = np.asarray(y, dtype=np.float64)
    p = np.asarray(p, dtype=np.float64)
    m = np.isfinite(y) & np.isfinite(p)
    if m.sum() < 5 or len(np.unique(y[m])) < 2:
        return float("nan")
    try:
        return float(roc_auc_score(y[m], p[m]))
    except ValueError:
        return float("nan")


def _brier(y: np.ndarray, p: np.ndarray) -> float:
    y = np.asarray(y, dtype=np.float64)
    p = np.asarray(p, dtype=np.float64)
    m = np.isfinite(y) & np.isfinite(p)
    if m.sum() == 0:
        return float("nan")
    return float(brier_score_loss(y[m], np.clip(p[m], 1e-6, 1 - 1e-6)))


def _base_brier(y: np.ndarray) -> float:
    y = np.asarray(y, dtype=np.float64)
    y = y[np.isfinite(y)]
    if y.size == 0:
        return float("nan")
    p = float(y.mean())
    return float(np.mean((y - p) ** 2))


def _calibration(y: np.ndarray, p: np.ndarray, *, n_bins: int = 5) -> dict[str, Any]:
    y = np.asarray(y, dtype=np.float64)
    p = np.asarray(p, dtype=np.float64)
    m = np.isfinite(y) & np.isfinite(p)
    if m.sum() < n_bins * 2 or len(np.unique(y[m])) < 2:
        return {"error": "underpowered", "n": int(m.sum())}
    try:
        frac_pos, mean_pred = calibration_curve(y[m], p[m], n_bins=n_bins, strategy="quantile")
        return {
            "frac_pos": [float(x) for x in frac_pos],
            "mean_pred": [float(x) for x in mean_pred],
            "n_bins": n_bins,
            "n": int(m.sum()),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


def fit_classifiers(
    events: list[dict[str, Any]],
    tr: np.ndarray,
    te: np.ndarray,
    *,
    fit_gbm: bool = True,
) -> dict[str, Any]:
    """Fit logistic (+ optional GBM) on chrono split; return metrics + OOS proba."""
    X, cols, row_ok = feature_matrix(events, include_recovery=True)
    for c in cols:
        assert c not in FORBIDDEN_FEATURES, c

    y = np.asarray([float(e["y_v"]) for e in events], dtype=np.float64)
    usable = row_ok & np.isfinite(y)
    tr_u = tr & usable
    te_u = te & usable
    if int(tr_u.sum()) < 25 or int(te_u.sum()) < 15:
        return {"error": "split_too_small", "n_train": int(tr_u.sum()), "n_test": int(te_u.sum())}
    if len(np.unique(y[tr_u])) < 2 or len(np.unique(y[te_u])) < 2:
        return {
            "error": "single_class_split",
            "base_rate_train": float(y[tr_u].mean()),
            "base_rate_test": float(y[te_u].mean()),
        }

    X_tr, X_te, med = impute_train_median(X[tr_u], X[te_u])
    y_tr, y_te = y[tr_u], y[te_u]

    # Full-length proba arrays (nan where unused)
    n = len(events)
    proba_logit = np.full(n, np.nan, dtype=np.float64)
    proba_gbm = np.full(n, np.nan, dtype=np.float64)

    logit = Pipeline(
        [
            ("sc", StandardScaler()),
            (
                "clf",
                LogisticRegression(
                    C=0.5,
                    max_iter=3000,
                    class_weight="balanced",
                    solver="lbfgs",
                ),
            ),
        ]
    )
    logit.fit(X_tr, y_tr)
    p_tr_l = logit.predict_proba(X_tr)[:, 1]
    p_te_l = logit.predict_proba(X_te)[:, 1]
    # also score all usable rows with train impute for train+test indexing
    X_all_tr_med = X.copy()
    for j in range(X.shape[1]):
        bad = ~np.isfinite(X_all_tr_med[:, j])
        X_all_tr_med[bad, j] = med[j]
    proba_logit[usable] = logit.predict_proba(X_all_tr_med[usable])[:, 1]

    coef = logit.named_steps["clf"].coef_.ravel()
    logit_pack = {
        "model": "logistic",
        "features": cols,
        "n_train": int(tr_u.sum()),
        "n_test": int(te_u.sum()),
        "base_rate_train": float(y_tr.mean()),
        "base_rate_test": float(y_te.mean()),
        "auc_train": _safe_auc(y_tr, p_tr_l),
        "auc_test": _safe_auc(y_te, p_te_l),
        "brier_train": _brier(y_tr, p_tr_l),
        "brier_test": _brier(y_te, p_te_l),
        "brier_base_test": _base_brier(y_te),
        "calibration_test": _calibration(y_te, p_te_l),
        "coef": {cols[i]: float(coef[i]) for i in range(len(cols))},
        "intercept": float(logit.named_steps["clf"].intercept_[0]),
        "beats_base_brier": bool(
            np.isfinite(_brier(y_te, p_te_l))
            and np.isfinite(_base_brier(y_te))
            and _brier(y_te, p_te_l) < _base_brier(y_te)
        ),
        "auc_ok": bool(np.isfinite(_safe_auc(y_te, p_te_l)) and _safe_auc(y_te, p_te_l) >= 0.55),
    }

    gbm_pack: dict[str, Any] | None = None
    if fit_gbm:
        gbm = GradientBoostingClassifier(
            n_estimators=80,
            max_depth=2,
            learning_rate=0.05,
            subsample=0.85,
            min_samples_leaf=8,
            random_state=7,
        )
        gbm.fit(X_tr, y_tr)
        p_tr_g = gbm.predict_proba(X_tr)[:, 1]
        p_te_g = gbm.predict_proba(X_te)[:, 1]
        proba_gbm[usable] = gbm.predict_proba(X_all_tr_med[usable])[:, 1]
        imp = gbm.feature_importances_
        gbm_pack = {
            "model": "sklearn_gbm",
            "features": cols,
            "n_train": int(tr_u.sum()),
            "n_test": int(te_u.sum()),
            "base_rate_train": float(y_tr.mean()),
            "base_rate_test": float(y_te.mean()),
            "auc_train": _safe_auc(y_tr, p_tr_g),
            "auc_test": _safe_auc(y_te, p_te_g),
            "brier_train": _brier(y_tr, p_tr_g),
            "brier_test": _brier(y_te, p_te_g),
            "brier_base_test": _base_brier(y_te),
            "calibration_test": _calibration(y_te, p_te_g),
            "feature_importance": {cols[i]: float(imp[i]) for i in range(len(cols))},
            "beats_base_brier": bool(
                np.isfinite(_brier(y_te, p_te_g))
                and np.isfinite(_base_brier(y_te))
                and _brier(y_te, p_te_g) < _base_brier(y_te)
            ),
            "auc_ok": bool(np.isfinite(_safe_auc(y_te, p_te_g)) and _safe_auc(y_te, p_te_g) >= 0.55),
            "beats_logistic_auc": bool(
                np.isfinite(_safe_auc(y_te, p_te_g))
                and np.isfinite(logit_pack["auc_test"])
                and _safe_auc(y_te, p_te_g) > float(logit_pack["auc_test"])
            ),
            "beats_logistic_brier": bool(
                np.isfinite(_brier(y_te, p_te_g))
                and np.isfinite(logit_pack["brier_test"])
                and _brier(y_te, p_te_g) < float(logit_pack["brier_test"])
            ),
        }

    # pick primary model for sizing: better OOS Brier among those with finite AUC
    primary = "logistic"
    if gbm_pack and gbm_pack.get("beats_logistic_brier") and gbm_pack.get("auc_ok"):
        primary = "gbm"
    elif gbm_pack and gbm_pack.get("beats_logistic_auc") and gbm_pack.get("beats_base_brier"):
        primary = "gbm"

    return {
        "features": cols,
        "impute_median": med.tolist(),
        "logistic": logit_pack,
        "gbm": gbm_pack,
        "primary_model": primary,
        "proba_logistic": proba_logit,
        "proba_gbm": proba_gbm,
        "tr_mask": tr,
        "te_mask": te,
        "usable_mask": usable,
        "y": y,
        "forbidden_ok": True,
        "note": "Classifier only — Promote gated on soft-size OOS PnL lift, not AUC alone",
    }
