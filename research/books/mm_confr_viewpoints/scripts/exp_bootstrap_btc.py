from __future__ import annotations
#!/usr/bin/env python3
"""Pass-2.5 hardening: day-block bootstrap CIs + BTC replication.

Writes ``out/hardening/`` JSON + PNGs, refreshes DESK_MEMO signal board and
touched CANDIDATES. Promote only if falsifiers pass.

ClickHouse MCP banned. No git commit.
"""


import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from ares_micro.stats import bootstrap_ci, spearman_r  # noqa: E402
from ares_micro.book.ticksize import fama_macbeth_slope  # noqa: E402

OUT = BOOK / "out" / "hardening"
FIGS = OUT / "figs"
N_BOOT = 1000
SEED = 42
NATIVE_VENUES = ("hyperliquid", "deribit", "kraken")  # Kraken spot L2 native; trade_synth still filtered


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str))


def _finite(v: Any) -> bool:
    if v is None:
        return False
    try:
        return bool(np.isfinite(float(v)))
    except (TypeError, ValueError):
        return False


def _is_synth_row(r: dict[str, Any]) -> bool:
    src = str(r.get("tob_source") or (r.get("constraint") or {}).get("tob_source") or "")
    if r.get("is_synth") is True:
        return True
    return "trade_synth" in src.lower() or "synth" in src.lower()


def _flat_day_rows(panel: dict[str, Any], *, native_only: bool) -> list[dict[str, Any]]:
    out = []
    for r in panel.get("rows") or []:
        if not r.get("tob_ok"):
            continue
        synth = _is_synth_row(r)
        if native_only and synth:
            continue
        cons = r.get("constraint") or {}
        uc = r.get("undercut") or {}
        out.append(
            {
                "day": r["day"],
                "venue": r["venue"],
                "symbol": r.get("symbol") or panel.get("symbol"),
                "rel_tick": r.get("rel_tick"),
                "quoted_spread_bps": r.get("quoted_spread_bps"),
                "frac_c": cons.get("frac_constrained_2tick"),
                "undercut_rate": uc.get("undercut_rate"),
                "tau": r.get("tau"),
                "complete": bool((r.get("completeness") or {}).get("complete")),
                "is_synth": synth,
                "tob_source": r.get("tob_source"),
            }
        )
    return out


def _ols_slope(xs: np.ndarray, ys: np.ndarray) -> float:
    m = np.isfinite(xs) & np.isfinite(ys)
    x, y = xs[m], ys[m]
    if x.size < 3:
        return float("nan")
    xc = x - x.mean()
    yc = y - y.mean()
    den = float((xc * xc).sum())
    if den <= 0:
        return float("nan")
    return float((xc * yc).sum() / den)


