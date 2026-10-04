from __future__ import annotations
#!/usr/bin/env python3
"""Pass 2.7 expand-panel — full listing-cache history + SOL.

Inventory ceiling (this host): HL/Deribit/Kraken listing caches each have
2026-08-28 … 2026-09-30 (34 UTC days). Collector TOB only last 2 days.
Kraken futures historical L2 still absent — spot L2 + proxies/REST.

Expands mid-clock / noise↔spread / TSRV OOS / clocks / xvenue concordance.
Checkpoint resume under out/expand_panel/rows.jsonl.

ClickHouse MCP banned. No git commits.
"""

import os

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(Path(os.environ.get('WAREHOUSE_SRC') or ((Path(os.environ.get('WAREHOUSE_ROOT') or (Path.home() / 'lab' / 'lab-n2070' / 'warehouse')) / 'src')))))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb')) / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import CORE_VENUES, ensure_env, resolve_days  # noqa: E402
from ares_micro.flow.continuous import amihud_illiquidity, trade_intensity  # noqa: E402
from ares_micro.stats import spearman_r  # noqa: E402
from ares_micro.vol.tsrv import compare_clocks_bootstrap  # noqa: E402

# Reuse day-row builder from blocker_close
from exp_blocker_close import (  # noqa: E402
    GATE_MID_CI_LO,
    GATE_TSRV_N,
    _boot_median_ci,
    _day_row,
    _mid_clock_decision,
    _tsrv_oos,
)

OUT = BOOK / "out" / "expand_panel"
LISTING = Path.home() / ".cache" / "warehouse" / "listings"


def _listing_days(bucket: str) -> list[str]:
    root = LISTING / bucket
    if not root.is_dir():
        return []
    return sorted(p.stem for p in root.glob("*.json"))


def _all_days() -> list[str]:
    sets = [
        set(_listing_days("mercat-hyperliquid-md")),
        set(_listing_days("mercat-deribit-md")),
        set(_listing_days("mercat-kraken-md")),
    ]
    inter = sorted(set.intersection(*sets)) if all(sets) else sorted(set.union(*sets))
    return inter


def _spearman_boot_ci(x, y, *, n_boot=1000, seed=3):
    a = np.asarray(x, dtype=np.float64)
    b = np.asarray(y, dtype=np.float64)
    m = np.isfinite(a) & np.isfinite(b)
    a, b = a[m], b[m]
    if a.size < 5:
        return {"n": float(a.size), "rho": float("nan"), "lo": float("nan"), "hi": float("nan")}
    rng = np.random.default_rng(seed)
    point = float(spearman_r(a, b))
    boots = [float(spearman_r(a[rng.integers(0, a.size, size=a.size)], b[rng.integers(0, a.size, size=a.size)])) for _ in range(n_boot)]
    boots_a = np.asarray(boots)
    boots_a = boots_a[np.isfinite(boots_a)]
    lo, hi = np.quantile(boots_a, [0.025, 0.975]) if boots_a.size else (float("nan"), float("nan"))
    return {"n": float(a.size), "rho": point, "lo": float(lo), "hi": float(hi)}


def _shuffle_p(x, y, *, n_shuffle, seed):
    a = np.asarray(x, dtype=np.float64)
    b = np.asarray(y, dtype=np.float64)
    m = np.isfinite(a) & np.isfinite(b)
    a, b = a[m], b[m]
    if a.size < 5:
        return float("nan")
    obs = abs(float(spearman_r(a, b)))
    rng = np.random.default_rng(seed)
    null = [abs(float(spearman_r(a, rng.permutation(b)))) for _ in range(n_shuffle)]
    null_a = np.asarray(null)
    null_a = null_a[np.isfinite(null_a)]
    return float(np.mean(null_a >= obs)) if null_a.size else float("nan")


def _block_shuffle_p(x, y, days, *, n_shuffle, seed):
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
        null.append(abs(float(spearman_r(a, b2))))
    null_a = np.asarray(null, dtype=np.float64)
    null_a = null_a[np.isfinite(null_a)]
    return float(np.mean(null_a >= obs)) if null_a.size else float("nan")


def _attach_amihud(row: dict) -> dict:
    """Best-effort Amihud from calendar path already loaded — skip heavy reload."""
    # Placeholder: expand uses tape only inside _day_row; Amihud needs tape.
    # We compute light Amihud only when spread ok by reusing n_trades proxy skip.
    return row


