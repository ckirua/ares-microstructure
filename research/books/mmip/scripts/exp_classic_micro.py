from __future__ import annotations
#!/usr/bin/env python3
"""Classic microstructure package: markout, spreads, session effects, resilience.

Implements under-covered book themes with real HL tape + collector/warehouse mids.
No ClickHouse MCP. Paper only.
"""

import os

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

BOOK_ROOT = Path(__file__).resolve().parents[1]
ROOT = BOOK_ROOT.parents[2]  # repo root (mmip → books → research → repo)
STARTARB = Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb'))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(STARTARB / "src"))

from research.lib import (  # noqa: E402
    adverse_selection_table,
    bootstrap_ci,
    effective_spread_bps,
    mid_price,
    quoted_spread_bps,
    realized_spread_bps,
    roll_implied_spread,
    time_split_mask,
    tob_resilience,
    trade_markouts,
)

OUT_DIR = BOOK_ROOT / "out" / "classic_micro"
DEFAULT_TOB = STARTARB / "results" / "xarb_md" / "tob"


def _ensure_env() -> None:
    from startarb.env import ensure_env

    ensure_env()


def load_trades(symbol: str, days: list[str], max_files: int):
    from startarb.data.trades import load_trade_tape

    return load_trade_tape("hyperliquid", symbol, days=days, max_files=max_files)