def day_block_bootstrap(
    rows: list[dict[str, Any]],
    stat_fn: Callable[[list[dict[str, Any]]], float],
    *,
    n_boot: int = N_BOOT,
    seed: int = SEED,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Resample UTC days with replacement; recompute scalar statistic."""
    days = sorted({r["day"] for r in rows if r.get("day") is not None})
    by_day: dict[str, list[dict[str, Any]]] = {d: [] for d in days}
    for r in rows:
        if r.get("day") in by_day:
            by_day[r["day"]].append(r)
    point = float(stat_fn(rows))
    if len(days) < 1:
        return {
            "point": point,
            "lo": float("nan"),
            "hi": float("nan"),
            "n_days": 0,
            "n_rows": len(rows),
            "n_boot": n_boot,
            "method": "day_block",
        }
    rng = np.random.default_rng(seed)
    boots: list[float] = []
    for _ in range(n_boot):
        draw = [days[i] for i in rng.integers(0, len(days), size=len(days))]
        sample: list[dict[str, Any]] = []
        for d in draw:
            sample.extend(by_day[d])
        v = float(stat_fn(sample))
        if np.isfinite(v):
            boots.append(v)
    arr = np.asarray(boots, dtype=np.float64)
    if arr.size:
        lo, hi = np.quantile(arr, [alpha / 2, 1 - alpha / 2])
    else:
        lo = hi = float("nan")
    return {
        "point": point,
        "lo": float(lo),
        "hi": float(hi),
        "n_days": len(days),
        "n_rows": len(rows),
        "n_boot": int(n_boot),
        "n_finite_boots": int(arr.size),
        "method": "day_block",
        "alpha": alpha,
    }


def time_split_stat(
    rows: list[dict[str, Any]],
    stat_fn: Callable[[list[dict[str, Any]]], float],
) -> dict[str, Any]:
    days = sorted({r["day"] for r in rows if r.get("day") is not None})
    mid = max(1, len(days) // 2)
    early, late = set(days[:mid]), set(days[mid:])
    e_rows = [r for r in rows if r["day"] in early]
    l_rows = [r for r in rows if r["day"] in late]
    e = float(stat_fn(e_rows)) if e_rows else float("nan")
    l = float(stat_fn(l_rows)) if l_rows else float("nan")
    same_sign = bool(np.isfinite(e) and np.isfinite(l) and np.sign(e) == np.sign(l) and e != 0)
    return {
        "days": days,
        "early_days": sorted(early),
        "late_days": sorted(late),
        "early": e,
        "late": l,
        "same_sign": same_sign,
        "both_finite": bool(np.isfinite(e) and np.isfinite(l)),
    }


def placebo_dqs(hour_rows: list[dict[str, Any]]) -> list[float]:
    """Hour-to-hour Δ quoted_spread_bps on placebo-flagged native hours."""
    keyed: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for h in hour_rows:
        if h.get("is_synth"):
            continue
        keyed.setdefault((h["venue"], h["day"]), []).append(h)
    out: list[float] = []
    for hrs in keyed.values():
        hrs = sorted(hrs, key=lambda z: z["hour_id"])
        for i in range(1, len(hrs)):
            if hrs[i].get("placebo_mid_move"):
                qs0 = hrs[i - 1].get("quoted_spread_bps")
                qs1 = hrs[i].get("quoted_spread_bps")
                if qs0 is not None and qs1 is not None and np.isfinite(qs0) and np.isfinite(qs1):
                    out.append(float(qs1) - float(qs0))
    return out


def placebo_stat_from_hours(hour_rows: list[dict[str, Any]]) -> float:
    dqs = placebo_dqs(hour_rows)
    if not dqs:
        return float("nan")
    return float(np.mean(np.abs(dqs)))


def _attach_day_to_hour_stat(hour_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten placebo |Δqs| observations tagged by day for day-block bootstrap."""
    keyed: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for h in hour_rows:
        if h.get("is_synth"):
            continue
        keyed.setdefault((h["venue"], h["day"]), []).append(h)
    obs: list[dict[str, Any]] = []
    for (venue, day), hrs in keyed.items():
        hrs = sorted(hrs, key=lambda z: z["hour_id"])
        for i in range(1, len(hrs)):
            if hrs[i].get("placebo_mid_move"):
                qs0 = hrs[i - 1].get("quoted_spread_bps")
                qs1 = hrs[i].get("quoted_spread_bps")
                if qs0 is not None and qs1 is not None and np.isfinite(qs0) and np.isfinite(qs1):
                    obs.append(
                        {
                            "day": day,
                            "venue": venue,
                            "abs_dqs": abs(float(qs1) - float(qs0)),
                            "dqs": float(qs1) - float(qs0),
                        }
                    )
    return obs


def load_liq_runner():
    path = BOOK / "chapters" / "liq_book_split" / "_run_local.py"
    spec = importlib.util.spec_from_file_location("liq_book_split_run", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_hours(symbol: str, days: list[str], known_tau: dict[str, float]) -> tuple[list, list]:
    mod = load_liq_runner()
    mod.SYMBOL = symbol
    mod.KNOWN_TAU = known_tau
    return mod.load_rows(days)


def rho_xy(rows: list[dict[str, Any]], x_key: str, y_key: str) -> float:
    pairs = [
        (float(r[x_key]), float(r[y_key]))
        for r in rows
        if _finite(r.get(x_key)) and _finite(r.get(y_key))
    ]
    if len(pairs) < 3:
        return float("nan")
    xs = np.asarray([p[0] for p in pairs], dtype=np.float64)
    ys = np.asarray([p[1] for p in pairs], dtype=np.float64)
    return spearman_r(xs, ys)


def fm_pooled_t(rows: list[dict[str, Any]]) -> float:
    fm = fama_macbeth_slope(rows, y_key="quoted_spread_bps", x_key="rel_tick", group_key="day")
    return float(fm.get("t") if fm.get("t") is not None else float("nan"))


def fm_pooled_slope(rows: list[dict[str, Any]]) -> float:
    fm = fama_macbeth_slope(rows, y_key="quoted_spread_bps", x_key="rel_tick", group_key="day")
    return float(fm.get("mean_slope") if fm.get("mean_slope") is not None else float("nan"))


def within_venue_hour_slope(hour_rows: list[dict[str, Any]], venue: str) -> float:
    sub = [h for h in hour_rows if h.get("venue") == venue and not h.get("is_synth")]
    xs = np.asarray([float(h["rel_tick"]) for h in sub], dtype=np.float64)
    ys = np.asarray([float(h["quoted_spread_bps"]) for h in sub], dtype=np.float64)
    return _ols_slope(xs, ys)


def mean_frac_c(rows: list[dict[str, Any]]) -> float:
    vals = [float(r["frac_c"]) for r in rows if _finite(r.get("frac_c"))]
    return float(np.mean(vals)) if vals else float("nan")


def analyze_symbol(
    symbol: str,
    panel: dict[str, Any],
    hour_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    days = panel.get("days") or sorted({r["day"] for r in panel.get("rows") or []})
    all_flat = _flat_day_rows(panel, native_only=False)
    native = _flat_day_rows(panel, native_only=True)
    n_complete = sum(1 for r in panel.get("rows") or [] if (r.get("completeness") or {}).get("complete"))
    n_tob = sum(1 for r in panel.get("rows") or [] if r.get("tob_ok"))
    n_synth = sum(1 for r in all_flat if r.get("is_synth"))

    # --- placebo flat-rel_tick ---
    placebo_obs = _attach_day_to_hour_stat(hour_rows)
    n_placebo = sum(1 for h in hour_rows if h.get("placebo_mid_move") and not h.get("is_synth"))

    def _mean_abs(obs: list[dict[str, Any]]) -> float:
        vals = [float(o["abs_dqs"]) for o in obs if _finite(o.get("abs_dqs"))]
        return float(np.mean(vals)) if vals else float("nan")

    def _mean_dqs(obs: list[dict[str, Any]]) -> float:
        vals = [float(o["dqs"]) for o in obs if _finite(o.get("dqs"))]
        return float(np.mean(vals)) if vals else float("nan")

    placebo_boot = day_block_bootstrap(placebo_obs, _mean_abs, seed=SEED + 1)
    placebo_signed = day_block_bootstrap(placebo_obs, _mean_dqs, seed=SEED + 2)
    # also unit bootstrap on abs_dqs vector (hour-level, not day-block)
    abs_vals = np.asarray([o["abs_dqs"] for o in placebo_obs], dtype=np.float64)
    placebo_unit = bootstrap_ci(abs_vals, np.mean, n_boot=N_BOOT, seed=SEED + 3) if abs_vals.size else {
        "n": 0,
        "point": float("nan"),
        "lo": float("nan"),
        "hi": float("nan"),
    }
    placebo_ts = time_split_stat(placebo_obs, _mean_abs)
    # venue-split (native) — Deribit sparse L2 can dominate |Δqs|
    by_venue_placebo: dict[str, Any] = {}
    for v in NATIVE_VENUES:
        v_obs = [o for o in placebo_obs if o.get("venue") == v]
        by_venue_placebo[v] = {
            "n": len(v_obs),
            "day_block_ci": day_block_bootstrap(v_obs, _mean_abs, seed=SEED + 4 + hash(v) % 50),
        }

    # --- FM pooled (all venues incl synth labeled) + native-only ---
    fm_all = fama_macbeth_slope(all_flat, y_key="quoted_spread_bps", x_key="rel_tick")
    fm_native = fama_macbeth_slope(native, y_key="quoted_spread_bps", x_key="rel_tick")
    # With only HL+DB, CS n=2 → FM skips groups needing ≥3. Use day-pooled OLS / Spearman instead.
    fm_boot_slope = day_block_bootstrap(all_flat, fm_pooled_slope, seed=SEED + 10)
    fm_boot_t = day_block_bootstrap(all_flat, fm_pooled_t, seed=SEED + 11)
    rho_all = day_block_bootstrap(
        all_flat, lambda rs: rho_xy(rs, "rel_tick", "quoted_spread_bps"), seed=SEED + 12
    )
    rho_native = day_block_bootstrap(
        native, lambda rs: rho_xy(rs, "rel_tick", "quoted_spread_bps"), seed=SEED + 13
    )
    fm_ts = time_split_stat(all_flat, fm_pooled_slope)
    rho_ts = time_split_stat(all_flat, lambda rs: rho_xy(rs, "rel_tick", "quoted_spread_bps"))

    # within-venue hour OLS (native only)
    within: dict[str, Any] = {}
    for v in NATIVE_VENUES:
        v_hours = [h for h in hour_rows if h.get("venue") == v and not h.get("is_synth")]

        def _slope(rs: list[dict[str, Any]], _v=v) -> float:
            # rs may be day-resampled hours
            xs = np.asarray([float(h["rel_tick"]) for h in rs], dtype=np.float64)
            ys = np.asarray([float(h["quoted_spread_bps"]) for h in rs], dtype=np.float64)
            return _ols_slope(xs, ys)

        within[v] = {
            "n_hours": len(v_hours),
            "ols_slope": within_venue_hour_slope(hour_rows, v),
            "spearman": rho_xy(v_hours, "rel_tick", "quoted_spread_bps"),
            "boot_slope": day_block_bootstrap(v_hours, _slope, seed=SEED + 20 + hash(v) % 97),
            "time_split": time_split_stat(v_hours, _slope),
            "note": "within-venue hour OLS qs~rel_tick; native TOB only",
        }

    # --- constraint frac by venue ---
    constraint: dict[str, Any] = {}
    for v in ("hyperliquid", "deribit", "kraken"):
        sub = [r for r in all_flat if r["venue"] == v]
        synth = any(r.get("is_synth") for r in sub)
        constraint[v] = {
            "mean_frac_c": mean_frac_c(sub),
            "boot": day_block_bootstrap(sub, mean_frac_c, seed=SEED + 30 + hash(v) % 97),
            "time_split": time_split_stat(sub, mean_frac_c),
            "is_synth": synth,
            "n_days": len(sub),
            "excluded_from_native": synth,
        }

    # --- undercut ρ ---
    # ρ(undercut, frac_c) and ρ(undercut, rel_tick) on native day rows
    undercut = {
        "rho_uc_frac_c": {
            "boot": day_block_bootstrap(
                native, lambda rs: rho_xy(rs, "undercut_rate", "frac_c"), seed=SEED + 40
            ),
            "time_split": time_split_stat(native, lambda rs: rho_xy(rs, "undercut_rate", "frac_c")),
        },
        "rho_uc_rel_tick": {
            "boot": day_block_bootstrap(
                native, lambda rs: rho_xy(rs, "undercut_rate", "rel_tick"), seed=SEED + 41
            ),
            "time_split": time_split_stat(native, lambda rs: rho_xy(rs, "undercut_rate", "rel_tick")),
        },
        "note": "trade_synth excluded; Kraken spot L2 included when tob_source=kraken_spot_l2_rebuild",
    }

    n_kraken_native = sum(
        1
        for r in all_flat
        if r["venue"] == "kraken" and not r.get("is_synth")
    )
    return {
        "symbol": symbol,
        "days": days,
        "completeness": {
            "n_venue_days": len(panel.get("rows") or []),
            "n_complete": n_complete,
            "n_tob": n_tob,
            "n_synth": n_synth,
            "n_kraken_native_spot": n_kraken_native,
            "native_venues": list(NATIVE_VENUES),
            "kraken_label": (
                "spot L2 native (warehouse:kraken_spot_l2_rebuild); "
                "futures PF_* still trade_synth / no L2 in S3"
            ),
        },
        "placebo_flat_rel_tick": {
            "n_hours_flagged": n_placebo,
            "n_dqs_obs": len(placebo_obs),
            "mean_abs_dqs_bps": placebo_boot["point"],
            "day_block_ci": placebo_boot,
            "signed_mean_dqs": placebo_signed,
            "unit_boot_ci": placebo_unit,
            "time_split": placebo_ts,
            "by_venue": by_venue_placebo,
            "rule": "mid_range≥5bps and rel_tick_range/rel_tick < 2%; synth excluded",
        },
        "fm_quoted_spread_rel_tick": {
            "pooled_all_venues": fm_all,
            "pooled_native_only": fm_native,
            "boot_mean_slope": fm_boot_slope,
            "boot_t": fm_boot_t,
            "rho_all": rho_all,
            "rho_native": rho_native,
            "time_split_slope": fm_ts,
            "time_split_rho": rho_ts,
            "within_venue_hour": within,
            "xvenue_confound": True,
            "note": (
                "Pooled day FM dominated by HL vs Deribit τ gap; "
                "within-venue hour slopes are the cleaner object"
            ),
        },
        "constraint_frac_by_venue": constraint,
        "undercut_rho": undercut,
    }


def decide_gates(eth: dict[str, Any], btc: dict[str, Any]) -> dict[str, Any]:
    """Promote only if falsifiers pass; else Hold with explicit blocker."""
    gates: dict[str, Any] = {}

    # taxonomy stays Promote
    gates["disc.tick_rq_taxonomy"] = {
        "decision": "Promote",
        "why": "framing taxonomy vs mmip tick.*; not a numeric claim",
    }

    # placebo: Promote if (1) day-block CI for mean|Δqs| tight near 0 on ETH,
    # (2) BTC replicates (also near 0), (3) time-split both finite & small.
    # Threshold: hi < 0.05 bps (tiny vs typical spreads) and BTC hi < 0.05.
    ep = eth["placebo_flat_rel_tick"]
    bp = btc["placebo_flat_rel_tick"]
    e_ci = ep["day_block_ci"]
    b_ci = bp["day_block_ci"]
    e_ts = ep["time_split"]
    b_ts = bp["time_split"]
    placebo_tight = (
        np.isfinite(e_ci.get("hi") or np.nan)
        and float(e_ci["hi"]) < 0.05
        and float(e_ci["point"]) < 0.02
        and ep["n_dqs_obs"] >= 20
    )
    btc_replicates = (
        np.isfinite(b_ci.get("hi") or np.nan)
        and float(b_ci["hi"]) < 0.05
        and float(b_ci["point"]) < 0.02
        and bp["n_dqs_obs"] >= 10
    )
    ts_ok = bool(e_ts.get("both_finite")) and bool(b_ts.get("both_finite"))
    # early/late abs means should both be small
    ts_small = (
        np.isfinite(e_ts.get("early") or np.nan)
        and np.isfinite(e_ts.get("late") or np.nan)
        and float(e_ts["early"]) < 0.05
        and float(e_ts["late"]) < 0.05
    )
    if placebo_tight and btc_replicates and ts_ok and ts_small:
        gates["liq.placebo_flat_rel_tick"] = {
            "decision": "Promote",
            "why": (
                f"ETH mean|Δqs|={e_ci['point']:.4g} dayCI=[{e_ci['lo']:.4g},{e_ci['hi']:.4g}] "
                f"n={ep['n_dqs_obs']}; BTC={b_ci['point']:.4g} CI=[{b_ci['lo']:.4g},{b_ci['hi']:.4g}]; "
                "time-split small — falsifier for rel_tick→MQ when rel_tick flat"
            ),
            "label": "disc/liq falsifier monitor (not tradable)",
        }
    else:
        blockers = []
        if not placebo_tight:
            blockers.append(
                f"ETH CI not tight (point={e_ci.get('point')}, hi={e_ci.get('hi')}, n={ep.get('n_dqs_obs')})"
            )
        if not btc_replicates:
            btc_hl = (bp.get("by_venue") or {}).get("hyperliquid") or {}
            btc_hl_ci = btc_hl.get("day_block_ci") or {}
            blockers.append(
                f"BTC pooled weak (point={b_ci.get('point'):.4g}, hi={b_ci.get('hi'):.4g}, n={bp.get('n_dqs_obs')}); "
                f"HL-only clean (point={btc_hl_ci.get('point')}, n={btc_hl.get('n')}) — Deribit sparse-L2 outlier"
            )
        if not (ts_ok and ts_small):
            blockers.append(f"time-split ETH early/late={e_ts.get('early')}/{e_ts.get('late')}")
        gates["liq.placebo_flat_rel_tick"] = {
            "decision": "Hold",
            "why": "blockers: " + "; ".join(blockers),
            "label": "falsifier candidate — needs clean CI+BTC",
        }

    # FM: keep Hold — xvenue confound; within-venue may still be Hold if slope dominated by mid drift
    efm = eth["fm_quoted_spread_rel_tick"]
    within_hl = (efm["within_venue_hour"].get("hyperliquid") or {})
    within_note = (
        f"HL hour slope={within_hl.get('ols_slope')}; "
        f"boot={within_hl.get('boot_slope', {}).get('point')}"
    )
    gates["liq.fm_rel_tick_spread"] = {
        "decision": "Hold",
        "why": (
            f"pooled day FM t={efm['pooled_all_venues'].get('t')}; "
            f"ρ day-block={efm['rho_all'].get('point'):.3g} "
            f"CI=[{efm['rho_all'].get('lo'):.3g},{efm['rho_all'].get('hi'):.3g}]; "
            f"xvenue τ confound; {within_note}"
        ),
    }
    gates["liq.rho_rel_tick_spread"] = {
        "decision": "Hold",
        "why": (
            f"Spearman ρ={efm['rho_all']['point']:.3g} "
            f"dayCI=[{efm['rho_all']['lo']:.3g},{efm['rho_all']['hi']:.3g}]; "
            f"native ρ={efm['rho_native']['point']:.3g}; BTC ρ={btc['fm_quoted_spread_rel_tick']['rho_all']['point']:.3g}"
        ),
    }

    # constraint
    ec = eth["constraint_frac_by_venue"]
    gates["exec.tick_constrained_flag"] = {
        "decision": "Hold",
        "why": (
            f"HL frac={ec['hyperliquid']['mean_frac_c']:.3f} "
            f"dayCI=[{ec['hyperliquid']['boot']['lo']:.3f},{ec['hyperliquid']['boot']['hi']:.3f}]; "
            f"DB={ec['deribit']['mean_frac_c']:.3f}; "
            "Kraken spot L2 included when present (futures PF still synth); overlaps mmip frac_one_tick"
        ),
    }

    # undercut
    eu = eth["undercut_rho"]["rho_uc_frac_c"]["boot"]
    gates["exec.undercut_rate"] = {
        "decision": "Hold",
        "why": (
            f"ρ(uc,frac_c)={eu['point']:.3g} dayCI=[{eu['lo']:.3g},{eu['hi']:.3g}] "
            f"native n_days={eu['n_days']}; L0 proxy, no queue ID; synth excluded"
        ),
    }

    # unchanged Holds / Kills from prior hardening
    gates["disc.expected_sign_matrix"] = {
        "decision": "Hold",
        "why": "codified pp.20–29; crypto scorecard fragile on 3-day slice",
    }
    gates["frag.xvenue_tau_gap"] = {
        "decision": "Hold",
        "why": "HL↔Deribit τ gap stable on ETH+BTC; Kraken spot L2 native but spot≠PF futures market",
    }
    gates["frag.grid_pressure"] = {
        "decision": "Hold",
        "why": "feature computed; residual MQ Δ needs FE / wider sample",
    }
    gates["id.lse_nasdaq_rdd_literal"] = {"decision": "Kill", "why": "no sovereign tick ladder / vanity RD"}
    gates["id.welfare_tick"] = {"decision": "Kill", "why": "unobservable"}
    gates["id.sec_ipo_channel"] = {"decision": "Kill", "why": "out of scope"}
    gates["disc.sign_scorecard_tradable"] = {
        "decision": "Kill",
        "why": "hit_rate≈0.33 on ETH slice; not a tradable signal",
    }
    gates["liq.book_tercile_het"] = {
        "decision": "Hold",
        "why": "n=3 per tercile; BTC replicates pattern but still thin",
    }

    return gates


def save_figs(eth: dict[str, Any], btc: dict[str, Any], gates: dict[str, Any]) -> list[str]:
    FIGS.mkdir(parents=True, exist_ok=True)
    produced: list[str] = []

    # 1) placebo CI bars ETH vs BTC
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    labels, points, los, his = [], [], [], []
    for lab, blob in (("ETH", eth), ("BTC", btc)):
        ci = blob["placebo_flat_rel_tick"]["day_block_ci"]
        labels.append(lab)
        points.append(ci["point"])
        los.append(ci["lo"])
        his.append(ci["hi"])
    x = np.arange(len(labels))
    yerr = np.vstack([np.asarray(points) - np.asarray(los), np.asarray(his) - np.asarray(points)])
    ax.bar(x, points, color=["#2a6f97", "#8b5e34"], alpha=0.85, width=0.55)
    ax.errorbar(x, points, yerr=yerr, fmt="none", ecolor="black", capsize=5, lw=1.2)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("mean |Δqs| (bps) on placebo hours")
    ax.set_title("Placebo flat-rel_tick — day-block 95% CI")
    ax.axhline(0, color="gray", lw=0.8)
    fig.tight_layout()
    p = FIGS / "placebo_ci_eth_btc.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    produced.append(p.name)

    # 2) FM / rho forest
    fig, ax = plt.subplots(figsize=(8.0, 4.5))
    rows = []
    for lab, blob in (("ETH pooled ρ", eth["fm_quoted_spread_rel_tick"]["rho_all"]),
                      ("ETH native ρ", eth["fm_quoted_spread_rel_tick"]["rho_native"]),
                      ("BTC pooled ρ", btc["fm_quoted_spread_rel_tick"]["rho_all"]),
                      ("BTC native ρ", btc["fm_quoted_spread_rel_tick"]["rho_native"])):
        rows.append((lab, blob["point"], blob["lo"], blob["hi"]))
    y = np.arange(len(rows))
    ax.axvline(0, color="gray", lw=0.8)
    for i, (lab, pt, lo, hi) in enumerate(rows):
        ax.plot([lo, hi], [i, i], color="#1b4332", lw=2)
        ax.plot([pt], [i], "o", color="#d62828", ms=7)
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows])
    ax.set_xlabel("Spearman ρ(rel_tick, quoted_spread) day-block 95% CI")
    ax.set_title("FM channel — rank corr (x-venue confound intact)")
    fig.tight_layout()
    p = FIGS / "fm_rho_forest.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    produced.append(p.name)

    # 3) constraint by venue
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.0), sharey=True)
    for ax, blob, title in ((axes[0], eth, "ETH"), (axes[1], btc, "BTC")):
        cons = blob["constraint_frac_by_venue"]
        venues = ["hyperliquid", "deribit", "kraken"]
        pts = [cons[v]["boot"]["point"] for v in venues]
        los = [cons[v]["boot"]["lo"] for v in venues]
        his = [cons[v]["boot"]["hi"] for v in venues]
        colors = ["#2a6f97", "#40916c", "#adb5bd"]
        x = np.arange(len(venues))
        ax.bar(x, pts, color=colors, alpha=0.9, width=0.6)
        yerr = np.vstack([np.asarray(pts) - np.asarray(los), np.asarray(his) - np.asarray(pts)])
        ax.errorbar(x, pts, yerr=yerr, fmt="none", ecolor="black", capsize=4)
        ax.set_xticks(x)
        ax.set_xticklabels(["HL", "DB", "KR*\nsynth"], fontsize=9)
        ax.set_title(title)
        ax.set_ylim(0, 1.05)
    axes[0].set_ylabel("frac constrained (≤2 ticks)")
    fig.suptitle("Constraint frac by venue — day-block CI (*Kraken synth hatched if present)", y=1.02)
    fig.tight_layout()
    p = FIGS / "constraint_frac_ci.png"
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    produced.append(p.name)

    # 4) undercut rho
    fig, ax = plt.subplots(figsize=(7.5, 4.0))
    rows = []
    for sym, blob in (("ETH", eth), ("BTC", btc)):
        for key, label in (
            ("rho_uc_frac_c", "ρ(uc,frac_c)"),
            ("rho_uc_rel_tick", "ρ(uc,rel_tick)"),
        ):
            b = blob["undercut_rho"][key]["boot"]
            rows.append((f"{sym} {label}", b["point"], b["lo"], b["hi"]))
    y = np.arange(len(rows))
    ax.axvline(0, color="gray", lw=0.8)
    for i, (lab, pt, lo, hi) in enumerate(rows):
        ax.plot([lo, hi], [i, i], color="#3d405b", lw=2)
        ax.plot([pt], [i], "o", color="#e07a5f", ms=7)
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows], fontsize=9)
    ax.set_xlabel("Spearman ρ — day-block 95% CI (native TOB)")
    ax.set_title("Undercut correlations")
    fig.tight_layout()
    p = FIGS / "undercut_rho_forest.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    produced.append(p.name)

    # 5) within-venue slopes
    fig, ax = plt.subplots(figsize=(8.0, 4.2))
    rows = []
    for sym, blob in (("ETH", eth), ("BTC", btc)):
        for v in NATIVE_VENUES:
            w = blob["fm_quoted_spread_rel_tick"]["within_venue_hour"][v]
            b = w["boot_slope"]
            rows.append((f"{sym} {v[:2].upper()} hour OLS", b["point"], b["lo"], b["hi"]))
    y = np.arange(len(rows))
    ax.axvline(0, color="gray", lw=0.8)
    for i, (lab, pt, lo, hi) in enumerate(rows):
        ax.plot([lo, hi], [i, i], color="#264653", lw=2)
        ax.plot([pt], [i], "o", color="#f4a261", ms=7)
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows], fontsize=8)
    ax.set_xlabel("OLS slope quoted_spread_bps ~ rel_tick (hour)")
    ax.set_title("Within-venue hour FM-style slopes — day-block CI")
    fig.tight_layout()
    p = FIGS / "within_venue_fm_slopes.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    produced.append(p.name)

    # 6) gate board
    fig, ax = plt.subplots(figsize=(10.0, 5.5))
    ax.axis("off")
    lines = ["Pass-2.5 gate board", ""]
    for gid, g in gates.items():
        lines.append(f"{g['decision']:7s}  {gid}")
    ax.text(0.02, 0.98, "\n".join(lines), va="top", ha="left", family="monospace", fontsize=9)
    fig.tight_layout()
    p = FIGS / "gate_board.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    produced.append(p.name)

    # 7) time-split placebo
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    width = 0.35
    for i, (lab, blob) in enumerate((("ETH", eth), ("BTC", btc))):
        ts = blob["placebo_flat_rel_tick"]["time_split"]
        ax.bar(i - width / 2, ts["early"], width, color="#2a6f97", label="early" if i == 0 else None)
        ax.bar(i + width / 2, ts["late"], width, color="#8b5e34", label="late" if i == 0 else None)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["ETH", "BTC"])
    ax.set_ylabel("mean |Δqs| bps")
    ax.set_title("Placebo time-split falsifier")
    ax.legend()
    fig.tight_layout()
    p = FIGS / "placebo_time_split.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    produced.append(p.name)

    return produced


