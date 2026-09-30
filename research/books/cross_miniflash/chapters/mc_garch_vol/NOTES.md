# MC-GARCH volatility — \(h_n\), \(s_j\), \(q_{n,j}\) → \(\sigma_p,\sigma_m\)

**Book:** Tee & Ting (2019)  
**PDF:** §3.1–3.2 MC-GARCH + KF variance feed pp. 8–10 · Fig 1 diurnal  
**Status:** `exp_run`  
**Lib:** [`../../../../lib/crash.py`](../../../../lib/crash.py) — `diurnal_sj`, `mc_garch_bar_vol`, `sigma_process_meas`  
**Reuse:** mmip `vol.curve_intraday`  
**Out:** [`../../out/phase2_baselines_ssm/`](../../out/phase2_baselines_ssm/)

---

## Pass 1 — formulas (UTC crypto)

5-minute bars, \(N_j=288\) per UTC day:

\[
h_n=\sum_j r_{n,j}^2,\quad
\hat s_j=\frac{1}{N}\sum_n\frac{r_{n,j}^2}{h_n}\ (\mathrm{norm\ }E[s]\approx1),\quad
z_{n,j}=\frac{r_{n,j}}{\sqrt{h_n s_j}}.
\]

\(q_{n,j}\) = GARCH(1,1) variance of \(z\) (Engle–Sokalska style), renormalized \(E[q]=1\).

Locked map:

\[
\sigma_p^2\Delta t \propto q\,h\,s\cdot\Delta t,\qquad
\sigma_m=\texttt{frac}\cdot\max\big(\mathrm{MAD}(\Delta\log p),\,10^{-4}\big).
\]

Default `frac=1.0`. Without the 1 bp noise floor, tick-clustered tapes collapse \(R\) and flood SSM flags.

---

## Pass 2 — diurnal signal, σ stress, vol.curve link

### Diurnal as signal
- Pooled hour notional share peaks at **UTC 12** (share≈0.091).  
- mmip Promote `vol.curve_intraday` peaked ~**18 UTC** on later HL-dense days — **sample-dependent**; treat as schedule prior, re-estimate per cohort.  
- Slot-level SSM crash intensity overlays `s_j` in `fig_diurnal_vs_crashes.png` (some empty-slot \(s_j\) spikes — flag sparse bins).

### σ_m / σ_p stress (SSM z*=6 pooled events)

| frac | n_SSM |
|-----:|------:|
| 0.5 | 13832 |
| 1.0 | **3668** |
| 2.0 | 808 |
| 4.0 | 177 |

**Falsifier:** 8× swing in crash count across frac ∈[0.5,4] → cannot Promote a single σ_m without publishing the stress table + noise floor.

### Vol-state conditioning
Time-split SSM early/late ≈2055/1868 (stable-ish). High-\(s_j\) slots coincide with bursty crash starts on HL event days (09-08/09) — qualitative; Phase 3 should bucket crash rate by \(h_n\) quintile.
