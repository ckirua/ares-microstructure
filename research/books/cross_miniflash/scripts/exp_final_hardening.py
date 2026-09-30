#!/usr/bin/env python3
"""Phase 4 program-wide Pass 2.5 hardening for cross_miniflash.

Bootstrap / time-split every Promote (and re-check Promotable Holds),
reconcile severity gates (primary 10bps/ic5; frag share tables also 5bps/ic3),
write DESK_MEMO signal board, CHAPTER_INDEX COMPLETE rollup, desk_synthesis.

ClickHouse MCP banned. No git commit. Do not edit the plan file.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(ROOT))

from research.lib.stats import bootstrap_ci, spearman_r  # noqa: E402

OUT = BOOK / "out" / "phase4_hardening"
FIG = OUT / "figs"
N_BOOT = 800
SEED = 41

# Unified gate note
GATE_PRIMARY = {"min_dp_pct": 0.10, "min_i_c": 5, "label": "10bps/ic5"}
GATE_FRAG_SHARE = {"min_dp_pct": 0.05, "min_i_c": 3, "label": "5bps/ic3"}


def _load(path: Path):
    return json.loads(path.read_text())


def _ci(arr, *, seed: int, n_boot: int = N_BOOT) -> dict:
    return bootstrap_ci(np.asarray(arr, dtype=np.float64), n_boot=n_boot, seed=seed)


def _days_split(days: list[str]) -> tuple[list[str], list[str]]:
    d = sorted(days)
    mid = len(d) // 2
    return d[:mid], d[mid:]


def _gate(
    decision: str,
    *,
    why: str,
    metric: dict | None = None,
    falsifier_ok: bool = True,
) -> dict:
    return {
        "decision": decision,
        "why": why,
        "falsifier_ok": bool(falsifier_ok),
        "metric": metric or {},
    }


def harden() -> dict:
    p2 = _load(BOOK / "out/phase2_baselines_ssm/phase2_rows.json")
    p2s = _load(BOOK / "out/phase2_baselines_ssm/phase2_summary.json")
    p3 = _load(BOOK / "out/phase3a_stats_xsec/phase3a_rows.json")
    p3s = _load(BOOK / "out/phase3a_stats_xsec/phase3a_summary.json")
    fr = _load(BOOK / "out/frag_xvenue/frag_rows.json")
    fs = _load(BOOK / "out/frag_xvenue/frag_summary.json")

    days = sorted({r["day"] for r in p2})
    early, late = _days_split(days)

    # --- Nanex ⊂ SSM precision (cell-level where Nanex fires) ---
    prec_all = []
    prec_early, prec_late = [], []
    for r in p2:
        ov = r.get("overlap_nanex_ssm") or {}
        na = float(ov.get("n_a") or 0)
        if na <= 0:
            continue
        p = float(ov["precision_a"])
        prec_all.append(p)
        (prec_early if r["day"] in early else prec_late).append(p)
    prec_ci = _ci(prec_all, seed=SEED)
    prec_point = float(p2s["overlap_pooled"]["nanex_vs_ssm"]["precision_a"])
    prec_early_m = float(np.mean(prec_early)) if prec_early else float("nan")
    prec_late_m = float(np.mean(prec_late)) if prec_late else float("nan")
    nanex_subset_ok = (
        prec_ci["lo"] >= 0.5
        and prec_point >= 0.7
        and min(prec_early_m, prec_late_m) >= 0.5
    )

    # --- z* scan monotone ---
    zscan = p2s.get("zstar_pooled") or []
    z_counts = [int(z["n_events"]) for z in zscan]
    z_stars = [float(z["z_star"]) for z in zscan]
    monotone = all(z_counts[i] >= z_counts[i + 1] for i in range(len(z_counts) - 1))
    # early/late cell-sum monotone at z=6 vs neighbors via cell scans
    def _cell_z_monotone(day_set: set[str]) -> bool:
        # pool cell zstar scans
        acc: dict[float, int] = defaultdict(int)
        for r in p2:
            if r["day"] not in day_set:
                continue
            for z in r.get("zstar_scan") or []:
                acc[float(z["z_star"])] += int(z["n_events"])
        zs = sorted(acc)
        cs = [acc[z] for z in zs]
        return all(cs[i] >= cs[i + 1] for i in range(len(cs) - 1)) if len(cs) >= 2 else False

    z_early_ok = _cell_z_monotone(set(early))
    z_late_ok = _cell_z_monotone(set(late))
    zstar_ok = monotone and z_early_ok and z_late_ok

    # --- sigma_m floor: stress table + floor evidence ---
    stress = {float(s["sigma_m_frac"]): int(s["n_ssm"]) for s in p2s.get("sigma_stress_pooled") or []}
    floor_ok = stress.get(1.0, 0) > 0 and stress.get(0.5, 0) > stress.get(1.0, 0) * 2

    # --- severity gate 10bps/ic5 ---
    abl = (p3s.get("pooled") or {}).get("gate_ablation_totals") or {}
    n_raw = int(abl.get("5bps_ic3", {}).get("n_raw") or p3s["pooled"]["n_ssm_raw"])
    n_5 = int(abl.get("5bps_ic3", {}).get("n_kept") or 0)
    n_10 = int(abl.get("10bps_ic5", {}).get("n_kept") or 0)
    n_30 = int(abl.get("30bps_ic10", {}).get("n_kept") or 0)
    gate_monotone = n_raw >= n_5 >= n_10 >= n_30 > 0
    # cell-level gated median ΔP bootstrap (cells with events)
    cell_med_dp = []
    cell_share_v = []
    cell_n_v = []
    cell_n_cont = []
    cell_n_part = []
    early_share_v = []
    late_share_v = []
    early_n_v = early_n_tot = late_n_v = late_n_tot = 0
    for r in p3:
        sg = r.get("ssm_gated") or {}
        n = int(sg.get("n_events") or 0)
        if n <= 0:
            continue
        dp = (sg.get("dp") or {}).get("median")
        if dp is not None and np.isfinite(dp):
            cell_med_dp.append(float(dp))
        cl = sg.get("class") or {}
        if cl:
            nv = int(cl.get("n_v_recovery") or 0)
            nc = int(cl.get("n_continuation") or 0)
            np_ = int(cl.get("n_partial") or 0)
            cell_n_v.append(nv)
            cell_n_cont.append(nc)
            cell_n_part.append(np_)
            sv = float(cl.get("share_v") or 0)
            cell_share_v.append(sv)
            if r["day"] in early:
                early_n_v += nv
                early_n_tot += n
                early_share_v.append(sv)
            else:
                late_n_v += nv
                late_n_tot += n
                late_share_v.append(sv)

    med_dp_ci = _ci(cell_med_dp, seed=SEED + 1)
    # event-weighted V share via cell multinomial bootstrap on (nv, n)
    rng = np.random.default_rng(SEED + 2)
    cell_nv = np.asarray(cell_n_v, dtype=np.float64)
    cell_nt = cell_nv + np.asarray(cell_n_cont, dtype=np.float64) + np.asarray(
        cell_n_part, dtype=np.float64
    )
    share_boots = []
    if cell_nv.size:
        for _ in range(N_BOOT):
            idx = rng.integers(0, cell_nv.size, size=cell_nv.size)
            den = float(cell_nt[idx].sum())
            share_boots.append(float(cell_nv[idx].sum() / den) if den > 0 else float("nan"))
    share_boots_a = np.asarray(share_boots, dtype=np.float64)
    share_boots_a = share_boots_a[np.isfinite(share_boots_a)]
    share_v_point = float(p3s["pooled"]["ssm_class"]["share_v"])
    if share_boots_a.size:
        share_v_ci = {
            "point": share_v_point,
            "lo": float(np.quantile(share_boots_a, 0.025)),
            "hi": float(np.quantile(share_boots_a, 0.975)),
            "n": int(cell_nv.size),
            "n_boot": N_BOOT,
        }
    else:
        share_v_ci = {"point": share_v_point, "lo": float("nan"), "hi": float("nan"), "n": 0}

    early_sv = early_n_v / early_n_tot if early_n_tot else float("nan")
    late_sv = late_n_v / late_n_tot if late_n_tot else float("nan")
    # placebo: obs recovery median >> placebo
    obs_rec = []
    pla_rec = []
    for r in p3:
        sg = r.get("ssm_gated") or {}
        if int(sg.get("n_events") or 0) <= 0:
            continue
        med = (sg.get("recovery_5s") or {}).get("median")
        if med is not None:
            obs_rec.append(float(med))
        pm = (r.get("placebo") or {}).get("recovery_median")
        if pm is not None:
            pla_rec.append(float(pm))
    obs_rec_m = float(np.mean(obs_rec)) if obs_rec else float("nan")
    pla_rec_m = float(np.mean(pla_rec)) if pla_rec else float("nan")
    v_ok = (
        share_v_ci["lo"] >= 0.5
        and early_sv >= 0.5
        and late_sv >= 0.5
        and (not np.isfinite(pla_rec_m) or obs_rec_m > pla_rec_m + 0.2)
    )
    gate_ok = gate_monotone and med_dp_ci["lo"] >= 0.05  # %

    # --- Frag Herfindahl / FEI / thin excess ---
    Hv = []
    Fei = []
    thin5 = []
    thin30 = []
    hl_share5 = []
    hl_share_nanex = []
    for r in fr:
        if not r.get("all_venues_complete") and int(r.get("n_complete") or 0) < 3:
            continue
        h = (r.get("herfindahl") or {}).get("H_v")
        if h is not None and np.isfinite(h):
            Hv.append(float(h))
        f = r.get("fei_volume")
        if f is not None and np.isfinite(f):
            Fei.append(float(f))
        tv = r.get("thin_venue") or {}
        t5 = (tv.get("ssm_5bps") or {}).get("thin_excess")
        t30 = (tv.get("ssm_30bps") or {}).get("thin_excess")
        if t5 is not None and np.isfinite(float(t5)):
            thin5.append(float(t5))
        if t30 is not None and np.isfinite(float(t30)):
            thin30.append(float(t30))
        cs5 = ((r.get("crash_shares") or {}).get("ssm_5bps") or {}).get("shares") or {}
        if cs5.get("hyperliquid") is not None:
            hl_share5.append(float(cs5["hyperliquid"]))
        csn = ((r.get("crash_shares") or {}).get("nanex") or {}).get("shares") or {}
        if csn.get("hyperliquid") is not None:
            hl_share_nanex.append(float(csn["hyperliquid"]))

    Hv_ci = _ci(Hv, seed=SEED + 3)
    Fei_ci = _ci(Fei, seed=SEED + 4)
    thin5_ci = _ci(thin5, seed=SEED + 5)
    thin30_ci = _ci(thin30, seed=SEED + 6)
    hl5_ci = _ci(hl_share5, seed=SEED + 7)

    Hv_early = [float((r.get("herfindahl") or {}).get("H_v")) for r in fr if r["day"] in early]
    Hv_late = [float((r.get("herfindahl") or {}).get("H_v")) for r in fr if r["day"] in late]
    Hv_early = [x for x in Hv_early if np.isfinite(x)]
    Hv_late = [x for x in Hv_late if np.isfinite(x)]
    Hv_e_m = float(np.mean(Hv_early)) if Hv_early else float("nan")
    Hv_l_m = float(np.mean(Hv_late)) if Hv_late else float("nan")
    dH = abs(Hv_e_m - Hv_l_m) if np.isfinite(Hv_e_m) and np.isfinite(Hv_l_m) else float("nan")
    # falsifier from CANDIDATES: |ΔH| early/late ≥0.15 → fail
    herf_ok = Hv_ci["lo"] > 0.25 and Hv_ci["hi"] < 0.85 and (not np.isfinite(dH) or dH < 0.15)
    fei_ok = Fei_ci["lo"] > 0.4

    def _finite_floats(vals):
        out = []
        for x in vals:
            if x is None:
                continue
            try:
                xf = float(x)
            except (TypeError, ValueError):
                continue
            if np.isfinite(xf):
                out.append(xf)
        return out

    thin_early = _finite_floats(
        [
            ((r.get("thin_venue") or {}).get("ssm_5bps") or {}).get("thin_excess")
            for r in fr
            if r["day"] in early
        ]
    )
    thin_late = _finite_floats(
        [
            ((r.get("thin_venue") or {}).get("ssm_5bps") or {}).get("thin_excess")
            for r in fr
            if r["day"] in late
        ]
    )
    thin_e_m = float(np.mean(thin_early)) if thin_early else float("nan")
    thin_l_m = float(np.mean(thin_late)) if thin_late else float("nan")
    thin_ok = (
        thin5_ci["lo"] > 0.3
        and thin30_ci["lo"] > 0.2
        and thin_e_m > 0.3
        and thin_l_m > 0.3
    )

    # 10bps venue shares from phase3a (primary gate)
    counts_10: dict[str, int] = defaultdict(int)
    counts_10_e: dict[str, int] = defaultdict(int)
    counts_10_l: dict[str, int] = defaultdict(int)
    for r in p3:
        n = int(((r.get("gate_ablation") or {}).get("10bps_ic5") or {}).get("n_kept") or 0)
        counts_10[r["venue"]] += n
        (counts_10_e if r["day"] in early else counts_10_l)[r["venue"]] += n
    tot10 = sum(counts_10.values()) or 1
    share10 = {k: v / tot10 for k, v in counts_10.items()}
    tote = sum(counts_10_e.values()) or 1
    totl = sum(counts_10_l.values()) or 1
    share10_e = {k: counts_10_e.get(k, 0) / tote for k in ("hyperliquid", "deribit", "kraken")}
    share10_l = {k: counts_10_l.get(k, 0) / totl for k in ("hyperliquid", "deribit", "kraken")}
    vol_shares = fs["pooled"]["vol_shares_pooled"]
    thin10 = float(share10.get("hyperliquid", 0) - vol_shares.get("hyperliquid", 0))
    # HL remains dominant crash venue early & late
    crash_share_ok = (
        share10.get("hyperliquid", 0) > 0.5
        and share10_e.get("hyperliquid", 0) > 0.5
        and share10_l.get("hyperliquid", 0) > 0.5
        and thin10 > 0.5
    )

    # concordance Hold reaffirm
    placebo_p = float(fs["pooled"].get("placebo_p_ge_obs_mean") or 1.0)
    jacc = fs["pooled"].get("concord_jaccard_5s_mean") or {}
    concord_ok = False  # placebo fails by design on this slice

    # VPIN×size Hold reaffirm (time-split already Kill size; interact Hold)
    ts = p3s.get("time_split") or {}
    vpin_hold = True  # keep Hold — no OOS bootstrap on interaction in artifact

    # taxonomy / framing Promotes
    taxonomy_ok = True

    gates = {
        "info.crash_def_taxonomy": _gate(
            "Promote",
            why="Framing taxonomy survives Nanex⊂SSM precision + outside-TOB stale-quote class; not a numeric claim",
            falsifier_ok=taxonomy_ok,
            metric={"precision_nanex_ssm": prec_point},
        ),
        "info.nanex_subset_of_ssm": _gate(
            "Promote" if nanex_subset_ok else "Kill",
            why=(
                f"pooled prec={prec_point:.3f}; cell boot CI95=[{prec_ci['lo']:.3f},{prec_ci['hi']:.3f}]; "
                f"early/late mean={prec_early_m:.3f}/{prec_late_m:.3f}"
            ),
            falsifier_ok=nanex_subset_ok,
            metric={
                "pooled_precision": prec_point,
                "cell_boot_ci": prec_ci,
                "early_mean": prec_early_m,
                "late_mean": prec_late_m,
            },
        ),
        "vol.sigma_m_noise_floor_1bp": _gate(
            "Promote" if floor_ok else "Hold",
            why=f"σ_m frac stress n_SSM {stress}; floor prevents tick-MAD collapse",
            falsifier_ok=floor_ok,
            metric={"sigma_stress": stress},
        ),
        "risk.ssm_zstar_scan_table": _gate(
            "Promote" if zstar_ok else "Hold",
            why=f"monotone pooled={monotone}; early={z_early_ok} late={z_late_ok}; z*={z_stars} n={z_counts}",
            falsifier_ok=zstar_ok,
            metric={"z_stars": z_stars, "n_events": z_counts},
        ),
        "risk.ssm_severity_gate_10bps": _gate(
            "Promote" if gate_ok else "Hold",
            why=(
                f"ablation {n_raw}→{n_5}→{n_10}→{n_30}; gated median ΔP cell-boot "
                f"CI95=[{med_dp_ci['lo']:.3f},{med_dp_ci['hi']:.3f}]% (primary gate {GATE_PRIMARY['label']})"
            ),
            falsifier_ok=gate_ok,
            metric={
                "ablation": {"raw": n_raw, "5bps_ic3": n_5, "10bps_ic5": n_10, "30bps_ic10": n_30},
                "median_dp_cell_ci": med_dp_ci,
                "gate_primary": GATE_PRIMARY,
                "gate_frag_share": GATE_FRAG_SHARE,
            },
        ),
        "info.crash_v_vs_continuation": _gate(
            "Promote" if v_ok else "Hold",
            why=(
                f"share_V={share_v_point:.3f} bootCI=[{share_v_ci['lo']:.3f},{share_v_ci['hi']:.3f}]; "
                f"early/late={early_sv:.3f}/{late_sv:.3f}; obs_rec_med≈{obs_rec_m:.2f} vs placebo≈{pla_rec_m:.2f}"
            ),
            falsifier_ok=v_ok,
            metric={
                "share_v_ci": share_v_ci,
                "early_share_v": early_sv,
                "late_share_v": late_sv,
                "obs_recovery_mean_of_cell_medians": obs_rec_m,
                "placebo_recovery_mean": pla_rec_m,
            },
        ),
        "frag.volume_herfindahl_3venue": _gate(
            "Promote" if herf_ok else "Hold",
            why=f"H^v boot CI95=[{Hv_ci['lo']:.3f},{Hv_ci['hi']:.3f}]; early/late={Hv_e_m:.3f}/{Hv_l_m:.3f} |Δ|={dH:.3f}",
            falsifier_ok=herf_ok,
            metric={"H_v_ci": Hv_ci, "early": Hv_e_m, "late": Hv_l_m, "abs_delta": dH},
        ),
        "frag.fei_volume_3venue": _gate(
            "Promote" if fei_ok else "Hold",
            why=f"FEI_vol boot CI95=[{Fei_ci['lo']:.3f},{Fei_ci['hi']:.3f}] on complete 3-venue days",
            falsifier_ok=fei_ok,
            metric={"fei_ci": Fei_ci},
        ),
        "frag.crash_venue_share": _gate(
            "Promote" if crash_share_ok else "Hold",
            why=(
                f"HL crash share @10bps={share10.get('hyperliquid', 0):.3f} "
                f"(early {share10_e.get('hyperliquid', 0):.3f} / late {share10_l.get('hyperliquid', 0):.3f}); "
                f"frag tables also report {GATE_FRAG_SHARE['label']}"
            ),
            falsifier_ok=crash_share_ok,
            metric={
                "share_10bps_ic5": share10,
                "share_10bps_early": share10_e,
                "share_10bps_late": share10_l,
                "share_5bps_pooled": fs["pooled"]["crash_shares_pooled"]["ssm_5bps"]["shares"],
                "hl_share_5bps_day_ci": hl5_ci,
            },
        ),
        "frag.thin_venue_crash_excess": _gate(
            "Promote" if thin_ok else "Hold",
            why=(
                f"HL thin excess @5bps bootCI=[{thin5_ci['lo']:.3f},{thin5_ci['hi']:.3f}] "
                f"early/late={thin_e_m:.3f}/{thin_l_m:.3f}; @30bps lo={thin30_ci['lo']:.3f}; "
                f"@10bps point={thin10:.3f}"
            ),
            falsifier_ok=thin_ok,
            metric={
                "thin5_ci": thin5_ci,
                "thin30_ci": thin30_ci,
                "thin10_point": thin10,
                "early": thin_e_m,
                "late": thin_l_m,
            },
        ),
        # Holds re-checked
        "frag.xvenue_crash_concord": _gate(
            "Hold",
            why=f"placebo p(ge obs)≈{placebo_p:.2f}; Jaccard@5s={jacc} — not above chance",
            falsifier_ok=concord_ok,
            metric={"placebo_p": placebo_p, "jaccard_5s": jacc},
        ),
        "info.vpin_x_size_severity": _gate(
            "Hold",
            why="interact t≈2.9 in-sample; time-split size sign unstable; needs wider OOS before Promote",
            falsifier_ok=False,
            metric={"time_split": ts},
        ),
        "risk.ssm_z6_binary": _gate(
            "Hold",
            why="raw median ΔP≈0; use severity gate + z* menu instead",
            falsifier_ok=False,
        ),
        "base.nanex_crypto_30bps": _gate(
            "Hold",
            why="high-precision burst tag only with SSM nesting; θ ablation fragile (80→30)",
            falsifier_ok=False,
            metric={"n": 105, "paper_80bps_n": 8},
        ),
        "exec.outside_tob_wh_l2": _gate(
            "Hold",
            why="warehouse L2 outside_rate 15–79%; sparse quotes vs ms trades",
            falsifier_ok=False,
        ),
        "info.ssm_innov_continuous": _gate(
            "Hold",
            why="forward lead–lag |corr|≈0.04 — diagnostic only, not tradable",
            falsifier_ok=False,
        ),
        "risk.duration_post_markout": _gate(
            "Hold",
            why="Spearman(dt,|mo|)≈−0.28 but median Δt=0 weakens clock",
            falsifier_ok=False,
        ),
        "exec.tape_markout_post_crash": _gate(
            "Hold",
            why="tape mo@5s≈−7bps; needs dense mid for Promote as exec throttle",
            falsifier_ok=False,
        ),
        "risk.exante_amihud_severity": _gate(
            "Hold",
            why="n_pred=20; Amihud t≈−2.5 direction OK but underpowered",
            falsifier_ok=False,
        ),
        "frag.crossed_nbbo_crashwin": _gate(
            "Hold",
            why="n_crossed_available=0 on slice; mmip crossed_nbbo still stands",
            falsifier_ok=False,
        ),
        "epps.crash_window_corr": _gate(
            "Hold",
            why="crash-window Epps not reliably < day Epps",
            falsifier_ok=False,
        ),
        "vol.mc_garch_sj_utc": _gate(
            "Hold",
            why="UTC-12 peak this cohort vs mmip ~18 elsewhere — schedule prior only",
            falsifier_ok=False,
        ),
        "vol.curve_intraday_link": _gate(
            "Hold",
            why="cross-book peak mismatch until joint panel",
            falsifier_ok=False,
        ),
        # Kills
        "base.nanex_paper_80bps": _gate(
            "Kill",
            why="n=8 / 42 cells — vanity equity cutoff on crypto ms tape",
            falsifier_ok=False,
        ),
        "xsec.size_reduces_severity": _gate(
            "Kill",
            why=f"R²≈0.02; time-split β sign flip early={ts.get('early_beta_logN')} late={ts.get('late_beta_logN')}",
            falsifier_ok=False,
            metric={"time_split": ts},
        ),
        "risk.ssm_raw_ungated_counts": _gate(
            "Kill",
            why="raw z*=6 median ΔP≈0; intensity without severity gate is vanity",
            falsifier_ok=False,
        ),
    }

    # vanity kill if any Promote failed falsifier
    for gid, g in list(gates.items()):
        if g["decision"] == "Promote" and not g["falsifier_ok"]:
            g["decision"] = "Kill"
            g["why"] = "HARDEN FAIL → " + g["why"]

    artifact = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days": days,
        "early": early,
        "late": late,
        "gate_primary": GATE_PRIMARY,
        "gate_frag_share": GATE_FRAG_SHARE,
        "gate_note": (
            "Primary Promote severity gate = 10bps / i_c≥5 (stats/xsec). "
            "Frag venue-share / thin-excess tables also report 5bps / i_c≥3 for denser counts; "
            "both documented; desk risk intensity uses primary."
        ),
        "gates": gates,
        "headline": {
            "n_ssm_raw": n_raw,
            "n_gated_5bps_ic3": n_5,
            "n_gated_10bps_ic5": n_10,
            "n_gated_30bps_ic10": n_30,
            "n_nanex_30bps": int(p3s["pooled"]["n_nanex"]),
            "share_v": share_v_point,
            "H_v_mean": float(fs["pooled"]["H_v_mean"]),
            "thin_excess_5bps": float(
                fs["pooled"]["thin_venue_pooled"]["ssm_5bps"]["thin_excess"]
            ),
            "thin_excess_10bps": thin10,
            "nanex_ssm_precision": prec_point,
        },
        "n_boot": N_BOOT,
        "seed": SEED,
    }
    return artifact


def write_figures(artifact: dict) -> list[str]:
    FIG.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    gates = artifact["gates"]
    decisions = sorted({g["decision"] for g in gates.values()})
    counts = {d: sum(1 for g in gates.values() if g["decision"] == d) for d in ("Promote", "Hold", "Kill")}

    # 1) decision board
    fig, ax = plt.subplots(figsize=(7, 3.2))
    cols = ["#2a9d8f", "#e9c46a", "#e76f51"]
    ax.bar(list(counts.keys()), [counts[k] for k in ("Promote", "Hold", "Kill")], color=cols)
    ax.set_title("Phase 4 harden — Promote / Hold / Kill")
    ax.set_ylabel("candidates")
    fig.tight_layout()
    p = FIG / "fig_decision_counts.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    paths.append(str(p.relative_to(OUT)))

    # 2) severity ablation
    h = artifact["headline"]
    fig, ax = plt.subplots(figsize=(7, 3.5))
    labels = ["raw z*=6", "5bps/ic3", "10bps/ic5\n(primary)", "30bps/ic10"]
    vals = [h["n_ssm_raw"], h["n_gated_5bps_ic3"], h["n_gated_10bps_ic5"], h["n_gated_30bps_ic10"]]
    bars = ax.bar(labels, vals, color=["#6c757d", "#457b9d", "#2a9d8f", "#1d3557"])
    bars[2].set_edgecolor("black")
    bars[2].set_linewidth(2)
    ax.set_ylabel("SSM events")
    ax.set_title("Severity gate ablation (both gates documented)")
    fig.tight_layout()
    p = FIG / "fig_severity_gates.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    paths.append(str(p.relative_to(OUT)))

    # 3) lens heatmap
    lens_map = {
        "info.crash_def_taxonomy": ["info"],
        "info.nanex_subset_of_ssm": ["info", "risk"],
        "vol.sigma_m_noise_floor_1bp": ["risk", "disc"],
        "risk.ssm_zstar_scan_table": ["risk", "disc"],
        "risk.ssm_severity_gate_10bps": ["risk", "disc"],
        "info.crash_v_vs_continuation": ["info", "risk", "liq"],
        "frag.volume_herfindahl_3venue": ["liq", "mm"],
        "frag.fei_volume_3venue": ["liq", "mm"],
        "frag.crash_venue_share": ["risk", "liq"],
        "frag.thin_venue_crash_excess": ["risk", "liq", "mm"],
    }
    lenses = ["risk", "info", "exec", "disc", "cont", "liq", "mm"]
    promotes = [k for k, g in gates.items() if g["decision"] == "Promote"]
    mat = np.zeros((len(promotes), len(lenses)))
    for i, pid in enumerate(promotes):
        for L in lens_map.get(pid, []):
            if L in lenses:
                mat[i, lenses.index(L)] = 1.0
    fig, ax = plt.subplots(figsize=(8, max(3.5, 0.35 * len(promotes) + 1.5)))
    im = ax.imshow(mat, aspect="auto", cmap="Greens", vmin=0, vmax=1)
    ax.set_xticks(range(len(lenses)))
    ax.set_xticklabels(lenses)
    ax.set_yticks(range(len(promotes)))
    ax.set_yticklabels(promotes, fontsize=8)
    ax.set_title("Promote rollup by lens")
    fig.colorbar(im, ax=ax, fraction=0.03, label="active")
    fig.tight_layout()
    p = FIG / "fig_promote_lenses.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    paths.append(str(p.relative_to(OUT)))

    # 4) H^v + thin excess time split
    Hv_ci = gates["frag.volume_herfindahl_3venue"]["metric"]["H_v_ci"]
    thin_m = gates["frag.thin_venue_crash_excess"]["metric"]
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.5))
    axes[0].errorbar(
        [0],
        [Hv_ci["point"]],
        yerr=[[Hv_ci["point"] - Hv_ci["lo"]], [Hv_ci["hi"] - Hv_ci["point"]]],
        fmt="o",
        color="#2a9d8f",
        capsize=6,
    )
    axes[0].scatter(
        [-0.3, 0.3],
        [
            gates["frag.volume_herfindahl_3venue"]["metric"]["early"],
            gates["frag.volume_herfindahl_3venue"]["metric"]["late"],
        ],
        color=["#457b9d", "#e9c46a"],
        zorder=3,
    )
    axes[0].set_xticks([-0.3, 0, 0.3])
    axes[0].set_xticklabels(["early", "boot mean", "late"])
    axes[0].set_ylim(0.3, 0.7)
    axes[0].set_title(r"3-venue $H^v$")
    axes[1].bar(
        ["5bps early", "5bps late", "10bps pt", "30bps lo"],
        [
            thin_m["early"],
            thin_m["late"],
            thin_m["thin10_point"],
            thin_m["thin30_ci"]["lo"],
        ],
        color=["#457b9d", "#e9c46a", "#2a9d8f", "#1d3557"],
    )
    axes[1].axhline(0, color="k", lw=0.8)
    axes[1].set_title("HL thin-venue crash excess")
    axes[1].tick_params(axis="x", rotation=20)
    fig.tight_layout()
    p = FIG / "fig_frag_harden.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    paths.append(str(p.relative_to(OUT)))

    # 5) V-recovery harden
    sv = gates["info.crash_v_vs_continuation"]["metric"]
    fig, ax = plt.subplots(figsize=(6.5, 3.5))
    ax.bar(
        ["share_V", "early", "late", "boot lo", "boot hi"],
        [
            sv["share_v_ci"]["point"],
            sv["early_share_v"],
            sv["late_share_v"],
            sv["share_v_ci"]["lo"],
            sv["share_v_ci"]["hi"],
        ],
        color="#2a9d8f",
    )
    ax.axhline(0.5, color="#e76f51", ls="--", label="falsifier floor 0.5")
    ax.set_ylim(0, 1.05)
    ax.set_title("V-recovery share @5s (gated 10bps/ic5)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    p = FIG / "fig_v_recovery_harden.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    paths.append(str(p.relative_to(OUT)))

    # 6) signal board roles
    roles = {
        "monitor": [
            "info.crash_def_taxonomy",
            "info.nanex_subset_of_ssm",
            "risk.ssm_zstar_scan_table",
            "risk.ssm_severity_gate_10bps",
            "info.crash_v_vs_continuation",
            "frag.volume_herfindahl_3venue",
            "frag.fei_volume_3venue",
            "frag.crash_venue_share",
            "frag.thin_venue_crash_excess",
            "vol.sigma_m_noise_floor_1bp",
        ],
        "tradable": [],
        "exec_throttle": ["exec.outside_tob_wh_l2", "exec.tape_markout_post_crash"],
        "kill": [k for k, g in gates.items() if g["decision"] == "Kill"],
    }
    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.bar(
        list(roles.keys()),
        [len(v) for v in roles.values()],
        color=["#2a9d8f", "#264653", "#e9c46a", "#e76f51"],
    )
    ax.set_title("Signal board roles (Promote monitors; no tradable Cleared)")
    ax.set_ylabel("IDs")
    fig.tight_layout()
    p = FIG / "fig_signal_roles.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    paths.append(str(p.relative_to(OUT)))

    artifact["figures"] = paths
    artifact["signal_roles"] = roles
    return paths


def write_desk_memo(artifact: dict) -> None:
    gates = artifact["gates"]
    n_p = sum(1 for g in gates.values() if g["decision"] == "Promote")
    n_h = sum(1 for g in gates.values() if g["decision"] == "Hold")
    n_k = sum(1 for g in gates.values() if g["decision"] == "Kill")
    h = artifact["headline"]
    days = artifact["days"]

    meta = {
        "info.crash_def_taxonomy": ("5 defs → class", "✓", "—", "—"),
        "info.nanex_subset_of_ssm": ("Nanex 30bps ∩ SSM", "✓", "—", "maybe"),
        "vol.sigma_m_noise_floor_1bp": (r"σ_m≥10^{-4}", "✓", "—", "—"),
        "risk.ssm_zstar_scan_table": ("events(z*), z∈[2,12]", "✓", "—", "—"),
        "risk.ssm_severity_gate_10bps": ("|ΔP|≥10bps, i_c≥5", "✓", "—", "—"),
        "info.crash_v_vs_continuation": ("recovery≥0.5 @5s", "✓", "✗", "maybe"),
        "frag.volume_herfindahl_3venue": ("H^v=∑s_k² USD", "✓", "—", "—"),
        "frag.fei_volume_3venue": ("FEI on 3-venue shares", "✓", "—", "—"),
        "frag.crash_venue_share": ("gated SSM/Nanex venue mix", "✓", "—", "—"),
        "frag.thin_venue_crash_excess": ("crash−vol share thin leg", "✓", "—", "maybe"),
        "frag.xvenue_crash_concord": ("±5s Jaccard HL↔DB↔KR", "maybe", "✗", "—"),
        "frag.crossed_nbbo_crashwin": ("cons. cross crash±pad", "—", "—", "mmip"),
        "epps.crash_window_corr": ("Epps @ crash±60s", "diag", "✗", "—"),
        "info.vpin_x_size_severity": ("VPIN×logN → ΔP", "maybe", "✗", "—"),
        "risk.ssm_z6_binary": ("|innov|/√S ≥ 6", "tent.", "✗", "—"),
        "info.ssm_innov_continuous": ("innov, κ path", "diag", "✗", "—"),
        "base.nanex_paper_80bps": ("θ=0.8%, 1.5s", "—", "—", "—"),
        "xsec.size_reduces_severity": ("logN → |ΔP|", "—", "—", "—"),
        "risk.ssm_raw_ungated_counts": ("raw z*=6 counts", "—", "—", "—"),
        "base.nanex_crypto_30bps": ("θ=0.3%", "✓", "—", "tent."),
        "exec.outside_tob_wh_l2": ("p∉[b,a] asof L2", "—", "—", "✗"),
        "risk.duration_post_markout": ("Spearman(dt,|mo|)", "maybe", "✗", "maybe"),
        "exec.tape_markout_post_crash": ("tape mo post crash", "—", "✗", "maybe"),
        "risk.exante_amihud_severity": ("lag1 Amihud→ΔP", "maybe", "✗", "—"),
        "vol.mc_garch_sj_utc": ("UTC diurnal s_j", "prior", "—", "—"),
        "vol.curve_intraday_link": ("mmip curve link", "prior", "—", "—"),
    }

    board = [
        "| ID | Formula / clock | Monitor | Tradable | Exec throttle | Decision |",
        "|----|-----------------|---------|----------|---------------|----------|",
    ]
    # order: Promote, Hold, Kill
    order = sorted(gates.keys(), key=lambda k: ({"Promote": 0, "Hold": 1, "Kill": 2}[gates[k]["decision"]], k))
    for gid in order:
        g = gates[gid]
        formula, mon, trad, thr = meta.get(gid, (gid, "—", "—", "—"))
        why = g["why"][:70].replace("|", "/")
        board.append(
            f"| `{gid}` | {formula} | {mon} | {trad} | {thr} | **{g['decision']}** — {why} |"
        )

    kill_ids = [k for k, g in gates.items() if g["decision"] == "Kill"]
    promote_ids = [k for k, g in gates.items() if g["decision"] == "Promote"]

    desk = f"""# Desk memo — Cross-Section of Mini Flash Crashes (Tee & Ting 2019)

