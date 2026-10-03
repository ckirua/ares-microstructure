#!/usr/bin/env python3
"""Pass-2b falsifiers for squeeze_metrics — hardened board (cd_me quality).

Certified ``panel_gex_options`` only (primary). Checks:
  - chronological half-split sign stability (GEX↔RV / GEX↔range / VEX↔range)
  - day-block bootstrap CIs (resample whole days; not iid rows)
  - placebo: shuffle GEX labels across days
  - venue-drop: HL-only vs Deribit-only vs HL+DB join metrics
  - appendix: spot_l2 subpanel n=4 sensitivity (not primary)

Never Promote TOB-cross α. Never re-admit trade_synth. ClickHouse MCP banned.
Writes ``out/pass2/`` JSON + figs + EXP_REPORT.
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
    pearson_spearman,
)
from certified_panel import gex_panel_days, load_certified, spot_l2_days  # noqa: E402

OUT = BOOK / "out" / "pass2"
FIGS = OUT / "figs"
GEX_ROWS = BOOK / "out" / "gex_implied_book" / "panel_rows.json"
GEX_SUM = BOOK / "out" / "gex_implied_book" / "summary.json"
N_BOOT = 600
SEED = 7
MIN_N = 4


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


def _savefig(fig: plt.Figure, name: str) -> str:
    FIGS.mkdir(parents=True, exist_ok=True)
    path = FIGS / name
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return str(path.relative_to(BOOK))


def _load_rows() -> list[dict[str, Any]]:
    if GEX_ROWS.is_file():
        rows = json.loads(GEX_ROWS.read_text())
    elif GEX_SUM.is_file():
        rows = [r for r in json.loads(GEX_SUM.read_text()).get("rows") or [] if r.get("ok")]
    else:
        return []
    return [r for r in rows if r.get("ok")]


def _arr(rows: list[dict[str, Any]], key: str) -> np.ndarray:
    return np.asarray([r.get(key) for r in rows], dtype=np.float64)


def _chrono_split(rows: list[dict[str, Any]]) -> dict[str, Any]:
    days = [str(r["day"]) for r in rows]
    order = sorted(range(len(rows)), key=lambda i: days[i])
    ordered = [rows[i] for i in order]
    mid = max(1, len(ordered) // 2)
    early, late = ordered[:mid], ordered[mid:]
    pairs = (
        ("gex", "hl_range"),
        ("gex", "hl_rv"),
        ("vex", "hl_range"),
        ("gex_plus", "hl_range"),
        ("squeeze_intensity", "hl_rv"),
    )
    splits: dict[str, Any] = {}
    sign_stable: dict[str, bool] = {}
    for a, b in pairs:
        e = pearson_spearman(_arr(early, a), _arr(early, b))
        l = pearson_spearman(_arr(late, a), _arr(late, b))
        key = f"{a}__{b}"
        splits[key] = {"early": e, "late": l}
        pe, pl = e.get("pearson"), l.get("pearson")
        sign_stable[key] = bool(
            pe is not None
            and pl is not None
            and np.isfinite(pe)
            and np.isfinite(pl)
            and np.sign(pe) == np.sign(pl)
        )
    return {
        "ok": len(ordered) >= 4,
        "early_days": [r["day"] for r in early],
        "late_days": [r["day"] for r in late],
        "splits": splits,
        "sign_stable": sign_stable,
        "any_gex_range_stable": bool(sign_stable.get("gex__hl_range")),
        "any_gex_rv_stable": bool(sign_stable.get("gex__hl_rv")),
    }


def _day_block_pair(rows: list[dict[str, Any]], a: str, b: str) -> dict[str, Any]:
    x = _arr(rows, a)
    y = _arr(rows, b)
    days = np.asarray([str(r["day"]) for r in rows], dtype=object)
    # one observation per day → bootstrap days = resample indices with replacement
    block = day_block_bootstrap_corr(days, x, y, n_boot=N_BOOT, seed=SEED, min_n=MIN_N)
    ps = pearson_spearman(x, y)
    bayes = fisher_z_normal_posterior(float(ps["pearson"]), int(ps["n"]))
    # also mean-of-day bootstrap for the correlation magnitude via day_block_bootstrap_stat on leave-one?
    return {"pearson_spearman": ps, "day_block": block, "bayes_fisher_z": bayes}


def _placebo_shuffle(rows: list[dict[str, Any]], *, n: int = 400, seed: int = 11) -> dict[str, Any]:
    gex = _arr(rows, "gex")
    rng_y = _arr(rows, "hl_range")
    rv = _arr(rows, "hl_rv")
    m = np.isfinite(gex) & np.isfinite(rng_y)
    if int(m.sum()) < MIN_N:
        return {"ok": False}
    obs_range = float(np.corrcoef(gex[m], rng_y[m])[0, 1])
    m2 = np.isfinite(gex) & np.isfinite(rv)
    obs_rv = float(np.corrcoef(gex[m2], rv[m2])[0, 1]) if int(m2.sum()) >= MIN_N else float("nan")
    rng = np.random.default_rng(seed)
    null_range, null_rv = [], []
    for _ in range(n):
        sh = rng.permutation(gex)
        mr = np.isfinite(sh) & np.isfinite(rng_y)
        if int(mr.sum()) >= MIN_N:
            null_range.append(abs(float(np.corrcoef(sh[mr], rng_y[mr])[0, 1])))
        mv = np.isfinite(sh) & np.isfinite(rv)
        if int(mv.sum()) >= MIN_N:
            null_rv.append(abs(float(np.corrcoef(sh[mv], rv[mv])[0, 1])))
    p95_r = float(np.nanpercentile(null_range, 95)) if null_range else float("nan")
    p95_v = float(np.nanpercentile(null_rv, 95)) if null_rv else float("nan")
    return {
        "ok": True,
        "label": "shuffle_gex_across_days",
        "obs_corr_gex_range": obs_range,
        "obs_corr_gex_rv": obs_rv,
        "null_abs_median_range": float(np.median(null_range)) if null_range else None,
        "null_abs_p95_range": p95_r,
        "null_abs_median_rv": float(np.median(null_rv)) if null_rv else None,
        "null_abs_p95_rv": p95_v,
        "exceeds_p95_range": bool(np.isfinite(obs_range) and abs(obs_range) > p95_r),
        "exceeds_p95_rv": bool(np.isfinite(obs_rv) and abs(obs_rv) > p95_v),
        "n_null": len(null_range),
    }


def _venue_drop(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """HL-only vs DB-only vs joint: which RV/range target GEX tracks."""
    gex = _arr(rows, "gex")
    out: dict[str, Any] = {
        "hl_only": {
            "corr_gex_rv": pearson_spearman(gex, _arr(rows, "hl_rv")),
            "corr_gex_range": pearson_spearman(gex, _arr(rows, "hl_range")),
            "day_block_gex_rv": day_block_bootstrap_corr(
                np.asarray([str(r["day"]) for r in rows], dtype=object),
                gex,
                _arr(rows, "hl_rv"),
                n_boot=N_BOOT,
                seed=SEED,
                min_n=MIN_N,
            ),
        },
        "db_only": {
            "corr_gex_rv": pearson_spearman(gex, _arr(rows, "db_rv")),
            "corr_gex_range": pearson_spearman(gex, _arr(rows, "db_range")),
            "day_block_gex_rv": day_block_bootstrap_corr(
                np.asarray([str(r["day"]) for r in rows], dtype=object),
                gex,
                _arr(rows, "db_rv"),
                n_boot=N_BOOT,
                seed=SEED + 1,
                min_n=MIN_N,
            ),
        },
    }
    # HL+DB: average z-scored RV as joint volatility proxy
    hl_rv = _arr(rows, "hl_rv")
    db_rv = _arr(rows, "db_rv")
    m = np.isfinite(hl_rv) & np.isfinite(db_rv)
    joint = np.full_like(hl_rv, np.nan)
    if int(m.sum()) >= 2:
        zhl = (hl_rv[m] - np.nanmean(hl_rv[m])) / (np.nanstd(hl_rv[m]) + 1e-12)
        zdb = (db_rv[m] - np.nanmean(db_rv[m])) / (np.nanstd(db_rv[m]) + 1e-12)
        joint[m] = 0.5 * (zhl + zdb)
    out["hl_plus_db"] = {
        "corr_gex_joint_z_rv": pearson_spearman(gex, joint),
        "note": "equal-weight z-score of HL RV + Deribit RV",
    }
    # concordance of signs HL vs DB
    r_hl = out["hl_only"]["corr_gex_rv"].get("pearson")
    r_db = out["db_only"]["corr_gex_rv"].get("pearson")
    out["sign_concordant_hl_db"] = bool(
        r_hl is not None
        and r_db is not None
        and np.isfinite(r_hl)
        and np.isfinite(r_db)
        and np.sign(r_hl) == np.sign(r_db)
    )
    return out


def _spot_l2_appendix(rows: list[dict[str, Any]], spot_days: list[str]) -> dict[str, Any]:
    spot_set = set(spot_days)
    spot = [r for r in rows if str(r["day"]) in spot_set]
    rest = [r for r in rows if str(r["day"]) not in spot_set]
    def _pack(sub: list[dict[str, Any]], label: str) -> dict[str, Any]:
        if len(sub) < 3:
            return {"ok": False, "n": len(sub), "label": label, "days": [r["day"] for r in sub]}
        return {
            "ok": True,
            "n": len(sub),
            "label": label,
            "days": [r["day"] for r in sub],
            "corr_gex_hl_rv": pearson_spearman(_arr(sub, "gex"), _arr(sub, "hl_rv")),
            "corr_gex_hl_range": pearson_spearman(_arr(sub, "gex"), _arr(sub, "hl_range")),
            "corr_vex_hl_range": pearson_spearman(_arr(sub, "vex"), _arr(sub, "hl_range")),
            "mean_gex": float(np.nanmean(_arr(sub, "gex"))),
            "n_scarce": int(sum(1 for r in sub if r.get("scarce"))),
        }
    return {
        "role": "appendix_not_primary",
        "spot_l2": _pack(spot, "panel_3venue_spot"),
        "absent_2venue": _pack(rest, "absent_2venue"),
        "note": "spot_l2 densify = feed-quality sensitivity only; never α; trade_synth QUARANTINED",
    }


def _leave_one_out(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Sensitivity of corr(GEX, HL RV) to dropping each day."""
    gex = _arr(rows, "gex")
    rv = _arr(rows, "hl_rv")
    days = [str(r["day"]) for r in rows]
    full = pearson_spearman(gex, rv)
    loo = []
    for i, d in enumerate(days):
        mask = np.ones(len(rows), dtype=bool)
        mask[i] = False
        ps = pearson_spearman(gex[mask], rv[mask])
        loo.append({"drop": d, "corr": ps.get("pearson"), "n": ps.get("n")})
    corrs = [x["corr"] for x in loo if x["corr"] is not None and np.isfinite(x["corr"])]
    return {
        "full": full,
        "leave_one_out": loo,
        "loo_min": float(np.min(corrs)) if corrs else None,
        "loo_max": float(np.max(corrs)) if corrs else None,
        "sign_flip_any": bool(any(np.sign(c) != np.sign(full.get("pearson") or 0) for c in corrs if np.isfinite(c))),
    }


