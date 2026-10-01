from __future__ import annotations
#!/usr/bin/env python3
"""Ch.9 estimation figures + BN/variance-ratio second pass on HL tape.

Enriches out/ch09_estimation and chapters/ch09_estimation/EXP_REPORT.md.
No ClickHouse MCP.
"""

import os

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
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
from research.lib.continuous import calendar_returns, noise_robust_rv  # noqa: E402
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
CHAP = BOOK / "chapters" / "ch09_estimation"


def _log_returns(px: np.ndarray) -> np.ndarray:
    p = np.asarray(px, dtype=np.float64)
    p = p[np.isfinite(p) & (p > 0)]
    if p.size < 3:
        return np.zeros(0, dtype=np.float64)
    return np.diff(np.log(p))


def _acov(r: np.ndarray, nlags: int = 10) -> np.ndarray:
    r = r[np.isfinite(r)]
    r = r - r.mean()
    n = r.size
    out = np.empty(nlags + 1, dtype=np.float64)
    for k in range(nlags + 1):
        if n - k < 2:
            out[k] = np.nan
        else:
            out[k] = float(np.dot(r[k:], r[: n - k]) / n)
    return out


def _variance_ratios(r: np.ndarray, horizons: list[int]) -> list[dict]:
    """Lo–MacKinlay style VR(q) = Var(q-period sum) / (q Var(1-period))."""
    r = r[np.isfinite(r)]
    if r.size < max(horizons) * 5:
        return []
    v1 = float(np.var(r, ddof=1))
    rows = []
    for q in horizons:
        if q < 1 or r.size < q + 10:
            continue
        # overlapping q-sums
        s = np.convolve(r, np.ones(q), mode="valid")
        vq = float(np.var(s, ddof=1))
        vr = vq / (q * v1) if v1 > 0 else float("nan")
        rows.append({"q": q, "vr": vr, "var_q": vq, "n": int(s.size)})
    return rows