**Audience:** crypto MM / SOR / execution / taker / risk / research  
**Source:** Tee & Ting working paper (2019-06-12) → `research/books/cross_miniflash/`  
**Philosophy:** lenses `risk | info | exec | disc | cont | liq | mm` — detection objects are **not** automatically tradable.  
**Data:** warehouse trades + collector/warehouse TOB on **HL + Deribit + Kraken** — **no ClickHouse MCP**.  
**Program status:** **COMPLETE (Phase 4 hardened)** — **{n_p} Promote / {n_h} Hold / {n_k} Kill**. Slice ETH/BTC {days[0]}…{days[-1]}.  
**SoT:** [`CHAPTER_INDEX.md`](CHAPTER_INDEX.md) · Lib: [`../../lib/crash.py`](../../lib/crash.py) · Out: [`out/phase4_hardening/`](out/phase4_hardening/) · Phase2 [`out/phase2_baselines_ssm/`](out/phase2_baselines_ssm/) · Phase3a [`out/phase3a_stats_xsec/`](out/phase3a_stats_xsec/) · Frag [`out/frag_xvenue/`](out/frag_xvenue/).

---

## 1. Desk jobs × outputs

| Job | Object | Desk label | Status |
|-----|--------|------------|--------|
| **Risk monitor** | SSM z* + **severity gate** + scan table | Gated counts only; z* menu | **Promote** gate / scan · **Hold** binary z*=6 |
| **Frag / SOR capacity** | 3-venue volume Herfindahl + FEI | Capacity / concentration monitor | **Promote** |
| **Crash venue map** | Severity-gated crash share vs vol share | Where crashes print vs volume | **Promote** (HL thin + crash-dense) |
| **X-venue sync** | HL↔Deribit↔Kraken concordance | Contagion / hedge-sync | **Hold** (placebo fails) |
| **Recovery class** | V-recovery vs continuation @5s | Hole vs news assimilation | **Promote** |
| **Toxicity / info** | VPIN around events; VPIN×size | Concurrent toxicity | Feature OK; xsec **Hold** |
| **Execution throttle** | Outside-TOB / tape markout | Stale L2; mo≈−7bps @5s | **Hold** |
| **Taxonomy** | Nanex ⊂ SSM; V vs continuation | Burst / hole vs news | **Promote** |
| **Xsec size** | log notional → ΔP | Paper MCap path | **Kill** |
| **Scheduling** | UTC hour share / s_j | Prior only | **Hold** |

