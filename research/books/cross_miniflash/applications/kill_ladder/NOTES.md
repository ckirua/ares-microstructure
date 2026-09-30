# Gated SSM kill-ladder

**Track:** RISK · **Readiness target:** Promote-as-risk-policy (monitor→soft rule)  
**Objects:** `risk.ssm_severity_gate_10bps` · `risk.ssm_zstar_scan_table` · `vol.sigma_m_noise_floor_1bp`  
**Lib:** `research/lib/crash.py` · shared `applications/scripts/_common.py`

## Rule sketch

Detection: z*=6 + σ_m floor + 10bps/ic5 gate. Escalation uses **within-gated** z percentiles
(absolute {8,10,12} bands collapse on this tape — gated median |z|≈16).

| Tier | Trigger | Action |
|------|---------|--------|
| observe | |z| < p25, intensity=1, no Nanex | Log only |
| widen | p25≤|z|<p50 or intensity=2 or Nanex alone | Soft clip / widen |
| size_cap | p50≤|z| or intensity∈{3,4} | Cap aggressive size |
| halt | intensity≥5 or (Nanex∧intensity≥2) or |ΔP|≥p90 | Halt aggressive (venue-local) |

## Simulation design

1. Build event panel (HL+DB+KR × ETH/BTC × slice days).
2. Label each gated event with ladder tier.
3. Outcomes vs observe-isolated controls + placebo windows.
4. Early/late day split + bootstrap CI on Δ|mo|.
5. Friction: require Δ|mo| > 2bps with CI>0 before executable claim.

## Formulas

Rolling intensity for event \(i\):

\[
I_i(W) = \#\{j:\, t_j \in (t_i-W,\,t_i]\},\quad W=60\mathrm{s}.
\]

Crash-signed tape markout:

\[
\mathrm{mo}_h = d\cdot\frac{p_{t+h}-p_t}{p_t}\times 10^4\ \mathrm{bps}.
\]

## Honesty

- No mid fantasy fills; tape-only markout.
- Venue-local (concordance Hold).
- V-recovery share among fire = false-positive cost of hard halt.
