"""SHADOW PAPER helpers — latest complete day, gap candidate, honesty banner."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .causal import jsonable
from .kill import _boot_mean

PKG = Path(__file__).resolve().parents[1]
SCRIPTS = PKG.parents[2] / "scripts"  # cross_miniflash/scripts
WAREHOUSE_SRC = Path("/home/dev/lab/lab-n2070/warehouse/src")
STARTARB = Path("/home/dev/srv/ares-startarb")

HONESTY_BANNER = (
    "**SHADOW PAPER** · `research_sim` · `live_orders=false` · "
    "lab = −mo₅ₛ−RT4 · path = entry@confirm→exit tape · **not** live OE"
)


def honesty_dict(
    *,
    mode: str = "shadow_paper",
    path_policy: str | None = None,
) -> dict[str, Any]:
    return {
        "mode": mode,
        "slice": "research_sim_on_real_tape",
        "strategy": "causal_fade_v_only",
        "fills": "tape_print_asof_shadow",
        "scoreboard": "lab_identity_-mo5s_minus_RT4",
        "path_pnl": "entry_to_exit_tape_print",
        "path_vs_lab": "path_may_differ_residual_hold",
        "mid_mo": "null_ignored_use_tape_mo",
        "live_orders": False,
        "alpha_claim": False,
        "clickhouse_mcp": False,
        "not_mm": True,
        "path_policy": path_policy,
    }


def apply_vf_overrides(cfg: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, Any]:
    """Merge CLI / gap_summary v_fade overrides into a deep-copied config."""
    out = dict(cfg)
    vf = dict(out.get("v_fade") or {})
    if overrides:
        for k, v in overrides.items():
            if v is None:
                continue
            vf[k] = v
    out["v_fade"] = vf
    return out


def load_gap_summary(path: str | Path | None = None) -> dict[str, Any] | None:
    p = Path(path) if path else PKG / "out" / "gap_summary.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def path_candidate_overrides(gap: dict[str, Any] | None) -> dict[str, Any] | None:
    """Extract best executable params from sibling gap_summary.json if present."""
    if not gap:
        return None
    for key in ("best_policy", "best_executable", "path_optimized", "candidate"):
        block = gap.get(key)
        if isinstance(block, dict) and block:
            pol = _normalize_policy(block)
            if pol:
                return pol
    # flat keys at top level
    flat_keys = ("confirm_s", "exit_s", "adverse_stop_bps", "v_threshold_r2", "soft_confirm_r1")
    if any(k in gap for k in flat_keys):
        pol = _normalize_policy(gap)
        if pol:
            return pol
    return None


def _normalize_policy(block: dict[str, Any]) -> dict[str, Any]:
    """Map common alias names → v_fade config keys."""
    aliases = {
        "confirm_s": "confirm_s",
        "entry_delay_s": "confirm_s",
        "entry_s": "confirm_s",
        "exit_s": "exit_s",
        "exit_horizon_s": "exit_s",
        "hold_s": "exit_s",
        "adverse_stop_bps": "adverse_stop_bps",
        "v_threshold_r2": "v_threshold_r2",
        "soft_confirm_r1": "soft_confirm_r1",
        "cont_threshold_r2": "cont_threshold_r2",
        "rt_friction_bps": "rt_friction_bps",
    }
    out: dict[str, Any] = {}
    params = block.get("params") if isinstance(block.get("params"), dict) else block
    for src, dst in aliases.items():
        if src in params and params[src] is not None:
            try:
                out[dst] = float(params[src])
            except (TypeError, ValueError):
                continue
    return out


def _ensure_data_path() -> None:
    for p in (str(SCRIPTS), str(WAREHOUSE_SRC), str(STARTARB / "src")):
        if p not in sys.path:
            sys.path.insert(0, p)


def list_warehouse_days(venue: str = "hyperliquid") -> list[str]:
    _ensure_data_path()
    from _data import ensure_env, resolve_days  # noqa: WPS433

    ensure_env()
    return list(resolve_days(None, venue, n=0))


def find_latest_complete_day(
    venue: str = "hyperliquid",
    symbol: str = "ETH",
    *,
    lookback: int = 21,
    quiet: bool = True,
) -> dict[str, Any]:
    """Walk listing cache newest→oldest until day_completeness.complete."""
    _ensure_data_path()
    from _data import ensure_env, load_day_trades  # noqa: WPS433

    ensure_env()
    days = list_warehouse_days(venue)
    if not days:
        raise RuntimeError(f"no warehouse listing days for {venue}")
    probed: list[dict[str, Any]] = []
    for day in reversed(days[-max(lookback, 1) :]):
        try:
            rec = load_day_trades(venue, symbol, day, quiet=True)
            flags = rec.get("completeness") or {}
            row = {
                "day": day,
                "complete": bool(flags.get("complete")),
                "n": flags.get("n"),
                "coverage": flags.get("coverage"),
                "reasons": flags.get("reasons"),
            }
            probed.append(row)
            if row["complete"]:
                if not quiet:
                    print(f"[shadow] latest complete day={day} n={row['n']} cov={row['coverage']}")
                return {"day": day, "completeness": flags, "probed": probed}
        except Exception as exc:  # noqa: BLE001
            probed.append({"day": day, "complete": False, "error": f"{type(exc).__name__}: {exc}"})
    raise RuntimeError(
        f"no complete {venue} {symbol} day in last {lookback} listings; probed={probed}"
    )


def _fmt(x: Any) -> str:
    if x is None:
        return "—"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    if not np.isfinite(v):
        return "—"
    return f"{v:.2f}"


def write_shadow_board(
    *,
    out_root: Path,
    day: str,
    venue: str,
    symbol: str,
    lab_run: dict[str, Any],
    path_run: dict[str, Any] | None,
    gap: dict[str, Any] | None,
    panel_days: list[str] | None = None,
) -> Path:
    """Living SHADOW_BOARD.md at out_root (also writes shadow trades.jsonl)."""
    out_root.mkdir(parents=True, exist_ok=True)
    lab_sum = lab_run.get("summary") or {}
    lab_trades = list(lab_run.get("trades") or [])
    path_sum = (path_run or {}).get("summary") or {}
    path_trades = list((path_run or {}).get("trades") or [])

    # Prefer path-candidate trades on board log when present, else lab
    board_trades = path_trades if path_trades else lab_trades
    trades_path = out_root / "trades.jsonl"
    # Living shadow board trades: tag policy
    tagged = []
    for t in board_trades:
        row = dict(t)
        row["shadow_mode"] = True
        row["live_orders"] = False
        row["policy"] = "path_candidate" if path_trades else "lab_causal_2s"
        tagged.append(row)
    # Also keep lab trades under a side file when both exist
    with trades_path.open("w") as f:
        for t in tagged:
            f.write(json.dumps(jsonable(t)) + "\n")
    if path_trades and lab_trades:
        with (out_root / "trades_lab_causal.jsonl").open("w") as f:
            for t in lab_trades:
                row = dict(t)
                row["policy"] = "lab_causal_2s"
                row["shadow_mode"] = True
                row["live_orders"] = False
                f.write(json.dumps(jsonable(row)) + "\n")
        with (out_root / "trades_path_candidate.jsonl").open("w") as f:
            for t in path_trades:
                row = dict(t)
                row["policy"] = "path_candidate"
                row["shadow_mode"] = True
                row["live_orders"] = False
                f.write(json.dumps(jsonable(row)) + "\n")

    lab_ci = lab_sum.get("lab_pnl_net_bps") or {}
    lab_path_ci = lab_sum.get("path_pnl_net_bps") or {}
    path_lab_ci = path_sum.get("lab_pnl_net_bps") or {}
    path_path_ci = path_sum.get("path_pnl_net_bps") or {}
    kills = lab_sum.get("kills") or {}

    gap_note = "_(gap_summary.json not present yet — lab causal@2s only)_"
    cand_params = path_candidate_overrides(gap)
    if gap is not None:
        decision = gap.get("decision") or gap.get("verdict") or gap.get("kill_decision")
        gap_note = (
            f"decision=`{decision}` · best_params=`{json.dumps(cand_params or {}, separators=(',', ':'))}` · "
            f"path_mean_report=`{gap.get('best_path_mean') or gap.get('path_mean') or '—'}`"
        )

    trade_rows = []
    for t in board_trades[:30]:
        trade_rows.append(
            f"| {t.get('event_i')} | {t.get('side_name')} | {t.get('exit_reason')} | "
            f"{_fmt(t.get('lab_pnl_net_bps'))} | {_fmt(t.get('path_pnl_net_bps'))} |"
        )

    vf_lab = ((lab_sum.get("config") or {}).get("v_fade")) or {}
    vf_path = ((path_sum.get("config") or {}).get("v_fade")) if path_sum else None

    md = f"""# V-fade SHADOW BOARD

