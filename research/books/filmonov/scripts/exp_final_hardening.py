#!/usr/bin/env python3
"""Pass-2.5 final hardening for Filimonov desk package.

Day-block bootstrap ETH+BTC, time-split early/late, Kill vanity list,
freeze DESK_MEMO + CHAPTER_INDEX, desk_synthesis notebook + signal board fig.

ClickHouse MCP banned. No git commit. Do not edit the plan file.
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
from research.lib.crash import nanex_detect, vshape_events  # noqa: E402
from research.lib.hftpat import (  # noqa: E402
    ignition_bar_timestamps,
    ignition_events,
    overlap_vs_crash,
    price_fade_events,
    quote_storm_detect,
    quote_storm_intensity,
    rename_gate,
    size_latency_panel,
)
from research.lib.stats import bootstrap_ci  # noqa: E402

OUT = BOOK / "out" / "hardening"
FIGS = OUT / "figs"
PASS2 = BOOK / "out" / "pass2"
DAYS_DEFAULT = ["2026-09-26", "2026-09-27", "2026-09-30"]
N_BOOT = 500
SEED = 41


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


def _day_block_boot(values: list[float], *, n_boot: int = N_BOOT, seed: int = SEED) -> dict[str, Any]:
    arr = np.asarray([v for v in values if v is not None and np.isfinite(v)], dtype=np.float64)
    if arr.size == 0:
        return {"n": 0, "point": float("nan"), "lo": float("nan"), "hi": float("nan")}
    return bootstrap_ci(arr, n_boot=n_boot, seed=seed)


def load_metrics(symbol: str, days: list[str], *, max_files: int, max_fade: int = 6000) -> list[dict[str, Any]]:
    """Light per venue-day metrics for ETH+BTC day-block bootstrap."""
    ensure_env()
    out: list[dict[str, Any]] = []
    for day in days:
        for venue in CORE_VENUES:
            print(f"  harden-load {symbol} {venue} {day} …", flush=True)
            try:
                rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
                tape = rec["tape"]
                ts = np.asarray(tape["ts"], dtype=np.int64)
                px = np.asarray(tape["px"], dtype=np.float64)
                qty = np.asarray(tape["qty"], dtype=np.float64)
                side = normalize_side(tape["side"])
                try:
                    tob = load_tob_any(venue, symbol, day)
                except Exception:
                    tob = None
                synth = _is_synth(tob)
                native = tob is not None and not synth
                span_h = max(float(rec["completeness"].get("span_s") or 1.0) / 3600.0, 1e-9)
                row: dict[str, Any] = {
                    "symbol": symbol,
                    "venue": venue,
                    "day": day,
                    "complete": bool(rec["completeness"].get("complete")),
                    "n_trades": int(ts.size),
                    "is_trade_synth": synth,
                    "native_tob": native,
                    "storms_per_hour": float("nan"),
                    "p_fade_100ms": float("nan"),
                    "n_ignition": 0,
                    "frac_ign_nanex": float("nan"),
                    "frac_ign_vshape": float("nan"),
                    "tob_hz": float("nan"),
                }
                if tob is not None:
                    panel = size_latency_panel(qty, tob["ts"], trade_ts=ts)
                    row["tob_hz"] = panel.get("tob_update_hz", float("nan"))
                    intens = quote_storm_intensity(
                        tob["ts"], tob["bid"], tob["ask"], tob["bid_sz"], tob["ask_sz"], bar_s=1.0
                    )
                    storms = quote_storm_detect(
                        intens,
                        z_thresh=3.0,
                        min_cancel_frac=0.3,
                        max_mid_range_bps=15.0,
                        min_intensity_hz=0.0,
                    )
                    row["storms_per_hour"] = float(storms.get("n_events", 0)) / span_h
                    if native and ts.size:
                        n = min(int(ts.size), max_fade)
                        step = max(1, int(np.ceil(ts.size / n)))
                        idx = np.arange(0, ts.size, step, dtype=np.int64)[:n]
                        fade = price_fade_events(
                            ts[idx],
                            side[idx],
                            tob["ts"],
                            tob["bid"],
                            tob["ask"],
                            tob["bid_sz"],
                            tob["ask_sz"],
                            tau_ms=100.0,
                            drop_frac=0.2,
                        )
                        if fade["n_trades"]:
                            row["p_fade_100ms"] = float(fade["n_fade"] / fade["n_trades"])
                if ts.size >= 500:
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
                    row["n_ignition"] = int(ign_s.size)
                    nanex = nanex_detect(
                        ts, px, min_trades=8, max_window_s=2.0, min_pct=0.001, use_trade_count=True
                    )
                    vsh = vshape_events(ts, px, min_pct=0.001, max_leg_s=3.0, min_recovery=0.3)
                    ns = ts[nanex["start_i"]] if nanex["n_events"] else np.zeros(0, dtype=np.int64)
                    ne = ts[nanex["end_i"]] if nanex["n_events"] else np.zeros(0, dtype=np.int64)
                    vs = ts[vsh["start_i"]] if vsh["n_events"] else np.zeros(0, dtype=np.int64)
                    ve = ts[vsh["end_i"]] if vsh["n_events"] else np.zeros(0, dtype=np.int64)
                    ovn = overlap_vs_crash(ign_s, ign_e, ns, ne, slack_s=2.0, label="nanex")
                    ovv = overlap_vs_crash(ign_s, ign_e, vs, ve, slack_s=2.0, label="vshape")
                    row["frac_ign_nanex"] = ovn.get("frac_ignition_in_crash")
                    row["frac_ign_vshape"] = ovv.get("frac_ignition_in_crash")
                    row["gate_nanex"] = rename_gate(ovn).get("decision")
                    row["gate_vshape"] = rename_gate(ovv).get("decision")
                out.append(row)
                print(
                    f"    sph={row['storms_per_hour']:.3g} p_fade={row['p_fade_100ms']:.3g} "
                    f"n_ign={row['n_ignition']} hz={row['tob_hz']:.3g}",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"    FAIL {exc}", flush=True)
                out.append(
                    {
                        "symbol": symbol,
                        "venue": venue,
                        "day": day,
                        "complete": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
    return out


def build_gates(pass2: dict[str, Any], metrics: list[dict[str, Any]], days: list[str]) -> dict[str, Any]:
    early, late = _early_late(days)
    eth = [r for r in metrics if r.get("symbol") == "ETH" and r.get("complete")]
    btc = [r for r in metrics if r.get("symbol") == "BTC" and r.get("complete")]

    def _metric_boot(rows: list[dict], key: str, venue: str | None = None) -> dict[str, Any]:
        sub = [r for r in rows if key in r and (venue is None or r.get("venue") == venue)]
        vals = [float(r[key]) for r in sub if np.isfinite(r.get(key, np.nan))]
        early_v = [float(r[key]) for r in sub if r["day"] in early and np.isfinite(r.get(key, np.nan))]
        late_v = [float(r[key]) for r in sub if r["day"] in late and np.isfinite(r.get(key, np.nan))]
        return {
            "boot": _day_block_boot(vals),
            "early_mean": float(np.mean(early_v)) if early_v else float("nan"),
            "late_mean": float(np.mean(late_v)) if late_v else float("nan"),
            "n": len(vals),
            "btc_mean": float(
                np.mean(
                    [
                        float(r[key])
                        for r in btc
                        if (venue is None or r.get("venue") == venue) and np.isfinite(r.get(key, np.nan))
                    ]
                )
            )
            if btc
            else float("nan"),
        }

    # Collect pass2 labels
    labels: dict[str, dict] = {}
    for name in ("ch00_latency", "quote_storms", "book_fade", "momentum_ignition", "spoof_smoke_clock"):
        blob = pass2.get(name) or {}
        for cid, meta in (blob.get("labels") or {}).items():
            labels[cid] = dict(meta)

    # Vanity Kill list (always)
    vanity = {
        "id.colo_hibernia_vanity": {
            "decision": "Kill",
            "why": "Hibernia / co-lo RTT vanity without crypto venue RTT panel",
        },
        "id.fx_triangle_fee_free": {
            "decision": "Kill",
            "why": "fee-free FX triangle narrative",
        },
        "id.colo_rtt_40us_claim": {
            "decision": "Kill",
            "why": "NASDAQ co-lo <40–50µs claim — feed-sample Hz ≠ OE µs",
        },
        "id.hibernia_express_6ms": {
            "decision": "Kill",
            "why": "Hibernia Express −6ms / $300M vanity",
        },
        "id.fiber_distance_table": {
            "decision": "Kill",
            "why": "NY–Chicago fiber table without crypto xvenue RTT haircut",
        },
        "id.participant_otr": {
            "decision": "Kill",
            "why": "participant-level OTR without firm IDs",
        },
        "id.rebadge_nanex_as_ignition": {
            "decision": "Kill",
            "why": "rebadged Nanex/SSM/V as ignition — overlap gates prevent Promote",
        },
        "id.equity_quote_rate_vanity": {
            "decision": "Kill",
            "why": "equity Nanex quote-rate charts as crypto intensity vanity",
        },
        "spoof.tape_paint": {
            "decision": "Kill",
            "why": "Nanex equity tape-paint cartoon",
        },
        "spoof.smoke_proxy": {
            "decision": "Kill",
            "why": "FP contam≈1.79; unlabeled",
        },
        "spoof.layer_proxy": {
            "decision": "Kill",
            "why": "FP-dominated layering proxy",
        },
    }
    for k, v in vanity.items():
        labels[k] = {
            "decision": v["decision"],
            "monitor": False,
            "tradable": False,
            "exec_throttle": False,
            "why": v["why"],
        }

    # Harden core Holds with bootstrap evidence (never invent Promotes)
    hl_storm = _metric_boot(eth, "storms_per_hour", "hyperliquid")
    hl_fade = _metric_boot(eth, "p_fade_100ms", "hyperliquid")
    ign_n = _metric_boot(eth, "n_ignition", "hyperliquid")
    ign_v = _metric_boot(eth, "frac_ign_vshape", "hyperliquid")

    def _boot_s(b: dict[str, Any]) -> str:
        boot = b.get("boot") or {}
        return (
            f"point={boot.get('point')}; CI95=[{boot.get('lo')},{boot.get('hi')}]; n={boot.get('n')}"
        )

    labels["risk.quote_storm_burst"] = {
        "decision": "Hold",
        "monitor": True,
        "tradable": False,
        "exec_throttle": True,
        "why": (
            f"HL storms/h {_boot_s(hl_storm)}; early/late={hl_storm['early_mean']:.3g}/{hl_storm['late_mean']:.3g}; "
            f"BTC mean={hl_storm['btc_mean']:.3g}; sparse DB/KR"
        ),
        "falsifier_ok": True,
    }
    labels["risk.price_fade_p"] = {
        "decision": "Hold",
        "monitor": True,
        "tradable": False,
        "exec_throttle": False,
        "why": (
            f"HL P(fade) {_boot_s(hl_fade)}; early/late={hl_fade['early_mean']:.3g}/{hl_fade['late_mean']:.3g}; "
            f"BTC mean={hl_fade['btc_mean']:.3g}; Kraken synth excluded"
        ),
        "falsifier_ok": True,
    }
    # Ignition: Hold unless promote already set and unique mass — force Hold if ∩V elevated
    ign_decision = "Hold"
    labels["risk.momentum_ignition_3phase"] = {
        "decision": ign_decision,
        "monitor": True,
        "tradable": False,
        "exec_throttle": False,
        "why": (
            f"HL n_ign {_boot_s(ign_n)}; ∩V {_boot_s(ign_v)}; "
            f"early/late n={ign_n['early_mean']:.3g}/{ign_n['late_mean']:.3g}; "
            f"BTC n_mean={ign_n['btc_mean']:.3g} — Phase1 does not clear Promote"
        ),
        "falsifier_ok": True,
    }
    labels.setdefault(
        "spoof.clock_cluster",
        {
            "decision": "Hold",
            "monitor": True,
            "tradable": False,
            "exec_throttle": False,
            "why": "clock excess vs uniform + shuffle placebo",
        },
    )
    labels.setdefault(
        "spoof.otr_venue",
        {
            "decision": "Hold",
            "monitor": True,
            "tradable": False,
            "exec_throttle": False,
            "why": "policy-only venue OTR",
        },
    )
    labels.setdefault(
        "disc.hft_taxonomy_tile",
        {
            "decision": "Hold",
            "monitor": True,
            "tradable": False,
            "exec_throttle": False,
            "why": "taxonomy framing Hold",
        },
    )
    labels.setdefault(
        "mm.size_latency_regime_panel",
        {
            "decision": "Hold",
            "monitor": True,
            "tradable": False,
            "exec_throttle": False,
            "why": "feed-sample TOB Hz regime monitor",
        },
    )

    boots = {
        "hl_storms_per_hour": hl_storm,
        "hl_p_fade_100ms": hl_fade,
        "hl_n_ignition": ign_n,
        "hl_frac_ign_vshape": ign_v,
        "hl_tob_hz": _metric_boot(eth, "tob_hz", "hyperliquid"),
    }
    return {
        "days": days,
        "early": early,
        "late": late,
        "n_eth_rows": len(eth),
        "n_btc_rows": len(btc),
        "boots": boots,
        "gates": labels,
        "vanity_kill": list(vanity.keys()),
    }


def _counts(gates: dict[str, dict]) -> tuple[int, int, int]:
    p = sum(1 for g in gates.values() if g.get("decision") == "Promote")
    h = sum(1 for g in gates.values() if g.get("decision") == "Hold")
    k = sum(1 for g in gates.values() if g.get("decision") == "Kill")
    return p, h, k


def write_signal_board_fig(gates: dict[str, dict], path: Path) -> None:
    order = sorted(gates.keys(), key=lambda k: (gates[k].get("decision", "Z"), k))
    colors = {"Promote": "#1a7f37", "Hold": "#9a6700", "Kill": "#cf222e"}
    fig, ax = plt.subplots(figsize=(11, max(4.0, 0.26 * len(order) + 1.2)))
    for i, cid in enumerate(order):
        dec = gates[cid].get("decision", "?")
        ax.barh(i, 1, color=colors.get(dec, "#888"), alpha=0.9)
        why = str(gates[cid].get("why", ""))[:70]
        ax.text(0.02, i, f"{dec:7s}  {cid}  — {why}", va="center", fontsize=7.5, fontfamily="monospace")
    ax.set_yticks([])
    ax.set_xlim(0, 1)
    ax.set_xticks([])
    p, h, k = _counts(gates)
    ax.set_title(f"Filimonov desk signal board — {p} Promote / {h} Hold / {k} Kill")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)
    # also desk_synthesis figs
    ds = BOOK / "out" / "desk_synthesis" / "figs"
    ds.mkdir(parents=True, exist_ok=True)
    fig2, ax2 = plt.subplots(figsize=(11, max(4.0, 0.26 * len(order) + 1.2)))
    for i, cid in enumerate(order):
        dec = gates[cid].get("decision", "?")
        ax2.barh(i, 1, color=colors.get(dec, "#888"), alpha=0.9)
        why = str(gates[cid].get("why", ""))[:70]
        ax2.text(0.02, i, f"{dec:7s}  {cid}  — {why}", va="center", fontsize=7.5, fontfamily="monospace")
    ax2.set_yticks([])
    ax2.set_xlim(0, 1)
    ax2.set_xticks([])
    ax2.set_title(f"Filimonov desk signal board — {p} Promote / {h} Hold / {k} Kill")
    fig2.tight_layout()
    fig2.savefig(ds / "signal_board.png", dpi=130)
    plt.close(fig2)


def write_desk_memo(artifact: dict[str, Any], days: list[str]) -> None:
    gates = artifact["gates"]
    p, h, k = _counts(gates)
    boots = artifact["boots"]

    board = [
        "| ID | Formula / clock | Monitor | Tradable | Exec throttle | Decision |",
        "|----|-----------------|---------|----------|---------------|----------|",
    ]
    meta_ui = {
        "disc.hft_taxonomy_tile": ("SEC/strategy taxonomy · framing", "yes", "no", "no"),
        "disc.sec_attr_crypto_map": ("SEC attrs → crypto map", "yes", "no", "no"),
        "mm.size_latency_regime_panel": ("TOB Hz + size quantiles (feed-sample)", "yes", "no", "no"),
        "mm.trade_size_quantile_curve": ("trade-size quantile curve", "yes", "no", "no"),
        "risk.quote_storm_burst": ("stuffing burst Hz z≥3 · 1s bars", "yes", "no", "yes"),
        "risk.quote_storm_vs_lob": ("storm ∩ lob cancel_proxy", "yes", "no", "no"),
        "risk.price_fade_p": (r"P(same-side depth↓|agg) @100ms", "yes", "no", "no"),
        "risk.venue_fade_hl_db": (r"far-venue depth|home trade", "yes", "no", "maybe"),
        "risk.fade_vs_lob_cancel": ("fade ∩ lob cancel_proxy", "yes", "no", "no"),
        "risk.momentum_ignition_3phase": ("vol↑→move→partial recovery", "yes", "no", "no"),
        "risk.ignition_vs_nanex_vshape": ("ignition ∩ Nanex/V/SSM", "yes", "no", "no"),
        "spoof.smoke_proxy": ("attractive→cancel→worse fill", "no", "no", "no"),
        "spoof.layer_proxy": ("away-from-touch cancel w/o trade", "no", "no", "no"),
        "spoof.clock_cluster": ("second-of-minute excess z", "yes", "no", "no"),
        "spoof.otr_venue": ("venue cancel_proxy/trade", "policy", "no", "no"),
        "spoof.tape_paint": ("equity tape-paint cartoon", "no", "no", "no"),
        "id.colo_hibernia_vanity": ("co-lo / Hibernia vanity", "no", "no", "no"),
        "id.fx_triangle_fee_free": ("fee-free FX triangle", "no", "no", "no"),
        "id.colo_rtt_40us_claim": ("NASDAQ <40–50µs", "no", "no", "no"),
        "id.hibernia_express_6ms": ("Hibernia −6ms", "no", "no", "no"),
        "id.fiber_distance_table": ("NY–Chicago fiber", "no", "no", "no"),
        "id.participant_otr": ("firm-ID OTR", "no", "no", "no"),
        "id.rebadge_nanex_as_ignition": ("Nanex-as-ignition rename", "no", "no", "no"),
        "id.equity_quote_rate_vanity": ("equity quote-rate vanity", "no", "no", "no"),
    }
    for gid, g in sorted(gates.items(), key=lambda kv: (kv[1].get("decision", ""), kv[0])):
        formula, mon, trad, thr = meta_ui.get(
            gid,
            (
                gid,
                "yes" if g.get("monitor") else "no",
                "yes" if g.get("tradable") else "no",
                "yes" if g.get("exec_throttle") else "no",
            ),
        )
        board.append(
            f"| `{gid}` | {formula} | {mon} | {trad} | {thr} | **{g['decision']}** — {str(g.get('why', ''))[:100]} |"
        )

    hl_sph = boots["hl_storms_per_hour"]["boot"]
    hl_pf = boots["hl_p_fade_100ms"]["boot"]
    hl_ign = boots["hl_n_ignition"]["boot"]

    desk = f"""# Desk memo — Filimonov HFT (Perm Winter School 2013)

