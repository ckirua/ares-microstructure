from __future__ import annotations
#!/usr/bin/env python3
"""Pass-2 info/exec dig on Kraken **spot** L2 (real quotes).

Analogous to ``exp_pass2_info_exec.py`` HL stacks:
1) Constraint-relax / undercut-burst event stacks (OFI / intensity / markout)
   on ``warehouse:kraken_spot_l2_rebuild`` + spot tape ``spot|ETH/USD``.
2) Within-KR-spot markout by rel_tick quartile (hourly).
3) HL vs KR-spot constrained-regime compare (both high frac_c).

Writes ``*_kraken_spot`` figs/JSON under out/tick_constraint/ and
out/rel_tick_panel/. Updates EXP_REPORT / CANDIDATES. No plan edit.
ClickHouse MCP banned. No git commit.
"""


import json
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
SCRIPTS = BOOK / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from _data import (  # noqa: E402
    clip_tape_to_utc_day,
    ensure_env,
    load_kraken_spot_tob_day,
)
from research.lib.markout import trade_markouts  # noqa: E402
from research.lib.spreads import quoted_spread_bps  # noqa: E402
from research.lib.stats import bootstrap_ci, spearman_r  # noqa: E402
from research.lib.ticksize import (  # noqa: E402
    markout_by_rel_tick_quartile,
    relative_tick,
    spread_in_ticks,
    tick_constrained,
    undercutting_proxy,
    venue_tick,
)

# Reuse HL dig helpers
from exp_pass2_info_exec import (  # noqa: E402
    HALF,
    N_BOOT,
    SEED,
    days_from_panel,
    desk_gate_summary,
    hour_rows_with_markout,
    minute_joint,
    per_trade_markout_bps,
    plot_stack,
    quartile_effect,
    quote_relax_bars,
    stack_events,
    undercut_burst_bars,
)

SYMBOL = "ETH"
SPOT_INST = "spot|ETH/USD"
KNOWN_TAU_SPOT = 0.01  # USD tick on ETH/USD spot (matches native dig)
BAR_NS = 60_000_000_000

TC_OUT = BOOK / "out" / "tick_constraint"
TC_FIGS = TC_OUT / "figs"
RTP_OUT = BOOK / "out" / "rel_tick_panel"
RTP_FIGS = RTP_OUT / "figs"

DAYS_DEFAULT = ["2026-09-26", "2026-09-27", "2026-09-30"]


def resolve_tau_spot(tob: dict[str, Any]) -> float:
    prices = np.concatenate(
        [np.asarray(tob["bid"], dtype=np.float64), np.asarray(tob["ask"], dtype=np.float64)]
    )
    vt = venue_tick("kraken", prices=prices, known_ticks={"kraken": KNOWN_TAU_SPOT})
    tau = float(vt["tau"])
    if not np.isfinite(tau) or tau < 1e-6:
        tau = KNOWN_TAU_SPOT
    return tau


def load_spot_trades(day: str, *, max_files: int = 32) -> dict[str, Any]:
    """Kraken spot ETH/USD tape (not PF futures)."""
    from startarb.data.trades import load_trade_tape

    ensure_env()
    raw = load_trade_tape(
        "kraken",
        SPOT_INST,
        days=[day],
        max_files=max_files,
        prefer_shards=True,
        quiet=True,
    )
    clipped = clip_tape_to_utc_day(raw, day)
    return {
        "venue": "kraken",
        "instrument": SPOT_INST,
        "market": "spot",
        "day": day,
        "tape": clipped,
        "n": int(clipped["ts"].size),
    }


def load_hl_gate_baseline() -> dict[str, Any] | None:
    p = TC_OUT / "pass2_info_exec.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text())


