# EXP_REPORT — squeeze_regimes (Pass 1)

GEX+ mean=1.987e+12; corr(GEX+, range)=0.271.  
Scarce days (GEX+≤0) counted in `out/squeeze_regimes/` after regime exp.

**Decision: Hold** — regime map / risk strip only.


## Pass 2b falsifiers (auto)

- **Panel:** panel_gex_options n=9 · DDOI=`PROXY_trade_flow_DDOI`.
- **Day-block corr(GEX, HL RV):** -0.2162754128722743 CI[-0.7386447742588608, 0.5912940092387926].
- **Chrono:** early=['2026-09-14', '2026-09-15', '2026-09-16', '2026-09-17'] late=['2026-09-18', '2026-09-25', '2026-09-26', '2026-09-27', '2026-10-01'] · GEX↔RV stable=True.
- **Placebo shuffle GEX:** exceeds_p95_rv=False.
- **Venue-drop HL vs DB sign concordant:** True.
- **spot_l2:** appendix only (n=4).
- **Decision:** 0 Promote; monitors **Hold**; Kill TOB-cross α / trade_synth.
