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

## Pass checklist

### Pass 1
- [x] Cite deck pages in NOTES
- [x] Implement on HL + Deribit + Kraken
- [x] EXP_REPORT with day-completeness
- [x] Draft CANDIDATES (+ draft overlap table)

### Pass 2
- [ ] Overlap gates vs crash + vstat
- [ ] Signal board → DESK_MEMO
