from __future__ import annotations
#!/usr/bin/env python3
"""Pass-1 empirics for filmonov ``ch00_overview`` + ``latency_size_regimes``.

ETH complete UTC days on HL + Deribit + Kraken (reuse mm_confr day set when
available). Uses ``hftpat.size_latency_panel`` + taxonomy framing. Writes:

  out/ch00_overview/{coverage,taxonomy,sibling_reuse}.json + figs/
  out/latency_size_regimes/{panel,summary}.json + figs/

Updates chapter NOTES/CANDIDATES/EXP_REPORT with numeric Pass-1 headlines.
ClickHouse MCP banned. Does not touch DESK_MEMO freeze or Pass-2 hardeners.
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
MM_CONFR = BOOK.parent / "mm_confr_viewpoints"
sys.path.insert(0, str(Path(os.environ.get('WAREHOUSE_SRC') or ((Path(os.environ.get('WAREHOUSE_ROOT') or (Path.home() / 'lab' / 'lab-n2070' / 'warehouse')) / 'src')))))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb')) / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import (  # noqa: E402
    CORE_VENUES,
    ensure_env,
    load_day_trades,
    load_tob_any,
    resolve_days,
)
from ares_micro.flow import hftpat  # noqa: E402

OUT = BOOK / "out"
VENUE_COLORS = {
    "hyperliquid": "#1f77b4",
    "deribit": "#ff7f0e",
    "kraken": "#2ca02c",
}
VENUE_SHORT = {"hyperliquid": "HL", "deribit": "DB", "kraken": "KR"}

# Deck strategy map (slide 17) → crypto desk object + sibling lib
STRATEGY_MAP: list[dict[str, str]] = [
    {"deck": "Market making / liquidity providing", "pkg": "latency_size_regimes", "lib": "hftpat.size_latency_panel", "sibling": "mmip latency / tick"},
    {"deck": "Statistical / cross-market arb", "pkg": "(framing)", "lib": "—", "sibling": "cross_miniflash / mmip"},
    {"deck": "Quote stuffing", "pkg": "quote_storms", "lib": "hftpat.quote_storm_*", "sibling": "lob cancel proxy (≠)"},
    {"deck": "Quote smoking / layering / spoofing", "pkg": "spoof_smoke_clock", "lib": "hftpat.smoke_spoof_proxy", "sibling": "—"},
    {"deck": "Momentum ignition", "pkg": "momentum_ignition", "lib": "hftpat.ignition_events", "sibling": "crash Nanex/SSM/V (≠)"},
    {"deck": "Painting the tape / order hunting", "pkg": "spoof_smoke_clock", "lib": "hftpat.clock_cluster_*", "sibling": "—"},
    {"deck": "Price / venue fade (slide 33)", "pkg": "book_fade", "lib": "hftpat.price_fade_* / venue_fade_*", "sibling": "lob depletion (≠)"},
]

SEC_ATTRS = [
    "extraordinarily high-speed / sophisticated programs",
    "co-location / individual data feeds to minimize latency",
    "very short position holding periods",
    "numerous orders cancelled shortly after submission",
    "end day flat (no significant overnight unhedged position)",
]

SIBLING_REUSE = [
    {
        "object": "Nanex / SSM / V-recovery",
        "lib": "crash.py",
        "filmonov": "≠ ignition 3-phase; overlap gate only",
        "action": "cross-link",
    },
    {
        "object": "MinV drift-burst",
        "lib": "vstat.py",
        "filmonov": "≠ ignition cause sequence",
        "action": "cross-link",
    },
    {
        "object": "tob_depletion_cancel_proxy",
        "lib": "lob.py",
        "filmonov": "≠ post-trade conditional fade",
        "action": "cross-link",
    },
    {
        "object": "relative tick / MQ / constraint",
        "lib": "ticksize.py (mm_confr)",
        "filmonov": "size/latency framing sibling; not re-Promote",
        "action": "reuse day set",
    },
    {
        "object": "Hawkes / branching ratio",
        "lib": "mmip",
        "filmonov": "wrong Filimonov lineage — out of scope",
        "action": "exclude",
    },
]


def _json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str))


def _savefig(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return path


def resolve_eth_days(explicit: list[str] | None, n: int) -> list[str]:
    """Prefer mm_confr pass1 panel days; else listing-cache resolve_days."""
    if explicit:
        return explicit
    panel_path = MM_CONFR / "out" / "pass1" / "panel.json"
    if panel_path.is_file():
        try:
            days = json.loads(panel_path.read_text()).get("days") or []
            if days:
                return list(days)
        except Exception:
            pass
    return resolve_days(None, venue="hyperliquid", n=n)


def build_venue_day(symbol: str, day: str, venue: str, *, max_files: int) -> dict[str, Any]:
    ensure_env()
    rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
    tape = rec["tape"]
    qty = np.asarray(tape["qty"], dtype=np.float64)
    ts = np.asarray(tape["ts"], dtype=np.int64)
    px = np.asarray(tape["px"], dtype=np.float64)

    tob_err = None
    tob: dict[str, Any] | None
    try:
        tob = load_tob_any(venue, symbol, day)
    except Exception as exc:  # noqa: BLE001
        tob = None
        tob_err = f"{type(exc).__name__}: {exc}"

    panel: dict[str, Any]
    if tob is not None:
        panel = hftpat.size_latency_panel(qty, tob["ts"], trade_ts=ts)
    else:
        panel = hftpat.size_latency_panel(qty, np.zeros(0, dtype=np.int64), trade_ts=ts)

    notional = px * qty if px.size and qty.size else np.array([])
    notional = notional[np.isfinite(notional) & (notional > 0)]
    size_notional_q: dict[str, float] = {}
    for qq in (0.1, 0.25, 0.5, 0.75, 0.9, 0.99):
        size_notional_q[f"q{int(100 * qq)}"] = (
            float(np.quantile(notional, qq)) if notional.size else float("nan")
        )

    synth = "trade_synth" in str((tob or {}).get("source") or "")
    return {
        "venue": venue,
        "symbol": symbol,
        "day": day,
        "instrument": rec.get("instrument"),
        "completeness": rec["completeness"],
        "n_trades": int(rec["completeness"].get("n") or qty.size),
        "tob_ok": tob is not None,
        "tob_error": tob_err,
        "tob_n": int(tob.get("n", 0)) if tob is not None else 0,
        "tob_source": (tob or {}).get("source"),
        "tob_table": (tob or {}).get("table"),
        "tob_synth": synth,
        "panel": panel,
        "size_notional_quantiles": size_notional_q,
        "mean_notional": float(np.mean(notional)) if notional.size else float("nan"),
    }


# ── figures: ch00 ───────────────────────────────────────────────────────────


def fig_ch00_coverage(rows: list[dict[str, Any]]) -> Path:
    days = sorted({r["day"] for r in rows})
    venues = list(CORE_VENUES)
    mat = np.full((len(venues), len(days)), np.nan)
    for i, v in enumerate(venues):
        for j, d in enumerate(days):
            hit = next((r for r in rows if r["venue"] == v and r["day"] == d), None)
            if hit:
                mat[i, j] = float((hit.get("completeness") or {}).get("coverage") or 0.0)
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    im = ax.imshow(mat, aspect="auto", vmin=0, vmax=1, cmap="YlGn")
    ax.set_xticks(range(len(days)))
    ax.set_xticklabels(days, rotation=30, ha="right")
    ax.set_yticks(range(len(venues)))
    ax.set_yticklabels([VENUE_SHORT.get(v, v) for v in venues])
    for i in range(len(venues)):
        for j in range(len(days)):
            if np.isfinite(mat[i, j]):
                ax.text(j, i, f"{mat[i, j]:.2f}", ha="center", va="center", fontsize=9)
    ax.set_title("ETH trade-stream coverage (UTC day)")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="coverage")
    fig.tight_layout()
    return _savefig(fig, OUT / "ch00_overview" / "figs" / "fig_coverage.png")


def fig_ch00_taxonomy() -> Path:
    labels = [s["deck"] for s in STRATEGY_MAP]
    pkgs = [s["pkg"] for s in STRATEGY_MAP]
    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    y = np.arange(len(labels))[::-1]
    colors = ["#4c78a8" if p not in ("(framing)",) else "#bab0ac" for p in pkgs]
    ax.barh(y, np.ones(len(labels)), color=colors, edgecolor="white", height=0.7)
    for yi, lab, pkg in zip(y, labels, pkgs):
        ax.text(0.02, yi, lab, va="center", ha="left", color="white", fontsize=9, fontweight="bold")
        ax.text(0.98, yi, pkg, va="center", ha="right", color="white", fontsize=8)
    ax.set_xlim(0, 1)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.set_title("Deck strategy map → filmonov packages (slide 17 + fade)")
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    return _savefig(fig, OUT / "ch00_overview" / "figs" / "fig_taxonomy.png")


def fig_ch00_reading_order() -> Path:
    order = [
        "ch00_overview",
        "latency_size_regimes",
        "quote_storms",
        "book_fade",
        "momentum_ignition",
        "spoof_smoke_clock",
    ]
    fig, ax = plt.subplots(figsize=(8.5, 2.8))
    x = np.arange(len(order))
    ax.plot(x, np.zeros_like(x), "-", color="#333", lw=2, zorder=1)
    ax.scatter(x, np.zeros_like(x), s=220, c="#1f77b4", zorder=2, edgecolors="white", lw=1.5)
    for i, name in enumerate(order):
        ax.text(i, 0.12, f"{i + 1}. {name}", ha="center", va="bottom", fontsize=8, rotation=25)
    ax.set_ylim(-0.4, 0.7)
    ax.set_xlim(-0.4, len(order) - 0.6)
    ax.axis("off")
    ax.set_title("Package reading order (Pass 1 → Pass 2)")
    fig.tight_layout()
    return _savefig(fig, OUT / "ch00_overview" / "figs" / "fig_reading_order.png")


def fig_ch00_sibling() -> Path:
    fig, ax = plt.subplots(figsize=(9.5, 3.8))
    ax.axis("off")
    col_labels = ["Sibling object", "Lib", "Filimonov stance", "Action"]
    cell = [[r["object"], r["lib"], r["filmonov"], r["action"]] for r in SIBLING_REUSE]
    table = ax.table(cellText=cell, colLabels=col_labels, loc="center", cellLoc="left")
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1.05, 1.55)
    ax.set_title("Sibling reuse — cross-link, do not re-Promote", pad=12)
    fig.tight_layout()
    return _savefig(fig, OUT / "ch00_overview" / "figs" / "fig_sibling_reuse.png")


# ── figures: latency_size_regimes ────────────────────────────────────────────


def fig_latency_size_quantiles(rows: list[dict[str, Any]]) -> Path:
    """Median trade size (coin qty) by venue across days."""
    venues = list(CORE_VENUES)
    days = sorted({r["day"] for r in rows})
    fig, ax = plt.subplots(figsize=(7.5, 4.0))
    width = 0.25
    x = np.arange(len(venues))
    for j, d in enumerate(days):
        vals = []
        for v in venues:
            hit = next((r for r in rows if r["venue"] == v and r["day"] == d), None)
            q = ((hit or {}).get("panel") or {}).get("size_quantiles") or {}
            vals.append(q.get("q50", float("nan")))
        ax.bar(x + (j - 1) * width, vals, width=width, label=d, alpha=0.9)
    ax.set_xticks(x)
    ax.set_xticklabels([VENUE_SHORT[v] for v in venues])
    ax.set_ylabel("median trade size (coin qty)")
    ax.set_title("Trade-size median by venue-day (ETH)")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    return _savefig(fig, OUT / "latency_size_regimes" / "figs" / "fig_size_quantiles.png")


def fig_latency_tob_hz(rows: list[dict[str, Any]]) -> Path:
    venues = list(CORE_VENUES)
    days = sorted({r["day"] for r in rows})
    fig, ax = plt.subplots(figsize=(7.5, 4.0))
    for v in venues:
        ys = []
        for d in days:
            hit = next((r for r in rows if r["venue"] == v and r["day"] == d), None)
            hz = ((hit or {}).get("panel") or {}).get("tob_update_hz", float("nan"))
            ys.append(hz if (hit or {}).get("tob_ok") else float("nan"))
        ax.plot(days, ys, "o-", label=VENUE_SHORT[v], color=VENUE_COLORS[v], lw=2)
    ax.set_ylabel("TOB update Hz")
    ax.set_title("TOB update rate (reaction-time proxy)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.autofmt_xdate(rotation=30)
    fig.tight_layout()
    return _savefig(fig, OUT / "latency_size_regimes" / "figs" / "fig_tob_hz.png")


def fig_latency_reaction(rows: list[dict[str, Any]]) -> Path:
    """Median TOB Δt (ms) vs trade Hz — desk regime scatter."""
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for v in CORE_VENUES:
        xs, ys, labs = [], [], []
        for r in rows:
            if r["venue"] != v or not r.get("tob_ok"):
                continue
            p = r.get("panel") or {}
            xs.append(p.get("trade_hz", float("nan")))
            ys.append(p.get("tob_median_dt_ms", float("nan")))
            labs.append(r["day"][-5:])
        ax.scatter(xs, ys, s=80, color=VENUE_COLORS[v], label=VENUE_SHORT[v], zorder=3)
        for x, y, lab in zip(xs, ys, labs):
            if np.isfinite(x) and np.isfinite(y):
                ax.annotate(lab, (x, y), textcoords="offset points", xytext=(4, 4), fontsize=7)
    ax.set_xlabel("trade Hz")
    ax.set_ylabel("median TOB Δt (ms)")
    ax.set_title("Size/latency regime scatter (Kill co-lo/Hibernia vanity)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return _savefig(fig, OUT / "latency_size_regimes" / "figs" / "fig_reaction_proxy.png")


def fig_latency_size_dist(rows: list[dict[str, Any]]) -> Path:
    """q10–q99 size ribbon by venue (mean across days)."""
    venues = list(CORE_VENUES)
    qs = ["q10", "q25", "q50", "q75", "q90", "q99"]
    fig, ax = plt.subplots(figsize=(7.5, 4.0))
    for v in venues:
        mats = []
        for r in rows:
            if r["venue"] != v:
                continue
            sq = ((r.get("panel") or {}).get("size_quantiles") or {})
            mats.append([sq.get(q, float("nan")) for q in qs])
        if not mats:
            continue
        arr = np.asarray(mats, dtype=float)
        med = np.nanmedian(arr, axis=0)
        ax.plot(qs, med, "o-", color=VENUE_COLORS[v], label=VENUE_SHORT[v], lw=2)
    ax.set_ylabel("trade size (coin qty)")
    ax.set_title("Trade-size quantile curve (day-median)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return _savefig(fig, OUT / "latency_size_regimes" / "figs" / "fig_size_curve.png")


# ── summaries + markdown writers ─────────────────────────────────────────────


def summarize_panel(rows: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [r for r in rows if (r.get("completeness") or {}).get("complete")]
    tob_ok = [r for r in rows if r.get("tob_ok")]
    by_venue: dict[str, Any] = {}
    for v in CORE_VENUES:
        vr = [r for r in rows if r["venue"] == v]
        hz = [float((r.get("panel") or {}).get("tob_update_hz") or np.nan) for r in vr if r.get("tob_ok")]
        dt = [float((r.get("panel") or {}).get("tob_median_dt_ms") or np.nan) for r in vr if r.get("tob_ok")]
        q50 = [
            float(((r.get("panel") or {}).get("size_quantiles") or {}).get("q50") or np.nan) for r in vr
        ]
        thz = [float((r.get("panel") or {}).get("trade_hz") or np.nan) for r in vr]
        by_venue[v] = {
            "n_days": len(vr),
            "n_complete": sum(1 for r in vr if (r.get("completeness") or {}).get("complete")),
            "n_tob": sum(1 for r in vr if r.get("tob_ok")),
            "n_synth_tob": sum(1 for r in vr if r.get("tob_synth")),
            "median_tob_hz": float(np.nanmedian(hz)) if hz else float("nan"),
            "median_tob_dt_ms": float(np.nanmedian(dt)) if dt else float("nan"),
            "median_trade_size_q50": float(np.nanmedian(q50)) if q50 else float("nan"),
            "median_trade_hz": float(np.nanmedian(thz)) if thz else float("nan"),
            "mean_n_trades": float(np.mean([r["n_trades"] for r in vr])) if vr else float("nan"),
        }
    return {
        "n_venue_days": len(rows),
        "n_complete": len(complete),
        "n_tob": len(tob_ok),
        "n_synth_tob": sum(1 for r in rows if r.get("tob_synth")),
        "by_venue": by_venue,
        "complete_keys": [
            f"{r['venue']}/{r['day']}" for r in complete
        ],
    }


def write_ch00_md(rows: list[dict[str, Any]], summary: dict[str, Any], days: list[str]) -> None:
    chap = BOOK / "chapters" / "ch00_overview"
    complete_n = summary["n_complete"]
    total = summary["n_venue_days"]
    notes = f"""# Ch.00 — Overview: HFT taxonomy

