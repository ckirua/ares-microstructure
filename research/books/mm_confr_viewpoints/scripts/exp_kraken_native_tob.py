#!/usr/bin/env python3
"""Native Kraken spot L2 vs futures trade_synth — focused compare for mm_confr.

Loads ``spot|ETH/USD`` (and BTC if cheap) via ``load_kraken_spot_tob_day``,
compares to futures ``PF_*`` trade_synth BBO, writes constraint / spread figs
and a gate-impact JSON under ``out/kraken_native/``.

Honesty: futures PF_* still have **no** L2 in mercat-kraken-md; spot L2 is
the native path for MQ / tick-constraint. ClickHouse MCP banned. No git commit.
"""

from __future__ import annotations

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
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from _data import (  # noqa: E402
    ensure_env,
    load_kraken_spot_tob_day,
    load_warehouse_tob,
)
from research.lib.ticksize import (  # noqa: E402
    spread_in_ticks,
    tick_constrained,
    venue_tick,
)

OUT = BOOK / "out" / "kraken_native"
FIGS = OUT / "figs"
DAYS_ETH = ["2026-09-26", "2026-09-27", "2026-09-30"]
DAYS_BTC = ["2026-09-27"]


def _json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str))


def _spread_bps(bid: np.ndarray, ask: np.ndarray) -> np.ndarray:
    mid = 0.5 * (bid + ask)
    return 1e4 * (ask - bid) / np.maximum(mid, 1e-12)


def _known_tau(symbol: str, bid: np.ndarray, ask: np.ndarray) -> float:
    prices = np.concatenate([bid, ask])
    known = {
        "ETH": {"kraken": 0.01},  # spot USD tick common; futures often 0.05
        "BTC": {"kraken": 0.1},
    }.get(symbol, {})
    vt = venue_tick("kraken", prices=prices, known_ticks=known or None)
    tau = float(vt["tau"])
    if not np.isfinite(tau) or tau < 1e-6:
        tau = known.get("kraken", 0.01)
    return tau


def summarize_tob(symbol: str, day: str, tob: dict[str, Any], *, kind: str) -> dict[str, Any]:
    bid = np.asarray(tob["bid"], dtype=np.float64)
    ask = np.asarray(tob["ask"], dtype=np.float64)
    mid = np.asarray(tob.get("mid", 0.5 * (bid + ask)), dtype=np.float64)
    spr = _spread_bps(bid, ask)
    tau = _known_tau(symbol, bid, ask)
    st = spread_in_ticks(bid, ask, tau)
    constrained = tick_constrained(st, max_ticks=2.0)
    frac_c = float(np.mean(constrained)) if getattr(constrained, "size", 0) else float(constrained)
    return {
        "symbol": symbol,
        "day": day,
        "kind": kind,
        "source": tob.get("source"),
        "table": tob.get("table"),
        "market": tob.get("market"),
        "is_synth": bool(tob.get("is_synth")) or ("synth" in str(tob.get("source", "")).lower()),
        "n": int(tob.get("n", bid.size)),
        "tau": tau,
        "med_mid": float(np.nanmedian(mid)),
        "med_spread_bps": float(np.nanmedian(spr)),
        "p90_spread_bps": float(np.nanpercentile(spr, 90)),
        "mean_spread_bps": float(np.nanmean(spr)),
        "med_spread_ticks": float(np.nanmedian(st)) if st.size else float("nan"),
        "frac_constrained_2tick": frac_c,
        "frac_one_tick": float(np.mean(st <= 1.0 + 1e-9)) if st.size else float("nan"),
        "med_bid_sz": float(np.nanmedian(np.asarray(tob.get("bid_sz"), dtype=np.float64)))
        if tob.get("bid_sz") is not None and np.isfinite(np.asarray(tob.get("bid_sz"), dtype=np.float64)).any()
        else float("nan"),
        "med_ask_sz": float(np.nanmedian(np.asarray(tob.get("ask_sz"), dtype=np.float64)))
        if tob.get("ask_sz") is not None and np.isfinite(np.asarray(tob.get("ask_sz"), dtype=np.float64)).any()
        else float("nan"),
    }


def load_pair(symbol: str, day: str) -> dict[str, Any]:
    out: dict[str, Any] = {"symbol": symbol, "day": day}
    try:
        native = load_kraken_spot_tob_day(symbol, day, max_files=64, quotes_per_minute=30)
        out["native"] = summarize_tob(symbol, day, native, kind="spot_l2")
        out["native_tob"] = {
            "ts": native["ts"],
            "bid": native["bid"],
            "ask": native["ask"],
            "mid": native["mid"],
            "spread_bps": _spread_bps(native["bid"], native["ask"]),
        }
    except Exception as exc:  # noqa: BLE001
        out["native_error"] = f"{type(exc).__name__}: {exc}"
    try:
        synth = load_warehouse_tob(
            "kraken",
            symbol,
            day,
            prefer_kraken_spot_l2=False,
            allow_trade_fallback=True,
            max_files=24,
            quotes_per_minute=20,
        )
        out["synth"] = summarize_tob(symbol, day, synth, kind="futures_trade_synth")
        out["synth_tob"] = {
            "ts": synth["ts"],
            "bid": synth["bid"],
            "ask": synth["ask"],
            "mid": synth["mid"],
            "spread_bps": _spread_bps(synth["bid"], synth["ask"]),
        }
    except Exception as exc:  # noqa: BLE001
        out["synth_error"] = f"{type(exc).__name__}: {exc}"
    return out