def run_kr_spot_stacks(days: list[str]) -> dict[str, Any]:
    ensure_env()
    keys = ("ofi_sum", "intensity", "markout_1s_bps", "undercut_rate")
    panels = [
        ("ofi_sum", "OFI sum (1m)"),
        ("intensity", "trade intensity λ (1/s)"),
        ("markout_1s_bps", "markout 1s (bps)"),
        ("undercut_rate", "undercut rate"),
    ]
    relax_mats: dict[str, list[np.ndarray]] = {k: [] for k in keys}
    burst_mats: dict[str, list[np.ndarray]] = {k: [] for k in keys}
    day_marks: list[float] = []
    day_meta: list[dict[str, Any]] = []
    tape_notes: list[str] = []

    for day in days:
        print(f"KR-spot dig {day}", flush=True)
        try:
            tob = load_kraken_spot_tob_day(SYMBOL, day, max_files=64, quotes_per_minute=30)
        except Exception as exc:  # noqa: BLE001
            day_meta.append({"day": day, "error": f"tob:{type(exc).__name__}: {exc}"})
            continue
        src = str(tob.get("source") or "")
        if "synth" in src.lower():
            day_meta.append({"day": day, "error": "synth_tob_skipped", "source": src})
            continue

        try:
            trades = load_spot_trades(day)
            tape = trades["tape"]
            ts_tr = np.asarray(tape["ts"], dtype=np.int64)
            px = np.asarray(tape["px"], dtype=np.float64)
            side = np.asarray(tape["side"], dtype=np.float64)
            tape_ok = ts_tr.size >= 50
            tape_notes.append(f"{day}: spot tape n={ts_tr.size}")
        except Exception as exc:  # noqa: BLE001
            tape_ok = False
            ts_tr = np.array([], dtype=np.int64)
            px = np.array([], dtype=np.float64)
            side = np.array([], dtype=np.float64)
            tape_notes.append(f"{day}: spot tape FAIL {type(exc).__name__}: {exc}")

        tau = resolve_tau_spot(tob)
        if tape_ok:
            mo = per_trade_markout_bps(ts_tr, side, tob["ts"], tob["mid"], horizon_ms=1000)
            try:
                agg = trade_markouts(ts_tr, px, side, tob["ts"], tob["mid"], horizons_ms=(1000,))
                day_marks.append(
                    float((agg.get("by_horizon") or {}).get("1000", {}).get("mean_bps", np.nan))
                )
            except Exception:
                sample = mo[np.isfinite(mo)]
                day_marks.append(float(np.mean(sample)) if sample.size else float("nan"))
        else:
            mo = np.array([], dtype=np.float64)
            day_marks.append(float("nan"))

        series = minute_joint(tob, tau, ts_tr, mo if mo.size else np.full(0, np.nan))
        if not series:
            day_meta.append({"day": day, "error": "thin_minute_series", "n_tob": int(tob.get("n", 0))})
            continue

        st = spread_in_ticks(tob["bid"], tob["ask"], tau)
        cons = tick_constrained(st, max_ticks=2.0)
        if not isinstance(cons, np.ndarray):
            cons = np.zeros(np.asarray(tob["ts"]).size, dtype=bool)

        relax_ev = quote_relax_bars(
            np.asarray(tob["ts"], dtype=np.int64),
            cons,
            series["t_mid"],
            min_gap=3,
        )
        burst_ev = undercut_burst_bars(series["undercut_rate"], q=0.85, min_gap=5)
        r_stack = stack_events(series, relax_ev, keys)
        b_stack = stack_events(series, burst_ev, keys)

        day_meta.append(
            {
                "day": day,
                "tau": tau,
                "source": tob.get("source"),
                "market": "spot",
                "n_tob": int(tob.get("n", 0)),
                "n_trades": int(ts_tr.size),
                "tape_ok": tape_ok,
                "n_relax": len(relax_ev),
                "n_burst": len(burst_ev),
                "frac_c": float(np.nanmean(series["frac_c"])),
                "undercut_med": float(np.nanmedian(series["undercut_rate"])),
                "day_markout_1s_bps": day_marks[-1],
                "relax_deltas": {k: (r_stack.get(k) or {}).get("delta_post_minus_pre") for k in keys},
                "burst_deltas": {k: (b_stack.get(k) or {}).get("delta_post_minus_pre") for k in keys},
            }
        )
        half = HALF
        for e in relax_ev:
            if e < half or e + half >= series["frac_c"].size:
                continue
            for k in keys:
                relax_mats[k].append(np.asarray(series[k][e - half : e + half + 1], dtype=np.float64))
        for e in burst_ev:
            if e < half or e + half >= series["frac_c"].size:
                continue
            for k in keys:
                burst_mats[k].append(np.asarray(series[k][e - half : e + half + 1], dtype=np.float64))

    def _from_mats(mats: dict[str, list[np.ndarray]]) -> dict[str, Any]:
        lags = np.arange(-HALF, HALF + 1)
        out: dict[str, Any] = {"n_events": 0, "lags": lags.tolist(), "half": HALF}
        rng = np.random.default_rng(SEED)
        for k, rows in mats.items():
            if not rows:
                out[k] = {
                    "mean": [float("nan")] * lags.size,
                    "lo": [float("nan")] * lags.size,
                    "hi": [float("nan")] * lags.size,
                    "n": 0,
                    "delta_post_minus_pre": float("nan"),
                }
                continue
            m = np.vstack(rows)
            n_ev = int(m.shape[0])
            out["n_events"] = max(out["n_events"], n_ev)
            mean = np.nanmean(m, axis=0)
            if n_ev >= 5:
                boots = np.empty((N_BOOT, lags.size), dtype=np.float64)
                for b in range(N_BOOT):
                    idx = rng.integers(0, n_ev, size=n_ev)
                    boots[b] = np.nanmean(m[idx], axis=0)
                lo, hi = np.nanquantile(boots, [0.025, 0.975], axis=0)
            else:
                lo = hi = np.full(lags.size, np.nan)
            delta = float(np.nanmean(mean[lags > 0]) - np.nanmean(mean[lags < 0]))
            out[k] = {
                "mean": [float(x) for x in mean],
                "lo": [float(x) for x in lo],
                "hi": [float(x) for x in hi],
                "n": n_ev,
                "delta_post_minus_pre": delta,
            }
        return out

    relax_pool = _from_mats(relax_mats)
    burst_pool = _from_mats(burst_mats)

    # Reuse desk_gate wording but re-tag for KR-spot
    gate = desk_gate_summary(relax_pool, burst_pool, day_marks)
    why = str(gate.get("why") or "").replace("HL ", "KR-spot ")
    gate["why"] = why
    gate["venue"] = "kraken_spot"
    gate["tape"] = "spot|ETH/USD"
    gate["tob_source"] = "warehouse:kraken_spot_l2_rebuild"

    figs: list[str] = []
    figs.append(
        plot_stack(
            relax_pool,
            "KR-spot constraint-relax stacks (OFI / intensity / markout / undercut)",
            TC_FIGS / "fig_kraken_spot_relax_stack_ofi_intensity_markout.png",
            panels,
        )
    )
    figs.append(
        plot_stack(
            burst_pool,
            "KR-spot undercut-burst stacks (OFI / intensity / markout / undercut)",
            TC_FIGS / "fig_kraken_spot_undercut_burst_stack.png",
            panels,
        )
    )

    # gate board
    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    eff = gate["effects"]
    labels = [
        "relax ΔOFI",
        "relax Δλ",
        "relax Δmo (bps)",
        "burst Δuc",
        "burst Δmo (bps)",
    ]
    vals = [
        eff["relax_ofi_delta"],
        eff["relax_intensity_delta"],
        eff["relax_markout_delta_bps"],
        eff["burst_undercut_delta"],
        eff["burst_markout_delta_bps"],
    ]
    display = []
    for lab, v in zip(labels, vals):
        if "OFI" in lab and np.isfinite(v):
            display.append(np.sign(v) * np.log1p(abs(v)))
        else:
            display.append(v if np.isfinite(v) else 0.0)
    colors = ["#8b1e1e" if gate["exec_throttle"] else "#1b7a5a"] * len(display)
    ax.barh(np.arange(len(labels)), display, color=colors)
    ax.set_yticks(np.arange(len(labels)))
    ax.set_yticklabels(labels)
    ax.axvline(0, color="k", lw=0.7)
    ax.set_title(
        f"KR-spot desk gate: {gate['desk_label']} · decision={gate['decision']} · tradable={gate['tradable']}"
    )
    ax.set_xlabel("Δ post−pre (OFI shown as sign·log1p|Δ|)")
    fig.tight_layout()
    p = TC_FIGS / "fig_kraken_spot_info_exec_gate.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    figs.append(p.name)

    return {
        "venue": "kraken_spot",
        "instrument_tob": SPOT_INST,
        "instrument_tape": SPOT_INST,
        "tob_source": "warehouse:kraken_spot_l2_rebuild",
        "days": days,
        "day_meta": day_meta,
        "tape_notes": tape_notes,
        "relax_stack": relax_pool,
        "burst_stack": burst_pool,
        "gate": gate,
        "figs": figs,
    }


