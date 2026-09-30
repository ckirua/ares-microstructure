# Auto-advance chapter research loop

## Pipeline status: **DESK EXPANSION COMPLETE**

Intro · Ch.1 · Ch.2 · Ch.3 · App.A · classic micro · Promote hardening shipped under the MM quality bar
(NOTES + CANDIDATES + EXP_REPORT + notebook/lib + `out/` + falsifiers/CIs).

See [`books/mmip/DESK_MEMO.md`](books/mmip/DESK_MEMO.md) for the unified feature/strategy map.

## Quality bar (Jane Street / top-MM desk)

1. Precise column definitions, units, update frequency, latency assumptions.
2. Label every candidate **D / T / E**.
3. Statistical hygiene: bootstrap CIs, chronological splits, multiple-testing honesty.
4. Explicit **falsifier** for every Promote.
5. Kill what fails; Hold borderline; never promote TOB-cross to arb α.
6. Shared `research/lib/` — notebooks import, do not copy-paste.

## Optional backlog

1. Full-day session curves (≥12 UTC hours × many days).
2. Multi-level L2 depth / true queue proxies.
3. Spatial multi-venue trade FEI.
4. Live POV / OE A/B for impact priors.
5. Funding-conditioned schedules; calibrated mean–variance λ.
