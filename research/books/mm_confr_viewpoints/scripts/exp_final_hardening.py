from __future__ import annotations
#!/usr/bin/env python3
"""Program-wide hardening for mm_confr_viewpoints.

Bootstrap / time-split gates, DESK_MEMO signal board, desk_synthesis notebook,
CHAPTER_INDEX Promote rollup. ClickHouse MCP banned. No git commit.

Pass-2.5 day-block bootstrap + BTC replication lives in
``scripts/exp_bootstrap_btc.py`` → ``out/hardening/``.
"""


import json
import sys
from pathlib import Path

import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from research.lib.stats import bootstrap_ci, spearman_r  # noqa: E402
from research.lib.ticksize import fama_macbeth_slope  # noqa: E402

OUT = BOOK / "out" / "pass2"


def _load(name: str):
    return json.loads((BOOK / "out" / "pass1" / name).read_text())


def main() -> None:
    panel = _load("panel.json")
    fm = _load("fm.json")
    score = _load("sign_scorecard.json")
    rows = panel["rows"]
    days = sorted({r["day"] for r in rows})
    early, late = days[: len(days) // 2], days[len(days) // 2 :]

    flat = []
    for r in rows:
        if not r.get("tob_ok"):
            continue
        flat.append(
            {
                "day": r["day"],
                "venue": r["venue"],
                "rel_tick": r.get("rel_tick"),
                "quoted_spread_bps": r.get("quoted_spread_bps"),
                "volume": r.get("volume"),
                "frac_c": (r.get("constraint") or {}).get("frac_constrained_2tick"),
                "tau": r.get("tau"),
                "complete": bool((r.get("completeness") or {}).get("complete")),
            }
        )

    # Bootstrap Spearman(rel_tick, spread) across venue-days
    xs = np.array([float(r["rel_tick"]) for r in flat if np.isfinite(r.get("rel_tick") or np.nan)])
    ys = np.array(
        [float(r["quoted_spread_bps"]) for r in flat if np.isfinite(r.get("quoted_spread_bps") or np.nan)]
    )
    n = min(xs.size, ys.size)
    xs, ys = xs[:n], ys[:n]
    rho = spearman_r(xs, ys) if n >= 3 else float("nan")

    def _boot_rho(arr_pair: np.ndarray) -> float:
        # unused signature for bootstrap_ci on indices
        return rho

    # index bootstrap
    rng = np.random.default_rng(11)
    boots = []
    if n >= 3:
        for _ in range(500):
            idx = rng.integers(0, n, size=n)
            boots.append(spearman_r(xs[idx], ys[idx]))
    boots_a = np.asarray(boots, dtype=np.float64)
    boots_a = boots_a[np.isfinite(boots_a)]
    if boots_a.size:
        lo, hi = np.quantile(boots_a, [0.025, 0.975])
        rho_ci = {"point": float(rho), "lo": float(lo), "hi": float(hi), "n": int(n)}
    else:
        rho_ci = {"point": float("nan"), "lo": float("nan"), "hi": float("nan"), "n": int(n)}

    fm_early = fama_macbeth_slope(
        [r for r in flat if r["day"] in early], y_key="quoted_spread_bps", x_key="rel_tick"
    )
    fm_late = fama_macbeth_slope(
        [r for r in flat if r["day"] in late], y_key="quoted_spread_bps", x_key="rel_tick"
    )
    hour_t = (fm.get("hour_quoted_spread_bps") or {}).get("t", float("nan"))
    day_t = (fm.get("quoted_spread_bps") or {}).get("t", float("nan"))

    # Gate honesty: day-level FM is dominated by cross-venue τ gaps (HL vs Deribit),
    # not within-venue τ/mid — Hold, do not Promote as FM replication.
    xvenue_confound = True
    promote_taxonomy = True
    promote_constraint_hl = False  # overlaps mmip without incremental falsifier → Hold
    kill_vanity_rdd = True
    kill_welfare = True
    kill_sec = True
    hit_rate = score["scorecard"].get("hit_rate")
    kill_sign_tradable = True  # theory scorecard not tradable at any hit_rate on this slice

    gates = {
        "disc.tick_rq_taxonomy": {
            "decision": "Promote",
            "why": "framing taxonomy vs mmip tick.*; not a numeric claim",
        },
        "disc.expected_sign_matrix": {
            "decision": "Hold",
            "why": f"codified pp.20–29; crypto scorecard hit_rate={hit_rate} n={n}",
        },
        "liq.fm_rel_tick_spread": {
            "decision": "Hold",
            "why": (
                f"day FM t={day_t}; hour FM t={hour_t}; early t={fm_early.get('t')} late t={fm_late.get('t')}; "
                "xvenue τ-gap confound — not clean within-venue FM"
            ),
        },
        "liq.rho_rel_tick_spread": {
            "decision": "Hold",
            "why": f"Spearman ρ={rho_ci['point']:.3g} CI95=[{rho_ci['lo']:.3g},{rho_ci['hi']:.3g}] n={rho_ci['n']}",
        },
        "exec.tick_constrained_flag": {
            "decision": "Hold",
            "why": "HL frac_constrained≈0.99 overlaps mmip tick.frac_one_tick — cross-link only",
        },
        "exec.undercut_rate": {
            "decision": "Hold",
            "why": "L0 tighten proxy only; no queue ID",
        },
        "frag.xvenue_tau_gap": {
            "decision": "Hold",
            "why": "HL τ=0.1 vs Deribit τ=0.05 stable; Kraken spot L2 native but spot≠PF futures market",
        },
        "frag.grid_pressure": {
            "decision": "Hold",
            "why": "feature computed; residual MQ Δ needs FE / wider sample",
        },
        "id.lse_nasdaq_rdd_literal": {
            "decision": "Kill",
            "why": "no sovereign tick ladder / vanity RD",
        },
        "id.welfare_tick": {"decision": "Kill", "why": "unobservable"},
        "id.sec_ipo_channel": {"decision": "Kill", "why": "out of scope"},
        "disc.sign_scorecard_tradable": {
            "decision": "Kill",
            "why": f"hit_rate={hit_rate} on ETH slice; not a tradable signal",
        },
    }

    OUT.mkdir(parents=True, exist_ok=True)
    artifact = {
        "days": days,
        "early": early,
        "late": late,
        "rho_ci": rho_ci,
        "fm_early": fm_early,
        "fm_late": fm_late,
        "hour_fm_t": hour_t,
        "day_fm_t": day_t,
        "scorecard": score["scorecard"],
        "gates": gates,
        "n_complete": sum(1 for r in rows if (r.get("completeness") or {}).get("complete")),
        "n_tob": sum(1 for r in rows if r.get("tob_ok")),
        "flags": {
            "xvenue_confound": xvenue_confound,
            "promote_taxonomy": promote_taxonomy,
            "promote_constraint_hl": promote_constraint_hl,
            "kill_vanity_rdd": kill_vanity_rdd,
            "kill_welfare": kill_welfare,
            "kill_sec": kill_sec,
            "kill_sign_tradable": kill_sign_tradable,
        },
    }
    (OUT / "hardening_gates.json").write_text(json.dumps(artifact, indent=2, default=str))

    # DESK_MEMO
    board_lines = [
        "| ID | Formula / clock | Monitor | Tradable | Exec throttle | Decision |",
        "|----|-----------------|---------|----------|---------------|----------|",
    ]
    meta = {
        "disc.tick_rq_taxonomy": ("RQ taxonomy · framing", "yes", "no", "no"),
        "disc.expected_sign_matrix": ("deck pp.20–29 signs", "yes", "no", "no"),
        "liq.fm_rel_tick_spread": ("FM y~τ/mid · UTC-day/hour", "maybe", "no", "no"),
        "liq.rho_rel_tick_spread": ("Spearman(τ/mid, spread)", "maybe", "no", "no"),
        "exec.tick_constrained_flag": ("spread≤2 ticks", "yes", "no", "maybe"),
        "exec.undercut_rate": ("L0 tighten ≤1.5 ticks", "maybe", "no", "maybe"),
        "frag.xvenue_tau_gap": ("HL↔Deribit↔Kraken Δτ", "yes", "no", "maybe"),
        "frag.grid_pressure": ("Δ(τ/mid) | τ fixed", "maybe", "no", "no"),
        "id.lse_nasdaq_rdd_literal": ("equity RDD template", "no", "no", "no"),
        "id.welfare_tick": ("welfare", "no", "no", "no"),
        "id.sec_ipo_channel": ("SEC/IPO", "no", "no", "no"),
        "disc.sign_scorecard_tradable": ("sign hit-rate", "no", "no", "no"),
    }
    for gid, g in gates.items():
        formula, mon, trad, thr = meta[gid]
        board_lines.append(
            f"| `{gid}` | {formula} | {mon} | {trad} | {thr} | **{g['decision']}** — {g['why'][:90]} |"
        )

    n_promote = sum(1 for g in gates.values() if g["decision"] == "Promote")
    n_hold = sum(1 for g in gates.values() if g["decision"] == "Hold")
    n_kill = sum(1 for g in gates.values() if g["decision"] == "Kill")

    desk = f"""# Desk memo — Tick Size Viewpoints (Rindi et al. MMCV #3 2014)

**Audience:** crypto MM / SOR / execution / taker / risk / research  
**Source:** Rindi et al. *Tick Size: Theory and Evidence* slides (Paris 2014-12-11) → `research/books/mm_confr_viewpoints/`  
**Philosophy:** lenses `risk | info | exec | disc | cont | liq | mm` — tick objects are **not** automatically tradable.  
**Data:** warehouse trades + collector/warehouse TOB on **HL + Deribit + Kraken** — **no ClickHouse MCP**.  
**Program status:** Hardened — **{n_promote} Promote / {n_hold} Hold / {n_kill} Kill**.  
**SoT:** [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) · Lib: [`../../lib/ticksize.py`](../../lib/ticksize.py) · Loaders: [`scripts/_data.py`](scripts/_data.py).

---

## 1. Desk jobs × intended outputs

| Job | Deck object | Tentative desk label | Status |
|-----|-------------|----------------------|--------|
| **Quote regime monitor** | Relative tick; frac 1-tick | Risk / quoting regime (cross-link mmip) | Hold — overlap |
| **Make / take aggressiveness** | Tick-constrained undercutting | Fragility monitor | Hold |
| **Liquidity split** | Liquid vs less-liquid × Δ(rel tick) | Heterogeneous MQ | Hold — thin terciles |
| **SOR / x-venue** | Cross-venue τ gap + grid pressure | Venue preference | Hold |
| **Prediction scorecard** | Expected-sign matrix pp. 20–29 | Theory→crypto hit rate | Hold matrix / Kill as tradable |
| **Competing defs** | vs mmip `tick.*` | Cross-link only | Promote taxonomy framing |

---

## 2. Signal board (Pass 2 + hardening)

{chr(10).join(board_lines)}

**Kill list:** literal LSE/Nasdaq RDD; welfare; SEC/IPO; sign-scorecard-as-tradable  
**Hold blockers:** x-venue τ confound for FM; Kraken futures PF still L2-absent (spot L2 now native); mmip descriptor overlap; thin Deribit L2 cadence

---

## 3. Venue completeness (locked)

| Venue | Role | TOB in slice | Notes |
|-------|------|--------------|-------|
| Hyperliquid | DEX anchor | Yes (collector + l2_rebuild) | τ≈0.1 ETH; ~99% tick-constrained |
| Deribit | CEX perps | Yes (warehouse L2 TOB) | τ≈0.05; wider spreads; sparse L2 |
| Kraken | CEX futures | Synth BBO from trades | Tick inference fragile — flag source |

Slice: ETH days {", ".join(days)} — complete venue-days {artifact["n_complete"]}/9; TOB {artifact["n_tob"]}/9.

**Figures (desk board):** see `out/<pkg>/figs/` — coverage, sign_matrix, scorecard, scatter_mq, fm_coefs, time_split, frac_constrained, spread_ticks_hist, relax_events, tercile_interaction, placebo, tau_gap_heatmap, mq_vs_gap, grid_pressure, signal_board. Notebook: [`notebooks/desk_synthesis.ipynb`](notebooks/desk_synthesis.ipynb).

---

## 4. Next gate (optional backlog)

1. Kraken futures PF L2 ingest (spot L2 already wired; drop remaining trade_synth for PF joins).  
2. Within-venue hourly FM with vol/OFI controls (remove x-venue confound).  
3. Constraint-relax event study for exec throttle Promote.  
4. Widen BTC after within-venue FM clears.
"""
    (BOOK / "DESK_MEMO.md").write_text(desk)

    # CHAPTER_INDEX status update
    idx = (BOOK / "CHAPTER_INDEX.md").read_text()
    idx = idx.replace(
        "**Program status:** Scaffold in progress → Pass 1/2 on ETH HL+Deribit+Kraken.",
        f"**Program status:** **Hardened** — {n_promote} Promote / {n_hold} Hold / {n_kill} Kill on ETH HL+Deribit+Kraken slice.",
    )
    for old, new in [
        ("| `ch00_overview` |", "| `ch00_overview` |"),
    ]:
        pass
    # status cells
    replacements = {
        "| Taxonomy vs mmip `tick.*`; signal roadmap | `notes` |": "| Taxonomy vs mmip `tick.*`; signal roadmap | `exp_run` |",
        "| Map cells → desk metric + falsifier; Kill welfare/SEC | `notes` |": "| Map cells → desk metric + falsifier; Kill welfare/SEC | `exp_run` |",
        "| Markout by rel-tick quartile; time-split; vs mmip `rel_tick_bps` | `todo` |": "| Markout by rel-tick quartile; time-split; vs mmip `rel_tick_bps` | `exp_run` |",
        "| Queue/cancel proxy; OFI/VPIN around relax bursts; exec throttle vs fragility | `todo` |": "| Queue/cancel proxy; OFI/VPIN around relax bursts; exec throttle vs fragility | `exp_run` |",
        "| Placebo price moves; exec make/take hypothesis | `todo` |": "| Placebo price moves; exec make/take hypothesis | `exp_run` |",
        "| Concordance; FEI/Epps; SOR venue preference | `todo` |": "| Concordance; FEI/Epps; SOR venue preference | `exp_run` |",
        # also if already iterate
        "| Markout by rel-tick quartile; time-split; vs mmip `rel_tick_bps` | `iterate` |": "| Markout by rel-tick quartile; time-split; vs mmip `rel_tick_bps` | `exp_run` |",
        "| Queue/cancel proxy; OFI/VPIN around relax bursts; exec throttle vs fragility | `iterate` |": "| Queue/cancel proxy; OFI/VPIN around relax bursts; exec throttle vs fragility | `exp_run` |",
        "| Placebo price moves; exec make/take hypothesis | `iterate` |": "| Placebo price moves; exec make/take hypothesis | `exp_run` |",
        "| Concordance; FEI/Epps; SOR venue preference | `iterate` |": "| Concordance; FEI/Epps; SOR venue preference | `exp_run` |",
    }
    for a, b in replacements.items():
        idx = idx.replace(a, b)

    # two-pass checklist mark done
    idx = idx.replace("- [ ] Extract PDF prediction tables", "- [x] Extract PDF prediction tables")
    idx = idx.replace("- [ ] Implement objects on real", "- [x] Implement objects on real")
    idx = idx.replace("- [ ] Baseline plots + EXP_REPORT", "- [x] Baseline plots + EXP_REPORT")
    idx = idx.replace("- [ ] Draft CANDIDATES", "- [x] Draft CANDIDATES")
    idx = idx.replace("- [ ] Info around tick regimes", "- [x] Info around tick regimes")
    idx = idx.replace("- [ ] Signal labels:", "- [x] Signal labels:")
    idx = idx.replace("- [ ] Competing defs", "- [x] Competing defs")
    idx = idx.replace("- [ ] Falsifiers:", "- [x] Falsifiers:")
    idx = idx.replace("- [ ] CANDIDATES + notebook", "- [x] CANDIDATES + notebook")

    promote_table = f"""## Promote rollup

| Candidate | risk | info | exec | disc | cont | liq | mm | Ch | One-line use |
|-----------|:----:|:----:|:----:|:----:|:----:|:---:|:--:|----|--------------|
| `disc.tick_rq_taxonomy` |  |  |  | ✓ |  |  | ✓ | ch00_overview | Taxonomy vs mmip tick.*; reading order |

**Kill:**
- `id.lse_nasdaq_rdd_literal` — no sovereign tick ladder / vanity RD
- `id.welfare_tick` — unobservable
- `id.sec_ipo_channel` — out of scope
- `disc.sign_scorecard_tradable` — hit_rate={score['scorecard'].get('hit_rate')} on ETH slice

**Hold:**
- `disc.expected_sign_matrix` — codified; crypto analogue fragile
- `liq.fm_rel_tick_spread` / `liq.rho_rel_tick_spread` — x-venue confound; bootstrap CI on ρ
- `exec.tick_constrained_flag` / `exec.undercut_rate` — mmip overlap / L0 proxy
- `frag.xvenue_tau_gap` / `frag.grid_pressure` — Kraken synth TOB; needs FE
"""
    import re

    idx = re.sub(
        r"## Promote rollup\n\n.*?\n---\n\n## Crypto adaptation",
        promote_table + "\n---\n\n## Crypto adaptation",
        idx,
        count=1,
        flags=re.S,
    )
    (BOOK / "CHAPTER_INDEX.md").write_text(idx)

    # Build PNG figures + full desk_synthesis notebook
    import subprocess

    fig_script = Path(__file__).resolve().parent / "exp_build_figs.py"
    rc = subprocess.call([sys.executable, str(fig_script)], cwd=str(BOOK))
    if rc != 0:
        print(f"WARNING: exp_build_figs exited {rc}", flush=True)

    # refresh ch00 candidates already Promote taxonomy
    print(json.dumps({"promote": n_promote, "hold": n_hold, "kill": n_kill, "rho_ci": rho_ci}, indent=2))


if __name__ == "__main__":
    main()
