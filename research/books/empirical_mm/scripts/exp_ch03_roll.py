from __future__ import annotations
#!/usr/bin/env python3
"""Ch.3 Roll (disc) + Ch.8 noise-robust RV (cont) — paired clocks.

Hasbrouck notes: Roll γ₁ identification; continuous-path RV fine vs coarse.
No ClickHouse MCP.
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

from _data import (  # noqa: E402
    ensure_env,
    load_hl_tob,
    load_trades,
    overlap_trades_with_mids,
    resolve_days,
)
from research.lib import (  # noqa: E402
    bootstrap_ci,
    calendar_returns,
    noise_robust_rv,
    roll_on_mid_bps,
    time_split_mask,
    volume_clock_returns,
)

OUT = BOOK / "out" / "ch03_roll"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--days", nargs="*", default=None)
    ap.add_argument("--max-files", type=int, default=24)
    args = ap.parse_args()
    ensure_env()
    days = resolve_days(args.days)
    OUT.mkdir(parents=True, exist_ok=True)

    tob = load_hl_tob(args.symbol)
    tape = load_trades(args.symbol, days, args.max_files)
    ov = overlap_trades_with_mids(tape, tob)

    # --- disc: Roll on trade-event mid changes & calendar mid ---
    mid0 = ov["mid0"]
    ok = np.isfinite(mid0) & (mid0 > 0)
    # trade-time mid path (as-of), differenced in event time
    m_ev = mid0[ok]
    roll_event = roll_on_mid_bps(m_ev)
    # calendar 1s mid
    roll_cal = roll_on_mid_bps(tob["mid"][:: max(1, tob["mid"].size // 50_000)])
    # trade price Roll (classic Hasbrouck setting without quotes)
    px = ov["px"][ok]
    roll_px = roll_on_mid_bps(px)  # reuse mid helper on price series

    tr, te = time_split_mask(ov["ts"][ok], train_frac=0.7)
    roll_tr = roll_on_mid_bps(m_ev[tr])
    roll_te = roll_on_mid_bps(m_ev[te])

    # --- cont: noise-robust RV + volume clock ---
    noise = noise_robust_rv(tob["ts"], tob["mid"], fine_ns=100_000_000, coarse_ns=1_000_000_000)
    _, r_cal = calendar_returns(tob["ts"], tob["mid"], bar_ns=1_000_000_000)
    # volume clock: median trade qty * 50
    q = ov["qty"]
    bar_v = float(np.nanmedian(q[q > 0]) * 50) if np.any(q > 0) else 1.0
    _, r_vol = volume_clock_returns(ov["ts"], ov["px"], ov["qty"], bar_volume=bar_v)

    def _ac1(r: np.ndarray) -> float:
        r = r[np.isfinite(r)]
        if r.size < 10:
            return float("nan")
        x, y = r[1:] - r[1:].mean(), r[:-1] - r[:-1].mean()
        den = float(np.sqrt((x * x).sum() * (y * y).sum()))
        return float((x * y).sum() / den) if den > 0 else float("nan")

    # Decisions
    disc_id = bool(roll_event.get("identified"))
    # Promote disc Roll only if identified on train AND test
    promote_roll = bool(roll_tr.get("identified") and roll_te.get("identified"))
    # cont noise: Promote only if fine RV clearly inflates; else Kill (no bounce)
    nr = noise.get("noise_ratio", float("nan"))
    if np.isfinite(nr) and nr > 1.5:
        noise_dec = "Promote"
    elif np.isfinite(nr) and nr <= 1.05:
        noise_dec = "Kill"
    else:
        noise_dec = "Hold"

    decisions = {
        "disc.roll_event_mid": "Promote" if promote_roll else ("Hold" if disc_id else "Kill"),
        "disc.roll_trade_px": "Hold" if roll_px.get("identified") else "Kill",
        "cont.noise_rv_ratio": noise_dec,
        "cont.volclock_ac1": "Hold",  # descriptive clock contrast
    }
    falsifiers = {
        "disc.roll_event_mid": "γ₁≥0 on held-out half (unidentified) or spread_bps ≫ quoted",
        "disc.roll_trade_px": "γ₁≥0 (bounce absent / dominated by drift)",
        "cont.noise_rv_ratio": "RV_fine/RV_coarse ≤ 1 on dense collector (no bounce inflation)",
        "cont.volclock_ac1": "AC1 indistinguishable across calendar vs volume clocks",
    }

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": args.symbol,
        "days": days,
        "n_trades": int(ov["ts"].size),
        "n_mids": int(tob["ts"].size),
        "disc": {
            "roll_event_mid": roll_event,
            "roll_calendar_subsample": roll_cal,
            "roll_trade_px": roll_px,
            "roll_train": roll_tr,
            "roll_test": roll_te,
            "event_ac1_dmid": _ac1(np.diff(m_ev)),
        },
        "cont": {
            "noise_robust_rv": noise,
            "calendar_1s_ac1": _ac1(r_cal),
            "volclock_ac1": _ac1(r_vol),
            "volclock_bar_volume": bar_v,
            "n_vol_bars": int(r_vol.size),
            "n_cal_bars": int(np.isfinite(r_cal).sum()),
        },
        "decisions": decisions,
        "falsifiers": falsifiers,
        "lenses": {
            "disc.roll_event_mid": ["disc", "liq", "mm"],
            "disc.roll_trade_px": ["disc", "info"],
            "cont.noise_rv_ratio": ["cont", "info"],
            "cont.volclock_ac1": ["cont", "exec"],
        },
    }
    out_j = OUT / f"exp_ch03_{args.symbol.lower()}_summary.json"
    out_j.write_text(json.dumps(payload, indent=2))

    lines = [
        f"# Ch.3 / Ch.8 Roll & noise — {args.symbol}",
        "",
        f"- Days: {days} · trades={ov['ts'].size:,} · mids={tob['ts'].size:,}",
        f"- **disc** Roll event-mid identified={roll_event.get('identified')} "
        f"spread_bps={roll_event.get('spread_bps')} "
        f"train/test id={roll_tr.get('identified')}/{roll_te.get('identified')}",
        f"- **disc** Roll trade-px identified={roll_px.get('identified')} "
        f"spread_bps={roll_px.get('spread_bps')}",
        f"- **cont** noise_ratio RV_fine/RV_coarse={nr}",
        f"- **cont** AC1 calendar={payload['cont']['calendar_1s_ac1']:.4f} · "
        f"volclock={payload['cont']['volclock_ac1']}",
        "",
        "## Decisions",
        "",
    ]
    for k, v in decisions.items():
        lines.append(f"- `{k}`: **{v}** — {falsifiers[k]}")
    (OUT / f"exp_ch03_{args.symbol.lower()}_REPORT.md").write_text("\n".join(lines) + "\n")
    print((OUT / f"exp_ch03_{args.symbol.lower()}_REPORT.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
