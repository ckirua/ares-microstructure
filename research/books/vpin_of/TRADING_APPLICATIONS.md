# Trading / modelling applications — VPIN / order flow

**Companion:** [`DESK_MEMO.md`](DESK_MEMO.md) · Index: [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md)  
**Slice honesty:** **Construction + falsifiers Promote** on warehouse complete UTC days — wire VPIN as **monitor / sizing feature**, not standalone alpha. Desk wiring cites **`decisions_panel_promote.json`** (HL+Deribit, n_ok=139). **Pass 2:** `info.vpin_markout` **Promote** on HL+DB TOB (median day IC>0, early∧late>0) — usable as **soft** aggression throttle input, not hard alpha. **`risk.vpin_toxicity_flag` Hold** — high VPIN does **not** co-move with wider spread on joined sample; keep monitor-only.

Confidence: **high** = wire as monitor with known failure modes · **med** = rule sketch needs paper trade · **low** = research feature only.

**Promote IDs (Pass 2 merge):** Pass 1 five + `info.vpin_markout` · **`disc.pin_proxy_vs_vpin`** remains rank Promote (not PIN level parity)

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

**Pass 2:** ex-ante VPIN vs 30s TOB markout — median IC≈0.022, early/late splits both positive (36 day-cells). Do **not** Kill construction; optional tactical use only with venue holdout.

---

## 2. Execution / taker

### 2.1 Aggression throttle

| Use | Conf |
|-----|------|
| Delay marketable flow when ex-ante VPIN high **and** rising quintile markout adverse | **med** (Pass 2 Promote — paper trade) |
| Prefer passive when VPIN high **and** spread already wide | **low** — toxicity join shows **negative** vpin–spread correlation on HL+DB |

---

## 3. Risk

### 3.1 Stress flag

| Use | Conf |
|-----|------|
| Daily risk strip: mean VPIN + last rolling VPIN per venue | **high** |
| `risk.vpin_toxicity_flag` as auto-widen trigger | **low** (**Hold** — falsifier: top VPIN without spread widen) |
| Cross-venue divergence HL vs DB VPIN | **med** (**Hold** — ρ≈−0.32) |

---

## 4. Monitors

[`applications/monitors.py`](applications/monitors.py) — Pass 1 + Pass 2 rollup in `applications/out/monitor_snapshot.json`.

Rebuild: `python3 scripts/build_notebook_figs.py` · `python3 scripts/build_notebooks.py` · Pass 2: `python3 scripts/exp_pass2.py --resume`
