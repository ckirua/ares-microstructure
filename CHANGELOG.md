# Changelog

All notable **repository-level** changes for [ares-microstructure](README.md) are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Dates are UTC calendar days of the corresponding git tip.

Day-to-day research runs and experiment promote/hold/kill notes live in
[`research/books/EXPERIMENTS.md`](research/books/EXPERIMENTS.md) — not duplicated here.

## [Unreleased]

### Added

- _(none yet)_

### Changed

- _(none yet)_

### Fixed

- _(none yet)_

## [2026-10-03]

### Added

- **vpin_of** research book (Easley et al. VPIN / order-flow toxicity): chapter packages, desk memo, inventory, trading-applications map, panel + Pass 2 experiment scripts, desk-synthesis notebook, and shared `research/lib/vpin.py`.
- **vpin_of Pass 1** (canonical boards `out/vpin_panel/decisions.json` + `decisions_panel_promote.json`): exploratory **n_ok=226**/315 (ETH/BTC/SOL × HL+Deribit+Kraken, complete UTC); promote-provenance HL+DB **n_ok=139**; med VPIN ≈**0.862** CI [0.845, 0.876]; gate table **5 Promote / 3 Hold** (constructed, bucket_mean, side_shuffle, time_split, pin_proxy Promote; xvenue / Kraken / HL-SOL Hold).
- **vpin_of Pass 2** (`scripts/exp_pass2.py` → `out/pass2/decisions_pass2.json`): HL+Deribit TOB join panel **n=110**; merged board **6 Promote / 5 Hold**. New Promote: `info.vpin_markout` (36/48 day-cells; median day IC≈**0.022**, early≈**0.030**, late≈**0.015**). Hold: `risk.vpin_toxicity_flag` (n=73; ρ(vpin, spread)≈**−0.36**, inverted vs widen narrative), `cont.vpin_bucket_robust`, plus unchanged frag Holds (xvenue / Kraken / HL-SOL).
- **squeeze_metrics** research book (SqueezeMetrics / GEX Ed., *The Implied Order Book*): chapter packages, desk memo, APPLICATIONS map, certified-panel + Pass1/Pass2b experiment scripts, desk-synthesis / info-stats notebooks, and `applications/paper_shadow/` harness (`live_orders=false`).
- Shared helpers `research/lib/squeeze.py` (GEX/VEX/GEX+, DDOI proxies, panel joins).
- Certified primary panel `panel_gex_options` **n=9**; Pass **2b** falsifiers show paper-sign corr(GEX, HL RV)≈**−0.22** but CI/chrono/placebo/LOO fail Promote → **0 Promote** (honest Hold ceiling).
- **cd_me** research book (Huang–Ranaldo–Schrimpf–Somogyi, *Constrained Dealers and Market Efficiency*): chapter packages, desk memo, experiment scripts, notebooks, and `paper_shadow` application harness.
- Shared helpers `research/lib/cdme.py` and `research/lib/tsrv.py`.
- **mn_tuwrv** desk applications: trading-applications memo, monitors, depth-predict experiment, and predictive-power / uses-and-information notebooks.

### Changed

- **mn_tuwrv** chapter index, desk memo, and desk-synthesis notebook extended for the new application surface.
- Research loop / books index updated for the **cd_me**, **squeeze_metrics**, and **vpin_of** slugs.

## [2026-10-01]

### Added

- [`PUBLIC.md`](PUBLIC.md): public-release disclaimer, publish vs gitignore boundary, env setup, history leftovers.

### Changed

- Portable path resolution via `ARES_STARTARB`, `WAREHOUSE_ROOT` / `WAREHOUSE_SRC`, `ARES_MICROSTRUCTURE` (and `%h` / `EnvironmentFile` in systemd units) instead of hardcoded host paths.
- README / data-path docs hygiene for a public visibility flip (no history rewrite).

## [2026-09-30]

### Added

- Multi-book research tree under `research/books/`: **mmip**, **empirical_mm**, **cross_miniflash**, **v_shapes**, **mn_tuwrv**, **mm_confr_viewpoints**, **filmonov** (notebooks, memos, scripts; PDFs/`out`/logs stay local).
- Desk-ready research bar: shared `research/lib`, intro liquidity + classic micro experiments, Promote hardening (falsifiers/CIs), unified MMIP desk memo.
- Shadow / paper application source: **v_fade_paper**, **paper_throttle**, **tick_shadow**, **paper_live** (source + units; runtime logs/artifacts ignored).

### Changed

- MMIP research relocated under `research/books/mmip/` (PR #1); shared lib, `DATA_PATHS`, and `LOOP` remain at `research/`.
- Artifact ignore policy tightened: research `out/`, logs, caches, poller dumps untracked; `.gitkeep` placeholders retained.

### Research experiments

- Session scoreboard (edge_lab Promotes / xvenue_lag Kill / sibling desks): [`research/books/EXPERIMENTS.md`](research/books/EXPERIMENTS.md#2026-09-30).

## [2026-09-29]

### Added

- Initial repository commit.
