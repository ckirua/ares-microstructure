# Auto-advance chapter research loop

## Pipeline status

| Program | Status |
|---------|--------|
| **mmip** (Lehalle/Laruelle) | Desk expansion complete — see [`books/mmip/DESK_MEMO.md`](books/mmip/DESK_MEMO.md) |
| **empirical_mm** (Hasbrouck notes) | Holds pass complete — OE public proxies + Sandas L1 + noise Kill — see [`books/empirical_mm/DESK_MEMO.md`](books/empirical_mm/DESK_MEMO.md) |

## Quality bar (Jane Street / top-MM desk — multi-lens)

1. Precise column definitions, units, update frequency, latency assumptions.
2. Label every candidate **D / T / E** and tag lenses: **`mm | disc | cont | exec | info | liq`**.
3. Where the book presents both, ship paired **`disc.*` / `cont.*`** candidates and state which clock fits our crypto MD.
4. Statistical hygiene: bootstrap CIs, chronological splits, multiple-testing honesty.
5. Explicit **falsifier** for every Promote.
6. Kill what fails; Hold borderline; never promote TOB-cross to arb α.
7. Shared `research/lib/` — notebooks import, do not copy-paste.

## Optional backlog

1. ~~Quote-update-aligned Δm for Hasbrouck VAR λ~~ — **done** (Promote λ/IRF/GH; HS lump π).
2. ~~Full EHO PIN MLE on ≥20 complete days~~ — **ran** on max warehouse tape (20–34 listed days; **13–~20 usable** after span filters) → PIN̂≈0.15–0.19 **Hold** (<20 certified full days / thin tails). See `books/empirical_mm/out/ch15_pin/`.
3. ~~Part III public-tape OE proxies + Sandas L1 moments~~ — **done** (`cont.size_touch_survival`, `cont.tob_cancel_proxy`, `disc.sandas_depth_moments`); true OE hazard + structural Sandas GMM remain Hold. `cont.noise_rv_ratio` **Kill** (block boot).
4. ~~Huang–Stoll α vs β decomposition~~ — two-way λ̂ + GMM/restricted + trade/quote/vol clocks; **`disc.hs_as_inv_split` Hold** (â<0 primary; proxy inventory). Lump `disc.hs_pi` Promote. `disc.mrr_rho_q` Hold hardened (ρ≃0.6 split-stable).
5. Full-day session curves (≥12 UTC hours × many days).
6. Residual theory-only: queue-position value; Stoll/CMSW EU / Foucault–Parlour eq (need prefs / OE).
