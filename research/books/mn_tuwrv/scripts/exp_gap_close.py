from __future__ import annotations
#!/usr/bin/env python3
"""Gap-close Pass 2.5 for mn_tuwrv — desk-grade statistical depth.

1. Cross-venue TOB: collector → warehouse L2 (Deribit/HL); Kraken Roll/mark proxies
2. Multi-week panels + chronological time-split / shuffle falsifiers with CIs
3. Mid + tick-bounce clocks vs calendar / trade clocks (bootstrap paired diffs)

Pre-registered Promote gates (documented in CANDIDATES):
- liq.noise_vs_spread: Spearman ρ>0, shuffle p<0.05, early & late ρ same sign,
  n_spread_rows≥20, bootstrap CI for ρ excludes ≤0
- cont.tsrv_first_adj: ablation fragile_rate<0.2; early/late |ρ(first_adj,iv_proxy)|
  not required — Hold unless OOS first_adj RMSE advantage survives time-split
  (MC already Kill sparse; Promote only if multi-week first_adj/fourth median
  ratio advantage CI>0 AND ablation fragile_rate=0)
- cont.noise_* clocks: Promote bounce claim only if median fifth/fourth CI lower
  bound >1.5

ClickHouse MCP banned.
"""

import os

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(Path(os.environ.get('WAREHOUSE_SRC') or ((Path(os.environ.get('WAREHOUSE_ROOT') or (Path.home() / 'lab' / 'lab-n2070' / 'warehouse')) / 'src')))))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb')) / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import (  # noqa: E402
    CORE_VENUES,
    ensure_env,
    kraken_liquidity_proxies,
    load_day_trades,
    load_tob_day,
    resolve_days,
)
from ares_micro.flow.continuous import amihud_illiquidity, trade_intensity  # noqa: E402
from ares_micro.book.spreads import quoted_spread_bps  # noqa: E402
from ares_micro.stats import spearman_r  # noqa: E402
from ares_micro.vol.tsrv import (  # noqa: E402
    all_estimators,
    compare_clocks_bootstrap,
    estimators_on_log_px,
    estimators_trade_clock,
    grid_log_price_from_tape,
    k_step_ablation,
    log_returns,
    mid_clock_log_px,
    noise_variance_proxy,
    tick_rule_bounce_path,
)

OUT = BOOK / "out" / "gap_close"


def _spearman_boot_ci(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    *,
    n_boot: int = 800,
    seed: int = 3,
) -> dict[str, float]:
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
        idx = rng.integers(0, n, size=n)
        boots.append(float(spearman_r(a[idx], b[idx])))
    boots_a = np.asarray(boots, dtype=np.float64)
    boots_a = boots_a[np.isfinite(boots_a)]
    lo, hi = np.quantile(boots_a, [0.025, 0.975]) if boots_a.size else (float("nan"), float("nan"))
    return {"n": float(n), "rho": point, "lo": float(lo), "hi": float(hi)}


def _shuffle_p(x: NDArray[np.float64], y: NDArray[np.float64], *, n_shuffle: int, seed: int) -> float:
    a = np.asarray(x, dtype=np.float64)
    b = np.asarray(y, dtype=np.float64)
    m = np.isfinite(a) & np.isfinite(b)
    a, b = a[m], b[m]
    if a.size < 5:
        return float("nan")
    obs = abs(float(spearman_r(a, b)))
    rng = np.random.default_rng(seed)
    null = []
    for _ in range(n_shuffle):
        null.append(abs(float(spearman_r(a, rng.permutation(b)))))
    null_a = np.asarray(null, dtype=np.float64)
    null_a = null_a[np.isfinite(null_a)]
    return float(np.mean(null_a >= obs)) if null_a.size else float("nan")


