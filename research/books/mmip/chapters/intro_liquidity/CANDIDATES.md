# Intro candidates — Promote / Hold / Kill

Label: **D** descriptive · **T** tradable · **E** execution heuristic.

| id | type | definition | desk use | decision | falsifier |
|----|------|------------|----------|----------|-----------|
| `liq.quoted_spread_bps` | D | \(10^4(A-B)/M\) | Cost floor, make vs take | **Promote** | Train mean outside test CI for 3 consecutive days |
| `liq.depth_imbalance` | D→E | \((b-a)/(b+a)\) L0 | Quote skew / inventory lean | **Promote** | No short-horizon mid association (separate test) |
| `liq.role_blur_l1` | D monitor | \(\|u_v-s_v\|\) update vs size share | Flicker / unstable make venue | **Promote** | \(u\approx s\) all venues |
| `liq.update_hz` | D | BBO events / second | Latency / cancel regime | **Hold** | Needs RTT model before routing action |
| `liq.fei_size` | D | FEI on mean TOB size | Fragmentation regime | **Hold** | Same as Ch.1 — TOB≠trade share |

**Promotion rule:** Intro features are **inputs** to quoting/SOR/inventory — not standalone α.