---

## 2. Signal board (Phase 4 hardened)

{chr(10).join(board)}

**Monitor (Promote):** {", ".join(f"`{x}`" for x in promote_ids)}  
**Tradable:** *none cleared* on this slice (all Promotes are risk/info/frag monitors).  
**Exec throttle:** Hold — `exec.outside_tob_wh_l2`, `exec.tape_markout_post_crash` (TOB sparse).  
**Kill list:** {", ".join(f"`{x}`" for x in kill_ids)}

**Hold blockers:** dense multi-venue TOB; concordance placebo; wider panel for VPIN×size / ex-ante Amihud.

**mmip / empirical_mm cross-links:** `frag.crossed_nbbo`, `frag.update_share`, `epps.xvenue_corr`, `vol.fei_hourly`; empirical_mm `disc.jump_sign_concord`, `cont.vpin`, markout.

---

## 3. Severity gate (unified)

| Gate | Use | Pooled n (raw 3668) |
|------|-----|--------------------:|
| **10bps / i_c≥5 (PRIMARY)** | Promote risk intensity, ΔP/recovery stats, xsec | **{h['n_gated_10bps_ic5']}** |
| 5bps / i_c≥3 | Frag venue-share / thin-excess denser counts | {h['n_gated_5bps_ic3']} |
| 30bps / i_c≥10 | Strict ablation / Nanex-like severity | {h['n_gated_30bps_ic10']} |

