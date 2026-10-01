from __future__ import annotations
#!/usr/bin/env python3
"""Core V-statistic + bootstrap_sim empirics (Pass 1+2) for v_shapes.

Runs on HL + Deribit + Kraken ETH complete UTC days when warehouse is up.
Also always runs Models 0–3 size/power (synthetic) and writes chapter artifacts.
ClickHouse MCP banned — warehouse / startarb loaders only.
"""

import os

import argparse
import json
import sys
from pathlib import Path

import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(Path(os.environ.get('WAREHOUSE_SRC') or ((Path(os.environ.get('WAREHOUSE_ROOT') or (Path.home() / 'lab' / 'lab-n2070' / 'warehouse')) / 'src')))))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb')) / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import (  # noqa: E402
    CORE_VENUES,
    ensure_env,
    load_day_trades,
    resolve_days,
)
from research.lib.vstat import (  # noqa: E402
    ASYMPTOTIC_BAND_95,
    ASYMPTOTIC_BAND_99,
    bootstrap_minv_ci,
    grid_1s,
    min_v,
    preaverage_returns,
    returns_from_log_px,
    size_power_table,
    v_path,
)

OUT_V = BOOK / "out" / "v_statistic"
OUT_B = BOOK / "out" / "bootstrap_sim"
HN_MIN = (1, 5, 30)  # minutes


def _hn_seconds(m: int) -> float:
    return float(m * 60)


def _day_vstat(
    tape: dict,
    hn_s: float,
    *,
    n_grid: int = 101,
    preavg_kn: int = 1,
    dt_s: float = 5.0,
    n_boot: int = 40,
) -> dict:
    g = grid_1s(tape["ts"], tape["px"], dt_s=dt_s)
    if int(g["n_filled"]) < 60:
        return {"ok": False, "reason": "short_grid", "n_filled": int(g["n_filled"])}
    t, r = returns_from_log_px(
        g["log_px"], g["ts_ns"], time_unit_s=1.0, preavg_kn=preavg_kn
    )
    # hn and t are in seconds
    if r.size < 60:
        return {"ok": False, "reason": "short_returns", "n": int(r.size)}
    t0, t1 = float(t[0] + hn_s), float(t[-1] - hn_s)
    if t1 <= t0:
        return {"ok": False, "reason": "hn_too_wide"}
    taus = np.linspace(t0, t1, n_grid)
    mv = min_v(t, r, taus, hn_s)
    path = mv["path"]
    V = path["V"]
    boot = bootstrap_minv_ci(
        r, hn_s, n_paths=n_boot, n_grid=min(n_grid, 41), rng=np.random.default_rng(0), dt_s=float(g["dt_s"])
    )
    q5 = boot["quantiles"].get(0.05, float("nan"))
    q1 = boot["quantiles"].get(0.01, float("nan"))
    sig5 = bool(np.isfinite(mv["min_v"]) and np.isfinite(q5) and mv["min_v"] < q5)
    sig1 = bool(np.isfinite(mv["min_v"]) and np.isfinite(q1) and mv["min_v"] < q1)
    leadlag = {}
    if np.isfinite(V).sum() > 20:
        r2 = r * r
        ti = np.searchsorted(t, path["tau"])
        ti = np.clip(ti, 0, r.size - 2)
        for k in (1, 6, 12):  # steps on dt grid ≈ 5s,30s,60s if dt=5
            fut = r2[np.clip(ti + k, 0, r.size - 1)]
            m = np.isfinite(V) & np.isfinite(fut)
            if m.sum() > 20:
                leadlag[f"corr_V_r2_step{k}"] = float(np.corrcoef(V[m], fut[m])[0, 1])
    return {
        "ok": True,
        "min_v": mv["min_v"],
        "tau_star_s": mv["tau_star"],
        "shape": mv["shape"],
        "T_minus": mv["T_minus"],
        "T_plus": mv["T_plus"],
        "sig_5": sig5,
        "sig_1": sig1,
        "q05": q5,
        "q01": q1,
        "coverage": float(g["coverage"]),
        "n_grid_px": int(g["n_filled"]),
        "dt_s": float(g["dt_s"]),
        "V_mean": float(np.nanmean(V)),
        "V_p10": float(np.nanpercentile(V[np.isfinite(V)], 10)) if np.isfinite(V).any() else float("nan"),
        "leadlag": leadlag,
        "boot_n_paths": boot["n_paths"],
        "asymptotic_bands_kill": {"95": ASYMPTOTIC_BAND_95, "99": ASYMPTOTIC_BAND_99},
    }


def run_bootstrap_sim(fast: bool) -> dict:
    OUT_B.mkdir(parents=True, exist_ok=True)
    n = 2_500 if fast else 5_000
    n_mc = 20 if fast else 40
    n_boot = 20 if fast else 40
    table = size_power_table(n=n, n_mc=n_mc, hn=0.05, n_grid=41, n_boot=n_boot)
    path = OUT_B / "size_power_models0_3.json"
    path.write_text(json.dumps(table, indent=2, default=str))
    # Kill note artifact
    (OUT_B / "kill_asymptotic_bands.json").write_text(
        json.dumps(
            {
                "band_95": ASYMPTOTIC_BAND_95,
                "band_99": ASYMPTOTIC_BAND_99,
                "decision": "Kill",
                "reason": "paper §3.1: too small for realistic DGP + multiple testing; use EGARCH bootstrap",
            },
            indent=2,
        )
    )
    return table


