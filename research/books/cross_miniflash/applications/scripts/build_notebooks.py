#!/usr/bin/env python3
"""Build application notebooks with formulas + embedded result pointers."""

from __future__ import annotations

import json
from pathlib import Path

import nbformat as nbf

APP = Path(__file__).resolve().parents[1]
OUT = APP / "out"
BOARD = json.loads((OUT / "applications_board.json").read_text()) if (OUT / "applications_board.json").exists() else {}


def _md(s: str) -> nbf.NotebookNode:
    return nbf.v4.new_markdown_cell(s)


def _code(s: str) -> nbf.NotebookNode:
    return nbf.v4.new_code_cell(s)


def build_kill_ladder() -> None:
    nb = nbf.v4.new_notebook()
    b = BOARD.get("kill_ladder", {})
    nb.cells = [
        _md(
            f"""# Gated SSM kill-ladder

RISK track · gate 10bps/ic5 · within-gated z percentiles + intensity + Nanex nest.

**Readiness:** `{b.get('readiness')}` · promote_as_risk_policy={b.get('promote_as_risk_policy')}

## Ladder

| Tier | Trigger | Action |
|------|---------|--------|
| observe | \|z\| < p25, I=1 | log |
| widen | p25–p50 or I=2 | soft clip |
| size_cap | ≥p75 or I∈{{3,4}} | size cap |
| halt | I≥5 or Nanex∧I≥2 or \|ΔP\|≥p90 | halt aggressive |

Breaks this slice: `{b.get('ladder_breaks')}`

## Outcome formulas

Rolling intensity \(I_i(60s)=\#{{j:t_j\\in(t_i-60,t_i]}}\).

Tape markout \(\\mathrm{{mo}}_h=d\\cdot(p_{{t+h}}-p_t)/p_t\\times10^4\) bps.

Friction haircut 2 bps one-way; no fantasy fills.
"""
        ),
        _code(
            """
import json
from pathlib import Path
import matplotlib.pyplot as plt
from IPython.display import Image, display

OUT = Path('../../out/kill_ladder')
s = json.loads((OUT/'summary.json').read_text())
print('tiers', s['tier_counts'])
print('abs_mo fire-ctrl', s['policy']['abs_mo_elevation_fire_vs_ctrl'])
print('readiness', s['policy']['readiness'])
print('sign_stable', s['time_split']['sign_stable'])
for fig in sorted((OUT/'figs').glob('*.png')):
    display(Image(filename=str(fig)))
"""
        ),
    ]
    path = APP / "kill_ladder" / "kill_ladder.ipynb"
    nbf.write(nb, path)
    print("wrote", path)


def build_nanex() -> None:
    nb = nbf.v4.new_notebook()
    b = BOARD.get("nanex_burst", {})
    nb.cells = [
        _md(
            f"""# Nanex∩SSM burst escalate

Precision = P(SSM | Nanex) ≈ **{b.get('precision')}**.

Treat = gated SSM ∩ Nanex; control = SSM-only.

**Tag:** `{b.get('tag_readiness')}` · **Auto-pull:** `{b.get('auto_pull_readiness')}`
"""
        ),
        _code(
            """
import json
from pathlib import Path
from IPython.display import Image, display
OUT = Path('../../out/nanex_burst')
s = json.loads((OUT/'summary.json').read_text())
print('n_nested', s['n_nested'], 'precision', s['nanex_precision_pooled'])
print('Δ|ΔP|', s['effects_nested_minus_ssm_only']['dp'])
print('Δ|mo|', s['effects_nested_minus_ssm_only']['abs_mo_5s'])
for fig in sorted((OUT/'figs').glob('*.png')):
    display(Image(filename=str(fig)))
"""
        ),
    ]
    nbf.write(nb, APP / "nanex_burst" / "nanex_burst.ipynb")


def build_hl() -> None:
    nb = nbf.v4.new_notebook()
    b = BOARD.get("hl_thin_sor", {})
    nb.cells = [
        _md(
            f"""# HL thin-excess + crash-share SOR

Crash share: `{b.get('crash_share')}`

Thin excess mean CI: `{b.get('thin_excess_mean')}`

**Monitor:** `{b.get('monitor')}` · **Rule:** `{b.get('readiness')}`

Venue-local counterfactuals only (concordance Hold).
"""
        ),
        _code(
            """
import json
from pathlib import Path
from IPython.display import Image, display
OUT = Path('../../out/hl_thin_sor')
s = json.loads((OUT/'summary.json').read_text())
print('HL fire vs thick |mo|', s['hl_fire_vs_thick']['abs_mo'])
print('SOR schedule', s['sor_schedule'])
for fig in sorted((OUT/'figs').glob('*.png')):
    display(Image(filename=str(fig)))
"""
        ),
    ]
    nbf.write(nb, APP / "hl_thin_sor" / "hl_thin_sor.ipynb")