def _enrich_amihud_intensity(row: dict, *, max_files: int) -> dict:
    if not row.get("ok"):
        return row
    try:
        from _data import load_day_trades

        rec = load_day_trades(row["venue"], row["symbol"], row["day"], max_files=max_files, quiet=True)
        tape = rec["tape"]
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
        row["amihud"] = float(am["illiq"])
        row["intensity"] = float(intens.get("mean_lambda", float("nan")))
        row["noise_std"] = float((row.get("calendar") or {}).get("noise_std", float("nan")))
    except Exception as exc:  # noqa: BLE001
        row["amihud"] = float("nan")
        row["intensity"] = float("nan")
        row["noise_std"] = float((row.get("calendar") or {}).get("noise_std", float("nan")))
        row["amihud_error"] = f"{type(exc).__name__}: {exc}"
    return row


def _falsify_spread(rows: list[dict], *, n_shuffle: int) -> dict:
    ok = [
        r
        for r in rows
        if r.get("ok")
        and (r.get("spread") or {}).get("ok")
        and np.isfinite(r.get("noise_std", np.nan))
        and np.isfinite((r.get("spread") or {}).get("spread_bps_mean", np.nan))
    ]
    noise = np.array([r["noise_std"] for r in ok], dtype=np.float64)
    spread = np.array([r["spread"]["spread_bps_mean"] for r in ok], dtype=np.float64)
    amihud = np.array([r.get("amihud", np.nan) for r in ok], dtype=np.float64)
    days = [r["day"] for r in ok]
    kinds = [r["spread"].get("spread_kind") for r in ok]
    sources = [r["spread"].get("source") for r in ok]

    rho = _spearman_boot_ci(noise, spread, n_boot=1000, seed=3)
    rho_am = _spearman_boot_ci(noise, amihud, n_boot=1000, seed=4)
    sh_p = _shuffle_p(noise, spread, n_shuffle=n_shuffle, seed=9)
    blk_p = _block_shuffle_p(noise, spread, days, n_shuffle=n_shuffle, seed=10)

    uniq = sorted(set(days))
    mid = max(len(uniq) // 2, 1)
    early_d, late_d = set(uniq[:mid]), set(uniq[mid:])
    early = [i for i, d in enumerate(days) if d in early_d]
    late = [i for i, d in enumerate(days) if d in late_d]

    def _rho_idx(idx):
        if len(idx) < 5:
            return {"n": float(len(idx)), "rho": float("nan"), "lo": float("nan"), "hi": float("nan")}
        return _spearman_boot_ci(noise[idx], spread[idx], n_boot=800, seed=11)

    early_rho, late_rho = _rho_idx(early), _rho_idx(late)
    same_sign = (
        np.isfinite(rho["rho"])
        and np.isfinite(early_rho["rho"])
        and np.isfinite(late_rho["rho"])
        and (early_rho["rho"] * rho["rho"] > 0)
        and (late_rho["rho"] * rho["rho"] > 0)
    )
    ci_pos = bool(np.isfinite(rho["lo"]) and rho["lo"] > 0)
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
    why = (
        f"ρ={rho['rho']:.3f} CI=[{rho['lo']:.3f},{rho['hi']:.3f}] "
        f"shuffle_p={sh_p:.4f} block_p={blk_p:.4f} n={len(ok)} "
        f"same_sign={same_sign} ci_pos={ci_pos} early_n={early_rho['n']} late_n={late_rho['n']}"
    )
    if rho["rho"] > 0 and sh_p < 0.05 and same_sign and len(ok) >= 20 and ci_pos:
        gate = "Promote"
        why = (
            f"ρ={rho['rho']:.3f} CI=[{rho['lo']:.3f},{rho['hi']:.3f}] "
            f"shuffle_p={sh_p:.4f} block_p={blk_p:.4f} n={len(ok)} "
            f"early/late={early_rho['rho']:.3f}/{late_rho['rho']:.3f}"
        )
    elif np.isfinite(rho["rho"]) and rho["hi"] < 0 and len(ok) >= 20:
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
        "spread_kinds": {k: kinds.count(k) for k in sorted(set(map(str, kinds)))},
        "sources": {k: sources.count(k) for k in sorted(set(map(str, sources)))},
        "gate": {"id": "liq.noise_vs_spread", "decision": gate, "why": why},
    }


def _xvenue_concord(rows: list[dict]) -> dict:
    from collections import defaultdict

    ok = [r for r in rows if r.get("ok") and np.isfinite(r.get("noise_std", np.nan))]
    groups: dict[tuple[str, str], list] = defaultdict(list)
    for r in ok:
        groups[(r["day"], r["symbol"])].append(r)
    conc = []
    for (day, sym), g in groups.items():
        if len({r["venue"] for r in g}) < 2:
            continue
        vals = np.asarray([r["noise_std"] for r in g], dtype=float)
        rel = float((vals.max() - vals.min()) / max(float(np.median(vals)), 1e-12))
        conc.append(
            {
                "day": day,
                "symbol": sym,
                "n_venues": len(g),
                "rel_range": rel,
                "close": rel < 0.35,
            }
        )
    n = len(conc)
    frac = float(np.mean([c["close"] for c in conc])) if n else float("nan")
    return {
        "n_cells": n,
        "frac_rel_range_lt_0_35": frac,
        "gate": {
            "id": "frag.xvenue_noise_concord",
            "decision": "Hold",
            "why": f"frac_close={frac:.3f} n_cells={n} (descriptive concordance ≠ edge)",
        },
    }


