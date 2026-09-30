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
        "z_min": "z_min",
        "severity_z_min": "z_min",
        "entry_mode": "entry_mode",
        "suppress_fire_pause": "suppress_fire_pause",
        "always_fade": "always_fade",
    }
    out: dict[str, Any] = {}
    params = block.get("params") if isinstance(block.get("params"), dict) else block
    for src, dst in aliases.items():
        if src not in params:
            continue
        val = params[src]
        if val is None and dst == "adverse_stop_bps":
            out[dst] = 1e9
            continue
        if val is None:
            continue
        if dst == "entry_mode":
            out[dst] = str(val)
            continue
        if dst == "suppress_fire_pause":
            # keep prior_only|all|off strings; bool → prior_only/off
            if isinstance(val, bool):
                out[dst] = "prior_only" if val else "off"
            else:
                out[dst] = str(val)
            continue
        if dst == "always_fade":
            out[dst] = bool(val)
            continue
        try:
            out[dst] = float(val)
        except (TypeError, ValueError):
            continue
    if "always_fade" in params and "always_fade" not in out:
        out["always_fade"] = bool(params["always_fade"])
    if out.get("entry_mode") == "severity_zend":
        out.setdefault("confirm_s", 0.5)
        out.setdefault("z_min", 20.0)
        out.setdefault("suppress_fire_pause", "prior_only")
        out.pop("always_fade", None)  # severity gate replaces always_fade
    elif out.get("always_fade") and "confirm_s" not in out:
        out.setdefault("confirm_s", 0.0)
    elif out.get("confirm_s") is not None and float(out["confirm_s"]) <= 0 and "entry_mode" not in out:
        out.setdefault("always_fade", True)
    return out if out else {}


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
    require_gated_ssm: bool = False,
) -> dict[str, Any]:
    """Walk listing cache newest→oldest until day_completeness.complete.

    If require_gated_ssm, also require detect_day ssm_10_n>0 (skips quiet days
    like 2026-09-30 which can be complete yet ungated).
    """
    _ensure_data_path()
    from _data import ensure_env, load_day_trades  # noqa: WPS433

    ensure_env()
    days = list_warehouse_days(venue)
    if not days:
        raise RuntimeError(f"no warehouse listing days for {venue}")
    probed: list[dict[str, Any]] = []
    detect_day = None
    if require_gated_ssm:
        # Lazy import paper detect via pipeline helper
        from .pipeline import _load_paper_detect  # noqa: WPS433

        detect_day = _load_paper_detect()

    for day in reversed(days[-max(lookback, 1) :]):
        try:
            rec = load_day_trades(venue, symbol, day, quiet=True)
            flags = rec.get("completeness") or {}
            row: dict[str, Any] = {
                "day": day,
                "complete": bool(flags.get("complete")),
                "n": flags.get("n"),
                "coverage": flags.get("coverage"),
                "reasons": flags.get("reasons"),
            }
            if row["complete"] and require_gated_ssm and detect_day is not None:
                cell = detect_day(
                    venue,
                    symbol,
                    day,
                    cfg={"z_star": 6.0, "sigma_m_frac": 1.0, "gate": {"min_dp_pct": 0.10, "min_i_c": 5}},
                    quiet=True,
                )
                ssm = int(cell.get("ssm_10_n") or 0)
                row["ssm_10_n"] = ssm
                if ssm <= 0:
                    row["complete_but_no_gated_ssm"] = True
                    probed.append(row)
                    continue
            probed.append(row)
            if row["complete"]:
                if not quiet:
                    print(
                        f"[shadow] latest complete day={day} n={row['n']} "
                        f"cov={row['coverage']} ssm={row.get('ssm_10_n')}"
                    )
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
    policy_a_name: str = "confirm_r2@2→5 (Hold / path-late)",
    policy_b_name: str = "severity_zend |z|≥20 @0.5s→3s prior_only (Promote_shadow)",
) -> Path:
    """Living SHADOW_BOARD.md — side-by-side confirm@2s vs severity@ts_end."""
    out_root.mkdir(parents=True, exist_ok=True)
    a_sum = lab_run.get("summary") or {}
    a_trades = list(lab_run.get("trades") or [])
    b_sum = (path_run or {}).get("summary") or {}
    b_trades = list((path_run or {}).get("trades") or [])

    a_ci_lab = a_sum.get("lab_pnl_net_bps") or {}
    a_ci_path = a_sum.get("path_pnl_net_bps") or {}
    b_ci_lab = b_sum.get("lab_pnl_net_bps") or {}
    b_ci_path = b_sum.get("path_pnl_net_bps") or {}
    a_kills = a_sum.get("kills") or {}
    b_kills = b_sum.get("kills") or {}

    vf_a = ((a_sum.get("config") or {}).get("v_fade")) or {}
    vf_b = ((b_sum.get("config") or {}).get("v_fade")) or {}

    # Living trades.jsonl = severity (executable candidate) when present
    board_trades = b_trades if b_trades else a_trades
    board_policy = "severity_zend" if b_trades else "confirm_r2"
    trades_path = out_root / "trades.jsonl"
    with trades_path.open("w") as f:
        for t in board_trades:
            row = dict(t)
            row["shadow_mode"] = True
            row["live_orders"] = False
            row["policy"] = board_policy
            f.write(json.dumps(jsonable(row)) + "\n")
    with (out_root / "trades_confirm_r2.jsonl").open("w") as f:
        for t in a_trades:
            row = dict(t)
            row.update(policy="confirm_r2", shadow_mode=True, live_orders=False)
            f.write(json.dumps(jsonable(row)) + "\n")
    if b_trades:
        with (out_root / "trades_severity_zend.jsonl").open("w") as f:
            for t in b_trades:
                row = dict(t)
                row.update(policy="severity_zend", shadow_mode=True, live_orders=False)
                f.write(json.dumps(jsonable(row)) + "\n")

    def _trade_table(trades: list[dict[str, Any]], n: int = 20) -> str:
        rows = []
        for t in trades[:n]:
            rows.append(
                f"| {t.get('event_i')} | {t.get('side_name')} | {t.get('exit_reason')} | "
                f"{_fmt(t.get('z_peak'))} | {_fmt(t.get('lab_pnl_net_bps'))} | "
                f"{_fmt(t.get('path_pnl_net_bps'))} |"
            )
        return "\n".join(rows) if rows else "| — | — | — | — | — | — |"

    gap_best = (gap or {}).get("best_policy") or {}
    gap_base = (gap or {}).get("baseline_confirm_r2") or {}
    decision = (gap or {}).get("decision") or "—"
    scope = (gap or {}).get("promote_scope") or ""

    gap_note = "_(no gap_summary.json)_"
    if gap is not None:
        gap_note = (
            f"**{decision}** · scope=`{scope}` · "
            f"best=severity z≥{_fmt(gap_best.get('z_min'))} "
            f"@{_fmt(gap_best.get('confirm_s'))}s→{_fmt(gap_best.get('exit_s'))}s "
            f"path **{_fmt(gap_best.get('path_mean'))}** "
            f"CI[{_fmt(gap_best.get('path_lo'))}, {_fmt(gap_best.get('path_hi'))}] "
            f"n={gap_best.get('n')} · see PATH_GAP_REPORT.md"
        )

    md = f"""# V-fade SHADOW BOARD

Generated: `{datetime.now(timezone.utc).isoformat()}`

> {HONESTY_BANNER}

**Decision: {decision}** · scope `{scope}` · `live_orders=false`

**Living day:** `{day}` · **{venue} {symbol}** (latest complete w/ gated SSM)  
Panel days: `{panel_days or []}`

## Panel path scoreboard (HL ETH 09-04…10 · RT=4)

| policy | n | path mean | path CI | lab mean | clear? |
|--------|--:|----------:|---------|---------:|:------:|
| confirm_r2 @2→5 (legacy) | {gap_base.get('n') or '—'} | {_fmt(gap_base.get('path_mean'))} | [{_fmt(gap_base.get('path_lo'))}, {_fmt(gap_base.get('path_hi'))}] | {_fmt(gap_base.get('lab_mean'))} | |
| **severity_zend best** z≥{_fmt(gap_best.get('z_min'))} @{_fmt(gap_best.get('confirm_s'))}→{_fmt(gap_best.get('exit_s'))} prior_only | {gap_best.get('n') or '—'} | **{_fmt(gap_best.get('path_mean'))}** | [{_fmt(gap_best.get('path_lo'))}, {_fmt(gap_best.get('path_hi'))}] | {_fmt(gap_best.get('lab_mean'))} | Y |

{gap_note}

## Compose / ENTRY_TIMING

1. Rebound used up by ~**+1s** — confirm_r2@+2s is path-late (Hold on path ≈ −5.7).
2. **Executable default:** `severity_zend` · `|z|≥20` · enter `@+0.5s` · exit `@3s` · `fire_pause=prior_only` · adverse off.
3. No r2 wait for executable path. Lab identity (−mo₅ₛ−RT) still reported separately.

Sources: `ENTRY_TIMING.md` · `PATH_GAP_REPORT.md` · `gap_summary.json`

## Living day side-by-side (`{day}`)

| | **A · {policy_a_name}** | **B · {policy_b_name}** |
|--|--:|--:|
| entry_mode | `{vf_a.get('entry_mode') or a_sum.get('entry_mode') or 'confirm_r2'}` | `{vf_b.get('entry_mode') or b_sum.get('entry_mode') or 'severity_zend'}` |
| confirm_s (delay) | {_fmt(a_sum.get('confirm_s', vf_a.get('confirm_s')))} | {_fmt(b_sum.get('confirm_s', vf_b.get('confirm_s')))} |
| exit_s | {_fmt(a_sum.get('exit_s', vf_a.get('exit_s')))} | {_fmt(b_sum.get('exit_s', vf_b.get('exit_s')))} |
| z_min | — | {_fmt(vf_b.get('z_min', b_sum.get('z_min')))} |
| fire_pause | prior_only | {vf_b.get('suppress_fire_pause') or 'prior_only'} |
| n_faded | {a_sum.get('n_faded')} | {b_sum.get('n_faded') if b_sum else '—'} |
| **lab** mean (−mo₅ₛ−RT) | **{_fmt(a_ci_lab.get('mean'))}** | {_fmt(b_ci_lab.get('mean')) if b_sum else '—'} |
| lab CI | [{_fmt(a_ci_lab.get('lo'))}, {_fmt(a_ci_lab.get('hi'))}] | [{_fmt(b_ci_lab.get('lo'))}, {_fmt(b_ci_lab.get('hi'))}] |
| **path** mean (entry→exit) | {_fmt(a_ci_path.get('mean'))} | **{_fmt(b_ci_path.get('mean')) if b_sum else '—'}** |
| path CI | [{_fmt(a_ci_path.get('lo'))}, {_fmt(a_ci_path.get('hi'))}] | [{_fmt(b_ci_path.get('lo'))}, {_fmt(b_ci_path.get('hi'))}] |
| hit lab / path | {_fmt(a_sum.get('hit_rate_lab'))} / {_fmt(a_sum.get('hit_rate_path'))} | {_fmt(b_sum.get('hit_rate_lab')) if b_sum else '—'} / {_fmt(b_sum.get('hit_rate_path')) if b_sum else '—'} |
| kill | {a_kills.get('decision')} | {b_kills.get('decision') if b_sum else '—'} |

> Panel Promote_shadow is on **path** for severity_zend. Living day is a single-day check — not a re-Promote.

## Trades A — confirm_r2@2→5

| event_i | side | exit | z_peak | lab_net | path_net |
|---------|------|------|--------|---------|----------|
{_trade_table(a_trades)}

## Trades B — severity_zend Promote default

| event_i | side | exit | z_peak | lab_net | path_net |
|---------|------|------|--------|---------|----------|
{_trade_table(b_trades)}

Artifacts:
- `SHADOW_BOARD.md` · `trades.jsonl` (severity living day)
- `trades_confirm_r2.jsonl` · `trades_severity_zend.jsonl`
- `EQUITY.md` · `figs/equity_path_event.png` · `figs/equity_path_calendar.png` · `figs/equity_path_vs_confirm_r2.png`
- `{lab_run.get('out_dir')}/RISK_REPORT.md`
{f"- `{(path_run or {}).get('out_dir')}/RISK_REPORT.md`" if path_run else ""}
- Panel: `RISK_REPORT.md` · `rollup.json` · `PATH_GAP_REPORT.md`

## Path equity curves

See [`EQUITY.md`](EQUITY.md) (panel n from gap best / `build_equity_curves.py`).

![path equity event-time](figs/equity_path_event.png)

![path equity calendar-time](figs/equity_path_calendar.png)

![severity vs confirm_r2](figs/equity_path_vs_confirm_r2.png)

## Living shadow poller (≠ paper_live)

**This board** = directional V-fade taker (`severity_zend`).  
**`ares-paper-live.service`** = crash-risk **kill-ladder** overlay only — different class; do not confuse.

| | V-fade shadow | paper_live |
|--|--|--|
| unit | `ares-vfade-shadow.service` | `ares-paper-live.service` |
| script | `run_v_fade_shadow_live.py --poll` | `run_paper_live.py --poll` |
| log | `logs/v_fade_shadow.log` | `../paper_live/logs/paper_live.log` |
| alpha | causal fade path equity | ladder maker equity scoreboard |
| orders | `live_orders=false` | `live_orders=false` |

```bash
# tail V-fade living shadow
tail -f /home/dev/srv/ares-microstructure/research/books/cross_miniflash/applications/edge_lab/v_fade_paper/logs/v_fade_shadow.log

# status / restart (user systemd)
systemctl --user status ares-vfade-shadow.service
systemctl --user restart ares-vfade-shadow.service
```

Heartbeats log `cum_path_eq_bps`; TRADE lines fire when new fades appear. Defaults: `severity_zend` · `|z|≥20` · `+0.5s→3s` · `prior_only`.

## Honesty

`{json.dumps(honesty_dict(path_policy='confirm_r2_vs_severity_zend_promote'), separators=(',', ':'))}`

research_sim · live_orders=false · lab ≠ path · ClickHouse MCP banned · not live OE.
"""
    board = out_root / "SHADOW_BOARD.md"
    board.write_text(md)

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "day": day,
        "venue": venue,
        "symbol": symbol,
        "panel_days": panel_days,
        "live_orders": False,
        "decision": decision,
        "promote_scope": scope,
        "panel_confirm_r2": {
            "n": gap_base.get("n"),
            "path_mean": gap_base.get("path_mean"),
            "path_lo": gap_base.get("path_lo"),
            "path_hi": gap_base.get("path_hi"),
            "lab_mean": gap_base.get("lab_mean"),
        },
        "panel_severity_best": {
            "n": gap_best.get("n"),
            "path_mean": gap_best.get("path_mean"),
            "path_lo": gap_best.get("path_lo"),
            "path_hi": gap_best.get("path_hi"),
            "lab_mean": gap_best.get("lab_mean"),
            "confirm_s": gap_best.get("confirm_s"),
            "exit_s": gap_best.get("exit_s"),
            "z_min": gap_best.get("z_min"),
            "suppress_fire_pause": gap_best.get("suppress_fire_pause"),
        },
        "confirm_r2": {
            "label": policy_a_name,
            "n_faded": a_sum.get("n_faded"),
            "lab_pnl_net_bps": a_ci_lab,
            "path_pnl_net_bps": a_ci_path,
            "confirm_s": a_sum.get("confirm_s"),
            "exit_s": a_sum.get("exit_s"),
            "entry_mode": "confirm_r2",
            "out_dir": lab_run.get("out_dir"),
            "kills": a_kills.get("decision"),
        },
        "severity_zend": None
        if not b_sum
        else {
            "label": policy_b_name,
            "n_faded": b_sum.get("n_faded"),
            "lab_pnl_net_bps": b_ci_lab,
            "path_pnl_net_bps": b_ci_path,
            "confirm_s": b_sum.get("confirm_s"),
            "exit_s": b_sum.get("exit_s"),
            "z_min": vf_b.get("z_min", b_sum.get("z_min")),
            "entry_mode": "severity_zend",
            "out_dir": (path_run or {}).get("out_dir"),
            "kills": b_kills.get("decision"),
        },
        "honesty": honesty_dict(path_policy="confirm_r2_vs_severity_zend_promote"),
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
