from __future__ import annotations
#!/usr/bin/env python3
"""Blocker-close Pass 2.6 — denser mid-clock CI + TSRV tape OOS.

1. Expand dense quoted-TOB days: HL + Deribit warehouse + Kraken spot L2
   (S3 public-md). Futures quoted TOB via local REST ingest when present.
2. Mid vs calendar/trade/tick clocks — bootstrap CIs; Promote mid only if
   pre-registered gate CI_lo(fifth/fourth) > 1.5.
3. Tape-level TSRV vs sparse: chronological time-split + rolling OOS;
   MC Kill of sparse policy stands — Promote first_adj only if OOS CI clears.

ClickHouse MCP banned. No git commits.
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
from research.lib.tsrv import (  # noqa: E402
    compare_clocks_bootstrap,
    estimators_on_log_px,
    estimators_trade_clock,
    grid_log_price_from_tape,
    k_step_ablation,
    mid_clock_log_px,
    tick_rule_bounce_path,
)

OUT = BOOK / "out" / "blocker_close"

# Pre-registered Promote gates (must match CANDIDATES / DESK_MEMO)
GATE_MID_CI_LO = 1.5
GATE_TSRV_N = 20


def _boot_median_ci(x: NDArray[np.float64], *, n_boot: int = 1200, seed: int = 7) -> dict:
    a = np.asarray(x, dtype=np.float64)
    a = a[np.isfinite(a)]
    if a.size < 3:
        return {
            "n": float(a.size),
            "median": float("nan"),
            "mean": float("nan"),
            "se": float("nan"),
            "ci95": [float("nan"), float("nan")],
        }
    rng = np.random.default_rng(seed)
    boots = np.asarray(
        [float(np.median(a[rng.integers(0, a.size, size=a.size)])) for _ in range(n_boot)],
        dtype=np.float64,
    )
    lo, hi = np.quantile(boots, [0.025, 0.975])
    return {
        "n": float(a.size),
        "median": float(np.median(a)),
        "mean": float(np.mean(a)),
        "se": float(np.std(boots, ddof=1)),
        "ci95": [float(lo), float(hi)],
    }


def _spread_tob(venue: str, symbol: str, day: str, tape: dict, *, max_files: int) -> dict:
    """Prefer real quoted TOB (incl. Kraken spot L2 / futures ingest); else proxy."""
    try:
        tob = load_tob_day(venue, symbol, day, max_files=max_files)
        from research.lib.spreads import quoted_spread_bps

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


def _day_row(venue: str, symbol: str, day: str, *, max_files: int, K: int, step: int) -> dict:
    try:
        rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "venue": venue, "symbol": symbol, "day": day, "reason": f"load:{exc}"}
    tape = rec["tape"]
    if int(tape.get("n", 0)) < 50:
        return {"ok": False, "venue": venue, "symbol": symbol, "day": day, "reason": "empty"}
    g = grid_log_price_from_tape(tape["ts"], tape["px"], dt_s=1.0)
    if int(g["n_filled"]) < 60 or g["log_px"].size < step + 2:
        return {"ok": False, "venue": venue, "symbol": symbol, "day": day, "reason": "short_grid"}

    cal = estimators_on_log_px(g["log_px"], K=K, step=step)
    abl = k_step_ablation(g["log_px"])
    tc = estimators_trade_clock(tape["ts"], tape["px"], K=min(K, 50), step=min(step, 50), max_n=40_000)
    bounce = tick_rule_bounce_path(tape["ts"], tape["px"], max_n=40_000)
    bc = estimators_on_log_px(bounce["log_px"], K=min(K, 50), step=min(step, 50))

    spread = _spread_tob(venue, symbol, day, tape, max_files=max_files)
    mid_est: dict = {}
    if spread.get("quoted_available") and "bid" in spread:
        mg = mid_clock_log_px(spread["ts"], spread["bid"], spread["ask"], dt_s=1.0)
        mid_est = estimators_on_log_px(mg["log_px"], K=K, step=step)
        spread = {k: v for k, v in spread.items() if k not in ("bid", "ask", "ts")}

    fa = float(cal.get("first_adj", float("nan")))
    fo = float(cal.get("fourth", float("nan")))
    fi = float(cal.get("fifth", float("nan")))
    return {
        "ok": True,
        "venue": venue,
        "symbol": symbol,
        "day": day,
        "n_trades": int(tape.get("n", 0)),
        "calendar": cal,
        "trade_clock": tc,
        "tick_bounce": bc,
        "mid_clock": mid_est,
        "ablation": {
            "first_adj_cv": abl["first_adj_cv"],
            "fragile_first_adj": abl["fragile_first_adj"],
        },
        "fifth_over_fourth_cal": float(cal.get("fifth_over_fourth", float("nan"))),
        "fifth_over_fourth_tc": float(tc.get("fifth_over_fourth", float("nan"))),
        "fifth_over_fourth_bounce": float(bc.get("fifth_over_fourth", float("nan"))),
        "fifth_over_fourth_mid": float(mid_est.get("fifth_over_fourth", float("nan"))) if mid_est else float("nan"),
        "first_adj": fa,
        "fourth": fo,
        "fifth": fi,
        "sparse_minus_tsrv": (fo - fa) if np.isfinite(fa) and np.isfinite(fo) else float("nan"),
        "tsrv_over_sparse": (fa / fo) if np.isfinite(fa) and np.isfinite(fo) and fo > 0 else float("nan"),
        "spread": spread,
    }


def _mid_clock_decision(rows: list[dict], *, n_boot: int) -> dict:
    ok = [r for r in rows if r.get("ok")]
    clocks = {
        "calendar": [r["fifth_over_fourth_cal"] for r in ok],
        "trade": [r["fifth_over_fourth_tc"] for r in ok],
        "tick_bounce": [r["fifth_over_fourth_bounce"] for r in ok],
        "mid": [
            r["fifth_over_fourth_mid"]
            for r in ok
            if np.isfinite(r.get("fifth_over_fourth_mid", np.nan))
        ],
    }
    boot = compare_clocks_bootstrap(clocks, n_boot=n_boot, seed=21)
    # Extra dense-only mid CI (quoted TOB days only)
    mid_vals = np.asarray(clocks["mid"], dtype=np.float64)
    mid_ci = _boot_median_ci(mid_vals, n_boot=n_boot, seed=22)
    # venue coverage for mid
    mid_cov = {}
    for v in CORE_VENUES:
        subv = [
            r
            for r in ok
            if r["venue"] == v and np.isfinite(r.get("fifth_over_fourth_mid", np.nan))
        ]
        mid_cov[v] = {
            "n_mid": len(subv),
            "sources": sorted({str((r.get("spread") or {}).get("source")) for r in subv}),
            "median": float(np.median([r["fifth_over_fourth_mid"] for r in subv])) if subv else float("nan"),
        }

    decisions = {}
    for name, st in boot["clocks"].items():
        lo = st["ci95"][0] if st.get("ci95") else float("nan")
        med = st.get("median", float("nan"))
        if np.isfinite(lo) and lo > GATE_MID_CI_LO:
            decisions[name] = {
                "decision": "Promote",
                "why": f"median={med:.3f} CI_lo={lo:.3f}>{GATE_MID_CI_LO} n={st['n']}",
            }
        elif name != "mid" and np.isfinite(med) and med < 1.2:
            decisions[name] = {
                "decision": "Kill",
                "why": f"median={med:.3f} CI={st.get('ci95')} n={st['n']} (no bounce domination)",
            }
        else:
            decisions[name] = {
                "decision": "Hold",
                "why": f"median={med:.3f} CI={st.get('ci95')} n={st['n']} gate CI_lo>{GATE_MID_CI_LO}",
            }

    # Prefer denser mid-only CI for cont.noise_mid_clock
    mid_lo = mid_ci["ci95"][0]
    if np.isfinite(mid_lo) and mid_lo > GATE_MID_CI_LO:
        mid_dec = {
            "decision": "Promote",
            "why": (
                f"dense mid median={mid_ci['median']:.3f} CI=[{mid_ci['ci95'][0]:.3f},"
                f"{mid_ci['ci95'][1]:.3f}] SE={mid_ci['se']:.3f} n={mid_ci['n']} "
                f"gate CI_lo>{GATE_MID_CI_LO}"
            ),
        }
    else:
        mid_dec = {
            "decision": "Hold",
            "why": (
                f"dense mid median={mid_ci['median']:.3f} CI=[{mid_ci['ci95'][0]:.3f},"
                f"{mid_ci['ci95'][1]:.3f}] SE={mid_ci['se']:.3f} n={mid_ci['n']} "
                f"(need CI_lo>{GATE_MID_CI_LO})"
            ),
        }
    decisions["mid"] = mid_dec

    return {
        "pre_registered_gate": f"median fifth/fourth CI_lo > {GATE_MID_CI_LO}",
        "bootstrap_all_clocks": boot,
        "mid_dense_ci": mid_ci,
        "mid_coverage_by_venue": mid_cov,
        "per_clock": decisions,
        "gate": {"id": "cont.noise_mid_clock", **mid_dec},
    }


def _tsrv_oos(rows: list[dict], *, n_boot: int) -> dict:
    ok = [r for r in rows if r.get("ok")]
    fragile = sum(1 for r in ok if r.get("ablation", {}).get("fragile_first_adj"))
    fragile_rate = fragile / max(len(ok), 1)

    days = [r["day"] for r in ok]
    adv = np.asarray([r["sparse_minus_tsrv"] for r in ok], dtype=np.float64)
    ratio = np.asarray([r["tsrv_over_sparse"] for r in ok], dtype=np.float64)
    uniq = sorted(set(days))
    mid = max(len(uniq) // 2, 1)
    early_d, late_d = set(uniq[:mid]), set(uniq[mid:])
    early_m = np.asarray([d in early_d for d in days])
    late_m = np.asarray([d in late_d for d in days])

    overall_adv = _boot_median_ci(adv, n_boot=n_boot, seed=4)
    early_adv = _boot_median_ci(adv[early_m], n_boot=n_boot, seed=5)
    late_adv = _boot_median_ci(adv[late_m], n_boot=n_boot, seed=6)
    overall_ratio = _boot_median_ci(ratio, n_boot=n_boot, seed=14)
    early_ratio = _boot_median_ci(ratio[early_m], n_boot=n_boot, seed=15)
    late_ratio = _boot_median_ci(ratio[late_m], n_boot=n_boot, seed=16)

    # Rolling 5-day windows: fraction with median(adv)>0
    roll = []
    for i in range(0, max(len(uniq) - 4, 1)):
        win = set(uniq[i : i + 5])
        m = np.asarray([d in win for d in days])
        if int(m.sum()) < 5:
            continue
        st = _boot_median_ci(adv[m], n_boot=400, seed=30 + i)
        roll.append({"days": sorted(win), **st, "ci_lo_pos": bool(st["ci95"][0] > 0)})
    roll_pos_frac = (
        float(np.mean([r["ci_lo_pos"] for r in roll])) if roll else float("nan")
    )

    promote = (
        fragile_rate == 0
        and overall_adv["ci95"][0] > 0
        and early_adv["ci95"][0] > 0
        and late_adv["ci95"][0] > 0
        and len(ok) >= GATE_TSRV_N
    )
    decision = "Promote" if promote else "Hold"
    why = (
        f"fragile_rate={fragile_rate:.3f} adv_med={overall_adv['median']:.3g} "
        f"CI={overall_adv['ci95']} SE={overall_adv['se']:.3g} "
        f"earlyCI={early_adv['ci95']} lateCI={late_adv['ci95']} "
        f"ratio_med={overall_ratio['median']:.4f} ratioCI={overall_ratio['ci95']} "
        f"roll_ci_lo_pos_frac={roll_pos_frac:.2f} n={len(ok)} "
        f"(MC Kill sparse still stands; Promote needs OOS CI_lo>0 early∧late)"
    )
    return {
        "pre_registered_gate": (
            "fragile_rate=0 ∧ sparse−tsrv CI_lo>0 early∧late ∧ n≥20; "
            "MC Kill of sparse_rv_only unchanged"
        ),
        "fragile_rate": fragile_rate,
        "sparse_minus_tsrv": {"overall": overall_adv, "early": early_adv, "late": late_adv},
        "tsrv_over_sparse": {"overall": overall_ratio, "early": early_ratio, "late": late_ratio},
        "rolling_5d": {"windows": roll, "frac_ci_lo_pos": roll_pos_frac},
        "mc_sparse_policy": "Kill (unchanged)",
        "gate": {"id": "cont.tsrv_first_adj", "decision": decision, "why": why},
    }


def _write_reports(payload: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "blocker_close.json").write_text(json.dumps(payload, indent=2, default=str))

    mid = payload["mid_clock"]
    tsrv = payload["tsrv_oos"]
    rows = payload["rows"]
    n_ok = sum(1 for r in rows if r.get("ok"))
    n_mid = sum(1 for r in rows if r.get("ok") and np.isfinite(r.get("fifth_over_fourth_mid", np.nan)))
    n_quoted = sum(1 for r in rows if r.get("ok") and (r.get("spread") or {}).get("quoted_available"))

    lines = [
        "# Blocker-close Pass 2.6",
        "",
        f"- n_ok={n_ok} venue-days; n_mid_clock={n_mid}; n_quoted_tob={n_quoted}",
        f"- days={payload['meta']['days']}",
        f"- symbols={payload['meta']['symbols']}",
        "",
        "## Kraken TOB inventory",
        "",
        "- **Futures S3/MRCTCAP1:** trade/mark/index/funding/OI only — no BBO/L2 in sealed archives.",
        "- **Spot S3 public-md:** `l2_snapshot_*` + `l2_delta` → `load_kraken_spot_tob_day` (`spot|ETH/USD`).",
        "- **Futures quoted TOB:** `scripts/ingest_kraken_futures_tob.py` → `out/kraken_futures_tob/`.",
        "",
        "## Mid-clock gate",
        "",
        f"- Pre-registered: `{mid['pre_registered_gate']}`",
        f"- **Decision `cont.noise_mid_clock`:** **{mid['gate']['decision']}** — {mid['gate']['why']}",
        f"- Dense mid CI: {mid['mid_dense_ci']}",
        f"- Coverage: {json.dumps(mid['mid_coverage_by_venue'])}",
        "",
        "## TSRV OOS vs sparse",
        "",
        f"- Pre-registered: `{tsrv['pre_registered_gate']}`",
        f"- **Decision `cont.tsrv_first_adj`:** **{tsrv['gate']['decision']}** — {tsrv['gate']['why']}",
        f"- MC sparse policy: **{tsrv['mc_sparse_policy']}**",
        "",
        "## Decision table (blocker slice)",
        "",
        "| ID | Decision |",
        "|----|----------|",
        f"| `cont.noise_mid_clock` | **{mid['gate']['decision']}** |",
        f"| `cont.tsrv_first_adj` | **{tsrv['gate']['decision']}** |",
        "| `cont.sparse_rv_only` | **Kill** (MC; unchanged) |",
        "",
    ]
    (OUT / "blocker_close_REPORT.md").write_text("\n".join(lines) + "\n")

    # chapter EXP_REPORT snippets
    est = BOOK / "chapters" / "estimators" / "EXP_REPORT.md"
    est.write_text(
        "\n".join(
            [
                "# Estimators — EXP_REPORT (Pass 2.6 blocker-close)",
                "",
                f"**`cont.tsrv_first_adj`:** **{tsrv['gate']['decision']}** — {tsrv['gate']['why']}",
                "",
                f"- sparse−tsrv overall: {tsrv['sparse_minus_tsrv']['overall']}",
                f"- early/late: {tsrv['sparse_minus_tsrv']['early']} / {tsrv['sparse_minus_tsrv']['late']}",
                f"- tsrv/sparse ratio: {tsrv['tsrv_over_sparse']['overall']}",
                f"- rolling 5d frac CI_lo>0: {tsrv['rolling_5d']['frac_ci_lo_pos']}",
                "- **`cont.sparse_rv_only` remains Kill** (MC first_adj RMSE ≪ fourth).",
                "",
                f"Artifact: [`../../out/blocker_close/blocker_close.json`](../../out/blocker_close/blocker_close.json)",
                "",
            ]
        )
    )
    mn = BOOK / "chapters" / "market_noise" / "EXP_REPORT.md"
    mn.write_text(
        "\n".join(
            [
                "# Market noise / clocks — EXP_REPORT (Pass 2.6)",
                "",
                "## TOB paths",
                "",
                "- **HL:** warehouse `l2_rebuild` (+ collector when present).",
                "- **Deribit:** warehouse `l2_snapshot_level`.",
                "- **Kraken spot:** warehouse `l2_rebuild` via `spot|BTC/USD` / `spot|ETH/USD` (S3 public-md).",
                "- **Kraken futures:** no L2/BBO in S3 archives; REST ingest → `out/kraken_futures_tob/`.",
                "",
                "## Mid-clock",
                "",
                f"**`cont.noise_mid_clock`:** **{mid['gate']['decision']}** — {mid['gate']['why']}",
                "",
                f"- n_mid={n_mid}; dense CI={mid['mid_dense_ci']}",
                f"- coverage={json.dumps(mid['mid_coverage_by_venue'])}",
                f"- calendar/trade/tick remain Kill/Hold per `{mid['per_clock']}`",
                "",
                f"Artifact: [`../../out/blocker_close/blocker_close.json`](../../out/blocker_close/blocker_close.json)",
                "",
            ]
        )
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=["ETH", "BTC"])
    ap.add_argument("--n-days", type=int, default=21)
    ap.add_argument("--max-files", type=int, default=16)
    ap.add_argument("--K", type=int, default=300)
    ap.add_argument("--step", type=int, default=300)
    ap.add_argument("--n-boot", type=int, default=1200)
    ap.add_argument(
        "--kraken-max-days",
        type=int,
        default=10,
        help="Cap Kraken spot L2 rebuild days (expensive); HL/Deribit use full panel",
    )
    args = ap.parse_args()
    ensure_env()

    days = resolve_days(None, venue="hyperliquid", n=args.n_days)
    if len(days) < 5:
        days = resolve_days(None, venue="deribit", n=args.n_days)
    kraken_days = set(days[-args.kraken_max_days :]) if args.kraken_max_days > 0 else set()

    rows: list[dict] = []
    for sym in args.symbols:
        for day in days:
            for venue in CORE_VENUES:
                if venue == "kraken" and day not in kraken_days:
                    continue
                print(f"blocker_close {sym} {venue} {day} …", flush=True)
                rows.append(
                    _day_row(venue, sym, day, max_files=args.max_files, K=args.K, step=args.step)
                )

    mid = _mid_clock_decision(rows, n_boot=args.n_boot)
    tsrv = _tsrv_oos(rows, n_boot=args.n_boot)
    payload = {
        "meta": {
            "symbols": args.symbols,
            "days": days,
            "kraken_days": sorted(kraken_days),
            "n_days": len(days),
            "K": args.K,
            "step": args.step,
            "n_boot": args.n_boot,
            "gates": {
                "cont.noise_mid_clock": f"CI_lo(fifth/fourth)>{GATE_MID_CI_LO}",
                "cont.tsrv_first_adj": "fragile_rate=0 & sparse−tsrv CI_lo>0 early∧late & n≥20",
                "cont.sparse_rv_only": "Kill (MC; unchanged)",
            },
        },
        "rows": rows,
        "mid_clock": mid,
        "tsrv_oos": tsrv,
        "decisions": {
            "cont.noise_mid_clock": mid["gate"],
            "cont.tsrv_first_adj": tsrv["gate"],
            "cont.sparse_rv_only": {
                "decision": "Kill",
                "why": "MC first_adj RMSE ≪ fourth; unchanged",
            },
        },
    }
    _write_reports(payload)
    print(json.dumps(payload["decisions"], indent=2))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