def _block_sigma_w(dp: np.ndarray, ts: np.ndarray, *, lags: int = 10) -> dict:
    t = np.asarray(ts, dtype=np.int64)
    if t.size == dp.size + 1:
        t = t[1:]
    elif t.size != dp.size:
        t = t[: dp.size]
    day = t // 86_400_000_000_000
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
    ensure_env()
    OUT.mkdir(parents=True, exist_ok=True)
    symbol = "ETH"
    days = resolve_days(None, n=3)
    tob = load_hl_tob(symbol)
    tape = load_trades(symbol, days, max_files=24)
    ov = overlap_trades_with_mids(tape, tob)

    mid0 = ov["mid0"]
    ok = np.isfinite(mid0) & (mid0 > 0) & np.isfinite(ov["px"]) & (ov["px"] > 0)
    mid_ev = mid0[ok]
    px_ev = ov["px"][ok]
    ts_ev = ov["ts"][ok]

    dp_mid = _log_returns(mid_ev)
    dp_px = _log_returns(px_ev)
    gaps = np.diff(ts_ev)
    keep = np.ones(dp_mid.size, dtype=bool)
    if gaps.size >= dp_mid.size:
        keep[1:] = gaps[1:dp_mid.size] < 3_600_000_000_000
    elif gaps.size == dp_mid.size:
        keep = gaps < 3_600_000_000_000
    dp_mid_c = dp_mid[keep]
    dp_px_c = dp_px[keep]
    ts_dp = ts_ev[1 : 1 + dp_mid.size][keep]

    roll_mid = roll_on_mid_bps(mid_ev)
    roll_px = roll_on_mid_bps(px_ev)
    ma1_mid = ma1_from_acov(dp_mid_c)
    ma1_px = ma1_from_acov(dp_px_c)
    ar3 = ar_ols(dp_mid_c, lags=3)
    ar10 = ar_ols(dp_mid_c, lags=10)
    rw3 = rw_variance_from_ar(ar3)
    rw10 = rw_variance_from_ar(ar10)
    irf = impact_multipliers_from_ar(ar10, horizon=20)

    qs_arr = quoted_spread_bps(tob["bid"], tob["ask"], mid=tob["mid"])
    qs = bootstrap_ci(qs_arr, n_boot=300, seed=55)
    noise = noise_robust_rv(tob["ts"], tob["mid"])
    _, r_cal = calendar_returns(tob["ts"], tob["mid"], bar_ns=1_000_000_000)
    r_cal_f = r_cal[np.isfinite(r_cal)]
    ar_cal = ar_ols(r_cal_f, lags=10)
    rw_cal = rw_variance_from_ar(ar_cal)

    tr, te = time_split_mask(ts_dp, train_frac=0.7)
    rw_tr = rw_variance_from_ar(ar_ols(dp_mid_c[tr], lags=10))
    rw_te = rw_variance_from_ar(ar_ols(dp_mid_c[te], lags=10))
    blocks = _block_sigma_w(dp_mid_c, ts_dp, lags=10)

    ac_mid = _acov(dp_mid_c, 12)
    vr_event = _variance_ratios(dp_mid_c, [1, 2, 5, 10, 20, 50, 100])
    vr_cal = _variance_ratios(r_cal_f, [1, 2, 5, 10, 30, 60])

    # lag sweep for BN σ_w sensitivity
    lag_sweep = []
    for k in (1, 2, 3, 5, 10, 15, 20, 30):
        ar = ar_ols(dp_mid_c, lags=k)
        rw = rw_variance_from_ar(ar)
        lag_sweep.append(
            {
                "lags": k,
                "phi_at_1": ar.get("phi_at_1"),
                "sigma_w": rw.get("sigma_w"),
                "sigma_e": ar.get("sigma_e"),
                "r2": ar.get("r2"),
            }
        )

    # --- Fig 1: return ACF ---
    fig, ax = plt.subplots(figsize=(6.5, 3.5))
    lags = np.arange(len(ac_mid))
    g0 = ac_mid[0] if ac_mid[0] > 0 else 1.0
    ax.bar(lags, ac_mid / g0, color="#1f4e79", width=0.7)
    ax.axhline(0, color="k", lw=0.5)
    ax.set_xlabel("lag k (event)")
    ax.set_ylabel("ρ_k (Δlog mid)")
    ax.set_title("Event Δlog mid ACF — MA/AR input (Roll levels Kill)")
    fig.tight_layout()
    fig.savefig(OUT / "fig_return_acf.png", dpi=120)
    plt.close(fig)

    # --- Fig 2: σ_w comparison ---
    fig, ax = plt.subplots(figsize=(6.8, 3.6))
    names = ["MA(1) mid", "MA(1) px", "AR(3)", "AR(10)", "AR(10)\ncalendar 1s", "day-block\nmean"]
    vals = [
        ma1_mid.get("sigma_w", np.nan),
        ma1_px.get("sigma_w", np.nan),
        rw3.get("sigma_w", np.nan),
        rw10.get("sigma_w", np.nan),
        rw_cal.get("sigma_w", np.nan),
        blocks.get("mean", np.nan),
    ]
    colors = ["#1f4e79", "#5b8fbe", "#8fbf5b", "#c45c26", "#7a5c3c", "#555555"]
    ax.bar(names, vals, color=colors)
    ax.set_ylabel("σ_w (log-return units)")
    ax.set_title("Beveridge–Nelson / MA efficient-innovation scale")
    for i, v in enumerate(vals):
        if np.isfinite(v):
            ax.text(i, v * 1.01, f"{v:.2e}", ha="center", fontsize=7)
    fig.tight_layout()
    fig.savefig(OUT / "fig_sigma_w_compare.png", dpi=120)
    plt.close(fig)

    # --- Fig 3: IRF / impact multipliers ---
    fig, ax = plt.subplots(figsize=(6.5, 3.5))
    if irf.get("ok"):
        cum = np.asarray(irf.get("cum_q") or [], dtype=np.float64)
        ax.plot(np.arange(len(cum)), cum, "o-", color="#1f4e79", lw=1.4, ms=4)
        ax.axhline(1.0, color="k", ls=":", lw=0.7)
        ax.set_xlabel("horizon h")
        ax.set_ylabel("cumulative MA multiplier")
        ax.set_title(f"AR(10)→MA impact multipliers (cum@20={cum[-1]:.3f})")
    else:
        ax.text(0.5, 0.5, "IRF unavailable", ha="center", transform=ax.transAxes)
    fig.tight_layout()
    fig.savefig(OUT / "fig_ar_irf.png", dpi=120)
    plt.close(fig)

    # --- Fig 4: variance ratios ---
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.5))
    if vr_event:
        axes[0].plot([r["q"] for r in vr_event], [r["vr"] for r in vr_event], "o-", color="#1f4e79")
        axes[0].axhline(1.0, color="k", ls="--", lw=0.8)
        axes[0].set_xscale("log")
        axes[0].set_xlabel("horizon q (events)")
        axes[0].set_ylabel("VR(q)")
        axes[0].set_title("Event-time variance ratio")
    if vr_cal:
        axes[1].plot([r["q"] for r in vr_cal], [r["vr"] for r in vr_cal], "o-", color="#c45c26")
        axes[1].axhline(1.0, color="k", ls="--", lw=0.8)
        axes[1].set_xscale("log")
        axes[1].set_xlabel("horizon q (1s bars)")
        axes[1].set_ylabel("VR(q)")
        axes[1].set_title("Calendar 1s variance ratio")
    fig.suptitle("VR≠1 ⇒ MA structure / pitfalls for naive RW scaling", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "fig_variance_ratio.png", dpi=120)
    plt.close(fig)

    # --- Fig 5: lag truncation sensitivity ---
    fig, ax = plt.subplots(figsize=(6.5, 3.5))
    ax.plot(
        [r["lags"] for r in lag_sweep],
        [r["sigma_w"] for r in lag_sweep],
        "o-",
        color="#1f4e79",
        label="σ_w",
    )
    ax.set_xlabel("AR lag truncation K")
    ax.set_ylabel("σ_w")
    ax.set_title("BN σ_w vs AR truncation (estimation pitfall)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "fig_ar_lag_sweep.png", dpi=120)
    plt.close(fig)

    # decisions (same logic as exp_ch09)
    decisions = {}
    lenses = {}
    ma_ok = bool(ma1_mid.get("identified"))
    decisions["disc.ma1_moments"] = (
        "Promote" if ma_ok and ma1_mid.get("sigma_w", 0) > 0 else ("Hold" if ma_ok else "Kill")
    )
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
    decisions["disc.roll_vs_quote"] = "Kill" if not roll_mid.get("identified") else "Hold"
    lenses["disc.roll_vs_quote"] = ["disc", "liq"]
    nr = noise.get("noise_ratio", float("nan"))
    decisions["cont.noise_rv_ratio"] = (
        "Hold" if np.isfinite(nr) and 0.5 < nr < 2.0 else ("Promote" if np.isfinite(nr) else "Kill")
    )
    lenses["cont.noise_rv_ratio"] = ["cont", "mm"]

    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
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
        "time_split_sigma_w": {"train": rw_tr, "test": rw_te},
        "day_blocks_sigma_w": blocks,
        "variance_ratio_event": vr_event,
        "variance_ratio_calendar": vr_cal,
        "ar_lag_sweep": lag_sweep,
        "decisions": decisions,
        "lenses": lenses,
        "figures": [
            "fig_return_acf.png",
            "fig_sigma_w_compare.png",
            "fig_ar_irf.png",
            "fig_variance_ratio.png",
            "fig_ar_lag_sweep.png",
        ],
        "second_pass": {
            "bn_note": "σ_w from φ(1) only; full MA optional",
            "vr_note": "VR(q)≠1 on event and calendar — do not scale RW var linearly in horizon",
            "pitfalls": [
                "Roll on levels Kill while MA(1) on log-returns can still identify",
                "AR truncation K moves σ_w — report lag sweep / day-block SE",
                "Delta-method SEs poor for nonlinear RW maps — prefer day blocks",
                "Do not glue large gaps into Δp (1h filter applied)",
            ],
        },
    }
    (OUT / f"exp_ch09_{symbol.lower()}_summary.json").write_text(
        json.dumps(summary, indent=2, default=float)
    )

    vr_e_lines = "\n".join(f"  - q={r['q']}: VR={r['vr']:.4f}  n={r['n']}" for r in vr_event)
    vr_c_lines = "\n".join(f"  - q={r['q']}: VR={r['vr']:.4f}  n={r['n']}" for r in vr_cal)
    sweep_line = ", ".join(
        f"K={r['lags']}:{r['sigma_w']:.3e}" for r in lag_sweep if np.isfinite(r.get("sigma_w", np.nan))
    )
    report = f"""# Ch.9 estimation case — {symbol}

## Sample
- n_event={mid_ev.size:,} · n_Δp={dp_mid_c.size:,} · days={days}

## Roll vs MA/AR
- Roll mid identified={bool(roll_mid.get('identified'))} g1={roll_mid.get('g1')} · Roll px identified={bool(roll_px.get('identified'))}
- MA(1) mid identified={bool(ma1_mid.get('identified'))} θ={ma1_mid.get('theta')} σ_w={ma1_mid.get('sigma_w')} σ_s={ma1_mid.get('sigma_s')}
- MA(1) px identified={bool(ma1_px.get('identified'))} θ={ma1_px.get('theta')} σ_w={ma1_px.get('sigma_w')}
- AR(3) φ(1)={ar3.get('phi_at_1')} σ_w={rw3.get('sigma_w')}
- AR(10) φ(1)={ar10.get('phi_at_1')} σ_e={ar10.get('sigma_e')} σ_w={rw10.get('sigma_w')} (train={rw_tr.get('sigma_w')}, test={rw_te.get('sigma_w')})
- Day-block σ_w mean±SE={blocks.get('mean')}±{blocks.get('se')} (n_blocks={blocks.get('n_blocks')})
- Calendar 1s AR(10) σ_w={rw_cal.get('sigma_w')}
- IRF cum@20={summary['irf_h20_cum']}
- Quoted spread bps point={qs.get('point')} CI=[{qs.get('lo')}, {qs.get('hi')}]
- Noise RV ratio={noise.get('noise_ratio')}

## Variance ratios (second pass)
### Event Δlog mid
{vr_e_lines}
### Calendar 1s
{vr_c_lines}

## AR lag sweep σ_w
- {sweep_line}

## Decisions
- `disc.ma1_moments`: **{decisions['disc.ma1_moments']}**
- `disc.ar_sigma_w`: **{decisions['disc.ar_sigma_w']}**
- `disc.roll_vs_quote`: **{decisions['disc.roll_vs_quote']}**
- `cont.noise_rv_ratio`: **{decisions['cont.noise_rv_ratio']}**

## Figures
- `out/ch09_estimation/fig_return_acf.png`
- `out/ch09_estimation/fig_sigma_w_compare.png`
- `out/ch09_estimation/fig_ar_irf.png`
- `out/ch09_estimation/fig_variance_ratio.png`
- `out/ch09_estimation/fig_ar_lag_sweep.png`

## Desk / second-pass read
- BN σ_w is the permanent-vol prior when Roll Kill; prefer AR(10) + day-block SE over delta-method.
- VR(q)≠1 ⇒ naive √T scaling of event variance is wrong for TCA / risk — use MA/AR structure.
- Lag truncation moves σ_w; publish the sweep, not a single K.
- Ch.4 toolkit (MA↔AR invertibility, φ(1) only for σ_w) is the estimation hygiene for this chapter.
"""
    (OUT / f"exp_ch09_{symbol.lower()}_REPORT.md").write_text(report)
    (CHAP / "EXP_REPORT.md").write_text(report)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
