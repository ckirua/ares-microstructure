"""Event/tick simulator: trade tape + asof book → marked PnL / inventory.

Fill model (honest synthetic maker / optional taker):
- Maker posts size at touch; aggressive opposite trade fills min(our_sz, trade_qty)
  when the print reaches asof bid (we buy) or ask (we sell).
- Fill price is the trade print (tape px), not stale asof bid/ask — warehouse BBO
  can lag the ms tape by minutes; booking at touch would float markers / invent edge.
- One-way friction haircut on each fill (default 1–2 bps).
- Inventory marked to asof mid (book mid if available, else trade px).
- No fantasy latency edge; book may be seconds-stale vs ms tape.

Not live alpha — research equity curves for risk overlays vs baseline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np


@dataclass
class SimConfig:
    base_size: float = 0.25  # coin units at touch
    friction_bps: float = 2.0
    max_inventory: float = 2.0
    mark_every: int = 1  # mark on every trade
    seed: int = 0


@dataclass
class QuoteIntent:
    bid_sz: float
    ask_sz: float
    pulled: bool = False
    regime: str = "normal"  # observe/widen/size_cap/halt/nanex/v_wide/...


@dataclass
class SimResult:
    name: str
    ts: np.ndarray
    px: np.ndarray
    mid: np.ndarray
    equity_bps: np.ndarray
    inventory: np.ndarray
    regime: np.ndarray  # object array of labels
    fill_ts: np.ndarray
    fill_side: np.ndarray  # +1 buy / -1 sell (our side)
    fill_px: np.ndarray
    fill_qty: np.ndarray
    fill_pnl_bps: np.ndarray
    fill_i: np.ndarray  # tape index of each fill (plot / integrity)
    n_fills: int
    meta: dict[str, Any] = field(default_factory=dict)


class Strategy(Protocol):
    name: str

    def reset(self) -> None: ...

    def quote(
        self,
        i: int,
        *,
        ts: np.ndarray,
        px: np.ndarray,
        side: np.ndarray,
        qty: np.ndarray,
        mid: np.ndarray,
        bid: np.ndarray,
        ask: np.ndarray,
        inv: float,
    ) -> QuoteIntent: ...


def run_tick_sim(
    *,
    ts: np.ndarray,
    px: np.ndarray,
    side: np.ndarray,
    qty: np.ndarray,
    mid: np.ndarray,
    bid: np.ndarray,
    ask: np.ndarray,
    strategy: Strategy,
    cfg: SimConfig | None = None,
) -> SimResult:
    cfg = cfg or SimConfig()
    n = int(ts.size)
    strategy.reset()
    equity = np.zeros(n, dtype=np.float64)
    inv_path = np.zeros(n, dtype=np.float64)
    regimes = np.empty(n, dtype=object)
    cash_bps = 0.0  # cumulative realized + marked, in bps of notional ref
    inv = 0.0
    # use first valid mid/px as notional base for bps scaling
    ref = float(mid[0]) if np.isfinite(mid[0]) and mid[0] > 0 else float(px[0])
    if not np.isfinite(ref) or ref <= 0:
        ref = 1.0

    fill_ts: list[int] = []
    fill_side: list[int] = []
    fill_px: list[float] = []
    fill_qty: list[float] = []
    fill_pnl: list[float] = []
    fill_i: list[int] = []

    fr = float(cfg.friction_bps) * 1e-4
    prev_mid = ref

    for i in range(n):
        m = float(mid[i]) if np.isfinite(mid[i]) and mid[i] > 0 else float(px[i])
        if not np.isfinite(m) or m <= 0:
            m = prev_mid
        # mark-to-mid inventory PnL since last step (bps of ref notional per coin)
        if i > 0 and inv != 0.0 and prev_mid > 0:
            cash_bps += inv * (m - prev_mid) / ref * 1e4
        prev_mid = m

        intent = strategy.quote(
            i,
            ts=ts,
            px=px,
            side=side,
            qty=qty,
            mid=mid,
            bid=bid,
            ask=ask,
            inv=inv,
        )
        regimes[i] = intent.regime
        bid_sz = 0.0 if intent.pulled else max(0.0, float(intent.bid_sz))
        ask_sz = 0.0 if intent.pulled else max(0.0, float(intent.ask_sz))

        # inventory soft clamp: stop quoting into limit
        if inv >= cfg.max_inventory:
            bid_sz = 0.0
        if inv <= -cfg.max_inventory:
            ask_sz = 0.0

        tr_side = float(side[i])  # +1 buy aggressor, -1 sell aggressor
        tr_qty = float(qty[i]) if np.isfinite(qty[i]) else 0.0
        tr_px = float(px[i]) if np.isfinite(px[i]) else m

        filled = False
        our_side = 0
        fqty = 0.0
        fpx = tr_px

        if tr_qty > 0 and tr_side > 0 and ask_sz > 0:
            # buy aggressor lifts our ask only if print reaches ask
            ask_px = float(ask[i]) if np.isfinite(ask[i]) and ask[i] > 0 else tr_px
            if tr_px + 1e-12 >= ask_px:
                fqty = min(ask_sz, tr_qty)
                fpx = tr_px  # execute at print, not stale asof ask
                our_side = -1
                filled = True
        elif tr_qty > 0 and tr_side < 0 and bid_sz > 0:
            bid_px = float(bid[i]) if np.isfinite(bid[i]) and bid[i] > 0 else tr_px
            if tr_px - 1e-12 <= bid_px:
                fqty = min(bid_sz, tr_qty)
                fpx = tr_px  # execute at print, not stale asof bid
                our_side = +1
                filled = True

        if filled and fqty > 0:
            # friction cost in bps of ref
            cost = fqty * fr * 1e4 * (fpx / ref)
            # position update; immediate mark at mid vs fill
            edge = our_side * (m - fpx) / ref * 1e4 * fqty
            cash_bps += edge - cost
            inv += our_side * fqty
            fill_ts.append(int(ts[i]))
            fill_side.append(our_side)
            fill_px.append(fpx)
            fill_qty.append(fqty)
            fill_pnl.append(edge - cost)
            fill_i.append(i)

        inv_path[i] = inv
        equity[i] = cash_bps

    return SimResult(
        name=strategy.name,
        ts=ts,
        px=px,
        mid=mid,
        equity_bps=equity,
        inventory=inv_path,
        regime=regimes,
        fill_ts=np.asarray(fill_ts, dtype=np.int64),
        fill_side=np.asarray(fill_side, dtype=np.int64),
        fill_px=np.asarray(fill_px, dtype=np.float64),
        fill_qty=np.asarray(fill_qty, dtype=np.float64),
        fill_pnl_bps=np.asarray(fill_pnl, dtype=np.float64),
        fill_i=np.asarray(fill_i, dtype=np.int64),
        n_fills=len(fill_ts),
        meta={
            "friction_bps": cfg.friction_bps,
            "base_size": cfg.base_size,
            "max_inventory": cfg.max_inventory,
            "final_inv": float(inv),
            "final_equity_bps": float(equity[-1]) if n else float("nan"),
        },
    )