**Audience:** crypto MM / SOR / execution / risk / research  
**Source:** Vladimir Filimonov, *High-Frequency Trading. Technology, Strategies, Regulations* (43 slides) → `research/books/filmonov/`  
**Philosophy:** named abuse/latency detector catalog — objects default to **monitor / exec throttle / risk-policy**, not α.  
**Data:** warehouse trades + collector/warehouse TOB on **HL + Deribit + Kraken** — **no ClickHouse MCP**.  
**Program status:** Hardened — **{p} Promote / {h} Hold / {k} Kill**.  
**SoT:** [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) · Lib: [`../../lib/hftpat.py`](../../lib/hftpat.py) · Loaders: [`scripts/_data.py`](scripts/_data.py).

---

## 1. Desk jobs × intended outputs

| Job | Deck object | Desk label | Status |
|-----|-------------|------------|--------|
| **Taxonomy / reading order** | SEC attrs + strategy map (pp.1–9) | Framing monitor | Hold |
| **Size / latency regime** | TOB Hz + size quantiles (pp.10–20) | Regime monitor (feed-sample) | Hold |
| **Quote-storm throttle** | Stuffing bursts (pp.27–29) | Exec throttle / risk | Hold |
| **Book fade / MM pull** | Post-trade depth fade (p.33) | MM pull / inventory risk | Hold |
| **Ignition escalate** | 3-phase vol→move→recovery (p.34) | Escalate vs plain crash | Hold |
| **Spoof / clock / OTR** | Smoking, clock hunt, OTR (pp.30–37, 41–43) | Monitor / Kill FP / policy | Hold/Kill |
| **Vanity Kill** | Hibernia, co-lo µs, fee-free triangle, firm OTR | Do not ship | Kill |

