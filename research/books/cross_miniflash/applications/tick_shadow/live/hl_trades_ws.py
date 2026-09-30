"""Hyperliquid public trades feed — WS primary, REST warm/fallback.

Venue: ``wss://api.hyperliquid.xyz/ws`` subscribe
``{"method":"subscribe","subscription":{"type":"trades","coin":"ETH"}}``.

Uses ``websocket-client`` (thread) — async ``websockets``/``aiohttp`` segfaulted
on this host's TLS stack; payload is identical to venue docs / mercat MD notes.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterator

LOG = logging.getLogger("tick_shadow")

HL_WS = "wss://api.hyperliquid.xyz/ws"
HL_INFO = "https://api.hyperliquid.xyz/info"
_UA = {"User-Agent": "ares-tick-shadow/0", "Accept": "application/json"}


@dataclass(frozen=True, slots=True)
class Print:
    ts_ns: int
    px: float
    sz: float
    side: int  # +1 buy / -1 sell (aggressor)
    tid: int
    source: str  # ws:hl_trades | rest:hl_recentTrades


def _parse_row(row: dict[str, Any], *, source: str) -> Print | None:
    try:
        px = float(row.get("px") or row.get("price") or 0.0)
        sz = float(row.get("sz") or row.get("qty") or 0.0)
        t_ms = int(row.get("time") or 0)
        tid = int(row.get("tid") or 0)
    except (TypeError, ValueError):
        return None
    if not (px > 0 and sz > 0 and t_ms > 0):
        return None
    side_raw = str(row.get("side") or "").upper()
    side = 1 if side_raw in ("B", "BUY", "1") else -1
    return Print(
        ts_ns=int(t_ms) * 1_000_000,
        px=px,
        sz=sz,
        side=side,
        tid=tid,
        source=source,
    )


def fetch_recent_trades(coin: str = "ETH", *, timeout: float = 2.0) -> list[Print]:
    body = json.dumps({"type": "recentTrades", "coin": coin}).encode()
    req = urllib.request.Request(
        HL_INFO,
        data=body,
        headers={**_UA, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        LOG.warning("REST recentTrades fail: %s", exc)
        return []
    rows = list(payload) if isinstance(payload, list) else []
    out: list[Print] = []
    for row in rows:
        if isinstance(row, dict):
            p = _parse_row(row, source="rest:hl_recentTrades")
            if p is not None:
                out.append(p)
    out.sort(key=lambda p: (p.ts_ns, p.tid))
    return out


def parse_ws_trades_msg(msg: dict[str, Any]) -> list[Print]:
    if msg.get("channel") != "trades":
        return []
    data = msg.get("data")
    rows = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
    out: list[Print] = []
    for row in rows:
        if isinstance(row, dict):
            p = _parse_row(row, source="ws:hl_trades")
            if p is not None:
                out.append(p)
    return out


class HlTradesFeed:
    """Daemon-thread HL trades WS → ``queue.Queue[Print]``."""

    def __init__(
        self,
        coin: str = "ETH",
        *,
        qsize: int = 50_000,
        reconnect_s: float = 2.0,
        rest_fallback_poll_s: float = 1.0,
    ) -> None:
        self.coin = str(coin).upper()
        self.reconnect_s = float(reconnect_s)
        self.rest_fallback_poll_s = float(rest_fallback_poll_s)
        self.q: queue.Queue[Print | None] = queue.Queue(maxsize=qsize)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # Dedup key: (time_ms, coin, tid) — sibling / venue identity
        self._seen: set[tuple[int, str, int]] = set()
        self._seen_order: list[tuple[int, str, int]] = []
        self._seen_cap = 20_000
        self.n_ws = 0
        self.n_rest = 0
        self.n_dup = 0
        self.last_print_ts_ns = 0
        self.connected = False
        self.last_error: str | None = None

    def _remember(self, p: Print) -> bool:
        """Return True if new. Dedup on (time_ms, coin, tid)."""
        key = (int(p.ts_ns // 1_000_000), self.coin, int(p.tid or 0))
        if key in self._seen:
            self.n_dup += 1
            return False
        self._seen.add(key)
        self._seen_order.append(key)
        if len(self._seen_order) > self._seen_cap:
            old = self._seen_order.pop(0)
            self._seen.discard(old)
        return True

    def _emit(self, p: Print) -> None:
        if not self._remember(p):
            return
        try:
            self.q.put_nowait(p)
        except queue.Full:
            try:
                self.q.get_nowait()
            except queue.Empty:
                pass
            try:
                self.q.put_nowait(p)
            except queue.Full:
                return
        self.last_print_ts_ns = p.ts_ns
        if p.source.startswith("ws"):
            self.n_ws += 1
        else:
            self.n_rest += 1

    def warm_rest(self) -> int:
        rows = fetch_recent_trades(self.coin)
        for p in rows:
            self._emit(p)
        return len(rows)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name=f"hl-trades-{self.coin}", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            self.q.put_nowait(None)
        except queue.Full:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

    def iter_timeout(self, timeout_s: float) -> Iterator[Print]:
        """Yield prints until timeout with no new item (single wait)."""
        try:
            item = self.q.get(timeout=timeout_s)
        except queue.Empty:
            return
        if item is None:
            return
        yield item
        while True:
            try:
                item = self.q.get_nowait()
            except queue.Empty:
                break
            if item is None:
                break
            yield item

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._ws_once()
            except Exception as exc:  # noqa: BLE001
                self.connected = False
                self.last_error = str(exc)
                LOG.warning("HL trades WS error: %s — REST fallback briefly", exc)
                self._rest_fallback_burst()
            if self._stop.is_set():
                break
            time.sleep(self.reconnect_s)

    def _rest_fallback_burst(self) -> None:
        deadline = time.monotonic() + max(3.0, self.reconnect_s * 2)
        while not self._stop.is_set() and time.monotonic() < deadline:
            for p in fetch_recent_trades(self.coin):
                self._emit(p)
            time.sleep(self.rest_fallback_poll_s)

    def _ws_once(self) -> None:
        import websocket

        done = threading.Event()

        def on_open(ws: Any) -> None:
            self.connected = True
            self.last_error = None
            ws.send(
                json.dumps(
                    {
                        "method": "subscribe",
                        "subscription": {"type": "trades", "coin": self.coin},
                    }
                )
            )
            LOG.info("WS subscribed trades coin=%s", self.coin)

        def on_message(_ws: Any, message: str) -> None:
            try:
                msg = json.loads(message)
            except json.JSONDecodeError:
                return
            ch = msg.get("channel")
            if ch == "subscriptionResponse":
                LOG.info("WS subscriptionResponse %s", msg.get("data"))
                return
            if ch == "pong":
                return
            for p in parse_ws_trades_msg(msg):
                self._emit(p)

        def on_error(_ws: Any, err: Any) -> None:
            self.last_error = str(err)
            LOG.warning("WS on_error: %s", err)

        def on_close(_ws: Any, status: Any, msg: Any) -> None:
            self.connected = False
            LOG.info("WS closed status=%s msg=%s", status, msg)
            done.set()

        ws = websocket.WebSocketApp(
            HL_WS,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )

        def _pump() -> None:
            ws.run_forever(ping_interval=20, ping_timeout=10)

        t = threading.Thread(target=_pump, name="hl-ws-pump", daemon=True)
        t.start()
        while not self._stop.is_set() and t.is_alive():
            time.sleep(0.25)
        try:
            ws.close()
        except Exception:
            pass
        t.join(timeout=3.0)
        self.connected = False
