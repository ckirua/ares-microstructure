from __future__ import annotations
#!/usr/bin/env python3
"""Dump desk-quality PNG figures + package JSON for mm_confr_viewpoints.

Reads out/pass1 + out/pass2 artifacts; optionally reloads TOB for constraint
hist / relax-event windows. Writes:

  out/<pkg>/figs/*.png
  out/<pkg>/*.json  (rich slices for chapter notebooks)

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

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(os.environ.get('WAREHOUSE_SRC') or ((Path(os.environ.get('WAREHOUSE_ROOT') or (Path.home() / 'lab' / 'lab-n2070' / 'warehouse')) / 'src')))))
sys.path.insert(0, str(Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb')) / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ares_micro.book.ticksize import (  # noqa: E402
    constraint_flip_windows,
    expected_sign_matrix,
    fama_macbeth_slope,
    fm_ci_from_slopes,
    liquid_book_classifier,
    markout_by_rel_tick_quartile,
    relative_tick,
    spread_in_ticks,
    tercile_interaction,
    tick_constrained,
)

VENUE_COLORS = {
    "hyperliquid": "#1f77b4",
    "deribit": "#ff7f0e",
    "kraken": "#2ca02c",
}
VENUE_SHORT = {"hyperliquid": "HL", "deribit": "DB", "kraken": "KR"}


def _json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str))


def _savefig(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return path


def _load_pass1(name: str) -> Any:
    return json.loads((BOOK / "out" / "pass1" / name).read_text())


def _load_pass2(name: str) -> Any:
    p = BOOK / "out" / "pass2" / name
    if not p.exists():
        return None
    return json.loads(p.read_text())


def _flat_rows(panel: dict) -> list[dict]:
    out = []
    for r in panel.get("rows") or []:
        if r.get("error"):
            continue
        out.append(
            {
                "day": r["day"],
                "venue": r["venue"],
                "symbol": r.get("symbol"),
                "complete": bool((r.get("completeness") or {}).get("complete")),
                "coverage": (r.get("completeness") or {}).get("coverage"),
                "n_trades": r.get("n_trades") or (r.get("completeness") or {}).get("n"),
                "tob_ok": bool(r.get("tob_ok")),
                "tob_source": r.get("tob_source"),
                "tau": r.get("tau"),
                "tau_source": r.get("tau_source"),
                "rel_tick": r.get("rel_tick"),
                "rel_tick_bps": r.get("rel_tick_bps"),
                "quoted_spread_bps": r.get("quoted_spread_bps"),
                "relative_spread": r.get("relative_spread"),
                "bbo_depth": r.get("bbo_depth"),
                "volume": r.get("volume"),
                "vol": r.get("vol"),
                "intensity": r.get("intensity"),
                "markout_1s_bps": r.get("markout_1s_bps"),
                "ofi_corr": r.get("ofi_corr"),
                "frac_constrained_2tick": (r.get("constraint") or {}).get("frac_constrained_2tick"),
                "frac_one_tick": (r.get("constraint") or {}).get("frac_one_tick"),
                "spread_leeway": (r.get("constraint") or {}).get("spread_leeway"),
                "median_spread_ticks": (r.get("constraint") or {}).get("median_spread_ticks"),
                "undercut_rate": (r.get("undercut") or {}).get("undercut_rate"),
                "grid_pressure_std": (r.get("grid") or {}).get("pressure_std"),
                "synth": "trade_synth" in str(r.get("tob_source") or ""),
            }
        )
    return out


# ── ch00 coverage ──────────────────────────────────────────────────────────


def fig_coverage(comp: list, flat: list[dict]) -> Path:
    days = sorted({c["day"] for c in comp})
    venues = ["hyperliquid", "deribit", "kraken"]
    mat = np.full((len(venues), len(days)), np.nan)
    annot = [[""] * len(days) for _ in venues]
    for i, v in enumerate(venues):
        for j, d in enumerate(days):
            row = next((c for c in comp if c["venue"] == v and c["day"] == d), None)
            if not row:
                continue
            cov = float(row.get("coverage") or 0)
            mat[i, j] = cov
            flags = []
            if row.get("complete"):
                flags.append("C")
            if row.get("tob_ok"):
                flags.append("T")
            if "trade_synth" in str(
                next((f["tob_source"] for f in flat if f["venue"] == v and f["day"] == d), "")
            ):
                flags.append("S")
            annot[i][j] = f"{cov:.0%}\n{''.join(flags)}"
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    im = ax.imshow(mat, aspect="auto", cmap="YlGn", vmin=0, vmax=1)
    ax.set_xticks(range(len(days)))
    ax.set_xticklabels([d[5:] for d in days])
    ax.set_yticks(range(len(venues)))
    ax.set_yticklabels([VENUE_SHORT[v] for v in venues])
    for i in range(len(venues)):
        for j in range(len(days)):
            ax.text(j, i, annot[i][j], ha="center", va="center", fontsize=8)
    ax.set_title("Sample coverage — C=complete T=TOB S=trade_synth")
    fig.colorbar(im, ax=ax, fraction=0.046, label="coverage")
    path = BOOK / "out" / "ch00_overview" / "figs" / "coverage.png"
    return _savefig(fig, path)


# ── emp_predictions ────────────────────────────────────────────────────────


def fig_sign_matrix(matrix: dict) -> Path:
    # liquid / less_liquid × metrics for key regimes
    regimes = [
        "large_abs_reduction",
        "small_abs_reduction",
        "large_abs_increase",
        "rel_tick_up",
        "rel_tick_down",
    ]
    metrics = ["quoted_spread", "relative_spread", "bbo_depth", "total_depth", "volume", "welfare"]
    books = ["liquid", "less_liquid"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    cmap = plt.cm.RdYlGn  # type: ignore[attr-defined]
    for ax, book in zip(axes, books):
        M = np.zeros((len(regimes), len(metrics)))
        for i, r in enumerate(regimes):
            for j, m in enumerate(metrics):
                M[i, j] = matrix["matrix"].get(r, {}).get(book, {}).get(m, 0)
        im = ax.imshow(M, cmap=cmap, vmin=-1, vmax=1, aspect="auto")
        ax.set_xticks(range(len(metrics)))
        ax.set_xticklabels(metrics, rotation=35, ha="right", fontsize=8)
        ax.set_yticks(range(len(regimes)))
        ax.set_yticklabels(regimes, fontsize=8)
        ax.set_title(f"book={book}")
        for i in range(len(regimes)):
            for j in range(len(metrics)):
                val = int(M[i, j])
                # Kill welfare visually
                txt = "KILL" if metrics[j] == "welfare" else str(val)
                ax.text(j, i, txt, ha="center", va="center", fontsize=7, color="k" if abs(val) < 1 else "w")
    fig.suptitle("Expected-sign matrix (deck pp.20–29) — welfare = Kill", y=1.02)
    fig.colorbar(im, ax=axes.ravel().tolist(), fraction=0.025, pad=0.02, label="sign")
    path = BOOK / "out" / "emp_predictions" / "figs" / "sign_matrix.png"
    return _savefig(fig, path)


def fig_scorecard(score: dict, gates: dict | None) -> Path:
    detail = (score.get("scorecard") or score).get("detail") or score.get("detail") or []
    if not detail and "observed" in score:
        # rebuild match from scorecard
        detail = (score.get("scorecard") or {}).get("detail") or []
    labels = [f"{d.get('metric')}" for d in detail]
    exp = [d.get("expected", 0) for d in detail]
    obs = [d.get("obs_sign", 0) for d in detail]
    match = [d.get("match") for d in detail]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    x = np.arange(len(labels))
    w = 0.35
    ax.bar(x - w / 2, exp, w, label="expected", color="#4c72b0")
    ax.bar(x + w / 2, obs, w, label="observed", color="#dd8452")
    for i, m in enumerate(match):
        if m is True:
            ax.annotate("✓", (x[i], max(exp[i], obs[i]) + 0.15), ha="center", color="green", fontsize=12)
        elif m is False:
            ax.annotate("✗", (x[i], max(exp[i], obs[i]) + 0.15), ha="center", color="red", fontsize=12)
        else:
            ax.annotate("skip", (x[i], 1.15), ha="center", color="gray", fontsize=8)
    sc = score.get("scorecard") or score
    hr = sc.get("hit_rate", float("nan"))
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.set_ylim(-1.4, 1.5)
    ax.set_ylabel("sign (−1/0/+1)")
    ax.set_title(f"Empirical sign scorecard vs deck (rel_tick_up) — hit_rate={hr:.2f} → Kill tradable")
    ax.legend(fontsize=8)
    ax.grid(True, axis="y", alpha=0.3)
    # Kill badge
    ax.text(
        0.98,
        0.05,
        "KILL as tradable\n(welfare/SEC out of scope)",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=8,
        color="#a50f15",
        bbox=dict(boxstyle="round", facecolor="#fee0d2", edgecolor="#a50f15", alpha=0.9),
    )
    path = BOOK / "out" / "emp_predictions" / "figs" / "scorecard.png"
    return _savefig(fig, path)


# ── rel_tick_panel ─────────────────────────────────────────────────────────


def fig_scatter_mq(flat: list[dict]) -> Path:
    metrics = [
        ("quoted_spread_bps", "quoted spread (bps)"),
        ("bbo_depth", "BBO depth"),
        ("volume", "volume (coin)"),
        ("markout_1s_bps", "markout 1s (bps)"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(10, 7.5))
    axes = axes.ravel()
    for ax, (key, ylab) in zip(axes, metrics):
        for v in ("hyperliquid", "deribit", "kraken"):
            sub = [r for r in flat if r["venue"] == v and r.get("tob_ok")]
            xs = [r["rel_tick"] for r in sub if np.isfinite(r.get("rel_tick") or np.nan)]
            ys = []
            xs2 = []
            for r in sub:
                try:
                    x, y = float(r["rel_tick"]), float(r.get(key))
                except (TypeError, ValueError):
                    continue
                if np.isfinite(x) and np.isfinite(y):
                    xs2.append(x)
                    ys.append(y)
            if not xs2:
                continue
            marker = "x" if any(r.get("synth") for r in sub) else "o"
            ax.scatter(
                xs2,
                ys,
                c=VENUE_COLORS[v],
                label=f"{VENUE_SHORT[v]}{' (synth)' if any(r.get('synth') for r in sub) else ''}",
                alpha=0.85,
                s=55,
                marker=marker,
            )
        ax.set_xlabel("rel_tick τ/mid")
        ax.set_ylabel(ylab)
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=7)
        if key == "bbo_depth":
            ax.set_yscale("symlog", linthresh=1e3)
        if key == "volume":
            ax.set_yscale("log")
    fig.suptitle("Relative tick vs MQ — venue-colored (Kraken × = trade_synth TOB)", y=1.01)
    path = BOOK / "out" / "rel_tick_panel" / "figs" / "scatter_mq.png"
    return _savefig(fig, path)


def fig_fm_coefs(fm: dict) -> Path:
    keys = [
        ("quoted_spread_bps", "qspread"),
        ("relative_spread", "rel_spread"),
        ("volume", "volume"),
        ("hour_quoted_spread_bps", "hour qspread"),
        ("hour_bbo_depth", "hour depth"),
    ]
    labels, means, los, his = [], [], [], []
    for k, lab in keys:
        block = fm.get(k) or {}
        slopes = block.get("slopes") or []
        ci = fm_ci_from_slopes(slopes)
        # scale volume / depth for readability
        scale = 1.0
        if "volume" in k:
            scale = 1e-12
            lab = lab + " ×1e−12"
        if "depth" in k:
            scale = 1e-16
            lab = lab + " ×1e−16"
        labels.append(lab)
        means.append(ci["mean"] * scale if np.isfinite(ci["mean"]) else np.nan)
        los.append(ci["lo"] * scale if np.isfinite(ci["lo"]) else np.nan)
        his.append(ci["hi"] * scale if np.isfinite(ci["hi"]) else np.nan)
    fig, ax = plt.subplots(figsize=(8, 3.8))
    x = np.arange(len(labels))
    yerr = np.array(
        [
            [m - lo if np.isfinite(m) and np.isfinite(lo) else 0 for m, lo in zip(means, los)],
            [hi - m if np.isfinite(m) and np.isfinite(hi) else 0 for m, hi in zip(means, his)],
        ]
    )
    ax.bar(x, means, color="#4c72b0", alpha=0.85, yerr=yerr, capsize=4, ecolor="#333")
    ax.axhline(0, color="k", lw=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.set_ylabel("FM mean slope (±95% CI)")
    ax.set_title("Fama–MacBeth coefs: MQ ~ rel_tick (day/hour panels)")
    ax.grid(True, axis="y", alpha=0.3)
    path = BOOK / "out" / "rel_tick_panel" / "figs" / "fm_coefs.png"
    return _savefig(fig, path)


def fig_time_split(flat: list[dict], gates: dict | None) -> Path:
    days = sorted({r["day"] for r in flat})
    mid = max(1, len(days) // 2)
    early, late = set(days[:mid]), set(days[mid:])
    fm_e = fama_macbeth_slope([r for r in flat if r["day"] in early and r.get("tob_ok")], y_key="quoted_spread_bps", x_key="rel_tick")
    fm_l = fama_macbeth_slope([r for r in flat if r["day"] in late and r.get("tob_ok")], y_key="quoted_spread_bps", x_key="rel_tick")
    # also Spearman early/late
    def _rho(sub):
        xs, ys = [], []
        for r in sub:
            try:
                x, y = float(r["rel_tick"]), float(r["quoted_spread_bps"])
            except (TypeError, ValueError):
                continue
            if np.isfinite(x) and np.isfinite(y):
                xs.append(x)
                ys.append(y)
        if len(xs) < 3:
            return float("nan")
        from ares_micro.stats import spearman_r

        return spearman_r(np.asarray(xs), np.asarray(ys))

    rho_e = _rho([r for r in flat if r["day"] in early and r.get("tob_ok")])
    rho_l = _rho([r for r in flat if r["day"] in late and r.get("tob_ok")])
    # markout by quartile
    mq = markout_by_rel_tick_quartile([r for r in flat if r.get("tob_ok")])

    fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.6))
    # FM slopes early/late
    ax = axes[0]
    labs = ["early", "late"]
    vals = [fm_e.get("mean_slope", np.nan), fm_l.get("mean_slope", np.nan)]
    ax.bar(labs, vals, color=["#4c72b0", "#dd8452"])
    ax.axhline(0, color="k", lw=0.6)
    ax.set_title(f"FM slope qspread\nearly={sorted(early)}\nlate={sorted(late)}", fontsize=9)
    ax.set_ylabel("mean slope")
    ax.grid(True, axis="y", alpha=0.3)

    ax = axes[1]
    ax.bar(labs, [rho_e, rho_l], color=["#4c72b0", "#dd8452"])
    ax.axhline(0, color="k", lw=0.6)
    ci = (gates or {}).get("rho_ci") or {}
    ax.set_title(f"Spearman ρ(rel_tick, spread)\nfull CI95=[{ci.get('lo', float('nan')):.2f},{ci.get('hi', float('nan')):.2f}]", fontsize=9)
    ax.grid(True, axis="y", alpha=0.3)

    ax = axes[2]
    if mq.get("means"):
        ax.bar(range(len(mq["means"])), mq["means"], color="#55a868")
        ax.set_xticks(range(len(mq["means"])))
        ax.set_xticklabels([f"Q{i+1}\nn={n}" for i, n in enumerate(mq["ns"])], fontsize=8)
        ax.axhline(0, color="k", lw=0.6)
        ax.set_ylabel("mean markout 1s (bps)")
        ax.set_title("Markout by rel_tick quartile", fontsize=9)
        ax.grid(True, axis="y", alpha=0.3)
    else:
        ax.text(0.5, 0.5, "insufficient markout", ha="center", va="center", transform=ax.transAxes)
    fig.suptitle("Time-split falsifier + markout info lens", y=1.05)
    path = BOOK / "out" / "rel_tick_panel" / "figs" / "time_split.png"
    return _savefig(fig, path)


# ── tick_constraint ────────────────────────────────────────────────────────


def fig_frac_constrained(flat: list[dict]) -> Path:
    days = sorted({r["day"] for r in flat})
    venues = ["hyperliquid", "deribit", "kraken"]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    x = np.arange(len(days))
    w = 0.25
    for i, v in enumerate(venues):
        ys = []
        for d in days:
            row = next((r for r in flat if r["venue"] == v and r["day"] == d), None)
            val = float(row["frac_constrained_2tick"]) if row and np.isfinite(row.get("frac_constrained_2tick") or np.nan) else np.nan
            ys.append(val)
        bars = ax.bar(x + (i - 1) * w, ys, w, label=VENUE_SHORT[v] + (" synth" if v == "kraken" else ""), color=VENUE_COLORS[v], alpha=0.85)
        # hatch synth
        if v == "kraken":
            for b in bars:
                b.set_hatch("//")
    ax.set_xticks(x)
    ax.set_xticklabels([d[5:] for d in days])
    ax.set_ylabel("frac spread ≤ 2 ticks")
    ax.set_ylim(0, 1.05)
    ax.set_title("Tick-constrained fraction over time by venue (Kraken hatch = trade_synth)")
    ax.legend(fontsize=8)
    ax.grid(True, axis="y", alpha=0.3)
    path = BOOK / "out" / "tick_constraint" / "figs" / "frac_constrained.png"
    return _savefig(fig, path)


def _reload_constraint_series(panel: dict, *, max_days: int = 3) -> dict[str, Any]:
    """Reload TOB to build spread-tick hist + relax event windows."""
    from _data import ensure_env, load_tob_any

    ensure_env()
    series = []
    hist_by_venue: dict[str, list[float]] = {}
    flip_summary = []
    days = sorted({r["day"] for r in panel["rows"]})[:max_days]
    for r in panel["rows"]:
        if r["day"] not in days or not r.get("tob_ok"):
            continue
        venue, day, symbol = r["venue"], r["day"], r.get("symbol") or panel.get("symbol") or "ETH"
        tau = float(r.get("tau") or np.nan)
        try:
            tob = load_tob_any(venue, symbol, day)
        except Exception as exc:  # noqa: BLE001
            series.append({"venue": venue, "day": day, "error": str(exc)})
            continue
        st = spread_in_ticks(tob["bid"], tob["ask"], tau)
        st_f = st[np.isfinite(st)]
        hist_by_venue.setdefault(venue, []).extend(st_f[:: max(1, st_f.size // 5000)].tolist())
        constrained = tick_constrained(st, max_ticks=2.0)
        if isinstance(constrained, bool):
            continue
        # intensity proxy: quote update rate in rolling windows via ones
        ones = np.ones(st.size, dtype=np.float64)
        # crude ofi: signed depth change
        bs = np.asarray(tob["bid_sz"], dtype=np.float64)
        az = np.asarray(tob["ask_sz"], dtype=np.float64)
        ofi_proxy = np.diff(bs - az, prepend=bs[0] - az[0])
        flips = constraint_flip_windows(tob["ts"], constrained, intensity=ones, ofi=ofi_proxy)
        # hourly frac
        hours = np.asarray(tob["ts"], dtype=np.int64) // 3_600_000_000_000
        hour_frac = []
        for h in np.unique(hours):
            m = hours == h
            c = constrained[m]
            hour_frac.append({"hour_id": int(h), "frac": float(np.mean(c)) if c.size else float("nan"), "n": int(c.size)})
        series.append(
            {
                "venue": venue,
                "day": day,
                "tob_source": tob.get("source"),
                "n": int(st_f.size),
                "median_spread_ticks": float(np.median(st_f)) if st_f.size else float("nan"),
                "frac_constrained": float(np.mean(constrained)) if constrained.size else float("nan"),
                "hour_frac": hour_frac,
                "flips": flips,
                "synth": "trade_synth" in str(tob.get("source") or ""),
            }
        )
        flip_summary.append({"venue": venue, "day": day, **{k: flips[k] for k in ("n_relax", "n_tighten", "relax_intensity_delta", "relax_ofi_delta")}})
    return {"series": series, "hist_by_venue": {k: v[:20000] for k, v in hist_by_venue.items()}, "flip_summary": flip_summary}


def fig_spread_ticks_hist(constraint_art: dict) -> Path:
    fig, ax = plt.subplots(figsize=(8, 3.8))
    for v, vals in (constraint_art.get("hist_by_venue") or {}).items():
        a = np.asarray(vals, dtype=np.float64)
        a = a[np.isfinite(a) & (a > 0) & (a < 50)]
        if a.size == 0:
            continue
        ax.hist(
            a,
            bins=np.linspace(0, 20, 41),
            alpha=0.45,
            label=VENUE_SHORT.get(v, v) + (" synth" if v == "kraken" else ""),
            color=VENUE_COLORS.get(v, None),
            density=True,
        )
    ax.axvline(1.0, color="k", ls="--", lw=0.8, label="1 tick")
    ax.axvline(2.0, color="gray", ls=":", lw=0.8, label="2 tick")
    ax.set_xlabel("spread in ticks")
    ax.set_ylabel("density")
    ax.set_title("Spread-in-ticks histogram by venue (Kraken = trade_synth BBO)")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    path = BOOK / "out" / "tick_constraint" / "figs" / "spread_ticks_hist.png"
    return _savefig(fig, path)


def fig_relax_events(constraint_art: dict) -> Path:
    rows = constraint_art.get("flip_summary") or []
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    # counts
    ax = axes[0]
    venues = sorted({r["venue"] for r in rows})
    x = np.arange(len(venues))
    relax = [sum(r["n_relax"] for r in rows if r["venue"] == v) for v in venues]
    tight = [sum(r["n_tighten"] for r in rows if r["venue"] == v) for v in venues]
    ax.bar(x - 0.2, relax, 0.4, label="relax (C→U)", color="#55a868")
    ax.bar(x + 0.2, tight, 0.4, label="tighten (U→C)", color="#c44e52")
    ax.set_xticks(x)
    ax.set_xticklabels([VENUE_SHORT.get(v, v) for v in venues])
    ax.set_ylabel("event count")
    ax.set_title("Constraint flip counts")
    ax.legend(fontsize=8)
    ax.grid(True, axis="y", alpha=0.3)

    ax = axes[1]
    # hourly frac over time for HL (most constrained)
    series = [s for s in constraint_art.get("series") or [] if s.get("venue") == "hyperliquid" and s.get("hour_frac")]
    for s in series:
        hf = s["hour_frac"]
        xs = list(range(len(hf)))
        ys = [h["frac"] for h in hf]
        ax.plot(xs, ys, "o-", label=s["day"][5:], alpha=0.8)
    ax.set_xlabel("UTC hour index (within day)")
    ax.set_ylabel("frac constrained")
    ax.set_ylim(0, 1.05)
    ax.set_title("HL constraint fraction over day (relax windows rare)")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)
    fig.suptitle("Undercutting / relax event windows", y=1.02)
    path = BOOK / "out" / "tick_constraint" / "figs" / "relax_events.png"
    return _savefig(fig, path)


# ── liq_book_split ─────────────────────────────────────────────────────────


def fig_tercile_interaction(flat: list[dict], liq_art: dict | None) -> Path:
    tob = [r for r in flat if r.get("tob_ok") and np.isfinite(r.get("quoted_spread_bps") or np.nan)]
    classified = liquid_book_classifier(tob, by="quoted_spread_bps")
    inter = tercile_interaction(classified, x_key="rel_tick", y_key="quoted_spread_bps")
    # also depth
    inter_d = tercile_interaction(classified, x_key="rel_tick", y_key="volume")

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, inter_obj, ylab in (
        (axes[0], inter, "mean quoted spread (bps)"),
        (axes[1], inter_d, "mean volume"),
    ):
        books = ["liquid", "less_liquid"]
        for book, ls in zip(books, ["-", "--"]):
            cells = [c for c in inter_obj["cells"] if c["book"] == book]
            cells = sorted(cells, key=lambda c: c["x_tercile"])
            xs = [c["x_tercile"] for c in cells]
            ys = [c["mean_y"] for c in cells]
            ns = [c["n"] for c in cells]
            ax.plot(xs, ys, "o" + ls, label=f"{book} (n={sum(ns)})")
            for x, y, n in zip(xs, ys, ns):
                if np.isfinite(y):
                    ax.annotate(str(n), (x, y), textcoords="offset points", xytext=(0, 6), fontsize=7, ha="center")
        ax.set_xticks([0, 1, 2])
        ax.set_xticklabels(["low τ/mid", "mid", "high τ/mid"])
        ax.set_ylabel(ylab)
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        if ylab.startswith("mean volume"):
            ax.set_yscale("log")
    fig.suptitle("Tercile interaction: rel_tick × liquid/thin → MQ", y=1.02)
    path = BOOK / "out" / "liq_book_split" / "figs" / "tercile_interaction.png"
    return _savefig(fig, path)


def fig_placebo(flat: list[dict], liq_art: dict | None) -> Path:
    from ares_micro.stats import spearman_r

    tob = [r for r in flat if r.get("tob_ok")]
    # true channel
    xs = np.array([float(r["rel_tick"]) for r in tob if np.isfinite(r.get("rel_tick") or np.nan)])
    ys = np.array([float(r["quoted_spread_bps"]) for r in tob if np.isfinite(r.get("quoted_spread_bps") or np.nan)])
    n = min(xs.size, ys.size)
    rho_true = spearman_r(xs[:n], ys[:n]) if n >= 3 else float("nan")
    # placebo: vol
    xv = np.array([float(r["vol"]) for r in tob if np.isfinite(r.get("vol") or np.nan)])
    yv = np.array([float(r["quoted_spread_bps"]) for r in tob if np.isfinite(r.get("quoted_spread_bps") or np.nan)])
    n2 = min(xv.size, yv.size)
    rho_plac = spearman_r(xv[:n2], yv[:n2]) if n2 >= 3 else float("nan")
    # shuffle placebo
    rng = np.random.default_rng(7)
    boots = []
    if n >= 3:
        for _ in range(400):
            boots.append(spearman_r(xs[:n], ys[:n][rng.permutation(n)]))
    boots_a = np.asarray(boots)
    boots_a = boots_a[np.isfinite(boots_a)]

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    ax = axes[0]
    ax.bar(["rel_tick→spread", "vol→spread (placebo)"], [rho_true, rho_plac], color=["#4c72b0", "#999999"])
    ax.axhline(0, color="k", lw=0.6)
    ax.set_ylabel("Spearman ρ")
    ax.set_title("Channel vs placebo driver")
    ax.grid(True, axis="y", alpha=0.3)

    ax = axes[1]
    if boots_a.size:
        ax.hist(boots_a, bins=30, color="#cccccc", edgecolor="white", label="shuffle null")
        ax.axvline(rho_true, color="#4c72b0", lw=2, label=f"observed ρ={rho_true:.2f}")
        ax.legend(fontsize=8)
    ax.set_xlabel("ρ")
    ax.set_title("Placebo falsifier — shuffle y | x fixed")
    ax.grid(True, alpha=0.3)
    fig.suptitle("Liquid-book split placebo / falsifier", y=1.02)
    path = BOOK / "out" / "liq_book_split" / "figs" / "placebo.png"
    return _savefig(fig, path)


# ── xvenue_tick ────────────────────────────────────────────────────────────


def fig_tau_gap_heatmap(panel: dict, liq_art: dict | None) -> Path:
    days = sorted({r["day"] for r in panel["rows"]})
    venues = ["hyperliquid", "deribit", "kraken"]
    # mean τ by venue, and pairwise abs gap heat per day averaged
    tau_mat = np.full((len(venues), len(days)), np.nan)
    for i, v in enumerate(venues):
        for j, d in enumerate(days):
            row = next((r for r in panel["rows"] if r.get("venue") == v and r.get("day") == d), None)
            if row and np.isfinite(row.get("tau") or np.nan):
                tau_mat[i, j] = float(row["tau"])
    # pair gap matrix averaged
    pairs = (liq_art or {}).get("pair_summaries") or []
    pair_names = ["HL–DB", "HL–KR", "DB–KR"]
    pair_keys = [("hyperliquid", "deribit"), ("hyperliquid", "kraken"), ("deribit", "kraken")]
    gap_mat = np.full((len(pair_names), len(days)), np.nan)
    for j, d in enumerate(days):
        for i, (a, b) in enumerate(pair_keys):
            match = next((p for p in pairs if p["day"] == d and {p["a"], p["b"]} == {a, b}), None)
            if match:
                gap_mat[i, j] = float(match.get("rel_tick_gap") or match.get("tau_gap") or np.nan)

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.6))
    ax = axes[0]
    im = ax.imshow(tau_mat, aspect="auto", cmap="viridis")
    ax.set_xticks(range(len(days)))
    ax.set_xticklabels([d[5:] for d in days])
    ax.set_yticks(range(len(venues)))
    ax.set_yticklabels([VENUE_SHORT[v] for v in venues])
    for i in range(len(venues)):
        for j in range(len(days)):
            if np.isfinite(tau_mat[i, j]):
                ax.text(j, i, f"{tau_mat[i, j]:.2g}", ha="center", va="center", color="w", fontsize=8)
    ax.set_title("Absolute τ by venue-day")
    fig.colorbar(im, ax=ax, fraction=0.046)

    ax = axes[1]
    im2 = ax.imshow(gap_mat, aspect="auto", cmap="coolwarm")
    ax.set_xticks(range(len(days)))
    ax.set_xticklabels([d[5:] for d in days])
    ax.set_yticks(range(len(pair_names)))
    ax.set_yticklabels(pair_names)
    ax.set_title("Rel-tick gap (signed) heatmap")
    fig.colorbar(im2, ax=ax, fraction=0.046)
    fig.suptitle("Cross-venue τ gap — HL↔Deribit↔Kraken", y=1.02)
    path = BOOK / "out" / "xvenue_tick" / "figs" / "tau_gap_heatmap.png"
    return _savefig(fig, path)


def fig_mq_vs_gap(liq_art: dict | None) -> Path:
    pairs = (liq_art or {}).get("pair_summaries") or []
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    colors = {"hyperliquid-deribit": "#1f77b4", "hyperliquid-kraken": "#2ca02c", "deribit-kraken": "#ff7f0e"}
    for ax, ykey, ylab in (
        (axes[0], "spread_gap_bps", "Δ quoted spread (bps)"),
        (axes[1], "depth_gap", "Δ BBO depth"),
    ):
        for p in pairs:
            key = "-".join(sorted([p["a"], p["b"]]))
            # normalize key order as a-b from sorted short
            a, b = p["a"], p["b"]
            lab = f"{VENUE_SHORT.get(a, a)}–{VENUE_SHORT.get(b, b)}"
            x = p.get("rel_tick_gap", p.get("tau_gap"))
            y = p.get(ykey)
            try:
                x, y = float(x), float(y)
            except (TypeError, ValueError):
                continue
            if not (np.isfinite(x) and np.isfinite(y)):
                continue
            ax.scatter([x], [y], c=colors.get("-".join(sorted([a, b])), "#333"), s=60, alpha=0.85, label=lab)
        ax.axhline(0, color="k", lw=0.5)
        ax.axvline(0, color="k", lw=0.5)
        ax.set_xlabel("rel_tick gap")
        ax.set_ylabel(ylab)
        ax.grid(True, alpha=0.3)
        # dedupe legend
        handles, labels = ax.get_legend_handles_labels()
        by = dict(zip(labels, handles))
        ax.legend(by.values(), by.keys(), fontsize=7)
        if ykey == "depth_gap":
            ax.set_yscale("symlog", linthresh=1e6)
    fig.suptitle("MQ Δ vs τ/rel-tick gap (pair-days)", y=1.02)
    path = BOOK / "out" / "xvenue_tick" / "figs" / "mq_vs_gap.png"
    return _savefig(fig, path)


def fig_grid_pressure(flat: list[dict], liq_art: dict | None) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    ax = axes[0]
    for v in ("hyperliquid", "deribit", "kraken"):
        sub = [r for r in flat if r["venue"] == v]
        xs = [r["day"][5:] for r in sub]
        ys = [r.get("grid_pressure_std") for r in sub]
        ax.plot(xs, ys, "o-", color=VENUE_COLORS[v], label=VENUE_SHORT[v] + (" synth" if v == "kraken" else ""))
    ax.set_ylabel("grid pressure std (Δ τ/mid)")
    ax.set_title("Within-venue grid pressure")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    concord = (liq_art or {}).get("concord") or {}
    # residual: spread_gap vs rel_tick_gap scatter residual board
    pairs = (liq_art or {}).get("pair_summaries") or []
    xs, ys = [], []
    for p in pairs:
        try:
            x = float(p.get("rel_tick_gap"))
            y = float(p.get("spread_gap_bps"))
        except (TypeError, ValueError):
            continue
        if np.isfinite(x) and np.isfinite(y):
            xs.append(x)
            ys.append(y)
    if len(xs) >= 2:
        xs_a, ys_a = np.asarray(xs), np.asarray(ys)
        # residual after linear fit
        coef = np.polyfit(xs_a, ys_a, 1)
        resid = ys_a - np.polyval(coef, xs_a)
        ax.scatter(xs_a, resid, c="#4c72b0", s=55)
        ax.axhline(0, color="k", lw=0.6)
        ax.set_xlabel("rel_tick gap")
        ax.set_ylabel("spread_gap residual (bps)")
        ax.set_title(f"Grid-pressure MQ residual · concord {concord.get('hits')}/{concord.get('n')}")
    else:
        ax.text(0.5, 0.5, "no pairs", ha="center", transform=ax.transAxes)
    ax.grid(True, alpha=0.3)
    fig.suptitle("Grid pressure + concordance residuals", y=1.02)
    path = BOOK / "out" / "xvenue_tick" / "figs" / "grid_pressure.png"
    return _savefig(fig, path)


# ── desk synthesis board fig ───────────────────────────────────────────────


def fig_signal_board(gates: dict) -> Path:
    g = gates.get("gates") or gates
    order = list(g.keys())
    decisions = [g[k]["decision"] for k in order]
    color = {"Promote": "#2ca02c", "Hold": "#ffbf00", "Kill": "#d62728"}
    fig, ax = plt.subplots(figsize=(10, 5))
    y = np.arange(len(order))
    for i, (k, d) in enumerate(zip(order, decisions)):
        ax.barh(i, 1, color=color.get(d, "#999"), alpha=0.85)
        ax.text(0.02, i, f"{k}  ·  {d}", va="center", fontsize=8, color="k")
    ax.set_yticks([])
    ax.set_xticks([])
    ax.set_xlim(0, 1)
    ax.set_title(
        f"Signal board — "
        f"{sum(1 for d in decisions if d=='Promote')} Promote / "
        f"{sum(1 for d in decisions if d=='Hold')} Hold / "
        f"{sum(1 for d in decisions if d=='Kill')} Kill"
    )
    # legend
    from matplotlib.patches import Patch

    ax.legend(handles=[Patch(color=c, label=l) for l, c in color.items()], loc="lower right", fontsize=8)
    path = BOOK / "out" / "desk_synthesis" / "figs" / "signal_board.png"
    return _savefig(fig, path)


def write_desk_synthesis_nb(fig_paths: dict[str, str], gates: dict) -> None:
    """Full multi-lens desk_synthesis notebook embedding real PNGs."""
    n_promote = sum(1 for v in gates["gates"].values() if v["decision"] == "Promote")
    n_hold = sum(1 for v in gates["gates"].values() if v["decision"] == "Hold")
    n_kill = sum(1 for v in gates["gates"].values() if v["decision"] == "Kill")
    days = gates.get("days") or []

    def img_cell(title: str, rel: str) -> list:
        return [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [f"### {title}\n", f"\n`{rel}`\n"],
            },
            {
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": [
                    "from IPython.display import Image, display\n",
                    "from pathlib import Path\n",
                    f"p = BOOK / '{rel}'\n",
                    "display(Image(filename=str(p)) if p.exists() else f'missing {p}')\n",
                ],
            },
        ]

    cells: list[dict] = [
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "# Desk synthesis — Tick Size Viewpoints\n",
                "\n",
                f"**{n_promote} Promote / {n_hold} Hold / {n_kill} Kill** on ETH HL+Deribit+Kraken "
                f"({', '.join(days)}).\n",
                "\n",
                "Multi-lens board: `disc` taxonomy · `liq` FM/ρ · `exec` constraint · `frag` x-venue · Kill vanity/welfare/SEC.\n",
                "Kraken TOB is **trade_synth** — labeled in figures; do not overclaim.\n",
            ],
        },
        {
            "cell_type": "code",
            "metadata": {},
            "execution_count": None,
            "outputs": [],
            "source": [
                "import json, sys\n",
                "from pathlib import Path\n",
                "ROOT = Path(os.environ.get('ARES_MICROSTRUCTURE') or (Path.home() / 'srv' / 'ares-microstructure'))\n",
                "BOOK = ROOT / 'research/books/mm_confr_viewpoints'\n",
                "sys.path.insert(0, str(ROOT))\n",
                "gates = json.loads((BOOK/'out/pass2/hardening_gates.json').read_text())\n",
                "print('rho_ci', gates.get('rho_ci'))\n",
                "print('n_complete', gates.get('n_complete'), 'n_tob', gates.get('n_tob'))\n",
                "for k,v in gates['gates'].items():\n",
                "    print(f\"{v['decision']:7s}  {k}\")\n",
            ],
        },
    ]
    # board
    cells.extend(img_cell("Signal board", "out/desk_synthesis/figs/signal_board.png"))
    cells.extend(img_cell("Coverage (ch00)", "out/ch00_overview/figs/coverage.png"))
    cells.extend(img_cell("Expected-sign matrix", "out/emp_predictions/figs/sign_matrix.png"))
    cells.extend(img_cell("Sign scorecard (Kill tradable)", "out/emp_predictions/figs/scorecard.png"))
    cells.extend(img_cell("rel_tick × MQ scatter", "out/rel_tick_panel/figs/scatter_mq.png"))
    cells.extend(img_cell("FM coefs ± CI", "out/rel_tick_panel/figs/fm_coefs.png"))
    cells.extend(img_cell("Time-split + markout quartile", "out/rel_tick_panel/figs/time_split.png"))
    cells.extend(img_cell("Frac constrained by venue", "out/tick_constraint/figs/frac_constrained.png"))
    cells.extend(img_cell("Spread-in-ticks hist", "out/tick_constraint/figs/spread_ticks_hist.png"))
    cells.extend(img_cell("Relax / constraint flips", "out/tick_constraint/figs/relax_events.png"))
    cells.extend(img_cell("Tercile interaction", "out/liq_book_split/figs/tercile_interaction.png"))
    cells.extend(img_cell("Placebo falsifier", "out/liq_book_split/figs/placebo.png"))
    cells.extend(img_cell("τ gap heatmap", "out/xvenue_tick/figs/tau_gap_heatmap.png"))
    cells.extend(img_cell("MQ Δ vs gap", "out/xvenue_tick/figs/mq_vs_gap.png"))
    cells.extend(img_cell("Grid pressure", "out/xvenue_tick/figs/grid_pressure.png"))
    cells.append(
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## Gate call\n",
                "\n",
                "- **Promote:** `disc.tick_rq_taxonomy` only (framing).\n",
                "- **Hold:** FM/ρ (x-venue confound), constraint (mmip overlap), x-venue τ gap / grid pressure.\n",
                "- **Kill:** LSE/Nasdaq RDD, welfare, SEC/IPO, sign-scorecard-as-tradable.\n",
                "- **Data caveat:** Kraken BBO is trade_synth; Deribit L2 sparse on some hours.\n",
            ],
        }
    )
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "cells": cells,
    }
    (BOOK / "notebooks" / "desk_synthesis.ipynb").write_text(json.dumps(nb, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-tob-reload", action="store_true", help="skip constraint hist/relax TOB reload")
    args = ap.parse_args()

    panel = _load_pass1("panel.json")
    fm = _load_pass1("fm.json")
    score = _load_pass1("sign_scorecard.json")
    comp = _load_pass1("completeness.json")
    matrix = _load_pass1("expected_sign_matrix.json")
    liq = _load_pass2("liq_xvenue.json")
    gates = _load_pass2("hardening_gates.json") or {}
    flat = _flat_rows(panel)

    written: list[str] = []

    # package JSON slices
    _json(BOOK / "out" / "ch00_overview" / "coverage.json", {"completeness": comp, "flat": flat})
    _json(BOOK / "out" / "rel_tick_panel" / "panel_flat.json", {"rows": flat, "fm": fm})
    _json(BOOK / "out" / "emp_predictions" / "scorecard.json", score)
    _json(BOOK / "out" / "emp_predictions" / "expected_sign_matrix.json", matrix)
    _json(BOOK / "out" / "liq_book_split" / "het.json", liq or {})
    _json(BOOK / "out" / "xvenue_tick" / "pairs.json", {"pair_summaries": (liq or {}).get("pair_summaries"), "concord": (liq or {}).get("concord")})

    # figures
    written.append(str(fig_coverage(comp, flat)))
    written.append(str(fig_sign_matrix(matrix)))
    written.append(str(fig_scorecard(score, gates)))
    written.append(str(fig_scatter_mq(flat)))
    written.append(str(fig_fm_coefs(fm)))
    written.append(str(fig_time_split(flat, gates)))
    written.append(str(fig_frac_constrained(flat)))
    written.append(str(fig_tercile_interaction(flat, liq)))
    written.append(str(fig_placebo(flat, liq)))
    written.append(str(fig_tau_gap_heatmap(panel, liq)))
    written.append(str(fig_mq_vs_gap(liq)))
    written.append(str(fig_grid_pressure(flat, liq)))
    if gates:
        written.append(str(fig_signal_board(gates)))

    if not args.skip_tob_reload:
        print("reloading TOB for constraint hist / relax events …", flush=True)
        cart = _reload_constraint_series(panel)
        _json(BOOK / "out" / "tick_constraint" / "constraint_series.json", cart)
        written.append(str(fig_spread_ticks_hist(cart)))
        written.append(str(fig_relax_events(cart)))
    else:
        # stub empty hist from day medians if no reload
        stub = {
            "hist_by_venue": {},
            "flip_summary": [],
            "series": [],
        }
        for r in flat:
            if r.get("median_spread_ticks") and np.isfinite(r["median_spread_ticks"]):
                stub["hist_by_venue"].setdefault(r["venue"], []).append(r["median_spread_ticks"])
        written.append(str(fig_spread_ticks_hist(stub)))
        written.append(str(fig_relax_events(stub)))

    if gates:
        write_desk_synthesis_nb({p: p for p in written}, gates)

    manifest = {"n_figs": len(written), "figs": written}
    _json(BOOK / "out" / "fig_manifest.json", manifest)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