**Book:** Filimonov, Perm Winter School 2013  
**PDF:** slides (local) · **Status:** `pass1`  
**Raw:** [`../../_raw/`](../../_raw/) (local/gitignored)  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md) · Desk: [`../../DESK_MEMO.md`](../../DESK_MEMO.md)  
**Lib:** [`../../../../lib/hftpat.py`](../../../../lib/hftpat.py)

---

## Pass 1 focus

SEC-style HFT attributes, strategy map, reading order, sibling reuse table (deck slides **1–9**, strategy tile **17**).

### Deck citations
- Title / provenance: **p. 1** (Perm Winter School 2013)
- Hot topic / SSRN counts: **p. 2**
- Flash-crash framing (May 6 2010): **p. 3**
- CFTC HFT subcommittee (definition task): **p. 4**
- HFT market size / share (Aite, TABB): **p. 5**
- Technical revolutions / electronic milestones: **pp. 6–8**
- SEC (2010) HFT attribute list + latency×holding taxonomy: **p. 9**
- Strategy map (MM, stuffing, smoking, layering, ignition, hunting): **p. 17**

### SEC attributes → crypto desk mapping

| SEC attr (p. 9) | Crypto public-tape proxy |
|-----------------|--------------------------|
| High-speed programs | Venue TOB update Hz / trade Hz (`size_latency_panel`) |
| Co-location / private feeds | **Kill vanity** unless mapped to venue RTT panel (Pass 2+) |
| Short holding periods | Not directly observed without IDs — framing only |
| Numerous cancels | `quote_storm_*` / OTR aggregate (later packages) |
| Flat EOD | Not observable on public tape — framing only |

