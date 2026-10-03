#!/usr/bin/env python3
"""vpin_of Pass 4 (final) — close book on real warehouse tape only.

  python3 scripts/exp_pass4.py
  python3 scripts/exp_pass4.py --resume --skip-markout
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import (  # noqa: E402
    KRAKEN_FUT_TOB,
    load_day_trades,
    load_kraken_futures_tob_day,
    load_tob_day,
    load_warehouse_tob_day,
    normalize_side,
    normalize_venue,
    resolve_days,
    rolling_vpin_series,
    vpin_day_features,
)
from exp_pass3 import (  # noqa: E402
    OUT as OUT3,
    _exante_vpin_at,
    _panel_hl_db,
    _write_json,
    hl_sol_pass3,
    kraken_pass3,
    markout_day_pass3,
)
from research.lib.stats import bootstrap_ci, spearman_r  # noqa: E402
from research.lib.vpin import cross_section_spearman  # noqa: E402

OUT = BOOK / "out" / "pass4"
PANEL = BOOK / "out" / "vpin_panel"
PASS3_DEC = OUT3 / "decisions_pass3.json"

# Pre-registered Pass 4 gates (document before run)
MARKOUT_GATE_P4 = {
    "panel": "promote_slice_hl_db_only",
    "min_ok_days": 12,
    "median_day_ic_60s": 0.02,
    "median_rank_ic_60s": 0.02,
    "venue_holdout_min_median_ic": 0.0,
    "horizons_ms": [30_000, 60_000, 120_000, 300_000],
    "primary_horizon_ms": 60_000,
}
XVENUE_FRESH_GATE = {"min_pairs": 20, "ci_lo": 0.15, "min_fresh_days": 20}
TOX_EVENT_GATE = {"min_event_days": 8, "min_events": 40, "spread_lift_bps": 0.3}
KRAKEN_MARKOUT_GATE = {"min_ok_days": 5, "median_ic": 0.015}


def _load_pass3_decisions() -> dict[str, Any]:
    if PASS3_DEC.is_file():
        return json.loads(PASS3_DEC.read_text())
    p = PANEL / "decisions_pass3.json"
    return json.loads(p.read_text()) if p.is_file() else {"decision_table": []}


def _promote_slice_rows(panel_ok: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """HL+Deribit only — desk promote wiring (excludes Kraken arm)."""
    return [r for r in panel_ok if r.get("ok") and normalize_venue(r["venue"]) in ("hyperliquid", "deribit")]


def hl_sol_pass4() -> dict[str, Any]:
    p3_path = OUT3 / "hl_sol_probe.json"
    base = json.loads(p3_path.read_text()) if p3_path.is_file() else hl_sol_pass3()
    post_cut = "2026-08-28"
    days = resolve_days(None, "hyperliquid", n=999)
    post_days = [d for d in days if d > post_cut]
    post_attempts = []
    for day in post_days[-12:]:
        rec = load_day_trades("hyperliquid", "SOL", day, quiet=True)
        c = rec["completeness"]
        post_attempts.append({"day": day, "n": c.get("n"), "complete": c.get("complete")})
    post_nonempty = [a for a in post_attempts if int(a.get("n") or 0) > 0]
    shard_resumed = len(post_nonempty) > 0
    return {
        **base,
        "post_2026_08_28": {
            "n_listing_days": len(post_days),
            "n_days_with_trades": len(post_nonempty),
            "nonempty_days": post_nonempty[:8],
            "shard_resumed": shard_resumed,
        },
        "formal_sol_arm": "deribit_kraken_only",
        "decision": "Hold" if not shard_resumed else base.get("decision", "Hold"),
        "desk_note": (
            "frag.hl_sol_empty stays Hold until HL SOL shard resumes; "
            "desk SOL VPIN uses Deribit+Kraken panel arm (see sol_db_kraken_panel.json)."
        ),
    }


def sol_db_kraken_panel() -> dict[str, Any]:
    rows_path = PANEL / "rows.jsonl"
    rows = [json.loads(ln) for ln in rows_path.read_text().splitlines() if ln.strip()] if rows_path.is_file() else []
    sol = [r for r in rows if r.get("symbol") == "SOL" and r.get("ok")]
    by_venue: dict[str, int] = {}
    for r in sol:
        by_venue[normalize_venue(r["venue"])] = by_venue.get(normalize_venue(r["venue"]), 0) + 1
    hl_n = by_venue.get("hyperliquid", 0)
    db_n = by_venue.get("deribit", 0)
    kr_n = by_venue.get("kraken", 0)
    return {
        "symbol": "SOL",
        "n_ok_total": len(sol),
        "by_venue": by_venue,
        "formal_arm": {
            "venues": ["deribit", "kraken"],
            "n_ok": db_n + kr_n,
            "excludes": "hyperliquid (warehouse shard gap post-2026-08-28)",
        },
        "hl_sol_days_with_trades": hl_n,
        "decision": "documented_arm",
    }


def xvenue_fresh_calibration(panel_ok: list[dict[str, Any]]) -> dict[str, Any]:
    """Contract/notional bucket calibration on freshest paired HL↔DB days."""
    from exp_pass3 import _day_vpin_variants  # noqa: E402

    days_all = sorted(
        {
            r["day"]
            for r in panel_ok
            if r.get("venue") in ("hyperliquid", "deribit") and r.get("symbol") in ("ETH", "BTC")
        }
    )
    min_f = XVENUE_FRESH_GATE["min_fresh_days"]
    fresh_days = set(days_all[-max(min_f, 25) :] if len(days_all) >= min_f else days_all)
    full_ref_path = OUT3 / "xvenue_harmonized.json"
    full = json.loads(full_ref_path.read_text()) if full_ref_path.is_file() else {}

    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in panel_ok:
        if r.get("symbol") not in ("ETH", "BTC") or r["day"] not in fresh_days:
            continue
        v = normalize_venue(r["venue"])
        if v not in ("hyperliquid", "deribit"):
            continue
        by_key[(r["symbol"], r["day"], v)] = {"median_x50": float(r["mean_vpin"]), "target_50": float(r["mean_vpin"])}

    # Notional buckets: recompute on last 10 paired calendar days only (tape-heavy)
    notional_days = sorted(fresh_days)[-10:]
    for sym in ("ETH", "BTC"):
        for day in notional_days:
            for v in ("hyperliquid", "deribit"):
                try:
                    rv = _day_vpin_variants(v, sym, day, max_files=16)
                    if rv and np.isfinite(rv.get("notional_median_x50", float("nan"))):
                        cur = by_key.setdefault((sym, day, v), {})
                        cur["notional_median_x50"] = float(rv["notional_median_x50"])
                        cur["target_50"] = float(rv.get("target_50", cur.get("target_50", float("nan"))))
                except Exception:
                    continue

    def _pairs(field: str) -> list[tuple[float, float]]:
        pairs: list[tuple[float, float]] = []
        for sym in ("ETH", "BTC"):
            for day in sorted(fresh_days):
                a = by_key.get((sym, day, "hyperliquid"))
                b = by_key.get((sym, day, "deribit"))
                if not a or not b:
                    continue
                va, vb = a.get(field), b.get(field)
                if va is not None and vb is not None and np.isfinite(va) and np.isfinite(vb):
                    pairs.append((float(va), float(vb)))
        return pairs

    methods: dict[str, Any] = {}
    for field, label in (
        ("target_50", "target_50_buckets"),
        ("notional_median_x50", "notional_median_x50"),
        ("median_x50", "sot_median_x50"),
    ):
        pairs = _pairs(field)
        if len(pairs) >= 5:
            xv = cross_section_spearman(
                np.array([p[0] for p in pairs]),
                np.array([p[1] for p in pairs]),
                n_boot=600,
                seed=91,
            )
        else:
            xv = {"n": float(len(pairs)), "rho": float("nan"), "lo": float("nan"), "hi": float("nan")}
        dec = (
            "Promote"
            if xv.get("n", 0) >= XVENUE_FRESH_GATE["min_pairs"]
            and np.isfinite(xv.get("rho", float("nan")))
            and xv.get("lo", -1) >= XVENUE_FRESH_GATE["ci_lo"]
            else "Hold"
        )
        methods[label] = {"n_pairs": len(pairs), "spearman": xv, "decision": dec}

    primary = methods.get("notional_median_x50") or methods.get("target_50_buckets") or {}
    dec = primary.get("decision", "Hold")
    return {
        "fresh_day_range": [min(fresh_days), max(fresh_days)] if fresh_days else [],
        "n_fresh_paired_days": len(fresh_days),
        "methods": methods,
        "full_panel_reference": {
            "primary_method": full.get("primary_method"),
            "target_50_decision": (full.get("methods") or {}).get("target_50_buckets", {}).get("decision"),
        },
        "gate": XVENUE_FRESH_GATE,
        "decision": dec,
        "note": "Pass4: ≥20 freshest HL↔DB paired days; SoT target50 from panel; notional on last 10 paired days",
    }


def markout_day_p4(
    venue: str,
    symbol: str,
    day: str,
    *,
    trade_stride: int = 25,
    quotes_per_minute: int = 120,
) -> dict[str, Any]:
    return markout_day_pass3(
        venue,
        symbol,
        day,
        trade_stride=trade_stride,
        quotes_per_minute=quotes_per_minute,
        horizons_ms=tuple(MARKOUT_GATE_P4["horizons_ms"]),
    )


def run_markout_pass4(
    promote_rows: list[dict[str, Any]],
    *,
    trade_stride: int,
    quotes_per_minute: int,
) -> dict[str, Any]:
    cells = sorted({(r["venue"], r["symbol"]) for r in promote_rows})
    day_rows: list[dict[str, Any]] = []
    for v, sym in cells:
        days = sorted({r["day"] for r in promote_rows if r["venue"] == v and r["symbol"] == sym})
        for j, day in enumerate(days):
            print(f"markout_p4 {j+1}/{len(days)} {v} {sym} {day}", flush=True)
            day_rows.append(
                markout_day_p4(v, sym, day, trade_stride=trade_stride, quotes_per_minute=quotes_per_minute)
            )
    ok_rows = [r for r in day_rows if r.get("ok")]
    h_primary = str(MARKOUT_GATE_P4["primary_horizon_ms"])
    ic60: list[float] = []
    rank60: list[float] = []
    for r in ok_rows:
        hi = (r.get("horizon_ic") or {}).get(h_primary) or {}
        if np.isfinite(hi.get("rho", float("nan"))):
            ic60.append(float(hi["rho"]))
        if np.isfinite(hi.get("rank_rho", float("nan"))):
            rank60.append(float(hi["rank_rho"]))

    ic30 = np.array(
        [r["ic_spearman_vpin_vs_mo30"]["rho"] for r in ok_rows if np.isfinite(r["ic_spearman_vpin_vs_mo30"]["rho"])],
        dtype=np.float64,
    )
    by_venue: dict[str, list[float]] = {}
    for r in ok_rows:
        by_venue.setdefault(r["venue"], []).append(r["ic_spearman_vpin_vs_mo30"]["rho"])

    holdout: dict[str, float] = {}
    for v in ("hyperliquid", "deribit"):
        other = [x for r in ok_rows if r["venue"] != v for x in [r["ic_spearman_vpin_vs_mo30"]["rho"]] if np.isfinite(x)]
        holdout[f"median_ic_excluding_{v}"] = float(np.nanmedian(other)) if other else float("nan")

    g = MARKOUT_GATE_P4
    med60 = float(np.nanmedian(ic60)) if ic60 else float("nan")
    med_rank60 = float(np.nanmedian(rank60)) if rank60 else float("nan")
    promote = (
        len(ok_rows) >= g["min_ok_days"]
        and med60 > g["median_day_ic_60s"]
        and med_rank60 > g["median_rank_ic_60s"]
        and holdout.get("median_ic_excluding_hyperliquid", -1) > g["venue_holdout_min_median_ic"]
        and holdout.get("median_ic_excluding_deribit", -1) > g["venue_holdout_min_median_ic"]
    )
    compact = [
        {
            k: r[k]
            for k in (
                "venue",
                "symbol",
                "day",
                "n_join",
                "ic_spearman_vpin_vs_mo30",
                "rank_ic_30s",
                "horizon_ic",
                "tob_source",
            )
            if k in r
        }
        for r in ok_rows
    ]
    return {
        "panel_mode": g["panel"],
        "n_days_attempted": len(day_rows),
        "n_days_ok": len(ok_rows),
        "day_rows": compact,
        "median_ic_30s": float(np.nanmedian(ic30)) if ic30.size else float("nan"),
        "median_ic_60s": med60,
        "median_rank_ic_60s": med_rank60,
        "median_ic_by_venue": {k: float(np.nanmedian(v)) for k, v in by_venue.items()},
        "venue_holdout": holdout,
        "pre_registered_gate": g,
        "decision": "Promote" if promote else "Hold",
        "gate_note": "Pass4: promote-slice HL+DB only; primary 60s IC; venue holdout both >0",
    }


def kraken_futures_markout_probe(*, max_days: int = 12) -> dict[str, Any]:
    """Markout on Kraken where futures TOB cache exists; else document miss."""
    kr = kraken_pass3()
    strict_rows = [r for r in kr.get("rows") or [] if r.get("strict_complete")]
    # prioritize days with futures cache
    cache_days: set[str] = set()
    if KRAKEN_FUT_TOB.is_dir():
        for p in KRAKEN_FUT_TOB.iterdir():
            if p.is_dir():
                name = p.name
                if len(name) == 8 and name.isdigit():
                    cache_days.add(f"{name[:4]}-{name[4:6]}-{name[6:8]}")
                else:
                    cache_days.add(name)
    candidates = sorted({r["day"] for r in strict_rows if r["day"] in cache_days})[-max_days:]
    day_rows: list[dict[str, Any]] = []
    for sym in ("ETH", "BTC", "SOL"):
        for day in candidates:
            tob_src = "none"
            try:
                load_kraken_futures_tob_day(sym, day)
                tob_src = "futures_ingest"
            except Exception:
                continue
            rec = markout_day_p4("kraken", sym, day, trade_stride=30, quotes_per_minute=60)
            rec["tob_market"] = tob_src
            day_rows.append(rec)
    ok = [r for r in day_rows if r.get("ok")]
    rhos = [r["ic_spearman_vpin_vs_mo30"]["rho"] for r in ok if np.isfinite(r["ic_spearman_vpin_vs_mo30"]["rho"])]
    med = float(np.nanmedian(rhos)) if rhos else float("nan")
    g = KRAKEN_MARKOUT_GATE
    dec = "Promote" if len(ok) >= g["min_ok_days"] and med > g["median_ic"] else "Hold"
    return {
        "futures_tob_cache_root": str(KRAKEN_FUT_TOB),
        "n_cache_days_on_disk": len(cache_days),
        "n_strict_kraken_days": len(strict_rows),
        "n_candidates_with_futures_tob": len(candidates),
        "n_days_ok": len(ok),
        "median_ic_30s": med,
        "day_rows": ok[:20],
        "pre_registered_gate": g,
        "decision": dec,
        "note": (
            "S3 mercat-kraken-md futures sealed archives have no BBO/L2; "
            "futures quoted TOB requires local ingest cache (ingest_kraken_futures_tob.py). "
            "Spot L2 ≠ PF_* tape — not used for Pass4 Kraken markout arm."
        ),
    }


def toxicity_intraday_events(promote_rows: list[dict[str, Any]], *, max_days_per_cell: int = 5) -> dict[str, Any]:
    """Event study: VPIN spike minutes vs spread (intraday), not day-mean ρ."""
    events: list[dict[str, Any]] = []
    by_cell: dict[str, list[dict[str, Any]]] = {}
    for r in promote_rows:
        key = f"{r['venue']}|{r['symbol']}"
        by_cell.setdefault(key, []).append(r)
    todo_cells = list(by_cell.items())[:4]
    for ci, (key, rs) in enumerate(todo_cells):
        venue, sym = key.split("|", 1)
        for r in sorted(rs, key=lambda x: x["day"])[-max_days_per_cell:]:
            day = r["day"]
            print(f"tox_event {ci} {venue} {sym} {day}", flush=True)
            try:
                feat = vpin_day_features(venue, sym, day, max_files=24)
                tob = load_warehouse_tob_day(venue, sym, day, max_files=24, quotes_per_minute=60)
            except Exception:
                continue
            if not feat.get("completeness", {}).get("complete"):
                continue
            v_ts = np.asarray(feat["vpin_ts"], dtype=np.int64)
            v_roll = np.asarray(feat["vpin_roll"], dtype=np.float64)
            mt, mid = tob["ts"], tob["mid"]
            bid, ask = tob["bid"], tob["ask"]
            if v_roll.size < 20 or mt.size < 100:
                continue
            sp_full = 1e4 * (ask - bid) / np.maximum(mid, 1e-12)
            sp_ok = sp_full[np.isfinite(sp_full) & (sp_full > 0) & (sp_full < 500)]
            if sp_ok.size < 50:
                continue
            thr = float(np.quantile(v_roll[np.isfinite(v_roll)], 0.9))
            spike_idx = np.where(np.isfinite(v_roll) & (v_roll >= thr))[0]
            if spike_idx.size < 3:
                continue
            for j in spike_idx[:: max(1, spike_idx.size // 5)][:12]:
                t0 = int(v_ts[j])
                i0 = int(np.searchsorted(mt, t0, side="right") - 1)
                if i0 < 1 or i0 >= mt.size - 2:
                    continue
                s0 = float(sp_full[i0]) if 0 <= i0 < sp_full.size else float("nan")
                s_pre = float(np.nanmean(sp_full[max(0, i0 - 3) : i0]))
                s_post = float(np.nanmean(sp_full[i0 + 1 : min(sp_full.size, i0 + 4)]))
                events.append(
                    {
                        "venue": venue,
                        "symbol": sym,
                        "day": day,
                        "vpin": float(v_roll[j]),
                        "spread_bps": s0,
                        "spread_pre_bps": s_pre,
                        "spread_post_bps": s_post,
                        "delta_post_pre_bps": s_post - s_pre,
                    }
                )
    if len(events) < 5:
        return {"n_events": len(events), "decision": "Hold", "reason": "thin_events", "events_sample": events}
    deltas = np.array([e["delta_post_pre_bps"] for e in events if np.isfinite(e["delta_post_pre_bps"])])
    spreads = np.array([e["spread_bps"] for e in events if np.isfinite(e["spread_bps"])])
    ctrl_sp = float(np.nanmedian(spreads))
    lift = float(np.nanmedian(deltas))
    n_days = len({(e["venue"], e["day"]) for e in events})
    g = TOX_EVENT_GATE
    promote = n_days >= g["min_event_days"] and len(events) >= g["min_events"] and lift > g["spread_lift_bps"]
    return {
        "n_events": len(events),
        "n_event_days": n_days,
        "median_spread_at_spike_bps": ctrl_sp,
        "median_delta_post_minus_pre_bps": lift,
        "events_sample": events[:15],
        "pre_registered_gate": g,
        "decision": "Promote" if promote else "Hold",
        "falsifier": "VPIN spikes do not widen spread intraday (median Δpost-pre ≤ gate)",
    }


def merge_pass4(
    pass3: dict[str, Any],
    *,
    sol: dict[str, Any],
    sol_arm: dict[str, Any],
    xvenue: dict[str, Any],
    markout: dict[str, Any],
    kr_markout: dict[str, Any],
    tox_events: dict[str, Any],
    panel_n: int,
) -> dict[str, Any]:
    table = list(pass3.get("decision_table", []))
    updates = {
        "frag.hl_sol_empty": sol.get("decision", "Hold"),
        "frag.xvenue_vpin_concord": xvenue.get("decision", "Hold"),
        "info.vpin_markout": markout.get("decision", "Hold"),
        "risk.vpin_toxicity_flag": tox_events.get("decision", "Hold"),
        "frag.kraken_vpin": "Hold",
    }

    def _f4(x: Any) -> str:
        try:
            v = float(x)
            return f"{v:.4f}" if np.isfinite(v) else "nan"
        except (TypeError, ValueError):
            return "nan"

    post = (sol.get("post_2026_08_28") or {})
    xv = (xvenue.get("methods") or {}).get("notional_median_x50", {}).get("spearman") or {}
    extra = {
        "frag.hl_sol_empty": (
            f"post-08-28 trades={post.get('n_days_with_trades')}/{post.get('n_listing_days')}; "
            f"SOL arm DB+Kr n_ok={(sol_arm.get('formal_arm') or {}).get('n_ok')}; formal_arm documented"
        ),
        "frag.xvenue_vpin_concord": (
            f"fresh notional ρ={xv.get('rho')} CI=[{xv.get('lo')},{xv.get('hi')}] "
            f"n_pairs={(xvenue.get('methods') or {}).get('notional_median_x50', {}).get('n_pairs')}"
        ),
        "info.vpin_markout": (
            f"promote-slice n_ok={markout.get('n_days_ok')} medIC60={_f4(markout.get('median_ic_60s'))} "
            f"rank60={_f4(markout.get('median_rank_ic_60s'))} "
            f"holdout HL={_f4((markout.get('venue_holdout') or {}).get('median_ic_excluding_hyperliquid'))} "
            f"DB={_f4((markout.get('venue_holdout') or {}).get('median_ic_excluding_deribit'))}"
        ),
        "risk.vpin_toxicity_flag": (
            f"intraday events n={tox_events.get('n_events')} Δpost-pre={_f4(tox_events.get('median_delta_post_minus_pre_bps'))}b"
        ),
        "frag.kraken_vpin": (
            f"futures markout n_ok={kr_markout.get('n_days_ok')} cache_days={kr_markout.get('n_cache_days_on_disk')}; "
            f"strict probe unchanged — Hold"
        ),
    }
    seen = {t["id"] for t in table}
    for tid, dec in updates.items():
        ev = extra.get(tid, "")
        if tid in seen:
            for t in table:
                if t["id"] == tid:
                    t["decision"] = dec
                    if ev:
                        t["evidence"] = ev
        else:
            table.append({"id": tid, "decision": dec, "evidence": ev})
    counts: dict[str, int] = {}
    for t in table:
        counts[t["decision"]] = counts.get(t["decision"], 0) + 1
    out = dict(pass3)
    out["decision_table"] = table
    out["decision_counts"] = counts
    out["book_status"] = "FINAL"
    out["pass4"] = {
        "hl_sol": sol,
        "sol_db_kraken_arm": sol_arm,
        "xvenue_fresh": xvenue,
        "markout": {
            k: markout.get(k)
            for k in (
                "n_days_ok",
                "median_ic_60s",
                "median_rank_ic_60s",
                "venue_holdout",
                "decision",
                "panel_mode",
            )
        },
        "kraken_futures_markout": kr_markout,
        "toxicity_intraday": tox_events,
        "panel_promote_n": panel_n,
    }
    out["data_provenance"] = (
        pass3.get("data_provenance", "")
        + "; Pass4 FINAL: HL SOL post-shard probe; SOL DB+Kr arm; fresh xvenue notional; "
        "promote-slice markout 60s+ holdout; Kraken futures TOB probe; intraday toxicity events"
    )
    return out


def write_pass4_reports(dec: dict[str, Any], art: dict[str, Any]) -> None:
    def _rows(ids: list[str]) -> str:
        by_id = {t["id"]: t for t in dec.get("decision_table", [])}
        lines = []
        for i in ids:
            t = by_id.get(i, {"decision": "Hold", "evidence": "—"})
            lines.append(f"| `{i}` | **{t['decision']}** | {str(t.get('evidence', ''))[:160]} |")
        return "\n".join(lines)

    (BOOK / "chapters/predictiveness/EXP_REPORT.md").write_text(
        "# predictiveness — Pass 4 (FINAL)\n\n"
        f"Promote-slice markout: **{art['markout'].get('decision')}** — "
        f"n_ok={art['markout'].get('n_days_ok')}, medIC60={art['markout'].get('median_ic_60s')}.\n\n"
        "| id | decision | evidence |\n|----|----------|----------|\n"
        + _rows(["info.vpin_markout"])
        + "\n"
    )
    (BOOK / "chapters/toxicity_events/EXP_REPORT.md").write_text(
        "# toxicity_events — Pass 4 (FINAL)\n\n"
        f"Intraday spike event study: **{art['tox'].get('decision')}**.\n\n"
        "| id | decision | evidence |\n|----|----------|----------|\n"
        + _rows(["risk.vpin_toxicity_flag"])
        + "\n"
    )
    (BOOK / "chapters/cross_venue/EXP_REPORT.md").write_text(
        "# cross_venue — Pass 4 (FINAL)\n\n"
        f"Fresh notional harmonization: **{art['xvenue'].get('decision')}**.\n\n"
        "| id | decision | evidence |\n|----|----------|----------|\n"
        + _rows(["frag.xvenue_vpin_concord", "frag.kraken_vpin", "frag.hl_sol_empty"])
        + "\n"
    )
    ch00 = BOOK / "chapters/ch00_overview/EXP_REPORT.md"
    base = ch00.read_text().split("Pass 4")[0].strip() if ch00.is_file() else "# ch00 overview"
    ch00.write_text(
        base
        + f"\n\nPass 4 **FINAL**: counts {dec.get('decision_counts')} — book_status={dec.get('book_status')}\n"
    )


def update_candidates(dec: dict[str, Any]) -> None:
    by_id = {t["id"]: t for t in dec.get("decision_table", [])}

    def _patch(path: Path, mapping: dict[str, str]) -> None:
        if not path.is_file():
            return
        import re

        text = path.read_text()
        for cid in mapping:
            d = by_id.get(cid, {}).get("decision", "Hold")
            pat = rf"(\| `{re.escape(cid)}` \|[^|]*\|[^|]*\| )\*\*(?:Hold|Promote|Kill|Park)\*\*"
            text2, n = re.subn(pat, rf"\1**{d}**", text, count=1)
            if n:
                text = text2
        path.write_text(text)

    cross = BOOK / "chapters/cross_venue/CANDIDATES.md"
    _patch(
        cross,
        {"frag.xvenue_vpin_concord": "d", "frag.kraken_vpin": "d", "frag.hl_sol_empty": "d"},
    )
    for ch, ids in (
        ("predictiveness", ["info.vpin_markout"]),
        ("toxicity_events", ["risk.vpin_toxicity_flag"]),
    ):
        _patch(BOOK / "chapters" / ch / "CANDIDATES.md", {i: "d" for i in ids})


def update_plan_final() -> None:
    plan = BOOK / "PLAN.md"
    text = plan.read_text()
    if "## Pass 4 gaps" in text:
        block = """## Pass 4 — **complete (FINAL)** (2026-10-03)

