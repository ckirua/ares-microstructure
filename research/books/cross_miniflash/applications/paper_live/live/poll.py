"""One paper-live poll: warehouse refresh → detect → ladder → shadow → persist."""


from __future__ import annotations

import os

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

PKG = Path(__file__).resolve().parents[1]
APP = PKG.parent
PAPER = APP / "paper_harness"
LAB = APP / "strategy_lab"  # sim.* / strategies (risk_stack + shadow_fills)
BOOK = APP.parent
ROOT = BOOK.parents[2]
STARTARB = Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb'))
SCRIPTS = APP / "scripts"
BOOK_SCRIPTS = BOOK / "scripts"

for p in (
    str(LAB),
    str(PAPER),
    str(PKG),
    str(ROOT),
    str(STARTARB / "src"),
    str(SCRIPTS),
    str(BOOK_SCRIPTS),
):
    if p not in sys.path:
        sys.path.insert(0, p)

from harness.actions import jsonable as _jsonable_raw  # noqa: E402
from harness.detect import detect_day  # noqa: E402
from harness.ladder import event_action_records  # noqa: E402
from harness.report import (  # noqa: E402
    save_summary_json,
    summarize_day,
    write_figs,
    write_html,
    write_markdown,
)
from harness.shadow_fills import fill_action_records, run_shadow  # noqa: E402

from .logging_setup import LOG  # noqa: E402

NS = 1_000_000_000


def jsonable(obj: Any) -> Any:
    """Like harness.actions.jsonable but bool before int (bool subclasses int)."""
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    return _jsonable_raw(obj)


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(jsonable(record), separators=(",", ":")) + "\n")


def utc_day(now: datetime | None = None) -> str:
    t = now or datetime.now(timezone.utc)
    return t.strftime("%Y-%m-%d")


def day_out(root: Path, day: str, venue: str, symbol: str) -> Path:
    return root / f"{day}_{venue}_{symbol}"


def _load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text()) or {}
    except Exception:
        return {}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(state), indent=2) + "\n")


def _collector_probe(cfg: dict[str, Any], day: str) -> dict[str, Any]:
    """Probe collector TOB day dir (does not load full book)."""
    data = cfg.get("data") or {}
    if not bool(data.get("use_collector_tob", True)):
        return {"available": False, "reason": "disabled"}
    root = Path(
        data.get("collector_tob_root")
        or (STARTARB / "results" / "xarb_md" / "tob")
    )
    day_dir = root / day.replace("-", "")
    if not day_dir.is_dir():
        return {"available": False, "root": str(root), "day_dir": str(day_dir)}
    files = sorted(day_dir.glob("tob_*.parquet"))
    mtimes = [f.stat().st_mtime for f in files] if files else []
    last_mtime = max(mtimes) if mtimes else None
    lag_s = (
        float(datetime.now(timezone.utc).timestamp() - last_mtime)
        if last_mtime is not None
        else None
    )
    return {
        "available": bool(files),
        "root": str(root),
        "day_dir": str(day_dir),
        "n_files": len(files),
        "last_mtime_utc": (
            datetime.fromtimestamp(last_mtime, tz=timezone.utc).isoformat()
            if last_mtime is not None
            else None
        ),
        "lag_s": lag_s,
    }


def _tape_tail_meta(cell: dict[str, Any]) -> dict[str, Any]:
    tape = cell.get("tape") or {}
    ts = np.asarray(tape.get("ts", []), dtype=np.int64)
    if ts.size == 0:
        return {"n_trades": 0, "last_ts": None, "last_age_s": None}
    last = int(ts.max())
    now_ns = int(datetime.now(timezone.utc).timestamp() * NS)
    return {
        "n_trades": int(ts.size),
        "last_ts": last,
        "last_age_s": max(0.0, (now_ns - last) / NS),
    }


def _event_fingerprint(rec: dict[str, Any]) -> str:
    return f"{rec.get('ts_end')}:{rec.get('tier')}:{rec.get('z_peak')}:{rec.get('nanex_overlap')}"


