from __future__ import annotations
#!/usr/bin/env python3
"""Pass-1 empirics for Filimonov core detectors.

Packages: quote_storms · book_fade · momentum_ignition
Venues: HL + Deribit + Kraken via ``_data.py``. ETH first.
Outputs: ``out/{quote_storms,book_fade,momentum_ignition}/`` JSON + ≥3 figs each.

ClickHouse MCP banned. Detectors: ``research.lib.hftpat``.
Kraken ``trade_synth`` TOB is labeled and **excluded** from native TOB fade tests.
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
import numpy as np  # noqa: E402

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
from research.lib.crash import (  # noqa: E402
    detect_ssm_events,
    kalman_ssm_filter,
    mc_garch_bar_vol,
    nanex_detect,
    sigma_process_meas,
    vshape_events,
)
from research.lib.hftpat import (  # noqa: E402
    ignition_bar_timestamps,
    ignition_events,
    overlap_vs_crash,
    price_fade_events,
    price_fade_prob,
    quote_storm_detect,
    quote_storm_intensity,
    quote_storm_summary,
    rename_gate,
    venue_fade_events,
    venue_fade_prob,
)

OUT = BOOK / "out"
CH = BOOK / "chapters"


def _json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=_json_default))


def _json_default(o: Any) -> Any:
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating, np.float64, np.float32)):
        x = float(o)
        return x if np.isfinite(x) else None
    if isinstance(o, (np.integer, np.int64, np.int32)):
        return int(o)
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    return str(o)


def _is_trade_synth(tob: dict[str, Any] | None) -> bool:
    if tob is None:
        return False
    src = str(tob.get("source", "")).lower()
    return "trade_synth" in src


def _subsample(n: int, max_n: int, seed: int = 42) -> np.ndarray:
    """Even stride indices (deterministic) capped at max_n."""
    if n <= max_n:
        return np.arange(n, dtype=np.int64)
    step = max(1, int(np.ceil(n / max_n)))
    idx = np.arange(0, n, step, dtype=np.int64)
    if idx.size > max_n:
        rng = np.random.default_rng(seed)
        idx = np.sort(rng.choice(idx, size=max_n, replace=False))
    return idx


def _cancel_proxy_ts(
    tob: dict[str, Any],
    trade_ts: np.ndarray,
    trade_side: np.ndarray,
    trade_qty: np.ndarray,
    *,
    drop_frac: float = 0.2,
    trade_match_ms: int = 250,
) -> np.ndarray:
    """Timestamps of lob-style cancel_proxy events (for draft rename notes)."""
    t = np.asarray(tob["ts"], dtype=np.int64)
    b = np.asarray(tob["bid"], dtype=np.float64)
    a = np.asarray(tob["ask"], dtype=np.float64)
    bs = np.asarray(tob["bid_sz"], dtype=np.float64)
    az = np.asarray(tob["ask_sz"], dtype=np.float64)
    tt = np.asarray(trade_ts, dtype=np.int64)
    ts_side = normalize_side(trade_side)
    tq = np.asarray(trade_qty, dtype=np.float64)
    match_ns = int(trade_match_ms) * 1_000_000
    out: list[int] = []
    for px, sz, hit_sign in (
        (b, bs, -1.0),
        (a, az, 1.0),
    ):
        for i in range(1, t.size):
            if not (np.isfinite(px[i]) and np.isfinite(px[i - 1]) and abs(px[i] - px[i - 1]) < 1e-12):
                continue
            if not (np.isfinite(sz[i]) and np.isfinite(sz[i - 1]) and sz[i - 1] > 0):
                continue
            drop = float(sz[i - 1] - sz[i])
            if drop / sz[i - 1] < drop_frac or drop <= 0:
                continue
            lo = int(np.searchsorted(tt, t[i] - match_ns, side="left"))
            hi = int(np.searchsorted(tt, t[i] + match_ns, side="right"))
            matched = 0.0
            for j in range(lo, hi):
                if np.isfinite(ts_side[j]) and ts_side[j] * hit_sign > 0 and np.isfinite(tq[j]) and tq[j] > 0:
                    matched += float(tq[j])
            if matched <= 1e-12:
                out.append(int(t[i]))
    return np.asarray(out, dtype=np.int64)


def load_venue_day(symbol: str, day: str, venue: str, *, max_files: int) -> dict[str, Any]:
    ensure_env()
    rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
    tape = rec["tape"]
    tob_err = None
    tob: dict[str, Any] | None
    try:
        tob = load_tob_any(venue, symbol, day)
    except Exception as exc:  # noqa: BLE001
        tob = None
        tob_err = f"{type(exc).__name__}: {exc}"
    synth = _is_trade_synth(tob)
    return {
        "venue": venue,
        "symbol": symbol,
        "day": day,
        "instrument": rec.get("instrument"),
        "completeness": rec["completeness"],
        "tape": {
            "ts": np.asarray(tape["ts"], dtype=np.int64),
            "px": np.asarray(tape["px"], dtype=np.float64),
            "qty": np.asarray(tape["qty"], dtype=np.float64),
            "side": normalize_side(tape["side"]),
        },
        "tob": tob,
        "tob_ok": tob is not None,
        "tob_error": tob_err,
        "tob_n": int(tob.get("n", 0)) if tob is not None else 0,
        "tob_source": (tob or {}).get("source"),
        "is_trade_synth": synth,
        "native_tob": bool(tob is not None and not synth),
    }


# ---------------------------------------------------------------------------
# Quote storms
# ---------------------------------------------------------------------------


def run_quote_storms(rows: list[dict[str, Any]], out_dir: Path) -> dict[str, Any]:
    figs = out_dir / "figs"
    figs.mkdir(parents=True, exist_ok=True)
    day_rows: list[dict[str, Any]] = []
    for row in rows:
        venue, day = row["venue"], row["day"]
        base = {
            "venue": venue,
            "day": day,
            "completeness": row["completeness"],
            "tob_ok": row["tob_ok"],
            "tob_source": row["tob_source"],
            "is_trade_synth": row["is_trade_synth"],
            "native_tob": row["native_tob"],
            "note_not_lob_rename": (
                "quote_storm_* = burst intensity (add+cancel proxy Hz / update Hz) vs day "
                "baseline — not lob.tob_depletion_cancel_proxy (unconditional size-drop class)."
            ),
        }
        tob = row["tob"]
        if tob is None or int(tob.get("n", 0)) < 50:
            base["skip"] = "no_tob"
            day_rows.append(base)
            continue
        intens = quote_storm_intensity(
            tob["ts"], tob["bid"], tob["ask"], tob["bid_sz"], tob["ask_sz"], bar_s=1.0
        )
        # Crypto TOB cadence is sparse vs equity OE feeds — absolute Hz floors
        # from equity stuffing charts do not fire. Pass1 uses z vs *day* baseline
        # with min_intensity_hz=0; mid-range cap keeps price-discovery bursts out.
        storms_upd = quote_storm_detect(
            intens,
            z_thresh=3.0,
            min_cancel_frac=0.0,
            max_mid_range_bps=25.0,
            min_intensity_hz=0.0,
        )
        storms_sz = quote_storm_detect(
            intens,
            z_thresh=3.0,
            min_cancel_frac=0.25,
            max_mid_range_bps=25.0,
            min_intensity_hz=0.0,
            use_size_intensity=True,
        )
        sparse_tob = bool(float(np.nanmean(intens["intensity_hz"])) < 0.5) if intens["n_bars"] else True
        summ = quote_storm_summary(intens, storms_upd)
        summ_sz = quote_storm_summary(intens, storms_sz)
        # Draft overlap: storm bar mid-times vs cancel-proxy timestamps (native TOB only)
        lob_note: dict[str, Any] = {"skipped": True}
        if row["native_tob"]:
            ct = _cancel_proxy_ts(tob, row["tape"]["ts"], row["tape"]["side"], row["tape"]["qty"])
            storm_ts = np.asarray(storms_upd.get("ts", []), dtype=np.int64)
            if storm_ts.size and ct.size:
                # treat storm bars as 1s windows
                ov = overlap_vs_crash(
                    storm_ts,
                    storm_ts + 1_000_000_000,
                    ct,
                    ct + 50_000_000,
                    slack_s=1.0,
                    label="storm_vs_lob_cancel",
                )
                gate = rename_gate(ov, frac_key="frac_ignition_in_crash", kill_frac=0.85)
                lob_note = {"overlap": ov, "rename_gate": gate, "n_cancel_proxy": int(ct.size)}
            else:
                lob_note = {
                    "n_storms": int(storms_upd.get("n_events", 0)),
                    "n_cancel_proxy": int(ct.size),
                    "rename_gate": {"decision": "hold", "reason": "thin_overlap_sample"},
                }
        base.update(
            {
                "n_tob": int(tob.get("n", 0)),
                "n_bars": int(intens.get("n_bars", 0)),
                "sparse_tob": sparse_tob,
                "params": {
                    "z_thresh": 3.0,
                    "min_intensity_hz": 0.0,
                    "max_mid_range_bps": 25.0,
                    "note": "crypto-adapted; equity absolute-Hz floors would yield n=0 on warehouse TOB",
                },
                "summary_update": summ,
                "summary_size": summ_sz,
                "n_storms_update": int(storms_upd.get("n_events", 0)),
                "n_storms_size": int(storms_sz.get("n_events", 0)),
                "max_burst_vs_mean": float(storms_upd.get("max_burst_vs_mean", float("nan"))),
                "baseline_mean_hz": float(storms_upd.get("baseline_mean", float("nan"))),
                "storm_rate_per_hour": (
                    float(storms_upd.get("n_events", 0))
                    / max(float(row["completeness"].get("span_s", 0)) / 3600.0, 1e-6)
                ),
                "lob_cancel_draft": lob_note,
                "intensity_sample": {
                    "hz_p50": float(np.nanpercentile(intens["intensity_hz"], 50))
                    if intens["n_bars"]
                    else None,
                    "hz_p99": float(np.nanpercentile(intens["intensity_hz"], 99))
                    if intens["n_bars"]
                    else None,
                    "mean_cancel_frac": (
                        float(np.nanmean(intens["cancel_frac"]))
                        if intens["n_bars"] and np.isfinite(intens["cancel_frac"]).any()
                        else None
                    ),
                },
                # keep arrays for figs (per-venue first complete day later)
                "_intens": intens,
                "_storms_upd": storms_upd,
            }
        )
        day_rows.append(base)

    # Headlines pooled by venue (complete days only)
    headlines: dict[str, Any] = {}
    for venue in CORE_VENUES:
        sub = [
            r
            for r in day_rows
            if r["venue"] == venue and r.get("completeness", {}).get("complete") and "skip" not in r
        ]
        if not sub:
            headlines[venue] = {"n_days": 0, "blocker": "no_complete_days_with_tob"}
            continue
        n_storms = sum(int(r.get("n_storms_update", 0)) for r in sub)
        rates = [float(r.get("storm_rate_per_hour", float("nan"))) for r in sub]
        bursts = [float(r.get("max_burst_vs_mean", float("nan"))) for r in sub]
        headlines[venue] = {
            "n_days": len(sub),
            "n_storms_update_total": n_storms,
            "n_storms_size_total": sum(int(r.get("n_storms_size", 0)) for r in sub),
            "mean_storms_per_hour": float(np.nanmean(rates)),
            "median_max_burst_vs_mean": float(np.nanmedian(bursts)),
            "mean_baseline_hz": float(
                np.nanmean([r.get("baseline_mean_hz", float("nan")) for r in sub])
            ),
            "n_sparse_tob_days": sum(1 for r in sub if r.get("sparse_tob")),
            "days": [r["day"] for r in sub],
            "synth_days": [r["day"] for r in sub if r.get("is_trade_synth")],
        }

    # Figures
    _fig_storm_intensity(day_rows, figs / "fig_burst_intensity.png")
    _fig_storm_cancel(day_rows, figs / "fig_cancel_frac.png")
    _fig_storm_day_baseline(day_rows, figs / "fig_day_baseline.png")

    # Strip private arrays before JSON
    clean = []
    for r in day_rows:
        c = {k: v for k, v in r.items() if not k.startswith("_")}
        clean.append(c)

    payload = {
        "package": "quote_storms",
        "pass": 1,
        "symbol": rows[0]["symbol"] if rows else "ETH",
        "headlines": headlines,
        "day_rows": clean,
        "not_rename_of": "lob.tob_depletion_cancel_proxy / Nanex quote-rate vanity",
        "figs": [
            "figs/fig_burst_intensity.png",
            "figs/fig_cancel_frac.png",
            "figs/fig_day_baseline.png",
        ],
    }
    _json(out_dir / "pass1.json", payload)
    return payload


def _fig_storm_intensity(day_rows: list[dict[str, Any]], path: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), sharey=False)
    venues = list(CORE_VENUES)
    for ax, venue in zip(axes, venues):
        # prefer densest complete day (collector > sparse warehouse)
        pick = None
        cands = [
            r
            for r in day_rows
            if r["venue"] == venue and "_intens" in r and r.get("completeness", {}).get("complete")
        ]
        if cands:
            pick = max(cands, key=lambda r: int(r.get("n_tob", 0)))
        if pick is None:
            ax.set_title(f"{venue}\n(no data)")
            ax.axis("off")
            continue
        hz = np.asarray(pick["_intens"]["intensity_hz"], dtype=np.float64)
        ts = np.asarray(pick["_intens"]["ts"], dtype=np.int64)
        t0 = ts[0] if ts.size else 0
        hours = (ts - t0) / 1e9 / 3600.0
        ax.plot(hours, hz, lw=0.6, color="#1f4e79")
        storms = pick["_storms_upd"]
        if storms.get("n_events", 0):
            st = (np.asarray(storms["ts"]) - t0) / 1e9 / 3600.0
            ax.scatter(st, storms["intensity_hz"], s=18, c="#c0392b", zorder=3, label="storm")
        ax.axhline(pick.get("baseline_mean_hz", np.nan), color="#888", ls="--", lw=0.8)
        ax.set_title(f"{venue} · {pick['day']}")
        ax.set_xlabel("hours from start")
        ax.set_ylabel("TOB update Hz")
        if storms.get("n_events", 0):
            ax.legend(fontsize=7)
    fig.suptitle("Quote-storm intensity (1s bars) vs day baseline", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _fig_storm_cancel(day_rows: list[dict[str, Any]], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    labels, means, p99s = [], [], []
    for venue in CORE_VENUES:
        sub = [
            r
            for r in day_rows
            if r["venue"] == venue and "intensity_sample" in r and r.get("completeness", {}).get("complete")
        ]
        if not sub:
            continue
        labels.append(venue)
        cf = [r["intensity_sample"].get("mean_cancel_frac") for r in sub]
        cf = [float(x) for x in cf if x is not None and np.isfinite(x)]
        means.append(float(np.mean(cf)) if cf else float("nan"))
        p99 = [r["intensity_sample"].get("hz_p99") for r in sub]
        p99 = [float(x) for x in p99 if x is not None and np.isfinite(x)]
        p99s.append(float(np.mean(p99)) if p99 else float("nan"))
    x = np.arange(len(labels))
    ax.bar(x - 0.18, means, width=0.35, color="#2c5f2d", label="mean cancel_frac")
    ax2 = ax.twinx()
    ax2.bar(x + 0.18, p99s, width=0.35, color="#97c1a9", label="mean p99 Hz")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("mean cancel_frac (size flicker)")
    ax2.set_ylabel("p99 TOB update Hz")
    ax.set_title("Cancel fraction vs p99 intensity (complete days)")
    ax.legend(loc="upper left", fontsize=8)
    ax2.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _fig_storm_day_baseline(day_rows: list[dict[str, Any]], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 3.8))
    for venue, color in zip(CORE_VENUES, ("#1f4e79", "#c0392b", "#6c3483")):
        sub = [
            r
            for r in day_rows
            if r["venue"] == venue and "n_storms_update" in r and r.get("completeness", {}).get("complete")
        ]
        if not sub:
            continue
        days = [r["day"][-5:] for r in sub]
        rates = [r.get("storm_rate_per_hour", np.nan) for r in sub]
        ax.plot(days, rates, marker="o", label=venue, color=color)
    ax.set_ylabel("storms / hour (z≥3 update Hz)")
    ax.set_xlabel("UTC day")
    ax.set_title("Storm rate vs day (crypto z-baseline; sparse TOB → often 0)")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Book fade
# ---------------------------------------------------------------------------


def run_book_fade(
    rows: list[dict[str, Any]],
    out_dir: Path,
    *,
    max_trades: int = 8_000,
    tau_ms_grid: tuple[float, ...] = (50.0, 100.0, 250.0),
) -> dict[str, Any]:
    figs = out_dir / "figs"
    figs.mkdir(parents=True, exist_ok=True)
    day_rows: list[dict[str, Any]] = []

    for row in rows:
        venue, day = row["venue"], row["day"]
        base: dict[str, Any] = {
            "venue": venue,
            "day": day,
            "completeness": row["completeness"],
            "tob_ok": row["tob_ok"],
            "tob_source": row["tob_source"],
            "is_trade_synth": row["is_trade_synth"],
            "native_tob": row["native_tob"],
            "note_not_lob_rename": (
                "price_fade_* = P(same-side depth↓ | aggressor) within τ — "
                "post-trade conditional. Not lob.tob_depletion_cancel_proxy "
                "(unconditional same-price size-drop)."
            ),
            "kraken_trade_synth_excluded": bool(row["is_trade_synth"]),
        }
        tob = row["tob"]
        tape = row["tape"]
        if tob is None or tape["ts"].size < 100:
            base["skip"] = "no_tob_or_thin_tape"
            day_rows.append(base)
            continue

        # Native TOB fade only — exclude Kraken trade_synth (and any synth)
        if row["is_trade_synth"]:
            base["skip"] = "trade_synth_excluded_from_native_tob_fade"
            base["p_fade_native"] = None
            day_rows.append(base)
            continue
        if not row["native_tob"]:
            base["skip"] = "non_native_tob"
            day_rows.append(base)
            continue

        idx = _subsample(int(tape["ts"].size), max_trades)
        tt = tape["ts"][idx]
        side = tape["side"][idx]
        qty = tape["qty"][idx]

        tau_probs: dict[str, Any] = {}
        primary = None
        for tau in tau_ms_grid:
            ev = price_fade_events(
                tt, side, tob["ts"], tob["bid"], tob["ask"], tob["bid_sz"], tob["ask_sz"],
                tau_ms=tau, drop_frac=0.2,
            )
            pr = price_fade_prob(ev)
            tau_probs[str(tau)] = pr
            if abs(tau - 100.0) < 1e-9:
                primary = (ev, pr)

        # Draft overlap vs lob cancel_proxy
        lob_note: dict[str, Any] = {}
        if primary is not None:
            ev, pr = primary
            ct = _cancel_proxy_ts(tob, tape["ts"], tape["side"], tape["qty"])
            fade_ts = tt[np.asarray(ev["trade_i"], dtype=np.int64)] if ev["n_trades"] else np.zeros(0, dtype=np.int64)
            from research.lib.hftpat import overlap_vs_lob_cancel

            ov = overlap_vs_lob_cancel(fade_ts, ev["fade"], ct, slack_ms=250.0)
            gate = rename_gate(ov, frac_key="frac_fade_in_cancel", kill_frac=0.85)
            lob_note = {"overlap": ov, "rename_gate": gate}

        base.update(
            {
                "n_trades_scored": int(idx.size),
                "n_trades_day": int(tape["ts"].size),
                "tau_probs": tau_probs,
                "p_fade_100ms": (primary[1] if primary else {}).get("p_fade"),
                "n_fade_100ms": (primary[0] if primary else {}).get("n_fade"),
                "lob_cancel_draft": lob_note,
                "_tau_probs": tau_probs,
            }
        )
        day_rows.append(base)

    # Venue-fade: HL home trades → Deribit far (same day), when both native
    venue_fade_rows: list[dict[str, Any]] = []
    by_day: dict[str, dict[str, dict[str, Any]]] = {}
    for r in rows:
        by_day.setdefault(r["day"], {})[r["venue"]] = r
    for day, venue_map in sorted(by_day.items()):
        home = venue_map.get("hyperliquid")
        far = venue_map.get("deribit")
        if not home or not far:
            continue
        if not home.get("native_tob") or not far.get("native_tob"):
            venue_fade_rows.append(
                {
                    "day": day,
                    "home": "hyperliquid",
                    "far": "deribit",
                    "skip": "need_native_tob_both",
                    "home_synth": home.get("is_trade_synth"),
                    "far_synth": far.get("is_trade_synth"),
                }
            )
            continue
        if not home.get("completeness", {}).get("complete"):
            venue_fade_rows.append({"day": day, "skip": "home_incomplete"})
            continue
        ht = home["tape"]
        ftob = far["tob"]
        idx = _subsample(int(ht["ts"].size), max_trades)
        ev = venue_fade_events(
            ht["ts"][idx],
            ht["side"][idx],
            ftob["ts"],
            ftob["bid"],
            ftob["ask"],
            ftob["bid_sz"],
            ftob["ask_sz"],
            tau_ms=50.0,
            latency_ms=5.0,
            drop_frac=0.2,
        )
        pr = venue_fade_prob(ev)
        venue_fade_rows.append(
            {
                "day": day,
                "home": "hyperliquid",
                "far": "deribit",
                "latency_ms": 5.0,
                "tau_ms": 50.0,
                "n_scored": int(ev.get("n_trades", 0)),
                "p_fade": pr.get("p_fade"),
                "p_fade_buy": pr.get("p_fade_buy"),
                "p_fade_sell": pr.get("p_fade_sell"),
                "completeness_home": home["completeness"],
                "completeness_far": far["completeness"],
            }
        )

    headlines: dict[str, Any] = {}
    for venue in CORE_VENUES:
        sub = [
            r
            for r in day_rows
            if r["venue"] == venue
            and r.get("completeness", {}).get("complete")
            and r.get("p_fade_100ms") is not None
        ]
        excl = [
            r
            for r in day_rows
            if r["venue"] == venue and r.get("kraken_trade_synth_excluded")
        ]
        if not sub:
            headlines[venue] = {
                "n_days_native": 0,
                "blocker": "no_native_fade"
                if venue == "kraken" or excl
                else "no_complete_native_tob",
                "n_trade_synth_excluded": len(excl),
            }
            continue
        ps = [float(r["p_fade_100ms"]) for r in sub]
        headlines[venue] = {
            "n_days_native": len(sub),
            "p_fade_100ms_mean": float(np.nanmean(ps)),
            "p_fade_100ms_median": float(np.nanmedian(ps)),
            "n_fade_total": int(sum(int(r.get("n_fade_100ms") or 0) for r in sub)),
            "n_trades_scored_total": int(sum(int(r.get("n_trades_scored") or 0) for r in sub)),
            "days": [r["day"] for r in sub],
            "n_trade_synth_excluded": len(excl),
        }

    vf_ok = [r for r in venue_fade_rows if r.get("p_fade") is not None]
    headlines["venue_fade_hl_to_db"] = {
        "n_days": len(vf_ok),
        "p_fade_mean": float(np.nanmean([r["p_fade"] for r in vf_ok])) if vf_ok else None,
        "latency_ms": 5.0,
        "tau_ms": 50.0,
    }

    _fig_fade_tau(day_rows, figs / "fig_fade_p_tau.png")
    _fig_fade_venue_bars(headlines, figs / "fig_fade_venue_bars.png")
    _fig_venue_fade(venue_fade_rows, figs / "fig_venue_fade.png")

    clean = [{k: v for k, v in r.items() if not k.startswith("_")} for r in day_rows]
    payload = {
        "package": "book_fade",
        "pass": 1,
        "symbol": rows[0]["symbol"] if rows else "ETH",
        "headlines": headlines,
        "day_rows": clean,
        "venue_fade": venue_fade_rows,
        "not_rename_of": "lob.tob_depletion_cancel_proxy",
        "kraken_note": "Kraken trade_synth TOB excluded from native same-venue fade tests",
        "figs": [
            "figs/fig_fade_p_tau.png",
            "figs/fig_fade_venue_bars.png",
            "figs/fig_venue_fade.png",
        ],
    }
    _json(out_dir / "pass1.json", payload)
    return payload


def _fig_fade_tau(day_rows: list[dict[str, Any]], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    for venue, color in zip(CORE_VENUES, ("#1f4e79", "#c0392b", "#6c3483")):
        sub = [
            r
            for r in day_rows
            if r["venue"] == venue and r.get("tau_probs") and r.get("completeness", {}).get("complete")
        ]
        if not sub:
            continue
        taus = sorted(float(t) for t in sub[0]["tau_probs"].keys())
        means = []
        for t in taus:
            ps = [r["tau_probs"][str(t)]["p_fade"] for r in sub if str(t) in r["tau_probs"]]
            means.append(float(np.nanmean(ps)) if ps else np.nan)
        ax.plot(taus, means, marker="o", label=venue, color=color)
    ax.set_xlabel("τ (ms)")
    ax.set_ylabel("P(fade | aggressor)")
    ax.set_title("Same-venue price fade vs τ (native TOB; synth excluded)")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _fig_fade_venue_bars(headlines: dict[str, Any], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 3.6))
    labels, vals, ns = [], [], []
    for venue in CORE_VENUES:
        h = headlines.get(venue, {})
        labels.append(venue if h.get("n_days_native") else f"{venue}\n(excl/synth)")
        vals.append(h.get("p_fade_100ms_mean", np.nan) if h.get("n_days_native") else np.nan)
        ns.append(h.get("n_trades_scored_total", 0) or 0)
    x = np.arange(len(labels))
    bars = ax.bar(x, vals, color=["#1f4e79", "#c0392b", "#97c1a9"])
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("mean P(fade) @ 100ms")
    ax.set_title("Native TOB price-fade probability (complete days)")
    for b, n in zip(bars, ns):
        if np.isfinite(b.get_height()):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.01, f"n={n}", ha="center", fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _fig_venue_fade(venue_fade_rows: list[dict[str, Any]], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ok = [r for r in venue_fade_rows if r.get("p_fade") is not None]
    if not ok:
        ax.text(0.5, 0.5, "No venue-fade days\n(need HL+DB native TOB)", ha="center", va="center")
        ax.axis("off")
    else:
        days = [r["day"][-5:] for r in ok]
        ps = [r["p_fade"] for r in ok]
        ax.bar(days, ps, color="#1f4e79")
        ax.set_ylabel("P(far fade | home trade)")
        ax.set_title("Venue fade: HL trade → Deribit depth (lat=5ms, τ=50ms)")
        ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Momentum ignition
# ---------------------------------------------------------------------------


def run_momentum_ignition(rows: list[dict[str, Any]], out_dir: Path) -> dict[str, Any]:
    figs = out_dir / "figs"
    figs.mkdir(parents=True, exist_ok=True)
    day_rows: list[dict[str, Any]] = []

    for row in rows:
        venue, day = row["venue"], row["day"]
        tape = row["tape"]
        base: dict[str, Any] = {
            "venue": venue,
            "day": day,
            "completeness": row["completeness"],
            "n_trades": int(tape["ts"].size),
            "note_not_nanex_rename": (
                "ignition_events requires Phase1 (elevated vol, quiet mid) before "
                "move+partial recovery — distinct from crash Nanex/SSM / vshape geometry."
            ),
        }
        if tape["ts"].size < 500:
            base["skip"] = "thin_tape"
            day_rows.append(base)
            continue

        ts = tape["ts"]
        px = tape["px"]
        qty = tape["qty"]
        # Crypto trade bars: equity-tight quiet-mid (2–3 bps) + 15 bps moves
        # yield n≈0 on ETH days. Pass1 uses looser but still 3-phase fingerprint;
        # document params — Promote still gated on Phase1 unique mass vs Nanex/V.
        ign = ignition_events(
            ts,
            px,
            qty,
            bar_s=1.0,
            phase1_bars=3,
            phase2_bars=3,
            phase3_bars=5,
            vol_z=1.0,
            mid_quiet_bps=15.0,
            move_bps=5.0,
            min_recovery=0.15,
        )
        ign_s, ign_e = ignition_bar_timestamps(ign)

        # Competing defs — slightly looser than equity 0.8% so crypto days produce
        # a non-empty comparison set; still geometric move tags (not 3-phase).
        nanex = nanex_detect(
            ts, px, min_trades=8, max_window_s=2.0, min_pct=0.001, use_trade_count=True
        )
        vsh = vshape_events(ts, px, min_pct=0.001, max_leg_s=3.0, min_recovery=0.3)

        nanex_s = ts[nanex["start_i"]] if nanex["n_events"] else np.zeros(0, dtype=np.int64)
        nanex_e = ts[nanex["end_i"]] if nanex["n_events"] else np.zeros(0, dtype=np.int64)
        v_s = ts[vsh["start_i"]] if vsh["n_events"] else np.zeros(0, dtype=np.int64)
        v_e = ts[vsh["end_i"]] if vsh["n_events"] else np.zeros(0, dtype=np.int64)

        ov_nanex = overlap_vs_crash(ign_s, ign_e, nanex_s, nanex_e, slack_s=2.0, label="nanex")
        ov_v = overlap_vs_crash(ign_s, ign_e, v_s, v_e, slack_s=2.0, label="vshape")
        # Empty competing set → frac=0 (no rename evidence), not NaN
        for ov, n_comp in ((ov_nanex, int(nanex["n_events"])), (ov_v, int(vsh["n_events"]))):
            if n_comp == 0 and int(ov.get("n_ignition", 0)) > 0:
                ov["frac_ignition_in_crash"] = 0.0
                ov["frac_crash_in_ignition"] = float("nan")
                ov["jaccard"] = 0.0
                ov["note"] = "empty_competing_set_at_thresholds"
        gate_nanex = rename_gate(ov_nanex, frac_key="frac_ignition_in_crash", kill_frac=0.85)
        gate_v = rename_gate(ov_v, frac_key="frac_ignition_in_crash", kill_frac=0.85)

        # Optional SSM (may be dense / expensive — try/catch)
        ssm_note: dict[str, Any] = {}
        try:
            mcg = mc_garch_bar_vol(ts, px)
            log_px = np.log(np.where(px > 0, px, np.nan))
            sig = sigma_process_meas(ts, mcg, sigma_m_frac=1.0, log_px=log_px)
            filt = kalman_ssm_filter(ts, px, sig["sigma_p2_dt"], sig["sigma_m2"])
            ssm = detect_ssm_events(ts, px, filt, z_star=6.0)
            if ssm["n_events"]:
                ssm_s = ts[ssm["start_i"]]
                ssm_e = ts[ssm["end_i"]]
            else:
                ssm_s = ssm_e = np.zeros(0, dtype=np.int64)
            ov_ssm = overlap_vs_crash(ign_s, ign_e, ssm_s, ssm_e, slack_s=2.0, label="ssm")
            gate_ssm = rename_gate(ov_ssm, frac_key="frac_ignition_in_crash", kill_frac=0.85)
            ssm_note = {
                "n_ssm": int(ssm["n_events"]),
                "overlap": ov_ssm,
                "rename_gate": gate_ssm,
            }
        except Exception as exc:  # noqa: BLE001
            ssm_note = {"error": f"{type(exc).__name__}: {exc}"}

        # Promote-only-if-prephase adds info: draft decision Hold if n small or overlap high
        decision = "Hold"
        reason = "pass1_draft"
        n_ign = int(ign.get("n_events", 0))
        if n_ign == 0:
            reason = "zero_events"
        elif gate_nanex["decision"] == "kill_rename" or gate_v["decision"] == "kill_rename":
            decision = "Hold"  # Pass1 may Hold; Pass2 Kill if rename confirmed
            reason = "high_overlap_vs_crash_geometry"
        elif float(ov_nanex.get("frac_ignition_in_crash") or 0) < 0.5 and n_ign >= 3:
            decision = "Hold"
            reason = "prephase_may_add_info_needs_pass2_falsifier"

        moves = np.asarray(ign.get("move_bps", []), dtype=np.float64)
        recs = np.asarray(ign.get("recovery", []), dtype=np.float64)
        durs = (
            (ign_e - ign_s) / 1e9
            if ign_s.size
            else np.zeros(0, dtype=np.float64)
        )
        base.update(
            {
                "n_ignition": n_ign,
                "params": {
                    "bar_s": 1.0,
                    "phase_bars": [3, 3, 5],
                    "vol_z": 1.0,
                    "mid_quiet_bps": 15.0,
                    "move_bps": 5.0,
                    "min_recovery": 0.15,
                    "note": "crypto-loosened vs equity deck cartoon; Hold pending Pass2",
                },
                "mean_move_bps": float(np.nanmean(moves)) if moves.size else None,
                "mean_recovery": float(np.nanmean(recs)) if recs.size else None,
                "mean_duration_s": float(np.nanmean(durs)) if durs.size else None,
                "n_nanex": int(nanex["n_events"]),
                "n_vshape": int(vsh["n_events"]),
                "overlap_table": {
                    "vs_nanex": ov_nanex,
                    "vs_vshape": ov_v,
                    "vs_ssm": ssm_note,
                },
                "rename_gates": {"nanex": gate_nanex, "vshape": gate_v, "ssm": ssm_note.get("rename_gate")},
                "draft_decision": decision,
                "draft_reason": reason,
                "_ign": ign,
                "_ign_s": ign_s,
                "_ign_e": ign_e,
                "_px": px,
                "_ts": ts,
            }
        )
        day_rows.append(base)

    headlines: dict[str, Any] = {}
    overlap_rollup: list[dict[str, Any]] = []
    for venue in CORE_VENUES:
        sub = [
            r
            for r in day_rows
            if r["venue"] == venue and r.get("completeness", {}).get("complete") and "n_ignition" in r
        ]
        if not sub:
            headlines[venue] = {"n_days": 0, "blocker": "no_complete_days"}
            continue
        n_ign = sum(int(r.get("n_ignition", 0)) for r in sub)
        # pooled frac: mean of day fracs weighted by n_ignition
        fracs_n, fracs_v = [], []
        for r in sub:
            ovn = r.get("overlap_table", {}).get("vs_nanex", {})
            ovv = r.get("overlap_table", {}).get("vs_vshape", {})
            if r.get("n_ignition", 0) > 0 and np.isfinite(ovn.get("frac_ignition_in_crash", np.nan)):
                fracs_n.append(float(ovn["frac_ignition_in_crash"]))
            if r.get("n_ignition", 0) > 0 and np.isfinite(ovv.get("frac_ignition_in_crash", np.nan)):
                fracs_v.append(float(ovv["frac_ignition_in_crash"]))
        headlines[venue] = {
            "n_days": len(sub),
            "n_ignition_total": n_ign,
            "mean_move_bps": (
                float(
                    np.nanmean(
                        [
                            r["mean_move_bps"]
                            for r in sub
                            if r.get("mean_move_bps") is not None
                            and np.isfinite(r.get("mean_move_bps", np.nan))
                        ]
                    )
                )
                if any(
                    r.get("mean_move_bps") is not None
                    and np.isfinite(r.get("mean_move_bps", np.nan))
                    for r in sub
                )
                else None
            ),
            "mean_frac_in_nanex": float(np.nanmean(fracs_n)) if fracs_n else None,
            "mean_frac_in_vshape": float(np.nanmean(fracs_v)) if fracs_v else None,
            "draft_decision": "Hold",
            "days": [r["day"] for r in sub],
        }
        for r in sub:
            overlap_rollup.append(
                {
                    "venue": venue,
                    "day": r["day"],
                    "n_ignition": r.get("n_ignition"),
                    "n_nanex": r.get("n_nanex"),
                    "n_vshape": r.get("n_vshape"),
                    "frac_ign_in_nanex": r.get("overlap_table", {}).get("vs_nanex", {}).get(
                        "frac_ignition_in_crash"
                    ),
                    "frac_ign_in_vshape": r.get("overlap_table", {}).get("vs_vshape", {}).get(
                        "frac_ignition_in_crash"
                    ),
                    "jaccard_nanex": r.get("overlap_table", {}).get("vs_nanex", {}).get("jaccard"),
                    "gate_nanex": r.get("rename_gates", {}).get("nanex", {}).get("decision"),
                    "gate_vshape": r.get("rename_gates", {}).get("vshape", {}).get("decision"),
                }
            )

    _fig_ignition_counts(day_rows, figs / "fig_ignition_counts.png")
    _fig_ignition_dists(day_rows, figs / "fig_ignition_move_recovery.png")
    _fig_overlap_table(overlap_rollup, figs / "fig_overlap_table.png")

    clean = [{k: v for k, v in r.items() if not k.startswith("_")} for r in day_rows]
    payload = {
        "package": "momentum_ignition",
        "pass": 1,
        "symbol": rows[0]["symbol"] if rows else "ETH",
        "headlines": headlines,
        "day_rows": clean,
        "overlap_rollup": overlap_rollup,
        "not_rename_of": "crash.nanex_detect / SSM / vshape_events / vstat.min_v",
        "promote_rule": "Promote only if Phase1 pre-phase adds info beyond crash tags; Pass1 → Hold",
        "figs": [
            "figs/fig_ignition_counts.png",
            "figs/fig_ignition_move_recovery.png",
            "figs/fig_overlap_table.png",
        ],
    }
    _json(out_dir / "pass1.json", payload)
    _json(out_dir / "overlap_draft.json", {"rows": overlap_rollup, "headlines": headlines})
    return payload


def _fig_ignition_counts(day_rows: list[dict[str, Any]], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 3.8))
    width = 0.25
    days_all = sorted({r["day"] for r in day_rows if r.get("completeness", {}).get("complete")})
    x = np.arange(len(days_all))
    for i, (venue, color) in enumerate(zip(CORE_VENUES, ("#1f4e79", "#c0392b", "#6c3483"))):
        vals = []
        for d in days_all:
            hit = next(
                (r for r in day_rows if r["venue"] == venue and r["day"] == d and "n_ignition" in r),
                None,
            )
            vals.append(hit.get("n_ignition", 0) if hit else 0)
        ax.bar(x + (i - 1) * width, vals, width=width, label=venue, color=color)
    ax.set_xticks(x)
    ax.set_xticklabels([d[-5:] for d in days_all])
    ax.set_ylabel("n ignition events")
    ax.set_title("Momentum-ignition counts (complete UTC days)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _fig_ignition_dists(day_rows: list[dict[str, Any]], path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6))
    moves, recs = [], []
    for r in day_rows:
        if not r.get("completeness", {}).get("complete"):
            continue
        ign = r.get("_ign")
        if not ign or not ign.get("n_events"):
            continue
        moves.extend(list(np.asarray(ign["move_bps"], dtype=np.float64)))
        recs.extend(list(np.asarray(ign["recovery"], dtype=np.float64)))
    axes[0].hist(moves, bins=20, color="#1f4e79", alpha=0.85)
    axes[0].set_title("Phase2 |move| (bps)")
    axes[0].set_xlabel("bps")
    axes[1].hist(recs, bins=20, color="#2c5f2d", alpha=0.85)
    axes[1].set_title("Phase3 recovery fraction")
    axes[1].set_xlabel("recovered / move")
    if not moves:
        axes[0].text(0.5, 0.5, "n=0", ha="center", transform=axes[0].transAxes)
        axes[1].text(0.5, 0.5, "n=0", ha="center", transform=axes[1].transAxes)
    fig.suptitle("Ignition move / recovery distributions (pooled complete days)")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _fig_overlap_table(rollup: list[dict[str, Any]], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, max(2.5, 0.35 * len(rollup) + 1.2)))
    ax.axis("off")
    if not rollup:
        ax.text(0.5, 0.5, "No overlap rows", ha="center")
    else:
        cols = [
            "venue",
            "day",
            "n_ign",
            "n_nanex",
            "n_v",
            "frac∩nanex",
            "frac∩v",
            "gate_n",
            "gate_v",
        ]
        cell = []
        for r in rollup:
            def fmt(x: Any) -> str:
                if x is None:
                    return "—"
                try:
                    xf = float(x)
                    if not np.isfinite(xf):
                        return "—"
                    return f"{xf:.2f}"
                except (TypeError, ValueError):
                    return str(x)

            cell.append(
                [
                    r.get("venue", ""),
                    str(r.get("day", ""))[-5:],
                    str(r.get("n_ignition", "")),
                    str(r.get("n_nanex", "")),
                    str(r.get("n_vshape", "")),
                    fmt(r.get("frac_ign_in_nanex")),
                    fmt(r.get("frac_ign_in_vshape")),
                    str(r.get("gate_nanex") or "—"),
                    str(r.get("gate_vshape") or "—"),
                ]
            )
        table = ax.table(cellText=cell, colLabels=cols, loc="center", cellLoc="center")
        table.auto_set_font_size(False)
        table.set_fontsize(7)
        table.scale(1.0, 1.25)
        ax.set_title(
            "Draft overlap: ignition vs Nanex / vshape (Pass1 — Promote only if pre-phase adds info)",
            fontsize=9,
            pad=12,
        )
    fig.tight_layout()
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Chapter markdown writers
# ---------------------------------------------------------------------------


def write_chapter_docs(
    storm: dict[str, Any],
    fade: dict[str, Any],
    ign: dict[str, Any],
    *,
    days: list[str],
    symbol: str,
) -> None:
    # --- quote_storms ---
    hs = storm["headlines"]
    lines_qs = [
        "# Quote storms — EXP_REPORT",
        "",
        "## Pass 1",
        f"- Slice: **{symbol}** · HL + Deribit + Kraken · days `{days}`",
        "- Detector: `hftpat.quote_storm_intensity` / `quote_storm_detect` (1s bars, z≥3 update-Hz; min_hz=0 crypto-adapted)",
        "- Sparse warehouse TOB (mean Hz < 0.5) flagged; collector day (HL 09-30) carries most storm mass.",
        "- **Not a rename** of `lob.tob_depletion_cancel_proxy` (burst intensity vs unconditional cancel class) "
        "nor equity Nanex quote-rate vanity.",
        "",
        "### Headlines (complete days)",
    ]
    for v in CORE_VENUES:
        h = hs.get(v, {})
        if h.get("n_days"):
            lines_qs.append(
                f"- **{v}**: storms/hour={h.get('mean_storms_per_hour'):.3g}, "
                f"n_storms={h.get('n_storms_update_total')}, "
                f"median max_burst/mean={h.get('median_max_burst_vs_mean'):.3g}, "
                f"baseline Hz={h.get('mean_baseline_hz'):.3g}, n_days={h.get('n_days')}"
            )
        else:
            lines_qs.append(f"- **{v}**: blocker={h.get('blocker')}")
    n_complete = sum(
        1
        for r in storm["day_rows"]
        if r.get("completeness", {}).get("complete")
    )
    n_all = len(storm["day_rows"])
    lines_qs += [
        "",
        f"### Completeness",
        f"- Day×venue rows: {n_all}; complete: {n_complete}. Incomplete days flagged in `out/quote_storms/pass1.json`.",
        "",
        "### Figures",
        "- `out/quote_storms/figs/fig_burst_intensity.png`",
        "- `out/quote_storms/figs/fig_cancel_frac.png`",
        "- `out/quote_storms/figs/fig_day_baseline.png`",
        "",
        "## Pass 2 (pending)",
        "- Storm→spread / adverse selection join; harden lob-cancel overlap gate; exec-throttle candidacy.",
    ]
    (CH / "quote_storms" / "EXP_REPORT.md").write_text("\n".join(lines_qs) + "\n")

    (CH / "quote_storms" / "CANDIDATES.md").write_text(
        "\n".join(
            [
                "| id | type | lenses | decision | falsifier |",
                "|----|------|--------|----------|----------|",
                "| `risk.quote_storm_burst` | monitor / exec throttle | risk, exec | **Hold** | Pass1 baseline only; "
                "day-block bootstrap + lob-cancel rename gate in Pass2; not Promote on thin incomplete days |",
                "| `risk.quote_storm_vs_lob` | competing-def | risk, liq | **Hold** | Draft overlap in pass1.json; "
                "Kill if storm bars ⊆ lob cancel_proxy timestamps |",
                "",
                "**Explicit:** not a rename of `lob.tob_depletion_cancel_proxy` or Nanex equity quote-rate charts.",
                "",
            ]
        )
    )

    # --- book_fade ---
    hf = fade["headlines"]
    lines_bf = [
        "# Book fade — EXP_REPORT",
        "",
        "## Pass 1",
        f"- Slice: **{symbol}** · HL + Deribit + Kraken · days `{days}`",
        "- Detector: `hftpat.price_fade_*` (τ∈{50,100,250}ms, θ=0.2); `venue_fade_*` HL→DB lat=5ms τ=50ms",
        "- **Kraken `trade_synth` excluded** from native TOB fade tests (labeled in JSON).",
        "- **Not a rename** of `lob.tob_depletion_cancel_proxy` (post-trade conditional ≠ unconditional size-drop).",
        "",
        "### Headlines (native TOB, complete days)",
    ]
    for v in CORE_VENUES:
        h = hf.get(v, {})
        if h.get("n_days_native"):
            lines_bf.append(
                f"- **{v}**: P(fade)@100ms mean={h.get('p_fade_100ms_mean'):.3g}, "
                f"n_fade={h.get('n_fade_total')}, n_scored={h.get('n_trades_scored_total')}, "
                f"n_days={h.get('n_days_native')}"
            )
        else:
            lines_bf.append(
                f"- **{v}**: blocker={h.get('blocker')}; "
                f"trade_synth_excluded_days={h.get('n_trade_synth_excluded', 0)}"
            )
    vf = hf.get("venue_fade_hl_to_db", {})
    lines_bf += [
        "",
        f"- **Venue fade HL→DB**: P(fade) mean={vf.get('p_fade_mean')}, n_days={vf.get('n_days')} "
        f"(lat={vf.get('latency_ms')}ms, τ={vf.get('tau_ms')}ms)",
        "",
        "### Figures",
        "- `out/book_fade/figs/fig_fade_p_tau.png`",
        "- `out/book_fade/figs/fig_fade_venue_bars.png`",
        "- `out/book_fade/figs/fig_venue_fade.png`",
        "",
        "## Pass 2 (pending)",
        "- Markout after fade; τ grid harden; lob-cancel overlap Kill threshold.",
    ]
    (CH / "book_fade" / "EXP_REPORT.md").write_text("\n".join(lines_bf) + "\n")

    (CH / "book_fade" / "CANDIDATES.md").write_text(
        "\n".join(
            [
                "| id | type | lenses | decision | falsifier |",
                "|----|------|--------|----------|----------|",
                "| `risk.price_fade_p` | risk / MM pull | risk, mm, liq | **Hold** | Pass1 P(fade) baseline; "
                "Pass2 markout + early/late; Kill if rename of lob cancel_proxy |",
                "| `risk.venue_fade_hl_db` | SOR / xvenue risk | risk, exec | **Hold** | RTT assumption (5ms) stated; "
                "needs more synced native days + haircut |",
                "| `risk.fade_vs_lob_cancel` | competing-def | risk, liq | **Hold** | Draft `overlap_vs_lob_cancel` in pass1; "
                "Kraken synth excluded from native tests |",
                "",
                "**Explicit:** not a rename of `lob.tob_depletion_cancel_proxy`.",
                "**Kraken:** `trade_synth` TOB excluded from native same-venue fade.",
                "",
            ]
        )
    )

    # --- momentum_ignition ---
    hi = ign["headlines"]
    lines_mi = [
        "# Momentum ignition — EXP_REPORT",
        "",
        "## Pass 1",
        f"- Slice: **{symbol}** · HL + Deribit + Kraken · days `{days}`",
        "- Detector: `hftpat.ignition_events` (3-phase vol↑ quiet-mid → move → partial recovery)",
        "- Overlap draft: `overlap_vs_crash` vs Nanex / vshape / SSM + `rename_gate`",
        "- **Not a rename** of Nanex/SSM/V or `vstat.min_v`. Promote only if Phase1 adds info — **Pass1 → Hold**.",
        "",
        "### Headlines (complete days)",
    ]
    for v in CORE_VENUES:
        h = hi.get(v, {})
        if h.get("n_days"):
            lines_mi.append(
                f"- **{v}**: n_ignition={h.get('n_ignition_total')}, "
                f"mean |move| bps={h.get('mean_move_bps')}, "
                f"mean frac∩Nanex={h.get('mean_frac_in_nanex')}, "
                f"mean frac∩vshape={h.get('mean_frac_in_vshape')}, "
                f"decision={h.get('draft_decision')}"
            )
        else:
            lines_mi.append(f"- **{v}**: blocker={h.get('blocker')}")
    lines_mi += [
        "",
        "### Overlap table",
        "- See `out/momentum_ignition/overlap_draft.json` and `figs/fig_overlap_table.png`",
        "",
        "### Figures",
        "- `out/momentum_ignition/figs/fig_ignition_counts.png`",
        "- `out/momentum_ignition/figs/fig_ignition_move_recovery.png`",
        "- `out/momentum_ignition/figs/fig_overlap_table.png`",
        "",
        "## Pass 2 (pending)",
        "- Mandatory harden overlap vs Nanex∩SSM / V; Phase1 unique-mass test; day-block bootstrap.",
    ]
    (CH / "momentum_ignition" / "EXP_REPORT.md").write_text("\n".join(lines_mi) + "\n")

    (CH / "momentum_ignition" / "CANDIDATES.md").write_text(
        "\n".join(
            [
                "| id | type | lenses | decision | falsifier |",
                "|----|------|--------|----------|----------|",
                "| `risk.momentum_ignition_3phase` | escalate vs plain crash | risk, info | **Hold** | "
                "Pass1 draft; Promote only if Phase1 quiet-mid high-vol adds mass beyond Nanex/SSM/V |",
                "| `risk.ignition_vs_nanex_vshape` | competing-def / rename gate | risk | **Hold** | "
                "`rename_gate` on overlap_vs_crash; Kill if frac_ignition_in_crash ≥ 0.85 and n_ov≥3 |",
                "",
                "**Explicit:** not a rename of `crash.nanex_detect` / SSM / `vshape_events` / `vstat.min_v`.",
                "",
            ]
        )
    )


def write_notes_pass1() -> None:
    """Fill Pass-1 checklist + deck cites in NOTES (do not touch other packages)."""
    qs = CH / "quote_storms" / "NOTES.md"
    qs.write_text(
        """# Quote storms (stuffing bursts)