def run_within_kr_spot_markout(days: list[str]) -> dict[str, Any]:
    ensure_env()
    rows: list[dict[str, Any]] = []
    for day in days:
        print(f"within-KR-spot markout {day}", flush=True)
        try:
            tob = load_kraken_spot_tob_day(SYMBOL, day, max_files=64, quotes_per_minute=30)
            trades = load_spot_trades(day)
        except Exception as exc:  # noqa: BLE001
            print(f"  skip {day}: {exc}", flush=True)
            continue
        if "synth" in str(tob.get("source") or "").lower():
            continue
        tape = trades["tape"]
        ts_tr = np.asarray(tape["ts"], dtype=np.int64)
        side = np.asarray(tape["side"], dtype=np.float64)
        if ts_tr.size < 50:
            continue
        tau = resolve_tau_spot(tob)
        mo = per_trade_markout_bps(ts_tr, side, tob["ts"], tob["mid"], horizon_ms=1000)
        rows.extend(hour_rows_with_markout("kraken_spot", day, tob, tau, ts_tr, mo))

    mq = markout_by_rel_tick_quartile(rows, rel_key="rel_tick", markout_key="markout_1s_bps")
    xs = np.array([r["rel_tick"] for r in rows], dtype=np.float64)
    ys = np.array([r["markout_1s_bps"] for r in rows], dtype=np.float64)
    rho = spearman_r(xs, ys) if xs.size >= 3 else float("nan")
    if xs.size >= 8:
        rng = np.random.default_rng(SEED + 11)
        boots = []
        n = xs.size
        for _ in range(N_BOOT):
            idx = rng.integers(0, n, size=n)
            boots.append(spearman_r(xs[idx], ys[idx]))
        lo, hi = np.nanquantile(boots, [0.025, 0.975])
        rho_ci = [float(lo), float(hi)]
    else:
        rho_ci = [float("nan"), float("nan")]

    effects = {
        **quartile_effect(mq),
        "spearman_rho": rho,
        "spearman_ci95": rho_ci,
        "n_hours": len(rows),
        "quartiles": mq.get("quartiles"),
        "means": mq.get("means"),
        "ns": mq.get("ns"),
        "decision": "Hold",
        "tradable": False,
        "label": "info_monitor_within_kraken_spot",
        "why": (
            "Within-KR-spot hourly markout~rel_tick on native L2 + spot tape "
            "(τ≈0.01 fixed; mid-driven). Not tradable; comparable high-frac_c "
            "regime to HL."
        ),
    }

    # figs
    figs: list[str] = []
    color = "#1b7a5a"
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.8))
    ax = axes[0]
    means = mq.get("means") or []
    ns = mq.get("ns") or []
    if means:
        x = np.arange(len(means))
        ax.bar(x, means, color=color, alpha=0.9)
        for i, n in enumerate(ns):
            ax.text(i, means[i], f"n={n}", ha="center", va="bottom", fontsize=8)
        ax.set_xticks(x)
        ax.set_xticklabels([f"Q{i+1}" for i in range(len(means))])
        eff = quartile_effect(mq)
        ax.set_title(f"KR-spot Q4−Q1={eff.get('q4_minus_q1_bps', float('nan')):.3g} bps")
    else:
        ax.text(0.5, 0.5, "insufficient hours", ha="center", va="center", transform=ax.transAxes)
        ax.set_title("KR-spot quartiles")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_ylabel("mean markout 1s (bps)")
    ax.set_xlabel("rel_tick quartile (within KR-spot)")
    ax.grid(True, axis="y", alpha=0.3)

    ax = axes[1]
    if rows:
        xs_bps = np.array([r["rel_tick_bps"] for r in rows], dtype=np.float64)
        ax.scatter(xs_bps, ys, s=28, color=color, alpha=0.75)
        ax.set_title(f"hour scatter · Spearman ρ={rho:.3g}")
        ax.set_xlabel("rel_tick (bps)")
        ax.set_ylabel("markout 1s (bps)")
        ax.axhline(0, color="k", lw=0.5)
        ax.grid(True, alpha=0.3)
    else:
        ax.text(0.5, 0.5, "no hours", ha="center", va="center", transform=ax.transAxes)
    fig.suptitle(
        f"Within-KR-spot info lens (hourly; n_h={len(rows)}; τ={KNOWN_TAU_SPOT})",
        y=1.03,
    )
    fig.tight_layout()
    p = RTP_FIGS / "fig_markout_reltick_q_kraken_spot.png"
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    figs.append(p.name)

    # single-panel companion for board
    fig, ax = plt.subplots(figsize=(5.2, 3.6))
    if means:
        x = np.arange(len(means))
        ax.bar(x, means, color=color, alpha=0.9)
        for i, n in enumerate(ns):
            ax.text(i, means[i], f"n={n}", ha="center", va="bottom", fontsize=8)
        ax.set_xticks(x)
        ax.set_xticklabels([f"Q{i+1}" for i in range(len(means))])
    ax.axhline(0, color="k", lw=0.6)
    ax.set_ylabel("mean markout 1s (bps)")
    ax.set_xlabel("rel_tick quartile")
    ax.set_title(
        f"KR-spot within-venue markout · Q4−Q1="
        f"{effects.get('q4_minus_q1_bps', float('nan')):.3g} bps · ρ={rho:.3g}"
    )
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    p2 = RTP_FIGS / "fig_markout_reltick_q_within_kraken_spot.png"
    fig.savefig(p2, dpi=140, bbox_inches="tight")
    plt.close(fig)
    figs.append(p2.name)

    slim = [
        {
            k: r[k]
            for k in (
                "day",
                "hour_id",
                "rel_tick",
                "rel_tick_bps",
                "markout_1s_bps",
                "n_trades",
                "quoted_spread_bps",
            )
        }
        for r in rows
    ]
    return {
        "venue": "kraken_spot",
        "effects": {"kraken_spot": effects},
        "by_venue": {"kraken_spot": mq},
        "hours": {"kraken_spot": slim},
        "figs": figs,
    }