## Pass 2 dig

Taxonomy Promote only if desk labels add beyond `crash` / mmip / `lob`. Sibling reuse table is framing; detectors live in later packages.

## Pass checklist

### Pass 1
- [x] Cite deck pages in NOTES
- [x] Implement on HL + Deribit + Kraken
- [x] EXP_REPORT with day-completeness
- [x] Draft CANDIDATES

### Pass 2
- [ ] Info joins / falsifiers / overlap gates
- [ ] Signal board → DESK_MEMO

---

## Reading order

1. `ch00_overview` — taxonomy + sibling reuse
2. `latency_size_regimes` — size / TOB Hz framing
3. `quote_storms` — stuffing bursts
4. `book_fade` — post-trade depth fade
5. `momentum_ignition` — 3-phase events
6. `spoof_smoke_clock` — smoke / clock / OTR

## Sample snapshot (ETH slice)

Days: {", ".join(days)} — **{complete_n}/{total}** complete venue-days; TOB {summary["n_tob"]}/{total} (synth={summary["n_synth_tob"]}).

Artifacts: `out/ch00_overview/`.
"""
    (chap / "NOTES.md").write_text(notes)

    cands = """| id | type | lenses | decision | falsifier |
|----|------|--------|----------|----------|
| `disc.hft_taxonomy_tile` | framing | disc, risk, mm | **Hold** | Promote only if labels survive Pass 2 vs crash/mmip/lob rename gate |
| `disc.sec_attr_crypto_map` | framing | disc | **Hold** | co-lo / flat-EOD attrs unobservable on public tape |
| `id.colo_hibernia_vanity` | id | disc | **Kill** | equity co-lo RTT / Hibernia Express narrative without crypto venue RTT panel |
| `id.fx_triangle_fee_free` | id | disc | **Kill** | fee-free FX triangle (deck p. 22) without fee/latency haircut |
"""
    (chap / "CANDIDATES.md").write_text(cands)

    keys = ", ".join(f"`{k}`" for k in summary["complete_keys"])
    exp = f"""# ch00_overview — EXP_REPORT