Generated: `{datetime.now(timezone.utc).isoformat()}`

> {HONESTY_BANNER}

**Day:** `{day}` · **Venue×symbol:** **{venue} {symbol}** · complete warehouse day (latest available)

Panel context days: `{panel_days or []}`

## Policies run

| policy | confirm_s | exit_s | adverse_stop | n_faded | lab mean | path mean | kill |
|--------|----------:|-------:|-------------:|--------:|---------:|----------:|------|
| lab causal@2s (Promote identity) | {_fmt(vf_lab.get('confirm_s', 2.0))} | {_fmt(vf_lab.get('exit_s', 5.0))} | {_fmt(vf_lab.get('adverse_stop_bps', 12.0))} | {lab_sum.get('n_faded')} | **{_fmt(lab_ci.get('mean'))}** | {_fmt(lab_path_ci.get('mean'))} | {kills.get('decision')} |
| path-optimized candidate | {_fmt((vf_path or {}).get('confirm_s')) if vf_path else '—'} | {_fmt((vf_path or {}).get('exit_s')) if vf_path else '—'} | {_fmt((vf_path or {}).get('adverse_stop_bps')) if vf_path else '—'} | {path_sum.get('n_faded') if path_sum else '—'} | {_fmt(path_lab_ci.get('mean')) if path_sum else '—'} | **{_fmt(path_path_ci.get('mean')) if path_sum else '—'}** | {(path_sum.get('kills') or {}).get('decision') if path_sum else '—'} |

