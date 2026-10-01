from __future__ import annotations
#!/usr/bin/env python3
"""Ch.15 PIN (disc mixture intuition) + VPIN / intensity (cont) + Ch.22 Amihud.

EHO PIN full MLE needs day-level B/S counts across many days — we ship:
- disc: buy/sell imbalance mixture diagnostics on calendar days available
- cont: VPIN buckets + trade intensity
- liq: Amihud on calendar bars
"""

import os

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb')) / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import ensure_env, load_hl_tob, load_trades, overlap_trades_with_mids, resolve_days  # noqa: E402
from research.lib import (  # noqa: E402
    amihud_illiquidity,
    bootstrap_ci,
    calendar_returns,
    trade_intensity,
    vpin_bucket,
)

OUT15 = BOOK / "out" / "ch15_pin"
OUT22 = BOOK / "out" / "ch22_liquidity"


def daily_bs_counts(ts: np.ndarray, side: np.ndarray) -> dict:
    """Per UTC day buy/sell counts — PIN likelihood inputs (disc)."""
    sec = ts.astype(np.int64) // 1_000_000_000
    day = sec // 86_400
    out = {}
    for d in np.unique(day):
        m = day == d
        s = side[m]
        out[str(int(d))] = {
            "B": int((s > 0).sum()),
            "S": int((s < 0).sum()),
            "n": int(m.sum()),
            "imb": float((s > 0).sum() - (s < 0).sum()) / max(int(m.sum()), 1),
        }
    return out