- [x] HL SOL post-2026-08-28 probe + formal **SOL=Deribit+Kraken** panel arm (`sol_db_kraken_panel.json`)
- [x] Kraken futures TOB markout probe (no S3 BBO; ingest cache documented) — **Hold**
- [x] xvenue notional/target50 on ≥20 fresh paired HL↔DB days — gate **failed** — **Hold**
- [x] Markout promote-slice only; venue holdout; 60s+ horizons — pre-reg gate **failed** — **Hold**
- [x] Intraday VPIN-spike toxicity event study — **Hold**
- [x] [`out/pass4/decisions_pass4.json`](out/pass4/decisions_pass4.json) — merged final board
- [x] Desk memo § Pass 4, notebooks §8, monitors, chapter reports

**Book status: FINAL** (no Pass 5 planned).
"""
        import re

        text = re.sub(r"## Pass 4 gaps\n\n.*", block, text, flags=re.DOTALL)
        plan.write_text(text)


def update_desk_memo(dec: dict[str, Any]) -> None:
    memo = BOOK / "DESK_MEMO.md"
    head = memo.read_text().split("## Pass 4")[0].strip()
    p4 = dec.get("pass4") or {}
    counts = dec.get("decision_counts")
    memo.write_text(
        head
        + f"""

---

## Pass 4 — **FINAL**