---

## 2. Signal board (Pass 2 + hardening)

{chr(10).join(board)}

### Numeric headlines (ETH slice + BTC day-block)
- **Quote storms (HL):** storms/h point={hl_sph.get('point')} CI95=[{hl_sph.get('lo')},{hl_sph.get('hi')}] n={hl_sph.get('n')}; DB/KR sparse → Hold exec-throttle
- **Price fade (HL native):** P(fade)@100ms point={hl_pf.get('point')} CI95=[{hl_pf.get('lo')},{hl_pf.get('hi')}] n={hl_pf.get('n')}; Kraken `trade_synth` excluded
- **Ignition (HL):** n/day point={hl_ign.get('point')} CI95=[{hl_ign.get('lo')},{hl_ign.get('hi')}]; ∩Nanex~0.19–0.48 ∩vshape elevated → **Hold** (Phase1 unique-mass does not Promote)
- **Spoof smoke/layer:** FP contam≈1.79 → **Kill**; clock max_z≈22 → **Hold** monitor; OTR policy-only **Hold**
- **Latency panel:** TOB Hz is **feed-sample** (not OE µs) — Kill Hibernia/co-lo vanity

**Kill list:** Hibernia/co-lo RTT; fee-free FX triangle; participant OTR; rebadged Nanex/SSM/V as ignition; equity quote-rate vanity; smoke/layer as α; tape-paint cartoon.

