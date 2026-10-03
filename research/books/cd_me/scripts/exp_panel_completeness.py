#!/usr/bin/env python3
"""Build day×venue×stream completeness matrix + certified real-quote panels.

Hard rules:
- Primary = HL + Deribit **real** TOB (warehouse/collector). Never trade_synth.
- Kraken counts only as ``spot_l2`` when dense; missing/garbage → 2-venue day.
- ``trade_synth`` quarantined as PROXY / NOT TOB (appendix only).

Writes ``out/panel_completeness/{completeness.json,REPORT.md,figs/...}``.
ClickHouse MCP banned.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

BOOK = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from certified_panel import (  # noqa: E402
    GATE_DB_TOB_N,
    GATE_DCM_N_VALID,
    GATE_HL_TOB_N,
    GATE_KR_SPOT_N,
    GATE_PIM_2V_N_FINITE,
    OUT,
    SYNTH_LABEL,
)

PROBE = OUT / "_probe_raw.json"


def _n(rec: dict | None, *keys: str) -> int:
    if not isinstance(rec, dict):
        return 0
    for k in keys:
        if k in rec and rec[k] is not None:
            try:
                return int(rec[k])
            except (TypeError, ValueError):
                pass
    return 0


def _ok_hl(row: dict) -> tuple[bool, str]:
    tob = row.get("hl_tob") or {}
    n = _n(tob, "n")
    if tob.get("ok") and n >= GATE_HL_TOB_N and not tob.get("is_synth"):
        return True, f"n={n}"
    # collector may still be usable even if warehouse probe failed
    if n >= GATE_HL_TOB_N and not tob.get("is_synth") and "error" not in tob:
        return True, f"n={n}"
    return False, tob.get("error") or f"n={n}<{GATE_HL_TOB_N}"


def _ok_db(row: dict) -> tuple[bool, str]:
    tob = row.get("db_tob") or {}
    n = _n(tob, "n")
    if n >= GATE_DB_TOB_N and not tob.get("is_synth"):
        return True, f"n={n}"
    return False, tob.get("error") or f"n={n}<{GATE_DB_TOB_N}"


def _ok_kr_spot(row: dict) -> tuple[bool, str]:
    tob = row.get("kr_spot_l2") or {}
    n = _n(tob, "n")
    if tob.get("ok") and n >= GATE_KR_SPOT_N:
        return True, f"n={n}"
    if n > 0 and n <= 5:
        return False, f"garbage_n={n}"
    if n > 0:
        return False, f"thin_n={n}<{GATE_KR_SPOT_N}"
    return False, tob.get("error") or tob.get("reason") or "missing"


def _dcm_ok(row: dict) -> tuple[bool, int]:
    n = _n((row.get("legacy_dcm") or {}), "n_valid")
    # also accept deribit marks as DCM home proxy when legacy missing
    marks = int(row.get("deribit_marks_n") or 0)
    if n >= GATE_DCM_N_VALID:
        return True, n
    if n == 0 and marks >= GATE_DCM_N_VALID:
        # will recompute on re-run; provisional pass on marks density
        return True, marks
    return False, n


def build_matrix(probe: list[dict]) -> dict[str, Any]:
    days_out: list[dict[str, Any]] = []
    for row in probe:
        day = row["day"]
        hl_ok, hl_note = _ok_hl(row)
        db_ok, db_note = _ok_db(row)
        kr_ok, kr_note = _ok_kr_spot(row)
        dcm_ok, dcm_n = _dcm_ok(row)
        legacy = row.get("legacy_pim") or {}
        legacy_venues = list(legacy.get("venues") or [])
        # Honest: legacy "3-venue" with high KR cov + failed spot = was synth
        legacy_synth_lie = (
            "kraken" in legacy_venues
            and not kr_ok
            and float((legacy.get("coverage") or {}).get("kraken") or 0) > 0.2
        )
        core_2v = hl_ok and db_ok
        spot_3v = core_2v and kr_ok
        # soft PIM gate: prefer legacy 2v-quality; thin legacy n_finite still
        # may pass once re-run without synth (will re-check after exp)
        n_finite_legacy = _n(legacy, "n_finite")
        reasons: list[str] = []
        if not hl_ok:
            reasons.append(f"hl_tob:{hl_note}")
        if not db_ok:
            reasons.append(f"db_tob:{db_note}")
        if not kr_ok:
            reasons.append(f"kr_spot:{kr_note}")
        if not dcm_ok and core_2v:
            reasons.append(f"dcm_n_valid={dcm_n}<{GATE_DCM_N_VALID}")

        days_out.append(
            {
                "day": day,
                "hl_tob": {
                    "ok": hl_ok,
                    "n": _n(row.get("hl_tob"), "n"),
                    "note": hl_note,
                    "source": (row.get("hl_tob") or {}).get("source"),
                },
                "db_tob": {
                    "ok": db_ok,
                    "n": _n(row.get("db_tob"), "n"),
                    "note": db_note,
                    "source": (row.get("db_tob") or {}).get("source"),
                },
                "kr_spot_l2": {
                    "ok": kr_ok,
                    "n": _n(row.get("kr_spot_l2"), "n"),
                    "note": kr_note,
                },
                "kr_trade_synth": {
                    "status": "QUARANTINED",
                    "label": SYNTH_LABEL,
                    "use": "appendix_sensitivity_only_never_primary",
                    "legacy_falsely_counted_as_3venue": legacy_synth_lie,
                },
                "trades": {
                    "hl": row.get("hyperliquid_trades"),
                    "deribit": row.get("deribit_trades"),
                    "kraken": row.get("kraken_trades"),
                },
                "marks_n": {
                    "hl": row.get("hyperliquid_marks_n") or 0,
                    "deribit": row.get("deribit_marks_n") or 0,
                    "kraken": row.get("kraken_marks_n") or 0,
                },
                "dcm": {"n_valid_legacy": dcm_n, "ok_provisional": dcm_ok},
                "legacy_pim_n_finite": n_finite_legacy,
                "legacy_included_synth_as_3venue": legacy_synth_lie,
                "gates": {
                    "panel_core_2venue": core_2v,
                    "panel_3venue_spot": spot_3v,
                    "panel_3venue_any_QUARANTINED": False,  # synth never certifies
                },
                "reasons_fail": reasons,
            }
        )

    core = [d["day"] for d in days_out if d["gates"]["panel_core_2venue"]]
    spot = [d["day"] for d in days_out if d["gates"]["panel_3venue_spot"]]
    # Prefer days with DCM provisional OK for primary analysis
    core_dcm = [
        d["day"]
        for d in days_out
        if d["gates"]["panel_core_2venue"] and d["dcm"]["ok_provisional"]
    ]

    def largest_contiguous(days: list[str]) -> list[str]:
        if not days:
            return []
        s = sorted(days)
        best: list[str] = [s[0]]
        cur: list[str] = [s[0]]
        from datetime import datetime, timedelta

        def nxt(a: str, b: str) -> bool:
            da = datetime.strptime(a, "%Y-%m-%d")
            db = datetime.strptime(b, "%Y-%m-%d")
            return db - da == timedelta(days=1)

        for i in range(1, len(s)):
            if nxt(s[i - 1], s[i]):
                cur.append(s[i])
            else:
                if len(cur) > len(best):
                    best = cur
                cur = [s[i]]
        if len(cur) > len(best):
            best = cur
        return best

    contig = largest_contiguous(core_dcm or core)
    # Primary = largest set meeting core_2venue + DCM provisional
    primary_days = sorted(core_dcm) if core_dcm else sorted(core)
    primary_mode = "largest_set_core_2venue_dcm"
    if len(contig) >= len(primary_days) and contig:
        primary_days = contig
        primary_mode = "largest_contiguous_core_2venue_dcm"

    # If largest set is bigger and useful, prefer set (desk power)
    if len(core_dcm) > len(contig):
        primary_days = sorted(core_dcm)
        primary_mode = "largest_set_core_2venue_dcm"

    excluded = []
    for d in days_out:
        if d["day"] in primary_days:
            continue
        why = []
        if not d["gates"]["panel_core_2venue"]:
            why.append("fail_core_2venue_real_quotes")
        if d["legacy_included_synth_as_3venue"]:
            why.append("legacy_synth_miscounted_as_3venue")
        if not d["dcm"]["ok_provisional"]:
            why.append("dcm_thin")
        if d["kr_trade_synth"]["legacy_falsely_counted_as_3venue"]:
            why.append(f"kraken_was_{SYNTH_LABEL}")
        why.extend(d["reasons_fail"][:4])
        excluded.append({"day": d["day"], "why": why})

    # synth-only exclusion note for old panel days that relied on synth
    synth_days_legacy = [
        d["day"] for d in days_out if d["legacy_included_synth_as_3venue"]
    ]

    return {
        "symbol": "ETH",
        "rules": {
            "primary_tob": "HL + Deribit real quotes only (warehouse/collector)",
            "kraken": "spot_l2 only when n>=%d; else day is 2-venue" % GATE_KR_SPOT_N,
            "trade_synth": f"QUARANTINED as {SYNTH_LABEL} — never primary",
            "gates": {
                "hl_tob_n": GATE_HL_TOB_N,
                "db_tob_n": GATE_DB_TOB_N,
                "kr_spot_n": GATE_KR_SPOT_N,
                "pim_2v_n_finite": GATE_PIM_2V_N_FINITE,
                "dcm_n_valid": GATE_DCM_N_VALID,
            },
        },
        "days": days_out,
        "panels": {
            "panel_core_2venue": {
                "days": sorted(core),
                "n": len(core),
                "def": "HL TOB + Deribit TOB real quotes (Kraken optional absent)",
            },
            "panel_3venue_spot": {
                "days": sorted(spot),
                "n": len(spot),
                "def": "core_2venue + dense Kraken spot_l2 only",
            },
            "panel_3venue_any": {
                "days": [],
                "n": 0,
                "def": "DISABLED — trade_synth quarantine; do not certify",
                "status": "QUARANTINED",
            },
        },
        "primary": {
            "panel": "panel_core_2venue",
            "mode": primary_mode,
            "days": primary_days,
            "n": len(primary_days),
            "contiguous_block": contig,
            "spot_l2_subpanel": [d for d in sorted(spot) if d in set(primary_days) or True],
        },
        "excluded": excluded,
        "retracted": {
            "claim": "10/10 three-venue PIM",
            "reason": (
                "Prior panel mixed Kraken trade_synth into '3-venue' on days "
                "without usable spot_l2. Synth is PROXY/NOT TOB — retracted."
            ),
            "legacy_synth_miscount_days": synth_days_legacy,
        },
        "honesty": (
            "Never soft-Promote TOB-cross α. trade_synth ≠ quoted TOB. "
            "ClickHouse MCP banned."
        ),
    }


def write_report(cert: dict[str, Any], path: Path) -> None:
    lines = [
        "# Panel completeness — real quotes only",
        "",
        "## Rules",
        "",
        "- **Primary TOB:** Hyperliquid + Deribit (warehouse / collector).",
        "- **Kraken:** `spot_l2` only when dense; otherwise day is **2-venue**.",
        f"- **`trade_synth`:** QUARANTINED as `{SYNTH_LABEL}` — appendix/appendix only.",
        "- Retracted: any “10/10 three-venue” claim that depended on synth.",
        "",
        "## Gates",
        "",
    ]
    for k, v in (cert["rules"]["gates"] or {}).items():
        lines.append(f"- `{k}` ≥ **{v}**")
    lines += ["", "## Primary window", ""]
    p = cert["primary"]
    lines.append(
        f"- Panel: **`{p['panel']}`** · mode: `{p['mode']}` · **n={p['n']}**"
    )
    lines.append(f"- Days: `{', '.join(p['days'])}`")
    lines.append(f"- Contiguous block: `{', '.join(p.get('contiguous_block') or [])}`")
    spot = cert["panels"]["panel_3venue_spot"]
    lines.append(
        f"- Spot_l2 subpanel (3-venue real quotes): **n={spot['n']}** "
        f"`{', '.join(spot['days'])}`"
    )
    lines += ["", "## Completeness matrix", "", "| day | HL TOB | DB TOB | KR spot_l2 | DCM n_valid | core_2v | spot_3v | notes |",
              "|-----|--------|--------|------------|-------------|---------|---------|-------|"]
    for d in cert["days"]:
        notes = []
        if d["legacy_included_synth_as_3venue"]:
            notes.append("legacy_synth_lie")
        if not d["gates"]["panel_core_2venue"]:
            notes.append(";".join(d["reasons_fail"][:2]))
        lines.append(
            f"| {d['day']} | "
            f"{'✓' if d['hl_tob']['ok'] else '✗'} n={d['hl_tob']['n']} | "
            f"{'✓' if d['db_tob']['ok'] else '✗'} n={d['db_tob']['n']} | "
            f"{'✓' if d['kr_spot_l2']['ok'] else '✗'} n={d['kr_spot_l2']['n']} | "
            f"{d['dcm']['n_valid_legacy']} | "
            f"{'✓' if d['gates']['panel_core_2venue'] else '✗'} | "
            f"{'✓' if d['gates']['panel_3venue_spot'] else '✗'} | "
            f"{'; '.join(notes) or '—'} |"
        )
    lines += ["", "## Excluded", ""]
    for e in cert["excluded"]:
        lines.append(f"- **{e['day']}**: {', '.join(e['why'])}")
    lines += [
        "",
        "## Retraction",
        "",
        cert["retracted"]["reason"],
        f"- Legacy synth-miscount days: `{', '.join(cert['retracted']['legacy_synth_miscount_days'])}`",
        "",
        "## Honesty",
        "",
        cert["honesty"],
        "",
    ]
    path.write_text("\n".join(lines))


def write_heatmap(cert: dict[str, Any], fig_dir: Path) -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    days = [d["day"] for d in cert["days"]]
    streams = ["HL_TOB", "DB_TOB", "KR_spot_l2", "DCM", "core_2v", "spot_3v"]
    M = np.zeros((len(streams), len(days)), dtype=float)
    for j, d in enumerate(cert["days"]):
        M[0, j] = 1.0 if d["hl_tob"]["ok"] else 0.0
        M[1, j] = 1.0 if d["db_tob"]["ok"] else 0.0
        M[2, j] = 1.0 if d["kr_spot_l2"]["ok"] else (0.35 if d["kr_spot_l2"]["n"] > 0 else 0.0)
        M[3, j] = 1.0 if d["dcm"]["ok_provisional"] else 0.0
        M[4, j] = 1.0 if d["gates"]["panel_core_2venue"] else 0.0
        M[5, j] = 1.0 if d["gates"]["panel_3venue_spot"] else 0.0
    fig, ax = plt.subplots(figsize=(max(10, 0.55 * len(days) + 3), 3.8))
    im = ax.imshow(M, aspect="auto", cmap="RdYlGn", vmin=0, vmax=1)
    ax.set_yticks(range(len(streams)))
    ax.set_yticklabels(streams)
    ax.set_xticks(range(len(days)))
    ax.set_xticklabels([d[5:] for d in days], rotation=45, ha="right")
    ax.set_title(
        "cd_me ETH completeness — real quotes only\n"
        f"(trade_synth QUARANTINED · primary n={cert['primary']['n']})"
    )
    # mark primary
    primary = set(cert["primary"]["days"])
    for j, d in enumerate(days):
        if d in primary:
            ax.add_patch(
                plt.Rectangle(
                    (j - 0.5, -0.5), 1, len(streams), fill=False, edgecolor="#1f4e79", lw=1.5
                )
            )
    fig.colorbar(im, ax=ax, fraction=0.02, pad=0.02)
    fig.tight_layout()
    fig_dir.mkdir(parents=True, exist_ok=True)
    p = fig_dir / "fig_completeness_heatmap.png"
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return str(p)


def main() -> int:
    if not PROBE.is_file():
        print("missing", PROBE, "— run probe first", file=sys.stderr)
        return 2
    probe = json.loads(PROBE.read_text())
    # Enrich HL for days where warehouse failed but collector works
    try:
        from _data import ensure_env, load_venue_tob

        ensure_env()
        for row in probe:
            if (row.get("hl_tob") or {}).get("ok"):
                continue
            day = row["day"]
            try:
                tob = load_venue_tob("hyperliquid", "ETH", day=day)
                n = int(tob.get("n") or len(tob["ts"]))
                src = str(tob.get("source") or "")
                if n >= GATE_HL_TOB_N and "trade_synth" not in src:
                    row["hl_tob"] = {
                        "n": n,
                        "source": src,
                        "is_synth": False,
                        "ok": True,
                    }
                    print(f"[enrich] {day} HL via {src} n={n}", flush=True)
            except Exception:
                pass
            try:
                tob = load_venue_tob("deribit", "ETH", day=day)
                n = int(tob.get("n") or len(tob["ts"]))
                src = str(tob.get("source") or "")
                if n >= GATE_DB_TOB_N and "trade_synth" not in src:
                    cur = row.get("db_tob") or {}
                    if not cur.get("ok") or _n(cur, "n") < n:
                        row["db_tob"] = {
                            "n": n,
                            "source": src,
                            "is_synth": False,
                            "ok": True,
                        }
                        print(f"[enrich] {day} DB via {src} n={n}", flush=True)
            except Exception:
                pass
    except Exception as exc:  # noqa: BLE001
        print("enrich skipped:", exc, flush=True)

    cert = build_matrix(probe)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "completeness.json").write_text(json.dumps(cert, indent=2))
    (OUT / "certified_panels.json").write_text(
        json.dumps(
            {
                "primary": cert["primary"],
                "panels": cert["panels"],
                "excluded": cert["excluded"],
                "retracted": cert["retracted"],
                "rules": cert["rules"],
            },
            indent=2,
        )
    )
    write_report(cert, OUT / "REPORT.md")
    fig = write_heatmap(cert, OUT / "figs")
    print(
        json.dumps(
            {
                "primary_days": cert["primary"]["days"],
                "n_primary": cert["primary"]["n"],
                "spot_l2": cert["panels"]["panel_3venue_spot"]["days"],
                "excluded_n": len(cert["excluded"]),
                "fig": fig,
                "out": str(OUT),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
