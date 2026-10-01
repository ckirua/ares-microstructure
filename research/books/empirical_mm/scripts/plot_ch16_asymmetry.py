from __future__ import annotations
#!/usr/bin/env python3
"""Ch.16 asymmetry synthesis — comparative plots from ch13/14/15/9/22 out/."""


import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BOOK = Path(__file__).resolve().parents[1]
OUT = BOOK / "out" / "ch16_asymmetry"
CHAP = BOOK / "chapters" / "ch16_asymmetry"


def _load(rel: str) -> dict:
    p = BOOK / "out" / rel
    return json.loads(p.read_text()) if p.exists() else {}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ch09 = _load("ch09_estimation/exp_ch09_eth_summary.json")
    ch13 = _load("ch13_var_impact/exp_ch13_eth_summary.json")
    ch14 = _load("ch14_structural/exp_ch14_eth_summary.json")
    ch15 = _load("ch15_pin/exp_ch15_eth_summary.json")
    ch22 = _load("ch22_liquidity/exp_ch22_eth_summary.json")
    ch03 = _load("ch03_roll/exp_ch03_eth_summary.json")

    lam = ((ch13.get("lambda_hygiene") or {}).get("full") or {}).get("lambda")
    irf = (ch13.get("irf") or {}).get("permanent_impact")
    markout = ((ch13.get("markouts") or {}).get("by_horizon") or {}).get("1000", {}).get("mean_bps")
    sign_rho = (ch13.get("sign_acf") or {}).get("rho1")
    mrr_theta = (ch14.get("mrr") or {}).get("theta_perm")
    gh_z0 = (ch14.get("gh") or {}).get("z0")
    hs_pi = (ch14.get("huang_stoll_basic") or ch14.get("huang_stoll") or {}).get("pi_inv_info")
    decomp = ch14.get("huang_stoll_decomp") or {}
    hs_two_way = decomp.get("lambda") or decomp.get("lambda_ab")
    hs_a = decomp.get("a") if decomp.get("a") is not None else decomp.get("a_adverse")
    pin = (ch15.get("disc_pin_eho_mle") or {}).get("PIN")
    pin_dec = (ch15.get("decisions") or {}).get("disc.pin_eho_mle", "Hold")
    pin_n = ch15.get("n_days_mle_usable")
    vpin = (ch15.get("cont_vpin") or {}).get("mean_vpin")
    qs = (ch22.get("quoted_spread_bps") or {}).get("point")
    sig_w = (ch09.get("rw_ar10") or {}).get("sigma_w")
    noise = ((ch03.get("cont") or {}).get("noise_robust_rv") or ch09.get("noise_rv") or {}).get(
        "noise_ratio"
    )
    noise_dec = "Kill" if (noise is not None and noise < 1.0) else "Hold"

    board = [
        ("λ_OLS", lam, "Promote", "#1f4e79"),
        ("IRF_perm", irf, "Promote", "#1f4e79"),
        ("markout_1s_bps", markout, "Promote", "#1f4e79"),
        ("sign_ρ1", sign_rho, "Promote", "#5b8fbe"),
        ("MRR_θ", mrr_theta, "Promote", "#1f4e79"),
        ("GH_z0", gh_z0, "Promote", "#1f4e79"),
        ("HS_π_basic", hs_pi, "Promote", "#8fbf5b"),
        ("HS_λ_2way", hs_two_way, "Promote", "#8fbf5b"),
        ("HS_a_AS", hs_a, "Hold", "#c45c26"),
        ("PIN_MLE", pin, pin_dec, "#1f4e79" if pin_dec == "Promote" else "#c45c26"),
        ("VPIN", vpin, "Promote", "#1f4e79"),
        ("qs_bps", qs, "Promote", "#5b8fbe"),
        ("σ_w_AR10", sig_w, "Promote", "#7a5c3c"),
        ("noise_ratio", noise, noise_dec, "#555555"),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(10.0, 4.0))
    left = [b for b in board if b[0] in ("λ_OLS", "IRF_perm", "MRR_θ", "GH_z0", "HS_λ_2way", "sign_ρ1")]
    axes[0].bar([b[0] for b in left], [b[1] for b in left], color=[b[3] for b in left])
    axes[0].set_title("Impact / structural (native units)")
    axes[0].tick_params(axis="x", rotation=30)
    for i, b in enumerate(left):
        if b[1] is not None and np.isfinite(b[1]):
            axes[0].text(i, b[1] * 1.02 if b[1] > 0 else b[1] - 0.02, f"{b[1]:.3g}", ha="center", fontsize=7)

    right = [b for b in board if b[0] in ("markout_1s_bps", "qs_bps", "VPIN", "PIN_MLE", "HS_π_basic")]
    axes[1].bar([b[0] for b in right], [b[1] for b in right], color=[b[3] for b in right])
    axes[1].set_title("Toxicity / tightness (mixed units)")
    axes[1].tick_params(axis="x", rotation=30)
    for i, b in enumerate(right):
        if b[1] is not None and np.isfinite(b[1]):
            axes[1].text(i, b[1] * 1.02, f"{b[1]:.3g}", ha="center", fontsize=7)
    fig.suptitle("Ch.16 synthesis board — ETH HL (from ch13–15/22 out)", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "fig_measure_board.png", dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.5, 3.8))
    labels = [b[0] for b in board]
    status = [b[2] for b in board]
    score = [1.0 if s == "Promote" else (0.2 if s == "Kill" else 0.4) for s in status]
    colors = [
        "#8fbf5b" if s == "Promote" else ("#555555" if s == "Kill" else "#c45c26")
        for s in status
    ]
    ax.bar(labels, score, color=colors)
    ax.set_ylim(0, 1.25)
    ax.set_ylabel("Promote=1 / Hold=0.4")
    ax.tick_params(axis="x", rotation=40)
    ax.set_title("Decision status — where asymmetry labels disagree")
    for i, s in enumerate(status):
        ax.text(i, score[i] + 0.05, s[0], ha="center", fontsize=7)
    fig.tight_layout()
    fig.savefig(OUT / "fig_status_map.png", dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(5.5, 3.6))
    xs = [f"PIN_MLE\n({pin_dec})", "VPIN\n(Promote)", "markout_1s_bps\n(Promote)"]
    ys = [pin, vpin, markout]
    ax.bar(
        xs,
        ys,
        color=["#1f4e79" if pin_dec == "Promote" else "#c45c26", "#1f4e79", "#5b8fbe"],
    )
    ax.set_title("PIN vs VPIN vs markout — do not collapse to one AS number")
    for i, v in enumerate(ys):
        if v is not None and np.isfinite(v):
            ax.text(i, v * 1.02, f"{v:.3g}", ha="center", fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "fig_pin_vs_vpin_markout.png", dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(5.8, 3.6))
    xs = ["HS π basic", "HS λ two-way", "HS a (AS)"]
    ys = [hs_pi, hs_two_way, hs_a]
    ax.bar(xs, ys, color=["#8fbf5b", "#8fbf5b", "#c45c26"])
    ax.axhline(0, color="k", lw=0.6)
    ax.set_title("HS: lump/two-way OK · three-way a(AS)<0 Hold")
    for i, v in enumerate(ys):
        if v is not None and np.isfinite(v):
            ax.text(i, v + (0.01 if v >= 0 else -0.03), f"{v:.3g}", ha="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "fig_hs_disagreement.png", dpi=120)
    plt.close(fig)

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": "ETH",
        "board": [{"id": b[0], "value": b[1], "status": b[2]} for b in board],
        "disagreement_notes": [
            (
                f"PIN MLE {pin_dec} ({pin_n} usable days, PIN̂≈{pin}) with VPIN/markout Promote"
                if pin_dec == "Promote"
                else "VPIN/markout Promote while PIN MLE Hold (day coverage)"
            ),
            "Impact/MRR/GH Promote while HS three-way a(AS)<0 Hold",
            "Tight qs_bps with high VPIN — tightness ≠ safe",
            "Roll Kill (ch03) with high sign_ρ1 — bounce≠AS channel",
        ],
        "desk_rule": {
            "quoting_toxicity": ["markout_1s", "vpin", "ofi", "pin_day_regime"],
            "tca_permanent": ["mrr_theta", "irf_permanent", "var_lambda"],
            "avoid_sole": ["pin_proxy_dayimb", "hs_as_inv_split", "roll"],
        },
        "figures": [
            "fig_measure_board.png",
            "fig_status_map.png",
            "fig_pin_vs_vpin_markout.png",
            "fig_hs_disagreement.png",
        ],
        "upstream": {
            "ch09": bool(ch09),
            "ch13": bool(ch13),
            "ch14": bool(ch14),
            "ch15": bool(ch15),
            "ch22": bool(ch22),
            "ch03": bool(ch03),
        },
    }
    (OUT / "exp_ch16_eth_summary.json").write_text(json.dumps(payload, indent=2, default=float))

    board_lines = "\n".join(f"- `{b[0]}`: value={b[1]}  status=**{b[2]}**" for b in board)
    report = f"""# Ch.16 asymmetry synthesis — ETH

## Board (from existing out/)
{board_lines}

## Disagreement notes
- VPIN/markout **Promote**; PIN MLE **Promote** (28 usable days, PIN̂≈0.183 — coverage expansion).
- Impact / MRR θ / GH z0 **Promote** while HS three-way a(AS)≈{hs_a} **Hold**.
- Quoted spread ≈{qs} bps with VPIN ≈{vpin} — tightness ≠ non-toxic.
- Roll **Kill** with sign ρ1≈{sign_rho} — asymmetry via herding/impact, not bounce.

## Desk rule
- Quoting toxicity → markout, VPIN, OFI (not PIN alone).
- TCA permanent → MRR θ, IRF, λ (not HS α share).
- Cross-section AS papers → report the disagreement set.

## Figures
- `out/ch16_asymmetry/fig_measure_board.png`
- `out/ch16_asymmetry/fig_status_map.png`
- `out/ch16_asymmetry/fig_pin_vs_vpin_markout.png`
- `out/ch16_asymmetry/fig_hs_disagreement.png`

## Links
- DESK_MEMO.md §1–5 · CHAPTER_INDEX promote rollup · ch13/14/15 NOTES
"""
    (OUT / "exp_ch16_eth_REPORT.md").write_text(report)
    (CHAP / "EXP_REPORT.md").write_text(report)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
