"""GEX / VEX / squeeze / implied-book scarcity monitors (Hold board, no orders).

Honesty
-------
- All research gates pinned **Hold** (or Kill for TOB-cross α).
- Wire **Promote only** — Promote count expected **0** until Pass 2.
- Never soft-Promote TOB-cross as α. live_orders=False always.
- Imports `research.lib.squeeze` when present; does not own/edit that module.
- ClickHouse MCP banned.
"""

from __future__ import annotations

import importlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

PKG = Path(__file__).resolve().parents[1]
BOOK = PKG.parents[1]
SCRIPTS = BOOK / "scripts"
LIB_SQUEEZE = BOOK.parents[2] / "research" / "lib" / "squeeze.py"
WAREHOUSE_SRC = Path(
    os.environ.get("WAREHOUSE_SRC")
    or ((Path(os.environ.get("WAREHOUSE_ROOT") or (Path.home() / "lab" / "lab-n2070" / "warehouse")) / "src"))
)
STARTARB = Path(os.environ.get("ARES_STARTARB") or (Path.home() / "srv" / "ares-startarb"))
ROOT = BOOK.parents[2]

for _p in (str(WAREHOUSE_SRC), str(STARTARB / "src"), str(ROOT), str(SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

GATE_LABELS = {
    "risk.gex_exposure": "Hold",
    "risk.vex_exposure": "Hold",
    "risk.squeeze_intensity": "Hold",
    "liq.implied_book_scarcity": "Hold",
    "alpha.tob_cross_arb": "Kill",
}

# Pass-1 day packs live under gex_implied_book (not a synthetic squeeze_metrics/ folder).
ARTIFACT_DIR = BOOK / "out" / "gex_implied_book"
ARTIFACT_FALLBACKS = (
    BOOK / "out" / "gex_implied_book",
    BOOK / "out" / "squeeze_regimes",
    BOOK / "out" / "vex_vanna",
)


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


def promote_only(gates: dict[str, Any] | None) -> list[str]:
    """Surface gate IDs labeled Promote. Expect empty until Pass 2."""
    out: list[str] = []
    for gid, label in (gates or {}).items():
        if str(label).strip().lower() == "promote":
            out.append(str(gid))
    return out


def squeeze_lib_status() -> dict[str, Any]:
    path = LIB_SQUEEZE
    if not path.is_file():
        return {
            "ok": False,
            "reason": "missing_lib_squeeze",
            "path": str(path),
            "note": "research/lib/squeeze.py not present — owned by sibling agent; import when ready",
        }
    try:
        mod = importlib.import_module("research.lib.squeeze")
        return {
            "ok": True,
            "path": str(path),
            "exports": sorted(
                n
                for n in dir(mod)
                if not n.startswith("_") and callable(getattr(mod, n, None))
            )[:40],
            "module": mod,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "reason": "lib_squeeze_import_failed",
            "path": str(path),
            "error": f"{type(exc).__name__}: {exc}",
        }


def _hold_block(gate_id: str, *, reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "ok": False,
        "reason": reason,
        "gate": "Hold",
        "gate_id": gate_id,
        "label": "Monitor",
        **extra,
    }


def _call_lib(mod: Any, names: tuple[str, ...], *args: Any, **kwargs: Any) -> Any:
    for name in names:
        fn = getattr(mod, name, None)
        if callable(fn):
            return fn(*args, **kwargs)
    return None


def _compute_from_lib(
    *,
    mod: Any,
    day: str,
    venue: str,
    symbol: str,
    cfg: dict[str, Any],
    tape: dict[str, Any] | None,
) -> dict[str, Any]:
    """Best-effort call into research.lib.squeeze when API is available."""
    gex = _call_lib(mod, ("gex_day", "compute_gex", "gex"), day=day, venue=venue, symbol=symbol, cfg=cfg, tape=tape)
    if gex is None and tape is not None:
        gex = _call_lib(mod, ("gex_from_tape", "gex_panel"), tape)
    vex = _call_lib(mod, ("vex_day", "compute_vex", "vex"), day=day, venue=venue, symbol=symbol, cfg=cfg, tape=tape)
    if vex is None and tape is not None:
        vex = _call_lib(mod, ("vex_from_tape", "vex_panel"), tape)
    squeeze = _call_lib(
        mod,
        ("squeeze_intensity", "compute_squeeze", "gex_plus", "gex_plus_day"),
        day=day,
        venue=venue,
        symbol=symbol,
        cfg=cfg,
        tape=tape,
        gex=gex,
        vex=vex,
    )
    scarcity = _call_lib(
        mod,
        ("implied_book_scarcity", "liquidity_scarcity", "compute_scarcity"),
        day=day,
        venue=venue,
        symbol=symbol,
        cfg=cfg,
        tape=tape,
        gex=gex,
        vex=vex,
        squeeze=squeeze,
    )

    def _normalize(block: Any, gate_id: str, default_reason: str) -> dict[str, Any]:
        if block is None:
            return _hold_block(gate_id, reason=default_reason)
        if isinstance(block, dict):
            out = dict(block)
            out.setdefault("ok", True)
            out.setdefault("gate", "Hold")
            out.setdefault("gate_id", gate_id)
            out.setdefault("label", "Monitor")
            # Never allow lib to soft-Promote
            if str(out.get("gate")).lower() == "promote":
                out["gate"] = "Hold"
                out["promote_suppressed"] = True
            return out
        try:
            val = float(block)
        except (TypeError, ValueError):
            return _hold_block(gate_id, reason="non_numeric_lib_result", raw=str(block)[:200])
        return {
            "ok": np.isfinite(val),
            "value": val if np.isfinite(val) else None,
            "gate": "Hold",
            "gate_id": gate_id,
            "label": "Monitor",
        }

    return {
        "gex": _normalize(gex, "risk.gex_exposure", "lib_no_gex_export"),
        "vex": _normalize(vex, "risk.vex_exposure", "lib_no_vex_export"),
        "squeeze": _normalize(squeeze, "risk.squeeze_intensity", "lib_no_squeeze_export"),
        "scarcity": _normalize(scarcity, "liq.implied_book_scarcity", "lib_no_scarcity_export"),
        "source": "research.lib.squeeze",
    }


def _artifact_fallback(day: str) -> dict[str, Any] | None:
    import json

    path = None
    blob: dict[str, Any] | None = None
    for root in ARTIFACT_FALLBACKS:
        cand = root / f"day_{day}.json"
        if not cand.is_file():
            continue
        try:
            blob = json.loads(cand.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if blob:
            path = cand
            break
    if not blob or path is None:
        return None
    gex = blob.get("gex_mean", blob.get("gex"))
    vex = blob.get("vex_mean", blob.get("vex"))
    intensity = blob.get("squeeze_intensity", blob.get("gex_plus"))
    scarce = blob.get("scarce", blob.get("scarcity", blob.get("implied_book_scarcity")))
    ok = bool(blob.get("ok", True))
    return {
        "gex": {
            "ok": ok and gex is not None,
            "gex_mean": gex,
            "value": gex,
            "gate": "Hold",
            "gate_id": "risk.gex_exposure",
            "label": "Monitor",
            "ddoi_mode": blob.get("ddoi_mode"),
            "source": f"artifact:{path.parent.name}",
        },
        "vex": {
            "ok": ok and vex is not None,
            "vex_mean": vex,
            "value": vex,
            "gate": "Hold",
            "gate_id": "risk.vex_exposure",
            "label": "Monitor",
            "source": f"artifact:{path.parent.name}",
        },
        "squeeze": {
            "ok": ok and intensity is not None,
            "intensity": intensity,
            "value": intensity,
            "gate": "Hold",
            "gate_id": "risk.squeeze_intensity",
            "label": "Monitor",
            "source": f"artifact:{path.parent.name}",
        },
        "scarcity": {
            "ok": ok and scarce is not None,
            "scarcity": scarce,
            "value": scarce,
            "gate": "Hold",
            "gate_id": "liq.implied_book_scarcity",
            "label": "Monitor",
            "source": f"artifact:{path.parent.name}",
        },
        "source": "artifact",
        "artifact_path": str(path),
        "honesty": blob.get("honesty"),
    }


def _lib_results_usable(computed: dict[str, Any] | None) -> bool:
    if not computed:
        return False
    for key in ("gex", "vex", "squeeze", "scarcity"):
        block = computed.get(key) or {}
        if block.get("ok"):
            return True
    return False


def _compute_from_loaders(*, day: str, symbol: str) -> dict[str, Any] | None:
    """Recompute GEX/VEX via book loaders + squeeze.chain_exposures (Pass-1 parity)."""
    try:
        from _data import (
            ensure_env,
            load_day_marks,
            load_eth_option_iv_day,
            load_eth_option_trades_day,
        )
        from research.lib.squeeze import (
            LABEL_TRADE_DDOI,
            LABEL_UNIT_OI,
            accumulate_ddoi_by_instrument,
            chain_exposures,
            ddoi_from_trade_flow,
            scarcity_flag,
            squeeze_intensity,
            unsigned_unit_ddoi,
        )
    except Exception:
        return None

    ensure_env()
    iv = load_eth_option_iv_day(day, underlying=symbol)
    if not iv.get("ok"):
        return None
    marks = load_day_marks("deribit", symbol, day)
    mid = np.asarray(marks.get("mid") if marks.get("mid") is not None else marks.get("price"), dtype=np.float64)
    mid = mid[np.isfinite(mid) & (mid > 0)]
    if mid.size == 0:
        return None
    spot = float(np.nanmedian(mid))
    ddoi = unsigned_unit_ddoi(int(iv["n"]), sign=1.0)
    ddoi_mode = LABEL_UNIT_OI
    try:
        tr = load_eth_option_trades_day(day, underlying=symbol)
        if tr.get("ok") and int(tr.get("n") or 0) > 0:
            cols = tr["columns"]
            qty = np.asarray(cols["md_qty_lots"], dtype=np.float64)
            med = float(np.nanmedian(np.abs(qty))) if qty.size else 0.0
            scale = 1e8 if med > 1e5 else 1.0
            flow = ddoi_from_trade_flow(qty / scale, cols["aggressor_side"])
            by_id = accumulate_ddoi_by_instrument(cols["instrument_id"], flow)
            mapped = np.asarray([by_id.get(int(i), 0.0) for i in iv["instrument_ids"]], dtype=np.float64)
            if not np.allclose(mapped, 0):
                ddoi = mapped
                ddoi_mode = LABEL_TRADE_DDOI
    except Exception:  # noqa: BLE001
        pass
    pack = chain_exposures(
        flags=iv["flags"],
        strikes=iv["strikes"],
        ttm_years=iv["ttm_years"],
        iv=iv["iv"],
        ddoi=ddoi,
        spot=spot,
    )
    gex, vex, gp = pack["gex"], pack["vex"], pack["gex_plus"]
    inten = squeeze_intensity(gex, vex, gex_scale=max(abs(gex), 1.0), vex_scale=max(abs(vex), 1.0))
    scarce = scarcity_flag(gp)
    return {
        "gex": {
            "ok": True,
            "gex_mean": gex,
            "value": gex,
            "spot": spot,
            "ddoi_mode": ddoi_mode,
            "gate": "Hold",
            "gate_id": "risk.gex_exposure",
            "label": "Monitor",
            "source": "loaders+chain_exposures",
        },
        "vex": {
            "ok": True,
            "vex_mean": vex,
            "value": vex,
            "gate": "Hold",
            "gate_id": "risk.vex_exposure",
            "label": "Monitor",
            "source": "loaders+chain_exposures",
        },
        "squeeze": {
            "ok": True,
            "intensity": inten,
            "gex_plus": gp,
            "value": inten,
            "gate": "Hold",
            "gate_id": "risk.squeeze_intensity",
            "label": "Monitor",
            "source": "loaders+chain_exposures",
        },
        "scarcity": {
            "ok": True,
            "scarcity": scarce,
            "value": scarce,
            "gate": "Hold",
            "gate_id": "liq.implied_book_scarcity",
            "label": "Monitor",
            "source": "loaders+chain_exposures",
        },
        "source": "loaders+chain_exposures",
        "honesty": f"DDOI={ddoi_mode}; monitor≠α; live_orders=false",
    }


def compute_day_monitors(*, cfg: dict[str, Any], day: str | None = None) -> dict[str, Any]:
    from .shadow import data_loader_ready, find_latest_day

    if bool(cfg.get("live_orders")):
        raise RuntimeError("hard refuse: live_orders=True")

    venue = str(cfg.get("venue") or "hyperliquid").lower()
    symbol = str(cfg.get("symbol") or "ETH").upper()
    lookback = int(cfg.get("lookback_days") or 21)
    max_files = int(cfg.get("max_files") or 48)
    prefer_complete = bool(cfg.get("require_complete_day", False))

    deps: dict[str, Any] = {"data_loader": data_loader_ready(), "lib_squeeze": squeeze_lib_status()}
    found = None
    tape: dict[str, Any] | None = None

    if day is None:
        if deps["data_loader"].get("ok"):
            found = find_latest_day(
                venue,
                symbol,
                lookback=lookback,
                prefer_complete=prefer_complete,
                quiet=True,
                max_files=max_files,
            )
            day = str(found["day"])
        else:
            day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            deps["day_resolution"] = "fallback_utc_today_no_loader"

    assert day is not None

    # Optional tape load when scripts exist
    if deps["data_loader"].get("ok"):
        try:
            from _data import ensure_env, load_core_venues_day

            ensure_env()
            tape = load_core_venues_day(symbol, day, quiet=True)
        except Exception as exc:  # noqa: BLE001
            deps["tape_error"] = f"{type(exc).__name__}: {exc}"

    lib_st = deps["lib_squeeze"]
    computed: dict[str, Any] | None = None

    # 1) Prefer Pass-1 day artifacts (fast, certified numbers)
    art = _artifact_fallback(day)
    if art is not None and _lib_results_usable(art):
        computed = art

    # 2) Else recompute from warehouse loaders + squeeze.chain_exposures
    if not _lib_results_usable(computed) and deps["data_loader"].get("ok") and lib_st.get("ok"):
        try:
            computed = _compute_from_loaders(day=day, symbol=symbol)
        except Exception as exc:  # noqa: BLE001
            deps["loader_compute_error"] = f"{type(exc).__name__}: {exc}"
            computed = None

    # 3) Legacy high-level lib API (if a future squeeze.py exports gex_day/…)
    if not _lib_results_usable(computed) and lib_st.get("ok") and lib_st.get("module") is not None:
        try:
            computed = _compute_from_lib(
                mod=lib_st["module"],
                day=day,
                venue=venue,
                symbol=symbol,
                cfg=cfg,
                tape=tape,
            )
            if not _lib_results_usable(computed):
                computed = None
        except Exception as exc:  # noqa: BLE001
            deps["lib_compute_error"] = f"{type(exc).__name__}: {exc}"
            computed = None

    if not _lib_results_usable(computed):
        reason = lib_st.get("reason") or "monitors_unavailable"
        computed = {
            "gex": _hold_block("risk.gex_exposure", reason=reason),
            "vex": _hold_block("risk.vex_exposure", reason=reason),
            "squeeze": _hold_block("risk.squeeze_intensity", reason=reason),
            "scarcity": _hold_block("liq.implied_book_scarcity", reason=reason),
            "source": "dependency_stub",
        }

    # Drop non-serializable module handle from deps
    deps_out = {
        "data_loader": {k: v for k, v in deps["data_loader"].items() if k != "module"},
        "lib_squeeze": {k: v for k, v in lib_st.items() if k != "module"},
    }
    for k in ("day_resolution", "tape_error", "lib_compute_error", "loader_compute_error"):
        if k in deps:
            deps_out[k] = deps[k]

    gates = dict(cfg.get("gates") or GATE_LABELS)
    # Hard-pin Kill on TOB-cross; never soft-Promote as α
    gates["alpha.tob_cross_arb"] = "Kill"
    promotes = promote_only(gates)

    return {
        "ok": True,
        "day": day,
        "venue": venue,
        "symbol": symbol,
        "gex": computed.get("gex"),
        "vex": computed.get("vex"),
        "squeeze": computed.get("squeeze"),
        "scarcity": computed.get("scarcity"),
        "monitor_source": computed.get("source"),
        "gates": gates,
        "promote_ids": promotes,
        "promote_count": len(promotes),
        "deps": deps_out,
        "found": (
            {k: found[k] for k in ("day", "completeness", "probed") if found and k in found}
            if found
            else None
        ),
        "live_orders": False,
        "alpha_claim": False,
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "honesty": (
            "Monitor/Hold only — wire Promote only (expect 0); "
            "never soft-Promote TOB-cross α; never sized"
        ),
    }
