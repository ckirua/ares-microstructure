#!/usr/bin/env python3
"""Build executed-style notebooks that load summary JSON + display figures."""

from __future__ import annotations

import base64
import json
from pathlib import Path

BOOK = Path(__file__).resolve().parents[1]


def _img_output(path: Path) -> dict:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        "output_type": "display_data",
        "data": {"image/png": data, "text/plain": [f"<IPython.core.display.Image object>"]},
        "metadata": {},
    }


def _code_cell(source: str, outputs: list | None = None, exec_count: int | None = 1) -> dict:
    return {
        "cell_type": "code",
        "execution_count": exec_count,
        "metadata": {},
        "outputs": outputs or [],
        "source": [line + "\n" for line in source.split("\n")],
    }


def _md_cell(source: str) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": [line + "\n" for line in source.split("\n")],
    }


def build_chapter_nb(
    *,
    chap_dir: Path,
    nb_name: str,
    title_md: str,
    out_rel: str,
    summary_name: str,
    print_keys: list[str],
    figures: list[tuple[str, str]],
    takeaway_md: str,
) -> Path:
    out = BOOK / "out" / out_rel
    summary = out / summary_name
    d = json.loads(summary.read_text()) if summary.exists() else {}

    # summary cell
    prints = "\n".join(f"print({k!r}, d.get({k!r}))" for k in print_keys)
    src_sum = (
        "from pathlib import Path\n"
        "import json\n"
        f"OUT = Path('../../out/{out_rel}').resolve()\n"
        f"d = json.loads((OUT / '{summary_name}').read_text())\n"
        f"{prints}\n"
        "print('figures', d.get('figures'))"
    )
    # build text output from actual data
    lines = []
    for k in print_keys:
        lines.append(f"{k} {d.get(k)}")
    lines.append(f"figures {d.get('figures')}")
    out_stream = {
        "output_type": "stream",
        "name": "stdout",
        "text": [l + "\n" for l in lines],
    }

    cells = [_md_cell(title_md), _code_cell(src_sum, outputs=[out_stream], exec_count=1)]
    for i, (caption, fig) in enumerate(figures):
        cells.append(_md_cell(f"### {caption}\n\n`{fig}`"))
        p = out / fig
        src = (
            "from IPython.display import Image, display\n"
            f"p = OUT / '{fig}'\n"
            "print(p, 'exists', p.exists(), 'bytes', p.stat().st_size if p.exists() else 0)\n"
            "display(Image(filename=str(p)))"
        )
        outputs = [
            {
                "output_type": "stream",
                "name": "stdout",
                "text": [
                    f"{p} exists {p.exists()} bytes {p.stat().st_size if p.exists() else 0}\n"
                ],
            }
        ]
        if p.exists():
            outputs.append(_img_output(p))
        cells.append(_code_cell(src, outputs=outputs, exec_count=i + 2))
    cells.append(_md_cell(takeaway_md))

    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
        "cells": cells,
    }
    dest = chap_dir / nb_name
    dest.write_text(json.dumps(nb, indent=1))
    return dest


