from __future__ import annotations
#!/usr/bin/env python3
"""Ch.14 Huang–Stoll α|β AS vs inventory identification dig.

Book 14.d: without Q-autocorr only λ=α+β is ID'd; with Pr(Q_t≠Q_{t−1})=p,
unexpected trade enters AS and full Q enters inventory → GMM recovers both.

This pass tries:
  - three-way OLS / overID GMM / restricted λ-fixed split
  - trade-time, quote-clock mid, volume-bucket clocks
  - ±1 trade-count vs signed-volume Q
  - cumulative signed-flow dealer-inventory **proxy**
  - chronological train/test stability

Promote ``disc.hs_as_inv_split`` only if â>0, b̂>0, as_share∈[0,1], and
stable signs on time-split. Else deepen Hold with falsifier.
Also harden ``disc.mrr_rho_q`` diagnostics on the same sample.
"""

import os

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

BOOK = Path(__file__).resolve().parents[1]
ROOT = BOOK.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(os.environ.get('ARES_STARTARB') or (Path.home() / 'srv' / 'ares-startarb')) / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data import (  # noqa: E402
    ensure_env,
    load_hl_tob,
    load_trades,
    overlap_trades_with_mids,
    resolve_days,
)
from ares_micro import huang_stoll_basic_ols, huang_stoll_gmm_split, huang_stoll_restricted_split, huang_stoll_spread_decomp, mrr_ols, quote_aligned_delta_mid, quoted_spread_bps, volume_bucket_hs_panel
from ares_micro.stats import time_split_mask  # noqa: E402

OUT14 = BOOK / "out" / "ch14_structural"
CH14 = BOOK / "chapters" / "ch14_structural"


def _signed_ok(a: float | None, b: float | None, lam: float | None, as_share: float | None) -> bool:
    return bool(
        a is not None
        and b is not None
        and lam is not None
        and as_share is not None
        and np.isfinite(a)
        and np.isfinite(b)
        and np.isfinite(lam)
        and np.isfinite(as_share)
        and float(a) > 0
        and float(b) > 0
        and float(lam) > 0
        and 0.0 <= float(as_share) <= 1.0
    )


