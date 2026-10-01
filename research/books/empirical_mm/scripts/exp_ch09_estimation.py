from __future__ import annotations
#!/usr/bin/env python3
"""Ch.9 estimation case study — crypto remake of Hasbrouck Case Study I.

Book: Roll + MA(1)/AR σ_w vs quoted spreads on one symbol×day (TAQ/SAS).
Here: ETH HL trades + collector TOB; moments + AR truncation + day/time blocks.
No ClickHouse MCP.
"""

import os

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb')) / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import (  # noqa: E402
    ensure_env,
    load_hl_tob,
    load_trades,
    overlap_trades_with_mids,
    resolve_days,
)
from research.lib.continuous import (  # noqa: E402
    calendar_returns,
    noise_robust_rv,
    noise_rv_ratio_bootstrap,
)
from research.lib.discrete import (  # noqa: E402
    ar_ols,
    impact_multipliers_from_ar,
    ma1_from_acov,
    roll_on_mid_bps,
    rw_variance_from_ar,
)
from research.lib.spreads import quoted_spread_bps  # noqa: E402
from research.lib.stats import bootstrap_ci, time_split_mask  # noqa: E402

OUT = BOOK / "out" / "ch09_estimation"


def _log_returns(px: np.ndarray) -> np.ndarray:
    p = np.asarray(px, dtype=np.float64)
    p = p[np.isfinite(p) & (p > 0)]
    if p.size < 3:
        return np.zeros(0, dtype=np.float64)
    return np.diff(np.log(p))


