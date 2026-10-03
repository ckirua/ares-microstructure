# paper_shadow — NOTES

**Book:** SqueezeMetrics (`sqzme`), *The Implied Order Book* (GEX Ed., 6 July 2020)  
**Status:** `notes` + sibling harness scaffold (do not edit app from this package)  
**Path:** [`../../applications/paper_shadow/`](../../applications/paper_shadow/)  
**Honesty:** Monitor/Hold only · `live_orders=false` · **never TOB-cross α**

Page cites = PDF viewer / file page index (cover = p.1).

---

## 1. What the harness mirrors from paper objects

Living warehouse-day shadow (pattern after `cd_me` / `v_shapes` paper_live). Each poll / day replay computes Pass-1 objects and tags them **Monitor/Hold** — telemetry only.

| Paper object | PDF | Shadow monitor | Gate label |
|--------------|-----|----------------|------------|
| DDOI | p. 3 | signed OI proxy (when loaders exist) | feeds GEX/VEX |
| GEX | pp. 4–5 | dealer γ → $ | `risk.gex_exposure` **Hold** |
| VEX | pp. 6–8 | dealer vanna → $ | `risk.vex_exposure` **Hold** |
| GEX+ / squeeze | p. 9 | GEX + VEX intensity | `risk.squeeze_intensity` **Hold** |
| Scarcity / red zone | pp. 10–11 | implied-book scarcity | `liq.implied_book_scarcity` **Hold** |
| Put sell/buy | pp. 11–12 | flow imbalance (planned) | Hold when wired |
| Executable TOB cross | p. 1 | — | `alpha.tob_cross_arb` **Kill** |
| `trade_synth` | — | — | **Kill** / quarantined |

**Deps (sibling agents):** `research/lib/squeeze.py` + `scripts/_data.py`. Dry-run on `2026-09-29` emits `missing_lib_squeeze` stubs — board still Hold-only.

**Not mirrored yet:** full conditional GIV surface (pp. 10–11); charm (paper drops, p. 3).

---

## 2. I/O & clocks

- Config / runner: `applications/paper_shadow/` (`config.yaml`, `run_paper_shadow.py`).
- Outputs: `logs/shadow.log`, `out/events.jsonl`, `out/SHADOW_BOARD.md`, per-day `summary.json`.
- Clock: UTC warehouse day; primary cell HL ETH (+ Deribit/Kraken when loaders ready).
- Hard refuse: `live_orders=true`; never mercat/gateway OE.

---

## 3. Pass checklist

### Pass 0
- [x] Map paper objects → Hold/Kill gate labels (aligned with app README)
- [x] Chapter notes only — do not overwrite harness

### Pass 1
- [ ] Metrics once `lib/squeeze` + loaders present
- [ ] Dry-run historical day; still no orders; Promote count = 0
