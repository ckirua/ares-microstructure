"""Shadow fills against tape/TOB using strategy_lab maker sim."""


from __future__ import annotations

import os

import sys
from pathlib import Path
from typing import Any

import numpy as np

PKG = Path(__file__).resolve().parents[1]
APP = PKG.parent
BOOK = APP.parent
ROOT = BOOK.parents[2]
STARTARB = Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb'))
LAB = APP / "strategy_lab"

for p in (str(LAB), str(ROOT), str(STARTARB / "src"), str(BOOK / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from _data import normalize_side  # noqa: E402
from sim.book import book_meta, load_best_book  # noqa: E402
from sim.engine import SimConfig, run_tick_sim  # noqa: E402
from sim.metrics import equity_stats  # noqa: E402
from strategies import (  # noqa: E402
    BaselineMaker,
    KillLadderOverlay,
    LadderPlusConfirmBeforeRestore,
    build_event_clock,
)

from .risk_stack import (  # noqa: E402
    RiskGateStackOverlay,
    build_risk_gate_clock,
    clock_regime_counts,
)

NS = 1_000_000_000
FIRE_REGIMES = frozenset({
    "widen",
    "size_cap",
    "halt",
    "halt_flatten",
    "ladder_halt",
    "ladder_await_confirm",
    "ladder_confirm_restore",
    "ladder_stay_wide",
    "ladder_v_restore",
    "nest_hard_pause",
    "fire_pause_5m",
})


def assert_fills_on_tape(sim_result: dict[str, Any]) -> None:
    """Integrity: every shadow fill books at the trade print, not asof bid/ask.

    Same rule as strategy_lab (warehouse TOB can be minutes-stale).
    """
    fpx = np.asarray(sim_result.get("fill_px", []), dtype=np.float64)
    fi = np.asarray(sim_result.get("fill_i", []), dtype=np.int64)
    px = np.asarray(sim_result["px"], dtype=np.float64)
    ts = np.asarray(sim_result["ts"], dtype=np.int64)
    fts = np.asarray(sim_result.get("fill_ts", []), dtype=np.int64)
    if fpx.size == 0:
        return
    if fi.size != fpx.size:
        raise AssertionError(f"fill_i len {fi.size} != fill_px len {fpx.size}")
    for j in range(fpx.size):
        i = int(fi[j])
        if i < 0 or i >= px.size:
            raise AssertionError(f"fill[{j}] fill_i={i} out of range n={px.size}")
        if not np.isclose(px[i], fpx[j], rtol=0.0, atol=1e-6):
            raise AssertionError(
                f"fill[{j}] px={fpx[j]} != tape[{i}]={px[i]} — must book at trade print"
            )
        if int(ts[i]) != int(fts[j]):
            raise AssertionError(
                f"fill[{j}] ts={fts[j]} != tape[{i}] ts={ts[i]}"
            )


def _downsample(tape: dict[str, np.ndarray], max_trades: int) -> dict[str, np.ndarray]:
    n = int(tape["ts"].size)
    if n <= max_trades:
        return tape
    step = int(np.ceil(n / max_trades))
    idx = np.arange(0, n, step)
    return {k: (v[idx] if isinstance(v, np.ndarray) and v.shape == (n,) else v) for k, v in tape.items()}


def _tape_proxy_book(
    px: np.ndarray,
    *,
    half_spread_bps: float = 0.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Synthetic touch around trade print when warehouse BBO is too stale for fills.

    half_spread_bps must be **0** for maker eligibility: engine requires print to
    reach asof bid/ask; a positive synthetic spread puts every print *inside*
    the quote and yields zero fills. Mark still uses mid (=px); fill_px = tape.
    """
    px = np.asarray(px, dtype=np.float64)
    if float(half_spread_bps) <= 0:
        return px.copy(), px.copy(), px.copy()
    half = np.maximum(px, 1e-12) * (float(half_spread_bps) * 1e-4)
    return px - half, px + half, px.copy()


def _fills_by_regime(sim_result: dict[str, Any]) -> dict[str, int]:
    regime = np.asarray(sim_result.get("regime", []), dtype=object)
    fi = np.asarray(sim_result.get("fill_i", []), dtype=np.int64)
    counts: dict[str, int] = {}
    for i in fi:
        if 0 <= int(i) < regime.size:
            key = str(regime[int(i)])
            counts[key] = counts.get(key, 0) + 1
    return counts


def _qty_by_regime(sim_result: dict[str, Any]) -> dict[str, float]:
    regime = np.asarray(sim_result.get("regime", []), dtype=object)
    fi = np.asarray(sim_result.get("fill_i", []), dtype=np.int64)
    fq = np.asarray(sim_result.get("fill_qty", []), dtype=np.float64)
    out: dict[str, float] = {}
    for j, i in enumerate(fi):
        if 0 <= int(i) < regime.size and j < fq.size:
            key = str(regime[int(i)])
            out[key] = out.get(key, 0.0) + float(fq[j])
    return out


def _fire_mask(regime: np.ndarray) -> np.ndarray:
    return np.asarray([str(r) in FIRE_REGIMES or str(r) in ("widen", "size_cap", "halt") for r in regime], dtype=bool)


def _crash_window_stats(sim_result: dict[str, Any], clock_tier: np.ndarray) -> dict[str, Any]:
    """Metrics restricted to ladder fire windows (tier ∈ widen/size_cap/halt)."""
    regime = np.asarray(sim_result.get("regime", []), dtype=object)
    # Prefer clock tier (shared across strategies) so baseline is scored on same windows
    fire = np.asarray(
        [str(t) in ("widen", "size_cap", "halt") for t in clock_tier],
        dtype=bool,
    )
    if fire.size != regime.size:
        fire = _fire_mask(regime)
    eq = np.asarray(sim_result.get("equity_bps", []), dtype=np.float64)
    inv = np.asarray(sim_result.get("inventory", []), dtype=np.float64)
    fi = np.asarray(sim_result.get("fill_i", []), dtype=np.int64)
    fq = np.asarray(sim_result.get("fill_qty", []), dtype=np.float64)

    n_fire_prints = int(fire.sum())
    n_fills_fire = int(sum(1 for i in fi if 0 <= int(i) < fire.size and fire[int(i)]))
    qty_fire = float(
        sum(float(fq[j]) for j, i in enumerate(fi) if j < fq.size and 0 <= int(i) < fire.size and fire[int(i)])
    )
    if eq.size and fire.any():
        d = np.diff(eq, prepend=eq[0] if eq.size else 0.0)
        equity_incr_fire = float(d[fire].sum())
        # local DD on fire-concatenated path is noisy; report peak |inv| in fire
        peak_abs_inv_fire = float(np.max(np.abs(inv[fire]))) if inv.size == fire.size else float("nan")
    else:
        equity_incr_fire = 0.0 if n_fire_prints == 0 else float("nan")
        peak_abs_inv_fire = float("nan")

    return {
        "n_fire_prints": n_fire_prints,
        "n_fills_in_fire": n_fills_fire,
        "qty_in_fire": qty_fire,
        "equity_incr_fire_bps": equity_incr_fire,
        "peak_abs_inv_fire": peak_abs_inv_fire,
        "fills_by_regime": _fills_by_regime(sim_result),
        "qty_by_regime": _qty_by_regime(sim_result),
    }


def run_shadow(
    cell: dict[str, Any],
    *,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Run baseline + kill-ladder (+ optional confirm) makers; return paths + fill logs."""
    tape = cell["tape"]
    ts = np.asarray(tape["ts"], dtype=np.int64)
    px = np.asarray(tape["px"], dtype=np.float64)
    qty = np.asarray(tape["qty"], dtype=np.float64)
    side = normalize_side(tape["side"])

    book = None
    bmeta: dict[str, Any] = {"source": "none"}
    try:
        book = load_best_book(cell["venue"], cell["symbol"], cell["day"])
        bmeta = book_meta(book) if book is not None else bmeta
    except Exception as exc:  # noqa: BLE001
        bmeta = {"source": "error", "error": f"{type(exc).__name__}: {exc}"}

    stale_s = float(cfg.get("stale_book_s", 5.0))
    # Default 0 — positive half-spread makes prints unreachable (zero fills).
    half_bps = float(cfg.get("tape_proxy_half_spread_bps", 0.0))
    fill_model = "warehouse_asof"
    if book is not None:
        asof = book.asof(ts)
        bid, ask, mid = asof["bid"], asof["ask"], asof["mid"]
        med = bmeta.get("median_dt_s")
        # Minute-scale L2 cannot gate fills into crash windows → overlay ≡ baseline.
        # Fall back to tape-proxy touch so ladder size/pull actually binds on the print clock.
        if med is None or (isinstance(med, (int, float)) and (not np.isfinite(med) or float(med) > stale_s)):
            bid, ask, mid = _tape_proxy_book(px, half_spread_bps=half_bps)
            fill_model = "tape_proxy_stale_bbo_fallback"
            bmeta = dict(bmeta)
            bmeta["fill_model"] = fill_model
            bmeta["stale_book_s"] = stale_s
            bmeta["tape_proxy_half_spread_bps"] = half_bps
            bmeta["cadence_note"] = (
                f"{bmeta.get('cadence_note', '')}; fill eligibility = tape-proxy "
                f"(warehouse median Δt={med}s > {stale_s}s; half_spread_bps={half_bps})"
            ).strip("; ")
    else:
        bid, ask, mid = _tape_proxy_book(px, half_spread_bps=half_bps)
        fill_model = "tape_proxy_no_book"
        bmeta = {
            "available": False,
            "source": "tape_proxy",
            "fill_model": fill_model,
            "median_dt_s": None,
            "cadence_note": "no warehouse/collector book → tape-proxy touch",
        }

    packed = {
        "ts": ts,
        "px": px,
        "qty": qty,
        "side": side,
        "bid": bid,
        "ask": ask,
        "mid": mid,
    }
    packed = _downsample(packed, int(cfg.get("max_trades", 120_000)))

    events = cell.get("events") or {}
    n_ev = len(events.get("ts_end", []))
    r1 = list(events.get("recovery_1s", [np.nan] * n_ev))
    r2 = list(events.get("recovery_2s", [np.nan] * n_ev))

    ev_payload = {
        "ts_end": events.get("ts_end", []),
        "tier": list(events.get("tier", [])),
        "recovery_label": list(events.get("recovery_label", [])),
        "recovery_1s": r1,
        "recovery_2s": r2,
        "nanex_overlap": list(events.get("nanex_overlap", [])),
    }
    clock = build_event_clock(
        packed["ts"],
        ev_payload,
        ladder_hold_s=float(cfg.get("ladder_hold_s", 60.0)),
        nanex_pull_s=float(cfg.get("nanex_pull_s", 15.0)),
    )
    run_stack = bool(cfg.get("run_risk_gate_stack", True))
    stack_clock = None
    if run_stack:
        stack_clock = build_risk_gate_clock(
            packed["ts"],
            ev_payload,
            ladder_hold_s=float(cfg.get("ladder_hold_s", 60.0)),
            nanex_pull_s=float(cfg.get("nanex_pull_s", 15.0)),
            fire_pause_s=float(cfg.get("fire_pause_5m_s", 300.0)),
            nest_hard_pause=bool(cfg.get("nest_hard_pause", True)),
        )

    sim_cfg = SimConfig(
        base_size=float(cfg.get("base_size", 0.25)),
        friction_bps=float(cfg.get("friction_bps", 2.0)),
        max_inventory=float(cfg.get("max_inventory", 10.0)),
    )
    size_mult = cfg.get("size_mult") or {}
    sm = {
        "none": float(size_mult.get("none", 1.0)),
        "observe": float(size_mult.get("observe", 1.0)),
        "widen": float(size_mult.get("widen", 0.5)),
        "size_cap": float(size_mult.get("size_cap", 0.25)),
        "halt": float(size_mult.get("halt", 0.0)),
    }

    baseline = BaselineMaker(base_size=sim_cfg.base_size)
    ladder = KillLadderOverlay(
        clock=clock,
        base_size=sim_cfg.base_size,
        size_mult=sm,
    )
    strategies: list[Any] = [baseline, ladder]
    if bool(cfg.get("run_ladder_plus_confirm", True)):
        strategies.append(
            LadderPlusConfirmBeforeRestore(
                clock=clock,
                base_size=sim_cfg.base_size,
                wide_mult=float(cfg.get("wide_mult", 0.25)),
                size_mult=sm,
            )
        )
    if run_stack and stack_clock is not None:
        strategies.append(
            RiskGateStackOverlay(
                clock=stack_clock,
                base_size=sim_cfg.base_size,
                size_mult=sm,
            )
        )

    results: dict[str, Any] = {}
    for strat in strategies:
        sim = run_tick_sim(
            ts=packed["ts"],
            px=packed["px"],
            side=packed["side"],
            qty=packed["qty"],
            mid=packed["mid"],
            bid=packed["bid"],
            ask=packed["ask"],
            strategy=strat,
            cfg=sim_cfg,
        )
        st = equity_stats(sim.equity_bps)
        block = {
            "final_equity_bps": st["final_bps"],
            "max_dd_bps": st["max_dd_bps"],
            "n_fills": sim.n_fills,
            "final_inv": sim.meta["final_inv"],
            "equity_bps": sim.equity_bps,
            "inventory": sim.inventory,
            "regime": sim.regime,
            "fill_ts": sim.fill_ts,
            "fill_side": sim.fill_side,
            "fill_px": sim.fill_px,
            "fill_qty": sim.fill_qty,
            "fill_i": sim.fill_i,
            "ts": sim.ts,
            "px": sim.px,
            "mid": sim.mid,
        }
        block["fills_by_regime"] = _fills_by_regime(block)
        block["crash_window"] = _crash_window_stats(block, clock.tier)
        results[strat.name] = block
        assert_fills_on_tape(results[strat.name])

    bl = results["baseline_maker"]
    kl = results["kill_ladder_maker"]
    delta = {
        "delta_equity_bps": float(kl["final_equity_bps"] - bl["final_equity_bps"]),
        "delta_max_dd_bps": float(kl["max_dd_bps"] - bl["max_dd_bps"]),
        "delta_n_fills": int(kl["n_fills"] - bl["n_fills"]),
        "delta_final_inv": float(kl["final_inv"] - bl["final_inv"]),
        "delta_fills_in_fire": int(
            kl["crash_window"]["n_fills_in_fire"] - bl["crash_window"]["n_fills_in_fire"]
        ),
        "delta_qty_in_fire": float(
            kl["crash_window"]["qty_in_fire"] - bl["crash_window"]["qty_in_fire"]
        ),
        "delta_equity_incr_fire_bps": float(
            kl["crash_window"]["equity_incr_fire_bps"] - bl["crash_window"]["equity_incr_fire_bps"]
        ),
    }
    # Overlay nullified if crash windows have zero baseline fills (clamp / book dead)
    nullified = (
        int(bl["crash_window"]["n_fills_in_fire"]) == 0
        and int(kl["crash_window"]["n_fills_in_fire"]) == 0
        and int(np.sum(clock.tier != "none")) > 0
    )
    delta["overlay_nullified_in_fire"] = bool(nullified)

    confirm = results.get("ladder_plus_confirm_before_restore")
    delta_confirm = None
    if confirm is not None:
        delta_confirm = {
            "delta_equity_bps": float(confirm["final_equity_bps"] - bl["final_equity_bps"]),
            "delta_max_dd_bps": float(confirm["max_dd_bps"] - bl["max_dd_bps"]),
            "delta_n_fills": int(confirm["n_fills"] - bl["n_fills"]),
            "delta_fills_in_fire": int(
                confirm["crash_window"]["n_fills_in_fire"] - bl["crash_window"]["n_fills_in_fire"]
            ),
            "delta_equity_incr_fire_bps": float(
                confirm["crash_window"]["equity_incr_fire_bps"]
                - bl["crash_window"]["equity_incr_fire_bps"]
            ),
        }

    stack = results.get("risk_gate_stack")
    delta_stack = None
    stack_regime_counts = None
    if stack is not None:
        delta_stack = {
            "delta_equity_bps": float(stack["final_equity_bps"] - bl["final_equity_bps"]),
            "delta_max_dd_bps": float(stack["max_dd_bps"] - bl["max_dd_bps"]),
            "delta_n_fills": int(stack["n_fills"] - bl["n_fills"]),
            "delta_final_inv": float(stack["final_inv"] - bl["final_inv"]),
            "delta_fills_in_fire": int(
                stack["crash_window"]["n_fills_in_fire"] - bl["crash_window"]["n_fills_in_fire"]
            ),
            "delta_qty_in_fire": float(
                stack["crash_window"]["qty_in_fire"] - bl["crash_window"]["qty_in_fire"]
            ),
            "delta_equity_incr_fire_bps": float(
                stack["crash_window"]["equity_incr_fire_bps"]
                - bl["crash_window"]["equity_incr_fire_bps"]
            ),
        }
        stack_null = (
            int(bl["crash_window"]["n_fills_in_fire"]) == 0
            and int(stack["crash_window"]["n_fills_in_fire"]) == 0
            and (
                int(np.sum(clock.tier != "none")) > 0
                or (stack_clock is not None and int(np.sum(stack_clock.fire_pause_active)) > 0)
            )
        )
        delta_stack["overlay_nullified_in_fire"] = bool(stack_null)
        if stack_clock is not None:
            stack_regime_counts = clock_regime_counts(stack_clock)

    return {
        "book": bmeta,
        "fill_model": fill_model,
        "n_trades_sim": int(packed["ts"].size),
        "results": results,
        "delta_vs_baseline": delta,
        "delta_confirm_vs_baseline": delta_confirm,
        "delta_stack_vs_baseline": delta_stack,
        "clock_tier_counts": {
            t: int(np.sum(clock.tier == t))
            for t in ("none", "observe", "widen", "size_cap", "halt")
        },
        "stack_regime_counts": stack_regime_counts,
        "n_fire_pause_prints": int(np.sum(stack_clock.fire_pause_active)) if stack_clock is not None else 0,
        "n_nest_hard_prints": int(np.sum(stack_clock.nanex_active)) if stack_clock is not None else 0,
        "max_inventory": sim_cfg.max_inventory,
        "friction_bps": sim_cfg.friction_bps,
    }


def fill_action_records(
    shadow: dict[str, Any],
    *,
    day: str,
    symbol: str,
    venue: str,
    strat: str = "kill_ladder_maker",
) -> list[dict[str, Any]]:
    r = (shadow.get("results") or {}).get(strat) or {}
    fts = np.asarray(r.get("fill_ts", []), dtype=np.int64)
    fpx = np.asarray(r.get("fill_px", []), dtype=np.float64)
    fside = np.asarray(r.get("fill_side", []), dtype=np.int64)
    fqty = np.asarray(r.get("fill_qty", []), dtype=np.float64)
    fi = np.asarray(r.get("fill_i", []), dtype=np.int64)
    regime = np.asarray(r.get("regime", []), dtype=object)
    out: list[dict[str, Any]] = []
    for j in range(fts.size):
        reg = str(regime[int(fi[j])]) if fi.size == fts.size and 0 <= int(fi[j]) < regime.size else "unknown"
        out.append(
            {
                "kind": "shadow_fill",
                "day": day,
                "symbol": symbol,
                "venue": venue,
                "strat": strat,
                "ts": int(fts[j]),
                "px": float(fpx[j]),
                "side": int(fside[j]),
                "qty": float(fqty[j]) if j < fqty.size else None,
                "tape_i": int(fi[j]) if j < fi.size else None,
                "regime": reg,
            }
        )
    return out
