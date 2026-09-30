"""Unit + dry-run tests for paper harness (no live orders)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG))

from harness.actions import write_jsonl  # noqa: E402
from harness.config import load_config  # noqa: E402
from harness.ladder import FIRE_TIERS, event_action_records, tier_action  # noqa: E402


def test_load_config():
    cfg = load_config(PKG / "config.yaml")
    assert cfg["mode"] == "paper"
    assert cfg["venue"] == "hyperliquid"
    assert cfg["symbol"] == "ETH"
    assert cfg["gate"]["min_dp_pct"] == 0.10
    assert cfg["gate"]["min_i_c"] == 5


def test_tier_actions():
    assert tier_action("observe")["pull"] is False
    assert tier_action("halt")["pull"] is True
    assert tier_action("halt")["quote_size_mult"] == 0.0
    a = tier_action("widen", size_mult={"widen": 0.4})
    assert a["quote_size_mult"] == 0.4


def test_event_action_records_shapes():
    cell = {
        "day": "2026-09-04",
        "symbol": "ETH",
        "venue": "hyperliquid",
        "events": {
            "ts_start": np.asarray([1, 2], dtype=np.int64),
            "ts_end": np.asarray([10, 20], dtype=np.int64),
            "z_peak": np.asarray([13.0, 22.0]),
            "dp_pct": np.asarray([0.12, 0.5]),
            "i_c": np.asarray([6, 12]),
            "intensity_60s": np.asarray([1, 5]),
            "direction": np.asarray([-1, -1]),
            "nanex_overlap": np.asarray([False, True]),
            "recovery": np.asarray([0.8, 0.1]),
            "recovery_label": np.asarray(["v_recovery", "continuation"], dtype=object),
            "mo_1s": np.asarray([1.0, 2.0]),
            "mo_5s": np.asarray([3.0, 4.0]),
            "tier": np.asarray(["observe", "halt"], dtype=object),
        },
    }
    recs = event_action_records(cell)
    assert len(recs) == 2
    assert recs[0]["kind"] == "ladder_observe"
    assert recs[1]["kind"] == "ladder_fire"
    assert recs[1]["tier"] in FIRE_TIERS
    assert recs[1]["escalate"] == "nanex_intersect_ssm"
    assert recs[1]["nest_hard_pause"] is True
    assert recs[1]["quote_size_mult"] == 0.0
    assert recs[1]["pull"] is True


def test_nest_hard_forces_zero_on_widen():
    cell = {
        "day": "2026-09-04",
        "symbol": "ETH",
        "venue": "hyperliquid",
        "events": {
            "ts_start": np.asarray([1], dtype=np.int64),
            "ts_end": np.asarray([10], dtype=np.int64),
            "z_peak": np.asarray([13.0]),
            "dp_pct": np.asarray([0.12]),
            "i_c": np.asarray([6]),
            "intensity_60s": np.asarray([2]),
            "direction": np.asarray([-1]),
            "nanex_overlap": np.asarray([True]),
            "recovery": np.asarray([0.5]),
            "recovery_label": np.asarray(["continuation"], dtype=object),
            "mo_1s": np.asarray([1.0]),
            "mo_5s": np.asarray([2.0]),
            "tier": np.asarray(["widen"], dtype=object),
        },
    }
    rec = event_action_records(cell, nest_hard_pause=True)[0]
    assert rec["tier"] == "widen"
    assert rec["quote_size_mult"] == 0.0
    assert rec["action"] == "nest_hard_pause"


def test_risk_gate_effective_mult():
    from harness.risk_stack import (
        RiskGateClock,
        RiskGateStackOverlay,
        build_risk_gate_clock,
        effective_mult_at,
        fire_pause_action_records,
    )

    ns = 1_000_000_000
    ts = np.arange(0, 400, dtype=np.int64) * ns  # 400s of 1Hz prints
    events = {
        "ts_end": [50 * ns],
        "tier": ["widen"],
        "recovery_label": ["continuation"],
        "recovery_1s": [0.1],
        "recovery_2s": [0.1],
        "nanex_overlap": [True],
    }
    clock = build_risk_gate_clock(
        ts, events, ladder_hold_s=60.0, nanex_pull_s=15.0, fire_pause_s=300.0, nest_hard_pause=True
    )
    sm = {"none": 1.0, "observe": 1.0, "widen": 0.5, "size_cap": 0.25, "halt": 0.0}
    # At fire onset: nest_hard and/or fire_pause → 0
    m0, reg0 = effective_mult_at(50, clock, sm)
    assert m0 == 0.0
    assert reg0 in ("fire_pause_5m", "nest_hard_pause")
    # After nest pull expires but still inside 5m fire pause → still 0
    m1, reg1 = effective_mult_at(80, clock, sm)  # +30s
    assert m1 == 0.0
    assert reg1 == "fire_pause_5m"
    # Cold tape before fire
    m2, reg2 = effective_mult_at(10, clock, sm)
    assert m2 == 1.0
    assert reg2 == "none"
    # After 5m pause ends
    m3, _ = effective_mult_at(360, clock, sm)
    assert m3 == 1.0

    overlay = RiskGateStackOverlay(clock=clock, base_size=0.25, size_mult=sm)
    q = overlay.quote(50)
    assert q.pulled is True and q.bid_sz == 0.0

    fps = fire_pause_action_records(
        {"day": "d", "symbol": "ETH", "venue": "hyperliquid", "events": {
            "ts_end": [50 * ns],
            "tier": ["widen"],
            "z_peak": [14.0],
            "intensity_60s": [3],
            "mo_5s": [5.0],
        }},
        fire_pause_s=300.0,
    )
    assert len(fps) == 1 and fps[0]["kind"] == "fire_pause_5m"
    assert fps[0]["quote_size_mult"] == 0.0
    assert isinstance(clock, RiskGateClock)


def test_jsonl_roundtrip(tmp_path: Path):
    path = write_jsonl(tmp_path / "a.jsonl", [{"kind": "x", "v": 1.5}, {"kind": "y", "v": None}])
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["kind"] == "x"


def test_assert_fills_on_tape():
    from harness.shadow_fills import assert_fills_on_tape

    ok = {
        "ts": np.asarray([100, 200, 300], dtype=np.int64),
        "px": np.asarray([10.0, 11.0, 12.0]),
        "fill_i": np.asarray([1], dtype=np.int64),
        "fill_ts": np.asarray([200], dtype=np.int64),
        "fill_px": np.asarray([11.0]),
    }
    assert_fills_on_tape(ok)
    bad = dict(ok)
    bad["fill_px"] = np.asarray([99.0])  # stale touch fantasy
    with pytest.raises(AssertionError, match="trade print"):
        assert_fills_on_tape(bad)


def test_tape_proxy_book_shapes():
    from harness.shadow_fills import _tape_proxy_book

    px = np.asarray([100.0, 101.0, 99.5])
    bid, ask, mid = _tape_proxy_book(px, half_spread_bps=0.5)
    assert bid.shape == px.shape and ask.shape == px.shape
    assert np.all(ask > bid)
    assert np.allclose(mid, px)
    # Desk default: 0 half-spread so prints reach touch (else zero fills)
    bid0, ask0, _ = _tape_proxy_book(px, half_spread_bps=0.0)
    assert np.allclose(bid0, px) and np.allclose(ask0, px)
    assert np.all(px + 1e-12 >= ask0) and np.all(px - 1e-12 <= bid0)


@pytest.mark.slow
def test_dry_run_historical_day():
    """Full pipeline on a Phase-4 complete HL ETH day (warehouse)."""
    from harness.pipeline import run_paper_day

    cfg = load_config(PKG / "config.yaml")
    cfg["require_complete_day"] = True
    cfg["extra_venues"] = []
    out = PKG / "out" / "_pytest"
    r = run_paper_day(
        "2026-09-04",
        cfg=cfg,
        out_root=out,
        quiet=True,
    )
    assert not r.get("skipped")
    summary = r["summary"]
    assert summary["venue"] == "hyperliquid"
    assert summary["symbol"] == "ETH"
    assert summary["ssm_10_n"] is not None and summary["ssm_10_n"] >= 0
    assert Path(r["actions_jsonl"]).is_file()
    assert Path(r["risk_report_md"]).is_file()
    assert Path(r["risk_report_html"]).is_file()
    fills = [
        json.loads(line)
        for line in Path(r["actions_jsonl"]).read_text().splitlines()
        if line and json.loads(line).get("kind") == "shadow_fill"
    ]
    assert isinstance(fills, list)
    figs = list((Path(r["out_dir"]) / "figs").glob("*.png"))
    assert figs, "expected risk-report PNGs"
    sh = summary.get("shadow") or {}
    delta = sh.get("delta_vs_baseline") or {}
    if int(summary.get("n_fire") or 0) > 0:
        assert delta.get("overlay_nullified_in_fire") is False
        assert int(delta.get("delta_fills_in_fire") or 0) != 0 or abs(
            float(delta.get("delta_equity_bps") or 0.0)
        ) > 1e-9
    assert "crash_window_fills.png" in {p.name for p in figs}