**Book:** Filimonov, Perm Winter School 2013  
**PDF:** slides (local) · **Status:** `pass1`  
**Raw:** [`../../_raw/`](../../_raw/) (local/gitignored)  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md)  
**Lib:** [`../../../../lib/hftpat.py`](../../../../lib/hftpat.py) · `quote_storm_*`

---

## Pass 1 focus

Burst detectors: adds+cancels/s proxies, cancel fraction, max burst vs day baseline (deck slides **27–29**).

### Deck citations
- Slides **27–29**: quote stuffing / flickering quotes — bursts of adds+cancels with little price discovery; intensity vs quieter baseline.
- Crypto map: L0 TOB update Hz + same-price size↑/↓ as add/cancel proxies (no firm IDs / OE message types).

### Not a rename
- **Not** `lob.tob_depletion_cancel_proxy` (unconditional same-price size-drop class).
- **Not** equity Nanex quote-rate vanity charts.

## Pass 2 dig

Storm→spread / adverse selection join; overlap vs `lob.tob_depletion_cancel_proxy`; exec-throttle candidacy.

## Pass checklist

### Pass 1
- [x] Cite deck pages in NOTES
- [x] Implement on HL + Deribit + Kraken
- [x] EXP_REPORT with day-completeness
- [x] Draft CANDIDATES

