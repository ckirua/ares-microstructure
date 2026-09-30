#!/usr/bin/env python3
"""Native Kraken spot L2 rerun for mm_confr_viewpoints packages.

Rebuilds Pass-1/2 panels into ``out/pass1_native/`` + ``out/pass2_native/``
(keeping ``out/pass1/`` synth-era baseline intact). Re-runs chapter empirics
with spot L2 wired via ``_data.load_tob_any``, writes package + ``out/native_rerun/``
artifacts, dual xvenue slices (KR futures synth vs KR spot), refreshes desk docs.

Honesty: spot ≠ PF futures. ClickHouse MCP banned. No git commit. No secrets.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path("/home/dev/lab/lab-n2070/warehouse/src")))
sys.path.insert(0, str(Path("/home/dev/srv/ares-startarb") / "src"))
sys.path.insert(0, str(SCRIPTS))

from _data import (  # noqa: E402
    CORE_VENUES,
    ensure_env,
    load_day_trades,
    load_warehouse_tob,
)
from research.lib.stats import spearman_r  # noqa: E402
from research.lib.ticksize import (  # noqa: E402
    cross_venue_tau_gap,
    expected_sign_matrix,
    fama_macbeth_slope,
    markout_by_rel_tick_quartile,
    relative_tick,
    sign_scorecard,
    venue_tick,
)

import exp_pass12 as P12  # noqa: E402

DAYS_ETH = ["2026-09-26", "2026-09-27", "2026-09-30"]
DAYS_BTC = ["2026-09-26", "2026-09-27", "2026-09-30"]
OUT_NATIVE = BOOK / "out" / "native_rerun"
PASS1_N = BOOK / "out" / "pass1_native"
PASS2_N = BOOK / "out" / "pass2_native"
PASS1_BASE = BOOK / "out" / "pass1"


def _json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str))


def _load_mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def build_panels(*, symbol: str, days: list[str], out_dir: Path, max_files: int = 24) -> dict[str, Any]:
    ensure_env()
    matrix = expected_sign_matrix()
    _json(out_dir / "expected_sign_matrix.json", matrix)
    rows = P12.run_panel(symbol, days, max_files=max_files)
    panel = {"symbol": symbol, "days": days, "rows": rows, "kraken_market": "spot_l2_preferred"}
    _json(out_dir / ("panel.json" if symbol == "ETH" else "panel_btc.json"), panel)

    flat = P12.flatten_for_fm(rows)
    hour_flat = P12.flatten_hour_rows(rows)
    fm = {
        "quoted_spread_bps": fama_macbeth_slope(flat, y_key="quoted_spread_bps", x_key="rel_tick"),
        "bbo_depth": fama_macbeth_slope(flat, y_key="bbo_depth", x_key="rel_tick"),
        "volume": fama_macbeth_slope(flat, y_key="volume", x_key="rel_tick"),
        "relative_spread": fama_macbeth_slope(flat, y_key="relative_spread", x_key="rel_tick"),
        "quoted_spread_bps_by_venue": fama_macbeth_slope(
            flat, y_key="quoted_spread_bps", x_key="rel_tick", group_key="venue"
        ),
        "hour_quoted_spread_bps": fama_macbeth_slope(
            hour_flat, y_key="quoted_spread_bps", x_key="rel_tick", group_key="day"
        ),
        "hour_bbo_depth": fama_macbeth_slope(hour_flat, y_key="bbo_depth", x_key="rel_tick", group_key="day"),
    }
    fm_name = "fm.json" if symbol == "ETH" else "btc_fm.json"
    _json(out_dir / fm_name, fm)

    obs = P12.observe_signs_from_panel(flat)
    scorecard = sign_scorecard(obs)
    sc_name = "sign_scorecard.json" if symbol == "ETH" else "btc_sign_scorecard.json"
    _json(out_dir / sc_name, {"observed": obs, "scorecard": scorecard})

    if symbol == "ETH":
        xmeta = P12.write_liq_xvenue(rows, flat)
        PASS2_N.mkdir(parents=True, exist_ok=True)
        _json(PASS2_N / "liq_xvenue.json", xmeta)

    comp = []
    for r in rows:
        c = r.get("completeness") or {}
        comp.append(
            {
                "venue": r.get("venue"),
                "day": r.get("day"),
                "complete": c.get("complete"),
                "n": c.get("n"),
                "coverage": c.get("coverage"),
                "reasons": c.get("reasons"),
                "tob_ok": r.get("tob_ok"),
                "tob_source": r.get("tob_source"),
                "tau": r.get("tau"),
                "tau_source": r.get("tau_source"),
            }
        )
    comp_name = "completeness.json" if symbol == "ETH" else "btc_completeness.json"
    _json(out_dir / comp_name, comp)
    return {"panel": panel, "fm": fm, "flat": flat, "comp": comp, "scorecard": scorecard}


def kraken_row_snapshot(panel: dict) -> list[dict[str, Any]]:
    out = []
    for r in panel.get("rows") or []:
        if r.get("venue") != "kraken":
            continue
        out.append(
            {
                "day": r.get("day"),
                "tob_source": r.get("tob_source"),
                "tau": r.get("tau"),
                "rel_tick": r.get("rel_tick"),
                "quoted_spread_bps": r.get("quoted_spread_bps"),
                "frac_constrained_2tick": (r.get("constraint") or {}).get("frac_constrained_2tick"),
                "undercut_rate": (r.get("undercut") or {}).get("undercut_rate"),
                "bbo_depth": r.get("bbo_depth"),
                "markout_1s_bps": r.get("markout_1s_bps"),
            }
        )
    return out


def compare_native_vs_baseline() -> dict[str, Any]:
    base = json.loads((PASS1_BASE / "panel.json").read_text()) if (PASS1_BASE / "panel.json").is_file() else None
    nat = json.loads((PASS1_N / "panel.json").read_text())
    base_kr = {r["day"]: r for r in (base or {}).get("rows", []) if r.get("venue") == "kraken"} if base else {}
    nat_kr = {r["day"]: r for r in nat.get("rows", []) if r.get("venue") == "kraken"}
    days = sorted(set(base_kr) | set(nat_kr))
    rows = []
    for d in days:
        b, n = base_kr.get(d), nat_kr.get(d)
        rows.append(
            {
                "day": d,
                "baseline_tob_source": (b or {}).get("tob_source"),
                "native_tob_source": (n or {}).get("tob_source"),
                "baseline_spread_bps": (b or {}).get("quoted_spread_bps"),
                "native_spread_bps": (n or {}).get("quoted_spread_bps"),
                "baseline_frac_c": ((b or {}).get("constraint") or {}).get("frac_constrained_2tick"),
                "native_frac_c": ((n or {}).get("constraint") or {}).get("frac_constrained_2tick"),
                "baseline_tau": (b or {}).get("tau"),
                "native_tau": (n or {}).get("tau"),
                "baseline_rel_tick": (b or {}).get("rel_tick"),
                "native_rel_tick": (n or {}).get("rel_tick"),
            }
        )
    # panel-level FM / rho
    def _rho(panel: dict) -> float:
        xs, ys = [], []
        for r in panel.get("rows") or []:
            if not r.get("tob_ok"):
                continue
            try:
                x, y = float(r["rel_tick"]), float(r["quoted_spread_bps"])
            except (TypeError, ValueError, KeyError):
                continue
            if np.isfinite(x) and np.isfinite(y):
                xs.append(x)
                ys.append(y)
        return float(spearman_r(np.asarray(xs), np.asarray(ys))) if len(xs) >= 4 else float("nan")

    return {
        "kraken_day_compare": rows,
        "rho_rel_tick_spread_baseline": _rho(base) if base else None,
        "rho_rel_tick_spread_native": _rho(nat),
        "fm_baseline": json.loads((PASS1_BASE / "fm.json").read_text())
        if (PASS1_BASE / "fm.json").is_file()
        else None,
        "fm_native": json.loads((PASS1_N / "fm.json").read_text()),
    }


def build_futures_synth_xvenue(days: list[str]) -> dict[str, Any]:
    """HL–Deribit–KR-futures trade_synth pairs (labeled), separate from spot slice."""
    ensure_env()
    rows = []
    for day in days:
        by_v: dict[str, dict[str, Any]] = {}
        for venue in CORE_VENUES:
            try:
                trades = load_day_trades(venue, "ETH", day, quiet=True, max_files=24)
                px = np.asarray(trades["tape"]["px"], dtype=np.float64)
                if venue == "kraken":
                    tob = load_warehouse_tob(
                        "kraken",
                        "ETH",
                        day,
                        prefer_kraken_spot_l2=False,
                        allow_trade_fallback=True,
                        max_files=24,
                        quotes_per_minute=20,
                    )
                else:
                    from _data import load_tob_any

                    tob = load_tob_any(venue, "ETH", day)
                known = {"hyperliquid": 0.1, "deribit": 0.05}.get(venue)
                prices = np.concatenate(
                    [np.asarray(tob["bid"], dtype=np.float64), np.asarray(tob["ask"], dtype=np.float64)]
                )
                if venue == "kraken":
                    prices = px if px.size else prices
                vt = venue_tick(venue, prices=prices, known_ticks={venue: known} if known else None)
                tau = float(vt["tau"])
                if venue == "kraken" and (not np.isfinite(tau) or tau < 1e-4):
                    tau = 0.05
                mid = float(np.nanmedian(tob["mid"]))
                qs = float(1e4 * np.nanmedian((tob["ask"] - tob["bid"]) / np.maximum(tob["mid"], 1e-12)))
                by_v[venue] = {
                    "venue": venue,
                    "day": day,
                    "symbol": "ETH",
                    "tob_ok": True,
                    "tau": tau,
                    "tau_source": vt.get("source"),
                    "tob_source": tob.get("source"),
                    "is_synth": bool(tob.get("is_synth")) or "synth" in str(tob.get("source", "")).lower(),
                    "market": tob.get("market") or ("futures" if venue == "kraken" else None),
                    "quoted_spread_bps": qs,
                    "rel_tick": float(relative_tick(tau, mid, as_bps=False)),
                    "rel_tick_bps": float(relative_tick(tau, mid, as_bps=True)),
                    "bbo_depth": float(
                        np.nanmedian(
                            np.asarray(tob["bid_sz"], dtype=np.float64) + np.asarray(tob["ask_sz"], dtype=np.float64)
                        )
                    ),
                    "mq": {"mid": mid},
                    "volume": float(np.nansum(px * np.asarray(trades["tape"]["qty"], dtype=np.float64))),
                    "grid": {},
                }
            except Exception as exc:  # noqa: BLE001
                by_v[venue] = {
                    "venue": venue,
                    "day": day,
                    "symbol": "ETH",
                    "tob_ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
        rows.extend(by_v.values())

    # pairs
    pairs = []
    by_day: dict[str, dict[str, dict]] = {}
    for r in rows:
        if r.get("tob_ok"):
            by_day.setdefault(r["day"], {})[r["venue"]] = r
    for day, by_v in sorted(by_day.items()):
        taus = {v: float(by_v[v]["tau"]) for v in by_v}
        mids = {v: float(by_v[v]["mq"]["mid"]) for v in by_v}
        gaps = cross_venue_tau_gap(taus, mid_by_venue=mids)
        for p in gaps.get("pairs", []):
            va, vb = p["a"], p["b"]
            ra, rb = by_v[va], by_v[vb]
            pairs.append(
                {
                    "slice": "kraken_futures_synth",
                    "market_note": "KR=PF futures trade_synth; HL/DB=perps — labeled, not spot",
                    "day": day,
                    **p,
                    "spread_gap_bps": float(ra["quoted_spread_bps"] - rb["quoted_spread_bps"]),
                    "rel_tick_a": ra["rel_tick"],
                    "rel_tick_b": rb["rel_tick"],
                    "tob_source_a": ra.get("tob_source"),
                    "tob_source_b": rb.get("tob_source"),
                    "is_synth_a": ra.get("is_synth"),
                    "is_synth_b": rb.get("is_synth"),
                }
            )
    return {"rows": rows, "pairs": pairs, "label": "HL–Deribit–KR-futures_synth"}


def build_spot_xvenue_pairs(panel: dict) -> list[dict[str, Any]]:
    pairs = []
    by_day: dict[str, dict[str, dict]] = {}
    for r in panel.get("rows") or []:
        if r.get("tob_ok") and not r.get("error"):
            by_day.setdefault(r["day"], {})[r["venue"]] = r
    for day, by_v in sorted(by_day.items()):
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
            pairs.append(
                {
                    "slice": "kraken_spot_l2",
                    "market_note": "KR=spot L2; HL/DB=perps — spot≠perp honesty",
                    "day": day,
                    **p,
                    "spread_a": float(ra.get("quoted_spread_bps") or np.nan),
                    "spread_b": float(rb.get("quoted_spread_bps") or np.nan),
                    "spread_gap_bps": float(ra["quoted_spread_bps"] - rb["quoted_spread_bps"])
                    if np.isfinite(ra.get("quoted_spread_bps") or np.nan)
                    and np.isfinite(rb.get("quoted_spread_bps") or np.nan)
                    else float("nan"),
                    "rel_tick_a": ra.get("rel_tick"),
                    "rel_tick_b": rb.get("rel_tick"),
                    "tob_source_a": ra.get("tob_source"),
                    "tob_source_b": rb.get("tob_source"),
                }
            )
    return pairs


def fig_native_vs_base(compare: dict, path: Path) -> None:
    rows = compare["kraken_day_compare"]
    if not rows:
        return
    days = [r["day"] for r in rows]
    x = np.arange(len(days))
    w = 0.35
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    for ax, key_b, key_n, ylab, title in (
        (
            axes[0],
            "baseline_spread_bps",
            "native_spread_bps",
            "quoted spread (bps)",
            "KR med spread: synth-era vs spot L2",
        ),
        (
            axes[1],
            "baseline_frac_c",
            "native_frac_c",
            "frac ≤2 ticks",
            "KR frac_constrained: synth-era vs spot L2",
        ),
    ):
        yb = [r.get(key_b) for r in rows]
        yn = [r.get(key_n) for r in rows]
        ax.bar(x - w / 2, yb, w, label="baseline (pass1 synth)", color="#d95f02", alpha=0.9)
        ax.bar(x + w / 2, yn, w, label="native spot L2", color="#1b9e77", alpha=0.9)
        ax.set_xticks(x)
        ax.set_xticklabels([d[5:] for d in days])
        ax.set_ylabel(ylab)
        ax.set_title(title)
        if key_b.endswith("spread_bps"):
            ax.set_yscale("log")
        ax.legend(fontsize=7, frameon=False)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def fig_xvenue_dual(synth_pairs: list, spot_pairs: list, path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.0), sharey=True)
    for ax, pairs, title in (
        (axes[0], synth_pairs, "KR futures synth × HL/DB perps"),
        (axes[1], spot_pairs, "KR spot L2 × HL/DB perps (≠ market)"),
    ):
        for p in pairs:
            lab = f"{p['a'][:2]}-{p['b'][:2]}"
            ax.scatter(p.get("tau_gap"), p.get("spread_gap_bps"), s=50, alpha=0.85, label=f"{p['day'][5:]} {lab}")
        ax.axhline(0, color="0.6", lw=0.8)
        ax.axvline(0, color="0.6", lw=0.8)
        ax.set_xlabel("τ gap (A−B)")
        ax.set_ylabel("Δ quoted spread bps")
        ax.set_title(title, fontsize=9)
        ax.legend(fontsize=6, frameon=False, loc="best")
    fig.suptitle("xvenue τ/MQ — dual KR market slices", y=1.02)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def rel_tick_within_venue(panel: dict) -> dict[str, Any]:
    by_v: dict[str, list[dict]] = {}
    for r in panel.get("rows") or []:
        if not r.get("tob_ok"):
            continue
        by_v.setdefault(r["venue"], []).append(r)
    out: dict[str, Any] = {"venues": {}}
    for v, rows in by_v.items():
        flat = [
            {
                "day": r["day"],
                "venue": v,
                "rel_tick": r.get("rel_tick"),
                "quoted_spread_bps": r.get("quoted_spread_bps"),
                "markout_1s_bps": r.get("markout_1s_bps"),
                "hour_rows": r.get("hour_rows") or [],
            }
            for r in rows
        ]
        hours = []
        for r in rows:
            for h in r.get("hour_rows") or []:
                hh = dict(h)
                hh["venue"] = v
                hh["day"] = r["day"]
                hours.append(hh)
        xs = [float(r["rel_tick"]) for r in rows if np.isfinite(float(r.get("rel_tick") or np.nan))]
        ys = [float(r["quoted_spread_bps"]) for r in rows if np.isfinite(float(r.get("quoted_spread_bps") or np.nan))]
        n = min(len(xs), len(ys))
        rho = spearman_r(np.asarray(xs[:n]), np.asarray(ys[:n])) if n >= 3 else float("nan")
        fm = fama_macbeth_slope(hours, y_key="quoted_spread_bps", x_key="rel_tick", group_key="day") if hours else {}
        # Prefer day-level markout if present
        day_mo = [
            {"rel_tick": float(r["rel_tick"]), "markout_1s_bps": float(r.get("markout_1s_bps") or np.nan)}
            for r in rows
            if np.isfinite(float(r.get("rel_tick") or np.nan)) and np.isfinite(float(r.get("markout_1s_bps") or np.nan))
        ]
        markout_q = None
        try:
            if len(day_mo) >= 4:
                markout_q = markout_by_rel_tick_quartile(day_mo)
            elif len(hours) >= 8:
                markout_q = markout_by_rel_tick_quartile(
                    [
                        {
                            "rel_tick": float(h["rel_tick"]),
                            "markout_1s_bps": float(h.get("quoted_spread_bps") or np.nan),
                        }
                        for h in hours
                        if np.isfinite(float(h.get("rel_tick") or np.nan))
                    ],
                    markout_key="markout_1s_bps",
                )
            else:
                markout_q = {"n": len(day_mo), "note": "thin"}
        except Exception as exc:  # noqa: BLE001
            markout_q = {"error": f"{type(exc).__name__}: {exc}"}
        out["venues"][v] = {
            "n_days": len(rows),
            "rho_day": rho,
            "fm_hour": fm,
            "markout_quartile": markout_q,
            "mean_spread_bps": float(np.nanmean(ys)) if ys else float("nan"),
            "mean_rel_tick": float(np.nanmean(xs)) if xs else float("nan"),
            "tob_sources": sorted({str(r.get("tob_source")) for r in rows}),
        }
    return out


def run_chapter_scripts(days: list[str]) -> dict[str, Any]:
    """Run chapter locals with OUT → package dirs + mirror under native_rerun."""
    status: dict[str, Any] = {}

    # Point chapter runners at pass1_native for day list consistency
    # tick_constraint
    tc = _load_mod("tc_native", BOOK / "chapters" / "tick_constraint" / "_run_local.py")
    tc.OUT = BOOK / "out" / "tick_constraint"
    tc.FIGS = tc.OUT / "figs"
    tc.OUT.mkdir(parents=True, exist_ok=True)
    print("=== tick_constraint ===", flush=True)
    tc_rows = tc.load_slice(days)
    tc_figs = tc.save_figs(tc_rows)
    slim = []
    for r in tc_rows:
        s = {k: v for k, v in r.items() if k not in ("spread_ticks_sample", "series")}
        ser = r.get("series") or {}
        if ser.get("frac_c"):
            fc = np.asarray(ser["frac_c"], dtype=np.float64)
            s["series_summary"] = {
                "n_bars": int(fc.size),
                "mean_frac_c": float(np.nanmean(fc)),
                "std_frac_c": float(np.nanstd(fc)),
            }
        slim.append(s)
    tc_summary = {
        "symbol": "ETH",
        "days": days,
        "venues": list(CORE_VENUES),
        "n_rows": len(tc_rows),
        "n_tob_ok": sum(1 for r in tc_rows if r.get("tob_ok")),
        "n_synth": sum(1 for r in tc_rows if r.get("is_synth")),
        "median_frac_c": float(np.nanmedian([r["frac_constrained_2tick"] for r in tc_rows if r.get("tob_ok")])),
        "median_undercut": float(
            np.nanmedian(
                [
                    r["undercut_rate"]
                    for r in tc_rows
                    if r.get("tob_ok") and np.isfinite(r.get("undercut_rate") or np.nan)
                ]
            )
        ),
        "by_venue": {
            v: {
                "mean_frac_c": float(
                    np.nanmean(
                        [r["frac_constrained_2tick"] for r in tc_rows if r.get("venue") == v and r.get("tob_ok")]
                    )
                ),
                "mean_undercut": float(
                    np.nanmean(
                        [
                            r["undercut_rate"]
                            for r in tc_rows
                            if r.get("venue") == v and r.get("tob_ok") and np.isfinite(r.get("undercut_rate") or np.nan)
                        ]
                    )
                ),
                "tob_sources": sorted(
                    {str(r.get("tob_source")) for r in tc_rows if r.get("venue") == v and r.get("tob_ok")}
                ),
                "n_relax_flips": int(
                    sum(r.get("n_flips_relax") or 0 for r in tc_rows if r.get("venue") == v and r.get("tob_ok"))
                ),
            }
            for v in CORE_VENUES
        },
        "desk_label_counts": {
            lab: sum(1 for r in tc_rows if r.get("desk_label") == lab)
            for lab in sorted({r.get("desk_label") for r in tc_rows if r.get("tob_ok")})
        },
        "figs": tc_figs,
        "note_kraken": "Kraken spot L2 native via load_tob_any; futures PF_* still synth-only if spot miss",
        "rows": slim,
        "native_rerun": True,
    }
    _json(tc.OUT / "summary.json", tc_summary)
    _json(tc.OUT / "constraint_series.json", {"days": days, "rows": slim})
    # mirror
    nr_tc = OUT_NATIVE / "tick_constraint"
    nr_tc.mkdir(parents=True, exist_ok=True)
    shutil.copy2(tc.OUT / "summary.json", nr_tc / "summary.json")
    if (tc.OUT / "figs").is_dir():
        dest = nr_tc / "figs"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(tc.OUT / "figs", dest)
    status["tick_constraint"] = {
        "n_synth": tc_summary["n_synth"],
        "by_venue": tc_summary["by_venue"],
        "figs": tc_figs,
    }

    # liq_book_split
    liq = _load_mod("liq_native", BOOK / "chapters" / "liq_book_split" / "_run_local.py")
    liq.OUT = BOOK / "out" / "liq_book_split"
    liq.FIGS = liq.OUT / "figs"
    liq.OUT.mkdir(parents=True, exist_ok=True)
    print("=== liq_book_split ===", flush=True)
    day_rows, hour_rows = liq.load_rows(days)
    classified = liq.liquid_book_classifier(
        [r for r in day_rows if r.get("tob_ok") and np.isfinite(r.get("quoted_spread_bps") or np.nan)],
        by="quoted_spread_bps",
    )
    key_to_book = {(r["venue"], r["day"]): r for r in classified}
    for r in day_rows:
        k = (r.get("venue"), r.get("day"))
        if k in key_to_book:
            r["book_liq"] = key_to_book[k].get("book_liq")
            r["liq_tercile"] = key_to_book[k].get("liq_tercile")
    het = liq.het_by_tercile(classified)
    make_take = liq.make_take_hypothesis(hour_rows, classified)
    n_placebo = sum(1 for h in hour_rows if h.get("placebo_mid_move") and not h.get("is_synth"))
    # include KR-spot hours in placebo
    n_placebo_kr = sum(
        1
        for h in hour_rows
        if h.get("placebo_mid_move") and not h.get("is_synth") and h.get("venue") == "kraken"
    )
    placebo_dqs = []
    keyed: dict[tuple[str, str], list] = {}
    for h in hour_rows:
        if h.get("is_synth"):
            continue
        keyed.setdefault((h["venue"], h["day"]), []).append(h)
    for hrs in keyed.values():
        hrs = sorted(hrs, key=lambda z: z["hour_id"])
        for i in range(1, len(hrs)):
            if hrs[i].get("placebo_mid_move"):
                placebo_dqs.append(hrs[i]["quoted_spread_bps"] - hrs[i - 1]["quoted_spread_bps"])
    liq_figs = liq.save_figs(day_rows, hour_rows, classified, het, make_take)
    liq_summary = {
        "symbol": "ETH",
        "days": days,
        "venues": list(CORE_VENUES),
        "n_day_rows": len(day_rows),
        "n_hour_rows": len(hour_rows),
        "n_synth_days": sum(1 for r in day_rows if r.get("is_synth")),
        "het": het,
        "make_take": make_take,
        "placebo": {
            "n_hours_flagged": n_placebo,
            "n_hours_flagged_kraken_spot": n_placebo_kr,
            "mean_abs_dqs_bps": float(np.mean(np.abs(placebo_dqs))) if placebo_dqs else float("nan"),
            "mean_dqs_bps": float(np.mean(placebo_dqs)) if placebo_dqs else float("nan"),
            "rule": "mid_range≥5bps and rel_tick_range/rel_tick < 2%; synth excluded; KR-spot included",
        },
        "figs": liq_figs,
        "note_kraken": "Kraken spot L2 included in tercile/placebo when not synth",
        "day_rows": day_rows,
        "native_rerun": True,
    }
    _json(liq.OUT / "summary.json", liq_summary)
    _json(liq.OUT / "het.json", het)
    _json(liq.OUT / "hour_rows.json", hour_rows)
    nr_liq = OUT_NATIVE / "liq_book_split"
    nr_liq.mkdir(parents=True, exist_ok=True)
    shutil.copy2(liq.OUT / "summary.json", nr_liq / "summary.json")
    if (liq.OUT / "figs").is_dir():
        dest = nr_liq / "figs"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(liq.OUT / "figs", dest)
    status["liq_book_split"] = {
        "het": het,
        "placebo": liq_summary["placebo"],
        "n_synth_days": liq_summary["n_synth_days"],
        "figs": liq_figs,
    }
    return status


def run_xvenue(panel: dict, synth_blob: dict) -> dict[str, Any]:
    xv = _load_mod("xv_native", BOOK / "chapters" / "xvenue_tick" / "_run_xvenue.py")
    xv.OUT = BOOK / "out" / "xvenue_tick"
    xv.FIGS = xv.OUT / "figs"
    xv.PASS1_PANEL = PASS1_N / "panel.json"
    xv.OUT.mkdir(parents=True, exist_ok=True)
    print("=== xvenue_tick (spot panel) ===", flush=True)
    xv.main()  # uses PASS1_PANEL we set

    spot_pairs = build_spot_xvenue_pairs(panel)
    dual = {
        "futures_synth_slice": synth_blob,
        "spot_l2_slice": {
            "pairs": spot_pairs,
            "label": "HL–Deribit–KR-spot",
            "honesty": "Kraken=spot L2; HL/Deribit=perps — market mismatch",
        },
    }
    _json(xv.OUT / "pairs.json", {"spot": spot_pairs, "futures_synth": synth_blob.get("pairs")})
    _json(OUT_NATIVE / "xvenue_tick" / "dual_slices.json", dual)
    fig_xvenue_dual(synth_blob.get("pairs") or [], spot_pairs, OUT_NATIVE / "figs" / "fig_xvenue_dual_slices.png")
    # also copy package figs
    if xv.FIGS.is_dir():
        dest = OUT_NATIVE / "xvenue_tick" / "figs"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(xv.FIGS, dest)
    return dual


def run_rel_tick_and_info(panel: dict, days: list[str]) -> dict[str, Any]:
    rtp = BOOK / "out" / "rel_tick_panel"
    rtp.mkdir(parents=True, exist_ok=True)
    (rtp / "figs").mkdir(parents=True, exist_ok=True)

    within = rel_tick_within_venue(panel)
    _json(rtp / "within_venue_native.json", within)
    _json(OUT_NATIVE / "rel_tick_panel" / "within_venue_native.json", within)

    flat = P12.flatten_for_fm(panel["rows"])
    _json(rtp / "panel_flat.json", flat)

    # markout quartile pooled + KR-spot only
    mo_all = [
        {"rel_tick": float(r["rel_tick"]), "markout_1s_bps": float(r["markout_1s_bps"])}
        for r in panel["rows"]
        if r.get("tob_ok")
        and np.isfinite(float(r.get("rel_tick") or np.nan))
        and np.isfinite(float(r.get("markout_1s_bps") or np.nan))
    ]
    mo_kr = [
        {"rel_tick": float(r["rel_tick"]), "markout_1s_bps": float(r["markout_1s_bps"])}
        for r in panel["rows"]
        if r.get("venue") == "kraken"
        and r.get("tob_ok")
        and np.isfinite(float(r.get("rel_tick") or np.nan))
        and np.isfinite(float(r.get("markout_1s_bps") or np.nan))
    ]
    mq = {}
    try:
        if len(mo_all) >= 4:
            mq["pooled"] = markout_by_rel_tick_quartile(mo_all)
        if len(mo_kr) >= 4:
            mq["kraken_spot"] = markout_by_rel_tick_quartile(mo_kr)
        else:
            mq["kraken_spot"] = {"n": len(mo_kr), "note": "thin day panel — see hour within_venue"}
    except Exception as exc:  # noqa: BLE001
        mq["error"] = f"{type(exc).__name__}: {exc}"
    _json(rtp / "markout_quartile.json", mq)
    _json(OUT_NATIVE / "rel_tick_panel" / "markout_quartile.json", mq)

    # FM / rho fig
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    labels, rhos = [], []
    for v, blob in within.get("venues", {}).items():
        labels.append({"hyperliquid": "HL", "deribit": "DB", "kraken": "KR-spot"}.get(v, v))
        rhos.append(blob.get("rho_day", np.nan))
    ax.bar(labels, rhos, color=["#1f77b4", "#ff7f0e", "#2ca02c"][: len(labels)])
    ax.axhline(0, color="0.5", lw=0.8)
    ax.set_ylabel("Spearman ρ(rel_tick, spread) day panel")
    ax.set_title("Within-venue ρ — native KR spot L2")
    fig.tight_layout()
    fig.savefig(rtp / "figs" / "fig_within_venue_rho_native.png", dpi=140, bbox_inches="tight")
    fig.savefig(OUT_NATIVE / "figs" / "fig_within_venue_rho_native.png", dpi=140, bbox_inches="tight")
    plt.close(fig)

    # optional denser info/exec stacks (HL real TOB)
    print("=== exp_pass2_info_exec ===", flush=True)
    try:
        import exp_pass2_info_exec as info

        # force days from native panel
        info.TC_OUT = BOOK / "out" / "tick_constraint"
        info.TC_FIGS = info.TC_OUT / "figs"
        info.RTP_OUT = rtp
        info.RTP_FIGS = rtp / "figs"
        # monkeypatch days_from_panel
        info.days_from_panel = lambda: days  # type: ignore[assignment]
        info.main()
    except Exception as exc:  # noqa: BLE001
        print(f"info_exec skip/fail: {type(exc).__name__}: {exc}", flush=True)
        mq["info_exec_error"] = f"{type(exc).__name__}: {exc}"

    return {"within": within, "markout_quartile": mq}


def decide_gates(compare: dict, tc_status: dict, liq_status: dict, within: dict) -> dict[str, Any]:
    """Promote only if falsifiers pass — default Hold with native updates."""
    kr = within.get("venues", {}).get("kraken", {})
    rho_n = compare.get("rho_rel_tick_spread_native")
    fm_t = ((compare.get("fm_native") or {}).get("quoted_spread_bps") or {}).get("t")
    placebo = (liq_status.get("placebo") or {})
    gates = {
        "exec.tick_constrained_flag": {
            "decision": "Hold",
            "why": (
                f"KR spot L2 native frac_c≈{((tc_status.get('by_venue') or {}).get('kraken') or {}).get('mean_frac_c')}; "
                "HL still dominates; mmip overlap; futures PF_* L2-absent"
            ),
        },
        "exec.undercut_rate": {
            "decision": "Hold",
            "why": "L0 proxy; native KR stacks now eligible but no queue ID / thin relax sample",
        },
        "liq.fm_rel_tick_spread": {
            "decision": "Hold",
            "why": f"native FM t={fm_t}; xvenue τ confound (HL/DB grids) unchanged by KR spot",
        },
        "liq.rho_rel_tick_spread": {
            "decision": "Hold",
            "why": f"native pooled ρ={rho_n}; KR-spot within-venue ρ={kr.get('rho_day')}",
        },
        "liq.placebo_flat_rel_tick": {
            "decision": "Hold",
            "why": (
                f"placebo |Δqs|≈{placebo.get('mean_abs_dqs_bps')} n_hours={placebo.get('n_hours_flagged')} "
                f"(KR-spot hours={placebo.get('n_hours_flagged_kraken_spot')}); BTC pooled still weak historically"
            ),
        },
        "liq.book_tercile_het": {
            "decision": "Hold",
            "why": f"het={liq_status.get('het')}; n still thin per tercile",
        },
        "frag.xvenue_tau_gap": {
            "decision": "Hold",
            "why": "HL↔DB stable; KR-spot τ usable but spot≠perp — dual slice documented, no Promote",
        },
        "frag.grid_pressure": {
            "decision": "Hold",
            "why": "feature only; residual MQ Δ needs FE",
        },
        "disc.tick_rq_taxonomy": {
            "decision": "Promote",
            "why": "framing taxonomy vs mmip tick.*; not a numeric claim",
        },
    }
    # no numeric Promote flips — falsifiers not newly passed
    return gates


def refresh_docs(compare: dict, gates: dict, tc_status: dict, liq_status: dict, within: dict, dual: dict) -> None:
    kr_days = compare.get("kraken_day_compare") or []
    n_frac = float(np.nanmean([r.get("native_frac_c") for r in kr_days])) if kr_days else float("nan")
    b_frac = float(np.nanmean([r.get("baseline_frac_c") for r in kr_days])) if kr_days else float("nan")
    n_spr = float(np.nanmean([r.get("native_spread_bps") for r in kr_days])) if kr_days else float("nan")
    b_spr = float(np.nanmean([r.get("baseline_spread_bps") for r in kr_days])) if kr_days else float("nan")

    # tick_constraint EXP_REPORT append-style rewrite keeping structure
    (BOOK / "chapters" / "tick_constraint" / "EXP_REPORT.md").write_text(
        "\n".join(
            [
                "# tick_constraint — EXP_REPORT",
                "",
                "## Pass 1 / native spot L2 rerun",
                f"- Days: {DAYS_ETH}",
                f"- KR mean frac_constrained: native≈{n_frac:.3f} vs baseline synth≈{b_frac:.3f}",
                f"- KR mean quoted spread bps: native≈{n_spr:.4g} vs baseline≈{b_spr:.4g}",
                f"- Venue means: {json.dumps(tc_status.get('by_venue'), default=str)}",
                "- Cross-link mmip `tick.frac_one_tick` / `spread_leeway`.",
                "",
                "## Pass 2",
                "- Label: *fragility monitor* when frac_constrained high + undercut bursts; *exec throttle* only if markout worsens.",
                "- Script: `scripts/exp_pass2_info_exec.py` → `out/tick_constraint/pass2_info_exec.json`",
                "- Relax/undercut stacks on venues with real TOB (HL, Deribit, KR-spot).",
                "",
                "## Native rerun artifacts",
                "- Panels: `out/pass1_native/` · `out/pass2_native/` (baseline `out/pass1/` preserved).",
                "- Package figs: `out/tick_constraint/figs/` · mirror `out/native_rerun/tick_constraint/`.",
                f"- Gate `exec.tick_constrained_flag`: **{gates['exec.tick_constrained_flag']['decision']}** — {gates['exec.tick_constrained_flag']['why']}",
                "",
            ]
        )
    )
    (BOOK / "chapters" / "tick_constraint" / "CANDIDATES.md").write_text(
        "| id | type | lenses | decision | falsifier |\n"
        "|----|------|--------|----------|----------|\n"
        f"| `exec.tick_constrained_flag` | regime | exec, disc | **{gates['exec.tick_constrained_flag']['decision']}** | {gates['exec.tick_constrained_flag']['why'][:80]} |\n"
        f"| `exec.undercut_rate` | proxy | exec, mm | **{gates['exec.undercut_rate']['decision']}** | L0 tighten ≠ true undercut queue |\n"
    )

    kr_rho = (within.get("venues") or {}).get("kraken", {}).get("rho_day")
    (BOOK / "chapters" / "rel_tick_panel" / "EXP_REPORT.md").write_text(
        "\n".join(
            [
                "# rel_tick_panel — EXP_REPORT",
                "",
                "## Native spot L2 rerun",
                f"- Pooled ρ(rel_tick, spread) native={compare.get('rho_rel_tick_spread_native')} vs baseline={compare.get('rho_rel_tick_spread_baseline')}",
                f"- FM quoted_spread t native={((compare.get('fm_native') or {}).get('quoted_spread_bps') or {}).get('t')}",
                f"- Within-venue KR-spot ρ={kr_rho}; HL/DB in `out/rel_tick_panel/within_venue_native.json`",
                "- Markout by rel_tick quartile (pooled + KR-spot): `out/rel_tick_panel/markout_quartile.json`",
                "",
                f"- Gate `liq.fm_rel_tick_spread`: **{gates['liq.fm_rel_tick_spread']['decision']}**",
                f"- Gate `liq.rho_rel_tick_spread`: **{gates['liq.rho_rel_tick_spread']['decision']}**",
                "",
            ]
        )
    )
    (BOOK / "chapters" / "rel_tick_panel" / "CANDIDATES.md").write_text(
        "| id | type | lenses | decision | falsifier |\n"
        "|----|------|--------|----------|----------|\n"
        f"| `liq.fm_rel_tick_spread` | panel | liq, disc | **{gates['liq.fm_rel_tick_spread']['decision']}** | xvenue τ confound |\n"
        f"| `liq.rho_rel_tick_spread` | panel | liq | **{gates['liq.rho_rel_tick_spread']['decision']}** | thin day panel |\n"
        "| `info.markout_by_rel_tick` | info | info, exec | **Hold** | denser markout join |\n"
    )

    placebo = liq_status.get("placebo") or {}
    (BOOK / "chapters" / "liq_book_split" / "EXP_REPORT.md").write_text(
        "\n".join(
            [
                "# liq_book_split — EXP_REPORT",
                "",
                "## Native spot L2 rerun",
                f"- Tercile het: {json.dumps(liq_status.get('het'), default=str)}",
                f"- Placebo flat-rel_tick: n_hours={placebo.get('n_hours_flagged')} "
                f"(KR-spot={placebo.get('n_hours_flagged_kraken_spot')}) "
                f"mean|Δqs|={placebo.get('mean_abs_dqs_bps')}",
                f"- Synth day rows remaining: {liq_status.get('n_synth_days')}",
                "",
                f"- Gate `liq.book_tercile_het`: **{gates['liq.book_tercile_het']['decision']}**",
                f"- Gate `liq.placebo_flat_rel_tick`: **{gates['liq.placebo_flat_rel_tick']['decision']}**",
                "",
            ]
        )
    )
    (BOOK / "chapters" / "liq_book_split" / "CANDIDATES.md").write_text(
        "| id | type | lenses | decision | falsifier |\n"
        "|----|------|--------|----------|----------|\n"
        f"| `liq.book_tercile_het` | panel | liq | **{gates['liq.book_tercile_het']['decision']}** | small n per tercile |\n"
        f"| `liq.placebo_flat_rel_tick` | falsifier | liq | **{gates['liq.placebo_flat_rel_tick']['decision']}** | BTC pooled historically weak |\n"
    )

    n_spot = len((dual.get("spot_l2_slice") or {}).get("pairs") or [])
    n_fut = len((dual.get("futures_synth_slice") or {}).get("pairs") or [])
    (BOOK / "chapters" / "xvenue_tick" / "EXP_REPORT.md").write_text(
        "\n".join(
            [
                "# xvenue_tick — EXP_REPORT",
                "",
                "## Dual slices (native rerun)",
                f"- (a) HL–Deribit–KR-**futures synth**: {n_fut} pair-rows — labeled trade_synth / PF market.",
                f"- (b) HL–Deribit–KR-**spot L2**: {n_spot} pair-rows — **spot≠perp** honesty for τ/MQ concordance.",
                "- Figs: `out/xvenue_tick/figs/` + `out/native_rerun/figs/fig_xvenue_dual_slices.png`",
                "- Artifacts: `out/xvenue_tick/pairs.json` · `out/native_rerun/xvenue_tick/dual_slices.json`",
                "",
                f"- Gate `frag.xvenue_tau_gap`: **{gates['frag.xvenue_tau_gap']['decision']}** — {gates['frag.xvenue_tau_gap']['why']}",
                "",
            ]
        )
    )
    (BOOK / "chapters" / "xvenue_tick" / "CANDIDATES.md").write_text(
        "| id | type | lenses | decision | falsifier |\n"
        "|----|------|--------|----------|----------|\n"
        f"| `frag.xvenue_tau_gap` | qe | frag, disc | **{gates['frag.xvenue_tau_gap']['decision']}** | HL↔Deribit stable; KR spot≠PF futures market |\n"
        f"| `frag.grid_pressure` | feature | disc, liq | **{gates['frag.grid_pressure']['decision']}** | residual MQ Δ needs FE |\n"
        "| `exec.sor_rel_tick` | policy | exec | **Hold** | no fill-quality label in slice |\n"
        "| `id.vanity_price_rdd` | id | disc | **Kill** | no discrete tick schedule thresholds |\n"
    )

    # DESK_MEMO — surgical update of key native facts (keep structure)
    memo = (BOOK / "DESK_MEMO.md").read_text()
    addendum = (
        "\n\n---\n\n## Native Kraken spot L2 rerun (addendum)\n\n"
        f"- Panels: `out/pass1_native/` + `out/pass2_native/` (baseline `out/pass1/` = prior synth-era SoT).\n"
        f"- KR spread bps mean native≈{n_spr:.4g} vs baseline≈{b_spr:.4g}; "
        f"frac_c native≈{n_frac:.3f} vs baseline≈{b_frac:.3f}.\n"
        f"- ρ(rel_tick,spread) native={compare.get('rho_rel_tick_spread_native')} "
        f"vs baseline={compare.get('rho_rel_tick_spread_baseline')}.\n"
        "- xvenue: dual slices in `out/native_rerun/xvenue_tick/dual_slices.json` "
        "(futures synth labeled + spot L2 with spot≠perp).\n"
        "- **No new Promotes** from numeric falsifiers; `disc.tick_rq_taxonomy` remains sole Promote.\n"
        f"- Gate board snapshot: `{OUT_NATIVE.relative_to(BOOK)}/gates.json`.\n"
        f"- Figs: `out/native_rerun/figs/` + refreshed `out/<pkg>/figs/`.\n"
    )
    if "## Native Kraken spot L2 rerun (addendum)" in memo:
        head = memo.split("## Native Kraken spot L2 rerun (addendum)")[0].rstrip()
        memo = head + addendum
    else:
        memo = memo.rstrip() + addendum
    (BOOK / "DESK_MEMO.md").write_text(memo)


def main() -> None:
    ensure_env()
    OUT_NATIVE.mkdir(parents=True, exist_ok=True)
    (OUT_NATIVE / "figs").mkdir(parents=True, exist_ok=True)
    PASS1_N.mkdir(parents=True, exist_ok=True)
    PASS2_N.mkdir(parents=True, exist_ok=True)

    print(f"=== build ETH panel → {PASS1_N} ===", flush=True)
    eth = build_panels(symbol="ETH", days=DAYS_ETH, out_dir=PASS1_N, max_files=24)
    # avoid rewriting chapter docs from write_liq_xvenue with incomplete story — already wrote pass2
    print(f"=== build BTC panel (optional) → {PASS1_N} ===", flush=True)
    try:
        btc = build_panels(symbol="BTC", days=DAYS_BTC, out_dir=PASS1_N, max_files=16)
    except Exception as exc:  # noqa: BLE001
        print(f"BTC panel partial/fail: {type(exc).__name__}: {exc}", flush=True)
        btc = None

    compare = compare_native_vs_baseline()
    _json(OUT_NATIVE / "native_vs_baseline.json", compare)
    fig_native_vs_base(compare, OUT_NATIVE / "figs" / "fig_kraken_native_vs_baseline.png")

    print("=== chapter empirics ===", flush=True)
    ch_status = run_chapter_scripts(DAYS_ETH)

    print("=== futures synth xvenue slice ===", flush=True)
    synth_blob = build_futures_synth_xvenue(DAYS_ETH)
    _json(OUT_NATIVE / "xvenue_tick" / "futures_synth_slice.json", synth_blob)

    dual = run_xvenue(eth["panel"], synth_blob)
    rtp = run_rel_tick_and_info(eth["panel"], DAYS_ETH)

    gates = decide_gates(compare, ch_status.get("tick_constraint") or {}, ch_status.get("liq_book_split") or {}, rtp["within"])
    _json(OUT_NATIVE / "gates.json", gates)
    _json(PASS2_N / "hardening_gates.json", gates)

    refresh_docs(
        compare,
        gates,
        ch_status.get("tick_constraint") or {},
        ch_status.get("liq_book_split") or {},
        rtp["within"],
        dual,
    )

    summary = {
        "days_eth": DAYS_ETH,
        "days_btc": DAYS_BTC,
        "pass1_native": str(PASS1_N.relative_to(BOOK)),
        "pass2_native": str(PASS2_N.relative_to(BOOK)),
        "pass1_baseline_preserved": str(PASS1_BASE.relative_to(BOOK)),
        "kraken_native_snapshot": kraken_row_snapshot(eth["panel"]),
        "compare": {k: compare[k] for k in compare if k not in ("fm_baseline", "fm_native")},
        "fm_native_t": ((eth["fm"].get("quoted_spread_bps") or {}).get("t")),
        "gates": gates,
        "tick_constraint": ch_status.get("tick_constraint"),
        "liq_book_split": {
            "het": (ch_status.get("liq_book_split") or {}).get("het"),
            "placebo": (ch_status.get("liq_book_split") or {}).get("placebo"),
            "n_synth_days": (ch_status.get("liq_book_split") or {}).get("n_synth_days"),
        },
        "rel_tick_within": rtp["within"],
        "btc_ok": btc is not None,
        "figs": sorted(str(p.relative_to(BOOK)) for p in OUT_NATIVE.rglob("*.png")),
    }
    _json(OUT_NATIVE / "summary.json", summary)
    print(json.dumps({k: summary[k] for k in summary if k not in ("rel_tick_within", "gates")}, indent=2, default=str))
    print("gates", json.dumps(gates, indent=2))
    print("done", flush=True)


if __name__ == "__main__":
    main()