def update_desk_memo(artifact: dict[str, Any]) -> None:
    gates = artifact["gates"]
    eth = artifact["eth"]
    btc = artifact["btc"]
    n_promote = sum(1 for g in gates.values() if g["decision"] == "Promote")
    n_hold = sum(1 for g in gates.values() if g["decision"] == "Hold")
    n_kill = sum(1 for g in gates.values() if g["decision"] == "Kill")

    board_lines = [
        "| ID | Formula / clock | Monitor | Tradable | Exec throttle | Decision |",
        "|----|-----------------|---------|----------|---------------|----------|",
    ]
    meta = {
        "disc.tick_rq_taxonomy": ("RQ taxonomy · framing", "yes", "no", "no"),
        "liq.placebo_flat_rel_tick": ("|Δqs| | mid↑ & rel_tick flat", "yes", "no", "no"),
        "disc.expected_sign_matrix": ("deck pp.20–29 signs", "yes", "no", "no"),
        "liq.fm_rel_tick_spread": ("FM y~τ/mid · UTC-day/hour", "maybe", "no", "no"),
        "liq.rho_rel_tick_spread": ("Spearman(τ/mid, spread)", "maybe", "no", "no"),
        "exec.tick_constrained_flag": ("spread≤2 ticks", "yes", "no", "maybe"),
        "exec.undercut_rate": ("L0 tighten ≤1.5 ticks", "maybe", "no", "maybe"),
        "frag.xvenue_tau_gap": ("HL↔Deribit↔Kraken Δτ", "yes", "no", "maybe"),
        "frag.grid_pressure": ("Δ(τ/mid) | τ fixed", "maybe", "no", "no"),
        "liq.book_tercile_het": ("liquid×rel_tick het", "maybe", "no", "no"),
        "id.lse_nasdaq_rdd_literal": ("equity RDD template", "no", "no", "no"),
        "id.welfare_tick": ("welfare", "no", "no", "no"),
        "id.sec_ipo_channel": ("SEC/IPO", "no", "no", "no"),
        "disc.sign_scorecard_tradable": ("sign hit-rate", "no", "no", "no"),
    }
    # stable order
    order = [
        "disc.tick_rq_taxonomy",
        "liq.placebo_flat_rel_tick",
        "disc.expected_sign_matrix",
        "liq.fm_rel_tick_spread",
        "liq.rho_rel_tick_spread",
        "exec.tick_constrained_flag",
        "exec.undercut_rate",
        "frag.xvenue_tau_gap",
        "frag.grid_pressure",
        "liq.book_tercile_het",
        "id.lse_nasdaq_rdd_literal",
        "id.welfare_tick",
        "id.sec_ipo_channel",
        "disc.sign_scorecard_tradable",
    ]
    for gid in order:
        g = gates[gid]
        formula, mon, trad, thr = meta[gid]
        why = g["why"][:100].replace("|", "/")
        board_lines.append(
            f"| `{gid}` | {formula} | {mon} | {trad} | {thr} | **{g['decision']}** — {why} |"
        )

    ep = eth["placebo_flat_rel_tick"]["day_block_ci"]
    bp = btc["placebo_flat_rel_tick"]["day_block_ci"]
    days = ", ".join(eth["days"])

    desk = f"""# Desk memo — Tick Size Viewpoints (Rindi et al. MMCV #3 2014)

**Audience:** crypto MM / SOR / execution / taker / risk / research  
**Source:** Rindi et al. *Tick Size: Theory and Evidence* slides (Paris 2014-12-11) → `research/books/mm_confr_viewpoints/`  
**Philosophy:** lenses `risk | info | exec | disc | cont | liq | mm` — tick objects are **not** automatically tradable.  
**Data:** warehouse trades + collector/warehouse TOB on **HL + Deribit + Kraken** — **no ClickHouse MCP**.  
**Program status:** Pass-2.5 hardened — **{n_promote} Promote / {n_hold} Hold / {n_kill} Kill**.  
**SoT:** [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) · Lib: [`../../lib/ticksize.py`](../../lib/ticksize.py) · Loaders: [`scripts/_data.py`](scripts/_data.py) · Bootstrap: [`scripts/exp_bootstrap_btc.py`](scripts/exp_bootstrap_btc.py).

---

## 1. Desk jobs × intended outputs

| Job | Deck object | Tentative desk label | Status |
|-----|-------------|----------------------|--------|
| **Quote regime monitor** | Relative tick; frac 1-tick | Risk / quoting regime (cross-link mmip) | Hold — overlap |
| **Make / take aggressiveness** | Tick-constrained undercutting | Fragility monitor | Hold |
| **Liquidity split** | Liquid vs less-liquid × Δ(rel tick) | Heterogeneous MQ | Hold — thin terciles |
| **Placebo flat-rel_tick** | Mid moves with flat τ/mid → |Δqs|≈0 | Channel falsifier | {gates['liq.placebo_flat_rel_tick']['decision']} |
| **SOR / x-venue** | Cross-venue τ gap + grid pressure | Venue preference | Hold |
| **Prediction scorecard** | Expected-sign matrix pp. 20–29 | Theory→crypto hit rate | Hold matrix / Kill as tradable |
| **Competing defs** | vs mmip `tick.*` | Cross-link only | Promote taxonomy framing |

---

## 2. Signal board (Pass 2.5 — day-block bootstrap + BTC)

{chr(10).join(board_lines)}

**Kill list:** literal LSE/Nasdaq RDD; welfare; SEC/IPO; sign-scorecard-as-tradable  
**Hold blockers:** x-venue τ confound for FM; Kraken futures PF still L2-absent (spot L2 now native); mmip descriptor overlap; thin Deribit L2 cadence

### Bootstrap snapshot (day-block 95% CI)

| Object | ETH | BTC |
|--------|-----|-----|
| placebo mean\\|Δqs\\| bps | {ep['point']:.4g} [{ep['lo']:.4g},{ep['hi']:.4g}] n={eth['placebo_flat_rel_tick']['n_dqs_obs']} | {bp['point']:.4g} [{bp['lo']:.4g},{bp['hi']:.4g}] n={btc['placebo_flat_rel_tick']['n_dqs_obs']} |
| ρ(rel_tick, spread) | {eth['fm_quoted_spread_rel_tick']['rho_all']['point']:.3g} [{eth['fm_quoted_spread_rel_tick']['rho_all']['lo']:.3g},{eth['fm_quoted_spread_rel_tick']['rho_all']['hi']:.3g}] | {btc['fm_quoted_spread_rel_tick']['rho_all']['point']:.3g} [{btc['fm_quoted_spread_rel_tick']['rho_all']['lo']:.3g},{btc['fm_quoted_spread_rel_tick']['rho_all']['hi']:.3g}] |
| HL frac_constrained | {eth['constraint_frac_by_venue']['hyperliquid']['mean_frac_c']:.3f} | {btc['constraint_frac_by_venue']['hyperliquid']['mean_frac_c']:.3f} |
| ρ(uc, frac_c) native | {eth['undercut_rho']['rho_uc_frac_c']['boot']['point']:.3g} | {btc['undercut_rho']['rho_uc_frac_c']['boot']['point']:.3g} |

Artifacts: `out/hardening/hardening_pass25.json` · figs under `out/hardening/figs/`.

---

## 3. Venue completeness (locked)

| Venue | Role | TOB in slice | Notes |
|-------|------|--------------|-------|
| Hyperliquid | DEX anchor | Yes (collector + l2_rebuild) | native TOB |
| Deribit | CEX perps | Yes (warehouse L2 TOB) | native TOB |
| Kraken | CEX spot L2 + futures tape | Spot `l2_rebuild` (`spot|ETH/USD`); futures `PF_*` trade_synth | **Spot native** for MQ/constraint; PF futures still no L2 in S3 |

Slice days: {days}  
ETH complete venue-days {eth['completeness']['n_complete']}/{eth['completeness']['n_venue_days']}; TOB {eth['completeness']['n_tob']}.  
BTC complete venue-days {btc['completeness']['n_complete']}/{btc['completeness']['n_venue_days']}; TOB {btc['completeness']['n_tob']} — panel `out/pass1/panel_btc.json`.

**Figures:** `out/hardening/figs/` (placebo CI, FM ρ forest, constraint, undercut, within-venue slopes, time-split, gate board) + package figs under `out/<pkg>/figs/`. Notebook: [`notebooks/desk_synthesis.ipynb`](notebooks/desk_synthesis.ipynb).

---

## 4. Next gate (optional backlog)

1. Kraken futures PF L2 ingest (spot L2 already wired; drop remaining trade_synth for PF joins).  
2. Within-venue hourly FM with vol/OFI controls (remove residual mid-drift).  
3. Constraint-relax event study for exec throttle Promote (HL rarely relaxes).  
4. Widen days before flipping FM / undercut gates.
"""
    (BOOK / "DESK_MEMO.md").write_text(desk)