def main() -> None:
    # ch03
    build_chapter_nb(
        chap_dir=BOOK / "chapters" / "ch03_roll",
        nb_name="ch03_roll.ipynb",
        title_md=(
            "# Ch.3 Roll model (disc) + noise clocks (cont)\n\n"
            "Hasbrouck notes pp. 20–22 · Roll c=sqrt(-γ1) identification.\n\n"
            "Figures from `scripts/plot_ch03_roll.py`."
        ),
        out_rel="ch03_roll",
        summary_name="exp_ch03_eth_summary.json",
        print_keys=["decisions", "n_trades", "n_mids", "days"],
        figures=[
            ("Event / trade autocovariance (Roll needs γ1<0)", "fig_roll_acov.png"),
            ("Identification map train/test", "fig_roll_id_map.png"),
            ("Noise RV vs sampling horizon", "fig_noise_rv_curve.png"),
            ("Calendar vs volume-clock ACF", "fig_clock_acf.png"),
            ("Mid path context", "fig_mid_path.png"),
        ],
        takeaway_md=(
            "## Desk takeaway\n\n"
            "- **Kill** `disc.roll_event_mid` and `disc.roll_trade_px` (γ1≥0).\n"
            "- **Hold** `cont.noise_rv_ratio` (~0.90) and `cont.volclock_ac1`.\n"
            "- Use quoted spread (Ch.22) + AR σ_w (Ch.9), not Roll 2c."
        ),
    )
    # ch08
    build_chapter_nb(
        chap_dir=BOOK / "chapters" / "ch08_noise",
        nb_name="ch08_noise.ipynb",
        title_md=(
            "# Ch.8 Univariate RW / microstructure noise (cont)\n\n"
            "Hasbrouck notes pp. 61–71 · MA-first / BN; paired with Ch.3.\n\n"
            "Figures from `scripts/plot_ch03_roll.py` → `out/ch08_noise/`."
        ),
        out_rel="ch08_noise",
        summary_name="exp_ch08_eth_summary.json",
        print_keys=["decisions", "days", "paired_with"],
        figures=[
            ("RV vs horizon (sampling-noise diagnostic)", "fig_noise_rv_curve.png"),
            ("Calendar vs volume-clock ACF", "fig_clock_acf.png"),
        ],
        takeaway_md=(
            "## Desk takeaway\n\n"
            "- Fine/coarse RV is **not** the BN pricing-error bound.\n"
            "- noise_ratio≈0.9 ⇒ no bounce inflation on collector mid (**Hold**).\n"
            "- Permanent vol: use Ch.9 `disc.ar_sigma_w` / MA moments."
        ),
    )
    # ch09
    build_chapter_nb(
        chap_dir=BOOK / "chapters" / "ch09_estimation",
        nb_name="ch09_estimation.ipynb",
        title_md=(
            "# Ch.9 Estimation case (MA/AR / BN σ_w)\n\n"
            "Hasbrouck notes pp. 72–79 · Case Study I remake on HL ETH.\n\n"
            "Ch.4 MA/AR toolkit folded into NOTES. Second pass: VR + lag sweep.\n\n"
            "Figures from `scripts/plot_ch09_estimation.py`."
        ),
        out_rel="ch09_estimation",
        summary_name="exp_ch09_eth_summary.json",
        print_keys=["decisions", "n_dp", "days", "second_pass"],
        figures=[
            ("Event Δlog mid ACF", "fig_return_acf.png"),
            ("σ_w comparison (MA / AR / blocks)", "fig_sigma_w_compare.png"),
            ("AR→MA impact multipliers", "fig_ar_irf.png"),
            ("Variance ratios (event + calendar)", "fig_variance_ratio.png"),
            ("BN σ_w vs AR truncation K", "fig_ar_lag_sweep.png"),
        ],
        takeaway_md=(
            "## Desk takeaway\n\n"
            "- **Promote** `disc.ma1_moments` and `disc.ar_sigma_w`.\n"
            "- **Kill** Roll-vs-quote; **Hold** noise RV.\n"
            "- VR(q)≠1 and lag-sweep sensitivity ⇒ publish day-block SE, not a single K."
        ),
    )
    # ch16
    build_chapter_nb(
        chap_dir=BOOK / "chapters" / "ch16_asymmetry",
        nb_name="ch16_asymmetry.ipynb",
        title_md=(
            "# Ch.16 Asymmetry synthesis (Ch.13–15 measures)\n\n"
            "Hasbrouck notes p. 124 · when PIN vs impact vs HS disagree.\n\n"
            "Comparative board from existing `out/ch13|14|15|09|22`.\n\n"
            "Figures from `scripts/plot_ch16_asymmetry.py`."
        ),
        out_rel="ch16_asymmetry",
        summary_name="exp_ch16_eth_summary.json",
        print_keys=["board", "disagreement_notes", "desk_rule"],
        figures=[
            ("Measure board (impact vs toxicity)", "fig_measure_board.png"),
            ("Promote / Hold status map", "fig_status_map.png"),
            ("PIN vs VPIN vs markout", "fig_pin_vs_vpin_markout.png"),
            ("HS lump/two-way vs three-way a(AS)", "fig_hs_disagreement.png"),
        ],
        takeaway_md=(
            "## Desk takeaway\n\n"
            "- Do not collapse asymmetry to a single PIN / Roll number.\n"
            "- Quoting toxicity → markout + VPIN + OFI.\n"
            "- TCA permanent → MRR θ / IRF / λ; HS α|β stays Hold on public tape."
        ),
    )
    # ch10
    build_chapter_nb(
        chap_dir=BOOK / "chapters" / "ch10_trades",
        nb_name="ch10_trades.ipynb",
        title_md=(
            "# Ch.10 Trade process and inventory control\n\n"
            "Hasbrouck notes pp. 80–86 · Garman / Amihud–Mendelson + sign ACF.\n\n"
            "Empirics from Ch.13 sign ACF + Ch.15 intensity/VPIN + light size/vol-clock.\n\n"
            "SECOND PASS: inventory/trades ↔ Ch.13 permanent impact + Ch.15 toxicity.\n\n"
            "Figures from `scripts/plot_ch10_trades.py`."
        ),
        out_rel="ch10_trades",
        summary_name="exp_ch10_eth_summary.json",
        print_keys=["decisions", "n_trades_overlap", "days", "second_pass"],
        figures=[
            ("Trade-sign ACF (Ch.10.d herding)", "fig_sign_acf.png"),
            ("Calendar intensity + volume-clock sign ACF", "fig_intensity_volclock.png"),
            ("Trade size density + moment ceiling", "fig_trade_size.png"),
            ("Cum-flow inventory proxy (Hold as control)", "fig_cumflow_inv.png"),
        ],
        takeaway_md=(
            "## Desk takeaway\n\n"
            "- **Promote** `disc.sign_acf`, `cont.trade_intensity` (+ VPIN via Ch.15).\n"
            "- Permanent channel = Ch.13 IRF/markout; inventory quote-skew stays **Hold**.\n"
            "- Pair ρ₁ + intensity clustering with Ch.15 VPIN for toxicity pacing."
        ),
    )
    # ch18
    build_chapter_nb(
        chap_dir=BOOK / "chapters" / "ch18_limit_orders",
        nb_name="ch18_limit_orders.ipynb",
        title_md=(
            "# Ch.18–21 Limit-order empirics (Part III)\n\n"
            "Hasbrouck notes pp. 132–157 · Sandas / CMSW / Foucault / Parlour.\n\n"
            "Public-tape TOB + L1 Sandas moments — OE/queue Holds explicit.\n\n"
            "Figures from `scripts/plot_ch18_limit_orders.py`."
        ),
        out_rel="ch18_limit_orders",
        summary_name="exp_ch18_eth_summary.json",
        print_keys=["decisions", "n_tob", "n_trades", "days", "data_ceilings"],
        figures=[
            ("Time-to-touch vs tick offset", "fig_time_to_touch.png"),
            ("Size-at-touch fill-proxy survival", "fig_size_touch_survival.png"),
            ("TOB cancel vs fill depletion shares", "fig_cancel_vs_fill.png"),
            ("Sandas L1 depth decay / schedule", "fig_sandas_depth.png"),
            ("Resilience + same-side refill", "fig_resilience_refill.png"),
            ("Parlour depth↔aggressor + LO clocks", "fig_parlour_lob_clocks.png"),
        ],
        takeaway_md=(
            "## Desk takeaway\n\n"
            "- Touch / size-touch / cancel / refill / Sandas L1 / Parlour: **Promote**.\n"
            "- `info.improve_markout`: **Kill** (continuation).\n"
            "- OE fill hazard, queue value, structural Sandas GMM, Stoll/CMSW EU: **Hold**."
        ),
    )
    # ch15
    build_chapter_nb(
        chap_dir=BOOK / "chapters" / "ch15_pin",
        nb_name="ch15_pin.ipynb",
        title_md=(
            "# Ch.15 PIN (disc) + VPIN / intensity (cont)\n\n"
            "Hasbrouck notes pp. 115–123 · EHO day-mixture vs volume-clock toxicity.\n\n"
            r"$$\mathrm{PIN}=\frac{\alpha\mu}{\alpha\mu+\varepsilon_B+\varepsilon_S}$$"
            "\n\n"
            "SECOND PASS densify: day panel + VPIN path + markout cross-link.\n\n"
            "Figures from `scripts/plot_ch15_pin.py`."
        ),
        out_rel="ch15_pin",
        summary_name="exp_ch15_eth_summary.json",
        print_keys=["decisions", "n_days_mle_usable", "disc_pin_eho_mle", "cont_vpin", "cont_intensity", "blockers"],
        figures=[
            ("Day-level (B,S) scatter — EHO mixture inputs", "fig_bs_scatter.png"),
            ("PIN day panel (imb + span_h, usable in green)", "fig_pin_day_panel.png"),
            ("PIN vs VPIN levels (not interchangeable)", "fig_pin_vs_vpin.png"),
            ("VPIN rolling path (recent usable days)", "fig_vpin_path.png"),
            ("VPIN / intensity vs Ch.13 markout", "fig_vpin_vs_markout.png"),
            ("Trade intensity λ̂ + count ac1", "fig_intensity.png"),
        ],
        takeaway_md=(
            "## Desk takeaway\n\n"
            "- **Promote** `cont.vpin` (~0.905) and `cont.trade_intensity`.\n"
            "- **Promote** EHO PIN (28 usable days) ; **Hold** day-imb proxy.\n"
            "- VPIN = *when* to widen; Ch.13 markout = *how much* AS edge."
        ),
    )
    # ch05 (synthetic)
    build_chapter_nb(
        chap_dir=BOOK / "chapters" / "ch05_seq_info",
        nb_name="ch05_seq_info.ipynb",
        title_md=(
            "# Ch.5 Sequential trade (Glosten–Milgrom) — study guide\n\n"
            "Hasbrouck notes pp. 29–40 · theory parent of Ch.14–15.\n\n"
            "**All figures SYNTHETIC** (labeled). Empirics live in ch13/14/15.\n\n"
            "Figures from `scripts/plot_ch05_seq_info.py`."
        ),
        out_rel="ch05_seq_info",
        summary_name="exp_ch05_synthetic_summary.json",
        print_keys=["kind", "label", "params_example", "empirics_owners"],
        figures=[
            ("Spread vs μ (δ=½ linear AS)", "fig_spread_vs_mu.png"),
            ("Pr(Informed|Buy) vs μ", "fig_pr_informed_buy.png"),
            ("Quote / belief path after buys & sells", "fig_quote_belief_path.png"),
            ("Permanent-impact cartoon → Ch.13 IRF", "fig_impact_cartoon.png"),
        ],
        takeaway_md=(
            "## Desk takeaway\n\n"
            "- GM: wider quotes + permanent impact when μ high.\n"
            "- Stack days → PIN; continuous flow → VPIN / markout.\n"
            "- Do not estimate GM closed forms on HL here — use sibling empirics."
        ),
    )
    # ch06 (synthetic)
    build_chapter_nb(
        chap_dir=BOOK / "chapters" / "ch06_strategic",
        nb_name="ch06_strategic.ipynb",
        title_md=(
            "# Ch.6 Strategic trade (Kyle) — study guide\n\n"
            "Hasbrouck notes pp. 41–51 · λ as inverse liquidity; order splitting.\n\n"
            "**All figures SYNTHETIC** (labeled). Empirics: ch13/14 + mmip POV.\n\n"
            "Figures from `scripts/plot_ch06_strategic.py`."
        ),
        out_rel="ch06_strategic",
        summary_name="exp_ch06_synthetic_summary.json",
        print_keys=["kind", "label", "single_period", "empirics_owners"],
        figures=[
            ("Kyle λ vs σ_u and Σ₀", "fig_kyle_lambda_statics.png"),
            ("Single-period (y,p) cloud", "fig_kyle_yp_scatter.png"),
            ("Multiperiod S_k / b_k / λ_k (book T=4)", "fig_kyle_multiperiod.png"),
            ("Order-split vs dump cartoon", "fig_order_split_cartoon.png"),
        ],
        takeaway_md=(
            "## Desk takeaway\n\n"
            "- λ = permanent-impact prior for TCA / POV (measure via Ch.13/14).\n"
            "- Multiperiod: early flow costlier; split into declining λ.\n"
            "- Pure Kyle ⇒ uncorrelated net flow; HL sign ACF is more GM/herding."
        ),
    )
    print("notebooks written")


if __name__ == "__main__":
    main()