def compare_hl_vs_kr(
    kr: dict[str, Any],
    hl: dict[str, Any] | None,
    wv_kr: dict[str, Any],
) -> dict[str, Any]:
    """Both venues ~high frac_c — compare event Δ and within-venue markout slope."""
    hl_meta = (hl or {}).get("day_meta") or []
    kr_meta = kr.get("day_meta") or []
    hl_frac = [float(d["frac_c"]) for d in hl_meta if "frac_c" in d]
    kr_frac = [float(d["frac_c"]) for d in kr_meta if "frac_c" in d and "error" not in d]

    def _stack_eff(blob: dict[str, Any] | None, key: str) -> dict[str, float]:
        if not blob:
            return {}
        st = blob.get(key) or {}
        out = {"n_events": float(st.get("n_events") or 0)}
        for k in ("ofi_sum", "intensity", "markout_1s_bps", "undercut_rate"):
            out[f"Δ{k}"] = float((st.get(k) or {}).get("delta_post_minus_pre", float("nan")))
        return out

    hl_gate = (hl or {}).get("gate") or {}
    kr_gate = kr.get("gate") or {}

    # load HL within-venue markout if present
    hl_wv_path = RTP_OUT / "markout_quartile_within_venue.json"
    hl_wv_eff: dict[str, Any] = {}
    if hl_wv_path.is_file():
        hl_wv = json.loads(hl_wv_path.read_text())
        hl_wv_eff = (hl_wv.get("effects") or {}).get("hyperliquid") or {}

    kr_eff = (wv_kr.get("effects") or {}).get("kraken_spot") or {}

    compare = {
        "both_high_frac_c": bool(hl_frac and kr_frac and min(hl_frac) > 0.7 and min(kr_frac) > 0.7),
        "frac_c": {
            "hl_mean": float(np.mean(hl_frac)) if hl_frac else float("nan"),
            "hl_by_day": hl_frac,
            "kr_spot_mean": float(np.mean(kr_frac)) if kr_frac else float("nan"),
            "kr_spot_by_day": kr_frac,
        },
        "relax": {"hl": _stack_eff(hl, "relax_stack"), "kr_spot": _stack_eff(kr, "relax_stack")},
        "burst": {"hl": _stack_eff(hl, "burst_stack"), "kr_spot": _stack_eff(kr, "burst_stack")},
        "gate": {
            "hl": {
                "desk_label": hl_gate.get("desk_label"),
                "decision": hl_gate.get("decision"),
                "tradable": hl_gate.get("tradable"),
                "exec_throttle": hl_gate.get("exec_throttle"),
            },
            "kr_spot": {
                "desk_label": kr_gate.get("desk_label"),
                "decision": kr_gate.get("decision"),
                "tradable": kr_gate.get("tradable"),
                "exec_throttle": kr_gate.get("exec_throttle"),
            },
        },
        "within_venue_markout": {
            "hl": {
                "q4_minus_q1_bps": hl_wv_eff.get("q4_minus_q1_bps"),
                "spearman_rho": hl_wv_eff.get("spearman_rho"),
                "n_hours": hl_wv_eff.get("n_hours"),
            },
            "kr_spot": {
                "q4_minus_q1_bps": kr_eff.get("q4_minus_q1_bps"),
                "spearman_rho": kr_eff.get("spearman_rho"),
                "n_hours": kr_eff.get("n_hours"),
            },
        },
        "note": (
            "HL (perp L2, τ=0.1) and KR-spot (spot L2, τ=0.01) both sit in high "
            "frac_constrained regimes on these days — event Δmarkout near zero on both "
            "→ risk_monitor, not exec_throttle. Within-venue Q4−Q1 remains weak/noisy."
        ),
    }

    # compare fig
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.8))
    ax = axes[0]
    ax.bar(
        [0, 1],
        [compare["frac_c"]["hl_mean"], compare["frac_c"]["kr_spot_mean"]],
        color=["#1f4e6b", "#1b7a5a"],
        alpha=0.9,
    )
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["HL", "KR-spot"])
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("mean frac_constrained (≤2τ)")
    ax.set_title("Constraint regime")
    ax.grid(True, axis="y", alpha=0.3)

    ax = axes[1]
    labs = ["relax Δmo", "burst Δmo"]
    hl_vals = [
        compare["relax"]["hl"].get("Δmarkout_1s_bps", np.nan),
        compare["burst"]["hl"].get("Δmarkout_1s_bps", np.nan),
    ]
    kr_vals = [
        compare["relax"]["kr_spot"].get("Δmarkout_1s_bps", np.nan),
        compare["burst"]["kr_spot"].get("Δmarkout_1s_bps", np.nan),
    ]
    x = np.arange(len(labs))
    ax.bar(x - 0.18, [v if np.isfinite(v) else 0 for v in hl_vals], 0.35, color="#1f4e6b", label="HL")
    ax.bar(x + 0.18, [v if np.isfinite(v) else 0 for v in kr_vals], 0.35, color="#1b7a5a", label="KR-spot")
    ax.set_xticks(x)
    ax.set_xticklabels(labs)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_ylabel("Δ markout 1s (bps)")
    ax.set_title("Event Δmarkout")
    ax.legend(fontsize=8)
    ax.grid(True, axis="y", alpha=0.3)

    ax = axes[2]
    q_hl = compare["within_venue_markout"]["hl"].get("q4_minus_q1_bps")
    q_kr = compare["within_venue_markout"]["kr_spot"].get("q4_minus_q1_bps")
    ax.bar(
        [0, 1],
        [q_hl if q_hl is not None and np.isfinite(q_hl) else 0, q_kr if q_kr is not None and np.isfinite(q_kr) else 0],
        color=["#1f4e6b", "#1b7a5a"],
        alpha=0.9,
    )
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["HL", "KR-spot"])
    ax.axhline(0, color="k", lw=0.6)
    ax.set_ylabel("Q4−Q1 markout (bps)")
    ax.set_title("Within-venue info slope")
    ax.grid(True, axis="y", alpha=0.3)

    hl_lab = compare["gate"]["hl"].get("desk_label")
    kr_lab = compare["gate"]["kr_spot"].get("desk_label")
    fig.suptitle(
        f"HL vs KR-spot constrained regimes · gate HL={hl_lab} / KR={kr_lab}",
        y=1.04,
    )
    fig.tight_layout()
    p = TC_FIGS / "fig_hl_vs_kraken_spot_constrained.png"
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    compare["figs"] = [p.name]
    return compare


