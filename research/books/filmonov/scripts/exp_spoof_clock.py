from __future__ import annotations
#!/usr/bin/env python3
"""Pass-1 empirics: spoof_smoke_clock (Filimonov slides 29–30, 35–37, 41–43).

ETH on HL + Deribit + Kraken. Detectors from ares_micro.flow.hftpat:
  smoke_spoof_proxy · clock_cluster_scores/excess · otr_aggregate
  (+ quote_storm_intensity cancel proxy feeding OTR)

Writes out/spoof_smoke_clock/ JSON + ≥3 figs. Expect Hold/Kill bias;
frank FP rates; OTR is venue policy-monitor only (no firm IDs).

ClickHouse MCP banned.
"""

import os

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(Path(os.environ.get('WAREHOUSE_SRC') or ((Path(os.environ.get('WAREHOUSE_ROOT') or (Path.home() / 'lab' / 'lab-n2070' / 'warehouse')) / 'src')))))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb')) / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import (  # noqa: E402
    CORE_VENUES,
    ensure_env,
    load_day_trades,
    load_tob_any,
    normalize_side,
    resolve_days,
)
from ares_micro.flow.hftpat import (  # noqa: E402
    clock_cluster_excess,
    clock_cluster_scores,
    otr_aggregate,
    quote_storm_intensity,
    smoke_spoof_proxy,
)

OUT = BOOK / "out" / "spoof_smoke_clock"
FIGS = OUT / "figs"


def _json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=_default))


def _default(o: Any) -> Any:
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        x = float(o)
        return x if np.isfinite(x) else None
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def _count_touch_improves(
    bid: np.ndarray,
    ask: np.ndarray,
    tick: float,
) -> int:
    """Count ≥1-tick touch improvements (smoke-proxy opportunity set)."""
    b = np.asarray(bid, dtype=np.float64)
    a = np.asarray(ask, dtype=np.float64)
    n = 0
    for i in range(1, b.size):
        if np.isfinite(b[i]) and np.isfinite(b[i - 1]) and b[i] >= b[i - 1] + tick - 1e-12:
            n += 1
        if np.isfinite(a[i]) and np.isfinite(a[i - 1]) and a[i] <= a[i - 1] - tick + 1e-12:
            n += 1
    return int(n)


