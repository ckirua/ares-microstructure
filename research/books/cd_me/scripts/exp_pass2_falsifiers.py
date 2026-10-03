#!/usr/bin/env python3
"""Pass-2 falsifiers for cd_me: time-split, block bootstrap, placebo regimes.

Reads Pass-1 artifacts under ``out/pim_vloop_tcost/`` and ``out/dcm_proxies/``,
recomputes pooled checks, writes ``out/pass2/pass2_falsifiers.json``.

ClickHouse MCP banned.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
SCRIPTS = Path(__file__).resolve().parent
WAREHOUSE_SRC = Path(
    os.environ.get("WAREHOUSE_SRC")
    or (
        (Path(os.environ.get("WAREHOUSE_ROOT") or (Path.home() / "lab/lab-n2070/warehouse")) / "src")
    )
)
STARTARB = Path(os.environ.get("ARES_STARTARB") or (Path.home() / "srv/ares-startarb"))

for _p in (str(WAREHOUSE_SRC), str(STARTARB / "src"), str(ROOT), str(SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from research.lib.cdme import elasticity_corr, regime_split_corr  # noqa: E402

PIM_OUT = BOOK / "out" / "pim_vloop_tcost"
DCM_OUT = BOOK / "out" / "dcm_proxies"
EL_OUT = BOOK / "out" / "elasticity_regimes"
OUT = BOOK / "out" / "pass2"

MIN_N = 5


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        x = float(obj)
        return x if np.isfinite(x) else None
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, np.ndarray):
        return _jsonable(obj.tolist())
    return obj


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _pool_from_dcm_rows(rows: list[dict[str, Any]]) -> dict[str, np.ndarray]:
    vols, pims, dcms, days = [], [], [], []
    for r in rows:
        if not r.get("ok"):
            continue
        hp = r.get("hourly_pool") or {}
        day = str(r.get("day"))
        n = max(len(hp.get("pim") or []), len(hp.get("notional") or []), len(hp.get("dcm") or []))
        for i in range(n):
            try:
                v = float((hp.get("notional") or [None] * n)[i])
                p = float((hp.get("pim") or [None] * n)[i])
            except (TypeError, ValueError):
                continue
            if not (np.isfinite(v) and np.isfinite(p)):
                continue
            d_raw = (hp.get("dcm") or [None] * n)[i]
            try:
                d = float(d_raw) if d_raw is not None else float("nan")
            except (TypeError, ValueError):
                d = float("nan")
            vols.append(v)
            pims.append(p)
            dcms.append(d)
            days.append(day)
    return {
        "volume": np.asarray(vols, dtype=np.float64),
        "pim": np.asarray(pims, dtype=np.float64),
        "dcm": np.asarray(dcms, dtype=np.float64),
        "day": np.asarray(days, dtype=object),
    }


def _bootstrap_corr(
    x: np.ndarray,
    y: np.ndarray,
    *,
    n_boot: int = 600,
    seed: int = 42,
) -> dict[str, Any]:
    m = np.isfinite(x) & np.isfinite(y)
    xx, yy = x[m], y[m]
    n = int(xx.size)
    if n < MIN_N:
        return {"ok": False, "n": n}
    point = float(np.corrcoef(xx, yy)[0, 1])
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        c = float(np.corrcoef(xx[idx], yy[idx])[0, 1])
        if np.isfinite(c):
            boots.append(c)
    if len(boots) < 50:
        return {"ok": True, "n": n, "corr": point, "ci_lo": None, "ci_hi": None}
    lo, hi = np.quantile(boots, [0.025, 0.975])
    return {"ok": True, "n": n, "corr": point, "ci_lo": float(lo), "ci_hi": float(hi)}


def _block_bootstrap_by_day(
    pool: dict[str, np.ndarray],
    *,
    n_boot: int = 400,
    seed: int = 7,
) -> dict[str, Any]:
    days = pool["day"]
    uniq = sorted({str(d) for d in days.tolist()})
    if len(uniq) < 2:
        return {"ok": False, "reason": "need_ge_2_days"}
    by_day: dict[str, list[int]] = {d: [] for d in uniq}
    for i, d in enumerate(days.tolist()):
        by_day[str(d)].append(i)
    v, p = pool["volume"], pool["pim"]
    m = np.isfinite(v) & np.isfinite(p)
    point = float(np.corrcoef(v[m], p[m])[0, 1]) if int(m.sum()) >= MIN_N else float("nan")
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        pick_days = [uniq[i] for i in rng.integers(0, len(uniq), size=len(uniq))]
        idx = []
        for d in pick_days:
            idx.extend(by_day[d])
        if len(idx) < MIN_N:
            continue
        idx_arr = np.asarray(idx, dtype=np.int64)
        c = float(np.corrcoef(v[idx_arr], p[idx_arr])[0, 1])
        if np.isfinite(c):
            boots.append(c)
    if len(boots) < 50:
        return {"ok": False, "n_days": len(uniq), "corr": point}
    lo, hi = np.quantile(boots, [0.025, 0.975])
    return {
        "ok": True,
        "n_days": len(uniq),
        "corr": point,
        "ci_lo": float(lo),
        "ci_hi": float(hi),
        "n_boot": len(boots),
        "label": "block_bootstrap_resample_days",
    }


def _chronological_split(pool: dict[str, np.ndarray]) -> dict[str, Any]:
    days = pool["day"]
    uniq = sorted({str(d) for d in days.tolist()})
    if len(uniq) < 4:
        return {"ok": False, "reason": "need_ge_4_days"}
    mid = len(uniq) // 2
    early, late = set(uniq[:mid]), set(uniq[mid:])
    m_e = np.array([str(d) in early for d in days.tolist()])
    m_l = np.array([str(d) in late for d in days.tolist()])
    v, p = pool["volume"], pool["pim"]
    e = elasticity_corr(v[m_e], p[m_e], min_n=MIN_N)
    l = elasticity_corr(v[m_l], p[m_l], min_n=MIN_N)
    stable_sign = (
        e.get("corr") is not None
        and l.get("corr") is not None
        and np.sign(e["corr"]) == np.sign(l["corr"])
    )
    return {
        "ok": True,
        "early_days": sorted(early),
        "late_days": sorted(late),
        "early": e,
        "late": l,
        "sign_stable": bool(stable_sign),
        "falsifier": "sign_flip_across_chrono_halves → weaken Hold",
    }


def _placebo_shuffle_pim(pool: dict[str, np.ndarray], *, seed: int = 99) -> dict[str, Any]:
    v, p, days = pool["volume"], pool["pim"], pool["day"]
    m = np.isfinite(v) & np.isfinite(p)
    if int(m.sum()) < MIN_N:
        return {"ok": False}
    real = float(np.corrcoef(v[m], p[m])[0, 1])
    rng = np.random.default_rng(seed)
    nulls = []
    for _ in range(300):
        p_sh = p.copy()
        for d in sorted({str(x) for x in days.tolist()}):
            idx = np.where(days == d)[0]
            if idx.size < 2:
                continue
            perm = rng.permutation(idx.size)
            p_sh[idx] = p_sh[idx[perm]]
        mm = np.isfinite(v) & np.isfinite(p_sh)
        if int(mm.sum()) < MIN_N:
            continue
        c = float(np.corrcoef(v[mm], p_sh[mm])[0, 1])
        if np.isfinite(c):
            nulls.append(abs(c))
    if not nulls:
        return {"ok": False}
    null_med = float(np.median(nulls))
    return {
        "ok": True,
        "real_abs_corr": abs(real),
        "placebo_abs_corr_median": null_med,
        "passes": bool(abs(real) > null_med + 0.05),
        "label": "within_day_pim_shuffle",
    }


def _placebo_dcm_regime(pool: dict[str, np.ndarray], *, seed: int = 101) -> dict[str, Any]:
    v, p, d = pool["volume"], pool["pim"], pool["dcm"]
    m = np.isfinite(v) & np.isfinite(p) & np.isfinite(d)
    if int(m.sum()) < MIN_N * 2:
        return {"ok": False, "reason": "thin_dcm_join"}
    real = regime_split_corr(v[m], p[m], d[m], min_n=MIN_N)
    rng = np.random.default_rng(seed)
    deltas = []
    for _ in range(200):
        d_sh = d[m].copy()
        rng.shuffle(d_sh)
        sh = regime_split_corr(v[m], p[m], d_sh, min_n=MIN_N)
        if sh.get("delta_corr") is not None and np.isfinite(sh["delta_corr"]):
            deltas.append(abs(float(sh["delta_corr"])))
    real_delta = real.get("delta_corr")
    if real_delta is None or not deltas:
        return {"ok": False, "real": real}
    return {
        "ok": True,
        "real_delta_corr": float(real_delta) if np.isfinite(real_delta) else None,
        "placebo_abs_delta_median": float(np.median(deltas)),
        "passes": bool(abs(float(real_delta)) > np.median(deltas) + 0.03),
        "label": "shuffle_dcm_pc1_regime_split",
    }


def _pim_panel_falsifiers(pim_summary: dict[str, Any]) -> dict[str, Any]:
    rows = pim_summary.get("day_summaries") or []
    three_v = sum(
        1
        for r in rows
        if r.get("ok") and len(r.get("venues_tob") or []) >= 3
    )
    kr_in = sum(1 for r in rows if "kraken" in (r.get("venues_tob") or []))
    corrs = [
        (r.get("summary") or {}).get("corr_vloop_tcost")
        for r in rows
        if r.get("ok")
    ]
    corrs_f = [c for c in corrs if c is not None and np.isfinite(c)]
    return {
        "n_days_ok": pim_summary.get("n_ok"),
        "n_days_3_venue_tob": three_v,
        "n_days_kraken_tob": kr_in,
        "kraken_status": pim_summary.get("kraken_status"),
        "vloop_tcost_corr_by_day": corrs_f,
        "vloop_tcost_corr_median": float(np.median(corrs_f)) if corrs_f else None,
        "venue_drop_note": "3-venue triangle only when Kraken spot L2 listed for day",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write-reports", action="store_true", help="Patch chapter EXP_REPORT snippets")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    pim_path = PIM_OUT / "summary.json"
    dcm_path = DCM_OUT / "panel_rows.json"
    el_path = EL_OUT / "summary.json"
    if not pim_path.is_file():
        print(json.dumps({"ok": False, "blocker": "missing pim summary"}))
        return 2

    pim_summary = _load_json(pim_path)
    dcm_rows: list[dict[str, Any]] = []
    if dcm_path.is_file():
        dcm_rows = json.loads(dcm_path.read_text())
    el_summary = _load_json(el_path) if el_path.is_file() else {}

    pool = _pool_from_dcm_rows(dcm_rows)
    pooled = el_summary.get("pooled") or {}

    out = {
        "ok": True,
        "pass": 2,
        "pim_panel": _pim_panel_falsifiers(pim_summary),
        "elasticity_pooled_pass1": {
            "n_hours": pooled.get("n_hours_pooled") or int(pool["volume"].size),
            "all": pooled.get("all"),
            "regime_bootstrap": pooled.get("regime_bootstrap"),
        },
        "falsifiers": {
            "chrono_split": _chronological_split(pool),
            "iid_bootstrap_corr": _bootstrap_corr(pool["volume"], pool["pim"]),
            "block_bootstrap_by_day": _block_bootstrap_by_day(pool),
            "placebo_pim_shuffle": _placebo_shuffle_pim(pool),
            "placebo_dcm_regime": _placebo_dcm_regime(pool),
        },
        "decisions": {
            "risk.pim_cross_venue": "Hold",
            "info.vloop_tcost_commonality": "Hold",
            "risk.dcm_pc1": "Hold",
            "liq.elasticity_regime": "Hold",
            "promote_count": 0,
            "note": "Pass-2 falsifiers run; 0 Promote — monitors only, no TOB-cross α",
        },
    }

    # Gate elasticity Hold on falsifiers
    chrono = out["falsifiers"]["chrono_split"]
    placebo_p = out["falsifiers"]["placebo_pim_shuffle"]
    if chrono.get("ok") and not chrono.get("sign_stable"):
        out["decisions"]["liq.elasticity_regime"] = "Hold (chrono sign split — weaker)"
    if placebo_p.get("ok") and not placebo_p.get("passes"):
        out["decisions"]["liq.elasticity_regime"] = "Hold (placebo PIM shuffle not separated)"

    path = OUT / "pass2_falsifiers.json"
    path.write_text(json.dumps(_jsonable(out), indent=2))
    print(json.dumps(_jsonable({"written": str(path), "decisions": out["decisions"]}), indent=2))

    if args.write_reports:
        _patch_exp_reports(out)
    return 0


def _patch_exp_reports(payload: dict[str, Any]) -> None:
    f = payload["falsifiers"]
    ch = f["chrono_split"]
    bb = f["block_bootstrap_by_day"]
    pp = payload["pim_panel"]
    el = payload["elasticity_pooled_pass1"].get("all") or {}
    addendum = f"""