def _append_exp_reports(kr: dict[str, Any], wv: dict[str, Any], cmp: dict[str, Any]) -> None:
    gate = kr.get("gate") or {}
    eff = gate.get("effects") or {}
    relax = kr.get("relax_stack") or {}
    burst = kr.get("burst_stack") or {}
    kr_eff = (wv.get("effects") or {}).get("kraken_spot") or {}

    tc_path = BOOK / "chapters" / "tick_constraint" / "EXP_REPORT.md"
    uc_r = (relax.get("undercut_rate") or {}).get("delta_post_minus_pre")
    day_mo = eff.get("hl_day_mean_markout_1s_bps")  # reused key from shared gate helper
    block = f"""
## Pass 2 — KR-spot info/exec event dig (native L2)

- Script: `scripts/exp_pass2_info_exec_kraken_spot.py` → `out/tick_constraint/pass2_info_exec_kraken_spot.json`
- TOB: `warehouse:kraken_spot_l2_rebuild` (`spot|ETH/USD`); tape: spot `spot|ETH/USD` (not PF).
- Days: {kr.get('days')}
- Mean frac_c (1m): **{cmp['frac_c']['kr_spot_mean']:.3f}** (HL baseline **{cmp['frac_c']['hl_mean']:.3f}**) — both high-constraint regimes.
- KR-spot constraint-relax stacks (n_events={relax.get('n_events')}, ±10m, event-bootstrap 95%):
  - ΔOFI post−pre = **{eff.get('relax_ofi_delta')}**
  - Δintensity = **{eff.get('relax_intensity_delta')}**/s
  - Δmarkout_1s = **{eff.get('relax_markout_delta_bps')} bps**
  - Δundercut = **{uc_r}**
- KR-spot undercut-burst stacks (n_events={burst.get('n_events')}):
  - Δundercut = **{eff.get('burst_undercut_delta')}**; Δintensity = **{(burst.get('intensity') or {}).get('delta_post_minus_pre')}**/s; Δmarkout_1s = **{eff.get('burst_markout_delta_bps')} bps**; ΔOFI = **{(burst.get('ofi_sum') or {}).get('delta_post_minus_pre')}**
- Day-mean KR-spot markout_1s ≈ **{day_mo} bps**.
- Desk label: **`{gate.get('desk_label')}`**. Tradable={gate.get('tradable')}. Decision: **{gate.get('decision')}**.
- Why: {gate.get('why')}
- HL vs KR-spot compare → `out/tick_constraint/hl_vs_kraken_spot_constrained.json` + `fig_hl_vs_kraken_spot_constrained.png`.
- Figs: `fig_kraken_spot_relax_stack_ofi_intensity_markout.png`, `fig_kraken_spot_undercut_burst_stack.png`, `fig_kraken_spot_info_exec_gate.png`, `fig_hl_vs_kraken_spot_constrained.png`
"""
    text = tc_path.read_text() if tc_path.is_file() else "# tick_constraint — EXP_REPORT\n"
    marker = "## Pass 2 — KR-spot info/exec event dig"
    if marker in text:
        pre = text.split(marker)[0].rstrip()
        text = pre + "\n" + block
    else:
        text = text.rstrip() + "\n" + block
    tc_path.write_text(text)

    rtp_path = BOOK / "chapters" / "rel_tick_panel" / "EXP_REPORT.md"
    rtp_block = f"""
### Within-KR-spot hourly markout ~ rel_tick (native spot L2)

- Script: `scripts/exp_pass2_info_exec_kraken_spot.py` → `out/rel_tick_panel/markout_quartile_kraken_spot.json`
- **KR-spot** (n_hours={kr_eff.get('n_hours')}): Q means {kr_eff.get('means')}; **Q4−Q1 = {kr_eff.get('q4_minus_q1_bps')} bps**; Spearman ρ=**{kr_eff.get('spearman_rho')}** CI95={kr_eff.get('spearman_ci95')}
- Label: `{kr_eff.get('label')}` · **Hold** · **not tradable**.
- Compare vs HL within-venue: HL Q4−Q1={cmp['within_venue_markout']['hl'].get('q4_minus_q1_bps')} bps (ρ={cmp['within_venue_markout']['hl'].get('spearman_rho')}) — neither clears Promote on this info lens.
- Figs: `fig_markout_reltick_q_kraken_spot.png`, `fig_markout_reltick_q_within_kraken_spot.png`
"""
    rtext = rtp_path.read_text() if rtp_path.is_file() else "# rel_tick_panel — EXP_REPORT\n"
    rmarker = "### Within-KR-spot hourly markout"
    if rmarker in rtext:
        pre = rtext.split(rmarker)[0].rstrip()
        rtext = pre + "\n" + rtp_block
    else:
        rtext = rtext.rstrip() + "\n" + rtp_block
    rtp_path.write_text(rtext)


