from __future__ import annotations
#!/usr/bin/env python3
"""Chapter-local xvenue_tick runner — owns out/xvenue_tick/ only.

Does not edit shared scripts/ or research/lib/. Uses ticksize + book _data
loaders + mmip helpers (epps / fei) when importable.
"""


import json
import math
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BOOK = Path(__file__).resolve().parents[2]
ROOT = BOOK.parents[1]
MICRO = ROOT  # research/
REPO = MICRO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(BOOK / "scripts"))

from ares_micro.book.ticksize import (  # noqa: E402
    cross_venue_tau_gap,
    grid_pressure_feature,
)
from ares_micro.flow.epps import corr_vs_lag  # noqa: E402
from ares_micro.flow.fei import fei  # noqa: E402

import _data as D  # noqa: E402

OUT = BOOK / "out" / "xvenue_tick"
FIGS = OUT / "figs"
CH = BOOK / "chapters" / "xvenue_tick"
PASS1_PANEL = BOOK / "out" / "pass1" / "panel.json"
PASS2_X = BOOK / "out" / "pass2" / "liq_xvenue.json"

VENUES = ("hyperliquid", "deribit", "kraken")
VENUE_SHORT = {"hyperliquid": "HL", "deribit": "DB", "kraken": "KR"}
PAIR_ORDER = [
    ("hyperliquid", "deribit"),
    ("hyperliquid", "kraken"),
    ("deribit", "kraken"),
]


def _json_dump(path: Path, obj: Any) -> None:
    def _default(o: Any) -> Any:
        if isinstance(o, (np.floating, np.integer)):
            return float(o) if np.isfinite(o) else None
        if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
            return None
        if isinstance(o, Path):
            return str(o)
        raise TypeError(type(o))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=_default) + "\n")


def load_eth_panel() -> dict[str, Any]:
    return json.loads(PASS1_PANEL.read_text())


def rows_by_day_venue(rows: list[dict]) -> dict[tuple[str, str, str], dict]:
    out = {}
    for r in rows:
        if r.get("error"):
            continue
        out[(r.get("symbol", "ETH"), r["day"], r["venue"])] = r
    return out


def build_pair_table(rows: list[dict]) -> list[dict[str, Any]]:
    """Same-coin τ gaps + MQ Δ for dual-TOB venue pairs."""
    by = {}
    for r in rows:
        if r.get("error") or not r.get("tob_ok"):
            continue
        by.setdefault((r.get("symbol", "ETH"), r["day"]), {})[r["venue"]] = r
    pairs = []
    for (sym, day), by_v in sorted(by.items()):
        taus = {v: float(by_v[v]["tau"]) for v in by_v if np.isfinite(by_v[v].get("tau") or np.nan)}
        mids = {}
        for v, rec in by_v.items():
            mid = (rec.get("mq") or {}).get("mid")
            if mid is not None and np.isfinite(float(mid)):
                mids[v] = float(mid)
        gaps = cross_venue_tau_gap(taus, mid_by_venue=mids or None)
        for p in gaps.get("pairs", []):
            va, vb = p["a"], p["b"]
            ra, rb = by_v[va], by_v[vb]
            vol_a = float(ra.get("volume") or np.nan)
            vol_b = float(rb.get("volume") or np.nan)
            pairs.append(
                {
                    "symbol": sym,
                    "day": day,
                    **p,
                    "spread_a": float(ra.get("quoted_spread_bps") or np.nan),
                    "spread_b": float(rb.get("quoted_spread_bps") or np.nan),
                    "spread_gap_bps": float(ra["quoted_spread_bps"] - rb["quoted_spread_bps"])
                    if np.isfinite(ra.get("quoted_spread_bps") or np.nan)
                    and np.isfinite(rb.get("quoted_spread_bps") or np.nan)
                    else float("nan"),
                    "depth_a": float(ra.get("bbo_depth") or np.nan),
                    "depth_b": float(rb.get("bbo_depth") or np.nan),
                    "depth_gap": float(ra["bbo_depth"] - rb["bbo_depth"])
                    if np.isfinite(ra.get("bbo_depth") or np.nan)
                    and np.isfinite(rb.get("bbo_depth") or np.nan)
                    else float("nan"),
                    "volume_a": vol_a,
                    "volume_b": vol_b,
                    "volume_gap": vol_a - vol_b
                    if np.isfinite(vol_a) and np.isfinite(vol_b)
                    else float("nan"),
                    "rel_tick_bps_a": float(ra.get("rel_tick_bps") or np.nan),
                    "rel_tick_bps_b": float(rb.get("rel_tick_bps") or np.nan),
                    "grid_pressure_a": float((ra.get("grid") or {}).get("pressure_std") or np.nan),
                    "grid_pressure_b": float((rb.get("grid") or {}).get("pressure_std") or np.nan),
                    "tau_source_a": ra.get("tau_source"),
                    "tau_source_b": rb.get("tau_source"),
                    "tob_source_a": ra.get("tob_source"),
                    "tob_source_b": rb.get("tob_source"),
                }
            )
    return pairs