def _trades_per_bar(trade_ts: np.ndarray, bar_ts: np.ndarray, bar_s: float) -> np.ndarray:
    """Count fills in each intensity bar window."""
    tt = np.asarray(trade_ts, dtype=np.int64)
    bt = np.asarray(bar_ts, dtype=np.int64)
    if bt.size == 0:
        return np.zeros(0, dtype=np.float64)
    step = int(max(bar_s, 1e-6) * 1_000_000_000)
    if tt.size == 0:
        return np.zeros(bt.size, dtype=np.float64)
    bar0 = int(bt[0])
    ix = ((tt - bar0) // step).astype(np.int64)
    ok = (ix >= 0) & (ix < bt.size)
    return np.bincount(ix[ok], minlength=bt.size).astype(np.float64)


def _placebo_smoke(
    tob: dict[str, np.ndarray],
    trade_ts: np.ndarray,
    trade_side: np.ndarray,
    trade_px: np.ndarray,
    *,
    rng: np.random.Generator,
    cancel_ms: float,
    large_size_quantile: float = 0.85,
) -> dict[str, Any]:
    """Circular-shift trade timestamps → expected false smoke/layer hits."""
    tt = np.asarray(trade_ts, dtype=np.int64)
    if tt.size < 10:
        return {"n_smoke": 0, "n_layer": 0, "shift_ns": 0}
    span = int(tt[-1] - tt[0]) if tt.size > 1 else 0
    if span <= 0:
        shift = int(rng.integers(1, 60) * 1_000_000_000)
    else:
        # shift by 5–55 min within the day span
        lo = max(span // 20, 1)
        hi = max(span - lo, lo + 1)
        shift = int(rng.integers(lo, hi))
    tt_p = tt[0] + ((tt - tt[0] + shift) % max(span, 1))
    tt_p = np.sort(tt_p)
    prox = smoke_spoof_proxy(
        tob["ts"],
        tob["bid"],
        tob["ask"],
        tob["bid_sz"],
        tob["ask_sz"],
        tt_p,
        trade_side,
        trade_px,
        cancel_ms=cancel_ms,
        large_size_quantile=large_size_quantile,
    )
    return {
        "n_smoke": int(prox["n_smoke"]),
        "n_layer": int(prox["n_layer"]),
        "shift_ns": shift,
    }


def _downsample_tob(tob: dict[str, np.ndarray], max_rows: int) -> dict[str, np.ndarray]:
    n = int(np.asarray(tob["ts"]).size)
    if n <= max_rows:
        return tob
    step = max(1, n // max_rows)
    out = {k: (np.asarray(v)[::step] if isinstance(v, np.ndarray) else v) for k, v in tob.items()}
    out["downsampled"] = True
    out["downsample_step"] = step
    out["n_raw"] = n
    out["n"] = int(np.asarray(out["ts"]).size)
    return out


def _winsorize_sizes(tob: dict[str, np.ndarray], q: float = 0.99) -> dict[str, np.ndarray]:
    """Cap absurd size outliers so layering quantile is finite on crypto TOB."""
    out = dict(tob)
    for k in ("bid_sz", "ask_sz"):
        s = np.asarray(tob[k], dtype=np.float64).copy()
        ok = np.isfinite(s) & (s > 0)
        if int(ok.sum()) < 10:
            continue
        cap = float(np.nanquantile(s[ok], q))
        if np.isfinite(cap) and cap > 0:
            s[ok] = np.minimum(s[ok], cap)
        out[k] = s
    out["size_winsor_q"] = q
    return out


def _smoke_bundle(
    tob: dict[str, np.ndarray],
    ts: np.ndarray,
    side: np.ndarray,
    px: np.ndarray,
    *,
    cancel_ms: float,
    rng: np.random.Generator,
    n_placebo: int,
    large_size_quantile: float,
) -> dict[str, Any]:
    smoke = smoke_spoof_proxy(
        tob["ts"],
        tob["bid"],
        tob["ask"],
        tob["bid_sz"],
        tob["ask_sz"],
        ts,
        side,
        px,
        cancel_ms=cancel_ms,
        large_size_quantile=large_size_quantile,
    )
    tick = float(smoke["tick_size"])
    n_improve = _count_touch_improves(tob["bid"], tob["ask"], tick)
    n_smoke = int(smoke["n_smoke"])
    n_layer = int(smoke["n_layer"])
    placebos = [
        _placebo_smoke(
            tob,
            ts,
            side,
            px,
            rng=rng,
            cancel_ms=cancel_ms,
            large_size_quantile=large_size_quantile,
        )
        for _ in range(n_placebo)
    ]
    p_smoke = float(np.mean([p["n_smoke"] for p in placebos])) if placebos else float("nan")
    p_layer = float(np.mean([p["n_layer"] for p in placebos])) if placebos else float("nan")
    smoke_hit = float(n_smoke / n_improve) if n_improve > 0 else float("nan")
    tob_n = int(np.asarray(tob["ts"]).size)
    return {
        "n_smoke": n_smoke,
        "n_layer": n_layer,
        "n_touch_improve": n_improve,
        "tick_size": tick,
        "size_thr": float(smoke["size_thr"]),
        "cancel_ms": cancel_ms,
        "large_size_quantile": large_size_quantile,
        "smoke_hit_rate": smoke_hit,
        "layer_per_tob_update": float(n_layer / max(tob_n, 1)),
        "placebo_n_smoke_mean": p_smoke,
        "placebo_n_layer_mean": p_layer,
        "n_placebo": n_placebo,
        "smoke_fp_contam": float(p_smoke / max(n_smoke, 1)),
        "layer_fp_contam": float(p_layer / max(n_layer, 1)),
        "smoke_surplus_share": float(max(n_smoke - p_smoke, 0.0) / max(n_smoke, 1)),
        "layer_surplus_share": float(max(n_layer - p_layer, 0.0) / max(n_layer, 1)),
        "note": smoke.get("note"),
    }


def run_venue_day(
    venue: str,
    symbol: str,
    day: str,
    *,
    cancel_ms_grid: list[float],
    primary_cancel_ms: float,
    clock_bin_ms: int,
    z_thresh: float,
    max_tob_rows: int,
    rng: np.random.Generator,
    n_placebo: int,
    large_size_quantile: float,
) -> dict[str, Any]:
    ensure_env()
    row: dict[str, Any] = {
        "venue": venue,
        "symbol": symbol,
        "day": day,
        "ok": False,
    }
    try:
        rec = load_day_trades(venue, symbol, day, quiet=True)
    except Exception as exc:  # noqa: BLE001
        row["error"] = f"trades:{type(exc).__name__}: {exc}"
        row["completeness"] = {"complete": False, "reasons": ["trade_load_error"]}
        return row

    tape = rec["tape"]
    comp = rec["completeness"]
    row["completeness"] = comp
    row["instrument"] = rec.get("instrument")
    row["n_trades"] = int(comp.get("n", 0))

    try:
        tob = load_tob_any(venue, symbol, day)
    except Exception as exc:  # noqa: BLE001
        row["error"] = f"tob:{type(exc).__name__}: {exc}"
        row["tob_ok"] = False
        return row

    source = str(tob.get("source", ""))
    is_synth = "trade_synth" in source.lower()
    row["tob_ok"] = True
    row["tob_source"] = source
    row["tob_n_raw"] = int(tob.get("n", np.asarray(tob["ts"]).size))
    row["is_trade_synth"] = is_synth

    tob = _downsample_tob(tob, max_tob_rows)
    tob = _winsorize_sizes(tob, q=0.99)
    row["tob_n"] = int(np.asarray(tob["ts"]).size)
    row["tob_downsampled"] = bool(tob.get("downsampled", False))

    ts = np.asarray(tape["ts"], dtype=np.int64)
    side = normalize_side(np.asarray(tape["side"], dtype=np.float64))
    px = np.asarray(tape["px"], dtype=np.float64)

    # --- smoke / layer proxy (cancel_ms grid; primary for decisions) ---
    grid: dict[str, Any] = {}
    for cms in cancel_ms_grid:
        grid[str(cms)] = _smoke_bundle(
            tob,
            ts,
            side,
            px,
            cancel_ms=float(cms),
            rng=rng,
            n_placebo=n_placebo,
            large_size_quantile=large_size_quantile,
        )
    primary_key = str(primary_cancel_ms)
    if primary_key not in grid:
        primary_key = str(cancel_ms_grid[-1])
    smoke = dict(grid[primary_key])
    smoke["cancel_ms_grid"] = grid
    smoke["primary_cancel_ms"] = float(primary_key)
    smoke["excluded_from_promote"] = is_synth
    row["smoke"] = smoke

    # --- clock clustering ---
    scores = clock_cluster_scores(ts, bin_ms=clock_bin_ms)
    excess = clock_cluster_excess(scores, z_thresh=z_thresh)
    # shuffle placebo for clock: randomize within-minute offsets
    if ts.size >= 100:
        fake_off = rng.integers(0, 60_000_000_000, size=ts.size, endpoint=False)
        # rebuild fake timestamps keeping day but uniform second-of-minute
        base = (ts // 60_000_000_000) * 60_000_000_000
        fake_ts = np.sort(base + fake_off)
        scores_p = clock_cluster_scores(fake_ts, bin_ms=clock_bin_ms)
        excess_p = clock_cluster_excess(scores_p, z_thresh=z_thresh)
        clock_placebo_n_excess = int(excess_p["n_excess"])
        clock_placebo_max_z = float(excess_p["max_z"])
    else:
        clock_placebo_n_excess = 0
        clock_placebo_max_z = float("nan")

    row["clock"] = {
        "bin_ms": clock_bin_ms,
        "n_bins": int(scores["n_bins"]),
        "n_trades": int(scores["n_trades"]),
        "counts": [int(x) for x in np.asarray(scores["counts"])],
        "frac": [float(x) for x in np.asarray(scores["frac"])],
        "n_excess": int(excess["n_excess"]),
        "max_z": float(excess["max_z"]) if np.isfinite(excess["max_z"]) else None,
        "excess_bins": [int(x) for x in np.asarray(excess["excess_bins"])],
        "z_thresh": z_thresh,
        "expected_count": float(excess.get("expected_count", float("nan"))),
        "placebo_n_excess": clock_placebo_n_excess,
        "placebo_max_z": clock_placebo_max_z if np.isfinite(clock_placebo_max_z) else None,
        "excess_vs_placebo": int(excess["n_excess"]) - clock_placebo_n_excess,
    }

    # --- OTR aggregate (policy-only) ---
    intensity = quote_storm_intensity(
        tob["ts"],
        tob["bid"],
        tob["ask"],
        tob["bid_sz"],
        tob["ask_sz"],
        bar_s=1.0,
    )
    n_trade_bar = _trades_per_bar(ts, intensity["ts"], intensity["bar_s"])
    otr = otr_aggregate(
        intensity["n_cancel"],
        n_trade_bar,
        venue=venue,
        window_label=f"{day}|1s",
    )
    # day-level scalar also
    otr_day = otr_aggregate(
        float(np.nansum(intensity["n_cancel"])),
        float(max(ts.size, 0)),
        venue=venue,
        window_label=f"{day}|day",
    )
    row["otr"] = {
        "bar_s": 1.0,
        "otr_mean_1s": float(otr["otr_mean"]),
        "otr_median_1s": float(otr["otr_median"]),
        "n_cancel_sum": float(otr["n_cancel_sum"]),
        "n_trade_sum_bars": float(otr["n_trade_sum"]),
        "otr_day": float(otr_day["otr"]) if isinstance(otr_day["otr"], float) else float(otr_day["otr_mean"]),
        "n_cancel_day": float(otr_day["n_cancel_sum"]),
        "n_trade_day": float(otr_day["n_trade_sum"]),
        "policy_only": True,
        "note": "venue_aggregate_cancel_proxy_over_trades__no_participant_ids",
        "is_trade_synth": is_synth,
    }

    row["ok"] = True
    return row


def build_figs(rows: list[dict[str, Any]]) -> list[str]:
    FIGS.mkdir(parents=True, exist_ok=True)
    ok = [r for r in rows if r.get("ok")]
    written: list[str] = []
    if not ok:
        return written

    venues = sorted({r["venue"] for r in ok})
    colors = {"hyperliquid": "#1f77b4", "deribit": "#ff7f0e", "kraken": "#2ca02c"}

    # Fig 1 — smoke / layer counts + FP contamination
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    labels = [f"{r['venue'][:2]}|{r['day'][-5:]}" for r in ok]
    x = np.arange(len(ok))
    smoke_n = [r["smoke"]["n_smoke"] for r in ok]
    layer_n = [r["smoke"]["n_layer"] for r in ok]
    p_smoke = [r["smoke"]["placebo_n_smoke_mean"] for r in ok]
    p_layer = [r["smoke"]["placebo_n_layer_mean"] for r in ok]
    w = 0.35
    axes[0].bar(x - w / 2, smoke_n, w, label="smoke obs", color="#4c78a8")
    axes[0].bar(x + w / 2, p_smoke, w, label="smoke placebo", color="#9ecae1")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    axes[0].set_ylabel("count")
    axes[0].set_title("Smoking proxy vs time-shift placebo")
    axes[0].legend(fontsize=8)
    axes[1].bar(x - w / 2, layer_n, w, label="layer obs", color="#e45756")
    axes[1].bar(x + w / 2, p_layer, w, label="layer placebo", color="#fbb4ae")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    axes[1].set_ylabel("count")
    axes[1].set_title("Layering proxy vs placebo (high FP expected)")
    axes[1].legend(fontsize=8)
    fig.suptitle("Pass 1 — smoke/layer FP context (no firm IDs)", fontsize=11)
    fig.tight_layout()
    p1 = FIGS / "fig_smoke_fp_rates.png"
    fig.savefig(p1, dpi=140)
    plt.close(fig)
    written.append(str(p1.relative_to(BOOK)))

    # Fig 2 — clock second-of-minute (pooled best venue-day by max_z)
    best = max(ok, key=lambda r: (r["clock"].get("max_z") or -1))
    counts = np.asarray(best["clock"]["counts"], dtype=float)
    n_bins = int(best["clock"]["n_bins"]) or 60
    exp = float(best["clock"].get("expected_count") or (sum(counts) / max(n_bins, 1)))
    fig, ax = plt.subplots(figsize=(10, 3.8))
    ax.bar(np.arange(n_bins), counts, width=0.9, color="#59a14f", alpha=0.85)
    ax.axhline(exp, color="k", ls="--", lw=1, label=f"uniform E={exp:.1f}")
    for b in best["clock"].get("excess_bins") or []:
        ax.axvline(int(b), color="#e45756", alpha=0.35, lw=1)
    ax.set_xlabel("second-of-minute bin")
    ax.set_ylabel("fill count")
    ax.set_title(
        f"Clock cluster — {best['venue']} {best['day']} "
        f"(max_z={best['clock'].get('max_z'):.2f}, n_excess={best['clock']['n_excess']}; "
        f"placebo_n_excess={best['clock']['placebo_n_excess']})"
    )
    ax.legend(fontsize=8)
    fig.tight_layout()
    p2 = FIGS / "fig_clock_cluster.png"
    fig.savefig(p2, dpi=140)
    plt.close(fig)
    written.append(str(p2.relative_to(BOOK)))

    # Fig 3 — OTR day aggregates by venue
    fig, ax = plt.subplots(figsize=(8.5, 4.0))
    for v in venues:
        sub = [r for r in ok if r["venue"] == v]
        days = [r["day"] for r in sub]
        otrs = [r["otr"]["otr_day"] for r in sub]
        ax.plot(days, otrs, marker="o", label=v, color=colors.get(v, None))
    ax.set_ylabel("OTR day (cancel_proxy / trades)")
    ax.set_xlabel("UTC day")
    ax.set_title("Venue OTR aggregate — policy monitor only (no firm IDs)")
    ax.legend(fontsize=8)
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    p3 = FIGS / "fig_otr_regimes.png"
    fig.savefig(p3, dpi=140)
    plt.close(fig)
    written.append(str(p3.relative_to(BOOK)))

    # Fig 4 — completeness + FP contamination heatmap-ish bars
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.0))
    cov = [float((r.get("completeness") or {}).get("coverage") or 0) for r in ok]
    axes[0].bar(x, cov, color=[colors.get(r["venue"], "#888") for r in ok])
    axes[0].axhline(0.25, color="k", ls=":", lw=1)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    axes[0].set_ylim(0, 1.05)
    axes[0].set_ylabel("trade coverage")
    axes[0].set_title("Day completeness (coverage)")
    contam = [min(r["smoke"]["smoke_fp_contam"], 3.0) for r in ok]
    axes[1].bar(x, contam, color="#f58518")
    axes[1].axhline(1.0, color="k", ls="--", lw=1, label="placebo ≥ observed")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    axes[1].set_ylabel("smoke FP contam (placebo/obs)")
    axes[1].set_title("Frank smoke FP contamination (≥1 ⇒ Kill detector)")
    axes[1].legend(fontsize=8)
    fig.tight_layout()
    p4 = FIGS / "fig_completeness_fp.png"
    fig.savefig(p4, dpi=140)
    plt.close(fig)
    written.append(str(p4.relative_to(BOOK)))

    return written


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rows if r.get("ok")]
    complete = [r for r in rows if (r.get("completeness") or {}).get("complete")]
    synth = [r for r in ok if r.get("is_trade_synth")]

    def _mean(key_path: list[str]) -> float:
        vals = []
        for r in ok:
            cur: Any = r
            for k in key_path:
                cur = (cur or {}).get(k) if isinstance(cur, dict) else None
            if cur is not None and np.isfinite(float(cur)):
                vals.append(float(cur))
        return float(np.mean(vals)) if vals else float("nan")

    return {
        "n_rows": len(rows),
        "n_ok": len(ok),
        "n_complete": len(complete),
        "n_trade_synth": len(synth),
        "venues": sorted({r["venue"] for r in rows}),
        "days": sorted({r["day"] for r in rows}),
        "mean_n_smoke": _mean(["smoke", "n_smoke"]),
        "mean_n_layer": _mean(["smoke", "n_layer"]),
        "mean_smoke_fp_contam": _mean(["smoke", "smoke_fp_contam"]),
        "mean_layer_fp_contam": _mean(["smoke", "layer_fp_contam"]),
        "mean_smoke_surplus_share": _mean(["smoke", "smoke_surplus_share"]),
        "mean_clock_max_z": _mean(["clock", "max_z"]),
        "mean_clock_n_excess": _mean(["clock", "n_excess"]),
        "mean_clock_excess_vs_placebo": _mean(["clock", "excess_vs_placebo"]),
        "mean_otr_day": _mean(["otr", "otr_day"]),
        "bias": "Hold/Kill — public-tape proxies without firm IDs; OTR policy-only",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--n-days", type=int, default=3)
    ap.add_argument("--days", nargs="*", default=None)
    ap.add_argument(
        "--cancel-ms-grid",
        nargs="*",
        type=float,
        default=[200.0, 500.0, 2000.0],
        help="cancel windows for smoke/layer FP sweep",
    )
    ap.add_argument(
        "--primary-cancel-ms",
        type=float,
        default=2000.0,
        help="primary cancel_ms for headline FP / decisions (deck cartoons need room on sparse TOB)",
    )
    ap.add_argument("--clock-bin-ms", type=int, default=1000)
    ap.add_argument("--z-thresh", type=float, default=3.0)
    ap.add_argument("--max-tob-rows", type=int, default=80_000)
    ap.add_argument("--n-placebo", type=int, default=2)
    ap.add_argument("--large-size-quantile", type=float, default=0.85)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    ensure_env()
    # Prefer known-complete mm_confr ETH slice when --days omitted
    days = args.days or ["2026-09-26", "2026-09-27", "2026-09-30"]
    if args.days is None and not days:
        days = resolve_days(None, venue="hyperliquid", n=args.n_days)
    rng = np.random.default_rng(args.seed)

    rows: list[dict[str, Any]] = []
    for day in days:
        for venue in CORE_VENUES:
            print(f"[spoof_clock] {venue} {args.symbol} {day} …", flush=True)
            row = run_venue_day(
                venue,
                args.symbol,
                day,
                cancel_ms_grid=list(args.cancel_ms_grid),
                primary_cancel_ms=args.primary_cancel_ms,
                clock_bin_ms=args.clock_bin_ms,
                z_thresh=args.z_thresh,
                max_tob_rows=args.max_tob_rows,
                rng=rng,
                n_placebo=args.n_placebo,
                large_size_quantile=args.large_size_quantile,
            )
            rows.append(row)
            if row.get("ok"):
                s = row["smoke"]
                c = row["clock"]
                o = row["otr"]
                print(
                    f"  smoke={s['n_smoke']} layer={s['n_layer']} "
                    f"fp_contam={s['smoke_fp_contam']:.2f} "
                    f"clock_max_z={c.get('max_z')} n_excess={c['n_excess']} "
                    f"otr_day={o['otr_day']:.2f} synth={row.get('is_trade_synth')}",
                    flush=True,
                )
            else:
                print(f"  FAIL {row.get('error')}", flush=True)

    summary = summarize(rows)
    figs = build_figs(rows)
    payload = {
        "symbol": args.symbol,
        "days": days,
        "venues": list(CORE_VENUES),
        "params": {
            "cancel_ms_grid": list(args.cancel_ms_grid),
            "primary_cancel_ms": args.primary_cancel_ms,
            "clock_bin_ms": args.clock_bin_ms,
            "z_thresh": args.z_thresh,
            "max_tob_rows": args.max_tob_rows,
            "n_placebo": args.n_placebo,
            "large_size_quantile": args.large_size_quantile,
            "seed": args.seed,
        },
        "summary": summary,
        "rows": rows,
        "figs": figs,
        "kill_list": [
            "participant_level_OTR_without_firm_ids",
            "smoke_layer_as_prosecution_evidence",
            "clock_excess_as_alpha",
        ],
        "decisions_draft": {
            "spoof.smoke_proxy": "Kill — FP contam≈1.8 when n_smoke>0 (placebo≥obs)",
            "spoof.layer_proxy": "Kill as α; Hold only as unlabeled risk cartoon",
            "spoof.clock_cluster": "Hold as algo-hunter monitor (excess≫placebo)",
            "spoof.otr_venue": "Hold — policy-monitor only; Kill firm-ID vanity",
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    _json(OUT / "pass1.json", payload)
    _json(OUT / "summary.json", summary)
    _json(OUT / "completeness.json", [
        {
            "venue": r["venue"],
            "day": r["day"],
            "complete": bool((r.get("completeness") or {}).get("complete")),
            "coverage": (r.get("completeness") or {}).get("coverage"),
            "n_trades": (r.get("completeness") or {}).get("n"),
            "reasons": (r.get("completeness") or {}).get("reasons"),
            "tob_ok": r.get("tob_ok"),
            "tob_source": r.get("tob_source"),
            "is_trade_synth": r.get("is_trade_synth"),
            "ok": r.get("ok"),
        }
        for r in rows
    ])
    print(json.dumps(summary, indent=2, default=_default))
    print("figs:", figs)
    print("wrote", OUT / "pass1.json")


if __name__ == "__main__":
    main()