def run_venues(symbol: str, days: list[str], *, max_files: int, fast: bool) -> dict:
    OUT_V.mkdir(parents=True, exist_ok=True)
    ensure_env()
    panel: dict = {"symbol": symbol, "days": days, "venues": {}, "hn_min": list(HN_MIN)}
    n_grid = 41 if fast else 61
    n_boot = 20 if fast else 40
    dt_s = 5.0
    for venue in CORE_VENUES:
        panel["venues"][venue] = {}
        for day in days:
            try:
                rec = load_day_trades(venue, symbol, day, max_files=max_files, quiet=True)
            except Exception as exc:  # noqa: BLE001
                panel["venues"][venue][day] = {
                    "error": f"{type(exc).__name__}: {exc}",
                    "completeness": {"complete": False},
                }
                continue
            day_out: dict = {
                "completeness": rec["completeness"],
                "instrument": rec.get("instrument"),
                "hn": {},
            }
            tape = rec["tape"]
            for hm in HN_MIN:
                hn_s = _hn_seconds(hm)
                try:
                    day_out["hn"][str(hm)] = _day_vstat(
                        tape, hn_s, n_grid=n_grid, preavg_kn=1, dt_s=dt_s, n_boot=n_boot
                    )
                    if hm == 5:
                        day_out["hn"]["5_preavg5"] = _day_vstat(
                            tape, hn_s, n_grid=n_grid, preavg_kn=5, dt_s=dt_s, n_boot=max(10, n_boot // 2)
                        )
                except Exception as exc:  # noqa: BLE001
                    day_out["hn"][str(hm)] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            panel["venues"][venue][day] = day_out
    (OUT_V / f"panel_{symbol.lower()}.json").write_text(json.dumps(panel, indent=2, default=str))
    return panel


def _write_reports(panel: dict, boot: dict) -> None:
    ch_v = BOOK / "chapters" / "v_statistic"
    ch_b = BOOK / "chapters" / "bootstrap_sim"
    ch_v.mkdir(parents=True, exist_ok=True)
    ch_b.mkdir(parents=True, exist_ok=True)

    # summarize significant days
    rows = []
    for venue, days in panel.get("venues", {}).items():
        for day, rec in days.items():
            if "error" in rec:
                rows.append(f"- {venue} {day}: LOAD_ERROR {rec['error']}")
                continue
            comp = rec.get("completeness", {})
            for hm, res in rec.get("hn", {}).items():
                if not isinstance(res, dict) or not res.get("ok"):
                    continue
                rows.append(
                    f"- {venue} {day} hn={hm}m: MinV={res['min_v']:.3f} shape={res['shape']} "
                    f"sig5={res['sig_5']} sig1={res['sig_1']} complete={comp.get('complete')} "
                    f"n={comp.get('n')} coverage_grid={res.get('coverage', float('nan')):.2f}"
                )

    (ch_v / "EXP_REPORT.md").write_text(
        "\n".join(
            [
                "# V-statistic — EXP_REPORT (Pass 1+2)",
                "",
                f"## Sample",
                f"- Symbol: `{panel.get('symbol')}`",
                f"- Days: {panel.get('days')}",
                f"- Venues: HL + Deribit + Kraken",
                "- Grid: 5s last-print (desk speed; paper uses 1s); hn in {1,5,30} min; EGARCH bootstrap",
                "",
                "## Per-venue / day MinV",
                *rows,
                "",
                "## Pass 2 notes",
                "- Continuous V_t summaries (V_mean, V_p10) and lead-lag vs future r^2 in JSON.",
                "- Pre-avg sensitivity: key `5_preavg5` vs `5`.",
                "- Asymptotic bands 2.18/3.60: **Kill** as desk defaults (see bootstrap_sim).",
                "",
                "## Figures / artifacts",
                f"- `{OUT_V.relative_to(BOOK)}/panel_{str(panel.get('symbol','eth')).lower()}.json`",
                "",
                "## Certification",
                "- UTC-day clip + day-completeness flags from `scripts/_data.py`.",
                "- Incomplete days flagged; do not Promote on thin tails alone.",
                "",
            ]
        )
    )

    boot_rows = []
    for k, v in boot.items():
        if k == "meta":
            continue
        boot_rows.append(
            f"- Model {k}: rej@5%={v['pct_rej_5']:.1f}% rej@1%={v['pct_rej_1']:.1f}% "
            f"mean_MinV={v['mean_minv']:.3f} (n_mc={v['n_mc']})"
        )
    (ch_b / "EXP_REPORT.md").write_text(
        "\n".join(
            [
                "# Bootstrap / simulations — EXP_REPORT (Pass 1+2)",
                "",
                "## Size / power (Models 0–3)",
                *boot_rows,
                "",
                f"Meta: {json.dumps(boot.get('meta', {}))}",
                "",
                "## Kill",
                f"- Asymptotic |V| bands **{ASYMPTOTIC_BAND_95} / {ASYMPTOTIC_BAND_99}**: Kill as desk defaults.",
                "- Use EGARCH simulated bootstrap quantiles for MinV.",
                "",
                "## Artifacts",
                f"- `{OUT_B.relative_to(BOOK)}/size_power_models0_3.json`",
                f"- `{OUT_B.relative_to(BOOK)}/kill_asymptotic_bands.json`",
                "",
            ]
        )
    )

    (ch_v / "CANDIDATES.md").write_text(
        "| id | type | lenses | decision | falsifier |\n"
        "|----|------|--------|----------|-----------|\n"
        "| `risk.minv_egarch` | D | risk, info | **Hold** → Promote after panel time-split | incomplete days; hn fragility; sig only on thin tape |\n"
        "| `info.v_path_continuous` | D | info, cont | **Hold** | lead-lag vs mid/markout flat |\n"
        "| `info.tpm_features` | D | info | **Hold** | no incremental R2 vs MinV binary |\n"
        "| `geom.crash_vshape` | baseline | risk | **cross-link only** | not Flora-Reno — see `crash.vshape_events` |\n"
        "\n"
        "Pass-2: continuous V_t / T+/- stored in panel JSON; pre-avg sensitivity on 5m.\n"
    )
    (ch_b / "CANDIDATES.md").write_text(
        """| id | type | lenses | decision | falsifier |
|----|------|--------|----------|-----------|
| `risk.egarch_minv_bands` | D | risk | **Promote** (CI source) | bootstrap degeneracy / n_paths too low |
| `risk.asymptotic_218_360` | D | risk | **Kill** | paper §3.1 + size/power over-reject risk |
| `sim.models_0_3_sizepower` | sim | disc | **Hold** (desk-scale MC) | full N=1000 not run |

Crypto DGP: reuse Model 3 path shape on 1s crypto grid in later stress days (`event_case`).
"""
    )


def _write_notebooks() -> None:
    """Minimal memo notebooks (nbformat-free JSON)."""
    for pkg, title in (
        ("v_statistic", "V-statistic Signal board"),
        ("bootstrap_sim", "Bootstrap / Models 0–3"),
    ):
        nb = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
            "cells": [
                {
                    "cell_type": "markdown",
                    "metadata": {},
                    "source": [
                        f"# {title}\n",
                        "\n",
                        "Imports `research.lib.vstat`. Artifacts under `out/`.\n",
                        "Geometric Dugast–Foucault lives in `crash.vshape_events` — do not merge.\n",
                    ],
                },
                {
                    "cell_type": "code",
                    "metadata": {},
                    "execution_count": None,
                    "outputs": [],
                    "source": [
                        "import json, sys\n",
                        "from pathlib import Path\n",
                        "ROOT = Path('../..').resolve().parents[1] if False else Path(os.environ.get('ARES_MICROSTRUCTURE') or (Path.home() / 'srv' / 'ares-microstructure'))\n",
                        "sys.path.insert(0, str(ROOT))\n",
                        "from research.lib.vstat import min_v, bootstrap_minv_ci, ASYMPTOTIC_BAND_95\n",
                        f"print('bands kill', ASYMPTOTIC_BAND_95)\n",
                        f"p = ROOT / 'research/books/v_shapes/out/{pkg}'\n",
                        "print('out', p, 'exists', p.exists())\n",
                    ],
                },
            ],
        }
        path = BOOK / "chapters" / pkg / f"{pkg}.ipynb"
        path.write_text(json.dumps(nb, indent=1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--n-days", type=int, default=5)
    ap.add_argument("--days", nargs="*", default=None)
    ap.add_argument("--max-files", type=int, default=24)
    ap.add_argument("--fast", action="store_true", help="Fewer MC / grid points")
    ap.add_argument("--skip-live", action="store_true")
    args = ap.parse_args()

    boot = run_bootstrap_sim(fast=args.fast)
    if args.skip_live:
        panel = {"symbol": args.symbol, "days": [], "venues": {}}
    else:
        try:
            ensure_env()
            days = resolve_days(args.days, venue="hyperliquid", n=args.n_days)
            panel = run_venues(args.symbol, days, max_files=args.max_files, fast=args.fast)
        except Exception as exc:  # noqa: BLE001
            panel = {
                "symbol": args.symbol,
                "days": args.days or [],
                "venues": {},
                "load_error": f"{type(exc).__name__}: {exc}",
            }
            OUT_V.mkdir(parents=True, exist_ok=True)
            (OUT_V / f"panel_{args.symbol.lower()}.json").write_text(
                json.dumps(panel, indent=2, default=str)
            )
    _write_reports(panel, boot)
    _write_notebooks()
    print(json.dumps({"bootstrap_meta": boot.get("meta"), "panel_days": panel.get("days"), "load_error": panel.get("load_error")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