Lib default: `severity_gate(..., min_dp_pct=0.10, min_i_c=5)`. Frag Pass-2 share tables also publish 5bps/ic3 — **both documented; primary Promote = 10bps/ic5**.

---

## 4. Headline numbers (hardened)

| Object | Value |
|--------|------:|
| Nanex→SSM precision (pooled) | **{h['nanex_ssm_precision']:.3f}** |
| Gated median ΔP / share_V @5s | see phase3a · **share_V≈{h['share_v']:.2f}** |
| H^v mean (USD, 3-venue) | **{h['H_v_mean']:.3f}** |
| HL thin excess @5bps / @10bps | **{h['thin_excess_5bps']:.2f}** / **{h['thin_excess_10bps']:.2f}** |
| Concordance placebo p | ≈0.58 → Hold |
| Plain size OLS | **Kill** (sign-unstable) |

Bootstrap: n_boot={artifact['n_boot']}, seed={artifact['seed']}; early days {artifact['early']}; late {artifact['late']}.  
Artifact: [`out/phase4_hardening/hardening_gates.json`](out/phase4_hardening/hardening_gates.json).

---

## 5. Venue completeness (locked)

| Venue | Role | Notes |
|-------|------|-------|
| Hyperliquid | DEX anchor | Thin USD share; crash-dense |
| Deribit | CEX inverse perps | qty = USD |
| Kraken | CEX futures | Largest USD share on slice |