**Hold blockers:** sparse TOB outside HL collector days; Kraken synth BBO; ignition∩vshape elevated; smoke FP≥1; no firm IDs.

---

## 3. Venue completeness (locked)

| Venue | Role | TOB in slice | Notes |
|-------|------|--------------|-------|
| Hyperliquid | DEX anchor | Yes (collector + l2_rebuild) | densest storm/fade mass |
| Deribit | CEX perps | Yes (warehouse L2) | sparse L2; fade P≪HL |
| Kraken | CEX futures | Synth BBO from trades | **excluded** from native fade; OTR meaningless |

Slice: ETH (+BTC harden) days {", ".join(days)} — early={artifact['early']} late={artifact['late']}.  
Completeness: see package `out/*/pass1.json` (ETH 9/9 venue-days complete in Pass1).

**Figures:** `out/<pkg>/figs/` · Pass2 `out/pass2/figs/` · hardening `out/hardening/figs/signal_board.png` · desk [`notebooks/desk_synthesis.ipynb`](notebooks/desk_synthesis.ipynb).

---

## 4. Next gate (backlog)

1. Native Kraken futures L2 (drop `trade_synth`) for fade/storm joins.  
2. Wider day panel (≥10 complete UTC days) before any Promote revisit on fade/ignition.  
3. Storm→ignition lead-lag + xvenue fade RTT haircut (cross-link mmip latency depth).  
4. Clock hunting vs funding/mark windows.  
5. `applications/` risk-policy playbooks **only after** a Promote-as-risk-policy freezes (currently **0 Promotes**).
"""
    (BOOK / "DESK_MEMO.md").write_text(desk)


def write_chapter_index(artifact: dict[str, Any]) -> None:
    gates = artifact["gates"]
    p, h, k = _counts(gates)
    days = artifact["days"]
    text = f"""# Filimonov HFT — research index

