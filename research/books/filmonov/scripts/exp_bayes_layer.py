from __future__ import annotations
#!/usr/bin/env python3
"""Bayesian layer for Filimonov desk features.

Conjugate Beta-Binomial / Poisson-Gamma + hierarchical EB shrinkage +
Laplace logistic. Prefer scipy/numpy (pymc/numpyro not in env).

Writes ``out/bayes/`` JSON + figs.
ClickHouse MCP banned. No git commit.
"""

import os

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy import stats  # noqa: E402

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(Path(os.environ.get('WAREHOUSE_SRC') or ((Path(os.environ.get('WAREHOUSE_ROOT') or (Path.home() / 'lab' / 'lab-n2070' / 'warehouse')) / 'src')))))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb')) / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import (  # noqa: E402
    CORE_VENUES,
    ensure_env,
    load_day_trades,
    load_tob_any,
    normalize_side,
)
from _stats_bayes import (  # noqa: E402
    beta_binomial_posterior,
    density_grid_beta,
    density_grid_gamma,
    hierarchical_beta_shrinkage,
    hierarchical_poisson_shrinkage,
    logistic_laplace_posterior,
    poisson_gamma_posterior,
    posterior_predictive_beta,
    prior_sensitivity_beta,
)
from research.lib.hftpat import (  # noqa: E402
    event_window_markout,
    ignition_bar_timestamps,
    ignition_events,
    price_fade_events,
    quote_storm_detect,
    quote_storm_intensity,
    spread_irf_after_events,
)

OUT = BOOK / "out" / "bayes"
FIGS = OUT / "figs"
DAYS_DEFAULT = ["2026-09-25", "2026-09-26", "2026-09-27", "2026-09-30"]
SEED = 42


def _json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=_default))


def _default(o: Any) -> Any:
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating,)):
        x = float(o)
        return x if np.isfinite(x) else None
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    if isinstance(o, float) and (o != o):
        return None
    return str(o)


def _is_synth(tob: dict | None) -> bool:
    if tob is None:
        return False
    return "trade_synth" in str(tob.get("source", "")).lower()


def _savefig(fig: plt.Figure, name: str) -> str:
    FIGS.mkdir(parents=True, exist_ok=True)
    path = FIGS / name
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return str(path.relative_to(BOOK))


def _subsample(n: int, max_n: int, seed: int) -> np.ndarray:
    if n <= max_n:
        return np.arange(n, dtype=np.int64)
    step = max(1, int(np.ceil(n / max_n)))
    idx = np.arange(0, n, step, dtype=np.int64)
    if idx.size > max_n:
        rng = np.random.default_rng(seed)
        idx = np.sort(rng.choice(idx, size=max_n, replace=False))
    return idx


