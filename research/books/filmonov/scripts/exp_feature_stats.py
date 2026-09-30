#!/usr/bin/env python3
"""Feature statistical analysis for Filimonov Hold objects.

Univariate · dependence · predictive markout/IRF · BH multiple-testing.
Sample: ETH+BTC · HL+Deribit+Kraken · day-completeness flags.
Kraken trade_synth excluded from native TOB tests.

Writes ``out/feature_stats/`` JSON + figs.
ClickHouse MCP banned. No git commit.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(Path("/home/dev/lab/lab-n2070/warehouse/src")))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path("/home/dev/srv/ares-startarb") / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import (  # noqa: E402
    CORE_VENUES,
    ensure_env,
    load_day_trades,
    load_tob_any,
    normalize_side,
)
from _stats_bayes import (  # noqa: E402
    bh_fdr,
    day_block_bootstrap_ci,
    lead_lag_crosscorr,
    mutual_info_binned,
    partial_corr,
    pearson_spearman,
    tod_seasonality,
    two_sided_p_from_ci,
    univariate_moments,
)
from research.lib.hftpat import (  # noqa: E402
    clock_cluster_excess,
    clock_cluster_scores,
    event_window_markout,
    ignition_bar_timestamps,
    ignition_events,
    lead_lag_cascade,
    price_fade_events,
    quote_storm_detect,
    quote_storm_intensity,
    spread_irf_after_events,
)

OUT = BOOK / "out" / "feature_stats"
FIGS = OUT / "figs"
DAYS_DEFAULT = ["2026-09-25", "2026-09-26", "2026-09-27", "2026-09-30"]
HORIZONS_MS = (250.0, 500.0, 1000.0, 2000.0, 5000.0)
N_BOOT = 400
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


def _early_late(days: list[str]) -> tuple[list[str], list[str]]:
    d = sorted(days)
    mid = max(1, len(d) // 2)
    return d[:mid], d[mid:]


def load_day_features(
    venue: str,
    symbol: str,
    day: str,
    *,
    max_files: int,
    max_trades: int,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "venue": venue,
        "symbol": symbol,
        "day": day,
        "complete": False,
        "native_tob": False,
        "is_trade_synth": False,
    }
    try:
        rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
        tape = rec["tape"]
        comp = rec.get("completeness") or {}
        row["complete"] = bool(comp.get("complete"))
        row["coverage"] = comp.get("coverage")
        row["n_trades"] = int(tape.get("n", 0))
        ts = np.asarray(tape["ts"], dtype=np.int64)
        side = normalize_side(tape["side"])
        qty = np.asarray(tape["qty"], dtype=np.float64)
        px = np.asarray(tape["px"], dtype=np.float64)
    except Exception as exc:  # noqa: BLE001
        row["trade_error"] = f"{type(exc).__name__}: {exc}"
        return row

    # clock always on trades
    try:
        clk = clock_cluster_scores(ts)
        exc = clock_cluster_excess(clk, z_thresh=3.0)
        z = np.asarray(exc.get("z", []), dtype=np.float64)
        row["clock_max_z"] = float(np.nanmax(z)) if z.size else float("nan")
        row["clock_n_excess"] = int(exc.get("n_excess", 0))
    except Exception:
        row["clock_max_z"] = float("nan")
        row["clock_n_excess"] = 0

    try:
        tob = load_tob_any(venue, symbol, day)
    except Exception as exc:  # noqa: BLE001
        row["tob_error"] = f"{type(exc).__name__}: {exc}"
        return row
    synth = _is_synth(tob)
    row["is_trade_synth"] = synth
    row["tob_source"] = tob.get("source")
    row["n_tob"] = int(tob.get("n", len(tob["ts"])))
    row["native_tob"] = (not synth) and row["n_tob"] >= 50
    if not row["native_tob"]:
        row["skip"] = "trade_synth_or_sparse_tob"
        return row

    mid = np.asarray(tob.get("mid", 0.5 * (np.asarray(tob["bid"]) + np.asarray(tob["ask"]))), dtype=np.float64)
    intens = quote_storm_intensity(tob["ts"], tob["bid"], tob["ask"], tob["bid_sz"], tob["ask_sz"])
    storms = quote_storm_detect(
        intens, z_thresh=3.0, min_cancel_frac=0.3, max_mid_range_bps=15.0, min_intensity_hz=0.0
    )
    storm_ts = np.asarray(storms["ts"], dtype=np.int64)
    span_h = max(1e-6, (float(tob["ts"][-1] - tob["ts"][0]) / 1e9) / 3600.0)
    row["n_storm"] = int(storms["n_events"])
    row["storms_per_hour"] = float(storms["n_events"]) / span_h
    row["storm_ts"] = storm_ts
    row["intensity_hz"] = np.asarray(intens["intensity_hz"], dtype=np.float64)
    row["cancel_frac"] = np.asarray(intens["cancel_frac"], dtype=np.float64)
    row["span_h"] = float(span_h)

    idx = _subsample(ts.size, max_trades, seed=hash(f"{symbol}{venue}{day}") % 10_000)
    tt, sd, qq, pp = ts[idx], side[idx], qty[idx], px[idx]
    fade = price_fade_events(
        tt, sd, tob["ts"], tob["bid"], tob["ask"], tob["bid_sz"], tob["ask_sz"], tau_ms=100.0
    )
    ti = np.asarray(fade["trade_i"], dtype=np.int64)
    ff = np.asarray(fade["fade"], dtype=np.int64)
    fade_ts = tt[ti[ff > 0]] if ti.size and ff.size else np.zeros(0, dtype=np.int64)
    row["n_fade"] = int(fade["n_fade"])
    row["n_fade_trades"] = int(fade["n_trades"])
    row["p_fade"] = float(fade["n_fade"] / fade["n_trades"]) if fade["n_trades"] else float("nan")
    row["fade_ts"] = fade_ts

    ign = ignition_events(
        ts, px, qty, bar_s=1.0, phase1_bars=3, phase2_bars=3, phase3_bars=5,
        vol_z=1.0, mid_quiet_bps=15.0, move_bps=5.0, min_recovery=0.15,
    )
    ign_starts, _ = ignition_bar_timestamps(ign)
    row["n_ignition"] = int(len(ign_starts))
    row["ignition_per_day"] = float(len(ign_starts))
    row["ignition_ts"] = ign_starts
    row["ignition_move_bps"] = np.asarray(ign.get("move_bps", []), dtype=np.float64)
    row["ignition_recovery"] = np.asarray(ign.get("recovery_frac", []), dtype=np.float64)

    # markouts / IRF multi-horizon
    markouts: dict[str, Any] = {}
    for h in HORIZONS_MS:
        markouts[f"storm_{int(h)}"] = event_window_markout(
            storm_ts, ts, side, tob["ts"], mid, post_ms=min(h, 2000.0), horizon_ms=h
        )
        markouts[f"fade_{int(h)}"] = event_window_markout(
            fade_ts, ts, side, tob["ts"], mid, post_ms=min(h, 1000.0), horizon_ms=h
        )
        markouts[f"ignition_{int(h)}"] = event_window_markout(
            ign_starts, ts, side, tob["ts"], mid, post_ms=min(h, 3000.0), horizon_ms=h
        )
    # placebo storm (random TOB timestamps)
    rng = np.random.default_rng(hash(f"pl{symbol}{venue}{day}") % 10_000)
    if tob["ts"].size > 10 and storm_ts.size > 0:
        plac = rng.choice(np.asarray(tob["ts"], dtype=np.int64), size=min(storm_ts.size, 40), replace=False)
    else:
        plac = np.zeros(0, dtype=np.int64)
    markouts["placebo_storm_1000"] = event_window_markout(
        plac, ts, side, tob["ts"], mid, post_ms=500.0, horizon_ms=1000.0
    )
    sm = markouts.get("storm_1000", {})
    pm = markouts.get("placebo_storm_1000", {})
    row["storm_as_delta"] = (
        float(sm["mean_bps"] - pm["mean_bps"])
        if np.isfinite(sm.get("mean_bps", np.nan)) and np.isfinite(pm.get("mean_bps", np.nan))
        else float("nan")
    )
    row["markouts"] = {k: {kk: vv for kk, vv in v.items() if kk != "per_event_mean"} for k, v in markouts.items()}
    # keep per-event for bootstrap later (storm/fade 1s)
    row["storm_mo_1s"] = np.asarray(markouts["storm_1000"].get("per_event_mean", []), dtype=np.float64)
    row["fade_mo_1s"] = np.asarray(markouts["fade_1000"].get("per_event_mean", []), dtype=np.float64)
    row["ign_mo_1s"] = np.asarray(markouts["ignition_1000"].get("per_event_mean", []), dtype=np.float64)

    irf = spread_irf_after_events(fade_ts, tob["ts"], tob["bid"], tob["ask"])
    row["fade_irf"] = irf
    dlt = np.asarray(irf.get("mean_delta_bps", []), dtype=np.float64)
    dlt = dlt[np.isfinite(dlt)]
    row["fade_irf_peak"] = float(np.max(dlt)) if dlt.size else float("nan")
    # temporary vs permanent: short (250ms) vs long (5s) fade markout
    short = markouts["fade_250"].get("mean_bps", float("nan"))
    long = markouts["fade_5000"].get("mean_bps", float("nan"))
    row["fade_temp_vs_perm"] = {
        "short_250ms": short,
        "long_5000ms": long,
        "perm_share": float(long / short) if np.isfinite(short) and abs(short) > 1e-9 else float("nan"),
    }

    cascade = lead_lag_cascade(storm_ts, fade_ts, ign_starts)
    row["cascade"] = cascade
    row["ll_storm_fade"] = lead_lag_crosscorr(storm_ts, fade_ts)
    row["ll_fade_ign"] = lead_lag_crosscorr(fade_ts, ign_starts)
    row["ll_storm_ign"] = lead_lag_crosscorr(storm_ts, ign_starts)
    row["tod_storm"] = tod_seasonality(storm_ts)
    row["tod_fade"] = tod_seasonality(fade_ts)
    row["tod_ign"] = tod_seasonality(ign_starts)

    # store light intensity sample for univariate
    ih = row["intensity_hz"]
    if ih.size > 5000:
        ih = ih[:: max(1, ih.size // 5000)]
    row["intensity_hz_sample"] = ih
    return row


def build_panel(symbols: list[str], days: list[str], *, max_files: int, max_trades: int) -> list[dict[str, Any]]:
    ensure_env()
    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        for day in days:
            for venue in CORE_VENUES:
                print(f"  feature_stats {symbol} {venue} {day}", flush=True)
                rows.append(load_day_features(venue, symbol, day, max_files=max_files, max_trades=max_trades))
    return rows


def _native(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("native_tob") and r.get("complete")]


def analyze(rows: list[dict[str, Any]], days: list[str]) -> dict[str, Any]:
    native = _native(rows)
    early, late = _early_late(days)

    # --- univariate day-level ---
    feat_day: dict[str, list[float]] = {
        "storms_per_hour": [],
        "p_fade": [],
        "ignition_per_day": [],
        "clock_max_z": [],
        "storm_as_delta": [],
        "fade_irf_peak": [],
    }
    labels: list[str] = []
    for r in native:
        lab = f"{r['symbol']}|{r['venue']}|{r['day']}"
        labels.append(lab)
        for k in feat_day:
            feat_day[k].append(float(r.get(k, np.nan)))

    univariate = {k: univariate_moments(np.asarray(v, dtype=np.float64)) for k, v in feat_day.items()}

    # intensity pool (HL ETH preferred for distribution)
    intens_pool = []
    cancel_pool = []
    for r in native:
        if r["venue"] == "hyperliquid" and r["symbol"] == "ETH":
            intens_pool.append(np.asarray(r.get("intensity_hz_sample", []), dtype=np.float64))
            cancel_pool.append(np.asarray(r.get("cancel_frac", []), dtype=np.float64))
    intens_arr = np.concatenate(intens_pool) if intens_pool else np.zeros(0)
    cancel_arr = np.concatenate([c[np.isfinite(c)] for c in cancel_pool]) if cancel_pool else np.zeros(0)
    univariate["intensity_hz_HL_ETH"] = univariate_moments(intens_arr)
    univariate["cancel_frac_HL_ETH"] = univariate_moments(cancel_arr)

    # ToD aggregated (HL ETH storms)
    tod_counts = np.zeros(24, dtype=np.float64)
    for r in native:
        if r["venue"] == "hyperliquid":
            td = r.get("tod_storm") or {}
            c = np.asarray(td.get("counts", []), dtype=np.float64)
            if c.size == 24:
                tod_counts += c
    tod = {"hours": list(range(24)), "storm_counts_hl": tod_counts.tolist()}

    # --- dependence (day-level) ---
    keys = ["storms_per_hour", "p_fade", "ignition_per_day", "clock_max_z", "storm_as_delta", "fade_irf_peak"]
    dep: dict[str, Any] = {"pairs": {}, "partial": {}, "mi": {}}
    for i, ka in enumerate(keys):
        for kb in keys[i + 1 :]:
            xa = np.asarray(feat_day[ka], dtype=np.float64)
            xb = np.asarray(feat_day[kb], dtype=np.float64)
            dep["pairs"][f"{ka}__{kb}"] = pearson_spearman(xa, xb)
            dep["mi"][f"{ka}__{kb}"] = mutual_info_binned(xa, xb, n_bins=4)
    # partial: storms vs fade controlling ignition
    dep["partial"]["storms_p_fade_ctrl_ign"] = partial_corr(
        np.asarray(feat_day["storms_per_hour"]),
        np.asarray(feat_day["p_fade"]),
        np.asarray(feat_day["ignition_per_day"]),
    )

    # lead-lag pooled HL ETH
    ll_pool: dict[str, Any] = {}
    for r in native:
        if r["venue"] == "hyperliquid" and r["symbol"] == "ETH":
            for name in ("ll_storm_fade", "ll_fade_ign", "ll_storm_ign"):
                ll_pool.setdefault(name, []).append(r.get(name) or {})
    lead_lag = {}
    for name, items in ll_pool.items():
        if not items:
            continue
        lags = items[0].get("lags_ms", [])
        mat = [it.get("corr", []) for it in items if it.get("corr")]
        if not mat:
            continue
        arr = np.asarray(mat, dtype=np.float64)
        lead_lag[name] = {
            "lags_ms": lags,
            "mean_corr": np.nanmean(arr, axis=0).tolist(),
            "n_days": int(arr.shape[0]),
        }

    # --- predictive usefulness ---
    predictive: dict[str, Any] = {"endpoints": [], "by_horizon": {}, "early_late": {}}

    def _day_means(key: str, subset_days: list[str] | None = None) -> np.ndarray:
        out = []
        for r in native:
            if subset_days is not None and r["day"] not in subset_days:
                continue
            if key == "storm_as_delta":
                out.append(float(r.get("storm_as_delta", np.nan)))
            elif key == "fade_irf_peak":
                out.append(float(r.get("fade_irf_peak", np.nan)))
            elif key == "fade_mo_1s":
                arr = np.asarray(r.get("fade_mo_1s", []), dtype=np.float64)
                arr = arr[np.isfinite(arr)]
                out.append(float(np.mean(arr)) if arr.size else float("nan"))
            elif key == "storm_mo_1s":
                arr = np.asarray(r.get("storm_mo_1s", []), dtype=np.float64)
                arr = arr[np.isfinite(arr)]
                out.append(float(np.mean(arr)) if arr.size else float("nan"))
            elif key == "ign_mo_1s":
                arr = np.asarray(r.get("ign_mo_1s", []), dtype=np.float64)
                arr = arr[np.isfinite(arr)]
                out.append(float(np.mean(arr)) if arr.size else float("nan"))
            elif key == "perm_share":
                out.append(float((r.get("fade_temp_vs_perm") or {}).get("perm_share", np.nan)))
        return np.asarray(out, dtype=np.float64)

    primary = [
        ("storm_as_delta", "info.storm_adverse_selection"),
        ("fade_irf_peak", "info.fade_spread_widen_irf"),
        ("fade_mo_1s", "info.fade_markout_1s"),
        ("storm_mo_1s", "info.storm_markout_1s"),
        ("ign_mo_1s", "info.ignition_markout_1s"),
        ("perm_share", "info.fade_temp_vs_perm_impact"),
    ]
    p_raw = []
    for key, cid in primary:
        vals = _day_means(key)
        ci = day_block_bootstrap_ci(vals, n_boot=N_BOOT, seed=SEED)
        p = two_sided_p_from_ci(ci["point"], ci["lo"], ci["hi"])
        p_raw.append(p)
        e_ci = day_block_bootstrap_ci(_day_means(key, early), n_boot=N_BOOT, seed=SEED + 1)
        l_ci = day_block_bootstrap_ci(_day_means(key, late), n_boot=N_BOOT, seed=SEED + 2)
        predictive["endpoints"].append(
            {
                "id": cid,
                "metric": key,
                "ci": ci,
                "p_proxy": p,
                "early_ci": e_ci,
                "late_ci": l_ci,
                "sign_stable": bool(
                    np.isfinite(e_ci["point"])
                    and np.isfinite(l_ci["point"])
                    and (e_ci["point"] * l_ci["point"] > 0)
                ),
            }
        )
    fdr = bh_fdr(p_raw, alpha=0.05)
    for i, ep in enumerate(predictive["endpoints"]):
        ep["p_adj_bh"] = fdr["p_adj"][i]
        ep["reject_bh"] = fdr["reject"][i]
        # honesty: Promote only if BH reject AND sign-stable AND n>=10 days — still Hold
        ep["decision"] = "Hold"
        ep["why"] = (
            f"point={ep['ci']['point']:.4g} CI95=[{ep['ci']['lo']:.4g},{ep['ci']['hi']:.4g}] "
            f"BH_reject={ep['reject_bh']} sign_stable={ep['sign_stable']} n_days={ep['ci']['n']}"
        )
    predictive["bh"] = fdr
    predictive["pre_registered"] = [x[1] for x in primary]

    # multi-horizon fade/storm markout means (HL ETH)
    for h in HORIZONS_MS:
        sm, fm = [], []
        for r in native:
            if r["venue"] != "hyperliquid":
                continue
            mk = r.get("markouts") or {}
            sm.append(float((mk.get(f"storm_{int(h)}") or {}).get("mean_bps", np.nan)))
            fm.append(float((mk.get(f"fade_{int(h)}") or {}).get("mean_bps", np.nan)))
        predictive["by_horizon"][str(int(h))] = {
            "storm_markout_ci": day_block_bootstrap_ci(np.asarray(sm), n_boot=N_BOOT, seed=SEED),
            "fade_markout_ci": day_block_bootstrap_ci(np.asarray(fm), n_boot=N_BOOT, seed=SEED),
        }

    # venue completeness matrix
    completeness = []
    for r in rows:
        completeness.append(
            {
                "symbol": r.get("symbol"),
                "venue": r.get("venue"),
                "day": r.get("day"),
                "complete": r.get("complete"),
                "native_tob": r.get("native_tob"),
                "is_trade_synth": r.get("is_trade_synth"),
                "n_trades": r.get("n_trades"),
                "n_tob": r.get("n_tob"),
                "skip": r.get("skip"),
            }
        )

    return {
        "days": days,
        "early": early,
        "late": late,
        "n_rows": len(rows),
        "n_native_complete": len(native),
        "labels": labels,
        "univariate": univariate,
        "tod": tod,
        "dependence": dep,
        "lead_lag": lead_lag,
        "predictive": predictive,
        "completeness": completeness,
        "feat_day": feat_day,
        "cascade_hit_rates": _cascade_summary(native),
    }


def _cascade_summary(native: list[dict[str, Any]]) -> dict[str, Any]:
    # mean storm→fade @1s across native days
    s2f, s2i, f2i = [], [], []
    for r in native:
        c = r.get("cascade") or {}
        wins = c.get("windows_ms") or []
        if 1000.0 in wins:
            j = wins.index(1000.0)
            s2f.append(c["storm_to_fade"][j])
            s2i.append(c["storm_to_ignition"][j])
            f2i.append(c["fade_to_ignition"][j])
    return {
        "storm_to_fade_1s": day_block_bootstrap_ci(np.asarray(s2f, dtype=np.float64), n_boot=N_BOOT, seed=SEED),
        "storm_to_ignition_1s": day_block_bootstrap_ci(np.asarray(s2i, dtype=np.float64), n_boot=N_BOOT, seed=SEED),
        "fade_to_ignition_1s": day_block_bootstrap_ci(np.asarray(f2i, dtype=np.float64), n_boot=N_BOOT, seed=SEED),
    }


def make_figs(art: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    uni = art["univariate"]

    # 1. moments forest
    names = ["storms_per_hour", "p_fade", "ignition_per_day", "clock_max_z", "storm_as_delta", "fade_irf_peak"]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    y = np.arange(len(names))
    means = [uni[n]["mean"] for n in names]
    stds = [uni[n]["std"] for n in names]
    ax.errorbar(means, y, xerr=stds, fmt="o", color="#264653", capsize=3)
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=8)
    ax.axvline(0, color="#999", lw=0.8)
    ax.set_title("Day-level feature means ± std (native complete)")
    ax.set_xlabel("value")
    paths.append(_savefig(fig, "fig_univariate_means.png"))

    # 2. intensity dist
    fig, ax = plt.subplots(figsize=(7, 4))
    q = uni.get("intensity_hz_HL_ETH", {}).get("quantiles", {})
    ax.bar(["mean", "q50", "q95", "q99"], [
        uni.get("intensity_hz_HL_ETH", {}).get("mean", np.nan),
        q.get("q50", np.nan),
        q.get("q95", np.nan),
        q.get("q99", np.nan),
    ], color="#2a9d8f")
    ax.set_title("HL ETH intensity_hz moments")
    ax.set_ylabel("Hz (feed-sample)")
    paths.append(_savefig(fig, "fig_intensity_moments.png"))

    # 3. ToD
    fig, ax = plt.subplots(figsize=(8, 3.5))
    hours = art["tod"]["hours"]
    ax.bar(hours, art["tod"]["storm_counts_hl"], color="#e9c46a")
    ax.set_xlabel("UTC hour")
    ax.set_ylabel("storm count (HL pool)")
    ax.set_title("Storm ToD seasonality")
    paths.append(_savefig(fig, "fig_tod_storms.png"))

    # 4. corr heatmap
    keys = names
    mat = np.eye(len(keys))
    for i, ka in enumerate(keys):
        for j, kb in enumerate(keys):
            if i == j:
                continue
            pair = art["dependence"]["pairs"].get(f"{ka}__{kb}") or art["dependence"]["pairs"].get(f"{kb}__{ka}")
            if pair:
                mat[i, j] = pair.get("spearman", np.nan)
    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(mat, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(keys)))
    ax.set_yticks(range(len(keys)))
    ax.set_xticklabels(keys, rotation=45, ha="right", fontsize=7)
    ax.set_yticklabels(keys, fontsize=7)
    fig.colorbar(im, ax=ax, fraction=0.046)
    ax.set_title("Spearman (day-level)")
    paths.append(_savefig(fig, "fig_corr_spearman.png"))

    # 5. lead-lag
    fig, ax = plt.subplots(figsize=(8, 4))
    for name, style in (("ll_storm_fade", "-"), ("ll_fade_ign", "--"), ("ll_storm_ign", ":")):
        ll = art["lead_lag"].get(name)
        if not ll:
            continue
        ax.plot(ll["lags_ms"], ll["mean_corr"], style, label=name.replace("ll_", ""))
    ax.axhline(0, color="#999", lw=0.8)
    ax.axvline(0, color="#999", lw=0.8)
    ax.legend(fontsize=8)
    ax.set_xlabel("lag ms (positive ⇒ A leads B)")
    ax.set_ylabel("bar-count corr")
    ax.set_title("Lead-lag cross-corr (HL ETH pool)")
    paths.append(_savefig(fig, "fig_lead_lag_xcorr.png"))

    # 6. predictive forest
    eps = art["predictive"]["endpoints"]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    y = np.arange(len(eps))
    pts = [e["ci"]["point"] for e in eps]
    los = [e["ci"]["point"] - e["ci"]["lo"] for e in eps]
    his = [e["ci"]["hi"] - e["ci"]["point"] for e in eps]
    ax.errorbar(pts, y, xerr=[los, his], fmt="o", color="#264653", capsize=3)
    ax.axvline(0, color="#c1121f", lw=0.9)
    ax.set_yticks(y)
    ax.set_yticklabels([e["id"] for e in eps], fontsize=7)
    ax.set_title("Primary endpoints — day-block bootstrap 95% CI (Hold)")
    ax.set_xlabel("effect size")
    paths.append(_savefig(fig, "fig_predictive_forest.png"))

    # 7. horizon IRF-style markouts
    fig, ax = plt.subplots(figsize=(7, 4))
    hs = sorted(int(k) for k in art["predictive"]["by_horizon"])
    storm_pts = [art["predictive"]["by_horizon"][str(h)]["storm_markout_ci"]["point"] for h in hs]
    fade_pts = [art["predictive"]["by_horizon"][str(h)]["fade_markout_ci"]["point"] for h in hs]
    ax.plot(hs, storm_pts, "o-", label="storm markout")
    ax.plot(hs, fade_pts, "s-", label="fade markout")
    ax.axhline(0, color="#999", lw=0.8)
    ax.legend(fontsize=8)
    ax.set_xlabel("horizon ms")
    ax.set_ylabel("mean markout bps")
    ax.set_title("Multi-horizon markout (HL pool, day means)")
    paths.append(_savefig(fig, "fig_markout_horizons.png"))

    # 8. completeness
    comp = art["completeness"]
    venues = sorted({c["venue"] for c in comp})
    days = art["days"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.5))
    for ax, sym in zip(axes, ("ETH", "BTC")):
        mat = np.zeros((len(venues), len(days)))
        for i, v in enumerate(venues):
            for j, d in enumerate(days):
                hit = [c for c in comp if c["symbol"] == sym and c["venue"] == v and c["day"] == d]
                if hit and hit[0].get("native_tob") and hit[0].get("complete"):
                    mat[i, j] = 1.0
                elif hit and hit[0].get("complete"):
                    mat[i, j] = 0.4
        ax.imshow(mat, cmap="Greens", vmin=0, vmax=1, aspect="auto")
        ax.set_yticks(range(len(venues)))
        ax.set_yticklabels(venues, fontsize=7)
        ax.set_xticks(range(len(days)))
        ax.set_xticklabels([d[5:] for d in days], fontsize=7, rotation=45)
        ax.set_title(f"{sym} completeness (1=native TOB)")
    paths.append(_savefig(fig, "fig_completeness.png"))

    return paths


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", nargs="*", default=DAYS_DEFAULT)
    ap.add_argument("--symbols", nargs="*", default=["ETH", "BTC"])
    ap.add_argument("--max-files", type=int, default=24)
    ap.add_argument("--max-trades", type=int, default=12_000)
    args = ap.parse_args()

    print("=== exp_feature_stats ===", flush=True)
    rows = build_panel(args.symbols, args.days, max_files=args.max_files, max_trades=args.max_trades)
    # strip heavy arrays before JSON of raw rows summary
    light_rows = []
    for r in rows:
        lr = {k: v for k, v in r.items() if k not in {
            "storm_ts", "fade_ts", "ignition_ts", "intensity_hz", "cancel_frac",
            "intensity_hz_sample", "storm_mo_1s", "fade_mo_1s", "ign_mo_1s",
            "ignition_move_bps", "ignition_recovery", "ll_storm_fade", "ll_fade_ign",
            "ll_storm_ign", "tod_storm", "tod_fade", "tod_ign", "cascade", "markouts",
            "fade_irf",
        }}
        # keep compact summaries
        lr["fade_temp_vs_perm"] = r.get("fade_temp_vs_perm")
        lr["fade_irf_peak"] = r.get("fade_irf_peak")
        lr["storm_as_delta"] = r.get("storm_as_delta")
        light_rows.append(lr)

    art = analyze(rows, args.days)
    figs = make_figs(art)
    art["fig_paths"] = figs
    # drop feat_day raw from top-level duplicate if huge — keep
    out = {
        "meta": {
            "days": args.days,
            "symbols": args.symbols,
            "horizons_ms": list(HORIZONS_MS),
            "n_boot": N_BOOT,
            "note": "Honest research usefulness — not α. Kraken synth excluded from native TOB.",
        },
        "panel_light": light_rows,
        "analysis": {k: v for k, v in art.items() if k != "feat_day"},
        "feat_day": art["feat_day"],
        "fig_paths": figs,
        "candidates": [
            {
                "id": ep["id"],
                "decision": ep["decision"],
                "type": "E",
                "lenses": ["info", "risk"],
                "why": ep["why"],
                "falsifier": "BH non-reject or early/late sign flip or n_days<10 → Hold not Promote",
                "source": "feature_stats",
            }
            for ep in art["predictive"]["endpoints"]
        ],
    }
    _json(OUT / "feature_stats.json", out)
    _json(OUT / "fig_index.json", {"figs": figs})
    print(json.dumps({"n_native": art["n_native_complete"], "figs": len(figs), "out": str(OUT)}, indent=2))
    for ep in art["predictive"]["endpoints"]:
        print(f"  {ep['id']}: {ep['why']}", flush=True)


if __name__ == "__main__":
    main()
