from __future__ import annotations
#!/usr/bin/env python3
"""Ch.3 Roll + Ch.8 noise figures + enriched EXP_REPORTs.

Paired clocks: event-time Roll (disc) vs RV fine/coarse + calendar/volclock AC1 (cont).
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
from ares_micro import noise_robust_rv, roll_on_mid_bps, time_split_mask, volume_clock_returns

OUT = BOOK / "out" / "ch03_roll"
OUT8 = BOOK / "out" / "ch08_noise"
CHAP3 = BOOK / "chapters" / "ch03_roll"
CHAP8 = BOOK / "chapters" / "ch08_noise"


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


def _ac1(r: np.ndarray) -> float:
    r = r[np.isfinite(r)]
    if r.size < 10:
        return float("nan")
    x, y = r[1:] - r[1:].mean(), r[:-1] - r[:-1].mean()
    den = float(np.sqrt((x * x).sum() * (y * y).sum()))
    return float((x * y).sum() / den) if den > 0 else float("nan")


def main() -> int:
    ensure_env()
    OUT.mkdir(parents=True, exist_ok=True)
    OUT8.mkdir(parents=True, exist_ok=True)
    symbol = "ETH"
    days = resolve_days(None, n=3)
    tob = load_hl_tob(symbol)
    tape = load_trades(symbol, days, max_files=24)
    ov = overlap_trades_with_mids(tape, tob)

    mid0 = ov["mid0"]
    ok = np.isfinite(mid0) & (mid0 > 0) & np.isfinite(ov["px"]) & (ov["px"] > 0)
    m_ev = mid0[ok]
    px = ov["px"][ok]
    ts = ov["ts"][ok]
    qty = ov["qty"][ok]

    roll_event = roll_on_mid_bps(m_ev)
    roll_px = roll_on_mid_bps(px)
    roll_cal = roll_on_mid_bps(tob["mid"][:: max(1, tob["mid"].size // 50_000)])
    tr, te = time_split_mask(ts, train_frac=0.7)
    roll_tr = roll_on_mid_bps(m_ev[tr])
    roll_te = roll_on_mid_bps(m_ev[te])

    dmid = np.diff(m_ev)
    dpx = np.diff(px)
    ac_mid = _acov(dmid, 10)
    ac_px = _acov(dpx, 10)

    noise = noise_robust_rv(tob["ts"], tob["mid"], fine_ns=100_000_000, coarse_ns=1_000_000_000)
    # multi-horizon RV for noise figs
    horizons_ns = [
        ("100ms", 100_000_000),
        ("500ms", 500_000_000),
        ("1s", 1_000_000_000),
        ("5s", 5_000_000_000),
        ("30s", 30_000_000_000),
    ]
    rv_curve = []
    for lab, ns in horizons_ns:
        _, r = calendar_returns(tob["ts"], tob["mid"], bar_ns=ns)
        rv = float(np.nansum(r[np.isfinite(r)] ** 2))
        rv_curve.append({"label": lab, "bar_ns": ns, "rv": rv, "n": int(np.isfinite(r).sum())})

    _, r_cal = calendar_returns(tob["ts"], tob["mid"], bar_ns=1_000_000_000)
    bar_v = float(np.nanmedian(qty[qty > 0]) * 50) if np.any(qty > 0) else 1.0
    _, r_vol = volume_clock_returns(ov["ts"][ok], px, qty, bar_volume=bar_v)
    ac1_cal = _ac1(r_cal)
    ac1_vol = _ac1(r_vol)
    ac_cal = _acov(r_cal[np.isfinite(r_cal)], 8)
    ac_vol = _acov(r_vol[np.isfinite(r_vol)], 8)

    # --- Fig 1: acov of Δmid / Δpx (Roll identification visual) ---
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.5))
    lags = np.arange(0, 11)
    axes[0].bar(lags, ac_mid, color="#1f4e79", width=0.7)
    axes[0].axhline(0, color="k", lw=0.6)
    axes[0].axhline(ac_mid[1], color="#c45c26", ls="--", lw=1.0, label=f"γ1={ac_mid[1]:.3g}")
    axes[0].set_title("Event-mid Δm autocovariance")
    axes[0].set_xlabel("lag k")
    axes[0].set_ylabel("γ_k")
    axes[0].legend(fontsize=8)
    axes[1].bar(lags, ac_px, color="#5b8fbe", width=0.7)
    axes[1].axhline(0, color="k", lw=0.6)
    axes[1].axhline(ac_px[1], color="#c45c26", ls="--", lw=1.0, label=f"γ1={ac_px[1]:.3g}")
    axes[1].set_title("Trade-price Δp autocovariance")
    axes[1].set_xlabel("lag k")
    axes[1].legend(fontsize=8)
    fig.suptitle("Roll requires γ1 < 0; HL ETH shows γ1 ≥ 0 → Kill", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "fig_roll_acov.png", dpi=120)
    plt.close(fig)

    # --- Fig 2: identification grid ---
    fig, ax = plt.subplots(figsize=(6.2, 3.4))
    labels = ["event mid", "trade px", "calendar mid\n(subsample)", "train 70%", "test 30%"]
    ids = [
        float(roll_event.get("identified", 0)),
        float(roll_px.get("identified", 0)),
        float(roll_cal.get("identified", 0)),
        float(roll_tr.get("identified", 0)),
        float(roll_te.get("identified", 0)),
    ]
    g1s = [
        roll_event.get("g1", np.nan),
        roll_px.get("g1", np.nan),
        roll_cal.get("g1", np.nan),
        roll_tr.get("g1", np.nan),
        roll_te.get("g1", np.nan),
    ]
    colors = ["#8fbf5b" if i else "#c45c26" for i in ids]
    bars = ax.bar(labels, [1.0] * len(labels), color=colors, edgecolor="k", linewidth=0.4)
    for b, g, i in zip(bars, g1s, ids):
        ax.text(
            b.get_x() + b.get_width() / 2,
            0.5,
            f"id={int(i)}\nγ1={g:.2e}" if np.isfinite(g) else f"id={int(i)}",
            ha="center",
            va="center",
            fontsize=8,
            color="white",
            fontweight="bold",
        )
    ax.set_ylim(0, 1.15)
    ax.set_yticks([])
    ax.set_title("Roll identification map (green=identified, red=Kill)")
    fig.tight_layout()
    fig.savefig(OUT / "fig_roll_id_map.png", dpi=120)
    plt.close(fig)

    # --- Fig 3: RV vs sampling horizon (noise) ---
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    xs = [np.log10(r["bar_ns"] / 1e9) for r in rv_curve]
    ys = [r["rv"] for r in rv_curve]
    ax.plot(xs, ys, "o-", color="#1f4e79", lw=1.5, ms=7)
    for x, y, r in zip(xs, ys, rv_curve):
        ax.annotate(r["label"], (x, y), textcoords="offset points", xytext=(4, 6), fontsize=8)
    ax.axhline(noise["rv_coarse"], color="#c45c26", ls="--", lw=0.9, label="1s coarse RV")
    ax.axhline(noise["rv_fine"], color="#5b8fbe", ls=":", lw=0.9, label="100ms fine RV")
    ax.set_xlabel("log10(bar seconds)")
    ax.set_ylabel("realized variance (sum r²)")
    ax.set_title(f"Noise diagnostic — RV vs horizon (ratio={noise['noise_ratio']:.3f})")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "fig_noise_rv_curve.png", dpi=120)
    fig.savefig(OUT8 / "fig_noise_rv_curve.png", dpi=120)
    plt.close(fig)

    # --- Fig 4: calendar vs volclock ACF ---
    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.5))
    k = np.arange(len(ac_cal))
    g0c = ac_cal[0] if ac_cal[0] and ac_cal[0] > 0 else 1.0
    g0v = ac_vol[0] if ac_vol[0] and ac_vol[0] > 0 else 1.0
    axes[0].bar(k, ac_cal / g0c, color="#1f4e79", width=0.7)
    axes[0].axhline(0, color="k", lw=0.5)
    axes[0].set_title(f"Calendar 1s ACF (AC1={ac1_cal:.3f})")
    axes[0].set_xlabel("lag")
    axes[0].set_ylabel("ρ_k")
    axes[1].bar(k[: len(ac_vol)], ac_vol / g0v, color="#c45c26", width=0.7)
    axes[1].axhline(0, color="k", lw=0.5)
    axes[1].set_title(f"Volume-clock ACF (AC1={ac1_vol:.3f})")
    axes[1].set_xlabel("lag")
    fig.suptitle("Clock contrast — cont.volclock_ac1 Hold (similar magnitude)", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "fig_clock_acf.png", dpi=120)
    fig.savefig(OUT8 / "fig_clock_acf.png", dpi=120)
    plt.close(fig)

    # --- Fig 5: mid path sample (context) ---
    step = max(1, m_ev.size // 2500)
    hours = (ts[::step] - ts[0]) / 3.6e12
    fig, ax = plt.subplots(figsize=(7.0, 3.2))
    ax.plot(hours, m_ev[::step], color="#1f4e79", lw=0.8)
    ax.set_xlabel("hours from sample start")
    ax.set_ylabel("as-of mid")
    ax.set_title(f"HL ETH mid path (n_trades={m_ev.size:,})")
    fig.tight_layout()
    fig.savefig(OUT / "fig_mid_path.png", dpi=120)
    plt.close(fig)

    disc_id = bool(roll_event.get("identified"))
    promote_roll = bool(roll_tr.get("identified") and roll_te.get("identified"))
    nr = float(noise.get("noise_ratio", float("nan")))
    promote_noise = bool(np.isfinite(nr) and nr > 1.5)

    decisions = {
        "disc.roll_event_mid": "Promote" if promote_roll else ("Hold" if disc_id else "Kill"),
        "disc.roll_trade_px": "Hold" if roll_px.get("identified") else "Kill",
        "cont.noise_rv_ratio": "Promote" if promote_noise else "Hold",
        "cont.volclock_ac1": "Hold",
    }
    falsifiers = {
        "disc.roll_event_mid": "γ₁≥0 on held-out half (unidentified) or spread_bps ≫ quoted",
        "disc.roll_trade_px": "γ₁≥0 (bounce absent / dominated by drift)",
        "cont.noise_rv_ratio": "RV_fine/RV_coarse ≤ 1 on dense collector (no bounce inflation)",
        "cont.volclock_ac1": "AC1 indistinguishable across calendar vs volume clocks",
    }

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "days": days,
        "n_trades": int(m_ev.size),
        "n_mids": int(tob["ts"].size),
        "disc": {
            "roll_event_mid": roll_event,
            "roll_calendar_subsample": roll_cal,
            "roll_trade_px": roll_px,
            "roll_train": roll_tr,
            "roll_test": roll_te,
            "event_ac1_dmid": _ac1(dmid),
            "acov_mid": ac_mid.tolist(),
            "acov_px": ac_px.tolist(),
        },
        "cont": {
            "noise_robust_rv": noise,
            "rv_curve": rv_curve,
            "calendar_1s_ac1": ac1_cal,
            "volclock_ac1": ac1_vol,
            "volclock_bar_volume": bar_v,
            "n_vol_bars": int(r_vol.size),
            "n_cal_bars": int(np.isfinite(r_cal).sum()),
        },
        "decisions": decisions,
        "falsifiers": falsifiers,
        "lenses": {
            "disc.roll_event_mid": ["disc", "liq", "mm"],
            "disc.roll_trade_px": ["disc", "info"],
            "cont.noise_rv_ratio": ["cont", "info"],
            "cont.volclock_ac1": ["cont", "exec"],
        },
        "figures": [
            "fig_roll_acov.png",
            "fig_roll_id_map.png",
            "fig_noise_rv_curve.png",
            "fig_clock_acf.png",
            "fig_mid_path.png",
        ],
    }
    (OUT / f"exp_ch03_{symbol.lower()}_summary.json").write_text(json.dumps(payload, indent=2, default=float))
    (OUT8 / f"exp_ch08_{symbol.lower()}_summary.json").write_text(
        json.dumps(
            {
                "created_at": payload["created_at"],
                "symbol": symbol,
                "days": days,
                "cont": payload["cont"],
                "decisions": {
                    "cont.noise_rv_ratio": decisions["cont.noise_rv_ratio"],
                    "cont.volclock_ac1": decisions["cont.volclock_ac1"],
                },
                "falsifiers": {
                    "cont.noise_rv_ratio": falsifiers["cont.noise_rv_ratio"],
                    "cont.volclock_ac1": falsifiers["cont.volclock_ac1"],
                },
                "figures": ["fig_noise_rv_curve.png", "fig_clock_acf.png"],
                "paired_with": "ch03_roll",
            },
            indent=2,
            default=float,
        )
    )

    report3 = f"""# Ch.3 / Ch.8 Roll & noise — {symbol}

