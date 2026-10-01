from __future__ import annotations
#!/usr/bin/env python3
"""Ch.17 discovery figures + enriched EXP_REPORT (IS, Epps, jump concordance)."""

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

from _data import align_mids_calendar, ensure_env, load_venue_tob  # noqa: E402
from research.lib import corr_vs_lag, hasbrouck_info_share_2  # noqa: E402

OUT = BOOK / "out" / "ch17_discovery"
CHAP = BOOK / "chapters" / "ch17_discovery"


def main() -> int:
    ensure_env()
    OUT.mkdir(parents=True, exist_ok=True)
    symbol = "ETH"
    bar_s = 1.0
    hl = load_venue_tob("hyperliquid", symbol)
    lit = load_venue_tob("lighter", symbol)
    bar_ns = int(bar_s * 1e9)
    ma, mb = align_mids_calendar(hl, lit, bar_ns=bar_ns)
    n_full = int(ma.size)
    if ma.size > 20_000:
        step = ma.size // 20_000
        ma_is, mb_is = ma[::step], mb[::step]
    else:
        ma_is, mb_is = ma, mb

    ishare = hasbrouck_info_share_2(ma_is, mb_is, lags=5)

    t0 = int(max(hl["ts"].min(), lit["ts"].min()))
    t1 = int(min(hl["ts"].max(), lit["ts"].max()))
    m_hl = (hl["ts"] >= t0) & (hl["ts"] <= t1)
    m_lit = (lit["ts"] >= t0) & (lit["ts"] <= t1)
    epps = corr_vs_lag(
        hl["ts"][m_hl],
        hl["mid"][m_hl],
        lit["ts"][m_lit],
        lit["mid"][m_lit],
        lags_s=(1.0, 5.0, 15.0, 60.0, 300.0),
    )
    curve = epps.get("curve") or []

    da = np.diff(np.log(ma))
    db = np.diff(np.log(mb))
    thr = np.nanquantile(np.abs(da), 0.9)
    big = np.abs(da) >= thr
    concord = float(np.mean(np.sign(da[big]) == np.sign(db[big]))) if big.sum() else float("nan")

    # lead-lag: for large HL moves, does Lit move same sign in next k bars?
    lead_rows = []
    for k in (0, 1, 2, 5, 10):
        if k == 0:
            c = concord
        else:
            # HL move at t, Lit cumulative sign over [t, t+k]
            if da.size <= k:
                c = float("nan")
            else:
                use = big[:-k] if k > 0 else big
                if use.sum() == 0:
                    c = float("nan")
                else:
                    lit_fwd = np.zeros(da.size - k)
                    for j in range(k):
                        lit_fwd += db[j : j + (da.size - k)]
                    c = float(
                        np.mean(np.sign(da[:-k][use]) == np.sign(lit_fwd[use]))
                    )
        lead_rows.append({"k_bars": k, "concord": c, "n_big": int(big.sum() if k == 0 else big[:-k].sum())})

    # basis series on full 1s align (subsample for plot)
    basis_bps = 1e4 * (ma - mb) / np.where(ma > 0, ma, np.nan)
    step_p = max(1, ma.size // 3000)
    hours = (np.arange(ma.size)[::step_p]) * bar_s / 3600.0

    # --- figures ---
    # Fig 1 Epps
    lags = [r["lag_s"] for r in curve]
    corrs = [r["corr"] for r in curve]
    ns = [r["n"] for r in curve]
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    ax.plot(lags, corrs, "o-", color="#1f4e79", lw=1.5, ms=6)
    for x, y, n in zip(lags, corrs, ns):
        if np.isfinite(y):
            ax.annotate(f"n={n}", (x, y), textcoords="offset points", xytext=(4, 6), fontsize=7)
    ax.set_xscale("log")
    ax.set_xlabel("sampling lag (s, log)")
    ax.set_ylabel("corr(Δlog mid HL, Δlog mid Lit)")
    ax.set_title("Epps effect — HL vs Lighter ETH mids")
    ax.set_ylim(-0.05, 1.05)
    ax.axhline(0.8, color="#c45c26", ls="--", lw=0.8, label="corr=0.8 hedge threshold")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "fig_epps_curve.png", dpi=120)
    plt.close(fig)

    # Fig 2 IS bounds
    fig, ax = plt.subplots(figsize=(6.0, 3.6))
    venues = ["HL", "Lighter"]
    lows = [ishare.get("is_a_low", np.nan), ishare.get("is_b_low", np.nan)]
    highs = [ishare.get("is_a_high", np.nan), ishare.get("is_b_high", np.nan)]
    mids_ = [0.5 * (lo + hi) for lo, hi in zip(lows, highs)]
    yerr = np.array([[m - lo, hi - m] for m, lo, hi in zip(mids_, lows, highs)]).T
    ax.bar(venues, mids_, yerr=yerr, color=["#1f4e79", "#5b8fbe"], capsize=6, alpha=0.85)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("information share")
    ax.set_title("Hasbrouck IS bounds (Cholesky orderings)")
    for i, (lo, hi) in enumerate(zip(lows, highs)):
        ax.text(i, hi + 0.03, f"[{lo:.2f},{hi:.2f}]", ha="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "fig_info_share_bounds.png", dpi=120)
    plt.close(fig)

    # Fig 3 basis + histogram
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.5))
    axes[0].plot(hours, basis_bps[::step_p], color="#1f4e79", lw=0.5)
    axes[0].axhline(0, color="k", lw=0.6)
    axes[0].set_xlabel("hours on 1s grid (subsampled)")
    axes[0].set_ylabel("basis (HL−Lit)/HL  bps")
    axes[0].set_title("Cross-venue mid basis")
    b_ok = basis_bps[np.isfinite(basis_bps)]
    axes[1].hist(b_ok, bins=50, color="#5b8fbe", edgecolor="k", linewidth=0.2)
    axes[1].axvline(np.median(b_ok), color="#c45c26", ls="--", label=f"median={np.median(b_ok):.3f}")
    axes[1].set_xlabel("basis bps")
    axes[1].set_title("Basis distribution")
    axes[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "fig_basis.png", dpi=120)
    plt.close(fig)

    # Fig 4 jump concordance + lead-lag
    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.5))
    # scatter of contemporaneous returns on big HL moves
    axes[0].scatter(da[big], db[big], s=8, alpha=0.35, c="#1f4e79", edgecolors="none")
    lim = float(np.nanpercentile(np.abs(da[big]), 99)) if big.sum() else 1e-4
    axes[0].plot([-lim, lim], [-lim, lim], "k--", lw=0.7)
    axes[0].set_xlabel("Δlog mid HL (p90 moves)")
    axes[0].set_ylabel("Δlog mid Lit (same 1s bar)")
    axes[0].set_title(f"Jump sign concordance={concord:.3f}")
    ks = [r["k_bars"] for r in lead_rows]
    cs = [r["concord"] for r in lead_rows]
    axes[1].plot(ks, cs, "o-", color="#c45c26", lw=1.5)
    axes[1].axhline(0.5, color="k", ls=":", lw=0.8, label="coin-flip")
    axes[1].set_xlabel("Lit forward window k (1s bars)")
    axes[1].set_ylabel("sign concordance")
    axes[1].set_title("Lead–lag vs IS companion (cond. on HL jump)")
    axes[1].set_ylim(0.4, 1.0)
    axes[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "fig_jump_leadlag.png", dpi=120)
    plt.close(fig)

    decisions = {
        "cont.info_share_hl_lit": "Promote" if ishare.get("ok") and np.isfinite(ishare.get("is_a_low", np.nan)) else "Hold",
        "cont.epps_xvenue": "Promote",
        "disc.jump_sign_concord": "Promote" if (np.isfinite(concord) and concord > 0.55) else "Hold",
    }
    falsifiers = {
        "cont.info_share_hl_lit": "IS bounds collapse to [0,1] noise or Ψ singular",
        "cont.epps_xvenue": "corr flat in lag (no Epps) on overlapping window",
        "disc.jump_sign_concord": "concordance ≈ 0.5 on large HL moves",
    }
    # Epps flat check
    if len(corrs) >= 2 and np.isfinite(corrs[0]) and np.isfinite(corrs[-1]):
        if abs(corrs[-1] - corrs[0]) < 0.05:
            decisions["cont.epps_xvenue"] = "Hold"

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "n_aligned": n_full,
        "n_is": int(ma_is.size),
        "bar_s": bar_s,
        "info_share": ishare,
        "epps": epps,
        "jump_sign_concord_p90": concord,
        "lead_lag_concord": lead_rows,
        "basis_bps": {
            "median": float(np.median(b_ok)) if b_ok.size else float("nan"),
            "mean": float(np.mean(b_ok)) if b_ok.size else float("nan"),
            "std": float(np.std(b_ok)) if b_ok.size else float("nan"),
            "p05": float(np.percentile(b_ok, 5)) if b_ok.size else float("nan"),
            "p95": float(np.percentile(b_ok, 95)) if b_ok.size else float("nan"),
        },
        "decisions": decisions,
        "falsifiers": falsifiers,
        "lenses": {
            "cont.info_share_hl_lit": ["cont", "info", "exec"],
            "cont.epps_xvenue": ["cont", "info", "exec"],
            "disc.jump_sign_concord": ["disc", "info"],
        },
        "figures": [
            "fig_epps_curve.png",
            "fig_info_share_bounds.png",
            "fig_basis.png",
            "fig_jump_leadlag.png",
        ],
        "caveats": [
            "IS via differenced VAR + Cholesky bounds — not full Johansen VECM",
            "Collector TOB clocks ≠ matching-engine time; ordinal research use",
            "Lighter is another electronic perp venue, not equity 'lit vs dark'",
            "Lead-lag concordance ≠ information share; wide IS bounds when Omega nondiagonal",
        ],
    }
    (OUT / f"exp_ch17_{symbol.lower()}_summary.json").write_text(json.dumps(payload, indent=2))

    epps_lines = "\n".join(
        f"  - lag={r['lag_s']}s  corr={r['corr']:.4f}  n={r['n']}" for r in curve
    )
    lead_lines = "\n".join(
        f"  - k={r['k_bars']}: concord={r['concord']:.4f}  n_big={r['n_big']}" for r in lead_rows
    )
    report = f"""# Ch.17 price discovery — {symbol}

## Sample
- Aligned 1s mids n={n_full:,} (IS subsample n={ma_is.size:,})
- Overlap window mutual HL∩Lit TOB

## Information share (Hasbrouck bounds)
- HL: [{ishare.get('is_a_low')}, {ishare.get('is_a_high')}]
- Lit: [{ishare.get('is_b_low')}, {ishare.get('is_b_high')}]
- ordering_ab: {ishare.get('ordering_ab')}
- ordering_ba: {ishare.get('ordering_ba')}
- ok={ishare.get('ok')} lags={ishare.get('lags')}

## Epps curve
{epps_lines}

## Jump / lead–lag
- Contemporaneous sign concordance (p90 HL |Δm|): {concord:.4f}
{lead_lines}

## Basis (HL−Lit)/HL bps
- median={payload['basis_bps']['median']:.4f}  mean={payload['basis_bps']['mean']:.4f}  std={payload['basis_bps']['std']:.4f}
- p05={payload['basis_bps']['p05']:.4f}  p95={payload['basis_bps']['p95']:.4f}

## Decisions
- `cont.info_share_hl_lit`: **{decisions['cont.info_share_hl_lit']}** — {falsifiers['cont.info_share_hl_lit']}
- `cont.epps_xvenue`: **{decisions['cont.epps_xvenue']}** — {falsifiers['cont.epps_xvenue']}
- `disc.jump_sign_concord`: **{decisions['disc.jump_sign_concord']}** — {falsifiers['disc.jump_sign_concord']}

## Figures
- `out/ch17_discovery/fig_epps_curve.png`
- `out/ch17_discovery/fig_info_share_bounds.png`
- `out/ch17_discovery/fig_basis.png`
- `out/ch17_discovery/fig_jump_leadlag.png`

## Desk / second-pass read
- Rising Epps corr with lag ⇒ asynchronicity; use lag where corr≳0.8 as sync horizon for hedges.
- Wide IS bounds ⇒ residual correlation; report interval, not a point weight for SOR.
- Lead–lag concordance climbing in k means Lit catches HL jumps within a few seconds — complementary to IS, not a substitute.
- HL vs Lit here ≠ equity lit/dark; both are continuous LOB perps with collector-clock mids.
"""
    (OUT / f"exp_ch17_{symbol.lower()}_REPORT.md").write_text(report)
    (CHAP / "EXP_REPORT.md").write_text(report)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