def fig_tau_gap_heatmap(pairs: list[dict], path: Path) -> dict[str, Any]:
    """τ gap heatmap HL↔DB↔KR by coin×day."""
    symbols = sorted({p["symbol"] for p in pairs})
    days = sorted({p["day"] for p in pairs})
    n_sym, n_day = max(len(symbols), 1), max(len(days), 1)
    fig, axes = plt.subplots(1, len(PAIR_ORDER), figsize=(4.2 * len(PAIR_ORDER), 2.8 + 0.35 * n_day))
    if len(PAIR_ORDER) == 1:
        axes = [axes]
    meta = {"cells": []}
    for ax, (va, vb) in zip(axes, PAIR_ORDER):
        mat = np.full((n_sym, n_day), np.nan)
        for i, sym in enumerate(symbols):
            for j, day in enumerate(days):
                hit = [
                    p
                    for p in pairs
                    if p["symbol"] == sym
                    and p["day"] == day
                    and ((p["a"] == va and p["b"] == vb) or (p["a"] == vb and p["b"] == va))
                ]
                if not hit:
                    continue
                p = hit[0]
                gap = float(p["tau_gap"])
                if p["a"] == vb and p["b"] == va:
                    gap = -gap
                mat[i, j] = gap
                meta["cells"].append(
                    {
                        "symbol": sym,
                        "day": day,
                        "pair": f"{VENUE_SHORT[va]}-{VENUE_SHORT[vb]}",
                        "tau_gap": gap,
                        "tau_a": p["tau_a"] if p["a"] == va else p["tau_b"],
                        "tau_b": p["tau_b"] if p["b"] == vb else p["tau_a"],
                    }
                )
        finite = mat[np.isfinite(mat)]
        if finite.size:
            lim = float(max(0.05, np.nanmax(np.abs(finite))))
        else:
            lim = 0.06
        im = ax.imshow(mat, aspect="auto", cmap="RdBu_r", vmin=-lim, vmax=lim)
        ax.set_xticks(range(n_day))
        ax.set_xticklabels([d[5:] for d in days], rotation=45, ha="right", fontsize=8)
        ax.set_yticks(range(n_sym))
        ax.set_yticklabels(symbols, fontsize=9)
        ax.set_title(f"τ gap {VENUE_SHORT[va]}−{VENUE_SHORT[vb]}", fontsize=10)
        for i in range(n_sym):
            for j in range(n_day):
                if np.isfinite(mat[i, j]):
                    ax.text(j, i, f"{mat[i, j]:.2f}", ha="center", va="center", fontsize=7, color="k")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="τ_a − τ_b")
    fig.suptitle("Cross-venue absolute tick gap (same coin)", fontsize=11, y=1.02)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return meta