### Pass 2
- [ ] Overlap gate vs lob cancel proxy (Kill if rename)
- [ ] Signal board → DESK_MEMO
"""
    )

    bf = CH / "book_fade" / "NOTES.md"
    bf.write_text(
        """# Book fade (price / venue)

**Book:** Filimonov, Perm Winter School 2013  
**PDF:** slides (local) · **Status:** `pass1`  
**Raw:** [`../../_raw/`](../../_raw/) (local/gitignored)  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md)  
**Lib:** [`../../../../lib/hftpat.py`](../../../../lib/hftpat.py) · `price_fade_*` · `venue_fade_*`

---

## Pass 1 focus

Same-venue price fade event study; venue-fade when xvenue sync allows (deck slide **33**).

### Deck citations
- Slide **33**: liquidity fade after aggressor trade — same-side depth pulled within a short horizon; cross-venue analogue when latency-aligned.
- Crypto map: P(same-side TOB depth↓ > θ within τ | aggressor) on native TOB; far-venue fade = HL trade → Deribit depth (lat=5ms assumption stated in EXP_REPORT).

### Not a rename
- **Not** `lob.tob_depletion_cancel_proxy` — fade is **post-trade conditional**; lob cancel is unconditional size-drop classification.

### Kraken
- Collector/warehouse rows with source containing **`trade_synth`** are **excluded** from native same-venue TOB fade tests (labeled in JSON / EXP_REPORT).