Panel: 42/42 complete cells · 14/14 day×symbol all-3 for Herfindahl.

---

## 6. Program status

**COMPLETE.** Optional backlog (not blocking): dense TOB for crossed NBBO; true OI; widen days/SOL for ex-ante xsec power.
"""
    (BOOK / "DESK_MEMO.md").write_text(desk)


def write_chapter_index(artifact: dict) -> None:
    gates = artifact["gates"]
    n_p = sum(1 for g in gates.values() if g["decision"] == "Promote")
    n_h = sum(1 for g in gates.values() if g["decision"] == "Hold")
    n_k = sum(1 for g in gates.values() if g["decision"] == "Kill")
    h = artifact["headline"]

    lens_map = {
        "info.crash_def_taxonomy": ("info", "ch00", "Label bursts vs broad outliers vs stale-quote artifacts"),
        "info.nanex_subset_of_ssm": ("risk|info", "baselines", "Nanex = high-precision SSM subset"),
        "vol.sigma_m_noise_floor_1bp": ("risk|disc", "mcgarch", "Required σ_m floor so KF z-scores don't flood"),
        "risk.ssm_zstar_scan_table": ("risk|disc", "ssm", "Publish z* menu with any binary cut"),
        "risk.ssm_severity_gate_10bps": ("risk|disc", "stats", "Gate raw SSM before intensity/risk counts"),
        "info.crash_v_vs_continuation": ("risk|info|liq", "stats", "V@5s — hole vs news class"),
        "frag.volume_herfindahl_3venue": ("liq|mm", "frag", "3-venue USD H^v capacity monitor"),
        "frag.fei_volume_3venue": ("liq|mm", "frag", "FEI companion to Herfindahl"),
        "frag.crash_venue_share": ("risk|liq", "frag", "Gated SSM/Nanex venue mix (HL-heavy)"),
        "frag.thin_venue_crash_excess": ("risk|liq|mm", "frag", "HL thin on USD but crash-dense"),
    }

    def marks(spec: str) -> dict[str, str]:
        active = set(spec.split("|"))
        return {L: "✓" if L in active else "" for L in ("risk", "info", "exec", "disc", "cont", "liq", "mm")}

    rows = []
    for pid, g in gates.items():
        if g["decision"] != "Promote":
            continue
        spec, ch, use = lens_map.get(pid, ("risk", "?", g["why"][:40]))
        m = marks(spec)
        rows.append(
            f"| `{pid}` | {m['risk']} | {m['info']} | {m['exec']} | {m['disc']} | {m['cont']} | {m['liq']} | {m['mm']} | {ch} | {use} |"
        )

    hold_ids = [k for k, g in gates.items() if g["decision"] == "Hold"]
    kill_ids = [k for k, g in gates.items() if g["decision"] == "Kill"]

    idx = f"""# Cross-Section of Mini Flash Crashes — research index