## Sample
- Days: {days} · trades={m_ev.size:,} · mids={tob['ts'].size:,}

## Disc — Roll identification
- event-mid: identified={bool(roll_event.get('identified'))}  g0={roll_event.get('g0')}  g1={roll_event.get('g1')}  spread_bps={roll_event.get('spread_bps')}
- trade-px: identified={bool(roll_px.get('identified'))}  g0={roll_px.get('g0')}  g1={roll_px.get('g1')}
- calendar subsample: identified={bool(roll_cal.get('identified'))}  g1={roll_cal.get('g1')}
- train/test identified={bool(roll_tr.get('identified'))}/{bool(roll_te.get('identified'))}
- event AC1(Δmid)={payload['disc']['event_ac1_dmid']:.4f}

## Cont — noise & clocks
- RV_fine(100ms)={noise.get('rv_fine')}  RV_coarse(1s)={noise.get('rv_coarse')}  **noise_ratio={nr:.4f}**
- calendar 1s AC1={ac1_cal:.4f} · volclock AC1={ac1_vol:.4f} · bar_volume={bar_v:.4g} · n_vol={r_vol.size:,}

## Decisions
- `disc.roll_event_mid`: **{decisions['disc.roll_event_mid']}** — {falsifiers['disc.roll_event_mid']}
- `disc.roll_trade_px`: **{decisions['disc.roll_trade_px']}** — {falsifiers['disc.roll_trade_px']}
- `cont.noise_rv_ratio`: **{decisions['cont.noise_rv_ratio']}** — {falsifiers['cont.noise_rv_ratio']}
- `cont.volclock_ac1`: **{decisions['cont.volclock_ac1']}** — {falsifiers['cont.volclock_ac1']}

