"""Orchestrate detect → causal V-fade → report for one day or panel."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .causal import write_jsonl
from .config import load_config
from .kill import _boot_mean, evaluate_kills
from .report import save_summary_json, summarize, write_figs, write_markdown, write_panel_markdown
from .shadow import honesty_dict
from .strategy import simulate_day_fades

PKG = Path(__file__).resolve().parents[1]
PAPER_HARNESS = PKG.parents[1] / "paper_harness"

_detect_day_fn: Callable[..., dict[str, Any]] | None = None


def _load_paper_detect() -> Callable[..., dict[str, Any]]:
    """Import paper_harness.harness.detect without colliding with this package's `harness`."""
    global _detect_day_fn
    if _detect_day_fn is not None:
        return _detect_day_fn

    detect_path = PAPER_HARNESS / "harness" / "detect.py"
    if not detect_path.is_file():
        raise FileNotFoundError(f"paper_harness detect missing: {detect_path}")

    # paper_harness detect inserts its own paths; ensure package root is importable
    ph = str(PAPER_HARNESS)
    if ph not in sys.path:
        sys.path.append(ph)

    spec = importlib.util.spec_from_file_location(
        "paper_harness_detect_vfade",
        detect_path,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {detect_path}")
    mod = importlib.util.module_from_spec(spec)
    # Register before exec so dataclass/relative-free module can self-ref if needed
    sys.modules["paper_harness_detect_vfade"] = mod
    spec.loader.exec_module(mod)
    fn = getattr(mod, "detect_day", None)
    if fn is None:
        raise ImportError("paper_harness detect_day not found")
    _detect_day_fn = fn
    return fn


def _day_out(root: Path, day: str, venue: str, symbol: str) -> Path:
    return root / f"{day}_{venue}_{symbol}"


def _detect_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    """Subset of config consumed by paper_harness.detect_day."""
    return {
        "z_star": cfg.get("z_star", 6.0),
        "sigma_m_frac": cfg.get("sigma_m_frac", 1.0),
        "gate": cfg.get("gate") or {"min_dp_pct": 0.10, "min_i_c": 5},
        "intensity_window_s": cfg.get("intensity_window_s", 60.0),
        "nanex_slack_s": cfg.get("nanex_slack_s", 0.5),
    }


def run_v_fade_day(
    day: str,
    *,
    config: str | Path | None = None,
    cfg: dict[str, Any] | None = None,
    out_root: str | Path | None = None,
    venue: str | None = None,
    symbol: str | None = None,
    quiet: bool = False,
) -> dict[str, Any]:
    """One UTC day: warehouse tape → SSM detect → causal fade → artifacts."""
    cfg = dict(cfg or load_config(config))
    if cfg.get("live_orders"):
        raise RuntimeError("K8 hard refuse: live_orders=True is not allowed in v_fade_paper")

    venue = (venue or cfg.get("venue") or "hyperliquid").lower()
    symbol = (symbol or cfg.get("symbol") or "ETH").upper()
    root = Path(out_root) if out_root else PKG / str(cfg.get("out_dir") or "out")
    day_dir = _day_out(root, day, venue, symbol)
    day_dir.mkdir(parents=True, exist_ok=True)

    if not quiet:
        print(f"[v_fade_paper] day={day} venue={venue} symbol={symbol} out={day_dir}")

    detect_day = _load_paper_detect()
    dcfg = _detect_cfg(cfg)
    cell = detect_day(venue, symbol, day, cfg=dcfg, quiet=quiet)

    if cell.get("skip"):
        summary = {
            "day": day,
            "venue": venue,
            "symbol": symbol,
            "skip": cell["skip"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "honesty": honesty_dict(),
        }
        save_summary_json(summary, day_dir / "summary.json")
        return {"summary": summary, "out_dir": str(day_dir), "skipped": True, "trades": []}

    if cfg.get("require_complete_day", True) and not cell.get("complete"):
        reasons = (cell.get("completeness") or {}).get("reasons")
        raise RuntimeError(
            f"day {day} {venue} {symbol} incomplete (completeness={reasons}); "
            "pass --allow-incomplete to override"
        )

    sim = simulate_day_fades(cell, cfg=cfg)
    kills = evaluate_kills(
        sim["trades"],
        cfg=cfg,
        live_orders=False,
        sigma_m_floor_hit=cell.get("sigma_m_floor_hit"),
        detector_skip=False,
    )
    summary = summarize(cell, sim, cfg=cfg, kills=kills)

    session = [
        {
            "kind": "session_start",
            "day": day,
            "venue": venue,
            "symbol": symbol,
            "mode": "paper",
            "class": "directional_v_fade",
            "strategy": "causal_fade_v_only",
            "live_orders": False,
            "shadow_paper": True,
            "n_gated": cell.get("ssm_10_n"),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    ]
    all_actions = session + list(sim.get("actions") or [])
    all_actions.append(
        {
            "kind": "session_end",
            "day": day,
            "venue": venue,
            "symbol": symbol,
            "n_faded": sim.get("n_faded"),
            "kills_decision": kills.get("decision"),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    )
    actions_path = day_dir / "actions.jsonl"
    write_jsonl(actions_path, all_actions)
    trades_path = day_dir / "trades.jsonl"
    write_jsonl(trades_path, sim.get("trades") or [])

    fig_paths = write_figs(cell, sim, day_dir, day=day, venue=venue, symbol=symbol)
    summary["figures"] = fig_paths
    summary["actions_jsonl"] = str(actions_path)
    summary["trades_jsonl"] = str(trades_path)

    # Extra venues: full fade sim when easy (same day/symbol)
    extras = []
    for v in cfg.get("extra_venues") or []:
        if v == venue:
            continue
        try:
            extra_cell = detect_day(v, symbol, day, cfg=dcfg, quiet=True)
            if extra_cell.get("skip"):
                extras.append({"venue": v, "skip": extra_cell["skip"]})
                continue
            if cfg.get("require_complete_day", True) and not extra_cell.get("complete"):
                extras.append({"venue": v, "skip": "incomplete_day"})
                continue
            extra_sim = simulate_day_fades(extra_cell, cfg=cfg)
            extra_dir = _day_out(root, day, v, symbol)
            extra_dir.mkdir(parents=True, exist_ok=True)
            write_jsonl(extra_dir / "trades.jsonl", extra_sim.get("trades") or [])
            write_jsonl(extra_dir / "actions.jsonl", extra_sim.get("actions") or [])
            ek = evaluate_kills(extra_sim["trades"], cfg=cfg, live_orders=False)
            es = summarize(extra_cell, extra_sim, cfg=cfg, kills=ek)
            ef = write_figs(extra_cell, extra_sim, extra_dir, day=day, venue=v, symbol=symbol)
            es["figures"] = ef
            write_markdown(es, ef, extra_sim.get("trades") or [], extra_dir / "RISK_REPORT.md")
            save_summary_json(es, extra_dir / "summary.json")
            extras.append(
                {
                    "venue": v,
                    "ssm_10_n": extra_cell.get("ssm_10_n"),
                    "n_faded": extra_sim.get("n_faded"),
                    "lab_mean": (es.get("lab_pnl_net_bps") or {}).get("mean"),
                    "out_dir": str(extra_dir),
                }
            )
        except Exception as exc:  # noqa: BLE001
            extras.append({"venue": v, "error": f"{type(exc).__name__}: {exc}"})
    if extras:
        summary["extra_venues"] = extras

    md_path = write_markdown(summary, fig_paths, sim.get("trades") or [], day_dir / "RISK_REPORT.md")
    json_path = save_summary_json(summary, day_dir / "summary.json")

    if not quiet:
        lab = summary.get("lab_pnl_net_bps") or {}
        print(
            f"[v_fade_paper] faded={summary.get('n_faded')} "
            f"lab_mean={lab.get('mean')} kill={kills.get('decision')} → {md_path}"
        )

    return {
        "summary": summary,
        "out_dir": str(day_dir),
        "risk_report_md": str(md_path),
        "summary_json": str(json_path),
        "trades": sim.get("trades") or [],
        "kills": kills,
        "skipped": False,
    }


def run_v_fade_panel(
    days: list[str],
    *,
    config: str | Path | None = None,
    cfg: dict[str, Any] | None = None,
    out_root: str | Path | None = None,
    quiet: bool = False,
) -> dict[str, Any]:
    """Multi-day panel with bootstrap CIs + kill flags on pooled fades."""
    cfg = dict(cfg or load_config(config))
    root = Path(out_root) if out_root else PKG / str(cfg.get("out_dir") or "out")
    venue = cfg.get("venue") or "hyperliquid"
    symbol = cfg.get("symbol") or "ETH"

    results = []
    all_trades: list[dict[str, Any]] = []
    for day in days:
        try:
            r = run_v_fade_day(day, cfg=cfg, out_root=root, quiet=quiet)
            s = r.get("summary") or {}
            if r.get("skipped"):
                results.append(
                    {
                        "day": day,
                        "ok": False,
                        "skipped": True,
                        "skip": s.get("skip"),
                        "out_dir": r.get("out_dir"),
                    }
                )
                continue
            trades = r.get("trades") or []
            all_trades.extend(trades)
            results.append(
                {
                    "day": day,
                    "ok": True,
                    "out_dir": r.get("out_dir"),
                    "risk_report_md": r.get("risk_report_md"),
                    "n_faded": s.get("n_faded"),
                    "ssm_10_n": s.get("ssm_10_n"),
                    "lab_pnl_net_bps": s.get("lab_pnl_net_bps"),
                    "path_pnl_net_bps": s.get("path_pnl_net_bps"),
                    "hit_rate_lab": s.get("hit_rate_lab"),
                    "kills_decision": (r.get("kills") or {}).get("decision"),
                    "extra_venues": s.get("extra_venues"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            results.append({"day": day, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
            if not quiet:
                print(f"[v_fade_paper] FAIL {day}: {exc}", file=sys.stderr)

    vf = dict(cfg.get("v_fade") or {})
    early = set(vf.get("early_days") or [])
    late = set(vf.get("late_days") or [])
    n_boot = int(vf.get("n_boot", 800))

    lab = np.asarray(
        [t["lab_pnl_net_bps"] for t in all_trades if t.get("lab_pnl_net_bps") is not None],
        dtype=np.float64,
    )
    lab = lab[np.isfinite(lab)]
    path = np.asarray(
        [t["path_pnl_net_bps"] for t in all_trades if t.get("path_pnl_net_bps") is not None],
        dtype=np.float64,
    )
    path = path[np.isfinite(path)]
    lab_ci = _boot_mean(lab, seed=101, n_boot=n_boot)
    path_ci = _boot_mean(path, seed=102, n_boot=n_boot)

    e_pnls = np.asarray(
        [
            float(t["lab_pnl_net_bps"])
            for t in all_trades
            if t.get("day") in early and t.get("lab_pnl_net_bps") is not None
        ],
        dtype=np.float64,
    )
    l_pnls = np.asarray(
        [
            float(t["lab_pnl_net_bps"])
            for t in all_trades
            if t.get("day") in late and t.get("lab_pnl_net_bps") is not None
        ],
        dtype=np.float64,
    )
    e_pnls = e_pnls[np.isfinite(e_pnls)]
    l_pnls = l_pnls[np.isfinite(l_pnls)]
    early_mean = float(np.mean(e_pnls)) if e_pnls.size else float("nan")
    late_mean = float(np.mean(l_pnls)) if l_pnls.size else float("nan")
    hit = float(np.mean(lab > 0)) if lab.size else float("nan")

    kills = evaluate_kills(
        all_trades,
        cfg=cfg,
        early_days=early,
        late_days=late,
        live_orders=bool(cfg.get("live_orders", False)),
    )

    # Panel equity + figs
    fig_dir = root / "figs"
    fig_dir.mkdir(parents=True, exist_ok=True)
    panel_figs = _write_panel_figs(all_trades, fig_dir, venue=venue, symbol=symbol)

    rollup = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days": days,
        "venue": venue,
        "symbol": symbol,
        "extra_venues": cfg.get("extra_venues") or [],
        "results": results,
        "n_ok": sum(1 for r in results if r.get("ok")),
        "n_faded": len(all_trades),
        "lab_pnl_net_bps": lab_ci,
        "path_pnl_net_bps": path_ci,
        "early_mean": early_mean,
        "late_mean": late_mean,
        "early_n": int(e_pnls.size),
        "late_n": int(l_pnls.size),
        "hit_rate": hit,
        "kills": kills,
        "figures": panel_figs,
        "mode": "SHADOW_PAPER",
        "live_orders": False,
        "confirm_s": vf.get("confirm_s"),
        "exit_s": vf.get("exit_s"),
        "config": {"v_fade": vf, "live_orders": False, "mode": "SHADOW_PAPER"},
        "honesty": honesty_dict(),
    }
    rollup_path = root / "rollup.json"
    save_summary_json(rollup, rollup_path)
    md_path = write_panel_markdown(rollup, root / "RISK_ROLLUP.md")
    # Also primary RISK_REPORT at panel root
    write_panel_markdown(rollup, root / "RISK_REPORT.md")
    write_jsonl(root / "trades.jsonl", all_trades)

    if not quiet:
        print(
            f"[v_fade_paper] panel n_faded={len(all_trades)} "
            f"lab_mean={lab_ci.get('mean')} kill={kills.get('decision')} → {md_path}"
        )
    return rollup


def _write_panel_figs(
    trades: list[dict[str, Any]],
    fig_dir: Path,
    *,
    venue: str,
    symbol: str,
) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    paths: list[str] = []
    if not trades:
        return paths

    # Sort by day then entry
    ordered = sorted(trades, key=lambda t: (str(t.get("day")), int(t.get("entry_ts") or 0)))
    lab = [float(t["lab_pnl_net_bps"]) for t in ordered if t.get("lab_pnl_net_bps") is not None]
    days = [str(t.get("day")) for t in ordered if t.get("lab_pnl_net_bps") is not None]

    fig, ax = plt.subplots(figsize=(11, 3.8))
    if lab:
        eq = np.cumsum(lab)
        ax.plot(np.arange(1, len(eq) + 1), eq, color="#1a5276", lw=1.3)
        ax.axhline(0, color="#7f8c8d", lw=0.8, ls="--")
        # day separators
        prev = None
        for i, d in enumerate(days):
            if d != prev:
                ax.axvline(i + 1, color="#ecf0f1", lw=0.8)
                prev = d
    ax.set_title(f"Panel equity — {venue} {symbol} causal V-fade (lab −mo5s−RT4)")
    ax.set_xlabel("fade #")
    ax.set_ylabel("cum net bps")
    p = fig_dir / "panel_equity_lab.png"
    fig.tight_layout()
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p))

    # Per-day means
    by_day: dict[str, list[float]] = {}
    for t in ordered:
        if t.get("lab_pnl_net_bps") is None:
            continue
        by_day.setdefault(str(t["day"]), []).append(float(t["lab_pnl_net_bps"]))
    fig, ax = plt.subplots(figsize=(10, 3.6))
    ds = sorted(by_day.keys())
    means = [float(np.mean(by_day[d])) for d in ds]
    ns = [len(by_day[d]) for d in ds]
    colors = ["#27ae60" if m > 0 else "#c0392b" for m in means]
    ax.bar(ds, means, color=colors, alpha=0.85)
    for i, (m, n) in enumerate(zip(means, ns)):
        ax.text(i, m, f"n={n}", ha="center", va="bottom" if m >= 0 else "top", fontsize=7)
    ax.axhline(0, color="#7f8c8d", lw=0.8)
    ax.set_title(f"Per-day mean lab net bps — {venue} {symbol}")
    ax.tick_params(axis="x", rotation=30)
    p = fig_dir / "panel_daily_means.png"
    fig.tight_layout()
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    paths.append(str(p))

    return paths