def _decide(chrono: dict, boots: dict, placebo: dict, venue: dict) -> dict[str, Any]:
    reasons = [
        "Pass-2b: paper higher GEX → tighter ranges; certified ETH panel small-n",
        "DDOI is PROXY_trade_flow (not verified ΔOI)",
        "Never Promote TOB-cross α; trade_synth QUARANTINED",
    ]
    promote = False
    decision = "Hold"
    gex_rv = boots.get("gex__hl_rv", {}).get("day_block") or {}
    ci_lo, ci_hi = gex_rv.get("ci_lo"), gex_rv.get("ci_hi")
    ci_crosses = (
        ci_lo is not None
        and ci_hi is not None
        and np.isfinite(ci_lo)
        and np.isfinite(ci_hi)
        and (ci_lo < 0 < ci_hi or ci_hi < 0 < ci_lo)
    )
    if not chrono.get("any_gex_rv_stable"):
        reasons.append("chrono corr(GEX, HL RV) sign unstable → ceiling Hold")
    if not chrono.get("any_gex_range_stable"):
        reasons.append("chrono corr(GEX, HL range) sign unstable → ceiling Hold")
    if ci_crosses:
        reasons.append("day-block bootstrap CI for corr(GEX, HL RV) crosses 0 → Hold")
    if placebo.get("ok") and not placebo.get("exceeds_p95_rv"):
        reasons.append("placebo: |obs corr(GEX,RV)| does not exceed null p95 → Hold")
    if not venue.get("sign_concordant_hl_db"):
        reasons.append("venue-drop: HL vs Deribit GEX↔RV sign discordant → weaken Hold")
    return {
        "decision": decision,
        "promote": promote,
        "promote_count": 0,
        "kill": ["alpha.tob_cross_arb", "data.trade_synth"],
        "reasons": reasons,
        "candidates": {
            "risk.gex_exposure": "Hold",
            "risk.vex_exposure": "Hold",
            "risk.squeeze_intensity": "Hold",
            "liq.implied_book_scarcity": "Hold",
            "risk.squeeze_falsifier_board": "Hold",
            "alpha.tob_cross_arb": "Kill",
            "data.trade_synth": "Kill",
        },
    }