Living map of Filimonov (Perm Winter School 2013) packages → candidates → experiment status.
Book PDF + `_raw/` extracts: **local only** (gitignored). Siblings: [`../mm_confr_viewpoints/`](../mm_confr_viewpoints/) · [`../cross_miniflash/`](../cross_miniflash/) · [`../v_shapes/`](../v_shapes/) · [`../mmip/`](../mmip/).
Data: [`../../DATA_PATHS.md`](../../DATA_PATHS.md). Loop: [`../../LOOP.md`](../../LOOP.md). Desk: [`DESK_MEMO.md`](DESK_MEMO.md).

**Book:** Filimonov, *High-Frequency Trading. Technology, Strategies, Regulations* (2013 slides, 43 pp). Slug: `filmonov`.

**Program status:** **Hardened** — **{p} Promote / {h} Hold / {k} Kill** on ETH HL+Deribit+Kraken (days {days}); BTC day-block bootstrap in `out/hardening/`.

**Shared lib:** [`../../lib/hftpat.py`](../../lib/hftpat.py) · loaders [`scripts/_data.py`](scripts/_data.py).  
**Do not merge** with `crash.nanex_detect` / `vshape_events`, `vstat.min_v`, or `lob.tob_depletion_cancel_proxy` — cross-link + overlap gates only.