def _fills_by_regime(fills: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for f in fills:
        r = str(f.get("regime") or "?")
        out[r] = out.get(r, 0) + 1
    return out


def _tier_counts(cell: dict[str, Any]) -> dict[str, int]:
    ev = cell.get("events") or {}
    tiers = [str(t) for t in list(ev.get("tier", []))]
    out: dict[str, int] = {}
    for t in tiers:
        out[t] = out.get(t, 0) + 1
    return out


def poll_once(
    *,
    cfg: dict[str, Any],
    out_root: Path,
    day: str | None = None,
    poll_i: int = 0,
    write_figs_on_report: bool = False,
) -> dict[str, Any]:
    """One continuous-paper poll for venue×symbol×UTC day (shadow only).

    Pipeline:
      1. Re-list/load warehouse trade tape (S3→cache refresh)
      2. Probe collector TOB if present
      3. Gated SSM detect + Nanex∩SSM + kill-ladder tiers
      4. Shadow fills at trade print (baseline / kill-ladder / optional confirm)
      5. Append new actions.jsonl rows; refresh RISK_REPORT on change / cadence
    """
    if bool(cfg.get("live_orders")):
        raise RuntimeError("paper_live refuses live_orders=true — shadow only")

    venue = str(cfg.get("venue") or "hyperliquid").lower()
    symbol = str(cfg.get("symbol") or "ETH").upper()
    day = day or utc_day()
    day_dir = day_out(out_root, day, venue, symbol)
    day_dir.mkdir(parents=True, exist_ok=True)
    actions_path = day_dir / "actions.jsonl"
    state_path = day_dir / "state.json"
    state = _load_state(state_path)

    collector = _collector_probe(cfg, day)
    t0 = time_mono()

    # --- warehouse tape refresh (startarb loaders / DATA_PATHS) ---
    try:
        from startarb.env import ensure_env

        ensure_env()
    except Exception as exc:  # noqa: BLE001
        LOG.error("ensure_env failed: %s", exc)

    max_files = int(cfg.get("max_files") or 48)
    # Pass through to detect via monkeypatch on load? detect_day uses default
    # max_files=24 inside load_day_trades. Override by temporarily wrapping is
    # heavy — call detect_day which uses load_tape → load_day_trades.
    # Bump via cfg note: we re-export a thin wrapper if needed.
    try:
        cell = _detect_with_max_files(venue, symbol, day, cfg=cfg, max_files=max_files)
    except Exception as exc:  # noqa: BLE001
        LOG.error(
            "poll=%s day=%s warehouse load/detect FAIL: %s",
            poll_i,
            day,
            exc,
        )
        return {
            "ok": False,
            "day": day,
            "error": f"{type(exc).__name__}: {exc}",
            "collector": collector,
        }

    if cell.get("skip"):
        LOG.warning(
            "poll=%s day=%s skip=%s collector=%s",
            poll_i,
            day,
            cell.get("skip"),
            collector.get("available"),
        )
        state.update(
            {
                "day": day,
                "venue": venue,
                "symbol": symbol,
                "skip": cell.get("skip"),
                "poll_i": poll_i,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        _save_state(state_path, state)
        return {"ok": True, "skipped": True, "day": day, "skip": cell.get("skip")}

    tape_meta = _tape_tail_meta(cell)
    prev_n = int(state.get("n_trades") or 0)
    prev_last = state.get("last_ts")
    new_trades = int(tape_meta["n_trades"]) - prev_n
    tape_grew = (
        tape_meta["n_trades"] > prev_n
        or (tape_meta["last_ts"] is not None and tape_meta["last_ts"] != prev_last)
    )

    data_src = {
        "trade_tape": "warehouse",
        "warehouse_lag_s": tape_meta.get("last_age_s"),
        "collector_tob": collector,
        "note": (
            "Trades from warehouse S3/cache (minutes–hours lag typical). "
            "Collector TOB used for book when day dir exists; never mercat OE."
        ),
    }

    if not tape_grew and poll_i > 0 and state.get("last_summary"):
        # Heartbeat only — no re-sim
        LOG.info(
            "heartbeat poll=%s day=%s trades=%s last_age_s=%.0f "
            "gated=%s fires=%s collector=%s lag_s=%s "
            "cum_eq_ladder_bps=%s Δeq_bps=%s (no new tape)",
            poll_i,
            day,
            tape_meta["n_trades"],
            float(tape_meta.get("last_age_s") or 0.0),
            state.get("ssm_10_n"),
            state.get("n_fire"),
            collector.get("available"),
            (
                f"{collector['lag_s']:.0f}"
                if isinstance(collector.get("lag_s"), (int, float))
                else "—"
            ),
            state.get("cum_equity_ladder_bps"),
            state.get("delta_equity_bps"),
        )
        report_every = int(cfg.get("report_every_polls") or 6)
        force_report = report_every > 0 and (poll_i % report_every == 0)
        result = {
            "ok": True,
            "day": day,
            "changed": False,
            "tape": tape_meta,
            "data_source": data_src,
            "out_dir": str(day_dir),
            "elapsed_s": time_mono() - t0,
        }
        if force_report and (day_dir / "summary.json").is_file():
            LOG.info("heartbeat report refresh poll=%s → %s", poll_i, day_dir / "RISK_REPORT.md")
        return result

    # --- ladder actions (diff vs watermark) ---
    actions = event_action_records(cell, size_mult=cfg.get("size_mult"))
    seen_events = set(state.get("seen_event_fps") or [])
    new_actions = [a for a in actions if _event_fingerprint(a) not in seen_events]
    for a in new_actions:
        seen_events.add(_event_fingerprint(a))
        if a.get("kind") == "ladder_fire":
            esc = a.get("escalate") or ""
            LOG.info(
                "FIRE tier=%s z=%.2f dp=%.3f%% ic=%s nanex=%s %s day=%s ts_end=%s",
                a.get("tier"),
                float(a.get("z_peak") or 0.0),
                float(a.get("dp_pct") or 0.0),
                a.get("i_c"),
                a.get("nanex_overlap"),
                esc,
                day,
                a.get("ts_end"),
            )
        elif a.get("kind") == "ladder_observe":
            LOG.info(
                "tier observe z=%.2f dp=%.3f%% day=%s",
                float(a.get("z_peak") or 0.0),
                float(a.get("dp_pct") or 0.0),
                day,
            )

    prev_tiers = state.get("tier_counts") or {}
    cur_tiers = _tier_counts(cell)
    if cur_tiers != prev_tiers:
        LOG.info("tier_counts %s → %s", prev_tiers, cur_tiers)

    # --- shadow fills ---
    LOG.info(
        "shadow sim poll=%s day=%s trades=%s (+%s) gated=%s …",
        poll_i,
        day,
        tape_meta["n_trades"],
        max(0, new_trades),
        cell.get("ssm_10_n"),
    )
    try:
        shadow = run_shadow(cell, cfg=cfg)
    except Exception as exc:  # noqa: BLE001
        LOG.error("shadow FAIL poll=%s: %s", poll_i, exc)
        return {
            "ok": False,
            "day": day,
            "error": f"shadow:{type(exc).__name__}: {exc}",
            "tape": tape_meta,
            "data_source": data_src,
        }

    fills = fill_action_records(
        shadow, day=day, symbol=symbol, venue=venue, strat="kill_ladder_maker"
    )
    n_fills = len(fills)
    prev_n_fills = int(state.get("n_fills_ladder") or 0)
    delta_fills = n_fills - prev_n_fills
    by_reg = _fills_by_regime(fills)
    # Last few fills for optional detail (not full dump — keeps actions.jsonl tail-able)
    fill_tail = fills[-5:] if fills else []

    if delta_fills != 0 or poll_i == 0:
        LOG.info(
            "shadow_fills n=%s Δ=%s by_regime=%s fill_model=%s",
            n_fills,
            delta_fills,
            by_reg,
            shadow.get("fill_model"),
        )

    # session header once per day file
    if not actions_path.is_file() or actions_path.stat().st_size == 0:
        append_jsonl(
            actions_path,
            {
                "kind": "session_start",
                "mode": "paper_live",
                "day": day,
                "venue": venue,
                "symbol": symbol,
                "class": "risk_policy",
                "live_orders": False,
                "data_source": data_src,
                "ts": datetime.now(timezone.utc).isoformat(),
            },
        )

    for rec in new_actions:
        append_jsonl(actions_path, rec)

    # Summary only — never dump tens of thousands of per-fill rows into jsonl
    if delta_fills != 0 or poll_i == 0 or bool(new_actions):
        append_jsonl(
            actions_path,
            {
                "kind": "shadow_fills_summary",
                "day": day,
                "venue": venue,
                "symbol": symbol,
                "strat": "kill_ladder_maker",
                "n_fills": n_fills,
                "delta_fills": delta_fills,
                "by_regime": by_reg,
                "fill_model": shadow.get("fill_model"),
                "tail": fill_tail,
                "ts": datetime.now(timezone.utc).isoformat(),
            },
        )

    append_jsonl(
        actions_path,
        {
            "kind": "poll_tick",
            "day": day,
            "poll_i": poll_i,
            "n_trades": tape_meta["n_trades"],
            "new_trades": max(0, new_trades),
            "n_gated": cell.get("ssm_10_n"),
            "n_new_fires": sum(1 for a in new_actions if a.get("kind") == "ladder_fire"),
            "n_fills": n_fills,
            "delta_fills": delta_fills,
            "warehouse_lag_s": tape_meta.get("last_age_s"),
            "collector_available": collector.get("available"),
            "ts": datetime.now(timezone.utc).isoformat(),
        },
    )

    summary = summarize_day(cell, shadow, actions, cfg=cfg)
    summary["mode"] = "paper_live"
    summary["data_source"] = data_src
    summary["poll_i"] = poll_i
    summary["actions_jsonl"] = str(actions_path)

    report_every = int(cfg.get("report_every_polls") or 6)
    fills_changed = delta_fills != 0
    should_report = (
        bool(new_actions)
        or fills_changed
        or poll_i == 0
        or (report_every > 0 and poll_i % report_every == 0)
        or not (day_dir / "RISK_REPORT.md").is_file()
    )
    fig_paths: list[str] = []
    md_path = day_dir / "RISK_REPORT.md"
    html_path = day_dir / "RISK_REPORT.html"
    if should_report:
        if write_figs_on_report or poll_i == 0 or bool(new_actions):
            try:
                fig_paths = write_figs(
                    shadow, day_dir, day=day, symbol=symbol, venue=venue
                )
            except Exception as exc:  # noqa: BLE001
                LOG.warning("figs skip: %s", exc)
        summary["figures"] = fig_paths or list(state.get("figures") or [])
        write_markdown(summary, summary["figures"], md_path)
        write_html(summary, summary["figures"], html_path)
        save_summary_json(summary, day_dir / "summary.json")
        LOG.info(
            "RISK_REPORT refreshed → %s fires=%s fills=%s "
            "cum_eq_ladder_bps=%s Δeq_bps=%s",
            md_path,
            summary.get("n_fire"),
            (summary.get("shadow") or {}).get("kill_ladder", {}).get("n_fills"),
            ((summary.get("shadow") or {}).get("kill_ladder") or {}).get(
                "final_equity_bps"
            ),
            ((summary.get("shadow") or {}).get("delta_vs_baseline") or {}).get(
                "delta_equity_bps"
            ),
        )

    delta = shadow.get("delta_vs_baseline") or {}
    kl = (shadow.get("results") or {}).get("kill_ladder_maker") or {}
    if not kl:
        kl = shadow.get("kill_ladder") or {}
    cum_eq = kl.get("final_equity_bps")
    state = {
        "day": day,
        "venue": venue,
        "symbol": symbol,
        "poll_i": poll_i,
        "n_trades": tape_meta["n_trades"],
        "last_ts": tape_meta["last_ts"],
        "last_age_s": tape_meta.get("last_age_s"),
        "ssm_10_n": cell.get("ssm_10_n"),
        "n_fire": summary.get("n_fire"),
        "n_fills_ladder": (shadow.get("results") or {})
        .get("kill_ladder_maker", {})
        .get("n_fills"),
        "tier_counts": cur_tiers,
        "seen_event_fps": sorted(seen_events)[-5000:],
        "fill_model": shadow.get("fill_model"),
        "fills_by_regime": by_reg,
        "delta_equity_bps": delta.get("delta_equity_bps"),
        "cum_equity_ladder_bps": cum_eq,
        "v_fade_defaults": {
            "entry_mode": (cfg.get("v_fade") or {}).get("entry_mode", "severity_zend"),
            "z_min": (cfg.get("v_fade") or {}).get("z_min", 20.0),
            "confirm_s": (cfg.get("v_fade") or {}).get("confirm_s", 0.5),
            "exit_s": (cfg.get("v_fade") or {}).get("exit_s", 3.0),
            "suppress_fire_pause": (cfg.get("v_fade") or {}).get(
                "suppress_fire_pause", "prior_only"
            ),
        },
        "figures": summary.get("figures") or state.get("figures"),
        "data_source": data_src,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "last_summary": {
            "n_fire": summary.get("n_fire"),
            "ssm_10_n": summary.get("ssm_10_n"),
            "n_trades": summary.get("n_trades"),
            "cum_equity_ladder_bps": cum_eq,
            "delta_equity_bps": delta.get("delta_equity_bps"),
        },
    }
    _save_state(state_path, state)

    LOG.info(
        "poll=%s done day=%s trades=%s gated=%s fires=%s "
        "new_actions=%s fills=%s Δfills=%s "
        "cum_eq_ladder_bps=%s Δeq_bps=%s warehouse_lag_s=%.0f "
        "collector=%s elapsed=%.1fs",
        poll_i,
        day,
        tape_meta["n_trades"],
        cell.get("ssm_10_n"),
        summary.get("n_fire"),
        len(new_actions),
        n_fills,
        delta_fills,
        cum_eq,
        delta.get("delta_equity_bps"),
        float(tape_meta.get("last_age_s") or 0.0),
        collector.get("available"),
        time_mono() - t0,
    )

    return {
        "ok": True,
        "day": day,
        "changed": True,
        "tape": tape_meta,
        "data_source": data_src,
        "n_new_actions": len(new_actions),
        "n_fills": n_fills,
        "delta_fills": delta_fills,
        "summary": {
            "ssm_10_n": summary.get("ssm_10_n"),
            "n_fire": summary.get("n_fire"),
            "n_nanex_escalate": summary.get("n_nanex_escalate"),
            "tier_counts": cur_tiers,
            "delta_vs_baseline": delta,
            "fill_model": shadow.get("fill_model"),
        },
        "out_dir": str(day_dir),
        "actions_jsonl": str(actions_path),
        "risk_report_md": str(md_path),
        "elapsed_s": time_mono() - t0,
    }


def _detect_with_max_files(
    venue: str,
    symbol: str,
    day: str,
    *,
    cfg: dict[str, Any],
    max_files: int,
) -> dict[str, Any]:
    """detect_day with configurable warehouse max_files (fresher shard tail)."""
    from harness import detect as detect_mod
    from _data import ensure_env, load_day_trades

    def _load(venue: str, symbol: str, day: str, *, quiet: bool = True):
        ensure_env()
        return load_day_trades(
            venue, symbol, day, max_files=max_files, quiet=quiet
        )

    orig = detect_mod.load_tape
    detect_mod.load_tape = _load  # type: ignore[assignment]
    try:
        return detect_day(venue, symbol, day, cfg=cfg, quiet=True)
    finally:
        detect_mod.load_tape = orig


def time_mono() -> float:
    return time.monotonic()
