#!/usr/bin/env python3
"""Info-lens feature dig for Filimonov desk package.

New candidates (D/T/E + lenses incl. info), honest Hold/Kill/Promote with
falsifiers. Joins OFI / VPIN / markout / intensity around storms/fades/
ignition/clock; storm→AS; fade→spread IRF; ignition Phase1 unique mass;
clock vs funding; xvenue IS around fade.

Writes ``out/pass2_expand/info_features.json`` + figs.
ClickHouse MCP banned. No git commit.
"""

from __future__ import annotations

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
sys.path.insert(0, str(Path("/home/dev/lab/lab-n2070/warehouse/src")))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path("/home/dev/srv/ares-startarb") / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import (  # noqa: E402
    CORE_VENUES,
    ensure_env,
    load_day_trades,
    load_tob_any,
    normalize_side,
)
from research.lib.continuous import ofi_continuous, trade_intensity, vpin_bucket  # noqa: E402
from research.lib.crash import nanex_detect, vshape_events  # noqa: E402
from research.lib.hftpat import (  # noqa: E402
    clock_vs_funding_windows,
    event_window_markout,
    ignition_bar_timestamps,
    ignition_events,
    ignition_phase1_unique_mass,
    price_fade_events,
    quote_storm_detect,
    quote_storm_intensity,
    spread_irf_after_events,
    xvenue_fade_info_share,
)
from research.lib.spreads import quoted_spread_bps  # noqa: E402
from research.lib.stats import bootstrap_ci  # noqa: E402

OUT = BOOK / "out" / "pass2_expand"
FIGS = OUT / "figs"
DAYS_DEFAULT = ["2026-09-25", "2026-09-26", "2026-09-27", "2026-09-30"]
N_BOOT = 400


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


def _savefig(fig: plt.Figure, name: str) -> str:
    FIGS.mkdir(parents=True, exist_ok=True)
    path = FIGS / name
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return str(path.relative_to(BOOK))


def _subsample(n: int, max_n: int, seed: int) -> np.ndarray:
    if n <= max_n:
        return np.arange(n, dtype=np.int64)
    step = max(1, int(np.ceil(n / max_n)))
    idx = np.arange(0, n, step, dtype=np.int64)
    if idx.size > max_n:
        rng = np.random.default_rng(seed)
        idx = np.sort(rng.choice(idx, size=max_n, replace=False))
    return idx


