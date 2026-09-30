#!/usr/bin/env python3
"""Evidence widen + continuous V_t Pass-2 + trade-idea inputs for v_shapes.

A. Expand ETH+BTC UTC-day MinV panels (HL+Deribit+Kraken) as far as warehouse
   completeness allows; document max_files / completeness.
B. Join Deribit warehouse L2 TOB (and collector when present) around MinV.
C. Deeper continuous V_t / T± lead-lag vs forward mid returns on sig days.
D. Write trade-idea evidence blob for DESK_MEMO / notebooks (desk-honest labels).

ClickHouse MCP banned. No commit.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(Path("/home/dev/lab/lab-n2070/warehouse/src")))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path("/home/dev/srv/ares-startarb") / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import (  # noqa: E402
    CORE_VENUES,
    collector_tob_days,
    ensure_env,
    load_day_trades,
    load_venue_tob,
)
from research.lib.vstat import (  # noqa: E402
    bootstrap_minv_ci,
    grid_1s,
    min_v,
    returns_from_log_px,
    v_path,
)

# Import panel helpers
from exp_panel_case import (  # noqa: E402
    _minv_day,
    pick_stress_day,
    write_daily_reports,
    write_event_case,
)
from exp_liq_xvenue import liq_around, write_reports, xvenue  # noqa: E402

OUT = BOOK / "out"
HN_MIN = (1, 5, 30)

# Existing + gap days from day_completeness_probe_v2 (HL+DB usable)
ETH_BASE = [
    "2026-09-04",
    "2026-09-05",
    "2026-09-06",
    "2026-09-07",
    "2026-09-08",
    "2026-09-09",
    "2026-09-10",
    "2026-09-15",
    "2026-09-18",
    "2026-09-25",
    "2026-09-26",
    "2026-09-27",
    "2026-09-30",
]
ETH_GAP = [
    "2026-09-14",
    "2026-09-16",
    "2026-09-17",
    "2026-09-19",
    "2026-09-20",
    "2026-09-21",
    "2026-09-22",
]
BTC_DAYS = list(ETH_BASE)  # all probe-usable HL+DB


def _mean_ci(vals: list[float]) -> tuple[float, float, float, int]:
    a = np.asarray(vals, dtype=float)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return float("nan"), float("nan"), float("nan"), 0
    m = float(np.mean(a))
    if a.size < 2:
        return m, float("nan"), float("nan"), int(a.size)
    se = float(np.std(a, ddof=1) / math.sqrt(a.size))
    return m, m - 1.96 * se, m + 1.96 * se, int(a.size)


def merge_panel_rows(existing: dict | None, new_rows: list[dict], symbol: str, days: list[str]) -> dict:
    """Merge new rows into existing panel; replace (venue,day,hn) keys."""
    by_key: dict[tuple, dict] = {}
    for r in (existing or {}).get("rows") or []:
        if not isinstance(r, dict):
            continue
        key = (r.get("venue"), r.get("day"), r.get("hn_min"))
        by_key[key] = r
    for r in new_rows:
        key = (r.get("venue"), r.get("day"), r.get("hn_min"))
        by_key[key] = r
    rows = sorted(by_key.values(), key=lambda r: (r.get("day") or "", r.get("venue") or "", r.get("hn_min") or 0))
    all_days = sorted({r.get("day") for r in rows if r.get("day")} | set(days))
    return {"symbol": symbol, "days": all_days, "rows": rows, "max_files_note": "warehouse max_files=24"}


def build_panel_incremental(
    symbol: str,
    days: list[str],
    *,
    max_files: int,
    fast: bool,
    existing: dict | None,
    only_missing: bool = True,
) -> dict:
    ensure_env()
    n_grid = 41 if fast else 51
    n_boot = 20 if fast else 40
    have = set()
    if only_missing and existing:
        for r in existing.get("rows") or []:
            if r.get("ok") and r.get("venue") and r.get("day") and r.get("hn_min") is not None:
                have.add((r["venue"], r["day"], int(r["hn_min"])))
    new_rows: list[dict] = []
    for venue in CORE_VENUES:
        for day in days:
            need_any = any((venue, day, hm) not in have for hm in HN_MIN) if only_missing else True
            if not need_any:
                continue
            try:
                rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
            except Exception as exc:  # noqa: BLE001
                for hm in HN_MIN:
                    new_rows.append({"venue": venue, "day": day, "hn_min": hm, "error": str(exc), "ok": False})
                print(f"  LOAD_ERR {symbol} {venue} {day}: {exc}", flush=True)
                continue
            for hm in HN_MIN:
                if only_missing and (venue, day, hm) in have:
                    continue
                try:
                    out = _minv_day(rec["tape"], float(hm * 60), n_grid=n_grid, n_boot=n_boot)
                except Exception as exc:  # noqa: BLE001
                    out = {"ok": False, "error": str(exc)}
                row = {
                    "venue": venue,
                    "day": day,
                    "hn_min": hm,
                    "complete": rec["completeness"].get("complete"),
                    "n_trades": rec["completeness"].get("n"),
                    **out,
                }
                new_rows.append(row)
                print(
                    f"  {symbol} {venue} {day} hn={hm}: ok={row.get('ok')} "
                    f"minv={row.get('min_v')} sig5={row.get('sig_5')} complete={row.get('complete')}",
                    flush=True,
                )
    panel = merge_panel_rows(existing, new_rows, symbol, days)
    OUT_D = OUT / "daily_minv"
    OUT_D.mkdir(parents=True, exist_ok=True)
    (OUT_D / f"daily_minv_{symbol.lower()}.json").write_text(json.dumps(panel, indent=2, default=str))
    return panel


def continuous_v_deeper(symbol: str, panel: dict, *, max_files: int, fast: bool) -> dict:
    """Lead-lag of continuous V_t / T± vs forward mid returns on sig@5% complete days."""
    ensure_env()
    sig = [
        r
        for r in panel.get("rows") or []
        if r.get("ok")
        and r.get("sig_5")
        and r.get("complete")
        and r.get("hn_min") == 5
        and np.isfinite(r.get("min_v", np.nan))
    ]
    # de-dupe venue/day
    seen = set()
    events = []
    for r in sig:
        key = (r["venue"], r["day"])
        if key in seen:
            continue
        seen.add(key)
        events.append(r)
    n_grid = 31 if fast else 51
    dt_s = 5.0
    hn_s = 300.0
    rows = []
    for ev in events:
        venue, day = ev["venue"], ev["day"]
        try:
            rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
        except Exception as exc:  # noqa: BLE001
            rows.append({"venue": venue, "day": day, "error": str(exc)})
            continue
        g = grid_1s(rec["tape"]["ts"], rec["tape"]["px"], dt_s=dt_s)
        if int(g["n_filled"]) < 80:
            rows.append({"venue": venue, "day": day, "ok": False, "reason": "short_grid"})
            continue
        t, r = returns_from_log_px(g["log_px"], g["ts_ns"], time_unit_s=1.0)
        t0, t1 = float(t[0] + hn_s), float(t[-1] - hn_s)
        if t1 <= t0:
            rows.append({"venue": venue, "day": day, "ok": False, "reason": "hn_too_wide"})
            continue
        taus = np.linspace(t0, t1, n_grid)
        path = v_path(t, r, taus, hn_s)
        V, Tm, Tp = path["V"], path["T_minus"], path["T_plus"]
        ti = np.clip(np.searchsorted(t, path["tau"]), 0, r.size - 2)
        leadlag: dict[str, float] = {}
        for k_steps, label in ((1, "5s"), (6, "30s"), (12, "60s"), (60, "300s")):
            fut_r = np.asarray([np.sum(r[i : min(r.size, i + k_steps)]) for i in ti], dtype=float)
            fut_r2 = fut_r * fut_r
            for name, feat in (("V", V), ("Tm", Tm), ("Tp", Tp)):
                m = np.isfinite(feat) & np.isfinite(fut_r)
                if int(m.sum()) < 15:
                    continue
                leadlag[f"corr_{name}_fwdret_{label}"] = float(np.corrcoef(feat[m], fut_r[m])[0, 1])
                leadlag[f"corr_{name}_fwdr2_{label}"] = float(np.corrcoef(feat[m], fut_r2[m])[0, 1])
        # post-trough from path argmin
        mv = min_v(t, r, taus, hn_s)
        post = {}
        if np.isfinite(mv["tau_star"]):
            i0 = int(np.searchsorted(t, mv["tau_star"]))
            for horizon in (60, 300, 1800):
                step = max(1, int(horizon / dt_s))
                i1 = min(r.size, i0 + step)
                if i1 > i0:
                    post[f"ret_{horizon}s"] = float(np.sum(r[i0:i1]))
        rows.append(
            {
                "venue": venue,
                "day": day,
                "ok": True,
                "min_v": mv["min_v"],
                "shape": mv["shape"],
                "tau_star_s": mv["tau_star"],
                "leadlag": leadlag,
                "post_trough": post,
                "panel_sig5": True,
            }
        )
        print(f"  contV {symbol} {venue} {day}: n_ll={len(leadlag)} post={post}", flush=True)

    # aggregate CIs
    agg: dict[str, dict] = {}
    for key in sorted({k for r in rows for k in (r.get("leadlag") or {})}):
        vals = [float(r["leadlag"][key]) for r in rows if r.get("ok") and key in (r.get("leadlag") or {})]
        m, lo, hi, n = _mean_ci(vals)
        agg[key] = {"mean": m, "lo": lo, "hi": hi, "n": n, "excludes_0": bool(np.isfinite(lo) and np.isfinite(hi) and (hi < 0 or lo > 0) and n >= 6)}
    post300 = [float(r["post_trough"]["ret_300s"]) for r in rows if r.get("ok") and isinstance(r.get("post_trough"), dict) and np.isfinite(r["post_trough"].get("ret_300s", np.nan))]
    pm, plo, phi, pn = _mean_ci(post300)
    out = {
        "symbol": symbol,
        "n_events": len(rows),
        "n_ok": sum(1 for r in rows if r.get("ok")),
        "rows": rows,
        "leadlag_agg": agg,
        "post300": {"mean": pm, "lo": plo, "hi": phi, "n": pn, "excludes_0": bool(np.isfinite(plo) and np.isfinite(phi) and (phi < 0 or plo > 0) and pn >= 6)},
        "promote_hint_v_path": any(v.get("excludes_0") and abs(v.get("mean", 0)) >= 0.05 for k, v in agg.items() if "fwdret" in k or "fwdr2" in k),
    }
    out_dir = OUT / "v_statistic"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"continuous_v_{symbol.lower()}.json").write_text(json.dumps(out, indent=2, default=str))
    return out


def write_widen_plan(eth_days: list[str], btc_days: list[str], tob_note: dict) -> None:
    plan = {
        "eth_days": eth_days,
        "eth_gap_added": ETH_GAP,
        "btc_days": btc_days,
        "max_files": 24,
        "tob_collector_days": collector_tob_days(),
        "tob_note": tob_note,
        "note": (
            "Kraken trade tape empty most Sep days (listings exist). "
            "HL+Deribit multi-week usable with max_files=24. "
            "Warehouse Deribit L2→TOB multi-day; Kraken warehouse L2 empty; "
            "collector TOB only 2026-09-29/30."
        ),
    }
    (OUT / "widen_day_plan.json").write_text(json.dumps(plan, indent=2))


def trade_ideas_blob(rollup_path: Path, cont_eth: dict, cont_btc: dict) -> dict:
    """Desk-honest trade idea sketches mapped to gates (labels only; no alpha cosplay)."""
    rollup = json.loads(rollup_path.read_text()) if rollup_path.exists() else {}
    promotes = {p["id"] for p in rollup.get("promotes") or []}
    holds = {h["id"]: h.get("why", "") for h in rollup.get("holds") or []}
    kills = {k["id"] for k in rollup.get("kills") or []}

    def gate_of(cid: str) -> str:
        if cid in promotes:
            return "Promote"
        if cid in kills:
            return "Kill"
        return "Hold"

    ideas = [
        {
            "id": "ti.risk_monitor_minv_breach",
            "label": "Monitor",
            "title": "MinV breach → widen quotes / cut size / pause aggressive takes",
            "sketch": (
                "When UTC-day MinV < EGARCH 5% band at hn∈{1,5,30}m on home venue, "
                "widen quotes, cut inventory size, and pause aggressive takes for one hn window. "
                "Uses Promote EGARCH bands + taxonomy; panel status gates how hard you size the cut."
            ),
            "depends_on": ["risk.egarch_minv_bands", "risk.v_vs_jump_taxonomy", "risk.daily_minv_panel"],
            "gate_status": {cid: gate_of(cid) for cid in ("risk.egarch_minv_bands", "risk.v_vs_jump_taxonomy", "risk.daily_minv_panel")},
            "tradable_size": "N/A — Monitor only (Promote bands exist; panel may still be Hold)",
            "falsifier": "time-split / hn fragility on daily_minv_panel; EGARCH size/power Models 0–3",
        },
        {
            "id": "ti.exec_throttle_avoid_chase",
            "label": "Exec throttle",
            "title": "Avoid chasing through MinV trough; delay POV until recovery",
            "sketch": (
                "If live V_t / MinV path approaches trough (T−≪0 then T+ rising), "
                "delay POV / reduce participation until mid recovers past τ*+hn/2. "
                "Throttle — not alpha. Requires continuous path info Hold/Promote honesty."
            ),
            "depends_on": ["info.v_path_continuous", "risk.egarch_minv_bands"],
            "gate_status": {cid: gate_of(cid) for cid in ("info.v_path_continuous", "risk.egarch_minv_bands")},
            "tradable_size": "Paper-only throttle params until info.v_path_continuous Promotes",
            "falsifier": cont_eth.get("leadlag_agg") and "lead-lag CI vs fwd mid returns on sig days" or "thin continuous V sample",
        },
        {
            "id": "ti.mean_reversion_fade",
            "label": "Tradable alpha" if gate_of("info.post_trough_ret") == "Promote" else "Monitor",
            "title": "Post-trough mean-reversion fade",
            "sketch": (
                "Fade post-τ* only if post-trough return CIs clear 0 after time-split/bootstrap. "
                "Else paper-only Hold — no sized alpha."
            ),
            "depends_on": ["info.post_trough_ret"],
            "gate_status": {"info.post_trough_ret": gate_of("info.post_trough_ret")},
            "tradable_size": (
                "Sized only if Promote"
                if gate_of("info.post_trough_ret") == "Promote"
                else "Paper-only / not sized — CI does not clear 0 or n too small"
            ),
            "falsifier": f"ETH post300={cont_eth.get('post300')}; BTC post300={cont_btc.get('post300')}",
        },
        {
            "id": "ti.xvenue_sor_caution",
            "label": "Exec throttle",
            "title": "SOR caution on thin venue during V",
            "sketch": (
                "If HL↔Deribit↔Kraken MinV concordance improves (pairwise |Δτ*|≤hn among sig), "
                "cut child size on thin venue during V windows. Else Hold — no SOR rule from discordant noise."
            ),
            "depends_on": ["risk.xvenue_minv_concord"],
            "gate_status": {"risk.xvenue_minv_concord": gate_of("risk.xvenue_minv_concord")},
            "tradable_size": "Not sized — Hold until concordant pairs exist",
            "falsifier": "pairwise concordance within hn on multi-day tri-venue sample",
        },
        {
            "id": "ti.liq_spread_widen",
            "label": "Monitor",
            "title": "Spread/depth deterioration around MinV as secondary risk flag",
            "sketch": (
                "Join TOB spread pre/post τ*; if spread widens materially into trough, reinforce quote widen. "
                "Hard ceiling: Kraken warehouse L2 empty; collector only 0929-30; Deribit warehouse L2 usable."
            ),
            "depends_on": ["liq.spread_around_minv"],
            "gate_status": {"liq.spread_around_minv": gate_of("liq.spread_around_minv")},
            "tradable_size": "N/A — Monitor; no fake TOB",
            "falsifier": "multi-day TOB coverage ≥2 days with usable spread pre/post",
        },
    ]
    # Explicit Kill reminders — no trade ideas
    kill_notes = [
        {"id": kid, "note": "No trade idea — Kill object. Do not alpha-cosplay."}
        for kid in sorted(kills)
    ]
    blob = {
        "ideas": ideas,
        "kill_no_alpha": kill_notes,
        "promotes": sorted(promotes),
        "holds": holds,
        "kills": sorted(kills),
    }
    (OUT / "trade_ideas.json").write_text(json.dumps(blob, indent=2, default=str))
    return blob


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-files", type=int, default=24)
    ap.add_argument("--fast", action="store_true", default=True)
    ap.add_argument("--no-fast", action="store_true")
    ap.add_argument("--skip-panel", action="store_true")
    ap.add_argument("--skip-liq", action="store_true")
    ap.add_argument("--skip-cont", action="store_true")
    ap.add_argument("--eth-only-gap", action="store_true", help="Only compute ETH gap days (merge into existing)")
    args = ap.parse_args()
    fast = not args.no_fast
    ensure_env()
    OUT.mkdir(parents=True, exist_ok=True)

    eth_days = sorted(set(ETH_BASE + ETH_GAP))
    btc_days = list(BTC_DAYS)
    tob_note = {
        "collector_days": collector_tob_days(),
        "warehouse_deribit": "l2_snapshot_level multi-day usable (~2k quotes/day when present)",
        "warehouse_kraken": "empty — hard ceiling",
        "warehouse_hl": "sparse snap/L2; refuse trade_synth for liq Promotes",
    }
    write_widen_plan(eth_days, btc_days, tob_note)

    panels = {}
    if not args.skip_panel:
        for symbol, days in (("ETH", eth_days if not args.eth_only_gap else ETH_GAP), ("BTC", btc_days)):
            path = OUT / "daily_minv" / f"daily_minv_{symbol.lower()}.json"
            existing = json.loads(path.read_text()) if path.exists() else None
            print(f"\n=== PANEL {symbol} days={days} (incremental) ===", flush=True)
            # For ETH gap-only, still merge onto full day list
            full_days = eth_days if symbol == "ETH" else btc_days
            panel = build_panel_incremental(
                symbol,
                days,
                max_files=args.max_files,
                fast=fast,
                existing=existing,
                only_missing=True,
            )
            # ensure days list is full target
            panel["days"] = full_days if symbol == "ETH" else btc_days
            path.write_text(json.dumps(panel, indent=2, default=str))
            write_daily_reports(panel)
            stress = pick_stress_day(panel)
            write_event_case(symbol, stress, panel)
            panels[symbol] = panel
            print(f"  {symbol} rows={len(panel['rows'])} stress={stress and {k: stress.get(k) for k in ('venue','day','min_v','sig_5')}}", flush=True)
    else:
        for symbol in ("ETH", "BTC"):
            path = OUT / "daily_minv" / f"daily_minv_{symbol.lower()}.json"
            if path.exists():
                panels[symbol] = json.loads(path.read_text())

    cont = {}
    if not args.skip_cont:
        for symbol in ("ETH", "BTC"):
            if symbol not in panels:
                continue
            print(f"\n=== CONTINUOUS V_t {symbol} ===", flush=True)
            cont[symbol] = continuous_v_deeper(symbol, panels[symbol], max_files=args.max_files, fast=fast)

    if not args.skip_liq:
        # Prefer days with TOB hope: Deribit warehouse days + collector days
        liq_days = sorted(
            set(
                [
                    "2026-09-08",
                    "2026-09-15",
                    "2026-09-20",
                    "2026-09-25",
                    "2026-09-27",
                    "2026-09-30",
                ]
                + collector_tob_days()
            )
        )
        for symbol in ("ETH", "BTC"):
            print(f"\n=== LIQ+XVENUE {symbol} days={liq_days} ===", flush=True)
            liq_rows = []
            xrows = []
            for day in liq_days:
                xrows.append(xvenue(symbol, day, max_files=args.max_files))
                for venue in CORE_VENUES:
                    try:
                        liq_rows.append(liq_around(symbol, day, venue, max_files=args.max_files))
                    except Exception as exc:  # noqa: BLE001
                        liq_rows.append({"venue": venue, "day": day, "error": str(exc)})
                print(f"  done {symbol} {day}", flush=True)
            write_reports(liq_rows, xrows, symbol)

    # Flatten continuous leadlag into v_statistic panel for hardening scanner
    for symbol, c in cont.items():
        vpath = OUT / "v_statistic" / f"panel_{symbol.lower()}.json"
        panel_v = json.loads(vpath.read_text()) if vpath.exists() else {"symbol": symbol, "venues": {}, "rows": []}
        # add flat rows with leadlag for hardening
        flat = []
        for r in c.get("rows") or []:
            if not r.get("ok"):
                continue
            flat.append(
                {
                    "venue": r["venue"],
                    "day": r["day"],
                    "hn_min": 5,
                    "ok": True,
                    "leadlag": r.get("leadlag") or {},
                    "min_v": r.get("min_v"),
                }
            )
        panel_v["rows"] = flat
        panel_v["continuous_meta"] = {
            "post300": c.get("post300"),
            "promote_hint": c.get("promote_hint_v_path"),
            "leadlag_agg": c.get("leadlag_agg"),
        }
        vpath.parent.mkdir(parents=True, exist_ok=True)
        vpath.write_text(json.dumps(panel_v, indent=2, default=str))

    summary = {
        "eth_days": eth_days,
        "btc_days": btc_days,
        "n_eth_rows": len((panels.get("ETH") or {}).get("rows") or []),
        "n_btc_rows": len((panels.get("BTC") or {}).get("rows") or []),
        "cont_eth_events": (cont.get("ETH") or {}).get("n_ok"),
        "cont_btc_events": (cont.get("BTC") or {}).get("n_ok"),
        "tob_note": tob_note,
    }
    (OUT / "widen_evidence_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