## Pass 2 dig

Markout after fade; τ grid; Kraken `trade_synth` excluded from native TOB. Not a rename of `lob.tob_depletion_cancel_proxy`.

## Pass checklist

### Pass 1
- [x] Cite deck pages in NOTES
- [x] Implement on HL + Deribit + Kraken
- [x] EXP_REPORT with day-completeness
- [x] Draft CANDIDATES

### Pass 2
- [ ] Overlap gate vs lob cancel proxy
- [ ] Signal board → DESK_MEMO
"""
    )

    mi = CH / "momentum_ignition" / "NOTES.md"
    mi.write_text(
        """# Momentum ignition

**Book:** Filimonov, Perm Winter School 2013  
**PDF:** slides (local) · **Status:** `pass1`  
**Raw:** [`../../_raw/`](../../_raw/) (local/gitignored)  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md)  
**Lib:** [`../../../../lib/hftpat.py`](../../../../lib/hftpat.py) · `ignition_events`

---

## Pass 1 focus

3-phase classifier: Phase1 vol↑ & |Δmid|≈0 → Phase2 large move+vol → Phase3 low-vol partial recovery (deck slide **34**).

### Deck citations
- Slide **34**: momentum ignition cartoon — build pressure (volume without move), impulse, partial reversion under quieter volume.
- Crypto map: `hftpat.ignition_events` on trade bars; overlap table vs `crash.nanex_detect` / SSM / `vshape_events` via `overlap_vs_crash` + `rename_gate`.