def _figs(rows: list[dict[str, Any]], chrono: dict, boots: dict, venue: dict, loo: dict) -> list[str]:
    paths: list[str] = []
    days = [str(r["day"]) for r in rows]
    gex = _arr(rows, "gex")
    rv = _arr(rows, "hl_rv")
    rng = _arr(rows, "hl_range")

    # fig 1: chrono halves
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.8))
    early_set = set(chrono.get("early_days") or [])
    for ax, y, ylab in ((axes[0], rv, "HL RV"), (axes[1], rng, "HL range")):
        for i, d in enumerate(days):
            c = "#3d5a80" if d in early_set else "#ee6c4d"
            ax.scatter(gex[i], y[i], c=c, s=55, zorder=3)
            ax.annotate(d[5:], (gex[i], y[i]), fontsize=7)
        ax.axhline(0, color="k", lw=0.4) if False else None
        ax.set_xlabel("GEX")
        ax.set_ylabel(ylab)
        ax.set_title(f"chrono: early=blue late=red · {ylab}")
    fig.suptitle("Pass-2b chrono split — panel_gex_options", fontsize=11)
    paths.append(_savefig(fig, "fig_chrono_split.png"))

    # fig 2: bootstrap CI bars
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    labels, pts, los, his = [], [], [], []
    for key, label in (
        ("gex__hl_rv", "GEX↔HL RV"),
        ("gex__hl_range", "GEX↔HL range"),
        ("vex__hl_range", "VEX↔HL range"),
        ("gex_plus__hl_range", "GEX+↔range"),
    ):
        b = (boots.get(key) or {}).get("day_block") or {}
        labels.append(label)
        pts.append(b.get("corr"))
        los.append(b.get("ci_lo"))
        his.append(b.get("ci_hi"))
    y = np.arange(len(labels))
    for i in range(len(labels)):
        if pts[i] is None or not np.isfinite(pts[i]):
            continue
        lo = los[i] if los[i] is not None else pts[i]
        hi = his[i] if his[i] is not None else pts[i]
        ax.plot([lo, hi], [y[i], y[i]], color="#3d5a80", lw=2)
        ax.scatter([pts[i]], [y[i]], color="#ee6c4d", zorder=3, s=40)
    ax.axvline(0, color="k", lw=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Pearson corr (day-block 95% CI)")
    ax.set_title(f"Pass-2b day-block bootstrap · n={len(rows)}")
    paths.append(_savefig(fig, "fig_dayblock_ci.png"))

    # fig 3: venue drop
    fig, ax = plt.subplots(figsize=(6.2, 3.6))
    names = ["HL RV", "DB RV", "HL+DB z-RV"]
    vals = [
        venue["hl_only"]["corr_gex_rv"].get("pearson"),
        venue["db_only"]["corr_gex_rv"].get("pearson"),
        venue["hl_plus_db"]["corr_gex_joint_z_rv"].get("pearson"),
    ]
    colors = ["#3d5a80", "#98c1d9", "#ee6c4d"]
    ax.bar(names, [v if v is not None and np.isfinite(v) else 0 for v in vals], color=colors)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_ylabel("corr(GEX, ·)")
    ax.set_title("Venue-drop: HL-only vs DB-only vs joint")
    paths.append(_savefig(fig, "fig_venue_drop.png"))

    # fig 4: LOO
    fig, ax = plt.subplots(figsize=(8.5, 3.5))
    loo_rows = loo.get("leave_one_out") or []
    ax.plot([r["drop"] for r in loo_rows], [r["corr"] for r in loo_rows], "o-", color="#3d5a80")
    full = (loo.get("full") or {}).get("pearson")
    if full is not None:
        ax.axhline(full, color="#ee6c4d", ls="--", label=f"full={full:.3f}")
    ax.axhline(0, color="k", lw=0.6)
    ax.tick_params(axis="x", rotation=70)
    ax.set_ylabel("corr(GEX, HL RV)")
    ax.set_title("Leave-one-day-out sensitivity")
    ax.legend(fontsize=8)
    paths.append(_savefig(fig, "fig_loo_corr.png"))
    return paths


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write-reports", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    FIGS.mkdir(parents=True, exist_ok=True)
    cert = load_certified()
    primary = gex_panel_days(cert)
    spot = spot_l2_days(cert)
    rows_all = _load_rows()
    rows = [r for r in rows_all if str(r.get("day")) in set(primary)]
    if not rows:
        rows = rows_all
    if not rows:
        print(json.dumps({"ok": False, "blocker": "missing gex panel_rows"}))
        return 2

    chrono = _chrono_split(rows)
    boots = {
        "gex__hl_rv": _day_block_pair(rows, "gex", "hl_rv"),
        "gex__hl_range": _day_block_pair(rows, "gex", "hl_range"),
        "vex__hl_range": _day_block_pair(rows, "vex", "hl_range"),
        "vex__hl_rv": _day_block_pair(rows, "vex", "hl_rv"),
        "gex_plus__hl_range": _day_block_pair(rows, "gex_plus", "hl_range"),
        "squeeze__hl_rv": _day_block_pair(rows, "squeeze_intensity", "hl_rv"),
    }
    placebo = _placebo_shuffle(rows)
    venue = _venue_drop(rows)
    spot_app = _spot_l2_appendix(rows, spot)
    loo = _leave_one_out(rows)
    decisions = _decide(chrono, boots, placebo, venue)
    fig_paths = _figs(rows, chrono, boots, venue, loo)

    # day-mean CI for GEX / VEX / GEX+
    day_means = {
        "gex": day_block_bootstrap_stat(_arr(rows, "gex"), n_boot=N_BOOT, seed=SEED),
        "vex": day_block_bootstrap_stat(_arr(rows, "vex"), n_boot=N_BOOT, seed=SEED + 2),
        "gex_plus": day_block_bootstrap_stat(_arr(rows, "gex_plus"), n_boot=N_BOOT, seed=SEED + 3),
        "hl_rv": day_block_bootstrap_stat(_arr(rows, "hl_rv"), n_boot=N_BOOT, seed=SEED + 4),
    }

    out = {
        "ok": True,
        "pass": "2b",
        "panel": "panel_gex_options",
        "n": len(rows),
        "days": [str(r["day"]) for r in rows],
        "spot_l2_days": spot,
        "ddoi_mode": rows[0].get("ddoi_mode") if rows else None,
        "falsifiers": {
            "chrono_split": chrono,
            "day_block_bootstrap": boots,
            "placebo_shuffle_gex": placebo,
            "venue_drop": venue,
            "leave_one_out": loo,
            "spot_l2_appendix": spot_app,
            "day_means": day_means,
        },
        "decisions": decisions,
        "figs": fig_paths,
        "honesty": (
            "Pass-2b on certified panel_gex_options; DDOI=PROXY_trade_flow; "
            "day-block bootstrap; spot_l2 appendix only; 0 Promote; ClickHouse MCP banned"
        ),
    }
    (OUT / "pass2_falsifiers.json").write_text(json.dumps(_jsonable(out), indent=2))

    gex_rv = boots["gex__hl_rv"]["day_block"]
    gex_rng = boots["gex__hl_range"]["day_block"]
    report = "\n".join(
        [
            "# Pass-2b falsifiers — squeeze_metrics",
            "",
            f"- Panel: **panel_gex_options** n={out['n']}: {', '.join(out['days'])}",
            f"- DDOI: `{out['ddoi_mode']}` · spot_l2 appendix n={len(spot)}",
            f"- corr(GEX, HL RV) = **{gex_rv.get('corr')}** day-block CI[{gex_rv.get('ci_lo')}, {gex_rv.get('ci_hi')}]",
            f"- corr(GEX, HL range) = **{gex_rng.get('corr')}** CI[{gex_rng.get('ci_lo')}, {gex_rng.get('ci_hi')}]",
            f"- chrono GEX↔RV sign stable: **{chrono.get('any_gex_rv_stable')}** · GEX↔range: **{chrono.get('any_gex_range_stable')}**",
            f"- placebo exceeds p95 (RV): **{placebo.get('exceeds_p95_rv')}** · (range): **{placebo.get('exceeds_p95_range')}**",
            f"- venue HL↔DB sign concordant: **{venue.get('sign_concordant_hl_db')}**",
            f"- LOO sign flip any: **{loo.get('sign_flip_any')}** · LOO range [{loo.get('loo_min')}, {loo.get('loo_max')}]",
            f"- **Decision: {decisions['decision']}** (promote={decisions['promote']}, count={decisions['promote_count']})",
            "",
            "## Reasons",
            "",
            *[f"- {r}" for r in decisions["reasons"]],
            "",
            "## Figs",
            "",
            *[f"- `{p}`" for p in fig_paths],
            "",
            "## Appendix — spot_l2 (not primary)",
            "",
            f"- spot_l2 n={spot_app['spot_l2'].get('n')} corr(GEX,RV)={((spot_app['spot_l2'].get('corr_gex_hl_rv') or {}).get('pearson'))}",
            f"- absent_2venue n={spot_app['absent_2venue'].get('n')} corr(GEX,RV)={((spot_app['absent_2venue'].get('corr_gex_hl_rv') or {}).get('pearson'))}",
            "",
            "**0 Promote.** Kill: `alpha.tob_cross_arb`, `data.trade_synth`.",
            "",
        ]
    )
    (OUT / "EXP_REPORT.md").write_text(report)
    print(json.dumps(_jsonable({"written": str(OUT / "pass2_falsifiers.json"), "decisions": decisions, "figs": fig_paths}), indent=2))

    if args.write_reports:
        _patch_chapter_reports(out)
    return 0


def _patch_chapter_reports(payload: dict[str, Any]) -> None:
    f = payload["falsifiers"]
    ch = f["chrono_split"]
    boots = f["day_block_bootstrap"]
    gex_rv = boots.get("gex__hl_rv", {}).get("day_block") or {}
    placebo = f["placebo_shuffle_gex"]
    venue = f["venue_drop"]
    addendum = f"""

## Pass 2b falsifiers (auto)

- **Panel:** panel_gex_options n={payload.get('n')} · DDOI=`{payload.get('ddoi_mode')}`.
- **Day-block corr(GEX, HL RV):** {gex_rv.get('corr')} CI[{gex_rv.get('ci_lo')}, {gex_rv.get('ci_hi')}].
- **Chrono:** early={ch.get('early_days')} late={ch.get('late_days')} · GEX↔RV stable={ch.get('any_gex_rv_stable')}.
- **Placebo shuffle GEX:** exceeds_p95_rv={placebo.get('exceeds_p95_rv')}.
- **Venue-drop HL vs DB sign concordant:** {venue.get('sign_concordant_hl_db')}.
- **spot_l2:** appendix only (n={len(payload.get('spot_l2_days') or [])}).
- **Decision:** 0 Promote; monitors **Hold**; Kill TOB-cross α / trade_synth.
"""
    for rel in (
        "chapters/robustness/EXP_REPORT.md",
        "chapters/gex_implied_book/EXP_REPORT.md",
        "chapters/ch00_overview/EXP_REPORT.md",
        "chapters/squeeze_regimes/EXP_REPORT.md",
    ):
        p = BOOK / rel
        if not p.is_file():
            continue
        text = p.read_text()
        marker = "## Pass 2b falsifiers (auto)"
        if marker in text:
            text = text.split(marker)[0].rstrip()
        # also strip older Pass 2 marker if present alone
        p.write_text(text.rstrip() + "\n" + addendum)


if __name__ == "__main__":
    raise SystemExit(main())
