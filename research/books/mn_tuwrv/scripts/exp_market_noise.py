from __future__ import annotations
#!/usr/bin/env python3
"""market_noise Pass 1+2: noise vs spread / Amihud + shuffle / time-split.

Thesis §VI: wider bid-ask ⇒ higher Ê[ε²]. Crypto mapping: quoted_spread_bps
(TOB), Amihud, trade intensity. Falsifiers: shuffle spreads, chronological
time-split Spearman.

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
    day_bounds_ns,
    ensure_env,
    load_day_trades,
    load_venue_tob,
    resolve_days,
)
from research.lib.continuous import amihud_illiquidity, trade_intensity  # noqa: E402
from research.lib.spreads import quoted_spread_bps  # noqa: E402
from research.lib.stats import spearman_r  # noqa: E402
from research.lib.tsrv import (  # noqa: E402
    all_estimators,
    grid_log_price_from_tape,
    log_returns,
    noise_variance_proxy,
)

OUT = BOOK / "out" / "market_noise"
CH = BOOK / "chapters" / "market_noise"


def _tob_day_spread(venue: str, symbol: str, day: str) -> dict:
    """Mean quoted spread bps on collector TOB clipped to UTC day."""
    try:
        tob = load_venue_tob(venue, symbol, max_day_dirs=4, max_rows=400_000)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    lo, hi = day_bounds_ns(day)
    m = (tob["ts"] >= lo) & (tob["ts"] < hi)
    if not m.any():
        # collector may use wall clock misaligned — try full sample mean as fallback
        sp = quoted_spread_bps(tob["bid"], tob["ask"], mid=tob["mid"])
        return {
            "ok": bool(np.isfinite(sp).any()),
            "spread_bps_mean": float(np.nanmean(sp)) if np.isfinite(sp).any() else float("nan"),
            "n_tob": int(tob["ts"].size),
            "clipped": False,
            "note": "no_tob_in_utc_day_used_all",
        }
    sp = quoted_spread_bps(tob["bid"][m], tob["ask"][m], mid=tob["mid"][m])
    depth = tob["bid_sz"][m] + tob["ask_sz"][m]
    return {
        "ok": True,
        "spread_bps_mean": float(np.nanmean(sp)),
        "spread_bps_med": float(np.nanmedian(sp)),
        "depth_touch_mean": float(np.nanmean(depth)),
        "n_tob": int(m.sum()),
        "clipped": True,
    }


def _row(venue: str, symbol: str, day: str, *, K: int, step: int, dt_s: float, max_files: int) -> dict:
    try:
        rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "venue": venue, "day": day, "symbol": symbol, "reason": f"load:{exc}"}
    tape = rec["tape"]
    comp = rec.get("completeness") or {}
    if int(tape.get("n", 0)) < 30:
        return {
            "ok": False,
            "venue": venue,
            "day": day,
            "symbol": symbol,
            "reason": "empty_tape",
            "complete": bool(comp.get("complete", False)),
        }
    g = grid_log_price_from_tape(tape["ts"], tape["px"], dt_s=dt_s)
    log_px = g["log_px"]
    if int(g["n_filled"]) < 60 or log_px.size < step + 2:
        return {
            "ok": False,
            "venue": venue,
            "day": day,
            "symbol": symbol,
            "reason": "short_grid",
            "n_filled": int(g["n_filled"]),
        }
    est = all_estimators(log_px, K=K, step=step)
    noise = noise_variance_proxy(log_returns(log_px))
    # Amihud on 1-min calendar bars from tape
    # build 60s returns + dollar volume
    t = np.asarray(tape["ts"], dtype=np.int64)
    px = np.asarray(tape["px"], dtype=np.float64)
    qty = np.asarray(tape["qty"], dtype=np.float64)
    bar_ns = 60_000_000_000
    t0, t1 = int(t.min()), int(t.max())
    edges = np.arange(t0, t1 + bar_ns, bar_ns, dtype=np.int64)
    last_px = np.full(edges.size, np.nan)
    dvol = np.zeros(edges.size)
    idx = np.searchsorted(edges, t, side="right") - 1
    idx = np.clip(idx, 0, edges.size - 1)
    for i, j in enumerate(idx):
        if np.isfinite(px[i]) and px[i] > 0:
            last_px[j] = px[i]
            dvol[j] += float(qty[i]) * float(px[i])
    # forward fill last_px for returns
    last = np.nan
    for i in range(last_px.size):
        if np.isfinite(last_px[i]):
            last = last_px[i]
        elif np.isfinite(last):
            last_px[i] = last
    r60 = np.diff(np.log(last_px))
    am = amihud_illiquidity(r60, dvol[1:])
    intens = trade_intensity(t, bar_ns=1_000_000_000)
    tob = _tob_day_spread(venue, symbol, day)
    return {
        "ok": True,
        "venue": venue,
        "day": day,
        "symbol": symbol,
        "complete": bool(comp.get("complete", False)),
        "n_trades": int(tape.get("n", t.size)),
        "coverage_grid": float(g["coverage"]),
        "noise_std": float(noise["noise_std"]),
        "noise_var": float(noise["noise_var"]),
        "first_adj": float(est["first_adj"]),
        "fifth": float(est["fifth"]),
        "fourth": float(est["fourth"]),
        "fifth_over_fourth": (
            float(est["fifth"] / est["fourth"])
            if np.isfinite(est["fifth"]) and np.isfinite(est["fourth"]) and est["fourth"] > 0
            else float("nan")
        ),
        "amihud": float(am["illiq"]),
        "amihud_n": float(am["n"]),
        "intensity_mean": float(intens.get("mean_lambda", float("nan"))),
        "spread": tob,
    }


def _corr_block(rows: list[dict], *, n_shuffle: int = 400, seed: int = 7) -> dict:
    """Spearman noise_std vs spread / Amihud + shuffle null + time-split."""
    ok = [r for r in rows if r.get("ok") and r.get("spread", {}).get("ok")]
    noise = np.array([r["noise_std"] for r in ok], dtype=np.float64)
    spread = np.array([r["spread"]["spread_bps_mean"] for r in ok], dtype=np.float64)
    amihud = np.array([r["amihud"] for r in ok], dtype=np.float64)
    intens = np.array([r["intensity_mean"] for r in ok], dtype=np.float64)
    days = [r["day"] for r in ok]

    def _safe_spear(a, b):
        return float(spearman_r(a, b)) if a.size >= 3 else float("nan")

    r_spread = _safe_spear(noise, spread)
    r_amihud = _safe_spear(noise, amihud)
    r_intens = _safe_spear(noise, intens)

    rng = np.random.default_rng(seed)
    sh_spread = []
    sh_amihud = []
    for _ in range(n_shuffle):
        sh_spread.append(_safe_spear(noise, rng.permutation(spread)))
        sh_amihud.append(_safe_spear(noise, rng.permutation(amihud)))
    sh_spread_a = np.asarray(sh_spread, dtype=np.float64)
    sh_amihud_a = np.asarray(sh_amihud, dtype=np.float64)
    sh_spread_a = sh_spread_a[np.isfinite(sh_spread_a)]
    sh_amihud_a = sh_amihud_a[np.isfinite(sh_amihud_a)]

    def _p_two_sided(obs: float, null: NDArray) -> float:
        if not np.isfinite(obs) or null.size == 0:
            return float("nan")
        return float(np.mean(np.abs(null) >= abs(obs)))

    # time-split by day order
    uniq_days = sorted(set(days))
    mid = max(len(uniq_days) // 2, 1)
    early_d, late_d = set(uniq_days[:mid]), set(uniq_days[mid:])
    early_idx = [i for i, d in enumerate(days) if d in early_d]
    late_idx = [i for i, d in enumerate(days) if d in late_d]

    def _sub(idx, a, b):
        if len(idx) < 3:
            return float("nan")
        return _safe_spear(a[idx], b[idx])

    return {
        "n_rows": int(len(ok)),
        "spearman_noise_vs_spread": r_spread,
        "spearman_noise_vs_amihud": r_amihud,
        "spearman_noise_vs_intensity": r_intens,
        "shuffle": {
            "n": int(n_shuffle),
            "spread_p": _p_two_sided(r_spread, sh_spread_a),
            "amihud_p": _p_two_sided(r_amihud, sh_amihud_a),
            "spread_null_p95": float(np.quantile(np.abs(sh_spread_a), 0.95)) if sh_spread_a.size else float("nan"),
            "amihud_null_p95": float(np.quantile(np.abs(sh_amihud_a), 0.95)) if sh_amihud_a.size else float("nan"),
        },
        "time_split": {
            "early_days": sorted(early_d),
            "late_days": sorted(late_d),
            "early_noise_spread": _sub(early_idx, noise, spread),
            "late_noise_spread": _sub(late_idx, noise, spread),
            "early_noise_amihud": _sub(early_idx, noise, amihud),
            "late_noise_amihud": _sub(late_idx, noise, amihud),
        },
    }


def _decide(corr: dict) -> dict:
    """Promote only if sign matches thesis (+), shuffle p small, time-split same sign."""
    r = corr.get("spearman_noise_vs_spread", float("nan"))
    p = (corr.get("shuffle") or {}).get("spread_p", float("nan"))
    ts = corr.get("time_split") or {}
    e, l = ts.get("early_noise_spread"), ts.get("late_noise_spread")
    same_sign = (
        np.isfinite(e)
        and np.isfinite(l)
        and np.isfinite(r)
        and (e * r > 0)
        and (l * r > 0)
    )
    thesis_sign = bool(np.isfinite(r) and r > 0)
    shuffle_ok = bool(np.isfinite(p) and p < 0.05)
    if thesis_sign and shuffle_ok and same_sign and corr.get("n_rows", 0) >= 6:
        decision = "Promote"
        why = f"ρ={r:.3f} shuffle_p={p:.3f} early/late={e}/{l}"
    elif thesis_sign and corr.get("n_rows", 0) >= 4:
        decision = "Hold"
        why = f"ρ={r:.3f} but falsifier weak (p={p}, same_sign={same_sign}, n={corr.get('n_rows')})"
    else:
        decision = "Kill" if (np.isfinite(r) and r <= 0 and corr.get("n_rows", 0) >= 4) else "Hold"
        why = f"ρ={r:.3f} p={p} n={corr.get('n_rows')} same_sign={same_sign}"
    return {"decision": decision, "why": why, "id": "liq.noise_vs_spread"}


def _write_report(payload: dict) -> None:
    rows = payload["rows"]
    corr = payload["corr"]
    gate = payload["gate"]
    lines = [
        "# Market noise — EXP_REPORT (Pass 1+2)",
        "",
        "## Sample",
        f"- Symbols: {payload['meta']['symbols']}",
        f"- Days: {payload['meta']['days']}",
        f"- Venues: {list(CORE_VENUES)}",
        f"- Grid: {payload['meta']['dt_s']}s; K={payload['meta']['K']} step={payload['meta']['step']}",
        "",
        "## Per-row (noise × liquidity)",
    ]
    for r in rows:
        if not r.get("ok"):
            lines.append(f"- {r.get('symbol')} {r.get('venue')} {r.get('day')}: FAIL {r.get('reason')}")
            continue
        sp = r.get("spread") or {}
        lines.append(
            f"- {r['symbol']} {r['venue']} {r['day']}: noise_std={r['noise_std']:.6g} "
            f"spread_bps={sp.get('spread_bps_mean', float('nan')):.4g} "
            f"amihud={r['amihud']:.6g} intens={r['intensity_mean']:.4g} "
            f"complete={r['complete']} tob_n={sp.get('n_tob', 0)}"
        )
    sh = corr.get("shuffle") or {}
    ts = corr.get("time_split") or {}
    lines += [
        "",
        "## Falsifiers",
        f"- Spearman(noise, spread) = {corr.get('spearman_noise_vs_spread')}",
        f"- Spearman(noise, Amihud) = {corr.get('spearman_noise_vs_amihud')}",
        f"- Spearman(noise, intensity) = {corr.get('spearman_noise_vs_intensity')}",
        f"- Shuffle p (spread) = {sh.get('spread_p')}  (null |ρ| p95 = {sh.get('spread_null_p95')})",
        f"- Shuffle p (Amihud) = {sh.get('amihud_p')}",
        f"- Time-split early/late ρ(noise,spread) = {ts.get('early_noise_spread')} / {ts.get('late_noise_spread')}",
        f"- Days early={ts.get('early_days')} late={ts.get('late_days')}",
        "",
        "## Gate",
        f"- `{gate['id']}` → **{gate['decision']}** — {gate['why']}",
        "",
        f"- JSON: `{OUT.relative_to(BOOK)}/market_noise.json`",
        "",
    ]
    (CH / "EXP_REPORT.md").write_text("\n".join(lines))
    cand = (
        "| id | type | lenses | decision | falsifier |\n"
        "|----|------|--------|----------|----------|\n"
        f"| `liq.noise_vs_spread` | panel | liq, cont | **{gate['decision']}** | shuffle + time-split — {gate['why']} |\n"
    )
    (CH / "CANDIDATES.md").write_text(cand)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="ETH,BTC")
    ap.add_argument("--days", default="")
    ap.add_argument("--n-days", type=int, default=3)
    ap.add_argument("--K", type=int, default=300)
    ap.add_argument("--step", type=int, default=300)
    ap.add_argument("--dt-s", type=float, default=1.0)
    ap.add_argument("--max-files", type=int, default=24)
    ap.add_argument("--n-shuffle", type=int, default=400)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        ensure_env()
    except Exception as e:  # noqa: BLE001
        print(f"ensure_env warn: {e}", flush=True)

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    day_list = [d.strip() for d in args.days.split(",") if d.strip()] or None
    days = resolve_days(day_list, venue="hyperliquid", n=args.n_days)
    rows: list[dict] = []
    for sym in symbols:
        for day in days:
            for venue in CORE_VENUES:
                print(f"market_noise {sym} {venue} {day} …", flush=True)
                rows.append(
                    _row(
                        venue,
                        sym,
                        day,
                        K=args.K,
                        step=args.step,
                        dt_s=args.dt_s,
                        max_files=args.max_files,
                    )
                )
    corr = _corr_block(rows, n_shuffle=args.n_shuffle)
    gate = _decide(corr)
    payload = {
        "meta": {
            "symbols": symbols,
            "days": days,
            "K": args.K,
            "step": args.step,
            "dt_s": args.dt_s,
        },
        "rows": rows,
        "corr": corr,
        "gate": gate,
    }
    path = OUT / "market_noise.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    _write_report(payload)
    print(json.dumps({"gate": gate, "corr": {k: corr[k] for k in corr if k != "shuffle"}}, indent=2))
    print(f"Wrote {path} ok={sum(1 for r in rows if r.get('ok'))}/{len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