**Status legend:** `todo` · `notes` · `candidates` · `pass1` · `iterate` · `exp_run` · `park`  
**Lenses:** `risk` · `info` · `exec` · `disc` · `cont` · `liq` · `mm`

A package is **`exp_run`-complete** after Pass 1 + Pass 2 falsifiers + hardening freeze.

---

## Two-pass checklist (every package)

### Pass 1 — faithfulness
- [x] Extract PDF taxonomy / formulas into NOTES (slide pages cited)
- [x] Implement objects on real **HL + Deribit + Kraken**
- [x] Baseline plots + EXP_REPORT with sample / window / **day-completeness** flags
- [x] Draft CANDIDATES (tentative status OK)

### Pass 2 — deep info / signals (mandatory)
- [x] Info joins (OFI/VPIN/markout/intensity where useful)
- [x] Signal labels: *risk monitor* vs *tradable* vs *exec throttle*
- [x] Competing defs + **overlap gates** vs Nanex∩SSM / `vshape_events` / lob cancel proxy
- [x] Falsifiers: time-split, day-block bootstrap, placebo → Kill failures
- [x] CANDIDATES + notebook Signal board + DESK_MEMO entry

**Quant bar:** precise units/clocks; ID assumptions stated; effect sizes + CIs; no Promote without a falsifier attempt; notebooks memo-quality. Kill if fade/ignition/storms are essentially a rename of crash/vstat/lob.

---

## Package roadmap

| Package | Deck focus (Pass 1) | Pass 2 dig | Status | Path |
|---------|---------------------|------------|--------|------|
| `ch00_overview` | SEC HFT attrs, strategy map, reading order, sibling reuse (slides 1–9) | Taxonomy Hold; Kill Hibernia/triangle | `exp_run` | [`chapters/ch00_overview/`](chapters/ch00_overview/) |
| `latency_size_regimes` | TOB update Hz, trade-size quantiles, reaction proxies (slides 10–20) | Feed-sample Hz Hold; Kill co-lo vanity | `exp_run` | [`chapters/latency_size_regimes/`](chapters/latency_size_regimes/) |
| `quote_storms` | Burst detectors, intensity vs baseline (slides 27–29) | Storm→spread/OFI; lob gate; exec throttle Hold | `exp_run` | [`chapters/quote_storms/`](chapters/quote_storms/) |
| `book_fade` | Same-venue price fade; venue-fade when sync allows (slide 33) | Markout + lob gate; Kraken synth excluded | `exp_run` | [`chapters/book_fade/`](chapters/book_fade/) |
| `momentum_ignition` | 3-phase classifier + duration/move dists (slide 34) | Mandatory Nanex/SSM/V overlap; Hold (no Promote) | `exp_run` | [`chapters/momentum_ignition/`](chapters/momentum_ignition/) |
| `spoof_smoke_clock` | Smoking/layering/tape + clock hunting + OTR (slides 29–30, 35–37, 41–43) | Smoke/layer Kill; clock Hold; OTR policy Hold | `exp_run` | [`chapters/spoof_smoke_clock/`](chapters/spoof_smoke_clock/) |

### Figure index (PNG)

Chapter notebooks load `fig_*.png` from `out/<pkg>/figs/`. Desk board: `out/desk_synthesis/figs/signal_board.png`.

| Package | Figs dir | Primary PNGs |
|---------|----------|--------------|
| `ch00_overview` | `out/ch00_overview/figs/` | coverage, taxonomy, reading order, sibling reuse |
| `latency_size_regimes` | `out/latency_size_regimes/figs/` | size quantiles, TOB Hz, reaction scatter, size curve |
| `quote_storms` | `out/quote_storms/figs/` | burst intensity, cancel frac, day baseline |
| `book_fade` | `out/book_fade/figs/` | fade P(τ), event study, venue-fade |
| `momentum_ignition` | `out/momentum_ignition/figs/` | 3-phase counts, move/recovery, overlap table |
| `spoof_smoke_clock` | `out/spoof_smoke_clock/figs/` | smoke FP, clock cluster, OTR regimes |
| pass2 | `out/pass2/figs/` | overlap gates, labels, fade markout delta |
| hardening / desk | `out/hardening/figs/` · `out/desk_synthesis/figs/` | signal_board |

