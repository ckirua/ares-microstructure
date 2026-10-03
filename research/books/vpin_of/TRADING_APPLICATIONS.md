# Trading / modelling applications — VPIN / order flow

**Companion:** [`DESK_MEMO.md`](DESK_MEMO.md) · Index: [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md)  
**Slice honesty:** **Construction + falsifiers Promote** on warehouse complete UTC days — wire VPIN as **monitor / sizing feature**, not standalone alpha. Desk wiring cites **`decisions_panel_promote.json`** (HL+Deribit, n_ok=139). **Pass 4 (FINAL, latest):** `out/pass4/decisions_pass4.json` — **5 Promote / 6 Hold** unchanged. Markout **Hold** on promote-slice with 60s IC + venue holdout (gate failed). Toxicity **Hold** — intraday VPIN-spike events do not widen spread. xvenue **Hold** — fresh notional calibration on newest HL↔DB pairs fails CI gate. **SOL:** formal **Deribit+Kraken** arm; HL shard still empty post-2026-08-28.

Confidence: **high** = wire as monitor with known failure modes · **med** = rule sketch needs paper trade · **low** = research feature only.

**Promote IDs (Pass 4 FINAL):** same five construction/falsifier/proxy IDs — **no** new Promotes from Pass 2–4 blocker retests

---

## 1. Market making / quoting

### 1.1 Toxic-flow dial

**Object:** rolling VPIN from volume-clock buckets (`scripts/_data.py` · median(qty)×50 SoT)

| Layer | Rule sketch | Conf |
|-------|-------------|------|
| Quote width | Widen when rolling VPIN > 90p **and** markout IC regime confirms (Pass 2) | **med** |
| Size | Cut `base_clip` when VPIN×log(notional) elevated (cross_miniflash taxonomy) | **med** |
| Alpha | Do **not** fade purely on VPIN threshold without event context | **high** |

**Falsifier (Pass 1 cleared):** side-shuffle null — pass_rate≈0.98 on n_ok=226.

**Pass 4:** ex-ante VPIN vs 60s markout on **promote-slice** HL+DB only, venue holdout — gate **failed**. Do **not** Kill construction; **do not** Promote as aggression throttle without new evidence.

---

## 2. Execution / taker

### 2.1 Aggression throttle

| Use | Conf |
|-----|------|
| Delay marketable flow when ex-ante VPIN high **and** rising quintile markout adverse | **low** (Pass 2 Hold — IC≈0) |
| Prefer passive when VPIN high **and** spread already wide | **low** — toxicity join shows **negative** vpin–spread correlation on HL+DB |

---

## 3. Risk

### 3.1 Stress flag

| Use | Conf |
|-----|------|
| Daily risk strip: mean VPIN + last rolling VPIN per venue | **high** |
| `risk.vpin_toxicity_flag` as auto-widen trigger | **low** (**Hold** — falsifier: top VPIN without spread widen) |
| Cross-venue divergence HL vs DB VPIN | **med** (**Hold** — SoT ρ≈−0.32; target50 ρ≈−0.04, gate failed) |

---

## 4. Monitors

[`applications/monitors.py`](applications/monitors.py) — Pass 1–4 rollup in `applications/out/monitor_snapshot.json` (`book_status=FINAL` when Pass 4 complete).

Rebuild: `python3 scripts/build_notebook_figs.py` · `python3 scripts/build_notebooks.py` · Pass 4: `python3 scripts/exp_pass4.py --resume`