def pin_proxy_from_days(days_bs: dict) -> dict:
    """Crude PIN-style proxy without full MLE: mean |imb| and mixture gap.

    Full EHO MLE Hold until ≥20 full days. This is a descriptive stand-in.
    """
    imbs = np.array([v["imb"] for v in days_bs.values()], dtype=np.float64)
    Bs = np.array([v["B"] for v in days_bs.values()], dtype=np.float64)
    Ss = np.array([v["S"] for v in days_bs.values()], dtype=np.float64)
    # naive: PIN ~ E[|B-S|] / E[B+S]
    pin_hat = float(np.mean(np.abs(Bs - Ss) / np.maximum(Bs + Ss, 1)))
    return {
        "n_days": int(len(days_bs)),
        "pin_proxy": pin_hat,
        "mean_abs_imb": float(np.mean(np.abs(imbs))) if imbs.size else float("nan"),
        "mean_B": float(np.mean(Bs)) if Bs.size else float("nan"),
        "mean_S": float(np.mean(Ss)) if Ss.size else float("nan"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--days", nargs="*", default=None)
    ap.add_argument("--max-files", type=int, default=32)
    args = ap.parse_args()
    ensure_env()
    days = resolve_days(args.days, n=5)
    OUT15.mkdir(parents=True, exist_ok=True)
    OUT22.mkdir(parents=True, exist_ok=True)

    tob = load_hl_tob(args.symbol)
    tape = load_trades(args.symbol, days, args.max_files)
    ov = overlap_trades_with_mids(tape, tob)
    ok = np.isfinite(ov["side"]) & (ov["side"] != 0) & (ov["qty"] > 0)
    ts, side, qty, px = ov["ts"][ok], ov["side"][ok], ov["qty"][ok], ov["px"][ok]

    days_bs = daily_bs_counts(ts, side)
    pin = pin_proxy_from_days(days_bs)
    bar_v = float(np.nanmedian(qty) * 100)
    vpin = vpin_bucket(side, qty, bucket_volume=bar_v, n_buckets_window=50)
    intens = trade_intensity(ts, bar_ns=1_000_000_000)

    # Amihud on 1m calendar bars from trades
    # build dollar volume and returns
    t0, t1 = int(ts.min()), int(ts.max())
    bar = 60_000_000_000
    grid = np.arange(t0, t1 + 1, bar, dtype=np.int64)
    idx = np.searchsorted(ts, grid, side="left")
    rets, dvol = [], []
    last_px = np.nan
    for i in range(len(grid) - 1):
        lo, hi = idx[i], idx[i + 1]
        if hi <= lo:
            continue
        p_close = float(px[hi - 1])
        dv = float(np.sum(px[lo:hi] * qty[lo:hi]))
        if np.isfinite(last_px) and last_px > 0 and p_close > 0 and dv > 0:
            rets.append(np.log(p_close / last_px))
            dvol.append(dv)
        last_px = p_close
    amihud = amihud_illiquidity(np.asarray(rets), np.asarray(dvol))

    # quoted spread mean as liquidity companion
    from research.lib import quoted_spread_bps, bootstrap_ci

    qs = quoted_spread_bps(tob["bid"], tob["ask"], mid=tob["mid"])
    qs_ci = bootstrap_ci(qs, n_boot=300, seed=55)

    promote_vpin = bool(vpin.get("n_buckets", 0) >= 20 and np.isfinite(vpin.get("mean_vpin", float("nan"))))
    promote_int = bool(intens.get("n_bars", 0) >= 30 and np.isfinite(intens.get("mean_lambda", float("nan"))))
    promote_ami = bool(amihud.get("n", 0) >= 20 and np.isfinite(amihud.get("illiq", float("nan"))))
    # PIN MLE Hold — too few days
    pin_dec = "Hold" if pin["n_days"] < 20 else ("Promote" if pin["pin_proxy"] > 0 else "Kill")

    p15 = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": args.symbol,
        "days": days,
        "disc_pin": pin,
        "daily_bs": days_bs,
        "cont_vpin": vpin,
        "cont_intensity": intens,
        "decisions": {
            "disc.pin_eho_mle": pin_dec,
            "disc.pin_proxy_dayimb": "Hold",
            "cont.vpin": "Promote" if promote_vpin else "Hold",
            "cont.trade_intensity": "Promote" if promote_int else "Hold",
        },
        "falsifiers": {
            "disc.pin_eho_mle": "<20 full days or MLE unstable → Hold",
            "disc.pin_proxy_dayimb": "proxy uncorrelated with markout/VPIN across regimes",
            "cont.vpin": "flat VPIN across buckets / n_buckets<20",
            "cont.trade_intensity": "λ̂ CI empty or no clustering (ac1≈0 always)",
        },
        "lenses": {
            "disc.pin_eho_mle": ["disc", "info"],
            "disc.pin_proxy_dayimb": ["disc", "info"],
            "cont.vpin": ["cont", "info", "mm", "exec"],
            "cont.trade_intensity": ["cont", "exec", "info"],
        },
    }
    p22 = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": args.symbol,
        "days": days,
        "amihud": amihud,
        "quoted_spread_bps": qs_ci,
        "decisions": {
            "liq.amihud_1m": "Promote" if promote_ami else "Hold",
            "liq.quoted_spread_bps": "Promote" if qs_ci["n"] > 100 else "Hold",
        },
        "falsifiers": {
            "liq.amihud_1m": "ILLIQ≈0 or unstable across days",
            "liq.quoted_spread_bps": "non-finite / empty TOB",
        },
        "lenses": {
            "liq.amihud_1m": ["liq", "info", "exec"],
            "liq.quoted_spread_bps": ["liq", "mm", "exec"],
        },
    }
    (OUT15 / f"exp_ch15_{args.symbol.lower()}_summary.json").write_text(json.dumps(p15, indent=2))
    (OUT22 / f"exp_ch22_{args.symbol.lower()}_summary.json").write_text(json.dumps(p22, indent=2))
    r15 = [
        f"# Ch.15 PIN / VPIN / intensity — {args.symbol}",
        "",
        f"- PIN proxy days={pin['n_days']} pin_proxy={pin['pin_proxy']:.4f}",
        f"- VPIN mean={vpin.get('mean_vpin')} n_buckets={vpin.get('n_buckets')}",
        f"- Intensity λ={intens.get('mean_lambda')} /s · ac1={intens.get('count_ac1')}",
        "",
        "## Decisions",
    ]
    for k, v in p15["decisions"].items():
        r15.append(f"- `{k}`: **{v}**")
    (OUT15 / f"exp_ch15_{args.symbol.lower()}_REPORT.md").write_text("\n".join(r15) + "\n")
    r22 = [
        f"# Ch.22 liquidity / Amihud — {args.symbol}",
        "",
        f"- Amihud ILLIQ={amihud}",
        f"- Quoted spread={qs_ci}",
        "",
        "## Decisions",
    ]
    for k, v in p22["decisions"].items():
        r22.append(f"- `{k}`: **{v}**")
    (OUT22 / f"exp_ch22_{args.symbol.lower()}_REPORT.md").write_text("\n".join(r22) + "\n")
    print((OUT15 / f"exp_ch15_{args.symbol.lower()}_REPORT.md").read_text())
    print((OUT22 / f"exp_ch22_{args.symbol.lower()}_REPORT.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
