#!/usr/bin/env python3
"""Feature statistical analysis for cd_me Hold / info objects.

Univariate · Spearman/Pearson · day-block bootstrap · chrono splits · ToD ·
optional Fisher-z Normal posterior on key corrs. Consumes
``out/info_features/joined_hourly.json`` when present (else rebuilds via
exp_info_features helpers).

Writes ``out/feature_stats/`` JSON + figs. ClickHouse MCP banned.
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

from _data import ensure_env  # noqa: E402
from _stats_info import (  # noqa: E402
    day_block_bootstrap_corr,
    day_block_bootstrap_stat,
    fisher_z_normal_posterior,
    lead_lag_corr,
    pearson_spearman,
    tod_profile,
    univariate_moments,
)
from exp_info_features import build_joined_panel  # noqa: E402

OUT = BOOK / "out" / "feature_stats"
FIGS = OUT / "figs"
INFO_JOINED = BOOK / "out" / "info_features" / "joined_hourly.json"
N_BOOT = 500
SEED = 7
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


def _load_joined(symbol: str) -> list[dict[str, Any]]:
    if INFO_JOINED.is_file():
        blob = json.loads(INFO_JOINED.read_text())
        rows = blob.get("rows") or []
        if rows:
            print(f"loaded joined_hourly n_days={len(rows)}", flush=True)
            return rows
    print("rebuilding joined panel…", flush=True)
    rows, _ = build_joined_panel(symbol)
    return rows


def _flat(joined: list[dict[str, Any]], key: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    xs: list[float] = []
    days: list[str] = []
    hours: list[float] = []
    for r in joined:
        arr = np.asarray(r[key], dtype=np.float64)
        hu = np.asarray(r.get("hour_utc") or [], dtype=np.float64)
        for i, v in enumerate(arr):
            xs.append(float(v))
            days.append(str(r["day"]))
            hours.append(float(hu[i]) if i < hu.size else float("nan"))
    return np.asarray(xs), np.asarray(days, dtype=object), np.asarray(hours)


def _pair(joined: list[dict[str, Any]], a: str, b: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    xs: list[float] = []
    ys: list[float] = []
    days: list[str] = []
    for r in joined:
        aa = np.asarray(r[a], dtype=np.float64)
        bb = np.asarray(r[b], dtype=np.float64)
        n = min(aa.size, bb.size)
        for i in range(n):
            xs.append(float(aa[i]))
            ys.append(float(bb[i]))
            days.append(str(r["day"]))
    return np.asarray(xs), np.asarray(ys), np.asarray(days, dtype=object)


def _day_means(joined: list[dict[str, Any]], key: str) -> np.ndarray:
    out = []
    for r in joined:
        a = np.asarray(r[key], dtype=np.float64)
        out.append(float(np.nanmean(a)) if np.isfinite(a).any() else float("nan"))
    return np.asarray(out, dtype=np.float64)


def run_stats(joined: list[dict[str, Any]]) -> dict[str, Any]:
    days = sorted({r["day"] for r in joined})
    mid = max(1, len(days) // 2)
    early, late = days[:mid], days[mid:]

    features = ("pim", "vloop", "tcost", "dcm", "notional", "rv", "mid_ret", "abs_funding", "abs_basis", "imbalance")
    uni: dict[str, Any] = {}
    tod: dict[str, Any] = {}
    day_mean_ci: dict[str, Any] = {}
    for key in features:
        x, d, h = _flat(joined, key)
        uni[key] = univariate_moments(x)
        tod[key] = tod_profile(h, x)
        dm = _day_means(joined, key)
        day_mean_ci[key] = day_block_bootstrap_stat(dm, n_boot=N_BOOT, seed=SEED)

    pairs = [
        ("pim", "dcm"),
        ("pim", "rv"),
        ("pim", "notional"),
        ("pim", "mid_ret"),
        ("vloop", "tcost"),
        ("vloop", "dcm"),
        ("tcost", "dcm"),
        ("dcm", "rv"),
        ("dcm", "abs_funding"),
        ("notional", "rv"),
    ]
    dep: dict[str, Any] = {}
    for a, b in pairs:
        xa, ya, da = _pair(joined, a, b)
        block = day_block_bootstrap_corr(da, xa, ya, n_boot=N_BOOT, seed=SEED)
        ps = pearson_spearman(xa, ya)
        bayes = fisher_z_normal_posterior(float(ps["pearson"]), int(ps["n"]))
        # chrono
        early_rows = [r for r in joined if r["day"] in early]
        late_rows = [r for r in joined if r["day"] in late]
        xe, ye, _ = _pair(early_rows, a, b)
        xl, yl, _ = _pair(late_rows, a, b)
        dep[f"{a}__{b}"] = {
            **ps,
            "day_block": block,
            "bayes_fisher_z": bayes,
            "chrono": {
                "early": pearson_spearman(xe, ye),
                "late": pearson_spearman(xl, yl),
                "early_days": early,
                "late_days": late,
                "sign_stable": bool(
                    np.isfinite(pearson_spearman(xe, ye)["pearson"])
                    and np.isfinite(pearson_spearman(xl, yl)["pearson"])
                    and np.sign(pearson_spearman(xe, ye)["pearson"])
                    == np.sign(pearson_spearman(xl, yl)["pearson"])
                ),
            },
        }

    # IRF-style lead-lag summaries (objects → mid_ret / RV)
    irf: dict[str, Any] = {}
    for carr in ("pim", "vloop", "tcost", "dcm"):
        for tgt in ("mid_ret", "rv", "notional"):
            xs: list[float] = []
            ys: list[float] = []
            for r in joined:
                xs.extend(np.asarray(r[carr], dtype=np.float64).tolist())
                ys.extend(np.asarray(r[tgt], dtype=np.float64).tolist())
                xs.append(float("nan"))
                ys.append(float("nan"))
            irf[f"{carr}->{tgt}"] = lead_lag_corr(np.asarray(xs), np.asarray(ys), lags=LAGS)

    # Kraken mode strata stats
    by_mode: dict[str, list] = {}
    for r in joined:
        by_mode.setdefault(r.get("kraken_mode", "unknown"), []).append(r)
    mode_stats: dict[str, Any] = {}
    for mode, rows in by_mode.items():
        xa, ya, da = _pair(rows, "pim", "dcm")
        mode_stats[mode] = {
            "n_days": len(rows),
            "pim_day_mean_ci": day_block_bootstrap_stat(_day_means(rows, "pim"), n_boot=N_BOOT, seed=SEED),
            "corr_pim_dcm": {
                **pearson_spearman(xa, ya),
                "day_block": day_block_bootstrap_corr(da, xa, ya, n_boot=N_BOOT, seed=SEED),
            },
        }

    # decisions echo (stats hygiene board — not new α)
    hygiene = {
        "note": "Stats layer supports Hold/Kill; never soft-Promote TOB-cross α",
        "n_pairs_tested": len(pairs),
        "multiple_testing": "report family size; do not claim discovery from unadjusted α",
        "block_bootstrap": "day blocks preferred over iid hour bootstrap",
    }

    return {
        "meta": {"n_days": len(days), "days": days, "early": early, "late": late},
        "univariate": uni,
        "tod": tod,
        "day_mean_ci": day_mean_ci,
        "dependence": dep,
        "irf_leadlag": irf,
        "kraken_mode_stats": mode_stats,
        "hygiene": hygiene,
    }


def write_figs(joined: list[dict[str, Any]], stats: dict[str, Any]) -> list[str]:
    paths: list[str] = []

    # hist PIM / DCM / VLOOP
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.4))
    for ax, key, color in zip(axes, ("pim", "vloop", "dcm"), ("#1f4e79", "#c55a11", "#548235")):
        x, _, _ = _flat(joined, key)
        x = x[np.isfinite(x)]
        if x.size:
            # clip display tails
            lo, hi = np.nanpercentile(x, [1, 99])
            ax.hist(x[(x >= lo) & (x <= hi)], bins=40, color=color, alpha=0.85)
        ax.set_title(f"{key} (n={x.size})")
    fig.suptitle("Univariate distributions (1–99% display clip)", fontsize=11)
    fig.tight_layout()
    paths.append(_savefig(fig, "fig_univariate_hists.png"))

    # corr forest with day-block CI
    keys = ["pim__dcm", "pim__rv", "pim__notional", "vloop__tcost", "dcm__rv"]
    labels = ["PIM↔DCM", "PIM↔RV", "PIM↔VLM", "VLOOP↔TCOST", "DCM↔RV"]
    pts, los, his = [], [], []
    for k in keys:
        block = (stats["dependence"].get(k) or {}).get("day_block") or {}
        pts.append(block.get("corr"))
        los.append(block.get("ci_lo"))
        his.append(block.get("ci_hi"))
    fig, ax = plt.subplots(figsize=(7.5, 4.0))
    y = np.arange(len(labels))
    for i, (p, lo, hi) in enumerate(zip(pts, los, his)):
        if p is None or not np.isfinite(p):
            continue
        ax.plot(p, i, "o", color="#1f4e79")
        if lo is not None and hi is not None and np.isfinite(lo) and np.isfinite(hi):
            ax.hlines(i, lo, hi, color="#1f4e79", lw=2)
    ax.axvline(0, color="#888", lw=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Pearson corr (day-block bootstrap 95% CI)")
    ax.set_title("Dependence forest — day-block CIs")
    fig.tight_layout()
    paths.append(_savefig(fig, "fig_corr_forest.png"))

    # ToD heatmap objects × hour
    keys_tod = ["pim", "vloop", "tcost", "dcm", "notional"]
    mat = np.full((len(keys_tod), 24), np.nan)
    for i, k in enumerate(keys_tod):
        means = stats["tod"][k]["means"]
        for j in range(24):
            mat[i, j] = means[j] if j < len(means) else np.nan
    # z-score rows for display
    mat_z = mat.copy()
    for i in range(mat_z.shape[0]):
        row = mat_z[i]
        m = np.isfinite(row)
        if m.sum() >= 3:
            mu, sd = np.nanmean(row), np.nanstd(row)
            if sd > 0:
                mat_z[i] = (row - mu) / sd
    fig, ax = plt.subplots(figsize=(10, 3.6))
    im = ax.imshow(mat_z, aspect="auto", cmap="coolwarm", vmin=-2, vmax=2)
    ax.set_yticks(range(len(keys_tod)))
    ax.set_yticklabels(keys_tod)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xlabel("UTC hour")
    ax.set_title("ToD profiles (row z-score)")
    fig.colorbar(im, ax=ax, fraction=0.025)
    fig.tight_layout()
    paths.append(_savefig(fig, "fig_tod_heatmap.png"))

    # chrono early/late for key pairs
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    pairs_show = ["pim__dcm", "pim__notional", "vloop__tcost"]
    x = np.arange(len(pairs_show))
    w = 0.35
    early_v = [((stats["dependence"][k]["chrono"]["early"]).get("pearson") or 0) for k in pairs_show]
    late_v = [((stats["dependence"][k]["chrono"]["late"]).get("pearson") or 0) for k in pairs_show]
    ax.bar(x - w / 2, early_v, w, label="early", color="#3d5a80")
    ax.bar(x + w / 2, late_v, w, label="late", color="#ee6c4d")
    ax.axhline(0, color="#888", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(["PIM↔DCM", "PIM↔VLM", "VLOOP↔TCOST"])
    ax.set_ylabel("Pearson")
    ax.set_title("Chronological early / late split")
    ax.legend(frameon=False)
    fig.tight_layout()
    paths.append(_savefig(fig, "fig_chrono_split.png"))

    # Bayes posterior CrI for key corrs
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    names = ["pim__dcm", "vloop__tcost", "pim__notional"]
    labs = ["PIM↔DCM", "VLOOP↔TCOST", "PIM↔VLM"]
    for i, (k, lab) in enumerate(zip(names, labs)):
        b = (stats["dependence"][k].get("bayes_fisher_z") or {})
        mean = b.get("mean_r")
        cri = b.get("cri95") or [None, None]
        if mean is None or not np.isfinite(mean):
            continue
        ax.plot(mean, i, "o", color="#1f4e79")
        if cri[0] is not None and cri[1] is not None:
            ax.hlines(i, cri[0], cri[1], color="#1f4e79", lw=2)
    ax.axvline(0, color="#888", lw=0.8)
    ax.set_yticks(range(len(labs)))
    ax.set_yticklabels(labs)
    ax.set_xlabel("posterior mean r (Fisher-z Normal, 95% CrI)")
    ax.set_title("Light Bayes on correlations (not α)")
    fig.tight_layout()
    paths.append(_savefig(fig, "fig_bayes_corr_cri.png"))

    # IRF lead-lag for PIM→mid_ret
    irf = stats["irf_leadlag"].get("pim->mid_ret") or {}
    fig, ax = plt.subplots(figsize=(7.0, 3.5))
    ax.axhline(0, color="#888", lw=0.8)
    ax.plot(irf.get("lags") or [], irf.get("corr") or [], "o-", color="#1f4e79")
    ax.set_xlabel("lag hours")
    ax.set_ylabel("corr(PIM, mid_ret)")
    ax.set_title("IRF-style lead-lag: PIM vs mid returns")
    fig.tight_layout()
    paths.append(_savefig(fig, "fig_irf_pim_midret.png"))

    return paths


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default="ETH")
    args = ap.parse_args()
    ensure_env()
    OUT.mkdir(parents=True, exist_ok=True)
    FIGS.mkdir(parents=True, exist_ok=True)

    joined = _load_joined(args.symbol)
    if not joined:
        print("no joined panel", file=sys.stderr)
        return 1
    stats = run_stats(joined)
    figs = write_figs(joined, stats)
    stats["figs"] = figs
    _write(OUT / "feature_stats.json", stats)

    # EXP_REPORT
    dep = stats["dependence"]
    lines = [
        "# EXP_REPORT — feature stats (Pass 2.5)",
        "",
        f"- Days: {stats['meta']['n_days']} · `{stats['meta']['days']}`",
        f"- Early/late: {stats['meta']['early']} / {stats['meta']['late']}",
        f"- Figs: `out/feature_stats/figs/`",
        "",
        "## Key correlations (day-block CI)",
        "",
        "| pair | pearson | spearman | CI lo | CI hi | sign-stable |",
        "|------|---------|----------|-------|-------|-------------|",
    ]
    for k in ("pim__dcm", "pim__rv", "pim__notional", "vloop__tcost", "dcm__rv"):
        d = dep[k]
        b = d.get("day_block") or {}
        lines.append(
            f"| {k} | {d.get('pearson'):.3f} | {d.get('spearman'):.3f} | "
            f"{b.get('ci_lo')} | {b.get('ci_hi')} | {d['chrono'].get('sign_stable')} |"
        )
    lines += [
        "",
        "## Day-mean CIs (block bootstrap over days)",
        "",
    ]
    for k in ("pim", "vloop", "tcost", "dcm"):
        ci = stats["day_mean_ci"][k]
        lines.append(f"- **{k}**: point={ci.get('point'):.6g} CI[{ci.get('lo')}, {ci.get('hi')}] n_days={ci.get('n')}")
    lines += [
        "",
        "## Honesty",
        "",
        "- Family size reported; no Discover-from-α",
        "- Fisher-z Bayes is descriptive posterior on corr — **not** tradable edge",
        "- Never soft-Promote TOB-cross α",
        "",
    ]
    (OUT / "EXP_REPORT.md").write_text("\n".join(lines))
    print("wrote", OUT / "feature_stats.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