def _block_sigma_w(dp: np.ndarray, ts: np.ndarray, *, lags: int = 10) -> dict:
    """Fama–MacBeth-style: AR σ_w per calendar-day block."""
    if dp.size < 100 or ts.size != dp.size + 0 and ts.size < dp.size:
        # align: ts for levels → use midpoints of return intervals
        pass
    t = np.asarray(ts, dtype=np.int64)
    if t.size == dp.size + 1:
        t = t[1:]
    elif t.size != dp.size:
        t = t[: dp.size]
    day = t // 86_400_000_000_000  # ns → day id
    vals = []
    for d in np.unique(day):
        m = day == d
        if int(m.sum()) < lags + 50:
            continue
        ar = ar_ols(dp[m], lags=lags)
        rw = rw_variance_from_ar(ar)
        if np.isfinite(rw.get("sigma_w", np.nan)):
            vals.append(float(rw["sigma_w"]))
    if not vals:
        return {"n_blocks": 0, "mean": float("nan"), "se": float("nan"), "vals": []}
    v = np.asarray(vals, dtype=np.float64)
    se = float(v.std(ddof=1) / np.sqrt(v.size)) if v.size > 1 else float("nan")
    return {"n_blocks": int(v.size), "mean": float(v.mean()), "se": se, "vals": vals}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--days", nargs="*", default=None)
    ap.add_argument("--max-files", type=int, default=24)
    args = ap.parse_args()
    ensure_env()
    days = resolve_days(args.days)
    OUT.mkdir(parents=True, exist_ok=True)

    tob = load_hl_tob(args.symbol)
    tape = load_trades(args.symbol, days, args.max_files)
    ov = overlap_trades_with_mids(tape, tob)

    mid0 = ov["mid0"]
    ok = np.isfinite(mid0) & (mid0 > 0) & np.isfinite(ov["px"]) & (ov["px"] > 0)
    mid_ev = mid0[ok]
    px_ev = ov["px"][ok]
    ts_ev = ov["ts"][ok]

    dp_mid = _log_returns(mid_ev)
    dp_px = _log_returns(px_ev)
    # drop first return analogue of "discard overnight glue" — here: drop if gap > 1h
    # (crypto 24/7: still mark large gaps)
    gaps = np.diff(ts_ev)
    gap_ok = gaps[1:] < 3_600_000_000_000  # align to dp length = n-1; skip first gap row
    if gap_ok.size == dp_mid.size - 1:
        # dp[i] uses ts[i]→ts[i+1]; flag large gaps after first
        keep = np.ones(dp_mid.size, dtype=bool)
        keep[1:] = gaps[1:] < 3_600_000_000_000
        dp_mid_c = dp_mid[keep]
        dp_px_c = dp_px[keep]
        ts_dp = ts_ev[1:][keep]
    else:
        dp_mid_c, dp_px_c, ts_dp = dp_mid, dp_px, ts_ev[1 : 1 + dp_mid.size]

    roll_mid = roll_on_mid_bps(mid_ev)
    roll_px = roll_on_mid_bps(px_ev)
    ma1_mid = ma1_from_acov(dp_mid_c)
    ma1_px = ma1_from_acov(dp_px_c)

    ar3 = ar_ols(dp_mid_c, lags=3)
    ar10 = ar_ols(dp_mid_c, lags=10)
    rw3 = rw_variance_from_ar(ar3)
    rw10 = rw_variance_from_ar(ar10)
    irf = impact_multipliers_from_ar(ar10, horizon=20)

    # quoted spread on TOB (array → bootstrap CI, same as ch22)
    qs_arr = quoted_spread_bps(tob["bid"], tob["ask"], mid=tob["mid"])
    qs = bootstrap_ci(qs_arr, n_boot=300, seed=55)
    noise = noise_robust_rv(tob["ts"], tob["mid"])
    noise_boot = noise_rv_ratio_bootstrap(tob["ts"], tob["mid"], n_blocks=24, n_boot=400)
    _, r_cal = calendar_returns(tob["ts"], tob["mid"], bar_ns=1_000_000_000)
    ar_cal = ar_ols(r_cal[np.isfinite(r_cal)], lags=10)
    rw_cal = rw_variance_from_ar(ar_cal)

    tr, te = time_split_mask(ts_dp, train_frac=0.7)
    rw_tr = rw_variance_from_ar(ar_ols(dp_mid_c[tr], lags=10))
    rw_te = rw_variance_from_ar(ar_ols(dp_mid_c[te], lags=10))
    blocks = _block_sigma_w(dp_mid_c, ts_dp, lags=10)

    # decisions
    decisions = {}
    lenses = {}

    ma_ok = bool(ma1_mid.get("identified"))
    decisions["disc.ma1_moments"] = "Promote" if ma_ok and ma1_mid.get("sigma_w", 0) > 0 else (
        "Hold" if ma_ok else "Kill"
    )
    # Prefer Hold when Roll-like unidentified: still useful method when identified on px
    if not ma_ok and bool(ma1_px.get("identified")):
        decisions["disc.ma1_moments"] = "Hold"
    lenses["disc.ma1_moments"] = ["disc", "info"]

    sw_ok = np.isfinite(rw10.get("sigma_w", np.nan)) and rw10["sigma_w"] > 0
    split_ok = (
        np.isfinite(rw_tr.get("sigma_w", np.nan))
        and np.isfinite(rw_te.get("sigma_w", np.nan))
        and rw_tr["sigma_w"] > 0
        and rw_te["sigma_w"] > 0
    )
    decisions["disc.ar_sigma_w"] = "Promote" if sw_ok and split_ok else ("Hold" if sw_ok else "Kill")
    lenses["disc.ar_sigma_w"] = ["disc", "info", "mm"]

    decisions["disc.roll_vs_quote"] = (
        "Kill" if not roll_mid.get("identified") else "Hold"
    )
    lenses["disc.roll_vs_quote"] = ["disc", "liq"]

    # Promote only if fine RV clearly inflates (microstructure noise); else Kill.
    nr = noise_boot.get("noise_ratio", noise.get("noise_ratio", float("nan")))
    ci_lo, ci_hi = noise_boot.get("ratio_ci95", [float("nan"), float("nan")])
    if noise_boot.get("ok") and np.isfinite(ci_lo) and ci_lo > 1.2:
        decisions["cont.noise_rv_ratio"] = "Promote"
    elif np.isfinite(nr) and (nr <= 1.05 or (np.isfinite(ci_hi) and ci_hi <= 1.2)):
        decisions["cont.noise_rv_ratio"] = "Kill"
    elif np.isfinite(nr):
        decisions["cont.noise_rv_ratio"] = "Hold"
    else:
        decisions["cont.noise_rv_ratio"] = "Kill"
    lenses["cont.noise_rv_ratio"] = ["cont", "mm"]

    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": args.symbol,
        "days": days,
        "n_event_mid": int(mid_ev.size),
        "n_dp": int(dp_mid_c.size),
        "roll_mid": roll_mid,
        "roll_px": roll_px,
        "ma1_mid": ma1_mid,
        "ma1_px": ma1_px,
        "ar3": {k: ar3[k] for k in ("ok", "n", "lags", "phi_at_1", "sigma_e", "r2") if k in ar3},
        "ar10": {k: ar10[k] for k in ("ok", "n", "lags", "phi_at_1", "sigma_e", "r2") if k in ar10},
        "rw_ar3": rw3,
        "rw_ar10": rw10,
        "rw_calendar_1s": rw_cal,
        "irf_h20_cum": irf.get("cum_q", [None])[-1] if irf.get("ok") else None,
        "quoted_spread_bps": qs,
        "noise_rv": noise,
        "noise_rv_bootstrap": {
            k: noise_boot[k]
            for k in (
                "noise_ratio",
                "ratio_ci95",
                "ratio_boot_mean",
                "n_blocks_used",
                "block_ratios",
                "ok",
            )
            if k in noise_boot
        },
        "time_split_sigma_w": {"train": rw_tr, "test": rw_te},
        "day_blocks_sigma_w": blocks,
        "decisions": decisions,
        "lenses": lenses,
        "falsifiers": {
            "cont.noise_rv_ratio": "CI lo≤1.2 / point≤1 — no fine-RV inflation on dense mid",
        },
    }

    (OUT / f"exp_ch09_{args.symbol.lower()}_summary.json").write_text(
        json.dumps(summary, indent=2, default=float)
    )

    report = [
        f"# Ch.9 estimation case — {args.symbol}",
        "",
        f"- n_event={mid_ev.size:,} · n_Δp={dp_mid_c.size:,} · days={days}",
        f"- Roll mid identified={bool(roll_mid.get('identified'))} "
        f"g1={roll_mid.get('g1')} · Roll px identified={bool(roll_px.get('identified'))}",
        f"- MA(1) mid identified={bool(ma1_mid.get('identified'))} "
        f"θ={ma1_mid.get('theta')} σ_w={ma1_mid.get('sigma_w')}",
        f"- MA(1) px identified={bool(ma1_px.get('identified'))} "
        f"θ={ma1_px.get('theta')} σ_w={ma1_px.get('sigma_w')}",
        f"- AR(10) φ(1)={ar10.get('phi_at_1')} σ_e={ar10.get('sigma_e')} "
        f"σ_w={rw10.get('sigma_w')} (train={rw_tr.get('sigma_w')}, test={rw_te.get('sigma_w')})",
        f"- Day-block σ_w mean±SE={blocks.get('mean')}±{blocks.get('se')} "
        f"(n_blocks={blocks.get('n_blocks')})",
        f"- Quoted spread bps={qs}",
        f"- Noise RV ratio={nr} · boot CI95={noise_boot.get('ratio_ci95')} "
        f"(n_blocks={noise_boot.get('n_blocks_used')})",
        "",
        "## Decisions",
    ]
    for k, v in decisions.items():
        report.append(f"- `{k}`: **{v}**")
    report.append("")
    (OUT / f"exp_ch09_{args.symbol.lower()}_REPORT.md").write_text("\n".join(report))
    (BOOK / "chapters" / "ch09_estimation" / "EXP_REPORT.md").write_text("\n".join(report))

    print("\n".join(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
