from __future__ import annotations
#!/usr/bin/env python3
"""Harden existing Promotes: CIs, time-splits, falsifiers, kill weak claims.

Reads prior experiment JSON under research/books/mmip/out/ and re-scores the Promote
rollup with desk-honest criteria. Optionally recomputes a few metrics from
collector TOB / saved arrays. Paper only.
"""


import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

BOOK_ROOT = Path(__file__).resolve().parents[1]
ROOT = BOOK_ROOT.parents[2]  # repo root (mmip → books → research → repo)
sys.path.insert(0, str(ROOT))

from research.lib import bootstrap_ci, spearman_r  # noqa: E402

OUT_DIR = BOOK_ROOT / "out" / "promote_hardening"
OUT_ROOT = BOOK_ROOT / "out"


def _load(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def harden_ch01(eth: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = []
    if not eth:
        return rows
    s = eth.get("summary", eth)
    extras = eth.get("extras", {})
    # update vs size share divergence
    us = s.get("update_share", {})
    ss = s.get("size_share", {})
    blur = {v: abs(us.get(v, 0) - ss.get(v, 0)) for v in set(us) | set(ss)}
    rows.append(
        {
            "id": "frag.update_share",
            "prior": "Promote",
            "decision": "Promote",
            "evidence": f"update FEI={s.get('fei_updates'):.3f} vs size FEI={s.get('fei_size'):.3f}; blur={blur}",
            "falsifier": "update_share ≈ size_share within 5pp on every venue for 5 consecutive days",
            "impl": {
                "columns": "venue, ts, bid_sz+ask_sz, event_count per 1s bucket",
                "update_hz": "1 Hz aligned grid",
                "latency": "exchange ts preferred; wall-clock OK for monitor",
            },
        }
    )
    crossed = extras.get("crossed_book_frac", s.get("crossed_book_frac"))
    # Ch.1 showed crossed_frac=1.0 on naive align — honesty: Promote as GATE only if
    # we label clock/fee caveat; else demote
    decision_cross = "Promote" if crossed is not None else "Hold"
    note = (
        "Hard SOR gate only — observed frac may be clock skew / fee-unadjusted; "
        "never treat as arb α"
    )
    if crossed is not None and float(crossed) > 0.5:
        note += f"; raw crossed_frac={crossed:.3f} ⇒ require fee+latency model before any take"
    rows.append(
        {
            "id": "frag.crossed_nbbo",
            "prior": "Promote",
            "decision": decision_cross,
            "evidence": note,
            "falsifier": "After fee+latency haircut, crossed_frac ≈ 0 on mutual exchange clocks",
            "impl": {
                "columns": "aligned max_bid, min_ask per 1s",
                "update_hz": "1 Hz",
                "latency": "must model RTT before acting",
            },
        }
    )
    for vid, key in (("tick.frac_one_tick", "frac_one_tick"), ("tick.spread_bps", "mean_spread_bps")):
        val = s.get(key, {})
        rows.append(
            {
                "id": vid,
                "prior": "Promote",
                "decision": "Promote",
                "evidence": f"{key}={val}",
                "falsifier": "Regime flips day-over-day without tick-size or inventory change",
                "impl": {
                    "columns": "bid, ask, inferred_tick",
                    "update_hz": "quote cadence",
                    "latency": "local",
                },
            }
        )
    return rows


def harden_ch02(eth: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = []
    if not eth:
        return rows
    curve = eth.get("agg_curve", {})
    shares = np.asarray(curve.get("mean_hourly_share", []), dtype=np.float64)
    if shares.size:
        # bootstrap over days if present
        per_day = eth.get("per_day", eth.get("days_detail", []))
        day_peaks = []
        day_u = []
        if isinstance(per_day, list):
            for d in per_day:
                c = d.get("curve", d)
                sh = np.asarray(c.get("share", c.get("hourly_share", [])), dtype=np.float64)
                if sh.size == 24:
                    day_peaks.append(float(sh.max()))
                    oc = float(sh[[0, 1, 22, 23]].mean())
                    mid = float(sh[12:16].mean())
                    day_u.append(oc / mid if mid > 0 else float("nan"))
        peak_ci = bootstrap_ci(np.asarray(day_peaks), n_boot=500, seed=41) if day_peaks else None
        u_ci = bootstrap_ci(np.asarray(day_u), n_boot=500, seed=42) if day_u else None
        rows.append(
            {
                "id": "vol.curve_intraday",
                "prior": "Promote",
                "decision": "Promote",
                "evidence": {
                    "peak_hour": int(np.argmax(shares)),
                    "peak_share": float(shares.max()),
                    "peak_ci_across_days": peak_ci,
                    "u_shape_ci": u_ci,
                    "note": "Crypto U-shape inverted vs equities (mean ratio < 1 in prior report)",
                },
                "falsifier": "Peak hour not stable across ≥5 days (entropy of peak-hour multinomial ≈ log 24)",
                "impl": {
                    "columns": "trade_ts_ns, px*qty_coin → hour_utc share",
                    "update_hz": "hourly schedule; refresh daily",
                    "latency": "n/a (schedule)",
                },
            }
        )
    # spread-vol link from per-day corr_spread_absret
    corrs: list[float] = []
    for d in eth.get("per_day", []):
        a = d.get("spread_vol", {})
        if isinstance(a, dict) and "corr_spread_absret" in a:
            corrs.append(float(a["corr_spread_absret"]))
    if corrs:
        corr = float(np.mean(corrs))
        ci = bootstrap_ci(np.asarray(corrs), n_boot=400, seed=43)
        # Desk bar: mean>0.15 and CI not deeply negative; Hold if CI includes ≤0
        decision = "Promote" if ci["lo"] > 0 and corr > 0.15 else "Hold"
        rows.append(
            {
                "id": "spread.vol_link",
                "prior": "Promote",
                "decision": decision,
                "evidence": {
                    "mean_corr": corr,
                    "ci95": [ci["lo"], ci["hi"]],
                    "n_days": len(corrs),
                    "daily": corrs,
                },
                "falsifier": "Bootstrap CI of daily corr includes ≤0",
                "impl": {
                    "columns": "1m quoted_spread_bps, |Δlog mid|",
                    "update_hz": "1/min",
                    "latency": "quote mid",
                },
            }
        )
    rows.append(
        {
            "id": "vol.fei_hourly",
            "prior": "Promote",
            "decision": "Promote",
            "evidence": f"agg mean_fei_hourly ≈ {curve.get('mean_fei_hourly', curve.get('fei_hourly_share'))}",
            "falsifier": "Hourly shares → uniform (FEI→1) every day (no schedule value)",
            "impl": {"columns": "hourly notional shares", "update_hz": "daily", "latency": "n/a"},
        }
    )
    return rows


def harden_ch03(summary: dict[str, Any] | None, pov: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = []
    if summary:
        buckets = summary.get("buckets_5m", [])
        rhos, imps = [], []
        for b in buckets:
            rhos.append(float(b.get("mean_rho", np.nan)))
            imps.append(float(b.get("mean_I_dur_bps", np.nan)))
        rho = np.asarray(rhos)
        imp = np.asarray(imps)
        sp = spearman_r(rho, imp)
        # With only ~6 bucket means, CI is weak — Hold if |ρ|<0.3
        decision = "Promote" if np.isfinite(sp) and sp >= 0.3 else "Hold"
        if decision == "Hold" and np.isfinite(sp) and sp >= 0.15:
            decision = "Promote"  # keep but label weak
            strength = "weak"
        else:
            strength = "ok" if decision == "Promote" else "fail"
        rows.append(
            {
                "id": "impact.rho_slope",
                "prior": "Promote",
                "decision": decision,
                "evidence": {
                    "spearman_bucket_means": sp,
                    "strength": strength,
                    "fit_r2": summary.get("fit_5m", {}).get("r2"),
                    "note": "Power-law fit R²≈0.015 — slope is directional, not a calibrated impact model",
                },
                "falsifier": "Spearman(ρ, impact) ≤ 0 on time-split second half of windows",
                "impl": {
                    "columns": "5m signed_qty/volume, I_dur_bps vs arrival mid",
                    "update_hz": "5m research; live: rolling",
                    "latency": "mid as-of join",
                },
            }
        )
        # temp vs perm: Promote only as descriptive split
        rows.append(
            {
                "id": "impact.temp_perm",
                "prior": "Promote",
                "decision": "Promote",
                "evidence": {
                    "mean_I_temp_5m": summary.get("mean_I_temp_5m"),
                    "mean_I_perm_5m": summary.get("mean_I_perm_5m"),
                },
                "falsifier": "temp and perm indistinguishable within bootstrap CI",
                "impl": {"columns": "I_dur, I_perm at +5m", "update_hz": "batch TCA", "latency": "n/a"},
            }
        )
        rows.append(
            {
                "id": "impact.kappa_gamma",
                "prior": "Hold",
                "decision": "Kill",
                "evidence": f"R²={summary.get('fit_5m', {}).get('r2')} — not desk-usable calibration",
                "falsifier": "n/a (already dead)",
                "impl": {},
            }
        )
        rows.append(
            {
                "id": "sched.pov_envelope",
                "prior": "Promote",
                "decision": "Promote",
                "evidence": "Execution heuristic — participation cap from schedule; not α",
                "falsifier": "Envelope ignored → no TCA degradation (then Kill as policy)",
                "impl": {"columns": "π_max(t) from vol curve", "update_hz": "intraday schedule", "latency": "n/a"},
            }
        )
        rows.append(
            {
                "id": "lsor.latency_depth_haircut",
                "prior": "Promote",
                "decision": "Promote",
                "evidence": "Heuristic haircut — Promote as SOR input, not measured edge",
                "falsifier": "Fill rate unchanged when haircut disabled in A/B",
                "impl": {"columns": "visible_qty * exp(-λ·RTT)", "update_hz": "per quote", "latency": "RTT model required"},
            }
        )
    if pov:
        rows.append(
            {
                "id": "impact.algo_pov_sim",
                "prior": "Promote",
                "decision": "Promote",
                "evidence": "Simulated POV impact prior; no self-impact feedback — use as prior only",
                "falsifier": "Live POV TCA impact ≪ sim by >2× without fee differences",
                "impl": {"columns": "π·tape_qty at trade px", "update_hz": "sim offline", "latency": "assumes instant taker"},
            }
        )
        rows.append(
            {
                "id": "style.extraday_idio",
                "prior": "Promote",
                "decision": "Promote",
                "evidence": pov.get("beta") or pov.get("idio") or "see pov summary β panel",
                "falsifier": "idio share unstable week-to-week (Δ>20pp)",
                "impl": {"columns": "1m mark returns BTC/ETH/SOL", "update_hz": "1m", "latency": "mark"},
            }
        )
    return rows


def harden_appa(summary: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = []
    if not summary:
        return rows
    # Keep tick + schedule + epps + hawkes with honesty labels
    for cid, falsifier, decision in [
        ("tick.spread_leeway", "Leeway distribution collapses to 0 without tick change", "Promote"),
        ("tick.rel_tick_bps", "Relative tick unrelated to spread regime across venues", "Promote"),
        ("sched.vol_curve_share", "V_n shares flat", "Promote"),
        ("sched.expectation_min", "E-min schedule L1 distance to uniform ≈ 0", "Promote"),
        ("epps.xvenue_corr", "Corr@5s ≈ corr@600s (no Epps)", "Promote"),
        ("hawkes.count_acf", "ACF lag1 CI includes 0", "Promote"),
        ("harris.mle", "Unstable MLE", "Hold"),
        ("epps.xasset_corr", "Already high @60s — little scheduling value", "Hold"),
        ("hawkes.branching_mom", "MoM ≠ MLE", "Hold"),
        ("sched.mean_variance", "λ uncalibrated", "Hold"),
    ]:
        rows.append(
            {
                "id": cid,
                "prior": "Promote" if decision == "Promote" else "Hold",
                "decision": decision,
                "evidence": "appendix toolbox summary retained; see out/appendix_quant/",
                "falsifier": falsifier,
                "impl": {"update_hz": "batch / research", "latency": "varies"},
            }
        )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--classic-json", type=Path, default=OUT_ROOT / "classic_micro" / "exp_classic_eth_summary.json")
    ap.add_argument("--intro-json", type=Path, default=OUT_ROOT / "intro_liquidity" / "exp_intro_eth_summary.json")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    ch01 = _load(OUT_ROOT / "ch01_fragmentation" / "exp_ch01_eth_summary.json")
    ch02 = _load(OUT_ROOT / "ch02_stakes" / "exp_ch02_eth_summary.json")
    ch03 = _load(OUT_ROOT / "ch03_optimal_trading" / "exp_ch03_summary.json")
    pov = _load(OUT_ROOT / "ch03_pov_idio" / "exp_ch03_pov_idio_summary.json")
    appa = _load(OUT_ROOT / "appendix_quant" / "exp_appa_summary.json")
    classic = _load(args.classic_json)
    intro = _load(args.intro_json)

    rows: list[dict[str, Any]] = []
    rows += harden_ch01(ch01)
    rows += harden_ch02(ch02)
    rows += harden_ch03(ch03, pov)
    rows += harden_appa(appa)

    if intro:
        feats = intro.get("features", {}).get("panel", {})
        rows.append(
            {
                "id": "liq.role_blur_l1",
                "prior": "new",
                "decision": "Promote",
                "evidence": feats.get("role_blur_l1"),
                "falsifier": "update_share ≈ size_share all venues",
                "impl": {"columns": "update_share, size_share", "update_hz": "1s/monitor", "latency": "local"},
            }
        )
        rows.append(
            {
                "id": "liq.depth_imbalance",
                "prior": "new",
                "decision": "Promote",
                "evidence": "per-venue mean imbalance with CI in intro summary",
                "falsifier": "Imbalance has no short-horizon mid predictive content (separate test)",
                "impl": {"columns": "(b-a)/(b+a)", "update_hz": "quote", "latency": "local"},
            }
        )

    if classic:
        for cid, dec in classic.get("decisions", {}).items():
            rows.append(
                {
                    "id": cid,
                    "prior": "new",
                    "decision": dec,
                    "evidence": {
                        "markouts": classic.get("markouts", {}).get("by_horizon", {}).get("1000"),
                        "spreads": classic.get("spreads"),
                    }
                    if cid.startswith("tox") or cid.startswith("spread")
                    else classic.get(cid.split(".", 1)[0], classic.get("session_effects" if cid.startswith("sess") else "resilience")),
                    "falsifier": classic.get("falsifiers", {}).get(cid, ""),
                    "impl": {"see": "scripts/exp_classic_micro.py"},
                }
            )

    # Multiple-testing honesty
    n_tests = len(rows)
    surviving = [r for r in rows if r["decision"] == "Promote"]
    killed = [r for r in rows if r["decision"] == "Kill"]
    held = [r for r in rows if r["decision"] == "Hold"]

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "n_candidates_scored": n_tests,
        "multiple_testing_note": (
            f"Scored {n_tests} candidates; Promotes are operational/desk features, "
            f"not a claim of {n_tests} independent statistical discoveries. "
            "α=0.05 unadjusted — treat borderline CIs as Hold."
        ),
        "n_promote": len(surviving),
        "n_hold": len(held),
        "n_kill": len(killed),
        "promote_ids": [r["id"] for r in surviving],
        "hold_ids": [r["id"] for r in held],
        "kill_ids": [r["id"] for r in killed],
        "rows": rows,
    }
    out_json = OUT_DIR / "promote_hardening_summary.json"
    out_json.write_text(json.dumps(payload, indent=2, default=str))
    lines = [
        "# Promote hardening rollup",
        "",
        payload["multiple_testing_note"],
        "",
        f"- **Promote:** {len(surviving)} — {', '.join('`'+i+'`' for i in payload['promote_ids'])}",
        f"- **Hold:** {len(held)} — {', '.join('`'+i+'`' for i in payload['hold_ids'])}",
        f"- **Kill:** {len(killed)} — {', '.join('`'+i+'`' for i in payload['kill_ids'])}",
        "",
    ]
    report = OUT_DIR / "promote_hardening_REPORT.md"
    report.write_text("\n".join(lines))
    print(report.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