def update_candidates(gates: dict[str, Any]) -> None:
    placebo = gates["liq.placebo_flat_rel_tick"]
    # liq_book_split
    (BOOK / "chapters" / "liq_book_split" / "CANDIDATES.md").write_text(
        "| id | type | lenses | decision | falsifier |\n"
        "|----|------|--------|----------|----------|\n"
        "| `liq.book_tercile_het` | panel | liq | **Hold** | small n per tercile; BTC same thin |\n"
        f"| `liq.placebo_flat_rel_tick` | falsifier | liq, disc | **{placebo['decision']}** | {placebo['why'][:160]} |\n"
    )
    # rel_tick_panel
    fm = gates["liq.fm_rel_tick_spread"]
    rho = gates["liq.rho_rel_tick_spread"]
    (BOOK / "chapters" / "rel_tick_panel" / "CANDIDATES.md").write_text(
        "| id | type | lenses | decision | falsifier |\n"
        "|----|------|--------|----------|----------|\n"
        f"| `liq.fm_rel_tick_spread` | panel | liq, disc | **Hold** | {fm['why'][:160]} |\n"
        f"| `liq.rho_rel_tick_spread` | panel | liq | **Hold** | {rho['why'][:160]} |\n"
        "| `liq.fm_rel_tick_depth` | panel | liq | **Hold** | thin TOB cross-section |\n"
        "| `info.markout_by_rel_tick` | info | info, exec | **Hold** | need denser markout join |\n"
    )
    # tick_constraint — preserve any extra rows (relax/burst) below the two core gates
    cons = gates["exec.tick_constrained_flag"]
    uc = gates["exec.undercut_rate"]
    tc_path = BOOK / "chapters" / "tick_constraint" / "CANDIDATES.md"
    extra_rows: list[str] = []
    if tc_path.is_file():
        for line in tc_path.read_text().splitlines():
            if line.startswith("| `") and "exec.tick_constrained_flag" not in line and "exec.undercut_rate" not in line:
                if "id |" not in line:
                    extra_rows.append(line)
    tc_lines = [
        "| id | type | lenses | decision | falsifier |",
        "|----|------|--------|----------|----------|",
        f"| `exec.tick_constrained_flag` | regime | exec, disc | **Hold** | {cons['why'][:160]} |",
        f"| `exec.undercut_rate` | proxy | exec, mm | **Hold** | {uc['why'][:160]} |",
    ]
    tc_lines.extend(extra_rows)
    tc_path.write_text("\n".join(tc_lines) + "\n")
    # xvenue — keep Hold with synth note
    xv = gates["frag.xvenue_tau_gap"]
    gp = gates["frag.grid_pressure"]
    (BOOK / "chapters" / "xvenue_tick" / "CANDIDATES.md").write_text(
        "| id | type | lenses | decision | falsifier |\n"
        "|----|------|--------|----------|----------|\n"
        f"| `frag.xvenue_tau_gap` | qe | frag, disc | **Hold** | {xv['why'][:160]} |\n"
        f"| `frag.grid_pressure` | feature | disc, liq | **Hold** | {gp['why'][:160]} |\n"
        "| `exec.sor_rel_tick` | policy | exec | **Hold** | no fill-quality label in slice |\n"
        "| `id.vanity_price_rdd` | id | disc | **Kill** | no discrete tick schedule thresholds |\n"
    )


