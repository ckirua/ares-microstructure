# Strategy / money path — Filimonov

**Companion:** [`DESK_MEMO.md`](DESK_MEMO.md) · [`APPLICATIONS.md`](APPLICATIONS.md) · [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) · board [`notebooks/info_bayes_board.ipynb`](notebooks/info_bayes_board.ipynb)  
**Artifacts:** `out/feature_stats/` · `out/bayes/` · sibling policy pattern [`../cross_miniflash/`](../cross_miniflash/) kill-ladder  
**Board freeze:** **0 Promote / 30 Hold / 11 Kill** — not a clean “trade the signal” book yet.

---

## Reality

Money today is mostly **lose-less / fill-better**, not harvest α.  
Edge path: **protect maker PnL and exec quality** (policy like cross_miniflash kill-ladder), **not** a directional bet.  
No Promote → no inventable tradable edge; wire-as stays risk / MM / exec throttle.

---

## Indirect pay (wire-as now)

| Wire-as | Target | How money shows up | Status |
|---------|--------|--------------------|--------|
| Storm throttle | Don’t thicken / cut size when λ_storm spikes | Lower AS after quote storms | Hold |
| Fade → MM pull | De-thicken / pull when post-trade fade fires | Fewer trapped thick quotes | Hold |
| Ignition escalate | Risk widen / kill-ladder vs crash labels | Avoid inventory in Phase2 | Hold |
| Clock / funding | Avoid sizing into clock clusters | Less algo-hunter toxicity | Hold (monitor) |

Playbook detail: [`APPLICATIONS.md`](APPLICATIONS.md) §§1–3. Bayes headlines: θ_fade≈0.0114; λ_storm HL≈0.41; P(AS\|storm) CrI∋0.5 — see [`DESK_MEMO.md`](DESK_MEMO.md) §2.

---

## Not good money targets yet

| Candidate | Why not | Decision |
|-----------|---------|----------|
| Smoking / layering farmer-finder | Kill FP (~1.79); smoke/layer proxies | **Kill** |
| Firm / person attribution | Public tape has no firm IDs; cannot find “people” | **Kill** (`id.participant_otr`) |
| Fade IRF widen rule | Sign-unstable (peak ≈−0.11bps this dig) | **Hold** — do not auto-widen |
| P(AS\|storm) hard size cut | Beta CrI covers 0.5 (≈0.43 [0.30, 0.57]) | **Hold** — gate not earned |
| Ignition / storm markouts as standalone taker α | Thin days; storm mass on 09-30; Hold blockers | **Hold** — not taker α |

Use attribution objects only as **when-not-to-thicken / when-to-pull on our quotes** — never as counterparty IDs.

---

## Next strategy graduates

Still need **≥10 complete UTC days** + **Promote gates** before any of these leave paper/monitor:

1. **Maker protect** — storm ∪ fade → auto de-thicken (paper avoided markout)
2. **Exec gate** — skip aggressive takes in storm / high VPIN∩storm windows
3. **Cross-link** Filimonov bits into V-fade / MM quoting labs — **not** a new standalone book

Backlog gates: [`DESK_MEMO.md`](DESK_MEMO.md) §4.

---

## Non-goals

- Speculative **long ignition / short after fade** — not earned
- **No tradable α** without a Promote freeze
- No firm-ID / person hunting on public tape
- No ClickHouse MCP; do not merge crash / vstat / lob APIs into Filimonov objects
- Do not inflate Promotes or invent PnL from Hold markouts

---

## Pointers

| Need | Where |
|------|-------|
| Signal board + numeric headlines | [`DESK_MEMO.md`](DESK_MEMO.md) |
| Rule sketches by desk job | [`APPLICATIONS.md`](APPLICATIONS.md) |
| Package map / pass status | [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) |
| Stats + Bayes dig | [`applications/feature_stats/EXP_REPORT.md`](applications/feature_stats/EXP_REPORT.md) · `out/bayes/` · [`notebooks/info_bayes_board.ipynb`](notebooks/info_bayes_board.ipynb) |