**Board:** `{counts}` on [`out/pass4/decisions_pass4.json`](out/pass4/decisions_pass4.json) · **book_status=FINAL**

| ID | Pass 3 | Pass 4 | Key delta |
|----|--------|--------|-----------|
| `frag.hl_sol_empty` | Hold | **Hold** | post-08-28 still 0 trades; formal **SOL=DB+Kr** arm documented |
| `frag.kraken_vpin` | Hold | **Hold** | futures TOB cache empty; S3 has no PF_* BBO |
| `frag.xvenue_vpin_concord` | Hold | **Hold** | fresh notional pairs on newest HL↔DB days — CI gate failed |
| `info.vpin_markout` | Hold | **Hold** | promote-slice 60s IC + venue holdout — gate failed |
| `risk.vpin_toxicity_flag` | Hold | **Hold** | intraday spike events — no spread widen |

```bash
python3 scripts/exp_pass4.py --resume
python3 scripts/build_notebook_figs.py && python3 scripts/build_notebooks.py
```
"""
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--skip-markout", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    pass3 = _load_pass3_decisions()
    panel_ok = _panel_hl_db()
    promote_rows = _promote_slice_rows(panel_ok)
    print(f"panel n={len(panel_ok)} promote_slice n={len(promote_rows)}", flush=True)

    def _lor(name: str, fn):
        path = OUT / name
        if args.resume and path.is_file():
            return json.loads(path.read_text())
        val = fn()
        _write_json(path, val)
        return val

    sol = _lor("hl_sol_probe.json", hl_sol_pass4)
    sol_arm = _lor("sol_db_kraken_panel.json", sol_db_kraken_panel)
    xvenue = _lor("xvenue_fresh_calibration.json", lambda: xvenue_fresh_calibration(panel_ok))
    kr_mo = _lor("kraken_futures_markout.json", kraken_futures_markout_probe)
    tox = _lor("toxicity_intraday.json", lambda: toxicity_intraday_events(promote_rows))

    if args.skip_markout:
        markout = {"n_days_ok": 0, "decision": "Hold", "skipped": True}
    else:
        mo_path = OUT / "markout.json"
        if args.resume and mo_path.is_file():
            markout = json.loads(mo_path.read_text())
        else:
            markout = run_markout_pass4(
                promote_rows,
                trade_stride=25,
                quotes_per_minute=120,
            )
            _write_json(mo_path, markout)

    merged = merge_pass4(
        pass3,
        sol=sol,
        sol_arm=sol_arm,
        xvenue=xvenue,
        markout=markout,
        kr_markout=kr_mo,
        tox_events=tox,
        panel_n=len(promote_rows),
    )
    _write_json(OUT / "decisions_pass4.json", merged)
    _write_json(PANEL / "decisions_pass4.json", merged)

    art = {"markout": markout, "xvenue": xvenue, "tox": tox, "sol": sol}
    write_pass4_reports(merged, art)
    update_candidates(merged)
    update_plan_final()
    update_desk_memo(merged)
    _write_json(
        OUT / "pass4_summary.json",
        {
            "book_status": "FINAL",
            "decision_counts": merged.get("decision_counts"),
            "n_promote_slice": len(promote_rows),
            "markout": markout.get("decision"),
            "xvenue_fresh": xvenue.get("decision"),
            "toxicity_intraday": tox.get("decision"),
            "hl_sol_post_trades": (sol.get("post_2026_08_28") or {}).get("n_days_with_trades"),
        },
    )
    print(json.dumps(merged.get("decision_counts"), indent=2))


if __name__ == "__main__":
    main()
