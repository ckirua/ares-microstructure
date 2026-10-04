#!/usr/bin/env python3
"""Pass-1 DCM̂ + liquidity-elasticity regimes for cd_me.

Builds public constraint proxies (funding proxy, |basis|, RV, imbalance),
PC1 DCM̂, and corr(VLM, PIM) unconstrained vs DCM-high. Writes
``out/dcm_proxies/`` and ``out/elasticity_regimes/``.

Depends on ``exp_pim_panel.py`` hourly artifacts when present; otherwise
recomputes a light PIM join. ClickHouse MCP banned.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
SCRIPTS = Path(__file__).resolve().parent
WAREHOUSE_SRC = Path(
    os.environ.get("WAREHOUSE_SRC")
    or (
        (Path(os.environ.get("WAREHOUSE_ROOT") or (Path.home() / "lab" / "lab-n2070" / "warehouse")) / "src")
    )
)
STARTARB = Path(os.environ.get("ARES_STARTARB") or (Path.home() / "srv" / "ares-startarb"))

for _p in (str(WAREHOUSE_SRC), str(STARTARB / "src"), str(ROOT), str(SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from _data import (  # noqa: E402
    asof_join,
    ensure_env,
    funding_proxy_from_marks,
    load_cross_venue_marks,
    resolve_days,
)
from ares_micro.flow.cdme import (  # noqa: E402
    dcm_pc1,
    dcm_proxies,
    elasticity_corr,
    logistic_G,
    realized_vol,
    regime_split_corr,
)

OUT_DCM = BOOK / "out" / "dcm_proxies"
OUT_EL = BOOK / "out" / "elasticity_regimes"
PIM_OUT = BOOK / "out" / "pim_vloop_tcost"

# Exploratory floor for Hold-board elasticity (never Promote on this alone).
# Paper-faithful Pass-2 should re-run with min_n≥15–20 + placebo regimes.
MIN_N_EXPLORATORY = 5
MIN_N_PROMOTE_GATE = 15


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


def _load_pim_hourly(day: str) -> dict[str, Any] | None:
    path = PIM_OUT / f"day_{day}.json"
    if not path.is_file():
        return None
    try:
        blob = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not blob.get("ok"):
        return None
    return blob


def _day_dcm_elasticity(symbol: str, day: str, pim_row: dict[str, Any] | None) -> dict[str, Any]:
    marks = load_cross_venue_marks(symbol, day, quiet=True)
    venues = marks.get("venues") or {}
    home = venues.get("hyperliquid")
    if not isinstance(home, dict) or home.get("n", 0) < 15 or "error" in home:
        # fall back to any venue with marks
        home = None
        home_name = None
        for v, rec in venues.items():
            if isinstance(rec, dict) and rec.get("n", 0) >= 15 and "error" not in rec:
                home = rec
                home_name = v
                break
        if home is None:
            return {
                "ok": False,
                "day": day,
                "reason": "no_mark_bars",
                "mark_errors": {
                    k: (v.get("error") if isinstance(v, dict) else None) for k, v in venues.items()
                },
            }
        home_venue = home_name
    else:
        home_venue = "hyperliquid"

    h_ts = np.asarray(home["ts"], dtype=np.int64)
    h_mid = np.asarray(home["mid"], dtype=np.float64)
    log_px = np.log(np.clip(h_mid, 1e-12, None))
    rv = realized_vol(log_px, window=30)
    fund = funding_proxy_from_marks(h_mid, h_ts, window=30)["funding_proxy"]

    # basis vs Deribit (preferred) or Kraken
    basis = np.full(h_mid.shape, np.nan, dtype=np.float64)
    basis_venue = None
    for bv in ("deribit", "kraken"):
        rec = venues.get(bv)
        if not isinstance(rec, dict) or rec.get("n", 0) < 10 or "error" in rec:
            continue
        far = asof_join(h_ts, np.asarray(rec["ts"], dtype=np.int64), np.asarray(rec["mid"], dtype=np.float64))
        ok = np.isfinite(far) & (far > 0) & np.isfinite(h_mid) & (h_mid > 0)
        basis[ok] = np.log(far[ok] / h_mid[ok])
        basis_venue = bv
        break

    # imbalance / volume from PIM hourly if available
    imb = np.full(h_mid.shape, np.nan, dtype=np.float64)
    pim_on_mark = np.full(h_mid.shape, np.nan, dtype=np.float64)
    notional_on_mark = np.full(h_mid.shape, np.nan, dtype=np.float64)
    hourly_meta = None
    if pim_row and pim_row.get("hourly"):
        hourly_meta = pim_row["hourly"]
        hts = np.asarray(hourly_meta.get("ts") or [], dtype=np.int64)
        n_h = int(hts.size)

        def _hour_arr(key: str) -> np.ndarray:
            raw = hourly_meta.get(key)
            if raw is None:
                return np.full(n_h, np.nan, dtype=np.float64)
            arr = np.asarray(
                [np.nan if x is None else float(x) for x in raw],
                dtype=np.float64,
            )
            if arr.size == n_h:
                return arr
            out = np.full(n_h, np.nan, dtype=np.float64)
            n = min(arr.size, n_h)
            if n:
                out[:n] = arr[:n]
            return out

        himb = _hour_arr("imbalance")
        hpim = _hour_arr("pim")
        hnot = _hour_arr("notional")
        if n_h:
            imb = asof_join(h_ts, hts, himb)
            pim_on_mark = asof_join(h_ts, hts, hpim)
            notional_on_mark = asof_join(h_ts, hts, hnot)

    prox = dcm_proxies(funding=fund, basis=basis, rv=rv, imbalance=imb)
    pc = dcm_pc1(prox)

    # hourly elasticity: prefer PIM hourly arrays directly
    el_hourly: dict[str, Any]
    if pim_row and pim_row.get("hourly") and hourly_meta:
        hts = np.asarray(hourly_meta.get("ts") or [], dtype=np.int64)
        n_h = int(hts.size)

        def _hour_arr2(key: str) -> np.ndarray:
            raw = hourly_meta.get(key)
            if raw is None:
                return np.full(n_h, np.nan, dtype=np.float64)
            arr = np.asarray(
                [np.nan if x is None else float(x) for x in raw],
                dtype=np.float64,
            )
            if arr.size == n_h:
                return arr
            out = np.full(n_h, np.nan, dtype=np.float64)
            n = min(arr.size, n_h)
            if n:
                out[:n] = arr[:n]
            return out

        hpim = _hour_arr2("pim")
        hnot = _hour_arr2("notional")
        dcm_h = asof_join(hts, h_ts, pc["pc1"]) if n_h else np.zeros(0)
        el_hourly = regime_split_corr(hnot, hpim, dcm_h, min_n=MIN_N_EXPLORATORY)
        el_all = elasticity_corr(hnot, hpim, min_n=MIN_N_EXPLORATORY)
        hourly_pool = {
            "ts": hts.tolist(),
            "pim": [float(x) if np.isfinite(x) else None for x in hpim],
            "notional": [float(x) if np.isfinite(x) else None for x in hnot],
            "dcm": [float(x) if np.isfinite(x) else None for x in dcm_h],
        }
    else:
        el_hourly = regime_split_corr(
            notional_on_mark, pim_on_mark, pc["pc1"], min_n=MIN_N_EXPLORATORY
        )
        el_all = elasticity_corr(notional_on_mark, pim_on_mark, min_n=MIN_N_EXPLORATORY)
        hourly_pool = {
            "ts": h_ts.tolist(),
            "pim": [float(x) if np.isfinite(x) else None for x in pim_on_mark],
            "notional": [float(x) if np.isfinite(x) else None for x in notional_on_mark],
            "dcm": [float(x) if np.isfinite(x) else None for x in pc["pc1"]],
        }

    G = logistic_G(pc["pc1"], gamma=1.0)
    return {
        "ok": True,
        "day": day,
        "symbol": symbol,
        "home_venue": home_venue,
        "basis_venue": basis_venue,
        "n_marks": int(h_mid.size),
        "mark_venues_ok": [k for k, v in venues.items() if isinstance(v, dict) and v.get("n", 0) > 0 and "error" not in v],
        "pim_joined": bool(pim_row),
        "min_n_exploratory": MIN_N_EXPLORATORY,
        "min_n_promote_gate": MIN_N_PROMOTE_GATE,
        "hourly_pool": hourly_pool,
        "dcm": {
            "keys": pc.get("keys"),
            "loadings": pc.get("loadings"),
            "explained_var": pc.get("explained_var"),
            "n_valid": pc.get("n_valid"),
            "pc1_mean": float(np.nanmean(pc["pc1"])) if np.isfinite(pc["pc1"]).any() else None,
            "pc1_p75": float(np.nanpercentile(pc["pc1"][np.isfinite(pc["pc1"])], 75))
            if np.isfinite(pc["pc1"]).any()
            else None,
            "G_mean": float(np.nanmean(G)) if np.isfinite(G).any() else None,
        },
        "elasticity": {
            "all": el_all,
            "regime": el_hourly,
            "note": (
                f"min_n={MIN_N_EXPLORATORY} exploratory Hold only; "
                f"Promote gate remains min_n>={MIN_N_PROMOTE_GATE}"
            ),
        },
        "honesty": {
            "funding": "funding_proxy = rolling |Δlog mid| (not exchange funding rate)",
            "cds_var": "Kill — no bank VaR/CDS in this panel",
            "alpha": "elasticity/PIM monitors only — never sized arb",
        },
    }


def _pool_hourly(ok_rows: list[dict[str, Any]]) -> dict[str, np.ndarray]:
    vols: list[float] = []
    pims: list[float] = []
    dcms: list[float] = []
    days_tag: list[str] = []
    for r in ok_rows:
        hp = r.get("hourly_pool") or {}
        day = str(r.get("day"))
        n = max(len(hp.get("pim") or []), len(hp.get("notional") or []), len(hp.get("dcm") or []))
        pim = hp.get("pim") or [None] * n
        notional = hp.get("notional") or [None] * n
        dcm = hp.get("dcm") or [None] * n
        for i in range(n):
            v = notional[i] if i < len(notional) else None
            p = pim[i] if i < len(pim) else None
            d = dcm[i] if i < len(dcm) else None
            if v is None or p is None:
                continue
            try:
                vf, pf = float(v), float(p)
            except (TypeError, ValueError):
                continue
            if not (np.isfinite(vf) and np.isfinite(pf)):
                continue
            vols.append(vf)
            pims.append(pf)
            if d is not None:
                try:
                    df = float(d)
                except (TypeError, ValueError):
                    df = float("nan")
            else:
                df = float("nan")
            dcms.append(df)
            days_tag.append(day)
    return {
        "volume": np.asarray(vols, dtype=np.float64),
        "pim": np.asarray(pims, dtype=np.float64),
        "dcm": np.asarray(dcms, dtype=np.float64),
        "day": np.asarray(days_tag, dtype=object),
    }


def _bootstrap_corr_ci(
    x: np.ndarray,
    y: np.ndarray,
    *,
    n_boot: int = 800,
    seed: int = 42,
    min_n: int = MIN_N_EXPLORATORY,
) -> dict[str, Any]:
    m = np.isfinite(x) & np.isfinite(y)
    xx, yy = x[m], y[m]
    n = int(xx.size)
    if n < min_n:
        return {"ok": False, "n": n, "corr": None, "ci_lo": None, "ci_hi": None, "n_boot": 0}
    point = float(np.corrcoef(xx, yy)[0, 1])
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot, dtype=np.float64)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        c = float(np.corrcoef(xx[idx], yy[idx])[0, 1])
        boots[i] = c if np.isfinite(c) else np.nan
    boots = boots[np.isfinite(boots)]
    if boots.size < max(50, n_boot // 4):
        return {"ok": True, "n": n, "corr": point, "ci_lo": None, "ci_hi": None, "n_boot": int(boots.size)}
    lo, hi = np.quantile(boots, [0.025, 0.975])
    return {
        "ok": True,
        "n": n,
        "corr": point,
        "ci_lo": float(lo),
        "ci_hi": float(hi),
        "n_boot": int(boots.size),
    }


def _pooled_elasticity(ok_rows: list[dict[str, Any]]) -> dict[str, Any]:
    pool = _pool_hourly(ok_rows)
    v, p, d = pool["volume"], pool["pim"], pool["dcm"]
    all_ci = _bootstrap_corr_ci(v, p, min_n=MIN_N_EXPLORATORY)
    # regime split on pooled DCM (only rows with finite DCM)
    m = np.isfinite(v) & np.isfinite(p) & np.isfinite(d)
    regime = regime_split_corr(v[m], p[m], d[m], min_n=MIN_N_EXPLORATORY)
    regime_ci: dict[str, Any] = {"ok": False}
    if int(m.sum()) >= MIN_N_EXPLORATORY * 2:
        ql = float(np.nanquantile(d[m], 0.25))
        qh = float(np.nanquantile(d[m], 0.75))
        low = m & (d <= ql)
        high = m & (d >= qh)
        low_ci = _bootstrap_corr_ci(v[low], p[low], min_n=MIN_N_EXPLORATORY, seed=43)
        high_ci = _bootstrap_corr_ci(v[high], p[high], min_n=MIN_N_EXPLORATORY, seed=44)
        delta = None
        if low_ci.get("corr") is not None and high_ci.get("corr") is not None:
            delta = float(high_ci["corr"] - low_ci["corr"])
        regime_ci = {
            "ok": bool(low_ci.get("ok") and high_ci.get("ok")),
            "low": low_ci,
            "high": high_ci,
            "delta": delta,
            "q_low": ql,
            "q_high": qh,
        }
    meets_promote_n = int(all_ci.get("n") or 0) >= MIN_N_PROMOTE_GATE
    return {
        "n_hours_pooled": int(v.size),
        "n_days_pooled": int(len({str(x) for x in pool["day"].tolist()})) if v.size else 0,
        "all": all_ci,
        "regime_point": regime,
        "regime_bootstrap": regime_ci,
        "min_n_exploratory": MIN_N_EXPLORATORY,
        "min_n_promote_gate": MIN_N_PROMOTE_GATE,
        "meets_promote_n_gate": meets_promote_n,
        "decision_ceiling": "Hold" if all_ci.get("ok") else "thin_n",
        "note": (
            "Pooled hourly corr(VLM,PIM) with percentile bootstrap CI. "
            f"min_n={MIN_N_EXPLORATORY} is exploratory Hold only — never soft-Promote; "
            f"Promote gate min_n>={MIN_N_PROMOTE_GATE} + Pass-2 falsifiers."
        ),
    }


def _write_el_figs(ok_rows: list[dict[str, Any]], pooled: dict[str, Any], out_dir: Path) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    paths: list[str] = []
    if not ok_rows:
        return paths

    days = [r.get("day") for r in ok_rows]
    corr_all = []
    n_all = []
    for r in ok_rows:
        el = ((r.get("elasticity") or {}).get("all") or {})
        corr_all.append(el.get("corr"))
        n_all.append(el.get("n"))

    fig, ax = plt.subplots(figsize=(max(7, 1.1 * len(days)), 3.8))
    ax.axhline(0, color="#888", lw=0.8)
    y = [c if c is not None else float("nan") for c in corr_all]
    ax.plot(days, y, "o-", color="#1f4e79", label="corr(VLM,PIM)")
    for i, (d, c, n) in enumerate(zip(days, corr_all, n_all)):
        if c is not None and n:
            ax.annotate(f"n={n}", (d, c), textcoords="offset points", xytext=(0, 6), ha="center", fontsize=7)
    ax.set_ylabel("corr")
    ax.set_title("Per-day elasticity corr (exploratory min_n)")
    ax.tick_params(axis="x", rotation=45)
    ax.grid(True, alpha=0.3)
    ax.legend(frameon=False)
    fig.tight_layout()
    p1 = out_dir / "fig_elasticity_by_day.png"
    fig.savefig(p1, dpi=140, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p1))

    # Pooled point + CI
    all_ci = pooled.get("all") or {}
    fig, ax = plt.subplots(figsize=(5.5, 3.6))
    if all_ci.get("corr") is not None:
        ax.errorbar(
            [0],
            [all_ci["corr"]],
            yerr=[
                [all_ci["corr"] - (all_ci["ci_lo"] if all_ci.get("ci_lo") is not None else all_ci["corr"])],
                [(all_ci["ci_hi"] if all_ci.get("ci_hi") is not None else all_ci["corr"]) - all_ci["corr"]],
            ],
            fmt="o",
            color="#c55a11",
            capsize=6,
            label=f"pooled n={all_ci.get('n')}",
        )
        rb = pooled.get("regime_bootstrap") or {}
        if rb.get("ok"):
            low = rb.get("low") or {}
            high = rb.get("high") or {}
            xs = [1, 2]
            ys = [low.get("corr"), high.get("corr")]
            lo_err = [
                (ys[0] or 0) - (low.get("ci_lo") if low.get("ci_lo") is not None else (ys[0] or 0)),
                (ys[1] or 0) - (high.get("ci_lo") if high.get("ci_lo") is not None else (ys[1] or 0)),
            ]
            hi_err = [
                (low.get("ci_hi") if low.get("ci_hi") is not None else (ys[0] or 0)) - (ys[0] or 0),
                (high.get("ci_hi") if high.get("ci_hi") is not None else (ys[1] or 0)) - (ys[1] or 0),
            ]
            ax.errorbar(xs, ys, yerr=[lo_err, hi_err], fmt="s", color="#548235", capsize=6, label="DCM low/high")
            ax.set_xticks([0, 1, 2])
            ax.set_xticklabels(["all", "DCM low", "DCM high"])
        else:
            ax.set_xticks([0])
            ax.set_xticklabels(["all"])
    ax.axhline(0, color="#888", lw=0.8)
    ax.set_ylabel("corr(VLM, PIM)")
    ax.set_title("Pooled elasticity ± 95% bootstrap CI")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    p2 = out_dir / "fig_elasticity_pooled_ci.png"
    fig.savefig(p2, dpi=140, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p2))

    # DCM explained var / n_valid
    fig, ax = plt.subplots(figsize=(max(7, 1.1 * len(days)), 3.6))
    n_valid = [(r.get("dcm") or {}).get("n_valid") or 0 for r in ok_rows]
    expl = [(r.get("dcm") or {}).get("explained_var") for r in ok_rows]
    ax.bar(days, n_valid, color="#1f4e79", alpha=0.75, label="n_valid")
    ax2 = ax.twinx()
    ax2.plot(days, [e if e is not None else float("nan") for e in expl], "o-", color="#c55a11", label="explained_var")
    ax.set_ylabel("DCM n_valid")
    ax2.set_ylabel("PC1 explained var")
    ax.set_title("DCM̂ PC1 coverage by day")
    ax.tick_params(axis="x", rotation=45)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    p3 = OUT_DCM / "figs" / "fig_dcm_coverage.png"
    p3.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(p3, dpi=140, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p3))
    return paths


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--days", nargs="*", default=None)
    ap.add_argument("--n-days", type=int, default=7)
    ap.add_argument("--fast", action="store_true")
    args = ap.parse_args()

    ensure_env()
    OUT_DCM.mkdir(parents=True, exist_ok=True)
    OUT_EL.mkdir(parents=True, exist_ok=True)

    # Prefer certified primary days, then PIM artifacts, then listings
    if args.days:
        days = list(args.days)
    else:
        try:
            from certified_panel import primary_days as _cert_days

            days = list(_cert_days())
        except Exception:
            days = []
        if not days and PIM_OUT.joinpath("summary.json").is_file():
            try:
                days = list(json.loads((PIM_OUT / "summary.json").read_text()).get("days") or [])
            except (OSError, json.JSONDecodeError):
                days = []
        if not days:
            days = resolve_days(None, "hyperliquid", n=args.n_days)
    if args.fast:
        days = days[-3:]
    if not days:
        blocker = {
            "ok": False,
            "blocker": "no_days",
            "hint": "Run exp_pim_panel.py first or check warehouse listings",
        }
        (OUT_DCM / "summary.json").write_text(json.dumps(blocker, indent=2))
        (OUT_EL / "summary.json").write_text(json.dumps(blocker, indent=2))
        print(json.dumps(blocker, indent=2))
        return 2

    rows: list[dict[str, Any]] = []
    for day in days:
        print(f"[dcm] {args.symbol} {day} …", flush=True)
        pim_row = _load_pim_hourly(day)
        try:
            row = _day_dcm_elasticity(args.symbol, day, pim_row)
        except Exception as exc:  # noqa: BLE001
            row = {"ok": False, "day": day, "error": f"{type(exc).__name__}: {exc}"}
        rows.append(row)
        (OUT_DCM / f"day_{day}.json").write_text(json.dumps(_jsonable(row), indent=2))

    ok_rows = [r for r in rows if r.get("ok")]
    pooled = _pooled_elasticity(ok_rows) if ok_rows else {
        "ok": False,
        "note": "no ok days",
        "n_hours_pooled": 0,
    }
    fig_paths: list[str] = []
    try:
        (OUT_EL / "figs").mkdir(parents=True, exist_ok=True)
        (OUT_DCM / "figs").mkdir(parents=True, exist_ok=True)
        fig_paths = _write_el_figs(ok_rows, pooled, OUT_EL / "figs")
    except Exception as exc:  # noqa: BLE001
        print(f"[dcm] fig write skipped: {type(exc).__name__}: {exc}", flush=True)

    dcm_summary = {
        "ok": bool(ok_rows),
        "symbol": args.symbol,
        "days": days,
        "n_ok": len(ok_rows),
        "n_fail": len(rows) - len(ok_rows),
        "figs": [p for p in fig_paths if "dcm" in Path(p).name],
        "day_summaries": [
            {
                "day": r.get("day"),
                "ok": r.get("ok"),
                "home_venue": r.get("home_venue"),
                "basis_venue": r.get("basis_venue"),
                "n_marks": r.get("n_marks"),
                "mark_venues_ok": r.get("mark_venues_ok"),
                "dcm": r.get("dcm"),
                "reason": r.get("reason") or r.get("error"),
            }
            for r in rows
        ],
        "kill_cds_var": True,
        "note": "DCM̂ = PC1 of public proxies only",
    }
    el_summary = {
        "ok": bool(ok_rows),
        "symbol": args.symbol,
        "days": days,
        "n_ok": len(ok_rows),
        "min_n_exploratory": MIN_N_EXPLORATORY,
        "min_n_promote_gate": MIN_N_PROMOTE_GATE,
        "pooled": pooled,
        "figs": fig_paths,
        "day_elasticity": [
            {
                "day": r.get("day"),
                "ok": r.get("ok"),
                "elasticity": r.get("elasticity"),
            }
            for r in rows
            if r.get("ok")
        ],
        "honesty": (
            "Hold after Pass-2 falsifiers; "
            f"min_n={MIN_N_EXPLORATORY} exploratory only — never soft-Promote; "
            "TOB-cross α Kill; primary=panel_core_2venue real quotes; trade_synth QUARANTINED"
        ),
    }
    (OUT_DCM / "summary.json").write_text(json.dumps(_jsonable(dcm_summary), indent=2))
    (OUT_DCM / "panel_rows.json").write_text(json.dumps(_jsonable(rows), indent=2))
    (OUT_EL / "summary.json").write_text(json.dumps(_jsonable(el_summary), indent=2))
    print(
        json.dumps(
            _jsonable(
                {
                    "n_ok": dcm_summary["n_ok"],
                    "n_fail": dcm_summary["n_fail"],
                    "days": days,
                    "pooled_n": pooled.get("n_hours_pooled"),
                    "pooled_corr": (pooled.get("all") or {}).get("corr"),
                    "pooled_ci": [
                        (pooled.get("all") or {}).get("ci_lo"),
                        (pooled.get("all") or {}).get("ci_hi"),
                    ],
                    "figs": fig_paths,
                }
            ),
            indent=2,
        )
    )
    return 0 if ok_rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
