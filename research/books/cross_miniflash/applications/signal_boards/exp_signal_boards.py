from __future__ import annotations
#!/usr/bin/env python3
"""Signal boards + info-theory + stats + Bayesian panels for cross_miniflash.

Desk-quality figures for Promote risk/features. Reuses panel_cache (mm_quoting)
and applications/out/event_panel. ClickHouse MCP banned. Strategy equity curves
live in sibling ``strategy_lab/`` — this package does not overwrite them.

Bayesian: conjugate Beta–Binomial (V-recovery) + Metropolis–Hastings logistic
(occurrence) with stated priors and posterior predictive checks. No PyMC/numpyro
required (not installed cleanly on this host).
"""


import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.feature_selection import mutual_info_classif, mutual_info_regression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    brier_score_loss,
    roc_auc_score,
    roc_curve,
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
    EARLY_DAYS,
    LATE_DAYS,
    boot_mean,
    jsonable,
)
from ares_micro.stats import bootstrap_ci, time_split_mask  # noqa: E402

# Import occurrence row builder from feature_models (no leakage schema)
sys.path.insert(0, str(APP / "feature_models"))
from exp_feature_models import (  # noqa: E402
    FEAT_COLS,
    build_cell_crash_labels,
    fit_logistic_occurrence,
)

OUT = APP / "out" / "signal_boards"
FIG = OUT / "figs"
PANEL_CACHE = APP / "mm_quoting" / "out" / "panel_cache.json"
PANEL_ROWS = APP / "out" / "event_panel" / "panel_rows.json"
FRAG_SUMMARY = BOOK / "out" / "frag_xvenue" / "frag_summary.json"

NS_PER_S = 1_000_000_000
DAY0_NS = int(datetime(2026, 9, 4, tzinfo=timezone.utc).timestamp() * NS_PER_S)

