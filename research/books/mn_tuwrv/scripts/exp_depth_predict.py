from __future__ import annotations
#!/usr/bin/env python3
"""Pass 2.8 depth / information / uses / predictive-power for mn_tuwrv.

Reads Pass 2.7 expand_panel (n_ok=204). Adds:
  - thesis empirics: signature plot, optimal K, noise ACF/MA(1) on tape subset
  - information content: noise stack vs spread/Amihud/intensity/RV/range proxies
  - predictive OOS: next-day targets, rank-IC + bootstrap CIs, DM vs sparse
  - venue/symbol taxonomy + TOD profiles (subset)
  - decision hygiene: Kill weak predictive; Hold suggestive; no forced Promote

ClickHouse MCP banned. No git commits.
"""

import os
import argparse
import json
import math
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from numpy.typing import NDArray

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(Path(os.environ.get("WAREHOUSE_SRC") or ((Path(os.environ.get("WAREHOUSE_ROOT") or (Path.home() / "lab" / "lab-n2070" / "warehouse")) / "src")))))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(os.environ.get("ARES_STARTARB") or (Path.home() / "srv" / "ares-startarb")) / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ares_micro.stats import spearman_r  # noqa: E402
from ares_micro.vol.tsrv import (  # noqa: E402
    grid_log_price_from_tape,
    noise_return_acf,
    optimal_K_scan,
    signature_rv_curve,
)

OUT = BOOK / "out" / "depth_predict"
FIGS = BOOK / "out" / "desk_synthesis" / "figs"
EXPAND = BOOK / "out" / "expand_panel" / "expand_panel.json"

# Pre-registered predictive gates (honest — do not force Promote)
GATE_IC_LO = 0.10  # |IC| CI_lo must clear this on OOS late half
GATE_N_MIN = 30


def _json_dump(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    def _default(o):
        if isinstance(o, (np.floating, np.integer)):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, (np.bool_,)):
            return bool(o)
        raise TypeError(type(o))

    path.write_text(json.dumps(obj, indent=2, default=_default))


def _spearman_boot_ci(x, y, *, n_boot=800, seed=7) -> dict[str, float]:
    a = np.asarray(x, dtype=np.float64)
    b = np.asarray(y, dtype=np.float64)
    m = np.isfinite(a) & np.isfinite(b)
    a, b = a[m], b[m]
    if a.size < 5:
        return {"n": float(a.size), "rho": float("nan"), "lo": float("nan"), "hi": float("nan")}
    rng = np.random.default_rng(seed)
    point = float(spearman_r(a, b))
    boots = []
    n = a.size
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)  # paired resample
        boots.append(float(spearman_r(a[idx], b[idx])))
    ba = np.asarray(boots)
    ba = ba[np.isfinite(ba)]
    lo, hi = (float(np.quantile(ba, 0.025)), float(np.quantile(ba, 0.975))) if ba.size else (float("nan"), float("nan"))
    return {"n": float(a.size), "rho": point, "lo": lo, "hi": hi}


def _shuffle_p(x, y, *, n_shuffle=400, seed=11) -> float:
    a = np.asarray(x, dtype=np.float64)
    b = np.asarray(y, dtype=np.float64)
    m = np.isfinite(a) & np.isfinite(b)
    a, b = a[m], b[m]
    if a.size < 5:
        return float("nan")
    obs = abs(float(spearman_r(a, b)))
    rng = np.random.default_rng(seed)
    null = [abs(float(spearman_r(a, rng.permutation(b)))) for _ in range(n_shuffle)]
    na = np.asarray(null)
    na = na[np.isfinite(na)]
    return float(np.mean(na >= obs)) if na.size else float("nan")


def _feature_row(r: dict) -> dict[str, float]:
    spread = r.get("spread") or {}
    cal = r.get("calendar") or {}
    return {
        "noise_std": float(r.get("noise_std", cal.get("noise_std", float("nan")))),
        "noise_var": float(cal.get("noise_var", float("nan"))),
        "fifth_over_fourth": float(r.get("fifth_over_fourth_cal", cal.get("fifth_over_fourth", float("nan")))),
        "fifth_over_fourth_mid": float(r.get("fifth_over_fourth_mid", float("nan"))),
        "sparse_minus_tsrv": float(r.get("sparse_minus_tsrv", float("nan"))),
        "tsrv_over_sparse": float(r.get("tsrv_over_sparse", float("nan"))),
        "first_adj": float(r.get("first_adj", cal.get("first_adj", float("nan")))),
        "fourth": float(r.get("fourth", cal.get("fourth", float("nan")))),
        "fifth": float(r.get("fifth", cal.get("fifth", float("nan")))),
        "spread_bps": float(spread.get("spread_bps_mean", float("nan"))),
        "amihud": float(r.get("amihud", float("nan"))),
        "intensity": float(r.get("intensity", float("nan"))),
        "n_trades": float(r.get("n_trades", float("nan"))),
        "sqrt_fourth": float(math.sqrt(max(float(r.get("fourth", cal.get("fourth", float("nan")))), 0.0)))
        if np.isfinite(float(r.get("fourth", cal.get("fourth", float("nan")))))
        else float("nan"),
        "sqrt_first_adj": float(math.sqrt(max(float(r.get("first_adj", cal.get("first_adj", float("nan")))), 0.0)))
        if np.isfinite(float(r.get("first_adj", cal.get("first_adj", float("nan")))))
        else float("nan"),
    }


def _next_day(day: str) -> str:
    d = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return (d + timedelta(days=1)).strftime("%Y-%m-%d")


def build_panel_index(rows: list[dict]) -> dict[tuple[str, str, str], dict]:
    out = {}
    for r in rows:
        if not r.get("ok"):
            continue
        out[(r["venue"], r["symbol"], r["day"])] = r
    return out