def collect_counts(
    symbols: list[str],
    days: list[str],
    *,
    max_files: int,
    max_trades: int,
) -> dict[str, Any]:
    ensure_env()
    day_rows: list[dict[str, Any]] = []
    # event-level for logistic
    storm_adverse: list[dict[str, float]] = []
    fade_widen: list[dict[str, float]] = []

    for symbol in symbols:
        for day in days:
            for venue in CORE_VENUES:
                print(f"  bayes {symbol} {venue} {day}", flush=True)
                row: dict[str, Any] = {
                    "symbol": symbol,
                    "venue": venue,
                    "day": day,
                    "native_tob": False,
                    "complete": False,
                }
                try:
                    rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
                    tape = rec["tape"]
                    row["complete"] = bool((rec.get("completeness") or {}).get("complete"))
                    ts = np.asarray(tape["ts"], dtype=np.int64)
                    side = normalize_side(tape["side"])
                    qty = np.asarray(tape["qty"], dtype=np.float64)
                    px = np.asarray(tape["px"], dtype=np.float64)
                    row["n_trades"] = int(tape.get("n", 0))
                except Exception as exc:  # noqa: BLE001
                    row["trade_error"] = f"{type(exc).__name__}: {exc}"
                    day_rows.append(row)
                    continue
                try:
                    tob = load_tob_any(venue, symbol, day)
                except Exception as exc:  # noqa: BLE001
                    row["tob_error"] = f"{type(exc).__name__}: {exc}"
                    day_rows.append(row)
                    continue
                synth = _is_synth(tob)
                row["is_trade_synth"] = synth
                row["n_tob"] = int(tob.get("n", len(tob["ts"])))
                row["native_tob"] = (not synth) and row["n_tob"] >= 50
                if not row["native_tob"] or not row["complete"]:
                    day_rows.append(row)
                    continue

                mid = np.asarray(
                    tob.get("mid", 0.5 * (np.asarray(tob["bid"]) + np.asarray(tob["ask"]))),
                    dtype=np.float64,
                )
                intens = quote_storm_intensity(tob["ts"], tob["bid"], tob["ask"], tob["bid_sz"], tob["ask_sz"])
                storms = quote_storm_detect(
                    intens, z_thresh=3.0, min_cancel_frac=0.3, max_mid_range_bps=15.0, min_intensity_hz=0.0
                )
                storm_ts = np.asarray(storms["ts"], dtype=np.int64)
                span_h = max(1e-6, (float(tob["ts"][-1] - tob["ts"][0]) / 1e9) / 3600.0)
                row["n_storm"] = int(storms["n_events"])
                row["span_h"] = float(span_h)
                row["storms_per_hour"] = float(storms["n_events"]) / span_h

                idx = _subsample(ts.size, max_trades, seed=hash(f"b{symbol}{venue}{day}") % 10_000)
                tt, sd = ts[idx], side[idx]
                fade = price_fade_events(
                    tt, sd, tob["ts"], tob["bid"], tob["ask"], tob["bid_sz"], tob["ask_sz"], tau_ms=100.0
                )
                row["n_fade"] = int(fade["n_fade"])
                row["n_fade_trials"] = int(fade["n_trades"])
                ti = np.asarray(fade["trade_i"], dtype=np.int64)
                ff = np.asarray(fade["fade"], dtype=np.int64)
                fade_ts = tt[ti[ff > 0]] if ti.size and ff.size else np.zeros(0, dtype=np.int64)

                ign = ignition_events(
                    ts, px, qty, bar_s=1.0, phase1_bars=3, phase2_bars=3, phase3_bars=5,
                    vol_z=1.0, mid_quiet_bps=15.0, move_bps=5.0, min_recovery=0.15,
                )
                ign_starts, _ = ignition_bar_timestamps(ign)
                row["n_ignition"] = int(len(ign_starts))

                # storm adverse: per-event markout > 0
                mo = event_window_markout(storm_ts, ts, side, tob["ts"], mid, post_ms=500.0, horizon_ms=1000.0)
                per = np.asarray(mo.get("per_event_mean", []), dtype=np.float64)
                per = per[np.isfinite(per)]
                row["n_storm_mo"] = int(per.size)
                row["n_storm_adverse"] = int(np.sum(per > 0))
                for v in per:
                    storm_adverse.append({"y": 1.0 if v > 0 else 0.0, "storm": 1.0, "venue_hl": 1.0 if venue == "hyperliquid" else 0.0})

                # placebo non-storm for logistic contrast
                rng = np.random.default_rng(hash(f"np{symbol}{venue}{day}") % 10_000)
                if tob["ts"].size > 20:
                    plac = rng.choice(np.asarray(tob["ts"], dtype=np.int64), size=min(40, int(tob["ts"].size)), replace=False)
                    pmo = event_window_markout(plac, ts, side, tob["ts"], mid, post_ms=500.0, horizon_ms=1000.0)
                    pper = np.asarray(pmo.get("per_event_mean", []), dtype=np.float64)
                    pper = pper[np.isfinite(pper)]
                    for v in pper:
                        storm_adverse.append({"y": 1.0 if v > 0 else 0.0, "storm": 0.0, "venue_hl": 1.0 if venue == "hyperliquid" else 0.0})

                # fade widen: Δspread at 250ms > 0
                irf = spread_irf_after_events(
                    fade_ts, tob["ts"], tob["bid"], tob["ask"],
                    lags_ms=(0.0, 250.0, 500.0),
                )
                # approximate per-event widen via IRF mean sign + Bernoulli from peak
                # build event-level: compare spread at +250 vs pre
                tob_ts = np.asarray(tob["ts"], dtype=np.int64)
                bid = np.asarray(tob["bid"], dtype=np.float64)
                ask = np.asarray(tob["ask"], dtype=np.float64)
                midv = 0.5 * (bid + ask)
                with np.errstate(divide="ignore", invalid="ignore"):
                    spr = np.where(midv > 0, 1e4 * (ask - bid) / midv, np.nan)
                n_widen = 0
                n_fade_ev = 0
                for e in fade_ts[:200]:
                    i_ev = int(np.searchsorted(tob_ts, int(e), side="right") - 1)
                    if i_ev < 2:
                        continue
                    i_pre0 = int(np.searchsorted(tob_ts, int(e) - 1_000_000_000, side="left"))
                    base = spr[i_pre0:i_ev]
                    base = base[np.isfinite(base)]
                    if base.size < 2:
                        continue
                    j = int(np.searchsorted(tob_ts, int(e) + 250_000_000, side="right") - 1)
                    if j < 0 or j >= spr.size or not np.isfinite(spr[j]):
                        continue
                    widen = 1.0 if spr[j] > float(np.nanmean(base)) else 0.0
                    fade_widen.append({"y": widen, "fade": 1.0})
                    n_fade_ev += 1
                    n_widen += int(widen)
                row["n_fade_irf"] = n_fade_ev
                row["n_fade_widen"] = n_widen
                dlt = np.asarray(irf.get("mean_delta_bps", []), dtype=np.float64)
                dlt = dlt[np.isfinite(dlt)]
                row["fade_irf_peak"] = float(np.max(dlt)) if dlt.size else float("nan")
                day_rows.append(row)

    return {"day_rows": day_rows, "storm_adverse": storm_adverse, "fade_widen": fade_widen}