### Not a rename
- **Not** Nanex / SSM crash tags or `vshape_events` (move+recovery geometry alone).
- **Not** `vstat.min_v` (econometric drift-burst product ≠ cause sequence).
- Promote **only** if Phase1 (quiet-mid high-vol) adds information; **Pass 1 decision = Hold**.

## Pass 2 dig

**Mandatory** overlap table vs Nanex / SSM / `vshape_events` / MinV. Promote only if pre-phase adds info beyond crash tags.

## Pass checklist

### Pass 1
- [x] Cite deck pages in NOTES
- [x] Implement on HL + Deribit + Kraken
- [x] EXP_REPORT with day-completeness
- [x] Draft CANDIDATES (+ draft overlap table)

### Pass 2
- [ ] Overlap gates vs crash + vstat
- [ ] Signal board → DESK_MEMO
"""
    )


def write_notebooks() -> None:
    """Memo notebooks that load pass1 JSON + figs."""

    def nb(title: str, pkg: str, bullets: list[str]) -> dict[str, Any]:
        md = [
            f"# {title}\n",
            "\n",
            f"**Book:** Filimonov 2013 · package `{pkg}` · Pass 1\n",
            "\n",
            "Slice: ETH · HL + Deribit + Kraken. Artifacts under "
            f"`out/{pkg}/`. Regenerate: `scripts/exp_core_detectors.py`.\n",
            "\n",
        ]
        for b in bullets:
            md.append(f"- {b}\n")
        code = f"""from pathlib import Path
