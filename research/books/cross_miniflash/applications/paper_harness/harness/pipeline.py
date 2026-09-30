"""Orchestrate detector → ladder → shadow fills → daily risk report."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .actions import append_jsonl, write_jsonl
from .config import load_config
from .detect import detect_day
from .ladder import event_action_records
from .report import save_summary_json, summarize_day, write_figs, write_html, write_markdown
from .risk_stack import fire_pause_action_records
from .shadow_fills import fill_action_records, run_shadow

PKG = Path(__file__).resolve().parents[1]


def _day_out(root: Path, day: str, venue: str, symbol: str) -> Path:
    return root / f"{day}_{venue}_{symbol}"


def run_paper_day(
    day: str,
    *,
    config: str | Path | None = None,
    cfg: dict[str, Any] | None = None,
    out_root: str | Path | None = None,
    venue: str | None = None,
    symbol: str | None = None,
    quiet: bool = False,
) -> dict[str, Any]:
    """Run one UTC day paper harness (shadow only).

    Pipeline:
      1. Load warehouse tape (HL ETH default) via startarb/warehouse loaders
      2. Gated SSM detect (σ_m floor + 10bps/ic5) + Nanex∩SSM
      3. Ladder tiers → action log
      4. Shadow maker fills (baseline vs kill-ladder) against tape/TOB
      5. Daily risk report (md/html/json) + PNGs
    """
    cfg = dict(cfg or load_config(config))
    venue = (venue or cfg.get("venue") or "hyperliquid").lower()
    symbol = (symbol or cfg.get("symbol") or "ETH").upper()
    root = Path(out_root) if out_root else PKG / str(cfg.get("out_dir") or "out")
    day_dir = _day_out(root, day, venue, symbol)
    day_dir.mkdir(parents=True, exist_ok=True)

    if not quiet:
        print(f"[paper_harness] day={day} venue={venue} symbol={symbol} out={day_dir}")

    cell = detect_day(venue, symbol, day, cfg=cfg, quiet=quiet)
    if cell.get("skip"):
        summary = {
            "day": day,
            "venue": venue,
            "symbol": symbol,
            "skip": cell["skip"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        save_summary_json(summary, day_dir / "summary.json")
        return {"summary": summary, "out_dir": str(day_dir), "skipped": True}

    if cfg.get("require_complete_day", True) and not cell.get("complete"):
        reasons = (cell.get("completeness") or {}).get("reasons")
        raise RuntimeError(
            f"day {day} {venue} {symbol} incomplete (completeness={reasons}); "
            "pass require_complete_day: false to override"
        )

    # Drop heavy tape from action payload; shadow still uses cell["tape"]
    nest_hard = bool(cfg.get("nest_hard_pause", True))
    actions = event_action_records(
        cell, size_mult=cfg.get("size_mult"), nest_hard_pause=nest_hard
    )
    fire_pause_recs = []
    if bool(cfg.get("run_risk_gate_stack", True)):
        fire_pause_recs = fire_pause_action_records(
            cell, fire_pause_s=float(cfg.get("fire_pause_5m_s", 300.0))
        )
    session_hdr = {
        "kind": "session_start",
        "day": day,
        "venue": venue,
        "symbol": symbol,
        "mode": "paper",
        "class": "risk_policy",
        "live_orders": False,
        "n_gated": cell.get("ssm_10_n"),
        "ladder_breaks": cell.get("ladder_breaks"),
        "nest_hard_pause": nest_hard,
        "fire_pause_5m_s": float(cfg.get("fire_pause_5m_s", 300.0)),
        "risk_gate_stack": bool(cfg.get("run_risk_gate_stack", True)),
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    if not quiet:
        print(f"[paper_harness] gated_events={cell.get('ssm_10_n')} → shadow fills…")

    shadow = run_shadow(cell, cfg=cfg)
    fills = fill_action_records(
        shadow, day=day, symbol=symbol, venue=venue, strat="kill_ladder_maker"
    )
    stack_fills = []
    if (shadow.get("results") or {}).get("risk_gate_stack") is not None:
        stack_fills = fill_action_records(
            shadow, day=day, symbol=symbol, venue=venue, strat="risk_gate_stack"
        )

    all_actions = [session_hdr] + actions + fire_pause_recs + fills + stack_fills
    all_actions.append(
        {
            "kind": "session_end",
            "day": day,
            "venue": venue,
            "symbol": symbol,
            "n_actions": len(actions),
            "n_fire_pause": len(fire_pause_recs),
            "n_fills": len(fills),
            "n_stack_fills": len(stack_fills),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    )
    actions_path = write_jsonl(day_dir / "actions.jsonl", all_actions)

    summary = summarize_day(cell, shadow, actions, cfg=cfg)
    fig_paths = write_figs(shadow, day_dir, day=day, symbol=symbol, venue=venue)
    summary["figures"] = fig_paths
    summary["actions_jsonl"] = str(actions_path)
    summary["n_fire_pause_armed"] = len(fire_pause_recs)
    md_path = write_markdown(summary, fig_paths, day_dir / "RISK_REPORT.md")
    html_path = write_html(summary, fig_paths, day_dir / "RISK_REPORT.html")
    json_path = save_summary_json(summary, day_dir / "summary.json")

    # optional extra venues (detect+log only; primary shadow stays on primary venue)
    extras = []
    for v in cfg.get("extra_venues") or []:
        if v == venue:
            continue
        try:
            extra = detect_day(v, symbol, day, cfg=cfg, quiet=True)
            if extra.get("skip"):
                extras.append({"venue": v, "skip": extra["skip"]})
                continue
            ea = event_action_records(
                extra, size_mult=cfg.get("size_mult"), nest_hard_pause=nest_hard
            )
            for rec in ea:
                append_jsonl(actions_path, rec)
            extras.append(
                {
                    "venue": v,
                    "ssm_10_n": extra.get("ssm_10_n"),
                    "tier_counts": dict(
                        __import__("collections").Counter(
                            str(t) for t in list((extra.get("events") or {}).get("tier", []))
                        )
                    ),
                    "complete": extra.get("complete"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            extras.append({"venue": v, "error": f"{type(exc).__name__}: {exc}"})
    if extras:
        summary["extra_venues"] = extras
        save_summary_json(summary, json_path)

    if not quiet:
        print(
            f"[paper_harness] done fires={summary.get('n_fire')} "
            f"fills={len(fills)} report={md_path}"
        )

    return {
        "summary": summary,
        "out_dir": str(day_dir),
        "actions_jsonl": str(actions_path),
        "risk_report_md": str(md_path),
        "risk_report_html": str(html_path),
        "summary_json": str(json_path),
        "figures": fig_paths,
        "skipped": False,
        # keep shadow results in memory for tests; not written fully (large)
        "shadow_meta": {
            "book": shadow.get("book"),
            "fill_model": shadow.get("fill_model"),
            "n_trades_sim": shadow.get("n_trades_sim"),
            "n_fills_ladder": (shadow.get("results") or {})
            .get("kill_ladder_maker", {})
            .get("n_fills"),
            "n_fills_stack": (shadow.get("results") or {})
            .get("risk_gate_stack", {})
            .get("n_fills"),
            "delta_vs_baseline": shadow.get("delta_vs_baseline"),
            "delta_confirm_vs_baseline": shadow.get("delta_confirm_vs_baseline"),
            "delta_stack_vs_baseline": shadow.get("delta_stack_vs_baseline"),
        },
    }