## Pass 1
- Slice: **ETH** · venues {list(CORE_VENUES)} · days {days}
- Complete venue-days: **{complete_n}/{total}** → [{keys}]
- TOB venue-days: **{summary["n_tob"]}/{total}** (trade_synth={summary["n_synth_tob"]})
- Taxonomy: SEC attrs (p. 9) + strategy map (p. 17) → package reading order locked
- Sibling reuse: crash / vstat / lob / ticksize / mmip Hawkes — cross-link only (see `out/ch00_overview/sibling_reuse.json`)
- Runner: [`../../scripts/exp_ch00_latency.py`](../../scripts/exp_ch00_latency.py)

## Pass 2
- Not run. Taxonomy Promote gated on labels beyond crash/mmip/lob.

## Figures
- Notebook: [`ch00_overview.ipynb`](ch00_overview.ipynb)
- `out/ch00_overview/figs/fig_coverage.png`
- `out/ch00_overview/figs/fig_taxonomy.png`
- `out/ch00_overview/figs/fig_reading_order.png`
- `out/ch00_overview/figs/fig_sibling_reuse.png`
"""
    (chap / "EXP_REPORT.md").write_text(exp)


def write_latency_md(rows: list[dict[str, Any]], summary: dict[str, Any], days: list[str]) -> None:
    chap = BOOK / "chapters" / "latency_size_regimes"
    bv = summary["by_venue"]
    lines = [
        "| Venue | complete | tob | median TOB Hz | median Δt ms | median size q50 | median trade Hz |",
        "|-------|----------|-----|---------------|--------------|-----------------|-----------------|",
    ]
    for v in CORE_VENUES:
        s = bv[v]
        lines.append(
            f"| {v} | {s['n_complete']}/{s['n_days']} | {s['n_tob']} | "
            f"{s['median_tob_hz']:.4g} | {s['median_tob_dt_ms']:.4g} | "
            f"{s['median_trade_size_q50']:.4g} | {s['median_trade_hz']:.4g} |"
        )
    table = "\n".join(lines)

    notes = f"""# Latency / size regimes

