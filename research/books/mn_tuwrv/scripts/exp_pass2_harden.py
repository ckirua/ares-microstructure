from __future__ import annotations
#!/usr/bin/env python3
"""Pass 2 hardening for mn_tuwrv: larger MC, K/step ablation, trade-clock, BTC.

Updates estimators / monte_carlo / noise_proxy / xvenue EXP_REPORTs and
DESK_MEMO signal board inputs via JSON artifacts.

ClickHouse MCP banned.
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

from _data import CORE_VENUES, ensure_env, load_day_trades, resolve_days  # noqa: E402
from ares_micro.vol.tsrv import (  # noqa: E402
    all_estimators,
    estimators_trade_clock,
    grid_log_price_from_tape,
    k_step_ablation,
    log_returns,
    monte_carlo_estimators,
    noise_variance_proxy,
)

OUT = BOOK / "out" / "pass2"
OUT_MC = BOOK / "out" / "monte_carlo"


def run_mc(n_sims: int, seed: int = 42) -> dict:
    print(f"MC n_sims={n_sims} …", flush=True)
    summary = monte_carlo_estimators(n_sims=n_sims, K=300, step=300, seed=seed)
    OUT_MC.mkdir(parents=True, exist_ok=True)
    (OUT_MC / "mc_summary_pass2.json").write_text(json.dumps(summary, indent=2, default=str))
    # also refresh primary summary
    (OUT_MC / "mc_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    est = summary["estimators"]
    fourth_rmse = est["fourth"]["rmse"]
    adj_rmse = est["first_adj"]["rmse"]
    kill_sparse = bool(np.isfinite(adj_rmse) and np.isfinite(fourth_rmse) and adj_rmse < 0.75 * fourth_rmse)
    summary["gate"] = {
        "cont.sparse_rv_only": "Kill" if kill_sparse else "Hold",
        "why": f"first_adj_rmse={adj_rmse:.6g} fourth_rmse={fourth_rmse:.6g}",
    }
    ch = BOOK / "chapters" / "monte_carlo"
    lines = [
        "# Monte Carlo — EXP_REPORT (Pass 2)",
        "",
        f"## Sample\n- n_sims: {summary['n_sims']}\n- K: {summary['K']}  step: {summary['step']}",
        f"- Heston σ_ε={summary['heston']['noise_std']}",
        "",
        "| Estimator | Bias | Var | RMSE | n |",
        "|-----------|------|-----|------|---|",
    ]
    for name, row in est.items():
        lines.append(
            f"| {name} | {row['bias']:.6g} | {row['var']:.6g} | {row['rmse']:.6g} | {row['n']} |"
        )
    lines += [
        "",
        f"## Gate\n- `cont.sparse_rv_only` → **{summary['gate']['cont.sparse_rv_only']}** — {summary['gate']['why']}",
        f"- Artifact: `out/monte_carlo/mc_summary_pass2.json`",
        "",
    ]
    (ch / "EXP_REPORT.md").write_text("\n".join(lines))
    (ch / "CANDIDATES.md").write_text(
        "| id | type | lenses | decision | falsifier |\n"
        "|----|------|--------|----------|----------|\n"
        f"| `cont.tsrv_beats_sparse_mc` | sim | cont, risk | **Hold** (desk MC; not 25k) | enlarge n_sims |\n"
        f"| `cont.sparse_rv_only` | policy | cont | **{summary['gate']['cont.sparse_rv_only']}** | {summary['gate']['why']} |\n"
    )
    return summary


def run_panel(
    symbols: list[str],
    days: list[str],
    *,
    max_files: int,
    dt_s: float = 1.0,
) -> dict:
    rows = []
    for sym in symbols:
        for day in days:
            for venue in CORE_VENUES:
                print(f"pass2 {sym} {venue} {day} …", flush=True)
                try:
                    rec = load_day_trades(venue, sym, day, max_files=max_files, quiet=True)
                except Exception as exc:  # noqa: BLE001
                    rows.append(
                        {"ok": False, "symbol": sym, "venue": venue, "day": day, "reason": str(exc)}
                    )
                    continue
                tape = rec["tape"]
                comp = rec.get("completeness") or {}
                if int(tape.get("n", 0)) < 30:
                    rows.append(
                        {
                            "ok": False,
                            "symbol": sym,
                            "venue": venue,
                            "day": day,
                            "reason": "empty",
                        }
                    )
                    continue
                g = grid_log_price_from_tape(tape["ts"], tape["px"], dt_s=dt_s)
                cal = {}
                if int(g["n_filled"]) >= 60 and g["log_px"].size > 602:
                    est = all_estimators(g["log_px"], K=300, step=300)
                    nv = noise_variance_proxy(log_returns(g["log_px"]))
                    abl = k_step_ablation(g["log_px"])
                    cal = {
                        "noise_std": float(nv["noise_std"]),
                        "first_adj": float(est["first_adj"]),
                        "fifth": float(est["fifth"]),
                        "fourth": float(est["fourth"]),
                        "fifth_over_fourth": (
                            float(est["fifth"] / est["fourth"])
                            if est["fourth"] and np.isfinite(est["fourth"])
                            else float("nan")
                        ),
                        "ablation": {
                            "first_adj_cv": abl["first_adj_cv"],
                            "noise_std_cv": abl["noise_std_cv"],
                            "fragile_first_adj": abl["fragile_first_adj"],
                            "first_adj_range": abl["first_adj_range"],
                            "grid": abl["grid"],
                        },
                        "coverage": float(g["coverage"]),
                    }
                # trade clock: step in trades — use denser step (every 50 trades) / K=50
                tc = estimators_trade_clock(
                    tape["ts"], tape["px"], K=50, step=50, max_n=40_000
                )
                rows.append(
                    {
                        "ok": True,
                        "symbol": sym,
                        "venue": venue,
                        "day": day,
                        "complete": bool(comp.get("complete", False)),
                        "n_trades": int(tape.get("n", 0)),
                        "calendar": cal,
                        "trade_clock": tc,
                    }
                )
    return {"symbols": symbols, "days": days, "rows": rows}


def _gates(panel: dict, mc: dict) -> dict:
    rows = [r for r in panel["rows"] if r.get("ok") and r.get("calendar")]
    ratios = [
        r["calendar"]["fifth_over_fourth"]
        for r in rows
        if np.isfinite(r["calendar"].get("fifth_over_fourth", np.nan))
    ]
    tc_ratios = [
        r["trade_clock"]["fifth_over_fourth"]
        for r in panel["rows"]
        if r.get("ok") and r.get("trade_clock", {}).get("ok") and np.isfinite(r["trade_clock"].get("fifth_over_fourth", np.nan))
    ]
    fragile = sum(1 for r in rows if r["calendar"].get("ablation", {}).get("fragile_first_adj"))
    med_ratio = float(np.median(ratios)) if ratios else float("nan")
    med_tc = float(np.median(tc_ratios)) if tc_ratios else float("nan")
    # Kill noise-dominates calendar if median ratio not ≫ 1
    kill_cal_noise = bool(np.isfinite(med_ratio) and med_ratio < 1.5)
    # trade-clock: Promote as monitor only if median ratio ≫ 1.5 and majority
    promote_tc = bool(np.isfinite(med_tc) and med_tc >= 2.0 and len(tc_ratios) >= 4)
    hold_tc = bool(np.isfinite(med_tc) and med_tc >= 1.2 and not promote_tc)
    # TSRV first_adj: Hold if fragile ablation on any complete-ish row
    tsrv_decision = "Hold"
    tsrv_why = f"ablation_fragile_count={fragile}/{len(rows)}; need time-split Promote bar"
    if fragile == 0 and len(rows) >= 6:
        tsrv_why += "; ablation stable but still Hold (no Promote without out-of-sample)"
    # xvenue: compare noise ranks concordance within day
    by_day: dict[str, dict[str, float]] = {}
    for r in rows:
        key = f"{r['symbol']}|{r['day']}"
        by_day.setdefault(key, {})[r["venue"]] = r["calendar"]["noise_std"]
    concord = 0
    pairs = 0
    for key, m in by_day.items():
        vs = [m[v] for v in CORE_VENUES if v in m]
        if len(vs) < 2:
            continue
        # relative range
        pairs += 1
        if (max(vs) - min(vs)) / max(np.mean(vs), 1e-18) < 0.35:
            concord += 1
    xvenue_decision = "Hold"
    xvenue_why = f"close_noise_days={concord}/{pairs} (rel range <35%)"

    return {
        "cont.sparse_rv_only": mc.get("gate", {}),
        "cont.noise_dominates_1s_mid": {
            "decision": "Kill" if kill_cal_noise else "Hold",
            "why": f"median fifth/fourth calendar={med_ratio:.3f} n={len(ratios)}",
        },
        "cont.noise_trade_clock_bounce": {
            "decision": "Promote" if promote_tc else ("Hold" if hold_tc else "Kill"),
            "why": f"median fifth/fourth trade_clock={med_tc:.3f} n={len(tc_ratios)}; monitor-only if Promote",
            "label": "risk_monitor" if promote_tc or hold_tc else "none",
        },
        "cont.tsrv_first_adj": {"decision": tsrv_decision, "why": tsrv_why},
        "cont.noise_var_fifth": {
            "decision": "Hold",
            "why": "liquidity proxy only; causal efficiency Hold; see market_noise gate",
        },
        "frag.xvenue_noise_concord": {"decision": xvenue_decision, "why": xvenue_why},
        "summary_ratios": {"calendar_med": med_ratio, "trade_clock_med": med_tc},
    }


def write_reports(panel: dict, gates: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pass2_panel.json").write_text(json.dumps(panel, indent=2, default=str))
    (OUT / "pass2_gates.json").write_text(json.dumps(gates, indent=2, default=str))

    # estimators EXP_REPORT
    lines = [
        "# Estimators — EXP_REPORT (Pass 2)",
        "",
        f"- Symbols {panel['symbols']} days {panel['days']}",
        "",
        "## Calendar vs trade-clock fifth/fourth",
    ]
    for r in panel["rows"]:
        if not r.get("ok"):
            lines.append(f"- {r.get('symbol')} {r.get('venue')} {r.get('day')}: FAIL {r.get('reason')}")
            continue
        cal = r.get("calendar") or {}
        tc = r.get("trade_clock") or {}
        abl = (cal.get("ablation") or {}) if cal else {}
        lines.append(
            f"- {r['symbol']} {r['venue']} {r['day']}: cal_ff={cal.get('fifth_over_fourth')} "
            f"tc_ff={tc.get('fifth_over_fourth')} first_adj_cv={abl.get('first_adj_cv')} "
            f"fragile={abl.get('fragile_first_adj')} complete={r.get('complete')}"
        )
    g_tsrv = gates["cont.tsrv_first_adj"]
    g_tc = gates["cont.noise_trade_clock_bounce"]
    g_cal = gates["cont.noise_dominates_1s_mid"]
    lines += [
        "",
        "## Gates",
        f"- `cont.tsrv_first_adj` → **{g_tsrv['decision']}** — {g_tsrv['why']}",
        f"- `cont.noise_dominates_1s_mid` → **{g_cal['decision']}** — {g_cal['why']}",
        f"- `cont.noise_trade_clock_bounce` → **{g_tc['decision']}** — {g_tc['why']}",
        "",
    ]
    (BOOK / "chapters" / "estimators" / "EXP_REPORT.md").write_text("\n".join(lines))
    (BOOK / "chapters" / "estimators" / "CANDIDATES.md").write_text(
        "| id | type | lenses | decision | falsifier |\n"
        "|----|------|--------|----------|----------|\n"
        f"| `cont.tsrv_first_adj` | estimator | cont, risk | **{g_tsrv['decision']}** | K/step ablation — {g_tsrv['why']} |\n"
        f"| `cont.noise_dominates_1s_mid` | diagnostic | cont | **{g_cal['decision']}** | {g_cal['why']} |\n"
        f"| `cont.noise_trade_clock_bounce` | diagnostic | cont, info | **{g_tc['decision']}** | {g_tc['why']} |\n"
        f"| `cont.sparse_rv_only` | estimator | cont | **Kill** | see monte_carlo |\n"
    )

    # noise_proxy
    np_lines = [
        "# Noise proxy — EXP_REPORT (Pass 2)",
        "",
        "## Calendar noise_std",
    ]
    for r in panel["rows"]:
        if not r.get("ok") or not r.get("calendar"):
            continue
        np_lines.append(
            f"- {r['symbol']} {r['venue']} {r['day']}: noise_std={r['calendar']['noise_std']:.6g} "
            f"tc_noise_std={r['trade_clock'].get('noise_std')} "
            f"tc_ff={r['trade_clock'].get('fifth_over_fourth')}"
        )
    g_nv = gates["cont.noise_var_fifth"]
    np_lines += [
        "",
        f"## Gate\n- `cont.noise_var_fifth` → **{g_nv['decision']}** — {g_nv['why']}",
        f"- `cont.noise_trade_clock_bounce` → **{g_tc['decision']}** — {g_tc['why']}",
        "",
    ]
    (BOOK / "chapters" / "noise_proxy" / "EXP_REPORT.md").write_text("\n".join(np_lines))
    (BOOK / "chapters" / "noise_proxy" / "CANDIDATES.md").write_text(
        "| id | type | lenses | decision | falsifier |\n"
        "|----|------|--------|----------|----------|\n"
        f"| `cont.noise_var_fifth` | proxy | cont, liq, info | **{g_nv['decision']}** | {g_nv['why']} |\n"
        f"| `cont.noise_dominates_1s_mid` | diagnostic | cont | **{g_cal['decision']}** | {g_cal['why']} |\n"
        f"| `cont.noise_trade_clock_bounce` | diagnostic | cont | **{g_tc['decision']}** | {g_tc['why']} |\n"
    )

    # xvenue
    xv = gates["frag.xvenue_noise_concord"]
    xv_lines = [
        "# X-venue noise — EXP_REPORT (Pass 2)",
        "",
        "## Same-day noise_std",
    ]
    by: dict[str, dict[str, float]] = {}
    for r in panel["rows"]:
        if not r.get("ok") or not r.get("calendar"):
            continue
        by.setdefault(f"{r['symbol']} {r['day']}", {})[r["venue"]] = r["calendar"]["noise_std"]
    for k, m in sorted(by.items()):
        xv_lines.append(f"- {k}: " + ", ".join(f"{v}={m[v]:.6g}" for v in CORE_VENUES if v in m))
    xv_lines += ["", f"## Gate\n- `frag.xvenue_noise_concord` → **{xv['decision']}** — {xv['why']}", ""]
    (BOOK / "chapters" / "xvenue_noise" / "EXP_REPORT.md").write_text("\n".join(xv_lines))
    (BOOK / "chapters" / "xvenue_noise" / "CANDIDATES.md").write_text(
        "| id | type | lenses | decision | falsifier |\n"
        "|----|------|--------|----------|----------|\n"
        f"| `frag.xvenue_noise_concord` | panel | frag, liq, cont | **{xv['decision']}** | {xv['why']} |\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="ETH,BTC")
    ap.add_argument("--days", default="")
    ap.add_argument("--n-days", type=int, default=3)
    ap.add_argument("--n-sims", type=int, default=500)
    ap.add_argument("--max-files", type=int, default=24)
    ap.add_argument("--skip-mc", action="store_true")
    args = ap.parse_args()
    try:
        ensure_env()
    except Exception as e:  # noqa: BLE001
        print(f"ensure_env warn: {e}", flush=True)

    mc = {"gate": {"cont.sparse_rv_only": "Kill", "why": "from prior"}}
    if not args.skip_mc:
        mc = run_mc(args.n_sims)

    day_list = [d.strip() for d in args.days.split(",") if d.strip()] or None
    days = resolve_days(day_list, venue="hyperliquid", n=args.n_days)
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    panel = run_panel(symbols, days, max_files=args.max_files)
    gates = _gates(panel, mc)
    write_reports(panel, gates)
    print(json.dumps(gates, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