def load_mids_from_tob(symbol: str, tob_root: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return ts, mid, depth, bid, ask for HL from latest collector day(s)."""
    import pandas as pd
    import pyarrow.parquet as pq

    day_dirs = sorted(p for p in tob_root.iterdir() if p.is_dir())
    if not day_dirs:
        raise FileNotFoundError(tob_root)
    frames = []
    for d in day_dirs[-2:]:
        for f in sorted(d.glob("tob_*.parquet")):
            t = pq.read_table(f, columns=["ts", "venue", "symbol", "bid", "ask", "bid_sz", "ask_sz"]).to_pandas()
            frames.append(t)
    df = pd.concat(frames, ignore_index=True)
    df = df[(df["venue"] == "hyperliquid") & (df["symbol"].astype(str).str.upper() == symbol.upper())]
    df = df.sort_values("ts")
    # downsample if huge
    if len(df) > 400_000:
        df = df.iloc[:: max(1, len(df) // 400_000)]
    bid = df["bid"].to_numpy(np.float64)
    ask = df["ask"].to_numpy(np.float64)
    mid = mid_price(bid, ask)
    depth = df["bid_sz"].to_numpy(np.float64) + df["ask_sz"].to_numpy(np.float64)
    return df["ts"].to_numpy(np.int64), mid, depth, bid, ask


def load_mids_warehouse(symbol: str, days: list[str]):
    """Fallback: warehouse quote stream → mid."""
    from startarb.data.bbo_stream import load_quote_stream

    q = load_quote_stream(
        "hyperliquid",
        symbol,
        days,
        table="l2_rebuild",
        max_files=12,
        quotes_per_minute=60,
    )
    # QuoteStream fields
    ts = np.asarray(q.ts_ns, dtype=np.int64)
    bid = np.asarray(q.bid, dtype=np.float64)
    ask = np.asarray(q.ask, dtype=np.float64)
    mid = mid_price(bid, ask)
    depth = np.asarray(q.bid_qty, dtype=np.float64) + np.asarray(q.ask_qty, dtype=np.float64)
    return ts, mid, depth, bid, ask


def session_effects(ts_ns: np.ndarray, notional: np.ndarray, spread_bps: np.ndarray | None) -> dict[str, Any]:
    """Crypto analogue of open/close: UTC hour buckets + Asia/EU/US sessions."""
    sec = ts_ns.astype(np.int64) // 1_000_000_000
    hour = ((sec % 86_400) // 3600).astype(np.int64)
    sessions = {
        "asia": (hour >= 0) & (hour < 8),
        "eu": (hour >= 8) & (hour < 16),
        "us": (hour >= 16) & (hour < 24),
    }
    out: dict[str, Any] = {"hourly_notional_share": [], "sessions": {}}
    vol = np.zeros(24, dtype=np.float64)
    for h in range(24):
        vol[h] = float(notional[hour == h].sum())
    tot = vol.sum()
    share = vol / tot if tot > 0 else vol
    out["hourly_notional_share"] = share.tolist()
    out["peak_hour_utc"] = int(np.argmax(share)) if tot > 0 else -1
    out["fei_hourly"] = float(
        __import__("research.lib.fei", fromlist=["fei"]).fei(share)
    )
    for name, mask in sessions.items():
        n = float(notional[mask].sum())
        row: dict[str, Any] = {"notional_share": n / tot if tot > 0 else float("nan"), "n_trades": int(mask.sum())}
        if spread_bps is not None:
            sub = spread_bps[mask]
            ci = bootstrap_ci(sub[np.isfinite(sub)], n_boot=300, seed=21)
            row["mean_spread_bps"] = ci["point"]
            row["spread_ci95"] = [ci["lo"], ci["hi"]]
        out["sessions"][name] = row
    # overnight proxy: hour 0–3 vs 13–16 (EU afternoon liquidity)
    off = float(share[0:4].mean()) if tot > 0 else float("nan")
    on = float(share[13:17].mean()) if tot > 0 else float("nan")
    out["offhours_vs_eu_aft_ratio"] = off / on if on and on > 0 else float("nan")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--days", nargs="*", default=None)
    ap.add_argument("--max-files", type=int, default=24)
    ap.add_argument("--tob-root", type=Path, default=DEFAULT_TOB)
    ap.add_argument("--warehouse-mids", action="store_true")
    args = ap.parse_args()

    _ensure_env()
    from warehouse import list_days

    days = args.days or list_days("hyperliquid")[-3:]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    tape = load_trades(args.symbol, days, args.max_files)
    side = np.asarray(tape.side, dtype=np.float64)
    # map if warehouse uses 1/-1 already; if only {0,1} map 0→-1
    uniq = set(np.unique(side).tolist())
    if uniq <= {0.0, 1.0} or uniq <= {0, 1}:
        side = np.where(side > 0, 1.0, -1.0)
    px = np.asarray(tape.price, dtype=np.float64)
    qty = np.asarray(tape.qty_coin, dtype=np.float64)
    ts = np.asarray(tape.ts_ns, dtype=np.int64)
    notional = px * qty

    # mids
    mid_source = "collector_tob"
    try:
        if args.warehouse_mids:
            raise RuntimeError("force warehouse")
        m_ts, mid, depth, bid, ask = load_mids_from_tob(args.symbol, args.tob_root)
        # overlap trades with mid window
        m0, m1 = int(m_ts.min()), int(m_ts.max())
        in_win = (ts >= m0) & (ts <= m1)
        if int(in_win.sum()) < 500:
            raise RuntimeError(f"overlap too small ({in_win.sum()})")
        ts_w, px_w, side_w, qty_w, notional_w = ts[in_win], px[in_win], side[in_win], qty[in_win], notional[in_win]
    except Exception as e:  # noqa: BLE001
        mid_source = f"warehouse_l2_rebuild ({e})"
        m_ts, mid, depth, bid, ask = load_mids_warehouse(args.symbol, days)
        ts_w, px_w, side_w, qty_w, notional_w = ts, px, side, qty, notional

    # as-of mid at trade
    i0 = np.searchsorted(m_ts, ts_w, side="right") - 1
    valid = (i0 >= 0) & (i0 < m_ts.size)
    mid0 = np.full(ts_w.size, np.nan)
    mid0[valid] = mid[i0[valid]]
    bid0 = np.full(ts_w.size, np.nan)
    ask0 = np.full(ts_w.size, np.nan)
    bid0[valid] = bid[i0[valid]]
    ask0[valid] = ask[i0[valid]]

    # 1s future mid for realized / markout table
    i1 = np.searchsorted(m_ts, ts_w + 1_000_000_000, side="right") - 1
    mid1 = np.full(ts_w.size, np.nan)
    ok1 = valid & (i1 > i0) & (i1 < m_ts.size)
    mid1[ok1] = mid[i1[ok1]]

    eff = effective_spread_bps(px_w, mid0, side_w)
    real = realized_spread_bps(px_w, mid1, side_w)
    qspr = quoted_spread_bps(bid0, ask0, mid=mid0)
    # Roll on mid returns at ~1s if collector dense else use trade returns
    if m_ts.size > 100:
        # approx 1s grid roll
        step = 1_000_000_000
        grid = np.arange(int(m_ts.min()), int(m_ts.max()), step)
        idx = np.searchsorted(m_ts, grid, side="right") - 1
        okg = (idx >= 0) & (idx < m_ts.size)
        mgrid = mid[idx[okg]]
        rets = np.diff(np.log(mgrid[mgrid > 0]))
        roll = roll_implied_spread(rets)
        # convert price units → bps via mean mid
        roll_bps = float(1e4 * roll / np.nanmean(mgrid)) if np.isfinite(roll) and np.nanmean(mgrid) > 0 else float("nan")
    else:
        roll_bps = float("nan")

    mo = trade_markouts(ts_w, px_w, side_w, m_ts, mid, horizons_ms=(100, 500, 1000, 5000, 30000))
    # 1s markouts vector for adverse table
    mo_1s = np.full(ts_w.size, np.nan)
    i1s = np.searchsorted(m_ts, ts_w + 1_000_000_000, side="right") - 1
    vok = valid & (i1s > i0) & (i1s < m_ts.size) & np.isfinite(side_w) & (mid0 > 0)
    mo_1s[vok] = side_w[vok] * 1e4 * (mid[i1s[vok]] - mid0[vok]) / mid0[vok]
    adv = adverse_selection_table(mo_1s, side_w, notional_w)

    # Resilience after trades (L0 depth recovery proxy; not true queue position)
    # Prefer large notionals as events; cap sample for runtime.
    if notional_w.size:
        thr_n = float(np.nanquantile(notional_w, 0.9))
        ev_mask = notional_w >= thr_n
        ev = ts_w[ev_mask]
    else:
        ev = ts_w
    if ev.size > 600:
        ev = ev[:: max(1, ev.size // 600)]
    res = tob_resilience(m_ts, mid, depth, ev, horizons_ms=(100, 500, 1000, 5000))

    sess = session_effects(ts_w, notional_w, qspr)
    # Incomplete UTC coverage (warehouse tails) → don't overclaim session Promote
    hour_shares = np.asarray(sess.get("hourly_notional_share", []), dtype=np.float64)
    hours_active = int((hour_shares > 0).sum()) if hour_shares.size else 0
    sess["hours_active"] = hours_active
    sess_decision = "Promote" if hours_active >= 12 else "Hold"

    # train/test: mean 1s markout
    tr, te = time_split_mask(ts_w, train_frac=0.7)
    mo_tr = bootstrap_ci(mo_1s[tr], n_boot=400, seed=31)
    mo_te = bootstrap_ci(mo_1s[te], n_boot=400, seed=32)

    eff_ci = bootstrap_ci(eff, n_boot=400, seed=33)
    real_ci = bootstrap_ci(real, n_boot=400, seed=34)
    q_ci = bootstrap_ci(qspr, n_boot=400, seed=35)

    # Promote decisions under scrutiny
    mo_1s_mean = mo["by_horizon"].get("1000", {})
    promote_markout = bool(
        mo_1s_mean.get("n", 0) >= 200
        and np.isfinite(mo_1s_mean.get("mean_bps", float("nan")))
        and mo_1s_mean["ci95"][0] > 0  # adverse selection positive for maker
    )
    promote_eff = bool(eff_ci["n"] >= 200 and np.isfinite(eff_ci["point"]) and abs(eff_ci["point"]) > 0)
    # Kill Roll if unidentified
    roll_decision = "Kill" if not np.isfinite(roll_bps) else "Hold"
    n_res = int(res["n_events"][2]) if len(res.get("n_events", [])) > 2 else int(res["n_events"][0] if res.get("n_events") else 0)
    promote_res = n_res >= 50 and np.isfinite(res["mean_depth_ratio"][2] if len(res["mean_depth_ratio"]) > 2 else float("nan"))

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": args.symbol,
        "days": days,
        "n_trades": int(ts_w.size),
        "mid_source": mid_source,
        "n_mids": int(m_ts.size),
        "spreads": {
            "quoted_bps": q_ci,
            "effective_bps": eff_ci,
            "realized_1s_bps": real_ci,
            "roll_bps": roll_bps,
            "roll_decision": roll_decision,
        },
        "markouts": mo,
        "adverse_selection": adv,
        "resilience": res,
        "session_effects": sess,
        "markout_train_test": {"train": mo_tr, "test": mo_te},
        "decisions": {
            "tox.markout_1s": "Promote" if promote_markout else "Hold",
            "spread.effective_vs_quoted": "Promote" if promote_eff else "Hold",
            "spread.roll": roll_decision,
            "book.resilience": "Promote" if promote_res else "Hold",
            "sess.utc_hour_share": sess_decision,
        },
        "falsifiers": {
            "tox.markout_1s": "CI includes ≤0 at 1s on held-out half, or flips sign by side",
            "spread.effective_vs_quoted": "effective ≪ 0.5·quoted persistently (bad side/mid join)",
            "book.resilience": "depth_ratio@1s ≈ 1 always (no impact events) or mid move uncorrelated",
            "sess.utc_hour_share": "hourly shares flat within bootstrap noise across days, or <12 active UTC hours in sample",
        },
    }
    out_json = OUT_DIR / f"exp_classic_{args.symbol.lower()}_summary.json"
    out_json.write_text(json.dumps(payload, indent=2))

    lines = [
        f"# Classic microstructure — {args.symbol}",
        "",
        f"- Days: {days}",
        f"- Trades in window: **{ts_w.size:,}** · mids: **{m_ts.size:,}** ({mid_source})",
        f"- Quoted spread: **{q_ci['point']:.3f}** bps CI95 [{q_ci['lo']:.3f},{q_ci['hi']:.3f}]",
        f"- Effective spread: **{eff_ci['point']:.3f}** bps · Realized 1s: **{real_ci['point']:.3f}** bps",
        f"- Roll implied: **{roll_bps}** ({roll_decision})",
        f"- Markout 1s mean: **{mo_1s_mean.get('mean_bps', float('nan'))}** "
        f"CI {mo_1s_mean.get('ci95')} · decision **{payload['decisions']['tox.markout_1s']}**",
        f"- Peak hour UTC: **{sess['peak_hour_utc']}** · off/EU-aft ratio: **{sess['offhours_vs_eu_aft_ratio']:.3f}**",
        f"- Resilience n@1s: **{res['n_events'][2] if len(res['n_events'])>2 else 0}** · "
        f"depth_ratio means: {res['mean_depth_ratio']} · hours_active={hours_active}",
        "",
        "## Decisions",
        "",
    ]
    for k, v in payload["decisions"].items():
        lines.append(f"- `{k}`: **{v}** — falsifier: {payload['falsifiers'].get(k, '—')}")
    lines += ["", f"JSON: `{out_json.name}`", ""]
    report = OUT_DIR / f"exp_classic_{args.symbol.lower()}_REPORT.md"
    report.write_text("\n".join(lines))
    print(report.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