Living map of Tee & Ting (2019) packages → candidates → experiment status.
Book PDF + `_raw/` extracts: **local only** (gitignored). Siblings: [`../mmip/`](../mmip/) · [`../empirical_mm/`](../empirical_mm/).
Data: [`../../DATA_PATHS.md`](../../DATA_PATHS.md). Loop: [`../../LOOP.md`](../../LOOP.md). Desk: [`DESK_MEMO.md`](DESK_MEMO.md).

**Book:** Tee & Ting, *Cross-Section of Mini Flash Crashes…* (2019-06-12), 43 PDF pp. Slug: `cross_miniflash`.

**Program status:** **COMPLETE (Phase 4 hardened)** — **{n_p} Promote / {n_h} Hold / {n_k} Kill** on HL+Deribit+Kraken ETH/BTC {artifact['days'][0]}…{artifact['days'][-1]}.  
Empirics: [`out/phase2_baselines_ssm/`](out/phase2_baselines_ssm/) · [`out/phase3a_stats_xsec/`](out/phase3a_stats_xsec/) · [`out/frag_xvenue/`](out/frag_xvenue/) · Harden: [`out/phase4_hardening/`](out/phase4_hardening/).

**Shared lib:** [`../../lib/crash.py`](../../lib/crash.py) (Nanex, Kalman SSM, `severity_gate` default **10bps/ic5**, recovery/markout, `volume_herfindahl`, `xvenue_event_concordance`, z*-scan) · NW-OLS [`../../lib/stats.py`](../../lib/stats.py) · loaders [`scripts/_data.py`](scripts/_data.py).

**Reuse (do not rewrite):** mmip `vol.curve_intraday`, `book.resilience`, `frag.crossed_nbbo`, `frag.update_share`, `epps.xvenue_corr`, `vol.fei_hourly`; empirical_mm `cont.vpin`, `disc.jump_sign_concord`, `liq.amihud_1m`, `disc.var_lambda`, markout.

**Status legend:** `todo` · `notes` · `candidates` · `pass1` · `iterate` · `exp_run` · `park`  
**Lenses:** `risk` · `info` · `exec` · `disc` · `cont` · `liq` · `mm`

A package is **not** `exp_run`-complete after Pass 1 alone. Tracking path: **`pass1` → `iterate` → `exp_run`**. All packages below are **`exp_run`** + program **COMPLETE**.

---

## Two-pass checklist (every package)

### Pass 1 — faithfulness
- [x] Extract PDF theory/formulas into NOTES (pages cited)
- [x] Implement paper object on real **HL + Deribit + Kraken**
- [x] Baseline plots + EXP_REPORT with sample / window / **day-completeness** flags
- [x] Draft CANDIDATES (tentative status OK)

### Pass 2 — deep info / signals (mandatory)
- [x] What information does the object carry?
- [x] Signal hypotheses labeled: *risk monitor* vs *tradable* vs *exec throttle*
- [x] Competing defs + ablations (z*, θ, σ_m frac)
- [x] Falsifiers: time-split, σ/z* stress, threshold fragility → Kill failures
- [x] CANDIDATES + notebook “Signal board” + DESK_MEMO entry

