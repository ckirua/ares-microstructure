"""PIM / DCM monitors for cd_me paper_shadow (Hold board, no orders)."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

PKG = Path(__file__).resolve().parents[1]
BOOK = PKG.parents[1]
SCRIPTS = BOOK / "scripts"
WAREHOUSE_SRC = Path(
    os.environ.get("WAREHOUSE_SRC")
    or ((Path(os.environ.get("WAREHOUSE_ROOT") or (Path.home() / "lab" / "lab-n2070" / "warehouse")) / "src"))
)
STARTARB = Path(os.environ.get("ARES_STARTARB") or (Path.home() / "srv" / "ares-startarb"))
ROOT = BOOK.parents[2]

for _p in (str(WAREHOUSE_SRC), str(STARTARB / "src"), str(ROOT), str(SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from ares_micro.flow.cdme import (  # noqa: E402
    align_tob_panel,
    dcm_pc1,
    dcm_proxies,
    elasticity_corr,
    logistic_G,
    pim_from_components,
    realized_vol,
    regime_split_corr,
    tcost_from_spreads,
    vloop_cross_venue,
)
from research.md import asof_join  # noqa: E402

GATE_LABELS = {
    "risk.pim_cross_venue": "Hold",
    "risk.dcm_pc1": "Hold",
    "liq.elasticity_regime": "Hold",
    "info.vloop_tcost_commonality": "Hold",
    "alpha.tob_cross_arb": "Kill",
    "risk.bank_cds_var": "Kill",
}

PIM_ARTIFACT_DIR = BOOK / "out" / "pim_vloop_tcost"


def _hour_arr(hourly: dict[str, Any], key: str, n_h: int) -> np.ndarray:
    raw = hourly.get(key)
    if raw is None:
        return np.full(n_h, np.nan, dtype=np.float64)
    arr = np.asarray([np.nan if x is None else float(x) for x in raw], dtype=np.float64)
    if arr.size == n_h:
        return arr
    out = np.full(n_h, np.nan, dtype=np.float64)
    n = min(arr.size, n_h)
    if n:
        out[:n] = arr[:n]
    return out


def _elasticity_from_artifacts_or_proxy(
    *,
    day: str,
    pim_block: dict[str, Any],
    notional_h: np.ndarray,
    fund: np.ndarray,
    pc1: np.ndarray,
    mark_ts: np.ndarray | None = None,
) -> dict[str, Any]:
    """Prefer out/pim_vloop_tcost hourly PIM×notional; else diagnostic proxy."""
    path = PIM_ARTIFACT_DIR / f"day_{day}.json"
    if path.is_file():
        try:
            blob = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            blob = None
        if blob and blob.get("ok") and blob.get("hourly"):
            h = blob["hourly"]
            hts = np.asarray(h.get("ts") or [], dtype=np.int64)
            n_h = int(hts.size)
            if n_h:
                hpim = _hour_arr(h, "pim", n_h)
                hnot = _hour_arr(h, "notional", n_h)
                if mark_ts is not None and np.asarray(mark_ts).size and np.isfinite(pc1).any():
                    dcm_h = asof_join(hts, np.asarray(mark_ts, dtype=np.int64), pc1)
                else:
                    dcm_h = np.full(n_h, np.nan, dtype=np.float64)
                el = regime_split_corr(hnot, hpim, dcm_h, min_n=5)
                el_all = elasticity_corr(hnot, hpim, min_n=5)
                return {
                    "ok": bool(el_all.get("ok") or el.get("ok")),
                    "all": el_all,
                    "regime": el,
                    "source": "pim_vloop_tcost_hourly",
                    "note": "Hourly PIM×notional from research out/ artifact; min_n=5 exploratory Hold",
                    "gate": "Hold",
                    "gate_id": "liq.elasticity_regime",
                    "pim_mean_ref": pim_block.get("pim_mean"),
                }
    if pim_block.get("ok") and pim_block.get("pim_mean") is not None:
        el = regime_split_corr(notional_h, np.abs(fund), pc1, min_n=8)
        el_all = elasticity_corr(notional_h, np.abs(fund), min_n=8)
        return {
            "ok": bool(el.get("ok")),
            "all": el_all,
            "regime": el,
            "source": "funding_proxy_diagnostic",
            "note": "Fallback: notional vs |funding_proxy| under DCM split (hourly PIM artifact missing/thin)",
            "gate": "Hold",
            "gate_id": "liq.elasticity_regime",
            "pim_mean_ref": pim_block.get("pim_mean"),
        }
    return {
        "ok": False,
        "reason": "no_pim",
        "gate": "Hold",
        "gate_id": "liq.elasticity_regime",
    }


def jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.floating, float)):
        x = float(obj)
        return x if np.isfinite(x) else None
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, np.ndarray):
        return jsonable(obj.tolist())
    return obj


def compute_day_monitors(*, cfg: dict[str, Any], day: str | None = None) -> dict[str, Any]:
    from _data import (
        day_bounds_ns,
        ensure_env,
        funding_proxy_from_marks,
        load_core_venues_day,
        load_cross_venue_marks,
        load_cross_venue_tob,
        trade_volume_buckets,
    )
    from .shadow import find_latest_day

    ensure_env()
    if bool(cfg.get("live_orders")):
        raise RuntimeError("hard refuse: live_orders=True")

    venue = str(cfg.get("venue") or "hyperliquid").lower()
    symbol = str(cfg.get("symbol") or "ETH").upper()
    lookback = int(cfg.get("lookback_days") or 21)
    max_files = int(cfg.get("max_files") or 48)
    dt_s = float(cfg.get("dt_s") or 5.0)
    max_lag_s = float(cfg.get("max_lag_s") or 30.0)
    bucket_s = float(cfg.get("bucket_s") or 3600.0)
    prefer_complete = bool(cfg.get("require_complete_day", False))

    found = None
    if day is None:
        found = find_latest_day(
            venue,
            symbol,
            lookback=lookback,
            prefer_complete=prefer_complete,
            quiet=True,
            max_files=max_files,
        )
        day = str(found["day"])

    assert day is not None
    tob_pack = load_cross_venue_tob(symbol, day)
    venues_tob = tob_pack.get("venues") or {}
    trades = load_core_venues_day(symbol, day, quiet=True)
    marks = load_cross_venue_marks(symbol, day, quiet=True)

    pim_block: dict[str, Any] = {"ok": False}
    if len(venues_tob) >= 2:
        lo, hi = day_bounds_ns(day)
        panel = align_tob_panel(
            venues_tob,
            dt_s=dt_s,
            max_lag_s=max_lag_s,
            day_start_ns=lo,
            day_end_ns=hi,
        )
        vl = vloop_cross_venue(panel["mid"])
        hs_list = [panel["half_spread"][v] for v in panel["venues"] if v in panel["half_spread"]]
        tcost = tcost_from_spreads(hs_list)
        vloop = vl["vloop_max"]
        pim = pim_from_components(vloop, tcost)
        common = np.isfinite(vloop) & np.isfinite(tcost)
        corr_vt = (
            float(np.corrcoef(vloop[common], tcost[common])[0, 1])
            if int(common.sum()) >= 20
            else float("nan")
        )
        finite = pim[np.isfinite(pim)]
        pim_block = {
            "ok": True,
            "venues_tob": list(panel["venues"]),
            "coverage": panel.get("coverage"),
            "n_grid": panel["n"],
            "n_finite_pim": int(finite.size),
            "pim_mean": float(np.mean(finite)) if finite.size else None,
            "pim_p50": float(np.median(finite)) if finite.size else None,
            "pim_p90": float(np.percentile(finite, 90)) if finite.size else None,
            "vloop_mean": float(np.nanmean(vloop)) if np.isfinite(vloop).any() else None,
            "tcost_mean": float(np.nanmean(tcost)) if np.isfinite(tcost).any() else None,
            "corr_vloop_tcost": corr_vt if np.isfinite(corr_vt) else None,
            "gate": "Hold",
            "gate_id": "risk.pim_cross_venue",
            "label": "Monitor",
        }
    else:
        pim_block = {
            "ok": False,
            "reason": "need_ge_2_venue_tob",
            "tob_errors": tob_pack.get("errors"),
            "n_venues_tob": len(venues_tob),
            "gate": "Hold",
            "gate_id": "risk.pim_cross_venue",
        }

    # DCM from marks
    dcm_block: dict[str, Any] = {"ok": False}
    mark_venues = marks.get("venues") or {}
    home = None
    home_name = None
    for cand in (venue, "deribit", "kraken", "hyperliquid"):
        rec = mark_venues.get(cand)
        if isinstance(rec, dict) and rec.get("n", 0) >= 15 and "error" not in rec:
            home = rec
            home_name = cand
            break
    el_block: dict[str, Any] = {"ok": False}
    if home is not None:
        h_ts = np.asarray(home["ts"], dtype=np.int64)
        h_mid = np.asarray(home["mid"], dtype=np.float64)
        log_px = np.log(np.clip(h_mid, 1e-12, None))
        rv = realized_vol(log_px, window=30)
        fund = funding_proxy_from_marks(h_mid, h_ts, window=30)["funding_proxy"]
        basis = np.full(h_mid.shape, np.nan, dtype=np.float64)
        for bv in ("deribit", "kraken"):
            if bv == home_name:
                continue
            rec = mark_venues.get(bv)
            if not isinstance(rec, dict) or rec.get("n", 0) < 10 or "error" in rec:
                continue
            far = asof_join(
                h_ts,
                np.asarray(rec["ts"], dtype=np.int64),
                np.asarray(rec["mid"], dtype=np.float64),
            )
            ok = np.isfinite(far) & (far > 0) & np.isfinite(h_mid) & (h_mid > 0)
            basis[ok] = np.log(far[ok] / h_mid[ok])
            break
        # imbalance from home trades
        imb = np.full(h_mid.shape, np.nan, dtype=np.float64)
        notional_h = np.full(h_mid.shape, np.nan, dtype=np.float64)
        home_trade = (trades.get("venues") or {}).get(home_name or venue)
        if isinstance(home_trade, dict) and "tape" in home_trade:
            vb = trade_volume_buckets(home_trade["tape"], bucket_s=bucket_s, day=day)
            if vb["ts"].size:
                imb = asof_join(h_ts, vb["ts"], vb["imbalance"])
                notional_h = asof_join(h_ts, vb["ts"], vb["notional"])
        prox_kwargs: dict[str, Any] = {}
        if np.isfinite(fund).any():
            prox_kwargs["funding"] = fund
        if np.isfinite(basis).any():
            prox_kwargs["basis"] = basis
        if np.isfinite(rv).any():
            prox_kwargs["rv"] = rv
        if np.isfinite(imb).any():
            prox_kwargs["imbalance"] = imb
        prox = dcm_proxies(**prox_kwargs)
        pc = dcm_pc1(prox)
        G = logistic_G(pc["pc1"])
        dcm_block = {
            "ok": True,
            "home_venue": home_name,
            "n_marks": int(h_mid.size),
            "keys": pc.get("keys"),
            "loadings": pc.get("loadings"),
            "explained_var": pc.get("explained_var"),
            "n_valid": pc.get("n_valid"),
            "pc1_mean": float(np.nanmean(pc["pc1"])) if np.isfinite(pc["pc1"]).any() else None,
            "G_mean": float(np.nanmean(G)) if np.isfinite(G).any() else None,
            "constrained_flag": bool(
                np.isfinite(pc["pc1"]).any()
                and float(np.nanmean(pc["pc1"][-min(30, pc["pc1"].size) :]))
                > float(np.nanpercentile(pc["pc1"][np.isfinite(pc["pc1"])], 75))
            )
            if int(np.isfinite(pc["pc1"]).sum()) >= 10
            else False,
            "gate": "Hold",
            "gate_id": "risk.dcm_pc1",
            "label": "Monitor",
        }
        # Prefer research-panel hourly PIM×notional from out/pim_vloop_tcost when present;
        # else fall back to notional vs |funding_proxy| under DCM split (diagnostic only).
        el_block = _elasticity_from_artifacts_or_proxy(
            day=day,
            pim_block=pim_block,
            notional_h=notional_h,
            fund=fund,
            pc1=pc["pc1"],
            mark_ts=h_ts,
        )
    else:
        dcm_block = {
            "ok": False,
            "reason": "no_mark_bars",
            "gate": "Hold",
            "gate_id": "risk.dcm_pc1",
        }
        el_block = {"ok": False, "reason": "no_marks", "gate": "Hold", "gate_id": "liq.elasticity_regime"}

    gates = dict(cfg.get("gates") or GATE_LABELS)
    return {
        "ok": True,
        "day": day,
        "venue": venue,
        "symbol": symbol,
        "pim": pim_block,
        "dcm": dcm_block,
        "elasticity": el_block,
        "tob_errors": tob_pack.get("errors"),
        "trades_n_complete": trades.get("n_complete"),
        "gates": gates,
        "found": (
            {k: found[k] for k in ("day", "completeness", "probed") if found and k in found}
            if found
            else None
        ),
        "live_orders": False,
        "alpha_claim": False,
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "honesty": "Monitor/Hold only — never sized arb; Kill TOB-cross α and CDS vanity",
    }
