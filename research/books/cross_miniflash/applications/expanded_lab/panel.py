"""Expanded event panel — own cache; never overwrites sibling event_panel.

Extensions vs Phase-4 core (ETH/BTC · 2026-09-04…10 · 3 venues):
  - early days 2026-09-01…03 (ETH/BTC) when tape complete
  - SOL on Deribit + Kraken (HL flat-era SOL often empty — documented)
  - dense-TOB days 2026-09-29…30 (collector TOB) for book-realism cells

ClickHouse MCP banned.
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

LAB = Path(__file__).resolve().parent
APP = LAB.parent
BOOK = APP.parent
ROOT = BOOK.parents[2]
SCRIPTS_APP = APP / "scripts"
OUT = LAB / "out"
PANEL_DIR = OUT / "panel"
CORE_PANEL_DIR = APP / "out" / "event_panel"

for p in (str(SCRIPTS_APP), str(BOOK / "scripts"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from _common import (  # noqa: E402
    CORE_VENUES,
    DEFAULT_DAYS,
    DEFAULT_SYMBOLS,
    FRICTION_BPS,
    GATE_PRIMARY,
    Z_STAR,
    assign_ladder_tiers,
    detect_venue_day,
    flatten_events,
    jsonable,
    placebo_windows,
    rolling_gated_intensity,
    save_json,
    subsequent_abs_dp,
    tape_notional,
)
from _data import ensure_env, load_core_venues_day, load_day_trades  # noqa: E402
from ares_micro.vol.crash import volume_herfindahl  # noqa: E402
from ares_micro.flow.fei import fei  # noqa: E402

CORE_DAYS = list(DEFAULT_DAYS)
EXTEND_DAYS = ["2026-09-01", "2026-09-02", "2026-09-03"]
DENSE_TOB_DAYS = ["2026-09-29", "2026-09-30"]
SOL_VENUES = ("deribit", "kraken")  # HL SOL empty on flat-era slice


def _row_from_pack(
    day: str,
    sym: str,
    venue: str,
    rec: dict[str, Any],
    *,
    vols: dict[str, float],
    hv: dict[str, Any],
    fei_v: float,
    thin_venue: str | None,
) -> dict[str, Any]:
    if "error" in rec:
        return {
            "day": day,
            "symbol": sym,
            "venue": venue,
            "skip": rec.get("error"),
            "complete": False,
            "panel_slice": "extended",
        }
    det = detect_venue_day(rec["tape"])
    if det.get("skip"):
        return {
            "day": day,
            "symbol": sym,
            "venue": venue,
            "skip": det["skip"],
            "complete": bool(rec.get("completeness", {}).get("complete")),
            "n_trades": det.get("n_trades", 0),
            "panel_slice": "extended",
        }
    s10 = det["ssm_10bps"]
    n_ev = int(s10["n_events"])
    intens = rolling_gated_intensity(s10["ts_start"], window_s=60.0)
    sub_dp = subsequent_abs_dp(det["ts"], det["px"], s10["end_i"], horizon_s=30.0)
    nx = det["nanex"]
    from _common import _ssm_has_nanex_overlap, ladder_tier  # local helper

    ssm_has_nanex = _ssm_has_nanex_overlap(s10, nx, det["ts"], slack_s=0.5)
    tiers = [
        ladder_tier(
            float(z),
            intensity=int(intens[i]),
            nanex_overlap=bool(ssm_has_nanex[i]),
            dp_pct=float(s10["dp_pct"][i]),
        )
        for i, z in enumerate(np.asarray(s10["z_peak"], dtype=np.float64))
    ]
    row = {
        "day": day,
        "symbol": sym,
        "venue": venue,
        "complete": bool(rec.get("completeness", {}).get("complete")),
        "n_trades": int(det["n_trades"]),
        "vol_usd": float(vols.get(venue, 0.0)),
        "vol_shares": hv["shares"],
        "H_v": hv["H_v"],
        "FEI": fei_v,
        "thin_venue": thin_venue,
        "thin_excess": None,
        "ssm_raw_n": int(det["ssm_raw"]["n_events"]),
        "ssm_10_n": n_ev,
        "ssm_5_n": int(det["ssm_5bps"]["n_events"]),
        "nanex_n": int(nx["n_events"]),
        "nanex_nested_n": int(det["nanex_nested_mask"].sum()),
        "nanex_ssm_precision": det["nanex_ssm_nest"].get("precision_a"),
        "sigma_m_median": det.get("sigma_m_median"),
        "panel_slice": "extended",
        "events": {
            "ts_start": s10["ts_start"].tolist(),
            "ts_end": s10["ts_end"].tolist(),
            "dp_pct": s10["dp_pct"].tolist(),
            "i_c": s10["i_c"].tolist(),
            "dt_s": s10["dt_s"].tolist(),
            "direction": s10["direction"].tolist(),
            "z_peak": s10["z_peak"].tolist(),
            "intensity_60s": intens.tolist(),
            "tier": tiers,
            "recovery": det["recovery"].tolist(),
            "recovery_label": det["recovery_class"]["labels"].tolist(),
            "mo_1s": det["markout_1s"].tolist(),
            "mo_5s": det["markout_5s"].tolist(),
            "sub_dp_30s": sub_dp.tolist(),
            "nanex_overlap": ssm_has_nanex.tolist(),
        },
        "nanex_events": {
            "ts_start": nx["ts_start"].tolist(),
            "ts_end": nx["ts_end"].tolist(),
            "dp_pct": nx["dp_pct"].tolist(),
            "nested": det["nanex_nested_mask"].tolist(),
        },
        "placebo": placebo_windows(
            det["ts"], det["px"], max(n_ev, 5), seed=hash((day, sym, venue)) % (2**31)
        ),
        "tape_summary": {
            "n": int(det["ts"].size),
            "t0": int(det["ts"][0]) if det["ts"].size else None,
            "t1": int(det["ts"][-1]) if det["ts"].size else None,
            "px0": float(det["px"][0]) if det["px"].size else None,
            "px1": float(det["px"][-1]) if det["px"].size else None,
        },
    }
    row["placebo"] = {
        "n": row["placebo"]["n"],
        "dp_pct": row["placebo"]["dp_pct"].tolist(),
        "mo_5s": row["placebo"]["mo_5s"].tolist(),
        "sub_dp": row["placebo"]["sub_dp"].tolist(),
    }
    return row


def _process_day_symbol(
    day: str,
    sym: str,
    venues: tuple[str, ...],
    *,
    quiet: bool = True,
) -> list[dict[str, Any]]:
    ensure_env()
    pack = load_core_venues_day(sym, day, venues=venues, quiet=quiet)
    vols: dict[str, float] = {}
    for v, rec in pack["venues"].items():
        if "error" in rec or not rec.get("completeness", {}).get("complete"):
            continue
        vols[v] = tape_notional(rec["tape"], v)
    hv = volume_herfindahl(vols, keys=list(venues))
    fei_v = (
        float(fei([hv["shares"].get(v, 0.0) for v in venues], n_pools=len(venues)))
        if hv["complete"]
        else float("nan")
    )
    thin_venue = min(hv["shares"], key=hv["shares"].get) if hv["complete"] and hv["shares"] else None
    rows = []
    for v, rec in pack["venues"].items():
        rows.append(
            _row_from_pack(
                day, sym, v, rec, vols=vols, hv=hv, fei_v=fei_v, thin_venue=thin_venue
            )
        )
    # crash shares within this day×symbol
    cell = [r for r in rows if "events" in r]
    if cell:
        counts = {r["venue"]: int(r["ssm_10_n"]) for r in cell}
        tot = sum(counts.values()) or 1
        crash_shares = {v: counts.get(v, 0) / tot for v in venues}
        vol_shares = cell[0].get("vol_shares") or {}
        thin = cell[0].get("thin_venue")
        for r in cell:
            r["crash_shares"] = crash_shares
            r["crash_share"] = crash_shares.get(r["venue"], float("nan"))
            vs = float(vol_shares.get(r["venue"], float("nan")))
            cs = float(crash_shares.get(r["venue"], float("nan")))
            r["excess"] = cs - vs if np.isfinite(cs) and np.isfinite(vs) else float("nan")
            if thin and r["venue"] == thin:
                r["thin_excess"] = r["excess"]
    return rows


def _load_core_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta_path = CORE_PANEL_DIR / "panel_meta.json"
    rows_path = CORE_PANEL_DIR / "panel_rows.json"
    if not meta_path.exists() or not rows_path.exists():
        raise FileNotFoundError(
            f"Core panel missing at {CORE_PANEL_DIR} — run applications/scripts/run_all.py first"
        )
    meta = json.loads(meta_path.read_text())
    rows = json.loads(rows_path.read_text())
    for r in rows:
        r.setdefault("panel_slice", "core")
    return rows, meta


def build_expanded_panel(
    *,
    force: bool = False,
    workers: int = 8,
    include_extend_days: bool = True,
    include_sol: bool = True,
    include_dense_tob: bool = False,  # Sep29/30 tapes incomplete; book_realism probes separately
    quiet: bool = True,
) -> dict[str, Any]:
    """Core panel + optional extensions. Cached under expanded_lab/out/panel/."""
    PANEL_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = PANEL_DIR / "panel_meta.json"
    rows_path = PANEL_DIR / "panel_rows.json"
    cfg = {
        "include_extend_days": include_extend_days,
        "include_sol": include_sol,
        "include_dense_tob": include_dense_tob,
        "core_days": CORE_DAYS,
        "extend_days": EXTEND_DAYS if include_extend_days else [],
        "dense_tob_days": DENSE_TOB_DAYS if include_dense_tob else [],
        "sol_venues": list(SOL_VENUES) if include_sol else [],
    }
    if not force and meta_path.exists() and rows_path.exists():
        meta = json.loads(meta_path.read_text())
        if meta.get("expand_cfg") == cfg:
            rows = json.loads(rows_path.read_text())
            return {"meta": meta, "rows": rows, "cached": True}

    core_rows, core_meta = _load_core_rows()
    rows: list[dict[str, Any]] = list(core_rows)
    jobs: list[tuple[str, str, tuple[str, ...], str]] = []

    if include_extend_days:
        for day in EXTEND_DAYS:
            for sym in DEFAULT_SYMBOLS:
                jobs.append((day, sym, CORE_VENUES, "extend"))
    if include_sol:
        for day in CORE_DAYS:
            jobs.append((day, "SOL", SOL_VENUES, "sol"))
    if include_dense_tob:
        for day in DENSE_TOB_DAYS:
            for sym in ["ETH", "BTC", "SOL"]:
                # dense collector TOB is HL-heavy; still attempt 3-venue trades
                jobs.append((day, sym, CORE_VENUES, "dense_tob"))

    new_rows: list[dict[str, Any]] = []
    if jobs:
        # sequential is safer for warehouse; parallel optional
        if workers <= 1:
            for day, sym, venues, tag in jobs:
                try:
                    rs = _process_day_symbol(day, sym, venues, quiet=quiet)
                    for r in rs:
                        r["panel_slice"] = tag
                    new_rows.extend(rs)
                    print(f"[panel] {tag} {day} {sym} venues={venues} rows={len(rs)}", flush=True)
                except Exception as exc:  # noqa: BLE001
                    print(f"[panel] FAIL {tag} {day} {sym}: {exc}", flush=True)
                    for v in venues:
                        new_rows.append(
                            {
                                "day": day,
                                "symbol": sym,
                                "venue": v,
                                "skip": f"{type(exc).__name__}: {exc}",
                                "complete": False,
                                "panel_slice": tag,
                            }
                        )
        else:
            with ProcessPoolExecutor(max_workers=workers) as ex:
                futs = {
                    ex.submit(_process_day_symbol, day, sym, venues, quiet=quiet): (day, sym, venues, tag)
                    for day, sym, venues, tag in jobs
                }
                for fut in as_completed(futs):
                    day, sym, venues, tag = futs[fut]
                    try:
                        rs = fut.result()
                        for r in rs:
                            r["panel_slice"] = tag
                        new_rows.extend(rs)
                        print(f"[panel] {tag} {day} {sym} rows={len(rs)}", flush=True)
                    except Exception as exc:  # noqa: BLE001
                        print(f"[panel] FAIL {tag} {day} {sym}: {exc}", flush=True)
                        for v in venues:
                            new_rows.append(
                                {
                                    "day": day,
                                    "symbol": sym,
                                    "venue": v,
                                    "skip": f"{type(exc).__name__}: {exc}",
                                    "complete": False,
                                    "panel_slice": tag,
                                }
                            )

    rows.extend(new_rows)
    # de-dupe by (day,symbol,venue) preferring later slices only if core missing
    seen: dict[tuple, dict] = {}
    for r in rows:
        key = (r.get("day"), r.get("symbol"), r.get("venue"))
        if key not in seen:
            seen[key] = r
        else:
            # keep core if present; else keep first complete
            cur = seen[key]
            if cur.get("panel_slice") == "core":
                continue
            if r.get("panel_slice") == "core":
                seen[key] = r
            elif r.get("complete") and not cur.get("complete"):
                seen[key] = r
    rows = list(seen.values())

    days_all = sorted({r["day"] for r in rows if r.get("day")})
    symbols_all = sorted({r["symbol"] for r in rows if r.get("symbol")})
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days": days_all,
        "symbols": symbols_all,
        "venues": list(CORE_VENUES),
        "gate": GATE_PRIMARY,
        "z_star": Z_STAR,
        "friction_bps": FRICTION_BPS,
        "n_rows": len(rows),
        "n_core_rows": len(core_rows),
        "n_extended_rows": len(new_rows),
        "core_meta": {k: core_meta.get(k) for k in ("days", "symbols", "n_rows", "generated_at")},
        "expand_cfg": cfg,
        "notes": [
            "Own cache under expanded_lab/out/panel — sibling event_panel untouched",
            "HL SOL often empty on flat-era (≤2026-09-10); SOL = Deribit+Kraken",
            "Dense TOB days use collector TOB when present (HL)",
        ],
    }
    save_json(meta_path, meta)
    save_json(rows_path, rows)
    return {"meta": meta, "rows": rows, "cached": False}


def panel_event_lists(panel: dict[str, Any]) -> dict[str, Any]:
    """Split flattened events by slice for robustness compares."""
    rows = panel["rows"]
    all_ev = flatten_events(rows)
    breaks = assign_ladder_tiers(all_ev)
    row_slice = {(r["day"], r["symbol"], r["venue"]): r.get("panel_slice", "core") for r in rows}
    for e in all_ev:
        e["panel_slice"] = row_slice.get((e["day"], e["symbol"], e["venue"]), "core")
    by_slice: dict[str, Any] = {
        "all": all_ev,
        "core": [e for e in all_ev if e["day"] in CORE_DAYS and e["symbol"] in DEFAULT_SYMBOLS],
        "core_plus_extend": [
            e
            for e in all_ev
            if e["symbol"] in DEFAULT_SYMBOLS and e["day"] in (CORE_DAYS + EXTEND_DAYS)
        ],
        "sol": [e for e in all_ev if e["symbol"] == "SOL"],
        "extend": [e for e in all_ev if e.get("panel_slice") == "extend"],
        "dense_tob": [e for e in all_ev if e.get("panel_slice") == "dense_tob"],
        "ladder_breaks": breaks,
    }
    return by_slice