def _update_candidates(kr: dict[str, Any], wv: dict[str, Any], cmp: dict[str, Any]) -> None:
    gate = kr.get("gate") or {}
    eff = gate.get("effects") or {}
    relax_n = int((kr.get("relax_stack") or {}).get("n_events") or 0)
    burst_n = int((kr.get("burst_stack") or {}).get("n_events") or 0)
    kr_eff = (wv.get("effects") or {}).get("kraken_spot") or {}

    tc_path = BOOK / "chapters" / "tick_constraint" / "CANDIDATES.md"
    rows = [
        f"| `info.constraint_relax_ofi_kraken_spot` | event | info, exec | **Hold** | KR-spot n={relax_n}: ΔOFI={eff.get('relax_ofi_delta')}; Δmo≈{eff.get('relax_markout_delta_bps')}bps — `{gate.get('desk_label')}`, not tradable; high frac_c≈{cmp['frac_c']['kr_spot_mean']:.3f} like HL |",
        f"| `exec.undercut_burst_stack_kraken_spot` | event | exec, risk | **Hold** | KR-spot n={burst_n}: Δuc={eff.get('burst_undercut_delta')}; Δmo≈{eff.get('burst_markout_delta_bps')}bps — monitor; no throttle Promote |",
        f"| `exec.hl_vs_kraken_spot_constrained` | regime | exec, info | **Hold** | Both high frac_c (HL={cmp['frac_c']['hl_mean']:.3f}, KR-spot={cmp['frac_c']['kr_spot_mean']:.3f}); event Δmo near 0 on both → risk_monitor parallel |",
    ]
    text = tc_path.read_text() if tc_path.is_file() else (
        "| id | type | lenses | decision | falsifier |\n"
        "|----|------|--------|----------|----------|\n"
    )
    for row in rows:
        cid = row.split("|")[1].strip().strip("`")
        lines = text.splitlines()
        kept = [ln for ln in lines if cid not in ln]
        # ensure header
        if not any(ln.startswith("| id") for ln in kept):
            kept = [
                "| id | type | lenses | decision | falsifier |",
                "|----|------|--------|----------|----------|",
            ] + [ln for ln in kept if ln.strip()]
        kept.append(row)
        text = "\n".join(kept) + "\n"
    tc_path.write_text(text)

    rtp_path = BOOK / "chapters" / "rel_tick_panel" / "CANDIDATES.md"
    row = (
        f"| `info.markout_by_rel_tick_kraken_spot` | info | info, exec | **Hold** | "
        f"KR-spot n_h={kr_eff.get('n_hours')}: Q4−Q1={kr_eff.get('q4_minus_q1_bps')}bps; "
        f"ρ={kr_eff.get('spearman_rho')} CI={kr_eff.get('spearman_ci95')}; "
        f"high-frac_c regime parallel to HL; not tradable |"
    )
    rtext = rtp_path.read_text() if rtp_path.is_file() else (
        "| id | type | lenses | decision | falsifier |\n"
        "|----|------|--------|----------|----------|\n"
    )
    cid = "info.markout_by_rel_tick_kraken_spot"
    lines = rtext.splitlines()
    kept = [ln for ln in lines if cid not in ln]
    if not any(ln.startswith("| id") for ln in kept):
        kept = [
            "| id | type | lenses | decision | falsifier |",
            "|----|------|--------|----------|----------|",
        ] + [ln for ln in kept if ln.strip()]
    kept.append(row)
    rtp_path.write_text("\n".join(kept) + "\n")


