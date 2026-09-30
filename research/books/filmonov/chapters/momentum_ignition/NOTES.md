# Momentum ignition

**Book:** Filimonov, Perm Winter School 2013  
**PDF:** slides (local) · **Status:** `pass1`  
**Raw:** [`../../_raw/`](../../_raw/) (local/gitignored)  
**SoT:** [`../../CHAPTER_INDEX.md`](../../CHAPTER_INDEX.md)  
**Lib:** [`../../../../lib/hftpat.py`](../../../../lib/hftpat.py) · `ignition_events`

---

## Pass 1 focus

3-phase classifier: Phase1 vol↑ & |Δmid|≈0 → Phase2 large move+vol → Phase3 low-vol partial recovery (deck slide **34**).

### Deck citations
- Slide **34**: momentum ignition cartoon — build pressure (volume without move), impulse, partial reversion under quieter volume.
- Crypto map: `hftpat.ignition_events` on trade bars; overlap table vs `crash.nanex_detect` / SSM / `vshape_events` via `overlap_vs_crash` + `rename_gate`.

### Not a rename
- **Not** Nanex / SSM crash tags or `vshape_events` (move+recovery geometry alone).
- **Not** `vstat.min_v` (econometric drift-burst product ≠ cause sequence).
- Promote **only** if Phase1 (quiet-mid high-vol) adds information; **Pass 1 decision = Hold**.

## Pass 2 dig

**Mandatory** overlap table vs Nanex / SSM / `vshape_events` / MinV. Promote only if pre-phase adds info beyond crash tags.

## Info / Bayesian dig

**Question:** does the 3-phase sequence carry **incremental** information vs crash/V geometry?

| Lens | Finding | Path |
|------|---------|------|
| Forward markout @1s | ≈1.60bps CI[0.97,2.14]; BH-reject + sign-stable; n_days=6 | `out/feature_stats/` |
| λ ignition / day-venue | ≈6.41 CrI[5.26,7.67] | `out/bayes/` |
| Phase1 unique mass | often vacuous when Nanex n=0 @default % | prior expand |
| Cascade storm→ign @1s | hit-rate ≈0 | sparse storms |

**Wire-as:** escalate-vs-crash **label** on risk strip — not tradable α. Cross-link `crash` / `vstat` via overlap helpers only.

## Pass checklist

### Pass 1
- [x] Cite deck pages in NOTES
- [x] Implement on HL + Deribit + Kraken
- [x] EXP_REPORT with day-completeness
- [x] Draft CANDIDATES (+ draft overlap table)

### Pass 2
- [x] Overlap gates vs crash + vstat
- [x] Signal board → DESK_MEMO
- [x] Info/Bayes deep dig
