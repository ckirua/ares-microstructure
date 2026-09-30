| id | type | lenses | decision | falsifier |
|----|------|--------|----------|----------|
| `frag.volume_herfindahl_3venue` | D | frag, liq, mm | **Promote** | time-split \|ΔH^v\| early/late ≥0.15 or incomplete legs |
| `frag.crash_venue_share` | D | frag, risk | **Promote** | severity gate off → HL micro-flood dominates share |
| `frag.thin_venue_crash_excess` | D | frag, risk, liq | **Promote** | thin_excess≤0 or flips on 30bps gate / time-split |
| `frag.xvenue_crash_concord` | D | frag, risk, info | **Hold** | placebo p≥0.2 or Jaccard≈0 at 5s |
| `frag.fei_volume_3venue` | D | frag, liq | **Promote** | FEI on incomplete venue set |
| `frag.crossed_nbbo_crashwin` | E | frag, exec | **Hold** | need dense multi-venue TOB on slice days (mmip Promote still stands) |
| `epps.crash_window_corr` | D | frag, cont | **Hold** | crash-window corr not reliably < day Epps on this slice |

**Headline:** pooled \(H^v\)≈**0.490** · mean day \(H^v\)≈**0.482** · FEI_vol≈**0.750**.  
Vol shares HL/DB/KR ≈ **4.0% / 36.2% / 59.7%** (USD; Deribit inverse qty). Coin-share robustness: ≈18% / 34% / 48%.  
Crash share SSM≥5bps ≈ **82.5% / 10.2% / 7.3%** (raw 3668 → gated 589).  
Concord Jaccard@5s: HL–DB **0**, HL–KR **0**, DB–KR **0.126**; placebo p(ge obs)≈**0.58** → Hold.  
Thin excess (HL lowest USD share): mean≈**+0.78**.

**Cross-links:** mmip `frag.crossed_nbbo` (gate), `epps.xvenue_corr`, `vol.fei_hourly`; empirical_mm `disc.jump_sign_concord`.

## Phase 4 harden

Program-wide bootstrap/time-split applied (`scripts/exp_final_hardening.py` → `out/phase4_hardening/hardening_gates.json`). Gate note: primary **10bps/ic5**; frag share also **5bps/ic3**.
| id | Phase4 decision | harden why |
|----|-----------------|------------|
| `frag.volume_herfindahl_3venue` | **Promote** | H^v boot CI95=[0.463,0.499]; early/late=0.500/0.468 |Δ|=0.032 |
| `frag.fei_volume_3venue` | **Promote** | FEI_vol boot CI95=[0.721,0.784] on complete 3-venue days |
| `frag.crash_venue_share` | **Promote** | HL crash share @10bps=0.829 (early 0.660 / late 0.917); frag tables also report 5bps/ic3 |
| `frag.thin_venue_crash_excess` | **Promote** | HL thin excess @5bps bootCI=[0.628,0.828] early/late=0.745/0.714; @30bps lo=0.533; @10bps point=0.78 |
| `frag.xvenue_crash_concord` | **Hold** | placebo p(ge obs)≈0.58; Jaccard@5s={'hyperliquid_deribit': 0.0, 'hyperliquid_kraken': 0.0, 'deribit_ |
| `frag.crossed_nbbo_crashwin` | **Hold** | n_crossed_available=0 on slice; mmip crossed_nbbo still stands |
| `epps.crash_window_corr` | **Hold** | crash-window Epps not reliably < day Epps |