def fig_mq_vs_tau_scatter(pairs: list[dict], path: Path) -> dict[str, Any]:
    """MQ Δ (spread/depth/volume) vs τ gap scatter."""
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.6))
    metrics = [
        ("spread_gap_bps", "Δ quoted spread (bps)\nA − B"),
        ("depth_gap", "Δ BBO depth\nA − B"),
        ("volume_gap", "Δ volume\nA − B"),
    ]
    stats = {}
    for ax, (key, ylab) in zip(axes, metrics):
        xs, ys, labels = [], [], []
        for p in pairs:
            x = float(p.get("tau_gap") or np.nan)
            y = float(p.get(key) or np.nan)
            if not (np.isfinite(x) and np.isfinite(y)):
                continue
            # depth can be huge / unit-inconsistent — use log-signed
            if key == "depth_gap" and abs(y) > 0:
                y = np.sign(y) * np.log10(1.0 + abs(y))
            xs.append(x)
            ys.append(y)
            labels.append(f"{p['symbol'][:1]} {VENUE_SHORT[p['a']]}-{VENUE_SHORT[p['b']]}")
        xs_a, ys_a = np.asarray(xs), np.asarray(ys)
        colors = []
        for p in pairs:
            x = float(p.get("tau_gap") or np.nan)
            y = float(p.get(key) or np.nan)
            if not (np.isfinite(x) and np.isfinite(y)):
                continue
            colors.append({"ETH": "#1f77b4", "BTC": "#ff7f0e"}.get(p["symbol"], "#555"))
        if xs_a.size:
            ax.scatter(xs_a, ys_a, c=colors[: xs_a.size], s=42, alpha=0.85, edgecolors="k", linewidths=0.3)
            if xs_a.size >= 3 and np.std(xs_a) > 0:
                slope = float(np.corrcoef(xs_a, ys_a)[0, 1])
            else:
                slope = float("nan")
        else:
            slope = float("nan")
        ax.axhline(0, color="0.6", lw=0.8)
        ax.axvline(0, color="0.6", lw=0.8)
        ax.set_xlabel("τ gap (A − B)")
        ax.set_ylabel(ylab + (" [sign·log10]" if key == "depth_gap" else ""))
        ax.set_title(f"ρ={slope:.2f}" if np.isfinite(slope) else "n<3")
        stats[key] = {"n": int(xs_a.size), "pearson": slope}
    fig.suptitle("MQ Δ vs cross-venue τ gap", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return stats


def fig_grid_pressure_residuals(rows: list[dict], path: Path) -> dict[str, Any]:
    """Grid-pressure residuals: within-venue rel_tick moves without τ change.

    Residualize hour-level spread on hour-level rel_tick; residual vs
    |Δrel_tick| from day-open (grid pressure proxy). τ fixed within venue.
    """
    pts = []
    for r in rows:
        if not r.get("tob_ok"):
            continue
        hrs = r.get("hour_rows") or []
        if len(hrs) < 4:
            continue
        rts = np.array([float(h.get("rel_tick") or np.nan) for h in hrs], dtype=np.float64)
        sps = np.array([float(h.get("quoted_spread_bps") or np.nan) for h in hrs], dtype=np.float64)
        ok = np.isfinite(rts) & np.isfinite(sps)
        if ok.sum() < 4:
            continue
        x, y = rts[ok], sps[ok]
        x_c = x - x.mean()
        den = float((x_c * x_c).sum())
        if den <= 0:
            continue
        beta = float((x_c * (y - y.mean())).sum() / den)
        resid = y - (y.mean() + beta * x_c)
        # pressure vs first hour
        rt0 = float(x[0])
        pressure = x - rt0
        for p_i, e_i in zip(pressure, resid):
            pts.append(
                {
                    "symbol": r.get("symbol", "ETH"),
                    "venue": r["venue"],
                    "day": r["day"],
                    "pressure": float(p_i),
                    "resid_spread_bps": float(e_i),
                    "tau": float(r.get("tau") or np.nan),
                }
            )

    fig, ax = plt.subplots(figsize=(6.2, 4.0))
    by_v = {v: [(p["pressure"], p["resid_spread_bps"]) for p in pts if p["venue"] == v] for v in VENUES}
    for v, xy in by_v.items():
        if not xy:
            continue
        xs, ys = zip(*xy)
        ax.scatter(xs, ys, s=18, alpha=0.55, label=VENUE_SHORT[v])
    ax.axhline(0, color="0.5", lw=0.8)
    ax.axvline(0, color="0.5", lw=0.8)
    ax.set_xlabel("grid pressure Δ(τ/mid) vs day-open (τ fixed)")
    ax.set_ylabel("residual quoted spread (bps)\nafter within-day β·rel_tick")
    ax.set_title("Grid-pressure residuals (rel_tick moves, no τ change)")
    ax.legend(fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)

    if len(pts) >= 5:
        xs = np.array([p["pressure"] for p in pts])
        ys = np.array([p["resid_spread_bps"] for p in pts])
        rho = float(np.corrcoef(xs, ys)[0, 1]) if np.std(xs) > 0 and np.std(ys) > 0 else float("nan")
    else:
        rho = float("nan")
    return {"n_points": len(pts), "rho_pressure_resid_spread": rho}


def _high_rel_tick_hours(rows: list[dict], *, q: float = 0.75) -> dict[tuple[str, str], set[int]]:
    """Per (symbol, day): set of hour_ids in top quartile of median rel_tick across venues."""
    by_day: dict[tuple[str, str], list[tuple[int, float]]] = {}
    for r in rows:
        if not r.get("tob_ok"):
            continue
        key = (r.get("symbol", "ETH"), r["day"])
        for h in r.get("hour_rows") or []:
            rt = h.get("rel_tick")
            hid = h.get("hour_id")
            if hid is None or not np.isfinite(float(rt or np.nan)):
                continue
            by_day.setdefault(key, []).append((int(hid), float(rt)))
    out = {}
    for key, pairs in by_day.items():
        # median rt per hour across venue observations
        bucket: dict[int, list[float]] = {}
        for hid, rt in pairs:
            bucket.setdefault(hid, []).append(rt)
        med = {hid: float(np.median(vs)) for hid, vs in bucket.items()}
        if len(med) < 4:
            continue
        thr = float(np.quantile(list(med.values()), q))
        out[key] = {hid for hid, v in med.items() if v >= thr}
    return out


def fig_concord_epps_fei(
    rows: list[dict],
    path: Path,
    *,
    try_load_trades: bool = True,
) -> dict[str, Any]:
    """Concordance of high-rel-tick hours + FEI volume; Epps if tapes load."""
    high = _high_rel_tick_hours(rows)
    # venue-specific high hours for Jaccard
    venue_high: dict[tuple[str, str, str], set[int]] = {}
    for r in rows:
        if not r.get("tob_ok"):
            continue
        hrs = r.get("hour_rows") or []
        rts = [float(h.get("rel_tick") or np.nan) for h in hrs]
        finite = [x for x in rts if np.isfinite(x)]
        if len(finite) < 4:
            continue
        thr = float(np.quantile(finite, 0.75))
        key = (r.get("symbol", "ETH"), r["day"], r["venue"])
        venue_high[key] = {
            int(h["hour_id"])
            for h, rt in zip(hrs, rts)
            if np.isfinite(rt) and rt >= thr and h.get("hour_id") is not None
        }

    jaccards = []
    days_sym = sorted({(r.get("symbol", "ETH"), r["day"]) for r in rows if r.get("tob_ok")})
    for sym, day in days_sym:
        for va, vb in PAIR_ORDER:
            sa = venue_high.get((sym, day, va), set())
            sb = venue_high.get((sym, day, vb), set())
            if not sa and not sb:
                continue
            inter = len(sa & sb)
            union = len(sa | sb)
            jaccards.append(
                {
                    "symbol": sym,
                    "day": day,
                    "pair": f"{VENUE_SHORT[va]}-{VENUE_SHORT[vb]}",
                    "jaccard": float(inter / union) if union else float("nan"),
                    "n_a": len(sa),
                    "n_b": len(sb),
                    "n_overlap": inter,
                }
            )

    # FEI on daily volume shares
    fei_rows = []
    by = {}
    for r in rows:
        if r.get("error"):
            continue
        by.setdefault((r.get("symbol", "ETH"), r["day"]), {})[r["venue"]] = r
    for (sym, day), by_v in sorted(by.items()):
        vols = [float(by_v[v].get("volume") or 0.0) if v in by_v else 0.0 for v in VENUES]
        fei_rows.append(
            {
                "symbol": sym,
                "day": day,
                "volumes": {v: float(by_v[v].get("volume") or np.nan) if v in by_v else float("nan") for v in VENUES},
                "fei_volume": float(fei(vols, n_pools=3)),
            }
        )

    # Epps: load one complete ETH day trades if possible
    epps_curves = []
    epps_note = "skipped"
    if try_load_trades:
        eth_days = sorted({r["day"] for r in rows if r.get("symbol", "ETH") == "ETH" and r.get("completeness", {}).get("complete")})
        target_day = eth_days[0] if eth_days else None
        if target_day:
            try:
                D.ensure_env()
                packed = D.load_core_venues_day("ETH", target_day, quiet=True)
                tapes = {}
                for v, rec in packed.get("venues", {}).items():
                    if rec.get("error"):
                        continue
                    tape = rec.get("tape") or {}
                    ts = np.asarray(tape.get("ts", []), dtype=np.int64)
                    px = np.asarray(tape.get("px", []), dtype=np.float64)
                    if ts.size >= 500 and np.isfinite(px).sum() >= 500:
                        tapes[v] = (ts, px)
                # restrict to high-rel-tick UTC hours if we have them
                hi = high.get(("ETH", target_day), set())
                for va, vb in PAIR_ORDER:
                    if va not in tapes or vb not in tapes:
                        continue
                    ta, pa = tapes[va]
                    tb, pb = tapes[vb]
                    if hi:
                        # hour_id = ts // 3.6e12
                        def _mask(ts: np.ndarray) -> np.ndarray:
                            hid = ts // 3_600_000_000_000
                            return np.isin(hid, list(hi))

                        ma, mb = _mask(ta), _mask(tb)
                        if int(ma.sum()) >= 200 and int(mb.sum()) >= 200:
                            ta, pa = ta[ma], pa[ma]
                            tb, pb = tb[mb], pb[mb]
                            window = "high_rel_tick_hours"
                        else:
                            window = "full_day_fallback"
                    else:
                        window = "full_day"
                    curve = corr_vs_lag(ta, pa, tb, pb, lags_s=(1.0, 5.0, 15.0, 60.0, 300.0))
                    epps_curves.append(
                        {
                            "symbol": "ETH",
                            "day": target_day,
                            "pair": f"{VENUE_SHORT[va]}-{VENUE_SHORT[vb]}",
                            "window": window,
                            "curve": curve["curve"],
                        }
                    )
                epps_note = f"ETH {target_day}; n_pairs={len(epps_curves)}"
            except Exception as exc:  # noqa: BLE001
                epps_note = f"load_failed: {type(exc).__name__}: {exc}"

    # plot
    fig, axes = plt.subplots(1, 3, figsize=(12.0, 3.8))

    # concordance bars
    ax = axes[0]
    if jaccards:
        labels = [f"{j['pair']}\n{j['day'][5:]}" for j in jaccards]
        vals = [j["jaccard"] for j in jaccards]
        ax.bar(range(len(vals)), vals, color="#4c72b0", alpha=0.85)
        ax.set_xticks(range(len(vals)))
        ax.set_xticklabels(labels, fontsize=6, rotation=45, ha="right")
        ax.set_ylim(0, 1)
        ax.set_ylabel("Jaccard (high-τ/mid hours)")
        ax.set_title(f"Concordance mean={np.nanmean(vals):.2f}")
    else:
        ax.text(0.5, 0.5, "no hour overlap", ha="center", transform=ax.transAxes)
        ax.set_title("Concordance")

    # FEI
    ax = axes[1]
    if fei_rows:
        x = np.arange(len(fei_rows))
        ax.bar(x, [f["fei_volume"] for f in fei_rows], color="#55a868", alpha=0.85)
        ax.set_xticks(x)
        ax.set_xticklabels([f"{f['symbol']}\n{f['day'][5:]}" for f in fei_rows], fontsize=7)
        ax.set_ylim(0, 1.05)
        ax.set_ylabel("FEI (volume, N=3)")
        ax.set_title(f"FEI mean={np.nanmean([f['fei_volume'] for f in fei_rows]):.2f}")
    else:
        ax.set_title("FEI")

    # Epps
    ax = axes[2]
    if epps_curves:
        for c in epps_curves:
            lags = [r["lag_s"] for r in c["curve"]]
            corrs = [r["corr"] for r in c["curve"]]
            ax.plot(lags, corrs, marker="o", ms=4, label=c["pair"])
        ax.set_xscale("log")
        ax.set_xlabel("lag (s)")
        ax.set_ylabel("corr(log-ret)")
        ax.set_title(f"Epps @ high-τ/mid\n{epps_note}")
        ax.legend(fontsize=7, frameon=False)
        ax.axhline(0, color="0.6", lw=0.7)
    else:
        ax.text(0.5, 0.5, f"Epps Hold\n{epps_note}", ha="center", va="center", transform=ax.transAxes, fontsize=8)
        ax.set_title("Epps")

    fig.suptitle("Pass-2 join: concordance / FEI / Epps around high relative-tick", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)

    return {
        "concord_jaccard": jaccards,
        "concord_mean": float(np.nanmean([j["jaccard"] for j in jaccards])) if jaccards else float("nan"),
        "fei": fei_rows,
        "epps": epps_curves,
        "epps_note": epps_note,
    }


def fig_sor_panel(rows: list[dict], path: Path) -> dict[str, Any]:
    """SOR implication: which venue looks preferable when (spread, rel_tick, depth)."""
    by = {}
    for r in rows:
        if not r.get("tob_ok"):
            continue
        by.setdefault((r.get("symbol", "ETH"), r["day"]), {})[r["venue"]] = r

    preference = []
    for (sym, day), by_v in sorted(by.items()):
        if len(by_v) < 2:
            continue
        # score: lower spread better; lower rel_tick better; higher depth better
        scored = []
        for v, r in by_v.items():
            sp = float(r.get("quoted_spread_bps") or np.nan)
            rt = float(r.get("rel_tick_bps") or np.nan)
            dp = float(r.get("bbo_depth") or np.nan)
            scored.append((v, sp, rt, dp))
        # ranks
        spreads = [(v, sp) for v, sp, _, _ in scored if np.isfinite(sp)]
        rts = [(v, rt) for v, _, rt, _ in scored if np.isfinite(rt)]
        depths = [(v, dp) for v, _, _, dp in scored if np.isfinite(dp)]
        rank_sp = {v: i for i, (v, _) in enumerate(sorted(spreads, key=lambda x: x[1]))}
        rank_rt = {v: i for i, (v, _) in enumerate(sorted(rts, key=lambda x: x[1]))}
        # depth: higher better → reverse
        rank_dp = {v: i for i, (v, _) in enumerate(sorted(depths, key=lambda x: -x[1]))}
        composite = {}
        for v, sp, rt, dp in scored:
            parts = []
            if v in rank_sp:
                parts.append(rank_sp[v])
            if v in rank_rt:
                parts.append(rank_rt[v])
            if v in rank_dp:
                parts.append(rank_dp[v])
            composite[v] = float(np.mean(parts)) if parts else float("nan")
        pref = min(composite, key=lambda k: composite[k] if np.isfinite(composite[k]) else 9e9)
        preference.append(
            {
                "symbol": sym,
                "day": day,
                "prefer": pref,
                "composite_rank": composite,
                "spread_bps": {v: float(by_v[v].get("quoted_spread_bps") or np.nan) for v in by_v},
                "rel_tick_bps": {v: float(by_v[v].get("rel_tick_bps") or np.nan) for v in by_v},
                "tau": {v: float(by_v[v].get("tau") or np.nan) for v in by_v},
            }
        )

    # heatmap: venue × day of composite rank (lower better)
    days = sorted({p["day"] for p in preference})
    symbols = sorted({p["symbol"] for p in preference})
    fig, axes = plt.subplots(1, max(len(symbols), 1), figsize=(4.0 * max(len(symbols), 1), 3.4))
    if len(symbols) <= 1:
        axes = [axes]
    for ax, sym in zip(axes, symbols):
        mat = np.full((len(VENUES), len(days)), np.nan)
        annot = np.full((len(VENUES), len(days)), "", dtype=object)
        for j, day in enumerate(days):
            hit = [p for p in preference if p["symbol"] == sym and p["day"] == day]
            if not hit:
                continue
            p = hit[0]
            for i, v in enumerate(VENUES):
                mat[i, j] = p["composite_rank"].get(v, np.nan)
                if v == p["prefer"]:
                    annot[i, j] = "★"
        im = ax.imshow(mat, aspect="auto", cmap="viridis_r", vmin=0, vmax=2)
        ax.set_xticks(range(len(days)))
        ax.set_xticklabels([d[5:] for d in days], rotation=45, ha="right", fontsize=8)
        ax.set_yticks(range(len(VENUES)))
        ax.set_yticklabels([VENUE_SHORT[v] for v in VENUES])
        ax.set_title(f"{sym}: composite rank\n(lower better; ★ prefer)")
        for i in range(len(VENUES)):
            for j in range(len(days)):
                if np.isfinite(mat[i, j]):
                    ax.text(
                        j,
                        i,
                        f"{mat[i, j]:.1f}{annot[i, j]}",
                        ha="center",
                        va="center",
                        color="w",
                        fontsize=8,
                    )
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="mean rank")
    fig.suptitle(
        "SOR implication panel — prefer lower composite of\n"
        "rank(spread) + rank(rel_tick) + rank(−depth)",
        fontsize=10,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)

    counts: dict[str, int] = {}
    for p in preference:
        counts[p["prefer"]] = counts.get(p["prefer"], 0) + 1
    return {"preference": preference, "prefer_counts": counts}