def _early_late(days: list[str]) -> tuple[list[str], list[str]]:
    d = sorted(days)
    mid = max(1, len(d) // 2)
    return d[:mid], d[mid:]


def dig_day(
    venue: str,
    symbol: str,
    day: str,
    *,
    max_files: int,
    max_trades: int,
    far_tob: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "venue": venue,
        "symbol": symbol,
        "day": day,
        "native_tob": False,
        "is_trade_synth": False,
    }
    rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
    tape = rec["tape"]
    row["complete"] = bool((rec.get("completeness") or {}).get("complete"))
    row["n_trades"] = int(tape.get("n", 0))
    ts = np.asarray(tape["ts"], dtype=np.int64)
    side = normalize_side(tape["side"])
    qty = np.asarray(tape["qty"], dtype=np.float64)
    px = np.asarray(tape["px"], dtype=np.float64)

    try:
        tob = load_tob_any(venue, symbol, day)
    except Exception as exc:  # noqa: BLE001
        row["tob_error"] = f"{type(exc).__name__}: {exc}"
        return row
    synth = _is_synth(tob)
    row["is_trade_synth"] = synth
    row["tob_source"] = tob.get("source")
    row["n_tob"] = int(tob.get("n", len(tob["ts"])))
    row["native_tob"] = (not synth) and row["n_tob"] >= 50
    if not row["native_tob"]:
        row["skip"] = "trade_synth_or_sparse_tob"
        # still compute clock vs funding on trades
        row["clock_funding"] = clock_vs_funding_windows(ts)
        return row

    mid = np.asarray(tob.get("mid", 0.5 * (np.asarray(tob["bid"]) + np.asarray(tob["ask"]))), dtype=np.float64)
    intens = quote_storm_intensity(tob["ts"], tob["bid"], tob["ask"], tob["bid_sz"], tob["ask_sz"])
    storms = quote_storm_detect(
        intens, z_thresh=3.0, min_cancel_frac=0.3, max_mid_range_bps=15.0, min_intensity_hz=0.0
    )
    storm_ts = np.asarray(storms["ts"], dtype=np.int64)

    idx = _subsample(ts.size, max_trades, seed=hash(f"{symbol}{venue}{day}") % 10_000)
    tt, sd, qq, pp = ts[idx], side[idx], qty[idx], px[idx]
    fade = price_fade_events(
        tt, sd, tob["ts"], tob["bid"], tob["ask"], tob["bid_sz"], tob["ask_sz"], tau_ms=100.0
    )
    ti = np.asarray(fade["trade_i"], dtype=np.int64)
    ff = np.asarray(fade["fade"], dtype=np.int64)
    fade_ts = tt[ti[ff > 0]] if ti.size and ff.size else np.zeros(0, dtype=np.int64)

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
    ign_starts, ign_ends = ignition_bar_timestamps(ign)

    # crash overlap for unique mass (indices → timestamps)
    try:
        nanex = nanex_detect(ts, px)
        si = np.asarray(nanex.get("start_i", []), dtype=np.int64)
        ei = np.asarray(nanex.get("end_i", []), dtype=np.int64)
        n_starts = ts[si] if si.size and si.max() < ts.size else np.zeros(0, dtype=np.int64)
        n_ends = ts[ei] if ei.size and ei.max() < ts.size else n_starts.copy()
    except Exception:
        n_starts = n_ends = np.zeros(0, dtype=np.int64)
    try:
        vs = vshape_events(ts, px)
        si = np.asarray(vs.get("start_i", []), dtype=np.int64)
        ei = np.asarray(vs.get("end_i", []), dtype=np.int64)
        v_starts = ts[si] if si.size and si.max() < ts.size else np.zeros(0, dtype=np.int64)
        v_ends = ts[ei] if ei.size and ei.max() < ts.size else v_starts.copy()
    except Exception:
        v_starts = v_ends = np.zeros(0, dtype=np.int64)
    crash_s = (
        np.concatenate([n_starts, v_starts]) if (n_starts.size or v_starts.size) else np.zeros(0, dtype=np.int64)
    )
    crash_e = (
        np.concatenate([n_ends, v_ends]) if (n_ends.size or v_ends.size) else crash_s.copy()
    )
    if crash_e.size != crash_s.size:
        crash_e = crash_s.copy()

    # info joins
    ofi = ofi_continuous(tob["ts"], tob["bid"], tob["ask"], tob["bid_sz"], tob["ask_sz"])
    lam = trade_intensity(ts, bar_ns=1_000_000_000)
    bucket_vol = float(np.nanpercentile(qq[qq > 0], 75) * 40) if (qq > 0).any() else 1.0
    vpin = vpin_bucket(sd, qq, bucket_volume=max(bucket_vol, 1e-6))

    storm_mo = event_window_markout(storm_ts, tt, sd, tob["ts"], mid, post_ms=1000.0, horizon_ms=1000.0)
    fade_mo = event_window_markout(fade_ts, tt, sd, tob["ts"], mid, post_ms=500.0, horizon_ms=1000.0)
    ign_mo = event_window_markout(ign_starts, tt, sd, tob["ts"], mid, post_ms=2000.0, horizon_ms=1000.0)
    # placebo: random timestamps
    if ts.size > 100 and storm_ts.size:
        rng = np.random.default_rng(hash(day) % 10_000)
        placebo = np.sort(rng.choice(ts, size=min(int(storm_ts.size), 50), replace=False))
        placebo_mo = event_window_markout(placebo, tt, sd, tob["ts"], mid, post_ms=1000.0, horizon_ms=1000.0)
    else:
        placebo_mo = {"mean_bps": float("nan"), "n_events": 0}

    fade_irf = spread_irf_after_events(fade_ts, tob["ts"], tob["bid"], tob["ask"])
    storm_irf = spread_irf_after_events(storm_ts, tob["ts"], tob["bid"], tob["ask"])
    uniq = ignition_phase1_unique_mass(ign, crash_s, crash_e)
    clock_fund = clock_vs_funding_windows(ts)

    xvenue = {"n_events": 0, "mean_is_home_lo": float("nan"), "mean_is_home_hi": float("nan")}
    if far_tob is not None and fade_ts.size and not _is_synth(far_tob):
        xvenue = xvenue_fade_info_share(
            fade_ts,
            tob["ts"],
            mid,
            far_tob["ts"],
            np.asarray(far_tob.get("mid", 0.5 * (far_tob["bid"] + far_tob["ask"])), dtype=np.float64),
        )

    # intensity around storms: trade counts in ±1s / baseline mean λ
    intens_around = float("nan")
    if storm_ts.size and ts.size:
        base_lam = float(lam.get("mean_lambda", np.nan))
        ratios = []
        w = 1_000_000_000
        for e in storm_ts[:80]:
            n_loc = int(np.sum((ts >= int(e) - w) & (ts <= int(e) + w)))
            # 2-second window → Hz
            loc = n_loc / 2.0
            if np.isfinite(base_lam) and base_lam > 0:
                ratios.append(loc / base_lam)
        intens_around = float(np.nanmean(ratios)) if ratios else float("nan")

    spr = quoted_spread_bps(tob["bid"], tob["ask"])
    row.update(
        {
            "n_storm": int(storms["n_events"]),
            "n_fade": int(fade["n_fade"]),
            "n_ignition": int(ign["n_events"]),
            "ofi_corr_ret": ofi.get("corr_ofi_ret"),
            "ofi_beta": ofi.get("beta_ofi"),
            "mean_vpin": vpin.get("mean_vpin"),
            "vpin_ci95": vpin.get("vpin_ci95"),
            "mean_lambda": lam.get("mean_lambda"),
            "storm_markout_1s": storm_mo,
            "fade_markout_1s": fade_mo,
            "ignition_markout_1s": ign_mo,
            "placebo_storm_markout_1s": placebo_mo,
            "storm_as_delta_vs_placebo": (
                float(storm_mo.get("mean_bps", np.nan) - placebo_mo.get("mean_bps", np.nan))
                if np.isfinite(storm_mo.get("mean_bps", np.nan))
                and np.isfinite(placebo_mo.get("mean_bps", np.nan))
                else float("nan")
            ),
            "fade_spread_irf": fade_irf,
            "storm_spread_irf": storm_irf,
            "ignition_unique_mass": uniq,
            "clock_funding": clock_fund,
            "xvenue_is_around_fade": xvenue,
            "storm_intensity_ratio": intens_around,
            "mean_spread_bps": float(np.nanmean(spr)) if np.isfinite(spr).any() else float("nan"),
        }
    )
    return row


def decide_candidates(day_rows: list[dict[str, Any]], days: list[str]) -> dict[str, Any]:
    """Label new info candidates with honest Hold/Kill (0 Promote default)."""
    early, late = _early_late(days)
    hl = [r for r in day_rows if r.get("venue") == "hyperliquid" and r.get("native_tob")]

    def _means(key: str, subkey: str | None = None) -> list[float]:
        out = []
        for r in hl:
            v = r.get(key)
            if subkey and isinstance(v, dict):
                v = v.get(subkey)
            if v is not None and np.isfinite(v):
                out.append(float(v))
        return out

    storm_as = _means("storm_as_delta_vs_placebo")
    uniq = []
    for r in hl:
        u = (r.get("ignition_unique_mass") or {}).get("unique_mass")
        if u is not None and np.isfinite(u):
            uniq.append(float(u))
    clock_ratio = []
    for r in hl:
        c = r.get("clock_funding") or {}
        if np.isfinite(c.get("excess_ratio", np.nan)):
            clock_ratio.append(float(c["excess_ratio"]))
    fade_irf_peak = []
    for r in hl:
        irf = r.get("fade_spread_irf") or {}
        d = irf.get("mean_delta_bps") or []
        if d:
            fade_irf_peak.append(float(np.nanmax(np.asarray(d, dtype=np.float64))))
    xvenue_lo = []
    for r in hl:
        x = r.get("xvenue_is_around_fade") or {}
        if np.isfinite(x.get("mean_is_home_lo", np.nan)):
            xvenue_lo.append(float(x["mean_is_home_lo"]))
    ofi_c = _means("ofi_corr_ret")
    vpin_m = _means("mean_vpin")

    # early/late storm AS
    early_as = [
        float(r["storm_as_delta_vs_placebo"])
        for r in hl
        if r["day"] in early and np.isfinite(r.get("storm_as_delta_vs_placebo", np.nan))
    ]
    late_as = [
        float(r["storm_as_delta_vs_placebo"])
        for r in hl
        if r["day"] in late and np.isfinite(r.get("storm_as_delta_vs_placebo", np.nan))
    ]

    labels: dict[str, Any] = {}

    # info.storm_adverse_selection — Hold if delta vs placebo has sign but CI crosses 0 or n small
    boot_as = bootstrap_ci(np.asarray(storm_as, dtype=np.float64), n_boot=N_BOOT, seed=11) if storm_as else None
    as_promote = False  # never promote on thin panel
    as_kill = boot_as is not None and boot_as["n"] >= 2 and abs(boot_as["point"]) < 0.05
    labels["info.storm_adverse_selection"] = {
        "type": "E",
        "lenses": ["info", "risk", "mm"],
        "decision": "Kill" if as_kill else "Hold",
        "monitor": True,
        "tradable": False,
        "exec_throttle": True,
        "boot": boot_as,
        "early_mean": float(np.mean(early_as)) if early_as else float("nan"),
        "late_mean": float(np.mean(late_as)) if late_as else float("nan"),
        "falsifier": "placebo timestamp markout; early/late sign flip; CI∋0 → Hold not Promote",
        "why": (
            f"storm−placebo markout Δ≈{boot_as['point'] if boot_as else None}bps "
            f"CI={None if not boot_as else [boot_as['lo'], boot_as['hi']]}; n={len(storm_as)}"
        ),
    }

    boot_irf = bootstrap_ci(np.asarray(fade_irf_peak, dtype=np.float64), n_boot=N_BOOT, seed=12) if fade_irf_peak else None
    labels["info.fade_spread_widen_irf"] = {
        "type": "E",
        "lenses": ["info", "mm", "liq"],
        "decision": "Hold",
        "monitor": True,
        "tradable": False,
        "exec_throttle": False,
        "boot": boot_irf,
        "falsifier": "IRF peak ≤0 or unstable early/late → Kill widen policy",
        "why": (
            f"fade IRF peak Δspread≈{boot_irf['point'] if boot_irf else None}bps; "
            "MM pull / widen sketch only"
        ),
    }

    boot_u = bootstrap_ci(np.asarray(uniq, dtype=np.float64), n_boot=N_BOOT, seed=13) if uniq else None
    # Kill rename if unique_mass very low
    u_dec = "Hold"
    if boot_u and boot_u["n"] and boot_u["point"] < 0.15:
        u_dec = "Kill"
    labels["info.ignition_phase1_unique_mass"] = {
        "type": "D",
        "lenses": ["info", "risk"],
        "decision": u_dec,
        "monitor": True,
        "tradable": False,
        "exec_throttle": False,
        "boot": boot_u,
        "falsifier": "unique_mass≪0.5 ⇒ rename of Nanex/V — Kill as distinct object",
        "why": (
            f"Phase1 unique_mass≈{boot_u['point'] if boot_u else None}; "
            "escalate-vs-crash only if unique mass material"
        ),
    }

    boot_cf = bootstrap_ci(np.asarray(clock_ratio, dtype=np.float64), n_boot=N_BOOT, seed=14) if clock_ratio else None
    labels["info.clock_vs_funding_window"] = {
        "type": "E",
        "lenses": ["info", "exec"],
        "decision": "Hold",
        "monitor": True,
        "tradable": False,
        "exec_throttle": False,
        "boot": boot_cf,
        "falsifier": "excess_ratio≈1 (funding windows not special) → Kill funding-specific clock",
        "why": (
            f"max_z_in/out ratio≈{boot_cf['point'] if boot_cf else None}; "
            "algo-hunter vs funding/mark windows"
        ),
    }

    boot_xv = bootstrap_ci(np.asarray(xvenue_lo, dtype=np.float64), n_boot=N_BOOT, seed=15) if xvenue_lo else None
    labels["info.xvenue_is_around_fade"] = {
        "type": "E",
        "lenses": ["info", "disc"],
        "decision": "Hold" if xvenue_lo else "Hold",
        "monitor": True,
        "tradable": False,
        "exec_throttle": False,
        "boot": boot_xv,
        "falsifier": "IS bounds unstable / n_events≪10 → research-only Hold",
        "why": (
            f"Hasbrouck IS home lo≈{boot_xv['point'] if boot_xv else None} around fade; "
            "not arb α; RTT haircut missing"
        ),
    }

    boot_ofi = bootstrap_ci(np.asarray(ofi_c, dtype=np.float64), n_boot=N_BOOT, seed=16) if ofi_c else None
    labels["info.ofi_around_storm_regime"] = {
        "type": "E",
        "lenses": ["info", "cont"],
        "decision": "Hold",
        "monitor": True,
        "tradable": False,
        "exec_throttle": False,
        "boot": boot_ofi,
        "falsifier": "corr(OFI,ret) CI∋0 day-block → Kill as storm-regime signal",
        "why": f"day OFI–ret corr≈{boot_ofi['point'] if boot_ofi else None} (regime join, not α)",
    }

    boot_vpin = bootstrap_ci(np.asarray(vpin_m, dtype=np.float64), n_boot=N_BOOT, seed=17) if vpin_m else None
    labels["info.vpin_storm_join"] = {
        "type": "E",
        "lenses": ["info", "liq"],
        "decision": "Hold",
        "monitor": True,
        "tradable": False,
        "exec_throttle": False,
        "boot": boot_vpin,
        "falsifier": "VPIN flat across storm/non-storm days → Kill join",
        "why": f"mean VPIN≈{boot_vpin['point'] if boot_vpin else None}; toxicity join with storms",
    }

    # storm intensity ratio
    intens = _means("storm_intensity_ratio")
    boot_i = bootstrap_ci(np.asarray(intens, dtype=np.float64), n_boot=N_BOOT, seed=18) if intens else None
    labels["info.storm_trade_intensity_burst"] = {
        "type": "E",
        "lenses": ["info", "exec"],
        "decision": "Hold",
        "monitor": True,
        "tradable": False,
        "exec_throttle": True,
        "boot": boot_i,
        "falsifier": "λ_storm/λ_base ≈ 1 → Kill intensity join",
        "why": f"storm-bar λ / baseline≈{boot_i['point'] if boot_i else None}",
    }

    n_hold = sum(1 for g in labels.values() if g["decision"] == "Hold")
    n_kill = sum(1 for g in labels.values() if g["decision"] == "Kill")
    n_promote = sum(1 for g in labels.values() if g["decision"] == "Promote")
    assert not as_promote
    return {
        "labels": labels,
        "n_promote": n_promote,
        "n_hold": n_hold,
        "n_kill": n_kill,
        "early": early,
        "late": late,
        "note": "0 Promote default — info dig expands monitor board only",
    }


def make_figs(day_rows: list[dict[str, Any]], decisions: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    hl = [r for r in day_rows if r.get("venue") == "hyperliquid" and r.get("native_tob")]

    # storm AS vs placebo
    fig, ax = plt.subplots(figsize=(5.5, 3.4))
    days = [r["day"][-5:] for r in hl]
    storm = [float((r.get("storm_markout_1s") or {}).get("mean_bps", np.nan)) for r in hl]
    plac = [float((r.get("placebo_storm_markout_1s") or {}).get("mean_bps", np.nan)) for r in hl]
    x = np.arange(len(days))
    if days:
        ax.bar(x - 0.18, storm, 0.35, label="storm", color="#e76f51")
        ax.bar(x + 0.18, plac, 0.35, label="placebo", color="#8d99ae")
        ax.set_xticks(x)
        ax.set_xticklabels(days)
        ax.axhline(0, color="k", lw=0.6)
        ax.legend(fontsize=8)
    ax.set_ylabel("markout bps @1s")
    ax.set_title("Storm adverse selection vs placebo (HL)")
    paths.append(_savefig(fig, "fig_info_storm_as.png"))

    # fade spread IRF
    fig, ax = plt.subplots(figsize=(5.5, 3.4))
    for r in hl:
        irf = r.get("fade_spread_irf") or {}
        lags = irf.get("lags_ms") or []
        d = irf.get("mean_delta_bps") or []
        if lags and d:
            ax.plot(lags, d, "-o", alpha=0.75, label=r["day"][-5:])
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlabel("lag ms")
    ax.set_ylabel("Δ spread bps vs pre")
    ax.set_title("Fade → spread widen IRF (HL)")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)
    paths.append(_savefig(fig, "fig_info_fade_spread_irf.png"))

    # unique mass forest
    fig, ax = plt.subplots(figsize=(5.2, 3.2))
    labs = decisions.get("labels") or {}
    ids, pts, los, his, cols = [], [], [], [], []
    for cid, g in labs.items():
        b = g.get("boot")
        if not b or b.get("n", 0) == 0:
            continue
        ids.append(cid.replace("info.", ""))
        pts.append(b["point"])
        los.append(b["lo"])
        his.append(b["hi"])
        cols.append("#2a9d8f" if g["decision"] == "Hold" else "#e76f51")
    if ids:
        y = np.arange(len(ids))
        ax.hlines(y, los, his, color="#6c757d")
        ax.scatter(pts, y, c=cols, zorder=3)
        ax.set_yticks(y)
        ax.set_yticklabels(ids, fontsize=7)
        ax.axvline(0, color="k", lw=0.5)
    ax.set_title("Info candidates day-block CI")
    paths.append(_savefig(fig, "fig_info_candidate_forest.png"))

    # clock funding
    fig, ax = plt.subplots(figsize=(5.5, 3.4))
    for r in hl:
        c = r.get("clock_funding") or {}
        ax.scatter(
            [c.get("max_z_out", np.nan)],
            [c.get("max_z_in", np.nan)],
            s=60,
            label=r["day"][-5:],
        )
    lim = ax.get_xlim()
    mx = max(lim[1], ax.get_ylim()[1], 1)
    ax.plot([0, mx], [0, mx], "k--", lw=0.8, label="y=x")
    ax.set_xlabel("max_z outside funding")
    ax.set_ylabel("max_z inside funding")
    ax.set_title("Clock excess vs funding windows (HL)")
    ax.legend(fontsize=7)
    paths.append(_savefig(fig, "fig_info_clock_funding.png"))

    # OFI / VPIN panel
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.3))
    for r in hl:
        axes[0].bar(r["day"][-5:], r.get("ofi_corr_ret", np.nan), color="#264653", alpha=0.8)
        axes[1].bar(r["day"][-5:], r.get("mean_vpin", np.nan), color="#e9c46a", alpha=0.9)
    axes[0].set_title("OFI–ret corr (HL)")
    axes[1].set_title("mean VPIN (HL)")
    for ax in axes:
        ax.tick_params(axis="x", rotation=30)
        ax.grid(True, axis="y", alpha=0.25)
    paths.append(_savefig(fig, "fig_info_ofi_vpin.png"))

    # xvenue IS
    fig, ax = plt.subplots(figsize=(5.5, 3.4))
    for r in hl:
        x = r.get("xvenue_is_around_fade") or {}
        lo, hi = x.get("mean_is_home_lo"), x.get("mean_is_home_hi")
        if lo is None or not np.isfinite(lo):
            continue
        ax.plot([lo, hi], [r["day"][-5:], r["day"][-5:]], solid_capstyle="round", lw=4, color="#457b9d")
        ax.scatter([0.5 * (lo + hi)], [r["day"][-5:]], color="#1d3557", zorder=3)
    ax.set_xlim(0, 1)
    ax.set_xlabel("Hasbrouck IS (home) around fade")
    ax.set_title("Xvenue info share @ fade (HL→far)")
    paths.append(_savefig(fig, "fig_info_xvenue_is_fade.png"))

    # ignition unique mass bars
    fig, ax = plt.subplots(figsize=(5.5, 3.4))
    for r in hl:
        u = (r.get("ignition_unique_mass") or {}).get("unique_mass", np.nan)
        ax.bar(r["day"][-5:], u, color="#2a9d8f")
    ax.axhline(0.5, color="#e76f51", ls="--", label="0.5 rename pressure")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("unique mass")
    ax.set_title("Ignition Phase1 unique mass vs Nanex/V")
    ax.legend(fontsize=8)
    paths.append(_savefig(fig, "fig_info_ignition_unique_mass.png"))

    return paths


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", nargs="+", default=DAYS_DEFAULT)
    ap.add_argument("--symbols", nargs="+", default=["ETH", "BTC"])
    ap.add_argument("--max-files", type=int, default=12)
    ap.add_argument("--max-trades", type=int, default=6000)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    FIGS.mkdir(parents=True, exist_ok=True)
    ensure_env()
    print("Info features days", args.days, flush=True)
    day_rows: list[dict[str, Any]] = []
    for symbol in args.symbols:
        for day in args.days:
            # preload far TOB (deribit) for HL xvenue
            far = None
            try:
                far = load_tob_any("deribit", symbol, day)
            except Exception:
                far = None
            for venue in CORE_VENUES:
                try:
                    far_use = far if venue == "hyperliquid" else None
                    row = dig_day(
                        venue,
                        symbol,
                        day,
                        max_files=args.max_files,
                        max_trades=args.max_trades,
                        far_tob=far_use,
                    )
                    day_rows.append(row)
                    print(
                        f"  {symbol} {venue:12s} {day} native={row.get('native_tob')} "
                        f"storm_as={row.get('storm_as_delta_vs_placebo')} "
                        f"uniq={(row.get('ignition_unique_mass') or {}).get('unique_mass')}",
                        flush=True,
                    )
                except Exception as exc:  # noqa: BLE001
                    print(f"  FAIL {symbol} {venue} {day}: {exc}", flush=True)
                    day_rows.append(
                        {
                            "venue": venue,
                            "symbol": symbol,
                            "day": day,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )

    # decisions on ETH HL primary + BTC as check
    eth_rows = [r for r in day_rows if r.get("symbol") == "ETH"]
    decisions = decide_candidates(eth_rows, args.days)
    # BTC check note
    btc_hl = [r for r in day_rows if r.get("symbol") == "BTC" and r.get("venue") == "hyperliquid" and r.get("native_tob")]
    decisions["btc_hl_storm_as_mean"] = float(
        np.nanmean([r.get("storm_as_delta_vs_placebo", np.nan) for r in btc_hl])
    ) if btc_hl else float("nan")

    fig_paths = make_figs([r for r in day_rows if r.get("symbol") == "ETH"], decisions)
    payload = {
        "days": args.days,
        "symbols": args.symbols,
        "day_rows": day_rows,
        "decisions": decisions,
        "fig_paths": fig_paths,
    }
    _json(OUT / "info_features.json", payload)
    print(
        f"Info board: {decisions['n_promote']} Promote / {decisions['n_hold']} Hold / {decisions['n_kill']} Kill"
    )
    for cid, g in decisions["labels"].items():
        print(f"  {g['decision']:7s} {cid}: {g['why'][:100]}")
    for p in fig_paths:
        print(" ", p)


if __name__ == "__main__":
    main()
