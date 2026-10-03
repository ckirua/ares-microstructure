#!/usr/bin/env python3
"""Build day×venue×stream completeness matrix + certified real-quote panels.

Hard rules:
- Primary = HL + Deribit **real** TOB (warehouse/collector). Never trade_synth.
- Kraken counts only as ``spot_l2`` when dense; missing/garbage → 2-venue day.
- ``trade_synth`` quarantined as PROXY / NOT TOB.
- GEX panel = core_2venue + dense Deribit option ``implied_vol`` (DDOI = trade-flow PROXY).
- Prefer cd_me days (2026-09-14…18, 25–27, 2026-10-01) when they pass.

Writes ``out/panel_completeness/{completeness.json,certified_panels.json,REPORT.md}``.
ClickHouse MCP banned. Never soft-Promote TOB-cross α.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

BOOK = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
MICRO_ROOT = BOOK.parents[2]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(MICRO_ROOT))

from certified_panel import (  # noqa: E402
    CANDIDATE_DAYS,
    CD_ME_PREFERRED_DAYS,
    DDOI_LABEL,
    GATE_DB_TOB_N,
    GATE_HL_TOB_N,
    GATE_KR_SPOT_N,
    GATE_MARKS_N,
    GATE_OPT_IV_N,
    GATE_OPT_TRADE_N,
    GEX_PROXY_LABEL,
    OUT,
    SYNTH_LABEL,
)

PROBE = OUT / "_probe_raw.json"
SYMBOL = "ETH"


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


def _ok_opt_iv(row: dict) -> tuple[bool, str]:
    opt = row.get("option_iv") or {}
    n = _n(opt, "n")
    if opt.get("ok") and n >= GATE_OPT_IV_N:
        return True, f"n={n}"
    return False, opt.get("error") or f"n={n}<{GATE_OPT_IV_N}"


def probe_option_iv(day: str) -> dict[str, Any]:
    from _data import load_eth_option_iv_day, load_eth_option_trades_day

    try:
        iv = load_eth_option_iv_day(day, max_files=12)
        out = {
            "ok": bool(iv.get("ok")) and int(iv.get("n") or 0) >= GATE_OPT_IV_N,
            "n": int(iv.get("n") or 0),
            "n_iv_raw": int(iv.get("n_iv_raw") or 0),
            "label": iv.get("label"),
            "error": iv.get("error"),
        }
    except Exception as exc:  # noqa: BLE001
        out = {"ok": False, "n": 0, "error": f"{type(exc).__name__}:{exc}"}
    try:
        tr = load_eth_option_trades_day(day, max_files=16)
        out["trades_n"] = int(tr.get("n") or 0)
        out["trades_ok"] = int(tr.get("n") or 0) >= GATE_OPT_TRADE_N
    except Exception as exc:  # noqa: BLE001
        out["trades_n"] = 0
        out["trades_ok"] = False
        out["trades_error"] = f"{type(exc).__name__}:{exc}"
    return out


def probe_day(day: str) -> dict[str, Any]:
    from _data import (
        ensure_env,
        load_day_marks,
        load_day_trades,
        load_kraken_spot_tob_day,
        load_venue_tob,
    )

    ensure_env()
    t0 = time.time()
    row: dict[str, Any] = {"day": day, "cd_me_preferred": day in CD_ME_PREFERRED_DAYS}

    try:
        tob = load_venue_tob("hyperliquid", SYMBOL, day=day, allow_kraken_synth=False)
        n = int(tob.get("n") or len(tob["ts"]))
        src = str(tob.get("source") or "")
        is_synth = bool(tob.get("is_synth")) or ("trade_synth" in src)
        row["hl_tob"] = {
            "n": n,
            "source": src,
            "is_synth": is_synth,
            "ok": n >= GATE_HL_TOB_N and not is_synth,
        }
    except Exception as exc:  # noqa: BLE001
        row["hl_tob"] = {"n": 0, "ok": False, "error": f"{type(exc).__name__}:{exc}", "is_synth": False}

    try:
        tob = load_venue_tob("deribit", SYMBOL, day=day, allow_kraken_synth=False)
        n = int(tob.get("n") or len(tob["ts"]))
        src = str(tob.get("source") or "")
        is_synth = bool(tob.get("is_synth")) or ("trade_synth" in src)
        row["db_tob"] = {
            "n": n,
            "source": src,
            "is_synth": is_synth,
            "ok": n >= GATE_DB_TOB_N and not is_synth,
        }
    except Exception as exc:  # noqa: BLE001
        row["db_tob"] = {"n": 0, "ok": False, "error": f"{type(exc).__name__}:{exc}", "is_synth": False}

    try:
        tob = load_kraken_spot_tob_day(SYMBOL, day)
        n = int(tob.get("n") or len(tob["ts"]))
        row["kr_spot_l2"] = {"ok": n >= GATE_KR_SPOT_N, "n": n, "source": tob.get("source")}
    except Exception as exc:  # noqa: BLE001
        row["kr_spot_l2"] = {"ok": False, "n": 0, "error": f"{type(exc).__name__}:{exc}"}

    for venue, key in (
        ("hyperliquid", "hyperliquid_marks_n"),
        ("deribit", "deribit_marks_n"),
        ("kraken", "kraken_marks_n"),
    ):
        try:
            m = load_day_marks(venue, SYMBOL, day, quiet=True)
            row[key] = int(m.get("n") or 0)
        except Exception as exc:  # noqa: BLE001
            row[key] = 0
            row[f"{venue}_marks_err"] = type(exc).__name__

    for venue, key in (("hyperliquid", "hyperliquid_trades"), ("deribit", "deribit_trades")):
        try:
            rec = load_day_trades(venue, SYMBOL, day, quiet=True)
            c = rec.get("completeness") or {}
            row[key] = {
                "n": int(c.get("n") or 0),
                "complete": bool(c.get("complete")),
                "cov": float(c.get("coverage") or 0.0),
            }
        except Exception as exc:  # noqa: BLE001
            row[key] = {"n": 0, "complete": False, "cov": 0.0, "error": type(exc).__name__}

    row["option_iv"] = probe_option_iv(day)
    row["elapsed_s"] = round(time.time() - t0, 1)
    return row


def run_probe(days: list[str], *, force: bool = False, probe_options: bool = True) -> list[dict[str, Any]]:
    OUT.mkdir(parents=True, exist_ok=True)
    by_day: dict[str, dict[str, Any]] = {}
    if PROBE.is_file():
        for r in json.loads(PROBE.read_text()):
            by_day[r["day"]] = r

    rows: list[dict[str, Any]] = []
    for day in days:
        row = by_day.get(day)
        need_tob = force or row is None or not (row.get("hl_tob") or {}).get("n")
        need_opt = probe_options and (
            force or row is None or "option_iv" not in row or not (row.get("option_iv") or {}).get("n")
        )
        if need_tob:
            print(f"[probe] {day} TOB…", flush=True)
            row = probe_day(day)
            by_day[day] = row
        elif need_opt and row is not None:
            print(f"[probe] {day} option IV…", flush=True)
            row["option_iv"] = probe_option_iv(day)
            row["cd_me_preferred"] = day in CD_ME_PREFERRED_DAYS
            by_day[day] = row
        else:
            print(f"[probe] reuse {day}", flush=True)
            if row is not None:
                row["cd_me_preferred"] = day in CD_ME_PREFERRED_DAYS
        assert row is not None
        rows.append(row)
        PROBE.write_text(json.dumps(list(by_day.values()), indent=2))
        opt = row.get("option_iv") or {}
        print(
            f"  HL={_n(row.get('hl_tob'),'n')} DB={_n(row.get('db_tob'),'n')} "
            f"KR={_n(row.get('kr_spot_l2'),'n')} opt_iv={opt.get('n',0)} "
            f"opt_tr={opt.get('trades_n',0)}",
            flush=True,
        )
    return rows


def build_matrix(probe: list[dict]) -> dict[str, Any]:
    days_out: list[dict[str, Any]] = []
    for row in probe:
        day = row["day"]
        hl_ok, hl_note = _ok_hl(row)
        db_ok, db_note = _ok_db(row)
        kr_ok, kr_note = _ok_kr_spot(row)
        opt_ok, opt_note = _ok_opt_iv(row)
        marks_n = int(row.get("deribit_marks_n") or 0)
        marks_ok = marks_n >= GATE_MARKS_N
        core_2v = hl_ok and db_ok
        spot_3v = core_2v and kr_ok
        gex_ok = core_2v and opt_ok
        reasons: list[str] = []
        if not hl_ok:
            reasons.append(f"hl_tob:{hl_note}")
        if not db_ok:
            reasons.append(f"db_tob:{db_note}")
        if not kr_ok:
            reasons.append(f"kr_spot:{kr_note}")
        if not opt_ok:
            reasons.append(f"option_iv:{opt_note}")
        if not marks_ok and core_2v:
            reasons.append(f"marks_n={marks_n}<{GATE_MARKS_N}")

        days_out.append(
            {
                "day": day,
                "cd_me_preferred": bool(row.get("cd_me_preferred")),
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
                "option_iv": {
                    "ok": opt_ok,
                    "n": _n(row.get("option_iv"), "n"),
                    "note": opt_note,
                    "trades_n": _n(row.get("option_iv"), "trades_n"),
                },
                "kr_trade_synth": {
                    "status": "QUARANTINED",
                    "label": SYNTH_LABEL,
                    "use": "appendix_sensitivity_only_never_primary",
                },
                "ddoi": {"label": DDOI_LABEL, "note": "trade-flow proxy; futures OI quarantined"},
                "trades": {"hl": row.get("hyperliquid_trades"), "deribit": row.get("deribit_trades")},
                "marks_n": {
                    "hl": row.get("hyperliquid_marks_n") or 0,
                    "deribit": marks_n,
                    "kraken": row.get("kraken_marks_n") or 0,
                },
                "marks": {"n_deribit": marks_n, "ok": marks_ok},
                "gates": {
                    "panel_core_2venue": core_2v,
                    "panel_3venue_spot": spot_3v,
                    "panel_gex_options": gex_ok,
                    "panel_3venue_any_QUARANTINED": False,
                },
                "reasons_fail": reasons,
            }
        )

    core = [d["day"] for d in days_out if d["gates"]["panel_core_2venue"]]
    spot = [d["day"] for d in days_out if d["gates"]["panel_3venue_spot"]]
    gex = [d["day"] for d in days_out if d["gates"]["panel_gex_options"]]

    preferred_gex = [d for d in CD_ME_PREFERRED_DAYS if d in set(gex)]
    preferred_core = [d for d in CD_ME_PREFERRED_DAYS if d in set(core)]
    if preferred_gex:
        primary_days = preferred_gex
        primary_mode = "cd_me_preferred_passing_gex_options"
        primary_panel = "panel_gex_options"
    elif preferred_core:
        primary_days = preferred_core
        primary_mode = "cd_me_preferred_passing_core_2venue"
        primary_panel = "panel_core_2venue"
    else:
        primary_days = sorted(gex) if gex else sorted(core)
        primary_mode = "largest_set_gex_or_core"
        primary_panel = "panel_gex_options" if gex else "panel_core_2venue"

    excluded = []
    for d in days_out:
        if d["day"] in primary_days:
            continue
        why = []
        if not d["gates"]["panel_core_2venue"]:
            why.append("fail_core_2venue_real_quotes")
        if not d["gates"]["panel_gex_options"]:
            why.append("fail_gex_options")
        why.extend(d["reasons_fail"][:4])
        excluded.append({"day": d["day"], "why": why})

    return {
        "symbol": SYMBOL,
        "rules": {
            "primary_tob": "HL + Deribit real quotes only (warehouse/collector)",
            "kraken": "spot_l2 only when n>=%d; else day is 2-venue" % GATE_KR_SPOT_N,
            "trade_synth": f"QUARANTINED as {SYNTH_LABEL} — never primary",
            "ddoi": f"{DDOI_LABEL} — warehouse open_interest is futures-only",
            "gex_vex": f"{GEX_PROXY_LABEL} — BS γ/vanna on Deribit option implied_vol",
            "gates": {
                "hl_tob_n": GATE_HL_TOB_N,
                "db_tob_n": GATE_DB_TOB_N,
                "kr_spot_n": GATE_KR_SPOT_N,
                "marks_n": GATE_MARKS_N,
                "opt_iv_n": GATE_OPT_IV_N,
                "opt_trade_n": GATE_OPT_TRADE_N,
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
            "panel_gex_options": {
                "days": sorted(gex),
                "n": len(gex),
                "def": "core_2venue + Deribit ETH option implied_vol (≥%d instruments)" % GATE_OPT_IV_N,
            },
            "panel_3venue_any": {
                "days": [],
                "n": 0,
                "def": "DISABLED — trade_synth quarantine; do not certify",
                "status": "QUARANTINED",
            },
        },
        "primary": {
            "panel": primary_panel,
            "mode": primary_mode,
            "days": primary_days,
            "n": len(primary_days),
            "cd_me_preferred": CD_ME_PREFERRED_DAYS,
            "spot_l2_subpanel": sorted(spot),
            "gex_options_subpanel": sorted(gex),
        },
        "excluded": excluded,
        "blockers": {
            "option_oi": (
                "Deribit warehouse open_interest is FUTURES-ONLY. "
                f"Option DDOI uses {DDOI_LABEL} (or live API OI snapshot)."
            ),
            "clickhouse_mcp": "BANNED — not used",
        },
        "honesty": (
            "Never soft-Promote TOB-cross α. trade_synth ≠ quoted TOB. "
            f"DDOI={DDOI_LABEL}. GEX={GEX_PROXY_LABEL}. ClickHouse MCP banned."
        ),
    }


def write_report(cert: dict[str, Any], path: Path) -> None:
    lines = [
        "# Panel completeness — squeeze_metrics (real quotes only)",
        "",
        "## Rules",
        "",
        "- **Primary TOB:** Hyperliquid + Deribit (warehouse / collector).",
        "- **Kraken:** `spot_l2` only when dense; otherwise day is **2-venue**.",
        f"- **`trade_synth`:** QUARANTINED as `{SYNTH_LABEL}`.",
        f"- **DDOI:** `{DDOI_LABEL}` — futures OI quarantined.",
        f"- **GEX/VEX:** `{GEX_PROXY_LABEL}` on Deribit option `implied_vol`.",
        "",
        "## Gates",
        "",
    ]
    for k, v in (cert["rules"]["gates"] or {}).items():
        lines.append(f"- `{k}` ≥ **{v}**")
    lines += ["", "## Primary window", ""]
    p = cert["primary"]
    lines.append(f"- Panel: **`{p['panel']}`** · mode: `{p['mode']}` · **n={p['n']}**")
    lines.append(f"- Days: `{', '.join(p['days'])}`")
    lines.append(f"- cd_me preferred: `{', '.join(p.get('cd_me_preferred') or [])}`")
    gex = cert["panels"]["panel_gex_options"]
    spot = cert["panels"]["panel_3venue_spot"]
    lines.append(f"- GEX options subpanel: **n={gex['n']}** `{', '.join(gex['days'])}`")
    lines.append(f"- Spot_l2 subpanel: **n={spot['n']}** `{', '.join(spot['days'])}`")
    lines += [
        "",
        "## Completeness matrix",
        "",
        "| day | HL TOB | DB TOB | KR spot | opt IV | core_2v | gex_opt | notes |",
        "|-----|--------|--------|---------|--------|---------|---------|-------|",
    ]
    for d in cert["days"]:
        notes = []
        if d.get("cd_me_preferred"):
            notes.append("cd_me")
        if not d["gates"]["panel_gex_options"]:
            notes.append(";".join(d["reasons_fail"][:2]))
        lines.append(
            f"| {d['day']} | "
            f"{'✓' if d['hl_tob']['ok'] else '✗'} n={d['hl_tob']['n']} | "
            f"{'✓' if d['db_tob']['ok'] else '✗'} n={d['db_tob']['n']} | "
            f"{'✓' if d['kr_spot_l2']['ok'] else '✗'} n={d['kr_spot_l2']['n']} | "
            f"{'✓' if d['option_iv']['ok'] else '✗'} n={d['option_iv']['n']} | "
            f"{'✓' if d['gates']['panel_core_2venue'] else '✗'} | "
            f"{'✓' if d['gates']['panel_gex_options'] else '✗'} | "
            f"{'; '.join(notes) or '—'} |"
        )
    lines += ["", "## Excluded", ""]
    for e in cert["excluded"]:
        lines.append(f"- **{e['day']}**: {', '.join(e['why'])}")
    lines += [
        "",
        "## Blockers",
        "",
        f"- Option OI: {cert['blockers']['option_oi']}",
        f"- ClickHouse: {cert['blockers']['clickhouse_mcp']}",
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
    streams = ["HL_TOB", "DB_TOB", "KR_spot", "opt_IV", "core_2v", "gex_opt"]
    M = np.zeros((len(streams), len(days)), dtype=float)
    for j, d in enumerate(cert["days"]):
        M[0, j] = 1.0 if d["hl_tob"]["ok"] else 0.0
        M[1, j] = 1.0 if d["db_tob"]["ok"] else 0.0
        M[2, j] = 1.0 if d["kr_spot_l2"]["ok"] else (0.35 if d["kr_spot_l2"]["n"] > 0 else 0.0)
        M[3, j] = 1.0 if d["option_iv"]["ok"] else 0.0
        M[4, j] = 1.0 if d["gates"]["panel_core_2venue"] else 0.0
        M[5, j] = 1.0 if d["gates"]["panel_gex_options"] else 0.0
    fig, ax = plt.subplots(figsize=(max(10, 0.55 * len(days) + 3), 3.8))
    im = ax.imshow(M, aspect="auto", cmap="RdYlGn", vmin=0, vmax=1)
    ax.set_yticks(range(len(streams)))
    ax.set_yticklabels(streams)
    ax.set_xticks(range(len(days)))
    ax.set_xticklabels([d[5:] for d in days], rotation=45, ha="right")
    ax.set_title(
        "squeeze_metrics ETH completeness — real quotes + option IV\n"
        f"(trade_synth QUARANTINED · primary n={cert['primary']['n']})"
    )
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
    preferred_only = "--preferred-only" in sys.argv
    force = "--force" in sys.argv
    if preferred_only:
        probe_days = list(CD_ME_PREFERRED_DAYS)
    else:
        probe_days = list(CD_ME_PREFERRED_DAYS) + [
            d for d in CANDIDATE_DAYS if d not in set(CD_ME_PREFERRED_DAYS)
        ]

    probe = run_probe(probe_days, force=force, probe_options=True)
    cert = build_matrix(probe)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "completeness.json").write_text(json.dumps(cert, indent=2))
    (OUT / "certified_panels.json").write_text(
        json.dumps(
            {
                "primary": cert["primary"],
                "panels": cert["panels"],
                "excluded": cert["excluded"],
                "blockers": cert["blockers"],
                "rules": cert["rules"],
            },
            indent=2,
        )
    )
    write_report(cert, OUT / "REPORT.md")
    try:
        fig = write_heatmap(cert, OUT / "figs")
    except Exception as exc:  # noqa: BLE001
        fig = f"heatmap_skipped:{exc}"
    print(
        json.dumps(
            {
                "primary_days": cert["primary"]["days"],
                "n_primary": cert["primary"]["n"],
                "primary_panel": cert["primary"]["panel"],
                "gex_options": cert["panels"]["panel_gex_options"]["days"],
                "spot_l2": cert["panels"]["panel_3venue_spot"]["days"],
                "excluded_n": len(cert["excluded"]),
                "fig": fig,
                "out": str(OUT),
                "blockers": cert["blockers"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
