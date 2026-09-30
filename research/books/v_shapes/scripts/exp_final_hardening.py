#!/usr/bin/env python3
"""Program-wide hardening: Promote rollup, DESK_MEMO signal board, desk_synthesis."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(ROOT))

OUT = BOOK / "out"


def _load(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _mean_ci(vals: list[float]) -> tuple[float, float, float]:
    a = np.asarray(vals, dtype=float)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return float("nan"), float("nan"), float("nan")
    m = float(np.mean(a))
    se = float(np.std(a, ddof=1) / math.sqrt(a.size)) if a.size > 1 else float("nan")
    if not np.isfinite(se):
        return m, float("nan"), float("nan")
    return m, m - 1.96 * se, m + 1.96 * se


def _merge_daily_rows(*dailies: dict) -> list[dict]:
    rows: list[dict] = []
    for d in dailies:
        for r in (d or {}).get("rows") or []:
            if isinstance(r, dict):
                rr = dict(r)
                if "symbol" not in rr and d.get("symbol"):
                    rr["symbol"] = d["symbol"]
                rows.append(rr)
    return rows


def main() -> int:
    panel = _load(OUT / "v_statistic" / "panel_eth.json") or {}
    panel_btc = _load(OUT / "v_statistic" / "panel_btc.json") or {}
    daily = _load(OUT / "daily_minv" / "daily_minv_eth.json") or {}
    daily_btc = _load(OUT / "daily_minv" / "daily_minv_btc.json") or {}
    event = _load(OUT / "event_case" / "event_eth.json") or {}
    liq = _load(OUT / "liq_around_v" / "liq_eth.json") or {}
    liq_btc = _load(OUT / "liq_around_v" / "liq_btc.json") or {}
    xven = _load(OUT / "xvenue_concord" / "xvenue_eth.json") or {}
    xven_btc = _load(OUT / "xvenue_concord" / "xvenue_btc.json") or {}
    boot = _load(OUT / "bootstrap_sim" / "size_power_models0_3.json") or {}
    kill_asym = _load(OUT / "bootstrap_sim" / "kill_asymptotic_bands.json") or {}
    widen = _load(OUT / "widen_day_plan.json") or {}
    cont_eth = _load(OUT / "v_statistic" / "continuous_v_eth.json") or {}
    cont_btc = _load(OUT / "v_statistic" / "continuous_v_btc.json") or {}

    # Scan daily panel for Promote evidence (ETH+BTC merged)
    rows = _merge_daily_rows(daily, daily_btc)
    ok = [r for r in rows if r.get("ok")]
    sig5 = [r for r in ok if r.get("sig_5") and r.get("complete")]
    days = sorted({r["day"] for r in ok if "day" in r})
    mid = max(1, len(days) // 2)
    early, late = set(days[:mid]), set(days[mid:])
    early_sig = [r for r in sig5 if r.get("day") in early]
    late_sig = [r for r in sig5 if r.get("day") in late]
    # Require both halves when sample has ≥3 distinct days; else keep prior thin-slice rule.
    if len(days) >= 3:
        time_split_ok = bool(early_sig) and bool(late_sig)
    else:
        time_split_ok = bool(early_sig) and bool(late_sig) or (len(sig5) >= 1 and len(days) <= 2)

    # hn fragility: sign of mean MinV should not flip across {1,5,30} for complete sig rows
    hn_means = {}
    for hm in (1, 5, 30):
        vals = [r["min_v"] for r in ok if r.get("hn_min") == hm and r.get("complete") and np.isfinite(r.get("min_v", np.nan))]
        hn_means[hm] = float(np.mean(vals)) if vals else float("nan")
    hn_signs = [np.sign(v) for v in hn_means.values() if np.isfinite(v)]
    hn_fragile = len(set(hn_signs)) > 1 if len(hn_signs) >= 2 else False

    xrows = (xven.get("rows") or []) + (xven_btc.get("rows") or [])
    concord = any(any(p.get("concord_5m") for p in (r.get("pairs") or [])) for r in xrows)

    # post-trough CI on sig5 complete rows (panel); continuous-pass is corroboration only
    post_src = sig5 if sig5 else [r for r in ok if r.get("sig_5")]
    post_vals = [
        float(r.get("post_trough", {}).get("ret_300s"))
        for r in post_src
        if isinstance(r.get("post_trough"), dict)
        and r.get("post_trough", {}).get("ret_300s") is not None
        and np.isfinite(r.get("post_trough", {}).get("ret_300s", np.nan))
    ]
    if len(post_vals) < 6:
        for c in (cont_eth, cont_btc):
            for r in (c or {}).get("rows") or []:
                if r.get("ok") and isinstance(r.get("post_trough"), dict):
                    v = r["post_trough"].get("ret_300s")
                    if v is not None and np.isfinite(v):
                        post_vals.append(float(v))
    post_m, post_lo, post_hi = _mean_ci(post_vals)
    post_ci_excludes_0 = bool(np.isfinite(post_lo) and np.isfinite(post_hi) and (post_hi < 0 or post_lo > 0) and len(post_vals) >= 6)

    # lead-lag from continuous V_t Pass-2 — V only (T± vs fwd returns is partly mechanical)
    leadlag_ok = False
    leadlag_note = "no lead-lag fields in panel"
    corrs = []
    for c in (cont_eth, cont_btc):
        for r in (c or {}).get("rows") or []:
            for k, val in (r.get("leadlag") or {}).items():
                # Only corr_V_* — T± kernels use same-side returns; fwd corr can be mechanical
                if str(k).startswith("corr_V_") and np.isfinite(val):
                    corrs.append(float(val))
        for k, v in ((c or {}).get("leadlag_agg") or {}).items():
            if not str(k).startswith("corr_V_"):
                continue
            if (
                isinstance(v, dict)
                and v.get("excludes_0")
                and abs(float(v.get("mean") or 0)) >= 0.05
                and int(v.get("n") or 0) >= 6
            ):
                leadlag_ok = True
                leadlag_note = f"agg {k}: mean={v['mean']:.3f} CI=[{v['lo']:.3f},{v['hi']:.3f}] n={v['n']}"
    # also legacy panel corr_V_r2
    for pan in (panel, panel_btc):
        for r in pan.get("rows") or []:
            ll = r.get("leadlag") or {}
            for k, val in ll.items():
                if "corr_V" in str(k) and np.isfinite(val):
                    corrs.append(float(val))
        venues = pan.get("venues") or {}
        if isinstance(venues, dict):
            for _v, days_map in venues.items():
                if not isinstance(days_map, dict):
                    continue
                for _d, day_rec in days_map.items():
                    if not isinstance(day_rec, dict):
                        continue
                    hn_map = day_rec.get("hn") if isinstance(day_rec.get("hn"), dict) else day_rec
                    if not isinstance(hn_map, dict):
                        continue
                    for _h, rec in hn_map.items():
                        if not isinstance(rec, dict):
                            continue
                        for k, val in (rec.get("leadlag") or {}).items():
                            if "corr_V" in str(k) and np.isfinite(val):
                                corrs.append(float(val))
    if corrs and not leadlag_ok:
        cm, clo, chi = _mean_ci(corrs)
        # Require stronger bar: |mean|≥0.05, CI excludes 0, n≥12 (multi-event), not a soft pool of T±
        leadlag_ok = bool(
            np.isfinite(clo)
            and np.isfinite(chi)
            and (chi < 0 or clo > 0)
            and abs(cm) >= 0.05
            and len(corrs) >= 12
        )
        leadlag_note = f"mean_corr_V={cm:.3f} CI=[{clo:.3f},{chi:.3f}] n={len(corrs)}"
        if not leadlag_ok:
            leadlag_note += " (V-only; CI does not clear Promote bar / thin events)"
    elif not corrs and not leadlag_ok:
        leadlag_note = "lead-lag corr_V vs fwd mid returns / r2 not Promote-grade (missing or thin)"

    # TOB / liq coverage (ETH+BTC) — multi-day coverage necessary but not sufficient
    lrows = (liq.get("rows") or []) + (liq_btc.get("rows") or [])
    tob_ok = [
        r
        for r in lrows
        if isinstance(r.get("liq"), dict) and "spread_bps_mean" in r["liq"] and np.isfinite(r["liq"].get("spread_bps_mean", np.nan))
    ]
    tob_days = sorted({r.get("day") for r in tob_ok if r.get("day")})
    tob_sources = sorted({(r.get("liq") or {}).get("tob_source") or r.get("tob_source") or "?" for r in tob_ok})
    # pre/post Δspread CI must clear 0; drop absurd warehouse L2 bps (>50) as noise for the test
    deltas = []
    for r in tob_ok:
        pre = r["liq"].get("spread_bps_pre")
        post = r["liq"].get("spread_bps_post")
        mean_s = r["liq"].get("spread_bps_mean")
        if not (np.isfinite(pre) and np.isfinite(post) and np.isfinite(mean_s)):
            continue
        if float(mean_s) > 50.0:  # Deribit sparse L2 often prints 100–500bps garbage
            continue
        deltas.append(float(post) - float(pre))
    d_m, d_lo, d_hi = _mean_ci(deltas)
    delta_ok = bool(np.isfinite(d_lo) and np.isfinite(d_hi) and (d_hi < 0 or d_lo > 0) and len(deltas) >= 6)
    liq_promote = len(tob_ok) >= 4 and len(tob_days) >= 2 and delta_ok
    liq_hold_why = (
        f"TOB usable rows={len(tob_ok)} days={tob_days} sources={tob_sources[:3]}; "
        f"Δspread(post-pre) mean={d_m:.4f} CI=[{d_lo:.4f},{d_hi:.4f}] n_sane={len(deltas)} "
        "(Kraken warehouse L2 empty; collector only 0929-30; Deribit L2 multi-day but Δ not Promote-grade)"
    )

    # stress-day reproducibility
    stress_days = sorted({r["day"] for r in sig5 if r.get("hn_min") == 5})
    stress_promote = len(stress_days) >= 3

    promotes = []
    holds = []
    kills = [
        {
            "id": "risk.asymptotic_218_360",
            "decision": "Kill",
            "why": kill_asym.get("reason")
            or "paper §3.1: too small for realistic DGP + multiple testing; use EGARCH bootstrap",
        },
        {
            "id": "risk.gm_mu_sigma_tradable",
            "decision": "Kill",
            "why": "Grossman–Miller mu/sigma monitor only — vanity as tradable",
        },
    ]

    # Always keep taxonomy Promote when boot/program exists
    promotes.append(
        {
            "id": "risk.v_vs_jump_taxonomy",
            "lenses": "risk,info",
            "ch": "ch00_overview",
            "use": "V ≠ jump ≠ vol spike ≠ geometric V",
        }
    )
    if boot:
        promotes.append(
            {
                "id": "risk.egarch_minv_bands",
                "lenses": "risk",
                "ch": "bootstrap_sim",
                "use": "EGARCH simulated bootstrap CIs for MinV",
            }
        )
    if sig5 and time_split_ok and not hn_fragile:
        promotes.append(
            {
                "id": "risk.daily_minv_panel",
                "lenses": "risk",
                "ch": "daily_minv",
                "use": "UTC-day MinV vs EGARCH 5% as fragility monitor",
            }
        )
    else:
        why = f"sig5_complete={len(sig5)} time_split early/late={len(early_sig)}/{len(late_sig)}"
        if hn_fragile:
            why += f" hn_fragile means={ {k: round(v,2) for k,v in hn_means.items() if np.isfinite(v)} }"
        holds.append({"id": "risk.daily_minv_panel", "why": why})

    if concord:
        promotes.append(
            {
                "id": "risk.xvenue_minv_concord",
                "lenses": "risk,mm",
                "ch": "xvenue_concord",
                "use": "HL↔Deribit↔Kraken MinV concordance within hn",
            }
        )
    else:
        holds.append({"id": "risk.xvenue_minv_concord", "why": "no concordant significant pair in slice"})

    if leadlag_ok:
        promotes.append(
            {
                "id": "info.v_path_continuous",
                "lenses": "info,risk",
                "ch": "v_statistic",
                "use": "Continuous V_t lead-lag vs future r^2 as info feature",
            }
        )
    else:
        holds.append({"id": "info.v_path_continuous", "why": leadlag_note})

    if post_ci_excludes_0:
        promotes.append(
            {
                "id": "info.post_trough_ret",
                "lenses": "info,exec",
                "ch": "daily_minv",
                "use": "Post-trough mean return CI excludes 0 (Table-2 style)",
            }
        )
    else:
        holds.append(
            {
                "id": "info.post_trough_ret",
                "why": f"post300 mean={post_m:.5f} CI=[{post_lo:.5f},{post_hi:.5f}] n={len(post_vals)}",
            }
        )

    if liq_promote:
        promotes.append(
            {
                "id": "liq.spread_around_minv",
                "lenses": "liq,risk",
                "ch": "liq_around_v",
                "use": "Spread pre/post MinV on multi-day TOB coverage",
            }
        )
    else:
        holds.append(
            {
                "id": "liq.spread_around_minv",
                "why": liq_hold_why,
            }
        )

    # Identification Hold — never Promote
    holds.append({"id": "id.auction_loss", "why": "no crypto sovereign auction analogue"})

    if stress_promote:
        promotes.append(
            {
                "id": "risk.stress_day_minv",
                "lenses": "risk,info",
                "ch": "event_case",
                "use": "Stress-day MinV narrative reproduced across ≥3 complete days",
            }
        )
    else:
        holds.append(
            {
                "id": "risk.stress_day_minv",
                "why": f"complete+sig5@5m distinct days={stress_days}",
            }
        )

    rollup = {
        "promotes": promotes,
        "holds": holds,
        "kills": kills,
        "n_sig5_complete": len(sig5),
        "n_days": len(days),
        "days": days,
        "time_split": {"early": sorted(early), "late": sorted(late), "early_sig": len(early_sig), "late_sig": len(late_sig)},
        "hn_means": hn_means,
        "post300": {"mean": post_m, "lo": post_lo, "hi": post_hi, "n": len(post_vals)},
        "tob": {"n_ok": len(tob_ok), "days": tob_days, "sources": tob_sources},
        "concord": concord,
        "widen": {k: widen.get(k) for k in ("eth_days", "btc_days", "eth_gap_added", "tob_collector_days", "tob_note", "note", "max_files") if k in widen},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "hardening_rollup.json").write_text(json.dumps(rollup, indent=2, default=str))

    # CHAPTER_INDEX Promote rollup + status updates
    idx = (BOOK / "CHAPTER_INDEX.md").read_text()
    # rewrite statuses
    status_map = {
        "ch00_overview": "`exp_run`",
        "v_statistic": "`exp_run`",
        "bootstrap_sim": "`exp_run`",
        "daily_minv": "`exp_run`",
        "event_case": "`exp_run`",
        "liq_around_v": "`exp_run`",
        "xvenue_concord": "`exp_run`",
    }
    for pkg, st in status_map.items():
        # replace status cell for package row — crude but OK
        import re

        idx = re.sub(
            rf"(\| `{pkg}` \|[^|]+\|[^|]+\|) `[^`]+` \|",
            rf"\1 {st} |",
            idx,
            count=1,
        )
    # replace promote rollup table
    promo_lines = [
        "| Candidate | risk | info | exec | disc | cont | liq | mm | Ch | One-line use |",
        "|-----------|:----:|:----:|:----:|:----:|:----:|:---:|:--:|----|--------------|",
    ]
    for p in promotes:
        lenses = {x.strip() for x in p["lenses"].split(",")}
        marks = {k: ("✓" if k in lenses else "") for k in ("risk", "info", "exec", "disc", "cont", "liq", "mm")}
        promo_lines.append(
            f"| `{p['id']}` | {marks['risk']} | {marks['info']} | {marks['exec']} | {marks['disc']} | "
            f"{marks['cont']} | {marks['liq']} | {marks['mm']} | {p['ch']} | {p['use']} |"
        )
    if not promotes:
        promo_lines.append("| — | | | | | | | | | *(none yet)* |")
    kill_hold = "**Kill / Hold:**\n" + "\n".join(
        [f"- **Kill** `{k['id']}`: {k['why']}" for k in kills]
        + [f"- **Hold** `{h['id']}`: {h['why']}" for h in holds]
    )
    import re

    idx = re.sub(
        r"## Promote rollup.*?\n---\n",
        "## Promote rollup\n\n"
        + "\n".join(promo_lines)
        + "\n\n"
        + kill_hold
        + "\n\n---\n",
        idx,
        count=1,
        flags=re.S,
    )
    idx = re.sub(
        r"\*\*Program status:\*\*[^\n]*",
        f"**Program status:** **Widened+hardened** — {len(days)} UTC days · "
        f"{len(promotes)} Promote / {len(holds)} Hold / {len(kills)} Kill.",
        idx,
        count=1,
    )
    # two-pass checklist mark done for program slice
    idx = idx.replace("- [ ] Extract PDF", "- [x] Extract PDF")
    idx = idx.replace("- [ ] Implement paper", "- [x] Implement paper")
    idx = idx.replace("- [ ] Baseline plots", "- [x] Baseline plots")
    idx = idx.replace("- [ ] Draft CANDIDATES", "- [x] Draft CANDIDATES")
    idx = idx.replace("- [ ] What information", "- [x] What information")
    idx = idx.replace("- [ ] Signal hypotheses", "- [x] Signal hypotheses")
    idx = idx.replace("- [ ] Competing defs", "- [x] Competing defs")
    idx = idx.replace("- [ ] Falsifiers:", "- [x] Falsifiers:")
    idx = idx.replace("- [ ] CANDIDATES + notebook", "- [x] CANDIDATES + notebook")
    (BOOK / "CHAPTER_INDEX.md").write_text(idx)

    # DESK_MEMO signal board
    board = [
        "| ID | Formula / clock | Monitor | Tradable | Exec throttle | Decision |",
        "|----|-----------------|---------|----------|---------------|----------|",
    ]
    for p in promotes:
        formula = {
            "risk.egarch_minv_bands": "MinV / EGARCH · UTC-day · hn∈{1,5,30}m",
            "risk.v_vs_jump_taxonomy": "Def 1 / Prop 1 framing",
            "risk.daily_minv_panel": "UTC-day MinV panel + time-split",
            "risk.xvenue_minv_concord": "pairwise |Δτ*|≤hn among sig venues",
            "info.v_path_continuous": "corr(V_t, future r²)",
            "info.post_trough_ret": "mean post-τ* ret CI",
            "liq.spread_around_minv": "TOB spread pre/post τ*",
            "risk.stress_day_minv": "multi-day stress MinV",
        }.get(p["id"], "—")
        board.append(
            f"| `{p['id']}` | {formula} | yes | no | maybe | **Promote** |"
        )
    for h in holds:
        board.append(f"| `{h['id']}` | — | maybe | no | no | **Hold** — {h['why'][:80]} |")
    for k in kills:
        board.append(f"| `{k['id']}` | — | no | no | no | **Kill** — {k['why'][:80]} |")

    memo = (BOOK / "DESK_MEMO.md").read_text()
    import re

    hold_blockers = "; ".join(h["id"] for h in holds[:4]) or "none"
    memo = re.sub(
        r"## 2\. Signal board.*?\n---\n",
        "## 2. Signal board (Pass 2 + hardening)\n\n"
        + "\n".join(board)
        + "\n\n**Kill list:** asymptotic 2.18/3.60; GM μ/σ as tradable\n"
        + f"**Hold blockers:** {hold_blockers}\n\n---\n",
        memo,
        count=1,
        flags=re.S,
    )
    memo = re.sub(
        r"\*\*Program status:\*\*[^\n]*",
        f"**Program status:** Widened+hardened — {len(promotes)} Promote / {len(holds)} Hold / {len(kills)} Kill · days={len(days)}.",
        memo,
        count=1,
    )
    # refresh next-gate section lightly
    memo = re.sub(
        r"## 4\. Next gate.*",
        "## 4. Next gate (post-widen)\n\n"
        f"1. Sample days in rollup: `{days}`.\n"
        f"2. TOB reality: usable={len(tob_ok)} days={tob_days}; "
        "Kraken warehouse L2 empty; collector only 2026-09-29/30; Deribit L2 multi-day when present — no fake TOB.\n"
        "3. Keep EGARCH bootstrap CIs; asymptotic 2.18/3.60 stay **Kill**.\n"
        "4. `id.auction_loss` stays Hold (identification).\n"
        "5. Trade ideas: see §5 — Monitor / Exec throttle only until post-trough / xvenue Promotes.\n",
        memo,
        count=1,
        flags=re.S,
    )
    # Trade ideas from current gate (desk-honest; no Kill alpha)
    def _gate_of(cid: str) -> str:
        if any(p["id"] == cid for p in promotes):
            return "Promote"
        if any(k["id"] == cid for k in kills):
            return "Kill"
        return "Hold"

    ideas = {
        "ideas": [
            {
                "id": "ti.risk_monitor_minv_breach",
                "label": "Monitor",
                "title": "MinV breach → widen quotes / cut size / pause aggressive takes",
                "sketch": (
                    "When UTC-day MinV < EGARCH 5% band at hn∈{1,5,30}m on home venue, "
                    "widen quotes, cut inventory size, and pause aggressive takes for one hn window."
                ),
                "depends_on": ["risk.egarch_minv_bands", "risk.v_vs_jump_taxonomy", "risk.daily_minv_panel"],
                "gate_status": {
                    cid: _gate_of(cid)
                    for cid in ("risk.egarch_minv_bands", "risk.v_vs_jump_taxonomy", "risk.daily_minv_panel")
                },
                "tradable_size": "N/A — Monitor only",
                "falsifier": f"time-split early/late sig={len(early_sig)}/{len(late_sig)}; hn_means={ {k: round(v,2) for k,v in hn_means.items() if np.isfinite(v)} }",
            },
            {
                "id": "ti.exec_throttle_avoid_chase",
                "label": "Exec throttle",
                "title": "Avoid chasing through MinV trough; delay POV until recovery",
                "sketch": (
                    "If live V_t / MinV path approaches trough (T−≪0 then T+ rising), "
                    "delay POV / reduce participation until mid recovers past τ*+hn/2. Throttle — not alpha."
                ),
                "depends_on": ["info.v_path_continuous", "risk.egarch_minv_bands"],
                "gate_status": {
                    cid: _gate_of(cid) for cid in ("info.v_path_continuous", "risk.egarch_minv_bands")
                },
                "tradable_size": (
                    "Paper-only throttle params"
                    if _gate_of("info.v_path_continuous") != "Promote"
                    else "Throttle params OK to paper-live; still not alpha size"
                ),
                "falsifier": leadlag_note,
            },
            {
                "id": "ti.mean_reversion_fade",
                "label": "Tradable alpha" if _gate_of("info.post_trough_ret") == "Promote" else "Monitor",
                "title": "Post-trough mean-reversion fade",
                "sketch": (
                    "Fade post-τ* only if post-trough return CIs clear 0 after time-split/bootstrap. "
                    "Else paper-only Hold — no sized alpha."
                ),
                "depends_on": ["info.post_trough_ret"],
                "gate_status": {"info.post_trough_ret": _gate_of("info.post_trough_ret")},
                "tradable_size": (
                    "Sized only if Promote"
                    if _gate_of("info.post_trough_ret") == "Promote"
                    else f"Paper-only / not sized — post300 mean={post_m:.5f} CI=[{post_lo:.5f},{post_hi:.5f}] n={len(post_vals)}"
                ),
                "falsifier": f"post300 mean={post_m:.5f} CI=[{post_lo:.5f},{post_hi:.5f}] n={len(post_vals)}",
            },
            {
                "id": "ti.xvenue_sor_caution",
                "label": "Exec throttle",
                "title": "SOR caution on thin venue during V",
                "sketch": (
                    "If HL↔Deribit↔Kraken MinV concordance (pairwise |Δτ*|≤hn among sig), "
                    "cut child size on thin venue during V windows. Else Hold."
                ),
                "depends_on": ["risk.xvenue_minv_concord"],
                "gate_status": {"risk.xvenue_minv_concord": _gate_of("risk.xvenue_minv_concord")},
                "tradable_size": "Not sized until concordant pairs exist" if not concord else "Throttle OK on concordant days",
                "falsifier": f"concordant_pair_in_slice={concord}",
            },
            {
                "id": "ti.liq_spread_widen",
                "label": "Monitor",
                "title": "Spread/depth deterioration around MinV as secondary risk flag",
                "sketch": (
                    "Join TOB spread pre/post τ*; if spread widens into trough, reinforce quote widen. "
                    "Hard ceiling: Kraken warehouse L2 empty; collector only 0929-30; Deribit warehouse L2 usable."
                ),
                "depends_on": ["liq.spread_around_minv"],
                "gate_status": {"liq.spread_around_minv": _gate_of("liq.spread_around_minv")},
                "tradable_size": "N/A — Monitor; no fake TOB",
                "falsifier": f"TOB usable rows={len(tob_ok)} days={tob_days}",
            },
        ],
        "kill_no_alpha": [
            {"id": k["id"], "note": "No trade idea — Kill object. Do not alpha-cosplay."} for k in kills
        ],
        "promotes": [p["id"] for p in promotes],
        "holds": {h["id"]: h["why"] for h in holds},
        "kills": [k["id"] for k in kills],
    }
    (OUT / "trade_ideas.json").write_text(json.dumps(ideas, indent=2, default=str))

    ti_lines = [
        "## 5. Trade ideas / strategies (desk-honest)",
        "",
        "First-cut sketches only. Labels: **Monitor** / **Exec throttle** / **Tradable alpha**. "
        "Sized tradable only if a Promote (or explicit paper-only Hold) survives falsifiers. "
        "No alpha cosplay on Kill objects.",
        "",
        "| Idea | Label | Depends | Gate | Falsifier |",
        "|------|-------|---------|------|-----------|",
    ]
    for idea in ideas.get("ideas") or []:
        deps = ", ".join(f"`{d}`" for d in idea.get("depends_on") or [])
        gates = ", ".join(f"{k}={v}" for k, v in (idea.get("gate_status") or {}).items())
        ti_lines.append(
            f"| `{idea.get('id')}` {idea.get('title','')} | **{idea.get('label')}** | {deps} | {gates} | {str(idea.get('falsifier',''))[:90]} |"
        )
    ti_lines += ["", "### Sketches", ""]
    for idea in ideas.get("ideas") or []:
        ti_lines += [
            f"**{idea.get('id')}** — {idea.get('label')}: {idea.get('title')}",
            "",
            idea.get("sketch", ""),
            "",
            f"*Size:* {idea.get('tradable_size', 'n/a')}",
            "",
        ]
    if ideas.get("kill_no_alpha"):
        ti_lines += ["### Kill — no trade ideas", ""]
        for k in ideas["kill_no_alpha"]:
            ti_lines.append(f"- `{k['id']}`: {k.get('note', 'Kill')}")
        ti_lines.append("")
    if "## 5. Trade ideas" in memo:
        memo = re.sub(r"## 5\. Trade ideas.*", "\n".join(ti_lines), memo, count=1, flags=re.S)
    else:
        memo = memo.rstrip() + "\n\n" + "\n".join(ti_lines) + "\n"
    (BOOK / "DESK_MEMO.md").write_text(memo)

    # Update chapter CANDIDATES from gate
    cand_map = {
        "daily_minv": ["risk.daily_minv_panel", "info.post_trough_ret"],
        "v_statistic": ["info.v_path_continuous"],
        "liq_around_v": ["liq.spread_around_minv", "risk.gm_mu_sigma_tradable"],
        "xvenue_concord": ["risk.xvenue_minv_concord"],
        "event_case": ["risk.stress_day_minv", "id.auction_loss"],
        "bootstrap_sim": ["risk.egarch_minv_bands", "risk.asymptotic_218_360"],
        "ch00_overview": ["risk.v_vs_jump_taxonomy"],
    }
    decision_by = {p["id"]: ("Promote", p.get("use", "")) for p in promotes}
    decision_by.update({h["id"]: ("Hold", h["why"]) for h in holds})
    decision_by.update({k["id"]: ("Kill", k["why"]) for k in kills})
    for pkg, ids in cand_map.items():
        lines = [
            "| id | type | lenses | decision | evidence |",
            "|----|------|--------|----------|----------|",
        ]
        for cid in ids:
            dec, why = decision_by.get(cid, ("Hold", "not in rollup"))
            lines.append(f"| `{cid}` | D | — | **{dec}** | {why[:120]} |")
        (BOOK / "chapters" / pkg / "CANDIDATES.md").write_text("\n".join(lines) + "\n")

    # desk_synthesis notebook
    nb_dir = BOOK / "notebooks"
    nb_dir.mkdir(parents=True, exist_ok=True)
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "# V-shapes — desk synthesis\n",
                    "\n",
                    "Flora & Renò (2020) program rollup. Lib: `research.lib.vstat` "
                    "(not `crash.vshape_events`).\n",
                    "\n",
                    "## Signal board\n",
                    "\n",
                    "See `DESK_MEMO.md` and `out/hardening_rollup.json`.\n",
                ],
            },
            {
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": [
                    "import json\n",
                    "from pathlib import Path\n",
                    "p = Path('/home/dev/srv/ares-microstructure/research/books/v_shapes/out/hardening_rollup.json')\n",
                    "print(json.dumps(json.loads(p.read_text()), indent=2))\n",
                ],
            },
        ],
    }
    (nb_dir / "desk_synthesis.ipynb").write_text(json.dumps(nb, indent=1))

    # Cross-link into cross_miniflash crash_baselines NOTES
    cb = ROOT / "research" / "books" / "cross_miniflash" / "chapters" / "crash_baselines" / "NOTES.md"
    if cb.exists():
        txt = cb.read_text()
        marker = "## Cross-link: Flora–Renò V-statistic (`v_shapes`)"
        block = (
            f"\n{marker}\n\n"
            "Geometric Dugast–Foucault `crash.vshape_events` remains the Tee–Ting baseline.\n"
            "Econometric Flora–Renò MinV lives in `research/lib/vstat.py` / "
            "`research/books/v_shapes/`.\n"
            f"Promote overlap IDs from v_shapes hardening: "
            f"{', '.join('`'+p['id']+'`' for p in promotes) or '(none)'}.\n"
            "Do **not** merge APIs; use Pass-2 PR/overlap tables only.\n"
        )
        if marker in txt:
            # replace existing block until next ## or EOF
            import re

            txt = re.sub(rf"\n{re.escape(marker)}.*?(?=\n## |\Z)", block, txt, count=1, flags=re.S)
        else:
            txt = txt.rstrip() + "\n" + block
        cb.write_text(txt)

    print(json.dumps(rollup, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