def fig_spread_compare(pairs: list[dict[str, Any]], path: Path) -> None:
    fig, axes = plt.subplots(1, len(pairs), figsize=(4.2 * max(len(pairs), 1), 3.6), squeeze=False)
    for ax, p in zip(axes[0], pairs):
        day = p["day"]
        rows = []
        if "native" in p:
            rows.append(("spot L2", p["native"]["med_spread_bps"], "#1b9e77"))
        if "synth" in p:
            rows.append(("trade_synth", p["synth"]["med_spread_bps"], "#d95f02"))
        if not rows:
            ax.set_title(f"{day}\n(no data)")
            continue
        labels, vals, colors = zip(*rows)
        ax.bar(labels, vals, color=colors, alpha=0.9)
        ax.set_ylabel("median spread (bps)")
        ax.set_title(f"ETH {day}")
        ax.set_yscale("log")
        for i, v in enumerate(vals):
            ax.text(i, v * 1.15, f"{v:.3g}", ha="center", fontsize=8)
    fig.suptitle("Kraken ETH: native spot L2 vs futures trade_synth spread", y=1.02)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def fig_constraint_compare(rows: list[dict[str, Any]], path: Path) -> None:
    days = sorted({r["day"] for r in rows})
    kinds = ["spot_l2", "futures_trade_synth"]
    x = np.arange(len(days))
    w = 0.35
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    for i, kind in enumerate(kinds):
        ys = []
        for d in days:
            hit = next((r for r in rows if r["day"] == d and r["kind"] == kind), None)
            ys.append(hit["frac_constrained_2tick"] if hit else np.nan)
        ax.bar(
            x + (i - 0.5) * w,
            ys,
            w,
            label="spot L2" if kind == "spot_l2" else "trade_synth",
            color="#1b9e77" if kind == "spot_l2" else "#d95f02",
            alpha=0.9,
        )
    ax.set_xticks(x)
    ax.set_xticklabels(days, rotation=15)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("frac spread ≤ 2 ticks")
    ax.set_title("Tick-constraint fraction — Kraken ETH native spot vs synth")
    ax.legend(frameon=False)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def fig_spread_hist(pair: dict[str, Any], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    for key, label, color in (
        ("native_tob", "spot L2", "#1b9e77"),
        ("synth_tob", "trade_synth", "#d95f02"),
    ):
        tob = pair.get(key)
        if not tob:
            continue
        s = np.asarray(tob["spread_bps"], dtype=np.float64)
        s = s[np.isfinite(s) & (s > 0) & (s < 50)]
        if s.size == 0:
            continue
        ax.hist(s, bins=40, alpha=0.55, label=label, color=color, density=True)
    ax.set_xlabel("spread (bps)")
    ax.set_ylabel("density")
    ax.set_title(f"Spread distribution ETH {pair.get('day')} — native vs synth")
    ax.legend(frameon=False)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def gate_impact(eth_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare prior Hold rationale vs native-spot availability."""
    native = [r for r in eth_rows if r["kind"] == "spot_l2"]
    synth = [r for r in eth_rows if r["kind"] == "futures_trade_synth"]
    n_frac = float(np.nanmean([r["frac_constrained_2tick"] for r in native])) if native else float("nan")
    s_frac = float(np.nanmean([r["frac_constrained_2tick"] for r in synth])) if synth else float("nan")
    n_bps = float(np.nanmean([r["med_spread_bps"] for r in native])) if native else float("nan")
    s_bps = float(np.nanmean([r["med_spread_bps"] for r in synth])) if synth else float("nan")
    return {
        "prior_blocker": "Kraken trade_synth excluded from native TOB / tick fragility",
        "now": {
            "spot_l2_days": [r["day"] for r in native],
            "mean_frac_constrained_spot": n_frac,
            "mean_frac_constrained_synth": s_frac,
            "mean_med_spread_bps_spot": n_bps,
            "mean_med_spread_bps_synth": s_bps,
            "spread_ratio_synth_over_spot": (s_bps / n_bps) if n_bps and n_bps > 0 else None,
        },
        "gates": {
            "exec.tick_constrained_flag": {
                "decision": "Hold",
                "why": (
                    f"Kraken **spot** L2 now native on {len(native)} ETH days "
                    f"(mean frac_c={n_frac:.3f} vs synth {s_frac:.3f}); "
                    "still Hold — HL frac dominates + mmip overlap; "
                    "futures PF_* remain L2-absent"
                ),
            },
            "frag.xvenue_tau_gap": {
                "decision": "Hold",
                "why": (
                    "HL↔Deribit τ gap unchanged; Kraken τ now from spot L2 quotes "
                    "(not trade_synth), but spot vs futures market mismatch remains "
                    "for x-venue PF joins"
                ),
            },
            "liq.fm_rel_tick_spread": {
                "decision": "Hold",
                "why": "xvenue τ confound unchanged; spot L2 does not remove HL/DB grid gap",
            },
        },
        "honesty": {
            "spot_l2": "mercat-kraken-md kr-md-spot-* l2_snapshot_level + l2_delta",
            "futures_pf": "NO l2_* in S3 — trade/mark/index only; trade_synth labeled fallback",
        },
    }


def main() -> None:
    ensure_env()
    OUT.mkdir(parents=True, exist_ok=True)
    FIGS.mkdir(parents=True, exist_ok=True)

    eth_pairs: list[dict[str, Any]] = []
    eth_rows: list[dict[str, Any]] = []
    for day in DAYS_ETH:
        print(f"load ETH {day} …", flush=True)
        p = load_pair("ETH", day)
        # drop heavy arrays from JSON summary later
        eth_pairs.append(p)
        if "native" in p:
            eth_rows.append(p["native"])
        if "synth" in p:
            eth_rows.append(p["synth"])

    btc_rows: list[dict[str, Any]] = []
    for day in DAYS_BTC:
        print(f"load BTC {day} …", flush=True)
        p = load_pair("BTC", day)
        if "native" in p:
            btc_rows.append(p["native"])
        if "synth" in p:
            btc_rows.append(p["synth"])
        # one hist for BTC if both exist
        if "native_tob" in p and "synth_tob" in p:
            fig_spread_hist(p, FIGS / f"fig_btc_spread_hist_{day}.png")

    # figs (ETH)
    slim_pairs = [{k: v for k, v in p.items() if k not in ("native_tob", "synth_tob")} for p in eth_pairs]
    fig_spread_compare(slim_pairs, FIGS / "fig_eth_spread_native_vs_synth.png")
    fig_constraint_compare(eth_rows, FIGS / "fig_eth_constraint_native_vs_synth.png")
    # hist on densest day with both
    for p in eth_pairs:
        if "native_tob" in p and "synth_tob" in p:
            fig_spread_hist(p, FIGS / f"fig_eth_spread_hist_{p['day']}.png")
            break

    impact = gate_impact(eth_rows)
    artifact = {
        "days_eth": DAYS_ETH,
        "days_btc": DAYS_BTC,
        "eth_rows": eth_rows,
        "btc_rows": btc_rows,
        "eth_day_status": [
            {
                "day": p["day"],
                "native_ok": "native" in p,
                "synth_ok": "synth" in p,
                "native_n": (p.get("native") or {}).get("n"),
                "synth_n": (p.get("synth") or {}).get("n"),
                "native_error": p.get("native_error"),
                "synth_error": p.get("synth_error"),
            }
            for p in eth_pairs
        ],
        "gate_impact": impact,
        "figs": sorted(str(p.relative_to(BOOK)) for p in FIGS.glob("*.png")),
    }
    _json(OUT / "native_vs_synth.json", artifact)
    _json(OUT / "gate_impact.json", impact)

    # short EXP note
    note = BOOK / "chapters" / "tick_constraint" / "EXP_REPORT.md"
    if note.is_file():
        prev = note.read_text()
        block = (
            "\n\n## Kraken native spot L2 (2026-09-30 addendum)\n\n"
            f"- Spot L2 days ETH: {DAYS_ETH} via `warehouse:kraken_spot_l2_rebuild`.\n"
            f"- Mean med spread spot≈{impact['now']['mean_med_spread_bps_spot']:.4g} bps "
            f"vs synth≈{impact['now']['mean_med_spread_bps_synth']:.4g} bps "
            f"(ratio≈{impact['now']['spread_ratio_synth_over_spot']}).\n"
            f"- Constraint frac spot≈{impact['now']['mean_frac_constrained_spot']:.3f} "
            f"vs synth≈{impact['now']['mean_frac_constrained_synth']:.3f}.\n"
            "- Futures `PF_*` still **no** L2 in S3 — keep trade_synth labeled for futures joins.\n"
            "- Artifacts: `out/kraken_native/`.\n"
        )
        if "Kraken native spot L2" not in prev:
            note.write_text(prev.rstrip() + block)

    print(json.dumps({
        "eth_native_days": [r["day"] for r in eth_rows if r["kind"] == "spot_l2"],
        "gate_impact": impact["gates"],
        "figs": artifact["figs"],
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