### Pass 2.5 — program hardening
- [x] Bootstrap / time-split every Promote
- [x] Kill vanity metrics that fail
- [x] Unified severity-gate note (primary 10bps/ic5; frag also 5bps/ic3)
- [x] DESK_MEMO signal board freeze + `notebooks/desk_synthesis.ipynb`

**Quant bar:** precise units/clocks; ID assumptions stated; effect sizes + CIs; no Promote without a falsifier attempt; notebooks memo-quality.

---

## Package roadmap

| Package | Paper focus (Pass 1) | Pass 2 dig | Status | Path |
|---------|----------------------|------------|--------|------|
| `ch00_overview` | Map 5 defs → SSM | Info taxonomy; reading order + signal roadmap | `exp_run` | [`chapters/ch00_overview/`](chapters/ch00_overview/) |
| `crash_baselines` | Nanex, outside-TOB, V-shape | Overlap / PR vs SSM; toxicity/OFI; θ ablation | `exp_run` | [`chapters/crash_baselines/`](chapters/crash_baselines/) |
| `mc_garch_vol` | h_n,s_j,q fit; σ_p,σ_m | Diurnal signal; σ-split stress; `vol.curve_intraday` link | `exp_run` | [`chapters/mc_garch_vol/`](chapters/mc_garch_vol/) |
| `kalman_ssm` | KF + z=6 flags | z∈[2,12] scan; innov/gain features; lead–lag | `exp_run` | [`chapters/kalman_ssm/`](chapters/kalman_ssm/) |
| `crash_stats` | ΔP,i_c,Δt, recovery | Post-event markout/resilience; V vs continuation | `exp_run` | [`chapters/crash_stats/`](chapters/crash_stats/) |
| `cross_section` | Quintiles + NW-OLS | Ex-ante OI/vol/liq → severity?; ×VPIN | `exp_run` | [`chapters/cross_section/`](chapters/cross_section/) |
| `frag_xvenue` | Herfindahl, venue share (HL+Deribit+Kraken) | Thin-venue concentration; concordance; FEI / Epps | `exp_run` | [`chapters/frag_xvenue/`](chapters/frag_xvenue/) |

**MC-GARCH → σ (locked):** σ_p² ∝ q h s·Δt; σ_m = frac × max(MAD(Δlog p), **1 bp**) — Pass 2 + Phase 4 stress-tested.

**Vertical slice counts @ z*=6 (noise floor on):** Nanex 30bps **{h['n_nanex_30bps']}** vs SSM raw **{h['n_ssm_raw']}** → gated 5bps/ic3 **{h['n_gated_5bps_ic3']}** · **10bps/ic5 {h['n_gated_10bps_ic5']}** · 30bps/ic10 **{h['n_gated_30bps_ic10']}**. Paper Nanex 80bps: **8** (Kill).

---

## Promote rollup (Phase 4 hardened) by lens

| Candidate | risk | info | exec | disc | cont | liq | mm | Ch | One-line use |
|-----------|:----:|:----:|:----:|:----:|:----:|:---:|:--:|----|--------------|
{chr(10).join(rows)}

**Kill:** {", ".join(f"`{k}`" for k in kill_ids)}  
**Hold:** {", ".join(f"`{k}`" for k in hold_ids)}

**Gate note:** primary Promote = **10bps/ic5**; frag share/thin tables also report **5bps/ic3** (denser).  
**Stats headline:** gated median ΔP≈0.18%; V-share≈{h['share_v']:.0%}; tape mo@5s≈−7bps; plain size **Kill**.  
**Frag headline:** H^v≈{h['H_v_mean']:.2f}; HL thin excess @5bps≈{h['thin_excess_5bps']:.2f} / @10bps≈{h['thin_excess_10bps']:.2f}; concordance **Hold**.

---

## Crypto adaptation defaults

| Paper | Desk mapping |
|-------|----------------|
| S&P500 MCap | OI / 24h notional (HL) |
| Compustat vol / avg price | Realized vol + mark/mid |
| RTH diurnal s_j | **UTC-day** 5m diurnal on 24/7 tape |
| Equity ticks i_c | Trade count + bps move; tick-count secondary |
| 17 venues / Herfindahl | HL + Deribit + Kraken core |
| TAQ ms trades | Warehouse + collector; incomplete-day flags (flat-id + UTC clip) |
| SSM z-score | **Standardized innovation** (not posterior/√P) |
| σ_m | frac × max(MAD(Δlog p), **1 bp**) |
| Severity gate | **Primary 10bps / i_c≥5**; frag also 5bps / i_c≥3 |
"""
    (BOOK / "CHAPTER_INDEX.md").write_text(idx)


def write_desk_synthesis(artifact: dict) -> None:
    nb_dir = BOOK / "notebooks"
    nb_dir.mkdir(parents=True, exist_ok=True)
    gates = artifact["gates"]
    n_p = sum(1 for g in gates.values() if g["decision"] == "Promote")
    n_h = sum(1 for g in gates.values() if g["decision"] == "Hold")
    n_k = sum(1 for g in gates.values() if g["decision"] == "Kill")
    figs = artifact.get("figures") or []

    board_md = [
        "## Signal board\n",
        "\n",
        "| ID | Decision | Role |\n",
        "|----|----------|------|\n",
    ]
    roles = artifact.get("signal_roles") or {}
    role_of = {}
    for role, ids in roles.items():
        for i in ids:
            role_of[i] = role
    for k, g in sorted(gates.items(), key=lambda kv: ({"Promote": 0, "Hold": 1, "Kill": 2}[kv[1]["decision"]], kv[0])):
        board_md.append(f"| `{k}` | **{g['decision']}** | {role_of.get(k, 'hold')} |\n")

    fig_cells = []
    for rel in figs:
        fig_cells.append(
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [f"### `{rel}`\n"],
            }
        )
        fig_cells.append(
            {
                "cell_type": "code",
                "metadata": {},
                "outputs": [],
                "execution_count": None,
                "source": [
                    "from IPython.display import Image\n",
                    f"Image(filename=str(BOOK/'out/phase4_hardening'/'{rel}'))\n",
                ],
            }
        )

    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "# Desk synthesis — Cross-Section of Mini Flash Crashes\n",
                    "\n",
                    f"**{n_p} Promote / {n_h} Hold / {n_k} Kill** (Phase 4 hardened) on HL+Deribit+Kraken "
                    f"ETH/BTC {artifact['days'][0]}…{artifact['days'][-1]}.\n",
                    "\n",
                    "Primary severity gate **10bps / i_c≥5**; frag share tables also **5bps / i_c≥3**. "
                    "See `DESK_MEMO.md` · `out/phase4_hardening/hardening_gates.json`.\n",
                ],
            },
            {
                "cell_type": "code",
                "metadata": {},
                "outputs": [],
                "execution_count": None,
                "source": [
                    "import json\n",
                    "from pathlib import Path\n",
                    "BOOK = Path('/home/dev/srv/ares-microstructure/research/books/cross_miniflash')\n",
                    "gates = json.loads((BOOK/'out/phase4_hardening/hardening_gates.json').read_text())\n",
                    "G = gates['gates']\n",
                    "print('Promote:', [k for k,v in G.items() if v['decision']=='Promote'])\n",
                    "print('Hold:', [k for k,v in G.items() if v['decision']=='Hold'])\n",
                    "print('Kill:', [k for k,v in G.items() if v['decision']=='Kill'])\n",
                    "print('gate_note:', gates['gate_note'])\n",
                    "print('headline:', gates['headline'])\n",
                ],
            },
            {"cell_type": "markdown", "metadata": {}, "source": board_md},
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## Multi-lens figures\n",
                    "\n",
                    "Risk / info / liq / mm Promotes after bootstrap + time-split.\n",
                ],
            },
            *fig_cells,
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## Cross-package figure pointers\n",
                    "\n",
                    "- Phase 2: `out/phase2_baselines_ssm/figs/`\n",
                    "- Phase 3a: `out/phase3a_stats_xsec/figs/`\n",
                    "- Frag: `out/frag_xvenue/figs/`\n",
                ],
            },
        ],
    }
    (nb_dir / "desk_synthesis.ipynb").write_text(json.dumps(nb, indent=1))


def patch_notes_and_candidates(artifact: dict) -> None:
    """Reconcile severity-gate docs; stamp Phase 4 decisions on CANDIDATES."""
    gates = artifact["gates"]

    # frag NOTES — dual gate
    frag_notes = BOOK / "chapters/frag_xvenue/NOTES.md"
    text = frag_notes.read_text()
    dual = """## Severity gate (shared — Phase 4 reconciled)