def run_bayes(panel: dict[str, Any]) -> dict[str, Any]:
    rows = [r for r in panel["day_rows"] if r.get("native_tob") and r.get("complete")]

    # --- pooled fade P ---
    n_fade = sum(int(r.get("n_fade", 0)) for r in rows)
    n_trials = sum(int(r.get("n_fade_trials", 0)) for r in rows)
    fade_post = beta_binomial_posterior(n_fade, n_trials, a0=1.0, b0=1.0)
    fade_sens = prior_sensitivity_beta(n_fade, n_trials)
    fade_ppc = posterior_predictive_beta(fade_post, n_pred_trials=max(100, n_trials // max(len(rows), 1)), seed=SEED)

    # --- storms/hour Poisson-Gamma (pool HL) ---
    hl = [r for r in rows if r["venue"] == "hyperliquid"]
    storm_count = sum(int(r.get("n_storm", 0)) for r in hl)
    storm_exp = sum(float(r.get("span_h", 0.0)) for r in hl)
    storm_post = poisson_gamma_posterior(storm_count, storm_exp, a0=1.0, b0=1.0)

    # --- ignition rate per day ---
    ign_count = sum(int(r.get("n_ignition", 0)) for r in rows)
    ign_exp = float(len(rows))  # day-venues
    ign_post = poisson_gamma_posterior(ign_count, ign_exp, a0=1.0, b0=1.0)

    # hierarchical venue fade
    by_venue: dict[str, list[dict]] = {}
    for r in rows:
        by_venue.setdefault(r["venue"], []).append(r)
    v_succ, v_trial, v_lab = [], [], []
    for v, rs in by_venue.items():
        v_succ.append(sum(int(r.get("n_fade", 0)) for r in rs))
        v_trial.append(sum(int(r.get("n_fade_trials", 0)) for r in rs))
        v_lab.append(v)
    hier_fade_venue = hierarchical_beta_shrinkage(v_succ, v_trial, v_lab)

    # hierarchical day (HL ETH) storms
    day_counts, day_exp, day_lab = [], [], []
    for r in hl:
        if r["symbol"] != "ETH":
            continue
        day_counts.append(float(r.get("n_storm", 0)))
        day_exp.append(float(r.get("span_h", 1.0)))
        day_lab.append(str(r["day"]))
    hier_storm_day = hierarchical_poisson_shrinkage(day_counts, day_exp, day_lab)

    # hierarchical venue ignition rate
    ig_c, ig_e, ig_l = [], [], []
    for v, rs in by_venue.items():
        ig_c.append(sum(int(r.get("n_ignition", 0)) for r in rs))
        ig_e.append(float(len(rs)))
        ig_l.append(v)
    hier_ign_venue = hierarchical_poisson_shrinkage(ig_c, ig_e, ig_l)

    # P(adverse | storm) Beta
    n_adv = sum(int(r.get("n_storm_adverse", 0)) for r in rows)
    n_smo = sum(int(r.get("n_storm_mo", 0)) for r in rows)
    adverse_post = beta_binomial_posterior(n_adv, max(n_smo, 1), a0=1.0, b0=1.0)

    # P(widen | fade) Beta
    n_w = sum(int(r.get("n_fade_widen", 0)) for r in rows)
    n_fe = sum(int(r.get("n_fade_irf", 0)) for r in rows)
    widen_post = beta_binomial_posterior(n_w, max(n_fe, 1), a0=1.0, b0=1.0)

    # logistic P(adverse | storm)
    sa = panel["storm_adverse"]
    if sa:
        y = np.asarray([x["y"] for x in sa], dtype=np.float64)
        X = np.asarray([[x["storm"], x["venue_hl"]] for x in sa], dtype=np.float64)
        logit_adverse = logistic_laplace_posterior(y, X, prior_var=25.0)
    else:
        logit_adverse = {"n": 0, "converged": False}

    fw = panel["fade_widen"]
    if fw:
        y2 = np.asarray([x["y"] for x in fw], dtype=np.float64)
        X2 = np.asarray([[x["fade"]] for x in fw], dtype=np.float64)
        logit_widen = logistic_laplace_posterior(y2, X2, prior_var=25.0)
    else:
        logit_widen = {"n": 0, "converged": False}

    # candidates (Bayesian decision quantities — still Hold)
    candidates = [
        {
            "id": "info.bayes_fade_p_posterior",
            "decision": "Hold",
            "type": "E",
            "lenses": ["info", "mm"],
            "why": (
                f"P(fade) posterior mean={fade_post['mean']:.4g} "
                f"CrI95={fade_post['cri95']} n={n_trials}"
            ),
            "falsifier": "CrI covers values useless for MM widen (≈0) under skeptical prior → Hold",
            "bayes_quantity": "θ_fade",
            "wire_as": "MM pull / widen monitor threshold on posterior mean+CrI",
            "source": "bayes_layer",
        },
        {
            "id": "info.bayes_storm_rate_venue",
            "decision": "Hold",
            "type": "E",
            "lenses": ["info", "risk", "exec"],
            "why": (
                f"HL storms/h posterior mean={storm_post['mean']:.4g} "
                f"CrI95={storm_post['cri95']}"
            ),
            "falsifier": "posterior mass near 0 after wider days → Kill throttle",
            "bayes_quantity": "λ_storm",
            "wire_as": "exec throttle when λ posterior > descriptive threshold",
            "source": "bayes_layer",
        },
        {
            "id": "info.bayes_ignition_rate_venue",
            "decision": "Hold",
            "type": "E",
            "lenses": ["info", "risk"],
            "why": f"ignition/day-venue mean={ign_post['mean']:.4g} CrI95={ign_post['cri95']}",
            "falsifier": "venue hierarchy collapses to zero → research-only",
            "bayes_quantity": "λ_ign",
            "wire_as": "risk escalate strip rate",
            "source": "bayes_layer",
        },
        {
            "id": "info.bayes_adverse_given_storm",
            "decision": "Hold",
            "type": "E",
            "lenses": ["info", "mm", "risk"],
            "why": (
                f"P(adverse|storm) mean={adverse_post['mean']:.4g} CrI95={adverse_post['cri95']} "
                f"logit_storm_coef={logit_adverse.get('beta_mean', [None, None])[1] if logit_adverse.get('beta_mean') else None}"
            ),
            "falsifier": "P(adverse|storm) CrI ⊆ [0,0.5] and logit coeff CrI∋0 → Kill toxicity join",
            "bayes_quantity": "P(AS|storm)",
            "wire_as": "MM size cut in storm regime if posterior > 0.5 with CrI clear of 0.5",
            "source": "bayes_layer",
        },
        {
            "id": "info.bayes_widen_given_fade",
            "decision": "Hold",
            "type": "E",
            "lenses": ["info", "mm", "liq"],
            "why": f"P(widen|fade) mean={widen_post['mean']:.4g} CrI95={widen_post['cri95']}",
            "falsifier": "posterior mean ≤0.5 with CrI covering 0.5 → Kill widen-on-fade",
            "bayes_quantity": "P(widen|fade)",
            "wire_as": "temporary widen when fade cluster + P(widen) elevated",
            "source": "bayes_layer",
        },
        {
            "id": "info.fade_temp_vs_perm_impact",
            "decision": "Hold",
            "type": "E",
            "lenses": ["info", "cont"],
            "why": "multi-horizon markout temp/perm share from feature_stats companion",
            "falsifier": "perm_share≈1 with no reversion → permanent impact claim needs ≥10 days",
            "bayes_quantity": "impact_horizon_profile",
            "wire_as": "research tile — temporary vs permanent fade impact",
            "source": "bayes_layer",
        },
    ]

    return {
        "n_native_complete": len(rows),
        "fade_posterior": fade_post,
        "fade_prior_sensitivity": fade_sens,
        "fade_ppc": fade_ppc,
        "storm_rate_posterior": storm_post,
        "ignition_rate_posterior": ign_post,
        "adverse_given_storm": adverse_post,
        "widen_given_fade": widen_post,
        "hier_fade_venue": hier_fade_venue,
        "hier_storm_day_hl_eth": hier_storm_day,
        "hier_ignition_venue": hier_ign_venue,
        "logit_adverse_storm": logit_adverse,
        "logit_widen_fade": logit_widen,
        "prior_note": (
            "Default priors: Beta(1,1) / Gamma(1,1). Sensitivity includes Jeffreys and "
            "skeptical Beta(1,19)/Beta(1,99). Hierarchical uses moment-matched EB hyperparams "
            "blended 50/50 with weak prior. Laplace logistic ≈ N(MAP, −H⁻¹)."
        ),
        "candidates": candidates,
        "day_rows_light": [
            {k: v for k, v in r.items()} for r in rows
        ],
    }


def make_figs(art: dict[str, Any]) -> list[str]:
    paths: list[str] = []

    # 1. fade posterior density + prior
    post = art["fade_posterior"]
    grid = density_grid_beta(post)
    prior = density_grid_beta({"a": 1.0, "b": 1.0})
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(prior["x"], prior["y"], "--", color="#adb5bd", label="prior Beta(1,1)")
    ax.plot(grid["x"], grid["y"], color="#264653", label="posterior")
    ax.axvline(post["mean"], color="#e76f51", lw=1.2, label=f"mean={post['mean']:.4f}")
    ax.axvspan(post["cri95"][0], post["cri95"][1], alpha=0.15, color="#2a9d8f", label="95% CrI")
    ax.set_xlabel("θ = P(fade)")
    ax.set_ylabel("density")
    ax.set_title("Fade probability — Beta-Binomial posterior")
    ax.legend(fontsize=8)
    paths.append(_savefig(fig, "fig_posterior_fade.png"))

    # 2. storm rate gamma
    sp = art["storm_rate_posterior"]
    g = density_grid_gamma(sp)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(g["x"], g["y"], color="#264653")
    ax.axvline(sp["mean"], color="#e76f51", lw=1.2, label=f"mean={sp['mean']:.3f}")
    ax.axvspan(sp["cri95"][0], sp["cri95"][1], alpha=0.15, color="#2a9d8f")
    ax.set_xlabel("λ storms / hour (HL pool)")
    ax.set_title("Storm rate — Poisson-Gamma posterior")
    ax.legend(fontsize=8)
    paths.append(_savefig(fig, "fig_posterior_storm_rate.png"))

    # 3. forest of posterior means
    items = [
        ("P(fade)", art["fade_posterior"]),
        ("P(AS|storm)", art["adverse_given_storm"]),
        ("P(widen|fade)", art["widen_given_fade"]),
    ]
    # add venue fade hierarchy
    for g in art["hier_fade_venue"].get("groups", []):
        items.append((f"P(fade)|{g['label']}", g["posterior"]))
    fig, ax = plt.subplots(figsize=(8, max(4, 0.35 * len(items) + 1)))
    y = np.arange(len(items))
    means = [it[1]["mean"] for it in items]
    los = [it[1]["mean"] - it[1]["cri95"][0] for it in items]
    his = [it[1]["cri95"][1] - it[1]["mean"] for it in items]
    ax.errorbar(means, y, xerr=[los, his], fmt="o", color="#264653", capsize=3)
    ax.set_yticks(y)
    ax.set_yticklabels([it[0] for it in items], fontsize=8)
    ax.set_xlabel("posterior mean + 95% CrI")
    ax.set_title("Bayesian forest — probabilities")
    ax.set_xlim(0, 1)
    paths.append(_savefig(fig, "fig_forest_prob.png"))

    # 4. rate forest
    rate_items = [("λ_storm HL", art["storm_rate_posterior"]), ("λ_ign /day-venue", art["ignition_rate_posterior"])]
    for g in art["hier_ignition_venue"].get("groups", []):
        rate_items.append((f"λ_ign|{g['label']}", g["posterior"]))
    for g in art["hier_storm_day_hl_eth"].get("groups", []):
        rate_items.append((f"λ_storm|{g['label']}", g["posterior"]))
    fig, ax = plt.subplots(figsize=(8, max(4, 0.35 * len(rate_items) + 1)))
    y = np.arange(len(rate_items))
    means = [it[1]["mean"] for it in rate_items]
    los = [it[1]["mean"] - it[1]["cri95"][0] for it in rate_items]
    his = [it[1]["cri95"][1] - it[1]["mean"] for it in rate_items]
    ax.errorbar(means, y, xerr=[los, his], fmt="o", color="#2a9d8f", capsize=3)
    ax.set_yticks(y)
    ax.set_yticklabels([it[0] for it in rate_items], fontsize=7)
    ax.set_xlabel("posterior mean + 95% CrI")
    ax.set_title("Bayesian forest — rates")
    paths.append(_savefig(fig, "fig_forest_rates.png"))

    # 5. prior sensitivity
    sens = art["fade_prior_sensitivity"]["rows"]
    fig, ax = plt.subplots(figsize=(7, 4))
    y = np.arange(len(sens))
    means = [r["mean"] for r in sens]
    los = [r["mean"] - r["cri95"][0] for r in sens]
    his = [r["cri95"][1] - r["mean"] for r in sens]
    ax.errorbar(means, y, xerr=[los, his], fmt="o", color="#264653", capsize=3)
    ax.set_yticks(y)
    ax.set_yticklabels([r["prior"] for r in sens], fontsize=8)
    ax.set_title("Prior sensitivity — P(fade)")
    ax.set_xlabel("posterior mean + 95% CrI")
    paths.append(_savefig(fig, "fig_prior_sensitivity_fade.png"))

    # 6. PPC histogram
    ppc = art["fade_ppc"]
    fig, ax = plt.subplots(figsize=(7, 4))
    # redraw predictive from posterior
    a, b = art["fade_posterior"]["a"], art["fade_posterior"]["b"]
    rng = np.random.default_rng(SEED)
    theta = rng.beta(a, b, size=2000)
    yhat = rng.binomial(ppc["n_pred_trials"], theta)
    ax.hist(yhat, bins=30, color="#8ab17d", alpha=0.85, density=True)
    ax.axvline(ppc["y_mean"], color="#e76f51", label=f"PPC mean={ppc['y_mean']:.1f}")
    ax.set_title(f"PPC: y ~ Bin(n={ppc['n_pred_trials']}, θ) for fade")
    ax.legend(fontsize=8)
    paths.append(_savefig(fig, "fig_ppc_fade.png"))

    # 7. logistic coeffs
    la = art["logit_adverse_storm"]
    if la.get("beta_mean"):
        fig, ax = plt.subplots(figsize=(7, 3.5))
        names = la.get("names", [])
        means = la["beta_mean"]
        cri = la["cri95"]
        y = np.arange(len(names))
        los = [means[i] - cri[i][0] for i in range(len(names))]
        his = [cri[i][1] - means[i] for i in range(len(names))]
        ax.errorbar(means, y, xerr=[los, his], fmt="o", color="#264653", capsize=3)
        ax.axvline(0, color="#c1121f", lw=0.9)
        ax.set_yticks(y)
        ax.set_yticklabels(names, fontsize=8)
        ax.set_title("Laplace logistic — P(adverse | storm, venue)")
        paths.append(_savefig(fig, "fig_logit_adverse.png"))

    return paths


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", nargs="*", default=DAYS_DEFAULT)
    ap.add_argument("--symbols", nargs="*", default=["ETH", "BTC"])
    ap.add_argument("--max-files", type=int, default=24)
    ap.add_argument("--max-trades", type=int, default=12_000)
    args = ap.parse_args()

    print("=== exp_bayes_layer ===", flush=True)
    panel = collect_counts(args.symbols, args.days, max_files=args.max_files, max_trades=args.max_trades)
    art = run_bayes(panel)
    figs = make_figs(art)
    art["fig_paths"] = figs
    art["meta"] = {
        "days": args.days,
        "symbols": args.symbols,
        "method": "conjugate Beta-Binomial / Poisson-Gamma + EB hierarchical + Laplace logistic",
        "deps": "scipy+numpy only (no pymc/numpyro)",
    }
    # drop raw event lists from panel dump
    out = {k: v for k, v in art.items()}
    _json(OUT / "bayes_layer.json", out)
    _json(OUT / "fig_index.json", {"figs": figs})
    print(json.dumps({
        "n_native": art["n_native_complete"],
        "fade_mean": art["fade_posterior"]["mean"],
        "fade_cri": art["fade_posterior"]["cri95"],
        "storm_mean": art["storm_rate_posterior"]["mean"],
        "adverse_mean": art["adverse_given_storm"]["mean"],
        "widen_mean": art["widen_given_fade"]["mean"],
        "figs": len(figs),
    }, indent=2, default=_default))


if __name__ == "__main__":
    main()