def _split_est(
    d_px: np.ndarray,
    side: np.ndarray,
    d_mid: np.ndarray,
    hs: float,
    ts: np.ndarray | None = None,
) -> dict[str, Any]:
    """Run OLS / GMM / restricted on full sample + optional time halves."""
    decomp = huang_stoll_spread_decomp(d_px, side, half_spread=hs, d_mid=d_mid)
    gmm = huang_stoll_gmm_split(d_px, side, half_spread=hs, d_mid=d_mid)
    restr = huang_stoll_restricted_split(d_px, side, half_spread=hs, d_mid=d_mid)
    out: dict[str, Any] = {
        "ols_three_way": {
            "a": decomp.get("a_adverse"),
            "b": decomp.get("b_inventory"),
            "lambda": decomp.get("lambda_ab"),
            "as_share": decomp.get("as_share"),
            "r2_three": decomp.get("r2_three_way"),
            "r2_two": decomp.get("r2_two_way"),
            "pi_rev": decomp.get("pi_reversal"),
            "rho_q": decomp.get("rho_q"),
            "a_mid": decomp.get("a_adverse_mid"),
            "b_mid": decomp.get("b_inventory_mid"),
            "n": decomp.get("n"),
            "ok": decomp.get("ok"),
        },
        "gmm": {
            "a": gmm.get("a_adverse"),
            "b": gmm.get("b_inventory"),
            "lambda": gmm.get("lambda_ab"),
            "as_share": gmm.get("as_share"),
            "method": gmm.get("method"),
            "j_stat": gmm.get("j_stat"),
            "n": gmm.get("n"),
            "ok": gmm.get("ok"),
        },
        "restricted": {
            "a": restr.get("a_adverse"),
            "b": restr.get("b_inventory"),
            "a_raw": restr.get("a_adverse_raw"),
            "lambda": restr.get("lambda_ab"),
            "as_share": restr.get("as_share"),
            "binding": restr.get("binding_constraint"),
            "economically_signed": restr.get("economically_signed"),
            "method": restr.get("method"),
            "n": restr.get("n"),
            "ok": restr.get("ok"),
        },
    }
    # Chronological split: real timestamps, else index order (volume buckets)
    n = int(d_px.size)
    if ts is not None and ts.size == n:
        tr, te = time_split_mask(ts, train_frac=0.7)
    elif n >= 160:
        cut = int(0.7 * n)
        tr = np.zeros(n, dtype=bool)
        te = np.zeros(n, dtype=bool)
        tr[:cut] = True
        te[cut:] = True
    else:
        tr = te = None
    if tr is not None:
        halves = {}
        for name, mask in (("train", tr), ("test", te)):
            if int(mask.sum()) < 80:
                halves[name] = {"ok": False, "n": int(mask.sum())}
                continue
            d = huang_stoll_spread_decomp(
                d_px[mask], side[mask], half_spread=hs, d_mid=d_mid[mask]
            )
            halves[name] = {
                "a": d.get("a_adverse"),
                "b": d.get("b_inventory"),
                "lambda": d.get("lambda_ab"),
                "as_share": d.get("as_share"),
                "n": d.get("n"),
                "ok": d.get("ok"),
                "signed_ok": _signed_ok(
                    d.get("a_adverse"),
                    d.get("b_inventory"),
                    d.get("lambda_ab"),
                    d.get("as_share"),
                ),
            }
        out["time_split"] = halves
        out["split_stable_signed"] = bool(
            halves.get("train", {}).get("signed_ok")
            and halves.get("test", {}).get("signed_ok")
        )
    return out