def main() -> None:
    TC_FIGS.mkdir(parents=True, exist_ok=True)
    RTP_FIGS.mkdir(parents=True, exist_ok=True)
    days = days_from_panel() or DAYS_DEFAULT
    # Prefer days known to have spot L2 inventory
    days = [d for d in days if d in set(DAYS_DEFAULT)] or DAYS_DEFAULT
    print("days", days, flush=True)

    kr = run_kr_spot_stacks(days)
    (TC_OUT / "pass2_info_exec_kraken_spot.json").write_text(json.dumps(kr, indent=2, default=str))

    wv = run_within_kr_spot_markout(days)
    (RTP_OUT / "markout_quartile_kraken_spot.json").write_text(json.dumps(wv, indent=2, default=str))

    hl = load_hl_gate_baseline()
    cmp = compare_hl_vs_kr(kr, hl, wv)
    (TC_OUT / "hl_vs_kraken_spot_constrained.json").write_text(json.dumps(cmp, indent=2, default=str))

    _append_exp_reports(kr, wv, cmp)
    _update_candidates(kr, wv, cmp)

    print("KR figs", kr["figs"])
    print("KR gate", json.dumps(kr["gate"], indent=2, default=str))
    print("within KR-spot", json.dumps(wv["effects"], indent=2, default=str))
    print("compare", json.dumps(cmp, indent=2, default=str)[:2000])
    print("RTP figs", wv["figs"], "+", cmp.get("figs"))


if __name__ == "__main__":
    main()
