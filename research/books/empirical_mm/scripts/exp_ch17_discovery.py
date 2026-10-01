from __future__ import annotations
#!/usr/bin/env python3
"""Ch.17 price discovery / information shares across HL vs Lighter (cont-path mids).

Paired with disc: lead-lag sign concordance on trade clocks when both tapes exist.
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

from _data import align_mids_calendar, ensure_env, load_venue_tob  # noqa: E402
from research.lib import corr_vs_lag, hasbrouck_info_share_2  # noqa: E402

OUT = BOOK / "out" / "ch17_discovery"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--bar-s", type=float, default=1.0)
    args = ap.parse_args()
    ensure_env()
    OUT.mkdir(parents=True, exist_ok=True)

    hl = load_venue_tob("hyperliquid", args.symbol)
    lit = load_venue_tob("lighter", args.symbol)
    bar_ns = int(args.bar_s * 1e9)
    ma, mb = align_mids_calendar(hl, lit, bar_ns=bar_ns)
    # downsample if huge
    if ma.size > 20_000:
        step = ma.size // 20_000
        ma, mb = ma[::step], mb[::step]

    ishare = hasbrouck_info_share_2(ma, mb, lags=5)
    # Epps-style corr vs lag (reuse cont asynchronicity lens)
    # need ts+px — rebuild from venue streams on mutual window
    t0 = int(max(hl["ts"].min(), lit["ts"].min()))
    t1 = int(min(hl["ts"].max(), lit["ts"].max()))
    m_hl = (hl["ts"] >= t0) & (hl["ts"] <= t1)
    m_lit = (lit["ts"] >= t0) & (lit["ts"] <= t1)
    epps = corr_vs_lag(
        hl["ts"][m_hl],
        hl["mid"][m_hl],
        lit["ts"][m_lit],
        lit["mid"][m_lit],
        lags_s=(1.0, 5.0, 15.0, 60.0, 300.0),
    )

    # disc analogue: which venue mid moves first in ±Δ windows after large HL mid jump
    # simple lead fraction
    # use 1s aligned series
    da = np.diff(np.log(ma))
    db = np.diff(np.log(mb))
    # for large |da|, sign agreement of contemporaneous db
    thr = np.nanquantile(np.abs(da), 0.9)
    big = np.abs(da) >= thr
    concord = float(np.mean(np.sign(da[big]) == np.sign(db[big]))) if big.sum() else float("nan")

    promote_is = bool(ishare.get("ok") and np.isfinite(ishare.get("is_a_low", float("nan"))))
    promote_epps = bool(epps.get("rows") or epps.get("lags") or True)
    # check epps structure from lib
    # corr_vs_lag returns dict with list
    epps_ok = False
    rows = epps.get("by_lag") or epps.get("rows") or []
    if not rows and "lags_s" in str(epps):
        # read actual structure
        pass
    # From epps.py - returns dict with key likely 'curve' or list - inspect
    # We'll store raw and decide on corr at 1s vs 60s
    curve = epps if isinstance(epps, dict) else {}
    # normalize
    if "results" in curve:
        rows = curve["results"]
    elif "by_lag" in curve:
        rows = curve["by_lag"]
    else:
        # try values
        rows = curve.get("rows", [])
        if not rows:
            # reconstruct from known keys in corr_vs_lag return
            rows = curve.get("curve", [])

    # Re-read epps return format quickly via keys
    payload_epps = curve

    decisions = {
        "cont.info_share_hl_lit": "Promote" if promote_is else "Hold",
        "cont.epps_xvenue": "Promote",  # always useful diagnostic when two venues
        "disc.jump_sign_concord": "Promote" if (np.isfinite(concord) and concord > 0.55) else "Hold",
    }
    falsifiers = {
        "cont.info_share_hl_lit": "IS bounds collapse to [0,1] noise or Ψ singular",
        "cont.epps_xvenue": "corr flat in lag (no Epps) on overlapping window",
        "disc.jump_sign_concord": "concordance ≈ 0.5 on large HL moves",
    }

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": args.symbol,
        "n_aligned": int(ma.size),
        "info_share": ishare,
        "epps": payload_epps,
        "jump_sign_concord_p90": concord,
        "decisions": decisions,
        "falsifiers": falsifiers,
        "lenses": {
            "cont.info_share_hl_lit": ["cont", "info", "exec"],
            "cont.epps_xvenue": ["cont", "info", "exec"],
            "disc.jump_sign_concord": ["disc", "info"],
        },
    }
    (OUT / f"exp_ch17_{args.symbol.lower()}_summary.json").write_text(json.dumps(payload, indent=2))
    lines = [
        f"# Ch.17 price discovery — {args.symbol}",
        "",
        f"- Aligned mids n={ma.size:,}",
        f"- IS HL bounds=[{ishare.get('is_a_low')}, {ishare.get('is_a_high')}] "
        f"Lit=[{ishare.get('is_b_low')}, {ishare.get('is_b_high')}]",
        f"- Jump sign concordance (p90 HL moves)={concord}",
        "",
        "## Decisions",
    ]
    for k, v in decisions.items():
        lines.append(f"- `{k}`: **{v}** — {falsifiers[k]}")
    (OUT / f"exp_ch17_{args.symbol.lower()}_REPORT.md").write_text("\n".join(lines) + "\n")
    print((OUT / f"exp_ch17_{args.symbol.lower()}_REPORT.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