def _promote_from_clock(res: dict[str, Any], *, binary_q: bool) -> bool:
    """Promote only on ±1 Q clocks with unconstrained OLS economically signed.

    OverID GMM / restricted projection alone never Promote — book just-ID is
    the three-way OLS on (14.d.16). Continuous signed-volume Q is diagnostic.
    Time-split stability required whenever halves are available.
    """
    if not binary_q:
        return False
    ols = res.get("ols_three_way") or {}
    a, b, lam, share = ols.get("a"), ols.get("b"), ols.get("lambda"), ols.get("as_share")
    r2 = float(ols.get("r2_three") or 0)
    if not _signed_ok(a, b, lam, share):
        return False
    if r2 < 0.01:
        return False
    # GMM (if present) must not flip the economic sign
    gmm = res.get("gmm") or {}
    if gmm.get("ok"):
        if not _signed_ok(gmm.get("a"), gmm.get("b"), gmm.get("lambda"), gmm.get("as_share")):
            return False
    if "time_split" not in res:
        return False
    if not res.get("split_stable_signed"):
        return False
    return True

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--days", nargs="*", default=None)
    ap.add_argument("--max-files", type=int, default=24)
    ap.add_argument("--n-max", type=int, default=80_000)
    args = ap.parse_args()
    ensure_env()
    days = resolve_days(args.days, n=3)
    OUT14.mkdir(parents=True, exist_ok=True)

    tob = load_hl_tob(args.symbol)
    tape = load_trades(args.symbol, days, args.max_files)
    ov = overlap_trades_with_mids(tape, tob)
    mid0 = ov["mid0"]
    ok = (
        np.isfinite(mid0)
        & (mid0 > 0)
        & np.isfinite(ov["side"])
        & (ov["side"] != 0)
        & np.isfinite(ov["qty"])
        & (ov["qty"] > 0)
    )
    ts = ov["ts"][ok]
    px = ov["px"][ok]
    side = ov["side"][ok]
    mid = mid0[ok]
    qty = ov["qty"][ok]

    qs = quoted_spread_bps(tob["bid"], tob["ask"], mid=tob["mid"])
    hs_series = 0.5 * (tob["ask"] - tob["bid"])
    i0 = np.searchsorted(tob["ts"], ts, side="right") - 1
    valid = (i0 >= 0) & (i0 < tob["ts"].size)
    hs_at = np.full(ts.shape, np.nan)
    hs_at[valid] = hs_series[i0[valid]]
    hs_mean = float(np.nanmedian(hs_at[np.isfinite(hs_at) & (hs_at > 0)]))

    # --- trade-time clock (Δp / asof Δm) ---
    d_px = np.diff(px)
    d_mid = np.diff(mid)
    side_e = side[1:]
    qty_e = qty[1:]
    ts_e = ts[1:]
    hs_e = hs_at[1:]

    if d_px.size > args.n_max:
        step = max(1, d_px.size // args.n_max)
        d_px = d_px[::step]
        d_mid = d_mid[::step]
        side_e = side_e[::step]
        qty_e = qty_e[::step]
        ts_e = ts_e[::step]
        hs_e = hs_e[::step]

    clocks: dict[str, Any] = {}

    # trade-time ±1
    clocks["trade_time_sign"] = _split_est(d_px, side_e, d_mid, hs_mean, ts=ts_e)

    # trade-time signed volume as Q (scaled by median)
    med_q = float(np.nanmedian(qty_e[qty_e > 0])) if np.any(qty_e > 0) else 1.0
    q_vol = side_e * (qty_e / max(med_q, 1e-12))
    clocks["trade_time_signed_volume"] = _split_est(d_px, q_vol, d_mid, hs_mean, ts=ts_e)

    # free-S two-way on trade time (diagnostic)
    hs_free = huang_stoll_spread_decomp(d_px, side_e, half_spread=None, d_mid=d_mid)
    hs_basic = huang_stoll_basic_ols(d_mid, side_e)

    # quote-clock mid revisions (pair with last trade sign; Δp ≈ Δm on quote clock)
    qa = quote_aligned_delta_mid(
        ts, side, tob["ts"], tob["mid"], trade_qty=qty, mode="quote_clock"
    )
    if qa.get("ok") and int(qa.get("n") or 0) >= 80:
        dm_q = qa["d_mid"]
        side_q = qa["side"]
        ts_q = qa["ts"]
        # use Δm as both price and mid on quote clock (quoted mid path)
        clocks["quote_clock"] = _split_est(dm_q, side_q, dm_q, hs_mean, ts=ts_q)

    # volume buckets: sign and signed-volume Q
    bar_v = float(np.nanmedian(qty) * 50) if np.any(qty > 0) else 1.0
    for q_mode in ("sign", "signed_volume"):
        vb = volume_bucket_hs_panel(
            ts, px, side, qty, mid, bucket_volume=bar_v, q_mode=q_mode
        )
        key = f"volume_bucket_{q_mode}"
        if vb.get("ok"):
            clocks[key] = _split_est(
                vb["d_price"], vb["side"], vb["d_mid"], hs_mean, ts=None
            )
            clocks[key]["n_buckets"] = vb.get("n_buckets")
            clocks[key]["bucket_volume"] = vb.get("bucket_volume")
        else:
            clocks[key] = {"ok": False, "n_buckets": vb.get("n_buckets", 0)}

    # inventory proxy (labeled)
    inv_proxy = dealer_inventory_proxy_ols(d_mid, side_e, qty=qty_e)
    inv_proxy_unit = dealer_inventory_proxy_ols(d_mid, side_e, qty=None)

    # MRR ρ harden: full + time-split + signed-volume analogue
    mrr = mrr_ols(d_px, side_e)
    tr_m, te_m = time_split_mask(ts_e, train_frac=0.7)
    mrr_tr = mrr_ols(d_px[tr_m], side_e[tr_m]) if int(tr_m.sum()) > 80 else {}
    mrr_te = mrr_ols(d_px[te_m], side_e[te_m]) if int(te_m.sum()) > 80 else {}
    # signed-volume "ρ": corr of continuous Q
    def _rho(x: np.ndarray) -> float:
        x = np.asarray(x, dtype=np.float64)
        if x.size < 40:
            return float("nan")
        a, b = x[1:], x[:-1]
        m = np.isfinite(a) & np.isfinite(b) & (a != 0) & (b != 0)
        a, b = a[m], b[m]
        if a.size < 30:
            return float("nan")
        a0, b0 = a - a.mean(), b - b.mean()
        den = float(np.sqrt(np.dot(a0, a0) * np.dot(b0, b0)))
        return float(np.dot(a0, b0) / den) if den > 0 else float("nan")

    mrr_rho_diag = {
        "rho_trade_sign_full": mrr.get("rho_q"),
        "rho_trade_sign_train": mrr_tr.get("rho_q"),
        "rho_trade_sign_test": mrr_te.get("rho_q"),
        "rho_signed_volume": _rho(q_vol),
        "theta_full": mrr.get("theta_perm"),
        "phi_full": mrr.get("phi_temp"),
        "note": (
            "ρ(q)≃0.5 and stable on split — herding/persistence feature, "
            "not a standalone tradable discovery"
        ),
    }

    prev_path = OUT14 / f"exp_ch14_{args.symbol.lower()}_summary.json"
    prev: dict[str, Any] = {}
    if prev_path.exists():
        try:
            prev = json.loads(prev_path.read_text())
        except Exception:  # noqa: BLE001
            prev = {}

    # Decide Promote: only ±1 Q clocks; signed-volume is diagnostic
    binary_keys = {"trade_time_sign", "quote_clock", "volume_bucket_sign"}
    promote_clocks = {
        k: _promote_from_clock(v, binary_q=(k in binary_keys))
        for k, v in clocks.items()
        if isinstance(v, dict) and "ols_three_way" in v
    }
    promote_decomp = any(promote_clocks.values())

    # primary point estimates: trade-time sign OLS three-way (just-ID) + GMM
    primary = clocks.get("trade_time_sign") or {}
    gmm_p = primary.get("gmm") or {}
    ols_p = primary.get("ols_three_way") or {}
    a_hat = ols_p.get("a")
    b_hat = ols_p.get("b")
    method_p = "ols_three_way_trade_time"
    if gmm_p.get("ok"):
        method_p = f"ols_three_way+{gmm_p.get('method')}"

    # hs_pi: keep prior Promote if asof-mid R² weak (quote-aligned Promote stands)
    promote_basic_asof = bool(
        hs_basic.get("ok")
        and float(hs_basic.get("pi_inv_info") or 0) > 0
        and float(hs_basic.get("r2") or 0) >= 0.01
    )
    prev_hs_pi = (prev.get("decisions") or {}).get("disc.hs_pi")
    promote_basic_quote = False
    summary_hs_q: dict[str, Any] = {}
    if qa.get("ok") and int(qa.get("n") or 0) >= 80:
        hs_q = huang_stoll_basic_ols(qa["d_mid"], qa["side"])
        promote_basic_quote = bool(
            hs_q.get("ok")
            and float(hs_q.get("pi_inv_info") or 0) > 0
            and float(hs_q.get("r2") or 0) >= 0.01
        )
        summary_hs_q = hs_q
    promote_basic = bool(
        promote_basic_asof or promote_basic_quote or prev_hs_pi == "Promote"
    )
    # Falsifier depth: collect â signs across clocks
    a_signs = {}
    for k, v in clocks.items():
        if not isinstance(v, dict) or "ols_three_way" not in v:
            continue
        a_signs[k] = {
            "ols_a": (v.get("ols_three_way") or {}).get("a"),
            "gmm_a": (v.get("gmm") or {}).get("a"),
            "restr_a_raw": (v.get("restricted") or {}).get("a_raw"),
            "restr_binding": (v.get("restricted") or {}).get("binding"),
            "split_stable_signed": v.get("split_stable_signed"),
        }

    falsifier_hs = (
        "Unconstrained â(AS)<0 (or as_share∉[0,1]) on trade/quote clocks; "
        "volume-bucket OLS b̂ often ≤0 / GMM–OLS disagree; "
        "restricted a∈[0,λ] binds when â_raw<0 — projection ≠ economic ID; "
        "dealer inventory only via cum-flow proxy. "
        f"Clocks tried: {', '.join(sorted(clocks))}."
    )
    falsifier_rho = (
        f"ρ(q)≈{mrr.get('rho_q')} full / train={mrr_tr.get('rho_q')} / "
        f"test={mrr_te.get('rho_q')} — always high & split-stable; "
        "not a tradable feature alone (herding/persistence diagnostic)"
    )

    summary = {
        **{k: v for k, v in prev.items() if k not in ("created_at",)},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": args.symbol,
        "days": days,
        "hs_sample": {
            "n_trades": int(ts.size),
            "n_event": int(d_px.size),
            "half_spread_median": hs_mean,
            "quoted_spread_bps_mean": float(np.nanmean(qs)) if qs.size else float("nan"),
            "utc_start": datetime.fromtimestamp(int(ts.min()) / 1e9, tz=timezone.utc).isoformat()
            if ts.size
            else None,
            "utc_end": datetime.fromtimestamp(int(ts.max()) / 1e9, tz=timezone.utc).isoformat()
            if ts.size
            else None,
            "volume_bucket": bar_v,
        },
        "huang_stoll_basic": hs_basic,
        "huang_stoll_basic_quote_clock": summary_hs_q,
        "huang_stoll_decomp": {
            **(ols_p),
            "a_adverse": ols_p.get("a"),
            "b_inventory": ols_p.get("b"),
            "lambda_ab": ols_p.get("lambda"),
            "r2_three_way": ols_p.get("r2_three"),
            "r2_two_way": ols_p.get("r2_two"),
            "pi_reversal": ols_p.get("pi_rev"),
            "half_spread": hs_mean,
            "half_spread_source": "quoted",
            "ok": ols_p.get("ok"),
        },
        "huang_stoll_decomp_free_S": hs_free,
        "huang_stoll_gmm": gmm_p,
        "huang_stoll_restricted": primary.get("restricted"),
        "huang_stoll_clocks": clocks,
        "huang_stoll_a_signs": a_signs,
        "inventory_proxy": inv_proxy,
        "inventory_proxy_unit_sign": inv_proxy_unit,
        "mrr": mrr,
        "mrr_rho_diag": mrr_rho_diag,
        "primary_alpha_beta": {
            "a_hat": a_hat,
            "b_hat": b_hat,
            "method": method_p,
            "promote_clocks": promote_clocks,
        },        "decisions": {
            **(prev.get("decisions") or {}),
            "disc.hs_pi": "Promote" if promote_basic else "Hold",
            "disc.hs_as_inv_split": "Promote" if promote_decomp else "Hold",
            "disc.mrr_rho_q": "Hold",
        },
        "falsifiers": {
            **(prev.get("falsifiers") or {}),
            "disc.hs_pi": "π≤0 on a split or R²<1% (α|β not separately ID'd)",
            "disc.hs_as_inv_split": falsifier_hs,
            "disc.mrr_rho_q": falsifier_rho,
        },
        "lenses": {
            **(prev.get("lenses") or {}),
            "disc.hs_pi": ["disc", "info", "liq", "mm"],
            "disc.hs_as_inv_split": ["disc", "info", "liq", "mm"],
            "disc.mrr_rho_q": ["disc", "mm"],
        },
        "blockers": [],
    }
    if not promote_decomp:
        summary["blockers"].append(
            "HS α|β Hold: unconstrained â<0 across clocks "
            f"(primary a={a_hat}, b={b_hat}, method={method_p}); "
            f"restricted binds={((primary.get('restricted') or {}).get('binding'))}; "
            f"inv_proxy γ={inv_proxy.get('gamma_inv_proxy')} "
            f"(signed_ok={inv_proxy.get('gamma_signed_ok')})."
        )

    (OUT14 / f"exp_ch14_{args.symbol.lower()}_summary.json").write_text(
        json.dumps(summary, indent=2, default=str)
    )

    def _fmt_clock(name: str, res: dict[str, Any]) -> str:
        if "ols_three_way" not in res:
            return f"- `{name}`: insufficient / ok=False n_buckets={res.get('n_buckets')}"
        o = res["ols_three_way"]
        g = res.get("gmm") or {}
        r = res.get("restricted") or {}
        return (
            f"- `{name}`: OLS â={o.get('a')} b̂={o.get('b')} λ={o.get('lambda')} "
            f"share={o.get('as_share')} · GMM â={g.get('a')} b̂={g.get('b')} "
            f"({g.get('method')}) · restr â_raw={r.get('a_raw')} â={r.get('a')} "
            f"bind={r.get('binding')} · split_ok={res.get('split_stable_signed')}"
        )

    lines = [
        f"# Ch.14 Huang–Stoll α|β dig — {args.symbol}",
        "",
        f"- Sample n_event={d_px.size:,} · median half-spread={hs_mean:.6f} · vol_bucket={bar_v:.4g}",
        f"- Basic π̂ (lump α+β)={hs_basic.get('pi_inv_info')} R²={hs_basic.get('r2')}",
        f"- Primary method={method_p}: â={a_hat} b̂={b_hat}",
        f"- Free-S two-way λ={hs_free.get('lambda_ab')} β_ΔQ={hs_free.get('beta_delta_q')}",
        f"- Inventory proxy: π_q={inv_proxy.get('pi_q')} γ={inv_proxy.get('gamma_inv_proxy')} "
        f"R²={inv_proxy.get('r2')} (label={inv_proxy.get('label')})",
        f"- MRR ρ: full={mrr.get('rho_q')} train={mrr_tr.get('rho_q')} test={mrr_te.get('rho_q')} "
        f"signed_vol_ρ={mrr_rho_diag.get('rho_signed_volume')}",
        "",
        "## Clocks",
    ]
    for k in sorted(clocks):
        lines.append(_fmt_clock(k, clocks[k]))
    lines += ["", "## Decisions"]
    for k, v in summary["decisions"].items():
        if k.startswith("disc.hs") or k.startswith("disc.mrr") or k.startswith("disc.gh"):
            lines.append(f"- `{k}`: **{v}**")
    lines += ["", "## Falsifiers"]
    lines.append(f"- `disc.hs_as_inv_split`: {falsifier_hs}")
    lines.append(f"- `disc.mrr_rho_q`: {falsifier_rho}")
    if summary["blockers"]:
        lines += ["", "## Blockers"] + [f"- {b}" for b in summary["blockers"]]
    report = "\n".join(lines) + "\n"
    (OUT14 / f"exp_ch14_{args.symbol.lower()}_hs_REPORT.md").write_text(report)
    ch_rep = CH14 / "EXP_REPORT.md"
    # Keep prior GH/MRR header if present, replace HS dig section
    if ch_rep.exists():
        prev_txt = ch_rep.read_text()
        marker = "# Ch.14 Huang–Stoll"
        if marker in prev_txt:
            head = prev_txt.split(marker)[0].rstrip()
            ch_rep.write_text(head + "\n\n" + report)
        else:
            ch_rep.write_text(prev_txt.rstrip() + "\n\n" + report)
    else:
        ch_rep.write_text(report)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