## Pass 2 falsifiers (auto)

- **Kraken TOB:** loader fixed → spot `l2_rebuild`; **{pp.get('n_days_kraken_tob')}** / {pp.get('n_days_ok')} panel days with Kraken; **{pp.get('n_days_3_venue_tob')}** days with 3-venue TOB.
- **Pooled elasticity:** n={el.get('n')} corr={el.get('corr')} CI[{el.get('ci_lo')}, {el.get('ci_hi')}].
- **Chrono split:** early corr={((ch.get('early') or {}).get('corr'))} late={((ch.get('late') or {}).get('corr'))} sign_stable={ch.get('sign_stable')}.
- **Block bootstrap (by day):** corr={bb.get('corr')} CI[{bb.get('ci_lo')}, {bb.get('ci_hi')}].
- **Placebo PIM shuffle:** passes={f['placebo_pim_shuffle'].get('passes')}; **DCM shuffle:** passes={f['placebo_dcm_regime'].get('passes')}.
- **Decision:** 0 Promote; all monitors **Hold**.
"""
    for rel in (
        "chapters/pim_vloop_tcost/EXP_REPORT.md",
        "chapters/dcm_proxies/EXP_REPORT.md",
        "chapters/elasticity_regimes/EXP_REPORT.md",
        "chapters/ch00_overview/EXP_REPORT.md",
    ):
        p = BOOK / rel
        if not p.is_file():
            continue
        text = p.read_text()
        marker = "## Pass 2 falsifiers (auto)"
        if marker in text:
            text = text.split(marker)[0].rstrip()
        p.write_text(text + addendum)


if __name__ == "__main__":
    raise SystemExit(main())