from IPython.display import display, Markdown, Image
import json

BOOK = Path(".").resolve()
if BOOK.name != "filmonov":
    # notebook may live in chapters/<pkg>/
    BOOK = BOOK.parents[1] if (BOOK / "pass1.json").exists() is False else BOOK
OUT = BOOK / "out" / "{pkg}"
if not OUT.exists():
    OUT = Path("../../out/{pkg}").resolve()
    BOOK = OUT.parents[1]

js = json.loads((OUT / "pass1.json").read_text())
print("package", js["package"], "symbol", js.get("symbol"))
print("headlines:")
print(json.dumps(js.get("headlines"), indent=2, default=str)[:3000])
figs = OUT / "figs"
for p in sorted(figs.glob("fig_*.png")):
    display(Markdown(f"### {{p.name}}"))
    display(Image(filename=str(p)))
"""
        return {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
            "cells": [
                {"cell_type": "markdown", "metadata": {}, "source": md},
                {"cell_type": "code", "metadata": {}, "outputs": [], "execution_count": None, "source": code},
            ],
        }

    import nbformat  # type: ignore

    specs = [
        (
            "Quote storms",
            "quote_storms",
            [
                "Burst intensity vs day baseline (`quote_storm_*`).",
                "Not a rename of lob cancel proxy / Nanex quote-rate vanity.",
            ],
        ),
        (
            "Book fade",
            "book_fade",
            [
                "Same-venue P(fade|aggressor); venue-fade HL→DB when native TOB syncs.",
                "Kraken `trade_synth` **excluded** from native TOB fade.",
                "Not a rename of `lob.tob_depletion_cancel_proxy`.",
            ],
        ),
        (
            "Momentum ignition",
            "momentum_ignition",
            [
                "3-phase classifier + draft overlap vs Nanex / vshape / SSM.",
                "Not a rename of crash tags; Pass1 **Hold** pending Phase1 unique-mass test.",
            ],
        ),
    ]
    for title, pkg, bullets in specs:
        path = CH / pkg / f"{pkg}.ipynb"
        path.write_text(nbformat.writes(nbformat.from_dict(nb(title, pkg, bullets))))


def patch_chapter_index() -> None:
    """Only touch rows for the three owned packages → pass1."""
    path = BOOK / "CHAPTER_INDEX.md"
    text = path.read_text()
    import re

    for pkg in ("quote_storms", "book_fade", "momentum_ignition"):
        text, _n = re.subn(
            rf"(\| `{pkg}` \|[^\n]*\| )`(todo|notes)`( \| \[`chapters/{pkg}/`\])",
            rf"\1`pass1`\3",
            text,
            count=1,
        )
    path.write_text(text)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--days", nargs="*", default=None)
    ap.add_argument("--n-days", type=int, default=3, help="If --days omitted, last n listing-cache days")
    ap.add_argument("--max-files", type=int, default=24)
    ap.add_argument("--max-fade-trades", type=int, default=8000)
    ap.add_argument("--prefer-complete", action="store_true", default=True)
    args = ap.parse_args()

    ensure_env()
    days = args.days or resolve_days(None, "hyperliquid", n=max(args.n_days, 5))
    # Prefer complete days when available (mm_confr pattern)
    if args.prefer_complete and not args.days:
        # probe completeness cheaply via load — use known good set first
        prefer = ["2026-09-26", "2026-09-27", "2026-09-30"]
        days = [d for d in prefer if d in days] or days[-args.n_days :]
        if len(days) > args.n_days:
            days = days[-args.n_days :]

    print(f"symbol={args.symbol} days={days} venues={CORE_VENUES}")
    rows: list[dict[str, Any]] = []
    for day in days:
        for venue in CORE_VENUES:
            print(f"  load {venue} {day} …", flush=True)
            try:
                row = load_venue_day(args.symbol, day, venue, max_files=args.max_files)
                c = row["completeness"]
                print(
                    f"    trades n={c.get('n')} complete={c.get('complete')} "
                    f"tob={row['tob_n']} src={row['tob_source']} synth={row['is_trade_synth']}",
                    flush=True,
                )
                rows.append(row)
            except Exception as exc:  # noqa: BLE001
                print(f"    FAIL {type(exc).__name__}: {exc}", flush=True)
                rows.append(
                    {
                        "venue": venue,
                        "symbol": args.symbol,
                        "day": day,
                        "completeness": {"complete": False, "reasons": ["load_error"], "n": 0},
                        "tape": {
                            "ts": np.zeros(0, dtype=np.int64),
                            "px": np.zeros(0, dtype=np.float64),
                            "qty": np.zeros(0, dtype=np.float64),
                            "side": np.zeros(0, dtype=np.float64),
                        },
                        "tob": None,
                        "tob_ok": False,
                        "tob_error": f"{type(exc).__name__}: {exc}",
                        "tob_n": 0,
                        "tob_source": None,
                        "is_trade_synth": False,
                        "native_tob": False,
                    }
                )

    print("=== quote_storms ===", flush=True)
    storm = run_quote_storms(rows, OUT / "quote_storms")
    print("=== book_fade ===", flush=True)
    fade = run_book_fade(rows, OUT / "book_fade", max_trades=args.max_fade_trades)
    print("=== momentum_ignition ===", flush=True)
    ign = run_momentum_ignition(rows, OUT / "momentum_ignition")

    write_chapter_docs(storm, fade, ign, days=days, symbol=args.symbol)
    write_notes_pass1()
    try:
        write_notebooks()
    except Exception as exc:  # noqa: BLE001
        print(f"notebook write warning: {exc}")
        # minimal ipynb without nbformat
        for pkg in ("quote_storms", "book_fade", "momentum_ignition"):
            path = CH / pkg / f"{pkg}.ipynb"
            if not path.exists():
                path.write_text(
                    json.dumps(
                        {
                            "nbformat": 4,
                            "nbformat_minor": 5,
                            "metadata": {},
                            "cells": [
                                {
                                    "cell_type": "markdown",
                                    "metadata": {},
                                    "source": [f"# {pkg}\n", f"See `out/{pkg}/pass1.json`.\n"],
                                }
                            ],
                        },
                        indent=1,
                    )
                )
    patch_chapter_index()

    # Console headline summary
    print("\n======== PASS1 HEADLINES ========", flush=True)
    print("quote_storms:", json.dumps(storm["headlines"], indent=2, default=str), flush=True)
    print("book_fade:", json.dumps(fade["headlines"], indent=2, default=str), flush=True)
    print("momentum_ignition:", json.dumps(ign["headlines"], indent=2, default=str), flush=True)
    print("overlap_rollup n=", len(ign.get("overlap_rollup", [])), flush=True)
    print("done.", flush=True)


if __name__ == "__main__":
    main()
