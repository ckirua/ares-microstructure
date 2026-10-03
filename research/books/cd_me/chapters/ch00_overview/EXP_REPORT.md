# Ch.00 overview — EXP_REPORT

## Sample
- Framing package; empirics in sibling packages.
- Venue set locked: **HL + Deribit** real quotes (primary); Kraken **spot_l2** when dense.
- Pass-2 empirics: certified `panel_core_2venue` **n=9**; spot_l2 subpanel **n=4**. Prior “10/10 three-venue + trade_synth” **retracted**.

## Notes
- Crypto adaptation locked in BOOK.md / CHAPTER_INDEX (cross-venue LOP; DCM from public proxies).
- Native triangles parked until multi-pair TOB confirmed.
- PDF formulas cited in NOTES (pp. 2–12 taxonomy; Eqs 1–3).
- Completeness SoT: `out/panel_completeness/`.

## Status
- Pass 2 framing aligned with Hold board (0 Promote)
- Promote: none

## Pass 2 falsifiers (auto)

- **Certified panel:** n=9 primary; spot_l2=4; trade_synth **QUARANTINED**.
- **Pooled elasticity:** n=88 corr=-0.461 CI[-0.570, -0.353].
- **Chrono split:** early corr=-0.314 late=-0.544 sign_stable=True.
- **Block bootstrap (by day):** corr=-0.461 CI[-0.548, -0.374].
- **Placebo PIM shuffle:** passes=True; **DCM shuffle:** inconclusive.
- **Decision:** 0 Promote; all monitors **Hold**.
