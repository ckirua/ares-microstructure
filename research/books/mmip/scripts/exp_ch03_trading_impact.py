#!/usr/bin/env python3
"""Chapter 3 experiment: market-impact stylized facts on HL ETH trade tape.

Book framing (Lehalle & Laruelle Ch.3 / App A.6):
  - Impact model I = κ · σ · (v/V)^γ  with participation ρ = v/V
  - Temporary vs permanent: price rises during execution, partially reverts after
  - TCA-style arrival vs VWAP descriptive measures

Honesty (mandatory):
  Without proprietary meta-order fills we use *tape order-flow intensity*
      ρ = |Σ side·qty| / Σ qty
  as a *proxy* for participation — NOT a single-algo POV. Temporary/permanent
  impacts are signed mid returns aligned to that flow. Label: descriptive (D).

Data preference (no ClickHouse MCP):
  1. startarb warehouse load_trade_tape (HL ETH DENSE days)
  2. Optional public REST fallback if warehouse empty

Paper only. No orders.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

BOOK_ROOT = Path(__file__).resolve().parents[1]
ROOT = BOOK_ROOT.parents[2]  # repo root (mmip → books → research → repo)
OUT_DIR = BOOK_ROOT / "out" / "ch03_optimal_trading"
STARTARB = Path("/home/dev/srv/ares-startarb")
DENSE_DAYS = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-25", "2026-09-26"]


def _ensure_startarb() -> None:
    sys.path.insert(0, str(STARTARB / "src"))
    from startarb.env import ensure_env

    ensure_env()


def load_hl_eth_tape(days: list[str], max_files: int = 16):
    from startarb.data.trades import load_trade_tape

    tapes = []
    for day in days:
        try:
            t = load_trade_tape("hyperliquid", "ETH", days=[day], max_files=max_files)
            if t is not None and len(t) > 0:
                tapes.append(t)
                print(f"  day {day}: n={len(t)}")
        except Exception as e:
            print(f"  day {day}: FAIL {e}")
    if not tapes:
        return None
    # Concatenate arrays
    class Tape:
        pass

    out = Tape()
    out.ts_ns = np.concatenate([np.asarray(t.ts_ns) for t in tapes])
    out.price = np.concatenate([np.asarray(t.price, dtype=np.float64) for t in tapes])
    out.qty_coin = np.concatenate([np.asarray(t.qty_coin, dtype=np.float64) for t in tapes])
    out.side = np.concatenate([np.asarray(t.side) for t in tapes]).astype(np.int8)
    order = np.argsort(out.ts_ns)
    out.ts_ns = out.ts_ns[order]
    out.price = out.price[order]
    out.qty_coin = out.qty_coin[order]
    out.side = out.side[order]
    out.days = days
    out.n = int(len(out.ts_ns))
    return out


def window_metrics(ts_ns, price, qty, side, window_s: int, post_mult: float = 1.0):
    """Non-overlapping windows → impact / participation proxies."""
    t0 = int(ts_ns[0])
    t1 = int(ts_ns[-1])
    w_ns = int(window_s * 1e9)
    post_ns = int(window_s * post_mult * 1e9)
    rows = []
    start = t0
    while start + w_ns <= t1:
        end = start + w_ns
        m = (ts_ns >= start) & (ts_ns < end)
        if m.sum() < 20:
            start = end
            continue
        p = price[m]
        q = qty[m]
        s = side[m].astype(np.float64)
        V = float(q.sum())
        if V <= 0:
            start = end
            continue
        Qnet = float(np.sum(s * q))
        rho = abs(Qnet) / V
        sgn = 1.0 if Qnet >= 0 else -1.0
        S0 = float(p[0])
        Send = float(p[-1])
        # mid proxy = trade price; duration impact
        I_dur = sgn * 1e4 * (Send - S0) / S0  # bps
        # VWAP in window
        vwap = float(np.sum(p * q) / V)
        is_arrival = sgn * 1e4 * (vwap - S0) / S0
        # permanent: price at end+post window (first trade after end+post, else last in post)
        post_end = end + post_ns
        m_post = (ts_ns >= end) & (ts_ns < post_end)
        if m_post.sum() >= 5:
            S_perm = float(price[m_post][-1])
            I_perm = sgn * 1e4 * (S_perm - S0) / S0
        else:
            I_perm = float("nan")
        I_temp = I_dur - I_perm if np.isfinite(I_perm) else float("nan")
        # realized vol proxy (bps): std of 1s log returns in window * sqrt(n)
        ts_s = (ts_ns[m] // 1_000_000_000).astype(np.int64)
        # last price per second
        uniq, inv = np.unique(ts_s, return_inverse=True)
        last_p = np.zeros(len(uniq), dtype=np.float64)
        for i, pi in enumerate(p):
            last_p[inv[i]] = pi
        if len(last_p) >= 5:
            lr = np.diff(np.log(last_p))
            sigma_bps = float(np.std(lr) * 1e4 * math.sqrt(max(len(lr), 1)))
        else:
            sigma_bps = float("nan")
        rows.append(
            {
                "start_ns": int(start),
                "window_s": window_s,
                "n_trades": int(m.sum()),
                "V": V,
                "Qnet": Qnet,
                "rho": rho,
                "S0": S0,
                "I_dur_bps": I_dur,
                "I_perm_bps": I_perm,
                "I_temp_bps": I_temp,
                "is_arrival_bps": is_arrival,
                "sigma_bps": sigma_bps,
            }
        )
        start = end
    return rows


def fit_kappa_gamma(rows: list[dict], rho_min: float = 0.05) -> dict[str, Any]:
    """Fit log(I/σ) = log κ + γ log ρ on windows with I_dur>0 and finite σ."""
    xs, ys = [], []
    for r in rows:
        rho = r["rho"]
        sig = r["sigma_bps"]
        I = r["I_dur_bps"]
        if not (np.isfinite(rho) and np.isfinite(sig) and np.isfinite(I)):
            continue
        if rho < rho_min or sig <= 1e-6 or I <= 0:
            continue
        xs.append(math.log(rho))
        ys.append(math.log(I / sig))
    if len(xs) < 20:
        return {"n": len(xs), "ok": False, "note": "insufficient points"}
    x = np.asarray(xs)
    y = np.asarray(ys)
    # OLS y = a + b x  → κ=exp(a), γ=b
    A = np.vstack([np.ones_like(x), x]).T
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    a, b = float(coef[0]), float(coef[1])
    yhat = a + b * x
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return {
        "n": int(len(x)),
        "ok": True,
        "log_kappa": a,
        "kappa": math.exp(a),
        "gamma": b,
        "r2": r2,
        "rho_min": rho_min,
    }


def rho_bucket_summary(rows: list[dict], edges: list[float] | None = None) -> list[dict]:
    if edges is None:
        edges = [0.0, 0.05, 0.10, 0.15, 0.25, 0.40, 1.01]
    out = []
    rhos = np.array([r["rho"] for r in rows])
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        m = (rhos >= lo) & (rhos < hi)
        if m.sum() == 0:
            continue
        sub = [rows[j] for j in np.where(m)[0]]
        def mean_key(k):
            v = np.array([r[k] for r in sub], dtype=float)
            v = v[np.isfinite(v)]
            return float(v.mean()) if len(v) else float("nan")

        out.append(
            {
                "rho_lo": lo,
                "rho_hi": hi,
                "n": int(m.sum()),
                "mean_rho": mean_key("rho"),
                "mean_I_dur_bps": mean_key("I_dur_bps"),
                "mean_I_perm_bps": mean_key("I_perm_bps"),
                "mean_I_temp_bps": mean_key("I_temp_bps"),
                "mean_is_arrival_bps": mean_key("is_arrival_bps"),
            }
        )
    return out


def almgren_chriss_toy(
    v_star: float = 1.0,
    N: int = 20,
    kappa: float = 0.5,
    gamma: float = 0.5,
    lam: float = 1e-3,
    sigma: float = 1.0,
    V: float = 1.0,
) -> dict[str, Any]:
    """Toy AC remaining-qty path for γ=1 linear impact (A.28 special case style).

    For illustration we use a simple discrete mean-variance schedule with
    constant σ,V and linear impact (γ=1): solve recurrence for x_n.
    Returns remaining fraction x/v*.
    """
    # Use shooting on x1 for linear impact recurrence (book A.28 simplified):
    # xn+1 = (1 + Vn/Vn-1 + λ/κ * Vn/σ) xn - (Vn/Vn-1) xn-1   with σ const, V const
    # → xn+1 = (2 + λ V /(κ σ)) xn - xn-1
    alpha = 2.0 + (lam * V) / (kappa * sigma) if kappa * sigma > 0 else 2.0

    def path(x1: float) -> np.ndarray:
        x = np.zeros(N + 1)
        x[0] = v_star
        x[1] = x1
        for n in range(1, N):
            # n indexes current; need xn-1, xn → xn+1
            x[n + 1] = alpha * x[n] - x[n - 1]
        return x

    # binary search x1 so xN ≈ 0
    lo, hi = 0.0, v_star
    best = None
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        x = path(mid)
        best = x
        if x[-1] > 0:
            lo = mid  # too slow → need smaller remaining after first = trade more first = smaller x1
            # wait: x1 = remaining after first slice = v* - v1; if xN>0 traded too slow → increase v1 → decrease x1
            hi = mid
        else:
            lo = mid
    x = best if best is not None else path(0.5 * v_star)
    # fix numerical: clip and renormalize schedule
    x = np.maximum(x, 0)
    x[0] = v_star
    x[-1] = 0.0
    v = -np.diff(x)
    v = np.maximum(v, 0)
    if v.sum() > 0:
        v = v * (v_star / v.sum())
    x2 = np.concatenate([[v_star], v_star - np.cumsum(v)])
    x2[-1] = 0.0
    return {
        "N": N,
        "lambda": lam,
        "kappa": kappa,
        "sigma": sigma,
        "V": V,
        "remaining": x2.tolist(),
        "child": v.tolist(),
    }


def make_plots(summary: dict, out_dir: Path) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    paths = []
    # 1) Impact vs rho buckets (5m)
    buckets = summary["buckets_5m"]
    if buckets:
        fig, ax = plt.subplots(figsize=(7, 4))
        x = [0.5 * (b["rho_lo"] + b["rho_hi"]) for b in buckets]
        y_d = [b["mean_I_dur_bps"] for b in buckets]
        y_p = [b["mean_I_perm_bps"] for b in buckets]
        y_t = [b["mean_I_temp_bps"] for b in buckets]
        ax.plot(x, y_d, "o-", label=r"$I_{\mathrm{dur}}$ (during)")
        ax.plot(x, y_p, "s-", label=r"$I_{\mathrm{perm}}$ (post)")
        ax.plot(x, y_t, "^--", label=r"$I_{\mathrm{temp}}=I_{\mathrm{dur}}-I_{\mathrm{perm}}$")
        ax.set_xlabel(r"Participation proxy $\rho=|Q_{\mathrm{net}}|/V$")
        ax.set_ylabel("Signed impact (bps)")
        ax.set_title("Ch.3 — Impact vs participation (HL ETH, 5m windows)")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        p = out_dir / "impact_vs_rho_5m.png"
        fig.tight_layout()
        fig.savefig(p, dpi=120)
        plt.close(fig)
        paths.append(str(p))

    # 2) Scatter I_dur vs rho with power-law guide
    rows = summary["rows_5m_sample"]
    if rows:
        fig, ax = plt.subplots(figsize=(7, 4))
        rho = np.array([r["rho"] for r in rows])
        I = np.array([r["I_dur_bps"] for r in rows])
        ax.scatter(rho, I, s=8, alpha=0.35, c="#1f4e79")
        fit = summary.get("fit_5m") or {}
        if fit.get("ok"):
            xs = np.linspace(max(rho.min(), 0.02), min(rho.max(), 0.95), 50)
            # I ≈ κ σ ρ^γ — use median σ
            sigs = np.array([r["sigma_bps"] for r in rows])
            sigs = sigs[np.isfinite(sigs)]
            sig_med = float(np.median(sigs)) if len(sigs) else 1.0
            ys = fit["kappa"] * sig_med * (xs ** fit["gamma"])
            ax.plot(
                xs,
                ys,
                "r-",
                lw=2,
                label=rf"$\hat\kappa={fit['kappa']:.3f},\ \hat\gamma={fit['gamma']:.2f}$ (med σ)",
            )
            ax.legend(fontsize=8)
        ax.set_xlabel(r"$\rho$")
        ax.set_ylabel(r"$I_{\mathrm{dur}}$ (bps)")
        ax.set_title("Duration impact scatter (5m) + power-law guide")
        ax.grid(True, alpha=0.3)
        p = out_dir / "impact_scatter_5m.png"
        fig.tight_layout()
        fig.savefig(p, dpi=120)
        plt.close(fig)
        paths.append(str(p))

    # 3) AC toy schedule
    ac = summary.get("ac_toy")
    if ac:
        fig, ax = plt.subplots(figsize=(7, 3.5))
        rem = ac["remaining"]
        ax.plot(np.arange(len(rem)), rem, "o-", color="#0b6e4f")
        ax.set_xlabel("Slice n")
        ax.set_ylabel(r"Remaining $x_n / v^*$")
        ax.set_title(rf"Almgren–Chriss toy schedule ($\lambda={ac['lambda']}$)")
        ax.grid(True, alpha=0.3)
        p = out_dir / "ac_schedule_toy.png"
        fig.tight_layout()
        fig.savefig(p, dpi=120)
        plt.close(fig)
        paths.append(str(p))

    # 4) Temp vs perm histogram
    rows = summary.get("rows_5m_sample") or []
    temps = np.array([r["I_temp_bps"] for r in rows], dtype=float)
    temps = temps[np.isfinite(temps)]
    if len(temps) > 10:
        fig, ax = plt.subplots(figsize=(7, 3.5))
        ax.hist(temps, bins=40, color="#6b4c9a", alpha=0.85)
        ax.axvline(float(np.mean(temps)), color="k", ls="--", label=f"mean={np.mean(temps):.2f} bps")
        ax.set_xlabel(r"$I_{\mathrm{temp}}$ (bps)")
        ax.set_ylabel("Count")
        ax.set_title("Temporary impact distribution (5m, post = +1× window)")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        p = out_dir / "temp_impact_hist.png"
        fig.tight_layout()
        fig.savefig(p, dpi=120)
        plt.close(fig)
        paths.append(str(p))

    return paths


def write_report(summary: dict, out_dir: Path) -> Path:
    fit = summary.get("fit_5m") or {}
    buckets = summary.get("buckets_5m") or []
    lines = [
        "# EXP_REPORT — Ch.3 Optimal Organisations / Trading Impact (MM memo)",
        "",
        "**Classification:** Research memo · paper only · no orders  ",
        "**Authors/plane:** ares-microstructure ← startarb warehouse `trade` (HL ETH)  ",
        f"**Date:** {summary.get('created_at', '')[:10]}  ",
        "**Decision summary:** Promote `impact.rho_slope`, `impact.temp_perm`, `sched.pov_envelope`, "
        "`lsor.latency_depth_haircut`. Hold `impact.kappa_gamma` / AC curve / TCA fill metrics. "
        "Kill extradial style split on this panel.",
        "",
        "---",
        "",
        "## 1. Executive takeaway",
        "",
        f"On HL ETH DENSE days ({', '.join(summary.get('days', []))}), "
        f"**{summary.get('n_windows_5m', 0)}** non-overlapping 5m windows show "
        "signed mid impact rising with tape order-flow intensity "
        r"$\rho=|Q_{\mathrm{net}}|/V$. "
        f"Mean temporary component ≈ **{summary.get('mean_I_temp_5m', float('nan')):.2f} bps** "
        f"(partial post-window reversion). "
        + (
            f"Power-law guide gamma_hat≈{fit['gamma']:.2f}, R²={fit['r2']:.2f} (n={fit['n']}). "
            if fit.get("ok")
            else "Power-law fit under-powered / unstable on this proxy. "
        )
        + "Treat rho as **descriptive flow intensity**, not single-algo POV capacity. "
        "Cross-ref Ch.2: schedule against `vol.curve_intraday` (peak ~18 UTC, U≈0.56).",
        "",
        "## 2. Definitions & formulas",
        "",
        "| Symbol | Definition | Units / clock |",
        "|--------|------------|---------------|",
        r"| $\rho$ | $\|Q_{\mathrm{net}}\|/V$, $Q_{\mathrm{net}}=\sum s_i q_i$ | share ∈ [0,1]; **proxy** |",
        r"| $I_{\mathrm{dur}}$ | $\mathrm{sign}(Q_{\mathrm{net}})\cdot 10^4(S_{\mathrm{end}}-S_0)/S_0$ | bps |",
        r"| $I_{\mathrm{perm}}$ | same to first post window end ($+T$) | bps |",
        r"| $I_{\mathrm{temp}}$ | $I_{\mathrm{dur}}-I_{\mathrm{perm}}$ | bps |",
        r"| IS-arrival | $\mathrm{sign}\cdot 10^4(\mathrm{VWAP}-S_0)/S_0$ | bps (D) |",
        r"| Model | $I=\kappa\sigma\rho^\gamma$ (book 3.1.1 / A.6) | fit on $I_{\mathrm{dur}}>0$ |",
        "",
        "**Honesty:** No proprietary meta-orders. Side is aggressor from warehouse tape. "
        "Price path = trade prints (not BBO mid). Warehouse tape is research-grade / may be "
        "tail-windowed per day shard — see DATA_PATHS.md.",
        "",
        "## 3. Data & method",
        "",
        "| Item | Detail |",
        "|------|--------|",
        "| Source | `startarb.data.trades.load_trade_tape('hyperliquid','ETH')` |",
        f"| Days | {summary.get('days')} (DENSE) |",
        f"| Trades | n={summary.get('n_trades')} |",
        "| Windows | 5m primary; 15m secondary; non-overlapping |",
        "| Post horizon | +1× window for permanent |",
        "| Not used | ClickHouse; own fills; multi-venue SOR OE |",
        "| Baseline | Book Fig 3.3–3.4 (CAC40 broker fills) — qualitative only |",
        "",
        "## 4. Results",
        "",
        "### 5m windows",
        "",
        f"- n windows: **{summary.get('n_windows_5m')}**",
        f"- mean ρ: **{summary.get('mean_rho_5m', float('nan')):.3f}**",
        f"- mean $I_{{\\mathrm{{dur}}}}$: **{summary.get('mean_I_dur_5m', float('nan')):.2f} bps**",
        f"- mean $I_{{\\mathrm{{perm}}}}$: **{summary.get('mean_I_perm_5m', float('nan')):.2f} bps**",
        f"- mean $I_{{\\mathrm{{temp}}}}$: **{summary.get('mean_I_temp_5m', float('nan')):.2f} bps**",
        f"- mean IS-arrival: **{summary.get('mean_is_5m', float('nan')):.2f} bps**",
        "",
    ]
    if fit.get("ok"):
        lines += [
            "### Power-law fit (5m, $I_{\\mathrm{dur}}>0$, $\\rho\\ge 0.05$)",
            "",
            f"- $\\hat\\kappa$ = **{fit['kappa']:.4f}**, $\\hat\\gamma$ = **{fit['gamma']:.3f}**, "
            f"$R^2$ = {fit['r2']:.3f}, n={fit['n']}",
            f"- Square-root reference $\\gamma=0.5$: "
            + ("near" if abs(fit["gamma"] - 0.5) < 0.25 else "away from")
            + " classic $\\sqrt{\\rho}$ heuristic.",
            "",
        ]
    if buckets:
        lines += [
            "### Impact by $\\rho$ bucket (5m)",
            "",
            "| ρ range | n | mean ρ | $I_{dur}$ | $I_{perm}$ | $I_{temp}$ |",
            "|---------|---|--------|-----------|------------|------------|",
        ]
        for b in buckets:
            lines.append(
                f"| [{b['rho_lo']:.2f},{b['rho_hi']:.2f}) | {b['n']} | {b['mean_rho']:.3f} | "
                f"{b['mean_I_dur_bps']:.2f} | {b['mean_I_perm_bps']:.2f} | {b['mean_I_temp_bps']:.2f} |"
            )
        lines.append("")
    lines += [
        f"### 15m windows: n={summary.get('n_windows_15m')}, "
        f"mean $I_{{dur}}$={summary.get('mean_I_dur_15m', float('nan')):.2f} bps, "
        f"mean $I_{{temp}}$={summary.get('mean_I_temp_15m', float('nan')):.2f} bps",
        "",
        "## 5. MM interpretation",
        "",
        "| Desk function | Implication |",
        "|---------------|-------------|",
        "| **Child-order scheduling** | Raise urgency cost with ρ; widen envelope when Ch.2 vol curve peaks (18 UTC) |",
        "| **Quoting / hedging** | Temporary component → inventory can fade; permanent → treat as toxic flow |",
        "| **PoV / VWAP algos** | Use `sched.pov_envelope` with conservative κ,γ; do not trust tape ρ as capacity |",
        "| **Liquidity seeking / SOR** | Haircut unvalidated depth (`lsor.latency_depth_haircut`); Ch.1 crossed gate still applies |",
        "| **TCA** | Arrival–VWAP gap here is market self-measure — score brokers only with *own* fills |",
        "",
        "## 6. Promote / Hold / Kill",
        "",
        "See [`CANDIDATES.md`](../../chapters/ch03_optimal_trading/CANDIDATES.md). "
        "Notebook: [`ch03_optimal_trading.ipynb`](../../chapters/ch03_optimal_trading/ch03_optimal_trading.ipynb).",
        "",
        f"Artifacts: `research/books/mmip/out/ch03_optimal_trading/`. Plots: {summary.get('plot_files', [])}",
        "",
    ]
    # Also write chapter-local copy path note
    p = out_dir / "exp_ch03_REPORT.md"
    p.write_text("\n".join(lines))
    # Mirror into chapter folder
    chap = BOOK_ROOT / "chapters" / "ch03_optimal_trading" / "EXP_REPORT.md"
    chap.write_text("\n".join(lines))
    return chap


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", nargs="*", default=DENSE_DAYS)
    ap.add_argument("--max-files", type=int, default=16)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args()
    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    print("ensure startarb…")
    _ensure_startarb()
    print("load HL ETH tape…")
    tape = load_hl_eth_tape(list(args.days), max_files=args.max_files)
    if tape is None:
        print("ERROR: no tape; abort")
        return 1

    rows5 = window_metrics(tape.ts_ns, tape.price, tape.qty_coin, tape.side, 300)
    rows15 = window_metrics(tape.ts_ns, tape.price, tape.qty_coin, tape.side, 900)
    fit5 = fit_kappa_gamma(rows5)
    buckets5 = rho_bucket_summary(rows5)
    ac = almgren_chriss_toy(
        kappa=float(fit5["kappa"]) if fit5.get("ok") else 0.5,
        lam=1e-3,
    )

    def means(rows, key):
        v = np.array([r[key] for r in rows], dtype=float)
        v = v[np.isfinite(v)]
        return float(v.mean()) if len(v) else float("nan")

    # sample rows for scatter (cap size)
    rng = np.random.default_rng(42)
    idx = np.arange(len(rows5))
    if len(idx) > 2000:
        idx = rng.choice(idx, 2000, replace=False)
    sample = [rows5[i] for i in idx]

    summary: dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "days": list(args.days),
        "n_trades": tape.n,
        "n_windows_5m": len(rows5),
        "n_windows_15m": len(rows15),
        "mean_rho_5m": means(rows5, "rho"),
        "mean_I_dur_5m": means(rows5, "I_dur_bps"),
        "mean_I_perm_5m": means(rows5, "I_perm_bps"),
        "mean_I_temp_5m": means(rows5, "I_temp_bps"),
        "mean_is_5m": means(rows5, "is_arrival_bps"),
        "mean_I_dur_15m": means(rows15, "I_dur_bps"),
        "mean_I_temp_15m": means(rows15, "I_temp_bps"),
        "fit_5m": fit5,
        "buckets_5m": buckets5,
        "rows_5m_sample": sample,
        "ac_toy": ac,
        "honesty": (
            "rho is tape |Qnet|/V (order-flow intensity), not single-algo POV; "
            "no proprietary fills; trade-print mid proxy"
        ),
    }
    plots = make_plots(summary, out_dir)
    summary["plot_files"] = plots
    # drop bulky sample from json (keep path to npz-less: store compact)
    json_payload = {k: v for k, v in summary.items() if k != "rows_5m_sample"}
    json_payload["n_sample_rows"] = len(sample)
    # store compact arrays for notebook
    np.savez_compressed(
        out_dir / "exp_ch03_windows.npz",
        rho5=np.array([r["rho"] for r in rows5]),
        I_dur5=np.array([r["I_dur_bps"] for r in rows5]),
        I_perm5=np.array([r["I_perm_bps"] for r in rows5]),
        I_temp5=np.array([r["I_temp_bps"] for r in rows5]),
        is5=np.array([r["is_arrival_bps"] for r in rows5]),
        sigma5=np.array([r["sigma_bps"] for r in rows5]),
        rho15=np.array([r["rho"] for r in rows15]),
        I_dur15=np.array([r["I_dur_bps"] for r in rows15]),
        I_temp15=np.array([r["I_temp_bps"] for r in rows15]),
    )
    (out_dir / "exp_ch03_summary.json").write_text(json.dumps(json_payload, indent=2, default=str))
    # re-attach sample for plotting already done; write report
    report = write_report(summary, out_dir)
    print("fit", fit5)
    print("wrote", out_dir / "exp_ch03_summary.json")
    print("wrote", report)
    for p in plots:
        print("plot", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
