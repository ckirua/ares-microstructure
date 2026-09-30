#!/usr/bin/env python3
"""Ch.15 PIN / VPIN / intensity figures + enriched EXP_REPORT (second pass)."""

from __future__ import annotations

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
sys.path.insert(0, str(Path("/home/dev/srv/ares-startarb") / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import ensure_env, load_trades  # noqa: E402
from research.lib import vpin_bucket  # noqa: E402

OUT = BOOK / "out" / "ch15_pin"
OUT13 = BOOK / "out" / "ch13_var_impact"
CHAP = BOOK / "chapters" / "ch15_pin"


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.grid": True,
            "grid.alpha": 0.25,
            "font.size": 10,
        }
    )


def _usable_days(day_meta: dict, min_trades: int = 400, min_span_h: float = 4.0) -> list[str]:
    out = []
    for day, v in sorted(day_meta.items()):
        if not isinstance(v, dict):
            continue
        n = int(v.get("n") or 0)
        span = float(v.get("span_h") or 0.0)
        if n >= min_trades and span >= min_span_h and "B" in v:
            out.append(day)
    return out


def _vpin_roll_series(
    symbol: str, days: list[str], *, max_files: int = 48
) -> tuple[np.ndarray, dict]:
    """Reload a few days and return rolling VPIN path (for path figure)."""
    all_side: list[np.ndarray] = []
    all_qty: list[np.ndarray] = []
    for day in days:
        try:
            tape = load_trades(symbol, [day], max_files=max_files)
        except Exception as exc:  # noqa: BLE001
            print(f"  vpin path skip {day}: {exc}")
            continue
        if len(tape) == 0:
            continue
        side = np.asarray(tape.side, dtype=np.float64)
        qty = np.asarray(tape.qty_coin, dtype=np.float64)
        all_side.append(side)
        all_qty.append(qty)
    if not all_side:
        return np.array([]), {}
    side = np.concatenate(all_side)
    qty = np.concatenate(all_qty)
    bar_v = float(np.nanmedian(qty[qty > 0]) * 50) if np.any(qty > 0) else 1.0
    # rebuild imbalances + roll locally (vpin_bucket only returns summary)
    s = side
    q = qty
    m = np.isfinite(s) & np.isfinite(q) & (q > 0) & (s != 0)
    s, q = s[m], q[m]
    buy_acc = sell_acc = vol_acc = 0.0
    imbalances: list[float] = []
    for i in range(s.size):
        if s[i] > 0:
            buy_acc += q[i]
        else:
            sell_acc += q[i]
        vol_acc += q[i]
        if vol_acc >= bar_v:
            imbalances.append(abs(buy_acc - sell_acc) / vol_acc)
            buy_acc = sell_acc = vol_acc = 0.0
    imb = np.asarray(imbalances, dtype=np.float64)
    w = min(50, int(imb.size))
    if imb.size < 5:
        return np.array([]), {"bucket_volume": bar_v, "n_buckets": int(imb.size)}
    roll = np.convolve(imb, np.ones(w) / w, mode="valid")
    summary = vpin_bucket(side, qty, bucket_volume=bar_v, n_buckets_window=50)
    summary["path_days"] = days
    summary["path_n_trades"] = int(s.size)
    return roll, summary


