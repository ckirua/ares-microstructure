from __future__ import annotations
#!/usr/bin/env python3
"""Ch.13–14: quote-aligned signed-trade VAR / IRF + OFI + GH / MRR / HS.

Lenses: disc / cont / info / exec / mm / liq.

Δm construction (critical): ``quote_aligned_delta_mid(..., mode='next_mid_change')``
— not asof-mid diffs paired with q_{t+1}.
"""

import os

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

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
from research.lib import (  # noqa: E402
    glosten_harris_ols,
    huang_stoll_basic_ols,
    impulse_response_trade,
    lambda_time_split_bootstrap,
    mrr_ols,
    ofi_continuous,
    quote_aligned_delta_mid,
    signed_trade_var,
    trade_markouts,
    trade_sign_acf,
)

OUT13 = BOOK / "out" / "ch13_var_impact"
OUT14 = BOOK / "out" / "ch14_structural"


def _subsample(
    *arrs: np.ndarray, n_max: int = 80_000
) -> tuple[np.ndarray, ...]:
    n = arrs[0].size
    if n <= n_max:
        return arrs
    step = max(1, n // n_max)
    return tuple(a[::step] for a in arrs)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--days", nargs="*", default=None)
    ap.add_argument("--max-files", type=int, default=24)
    ap.add_argument("--lags", type=int, default=5)
    ap.add_argument("--max-lag-ms", type=int, default=5000)
    args = ap.parse_args()
    ensure_env()
    days = resolve_days(args.days)
    OUT13.mkdir(parents=True, exist_ok=True)
    OUT14.mkdir(parents=True, exist_ok=True)

    tob = load_hl_tob(args.symbol)
    tape = load_trades(args.symbol, days, args.max_files)
    ov = overlap_trades_with_mids(tape, tob)

    mid0 = ov["mid0"]
    ok = np.isfinite(mid0) & (mid0 > 0) & np.isfinite(ov["side"]) & (ov["side"] != 0)
    ts, px, side, qty = (
        ov["ts"][ok],
        ov["px"][ok],
        ov["side"][ok],
        ov["qty"][ok],
    )

    max_lag_ns = int(args.max_lag_ms) * 1_000_000
    # Primary: quote-update-aligned Δm (trade → first subsequent mid change)
    qa = quote_aligned_delta_mid(
        ts,
        side,
        tob["ts"],
        tob["mid"],
        trade_qty=qty,
        mode="next_mid_change",
        max_lag_ns=max_lag_ns,
    )
    # Robustness: corrected pre→next-trade mid (q_t not q_{t+1}) + quote clock
    qa_pt = quote_aligned_delta_mid(
        ts, side, tob["ts"], tob["mid"], trade_qty=qty, mode="pre_to_next_trade"
    )
    qa_qc = quote_aligned_delta_mid(
        ts, side, tob["ts"], tob["mid"], trade_qty=qty, mode="quote_clock"
    )

    if not qa.get("ok"):
        raise RuntimeError(f"quote-aligned Δm failed: n={qa.get('n')}")

    d_mid = qa["d_mid"]
    side_e = qa["side"]
    qty_e = qa["qty"]
    ts_e = qa["ts"]
    # trade-price Δ for MRR (event-time on same trade index as qa where possible)
    # MRR uses consecutive trade prices on the filtered trade set
    d_px = np.diff(px)
    side_px = side[:-1]
    m_px = np.isfinite(d_px) & np.isfinite(side_px) & (side_px != 0)

    d_mid_s, side_s, qty_s, ts_s = _subsample(d_mid, side_e, qty_e, ts_e)
    d_px_s, side_px_s = _subsample(d_px[m_px], side_px[m_px])

    var = signed_trade_var(d_mid_s, side_s, lags=args.lags)
    irf = impulse_response_trade(d_mid_s, side_s, lags=args.lags, horizon=25)
    lam_hygiene = lambda_time_split_bootstrap(d_mid_s, side_s, ts_s, n_boot=400, seed=13)

    # IRF time-split: permanent impact sign on train/test
    cut = int(0.7 * d_mid_s.size)
    irf_tr = impulse_response_trade(d_mid_s[:cut], side_s[:cut], lags=args.lags, horizon=25)
    irf_te = impulse_response_trade(d_mid_s[cut:], side_s[cut:], lags=args.lags, horizon=25)

    acf = trade_sign_acf(side, max_lag=20)
    mo = trade_markouts(ts, px, side, tob["ts"], tob["mid"], horizons_ms=(500, 1000, 5000))
    ofi = ofi_continuous(
        tob["ts"], tob["bid"], tob["ask"], tob["bid_sz"], tob["ask_sz"], bar_ns=1_000_000_000
    )

    sz = qty_s / max(float(np.nanmedian(qty_s[qty_s > 0])), 1e-12)
    gh = glosten_harris_ols(d_mid_s, side_s, sz)
    gh_tr = glosten_harris_ols(d_mid_s[:cut], side_s[:cut], sz[:cut])
    gh_te = glosten_harris_ols(d_mid_s[cut:], side_s[cut:], sz[cut:])
    mrr = mrr_ols(d_px_s, side_px_s)
    hs = huang_stoll_basic_ols(d_mid_s, side_s)

    lam = float(var.get("lambda_contemp", float("nan")))
    perm = float(irf.get("permanent_impact", float("nan")))
    perm_tr = float(irf_tr.get("permanent_impact", float("nan")))
    perm_te = float(irf_te.get("permanent_impact", float("nan")))

    promote_lam = bool(
        var.get("ok")
        and lam_hygiene.get("promote_ok")
        and np.isfinite(lam)
        and lam > 0
    )
    promote_irf = bool(
        irf.get("ok")
        and np.isfinite(perm)
        and np.isfinite(lam)
        and np.sign(perm) == np.sign(lam)
        and abs(perm) > 0
        and np.isfinite(perm_tr)
        and np.isfinite(perm_te)
        and np.sign(perm_tr) == np.sign(lam)
        and np.sign(perm_te) == np.sign(lam)
    )
    promote_ofi = bool(ofi.get("n", 0) >= 50 and np.isfinite(ofi.get("corr_ofi_ret", float("nan"))))
    promote_gh = bool(
        gh.get("n", 0) >= 200
        and np.isfinite(gh.get("z0", float("nan")))
        and gh["z0"] > 0
        and float(gh_te.get("z0") or 0) > 0
        and float(gh.get("r2") or 0) >= 0.01
    )
    promote_mrr = bool(
        mrr.get("n", 0) >= 200
        and np.isfinite(mrr.get("theta_perm", float("nan")))
        and mrr["theta_perm"] > 0
    )
    # HS lump π=(α+β)S/2: Hold unless explanatory power + positive on both halves
    hs_tr = huang_stoll_basic_ols(d_mid_s[:cut], side_s[:cut])
    hs_te = huang_stoll_basic_ols(d_mid_s[cut:], side_s[cut:])
    promote_hs = bool(
        hs.get("ok")
        and float(hs.get("pi_inv_info") or 0) > 0
        and float(hs_tr.get("pi_inv_info") or 0) > 0
        and float(hs_te.get("pi_inv_info") or 0) > 0
        and float(hs.get("r2") or 0) >= 0.01
    )

    decisions_13 = {
        "disc.var_lambda": "Promote" if promote_lam else "Hold",
        "disc.irf_permanent": "Promote" if promote_irf else "Hold",
        "disc.sign_acf": "Promote" if (acf.get("rho1") or 0) > 0.05 else "Hold",
        "cont.ofi_mid_corr": "Promote" if promote_ofi else "Hold",
        "info.markout_1s": (
            "Promote"
            if mo["by_horizon"].get("1000", {}).get("ci95", [0, 0])[0] > 0
            else "Hold"
        ),
    }
    decisions_14 = {
        "disc.gh_z0": "Promote" if promote_gh else "Hold",
        "disc.mrr_theta": "Promote" if promote_mrr else "Hold",
        "disc.mrr_rho_q": "Hold",
        "disc.hs_pi": "Promote" if promote_hs else "Hold",
    }
    fals_13 = {
        "disc.var_lambda": "λ≤0 on full/train/test or bootstrap CI lo≤0",
        "disc.irf_permanent": "cum IRF → 0, opposite sign to λ, or train/test sign flip",
        "disc.sign_acf": "ρ₁(q) ≤ 0 (no clustering)",
        "cont.ofi_mid_corr": "corr(OFI, r) CI includes 0",
        "info.markout_1s": "1s markout CI ≤ 0",
    }
    fals_14 = {
        "disc.gh_z0": "z0≤0 on test half or R²≈0",
        "disc.mrr_theta": "θ≤0 or unidentified ρ",
        "disc.mrr_rho_q": "ρ(q)≈0 always",
        "disc.hs_pi": "π≤0 on a split or R²<1% (α|β not separately ID'd)",
    }

    def _qa_summary(x: dict) -> dict:
        return {
            "mode": x.get("mode"),
            "n": x.get("n"),
            "ok": x.get("ok"),
            "corr_dm_q": x.get("corr_dm_q"),
            "median_lag_ms": x.get("median_lag_ms"),
        }

    p13 = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": args.symbol,
        "days": days,
        "alignment": {
            "primary": "next_mid_change",
            "max_lag_ms": args.max_lag_ms,
            "next_mid_change": _qa_summary(qa),
            "pre_to_next_trade": _qa_summary(qa_pt),
            "quote_clock": _qa_summary(qa_qc),
            "note": "Prior asof-mid+q[t+1] contaminated λ (negative); see NOTES.",
        },
        "n_event": int(d_mid_s.size),
        "var": var,
        "lambda_hygiene": lam_hygiene,
        "irf": {k: v for k, v in irf.items() if k != "irf"},
        "irf_train_permanent": perm_tr,
        "irf_test_permanent": perm_te,
        "irf_path": irf.get("irf", [])[:26],
        "sign_acf": acf,
        "ofi": ofi,
        "markouts": mo,
        "decisions": decisions_13,
        "falsifiers": fals_13,
        "lenses": {
            "disc.var_lambda": ["disc", "info", "exec"],
            "disc.irf_permanent": ["disc", "info", "exec"],
            "disc.sign_acf": ["disc", "mm", "info"],
            "cont.ofi_mid_corr": ["cont", "info", "mm"],
            "info.markout_1s": ["info", "mm", "exec"],
        },
    }
    p14 = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": args.symbol,
        "days": days,
        "alignment": "quote-aligned Δm (next_mid_change) for GH/HS; MRR on Δp",
        "gh": gh,
        "gh_train": gh_tr,
        "gh_test": gh_te,
        "mrr": mrr,
        "huang_stoll": hs,
        "huang_stoll_train": hs_tr,
        "huang_stoll_test": hs_te,
        "decisions": decisions_14,
        "falsifiers": fals_14,
        "lenses": {
            "disc.gh_z0": ["disc", "info", "exec"],
            "disc.mrr_theta": ["disc", "info", "liq"],
            "disc.mrr_rho_q": ["disc", "mm"],
            "disc.hs_pi": ["disc", "info", "liq", "mm"],
        },
    }
    (OUT13 / f"exp_ch13_{args.symbol.lower()}_summary.json").write_text(json.dumps(p13, indent=2))
    (OUT14 / f"exp_ch14_{args.symbol.lower()}_summary.json").write_text(json.dumps(p14, indent=2))

    hy = lam_hygiene
    rep13 = [
        f"# Ch.13 VAR / IRF / OFI — {args.symbol}",
        "",
        f"- alignment=`next_mid_change` · n_event={d_mid_s.size:,} · corr(Δm,q)={qa.get('corr_dm_q')}",
        f"- λ_VAR={lam} · λ_OLS={hy['full'].get('lambda')} · "
        f"train={hy['train'].get('lambda')} test={hy['test'].get('lambda')} · "
        f"boot CI=[{hy['boot_lo']}, {hy['boot_hi']}]",
        f"- permanent_IRF={perm} (train={perm_tr}, test={perm_te})",
        f"- sign ρ₁={acf.get('rho1')} · OFI corr={ofi.get('corr_ofi_ret')}",
        f"- markout 1s={mo['by_horizon'].get('1000')}",
        f"- robustness corr: pre_to_next_trade={qa_pt.get('corr_dm_q')} · "
        f"quote_clock={qa_qc.get('corr_dm_q')}",
        "",
        "## Decisions",
    ]
    for k, v in decisions_13.items():
        rep13.append(f"- `{k}`: **{v}** — {fals_13[k]}")
    (OUT13 / f"exp_ch13_{args.symbol.lower()}_REPORT.md").write_text("\n".join(rep13) + "\n")

    rep14 = [
        f"# Ch.14 GH / MRR / Huang–Stoll — {args.symbol}",
        "",
        f"- GH z0={gh.get('z0')} z1={gh.get('z1')} R²={gh.get('r2')} "
        f"(train z0={gh_tr.get('z0')}, test z0={gh_te.get('z0')})",
        f"- MRR θ={mrr.get('theta_perm')} φ={mrr.get('phi_temp')} ρ_q={mrr.get('rho_q')}",
        f"- HS π̂={hs.get('pi_inv_info')} R²={hs.get('r2')} "
        f"(train={hs_tr.get('pi_inv_info')}, test={hs_te.get('pi_inv_info')})",
        "",
        "## Decisions",
    ]
    for k, v in decisions_14.items():
        rep14.append(f"- `{k}`: **{v}** — {fals_14[k]}")
    (OUT14 / f"exp_ch14_{args.symbol.lower()}_REPORT.md").write_text("\n".join(rep14) + "\n")
    print((OUT13 / f"exp_ch13_{args.symbol.lower()}_REPORT.md").read_text())
    print((OUT14 / f"exp_ch14_{args.symbol.lower()}_REPORT.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