**Book:** Filimonov, Perm Winter School 2013  
**PDF:** slides (local) · **Status:** `pass1`  
**Raw:** [`../../_raw/`](../../_raw/) (local/gitignored)  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md)  
**Lib:** [`../../../../lib/hftpat.py`](../../../../lib/hftpat.py) · `size_latency_panel`

---

## Pass 1 focus

TOB update Hz, trade-size quantiles, reaction-time proxies on HL+Deribit+Kraken (deck slides **10–20**).

### Deck citations
- Client–broker–market / DMA: **p. 10**
- Typical trading process (quote→decision→risk→gateway): **pp. 11–12**
- Speed-of-light annoyance quote (Bach / NYSE): **p. 13**
- Co-location RTT <40–50 µs (NASDAQ OMX): **p. 14** — **Kill vanity** for crypto desk unless remapped
- Distance / fiber RTT table (NY–Chicago etc.): **p. 15**
- Hibernia Express ($300M / −6 ms): **p. 16** — **Kill** as equity vanity
- Strategy map (MM first): **p. 17**
- Market making / spread + rebates: **p. 18**
- MM reaction-time history (ms→sub-ms): **p. 19**
- Typical trade volume median vs average (commodities / E-mini): **p. 20**

## Pass 2 dig

Regime **monitor** vs tradable; keep Kill on co-lo / Hibernia unless crypto venue RTT panel exists. Early/late day split + bootstrap on size/Hz when n allows.

## Pass checklist

### Pass 1
- [x] Cite deck pages in NOTES
- [x] Implement on HL + Deribit + Kraken
- [x] EXP_REPORT with day-completeness
- [x] Draft CANDIDATES

### Pass 2
- [ ] Info joins / falsifiers
- [ ] Signal board → DESK_MEMO

## Key numbers (ETH, {len(days)} days × 3 venues)

{table}

Days: {", ".join(days)} — complete **{summary["n_complete"]}/{summary["n_venue_days"]}**; TOB **{summary["n_tob"]}** (synth={summary["n_synth_tob"]}).
"""
    (chap / "NOTES.md").write_text(notes)

    # numeric falsifier stubs from panel
    hl = bv.get("hyperliquid", {})
    db = bv.get("deribit", {})
    kr = bv.get("kraken", {})
    cands = f"""| id | type | lenses | decision | falsifier |
|----|------|--------|----------|----------|
| `mm.size_latency_regime_panel` | monitor | mm, risk, exec | **Hold** | day-median HL TOB Hz={hl.get('median_tob_hz')}; DB={db.get('median_tob_hz')}; KR={kr.get('median_tob_hz')}; early/late + day-block bootstrap in Pass 2 |
| `mm.trade_size_quantile_curve` | framing | mm, liq | **Hold** | q50 HL={hl.get('median_trade_size_q50')}; DB={db.get('median_trade_size_q50')}; KR={kr.get('median_trade_size_q50')} — not α |
| `id.colo_rtt_40us_claim` | id | disc | **Kill** | deck p.14 NASDAQ co-lo <40–50µs — no crypto venue RTT mapping in this slice |
| `id.hibernia_express_6ms` | id | disc | **Kill** | deck p.16 Hibernia Express −6ms / $300M — equity transatlantic vanity |
| `id.fiber_distance_table` | id | disc | **Kill** | deck p.15 NY–Chicago fiber table without crypto xvenue RTT haircut |
"""
    (chap / "CANDIDATES.md").write_text(cands)

    exp = f"""# latency_size_regimes — EXP_REPORT

