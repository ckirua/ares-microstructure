from __future__ import annotations
#!/usr/bin/env python3
"""Ch.15 deep empirics: full EHO PIN MLE (≥20 days) + VPIN compare.

Coverage expansion (2026-09-30):
- Flat-era days (≤2026-09-10): opaque HL instrument id (catalog FNV misses).
- UTC-day clip of warehouse objects (flat files bleed across calendar days).
- Preferred-shard walk with high max_files; all-shards does NOT expand ETH
  span on thin public-md days (instrument is shard-local) — certified gap.
- Optional multi-asset / Deribit secondary panel if ETH usable <20.
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
    clip_tape_to_utc_day,
    ensure_env,
    hl_trade_instrument,
    load_trades,
    resolve_days,
)
from research.lib import (  # noqa: E402
    compare_pin_vpin,
    daily_buy_sell_counts,
    eho_pin_mle,
    pin_proxy_from_days,
    trade_intensity,
    vpin_bucket,
)

OUT15 = BOOK / "out" / "ch15_pin"
CH15 = BOOK / "chapters" / "ch15_pin"


def _load_day(symbol: str, day: str, max_files: int, prefer_shards: bool):
    return load_trades(
        symbol,
        [day],
        max_files=max_files,
        prefer_shards=prefer_shards,
        use_flat_ids=True,
        quiet=True,
    )


def _mle_block(days_bs: dict, *, min_trades: int, min_span_h: float) -> dict:
    mle = eho_pin_mle(
        days_bs,
        symmetric=False,
        delta_fixed=0.5,
        min_trades_per_day=min_trades,
        min_span_h=min_span_h,
    )
    mle_sym = eho_pin_mle(
        days_bs,
        symmetric=True,
        delta_fixed=0.5,
        min_trades_per_day=min_trades,
        min_span_h=min_span_h,
    )
    return {"free": mle, "sym": mle_sym}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--n-days", type=int, default=0, help="0 = all listing-cache days")
    ap.add_argument("--days", nargs="*", default=None)
    ap.add_argument("--max-files", type=int, default=32)
    ap.add_argument("--min-trades", type=int, default=400)
    ap.add_argument("--min-span-h", type=float, default=4.0)
    ap.add_argument("--prefer-shards", action="store_true", default=True)
    ap.add_argument("--no-prefer-shards", action="store_false", dest="prefer_shards")
    ap.add_argument(
        "--secondary",
        nargs="*",
        default=[],
        help="Extra symbols for multi-asset panel (e.g. BTC SOL) if ETH <20",
    )
    ap.add_argument("--deribit", action="store_true", help="Try Deribit ETH-PERPETUAL secondary")
    args = ap.parse_args()
    ensure_env()

    n = args.n_days if args.n_days > 0 else 10_000
    days = resolve_days(args.days, n=n, prefer_listing_cache=True)
    OUT15.mkdir(parents=True, exist_ok=True)

    certification = [
        "Flat-era (≤2026-09-10): opaque HL id from symbols.yaml hyperliquid_flat_ids "
        f"(ETH→{hl_trade_instrument('ETH','2026-09-01')}); catalog FNV(coin) empty on flat parquet.",
        "UTC-day clip of warehouse objects — flat files often bleed across calendar days; "
        "clip avoids double-counting across adjacent warehouse days.",
        "Preferred-shard tails (HL trade shard 02) + high max_files walk; "
        "all-shards does not expand ETH span on thin public-md days (instrument shard-local).",
        "Thin public-md days (e.g. 09-12/13/23/24/28/29) remain unusable — warehouse release "
        "coverage gap, not a loader miss. Not certified equity-session full-day B/S.",
    ]

    all_ts: list[np.ndarray] = []
    all_side: list[np.ndarray] = []
    all_qty: list[np.ndarray] = []
    day_meta: dict[str, dict] = {}
    seen_ts: set[int] = set()  # light dedupe across days for VPIN concat

    for day in days:
        inst = hl_trade_instrument(args.symbol, day)
        try:
            tape = _load_day(args.symbol, day, args.max_files, args.prefer_shards)
        except Exception as exc:  # noqa: BLE001
            day_meta[day] = {"error": str(exc), "n": 0, "instrument": str(inst)}
            print(f"  skip {day}: {exc}", flush=True)
            continue
        if len(tape) == 0:
            day_meta[day] = {"n": 0, "instrument": str(inst)}
            print(f"  {day}: EMPTY (inst={inst})", flush=True)
            continue
        clipped = clip_tape_to_utc_day(tape, day)
        ts = clipped["ts"]
        side = clipped["side"]
        qty = clipped["qty"]
        # Dedupe exact ns already counted (flat bleed)
        if seen_ts:
            keep = np.array([int(t) not in seen_ts for t in ts], dtype=bool)
            ts, side, qty = ts[keep], side[keep], qty[keep]
        for t in ts.tolist():
            seen_ts.add(int(t))
        labels = np.array([day] * ts.size, dtype=object)
        bs = daily_buy_sell_counts(ts, side, day_labels=labels)
        meta = dict(bs.get(day, {"B": 0, "S": 0, "n": 0, "span_h": 0.0}))
        meta["n_files"] = int(tape.n_files)
        meta["warehouse_day"] = day
        meta["instrument"] = str(inst)
        meta["utc_clipped"] = bool(clipped["clipped"])
        meta["n_raw_unclipped"] = int(clipped["n_raw"])
        day_meta[day] = meta
        all_ts.append(ts)
        all_side.append(side)
        all_qty.append(qty)
        print(
            f"  {day}: n={meta.get('n')} B={meta.get('B')} S={meta.get('S')} "
            f"span_h={float(meta.get('span_h') or 0):.2f} inst={inst} "
            f"clip={meta['utc_clipped']}",
            flush=True,
        )

    days_bs = {
        k: v
        for k, v in day_meta.items()
        if isinstance(v.get("B"), (int, float)) and int(v.get("n", 0)) > 0
    }
    proxy = pin_proxy_from_days(days_bs)
    block = _mle_block(days_bs, min_trades=args.min_trades, min_span_h=args.min_span_h)
    mle, mle_sym = block["free"], block["sym"]

    # Time-split on usable day keys (chronological)
    usable_keys = list(mle.get("day_keys") or [])
    split = {"n_usable": len(usable_keys), "early": {}, "late": {}}
    if len(usable_keys) >= 6:
        mid = len(usable_keys) // 2
        early_bs = {k: days_bs[k] for k in usable_keys[:mid] if k in days_bs}
        late_bs = {k: days_bs[k] for k in usable_keys[mid:] if k in days_bs}
        split["early"] = _mle_block(early_bs, min_trades=args.min_trades, min_span_h=0.0)
        split["late"] = _mle_block(late_bs, min_trades=args.min_trades, min_span_h=0.0)
        # min_span already satisfied for usable keys; relax span for subset MLE
        split["early_PIN"] = (split["early"]["free"] or {}).get("PIN")
        split["late_PIN"] = (split["late"]["free"] or {}).get("PIN")
        split["early_n"] = (split["early"]["free"] or {}).get("n_days")
        split["late_n"] = (split["late"]["free"] or {}).get("n_days")

    # Day-level leave-one-out PIN sd (stability)
    loo_pins: list[float] = []
    if len(usable_keys) >= 8:
        for drop in usable_keys:
            sub = {k: days_bs[k] for k in usable_keys if k != drop and k in days_bs}
            m = eho_pin_mle(
                sub,
                symmetric=False,
                delta_fixed=0.5,
                min_trades_per_day=args.min_trades,
                min_span_h=0.0,
            )
            if m.get("ok") and np.isfinite(m.get("PIN", float("nan"))):
                loo_pins.append(float(m["PIN"]))
    stability = {
        "loo_n": len(loo_pins),
        "loo_pin_mean": float(np.mean(loo_pins)) if loo_pins else float("nan"),
        "loo_pin_sd": float(np.std(loo_pins)) if loo_pins else float("nan"),
        "loo_pin_min": float(np.min(loo_pins)) if loo_pins else float("nan"),
        "loo_pin_max": float(np.max(loo_pins)) if loo_pins else float("nan"),
    }

    if all_ts:
        ts = np.concatenate(all_ts)
        side = np.concatenate(all_side)
        qty = np.concatenate(all_qty)
        order = np.argsort(ts)
        ts, side, qty = ts[order], side[order], qty[order]
        bar_v = float(np.nanmedian(qty[qty > 0]) * 50) if np.any(qty > 0) else 1.0
        vpin = vpin_bucket(side, qty, bucket_volume=bar_v, n_buckets_window=50)
        intens = trade_intensity(ts, bar_ns=1_000_000_000)
        span = {
            "ts_min": int(ts.min()),
            "ts_max": int(ts.max()),
            "n_trades": int(ts.size),
            "span_h": float((ts.max() - ts.min()) / 1e9 / 3600.0),
            "utc_start": datetime.fromtimestamp(ts.min() / 1e9, tz=timezone.utc).isoformat(),
            "utc_end": datetime.fromtimestamp(ts.max() / 1e9, tz=timezone.utc).isoformat(),
        }
    else:
        vpin = {"n_buckets": 0, "mean_vpin": float("nan")}
        intens = {"n_bars": 0, "mean_lambda": float("nan")}
        span = {}

    cmp_ = compare_pin_vpin(mle, vpin)

    usable = int(mle.get("n_days") or 0)
    pin_ok = bool(mle.get("ok")) and np.isfinite(mle.get("PIN", float("nan")))
    pin_delta = (
        abs(float(mle["PIN"]) - float(mle_sym.get("PIN", float("nan"))))
        if pin_ok and mle_sym.get("ok")
        else float("nan")
    )
    pin_stable = pin_ok and bool(mle_sym.get("ok")) and pin_delta < 0.15
    split_ok = True
    if np.isfinite(split.get("early_PIN", float("nan"))) and np.isfinite(
        split.get("late_PIN", float("nan"))
    ):
        split_ok = abs(float(split["early_PIN"]) - float(split["late_PIN"])) < 0.25

    if usable >= 20 and pin_stable and 0.0 < float(mle["PIN"]) < 1.0 and split_ok:
        pin_dec = "Promote"
    elif usable >= 10 and pin_ok and 0.0 < float(mle["PIN"]) < 1.0:
        pin_dec = "Hold"
    else:
        pin_dec = "Hold"

    promote_vpin = bool(
        vpin.get("n_buckets", 0) >= 20 and np.isfinite(vpin.get("mean_vpin", float("nan")))
    )
    promote_int = bool(
        intens.get("n_bars", 0) >= 30 and np.isfinite(intens.get("mean_lambda", float("nan")))
    )

    # Secondary panels only if still short of 20
    secondary: dict[str, Any] = {}
    if usable < 20:
        for sym in args.secondary or ["BTC", "SOL"]:
            if sym.upper() == args.symbol.upper():
                continue
            sec_meta: dict[str, dict] = {}
            for day in days:
                try:
                    tape = _load_day(sym, day, min(args.max_files, 24), args.prefer_shards)
                except Exception as exc:  # noqa: BLE001
                    sec_meta[day] = {"error": str(exc), "n": 0}
                    continue
                if len(tape) == 0:
                    continue
                clipped = clip_tape_to_utc_day(tape, day)
                labels = np.array([day] * clipped["ts"].size, dtype=object)
                bs = daily_buy_sell_counts(clipped["ts"], clipped["side"], day_labels=labels)
                sec_meta[day] = dict(bs.get(day, {"n": 0}))
            sec_bs = {
                k: v
                for k, v in sec_meta.items()
                if isinstance(v.get("B"), (int, float)) and int(v.get("n", 0)) > 0
            }
            sec_mle = eho_pin_mle(
                sec_bs,
                symmetric=False,
                delta_fixed=0.5,
                min_trades_per_day=args.min_trades,
                min_span_h=args.min_span_h,
            )
            secondary[sym] = {
                "label": f"HL {sym} secondary panel (not pooled with ETH)",
                "n_days_with_tape": len(sec_bs),
                "n_days_mle_usable": sec_mle.get("n_days"),
                "PIN": sec_mle.get("PIN"),
                "ok": sec_mle.get("ok"),
            }
        if args.deribit:
            from startarb.data.trades import load_trade_tape

            d_days = resolve_days(None, venue="deribit", n=40, prefer_listing_cache=True)
            d_meta: dict[str, dict] = {}
            for day in d_days:
                try:
                    tape = load_trade_tape(
                        "deribit",
                        "ETH-PERPETUAL",
                        [day],
                        max_files=min(args.max_files, 32),
                        quiet=True,
                    )
                except Exception as exc:  # noqa: BLE001
                    d_meta[day] = {"error": str(exc), "n": 0}
                    continue
                if len(tape) == 0:
                    continue
                clipped = clip_tape_to_utc_day(tape, day)
                labels = np.array([day] * clipped["ts"].size, dtype=object)
                bs = daily_buy_sell_counts(clipped["ts"], clipped["side"], day_labels=labels)
                d_meta[day] = dict(bs.get(day, {"n": 0}))
            d_bs = {
                k: v
                for k, v in d_meta.items()
                if isinstance(v.get("B"), (int, float)) and int(v.get("n", 0)) > 0
            }
            d_mle = eho_pin_mle(
                d_bs,
                symmetric=False,
                delta_fixed=0.5,
                min_trades_per_day=max(200, args.min_trades // 2),
                min_span_h=args.min_span_h,
            )
            secondary["deribit_ETH-PERPETUAL"] = {
                "label": "Deribit ETH-PERPETUAL secondary (not pooled with HL)",
                "n_days_with_tape": len(d_bs),
                "n_days_mle_usable": d_mle.get("n_days"),
                "PIN": d_mle.get("PIN"),
                "ok": d_mle.get("ok"),
            }

    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": args.symbol,
        "days_requested": days,
        "sample_span": span,
        "day_meta": day_meta,
        "n_days_with_tape": int(len(days_bs)),
        "n_days_mle_usable": usable,
        "certification": certification,
        "disc_pin_proxy": proxy,
        "disc_pin_eho_mle": mle,
        "disc_pin_eho_mle_symmetric": mle_sym,
        "pin_free_vs_sym_abs": pin_delta,
        "time_split": {
            "early_PIN": split.get("early_PIN"),
            "late_PIN": split.get("late_PIN"),
            "early_n": split.get("early_n"),
            "late_n": split.get("late_n"),
            "split_ok_abs_lt_0.25": split_ok,
        },
        "day_loo_stability": stability,
        "cont_vpin": vpin,
        "cont_intensity": intens,
        "pin_vs_vpin": cmp_,
        "secondary_panels": secondary,
        "decisions": {
            "disc.pin_eho_mle": pin_dec,
            "disc.pin_proxy_dayimb": "Hold",
            "cont.vpin": "Promote" if promote_vpin else "Hold",
            "cont.trade_intensity": "Promote" if promote_int else "Hold",
        },
        "falsifiers": {
            "disc.pin_eho_mle": (
                "<20 usable days (span/trades filters), MLE fail, "
                "|PIN_free−PIN_sym|≥0.15, or early/late |ΔPIN|≥0.25 → Hold"
            ),
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
        "blockers": [],
    }
    if usable < 20:
        summary["blockers"].append(
            f"Only {usable} usable days after min_trades={args.min_trades} "
            f"min_span_h={args.min_span_h} (requested {len(days)}; "
            f"thin public-md days are a warehouse coverage ceiling)."
        )
    if not pin_ok:
        summary["blockers"].append(f"MLE not ok: {mle.get('message')}")
    if pin_ok and not pin_stable:
        summary["blockers"].append(
            f"PIN free={mle.get('PIN'):.4f} vs symmetric={mle_sym.get('PIN')} "
            f"|Δ|={pin_delta:.4f} ≥0.15"
        )
    if not split_ok:
        summary["blockers"].append(
            f"Time-split unstable: early={split.get('early_PIN')} late={split.get('late_PIN')}"
        )

    (OUT15 / f"exp_ch15_{args.symbol.lower()}_summary.json").write_text(
        json.dumps(summary, indent=2, default=str)
    )
    (CH15 / "EXP_REPORT.md").parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Ch.15 PIN / VPIN / intensity — {args.symbol} (deep)",
        "",
        f"- Sample: {span.get('utc_start')} → {span.get('utc_end')} "
        f"({span.get('span_h', float('nan')):.1f}h, n_trades={span.get('n_trades')})",
        f"- Days requested={len(days)} · with tape={len(days_bs)} · MLE usable={usable}",
        f"- PIN MLE={mle.get('PIN')} (α={mle.get('alpha')}, μ={mle.get('mu')}, "
        f"εb={mle.get('eps_b')}, εs={mle.get('eps_s')})",
        f"- PIN symmetric-ε={mle_sym.get('PIN')} · |Δ|={pin_delta} · proxy={proxy.get('pin_proxy')}",
        f"- Time-split early={split.get('early_PIN')} (n={split.get('early_n')}) · "
        f"late={split.get('late_PIN')} (n={split.get('late_n')}) · ok={split_ok}",
        f"- LOO stability mean={stability['loo_pin_mean']} sd={stability['loo_pin_sd']} "
        f"(n={stability['loo_n']})",
        f"- VPIN mean={vpin.get('mean_vpin')} n_buckets={vpin.get('n_buckets')}",
        f"- Intensity λ={intens.get('mean_lambda')} /s · ac1={intens.get('count_ac1')}",
        "",
        "## Certification",
    ]
    for c in certification:
        lines.append(f"- {c}")
    lines += ["", "## Decisions"]
    for k, v in summary["decisions"].items():
        lines.append(f"- `{k}`: **{v}**")
    if summary["blockers"]:
        lines += ["", "## Blockers"]
        for b in summary["blockers"]:
            lines.append(f"- {b}")
    if secondary:
        lines += ["", "## Secondary panels (not pooled)"]
        for k, v in secondary.items():
            lines.append(
                f"- `{k}`: usable={v.get('n_days_mle_usable')} PIN={v.get('PIN')} — {v.get('label')}"
            )
    report = "\n".join(lines) + "\n"
    (OUT15 / f"exp_ch15_{args.symbol.lower()}_REPORT.md").write_text(report)
    (CH15 / "EXP_REPORT.md").write_text(report)
    print(report, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
