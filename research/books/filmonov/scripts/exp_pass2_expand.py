from __future__ import annotations
#!/usr/bin/env python3
"""Pass-2 expand — richer stats/plots + wider ETH/BTC day panel.

Builds distributions, CDFs, forest/CI, ToD heatmaps, venue panels, early/late
splits, bootstrap histograms, lead-lag cascade, τ-sensitivity, size×storm.

Writes ``out/pass2_expand/`` JSON + figs. Does not rewrite Pass1.
ClickHouse MCP banned. No git commit.
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
)
from ares_micro.flow.hftpat import (  # noqa: E402
    fade_tau_sensitivity,
    ignition_bar_timestamps,
    ignition_events,
    lead_lag_cascade,
    price_fade_events,
    quote_storm_detect,
    quote_storm_intensity,
    size_storm_interaction,
    tod_event_heatmap,
)
from ares_micro.stats import bootstrap_ci  # noqa: E402

OUT = BOOK / "out" / "pass2_expand"
FIGS = OUT / "figs"
DAYS_DEFAULT = ["2026-09-25", "2026-09-26", "2026-09-27", "2026-09-30"]
N_BOOT = 500
SEED = 42


def _json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=_default))


def _default(o: Any) -> Any:
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating,)):
        x = float(o)
        return x if np.isfinite(x) else None
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    return str(o)


def _is_synth(tob: dict | None) -> bool:
    if tob is None:
        return False
    return "trade_synth" in str(tob.get("source", "")).lower()


def _early_late(days: list[str]) -> tuple[list[str], list[str]]:
    d = sorted(days)
    mid = max(1, len(d) // 2)
    return d[:mid], d[mid:]


def _savefig(fig: plt.Figure, name: str) -> str:
    FIGS.mkdir(parents=True, exist_ok=True)
    path = FIGS / name
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return str(path.relative_to(BOOK))


def _subsample(n: int, max_n: int, seed: int = 0) -> np.ndarray:
    if n <= max_n:
        return np.arange(n, dtype=np.int64)
    step = max(1, int(np.ceil(n / max_n)))
    idx = np.arange(0, n, step, dtype=np.int64)
    if idx.size > max_n:
        rng = np.random.default_rng(seed)
        idx = np.sort(rng.choice(idx, size=max_n, replace=False))
    return idx


def load_panel(
    symbols: list[str],
    days: list[str],
    *,
    max_files: int,
    max_fade: int,
) -> list[dict[str, Any]]:
    ensure_env()
    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        for day in days:
            for venue in CORE_VENUES:
                row: dict[str, Any] = {
                    "symbol": symbol,
                    "venue": venue,
                    "day": day,
                    "complete": False,
                    "native_tob": False,
                    "is_trade_synth": False,
                }
                try:
                    rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
                    tape = rec["tape"]
                    comp = rec.get("completeness") or {}
                    row["complete"] = bool(comp.get("complete"))
                    row["coverage"] = comp.get("coverage")
                    row["n_trades"] = int(tape.get("n", 0))
                    row["tape"] = {
                        "ts": np.asarray(tape["ts"], dtype=np.int64),
                        "side": normalize_side(tape["side"]),
                        "qty": np.asarray(tape["qty"], dtype=np.float64),
                        "px": np.asarray(tape["px"], dtype=np.float64),
                    }
                except Exception as exc:  # noqa: BLE001
                    row["trade_error"] = f"{type(exc).__name__}: {exc}"
                    rows.append(row)
                    continue
                try:
                    tob = load_tob_any(venue, symbol, day)
                    synth = _is_synth(tob)
                    row["is_trade_synth"] = synth
                    row["tob_source"] = tob.get("source")
                    row["n_tob"] = int(tob.get("n", len(tob["ts"])))
                    row["native_tob"] = (not synth) and row["n_tob"] >= 50
                    row["tob"] = tob
                except Exception as exc:  # noqa: BLE001
                    row["tob_error"] = f"{type(exc).__name__}: {exc}"
                    rows.append(row)
                    continue

                # detectors (native TOB only for storm/fade)
                if row["native_tob"] and row["tob"] is not None:
                    tob = row["tob"]
                    intens = quote_storm_intensity(
                        tob["ts"], tob["bid"], tob["ask"], tob["bid_sz"], tob["ask_sz"], bar_s=1.0
                    )
                    # crypto TOB is feed-sample sparse — min_intensity_hz=0 (Pass2/hardening)
                    storms = quote_storm_detect(
                        intens,
                        z_thresh=3.0,
                        min_cancel_frac=0.3,
                        max_mid_range_bps=15.0,
                        min_intensity_hz=0.0,
                    )
                    row["n_storm"] = int(storms["n_events"])
                    span_h = max(
                        1e-6,
                        (float(tob["ts"][-1] - tob["ts"][0]) / 1e9) / 3600.0,
                    )
                    row["storms_per_hour"] = float(storms["n_events"]) / span_h
                    row["storm_ts"] = np.asarray(storms["ts"], dtype=np.int64)
                    row["storm_z"] = np.asarray(storms["z"], dtype=np.float64)
                    row["intensity_hz"] = np.asarray(intens["intensity_hz"], dtype=np.float64)
                    row["cancel_frac"] = np.asarray(intens["cancel_frac"], dtype=np.float64)

                    idx = _subsample(row["tape"]["ts"].size, max_fade, seed=hash(f"{symbol}{venue}{day}") % 99991)
                    tt = row["tape"]["ts"][idx]
                    side = row["tape"]["side"][idx]
                    fade = price_fade_events(
                        tt,
                        side,
                        tob["ts"],
                        tob["bid"],
                        tob["ask"],
                        tob["bid_sz"],
                        tob["ask_sz"],
                        tau_ms=100.0,
                        drop_frac=0.2,
                    )
                    row["p_fade_100ms"] = (
                        float(fade["n_fade"] / fade["n_trades"]) if fade["n_trades"] else float("nan")
                    )
                    row["n_fade"] = int(fade["n_fade"])
                    row["n_fade_scored"] = int(fade["n_trades"])
                    ti = np.asarray(fade["trade_i"], dtype=np.int64)
                    ff = np.asarray(fade["fade"], dtype=np.int64)
                    row["fade_ts"] = tt[ti[ff > 0]] if ti.size and ff.size else np.zeros(0, dtype=np.int64)
                    row["fade_drop"] = (
                        np.asarray(fade["drop_frac"], dtype=np.float64)[ff > 0]
                        if ff.size
                        else np.zeros(0, dtype=np.float64)
                    )
                    row["tau_sens"] = fade_tau_sensitivity(
                        tt,
                        side,
                        tob["ts"],
                        tob["bid"],
                        tob["ask"],
                        tob["bid_sz"],
                        tob["ask_sz"],
                        max_trades=min(4000, max_fade),
                    )
                    row["size_storm"] = size_storm_interaction(
                        row["tape"]["ts"],
                        row["tape"]["qty"],
                        row["storm_ts"],
                        window_ms=1000.0,
                    )
                else:
                    row["storms_per_hour"] = float("nan")
                    row["p_fade_100ms"] = float("nan")
                    row["storm_ts"] = np.zeros(0, dtype=np.int64)
                    row["fade_ts"] = np.zeros(0, dtype=np.int64)

                # ignition — crypto-relaxed params (Pass2/hardening parity)
                ign = ignition_events(
                    row["tape"]["ts"],
                    row["tape"]["px"],
                    row["tape"]["qty"],
                    bar_s=1.0,
                    phase1_bars=3,
                    phase2_bars=3,
                    phase3_bars=5,
                    vol_z=1.0,
                    mid_quiet_bps=15.0,
                    move_bps=5.0,
                    min_recovery=0.15,
                )
                row["n_ignition"] = int(ign["n_events"])
                s_ts, _ = ignition_bar_timestamps(ign)
                row["ignition_ts"] = s_ts
                row["ignition_move_bps"] = np.asarray(ign.get("move_bps", []), dtype=np.float64)
                row["ignition_recovery"] = np.asarray(ign.get("recovery", []), dtype=np.float64)

                if row["native_tob"]:
                    row["lead_lag"] = lead_lag_cascade(
                        row.get("storm_ts", np.zeros(0, dtype=np.int64)),
                        row.get("fade_ts", np.zeros(0, dtype=np.int64)),
                        row.get("ignition_ts", np.zeros(0, dtype=np.int64)),
                    )
                    row["tod_storm"] = tod_event_heatmap(row.get("storm_ts", np.zeros(0, dtype=np.int64)))
                    row["tod_fade"] = tod_event_heatmap(row.get("fade_ts", np.zeros(0, dtype=np.int64)))
                    row["tod_ign"] = tod_event_heatmap(row.get("ignition_ts", np.zeros(0, dtype=np.int64)))

                # drop heavy arrays before JSON (keep summaries)
                row.pop("tape", None)
                row.pop("tob", None)
                rows.append(row)
                print(
                    f"  {symbol} {venue:12s} {day} complete={row['complete']} "
                    f"native={row['native_tob']} storms/h={row.get('storms_per_hour')} "
                    f"p_fade={row.get('p_fade_100ms')} n_ign={row.get('n_ignition')}",
                    flush=True,
                )
    return rows


def _boot_list(vals: list[float]) -> dict[str, Any]:
    arr = np.asarray([v for v in vals if v is not None and np.isfinite(v)], dtype=np.float64)
    if arr.size == 0:
        return {"n": 0, "point": float("nan"), "lo": float("nan"), "hi": float("nan")}
    return bootstrap_ci(arr, n_boot=N_BOOT, seed=SEED)


def summarize(rows: list[dict[str, Any]], days: list[str]) -> dict[str, Any]:
    early, late = _early_late(days)
    out: dict[str, Any] = {"early": early, "late": late, "by_symbol_venue": {}, "boots": {}}
    for symbol in sorted({r["symbol"] for r in rows}):
        for venue in CORE_VENUES:
            sub = [r for r in rows if r["symbol"] == symbol and r["venue"] == venue]
            sph = [float(r["storms_per_hour"]) for r in sub if np.isfinite(r.get("storms_per_hour", np.nan))]
            pf = [float(r["p_fade_100ms"]) for r in sub if np.isfinite(r.get("p_fade_100ms", np.nan))]
            ni = [float(r["n_ignition"]) for r in sub if np.isfinite(r.get("n_ignition", np.nan))]
            out["by_symbol_venue"][f"{symbol}:{venue}"] = {
                "n_rows": len(sub),
                "n_complete": sum(1 for r in sub if r.get("complete")),
                "n_native_tob": sum(1 for r in sub if r.get("native_tob")),
                "storms_per_hour": _boot_list(sph),
                "p_fade_100ms": _boot_list(pf),
                "n_ignition": _boot_list(ni),
                "early_storms": float(
                    np.mean([float(r["storms_per_hour"]) for r in sub if r["day"] in early and np.isfinite(r.get("storms_per_hour", np.nan))])
                )
                if any(r["day"] in early for r in sub)
                else float("nan"),
                "late_storms": float(
                    np.mean([float(r["storms_per_hour"]) for r in sub if r["day"] in late and np.isfinite(r.get("storms_per_hour", np.nan))])
                )
                if any(r["day"] in late for r in sub)
                else float("nan"),
                "early_fade": float(
                    np.mean([float(r["p_fade_100ms"]) for r in sub if r["day"] in early and np.isfinite(r.get("p_fade_100ms", np.nan))])
                )
                if any(r["day"] in early for r in sub)
                else float("nan"),
                "late_fade": float(
                    np.mean([float(r["p_fade_100ms"]) for r in sub if r["day"] in late and np.isfinite(r.get("p_fade_100ms", np.nan))])
                )
                if any(r["day"] in late for r in sub)
                else float("nan"),
            }
    # headline boots HL ETH
    hl = [r for r in rows if r["symbol"] == "ETH" and r["venue"] == "hyperliquid"]
    out["boots"]["eth_hl_storms_per_hour"] = _boot_list(
        [float(r["storms_per_hour"]) for r in hl if np.isfinite(r.get("storms_per_hour", np.nan))]
    )
    out["boots"]["eth_hl_p_fade"] = _boot_list(
        [float(r["p_fade_100ms"]) for r in hl if np.isfinite(r.get("p_fade_100ms", np.nan))]
    )
    out["boots"]["eth_hl_n_ign"] = _boot_list(
        [float(r["n_ignition"]) for r in hl if np.isfinite(r.get("n_ignition", np.nan))]
    )
    btc = [r for r in rows if r["symbol"] == "BTC" and r["venue"] == "hyperliquid"]
    out["boots"]["btc_hl_storms_per_hour"] = _boot_list(
        [float(r["storms_per_hour"]) for r in btc if np.isfinite(r.get("storms_per_hour", np.nan))]
    )
    out["boots"]["btc_hl_p_fade"] = _boot_list(
        [float(r["p_fade_100ms"]) for r in btc if np.isfinite(r.get("p_fade_100ms", np.nan))]
    )
    return out


def make_figs(rows: list[dict[str, Any]], summary: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    # 1) forest CI storms/fade/ign by venue ETH
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.6))
    metrics = [
        ("storms_per_hour", "Storms / hour"),
        ("p_fade_100ms", "P(fade) @100ms"),
        ("n_ignition", "n ignition / day"),
    ]
    for ax, (key, title) in zip(axes, metrics):
        labs, pts, los, his = [], [], [], []
        for venue in CORE_VENUES:
            b = (summary["by_symbol_venue"].get(f"ETH:{venue}") or {}).get(key) or {}
            if b.get("n", 0) == 0:
                continue
            labs.append(venue[:2].upper())
            pts.append(b["point"])
            los.append(b["lo"])
            his.append(b["hi"])
        if not labs:
            ax.set_title(title + " (empty)")
            continue
        y = np.arange(len(labs))
        ax.errorbar(pts, y, xerr=[np.array(pts) - np.array(los), np.array(his) - np.array(pts)], fmt="o", capsize=3)
        ax.set_yticks(y)
        ax.set_yticklabels(labs)
        ax.set_title(title)
        ax.grid(True, axis="x", alpha=0.3)
    fig.suptitle("ETH forest CI (day-block bootstrap)", fontsize=11)
    paths.append(_savefig(fig, "fig_forest_ci_eth.png"))

    # 2) bootstrap histogram for HL ETH storms
    hl_vals = [
        float(r["storms_per_hour"])
        for r in rows
        if r["symbol"] == "ETH" and r["venue"] == "hyperliquid" and np.isfinite(r.get("storms_per_hour", np.nan))
    ]
    fig, ax = plt.subplots(figsize=(5.5, 3.4))
    if hl_vals:
        arr = np.asarray(hl_vals, dtype=np.float64)
        rng = np.random.default_rng(SEED)
        boots = [float(np.mean(rng.choice(arr, size=arr.size, replace=True))) for _ in range(N_BOOT)]
        ax.hist(boots, bins=30, color="#3d5a80", alpha=0.85)
        ax.axvline(float(np.mean(arr)), color="#e76f51", lw=2, label=f"point={np.mean(arr):.3f}")
        ax.legend(fontsize=8)
    ax.set_title("HL ETH storms/h day-block bootstrap")
    ax.set_xlabel("mean storms/h")
    paths.append(_savefig(fig, "fig_boot_hist_storms.png"))

    # 3) early/late split bars
    fig, ax = plt.subplots(figsize=(6, 3.4))
    labels, early_v, late_v = [], [], []
    for venue in ("hyperliquid", "deribit"):
        s = summary["by_symbol_venue"].get(f"ETH:{venue}") or {}
        labels.append(venue)
        early_v.append(s.get("early_fade", float("nan")))
        late_v.append(s.get("late_fade", float("nan")))
    x = np.arange(len(labels))
    ax.bar(x - 0.18, early_v, 0.35, label="early days", color="#2a9d8f")
    ax.bar(x + 0.18, late_v, 0.35, label="late days", color="#e9c46a")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("P(fade)@100ms")
    ax.set_title("Early vs late fade (ETH)")
    ax.legend(fontsize=8)
    paths.append(_savefig(fig, "fig_early_late_fade.png"))

    # 4) venue panel storms + fade
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.5))
    for ax, key, title in zip(
        axes,
        ("storms_per_hour", "p_fade_100ms"),
        ("Storms/h by day", "P(fade) by day"),
    ):
        for venue, color in zip(("hyperliquid", "deribit"), ("#264653", "#e76f51")):
            for symbol, ls in zip(("ETH", "BTC"), ("-", "--")):
                sub = sorted(
                    [
                        r
                        for r in rows
                        if r["symbol"] == symbol
                        and r["venue"] == venue
                        and np.isfinite(r.get(key, np.nan))
                    ],
                    key=lambda r: r["day"],
                )
                if not sub:
                    continue
                ax.plot(
                    [r["day"][-5:] for r in sub],
                    [float(r[key]) for r in sub],
                    ls=ls,
                    color=color,
                    marker="o",
                    label=f"{symbol[:1]}-{venue[:2]}",
                )
        ax.set_title(title)
        ax.tick_params(axis="x", rotation=30)
        ax.legend(fontsize=7, ncol=2)
        ax.grid(True, alpha=0.25)
    paths.append(_savefig(fig, "fig_venue_panel_days.png"))

    # 5) τ-sensitivity (mean across HL ETH days)
    tau_curves = [
        r["tau_sens"]
        for r in rows
        if r["symbol"] == "ETH" and r["venue"] == "hyperliquid" and r.get("tau_sens")
    ]
    fig, ax = plt.subplots(figsize=(5.5, 3.4))
    if tau_curves:
        taus = tau_curves[0]["taus_ms"]
        mat = np.asarray([c["p_fade"] for c in tau_curves], dtype=np.float64)
        mean = np.nanmean(mat, axis=0)
        lo = np.nanpercentile(mat, 10, axis=0)
        hi = np.nanpercentile(mat, 90, axis=0)
        ax.plot(taus, mean, "-o", color="#1d3557")
        ax.fill_between(taus, lo, hi, alpha=0.25, color="#457b9d")
        ax.set_xlabel("τ ms")
        ax.set_ylabel("P(fade)")
        ax.set_title("Fade τ-sensitivity (HL ETH)")
        ax.set_xscale("log")
        ax.grid(True, alpha=0.3)
    paths.append(_savefig(fig, "fig_fade_tau_sensitivity.png"))

    # 6) size×storm interaction
    fig, ax = plt.subplots(figsize=(5.5, 3.4))
    plotted = False
    for r in rows:
        if r["symbol"] != "ETH" or r["venue"] != "hyperliquid":
            continue
        ss = r.get("size_storm") or {}
        rates = ss.get("storm_rate") or []
        if not rates:
            continue
        ax.plot(np.arange(1, len(rates) + 1), rates, "-o", alpha=0.7, label=r["day"][-5:])
        plotted = True
    if plotted:
        ax.set_xlabel("size quantile (lo→hi)")
        ax.set_ylabel("P(near storm | size q)")
        ax.set_title("Size × storm interaction (HL ETH)")
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3)
    paths.append(_savefig(fig, "fig_size_storm_interaction.png"))

    # 7) lead-lag cascade
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ll_rows = [
        r["lead_lag"]
        for r in rows
        if r["symbol"] == "ETH" and r["venue"] == "hyperliquid" and r.get("lead_lag")
    ]
    if ll_rows:
        wins = ll_rows[0]["windows_ms"]
        for key, color, label in (
            ("storm_to_fade", "#e76f51", "storm→fade"),
            ("storm_to_ignition", "#2a9d8f", "storm→ign"),
            ("fade_to_ignition", "#264653", "fade→ign"),
        ):
            mat = np.asarray([r[key] for r in ll_rows], dtype=np.float64)
            ax.plot(wins, np.nanmean(mat, axis=0), "-o", color=color, label=label)
        ax.set_xscale("log")
        ax.set_xlabel("window ms")
        ax.set_ylabel("forward hit rate")
        ax.set_title("Lead-lag cascade (HL ETH)")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
    paths.append(_savefig(fig, "fig_lead_lag_cascade.png"))

    # 8) ToD heatmap storms
    grids = [
        np.asarray(r["tod_storm"]["grid"], dtype=np.float64)
        for r in rows
        if r["symbol"] == "ETH" and r["venue"] == "hyperliquid" and r.get("tod_storm")
    ]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    if grids:
        g = np.nansum(grids, axis=0)
        im = ax.imshow(g, aspect="auto", origin="lower", cmap="YlOrRd")
        ax.set_xlabel("minute bin (5m)")
        ax.set_ylabel("UTC hour")
        ax.set_title("Storm ToD heatmap (HL ETH sum)")
        fig.colorbar(im, ax=ax, fraction=0.046)
    paths.append(_savefig(fig, "fig_tod_heatmap_storms.png"))

    # 9) fade drop CDF + ignition move CDF
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.4))
    drops = np.concatenate(
        [
            np.asarray(r.get("fade_drop", []), dtype=np.float64)
            for r in rows
            if r["symbol"] == "ETH" and r["venue"] == "hyperliquid"
        ]
    ) if any(r.get("fade_drop") is not None for r in rows) else np.zeros(0)
    drops = drops[np.isfinite(drops)]
    if drops.size:
        xs = np.sort(drops)
        ys = np.arange(1, xs.size + 1) / xs.size
        axes[0].plot(xs, ys, color="#1d3557")
    axes[0].set_title("Fade drop-frac CDF (HL ETH)")
    axes[0].set_xlabel("max drop frac")
    axes[0].grid(True, alpha=0.3)
    moves = np.concatenate(
        [
            np.asarray(r.get("ignition_move_bps", []), dtype=np.float64)
            for r in rows
            if r["symbol"] == "ETH" and r["venue"] == "hyperliquid"
        ]
    ) if any(r.get("ignition_move_bps") is not None for r in rows) else np.zeros(0)
    moves = moves[np.isfinite(moves)]
    if moves.size:
        xs = np.sort(np.abs(moves))
        ys = np.arange(1, xs.size + 1) / xs.size
        axes[1].plot(xs, ys, color="#e76f51")
    axes[1].set_title("|ignition move| CDF (HL ETH)")
    axes[1].set_xlabel("bps")
    axes[1].grid(True, alpha=0.3)
    paths.append(_savefig(fig, "fig_cdf_fade_ignition.png"))

    # 10) intensity Hz distribution
    fig, ax = plt.subplots(figsize=(5.5, 3.4))
    for venue, color in zip(("hyperliquid", "deribit"), ("#264653", "#e76f51")):
        hz = np.concatenate(
            [
                np.asarray(r.get("intensity_hz", []), dtype=np.float64)
                for r in rows
                if r["symbol"] == "ETH" and r["venue"] == venue and r.get("intensity_hz") is not None
            ]
        ) if True else np.zeros(0)
        hz = hz[np.isfinite(hz)]
        if hz.size:
            ax.hist(hz, bins=40, alpha=0.45, color=color, label=venue, density=True)
    ax.set_title("TOB intensity Hz distribution (ETH)")
    ax.set_xlabel("Hz")
    ax.legend(fontsize=8)
    paths.append(_savefig(fig, "fig_intensity_hz_dist.png"))

    # 11) completeness matrix
    fig, ax = plt.subplots(figsize=(7, 3.2))
    days = sorted({r["day"] for r in rows})
    labs = []
    mat = []
    for symbol in ("ETH", "BTC"):
        for venue in CORE_VENUES:
            labs.append(f"{symbol[0]}-{venue[:2]}")
            mat.append(
                [
                    1.0
                    if any(
                        r["symbol"] == symbol
                        and r["venue"] == venue
                        and r["day"] == d
                        and r.get("complete")
                        for r in rows
                    )
                    else 0.0
                    for d in days
                ]
            )
    im = ax.imshow(np.asarray(mat), aspect="auto", cmap="Greens", vmin=0, vmax=1)
    ax.set_yticks(range(len(labs)))
    ax.set_yticklabels(labs, fontsize=7)
    ax.set_xticks(range(len(days)))
    ax.set_xticklabels([d[-5:] for d in days], rotation=30)
    ax.set_title("Day completeness (trades)")
    fig.colorbar(im, ax=ax, fraction=0.046)
    paths.append(_savefig(fig, "fig_completeness_matrix.png"))

    # 12) BTC vs ETH storm comparison
    fig, ax = plt.subplots(figsize=(5.5, 3.4))
    for symbol, color in zip(("ETH", "BTC"), ("#2a9d8f", "#e76f51")):
        sub = [
            r
            for r in rows
            if r["symbol"] == symbol
            and r["venue"] == "hyperliquid"
            and np.isfinite(r.get("storms_per_hour", np.nan))
        ]
        if sub:
            ax.bar(
                [f"{symbol[0]}-{r['day'][-5:]}" for r in sub],
                [float(r["storms_per_hour"]) for r in sub],
                color=color,
                alpha=0.8,
            )
    ax.set_title("HL storms/h ETH vs BTC")
    ax.tick_params(axis="x", rotation=45)
    ax.set_ylabel("storms/h")
    paths.append(_savefig(fig, "fig_eth_btc_storms.png"))

    return paths


def light_rows_for_json(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    light: list[dict[str, Any]] = []
    keep_arr_keys = {
        "storm_z",
        "fade_drop",
        "ignition_move_bps",
        "ignition_recovery",
        "intensity_hz",
        "cancel_frac",
    }
    for r in rows:
        o: dict[str, Any] = {}
        for k, v in r.items():
            if k in ("storm_ts", "fade_ts", "ignition_ts"):
                o[k + "_n"] = int(np.asarray(v).size) if v is not None else 0
                continue
            if k.startswith("tod_"):
                o[k] = {
                    "n": v.get("n"),
                    "peak_hour": v.get("peak_hour"),
                    "hour_marginal": v.get("hour_marginal"),
                }
                continue
            if k in keep_arr_keys and isinstance(v, np.ndarray):
                # downsample for JSON size
                if v.size > 2000:
                    step = max(1, v.size // 2000)
                    o[k] = v[::step]
                else:
                    o[k] = v
                continue
            if isinstance(v, np.ndarray):
                continue
            o[k] = v
        light.append(o)
    return light


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", nargs="+", default=DAYS_DEFAULT)
    ap.add_argument("--symbols", nargs="+", default=["ETH", "BTC"])
    ap.add_argument("--max-files", type=int, default=12)
    ap.add_argument("--max-fade", type=int, default=5000)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    FIGS.mkdir(parents=True, exist_ok=True)
    print("Pass2 expand days", args.days, "symbols", args.symbols, flush=True)
    rows = load_panel(args.symbols, args.days, max_files=args.max_files, max_fade=args.max_fade)
    summary = summarize(rows, args.days)
    fig_paths = make_figs(rows, summary)
    payload = {
        "days": args.days,
        "symbols": args.symbols,
        "n_rows": len(rows),
        "summary": summary,
        "fig_paths": fig_paths,
        "day_rows": light_rows_for_json(rows),
        "notes": {
            "kraken_trade_synth": "excluded from native TOB fade/storm",
            "wider_panel": "adds 2026-09-25 vs Pass-2.5 freeze days",
        },
    }
    _json(OUT / "pass2_expand_rollup.json", payload)
    _json(OUT / "fig_index.json", {"figs": fig_paths})
    print("Wrote", OUT / "pass2_expand_rollup.json")
    print("Figs:", len(fig_paths))
    for p in fig_paths:
        print(" ", p)


if __name__ == "__main__":
    main()
