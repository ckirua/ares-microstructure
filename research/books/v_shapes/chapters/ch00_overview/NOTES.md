# Ch.00 — Overview: V-shapes vs inefficiency

**Book:** Flora & Renò (2020-09-17)  
**PDF:** §1 Introduction pp. 2–6 · §2 Def 1 / Prop 1 pp. 7–9 · **Status:** `exp_run`  
**Raw:** [`../../_raw/`](../../_raw/) (local/gitignored)  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md) · Desk: [`../../DESK_MEMO.md`](../../DESK_MEMO.md)

Scaffold: Definition 1 (discontinuous drift sign change), Prop 1 (V ⇒ inefficiency under long-run efficiency), and why **vol / jumps ≠ inefficiency**. Empirics deferred to sibling packages.

---

## 1. Definition & claim (§1–2)

| Object | Paper | Crypto desk mapping |
|--------|-------|---------------------|
| V-shape | Sudden sign change of \(\mu_t\) (Def 1) | UTC-day 1s mid/last path |
| Inefficiency | Overshoot vs fundamentals (Prop 1) | Hold causal ID of “fundamentals” |
| Flash crash | BoE-style V subset | Competing: Nanex / geometric V / SSM |
| Vol spike | Present in efficient *and* inefficient | Kill vol-as-inefficiency monitor |
| Jump | Efficient news embed | Competing jump detectors |

---

## 2. Reading order

1. This overview → taxonomy + signal roadmap  
2. `v_statistic` → \(T^\pm\), \(V\), kernels in `lib/vstat.py`  
3. `bootstrap_sim` → EGARCH bands + Models 0–3  
4. `daily_minv` → UTC-day MinV panel  
5. `event_case` + `liq_around_v` + `xvenue_concord` in parallel  
6. Program hardening → DESK_MEMO signal board

---

## 3. Signal roadmap (pre-empt)

| Object | Tentative label | Falsifier before Promote |
|--------|-----------------|--------------------------|
| MinV vs EGARCH 5%/1% | Risk monitor | \(h_n\) fragility; placebo times |
| Continuous \(V_t\), \(T^\pm\) | Info feature | Lead-lag vs mid / markout |
| Geometric `crash.vshape_events` | Baseline PR | Incremental overlap vs MinV |
| X-venue MinV concordance | Frag risk | Thin-tape days only? |

---

## 4. Pass checklist

### Pass 1
- [ ] Cite Def 1 / Prop 1 / vol≠inefficiency pages
- [ ] Map reading order onto venue set HL+Deribit+Kraken

### Pass 2
- [ ] Taxonomy table: V vs jump vs liq hole vs Tee–Ting mini-crash with empirical overlap
- [ ] Notebook Signal board skeleton → DESK_MEMO