def information_content(rows: list[dict]) -> dict:
    """Contemporaneous co-movement of noise stack with liquidity / activity / vol."""
    feats = []
    for r in rows:
        if not r.get("ok"):
            continue
        f = _feature_row(r)
        f["venue"] = r["venue"]
        f["symbol"] = r["symbol"]
        f["day"] = r["day"]
        feats.append(f)

    predictors = [
        "noise_std",
        "fifth_over_fourth",
        "fifth_over_fourth_mid",
        "sparse_minus_tsrv",
        "tsrv_over_sparse",
    ]
    targets = [
        "spread_bps",
        "amihud",
        "intensity",
        "fourth",
        "first_adj",
        "sqrt_fourth",
        "n_trades",
    ]
    matrix = {}
    for p in predictors:
        matrix[p] = {}
        xp = np.asarray([f[p] for f in feats], dtype=np.float64)
        for t in targets:
            yt = np.asarray([f[t] for f in feats], dtype=np.float64)
            ci = _spearman_boot_ci(xp, yt, seed=hash(p + t) % 10_000)
            ci["shuffle_p"] = _shuffle_p(xp, yt, seed=hash("sh" + p + t) % 10_000)
            matrix[p][t] = ci

    # Regime splits: high vs low intensity / spread
    intens = np.asarray([f["intensity"] for f in feats], dtype=np.float64)
    spreads = np.asarray([f["spread_bps"] for f in feats], dtype=np.float64)
    noise = np.asarray([f["noise_std"] for f in feats], dtype=np.float64)
    regimes = {}
    for name, arr in (("intensity", intens), ("spread", spreads)):
        m = np.isfinite(arr) & np.isfinite(noise)
        if m.sum() < 20:
            regimes[name] = {"ok": False, "why": "n_low"}
            continue
        med = float(np.nanmedian(arr[m]))
        hi = m & (arr >= med)
        lo = m & (arr < med)
        regimes[name] = {
            "ok": True,
            "median_split": med,
            "high": _spearman_boot_ci(noise[hi], spreads[hi] if name != "spread" else intens[hi], seed=31),
            "low": _spearman_boot_ci(noise[lo], spreads[lo] if name != "spread" else intens[lo], seed=32),
            "note": "noise↔spread in high/low intensity; noise↔intensity in high/low spread",
        }

    # Interpretation sketch
    rho_ns = matrix["noise_std"]["spread_bps"]
    rho_na = matrix["noise_std"]["amihud"]
    rho_ni = matrix["noise_std"]["intensity"]
    rho_nv = matrix["noise_std"]["fourth"]
    interpretation = {
        "friction_vs_information": (
            "If Êε tracks spread/Amihud more than intensity/RV → friction/liquidity; "
            "if tracks intensity/RV with weak spread link → activity/information arrival."
        ),
        "observed": {
            "noise_vs_spread": rho_ns,
            "noise_vs_amihud": rho_na,
            "noise_vs_intensity": rho_ni,
            "noise_vs_sparse_rv": rho_nv,
        },
        "read": (
            "Pass 2.7 already Hold on noise↔spread (ρ≈0). Recompute here on full stack; "
            "do not Promote friction claim without CI_lo>0."
        ),
    }
    return {
        "n": len(feats),
        "matrix": matrix,
        "regimes": regimes,
        "interpretation": interpretation,
    }