def _block_shuffle_p(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    days: list[str],
    *,
    n_shuffle: int,
    seed: int,
) -> float:
    """Permute y within day-blocks to preserve some dependence."""
    a = np.asarray(x, dtype=np.float64)
    b = np.asarray(y, dtype=np.float64)
    d = np.asarray(days)
    m = np.isfinite(a) & np.isfinite(b)
    a, b, d = a[m], b[m], d[m]
    if a.size < 5:
        return float("nan")
    obs = abs(float(spearman_r(a, b)))
    rng = np.random.default_rng(seed)
    uniq = list(dict.fromkeys(d.tolist()))
    null = []
    for _ in range(n_shuffle):
        b2 = b.copy()
        for day in uniq:
            idx = np.where(d == day)[0]
            if idx.size > 1:
                b2[idx] = rng.permutation(b2[idx])
            elif idx.size == 1:
                # swap with random other block element
                j = rng.integers(0, a.size)
                b2[idx[0]], b2[j] = b2[j], b2[idx[0]]
        null.append(abs(float(spearman_r(a, b2))))
    null_a = np.asarray(null, dtype=np.float64)
    null_a = null_a[np.isfinite(null_a)]
    return float(np.mean(null_a >= obs)) if null_a.size else float("nan")


def _spread_for(venue: str, symbol: str, day: str, tape: dict, *, max_files: int) -> dict:
    """Quoted TOB first (HL/Deribit/Kraken spot L2 / futures ingest); Kraken proxy fallback."""
    try:
        tob = load_tob_day(venue, symbol, day, max_files=max_files)
        sp = quoted_spread_bps(tob["bid"], tob["ask"], mid=tob["mid"])
        return {
            "ok": True,
            "spread_bps_mean": float(np.nanmean(sp)),
            "spread_bps_med": float(np.nanmedian(sp)),
            "n_tob": int(tob["ts"].size),
            "source": tob.get("source"),
            "market": tob.get("market"),
            "quoted_available": True,
            "spread_kind": "quoted",
            "bid": tob["bid"],
            "ask": tob["ask"],
            "ts": tob["ts"],
        }
    except Exception as exc:  # noqa: BLE001
        if venue == "kraken":
            prox = kraken_liquidity_proxies(tape, symbol, day)
            prox["tob_error"] = f"{type(exc).__name__}: {exc}"
            return prox
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "quoted_available": False,
            "spread_bps_mean": float("nan"),
        }


def _day_metrics(venue: str, symbol: str, day: str, *, max_files: int, K: int, step: int) -> dict:
    try:
        rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "venue": venue, "symbol": symbol, "day": day, "reason": f"load:{exc}"}
    tape = rec["tape"]
    comp = rec.get("completeness") or {}
    if int(tape.get("n", 0)) < 50:
        return {"ok": False, "venue": venue, "symbol": symbol, "day": day, "reason": "empty"}
    g = grid_log_price_from_tape(tape["ts"], tape["px"], dt_s=1.0)
    if int(g["n_filled"]) < 60 or g["log_px"].size < step + 2:
        return {
            "ok": False,
            "venue": venue,
            "symbol": symbol,
            "day": day,
            "reason": "short_grid",
            "n_filled": int(g["n_filled"]),
        }
    cal = estimators_on_log_px(g["log_px"], K=K, step=step)
    abl = k_step_ablation(g["log_px"])
    tc = estimators_trade_clock(tape["ts"], tape["px"], K=min(K, 50), step=min(step, 50), max_n=40_000)
    bounce = tick_rule_bounce_path(tape["ts"], tape["px"], max_n=40_000)
    bc = estimators_on_log_px(bounce["log_px"], K=min(K, 50), step=min(step, 50))
    bc["flip_rate"] = float(bounce.get("flip_rate", float("nan")))

    spread = _spread_for(venue, symbol, day, tape, max_files=max_files)
    mid_est = {}
    if spread.get("quoted_available") and "bid" in spread:
        mg = mid_clock_log_px(spread["ts"], spread["bid"], spread["ask"], dt_s=1.0)
        mid_est = estimators_on_log_px(mg["log_px"], K=K, step=step)
        # drop heavy arrays from persisted spread
        spread = {k: v for k, v in spread.items() if k not in ("bid", "ask", "ts")}

    # Amihud 60s
    t = np.asarray(tape["ts"], dtype=np.int64)
    px = np.asarray(tape["px"], dtype=np.float64)
    qty = np.asarray(tape["qty"], dtype=np.float64)
    bar_ns = 60_000_000_000
    edges = np.arange(int(t.min()), int(t.max()) + bar_ns, bar_ns, dtype=np.int64)
    last = np.full(edges.size, np.nan)
    dvol = np.zeros(edges.size)
    idx = np.clip(np.searchsorted(edges, t, side="right") - 1, 0, edges.size - 1)
    for i, j in enumerate(idx):
        if np.isfinite(px[i]) and px[i] > 0:
            last[j] = px[i]
            dvol[j] += float(qty[i]) * float(px[i])
    fill = np.nan
    for i in range(last.size):
        if np.isfinite(last[i]):
            fill = last[i]
        elif np.isfinite(fill):
            last[i] = fill
    r60 = np.diff(np.log(last))
    am = amihud_illiquidity(r60, dvol[1:])
    intens = trade_intensity(t)

    return {
        "ok": True,
        "venue": venue,
        "symbol": symbol,
        "day": day,
        "complete": bool(comp.get("complete", False)),
        "n_trades": int(tape.get("n", t.size)),
        "coverage_grid": float(g["coverage"]),
        "calendar": cal,
        "trade_clock": tc,
        "tick_bounce": bc,
        "mid_clock": mid_est,
        "ablation": {
            "first_adj_cv": abl["first_adj_cv"],
            "fragile_first_adj": abl["fragile_first_adj"],
            "first_adj_range": abl["first_adj_range"],
        },
        "noise_std": float(cal["noise_std"]),
        "first_adj": float(cal["first_adj"]),
        "fifth_over_fourth_cal": float(cal["fifth_over_fourth"]),
        "fifth_over_fourth_tc": float(tc.get("fifth_over_fourth", float("nan"))),
        "fifth_over_fourth_bounce": float(bc.get("fifth_over_fourth", float("nan"))),
        "fifth_over_fourth_mid": float(mid_est.get("fifth_over_fourth", float("nan"))) if mid_est else float("nan"),
        "spread": spread,
        "amihud": float(am["illiq"]),
        "intensity": float(intens.get("mean_lambda", float("nan"))),
    }