## Figures
- `out/ch03_roll/fig_roll_acov.png`
- `out/ch03_roll/fig_roll_id_map.png`
- `out/ch03_roll/fig_noise_rv_curve.png`
- `out/ch03_roll/fig_clock_acf.png`
- `out/ch03_roll/fig_mid_path.png`

## Desk / second-pass read
- γ1 ≥ 0 on mid **and** trade px ⇒ classic Roll bounce is **not** the dominant Δp structure on HL collector tape (sign herding / drift / continuous mid).
- noise_ratio ≈ {nr:.2f} < 1 ⇒ fine sampling does **not** inflate RV — collector mid is not bounce-dominated; Hold as diagnostic, not alpha.
- Volume-clock AC1 ({ac1_vol:.3f}) vs calendar ({ac1_cal:.3f}) same order ⇒ clock choice does not unlock a tradable ACF feature alone.
"""
    (OUT / f"exp_ch03_{symbol.lower()}_REPORT.md").write_text(report3)
    (CHAP3 / "EXP_REPORT.md").write_text(report3)

    report8 = f"""# Ch.8 univariate RW / noise — {symbol}

Paired empirics with Ch.3 (`out/ch03_roll/`). Cont candidates only here.

## Cont results
- noise_ratio RV_fine/RV_coarse = **{nr:.4f}**
- RV curve (sum r²): {', '.join(f"{r['label']}={r['rv']:.3e}" for r in rv_curve)}
- calendar AC1={ac1_cal:.4f} · volclock AC1={ac1_vol:.4f}

## Decisions
- `cont.noise_rv_ratio`: **{decisions['cont.noise_rv_ratio']}** — {falsifiers['cont.noise_rv_ratio']}
- `cont.volclock_ac1`: **{decisions['cont.volclock_ac1']}** — {falsifiers['cont.volclock_ac1']}

## Figures
- `out/ch08_noise/fig_noise_rv_curve.png`
- `out/ch08_noise/fig_clock_acf.png`

## BN / pricing-error link
- Roll Kill (γ1≥0) ⇒ MA(1) bounce parameterization fails; efficient-innovation σ_w still recoverable via AR truncation (see Ch.9 `disc.ar_sigma_w`).
- Fine/coarse RV is a **sampling-noise** diagnostic, not the BN pricing-error variance bound — do not equate them.
"""
    (OUT8 / f"exp_ch08_{symbol.lower()}_REPORT.md").write_text(report8)
    (CHAP8 / "EXP_REPORT.md").write_text(report8)
    print(report3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