def predictive_oos(rows: list[dict]) -> dict:
    """OOS time-split: features_t → targets_{t+1}; late-half IC with bootstrap CI."""
    idx = build_panel_index(rows)
    pairs = []
    for (venue, symbol, day), r in idx.items():
        nxt = idx.get((venue, symbol, _next_day(day)))
        if nxt is None:
            continue
        f = _feature_row(r)
        g = _feature_row(nxt)
        # daily |ret| proxy unavailable without OHLC — use |Δ log sqrt(RV)| and RV levels
        fourth_t = f["fourth"]
        fourth_n = g["fourth"]
        fa_t = f["first_adj"]
        fa_n = g["first_adj"]
        spread_t = f["spread_bps"]
        spread_n = g["spread_bps"]
        pairs.append(
            {
                "venue": venue,
                "symbol": symbol,
                "day": day,
                "next_day": nxt["day"],
                **{f"x_{k}": v for k, v in f.items()},
                "y_next_fourth": fourth_n,
                "y_next_first_adj": fa_n,
                "y_next_sqrt_fourth": g["sqrt_fourth"],
                "y_next_noise_std": g["noise_std"],
                "y_next_spread": spread_n,
                "y_next_amihud": g["amihud"],
                "y_next_intensity": g["intensity"],
                "y_spread_widen": (spread_n - spread_t) if np.isfinite(spread_n) and np.isfinite(spread_t) else float("nan"),
                "y_amihud_widen": (g["amihud"] - f["amihud"])
                if np.isfinite(g["amihud"]) and np.isfinite(f["amihud"])
                else float("nan"),
                "y_abs_dlog_rv": abs(math.log(fourth_n / fourth_t))
                if np.isfinite(fourth_n) and np.isfinite(fourth_t) and fourth_t > 0 and fourth_n > 0
                else float("nan"),
                # forecast errors for next_fourth using persistence of sparse vs TSRV
                "err_sparse_sq": (fourth_n - fourth_t) ** 2
                if np.isfinite(fourth_n) and np.isfinite(fourth_t)
                else float("nan"),
                "err_tsrv_sq": (fourth_n - fa_t) ** 2
                if np.isfinite(fourth_n) and np.isfinite(fa_t)
                else float("nan"),
                "err_sparse_fa_sq": (fa_n - fourth_t) ** 2
                if np.isfinite(fa_n) and np.isfinite(fourth_t)
                else float("nan"),
                "err_tsrv_fa_sq": (fa_n - fa_t) ** 2
                if np.isfinite(fa_n) and np.isfinite(fa_t)
                else float("nan"),
            }
        )

    if not pairs:
        return {"ok": False, "why": "no next-day pairs", "n_pairs": 0}

    days = sorted({p["day"] for p in pairs})
    split = days[len(days) // 2]
    early = [p for p in pairs if p["day"] < split]
    late = [p for p in pairs if p["day"] >= split]

    x_names = [
        "x_noise_std",
        "x_fifth_over_fourth",
        "x_fifth_over_fourth_mid",
        "x_sparse_minus_tsrv",
        "x_tsrv_over_sparse",
        "x_spread_bps",
        "x_amihud",
        "x_intensity",
        "x_fourth",
        "x_first_adj",
    ]
    y_names = [
        "y_next_fourth",
        "y_next_first_adj",
        "y_next_sqrt_fourth",
        "y_next_noise_std",
        "y_next_spread",
        "y_next_amihud",
        "y_spread_widen",
        "y_amihud_widen",
        "y_abs_dlog_rv",
    ]

    def _ic_block(block: list[dict], seed0: int) -> dict:
        out = {}
        for xn in x_names:
            out[xn] = {}
            x = np.asarray([p[xn] for p in block], dtype=np.float64)
            for yn in y_names:
                y = np.asarray([p[yn] for p in block], dtype=np.float64)
                ci = _spearman_boot_ci(x, y, seed=seed0 + hash(xn + yn) % 5000)
                ci["shuffle_p"] = _shuffle_p(x, y, seed=seed0 + 17 + hash(xn + yn) % 5000)
                out[xn][yn] = ci
        return out

    ic_all = _ic_block(pairs, 100)
    ic_early = _ic_block(early, 200)
    ic_late = _ic_block(late, 300)  # OOS

    # Simple early→late: rank predictor = x_noise_std (univariate); also multi-feature score
    def _zscore(a: NDArray[np.float64]) -> NDArray[np.float64]:
        m = np.isfinite(a)
        out = np.full_like(a, np.nan)
        if m.sum() < 3:
            return out
        mu, sd = float(np.nanmean(a[m])), float(np.nanstd(a[m]))
        if sd < 1e-18:
            return out
        out[m] = (a[m] - mu) / sd
        return out

    score_feats = ["x_noise_std", "x_fifth_over_fourth", "x_sparse_minus_tsrv", "x_intensity"]
    # fit signs on early (corr sign), apply to late
    signs = {}
    for xn in score_feats:
        xe = np.asarray([p[xn] for p in early], dtype=np.float64)
        ye = np.asarray([p["y_next_fourth"] for p in early], dtype=np.float64)
        r = spearman_r(xe, ye)
        signs[xn] = 1.0 if (np.isfinite(r) and r >= 0) else -1.0
    late_score = np.zeros(len(late), dtype=np.float64)
    for xn in score_feats:
        xl = np.asarray([p[xn] for p in late], dtype=np.float64)
        late_score += signs[xn] * _zscore(xl)
    model_ics = {}
    for yn in ("y_next_fourth", "y_next_spread", "y_spread_widen", "y_abs_dlog_rv", "y_next_amihud"):
        yl = np.asarray([p[yn] for p in late], dtype=np.float64)
        model_ics[yn] = _spearman_boot_ci(late_score, yl, seed=404)
        model_ics[yn]["signs"] = signs

    # Diebold-Mariano: d_t = err_sparse_sq - err_tsrv_sq on late; H0 mean(d)=0
    def _dm(block: list[dict], e1: str, e2: str) -> dict:
        d = np.asarray([p[e1] - p[e2] for p in block], dtype=np.float64)
        d = d[np.isfinite(d)]
        if d.size < 8:
            return {"n": float(d.size), "mean_d": float("nan"), "t": float("nan"), "prefer": "insuff"}
        mu = float(np.mean(d))
        se = float(np.std(d, ddof=1) / math.sqrt(d.size))
        t = mu / se if se > 0 else float("nan")
        # positive mean_d ⇒ sparse worse ⇒ prefer TSRV
        prefer = "tsrv" if (np.isfinite(t) and t > 1.96) else ("sparse" if (np.isfinite(t) and t < -1.96) else "tie")
        # bootstrap CI on mean_d
        rng = np.random.default_rng(55)
        boots = [float(np.mean(d[rng.integers(0, d.size, size=d.size)])) for _ in range(600)]
        ba = np.asarray(boots)
        return {
            "n": float(d.size),
            "mean_d": mu,
            "t": float(t),
            "ci95": [float(np.quantile(ba, 0.025)), float(np.quantile(ba, 0.975))],
            "prefer": prefer,
            "note": f"d={e1}-{e2}; >0 ⇒ {e1} worse",
        }

    dm = {
        "next_fourth_persistence": {
            "all": _dm(pairs, "err_sparse_sq", "err_tsrv_sq"),
            "early": _dm(early, "err_sparse_sq", "err_tsrv_sq"),
            "late_oos": _dm(late, "err_sparse_sq", "err_tsrv_sq"),
        },
        "next_first_adj_persistence": {
            "all": _dm(pairs, "err_sparse_fa_sq", "err_tsrv_fa_sq"),
            "late_oos": _dm(late, "err_sparse_fa_sq", "err_tsrv_fa_sq"),
        },
    }

    # Decision board for predictive candidates
    decisions = {}
    # Focus claims user asked for
    focus = [
        ("pred.noise_to_next_rv", "x_noise_std", "y_next_fourth"),
        ("pred.noise_to_next_spread", "x_noise_std", "y_next_spread"),
        ("pred.noise_to_spread_widen", "x_noise_std", "y_spread_widen"),
        ("pred.fifth_fourth_to_next_rv", "x_fifth_over_fourth", "y_next_fourth"),
        ("pred.tsrv_gap_to_next_rv", "x_sparse_minus_tsrv", "y_next_fourth"),
        ("pred.intensity_to_next_noise", "x_intensity", "y_next_noise_std"),
        ("pred.amihud_to_next_amihud", "x_amihud", "y_next_amihud"),
        ("pred.model_score_next_rv", None, "y_next_fourth"),
    ]
    for cid, xn, yn in focus:
        if xn is None:
            ci_late = model_ics.get(yn, {})
            # model score only defined on late; treat early as n/a → Hold max
            ci_early = {"n": 0, "rho": float("nan"), "lo": float("nan"), "hi": float("nan")}
        else:
            ci_late = ic_late.get(xn, {}).get(yn, {})
            ci_early = ic_early.get(xn, {}).get(yn, {})
        n = float(ci_late.get("n", 0) or 0)
        lo, hi = ci_late.get("lo", float("nan")), ci_late.get("hi", float("nan"))
        rho = ci_late.get("rho", float("nan"))
        elo, ehi = ci_early.get("lo", float("nan")), ci_early.get("hi", float("nan"))
        erho = ci_early.get("rho", float("nan"))

        def _same_sign(r1, r2) -> bool:
            return bool(np.isfinite(r1) and np.isfinite(r2) and ((r1 > 0 and r2 > 0) or (r1 < 0 and r2 < 0)))

        def _clears(lo_, hi_) -> bool:
            return bool(np.isfinite(lo_) and np.isfinite(hi_) and (lo_ > GATE_IC_LO or hi_ < -GATE_IC_LO))

        if n >= GATE_N_MIN and np.isfinite(lo) and np.isfinite(hi):
            if (
                _clears(lo, hi)
                and _same_sign(rho, erho)
                and (np.isfinite(elo) and np.isfinite(ehi))
                and ((elo > 0 and ehi > 0) or (elo < 0 and ehi < 0) or _clears(elo, ehi))
            ):
                # Promote only if late clears |CI| gate AND early same-sign with CI not through 0
                dec = "Promote"
                why = (
                    f"OOS late IC={rho:.3f} CI=[{lo:.3f},{hi:.3f}] n={int(n)} clears |CI|>{GATE_IC_LO}; "
                    f"early IC={erho:.3f} CI=[{elo:.3f},{ehi:.3f}] same_sign"
                )
            elif (lo > 0 and hi > 0) or (lo < 0 and hi < 0):
                dec = "Hold"
                why = (
                    f"OOS late same-sign but gate incomplete: late ρ={rho:.3f} CI=[{lo:.3f},{hi:.3f}]; "
                    f"early ρ={erho:.3f} CI=[{elo:.3f},{ehi:.3f}] n={int(n)}"
                )
            else:
                dec = "Kill"
                why = f"OOS late IC CI through 0: ρ={rho:.3f} CI=[{lo:.3f},{hi:.3f}] n={int(n)}"
        else:
            dec = "Hold" if n >= 10 else "Kill"
            why = f"insuff or weak OOS n={int(n)} ρ={rho} CI=[{lo},{hi}]"
        # Amihud persistence is liquidity autocorrelation — demote Promote→Hold (not noise thesis)
        if cid == "pred.amihud_to_next_amihud" and dec == "Promote":
            dec = "Hold"
            why = "Amihud persistence clears IC gate but is liquidity autocorrelation, not Êε predictive claim — Hold"
        decisions[cid] = {
            "decision": dec,
            "why": why,
            "oos_ic": ci_late,
            "early_ic": ci_early,
        }

    # Encompassing: noise→next_fourth vs sparse fourth persistence (rank residual)
    def _partial_ic(block: list[dict]) -> dict:
        n = np.asarray([p["x_noise_std"] for p in block], dtype=np.float64)
        f = np.asarray([p["x_fourth"] for p in block], dtype=np.float64)
        y = np.asarray([p["y_next_fourth"] for p in block], dtype=np.float64)
        m = np.isfinite(n) & np.isfinite(f) & np.isfinite(y)
        n, f, y = n[m], f[m], y[m]
        if n.size < 10:
            return {"n": float(n.size), "noise_partial": float("nan"), "fourth_partial": float("nan")}
        rn = n.argsort().argsort().astype(np.float64)
        rf = f.argsort().argsort().astype(np.float64)
        ry = y.argsort().argsort().astype(np.float64)
        Xn = np.c_[np.ones(rf.size), rf]
        coef_n = np.linalg.lstsq(Xn, rn, rcond=None)[0]
        resid_n = rn - Xn @ coef_n
        Xf = np.c_[np.ones(rn.size), rn]
        coef_f = np.linalg.lstsq(Xf, rf, rcond=None)[0]
        resid_f = rf - Xf @ coef_f
        return {
            "n": float(n.size),
            "noise_partial_ic": float(spearman_r(resid_n, ry)),
            "fourth_partial_ic": float(spearman_r(resid_f, ry)),
            "noise_raw_ic": float(spearman_r(n, y)),
            "fourth_raw_ic": float(spearman_r(f, y)),
        }

    enc = {"early": _partial_ic(early), "late_oos": _partial_ic(late)}
    # If noise has no incremental IC over fourth, demote Promote on pred.noise_to_next_rv
    if "pred.noise_to_next_rv" in decisions and decisions["pred.noise_to_next_rv"]["decision"] == "Promote":
        late_p = enc["late_oos"].get("noise_partial_ic", float("nan"))
        if not (np.isfinite(late_p) and abs(late_p) > GATE_IC_LO):
            decisions["pred.noise_to_next_rv"] = {
                "decision": "Hold",
                "why": (
                    f"Raw OOS IC clears gate but encompassing fails: noise⊥fourth partial IC={late_p:.3f}; "
                    f"fourth raw IC={enc['late_oos'].get('fourth_raw_ic'):.3f} dominates — vol clustering, not Êε alpha"
                ),
                "oos_ic": decisions["pred.noise_to_next_rv"]["oos_ic"],
                "early_ic": decisions["pred.noise_to_next_rv"]["early_ic"],
                "encompassing": enc,
            }

    # DM candidate
    dm_late = dm["next_fourth_persistence"]["late_oos"]
    if dm_late.get("prefer") == "tsrv" and dm_late.get("n", 0) >= GATE_N_MIN:
        # still Hold unless also early clears (pre-registered style)
        dm_early = dm["next_fourth_persistence"]["early"]
        if dm_early.get("prefer") == "tsrv":
            decisions["pred.tsrv_beats_sparse_rv_forecast"] = {
                "decision": "Hold",  # not Promote: forecast is level persistence, not pre-registered RV gate
                "why": f"DM late prefer tsrv t={dm_late.get('t'):.2f} but claim is diagnostic not tradable",
                "dm_late": dm_late,
                "dm_early": dm_early,
            }
        else:
            decisions["pred.tsrv_beats_sparse_rv_forecast"] = {
                "decision": "Hold",
                "why": f"DM late={dm_late.get('prefer')} early={dm_early.get('prefer')} — unstable",
                "dm_late": dm_late,
            }
    else:
        decisions["pred.tsrv_beats_sparse_rv_forecast"] = {
            "decision": "Kill" if dm_late.get("prefer") in ("sparse", "tie") and dm_late.get("n", 0) >= GATE_N_MIN else "Hold",
            "why": f"DM late prefer={dm_late.get('prefer')} t={dm_late.get('t')} n={dm_late.get('n')}",
            "dm_late": dm_late,
        }

    return {
        "ok": True,
        "n_pairs": len(pairs),
        "n_early": len(early),
        "n_late": len(late),
        "split_day": split,
        "days": days,
        "ic_all": ic_all,
        "ic_early": ic_early,
        "ic_late_oos": ic_late,
        "model_score_oos": model_ics,
        "diebold_mariano": dm,
        "encompassing_noise_vs_sparse": enc,
        "decisions": decisions,
        "crash_v_note": "crash/V flags not in expand_panel; skipped (no cross_miniflash SSM join on this pass)",
        "horizons": {"next_day": 1, "units": "UTC venue-day"},
    }


def taxonomy(rows: list[dict]) -> dict:
    ok = [r for r in rows if r.get("ok")]
    by_vs: dict[str, list] = defaultdict(list)
    for r in ok:
        by_vs[f"{r['venue']}|{r['symbol']}"].append(r)

    cells = {}
    for key, grp in sorted(by_vs.items()):
        noise = np.asarray([_feature_row(r)["noise_std"] for r in grp], dtype=np.float64)
        mid = np.asarray([_feature_row(r)["fifth_over_fourth_mid"] for r in grp], dtype=np.float64)
        ff = np.asarray([_feature_row(r)["fifth_over_fourth"] for r in grp], dtype=np.float64)
        sm = np.asarray([_feature_row(r)["sparse_minus_tsrv"] for r in grp], dtype=np.float64)
        cells[key] = {
            "n": len(grp),
            "noise_std_med": float(np.nanmedian(noise)),
            "fifth_fourth_cal_med": float(np.nanmedian(ff)),
            "fifth_fourth_mid_med": float(np.nanmedian(mid[np.isfinite(mid)])) if np.isfinite(mid).any() else float("nan"),
            "n_mid": int(np.isfinite(mid).sum()),
            "sparse_minus_tsrv_med": float(np.nanmedian(sm)),
        }

    # venue mid heterogeneity (already known — restate with symbols)
    venue_mid = {}
    for v in ("hyperliquid", "deribit", "kraken"):
        mids = [
            _feature_row(r)["fifth_over_fourth_mid"]
            for r in ok
            if r["venue"] == v and np.isfinite(_feature_row(r)["fifth_over_fourth_mid"])
        ]
        venue_mid[v] = {
            "n": len(mids),
            "median": float(np.median(mids)) if mids else float("nan"),
            "p25": float(np.percentile(mids, 25)) if mids else float("nan"),
            "p75": float(np.percentile(mids, 75)) if mids else float("nan"),
        }
    return {"cells": cells, "venue_mid": venue_mid, "n_ok": len(ok)}


def tape_depth_subset(rows: list[dict], *, max_files: int, max_days: int) -> dict:
    """Signature / optimal K / noise ACF / light TOD on stratified tape subset."""
    from _data import load_day_trades  # local import after path setup

    ok = [r for r in rows if r.get("ok")]
    # stratify: up to 2 days per venue×symbol, prefer mid days + spread extremes
    buckets: dict[tuple[str, str], list] = defaultdict(list)
    for r in ok:
        buckets[(r["venue"], r["symbol"])].append(r)
    chosen = []
    for key, grp in sorted(buckets.items()):
        grp = sorted(grp, key=lambda r: r["day"])
        # pick early + late
        picks = [grp[0], grp[-1]] if len(grp) >= 2 else grp[:1]
        # add a mid-clock day if any
        mid_days = [r for r in grp if np.isfinite(r.get("fifth_over_fourth_mid", np.nan))]
        if mid_days:
            picks.append(mid_days[len(mid_days) // 2])
        # unique by day
        seen = set()
        for p in picks:
            if p["day"] not in seen:
                chosen.append(p)
                seen.add(p["day"])
        if len(chosen) >= max_days:
            break
    chosen = chosen[:max_days]

    sig_curves = []
    acfs = []
    optks = []
    tod = []  # hour → mean |ret| and noise proxy from 1s grid chunks

    t0 = time.time()
    for r in chosen:
        try:
            rec = load_day_trades(r["venue"], r["symbol"], r["day"], max_files=max_files, quiet=True)
            tape = rec["tape"]
            g = grid_log_price_from_tape(tape["ts"], tape["px"], dt_s=1.0)
            lp = g["log_px"]
            if lp.size < 600:
                continue
            sig = signature_rv_curve(lp)
            acf = noise_return_acf(lp, max_lag=15)
            ok_scan = optimal_K_scan(lp, step=300)
            sig_curves.append(
                {
                    "venue": r["venue"],
                    "symbol": r["symbol"],
                    "day": r["day"],
                    **{k: sig[k] for k in ("fine_log_slope", "rv_1s", "rv_300s", "steps", "rv")},
                }
            )
            acfs.append(
                {
                    "venue": r["venue"],
                    "symbol": r["symbol"],
                    "day": r["day"],
                    "lag1": acf["lag1"],
                    "ma1_compatible": acf["ma1_compatible"],
                    "acf": acf["acf"],
                }
            )
            optks.append(
                {
                    "venue": r["venue"],
                    "symbol": r["symbol"],
                    "day": r["day"],
                    "best_K_stability": ok_scan["best_K_stability"],
                    "grid": ok_scan["grid"],
                }
            )
            # TOD: split 1s grid into UTC hours
            n = lp.size
            # approximate hour index from position in day (grid starts at first trade)
            # Better: use tape ts
            ts = np.asarray(tape["ts"], dtype=np.int64)
            px = np.asarray(tape["px"], dtype=np.float64)
            hours = ((ts // 1_000_000_000) % 86400) // 3600
            for h in range(24):
                m = hours == h
                if m.sum() < 30:
                    continue
                # subsample
                idx = np.where(m)[0]
                if idx.size > 5000:
                    idx = idx[:: idx.size // 5000]
                sub_ts = ts[idx]
                sub_px = px[idx]
                gg = grid_log_price_from_tape(sub_ts, sub_px, dt_s=1.0)
                if gg["log_px"].size < 60:
                    continue
                ac = noise_return_acf(gg["log_px"], max_lag=3)
                tod.append(
                    {
                        "venue": r["venue"],
                        "symbol": r["symbol"],
                        "day": r["day"],
                        "hour_utc": h,
                        "n_trades": int(m.sum()),
                        "acf_lag1": ac["lag1"],
                        "noise_std": float(
                            np.std(np.diff(gg["log_px"])) / math.sqrt(2.0)
                        ),  # rough
                    }
                )
        except Exception as exc:  # noqa: BLE001
            sig_curves.append(
                {"venue": r["venue"], "symbol": r["symbol"], "day": r["day"], "error": f"{type(exc).__name__}: {exc}"}
            )

    lag1s = np.asarray([a["lag1"] for a in acfs if np.isfinite(a.get("lag1", np.nan))], dtype=np.float64)
    slopes = np.asarray(
        [s["fine_log_slope"] for s in sig_curves if np.isfinite(s.get("fine_log_slope", np.nan))], dtype=np.float64
    )
    best_ks = np.asarray(
        [o["best_K_stability"] for o in optks if np.isfinite(o.get("best_K_stability", np.nan))], dtype=np.float64
    )

    # TOD aggregate
    tod_agg = {}
    by_h: dict[int, list] = defaultdict(list)
    for row in tod:
        by_h[int(row["hour_utc"])].append(row["acf_lag1"])
    for h, vals in sorted(by_h.items()):
        a = np.asarray(vals, dtype=np.float64)
        a = a[np.isfinite(a)]
        tod_agg[str(h)] = {"n": int(a.size), "median_acf_lag1": float(np.median(a)) if a.size else float("nan")}

    return {
        "n_requested": len(chosen),
        "n_signature": len([s for s in sig_curves if "error" not in s]),
        "elapsed_s": time.time() - t0,
        "signature": {
            "rows": sig_curves,
            "median_fine_log_slope": float(np.median(slopes)) if slopes.size else float("nan"),
            "frac_negative_slope": float(np.mean(slopes < 0)) if slopes.size else float("nan"),
            "note": "Negative fine-end log(RV)/log(step) slope ⇒ noise-dominated high-freq RV (thesis signature)",
        },
        "noise_acf": {
            "rows": acfs,
            "median_lag1": float(np.median(lag1s)) if lag1s.size else float("nan"),
            "frac_ma1_compatible": float(np.mean(lag1s < -0.05)) if lag1s.size else float("nan"),
            "note": "ZMA05 i.i.d. noise ⇒ negative lag-1 return ACF (MA(1)-like)",
        },
        "optimal_K": {
            "rows": optks,
            "median_best_K": float(np.median(best_ks)) if best_ks.size else float("nan"),
            "book_default_K": 300,
            "note": "Stability proxy vs median first_adj — not true IV oracle",
        },
        "tod_acf_lag1": tod_agg,
    }


def uses_memo(info: dict, pred: dict, tape: dict, tax: dict) -> dict:
    """Structured uses / trading applications takeaways (no fake PnL)."""
    dm = (pred.get("diebold_mariano") or {}).get("next_fourth_persistence", {}).get("late_oos", {})
    mid = tax.get("venue_mid", {})
    return {
        "when_prefer_tsrv_vs_sparse": {
            "risk_RV": "Always prefer TSRV/first_adj over sparse-only for risk RV — MC Kill stands regardless of tape OOS Hold.",
            "tape_advantage": (
                f"DM late OOS prefer={dm.get('prefer')} t={dm.get('t')} — "
                "do not size a tradable TSRV edge; use as bias-reduced RV input."
            ),
            "confidence": "high for MC policy; med for tape DM",
        },
        "when_mid_clock_noise_matters": {
            "quoting": (
                "Mid-clock fifth/fourth elevated (esp. Deribit) ⇒ bounce on mid path; "
                "widen / distrust mid-mark RV; calendar/trade clocks do NOT show bounce domination (Kill)."
            ),
            "venue_heterogeneity": mid,
            "confidence": "med monitor — Hold on Promote gate",
        },
        "clock_trust": {
            "calendar": "Kill as bounce-domination claim; still default sampling clock for TSRV.",
            "trade": "Kill — fifth/fourth < 1.",
            "tick_bounce": "Kill — CI fails gate.",
            "mid": "Hold — point estimate high, CI_lo < 1.5; Deribit≫HL.",
            "ops": "Publish clock alongside RV; never treat trade-clock bounce as Promote.",
        },
        "monitors": [
            {
                "id": "mon.noise_std_level",
                "spec": "rolling venue-day noise_std vs 14d median; flag z>2",
                "action": "research/risk strip — not auto-widen until liq.noise_vs_spread Promotes",
                "conf": "low",
            },
            {
                "id": "mon.mid_fifth_fourth",
                "spec": "when quoted TOB: mid fifth/fourth; alert if >3 and venue=deribit",
                "action": "MM: treat mid-mark vol as noisy; prefer TSRV on mid grid",
                "conf": "med",
            },
            {
                "id": "mon.tsrv_sparse_gap",
                "spec": "sparse−first_adj; alert if gap widens vs own 14d",
                "action": "risk: prefer first_adj for σ budgets when gap large",
                "conf": "med",
            },
            {
                "id": "mon.signature_slope",
                "spec": f"fine log-slope med={tape.get('signature',{}).get('median_fine_log_slope')}",
                "action": "diagnostic that 1s RV is noise-dominated — Kill sparse-only (already)",
                "conf": "high",
            },
            {
                "id": "mon.acf_lag1",
                "spec": f"return ACF lag1 med={tape.get('noise_acf',{}).get('median_lag1')}",
                "action": "MA(1) noise check; if lag1≳0 revisit i.i.d. noise assumption",
                "conf": "med",
            },
        ],
        "predictive_honesty": {
            "summary": "See pred.decisions — Kill weak ICs; Hold suggestive same-sign; 0 forced Promote",
            "n_pairs": pred.get("n_pairs"),
            "split_day": pred.get("split_day"),
        },
        "info_read": info.get("interpretation"),
    }


def write_figures(info: dict, pred: dict, tape: dict, tax: dict) -> list[str]:
    FIGS.mkdir(parents=True, exist_ok=True)
    paths = []

    # 1) information heatmap (noise_std row)
    mat = info.get("matrix", {})
    preds = list(mat.keys())
    tgts = list(next(iter(mat.values())).keys()) if mat else []
    if preds and tgts:
        Z = np.full((len(preds), len(tgts)), np.nan)
        for i, p in enumerate(preds):
            for j, t in enumerate(tgts):
                Z[i, j] = mat[p][t].get("rho", np.nan)
        fig, ax = plt.subplots(figsize=(9.0, 4.8))
        im = ax.imshow(Z, cmap="RdBu_r", vmin=-0.6, vmax=0.6, aspect="auto")
        ax.set_xticks(range(len(tgts)))
        ax.set_xticklabels(tgts, rotation=40, ha="right", fontsize=8)
        ax.set_yticks(range(len(preds)))
        ax.set_yticklabels(preds, fontsize=8)
        ax.set_title("Information content — Spearman ρ (contemporaneous)")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        p = FIGS / "fig_info_heatmap.png"
        fig.tight_layout()
        fig.savefig(p, dpi=140, bbox_inches="tight")
        plt.close(fig)
        paths.append(str(p))

    # 2) OOS IC forest for noise_std → targets
    late = pred.get("ic_late_oos", {}).get("x_noise_std", {})
    if late:
        labels = list(late.keys())
        rhos = [late[k]["rho"] for k in labels]
        los = [late[k]["lo"] for k in labels]
        his = [late[k]["hi"] for k in labels]
        y = np.arange(len(labels))
        fig, ax = plt.subplots(figsize=(8.0, 4.6))
        rh = np.asarray(rhos, dtype=float)
        lo_a = np.asarray(los, dtype=float)
        hi_a = np.asarray(his, dtype=float)
        xerr_lo = np.clip(rh - lo_a, 0, None)
        xerr_hi = np.clip(hi_a - rh, 0, None)
        # drop non-finite
        m = np.isfinite(rh) & np.isfinite(xerr_lo) & np.isfinite(xerr_hi)
        ax.errorbar(
            rh[m],
            y[m],
            xerr=[xerr_lo[m], xerr_hi[m]],
            fmt="o",
            color="#2c3e50",
            ecolor="#7f8c8d",
            capsize=3,
        )
        ax.axvline(0, color="#b33a3a", ls="--", lw=1)
        ax.axvline(GATE_IC_LO, color="#2f7d4a", ls=":", lw=1, label=f"Promote |CI_lo|>{GATE_IC_LO}")
        ax.axvline(-GATE_IC_LO, color="#2f7d4a", ls=":", lw=1)
        ax.set_yticks(y)
        ax.set_yticklabels([l.replace("y_", "") for l in labels], fontsize=8)
        ax.set_xlabel("OOS late Spearman IC")
        ax.set_title(f"Predictive: noise_std_t → y_{{t+1}} (split={pred.get('split_day')})")
        ax.legend(fontsize=8)
        p = FIGS / "fig_pred_ic_noise.png"
        fig.tight_layout()
        fig.savefig(p, dpi=140, bbox_inches="tight")
        plt.close(fig)
        paths.append(str(p))

    # 3) signature plot overlay
    sig_rows = [s for s in tape.get("signature", {}).get("rows", []) if "rv" in s and s.get("steps")]
    if sig_rows:
        fig, ax = plt.subplots(figsize=(7.2, 4.2))
        for s in sig_rows[:12]:
            ax.plot(s["steps"], s["rv"], alpha=0.55, lw=1.2, label=f"{s['venue'][:2]}-{s['symbol']}-{s['day'][5:]}")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("sampling step (s)")
        ax.set_ylabel("sparse RV")
        ax.set_title(
            f"Signature plots (subset n={len(sig_rows)}) — med slope={tape['signature'].get('median_fine_log_slope'):.2f}"
        )
        ax.legend(fontsize=6, ncol=2, loc="upper right")
        p = FIGS / "fig_signature.png"
        fig.tight_layout()
        fig.savefig(p, dpi=140, bbox_inches="tight")
        plt.close(fig)
        paths.append(str(p))

    # 4) ACF lag1 hist
    acf_rows = [a for a in tape.get("noise_acf", {}).get("rows", []) if np.isfinite(a.get("lag1", np.nan))]
    if acf_rows:
        fig, ax = plt.subplots(figsize=(6.0, 3.8))
        ax.hist([a["lag1"] for a in acf_rows], bins=12, color="#4a7ab5", edgecolor="white")
        ax.axvline(-0.05, color="#b33a3a", ls="--", label="MA(1) threshold")
        ax.axvline(tape["noise_acf"]["median_lag1"], color="#2f7d4a", ls="-", label="median")
        ax.set_xlabel("return ACF lag-1")
        ax.set_title("Noise ACF lag-1 (tape subset)")
        ax.legend(fontsize=8)
        p = FIGS / "fig_noise_acf_lag1.png"
        fig.tight_layout()
        fig.savefig(p, dpi=140, bbox_inches="tight")
        plt.close(fig)
        paths.append(str(p))

    # 5) venue mid taxonomy
    vm = tax.get("venue_mid", {})
    if vm:
        venues = list(vm.keys())
        meds = [vm[v]["median"] for v in venues]
        fig, ax = plt.subplots(figsize=(6.2, 3.6))
        ax.bar(venues, meds, color=["#4a7ab5", "#8e5aa8", "#5a9e6f"])
        ax.axhline(1.5, color="#b33a3a", ls="--")
        ax.set_ylabel("median mid fifth/fourth")
        ax.set_title("Venue mid-clock heterogeneity")
        p = FIGS / "fig_venue_mid_taxonomy.png"
        fig.tight_layout()
        fig.savefig(p, dpi=140, bbox_inches="tight")
        plt.close(fig)
        paths.append(str(p))

    # 6) decision strip for predictive
    decs = pred.get("decisions", {})
    if decs:
        items = [(k, v["decision"]) for k, v in decs.items()]
        colors = {"Kill": "#b33a3a", "Hold": "#c4a035", "Promote": "#2f7d4a"}
        fig, ax = plt.subplots(figsize=(9.5, max(3.5, 0.38 * len(items))))
        y = np.arange(len(items))[::-1]
        for i, (cid, dec) in enumerate(items):
            ax.barh(y[i], 1.0, color=colors.get(dec, "#888"), height=0.7)
            ax.text(0.02, y[i], f"{dec:7s}  {cid}", va="center", color="white", fontsize=9, fontweight="bold")
        ax.set_xlim(0, 1)
        ax.set_yticks([])
        ax.set_xticks([])
        ax.set_title("Predictive board — Pass 2.8 (no forced Promote)")
        for sp in ax.spines.values():
            sp.set_visible(False)
        p = FIGS / "fig_pred_board.png"
        fig.tight_layout()
        fig.savefig(p, dpi=140, bbox_inches="tight")
        plt.close(fig)
        paths.append(str(p))

    # 7) TOD profile
    tod = tape.get("tod_acf_lag1", {})
    if tod:
        hs = sorted(int(h) for h in tod.keys())
        meds = [tod[str(h)]["median_acf_lag1"] for h in hs]
        fig, ax = plt.subplots(figsize=(7.5, 3.6))
        ax.plot(hs, meds, "o-", color="#2c3e50")
        ax.axhline(-0.05, color="#b33a3a", ls="--")
        ax.set_xlabel("UTC hour")
        ax.set_ylabel("median ACF lag-1")
        ax.set_title("TOD noise ACF profile (tape subset)")
        p = FIGS / "fig_tod_acf.png"
        fig.tight_layout()
        fig.savefig(p, dpi=140, bbox_inches="tight")
        plt.close(fig)
        paths.append(str(p))

    return paths


def write_report(blob: dict) -> str:
    pred = blob["predictive"]
    info = blob["information"]
    tape = blob["tape_depth"]
    uses = blob["uses"]
    decs = pred.get("decisions", {})
    lines = [
        "# Depth / information / predictive — Pass 2.8",
        "",
        f"- expand n_ok features from Pass 2.7; next-day pairs n={pred.get('n_pairs')} split={pred.get('split_day')}",
        f"- tape subset signature n={tape.get('n_signature')} elapsed={tape.get('elapsed_s'):.1f}s",
        "",
        "## Thesis empirics",
        f"- signature fine-end log-slope median = {tape.get('signature', {}).get('median_fine_log_slope')}",
        f"- frac negative slope = {tape.get('signature', {}).get('frac_negative_slope')}",
        f"- ACF lag1 median = {tape.get('noise_acf', {}).get('median_lag1')} · MA(1) frac = {tape.get('noise_acf', {}).get('frac_ma1_compatible')}",
        f"- optimal K (stability) median = {tape.get('optimal_K', {}).get('median_best_K')} (book default 300)",
        "",
        "## Information content (noise_std row)",
    ]
    ns = info.get("matrix", {}).get("noise_std", {})
    for t, ci in ns.items():
        lines.append(f"- vs {t}: ρ={ci.get('rho'):.4f} CI=[{ci.get('lo'):.3f},{ci.get('hi'):.3f}] shuffle_p={ci.get('shuffle_p')}")
    lines += ["", "## Predictive decisions"]
    for cid, d in decs.items():
        lines.append(f"- `{cid}` **{d['decision']}** — {d['why']}")
    lines += [
        "",
        "## Uses (summary)",
        f"- TSRV vs sparse: {uses['when_prefer_tsrv_vs_sparse']['risk_RV']}",
        f"- Mid-clock: {uses['when_mid_clock_noise_matters']['quoting'][:120]}…",
        "",
        "## Open",
        "- crash/V join not wired",
        "- listing ceiling 34d",
        "- Deribit≫HL mid heterogeneity unexplained",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-files", type=int, default=3)
    ap.add_argument("--max-tape-days", type=int, default=24)
    ap.add_argument("--skip-tape", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    expand = json.loads(EXPAND.read_text())
    rows = expand["rows"]

    print("information content…", flush=True)
    info = information_content(rows)
    print("predictive OOS…", flush=True)
    pred = predictive_oos(rows)
    print("taxonomy…", flush=True)
    tax = taxonomy(rows)
    if args.skip_tape:
        tape = {"n_requested": 0, "n_signature": 0, "signature": {}, "noise_acf": {}, "optimal_K": {}, "tod_acf_lag1": {}}
        prev = OUT / "depth_predict.json"
        if prev.is_file():
            try:
                old = json.loads(prev.read_text())
                if old.get("tape_depth", {}).get("n_signature", 0):
                    tape = old["tape_depth"]
                    print(f"reusing prior tape_depth n_signature={tape.get('n_signature')}", flush=True)
            except Exception:  # noqa: BLE001
                pass
    else:
        print(f"tape depth subset (max_days={args.max_tape_days})…", flush=True)
        tape = tape_depth_subset(rows, max_files=args.max_files, max_days=args.max_tape_days)
    uses = uses_memo(info, pred, tape, tax)
    blob = {
        "meta": {
            "pass": "2.8_depth_predict",
            "expand_source": str(EXPAND),
            "n_ok_expand": sum(1 for r in rows if r.get("ok")),
            "gates": {"GATE_IC_LO": GATE_IC_LO, "GATE_N_MIN": GATE_N_MIN},
            "created": datetime.now(timezone.utc).isoformat(),
        },
        "information": info,
        "predictive": pred,
        "taxonomy": tax,
        "tape_depth": tape,
        "uses": uses,
        "figures": [],
        "decisions_rollup": pred.get("decisions", {}),
    }
    _json_dump(OUT / "depth_predict.json", blob)
    (OUT / "depth_predict_REPORT.md").write_text(write_report(blob))
    ideas = {
        "generated": blob["meta"]["created"],
        "ideas": [
            {
                "id": m["id"],
                "kind": "monitor",
                "spec": m["spec"],
                "action": m["action"],
                "conf": m["conf"],
                "pnl_claim": False,
            }
            for m in uses["monitors"]
        ],
        "predictive_decisions": pred.get("decisions", {}),
    }
    _json_dump(OUT / "trade_ideas.json", ideas)
    figs = write_figures(info, pred, tape, tax)
    blob["figures"] = figs
    _json_dump(OUT / "depth_predict.json", blob)
    print(
        json.dumps(
            {
                "out": str(OUT),
                "n_pairs": pred.get("n_pairs"),
                "figs": len(figs),
                "decs": {k: v["decision"] for k, v in pred.get("decisions", {}).items()},
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
