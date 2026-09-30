# Fragmentation — Herfindahl & venue crash share

**Book:** Tee & Ting (2019)  
**PDF:** §4.1 Herfindahl pp. 10–11 · Table II venue trade/volume · Table IX exchange crash split  
**Status:** `exp_run` (Pass 1+2)  
**Lib:** [`../../../../lib/fei.py`](../../../../lib/fei.py) · [`../../../../lib/epps.py`](../../../../lib/epps.py) · severity/Herfindahl/concordance in [`../../../../lib/crash.py`](../../../../lib/crash.py)  
**Venues (locked core):** Hyperliquid · Deribit · **Kraken**  
**Cross-links:** mmip `frag.crossed_nbbo`, `frag.update_share`, `epps.xvenue_corr`, `vol.fei_hourly`; empirical_mm `disc.jump_sign_concord`

---

## Pass 1 — paper objects

Volume Herfindahl on day t:

$$
H^v_t = \sum_{k=1}^{K}(s^k_t)^2,\quad s^k_t = \text{venue }k\text{ notional share}.
$$

- Core K=3: HL + Deribit + Kraken. Incomplete days (any leg missing) excluded from H^v means.  
- Venue share of **severity-gated** SSM (z*=6, |ΔP|≥5 bps, i_c≥3) and Nanex 30bps — Table IX analogue.  
- Raw SSM counts reported for honesty (micro-outlier flood).

## Pass 2 — info / signals dig

1. **Thin-venue concentration:** excess = crash_share − vol_share on the lowest-volume venue.  
2. **Concordance:** Kraken ↔ HL ↔ Deribit event match by absolute time (±1/5/30/60s); placebo circular-shift of event times.  
3. **FEI** on volume shares (`research.lib.fei`); **crossed-book** when ≥2 venues have TOB (mmip gate).  
4. **Epps** day vs ±60s crash windows (`corr_vs_lag`).  
5. **Falsifiers:** time-split H^v early/late; concordance placebo p; severity ablation 5→30bps.

## Identification assumptions

- USD notional: HL/Kraken = p×q (coin qty); **Deribit inverse perps = qty already USD** (do not multiply by p). Coin-volume Herfindahl reported as robustness.  
- Herfindahl only interpreted on days with **all three** venues complete.  
- SSM clock = trade time; concordance uses exchange timestamps as stored (no latency haircut).  
- Crossed-book requires multi-venue TOB — often unavailable on this warehouse slice.

## Severity gate (shared — Phase 4 reconciled)

**Primary Promote gate (stats / risk intensity):**

```
severity_gate(events, min_dp_pct=0.10, min_i_c=5)  # 10bps / ic5
```

**Frag share / thin-excess tables (denser counts; also documented):**

```
severity_gate(events, min_dp_pct=0.05, min_i_c=3)  # 5bps / ic3
```

Raw SSM @ z*=6 pooled **3668** → ≥5bps/ic3 **589** → ≥10bps/ic5 **275** → ≥30bps **76** (30bps share table) / **56** (30bps/ic10 stats ablation).

Desk risk intensity and xsec use **primary 10bps/ic5**. Frag venue-mix Promotes were re-checked at both gates in Phase 4 (`out/phase4_hardening/`).