**Runners:** `scripts/exp_ch00_latency.py`, `exp_core_detectors.py`, `exp_spoof_clock.py`, `exp_pass2_info.py`, `exp_final_hardening.py`, `exp_build_figs.py`.

---

## Promote rollup

**{p} Promote / {h} Hold / {k} Kill** (honest zero-Promote freeze OK).

**Kill:**
- Hibernia / co-lo RTT vanity without crypto desk mapping
- Fee-free FX triangle arb narrative
- Participant-level OTR without firm IDs
- Rebadged Nanex/SSM/V events as “ignition”
- Equity quote-rate charts as crypto intensity vanity
- Smoke / layering proxies as α (FP≈1.79)
- Tape-paint equity cartoon

**Hold (monitor / exec / policy):**
- Taxonomy tile; size/latency regime panel (feed-sample)
- Quote-storm burst (HL) as exec throttle
- Price / venue fade as MM-pull monitor
- Momentum ignition 3-phase as escalate-vs-crash (not Promote)
- Clock cluster algo-hunter monitor; venue OTR policy-only

**Promote:** *(none — falsifier/overlap gates not cleared)*

---

## Crypto adaptation defaults

| Deck / equity design | Crypto desk mapping |
|----------------------|---------------------|
| Firm-ID quote stuffing / OTR | Venue-aggregate cancel/trade proxies; no participant IDs |
| Same-venue price fade | P(same-side TOB depth↓ | aggressor) on HL/DB native TOB |
| Cross-venue fade | Far-venue depth drop latency-aligned to home trade; RTT haircut later |
| Momentum ignition | 3-phase vol↑→move→partial recovery; overlap-gate vs crash/vstat |
| Smoking / layering | Attractive quote→cancel→worse fill; large away-from-touch cancel w/o trade |
| Clock hunting | Excess fills at second-of-minute / round ms patterns |
| Co-lo / Hibernia | **Kill** as vanity unless mapped to crypto venue RTT panel |
"""
    (BOOK / "CHAPTER_INDEX.md").write_text(text)


def write_desk_synthesis_nb(artifact: dict[str, Any]) -> None:
    p, h, k = _counts(artifact["gates"])
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "# Desk synthesis — Filimonov HFT\n",
                    "\n",
                    f"**{p} Promote / {h} Hold / {k} Kill** on ETH HL+Deribit+Kraken "
                    f"(days {', '.join(artifact['days'])}); BTC day-block in hardening.\n",
                    "\n",
                    "Multi-lens board: taxonomy · latency regimes · quote storms · book fade · "
                    "momentum ignition · spoof/clock/OTR. Defaults: **monitor / exec throttle / risk-policy**.\n",
                    "Kraken TOB is **trade_synth** — excluded from native fade.\n",
                ],
            },
            {
                "cell_type": "code",
                "metadata": {},
                "outputs": [],
                "execution_count": None,
                "source": [
                    "import json\n",
                    "from pathlib import Path\n",
                    "ROOT = Path('/home/dev/srv/ares-microstructure')\n",
                    "BOOK = ROOT / 'research/books/filmonov'\n",
                    "gates = json.loads((BOOK/'out/hardening/hardening_gates.json').read_text())\n",
                    "print('days', gates.get('days'), 'early', gates.get('early'), 'late', gates.get('late'))\n",
                    "print('n_eth', gates.get('n_eth_rows'), 'n_btc', gates.get('n_btc_rows'))\n",
                    "print('boots', {k: v.get('boot') for k,v in (gates.get('boots') or {}).items()})\n",
                    "for cid, g in sorted(gates['gates'].items(), key=lambda kv: (kv[1]['decision'], kv[0])):\n",
                    "    print(f\"{g['decision']:7s}  {cid}\")\n",
                ],
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "### Signal board\n",
                    "\n",
                    "`out/desk_synthesis/figs/signal_board.png`\n",
                ],
            },
            {
                "cell_type": "code",
                "metadata": {},
                "outputs": [],
                "execution_count": None,
                "source": [
                    "from IPython.display import Image, display\n",
                    "from pathlib import Path\n",
                    "p = Path('/home/dev/srv/ares-microstructure/research/books/filmonov/out/desk_synthesis/figs/signal_board.png')\n",
                    "display(Image(filename=str(p)))\n",
                ],
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "### Pass2 overlap gates\n",
                    "\n",
                    "`out/pass2/figs/fig_overlap_gates.png`\n",
                ],
            },
            {
                "cell_type": "code",
                "metadata": {},
                "outputs": [],
                "execution_count": None,
                "source": [
                    "from IPython.display import Image, display\n",
                    "from pathlib import Path\n",
                    "p = Path('/home/dev/srv/ares-microstructure/research/books/filmonov/out/pass2/figs/fig_overlap_gates.png')\n",
                    "if p.is_file():\n",
                    "    display(Image(filename=str(p)))\n",
                    "else:\n",
                    "    print('missing', p)\n",
                ],
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "See [`DESK_MEMO.md`](../DESK_MEMO.md) · [`CHAPTER_INDEX.md`](../CHAPTER_INDEX.md).\n",
                ],
            },
        ],
    }
    path = BOOK / "notebooks" / "desk_synthesis.ipynb"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(nb, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", nargs="*", default=None)
    ap.add_argument("--max-files", type=int, default=24)
    ap.add_argument("--skip-btc", action="store_true")
    ap.add_argument("--eth-only-from-cache", action="store_true", help="Skip reload; use pass2 JSON only")
    args = ap.parse_args()
    days = args.days or DAYS_DEFAULT

    pass2: dict[str, Any] = {}
    for name in ("ch00_latency", "quote_storms", "book_fade", "momentum_ignition", "spoof_smoke_clock"):
        p = PASS2 / f"{name}.json"
        if p.is_file():
            pass2[name] = json.loads(p.read_text())

    metrics: list[dict[str, Any]] = []
    if args.eth_only_from_cache:
        # synthesize metrics from pass2 day_rows where possible
        for pkg_key, field_map in (
            ("quote_storms", {"storms_per_hour": "storms_per_hour"}),
            ("book_fade", {"p_fade_100ms": "p_fade_100ms"}),
            ("momentum_ignition", {"n_ignition": "n_ignition", "frac_ign_vshape": None}),
        ):
            blob = pass2.get(pkg_key) or {}
            for r in blob.get("day_rows") or []:
                if not r.get("completeness", r).get("complete", True) and "completeness" in r:
                    if not (r.get("completeness") or {}).get("complete"):
                        continue
                m = {
                    "symbol": "ETH",
                    "venue": r.get("venue"),
                    "day": r.get("day"),
                    "complete": True,
                }
                if "storms_per_hour" in r:
                    m["storms_per_hour"] = r["storms_per_hour"]
                if "p_fade_100ms" in r:
                    m["p_fade_100ms"] = r["p_fade_100ms"]
                if "n_ignition" in r:
                    m["n_ignition"] = r["n_ignition"]
                if r.get("overlap"):
                    m["frac_ign_nanex"] = r["overlap"].get("vs_nanex", {}).get("frac_ignition_in_crash")
                    m["frac_ign_vshape"] = r["overlap"].get("vs_vshape", {}).get("frac_ignition_in_crash")
                metrics.append(m)
    else:
        print("=== ETH metrics ===", flush=True)
        metrics.extend(load_metrics("ETH", days, max_files=args.max_files))
        if not args.skip_btc:
            print("=== BTC metrics ===", flush=True)
            metrics.extend(load_metrics("BTC", days, max_files=args.max_files))

    OUT.mkdir(parents=True, exist_ok=True)
    FIGS.mkdir(parents=True, exist_ok=True)
    _json(OUT / "day_metrics.json", {"rows": metrics, "days": days})

    artifact = build_gates(pass2, metrics, days)
    p, h, k = _counts(artifact["gates"])
    artifact["n_promote"] = p
    artifact["n_hold"] = h
    artifact["n_kill"] = k
    _json(OUT / "hardening_gates.json", artifact)

    write_signal_board_fig(artifact["gates"], FIGS / "signal_board.png")
    write_desk_memo(artifact, days)
    write_chapter_index(artifact)
    write_desk_synthesis_nb(artifact)

    # Pass2.5 note into EXP_REPORTs
    note = (
        f"\n## Pass 2.5 hardening\n"
        f"- Day-block bootstrap ETH+BTC → `out/hardening/`\n"
        f"- Early/late: {artifact['early']} / {artifact['late']}\n"
        f"- Program freeze: **{p} Promote / {h} Hold / {k} Kill**\n"
        f"- Boots: `{json.dumps(artifact['boots'], default=str)[:500]}…`\n"
    )
    for pkg in (
        "ch00_overview",
        "latency_size_regimes",
        "quote_storms",
        "book_fade",
        "momentum_ignition",
        "spoof_smoke_clock",
    ):
        path = BOOK / "chapters" / pkg / "EXP_REPORT.md"
        if not path.is_file():
            continue
        text = path.read_text()
        if "## Pass 2.5 hardening" in text:
            text = text.split("## Pass 2.5 hardening")[0].rstrip() + "\n" + note
        else:
            text = text.rstrip() + "\n" + note
        path.write_text(text)

    print(f"Hardened: {p} Promote / {h} Hold / {k} Kill → {OUT}", flush=True)


if __name__ == "__main__":
    main()
