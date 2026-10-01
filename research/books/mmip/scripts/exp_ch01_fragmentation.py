from __future__ import annotations
#!/usr/bin/env python3
"""Chapter 1 experiment: fragmentation metrics on cross-venue ETH TOB.

Implements book measures from *Market Microstructure in Practice* Ch.1 / App.A.1:
  - Market-share-style weights from visible TOB size (proxy when trade tape absent)
  - Entropy H and Fragmentation Efficiency Index FEI = H / log(N)
  - Cross-venue spreads (bps, ticks) and NBBO participation
  - Duplicate best-price incidence (SOR / duplicate-liquidity caution)

Data preference (no ClickHouse MCP):
  1. ares-startarb collector parquet ``results/xarb_md/tob/``
  2. Optional live public REST snapshot (Hyperliquid + Binance) as sanity check

Paper only. No orders.
"""

import os

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq

BOOK_ROOT = Path(__file__).resolve().parents[1]
ROOT = BOOK_ROOT.parents[2]  # repo root (mmip → books → research → repo)
DEFAULT_TOB = Path(str(Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb')) / "results/xarb_md/tob"))
OUT_DIR = BOOK_ROOT / "out" / "ch01_fragmentation"


def entropy(q: np.ndarray) -> float:
    """Shannon entropy H = -sum q log q (nats). 0*log0 := 0."""
    q = np.asarray(q, dtype=np.float64)
    q = q[q > 0]
    if q.size == 0:
        return 0.0
    return float(-np.sum(q * np.log(q)))


def fei(q: np.ndarray) -> float:
    """Fragmentation Efficiency Index F = H / log(N) for N pools with q_n>0 or fixed N."""
    q = np.asarray(q, dtype=np.float64)
    s = q.sum()
    if s <= 0:
        return 0.0
    q = q / s
    n = int((q > 0).sum())
    if n <= 1:
        return 0.0
    return entropy(q) / math.log(n)


def infer_tick(prices: np.ndarray) -> float:
    """Infer min positive price increment from observed best prices."""
    p = np.unique(np.round(prices.astype(np.float64), 10))
    if p.size < 2:
        return float("nan")
    d = np.diff(np.sort(p))
    d = d[d > 1e-12]
    if d.size == 0:
        return float("nan")
    return float(np.min(d))


@dataclass
class Summary:
    symbol: str
    n_rows: int
    venues: list[str]
    window_start_ns: int
    window_end_ns: int
    duration_s: float
    size_share: dict[str, float]
    update_share: dict[str, float]
    fei_size: float
    fei_updates: float
    entropy_size: float
    mean_spread_bps: dict[str, float]
    median_spread_bps: dict[str, float]
    frac_one_tick: dict[str, float]
    inferred_tick: dict[str, float]
    nbbo_bid_frac: dict[str, float]
    nbbo_ask_frac: dict[str, float]
    duplicate_bid_frac: float
    duplicate_ask_frac: float
    n_aligned_buckets: int
    bucket_ms: int


def _base_symbol(sym: str) -> str:
    """Normalize HL ``ETH``, RiseX ``ETH/USDC``, etc. → ``ETH``."""
    s = str(sym or "").strip().upper()
    if "/" in s:
        s = s.split("/", 1)[0]
    if s.endswith("USDT"):
        s = s[: -len("USDT")]
    if s.endswith("USDC"):
        s = s[: -len("USDC")]
    if s.endswith("-PERPETUAL"):
        s = s[: -len("-PERPETUAL")]
    return s


def load_tob(tob_root: Path, day: str | None, symbol: str) -> Any:
    import pandas as pd

    if day:
        day_dirs = [tob_root / day]
    else:
        day_dirs = sorted(p for p in tob_root.iterdir() if p.is_dir())
        if not day_dirs:
            raise FileNotFoundError(f"No day dirs under {tob_root}")
        day_dirs = [day_dirs[-1]]

    frames = []
    for d in day_dirs:
        files = sorted(d.glob("tob_*.parquet"))
        if not files:
            raise FileNotFoundError(f"No tob_*.parquet in {d}")
        for f in files:
            frames.append(pq.read_table(f).to_pandas())
    df = pd.concat(frames, ignore_index=True)
    want = symbol.upper()
    df = df[_base_symbol_series(df["symbol"]) == want].copy()
    if df.empty:
        raise RuntimeError(f"No rows for symbol={symbol} in {day_dirs}")
    df["venue"] = df["venue"].astype(str).str.lower()
    df["base"] = want
    df["mid"] = 0.5 * (df["bid"] + df["ask"])
    df["spread"] = df["ask"] - df["bid"]
    df["spread_bps"] = 1e4 * df["spread"] / df["mid"]
    df["tob_sz"] = df["bid_sz"].astype(float) + df["ask_sz"].astype(float)
    df = df.sort_values("ts").reset_index(drop=True)
    return df


def _base_symbol_series(series: Any) -> Any:
    return series.map(_base_symbol)


def align_buckets(df: Any, venues: list[str], bucket_ms: int) -> Any:
    import pandas as pd

    bucket_ns = int(bucket_ms * 1_000_000)
    df = df.copy()
    df["bucket"] = (df["ts"].astype("int64") // bucket_ns) * bucket_ns
    # last quote in bucket per venue
    last = (
        df.sort_values("ts")
        .groupby(["bucket", "venue"], as_index=False)
        .tail(1)
    )
    wide = {}
    for v in venues:
        sub = last[last["venue"] == v].set_index("bucket")
        wide[v] = sub
    # intersection of buckets with all venues present
    common = None
    for v in venues:
        idx = set(wide[v].index)
        common = idx if common is None else (common & idx)
    if not common:
        raise RuntimeError("No common time buckets across venues")
    buckets = sorted(common)
    rows = []
    for b in buckets:
        row: dict[str, Any] = {"bucket": b}
        for v in venues:
            r = wide[v].loc[b]
            row[f"{v}_bid"] = float(r["bid"])
            row[f"{v}_ask"] = float(r["ask"])
            row[f"{v}_bid_sz"] = float(r["bid_sz"])
            row[f"{v}_ask_sz"] = float(r["ask_sz"])
            row[f"{v}_spread"] = float(r["spread"])
            row[f"{v}_spread_bps"] = float(r["spread_bps"])
            row[f"{v}_tob_sz"] = float(r["tob_sz"])
            row[f"{v}_mid"] = float(r["mid"])
        rows.append(row)
    return pd.DataFrame(rows)


def analyze(df: Any, bucket_ms: int, symbol: str) -> tuple[Summary, dict[str, Any]]:
    venues = sorted(df["venue"].unique().tolist())
    aligned = align_buckets(df, venues, bucket_ms)

    # Crossed / consolidated book diagnostics (Ch.1 SOR motivation)
    if len(venues) >= 2:
        bids = np.column_stack([aligned[f"{v}_bid"].to_numpy() for v in venues])
        asks = np.column_stack([aligned[f"{v}_ask"].to_numpy() for v in venues])
        c_bid = bids.max(axis=1)
        c_ask = asks.min(axis=1)
        c_mid = 0.5 * (c_bid + c_ask)
        cons_spread_bps = 1e4 * (c_ask - c_bid) / np.where(c_mid > 0, c_mid, np.nan)
        crossed_frac = float(np.mean(c_ask < c_bid))
    else:
        cons_spread_bps = np.array([])
        crossed_frac = float("nan")

    # size shares from aligned TOB size
    size_mat = np.column_stack([aligned[f"{v}_tob_sz"].to_numpy() for v in venues])
    size_mat = np.maximum(size_mat, 0.0)
    row_sum = size_mat.sum(axis=1, keepdims=True)
    row_sum[row_sum <= 0] = np.nan
    shares = size_mat / row_sum
    mean_share = np.nanmean(shares, axis=0)
    mean_share = mean_share / mean_share.sum()

    # update activity share (raw event counts)
    upd = df["venue"].value_counts()
    upd_share = {v: float(upd.get(v, 0)) / float(len(df)) for v in venues}

    fei_series = np.array([fei(shares[i]) for i in range(len(shares))], dtype=np.float64)
    fei_size = float(np.nanmean(fei_series))
    H_size = entropy(mean_share)

    # ticks + spreads
    ticks: dict[str, float] = {}
    mean_bps: dict[str, float] = {}
    med_bps: dict[str, float] = {}
    one_tick: dict[str, float] = {}
    for v in venues:
        sub = df[df["venue"] == v]
        tick = infer_tick(np.concatenate([sub["bid"].to_numpy(), sub["ask"].to_numpy()]))
        ticks[v] = tick
        mean_bps[v] = float(sub["spread_bps"].mean())
        med_bps[v] = float(sub["spread_bps"].median())
        if tick == tick and tick > 0:
            one_tick[v] = float(np.mean(np.abs(sub["spread"].to_numpy() - tick) < 0.5 * tick))
        else:
            one_tick[v] = float("nan")

    # NBBO participation + duplicate liquidity on aligned panel
    bids = np.column_stack([aligned[f"{v}_bid"].to_numpy() for v in venues])
    asks = np.column_stack([aligned[f"{v}_ask"].to_numpy() for v in venues])
    best_bid = bids.max(axis=1, keepdims=True)
    best_ask = asks.min(axis=1, keepdims=True)
    # tolerate half-tick equality using min inferred tick across venues
    valid_ticks = [t for t in ticks.values() if t == t and t > 0]
    tol = 0.5 * min(valid_ticks) if valid_ticks else 1e-9
    on_bb = np.abs(bids - best_bid) <= tol
    on_ba = np.abs(asks - best_ask) <= tol
    nbbo_bid = {v: float(on_bb[:, i].mean()) for i, v in enumerate(venues)}
    nbbo_ask = {v: float(on_ba[:, i].mean()) for i, v in enumerate(venues)}
    dup_bid = float((on_bb.sum(axis=1) >= 2).mean())
    dup_ask = float((on_ba.sum(axis=1) >= 2).mean())

    summary = Summary(
        symbol=symbol,
        n_rows=int(len(df)),
        venues=venues,
        window_start_ns=int(df["ts"].min()),
        window_end_ns=int(df["ts"].max()),
        duration_s=float((df["ts"].max() - df["ts"].min()) / 1e9),
        size_share={v: float(mean_share[i]) for i, v in enumerate(venues)},
        update_share=upd_share,
        fei_size=fei_size,
        fei_updates=fei(np.array([upd_share[v] for v in venues])),
        entropy_size=H_size,
        mean_spread_bps=mean_bps,
        median_spread_bps=med_bps,
        frac_one_tick=one_tick,
        inferred_tick=ticks,
        nbbo_bid_frac=nbbo_bid,
        nbbo_ask_frac=nbbo_ask,
        duplicate_bid_frac=dup_bid,
        duplicate_ask_frac=dup_ask,
        n_aligned_buckets=int(len(aligned)),
        bucket_ms=bucket_ms,
    )

    # FEI reference configs from book Table 1.2
    refs = {
        "25/25/25/25": fei(np.array([0.25, 0.25, 0.25, 0.25])),
        "50/50": fei(np.array([0.5, 0.5])),
        "70/20/5/5": fei(np.array([0.70, 0.20, 0.05, 0.05])),
        "70/20/10": fei(np.array([0.70, 0.20, 0.10])),
        "observed_mean_size": fei(mean_share),
    }
    extras = {
        "fei_size_series_p50": float(np.nanmedian(fei_series)),
        "fei_size_series_p10": float(np.nanpercentile(fei_series, 10)),
        "fei_size_series_p90": float(np.nanpercentile(fei_series, 90)),
        "fei_reference_table": refs,
        "aligned_mean_spread_bps": {
            v: float(aligned[f"{v}_spread_bps"].mean()) for v in venues
        },
        "consolidated_spread_bps_mean": float(np.nanmean(cons_spread_bps))
        if cons_spread_bps.size
        else None,
        "crossed_book_frac": crossed_frac,
    }
    return summary, extras


def live_public_snapshot(symbol: str = "ETH") -> dict[str, Any]:
    """Optional public REST snapshot: HL L2 + Binance bookTicker (not startarb)."""
    import json as _json
    import urllib.request

    out: dict[str, Any] = {"symbol": symbol, "sources": []}
    # Hyperliquid
    req = urllib.request.Request(
        "https://api.hyperliquid.xyz/info",
        data=_json.dumps({"type": "l2Book", "coin": symbol}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        hl = _json.loads(resp.read().decode())
    bid = float(hl["levels"][0][0]["px"])
    ask = float(hl["levels"][1][0]["px"])
    bid_sz = float(hl["levels"][0][0]["sz"])
    ask_sz = float(hl["levels"][1][0]["sz"])
    out["hyperliquid"] = {
        "bid": bid,
        "ask": ask,
        "spread_bps": 1e4 * (ask - bid) / (0.5 * (ask + bid)),
        "tob_sz": bid_sz + ask_sz,
    }
    out["sources"].append("hyperliquid_l2Book")

    # Binance USDT perpetual-ish spot ticker as lit CEX proxy
    bn_sym = f"{symbol}USDT"
    with urllib.request.urlopen(
        f"https://api.binance.com/api/v3/ticker/bookTicker?symbol={bn_sym}",
        timeout=10,
    ) as resp:
        bn = _json.loads(resp.read().decode())
    b_bid, b_ask = float(bn["bidPrice"]), float(bn["askPrice"])
    b_bsz, b_asz = float(bn["bidQty"]), float(bn["askQty"])
    out["binance"] = {
        "bid": b_bid,
        "ask": b_ask,
        "spread_bps": 1e4 * (b_ask - b_bid) / (0.5 * (b_ask + b_bid)),
        "tob_sz": b_bsz + b_asz,
    }
    out["sources"].append("binance_bookTicker")

    sizes = np.array([out["hyperliquid"]["tob_sz"], out["binance"]["tob_sz"]], dtype=float)
    out["size_share"] = {
        "hyperliquid": float(sizes[0] / sizes.sum()),
        "binance": float(sizes[1] / sizes.sum()),
    }
    out["fei_size"] = fei(sizes)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tob-root", type=Path, default=DEFAULT_TOB)
    ap.add_argument("--day", default=None, help="YYYYMMDD under tob-root")
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--bucket-ms", type=int, default=1000)
    ap.add_argument("--live-snapshot", action="store_true")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    df = load_tob(args.tob_root, args.day, args.symbol)
    summary, extras = analyze(df, args.bucket_ms, args.symbol)
    payload: dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data_source": str(args.tob_root),
        "summary": asdict(summary),
        "extras": extras,
    }
    if args.live_snapshot:
        try:
            payload["live_public_snapshot"] = live_public_snapshot(args.symbol)
        except Exception as exc:  # noqa: BLE001
            payload["live_public_snapshot_error"] = str(exc)

    out_json = args.out_dir / f"exp_ch01_{args.symbol.lower()}_summary.json"
    out_json.write_text(json.dumps(payload, indent=2, sort_keys=True))

    # human-readable markdown
    s = summary
    lines = [
        f"# Ch1 fragmentation experiment — {s.symbol}",
        "",
        f"- Window: `{s.window_start_ns}` → `{s.window_end_ns}` ({s.duration_s:.1f}s)",
        f"- Rows: {s.n_rows:,} | venues: {', '.join(s.venues)} | aligned buckets@{s.bucket_ms}ms: {s.n_aligned_buckets:,}",
        f"- **FEI (mean TOB-size shares, time-avg of bucket FEI): {s.fei_size:.1%}**",
        f"- FEI (update-count shares): {s.fei_updates:.1%}",
        f"- Entropy H(size): {s.entropy_size:.4f} nats",
        "",
        "## Size / update shares",
        "",
        "| venue | size_share | update_share | mean_spread_bps | median_spread_bps | frac_1tick | tick |",
        "|-------|------------|--------------|-----------------|-------------------|------------|------|",
    ]
    for v in s.venues:
        lines.append(
            f"| {v} | {s.size_share[v]:.1%} | {s.update_share[v]:.1%} | "
            f"{s.mean_spread_bps[v]:.3f} | {s.median_spread_bps[v]:.3f} | "
            f"{s.frac_one_tick[v]:.1%} | {s.inferred_tick[v]} |"
        )
    lines += [
        "",
        "## NBBO / duplicate liquidity",
        "",
        f"- Duplicate best bid (≥2 venues): **{s.duplicate_bid_frac:.1%}**",
        f"- Duplicate best ask (≥2 venues): **{s.duplicate_ask_frac:.1%}**",
        f"- Crossed consolidated book (max bid > min ask): **{extras.get('crossed_book_frac', float('nan')):.1%}**",
        f"- Mean consolidated spread (bps): **{extras.get('consolidated_spread_bps_mean')}**",
        "",
        "| venue | frac_on_NBBO_bid | frac_on_NBBO_ask |",
        "|-------|------------------|------------------|",
    ]
    for v in s.venues:
        lines.append(f"| {v} | {s.nbbo_bid_frac[v]:.1%} | {s.nbbo_ask_frac[v]:.1%} |")
    lines += [
        "",
        "## Book FEI references (App A.1 / Table 1.2 style)",
        "",
        "```json",
        json.dumps(extras.get("fei_reference_table", {}), indent=2),
        "```",
        "",
        f"Artifacts: `{out_json}`",
    ]
    out_md = args.out_dir / f"exp_ch01_{args.symbol.lower()}_REPORT.md"
    out_md.write_text("\n".join(lines) + "\n")
    print(out_md.read_text())
    print(f"\nWrote {out_json} and {out_md}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    # fix accidental leftover from editing
    raise SystemExit(main())