def update_chapter_index(gates: dict[str, Any]) -> None:
    n_promote = sum(1 for g in gates.values() if g["decision"] == "Promote")
    n_hold = sum(1 for g in gates.values() if g["decision"] == "Hold")
    n_kill = sum(1 for g in gates.values() if g["decision"] == "Kill")
    idx_path = BOOK / "CHAPTER_INDEX.md"
    idx = idx_path.read_text()
    idx = re.sub(
        r"\*\*Program status:\*\*.*",
        f"**Program status:** **Pass-2.5 hardened** — {n_promote} Promote / {n_hold} Hold / {n_kill} Kill "
        "(ETH+BTC day-block bootstrap in `out/hardening/`).",
        idx,
        count=1,
    )
    promote_rows = [
        "| Candidate | risk | info | exec | disc | cont | liq | mm | Ch | One-line use |",
        "|-----------|:----:|:----:|:----:|:----:|:----:|:---:|:--:|----|--------------|",
        "| `disc.tick_rq_taxonomy` |  |  |  | ✓ |  |  | ✓ | ch00_overview | Taxonomy vs mmip tick.*; reading order |",
    ]
    if gates["liq.placebo_flat_rel_tick"]["decision"] == "Promote":
        promote_rows.append(
            "| `liq.placebo_flat_rel_tick` |  |  |  | ✓ |  | ✓ |  | liq_book_split | "
            "Falsifier: |Δqs|≈0 when mid moves & rel_tick flat |"
        )
    holds = []
    kills = []
    for gid, g in gates.items():
        if g["decision"] == "Hold":
            holds.append(f"- `{gid}` — {g['why'][:120]}")
        elif g["decision"] == "Kill":
            kills.append(f"- `{gid}` — {g['why'][:120]}")
    promote_table = (
        "## Promote rollup\n\n"
        + "\n".join(promote_rows)
        + "\n\n**Kill:**\n"
        + "\n".join(kills)
        + "\n\n**Hold:**\n"
        + "\n".join(holds)
        + "\n"
    )
    idx = re.sub(
        r"## Promote rollup\n\n.*?\n---\n\n## Crypto adaptation",
        promote_table + "\n---\n\n## Crypto adaptation",
        idx,
        count=1,
        flags=re.S,
    )
    idx_path.write_text(idx)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    FIGS.mkdir(parents=True, exist_ok=True)

    eth_panel = _load_json(BOOK / "out" / "pass1" / "panel.json")
    btc_panel = _load_json(BOOK / "out" / "pass1" / "panel_btc.json")
    days = eth_panel.get("days") or ["2026-09-26", "2026-09-27", "2026-09-30"]

    # ETH hours: prefer cached liq_book_split hour_rows
    eth_hours_path = BOOK / "out" / "liq_book_split" / "hour_rows.json"
    if eth_hours_path.is_file():
        print("loading cached ETH hour_rows", flush=True)
        eth_hours = _load_json(eth_hours_path)
    else:
        print("building ETH hour_rows", flush=True)
        _, eth_hours = build_hours("ETH", days, {"hyperliquid": 0.1, "deribit": 0.05})

    # BTC hours: build (or use cache if present)
    btc_hours_path = OUT / "hour_rows_btc.json"
    if btc_hours_path.is_file():
        print("loading cached BTC hour_rows", flush=True)
        btc_hours = _load_json(btc_hours_path)
    else:
        print("building BTC hour_rows (HL+DB+KR)", flush=True)
        _, btc_hours = build_hours("BTC", days, {"hyperliquid": 1.0, "deribit": 0.5})
        # ensure placebo flags (load_rows already applies placebo_flags)
        _write_json(btc_hours_path, btc_hours)

    print(f"ETH hours={len(eth_hours)} BTC hours={len(btc_hours)}", flush=True)

    eth = analyze_symbol("ETH", eth_panel, eth_hours)
    btc = analyze_symbol("BTC", btc_panel, btc_hours)
    gates = decide_gates(eth, btc)
    figs = save_figs(eth, btc, gates)

    n_promote = sum(1 for g in gates.values() if g["decision"] == "Promote")
    n_hold = sum(1 for g in gates.values() if g["decision"] == "Hold")
    n_kill = sum(1 for g in gates.values() if g["decision"] == "Kill")

    artifact = {
        "pass": "2.5",
        "n_boot": N_BOOT,
        "seed": SEED,
        "method": "day_block_bootstrap",
        "native_tob_note": (
            "Kraken spot L2 (l2_rebuild) counted native; "
            "futures PF_* trade_synth still excluded — no futures L2 in S3"
        ),
        "eth": eth,
        "btc": btc,
        "gates": gates,
        "counts": {"promote": n_promote, "hold": n_hold, "kill": n_kill},
        "figs": figs,
    }
    _write_json(OUT / "hardening_pass25.json", artifact)
    _write_json(OUT / "gates.json", gates)
    _write_json(
        OUT / "bootstrap_summary.json",
        {
            "eth_placebo": eth["placebo_flat_rel_tick"],
            "btc_placebo": btc["placebo_flat_rel_tick"],
            "eth_fm": {
                "rho_all": eth["fm_quoted_spread_rel_tick"]["rho_all"],
                "rho_native": eth["fm_quoted_spread_rel_tick"]["rho_native"],
                "within_venue": eth["fm_quoted_spread_rel_tick"]["within_venue_hour"],
                "time_split_slope": eth["fm_quoted_spread_rel_tick"]["time_split_slope"],
            },
            "btc_fm": {
                "rho_all": btc["fm_quoted_spread_rel_tick"]["rho_all"],
                "rho_native": btc["fm_quoted_spread_rel_tick"]["rho_native"],
                "within_venue": btc["fm_quoted_spread_rel_tick"]["within_venue_hour"],
            },
            "eth_constraint": eth["constraint_frac_by_venue"],
            "btc_constraint": btc["constraint_frac_by_venue"],
            "eth_undercut": eth["undercut_rho"],
            "btc_undercut": btc["undercut_rho"],
        },
    )

    update_desk_memo(artifact)
    update_candidates(gates)
    update_chapter_index(gates)

    # also refresh pass2 gates pointer for notebooks
    pass2 = BOOK / "out" / "pass2"
    pass2.mkdir(parents=True, exist_ok=True)
    _write_json(
        pass2 / "hardening_gates.json",
        {
            **(_load_json(pass2 / "hardening_gates.json") if (pass2 / "hardening_gates.json").is_file() else {}),
            "pass25": {
                "counts": artifact["counts"],
                "gates": gates,
                "eth_placebo_ci": eth["placebo_flat_rel_tick"]["day_block_ci"],
                "btc_placebo_ci": btc["placebo_flat_rel_tick"]["day_block_ci"],
            },
            "gates": {k: {"decision": v["decision"], "why": v["why"]} for k, v in gates.items()},
            "flags": {
                "xvenue_confound": True,
                "promote_taxonomy": True,
                "kraken_synth_excluded_native": True,
                "kraken_spot_l2_native": True,
                "pass25": True,
            },
        },
    )

    print(
        json.dumps(
            {
                "counts": artifact["counts"],
                "placebo_eth": eth["placebo_flat_rel_tick"]["day_block_ci"],
                "placebo_btc": btc["placebo_flat_rel_tick"]["day_block_ci"],
                "placebo_gate": gates["liq.placebo_flat_rel_tick"],
                "figs": figs,
            },
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
