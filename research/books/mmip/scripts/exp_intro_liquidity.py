from __future__ import annotations
#!/usr/bin/env python3
"""Introduction chapter experiment: liquidity defs → extractable MM features.

Book front matter / Introduction (liquidity, best execution, maker–taker blur).
Data: local collector TOB (no ClickHouse). Paper only.
"""

import os

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq

BOOK_ROOT = Path(__file__).resolve().parents[1]
ROOT = BOOK_ROOT.parents[2]  # repo root (mmip → books → research → repo)
sys.path.insert(0, str(ROOT))

from ares_micro.flow import fei

from ares_micro import depth_imbalance, infer_tick, mid_price, quoted_spread_bps, time_split_mask

DEFAULT_TOB = Path(str(Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb')) / "results/xarb_md/tob"))
OUT_DIR = BOOK_ROOT / "out" / "intro_liquidity"


def _base_symbol(sym: str) -> str:
    s = str(sym or "").strip().upper()
    if "/" in s:
        s = s.split("/", 1)[0]
    for suf in ("USDT", "USDC", "-PERPETUAL"):
        if s.endswith(suf):
            s = s[: -len(suf)]
    return s


def load_tob(tob_root: Path, day: str | None, symbol: str):
    import pandas as pd

    day_dirs = [tob_root / day] if day else sorted(p for p in tob_root.iterdir() if p.is_dir())
    if not day and day_dirs:
        day_dirs = [day_dirs[-1]]
    frames = []
    for d in day_dirs:
        for f in sorted(d.glob("tob_*.parquet")):
            t = pq.read_table(f).to_pandas()
            frames.append(t)
    if not frames:
        raise FileNotFoundError(f"No TOB under {tob_root}")
    df = pd.concat(frames, ignore_index=True)
    df["base"] = df["symbol"].map(_base_symbol)
    df = df[df["base"] == symbol.upper()].copy()
    df = df.sort_values("ts").reset_index(drop=True)
    return df


def maker_taker_blur_features(df) -> dict[str, Any]:
    """Features that operationalize 'same firm is maker and taker'.

    - Quote presence / flicker (update intensity)
    - Spread regime (make cost floor)
    - Imbalance (inventory / skew input)
    - Cross-venue FEI on size (where to make vs take)
    """
    venues = sorted(df["venue"].unique().tolist())
    out: dict[str, Any] = {"venues": venues, "per_venue": {}, "panel": {}}
    spreads_all = []
    updates = []
    size_shares = []

    for v in venues:
        g = df[df["venue"] == v]
        bid = g["bid"].to_numpy(np.float64)
        ask = g["ask"].to_numpy(np.float64)
        bsz = g["bid_sz"].to_numpy(np.float64)
        asz = g["ask_sz"].to_numpy(np.float64)
        ts = g["ts"].to_numpy(np.int64)
        mid = mid_price(bid, ask)
        spr = quoted_spread_bps(bid, ask, mid=mid)
        imb = depth_imbalance(bsz, asz)
        tick = infer_tick(np.concatenate([bid, ask]))
        one_tick = np.isfinite(spr) & np.isfinite(tick) & (tick > 0)
        frac_1t = float(np.mean(np.abs((ask - bid) - tick) < 0.5 * tick)) if one_tick.any() and np.isfinite(tick) else float("nan")
        # update intensity: events per second
        dur = (float(ts[-1] - ts[0]) / 1e9) if ts.size > 1 else float("nan")
        ups = float(ts.size / dur) if dur and dur > 0 else float("nan")
        spr_ci = bootstrap_ci(spr[np.isfinite(spr)], n_boot=400, seed=3)
        imb_ci = bootstrap_ci(imb[np.isfinite(imb)], n_boot=400, seed=5)
        out["per_venue"][v] = {
            "n_quotes": int(ts.size),
            "duration_s": dur,
            "update_hz": ups,
            "mean_spread_bps": spr_ci["point"],
            "spread_ci95": [spr_ci["lo"], spr_ci["hi"]],
            "mean_imbalance": imb_ci["point"],
            "imbalance_ci95": [imb_ci["lo"], imb_ci["hi"]],
            "frac_one_tick": frac_1t,
            "inferred_tick": tick,
            "mean_tob_size": float(np.nanmean(bsz + asz)),
        }
        spreads_all.append(spr_ci["point"])
        updates.append(ups if np.isfinite(ups) else 0.0)
        size_shares.append(float(np.nanmean(bsz + asz)))

    ss = np.asarray(size_shares, dtype=np.float64)
    us = np.asarray(updates, dtype=np.float64)
    out["panel"]["fei_size"] = fei(ss)
    out["panel"]["fei_updates"] = fei(us)
    out["panel"]["size_share"] = {
        v: float(ss[i] / ss.sum()) if ss.sum() > 0 else float("nan") for i, v in enumerate(venues)
    }
    out["panel"]["update_share"] = {
        v: float(us[i] / us.sum()) if us.sum() > 0 else float("nan") for i, v in enumerate(venues)
    }
    # Role-blur score: |update_share − size_share| high ⇒ flickering maker / thin size
    blur = {
        v: float(abs(out["panel"]["update_share"][v] - out["panel"]["size_share"][v]))
        for v in venues
    }
    out["panel"]["role_blur_l1"] = blur
    out["panel"]["role_blur_max"] = float(max(blur.values())) if blur else float("nan")

    # Train/test stability of mean spread (HL if present else first venue)
    focus = "hyperliquid" if "hyperliquid" in venues else venues[0]
    g = df[df["venue"] == focus]
    spr = quoted_spread_bps(g["bid"].to_numpy(), g["ask"].to_numpy())
    ts = g["ts"].to_numpy(np.int64)
    train, test = time_split_mask(ts, train_frac=0.7)
    tr = bootstrap_ci(spr[train], n_boot=300, seed=9)
    te = bootstrap_ci(spr[test], n_boot=300, seed=10)
    out["panel"]["spread_stability"] = {
        "venue": focus,
        "train": tr,
        "test": te,
        "stable": bool(
            np.isfinite(tr["point"])
            and np.isfinite(te["lo"])
            and np.isfinite(te["hi"])
            and te["lo"] <= tr["point"] <= te["hi"]
        ),
    }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--day", default=None)
    ap.add_argument("--tob-root", type=Path, default=DEFAULT_TOB)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_tob(args.tob_root, args.day, args.symbol)
    feats = maker_taker_blur_features(df)
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": args.symbol,
        "n_rows": int(len(df)),
        "data_source": str(args.tob_root),
        "features": feats,
        "candidates": {
            "liq.quoted_spread_bps": "Promote — cost floor / make–take",
            "liq.depth_imbalance": "Promote — skew / inventory input",
            "liq.role_blur_l1": "Promote — flicker vs size monitor",
            "liq.update_hz": "Hold — venue-specific; needs latency model",
        },
    }
    out_json = OUT_DIR / f"exp_intro_{args.symbol.lower()}_summary.json"
    out_json.write_text(json.dumps(payload, indent=2))
    report = OUT_DIR / f"exp_intro_{args.symbol.lower()}_REPORT.md"
    blur = feats["panel"]["role_blur_l1"]
    lines = [
        f"# Intro liquidity experiment — {args.symbol}",
        "",
        f"- Rows: **{len(df):,}** · venues: {', '.join(feats['venues'])}",
        f"- FEI(size)={feats['panel']['fei_size']:.3f} · FEI(updates)={feats['panel']['fei_updates']:.3f}",
        f"- Max role-blur L1(|upd−size|)={feats['panel']['role_blur_max']:.3f}",
        f"- Spread train/test stable ({feats['panel']['spread_stability']['venue']}): "
        f"**{feats['panel']['spread_stability']['stable']}**",
        "",
        "## Per-venue",
        "",
    ]
    for v, row in feats["per_venue"].items():
        lines.append(
            f"- **{v}**: spread {row['mean_spread_bps']:.3f} bps "
            f"(CI [{row['spread_ci95'][0]:.3f},{row['spread_ci95'][1]:.3f}]), "
            f"imb {row['mean_imbalance']:.3f}, upd {row['update_hz']:.1f} Hz, "
            f"blur {blur.get(v, float('nan')):.3f}"
        )
    lines += ["", f"JSON: `{out_json.name}`", ""]
    report.write_text("\n".join(lines))
    print(report.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
