#!/usr/bin/env python3
"""Ch.18–21 Part III limit-order empirics (Hasbrouck notes).

Public-tape proxies — no OE fills. L0 collector TOB + warehouse trades +
cached multilevel ``l2_snapshot_level`` for Sandas L1 depth moments.
Themes: size-at-touch / cancel proxies, Sandas depth schedule, CMSW hit
times, Foucault pick-off, Parlour crowding, disc vs cont LO-event clocks.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path("/home/dev/srv/ares-startarb") / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import (  # noqa: E402
    ensure_env,
    load_hl_l2_levels,
    load_hl_tob,
    load_trades,
    normalize_side,
    overlap_trades_with_mids,
    resolve_days,
)
from research.lib import (  # noqa: E402
    depth_imbalance,
    improve_adverse_markout,
    lob_event_clocks,
    parlour_depth_aggressor,
    qty_moment_ceiling,
    same_side_refill,
    sandas_depth_moments,
    size_at_touch_survival,
    time_split_mask,
    time_to_touch,
    tob_depletion_cancel_proxy,
    tob_resilience,
    trade_markouts,
)

OUT = BOOK / "out" / "ch18_limit_orders"
CHAP = BOOK / "chapters" / "ch18_limit_orders"


def _r_sign(r: dict, expect_pos: bool) -> bool:
    if not np.isfinite(r.get("r", float("nan"))):
        return False
    lo, hi = r.get("lo", float("nan")), r.get("hi", float("nan"))
    if not (np.isfinite(lo) and np.isfinite(hi)):
        return False
    if expect_pos:
        return lo > 0
    return hi < 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--days", nargs="*", default=None)
    ap.add_argument("--max-files", type=int, default=32)
    ap.add_argument("--max-rows", type=int, default=400_000)
    ap.add_argument("--l2-files", type=int, default=60)
    args = ap.parse_args()

    ensure_env()
    days = resolve_days(args.days, n=3)
    OUT.mkdir(parents=True, exist_ok=True)

    tob = load_hl_tob(args.symbol, max_rows=args.max_rows)
    tape = load_trades(args.symbol, days, args.max_files)
    ov = overlap_trades_with_mids(tape, tob)
    side = normalize_side(ov["side"])
    ok = np.isfinite(side) & (side != 0) & np.isfinite(ov["px"])
    ts_tr = ov["ts"][ok]
    side_tr = side[ok]
    px_tr = ov["px"][ok]
    qty_tr = ov["qty"][ok]

    depth = tob["bid_sz"] + tob["ask_sz"]
    imb = depth_imbalance(tob["bid_sz"], tob["ask_sz"])

    touch = time_to_touch(
        tob["ts"],
        tob["bid"],
        tob["ask"],
        offsets_ticks=(0, 1, 2),
        max_horizon_ms=30_000,
        sample_stride=40,
        side="buy",
    )
    size_surv = size_at_touch_survival(
        tob["ts"],
        tob["bid"],
        tob["ask"],
        tob["bid_sz"],
        tob["ask_sz"],
        ts_tr,
        side_tr,
        qty_tr,
        offsets_ticks=(0, 1),
        size_quantiles=(0.25, 0.5, 0.75),
        max_horizon_ms=30_000,
        sample_stride=100,
        side="buy",
    )
    cancel_px = tob_depletion_cancel_proxy(
        tob["ts"],
        tob["bid"],
        tob["ask"],
        tob["bid_sz"],
        tob["ask_sz"],
        ts_tr,
        side_tr,
        qty_tr,
        drop_frac=0.2,
        trade_match_ms=250,
    )
    refill = same_side_refill(
        tob["ts"],
        tob["bid"],
        tob["ask"],
        tob["bid_sz"],
        tob["ask_sz"],
        drop_frac=0.3,
        horizons_ms=(100, 500, 1000, 5000),
    )
    pickoff = improve_adverse_markout(
        tob["ts"],
        tob["bid"],
        tob["ask"],
        tob["mid"],
        horizons_ms=(100, 500, 1000, 5000),
    )
    parlour = parlour_depth_aggressor(
        ts_tr, side_tr, tob["ts"], tob["bid_sz"], tob["ask_sz"]
    )
    clocks = lob_event_clocks(
        tob["ts"], tob["bid"], tob["ask"], tob["bid_sz"], tob["ask_sz"]
    )
    mid = tob["mid"]
    mid_ret = np.zeros_like(mid)
    mid_ret[1:] = np.abs(np.diff(mid) / np.maximum(mid[:-1], 1e-12))
    big = np.where(mid_ret > np.nanpercentile(mid_ret[mid_ret > 0], 95))[0]
    ev_ts = tob["ts"][big] if big.size else tob["ts"][:: max(1, tob["ts"].size // 200)]
    res_trade = tob_resilience(
        tob["ts"], mid, depth, ts_tr[:: max(1, ts_tr.size // 800)], horizons_ms=(100, 500, 1000, 5000)
    )
    res_jump = tob_resilience(
        tob["ts"], mid, depth, ev_ts[:2000], horizons_ms=(100, 500, 1000, 5000)
    )

    mo = trade_markouts(
        ts_tr, px_tr, side_tr, tob["ts"], mid, horizons_ms=(100, 500, 1000, 5000)
    )

    train, test = time_split_mask(tob["ts"], train_frac=0.7)
    pick_train = improve_adverse_markout(
        tob["ts"][train],
        tob["bid"][train],
        tob["ask"][train],
        mid[train],
        horizons_ms=(1000,),
    )
    pick_test = improve_adverse_markout(
        tob["ts"][test],
        tob["bid"][test],
        tob["ask"][test],
        mid[test],
        horizons_ms=(1000,),
    )

    l2 = load_hl_l2_levels(args.symbol, max_files=args.l2_files)
    sandas = sandas_depth_moments(
        l2["ts"],
        l2["side"],
        l2["level"],
        l2["qty"],
        l2["price_ticks"],
        l2["snapshot_id"],
        max_level=5,
        ask_level_offset=20,
    )
    qty_mom = qty_moment_ceiling(qty_tr)

    t0 = touch["by_offset"].get("0", {})
    t1 = touch["by_offset"].get("1", {})
    touch_ok = (
        t0.get("n_starts", 0) >= 50
        and np.isfinite(t0.get("touch_rate", float("nan")))
        and t0["touch_rate"] > t1.get("touch_rate", 1.0)
    )
    rates = [touch["by_offset"].get(str(k), {}).get("touch_rate", float("nan")) for k in (0, 1, 2)]
    mono = all(
        np.isfinite(rates[i]) and np.isfinite(rates[i + 1]) and rates[i] >= rates[i + 1] - 1e-9
        for i in range(len(rates) - 1)
    )

    r1s = refill["sides"].get("bid", {}).get("by_horizon", {}).get("1000", {})
    refill_rate = r1s.get("refill_rate", float("nan"))
    refill_dec = (
        "Promote"
        if (r1s.get("n", 0) >= 30 and np.isfinite(refill_rate) and refill_rate > 0.05)
        else "Hold"
    )

    p1 = pickoff["by_horizon"].get("1000", {})
    pick_lo = p1.get("ci95", [float("nan")] * 2)[0]
    pick_hi = p1.get("ci95", [float("nan")] * 2)[1]
    pt = pick_test["by_horizon"].get("1000", {})
    pt_lo = pt.get("ci95", [float("nan")] * 2)[0]
    if (
        p1.get("n", 0) >= 50
        and np.isfinite(pick_hi)
        and pick_hi < 0
        and np.isfinite(pt_lo)
        and pt.get("n", 0) >= 30
    ):
        pick_dec = "Kill"
    elif (
        p1.get("n", 0) >= 50
        and np.isfinite(pick_lo)
        and pick_lo > 0
        and np.isfinite(pt_lo)
        and pt_lo > 0
    ):
        pick_dec = "Promote"
    else:
        pick_dec = "Hold"

    parlour_dec = "Hold"
    if parlour.get("ok"):
        same_ok = _r_sign(parlour["same_ask_vs_sell"], True) or _r_sign(
            parlour["same_bid_vs_buy"], True
        )
        if same_ok and parlour["n"] >= 200:
            parlour_dec = "Promote"

    clock_dec = (
        "Promote"
        if clocks["n_events"] >= 200
        and np.isfinite(clocks["cont_intensity"].get("mean_lambda", float("nan")))
        else "Hold"
    )

    res_n = res_trade.get("n_events", [0])[2] if res_trade.get("n_events") else 0
    res_ratio = (
        res_trade.get("mean_depth_ratio", [float("nan")])[2]
        if res_trade.get("mean_depth_ratio")
        else float("nan")
    )
    res_dec = (
        "Promote"
        if res_n >= 50 and np.isfinite(res_ratio) and abs(res_ratio - 1.0) > 0.05
        else "Hold"
    )

    touch_dec = "Promote" if (touch_ok and mono) else "Hold"

    s0 = size_surv.get("by_offset", {}).get("0", {})
    size_dec = "Hold"
    if (
        s0.get("n_starts", 0) >= 50
        and np.isfinite(s0.get("fill_proxy_rate", float("nan")))
        and size_surv.get("size_monotone_lower_fill")
    ):
        size_dec = "Promote"
    elif (
        s0.get("n_starts", 0) >= 80
        and np.isfinite(s0.get("fill_proxy_rate", float("nan")))
        and 0.02 < s0["fill_proxy_rate"] < 0.98
    ):
        size_dec = "Promote"

    pool = cancel_px.get("pooled", {})
    cancel_dec = (
        "Promote"
        if (
            pool.get("n_events", 0) >= 100
            and np.isfinite(pool.get("cancel_proxy_share", float("nan")))
            and pool["cancel_proxy_share"] > 0.05
            and np.isfinite(pool.get("fill_proxy_share", float("nan")))
            and pool["fill_proxy_share"] > 0.02
        )
        else "Hold"
    )

    sandas_dec = "Hold"
    if sandas.get("ok") and sandas.get("n_snapshots", 0) >= 30:
        behind = sandas.get("mean_behind_touch_decay", float("nan"))
        if np.isfinite(behind) and behind > 0.1:
            sandas_dec = "Promote"

    qty_dec = "Hold"
    if qty_mom.get("ok"):
        infl = qty_mom.get("var_inflation_0p995_over_0p9", float("nan"))
        if np.isfinite(infl) and infl >= 1.5:
            qty_dec = "Promote"
        elif np.isfinite(infl):
            qty_dec = "Kill"

    decisions = {
        "cont.time_to_touch": touch_dec,
        "cont.size_touch_survival": size_dec,
        "cont.tob_cancel_proxy": cancel_dec,
        "cont.same_side_refill": refill_dec,
        "info.improve_markout": pick_dec,
        "disc.parlour_depth_side": parlour_dec,
        "cont.lob_event_intensity": clock_dec,
        "disc.lob_event_ac1": (
            "Promote"
            if clocks["n_events"] >= 200
            and np.isfinite(clocks.get("disc_event_ac1", float("nan")))
            else "Hold"
        ),
        "mm.book_resilience_lo": res_dec,
        "disc.sandas_depth_moments": sandas_dec,
        "disc.qty_moment_ceiling": qty_dec,
        "mm.queue_value_tick": "Hold",
        "mm.limit_fill_hazard_oe": "Hold",
        "theory.sandas_gmm_multilevel": "Hold",
        "theory.stoll_cara_bid": "Hold",
        "theory.cmsw_optimal_L": "Hold",
        "theory.foucault_parlour_eq": "Hold",
    }

    falsifiers = {
        "cont.time_to_touch": "touch_rate not decreasing in tick offset, or n_starts<50",
        "cont.size_touch_survival": "fill_proxy_rate flat/empty or n_starts<50",
        "cont.tob_cancel_proxy": "cancel_proxy_share≈0 or fill_proxy_share≈0 or n<100",
        "cont.same_side_refill": "refill_rate@1s ≈ 0 (Sandas conj.1 holds) or n<30",
        "info.improve_markout": "pick-off claim: CI≤0 (continuation) → Kill; Promote only if held-out CI>0",
        "disc.parlour_depth_side": "same-side depth–aggressor corr CI∋0 both sides",
        "cont.lob_event_intensity": "λ̂ undefined / n_events<200",
        "disc.lob_event_ac1": "n_events<200 or ac1 undefined",
        "mm.book_resilience_lo": "depth_ratio@1s≈1 or n_events<50",
        "disc.sandas_depth_moments": "no multilevel L2 / behind-touch decay≈0 / n_snap<30",
        "disc.qty_moment_ceiling": "trunc-var inflation <1.5 (no Gabaix-style volume ceiling)",
        "mm.queue_value_tick": "L0 only — no queue position (needs multi-level + OE)",
        "mm.limit_fill_hazard_oe": "no OE fill tape (startarb OE dry-run / SHM only)",
        "theory.sandas_gmm_multilevel": "need structural GMM break-even Q_k vs impact (L1 moments ≠ GMM)",
        "theory.stoll_cara_bid": "utility/risk-aversion not identified from public tape",
        "theory.cmsw_optimal_L": "agent-level EU; only touch proxies ship",
        "theory.foucault_parlour_eq": "equilibrium welfare / one-shot LO; empirics are reduced-form",
    }

    lenses = {
        "cont.time_to_touch": ["cont", "exec", "mm"],
        "cont.size_touch_survival": ["cont", "exec", "mm"],
        "cont.tob_cancel_proxy": ["cont", "exec", "mm"],
        "cont.same_side_refill": ["cont", "mm", "liq"],
        "info.improve_markout": ["info", "mm", "exec"],
        "disc.parlour_depth_side": ["disc", "mm", "exec"],
        "cont.lob_event_intensity": ["cont", "exec", "mm"],
        "disc.lob_event_ac1": ["disc", "mm"],
        "mm.book_resilience_lo": ["mm", "liq", "cont"],
        "disc.sandas_depth_moments": ["disc", "mm", "info", "liq"],
        "disc.qty_moment_ceiling": ["disc", "exec", "liq"],
        "mm.queue_value_tick": ["mm", "disc"],
        "mm.limit_fill_hazard_oe": ["mm", "exec"],
    }

    data_ceilings = {
        "oe_fills": (
            "startarb/oe is dry_gateway + SHM rings only — no historical own-order fill/cancel tape"
        ),
        "mercat_collectors": "xarb_collector TOB is L0; no OE ack stream in results/xarb_md",
        "l2_multilevel": (
            f"HL l2_snapshot_level depth>1 AVAILABLE (cache files={l2.get('n_files')}, "
            f"rows={l2['ts'].size}, snaps≈{sandas.get('n_snapshots')}, ask_level_offset=20) "
            "— L1 moments ship; full Sandas GMM still blocked (no structural break-even ID)"
        ),
        "warehouse_l2_cadence": "~snapshot/delta rebuild ~5s — not ms HFT book",
    }

    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": args.symbol,
        "days": days,
        "n_tob": int(tob["ts"].size),
        "n_trades": int(ts_tr.size),
        "mean_abs_imbalance": float(np.nanmean(np.abs(imb))),
        "time_to_touch": touch,
        "size_at_touch_survival": size_surv,
        "tob_depletion_cancel_proxy": cancel_px,
        "same_side_refill": refill,
        "improve_markout": pickoff,
        "improve_markout_split": {"train_1s": pick_train, "test_1s": pick_test},
        "parlour": parlour,
        "lob_clocks": clocks,
        "resilience_trade": res_trade,
        "resilience_jump": res_jump,
        "markouts": mo,
        "sandas_depth_moments": sandas,
        "qty_moment_ceiling": qty_mom,
        "l2_meta": {
            "n_files": l2.get("n_files"),
            "n_rows": int(l2["ts"].size),
            "instrument_id": l2.get("instrument_id_target"),
        },
        "decisions": decisions,
        "falsifiers": falsifiers,
        "lenses": lenses,
        "data_ceilings": data_ceilings,
        "theory_gaps": [
            "True OE fill/cancel hazard (needs own-order feedback) — public-tape proxies shipped",
            "Sandas GMM multilevel break-even schedule (L1 moments shipped; structural GMM Hold)",
            "Stoll CARA bid markdown (unobserved risk aversion / inventory)",
            "CMSW optimal limit price via EU (agent preferences)",
            "Foucault/Parlour structural equilibrium / welfare",
            "Seppi dealer quantity-improvement (no hybrid specialist on HL)",
            "Multi-level queue position / time priority (L0/Lk size ≠ queue rank)",
        ],
        "ch5_6_bridge": (
            "Ch.5–6 sequential/strategic info → permanent impact & spreads; "
            "Part III picking-off is the *public*-news free-option analogue — "
            "info.improve_markout + trade markouts share the adverse-selection lens. "
            "Ch.9 GMM toolkit still reserved for structural Sandas; L1 depth moments use "
            "reduced-form Corr(cumQ,|Δmid|)."
        ),
        "ch00_dig": (
            "Ch.0/2 finite-moment caution (Gabaix et al.) → disc.qty_moment_ceiling on trade size."
        ),
    }

    tag = args.symbol.lower()
    sum_path = OUT / f"exp_ch18_{tag}_summary.json"
    sum_path.write_text(json.dumps(summary, indent=2, default=str))

    s25 = size_surv.get("by_size_q", {}).get("0.25", {})
    s75 = size_surv.get("by_size_q", {}).get("0.75", {})
    lines = [
        f"# Ch.18–21 limit-order empirics — {args.symbol}",
        "",
        f"- Days: {days}",
        f"- TOB rows: **{tob['ts'].size:,}** · trades overlap: **{ts_tr.size:,}**",
        f"- Touch@0ticks rate: **{t0.get('touch_rate', float('nan')):.3f}** "
        f"(mean touch {t0.get('mean_touch_ms', float('nan')):.0f} ms) · "
        f"@1tick **{t1.get('touch_rate', float('nan')):.3f}**",
        f"- Size-touch fill_proxy@L0: **{s0.get('fill_proxy_rate', float('nan')):.3f}** "
        f"(q25={s25.get('fill_proxy_rate', float('nan')):.3f}, "
        f"q75={s75.get('fill_proxy_rate', float('nan')):.3f}; "
        f"size_mono={size_surv.get('size_monotone_lower_fill')})",
        f"- TOB cancel_proxy share: **{pool.get('cancel_proxy_share', float('nan')):.3f}** · "
        f"fill_proxy **{pool.get('fill_proxy_share', float('nan')):.3f}** (n={pool.get('n_events', 0)})",
        f"- Bid refill@1s: **{refill_rate:.3f}** (n={r1s.get('n', 0)})",
        f"- Improve adverse markout 1s: **{p1.get('mean_adverse_bps', float('nan')):.4f}** bps "
        f"CI {p1.get('ci95')} · n={p1.get('n', 0)}",
        f"- Parlour same ask↔sell r: {parlour.get('same_ask_vs_sell', {})}",
        f"- LO events: **{clocks['n_events']}** · "
        f"λ̂={clocks['cont_intensity'].get('mean_lambda', float('nan')):.3f}/s · "
        f"disc ac1={clocks.get('disc_event_ac1', float('nan')):.3f}",
        f"- Resilience depth_ratio@1s (trade): **{res_ratio}** n={res_n}",
        f"- Sandas L1: snaps={sandas.get('n_snapshots')} · "
        f"pooled_decay={sandas.get('pooled_decay_Qk_over_Q0')} · "
        f"behind={sandas.get('mean_behind_touch_decay')}",
        f"- Qty moment ceiling: var_infl(0.995/0.9)="
        f"**{qty_mom.get('var_inflation_0p995_over_0p9', float('nan')):.3f}** n={qty_mom.get('n')}",
        "",
        "## Decisions",
        "",
    ]
    for k, v in decisions.items():
        lines.append(f"- `{k}`: **{v}**")
    lines.extend(["", "## Data ceilings", ""])
    for k, v in data_ceilings.items():
        lines.append(f"- **{k}:** {v}")
    lines.extend(["", "## Theory-only (explicit gaps)", ""])
    for g in summary["theory_gaps"]:
        lines.append(f"- {g}")
    lines.extend(["", f"JSON: `{sum_path.name}`", ""])
    rep_path = OUT / f"exp_ch18_{tag}_REPORT.md"
    rep_path.write_text("\n".join(lines))

    CHAP.mkdir(parents=True, exist_ok=True)
    (CHAP / "EXP_REPORT.md").write_text("\n".join(lines))

    print(rep_path.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
