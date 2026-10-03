#!/usr/bin/env python3
"""Feature statistical analysis for squeeze_metrics Hold / info objects.

Univariate · Spearman/Pearson · day-block bootstrap · chrono splits · ToD ·
Fisher-z Normal posterior. Consumes ``out/info_features/joined_day_hourly.json``
when present.

Writes ``out/feature_stats/`` JSON + figs + EXP_REPORT.
ClickHouse MCP banned. Never soft-Promote TOB-cross α.
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

from _stats_info import (  # noqa: E402
    day_block_bootstrap_corr,
    day_block_bootstrap_stat,
    fisher_z_normal_posterior,
    lead_lag_corr,
    pearson_spearman,
    tod_profile,
    univariate_moments,
)

OUT = BOOK / "out" / "feature_stats"
FIGS = OUT / "figs"
JOINED = BOOK / "out" / "info_features" / "joined_day_hourly.json"
GEX_ROWS = BOOK / "out" / "gex_implied_book" / "panel_rows.json"
N_BOOT = 500
SEED = 7


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


def _load() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    day_rows: list[dict[str, Any]] = []
    if JOINED.is_file():
        blob = json.loads(JOINED.read_text())
        day_rows = list(blob.get("rows") or [])
    if not day_rows and GEX_ROWS.is_file():
        day_rows = [r for r in json.loads(GEX_ROWS.read_text()) if r.get("ok")]
    # flatten hourly
    hourly: list[dict[str, Any]] = []
    for r in day_rows:
        h = r.get("hourly") or {}
        if not h.get("ok"):
            continue
        hours = h.get("hour_utc") or []
        for i, hh in enumerate(hours):
            hourly.append(
                {
                    "day": r["day"],
                    "hour_utc": hh,
                    "mid_ret": (h.get("mid_ret") or [None])[i] if i < len(h.get("mid_ret") or []) else None,
                    "rv": (h.get("rv") or [None])[i] if i < len(h.get("rv") or []) else None,
                    "spread_bps": (h.get("spread_bps") or [None])[i] if i < len(h.get("spread_bps") or []) else None,
                    "range_1h": (h.get("range_1h") or [None])[i] if i < len(h.get("range_1h") or []) else None,
                    "gex": r.get("gex"),
                    "vex": r.get("vex"),
                    "squeeze_intensity": r.get("squeeze_intensity"),
                    "scarce": r.get("scarce"),
                }
            )
    return day_rows, hourly


def run_stats(day_rows: list[dict[str, Any]], hourly: list[dict[str, Any]]) -> dict[str, Any]:
    days = sorted({str(r["day"]) for r in day_rows})
    mid = max(1, len(days) // 2)
    early, late = days[:mid], days[mid:]

    day_features = ("gex", "vex", "gex_plus", "squeeze_intensity", "hl_rv", "hl_range", "db_rv", "db_range")
    uni: dict[str, Any] = {}
    day_mean_ci: dict[str, Any] = {}
    for key in day_features:
        x = np.asarray([r.get(key) for r in day_rows], dtype=np.float64)
        uni[key] = univariate_moments(x)
        day_mean_ci[key] = day_block_bootstrap_stat(x, n_boot=N_BOOT, seed=SEED)

    pairs = [
        ("gex", "hl_rv"),
        ("gex", "hl_range"),
        ("vex", "hl_range"),
        ("vex", "hl_rv"),
        ("gex_plus", "hl_range"),
        ("squeeze_intensity", "hl_rv"),
        ("gex", "vex"),
        ("gex", "db_rv"),
    ]
    dep: dict[str, Any] = {}
    days_arr = np.asarray([str(r["day"]) for r in day_rows], dtype=object)
    for a, b in pairs:
        xa = np.asarray([r.get(a) for r in day_rows], dtype=np.float64)
        ya = np.asarray([r.get(b) for r in day_rows], dtype=np.float64)
        ps = pearson_spearman(xa, ya)
        block = day_block_bootstrap_corr(days_arr, xa, ya, n_boot=N_BOOT, seed=SEED, min_n=4)
        bayes = fisher_z_normal_posterior(float(ps["pearson"]), int(ps["n"]))
        early_rows = [r for r in day_rows if str(r["day"]) in early]
        late_rows = [r for r in day_rows if str(r["day"]) in late]
        xe = np.asarray([r.get(a) for r in early_rows], dtype=np.float64)
        ye = np.asarray([r.get(b) for r in early_rows], dtype=np.float64)
        xl = np.asarray([r.get(a) for r in late_rows], dtype=np.float64)
        yl = np.asarray([r.get(b) for r in late_rows], dtype=np.float64)
        pe, pl = pearson_spearman(xe, ye), pearson_spearman(xl, yl)
        dep[f"{a}__{b}"] = {
            **ps,
            "day_block": block,
            "bayes_fisher_z": bayes,
            "chrono": {
                "early": pe,
                "late": pl,
                "early_days": early,
                "late_days": late,
                "sign_stable": bool(
                    np.isfinite(pe["pearson"])
                    and np.isfinite(pl["pearson"])
                    and np.sign(pe["pearson"]) == np.sign(pl["pearson"])
                ),
            },
        }

    # hourly uni + ToD
    tod: dict[str, Any] = {}
    hourly_uni: dict[str, Any] = {}
    if hourly:
        for key in ("mid_ret", "rv", "spread_bps", "range_1h"):
            x = np.asarray([h.get(key) for h in hourly], dtype=np.float64)
            hu = np.asarray([h.get("hour_utc") for h in hourly], dtype=np.float64)
            hourly_uni[key] = univariate_moments(x)
            tod[key] = tod_profile(hu, x)

    # IRF-style: day GEX broadcast onto hourly mid_ret lead-lag pooled within day is weak;
    # instead report pooled hourly lead-lag mid_ret ↔ rv
    irf: dict[str, Any] = {}
    if hourly:
        mr = np.asarray([h.get("mid_ret") for h in hourly], dtype=np.float64)
        rv = np.asarray([h.get("rv") for h in hourly], dtype=np.float64)
        sp = np.asarray([h.get("spread_bps") for h in hourly], dtype=np.float64)
        irf["mid_ret->rv"] = lead_lag_corr(mr, rv, lags=(-3, -2, -1, 0, 1, 2, 3))
        irf["mid_ret->spread"] = lead_lag_corr(mr, sp, lags=(-3, -2, -1, 0, 1, 2, 3))
        # day-level GEX vs same-day mean |mid_ret|
        gex_day = []
        absret_day = []
        for r in day_rows:
            h = r.get("hourly") or {}
            if not h.get("ok"):
                continue
            gex_day.append(r.get("gex"))
            mr_d = np.asarray(h.get("mid_ret") or [], dtype=np.float64)
            absret_day.append(float(np.nanmean(np.abs(mr_d))) if mr_d.size else float("nan"))
        irf["gex_vs_mean_abs_mid_ret"] = pearson_spearman(
            np.asarray(gex_day, dtype=np.float64), np.asarray(absret_day, dtype=np.float64)
        )

    return {
        "n_days": len(day_rows),
        "days": days,
        "early_days": early,
        "late_days": late,
        "univariate_day": uni,
        "day_mean_ci": day_mean_ci,
        "dependence": dep,
        "hourly_univariate": hourly_uni,
        "tod": tod,
        "irf": irf,
        "n_hourly": len(hourly),
    }


def _figs(stats: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    dep = stats.get("dependence") or {}
    # corr CI forest
    fig, ax = plt.subplots(figsize=(7.5, 4.0))
    labels, pts, los, his, stable = [], [], [], [], []
    for key, rec in dep.items():
        b = rec.get("day_block") or {}
        labels.append(key.replace("__", "↔"))
        pts.append(b.get("corr") if b.get("corr") is not None else rec.get("pearson"))
        los.append(b.get("ci_lo"))
        his.append(b.get("ci_hi"))
        stable.append((rec.get("chrono") or {}).get("sign_stable"))
    y = np.arange(len(labels))
    for i in range(len(labels)):
        if pts[i] is None or not np.isfinite(pts[i]):
            continue
        lo = los[i] if los[i] is not None and np.isfinite(los[i]) else pts[i]
        hi = his[i] if his[i] is not None and np.isfinite(his[i]) else pts[i]
        color = "#2f7d4a" if stable[i] else "#b33a3a"
        ax.plot([lo, hi], [y[i], y[i]], color=color, lw=2)
        ax.scatter([pts[i]], [y[i]], color=color, zorder=3, s=35)
    ax.axvline(0, color="k", lw=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("Pearson (day-block 95% CI); green=chrono stable")
    ax.set_title(f"Feature dependence · n_days={stats.get('n_days')}")
    paths.append(_savefig(fig, "fig_dep_ci.png"))

    # ToD mid_ret / rv
    tod = stats.get("tod") or {}
    if tod:
        fig, axes = plt.subplots(1, 2, figsize=(9.0, 3.5))
        for ax, key, title in ((axes[0], "mid_ret", "ToD mid_ret"), (axes[1], "rv", "ToD RV")):
            rec = tod.get(key) or {}
            ax.plot(rec.get("hours") or [], rec.get("means") or [], "-o", ms=3, color="#3d5a80")
            ax.set_xlabel("UTC hour")
            ax.set_title(title)
        paths.append(_savefig(fig, "fig_tod.png"))

    # univariate GEX hist
    uni = stats.get("univariate_day") or {}
    fig, axes = plt.subplots(1, 3, figsize=(9.5, 3.2))
    for ax, key in zip(axes, ("gex", "vex", "hl_rv")):
        # reconstruct from quantiles only — skip hist if no raw; use text summary
        u = uni.get(key) or {}
        ax.axis("off")
        txt = "\n".join(
            [
                f"{key}",
                f"n={u.get('n')}",
                f"mean={u.get('mean')}",
                f"std={u.get('std')}",
                f"skew={u.get('skew')}",
            ]
        )
        ax.text(0.05, 0.5, txt, fontsize=9, family="monospace", va="center")
    fig.suptitle("Day-level univariate moments")
    paths.append(_savefig(fig, "fig_uni_moments.png"))
    return paths


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    args = ap.parse_args()
    del args

    OUT.mkdir(parents=True, exist_ok=True)
    FIGS.mkdir(parents=True, exist_ok=True)
    day_rows, hourly = _load()
    if not day_rows:
        print(json.dumps({"ok": False, "blocker": "missing joined/gex rows"}))
        return 2

    stats = run_stats(day_rows, hourly)
    fig_paths = _figs(stats)
    stats["figs"] = fig_paths
    stats["honesty"] = (
        "Feature stats on certified panel; Fisher-z descriptive; "
        "0 Promote; ClickHouse MCP banned; trade_synth QUARANTINED"
    )
    _write(OUT / "feature_stats.json", stats)

    # report table of key corrs
    lines = [
        "# EXP_REPORT — feature stats (Pass 2b)",
        "",
        f"- Days: {stats['n_days']} · `{stats['days']}`",
        f"- Early/late: {stats['early_days']} / {stats['late_days']}",
        f"- Hourly obs: {stats['n_hourly']}",
        f"- Figs: `out/feature_stats/figs/`",
        "",
        "## Key correlations (day-block CI)",
        "",
        "| pair | pearson | spearman | CI lo | CI hi | sign-stable |",
        "|------|---------|----------|-------|-------|-------------|",
    ]
    for key, rec in (stats.get("dependence") or {}).items():
        b = rec.get("day_block") or {}
        ch = rec.get("chrono") or {}
        lines.append(
            f"| {key} | {rec.get('pearson')} | {rec.get('spearman')} | "
            f"{b.get('ci_lo')} | {b.get('ci_hi')} | {ch.get('sign_stable')} |"
        )
    lines += [
        "",
        "## Day-mean CIs (block bootstrap over days)",
        "",
    ]
    for key, ci in (stats.get("day_mean_ci") or {}).items():
        lines.append(
            f"- **{key}**: point={ci.get('point')} CI[{ci.get('lo')}, {ci.get('hi')}] n_days={ci.get('n')}"
        )
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
    print(json.dumps(_jsonable({"written": str(OUT / "feature_stats.json"), "figs": fig_paths}), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