def _load_checkpoint(path: Path) -> dict[tuple[str, str, str], dict]:
    out = {}
    if not path.exists():
        return out
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            out[(r["venue"], r["symbol"], r["day"])] = r
    return out


def _coverage_table(rows: list[dict]) -> dict:
    from collections import Counter

    ok = [r for r in rows if r.get("ok")]
    by_v = Counter(r["venue"] for r in ok)
    by_s = Counter(r["symbol"] for r in ok)
    quoted = sum(1 for r in ok if (r.get("spread") or {}).get("quoted_available"))
    mid_n = sum(1 for r in ok if np.isfinite(r.get("fifth_over_fourth_mid", np.nan)))
    sources = Counter(str((r.get("spread") or {}).get("source")) for r in ok)
    return {
        "n_rows": len(rows),
        "n_ok": len(ok),
        "n_quoted": quoted,
        "n_mid": mid_n,
        "by_venue": dict(by_v),
        "by_symbol": dict(by_s),
        "sources": dict(sources),
        "days": sorted({r["day"] for r in ok}),
        "n_days": len({r["day"] for r in ok}),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=["ETH", "BTC", "SOL"])
    ap.add_argument("--max-files", type=int, default=12)
    ap.add_argument("--K", type=int, default=300)
    ap.add_argument("--step", type=int, default=300)
    ap.add_argument("--n-boot", type=int, default=1500)
    ap.add_argument("--n-shuffle", type=int, default=800)
    ap.add_argument("--fresh", action="store_true", help="ignore checkpoint")
    args = ap.parse_args()
    ensure_env()

    days = _all_days()
    if not days:
        days = resolve_days(None, venue="hyperliquid", n=40)
    print(f"expand_panel days={len(days)} {days[0]}…{days[-1]} symbols={args.symbols}", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    ckpt = OUT / "rows.jsonl"
    done = {} if args.fresh else _load_checkpoint(ckpt)
    if args.fresh and ckpt.exists():
        ckpt.unlink()
    print(f"checkpoint loaded {len(done)} rows", flush=True)

    rows: list[dict] = []
    jobs = [(sym, day, venue) for sym in args.symbols for day in days for venue in CORE_VENUES]
    t0 = time.time()
    for i, (sym, day, venue) in enumerate(jobs, 1):
        key = (venue, sym, day)
        if key in done:
            row = done[key]
            # ensure amihud fields for old checkpoint rows
            if row.get("ok") and "noise_std" not in row:
                row["noise_std"] = float((row.get("calendar") or {}).get("noise_std", float("nan")))
            if row.get("ok") and "amihud" not in row:
                row = _enrich_amihud_intensity(row, max_files=args.max_files)
            rows.append(row)
            continue
        print(f"[{i}/{len(jobs)}] {sym} {venue} {day} …", flush=True)
        row = _day_row(venue, sym, day, max_files=args.max_files, K=args.K, step=args.step)
        if row.get("ok"):
            row = _enrich_amihud_intensity(row, max_files=args.max_files)
        else:
            row["noise_std"] = float("nan")
            row["amihud"] = float("nan")
        rows.append(row)
        with ckpt.open("a") as f:
            f.write(json.dumps(row, default=str) + "\n")
        if i % 10 == 0:
            ok = sum(1 for r in rows if r.get("ok"))
            print(f"  progress ok={ok}/{len(rows)} elapsed={time.time()-t0:.0f}s", flush=True)

    # If checkpoint had extras from previous symbols, keep only this run's jobs
    want = {(v, s, d) for s, d, v in jobs}
    rows = [r for r in rows if (r["venue"], r["symbol"], r["day"]) in want]
    # de-dupe prefer last
    uniq = {}
    for r in rows:
        uniq[(r["venue"], r["symbol"], r["day"])] = r
    rows = list(uniq.values())

    cov = _coverage_table(rows)
    mid = _mid_clock_decision(rows, n_boot=args.n_boot)
    tsrv = _tsrv_oos(rows, n_boot=args.n_boot)
    spread = _falsify_spread(rows, n_shuffle=args.n_shuffle)
    xvenue = _xvenue_concord(rows)

    # also kill calendar/trade/tick from mid per_clock
    decisions = {
        "cont.noise_mid_clock": mid["gate"],
        "cont.tsrv_first_adj": tsrv["gate"],
        "liq.noise_vs_spread": spread["gate"],
        "frag.xvenue_noise_concord": xvenue["gate"],
        "cont.sparse_rv_only": {"decision": "Kill", "why": "MC first_adj RMSE ≪ fourth; unchanged"},
        "cont.noise_dominates_1s_mid": mid["per_clock"].get("calendar"),
        "cont.noise_trade_clock_bounce": mid["per_clock"].get("trade"),
        "cont.noise_tick_bounce_clock": mid["per_clock"].get("tick_bounce"),
    }

    payload = {
        "meta": {
            "pass": "2.7_expand",
            "symbols": args.symbols,
            "days": days,
            "n_days": len(days),
            "venues": list(CORE_VENUES),
            "K": args.K,
            "step": args.step,
            "n_boot": args.n_boot,
            "n_shuffle": args.n_shuffle,
            "data_ceiling": {
                "listing_cache_days": 34,
                "range": [days[0], days[-1]] if days else [],
                "collector_tob_days": 2,
                "kraken_futures_historical_l2": False,
            },
            "prior_compare": {
                "blocker_close_n_ok": 90,
                "blocker_close_n_mid": 73,
                "gap_close_n_ok": 68,
                "gap_close_n_days": 14,
            },
            "gates": {
                "cont.noise_mid_clock": f"CI_lo(fifth/fourth)>{GATE_MID_CI_LO}",
                "cont.tsrv_first_adj": "fragile_rate=0 & sparse−tsrv CI_lo>0 early∧late & n≥20",
                "liq.noise_vs_spread": "ρ>0 & shuffle_p<0.05 & early∧late same sign & n≥20 & CI_lo>0",
            },
        },
        "coverage": cov,
        "rows": rows,
        "mid_clock": mid,
        "tsrv_oos": tsrv,
        "spread_falsify": spread,
        "xvenue": xvenue,
        "decisions": decisions,
    }
    (OUT / "expand_panel.json").write_text(json.dumps(payload, indent=2, default=str))

    # Also mirror into blocker_close / gap_close shapes for notebook builders that read those paths
    # Update blocker_close.json with expanded mid/tsrv so desk notebooks pick it up
    bc_out = BOOK / "out" / "blocker_close"
    bc_out.mkdir(parents=True, exist_ok=True)
    (bc_out / "blocker_close.json").write_text(
        json.dumps(
            {
                "meta": payload["meta"],
                "rows": rows,
                "mid_clock": mid,
                "tsrv_oos": tsrv,
                "decisions": {
                    "cont.noise_mid_clock": mid["gate"],
                    "cont.tsrv_first_adj": tsrv["gate"],
                    "cont.sparse_rv_only": decisions["cont.sparse_rv_only"],
                },
            },
            indent=2,
            default=str,
        )
    )
    gc_out = BOOK / "out" / "gap_close"
    gc_out.mkdir(parents=True, exist_ok=True)
    # preserve fig; overwrite json
    (gc_out / "gap_close.json").write_text(
        json.dumps(
            {
                "meta": payload["meta"],
                "rows": rows,
                "spread_falsify": spread,
                "clock_falsify": {
                    "bootstrap": mid.get("bootstrap_all_clocks"),
                    "per_clock": mid.get("per_clock"),
                },
                "tsrv_falsify": {
                    "fragile_rate": tsrv["fragile_rate"],
                    "first_adj_cv_median": float("nan"),
                    "sparse_minus_tsrv": tsrv["sparse_minus_tsrv"],
                    "gate": tsrv["gate"],
                },
            },
            indent=2,
            default=str,
        )
    )

    report = [
        "# Expand panel Pass 2.7",
        "",
        f"- days={len(days)} ({days[0]}…{days[-1]}) symbols={args.symbols}",
        f"- coverage: {json.dumps(cov)}",
        "",
        "## Decisions",
    ]
    for k, v in decisions.items():
        if not v:
            continue
        report.append(f"- `{k}` → **{v.get('decision')}** — {v.get('why','')}")
    report += [
        "",
        "## vs prior",
        f"- prior blocker n_ok=90 n_mid=73 → now n_ok={cov['n_ok']} n_mid={cov['n_mid']}",
        f"- prior gap n_ok=68 → now spread n={spread['n_rows']}",
        "",
    ]
    (OUT / "expand_panel_REPORT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"coverage": cov, "decisions": {k: v.get("decision") if v else None for k, v in decisions.items()}}, indent=2))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