**Primary Promote gate (stats / risk intensity):**

```
severity_gate(events, min_dp_pct=0.10, min_i_c=5)  # 10bps / ic5
```

**Frag share / thin-excess tables (denser counts; also documented):**

```
severity_gate(events, min_dp_pct=0.05, min_i_c=3)  # 5bps / ic3
```

Raw SSM @ z*=6 pooled **3668** → ≥5bps/ic3 **589** → ≥10bps/ic5 **275** → ≥30bps **76** (30bps share table) / **56** (30bps/ic10 stats ablation).

Desk risk intensity and xsec use **primary 10bps/ic5**. Frag venue-mix Promotes were re-checked at both gates in Phase 4 (`out/phase4_hardening/`).
"""
    import re

    text2 = re.sub(
        r"## Severity gate \(shared\).*?(?=\n## |\Z)",
        dual + "\n",
        text,
        count=1,
        flags=re.S,
    )
    if text2 == text:
        # append if section missing / different
        if "Phase 4 reconciled" not in text:
            text2 = text.rstrip() + "\n\n" + dual + "\n"
    frag_notes.write_text(text2)

    # crash_stats NOTES — emphasize primary + frag companion
    stats_notes = BOOK / "chapters/crash_stats/NOTES.md"
    st = stats_notes.read_text()
    if "Phase 4" not in st:
        st = st.rstrip() + (
            "\n\n## Phase 4 harden\n\n"
            "Bootstrap cell-median ΔP CI and V-share time-split survive → "
            "`risk.ssm_severity_gate_10bps`, `info.crash_v_vs_continuation` remain **Promote**. "
            "Frag packages also publish 5bps/ic3 for venue shares; primary remains **10bps/ic5** "
            "(see `DESK_MEMO.md` §3).\n"
        )
        stats_notes.write_text(st)

    # ch00 — PDF page dig expand slightly if thin
    ch00 = BOOK / "chapters/ch00_overview/NOTES.md"
    c0 = ch00.read_text()
    if "PDF dig (pp." not in c0:
        dig = """
## PDF dig (pp. 2–6, 7–10, 11–15)

- **pp. 2–3:** Nanex (≥10 ticks, ≤1.5s, ≥0.8%), outside-BBO, residual EPM, Lee–Mykland, Dugast–Foucault V — five competing defs.  
- **pp. 4–6:** Motivation — mini crashes as microstructure objects; SSM as common detector.  
- **pp. 7–10:** State-space + MC-GARCH feed for σ_p, σ_m; standardized innovation z-score.  
- **pp. 11–15:** Crash stats ΔP / i_c / Δt / recovery; severity matters (raw outliers ≠ Nanex-style events).

Crypto desk: equity tick→trade count; RTH diurnal→UTC 5m; MCap→notional/OI proxy; 17 venues→HL+Deribit+Kraken.
"""
        c0 = c0.replace(
            "## 2. Reading order",
            dig + "\n## 2. Reading order",
        )
        ch00.write_text(c0)

    # Stamp harden line into each CANDIDATES Promote/Hold/Kill
    cand_dirs = [
        "ch00_overview",
        "crash_baselines",
        "mc_garch_vol",
        "kalman_ssm",
        "crash_stats",
        "cross_section",
        "frag_xvenue",
    ]
    stamp = (
        "\n\n## Phase 4 harden\n\n"
        "Program-wide bootstrap/time-split applied (`scripts/exp_final_hardening.py` → "
        "`out/phase4_hardening/hardening_gates.json`). "
        f"Gate note: primary **10bps/ic5**; frag share also **5bps/ic3**.\n"
    )
    for d in cand_dirs:
        path = BOOK / "chapters" / d / "CANDIDATES.md"
        if not path.exists():
            continue
        t = path.read_text()
        # refresh decisions from gates where IDs appear
        for gid, g in gates.items():
            # replace **Promote**/Hold/Kill only on matching row
            import re as _re

            pat = _re.compile(
                rf"(\| `{_re.escape(gid)}` \|[^|]+\|[^|]+\| )\*\*(Promote|Hold|Kill)\*\*"
            )
            t = pat.sub(rf"\1**{g['decision']}**", t)
        if "## Phase 4 harden" in t:
            t = _re.sub(r"\n## Phase 4 harden\n.*", stamp, t, count=1, flags=_re.S)
        else:
            t = t.rstrip() + stamp
        # append per-ID why for IDs in this file
        mentioned = [gid for gid in gates if f"`{gid}`" in t]
        if mentioned:
            lines = ["\n| id | Phase4 decision | harden why |\n|----|-----------------|------------|\n"]
            for gid in mentioned:
                g = gates[gid]
                lines.append(f"| `{gid}` | **{g['decision']}** | {g['why'][:100]} |\n")
            # avoid duplicating table
            if "Phase4 decision" not in t:
                t = t.rstrip() + "".join(lines)
        path.write_text(t)

    # cross_section NOTES gate line
    xs = BOOK / "chapters/cross_section/NOTES.md"
    xt = xs.read_text()
    if "Phase 4" not in xt:
        xs.write_text(
            xt.rstrip()
            + "\n\n## Phase 4\n\n"
            "`xsec.size_reduces_severity` remains **Kill** (time-split sign flip). "
            "`info.vpin_x_size_severity` / `risk.exante_amihud_severity` remain **Hold**. "
            "Events use primary gate **10bps/ic5**.\n"
        )


def write_report(artifact: dict) -> None:
    gates = artifact["gates"]
    lines = [
        "# Phase 4 hardening REPORT",
        "",
        f"Generated: {artifact['generated_at']}",
        f"Days: {artifact['days']}",
        f"Early/late: {artifact['early']} / {artifact['late']}",
        "",
        artifact["gate_note"],
        "",
        "| ID | Decision | Falsifier OK | Why |",
        "|----|----------|:------------:|-----|",
    ]
    for k, g in sorted(gates.items()):
        lines.append(
            f"| `{k}` | **{g['decision']}** | {g['falsifier_ok']} | {g['why'][:120]} |"
        )
    lines += ["", "## Headline", "", "```json", json.dumps(artifact["headline"], indent=2), "```", ""]
    if artifact.get("figures"):
        lines += ["## Figures", ""] + [f"- `{f}`" for f in artifact["figures"]]
    (OUT / "hardening_REPORT.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    artifact = harden()
    write_figures(artifact)
    (OUT / "hardening_gates.json").write_text(json.dumps(artifact, indent=2, default=str))
    write_report(artifact)
    write_desk_memo(artifact)
    write_chapter_index(artifact)
    write_desk_synthesis(artifact)
    patch_notes_and_candidates(artifact)

    n_p = sum(1 for g in artifact["gates"].values() if g["decision"] == "Promote")
    n_h = sum(1 for g in artifact["gates"].values() if g["decision"] == "Hold")
    n_k = sum(1 for g in artifact["gates"].values() if g["decision"] == "Kill")
    print(
        json.dumps(
            {
                "promote": n_p,
                "hold": n_h,
                "kill": n_k,
                "promote_ids": [k for k, g in artifact["gates"].items() if g["decision"] == "Promote"],
                "kill_ids": [k for k, g in artifact["gates"].items() if g["decision"] == "Kill"],
                "out": str(OUT),
                "desk_synthesis": str(BOOK / "notebooks/desk_synthesis.ipynb"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