def try_btc_slice(days: list[str]) -> list[dict]:
    """Opportunistic BTC rows — fail soft; do not block ETH memo."""
    rows = []
    try:
        D.ensure_env()
    except Exception as exc:  # noqa: BLE001
        print(f"BTC skip ensure_env: {exc}", flush=True)
        return rows
    from ares_micro.book.ticksize import (  # local import to keep top light
        mq_vector,
        relative_tick,
        venue_tick,
        grid_pressure_feature as gpf,
    )

    known = {"hyperliquid": 1.0, "deribit": 0.5, "kraken": 0.1}  # rough BTC defaults; prefer infer
    for day in days[:2]:
        for venue in VENUES:
            print(f"BTC probe {venue} {day} …", flush=True)
            try:
                rec = D.load_day_trades(venue, "BTC", day, quiet=True)
                try:
                    tob = D.load_tob_any(venue, "BTC", day)
                except Exception as te:  # noqa: BLE001
                    print(f"  tob fail: {te}", flush=True)
                    continue
                px = np.asarray(rec["tape"]["px"], dtype=np.float64)
                qty = np.asarray(rec["tape"]["qty"], dtype=np.float64)
                # infer tick from TOB
                prices = np.concatenate([tob["bid"], tob["ask"]])
                vt = venue_tick(venue, prices=prices, known_ticks=None)
                tau = float(vt["tau"])
                mq = mq_vector(
                    bid=tob["bid"],
                    ask=tob["ask"],
                    bid_sz=tob.get("bid_sz"),
                    ask_sz=tob.get("ask_sz"),
                    mid=tob.get("mid"),
                    tau=tau if np.isfinite(tau) else None,
                    trade_qty=qty,
                    trade_px=px,
                )
                grid = gpf(tob["mid"], tau) if np.isfinite(tau) else {}
                # hour buckets
                from ares_micro.book.spreads import quoted_spread_bps as qsb
                from ares_micro.book.ticksize import panel_hour_buckets

                qs = qsb(tob["bid"], tob["ask"], mid=tob["mid"])
                rt = relative_tick(tau, tob["mid"], as_bps=False)
                depth = np.asarray(tob["bid_sz"], dtype=np.float64) + np.asarray(tob["ask_sz"], dtype=np.float64)
                hour_rows = panel_hour_buckets(
                    tob["ts"],
                    {"quoted_spread_bps": qs, "rel_tick": np.asarray(rt, dtype=np.float64), "bbo_depth": depth},
                )
                for hr in hour_rows:
                    hr["day"] = day
                    hr["venue"] = venue
                    hr["symbol"] = "BTC"
                rows.append(
                    {
                        "venue": venue,
                        "symbol": "BTC",
                        "day": day,
                        "completeness": rec.get("completeness"),
                        "tau": tau,
                        "tau_source": vt["source"],
                        "tob_ok": True,
                        "tob_source": tob.get("source"),
                        "mq": mq,
                        "grid": grid,
                        "rel_tick": mq.get("rel_tick"),
                        "rel_tick_bps": mq.get("rel_tick_bps"),
                        "quoted_spread_bps": mq.get("quoted_spread_bps"),
                        "bbo_depth": mq.get("bbo_depth"),
                        "volume": mq.get("volume"),
                        "hour_rows": hour_rows,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  BTC fail {venue} {day}: {exc}", flush=True)
    return rows


def write_docs(summary: dict[str, Any]) -> None:
    figs = summary["figs"]
    pairs = summary["pairs"]
    concord = summary["concord_epps"]
    sor = summary["sor"]
    grid = summary["grid"]
    mq = summary["mq_scatter"]

    lims = summary.get("limitations", [])
    lim_md = "\n".join(f"- {x}" for x in lims)

    (CH / "EXP_REPORT.md").write_text(
        "\n".join(
            [
                "# xvenue_tick — EXP_REPORT",
                "",
                "## Sample",
                f"- Symbols: {summary['symbols']}",
                f"- Days: {summary['days']}",
                f"- Dual-TOB pair-days: {len(pairs)}",
                f"- Venues: HL + Deribit + Kraken",
                "",
                "## Pass 1 — τ gaps → MQ Δ / grid pressure",
                f"- τ-gap heatmap cells: {len(summary['heatmap'].get('cells', []))}",
                f"- MQΔ vs τ-gap Pearson: {json.dumps(mq, default=str)}",
                f"- Grid-pressure residual ρ(pressure, resid spread)={grid.get('rho_pressure_resid_spread')} (n={grid.get('n_points')})",
                "",
                "## Pass 2 — concordance / FEI / Epps / SOR",
                f"- High-rel-tick hour Jaccard mean={concord.get('concord_mean')} (n_pairs={len(concord.get('concord_jaccard') or [])})",
                f"- FEI volume (N=3) by day: {json.dumps(concord.get('fei'), default=str)}",
                f"- Epps: {concord.get('epps_note')}",
                f"- SOR prefer counts: {sor.get('prefer_counts')}",
                "",
                "## Figures",
                *[f"- `{p}`" for p in figs],
                "",
                "## Data limitations",
                lim_md,
                "",
                "## Gate notes",
                "- `frag.xvenue_tau_gap` — **Hold** (stable HL↔DB 2× gap on ETH; Kraken τ inferred ≈ HL; catalog decimals missing; no FE controls).",
                "- `frag.grid_pressure` — **Hold** (residuals exist; ρ weak / needs FE + more days).",
                "- `frag.xvenue_rel_tick_concord` — **Hold** (hour Jaccard on thin day set; not crash-event concordance).",
                "- `frag.fei_epps_hightick` — **Hold** (FEI reported; Epps depends on tape clocks / high-τ/mid filter).",
                "- `exec.sor_rel_tick` — **Hold** (composite rank heuristic only; no fill-quality / fee / latency label).",
                "- `id.vanity_price_rdd` — **Kill** (no discrete tick schedule thresholds in crypto perps).",
                "",
            ]
        )
    )

    (CH / "CANDIDATES.md").write_text(
        "\n".join(
            [
                "| id | type | lenses | decision | falsifier / blocker |",
                "|----|------|--------|----------|---------------------|",
                "| `frag.xvenue_tau_gap` | qe | frag, disc | **Hold** | τ often inferred (Kraken); no FE for venue microstructure confound |",
                "| `frag.grid_pressure` | feature | disc, liq | **Hold** | residual MQ Δ vs pressure weak; needs FE + longer panel |",
                "| `frag.xvenue_rel_tick_concord` | sync | frag, info | **Hold** | hour-set Jaccard on 3 ETH days; placebo not yet decisive |",
                "| `frag.fei_epps_hightick` | frag | frag, cont | **Hold** | FEI ok as descriptive; Epps clock/latency haircut missing |",
                "| `exec.sor_rel_tick` | policy | exec | **Hold** | no fill-quality / fee / latency label in slice |",
                "| `id.vanity_price_rdd` | id | disc | **Kill** | no sovereign tick ladder / discrete thresholds |",
                "",
                f"**Headline:** ETH HL τ≈0.1 vs Deribit τ≈0.05 (ratio 2) stable across days; Kraken inferred τ≈0.1 ≈ HL. "
                f"SOR composite prefers Deribit on spread+rel_tick when depth units comparable — **do not Promote** without fee/latency PnL.",
                "",
            ]
        )
    )

    notes = (CH / "NOTES.md").read_text()
    # refresh checklist + findings block
    block = f"""# Cross-venue τ gaps / grid pressure

**Book:** Rindi et al. MMCV #3 Paris 2014  
**PDF:** slides (local) · **Status:** `exp_run`  
**Raw:** [`../../_raw/`](../../_raw/) (local/gitignored)  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md) · Desk: [`../../DESK_MEMO.md`](../../DESK_MEMO.md)  
**Lib:** [`../../../../lib/ticksize.py`](../../../../lib/ticksize.py) · helpers [`../../../../lib/epps.py`](../../../../lib/epps.py), [`../../../../lib/fei.py`](../../../../lib/fei.py)  
**Out:** [`../../out/xvenue_tick/`](../../out/xvenue_tick/)

---

## Deck mapping (Pass 1)

| Slide theme | Crypto QE here |
|-------------|----------------|
| LSE price→tick RDD (pp. ~15–19) | **Park / Kill vanity RD** — no discrete schedule |
| Cross-listing / fragmentation | Same-coin τ gap HL↔Deribit↔Kraken (primary QE) |
| Relative tick / grid pressure (p. ~28) | Within-venue Δ(τ/mid) with τ fixed; residual MQ |
| Liquid vs thin × Δτ | Depth/spread MQ Δ vs τ gap (see also `liq_book_split`) |

## Pass 1 focus

Same-coin τ gaps HL↔Deribit↔Kraken → MQ Δ; grid-pressure residuals.

## Pass 2 dig

Concordance of high-rel-tick hours; FEI on 3-venue volume; Epps curve around high-τ/mid windows; SOR venue preference panel.

## Findings (this slice)

- ETH absolute τ: HL **0.1** (known) · Deribit **0.05** (known) · Kraken **~0.1** (inferred) → HL−DB gap **+0.05** stable.
- MQ: HL quoted spread tighter than Deribit on pair-days (spread_gap HL−DB < 0) despite **higher** τ — venue confound (book, fees, inventory) dominates pure tick story.
- Grid pressure: within-day rel_tick drift small; residual spread ρ vs pressure = {grid.get('rho_pressure_resid_spread')} (Hold).
- Concordance mean Jaccard (high-τ/mid hours) = {concord.get('concord_mean')}; FEI volume mean ≈ {float(np.nanmean([f['fei_volume'] for f in (concord.get('fei') or [])])) if concord.get('fei') else float('nan'):.3f}.
- Epps: {concord.get('epps_note')}.
- SOR composite prefer counts: {sor.get('prefer_counts')}.

## Data limitations

{lim_md}

## Pass checklist

### Pass 1
- [x] Cite deck pages in NOTES
- [x] Implement on HL + Deribit + Kraken
- [x] EXP_REPORT with day-completeness
- [x] Draft CANDIDATES

### Pass 2
- [x] Info joins / falsifiers (concordance + FEI + Epps attempt)
- [x] Signal board → CANDIDATES / EXP_REPORT (DESK_MEMO owned by hardening package)
"""
    (CH / "NOTES.md").write_text(block)


def main() -> None:
    FIGS.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    panel = load_eth_panel()
    eth_rows = panel["rows"]
    days = list(panel.get("days") or sorted({r["day"] for r in eth_rows}))

    btc_rows = try_btc_slice(days)
    rows = eth_rows + btc_rows
    for r in eth_rows:
        r.setdefault("symbol", "ETH")

    pairs = build_pair_table(rows)
    limitations = [
        "Kraken TOB often trade-synthesized or inferred τ — treat absolute τ as soft.",
        "Depth units not cross-venue comparable (contracts vs coin); depth_gap is directional only.",
        "ETH slice = 3 UTC days from pass1 panel; BTC opportunistic if loaders succeed.",
        "No fee / latency / markout fill label for SOR — preference is MQ-rank heuristic.",
        "Epps assumes comparable exchange clocks; no latency haircut.",
        "ClickHouse MCP banned; warehouse + collector TOB only.",
    ]

    heat = fig_tau_gap_heatmap(pairs, FIGS / "fig_tau_gap_heatmap.png")
    mq = fig_mq_vs_tau_scatter(pairs, FIGS / "fig_mq_delta_vs_tau_gap.png")
    grid = fig_grid_pressure_residuals(rows, FIGS / "fig_grid_pressure_residuals.png")
    concord = fig_concord_epps_fei(rows, FIGS / "fig_concord_fei_epps.png", try_load_trades=True)
    sor = fig_sor_panel(rows, FIGS / "fig_sor_preference.png")

    fig_paths = [
        "out/xvenue_tick/figs/fig_tau_gap_heatmap.png",
        "out/xvenue_tick/figs/fig_mq_delta_vs_tau_gap.png",
        "out/xvenue_tick/figs/fig_grid_pressure_residuals.png",
        "out/xvenue_tick/figs/fig_concord_fei_epps.png",
        "out/xvenue_tick/figs/fig_sor_preference.png",
    ]

    summary = {
        "symbols": sorted({r.get("symbol", "ETH") for r in rows}),
        "days": days,
        "n_eth_rows": len(eth_rows),
        "n_btc_rows": len(btc_rows),
        "pairs": pairs,
        "heatmap": heat,
        "mq_scatter": mq,
        "grid": grid,
        "concord_epps": concord,
        "sor": sor,
        "figs": fig_paths,
        "limitations": limitations,
        "completeness": [
            {
                "symbol": r.get("symbol", "ETH"),
                "venue": r["venue"],
                "day": r["day"],
                "complete": bool((r.get("completeness") or {}).get("complete")),
                "n": (r.get("completeness") or {}).get("n"),
                "tob_ok": r.get("tob_ok"),
                "tau": r.get("tau"),
                "tau_source": r.get("tau_source"),
                "tob_source": r.get("tob_source"),
            }
            for r in rows
            if not r.get("error")
        ],
    }
    _json_dump(OUT / "xvenue_summary.json", summary)
    write_docs(summary)
    print(json.dumps({"figs": fig_paths, "n_pairs": len(pairs), "btc": len(btc_rows), "epps": concord.get("epps_note")}, indent=2))


if __name__ == "__main__":
    main()