## Pass 1
- Slice: **ETH** · venues {list(CORE_VENUES)} · days {days}
- Complete venue-days: **{summary["n_complete"]}/{summary["n_venue_days"]}**
- TOB venue-days: **{summary["n_tob"]}/{summary["n_venue_days"]}** (trade_synth={summary["n_synth_tob"]})
- Detector: `hftpat.size_latency_panel` (trade-size quantiles + TOB Hz + median Δt + trade Hz)
- By venue (day-medians):

{table}

- Kill list applied: co-lo µs vanity (p.14), Hibernia (p.16), fiber distance table (p.15) — candidates marked **Kill**
- Runner: [`../../scripts/exp_ch00_latency.py`](../../scripts/exp_ch00_latency.py)
- JSON: `out/latency_size_regimes/panel.json`, `summary.json`

## Pass 2
- Not run. Planned: early/late sign check, day-block bootstrap on Hz/size, monitor vs tradable label.

## Figures
- Notebook: [`latency_size_regimes.ipynb`](latency_size_regimes.ipynb)
- `out/latency_size_regimes/figs/fig_size_quantiles.png`
- `out/latency_size_regimes/figs/fig_tob_hz.png`
- `out/latency_size_regimes/figs/fig_reaction_proxy.png`
- `out/latency_size_regimes/figs/fig_size_curve.png`
"""
    (chap / "EXP_REPORT.md").write_text(exp)


def write_notebooks() -> None:
    """Minimal memo notebooks that load out/ JSON + display figs."""

    def nb(cells: list[tuple[str, str]]) -> dict:
        out_cells = []
        for kind, src in cells:
            if kind == "md":
                out_cells.append(
                    {
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": [line + "\n" for line in src.split("\n")],
                    }
                )
            else:
                out_cells.append(
                    {
                        "cell_type": "code",
                        "execution_count": None,
                        "metadata": {},
                        "outputs": [],
                        "source": [line + "\n" for line in src.split("\n")],
                    }
                )
        return {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {
                "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                "language_info": {"name": "python", "pygments_lexer": "ipython3"},
            },
            "cells": out_cells,
        }

    ch00 = nb(
        [
            (
                "md",
                "# Ch.00 — Overview: HFT taxonomy\n\n"
                "Filimonov, *High-Frequency Trading* (Perm Winter School 2013).  \n"
                "Slice: **ETH** on **Hyperliquid + Deribit + Kraken**, artifacts in `out/ch00_overview/`.  \n"
                "Lib: `ares_micro.flow.hftpat` (framing only here). Kill: co-lo / Hibernia vanity.",
            ),
            (
                "code",
                "import json\n"
                "from pathlib import Path\n"
                "import pandas as pd\n"
                "from IPython.display import Image, display, Markdown\n\n"
                "BOOK = (Path(os.environ.get('ARES_MICROSTRUCTURE') or (Path.home() / 'srv' / 'ares-microstructure')) / 'research' / 'books' / 'filmonov')\n"
                "OUT = BOOK / 'out' / 'ch00_overview'\n"
                "FIGS = OUT / 'figs'\n"
                "cov = json.loads((OUT / 'coverage.json').read_text())\n"
                "tax = json.loads((OUT / 'taxonomy.json').read_text())\n"
                "print('symbol', cov.get('symbol'), 'days', cov.get('days'))\n"
                "print('n_complete', cov['summary']['n_complete'], '/', cov['summary']['n_venue_days'],\n"
                "      'n_tob', cov['summary']['n_tob'])\n"
                "rows = pd.DataFrame([\n"
                "    {'venue': r['venue'], 'day': r['day'],\n"
                "     'complete': r['completeness']['complete'],\n"
                "     'coverage': r['completeness']['coverage'],\n"
                "     'n': r['n_trades'], 'tob_ok': r['tob_ok'],\n"
                "     'tob_source': r.get('tob_source')}\n"
                "    for r in cov['rows']\n"
                "])\n"
                "print(rows.pivot_table(index='venue', columns='day', values='coverage').round(3))\n"
                "print('SEC attrs:', len(tax['sec_attrs']), '| strategies:', len(tax['strategy_map']))\n",
            ),
            ("md", "## Day-completeness coverage\n"),
            (
                "code",
                "display(Image(filename=str(FIGS / 'fig_coverage.png')))\n",
            ),
            ("md", "## Taxonomy tile (deck strategy map → packages)\n"),
            (
                "code",
                "display(Image(filename=str(FIGS / 'fig_taxonomy.png')))\n"
                "display(Image(filename=str(FIGS / 'fig_reading_order.png')))\n",
            ),
            ("md", "## Sibling reuse (do not re-Promote crash/vstat/lob)\n"),
            (
                "code",
                "display(Image(filename=str(FIGS / 'fig_sibling_reuse.png')))\n"
                "sib = json.loads((OUT / 'sibling_reuse.json').read_text())\n"
                "display(pd.DataFrame(sib))\n",
            ),
            (
                "md",
                "## Candidates (Pass 1 draft)\n\n"
                "- `disc.hft_taxonomy_tile` — **Hold** (Promote only if labels add beyond crash/mmip/lob)\n"
                "- `id.colo_hibernia_vanity` — **Kill**\n"
                "- `id.fx_triangle_fee_free` — **Kill**\n",
            ),
        ]
    )
    (BOOK / "chapters" / "ch00_overview" / "ch00_overview.ipynb").write_text(
        json.dumps(ch00, indent=1)
    )

    lat = nb(
        [
            (
                "md",
                "# Latency / size regimes\n\n"
                "Deck slides 10–20 → `hftpat.size_latency_panel`.  \n"
                "Slice: **ETH** · HL+Deribit+Kraken · `out/latency_size_regimes/`.  \n"
                "**Kill:** co-lo µs claims, Hibernia Express, fiber distance vanity.",
            ),
            (
                "code",
                "import json\n"
                "from pathlib import Path\n"
                "import pandas as pd\n"
                "from IPython.display import Image, display\n\n"
                "BOOK = (Path(os.environ.get('ARES_MICROSTRUCTURE') or (Path.home() / 'srv' / 'ares-microstructure')) / 'research' / 'books' / 'filmonov')\n"
                "OUT = BOOK / 'out' / 'latency_size_regimes'\n"
                "FIGS = OUT / 'figs'\n"
                "panel = json.loads((OUT / 'panel.json').read_text())\n"
                "summary = json.loads((OUT / 'summary.json').read_text())\n"
                "print('days', panel['days'], 'n_complete', summary['n_complete'], '/', summary['n_venue_days'])\n"
                "flat = []\n"
                "for r in panel['rows']:\n"
                "    p = r.get('panel') or {}\n"
                "    flat.append({\n"
                "        'venue': r['venue'], 'day': r['day'],\n"
                "        'complete': r['completeness']['complete'],\n"
                "        'tob_ok': r['tob_ok'], 'tob_synth': r.get('tob_synth'),\n"
                "        'tob_hz': p.get('tob_update_hz'),\n"
                "        'tob_dt_ms': p.get('tob_median_dt_ms'),\n"
                "        'trade_hz': p.get('trade_hz'),\n"
                "        'size_q50': (p.get('size_quantiles') or {}).get('q50'),\n"
                "        'size_q99': (p.get('size_quantiles') or {}).get('q99'),\n"
                "        'n_trades': r['n_trades'],\n"
                "    })\n"
                "df = pd.DataFrame(flat)\n"
                "print(df.groupby('venue')[['tob_hz','tob_dt_ms','trade_hz','size_q50']].median())\n",
            ),
            ("md", "## Trade-size medians by venue-day\n"),
            ("code", "display(Image(filename=str(FIGS / 'fig_size_quantiles.png')))\n"),
            ("md", "## TOB update Hz (reaction-time proxy)\n"),
            ("code", "display(Image(filename=str(FIGS / 'fig_tob_hz.png')))\n"),
            ("md", "## Regime scatter + size quantile curve\n"),
            (
                "code",
                "display(Image(filename=str(FIGS / 'fig_reaction_proxy.png')))\n"
                "display(Image(filename=str(FIGS / 'fig_size_curve.png')))\n",
            ),
            (
                "md",
                "## Candidates (Pass 1 draft)\n\n"
                "- `mm.size_latency_regime_panel` — **Hold** (monitor; Pass 2 bootstrap)\n"
                "- `id.colo_rtt_40us_claim` / `id.hibernia_express_6ms` / `id.fiber_distance_table` — **Kill**\n",
            ),
        ]
    )
    (BOOK / "chapters" / "latency_size_regimes" / "latency_size_regimes.ipynb").write_text(
        json.dumps(lat, indent=1)
    )


def patch_chapter_index(days: list[str], summary: dict[str, Any]) -> None:
    """Note pass1 status for ch00 + latency only — do not mark exp_run-complete."""
    path = BOOK / "CHAPTER_INDEX.md"
    text = path.read_text()
    # Program status line
    old = "**Program status:** **Scaffold** — lib + package stubs; Pass 1 empirics not started."
    new = (
        "**Program status:** **Pass 1 partial** — `ch00_overview` + `latency_size_regimes` "
        f"Pass 1 on ETH days {days} ({summary['n_complete']}/{summary['n_venue_days']} complete); "
        "other packages still scaffold. Not `exp_run`-complete."
    )
    if old in text:
        text = text.replace(old, new)
    # Package table status cells for our two only
    text = text.replace(
        "| `ch00_overview` | SEC HFT attrs, strategy map, reading order, sibling reuse (slides 1–9) | Taxonomy Promote only if labels beyond crash/mmip | `todo` |",
        "| `ch00_overview` | SEC HFT attrs, strategy map, reading order, sibling reuse (slides 1–9) | Taxonomy Promote only if labels beyond crash/mmip | `pass1` |",
    )
    text = text.replace(
        "| `latency_size_regimes` | TOB update Hz, trade-size quantiles, reaction proxies (slides 10–20) | Regime monitor vs tradable; Kill co-lo / Hibernia vanity | `todo` |",
        "| `latency_size_regimes` | TOB update Hz, trade-size quantiles, reaction proxies (slides 10–20) | Regime monitor vs tradable; Kill co-lo / Hibernia vanity | `pass1` |",
    )
    # Figure index note
    text = text.replace(
        "Chapter notebooks will load `fig_*.png` from `out/<pkg>/figs/` after Pass 1 (not yet built).",
        "Chapter notebooks load `fig_*.png` from `out/<pkg>/figs/`. "
        "`ch00_overview` + `latency_size_regimes` Pass 1 figs built; others pending.",
    )
    text = text.replace(
        "| `ch00_overview` | `out/ch00_overview/figs/` | taxonomy tile, reading order, sibling reuse |",
        "| `ch00_overview` | `out/ch00_overview/figs/` | coverage, taxonomy, reading order, sibling reuse |",
    )
    text = text.replace(
        "| `latency_size_regimes` | `out/latency_size_regimes/figs/` | size quantiles, TOB Hz panel |",
        "| `latency_size_regimes` | `out/latency_size_regimes/figs/` | size quantiles, TOB Hz, reaction scatter, size curve |",
    )
    # Promote rollup note — pass1 only, no freeze
    if "*(empty — Pass 1 not run)*" in text:
        text = text.replace(
            "*(empty — Pass 1 not run)*",
            "*(Pass 1 draft for ch00/latency only — no Promote freeze; Hold taxonomy + Kill Hibernia/co-lo)*",
        )
    path.write_text(text)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--days", nargs="*", default=None)
    ap.add_argument("--n-days", type=int, default=3)
    ap.add_argument("--max-files", type=int, default=24)
    ap.add_argument("--skip-md", action="store_true", help="skip NOTES/CANDIDATES/EXP_REPORT rewrite")
    args = ap.parse_args()

    ensure_env()
    days = resolve_eth_days(args.days, args.n_days)
    symbol = args.symbol.upper()
    print(f"symbol={symbol} days={days} venues={CORE_VENUES}")

    rows: list[dict[str, Any]] = []
    for day in days:
        for venue in CORE_VENUES:
            print(f"  load {venue}/{day} …", flush=True)
            try:
                row = build_venue_day(symbol, day, venue, max_files=args.max_files)
            except Exception as exc:  # noqa: BLE001
                row = {
                    "venue": venue,
                    "symbol": symbol,
                    "day": day,
                    "error": f"{type(exc).__name__}: {exc}",
                    "completeness": {"complete": False, "reasons": ["load_error"], "n": 0, "coverage": 0.0},
                    "n_trades": 0,
                    "tob_ok": False,
                    "panel": {},
                }
            rows.append(row)
            c = row.get("completeness") or {}
            print(
                f"    complete={c.get('complete')} n={c.get('n')} "
                f"tob={row.get('tob_ok')} hz={(row.get('panel') or {}).get('tob_update_hz')}",
                flush=True,
            )

    summary = summarize_panel(rows)

    # ch00 artifacts
    coverage = {
        "symbol": symbol,
        "days": days,
        "venues": list(CORE_VENUES),
        "rows": rows,
        "summary": summary,
        "day_source": "mm_confr_pass1" if (MM_CONFR / "out" / "pass1" / "panel.json").is_file() else "resolve_days",
    }
    _json(OUT / "ch00_overview" / "coverage.json", coverage)
    _json(
        OUT / "ch00_overview" / "taxonomy.json",
        {
            "sec_attrs": SEC_ATTRS,
            "strategy_map": STRATEGY_MAP,
            "reading_order": [s["pkg"] for s in STRATEGY_MAP if s["pkg"] != "(framing)"],
            "deck_pages": "1-9, 17",
        },
    )
    _json(OUT / "ch00_overview" / "sibling_reuse.json", SIBLING_REUSE)

    # latency artifacts
    _json(
        OUT / "latency_size_regimes" / "panel.json",
        {"symbol": symbol, "days": days, "venues": list(CORE_VENUES), "rows": rows},
    )
    _json(OUT / "latency_size_regimes" / "summary.json", summary)

    # figures
    figs = [
        fig_ch00_coverage(rows),
        fig_ch00_taxonomy(),
        fig_ch00_reading_order(),
        fig_ch00_sibling(),
        fig_latency_size_quantiles(rows),
        fig_latency_tob_hz(rows),
        fig_latency_reaction(rows),
        fig_latency_size_dist(rows),
    ]
    print("figs:", *[str(p.relative_to(BOOK)) for p in figs], sep="\n  ")

    if not args.skip_md:
        write_ch00_md(rows, summary, days)
        write_latency_md(rows, summary, days)
        write_notebooks()
        patch_chapter_index(days, summary)

    print(
        f"DONE complete={summary['n_complete']}/{summary['n_venue_days']} "
        f"tob={summary['n_tob']} synth={summary['n_synth_tob']}"
    )
    for v, s in summary["by_venue"].items():
        print(
            f"  {v}: tob_hz={s['median_tob_hz']:.4g} dt_ms={s['median_tob_dt_ms']:.4g} "
            f"size_q50={s['median_trade_size_q50']:.4g} trade_hz={s['median_trade_hz']:.4g}"
        )


if __name__ == "__main__":
    main()
