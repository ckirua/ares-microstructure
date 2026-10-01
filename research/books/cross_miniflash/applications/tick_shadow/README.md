# tick_shadow — HL trades WS + incremental SSM + severity_zend shadow

`live_orders=false`. See [`ARCHITECTURE.md`](ARCHITECTURE.md).

## systemd (preferred)

Long-running WS client under user systemd (no foreground terminal):

```bash
systemctl --user daemon-reload
systemctl --user enable --now ares-tick-shadow.service
systemctl --user status ares-tick-shadow.service
journalctl --user -u ares-tick-shadow.service -f
tail -f logs/tick_shadow.log
systemctl --user stop ares-tick-shadow.service
systemctl --user restart ares-tick-shadow.service
```

Unit file: `ares-tick-shadow.service` → `~/.config/systemd/user/`.  
ExecStart: `python3 -u run_tick_shadow.py --coin ETH` (severity defaults from `config.yaml`).  
Stop any manual `run_tick_shadow.py` before enable to avoid duplicate WS clients.

## Manual run (smoke)

```bash
cd research/books/cross_miniflash/applications/tick_shadow   # from repo root
python3 -u run_tick_shadow.py --coin ETH
# smoke: --heartbeat-s 5 --max-seconds 30
tail -f logs/tick_shadow.log
```

## Feed

Primary: **HL public WS `trades`** on `wss://api.hyperliquid.xyz/ws`  
`{"method":"subscribe","subscription":{"type":"trades","coin":"ETH"}}`  
Bootstrap: REST `recentTrades`. Dedup `(time_ms, coin, tid)`.  
Transport: `websocket-client` (aiohttp/websockets segfault on this host).  
Not startarb `ExchangeWsHub` (TOB-only). No SHM/Redis. Warehouse poll peers unchanged.