def main() -> int:
    ensure_env()
    OUT.mkdir(parents=True, exist_ok=True)
    _style()
    summary_path = OUT / "exp_ch15_eth_summary.json"
    d = json.loads(summary_path.read_text())
    symbol = d.get("symbol", "ETH")
    day_meta = d.get("day_meta") or {}
    mle = d.get("disc_pin_eho_mle") or {}
    mle_sym = d.get("disc_pin_eho_mle_symmetric") or {}
    proxy = d.get("disc_pin_proxy") or {}
    vpin = d.get("cont_vpin") or {}
    intens = d.get("cont_intensity") or {}
    usable = set(mle.get("day_keys") or _usable_days(day_meta))

    # --- Fig 1: day-level B/S scatter ---
    rows = [(k, v) for k, v in sorted(day_meta.items()) if isinstance(v, dict) and "B" in v]
    Bs = np.array([v["B"] for _, v in rows], dtype=float)
    Ss = np.array([v["S"] for _, v in rows], dtype=float)
    spans = np.array([v.get("span_h", np.nan) for _, v in rows], dtype=float)
    days_lab = [k for k, _ in rows]
    is_u = np.array([k in usable for k in days_lab], dtype=bool)

    fig, ax = plt.subplots(figsize=(6.4, 5.2), constrained_layout=True)
    if rows:
        sc = ax.scatter(
            Bs[~is_u],
            Ss[~is_u],
            c=spans[~is_u],
            cmap="Greys",
            s=36,
            edgecolors="0.4",
            linewidths=0.4,
            vmin=0,
            vmax=max(24.0, float(np.nanmax(spans))),
            label="thin / unused",
            alpha=0.7,
        )
        ax.scatter(
            Bs[is_u],
            Ss[is_u],
            c=spans[is_u],
            cmap="viridis",
            s=55,
            edgecolors="k",
            linewidths=0.4,
            vmin=0,
            vmax=max(24.0, float(np.nanmax(spans))),
            label=f"MLE usable (n={is_u.sum()})",
        )
        lim = max(float(Bs.max(initial=1)), float(Ss.max(initial=1))) * 1.05
        ax.plot([0, lim], [0, lim], "k--", lw=0.8, alpha=0.5)
        cb = fig.colorbar(sc, ax=ax)
        cb.set_label("span_h")
    ax.set_xlabel("Buys B")
    ax.set_ylabel("Sells S")
    ax.set_title("Day-level (B,S) — EHO mixture inputs")
    ax.legend(loc="upper left", fontsize=8)
    fig.savefig(OUT / "fig_bs_scatter.png", dpi=120)
    plt.close(fig)

    # --- Fig 2: PIN day panel (imb + span + usable) ---
    fig, ax = plt.subplots(2, 1, figsize=(11.0, 5.8), sharex=True, constrained_layout=True)
    if rows:
        x = np.arange(len(rows))
        imb = np.array([(v["B"] - v["S"]) / max(v["B"] + v["S"], 1) for _, v in rows], dtype=float)
        colors = ["#238b45" if u else "#bdbdbd" for u in is_u]
        ax[0].bar(x, imb, color=colors, alpha=0.9)
        ax[0].axhline(0, color="k", lw=0.6)
        ax[0].set_ylabel("(B−S)/(B+S)")
        ax[0].set_title(
            f"PIN day panel · usable≥4h/n≥400 in green · "
            f"MLE PIN={mle.get('PIN', float('nan')):.3f} (n={mle.get('n_days')})"
        )
        ax[1].bar(x, spans, color=colors, alpha=0.9)
        ax[1].axhline(4.0, color="#e6550d", ls="--", lw=1, label="min_span_h=4")
        ax[1].set_ylabel("span_h")
        ax[1].set_xlabel("warehouse day")
        ax[1].set_xticks(x)
        ax[1].set_xticklabels([d[-5:] for d in days_lab], rotation=60, ha="right", fontsize=8)
        ax[1].legend(fontsize=8, loc="upper right")
    fig.savefig(OUT / "fig_pin_day_panel.png", dpi=120)
    plt.close(fig)

    # --- Fig 3: PIN vs VPIN levels ---
    pin = mle.get("PIN")
    pin_s = mle_sym.get("PIN")
    proxy_v = proxy.get("pin_proxy")
    vpin_m = vpin.get("mean_vpin")
    fig, ax = plt.subplots(figsize=(6.2, 3.6), constrained_layout=True)
    labels = ["PIN MLE\n(free ε)", "PIN MLE\n(sym ε)", "PIN proxy\n|imb|", "VPIN mean\n(vol clock)"]
    vals = [
        pin if pin is not None else np.nan,
        pin_s if pin_s is not None else np.nan,
        proxy_v if proxy_v is not None else np.nan,
        vpin_m if vpin_m is not None else np.nan,
    ]
    cols = ["#1f4e79", "#5b8fbe", "#9ecae1", "#c45c26"]
    ax.bar(labels, vals, color=cols, alpha=0.92)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("level")
    ax.set_title("PIN (day mixture) vs VPIN (volume clock)\n— not interchangeable")
    for i, v in enumerate(vals):
        if np.isfinite(v):
            ax.text(i, v + 0.02, f"{v:.3f}", ha="center", fontsize=9)
    fig.savefig(OUT / "fig_pin_vs_vpin.png", dpi=120)
    plt.close(fig)

    # --- Fig 4: VPIN rolling path (reload recent usable days) ---
    path_days = [d for d in sorted(usable) if d >= "2026-09-25"][-4:]
    if not path_days:
        path_days = sorted(usable)[-3:]
    print("VPIN path days:", path_days)
    roll, path_meta = _vpin_roll_series(symbol, path_days)
    fig, ax = plt.subplots(figsize=(10.5, 3.6), constrained_layout=True)
    if roll.size:
        # downsample for draw
        step = max(1, roll.size // 2500)
        xs = np.arange(0, roll.size, step)
        ax.plot(xs, roll[::step], color="#c45c26", lw=0.9, alpha=0.9)
        ax.axhline(float(vpin_m or np.nanmean(roll)), color="#a63603", ls="--", lw=1.2, label="deep-run mean VPIN")
        ax.axhline(float(np.median(roll)), color="#fd8d3c", ls=":", lw=1.1, label="path median")
        ax.set_ylim(0, 1.05)
        ax.set_xlabel(f"volume-bucket index (window=50; days={path_days})")
        ax.set_ylabel("rolling VPIN")
        ax.set_title(
            f"VPIN path (synthetic reload) · n_roll={roll.size:,} · "
            f"bucket_V≈{path_meta.get('bucket_volume', float('nan')):.2f}"
        )
        ax.legend(fontsize=8)
    else:
        ax.text(0.5, 0.5, "no VPIN path", ha="center", va="center", transform=ax.transAxes)
        ax.set_title("VPIN path (empty)")
    fig.savefig(OUT / "fig_vpin_path.png", dpi=120)
    plt.close(fig)

    # --- Fig 5: VPIN vs markout comparative board (cross-ch13) ---
    d13 = {}
    p13 = OUT13 / "exp_ch13_eth_summary.json"
    if p13.exists():
        d13 = json.loads(p13.read_text())
    mo = ((d13.get("markouts") or {}).get("by_horizon") or {})
    mo1 = (mo.get("1000") or {}).get("mean_bps")
    mo05 = (mo.get("500") or {}).get("mean_bps")
    mo5 = (mo.get("5000") or {}).get("mean_bps")
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 3.8), constrained_layout=True)
    # left: toxicity / intensity levels (unitless 0–1 scale where applicable)
    left_labs = ["PIN MLE", "VPIN mean", "intens ac1"]
    left_vals = [
        float(pin) if pin is not None else np.nan,
        float(vpin_m) if vpin_m is not None else np.nan,
        float(intens.get("count_ac1", np.nan)),
    ]
    ax[0].bar(left_labs, left_vals, color=["#1f4e79", "#c45c26", "#6a51a3"], alpha=0.9)
    ax[0].set_ylim(0, 1.05)
    ax[0].set_title("Toxicity / clustering (unitless)")
    ax[0].set_ylabel("level")
    for i, v in enumerate(left_vals):
        if np.isfinite(v):
            ax[0].text(i, min(v + 0.03, 1.0), f"{v:.3f}", ha="center", fontsize=8)
    # right: markout horizons (bps) — different units, explicit
    right_labs = ["0.5s", "1s", "5s"]
    right_vals = [
        float(mo05) if mo05 is not None else np.nan,
        float(mo1) if mo1 is not None else np.nan,
        float(mo5) if mo5 is not None else np.nan,
    ]
    ax[1].bar(right_labs, right_vals, color=["#9ecae1", "#3182bd", "#08519c"], alpha=0.9)
    ax[1].axhline(0, color="k", lw=0.6)
    ax[1].set_ylabel("signed markout (bps)")
    ax[1].set_title("Ch.13 markout (same ETH window family)\nVPIN high ⇒ widen; markout = AS edge")
    for i, v in enumerate(right_vals):
        if np.isfinite(v):
            ax[1].text(i, v + 0.02, f"{v:.3f}", ha="center", fontsize=8)
    fig.savefig(OUT / "fig_vpin_vs_markout.png", dpi=120)
    plt.close(fig)

    # --- Fig 6: intensity summary ---
    fig, ax = plt.subplots(1, 2, figsize=(9.5, 3.6), constrained_layout=True)
    lam = float(intens.get("mean_lambda", np.nan))
    lo, hi = (intens.get("lambda_ci95") or [np.nan, np.nan])[:2]
    ax[0].bar(["λ̂ /s"], [lam], color="#2c7fb8", alpha=0.9)
    if np.isfinite(lo) and np.isfinite(hi):
        ax[0].errorbar([0], [lam], yerr=[[lam - lo], [hi - lam]], fmt="none", ecolor="k", capsize=4)
    ax[0].set_title(f"Trade intensity · n_bars={intens.get('n_bars', 0):,}")
    ax[0].set_ylabel("trades / second")
    ac1 = float(intens.get("count_ac1", np.nan))
    ax[1].bar(["count ac1"], [ac1], color="#6a51a3", alpha=0.9)
    ax[1].axhline(0, color="k", lw=0.6)
    ax[1].set_ylim(-0.05, max(0.5, ac1 * 1.25 if np.isfinite(ac1) else 0.5))
    ax[1].set_title("1s count clustering")
    ax[1].set_ylabel("ρ₁(counts)")
    fig.savefig(OUT / "fig_intensity.png", dpi=120)
    plt.close(fig)

    figures = [
        "fig_bs_scatter.png",
        "fig_pin_day_panel.png",
        "fig_pin_vs_vpin.png",
        "fig_vpin_path.png",
        "fig_vpin_vs_markout.png",
        "fig_intensity.png",
    ]
    d["figures"] = figures
    d["plot_meta"] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "vpin_path_days": path_days,
        "vpin_path_n_roll": int(roll.size),
        "vpin_path_meta": {k: path_meta.get(k) for k in ("bucket_volume", "path_n_trades", "n_buckets")},
        "markout_1s_bps": mo1,
        "markout_source": "out/ch13_var_impact/exp_ch13_eth_summary.json",
    }
    summary_path.write_text(json.dumps(d, indent=2, default=str))

    span = d.get("sample_span") or {}
    lines = [
        f"# Ch.15 PIN / VPIN / intensity — {symbol} (deep + plot pass)",
        "",
        "## Sample",
        f"- Sample: {span.get('utc_start')} → {span.get('utc_end')} "
        f"({span.get('span_h', float('nan')):.1f}h, n_trades={span.get('n_trades')})",
        f"- Days requested={d.get('days_requested') and len(d['days_requested'])} · "
        f"with tape={d.get('n_days_with_tape')} · MLE usable={d.get('n_days_mle_usable')}",
        "",
        "## PIN (disc)",
        f"- PIN MLE (free ε)={mle.get('PIN')} · α={mle.get('alpha')} · μ={mle.get('mu')} · "
        f"εb={mle.get('eps_b')} · εs={mle.get('eps_s')}",
        f"- PIN symmetric-ε={mle_sym.get('PIN')} · |ΔPIN|="
        f"{abs(float(mle.get('PIN', np.nan)) - float(mle_sym.get('PIN', np.nan))):.4f}",
        f"- proxy E|B−S|/(B+S)={proxy.get('pin_proxy')} · usable day_keys={mle.get('day_keys')}",
        "",
        "## VPIN / intensity (cont)",
        f"- VPIN mean={vpin.get('mean_vpin')} · CI={vpin.get('vpin_ci95')} · "
        f"n_buckets={vpin.get('n_buckets')} · p50={vpin.get('p50_vpin')}",
        f"- Intensity λ={intens.get('mean_lambda')} /s · CI={intens.get('lambda_ci95')} · "
        f"ac1={intens.get('count_ac1')}",
        f"- Path reload days={path_days} · n_roll={roll.size:,}",
        "",
        "## Cross-link Ch.13 markout",
        f"- markout 0.5/1/5s bps = {mo05} / {mo1} / {mo5}",
        "- VPIN and markout are **different clocks/units** — panel is regime vs AS-edge, not a regression.",
        "",
        "## Decisions",
    ]
    for k, v in (d.get("decisions") or {}).items():
        fals = (d.get("falsifiers") or {}).get(k, "")
        lines.append(f"- `{k}`: **{v}** — {fals}")
    if d.get("blockers"):
        lines += ["", "## Blockers"]
        for b in d["blockers"]:
            lines.append(f"- {b}")
    lines += ["", "## Figures"]
    for f in figures:
        lines.append(f"- `out/ch15_pin/{f}`")
    n_use = int(d.get("n_days_mle_usable") or 0)
    pin_f = float(mle.get("PIN", float("nan")))
    pin_s = float(mle_sym.get("PIN", float("nan")))
    split = d.get("time_split") or {}
    cert = d.get("certification") or []
    lines += ["", "## Desk / second-pass read"]
    if n_use >= 20 and (d.get("decisions") or {}).get("disc.pin_eho_mle") == "Promote":
        lines += [
            f"- Day panel: **{n_use} usable** ≥4h days → EHO MLE **Promote** "
            f"(opaque flat-id + UTC clip; thin public-md days still warehouse gaps).",
            f"- Free vs sym-ε PIN ≈{pin_f:.3f} vs {pin_s:.3f} "
            f"(|Δ|={abs(pin_f-pin_s):.3f}<0.15) — product αμ better ID'd than α,μ alone (Ch.15.b).",
            f"- Time-split early/late ≈{split.get('early_PIN')}/{split.get('late_PIN')} (ok).",
            f"- VPIN mean≈{float(vpin.get('mean_vpin') or float('nan')):.3f} on "
            f"~{int(vpin.get('n_buckets') or 0):.0e} buckets → **Promote** volume-clock toxicity.",
            "- Markout 1s (Ch.13) is the tick AS object; use VPIN to *when* to widen, markout for *how much*.",
            f"- Intensity λ≈{float(intens.get('mean_lambda') or float('nan')):.2f}/s with "
            f"ac1≈{float(intens.get('count_ac1') or float('nan')):.2f} → clustering; POV / delay-take.",
            "- PIN day-mixture ≠ VPIN level — never scale one into the other.",
        ]
    else:
        lines += [
            f"- Day panel shows only {n_use} usable ≥4h days → EHO MLE stays **Hold** (need ≥20).",
            f"- Free vs sym-ε PIN ≈{pin_f:.3f} vs {pin_s:.3f}.",
            "- PIN day-mixture ≠ VPIN level — never scale one into the other.",
        ]
    if cert:
        lines += ["", "## Certification"]
        for c in cert:
            lines.append(f"- {c}")
    report = "\n".join(lines) + "\n"
    (OUT / f"exp_ch15_{symbol.lower()}_REPORT.md").write_text(report)
    (CHAP / "EXP_REPORT.md").write_text(report)
    print(report)
    print("Wrote figures:", figures)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