# Desk palette (not purple-default)
C = {
    "ink": "#1a1a1a",
    "mute": "#6b6b6b",
    "hl": "#c45c26",
    "db": "#2a6f7f",
    "kr": "#3d7a4a",
    "grid": "#e8e4dc",
    "accent": "#b33a3a",
    "ok": "#2f6b4f",
    "hold": "#a67c2d",
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _day_ord(day: str) -> float:
    try:
        return float(DEFAULT_DAYS.index(day))
    except ValueError:
        return 99.0


def flatten_panel_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Join panel_rows event arrays with cell-level H^v / FEI / thin_excess."""
    out: list[dict[str, Any]] = []
    for cell in rows:
        ev = cell.get("events") or {}
        n = len(ev.get("ts_start") or [])
        for i in range(n):
            lab = (ev.get("recovery_label") or [None] * n)[i]
            out.append(
                {
                    "venue": cell["venue"],
                    "symbol": cell["symbol"],
                    "day": cell["day"],
                    "cohort": "early" if cell["day"] in EARLY_DAYS else "late",
                    "ts_start": int(ev["ts_start"][i]),
                    "ts_end": int(ev["ts_end"][i]),
                    "dp_pct": float(ev["dp_pct"][i]),
                    "i_c": int(ev["i_c"][i]),
                    "dt_s": float(ev["dt_s"][i]),
                    "direction": int(ev["direction"][i]),
                    "z_peak": float(ev["z_peak"][i]) if ev["z_peak"][i] is not None else float("nan"),
                    "intensity_60s": float(ev["intensity_60s"][i]),
                    "tier": ev["tier"][i],
                    "recovery": float(ev["recovery"][i]) if ev["recovery"][i] is not None else float("nan"),
                    "label": lab,
                    "is_v": 1 if lab == "v_recovery" else 0,
                    "mo_1s": float(ev["mo_1s"][i]) if ev["mo_1s"][i] is not None else float("nan"),
                    "mo_5s": float(ev["mo_5s"][i]) if ev["mo_5s"][i] is not None else float("nan"),
                    "nanex_overlap": int(ev["nanex_overlap"][i]),
                    "H_v": float(cell.get("H_v") or float("nan")),
                    "FEI": float(cell.get("FEI") or float("nan")),
                    "thin_excess": float(cell.get("thin_excess") or float("nan")),
                    "thin_venue": cell.get("thin_venue"),
                    "vol_usd": float(cell.get("vol_usd") or float("nan")),
                    "crash_share_venue": float((cell.get("crash_shares") or {}).get(cell["venue"], float("nan")))
                    if isinstance(cell.get("crash_shares"), dict)
                    else float("nan"),
                }
            )
    return out


def merge_features(
    row_events: list[dict[str, Any]],
    cache_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Match by (venue, symbol, day, ts_start) and attach pre-window features."""
    idx: dict[tuple, dict[str, Any]] = {}
    for e in cache_events:
        key = (e["venue"], e["symbol"], e["day"], int(e["ts_start"]))
        idx[key] = e
    merged: list[dict[str, Any]] = []
    for e in row_events:
        key = (e["venue"], e["symbol"], e["day"], int(e["ts_start"]))
        c = idx.get(key, {})
        m = dict(e)
        for k in (
            "vpin_exante",
            "intensity",
            "rv_1m",
            "amihud",
            "log_notional_pre",
            "hour_utc",
            "day_vpin",
            "day_intensity",
            "log_notional_event",
            "vol_clock",
            "recovery_5s",
            "recovery_1s",
            "recovery_2s",
        ):
            if k in c and c[k] is not None:
                try:
                    m[k] = float(c[k])
                except (TypeError, ValueError):
                    m[k] = float("nan")
            else:
                m.setdefault(k, float("nan"))
        # VPIN × size interact (Promote med feature)
        vp = m.get("vpin_exante", float("nan"))
        ln = m.get("log_notional_pre", float("nan"))
        m["vpin_x_size"] = (
            float(vp * ln) if np.isfinite(vp) and np.isfinite(ln) else float("nan")
        )
        # t_rel days from slice start
        m["t_day"] = (int(m["ts_start"]) - DAY0_NS) / (NS_PER_S * 86400.0)
        merged.append(m)
    return merged


# ---------------------------------------------------------------------------
# Signal boards
# ---------------------------------------------------------------------------

def build_daily_series(events: list[dict[str, Any]], cells: list[dict[str, Any]]) -> dict[str, Any]:
    """Day×venue aggregates for time-series boards."""
    days = list(DEFAULT_DAYS)
    venues = ["hyperliquid", "deribit", "kraken"]
    series: dict[str, Any] = {"days": days, "venues": venues, "by_venue": {}, "pooled": {}}

    for v in venues:
        gated_n, intensity_mean, z_med, nanex_n, thin, hv, fei, vpin_x = (
            [],
            [],
            [],
            [],
            [],
            [],
            [],
            [],
        )
        for d in days:
            evs = [e for e in events if e["venue"] == v and e["day"] == d]
            gated_n.append(len(evs))
            intensity_mean.append(
                float(np.nanmean([e["intensity_60s"] for e in evs])) if evs else 0.0
            )
            zs = [e["z_peak"] for e in evs if np.isfinite(e.get("z_peak", np.nan))]
            z_med.append(float(np.median(zs)) if zs else float("nan"))
            nanex_n.append(sum(int(e.get("nanex_overlap", 0)) for e in evs))
            # thin/H^v/FEI are symbol-day shared — take mean across symbols present
            cells_d = [c for c in cells if c.get("venue") == v and c.get("day") == d and c.get("complete")]

            def _nanmean(vals: list) -> float:
                a = np.asarray(
                    [float(x) for x in vals if x is not None and np.isfinite(float(x))],
                    dtype=np.float64,
                )
                return float(a.mean()) if a.size else float("nan")

            if not cells_d:
                thin.append(_nanmean([e.get("thin_excess") for e in evs]))
                hv.append(_nanmean([e.get("H_v") for e in evs]))
                fei.append(_nanmean([e.get("FEI") for e in evs]))
            else:
                thin.append(_nanmean([c.get("thin_excess") for c in cells_d]))
                hv.append(_nanmean([c.get("H_v") for c in cells_d]))
                fei.append(_nanmean([c.get("FEI") for c in cells_d]))
            vx = [e.get("vpin_x_size") for e in evs]
            vpin_x.append(_nanmean(vx))
        series["by_venue"][v] = {
            "gated_n": gated_n,
            "intensity_mean": intensity_mean,
            "z_med": z_med,
            "nanex_n": nanex_n,
            "thin_excess": thin,
            "H_v": hv,
            "FEI": fei,
            "vpin_x_size": vpin_x,
        }

    # pooled day totals
    for key in ("gated_n", "nanex_n"):
        series["pooled"][key] = [
            int(sum(series["by_venue"][v][key][i] for v in venues)) for i in range(len(days))
        ]
    return series


def event_aligned_matrix(
    events: list[dict[str, Any]],
    feat: str,
    *,
    max_events: int = 80,
) -> tuple[np.ndarray, list[str]]:
    """Sort events chronologically; return (n_events,) values + labels for heatmap row."""
    evs = sorted(events, key=lambda e: int(e["ts_start"]))
    if len(evs) > max_events:
        # stratified subsample: keep extremes of |ΔP| + random mid
        abs_dp = np.asarray([abs(e["dp_pct"]) for e in evs])
        order = np.argsort(abs_dp)
        keep = set(order[: max_events // 4].tolist()) | set(order[-max_events // 4 :].tolist())
        mid = [i for i in range(len(evs)) if i not in keep]
        rng = np.random.default_rng(7)
        need = max_events - len(keep)
        if need > 0 and mid:
            keep |= set(rng.choice(mid, size=min(need, len(mid)), replace=False).tolist())
        evs = [evs[i] for i in sorted(keep)]
    vals = np.asarray([e.get(feat, np.nan) for e in evs], dtype=np.float64)
    labels = [f"{e['day'][-5:]} {e['venue'][:2]}/{e['symbol']}" for e in evs]
    return vals, labels


# ---------------------------------------------------------------------------
# Information theory
# ---------------------------------------------------------------------------

def _safe_entropy(p: np.ndarray) -> float:
    p = p[p > 0]
    if p.size == 0:
        return float("nan")
    return float(-np.sum(p * np.log2(p)))


def mutual_info_panel(events: list[dict[str, Any]], rows_occ: list[dict[str, Any]]) -> dict[str, Any]:
    """MI / lagged MI for pre-crash features vs outcomes. Honest about n."""
    out: dict[str, Any] = {
        "n_events": len(events),
        "n_occurrence_rows": len(rows_occ),
        "ofi_available": False,
        "ofi_note": "OFI not on panel_cache — skip; use VPIN/intensity/rv/H^v",
        "sample_honesty": (
            "n_events=275 gated; occurrence halves n=84. MI estimates noisy; "
            "lagged TE-style scan is descriptive only — not causal claim."
        ),
    }

    # Event-level: features → |ΔP|, V-class
    feat_names = ["vpin_exante", "intensity", "rv_1m", "intensity_60s", "H_v", "vpin_x_size", "z_peak"]
    X_list, names_ok = [], []
    for f in feat_names:
        col = np.asarray([e.get(f, np.nan) for e in events], dtype=np.float64)
        if np.isfinite(col).sum() >= 30:
            X_list.append(col)
            names_ok.append(f)
    if not X_list:
        out["error"] = "no_features"
        return out
    X = np.column_stack(X_list)
    # impute col median
    for j in range(X.shape[1]):
        med = np.nanmedian(X[:, j])
        X[np.isnan(X[:, j]), j] = med if np.isfinite(med) else 0.0

    abs_dp = np.asarray([abs(e["dp_pct"]) for e in events], dtype=np.float64)
    is_v = np.asarray([1 if e.get("label") == "v_recovery" else 0 for e in events], dtype=np.int64)
    # crash occurrence is tautological at event level — use high-severity bit
    high_sev = (abs_dp >= np.nanpercentile(abs_dp, 75)).astype(int)

    mi_abs = mutual_info_regression(X, abs_dp, random_state=41, n_neighbors=5)
    mi_v = mutual_info_classif(X, is_v, random_state=41, n_neighbors=5)
    mi_sev = mutual_info_classif(X, high_sev, random_state=41, n_neighbors=5)
    out["event_mi"] = {
        "features": names_ok,
        "mi_abs_dp": [float(x) for x in mi_abs],
        "mi_v_class": [float(x) for x in mi_v],
        "mi_high_severity": [float(x) for x in mi_sev],
    }

    # Occurrence-level MI (day halves)
    Xo_list, ono = [], []
    for f in FEAT_COLS:
        col = np.asarray([r.get(f, np.nan) for r in rows_occ], dtype=np.float64)
        if np.isfinite(col).sum() >= 20:
            med = np.nanmedian(col[np.isfinite(col)]) if np.isfinite(col).any() else 0.0
            col = col.copy()
            col[np.isnan(col)] = med
            Xo_list.append(col)
            ono.append(f)
    if Xo_list:
        Xo = np.column_stack(Xo_list)
        y = np.asarray([r["y_crash"] for r in rows_occ], dtype=np.int64)
        out["occurrence_mi"] = {
            "features": ono,
            "mi_crash": [float(x) for x in mutual_info_classif(Xo, y, random_state=41, n_neighbors=3)],
            "n": len(rows_occ),
        }

    # Venue crash-share entropy
    venues = ["hyperliquid", "deribit", "kraken"]
    counts = np.asarray([sum(1 for e in events if e["venue"] == v) for v in venues], dtype=np.float64)
    p = counts / max(counts.sum(), 1.0)
    out["venue_crash_entropy"] = {
        "venues": venues,
        "shares": [float(x) for x in p],
        "counts": [int(x) for x in counts],
        "H_bits": _safe_entropy(p),
        "H_max_bits": math.log2(len(venues)),
        "note": "Entropy of gated crash venue distribution (not volume share).",
    }

    # Lagged MI / TE-style scan: MI(X_{t-k}, Y_t) on chronological event series within venue
    # Using intensity_60s → next-event |ΔP| and is_v — small-n honest
    lag_scan: dict[str, Any] = {"lags_events": [1, 2, 3, 5], "by_target": {}}
    for target_name, target_fn in (
        ("abs_dp", lambda e: abs(e["dp_pct"])),
        ("is_v", lambda e: 1.0 if e.get("label") == "v_recovery" else 0.0),
    ):
        rows_lag = []
        for lag in lag_scan["lags_events"]:
            xs, ys = [], []
            for v in venues:
                for sym in ("ETH", "BTC"):
                    sub = sorted(
                        [e for e in events if e["venue"] == v and e["symbol"] == sym],
                        key=lambda e: int(e["ts_start"]),
                    )
                    for i in range(lag, len(sub)):
                        x = sub[i - lag].get("intensity_60s", np.nan)
                        y = target_fn(sub[i])
                        if np.isfinite(x) and np.isfinite(y):
                            xs.append(x)
                            ys.append(y)
            if len(xs) < 25:
                rows_lag.append({"lag": lag, "n": len(xs), "mi": float("nan"), "note": "n<25"})
                continue
            Xa = np.asarray(xs, dtype=np.float64).reshape(-1, 1)
            ya = np.asarray(ys, dtype=np.float64)
            if target_name == "is_v":
                mi = float(mutual_info_classif(Xa, ya.astype(int), random_state=41, n_neighbors=3)[0])
            else:
                mi = float(mutual_info_regression(Xa, ya, random_state=41, n_neighbors=3)[0])
            rows_lag.append({"lag": lag, "n": len(xs), "mi": mi})
        lag_scan["by_target"][target_name] = rows_lag
    lag_scan["te_style_note"] = (
        "Transfer-entropy style = lagged MI(intensity_60s_{t-k}, Y_t) within venue×symbol. "
        "Not full TE (no conditioning on Y history). Underpowered for k≥3."
    )
    out["lagged_mi_scan"] = lag_scan
    return out


# ---------------------------------------------------------------------------
# Statistical
# ---------------------------------------------------------------------------

def statistical_panel(
    events: list[dict[str, Any]],
    rows_occ: list[dict[str, Any]],
    occurrence_fit: dict[str, Any],
) -> dict[str, Any]:
    out: dict[str, Any] = {}

    # Bootstrap CIs on key Promote metrics
    abs_dp = np.asarray([abs(e["dp_pct"]) for e in events], dtype=np.float64)
    is_v = np.asarray([1.0 if e.get("label") == "v_recovery" else 0.0 for e in events])
    thin = np.asarray(
        [e["thin_excess"] for e in events if e["venue"] == "hyperliquid" and np.isfinite(e.get("thin_excess", np.nan))],
        dtype=np.float64,
    )
    nanex = np.asarray([e["dp_pct"] for e in events if e.get("nanex_overlap")], dtype=np.float64)
    ssm_only = np.asarray([e["dp_pct"] for e in events if not e.get("nanex_overlap")], dtype=np.float64)

    out["bootstrap"] = {
        "median_abs_dp": bootstrap_ci(abs_dp, np.median, n_boot=800, seed=41),
        "share_V": bootstrap_ci(is_v, np.mean, n_boot=800, seed=42),
        "hl_thin_excess_mean": bootstrap_ci(thin, np.mean, n_boot=800, seed=43) if thin.size else None,
        "nanex_nested_mean_dp": bootstrap_ci(np.abs(nanex), np.mean, n_boot=800, seed=44)
        if nanex.size
        else None,
        "ssm_only_mean_abs_dp": bootstrap_ci(np.abs(ssm_only), np.mean, n_boot=800, seed=45)
        if ssm_only.size
        else None,
    }
    if nanex.size and ssm_only.size:
        delta = float(np.mean(np.abs(nanex)) - np.mean(np.abs(ssm_only)))
        # bootstrap delta
        rng = np.random.default_rng(46)
        boots = []
        for _ in range(800):
            a = np.abs(nanex[rng.integers(0, nanex.size, nanex.size)])
            b = np.abs(ssm_only[rng.integers(0, ssm_only.size, ssm_only.size)])
            boots.append(float(a.mean() - b.mean()))
        lo, hi = np.quantile(boots, [0.025, 0.975])
        out["bootstrap"]["nanex_minus_ssm_abs_dp"] = {
            "point": delta,
            "lo": float(lo),
            "hi": float(hi),
            "n_nanex": int(nanex.size),
            "n_ssm_only": int(ssm_only.size),
        }

    # Time-split
    early = [e for e in events if e["cohort"] == "early"]
    late = [e for e in events if e["cohort"] == "late"]
    out["time_split"] = {
        "early_n": len(early),
        "late_n": len(late),
        "early_share_V": float(np.mean([e.get("label") == "v_recovery" for e in early])) if early else float("nan"),
        "late_share_V": float(np.mean([e.get("label") == "v_recovery" for e in late])) if late else float("nan"),
        "early_median_abs_dp": float(np.median([abs(e["dp_pct"]) for e in early])) if early else float("nan"),
        "late_median_abs_dp": float(np.median([abs(e["dp_pct"]) for e in late])) if late else float("nan"),
        "early_days": sorted(EARLY_DAYS),
        "late_days": sorted(LATE_DAYS),
    }

    # Occurrence model ROC + calibration (reuse fit + rebuild scores for curves)
    day_ord = {d: i for i, d in enumerate(DEFAULT_DAYS)}
    rows_s = sorted(rows_occ, key=lambda r: (day_ord.get(r["day"], 99), 0 if r["half"] == "am" else 1))
    y = np.asarray([r["y_crash"] for r in rows_s], dtype=np.float64)
    X = np.column_stack([np.asarray([r[c] for r in rows_s], dtype=np.float64) for c in FEAT_COLS])
    n = len(rows_s)
    cut = int(0.6 * n)
    X_tr, X_te = X[:cut], X[cut:]
    y_tr, y_te = y[:cut], y[cut:]
    med = np.nanmedian(X_tr, axis=0)
    med = np.where(np.isfinite(med), med, 0.0)
    X_tr, X_te = X_tr.copy(), X_te.copy()
    for j in range(X.shape[1]):
        X_tr[np.isnan(X_tr[:, j]), j] = med[j]
        X_te[np.isnan(X_te[:, j]), j] = med[j]
    pipe = Pipeline(
        [
            ("sc", StandardScaler()),
            (
                "clf",
                LogisticRegression(C=0.5, max_iter=2000, class_weight="balanced", solver="lbfgs"),
            ),
        ]
    )
    roc_pack: dict[str, Any] = {"n_train": int(cut), "n_test": int(n - cut)}
    if len(np.unique(y_tr)) > 1 and len(np.unique(y_te)) > 1:
        pipe.fit(X_tr, y_tr)
        proba_te = pipe.predict_proba(X_te)[:, 1]
        fpr, tpr, thr = roc_curve(y_te, proba_te)
        roc_pack.update(
            {
                "auc_test": float(roc_auc_score(y_te, proba_te)),
                "brier_test": float(brier_score_loss(y_te, proba_te)),
                "base_rate_test": float(y_te.mean()),
                "fpr": fpr.tolist(),
                "tpr": tpr.tolist(),
                "thresholds": thr.tolist(),
            }
        )
        try:
            frac_pos, mean_pred = calibration_curve(y_te, proba_te, n_bins=5, strategy="quantile")
            roc_pack["calibration"] = {
                "frac_pos": frac_pos.tolist(),
                "mean_pred": mean_pred.tolist(),
            }
        except Exception as exc:  # noqa: BLE001
            roc_pack["calibration"] = {"error": f"{type(exc).__name__}: {exc}"}
        roc_pack["coef"] = {
            FEAT_COLS[i]: float(pipe.named_steps["clf"].coef_.ravel()[i]) for i in range(len(FEAT_COLS))
        }
    else:
        roc_pack["error"] = "single_class_split"
    roc_pack["from_feature_models"] = {
        "auc_test": occurrence_fit.get("auc_test"),
        "brier_test": occurrence_fit.get("brier_test"),
    }
    out["occurrence_roc"] = roc_pack
    return out


# ---------------------------------------------------------------------------
# Bayesian (conjugate + MH logistic)
# ---------------------------------------------------------------------------

def beta_binomial_v_recovery(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Beta(α0,β0) prior on V-recovery rate; posterior Beta(α0+s, β0+n-s).

    Prior: Beta(1, 1) = Uniform — weakly informative on [0,1].
    PPC: draw θ ~ posterior, then ỹ ~ Binomial(n, θ); compare to observed share.
    """
    y = np.asarray([1 if e.get("label") == "v_recovery" else 0 for e in events], dtype=np.int64)
    n = int(y.size)
    s = int(y.sum())
    a0, b0 = 1.0, 1.0
    a_post, b_post = a0 + s, b0 + (n - s)
    # posterior mean / quantiles via Beta CDF inverse (numpy)
    rng = np.random.default_rng(51)
    post_draws = rng.beta(a_post, b_post, size=4000)
    # PPC
    y_rep = rng.binomial(n, post_draws)
    share_rep = y_rep / max(n, 1)
    obs_share = s / max(n, 1)
    # Bayesian p-value: P(T(y_rep) >= T(y_obs)) for T=share
    ppp = float(np.mean(share_rep >= obs_share - 1e-12))
    # early/late separate posteriors
    by_cohort = {}
    for name, mask in (
        ("early", np.asarray([e["cohort"] == "early" for e in events])),
        ("late", np.asarray([e["cohort"] == "late" for e in events])),
    ):
        yy = y[mask]
        nn, ss = int(yy.size), int(yy.sum())
        aa, bb = a0 + ss, b0 + (nn - ss)
        dd = rng.beta(aa, bb, size=4000)
        by_cohort[name] = {
            "n": nn,
            "successes": ss,
            "posterior_mean": float(aa / (aa + bb)),
            "ci95": [float(np.quantile(dd, 0.025)), float(np.quantile(dd, 0.975))],
            "alpha": aa,
            "beta": bb,
        }
    return {
        "model": "Beta-Binomial",
        "prior": {"family": "Beta", "alpha": a0, "beta": b0, "statement": "Uniform on (0,1)"},
        "likelihood": "y_i ~ Bern(θ), θ ~ Beta(α0,β0); n independent gated events",
        "n": n,
        "successes": s,
        "obs_share": obs_share,
        "posterior": {
            "alpha": a_post,
            "beta": b_post,
            "mean": float(a_post / (a_post + b_post)),
            "ci95": [float(np.quantile(post_draws, 0.025)), float(np.quantile(post_draws, 0.975))],
            "draws_path": None,  # stored separately if needed
        },
        "ppc": {
            "stat": "share_V",
            "obs": obs_share,
            "rep_mean": float(share_rep.mean()),
            "rep_ci95": [float(np.quantile(share_rep, 0.025)), float(np.quantile(share_rep, 0.975))],
            "bayesian_pvalue": ppp,
            "note": "ppp near 0.5 = adequate; extreme → model misspecification",
        },
        "by_cohort": by_cohort,
        "post_draws": post_draws.tolist()[:500],  # thin for JSON
        "share_rep": share_rep.tolist()[:500],
    }


def bayesian_logistic_occurrence(rows_occ: list[dict[str, Any]]) -> dict[str, Any]:
    """Bayesian logistic via random-walk Metropolis–Hastings.

    Prior: β_j ~ N(0, 2²) independent (weakly informative on standardized X);
    intercept ~ N(0, 2²). PPC on test-set predicted rates.
    """
    day_ord = {d: i for i, d in enumerate(DEFAULT_DAYS)}
    rows_s = sorted(rows_occ, key=lambda r: (day_ord.get(r["day"], 99), 0 if r["half"] == "am" else 1))
    y = np.asarray([r["y_crash"] for r in rows_s], dtype=np.float64)
    feat = ["vpin_exante", "intensity", "log_notional_pre", "hour_utc", "H_v"]
    X_raw = np.column_stack([np.asarray([r[c] for r in rows_s], dtype=np.float64) for c in feat])
    for j in range(X_raw.shape[1]):
        med = np.nanmedian(X_raw[:, j])
        X_raw[np.isnan(X_raw[:, j]), j] = med if np.isfinite(med) else 0.0
    # standardize using full sample (documented; small-n)
    mu = X_raw.mean(axis=0)
    sd = X_raw.std(axis=0)
    sd = np.where(sd > 1e-8, sd, 1.0)
    Xz = (X_raw - mu) / sd
    X = np.column_stack([np.ones(len(y)), Xz])
    p = X.shape[1]
    prior_sd = 2.0

    def log_post(beta: np.ndarray) -> float:
        eta = X @ beta
        # stable bernoulli loglik
        ll = np.sum(y * eta - np.logaddexp(0.0, eta))
        lp = -0.5 * np.sum((beta / prior_sd) ** 2)
        return float(ll + lp)

    rng = np.random.default_rng(61)
    # init at MLE-ish
    pipe = Pipeline(
        [
            ("sc", StandardScaler()),
            ("clf", LogisticRegression(C=1.0, max_iter=2000, solver="lbfgs")),
        ]
    )
    if len(np.unique(y)) < 2:
        return {"error": "single_class", "n": int(y.size)}
    pipe.fit(X_raw, y)
    beta = np.zeros(p)
    beta[0] = float(pipe.named_steps["clf"].intercept_[0])
    # map sklearn coefs (on StandardScaler space ≈ our Xz) 
    beta[1:] = pipe.named_steps["clf"].coef_.ravel()[: p - 1]

    n_iter, burn, thin = 8000, 2000, 5
    prop_sd = 0.08
    chain = []
    cur = beta.copy()
    cur_lp = log_post(cur)
    accept = 0
    for t in range(n_iter):
        prop = cur + rng.normal(0, prop_sd, size=p)
        lp = log_post(prop)
        if math.log(rng.random()) < lp - cur_lp:
            cur, cur_lp = prop, lp
            accept += 1
        if t >= burn and (t - burn) % thin == 0:
            chain.append(cur.copy())
    chain_a = np.asarray(chain)
    accept_rate = accept / n_iter

    # posterior summaries
    names = ["intercept", *feat]
    coef_sum = {}
    for i, name in enumerate(names):
        d = chain_a[:, i]
        coef_sum[name] = {
            "mean": float(d.mean()),
            "ci95": [float(np.quantile(d, 0.025)), float(np.quantile(d, 0.975))],
            "p_gt_0": float(np.mean(d > 0)),
        }

    # PPC: for each posterior draw, simulate ỹ; compare mean rate
    n_ppc = min(500, chain_a.shape[0])
    idx = rng.choice(chain_a.shape[0], size=n_ppc, replace=False)
    obs_rate = float(y.mean())
    rates = []
    for i in idx:
        eta = X @ chain_a[i]
        pr = 1.0 / (1.0 + np.exp(-eta))
        yrep = rng.binomial(1, pr)
        rates.append(float(yrep.mean()))
    rates_a = np.asarray(rates)
    ppp = float(np.mean(rates_a >= obs_rate - 1e-12))

    # chronological predictive AUC using posterior mean coef
    beta_mean = chain_a.mean(axis=0)
    cut = int(0.6 * len(y))
    eta_te = X[cut:] @ beta_mean
    pr_te = 1.0 / (1.0 + np.exp(-eta_te))
    y_te = y[cut:]
    auc_te = float("nan")
    if len(np.unique(y_te)) > 1:
        try:
            auc_te = float(roc_auc_score(y_te, pr_te))
        except ValueError:
            auc_te = float("nan")

    return {
        "model": "Bayesian logistic (RW-MH)",
        "prior": {
            "beta_j": f"N(0, {prior_sd}^2) independent",
            "statement": "Weakly informative on standardized predictors; intercept same.",
        },
        "features": feat,
        "n": int(y.size),
        "n_iter": n_iter,
        "burn": burn,
        "thin": thin,
        "accept_rate": accept_rate,
        "n_posterior_samples": int(chain_a.shape[0]),
        "coef": coef_sum,
        "ppc": {
            "stat": "mean_crash_rate",
            "obs": obs_rate,
            "rep_mean": float(rates_a.mean()),
            "rep_ci95": [float(np.quantile(rates_a, 0.025)), float(np.quantile(rates_a, 0.975))],
            "bayesian_pvalue": ppp,
        },
        "posterior_mean_auc_holdout": auc_te,
        "holdout_n": int(len(y) - cut),
        "chain_means": chain_a.mean(axis=0).tolist(),
        "chain_for_plot": {
            "intensity": chain_a[:, names.index("intensity")].tolist()[::2],
            "H_v": chain_a[:, names.index("H_v")].tolist()[::2],
            "vpin_exante": chain_a[:, names.index("vpin_exante")].tolist()[::2],
        },
        "ppc_rates": rates_a.tolist(),
    }


# ---------------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------------

def _setup_mpl():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "axes.facecolor": "#f7f5f0",
            "figure.facecolor": "white",
            "axes.edgecolor": C["ink"],
            "axes.grid": True,
            "grid.color": C["grid"],
            "grid.linewidth": 0.6,
            "axes.titleweight": "bold",
            "axes.titlesize": 11,
            "axes.labelsize": 9,
        }
    )
    return plt


def plot_all(
    series: dict[str, Any],
    events: list[dict[str, Any]],
    info: dict[str, Any],
    stats: dict[str, Any],
    bayes_v: dict[str, Any],
    bayes_occ: dict[str, Any],
) -> list[str]:
    plt = _setup_mpl()
    FIG.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    days = series["days"]
    x = np.arange(len(days))
    venue_colors = {"hyperliquid": C["hl"], "deribit": C["db"], "kraken": C["kr"]}

    # 1. Gated intensity time series
    fig, ax = plt.subplots(figsize=(9, 3.6))
    for v, col in venue_colors.items():
        ax.plot(x, series["by_venue"][v]["gated_n"], "o-", color=col, label=v, lw=1.6, ms=5)
    ax.set_xticks(x)
    ax.set_xticklabels([d[-5:] for d in days], rotation=0)
    ax.set_ylabel("gated SSM count")
    ax.set_title("Gated SSM intensity (10bps / i_c≥5) by venue×day")
    ax.legend(frameon=False, fontsize=8)
    p = FIG / "fig_gated_intensity_ts.png"
    fig.tight_layout()
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(str(p))

    # 2. z* path (median z_peak)
    fig, ax = plt.subplots(figsize=(9, 3.6))
    for v, col in venue_colors.items():
        ax.plot(x, series["by_venue"][v]["z_med"], "s-", color=col, label=v, lw=1.6, ms=5)
    ax.axhline(12.5, color=C["mute"], ls="--", lw=0.8, label="p25≈12.5")
    ax.axhline(20.4, color=C["mute"], ls=":", lw=0.8, label="p75≈20.4")
    ax.set_xticks(x)
    ax.set_xticklabels([d[-5:] for d in days])
    ax.set_ylabel("median z*")
    ax.set_title("z*-path (within-gated median peak |innov|/√S)")
    ax.legend(frameon=False, fontsize=8, ncol=2)
    p = FIG / "fig_zstar_path_ts.png"
    fig.tight_layout()
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(str(p))

    # 3. Nanex ∩ SSM counts
    fig, ax = plt.subplots(figsize=(9, 3.4))
    bottom = np.zeros(len(days))
    for v, col in venue_colors.items():
        vals = np.asarray(series["by_venue"][v]["nanex_n"], dtype=float)
        ax.bar(x, vals, bottom=bottom, color=col, label=v, width=0.7)
        bottom += vals
    ax.set_xticks(x)
    ax.set_xticklabels([d[-5:] for d in days])
    ax.set_ylabel("Nanex∩SSM count")
    ax.set_title("Nanex∩SSM nested burst events")
    ax.legend(frameon=False, fontsize=8)
    p = FIG / "fig_nanex_ssm_ts.png"
    fig.tight_layout()
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(str(p))

    # 4. VPIN × size
    fig, ax = plt.subplots(figsize=(9, 3.4))
    for v, col in venue_colors.items():
        ax.plot(x, series["by_venue"][v]["vpin_x_size"], "o-", color=col, label=v, lw=1.5, ms=5)
    ax.set_xticks(x)
    ax.set_xticklabels([d[-5:] for d in days])
    ax.set_ylabel("mean VPIN×logN")
    ax.set_title("VPIN×size interact (Promote med feature)")
    ax.legend(frameon=False, fontsize=8)
    p = FIG / "fig_vpin_x_size_ts.png"
    fig.tight_layout()
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(str(p))

    # 5. H^v / FEI
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.4), sharex=True)
    for v, col in venue_colors.items():
        axes[0].plot(x, series["by_venue"][v]["H_v"], "o-", color=col, label=v, lw=1.4, ms=4)
        axes[1].plot(x, series["by_venue"][v]["FEI"], "o-", color=col, label=v, lw=1.4, ms=4)
    axes[0].set_title("H^v (volume Herfindahl)")
    axes[1].set_title("FEI (volume)")
    for ax in axes:
        ax.set_xticks(x)
        ax.set_xticklabels([d[-5:] for d in days], fontsize=8)
    axes[0].legend(frameon=False, fontsize=7)
    fig.suptitle("Capacity monitors — H^v / FEI", fontsize=11, fontweight="bold", y=1.02)
    p = FIG / "fig_hv_fei_ts.png"
    fig.tight_layout()
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p))

    # 6. Thin excess (HL)
    fig, ax = plt.subplots(figsize=(9, 3.4))
    ax.plot(x, series["by_venue"]["hyperliquid"]["thin_excess"], "o-", color=C["hl"], lw=1.8, ms=6)
    ax.fill_between(x, series["by_venue"]["hyperliquid"]["thin_excess"], alpha=0.15, color=C["hl"])
    ax.set_xticks(x)
    ax.set_xticklabels([d[-5:] for d in days])
    ax.set_ylabel("thin excess (crash−vol share)")
    ax.set_title("HL thin-venue crash excess")
    p = FIG / "fig_thin_excess_ts.png"
    fig.tight_layout()
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(str(p))

    # 7. Event-aligned heatmaps (intensity, z*, vpin_x, thin)
    feats_hm = [
        ("intensity_60s", "Rolling intensity I(60s)"),
        ("z_peak", "z* peak"),
        ("vpin_x_size", "VPIN×logN"),
        ("thin_excess", "Thin excess"),
    ]
    fig, axes = plt.subplots(len(feats_hm), 1, figsize=(10, 7.5), sharex=False)
    for ax, (feat, title) in zip(axes, feats_hm):
        vals, labels = event_aligned_matrix(events, feat, max_events=60)
        # normalize row for display
        v = vals.copy()
        finite = np.isfinite(v)
        if finite.any():
            lo, hi = np.nanpercentile(v[finite], [5, 95])
            if hi <= lo:
                hi = lo + 1e-6
            vn = np.clip((v - lo) / (hi - lo), 0, 1)
            vn[~finite] = np.nan
        else:
            vn = v
        im = ax.imshow(vn.reshape(1, -1), aspect="auto", cmap="YlOrBr", vmin=0, vmax=1)
        ax.set_yticks([0])
        ax.set_yticklabels([title], fontsize=8)
        ax.set_xticks([])
        ax.set_title(title, fontsize=9, loc="left")
    axes[-1].set_xlabel("events (chronological subsample, n≤60)")
    fig.suptitle("Event-aligned feature heatmaps", fontsize=11, fontweight="bold")
    p = FIG / "fig_event_heatmaps.png"
    fig.tight_layout()
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(str(p))

    # 8. Multi-feature board strip (scatter |ΔP| vs features colored by venue)
    fig, axes = plt.subplots(2, 3, figsize=(10, 6))
    pairs = [
        ("intensity_60s", "I(60s)"),
        ("z_peak", "z*"),
        ("vpin_exante", "VPIN"),
        ("vpin_x_size", "VPIN×logN"),
        ("H_v", "H^v"),
        ("thin_excess", "thin excess"),
    ]
    for ax, (feat, lab) in zip(axes.ravel(), pairs):
        for v, col in venue_colors.items():
            sub = [e for e in events if e["venue"] == v]
            ax.scatter(
                [e.get(feat, np.nan) for e in sub],
                [abs(e["dp_pct"]) for e in sub],
                s=12,
                alpha=0.55,
                c=col,
                label=v if ax is axes[0, 0] else None,
            )
        ax.set_xlabel(lab, fontsize=8)
        ax.set_ylabel("|ΔP| %", fontsize=8)
    axes[0, 0].legend(frameon=False, fontsize=7)
    fig.suptitle("Promote features vs severity", fontsize=11, fontweight="bold")
    p = FIG / "fig_feature_vs_severity.png"
    fig.tight_layout()
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(str(p))

    # --- Info theory figs ---
    emi = info.get("event_mi") or {}
    if emi.get("features"):
        fig, ax = plt.subplots(figsize=(7.5, 4))
        feats = emi["features"]
        ypos = np.arange(len(feats))
        w = 0.25
        ax.barh(ypos - w, emi["mi_abs_dp"], height=w, color=C["accent"], label="MI→|ΔP|")
        ax.barh(ypos, emi["mi_v_class"], height=w, color=C["db"], label="MI→V-class")
        ax.barh(ypos + w, emi["mi_high_severity"], height=w, color=C["ok"], label="MI→high-sev")
        ax.set_yticks(ypos)
        ax.set_yticklabels(feats)
        ax.set_xlabel("mutual information (nats≈sklearn default)")
        ax.set_title(f"Event-level MI (n={info['n_events']})")
        ax.legend(frameon=False, fontsize=8)
        p = FIG / "fig_mi_event.png"
        fig.tight_layout()
        fig.savefig(p, dpi=150)
        plt.close(fig)
        paths.append(str(p))

    omi = info.get("occurrence_mi") or {}
    if omi.get("features"):
        fig, ax = plt.subplots(figsize=(7, 3.6))
        ax.barh(omi["features"], omi["mi_crash"], color=C["hl"])
        ax.set_xlabel("MI → crash occurrence")
        ax.set_title(f"Day-half occurrence MI (n={omi['n']}; day-level feats)")
        p = FIG / "fig_mi_occurrence.png"
        fig.tight_layout()
        fig.savefig(p, dpi=150)
        plt.close(fig)
        paths.append(str(p))

    # venue entropy
    ve = info.get("venue_crash_entropy") or {}
    if ve.get("shares"):
        fig, ax = plt.subplots(figsize=(5.5, 4))
        ax.bar(ve["venues"], ve["shares"], color=[venue_colors[v] for v in ve["venues"]])
        ax.set_ylabel("crash share")
        ax.set_title(f"Venue crash shares — H={ve['H_bits']:.2f} bits (max {ve['H_max_bits']:.2f})")
        p = FIG / "fig_venue_entropy.png"
        fig.tight_layout()
        fig.savefig(p, dpi=150)
        plt.close(fig)
        paths.append(str(p))

    # lagged MI scan
    lag = info.get("lagged_mi_scan") or {}
    if lag.get("by_target"):
        fig, ax = plt.subplots(figsize=(6.5, 3.8))
        for tname, style in (("abs_dp", "o-"), ("is_v", "s--")):
            rows = lag["by_target"][tname]
            ax.plot(
                [r["lag"] for r in rows],
                [r.get("mi", np.nan) for r in rows],
                style,
                label=tname,
                lw=1.6,
            )
        ax.set_xlabel("lag (events within venue×symbol)")
        ax.set_ylabel("lagged MI")
        ax.set_title("TE-style lag scan (intensity→Y); descriptive only")
        ax.legend(frameon=False)
        p = FIG / "fig_lagged_mi_scan.png"
        fig.tight_layout()
        fig.savefig(p, dpi=150)
        plt.close(fig)
        paths.append(str(p))

    # --- Statistical figs ---
    roc = stats.get("occurrence_roc") or {}
    if "fpr" in roc:
        fig, ax = plt.subplots(figsize=(5, 4.5))
        ax.plot(roc["fpr"], roc["tpr"], color=C["accent"], lw=2, label=f"AUC={roc['auc_test']:.3f}")
        ax.plot([0, 1], [0, 1], "k--", lw=0.8)
        ax.set_xlabel("FPR")
        ax.set_ylabel("TPR")
        ax.set_title("Occurrence model ROC (time-split holdout)")
        ax.legend(frameon=False)
        p = FIG / "fig_occurrence_roc.png"
        fig.tight_layout()
        fig.savefig(p, dpi=150)
        plt.close(fig)
        paths.append(str(p))

    cal = roc.get("calibration") or {}
    if "mean_pred" in cal:
        fig, ax = plt.subplots(figsize=(5, 4.5))
        ax.plot(cal["mean_pred"], cal["frac_pos"], "o-", color=C["db"], label="model")
        ax.plot([0, 1], [0, 1], "k--", lw=0.8, label="ideal")
        ax.set_xlabel("mean predicted P")
        ax.set_ylabel("observed frac")
        ax.set_title(f"Calibration (Brier={roc.get('brier_test'):.3f})")
        ax.legend(frameon=False)
        p = FIG / "fig_occurrence_calibration.png"
        fig.tight_layout()
        fig.savefig(p, dpi=150)
        plt.close(fig)
        paths.append(str(p))

    # bootstrap forest
    boot = stats.get("bootstrap") or {}
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    items = []
    for name, key in (
        ("median |ΔP|", "median_abs_dp"),
        ("share V", "share_V"),
        ("HL thin excess", "hl_thin_excess_mean"),
        ("Nanex−SSM Δ|ΔP|", "nanex_minus_ssm_abs_dp"),
    ):
        b = boot.get(key)
        if b and np.isfinite(b.get("point", np.nan)):
            items.append((name, b["point"], b["lo"], b["hi"]))
    if items:
        ypos = np.arange(len(items))
        ax.errorbar(
            [it[1] for it in items],
            ypos,
            xerr=[[it[1] - it[2] for it in items], [it[3] - it[1] for it in items]],
            fmt="o",
            color=C["ink"],
            ecolor=C["accent"],
            capsize=3,
        )
        ax.set_yticks(ypos)
        ax.set_yticklabels([it[0] for it in items])
        ax.axvline(0, color=C["mute"], lw=0.7)
        ax.set_title("Bootstrap CI95 (n_boot=800)")
        p = FIG / "fig_bootstrap_cis.png"
        fig.tight_layout()
        fig.savefig(p, dpi=150)
        plt.close(fig)
        paths.append(str(p))

    # time split bars
    ts = stats.get("time_split") or {}
    fig, axes = plt.subplots(1, 2, figsize=(7.5, 3.4))
    axes[0].bar(["early", "late"], [ts.get("early_share_V", np.nan), ts.get("late_share_V", np.nan)], color=[C["ok"], C["hold"]])
    axes[0].set_title("share V")
    axes[0].set_ylim(0, 1)
    axes[1].bar(
        ["early", "late"],
        [ts.get("early_median_abs_dp", np.nan), ts.get("late_median_abs_dp", np.nan)],
        color=[C["ok"], C["hold"]],
    )
    axes[1].set_title("median |ΔP| %")
    fig.suptitle("Time-split stability", fontsize=11, fontweight="bold")
    p = FIG / "fig_time_split.png"
    fig.tight_layout()
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(str(p))

    # --- Bayesian figs ---
    if "posterior" in bayes_v:
        fig, axes = plt.subplots(1, 2, figsize=(9, 3.6))
        draws = np.asarray(bayes_v["post_draws"], dtype=float)
        axes[0].hist(draws, bins=40, color=C["db"], alpha=0.85, density=True)
        axes[0].axvline(bayes_v["obs_share"], color=C["accent"], lw=2, label=f"obs={bayes_v['obs_share']:.3f}")
        ci = bayes_v["posterior"]["ci95"]
        axes[0].axvline(ci[0], color=C["mute"], ls="--", lw=1)
        axes[0].axvline(ci[1], color=C["mute"], ls="--", lw=1)
        axes[0].set_title(f"Posterior θ_V — Beta({bayes_v['posterior']['alpha']:.0f},{bayes_v['posterior']['beta']:.0f})")
        axes[0].set_xlabel("θ")
        axes[0].legend(frameon=False, fontsize=8)
        rep = np.asarray(bayes_v["share_rep"], dtype=float)
        axes[1].hist(rep, bins=30, color=C["ok"], alpha=0.85, density=True)
        axes[1].axvline(bayes_v["obs_share"], color=C["accent"], lw=2)
        axes[1].set_title(f"PPC share_V (ppp={bayes_v['ppc']['bayesian_pvalue']:.2f})")
        axes[1].set_xlabel("ỹ/n")
        fig.suptitle("Bayesian Beta–Binomial V-recovery", fontsize=11, fontweight="bold")
        p = FIG / "fig_bayes_v_recovery.png"
        fig.tight_layout()
        fig.savefig(p, dpi=150)
        plt.close(fig)
        paths.append(str(p))

    if "coef" in bayes_occ:
        fig, ax = plt.subplots(figsize=(7, 3.8))
        names = list(bayes_occ["coef"].keys())
        means = [bayes_occ["coef"][n]["mean"] for n in names]
        los = [bayes_occ["coef"][n]["ci95"][0] for n in names]
        his = [bayes_occ["coef"][n]["ci95"][1] for n in names]
        ypos = np.arange(len(names))
        ax.errorbar(
            means,
            ypos,
            xerr=[[m - lo for m, lo in zip(means, los)], [hi - m for m, hi in zip(means, his)]],
            fmt="o",
            color=C["ink"],
            ecolor=C["hl"],
            capsize=3,
        )
        ax.axvline(0, color=C["mute"], lw=0.8)
        ax.set_yticks(ypos)
        ax.set_yticklabels(names, fontsize=8)
        ax.set_title(
            f"Bayesian logistic coefs (MH accept={bayes_occ['accept_rate']:.2f}; "
            f"AUC_te={bayes_occ.get('posterior_mean_auc_holdout')})"
        )
        p = FIG / "fig_bayes_logistic_coefs.png"
        fig.tight_layout()
        fig.savefig(p, dpi=150)
        plt.close(fig)
        paths.append(str(p))

        # PPC rates + trace
        fig, axes = plt.subplots(1, 2, figsize=(9, 3.5))
        rates = np.asarray(bayes_occ.get("ppc_rates") or [], dtype=float)
        if rates.size:
            axes[0].hist(rates, bins=25, color=C["hl"], alpha=0.85)
            axes[0].axvline(bayes_occ["ppc"]["obs"], color=C["accent"], lw=2)
            axes[0].set_title(f"PPC crash rate (ppp={bayes_occ['ppc']['bayesian_pvalue']:.2f})")
        ch = bayes_occ.get("chain_for_plot") or {}
        if ch.get("intensity"):
            axes[1].plot(ch["intensity"], color=C["db"], lw=0.8, label="intensity")
            axes[1].plot(ch["H_v"], color=C["ok"], lw=0.8, label="H_v")
            axes[1].legend(frameon=False, fontsize=8)
            axes[1].set_title("MH traces (thinned)")
            axes[1].set_xlabel("sample")
        p = FIG / "fig_bayes_logistic_ppc.png"
        fig.tight_layout()
        fig.savefig(p, dpi=150)
        plt.close(fig)
        paths.append(str(p))

    return paths


def write_notebooks(summary: dict[str, Any]) -> list[str]:
    import nbformat as nbf

    def md(s: str):
        return nbf.v4.new_markdown_cell(s)

    def code(s: str):
        return nbf.v4.new_code_cell(s)

    FIG_REL = "../../out/signal_boards/figs"
    OUT_REL = "../../out/signal_boards"
    written: list[str] = []

    # --- signal_boards.ipynb ---
    nb = nbf.v4.new_notebook()
    nb.cells = [
        md(
            """# Signal boards — Promote risk / features

Gated SSM intensity · z*-path · Nanex∩SSM · VPIN×size · H^v/FEI · thin-excess.

**Slice:** ETH/BTC · HL+Deribit+Kraken · 2026-09-04…10 · n_gated=275.  
**Cross-link:** equity curves → [`../strategy_lab/`](../strategy_lab/) (do not overwrite).  
**SoT:** [`../../DESK_MEMO.md`](../../DESK_MEMO.md) §7 · playbook [`../../TRADING_APPLICATIONS.md`](../../TRADING_APPLICATIONS.md).
"""
        ),
        code(
            f"""
import json
from pathlib import Path
from IPython.display import Image, display, Markdown

OUT = Path('{OUT_REL}')
FIG = OUT / 'figs'
s = json.loads((OUT/'signal_boards_summary.json').read_text())
print('n_events', s['n_events'], 'n_figs', len(s.get('figs', [])))
print('series venues', s['series']['venues'])
board_figs = [
    'fig_gated_intensity_ts.png',
    'fig_zstar_path_ts.png',
    'fig_nanex_ssm_ts.png',
    'fig_vpin_x_size_ts.png',
    'fig_hv_fei_ts.png',
    'fig_thin_excess_ts.png',
    'fig_event_heatmaps.png',
    'fig_feature_vs_severity.png',
]
for name in board_figs:
    p = FIG/name
    display(Markdown(f'### {{name}}'))
    if p.exists():
        display(Image(filename=str(p)))
    else:
        print('missing', p)
"""
        ),
    ]
    path = Path(__file__).parent / "signal_boards.ipynb"
    nbf.write(nb, path)
    written.append(str(path))

    # --- info_theory.ipynb ---
    nb = nbf.v4.new_notebook()
    nb.cells = [
        md(
            """# Information theory — cross_miniflash features

Mutual information / lagged MI between pre-crash features and crash outcomes.  
**Honesty:** n_events=275, occurrence halves n=84 — MI noisy; TE-style lag scan is descriptive, not causal.  
OFI not on panel_cache → skipped (VPIN / intensity / RV / H^v used).
"""
        ),
        code(
            f"""
import json
from pathlib import Path
from IPython.display import Image, display, Markdown
OUT = Path('{OUT_REL}')
FIG = OUT/'figs'
info = json.loads((OUT/'signal_boards_summary.json').read_text())['info_theory']
print(info.get('sample_honesty'))
print('ofi:', info.get('ofi_note'))
print('venue entropy bits:', info.get('venue_crash_entropy',{{}}).get('H_bits'))
print('event MI:', info.get('event_mi'))
print('lagged:', info.get('lagged_mi_scan',{{}}).get('by_target'))
for name in ['fig_mi_event.png','fig_mi_occurrence.png','fig_venue_entropy.png','fig_lagged_mi_scan.png']:
    display(Markdown('### '+name))
    display(Image(filename=str(FIG/name)))
"""
        ),
    ]
    path = Path(__file__).parent / "info_theory.ipynb"
    nbf.write(nb, path)
    written.append(str(path))

    # --- statistical.ipynb ---
    nb = nbf.v4.new_notebook()
    nb.cells = [
        md(
            """# Statistical panel — bootstrap · time-split · ROC · calibration

Occurrence Soft Promote (AUC_te≈0.635) re-plotted with desk figures.  
Bootstrap n_boot=800, seed family 41–46. Early/late day split as Phase 4.
"""
        ),
        code(
            f"""
import json
from pathlib import Path
from IPython.display import Image, display, Markdown
OUT = Path('{OUT_REL}')
FIG = OUT/'figs'
st = json.loads((OUT/'signal_boards_summary.json').read_text())['statistical']
print('bootstrap keys', list(st['bootstrap'].keys()))
print('time_split', st['time_split'])
print('ROC AUC', st['occurrence_roc'].get('auc_test'))
for name in ['fig_bootstrap_cis.png','fig_time_split.png','fig_occurrence_roc.png','fig_occurrence_calibration.png']:
    display(Markdown('### '+name))
    display(Image(filename=str(FIG/name)))
"""
        ),
    ]
    path = Path(__file__).parent / "statistical.ipynb"
    nbf.write(nb, path)
    written.append(str(path))

    # --- bayesian.ipynb ---
    nb = nbf.v4.new_notebook()
    nb.cells = [
        md(
            """# Bayesian models — V-recovery & occurrence

1. **Beta–Binomial** on V-recovery rate. Prior: Beta(1,1)=Uniform. PPC on share_V.  
2. **Bayesian logistic** (RW Metropolis–Hastings) on day-half crash occurrence.  
   Prior: β_j ~ N(0, 2²) on standardized X. PPC on mean crash rate.

No PyMC/numpyro on this host — conjugate + custom MH is the clean install path.  
Not theater: priors stated, accept rate reported, PPC Bayesian p-values shown.
"""
        ),
        code(
            f"""
import json
from pathlib import Path
from IPython.display import Image, display, Markdown
OUT = Path('{OUT_REL}')
FIG = OUT/'figs'
s = json.loads((OUT/'signal_boards_summary.json').read_text())
bv, bo = s['bayesian']['v_recovery'], s['bayesian']['occurrence']
print('V-recovery prior', bv['prior'])
print('posterior mean', bv['posterior']['mean'], 'CI', bv['posterior']['ci95'])
print('PPC ppp', bv['ppc']['bayesian_pvalue'])
print('---')
print('logistic prior', bo.get('prior'))
print('accept_rate', bo.get('accept_rate'), 'AUC_te', bo.get('posterior_mean_auc_holdout'))
print('PPC', bo.get('ppc'))
print('coef', {{k: v['mean'] for k,v in (bo.get('coef') or {{}}).items()}})
for name in ['fig_bayes_v_recovery.png','fig_bayes_logistic_coefs.png','fig_bayes_logistic_ppc.png']:
    display(Markdown('### '+name))
    display(Image(filename=str(FIG/name)))
"""
        ),
    ]
    path = Path(__file__).parent / "bayesian.ipynb"
    nbf.write(nb, path)
    written.append(str(path))

    return written


def build_full_research_board_nb() -> str:
    import nbformat as nbf

    def md(s: str):
        return nbf.v4.new_markdown_cell(s)

    def code(s: str):
        return nbf.v4.new_code_cell(s)

    nb = nbf.v4.new_notebook()
    nb.cells = [
        md(
            """# Full research board — cross_miniflash

Synthesis of Phase 4 Promotes + application sims + **signal boards / info theory / stats / Bayesian**.

**Open these first** (also in `DESK_MEMO.md` / `applications/README.md`):

| Artifact | Path |
|----------|------|
| This notebook | `notebooks/full_research_board.ipynb` |
| Signal boards | `applications/signal_boards/signal_boards.ipynb` |
| Info theory | `applications/signal_boards/info_theory.ipynb` |
| Statistical | `applications/signal_boards/statistical.ipynb` |
| Bayesian | `applications/signal_boards/bayesian.ipynb` |
| Feature models | `applications/feature_models/severity_regime.ipynb` |
| MM quoting | `applications/mm_quoting/v_continuation_quoting.ipynb` |
| Strategy lab (equity) | `applications/strategy_lab/` |

Key PNGs under `applications/out/signal_boards/figs/`.
"""
        ),
        code(
            """
import json
from pathlib import Path
from IPython.display import Image, display, Markdown

BOOK = Path('..').resolve()
APP = BOOK / 'applications'
FIG = APP / 'out' / 'signal_boards' / 'figs'
SUM = APP / 'out' / 'signal_boards' / 'signal_boards_summary.json'
BOARD = APP / 'out' / 'applications_board.json'
s = json.loads(SUM.read_text()) if SUM.exists() else {}
b = json.loads(BOARD.read_text()) if BOARD.exists() else {}
print('signal_boards n_events', s.get('n_events'), 'figs', len(s.get('figs') or []))
print('applications board packages', list(b.keys())[:12] if isinstance(b, dict) else type(b))
"""
        ),
        md("## Signal boards (Promote features)"),
        code(
            """
for name in [
    'fig_gated_intensity_ts.png','fig_zstar_path_ts.png','fig_nanex_ssm_ts.png',
    'fig_vpin_x_size_ts.png','fig_hv_fei_ts.png','fig_thin_excess_ts.png',
    'fig_event_heatmaps.png','fig_feature_vs_severity.png',
]:
    p = FIG/name
    display(Markdown(f'**{name}**'))
    if p.exists(): display(Image(filename=str(p)))
"""
        ),
        md("## Information theory"),
        code(
            """
info = s.get('info_theory') or {}
print(info.get('sample_honesty'))
print('venue H_bits', (info.get('venue_crash_entropy') or {}).get('H_bits'))
for name in ['fig_mi_event.png','fig_mi_occurrence.png','fig_venue_entropy.png','fig_lagged_mi_scan.png']:
    display(Markdown(f'**{name}**'))
    display(Image(filename=str(FIG/name)))
"""
        ),
        md("## Statistical + Bayesian"),
        code(
            """
st = s.get('statistical') or {}
print('ROC AUC', (st.get('occurrence_roc') or {}).get('auc_test'))
bv = (s.get('bayesian') or {}).get('v_recovery') or {}
bo = (s.get('bayesian') or {}).get('occurrence') or {}
print('V posterior', (bv.get('posterior') or {}).get('mean'), (bv.get('posterior') or {}).get('ci95'))
print('logistic AUC_te', bo.get('posterior_mean_auc_holdout'), 'ppp', (bo.get('ppc') or {}).get('bayesian_pvalue'))
for name in [
    'fig_bootstrap_cis.png','fig_time_split.png','fig_occurrence_roc.png','fig_occurrence_calibration.png',
    'fig_bayes_v_recovery.png','fig_bayes_logistic_coefs.png','fig_bayes_logistic_ppc.png',
]:
    display(Markdown(f'**{name}**'))
    display(Image(filename=str(FIG/name)))
"""
        ),
        md(
            """## Cross-links

- Feature models summary: `applications/feature_models/out/feature_models_summary.json`
- MM quoting figs: `applications/mm_quoting/out/figs/`
- Strategy lab equity (sibling): `applications/strategy_lab/out/figs/`
- Risk apps figs: `applications/out/{kill_ladder,nanex_burst,hl_thin_sor,hv_fei_capacity}/figs/`
"""
        ),
    ]
    path = BOOK / "notebooks" / "full_research_board.ipynb"
    path.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(nb, path)
    return str(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel-json", type=Path, default=PANEL_CACHE)
    ap.add_argument("--panel-rows", type=Path, default=PANEL_ROWS)
    args = ap.parse_args()

    if not args.panel_json.exists():
        print("missing panel cache", args.panel_json, file=sys.stderr)
        return 1
    if not args.panel_rows.exists():
        print("missing panel rows", args.panel_rows, file=sys.stderr)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)

    cache = _load_json(args.panel_json)
    rows = _load_json(args.panel_rows)
    row_events = flatten_panel_rows(rows)
    events = merge_features(row_events, cache.get("events") or [])
    # attach FEI/thin from rows cells onto a light cell list for series
    cells_for_series = []
    for cell in rows:
        cells_for_series.append(
            {
                "venue": cell["venue"],
                "symbol": cell["symbol"],
                "day": cell["day"],
                "complete": cell.get("complete", 1),
                "thin_excess": cell.get("thin_excess"),
                "H_v": cell.get("H_v"),
                "FEI": cell.get("FEI"),
            }
        )

    # occurrence rows via feature_models helper (needs panel-shaped dict)
    panel_for_occ = {
        "events": cache.get("events") or [],
        "cells": cache.get("cells") or [],
    }
    # cells in cache lack FEI/thin — occurrence only needs day_vpin/intensity/H_v/notional
    rows_occ = build_cell_crash_labels(panel_for_occ)
    occurrence_fit = fit_logistic_occurrence(rows_occ)

    series = build_daily_series(events, cells_for_series)
    info = mutual_info_panel(events, rows_occ)
    stats = statistical_panel(events, rows_occ, occurrence_fit)
    bayes_v = beta_binomial_v_recovery(events)
    bayes_occ = bayesian_logistic_occurrence(rows_occ)

    figs = plot_all(series, events, info, stats, bayes_v, bayes_occ)

    # strip heavy draw arrays from summary (keep thin)
    bayes_v_light = {k: v for k, v in bayes_v.items() if k not in ("post_draws", "share_rep")}
    bayes_v_light["post_draws_n"] = len(bayes_v.get("post_draws") or [])
    bayes_occ_light = {k: v for k, v in bayes_occ.items() if k not in ("chain_for_plot", "ppc_rates")}
    if "chain_for_plot" in bayes_occ:
        bayes_occ_light["chain_for_plot_keys"] = list(bayes_occ["chain_for_plot"].keys())

    summary = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "n_events": len(events),
        "n_occurrence_rows": len(rows_occ),
        "panel_json": str(args.panel_json),
        "panel_rows": str(args.panel_rows),
        "series": series,
        "info_theory": info,
        "statistical": stats,
        "bayesian": {"v_recovery": bayes_v_light, "occurrence": bayes_occ_light},
        "occurrence_fit_ref": {
            "auc_test": occurrence_fit.get("auc_test"),
            "brier_test": occurrence_fit.get("brier_test"),
        },
        "figs": figs,
        "cross_link_strategy_lab": str(APP / "strategy_lab"),
        "note": "Strategy equity curves owned by strategy_lab — signal_boards does not overwrite.",
    }
    # For notebook/PPC plots we need draws on disk separately
    draws_path = OUT / "bayes_draws.json"
    draws_path.write_text(
        json.dumps(
            jsonable(
                {
                    "v_post_draws": bayes_v.get("post_draws"),
                    "v_share_rep": bayes_v.get("share_rep"),
                    "occ_chain": bayes_occ.get("chain_for_plot"),
                    "occ_ppc_rates": bayes_occ.get("ppc_rates"),
                }
            ),
            indent=2,
        )
    )
    # Re-plot bayesian using full draws already done in plot_all

    sum_path = OUT / "signal_boards_summary.json"
    # embed thin draws for notebook convenience in bayesian section of a companion? 
    # Keep summary lean; notebooks read figs.
    # But bayesian notebook references summary only — restore minimal draws into light via bayes_draws
    summary["bayesian"]["v_recovery"]["post_draws"] = bayes_v.get("post_draws")
    summary["bayesian"]["v_recovery"]["share_rep"] = bayes_v.get("share_rep")
    summary["bayesian"]["occurrence"]["chain_for_plot"] = bayes_occ.get("chain_for_plot")
    summary["bayesian"]["occurrence"]["ppc_rates"] = bayes_occ.get("ppc_rates")

    sum_path.write_text(json.dumps(jsonable(summary), indent=2))
    print("wrote", sum_path)
    print("figs", len(figs))
    for f in figs:
        print(" ", f)

    nbs = write_notebooks(summary)
    frb = build_full_research_board_nb()
    print("notebooks:", *nbs, frb, sep="\n  ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
