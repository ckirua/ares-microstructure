# H^v / FEI capacity → child sizing

**Track:** EXEC/SOR · **Objects:** `frag.volume_herfindahl_3venue` · `frag.fei_volume_3venue`

## Formulas

\[
H^v=\sum_k (s^k)^2,\quad \mathrm{FEI}=H_{\mathrm{Shannon}}(s)/\log N.
\]

POV child (paper): take \(\pi\) of each print; impact \(=10^4\cdot(vwap-p_0)/p_0\).

## Schedule

| H^v Q | \(\pi\) |
|------:|--------:|
| 0 (dispersed) | 0.08 |
| 1 | 0.06 |
| 2 | 0.04 |
| 3 (concentrated) | 0.025 |

## Honesty

No self-impact feedback into tape. Schedule is a capacity prior, not a calibrated Almgren–Chriss path.