def _panel(symbols: list[str], days: list[str], *, max_files: int, K: int, step: int) -> list[dict]:
    rows = []
    for sym in symbols:
        for day in days:
            for venue in CORE_VENUES:
                print(f"gap_close {sym} {venue} {day} …", flush=True)
                rows.append(_day_metrics(venue, sym, day, max_files=max_files, K=K, step=step))
    return rows


def _falsify_spread(rows: list[dict], *, n_shuffle: int) -> dict:
    ok = [
        r
        for r in rows
        if r.get("ok") and (r.get("spread") or {}).get("ok") and np.isfinite(r.get("noise_std", np.nan))
    ]
    noise = np.array([r["noise_std"] for r in ok], dtype=np.float64)
    spread = np.array([r["spread"]["spread_bps_mean"] for r in ok], dtype=np.float64)
    amihud = np.array([r["amihud"] for r in ok], dtype=np.float64)
    days = [r["day"] for r in ok]
    venues = [r["venue"] for r in ok]
    kinds = [r["spread"].get("spread_kind") for r in ok]
    sources = [r["spread"].get("source") for r in ok]

    rho = _spearman_boot_ci(noise, spread)
    rho_am = _spearman_boot_ci(noise, amihud)
    sh_p = _shuffle_p(noise, spread, n_shuffle=n_shuffle, seed=9)
    blk_p = _block_shuffle_p(noise, spread, days, n_shuffle=n_shuffle, seed=10)

    # chronological split by unique days
    uniq = sorted(set(days))
    mid = max(len(uniq) // 2, 1)
    early_d, late_d = set(uniq[:mid]), set(uniq[mid:])
    early = [i for i, d in enumerate(days) if d in early_d]
    late = [i for i, d in enumerate(days) if d in late_d]

    def _rho_idx(idx):
        if len(idx) < 5:
            return {"n": float(len(idx)), "rho": float("nan"), "lo": float("nan"), "hi": float("nan")}
        return _spearman_boot_ci(noise[idx], spread[idx])

    early_rho = _rho_idx(early)
    late_rho = _rho_idx(late)
    same_sign = (
        np.isfinite(rho["rho"])
        and np.isfinite(early_rho["rho"])
        and np.isfinite(late_rho["rho"])
        and (early_rho["rho"] * rho["rho"] > 0)
        and (late_rho["rho"] * rho["rho"] > 0)
    )
    ci_pos = bool(np.isfinite(rho["lo"]) and rho["lo"] > 0)
    # coverage by venue
    cov = {}
    for v in CORE_VENUES:
        subv = [r for r in ok if r["venue"] == v]
        cov[v] = {
            "n": len(subv),
            "quoted": sum(1 for r in subv if r["spread"].get("quoted_available")),
            "proxy": sum(1 for r in subv if not r["spread"].get("quoted_available")),
            "sources": sorted({str(r["spread"].get("source")) for r in subv}),
        }

    gate = "Hold"
    why = ""
    if (
        rho["rho"] > 0
        and sh_p < 0.05
        and same_sign
        and len(ok) >= 20
        and ci_pos
    ):
        gate = "Promote"
        why = (
            f"ρ={rho['rho']:.3f} CI=[{rho['lo']:.3f},{rho['hi']:.3f}] "
            f"shuffle_p={sh_p:.4f} block_p={blk_p:.4f} n={len(ok)} early/late={early_rho['rho']:.3f}/{late_rho['rho']:.3f}"
        )
    else:
        why = (
            f"ρ={rho['rho']:.3f} CI=[{rho['lo']:.3f},{rho['hi']:.3f}] "
            f"shuffle_p={sh_p:.4f} block_p={blk_p:.4f} n={len(ok)} "
            f"same_sign={same_sign} ci_pos={ci_pos} early_n={early_rho['n']} late_n={late_rho['n']}"
        )
        # Kill only if clearly opposite thesis with power
        if np.isfinite(rho["rho"]) and rho["hi"] < 0 and len(ok) >= 20:
            gate = "Kill"

    return {
        "n_rows": len(ok),
        "rho_spread": rho,
        "rho_amihud": rho_am,
        "shuffle_p": sh_p,
        "block_shuffle_p": blk_p,
        "time_split": {
            "early_days": sorted(early_d),
            "late_days": sorted(late_d),
            "early": early_rho,
            "late": late_rho,
            "same_sign": same_sign,
        },
        "coverage_by_venue": cov,
        "spread_kinds": {k: kinds.count(k) for k in sorted(set(kinds))},
        "sources": {k: sources.count(k) for k in sorted(set(map(str, sources)))},
        "gate": {"id": "liq.noise_vs_spread", "decision": gate, "why": why},
    }


def _falsify_clocks(rows: list[dict]) -> dict:
    ok = [r for r in rows if r.get("ok")]
    clocks = {
        "calendar": [r["fifth_over_fourth_cal"] for r in ok],
        "trade": [r["fifth_over_fourth_tc"] for r in ok],
        "tick_bounce": [r["fifth_over_fourth_bounce"] for r in ok],
        "mid": [r["fifth_over_fourth_mid"] for r in ok if np.isfinite(r.get("fifth_over_fourth_mid", np.nan))],
    }
    boot = compare_clocks_bootstrap(clocks, n_boot=600, seed=21)
    decisions = {}
    for name, st in boot["clocks"].items():
        lo = st["ci95"][0] if st.get("ci95") else float("nan")
        med = st.get("median", float("nan"))
        if np.isfinite(lo) and lo > 1.5:
            decisions[name] = {"decision": "Promote", "why": f"median={med:.3f} CI_lo={lo:.3f}>1.5 n={st['n']}"}
        elif np.isfinite(med) and med < 1.2:
            decisions[name] = {"decision": "Kill", "why": f"median={med:.3f} CI={st.get('ci95')} n={st['n']} (no bounce domination)"}
        else:
            decisions[name] = {"decision": "Hold", "why": f"median={med:.3f} CI={st.get('ci95')} n={st['n']}"}
    return {"bootstrap": boot, "per_clock": decisions}


def _falsify_tsrv(rows: list[dict]) -> dict:
    ok = [r for r in rows if r.get("ok")]
    fragile = sum(1 for r in ok if r.get("ablation", {}).get("fragile_first_adj"))
    cvs = [r["ablation"]["first_adj_cv"] for r in ok if np.isfinite(r.get("ablation", {}).get("first_adj_cv", np.nan))]
    # time-split: first_adj / fourth advantage
    adv = []
    days = []
    for r in ok:
        fa = r["calendar"].get("first_adj")
        fo = r["calendar"].get("fourth")
        if np.isfinite(fa) and np.isfinite(fo) and fo != 0:
            adv.append(float(fo - fa))  # positive ⇒ first_adj smaller error proxy vs sparse level
            days.append(r["day"])
    adv_a = np.asarray(adv, dtype=np.float64)
    uniq = sorted(set(days))
    mid = max(len(uniq) // 2, 1)
    early_d, late_d = set(uniq[:mid]), set(uniq[mid:])
    early = [a for a, d in zip(adv, days) if d in early_d]
    late = [a for a, d in zip(adv, days) if d in late_d]

    def _ci(a):
        a = np.asarray(a, dtype=np.float64)
        a = a[np.isfinite(a)]
        if a.size < 3:
            return {"n": float(a.size), "median": float("nan"), "ci95": [float("nan"), float("nan")]}
        rng = np.random.default_rng(4)
        boots = [float(np.median(a[rng.integers(0, a.size, size=a.size)])) for _ in range(500)]
        lo, hi = np.quantile(boots, [0.025, 0.975])
        return {"n": float(a.size), "median": float(np.median(a)), "ci95": [float(lo), float(hi)]}

    overall = _ci(adv_a)
    early_s = _ci(early)
    late_s = _ci(late)
    fragile_rate = fragile / max(len(ok), 1)
    # Promote bar deliberately strict
    promote = (
        fragile_rate == 0
        and overall["ci95"][0] > 0
        and early_s["ci95"][0] > 0
        and late_s["ci95"][0] > 0
        and len(ok) >= 20
    )
    decision = "Promote" if promote else "Hold"
    why = (
        f"fragile_rate={fragile_rate:.3f} adv_med={overall['median']:.3g} "
        f"CI={overall['ci95']} earlyCI={early_s['ci95']} lateCI={late_s['ci95']} n={len(ok)}"
    )
    return {
        "fragile_count": fragile,
        "fragile_rate": fragile_rate,
        "first_adj_cv_median": float(np.median(cvs)) if cvs else float("nan"),
        "sparse_minus_tsrv": {"overall": overall, "early": early_s, "late": late_s},
        "gate": {"id": "cont.tsrv_first_adj", "decision": decision, "why": why},
    }


def _write_all(payload: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "gap_close.json").write_text(json.dumps(payload, indent=2, default=str))

    spread = payload["spread_falsify"]
    clocks = payload["clock_falsify"]
    tsrv = payload["tsrv_falsify"]
    rows = payload["rows"]

    # market_noise EXP_REPORT
    lines = [
        "# Market noise — EXP_REPORT (Pass 2.5 gap-close)",
        "",
        "## Diagnosis: Deribit/Kraken TOB",
        "- Collector `results/xarb_md/tob` contains **HL + Lighter + RiseX only** (no Deribit/Kraken).",
        "- **Deribit:** fixed via warehouse `l2_snapshot_level` (`load_tob_day` → `load_quote_stream`).",
        "- **Kraken:** warehouse L2 is **spot-only**; futures `PF_*` never appear in listings → "
        "**Roll + mark-asof effective spread** proxies (`spread_kind=roll|effective_vs_mark`).",
        "",
        "## Coverage",
    ]
    for v, c in spread["coverage_by_venue"].items():
        lines.append(f"- {v}: n={c['n']} quoted={c['quoted']} proxy={c['proxy']} sources={c['sources']}")
    lines += [
        "",
        f"- Spread kinds: {spread['spread_kinds']}",
        f"- n_rows joined: {spread['n_rows']}",
        "",
        "## Statistics (noise_std vs spread_bps)",
        f"- Spearman ρ = {spread['rho_spread']['rho']:.4f}  "
        f"bootstrap CI95 = [{spread['rho_spread']['lo']:.4f}, {spread['rho_spread']['hi']:.4f}]  "
        f"n={spread['rho_spread']['n']}",
        f"- Spearman(noise, Amihud) ρ = {spread['rho_amihud']['rho']:.4f} "
        f"CI=[{spread['rho_amihud']['lo']:.4f}, {spread['rho_amihud']['hi']:.4f}]",
        f"- IID shuffle p = {spread['shuffle_p']:.4f}",
        f"- Block-shuffle (within-day) p = {spread['block_shuffle_p']:.4f}",
        f"- Time-split early ρ = {spread['time_split']['early']} days={spread['time_split']['early_days']}",
        f"- Time-split late ρ = {spread['time_split']['late']} days={spread['time_split']['late_days']}",
        f"- same_sign={spread['time_split']['same_sign']}",
        "",
        f"## Gate\n- `{spread['gate']['id']}` → **{spread['gate']['decision']}** — {spread['gate']['why']}",
        "",
        f"- Artifact: `out/gap_close/gap_close.json`",
        "",
    ]
    (BOOK / "chapters" / "market_noise" / "EXP_REPORT.md").write_text("\n".join(lines))
    (BOOK / "chapters" / "market_noise" / "CANDIDATES.md").write_text(
        "| id | type | lenses | decision | pre-registered gate | falsifier evidence |\n"
        "|----|------|--------|----------|---------------------|--------------------|\n"
        "| `liq.noise_vs_spread` | panel | liq, cont | "
        f"**{spread['gate']['decision']}** | ρ>0, shuffle p<0.05, early∧late same sign, "
        f"n≥20, bootstrap CI lo>0 | {spread['gate']['why']} |\n"
    )

    # estimators / noise clocks
    elines = [
        "# Estimators — EXP_REPORT (Pass 2.5 clocks)",
        "",
        "## fifth/fourth by clock (bootstrap medians)",
    ]
    for name, st in clocks["bootstrap"]["clocks"].items():
        elines.append(
            f"- {name}: median={st.get('median')} CI95={st.get('ci95')} n={st.get('n')} "
            f"→ **{clocks['per_clock'][name]['decision']}** ({clocks['per_clock'][name]['why']})"
        )
    elines += ["", "## Paired diffs (median A−B)"]
    for k, v in clocks["bootstrap"]["pairs"].items():
        elines.append(f"- {k}: {v}")
    elines += [
        "",
        "## TSRV first_adj",
        f"- `{tsrv['gate']['id']}` → **{tsrv['gate']['decision']}** — {tsrv['gate']['why']}",
        f"- fragile_rate={tsrv['fragile_rate']:.3f} first_adj_cv_med={tsrv['first_adj_cv_median']:.4f}",
        "",
    ]
    (BOOK / "chapters" / "estimators" / "EXP_REPORT.md").write_text("\n".join(elines))
    (BOOK / "chapters" / "estimators" / "CANDIDATES.md").write_text(
        "| id | type | lenses | decision | pre-registered gate | evidence |\n"
        "|----|------|--------|----------|---------------------|----------|\n"
        f"| `cont.tsrv_first_adj` | estimator | cont, risk | **{tsrv['gate']['decision']}** | "
        f"fragile_rate=0 ∧ sparse−tsrv CI_lo>0 early∧late ∧ n≥20 | {tsrv['gate']['why']} |\n"
        f"| `cont.noise_dominates_1s_mid` | diagnostic | cont | **{clocks['per_clock']['calendar']['decision']}** | "
        f"median fifth/fourth CI_lo>1.5 | {clocks['per_clock']['calendar']['why']} |\n"
        f"| `cont.noise_trade_clock_bounce` | diagnostic | cont | **{clocks['per_clock']['trade']['decision']}** | "
        f"CI_lo>1.5 | {clocks['per_clock']['trade']['why']} |\n"
        f"| `cont.noise_tick_bounce_clock` | diagnostic | cont, info | **{clocks['per_clock']['tick_bounce']['decision']}** | "
        f"CI_lo>1.5 | {clocks['per_clock']['tick_bounce']['why']} |\n"
        + (
            f"| `cont.noise_mid_clock` | diagnostic | cont | **{clocks['per_clock']['mid']['decision']}** | "
            f"CI_lo>1.5 | {clocks['per_clock']['mid']['why']} |\n"
            if "mid" in clocks["per_clock"]
            else ""
        )
        + "| `cont.sparse_rv_only` | policy | cont | **Kill** | MC first_adj RMSE ≪ fourth | see monte_carlo |\n"
    )

    # noise_proxy
    (BOOK / "chapters" / "noise_proxy" / "EXP_REPORT.md").write_text(
        "# Noise proxy — EXP_REPORT (Pass 2.5)\n\n"
        f"- Multi-week n_ok={sum(1 for r in rows if r.get('ok'))}\n"
        f"- Calendar / trade / tick_bounce / mid gates: { {k:v['decision'] for k,v in clocks['per_clock'].items()} }\n"
        f"- `cont.noise_var_fifth` remains **Hold** (liquidity proxy; not efficiency).\n"
    )
    (BOOK / "chapters" / "noise_proxy" / "CANDIDATES.md").write_text(
        "| id | type | lenses | decision | gate |\n"
        "|----|------|--------|----------|------|\n"
        "| `cont.noise_var_fifth` | proxy | cont, liq | **Hold** | no causal efficiency claim |\n"
        f"| `cont.noise_tick_bounce_clock` | diagnostic | cont | **{clocks['per_clock']['tick_bounce']['decision']}** | {clocks['per_clock']['tick_bounce']['why']} |\n"
    )

    # xvenue quick
    by = {}
    for r in rows:
        if not r.get("ok"):
            continue
        by.setdefault(f"{r['symbol']} {r['day']}", {})[r["venue"]] = r["noise_std"]
    close = 0
    tot = 0
    for m in by.values():
        vs = [m[v] for v in CORE_VENUES if v in m]
        if len(vs) < 2:
            continue
        tot += 1
        if (max(vs) - min(vs)) / max(abs(np.mean(vs)), 1e-18) < 0.35:
            close += 1
    (BOOK / "chapters" / "xvenue_noise" / "EXP_REPORT.md").write_text(
        "# X-venue noise — EXP_REPORT (Pass 2.5)\n\n"
        f"- Close-noise symbol-days: {close}/{tot}\n"
        "- `frag.xvenue_noise_concord` → **Hold** (level concordance ≠ edge).\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="ETH,BTC")
    ap.add_argument("--n-days", type=int, default=14)
    ap.add_argument("--days", default="")
    ap.add_argument("--max-files", type=int, default=16)
    ap.add_argument("--K", type=int, default=300)
    ap.add_argument("--step", type=int, default=300)
    ap.add_argument("--n-shuffle", type=int, default=600)
    args = ap.parse_args()
    try:
        ensure_env()
    except Exception as e:  # noqa: BLE001
        print(f"ensure_env warn: {e}", flush=True)

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    day_list = [d.strip() for d in args.days.split(",") if d.strip()] or None
    # Prefer intersection-ish: take HL listing days (widest), then filter later if load fails
    days = resolve_days(day_list, venue="hyperliquid", n=args.n_days)
    print(f"days={days}", flush=True)

    rows = _panel(symbols, days, max_files=args.max_files, K=args.K, step=args.step)
    # drop heavy arrays if any leaked
    for r in rows:
        sp = r.get("spread")
        if isinstance(sp, dict):
            for k in ("bid", "ask", "ts"):
                sp.pop(k, None)

    spread_f = _falsify_spread(rows, n_shuffle=args.n_shuffle)
    clock_f = _falsify_clocks(rows)
    tsrv_f = _falsify_tsrv(rows)
    payload = {
        "meta": {
            "symbols": symbols,
            "days": days,
            "n_days": len(days),
            "K": args.K,
            "step": args.step,
            "n_shuffle": args.n_shuffle,
            "pre_registered_gates": {
                "liq.noise_vs_spread": "ρ>0 & shuffle_p<0.05 & early∧late same sign & n≥20 & CI_lo>0",
                "cont.tsrv_first_adj": "fragile_rate=0 & sparse−tsrv CI_lo>0 early∧late & n≥20",
                "noise_clock_dominates": "median fifth/fourth CI_lo>1.5",
            },
        },
        "rows": rows,
        "spread_falsify": spread_f,
        "clock_falsify": clock_f,
        "tsrv_falsify": tsrv_f,
    }
    _write_all(payload)
    print(json.dumps({
        "spread_gate": spread_f["gate"],
        "tsrv_gate": tsrv_f["gate"],
        "clocks": {k: v["decision"] for k, v in clock_f["per_clock"].items()},
        "coverage": spread_f["coverage_by_venue"],
        "n_ok": sum(1 for r in rows if r.get("ok")),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