def build_hv() -> None:
    nb = nbf.v4.new_notebook()
    b = BOARD.get("hv_fei_capacity", {})
    nb.cells = [
        _md(
            f"""# H^v / FEI → child sizing

\\(H^v=\\sum s_k^2\\), FEI = Shannon/\(\\log N\\).

POV honesty: constant-π VWAP impact is **π-invariant**; schedule binds via max_child.

**Readiness:** `{b.get('readiness')}` · exposure_cut={b.get('exposure_cut')}
"""
        ),
        _code(
            """
import json
from pathlib import Path
from IPython.display import Image, display
OUT = Path('../../out/hv_fei_capacity')
s = json.loads((OUT/'summary.json').read_text())
print('spearman', s['spearman'])
print('pov high-H', (s.get('pov') or {}).get('sched_vs_flat_exposure_high_H'))
print('filled qty high-H', (s.get('pov') or {}).get('sched_vs_flat_filled_qty_high_H'))
for fig in sorted((OUT/'figs').glob('*.png')):
    display(Image(filename=str(fig)))
"""
        ),
    ]
    nbf.write(nb, APP / "hv_fei_capacity" / "hv_fei_capacity.ipynb")


def main() -> None:
    # refresh board snapshot used in markdown
    if (OUT / "kill_ladder" / "summary.json").exists():
        import sys

        sys.path.insert(0, str(APP / "scripts"))
        from _common import save_json, jsonable

        s1 = json.loads((OUT / "kill_ladder" / "summary.json").read_text())
        s2 = json.loads((OUT / "nanex_burst" / "summary.json").read_text())
        s3 = json.loads((OUT / "hl_thin_sor" / "summary.json").read_text())
        s4 = json.loads((OUT / "hv_fei_capacity" / "summary.json").read_text())
        board = {
            "kill_ladder": {
                "readiness": s1["policy"]["readiness"],
                "promote_as_risk_policy": s1["policy"]["promote_as_risk_policy"],
                "n_gated": s1["n_gated_events"],
                "tier_counts": s1["tier_counts"],
                "ladder_breaks": s1.get("ladder_breaks"),
                "abs_mo_delta": s1["policy"]["abs_mo_elevation_fire_vs_ctrl"],
                "friction_cleared": s1["policy"]["friction_cleared"],
                "sign_stable": s1["time_split"]["sign_stable"],
                "v_share_fire": s1["policy"]["false_positive_v_share_among_fire"],
            },
            "nanex_burst": {
                "tag_readiness": s2["policy"]["tag_readiness"],
                "auto_pull_readiness": s2["policy"]["auto_pull_readiness"],
                "promote_as_risk_policy": s2["policy"]["promote_as_risk_policy"],
                "n_nested": s2["n_nested"],
                "precision": s2["nanex_precision_pooled"],
                "dp_effect": s2["effects_nested_minus_ssm_only"]["dp"],
                "abs_mo_effect": s2["effects_nested_minus_ssm_only"]["abs_mo_5s"],
                "sign_stable": s2["time_split"]["sign_stable"],
            },
            "hl_thin_sor": {
                "readiness": s3["policy"]["readiness"],
                "monitor": s3["policy"]["monitor_readiness"],
                "promote_as_risk_policy": s3["policy"]["promote_as_risk_policy"],
                "crash_share": s3["crash_share_gated"],
                "thin_excess_mean": s3["thin_excess_mean"],
                "delta_abs_mo": s3["hl_fire_vs_thick"]["abs_mo"],
                "sign_stable": s3["time_split"]["sign_stable"],
            },
            "hv_fei_capacity": {
                "readiness": s4["policy"]["readiness"],
                "monitor": s4["policy"]["monitor_readiness"],
                "promote_as_risk_policy": s4["policy"]["promote_as_risk_policy"],
                "spearman": s4["spearman"],
                "pov_high_H_exposure": (s4.get("pov") or {}).get("sched_vs_flat_exposure_high_H"),
                "pov_high_H_qty": (s4.get("pov") or {}).get("sched_vs_flat_filled_qty_high_H"),
                "exposure_cut": s4["policy"].get("exposure_cut_vs_flat"),
            },
        }
        save_json(OUT / "applications_board.json", board)
        global BOARD
        BOARD = board
    build_kill_ladder()
    build_nanex()
    build_hl()
    build_hv()


if __name__ == "__main__":
    main()