### Lab vs path (lab policy)

- Lab CI: [{_fmt(lab_ci.get('lo'))}, {_fmt(lab_ci.get('hi'))}] n={lab_ci.get('n')}
- Path CI: [{_fmt(lab_path_ci.get('lo'))}, {_fmt(lab_path_ci.get('hi'))}] n={lab_path_ci.get('n')}
- Hit-rate (lab): {_fmt(lab_sum.get('hit_rate_lab'))}

### Gap sibling

{gap_note}

## Trades (board log — `{'path_candidate' if path_trades else 'lab_causal_2s'}`)

| event_i | side | exit | lab_net | path_net |
|---------|------|------|---------|----------|
{chr(10).join(trade_rows) if trade_rows else '| — | — | — | — | — |'}

Artifacts:
- `trades.jsonl` (living board log)
- `{lab_run.get('out_dir')}/RISK_REPORT.md` (lab policy day dir)
{f"- `{path_run.get('out_dir')}/RISK_REPORT.md` (path candidate day dir)" if path_run else ""}

## Honesty

`{json.dumps(honesty_dict(path_policy='lab_and_path_candidate' if path_run else 'lab_causal_2s'), separators=(',', ':'))}`

No live order routing. ClickHouse MCP banned. Do not equate path PnL with lab Promote.
"""
    board = out_root / "SHADOW_BOARD.md"
    board.write_text(md)

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "day": day,
        "venue": venue,
        "symbol": symbol,
        "panel_days": panel_days,
        "lab": {
            "n_faded": lab_sum.get("n_faded"),
            "lab_pnl_net_bps": lab_ci,
            "path_pnl_net_bps": lab_path_ci,
            "confirm_s": vf_lab.get("confirm_s"),
            "exit_s": vf_lab.get("exit_s"),
            "out_dir": lab_run.get("out_dir"),
            "kills": kills.get("decision"),
        },
        "path_candidate": None
        if not path_sum
        else {
            "n_faded": path_sum.get("n_faded"),
            "lab_pnl_net_bps": path_lab_ci,
            "path_pnl_net_bps": path_path_ci,
            "params": cand_params,
            "out_dir": (path_run or {}).get("out_dir"),
            "kills": (path_sum.get("kills") or {}).get("decision"),
        },
        "gap_summary_present": gap is not None,
        "honesty": honesty_dict(path_policy="lab_and_path_candidate" if path_run else "lab_causal_2s"),
        "shadow_board": str(board),
        "trades_jsonl": str(trades_path),
    }
    (out_root / "shadow_meta.json").write_text(json.dumps(jsonable(meta), indent=2) + "\n")
    return board


def pool_ci(trades: list[dict[str, Any]], key: str, *, seed: int, n_boot: int = 800) -> dict[str, float]:
    arr = np.asarray(
        [t[key] for t in trades if t.get(key) is not None],
        dtype=np.float64,
    )
    arr = arr[np.isfinite(arr)]
    return _boot_mean(arr, seed=seed, n_boot=n_boot)
